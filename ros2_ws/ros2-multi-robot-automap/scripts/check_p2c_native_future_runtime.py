#!/usr/bin/env python3
"""Actual native node/Future mutation under a blocked serialized state callback."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import types

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.task import Future
from multi_robot_exploration import battery_manager as current
from multi_robot_exploration import action_callbacks

REFERENCE='f0fe12ca4396be79979296ebf2f72aeaff69216f'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/battery_manager.py'


def case(manager_class,label):
    node=manager_class();node.timer.cancel();executor=MultiThreadedExecutor(num_threads=2)
    executor.add_node(node);entered=threading.Event();finished=threading.Event();errors=[];observed={}
    future=Future(executor=executor)
    if hasattr(node,'defer_action_done_callback'):node.defer_action_done_callback(future,node.return_goal_response)
    else:future.add_done_callback(node.return_goal_response)
    node.return_goal_pending=True
    def blocked():
        timer.cancel();entered.set();time.sleep(.5)
        observed['return_owner_mutated_during_state_callback']=not node.return_goal_pending
        finished.set()
    timer=node.create_timer(.01,blocked)
    def spin():
        try:executor.spin()
        except Exception as e:errors.append(repr(e))
    thread=threading.Thread(target=spin);thread.start()
    try:
        assert entered.wait(5.)
        future.set_result(types.SimpleNamespace(accepted=False))
        assert finished.wait(5.)
        deadline=time.monotonic()+5.
        while node.return_goal_pending and time.monotonic()<deadline:time.sleep(.01)
        assert not node.return_goal_pending and node.return_rejections==1 and not errors,errors
        observed.update(status='PASS',label=label,return_rejections=node.return_rejections,
            energy=node.energy,mode=node.mode)
        return observed
    finally:
        if hasattr(node,'shutdown_requested'):node.shutdown_requested=True
        timer.cancel();executor.shutdown();thread.join(timeout=5.)
        assert not thread.is_alive();node.destroy_node()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('do not overwrite runtime evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    old=types.ModuleType('p2c_frozen_native_future');old.__file__=current.__file__
    old.__package__='multi_robot_exploration';sys.modules[old.__name__]=old
    exec(compile(source,'<frozen battery manager>', 'exec'),old.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=false','-p','robot_name:=future_probe'])
    try:
        before=case(old.BatteryManager,'frozen_direct_future');after=case(current.BatteryManager,'current_grouped_future')
        assert before['return_owner_mutated_during_state_callback'] and not after['return_owner_mutated_during_state_callback']
        assert before['energy']==after['energy']==40. and before['mode']==after['mode']=='ACTIVE'
        result=dict(status='PASS',scope='Actual ROS native node, two-worker executor, real Future and real return_goal_response; controlled blocked callback and synthetic rejected handle; no Nav2/Gazebo motion or CPU bound claim',
            reference_commit=REFERENCE,reference_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            current_source_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            action_dispatcher_sha256=hashlib.sha256(Path(action_callbacks.__file__).read_bytes()).hexdigest(),cases=[before,after])
        a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
