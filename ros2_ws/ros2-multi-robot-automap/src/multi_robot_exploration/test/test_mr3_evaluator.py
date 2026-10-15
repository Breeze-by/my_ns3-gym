"""MR3 task gates and delayed start/stop message regressions."""

import json
from pathlib import Path
from types import MethodType, SimpleNamespace

from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Time
import pytest
from std_msgs.msg import Header, String

from multi_robot_exploration.control import HeadquartersControl
from multi_robot_exploration.mr3_contacts import CONTACT_COMPONENTS, ContactMonitor
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


def contact_evaluator():
    clock, active = [0.], [True]
    subscriptions, readiness, finalizations = [], [], []
    robots = ["tb1", "tb2", "tb3"]
    node = SimpleNamespace(
        robot_names=robots, contact_monitor=ContactMonitor(robots, [], compact=True),
        pending_contacts=[], finalized=False, start_sim_time=None, control_failure="",
        contact_subscription_started_sim_time_sec=None,
        contact_subscription_bootstrap_state="waiting_for_active_sim_clock",
        contact_clock_overflow_diagnostic=None, input_subscriptions=[],
        latest_map=object(), positions={name: (0., 0.) for name in robots},
        map_contract_failure="", task_ready_published=None,
        task_ready_publisher=SimpleNamespace(publish=lambda msg: readiness.append(msg.data)),
        _now=lambda: clock[0],
        get_clock=lambda: SimpleNamespace(ros_time_is_active=active[0]),
        create_subscription=lambda kind, topic, callback, depth: subscriptions.append(
            (topic, callback, depth)),
        finalize=finalizations.append,
    )

    def finalize(reason):
        node.finalized = True
        finalizations.append(reason)

    node.finalize = finalize
    for name in ("_mr3_timer_callback", "_mr3_contact_callback", "_drain_contacts"):
        setattr(node, name, MethodType(getattr(TaskEvaluator, name), node))
    return node, clock, active, subscriptions, readiness, finalizations


def contact_message(stamp, positive=False):
    states = [SimpleNamespace(collision1_name="tb1::base_link::base_collision",
                              collision2_name="wall::link::collision")] if positive else []
    return SimpleNamespace(header=header(stamp), states=states)


@pytest.mark.parametrize("now,active", [
    (0., True), (-1., True), (float("nan"), True), (float("inf"), True), (1., False),
])
def test_contact_subscriptions_wait_for_finite_positive_active_ros_clock(now, active):
    node, clock, clock_active, subscriptions, readiness, _ = contact_evaluator()
    clock[0], clock_active[0] = now, active
    node._mr3_timer_callback()
    assert not subscriptions
    assert not readiness
    assert node.contact_subscription_started_sim_time_sec is None
    assert node.contact_subscription_bootstrap_state == "waiting_for_active_sim_clock"


def test_contact_subscription_bootstrap_is_once_and_requires_all_sources_before_ready():
    node, clock, _, subscriptions, readiness, _ = contact_evaluator()
    clock[0] = 1.
    node._mr3_timer_callback()
    assert len(subscriptions) == 18
    assert {topic for topic, _, _ in subscriptions} == {
        f"/mr3_contacts/{robot}/{part}"
        for robot in node.robot_names for part in CONTACT_COMPONENTS
    }
    assert all(depth == 20 for _, _, depth in subscriptions)
    assert node.contact_subscription_started_sim_time_sec == 1.
    assert node.contact_subscription_bootstrap_state == "contact_subscriptions_started"
    assert not readiness
    for _, callback, _ in subscriptions[:-1]:
        callback(contact_message(1.))
    node._mr3_timer_callback()
    assert readiness == [False]
    subscriptions[-1][1](contact_message(1.))
    node._mr3_timer_callback()
    assert readiness == [False, True]
    assert len(subscriptions) == 18


