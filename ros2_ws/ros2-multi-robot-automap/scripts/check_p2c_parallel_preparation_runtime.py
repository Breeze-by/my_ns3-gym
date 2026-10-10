#!/usr/bin/env python3
"""Probe FOUND preparation through actual isolated DDS and deferred action Futures."""
import argparse
import base64
import copy
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
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rclpy.serialization import serialize_message
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from check_p2c_dispatch_boundary_runtime import until
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_outbound_routes import decode
from p2c_preparation_approach import preparation_approach_audit

REFERENCE='7e0222c5f5ff8cd005fb177f346a4a0a73c113f2'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'
FIXTURE=Path(__file__).parents[1]/'src/multi_robot_exploration/test/fixtures/p2c_v68_preparation_inputs.json.gz'


def case(module,label,ledger):
    with gzip.open(FIXTURE,'rt') as f:data=json.load(f)
    failed=data['failed_assignment'];survey=data['original_survey'];positions=failed['robot_positions']
    node=module.HeadquartersControl();probe=Node('p2c_preparation_'+label,use_global_arguments=False)
    for timer in node.timers:timer.cancel()
    executors=[MultiThreadedExecutor(num_threads=2),MultiThreadedExecutor(num_threads=4)]
    for executor,member in zip(executors,(node,probe)):executor.add_node(member)
    threads=[threading.Thread(target=e.spin) for e in executors]
    for thread in threads:thread.start()
    topics={'/merge_map':OccupancyGrid}
    for name in positions:
        topics.update({f'/gateway/received/{name}/'+suffix:kind for suffix,kind in
            [('map',OccupancyGrid),('odom',Odometry),('tf',TFMessage),('battery_state',String)]})
    pubs={topic:probe.create_publisher(kind,topic,QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if kind is String else 10) for topic,kind in topics.items()}
    clock=probe.create_publisher(Clock,'/clock',10);trigger=probe.create_publisher(String,'/p2c_preparation/run',10)
    events=[];raw=[];goals=[];errors=[];requests=[];done=threading.Event()
    survey_finish=threading.Event();accept_release=threading.Event();cancel_release=threading.Event()
    cancel_seen=threading.Event();peer_entered=threading.Event();teardown=threading.Event()
    if label!='late_acceptance':accept_release.set()
    def stamp(value,dest):dest.sec,dest.nanosec=divmod(round(value*1e9),10**9)
    def tick(value):msg=Clock();stamp(value,msg.clock);clock.publish(msg)
    def goal(request,name):
        p=request.pose.pose.position;h=request.pose.header.stamp
        goals.append(dict(robot=name,position=[p.x,p.y],source_time=h.sec+h.nanosec/1e9))
        if name=='tb2':peer_entered.set();assert accept_release.wait(10.)
        return GoalResponse.ACCEPT
    def execute(handle,name):
        deadline=time.monotonic()+20.
        while time.monotonic()<deadline:
            if handle.is_cancel_requested:
                if name=='tb2':cancel_seen.set();assert cancel_release.wait(10.)
                handle.canceled();return NavigateToPose.Result()
            if teardown.is_set() or name=='tb1' and survey_finish.is_set():
                handle.succeed();return NavigateToPose.Result()
            time.sleep(.01)
        handle.abort();return NavigateToPose.Result()
    servers=[ActionServer(probe,NavigateToPose,f'/gateway/{name}/navigate_to_pose',
        execute_callback=lambda handle,name=name:execute(handle,name),
        goal_callback=lambda request,name=name:goal(request,name),
        cancel_callback=lambda handle:CancelResponse.ACCEPT,callback_group=ReentrantCallbackGroup()) for name in positions]
    audit_sub=probe.create_subscription(String,'/gateway/consumed',lambda msg:events.append(json.loads(msg.data)),100)
    def run(msg):
        try:
            if msg.data=='survey':
                node.task_state='FOUND';node.target=tuple(failed['target']);node.target_received_source_time=node.now()
                node.detecting_robot=node.target_observing_robot='tb1'
                node.target_survey_choice=copy.deepcopy(survey['target_survey_selection'])
                assert node.send_survey_goal('tb1',module.RallyPose(*survey['requested_position'],survey['requested_yaw']))
            else:
                if msg.data=='target_changed':node.target=(node.target[0]+.1,node.target[1])
                if msg.data=='shutdown':node.shutdown_requested=True
                node.update_mission()
            requests.append(dict(request=msg.data,clock=node.now(),phase=node.task_state,
                prep_pending=node.rally_goal_pending['tb2'],prep_accepted=node.rally_goal_handles['tb2'] is not None))
        except Exception as error:errors.append(repr(error))
        finally:done.set()
    run_sub=node.create_subscription(String,'/p2c_preparation/run',run,10)
    def deliver(value,mode='ACTIVE'):
        for topic,pub in pubs.items():
            name='tb2' if '/tb2/' in topic else 'tb1';kind=topics[topic];msg=kind()
            if kind is String:
                state=copy.deepcopy(failed['battery_states'][name]);state['stamp_sec']=value
                if name=='tb2':
                    state['mode']=mode
                    if label=='unfunded':state['energy']=.1
                msg.data=json.dumps(state)
            elif kind is TFMessage:
                t=TransformStamped();stamp(value,t.header.stamp);t.header.frame_id='map';t.child_frame_id=name+'/odom'
                t.transform.rotation.w=1.;msg.transforms=[t]
                original=copy.deepcopy(msg);stamp(value+.2,original.transforms[0].header.stamp)
                raw.append(dict(topic='/'+name+'/tf',cdr=base64.b64encode(serialize_message(original)).decode()))
            elif kind is Odometry:
                stamp(value,msg.header.stamp);msg.header.frame_id=name+'/odom';msg.pose.pose.orientation.w=1.
                msg.pose.pose.position.x,msg.pose.pose.position.y=positions[name]
                raw.append(dict(topic='/'+name+'/odom',cdr=base64.b64encode(serialize_message(msg)).decode()))
            else:
                saved=failed['source_map'] if topic=='/merge_map' else failed['return_maps'][name]
                stamp(value,msg.header.stamp);msg.header.frame_id='map';msg.info.resolution=saved['resolution']
                msg.info.height,msg.info.width=saved['shape'];msg.info.origin.orientation.w=1.
                msg.info.origin.position.x,msg.info.origin.position.y=saved['origin'];msg.data=decode(saved).ravel().tolist()
                raw.append(dict(topic='/merge_map' if topic=='/merge_map' else '/'+name+'/map',cdr=base64.b64encode(serialize_message(msg)).decode()))
            pub.publish(msg)
    def invoke(value='update'):
        done.clear();trigger.publish(String(data=value));assert done.wait(10.) and not errors,errors
    expected=label not in ('reference','expired','unfunded')
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(pub.get_subscription_count()==1 for pub in pubs.values())
            and node.consumed_publisher.get_subscription_count()==1 and all(client.server_is_ready() for client in node.robot_nav_clients.values()),10.)
        for _ in range(8):tick(10.1);time.sleep(.02)
        until(lambda:node.now()==10.1)
        for _ in range(8):deliver(10.1);time.sleep(.02)
        until(node.fresh_robot_inputs);invoke('survey');until(lambda:node.survey_goal_handle is not None)
        if label=='expired':
            for _ in range(8):tick(13.1);time.sleep(.02)
            until(lambda:node.now()==13.1)
        invoke()
        if expected:until(peer_entered.is_set)
        else:time.sleep(.1);assert [g['robot'] for g in goals]==['tb1']
        if expected and label!='late_acceptance':until(lambda:node.rally_goal_handles['tb2'] is not None)
        invoke();assert len(goals)==(2 if expected else 1)
        assert node.rally_attempts=={'tb1':0,'tb2':0} and node.survey_attempts==1 and not node.rally_targets
        if expected:
            if label=='battery':
                for _ in range(8):deliver(10.1,'RETURNING');time.sleep(.02)
                until(lambda:node.battery_modes['tb2']=='RETURNING')
            elif label=='stale_accepted':
                for _ in range(8):tick(13.1);time.sleep(.02)
                until(lambda:node.now()==13.1);invoke()
            elif label in ('target_changed','shutdown'):invoke(label)
            else:
                survey_finish.set();until(lambda:node.survey_goal_handle is None and not node.survey_goal_pending)
                invoke()
            if label=='late_acceptance':
                assert node.rally_goal_pending['tb2'] and node.rally_yield_requested['tb2']
                accept_release.set()
            until(cancel_seen.is_set);assert node.task_state=='FOUND'
            assert node.rally_goal_pending['tb2'] or node.rally_goal_handles['tb2'] is not None
            assert len(goals)==2 and not node.rally_targets
            shutdown_result=node.rally_goal_handles['tb2'].get_result_async() if label=='shutdown' else None
            cancel_release.set()
            if shutdown_result is not None:
                until(shutdown_result.done);assert shutdown_result.result().status==5
                assert not any(e.get('event')=='coordinator_rally_preparation_finished' for e in events)
            else:
                until(lambda:node.rally_goal_handles['tb2'] is None and not node.rally_goal_pending['tb2'])
                until(lambda:any(e.get('event')=='coordinator_rally_preparation_finished' for e in events))
            assert node.rally_attempts=={'tb1':0,'tb2':0}
        shutdown_survey=node.survey_goal_handle.get_result_async() if label=='shutdown' else None
        survey_finish.set()
        if shutdown_survey is not None:until(shutdown_survey.done);assert shutdown_survey.result().status==4
        else:until(lambda:node.survey_goal_handle is None and not node.survey_goal_pending)
        until(lambda:sum(e.get('event')=='coordinator_navigation_decision' for e in events)==(2 if expected else 1))
        ledger.write_text(''.join(json.dumps(e)+'\n' for e in events))
        capture=ledger.with_suffix('.inputs.jsonl.gz')
        with gzip.open(capture,'wt') as stream:stream.write(''.join(json.dumps(row)+'\n' for row in raw))
        checked=preparation_approach_audit(ledger,True,capture)
        dispatch=navigation_dispatch_audit(ledger,True)
        assert checked['decisions']==int(expected)
        assert checked['closed_futures']==int(expected and label!='shutdown') and checked['pending_at_task_stop']==int(label=='shutdown')
        return dict(status='PASS',label=label,goals=goals,callbacks=requests,preparation_audit=checked,
            dispatch_audit=dispatch,action_server_results_closed=True,
            application_callbacks_consumed=label!='shutdown',shutdown_callbacks_discarded=label=='shutdown',actual_physical_nav2_goals=0)
    finally:
        accept_release.set();cancel_release.set();survey_finish.set();teardown.set()
        for executor in executors:executor.shutdown(timeout_sec=15.)
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        for server in servers:server.destroy()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_preparation_frozen');frozen.__file__=current.__file__;frozen.__package__='multi_robot_exploration'
    sys.modules[frozen.__name__]=frozen;exec(compile(source,'<original v68 FOUND waiting>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2','-p','enable_battery:=true',
        '-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        rows=[case(frozen,'reference',args.output.with_suffix('.reference.jsonl'))]
        rows.extend(case(current,label,args.output.with_suffix('.'+label+'.jsonl')) for label in
            ('funded','expired','unfunded','late_acceptance','battery','target_changed','shutdown','stale_accepted'))
        result=dict(status='PASS',scope='Actual isolated DDS and deferred Futures with original v68 maps/models and synthetic held ActionServers; no physical Nav2 movement or task timing claim',
            reference_commit=REFERENCE,reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),cases=rows,all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=r['label'],goals=len(r['goals']),audit=r['preparation_audit']) for r in rows],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
