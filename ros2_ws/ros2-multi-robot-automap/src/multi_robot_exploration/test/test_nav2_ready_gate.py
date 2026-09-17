from lifecycle_msgs.msg import Transition
from multi_robot_exploration.nav2_ready_gate import (
    lifecycle_change_service_names,
    lifecycle_service_names,
    navigation_action_names,
    recovery_transition,
    unavailable_actions,
)


class FakeActionClient:
    def __init__(self, ready):
        self.ready = ready

    def server_is_ready(self):
        return self.ready


def test_navigation_action_names_follow_robot_count():
    assert navigation_action_names(3) == [
        "/tb1/navigate_to_pose",
        "/tb2/navigate_to_pose",
        "/tb3/navigate_to_pose",
    ]


def test_unavailable_actions_reports_only_missing_servers():
    clients = {
        "/tb1/navigate_to_pose": FakeActionClient(True),
        "/tb2/navigate_to_pose": FakeActionClient(False),
    }
    assert unavailable_actions(clients) == ["/tb2/navigate_to_pose"]


def test_lifecycle_service_names_cover_critical_nav2_nodes():
    assert lifecycle_service_names(1) == [
        "/tb1/controller_server/get_state",
        "/tb1/planner_server/get_state",
        "/tb1/behavior_server/get_state",
        "/tb1/bt_navigator/get_state",
        "/tb1/waypoint_follower/get_state",
        "/tb1/velocity_smoother/get_state",
    ]


def test_lifecycle_change_service_names_follow_robot_count():
    names = lifecycle_change_service_names(2)

    assert names[0] == "/tb1/controller_server/change_state"
    assert names[-1] == "/tb2/velocity_smoother/change_state"
    assert len(names) == 12


def test_lifecycle_recovery_configures_before_activating():
    states = {
        "/tb1/controller_server/get_state": "inactive",
        "/tb1/planner_server/get_state": "unconfigured",
    }

    assert recovery_transition(states) == (
        "/tb1/planner_server/get_state",
        Transition.TRANSITION_CONFIGURE,
    )
    states["/tb1/planner_server/get_state"] = "inactive"
    assert recovery_transition(states) == (
        "/tb1/controller_server/get_state",
        Transition.TRANSITION_ACTIVATE,
    )


def test_lifecycle_recovery_waits_during_transition():
    assert recovery_transition({"node/get_state": "configuring"}) is None
