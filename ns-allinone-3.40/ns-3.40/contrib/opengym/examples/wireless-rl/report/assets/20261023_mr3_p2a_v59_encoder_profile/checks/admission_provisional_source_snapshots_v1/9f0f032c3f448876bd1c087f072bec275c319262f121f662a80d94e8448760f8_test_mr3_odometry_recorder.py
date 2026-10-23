"""Actual C++ MessageInfo and complete ROS payload CPU tests; no simulator."""

import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
import rclpy
from rosidl_runtime_py.convert import message_to_ordereddict
from std_msgs.msg import Bool
from tf2_msgs.msg import TFMessage


ROS_ROOT = Path(__file__).resolve().parents[3]
EXECUTABLE = ROS_ROOT / "install/multi_robot/lib/multi_robot/mr3_odometry_recorder"


def messages(index):
    odometry = Odometry()
    odometry.header.stamp.sec = 7
    odometry.header.stamp.nanosec = 123456789 + index
    odometry.header.frame_id = "odom"
    odometry.child_frame_id = "base_footprint"
    odometry.pose.pose.position.x = 1.25 + index
    odometry.pose.pose.position.y = -2.75
    odometry.pose.pose.position.z = .0125
    odometry.pose.pose.orientation.x = .1
    odometry.pose.pose.orientation.y = -.2
    odometry.pose.pose.orientation.z = .3
    odometry.pose.pose.orientation.w = .9
    odometry.twist.twist.linear.x = -.03125
    odometry.twist.twist.linear.y = .015625
    odometry.twist.twist.linear.z = -.0001
    odometry.twist.twist.angular.x = -.125
    odometry.twist.twist.angular.y = .25
    odometry.twist.twist.angular.z = .8
    odometry.pose.covariance = [position / 128. for position in range(36)]
    odometry.twist.covariance = [-position / 64. for position in range(36)]
    transform = TransformStamped()
    transform.header = copy.deepcopy(odometry.header)
    transform.child_frame_id = odometry.child_frame_id
    transform.transform.translation.x = odometry.pose.pose.position.x
    transform.transform.translation.y = odometry.pose.pose.position.y
    transform.transform.translation.z = odometry.pose.pose.position.z
    transform.transform.rotation = odometry.pose.pose.orientation
    wheel = TransformStamped()
    wheel.header = copy.deepcopy(odometry.header)
    wheel.header.frame_id = "base_footprint"
    wheel.child_frame_id = "wheel_left_link"
    wheel.transform.rotation.w = 1.
    return odometry, TFMessage(transforms=[wheel, transform])


