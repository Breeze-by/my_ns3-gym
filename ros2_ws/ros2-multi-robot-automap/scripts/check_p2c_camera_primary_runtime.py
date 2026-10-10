#!/usr/bin/env python3
"""Actual DDS/Future camera-first choice with recorded state and controlled epochs."""
import argparse
import base64
import copy
import gzip
import hashlib
import json
import math
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

from multi_robot_exploration import control as current
from check_p2c_gate import exploration_travel_audit
from check_p2c_initial_replenishment_runtime import until
from p2c_return_preparation import decode_grid

REFERENCE='1dbc38d55738bc43f52436547944bf8b9397d0d2'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module,label,saved,output):
    head=module.HeadquartersControl()
    for timer in head.timers:timer.cancel()
    probe=Node('p2c_camera_primary_'+label,use_global_arguments=False)
    executors=[MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    for executor,node in zip(executors,(head,probe)):executor.add_node(node)
    errors=[]
    def spin(executor):
        try:executor.spin()
        except Exception as error:errors.append(repr(error))
    threads=[threading.Thread(target=spin,args=(executor,)) for executor in executors]
    for thread in threads:thread.start()
    data=copy.deepcopy(saved['event']['diagnostic_inputs'])
    epoch=math.ceil(saved['event']['planning_started_at_sec'])
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_known_fallback/run',10)
    topics={'/merge_map':OccupancyGrid}
    for name in data['robot_positions']:
        topics.update({f'/gateway/received/{name}/map':OccupancyGrid,
            f'/gateway/received/{name}/odom':Odometry,f'/gateway/received/{name}/tf':TFMessage,
            f'/gateway/received/{name}/battery_state':String})
    qos=QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
    publishers={topic:probe.create_publisher(kind,topic,qos if kind is String else 10) for topic,kind in topics.items()}
    events,goals,cdrs,callbacks=[],[],{},[]
    subscriptions=[probe.create_subscription(String,head.consumed_publisher.topic_name,
        lambda msg:events.append(json.loads(msg.data)),100)]
    def endpoint(handle):
        point=handle.request.pose.pose.position
        goals.append(dict(robot='tb2',source=head.now(),point=[point.x,point.y],kind='synthetic_action_endpoint'))
        handle.succeed();return NavigateToPose.Result()
    server=ActionServer(probe,NavigateToPose,'/gateway/tb2/navigate_to_pose',endpoint)
    entered,release,finished=threading.Event(),threading.Event(),threading.Event()
    original=module.robot_candidate_assignments
    original_camera=module.known_space_search_candidates
    block=[True]
    def generate(*args,**kwargs):
        result=original(*args,**kwargs)
        if block[0]:
            block[0]=False;entered.set();assert release.wait(12.)
        return result
    module.robot_candidate_assignments=generate
    def camera_generate(*args,**kwargs):
        result=original_camera(*args,**kwargs)
        if block[0]:
            block[0]=False;entered.set();assert release.wait(12.)
        return result
    module.known_space_search_candidates=camera_generate
    def run(message):
        try:
            module.HeadquartersControl.assign_idle_robots(head)
            callbacks.append(dict(stage=message.data,clock=head.now(),pose_sources=dict(head.robot_odom_received_at),
                private_decisions=sum(e.get('event')=='coordinator_navigation_decision' for e in events)))
        except Exception as error:errors.append(repr(error))
        finished.set()
    subscriptions.append(head.create_subscription(String,'/p2c_known_fallback/run',run,10))
    def tick(value):
        message=Clock();message.clock.sec=value;clock.publish(message)
    def deliver(value):
        for topic,publisher in publishers.items():
            kind=topics[topic];message=kind()
            name=topic.split('/')[3] if topic.startswith('/gateway/') else None
            if kind is String:message.data=json.dumps({**data['battery_states'][name],'stamp_sec':value})
            elif kind is TFMessage:
                transform=TransformStamped();transform.header.stamp.sec=value
                transform.header.frame_id='map';transform.child_frame_id=name+'/odom';transform.transform.rotation.w=1.
                message.transforms=[transform]
            else:
                message.header.stamp.sec=value
                if kind is OccupancyGrid:
                    geometry=data['source_map'] if name is None else data['return_maps'][name]
                    message.header.frame_id='map';message.info.height,message.info.width=geometry['shape']
                    message.info.resolution=geometry['resolution']
                    message.info.origin.position.x,message.info.origin.position.y=geometry['origin']
                    message.info.origin.orientation.w=1.;message.data=decode_grid(geometry).ravel().tolist()
                else:
                    message.header.frame_id=name+'/odom'
                    message.pose.pose.position.x,message.pose.pose.position.y=data['robot_positions'][name]
                    message.pose.pose.orientation.w=1.
            cdrs[str(value)+topic]=base64.b64encode(serialize_message(message)).decode()
            publisher.publish(message)
    def fresh(value):
        deadline=time.monotonic()+12.
        while time.monotonic()<deadline:
            tick(value);deliver(value);time.sleep(.03)
            if head.now()==value and all(head.robot_odom_received_at[name]==head.robot_tf_received_at[name]
                ==head.robot_map_received_at[name]==head.battery_state_received_at[name]==value
                for name in data['robot_positions']) and head.fresh_robot_inputs():return
        raise AssertionError('synthetic fresh DDS samples not consumed')
    def invoke(stage):
        finished.clear();trigger.publish(String(data=stage))
        assert finished.wait(12.) and not errors,errors
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in publishers.values()))
        fresh(epoch)
        head.robot_states=dict(data['robot_states']);head.goal_routes=copy.deepcopy(data['goal_routes'])
        head.active_exclusions=lambda:data['exclusions']
        head.initial_search_next=dict(data['initial_search_next'])
        head.successful_exploration_legs=dict(data['successful_exploration_legs'])
        before=head.successful_exploration_legs.get('tb2',0)
        head.initial_search_visits={tuple(math.floor(v/module.INITIAL_SEARCH_VISIT_BIN_M)
            for v in row['position']):row for row in data['initial_search_visits']}
        head.initial_search_views={(*(math.floor(v/module.INITIAL_SEARCH_VISIT_BIN_M)
            for v in row['position']),math.floor((row['yaw']+math.pi)/(2.*math.pi/16))%16):row
            for row in data['initial_search_views']}
        head.exploration_resume_intents=dict(data['exploration_resume_intents'])
        trigger.publish(String(data='expire'))
        assert entered.wait(12.)
        for _ in range(12):tick(epoch+3);time.sleep(.02)
        until(lambda:head.now()==epoch+3)
        release.set();assert finished.wait(12.) and not errors,errors
        assert not goals and all(stamp==epoch for stamp in callbacks[0]['pose_sources'].values())
        until(lambda:any(e.get('event')=='coordinator_planning_lease_expired' for e in events))
        module.robot_candidate_assignments=original;module.known_space_search_candidates=original_camera
        fresh(epoch+4)
        for index in range(8):
            invoke('fresh'+str(index));time.sleep(.05)
            if any(e.get('event')=='coordinator_navigation_decision' for e in events):break
        decisions=[e for e in events if e.get('event')=='coordinator_navigation_decision']
        assert len(decisions)==1
        until(lambda:len(goals)==1 and head.successful_exploration_legs.get('tb2',0)==before+1)
        if label=='current':
            assert decisions[0]['kind']=='initial_visual_search'
            assert decisions[0]['travel_preference']['camera_first_search']['selected_kind']=='camera'
        else:
            assert decisions[0]['kind']=='exploration'
        transcript=output.with_name(output.stem+'_'+label+'_raw.json')
        assert not transcript.exists()
        transcript.write_text(json.dumps(dict(callbacks=callbacks,private_events=events,input_cdrs=cdrs,
            actual_action_endpoint_goals=goals,ordinary_future_successes=head.successful_exploration_legs.get('tb2',0)-before),indent=2)+'\n')
        checked=exploration_travel_audit(decisions,True,True,True,True,True,True,True,label=='current')
        return dict(status='PASS',label=label,callbacks=callbacks,private_events=events,input_cdrs=cdrs,
            actual_action_endpoint_goals=goals,ordinary_future_successes=head.successful_exploration_legs.get('tb2',0)-before,
            travel_audit=checked,expired_sources_dispatched_zero=True,
            refreshed_source_epoch_sec=epoch+4,recorded_prior_work_count=before,controlled_snapshot_prior_work=True,gazebo_or_real_nav2_motion=0,native_charge_cycles_executed=0)
    finally:
        release.set();module.robot_candidate_assignments=original;module.known_space_search_candidates=original_camera
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        server.destroy();head.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();assert not args.output.exists()
    assert os.environ.get('ROS_DOMAIN_ID') in ('216','217')
    fixture=Path(__file__).resolve().parent.parent/'src/multi_robot_exploration/test/fixtures/p2c_v74_camera_primary.json.gz'
    saved=json.load(gzip.open(fixture,'rt'))['snapshots'][1]
    old=subprocess.check_output(['rtk','proxy','git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_frozen_camera_primary');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(old,'<1dbc38d frozen>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2','-p','enable_battery:=true',
        '-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        output=dict(status='PASS',scope='Actual isolated DDS/Futures with recorded map, body and prior-work counters, controlled headings/epochs and stopped clock during fresh computation. Both full versions price current full go/return; old maps first, new camera first. Original prior count is controlled snapshot state; only newly returned Future SUCCESS increment is actual. No native credit, Gazebo/Nav2 motion or causal task/deadline proof.',
            reference_commit=REFERENCE,reference_control_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            reader_sha256=hashlib.sha256(Path(__file__).with_name('check_p2c_gate.py').read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen',saved,args.output),case(current,'current',saved,args.output)],all_owned_closed=True)
        args.output.write_text(json.dumps(output,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=row['label'],goals=len(row['actual_action_endpoint_goals']),
            futures=row['ordinary_future_successes']) for row in output['cases']])))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
