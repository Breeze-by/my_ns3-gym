#!/usr/bin/env python3
"""Original return-map prefixes via actual native DDS and ActionClient Futures."""
import argparse,base64,gzip,hashlib,json,math,subprocess,sys,tempfile,threading,time,types
from pathlib import Path

import rclpy
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid,Odometry
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy,QoSProfile
from rclpy.serialization import serialize_message
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import battery_manager as current
from check_p2c_dispatch_boundary_runtime import until
from check_p2c_gate import native_return_leg_audit
from p2c_outbound_routes import bind_original_maps,decode

REFERENCE='df0f3fc3911dfc513369c7650de1237d817effa1'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/battery_manager.py'
FIXTURE=Path(__file__).resolve().parents[1]/'src/multi_robot_exploration/test/fixtures/p2c_v62_native_prefix_input.json.gz'


def case(module,label,event):
    node=module.BatteryManager();probe=Node('p2c_native_curves_'+label,use_global_arguments=False)
    for timer in node.timers:timer.cancel()
    executors=[MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    for executor,member in zip(executors,(node,probe)):executor.add_node(member)
    threads=[threading.Thread(target=e.spin) for e in executors]
    for thread in threads:thread.start()
    clock=probe.create_publisher(Clock,'/clock',10)
    trigger=probe.create_publisher(String,'/p2c_native_curves/run',10)
    topics={'/tb1/map':OccupancyGrid,'/tb1/gateway/merge_map':OccupancyGrid,
        '/tb1/odom':Odometry,'/tb1/tf':TFMessage}
    pubs={topic:probe.create_publisher(kind,topic,QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if topic=='/tb1/map' else 10) for topic,kind in topics.items()}
    events=[];goals=[];callbacks=[];errors=[];raw=[];done=threading.Event()
    saved=event['map_evidence'];grid=decode(saved)
    def execute(handle):
        p=handle.request.pose.pose.position;goals.append((p.x,p.y))
        handle.succeed();return NavigateToPose.Result()
    server=ActionServer(probe,NavigateToPose,'/tb1/navigate_to_pose',execute)
    subscription=probe.create_subscription(String,'/tb1/battery_return_audit',
        lambda msg:events.append(json.loads(msg.data)),100)
    def run(msg):
        try:
            if msg.data=='begin':
                budget=node.current_return_budget();assert budget is not None
                node.begin_return(budget['required_energy'],reason='conditional_original_map_probe')
            else:
                if msg.data=='low_energy':node.energy=.1
                node.timer_callback()
            callbacks.append(dict(request=msg.data,clock=node.now(),mode=node.mode,energy=node.energy,
                pose_source_age=node.pose_source_age(),goal_pending=node.return_goal_pending))
        except Exception as error:errors.append(repr(error))
        finally:done.set()
    control_subscription=node.create_subscription(String,'/p2c_native_curves/run',run,10)
    def tick(value):msg=Clock();msg.clock.sec=value;clock.publish(msg)
    def deliver(value):
        for topic,pub in pubs.items():
            msg=topics[topic]()
            if isinstance(msg,TFMessage):
                t=TransformStamped();t.header.stamp.sec=value;t.header.frame_id='map';t.child_frame_id='tb1/odom'
                t.transform.rotation.w=1.;msg.transforms=[t]
            else:
                msg.header.stamp.sec=value
                if isinstance(msg,OccupancyGrid):
                    msg.header.frame_id='map';msg.info.height,msg.info.width=grid.shape;msg.info.resolution=saved['resolution']
                    msg.info.origin.position.x,msg.info.origin.position.y=saved['origin'];msg.info.origin.orientation.w=1.
                    msg.data=grid.ravel().tolist()
                    raw.append(dict(topic='/tb1/map' if topic=='/tb1/map' else '/merge_map',
                        cdr=base64.b64encode(serialize_message(msg)).decode()))
                else:
                    msg.header.frame_id='tb1/odom';msg.pose.pose.position.x,msg.pose.pose.position.y=event['position']
                    msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def invoke(request):
        done.clear();trigger.publish(String(data=request));assert done.wait(10.) and not errors,errors
    def fresh(value):
        for _ in range(12):tick(value);deliver(value);time.sleep(.03)
        until(lambda:node.now()==value and node.pose_source_age() is not None
            and node.return_map_source_time==value)
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values()))
        until(lambda:clock.get_subscription_count()==1 and node.navigation.server_is_ready())
        fresh(10);invoke('begin');assert node.mode==module.RETURNING
        fresh(11);invoke('dispatch')
        until(lambda:len(goals)==1 and not node.return_goal_pending and node.return_goal_handle is None)
        until(lambda:any(e['event']=='return_leg_sent' for e in events))
        if label=='current':assert math.dist(goals[0],event['position'])>3.
        else:assert math.dist(goals[0],event['position'])<.04
        for _ in range(8):tick(14);time.sleep(.03)
        until(lambda:node.now()==14.)
        invoke('expired_sources');assert len(goals)==1 and node.mode==module.RETURNING
        fresh(14);invoke('fresh_sources')
        until(lambda:len(goals)==2 and not node.return_goal_pending and node.return_goal_handle is None)
        fresh(15);invoke('low_energy');assert node.mode==module.FAILED and len(goals)==2
        legs=[e for e in events if e['event']=='return_leg_sent'];assert len(legs)==2
        if label=='current':
            bindings=[native_return_leg_audit(e) for e in legs]
            with tempfile.TemporaryDirectory() as directory:
                capture=Path(directory)/'capture.jsonl.gz'
                with gzip.open(capture,'wt') as stream:
                    for row in raw:stream.write(json.dumps(row)+'\n')
                sources=bind_original_maps(bindings,capture)
            assert sources==4
            audit=dict(status='PASS',legs=2,original_source_maps=sources)
        else:
            try:native_return_leg_audit(legs[0])
            except AssertionError:audit=dict(status='EXPECTED_REJECTION',reason='Old visible shortcut is not a complete-path prefix')
            else:raise AssertionError('Old short leg was accepted as a complete-path prefix')
        return dict(status='PASS',label=label,callbacks=callbacks,goals=goals,events=events,
            independent_audit=audit,stale_sources_rejected=True,reserve_floor_rejected=True,
            action_futures_closed=True)
    finally:
        server.destroy()
        for executor in executors:executor.shutdown()
        for thread in threads:thread.join(5.);assert not thread.is_alive()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_native_curves_reference');frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(source,'<frozen df0 native>','exec'),frozen.__dict__)
    fixture=json.loads(gzip.decompress(FIXTURE.read_bytes()));event=fixture['original_legs'][-2]
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_name:=tb1',
        '-p','capacity:=100.','-p','initial_energy:=40.','-p','charge_x:=0.','-p','charge_y:=-0.45'])
    try:
        result=dict(status='PASS',scope='Original native decision geometry; synthetic delivery epochs, stationary pose, return intent and low-energy mutation. Actual DDS/native safety timers and ActionClient Futures, no physical motion, native return completion or task causal claim.',
            reference_commit=REFERENCE,reference_source=source,fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            native_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen',event),case(current,'current',event)],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cases=len(result['cases']),goals=[r['goals'] for r in result['cases']],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
