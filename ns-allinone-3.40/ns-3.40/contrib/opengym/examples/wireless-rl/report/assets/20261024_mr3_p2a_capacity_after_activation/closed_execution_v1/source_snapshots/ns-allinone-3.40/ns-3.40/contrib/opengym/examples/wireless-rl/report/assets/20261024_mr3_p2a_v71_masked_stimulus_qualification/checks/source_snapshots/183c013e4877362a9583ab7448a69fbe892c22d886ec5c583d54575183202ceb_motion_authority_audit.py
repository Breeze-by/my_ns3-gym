"""Independent receiving-permission and deferred-callback journal replay.

No production authority implementation is imported. Original native/Reach
mathematics remain separate mandatory conjunctions; this module reuses their
independent scalar/raw/calibration predicates rather than the producer tracker.
"""
from collections import deque
from bisect import bisect_left, bisect_right, insort
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import importlib.util
import sys
import types

from mr3_learning import audit_reach_runtime as rt
from mr3_learning.motion_authority_profile import MOTION_AUTHORITY_PROFILE as PROFILE

ROBOTS=('tb1','tb2','tb3')
PACKET='mr3-motion-authority-v1'
ACK='mr3-motion-authority-ack-v1'
WIRE='mr3-motion-authority-ack-wire-v1'
LEASE=2_000_000_000
PACKET_KEYS={'schema','epoch','robot','operation','authority_sequence','owner_grant_sequence',
             'goal_id','native_goal_uuid','owner_command_id','owner_accept_received_clock_ns',
             'source_clock_ns','lease_until_ns'}
WIRE_KEYS={'schema','profile','epoch','robot','ack_sequence','clock_ns','authority_packet_sha256','ack'}


def require(value,reason):
    if not value:raise ValueError(reason)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def equal(a,b,reason):
    require(canonical(a)==canonical(b),reason)


def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value,minimum=0):
    require(type(value) is int and value>=minimum,'noncanonical integer')
    return value


def clock(value):
    return rt.sec_ns(value)


def parse_wire(raw,value):
    require(type(raw) is str,'raw JSON missing')
    equal(rt.decode_text(raw),value,'wire bytes changed parsed value')
    return hashlib.sha256(raw.encode()).hexdigest()


def graph(value,robot,ack=False):
    topic=f'/{robot}/mr3/motion_authority'+('_ack' if ack else '')
    require(type(value) is dict and value.get('valid') is True
            and value.get('scope')=='graph_at_callback' and value.get('topic')==topic
            and value.get('packet_publisher_gid_available') is False,
            'authority graph scope/owner differs; no packet authentication credit')
    endpoints=value.get('endpoints')
    require(type(endpoints) is list and len(endpoints)==1,'authority endpoint not unique')
    ep=endpoints[0]
    # The producer graph helper uses the actual Humble node_name shape.
    require(ep.get('node_name')==('motion_safety' if ack else 'mr3_adapter')
            and ep.get('node_namespace')=='/' and ep.get('topic_type')=='std_msgs/msg/String'
            and type(ep.get('endpoint_gid')) is str
            and re.fullmatch(r'(?:[0-9a-f]{2}){16,}',ep['endpoint_gid'])
            and int(ep['endpoint_gid'],16)!=0,'authority endpoint identity differs')
    return ep['endpoint_gid']


def owner_identity(packet):
    return packet['goal_id'],packet['native_goal_uuid']


def owner_token(packet):
    return tuple(packet[k] for k in ('goal_id','native_goal_uuid','owner_command_id',
                                     'owner_accept_received_clock_ns','owner_grant_sequence'))


def packet_shape(packet,epoch,robot):
    require(type(packet) is dict and set(packet)==PACKET_KEYS and packet['schema']==PACKET
            and packet['epoch']==epoch and packet['robot']==robot,'authority packet fields/context')
    for key in ('authority_sequence','owner_grant_sequence','owner_command_id'):integer(packet[key],1)
    for key in ('source_clock_ns','lease_until_ns','owner_accept_received_clock_ns'):integer(packet[key])
    require(packet['operation'] in ('grant','renew','revoke')
            and packet['owner_accept_received_clock_ns']<=packet['source_clock_ns']
            and packet['owner_grant_sequence']<=packet['authority_sequence'],'authority operation/clock/order')
    require(type(packet['goal_id']) is str and packet['goal_id']==f"{epoch}:{robot}:{packet['owner_command_id']}"
            and type(packet['native_goal_uuid']) is str and re.fullmatch('[0-9a-f]{32}',packet['native_goal_uuid']),
            'authority logical/native owner identity')
    if packet['operation']=='revoke':
        require(packet['lease_until_ns']==packet['source_clock_ns'],'revoke clock was refreshed')
    else:
        require(packet['source_clock_ns']<packet['lease_until_ns']<=packet['source_clock_ns']+LEASE,
                'authority changed the original two-second lease')


