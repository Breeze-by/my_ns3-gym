#!/usr/bin/env python3
"""Compare transit and fallback yaw at actual DDS/ActionServer boundaries."""
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

import rclpy
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.action import ActionServer, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from check_p2c_dispatch_boundary_runtime import until
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_rally_transit_heading import transit_heading_audit

REFERENCE='14a4fe8893a5361ee26acd55707be5b4d34a6880'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module,label):
    node=module.HeadquartersControl(); probe=Node('p2c_transit_'+label,use_global_arguments=False)
    for timer in node.timers:timer.cancel()
    executors=[MultiThreadedExecutor(num_threads=2),MultiThreadedExecutor(num_threads=2)]
    executors[0].add_node(node);executors[1].add_node(probe)
    threads=[threading.Thread(target=e.spin) for e in executors]
    for thread in threads:thread.start()
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_rally_transit/run',10)
    detection_qos=QoSProfile(depth=1)
    detection_qos.durability=DurabilityPolicy.TRANSIENT_LOCAL
    detection_qos.reliability=ReliabilityPolicy.RELIABLE
    detection=probe.create_publisher(String,'/gateway/received/target_detection',detection_qos)
    topics={'/merge_map':OccupancyGrid}
    for name in ('tb1','tb2'):
        topics.update({f'/gateway/received/{name}/map':OccupancyGrid,
                       f'/gateway/received/{name}/odom':Odometry,f'/gateway/received/{name}/tf':TFMessage})
    pubs={topic:probe.create_publisher(kind,topic,10) for topic,kind in topics.items()}
    events=[];goals=[];errors=[];finished=threading.Event();drained=threading.Event()
    original_result=node.rally_goal_result
    def result(*args):original_result(*args);drained.set()
    node.rally_goal_result=result
    def goal(request):
        p=request.pose.pose;stamp=request.pose.header.stamp
        goals.append(dict(yaw=2*math.atan2(p.orientation.z,p.orientation.w),
            header_time=stamp.sec+stamp.nanosec*1e-9,position=[p.position.x,p.position.y]))
        return GoalResponse.ACCEPT
    def execute(handle):handle.succeed();return NavigateToPose.Result()
    server=ActionServer(probe,NavigateToPose,'/gateway/tb1/navigate_to_pose',
        execute_callback=execute,goal_callback=goal)
    audit=probe.create_subscription(String,'/gateway/consumed',lambda msg:events.append(json.loads(msg.data)),100)
    def run(message):
        try:
            node.send_rally_goal('tb1',(module.RallyPose(2.05,1.55,math.atan2(.5,1.)),((1.05,1.05),(2.05,1.55))))
        except Exception as error:errors.append(repr(error))
        finally:finished.set()
    subscription=node.create_subscription(String,'/p2c_rally_transit/run',run,10)
    def stamp(value,dest):dest.sec=int(value);dest.nanosec=round((value-int(value))*1e9)
    def tick(value):msg=Clock();stamp(value,msg.clock);clock.publish(msg)
    def deliver(value):
        for topic,pub in pubs.items():
            msg=topics[topic]();name='tb2' if '/tb2/' in topic else 'tb1'
            if isinstance(msg,TFMessage):
                t=TransformStamped();stamp(value,t.header.stamp);t.header.frame_id='map'
                t.child_frame_id=name+'/odom';t.transform.rotation.w=1.;msg.transforms=[t]
            else:
                stamp(value,msg.header.stamp)
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=msg.info.height=60
                    msg.info.resolution=.1;msg.info.origin.orientation.w=1.;msg.data=[0]*3600
                else:
                    msg.header.frame_id=name+'/odom'
                    msg.pose.pose.position.x=msg.pose.pose.position.y=3.05 if name=='tb2' else 1.05
                    yaw=math.pi if name=='tb2' else math.atan2(2.,1.)
                    msg.pose.pose.orientation.z=math.sin(yaw/2);msg.pose.pose.orientation.w=math.cos(yaw/2)
            pub.publish(msg)
    try:
        until(lambda:trigger.get_subscription_count()==1 and detection.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values())
              and node.robot_nav_clients['tb1'].server_is_ready() and node.consumed_publisher.get_subscription_count()==1,10.)
        for _ in range(10):tick(10.);time.sleep(.02)
        until(lambda:node.now()==10.)
        for _ in range(10):deliver(10.);time.sleep(.02)
        until(node.fresh_robot_inputs)
        # Synthetic stationary-object context; poses/maps/clocks and actions use DDS.
        node.task_state='RALLY';node.target=(2.05,3.05)
        node.rally_targets={'tb1':module.RallyPose(1.05,3.05,.5),'tb2':module.RallyPose(3.05,3.05,math.pi)}
        node.rally_arrived['tb2']=True
        def confirm(robot,value):
            detection.publish(String(data=json.dumps(dict(robot=robot,target_x=2.05,target_y=3.05,
                max_distance_m=3.,field_of_view_deg=90.,stamp_sec=value,
                _gateway=dict(source_time=value,delivery_time=value)))))
        confirm('tb2',10.)
        until(lambda:node.target_received_source_time==10. and node.target_observing_robot=='tb2')
        for _ in range(10):tick(10.1);time.sleep(.02)
        until(lambda:node.now()==10.1)
        for _ in range(10):deliver(10.1);time.sleep(.02)
        until(node.fresh_robot_inputs)
        confirm('tb1',10.1)
        until(lambda:node.target_received_source_time==10.1 and node.target_observing_robot=='tb1')
        for index,value in enumerate((10.1,15.1)):
            if index:
                for _ in range(10):tick(value);time.sleep(.02)
                until(lambda:node.now()==value)
                for _ in range(10):deliver(value);time.sleep(.02)
                until(lambda:node.fresh_robot_inputs() and node.robot_odom_received_at['tb2']==value)
            finished.clear();drained.clear();trigger.publish(String(data=str(index)))
            assert finished.wait(5.) and not errors,errors
            until(lambda:len(goals)==index+1)
            assert drained.wait(5.)
        until(lambda:sum(e['event']=='coordinator_navigation_decision' for e in events)==2)
        assert math.isclose(goals[0]['yaw'],math.atan2(.5,1.) if label=='current' else math.pi/2,abs_tol=1e-8)
        assert math.isclose(goals[1]['yaw'],math.pi/2,abs_tol=1e-8)
        assert node.target_received_source_time==10.1
        assert node.rally_targets['tb1']==module.RallyPose(1.05,3.05,.5)
        with tempfile.TemporaryDirectory() as directory:
            ledger=Path(directory)/'ledger.jsonl';ledger.write_text(''.join(json.dumps(e)+'\n' for e in events))
            audits=dict(dispatch=navigation_dispatch_audit(ledger,True),
                        transit=transit_heading_audit(ledger,True))
        assert audits['transit']['supported_intermediate_legs']==int(label=='current')
        return dict(status='PASS',label=label,action_server_goals=goals,private_events=events,
                    independent_audits=audits,original_peer_confirmation_source_unchanged=10.,
                    original_latest_confirmation_source_unchanged=10.1,results_consumed_before_teardown=True)
    finally:
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        server.destroy();node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    old=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_frozen_transit');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(old,'<frozen P2C control>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2','-p',
        'enable_battery:=false','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        rows=[case(frozen,'frozen'),case(current,'current')]
        result=dict(status='PASS',scope='Actual isolated DDS input/clock and ActionServer/Future, synthetic stationary-target context/free map; no mission, latency or hardware safety guarantee',
            reference_commit=REFERENCE,reference_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),cases=rows,
            reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_rally_transit_heading.py').read_bytes()).hexdigest(),
            dispatch_reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_navigation_dispatch.py').read_bytes()).hexdigest())
        args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
