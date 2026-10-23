"""Artificial callback tests with real ROS types and real protocol/Reach state.

No ROS graph, DDS delivery, loaded native, World, raw inputs or physics credit.
"""
import copy
from collections import deque
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace as NS
import unittest

from action_msgs.msg import GoalInfo
from geometry_msgs.msg import Twist
from rclpy.task import Future
from std_msgs.msg import Header, String
from unique_identifier_msgs.msg import UUID

# Official ROS setup supplies the installed canonical package. No shadow path.
HERE=Path(__file__).resolve().parent
COMP=HERE.parent
ROOT=COMP.parents[3]
from multi_robot_exploration import mr3_adapter as adapter
from multi_robot_exploration import motion_safety as motion
from multi_robot_exploration import mr3_motion_authority as authority
from multi_robot_exploration.mr3_protocol import GoalDispatcher
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore
from multi_robot_exploration.mr3_safety_intent import payload_sha256
spec=importlib.util.spec_from_file_location('authority_actual_feed',HERE/'test_mr3_reach_runtime_independent.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
EPOCH=f.EPOCH
ROBOTS=('tb1','tb2','tb3')


class Publisher:
    def __init__(self):self.messages=[];self.failure=None
    def publish(self,message):
        if self.failure is not None:raise self.failure
        self.messages.append(copy.deepcopy(message))


class Handle:
    def __init__(self,number,clock):
        self.accepted=True;self.goal_id=UUID(uuid=[number]*16)
        self.result=Future();self.cancel=Future();self.clock=clock;self.cancel_calls=[]
    def get_result_async(self):return self.result
    def cancel_goal_async(self):self.cancel_calls.append(self.clock());return self.cancel


def bind(obj,cls,names):
    for name in names:setattr(obj,name,MethodType(getattr(cls,name),obj))


def graph(topic):
    if topic.endswith('/motion_authority_ack'):node,namespace='motion_safety','/'
    elif topic.endswith('/motion_authority'):node,namespace='mr3_adapter','/'
    elif '/mr3_drive/' in topic:node,namespace='turtlebot3_diff_drive','/'+topic.split('/')[1]
    else:node,namespace='velocity_smoother','/'+topic.split('/')[1]
    return [NS(node_name=node,node_namespace=namespace,topic_type='std_msgs/msg/String',endpoint_gid=bytes([7])*24)]


def clocked(now):
    obj=NS(clock_ns=now,rows=[])
    obj.now=lambda:obj.clock_ns/1e9
    obj.get_clock=lambda:NS(now=lambda:NS(nanoseconds=obj.clock_ns))
    obj.record=lambda kind,payload:obj.rows.append({'kind':kind,'clock_ns':obj.clock_ns,'payload':copy.deepcopy(payload)})
    obj.get_publishers_info_by_topic=graph
    return obj


def adapter_shell(now):
    a=clocked(now);a.epoch=EPOCH;a.motion_authority_profile=authority.PROFILE
    a.events=deque();a.dispatcher=GoalDispatcher(EPOCH,a.events.append)
    a.transport=IdealTransport(EPOCH);a.received=ReceivedStore(EPOCH)
    a.handles={};a.authority_native_identities={};a.authority_native_terminals={}
    a.authority_sequence=dict.fromkeys(ROBOTS,0)
    a.authority_packet=dict.fromkeys(ROBOTS);a.authority_grant=dict.fromkeys(ROBOTS)
    a.authority_ready=dict.fromkeys(ROBOTS);a.authority_ack_sequence=dict.fromkeys(ROBOTS,0)
    a.authority_last_ack=dict.fromkeys(ROBOTS);a.authority_ack_gids={}
    a.authority_pending_accept={};a.authority_buffered_terminal={}
    a.authority_publishers={name:Publisher() for name in ROBOTS}
    a.stop_requested=False;a.stop_acknowledged=False;a.started_at=now/1e9;a.pending_stop=None
    a.last_heartbeat=now/1e9;a.receipt_metadata={name:{} for name in ROBOTS}
    a.poll_task_terminal=lambda:None;a.publish_initial_inputs_ready=lambda now:None
    a.finish_observation=lambda:None;a.poll_snapshot=lambda:None;a.states_fresh=lambda now:True
    a.failure_pub=Publisher();a.stop_pub=Publisher()
    bind(a,adapter.MR3Adapter,('accepted','completed','canceled','receipt','publish_authority',
        'receive_authority_ack','authority_after_receipt','poll_authority_handoff',
        'release_authority_native_identity','cancel_native_goal','flush_protocol_events','maintain','receive_stop'))
    return a


def submitted(a,command=1):
    now=a.now()
    assert a.dispatcher.submit('tb1','GOAL',now,command,command,now+2,
        goal={'x':2.,'y':0.},command_epoch=EPOCH,created_at=now)=='sent'
    a.events.clear()  # This artificial native acceptance follows the already-issued goal.
    goal=a.dispatcher.states['tb1'].goal_id
    handle=Handle(command,lambda:a.clock_ns);future=Future();future.set_result(handle)
    return goal,handle,future


def deliver(a,now):
    a.clock_ns=now;a.last_heartbeat=now/1e9
    a.maintain()


def guard_shell(feed):
    g=clocked(feed.now);g.epoch=EPOCH;g.motion_authority_profile=authority.PROFILE
    g.motion_authorities=dict.fromkeys(ROBOTS);g.authority_ack_sequences=dict.fromkeys(ROBOTS,0)
    g.authority_ready_sent=dict.fromkeys(ROBOTS);g.authority_ack_publishers={n:Publisher() for n in ROBOTS}
    g.input_sequences={n:{'request':0,'odom':0,'tf':0} for n in ROBOTS}
    g.reach={'tb1':feed.r};g.reach_publisher_gids={};g.requests={}
    g.diagnostic_receipt_pub=None;g.control_phase=None;g.halted=None;g.failures=[]
    g.reach_failure=lambda name,error:g.failures.append((name,str(error)))
    g.try_reach_release=lambda:None
    bind(g,motion.MotionSafety,('authority_identity','bind_motion_authority','publish_authority_ack',
        'receive_motion_authority','receiving_permission','receive_reach_feed','receive_request',
        'twist','publisher_identity'))
    # twist is a staticmethod, not a bound Node method.
    g.twist=motion.MotionSafety.twist
    return g


def connect_initial(a,g,feed,goal):
    permission=g.receiving_permission('tb1',feed.r,None,feed.now)
    assert permission['effective_request']==[0.,0.]
    ack=g.authority_ack_publishers['tb1'].messages[-1]
    a.receive_authority_ack(ack,'tb1');a.poll_authority_handoff(a.now())
    packet=a.authority_publishers['tb1'].messages[-1]
    g.receive_motion_authority(packet,'tb1')
    assert g.motion_authorities['tb1'].state=='ACTIVE'
    assert a.authority_grant['tb1']['goal_id']==goal


class JointFeed:
    """Three real trackers fed declared synthetic sensor/storage/motor receipts."""
    def __init__(self):
        self.now=f.START;self.xy={'tb1':(0.,0.),'tb2':(3.,0.),'tb3':(0.,3.)}
        self.trackers={n:f.reach.ReachTracker(EPOCH,n) for n in ROBOTS}
        self.raw={};self.seq=dict.fromkeys(ROBOTS,0);self.cmd=dict.fromkeys(ROBOTS,0)
        self.act=dict.fromkeys(ROBOTS,40);self.next_act=dict.fromkeys(ROBOTS,f.START+f.STEP)
        self.stored={n:[] for n in ROBOTS};self.input_seq=1
        for name,t in self.trackers.items():
            self.raw[name]=f.odometry(self.now,robot=name,xy=self.xy[name]);self.publish(name)
            t.receive_raw(self.raw[name],1);t.receive_calibration(f.calibration(self.raw[name],1,robot=name))
            assert t.synchronize(self.now);t.release(self.now);self.publish(name)
        for _ in range(49):self.tick()
        assert all(t.role=='D' for t in self.trackers.values())
    def own(self,name):
        row=f.state(self.raw[name],self.trackers[name].current_intent,name=name)
        row['safety']['calibration']=copy.deepcopy(self.trackers[name].calibrations[self.now])
        return row
    def publish(self,name,output=(0.,0.)):
        self.seq[name]+=1;v=f.target(self.now,self.seq[name],output,robot=name)
        self.trackers[name].publish_target(v);self.cmd[name]+=1
        self.trackers[name].receive_storage(f.storage(v,self.cmd[name]));self.stored[name].append((v,self.cmd[name]))
    def stage(self):
        self.now+=f.STEP;self.input_seq+=1
        for name,t in self.trackers.items():
            self.raw[name]=f.odometry(self.now,robot=name,xy=self.xy[name])
            t.receive_raw(self.raw[name],self.input_seq)
            t.receive_calibration(f.calibration(self.raw[name],self.input_seq,robot=name))
            while self.next_act[name]<=self.now:
                v,cmd=max((x for x in self.stored[name] if x[0]['clock_ns']<=self.next_act[name]),key=lambda x:x[1])
                act=f.applied(v,self.next_act[name],self.act[name],cmd);act['robot']=name
                t.receive_applied(act);self.next_act[name]+=f.ACT;self.act[name]+=1
            assert t.synchronize(self.now)
    def tick(self):
        self.stage();states={n:self.own(n) for n in ROBOTS};outputs={}
        for n,t in self.trackers.items():
            outputs[n]=t.decide([0.,0.],states[n],{p:states[p] for p in ROBOTS if p!=n},self.now,t.current_intent)['output']
        for n in ROBOTS:self.publish(n,outputs[n])


class WrapperContracts(unittest.TestCase):
    def initial(self):
        feed=f.Feed().disk();a=adapter_shell(feed.now);g=guard_shell(feed)
        goal,handle,accepted=submitted(a);a.accepted(accepted,'tb1',goal)
        deliver(a,feed.now+200_000_000)
        # Artificial real tracker proof must match the current paused clock.
        for _ in range(10):feed.tick()
        g.clock_ns=feed.now
        connect_initial(a,g,feed,goal)
        return feed,a,g,goal,handle

    def test_quick_native_terminal_before_logical_accept_preserves_receipts_no_grant(self):
        for status in (4,6):
            a=adapter_shell(2_000_000_000);goal,h,accepted=submitted(a)
            a.accepted(accepted,'tb1',goal);a.clock_ns+=20_000_000
            h.result.set_result(NS(status=status))
            self.assertIn(goal,a.handles)
            deliver(a,2_200_000_000)
            self.assertEqual(a.dispatcher.states['tb1'].phase,'active')
            self.assertNotIn('tb1',a.authority_pending_accept)
            self.assertEqual(a.authority_sequence['tb1'],0)
            deliver(a,2_400_000_000)
            self.assertNotIn(goal,a.handles)
            self.assertEqual(a.dispatcher.states['tb1'].last_terminal,'SUCCEEDED' if status==4 else 'ABORTED')
            if status==6:self.assertEqual(a.dispatcher.states['tb1'].failure,'navigation_aborted')
            records=[r['payload'] for r in a.rows if r['kind']=='delivery' and r['payload']['stream']=='receipt']
            self.assertEqual([r['payload']['type'] for r in records],['accept','result'])
            self.assertEqual(records[1]['source_stamp'],2.02)
            self.assertEqual(records[1]['received_stamp'],2.4)
        # Already-completed real Future invokes completed during accepted();
        # preserve original receipt order instead of inventing a later source.
        a=adapter_shell(2_000_000_000);goal,h,accepted=submitted(a);h.result.set_result(NS(status=4))
        a.accepted(accepted,'tb1',goal);deliver(a,2_200_000_000);deliver(a,2_400_000_000)
        self.assertEqual(a.dispatcher.states['tb1'].last_terminal,'SUCCEEDED')
        self.assertEqual(a.authority_sequence['tb1'],0)
        records=[r['payload']['payload']['type'] for r in a.rows if r['kind']=='delivery']
        self.assertEqual(records,['result','accept'])

    def test_publication_error_still_subscribes_native_cancel_response(self):
        feed,a,g,goal,h=self.initial()
        start=a.clock_ns
        for tenth in range(1,52):
            now=(start+tenth*100_000_000)/1e9;a.dispatcher.renew('tb1',goal,EPOCH,now,now+2)
        a.clock_ns=start+5_100_000_000
        self.assertEqual(a.dispatcher.submit('tb1','WAIT',a.now(),7,7,a.now()+2,
            command_epoch=EPOCH,created_at=a.now()),'waiting')
        a.authority_publishers['tb1'].failure=OSError('ARTIFICIAL_publish_failed')
        with self.assertRaises(OSError):a.cancel_native_goal('tb1',goal)
        self.assertEqual(h.cancel_calls,[a.clock_ns])
        # Captured genuine handle also preserves a late response after cleanup.
        a.handles.pop(goal)
        h.cancel.set_result(NS(goals_canceling=[GoalInfo(goal_id=h.goal_id)]))
        receipts=list(a.transport.deliver(a.received,(a.clock_ns+200_000_000)/1e9))
        cancels=[v for v in receipts if v.payload.get('type')=='cancel']
        self.assertEqual(len(cancels),1);self.assertIs(cancels[0].payload['value'],True)
        self.assertEqual(cancels[0].source_stamp,a.clock_ns/1e9)

    def test_cancel_terminal_buffer_uses_real_ready_and_later_dispatch_clock(self):
        feed,a,g,goal,h=self.initial();anchor=copy.deepcopy(feed.r.anchor)
        start=a.clock_ns
        for tenth in range(1,52):
            now=(start+tenth*100_000_000)/1e9;a.dispatcher.renew('tb1',goal,EPOCH,now,now+2)
        a.clock_ns=start+5_100_000_000
        a.dispatcher.submit('tb1','WAIT',a.now(),7,7,a.now()+2,command_epoch=EPOCH,created_at=a.now())
        a.events.clear();a.cancel_native_goal('tb1',goal)
        h.cancel.set_result(NS(goals_canceling=[GoalInfo(goal_id=h.goal_id)]));h.result.set_result(NS(status=5))
        cancel_clock=a.clock_ns;g.clock_ns=cancel_clock
        g.receive_motion_authority(a.authority_publishers['tb1'].messages[-1],'tb1')
        deliver(a,cancel_clock+200_000_000)
        deliver(a,cancel_clock+400_000_000)
        saved=copy.deepcopy(a.authority_buffered_terminal['tb1'])
        self.assertEqual(a.dispatcher.states['tb1'].phase,'canceling')
        self.assertEqual(saved['source_stamp'],cancel_clock/1e9)
        self.assertEqual(saved['received_stamp'],(cancel_clock+400_000_000)/1e9)
        # Advance the real Reach fixture with normal zero decisions. Rebase no
        # tracker/source time; feed every intervening genuine artificial phase.
        while feed.now<cancel_clock+1_200_000_000:feed.tick()
        g.clock_ns=feed.now;g.receiving_permission('tb1',feed.r,None,feed.now)
        ready=g.authority_ack_publishers['tb1'].messages[-1]
        self.assertEqual(json.loads(ready.data)['ack']['stage'],'stop_obligation_ready')
        a.clock_ns=feed.now;a.receive_authority_ack(ready,'tb1');a.dispatcher.tick(a.now())
        a.poll_authority_handoff(a.now())
        self.assertEqual(a.dispatcher.states['tb1'].phase,'idle')
        row=[v['payload'] for v in a.rows if v['kind']=='authority_terminal_dispatched'][-1]
        self.assertEqual(row['original_delivery'],saved)
        self.assertEqual(row['dispatch_clock_ns'],feed.now)
        self.assertGreater(row['dispatch_clock_ns'],int(saved['received_stamp']*1e9))
        self.assertEqual(feed.r.anchor,anchor);self.assertFalse(feed.r.stopped)

    def test_natural_terminal_immediate_and_B_heartbeat_cannot_renew_A(self):
        feed,a,g,goal,h=self.initial();h.result.set_result(NS(status=4))
        deliver(a,a.clock_ns+200_000_000)
        self.assertEqual(a.dispatcher.states['tb1'].phase,'idle')
        self.assertEqual(a.authority_packet['tb1']['operation'],'revoke')
        sequence=a.authority_sequence['tb1']
        next_goal,next_handle,accept=submitted(a,2);a.accepted(accept,'tb1',next_goal)
        deliver(a,a.clock_ns+200_000_000)
        self.assertEqual(a.dispatcher.states['tb1'].goal_id,next_goal)
        self.assertEqual(a.dispatcher.states['tb1'].phase,'active')
        self.assertEqual(a.authority_sequence['tb1'],sequence)
        self.assertEqual(a.authority_pending_accept['tb1'],next_goal)
        now=a.now();a.transport.send('heartbeat','tb1',{'goal_id':next_goal,'expires_at':now+2},source_stamp=now,now=now)
        deliver(a,a.clock_ns+200_000_000)
        self.assertEqual(a.authority_sequence['tb1'],sequence)
        self.assertFalse(a.stop_requested);self.assertIsNone(a.dispatcher.states['tb1'].failure)
        self.assertEqual(a.dispatcher.states['tb1'].commitment_until,
            a.dispatcher.states['tb1'].accepted_at+5)
        # An external task stop is an independent real callback frontier, not
        # something a reader may infer from its resulting protocol.cancel.
        def message(clock,frame='map'):
            value=Header();value.stamp.sec,value.stamp.nanosec=divmod(clock,10**9);value.frame_id=frame
            return value
        a.receive_stop(message(a.clock_ns+200_000_000))
        a.receive_stop(message(a.clock_ns,frame='wrong'))
        a.receive_stop(message(int(a.started_at*1e9)-1))
        self.assertFalse(any(v['kind']=='authority_task_stop_callback' for v in a.rows))
        self.assertFalse(a.dispatcher.stopped)
        actual=message(a.clock_ns-20_000_000);a.receive_stop(actual)
        events=[v['payload'] for v in a.rows if v['kind']=='authority_task_stop_callback']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0],{'message':{'stamp':{'sec':actual.stamp.sec,'nanosec':actual.stamp.nanosec},
            'frame_id':'map'},'clock_ns':a.clock_ns,'started_at':a.started_at})
        self.assertTrue(a.dispatcher.stopped)
        self.assertEqual(a.dispatcher.states['tb1'].phase,'canceling')
        # Failure to write audit bytes cannot skip the existing stop effect.
        other=adapter_shell(10_000_000_000);owned,handle,accept=submitted(other)
        other.accepted(accept,'tb1',owned);deliver(other,10_200_000_000)
        def fail_record(kind,payload):raise OSError('ARTIFICIAL_task_stop_audit_failure')
        other.record=fail_record
        with self.assertRaises(OSError):other.receive_stop(message(other.clock_ns-20_000_000))
        self.assertTrue(other.dispatcher.stopped)
        self.assertEqual(other.dispatcher.states['tb1'].phase,'canceling')

    def test_each_applied_callback_latches_nonzero_before_coalesced_zero(self):
        feed,a,g,goal,h=self.initial();gate=g.motion_authorities['tb1']
        source=f.Feed().disk();destination=copy.deepcopy(source.r);g.reach['tb1']=destination
        gate.after_real_motion=False;last_synchronized=copy.deepcopy(destination.last_applied)
        def callback_next(output):
            before=source.r.last_applied['actuation_sequence']
            while source.r.last_applied['actuation_sequence']==before or source.r.last_applied['target']['linear_x']!=output[0]:
                source.tick(output)
            # Storage and publication receipts remain genuine synthetic source
            # history. Install that history prior to the real APPLIED callback.
            destination.published=copy.deepcopy(source.r.published)
            destination.storage=copy.deepcopy(source.r.storage)
            g.clock_ns=source.now
            for sequence,value in source.r.applied_seen.items():
                if sequence not in destination.applied_seen:
                    g.receive_reach_feed(String(data=json.dumps(value)), 'tb1','applied')
            return source.r.last_applied
        positive=callback_next([.1,0.]);self.assertGreater(positive['target']['linear_x'],0)
        self.assertTrue(gate.after_real_motion)
        zero=callback_next([0.,0.]);self.assertEqual(zero['target']['linear_x'],0)
        self.assertTrue(gate.after_real_motion);self.assertEqual(g.failures,[])
        self.assertEqual(destination.last_applied,last_synchronized)
        self.assertEqual(destination.applied_seen[max(destination.applied_seen)]['target']['linear_x'],0)

    def test_real_three_tracker_emit_keeps_all_raw_and_normal_ready_zero(self):
        joint=JointFeed();joint.stage();feed=NS(now=joint.now,r=joint.trackers['tb1'])
        g=guard_shell(feed);g.reach=joint.trackers;g.clock_ns=joint.now
        g.local_observers_ready=lambda:True;g.observers_started=True
        states={n:joint.own(n) for n in ROBOTS};table=payload_sha256({n:states[n]['safety'] for n in ROBOTS})
        refs={n:{'intent_sequence':states[n]['safety']['intent']['intent_sequence'],
                 'payload_sha256':payload_sha256(states[n]['safety']['intent'])} for n in ROBOTS}
        g.received={'robots':list(states.values()),'safety_contract':f.reach.CONTRACT,
            'safety_table_sha256':table,'intent_refs':refs}
        g.control_safety_context={'safety_table_sha256':table,'intent_refs':refs}
        g.control_inputs_ready=lambda clock:all(t.synchronize(clock) for t in joint.trackers.values())
        g.local_state=lambda name:joint.own(name);g.issued_motion=set();g.started=True;g.stop_time=None
        g.decision_sequences=copy.deepcopy(joint.seq);g.pending_outputs={n:deque() for n in ROBOTS}
        g.ready_pub=Publisher();g.outputs={n:Publisher() for n in ROBOTS};g.drive_targets={n:Publisher() for n in ROBOTS}
        g.publish_reach_intent=lambda name,intent:None;g.drive_audit=None;g.pending_status={}
        g.publish_completed_status=lambda clock:None
        bind(g,motion.MotionSafety,('_emit_reach_motion',))
        for name in ROBOTS:
            raw=Twist();raw.linear.x=.2;raw.angular.z=.3;g.receive_request(raw,name)
        original=copy.deepcopy(g.requests);anchors={n:copy.deepcopy(t.anchor) for n,t in g.reach.items()}
        g._emit_reach_motion()
        rows=[v['payload'] for v in g.rows if v['kind']=='reach_decision']
        self.assertEqual(len(rows),3)
        for row in rows:
            self.assertEqual(row['request'],original[row['robot']])
            self.assertEqual(row['effective_request'],[0.,0.]);self.assertEqual(row['decision']['output'],[0.,0.])
            self.assertIsNone(row['motion_authority']['raw_goal_generation'])
        self.assertTrue(g.ready_pub.messages[-1].data)
        self.assertEqual({n:t.anchor for n,t in g.reach.items()},anchors)
        self.assertTrue(all(not t.stopped for t in g.reach.values()));self.assertEqual(g.failures,[])

    def test_typed_ack_changed_duplicate_and_foreign_identity_fail_closed(self):
        feed=f.Feed().disk();a=adapter_shell(feed.now);g=guard_shell(feed)
        g.receiving_permission('tb1',feed.r,None,feed.now);message=g.authority_ack_publishers['tb1'].messages[-1]
        a.receive_authority_ack(message,'tb1');self.assertIsNotNone(a.authority_ready['tb1'])
        a.receive_authority_ack(message,'tb1');self.assertFalse(a.stop_requested)
        changed=json.loads(message.data);changed['ack']['witness']['anchor']['source_clock_ns']+=1
        a.receive_authority_ack(String(data=json.dumps(changed)),'tb1');self.assertTrue(a.stop_requested)
        for mutate in (lambda x:x.update(epoch='OTHER'),lambda x:x.update(ack_sequence=True),
                       lambda x:x.update(authority_packet_sha256='0'*64)):
            a=adapter_shell(feed.now);value=json.loads(message.data);mutate(value)
            a.receive_authority_ack(String(data=json.dumps(value)),'tb1')
            self.assertIsNone(a.authority_ready['tb1'])
        g.get_publishers_info_by_topic=lambda topic:[]
        g.receive_motion_authority(String(data='{}'),'tb1');self.assertTrue(g.failures)

    def test_received_cache_floor_and_unknown_generation_remain_distinct(self):
        feed,a,g,goal,h=self.initial();gate=g.motion_authorities['tb1']
        raw=Twist();raw.linear.x=.15;g.receive_request(raw,'tb1')
        result=g.receiving_permission('tb1',feed.r,g.requests['tb1'],g.clock_ns)
        self.assertEqual(result['effective_request'],[.15,0.]);self.assertIsNone(result['raw_goal_generation'])
        # New callback can be old-generated; receipt time cannot distinguish it.
        g.receive_request(raw,'tb1');again=g.receiving_permission('tb1',feed.r,g.requests['tb1'],g.clock_ns)
        self.assertEqual(again['raw_goal_association'],'UNKNOWN_UNSTAMPED_TWIST')
        self.assertEqual(again['permission'],'normal_reach')
        self.assertEqual(g.requests['tb1']['received_stamp'],g.clock_ns/1e9)
        revoke=copy.deepcopy(a.authority_packet['tb1']);revoke.update(operation='revoke',authority_sequence=2,
            source_clock_ns=g.clock_ns,lease_until_ns=g.clock_ns)
        g.receive_motion_authority(String(data=authority.canonical(revoke)),'tb1')
        for _ in range(59):
            g.receive_request(raw,'tb1');result=g.receiving_permission('tb1',feed.r,g.requests['tb1'],g.clock_ns)
            self.assertEqual(result['effective_request'],[0.,0.])
        self.assertFalse(feed.r.stopped)


if __name__=='__main__':unittest.main(verbosity=2)