def test_eligible_pending_contacts_drain_before_new_future_sample_uses_cap():
    node, clock, _, _, _, _ = contact_evaluator()
    clock[0] = 1.
    node._mr3_timer_callback()
    node.pending_contacts = [
        (.5 + index / 1000, "tb1", "base", contact_message(.5 + index / 1000))
        for index in range(256)
    ]
    future = contact_message(1.1)
    node._mr3_contact_callback(future, "tb1", "base")
    assert len(node.pending_contacts) == 1
    assert node.pending_contacts[0][3] is future
    assert node.contact_monitor.components[("tb1", "base")].accepted_message_count == 256
    assert not node.control_failure
    assert node.contact_clock_overflow_diagnostic is None


def test_pre_release_positive_contact_survives_bootstrap_and_monitor_start():
    node, clock, _, _, readiness, finalizations = contact_evaluator()
    clock[0] = 1.
    node._mr3_timer_callback()
    node._mr3_contact_callback(contact_message(1., positive=True), "tb1", "base")
    node._mr3_timer_callback()
    assert readiness == [False]
    assert finalizations == ["startup_collision"]
    node.contact_monitor.start(1.)
    assert node.contact_monitor.summary(1.)["event_count"] == 1


def test_true_future_overflow_finalizes_once_and_stops_accepting_messages():
    node, clock, _, _, _, finalizations = contact_evaluator()
    clock[0] = 1.
    node._mr3_timer_callback()
    for index in range(256):
        node._mr3_contact_callback(contact_message(2. + index / 1000), "tb1", "base")
    assert not node.control_failure
    node._mr3_contact_callback(contact_message(3.), "tb1", "base")
    assert node.control_failure == "contact_clock_desynchronization"
    assert node.finalized
    assert finalizations == ["navigation_failure"]
    diagnostic = node.contact_clock_overflow_diagnostic.copy()
    assert diagnostic == {
        "now_sim_time_sec": 1., "pending_count": 257,
        "min_source_sim_time_sec": 2., "max_source_sim_time_sec": 3.,
        "contact_subscription_bootstrap_state": "contact_subscriptions_started",
        "contact_subscription_started_sim_time_sec": 1., "start_sim_time_sec": None,
    }
    node._mr3_contact_callback(contact_message(4.), "tb1", "base")
    assert node.contact_clock_overflow_diagnostic == diagnostic
    assert len(node.pending_contacts) == 257
    assert finalizations == ["navigation_failure"]
    assert node.contact_monitor.components[("tb1", "base")].message_count == 0


@pytest.mark.parametrize("started,ready", [(None, None), (1., None), (1., False)])
def test_release_before_contact_bootstrap_and_readiness_fails_without_task_start(started, ready):
    node, clock, _, _, _, finalizations = contact_evaluator()
    clock[0] = 1.
    node.contact_subscription_started_sim_time_sec = started
    node.task_ready_published = ready
    TaskEvaluator._release_callback(node, header(1.1))
    assert finalizations == ["invalid_task_release"]
    assert node.start_sim_time is None
    assert not node.contact_monitor.started
    assert not hasattr(node, "pending_release")


def test_ready_release_still_waits_for_local_clock_without_losing_contacts():
    node, clock, _, subscriptions, readiness, finalizations = contact_evaluator()
    clock[0] = 1.
    node._mr3_timer_callback()
    for _, callback, _ in subscriptions:
        callback(contact_message(1.))
    node._mr3_timer_callback()
    assert readiness == [True]
    release = header(1.1)
    TaskEvaluator._release_callback(node, release)
    assert node.start_sim_time is None
    assert node.pending_release is release
    node._release_callback = MethodType(TaskEvaluator._release_callback, node)
    node._map_metrics = lambda: {}
    node._update_coverage_times = lambda: None
    node._timer_callback = lambda: None
    node.get_logger = lambda: SimpleNamespace(info=lambda message: None)
    node.episode_id = "release-test"
    clock[0] = 1.1
    node._mr3_timer_callback()
    assert node.start_sim_time == 1.1
    assert node.contact_monitor.started
    assert node.pending_release is None
    assert all(state.accepted_message_count == 1
               for state in node.contact_monitor.components.values())
    assert not finalizations


