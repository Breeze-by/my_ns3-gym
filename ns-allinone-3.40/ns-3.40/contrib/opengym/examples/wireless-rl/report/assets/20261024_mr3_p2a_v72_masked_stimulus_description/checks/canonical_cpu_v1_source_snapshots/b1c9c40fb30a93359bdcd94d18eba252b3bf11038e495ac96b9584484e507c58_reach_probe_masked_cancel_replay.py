"""Independent original-mask/long-path cancel stimulus replay; no producer oracle.

Common received lifecycle/schema/I/O primitives come from the independent V3
reader. Neither reader imports benchmark or a production authority helper.
"""
import math
from pathlib import Path
from . import reach_probe_v3_replay as lifecycle
from .reach_probe_v3_replay import (ROBOTS, ROUNDS, require, finite, ns, canonical,
    equal, digest, parse, check_snapshot, observe, consume, Inputs)

PROFILE = 'mr3-reach-reset-masked-cancel-v1'
PROBE = 'mr3-p2a-reach-masked-cancel-v1'
SCHEMA = 'mr3-independent-received-masked-cancel-replay-v1'
STATE_KEY = 'reach_masked_cancel_v1_stimulus'
GOAL_FILTER = 'original_per_robot_and_joint_masks_only_v1'
GOAL_RANK = 'goal_count_min_path_second_reverse_sum_path_action_v1'
SOURCE = lifecycle.WIRELESS+'mr3_learning/reach_probe_masked_cancel_replay.py'
SOURCE_PATHS = lifecycle.SOURCE_PATHS | {SOURCE}
RECEIPT_KEY = 'probe_masked_cancel_stimulus_replay'
QUALIFICATION_SCHEMA = 'mr3-independent-masked-cancel-qualification-v1'


def check_goal_data(snapshot):
    """A legal actor bit never becomes a silent missing/negative-path filter."""
    for i, own in enumerate(snapshot['robots']):
        for c, target in enumerate(snapshot['candidates']):
            if snapshot['per_robot_action_mask'][i][c] is not True:
                continue
            require(all(finite(own.get(k)) for k in ('x','y','yaw'))
                and all(finite(target.get(k)) for k in ('x','y')),
                'original-mask GOAL has invalid coordinates')
            distances=target.get('path_distances_m')
            require(type(distances) is list and len(distances)==3
                and finite(distances[i]) and distances[i]>=0,
                'original-mask GOAL has invalid path')


