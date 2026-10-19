"""Deterministic evaluator clock ACK regressions; no ROS node or physical launch."""

import copy
from contextlib import contextmanager
import io
import json
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import pytest
from std_msgs.msg import String

from multi_robot_exploration.mr3_evaluator_phase import (
    EvaluatorPhase, PHASE_PROTOCOL, PHASE_WALL_GUARD_SEC, PhaseClient, QUANTUM_NS,
)
from multi_robot_exploration.task_evaluator import TaskEvaluator
from test_mr3_worker_bootstrap import WORKER, terminal_worker


START = 10_000_000_000


def terminal(end_ns=START):
    return {"epoch": "current", "end_sim_time_sec": end_ns / 1e9,
            "termination_reason": "navigation_failure"}


def exchange(client, evaluator, target=START, notice=None, wall_ns=0):
    request = client.begin(target)
    ack = evaluator.request(request, target, notice, wall_ns)
    client.receive(ack, target, target)
    return client.consume()


def test_pending_old_clock_never_acknowledges_future_target_or_allows_advance():
    evaluator, client = EvaluatorPhase("current"), PhaseClient("current")
    request = client.begin(START)
    assert evaluator.request(request, START - QUANTUM_NS, None, 0) is None
    assert evaluator.poll(START - 1, None, 1) is None
    with pytest.raises(ValueError, match="requires_consumed"):
        client.before_advance(START)
    with pytest.raises(ValueError, match="not_received"):
        client.consume()
    ack = evaluator.poll(START, None, 2)
    client.receive(ack, START, START)
    with pytest.raises(ValueError, match="requires_consumed"):
        client.before_advance(START)  # Reception alone does not grant an advance.
    client.consume()
    client.before_advance(START)


def test_late_finalize_after_live_ack_arrives_directly_without_dds_terminal_notice():
    evaluator, client = EvaluatorPhase("current"), PhaseClient("current")
    assert exchange(client, evaluator)["status"] == "LIVE"
    client.before_advance(START)
    # finalize_at(T) runs after LIVE ACK(T), while /task_terminal delivery is delayed.
    response = exchange(client, evaluator, START + QUANTUM_NS, terminal(START), wall_ns=1)
    assert response["status"] == "TERMINAL" and client.terminal == terminal(START)
    assert response["target_time_ns"] - round(client.terminal["end_sim_time_sec"] * 1e9) == (
        20_000_000)
    with pytest.raises(ValueError, match="requires_consumed"):
        client.before_advance(START + QUANTUM_NS)
    with pytest.raises(ValueError, match="not_ready"):
        client.begin(START + 2 * QUANTUM_NS)


def test_terminal_before_previous_ack_is_rejected_without_clamping():
    evaluator, client = EvaluatorPhase("current"), PhaseClient("current")
    exchange(client, evaluator)
    request = client.begin(START + QUANTUM_NS)
    with pytest.raises(ValueError, match="predates_previous_ack"):
        evaluator.request(request, START + QUANTUM_NS, terminal(START - 1), 1)
    assert client.last_target_ns == evaluator.last_target_ns == START
    assert client.response is None


@pytest.mark.parametrize("clock_ns,error", [
    (START + 1, "ahead_of_target"), (START - 1, "clock_regressed"),
])
def test_evaluator_clock_future_or_regression_is_an_error(clock_ns, error):
    evaluator = EvaluatorPhase("current")
    request = {"epoch": "current", "request_id": "one", "target_time_ns": START}
    if clock_ns < START:
        evaluator.request(request, START, None, 0)
        request = {**request, "request_id": "two", "target_time_ns": START + QUANTUM_NS}
    with pytest.raises(ValueError, match=error):
        evaluator.request(request, clock_ns, None, 1)


@pytest.mark.parametrize("mutation,error", [
    ({"epoch": "previous"}, "wrong_phase_epoch"),
    ({"request_id": ""}, "invalid_phase_request_id"),
    ({"target_time_ns": True}, "invalid_phase_nanoseconds"),
    ({"target_time_ns": -1}, "invalid_phase_nanoseconds"),
    ({"truth": [1]}, "invalid_phase_request_fields"),
])
def test_malformed_epoch_id_target_and_extra_fields_cannot_queue(mutation, error):
    evaluator = EvaluatorPhase("current")
    request = {"epoch": "current", "request_id": "one", "target_time_ns": START}
    with pytest.raises(ValueError, match=error):
        evaluator.request({**request, **mutation}, START, None, 0)
    assert evaluator.pending is None