def terminal_evaluator_notice():
    notices = []
    node = SimpleNamespace(
        episode_id="notice-epoch", training_reward_enabled=True, finalized=True,
        start_sim_time=10., training_external_cut=None, task_terminal_notice_published=False,
        final_result={"end_sim_time_sec": 10.02, "termination_reason": "collision"},
        task_terminal_publisher=SimpleNamespace(publish=lambda message: notices.append(
            json.loads(message.data))),
    )
    node.publish_task_terminal_notice = MethodType(
        TaskEvaluator.publish_task_terminal_notice, node)
    return node, notices


@pytest.mark.parametrize("reason", (
    "collision", "collision_monitoring_interrupted", "timeout", "coverage_reached",
    "navigation_failure",
))
def test_frozen_task_terminal_notice_is_scalar_once_only_and_preserves_original_end(reason):
    node, notices = terminal_evaluator_notice()
    node.final_result["termination_reason"] = reason
    node.publish_task_terminal_notice()
    assert notices == [{"epoch": "notice-epoch", "end_sim_time_sec": 10.02,
                        "termination_reason": reason}]
    node.publish_task_terminal_notice()
    assert len(notices) == 1


@pytest.mark.parametrize("changes", (
    {"training_reward_enabled": False}, {"finalized": False}, {"start_sim_time": None},
    {"training_external_cut": 10.},
    {"final_result": {"end_sim_time_sec": 10.02,
                      "termination_reason": "training_external_truncation"}},
    {"final_result": {"end_sim_time_sec": 10.02, "termination_reason": "shutdown"}},
))
def test_external_cut_and_infrastructure_or_unstarted_state_do_not_publish_task_terminal(changes):
    node, notices = terminal_evaluator_notice()
    for name, value in changes.items():
        setattr(node, name, value)
    node.publish_task_terminal_notice()
    assert not notices and not node.task_terminal_notice_published


@pytest.mark.parametrize("probe_enabled", (False, True))
def test_real_evaluator_freezes_nanosecond_deadline_notice_before_result_file_io(
        monkeypatch, probe_enabled):
    import rclpy
    from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
    source = Path(__file__).resolve().parents[2] / "multi_robot"
    args = ["--ros-args", "-p", "training_reward_enabled:=true", "-p",
            "world_file:=" + str(source / "worlds/p1c_open.world"), "-p",
            "task_contract_path:=" + str(source / "config/mr3_p1a/open.json"), "-p",
            "training_terminal_probe:=" + str(probe_enabled).lower()]
    monkeypatch.setenv("ROS_DOMAIN_ID", "181")
    rclpy.init(args=args)
    node = None
    try:
        node = TaskEvaluator()
        assert any(subscription.topic_name == "/mr3/diagnostic_failure"
                   for subscription in node.input_subscriptions) == probe_enabled
        qos = node.task_terminal_publisher.qos_profile
        assert qos.depth == 1 and qos.durability == DurabilityPolicy.TRANSIENT_LOCAL
        assert qos.reliability == ReliabilityPolicy.RELIABLE
        events = []
        node.task_terminal_publisher = SimpleNamespace(publish=lambda message: events.append(
            ("notice", json.loads(message.data), node.final_result.copy())))
        node._write_outputs = lambda result: events.append(("file", result))
        node.start_sim_time = 212.06
        node._now = lambda: 512.06
        assert node._now() - node.start_sim_time < 300.
        node.finalize("coverage_reached")
        assert [event[0] for event in events] == ["notice", "file"]
        assert events[0][1] == {"epoch": node.episode_id, "end_sim_time_sec": 512.06,
                                "termination_reason": "timeout"}
        assert events[0][2]["termination_reason"] == "timeout"
        assert node.final_result["elapsed_sim_time_sec"] == 300.
        node.finalize("collision")
        assert len(events) == 2
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def diagnostic_probe_evaluator():
    node, clock, _, subscriptions, readiness, finalizations = contact_evaluator()
    clock[0] = 1.
    node._mr3_timer_callback()
    for _, callback, _ in subscriptions:
        callback(contact_message(1.))
    node._mr3_timer_callback()
    assert readiness == [True]
    node.start_sim_time = 1.
    node.max_duration = 300.
    node.coverage_threshold = .95
    node.teleport_jumps = {name: 0 for name in node.robot_names}
    node.task_contract = SimpleNamespace(data={
        "quality": QUALITY, "participation": PARTICIPATION,
        "navigation_closure_timeout_sec": 10.,
    })
    node._map_metrics = lambda: {"correct_free_coverage_ratio": 0.}
    node.training_reward_enabled = True
    node.training_terminal_probe = True
    node.episode_id = "probe-epoch"
    node.diagnostic_failure_request = None
    node.pending_diagnostic_failure = None
    node.training_external_cut = None
    node.training_acknowledged = False
    node.training_ack_deadline_wall = None
    node.training_ack_wall_guard_sec = 90.
    node._drain_reward_requests = lambda: None
    errors = []
    node.get_logger = lambda: SimpleNamespace(error=errors.append)
    for name in (
        "_mr3_termination_reason", "_timer_callback", "_control_failure_callback",
        "_diagnostic_failure_callback", "_poll_diagnostic_failure", "training_exit_ready",
    ):
        setattr(node, name, MethodType(getattr(TaskEvaluator, name), node))
    return node, clock, readiness, finalizations, errors


