#!/usr/bin/env python3
"""Observe frozen/current navigation dispatch across actual DDS clock delays."""
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
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.action import ActionServer, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from p2c_navigation_dispatch import navigation_dispatch_audit

REFERENCE = '1a6bed893baa10c501953334046ffa7bd75302e4'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def until(predicate, seconds=5.):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    assert predicate(), 'DDS probe condition did not arrive'


def case(module, label, stage):
    node = module.HeadquartersControl()
    probe = Node('p2c_dispatch_boundary_' + label + '_' + stage, use_global_arguments=False)
    for timer in node.timers:
        timer.cancel()
    executor = MultiThreadedExecutor(num_threads=2)
    sidecar = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node); sidecar.add_node(probe)
    threads = [threading.Thread(target=e.spin) for e in (executor, sidecar)]
    for thread in threads:
        thread.start()
    clock = probe.create_publisher(Clock, '/clock', 10)
    trigger = probe.create_publisher(String, '/p2c_dispatch_boundary/run', 10)
    topics = {'/merge_map': OccupancyGrid, '/gateway/received/tb1/map': OccupancyGrid,
              '/gateway/received/tb1/odom': Odometry, '/gateway/received/tb1/tf': TFMessage}
    pubs = {topic: probe.create_publisher(kind, topic, 10) for topic, kind in topics.items()}
    entered = threading.Event(); release = threading.Event(); finished = threading.Event()
    errors = []; callbacks = []; goals = []; events = []
    delaying = [True]
    result_consumed = threading.Event()
    original_result = node.rally_goal_result

    def consume_result(*args):
        original_result(*args)
        result_consumed.set()

    node.rally_goal_result = consume_result

    def goal(request):
        stamp = request.pose.header.stamp
        goals.append(dict(header_time=stamp.sec + stamp.nanosec * 1e-9,
                          coordinator_clock=node.now(), position=[request.pose.pose.position.x,
                                                                  request.pose.pose.position.y]))
        return GoalResponse.ACCEPT

    def execute(handle):
        handle.succeed()
        return NavigateToPose.Result()

    server = ActionServer(probe, NavigateToPose, '/gateway/tb1/navigate_to_pose',
                          execute_callback=execute, goal_callback=goal)
    audit = probe.create_subscription(String, '/gateway/consumed',
        lambda msg: events.append(json.loads(msg.data)), 100)
    logger = node.get_logger()

    def pause():
        entered.set()
        assert release.wait(10.), 'controlled dispatch delay was not released'

    class Logger:
        def info(self, message):
            if delaying[0] and stage == 'logger' and message.startswith(('Sending tb1 rally leg', 'Preparing tb1 rally leg')):
                pause()
            logger.info(message)

        def __getattr__(self, name):
            return getattr(logger, name)

    publisher = node.consumed_publisher

    class Publisher:
        def publish(self, message):
            publisher.publish(message)
            if delaying[0] and stage == 'publication' and json.loads(message.data)['event'] == 'coordinator_navigation_decision':
                pause()

    node.get_logger = lambda: Logger()
    node.consumed_publisher = Publisher()

    def run(message):
        try:
            node.send_rally_goal('tb1', plan=(module.RallyPose(3.05, 2.05, 0.),
                                           ((1.05, 2.05), (3.05, 2.05))))
            callbacks.append(dict(clock=node.now(), source=node.robot_odom_received_at['tb1'],
                                  pending=node.rally_goal_pending['tb1'],
                                  route=list(node.rally_leg_routes['tb1'])))
        except Exception as error:
            errors.append(repr(error))
        finally:
            finished.set()

    subscription = node.create_subscription(String, '/p2c_dispatch_boundary/run', run, 10)

    def stamp(value, dest):
        dest.sec = int(value); dest.nanosec = round((value - int(value)) * 1e9)

    def tick(value):
        msg = Clock(); stamp(value, msg.clock); clock.publish(msg)

    def deliver(value):
        for topic, pub in pubs.items():
            msg = topics[topic]()
            if isinstance(msg, TFMessage):
                t = TransformStamped(); stamp(value, t.header.stamp)
                t.header.frame_id = 'map'; t.child_frame_id = 'tb1/odom'
                t.transform.rotation.w = 1.; msg.transforms = [t]
            else:
                stamp(value, msg.header.stamp)
                if isinstance(msg, OccupancyGrid):
                    msg.header.frame_id = 'map'; msg.info.width = msg.info.height = 50
                    msg.info.resolution = .1; msg.info.origin.orientation.w = 1.; msg.data = [0] * 2500
                else:
                    msg.header.frame_id = 'tb1/odom'; msg.pose.pose.position.x = 1.05
                    msg.pose.pose.position.y = 2.05; msg.pose.pose.orientation.w = 1.
            pub.publish(msg)

    try:
        until(lambda: trigger.get_subscription_count() == 1 and
              all(p.get_subscription_count() == 1 for p in pubs.values()) and
              clock.get_subscription_count() == 1 and publisher.get_subscription_count() == 1 and
              node.robot_nav_clients['tb1'].server_is_ready(), 10.)
        for _ in range(10):
            tick(10.); time.sleep(.02)
        until(lambda: node.now() == 10.)
        for _ in range(10):
            deliver(10.); time.sleep(.02)
        until(node.fresh_robot_inputs)
        node.task_state = 'RALLY'; node.target = (3.05, 2.05)
        node.target_received_source_time = 10.; node.rally_targets = {'tb1': module.RallyPose(3.05, 2.05, 0.)}
        trigger.publish(String(data='expired'))
        assert entered.wait(5.)
        for _ in range(10):
            tick(12.1); time.sleep(.02)
        until(lambda: node.now() == 12.1)
        assert node.robot_odom_received_at['tb1'] == node.robot_tf_received_at['tb1'] == 10.
        release.set(); assert finished.wait(5.) and not errors, errors
        delaying[0] = False
        if label == 'frozen':
            until(lambda: len(goals) == 1)
            until(lambda: any(e['event'] == 'coordinator_navigation_decision' for e in events))
            assert callbacks[0]['pending'] and callbacks[0]['route']
            if stage == 'logger':
                event = next(e for e in events if e['event'] == 'coordinator_navigation_decision')
                assert event['inputs']['tb1/pose_state']['age_sec'] > 2.
            else:
                assert goals[0]['header_time'] == 10. and goals[0]['coordinator_clock'] == 12.1
        else:
            if stage == 'publication':
                until(lambda: any(e['event'] == 'coordinator_navigation_dispatch_revoked' for e in events))
            assert not goals and not callbacks[0]['pending'] and not callbacks[0]['route']
            assert node.rally_attempts['tb1'] == 0
            for _ in range(10):
                deliver(12.1); time.sleep(.02)
            until(lambda: node.robot_odom_received_at['tb1'] == node.robot_tf_received_at['tb1'] == 12.1
                  and node.fresh_robot_inputs())
            finished.clear(); trigger.publish(String(data='fresh'))
            assert finished.wait(5.) and not errors, errors
            until(lambda: len(goals) == 1)
            until(lambda: any(e['event'] == 'coordinator_navigation_decision' and e['event_time'] == 12.1 for e in events))
            assert goals[0]['header_time'] == 12.1
        assert result_consumed.wait(5.), 'real action result was not drained before teardown'
        return dict(status='PASS', label=label, delay_stage=stage, callbacks=callbacks,
                    action_server_goals=goals, private_events=events,
                    expired_callback_goals=1 if label == 'frozen' else 0,
                    original_source_held_at_10_during_delay=True,
                    current_resumes_only_after_new_delivery=label == 'current')
    finally:
        release.set()
        for e in (executor, sidecar):
            e.shutdown()
        for thread in threads:
            thread.join(timeout=5.); assert not thread.is_alive()
        server.destroy(); node.destroy_node(); probe.destroy_node()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('do not overwrite runtime evidence')
    old = subprocess.check_output(['git', 'show', REFERENCE + ':' + SOURCE], text=True)
    frozen = types.ModuleType('p2c_frozen_dispatch_boundary'); frozen.__file__ = current.__file__
    frozen.__package__ = 'multi_robot_exploration'; sys.modules[frozen.__name__] = frozen
    exec(compile(old, '<frozen P2C control>', 'exec'), frozen.__dict__)
    rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=true', '-p', 'robot_count:=1',
                    '-p', 'enable_battery:=false', '-p', 'enable_rally:=true', '-p', 'auto_save_map:=false'])
    try:
        rows = [case(module, label, stage) for stage in ('logger', 'publication')
                for module, label in ((frozen, 'frozen'), (current, 'current'))]
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / 'ledger.jsonl'
            for row in rows:
                if row['label'] == 'current':
                    ledger.write_text(''.join(json.dumps(e) + '\n' for e in row['private_events']))
                    row['independent_lease_audit'] = navigation_dispatch_audit(ledger, required=True)
        result = dict(status='PASS', scope='Isolated actual DDS clock, serial received-state callbacks and real ActionServer/Future with a controlled delay and synthetic free map. No Gazebo/Nav2 mission, hardware deadline or Wi-Fi claim.',
                      reference_commit=REFERENCE, reference_sha256=hashlib.sha256(old.encode()).hexdigest(),
                      control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
                      reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_navigation_dispatch.py').read_bytes()).hexdigest(),
                      cases=rows)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