def test_exact_duplicate_is_immutable_and_cannot_grant_another_quantum():
    evaluator, client = EvaluatorPhase("current"), PhaseClient("current")
    request = client.begin(START)
    ack = evaluator.request(request, START, None, 0)
    client.receive(ack, START, START)
    client.consume()
    replay = evaluator.request(copy.deepcopy(request), START, None, 1)
    assert replay == ack
    replay["terminal"] = terminal()
    assert evaluator.request(request, START, None, 2) == ack
    assert client.receive(ack, START + QUANTUM_NS, START + QUANTUM_NS) is False
    with pytest.raises(ValueError, match="not_received"):
        client.consume()
    with pytest.raises(ValueError, match="requires_consumed"):
        client.before_advance(START + QUANTUM_NS)
    with pytest.raises(ValueError, match="request_id_conflict"):
        evaluator.request({**request, "target_time_ns": START + QUANTUM_NS}, START, None, 3)
    with pytest.raises(ValueError, match="duplicate_conflict"):
        client.receive({**ack, "status": "TERMINAL"}, START, START)


def test_pending_duplicate_does_not_extend_wall_timeout():
    evaluator = EvaluatorPhase("current")
    request = {"epoch": "current", "request_id": "one", "target_time_ns": START}
    evaluator.request(request, START - 1, None, 0)
    evaluator.request(request, START - 1, None, 9_000_000_000)
    with pytest.raises(TimeoutError, match="wall_timeout"):
        evaluator.poll(START, None, round(PHASE_WALL_GUARD_SEC * 1e9))
    assert evaluator.last_target_ns is None


@pytest.mark.parametrize("mutation", [
    {"epoch": "old"}, {"request_id": "unbound"}, {"target_time_ns": START + 1},
    {"target_time_ns": True}, {"evaluator_clock_ns": START - 1},
    {"evaluator_clock_ns": START + 1}, {"status": "TERMINAL"}, {"metrics": {"truth": 1}},
    {"ok": False, "error": "clock_future"},
])
def test_client_rejects_misbound_ack_without_advance_permission(mutation):
    evaluator, client = EvaluatorPhase("current"), PhaseClient("current")
    request = client.begin(START)
    ack = evaluator.request(request, START, None, 0)
    with pytest.raises(ValueError):
        client.receive({**ack, **mutation}, START, START)
    assert client.response is None and client.last_target_ns is None
    with pytest.raises(ValueError, match="requires_consumed"):
        client.before_advance(START)


@pytest.mark.parametrize("physical,clock", [(START - 1, START), (START, START + 1)])
def test_worker_real_clock_and_physics_must_both_match(physical, clock):
    evaluator, client = EvaluatorPhase("current"), PhaseClient("current")
    request = client.begin(START)
    with pytest.raises(ValueError, match="clock_or_target_mismatch"):
        client.receive(evaluator.request(request, START, None, 0), physical, clock)


def evaluator_node(clock_ns=START):
    clock, responses = [clock_ns], []
    node = SimpleNamespace(
        episode_id="current", finalized=False, final_result=None, start_sim_time=10.,
        reward_reset_bound=True, evaluator_phase=EvaluatorPhase("current"),
        evaluator_phase_error=None, evaluator_phase_file=io.StringIO(),
        evaluator_phase_publisher=SimpleNamespace(publish=responses.append),
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=clock[0])),
    )
    for name in ("_trace_evaluator_phase", "_evaluator_phase_terminal", "_publish_evaluator_phase",
                 "_reject_evaluator_phase", "_evaluator_phase_callback", "_drain_evaluator_phase"):
        setattr(node, name, MethodType(getattr(TaskEvaluator, name), node))
    return node, clock, responses


@pytest.mark.parametrize("state", ["unreleased", "unbound", "partial_finalize"])
def test_evaluator_initialization_or_partial_finalization_never_falls_back_live(state):
    node, _, responses = evaluator_node()
    if state == "unreleased":
        node.start_sim_time = None
    elif state == "unbound":
        node.reward_reset_bound = False
    else:
        node.finalized = True  # final_result is deliberately not built yet.
    node._evaluator_phase_callback(String(data=json.dumps({
        "epoch": "current", "request_id": "one", "target_time_ns": START})))
    response = json.loads(responses[-1].data)
    assert response["ok"] is False and "terminal" not in response
    assert node.evaluator_phase.last_target_ns is None


