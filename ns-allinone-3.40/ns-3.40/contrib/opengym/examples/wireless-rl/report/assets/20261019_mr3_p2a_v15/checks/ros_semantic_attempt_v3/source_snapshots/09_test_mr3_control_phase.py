"""Paused phase identity, causal receipts and permanent zero-only interruption."""

import copy
import importlib.util
import io
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from multi_robot_exploration.mr3_control_phase import ControlPhaseClient, valid_motion_status, canonical
from multi_robot_exploration.mr3_drive_phase import DrivePhaseClient
from multi_robot_exploration.mr3_safety_intent import payload_sha256


def status(clock=20, stop=False, sequence=1):
    result = {"schema": "mr3-motion-safety-status-v1", "epoch": "epoch", "clock_ns": clock,
              "ready": not stop, "completion_scope": "publication_and_local_topic_receipt",
              "decision_sequences": {name: sequence for name in ("tb1", "tb2", "tb3")},
              "outputs": {name: {"linear_x": 0., "angular_z": 0.}
                          for name in ("tb1", "tb2", "tb3")}}
    if stop:
        result["phase_kind"] = "stop"
    return result


def ack(request, **fields):
    return {**{key: copy.deepcopy(request[key]) for key in
               ("epoch", "request_id", "target_time_ns", "operation")},
            "schema": request["schema"].replace("request", "ack"),
            "clock_ns": request["target_time_ns"], "ok": True, **fields}


def test_three_stage_chain_shares_identity_and_freezes_receipts():
    client = ControlPhaseClient("epoch")
    state_request = client.begin("state", "commit", 20, request_id="boundary20")
    state = ack(state_request, state_sequence=1, bundle_sha256="a" * 64)
    client.receive("state", state, 20, 20)
    stored = client.consume()
    state["state_sequence"] = 7
    assert stored["state_sequence"] == 1
    peer_request = client.begin("peer", "commit", 20, request_id="boundary20", state_commit=stored)
    peer = ack(peer_request, state_commit=stored)
    client.receive("peer", peer, 20, 20)
    client.consume()
    request = client.begin("motion", "commit", 20, request_id="boundary20",
                           state_commit=stored, peer_commit=peer)
    response = ack(request, status=status())
    client.receive("motion", response, 20, 20)
    assert client.consume() == response
    assert client.receive("motion", copy.deepcopy(response), 20, 20) is False
    response["status"]["ready"] = False
    with pytest.raises(ValueError, match="completed execution receipt changed"):
        client.receive("motion", response, 20, 20)


@pytest.mark.parametrize("field,value", [("clock_ns", True), ("clock_ns", 21),
                                         ("target_time_ns", False), ("ok", 1),
                                         ("request_id", "other"), ("operation", "takeover")])
def test_typed_clock_and_request_identity_cannot_be_forged(field, value):
    client = ControlPhaseClient("epoch")
    request = client.begin("motion", "commit", 20)
    response = ack(request, status=status())
    response[field] = value
    with pytest.raises(ValueError):
        client.receive("motion", response, 20, 20)


@pytest.mark.parametrize("physical,clock", [(19, 20), (20, 21), (None, 20)])
def test_receipt_requires_both_real_paused_clocks(physical, clock):
    client = ControlPhaseClient("epoch")
    request = client.begin("state", "takeover", 20)
    with pytest.raises(ValueError, match="clock/identity"):
        client.receive("state", ack(request), physical, clock)


def test_error_ack_is_preserved_and_does_not_grant_a_boundary():
    client = ControlPhaseClient("epoch")
    request = client.begin("state", "commit", 20)
    client.receive("state", ack(request, ok=False, error="fresh TF unavailable"), 20, 20)
    with pytest.raises(RuntimeError, match="fresh TF unavailable"):
        client.consume()
    assert client.pending is None


def test_permanent_stop_can_abandon_inflight_but_never_resume():
    client = ControlPhaseClient("epoch")
    old = client.begin("state", "commit", 20)
    client.abandon_for_stop()
    assert client.receive("state", ack(old), 20, 20) is False
    request = client.begin("motion", "stop", 20, reason="failure")
    client.receive("motion", ack(request, status=status(stop=True)), 20, 20)
    assert client.consume()["status"]["outputs"]["tb1"]["linear_x"] == 0.
    with pytest.raises(ValueError, match="cannot resume"):
        client.begin("state", "commit", 40)


