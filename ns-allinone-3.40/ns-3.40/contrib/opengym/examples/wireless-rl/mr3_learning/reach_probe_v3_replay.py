"""Independent received ProbeV3 selector/lifecycle replay, never a plant oracle.

No producer, authority helper, ROS module or simulator is imported. Complete
profile-selected real inputs and the original scientific roles remain required.
"""
import hashlib
import json
import math
from pathlib import Path

PROFILE = 'mr3-reach-reset-outward-cancel-v3'
PROBE = 'mr3-p2a-reach-outward-cancel-v3'
SCHEMA = 'mr3-independent-received-probe-v3-replay-v1'
ROBOTS = ('tb1','tb2','tb3')
ROUNDS = ('initial','second')
WIRELESS = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
PURE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/'
SOURCE = WIRELESS+'mr3_learning/reach_probe_v3_replay.py'
SOURCE_PATHS = {SOURCE, WIRELESS+'mr3_learning/benchmark.py', WIRELESS+'mr3_learning/supervisor.py',
    'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py',
    *(PURE+n+'.py' for n in ('mr3_observation','mr3_activity','mr3_protocol','mr3_adapter'))}


def require(value, reason):
    if not value:raise ValueError(reason)


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def ns(value):
    require(finite(value) and value>=0,'invalid received clock')
    return round(value*1e9)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def equal(left,right,label):
    require(canonical(left)==canonical(right),label)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        value={}
        for k,v in pairs:
            require(k not in value,'duplicate JSON key');value[k]=v
        return value
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def check_snapshot(value,epoch):
    require(value['epoch']==epoch and type(value['sequence']) is int and value['sequence']>0,'snapshot identity')
    equal(value['digest'],digest(canonical({k:v for k,v in value.items() if k!='digest'})),'snapshot whole digest')
    ns(value['source_stamp']);ns(value['task_elapsed_sec'])
    require([r['name'] for r in value['robots']]==list(ROBOTS),'robot order')
    require(len(value['candidates'])==8 and len(value['per_robot_action_mask'])==3
        and all(len(m)==10 and all(type(v) is bool for v in m) for m in value['per_robot_action_mask'])
        and len(value['joint_action_mask'])==1000 and all(type(v) is bool for v in value['joint_action_mask']),
        'original mask dimensions/types')


def nonapproach(snapshot,choices):
    if all(c>=8 for c in choices):return True
    own=snapshot['robots']
    if any(r.get('fresh') is not True or r.get('valid') is not True
        or not all(finite(r.get(k)) for k in ('x','y')) for r in own):return False
    for i,c in enumerate(choices):
        if c>=8:continue
        target=snapshot['candidates'][c]
        if not all(finite(target.get(k)) for k in ('x','y')):return False
        gx,gy=target['x']-own[i]['x'],target['y']-own[i]['y'];length=math.hypot(gx,gy)
        if not finite(length) or length<=0:return False
        for j,peer in enumerate(own):
            if i==j:continue
            px,py=peer['x']-own[i]['x'],peer['y']-own[i]['y'];den=length*math.hypot(px,py);dot=gx*px+gy*py
            if not all(finite(v) for v in (den,dot)) or den<=0 or -dot/den<0:return False
    return True


