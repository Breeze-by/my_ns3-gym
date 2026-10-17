"""Actual tagged receipt causality and physical-advance regressions, without ROS."""

import ast
import copy
import io
import json
import math
from pathlib import Path
import threading
import time
from types import MethodType, SimpleNamespace

import pytest

from multi_robot_exploration.mr3_drive_phase import (
    DrivePhaseClient, PROTOCOL, ROBOTS, WALL_GUARD_SEC, valid_output,
)


START = 76_260_000_000
EPOCH = "current-native-epoch"
WORKER_PATH = Path(__file__).resolve().parents[3] / "scripts/mr3_env_worker.py"


def motion(clock=START, sequence=3806, output=None):
    output = {"linear_x": 0., "angular_z": 0.} if output is None else output
    return {"schema": "mr3-motion-safety-status-v1", "epoch": EPOCH,
            "completion_scope": "publication_and_local_topic_receipt", "ready": True,
            "clock_ns": clock, "decision_sequences": {name: sequence for name in ROBOTS},
            "outputs": {name: copy.deepcopy(output) for name in ROBOTS}}


def receipt(name="tb1", *, clock=START, sequence=3806, cmd_seq=1232, output=None):
    value = motion(clock, sequence, output)["outputs"][name]
    return {"schema": PROTOCOL, "epoch": EPOCH, "robot": name, "clock_ns": clock,
            "source_clock_ns": clock, "decision_sequence": sequence,
            "cmd_seq": cmd_seq, **value}


def delivered(client, boundary=None):
    boundary = motion() if boundary is None else boundary
    for name in ROBOTS:
        assert client.receive(receipt(name, clock=boundary["clock_ns"],
                                      sequence=boundary["decision_sequences"][name],
                                      output=boundary["outputs"][name]))


def test_only_three_real_receipts_can_be_consumed_and_consumed_receipts_do_not_reappear():
    client = DrivePhaseClient(EPOCH)
    boundary = motion()
    for name in ROBOTS[:2]:
        client.receive(receipt(name))
    assert client.matching(boundary) is None
    with pytest.raises(RuntimeError, match="incomplete"):
        client.consume(boundary)
    client.receive(receipt("tb3"))
    result = client.consume(boundary)
    assert set(result) == set(ROBOTS)
    assert client.matching(boundary) is None
    assert client.receive(receipt("tb3")) is False
    assert client.matching(boundary) is None


def test_received_input_and_returned_rows_cannot_mutate_stored_target_identity():
    client = DrivePhaseClient(EPOCH)
    original = receipt()
    client.receive(original)
    original["linear_x"] = .2
    client.receive(receipt("tb2"))
    client.receive(receipt("tb3"))
    result = client.matching(motion())
    result["tb1"]["linear_x"] = .1
    assert client.consume(motion())["tb1"]["linear_x"] == 0.


def test_unknown_epoch_never_enters_the_three_robot_barrier():
    client = DrivePhaseClient(EPOCH)
    for name in ROBOTS:
        assert client.receive({**receipt(name), "epoch": "old-episode"}) is False
    assert client.matching(motion()) is None
    with pytest.raises(ValueError):
        client.matching({**motion(), "epoch": "old-episode"})


@pytest.mark.parametrize("field,value", [
    ("schema", "invented"), ("robot", "tb4"), ("clock_ns", True),
    ("clock_ns", -1), ("clock_ns", 76.26), ("source_clock_ns", -1),
    ("source_clock_ns", True), ("decision_sequence", True), ("decision_sequence", 0),
    ("decision_sequence", 3806.), ("cmd_seq", 0), ("cmd_seq", "1232"),
    ("linear_x", True), ("linear_x", None), ("linear_x", 10**1000),
    ("linear_x", float("nan")), ("angular_z", float("inf")),
    ("angular_z", -float("inf")), ("angular_z", 10**1000),
    ("linear_x", math.nextafter(.26, math.inf)),
    ("angular_z", -math.nextafter(.8, math.inf)),
])
def test_malformed_or_unbounded_driver_target_cannot_enter_pending(field, value):
    client = DrivePhaseClient(EPOCH)
    with pytest.raises(ValueError):
        client.receive({**receipt(), field: value})
    assert client.matching(motion()) is None


@pytest.mark.parametrize("value", [None, [], "receipt", 1])
def test_nonobject_json_receipts_are_protocol_errors(value):
    with pytest.raises(ValueError):
        DrivePhaseClient(EPOCH).receive(value)