class StopEvidence:
    """Exact source references and original normal-zero qualification facts."""
    def __init__(self,epoch,robot,release_ns,native):
        self.epoch,self.robot,self.release=epoch,robot,integer(release_ns)
        self.native=native
        self.raw,self.calibration,self.storage,self.applied={}, {}, {}, {}
        self.intents=[]
        self.raw_times=[];self.intent_sequences=[];self.publication_zero_prefix=[]
        self.latest_storage_cmd=0;self.storage_zero=None;self.latest_applied=None
        self.sticky_motion=False

    def ingest(self,row,index):
        kind,p=row['kind'],row['payload']
        if p.get('robot')!=self.robot:return
        if kind=='own_odom':
            raw=p['message'];source=rt.source(raw)
            original=self.native['odometry'].get(source)
            require(original is not None,'authority rest source has no native odometry')
            equal(raw,original['odometry'],'authority raw differs from actual native publication')
            if source not in self.raw:
                if not self.raw_times or source>self.raw_times[-1]:self.raw_times.append(source)
                else:insort(self.raw_times,source)
            self.raw[source]=(index,copy.deepcopy(raw))
        elif kind=='reach_driver_ingress':
            message=p['message']
            if message.get('epoch')!=self.epoch:return
            require(message.get('robot')==self.robot,'authority ingress robot differs')
            parse_wire(p['raw_json'],message)
            if p['kind']=='calibration':
                source=message['source_clock_ns']
                require(source in self.native['odometry'],'authority calibration no native source')
                rt.calibration_check(message,self.native['odometry'][source]['odometry'],self.epoch,self.robot)
                self.calibration[source]=(index,copy.deepcopy(message))
            elif p['kind']=='storage':
                command=self.native['commands'].get(message['cmd_seq'])
                require(command is not None and message['decision_sequence']==command['target_decision_sequence']
                        and message['clock_ns']==command['sim_time_ns']
                        and message['source_clock_ns']==command['target_clock_ns'],'authority storage native identity differs')
                equal([message['linear_x'],message['angular_z']],
                      [command['desired_v'],command['desired_w']],'authority storage body target differs')
                self.storage[message['cmd_seq']]=(index,copy.deepcopy(message))
                if message['cmd_seq']>self.latest_storage_cmd:
                    if message['linear_x']!=0 or message['angular_z']!=0:self.storage_zero=None
                    elif self.storage_zero is None:self.storage_zero=max(self.release,message['clock_ns'])
                    self.latest_storage_cmd=message['cmd_seq']
                else:
                    # Duplicates/stale deliveries are uncommon, but cannot
                    # change the original cmd-order qualification semantics.
                    rows=[v for _,v in self.storage.values()]
                    last=max((v['cmd_seq'] for v in rows if v['linear_x']!=0 or v['angular_z']!=0),default=0)
                    zeros=[v['clock_ns'] for v in rows if v['cmd_seq']>last and v['linear_x']==v['angular_z']==0]
                    self.storage_zero=max(self.release,min(zeros)) if zeros else None
            elif p['kind']=='applied':
                pairs=self.native['actuations'].get(message['actuation_sequence'])
                require(pairs and message['source_clock_ns']==pairs[0]['sim_time_ns']
                        and message['cmd_seq']==pairs[0]['cmd_seq'] and message['dt_ns']==34_000_000,
                        'authority APPLIED actual update identity differs')
                expected=[{k:q[k] for k in ('pair_index','current_rim_mps','desired_rim_mps',
                    'applied_rim_mps','alpha','max_acceleration_mps2')} for q in pairs]
                equal(message['pairs'],expected,'authority APPLIED changed actual pair writes')
                equal([message['target']['linear_x'],message['target']['angular_z']],
                      [pairs[0]['desired_v'],pairs[0]['desired_w']],'authority APPLIED target differs')
                old=self.applied.get(message['actuation_sequence'])
                require(old is None or canonical(old[1])==canonical(message),'authority APPLIED identity rewritten')
                self.applied[message['actuation_sequence']]=(index,copy.deepcopy(message))
                if self.latest_applied is None or message['actuation_sequence']>self.latest_applied['actuation_sequence']:
                    self.latest_applied=copy.deepcopy(message)
                # Every validated callback counts, including a nonzero that is
                # followed by zero before the next synchronize/decision.
                self.sticky_motion |= message['target']['linear_x']!=0 or message['target']['angular_z']!=0
        elif kind=='reach_intent_publish':
            intent=p['intent'];rt.intent_check(intent,self.epoch,self.robot)
            equal(p['payload_sha256'],digest(intent),'authority intent digest differs')
            require(not self.intent_sequences or intent['intent_sequence']>self.intent_sequences[-1],
                    'authority intent sequence regressed')
            zero=self.publication_zero_prefix[-1] if self.publication_zero_prefix else None
            if intent['target']['linear_x']!=0 or intent['target']['angular_z']!=0:zero=None
            elif zero is None:zero=max(self.release,intent['target']['clock_ns'])
            self.intent_sequences.append(intent['intent_sequence']);self.publication_zero_prefix.append(zero)
            self.intents.append((index,copy.deepcopy(intent)))

    def facts(self,now,before_index,not_before,exclude_current_intent=None):
        integer(now);integer(not_before)
        position=(len(self.intents)-1 if exclude_current_intent is None else
                  bisect_left(self.intent_sequences,exclude_current_intent)-1)
        while position>=0 and (self.intents[position][0]>=before_index
                              or self.intents[position][1]['source_clock_ns']>now):position-=1
        require(position>=0,'normal stop has no earlier owner intent')
        current=self.intents[position][1]
        require(current['role'] in ('HOLD','D','N'),'normal stop cannot claim permanent STOP/X')
        zero_pub=self.publication_zero_prefix[position];zero_store=self.storage_zero
        require(zero_pub is not None,'normal stop omitted zero publication')
        require(zero_store is not None,'normal stop omitted actual zero storage')
        require(now-zero_pub>=940_000_000 and now-zero_store>=780_000_000,'normal stop debt was shortened/restarted')
        actual=self.latest_applied
        if actual is not None and (actual['source_clock_ns']>now or self.applied[actual['actuation_sequence']][0]>=before_index):
            actual=max((v for i,v in self.applied.values() if i<before_index and v['source_clock_ns']<=now),
                       key=lambda v:v['actuation_sequence'],default=None)
        require(actual is not None,'normal stop omitted actual application');t=actual['target']
        require(t['linear_x']==t['angular_z']==0 and t['clock_ns']>=not_before,'normal stop cited moving/old target')
        stored=self.storage.get(actual['cmd_seq'])
        require(stored is not None and stored[0]<before_index
                and stored[1]['decision_sequence']==t['decision_sequence']
                and stored[1]['source_clock_ns']==t['clock_ns'],'normal stop omitted exact storage/APPLIED join')
        raws=[]
        for raw_position in range(bisect_right(self.raw_times,now)-1,-1,-1):
            source=self.raw_times[raw_position]
            if self.raw[source][0]>=before_index or source not in self.calibration or self.calibration[source][0]>=before_index:continue
            raws.append((source,self.raw[source][1]))
            if len(raws)==3:break
        require(raws,'normal stop raw/calibration empty')
        raws.sort();latest=raws[-1][0]
        require(actual['source_clock_ns']<latest and 0<=now-latest<20_000_000,'normal stop has no fresh strictly-later raw')
        require(0<=now-actual['source_clock_ns']<34_000_000,'normal stop used stale actual application')
        rest=[]
        for s,raw in raws:
            calibrated=self.calibration[s][1]
            if s>=zero_pub+940_000_000 and rt.residual_squared_upper(raw,calibrated,())<=Fraction(1,100)**2:
                rest=(rest+[(s,raw)])[-3:]
            else:rest=[]
        require(len(rest)==3 and all(not_before<=s<=now and now-s<=100_000_000 for s,_ in rest),
                'normal stop lacks three original fresh calibrated rest samples')
        anchor=current['anchor']
        require(anchor is not None and anchor['source_clock_ns'] in self.raw
                and self.raw[anchor['source_clock_ns']][0]<before_index,'normal stop anchor lacks genuine source')
        equal(anchor['odometry'],self.raw[anchor['source_clock_ns']][1],'normal stop reanchored to a substituted payload')
        if current['role'] in ('HOLD','D'):
            for _,raw in rest:
                require(sum((a-b)**2 for a,b in zip(rt.xy(raw),rt.xy(anchor['odometry'])))<=rt.R**2,
                        'normal stop fixed disk radius changed')
        else:
            # Original replay_robot independently proves the unchanged global
            # H/D/terminal disk for the complete actual stream. Here verify the
            # N causal lineage; do not invent a second relaxed stopping model.
            lineage=current['lineage'];receipt=self.applied.get(lineage['actuation_sequence'])
            require(receipt is not None and receipt[0]<before_index
                    and receipt[1]['source_clock_ns']==lineage['actuation_source_clock_ns']
                    and receipt[1]['cmd_seq']==lineage['cmd_seq']
                    and lineage['actuation_source_clock_ns']<lineage['causal_source_clock_ns']<=now
                    and lineage['causal_source_clock_ns'] in self.raw,
                    'N stop lacks genuine already-validated causal lineage')
        rims_zero=all(all(v==0 for v in pair['applied_rim_mps']) for pair in actual['pairs'])
        require(not self.sticky_motion or rims_zero,'body zero hid actual servo/slew motor target after real motion')
        return dict(clock_ns=now,not_before_ns=not_before,zero_publication_since_ns=zero_pub,
            zero_storage_since_ns=zero_store,storage=stored[1],applied=actual,actual_rims_zero=rims_zero,
            after_real_nonzero_application=self.sticky_motion,
            rest=[dict(source_clock_ns=s,odometry=raw,calibration=self.calibration[s][1]) for s,raw in rest],
            reach_role=current['role'],anchor=anchor)

    def witness(self,value,now,index,not_before):
        expected=dict(schema='mr3-normal-zero-authority-witness-v1',epoch=self.epoch,robot=self.robot,
                      **self.facts(now,index,not_before),permanent_stop=False,continuous_physics_proved=False)
        equal(value,expected,'normal stop witness differs from independent source reconstruction')
        return expected


