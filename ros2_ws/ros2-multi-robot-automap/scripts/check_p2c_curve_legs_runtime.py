#!/usr/bin/env python3
"""Compare bounded normal rally paths through actual DDS and action Futures."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types

import numpy as np
import rclpy
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.action import ActionServer, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from check_p2c_dispatch_boundary_runtime import until
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_outbound_routes import outbound_route_audit

REFERENCE='d5e9da317e26ef96b63f7413d786d0d9ddef460f'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module,label):
    node=module.HeadquartersControl();probe=Node('p2c_curve_'+label,use_global_arguments=False)
    for timer in node.timers:timer.cancel()
    executors=[MultiThreadedExecutor(num_threads=2),MultiThreadedExecutor(num_threads=2)]
    executors[0].add_node(node);executors[1].add_node(probe)
    threads=[threading.Thread(target=e.spin) for e in executors]
    for thread in threads:thread.start()
    topics={'/merge_map':OccupancyGrid}
    for name in ('tb1','tb2'):
        topics.update({f'/gateway/received/{name}/map':OccupancyGrid,
            f'/gateway/received/{name}/odom':Odometry,f'/gateway/received/{name}/tf':TFMessage,
            f'/gateway/received/{name}/battery_state':String})
    battery_qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)
    pubs={topic:probe.create_publisher(kind,topic,battery_qos if kind is String else 10) for topic,kind in topics.items()}
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_curve/run',10)
    events=[];goals=[];submitted_routes=[];errors=[];finished=threading.Event();drained=threading.Event()
    result=node.rally_goal_result
    def consumed(*args):submitted_routes.append((args[0],tuple(node.rally_leg_routes[args[0]])));result(*args);drained.set()
    node.rally_goal_result=consumed
    def goal(name,request):
        p=request.pose.pose;s=request.pose.header.stamp
        goals.append(dict(robot=name,position=[p.position.x,p.position.y],yaw=2*math.atan2(p.orientation.z,p.orientation.w),header_time=s.sec+s.nanosec*1e-9))
        return GoalResponse.ACCEPT
    def execute(handle):handle.succeed();return NavigateToPose.Result()
    servers=[ActionServer(probe,NavigateToPose,f'/gateway/{name}/navigate_to_pose',execute_callback=execute,goal_callback=lambda request,name=name:goal(name,request)) for name in ('tb1','tb2')]
    audit=probe.create_subscription(String,'/gateway/consumed',lambda msg:events.append(json.loads(msg.data)),100)
    def run(msg):
        try:node.update_mission()
        except Exception as error:errors.append(repr(error))
        finally:finished.set()
    subscription=node.create_subscription(String,'/p2c_curve/run',run,10)
    grid=np.zeros((60,60),dtype=np.int16);grid[:25,25:35]=100
    positions={'tb1':(1.05,1.05),'tb2':(4.05,4.05)}
    if label=='current_pair':positions['tb2']=(4.05,5.55)
    goal_count=2 if label=='current_pair' else 1
    energy=80.
    def stamp(value,dest):dest.sec=int(value);dest.nanosec=round((value-int(value))*1e9)
    def tick(value):msg=Clock();stamp(value,msg.clock);clock.publish(msg)
    def deliver(value):
        for topic,pub in pubs.items():
            msg=topics[topic]();name='tb2' if '/tb2/' in topic else 'tb1'
            if isinstance(msg,TFMessage):
                t=TransformStamped();stamp(value,t.header.stamp);t.header.frame_id='map';t.child_frame_id=name+'/odom';t.transform.rotation.w=1.;msg.transforms=[t]
            elif isinstance(msg,String):
                msg.data=json.dumps(dict(robot=name,mode='ACTIVE',energy=energy,capacity=100.,charge_x=positions[name][0],charge_y=positions[name][1],charge_target_fraction=.8,charge_radius_m=.8,stamp_sec=value,_gateway=dict(source_time=value,delivery_time=value),nominal_speed_mps=.18,idle_cost_per_sec=.02,move_cost_per_m=1.,return_path_factor=2.,return_safety_margin=5.,charge_duration_sec=10.,return_recovery_wait_sec=30.))
            else:
                stamp(value,msg.header.stamp)
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=msg.info.height=60;msg.info.resolution=.1;msg.info.origin.orientation.w=1.;msg.data=grid.ravel().tolist()
                else:
                    msg.header.frame_id=name+'/odom';msg.pose.pose.position.x,msg.pose.pose.position.y=positions[name]
                    yaw=-math.pi/2 if name=='tb2' else 0.;msg.pose.pose.orientation.z=math.sin(yaw/2);msg.pose.pose.orientation.w=math.cos(yaw/2)
            pub.publish(msg)
    def invoke():
        finished.clear();trigger.publish(String(data='run'));assert finished.wait(10.) and not errors,errors
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values()) and all(c.server_is_ready() for c in node.robot_nav_clients.values()) and node.consumed_publisher.get_subscription_count()==1,10.)
        for _ in range(10):tick(10.);time.sleep(.02)
        until(lambda:node.now()==10.)
        for _ in range(10):deliver(10.);time.sleep(.02)
        until(node.fresh_robot_inputs)
        # Only the target/assignment context is synthetic; geometry, models,
        # state and source clocks enter through the actual DDS callbacks.
        node.task_state='RALLY';node.target=(4.05,3.05);node.target_received_source_time=10.
        node.rally_targets={'tb1':module.RallyPose(4.05,2.05,math.pi/2),'tb2':module.RallyPose(4.05,4.05,-math.pi/2)}
        node.rally_final_targets=dict(node.rally_targets);node.rally_arrived['tb2']=True
        node.rally_dispatch_order=['tb1','tb2'];node.rally_preflight_complete=True
        if label=='current_pair':
            node.rally_targets['tb2']=module.RallyPose(4.05,4.85,-math.pi/2)
            node.rally_final_targets=dict(node.rally_targets);node.rally_arrived['tb2']=False
        if label=='current_refuge':node.rally_yield_targets.add('tb1')
        if label=='current_no_battery':node.enable_battery=False
        original_sources=node.input_freshness_details();invoke();until(lambda:len(goals)==goal_count)
        until(lambda:len(submitted_routes)==goal_count)
        until(lambda:sum(e.get('event')=='coordinator_navigation_decision' for e in events)==goal_count)
        decision=next(e for e in events if e.get('event')=='coordinator_navigation_decision' and e['robot']=='tb1')
        first_route=next(route for name,route in submitted_routes if name=='tb1')
        route=decision.get('outbound_map_route',dict(route=(positions['tb1'],*first_route)))['route']
        length=sum(math.dist(a,b) for a,b in zip(route,route[1:]))
        assert length<=module.MAX_NAVIGATION_LEG_M+.2
        cell=lambda point:module.world_to_grid(*point,node.resolution,*node.origin)
        safe=module.traversable_grid(node.map_data,node.resolution,module.RALLY_PATH_CLEARANCE_M)
        first_goal=next(g for g in goals if g['robot']=='tb1')
        direct_clear=all(safe[p] for p in module._line_cells(cell(positions['tb1']),cell(first_goal['position'])))
        assert direct_clear==(label not in ('current','current_pair'))
        assert node.input_freshness_details()==original_sources
        # Advancing the real /clock cannot extend the old pose/TF sources.
        for _ in range(10):tick(13.);time.sleep(.02)
        until(lambda:node.now()==13.);invoke();time.sleep(.1);assert len(goals)==goal_count
        for _ in range(10):deliver(13.);time.sleep(.02)
        until(node.fresh_robot_inputs);drained.clear();invoke();until(lambda:len(goals)==2*goal_count)
        until(lambda:len(submitted_routes)==2*goal_count)
        until(lambda:sum(e.get('event')=='coordinator_navigation_decision' for e in events)==2*goal_count)
        if node.enable_battery:
            energy=.1
            for _ in range(10):tick(14.);deliver(14.);time.sleep(.02)
            until(lambda:node.now()==14. and node.battery_states['tb1']['energy']==.1)
            invoke();time.sleep(.1);assert len(goals)==2*goal_count
        with tempfile.TemporaryDirectory() as directory:
            ledger=Path(directory)/'ledger.jsonl';ledger.write_text(''.join(json.dumps(e)+'\n' for e in events))
            audits=dict(dispatch=navigation_dispatch_audit(ledger,True),outbound=outbound_route_audit(ledger,node.enable_battery))
        return dict(status='PASS',label=label,action_server_goals=goals,private_events=events,independent_audits=audits,
            direct_clear=direct_clear,first_route_length_m=length,expired_source_goal_count=goal_count,
            fresh_source_goal_count=2*goal_count,unfunded_goal_count=2*goal_count if node.enable_battery else None,
            results_consumed_before_teardown=True)
    finally:
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        for server in servers:server.destroy()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    old=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_frozen_curve');frozen.__file__=current.__file__;frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(old,'<frozen P2C d5>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2','-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        rows=[case(frozen,'frozen'),case(current,'current'),case(current,'current_refuge'),case(current,'current_no_battery'),case(current,'current_pair')]
        result=dict(status='PASS',scope='Actual isolated DDS map/pose/TF/battery/clock and full update_mission dispatch plus synthetic ActionServer/Future; synthetic target/assignment, no physical Nav2, duration or task guarantee',reference_commit=REFERENCE,reference_sha256=hashlib.sha256(old.encode()).hexdigest(),reference_source=old,control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),cases=rows,owned_nodes_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status='PASS',cases=[{k:v for k,v in row.items() if k not in ('private_events',)} for row in rows])))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
