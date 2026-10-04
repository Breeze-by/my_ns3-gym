#!/usr/bin/env python3
"""Audit the complete fixed P3B.5 task/ledger/graph evidence, including failures."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import shlex
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from check_p3a6_gate import Snapshot, episode_ok as p3a_episode_ok, same_candidate
from run_p2d_baseline import file_digest
from run_p3b5_tasks import tdi
from multi_robot_exploration.bypass_audit import runtime_violations, source_violations
from multi_robot_exploration.fault_model import CHARGE_REQUEST_TTL_SEC

CORE_KEYS=('gateway_message','launch','exploration_source','merge_map_source','robot_params','slam_source','slam_config','bypass_manifest','smoke_runner')

def load(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def native_completion_ok(result):
    """Require the new cohort's independent native hold, never backfill P3A."""
    assert result['schema_version'] >= 9
    proof = result['native_rally_hold_proof']
    assert proof and proof['clock_basis'] == 'headerless_model_states_observer_sim_time'
    assert proof['required_robot_names'] == sorted(result['required_robot_names'])
    assert proof['sample_count'] >= 2
    start, end = (proof[k] for k in ('start_observer_sim_time_sec', 'end_observer_sim_time_sec'))
    duration = proof['observed_duration_sec']
    assert math.isfinite(start) and math.isfinite(end) and math.isfinite(duration)
    assert abs(end - start - duration) <= 1e-6 and duration >= result['rally_hold_sec'] == 5
    assert 0 <= proof['maximum_observation_gap_sec'] <= proof['maximum_allowed_observation_gap_sec'] == 2
    assert abs(end - result['start_sim_time_sec'] - result['completion_time_sec']) <= 1e-6
    assert 0 <= result['coordinator_completion_time_sec'] <= result['completion_time_sec'] <= 300
    for field, limit in (('maximum_position_error_m', .35), ('maximum_linear_speed_mps', .05),
                         ('maximum_angular_speed_radps', .1)):
        assert math.isfinite(proof[field]) and 0 <= proof[field] <= limit

def episode_ok(result):
    p3a_episode_ok(result)
    native_completion_ok(result)

def ledger_audit(path):
    """Verify attempt causality and receiver TTL/version semantics from raw events."""
    counts=Counter(); last={}; minimum_delay=None; maximum_clock_deferral=0.; waits=[]; waiting=None
    for line in path.open():
        e=json.loads(line); event=e['event']; when=e.get('time',e.get('event_time'))
        counts[event]+=1
        if event in ('enqueue','admitted','tx','delivered'):
            stages=[e[k] for k in ('source_time','enqueue_time','admit_time','tx_time','delivery_time') if k in e]
            assert all(b+1e-8>=a for a,b in zip(stages,stages[1:])), (path,e)
        if event=='clock_deferred':
            maximum_clock_deferral=max(maximum_clock_deferral,e['clock_deferral_sec'])
        if event=='accepted' and e.get('message_type','').startswith('navigation_') is False:
            delay=when-e['source_time']; minimum_delay=delay if minimum_delay is None else min(delay,minimum_delay)
            assert -1e-8<=delay<=e['ttl_sec']+1e-8,(path,e)
            key=(e['message_type'],e['sender'],e['recipient'])
            assert e['sequence']>last.get(key,0),(path,e)
            last[key]=e['sequence']
        if event in ('consumed','target_reconfirmed') and e.get('message_type') in ('target_detection','charge_request'):
            assert e['consumed_time']+1e-8>=e['delivery_time']>=e['source_time'],(path,e)
            ttl = 60. if e['message_type']=='target_detection' else CHARGE_REQUEST_TTL_SEC
            assert e['consumed_time']-e['source_time']<=ttl+1e-8,(path,e)
        if event=='coordinator_observer_handoff_wait':
            assert 0<=e['event_time']-e['observer_source_time']<=5.+1e-8,(path,e)
        if event in ('coordinator_navigation_decision','coordinator_charge_decision'):
            kind=e.get('kind')
            if kind=='target_reacquisition_scan':
                assert len(e['requested_position'])==len(e['current_position'])==2,(path,e)
                assert all(abs(a-b)<1e-8 for a,b in zip(e['requested_position'],e['current_position'])),(path,e)
            if kind=='target_reacquisition_exploration':
                import math
                assert e['search_basis'] in ('current_map_frontiers','current_map_known_free_sweep'),(path,e)
                route=e['search_route']
                assert route and all(len(point)==2 and all(math.isfinite(x) for x in point) for point in route),(path,e)
                assert math.dist(route[-1],e['requested_position'])<=e['map_resolution_m']+1e-8,(path,e)
            for name, sample in e['inputs'].items():
                if name=='headquarters/target_detection' and kind in ('local_return_yield','target_reacquisition_scan','target_reacquisition_exploration'):
                    continue
                assert sample['source_time'] is not None,(path,e)
                assert -1e-8<=sample['age_sec']<=sample['ttl_sec']+1e-8,(path,e)
        if event=='coordinator_wait' and waiting is None: waiting=when
        if event=='coordinator_recovered' and waiting is not None:
            waits.append([waiting,when]); waiting=None
    return {'attempt_stage_causality':'PASS','receiver_ttl_and_versions':'PASS',
            'coordinator_decision_source_leases':'PASS',
            'event_counts':dict(counts),'minimum_accepted_source_delay_sec':minimum_delay,
            'maximum_clock_deferral_sec':maximum_clock_deferral,'recovered_wait_intervals':waits}