def test_evaluator_pending_clock_drains_without_timer_gates_or_truth_fields():
    node, clock, responses = evaluator_node(START - 1)
    node._timer_callback = lambda: pytest.fail("phase ACK must not change task-gate cadence")
    node._evaluator_phase_callback(String(data=json.dumps({
        "epoch": "current", "request_id": "one", "target_time_ns": START})))
    assert not responses
    clock[0] = START
    node.finalized, node.final_result = True, {
        **terminal(), "end_sim_time_sec": 10., "termination_reason": "navigation_failure",
        "truth_mask": [1], "reward": 200, "metrics": {"coverage": 1.},
    }
    node._drain_evaluator_phase()
    response = json.loads(responses[-1].data)
    assert response["terminal"] == terminal()
    assert response["status"] == "TERMINAL" and response["evaluator_clock_ns"] == START
    assert set(response) == {"schema", "epoch", "request_id", "target_time_ns", "ok",
                             "evaluator_clock_ns", "status", "terminal"}
    events = [json.loads(line) for line in node.evaluator_phase_file.getvalue().splitlines()]
    assert [row["kind"] for row in events] == ["request_received", "ack_published"]
    assert all(type(row["wall_monotonic_ns"]) is int for row in events)


def phase_worker():
    instance = terminal_worker()
    # This legacy fixture bypasses Worker.__init__.
    instance.safety_contract = "legacy"
    instance.control_version = 1
    instance.bootstrap_intent_refs = None
    instance.task_terminal = None
    instance.evaluator_phase_pub = object()
    instance.evaluator_phase = PhaseClient("current")
    return instance


def test_worker_ack_supplies_delayed_terminal_notice_and_is_consumed_once():
    instance, evaluator = phase_worker(), EvaluatorPhase("current")

    def publish(_, request):
        ack = evaluator.request(request, START, terminal(), 0)
        instance.evaluator_phase.receive(ack, START, START)

    instance._publish = publish
    instance._wait = lambda predicate, *_: predicate() or pytest.fail("missing synchronous ACK")
    instance._evaluator_phase()
    assert instance._evaluation() == terminal()
    with pytest.raises(ValueError, match="not_received"):
        instance.evaluator_phase.consume()
    events = [json.loads(line) for line in instance.evaluator_phase_file.getvalue().splitlines()]
    assert [row["kind"] for row in events] == ["request", "ack_consumed"]
    assert all(row["worker_clock_ns"] == row["worker_physical_ns"] == START for row in events)


def test_worker_timeout_cannot_advance_another_policy_quantum():
    instance = phase_worker()
    instance._publish = lambda *_: None

    def wait(predicate, timeout, label):
        assert not predicate() and timeout == PHASE_WALL_GUARD_SEC
        raise TimeoutError(label)

    instance._wait = wait
    with patch.object(instance, "_physics") as physics:
        with pytest.raises(TimeoutError, match="phase ACK wall guard"):
            instance._evaluator_phase()
        with pytest.raises(ValueError, match="requires_consumed"):
            instance.evaluator_phase.before_advance(START)
        physics.assert_not_called()