def observe(snapshot,rounds):
    """Only received same-owner observations can capture or close a lifecycle."""
    now,task=ns(snapshot['source_stamp']),ns(snapshot['task_elapsed_sec'])
    for rid in ROUNDS:
        for robot in snapshot['robots']:
            saved=rounds[rid][robot['name']];nav=robot['navigation'];activity=robot['activity']
            if 'goal_id' not in saved:continue
            same=nav.get('goal_id')==saved['goal_id'];accepted=nav.get('accepted_at')
            confirmed=(same and nav.get('owned') is True and nav.get('phase') in ('active','canceling')
                and finite(accepted) and accepted<=snapshot['source_stamp']
                and type(nav.get('accepted_goal_count')) is int and nav['accepted_goal_count']>0)
            if confirmed:
                stamp=ns(accepted)
                require(finite(nav.get('commitment_until')) and ns(nav['commitment_until'])==stamp+5*10**9,'original five-second commitment differs')
                require(stamp>=saved['goal_created_ns'],'acceptance before submitted goal')
                require(stamp-(now-task)<=(2 if rid=='initial' else 20)*10**9,'acceptance outside bounded opportunity')
                require('accepted_at_ns' not in saved or saved['accepted_at_ns']==stamp,'accepted time changed')
                saved.setdefault('accepted_at_ns',stamp);saved.setdefault('accepted_observed_ns',now)
            path,source=activity.get('estimated_path_m'),activity.get('last_odom_source_stamp')
            capture=(saved.get('baseline_capture_count')==0 and same and nav.get('owned') is True
                and nav.get('phase')=='active' and 'accepted_at_ns' in saved
                and robot.get('fresh') is True and robot.get('valid') is True
                and activity.get('epoch')==snapshot['epoch']
                and type(activity.get('state_sequence')) is int and activity['state_sequence']>=0
                and activity.get('path_observation_complete') is True and finite(path) and path>=0
                and finite(source) and 0<=source<=snapshot['source_stamp'] and saved['accepted_at_ns']<=ns(source))
            if capture:
                saved.update(baseline_path_m=path,baseline_capture_count=1,baseline_epoch=snapshot['epoch'],
                    baseline_observed_ns=now,baseline_path_source_ns=ns(source),
                    baseline_snapshot_sequence=snapshot['sequence'],baseline_snapshot_digest=snapshot['digest'],
                    baseline_activity_state_sequence=activity['state_sequence'])
            if same and nav.get('cancel_requested') is True and nav.get('stop_reason')=='wait' and 'wait_command_id' in saved:
                saved.setdefault('cancel_request_observed_ns',now)
            if nav.get('last_goal_id')==saved['goal_id'] and nav.get('last_terminal') is not None and 'cancel_terminal_observed_ns' not in saved:
                require(nav['last_terminal']=='CANCELED' and 'wait_command_id' in saved
                    and 'accepted_at_ns' in saved and nav.get('stop_reason')=='wait',
                    'natural/unsolicited terminal is not stimulus cancel coverage')
                if nav.get('phase')=='idle' and nav.get('owned') is False:saved['cancel_terminal_observed_ns']=now
            if 'cancel_terminal_observed_ns' in saved and 'handoff_observed_ns' not in saved:
                stamp=robot.get('odom_source_stamp');speed=robot.get('v');rest=saved.setdefault('rest_source_ns',[])
                good=(robot.get('fresh') is True and robot.get('valid') is True and finite(stamp)
                    and 0<=stamp<=snapshot['source_stamp'] and finite(speed) and abs(speed)<=.01
                    and nav.get('phase')=='idle' and nav.get('owned') is False and nav.get('last_goal_id')==saved['goal_id'])
                if not good:rest.clear()
                elif not rest or ns(stamp)>rest[-1]:rest.append(ns(stamp));del rest[:-3]
                if len(rest)==3 and now-saved['cancel_terminal_observed_ns']>=3*10**9:saved['handoff_observed_ns']=now