def communication_aggregate(rows):
    groups=defaultdict(lambda: {'generated':0,'accepted':0,'delay_total':0.,'delay_count':0,
                               'aoi_area':0.,'observed_sec':0.,'unavailable_sec':0.,'events':Counter(),'reasons':Counter()})
    for row in rows:
        duration=row['result']['elapsed_sim_time_sec']
        for s in row['communication']['streams']:
            key=(row['mode'],s['direction'],s['message_type']); g=groups[key]
            g['generated']+=s['generated_unique'];g['accepted']+=s['accepted_unique']
            if s['mean_source_delay_sec'] is not None:
                g['delay_total']+=s['mean_source_delay_sec']*s['accepted_unique'];g['delay_count']+=s['accepted_unique']
            if s['mean_aoi_observed_sec'] is not None:
                observed=duration-s['unavailable_sec'];g['aoi_area']+=observed*s['mean_aoi_observed_sec'];g['observed_sec']+=observed
            g['unavailable_sec']+=s['unavailable_sec'];g['events'].update(s['events']);g['reasons'].update(s['drop_reasons'])
    return [{'mode':key[0],'direction':key[1],'message_type':key[2],
             'application_pdr':g['accepted']/g['generated'] if g['generated'] and key[2]!='ack' else None,
             'generated_unique':g['generated'],'accepted_unique':g['accepted'],
             'mean_source_delay_sec':g['delay_total']/g['delay_count'] if g['delay_count'] else None,
             'mean_aoi_observed_sec':g['aoi_area']/g['observed_sec'] if g['observed_sec'] else None,
             'unavailable_stream_sec':g['unavailable_sec'],'events':dict(g['events']),'drop_reasons':dict(g['reasons'])}
            for key,g in sorted(groups.items())]

def safety_trace(path):
    events=[json.loads(line) for line in path.open()]
    batteries=defaultdict(list); phases=[]; isolation=[]
    for e in events:
        data=e['data']
        if e['topic'].endswith('/battery_state'):
            batteries[data['robot']].append({'mode':data['mode'],'source_time':data['stamp_sec'],
                                            'observer_time':e['observer_time'],'energy':data['energy'],
                                            'return_count':data['return_count'],'charge_count':data['charge_count']})
        elif e['topic']=='/task_state': phases.append({'phase':data,'observer_time':e['observer_time']})
        elif e['topic']=='/robot_failure': isolation.append(e)
    return {'local_battery_transitions':dict(batteries),'central_phase_transitions':phases,'isolation_events':isolation}

