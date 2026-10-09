#!/usr/bin/env python3
"""Actual isolated DDS clock during a blocked state callback; no task motion."""
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
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String

from multi_robot_exploration import control as current

REFERENCE='b2b038c615af9fb728e90f7a57c150e936a9bce5'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(control_class, workers, label):
    node=control_class();publisher=Node('p2c_clock_probe_'+label,use_global_arguments=False)
    executor=SingleThreadedExecutor() if workers==1 else MultiThreadedExecutor(num_threads=workers)
    executor.add_node(node)
    for timer in node.timers:timer.cancel()
    qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT)
    clock=publisher.create_publisher(Clock,'/clock',qos)
    state=publisher.create_publisher(String,'/p2c_clock_probe/normal_state',10)
    entered=threading.Event();finished=threading.Event();state_received=threading.Event();observed={}
    timer=None;worker=None;spin_error=[]
    def spin():
        try:executor.spin()
        except Exception as error:spin_error.append(repr(error))
    thread=threading.Thread(target=spin);thread.start()
    def tick(value):
        msg=Clock();msg.clock.sec=int(value);msg.clock.nanosec=round((value-int(value))*1e9);clock.publish(msg)
    def normal(message):
        observed['normal_state_concurrent']=entered.is_set() and not finished.is_set()
        state_received.set()
    subscription=node.create_subscription(String,'/p2c_clock_probe/normal_state',normal,10)
    try:
        deadline=time.monotonic()+10.
        while (clock.get_subscription_count()!=1 or state.get_subscription_count()!=1) and time.monotonic()<deadline:
            time.sleep(.02)
        assert clock.get_subscription_count()==state.get_subscription_count()==1
        deadline=time.monotonic()+5.
        while node.now()!=1. and time.monotonic()<deadline:tick(1.);time.sleep(.02)
        assert node.now()==1.
        grid=np.zeros((80,80),dtype='<i2');grid.setflags(write=False)
        node.map_data=node.source_map_data=grid;node.resolution=.1;node.origin=(0.,0.)
        node.map_width=node.map_height=80;node.map_received_at=1.1
        node.robot_positions['tb1']=(2.05,3.05)
        node.robot_maps['tb1']=dict(data=grid,resolution=.1,origin=(0.,0.))
        for stamps in (node.robot_odom_received_at,node.robot_tf_received_at,node.robot_map_received_at):
            stamps['tb1']=1.1
        def blocked():
            timer.cancel();observed['begin_sim_time']=node.now();entered.set()
            time.sleep(.6)  # A controlled blocked callback, not a CPU benchmark.
            observed['end_sim_time']=node.now()
            observed['original_sources_still_fresh']=node.fresh_robot_inputs()
            observed['original_pose_source_time']=node.robot_odom_received_at['tb1']
            finished.set()
        timer=node.create_timer(.05,blocked)
        tick(1.1)
        assert entered.wait(5.)
        def advance():
            state.publish(String(data='queued_state'))
            for _ in range(15):tick(4.1);time.sleep(.02)
        worker=threading.Thread(target=advance);worker.start()
        assert finished.wait(5.) and state_received.wait(5.)
        worker.join();assert not spin_error,spin_error
        observed.update(label=label,workers=workers,status='PASS',externally_published_clock=4.1,
            clock_subscription_depth=node._time_source._clock_sub.qos_profile.depth,
            clock_subscription_reliability=node._time_source._clock_sub.qos_profile.reliability.name,
            clock_has_separate_callback_group=node._time_source._clock_sub.callback_group is not node.default_callback_group)
        assert not observed['normal_state_concurrent']
        assert observed['clock_subscription_depth']==1 and observed['clock_subscription_reliability']=='BEST_EFFORT'
        return observed
    finally:
        if worker is not None:worker.join(timeout=5.)
        executor.shutdown();thread.join(timeout=5.);assert not thread.is_alive()
        node.destroy_node();publisher.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--original-only',action='store_true');args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite runtime evidence')
    old=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_frozen_clock_control');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration'
    sys.modules[frozen.__name__]=frozen
    exec(compile(old,'<frozen P2C control>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=1',
        '-p','enable_battery:=false','-p','enable_rally:=false','-p','auto_save_map:=false'])
    try:
        rows=[case(frozen.HeadquartersControl,1,'frozen_single'),case(frozen.HeadquartersControl,2,'frozen_two')]
        for row in rows:
            assert row['begin_sim_time']==row['end_sim_time']==1.1
            assert row['original_sources_still_fresh'] and not row['clock_has_separate_callback_group']
        if not args.original_only:
            row=case(current.HeadquartersControl,2,'current_two');rows.append(row)
            assert row['begin_sim_time']==1.1 and row['end_sim_time']==4.1
            assert not row['original_sources_still_fresh'] and row['clock_has_separate_callback_group']
        result=dict(status='PASS',scope='Actual isolated DDS /clock and serialized state callbacks; synthetic grid and controlled wall sleep, no task/CPU/Wi-Fi claim',
            reference_commit=REFERENCE,reference_control_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),cases=rows)
        args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