@pytest.mark.parametrize("mutation", ["missing", "extra", "future-source"])
def test_exact_receipt_schema_and_source_not_ahead_of_actual_receipt(mutation):
    value = receipt()
    if mutation == "missing":
        del value["cmd_seq"]
    elif mutation == "extra":
        value["truth"] = [0, 0]
    else:
        value["source_clock_ns"] += 1
    with pytest.raises(ValueError):
        DrivePhaseClient(EPOCH).receive(value)


@pytest.mark.parametrize("change", [
    {"cmd_seq": 1231}, {"cmd_seq": 1232, "decision_sequence": 3807},
    {"cmd_seq": 1233, "decision_sequence": 3805},
    {"cmd_seq": 1233, "decision_sequence": 3807, "source_clock_ns": START - 1},
    {"cmd_seq": 1233, "decision_sequence": 3807,
     "clock_ns": START - 1, "source_clock_ns": START - 1},
    {"linear_x": .2},
])
def test_regression_or_conflicting_same_identity_is_not_an_ack_update(change):
    client = DrivePhaseClient(EPOCH)
    client.receive(receipt())
    with pytest.raises(ValueError, match="regressed|identity"):
        client.receive({**receipt(), **change})


def test_future_receipt_cannot_acknowledge_the_current_paused_clock():
    client = DrivePhaseClient(EPOCH)
    client.receive({**receipt(), "clock_ns": START + 1})
    with pytest.raises(ValueError, match="paused guard target"):
        client.matching(motion())


def test_history_cannot_authorize_motion_after_driver_has_stored_a_newer_target():
    client = DrivePhaseClient(EPOCH)
    delivered(client)
    client.receive(receipt(clock=START + 20_000_000, sequence=3807, cmd_seq=1233,
                           output={"linear_x": .2, "angular_z": .4}))
    with pytest.raises(ValueError, match="target changed"):
        client.consume(motion())


@pytest.mark.parametrize("boundary", [
    None, [], {**motion(), "clock_ns": True}, {**motion(), "clock_ns": -1},
    {**motion(), "decision_sequences": None}, {**motion(), "outputs": None},
    {**motion(), "decision_sequences": {"tb1": 3806, "tb2": 3806}},
    {**motion(), "outputs": {"tb1": {}, "tb2": {}, "tb3": {}}},
])
def test_malformed_expected_motion_never_consumes_receipts(boundary):
    client = DrivePhaseClient(EPOCH)
    delivered(client)
    with pytest.raises(ValueError):
        client.consume(boundary)
    assert client.matching(motion()) is not None


@pytest.mark.parametrize("change", [
    {"linear_x": .2}, {"angular_z": -.2}, {"source_clock_ns": START - 1},
])
def test_same_sequence_must_bind_exact_clock_and_both_output_components(change):
    client = DrivePhaseClient(EPOCH)
    for name in ROBOTS:
        client.receive({**receipt(name), **change})
    with pytest.raises(ValueError, match="paused guard target"):
        client.consume(motion())


def worker_class():
    """Compile actual worker methods only; never execute imports or ROS setup."""
    tree = ast.parse(WORKER_PATH.read_text())
    original = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "Worker")
    methods = [copy.deepcopy(x) for x in original.body
               if isinstance(x, ast.FunctionDef) and x.name != "__init__"]
    definition = ast.ClassDef(name="Worker", bases=[], keywords=[], body=methods,
                              decorator_list=[])
    namespace = {"json": json, "time": time, "valid_output": valid_output,
                 "DRIVE_WALL_GUARD_SEC": WALL_GUARD_SEC,
                 "MOTION_PHASE_COMPLETION": "publication_and_local_topic_receipt"}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[definition], type_ignores=[])),
                 str(WORKER_PATH), "exec"), namespace)
    return namespace["Worker"]


class HeldCondition:
    def __init__(self):
        self.depth = 0

    def __enter__(self):
        self.depth += 1
        return self

    def __exit__(self, *args):
        self.depth -= 1


