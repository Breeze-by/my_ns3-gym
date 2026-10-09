#!/usr/bin/env python3
"""Compare actual DDS source consumption after a controlled slow rally search."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import types

import numpy as np
import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current

REFERENCE='dbacbbf336e482871e3a25eff3ce178c962e2b76'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module,label):
    node=module.HeadquartersControl();publisher=Node('p2c_handoff_probe_'+label,use_global_arguments=False)
    for timer in node.timers:timer.cancel()
    executor=MultiThreadedExecutor(num_threads=2);executor.add_node(node)
    thread=threading.Thread(target=executor.spin);thread.start()
    clock=publisher.create_publisher(Clock,'/clock',10)
    trigger=publisher.create_publisher(String,'/p2c_handoff_probe/run',10)
    topics={'/merge_map':OccupancyGrid,'/gateway/received/tb1/map':OccupancyGrid,
        '/gateway/received/tb1/odom':Odometry,'/gateway/received/tb1/tf':TFMessage}
    pubs={topic:publisher.create_publisher(kind,topic,10) for topic,kind in topics.items()}
    entered=threading.Event();finished=threading.Event();observed=[];calls=[];errors=[]
    original=module.assign_rally_poses
    def slow(*args,**kwargs):
        result=original(*args,**kwargs);calls.append(node.now());entered.set()
        time.sleep(.6)  # Controlled callback delay, not a CPU benchmark.
        return result
    module.assign_rally_poses=slow
    def run(message):
        try:
            module.HeadquartersControl.update_mission(node)
            observed.append(dict(clock=node.now(),source=node.robot_odom_received_at['tb1'],
                phase=node.task_state,pending=bool(getattr(node,'pending_rally_proposal',None))))
        except Exception as error:errors.append(repr(error))
        finished.set()
    subscription=node.create_subscription(String,'/p2c_handoff_probe/run',run,10)
    def tick(value):
        msg=Clock();msg.clock.sec=int(value);msg.clock.nanosec=round((value-int(value))*1e9);clock.publish(msg)
    def deliver(value):
        for topic,pub in pubs.items():
            msg=topics[topic]()
            if isinstance(msg,TFMessage):
                t=TransformStamped();t.header.stamp.sec=int(value);t.header.frame_id='map'
                t.child_frame_id='tb1/odom';t.transform.rotation.w=1.;msg.transforms=[t]
            else:
                msg.header.stamp.sec=int(value)
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=msg.info.height=50
                    msg.info.resolution=.1;msg.info.origin.orientation.w=1.;msg.data=[0]*2500
                else:
                    msg.header.frame_id='tb1/odom';msg.pose.pose.position.x=1.05
                    msg.pose.pose.position.y=2.05;msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    try:
        deadline=time.monotonic()+10.
        while time.monotonic()<deadline:
            if trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values()) and clock.get_subscription_count()==1:break
            time.sleep(.02)
        assert trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values())
        deadline=time.monotonic()+5.
        while node.now()!=10. and time.monotonic()<deadline:tick(10.);time.sleep(.02)
        assert node.now()==10.
        deadline=time.monotonic()+5.
        while not node.fresh_robot_inputs() and time.monotonic()<deadline:deliver(10.);time.sleep(.03)
        assert node.fresh_robot_inputs()
        node.target=(3.05,2.05);node.target_received_source_time=10.;node.task_state='FOUND'
        node.detecting_robot='tb1';node.last_input_availability=True
        for attempt in range(2):
            entered.clear();finished.clear();trigger.publish(String(data=str(attempt)))
            # The new second callback admits the retained geometry immediately.
            if attempt==1 and label=='current':assert finished.wait(5.);break
            assert entered.wait(5.)
            new_time=13.+3.*attempt
            for _ in range(12):tick(new_time);deliver(new_time);time.sleep(.02)
            assert finished.wait(5.) and not errors,errors
            deadline=time.monotonic()+5.
            while (node.robot_odom_received_at['tb1']!=new_time or node.robot_tf_received_at['tb1']!=new_time or not node.fresh_robot_inputs()) and time.monotonic()<deadline:
                deliver(new_time);time.sleep(.02)
            assert node.robot_odom_received_at['tb1']==node.robot_tf_received_at['tb1']==new_time
        assert not errors,errors
        if label=='current':
            assert len(calls)==1 and node.task_state=='RALLY' and len(node.rally_targets)==1
            assert observed[0]==dict(clock=13.,source=10.,phase='FOUND',pending=True)
            assert observed[1]==dict(clock=13.,source=13.,phase='RALLY',pending=False)
        else:
            assert len(calls)==2 and node.task_state=='FOUND' and not node.rally_targets
            assert observed[0]==dict(clock=13.,source=10.,phase='FOUND',pending=False)
            assert observed[1]==dict(clock=16.,source=13.,phase='FOUND',pending=False)
        assert node.goal_handles['tb1'] is None and node.rally_goal_handles['tb1'] is None
        assert not node.rally_charge_requested
        return dict(status='PASS',label=label,searches=len(calls),callbacks=observed,
            original_state_group_serial=True,source_stamps_preserved=True,navigation_goals=0)
    finally:
        module.assign_rally_poses=original
        executor.shutdown();thread.join(timeout=5.);assert not thread.is_alive()
        node.destroy_node();publisher.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite runtime evidence')
    old=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_frozen_handoff');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(old,'<frozen P2C control>', 'exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=1',
        '-p','enable_battery:=false','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        result=dict(status='PASS',scope='Actual isolated DDS and serial state callbacks with a controlled delay and synthetic map; no mission, latency or Wi-Fi claim',
            reference_commit=REFERENCE,reference_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen'),case(current,'current')])
        args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
