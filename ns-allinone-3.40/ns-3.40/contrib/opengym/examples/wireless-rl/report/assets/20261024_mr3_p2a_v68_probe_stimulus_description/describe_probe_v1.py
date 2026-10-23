"""Fixed two-input received stimulus description; no native/scientific verdict."""
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
A = W/'report/assets/20261024_mr3_p2a_v68_probe_stimulus_description'
RUN = ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v67/mr3_p2a_reach_v67_interface'
INPUT_PATHS = (RUN/'worker0/episode001_open_101/transitions.jsonl', RUN/'benchmark_summary.json')
OUTPUT = Path('/tmp/mr3_p2a_v68_probe_stimulus_description_v1.json')
ROBOTS = ('tb1', 'tb2', 'tb3')
ROUNDS = ('initial', 'second')
PROBE = 'mr3-p2a-reach-outward-cancel-v2'
STABLE = ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
INTERPRETATION_SOURCES = {'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/benchmark.py': {'bytes': 75476, 'sha256': '644dbf45eb64c8a27c7ed02788973db9a48a144f3edc9ed383c4f34119988e33'}, 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/supervisor.py': {'bytes': 29590, 'sha256': '7cf7f5fc792cfab0cefe6171f272168e20253a178528ff6eac8b600b1b8afde0'}, 'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py': {'bytes': 108943, 'sha256': '24df8be9bacc76df53ba5f23959d4d81db09dcebb3b38d92a2d66a46fdd8777d'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py': {'bytes': 62388, 'sha256': '57542e09c126461db99e47e8c5125baa610aed672c996d07f4422653ca7a34a8'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py': {'bytes': 18491, 'sha256': '5a2b90efd162b19a35964750002fe549413fec6e07f9679ea611d3fe6b1e4ada'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py': {'bytes': 54797, 'sha256': '5709af2e31f45691d05034375b43ef4ca873c427ba3579e0944b3f0556fa83f1'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_activity.py': {'bytes': 6162, 'sha256': '7af918d75c05b6f8fb1a65899e43aad11a315640e8b00fdb589c31f693ad696e'}}


def require(value, message):
    if not value:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def ns(value):
    require(finite(value) and value >= 0, 'invalid producer clock')
    return round(value*1e9)  # Original producer conversion, no new epsilon.


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
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


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
    require(len({cmd['command_id'] for _,cmd,_ in out})==expected_steps,'duplicate command id')
    return out,snapshots[-1]


def observe(snapshot, state):
    now,task=ns(snapshot['source_stamp']),ns(snapshot['task_elapsed_sec'])
    for round_id in ROUNDS:
        for robot in snapshot['robots']:
            nav=robot['navigation'];saved=state[round_id][robot['name']]
            if 'goal_id' not in saved:continue
            same=nav.get('goal_id')==saved['goal_id'];accepted=nav.get('accepted_at')
            if (same and nav.get('owned') is True and nav.get('phase') in ('active','canceling')
                    and finite(accepted) and accepted<=snapshot['source_stamp']
                    and type(nav.get('accepted_goal_count')) is int and nav['accepted_goal_count']>0):
                accepted_ns=ns(accepted)
                require('accepted_at_ns' not in saved or saved['accepted_at_ns']==accepted_ns,'accepted time changed')
                saved.setdefault('accepted_at_ns',accepted_ns);saved.setdefault('accepted_observed_ns',now)
            if same and nav.get('cancel_requested') is True and nav.get('stop_reason')=='wait' and 'wait_command_id' in saved:
                saved.setdefault('cancel_request_observed_ns',now)
            if (nav.get('last_goal_id')==saved['goal_id'] and nav.get('last_terminal')=='CANCELED'
                    and 'wait_command_id' in saved and 'accepted_at_ns' in saved
                    and nav.get('stop_reason')=='wait' and nav.get('phase')=='idle' and nav.get('owned') is False):
                saved.setdefault('cancel_terminal_observed_ns',now)
            if 'cancel_terminal_observed_ns' in saved and 'handoff_observed_ns' not in saved:
                rest=saved.setdefault('rest_source_ns',[]);stamp=robot.get('odom_source_stamp');v=robot.get('v')
                good=(robot.get('fresh') is True and robot.get('valid') is True and finite(stamp)
                    and 0<=stamp<=snapshot['source_stamp'] and finite(v) and abs(v)<=.01
                    and nav.get('phase')=='idle' and nav.get('owned') is False
                    and nav.get('last_goal_id')==saved['goal_id'])
                if not good:rest.clear()
                elif not rest or ns(stamp)>rest[-1]:rest.append(ns(stamp));del rest[:-3]
                if len(rest)==3 and now-saved['cancel_terminal_observed_ns']>=3*10**9:
                    saved['handoff_observed_ns']=now


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


def predicates(snapshot, state, planned):
    task=ns(snapshot['task_elapsed_sec']);round_id='initial' if task<13*10**9 else 'second'
    window=task<1500000000 or 13*10**9<=task<20*10**9
    cleanup=10*10**9<=task<13*10**9 or task>=28*10**9
    desired=[];records=[];eligibles={}
    for i,robot in enumerate(snapshot['robots']):
        name=robot['name'];nav=robot['navigation'];saved=state[round_id][name];activity=robot['activity'];path=activity.get('estimated_path_m')
        common={'goal_window':window,'no_goal_command':'goal_command_id' not in saved,
            'idle':nav.get('phase')=='idle','unowned':nav.get('owned') is False,
            'fresh':robot.get('fresh') is True,'valid':robot.get('valid') is True,
            'path_finite':finite(path),'path_observation_complete':activity.get('path_observation_complete') is True,
            'initial_handoff':round_id=='initial' or 'handoff_observed_ns' in state['initial'][name]}
        moving={'fresh':common['fresh'],'valid':common['valid'],'active':nav.get('phase')=='active',
            'owned':nav.get('owned') is True,'same_saved_goal':'goal_id' in saved and nav.get('goal_id')==saved['goal_id'],
            'accepted_observed':'accepted_at_ns' in saved,'forward_speed':finite(robot.get('v')) and robot['v']>=.08,
            'path_complete':common['path_observation_complete'],
            'path_delta':finite(path) and finite(saved.get('baseline_path_m')) and path-saved['baseline_path_m']>=.05,
            'first_scientific_wait':'wait_command_id' not in saved,'original_wait_mask':snapshot['per_robot_action_mask'][i][9]}
        if all(moving.values()):mode='moving_owned_first_legal_wait';want=(9,)
        elif cleanup and snapshot['per_robot_action_mask'][i][9]:mode='bounded_cleanup_wait_no_credit';want=(9,)
        else:mode='eligible_goal_or_keep';want=None
        candidate_rows=[];eligible=[]
        for choice,candidate in enumerate(snapshot['candidates']):
            distance=candidate['path_distances_m'][i]
            coords=all(finite(v) for v in (candidate.get('x'),candidate.get('y'),robot.get('x'),robot.get('y')))
            endpoint=math.hypot(candidate['x']-robot['x'],candidate['y']-robot['y']) if coords else None
            checks={'original_mask':snapshot['per_robot_action_mask'][i][choice],
                'coordinates_finite':coords,'path_distance_finite':finite(distance),'path_distance_positive':finite(distance) and distance>0,
                'endpoint_strictly_over_1_45':endpoint is not None and endpoint>1.45}
            admitted=all(common.values()) and all(checks.values()) and want is None
            if admitted:eligible.append(choice)
            candidate_rows.append({'index':choice,'x':present(candidate,'x'),'y':present(candidate,'y'),
                'path_distance':distance,'valid':present(candidate,'valid'),'reachable':present(candidate,'reachable'),
                'endpoint_distance_m':endpoint,'checks':checks,'eligible':admitted,'feasible_joint_count':0})
        if want is None:want=tuple(eligible)+(8,);eligibles[name]=eligible
        desired.append(want)
        raw=planned.get('eligible_long_goal_candidates')
        require(type(raw) is dict,'summary eligible candidate map')
        records.append({'robot':name,'mode':mode,'GOAL_common':common,'moving_WAIT':moving,
            'values':{k:present(robot,k) for k in ('x','y','v','w','fresh','valid','odom_source_stamp')},
            'navigation':{k:present(nav,k) for k in ('phase','owned','goal_id','accepted_at','accepted_goal_count','commitment_until','commitment_remaining_sec','cancel_requested','stop_reason','last_goal_id','last_terminal')},
            'activity':{k:present(activity,k) for k in ('estimated_path_m','path_observation_complete')},
            'mask_reasons':copy.deepcopy(snapshot.get('diagnostics',{}).get('mask_reasons',{})),
            'summary_eligible':present(raw,name),'reconstructed_eligible':present(eligibles,name),
            'summary_eligible_equal':present(raw,name)==present(eligibles,name),
            'candidates':candidate_rows,'blocked_GOAL_common':[k for k,v in common.items() if not v]})
    legal=[];mask_count=0;desired_count=0
    for action,valid in enumerate(snapshot['joint_action_mask']):
        if valid is not True:continue
        mask_count+=1;choices=(action//100,action//10%10,action%10)
        if not all(c in desired[i] for i,c in enumerate(choices)):continue
        desired_count+=1
        if not nonapproach(snapshot,choices):continue
        legal.append(action)
        for i,c in enumerate(choices):
            if c<8:records[i]['candidates'][c]['feasible_joint_count']+=1
    require(legal,'original filtered legal subset unavailable')
    return round_id,records,legal,{'original_joint_mask_count':mask_count,'desired_subset_count':desired_count,
        'nonapproaching_legal_count':len(legal),'submitted_action_in_filtered_subset':planned['action'] in legal}


def describe(transitions, summary, epoch, *, expected_steps=32):
    """Independent received-condition reconstruction; no producer/helper imports."""
    require(type(epoch) is str and epoch,'epoch required')
    require(summary.get('preparation_probe_version')==PROBE and summary.get('freeze')=='50c740a64754aaa2dc3f2707cf5b0159eb929a28'
            and summary.get('workers')==1 and summary.get('schedule')==[['open',101]],'fixed original benchmark identity')
    worker=summary['workers_results'];require(len(worker)==1 and worker[0]['worker_id']==0,'one fixed worker')
    episodes=worker[0]['episodes'];require(len(episodes)==1 and episodes[0]['epoch']==epoch,'one fixed episode')
    original=episodes[0]['preparation_probe_diagnostics']['reach_v2_stimulus']
    require(original['epoch']==epoch,'summary epoch')
    pairs,last=joined(transitions,original['decisions'],epoch,expected_steps)
    state={r:{n:{} for n in ROBOTS} for r in ROUNDS};decisions=[]
    for ordinal,(snapshot,command,planned) in enumerate(pairs):
        observe(snapshot,state)
        round_id,robots,legal,counts=predicates(snapshot,state,planned)
        require(command['action'] in legal,'submitted command outside original received-filter subset')
        choices=(command['action']//100,command['action']//10%10,command['action']%10)
        for i,(name,choice) in enumerate(zip(ROBOTS,choices)):
            saved=state[round_id][name]
            if choice<8:
                require('goal_command_id' not in saved,'repeated GOAL round')
                saved.update(goal_command_id=command['command_id'],goal_id=epoch+':'+name+':'+str(command['command_id']),
                    goal_created_ns=ns(snapshot['source_stamp']),baseline_path_m=snapshot['robots'][i]['activity']['estimated_path_m'])
            elif choice==9 and robots[i]['mode']=='moving_owned_first_legal_wait':
                require('wait_command_id' not in saved,'repeated scientific WAIT')
                saved.update(wait_command_id=command['command_id'],wait_submitted_ns=ns(snapshot['source_stamp']))
        decisions.append({'decision':ordinal,'previous_snapshot_line':ordinal+1,'step_line':ordinal+2,
            'snapshot_sequence':snapshot['sequence'],'snapshot_digest':snapshot['digest'],
            'source_stamp':snapshot['source_stamp'],'task_elapsed_sec':snapshot['task_elapsed_sec'],
            'round':round_id,'command':copy.deepcopy(command),'planned_reasons':copy.deepcopy(planned.get('reasons')),
            'joint':counts,'robots':robots})
    observe(last,state)
    rounds=[]
    for r in ROUNDS:
        for name in ROBOTS:
            saved=state[r][name];declared=original['rounds'][r][name]
            require(type(declared) is dict,'declared round object')
            needed=('goal_command_id','accepted_at_ns','wait_command_id','cancel_terminal_observed_ns')
            missing=[k for k in needed if k not in saved]
            if len(saved.get('rest_source_ns',[]))<3:missing.append('three_fresh_rest_observations')
            if r=='initial' and 'handoff_observed_ns' not in saved:missing.append('terminal_and_rest_handoff')
            keys=set(saved)|set(declared)
            rounds.append({'round':r,'robot':name,'reconstructed':copy.deepcopy(saved),'persisted':copy.deepcopy(declared),
                'field_comparison':{k:{'reconstructed':present(saved,k),'persisted':present(declared,k),
                    'equal':present(saved,k)==present(declared,k)} for k in sorted(keys)},
                'missing':missing,'downstream_not_triggered_without_GOAL':'goal_command_id' not in saved})
    return {'schema':'mr3-v68-fixed-received-stimulus-description-v1','passed':True,
        'passed_scope':'complete two-input descriptive joins and received-condition decomposition only',
        'original_activity_passed':summary.get('passed'),'original_FAIL_preserved':True,
        'epoch':epoch,'decisions':decisions,'robot_rounds':rounds,
        'persisted_round_fields_equal':all(c['equal'] for r in rounds for c in r['field_comparison'].values()),
        'summary_eligible_fields_equal':all(r['summary_eligible_equal'] for d in decisions for r in d['robots']),
        'persisted_coverage_failures':copy.deepcopy(original['coverage_failures']),
        'persisted_coverage_passed':present(original,'coverage_passed'),
        'final_observation':{'line':len(transitions),'sequence':last['sequence'],'source_stamp':last['source_stamp'],
            'task_elapsed_sec':last['task_elapsed_sec'],'no_extra_command':True},
        'root_cause':'UNKNOWN_BEYOND_RECORDED_RECEIVED_PREDICATES','native_or_physics_or_qualification_credit':False,
        'no_cross_process_wall_order_invented':True}


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


def validate_admission(spec, freeze):
    require(type(spec.get('admitted')) is bool and spec['admitted'] is True,'unadmitted description spec')
    require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}',freeze)
            and spec.get('execution_freeze')=='CLI_EXACT_PUSHED_FREEZE','execution freeze binding')
    require(type(spec['identity']['epoch']) is str and spec['identity']['epoch'],'missing fixed epoch')
    require([r['path'] for r in spec['inputs']]==list(map(str,INPUT_PATHS)),'only the two fixed original inputs')
    for i,row in enumerate(spec['inputs']):
        require(row['encoding']=='plain' and type(row['expected_bytes']) is int and row['expected_bytes']>=0
                and re.fullmatch('[0-9a-f]{64}',row['expected_sha256']),'missing original input pins')
        limit=(4194304,262144)[i]
        require(row['expected_bytes']<=row['max_encoded_bytes']==row['max_decoded_bytes']==limit,'fixed input cap')
    require(spec['aggregate_limits']=={'max_inputs':2,'max_encoded_bytes':4456448,'max_decoded_bytes':4456448,
        'max_output_bytes':1048576,'max_snapshot_rows':33,'max_candidate_predicate_rows':792,'max_robot_round_summaries':6},'fixed aggregate caps')
    require(spec['output']['path']==str(OUTPUT) and spec['output']['native_or_physics_or_qualification_credit'] is False,'fixed output scope')


def main(argv=None):
    began=time.monotonic_ns();identity=self_identity();actual_argv=list(sys.argv)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',required=True)
    parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    require(args.output==OUTPUT and not OUTPUT.exists(),'fixed exclusive output required')
    result={'schema':'mr3-v68-fixed-received-stimulus-description-v1','passed':False,'identity':identity,
        'actual_argv':actual_argv,'raw_input_bytes_read':0,'raw_input_bytes_read_known':True,'native_or_physics_or_qualification_credit':False}
    observed={};source_raw={}
    try:
        require(Path(__file__).resolve()==A/'describe_probe_v1.py' and args.spec==A/'description_spec_v1.json','canonical consumer/spec only')
        spec_raw,_=fixed_file(args.spec,262144);spec=decode(spec_raw);validate_admission(spec,args.freeze)
        git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,timeout=10)
        require(git('rev-parse','HEAD').decode().strip()==args.freeze==git('rev-parse','origin/main').decode().strip()
                and not git('status','--porcelain','--untracked-files=all'),'clean exact pushed freeze required')
        bindings=spec['source_bindings']
        actual_interpretation={r['path']:{'bytes':r['bytes'],'sha256':r['sha256']} for r in bindings if r['path'] in INTERPRETATION_SOURCES}
        require(actual_interpretation==INTERPRETATION_SOURCES,'exact seven interpretation sources absent/changed')
        require(len(bindings)==8 and len({r['path'] for r in bindings})==8,'consumer plus seven interpretation sources')
        for row in bindings:
            path=ROOT/row['path'];raw,stamp=fixed_file(path,1048576)
            require(len(raw)==row['bytes'] and sha(raw)==row['sha256'] and raw==git('show',args.freeze+':'+row['path']),'source pin/freeze')
            source_raw[path]=(raw,stamp)
        require(str((A/'describe_probe_v1.py').relative_to(ROOT)) in {r['path'] for r in bindings},'consumer source missing')
        require(spec_raw==git('show',args.freeze+':'+str(args.spec.relative_to(ROOT))),'spec itself absent from freeze')
        metadata={}
        for key in ('inventory','previous_accounting'):
            row=spec[key];raw,stamp=fixed_file(Path(row['path']),2097152)
            require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'closed metadata pin')
            require(raw==git('show',args.freeze+':'+str(Path(row['path']).relative_to(ROOT))),'metadata not in new freeze')
            metadata[key]=decode(raw);source_raw[Path(row['path'])]=(raw,stamp)
        ledger=metadata['previous_accounting']
        require(ledger['passed'] is True and ledger['activity_passed'] is False
                and ledger['engineering_cumulative_seconds']=='110187.6667339046018','closed original FAIL/account')
        entries=metadata['inventory']['entries']
        require(time.monotonic_ns()-began<60*10**9,'work deadline before raw open')
        contents=[]
        def note_raw_read(count):
            if count is None:result['raw_input_bytes_read_known']=False
            else:result['raw_input_bytes_read']+=count
        for row in spec['inputs']:
            matches=[r for r in entries if r.get('original')==row['path']]
            require(len(matches)==1 and matches[0]['original_bytes']==row['expected_bytes']
                    and matches[0]['original_sha256']==row['expected_sha256'],'original inventory exact membership')
            raw,stamp=fixed_file(Path(row['path']),row['max_encoded_bytes'],note_raw_read)
            expected_stamp=matches[0]['source_stat_before']
            require(matches[0]['source_stat_stable'] is True and expected_stamp==matches[0]['source_stat_after']
                    and stamp==tuple(expected_stamp[k[3:]] for k in STABLE),'original inventory saved identity differs')
            require(len(raw)==row['expected_bytes'] and sha(raw)==row['expected_sha256'],'original bytes changed')
            contents.append(raw);observed[Path(row['path'])]=(raw,stamp)
        raw=contents[0];require(not raw or raw.endswith(b'\n'),'incomplete JSONL tail')
        lines=raw.splitlines(keepends=True);require(len(lines)<=64 and all(line.strip() for line in lines),'JSONL row cap/empty line')
        transitions=[decode(line) for line in lines];summary=decode(contents[1])
        result.update(describe(transitions,summary,spec['identity']['epoch']))
        result.update(input_proofs=[{'path':str(path),'bytes':len(raw),'sha256':sha(raw)} for path,(raw,_) in observed.items()],
            transition_line_proofs=[{'line':i+1,'bytes':len(line),'sha256':sha(line)} for i,line in enumerate(lines)],
            source_bindings=bindings,spec_sha256=sha(spec_raw),execution_freeze=args.freeze)
    except Exception as error:
        result.update(passed=False,error=repr(error),description_status='INCOMPLETE')
    finally:
        # Recheck fingerprints; no second content consumption of either raw input.
        try:
            for path,(_,stamp) in {**source_raw,**observed}.items():
                require(tuple(getattr(path.lstat(),k) for k in STABLE)==stamp,'bound file changed before verdict')
            if 'spec_raw' in locals():require(args.spec.read_bytes()==spec_raw,'spec changed before verdict')
        except Exception as error:result.update(passed=False,postcheck_error=repr(error))
        result.update(actual_work_seconds=(time.monotonic_ns()-began)/1e9,
            interpretation_scope='received sampled conditions only; no native/physical replay')
        if time.monotonic_ns()-began>60*10**9:result.update(passed=False,deadline_exceeded=True)
        raw=canonical(result)+b'\n'
        if len(raw)>1048576:
            result={k:v for k,v in result.items() if k not in ('decisions','robot_rounds')}
            result.update(passed=False,description_status='INCOMPLETE_OUTPUT_CAP',omitted_result_bytes=len(raw))
            raw=canonical(result)+b'\n'
        with OUTPUT.open('xb') as stream:stream.write(raw)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