@pytest.mark.parametrize("mutation", ["nonzero", "ready", "missing_kind", "bool_sequence"])
def test_stop_is_typed_and_zero_only(mutation):
    value = status(stop=True)
    if mutation == "nonzero":
        value["outputs"]["tb2"]["angular_z"] = .01
    elif mutation == "ready":
        value["ready"] = True
    elif mutation == "missing_kind":
        del value["phase_kind"]
    else:
        value["decision_sequences"]["tb2"] = True
    assert not valid_motion_status(value, "epoch", 20, stop=True)


def test_commit_can_report_an_actual_preempting_permanent_stop():
    client = ControlPhaseClient("epoch")
    request = client.begin("motion", "commit", 20)
    client.receive("motion", ack(request, status=status(stop=True)), 20, 20)
    assert client.consume()["status"]["phase_kind"] == "stop"
    with pytest.raises(ValueError, match="cannot resume"):
        client.begin("motion", "commit", 40)


def test_peer_cannot_substitute_a_numerically_equal_boolean_watermark():
    client = ControlPhaseClient("epoch")
    state = {"state_sequence": 1, "bundle_sha256": "a" * 64}
    request = client.begin("peer", "commit", 20, state_commit=state)
    with pytest.raises(ValueError):
        client.receive("peer", ack(request, state_commit={**state, "state_sequence": True}),
                       20, 20)


