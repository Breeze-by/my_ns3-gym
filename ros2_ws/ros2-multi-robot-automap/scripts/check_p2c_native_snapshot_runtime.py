#!/usr/bin/env python3
"""Actual native DDS with a blocked state group and mixed TF; no robots."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import battery_manager as b

REFERENCE = '4712c019080ed461a7968fc4e1ef53ba57bf2903'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/battery_manager.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():parser.error('do not overwrite native runtime evidence')
    original = b.BatteryManager.apply_native_frame
    frames = []
    def record(self, message, source):
        frames.append(source)
        return original(self, message, source)
    b.BatteryManager.apply_native_frame = record
    rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=true', '-p', 'robot_name:=tb1',
                     '-p', 'frame_stamp_offset_sec:=0.2'])
    native = injector = baseline = None
    executor = MultiThreadedExecutor(num_threads=2)
    released = threading.Event(); entered = threading.Event()
    worker = None
    try:
        native = b.BatteryManager(); native.timer.cancel()
        injector = Node('p2c_native_mixed_tf_injector')
        baseline = Node('p2c_blocked_native_tf_reference')
        executor.add_node(native)
        def run():
            try:executor.spin()
            except ExternalShutdownException:pass
        worker = threading.Thread(target=run); worker.start()
        def until(predicate):
            deadline = time.monotonic()+10.
            while not predicate() and time.monotonic()<deadline:time.sleep(.01)
            assert predicate(), 'isolated native DDS deadline'
        clock = injector.create_publisher(Clock, '/clock', 10)
        def advance(stamp):
            message = Clock(); message.clock.sec = stamp
            clock.publish(message); until(lambda:native.now() == stamp)
        topics = ['/tb1/tf', '/tb1/gateway/merge_map', '/tb1/odom']
        types = [TFMessage, OccupancyGrid, Odometry]
        historical = dict(tf20=[], tf1=[], fused=[], odom=[])
        def old_tf(message, key):
            historical[key].extend((t.header.frame_id, t.header.stamp.sec) for t in message.transforms)
        baseline.create_subscription(TFMessage, topics[0], lambda m:old_tf(m,'tf20'),20)
        baseline.create_subscription(TFMessage, topics[0], lambda m:old_tf(m,'tf1'),1)
        for key, topic, message_type in zip(('fused','odom'),topics[1:],types[1:]):
            baseline.create_subscription(message_type,topic,
                lambda m,key=key:historical[key].append(m.header.stamp.sec),10)
        publishers = [injector.create_publisher(t,topic,100) for t,topic in zip(types,topics)]
        until(lambda:[p.get_subscription_count() for p in publishers] == [3,2,2])
        advance(50)
        def block():
            entered.set()
            assert released.wait(10.), 'synthetic state-group block deadline'
        blocker = native.create_guard_condition(block)
        blocker.trigger()
        assert entered.wait(10.)
        def transform(stamp, translation, relevant=True):
            value = TransformStamped(); value.header.stamp.sec = stamp
            value.header.stamp.nanosec = 200000000
            value.header.frame_id = 'tb1/map' if relevant else 'tb1/odom'
            value.child_frame_id = 'tb1/odom' if relevant else 'tb1/base_footprint'
            value.transform.rotation.w = 1.; value.transform.translation.x = translation
            return TFMessage(transforms=[value])
        def grid(stamp):
            value = OccupancyGrid(); value.header.stamp.sec = stamp
            value.info.width = value.info.height = 100; value.info.resolution = .1
            value.info.origin.position.x = value.info.origin.position.y = -5.
            value.data = [0]*10000
            return value
        def odom(stamp,x):
            value = Odometry(); value.header.stamp.sec = stamp
            value.pose.pose.position.x = x; value.pose.pose.orientation.w = 1.
            return value
        for stamp in range(1,51):
            publishers[0].publish(transform(stamp,1.))
            publishers[0].publish(transform(stamp,99.,False))
            publishers[1].publish(grid(stamp)); publishers[2].publish(odom(stamp,stamp*.01))
            time.sleep(.02)
        for _ in range(30):
            publishers[0].publish(transform(50,99.,False)); time.sleep(.01)
        until(lambda:50. in native.native_frame_inbox)
        assert native.map_tf_source_time is None and native.last_odom_time is None
        assert len(native.native_frame_inbox)==1 and native.energy==native.initial_energy
        captured = dict(source=next(iter(native.native_frame_inbox)),
            relevant_receipts=native.native_frame_receipts, state_group_blocked=True,
            state_and_meter_unchanged=True)
        time.sleep(.2); released.set(); executor.add_node(baseline)
        until(lambda:native.map_tf_source_time==native.last_odom_time==native.return_map_source_time==50.
              and all(historical.values()))
        relevant_old = {k:[stamp for parent,stamp in historical[k] if parent=='tb1/map']
                        for k in ('tf20','tf1')}
        assert relevant_old==dict(tf20=[],tf1=[]),relevant_old
        assert historical['fused'][0]==historical['odom'][0]==41
        assert frames[0]==50.
        depths={s.topic_name:s.qos_profile.depth for s in native.subscriptions if s.topic_name in topics}
        assert depths==dict(zip(topics,(20,1,10)))
        assert abs(native.total_motion_distance-.09)<1e-8 and native.total_energy_elapsed==9.
        advance(53)
        publishers[1].publish(grid(53)); publishers[2].publish(odom(53,.5))
        publishers[0].publish(transform(53,99.,False))
        until(lambda:native.last_odom_time==native.return_map_source_time==53.)
        assert native.map_tf_source_time==50. and native.pose_source_age() is None
        assert native.current_return_budget() is None
        publishers[0].publish(transform(60,99.)); time.sleep(.2)
        assert native.map_tf_source_time==50. and not native.pending_native_inputs and not native.native_frame_inbox
        energy=native.energy
        publishers[0].publish(transform(53,2.)); until(lambda:native.map_tf_source_time==53.)
        assert native.map_position==(2.5,0.) and native.last_odom_time==53.
        assert native.energy==energy and native.total_energy_elapsed==12.
        assert abs(native.energy-(native.initial_energy-.09-12.*native.idle_cost))<1e-8
        assert native.current_return_budget() is not None
        source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE])
        result=dict(status='PASS',scope='Actual two-thread native DDS, default state group blocked, mixed body/relevant TF, original source stamps; task timer canceled, no Gazebo/Wi-Fi',
            reference_commit=REFERENCE,reference_battery_sha256=hashlib.sha256(source).hexdigest(),
            current_battery_sha256=hashlib.sha256(Path(b.__file__).read_bytes()).hexdigest(),
            native_subscription_depths=depths,blocked_state_group_ingress=captured,
            first_applied_frame_source=frames[0],blocked_historical_relevant_tf=relevant_old,
            first_historical_fused=historical['fused'][0],first_historical_odom=historical['odom'][0],
            original_odom_queue_preserved=True,stale_frame_budget_unavailable=True,
            irrelevant_tf_did_not_renew=True,far_future_rejected_without_poisoning=True,
            distance_meter_m=native.total_motion_distance,elapsed_meter_sec=native.total_energy_elapsed,
            energy_balance=native.energy,tf_only_reprojection=(2.5,0.))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))
    finally:
        released.set(); executor.shutdown()
        if worker is not None:worker.join(timeout=5.);assert not worker.is_alive()
        for node in (native,injector,baseline):
            if node is not None:node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
        b.BatteryManager.apply_native_frame=original


if __name__=='__main__':main()
