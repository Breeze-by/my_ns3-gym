#!/usr/bin/env python3
"""Check actual proposal DDS witnesses against local-obstacle CDR geometry."""
import argparse
import base64
import gzip
import hashlib
import json
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
from nav_msgs.msg import OccupancyGrid,Odometry
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.serialization import serialize_message
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as current
from check_p2c_gate import rally_proposal_audit
from check_p2c_dispatch_boundary_runtime import until

REFERENCE='41f6d86b2ac05712e3bc392e39dd5a1e0f58d4c5'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def case(module,label):
    node=module.HeadquartersControl();probe=Node('p2c_proposal_maps_'+label,use_global_arguments=False)
    for timer in node.timers:timer.cancel()
    ex=MultiThreadedExecutor(num_threads=2);ex.add_node(node);ex.add_node(probe)
    thread=threading.Thread(target=ex.spin);thread.start()
    positions={'tb1':(3.55,1.55),'tb2':(1.55,1.55),'tb3':(2.55,1.55)}
    poses={n:module.RallyPose(x,1.55,0.) for n,x in [('tb1',5.55),('tb2',6.55),('tb3',7.55)]}
    grid=np.full((40,100),100,dtype=np.int16);grid[10:21,10:90]=0
    local=grid.copy();local[:,45]=100
    topics={'/merge_map':OccupancyGrid}
    for n in positions:topics.update({f'/gateway/received/{n}/'+k:t for k,t in
        [('map',OccupancyGrid),('odom',Odometry),('tf',TFMessage)]})
    pubs={topic:probe.create_publisher(kind,topic,10) for topic,kind in topics.items()}
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_proposal_maps/run',10)
    finished=threading.Event();events=[];errors=[];admitted=[];raw=[]
    sub=probe.create_subscription(String,'/gateway/consumed',lambda msg:events.append(json.loads(msg.data)),100)
    original=dict(event='coordinator_rally_assignment_chosen',event_time=9.,computation_completed_at_sec=9.,
        assignment={n:[p.x,p.y,p.yaw] for n,p in poses.items()},target=[8.45,1.55],
        robot_positions=positions,battery_states=None)
    def run(msg):
        try:
            node.pending_rally_proposal=dict(assignment=poses,target=tuple(original['target']),
                evaluated_at=9.,participants=tuple(positions))
            admitted.append(module.HeadquartersControl.admit_rally_proposal(node,node.pending_rally_proposal))
        except Exception as error:errors.append(repr(error))
        finally:finished.set()
    subscription=node.create_subscription(String,'/p2c_proposal_maps/run',run,10)
    def tick(value):msg=Clock();msg.clock.sec=value;clock.publish(msg)
    def deliver(value):
        for topic,pub in pubs.items():
            msg=topics[topic]();n=next((n for n in positions if '/'+n+'/' in topic),'tb1')
            if isinstance(msg,TFMessage):
                tf=TransformStamped();tf.header.stamp.sec=value;tf.header.frame_id='map'
                tf.child_frame_id=n+'/odom';tf.transform.rotation.w=1.;msg.transforms=[tf]
            else:
                msg.header.stamp.sec=value
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.height,msg.info.width=grid.shape;msg.info.resolution=.1
                    msg.info.origin.orientation.w=1.;msg.data=(local if n=='tb3' else grid).ravel().tolist()
                    raw.append(dict(topic='/merge_map' if topic=='/merge_map' else '/'+n+'/map',
                        cdr=base64.b64encode(serialize_message(msg)).decode()))
                else:
                    msg.header.frame_id=n+'/odom';msg.pose.pose.position.x,msg.pose.pose.position.y=positions[n]
                    msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def invoke():finished.clear();trigger.publish(String(data='run'));assert finished.wait(10.) and not errors,errors
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(pub.get_subscription_count()==1 for pub in pubs.values())
            and node.consumed_publisher.get_subscription_count()==1)
        for _ in range(10):tick(10);deliver(10);time.sleep(.03)
        until(node.fresh_robot_inputs)
        node.target=tuple(original['target']);node.target_received_source_time=10.
        node.task_state='FOUND';node.detecting_robot='tb1'
        invoke();assert admitted==[True],(admitted,errors)
        until(lambda:any(e.get('event')=='coordinator_rally_proposal_admitted' for e in events))
        witness=next(e for e in events if e.get('event')=='coordinator_rally_proposal_admitted')
        assert witness['dispatch_order']==['tb1','tb2','tb3']
        assert module.map_safe_rally_dispatch_order(node.map_data,node.resolution,node.origin,poses,
            positions,node.target,'tb1')==['tb3','tb2','tb1']
        with tempfile.TemporaryDirectory() as directory:
            capture=Path(directory)/'capture.jsonl.gz'
            with gzip.open(capture,'wt') as stream:
                for row in raw:stream.write(json.dumps(row)+'\n')
            if label=='current':
                audit=rally_proposal_audit([original,witness],True,True,capture)
                assert audit['original_source_maps']==4
            else:
                try:rally_proposal_audit([original,witness],True,True,capture)
                except AssertionError:audit=dict(status='EXPECTED_REJECTION',reason='Original witness omits consulted maps')
                else:raise AssertionError('Original missing maps were accepted')
        for _ in range(8):tick(13);time.sleep(.03)
        until(lambda:node.now()==13);invoke();assert admitted==[True,False]
        assert all(handle is None for handle in node.rally_goal_handles.values())
        return dict(status='PASS',label=label,original=original,witness=witness,raw_cdr=raw,
            independent_audit=audit,stale_sources_rejected=True,navigation_goals=0)
    finally:
        ex.shutdown();thread.join(5.);assert not thread.is_alive()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_proposal_maps_reference');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(source,'<frozen v60>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=3',
        '-p','enable_battery:=false','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        result=dict(status='PASS',scope='Synthetic local-obstacle geometry, actual DDS/state callback/private witness and serialized original source binding; no physical Nav2 or task causal claim',
            reference_commit=REFERENCE,reference_source=source,
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen'),case(current,'current')],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=len(result['cases']),all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
