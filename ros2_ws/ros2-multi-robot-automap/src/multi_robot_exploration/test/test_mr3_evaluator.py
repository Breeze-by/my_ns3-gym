"""MR3 task gates and delayed start/stop message regressions."""

import json
from types import MethodType, SimpleNamespace

from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Time
import pytest
from std_msgs.msg import Header, String

from multi_robot_exploration.control import HeadquartersControl
from multi_robot_exploration.task_evaluator import (
    TaskEvaluator, mr3_participation_pass, mr3_quality_pass,
)
from test_navigation_ownership import accept_goal, make_controller


QUALITY = {
    "min_observed_accuracy": .95, "min_occupied_iou": .20, "max_false_free_ratio": .02,
}
PARTICIPATION = {"min_path_length_m": 1., "min_goal_count": 1}


def header(stamp):
    return Header(stamp=Time(sec=int(stamp), nanosec=round((stamp-int(stamp))*1e9)),
                  frame_id="map")


def eligible_evaluator():
    clock = [2.0]
    requests, finalizations = [], []
    metrics = {"correct_free_coverage_ratio": .95, "observed_accuracy": .96,
               "occupied_iou": .25, "false_free_ratio": .01}
    summary = {"fresh": True, "ever_unhealthy": False, "event_count": 0}
    node = SimpleNamespace(
        task_contract=SimpleNamespace(data={
            "quality": QUALITY, "participation": PARTICIPATION,
            "navigation_closure_timeout_sec": 10.,
        }),
        max_duration=300., coverage_threshold=.95, start_sim_time=1.,
        control_failure="", map_contract_failure="", teleport_jumps={"tb1": 0},
        path_lengths={name: 2. for name in ("tb1", "tb2", "tb3")},
        goal_ids={name: {name.encode()} for name in ("tb1", "tb2", "tb3")},
        stop_requested_sim_time=None, navigation_protocol_closed=False,
        robot_names=["tb1", "tb2", "tb3"], finalized=False,
        _now=lambda: clock[0], _map_metrics=lambda: metrics,
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            to_msg=lambda: header(clock[0]).stamp,
        )),
        task_stop_publisher=SimpleNamespace(publish=requests.append),
        finalize=finalizations.append, _timer_callback=lambda: None,
    )
    node._mr3_termination_reason = MethodType(TaskEvaluator._mr3_termination_reason, node)
    return node, clock, metrics, summary, requests, finalizations


@pytest.mark.parametrize("field,value", [
    ("observed_accuracy", .94), ("occupied_iou", .19),
    ("false_free_ratio", .021), ("observed_accuracy", float("nan")),
    ("false_free_ratio", float("inf")),
])
def test_coverage_cannot_bypass_map_quality(field, value):
    node, _, metrics, summary, requests, _ = eligible_evaluator()
    metrics[field] = value
    assert not mr3_quality_pass(metrics, QUALITY)
    assert node._mr3_termination_reason(1., summary) is None
    assert not requests


def test_all_three_robots_must_actually_participate():
    node, _, _, summary, requests, _ = eligible_evaluator()
    node.path_lengths["tb3"] = .9
    assert not mr3_participation_pass(node.path_lengths, node.goal_ids, PARTICIPATION)
    assert node._mr3_termination_reason(1., summary) is None
    assert not requests
    node.path_lengths["tb3"] = 2.
    node.goal_ids["tb3"].clear()
    assert not mr3_participation_pass(node.path_lengths, node.goal_ids, PARTICIPATION)


def test_restored_monitor_does_not_erase_an_episode_interruption():
    node, _, _, summary, requests, _ = eligible_evaluator()
    summary["ever_unhealthy"] = True
    assert node._mr3_termination_reason(1., summary) == "collision_monitoring_interrupted"
    assert not requests


def test_success_waits_for_terminal_ownership_and_respects_deadline():
    node, clock, _, summary, requests, _ = eligible_evaluator()
    assert node._mr3_termination_reason(1., summary) is None
    assert len(requests) == 1
    assert node._mr3_termination_reason(2., summary) is None
    assert len(requests) == 1
    node.navigation_protocol_closed = True
    assert node._mr3_termination_reason(2., summary) == "coverage_reached"
    clock[0] = 301.
    assert node._mr3_termination_reason(300., summary) == "timeout"


def test_task_gate_regression_while_cancelling_cannot_be_success():
    node, _, metrics, summary, _, _ = eligible_evaluator()
    node._mr3_termination_reason(1., summary)
    metrics["correct_free_coverage_ratio"] = .94
    node.navigation_protocol_closed = True
    assert node._mr3_termination_reason(2., summary) == "task_gate_regressed_during_closure"


def test_future_stop_is_buffered_and_late_acceptance_is_cancelled_before_ack():
    node, clock, _, assignment = make_controller()
    acknowledgments = []
    node.exploration_started = True
    node.exploration_start_time = .5
    node.task_stop_requested = False
    node.task_stop_acknowledged = False
    node.task_stop_publisher = SimpleNamespace(publish=acknowledgments.append)
    for name in ("_task_stop_callback", "_drain_task_stop", "_acknowledge_task_stop"):
        setattr(node, name, MethodType(getattr(HeadquartersControl, name), node))
    clock[0] = .9
    node._task_stop_callback(header(1.))
    assert not node.task_stop_requested
    clock[0] = 1.
    node._drain_task_stop()
    assert node.task_stop_requested
    assert not acknowledgments
    _, result, cancel = accept_goal(node, assignment)
    assert node.cancel_requested["tb1"]
    cancel.set_result(SimpleNamespace(goals_canceling=[]))
    assert not acknowledgments
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    assert len(acknowledgments) == 1
    assert json.loads(acknowledgments[0].data)["pending_goal_count"] == 0


def test_valid_future_terminal_ack_waits_for_local_clock_watermark():
    node, clock, _, _, _, finalizations = eligible_evaluator()
    node.stop_requested_sim_time = 2.
    message = String(data=json.dumps({
        "start_sim_time_sec": 1., "stop_sim_time_sec": 2.1, "pending_goal_count": 0,
        "robot_names": node.robot_names, "navigation_failure": False,
    }))
    TaskEvaluator._stopped_callback(node, message)
    assert not finalizations
    assert not node.navigation_protocol_closed
    assert node.pending_stop_ack is message
    clock[0] = 2.1
    TaskEvaluator._stopped_callback(node, message)
    assert node.navigation_protocol_closed
    assert not finalizations