def local_wait_audit(path, trace, start, end):
    """Controller waiting, excluding accepted navigation and local safety work.

    This is action-state waiting, not an estimate of physically zero velocity.
    """
    intervals=[];waiting=None; actions=defaultdict(list)
    for line in path.open():
        e=json.loads(line); event=e['event']; t=e.get('time',e.get('event_time'))
        if event=='coordinator_wait' and waiting is None: waiting=t
        elif event=='coordinator_recovered' and waiting is not None:
            intervals.append((waiting,t));waiting=None
        if event=='accepted' and e.get('message_type')=='navigation_goal':
            actions[e['recipient']].append((t,'begin',e['correlation_id']))
        elif event=='enqueue' and e.get('message_type')=='navigation_result':
            actions[e['sender']].append((e['source_time'],'end',e['correlation_id']))
    if waiting is not None:intervals.append((waiting,end))
    result={}
    for name, changes in trace['local_battery_transitions'].items():
        busy=[];active={};seen=set()
        for t,kind,identity in sorted(actions[name]):
            if kind=='begin' and identity not in seen:
                active[identity]=t;seen.add(identity)
            elif kind=='end' and identity in active:busy.append((active.pop(identity),t))
        busy.extend((t,end) for t in active.values())
        for index,change in enumerate(changes):
            if change['mode']!='ACTIVE':
                stop=changes[index+1]['source_time'] if index+1<len(changes) else end
                busy.append((change['source_time'],stop))
        cuts=sorted({start,end,*[max(start,min(end,t)) for a,b in intervals+busy for t in (a,b)]})
        duration=sum(b-a for a,b in zip(cuts,cuts[1:])
                     if any(x<=(a+b)/2<y for x,y in intervals)
                     and not any(x<=(a+b)/2<y for x,y in busy))
        idle=sum(b-a for a,b in zip(cuts,cuts[1:]) if not any(x<=(a+b)/2<y for x,y in busy))
        result[name]={'stale_controller_wait_sec':duration,'local_action_idle_sec':idle,'navigation_or_safety_busy_intervals':busy,
                      'definition':'stale coordinator input; no accepted live network action, local return/charge or failed state; not physical zero-speed duration'}
    return result

def bootstrap(rows):
    groups=defaultdict(list)
    for key,value in rows: groups[key].append(value)
    vals=[v for group in groups.values() for v in group]
    if not vals: return {'n':0,'mean':None,'ci95':None}
    keys=list(groups);rng=random.Random(17011); samples=[]
    for _ in range(10000):
        sample=[v for k in rng.choices(keys,k=len(keys)) for v in groups[k]]
        samples.append(sum(sample)/len(sample))
    samples.sort()
    return {'n':len(vals),'clusters':len(keys),'mean':sum(vals)/len(vals),'ci95':[samples[249],samples[9749]],
            'method':'physical-cell cluster percentile bootstrap, 10000 resamples seed17011; fixed matrix descriptive, not held-out population inference'}



def fixed_ideal_batches(paths):
    """Same-commit partition, with no duplicate physical cells or replacement."""
    batches=[load(path) for path in paths]
    reference=batches[0]['manifest'];episodes=[];cells=set()
    evidence=[]
    for path,batch in zip(paths,batches):
        same_candidate(batch['manifest'],reference)
        assert batch['max_duration_sec']==300 and batch['infrastructure_retries']==0
        for row in batch['episodes']:
            cell=(row['scenario_id'],row['robot_count'],row['gazebo_seed'])
            assert cell not in cells, ('duplicate fixed cell',cell)
            cells.add(cell);episodes.append(row)
        evidence.append({'summary_path':str(path),'content_sha256':sha(path),
                         'manifest':batch['manifest']})
    return {'manifest':reference,'episodes':episodes,'batches':evidence}


def physical_return_audit(events, epoch, homes, window=(42., 248.)):
    """Require motion toward home under local RETURNING and live native Nav2."""
    import math
    paths=defaultdict(list)
    for event in events:
        if event['event'] != 'physics': continue
        for name, robot in event['robots'].items():
            paths[name].append((event['observer_time'], robot))
    evidence={}
    for name, home in homes.items():
        starts={}; motion=defaultdict(float); progress={}; executing=defaultdict(float)
        previous=None
        for when, robot in paths[name]:
            battery=robot.get('battery') or {}
            if battery.get('mode') != 'RETURNING':
                previous=None
                continue
            count=battery['return_count']
            distance=math.hypot(robot['x']-home[0], robot['y']-home[1])
            if count not in starts:
                starts[count]={'time_offset_sec':when-epoch,'home_distance_m':distance}
                progress[count]=0.
            if window[0] <= when-epoch <= window[1]:
                progress[count]=max(progress[count], starts[count]['home_distance_m']-distance)
                if previous is not None:
                    t, old, old_count=previous
                    dt=when-t
                    if old_count==count and window[0]<=t-epoch<=window[1] and 0.<dt<=1.:
                        segment=math.hypot(robot['x']-old['x'], robot['y']-old['y'])
                        # Exclude discontinuities, and count only consecutive
                        # physical observations within the blackout guard.
                        assert segment<=.5*dt+.1, (name,dt,segment)
                        motion[count]+=segment
                        if any(s['status']==2 for s in robot.get('nav2_status',[])):
                            executing[count]+=segment
            previous=(when,robot,count)
        valid=[count for count,start in starts.items()
               if window[0]<=start['time_offset_sec']<=window[1]
               and start['home_distance_m']>=1.1 and motion[count]>=.5
               and progress[count]>=.5 and executing[count]>=.5]
        assert valid, (name,starts,dict(motion),progress,dict(executing))
        count=valid[0]
        evidence[name]={**starts[count],'return_count':count,
                        'return_path_inside_blackout_m':motion[count],
                        'progress_toward_home_m':progress[count],
                        'nav2_executing_motion_m':executing[count]}
    return evidence