def choose(snapshot,rounds,references):
    """Recompute the original masks, nonapproach subset and unchanged v2 rank."""
    now,task=ns(snapshot['source_stamp']),ns(snapshot['task_elapsed_sec'])
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
                if snapshot['per_robot_action_mask'][i][c] and all(finite(v) for v in (target['x'],target['y'],r['x'],r['y'],distance)) and distance>0:
                    eligible.append(c)
        admitted[name]=eligible;desired.append(tuple(eligible)+(8,))
    def choices(a):return (a//100,a//10%10,a%10)
    legal=[a for a,v in enumerate(snapshot['joint_action_mask']) if v is True
        and all(c in desired[i] for i,c in enumerate(choices(a))) and nonapproach(snapshot,choices(a))]
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
        cs=choices(a);margins=[];paths=0.;goals=0
        for i,c in enumerate(cs):
            if c>=8:continue
            goals+=1;own=snapshot['robots'][i];target=snapshot['candidates'][c];paths+=target['path_distances_m'][i]
            gx,gy=target['x']-own['x'],target['y']-own['y'];length=math.hypot(gx,gy);peer_margins=[]
            for j,peer in enumerate(snapshot['robots']):
                if i==j:continue
                px,py=peer['x']-own['x'],peer['y']-own['y'];den=length*math.hypot(px,py)
                peer_margins.append(-(gx*px+gy*py)/den if den else -1.)
            margins.append(min(peer_margins,default=-1.))
        return (-goals,-len(reverse(a)) if rid=='second' else 0,-min(margins,default=-1.),-sum(margins),-paths,a)
    action=min(legal,key=rank);cs=choices(action)
    request=dict(epoch=snapshot['epoch'],observation_sequence=snapshot['sequence'],observation_digest=snapshot['digest'],
        round=rid,task_elapsed_sec=snapshot['task_elapsed_sec'],clock_ns=now,action=action,reasons=reasons,
        submitted_activity={r['name']:dict(r['activity']) for r in snapshot['robots']},
        goal_robots=[ROBOTS[i] for i,c in enumerate(cs) if c<8],wait_robots=[ROBOTS[i] for i,c in enumerate(cs) if c==9],
        eligible_goal_candidates=admitted,
        scope='planned input only; no native cancel or physical credit')
    goal_note=None
    if request['goal_robots']:
        goal_note=dict(task_elapsed_sec=snapshot['task_elapsed_sec'],snapshot_sequence=snapshot['sequence'],stage=rid+'_goal',
            action=action,selected_reverse_robots=reverse(action),
            scope='original legal nonapproach stimulus subset; not actor availability or physical proof')
    return request,goal_note


def consume(request,info,rounds,epoch):
    require(info.get('action_submitted',True) is True,'unsubmitted action cannot qualify complete32 stimulus')
    command=info['command'];require(type(command) is dict and type(command['command_id']) is int and command['command_id']>0,'real returned command required')
    for k in ('epoch','observation_sequence','observation_digest','action'):
        require(type(command[k]) is type(request[k]) and command[k]==request[k],'command/previous snapshot association')
    require(ns(command['created_at'])==request['clock_ns'] and ns(command['expires_at'])==request['clock_ns']+2*10**9,'command source/expiry')
    for name in request['goal_robots']:
        saved=rounds[request['round']][name];require('goal_command_id' not in saved,'round GOAL retry')
        saved.update(goal_command_id=command['command_id'],goal_id=epoch+':'+name+':'+str(command['command_id']),
            goal_created_ns=request['clock_ns'],submitted_activity=dict(request['submitted_activity'][name]),baseline_capture_count=0)
    for name in request['wait_robots']:
        if request['reasons'].get(name)!='moving_owned_first_legal_wait':continue
        saved=rounds[request['round']][name];require('wait_command_id' not in saved,'round science WAIT retry')
        require(request['task_elapsed_sec']<=(10 if request['round']=='initial' else 28),'moving WAIT outside bounded opportunity')
        saved.update(wait_command_id=command['command_id'],wait_submitted_ns=request['clock_ns'])


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
    return dict(epoch=epoch,rounds=rounds,decisions=decisions,coverage_failures=[],last_clock_ns=ns(last['source_stamp']),
        pending_submission=None,coverage_passed=True,
        coverage_scope='received accepted/cancelled lifecycle only; independent native and physical gates required'),refs,goals


def replay_episode(transitions,diagnostics,*,epoch):
    expected,refs,goals=reconstruct(transitions,epoch)
    require(type(diagnostics) is dict and 'reach_v3_stimulus' in diagnostics
        and not any(k in diagnostics for k in ('reach_v2_stimulus','v4_stimulus','reach_masked_cancel_v1_stimulus')),'explicit v3 diagnostics required')
    for rid in ROUNDS:
        for name,saved in expected['rounds'][rid].items():
            required={'goal_command_id','accepted_at_ns','wait_command_id','cancel_terminal_observed_ns'}
            require(required<=saved.keys() and saved.get('baseline_capture_count')==1
                and len(saved.get('rest_source_ns',[]))==3
                and (rid!='initial' or 'handoff_observed_ns' in saved),'incomplete two-round received stimulus')
    equal(diagnostics['reach_v3_stimulus'],expected,'persisted v3 lifecycle/request/baseline differs from independent replay')
    equal(diagnostics.get('reference_turn_samples'),refs,'reference turn samples differ')
    equal(diagnostics.get('goal_decisions'),goals,'GOAL selection notes differ')
    return dict(schema=SCHEMA,profile=PROFILE,probe_version=PROBE,passed=True,epoch=epoch,
        real_steps=32,robot_rounds=6,goal_submissions=6,moving_WAIT_submissions=6,
        baseline_captures=6,original_rank_and_masks_replayed=True,accepted_path_baselines_replayed=True,
        original_accept_WAIT_windows_preserved=True,three_rest_and_initial_handoff_replayed=True,
        received_rounds=expected['rounds'],final_observed_clock_ns=expected['last_clock_ns'],producer_imported_as_oracle=False,native_physical_or_task_credit=False)


class Inputs:
    def __init__(self):self.bindings={};self.stats={}
    @staticmethod
    def stamp(path):
        s=path.stat();return (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    def read(self,path,rows=False):
        path=Path(path);before=self.stamp(path);raw=path.read_bytes();require(before==self.stamp(path),'probe input changed while read')
        proof={'bytes':len(raw),'sha256':digest(raw)}
        require(self.bindings.setdefault(str(path.resolve()),proof)==proof,'probe input changed between reads')
        self.stats[path]=before
        if rows:
            require(not raw or raw.endswith(b'\n'),'incomplete JSONL tail')
            return [parse(line) for line in raw.splitlines() if line.strip()]
        return parse(raw)
    def finish(self):require(all(self.stamp(p)==s for p,s in self.stats.items()),'probe input changed before verdict')


def replay_stage(directory,freeze):
    """Complete actual selected probe episodes; unchanged physical roles follow."""
    directory=Path(directory);inputs=Inputs();meta=inputs.read(directory/'benchmark_metadata.json');summary=inputs.read(directory/'benchmark_summary.json')
    for value in (meta,summary):
        require(value.get('freeze')==freeze and value.get('safety_contract')=='mr3-reach-v1'
            and value.get('preparation_probe_version')==PROBE and value.get('preparation_motion_probe') is True
            and type(value.get('workers')) is int and value['workers'] in (1,2)
            and type(value.get('steps_per_episode')) is int and value['steps_per_episode']==32,'actual v3 benchmark metadata')
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
                    and actual.get('safety_contract')=='mr3-reach-v1' and actual.get('preparation_probe_version')==PROBE,'actual worker/supervisor v3 pair')
            proof=replay_episode(inputs.read(ep/'transitions.jsonl',rows=True),declared['preparation_probe_diagnostics'],epoch=epoch)
            proof.update(directory=str(ep.resolve()),helper_sha256=digest(Path(__file__).read_bytes()))
            episodes.append(proof)
    require(set(directory.glob('worker*/episode*/metadata.json'))==expected_paths,'extra/missing actual probe episode')
    inputs.finish()
    return dict(schema=SCHEMA,profile=PROFILE,probe_version=PROBE,freeze=freeze,passed=True,
        episodes=episodes,bindings=inputs.bindings,helper_sha256=digest(Path(__file__).read_bytes()),
        producer_imported_as_oracle=False,native_physical_or_task_credit=False)


def require_stage_proof(proof,*,freeze,episodes,helper_sha256):
    require(type(proof) is dict and proof.get('schema')==SCHEMA and proof.get('profile')==PROFILE
        and proof.get('probe_version')==PROBE and proof.get('freeze')==freeze and proof.get('passed') is True
        and proof.get('producer_imported_as_oracle') is False and proof.get('helper_sha256')==helper_sha256
        and type(proof.get('episodes')) is list and len(proof['episodes'])==episodes,'missing substantive independent v3 stage replay')
    identities=set()
    for row in proof['episodes']:
        require(row.get('schema')==SCHEMA and row.get('profile')==PROFILE and row.get('probe_version')==PROBE
            and row.get('passed') is True and row.get('helper_sha256')==helper_sha256
            and all(type(row.get(k)) is int and row[k]==v for k,v in {'real_steps':32,'robot_rounds':6,'goal_submissions':6,'moving_WAIT_submissions':6,'baseline_captures':6}.items())
            and all(row.get(k) is True for k in ('original_rank_and_masks_replayed','accepted_path_baselines_replayed','original_accept_WAIT_windows_preserved','three_rest_and_initial_handoff_replayed')),
            'incomplete independent v3 episode replay')
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
        identity=(row['directory'],row['epoch']);require(identity not in identities,'duplicate v3 episode');identities.add(identity)
    return identities


def verify_stage_inputs(proof):
    require(type(proof.get('bindings')) is dict and proof['bindings'],'missing v3 input bindings')
    for name,row in proof['bindings'].items():
        raw=Path(name).read_bytes()
        require(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'v3 input changed before outer verdict')
