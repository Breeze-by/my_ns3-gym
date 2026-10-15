"""Native ROS message fixtures for the ideal bridge; no simulator is launched."""

import json
import math
from types import MethodType, SimpleNamespace

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.mr3_information import (
    IdealInformation, map_digest, map_payload, restore_message, state_payload,
)
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


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
        pending_transforms={name: [] for name in names},
        transport=IdealTransport("episode-a"), received=ReceivedStore("episode-a"),
        edges={name: ReceivedStore("episode-a") for name in names},
        downlinks={name: IdealTransport("episode-a") for name in names},
        navigation_publishers={name: Publisher() for name in names},
        received_map_publishers={name: Publisher() for name in names},
        received_map_digests={},
        odom_publishers={name: Publisher() for name in names},
        tf_publishers={name: Publisher() for name in names},
        map_publisher=Publisher(), state_publisher=Publisher(), map_signature=None,
        hub_map=None, map_payload_sha256=None, map_version=0, state_sequence=0,
        hub_map_source_stamp=None, hub_map_received_stamp=None,
    )
    node.publish_navigation_map = MethodType(IdealInformation.publish_navigation_map, node)
    node.promote_transforms = MethodType(IdealInformation.promote_transforms, node)
    return node


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


def test_hub_map_and_navigation_map_use_explicit_delivered_snapshot():
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
    # Local changes can help that robot before the next uplink; shared occupied
    # evidence still wins the local free conflict. Other robots retain delivery.
    node.local_maps["tb1"] = grid([100, 0, -1], stamp=2)
    node.publish_navigation_map("tb1")
    assert list(node.navigation_publishers["tb1"].messages[-1].data) == [100, 100, 0]
    assert list(node.navigation_publishers["tb3"].messages[-1].data) == [0, 100, 0]
    assert list(node.received.get("map", "tb1").payload["data"]) == [0, -1, 0]


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