def diagnostic_failure(node, **changes):
    request = {"epoch": node.episode_id, "request_id": "p1c-terminal-probe",
               "target_time_ns": 1020000000, "reason": "P1C_DIAGNOSTIC_FAILURE"}
    request.update(changes)
    node._diagnostic_failure_callback(String(data=json.dumps(request)))
    return request


def test_explicit_diagnostic_failure_waits_for_real_clock_and_changes_no_contact_samples():
    node, clock, readiness, finalizations, errors = diagnostic_probe_evaluator()
    counts = {key: value.accepted_message_count
              for key, value in node.contact_monitor.components.items()}
    request = diagnostic_failure(node)
    assert node.pending_diagnostic_failure == request and not node.control_failure
    assert not finalizations and readiness == [True]
    node.training_exit_ready()
    assert clock[0] == 1. and not finalizations
    clock[0] = 1.02
    node.training_exit_ready()
    assert clock[0] == 1.02 and readiness == [True, False]
    assert finalizations == ["navigation_failure"]
    assert node.control_failure == "P1C_DIAGNOSTIC_FAILURE"
    assert node.pending_diagnostic_failure is None and not errors
    assert counts == {key: value.accepted_message_count
                      for key, value in node.contact_monitor.components.items()}
    diagnostic_failure(node)
    assert finalizations == ["navigation_failure"]


@pytest.mark.parametrize("changes", (
    {"epoch": "other-epoch"}, {"target_time_ns": 999000000},
    {"target_time_ns": True}, {"reason": "collision"}, {"request_id": ""}, {"grid": [0]},
))
def test_diagnostic_failure_rejects_wrong_epoch_past_target_and_nonfixed_request(changes):
    node, clock, readiness, finalizations, errors = diagnostic_probe_evaluator()
    diagnostic_failure(node, **changes)
    assert errors and node.pending_diagnostic_failure is None
    assert not finalizations and not node.control_failure and readiness == [True]
    assert clock[0] == 1.


def test_disabled_diagnostic_failure_cannot_create_a_task_terminal_or_pending_request():
    node, clock, readiness, finalizations, errors = diagnostic_probe_evaluator()
    node.training_terminal_probe = False
    diagnostic_failure(node, target_time_ns=1000000000)
    assert node.diagnostic_failure_request is None and node.pending_diagnostic_failure is None
    assert not finalizations and not node.control_failure and not errors
    assert readiness == [True] and clock[0] == 1.


def test_diagnostic_failure_does_not_apply_after_overshooting_its_real_clock_target():
    node, clock, readiness, finalizations, errors = diagnostic_probe_evaluator()
    diagnostic_failure(node)
    clock[0] = 1.04
    node.training_exit_ready()
    assert errors and not finalizations and not node.control_failure
    assert node.pending_diagnostic_failure is None and readiness == [True]
    assert clock[0] == 1.04