@pytest.mark.parametrize("terminal_at_reset", [False, True])
def test_initial_phase_follows_reward_binding_and_terminal_cannot_return_live_reset(
        tmp_path, terminal_at_reset):
    instance, evaluator = phase_worker(), EvaluatorPhase("current")
    instance.directory, instance.outputs, instance.scene, instance.seed = tmp_path, [], "open", 101
    instance.started_wall = WORKER.time.monotonic()
    instance.initial_inputs_ready = {"stamp": 10., "state_sequence": 100}
    instance.motion_ready = True
    instance.odometry_recorder_ready = True
    instance.verify_motion_output_topology = lambda: None
    instance.verify_drive_topology = lambda: None
    instance.stopping = False
    instance.controlled = False
    instance.stop_status = instance.motion_status = None
    release = START + QUANTUM_NS
    instance.reward_ready = {"start_sim_time": release / 1e9}
    order = []
    instance._start_step_helper = lambda: order.append("helper_ready")
    instance._align_initial_clock = lambda: order.append("warmup_aligned")
    instance._snapshot = lambda: order.append("initial_snapshot")
    instance._wait = lambda predicate, *_: predicate() or pytest.fail("initial readiness missing")

    def motion_status(clock, ready, sequence):
        return {"schema": "mr3-motion-safety-status-v1", "epoch": "current", "clock_ns": clock,
                "ready": ready, "completion_scope": "publication_and_local_topic_receipt",
                "decision_sequences": {name: sequence for name in ("tb1", "tb2", "tb3")},
                "outputs": {name: {"linear_x": 0., "angular_z": 0.}
                            for name in ("tb1", "tb2", "tb3")}}

    def control(component, operation, request_id=None, **references):
        order.append(component + "_" + operation)
        if operation == "takeover":
            assert instance.physical_ns == START and request_id == f"takeover{START}"
            return ({"request_id": request_id, "status": motion_status(START, False, 1)}
                    if component == "motion" else {"request_id": request_id})
        assert operation == "commit" and instance.physical_ns == release
        assert request_id == f"boundary{release}"
        return ({"request_id": request_id, "status": motion_status(release, True, 2)}
                if component == "motion" else {"state_sequence": 100})

    instance._control_rpc = control
    instance.receive_motion_status = lambda value: setattr(instance, "motion_status", value)
    instance.wait_motion_phase = lambda: instance.motion_status

    def stored(value):
        order.append("actual_zero_storage" if value["clock_ns"] == START else "new_storage")
        assert all(item == {"linear_x": 0., "angular_z": 0.}
                   for item in value["outputs"].values())
        return {}

    instance.wait_drive_phase = stored

    def physics(steps, wait_clock=True):
        if steps == 0:
            assert wait_clock is False
            order.append("pause0")
            return {"end_time_ns": START}
        assert steps == 20 and wait_clock and instance.bootstrap_pending
        assert set(instance.takeover_acks) == {"state", "peer", "motion"}
        order.append("bootstrap_zero20")
        instance.bootstrap_pending = False
        instance.clock_ns = instance.physical_ns = release
        instance._commit_boundary()
        return {"end_time_ns": release}

    instance._physics = physics

    def reward(start, end, initialize=False):
        assert initialize and start == end == release / 1e9
        order.append("bound_reward_sequence0")
        return {"reward": 0., "terminated": False, "truncated": False}

    def publish(_, request):
        assert order[-1] == "bound_reward_sequence0"
        order.append("initial_phase_request")
        ack = evaluator.request(request, release,
                                terminal(release) if terminal_at_reset else None, 0)
        instance.evaluator_phase.receive(ack, release, release)

    instance._reward, instance._publish = reward, publish
    if terminal_at_reset:
        with pytest.raises(RuntimeError, match="initial evaluator phase is already"):
            instance.reset()
        assert instance.transition_file.getvalue() == ""
    else:
        result = instance.reset()
        assert result["terminated"] is False and result["info"]["release_time_ns"] == release
        assert result["info"]["initial_pause_time_ns"] == START
    assert order == ["helper_ready", "pause0", "warmup_aligned", "motion_takeover",
                     "state_takeover", "peer_takeover", "actual_zero_storage",
                     "bootstrap_zero20", "state_commit", "peer_commit", "motion_commit",
                     "new_storage", "new_storage", "initial_snapshot",
                     "bound_reward_sequence0", "initial_phase_request"]


def test_actual_step_missing_ack_stops_after_one_quantum_before_snapshot_or_reward():
    instance, evaluator = phase_worker(), EvaluatorPhase("current")
    exchange(instance.evaluator_phase, evaluator)
    instance.finished, instance.probe_armed = False, False
    instance.command_number, instance.events = 0, []
    instance.action_pub = object()
    ticks = []

    def publish(publisher, payload):
        if publisher is instance.action_pub:
            instance.events.append({"kind": "action", "payload": payload})

    def physics(count):
        ticks.append(count)
        instance.physical_ns = instance.clock_ns = START + QUANTUM_NS

    def wait(predicate, timeout, label):
        if not predicate():
            raise TimeoutError(label)

    instance._publish, instance._physics, instance._wait = publish, physics, wait
    with (patch.object(instance, "_snapshot") as snapshot,
          patch.object(instance, "_reward") as reward):
        with pytest.raises(TimeoutError, match="phase ACK wall guard"):
            instance.step(888)
        snapshot.assert_not_called()
        reward.assert_not_called()
    assert ticks == [20] and instance.evaluator_phase.pending is not None


def test_callback_failure_after_ack_reception_prevents_consumption():
    instance, evaluator = phase_worker(), EvaluatorPhase("current")

    def publish(_, request):
        instance.evaluator_phase.receive(evaluator.request(request, START, None, 0), START, START)
        instance.callback_error = "conflicting duplicate ACK"

    instance._publish = publish
    instance._wait = lambda predicate, *_: predicate() or pytest.fail("missing synchronous ACK")
    with pytest.raises(RuntimeError, match="conflicting duplicate ACK"):
        instance._evaluator_phase()
    assert instance.evaluator_phase.last_target_ns is None


