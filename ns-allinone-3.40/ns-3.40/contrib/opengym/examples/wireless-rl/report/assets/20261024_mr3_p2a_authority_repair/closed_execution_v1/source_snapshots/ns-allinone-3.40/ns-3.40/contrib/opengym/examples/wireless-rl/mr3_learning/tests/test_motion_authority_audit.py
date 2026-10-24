"""Artificial authority artifact attacks; no producer authority is an oracle."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from mr3_learning import motion_authority_audit as a
from mr3_learning import motion_authority_profile as profile

EPOCH='independent-authority';ROBOT='tb1';GID='12'*24

def graph(ack=False):
    return dict(scope='graph_at_callback',packet_publisher_gid_available=False,error=None,valid=True,
        topic='/tb1/mr3/motion_authority'+('_ack' if ack else ''),endpoints=[dict(
            node_name='motion_safety' if ack else 'mr3_adapter',node_namespace='/',
            topic_type='std_msgs/msg/String',endpoint_gid=GID)])

def raw(t):
    return dict(header=dict(stamp=dict(sec=t//10**9,nanosec=t%10**9),frame_id='odom'),
        child_frame_id='base_footprint',pose=dict(pose=dict(position=dict(x=0.,y=0.,z=0.),
            orientation=dict(x=0.,y=0.,z=0.,w=1.)),covariance=[0.]*36),
        twist=dict(twist=dict(linear=dict(x=0.,y=0.,z=0.),angular=dict(x=0.,y=0.,z=0.)),covariance=[0.]*36))

def packet(seq=1,op='grant',now=1_010_000_000,goal=1,grant=1,lease=None):
    return dict(schema=a.PACKET,epoch=EPOCH,robot=ROBOT,operation=op,authority_sequence=seq,
        owner_grant_sequence=grant,goal_id=f'{EPOCH}:tb1:{goal}',native_goal_uuid=('%02x'%goal)*16,
        owner_command_id=goal,owner_accept_received_clock_ns=1_000_000_000,source_clock_ns=now,
        lease_until_ns=(now if op=='revoke' else now+1_000_000_000) if lease is None else lease)

def callback(gate,p,now=None):
    now=p['source_clock_ns'] if now is None else now
    seq,op=p['authority_sequence'],p['operation']
    if seq<gate.seq:result=dict(accepted=False,reason='stale_authority',state=gate.state)
    elif seq==gate.seq:result=dict(accepted=True,reason='duplicate',state=gate.state)
    else:
        result=dict(schema=a.ACK,epoch=EPOCH,robot=ROBOT,authority_sequence=seq,
            stage='authority_received',accepted=True,state='REVOKED' if op=='revoke' else 'ACTIVE',
            received_clock_ns=now,source_clock_ns=p['source_clock_ns'],
            callback_floor=gate.raw_seq if op=='grant' else gate.floor,
            scope='actual authority callback only, not target storage, motor or rest')
    return dict(robot=ROBOT,message=copy.deepcopy(p),raw_json=a.canonical(p),packet_sha256=a.digest(p),
                publisher_identity=graph(),clock_ns=now,result=result)

def evidence(nonzero_history=False,rims=(0.,0.)):
    times=[0,960_000_000,980_000_000,1_000_000_000]
    native=dict(commands={},actuations={},odometry={t:dict(odometry=raw(t)) for t in times})
    t=dict(schema='mr3-drive-target-v1',epoch=EPOCH,robot=ROBOT,clock_ns=0,
           decision_sequence=1,linear_x=0.,angular_z=0.)
    command=dict(sim_time_ns=0,target_decision_sequence=1,target_clock_ns=0,desired_v=0.,desired_w=0.)
    native['commands'][1]=command
    pair=dict(pair_index=0,current_rim_mps=[0.,0.],desired_rim_mps=[0.,0.],applied_rim_mps=list(rims),
              alpha=1.,max_acceleration_mps2=1.)
    actual=dict(sim_time_ns=997_000_000,cmd_seq=1,dt_ns=34_000_000,desired_v=0.,desired_w=0.,**pair)
    native['actuations'][2]=[actual]
    applied=dict(schema='mr3-drive-applied-v1',epoch=EPOCH,robot=ROBOT,source_clock_ns=997_000_000,
        actuation_sequence=2,cmd_seq=1,dt_ns=34_000_000,target=t,pairs=[pair])
    stored=dict(schema='mr3-drive-target-consumed-v1',epoch=EPOCH,robot=ROBOT,clock_ns=0,
                source_clock_ns=0,decision_sequence=1,cmd_seq=1,linear_x=0.,angular_z=0.)
    intent=dict(schema='mr3-safety-intent-v1',epoch=EPOCH,robot=ROBOT,intent_sequence=1,
        source_clock_ns=0,role='HOLD',anchor=dict(source_clock_ns=0,odometry=raw(0)),
        admitted_signs=[],lineage=dict(release_clock_ns=0),target=t)
    ev=a.StopEvidence(EPOCH,ROBOT,0,native);index=0;calibrations={}
    def put(kind,p):
        nonlocal index
        index+=1;ev.ingest(dict(kind=kind,payload=p),index)
    def feed(kind,value):put('reach_driver_ingress',dict(robot=ROBOT,kind=kind,message=value,raw_json=a.canonical(value)))
    for t0 in times:
        message=raw(t0);cal=dict(schema='mr3-odom-calibration-v1',epoch=EPOCH,robot=ROBOT,
            source_clock_ns=t0,publication_sequence=times.index(t0)+1,coefficient_c=1.,coefficient_s=0.,
            odometry=message,conversion_contract='float32-trig-binary64-rn-v1',producer_frame='world-common-model-origin-v1')
        put('own_odom',dict(robot=ROBOT,message=message));feed('calibration',cal);calibrations[t0]=cal
    put('reach_intent_publish',dict(robot=ROBOT,intent=intent,payload_sha256=a.digest(intent)))
    feed('storage',stored)
    if nonzero_history:
        old=copy.deepcopy(applied);old.update(actuation_sequence=1,source_clock_ns=990_000_000)
        old['target']['linear_x']=.1
        native['actuations'][1]=[dict(actual,sim_time_ns=990_000_000,desired_v=.1)]
        feed('applied',old)
    feed('applied',applied)
    witness=dict(schema='mr3-normal-zero-authority-witness-v1',epoch=EPOCH,robot=ROBOT,
        clock_ns=1_006_000_000,not_before_ns=0,zero_publication_since_ns=0,zero_storage_since_ns=0,
        storage=stored,applied=applied,actual_rims_zero=list(rims)==[0.,0.],
        after_real_nonzero_application=nonzero_history,
        rest=[dict(source_clock_ns=s,odometry=raw(s),calibration=calibrations[s]) for s in times[1:]],
        reach_role='HOLD',anchor=intent['anchor'],permanent_stop=False,continuous_physics_proved=False)
    return ev,index+1,witness


class IndependentAuthorityTests(unittest.TestCase):
    def ready(self):
        ev,index,witness=evidence();ev.witness(witness,1_006_000_000,index,0)
        gate=a.ReceivingReplay(EPOCH,ROBOT,GID,ev)
        self.assertIsNotNone(gate.observe(1_006_000_000,index))
        return gate

    def test_actual_zero_evidence_then_grant_floor_and_generation_unknown(self):
        gate=self.ready();request=dict(sequence=1,v=.1,w=.2);gate.raw_callback(request)
        gate.receive(callback(gate,packet()),100)
        self.assertEqual(gate.permission(request,1_011_000_000)['effective_request'],[0.,0.])
        request=dict(sequence=2,v=.1,w=.2);gate.raw_callback(request)
        result=gate.permission(request,1_012_000_000)
        self.assertEqual(result['effective_request'],[.1,.2]);self.assertIsNone(result['raw_goal_generation'])
        self.assertEqual(result['raw_goal_association'],'UNKNOWN_UNSTAMPED_TWIST')

    def test_grant_without_local_stop_or_forged_callback_result_rejected(self):
        ev,_,_=evidence();gate=a.ReceivingReplay(EPOCH,ROBOT,GID,ev)
        with self.assertRaisesRegex(ValueError,'fresh local stop'):gate.receive(callback(gate,packet()),100)
        gate=self.ready();row=callback(gate,packet());row['result']['callback_floor']=9
        with self.assertRaisesRegex(ValueError,'transition table'):gate.receive(row,100)

    def test_revoke_stops_nonzero_raw_and_retired_owner_never_regranted(self):
        gate=self.ready();grant=packet();gate.receive(callback(gate,grant),100)
        gate.raw_callback(dict(sequence=1,v=.1,w=0.))
        self.assertEqual(gate.permission(gate.raw,1_012_000_000)['effective_request'],[.1,0.])
        revoke=packet(2,'revoke',1_020_000_000);gate.receive(callback(gate,revoke),101)
        self.assertEqual(gate.permission(gate.raw,1_021_000_000)['effective_request'],[0.,0.])
        reborn=packet(3,'grant',1_030_000_000,grant=3)
        with self.assertRaises(ValueError):gate.receive(callback(gate,reborn),102)

    def test_duplicate_and_stale_do_not_refresh_lease_or_floor(self):
        gate=self.ready();p=packet();gate.receive(callback(gate,p),100)
        gate.raw_callback(dict(sequence=1,v=.1,w=0.))
        gate.receive(callback(gate,p,1_020_000_000),101)
        self.assertEqual(gate.floor,0);self.assertEqual(gate.received,p['source_clock_ns'])
        self.assertEqual(gate.permission(gate.raw,p['lease_until_ns'])['effective_request'],[0.,0.])
        bad=copy.deepcopy(p);bad['lease_until_ns']+=1
        with self.assertRaisesRegex(ValueError,'same-sequence'):gate.receive(callback(gate,bad),102)

    def test_renew_owner_and_original_two_second_lease_enforced(self):
        gate=self.ready();gate.receive(callback(gate,packet()),100)
        renew=packet(2,'renew',1_020_000_000,lease=3_020_000_001)
        with self.assertRaisesRegex(ValueError,'two-second'):gate.receive(callback(gate,renew),101)
        renew=packet(2,'renew',1_020_000_000,goal=2)
        with self.assertRaisesRegex(ValueError,'matching owner'):gate.receive(callback(gate,renew),101)

    def test_stop_requires_actual_applied_motor_zero_after_every_nonzero_callback(self):
        ev,index,witness=evidence(nonzero_history=True,rims=(.001,-.001))
        self.assertTrue(ev.sticky_motion)
        witness['after_real_nonzero_application']=False
        with self.assertRaisesRegex(ValueError,'actual servo'):ev.witness(witness,1_006_000_000,index,0)
        ev,index,witness=evidence(rims=(.001,-.001))
        ev.witness(witness,1_006_000_000,index,0) # Initial encoder correction is disclosed.

    def test_stop_anchor_rest_storage_and_original_debts_not_asserted_flags(self):
        for part in ('anchor','storage','rest','debt'):
            ev,index,witness=evidence()
            if part=='anchor':witness['anchor']['odometry']['pose']['pose']['position']['x']=.01
            elif part=='storage':witness['storage']['cmd_seq']=9
            elif part=='rest':witness['rest'][0]['source_clock_ns']-=1
            else:witness['zero_publication_since_ns']=1
            with self.subTest(part=part),self.assertRaises(ValueError):ev.witness(witness,1_006_000_000,index,0)

    def test_raw_bytes_duplicate_keys_and_graph_scope_not_packet_authentication(self):
        gate=self.ready();row=callback(gate,packet());row['raw_json']='{"schema":1,"schema":2}'
        with self.assertRaises(ValueError):gate.receive(row,100)
        row=callback(self.ready(),packet());row['publisher_identity']['scope']='authenticated_packet'
        with self.assertRaisesRegex(ValueError,'no packet authentication'):self.ready().receive(row,100)


class DeferredTests(unittest.TestCase):
    def setup_chain(self):
        current=packet(2,'revoke',6_000_000_000)
        delivery=dict(epoch=EPOCH,stream='receipt',source=ROBOT,sequence=3,version=3,
            source_stamp=6.,generated_stamp=6.,received_stamp=6.2,
            payload=dict(type='result',robot=ROBOT,goal_id=current['goal_id'],value=5))
        ready=dict(schema=a.WIRE,profile=a.PROFILE,epoch=EPOCH,robot=ROBOT,ack_sequence=4,
            clock_ns=7_000_000_000,authority_packet_sha256=a.digest(current),ack=dict(
                stage='stop_obligation_ready',authority_sequence=2,owner=current))
        scheduler=a.DeferredTerminals()
        self.assertFalse(scheduler.delivery(delivery,6_200_000_000,'canceling',True))
        buffered=dict(robot=ROBOT,goal_id=current['goal_id'],delivery=delivery,authority_sequence=2,
                      buffered_clock_ns=6_200_000_000,receipt_times_rewritten=False)
        scheduler.buffer(buffered,6_200_000_000,current)
        scheduler.ready_callback(ROBOT,ready,7_020_000_000)
        dispatch=dict(robot=ROBOT,goal_id=current['goal_id'],original_delivery=delivery,
            matching_ready_ack=ready,dispatch_clock_ns=7_040_000_000,receipt_times_rewritten=False)
        return scheduler,current,delivery,dispatch

    def test_true_delivery_preserved_until_matching_received_stop_ready_dispatch(self):
        scheduler,current,delivery,dispatch=self.setup_chain()
        result=scheduler.dispatch(dispatch,7_040_000_000,current);scheduler.finish()
        self.assertEqual(result,delivery['payload']);self.assertEqual(dispatch['original_delivery']['received_stamp'],6.2)

    def test_no_ready_wrong_owner_rewritten_receipt_and_early_dispatch_rejected(self):
        for attack in ('no_ready','owner','receipt','early'):
            scheduler,current,delivery,dispatch=self.setup_chain()
            if attack=='no_ready':scheduler.ready.clear()
            elif attack=='owner':current=packet(3,'revoke',6_000_000_000,goal=2,grant=2)
            elif attack=='receipt':dispatch['original_delivery']=copy.deepcopy(delivery);dispatch['original_delivery']['received_stamp']=7.04
            else:dispatch['dispatch_clock_ns']=7_000_000_000
            with self.subTest(attack=attack),self.assertRaises(ValueError):
                scheduler.dispatch(dispatch,dispatch['dispatch_clock_ns'],current)

    def test_cleanup_requires_irreversible_stop_and_claims_no_normal_rest(self):
        scheduler,current,delivery,dispatch=self.setup_chain();scheduler.ready.clear()
        cleanup=dict(robot=ROBOT,goal_id=current['goal_id'],original_delivery=delivery,
            dispatch_clock_ns=7_040_000_000,receipt_times_rewritten=False,dispatcher_stopped=True,
            motion_regrant_allowed=False,normal_stop_evidence_claimed=False)
        with self.assertRaises(ValueError):scheduler.cleanup_dispatch(cleanup,7_040_000_000,current,False)
        changed=dict(cleanup,normal_stop_evidence_claimed=True)
        with self.assertRaises(ValueError):scheduler.cleanup_dispatch(changed,7_040_000_000,current,True)
        self.assertEqual(scheduler.cleanup_dispatch(cleanup,7_040_000_000,current,True),delivery['payload'])
        scheduler.finish()

    def test_normal_dispatch_rejects_old_ready_even_if_received_recently(self):
        scheduler,current,delivery,dispatch=self.setup_chain()
        dispatch['dispatch_clock_ns']=7_100_000_001
        with self.assertRaises(ValueError):scheduler.dispatch(dispatch,7_100_000_001,current)

    def test_cancel_result_without_buffer_and_unclosed_tail_rejected(self):
        scheduler,current,delivery,dispatch=self.setup_chain()
        with self.assertRaisesRegex(ValueError,'unclosed'):scheduler.finish()
        del scheduler.buffered[ROBOT]
        with self.assertRaisesRegex(ValueError,'buffer'):scheduler.dispatch(dispatch,7_040_000_000,current)


class ProfileTests(unittest.TestCase):
    def test_exact_types_fixed_profile_and_missing_qualification_rejected(self):
        class Fake:
            def __eq__(self,other):return True
        for value in (True,Fake(),type('S',(str,),{})('mr3-reach-v1')):
            with self.assertRaises(ValueError):profile.motion_authority_profile_for_safety_contract(value)
        self.assertEqual(profile.motion_authority_profile_for_safety_contract('mr3-reach-v1'),a.PROFILE)
        self.assertIsNone(profile.motion_authority_profile_for_safety_contract('legacy'))
        with self.assertRaises(ValueError):profile.require_qualified_motion_authority(dict(
            motion_authority_profile=a.PROFILE,safety_contract='mr3-reach-v1'))


def adapter_fixture(*,natural=False,quick=False,external=False):
    ros=Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration')
    sys.path.insert(0,str(ros))
    from multi_robot_exploration.mr3_protocol import GoalDispatcher
    events=[];oracle=GoalDispatcher(EPOCH,lambda p:events.append(copy.deepcopy(p)))
    rows=[];transitions=[];ack_publications=[];callbacks=[];seq=0;current=None
    goal=f'{EPOCH}:tb1:1';uuid='01'*16
    def record(kind,p,now):rows.append(dict(epoch=EPOCH,kind=kind,stamp=now,payload=copy.deepcopy(p)))
    record('authority_configuration',dict(motion_authority_profile=a.PROFILE,six_navigation_phases_unchanged=True,
        worker_quantum_ack_barrier=False,raw_goal_generation=None,raw_goal_association='UNKNOWN_UNSTAMPED_TWIST'),1.)
    record('task_start',dict(start_sim_time_sec=1.),1.)
    def flush(now):
        while events:record('protocol',events.pop(0),now)
    def act(now,identity,action):
        snap=dict(sequence=identity,digest=f'digest{identity}',candidate_version=1,
            joint_action_mask=[True]*1000,candidates=[dict(x=5.,y=0.)]*8,
            robots=[dict(name=n,navigation=v) for n,v in oracle.navigation(now).items()])
        command=dict(epoch=EPOCH,command_id=identity,observation_sequence=identity,
            observation_digest=snap['digest'],action=action,created_at=now,expires_at=now+2.)
        transitions.append(dict(snapshot=snap,info=dict(command=command)))
        choices=[action//100,action//10%10,action%10];results={}
        for name,choice in zip(a.ROBOTS,choices):
            results[name]=oracle.submit(name,'GOAL' if choice<8 else 'KEEP' if choice==8 else 'WAIT',
                now,identity,identity,now+2.,goal=dict(x=5.,y=0.) if choice<8 else None,
                command_epoch=EPOCH,created_at=now)
        record('action',dict(command_id=identity,action=action,results=results,
            observation_sequence=identity,observation_digest=snap['digest'],candidate_version=1,choices=choices),now)
        flush(now)
    def envelope(kind,value,source,received):
        nonlocal seq
        seq+=1
        return dict(epoch=EPOCH,stream='receipt',source=ROBOT,sequence=seq,version=seq,
            source_stamp=source,generated_stamp=source,received_stamp=received,
            payload=dict(type=kind,robot=ROBOT,goal_id=goal,value=value))
    def ready(authority_seq,owner,at,received):
        wire=dict(schema=a.WIRE,profile=a.PROFILE,epoch=EPOCH,robot=ROBOT,ack_sequence=1 if owner is None else 8,
            clock_ns=a.clock(at),authority_packet_sha256=None if owner is None else a.digest(owner),
            ack=dict(schema=a.ACK,epoch=EPOCH,robot=ROBOT,stage='stop_obligation_ready',
                authority_sequence=authority_seq,owner=copy.deepcopy(owner),received_clock_ns=None,
                witness=dict(schema='mr3-normal-zero-authority-witness-v1',epoch=EPOCH,robot=ROBOT,clock_ns=a.clock(at))))
        # Full witness belongs to replay_motion/StopEvidence, already tested
        # separately. This fixture exercises the strict adapter-side join.
        publication=dict(robot=ROBOT,message=wire,raw_json=a.canonical(wire),scope='publication_call_returned; not delivery')
        ack_publications.append((len(ack_publications)+1,publication))
        record('authority_ack_callback',dict(robot=ROBOT,message=wire,raw_json=a.canonical(wire),
            publisher_identity=graph(True),clock_ns=a.clock(received)),received)
        return wire
    def publish(op,now,authority_seq,lease):
        nonlocal current
        state=oracle.states[ROBOT]
        current=dict(schema=a.PACKET,epoch=EPOCH,robot=ROBOT,operation=op,authority_sequence=authority_seq,
            owner_grant_sequence=1,goal_id=goal,native_goal_uuid=uuid,owner_command_id=1,
            owner_accept_received_clock_ns=a.clock(1.1),source_clock_ns=a.clock(now),lease_until_ns=a.clock(lease))
        record('authority_publication',dict(robot=ROBOT,packet=current,raw_json=a.canonical(current),
            packet_sha256=a.digest(current),clock_ns=a.clock(now),scope='publication_call_returned'),now)
        callbacks.append((len(callbacks)+1,dict(message=copy.deepcopy(current),clock_ns=a.clock(now)+1)))
    act(1.,1,88)
    record('native_send',dict(robot=ROBOT,goal_id=goal,command_id=1),1.)
    accepted=dict(robot=ROBOT,goal_id=goal,native_goal_uuid=uuid,accepted_callback_clock_ns=a.clock(1.05))
    record('authority_native_accept_callback',accepted,1.05)
    terminal=None
    if quick:
        terminal=dict(robot=ROBOT,goal_id=goal,status=4,native_identity=accepted,terminal_callback_clock_ns=a.clock(1.08))
        record('authority_native_terminal_callback',terminal,1.08)
    accept=envelope('accept',True,1.05,1.1);record('delivery',accept,1.1);oracle.on_accept(ROBOT,goal,True,1.1);flush(1.1)
    if quick:
        record('authority_never_granted_terminal',dict(robot=ROBOT,goal_id=goal,native_terminal=terminal,
            accept_delivery=accept,permission='zero_only'),1.1)
        result=envelope('result',4,1.08,1.2);record('delivery',result,1.2);oracle.on_result(ROBOT,goal,4,1.2);flush(1.2)
        return rows,transitions,dict(ack_publications=ack_publications,callbacks=callbacks),GoalDispatcher
    ready(0,None,1.1,1.12);publish('grant',1.12,1,3.)
    if natural:
        terminal=dict(robot=ROBOT,goal_id=goal,status=4,native_identity=accepted,terminal_callback_clock_ns=a.clock(1.3))
        record('authority_native_terminal_callback',terminal,1.3)
        result=envelope('result',4,1.3,1.5);record('delivery',result,1.5)
        oracle.tick(1.5);publish('revoke',1.5,2,1.5);oracle.on_result(ROBOT,goal,4,1.5);flush(1.5)
        return rows,transitions,dict(ack_publications=ack_publications,callbacks=callbacks),GoalDispatcher
    for k in range(2,7):
        heartbeat=dict(epoch=EPOCH,stream='heartbeat',source=ROBOT,sequence=k-1,version=k-1,
            source_stamp=float(k),generated_stamp=float(k),received_stamp=float(k),
            payload=dict(goal_id=goal,expires_at=float(k+2)))
        record('delivery',heartbeat,float(k));oracle.renew(ROBOT,goal,EPOCH,float(k),float(k+2))
        publish('renew',float(k),k,float(k+2));flush(float(k))
    if external:
        record('authority_task_stop_callback',dict(message=dict(stamp=dict(sec=6,nanosec=200_000_000),
            frame_id='map'),clock_ns=a.clock(6.2),started_at=1.),6.2)
        oracle.safety_stop(6.2,'task_stop');flush(6.2)
    else:act(6.2,2,988)
    record('native_cancel',dict(robot=ROBOT,goal_id=goal,stamp=6.2,scope='native_cancel_call_attempt'),6.2)
    publish('revoke',6.2,7,6.2)
    canceled=envelope('cancel',True,6.3,6.4);record('delivery',canceled,6.4)
    oracle.on_cancel_response(ROBOT,goal,True,6.4);flush(6.4)
    terminal=dict(robot=ROBOT,goal_id=goal,status=5,native_identity=accepted,terminal_callback_clock_ns=a.clock(6.3))
    # Callback stamp precedes delivery; preserve actual source order.
    record('authority_native_terminal_callback',terminal,6.4)
    terminal['terminal_callback_clock_ns']=a.clock(6.4);rows[-1]['payload']=copy.deepcopy(terminal)
    result=envelope('result',5,6.4,6.5);record('delivery',result,6.5)
    record('authority_terminal_buffered',dict(robot=ROBOT,goal_id=goal,delivery=result,
        authority_sequence=7,buffered_clock_ns=a.clock(6.5),receipt_times_rewritten=False),6.5)
    if external:
        record('authority_terminal_cleanup_dispatched',dict(robot=ROBOT,goal_id=goal,
            original_delivery=result,dispatch_clock_ns=a.clock(6.5),receipt_times_rewritten=False,
            dispatcher_stopped=True,motion_regrant_allowed=False,normal_stop_evidence_claimed=False),6.5)
        oracle.on_result(ROBOT,goal,5,6.5);flush(6.5)
        return rows,transitions,dict(ack_publications=ack_publications,callbacks=callbacks),GoalDispatcher
    wire=ready(7,current,7.2,7.22)
    record('authority_terminal_dispatched',dict(robot=ROBOT,goal_id=goal,original_delivery=result,
        matching_ready_ack=wire,dispatch_clock_ns=a.clock(7.24),receipt_times_rewritten=False),7.24)
    oracle.on_result(ROBOT,goal,5,7.24);flush(7.24)
    return rows,transitions,dict(ack_publications=ack_publications,callbacks=callbacks),GoalDispatcher


class WholeAdapterTests(unittest.TestCase):
    def test_original_float_stop_gate_rejects_same_ns_ulp_edge_but_allows_later_dispatch(self):
        rows,steps,context,cls=adapter_fixture(natural=True)
        payload=dict(message=dict(stamp=dict(sec=2,nanosec=780_000_000),frame_id='map'),
            clock_ns=2_780_000_000,started_at=1.)
        rows.append(dict(epoch=EPOCH,kind='authority_task_stop_callback',stamp=2.78,payload=payload))
        self.assertGreater(2+780_000_000/1e9,2_780_000_000/1e9)
        with self.assertRaisesRegex(ValueError,'original float dispatch gate'):
            a.replay_adapter(rows,steps,EPOCH,context,cls)
        rows[-1]['stamp']=2.8;payload['clock_ns']=2_800_000_000
        self.assertTrue(a.replay_adapter(rows,steps,EPOCH,context,cls)['passed'])

    def test_unknown_authority_namespaces_and_unjustified_stale_ack_rejected_in_both_routes(self):
        rows,steps,context,cls=adapter_fixture()
        for kind in ('authority_future_extension','invalid_authority_extension','authority_ack_stale'):
            bad=copy.deepcopy(rows)
            bad.append(dict(epoch=EPOCH,kind=kind,stamp=7.24,payload=dict(robot=ROBOT,ack_sequence=9)))
            with self.subTest(kind=kind),self.assertRaises(ValueError):a.replay_adapter(bad,steps,EPOCH,context,cls)
        for kind in ('authority_future_extension','invalid_authority_extension'):
            motion=[dict(schema='mr3-motion-safety-v1',epoch=EPOCH,record_sequence=1,
                kind='configuration',payload=dict(motion_authority_profile=a.PROFILE)),
                dict(schema='mr3-motion-safety-v1',epoch=EPOCH,record_sequence=2,
                    kind=kind,payload={})]
            native={name:dict(commands={},actuations={},odometry={}) for name in a.ROBOTS}
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'unknown authority motion event'):
                a.replay_motion(motion,native,EPOCH,0)

    def test_actual_external_task_stop_frontier_required_without_inferred_protocol_trigger(self):
        rows,steps,context,cls=adapter_fixture(external=True)
        self.assertEqual(a.replay_adapter(rows,steps,EPOCH,context,cls)['deferred_terminal_dispatches'],1)
        for attack in ('missing','future','frame','release'):
            bad=copy.deepcopy(rows)
            callback=next(v for v in bad if v['kind']=='authority_task_stop_callback')
            if attack=='missing':bad.remove(callback)
            elif attack=='future':callback['payload']['message']['stamp']['sec']=7
            elif attack=='frame':callback['payload']['message']['frame_id']='odom'
            else:callback['payload']['started_at']=2.
            with self.subTest(attack=attack),self.assertRaises(ValueError):a.replay_adapter(bad,steps,EPOCH,context,cls)

    def test_original_goal_dispatcher_replayed_at_true_deferred_frontier(self):
        rows,steps,context,cls=adapter_fixture()
        result=a.replay_adapter(rows,steps,EPOCH,context,cls)
        self.assertEqual(result['deferred_terminal_dispatches'],1)
        self.assertTrue(result['original_six_phase_protocol_replayed'])

    def test_natural_and_quick_terminal_keep_original_immediate_order(self):
        for kwargs in (dict(natural=True),dict(quick=True)):
            rows,steps,context,cls=adapter_fixture(**kwargs)
            result=a.replay_adapter(rows,steps,EPOCH,context,cls)
            self.assertEqual(result['deferred_terminal_dispatches'],0)
            self.assertEqual(result['never_granted_terminals'],int(bool(kwargs.get('quick'))))

    def test_protocol_early_terminal_missing_ready_and_owner_tamper_rejected(self):
        for attack in ('early','ready','owner'):
            rows,steps,context,cls=adapter_fixture()
            if attack=='early':
                terminal=next(v for v in rows if v['kind']=='protocol' and v['payload']['type']=='protocol_terminal')
                terminal['payload']['stamp']=6.5
            elif attack=='ready':rows=[v for v in rows if not(v['kind']=='authority_ack_callback' and v['payload']['clock_ns']==a.clock(7.22))]
            else:next(v for v in rows if v['kind']=='authority_publication')['payload']['packet']['native_goal_uuid']='ff'*16
            with self.subTest(attack=attack),self.assertRaises(ValueError):a.replay_adapter(rows,steps,EPOCH,context,cls)


if __name__=='__main__':unittest.main()