def choose(snapshot,rounds,references):
    """Use supplied original mask bits and independently replay the fixed path rank."""
    now,task=ns(snapshot['source_stamp']),ns(snapshot['task_elapsed_sec'])
    check_goal_data(snapshot)
    observe(snapshot,rounds)
    if task<10*10**9:
        for r in snapshot['robots']:
            if r.get('fresh') is True and finite(r.get('w')) and abs(r['w'])>=.1:
                references.setdefault(r['name'],dict(sign=math.copysign(1.,r['w']),w=r['w'],
                    snapshot_sequence=snapshot['sequence'],source_stamp=r.get('source_stamp'),odom_source_stamp=r.get('odom_source_stamp')))
    rid='initial' if task<13*10**9 else 'second';goal_window=task<1500000000 or 13*10**9<=task<20*10**9
    cleanup=10*10**9<=task<13*10**9 or task>=28*10**9;desired=[];reasons={};admitted={}
    for i,r in enumerate(snapshot['robots']):
        name=r['name'];saved=rounds[rid][name];nav=r['navigation'];path=r['activity'].get('estimated_path_m')
        moving=(r.get('fresh') is True and r.get('valid') is True and nav.get('phase')=='active'
            and nav.get('owned') is True and nav.get('goal_id')==saved.get('goal_id') and 'accepted_at_ns' in saved
            and finite(nav.get('commitment_until')) and ns(snapshot['source_stamp'])>=ns(nav['commitment_until'])
            and finite(r.get('v')) and r['v']>=.08 and r['activity'].get('path_observation_complete') is True
            and saved.get('baseline_capture_count')==1 and finite(saved.get('baseline_path_m'))
            and r['activity'].get('epoch')==saved.get('baseline_epoch')==snapshot['epoch']
            and finite(r['activity'].get('last_odom_source_stamp'))
            and 0<=r['activity']['last_odom_source_stamp']<=snapshot['source_stamp']
            and ns(r['activity']['last_odom_source_stamp'])>=saved['baseline_path_source_ns']
            and finite(path) and path-saved['baseline_path_m']>=.05)
        if moving and 'wait_command_id' not in saved and snapshot['per_robot_action_mask'][i][9]:
            desired.append((9,));reasons[name]='moving_owned_first_legal_wait';continue
        if cleanup and snapshot['per_robot_action_mask'][i][9]:
            desired.append((9,));reasons[name]='bounded_cleanup_wait_no_credit';continue
        eligible=[]
        if (goal_window and 'goal_command_id' not in saved and nav.get('phase')=='idle'
                and nav.get('owned') is False and r.get('fresh') is True and r.get('valid') is True
                and (rid=='initial' or 'handoff_observed_ns' in rounds['initial'][name])):
            for c,target in enumerate(snapshot['candidates']):
                distance=target['path_distances_m'][i]
                if snapshot['per_robot_action_mask'][i][c] is True:
                    eligible.append(c)
        admitted[name]=eligible;desired.append(tuple(eligible)+(8,))
    def choices(a):return (a//100,a//10%10,a%10)
    legal=[a for a,v in enumerate(snapshot['joint_action_mask']) if v is True
        and all(c in desired[i] and snapshot['per_robot_action_mask'][i][c] is True for i,c in enumerate(choices(a)))]
    require(legal,'no original legal stimulus joint action')
    def reverse(a):
        out=[]
        for i,c in enumerate(choices(a)):
            own=snapshot['robots'][i];ref=references.get(own['name'])
            if c>=8 or ref is None:continue
            target=snapshot['candidates'][c];angle=math.atan2(target['y']-own['y'],target['x']-own['x'])-own['yaw']
            if math.atan2(math.sin(angle),math.cos(angle))*ref['sign']<=-.25:out.append(own['name'])
        return out
    def rank(a):
        selected=[snapshot['candidates'][c]['path_distances_m'][i]
            for i,c in enumerate(choices(a)) if c<8]
        return (-len(selected),-min(selected,default=0.),
            -len(reverse(a)) if rid=='second' else 0,-sum(selected),a)
    action=min(legal,key=rank);cs=choices(action)
    request=dict(epoch=snapshot['epoch'],observation_sequence=snapshot['sequence'],observation_digest=snapshot['digest'],
        round=rid,task_elapsed_sec=snapshot['task_elapsed_sec'],clock_ns=now,action=action,reasons=reasons,
        submitted_activity={r['name']:dict(r['activity']) for r in snapshot['robots']},
        goal_robots=[ROBOTS[i] for i,c in enumerate(cs) if c<8],wait_robots=[ROBOTS[i] for i,c in enumerate(cs) if c==9],
        eligible_goal_candidates=admitted,goal_filter=GOAL_FILTER,goal_rank=GOAL_RANK,
        scope='planned input only; no native cancel or physical credit')
    goal_note=None
    if request['goal_robots']:
        goal_note=dict(task_elapsed_sec=snapshot['task_elapsed_sec'],snapshot_sequence=snapshot['sequence'],stage=rid+'_goal',
            action=action,selected_reverse_robots=reverse(action),goal_filter=GOAL_FILTER,goal_rank=GOAL_RANK,
            scope='original mask lifecycle stimulus subset; not actor availability or physical proof')
    return request,goal_note


def reconstruct(transitions,epoch):
    """Independent reconstruction before any persisted diagnostics are trusted."""
    require(type(epoch) is str and epoch and len(transitions)==33,'complete32 plus reset required')
    require(transitions[0]['kind']=='reset' and all(r['kind']=='step' for r in transitions[1:]),'transition order')
    for row in transitions:check_snapshot(row['snapshot'],epoch)
    require(ns(transitions[0]['snapshot']['task_elapsed_sec'])==0,'initial task boundary')
    rounds={r:{n:{} for n in ROBOTS} for r in ROUNDS};refs={};decisions=[];goals=[];commands=[]
    for i,row in enumerate(transitions[1:]):
        before=transitions[i]['snapshot'];after=row['snapshot']
        require(after['sequence']>before['sequence'] and ns(after['source_stamp'])-ns(before['source_stamp'])==10**9
            and ns(after['task_elapsed_sec'])==ns(before['task_elapsed_sec'])+10**9,'noncausal one-second step')
        request,note=choose(before,rounds,refs);consume(request,row['info'],rounds,epoch)
        decisions.append(request);commands.append(row['info']['command']['command_id'])
        if note is not None:goals.append(note)
    require(len(set(commands))==32 and commands==sorted(commands),'missing/reordered real command ids')
    last=transitions[-1]['snapshot'];require(ns(last['task_elapsed_sec'])==32*10**9,'exact32 final observation')
    choose(last,rounds,refs)  # Same observation frontier, deliberately no33rd command.
    return dict(epoch=epoch,goal_filter=GOAL_FILTER,goal_rank=GOAL_RANK,rounds=rounds,decisions=decisions,coverage_failures=[],last_clock_ns=ns(last['source_stamp']),
        pending_submission=None,coverage_passed=True,
        coverage_scope='received accepted/cancelled lifecycle only; independent native and physical gates required'),refs,goals


def replay_episode(transitions,diagnostics,*,epoch):
    expected,refs,goals=reconstruct(transitions,epoch)
    require(type(diagnostics) is dict and STATE_KEY in diagnostics
        and not any(k in diagnostics for k in ('reach_v2_stimulus','reach_v3_stimulus','reach_v4_stimulus','v4_stimulus')),'explicit masked-cancel diagnostics required')
    for rid in ROUNDS:
        for name,saved in expected['rounds'][rid].items():
            required={'goal_command_id','accepted_at_ns','wait_command_id','cancel_terminal_observed_ns'}
            require(required<=saved.keys() and saved.get('baseline_capture_count')==1
                and len(saved.get('rest_source_ns',[]))==3
                and (rid!='initial' or 'handoff_observed_ns' in saved),'incomplete two-round received stimulus')
    equal(diagnostics[STATE_KEY],expected,'persisted masked-cancel lifecycle/request/baseline differs from independent replay')
    equal(diagnostics.get('reference_turn_samples'),refs,'reference turn samples differ')
    equal(diagnostics.get('goal_decisions'),goals,'GOAL selection notes differ')
    return dict(schema=SCHEMA,profile=PROFILE,probe_version=PROBE,goal_filter=GOAL_FILTER,goal_rank=GOAL_RANK,passed=True,epoch=epoch,
        real_steps=32,robot_rounds=6,goal_submissions=6,moving_WAIT_submissions=6,
        baseline_captures=6,fixed_rank_and_original_masks_replayed=True,accepted_path_baselines_replayed=True,
        original_accept_WAIT_windows_preserved=True,three_rest_and_initial_handoff_replayed=True,
        received_rounds=expected['rounds'],final_observed_clock_ns=expected['last_clock_ns'],producer_imported_as_oracle=False,native_physical_or_task_credit=False)


def replay_stage(directory,freeze):
    """Complete actual selected probe episodes; unchanged physical roles follow."""
    directory=Path(directory);inputs=Inputs();meta=inputs.read(directory/'benchmark_metadata.json');summary=inputs.read(directory/'benchmark_summary.json')
    for value in (meta,summary):
        require(value.get('freeze')==freeze and value.get('safety_contract')=='mr3-reach-v1'
            and value.get('preparation_probe_version')==PROBE and value.get('preparation_motion_probe') is True
            and value.get('goal_filter')==GOAL_FILTER and value.get('goal_rank')==GOAL_RANK
            and type(value.get('workers')) is int and value['workers'] in (1,2)
            and type(value.get('steps_per_episode')) is int and value['steps_per_episode']==32,'actual masked-cancel benchmark metadata')
    require(summary.get('passed') is True and summary['workers']==meta['workers']
        and summary['steps_per_episode']==meta['steps_per_episode'],'native producer did not actually complete/metadata differs')
    schedule=[['open',101]] if meta['workers']==1 else [['open',101],['open',101],['rooms',101],['corridors',101]]
    require(meta['schedule']==summary['schedule']==schedule,'fixed probe schedule')
    workers=summary['workers_results'];require(len(workers)==meta['workers'] and {w['worker_id'] for w in workers}==set(range(meta['workers'])),'actual worker set')
    episodes=[];expected_paths=set()
    for worker in workers:
        require(worker.get('error') is None and not worker.get('cleanup_error') and len(worker['episodes'])==len(schedule),'native worker failure')
        for i,(declared,(scene,seed)) in enumerate(zip(worker['episodes'],schedule),1):
            ep=directory/f"worker{worker['worker_id']}"/f'episode{i:03d}_{scene}_{seed}'
            require(Path(declared['output_directory']).resolve()==ep.resolve() and declared['scene']==scene and declared['seed']==seed
                and declared['transitions']==32,'actual episode identity/steps')
            epoch=declared['epoch'];expected_paths.add(ep/'metadata.json')
            for name in ('metadata.json','supervisor_metadata.json'):
                actual=inputs.read(ep/name)
                require(actual.get('epoch')==epoch and (name=='supervisor_metadata.json' or actual.get('freeze')==freeze)
                    and actual.get('freeze',freeze)==freeze
                    and actual.get('safety_contract')=='mr3-reach-v1' and actual.get('preparation_probe_version')==PROBE
                    and actual.get('goal_filter')==GOAL_FILTER and actual.get('goal_rank')==GOAL_RANK,'actual worker/supervisor masked-cancel pair')
            proof=replay_episode(inputs.read(ep/'transitions.jsonl',rows=True),declared['preparation_probe_diagnostics'],epoch=epoch)
            proof.update(directory=str(ep.resolve()),helper_sha256=digest(Path(__file__).read_bytes()))
            episodes.append(proof)
    require(set(directory.glob('worker*/episode*/metadata.json'))==expected_paths,'extra/missing actual probe episode')
    inputs.finish()
    return dict(schema=SCHEMA,profile=PROFILE,probe_version=PROBE,goal_filter=GOAL_FILTER,goal_rank=GOAL_RANK,freeze=freeze,passed=True,
        episodes=episodes,bindings=inputs.bindings,helper_sha256=digest(Path(__file__).read_bytes()),
        producer_imported_as_oracle=False,native_physical_or_task_credit=False)


def require_stage_proof(proof,*,freeze,episodes,helper_sha256):
    require(type(proof) is dict and proof.get('schema')==SCHEMA and proof.get('profile')==PROFILE
        and proof.get('probe_version')==PROBE and proof.get('goal_filter')==GOAL_FILTER and proof.get('goal_rank')==GOAL_RANK and proof.get('freeze')==freeze and proof.get('passed') is True
        and proof.get('producer_imported_as_oracle') is False and proof.get('helper_sha256')==helper_sha256
        and type(proof.get('episodes')) is list and len(proof['episodes'])==episodes,'missing substantive independent masked-cancel stage replay')
    identities=set()
    for row in proof['episodes']:
        require(row.get('schema')==SCHEMA and row.get('profile')==PROFILE and row.get('probe_version')==PROBE
            and row.get('passed') is True and row.get('goal_filter')==GOAL_FILTER and row.get('goal_rank')==GOAL_RANK and row.get('helper_sha256')==helper_sha256
            and all(type(row.get(k)) is int and row[k]==v for k,v in {'real_steps':32,'robot_rounds':6,'goal_submissions':6,'moving_WAIT_submissions':6,'baseline_captures':6}.items())
            and all(row.get(k) is True for k in ('fixed_rank_and_original_masks_replayed','accepted_path_baselines_replayed','original_accept_WAIT_windows_preserved','three_rest_and_initial_handoff_replayed')),
            'incomplete independent masked-cancel episode replay')
        rounds=row['received_rounds'];require(set(rounds)==set(ROUNDS),'missing received rounds')
        goal_ids=set()
        for rid in ROUNDS:
            require(set(rounds[rid])==set(ROBOTS),'missing received robot')
            for robot,saved in rounds[rid].items():
                require(type(saved.get('baseline_capture_count')) is int and saved['baseline_capture_count']==1
                    and finite(saved.get('baseline_path_m')) and saved['baseline_path_m']>=0
                    and saved.get('baseline_epoch')==row['epoch'],'invalid captured path baseline')
                clocks=[saved[k] for k in ('goal_created_ns','accepted_at_ns','baseline_path_source_ns',
                    'baseline_observed_ns','wait_submitted_ns','cancel_terminal_observed_ns')]
                require(all(type(v) is int and v>=0 for v in clocks) and clocks==sorted(clocks),
                        'received probe causal order differs')
                require(type(saved.get('goal_command_id')) is int and type(saved.get('wait_command_id')) is int
                    and saved['goal_command_id']<saved['wait_command_id']
                    and saved.get('goal_id')==row['epoch']+':'+robot+':'+str(saved['goal_command_id']),
                    'received probe command identity differs')
                rest=saved['rest_source_ns'];require(len(rest)==3 and len(set(rest))==3
                    and all(type(v) is int and 0<=v<=row['final_observed_clock_ns'] for v in rest)
                    and rest==sorted(rest),'missing distinct received rest sources')
                if rid=='initial':require(saved['handoff_observed_ns']-saved['cancel_terminal_observed_ns']>=3*10**9,'early handoff')
                goal_ids.add(saved['goal_id'])
        require(len(goal_ids)==6,'missing six real GOAL identities')
        identity=(row['directory'],row['epoch']);require(identity not in identities,'duplicate masked-cancel episode');identities.add(identity)
    return identities


def verify_stage_inputs(proof):
    require(type(proof.get('bindings')) is dict and proof['bindings'],'missing masked-cancel input bindings')
    for name,row in proof['bindings'].items():
        raw=Path(name).read_bytes()
        require(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'masked-cancel input changed before outer verdict')
