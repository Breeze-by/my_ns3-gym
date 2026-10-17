"""Native ROS message fixtures for the ideal bridge; no simulator is launched."""

import json
import math
import copy
import io
from concurrent.futures import Future
from types import MethodType, SimpleNamespace

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.mr3_information import (
    IdealInformation, map_digest, map_payload, payload_digest, restore_message, state_payload,
)
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class ImmediateExecutor:
    """Keep logical map fixtures synchronous; scheduling has separate fixtures."""

    def submit(self, function, *args):
        future = Future()
        future.set_result(function(*args))
        return future


class ControlledExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args):
        future = Future()
        self.jobs.append((future, function, args))
        return future

    def complete_next(self):
        future, function, args = self.jobs.pop(0)
        future.set_result(function(*args))


def grid(data, stamp=1, origin=0.0):
    message = OccupancyGrid()
    message.header.stamp.sec = stamp
    message.header.frame_id = "map"
    message.info.width = len(data)
    message.info.height = 1
    message.info.resolution = 0.1
    message.info.origin.position.x = origin
    message.info.origin.orientation.w = 1.0
    message.data = data
    return message


def bridge():
    names = ("tb1", "tb2", "tb3")
    node = SimpleNamespace(
        names=names, epoch="episode-a", now=lambda: 2.0, tf_validity_lead_sec=0.0,
        local_maps={}, local_map_versions={}, local_odometry={}, local_transforms={},
        pending_odometry={name: [] for name in names},
        pending_transforms={name: [] for name in names},
        state_input_sequences={(kind, name): 0 for kind in ("odom", "tf") for name in names},
        state_input_refs={kind: {} for kind in ("odom", "tf")},
        state_audit_stream=None, state_audit_sequence=0, state_input_failed=False,
        clock_failed=False,
        transport=IdealTransport("episode-a"), received=ReceivedStore("episode-a"),
        edges={name: ReceivedStore("episode-a") for name in names},
        downlinks={name: IdealTransport("episode-a") for name in names},
        navigation_publishers={name: Publisher() for name in names},
        received_map_publishers={name: Publisher() for name in names},
        received_map_digests={},
        published_map_records={}, navigation_maps={}, navigation_sources={},
        map_executor=ImmediateExecutor(), map_future=None, queued_map_job=None,
        map_failure_publisher=Publisher(),
        map_diagnostics={"submitted": 0, "completed": 0, "replaced_queued": 0,
                         "capture_wall_sec": 0.0, "publish_wall_sec": 0.0,
                         "worker_wall_sec": 0.0, "state_wall_sec": 0.0},
        odom_publishers={name: Publisher() for name in names},
        tf_publishers={name: Publisher() for name in names},
        map_publisher=Publisher(), map_metadata_publisher=Publisher(),
        state_publisher=Publisher(), map_signature=None,
        hub_map=None, map_payload_sha256=None, map_version=0, state_sequence=0,
        hub_map_source_stamp=None, hub_map_received_stamp=None,
    )
    node.publish_navigation_map = MethodType(IdealInformation.publish_navigation_map, node)
    for method in ("promote_transforms", "promote_odometry", "record_state", "prune_input_refs",
                   "fail_state_input"):
        setattr(node, method, MethodType(getattr(IdealInformation, method), node))
    node.submit_map_job = MethodType(IdealInformation.submit_map_job, node)
    node.finish_maps = MethodType(IdealInformation.finish_maps, node)
    return node


def state_input_bridge(audit=True):
    node = bridge()
    node.clock_ns = 2_000_000_000
    node.tf_validity_lead_sec = .2
    node.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=node.clock_ns))
    node.get_logger = lambda: SimpleNamespace(error=lambda message: None)
    node.last_now = None
    node.now = MethodType(IdealInformation.now, node)
    if audit:
        node.state_audit_stream = io.StringIO()
        node.record_state("configuration", {
            "tf_validity_lead_sec": .2, "pending_limit": 256, "state_period_sec": .1,
            "odom_pending_order": "source_ns_ascending",
            "tf_pending_order": "accepted_header_ascending",
        })
    return node


