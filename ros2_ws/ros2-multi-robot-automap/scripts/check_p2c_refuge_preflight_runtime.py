#!/usr/bin/env python3
"""Conditional original-map refuge preflight checks with actual DDS/Futures."""
import argparse
import base64
import gzip
import hashlib
import json
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
from rclpy.serialization import deserialize_message
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from check_p2c_refuge_release_runtime import until
from p2c_outbound_routes import audit_outbound
from p2c_refuge_release import audit_eligibility

REFERENCE='c5e333160b9f357a5f6836365abd2e742f087705'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'
FIXTURE=Path(__file__).resolve().parents[1]/'src/multi_robot_exploration/test/fixtures/p2c_v61_refuge_preflight_input.json.gz'


def case(module,label,prepared,snapshot):
    node=module.HeadquartersControl()
    for timer in node.timers:timer.cancel()
    probe=Node('p2c_refuge_preflight_'+label+str(prepared),use_global_arguments=False)
    executors=[MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    for executor,member in zip(executors,(node,probe)):executor.add_node(member)
    threads=[threading.Thread(target=executor.spin) for executor in executors]
    for thread in threads:thread.start()
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_refuge_preflight/run',10)
    positions=snapshot['original_hold']['positions'];names=list(positions)
    topics={'/merge_map':OccupancyGrid}
    for name in names:
        topics.update({f'/gateway/received/{name}/'+suffix:kind for suffix,kind in (
            ('map',OccupancyGrid),('odom',Odometry),('tf',TFMessage),('battery_state',String))})
    pubs={topic:probe.create_publisher(kind,topic,QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if kind is String else 10) for topic,kind in topics.items()}
    events=[];goals=[];calls=[];callbacks=[];errors=[];done=threading.Event()
    original_order=module.map_safe_rally_dispatch_order
    def measured_order(*args,**kwargs):
        start=time.perf_counter();result=original_order(*args,**kwargs)
        calls.append(dict(order=result,wall_sec=time.perf_counter()-start));return result
    module.map_safe_rally_dispatch_order=measured_order
    def execute(handle):
        p=handle.request.pose.pose.position;goals.append((p.x,p.y))
        handle.succeed();return NavigateToPose.Result()
    servers=[ActionServer(probe,NavigateToPose,f'/gateway/{n}/navigate_to_pose',execute) for n in names]
    subscription=probe.create_subscription(String,node.consumed_publisher.topic_name,
        lambda msg:events.append(json.loads(msg.data)),10)
    def run(msg):
        try:
            node.task_state='RALLY';node.target=tuple(snapshot['original_proposal']['target'])
            node.target_received_source_time=10.;node.detecting_robot='tb2';node.target_observing_robot='tb2'
            node.rally_final_targets={n:module.RallyPose(*p) for n,p in snapshot['original_proposal']['assignment'].items()}
            node.rally_targets=dict(node.rally_final_targets)
            node.rally_targets['tb1']=module.RallyPose(*node.robot_positions['tb1'],0.)
            node.rally_dispatch_order=['tb2','tb1','tb3'];node.rally_arrived={'tb1':True,'tb2':True,'tb3':False}
            node.return_yield_targets={'tb1':'tb3'};node.rally_yield_targets={'tb1'}
            node.rally_wait_budgets={}
            if msg.data=='low_energy':node.rally_wait_budgets=dict.fromkeys(names,20.)
            elif prepared:module.HeadquartersControl.prepare_rally_charges(node)
            before=len(calls);start=time.perf_counter()
            module.HeadquartersControl.release_return_yields(node)
            elapsed=time.perf_counter()-start
            restored='tb1' not in node.return_yield_targets
            if restored:
                plan=module.plan_rally_leg(node.rally_targets['tb1'],node.map_data,node.resolution,node.origin,
                    node.robot_positions['tb1'],max_distance_m=module.MAX_NAVIGATION_LEG_M,
                    blocked_positions=[p for n,p in node.robot_positions.items() if n!='tb1'],
                    visible_only=False,local_map=node.robot_maps['tb1'])
                module.HeadquartersControl.send_rally_goal(node,'tb1',plan)
            callbacks.append(dict(request=msg.data,clock=node.now(),restored=restored,
                permutation_searches=len(calls)-before,release_wall_sec=elapsed,
                order=node.rally_dispatch_order,wait_budgets=node.rally_wait_budgets))
        except Exception as error:errors.append(repr(error))
        done.set()
    control_subscription=node.create_subscription(String,'/p2c_refuge_preflight/run',run,10)
    def tick(stamp):
        msg=Clock();msg.clock.sec=stamp;clock.publish(msg)
    def deliver(stamp,energy=80.):
        for topic,pub in pubs.items():
            name=next((n for n in names if '/'+n+'/' in topic),'tb1')
            kind=topics[topic]
            if kind is OccupancyGrid:
                native='/merge_map' if topic=='/merge_map' else '/'+name+'/map'
                msg=deserialize_message(base64.b64decode(snapshot['messages'][native]['cdr']),OccupancyGrid)
                msg.header.stamp.sec=stamp;msg.header.stamp.nanosec=0
            else:
                msg=kind()
                if isinstance(msg,String):
                    home={'tb1':(0.,-.45),'tb2':(0.,.45),'tb3':(.45,0.)}[name]
                    msg.data=json.dumps(dict(stamp_sec=stamp,mode='ACTIVE',energy=energy,
                        capacity=100.,charge_target_fraction=.8,charge_x=home[0],charge_y=home[1],
                        charge_radius_m=.8,move_cost_per_m=1.,idle_cost_per_sec=.02,
                        nominal_speed_mps=.18,return_path_factor=2.,return_safety_margin=8.,charge_duration_sec=6.))
                elif isinstance(msg,TFMessage):
                    t=TransformStamped();t.header.stamp.sec=stamp;t.header.frame_id='map';t.child_frame_id=name+'/odom'
                    t.transform.rotation.w=1.;msg.transforms=[t]
                else:
                    msg.header.stamp.sec=stamp;msg.header.frame_id=name+'/odom'
                    msg.pose.pose.position.x,msg.pose.pose.position.y=positions[name]
                    msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def trigger_case(request):
        done.clear();trigger.publish(String(data=request));assert done.wait(15.) and not errors,errors
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values()))
        until(lambda:clock.get_subscription_count()==1)
        for _ in range(12):tick(10);deliver(10);time.sleep(.03)
        until(lambda:node.now()==10. and node.fresh_robot_inputs() and all(m=='ACTIVE' for m in node.battery_modes.values()))
        until(lambda:all(client.server_is_ready() for client in node.robot_nav_clients.values()))
        trigger_case('prepared' if prepared else 'unprepared')
        assert callbacks[0]['restored'] is prepared
        assert callbacks[0]['permutation_searches']==(1 if label=='frozen' else 0)
        until(lambda:not any(node.rally_goal_pending.values()) and not any(node.rally_goal_handles.values()))
        if prepared:
            until(lambda:len(goals)==1 and any(e.get('event')=='coordinator_navigation_decision' for e in events))
            checked=[e for e in events if e.get('event')=='coordinator_return_refuge_release_eligibility']
            assert len(checked)==1 and len(audit_eligibility(checked[0],label=='current'))==2
            decisions=[e for e in events if e.get('event')=='coordinator_navigation_decision']
            assert len(decisions)==1 and audit_outbound(decisions[0])>1
            for _ in range(8):tick(13);time.sleep(.02)
            until(lambda:node.now()==13.)
            trigger_case('expired_sources');assert not callbacks[-1]['restored'] and len(goals)==1
            for _ in range(12):deliver(13,.1);time.sleep(.03)
            until(lambda:node.fresh_robot_inputs() and all(s['energy']==.1 for s in node.battery_states.values()))
            trigger_case('low_energy');assert not callbacks[-1]['restored'] and len(goals)==1
        else:assert not goals and not events
        return dict(status='PASS',label=label,prepared=prepared,callbacks=callbacks,
            searches=calls,goals=goals,events=events,action_futures_closed=True)
    finally:
        module.map_safe_rally_dispatch_order=original_order
        for server in servers:server.destroy()
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_refuge_preflight_reference');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(source,'<frozen c5e refuge>','exec'),frozen.__dict__)
    snapshot=json.loads(gzip.decompress(FIXTURE.read_bytes()))
    assert snapshot['original_commit']==REFERENCE
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=3',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        result=dict(status='PASS',scope=snapshot['scope']+' Actual DDS and ActionServer/Futures; no physical Nav2, task causal or worst-case timing claim.',
            reference_commit=REFERENCE,reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_refuge_release.py').read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            cases=[case(module,label,prepared,snapshot) for prepared in (False,True)
                   for module,label in ((frozen,'frozen'),(current,'current'))],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[{k:r[k] for k in ('label','prepared','callbacks')} for r in result['cases']],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