def load_worker():
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("control_worker", scripts / "mr3_env_worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_commit_order_waits_actual_storage_before_returning():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.stopping = False
    worker.physical_ns = 20
    calls = []
    state = {"state_sequence": 1, "bundle_sha256": "a" * 64}
    peer = {"state_commit": state}

    def rpc(component, operation, **references):
        calls.append(component)
        assert references["request_id"] == "boundary20"
        if component == "state":
            return state
        if component == "peer":
            assert references["state_commit"] is state
            return peer
        assert references["state_commit"] is state and references["peer_commit"] is peer
        return {"status": status(), "request_id": "boundary20"}

    worker._control_rpc = rpc
    worker.receive_motion_status = lambda value: setattr(worker, "motion_status", value)
    worker.wait_motion_phase = lambda: calls.append("local_output_receipts")
    worker.wait_drive_phase = lambda value: calls.append("actual_driver_storage")
    assert worker._commit_boundary() == status()
    assert calls == ["state", "peer", "motion", "local_output_receipts", "actual_driver_storage"]


def test_worker_stop_notification_preserves_immutable_normal_status():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch = "epoch"
    worker.motion_status = status()
    worker.stop_status = None
    worker.stopping = False
    worker._trace_control_phase = lambda *args, **kwargs: None
    before = copy.deepcopy(worker.motion_status)
    worker.receive_stop_status(status(stop=True, sequence=2))
    assert worker.stopping and worker.motion_status == before
    assert worker.stop_status["decision_sequences"]["tb1"] == 2
    with pytest.raises(ValueError, match="regressed|supersede"):
        worker.receive_stop_status(status(stop=True, sequence=1))


def test_worker_stop_interrupts_pending_phase_without_advancing_physics():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch = "epoch"
    worker.clock_ns = worker.physical_ns = 20
    worker.control_phase = ControlPhaseClient(worker.epoch)
    worker.control_publishers = {"state": object()}
    worker.condition = threading.Condition()
    worker.stopping = False
    worker.control_phase_file = io.StringIO()

    def publish(*args):
        worker.stopping = True

    worker._publish = publish
    worker._wait = lambda predicate, *args: pytest.fail("no stop") if not predicate() else None
    assert worker._control_rpc("state", "commit") is None
    assert worker.control_phase.stopped


def driver_ack(name, motion):
    return {"schema": "mr3-drive-target-consumed-v1", "epoch": "epoch", "robot": name,
            "clock_ns": motion["clock_ns"], "source_clock_ns": motion["clock_ns"],
            "decision_sequence": motion["decision_sequences"][name],
            "cmd_seq": motion["decision_sequences"][name], **motion["outputs"][name]}


def test_real_physics_request_follows_old_storage_and_new_commit_follows_arrival():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch = "epoch"
    worker.clock_ns = worker.physical_ns = 20_000_000
    worker.controlled = True
    worker.execution_request_id = "boundary20000000"
    worker.stopping = worker.cleanup_mode = False
    worker.callback_error = None
    worker.stop_status = None
    worker.motion_status = status(clock=20_000_000)
    worker.drive_phase = DrivePhaseClient("epoch")
    worker.consumed_drive_phase = None
    for name in ("tb1", "tb2", "tb3"):
        worker.drive_phase.receive(driver_ack(name, worker.motion_status))
    worker.condition = threading.Condition()
    worker.physics_number = 0
    worker.physics_file = io.StringIO()
    events = []
    worker._trace_drive_phase = lambda kind, **fields: events.append(kind)
    receipt = {"epoch": "epoch", "request_id": "q1", "ok": True, "paused": True,
               "start_iterations": 20, "end_iterations": 40, "start_time_ns": 20_000_000,
               "end_time_ns": 40_000_000}
    worker.helper_peer = SimpleNamespace(
        send=lambda value: events.append("actual_physics_send"), receive=lambda timeout: receipt)

    def wait(predicate, *args):
        if not predicate():
            worker.clock_ns = receipt["end_time_ns"]
            events.append("actual_clock_arrived")
        assert predicate()

    worker._wait = wait

    def commit():
        assert worker.clock_ns == worker.physical_ns == 40_000_000
        events.append("new_clock_commit")

    worker._commit_boundary = commit
    worker._physics(20)
    assert events == ["ack_consumed", "advance_permitted", "actual_physics_send",
                      "physics_completed", "actual_clock_arrived", "new_clock_commit"]


def test_late_permanent_stop_preempts_normal_storage_wait_with_exact_stop_receipts():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch = "epoch"
    worker.clock_ns = worker.physical_ns = 20
    worker.motion_status = status()
    worker.stop_status = None
    worker.stopping = worker.cleanup_mode = False
    worker.callback_error = None
    worker.drive_phase = DrivePhaseClient("epoch")
    worker.consumed_drive_phase = None
    worker.condition = threading.Condition()
    worker.control_phase = ControlPhaseClient("epoch")
    worker._trace_control_phase = lambda *args, **kwargs: None
    worker._trace_drive_phase = lambda *args, **kwargs: None
    stopped = status(stop=True, sequence=2)

    def wait(predicate, *args):
        if not predicate():
            worker.receive_stop_status(stopped)
            for name in ("tb1", "tb2", "tb3"):
                worker.drive_phase.receive(driver_ack(name, stopped))
        assert predicate()

    worker._wait = wait
    worker._control_rpc = lambda *args, **kwargs: {
        "clock_ns": 20, "status": stopped, "request_id": "stop20"}
    result = worker.wait_drive_phase(worker.motion_status)
    assert all(row["decision_sequence"] == 2 for row in result.values())
    assert worker.motion_status == status()
    assert worker.consumed_drive_phase["expected_motion"]["phase_kind"] == "stop"


def test_error_can_report_lagging_node_clock_but_never_grants_normal_success():
    client = ControlPhaseClient("epoch")
    req = client.begin("state", "commit", 20)
    response = ack(req, ok=False, clock_ns=19, error="state_phase_task_terminal")
    client.receive("state", response, 20, 20)
    with pytest.raises(RuntimeError, match="state_phase_task_terminal"):
        client.consume()
    client = ControlPhaseClient("epoch")
    req = client.begin("state", "takeover", 20)
    with pytest.raises(ValueError, match="target clock"):
        client.receive("state", ack(req, clock_ns=19), 20, 20)


@pytest.mark.parametrize("actual_notice", [False, True])
def test_terminal_cancel_needs_the_workers_real_matching_terminal(actual_notice):
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch = "epoch"
    worker.clock_ns = worker.physical_ns = 20
    worker.control_phase = ControlPhaseClient("epoch")
    worker.control_publishers = {"state": object()}
    worker.control_phase_file = io.StringIO()
    worker.condition = threading.Condition()
    worker.stopping = False
    notice = {"epoch": "epoch", "end_sim_time_sec": 20 / 1e9,
              "termination_reason": "navigation_failure"}
    worker.task_terminal = notice if actual_notice else None

    def publish(publisher, value):
        worker.receive_control_phase("state", ack(
            value, clock_ns=19, ok=False, error="state_phase_task_terminal",
            terminal_notice=notice, scope="terminal_cancelled_uncommitted_state_phase"))

    def wait(predicate, *args):
        if not predicate():
            raise TimeoutError("missing real terminal")

    worker._publish, worker._wait = publish, wait
    if actual_notice:
        assert worker._control_rpc("state", "commit") is None
        assert worker.stopping
        assert '"kind": "terminal_cancelled"' in worker.control_phase_file.getvalue()
    else:
        with pytest.raises(TimeoutError, match="real terminal"):
            worker._control_rpc("state", "commit")
        assert not worker.stopping


def test_actual_stop_topic_callback_is_retained_after_control_ack_arrived_first():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch, worker.motion_status = "epoch", status()
    worker.stop_status = None
    worker.stopping = False
    events = []
    worker._trace_control_phase = lambda kind, **fields: events.append((kind, fields))
    value = status(stop=True, sequence=2)
    worker.receive_stop_status(value, origin="control_ack")
    worker.receive_stop_status(value, origin="stop_topic")
    assert [fields["origin"] for _, fields in events] == ["control_ack", "stop_topic"]
    assert events[-1][1]["duplicate"] is True


def test_abandoned_normal_timeout_cannot_be_hidden_by_a_permanent_stop():
    client = ControlPhaseClient("epoch")
    request = client.begin("motion", "commit", 20)
    client.abandon_for_stop()
    with pytest.raises(ValueError, match="actual failure"):
        client.receive("motion", ack(request, ok=False, error="phase timeout"), 20, 20)
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch = "epoch"
    worker._trace_control_phase = lambda *args, **kwargs: None
    with pytest.raises(RuntimeError, match="actual controlled execution failure"):
        worker.receive_control_phase("motion", ack(request, ok=False, error="phase timeout"))


def test_a_ready_predicate_cannot_bypass_a_sticky_callback_failure():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)

    def failed():
        raise RuntimeError("actual callback failure")

    worker._healthy = failed
    with pytest.raises(RuntimeError, match="actual callback failure"):
        worker._wait(lambda: True, 10., "must not return readiness")