def input_odom(source_ns, x=0.0):
    message = Odometry()
    message.header.frame_id = "odom"
    message.child_frame_id = "base_footprint"
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(source_ns, 1_000_000_000)
    message.pose.pose.position.x = x
    message.pose.pose.orientation.w = 1.0
    return message


def input_tf(source_ns):
    message = TransformStamped()
    message.header.frame_id, message.child_frame_id = "map", "odom"
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(
        source_ns + 200_000_000, 1_000_000_000)
    message.transform.rotation.w = 1.0
    return TFMessage(transforms=[message])


def input_rows(node, kind=None):
    rows = [json.loads(line) for line in node.state_audit_stream.getvalue().splitlines()]
    return [row for row in rows if kind is None or row["kind"] == kind]


def test_future_latest_odom_preserves_newest_causal_input_and_promotes_when_due():
    node = state_input_bridge()
    for stamp in (1_900_000_000, 2_002_000_000, 1_998_000_000):
        IdealInformation.receive_local_odom(node, "tb1", input_odom(stamp))
    IdealInformation.receive_local_tf(node, "tb1", input_tf(1_979_000_000))
    IdealInformation.publish_states(node)
    first = node.received.get("state", "tb1")
    assert first.payload["odom_source_stamp"] == 1.998
    assert math.isclose(first.payload["tf_source_stamp"], 1.979)
    assert len(node.pending_odometry["tb1"]) == 1
    selection = input_rows(node, "state_selection")[0]["payload"]
    assert selection["odom_input_sequence"] == 3
    assert selection["pending_odom_input_sequences"] == [2]
    node.clock_ns = 2_002_000_000
    IdealInformation.publish_states(node)
    assert node.received.get("state", "tb1").payload["odom_source_stamp"] == 2.002
    assert not node.pending_odometry["tb1"]


def test_only_future_odom_is_not_published_and_is_not_discarded():
    node = state_input_bridge()
    IdealInformation.receive_local_odom(node, "tb1", input_odom(2_002_000_000))
    IdealInformation.receive_local_tf(node, "tb1", input_tf(1_979_000_000))
    IdealInformation.publish_states(node)
    assert node.received.get("state", "tb1") is None
    selection = input_rows(node, "state_selection")[0]["payload"]
    assert selection["skip_reason"] == "missing_odom"
    assert selection["pending_odom_input_sequences"] == [1]


def test_odom_duplicate_keeps_original_reference_and_backwards_cannot_replace_selected():
    node = state_input_bridge()
    sample = input_odom(1_999_000_000)
    IdealInformation.receive_local_odom(node, "tb1", sample)
    IdealInformation.receive_local_odom(node, "tb1", copy.deepcopy(sample))
    node.promote_odometry(2.0)
    IdealInformation.receive_local_odom(node, "tb1", input_odom(1_900_000_000))
    rows = [row["payload"] for row in input_rows(node, "odom_ingress")]
    assert [row["admission"] for row in rows] == ["queued", "duplicate", "backwards"]
    assert rows[1]["matched_input_sequence"] == 1
    assert rows[2]["matched_input_sequence"] is None
    assert node.state_input_refs["odom"][id(node.local_odometry["tb1"])] == 1


def test_conflicting_odom_duplicate_publishes_explicit_failure_and_stops_future_progress():
    node = state_input_bridge()
    IdealInformation.receive_local_odom(node, "tb1", input_odom(1_999_000_000))
    IdealInformation.receive_local_odom(node, "tb1", input_odom(1_999_000_000, x=1.0))
    assert node.clock_failed and node.state_input_failed
    failure = json.loads(node.map_failure_publisher.messages[-1].data)
    assert failure["reason"] == "odom_conflicting_duplicate"
    assert input_rows(node)[-2]["payload"]["admission"] == "conflicting_duplicate"
    assert input_rows(node)[-1]["kind"] == "state_input_failure"
    IdealInformation.publish_states(node)
    IdealInformation.publish_maps(node)
    assert not node.state_publisher.messages and not node.map_publisher.messages


