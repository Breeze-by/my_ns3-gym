"""P1B ideal received-information bridge, using estimated robot inputs only.

This single-process ideal mode declares the eventual uplink/downlink information
boundary. It is neither process isolation nor a physical gateway: P3A must prove
that an unavailable delivery cannot be bypassed. Source timestamps are never
refreshed by retransmission, fusion, publication, or navigation-map composition.
The hub uses delivered full local-map snapshots. Each robot navigation map is
the conservative union of its current local map and its last delivered shared
map; occupied evidence wins, and unknown cells are never filled from truth.
Peer messages use the same delivered state snapshots and original odom/TF
headers; the existing 0.5 s peer freshness rule remains authoritative. SLAM's
map-to-odom TF header is a validity timestamp, set to scan time plus the declared
transform_timeout (currently 0.2 s). State metadata therefore exposes both the
unchanged tf_validity_stamp and tf_source_stamp = validity stamp minus that lead.
The combined source stamp is the older of odom time and this actual TF source
time. Source-age checks must use tf_source_stamp, never the forward-dated header.
"""

import copy
import hashlib
import json
import math

from geometry_msgs.msg import TransformStamped
from merge_map.merge_map import merge_maps
from nav_msgs.msg import OccupancyGrid, Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.mr3_transport import (
    IdealTransport, MAP_PERIOD_SEC, ReceivedStore, STATE_PERIOD_SEC,
)


def stamp_seconds(stamp):
    return stamp.sec + stamp.nanosec / 1e9


def stamp_payload(stamp):
    return {"sec": stamp.sec, "nanosec": stamp.nanosec}


def vector_payload(vector):
    return {"x": vector.x, "y": vector.y, "z": vector.z}


def quaternion_payload(quaternion):
    return dict(vector_payload(quaternion), w=quaternion.w)


def pose_payload(pose):
    return {"position": vector_payload(pose.position),
            "orientation": quaternion_payload(pose.orientation)}


def header_payload(header):
    return {"stamp": stamp_payload(header.stamp), "frame_id": header.frame_id}


def map_payload(grid):
    """The entire occupancy snapshot, including its original source header."""
    return {
        "header": header_payload(grid.header),
        "info": {
            "map_load_time": stamp_payload(grid.info.map_load_time),
            "resolution": grid.info.resolution, "width": grid.info.width,
            "height": grid.info.height, "origin": pose_payload(grid.info.origin),
        },
        "data": list(grid.data),
    }


