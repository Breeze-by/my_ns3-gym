"""Regression checks for delayed or failed Nav2 action handshakes."""

from types import MethodType, SimpleNamespace

from action_msgs.msg import GoalStatus
import pytest
from rclpy.task import Future

from multi_robot_exploration import control
from multi_robot_exploration.control import HeadquartersControl


def make_controller():
    clock = [0.0]
    messages = []
    assignment = SimpleNamespace(x=2.0, y=0.0, navigation_x=2.0, navigation_y=0.0)

    def noop(*args):
        pass
    node = SimpleNamespace(
        now=lambda: clock[0],
        get_logger=lambda: SimpleNamespace(error=noop, warn=noop, info=noop),
        failure_publisher=SimpleNamespace(publish=messages.append),
        goal_targets={"tb1": assignment}, goal_handles={"tb1": None},
        goal_requests={"tb1": Future()}, goal_requested_at={"tb1": 0.0},
        goal_results={"tb1": None}, goal_cancel_started_at={"tb1": None},
        goal_cancel_rejected={"tb1": False},
        failed_navigation={}, robot_states={"tb1": "active"},
        goal_started_at={"tb1": None}, goal_last_progress_at={"tb1": None},
        goal_best_distance={"tb1": None}, goal_last_position={"tb1": None},
        goal_known_count={"tb1": 0}, goal_initial_gain={"tb1": 1000},
        cancel_requested={"tb1": False}, robot_positions={"tb1": (0.0, 0.0)},
        map_known_count=0, target_history=[], bad_targets=[],
        goal_timeout_sec=60.0, response_timeout_sec=10.0, cancel_timeout_sec=10.0,
        target_information_gain=lambda *args: 1000,
        check_exploration_completion=noop,
    )
    for name in (
        "cancel_stalled_goals", "goal_response_callback", "goal_result_callback",
        "fail_navigation", "request_cancel", "cancel_response_callback", "finish_goal",
    ):
        setattr(node, name, MethodType(getattr(HeadquartersControl, name), node))
    return node, clock, messages, assignment


def make_handle():
    result = Future()
    cancel = Future()
    handle = SimpleNamespace(
        accepted=True, goal_id=SimpleNamespace(uuid=[1] * 16),
        get_result_async=lambda: result, cancel_goal_async=lambda: cancel,
    )
    return handle, result, cancel


def accept_goal(node, assignment):
    handle, result, cancel = make_handle()
    response = node.goal_requests["tb1"]
    response.set_result(handle)
    node.goal_response_callback("tb1", assignment, response)
    return handle, result, cancel


def test_missing_acceptance_fails_without_releasing_unknown_ownership():
    node, clock, messages, assignment = make_controller()
    clock[0] = 10.0
    node.cancel_stalled_goals()
    assert node.robot_states["tb1"] == "failed"
    assert node.goal_targets["tb1"] is assignment
    assert "navigation_response_timeout" in messages[0].data
    node.cancel_stalled_goals()
    assert len(messages) == 1


def test_late_acceptance_is_cancelled_and_cannot_reenable_robot():
    node, clock, messages, assignment = make_controller()
    clock[0] = 11.0
    handle, result, cancel = accept_goal(node, assignment)
    assert node.cancel_requested["tb1"]
    assert node.robot_states["tb1"] == "failed"
    cancel.set_result(SimpleNamespace(goals_canceling=[SimpleNamespace(goal_id=handle.goal_id)]))
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    assert node.robot_states["tb1"] == "failed"
    assert len(messages) == 1


def test_cancel_needs_terminal_result_and_times_out_if_missing():
    node, clock, messages, assignment = make_controller()
    handle, _, cancel = accept_goal(node, assignment)
    node.request_cancel("tb1", assignment)
    cancel.set_result(SimpleNamespace(goals_canceling=[SimpleNamespace(goal_id=handle.goal_id)]))
    clock[0] = 10.0
    node.cancel_stalled_goals()
    assert node.goal_handles["tb1"] is handle
    assert node.robot_states["tb1"] == "failed"
    assert "navigation_cancel_timeout" in messages[0].data


def test_rejected_cancel_fails_if_no_terminal_result_arrives_by_deadline():
    node, clock, messages, assignment = make_controller()
    _, _, cancel = accept_goal(node, assignment)
    node.request_cancel("tb1", assignment)
    cancel.set_result(SimpleNamespace(goals_canceling=[]))
    assert not messages
    clock[0] = 10.0
    node.cancel_stalled_goals()
    assert "navigation_cancel_rejected" in messages[0].data
    assert node.robot_states["tb1"] == "failed"


def test_cancel_racing_with_terminal_result_does_not_report_failure():
    node, _, messages, assignment = make_controller()
    _, result, cancel = accept_goal(node, assignment)
    node.request_cancel("tb1", assignment)
    cancel.set_result(SimpleNamespace(goals_canceling=[]))
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    assert node.robot_states["tb1"] == "idle"
    assert not messages


def test_normal_cancel_releases_ownership_only_after_terminal_result():
    node, _, messages, assignment = make_controller()
    handle, result, cancel = accept_goal(node, assignment)
    node.request_cancel("tb1", assignment)
    cancel.set_result(SimpleNamespace(goals_canceling=[SimpleNamespace(goal_id=handle.goal_id)]))
    assert node.robot_states["tb1"] == "active"
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    assert node.robot_states["tb1"] == "idle"
    assert not messages


