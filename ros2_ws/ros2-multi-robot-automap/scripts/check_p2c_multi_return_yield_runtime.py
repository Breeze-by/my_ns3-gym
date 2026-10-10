#!/usr/bin/env python3
"""Actual DDS/Futures with original v57 geometry and synthetic fresh sources."""
import argparse
import copy
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
from p2c_outbound_routes import audit_outbound, decode
from p2c_return_preparation import audit_preparation

REFERENCE = 'abd9822c486b487af0999b6f20e58f150fb29cb0'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def until(predicate, timeout=12.):
    deadline = time.monotonic()+timeout
    while not predicate() and time.monotonic() < deadline:time.sleep(.02)
    assert predicate(), 'bounded probe wait expired'


def case(module, label, original):
    node = module.HeadquartersControl()
    for timer in node.timers:timer.cancel()
    probe = Node('p2c_multi_return_'+label, use_global_arguments=False)
    executors = [MultiThreadedExecutor(num_threads=2), MultiThreadedExecutor(num_threads=2)]
    for executor, member in zip(executors, (node, probe)):executor.add_node(member)
    threads = [threading.Thread(target=e.spin) for e in executors]
    for thread in threads:thread.start()
    saved = original['return_preparation'];states = copy.deepcopy(saved['battery_states'])
    if label.endswith('uncovered'):states['tb2'].update(mode='ACTIVE', return_count=1)
    if label.endswith('unfundable'):states['tb3']['energy'] = .1
    topics = {'/merge_map':OccupancyGrid}
    for name in states:
        topics.update({f'/gateway/received/{name}/map':OccupancyGrid,
            f'/gateway/received/{name}/odom':Odometry, f'/gateway/received/{name}/tf':TFMessage,
            f'/gateway/received/{name}/battery_state':String})
    publishers = {topic:probe.create_publisher(kind, topic,
        QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL) if kind is String else 10)
        for topic,kind in topics.items()}
    clock = probe.create_publisher(Clock, '/clock', 10)
    trigger = probe.create_publisher(String, '/p2c_multi_return/run', 10)
    finished = threading.Event();release = threading.Event();goals = [];canceled = [];events = [];errors = []
    subscriptions = [probe.create_subscription(String, node.consumed_publisher.topic_name,
        lambda msg:events.append(json.loads(msg.data)), 10)]
    def execute(handle):
        goals.append((handle.request.pose.pose.position.x, handle.request.pose.pose.position.y))
        deadline = time.monotonic()+20.
        while time.monotonic() < deadline:
            if handle.is_cancel_requested:
                canceled.append(node.now());handle.canceled();return NavigateToPose.Result()
            if release.is_set():handle.succeed();return NavigateToPose.Result()
            time.sleep(.02)
        handle.abort();errors.append('synthetic action deadline expired');return NavigateToPose.Result()
    server = ActionServer(probe, NavigateToPose, '/gateway/tb3/navigate_to_pose', execute,
        cancel_callback=lambda request:CancelResponse.ACCEPT)
    def run(message):
        try:
            node.pending_exploration_return_yield = dict(robot='tb3', returning='tb1', task_phase='EXPLORE',
                refuge=module.RallyPose(*original['requested_position'], original['requested_yaw']))
            module.HeadquartersControl.admit_exploration_return_yield(node)
        except Exception as error:errors.append(repr(error))
        finished.set()
    subscriptions.append(node.create_subscription(String, '/p2c_multi_return/run', run, 10))
    def tick(value):
        msg = Clock();msg.clock.sec = int(value);clock.publish(msg)
    def deliver(value):
        for topic, publisher in publishers.items():
            msg = topics[topic]()
            if isinstance(msg, String):
                name = topic.split('/')[3];msg.data = json.dumps({**states[name], 'stamp_sec':value})
            elif isinstance(msg, TFMessage):
                name = topic.split('/')[3];tf = TransformStamped();tf.header.stamp.sec = int(value)
                tf.header.frame_id = 'map';tf.child_frame_id = name+'/odom';tf.transform.rotation.w = 1.;msg.transforms = [tf]
            else:
                msg.header.stamp.sec = int(value)
                if isinstance(msg, OccupancyGrid):
                    row = saved['source_map'] if topic == '/merge_map' else saved['return_maps'][topic.split('/')[3]]
                    msg.header.frame_id = 'map';msg.info.height, msg.info.width = row['shape'];msg.info.resolution = row['resolution']
                    msg.info.origin.position.x, msg.info.origin.position.y = row['origin'];msg.info.origin.orientation.w = 1.
                    msg.data = decode(row).ravel().tolist()
                else:
                    name = topic.split('/')[3];msg.header.frame_id = name+'/odom'
                    msg.pose.pose.position.x, msg.pose.pose.position.y = saved['robot_positions'][name]
                    msg.pose.pose.orientation.w = 1.
            publisher.publish(msg)
    def consume(value):
        def ready():
            return (node.now() == value and all(node.robot_odom_received_at[n] == node.robot_tf_received_at[n]
                == node.robot_map_received_at[n] == node.battery_state_received_at[n] == value
                and node.battery_states[n]['return_count'] == states[n]['return_count'] for n in states))
        deadline = time.monotonic()+12.
        while not ready() and time.monotonic() < deadline:
            tick(value);deliver(value);time.sleep(.03)
        assert ready(), 'fresh DDS inputs were not consumed'
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in publishers.values()))
        until(lambda:node.robot_nav_clients['tb3'].server_is_ready())
        consume(10.)
        if label.endswith('stale'):
            while node.now()!=13.:tick(13.);time.sleep(.02)
        trigger.publish(String(data='admit'))
        assert finished.wait(12.) and not errors, errors
        if label.endswith(('stale','unfundable')):
            assert not goals and not any(e.get('event')=='coordinator_navigation_decision' for e in events)
            assert node.pending_exploration_return_yield
        elif label == 'frozen':
            until(lambda:len(canceled)==1 and node.goal_handles['tb3'] is None and node.robot_states['tb3']=='idle')
            assert len(goals)==1
        else:
            until(lambda:len(goals)==1 and node.goal_handles['tb3'] is not None)
            if label.endswith('new_cycle'):states['tb2']['return_count'] += 1
            if label.endswith('uncovered'):states['tb2'].update(mode='RETURNING', return_count=2)
            if label.endswith('own_return'):states['tb3'].update(mode='RETURNING', return_count=3)
            consume(11.)
            if label.endswith(('new_cycle','uncovered','own_return')):
                until(lambda:len(canceled)==1 and node.goal_handles['tb3'] is None)
            else:
                time.sleep(.1)
                assert not canceled and not node.cancel_requested['tb3'] and node.goal_handles['tb3'] is not None
                release.set()
                until(lambda:node.goal_handles['tb3'] is None and node.robot_states['tb3']=='idle')
                assert not node.successful_exploration_legs and not node.exploration_return_yields
        relevant = [e for e in events if e.get('kind')=='exploration_return_yield']
        assert len(relevant)==len(goals)
        audits = [dict(preparation=audit_preparation(e), vertices=audit_outbound(e)) for e in relevant]
        assert not errors, errors
        return dict(label=label, status='PASS', synthetic_goals=goals, canceled_at=canceled,
            private_events=relevant, independent_audits=audits, action_futures_closed=True,
            source_stamps_preserved=True, physical_nav2_motion=False)
    finally:
        release.set()
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        server.destroy();node.destroy_node();probe.destroy_node()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():parser.error('do not overwrite evidence')
    assert os.environ.get('ROS_DOMAIN_ID') in ('216','217'), 'use an isolated component domain'
    root = Path(__file__).resolve().parents[1]
    directory = root/'log/p2c/20261010_p2c_v57/20261010_p2c_v57_dev_corridors303'
    original = next(e for e in map(json.loads,(directory/'ledger.jsonl').open())
        if e.get('kind')=='exploration_return_yield' and e['event_time']==276.7)
    assert json.loads((directory/'summary.json').read_text())['git_commit']==REFERENCE
    assert audit_preparation(original)=='yield' and audit_outbound(original)>0
    old = subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen = types.ModuleType('p2c_frozen_multi_return');frozen.__file__ = current.__file__
    frozen.__package__ = 'multi_robot_exploration';sys.modules[frozen.__name__] = frozen
    exec(compile(old,'<frozen original>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=3',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        cases = [case(frozen,'frozen',original)]
        cases += [case(current,label,original) for label in ('current','current_new_cycle',
            'current_uncovered','current_own_return','current_stale','current_unfundable')]
        result = dict(status='PASS',scope='Original v57 map/pose/energy geometry with synthetic refreshed stamps, actual DDS and ActionServer/Futures. No physical Nav2 motion, exact task replay or causal task benefit.',
            reference_commit=REFERENCE, reference_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            original_event=original, cases=cases, all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=r['label'],goals=len(r['synthetic_goals']),canceled=len(r['canceled_at'])) for r in cases])))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
