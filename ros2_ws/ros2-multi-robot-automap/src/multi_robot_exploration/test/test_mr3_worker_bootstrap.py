"""A visible ROS node cannot substitute for delivery before physical pause."""

import copy
import importlib.util
import io
from pathlib import Path
import sys
import threading
from unittest.mock import patch

import pytest

from multi_robot_exploration.mr3_evaluator_phase import EvaluatorPhase, PhaseClient


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("mr3_env_worker", SCRIPTS / "mr3_env_worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


def worker():
    instance = WORKER.Worker.__new__(WORKER.Worker)
    instance.epoch = "current"
    instance.monitor_ready = True
    instance.initial_inputs_ready = None
    return instance


def acknowledgement():
    return {"schema": "mr3-initial-inputs-ready-v1", "epoch": "current", "stamp": 10.,
            "state_sequence": 100, "map_payload_sha256": "a" * 64,
            "robots": [{"name": name, "source_stamp": 9.9, "received_stamp": 10.}
                       for name in ("tb1", "tb2", "tb3")]}


def test_initial_reset_does_not_pause_without_actual_delivered_input_ack():
    instance = worker()

    def wait(predicate, timeout, label):
        assert not predicate()
        raise TimeoutError(label)

    instance._wait = wait
    with patch.object(WORKER.subprocess, "Popen") as process:
        with pytest.raises(TimeoutError, match="delivered-input startup"):
            instance.reset()
        process.assert_not_called()


def test_same_epoch_ack_is_idempotent_and_does_not_release_the_task():
    instance = worker()
    value = acknowledgement()
    instance.receive_initial_inputs(value)
    instance.receive_initial_inputs(copy.deepcopy(value))
    assert instance.initial_inputs_ready == value
    assert not hasattr(instance, "start_ns")
    assert not hasattr(instance, "snapshot")


def test_previous_epoch_input_ack_cannot_unlock_reset():
    instance = worker()
    value = acknowledgement()
    value["epoch"] = "previous"
    instance.receive_initial_inputs(value)
    assert instance.initial_inputs_ready is None


@pytest.mark.parametrize("key,value", [
    ("schema", "other"), ("state_sequence", 0), ("state_sequence", True),
    ("stamp", float("nan")), ("map_payload_sha256", "a" * 63),
    ("robots", [{"name": "tb1"}]),
])
def test_invalid_delivery_ack_is_an_infrastructure_error(key, value):
    instance = worker()
    payload = acknowledgement()
    payload[key] = value
    with pytest.raises(ValueError, match="invalid initial"):
        instance.receive_initial_inputs(payload)
    assert instance.initial_inputs_ready is None


def test_future_robot_source_and_changed_same_epoch_ack_are_rejected():
    instance = worker()
    payload = acknowledgement()
    payload["robots"][0]["source_stamp"] = 10.1
    with pytest.raises(ValueError, match="source time"):
        instance.receive_initial_inputs(payload)
    instance.receive_initial_inputs(acknowledgement())
    payload = acknowledgement()
    payload["state_sequence"] += 1
    with pytest.raises(ValueError, match="changed within epoch"):
        instance.receive_initial_inputs(payload)


def test_evaluator_terminal_waits_for_both_real_physics_and_ros_clock():
    instance = worker()
    instance.task_terminal = None
    instance.physical_ns = 10000000000
    instance.clock_ns = 9980000000
    notice = {"epoch": "current", "end_sim_time_sec": 10.,
              "termination_reason": "navigation_failure"}
    instance.receive_terminal(notice)
    assert instance._evaluation() is None
    instance.clock_ns = 10000000000
    assert instance._evaluation() == notice
    for invalid in ({**notice, "end_sim_time_sec": float("nan")},
                    {**notice, "termination_reason": "training_external_truncation"},
                    {**notice, "truth": [0, 1]}):
        with pytest.raises(ValueError, match="invalid evaluator"):
            instance.receive_terminal(invalid)
    with pytest.raises(ValueError, match="boundary changed"):
        instance.receive_terminal({**notice, "end_sim_time_sec": 10.02})


def terminal_worker(end=10.):
    instance = worker()
    instance.finished = False
    instance.physical_ns = instance.clock_ns = 10000000000
    instance.task_terminal = {"epoch": "current", "end_sim_time_sec": end,
                              "termination_reason": "navigation_failure"}
    instance.snapshot = {"sequence": 4, "source_stamp": 10., "digest": "saved"}
    instance.watermarks = {"state_sequence": 100, "map_payload_sha256": "a" * 64}
    instance.transition_file = io.StringIO()
    instance.callback_error = None
    instance.evaluator_phase_file = io.StringIO()
    instance.condition = threading.Condition()
    instance.evaluator_phase = PhaseClient(instance.epoch)
    request = instance.evaluator_phase.begin(instance.physical_ns)
    ack = EvaluatorPhase(instance.epoch).request(request, instance.physical_ns, None, 0)
    instance.evaluator_phase.receive(ack, instance.physical_ns, instance.clock_ns)
    instance.evaluator_phase.consume()
    instance.shutdown_episode = lambda reason: setattr(instance, "shutdown_reason", reason)
    return instance


def test_same_boundary_terminal_settles_without_new_action_snapshot_or_physics():
    instance = terminal_worker()
    captured = instance.snapshot

    def reward(start, end, truncation=None):
        assert start == end == 10. and truncation == "external_sampler_limit"
        return {"reward": -20., "terminated": True, "truncated": False,
                "reason": "navigation_failure", "effective_step_end": 10.}

    instance._reward = reward
    with (patch.object(instance, "_physics") as physics,
          patch.object(instance, "_snapshot") as snap):
        result = instance.step(888, "external_sampler_limit")
        physics.assert_not_called()
        snap.assert_not_called()
    assert result["snapshot"] is captured
    assert result["info"]["dt"] == result["info"]["physical_dt"] == 0.
    assert result["info"]["terminal_observation_reused"] is True
    assert result["info"]["action_submitted"] is False and result["info"]["command"] is None
    assert result["terminated"] and not result["truncated"]
    assert instance.shutdown_reason == "task_terminal"


def test_terminal_before_previous_returned_boundary_is_an_explicit_error():
    instance = terminal_worker(9.98)
    with pytest.raises(RuntimeError, match="predates"):
        instance.step(888)


def test_zero_terminal_reward_cannot_move_the_already_returned_boundary():
    instance = terminal_worker()
    instance._reward = lambda *args, **kwargs: {
        "reward": -20., "terminated": True, "truncated": False,
        "effective_step_end": 10.02}
    with pytest.raises(RuntimeError, match="settled sample boundary"):
        instance.step(888)
    assert not hasattr(instance, "shutdown_reason")


def test_midstep_terminal_stops_after_one_real_quantum_and_authorizes_terminal_snapshot():
    instance = terminal_worker()
    instance.task_terminal = None
    instance.probe_armed = False
    instance.command_number = 0
    instance.events = []
    instance.action_pub = object()
    instance.evaluator_phase_pub = object()

    def publish(publisher, command):
        if publisher is instance.evaluator_phase_pub:
            ack = {"schema": "mr3-evaluator-clock-terminal-ack-v1", **command, "ok": True,
                   "evaluator_clock_ns": instance.physical_ns, "status": "TERMINAL",
                   "terminal": instance.task_terminal}
            instance.evaluator_phase.receive(ack, instance.physical_ns, instance.clock_ns)
        else:
            instance.events.append({"kind": "action", "payload": {
                "command_id": command["command_id"],
                "observation_sequence": command["observation_sequence"]}})

    instance._publish = publish

    def wait(predicate, timeout, label):
        assert predicate(), label

    instance._wait = wait
    ticks = []

    def physics(count):
        ticks.append(count)
        instance.physical_ns += count * 1000000
        instance.clock_ns = instance.physical_ns
        instance.task_terminal = {"epoch": "current", "end_sim_time_sec": 10.02,
                                  "termination_reason": "navigation_failure"}

    def snapshot(allow_terminal=False):
        assert allow_terminal
        instance.snapshot = {"sequence": 5, "source_stamp": 10.02, "digest": "actual"}

    instance._physics = physics
    instance._snapshot = snapshot
    instance._reward = lambda *args, **kwargs: {
        "reward": -20., "terminated": True, "truncated": False,
        "reason": "navigation_failure", "effective_step_end": 10.02}
    result = instance.step(888)
    assert ticks == [20]
    assert result["terminated"] and result["info"]["physical_dt"] == .02
    assert result["info"]["dt"] == .02


def test_diagnostic_failure_cannot_be_armed_or_sent_in_a_normal_environment():
    instance = terminal_worker()
    instance.terminal_probe = False
    with pytest.raises(ValueError, match="disabled"):
        instance.arm_failure_probe()
    with pytest.raises(ValueError, match="disabled"):
        instance.trigger_failure_probe()
