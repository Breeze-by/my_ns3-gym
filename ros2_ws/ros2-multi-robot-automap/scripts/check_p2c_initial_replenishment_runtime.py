#!/usr/bin/env python3
"""Actual DDS/Futures/native credit with synthetic motion; no Gazebo task."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import types

import rclpy
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rclpy.serialization import serialize_message
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import battery_manager as native
from multi_robot_exploration import control as current

REFERENCE = 'a383cda7296f3e696ef2349b3f0fceb0448dc3a9'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def until(predicate, timeout=12.):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.02)
    assert predicate(), 'bounded component wait expired'


def case(module, label):
    head, battery = module.HeadquartersControl(), native.BatteryManager()
    probe = Node('p2c_initial_replenishment_' + label, use_global_arguments=False)
    for member in (head, battery):
        for timer in member.timers:
            timer.cancel()
    executors = [MultiThreadedExecutor(num_threads=2) for _ in range(3)]
    for executor, member in zip(executors, (head, battery, probe)):
        executor.add_node(member)
    errors, events, requests, goals, audits, cdrs = [], [], [], [], [], []
    def spin(executor):
        try:
            executor.spin()
        except Exception as error:
            errors.append(repr(error))
    threads = [threading.Thread(target=spin, args=(executor,)) for executor in executors]
    for thread in threads:
        thread.start()
    clock = probe.create_publisher(Clock, '/clock', 10)
    head_trigger = probe.create_publisher(String, '/p2c_initial_replenishment/head', 10)
    native_trigger = probe.create_publisher(String, '/p2c_initial_replenishment/native', 10)
    positions = {'tb1': [3., 3.], 'tb2': [8., 5.]}
    state_qos = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    topics = {'/merge_map': OccupancyGrid, '/tb1/map': OccupancyGrid,
        '/tb1/gateway/merge_map': OccupancyGrid, '/tb1/odom': Odometry, '/tb1/tf': TFMessage}
    for name in positions:
        topics.update({f'/gateway/received/{name}/map': OccupancyGrid,
            f'/gateway/received/{name}/odom': Odometry, f'/gateway/received/{name}/tf': TFMessage})
    publishers = {topic: probe.create_publisher(kind, topic, state_qos if topic == '/tb1/map' else 10)
                  for topic, kind in topics.items()}
    battery_delivery = probe.create_publisher(String, '/gateway/received/tb1/battery_state', state_qos)
    peer_delivery = probe.create_publisher(String, '/gateway/received/tb2/battery_state', state_qos)
    request_delivery = probe.create_publisher(String, '/tb1/gateway/charge_request', 10)
    subscriptions = [probe.create_subscription(String, '/tb1/battery_state', battery_delivery.publish, state_qos),
        probe.create_subscription(String, '/tb1/battery_return_audit', lambda msg: audits.append(json.loads(msg.data)), state_qos),
        probe.create_subscription(String, head.consumed_publisher.topic_name, lambda msg: events.append(json.loads(msg.data)), 100)]
    def requested(message):
        requests.append(json.loads(message.data))
        cdrs.append(dict(topic=head.charge_request_publishers['tb1'].topic_name,
            cdr=base64.b64encode(serialize_message(message)).decode()))
        request_delivery.publish(message)
    subscriptions.append(probe.create_subscription(String, head.charge_request_publishers['tb1'].topic_name, requested, 10))
    ordinary_done, native_entered, native_release = threading.Event(), threading.Event(), threading.Event()
    def ordinary(handle):
        goals.append(dict(kind='ordinary_synthetic_endpoint', x=handle.request.pose.pose.position.x,
                          y=handle.request.pose.pose.position.y))
        handle.succeed()
        ordinary_done.set()
        return NavigateToPose.Result()
    def returning(handle):
        point = handle.request.pose.pose.position
        goals.append(dict(kind='native_return_synthetic_endpoint', x=point.x, y=point.y))
        native_entered.set()
        assert native_release.wait(12.), 'synthetic native result was not released'
        handle.succeed()
        return NavigateToPose.Result()
    servers = [ActionServer(probe, NavigateToPose, '/gateway/tb1/navigate_to_pose', ordinary),
               ActionServer(probe, NavigateToPose, '/tb1/navigate_to_pose', returning)]
    finished, entered, release = threading.Event(), threading.Event(), threading.Event()
    candidate = module.Assignment(module.Viewpoint(1,30,38,30,39,1000,10),3.8,3.,.3,100.,3.8,3.)
    callbacks = []
    original = module.plan_rally_leg
    def blocked(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(12.), 'controlled contact calculation was not released'
        return result
    def head_run(message):
        try:
            if message.data == 'ordinary':
                goal = module.Assignment(module.Viewpoint(1,30,35,30,36,1000,10),3.5,3.,.5,100.,3.5,3.)
                head.robot_states['tb1'] = 'active'
                head.goal_targets['tb1'] = goal
                head.goal_routes['tb1'] = [(3.,3.),(3.5,3.)]
                module.HeadquartersControl.send_goal(head,'tb1',goal)
            else:
                module.HeadquartersControl.request_exploration_charge(head,[('tb1',candidate)])
            callbacks.append(dict(stage=message.data, clock=head.now(),
                completed=head.successful_exploration_legs.get('tb1',0), requests=len(requests)))
        except Exception as error:
            errors.append(repr(error))
        finished.set()
    subscriptions.append(head.create_subscription(String, '/p2c_initial_replenishment/head', head_run, 10))
    native_finished = threading.Event()
    def native_run(message):
        try:
            battery.timer_callback()
        except Exception as error:
            errors.append(repr(error))
        native_finished.set()
    subscriptions.append(battery.create_subscription(String, '/p2c_initial_replenishment/native', native_run, 10))
    def tick(value):
        message = Clock();message.clock.sec = value;clock.publish(message)
    def deliver(value):
        for topic,publisher in publishers.items():
            message = topics[topic]()
            name = 'tb1' if topic.startswith('/tb1/') else topic.split('/')[3] if topic.startswith('/gateway/') else None
            if isinstance(message,TFMessage):
                transform=TransformStamped();transform.header.stamp.sec=value
                transform.header.frame_id='map';transform.child_frame_id=name+'/odom';transform.transform.rotation.w=1.
                message.transforms=[transform]
            else:
                message.header.stamp.sec=value
                if isinstance(message,OccupancyGrid):
                    message.header.frame_id='map';message.info.width=100;message.info.height=60;message.info.resolution=.1
                    message.info.origin.orientation.w=1.;message.data=[0]*6000
                else:
                    message.header.frame_id=name+'/odom'
                    message.pose.pose.position.x,message.pose.pose.position.y=positions[name]
                    message.pose.pose.orientation.w=1.
            publisher.publish(message)
            cdrs.append(dict(topic=topic,source=value,cdr=base64.b64encode(serialize_message(message)).decode()))
        peer_delivery.publish(String(data=json.dumps(dict(mode='ACTIVE',stamp_sec=value,energy=80.,capacity=100.,
            charge_count=0,return_count=0,charge_target_fraction=.8,charge_x=8.,charge_y=5.,charge_radius_m=.8,
            move_cost_per_m=1.,idle_cost_per_sec=.02,return_path_factor=2.,nominal_speed_mps=.18,return_safety_margin=8.))))
    def invoke_native():
        native_finished.clear();native_trigger.publish(String(data='tick'))
        assert native_finished.wait(12.) and not errors, errors
    def fresh(value):
        for _ in range(12):
            tick(value);deliver(value);time.sleep(.03)
        until(lambda:head.now()==battery.now()==value and battery.pose_source_age() is not None
            and battery.return_map_source_time==value)
        invoke_native()
        until(lambda:head.battery_state_received_at['tb1']==value and head.fresh_robot_inputs())
    def invoke_head(stage):
        finished.clear();head_trigger.publish(String(data=stage))
        assert finished.wait(12.) and not errors, errors
    try:
        until(lambda:head_trigger.get_subscription_count()==native_trigger.get_subscription_count()==1)
        until(lambda:head.robot_nav_clients['tb1'].server_is_ready() and battery.navigation.server_is_ready())
        fresh(10)
        invoke_head('before_work');assert not requests
        invoke_head('ordinary');assert ordinary_done.wait(12.)
        until(lambda:head.successful_exploration_legs.get('tb1')==1 and head.robot_states['tb1']=='idle')
        positions['tb1']=[3.5,3.];fresh(11)
        module.plan_rally_leg=blocked
        finished.clear();head_trigger.publish(String(data='expire'))
        assert entered.wait(12.)
        for _ in range(12):tick(14);time.sleep(.02)
        until(lambda:head.now()==14.)
        release.set();assert finished.wait(12.) and not errors, errors
        assert not requests and not head.rally_charge_requested
        module.plan_rally_leg=original
        fresh(14);invoke_head('fresh')
        if label=='frozen':
            assert not requests and battery.mode==native.ACTIVE and battery.charge_count==0
        else:
            until(lambda:len(requests)==1 and battery.mode==native.RETURNING)
            assert requests[0]['reason']=='initial_near_home_replenishment' and requests[0]['required_energy']==80.
            fresh(15);assert native_entered.wait(12.)
            point=next(goal for goal in goals if goal['kind']=='native_return_synthetic_endpoint')
            positions['tb1']=[point['x'],point['y']]
            fresh(16);native_release.set()
            until(lambda:not battery.return_goal_pending and battery.return_goal_handle is None)
            invoke_native()
            until(lambda:battery.mode==native.CHARGING)
            for value in range(17,25):fresh(value)
            until(lambda:battery.mode==native.ACTIVE and battery.charge_count==1
                and head.battery_modes['tb1']=='ACTIVE' and head.battery_states['tb1']['charge_count']==1)
            invoke_head('after_first_charge');assert len(requests)==1
            assert battery.charging_energy_added>0 and battery.energy>79.
            assert any(event['event']=='return_finished' and event['outcome']=='charger_stopped' for event in audits)
        return dict(status='PASS',label=label,callbacks=callbacks,requests=requests,
            goals=goals,private_events=events,native_audits=audits,input_and_request_cdrs=cdrs,
            native_charge_count=battery.charge_count,native_charged_energy_added=battery.charging_energy_added,
            native_motion_meter_distance=battery.total_motion_distance,
            no_work_rejected=True,expired_sources_rejected=True,post_charge_policy_rejected=True,
            source_epoch_14_delivered=True,physical_gazebo_or_nav2_motion=0)
    finally:
        module.plan_rally_leg=original;release.set();native_release.set()
        for server in servers:server.destroy()
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(5.);assert not thread.is_alive()
        head.destroy_node();battery.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite evidence')
    assert os.environ.get('ROS_DOMAIN_ID') in ('216','217')
    source=subprocess.check_output(['rtk','proxy','git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_initial_replenishment_reference');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(source,'<a383cda original control>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2','-p','enable_battery:=true',
        '-p','enable_rally:=true','-p','auto_save_map:=false','-p','robot_name:=tb1',
        '-p','capacity:=100.','-p','initial_energy:=40.','-p','charge_x:=2.','-p','charge_y:=3.','-p','charge_duration_sec:=6.'])
    try:
        result=dict(status='PASS',scope='Actual isolated DDS, ordinary and native ActionClient Futures, original native credit on controlled synthetic pose steps. No real Nav2/Gazebo motion, mission replay, deadline or causal benefit claim.',
            reference_commit=REFERENCE,reference_control_sha256=hashlib.sha256(source.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            native_sha256=hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen'),case(current,'current')],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=row['label'],requests=len(row['requests']),
            native_charges=row['native_charge_count']) for row in result['cases']],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
