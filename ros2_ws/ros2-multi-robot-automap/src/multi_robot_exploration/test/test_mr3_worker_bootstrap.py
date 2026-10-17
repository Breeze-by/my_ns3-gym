"""A visible ROS node cannot substitute for delivery before physical pause."""

import copy
import importlib.util
import io
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
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


def test_native_velocity_bypass_prevents_release_and_does_not_write_a_pass(tmp_path):
    instance = worker()
    instance.directory = tmp_path
    instance.clock_ns = 10**10
    bypass = SimpleNamespace(node_namespace="/tb2", node_name="behavior_server")
    instance.node = SimpleNamespace(get_publishers_info_by_topic=lambda topic: [bypass])
    instance._wait = lambda predicate, *args: predicate()
    with pytest.raises(RuntimeError, match="unguarded velocity publisher"):
        instance.verify_motion_output_topology()
    assert not (tmp_path / "motion_topology.json").exists()


def test_missing_or_duplicate_motion_gate_is_not_native_topology_proof(tmp_path):
    instance = worker()
    instance.directory = tmp_path
    instance.clock_ns = 10**10
    gate = SimpleNamespace(node_namespace="/", node_name="motion_safety",
                           endpoint_gid=[1] * 16, topic_type="geometry_msgs/msg/Twist")
    for entries in ([], [gate, gate]):
        instance.node = SimpleNamespace(get_publishers_info_by_topic=lambda topic: entries)

        def wait(predicate, *args):
            assert not predicate()
            raise TimeoutError("discovery incomplete")

        instance._wait = wait
        with pytest.raises(TimeoutError):
            instance.verify_motion_output_topology()
    assert not (tmp_path / "motion_topology.json").exists()


def test_three_unique_native_motion_publishers_bind_actual_endpoint_ids(tmp_path):
    import json
    instance = worker()
    instance.directory = tmp_path
    instance.clock_ns = 10**10
    gate = SimpleNamespace(node_namespace="/", node_name="motion_safety",
                           endpoint_gid=[1] * 16, topic_type="geometry_msgs/msg/Twist")
    instance.node = SimpleNamespace(get_publishers_info_by_topic=lambda topic: [gate])
    instance._wait = lambda predicate, *args: predicate()
    instance.verify_motion_output_topology()
    proof = json.loads((tmp_path / "motion_topology.json").read_text())
    assert proof["epoch"] == "current" and proof["stamp"] == 10.
    assert set(proof["endpoints"]) == {f"/tb{i}/cmd_vel" for i in (1, 2, 3)}
    assert all(entries[0]["endpoint_gid"] == "01" * 16
               for entries in proof["endpoints"].values())


def test_native_costmap_archive_preserves_source_header_and_actual_receipt(tmp_path):
    import gzip
    import hashlib
    import json
    instance = worker()
    instance.directory = tmp_path
    instance.clock_ns = 10**10
    instance.execution_map_digests = set()
    instance.execution_costmap_file = io.StringIO()
    payload = {"header": {"stamp": {"sec": 9, "nanosec": 123}, "frame_id": "map"},
               "info": {"width": 2, "height": 1}, "data": [100, -1]}
    instance.map_payload = lambda message: copy.deepcopy(payload)
    instance.record_costmap("tb2", "global", object())
    instance.clock_ns += 20_000_000
    instance.record_costmap("tb2", "global", object())
    rows = [json.loads(line) for line in instance.execution_costmap_file.getvalue().splitlines()]
    assert rows[0]["source_header"] == payload["header"] == rows[1]["source_header"]
    assert [row["received_clock_ns"] for row in rows] == [10**10, 10**10 + 20_000_000]
    assert len(list((tmp_path / "execution_inputs/maps").glob("*.gz"))) == 1
    raw = gzip.decompress((tmp_path / rows[0]["artifact"]).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == rows[0]["payload_sha256"]
    assert json.loads(raw) == payload


def motion_worker():
    instance = worker()
    instance.motion_status = None
    instance.clock_ns = instance.physical_ns = 10**10
    instance.motion_phase_file = io.StringIO()
    return instance


def motion_ack(clock_ns=10**10):
    return {"schema": "mr3-motion-safety-status-v1", "epoch": "current",
            "completion_scope": "publication_and_local_topic_receipt",
            "clock_ns": clock_ns, "ready": True,
            "decision_sequences": {name: clock_ns // 20_000_000
                                   for name in ("tb1", "tb2", "tb3")}}


def test_motion_phase_waits_for_actual_exact_clock_completion():
    instance = motion_worker()
    instance.receive_motion_status(motion_ack(10**10 - 20_000_000))

    def wait(predicate, *args):
        assert not predicate()
        instance.receive_motion_status(motion_ack())
        assert predicate()

    instance._wait = wait
    instance.wait_motion_phase()
    assert '"kind": "ack_consumed"' in instance.motion_phase_file.getvalue()


def test_future_motion_phase_cannot_authorize_a_paused_quantum():
    instance = motion_worker()
    instance.receive_motion_status(motion_ack(10**10 + 1))
    instance._wait = lambda predicate, *args: predicate()
    with pytest.raises(RuntimeError, match="beyond the paused"):
        instance.wait_motion_phase()


def test_motion_phase_rejects_cross_epoch_regression_and_conflicting_same_clock():
    instance = motion_worker()
    instance.receive_motion_status({**motion_ack(), "epoch": "old"})
    assert instance.motion_status is None
    instance.receive_motion_status(motion_ack())
    instance.receive_motion_status(motion_ack())
    with pytest.raises(ValueError, match="clock regressed"):
        instance.receive_motion_status(motion_ack(10**10 - 1))
    with pytest.raises(ValueError, match="changed within one clock"):
        instance.receive_motion_status({**motion_ack(), "ready": False})
    with pytest.raises(ValueError, match="invalid motion gate"):
        instance.receive_motion_status({**motion_ack(), "decision_sequences": {"tb1": True}})


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
