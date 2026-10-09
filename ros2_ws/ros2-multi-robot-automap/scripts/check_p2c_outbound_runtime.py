#!/usr/bin/env python3
"""Actual DDS/Future proof for local-obstacle route admission, without Gazebo."""
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
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from p2c_outbound_routes import audit_outbound


REFERENCE = '8be97e281a1b773b3fa4afecf14ea0d952e0c5ec'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def until(predicate, timeout=10.):
    deadline = time.monotonic()+timeout
    while not predicate() and time.monotonic() < deadline:time.sleep(.02)
    assert predicate(), 'bounded DDS probe wait expired'


def case(module, label):
    node = module.HeadquartersControl()
    for timer in node.timers:timer.cancel()
    probe = Node('p2c_outbound_probe_'+label, use_global_arguments=False)
    executors = [MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    for executor, member in zip(executors, (node, probe)):executor.add_node(member)
    threads = [threading.Thread(target=executor.spin) for executor in executors]
    for thread in threads:thread.start()
    clock = probe.create_publisher(Clock, '/clock', 10)
    trigger = probe.create_publisher(String, '/p2c_outbound_probe/run', 10)
    topics = {'/merge_map':OccupancyGrid, '/gateway/received/tb1/map':OccupancyGrid,
        '/gateway/received/tb1/odom':Odometry, '/gateway/received/tb1/tf':TFMessage,
        '/gateway/received/tb1/battery_state':String}
    pubs = {topic:probe.create_publisher(kind, topic,
        QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL) if kind is String else 10)
        for topic, kind in topics.items()}
    events = [];goals = [];callbacks = [];errors = [];done = threading.Event()
    def execute(handle):
        p = handle.request.pose.pose.position;goals.append((p.x,p.y))
        handle.succeed();return NavigateToPose.Result()
    server = ActionServer(probe, NavigateToPose, '/gateway/tb1/navigate_to_pose', execute)
    subscription = probe.create_subscription(String, node.consumed_publisher.topic_name,
        lambda msg:events.append(json.loads(msg.data)), 10)
    pose = module.RallyPose(5.05,2.05,0.)
    def run(msg):
        try:
            # Synthetic target/state setup; all maps/pose/TF/energy arrive on DDS.
            node.task_state = 'RALLY';node.target=(6.05,2.05);node.target_received_source_time=node.now()
            node.rally_targets = node.rally_final_targets = {'tb1':pose}
            node.rally_dispatch_order=['tb1']
            module.HeadquartersControl.prepare_rally_charges(node)
            kwargs = {} if msg.data == 'old_route' else dict(local_map=node.robot_maps['tb1'])
            plan = module.plan_rally_leg(pose, node.map_data, node.resolution, node.origin,
                node.robot_positions['tb1'], visible_only=True, **kwargs)
            module.HeadquartersControl.send_rally_goal(node,'tb1',plan)
            callbacks.append(dict(request=msg.data, clock=node.now(), source=node.robot_map_received_at['tb1'],
                                  pending=node.rally_goal_pending['tb1']))
        except Exception as error:errors.append(repr(error))
        done.set()
    control_subscription = node.create_subscription(String,'/p2c_outbound_probe/run',run,10)
    def tick(stamp):
        msg=Clock();msg.clock.sec=stamp;clock.publish(msg)
    def deliver(stamp):
        for topic, pub in pubs.items():
            msg=topics[topic]()
            if isinstance(msg,String):
                msg.data=json.dumps(dict(stamp_sec=stamp, mode='ACTIVE', energy=80., capacity=100.,
                    charge_target_fraction=.8, charge_x=1.05, charge_y=2.05, charge_radius_m=.8,
                    move_cost_per_m=1., idle_cost_per_sec=.02, nominal_speed_mps=.18,
                    return_path_factor=2., return_safety_margin=8., charge_duration_sec=6.))
            elif isinstance(msg,TFMessage):
                t=TransformStamped();t.header.stamp.sec=stamp;t.header.frame_id='map'
                t.child_frame_id='tb1/odom';t.transform.rotation.w=1.;msg.transforms=[t]
            else:
                msg.header.stamp.sec=stamp
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=80;msg.info.height=60;msg.info.resolution=.1
                    msg.info.origin.orientation.w=1.;msg.data=[0]*4800
                    if topic != '/merge_map':msg.data[20*80+30]=100
                else:
                    msg.header.frame_id='tb1/odom';msg.pose.pose.position.x=1.05
                    msg.pose.pose.position.y=2.05;msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    try:
        until(lambda: trigger.get_subscription_count()==1 and all(pub.get_subscription_count()==1 for pub in pubs.values()))
        until(lambda: clock.get_subscription_count()==1)
        for _ in range(12):tick(10);deliver(10);time.sleep(.03)
        until(lambda: node.now()==10. and node.fresh_robot_inputs() and node.battery_modes['tb1']=='ACTIVE')
        until(node.robot_nav_clients['tb1'].server_is_ready)
        done.clear();trigger.publish(String(data='old_route'));assert done.wait(10.) and not errors,errors
        expected = 1 if label=='frozen' else 0
        until(lambda: not node.rally_goal_pending['tb1'] and node.rally_goal_handles['tb1'] is None)
        assert len(goals)==expected
        if label=='current':
            until(lambda: any(e.get('event')=='coordinator_navigation_map_veto' for e in events))
            done.clear();trigger.publish(String(data='current_route'));assert done.wait(10.) and not errors,errors
            until(lambda: len(goals)==1 and not node.rally_goal_pending['tb1'] and node.rally_goal_handles['tb1'] is None)
            until(lambda: any(e.get('event')=='coordinator_navigation_decision' for e in events))
            decisions=[e for e in events if e.get('event')=='coordinator_navigation_decision']
            assert len(decisions)==1 and audit_outbound(decisions[0]) > 1
            assert decisions[0]['outbound_map_route']['local_map']['source_time']==10.
            assert goals[0] != (5.05,2.05)
            for _ in range(8):tick(13);time.sleep(.02)
            until(lambda: node.now()==13.)
            done.clear();trigger.publish(String(data='current_route'));assert done.wait(10.) and not errors,errors
            assert len(goals)==1 and not node.rally_goal_pending['tb1']
        else:assert abs(goals[0][0]-5.05)<1e-5 and abs(goals[0][1]-2.05)<1e-5
        return dict(status='PASS',label=label,callbacks=callbacks,goals=goals,
            private_decisions=[e for e in events if e.get('event')=='coordinator_navigation_decision'],
            rejected_old_route=label=='current',action_futures_closed=True)
    finally:
        server.destroy()
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_outbound_reference');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(source,'<frozen 8be97 control>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=1',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        result=dict(status='PASS',scope='Isolated real DDS and ActionServer/Futures with synthetic geometry and target; no physical navigation, task or causal latency claim',
            reference_commit=REFERENCE,reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_outbound_routes.py').read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen'),case(current,'current')],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status=result['status'],cases=[dict(label=c['label'],goals=len(c['goals'])) for c in result['cases']],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