def test_odom_queue_overflow_fails_instead_of_eviction_or_silent_wait():
    node = state_input_bridge()
    for value in range(257):
        IdealInformation.receive_local_odom(node, "tb1", input_odom(3_000_000_000 + value))
    assert len(node.pending_odometry["tb1"]) == 256
    assert node.clock_failed
    failure = json.loads(node.map_failure_publisher.messages[-1].data)
    assert failure["reason"] == "odom_queue_overflow"


def test_tf_duplicates_are_recorded_and_map_work_does_not_consume_state_inputs():
    node = state_input_bridge()
    for stamp in (1_900_000_000, 1_900_000_000, 1_899_000_000, 2_001_000_000):
        IdealInformation.receive_local_tf(node, "tb1", input_tf(stamp))
    node.local_maps = {"tb1": grid([0])}
    node.local_map_versions = {"tb1": 1}
    IdealInformation.publish_maps(node)
    assert not node.local_transforms
    node.promote_transforms(2.0)
    rows = [row["payload"] for row in input_rows(node, "tf_ingress")]
    assert [row["admission"] for row in rows] == [
        "queued", "ignored_pending_order", "ignored_pending_order", "queued"]
    assert [rows[i]["matched_input_sequence"] for i in (1, 2)] == [1, 1]
    promotion = input_rows(node, "tf_promote")[-1]["payload"]
    assert promotion == {"robot": "tb1", "selected_input_sequence": 1,
                         "pending_tf_input_sequences": [4]}
    assert not node.local_odometry and not node.pending_odometry["tb1"]


def test_tf_queue_overflow_publishes_failure_without_rewriting_map_failure_path():
    node = state_input_bridge()
    for value in range(257):
        IdealInformation.receive_local_tf(node, "tb1", input_tf(3_000_000_000 + value))
    assert len(node.pending_transforms["tb1"]) == 256
    assert node.clock_failed
    failure = json.loads(node.map_failure_publisher.messages[-1].data)
    assert failure["reason"] == "tf_queue_overflow"


def test_tf_source_integer_endpoint_is_promoted_without_float_boundary_starvation():
    node = state_input_bridge()
    node.clock_ns = 67_979_000_000
    IdealInformation.receive_local_tf(node, "tb1", input_tf(node.clock_ns))
    node.promote_transforms(node.clock_ns / 1e9)
    assert "tb1" in node.local_transforms
    assert not node.pending_transforms["tb1"]
    IdealInformation.receive_local_odom(node, "tb1", input_odom(node.clock_ns))
    IdealInformation.publish_states(node)
    robot = json.loads(node.state_publisher.messages[-1].data)["robots"][0]
    assert robot["valid"] and robot["sequence"] == 1
    assert input_rows(node, "state_selection")[0]["payload"]["skip_reason"] is None


def test_validity_half_second_endpoint_uses_exact_clock_endpoints_without_tolerance():
    for age_ns, valid in ((500_000_000, True), (500_000_001, False)):
        node = state_input_bridge()
        source = 564_000_000
        node.clock_ns = source + age_ns
        IdealInformation.receive_local_odom(node, "tb1", input_odom(source))
        IdealInformation.receive_local_tf(node, "tb1", input_tf(source))
        IdealInformation.publish_states(node)
        assert json.loads(node.state_publisher.messages[-1].data)["robots"][0]["valid"] is valid


def test_one_nanosecond_future_tf_and_odom_cannot_make_a_valid_state():
    node = state_input_bridge()
    IdealInformation.receive_local_odom(node, "tb1", input_odom(node.clock_ns + 1))
    IdealInformation.receive_local_tf(node, "tb1", input_tf(node.clock_ns + 1))
    IdealInformation.publish_states(node)
    assert node.received.get("state", "tb1") is None
    assert len(node.pending_odometry["tb1"]) == len(node.pending_transforms["tb1"]) == 1


