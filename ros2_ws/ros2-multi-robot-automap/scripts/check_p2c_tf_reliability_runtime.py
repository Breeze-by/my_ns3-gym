#!/usr/bin/env python3
"""Actual native DDS compatibility probe; synthetic sensor TF, no Gazebo."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from tf2_msgs.msg import TFMessage
from multi_robot_exploration import battery_manager as b
from multi_robot_exploration.tf_ingress_sampler import TfIngressSampler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite original probe')
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_name:=tb1','-p','frame_stamp_offset_sec:=0.2',
        '-r','battery_manager:/tb1/tf:=/tb1/battery/source_tf'])
    executor=MultiThreadedExecutor(num_threads=2);native=injector=reference=sampler=None;worker=sampler_worker=None
    source_executor=SingleThreadedExecutor()
    try:
        native=b.BatteryManager();native.timer.cancel()
        injector=Node('p2c_tf_qos_injector');reference=Node('p2c_tf_reliable_reference');sampler=TfIngressSampler()
        source_executor.add_node(sampler)
        def run_source():
            try:source_executor.spin()
            except ExternalShutdownException:pass
        sampler_worker=threading.Thread(target=run_source);sampler_worker.start()
        original=[]
        reference.create_subscription(TFMessage,'/tb1/tf',lambda m:original.extend(
            t.header.stamp.sec for t in m.transforms if t.header.frame_id.endswith('map')),20)
        for node in (native,reference):executor.add_node(node)
        def run():
            try:executor.spin()
            except ExternalShutdownException:pass
        worker=threading.Thread(target=run);worker.start()
        def until(predicate):
            deadline=time.monotonic()+10
            while not predicate() and time.monotonic()<deadline:time.sleep(.01)
            assert predicate(),'isolated native DDS deadline'
        clock=injector.create_publisher(Clock,'/clock',10)
        reliable=injector.create_publisher(TFMessage,'/tb1/tf',20)
        sensor=injector.create_publisher(TFMessage,'/tb1/tf',QoSProfile(depth=20,reliability=ReliabilityPolicy.BEST_EFFORT))
        maps=injector.create_publisher(OccupancyGrid,'/tb1/gateway/merge_map',10)
        odoms=injector.create_publisher(Odometry,'/tb1/odom',10)
        until(lambda:reliable.get_subscription_count()==2 and sensor.get_subscription_count()==1 and sampler.native_publisher.get_subscription_count()==1)
        def advance(stamp):
            message=Clock();message.clock.sec=stamp;clock.publish(message);until(lambda:native.now()==stamp)
        def tf(stamp,relevant=True):
            t=TransformStamped();t.header.stamp.sec=stamp;t.header.stamp.nanosec=200000000
            t.header.frame_id='tb1/map' if relevant else 'tb1/odom'
            t.child_frame_id='tb1/odom' if relevant else 'tb1/base_footprint';t.transform.rotation.w=1.
            return TFMessage(transforms=[t])
        def state(stamp):
            grid=OccupancyGrid();grid.header.stamp.sec=stamp;grid.info.width=grid.info.height=100
            grid.info.resolution=.1;grid.info.origin.position.x=grid.info.origin.position.y=-5.;grid.data=[0]*10000
            odom=Odometry();odom.header.stamp.sec=stamp;odom.pose.pose.orientation.w=1.
            maps.publish(grid);odoms.publish(odom);until(lambda:native.last_odom_time==native.return_map_source_time==stamp)
        advance(50);reliable.publish(tf(48));until(lambda:original==[48] and native.map_tf_source_time==48.)
        for stamp in range(49,51):
            sensor.publish(tf(stamp))
            for _ in range(30):sensor.publish(tf(stamp,False))
            time.sleep(.05)
        until(lambda:native.map_tf_source_time==50.)
        assert original==[48],original
        state(50);assert native.current_return_budget() is not None
        depths={s.topic_name:dict(depth=s.qos_profile.depth,reliability=s.qos_profile.reliability.name)
                for s in native.subscriptions if s.topic_name in ('/tb1/battery/source_tf','/tb1/odom')}
        assert depths['/tb1/battery/source_tf']==dict(depth=20,reliability='RELIABLE')
        assert depths['/tb1/odom']==dict(depth=10,reliability='RELIABLE')
        raw=next(s for s in sampler.subscriptions if s.topic_name=='/tb1/tf')
        assert raw.qos_profile.depth==100 and raw.qos_profile.reliability==ReliabilityPolicy.BEST_EFFORT
        advance(53);state(53);sensor.publish(tf(53,False));time.sleep(.1)
        assert native.map_tf_source_time==50. and native.current_return_budget() is None
        sensor.publish(tf(60));time.sleep(.2)
        assert native.map_tf_source_time==50. and not native.pending_native_inputs and not native.native_frame_inbox
        energy=native.energy;sensor.publish(tf(53));until(lambda:native.map_tf_source_time==53.)
        assert native.current_return_budget() is not None and native.energy==energy
        assert native.total_motion_distance==0. and native.total_energy_elapsed==3.
        assert abs(native.energy-(native.initial_energy-3*native.idle_cost))<1e-8
        result=dict(status='PASS',scope='Actual robot-side source filtering, mixed DDS reliability, unchanged native consumer; not v19 QoS attribution or mission proof',
            current_battery_sha256=hashlib.sha256(Path(b.__file__).read_bytes()).hexdigest(),subscription_qos=depths,raw_source_queue=dict(depth=100,reliability='BEST_EFFORT'),body_transforms_per_relevant_sample=30,body_spacing_sec=0,
            sampler_source_sha256=hashlib.sha256(Path(__import__('multi_robot_exploration.tf_ingress_sampler',fromlist=['']).__file__).read_bytes()).hexdigest(),
            reliable_raw_reference_source=original[-1],sensor_native_source=50.,source_stamp_preserved=True,
            stale_frame_budget_unavailable=True,irrelevant_tf_did_not_renew=True,
            far_future_rejected_without_poisoning=True,energy_unchanged_by_tf=True,
            energy_balance=native.energy,odom_meter_elapsed_sec=native.total_energy_elapsed)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:
        executor.shutdown();source_executor.shutdown()
        if worker:worker.join(5.);assert not worker.is_alive()
        if sampler_worker:sampler_worker.join(5.);assert not sampler_worker.is_alive()
        for node in (native,injector,reference,sampler):
            if node:node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':main()
