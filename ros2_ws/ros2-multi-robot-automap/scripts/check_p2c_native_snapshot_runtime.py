#!/usr/bin/env python3
"""Actual native DDS snapshot/lease probe; synthetic inputs, no robots."""
import argparse
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
from rosgraph_msgs.msg import Clock
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import battery_manager as b

REFERENCE = '1a30fc76c8a583b1547fbcbf01a980011e8cdaaf'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/battery_manager.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('do not overwrite native runtime evidence')
    original = b.BatteryManager.tf_callback
    frames = []
    def record(self, message):
        for transform in message.transforms:
            if transform.header.frame_id == 'tb1/map':
                stamp = transform.header.stamp
                frames.append(stamp.sec+stamp.nanosec/1e9-self.frame_stamp_offset)
        return original(self, message)
    b.BatteryManager.tf_callback = record
    rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=true', '-p', 'robot_name:=tb1',
                     '-p', 'frame_stamp_offset_sec:=0.2'])
    native = injector = baseline = None
    executor = SingleThreadedExecutor()
    try:
        native = b.BatteryManager()
        native.timer.cancel()  # Isolate DDS/lease/meter behavior, no task ticks.
        injector = Node('p2c_native_snapshot_injector')
        baseline = Node('p2c_v14_native_snapshot_reference')
        for node in (native, injector, baseline):
            executor.add_node(node)
        clock = injector.create_publisher(Clock, '/clock', 10)
        def advance(stamp):
            message = Clock(); message.clock.sec = stamp
            clock.publish(message)
            until(lambda:native.now() == stamp)
        def until(predicate):
            deadline = time.monotonic()+10.
            while not predicate() and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=.01)
            assert predicate(), 'isolated native DDS deadline'
        topics = ['/tb1/tf', '/tb1/gateway/merge_map', '/tb1/odom']
        types = [TFMessage, OccupancyGrid, Odometry]
        historical = dict(tf=[], fused=[], odom=[])
        subscriptions = []
        publishers = []
        for key, topic, message_type, depth in zip(historical, topics, types, (20,10,10)):
            def old(message, key=key):
                header = message.transforms[0].header if key == 'tf' else message.header
                historical[key].append(header.stamp.sec)
            subscriptions.append(baseline.create_subscription(message_type, topic, old, depth))
            publishers.append(injector.create_publisher(message_type, topic, 100))
        deadline = time.monotonic()+10.
        while not all(p.get_subscription_count() == 2 for p in publishers) and time.monotonic() < deadline:
            time.sleep(.02)
        assert all(p.get_subscription_count() == 2 for p in publishers)
        time.sleep(.2)
        advance(50)
        def transform(stamp, translation, relevant=True):
            value = TransformStamped()
            value.header.stamp.sec = stamp
            value.header.stamp.nanosec = 200000000
            value.header.frame_id = 'tb1/map' if relevant else 'tb1/odom'
            value.child_frame_id = 'tb1/odom' if relevant else 'tb1/base_footprint'
            value.transform.rotation.w = 1.
            value.transform.translation.x = translation
            return TFMessage(transforms=[value])
        def grid(stamp):
            value = OccupancyGrid(); value.header.stamp.sec = stamp
            value.info.width = value.info.height = 100; value.info.resolution = .1
            value.info.origin.position.x = value.info.origin.position.y = -5.
            value.data = [0]*10000
            return value
        def odom(stamp, x):
            value = Odometry(); value.header.stamp.sec = stamp
            value.pose.pose.position.x = x; value.pose.pose.orientation.w = 1.
            return value
        for stamp in range(1,51):
            for publisher, message in zip(publishers,
                    (transform(stamp,1.), grid(stamp), odom(stamp,stamp*.01))):
                publisher.publish(message)
            time.sleep(.02)
        time.sleep(.3)
        until(lambda: native.last_odom_time == native.map_tf_source_time == native.return_map_source_time == 50.
              and all(historical.values()))
        depths = {s.topic_name:s.qos_profile.depth for s in native.subscriptions if s.topic_name in topics}
        assert depths == dict(zip(topics,(1,1,10)))
        assert {k:v[0] for k,v in historical.items()} == dict(tf=31,fused=41,odom=41)
        assert frames[0] == 50.
        assert abs(native.total_motion_distance-.09) < 1e-8 and native.total_energy_elapsed == 9.
        first = dict(frame=native.map_tf_source_time, fused=native.return_map_source_time, odom=native.last_odom_time)
        advance(53)
        publishers[1].publish(grid(53)); publishers[2].publish(odom(53,.5))
        publishers[0].publish(transform(53,99.,False))
        until(lambda:native.last_odom_time == native.return_map_source_time == 53.)
        assert native.map_tf_source_time == 50. and native.pose_source_age() is None
        assert native.current_return_budget() is None
        publishers[0].publish(transform(60,99.))
        until(lambda: frames[-1] == 60.)
        assert native.map_tf_source_time == 50. and native.current_return_budget() is None
        energy = native.energy
        publishers[0].publish(transform(53,2.))
        until(lambda:native.map_tf_source_time == 53.)
        assert native.map_position == (2.5,0.) and native.last_odom_time == 53.
        assert native.energy == energy and native.total_energy_elapsed == 12.
        assert abs(native.energy-(native.initial_energy-.09-12.*native.idle_cost)) < 1e-8
        assert native.current_return_budget() is not None
        source = subprocess.check_output(['git','show',REFERENCE+':'+SOURCE])
        result = dict(status='PASS', scope='Actual native DDS with50 source-stamped snapshots and frozen synthetic clock; timer canceled, no task or physical/Wi-Fi measurement',
            reference_commit=REFERENCE, reference_battery_sha256=hashlib.sha256(source).hexdigest(),
            current_battery_sha256=hashlib.sha256(Path(b.__file__).read_bytes()).hexdigest(),
            native_subscription_depths=depths, first_historical_callbacks={k:v[0] for k,v in historical.items()},
            first_native_leases=first, original_odom_queue_preserved=True,
            irrelevant_tf_did_not_renew=True, stale_frame_budget_unavailable=True,
            far_future_tf_rejected_without_poisoning=True, tf_only_reprojection=(2.5,0.),
            distance_meter_m=native.total_motion_distance, elapsed_meter_sec=native.total_energy_elapsed,
            energy_balance=native.energy, source_timestamps_preserved=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))
    finally:
        executor.shutdown()
        for node in (native, injector, baseline):
            if node is not None: node.destroy_node()
        rclpy.shutdown()
        b.BatteryManager.tf_callback = original


if __name__ == '__main__':
    main()
