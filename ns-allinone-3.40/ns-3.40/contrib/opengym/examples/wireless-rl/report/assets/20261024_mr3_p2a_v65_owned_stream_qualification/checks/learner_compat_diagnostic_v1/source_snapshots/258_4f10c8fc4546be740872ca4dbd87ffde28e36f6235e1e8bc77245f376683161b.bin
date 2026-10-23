"""Source publication and real guard consumption are separate phase barriers."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from geometry_msgs.msg import Twist
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
import rclpy
from std_msgs.msg import String

from multi_robot_exploration.motion_safety import MotionSafety


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("plant_stimulus_worker", SCRIPTS / "mr3_env_worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


@pytest.mark.parametrize("relative,continuous,pulse", [
    (0, 0, 0), (1_199_999_999, 0, 0), (1_200_000_000, 800, 800),
    (2_199_999_999, 800, 800), (2_200_000_000, 800, 0),
    (2_239_999_999, 800, 0), (2_240_000_000, 800, 800),
    (2_739_999_999, 800, 800), (2_740_000_000, 0, 0), (4_000_000_000, 0, 0),
])
def test_fixed_waveform_has_exactly_one_40ms_opportunity(relative, continuous, pulse):
    assert WORKER.plant_stimulus_angular("continuous", relative) == continuous
    assert WORKER.plant_stimulus_angular("pulse", relative) == pulse


def fixture():
    worker = WORKER.Worker.__new__(WORKER.Worker)
    worker.epoch = "current"
    worker.plant_stimulus_arm = "pulse"
    worker.clock_ns = worker.physical_ns = 10_000_000_000
    worker.plant_stimulus_origin_ns = None
    worker.plant_stimulus_sequence = 0
    worker.plant_stimulus_pending = None
    worker.plant_stimulus_receipt = None
    worker.plant_stimulus_input_sequence = None
    worker.plant_stimulus_publisher_gid = None
    worker.plant_stimulus_receipt_publisher_gid = None
    worker.plant_stimulus_file = io.StringIO()
    worker.condition = threading.Condition()
    guard = SimpleNamespace(node_namespace="/", node_name="motion_safety",
                            topic_type="std_msgs/msg/String", endpoint_gid=[1] * 16)
    worker.node = SimpleNamespace(get_publishers_info_by_topic=lambda topic: [guard])
    return worker


def receipt():
    return {"schema": "mr3-guard-diagnostic-receipt-v1", "epoch": "current",
            "robot": "tb3", "clock_ns": 10_000_000_000, "input_sequence": 1,
            "v": 0., "w": 0., "supported": True,
            "publisher_identity": {"valid": True, "topic": "/tb3/cmd_vel_unguarded",
                                   "endpoints": [{"namespace": "/tb3",
                                                  "node": "velocity_smoother",
                                                  "endpoint_gid": "ab" * 16}]}}


@pytest.mark.parametrize("field,value", [
    ("epoch", "old"), ("robot", "tb1"), ("clock_ns", 10_000_000_001),
    ("input_sequence", True), ("input_sequence", 0), ("v", .01), ("w", .8),
    ("supported", False), ("publisher_identity", {"valid": False}),
])
def test_guard_receipt_rejects_wrong_boundary_source_or_value(field, value):
    worker = fixture()
    worker.plant_stimulus_pending = {"clock_ns": worker.clock_ns, "angular_millirad": 0}
    value_receipt = receipt()
    value_receipt[field] = value
    with pytest.raises(RuntimeError, match="real guard consumption"):
        worker.receive_plant_stimulus_receipt(value_receipt)
    assert worker.plant_stimulus_receipt is None


def test_guard_receipt_rejects_missing_publication_duplicate_and_replaced_publisher():
    worker = fixture()
    with pytest.raises(RuntimeError):
        worker.receive_plant_stimulus_receipt(receipt())
    worker.plant_stimulus_pending = {"clock_ns": worker.clock_ns, "angular_millirad": 0}
    worker.receive_plant_stimulus_receipt(receipt())
    with pytest.raises(RuntimeError):
        worker.receive_plant_stimulus_receipt(receipt())
    worker.plant_stimulus_receipt = None
    changed = receipt()
    changed["publisher_identity"]["endpoints"][0]["endpoint_gid"] = "cd" * 16
    with pytest.raises(RuntimeError):
        worker.receive_plant_stimulus_receipt(changed)


@pytest.mark.parametrize("case", ["absent", "duplicate", "imposter", "zero_gid", "replaced"])
def test_guard_receipt_topic_requires_the_unique_actual_guard_endpoint(case):
    worker = fixture()
    worker.plant_stimulus_pending = {"clock_ns": worker.clock_ns, "angular_millirad": 0}
    entries = worker.node.get_publishers_info_by_topic("unused")
    if case == "absent":
        entries = []
    elif case == "duplicate":
        entries *= 2
    elif case == "imposter":
        entries[0].node_name = "imposter"
    elif case == "zero_gid":
        entries[0].endpoint_gid = [0] * 16
    elif case == "replaced":
        worker.plant_stimulus_receipt_publisher_gid = "02" * 16
    worker.node.get_publishers_info_by_topic = lambda topic: entries
    with pytest.raises(RuntimeError, match="unique actual guard publisher"):
        worker.receive_plant_stimulus_receipt(receipt())
    assert worker.plant_stimulus_receipt is None


def test_source_service_ack_cannot_substitute_for_real_guard_consumption():
    worker = fixture()
    worker.Parameter = lambda name, value: SimpleNamespace(
        to_parameter_msg=lambda: (name, value))
    worker.SetParametersAtomically = SimpleNamespace(Request=SimpleNamespace)

    def call(request):
        fields = dict(request.parameters)
        ack = {"schema": "mr3-smoother-diagnostic-ack-v1", **fields, "robot": "tb3",
               "linear_x": 0., "publication_clock_ns": worker.clock_ns,
               "completion_scope": "smoother_publication_only_not_guard_or_storage",
               "output_topic": "/tb3/cmd_vel_unguarded"}
        return SimpleNamespace(done=lambda: True,
                               result=lambda: SimpleNamespace(result=SimpleNamespace(
                                   successful=True, reason=json.dumps(ack))))

    worker.plant_stimulus_client = SimpleNamespace(service_is_ready=lambda: True, call_async=call)

    def wait(predicate, timeout, label):
        if not predicate():
            raise TimeoutError(label)

    worker._wait = wait
    with pytest.raises(TimeoutError, match="real guard diagnostic request consumption"):
        worker._apply_plant_stimulus()
    assert worker.plant_stimulus_sequence == 0
    assert '"kind": "boundary_consumed"' not in worker.plant_stimulus_file.getvalue()


def test_stimulus_is_consumed_before_state_peer_and_guard_commit():
    worker = fixture()
    worker.stopping = False
    order = []
    status = {"phase_kind": "normal"}
    worker._apply_plant_stimulus = lambda: order.append("real_source_and_guard_receipt")

    def rpc(component, *args, **kwargs):
        order.append(component)
        return {"request_id": "same_boundary", "status": status}

    worker._control_rpc = rpc
    worker.receive_motion_status = lambda value: None
    worker.wait_motion_phase = lambda: None
    worker.wait_drive_phase = lambda value: order.append("real_storage")
    worker.motion_status = status
    worker._commit_boundary()
    assert order == ["real_source_and_guard_receipt", "state", "peer", "motion", "real_storage"]


def test_real_humble_guard_callback_receipt_contains_the_consumed_input_identity():
    """DDS CPU exchange, with no Gazebo or synthetic worker observation ACK."""
    rclpy.init(args=["--ros-args", "-p", "episode_epoch:=cpu_plant_receipt",
                    "-p", "stepped_mode:=true", "-p", "mr3_diagnostic_enabled:=true"])
    guard = MotionSafety()
    source = Node("velocity_smoother", namespace="/tb3")
    publisher = source.create_publisher(Twist, "/tb3/cmd_vel_unguarded", 20)
    receipts, recorded = [], []
    subscription = source.create_subscription(
        String, "/motion_safety/diagnostic_request_receipt",
        lambda message: receipts.append(json.loads(message.data)), 20)
    guard.record = lambda kind, payload: recorded.append((kind, payload))
    executor = SingleThreadedExecutor()
    executor.add_node(guard)
    executor.add_node(source)
    message = Twist()
    message.angular.z = .8
    try:
        deadline = time.monotonic() + 5.
        while not receipts and time.monotonic() < deadline:
            publisher.publish(message)
            executor.spin_once(timeout_sec=.02)
        assert receipts
        actual = receipts[0]
        assert actual["epoch"] == "cpu_plant_receipt" and actual["robot"] == "tb3"
        assert actual["v"] == 0. and actual["w"] == .8 and actual["supported"]
        assert type(actual["clock_ns"]) is int and actual["clock_ns"] > 0
        assert actual["publisher_identity"]["valid"]
        raw = next(payload for kind, payload in recorded if kind == "raw_request")
        assert actual["input_sequence"] == raw["request"]["sequence"]
        assert actual["publisher_identity"] == raw["request"]["publisher_identity"]
    finally:
        source.destroy_subscription(subscription)
        executor.remove_node(source)
        executor.remove_node(guard)
        executor.shutdown()
        source.destroy_node()
        guard.destroy_node()
        rclpy.shutdown()