def test_old_result_callback_cannot_clear_a_new_assignment():
    node, _, _, assignment = make_controller()
    node.goal_targets["tb1"] = object()
    node.goal_result_callback("tb1", assignment, Future())
    assert node.robot_states["tb1"] == "active"
    assert node.goal_targets["tb1"] is not None


def test_shared_sensor_failure_cancels_active_and_late_accepted_goals():
    node, _, messages, assignment = make_controller()
    HeadquartersControl.stop_on_failure(node, SimpleNamespace(data="peer_state_unavailable"))
    assert node.robot_states["tb1"] == "failed"
    assert node.goal_targets["tb1"] is assignment
    _, result, _ = accept_goal(node, assignment)
    assert node.cancel_requested["tb1"]
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    assert node.robot_states["tb1"] == "failed"
    assert not messages


@pytest.mark.parametrize("error", [
    KeyboardInterrupt, control.ExternalShutdownException, ValueError,
])
def test_control_main_cleans_context_when_construction_is_interrupted(monkeypatch, error):
    context_live = [True]

    def construct():
        raise error("construction stopped")

    monkeypatch.setattr(control, "HeadquartersControl", construct)
    monkeypatch.setattr(control.rclpy, "init", lambda **kwargs: None)
    monkeypatch.setattr(control.rclpy, "ok", lambda: context_live[0])
    monkeypatch.setattr(control.rclpy, "shutdown", lambda: context_live.__setitem__(0, False))
    monkeypatch.setattr(
        control.rclpy, "spin", lambda *args: pytest.fail("constructor did not finish")
    )
    if error is ValueError:
        with pytest.raises(ValueError, match="construction stopped"):
            control.main()
    else:
        control.main()
    assert not context_live[0]


def test_control_main_keeps_cleanup_errors_visible_and_closes_context(monkeypatch):
    context_live = [True]

    def destroy():
        raise OSError("node cleanup failed")

    class Executor:
        def __init__(self, **kwargs):
            pass

        def add_node(self, node):
            pass

        def spin_once(self, timeout_sec):
            raise KeyboardInterrupt()

        def shutdown(self, timeout_sec):
            return True

    node = SimpleNamespace(context=object(), destroy_node=destroy)
    monkeypatch.setattr(control, "HeadquartersControl", lambda: node)
    monkeypatch.setattr(control, "SingleThreadedExecutor", Executor)
    monkeypatch.setattr(control.rclpy, "init", lambda **kwargs: None)
    monkeypatch.setattr(control.rclpy, "ok", lambda **kwargs: context_live[0])
    monkeypatch.setattr(control.rclpy, "shutdown", lambda: context_live.__setitem__(0, False))
    with pytest.raises(OSError, match="node cleanup failed"):
        control.main()
    assert not context_live[0]


CONVERSION_ERROR = (
    "Unable to convert call argument to Python object (compile in debug mode for details)"
)


@pytest.mark.parametrize("context_closes,error,shutdown_ok,expected_error", [
    (True, None, True, None),
    (True, CONVERSION_ERROR, True, None),
    (False, CONVERSION_ERROR, True, "Unable to convert"),
    (True, "policy callback failed", True, "policy callback failed"),
    (False, "policy callback failed", True, "policy callback failed"),
    (True, None, False, "shutdown exceeded"),
])
def test_controller_owned_executor_only_accepts_known_closed_context_conversion(
    monkeypatch, context_closes, error, shutdown_ok, expected_error, capsys
):
    lifecycle = SimpleNamespace(context_live=True, node_live=True, executor_live=True,
                                adds=0, spins=0, shutdown_timeout=None)

    class Controller:
        context = object()

        def destroy_node(self):
            assert not lifecycle.executor_live
            lifecycle.node_live = False

    node = Controller()

    class Executor:
        def __init__(self, *, context):
            assert context is node.context

        def add_node(self, added):
            assert added is node
            lifecycle.adds += 1

        def spin_once(self, timeout_sec):
            lifecycle.spins += 1
            if context_closes:
                lifecycle.context_live = False
            if error is not None:
                raise RuntimeError(error)

        def shutdown(self, timeout_sec):
            lifecycle.shutdown_timeout = timeout_sec
            lifecycle.executor_live = False
            return shutdown_ok

    monkeypatch.setattr(control, "HeadquartersControl", lambda: node)
    monkeypatch.setattr(control, "SingleThreadedExecutor", Executor)
    monkeypatch.setattr(control.rclpy, "init", lambda **kwargs: None)
    monkeypatch.setattr(control.rclpy, "ok", lambda **kwargs: lifecycle.context_live)
    monkeypatch.setattr(
        control.rclpy, "shutdown", lambda: setattr(lifecycle, "context_live", False)
    )
    monkeypatch.setattr(control.rclpy, "spin", lambda *args: pytest.fail("must own its executor"))
    if expected_error:
        with pytest.raises(RuntimeError, match=expected_error):
            control.main()
    else:
        control.main()
    assert lifecycle.adds == 1 and lifecycle.spins == 1
    assert lifecycle.shutdown_timeout == 1.0
    assert not lifecycle.node_live and not lifecycle.executor_live and not lifecycle.context_live
    if context_closes and error == CONVERSION_ERROR:
        assert "ROS context already closed" in capsys.readouterr().err