def test_state_ledger_binds_full_raw_selected_inputs_actual_envelopes_and_side_publications():
    node = state_input_bridge()
    for name in node.names:
        IdealInformation.receive_local_odom(node, name, input_odom(1_999_000_000))
        IdealInformation.receive_local_tf(node, name, input_tf(1_979_000_000))
    IdealInformation.publish_states(node)
    rows = input_rows(node)
    assert [row["record_sequence"] for row in rows] == list(range(1, len(rows) + 1))
    for row in input_rows(node, "odom_ingress") + input_rows(node, "tf_ingress"):
        assert payload_digest(row["payload"]["raw"]) == row["payload"]["raw_sha256"]
    published = input_rows(node, "state_publish")[-1]
    value = published["payload"]
    assert value["message"] == json.loads(node.state_publisher.messages[-1].data)
    assert payload_digest(value["message"]) == value["message_sha256"]
    assert (value["publish_started_wall_monotonic_ns"]
            <= value["publish_completed_wall_monotonic_ns"] <= published["wall_monotonic_ns"])
    assert value["scope"] == "actual_publish_calls_returned"
    for side in value["side_publications"]:
        envelope = value["envelopes"][side["robot"]]
        assert side["odom_sha256"] == payload_digest(envelope["payload"]["odometry"])
        assert side["tf_sha256"] == payload_digest(envelope["payload"]["transform"])
        assert side["envelope_sequence"] == envelope["sequence"]
    assert not any("input_sequence" in robot for robot in value["message"]["robots"])


def test_empty_audit_does_not_read_clock_or_write_diagnostics():
    node = bridge()
    node.tf_validity_lead_sec = .2
    node.get_clock = lambda: (_ for _ in ()).throw(AssertionError("audit clock read"))
    IdealInformation.receive_local_odom(node, "tb1", input_odom(1_999_000_000))
    IdealInformation.receive_local_tf(node, "tb1", input_tf(1_979_000_000))
    IdealInformation.publish_states(node)
    assert node.state_audit_sequence == 0 and node.state_audit_stream is None
    assert node.received.get("state", "tb1") is not None


def test_full_occupancy_json_round_trip_preserves_unknown_and_original_header():
    original = grid([-1, 0, 100])
    payload = json.loads(json.dumps(map_payload(original)))
    restored = restore_message(OccupancyGrid(), payload)
    assert restored == original
    assert list(restored.data) == [-1, 0, 100]


def test_map_digest_binds_data_header_and_origin():
    original = grid([-1, 0, 100])
    digest = map_digest(original)
    assert digest == map_digest(restore_message(OccupancyGrid(), map_payload(original)))
    assert digest != map_digest(grid([-1, 100, 100]))
    assert digest != map_digest(grid([-1, 0, 100], stamp=2))
    assert digest != map_digest(grid([-1, 0, 100], origin=0.1))


def test_state_uses_estimated_transform_and_measured_twist():
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 2
    odometry.pose.pose.position.x = 2.0
    odometry.pose.pose.orientation.w = 1.0
    odometry.twist.twist.linear.x = 0.13
    odometry.twist.twist.angular.z = -0.2
    transform.header.stamp.sec = 1
    transform.transform.translation.x = 3.0
    transform.transform.rotation.z = math.sin(math.pi / 4)
    transform.transform.rotation.w = math.cos(math.pi / 4)
    result = state_payload("tb1", odometry, transform)
    assert math.isclose(result["x"], 3.0)
    assert math.isclose(result["y"], 2.0)
    assert math.isclose(result["yaw"], math.pi / 2)
    assert (result["v"], result["w"]) == (0.13, -0.2)
    assert (result["odom_source_stamp"], result["tf_source_stamp"]) == (2, 1)