class ReceivingReplay:
    """Independent transition table, receiving permission, and prefix receipts.

    Unsuccessful/malformed authority events are retained failures for a PASS
    activity. Genuine stale/duplicate callbacks are allowed without refresh.
    No command generation is inferred from callback receipt order.
    """
    def __init__(self,epoch,robot,gid,evidence):
        self.epoch,self.robot,self.gid,self.evidence=epoch,robot,gid,evidence
        self.seq=0;self.packet=None;self.owner=None;self.state='NONE'
        self.retired=set();self.floor=0;self.received=None;self.stop=None
        self.ready=None;self.last_clock=None;self.raw=None;self.raw_seq=0
        self.ack_seq=0;self.expected_acks=deque();self.sent_ready=set()
        self.decision_permissions={};self.callbacks=[];self.ack_publications=[]

    def raw_callback(self,request):
        require(type(request) is dict,'authority raw callback missing original object')
        require(integer(request['sequence'],1)==self.raw_seq+1,'authority raw callback sequence gap')
        self.raw_seq=request['sequence'];self.raw=copy.deepcopy(request)

    def observe(self,now,index,exclude_current_intent=None):
        if self.state=='ACTIVE':return None
        start=self.evidence.release if self.stop is None else self.stop
        try:facts=self.evidence.facts(now,index,start,exclude_current_intent)
        except ValueError:
            self.ready=None;return None
        self.ready=dict(schema='mr3-normal-zero-authority-witness-v1',epoch=self.epoch,robot=self.robot,
                        **facts,permanent_stop=False,continuous_physics_proved=False)
        return dict(schema=ACK,epoch=self.epoch,robot=self.robot,stage='stop_obligation_ready',
                    authority_sequence=self.seq,owner=copy.deepcopy(self.owner),
                    received_clock_ns=self.received,witness=copy.deepcopy(self.ready))

    def receive(self,p,index):
        packet=p['message'];now=integer(p['clock_ns'])
        require(graph(p['publisher_identity'],self.robot)==self.gid,'authority publisher identity changed')
        require(parse_wire(p['raw_json'],packet)==p['packet_sha256'],'authority original packet SHA differs')
        packet_shape(packet,self.epoch,self.robot)
        require(packet['source_clock_ns']<=now,'authority callback precedes its source clock')
        seq=packet['authority_sequence'];op=packet['operation']
        result=None
        if seq<self.seq:result=dict(accepted=False,reason='stale_authority',state=self.state)
        elif seq==self.seq:
            equal(packet,self.packet,'conflicting same-sequence authority packet')
            result=dict(accepted=True,reason='duplicate',state=self.state)
        elif owner_identity(packet) in self.retired and (op=='grant' or self.owner is None
                or owner_identity(packet)!=owner_identity(self.owner)):
            result=dict(accepted=False,reason='retired_owner',state=self.state)
        else:
            token=lambda v:(v['goal_id'],v['native_goal_uuid'],v['owner_grant_sequence'])
            if op in ('grant','renew'):
                require(now<packet['lease_until_ns'],'authority accepted an already-expired lease')
            if op=='revoke':
                require(self.owner is None or token(packet)==token(self.owner),'revoke changed actual owner')
                self.retired.add(owner_identity(packet));self.state='REVOKED';self.stop=now;self.ready=None
            elif op=='renew':
                require(self.state=='ACTIVE' and self.owner is not None and token(packet)==token(self.owner)
                        and packet['lease_until_ns']>self.owner['lease_until_ns'],
                        'renew lacks active matching owner or extends no lease')
            else:
                require(packet['owner_grant_sequence']==seq and self.state!='ACTIVE'
                        and owner_identity(packet) not in self.retired,'overlap/retired/mismatched grant')
                require(self.ready is not None and 0<=now-self.ready['clock_ns']<=100_000_000,
                        'grant without actual fresh local stop evidence')
                self.floor=self.raw_seq;self.state='ACTIVE';self.ready=None
            self.seq=seq;self.packet=copy.deepcopy(packet);self.owner=copy.deepcopy(packet);self.received=now
            result=dict(schema=ACK,epoch=self.epoch,robot=self.robot,authority_sequence=seq,
                stage='authority_received',accepted=True,state=self.state,received_clock_ns=now,
                source_clock_ns=packet['source_clock_ns'],callback_floor=self.floor,
                scope='actual authority callback only, not target storage, motor or rest')
            self.expected_acks.append((now,copy.deepcopy(result)))
        equal(p['result'],result,'authority callback result differs from independent transition table')
        self.callbacks.append((index,copy.deepcopy(p)))
        return result

    def permission(self,raw,now):
        integer(now)
        require(self.last_clock is None or now>=self.last_clock,'authority decision clock regression')
        self.last_clock=now
        if self.state=='ACTIVE' and now>=self.owner['lease_until_ns']:
            self.state='REVOKED';self.retired.add(owner_identity(self.owner));self.stop=now;self.ready=None
        permit=(self.state=='ACTIVE' and type(raw) is dict
                and type(raw.get('sequence')) is int and raw['sequence']>self.floor
                and all(type(raw.get(k)) in (int,float) and math.isfinite(raw[k]) for k in ('v','w')))
        return dict(effective_request=[raw['v'],raw['w']] if permit else [0.,0.],
            permission='normal_reach' if permit else 'zero_only',authority_sequence=self.seq,
            owner=copy.deepcopy(self.owner),state=self.state,fault=None,callback_floor=self.floor,
            raw_input_sequence=raw.get('sequence') if type(raw) is dict else None,
            raw_goal_generation=None,raw_goal_association='UNKNOWN_UNSTAMPED_TWIST',
            claim='receiving permission only; callback floor is not generation time')

    def decision(self,p,index):
        now=integer(p['clock_ns'])
        require(p.get('motion_authority_profile')==PROFILE,'decision authority profile missing/mixed')
        equal(p['request'],self.raw,'decision lost or rewrote latest original raw callback')
        self.observe(now,index,p['intent']['intent_sequence'])
        request=self.raw
        allowed=(p.get('started') is True and p.get('ready') is True and p.get('phase_kind')!='stop'
                 and request is not None and request.get('supported') is True
                 and request.get('publisher_identity',{}).get('valid') is True
                 and 0<=now-rt.state_ns(request['received_stamp'])<=200_000_000)
        expected=self.permission(request if allowed else None,now)
        equal(p['motion_authority'],expected,'claimed permission differs from actual receiving state')
        equal(p['effective_request'],expected['effective_request'],'effective request bypasses receiving authority')
        self.decision_permissions[integer(p['decision_sequence'],1)]=copy.deepcopy(expected)
        return expected

    def ack_publication(self,p,index):
        wire=p['message'];require(type(wire) is dict and set(wire)==WIRE_KEYS,'ACK wire shape')
        require(wire['schema']==WIRE and wire['profile']==PROFILE and wire['epoch']==self.epoch
                and wire['robot']==self.robot and integer(wire['ack_sequence'],1)==self.ack_seq+1,
                'ACK publication identity/profile/sequence differs')
        require(p['scope']=='publication_call_returned; not delivery','ACK publication misrepresented as delivery')
        parse_wire(p['raw_json'],wire)
        equal(wire['authority_packet_sha256'],None if self.packet is None else digest(self.packet),'ACK packet hash differs')
        now=integer(wire['clock_ns']);ack=wire['ack']
        if ack.get('stage')=='authority_received':
            require(self.expected_acks,'received ACK has no actual preceding authority callback')
            wanted_now,wanted=self.expected_acks.popleft()
            require(now==wanted_now,'received ACK clock changed')
            equal(ack,wanted,'received ACK differs from actual callback transition')
        else:
            require(self.seq not in self.sent_ready,'stop-ready republished for same authority sequence')
            wanted=self.observe(now,index)
            require(wanted is not None,'stopReady lacks actual original debts/storage/APPLIED/rest')
            equal(ack,wanted,'stopReady differs from actual source prefix')
            self.sent_ready.add(self.seq)
        self.ack_seq+=1;self.ack_publications.append((index,copy.deepcopy(p)))
        return wire


