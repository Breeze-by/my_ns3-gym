#!/usr/bin/env python3
"""Actual DDS/Future probe for corridor preparation; no Gazebo or real Nav2."""
import argparse
import hashlib
import gzip
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
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from p2c_return_preparation import audit_preparation
from p2c_outbound_routes import decode

REFERENCE = '39e1840930c692612d0cf0584050ae961dce4fff'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def until(predicate, timeout=10.):
    deadline = time.monotonic()+timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.02)
    assert predicate(), 'bounded probe wait expired'


def case(module, label, displacement=None):
    node = module.HeadquartersControl()
    for timer in node.timers:
        timer.cancel()
    probe = Node('p2c_return_preparation_'+label, use_global_arguments=False)
    executor = MultiThreadedExecutor(num_threads=2);executor.add_node(node)
    probe_executor = MultiThreadedExecutor(num_threads=2);probe_executor.add_node(probe)
    threads = [threading.Thread(target=e.spin) for e in (executor,probe_executor)]
    for thread in threads:thread.start()
    clock = probe.create_publisher(Clock, '/clock', 10)
    trigger = probe.create_publisher(String, '/p2c_return_preparation/run', 10)
    finished = threading.Event();entered = threading.Event();release = threading.Event()
    positions = {'tb1':(-4.,0.), 'tb2':(0.,0.)}
    states = {name:dict(mode='ACTIVE', energy=25. if name=='tb1' else 80., capacity=100.,
        charge_target_fraction=.8, charge_x=3. if name=='tb1' else 0., charge_y=0. if name=='tb1' else -4.,
        charge_radius_m=.8, move_cost_per_m=1., idle_cost_per_sec=.02,
        return_path_factor=2., nominal_speed_mps=.18, return_safety_margin=8.) for name in positions}
    helper, returning = 'tb2', 'tb1'
    if displacement:
        original_inputs = displacement['original_event']['diagnostic_inputs']
        positions = dict(original_inputs['robot_positions'])
        states = dict(original_inputs['battery_states'])
        helper, returning = 'tb1', 'tb2'
    topics = {'/merge_map':OccupancyGrid}
    for name in positions:
        topics.update({f'/gateway/received/{name}/map':OccupancyGrid,
            f'/gateway/received/{name}/odom':Odometry, f'/gateway/received/{name}/tf':TFMessage,
            f'/gateway/received/{name}/battery_state':String})
    publishers = {topic:probe.create_publisher(kind,topic,
        QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL) if kind is String else 10)
        for topic,kind in topics.items()}
    events=[];requests=[];goals=[];callbacks=[];errors=[]
    subscriptions = [probe.create_subscription(String,node.consumed_publisher.topic_name,
        lambda msg:events.append(json.loads(msg.data)),10),
        probe.create_subscription(String,node.charge_request_publishers[returning].topic_name,
        lambda msg:requests.append(json.loads(msg.data)),10)]
    def execute(handle):
        goals.append((handle.request.pose.pose.position.x, handle.request.pose.pose.position.y))
        assert release.wait(15.), 'synthetic action result was not released'
        handle.succeed()
        return NavigateToPose.Result()
    server = ActionServer(probe, NavigateToPose, f'/gateway/{helper}/navigate_to_pose', execute)
    assignment = module.Assignment(module.Viewpoint(1,160,60,161,60,1000,10),-4.,6.,6.,100.,-4.,6.)
    original = module.rally_yield_pose
    def slow(*args,**kwargs):
        result = original(*args,**kwargs);entered.set();time.sleep(.6)
        return result
    if label == 'current':module.rally_yield_pose=slow
    def run(message):
        try:
            if message.data in ('prepare','cleared'):
                result=module.HeadquartersControl.prepare_exploration_return(node,returning)
                if message.data=='cleared':assert result is False
            elif message.data == 'request':module.HeadquartersControl.request_exploration_charge(node,[(returning,assignment)])
            else:module.HeadquartersControl.admit_exploration_return_yield(node)
            callbacks.append(dict(clock=node.now(),pose_source=node.robot_odom_received_at[helper],
                pending=bool(getattr(node,'pending_exploration_return_yield',None)),charge_owner=bool(node.rally_charge_requested)))
        except Exception as error:errors.append(repr(error))
        finished.set()
    subscriptions.append(node.create_subscription(String,'/p2c_return_preparation/run',run,10))
    def tick(value):
        msg=Clock();msg.clock.sec=int(value);clock.publish(msg)
    def deliver(value):
        for topic,publisher in publishers.items():
            msg=topics[topic]()
            if isinstance(msg,String):
                name=topic.split('/')[3];msg.data=json.dumps({**states[name],'stamp_sec':value})
            elif isinstance(msg,TFMessage):
                name=topic.split('/')[3];tf=TransformStamped();tf.header.stamp.sec=int(value)
                tf.header.frame_id='map';tf.child_frame_id=name+'/odom';tf.transform.rotation.w=1.;msg.transforms=[tf]
            else:
                msg.header.stamp.sec=int(value)
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=msg.info.height=200;msg.info.resolution=.1
                    msg.info.origin.position.x=msg.info.origin.position.y=-10.;msg.info.origin.orientation.w=1.;msg.data=[0]*40000
                    if displacement:
                        saved = original_inputs['source_map'] if topic == '/merge_map' else original_inputs['return_maps'][topic.split('/')[3]]
                        msg.info.height,msg.info.width = saved['shape'];msg.info.resolution = saved['resolution']
                        msg.info.origin.position.x,msg.info.origin.position.y = saved['origin']
                        msg.data = decode(saved).ravel().tolist()
                else:
                    name=topic.split('/')[3];msg.header.frame_id=name+'/odom'
                    msg.pose.pose.position.x,msg.pose.pose.position.y=positions[name];msg.pose.pose.orientation.w=1.
            publisher.publish(msg)
    def consume(value):
        deadline=time.monotonic()+10.
        while time.monotonic()<deadline:
            tick(value);deliver(value);time.sleep(.03)
            if node.now()==value and all(node.robot_odom_received_at[n]==node.robot_tf_received_at[n]==node.robot_map_received_at[n]==value for n in positions) and node.fresh_robot_inputs():return
        raise AssertionError('fresh DDS inputs were not consumed')
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in publishers.values()))
        until(lambda:node.robot_nav_clients[helper].server_is_ready())
        consume(10.)
        assert node.task_state=='EXPLORE'
        trigger.publish(String(data='prepare' if displacement else 'request'))
        if label=='current':
            assert entered.wait(10.)
            for _ in range(12):
                tick(13.)
                if not displacement:deliver(13.)
                time.sleep(.02)
        assert finished.wait(10.) and not errors,errors
        if label=='frozen' and displacement:
            assert callbacks[0]['pending'] and not goals and not requests
            point=node.pending_exploration_return_yield['refuge']
            import math
            assert math.dist(node.robot_positions[helper],(point.x,point.y))<.5
            finished.clear();trigger.publish(String(data='admit'))
            assert finished.wait(10.) and not errors,errors
            assert not node.pending_exploration_return_yield and not goals and not requests
        elif label=='frozen':
            until(lambda:len(requests)==1)
            assert not goals and requests[0]['robot']=='tb1'
        else:
            assert callbacks[0]==dict(clock=13.,pose_source=10.,pending=True,charge_owner=False)
            assert not requests and not goals
            if displacement:
                finished.clear();trigger.publish(String(data='admit'))
                assert finished.wait(10.) and not errors,errors
                assert not requests and not goals and node.pending_exploration_return_yield
            consume(13.);finished.clear();trigger.publish(String(data='admit'))
            assert finished.wait(10.) and not errors,errors
            until(lambda:len(goals)==1 and node.goal_handles[helper] is not None)
            assert not requests and not node.rally_charge_requested
            positions[helper]=goals[0];consume(14.);release.set()
            until(lambda:node.goal_handles[helper] is None and node.robot_states[helper]=='idle')
            assert not node.exploration_return_yields
            if displacement:
                relevant=[e for e in events if e.get('kind')=='exploration_return_yield']
                assert len(relevant)==1 and audit_preparation(relevant[0])=='yield'
                finished.clear();trigger.publish(String(data='cleared'))
                assert finished.wait(10.) and not errors,errors
                assert not requests
            else:
                finished.clear();trigger.publish(String(data='request'))
                assert finished.wait(10.) and not errors,errors
                until(lambda:len(requests)==1 and len(events)>=2)
                relevant=[e for e in events if e.get('event')=='coordinator_charge_decision' or e.get('kind')=='exploration_return_yield']
                assert [audit_preparation(e) for e in relevant]==['yield','charge']
                assert requests[0]['stamp_sec']==14.
        return dict(status='PASS',label=label,callbacks=callbacks,charge_requests=requests,
            synthetic_endpoint_goals=goals,private_events=events,
            gazebo_or_real_nav2_goals=0,source_stamps_preserved=True,action_futures_closed=True)
    finally:
        module.rally_yield_pose=original;release.set()
        executor.shutdown();probe_executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        server.destroy();node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--displacement-fixture',type=Path,help='Original v54 grids/positions for the actual half-metre displacement counterexample')
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite evidence')
    assert os.environ.get('ROS_DOMAIN_ID') in ('216','217'), 'use an isolated component domain'
    displacement=None
    if args.displacement_fixture:
        with gzip.open(args.displacement_fixture,'rt') as stream:displacement=json.load(stream)
    reference=displacement['reference_commit'] if displacement else REFERENCE
    old=subprocess.check_output(['git','show',reference+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_frozen_return_preparation');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(old,'<frozen original>', 'exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        result=dict(status='PASS',scope='Actual isolated DDS/Futures, synthetic poses/maps and action endpoint; no task, latency or physical safety claim',
            reference_commit=reference,reference_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_return_preparation.py').read_bytes()).hexdigest(),
            displacement_fixture=displacement,
            cases=[case(frozen,'frozen',displacement),case(current,'current',displacement)],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status=result['status'],cases=[dict(label=r['label'],requests=len(r['charge_requests']),goals=len(r['synthetic_endpoint_goals'])) for r in result['cases']])))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