def test_future_tf_cannot_hide_behind_current_odom_source_stamp():
    node = bridge()
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 1
    odometry.pose.pose.orientation.w = 1.0
    transform.header.stamp.sec = 3
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    node.local_transforms["tb1"] = transform
    IdealInformation.publish_states(node)
    assert node.received.get("state", "tb1") is None
    assert not node.odom_publishers["tb1"].messages
    assert not node.tf_publishers["tb1"].messages


def test_tf_validity_lead_is_subtracted_from_source_age_without_rewriting_header():
    node = bridge()
    node.tf_validity_lead_sec = 0.2
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 2
    odometry.pose.pose.orientation.w = 1.0
    transform.header.stamp.sec = 2
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    node.local_transforms["tb1"] = transform
    IdealInformation.publish_states(node)
    robot = json.loads(node.state_publisher.messages[-1].data)["robots"][0]
    assert robot["tf_source_stamp"] == robot["source_stamp"] == 1.8
    assert robot["tf_validity_stamp"] == 2.0
    assert robot["tf_validity_lead_sec"] == 0.2
    assert robot["valid"] is True
    assert node.tf_publishers["tb1"].messages[-1].transforms[0].header.stamp.sec == 2


def test_available_sensor_estimate_does_not_wait_for_forward_dated_validity_header():
    node = bridge()
    node.tf_validity_lead_sec = 0.2
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 2
    odometry.pose.pose.orientation.w = 1.0
    transform.header.frame_id = "map"
    transform.child_frame_id = "odom"
    transform.header.stamp.sec = 2
    transform.header.stamp.nanosec = 100000000
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    IdealInformation.receive_local_tf(node, "tb1", TFMessage(transforms=[transform]))
    IdealInformation.publish_states(node)
    record = node.received.get("state", "tb1")
    robot = json.loads(node.state_publisher.messages[-1].data)["robots"][0]
    assert math.isclose(record.source_stamp, 1.9)
    assert record.received_stamp == 2.0
    assert robot["tf_validity_stamp"] == 2.1
    assert robot["valid"] is True
    actual = node.tf_publishers["tb1"].messages[-1].transforms[0]
    assert actual.header.stamp.sec == 2
    assert actual.header.stamp.nanosec == 100000000


def test_actual_future_tf_source_remains_buffered_even_with_declared_validity_lead():
    node = bridge()
    node.tf_validity_lead_sec = 0.2
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 2
    odometry.pose.pose.orientation.w = 1.0
    transform.header.frame_id = "map"
    transform.child_frame_id = "odom"
    transform.header.stamp.sec = 2
    transform.header.stamp.nanosec = 300000000
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    IdealInformation.receive_local_tf(node, "tb1", TFMessage(transforms=[transform]))
    IdealInformation.publish_states(node)
    assert node.received.get("state", "tb1") is None
    assert len(node.pending_transforms["tb1"]) == 1
    node.now = lambda: 2.15
    IdealInformation.publish_states(node)
    record = node.received.get("state", "tb1")
    assert math.isclose(record.payload["tf_source_stamp"], 2.1)
    assert record.received_stamp == 2.15


def test_tf_source_lead_reveals_stale_source_despite_fresh_validity_header():
    node = bridge()
    node.tf_validity_lead_sec = 0.2
    node.now = lambda: 2.4
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 2
    odometry.pose.pose.orientation.w = 1.0
    transform.header.stamp.sec = 2
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    node.local_transforms["tb1"] = transform
    IdealInformation.publish_states(node)
    robot = json.loads(node.state_publisher.messages[-1].data)["robots"][0]
    assert robot["source_stamp"] == 1.8
    assert robot["valid"] is False