def replay_motion(motion,native,epoch,release_ns):
    """Read-only full journal pass; original Reach replay is also mandatory."""
    evidence={n:StopEvidence(epoch,n,release_ns,native[n]) for n in ROBOTS}
    gates={};pubs=[];callbacks=[];configuration=None;raws={};raw_counts=dict.fromkeys(ROBOTS,0)
    for index,row in enumerate(motion,1):
        require(row.get('schema')=='mr3-motion-safety-v1' and row.get('epoch')==epoch
                and integer(row.get('record_sequence'),1)==index,'authority motion source sequence/context')
        kind,p=row['kind'],row['payload'];require(type(p) is dict,'authority motion payload object')
        require(type(kind) is str,'authority motion kind is not a string')
        if kind=='configuration':
            require(configuration is None and p.get('motion_authority_profile')==PROFILE,
                    'actual motion authority configuration missing/mixed')
            configuration=p
        if kind in ('invalid_motion_authority','invalid_authority_ack','reach_model_failure',
                    'invalid_reach_driver_ingress'):
            raise ValueError('actual authority/model fault retained: '+kind)
        robot=p.get('robot')
        if robot in ROBOTS:evidence[robot].ingest(row,index)
        if kind=='authority_configuration':
            require(robot in ROBOTS and robot not in gates and p.get('motion_authority_profile')==PROFILE,
                    'authority local configuration missing/duplicate/mixed')
            gid=graph(p['publisher_identity'],robot)
            gates[robot]=ReceivingReplay(epoch,robot,gid,evidence[robot])
            gates[robot].raw_seq=raw_counts[robot]
            gates[robot].raw=copy.deepcopy(raws.get(robot))
        elif kind=='raw_request':
            require(robot in ROBOTS,'authority raw owner unknown')
            require(integer(p['request']['sequence'],1)==raw_counts[robot]+1,'raw callback sequence gap before binding')
            raw_counts[robot]+=1;raws[robot]=copy.deepcopy(p['request'])
            if robot in gates:gates[robot].raw_callback(p['request'])
        elif kind=='authority_callback':
            require(robot in gates,'authority callback before actual configuration')
            gates[robot].receive(p,index);callbacks.append((index,copy.deepcopy(p)))
        elif kind=='authority_ack_publication':
            require(robot in gates,'authority ACK before actual configuration')
            gates[robot].ack_publication(p,index);pubs.append((index,copy.deepcopy(p)))
        elif kind=='reach_decision':
            require(robot in ROBOTS,'authority decision owner unknown')
            if robot not in gates:
                expected=dict(effective_request=[0.,0.],permission='zero_only',state='UNBOUND',
                    authority_sequence=0,owner=None,raw_goal_generation=None,
                    raw_goal_association='UNKNOWN_UNSTAMPED_TWIST')
                require(p.get('motion_authority_profile')==PROFILE,'unbound decision profile missing')
                equal(p['motion_authority'],expected,'unbound receiving permission changed')
                equal(p['effective_request'],[0.,0.],'unbound motion effective target nonzero')
            else:gates[robot].decision(p,index)
        elif kind.startswith(('authority_','invalid_authority','invalid_motion_authority')):
            raise ValueError('unknown authority motion event: '+kind)
    require(configuration is not None and set(gates)==set(ROBOTS),'all three genuine authority configurations required')
    require(all(not g.expected_acks for g in gates.values()),'successful callback omitted actual ACK publication')
    return dict(profile=PROFILE,raw_generation_known=False,robots={n:dict(
        passed=True,authority_callbacks=len(gates[n].callbacks),ack_publications=gates[n].ack_seq,
        decisions=len(gates[n].decision_permissions),
        after_real_nonzero_application=evidence[n].sticky_motion) for n in ROBOTS}),dict(
            gates=gates,ack_publications=pubs,callbacks=callbacks)


