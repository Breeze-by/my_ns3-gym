#!/usr/bin/env python3
"""Real DDS/Future check for a charged leader's conditional refuge release."""
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
from p2c_refuge_release import audit_eligibility

REFERENCE = 'e8af7f00bd2ce199636b3c3f317e2de4f89e38fb'
SOURCE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def until(predicate, timeout=10.):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:time.sleep(.02)
    assert predicate(), 'bounded DDS probe wait expired'


def case(module, label):
    node=module.HeadquartersControl()
    for timer in node.timers:timer.cancel()
    probe=Node('p2c_refuge_release_probe_'+label,use_global_arguments=False)
    executors=[MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    for executor,member in zip(executors,(node,probe)):executor.add_node(member)
    threads=[threading.Thread(target=executor.spin) for executor in executors]
    for thread in threads:thread.start()
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_refuge_release_probe/run',10)
    topics={'/merge_map':OccupancyGrid}
    for name in ('tb1','tb2'):
        topics.update({f'/gateway/received/{name}/'+suffix:kind for suffix,kind in (
            ('map',OccupancyGrid),('odom',Odometry),('tf',TFMessage),('battery_state',String))})
    pubs={topic:probe.create_publisher(kind,topic,QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if kind is String else 10) for topic,kind in topics.items()}
    events=[];goals=[];callbacks=[];errors=[];done=threading.Event()
    def execute(handle):
        p=handle.request.pose.pose.position;goals.append((p.x,p.y))
        handle.succeed();return NavigateToPose.Result()
    servers=[ActionServer(probe,NavigateToPose,f'/gateway/{name}/navigate_to_pose',execute) for name in ('tb1','tb2')]
    subscription=probe.create_subscription(String,node.consumed_publisher.topic_name,
        lambda msg:events.append(json.loads(msg.data)),10)
    def run(msg):
        try:
            # Only the target and existing completed-refuge state are synthetic.
            # The current maps, TF, odometry and energy enter on actual DDS.
            node.task_state='RALLY';node.target=(6.05,3.05);node.target_received_source_time=10.
            node.detecting_robot='tb1';node.target_observing_robot='tb1'
            node.rally_final_targets={'tb1':module.RallyPose(5.05,2.05,0.),'tb2':module.RallyPose(5.05,5.05,0.)}
            node.rally_targets={'tb1':module.RallyPose(*node.robot_positions['tb1'],0.),'tb2':node.rally_final_targets['tb2']}
            node.rally_dispatch_order=['tb2','tb1'];node.rally_arrived={'tb1':True,'tb2':False}
            node.return_yield_targets={'tb1':'tb2'};node.rally_yield_targets={'tb1'}
            node.rally_wait_budgets={'tb1':20.,'tb2':20.}
            module.HeadquartersControl.release_return_yields(node)
            restored='tb1' not in node.return_yield_targets
            if restored:
                module.HeadquartersControl.prepare_rally_charges(node)
                plan=module.plan_rally_leg(node.rally_targets['tb1'],node.map_data,node.resolution,node.origin,
                    node.robot_positions['tb1'],blocked_positions=[node.robot_positions['tb2']],
                    visible_only=True,local_map=node.robot_maps['tb1'])
                module.HeadquartersControl.send_rally_goal(node,'tb1',plan)
            callbacks.append(dict(request=msg.data,clock=node.now(),restored=restored,
                order=node.rally_dispatch_order,source=node.robot_map_received_at['tb1']))
        except Exception as error:errors.append(repr(error))
        done.set()
    control_subscription=node.create_subscription(String,'/p2c_refuge_release_probe/run',run,10)
    def tick(stamp):
        msg=Clock();msg.clock.sec=stamp;clock.publish(msg)
    def deliver(stamp):
        for topic,pub in pubs.items():
            msg=topics[topic]();name='tb2' if '/tb2/' in topic else 'tb1';y=5.05 if name=='tb2' else 2.05
            if isinstance(msg,String):
                msg.data=json.dumps(dict(stamp_sec=stamp,mode='ACTIVE',energy=80.,capacity=100.,charge_target_fraction=.8,
                    charge_x=1.05,charge_y=y,charge_radius_m=.8,move_cost_per_m=1.,idle_cost_per_sec=.02,
                    nominal_speed_mps=.18,return_path_factor=2.,return_safety_margin=8.,charge_duration_sec=6.))
            elif isinstance(msg,TFMessage):
                t=TransformStamped();t.header.stamp.sec=stamp;t.header.frame_id='map';t.child_frame_id=name+'/odom'
                t.transform.rotation.w=1.;msg.transforms=[t]
            else:
                msg.header.stamp.sec=stamp
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.width=80;msg.info.height=80;msg.info.resolution=.1
                    msg.info.origin.orientation.w=1.;msg.data=[0]*6400
                else:
                    msg.header.frame_id=name+'/odom';msg.pose.pose.position.x=1.05
                    msg.pose.pose.position.y=y;msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(pub.get_subscription_count()==1 for pub in pubs.values()))
        until(lambda:clock.get_subscription_count()==1)
        for _ in range(12):tick(10);deliver(10);time.sleep(.03)
        until(lambda:node.now()==10. and node.fresh_robot_inputs() and all(mode=='ACTIVE' for mode in node.battery_modes.values()))
        until(lambda:all(client.server_is_ready() for client in node.robot_nav_clients.values()))
        trigger.publish(String(data='charged_owner_parked'));assert done.wait(10.) and not errors,errors
        until(lambda:not any(node.rally_goal_pending.values()) and not any(node.rally_goal_handles.values()))
        assert callbacks[0]['restored'] is (label=='current')
        if label=='current':
            until(lambda:len(goals)==1 and any(e.get('event')=='coordinator_return_refuge_release_eligibility' for e in events))
            checked=[e for e in events if e.get('event')=='coordinator_return_refuge_release_eligibility']
            assert len(checked)==1 and len(audit_eligibility(checked[0]))==2
            until(lambda:any(e.get('event')=='coordinator_navigation_decision' for e in events))
            decisions=[e for e in events if e.get('event')=='coordinator_navigation_decision']
            assert len(decisions)==1 and audit_outbound(decisions[0])>1
            for _ in range(8):tick(13);time.sleep(.02)
            until(lambda:node.now()==13.)
            done.clear();trigger.publish(String(data='original_sources_expired'));assert done.wait(10.) and not errors,errors
            assert not callbacks[-1]['restored'] and len(goals)==1
        else:assert not goals
        return dict(status='PASS',label=label,callbacks=callbacks,goals=goals,events=events,action_futures_closed=True)
    finally:
        for server in servers:server.destroy()
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(timeout=5.);assert not thread.is_alive()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_refuge_release_reference');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(source,'<frozen e8af original release>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        result=dict(status='PASS',scope='Synthetic completed-refuge state and target; actual DDS and ActionServer/Futures. No physical Nav2 motion, native task success or causal timing claim',
            reference_commit=REFERENCE,reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            reader_sha256=hashlib.sha256(Path(__file__).with_name('p2c_refuge_release.py').read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen'),case(current,'current')],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=[dict(label=r['label'],goals=len(r['goals'])) for r in result['cases']],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
