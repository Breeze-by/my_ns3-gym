#!/usr/bin/env python3
"""Actual DDS and action Futures for a funded first ordinary goal continuation."""
import argparse
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
from rclpy.action import ActionServer, CancelResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from check_p2c_initial_replenishment_runtime import until

REFERENCE='d0be454749a80d2d20a4daa4bdc9efe544a1e5f1'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module, label, scenario):
    head=module.HeadquartersControl();probe=Node('initial_goal_'+label+'_'+scenario,use_global_arguments=False)
    for timer in head.timers:timer.cancel()
    executors=[MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    errors=[];threads=[]
    def spin(executor):
        try:executor.spin()
        except Exception as error:errors.append(repr(error))
    for ex,node in zip(executors,(head,probe)):
        ex.add_node(node);thread=threading.Thread(target=spin,args=(ex,));thread.start();threads.append(thread)
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/initial_goal/run',10)
    qos=QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
    kinds={'/merge_map':OccupancyGrid}
    positions={'tb1':[2.5,3.],'tb2':[8.,5.]}
    for name in positions:
        kinds.update({f'/gateway/received/{name}/map':OccupancyGrid,
            f'/gateway/received/{name}/odom':Odometry,f'/gateway/received/{name}/tf':TFMessage,
            f'/gateway/received/{name}/battery_state':String})
    publishers={topic:probe.create_publisher(kind,topic,qos if kind==String else 10) for topic,kind in kinds.items()}
    events=[];requests=[];goals=[];cancels=[];callbacks=[];native_sources=[]
    subscriptions=[probe.create_subscription(String,head.consumed_publisher.topic_name,
        lambda msg:events.append(json.loads(msg.data)),100),
        probe.create_subscription(String,head.charge_request_publishers['tb1'].topic_name,
        lambda msg:requests.append(json.loads(msg.data)),10)]
    entered=threading.Event();release=threading.Event();finished=threading.Event();calculation=threading.Event();calculation_release=threading.Event()
    def execute(handle):
        goals.append([handle.request.pose.pose.position.x,handle.request.pose.pose.position.y]);entered.set()
        assert release.wait(12.),'controlled action result was not released'
        if handle.is_cancel_requested:handle.canceled()
        else:handle.succeed()
        return NavigateToPose.Result()
    def cancel(handle):cancels.append(True);return CancelResponse.ACCEPT
    server=ActionServer(probe,NavigateToPose,'/gateway/tb1/navigate_to_pose',execute,cancel_callback=cancel)
    candidate=module.Assignment(module.Viewpoint(1,30,38,30,39,1000,10),3.8,3.,.3,100.,3.8,3.)
    original_plan=module.plan_rally_leg
    original_alternative=module.HeadquartersControl.has_funded_frontier_alternative
    module.HeadquartersControl.has_funded_frontier_alternative=lambda *args:True
    def blocked(*args,**kwargs):
        result=original_plan(*args,**kwargs);calculation.set()
        assert calculation_release.wait(12.)
        return result
    def run(message):
        try:
            if message.data=='ordinary':
                goal=module.Assignment(module.Viewpoint(1,30,35,30,36,1000,10),3.5,3.,1.,100.,3.5,3.)
                head.robot_states['tb1']='active';head.goal_targets['tb1']=goal
                head.goal_routes['tb1']=((2.5,3.),(3.5,3.));head.goal_initial_gain['tb1']=1000
                module.HeadquartersControl.send_goal(head,'tb1',goal)
            elif message.data=='cancel':module.HeadquartersControl.cancel_stalled_goals(head)
            else:module.HeadquartersControl.request_exploration_charge(head,[('tb1',candidate)])
            callbacks.append(dict(stage=message.data,clock=head.now(),completed=head.successful_exploration_legs.get('tb1',0),requests=len(requests)))
        except Exception as error:errors.append(repr(error))
        finished.set()
    subscriptions.append(head.create_subscription(String,'/initial_goal/run',run,10))
    def tick(value):msg=Clock();msg.clock.sec=value;clock.publish(msg)
    def deliver(value):
        for topic,pub in publishers.items():
            msg=kinds[topic]();name=topic.split('/')[3] if topic.startswith('/gateway/') else None
            if isinstance(msg,String):
                msg.data=json.dumps(dict(robot=name,mode='ACTIVE',stamp_sec=float(value),energy=40.,capacity=100.,charge_count=0,
                    charge_target_fraction=.8,charge_x=2. if name=='tb1' else 8.,charge_y=3. if name=='tb1' else 5.,charge_radius_m=.8,
                    move_cost_per_m=1.,idle_cost_per_sec=.02,return_path_factor=2.,nominal_speed_mps=.18,return_safety_margin=8.,return_recovery_wait_sec=30.))
                native_sources.append(dict(topic=topic,data=json.loads(msg.data)))
            elif isinstance(msg,TFMessage):
                t=TransformStamped();t.header.stamp.sec=value;t.header.frame_id='map';t.child_frame_id=name+'/odom';t.transform.rotation.w=1.;msg.transforms=[t]
            else:
                msg.header.stamp.sec=value
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=100;msg.info.height=60;msg.info.resolution=.1;msg.info.origin.orientation.w=1.;msg.data=[0]*6000
                else:
                    msg.header.frame_id=name+'/odom';msg.pose.pose.position.x,msg.pose.pose.position.y=positions[name];msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def fresh(value):
        for _ in range(12):tick(value);deliver(value);time.sleep(.03)
        until(lambda:head.now()==value and head.fresh_robot_inputs() and all(t==value for t in head.robot_odom_received_at.values()))
    def invoke(stage):
        finished.clear();trigger.publish(String(data=stage));assert finished.wait(12.) and not errors,errors
    try:
        until(lambda:trigger.get_subscription_count()==1 and head.robot_nav_clients['tb1'].server_is_ready())
        fresh(8);invoke('ordinary');assert entered.wait(12.)
        until(lambda:head.goal_handles['tb1'] is not None)
        accepted=head.goal_started_at['tb1'];assert accepted==8.
        epoch=68 if scenario=='timeout' else 29 if scenario=='no_progress' else 12
        fresh(epoch)
        if scenario=='expired':
            module.plan_rally_leg=blocked;finished.clear();trigger.publish(String(data='cancel'))
            assert calculation.wait(12.)
            for _ in range(12):tick(15);time.sleep(.02)
            until(lambda:head.now()==15.);calculation_release.set()
            assert finished.wait(12.) and not errors,errors
        else:invoke('cancel')
        preserved=label=='current' and scenario=='funded'
        if preserved:
            assert not head.cancel_requested['tb1'] and not cancels and not requests
            until(lambda:any(e.get('event')=='coordinator_initial_exploration_completion_hold' for e in events))
        else:
            until(lambda:bool(cancels));assert head.cancel_requested['tb1']
            assert not any(e.get('event')=='coordinator_initial_exploration_completion_hold' for e in events)
        release.set();until(lambda:head.goal_handles['tb1'] is None and head.robot_states['tb1']=='idle')
        assert head.successful_exploration_legs.get('tb1',0)==int(preserved)
        if preserved:
            positions['tb1']=[3.5,3.];fresh(13);invoke('charge');until(lambda:len(requests)==1)
            assert requests[0]['reason']=='initial_near_home_replenishment' and requests[0]['required_energy']==80.
        else:
            fresh(70);invoke('charge');assert not requests
        assert goals==[[3.5,3.]] and not errors
        return dict(status='PASS',label=label,scenario=scenario,accepted_at_sec=accepted,goals=goals,
            cancel_count=len(cancels),ordinary_future_successes=head.successful_exploration_legs.get('tb1',0),requests=requests,
            callbacks=callbacks,private_events=events,controlled_battery_sources=native_sources,
            no_gazebo_or_physical_nav2_motion=True,no_native_charge_cycle=True)
    finally:
        module.plan_rally_leg=original_plan;module.HeadquartersControl.has_funded_frontier_alternative=original_alternative
        release.set();calculation_release.set();server.destroy()
        for ex in executors:ex.shutdown()
        for t in threads:t.join(5.);assert not t.is_alive()
        head.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists() and os.environ.get('ROS_DOMAIN_ID') in ('216','217')
    source=subprocess.check_output(['rtk','proxy','git','show',REFERENCE+':'+SOURCE],text=True)
    old=types.ModuleType('frozen_initial_goal');old.__file__=current.__file__;old.__package__='multi_robot_exploration';sys.modules[old.__name__]=old
    exec(compile(source,'<d0be454 frozen>','exec'),old.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2','-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        cases=[case(old,'frozen','funded')]+[case(current,'current',s) for s in ['funded','expired','timeout','no_progress']]
        out=dict(status='PASS',reference_commit=REFERENCE,reference_control_sha256=hashlib.sha256(source.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),cases=cases,all_owned_closed=True,
            scope='Actual isolated DDS/ActionClient Futures with controlled static map, pose and battery samples. Funded continuation and normal charge request only; no native charge credit, physical Nav2/Gazebo, task causality or hard deadline guarantee.')
        out['controlled_predicate'] = 'Both full versions use an explicit funded-frontier-alternative=True test stimulus; actual geometry, freshness, continuation budget and ActionClient/Future handling remain real. This is not an end-to-end frontier-choice test.'
        args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(status='PASS',cases=[{k:r[k] for k in ['label','scenario','cancel_count','ordinary_future_successes']} for r in cases])))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