class DeferredTerminals:
    """Source-order actual receipt scheduling, separate from six-phase oracle.

    Callers invoke the unchanged GoalDispatcher only at the returned dispatch.
    This class never rewrites the delivered envelope or native-cancel B origin.
    """
    def __init__(self):
        self.buffered={};self.pending_delivery={};self.ready={};self.ready_clock={}
        self.deliveries={};self.dispatched=[];self.never_granted=set()

    def delivery(self,envelope,now,phase,granted):
        event=envelope['payload'];robot=event['robot'];goal=event['goal_id']
        require(robot in ROBOTS and envelope['stream']=='receipt' and envelope['source']==robot,
                'terminal receipt stream/owner differs')
        require(clock(envelope['source_stamp'])<=clock(envelope['generated_stamp'])
                <=clock(envelope['received_stamp'])==now,'terminal receipt source/generation/receive clocks differ')
        key=(robot,integer(envelope['sequence'],1));old=self.deliveries.get(key)
        require(old is None,'duplicate accepted receipt delivery')
        self.deliveries[key]=copy.deepcopy(envelope)
        if event['type']=='result' and granted and phase=='canceling' and event['value'] in (4,5,6):
            require(robot not in self.pending_delivery and robot not in self.buffered,'duplicate buffered terminal')
            self.pending_delivery[robot]=copy.deepcopy(envelope)
            return False
        return True

    def buffer(self,p,now,current):
        robot=p['robot'];saved=self.pending_delivery.pop(robot,None)
        require(saved is not None and current is not None and current['operation']=='revoke',
                'buffer lacks actual canceling result and revoked current owner')
        equal(p,dict(robot=robot,goal_id=saved['payload']['goal_id'],delivery=saved,
                     authority_sequence=current['authority_sequence'],buffered_clock_ns=now,
                     receipt_times_rewritten=False),'terminal buffer changed delivered receipt or clock')
        require(saved['payload']['goal_id']==current['goal_id'],'terminal buffer owner mismatch')
        self.buffered[robot]=saved

    def ready_callback(self,robot,wire,now):
        require(wire['ack']['stage']=='stop_obligation_ready' and integer(wire['clock_ns'])<=now,
                'terminal readiness is not a genuine received stopReady')
        self.ready[robot]=copy.deepcopy(wire);self.ready_clock[robot]=now

    def revoke(self,robot):
        self.ready.pop(robot,None);self.ready_clock.pop(robot,None)

    def dispatch(self,p,now,current):
        robot=p['robot'];saved=self.buffered.get(robot);ready=self.ready.get(robot)
        require(saved is not None and ready is not None and current is not None
                and current['operation']=='revoke','terminal dispatch omitted actual buffer/received readiness/revoke')
        ack=ready['ack']
        require(ack['authority_sequence']==current['authority_sequence']
                and ready['authority_packet_sha256']==digest(current)
                and now>=self.ready_clock[robot] and now>=clock(saved['received_stamp']),
                'terminal dispatch readiness belongs to another owner/sequence/time')
        equal(ack['owner'],current,'terminal readiness owner changed')
        expected=dict(robot=robot,goal_id=saved['payload']['goal_id'],original_delivery=saved,
                      matching_ready_ack=ready,dispatch_clock_ns=now,receipt_times_rewritten=False)
        equal(p,expected,'terminal dispatch rewrote original native source/delivery envelope')
        del self.buffered[robot];self.dispatched.append(copy.deepcopy(p))
        return saved['payload']

    def finish(self):
        require(not self.pending_delivery and not self.buffered,'unclosed deferred terminal tail')