def test_future_tf_is_retained_and_promoted_without_newer_future_tf_starvation():
    node = bridge()
    transforms = []
    for stamp in (2, 3, 4):
        transform = TransformStamped()
        transform.header.frame_id = "map"
        transform.child_frame_id = "odom"
        transform.header.stamp.sec = stamp
        transform.transform.rotation.w = 1.0
        transforms.append(transform)
    IdealInformation.receive_local_tf(node, "tb1", TFMessage(transforms=transforms))
    node.promote_transforms(1.9)
    assert "tb1" not in node.local_transforms
    node.promote_transforms(3.0)
    assert node.local_transforms["tb1"].header.stamp.sec == 3
    assert [item.header.stamp.sec for item in node.pending_transforms["tb1"]] == [4]


def test_hub_map_and_navigation_map_use_explicit_delivered_snapshot(monkeypatch):
    node = bridge()
    node.local_maps = {"tb1": grid([0, -1, 0]), "tb2": grid([-1, 100, -1])}
    node.local_map_versions = {"tb1": 1, "tb2": 1}
    assert node.received.get("map", "tb1") is None
    IdealInformation.publish_maps(node)
    assert list(node.map_publisher.messages[-1].data) == [0, 100, 0]
    assert node.map_version == 1
    assert node.map_payload_sha256 == map_digest(node.map_publisher.messages[-1])
    assert list(node.received_map_publishers["tb1"].messages[-1].data) == [0, -1, 0]
    assert list(node.received_map_publishers["tb2"].messages[-1].data) == [-1, 100, -1]
    assert not node.received_map_publishers["tb3"].messages
    # Local known cells govern that robot; only its unknown uses delivery.
    # The global hub and other robots still retain the actually delivered data.
    node.local_maps["tb1"] = grid([100, 0, -1], stamp=2)
    node.local_map_versions["tb1"] = 2
    node.now = lambda: 3.0
    monkeypatch.setattr(node.transport, "deliver", lambda *args, **kwargs: ())
    IdealInformation.publish_maps(node)
    assert list(node.navigation_publishers["tb1"].messages[-1].data) == [100, 0, 0]
    assert list(node.navigation_publishers["tb3"].messages[-1].data) == [0, 100, 0]
    assert list(node.received.get("map", "tb1").payload["data"]) == [0, -1, 0]
    bundle = json.loads(node.map_metadata_publisher.messages[-1].data)
    source = bundle["navigation_sources"]["tb1"]
    assert source["payload_sha256"] == map_digest(node.navigation_publishers["tb1"].messages[-1])
    assert source["input_own_map_payload_sha256"] == map_digest(node.local_maps["tb1"])
    assert source["input_shared_map_payload_sha256"] == node.map_payload_sha256
    assert source["composition_version"] == bundle["navigation_composition"]["version"]


def test_state_delivery_continues_while_map_encoding_is_pending_with_honest_receipts():
    node = bridge()
    node.map_executor = ControlledExecutor()
    node.local_maps = {"tb1": grid([0, -1, 100])}
    node.local_map_versions = {"tb1": 1}
    IdealInformation.publish_maps(node)
    assert not node.map_future.done()
    assert node.received.get("map", "tb1").received_stamp == 2.0
    assert node.hub_map is None
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = transform.header.stamp.sec = 2
    odometry.pose.pose.orientation.w = transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    node.local_transforms["tb1"] = transform
    for now in (2.0, 2.1):
        node.now = lambda now=now: now
        IdealInformation.publish_states(node)
        node.finish_maps()
    assert len(node.state_publisher.messages) == 2
    state = json.loads(node.state_publisher.messages[-1].data)
    assert state["robots"][0]["received_stamp"] == 2.1
    assert state["robots"][0]["source_stamp"] == 2.0
    assert state["robots"][0]["valid"] is True
    assert state["information_diagnostics"]["pending"] is True
    assert state["map_sources"] == {}
    node.map_executor.complete_next()
    node.now = lambda: 3.0
    node.finish_maps()
    assert node.hub_map.header.stamp.sec == 1
    assert node.hub_map_received_stamp == 2.0
    assert node.edges["tb1"].get("shared_map", "hub").received_stamp == 3.0
    assert node.edges["tb1"].get("shared_map", "hub").source_stamp == 1.0
    assert node.map_diagnostics["completed"] == 1


