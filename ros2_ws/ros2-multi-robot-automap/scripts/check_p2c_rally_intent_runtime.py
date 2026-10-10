#!/usr/bin/env python3
"""Actual DDS proofs for current serial authority and formal retarget roles."""
import argparse,base64,gzip,hashlib,json,math,subprocess,sys,tempfile,threading,time,types
from pathlib import Path

import numpy as np
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

from multi_robot_exploration import control as current
from check_p2c_dispatch_boundary_runtime import until
from check_p2c_gate import rally_proposal_audit
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_outbound_routes import audit_outbound,bind_original_maps,decode

REFERENCE='b488cd5ecd16f6061e19f6b8f47755fd055e51a8'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'
FIXTURE=Path(__file__).resolve().parents[1]/'src/multi_robot_exploration/test/fixtures/p2c_v63_rally_intent_input.json.gz'


def case(module,label,part):
    node=module.HeadquartersControl();probe=Node('p2c_rally_intent_'+part+'_'+label,use_global_arguments=False)
    for timer in node.timers:timer.cancel()
    ex=[MultiThreadedExecutor(num_threads=2) for _ in range(2)]
    for executor,member in zip(ex,(node,probe)):executor.add_node(member)
    threads=[threading.Thread(target=e.spin) for e in ex]
    for thread in threads:thread.start()
    if part=='serial':
        original=json.loads(gzip.decompress(FIXTURE.read_bytes()))['original_proposal']
        positions={n:tuple(p) for n,p in original['robot_positions'].items()};target=tuple(original['target'])
        poses={n:module.RallyPose(*v) for n,v in original['assignment'].items()}
        geometries={'fused':original['source_map'],**original['return_maps']}
        maps={n:dict(data=decode(s),resolution=s['resolution'],origin=s['origin']) for n,s in geometries.items()}
        home={n:(0.,0.) for n in positions}
    else:
        grid=np.full((50,100),100,dtype=np.int16);grid[19:31,1:99]=0;grid[8:26,35:46]=0
        for cell in module._line_cells((15,40),(25,64)):grid[cell]=0  # view slit, no traversable bypass
        positions={'tb1':(1.05,2.55),'tb2':(4.05,2.55)};target=(6.4,2.55)
        poses={'tb1':module.RallyPose(8.05,2.55,math.pi),'tb2':module.RallyPose(7.2,2.55,math.pi)}
        replacements={'tb1':module.RallyPose(5.55,2.55,0.),
            'tb2':module.RallyPose(4.05,1.55,math.atan2(1.,2.35))}
        maps={n:dict(data=grid,resolution=.1,origin=(0.,0.)) for n in ('fused',*positions)}
        home=dict.fromkeys(positions,(1.05,2.55))
    topics={'/merge_map':OccupancyGrid}
    for n in positions:topics.update({f'/gateway/received/{n}/'+k:t for k,t in
        [('map',OccupancyGrid),('odom',Odometry),('tf',TFMessage),('battery_state',String)]})
    pubs={topic:probe.create_publisher(kind,topic,QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if kind is String else 10) for topic,kind in topics.items()}
    clock=probe.create_publisher(Clock,'/clock',10);trigger=probe.create_publisher(String,'/p2c_rally_intent/run',10)
    events=[];raw=[];goals=[];calls=[];errors=[];budgets=[];searches=[];done=threading.Event();proposal=None
    subscription=probe.create_subscription(String,'/gateway/consumed',lambda msg:events.append(json.loads(msg.data)),100)
    servers=[]
    def execute(handle,name):
        p=handle.request.pose.pose.position;goals.append(dict(robot=name,position=[p.x,p.y]))
        handle.succeed();return NavigateToPose.Result()
    if part=='retarget':
        servers=[ActionServer(probe,NavigateToPose,f'/gateway/{n}/navigate_to_pose',
            lambda handle,name=n:execute(handle,name)) for n in positions]
    def tick(value):msg=Clock();msg.clock.sec=value;clock.publish(msg)
    old_search=module.map_safe_rally_dispatch_order
    old_refuge=module.rally_yield_pose;old_replacement=module.reassign_rally_pose
    def expiring_search(*args,**kwargs):
        order=old_search(*args,**kwargs);searches.append(order)
        later=14 if node.now()<14 else 17
        for _ in range(8):tick(later);time.sleep(.02)
        until(lambda:node.now()==later)
        return order
    if part=='serial':module.map_safe_rally_dispatch_order=expiring_search
    def price(name,plan):
        result=module.HeadquartersControl.rally_plan_has_energy(node,name,plan)
        budgets.append(dict(robot=name,clock=node.now(),energy=node.battery_states[name]['energy'],accepted=result))
        return result
    if part=='retarget':node.rally_plan_has_energy=price
    def run(msg):
        nonlocal proposal
        try:
            if part=='serial':
                if proposal is None:
                    node.task_state='FOUND';node.target=target;node.target_received_source_time=10.;node.detecting_robot='tb2'
                    proposal=dict(assignment=poses,target=target,evaluated_at=10.)
                    module.HeadquartersControl.record_rally_assignment(node,dict(node.robot_positions),
                        module.HeadquartersControl.delivered_return_maps(node),0.,poses,10.)
                accepted=module.HeadquartersControl.admit_rally_proposal(node,proposal)
                calls.append(dict(request=msg.data,clock=node.now(),accepted=accepted))
            elif msg.data=='retarget':
                node.task_state='RALLY';node.target=target;node.target_received_source_time=10.;node.detecting_robot='tb1'
                node.rally_targets=dict(poses);node.rally_final_targets=dict(poses);node.rally_dispatch_order=list(poses)
                node.rally_preflight_complete=True;node.rally_precharge_active=False
                node.rally_route_unavailable_since={'tb1':0.,'tb2':None};node.last_rally_dispatch_at=0.
                node.return_yield_targets={'tb1':'tb2'};node.rally_yield_targets={'tb1'};node.rally_probe_targets={'tb1'}
                # Condition the geometric chooser on a permanent replacement;
                # keep actual complete body/local leg and ordinary price checks.
                module.rally_yield_pose=lambda *a,**k:None
                module.reassign_rally_pose=lambda *a,**k:replacements[a[3]]
                try:module.HeadquartersControl.update_mission(node)
                finally:module.rally_yield_pose=old_refuge;module.reassign_rally_pose=old_replacement
                calls.append(dict(request=msg.data,clock=node.now(),target=list(node.rally_targets['tb1'].__dict__.values())
                    if hasattr(node.rally_targets['tb1'],'__dict__') else [node.rally_targets['tb1'].x,node.rally_targets['tb1'].y,node.rally_targets['tb1'].yaw],
                    return_yields=dict(node.return_yield_targets),temporary_yields=sorted(node.rally_yield_targets),probes=sorted(node.rally_probe_targets)))
            else:
                node.target_received_source_time=-60. if msg.data=='expired_target' else node.now()
                plan=module.plan_rally_leg(node.rally_targets['tb1'],node.map_data,node.resolution,node.origin,
                    node.robot_positions['tb1'],blocked_positions=[node.robot_positions['tb2']],local_map=node.robot_maps['tb1'])
                assert plan[0] is not None
                module.HeadquartersControl.send_rally_goal(node,'tb1',plan)
                calls.append(dict(request=msg.data,clock=node.now(),goals_before_future=len(goals)))
        except Exception as error:errors.append(repr(error))
        finally:done.set()
    control_subscription=node.create_subscription(String,'/p2c_rally_intent/run',run,10)
    def deliver(value,low=False):
        for topic,pub in pubs.items():
            msg=topics[topic]();n=next((n for n in positions if '/'+n+'/' in topic),'tb1')
            if isinstance(msg,String):
                msg.data=json.dumps(dict(stamp_sec=value,mode='ACTIVE',energy=.1 if low and n=='tb1' else 80.,
                    capacity=100.,charge_target_fraction=.8,charge_x=home[n][0],charge_y=home[n][1],charge_radius_m=.8,
                    move_cost_per_m=1.,idle_cost_per_sec=.02,nominal_speed_mps=.18,return_path_factor=2.,return_safety_margin=8.,charge_duration_sec=6.))
            elif isinstance(msg,TFMessage):
                t=TransformStamped();t.header.stamp.sec=value;t.header.frame_id='map';t.child_frame_id=n+'/odom'
                t.transform.rotation.w=1.;msg.transforms=[t]
            else:
                msg.header.stamp.sec=value
                if isinstance(msg,OccupancyGrid):
                    g=maps['fused' if topic=='/merge_map' else n];msg.header.frame_id='map'
                    msg.info.height,msg.info.width=g['data'].shape;msg.info.resolution=g['resolution']
                    msg.info.origin.position.x,msg.info.origin.position.y=g['origin'];msg.info.origin.orientation.w=1.
                    msg.data=g['data'].ravel().tolist()
                    raw.append(dict(topic='/merge_map' if topic=='/merge_map' else '/'+n+'/map',
                        cdr=base64.b64encode(serialize_message(msg)).decode()))
                else:
                    msg.header.frame_id=n+'/odom';msg.pose.pose.position.x,msg.pose.pose.position.y=positions[n]
                    msg.pose.pose.orientation.w=1.
            pub.publish(msg)
    def fresh(value,low=False):
        for _ in range(12):tick(value);deliver(value,low);time.sleep(.03)
        until(lambda:node.now()==value and node.fresh_robot_inputs()
            and all(node.robot_tf_received_at[n]==value and node.robot_odom_received_at[n]==value for n in positions)
            and node.battery_states['tb1']['energy']==(.1 if low else 80.))
    def invoke(request):done.clear();trigger.publish(String(data=request));assert done.wait(15.) and not errors,errors
    def closed():until(lambda:not any(node.rally_goal_handles.values()) and not any(node.rally_goal_pending.values()))
    try:
        until(lambda:trigger.get_subscription_count()==1 and all(p.get_subscription_count()==1 for p in pubs.values())
            and node.consumed_publisher.get_subscription_count()==1)
        fresh(10)
        if part=='serial':
            invoke('search_expires');assert calls[-1]['accepted'] is False
            fresh(14);invoke('new_sources');assert calls[-1]['accepted'] is (label=='current'),calls
            assert len(searches)==(1 if label=='current' else 2)
            for _ in range(8):tick(20);time.sleep(.02)
            until(lambda:node.now()==20);invoke('sources_expired');assert calls[-1]['accepted'] is False
            until(lambda:sum(e.get('event')=='coordinator_rally_proposal_admitted' for e in events)==(label=='current'))
        else:
            until(lambda:all(client.server_is_ready() for client in node.robot_nav_clients.values()))
            invoke('retarget');closed();until(lambda:len(goals)==1)
            assert node.rally_targets['tb1']==replacements['tb1']
            assert ('tb1' in node.return_yield_targets) is (label=='frozen')
            positions['tb2']=(replacements['tb2'].x,replacements['tb2'].y)
            fresh(11);invoke('formal_goal');closed();until(lambda:len(goals)==2)
            for _ in range(8):tick(14);time.sleep(.02)
            until(lambda:node.now()==14);invoke('sources_expired');closed();assert len(goals)==2
            fresh(14);invoke('expired_target');closed()
            until(lambda:len(goals)==(2 if label=='current' else 3))
            fresh(15,low=True);invoke('unfunded');closed()
            until(lambda:len(goals)==(2 if label=='current' else 4))
            until(lambda:sum(e.get('event')=='coordinator_navigation_decision' for e in events)==len(goals))
            tb1=[e for e in events if e.get('event')=='coordinator_navigation_decision' and e['robot']=='tb1']
            assert [e['kind'] for e in tb1]==(['rally'] if label=='current' else ['local_return_yield']*3)
            assert sum(b['robot']=='tb1' for b in budgets)==(2 if label=='current' else 0)
        with tempfile.TemporaryDirectory() as directory:
            capture=Path(directory)/'capture.jsonl.gz';ledger=Path(directory)/'ledger.jsonl'
            with gzip.open(capture,'wt') as stream:
                for row in raw:stream.write(json.dumps(row)+'\n')
            ledger.write_text(''.join(json.dumps(e)+'\n' for e in events))
            if part=='serial':
                audit=rally_proposal_audit(events,True,True,capture,True) if label=='current' else dict(status='EXPECTED_REJECTION',reason='Repeated full search consumes the deliberately advanced original lease')
            else:
                decisions=[e for e in events if e.get('event')=='coordinator_navigation_decision']
                for event in decisions:assert audit_outbound(event)>1
                sources=bind_original_maps(decisions,capture)
                if label=='current':audit=navigation_dispatch_audit(ledger,True,True)
                else:
                    try:navigation_dispatch_audit(ledger,True,True)
                    except (AssertionError,KeyError):audit=dict(status='EXPECTED_REJECTION',reason='Old formal retarget retains local-return role and lacks the new transition witness')
                    else:raise AssertionError('Old stale role accepted')
                audit['original_source_maps']=sources
        assert not any(node.rally_goal_handles.values()) and not any(node.rally_goal_pending.values())
        return dict(status='PASS',label=label,calls=calls,goals=goals,searches=searches,budget_calls=budgets,
            events=events,independent_audit=audit,action_futures_closed=True)
    finally:
        module.map_safe_rally_dispatch_order=old_search;module.rally_yield_pose=old_refuge;module.reassign_rally_pose=old_replacement
        for server in servers:server.destroy()
        for executor in ex:executor.shutdown()
        for thread in threads:thread.join(5.);assert not thread.is_alive()
        node.destroy_node();probe.destroy_node()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--part',choices=('serial','retarget'),required=True);args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite component evidence')
    source=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    frozen=types.ModuleType('p2c_rally_intent_reference_'+args.part);frozen.__file__=current.__file__
    frozen.__package__='multi_robot_exploration';sys.modules[frozen.__name__]=frozen
    exec(compile(source,'<frozen b488>','exec'),frozen.__dict__)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:='+('3' if args.part=='serial' else '2'),
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        result=dict(status='PASS',part=args.part,scope='Conditional original proposal geometry or synthetic corridor/permanent chooser and stale refuge state; synthetic delivery/clock/target/energy. Actual DDS, production retarget state transition, complete body/local legs and ordinary budget/target checks, ActionClient Futures. No physical motion, original live replay, task causality or worst-case deadline claim.',
            reference_commit=REFERENCE,reference_source=source,fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            cases=[case(frozen,'frozen',args.part),case(current,'current',args.part)],all_owned_closed=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',part=args.part,cases=2,goals=[len(r['goals']) for r in result['cases']],all_owned_closed=True)))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