def test_before_snapshot_abort_attempts_actual_zero_and_ordered_close_without_reward():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch = "epoch"
    worker.snapshot = None
    worker.helper = object()
    worker.clock_ns = worker.physical_ns = 20
    worker.control_phase = ControlPhaseClient(worker.epoch)
    events = []
    worker._trace_control_phase = lambda kind, **fields: events.append(kind)
    worker._commit_stop = lambda reason: events.append("actual_zero_storage")
    worker.shutdown_episode = lambda reason, infrastructure=False: events.append(
        ("ordered_close", reason, infrastructure))
    worker._reward = lambda *args, **kwargs: pytest.fail("invalid abort cannot manufacture reward")
    worker.abort_cleanup(RuntimeError("initial inputs unavailable"))
    assert worker.cleanup_mode and worker.controlled
    assert events == ["infrastructure_abort_started", "actual_zero_storage",
                      ("ordered_close", "infrastructure_failure", True),
                      "infrastructure_abort_closed"]


def reach_refs(sequence):
    return {name: {"intent_sequence": sequence, "payload_sha256": payload_sha256([name, sequence])}
            for name in ("tb1", "tb2", "tb3")}


def reach_status(clock=20, sequence=1, table="b"*64, stop=False):
    value = status(clock, stop=stop, sequence=sequence)
    value.update(schema="mr3-motion-safety-status-v2", safety_contract="mr3-reach-v1",
                 intent_refs=reach_refs(sequence), safety_table_sha256=table)
    return value


def reach_ack(request, refs=None, table="b"*64, **fields):
    return ack(request, safety_contract="mr3-reach-v1", intent_refs=refs,
               safety_table_sha256=table, **fields)


