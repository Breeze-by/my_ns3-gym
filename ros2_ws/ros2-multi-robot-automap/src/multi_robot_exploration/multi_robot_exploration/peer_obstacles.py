"""Represent observed peer bodies in a dedicated Nav2 obstacle layer."""

import json
import math

from action_msgs.msg import GoalStatus, GoalStatusArray
from nav_msgs.msg import Odometry
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import LaserScan, PointCloud2, PointField
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.control import (
    PEER_BODY_RADIUS_M, peer_safety_radius, quaternion_yaw, transform_point_2d,
)


BEAM_COUNT = 2048
MAX_RANGE_M = 20.0


def body_points(peers):
    """Fill observed (x, y, source_age) peer disks with dense marking points."""
    groups = []
    for x, y, age in peers:
        radius = peer_safety_radius(age)
        offsets = np.arange(-radius, radius + 0.025, 0.025)
        dx, dy = np.meshgrid(offsets, offsets)
        inside = dx * dx + dy * dy <= radius * radius
        groups.append(np.column_stack((x + dx[inside], y + dy[inside], np.zeros(inside.sum()))))
    return np.concatenate(groups).astype("<f4") if groups else np.empty((0, 3), dtype="<f4")


class PeerObstacles(Node):
    def __init__(self):
        super().__init__("peer_obstacles")
        count = self.declare_parameter("robot_count", 3).value
        if not 1 <= count <= 4:
            raise ValueError("robot_count must be between 1 and 4")
        self.names = [f"tb{i}" for i in range(1, count + 1)]
        self.transforms = {}
        self.odometry = {}
        self.mission_started = False
        self.failed = False
        self.publishers_by_robot = {
            name: self.create_publisher(LaserScan, f"/{name}/peer_obstacles", 1)
            for name in self.names
        }
        self.body_publishers = {
            name: self.create_publisher(PointCloud2, f"/{name}/peer_footprints", 1)
            for name in self.names
        }
        self.failure_publisher = self.create_publisher(
            String, "/exploration_failure",
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self.inputs = []
        for name in self.names:
            self.inputs.extend([
                self.create_subscription(
                    Odometry, f"/{name}/odom",
                    lambda msg, name=name: self.odometry.update({name: msg}), 1,
                ),
                self.create_subscription(
                    TFMessage, f"/{name}/tf",
                    lambda msg, name=name: self.receive_tf(msg, name), 20,
                ),
                self.create_subscription(
                    GoalStatusArray, f"/{name}/navigate_to_pose/_action/status",
                    self.receive_status, 10,
                ),
            ])
        self.timer = self.create_timer(0.1, self.publish_obstacles)

    def receive_tf(self, message, name):
        for transform in message.transforms:
            if (
                transform.header.frame_id.lstrip("/") == "map"
                and transform.child_frame_id.lstrip("/") == "odom"
            ):
                self.transforms[name] = transform

    def receive_status(self, message):
        if any(status.status in (
            GoalStatus.STATUS_ACCEPTED, GoalStatus.STATUS_EXECUTING, GoalStatus.STATUS_CANCELING,
        ) for status in message.status_list):
            self.mission_started = True

    def publish_obstacles(self):
        now = self.get_clock().now().nanoseconds / 1e9
        poses = {}
        for name in self.names:
            odometry = self.odometry.get(name)
            transform = self.transforms.get(name)
            if odometry is None or transform is None:
                break
            stamp = odometry.header.stamp.sec + odometry.header.stamp.nanosec / 1e9
            tf_stamp = transform.header.stamp.sec + transform.header.stamp.nanosec / 1e9
            if stamp <= 0 or now - stamp > 0.5 or now - tf_stamp > 0.5:
                break
            position = odometry.pose.pose.position
            x, y = transform_point_2d(position.x, position.y, transform.transform)
            yaw = quaternion_yaw(odometry.pose.pose.orientation) + quaternion_yaw(
                transform.transform.rotation
            )
            if not all(math.isfinite(v) for v in (x, y, yaw)):
                break
            poses[name] = (x, y, yaw, stamp)
        if len(poses) != len(self.names):
            if self.mission_started and not self.failed:
                message = String()
                message.data = json.dumps({
                    "component": "peer_obstacles", "reason": "peer_state_unavailable",
                })
                self.failure_publisher.publish(message)
                self.get_logger().error("Peer odom/TF unavailable; obstacle publication stopped")
                self.failed = True
            return
        if self.failed:
            return
        for index, name in enumerate(self.names):
            x, y, _, _ = poses[name]
            if any(math.hypot(poses[other][0] - x, poses[other][1] - y)
                   < 2 * PEER_BODY_RADIUS_M for other in self.names[index + 1:]):
                message = String()
                message.data = json.dumps({
                    "component": "peer_obstacles", "reason": "peer_body_envelopes_overlap",
                })
                self.failure_publisher.publish(message)
                self.failed = True
                return
        for name, (x, y, yaw, _) in poses.items():
            peers = []
            for other, (px, py, _, stamp) in poses.items():
                if other == name:
                    continue
                dx, dy = px - x, py - y
                peers.append((
                    math.cos(yaw) * dx + math.sin(yaw) * dy,
                    -math.sin(yaw) * dx + math.cos(yaw) * dy,
                    now - stamp,
                ))
            message = LaserScan()
            message.header.frame_id = "base_link"
            message.header.stamp = self.odometry[name].header.stamp
            message.angle_min = -math.pi
            message.angle_increment = 2 * math.pi / BEAM_COUNT
            message.angle_max = message.angle_min + (BEAM_COUNT - 1) * message.angle_increment
            message.range_min = 0.01
            message.range_max = MAX_RANGE_M
            # Clearing is confined to the separate peer layer. Static and real
            # lidar evidence remain in their own max-combined layers.
            message.ranges = [math.inf] * BEAM_COUNT
            self.publishers_by_robot[name].publish(message)
            points = body_points(peers)
            cloud = PointCloud2()
            cloud.header = message.header
            cloud.height = 1
            cloud.width = len(points)
            cloud.fields = [
                PointField(name=field, offset=offset, datatype=PointField.FLOAT32, count=1)
                for field, offset in (("x", 0), ("y", 4), ("z", 8))
            ]
            cloud.point_step = 12
            cloud.row_step = 12 * len(points)
            cloud.is_dense = True
            cloud.data = points.tobytes()
            self.body_publishers[name].publish(cloud)


def main(args=None):
    rclpy.init(args=args)
    node = PeerObstacles()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
