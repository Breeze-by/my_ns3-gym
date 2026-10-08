#!/usr/bin/env python3
"""Actual DDS backlog probe on the coordinator; synthetic snapshots, no robots."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import time

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as c

REFERENCE = '4de14884ff93d3c43aed22f60d4a16f4d9a3bb85'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('do not overwrite runtime evidence')
    old_source = subprocess.check_output(['git', 'show', REFERENCE+':'+SOURCE], text=True)
    old_depths = {}
    for node in ast.walk(ast.parse(old_source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'create_subscription':
            topic = ast.unparse(node.args[1])
            if isinstance(node.args[-1], ast.Constant) and any(s in topic for s in ('/merge_map', '/odom', '/tf', '/map')):
                old_depths[topic] = node.args[-1].value
    assert sorted(old_depths.values()) == [10, 10, 10, 20]
    received = {key: [] for key in ('fused', 'odom', 'tf', 'local')}
    methods = ('map_callback', 'robot_odom_callback', 'robot_tf_callback', 'robot_map_callback')
    original = {name: getattr(c.HeadquartersControl, name) for name in methods}
    for key, name in zip(received, methods):
        def record(self, message, *positional, key=key, function=original[name]):
            header = message.transforms[0].header if key == 'tf' else message.header
            received[key].append(header.stamp.sec)
            return function(self, message, *positional)
        setattr(c.HeadquartersControl, name, record)
    rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=true', '-p', 'robot_count:=1',
                     '-p', 'auto_save_map:=false'])
    coordinator = injector = baseline = None
    executor = SingleThreadedExecutor()
    try:
        coordinator = c.HeadquartersControl()
        injector = Node('p2c_snapshot_injector')
        baseline = Node('p2c_v12_backlog_reference')
        topics = ['/merge_map', '/gateway/received/tb1/odom',
                  '/gateway/received/tb1/tf', '/gateway/received/tb1/map']
        types = [OccupancyGrid, Odometry, TFMessage, OccupancyGrid]
        historical = {key: [] for key in received}
        publishers = []
        subscriptions = []
        for key, topic, message_type, depth in zip(received, topics, types, (10, 10, 20, 10)):
            def record_old(message, key=key):
                header = message.transforms[0].header if key == 'tf' else message.header
                historical[key].append(header.stamp.sec)
            subscriptions.append(baseline.create_subscription(message_type, topic, record_old, depth))
            publishers.append(injector.create_publisher(message_type, topic, 100))
        for node in (coordinator, injector, baseline):
            executor.add_node(node)
        deadline = time.monotonic()+10
        while not all(p.get_subscription_count() == 2 for p in publishers) and time.monotonic() < deadline:
            time.sleep(.02)
        assert all(p.get_subscription_count() == 2 for p in publishers), 'isolated DDS discovery failed'
        # DDS receives during the blocked application executor, as during a
        # synchronous planning call. Original source stamps are never renewed.
        for stamp in range(1, 51):
            grid = OccupancyGrid()
            grid.header.stamp.sec = stamp
            grid.info.width = grid.info.height = 2
            grid.info.resolution = .1
            grid.data = [0]*4
            odom = Odometry()
            odom.header.stamp.sec = stamp
            odom.pose.pose.orientation.w = 1.
            transform = TransformStamped()
            transform.header.stamp.sec = stamp
            transform.header.frame_id = 'tb1/map'
            transform.child_frame_id = 'tb1/odom'
            transform.transform.rotation.w = 1.
            transform.transform.translation.x = 1.
            for publisher, message in zip(publishers, (grid, odom, TFMessage(transforms=[transform]), grid)):
                publisher.publish(message)
            time.sleep(.02)
        time.sleep(.3)
        actual_depths = {s.topic_name: s.qos_profile.depth for s in coordinator.subscriptions if s.topic_name in topics}
        assert set(actual_depths.values()) == {1} and len(actual_depths) == 4
        deadline = time.monotonic()+10
        while not all(received[k] and historical[k] for k in received) and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.01)
        assert {k: v[0] for k, v in received.items()} == dict.fromkeys(received, 50), received
        assert {k: v[0] for k, v in historical.items()} == dict(fused=41, odom=41, tf=31, local=41), historical
        leases = dict(fused=coordinator.map_received_at, odom=coordinator.robot_odom_received_at['tb1'],
                      tf=coordinator.robot_tf_received_at['tb1'], local=coordinator.robot_map_received_at['tb1'])
        assert set(leases.values()) == {50.} and coordinator.now() == 0.
        assert coordinator.robot_positions['tb1'] == (1., 0.)
        transform.header.stamp.sec = 60
        transform.transform.translation.x = 2.
        publishers[2].publish(TFMessage(transforms=[transform]))
        deadline = time.monotonic()+5
        while coordinator.robot_tf_received_at['tb1'] != 60. and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.01)
        assert coordinator.robot_positions['tb1'] == (2., 0.)
        assert coordinator.robot_odom_received_at['tb1'] == 50.
        assert coordinator.robot_tf_received_at['tb1'] == 60.
        result = dict(status='PASS', scope='Actual ROS DDS with a blocked coordinator executor; synthetic messages, no task or Wi-Fi measurement',
                      reference_commit=REFERENCE, reference_control_sha256=hashlib.sha256(old_source.encode()).hexdigest(),
                      current_control_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
                      old_subscription_depths=old_depths, current_subscription_depths=actual_depths,
                      source_stamps=list(range(1, 51)), first_historical_callbacks={k: v[0] for k, v in historical.items()},
                      first_current_callbacks={k: v[0] for k, v in received.items()}, actual_received_leases=leases,
                      tf_only_update=dict(frame_source_time=coordinator.robot_tf_received_at['tb1'],
                          unchanged_odom_source_time=coordinator.robot_odom_received_at['tb1'],
                          recomputed_position=coordinator.robot_positions['tb1']),
                      frozen_simulation_time=coordinator.now(), source_timestamps_preserved=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result))
    finally:
        executor.shutdown()
        for node in (coordinator, injector, baseline):
            if node is not None:
                node.destroy_node()
        rclpy.shutdown()
        for name, function in original.items():
            setattr(c.HeadquartersControl, name, function)


if __name__ == '__main__':
    main()