def test_callback_error_latched_during_consume_lock_acquisition_cannot_slip_through():
    instance, evaluator = phase_worker(), EvaluatorPhase("current")

    def publish(_, request):
        instance.evaluator_phase.receive(evaluator.request(request, START, None, 0), START, START)

    original_condition = instance.condition

    @contextmanager
    def contended_consume_lock():
        with original_condition:
            instance.callback_error = "duplicate conflict before consume-lock acquisition"
            yield

    def wait(predicate, *_):
        assert predicate() and instance.callback_error is None
        instance.condition = contended_consume_lock()

    instance._publish, instance._wait = publish, wait
    with pytest.raises(RuntimeError, match="duplicate conflict before consume-lock"):
        instance._evaluator_phase()
    assert instance.evaluator_phase.last_target_ns is None
    assert instance.evaluator_phase.pending is not None


def test_worker_step_stops_on_ack_terminal_with_task_terminal_topic_undelivered():
    instance, evaluator = phase_worker(), EvaluatorPhase("current")
    exchange(instance.evaluator_phase, evaluator)
    instance.finished, instance.probe_armed = False, False
    instance.command_number, instance.events = 0, []
    instance.action_pub = object()
    ticks = []

    def publish(publisher, payload):
        if publisher is instance.action_pub:
            instance.events.append({"kind": "action", "payload": payload})
        else:
            ack = evaluator.request(payload, instance.physical_ns, terminal(START), 1)
            instance.evaluator_phase.receive(ack, instance.physical_ns, instance.clock_ns)

    def physics(count):
        ticks.append(count)
        instance.physical_ns = instance.clock_ns = START + QUANTUM_NS
        assert instance.task_terminal is None  # Separate DDS notice is still undelivered.

    instance._publish, instance._physics = publish, physics
    instance._wait = lambda predicate, *_: predicate() or pytest.fail("missing synchronous ACK")
    instance._snapshot = lambda allow_terminal=False: allow_terminal or pytest.fail("permission")
    instance._reward = lambda *_args, **_kwargs: {
        "reward": -20., "terminated": True, "truncated": False,
        "effective_step_end": 10., "reason": "navigation_failure"}
    result = instance.step(888)
    assert ticks == [20] and result["info"]["dt"] == 0.
    assert result["info"]["physical_dt"] == .02 and result["terminated"]


def test_worker_probe_still_runs_after_physics_before_phase_ack():
    instance, evaluator = phase_worker(), EvaluatorPhase("current")
    exchange(instance.evaluator_phase, evaluator)
    instance.finished, instance.probe_armed = False, True
    instance.command_number, instance.events = 0, []
    instance.action_pub = object()
    order = []

    def publish(publisher, payload):
        if publisher is instance.action_pub:
            instance.events.append({"kind": "action", "payload": payload})
        else:
            order.append("ACK")
            assert order == ["physics", "probe", "ACK"]
            ack = evaluator.request(payload, instance.physical_ns, instance.task_terminal, 1)
            instance.evaluator_phase.receive(ack, instance.physical_ns, instance.clock_ns)

    def physics(_):
        order.append("physics")
        instance.physical_ns = instance.clock_ns = START + QUANTUM_NS

    def probe():
        order.append("probe")
        instance.receive_terminal(terminal(START + QUANTUM_NS))

    instance._publish, instance._physics, instance.trigger_failure_probe = publish, physics, probe
    instance._wait = lambda predicate, *_: predicate() or pytest.fail("missing synchronous ACK")
    instance._snapshot = lambda allow_terminal=False: allow_terminal
    instance._reward = lambda *_args, **_kwargs: {
        "reward": -20., "terminated": True, "truncated": False,
        "effective_step_end": 10.02, "reason": "navigation_failure"}
    instance.step(888)
    assert order == ["physics", "probe", "ACK"]


def test_partial_evaluator_without_phase_initialization_has_no_poll_side_effect():
    TaskEvaluator._drain_evaluator_phase(SimpleNamespace())


def test_ack_schema_is_versioned():
    assert PHASE_PROTOCOL == "mr3-evaluator-clock-terminal-ack-v1"
    assert WORKER.PHASE_PROTOCOL == PHASE_PROTOCOL
