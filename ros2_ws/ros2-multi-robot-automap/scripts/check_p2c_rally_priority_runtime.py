#!/usr/bin/env python3
"""Exercise quiescent rally priority repair with actual DDS and action Futures."""
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

import numpy as np
import rclpy
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.action import ActionServer, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from check_p2c_dispatch_boundary_runtime import until
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_outbound_routes import outbound_route_audit

REFERENCE = '978c8dda8102a155dd7c282988ad18787c0ab36b'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module, label):
    names = ['tb1','tb2','tb3']
    positions = {'tb1':(1.05,3.05),'tb2':(5.05,3.05),'tb3':(10.05,6.05)}
    targets = {'tb1':module.RallyPose(9.05,3.05,0.),
               'tb2':module.RallyPose(7.05,3.85,0.),'tb3':module.RallyPose(10.05,6.05,0.)}
    grid = np.full((100,120),100,dtype=np.int16)
    grid[26:35,5:115] = 0
    grid[26:90,65:115] = 0
    node = module.HeadquartersControl()
    for timer in node.timers:timer.cancel()
    probe = Node('p2c_priority_'+label,use_global_arguments=False)
    executors = [MultiThreadedExecutor(num_threads=2),MultiThreadedExecutor(num_threads=2)]
    for executor,member in zip(executors,(node,probe)):executor.add_node(member)
    threads = [threading.Thread(target=e.spin) for e in executors]
    for thread in threads:thread.start()
    topics = {'/merge_map':OccupancyGrid}
    for name in names:
        topics.update({f'/gateway/received/{name}/'+suffix:kind for suffix,kind in (
            ('map',OccupancyGrid),('odom',Odometry),('tf',TFMessage),('battery_state',String))})
    pubs = {topic:probe.create_publisher(kind,topic,
        QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL) if kind is String else 10)
        for topic,kind in topics.items()}
    clock = probe.create_publisher(Clock,'/clock',10)
    trigger = probe.create_publisher(String,'/p2c_priority/run',10)
    events,goals,callbacks,errors = [],[],[],[]
    finished = threading.Event()
    accept = threading.Event()
    finish_action = threading.Event()
    pending_case = label == 'current_pending'
    live_case = label in ('current_pending','current_accepted')
    if not pending_case:accept.set()
    if not live_case:finish_action.set()
    def goal(name,request):
        assert accept.wait(10.), 'pending acceptance did not release'
        pose = request.pose.pose
        goals.append(dict(robot=name,position=[pose.position.x,pose.position.y],
            yaw=2*math.atan2(pose.orientation.z,pose.orientation.w)))
        return GoalResponse.ACCEPT
    def execute(handle):
        assert finish_action.wait(10.), 'accepted result did not release'
        handle.succeed()
        return NavigateToPose.Result()
    servers = [ActionServer(probe,NavigateToPose,f'/gateway/{name}/navigate_to_pose',
        execute_callback=execute,goal_callback=lambda request,name=name:goal(name,request)) for name in names]
    audit = probe.create_subscription(String,'/gateway/consumed',lambda msg:events.append(json.loads(msg.data)),100)
    def run(msg):
        try:
            if msg.data == 'update':node.update_mission()
            else:
                name = 'tb1' if msg.data == 'live' else 'tb2'
                pose = module.RallyPose(2.05,3.05,0.) if name == 'tb1' else targets[name]
                plan = module.plan_rally_leg(pose,node.map_data,node.resolution,node.origin,
                    node.robot_positions[name],blocked_positions=[p for other,p in node.robot_positions.items() if other != name],
                    local_map=node.robot_maps[name])
                node.send_rally_goal(name,plan)
            callbacks.append(dict(request=msg.data,clock=node.now(),order=list(node.rally_dispatch_order),
                pending=dict(node.rally_goal_pending),accepted={n:h is not None for n,h in node.rally_goal_handles.items()},
                preflight=node.rally_preflight_complete,budgets=dict(node.rally_charge_budgets),
                observer_guard=node.rally_observer_guard))
        except Exception as error:errors.append(repr(error))
        finally:finished.set()
    subscription = node.create_subscription(String,'/p2c_priority/run',run,10)
    energy = {name:80. for name in names}
    energy['tb3'] = 8.5
    def tick(value):
        msg = Clock();msg.clock.sec=int(value);clock.publish(msg)
    def deliver(value):
        for topic,pub in pubs.items():
            msg = topics[topic]();name=next((n for n in names if '/'+n+'/' in topic),'tb1')
            if isinstance(msg,String):
                msg.data=json.dumps(dict(robot=name,mode='ACTIVE',energy=energy[name],capacity=100.,
                    charge_x=positions[name][0],charge_y=positions[name][1],charge_radius_m=.8,
                    charge_target_fraction=.8,stamp_sec=value,_gateway=dict(source_time=value,delivery_time=value),
                    nominal_speed_mps=.18,idle_cost_per_sec=.02,move_cost_per_m=1.,return_path_factor=2.,
                    return_safety_margin=8.,charge_duration_sec=6.,return_recovery_wait_sec=30.))
            elif isinstance(msg,TFMessage):
                transform=TransformStamped();transform.header.stamp.sec=value;transform.header.frame_id='map'
                transform.child_frame_id=name+'/odom';transform.transform.rotation.w=1.;msg.transforms=[transform]
            else:
                msg.header.stamp.sec=value
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=120;msg.info.height=100;msg.info.resolution=.1
                    msg.info.origin.orientation.w=1.;msg.data=grid.ravel().tolist()
                else:
                    msg.header.frame_id=name+'/odom';msg.pose.pose.position.x,msg.pose.pose.position.y=positions[name]
                    msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def invoke(request='update'):
        finished.clear();trigger.publish(String(data=request))
        assert finished.wait(10.) and not errors,errors
    def advance(value,refresh=False):
        for _ in range(8):
            tick(value)
            if refresh:deliver(value)
            time.sleep(.025)
        until(lambda:node.now()==value)
        if refresh:until(node.fresh_robot_inputs)
    def closed():
        return not any(node.rally_goal_pending.values()) and not any(node.rally_goal_handles.values())
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values())
            and all(c.server_is_ready() for c in node.robot_nav_clients.values())
            and node.consumed_publisher.get_subscription_count()==1)
        advance(10,True)
        node.task_state='RALLY';node.target=(10.05,8.05);node.target_received_source_time=10.
        node.detecting_robot=node.target_observing_robot='tb3'
        node.rally_targets=targets.copy();node.rally_final_targets=targets.copy();node.rally_dispatch_order=names.copy()
        node.rally_preflight_complete=True
        if live_case:
            blocked=node.prepare_rally_charges()
            assert blocked=={'tb3'},blocked
            invoke('live')
            if pending_case:until(lambda:node.rally_goal_pending['tb1'])
            else:until(lambda:node.rally_goal_handles['tb1'] is not None)
        invoke()
        assert not callbacks[-1]['preflight']
        assert callbacks[-1]['observer_guard']=='tb3'
        if live_case:
            assert node.rally_dispatch_order==names
            accept.set();finish_action.set();until(closed)
            advance(11,True);invoke()
            assert node.rally_dispatch_order==['tb3','tb2','tb1']
            assert [g['robot'] for g in goals]==['tb1']
            advance(12,True);invoke();until(lambda:len(goals)==2);until(closed)
            assert goals[-1]['robot']=='tb2'
        elif label=='frozen':
            assert node.rally_dispatch_order==names and not goals
            advance(11,True);invoke()
            assert node.rally_dispatch_order==names and not goals
        else:
            assert node.rally_dispatch_order==['tb3','tb2','tb1'] and not goals
            advance(11,True);invoke();until(lambda:len(goals)==1);until(closed)
            assert goals[0]['robot']=='tb2'
        expected=len(goals)
        if label!='frozen':
            # These call the original dispatch guards, including its complete
            # actual detour/final-return budget; no readiness/energy stubs.
            advance(15);invoke('direct');assert len(goals)==expected
            advance(15,True);invoke('direct');until(lambda:len(goals)==expected+1);until(closed)
            energy['tb2']=.1;advance(16,True);invoke('direct');assert len(goals)==expected+1
        until(lambda:sum(e.get('event')=='coordinator_navigation_decision' for e in events)==len(goals))
        with tempfile.TemporaryDirectory() as directory:
            ledger=Path(directory)/'ledger.jsonl';ledger.write_text(''.join(json.dumps(e)+'\n' for e in events))
            audits=dict(dispatch=navigation_dispatch_audit(ledger,True),outbound=outbound_route_audit(ledger,True))
        assert all(g['robot']!='tb3' for g in goals)
        return dict(status='PASS',label=label,callbacks=callbacks,goals=goals,private_events=events,
            independent_audits=audits,old_live_order_preserved=live_case,
            expired_sources_rejected=label!='frozen',insufficient_energy_rejected=label!='frozen',
            action_futures_closed=closed())
    finally:
        accept.set();finish_action.set()
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        for server in servers:server.destroy()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    old=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_priority_reference');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(old,'<frozen v59 priority>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=3',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        rows=[case(frozen,'frozen'),case(current,'current'),
              case(current,'current_pending'),case(current,'current_accepted')]
        result=dict(status='PASS',scope='Synthetic target/assignment and geometry/models delivered on actual isolated DDS; actual original full budget/TTL/order/body/reservation checks and ActionServer/Futures. No physical Nav2, task benefit or general liveness guarantee.',
            reference_commit=REFERENCE,reference_source=old,reference_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),cases=rows,all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=r['label'],goals=len(r['goals'])) for r in rows],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