def worker():
    instance = worker_class()()
    instance.epoch = EPOCH
    instance.physical_ns = instance.clock_ns = START
    instance.physics_number = 0
    instance.motion_status = motion()
    instance.drive_phase = DrivePhaseClient(EPOCH)
    instance.consumed_drive_phase = None
    instance.callback_error = None
    instance.condition = HeldCondition()
    instance.physics_file = io.StringIO()
    instance.events = []
    instance.sent = []
    instance._trace_drive_phase = lambda kind, **payload: instance.events.append((kind, payload))

    def healthy():
        if instance.callback_error:
            raise RuntimeError("ROS callback failed: " + instance.callback_error)

    def wait(predicate, timeout, label):
        healthy()
        if not predicate():
            raise TimeoutError(label)

    def send(value):
        instance.events.append(("helper.send", value))
        instance.sent.append(value)

    def receive(timeout):
        request = instance.sent[-1]
        start, ticks = instance.physical_ns, request["steps"]
        instance.clock_ns = start + ticks * 1_000_000
        return {"request_id": request["request_id"], "epoch": EPOCH,
                "ok": True, "paused": True, "start_time_ns": start,
                "end_time_ns": instance.clock_ns, "start_iterations": start // 1_000_000,
                "end_iterations": start // 1_000_000 + ticks}

    instance._healthy = healthy
    instance._wait = wait
    instance.wait_motion_phase = lambda: instance.events.append(("wait_motion_phase", {}))
    instance.helper_peer = SimpleNamespace(send=send, receive=receive)
    return instance


def accept(instance, name="tb1", **kwargs):
    with instance.condition:
        instance.receive_drive_status(name, receipt(name, **kwargs))


def accept_all(instance, **kwargs):
    for name in ROBOTS:
        accept(instance, name, **kwargs)


def test_worker_requires_real_receive_then_three_consumes_before_physics_send():
    instance = worker()
    for name in ROBOTS[:2]:
        accept(instance, name)
    with pytest.raises(TimeoutError):
        instance._physics(20)
    assert not instance.sent
    accept(instance, "tb3")
    result = instance._physics(20)
    assert result["end_time_ns"] == START + 20_000_000
    kinds = [kind for kind, _ in instance.events]
    assert kinds.count("ack_received") == 3
    assert kinds.index("ack_consumed") < kinds.index("advance_permitted") < kinds.index(
        "helper.send") < kinds.index("physics_completed")
    assert instance.drive_phase.matching(motion()) is None


def test_worker_topic_robot_cannot_impersonate_the_missing_other_driver():
    instance = worker()
    with instance.condition:
        with pytest.raises(ValueError):
            instance.receive_drive_status("tb1", receipt("tb2"))
    assert instance.drive_phase.matching(motion()) is None
    assert not instance.sent


def test_actual_v6_stale_target_712ms_old_cannot_authorize_next_quantum():
    instance = worker()
    old = {"linear_x": .20526315789473687, "angular_z": -.7157894736842105}
    for name in ROBOTS:
        accept(instance, name, clock=75_560_000_000, sequence=3771,
               cmd_seq=1231, output=old)
    with pytest.raises(TimeoutError):
        instance._physics(20)
    assert not instance.sent
    accept_all(instance)
    instance._physics(20)
    assert len(instance.sent) == 1


def test_same_boundary_cache_does_not_consume_receipts_twice_or_supply_the_next_clock():
    instance = worker()
    accept_all(instance)
    boundary = copy.deepcopy(instance.motion_status)
    first = instance.wait_drive_phase(boundary)
    assert instance.wait_drive_phase(boundary) == first
    assert sum(kind == "ack_consumed" for kind, _ in instance.events) == 1
    instance._physics(20)
    instance.motion_status = motion(clock=START + 20_000_000, sequence=3807)
    with pytest.raises(TimeoutError):
        instance._physics(20)
    assert len(instance.sent) == 1
    accept_all(instance, clock=START + 20_000_000, sequence=3807, cmd_seq=1233)
    instance._physics(20)
    assert len(instance.sent) == 2


@pytest.mark.parametrize("cached", [False, True])
def test_callback_identity_error_blocks_even_a_complete_or_cached_phase(cached):
    instance = worker()
    accept_all(instance)
    if cached:
        instance.wait_drive_phase(instance.motion_status)
    # This is what the real callback wrapper records after receive rejects a conflict.
    with pytest.raises(ValueError):
        instance.drive_phase.receive({**receipt(), "angular_z": .2})
    instance.callback_error = "native drive receipt regressed or changed identity"
    with pytest.raises(RuntimeError):
        instance._physics(20)
    assert not instance.sent


def test_callback_error_between_phase_wait_and_send_cannot_advance_physics():
    instance = worker()
    accept_all(instance)
    original = instance.wait_drive_phase

    def callback_arrives(boundary):
        result = original(boundary)
        instance.callback_error = "conflicting driver receipt during physical pause"
        return result

    instance.wait_drive_phase = callback_arrives
    with pytest.raises(RuntimeError, match="callback"):
        instance._physics(20)
    assert not instance.sent


@pytest.mark.parametrize("field", ["clock_ns", "physical_ns"])
def test_cached_phase_cannot_bypass_exact_current_clock(field):
    instance = worker()
    accept_all(instance)
    boundary = copy.deepcopy(instance.motion_status)
    instance.wait_drive_phase(boundary)
    setattr(instance, field, START + 1)
    with pytest.raises(RuntimeError):
        instance.wait_drive_phase(boundary)


def test_future_or_wrong_target_sequence_does_not_supply_the_current_phase():
    instance = worker()
    accept_all(instance, clock=START + 20_000_000, sequence=3807, cmd_seq=1233)
    with pytest.raises(TimeoutError):
        instance._physics(20)
    assert not instance.sent


def test_cached_receipts_cannot_authorize_a_driver_that_has_stored_a_newer_target():
    instance = worker()
    accept_all(instance)
    instance.wait_drive_phase(instance.motion_status)
    accept(instance, clock=START + 20_000_000, sequence=3807, cmd_seq=1233,
           output={"linear_x": .2, "angular_z": .4})
    with pytest.raises((TimeoutError, ValueError)):
        instance._physics(20)
    assert not instance.sent


def test_outer_physics_lock_releases_for_real_ack_callback_then_sends_after_consumption():
    instance = worker()
    instance.condition = threading.Condition()
    actual_wait = MethodType(type(instance)._wait, instance)
    waiting, callback_completed = threading.Event(), threading.Event()
    callback_errors = []

    def wait(predicate, timeout, label):
        if "drive" in label:
            waiting.set()
        return actual_wait(predicate, timeout, label)

    def callback():
        try:
            assert waiting.wait(2.)
            with instance.condition:
                for name in ROBOTS:
                    instance.receive_drive_status(name, receipt(name))
                instance.condition.notify_all()
            callback_completed.set()
        except BaseException as error:
            callback_errors.append(error)

    instance._wait = wait
    thread = threading.Thread(target=callback)
    thread.start()
    try:
        instance._physics(20)
    finally:
        thread.join(2.)
    assert callback_completed.is_set() and not callback_errors and not thread.is_alive()
    kinds = [kind for kind, _ in instance.events]
    assert kinds.index("ack_consumed") < kinds.index("helper.send")


def test_only_initial_reset_alignment_may_advance_without_the_driver_barrier():
    tree = ast.parse(WORKER_PATH.read_text())
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "Worker")
    bypass = []
    for method in cls.body:
        if not isinstance(method, ast.FunctionDef):
            continue
        for call in ast.walk(method):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "_physics"
                    and any(x.arg == "wait_clock" and isinstance(x.value, ast.Constant)
                            and x.value.value is False for x in call.keywords)):
                assert call.args and isinstance(call.args[0], ast.Constant)
                bypass.append((method.name, call.args[0].value, call.lineno))
    # Zero-step pause also serves invalid startup cleanup. Only the dedicated
    # pre-control clock alignment may advance without a tagged-storage barrier.
    assert sorted((name, steps) for name, steps, _ in bypass) == [
        ("_align_initial_clock", 1), ("abort_cleanup", 0), ("reset", 0)]
    reset = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "reset")
    drive_line = next(x.lineno for x in ast.walk(reset) if isinstance(x, ast.Call)
                      and isinstance(x.func, ast.Attribute) and x.func.attr == "wait_drive_phase")
    snapshot_line = next(x.lineno for x in ast.walk(reset) if isinstance(x, ast.Call)
                         and isinstance(x.func, ast.Attribute) and x.func.attr == "_snapshot")
    bootstrap = [x for x in ast.walk(reset) if isinstance(x, ast.Call)
                 and isinstance(x.func, ast.Attribute) and x.func.attr == "_physics"
                 and x.args and isinstance(x.args[0], ast.Constant) and x.args[0].value == 20]
    assert len(bootstrap) == 1 and not bootstrap[0].keywords
    takeover = [x for x in ast.walk(reset) if isinstance(x, ast.Call)
                and isinstance(x.func, ast.Attribute) and x.func.attr == "_control_rpc"
                and len(x.args) > 1 and isinstance(x.args[1], ast.Constant)
                and x.args[1].value == "takeover"]
    assert len(takeover) == 3 and {x.args[0].value for x in takeover} == {
        "state", "peer", "motion"}
    assert max(x.lineno for x in takeover) < drive_line < bootstrap[0].lineno < snapshot_line
