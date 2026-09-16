from multi_robot_exploration.nav2_ready_gate import (
    lifecycle_service_names,
    navigation_action_names,
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
        "/tb1/bt_navigator/get_state",
    ]
