#!/usr/bin/env python3
"""Actual isolated DDS charge-geometry handoff; synthetic inputs, no task motion."""
import argparse
import base64
import copy
import gzip
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
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rclpy.serialization import serialize_message
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from p2c_charge_handoff import charge_geometry_handoff_audit
from p2c_outbound_routes import decode


REFERENCE = '939a77f17b6b21ec0966263d7883f016a71a1ca4'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def until(predicate, timeout=12.):
    deadline = time.monotonic()+timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.02)
    assert predicate(), 'bounded probe wait expired'


def case(module, label, saved, output):
    node = module.HeadquartersControl()
    for timer in node.timers:
        timer.cancel()
    probe = Node('p2c_charge_handoff_'+label, use_global_arguments=False)
    executors = [MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    executors[0].add_node(node)
    executors[1].add_node(probe)
    errors = []
    def spin(executor):
        try:
            executor.spin()
        except Exception as error:
            errors.append(repr(error))
    threads = [threading.Thread(target=spin, args=(executor,)) for executor in executors]
    for thread in threads:
        thread.start()
    clock = probe.create_publisher(Clock, '/clock', 10)
    trigger = probe.create_publisher(String, '/p2c_charge_handoff/run', 10)
    data = saved['diagnostic_inputs']
    positions = copy.deepcopy(data['robot_positions'])
    # Synthetic fresh body inputs deliberately leave the original return corridor
    # clear. This is a DDS protocol probe, with no Gazebo displacement claim.
    positions['tb1'] = [-1.51, -4.25]
    states = copy.deepcopy(data['battery_states'])
    topics = {'/merge_map': OccupancyGrid}
    for name in positions:
        topics.update({f'/gateway/received/{name}/map': OccupancyGrid,
            f'/gateway/received/{name}/odom': Odometry,
            f'/gateway/received/{name}/tf': TFMessage,
            f'/gateway/received/{name}/battery_state': String})
    publishers = {topic: probe.create_publisher(kind, topic,
        QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL) if kind is String else 10)
        for topic, kind in topics.items()}
    events, requests, callbacks, generations, cdrs = [], [], [], [], {}
    subscriptions = [probe.create_subscription(String, node.consumed_publisher.topic_name,
        lambda msg: events.append(json.loads(msg.data)), 10)]
    for name in positions:
        subscriptions.append(probe.create_subscription(String, node.charge_request_publishers[name].topic_name,
            lambda msg: requests.append(json.loads(msg.data)), 10))
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_factor = module.HeadquartersControl.exploration_battery_factor
    original_generate = module.robot_candidate_assignments
    original_visual = module.known_space_search_candidates
    blocked = [False]
    def slow_factor(self, *args):
        result = original_factor(self, *args)
        if not blocked[0]:
            blocked[0] = True
            entered.set()
            assert release.wait(12.), 'controlled blocked callback was not released'
        return result
    def generated(*args, **kwargs):
        generations.append(args[3])
        return original_generate(*args, **kwargs)
    def visual(*args, **kwargs):
        generations.append(args[3])
        return original_visual(*args, **kwargs)
    module.HeadquartersControl.exploration_battery_factor = slow_factor
    module.robot_candidate_assignments = generated
    module.known_space_search_candidates = visual
    def run(message):
        try:
            generations.clear()
            node.initial_search_next = dict(data['initial_search_next'])
            module.HeadquartersControl.assign_idle_robots(node)
            callbacks.append(dict(stage=message.data, clock=node.now(),
                pose_sources=dict(node.robot_odom_received_at), frame_sources=dict(node.robot_tf_received_at),
                generated_robots=list(generations), pending_charge=bool(node.rally_charge_requested),
                pending_yield=bool(getattr(node, 'pending_exploration_return_yield', None)),
                preference=copy.deepcopy(getattr(node, 'pending_exploration_charge_geometry', None))))
        except Exception as error:
            errors.append(repr(error))
        finished.set()
    subscriptions.append(node.create_subscription(String, '/p2c_charge_handoff/run', run, 10))
    def tick(value):
        message = Clock()
        message.clock.sec = int(value)
        clock.publish(message)
    def deliver(value):
        for topic, publisher in publishers.items():
            message = topics[topic]()
            if isinstance(message, String):
                name = topic.split('/')[3]
                message.data = json.dumps({**states[name], 'stamp_sec': value})
            elif isinstance(message, TFMessage):
                name = topic.split('/')[3]
                transform = TransformStamped()
                transform.header.stamp.sec = int(value)
                transform.header.frame_id = 'map'
                transform.child_frame_id = name+'/odom'
                transform.transform.rotation.w = 1.
                message.transforms = [transform]
            else:
                message.header.stamp.sec = int(value)
                if isinstance(message, OccupancyGrid):
                    geometry = data['source_map'] if topic == '/merge_map' else data['return_maps'][topic.split('/')[3]]
                    message.header.frame_id = 'map'
                    message.info.height, message.info.width = geometry['shape']
                    message.info.resolution = geometry['resolution']
                    message.info.origin.position.x, message.info.origin.position.y = geometry['origin']
                    message.info.origin.orientation.w = 1.
                    message.data = decode(geometry).ravel().tolist()
                else:
                    name = topic.split('/')[3]
                    message.header.frame_id = name+'/odom'
                    message.pose.pose.position.x, message.pose.pose.position.y = positions[name]
                    message.pose.pose.orientation.w = 1.
            cdrs[str(value)+topic] = base64.b64encode(serialize_message(message)).decode()
            publisher.publish(message)
    def consume(value):
        deadline = time.monotonic()+12.
        while time.monotonic() < deadline:
            tick(value)
            deliver(value)
            time.sleep(.03)
            if (node.now() == value and all(node.robot_odom_received_at[n] == node.robot_tf_received_at[n]
                    == node.robot_map_received_at[n] == node.battery_state_received_at[n] == value for n in positions)
                    and node.fresh_robot_inputs()):
                return
        raise AssertionError('fresh DDS sources were not consumed')
    try:
        until(lambda: trigger.get_subscription_count() == 1
              and all(publisher.get_subscription_count() == 1 for publisher in publishers.values()))
        consume(10.)
        trigger.publish(String(data='expire'))
        assert entered.wait(12.)
        for _ in range(12):
            tick(13.)
            time.sleep(.02)
        until(lambda: node.now() == 13.)
        release.set()
        assert finished.wait(12.) and not errors, errors
        assert not requests and not node.rally_charge_requested
        assert all(stamp == 10. for stamp in callbacks[0]['pose_sources'].values())
        assert bool(callbacks[0]['preference']) == (label == 'current')
        module.HeadquartersControl.exploration_battery_factor = original_factor
        consume(13.)
        finished.clear()
        trigger.publish(String(data='fresh'))
        assert finished.wait(12.) and not errors, errors
        until(lambda: any(row.get('event') == 'coordinator_planning_lease_expired' for row in events))
        if label == 'current':
            until(lambda: any(row.get('event') == 'coordinator_charge_geometry_handoff' for row in events))
            assert set(callbacks[1]['generated_robots']) == {callbacks[0]['preference']['robot']}
            assert callbacks[1]['pending_charge'] or callbacks[1]['pending_yield']
        else:
            assert len(set(callbacks[1]['generated_robots'])) == 3
            assert all(row.get('event') != 'coordinator_charge_geometry_handoff' for row in events)
        ledger = output.with_name(output.stem+'_'+label+'.jsonl')
        assert not ledger.exists()
        ledger.write_text(''.join(json.dumps(row)+'\n' for row in events))
        checked = charge_geometry_handoff_audit(ledger, label == 'current')
        assert checked['current_handoff_count'] == int(label == 'current')
        return dict(status='PASS', label=label, callbacks=callbacks, charge_requests=requests,
            private_events=events, current_source_cdrs=cdrs, handoff_audit=checked,
            source_epoch_10_expired_without_command=True, source_epoch_13_delivered=True,
            gazebo_or_real_nav2_goals=0, native_charge_cycles_executed=0)
    finally:
        release.set()
        module.HeadquartersControl.exploration_battery_factor = original_factor
        module.robot_candidate_assignments = original_generate
        module.known_space_search_candidates = original_visual
        for executor in executors:
            executor.shutdown()
        for thread in threads:
            thread.join(timeout=5.)
            assert not thread.is_alive()
        node.destroy_node()
        probe.destroy_node()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('do not overwrite evidence')
    assert os.environ.get('ROS_DOMAIN_ID') in ('216', '217'), 'use an isolated component domain'
    fixture = Path(__file__).resolve().parent.parent/'src/multi_robot_exploration/test/fixtures/p2c_v69_charge_handoff_inputs.json.gz'
    with gzip.open(fixture, 'rt') as stream:
        saved = json.load(stream)
    event = next(row['event'] for row in saved['snapshots']
                 if row['case'] == 'dev_rooms202' and row['event']['stage'] == 'candidate_budget')
    old = subprocess.check_output(['rtk', 'proxy', 'git', 'show', REFERENCE+':'+SOURCE], text=True)
    frozen = types.ModuleType('p2c_frozen_charge_handoff')
    frozen.__file__ = current.__file__
    frozen.__package__ = 'multi_robot_exploration'
    sys.modules[frozen.__name__] = frozen
    exec(compile(old, '<939a77f frozen original>', 'exec'), frozen.__dict__)
    rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=true', '-p', 'robot_count:=3',
        '-p', 'enable_battery:=true', '-p', 'enable_rally:=true', '-p', 'auto_save_map:=false'])
    try:
        result = dict(status='PASS', scope='Actual isolated DDS with synthetic fresh poses/model timestamps and original room grid content; controlled blocked callback, no task replay, CPU deadline or physical benefit claim',
            reference_commit=REFERENCE, reference_control_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_charge_handoff.py').read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
            cases=[case(frozen, 'frozen', event, args.output), case(current, 'current', event, args.output)],
            all_owned_closed=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(dict(status='PASS', cases=[dict(label=row['label'],
            generators=row['callbacks'][1]['generated_robots'], handoffs=row['handoff_audit']['current_handoff_count'],
            requests=len(row['charge_requests'])) for row in result['cases']])))
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