def exercise(tmp_path, *, imposter=False):
    output = tmp_path / "receipts.jsonl"
    console = tmp_path / "recorder.log"
    context = Context()
    rclpy.init(context=context, domain_id=232)
    nodes, odometry_publishers, tf_publishers, expected = [], [], [], {}
    observer = Node("cpu_odometry_receipt_observer", context=context)
    ready = []
    observer.create_subscription(
        Bool, "/mr3/odometry_recorder/ready", lambda message: ready.append(message.data),
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    nodes.append(observer)
    for index, robot in enumerate(("tb1", "tb2", "tb3")):
        name = "imposter" if imposter and index == 2 else "turtlebot3_diff_drive"
        node = Node(name, namespace="/" + robot, context=context)
        nodes.append(node)
        odometry_publishers.append(node.create_publisher(Odometry, "/" + robot + "/odom", 10))
        tf_publishers.append(node.create_publisher(TFMessage, "/" + robot + "/tf", 10))
        expected[robot] = messages(index)
    # A legitimate second TF publisher must not invalidate the driver packet GID.
    slam = Node("slam_toolbox", namespace="/tb1", context=context)
    nodes.append(slam)
    shared_tf = slam.create_publisher(TFMessage, "/tb1/tf", 10)
    other = TransformStamped()
    other.header.frame_id = "map"
    other.child_frame_id = "odom"
    other.transform.rotation.w = 1.
    executor = SingleThreadedExecutor(context=context)
    for node in nodes:
        executor.add_node(node)
    environment = dict(os.environ, ROS_DOMAIN_ID="232")
    command = [str(EXECUTABLE), "--ros-args", "-p", "episode_epoch:=cpu_odometry_receipt",
               "-p", "output_path:=" + str(output), "-p", "use_sim_time:=false"]
    child = None
    with console.open("wb") as stream:
        try:
            child = subprocess.Popen(command, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            deadline = time.monotonic() + 8.
            while time.monotonic() < deadline and not all(
                    publisher.get_subscription_count() for publisher in
                    odometry_publishers + tf_publishers):
                executor.spin_once(timeout_sec=.02)
                assert child.poll() is None, console.read_text()
            assert all(publisher.get_subscription_count() for publisher in
                       odometry_publishers + tf_publishers)
            # Five real streams are insufficient to claim readiness.
            deadline = time.monotonic() + .25
            while time.monotonic() < deadline:
                for index, robot in enumerate(("tb1", "tb2", "tb3")):
                    odometry_publishers[index].publish(expected[robot][0])
                    if index != 2:
                        tf_publishers[index].publish(expected[robot][1])
                shared_tf.publish(TFMessage(transforms=[other]))
                executor.spin_once(timeout_sec=.01)
            assert True not in ready
            deadline = time.monotonic() + (1. if imposter else 5.)
            while time.monotonic() < deadline and (imposter or True not in ready):
                for index, robot in enumerate(("tb1", "tb2", "tb3")):
                    odometry_publishers[index].publish(expected[robot][0])
                    tf_publishers[index].publish(expected[robot][1])
                shared_tf.publish(TFMessage(transforms=[other]))
                executor.spin_once(timeout_sec=.01)
            assert (True in ready) is not imposter
        finally:
            if child is not None and child.poll() is None:
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=10.)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5.)
            executor.shutdown()
            for node in reversed(nodes):
                node.destroy_node()
            context.shutdown()
    assert child is not None and child.returncode == 0, console.read_text()
    return output, expected, command, environment


def test_actual_cpp_messageinfo_full_payload_matches_standard_rosidl_conversion(tmp_path):
    output, expected, command, environment = exercise(tmp_path)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert [row["record_sequence"] for row in rows] == list(range(1, len(rows) + 1))
    config = rows[0]
    assert config["kind"] == "configuration" and config["reliable_queue_depth"] == 1000
    source = ROS_ROOT / "src/multi_robot/src/mr3_odometry_recorder.cpp"
    header = ROS_ROOT / "src/multi_robot/include/multi_robot/mr3_odometry_json.hpp"
    assert config["compiled_source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert config["compiled_odometry_json_sha256"] == hashlib.sha256(header.read_bytes()).hexdigest()
    assert sum(row["kind"] == "ready" for row in rows) == 1
    for robot, (odometry, transforms) in expected.items():
        for kind, message in (("odom", odometry), ("tf", transforms.transforms[1])):
            matches = [row for row in rows if row["kind"] == kind and row["robot"] == robot
                       and row["driver_identity_match"]]
            assert matches
            row = matches[-1]
            assert row["message"] == message_to_ordereddict(message)
            assert row["driver_gid_stable"] and any(bytes.fromhex(row["publisher_gid"]))
            endpoints = row["publisher_graph"]["endpoints"]
            matched = [entry for entry in endpoints if entry["endpoint_gid"] == row["publisher_gid"]]
            assert len(matched) == 1
            assert matched[0]["namespace"] == "/" + robot
            assert matched[0]["node"] == "turtlebot3_diff_drive"
            assert row["source_timestamp"] > 0 and row["received_timestamp"] > 0
            if kind == "tf":
                assert row["tf_message"] == message_to_ordereddict(transforms)
                assert row["transform_index"] == 1
                if robot == "tb1":
                    assert len(endpoints) >= 2
    # A failed second exclusive writer must not alter the actual first receipt bytes.
    before = output.read_bytes()
    repeated = subprocess.run(command, env=environment, capture_output=True, timeout=10.)
    assert repeated.returncode == 1 and output.read_bytes() == before


def test_same_payload_from_a_different_actual_publisher_never_grants_ready(tmp_path):
    output, _, _, _ = exercise(tmp_path, imposter=True)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert not any(row["kind"] == "ready" for row in rows)
    rejected = [row for row in rows if row.get("robot") == "tb3" and row["kind"] in ("odom", "tf")]
    assert rejected and all(not row["driver_identity_match"] for row in rejected)