def test_map_worker_has_only_one_running_and_one_latest_detached_job():
    node = bridge()
    node.map_executor = ControlledExecutor()
    node.local_maps = {"tb1": grid([0, -1])}
    node.local_map_versions = {"tb1": 1}
    IdealInformation.publish_maps(node)
    for stamp, value in ((2, 50), (3, 100)):
        node.local_maps["tb1"] = grid([value, -1], stamp=stamp)
        node.local_map_versions["tb1"] += 1
        node.now = lambda stamp=stamp: stamp + 1.0
        IdealInformation.publish_maps(node)
    assert len(node.map_executor.jobs) == 1
    assert node.map_diagnostics["replaced_queued"] == 1
    node.map_executor.complete_next()
    node.now = lambda: 4.5
    node.finish_maps()
    assert list(node.hub_map.data) == [0, -1]
    assert node.published_map_records["tb1"].received_stamp == 2.0
    assert len(node.map_executor.jobs) == 1
    node.map_executor.complete_next()
    node.now = lambda: 4.6
    node.finish_maps()
    assert list(node.hub_map.data) == [100, -1]
    assert node.hub_map.header.stamp.sec == 3
    assert node.published_map_records["tb1"].received_stamp == 4.0
    assert node.map_diagnostics["completed"] == 2


def test_raw_map_callback_only_admits_and_caches_without_synchronous_fusion(monkeypatch):
    node = bridge()
    monkeypatch.setattr("multi_robot_exploration.mr3_information.merge_maps",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("raw callback must not fuse maps")))
    original = grid([0, -1, 100])
    IdealInformation.receive_local_map(node, "tb1", original)
    assert node.local_maps["tb1"] == original
    assert not node.navigation_publishers["tb1"].messages
    original.data[0] = 100
    assert node.local_maps["tb1"].data[0] == 0


def test_undelivered_new_peer_map_cannot_refresh_hub_or_other_navigation_map(monkeypatch):
    node = bridge()
    node.local_maps = {"tb1": grid([0, -1, 0]), "tb2": grid([-1, 100, -1])}
    node.local_map_versions = {"tb1": 1, "tb2": 1}
    IdealInformation.publish_maps(node)
    # Change a raw peer source but withhold the explicit uplink delivery. The
    # ideal bridge still builds the hub and tb1 navigation map from old delivery.
    node.local_maps["tb2"] = grid([100, 100, 100], stamp=2)
    node.local_map_versions["tb2"] = 2
    node.now = lambda: 3.0
    monkeypatch.setattr(node.transport, "deliver", lambda *args, **kwargs: ())
    IdealInformation.publish_maps(node)
    node.publish_navigation_map("tb1")
    assert list(node.map_publisher.messages[-1].data) == [0, 100, 0]
    assert list(node.navigation_publishers["tb1"].messages[-1].data) == [0, 100, 0]
    assert node.received.get("map", "tb2").received_stamp == 2.0
    assert node.received.get("map", "tb2").source_stamp == 1.0
    assert node.hub_map_received_stamp == 2.0
    received_local = node.received_map_publishers["tb2"].messages[-1]
    assert list(received_local.data) == [-1, 100, -1]
    assert received_local.header.stamp.sec == 1
    assert node.received_map_digests["tb2"] == map_digest(received_local)
    IdealInformation.publish_states(node)
    state = json.loads(node.state_publisher.messages[-1].data)
    assert state["map_sources"]["tb2"]["payload_sha256"] == map_digest(received_local)


def test_received_local_map_metadata_digest_matches_exact_source_message():
    node = bridge()
    node.local_maps = {"tb1": grid([0, -1, 100], origin=0.15)}
    node.local_map_versions = {"tb1": 1}
    IdealInformation.publish_maps(node)
    IdealInformation.publish_states(node)
    state = json.loads(node.state_publisher.messages[-1].data)
    output = node.received_map_publishers["tb1"].messages[-1]
    assert output == node.local_maps["tb1"]
    assert state["map_sources"]["tb1"]["payload_sha256"] == map_digest(output)
    assert state["map_sources"]["tb1"]["source_stamp"] == 1.0
    assert state["map_sources"]["tb1"]["received_stamp"] == 2.0