def test_reach_client_keeps_new_owner_refs_distinct_from_consumed_old_table():
    client = ControlPhaseClient("epoch", safety_contract="mr3-reach-v1")
    old = reach_refs(1)
    request = client.begin("state", "commit", 20, request_id="boundary20", expected_intents=old)
    assert request["schema"] == "mr3-state-phase-request-v2"
    state = reach_ack(request, refs=old, state_sequence=1, bundle_sha256="a"*64)
    client.receive("state", state, 20, 20); state = client.consume()
    request = client.begin("peer", "commit", 20, request_id="boundary20", state_commit=state)
    peer = reach_ack(request, refs=old, state_commit=state)
    client.receive("peer", peer, 20, 20); peer = client.consume()
    request = client.begin("motion", "commit", 20, request_id="boundary20", state_commit=state, peer_commit=peer)
    observed = reach_status(sequence=2)
    response = reach_ack(request, refs=observed["intent_refs"], status=observed)
    client.receive("motion", response, 20, 20)
    final = client.consume()
    assert final["intent_refs"] != state["intent_refs"]
    assert final["safety_table_sha256"] == state["safety_table_sha256"]


@pytest.mark.parametrize("mutation", ["refs", "table", "schema", "extra"])
def test_reach_client_rejects_substituted_state_refs_or_unknown_ack_fields(mutation):
    client = ControlPhaseClient("epoch", safety_contract="mr3-reach-v1")
    request = client.begin("state", "commit", 20, expected_intents=reach_refs(1))
    response = reach_ack(request, refs=reach_refs(1), state_sequence=1, bundle_sha256="a"*64)
    if mutation == "refs":
        response["intent_refs"] = reach_refs(2)
    elif mutation == "table":
        response["safety_table_sha256"] = None
    elif mutation == "schema":
        response["schema"] = "mr3-state-phase-ack-v1"
    else:
        response["passed"] = True
    with pytest.raises(ValueError):
        client.receive("state", response, 20, 20)


def test_takeover_null_table_is_not_claimed_consumption_or_normal_permission():
    client = ControlPhaseClient("epoch", safety_contract="mr3-reach-v1")
    request = client.begin("state", "takeover", 20, expected_intents=reach_refs(1))
    response = reach_ack(request, refs=None, table=None)
    client.receive("state", response, 20, 20)
    assert client.consume()["intent_refs"] is None
    value = reach_status(table=None)
    assert valid_motion_status(value, "epoch", 20, safety_contract="mr3-reach-v1")
    assert not valid_motion_status(value, "epoch", 20, safety_contract="mr3-reach-v1", require_table=True)
    value["outputs"]["tb1"]["linear_x"] = .001
    assert not valid_motion_status(value, "epoch", 20, safety_contract="mr3-reach-v1")


def test_legacy_rejects_reach_extras_and_reach_stop_is_permanent():
    assert not valid_motion_status(reach_status(), "epoch", 20)
    client = ControlPhaseClient("epoch")
    request = client.begin("state", "takeover", 20)
    with pytest.raises(ValueError):
        client.receive("state", reach_ack(request, refs=None, table=None), 20, 20)
    client = ControlPhaseClient("epoch", safety_contract="mr3-reach-v1")
    request = client.begin("motion", "stop", 20, reason="terminal")
    value = reach_status(stop=True, table=None)
    client.receive("motion", reach_ack(request, refs=value["intent_refs"], table=None, status=value), 20, 20)
    client.consume()
    with pytest.raises(ValueError, match="cannot resume"):
        client.begin("state", "commit", 40, expected_intents=reach_refs(2))


def owner_hold(name, release=20, sequence=2):
    source = release if release is not None else 19
    vector = {"x": 0., "y": 0., "z": 0.}
    odom = {"header": {"stamp": {"sec": 0, "nanosec": source}, "frame_id": name+"/odom"},
            "child_frame_id": name+"/base_footprint",
            "pose": {"pose": {"position": vector, "orientation": dict(vector, w=1.)}, "covariance": [0.]*36},
            "twist": {"twist": {"linear": vector, "angular": vector}, "covariance": [0.]*36}}
    return {"schema": "mr3-safety-intent-v1", "epoch": "epoch", "robot": name,
            "intent_sequence": sequence, "source_clock_ns": source, "role": "HOLD",
            "anchor": None if release is None else {"source_clock_ns": source, "odometry": odom},
            "admitted_signs": [], "lineage": {"release_clock_ns": release},
            "target": {"schema": "mr3-drive-target-v1", "epoch": "epoch", "robot": name,
                       "clock_ns": source, "decision_sequence": 1, "linear_x": 0., "angular_z": 0.}}