def staging_audit(events, epoch, fixture):
    """Preparation is one-shot and all commanded legs use current source leases."""
    import math
    prepared={};requested=set();charged=False;resumed=False
    for event in events:
        kind=event['event'];name=event.get('robot')
        assert kind not in ('fixture_failed','interrupted')
        if kind=='staging_requested':
            assert name not in prepared and name in fixture['poses']
            assert 0<=event['observer_time']-epoch<=fixture['stage_deadline_sec']
            assert set(event['inputs'])=={'map_snapshot','pose_state','frame_state','battery_state'}
            for lease in event['inputs'].values():
                age=event['observer_time']-lease['source_time']
                assert 0<=age<lease['ttl_sec'] and abs(age-lease['age_sec'])<1e-6
            assert math.dist(event['waypoint'],event['current_position'])<=fixture['navigation_leg_limit_m']+1e-8
            requested.add(name)
        elif kind=='staged':
            assert name in requested and name not in prepared
            assert 0<=event['observer_time']-epoch<=fixture['stage_deadline_sec']
            assert math.dist(event['position'],fixture['poses'][name][:2])<=fixture['position_tolerance_m']+1e-8
            prepared[name]=event
        elif kind=='both_charged':
            assert set(prepared)==set(fixture['poses'])
            charged=True
        elif kind=='coordinator_resumed':
            assert charged
            resumed=True
    assert charged and resumed and set(prepared)==set(fixture['poses'])
    return prepared