def test_repeat_maps_do_not_refresh_source_time_or_content_version():
    node = bridge()
    node.local_maps = {"tb1": grid([0, -1])}
    node.local_map_versions = {"tb1": 1}
    IdealInformation.publish_maps(node)
    node.now = lambda: 3.0
    IdealInformation.publish_maps(node)
    assert node.map_version == 1
    assert node.hub_map_source_stamp == 1.0
    assert node.hub_map_received_stamp == 3.0
    assert node.edges["tb2"].get("shared_map", "hub").source_stamp == 1.0
    assert node.map_publisher.messages[-1].header.stamp.sec == 1


def test_state_republication_preserves_source_and_marks_stale_invalid():
    node = bridge()
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 1
    odometry.pose.pose.orientation.w = 1.0
    transform.header.stamp.sec = 1
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    node.local_transforms["tb1"] = transform
    IdealInformation.publish_states(node)
    result = json.loads(node.state_publisher.messages[-1].data)
    robot = result["robots"][0]
    assert robot["source_stamp"] == 1.0
    assert robot["received_stamp"] == 2.0
    assert robot["valid"] is False
    assert node.odom_publishers["tb1"].messages[-1].header.stamp.sec == 1
    assert node.tf_publishers["tb1"].messages[-1].transforms[0].header.stamp.sec == 1
    assert result["robots"][1]["valid"] is False


def test_missing_state_source_does_not_refresh_receive_stamp():
    node = bridge()
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 1
    odometry.pose.pose.orientation.w = 1.0
    transform.header.stamp.sec = 1
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    node.local_transforms["tb1"] = transform
    IdealInformation.publish_states(node)
    node.local_odometry.clear()
    node.now = lambda: 3.0
    IdealInformation.publish_states(node)
    robot = json.loads(node.state_publisher.messages[-1].data)["robots"][0]
    assert (robot["source_stamp"], robot["received_stamp"]) == (1.0, 2.0)
    assert robot["valid"] is False


def test_undelivered_new_peer_pose_cannot_refresh_published_peer_odom_tf(monkeypatch):
    node = bridge()
    odometry, transform = Odometry(), TransformStamped()
    odometry.header.stamp.sec = 1
    odometry.pose.pose.orientation.w = 1.0
    transform.header.stamp.sec = 1
    transform.transform.rotation.w = 1.0
    node.local_odometry["tb1"] = odometry
    node.local_transforms["tb1"] = transform
    IdealInformation.publish_states(node)
    node.local_odometry["tb1"] = Odometry()
    node.local_odometry["tb1"].header.stamp.sec = 3
    node.local_odometry["tb1"].pose.pose.position.x = 99.0
    node.local_odometry["tb1"].pose.pose.orientation.w = 1.0
    node.local_transforms["tb1"] = TransformStamped()
    node.local_transforms["tb1"].header.stamp.sec = 3
    node.local_transforms["tb1"].transform.rotation.w = 1.0
    node.now = lambda: 3.0
    monkeypatch.setattr(node.transport, "deliver", lambda *args, **kwargs: ())
    IdealInformation.publish_states(node)
    peer_odom = node.odom_publishers["tb1"].messages[-1]
    peer_transform = node.tf_publishers["tb1"].messages[-1].transforms[0]
    assert peer_odom.header.stamp.sec == peer_transform.header.stamp.sec == 1
    assert peer_odom.pose.pose.position.x == 0.0
    robot = json.loads(node.state_publisher.messages[-1].data)["robots"][0]
    assert (robot["source_stamp"], robot["received_stamp"]) == (1.0, 2.0)