def intent_worker():
    module = load_worker()
    worker = module.Worker.__new__(module.Worker)
    worker.epoch, worker.safety_contract = "epoch", "mr3-reach-v1"
    worker.safety_intents, worker.safety_intent_publishers = {}, {}
    endpoint = SimpleNamespace(node_namespace="/", node_name="motion_safety",
                               topic_type="std_msgs/msg/String", endpoint_gid=bytes([1]*24))
    worker.node = SimpleNamespace(get_publishers_info_by_topic=lambda topic: [endpoint])
    worker._trace_control_phase = lambda *args, **kwargs: None
    return worker, endpoint


def test_worker_release_bootstrap_needs_three_actual_postrelease_owner_callbacks():
    worker, _ = intent_worker()
    worker.motion_status = reach_status()  # RPC/status refs alone cannot fill subscriptions.
    assert worker.release_intent_refs(20) is None
    for name in ("tb1", "tb2", "tb3"):
        worker.receive_safety_intent(name, SimpleNamespace(data=canonical(owner_hold(name, release=None, sequence=1))))
    assert worker.release_intent_refs(20) is None
    for name in ("tb1", "tb2"):
        worker.receive_safety_intent(name, SimpleNamespace(data=canonical(owner_hold(name))))
    assert worker.release_intent_refs(20) is None
    third = owner_hold("tb3")
    worker.receive_safety_intent("tb3", SimpleNamespace(data=canonical(third)))
    refs = worker.release_intent_refs(20)
    assert refs["tb3"] == {"intent_sequence": 2, "payload_sha256": payload_sha256(third)}
    assert worker.release_intent_refs(21) is None
    with pytest.raises(ValueError):
        worker.release_intent_refs(None)


def test_worker_rejects_foreign_owner_and_changed_same_sequence_before_bootstrap():
    worker, endpoint = intent_worker()
    endpoint.node_name = "foreign"
    value = owner_hold("tb1")
    with pytest.raises(ValueError, match="owner graph"):
        worker.receive_safety_intent("tb1", SimpleNamespace(data=canonical(value)))
    assert not worker.safety_intents
    endpoint.node_name = "motion_safety"
    worker.receive_safety_intent("tb1", SimpleNamespace(data=canonical(value)))
    value["target"]["decision_sequence"] += 1
    with pytest.raises(ValueError, match="changed identity"):
        worker.receive_safety_intent("tb1", SimpleNamespace(data=canonical(value)))


def test_worker_uses_release_override_once_then_previous_actual_motion_refs():
    module = load_worker(); worker = module.Worker.__new__(module.Worker)
    worker.safety_contract, worker.stopping = "mr3-reach-v1", False
    worker.physical_ns, worker.motion_status = 20, reach_status(sequence=10)
    worker.bootstrap_intent_refs = reach_refs(11)
    expected = []
    def rpc(component, operation, **references):
        if component == "state":
            expected.append(copy.deepcopy(references["expected_intents"]))
            return {"state": True}
        if component == "peer":
            return {"peer": True}
        return {"status": reach_status(clock=worker.physical_ns, sequence=11+len(expected)), "request_id": "boundary"+str(worker.physical_ns)}
    worker._control_rpc = rpc
    worker.receive_motion_status = lambda value: setattr(worker, "motion_status", value)
    worker.wait_motion_phase = lambda: None
    worker.wait_drive_phase = lambda value: None
    worker._commit_boundary()
    assert worker.bootstrap_intent_refs is None
    worker.physical_ns = 40
    worker._commit_boundary()
    assert expected == [reach_refs(11), reach_refs(12)]


@pytest.mark.parametrize("profile", [None, True, "reach", 1])
def test_worker_invalid_contract_fails_before_ros_or_launch(tmp_path, profile):
    with pytest.raises(ValueError, match="safety contract"):
        load_worker().Worker(tmp_path, {"epoch": "epoch", "scene": "open", "seed": 1,
                                      "quantum_steps": 20, "safety_contract": profile})


@pytest.mark.parametrize("steps", [1, 40, 20., True])
def test_reach_worker_rejects_a_larger_or_untyped_normal_quantum_before_any_send(steps):
    module = load_worker(); worker = module.Worker.__new__(module.Worker)
    worker.safety_contract, worker.controlled, worker.stopping = "mr3-reach-v1", True, False
    with pytest.raises(ValueError, match="physical step|20ms quantum"):
        worker._physics(steps)