def main():
    p=argparse.ArgumentParser()
    p.add_argument('summaries',nargs='+',type=Path)
    p.add_argument('--ideal-fixed',required=True,type=Path,nargs='+')
    p.add_argument('--forced',required=True,type=Path)
    p.add_argument('--safety-probes',required=True,type=Path)
    p.add_argument('--return-proof',required=True,type=Path)
    p.add_argument('--return-physics',required=True,type=Path)
    p.add_argument('--historical-ideal',required=True,type=Path)
    p.add_argument('--protocol',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args(); summaries=[load(x) for x in a.summaries];config=summaries[0]['config']
    audit=load(ROOT/'src/multi_robot_exploration/config/p3a_forbidden_bypasses.json')
    assert not source_violations(audit,ROOT/'src/multi_robot_exploration')
    cases={c['id']:c for c in config['cases']}; episodes={}; pairs={}; reference=summaries[0]['manifest']
    for s in summaries:
        assert s['config']==config and s['manifest']['task_stack_clean']
        assert s.get('finished_at_utc') and len(s['episodes'])>=len(s['pairs'])
        assert s['manifest']['git_commit']==reference['git_commit']
        assert s['manifest']['source_digests']==reference['source_digests']
        assert s['manifest']['p3b5_runner_sha256']==reference['p3b5_runner_sha256']
        assert not (pairs.keys() & s['pairs'].keys())
        pairs.update(s['pairs']);episodes.update(s['episodes'])
    assert set(pairs)==set(cases), (set(cases)-pairs.keys())
    assert config['holdout_fault_seed']!=config['fault_seed']
    assert config['holdout_fault_seed_declaration']['predeclared_at_utc']<reference['generated_at_utc']
    heldout=config['scenarios']['holdout3']; declaration=config['holdout_world_declaration']
    assert declaration['predeclared_at_utc']<reference['generated_at_utc']
    assert heldout['holdout'] and heldout['seed'] in config['holdout_seeds']
    assert declaration['world']==heldout['world'] and declaration['gazebo_seed']==heldout['seed']
    assert declaration['fault_seed']==config['holdout_fault_seed']
    assert sha(ROOT/'src/multi_robot/worlds'/heldout['world'])==declaration['world_content_sha256']
    assert sha(ROOT/'src/multi_robot_exploration/multi_robot_exploration/control.py')==declaration['controller_content_sha256']
    for case in cases.values():
        if case['scenario']=='holdout3':
            assert config['profiles'][case['profile']]['gateway_seed']==config['holdout_fault_seed']
    raw_evidence=[]
    for key,row in episodes.items():
        assert not row['infrastructure_failure'] and not row['operational_failure']
        assert row['observer_returncode']==0 and row['safety_events_sha256']
        r=row['result']; path=Path(row['result_path']);d=path.parent
        assert row['result_sha256']==file_digest(path)
        assert row['communication']['ledger_sha256']==file_digest(d/'ledger.jsonl')
        assert row['graph_sha256']==file_digest(d/'graph.json')
        assert not runtime_violations(Snapshot(load(d/'graph.json')['nodes']),audit,r['robot_count'])
        # Evaluator records the first 0.5s sampling tick at/after the horizon.
        assert r['elapsed_sim_time_sec']<=config['duration_sec']+.6
        assert r['collision_monitoring_active'] and r['collision_events']==0, key
        if row['profile'].get('battery_initial_energy')!=0:
            assert r['battery_minimum_energy']>0, key
        assert r['mission_mode']==row['case']['mode']
        command=shlex.split(row['command'])
        seed_values=[int(command[i+1]) for i, arg in enumerate(command) if arg=='--gateway-seed']
        assert seed_values and seed_values[-1]==row['profile'].get('gateway_seed',config['fault_seed'])
        if r['success'] and r['mission_mode']=='rally': episode_ok(r)
        if r['partial_completion']:
            native_completion_ok(r)
            assert r['success'] is False and r['task_phase']=='PARTIAL_COMPLETE'
            assert r['failed_robots']==['tb3'] and set(r['required_robot_names'])=={'tb1','tb2'}
            for name in r['required_robot_names']:
                b=r['robots'][name]
                assert b['rally_final_error_m']<=.35 and b['final_linear_speed_mps']<=.05 and b['final_angular_speed_radps']<=.1
        temporal=ledger_audit(d/'ledger.jsonl')
        assert row['safety_events_sha256']==file_digest(d/'safety_events.jsonl')
        trace=safety_trace(d/'safety_events.jsonl')
        raw_evidence.append({'episode_id':key,'result_path':str(path),'result_content_sha256':sha(path),
                             'ledger_content_sha256':sha(d/'ledger.jsonl'),'graph_content_sha256':sha(d/'graph.json'),
                             'safety_events_content_sha256':sha(d/'safety_events.jsonl'),'temporal_audit':temporal,
                             'safety_trace':trace,'local_wait_audit':local_wait_audit(d/'ledger.jsonl',trace,r['start_sim_time_sec'],r['end_sim_time_sec'])})
    traces={e['episode_id']:e['safety_trace'] for e in raw_evidence}
    for name in ('up100_lab','ttl_lab','detection_loss_rooms','target_loss_rooms'):
        r=episodes[pairs[name]['fault']]['result']
        assert not r['success'] and r['time_to_rally_sec'] is None and r['completion_time_sec'] is None
    r=episodes[pairs['single_failure_rooms']['fault']]['result']
    assert r['partial_completion'] and len(r['required_robot_names'])==2
    single_trace=traces[pairs['single_failure_rooms']['fault']]
    local_failure=next(b['source_time'] for b in single_trace['local_battery_transitions']['tb3'] if b['mode']=='FAILED')
    isolation=next(e['observer_time'] for e in single_trace['isolation_events'] if e['data']['robot']=='tb3')
    isolation_latency=isolation-local_failure
    assert -.1<=isolation_latency<=5.,isolation_latency
    charge=episodes[pairs['forced_charge_outage']['fault']]['result']
    assert charge['battery_total_charges']>=2 and all(b['battery_charge_count']>=1 for b in charge['robots'].values())
    for name in ('battery_loss_lab','up100_lab'):
        assert episodes[pairs[name]['fault']]['result']['failed_robots']==[], 'silence is not physical failure'
    for mode in ('ideal','fault'):
        exhausted=episodes[pairs['battery_exhaust_lab'][mode]]['result']
        assert exhausted['task_phase']=='FAILED' and set(exhausted['failed_robots'])=={'tb1','tb2'}
    assert episodes[pairs['overflow_rooms']['fault']]['communication']['reasons'].get('queue_overflow',0)>0
    assert episodes[pairs['detection_loss_rooms']['fault']]['communication']['events'].get('failed',0)>0
    assert episodes[pairs['deadline_rooms']['fault']]['communication']['reasons'].get('expired_in_flight',0)>0
    duplicate=episodes[pairs['duplicates_corridors']['fault']]['communication']
    assert duplicate['events'].get('stale_sequence',0)>0
    assert duplicate['reordered_delivery_attempts']>0, 'actual reorder required, not a profile label'
    assert duplicate['reorders_by_type'].get('pose_state',0)>0, 'real application-state reorder required'
    fixed=fixed_ideal_batches(a.ideal_fixed);assert len(fixed['episodes'])==10
    cells=set()
    for row in fixed['episodes']:
        assert not row['infrastructure_failure'] and row['prestart_failure_count']==0 and row['runner_returncode']==0
        episode_ok(load(row['result_path']));cells.add((row['scenario_id'],row['robot_count'],row['gazebo_seed']))
        assert not runtime_violations(Snapshot(load(row['graph_path'])['nodes']),audit,row['robot_count'])
    expected={(scene,3,seed) for scene in ('lab_far_northwest','rooms_far_northeast','corridors_far_west') for seed in (101,202,303)}|{('corridors_far_west',2,202)}
    assert cells==expected
    forced=load(a.forced);forces=[e for e in forced['episodes'].values() if e['mode']=='ideal'];assert len(forces)==1
    force=forces[0];episode_ok(force['result']);assert all(b['battery_charge_count']>=1 for b in force['result']['robots'].values())
    assert reference['git_commit']==fixed['manifest']['git_commit']==forced['manifest']['git_commit']
    for k in CORE_KEYS:
        assert reference['source_digests'][k]==fixed['manifest']['source_digests'][k]==forced['manifest']['source_digests'][k]
    probes=load(a.safety_probes)
    assert probes['manifest']['git_commit']==reference['git_commit'] and probes['manifest']['task_stack_clean']
    assert set(probes['pairs'])=={'local_return_under_blackout','local_deadline_cancel'}
    for k in CORE_KEYS: assert probes['manifest']['source_digests'][k]==reference['source_digests'][k]
    probe_evidence=[]
    for identity,row in probes['episodes'].items():
        assert row['runner_returncode']==0 and not row['infrastructure_failure'] and row['observer_returncode']==0
        r=row['result']; assert r['collision_events']==0 and r['collision_monitoring_active']
        assert r['battery_minimum_energy']>0 and not r['failed_robots']
        d=Path(row['result_path']).parent
        assert row['result_sha256']==file_digest(d/(identity+'.json'))
        assert row['communication']['ledger_sha256']==file_digest(d/'ledger.jsonl')
        assert row['graph_sha256']==file_digest(d/'graph.json')
        assert row['safety_events_sha256']==file_digest(d/'safety_events.jsonl')
        assert not runtime_violations(Snapshot(load(d/'graph.json')['nodes']),audit,r['robot_count'])
        probe_evidence.append({'episode_id':identity,'temporal_audit':ledger_audit(d/'ledger.jsonl'),
                               'safety_trace':safety_trace(d/'safety_events.jsonl'),
                               'result_content_sha256':sha(d/(identity+'.json')),
                               'ledger_content_sha256':sha(d/'ledger.jsonl'),
                               'graph_content_sha256':sha(d/'graph.json'),
                               'safety_events_content_sha256':sha(d/'safety_events.jsonl')})
    assert len(probe_evidence)==4
    probe_pair=probes['pairs']['local_return_under_blackout'];probe=probes['episodes'][probe_pair['fault']]
    assert probes['episodes'][probe_pair['ideal']]['settings']==probe['settings']
    d=Path(probe['result_path']).parent
    epoch=next(json.loads(line)['event_time'] for line in (d/'ledger.jsonl').open() if json.loads(line)['event']=='fault_epoch')
    return_inside={name:[b['source_time']-epoch for b in changes if b['mode']=='RETURNING' and 20<=b['source_time']-epoch<=250]
                   for name,changes in safety_trace(d/'safety_events.jsonl')['local_battery_transitions'].items()}
    # The original contact-zone probe can begin before the blackout. Retain
    # its timing, but require BOTH robots to satisfy the stronger predeclared
    # physical-motion audit below for the outage-return guarantee.
    return_all={name:[b["source_time"]-epoch for b in changes if b["mode"]=="RETURNING"]
                for name,changes in safety_trace(d/"safety_events.jsonl")["local_battery_transitions"].items()}
    assert all(b['battery_charge_count']>=1 for b in probe['result']['robots'].values())
    local_deadline=probes['episodes'][probes['pairs']['local_deadline_cancel']['fault']]
    assert local_deadline['communication']['events'].get('navigation_deadline',0)>0
    physical=load(a.return_proof);metadata=load(a.return_physics)
    assert set(physical['pairs'])=={'physical_return_under_blackout'}
    assert len(physical['episodes'])==2 and physical.get('finished_at_utc')
    assert physical['manifest']['git_commit']==reference['git_commit'] and physical['manifest']['task_stack_clean']
    for k in CORE_KEYS: assert physical['manifest']['source_digests'][k]==reference['source_digests'][k]
    assert metadata['runner_returncode']==0
    assert metadata['config']==physical['config']
    assert hashlib.sha256(metadata['config_source'].encode()).hexdigest()==metadata['config_content_sha256']
    assert json.loads(metadata['config_source'])==physical['config']
    assert hashlib.sha256(metadata['observer_source'].encode()).hexdigest()==metadata['observer_content_sha256']
    assert metadata['config']['predeclared_at_utc']<physical['manifest']['generated_at_utc']
    interval=physical['config']['profiles']['physical_outage']['gateway_blackout_intervals'][0]
    assert physical['config']['physical_verification']['return_motion_window_sec']==[interval[0]+2,interval[1]-2]
    physical_evidence=[]
    for identity,row in physical['episodes'].items():
        assert row['runner_returncode']==0 and row['observer_returncode']==0
        assert not row['infrastructure_failure'] and not row['operational_failure']
        r=row['result'];assert r['collision_monitoring_active'] and r['collision_events']==0
        assert r['battery_minimum_energy']>0 and not r['failed_robots']
        assert all(b['battery_charge_count']>=1 for b in r['robots'].values())
        d=Path(row['result_path']).parent
        for key,file in [('result_sha256',identity+'.json'),('graph_sha256','graph.json'),('safety_events_sha256','safety_events.jsonl')]:
            assert row[key]==file_digest(d/file)
        assert row['communication']['ledger_sha256']==file_digest(d/'ledger.jsonl')
        assert not runtime_violations(Snapshot(load(d/'graph.json')['nodes']),audit,r['robot_count'])
        observer=next(x for x in metadata['observers'] if x['mode']==row['mode'])
        assert observer['ros_domain_id']==row['ros_domain_id'] and observer['returncode']==0
        assert observer['output_content_sha256']==sha(Path(observer['output']))
        detail={'episode_id':identity,'temporal_audit':ledger_audit(d/'ledger.jsonl'),
                'physics_content_sha256':observer['output_content_sha256']}
        if row['mode']=='fault':
            epoch=next(json.loads(line)['event_time'] for line in (d/'ledger.jsonl').open() if json.loads(line)['event']=='fault_epoch')
            homes={n:(b['battery_charge_x'],b['battery_charge_y']) for n,b in r['robots'].items()}
            detail['physical_local_return']=physical_return_audit(
                [json.loads(line) for line in Path(observer['output']).open()],epoch,homes,
                window=physical['config']['physical_verification']['return_motion_window_sec'])
        if 'return_staging' in physical['config']:
            assert row['staging_returncode']==0 and row['staging_events_sha256']==file_digest(d/'staging.jsonl')
            assert hashlib.sha256(row['staging_source'].encode()).hexdigest()==row['staging_source_sha256']
            stages=[json.loads(line) for line in (d/'staging.jsonl').open()]
            epoch=next(json.loads(line)['event_time'] for line in (d/'ledger.jsonl').open() if json.loads(line)['event']=='fault_epoch')
            prepared=staging_audit(stages,epoch,physical['config']['return_staging'])
            assert set(prepared)==set(r['robots'])
            detail['controlled_staging']={'source_sha256':row['staging_source_sha256'],
                'events_sha256':row['staging_events_sha256'],'prepared':prepared,
                'scope':'Supplemental safety fixture; suspended central exploration; excluded from mission/TDI.'}
        physical_evidence.append(detail)
    pair_rows=[];values=[];by_mode=defaultdict(Counter)
    for key,pair in pairs.items():
        c=cases[key];i,f=(episodes[pair[m]] for m in ('ideal','fault'));ir,fr=i['result'],f['result']
        assert i['settings']==f['settings']
        value=tdi(ir,fr);scenario=config['scenarios'][c['scenario']]
        if value is not None:
            cluster=json.dumps([scenario['world'],scenario['robot_count'],scenario['seed'],i['settings']['effective_initial_energy']])
            values.append((cluster,value))
        for label,r in (('ideal',ir),('fault',fr)):
            by_mode[c['mode']][label+'_'+r['termination_reason']]+=1
        rmst_i=ir['completion_time_sec'] if ir['success'] and c['mode']=='rally' else config['duration_sec']
        rmst_f=fr['completion_time_sec'] if fr['success'] and c['mode']=='rally' else config['duration_sec']
        pair_rows.append({'case_id':key,**pair,'scenario':scenario,'mode':c['mode'],'profile':c['profile'],'tdi':value,
                          'ideal_termination':ir['termination_reason'],'fault_termination':fr['termination_reason'],
                          'ideal_complete':bool(ir['success'] and c['mode']=='rally'),
                          'fault_complete':bool(fr['success'] and c['mode']=='rally'),
                          'fault_partial':fr['partial_completion'],'rmst300_ideal':rmst_i,'rmst300_fault':rmst_f,
                          'coverage_delta':fr['correct_free_coverage_ratio']-ir['correct_free_coverage_ratio'],
                          'energy_delta':fr['battery_minimum_energy']-ir['battery_minimum_energy']})
        communication=communication_aggregate([i,f]); indexed={}
        for stream in communication:indexed.setdefault((stream['direction'],stream['message_type']),{})[stream['mode']]=stream
        deltas=[]
        for (direction,message_type),streams in sorted(indexed.items()):
            before,after=streams.get('ideal'),streams.get('fault'); delta={}
            for field in ('application_pdr','mean_source_delay_sec','mean_aoi_observed_sec','unavailable_stream_sec'):
                x=before.get(field) if before else None;y=after.get(field) if after else None
                delta[field]=None if x is None or y is None else y-x
            deltas.append({'direction':direction,'message_type':message_type,'ideal':before,'fault':after,'fault_minus_ideal':delta})
        pair_rows[-1]['communication_delta_by_type']=deltas
    protocol=load(a.protocol)
    assert protocol['status']=='PASS' and len(protocol['matrix'])==54
    combinations={(r['seed'],r['direction'],r['loss_rate'],r['delay_sec']) for r in protocol['matrix']}
    assert combinations=={(seed,direction,loss,delay) for seed in (101,202,303)
                          for direction in ('uplink','downlink') for loss in (0.,.1,1.) for delay in (0.,.5,2.)}
    historical_fixed=load(a.historical_ideal)
    historical_outcomes=Counter(row.get('termination_reason') for row in historical_fixed['episodes'])
    report={'status':'PASS','config':config,'experiment_manifest':reference,'task_core_source_digests':{k:reference['source_digests'][k] for k in CORE_KEYS},
            'historical_ideal_batch':historical_fixed,'historical_ideal_outcomes':dict(historical_outcomes),'ideal_fixed_manifest':fixed['manifest'],'forced_manifest':forced['manifest'],'task_stack_frozen_commit':fixed['manifest']['git_commit'],
            'tdi':bootstrap(values),'paired_results':pair_rows,'result_counts_by_mode':dict(by_mode),
            'episodes':episodes,'evidence':raw_evidence,'unique_episode_count':len(episodes),
            'communication_by_type':communication_aggregate(episodes.values()),
            'fixed_ideal_evidence':fixed,'forced_ideal_episode':force,
            'hash_contract':'legacy *_sha256 uses filename+file bytes; *_content_sha256 is standard SHA256(bytes); tree digests use relative paths+bytes',
            'safety_audit':{'single_failure_observer_isolation_latency_sec':isolation_latency,
                            'outage_local_return_offsets_sec':return_inside,
                            'auxiliary_all_return_offsets_sec':return_all,
                            'outage_return_guarantee_basis':'Both robots in predeclared physical probe: start >=1.1m from home, >=0.5m return/progress/live-Nav2 motion within guarded blackout; original contact-zone timing is diagnostic only'},
            'auxiliary_safety_probes':probes,'auxiliary_probe_evidence':probe_evidence,
            'physical_return_probe':physical,'physical_return_metadata':metadata,'physical_return_evidence':physical_evidence,
            'all_gate_unique_episode_count':len(episodes)+len(fixed['episodes'])+len(probe_evidence)+len(physical_evidence),
            'validator':{'path':str(Path(__file__).resolve()),'content_sha256':sha(Path(__file__))},
            'protocol_evidence':{'path':str(a.protocol),'content_sha256':sha(a.protocol),'data':protocol},
            'summary_evidence':[{'path':str(x),'content_sha256':sha(x)} for x in a.summaries],
            'gate_checks':['all27cases; all historical failed batches retained, not pooled into primary task degradation cohort','ideal/fault same protocol/physical settings','safe complete/partial gates',
                           '100%/expired target cannot fake rally','actual queue/retry/deadline/duplicate/reorder',
                           'forced outage charging safety + both-robot predeclared physical return proof','10 fixed ideal cells + forced regression','source/graphs/hashes']}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':'PASS','episodes':len(episodes),'pairs':len(pairs),'tdi':report['tdi']}))

if __name__=='__main__': main()
