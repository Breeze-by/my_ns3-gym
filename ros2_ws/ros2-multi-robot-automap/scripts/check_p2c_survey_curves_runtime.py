#!/usr/bin/env python3
"""Compare survey paths using original geometry and real DDS/action Futures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types

import rclpy
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid,Odometry
from rclpy.action import ActionServer,GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy,QoSProfile
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
import check_p2c_gate as current_gate
from check_p2c_dispatch_boundary_runtime import until
from p2c_outbound_routes import decode,outbound_route_audit
from p2c_navigation_dispatch import navigation_dispatch_audit

REFERENCE='41f6d86b2ac05712e3bc392e39dd5a1e0f58d4c5'
BASE='ros2_ws/ros2-multi-robot-automap/'


def case(module,reader,label,original):
    names=list(original['current_positions']);positions=original['current_positions']
    grids={'/merge_map':original['source_map']}
    grids.update({f'/gateway/received/{n}/map':g for n,g in original['return_maps'].items()})
    node=module.HeadquartersControl()
    for timer in node.timers:timer.cancel()
    if label=='current_no_battery':node.enable_battery=False
    probe=Node('p2c_survey_curves_'+label,use_global_arguments=False)
    executors=[MultiThreadedExecutor(num_threads=2),MultiThreadedExecutor(num_threads=2)]
    for ex,member in zip(executors,(node,probe)):ex.add_node(member)
    threads=[threading.Thread(target=ex.spin) for ex in executors]
    for thread in threads:thread.start()
    topics={topic:OccupancyGrid for topic in grids}
    for name in names:
        topics.update({f'/gateway/received/{name}/'+suffix:kind for suffix,kind in (
            ('odom',Odometry),('tf',TFMessage),('battery_state',String))})
    pubs={topic:probe.create_publisher(kind,topic,
        QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL) if kind is String else 10)
        for topic,kind in topics.items()}
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_survey_curves/run',10)
    events,goals,callbacks,errors=[],[],[],[]
    finished=threading.Event();accept=threading.Event();complete=threading.Event()
    live=label in ('current_pending','current_accepted')
    if label!='current_pending':accept.set()
    if not live:complete.set()
    def goal(name,request):
        p=request.pose.pose.position;goals.append(dict(robot=name,position=[p.x,p.y]))
        assert accept.wait(25.),'pending response did not release'
        return GoalResponse.ACCEPT
    def execute(handle):
        assert complete.wait(25.),'accepted result did not release'
        handle.succeed();return NavigateToPose.Result()
    servers=[ActionServer(probe,NavigateToPose,f'/gateway/{name}/navigate_to_pose',execute_callback=execute,
        goal_callback=lambda request,name=name:goal(name,request)) for name in names]
    consumed=probe.create_subscription(String,'/gateway/consumed',lambda msg:events.append(json.loads(msg.data)),100)
    def run(msg):
        try:
            sent=module.HeadquartersControl.survey_target_frontiers(node,node.robot_positions)
            callbacks.append(dict(clock=node.now(),sent=sent,pending=node.survey_goal_pending,
                accepted=node.survey_goal_handle is not None))
        except Exception as error:errors.append(repr(error))
        finally:finished.set()
    subscription=node.create_subscription(String,'/p2c_survey_curves/run',run,10)
    energies={n:original['battery_states'][n]['energy'] for n in names}
    def tick(value):msg=Clock();msg.clock.sec=value;clock.publish(msg)
    def deliver(value):
        for topic,pub in pubs.items():
            kind=topics[topic];msg=kind();name=next((n for n in names if '/'+n+'/' in topic),names[0])
            if isinstance(msg,String):
                state={**original['battery_states'][name], 'robot':name,'mode':'ACTIVE','stamp_sec':value,
                    'energy':energies[name], '_gateway':dict(source_time=value,delivery_time=value)}
                msg.data=json.dumps(state)
            elif isinstance(msg,TFMessage):
                tf=TransformStamped();tf.header.stamp.sec=value;tf.header.frame_id='map'
                tf.child_frame_id=name+'/odom';tf.transform.rotation.w=1.;msg.transforms=[tf]
            else:
                msg.header.stamp.sec=value
                if isinstance(msg,OccupancyGrid):
                    g=grids[topic];msg.header.frame_id='map';msg.info.height,msg.info.width=g['shape']
                    msg.info.resolution=g['resolution'];msg.info.origin.position.x,msg.info.origin.position.y=g['origin']
                    msg.info.origin.orientation.w=1.;msg.data=decode(g).ravel().tolist()
                else:
                    msg.header.frame_id=name+'/odom';msg.pose.pose.position.x,msg.pose.pose.position.y=positions[name]
                    msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def advance(value,refresh=False):
        for _ in range(8):
            tick(value)
            if refresh:deliver(value)
            time.sleep(.03)
        until(lambda:node.now()==value)
        if refresh:until(node.fresh_robot_inputs)
    def invoke():
        finished.clear();trigger.publish(String(data='run'));assert finished.wait(10.) and not errors,errors
    def closed():return node.survey_goal_handle is None and not node.survey_goal_pending
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(pub.get_subscription_count()==1 for pub in pubs.values())
            and all(client.server_is_ready() for client in node.robot_nav_clients.values())
            and node.consumed_publisher.get_subscription_count()==1)
        advance(10,True)
        node.task_state='FOUND';node.target=tuple(original['target']);node.target_received_source_time=10.
        node.detecting_robot=node.target_observing_robot=original['observer_robot']
        invoke();until(lambda:len(goals)==1)
        expected='tb3' if label!='frozen' and node.enable_battery else 'tb1'
        assert goals[0]['robot']==expected,goals
        if live:
            if label=='current_accepted':until(lambda:node.survey_goal_handle is not None)
            else:assert node.survey_goal_pending
            invoke();assert not callbacks[-1]['sent'] and len(goals)==1
            accept.set();complete.set()
        until(closed)
        advance(13);invoke();assert not callbacks[-1]['sent'] and len(goals)==1
        if node.enable_battery:
            energies={n:.1 for n in names};advance(13,True);invoke()
            assert not callbacks[-1]['sent'] and len(goals)==1
        until(lambda:sum(e.get('event')=='coordinator_navigation_decision' for e in events)==1)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ledger.jsonl';path.write_text(''.join(json.dumps(e)+'\n' for e in events))
            kwargs={} if label=='frozen' else dict(curved_surveys=True)
            audits=dict(survey=reader.target_survey_audit(events,True,3.,.35,**kwargs),
                dispatch=navigation_dispatch_audit(path,True),outbound=outbound_route_audit(path,node.enable_battery))
        decision=next(e for e in events if e.get('event')=='coordinator_navigation_decision')
        return dict(status='PASS',label=label,goals=goals,callbacks=callbacks,private_events=events,
            independent_audits=audits,route_vertices=len(decision['target_survey_selection']['admitted_route']),
            selected_distance_m=decision['target_survey_selection']['admitted_distance_m'],
            expired_sources_rejected=True,unfunded_rejected=node.enable_battery,
            existing_action_preserved=live,action_futures_closed=closed())
    finally:
        accept.set();complete.set()
        for ex in executors:ex.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        for server in servers:server.destroy()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    directory=Path('log/p2c/20261010_p2c_v60/20261010_p2c_v60_dev_rooms202')
    original=next(json.loads(x) for x in (directory/'ledger.jsonl').open() if 'coordinator_rally_assignment_failed' in x)
    source=subprocess.check_output(['git','show',REFERENCE+':'+BASE+'src/multi_robot_exploration/multi_robot_exploration/control.py'],text=True)
    old=types.ModuleType('p2c_survey_curves_reference');old.__file__=current.__file__
    old.__package__='multi_robot_exploration';sys.modules[old.__name__]=old;exec(compile(source,'<frozen v60>','exec'),old.__dict__)
    reader_source=subprocess.check_output(['git','show',REFERENCE+':'+BASE+'scripts/check_p2c_gate.py'],text=True)
    reader=types.ModuleType('p2c_survey_curves_reader');reader.__file__=current_gate.__file__;sys.modules[reader.__name__]=reader
    exec(compile(reader_source,'<frozen v60 reader>','exec'),reader.__dict__);reader.control=old
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=3',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        cases=[case(old,reader,'frozen',original),*[case(current,current_gate,label,original)
            for label in ('current','current_pending','current_accepted','current_no_battery')]]
        result=dict(status='PASS',scope='Original frozen first rooms geometry/models with synthetic refreshed source stamps/target role and actual DDS/ActionServer/Futures; no physical Nav2, exact live replay, or causal task benefit.',
            reference_commit=REFERENCE,reference_source=source,reference_reader_source=reader_source,
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),cases=cases,
            original_geometry=original,all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=c['label'],goals=c['goals'],distance=c['selected_distance_m']) for c in cases],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
