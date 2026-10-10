#!/usr/bin/env python3
"""Probe geometry preferences through actual DDS, live clock and action Futures."""
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
from check_p2c_charge_reservations_runtime import until
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_outbound_routes import outbound_route_audit

REFERENCE = '0bfaf4211b971dc64572d7790f831bc26531c7ad'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module, label, ledger):
    node = module.HeadquartersControl()
    for timer in node.timers: timer.cancel()
    probe = Node('p2c_geometry_'+label, use_global_arguments=False)
    executors = [MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    for executor, member in zip(executors, (node, probe)): executor.add_node(member)
    threads = [threading.Thread(target=executor.spin) for executor in executors]
    for thread in threads: thread.start()
    clock = probe.create_publisher(Clock, '/clock', 10)
    trigger = probe.create_publisher(String, '/p2c_geometry/run', 10)
    topics = {'/merge_map': OccupancyGrid}
    for name in ('tb1', 'tb2'):
        topics.update({f'/gateway/received/{name}/'+suffix: kind for suffix, kind in (
            ('map', OccupancyGrid), ('odom', Odometry), ('tf', TFMessage), ('battery_state', String))})
    pubs = {topic: probe.create_publisher(kind, topic, QoSProfile(depth=10,
        durability=DurabilityPolicy.TRANSIENT_LOCAL) if kind is String else 10) for topic, kind in topics.items()}
    events=[]; goals=[]; requests=[]; callbacks=[]; errors=[]; done=threading.Event()
    state = dict(stage='initial', prices=0, energy=12., capacity=100., blocked=False)
    original = module.robot_candidate_assignments
    price = node.exploration_battery_factor
    def candidates(grid, resolution, origin, name, *args, **kwargs):
        rows = []
        if name == 'tb1':
            for i in range(50):
                x, y = 6.95+i*.001, 4.55
                view = module.Viewpoint(i, 45, 69, 45, 70, 1200 if state['stage']=='fresh' else 1000, 10)
                item = module.Assignment(view, x, y, 5., 600. if state['stage']=='fresh' else 1000., x, y)
                rows.append((item.utility, name, i, item))
        return rows, dict(frontier_groups=len(rows), groups_with_viewpoints=len(rows))
    module.robot_candidate_assignments = candidates
    def tick(value):
        msg=Clock(); msg.clock.sec=value; clock.publish(msg)
    def priced(*args):
        state['prices'] += 1
        threshold = 2 if state['stage']=='initial' else 16
        if state['prices'] == threshold:
            epoch = 13 if state['stage']=='initial' else 16
            for _ in range(5): tick(epoch); time.sleep(.02)
            until(lambda: node.now()==epoch)
        return price(*args)
    node.exploration_battery_factor = priced
    def execute(handle):
        p=handle.request.pose.pose.position; goals.append((p.x,p.y))
        handle.succeed(); return NavigateToPose.Result()
    servers=[ActionServer(probe, NavigateToPose, f'/gateway/{name}/navigate_to_pose', execute) for name in ('tb1','tb2')]
    audit=probe.create_subscription(String, node.consumed_publisher.topic_name,
        lambda msg: events.append(json.loads(msg.data)), 100)
    subscriptions=[probe.create_subscription(String, pub.topic_name,
        lambda msg: requests.append(json.loads(msg.data)), 10) for pub in node.charge_request_publishers.values()]
    def run(msg):
        state['prices']=0
        try:
            module.HeadquartersControl.assign_idle_robots(node)
            callbacks.append(dict(request=msg.data, clock=node.now(), prices=state['prices'],
                proposal=json.loads(json.dumps(getattr(node,'pending_exploration_geometry',None)))))
        except Exception as error: errors.append(repr(error))
        done.set()
    consumer=node.create_subscription(String, '/p2c_geometry/run', run, 10)
    def deliver(epoch):
        for topic, pub in pubs.items():
            if label=='current_stale' and state['stage']=='fresh' and topic.endswith('/tf'): continue
            msg=topics[topic](); name='tb2' if '/tb2/' in topic else 'tb1'
            x=5. if name=='tb2' else 2.; y=3.
            if isinstance(msg, String):
                msg.data=json.dumps(dict(robot=name, stamp_sec=epoch, mode='ACTIVE',
                    energy=80. if name=='tb2' else state['energy'], capacity=100. if name=='tb2' else state['capacity'],
                    charge_target_fraction=.8, charge_x=x, charge_y=y, charge_radius_m=.8,
                    move_cost_per_m=100. if name=='tb1' and state['capacity']<1. else 1., idle_cost_per_sec=.02,
                    nominal_speed_mps=.18, return_path_factor=2., return_safety_margin=8., charge_duration_sec=6.))
            elif isinstance(msg, TFMessage):
                t=TransformStamped(); t.header.stamp.sec=epoch; t.header.frame_id='map'; t.child_frame_id=name+'/odom'
                t.transform.rotation.w=1.; msg.transforms=[t]
            else:
                msg.header.stamp.sec=epoch
                if isinstance(msg, OccupancyGrid):
                    msg.header.frame_id='map'; msg.info.width=msg.info.height=80; msg.info.resolution=.1
                    msg.info.origin.orientation.w=1.; msg.data=[100 if state['blocked'] else 0]*6400
                else:
                    msg.header.frame_id=name+'/odom'; msg.pose.pose.position.x=x; msg.pose.pose.position.y=y
                    msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def invoke(value):
        done.clear(); trigger.publish(String(data=value)); assert done.wait(20.) and not errors, errors
    try:
        until(lambda: trigger.get_subscription_count()==1 and all(pub.get_subscription_count()==1 for pub in pubs.values()))
        until(lambda: all(client.server_is_ready() for client in node.robot_nav_clients.values()))
        until(lambda: node.consumed_publisher.get_subscription_count()==1)
        for _ in range(12): tick(10); deliver(10); time.sleep(.03)
        until(lambda: node.now()==10. and node.fresh_robot_inputs() and node.active_batteries_ready())
        invoke('initial')
        assert node.now()==13. and not goals and not requests
        proposal=getattr(node, 'pending_exploration_geometry', None)
        if label=='frozen': assert proposal is None
        else:
            assert proposal and proposal['cursor']=={} and proposal['points']['tb1']
            assert set(proposal)=={'context','generated_at','points','cursor'}
        state['stage']='fresh'
        if label=='current_funded': state['energy']=80.
        if label=='current_unfundable': state.update(energy=.1, capacity=.2)
        if label=='current_changed_map': state['blocked']=True
        for _ in range(12): deliver(13); time.sleep(.03)
        if label=='current_stale': until(lambda: node.robot_odom_received_at['tb1']==13. and node.robot_tf_received_at['tb1']==10.)
        else: until(lambda: node.fresh_robot_inputs() and node.robot_map_received_at['tb1']==13.)
        invoke('fresh')
        if label=='frozen':
            assert node.now()==16. and not requests and not goals
        elif label=='current':
            until(lambda: len(requests)==1 and any(e.get('event')=='coordinator_charge_decision' for e in events))
            assert not goals and requests[0]['robot']=='tb1' and 12.<requests[0]['required_energy']<80.
            decision=next(e for e in events if e.get('event')=='coordinator_charge_decision')
            assert decision['event_time']==13. and all(0<=v['age_sec']<=v['ttl_sec'] for v in decision['inputs'].values())
        elif label=='current_funded':
            until(lambda: len(goals)==1 and node.goal_handles['tb1'] is None and node.robot_states['tb1']=='idle')
            assert not requests
            decision=next(e for e in events if e.get('event')=='coordinator_navigation_decision')
            choice=decision['travel_preference']
            assert choice['information_gain']==1200 and choice['base_utility']==600.
            assert choice['deferred_geometry_preference']['prices_reused'] is False
            assert choice['required_energy_evaluated_at_sec']==13. and 80.>choice['required_energy']
        else: assert not goals and not requests
        ledger.write_text(''.join(json.dumps(e)+'\n' for e in events))
        if goals:
            navigation_dispatch_audit(ledger, True)
            outbound_route_audit(ledger, True)
        return dict(status='PASS', label=label, callbacks=callbacks, goals=goals,
            charge_requests=requests, events=events, action_futures_closed=True)
    finally:
        module.robot_candidate_assignments=original
        node.exploration_battery_factor=price
        for server in servers: server.destroy()
        for executor in executors: executor.shutdown()
        for thread in threads: thread.join(timeout=5.); assert not thread.is_alive()
        node.destroy_node(); probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE], text=True)
    frozen=types.ModuleType('p2c_geometry_reference'); frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration'; sys.modules[frozen.__name__]=frozen
    exec(compile(source, '<frozen 0bfaf42 geometry>', 'exec'), frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2',
        '-p','enable_battery:=true','-p','enable_rally:=false','-p','auto_save_map:=false'])
    try:
        labels=('current','current_funded','current_stale','current_changed_map','current_unfundable')
        cases=[case(frozen,'frozen',args.output.with_suffix('.frozen.jsonl'))]
        cases.extend(case(current,label,args.output.with_suffix('.'+label+'.jsonl')) for label in labels)
        payload=dict(status='PASS',scope='Synthetic candidate generator and free/blocked input maps. Identical price-count clock progression, actual DDS source delivery, charging and ActionServer/Futures; independent dispatch/outbound readers. No actual Nav2 motion, native task success, real timing or global ranking claim.',
            reference_commit=REFERENCE, reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), cases=cases, all_owned_closed=True)
        args.output.write_text(json.dumps(payload, indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=c['label'],goals=len(c['goals']),charges=len(c['charge_requests'])) for c in cases],all_owned_closed=True)))
    finally: rclpy.shutdown()


if __name__=='__main__': main()
