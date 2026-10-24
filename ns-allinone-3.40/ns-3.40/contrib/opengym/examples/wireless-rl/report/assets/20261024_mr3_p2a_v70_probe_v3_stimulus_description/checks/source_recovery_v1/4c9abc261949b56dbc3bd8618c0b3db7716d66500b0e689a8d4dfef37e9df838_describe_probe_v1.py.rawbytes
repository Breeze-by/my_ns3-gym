"""Fixed received ProbeV3 failure description; no native/scientific verdict."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261024_mr3_p2a_v70_probe_v3_stimulus_description'
RUN = ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v69/mr3_p2a_reach_v69_interface'
INPUT_PATHS = (RUN/'worker0/episode001_open_101/transitions.jsonl', RUN/'benchmark_summary.json')
OUTPUT = Path('/tmp/mr3_p2a_v70_probe_v3_stimulus_description_v1.json')
ROBOTS = ('tb1','tb2','tb3')
ROUNDS = ('initial','second')
PROBE = 'mr3-p2a-reach-outward-cancel-v3'
ORIGINAL_FREEZE = '720cd4e194eeb2e9f14a86ed9204f6110d72173b'
SCHEMA = 'mr3-v70-fixed-received-probe-v3-description-v1'
STABLE = ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
LIMITS = {'max_inputs':2,'max_encoded_bytes':4456448,'max_decoded_bytes':4456448,
    'max_output_bytes':4194304,'max_snapshot_rows':33,'max_timeline_rows':33,
    'max_initial_candidate_rows':24,'max_timeline_candidate_rows':264,'max_initial_joint_rows':1000}
INTERPRETATION_SOURCES = {'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/benchmark.py': {'bytes': 91880, 'sha256': '72360f3a786635a02e13d83d9afe9035afa556047e2ea50fe7c71d55c62b9e7b'}, 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/supervisor.py': {'bytes': 29711, 'sha256': 'dc632fd50321974317ee8c361f8101e3ecb9bd6189b76b35b5501cfbb34a22f2'}, 'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py': {'bytes': 109042, 'sha256': '39510df6fd68d0c196e6e2a461ac4ac867da73468176d953bcc2ea6f100218a1'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py': {'bytes': 62388, 'sha256': '57542e09c126461db99e47e8c5125baa610aed672c996d07f4422653ca7a34a8'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py': {'bytes': 18491, 'sha256': '5a2b90efd162b19a35964750002fe549413fec6e07f9679ea611d3fe6b1e4ada'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py': {'bytes': 54797, 'sha256': '5709af2e31f45691d05034375b43ef4ca873c427ba3579e0944b3f0556fa83f1'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_activity.py': {'bytes': 6162, 'sha256': '7af918d75c05b6f8fb1a65899e43aad11a315640e8b00fdb589c31f693ad696e'}}

def require(value, message):
    if not value:
        raise ValueError(message)

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def ns(value):
    require(finite(value) and value >= 0, 'invalid producer clock')
    return round(value*1e9)

def integer(value, low=0):
    require(type(value) is int and value >= low, 'invalid integer')
    return value

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def decode(raw):
    def unique(pairs):
        result = {}
        for key,value in pairs:
            require(key not in result,'duplicate JSON key')
            result[key] = value
        return result
    value=json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    canonical(value)  # Also reject ordinary JSON numeric overflow, such as1e999.
    return value

def present(value, key):
    """Never turn absent, null, false, zero or an empty list into each other."""
    require(type(value) is dict,'field parent is not an object')
    return {'present':key in value, **({'value':copy.deepcopy(value[key])} if key in value else {})}

def snapshot_check(snapshot, epoch):
    require(type(snapshot) is dict and snapshot['epoch']==epoch,'snapshot epoch')
    require(sha(canonical({k:v for k,v in snapshot.items() if k!='digest'}))==snapshot['digest'],
            'snapshot digest differs')
    integer(snapshot['sequence'],1);ns(snapshot['source_stamp']);ns(snapshot['task_elapsed_sec'])
    require([r['name'] for r in snapshot['robots']]==list(ROBOTS),'robot order')
    require(len(snapshot['candidates'])==8 and len(snapshot['per_robot_action_mask'])==3
            and all(len(m)==10 and all(type(v) is bool for v in m)
                    for m in snapshot['per_robot_action_mask'])
            and len(snapshot['joint_action_mask'])==1000
            and all(type(v) is bool for v in snapshot['joint_action_mask']),'original mask dimensions/types')

def joined(transitions, decisions, epoch, expected_steps=32):
    require(len(transitions)==expected_steps+1 and len(decisions)==expected_steps,'full original transition/decision count')
    require(transitions[0]['kind']=='reset' and all(r['kind']=='step' for r in transitions[1:]),'reset/step order')
    snapshots=[r['snapshot'] for r in transitions]
    for row in snapshots:snapshot_check(row,epoch)
    require(ns(snapshots[0]['task_elapsed_sec'])==0,'initial task boundary')
    out=[]
    for i,(before,after,row,planned) in enumerate(zip(snapshots,snapshots[1:],transitions[1:],decisions)):
        require(before['sequence']<after['sequence'] and ns(after['source_stamp'])-ns(before['source_stamp'])==10**9
                and ns(after['task_elapsed_sec'])==ns(before['task_elapsed_sec'])+10**9,'noncausal full one-second boundary')
        info=row['info'];require(info['epoch']==epoch,'step info epoch')
        flag=info.get('action_submitted',True)
        require(type(flag) is bool,'action_submitted type')
        require(flag is True and type(info.get('command')) is dict,'full32 original commands unavailable')
        cmd=info['command'];integer(cmd['command_id'],1);integer(cmd['action'])
        require(0<=cmd['action']<1000,'action range')
        expected=dict(epoch=epoch,observation_sequence=before['sequence'],observation_digest=before['digest'],action=cmd['action'])
        require(all(cmd.get(k)==v and type(cmd.get(k)) is type(v) for k,v in expected.items()),'command does not bind previous snapshot')
        require(ns(cmd['created_at'])==ns(before['source_stamp']) and ns(cmd['expires_at'])==ns(cmd['created_at'])+2*10**9,'command time/expiry')
        require(all(planned.get(k)==v and type(planned.get(k)) is type(v) for k,v in expected.items())
                and planned['clock_ns']==ns(before['source_stamp'])
                and ns(planned['task_elapsed_sec'])==ns(before['task_elapsed_sec']),'summary planned decision join')
        require(planned['round']==('initial' if ns(before['task_elapsed_sec'])<13*10**9 else 'second'),'summary decision round')
        require(before['joint_action_mask'][cmd['action']] is True,'submitted action not in original joint mask')
        out.append((before,cmd,planned))
    require(len({cmd['command_id'] for _,cmd,_ in out})==expected_steps and [cmd['command_id'] for _,cmd,_ in out]==sorted(cmd['command_id'] for _,cmd,_ in out),'duplicate/reordered command id')
    return out,snapshots[-1]

def nonapproach(snapshot, choices):
    if all(c>=8 for c in choices):return True
    robots=snapshot['robots']
    if any(r.get('fresh') is not True or r.get('valid') is not True
           or not all(finite(r.get(k)) for k in ('x','y')) for r in robots):return False
    for i,c in enumerate(choices):
        if c>=8:continue
        own=robots[i];goal=snapshot['candidates'][c]
        if not all(finite(goal.get(k)) for k in ('x','y')):return False
        gx,gy=goal['x']-own['x'],goal['y']-own['y'];length=math.hypot(gx,gy)
        if not finite(length) or length<=0:return False
        for j,peer in enumerate(robots):
            if i==j:continue
            px,py=peer['x']-own['x'],peer['y']-own['y'];den=length*math.hypot(px,py);dot=gx*px+gy*py
            if not all(finite(v) for v in (den,dot)) or den<=0 or -dot/den<0:return False
    return True

def self_identity():
    tail=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':os.getpid(),'parent':int(tail[1]),'group':int(tail[2]),'session':int(tail[3]),'start_ticks':int(tail[19])}

def fixed_file(path, limit, on_read=None):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve(strict=True)==path,'noncanonical path')
    before=path.lstat();require(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'not regular or over byte cap')
    with path.open('rb') as stream:
        require(tuple(getattr(os.fstat(stream.fileno()),k) for k in STABLE)==tuple(getattr(before,k) for k in STABLE),'opened identity differs')
        try:raw=stream.read(limit+1)
        except OSError:
            if on_read is not None:on_read(None)
            raise
        if on_read is not None:on_read(len(raw))
    require(len(raw)==before.st_size and tuple(getattr(path.lstat(),k) for k in STABLE)==tuple(getattr(before,k) for k in STABLE),'input changed')
    return raw,tuple(getattr(before,k) for k in STABLE)

def fail(state,rid,name,reason):
    row={'round':rid,'robot':name,'reason':reason}
    if row not in state['coverage_failures']:state['coverage_failures'].append(row)


def observe(snapshot,state):
    """Retain actual coverage failures; they are not JSON/description failures."""
    now,task=ns(snapshot['source_stamp']),ns(snapshot['task_elapsed_sec'])
    state['last_clock_ns']=now
    for rid in ROUNDS:
        for robot in snapshot['robots']:
            name=robot['name'];saved=state['rounds'][rid][name];nav=robot['navigation']
            if 'goal_id' not in saved:continue
            same=nav.get('goal_id')==saved['goal_id'];accepted=nav.get('accepted_at')
            if (same and nav.get('owned') is True and nav.get('phase') in ('active','canceling')
                    and finite(accepted) and accepted<=snapshot['source_stamp']
                    and type(nav.get('accepted_goal_count')) is int and nav['accepted_goal_count']>0):
                stamp=round(accepted*1e9)
                if stamp<saved['goal_created_ns']:fail(state,rid,name,'acceptance_predates_goal')
                if 'accepted_at_ns' in saved and stamp!=saved['accepted_at_ns']:fail(state,rid,name,'accepted_goal_time_changed')
                saved.setdefault('accepted_at_ns',stamp);saved.setdefault('accepted_observed_ns',now)
                if stamp-(now-task)>(2 if rid=='initial' else 20)*10**9:fail(state,rid,name,'acceptance_outside_bounded_opportunity')
            activity=robot['activity'];path=activity.get('estimated_path_m');source=activity.get('last_odom_source_stamp')
            if (saved.get('baseline_capture_count')==0 and same and nav.get('owned') is True
                    and nav.get('phase')=='active' and 'accepted_at_ns' in saved
                    and saved['accepted_at_ns']>=saved['goal_created_ns']
                    and robot.get('fresh') is True and robot.get('valid') is True
                    and activity.get('epoch')==snapshot['epoch']
                    and type(activity.get('state_sequence')) is int and activity['state_sequence']>=0
                    and activity.get('path_observation_complete') is True and finite(path) and path>=0
                    and finite(source) and 0<=source<=snapshot['source_stamp'] and saved['accepted_at_ns']<=ns(source)):
                saved.update(baseline_path_m=path,baseline_capture_count=1,baseline_epoch=snapshot['epoch'],
                    baseline_observed_ns=now,baseline_path_source_ns=ns(source),baseline_snapshot_sequence=snapshot['sequence'],
                    baseline_snapshot_digest=snapshot['digest'],baseline_activity_state_sequence=activity['state_sequence'])
            if same and nav.get('cancel_requested') is True and nav.get('stop_reason')=='wait' and 'wait_command_id' in saved:
                saved.setdefault('cancel_request_observed_ns',now)
            terminal=nav.get('last_terminal')
            if nav.get('last_goal_id')==saved['goal_id'] and terminal is not None and 'cancel_terminal_observed_ns' not in saved:
                if terminal!='CANCELED' or 'wait_command_id' not in saved or 'accepted_at_ns' not in saved or nav.get('stop_reason')!='wait':
                    fail(state,rid,name,'goal_terminal_without_confirmed_stimulus_cancel')
                elif nav.get('phase')=='idle' and nav.get('owned') is False:saved.setdefault('cancel_terminal_observed_ns',now)
            if 'cancel_terminal_observed_ns' in saved and 'handoff_observed_ns' not in saved:
                rest=saved.setdefault('rest_source_ns',[]);stamp=robot.get('odom_source_stamp');speed=robot.get('v')
                good=(robot.get('fresh') is True and robot.get('valid') is True and finite(stamp)
                    and 0<=stamp<=snapshot['source_stamp'] and finite(speed) and abs(speed)<=.01
                    and nav.get('phase')=='idle' and nav.get('owned') is False and nav.get('last_goal_id')==saved['goal_id'])
                if not good:rest.clear()
                elif not rest or ns(stamp)>rest[-1]:rest.append(ns(stamp));del rest[:-3]
                if len(rest)==3 and now-saved['cancel_terminal_observed_ns']>=3*10**9:saved['handoff_observed_ns']=now


def choices(action):return (action//100,action//10%10,action%10)


def reverse_robots(snapshot,references,action):
    result=[]
    for i,c in enumerate(choices(action)):
        own=snapshot['robots'][i];ref=references.get(own['name'])
        if c>=8 or ref is None:continue
        target=snapshot['candidates'][c]
        angle=math.atan2(target['y']-own['y'],target['x']-own['x'])-own['yaw']
        if math.atan2(math.sin(angle),math.cos(angle))*ref['sign']<=-.25:result.append(own['name'])
    return result


def rank(snapshot,references,rid,action):
    margins=[];paths=0.;goals=0
    for i,c in enumerate(choices(action)):
        if c>=8:continue
        goals+=1;own=snapshot['robots'][i];target=snapshot['candidates'][c];distance=target['path_distances_m'][i]
        require(finite(distance),'original legal GOAL has nonfinite path distance')
        paths+=distance;gx,gy=target['x']-own['x'],target['y']-own['y'];length=math.hypot(gx,gy);peer_margins=[]
        for j,peer in enumerate(snapshot['robots']):
            if j==i:continue
            px,py=peer['x']-own['x'],peer['y']-own['y'];den=length*math.hypot(px,py)
            peer_margins.append(-(gx*px+gy*py)/den if den else -1.)
        margins.append(min(peer_margins,default=-1.))
    return (-goals,-len(reverse_robots(snapshot,references,action)) if rid=='second' else 0,
        -min(margins,default=-1.),-sum(margins),-paths,action)


def robot_predicates(snapshot,state,index,rid):
    robot=snapshot['robots'][index];name=robot['name'];nav=robot['navigation'];activity=robot['activity'];saved=state['rounds'][rid][name]
    now,task=snapshot['source_stamp'],ns(snapshot['task_elapsed_sec']);path=activity.get('estimated_path_m');source=activity.get('last_odom_source_stamp')
    common={'goal_window':task<1500000000 or 13*10**9<=task<20*10**9,
        'no_goal_command':'goal_command_id' not in saved,'idle':nav.get('phase')=='idle','unowned':nav.get('owned') is False,
        'fresh':robot.get('fresh') is True,'valid':robot.get('valid') is True,
        'initial_handoff':rid=='initial' or 'handoff_observed_ns' in state['rounds']['initial'][name]}
    moving={'fresh':common['fresh'],'valid':common['valid'],'active':nav.get('phase')=='active','owned':nav.get('owned') is True,
        'same_saved_goal':nav.get('goal_id')==saved.get('goal_id'),'accepted_observed':'accepted_at_ns' in saved,
        'forward_speed_ge_0_08':finite(robot.get('v')) and robot['v']>=.08,
        'path_complete':activity.get('path_observation_complete') is True,'baseline_once':saved.get('baseline_capture_count')==1,
        'same_activity_epoch':activity.get('epoch')==saved.get('baseline_epoch')==snapshot['epoch'],
        'path_source_finite_not_future':finite(source) and 0<=source<=now,
        'path_source_not_before_baseline':finite(source) and source>=0 and 'baseline_path_source_ns' in saved and ns(source)>=saved['baseline_path_source_ns'],
        'baseline_finite':finite(saved.get('baseline_path_m')),'path_finite':finite(path),
        'path_delta_ge_0_05':finite(path) and finite(saved.get('baseline_path_m')) and path-saved['baseline_path_m']>=.05}
    # The producer uses the original WAIT mask for commitment, rather than a second invented eligibility gate.
    wait_mask=snapshot['per_robot_action_mask'][index][9]
    moving_info=dict(moving,first_scientific_wait='wait_command_id' not in saved,original_wait_mask=wait_mask,
        original_commitment_elapsed=finite(nav.get('commitment_until')) and now>=nav['commitment_until'])
    cleanup=10*10**9<=task<13*10**9 or task>=28*10**9
    if all(moving.values()) and 'wait_command_id' not in saved and wait_mask:mode='moving_owned_first_legal_wait';want=(9,)
    elif cleanup and wait_mask:mode='bounded_cleanup_wait_no_credit';want=(9,)
    else:mode='eligible_goal_or_keep';want=None
    candidate_rows=[];eligible=[]
    for c,target in enumerate(snapshot['candidates']):
        distance=target['path_distances_m'][index]
        coords=all(finite(v) for v in (target.get('x'),target.get('y'),robot.get('x'),robot.get('y')))
        endpoint=math.hypot(target['x']-robot['x'],target['y']-robot['y']) if coords else None
        bearing=math.atan2(target['y']-robot['y'],target['x']-robot['x']) if coords else None
        relative=math.atan2(math.sin(bearing-robot['yaw']),math.cos(bearing-robot['yaw'])) if bearing is not None and finite(robot.get('yaw')) else None
        checks={'original_goal_mask':snapshot['per_robot_action_mask'][index][c],'coordinates_finite':coords,
            'path_distance_finite':finite(distance),'path_distance_positive':finite(distance) and distance>0}
        admitted=all(common.values()) and all(checks.values()) and want is None
        if admitted:eligible.append(c)
        candidate_rows.append({'index':c,'x':present(target,'x'),'y':present(target,'y'),'path_distance_m':distance,
            'valid':present(target,'valid'),'reachable':present(target,'reachable'),'endpoint_distance_m':endpoint,
            'map_bearing_rad':bearing,'relative_bearing_rad':relative,'checks':checks,'currently_eligible':admitted})
    if want is None:want=tuple(eligible)+(8,)
    return dict(robot=name,mode=mode,GOAL_common=common,blocked_GOAL_common=[k for k,v in common.items() if not v],
        moving_WAIT=moving_info,path_delta_m=path-saved['baseline_path_m'] if finite(path) and finite(saved.get('baseline_path_m')) else None,
        candidates=candidate_rows,eligible_candidates=eligible,desired_choices=list(want)),want


def select(snapshot,state,references):
    observe(snapshot,state);now,task=ns(snapshot['source_stamp']),ns(snapshot['task_elapsed_sec'])
    if task<10*10**9:
        for robot in snapshot['robots']:
            w=robot.get('w')
            if robot.get('fresh') is True and finite(w) and abs(w)>=.1:
                references.setdefault(robot['name'],dict(sign=math.copysign(1.,w),w=w,snapshot_sequence=snapshot['sequence'],
                    source_stamp=robot.get('source_stamp'),odom_source_stamp=robot.get('odom_source_stamp')))
    rid='initial' if task<13*10**9 else 'second';records=[];desired=[];admitted={};reasons={}
    for i,name in enumerate(ROBOTS):
        record,want=robot_predicates(snapshot,state,i,rid);records.append(record);desired.append(want)
        if record['mode'] in ('moving_owned_first_legal_wait','bounded_cleanup_wait_no_credit'):reasons[name]=record['mode']
        else:admitted[name]=record['eligible_candidates']
    legal=[a for a,v in enumerate(snapshot['joint_action_mask']) if v is True
        and all(c in desired[i] for i,c in enumerate(choices(a))) and nonapproach(snapshot,choices(a))]
    require(legal,'original legal V3 subset unavailable')
    action=min(legal,key=lambda a:rank(snapshot,references,rid,a));cs=choices(action)
    request=dict(epoch=snapshot['epoch'],observation_sequence=snapshot['sequence'],observation_digest=snapshot['digest'],round=rid,
        task_elapsed_sec=snapshot['task_elapsed_sec'],clock_ns=now,action=action,reasons=reasons,
        submitted_activity={r['name']:dict(r['activity']) for r in snapshot['robots']},
        goal_robots=[ROBOTS[i] for i,c in enumerate(cs) if c<8],wait_robots=[ROBOTS[i] for i,c in enumerate(cs) if c==9],
        eligible_goal_candidates=admitted,scope='planned input only; no native cancel or physical credit')
    note=None
    if request['goal_robots']:
        note=dict(task_elapsed_sec=snapshot['task_elapsed_sec'],snapshot_sequence=snapshot['sequence'],stage=rid+'_goal',action=action,
            selected_reverse_robots=reverse_robots(snapshot,references,action),scope='original legal nonapproach stimulus subset; not actor availability or physical proof')
    return request,note,records,legal


def consume(request,command,state):
    for name in request['goal_robots']:
        saved=state['rounds'][request['round']][name];require('goal_command_id' not in saved,'round GOAL retry')
        saved.update(goal_command_id=command['command_id'],goal_id=request['epoch']+':'+name+':'+str(command['command_id']),
            goal_created_ns=request['clock_ns'],submitted_activity=dict(request['submitted_activity'][name]),baseline_capture_count=0)
    for name in request['wait_robots']:
        if request['reasons'].get(name)!='moving_owned_first_legal_wait':continue
        saved=state['rounds'][request['round']][name];require('wait_command_id' not in saved,'science WAIT retry')
        saved.update(wait_command_id=command['command_id'],wait_submitted_ns=request['clock_ns'])
        if request['task_elapsed_sec']>(10 if request['round']=='initial' else 28):
            state['coverage_failures'].append({'round':request['round'],'robot':name,'reason':'moving_WAIT_outside_bounded_opportunity'})
    state['pending_submission']=None


def finish(state):
    for rid in ROUNDS:
        for name,saved in state['rounds'][rid].items():
            missing=[k for k in ('goal_command_id','accepted_at_ns','wait_command_id','cancel_terminal_observed_ns') if k not in saved]
            if saved.get('baseline_capture_count')!=1:missing.append('accepted_path_baseline_once')
            if len(saved.get('rest_source_ns',[]))<3:missing.append('three_fresh_rest_observations')
            if rid=='initial' and 'handoff_observed_ns' not in saved:missing.append('terminal_and_rest_handoff')
            if missing:fail(state,rid,name,'coverage_unavailable:'+','.join(missing))
    state.update(coverage_passed=not state['coverage_failures'],coverage_scope='received accepted/cancelled lifecycle only; independent native and physical gates required')


def initial_choices(snapshot,references,request,records,legal):
    all_joints=[];counts={(i,c):0 for i in range(3) for c in range(8)}
    for action,valid in enumerate(snapshot['joint_action_mask']):
        if valid is not True or not nonapproach(snapshot,choices(action)):continue
        desired=action in legal
        if desired:
            for i,c in enumerate(choices(action)):
                if c<8:counts[i,c]+=1
        distances=[None if c>=8 else {'candidate':c,'endpoint_m':records[i]['candidates'][c]['endpoint_distance_m'],
            'declared_path_m':snapshot['candidates'][c]['path_distances_m'][i]} for i,c in enumerate(choices(action))]
        all_joints.append(dict(action=action,choices=choices(action),in_V3_desired_subset=desired,
            rank=rank(snapshot,references,'initial',action),selected=action==request['action'],per_robot_GOAL_distances=distances))
    candidates=copy.deepcopy(records)
    for i,record in enumerate(candidates):
        for c,row in enumerate(record['candidates']):
            row['feasible_V3_joint_count']=counts[i,c];row['chosen']=choices(request['action'])[i]==c
    return dict(source_snapshot_sequence=snapshot['sequence'],source_snapshot_digest=snapshot['digest'],
        selected_action=request['action'],rank_order=['minus_GOAL_count','minus_reverse_count_second_only',
            'minus_min_outward_margin','minus_sum_outward_margins','minus_sum_declared_path_m','action'],
        robots=candidates,all_original_legal_nonapproach_joint_choices=all_joints,
        note='All rows use the actually received task0 bank/masks. Later owned-bank values are not delayed-GOAL counterfactual proof.')


def terminal_class(nav,saved):
    terminal=nav.get('last_terminal')
    if terminal is None or nav.get('last_goal_id')!=saved.get('goal_id') or 'goal_id' not in saved:return 'no_matching_received_terminal'
    if terminal=='CANCELED':
        if 'wait_command_id' in saved and 'accepted_at_ns' in saved and nav.get('stop_reason')=='wait':return 'received_CANCELED_with_matching_scientific_WAIT'
        return 'received_CANCELED_without_matching_scientific_WAIT'
    return 'received_'+str(terminal)+'_without_confirmed_stimulus_cancel'


def timeline_row(snapshot,state,record,command=None):
    robot=snapshot['robots'][2];nav=robot['navigation']
    return dict(snapshot_sequence=snapshot['sequence'],snapshot_digest=snapshot['digest'],source_stamp=snapshot['source_stamp'],
        task_elapsed_sec=snapshot['task_elapsed_sec'],navigation=copy.deepcopy(nav),activity=copy.deepcopy(robot['activity']),
        values={k:present(robot,k) for k in ('x','y','yaw','v','w','fresh','valid','source_stamp','odom_source_stamp')},
        original_action_mask=copy.deepcopy(snapshot['per_robot_action_mask'][2]),
        original_mask_reasons=copy.deepcopy(snapshot.get('mask_reasons',snapshot.get('diagnostics',{}).get('mask_reasons'))),
        current_round=record,received_round_states={r:copy.deepcopy(state['rounds'][r]['tb3']) for r in ROUNDS},
        terminal_classifications={r:terminal_class(nav,state['rounds'][r]['tb3']) for r in ROUNDS},command=copy.deepcopy(command),
        actual_terminal_source_or_delivery_time='UNKNOWN_FROM_THESE_TWO_INPUTS')


def describe(transitions,summary,epoch,*,expected_steps=32):
    require(type(epoch) is str and epoch,'fixed epoch required')
    require(summary.get('preparation_probe_version')==PROBE and summary.get('freeze')==ORIGINAL_FREEZE
        and summary.get('safety_contract')=='mr3-reach-v1' and type(summary.get('workers')) is int and summary['workers']==1
        and type(summary.get('passed')) is bool and summary.get('schedule')==[['open',101]],'fixed original benchmark identity')
    workers=summary['workers_results'];require(len(workers)==1 and type(workers[0]['worker_id']) is int and workers[0]['worker_id']==0,'one fixed worker')
    episodes=workers[0]['episodes'];require(len(episodes)==1 and episodes[0]['epoch']==epoch
        and type(episodes[0]['transitions']) is int and episodes[0]['transitions']==32,'one fixed complete episode')
    diag=episodes[0]['preparation_probe_diagnostics'];persisted=diag['reach_v3_stimulus']
    require(persisted['epoch']==epoch,'persisted state epoch')
    pairs,last=joined(transitions,persisted['decisions'],epoch,expected_steps)
    state=dict(epoch=epoch,rounds={r:{n:{} for n in ROBOTS} for r in ROUNDS},decisions=[],coverage_failures=[],last_clock_ns=-1)
    refs={};goal_notes=[];timeline=[];decision_checks=[];first=None
    for i,(snapshot,command,planned) in enumerate(pairs):
        request,note,records,legal=select(snapshot,state,refs)
        require(command['action']==request['action'],'actual command differs from independent V3 rank winner')
        decision_checks.append(dict(decision=i,previous_snapshot_line=i+1,post_snapshot_line=i+2,
            previous_snapshot_sequence=snapshot['sequence'],previous_snapshot_digest=snapshot['digest'],
            command_id=command['command_id'],actual_action=command['action'],independent_action=request['action'],
            planned_fields_equal=canonical(planned)==canonical(request),planned_sha256=sha(canonical(planned)),independent_sha256=sha(canonical(request))))
        if i==0:first=initial_choices(snapshot,refs,request,records,legal)
        timeline.append(timeline_row(snapshot,state,records[2],command))
        state['decisions'].append(request)
        if note is not None:goal_notes.append(note)
        consume(request,command,state)
    request,note,records,_=select(last,state,refs)
    require(ns(last['task_elapsed_sec'])==32*10**9,'final full32 boundary')
    state['pending_submission']=None
    if note is not None:goal_notes.append(note)
    timeline.append(timeline_row(last,state,records[2]));finish(state)
    rounds=[]
    for rid in ROUNDS:
        for name in ROBOTS:
            actual=state['rounds'][rid][name];saved=persisted['rounds'][rid][name]
            fields={k:{'reconstructed':present(actual,k),'persisted':present(saved,k),
                'equal':canonical(present(actual,k))==canonical(present(saved,k))} for k in sorted(set(actual)|set(saved))}
            rounds.append(dict(round=rid,robot=name,reconstructed=actual,persisted=saved,field_comparison=fields))
    comparisons={'whole_stimulus_state_equal':canonical(state)==canonical(persisted),
        'all_planned_requests_equal':all(x['planned_fields_equal'] for x in decision_checks),
        'reference_turn_samples_equal':canonical(refs)==canonical(diag.get('reference_turn_samples')),
        'goal_selection_notes_equal':canonical(goal_notes)==canonical(diag.get('goal_decisions',[]))}
    complete=all(comparisons.values())
    events=[];seen=set()
    for i,row in enumerate(timeline):
        for rid,classification in row['terminal_classifications'].items():
            key=(rid,row['navigation'].get('last_goal_id'),classification)
            if classification=='no_matching_received_terminal' or key in seen:continue
            seen.add(key);events.append(dict(round=rid,classification=classification,navigation=copy.deepcopy(row['navigation']),
                first_observed_clock=row['source_stamp'],first_observed_task_elapsed_sec=row['task_elapsed_sec'],snapshot_sequence=row['snapshot_sequence'],
                preceding_sample_clock=None if i==0 else timeline[i-1]['source_stamp'],actual_delivery_or_terminal_generation_time='UNKNOWN_FROM_THESE_TWO_INPUTS'))
    return dict(schema=SCHEMA,passed=complete,description_status='COMPLETE' if complete else 'COMPLETE_WITH_COMPARISON_MISMATCH',
        passed_scope='complete bounded two-input descriptive joins/reconstruction, including genuine original coverage FAIL',
        original_activity_passed=present(summary,'passed'),original_worker_error=present(workers[0],'error'),original_FAIL_preserved=summary.get('passed') is False,
        epoch=epoch,probe_version=PROBE,original_freeze=ORIGINAL_FREEZE,decision_join_checks=decision_checks,
        initial_bank_and_joint_rank=first,tb3_received_timeline=timeline,tb3_first_observed_terminals=events,
        robot_rounds=rounds,independent_coverage_failures=state['coverage_failures'],persisted_coverage_failures=copy.deepcopy(persisted['coverage_failures']),
        independent_coverage_passed=state['coverage_passed'],persisted_coverage_passed=present(persisted,'coverage_passed'),comparisons=comparisons,
        final_observation=dict(line=len(transitions),sequence=last['sequence'],source_stamp=last['source_stamp'],task_elapsed_sec=last['task_elapsed_sec'],no_extra_command=True),
        causal_scope='sampled received high-level state only; no native delivery, physical B/R or counterfactual trajectory proof',
        native_or_physics_or_qualification_credit=False)
def validate_admission(spec,freeze):
    require(spec.get('schema')=='mr3-v70-fixed-received-probe-v3-description-spec-v1','fixed spec schema')
    require(spec.get('admitted') is True and type(spec.get('admitted')) is bool,'unadmitted fixed description')
    require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}',freeze)
        and spec.get('execution_freeze')=='CLI_EXACT_PUSHED_FREEZE','new exact CLI freeze required')
    require(canonical(spec['identity'])==canonical({'original_freeze':ORIGINAL_FREEZE,'epoch':'mr3_p2a_reach_v69_interface_w0_e1_48541a42','worker_id':0,'episode_index':1,'scene':'open','seed':101,'steps':32}),'fixed original identity')
    require([x['path'] for x in spec['inputs']]==list(map(str,INPUT_PATHS)),'only fixed two original inputs')
    for i,row in enumerate(spec['inputs']):
        cap=(4194304,262144)[i]
        require(row['encoding']=='plain' and type(row['expected_bytes']) is int and 0<=row['expected_bytes']<=cap
            and type(row['expected_sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['expected_sha256'])
            and row['max_encoded_bytes']==row['max_decoded_bytes']==cap,'fixed regular original input caps/pins')
    require(canonical(spec['aggregate_limits'])==canonical(LIMITS) and type(spec['work_seconds']) is int and spec['work_seconds']==60
        and type(spec['parent_seconds']) is int and spec['parent_seconds']==120,'fixed resource caps')
    require(spec['output']=={'path':str(OUTPUT),'native_or_physics_or_qualification_credit':False},'fixed descriptive output')


def main(argv=None):
    began=time.monotonic_ns();identity=self_identity();actual_argv=list(sys.argv)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',required=True)
    parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);require(args.output==OUTPUT and not OUTPUT.exists(),'exclusive fixed output required')
    result=dict(schema=SCHEMA,passed=False,identity=identity,actual_argv=actual_argv,raw_input_bytes_read=0,
        raw_input_bytes_read_known=True,native_or_physics_or_qualification_credit=False,
        consumption_disclosure='New independent descriptor only. Original summary was previously read as closure metadata; transitions were previously read as opaque archive bytes, without prior independent semantic description.')
    observed={};source_raw={}
    try:
        require(Path(__file__).resolve()==A/'describe_probe_v1.py' and args.spec==A/'description_spec_v1.json','canonical consumer/spec only')
        spec_raw,_=fixed_file(args.spec,262144);spec=decode(spec_raw);validate_admission(spec,args.freeze)
        git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,timeout=10)
        require(git('rev-parse','HEAD').decode().strip()==args.freeze==git('rev-parse','origin/main').decode().strip()
            and not git('status','--porcelain','--untracked-files=all'),'clean exact pushed freeze required')
        bindings=spec['source_bindings']
        interpretation={r['path']:{'bytes':r['bytes'],'sha256':r['sha256']} for r in bindings if r['path'] in INTERPRETATION_SOURCES}
        require(interpretation==INTERPRETATION_SOURCES and len(bindings)==8 and len({x['path'] for x in bindings})==8,'consumer plus exact seven interpretation sources')
        for row in bindings:
            path=ROOT/row['path'];raw,stamp=fixed_file(path,1048576)
            require(len(raw)==row['bytes'] and sha(raw)==row['sha256'] and raw==git('show',args.freeze+':'+row['path']),'actual current/source/Git pin')
            source_raw[path]=(raw,stamp)
        require(str((A/'describe_probe_v1.py').relative_to(ROOT)) in {r['path'] for r in bindings},'consumer pin missing')
        require(spec_raw==git('show',args.freeze+':'+str(args.spec.relative_to(ROOT))),'spec differs from new freeze')
        metadata={}
        for key in ('inventory','previous_accounting','fixed_input_reference'):
            row=spec[key];raw,stamp=fixed_file(Path(row['path']),2097152)
            require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'closed metadata pin')
            require(raw==git('show',args.freeze+':'+str(Path(row['path']).relative_to(ROOT))),'metadata absent from new freeze')
            metadata[key]=decode(raw);source_raw[Path(row['path'])]=(raw,stamp)
        ledger=metadata['previous_accounting']
        require(ledger['passed'] is True and ledger['activity_passed'] is False
            and type(spec['previous_accounting']['expected_engineering_cumulative_seconds']) is str
            and ledger['engineering_cumulative_seconds']==spec['previous_accounting']['expected_engineering_cumulative_seconds'],'actual closed FAIL/accounting differs')
        refs=metadata['fixed_input_reference']
        require(refs['evidence_freeze']==ORIGINAL_FREEZE
            and [x['original_path'] for x in refs['inputs']]==list(map(str,INPUT_PATHS)),'fixed archived reference identity')
        require(all(old['original_bytes']==new['expected_bytes'] and old['original_sha256']==new['expected_sha256']
            for old,new in zip(refs['inputs'],spec['inputs'])),'reference/spec original pins differ')
        entries=metadata['inventory']['entries'];contents=[]
        def note_read(count):
            if count is None:result['raw_input_bytes_read_known']=False
            else:result['raw_input_bytes_read']+=count
        for row,reference in zip(spec['inputs'],refs['inputs']):
            require(time.monotonic_ns()-began<60*10**9,'work deadline before original open')
            match=[x for x in entries if x.get('original')==row['path']]
            require(len(match)==1 and match[0]['original_bytes']==row['expected_bytes'] and match[0]['original_sha256']==row['expected_sha256'],'exact original inventory membership')
            raw,stamp=fixed_file(Path(row['path']),row['max_encoded_bytes'],note_read)
            saved=match[0]['source_stat_before']
            require(match[0]['source_stat_stable'] is True and saved==match[0]['source_stat_after']
                and saved==reference['original_source_stat_before']==reference['original_source_stat_after']
                and stamp==tuple(saved[k[3:]] for k in STABLE),'inventory original identity differs')
            require(len(raw)==row['expected_bytes'] and sha(raw)==row['expected_sha256'],'original encoded bytes/SHA differ')
            contents.append(raw);observed[Path(row['path'])]=(raw,stamp)
        raw=contents[0];require(not raw or raw.endswith(b'\n'),'incomplete JSONL tail')
        lines=raw.splitlines(keepends=True)
        require(len(lines)<=64 and all(line.strip() and len(line)<=1048576 for line in lines),'bounded nonblank complete JSONL rows')
        transitions=[decode(line) for line in lines];summary=decode(contents[1])
        result.update(parse_errors=0,parsed_transition_rows=len(transitions),parsed_summary_objects=1)
        result.update(describe(transitions,summary,spec['identity']['epoch']))
        result.update(input_proofs=[{'path':str(p),'bytes':len(raw),'sha256':sha(raw)} for p,(raw,_) in observed.items()],
            transition_line_proofs=[{'line':i+1,'bytes':len(line),'sha256':sha(line)} for i,line in enumerate(lines)],
            source_bindings=bindings,spec_sha256=sha(spec_raw),execution_freeze=args.freeze)
    except Exception as error:
        result.update(passed=False,error=repr(error),description_status='INCOMPLETE')
    finally:
        try:
            for path,(_,stamp) in {**source_raw,**observed}.items():
                require(tuple(getattr(path.lstat(),k) for k in STABLE)==stamp,'bound file changed before verdict')
            if 'spec_raw' in locals():require(args.spec.read_bytes()==spec_raw,'spec changed before verdict')
        except Exception as error:result.update(passed=False,postcheck_error=repr(error),description_status='INCOMPLETE_POSTCHECK')
        result.update(actual_work_seconds=(time.monotonic_ns()-began)/1e9,
            interpretation_scope='sampled received conditions only; no native/physical replay')
        if time.monotonic_ns()-began>60*10**9:result.update(passed=False,deadline_exceeded=True,description_status='INCOMPLETE_WORK_CAP')
        raw=canonical(result)+b'\n'
        if len(raw)>LIMITS['max_output_bytes']:
            result={k:v for k,v in result.items() if k not in ('tb3_received_timeline','robot_rounds','initial_bank_and_joint_rank')}
            result.update(passed=False,description_status='INCOMPLETE_OUTPUT_CAP',omitted_result_bytes=len(raw));raw=canonical(result)+b'\n'
        require(len(raw)<=LIMITS['max_output_bytes'],'minimal failure output exceeds cap')
        with OUTPUT.open('xb') as stream:stream.write(raw)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