def map_digest(grid):
    """Bind independently published map and metadata to the exact same snapshot."""
    encoded = json.dumps(map_payload(grid), allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def odom_payload(odometry):
    return {
        "header": header_payload(odometry.header),
        "child_frame_id": odometry.child_frame_id,
        "pose": {"pose": pose_payload(odometry.pose.pose),
                 "covariance": list(odometry.pose.covariance)},
        "twist": {
            "twist": {"linear": vector_payload(odometry.twist.twist.linear),
                      "angular": vector_payload(odometry.twist.twist.angular)},
            "covariance": list(odometry.twist.covariance),
        },
    }


def transform_payload(transform):
    return {
        "header": header_payload(transform.header),
        "child_frame_id": transform.child_frame_id,
        "transform": {
            "translation": vector_payload(transform.transform.translation),
            "rotation": quaternion_payload(transform.transform.rotation),
        },
    }


def restore_message(message, payload):
    """Restore nested ROS fields from the explicit JSON-compatible structure."""
    for key, value in payload.items():
        if isinstance(value, dict):
            restore_message(getattr(message, key), value)
        else:
            setattr(message, key, value)
    return message


def yaw(quaternion):
    return math.atan2(2 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
                      1 - 2 * (quaternion.y ** 2 + quaternion.z ** 2))


def state_payload(name, odometry, transform, tf_validity_lead_sec=0.0):
    """Estimated common-frame pose and measured twist, never commanded velocity."""
    lead = float(tf_validity_lead_sec)
    if not math.isfinite(lead) or lead < 0:
        raise ValueError("tf_validity_lead_sec must be finite and nonnegative")
    angle = yaw(transform.transform.rotation)
    position = odometry.pose.pose.position
    translation = transform.transform.translation
    return {
        "robot": name, "name": name,
        "x": translation.x + math.cos(angle) * position.x - math.sin(angle) * position.y,
        "y": translation.y + math.sin(angle) * position.x + math.cos(angle) * position.y,
        "yaw": math.atan2(math.sin(angle + yaw(odometry.pose.pose.orientation)),
                          math.cos(angle + yaw(odometry.pose.pose.orientation))),
        "v": odometry.twist.twist.linear.x,
        "w": odometry.twist.twist.angular.z,
        "odom_source_stamp": stamp_seconds(odometry.header.stamp),
        "tf_source_stamp": stamp_seconds(transform.header.stamp) - lead,
        "tf_validity_stamp": stamp_seconds(transform.header.stamp),
        "tf_validity_lead_sec": lead,
        "odometry": odom_payload(odometry), "transform": transform_payload(transform),
    }


class IdealInformation(Node):
    """Sample raw local inputs, explicitly deliver, then publish received copies."""

    def __init__(self):
        super().__init__("mr3_information")
        if self.declare_parameter("robot_count", 3).value != 3:
            raise ValueError("The MR3 information contract requires exactly three robots")
        self.epoch = self.declare_parameter("episode_epoch", "mr3-p1b").value
        self.tf_validity_lead_sec = float(
            self.declare_parameter("tf_validity_lead_sec", 0.2).value)
        if not math.isfinite(self.tf_validity_lead_sec) or self.tf_validity_lead_sec < 0:
            raise ValueError("tf_validity_lead_sec must be finite and nonnegative")
        self.names = ("tb1", "tb2", "tb3")
        self.transport = IdealTransport(self.epoch)
        self.received = ReceivedStore(self.epoch)
        self.edges = {name: ReceivedStore(self.epoch) for name in self.names}
        self.downlinks = {name: IdealTransport(self.epoch) for name in self.names}
        self.local_maps = {}
        self.local_map_versions = {}
        self.local_odometry = {}
        self.local_transforms = {}
        self.pending_transforms = {name: [] for name in self.names}
        self.map_version = 0
        self.map_signature = None
        self.hub_map = None
        self.map_payload_sha256 = None
        self.hub_map_source_stamp = None
        self.hub_map_received_stamp = None
        self.state_sequence = 0
        self.last_now = None
        self.clock_failed = False
        map_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.map_publisher = self.create_publisher(OccupancyGrid, "/mr3/received/map", map_qos)
        self.state_publisher = self.create_publisher(String, "/mr3/received/states", 1)
        self.navigation_publishers = {
            name: self.create_publisher(OccupancyGrid, f"/{name}/navigation_map", map_qos)
            for name in self.names
        }
        self.odom_publishers = {
            name: self.create_publisher(Odometry, f"/mr3/received/{name}/odom", 1)
            for name in self.names
        }
        self.tf_publishers = {
            name: self.create_publisher(TFMessage, f"/mr3/received/{name}/tf", 20)
            for name in self.names
        }
        self.subscriptions_by_robot = []
        for name in self.names:
            self.subscriptions_by_robot.extend([
                self.create_subscription(OccupancyGrid, f"/{name}/map",
                                         lambda msg, name=name: self.receive_local_map(name, msg),
                                         map_qos),
                self.create_subscription(Odometry, f"/{name}/odom",
                                         lambda msg, name=name: self.receive_local_odom(name, msg),
                                         1),
                self.create_subscription(TFMessage, f"/{name}/tf",
                                         lambda msg, name=name: self.receive_local_tf(name, msg),
                                         20),
            ])
        self.state_timer = self.create_timer(STATE_PERIOD_SEC, self.publish_states)
        self.map_timer = self.create_timer(MAP_PERIOD_SEC, self.publish_maps)

    def now(self):
        now = self.get_clock().now().nanoseconds / 1e9
        if self.last_now is not None and now < self.last_now - 1e-9:
            # P1C owns full reset: a rewind cannot mix old maps and new poses.
            self.clock_failed = True
            self.get_logger().error("Simulation clock rewound; restart with a new episode epoch")
        self.last_now = now
        return None if self.clock_failed or now <= 0 else now

    def receive_local_odom(self, name, message):
        previous = self.local_odometry.get(name)
        if (previous is None
                or stamp_seconds(message.header.stamp) >= stamp_seconds(previous.header.stamp)):
            self.local_odometry[name] = copy.deepcopy(message)

    def receive_local_tf(self, name, message):
        for transform in message.transforms:
            if (transform.header.frame_id.lstrip("/") == "map"
                    and transform.child_frame_id.lstrip("/") == "odom"):
                pending = self.pending_transforms[name]
                stamp = stamp_seconds(transform.header.stamp)
                if pending and stamp <= stamp_seconds(pending[-1].header.stamp):
                    continue
                if len(pending) >= 256:
                    self.clock_failed = True
                    self.get_logger().error("Future TF queue exceeded 256; episode must restart")
                    return
                pending.append(copy.deepcopy(transform))

    def promote_transforms(self, now):
        # SLAM stamps map->odom at scan time + transform_timeout. Keep that
        # original validity stamp, and wait until it is causally available.
        for name, pending in self.pending_transforms.items():
            ready = [item for item in pending if stamp_seconds(item.header.stamp) <= now]
            self.pending_transforms[name] = [
                item for item in pending if stamp_seconds(item.header.stamp) > now]
            if ready:
                newest = max(ready, key=lambda item: stamp_seconds(item.header.stamp))
                previous = self.local_transforms.get(name)
                if (previous is None or stamp_seconds(newest.header.stamp)
                        >= stamp_seconds(previous.header.stamp)):
                    self.local_transforms[name] = newest

    def receive_local_map(self, name, message):
        previous = self.local_maps.get(name)
        if (previous is not None
                and stamp_seconds(message.header.stamp) < stamp_seconds(previous.header.stamp)):
            return
        try:
            # Retain the existing merger's common-frame/resolution/orientation
            # validation, including compatibility with the other robot maps.
            others = [grid for robot, grid in self.local_maps.items() if robot != name]
            merge_maps([message, *others], "map")
        except ValueError as error:
            self.get_logger().error(f"Rejected {name} local map: {error}")
            return
        if previous != message:
            self.local_map_versions[name] = self.local_map_versions.get(name, 0) + 1
        self.local_maps[name] = copy.deepcopy(message)
        self.publish_navigation_map(name)

    def publish_navigation_map(self, name):
        local = self.local_maps.get(name)
        shared = self.edges[name].get("shared_map", "hub")
        maps = ([local] if local is not None else [])
        if shared is not None:
            maps.append(restore_message(OccupancyGrid(), shared.payload))
        if maps:
            self.navigation_publishers[name].publish(merge_maps(maps, "map"))

    def publish_maps(self):
        now = self.now()
        if now is None:
            return
        for name, grid in self.local_maps.items():
            source_stamp = stamp_seconds(grid.header.stamp)
            if source_stamp <= now:
                self.transport.send("map", name, map_payload(grid), source_stamp=source_stamp,
                                    now=now, version=self.local_map_versions[name])
        self.transport.deliver(self.received, now, sampled=True)
        records = [self.received.get("map", name) for name in self.names]
        records = [record for record in records if record is not None]
        if not records:
            return
        signature = tuple((record.source, record.version) for record in records)
        if signature != self.map_signature:
            self.map_version += 1
            self.map_signature = signature
        self.hub_map = merge_maps([
            restore_message(OccupancyGrid(), record.payload) for record in records], "map")
        self.map_payload_sha256 = map_digest(self.hub_map)
        # The oldest contributing source is the conservative freshness summary;
        # every source also remains individually visible in the state metadata.
        self.hub_map_source_stamp = min(record.source_stamp for record in records)
        self.hub_map_received_stamp = max(record.received_stamp for record in records)
        self.map_publisher.publish(self.hub_map)
        for name in self.names:
            self.downlinks[name].send(
                "shared_map", "hub", map_payload(self.hub_map),
                source_stamp=self.hub_map_source_stamp, now=now, version=self.map_version)
            self.downlinks[name].deliver(self.edges[name], now, sampled=True)
            self.publish_navigation_map(name)

    def publish_states(self):
        now = self.now()
        if now is None:
            return
        self.promote_transforms(now)
        for name in self.names:
            odometry = self.local_odometry.get(name)
            transform = self.local_transforms.get(name)
            if odometry is None or transform is None:
                continue
            stamps = (stamp_seconds(odometry.header.stamp),
                      stamp_seconds(transform.header.stamp) - self.tf_validity_lead_sec)
            source_stamp = min(stamps)
            if source_stamp < 0 or max(stamps) > now:
                continue
            payload = state_payload(name, odometry, transform, self.tf_validity_lead_sec)
            if not all(math.isfinite(payload[field]) for field in ("x", "y", "yaw", "v", "w")):
                continue
            self.transport.send("state", name, payload, source_stamp=source_stamp, now=now)
        self.transport.deliver(self.received, now, sampled=True)
        robots = []
        for name in self.names:
            record = self.received.get("state", name)
            if record is None:
                robots.append({"robot": name, "name": name, "valid": False,
                               "x": 0.0, "y": 0.0, "yaw": 0.0, "v": 0.0, "w": 0.0,
                               "epoch": self.epoch, "sequence": 0, "version": 0,
                               "source_stamp": None, "received_stamp": None})
                continue
            payload = record.payload
            odometry = restore_message(Odometry(), payload.pop("odometry"))
            transform = restore_message(TransformStamped(), payload.pop("transform"))
            # An ideal broadcast delivery; no raw odom or TF is published here.
            # Future edge isolation and faulted fanout are P3A/P3B gates.
            self.odom_publishers[name].publish(odometry)
            self.tf_publishers[name].publish(TFMessage(transforms=[transform]))
            payload.update({
                "epoch": self.epoch, "sequence": record.sequence, "version": record.version,
                "source_stamp": record.source_stamp, "received_stamp": record.received_stamp,
                "valid": (record.source_stamp > 0
                          and 0 <= now - record.source_stamp <= 0.5),
            })
            robots.append(payload)
        self.state_sequence += 1
        maps = {name: self.received.get("map", name) for name in self.names}
        message = String()
        message.data = json.dumps({
            "epoch": self.epoch, "sequence": self.state_sequence, "robots": robots,
            "map_version": self.map_version,
            "map_source_stamp": self.hub_map_source_stamp,
            "map_received_stamp": self.hub_map_received_stamp,
            "map_sources": {
                name: {"sequence": record.sequence, "version": record.version,
                       "source_stamp": record.source_stamp,
                       "received_stamp": record.received_stamp}
                for name, record in maps.items() if record is not None
            },
            "map_payload_sha256": self.map_payload_sha256,
        }, allow_nan=False, sort_keys=True)
        self.state_publisher.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = IdealInformation()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