def replay_adapter(rows,transitions,epoch,motion_context,protocol_class):
    """Original GoalDispatcher, with separately proven real callback scheduling.

    protocol_class must be the caller's whole-source pinned original class;
    it is not the production authority helper. Public custody verifies its pin.
    """
    expected_protocol=deque();oracle=protocol_class(epoch,lambda p:expected_protocol.append(copy.deepcopy(p)))
    scheduler=DeferredTerminals();current=dict.fromkeys(ROBOTS);grants=dict.fromkeys(ROBOTS)
    accepted={};native_terminal={};native_sent={};native_cancel={};pending_accept={}
    ack_last={n:0 for n in ROBOTS};ack_value={};ack_gid={};callback_count=0
    motion_pubs={canonical(p['message']):p for _,p in motion_context['ack_publications']}
    published={};publication_keys=set();seen_motion_callbacks=set();previous=-1
    commands={};snapshots={};configuration=False;started_at=None;expected_stale_ack=None
    for step in transitions:
        if 'snapshot' in step:snapshots[step['snapshot']['sequence']]=step['snapshot']
        command=step.get('info',{}).get('command')
        if command is not None and step.get('info',{}).get('action_submitted',True):
            identity=integer(command['command_id'])
            require(identity not in commands,'duplicate submitted policy command')
            commands[identity]=command
    for index,row in enumerate(rows,1):
        require(row.get('epoch')==epoch and type(row.get('payload')) is dict,'adapter authority source context')
        now=clock(row['stamp']);require(now>=previous,'adapter source clock regressed');previous=now
        kind,p=row['kind'],row['payload'];robot=p.get('robot');goal=p.get('goal_id')
        require(type(kind) is str,'authority adapter kind is not a string')
        require(expected_stale_ack is None or kind=='authority_ack_stale',
                'stale ACK callback omitted its actual source-order rejection event')
        if kind in ('invalid_authority_ack','rpc_error','authority_failure'):
            raise ValueError('actual authority/RPC failure retained: '+kind)
        if kind=='authority_configuration':
            require(not configuration,'duplicate adapter authority configuration')
            equal(p,dict(motion_authority_profile=PROFILE,six_navigation_phases_unchanged=True,
                worker_quantum_ack_barrier=False,raw_goal_generation=None,
                raw_goal_association='UNKNOWN_UNSTAMPED_TWIST'),'adapter authority configuration/claim differs')
            configuration=True
        elif kind=='task_start':
            require(started_at is None and clock(p['start_sim_time_sec'])==now,
                    'adapter task release missing/duplicated or changed frontier')
            started_at=p['start_sim_time_sec']
        elif kind=='authority_task_stop_callback':
            require(set(p)=={'message','clock_ns','started_at'} and started_at is not None,
                    'task stop lacks actual accepted callback fields/prior release')
            equal(p['started_at'],started_at,'task stop changed actual release origin')
            message=p['message']
            require(type(message) is dict and set(message)=={'stamp','frame_id'}
                    and message['frame_id']=='map' and type(message['stamp']) is dict
                    and set(message['stamp'])=={'sec','nanosec'},'task stop message fields/frame differ')
            stamp=integer(message['stamp']['sec'])*1_000_000_000+integer(message['stamp']['nanosec'])
            require(message['stamp']['nanosec']<1_000_000_000
                    and clock(started_at)<=stamp<=integer(p['clock_ns'])==now,
                    'task stop precedes release/is future or callback clock differs')
            original_stamp=message['stamp']['sec']+message['stamp']['nanosec']/1e9
            require(started_at<=original_stamp<=now/1e9,
                    'task stop did not pass the unchanged original float dispatch gate')
            oracle.safety_stop(now/1e9,'task_stop')
        elif kind=='action':
            command=commands.get(p['command_id']);require(command is not None,'action lost original submitted command')
            snapshot=snapshots.get(command['observation_sequence']);require(snapshot is not None,'action snapshot missing')
            require(command['epoch']==epoch and snapshot['digest']==command['observation_digest']
                    and snapshot['joint_action_mask'][command['action']], 'action epoch/digest/mask differs')
            nav=oracle.navigation(now/1e9)
            for own in snapshot['robots']:
                require(all(own['navigation'].get(k)==nav[own['name']].get(k) for k in ('phase','goal_id')),
                        'action navigation changed since real snapshot')
            choices=[command['action']//100,command['action']//10%10,command['action']%10]
            result={}
            for name,choice in zip(ROBOTS,choices):
                target=snapshot['candidates'][choice] if choice<8 else None
                result[name]=oracle.submit(name,'GOAL' if choice<8 else 'KEEP' if choice==8 else 'WAIT',
                    now/1e9,snapshot['sequence'],command['command_id'],command['expires_at'],
                    goal={k:target[k] for k in ('x','y')} if target else None,
                    command_epoch=epoch,created_at=command['created_at'])
            equal(p,dict(command_id=command['command_id'],action=command['action'],results=result,
                observation_sequence=snapshot['sequence'],observation_digest=snapshot['digest'],
                candidate_version=snapshot['candidate_version'],choices=choices),'action original protocol result differs')
        elif kind=='delivery':
            stream=p['stream'];event=p['payload'];name=p['source']
            require(p['epoch']==epoch and name in ROBOTS and clock(p['received_stamp'])==now,
                    'actual delivery context/clock differs')
            oracle.tick(now/1e9)
            if stream=='heartbeat':
                oracle.renew(name,event['goal_id'],epoch,now/1e9,event['expires_at'])
            elif stream=='receipt':
                event_goal=event['goal_id'];state=oracle.states[name]
                is_granted=grants[name] is not None and grants[name]['goal_id']==event_goal and state.goal_id==event_goal
                immediate=scheduler.delivery(p,now,state.phase,is_granted)
                if event['type']=='accept':
                    if event['value'] is True:
                        require(event_goal in accepted and clock(p['source_stamp'])==accepted[event_goal]['accepted_callback_clock_ns'],
                                'accept delivery lacks matching actual accepted native callback')
                    outcome=oracle.on_accept(name,event_goal,event['value'],now/1e9)
                    if outcome=='active':pending_accept[name]=event_goal
                elif event['type']=='cancel':oracle.on_cancel_response(name,event_goal,event['value'],now/1e9)
                elif event['type']=='result':
                    require(event_goal in native_terminal and native_terminal[event_goal]['status']==event['value']
                            and clock(p['source_stamp'])==native_terminal[event_goal]['terminal_callback_clock_ns'],
                            'result delivery lacks matching actual native callback/status/source')
                    if not immediate:continue
                    if is_granted and event['value'] in (4,5,6) and current[name]['operation']!='revoke':
                        # The next publication must revoke the still-current
                        # actual owner before its natural terminal is released.
                        scheduler.pending_delivery[name]=copy.deepcopy(p)
                    else:oracle.on_result(name,event_goal,event['value'],now/1e9)
        elif kind=='native_send':
            require(robot in ROBOTS and goal not in native_sent and oracle.states[robot].goal_id==goal,
                    'native send lacks exclusive original protocol owner')
            native_sent[goal]=copy.deepcopy(p)
        elif kind=='native_cancel':
            require(robot in ROBOTS and goal in native_sent and oracle.states[robot].goal_id==goal
                    and oracle.states[robot].cancel_requested,'actual native cancel lacks canceling owner')
            require(p['scope']=='native_cancel_call_attempt' and clock(p['stamp'])==now,
                    'native cancel B origin changed')
            native_cancel[goal]=(index,now)
        elif kind=='authority_native_accept_callback':
            require(robot in ROBOTS and goal in native_sent and goal not in accepted
                    and re.fullmatch('[0-9a-f]{32}',p['native_goal_uuid'])
                    and integer(p['accepted_callback_clock_ns'])==now,'actual native accepted identity differs')
            accepted[goal]=copy.deepcopy(p)
        elif kind=='authority_native_terminal_callback':
            require(robot in ROBOTS and goal in accepted and type(p['status']) is int and p['status'] in (4,5,6)
                    and integer(p['terminal_callback_clock_ns'])==now,'native terminal callback identity differs')
            equal(p['native_identity'],accepted[goal],'native terminal changed saved accepted UUID')
            require(goal not in native_terminal,'native terminal callback duplicated')
            native_terminal[goal]=copy.deepcopy(p)
        elif kind=='authority_publication':
            packet=p['packet'];packet_shape(packet,epoch,robot);state=oracle.states[robot]
            require(integer(p['clock_ns'])==now==packet['source_clock_ns']
                    and p['scope']=='publication_call_returned'
                    and parse_wire(p['raw_json'],packet)==p['packet_sha256'], 'authority publication raw/time/scope differs')
            require(packet['authority_sequence']==(0 if current[robot] is None else current[robot]['authority_sequence'])+1,
                    'adapter authority sequence not contiguous')
            require(state.goal_id==packet['goal_id'] and state.accepted is True
                    and state.command['command_id']==packet['owner_command_id']
                    and clock(state.accepted_at)==packet['owner_accept_received_clock_ns']
                    and goal is None,'authority producer lacks actual currently accepted owner')
            identity=accepted.get(packet['goal_id'])
            require(identity is not None and identity['native_goal_uuid']==packet['native_goal_uuid'],
                    'authority publisher substituted native UUID')
            op=packet['operation']
            if op=='grant':
                require(state.phase=='active' and not state.cancel_requested
                        and pending_accept.get(robot)==packet['goal_id']
                        and packet['goal_id'] not in native_terminal and scheduler.ready.get(robot) is not None,
                        'grant lacks actual accept/pending owner/received stopReady or is already terminal')
                require(packet['owner_grant_sequence']==packet['authority_sequence']
                        and packet['lease_until_ns']==clock(state.lease_until),'grant changed original owner lease')
                grants[robot]=copy.deepcopy(packet);pending_accept.pop(robot,None)
            elif op=='renew':
                require(state.phase=='active' and not state.cancel_requested and grants[robot] is not None,
                        'renew lacks original active owner')
                equal(owner_token(packet),owner_token(grants[robot]),'renew changed actual owner token')
                require(packet['lease_until_ns']==clock(state.lease_until),'renew changed original protocol lease')
            else:
                require(grants[robot] is not None,'revoke has no previously actual grant')
                equal(owner_token(packet),owner_token(grants[robot]),'revoke changed actual owner token')
                terminal=scheduler.pending_delivery.get(robot)
                require((state.cancel_requested and packet['goal_id'] in native_cancel
                         and native_cancel[packet['goal_id']][1]==now)
                        or (terminal is not None and terminal['payload']['goal_id']==packet['goal_id']
                            and packet['goal_id'] in native_terminal),
                        'revoke has neither actual native cancel nor genuine terminal delivery')
            current[robot]=copy.deepcopy(packet);scheduler.revoke(robot)
            published[canonical(packet)]=(index,now,p);publication_keys.add(canonical(packet))
            # Natural terminal: revoke then the original immediate result
            # callback at the unchanged actual delivery frontier.
            pending=scheduler.pending_delivery.get(robot)
            if op=='revoke' and pending is not None and state.phase!='canceling':
                require(clock(pending['received_stamp'])==now,'natural terminal dispatch was delayed')
                event=pending['payload'];oracle.on_result(robot,event['goal_id'],event['value'],now/1e9)
                scheduler.pending_delivery.pop(robot)
        elif kind=='authority_ack_callback':
            require(robot in ROBOTS,'authority ACK owner unknown')
            wire=p['message'];rawhash=parse_wire(p['raw_json'],wire)
            require(type(wire) is dict and set(wire)==WIRE_KEYS and wire['schema']==WIRE
                    and wire['profile']==PROFILE and wire['epoch']==epoch and wire['robot']==robot
                    and integer(wire['clock_ns'])<=integer(p['clock_ns'])==now,'ACK callback clock/profile/context differs')
            gid=graph(p['publisher_identity'],robot,ack=True)
            require(robot not in ack_gid or ack_gid[robot]==gid,'ACK publisher graph changed');ack_gid[robot]=gid
            source=motion_pubs.get(canonical(wire))
            require(source is not None and hashlib.sha256(source['raw_json'].encode()).hexdigest()==rawhash,
                    'ACK callback has no identical validated motion publication')
            seq=integer(wire['ack_sequence'],1)
            if seq==ack_last[robot]:equal(wire,ack_value[robot],'conflicting duplicate ACK callback')
            elif seq>ack_last[robot]:
                ack_last[robot]=seq;ack_value[robot]=copy.deepcopy(wire)
                packet=current[robot];ack=wire['ack']
                if (ack['authority_sequence']==(0 if packet is None else packet['authority_sequence'])
                        and wire['authority_packet_sha256']==(None if packet is None else digest(packet))):
                    if ack['stage']=='stop_obligation_ready':
                        require(packet is None or packet['operation']=='revoke','ready received for active owner')
                        equal(ack['owner'],packet,'ready ACK current owner differs')
                        scheduler.ready_callback(robot,wire,now)
                else:expected_stale_ack=dict(robot=robot,ack_sequence=seq)
            callback_count+=1
        elif kind=='authority_ack_stale':
            require(expected_stale_ack is not None,'stale ACK event lacks actual mismatched callback')
            equal(p,expected_stale_ack,'stale ACK event changed callback identity')
            expected_stale_ack=None
        elif kind=='authority_terminal_buffered':scheduler.buffer(p,now,current[robot])
        elif kind=='authority_terminal_dispatched':
            event=scheduler.dispatch(p,now,current[robot]);oracle.on_result(robot,event['goal_id'],event['value'],now/1e9)
        elif kind=='authority_never_granted_terminal':
            require(robot in ROBOTS and goal in native_terminal and goal not in {g['goal_id'] for g in grants.values() if g},
                    'never-granted terminal actually had authority')
            equal(p['native_terminal'],native_terminal[goal],'never-granted changed actual native terminal')
            require(p['permission']=='zero_only','quick terminal claimed motion permission')
            if 'accept_delivery' in p:
                require(p['accept_delivery']['payload']['type']=='accept'
                        and p['accept_delivery']['payload']['goal_id']==goal
                        and p['accept_delivery'] in scheduler.deliveries.values(),
                        'quick-terminal accept is not a genuine delivered receipt')
            else:require(integer(p['clock_ns'])==now,'quick-terminal check clock differs')
            pending_accept.pop(robot,None);scheduler.never_granted.add(goal)
        elif kind=='safety_stop':oracle.safety_stop(now/1e9,'external_safety_failure')
        elif kind=='task_terminal':oracle.safety_stop(now/1e9,'task_terminal:'+p['termination_reason'])
        elif kind=='state_stale':oracle.safety_stop(now/1e9,'received_state_stale')
        elif kind=='action_rejected' and p.get('reason')=='task_deadline':oracle.safety_stop(now/1e9,'task_deadline')
        elif kind=='edge_goal_not_sent':
            name=goal.split(':')[-2]
            if p['reason']=='stopped':oracle.on_result(name,goal,'CANCELED',now/1e9)
            elif p['reason']=='expired':oracle.on_accept(name,goal,False,now/1e9)
            else:raise ValueError('unknown unsent branch')
        elif kind=='protocol':
            if not expected_protocol:oracle.tick(now/1e9)
            require(expected_protocol,'protocol event has no unchanged GoalDispatcher transition')
            equal(p,expected_protocol.popleft(),'protocol event differs from original six-phase oracle/deferred schedule')
        elif kind.startswith(('authority_','invalid_authority','invalid_motion_authority')):
            raise ValueError('unknown authority adapter event: '+kind)
    scheduler.finish()
    require(expected_stale_ack is None,'unclosed stale ACK rejection tail')
    require(configuration,'actual adapter authority configuration missing')
    require(not expected_protocol,'missing original protocol events at closed tail')
    for _,p in motion_context['callbacks']:
        require(canonical(p['message']) in publication_keys,'motion authority callback has no actual adapter publication')
        source=published[canonical(p['message'])]
        require(source[1]<=p['clock_ns'],'authority callback precedes actual producer source clock')
        seen_motion_callbacks.add(canonical(p['message']))
    return dict(passed=True,profile=PROFILE,raw_generation_known=False,
                actual_publications=len(published),actual_ack_callbacks=callback_count,
                deferred_terminal_dispatches=len(scheduler.dispatched),
                never_granted_terminals=len(scheduler.never_granted),
                original_six_phase_protocol_replayed=True)


PROTOCOL_SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py'
PROTOCOL_SHA256='5a2b90efd162b19a35964750002fe549413fec6e07f9679ea611d3fe6b1e4ada'


def original_protocol_class(root):
    """Execute only the exact unchanged pure six-phase source in a private package.

    The public runtime source proof must separately bind both complete files to
    its current execution freeze. This is never a production authority oracle.
    """
    path=Path(root)/PROTOCOL_SOURCE;raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==PROTOCOL_SHA256,'original six-phase protocol source changed')
    package='_mr3_independent_original_protocol_'+hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:16]
    if package not in sys.modules:
        value=types.ModuleType(package);value.__path__=[str(path.parent)];sys.modules[package]=value
    for name in ('mr3_episode','mr3_protocol'):
        fullname=package+'.'+name;source=path.parent/(name+'.py')
        spec=importlib.util.spec_from_file_location(fullname,source)
        module=importlib.util.module_from_spec(spec);sys.modules[fullname]=module
        spec.loader.exec_module(module)
    return sys.modules[package+'.mr3_protocol'].GoalDispatcher


def require_episode_proof(report,profile=PROFILE):
    """Conjoin a freshly executed independent role report, never raw metadata."""
    require(type(report) is dict and report.get('passed') is True
            and report.get('motion_authority_profile')==profile
            and report.get('independent_motion_authority_replay_passed') is True,
            'public role omitted independent receiving-authority replay')
    proof=report.get('motion_authority_replay')
    require(type(proof) is dict and proof.get('schema')=='mr3-independent-motion-authority-episode-v1'
            and proof.get('profile')==profile and proof.get('passed') is True
            and proof.get('raw_generation_known') is False
            and proof.get('original_global_stop_debts_and_fixed_radius_passed') is True
            and proof.get('adapter',{}).get('original_six_phase_protocol_replayed') is True
            and set(proof.get('robots',{}))==set(ROBOTS)
            and all(type(v) is dict and v.get('passed') is True for v in proof['robots'].values()),
            'public role has incomplete owner/receiving/actual-stop/deferred-protocol proof')
    return proof
