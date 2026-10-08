#!/usr/bin/env python3
"""Read-only P2C.1 original/return-budget gate; never repairs task outcomes."""
import argparse,base64,hashlib,json,math,subprocess,traceback,zlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from check_p3a6_gate import Snapshot
from check_p3b5_gate import episode_ok,ledger_audit,native_completion_ok
from check_p3c5_gate import audit_original,declaration_audit
from multi_robot_exploration import control
from multi_robot_exploration.bypass_audit import runtime_violations


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def return_audit(path,require_pose_leases=False):
    starts={};finished={};rows=[];maps=0;legs=0;pose_checks=0
    for line in path.read_text().splitlines():
        outer=json.loads(line)
        if not outer['topic'].endswith('/battery_return_audit'):continue
        e=outer['data'];key=(e['robot'],e['return_count']);kind=e['event']
        assert math.isfinite(e['sim_time']) and math.isfinite(e['energy'])
        if kind=='return_started':
            assert key not in starts;starts[key]=e
        if kind=='return_prediction_available':
            assert key in starts and key not in finished
            assert starts[key]['budget'] is None
            starts[key]['budget']=e['start']['budget']
        if kind=='return_finished':
            assert key in starts and key not in finished;finished[key]=e
            assert all(math.isfinite(e[k]) for k in ('actual_distance_m','actual_elapsed_sec','actual_energy_spent'))
            assert e['actual_distance_m']>=0 and e['actual_elapsed_sec']>=0
            assert e['actual_energy_spent']>=-1e-8
            assert math.isclose(e['actual_energy_spent'],starts[key]['energy']-e['energy'],abs_tol=1e-6)
            model=e['energy_model']
            assert model==starts[key]['energy_model']
            spent=e['actual_distance_m']*model['move_cost_per_m']+e['actual_elapsed_sec']*model['idle_cost_per_sec']
            assert math.isclose(spent,e['actual_energy_spent'],abs_tol=1e-6)
            if e['predicted_energy_spent'] is not None:
                predicted=starts[key]['budget']
                assert predicted is not None
                assert math.isclose(e['predicted_energy_spent'],predicted['required_energy']-predicted['safety_margin'],abs_tol=1e-8)
                assert abs(e['prediction_error']-(e['actual_energy_spent']-e['predicted_energy_spent']))<1e-8
            if e['outcome']=='charger_stopped':
                assert e['energy']>0 and e['prediction_error'] is not None and e['prediction_error']<=1e-6
            rows.append(e)
        saved=e.get('map_evidence');budget=e.get('budget')
        if kind=='return_prediction_available':budget=e['start']['budget']
        if budget is not None and (require_pose_leases or 'pose_age_sec' in budget):
            ages=[e['sim_time']-budget[name] for name in ('odom_source_time','frame_source_time')]
            assert all(math.isfinite(age) and 0<=age<=2. for age in ages)
            assert math.isclose(max(ages),budget['pose_age_sec'],abs_tol=1e-8)
            assert math.isfinite(budget['frame_stamp_offset_sec']) and budget['frame_stamp_offset_sec']>=0
            m=e['energy_model']
            rebuilt=control.return_energy_budget(budget['path_distance_m'],m['move_cost_per_m'],m['idle_cost_per_sec'],
                m['path_factor'],m['nominal_speed_mps'],m['safety_margin'],m['recovery_wait_sec'],
                budget['map_age_sec'],budget['pose_age_sec'])
            assert math.isclose(rebuilt['required_energy'],budget['required_energy'],abs_tol=1e-8)
            pose_checks+=1
        if saved and budget and budget['path_distance_m']>0:
            assert saved['encoding']=='zlib_base64_int16_le'
            raw=np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape'])
            assert saved['version']==budget['map_version'] and saved['source_time']==budget['map_source_time']
            assert saved['source']==budget['map_source']
            assert 0<=e['sim_time']-saved['source_time']<=5.
            assert math.isclose(budget['map_age_sec'],e['sim_time']-saved['source_time'],abs_tol=1e-8)
            assert hashlib.blake2b(raw.tobytes(),digest_size=16).hexdigest()==budget['map_content_blake2b']
            position=e.get('position')
            if position is None and budget.get('route'):position=budget['route'][0]
            assert position is not None
            distance,route=control.known_return_route(raw,saved['resolution'],saved['origin'],position,
                e['home'],e['charge_radius_m'],include_route=True)
            assert distance is not None and math.isclose(distance,budget['path_distance_m'],abs_tol=1e-8)
            m=e['energy_model']
            rebuilt=control.return_energy_budget(distance,m['move_cost_per_m'],m['idle_cost_per_sec'],
                m['path_factor'],m['nominal_speed_mps'],m['safety_margin'],m['recovery_wait_sec'],budget['map_age_sec'],
                budget.get('pose_age_sec',0.))
            assert math.isclose(rebuilt['required_energy'],budget['required_energy'],abs_tol=1e-8)
            if budget.get('route'):
                assert abs(sum(math.dist(a,b) for a,b in zip(budget['route'],budget['route'][1:]))-distance)<1e-8
            maps+=1
        if kind=='return_leg_sent':
            assert budget is not None and e['energy']>e['energy_model']['safety_margin']
            assert saved is not None and e['route'];legs+=1
    assert set(starts)==set(finished),('unclosed return prediction',set(starts)-set(finished))
    return dict(status='PASS',return_triggers=len(starts),map_budget_reconstructions=maps,
        pose_lease_reconstructions=pose_checks,pose_leases_required=require_pose_leases,
        local_legs=legs,charger_returns=sum(r['outcome']=='charger_stopped' for r in rows),returns=rows)


def lookahead_audit(records):
    count=0
    for e in records:
        if e.get('event')!='coordinator_charge_decision' or not e.get('opportunity_lookahead'):
            continue
        f=e['opportunity_lookahead'];saved=f['map_evidence'];state=f['battery_state']
        assert f['strategy']=='two_current_frontiers' and saved['source']=='ap_delivered_planning_map'
        assert saved['encoding']=='zlib_base64_int16_le'
        assert f['first_group']!=f['second_group']
        assert math.dist(f['first_position'],f['second_position'])>=control.MIN_TARGET_SEPARATION_M
        assert math.isclose(e['event_time']-saved['source_time'],f['map_age_sec'],abs_tol=1e-8)
        assert e['inputs']['headquarters/fused_map_snapshot']['source_time']==saved['source_time']
        assert math.isclose(e['inputs'][e['robot']+'/pose_state']['age_sec'],f['pose_age_sec'],abs_tol=1e-8)
        assert 0<=f['map_age_sec']<=5 and 0<=f['pose_age_sec']<=2
        assert e['available_energy']<f['required_energy']<state['capacity']*state['charge_target_fraction']
        assert e['required_energy']==f['required_energy']
        raw=np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape'])
        first,second=f['first_position'],f['second_position']
        _,route=control.plan_rally_leg(control.RallyPose(*second,0.),raw,saved['resolution'],saved['origin'],first,
            max_distance_m=float('inf'),blocked_positions=f['blocked_positions'],clearance_m=control.PATH_CLEARANCE_M)
        assert route and np.allclose(route,f['between_route'])
        between=math.dist(first,route[0])+sum(math.dist(a,b) for a,b in zip(route,route[1:]))
        assert math.isclose(between,f['between_distance_m'],abs_tol=1e-8)
        home_distance,_=control.known_return_route(raw,saved['resolution'],saved['origin'],second,f['home'],state.get('charge_radius_m',.8))
        assert home_distance is not None and math.isclose(home_distance,f['home_distance_m'],abs_tol=1e-8)
        required=control.battery_assignment_required_energy(f['first_path_distance_m']+between,home_distance,
            state.get('move_cost_per_m',1.),state.get('idle_cost_per_sec',.02),state.get('return_path_factor',2.),
            state.get('nominal_speed_mps',.18),state.get('return_safety_margin',8.),
            state.get('return_recovery_wait_sec',30.),f['map_age_sec'],f['pose_age_sec'])
        assert math.isclose(required,f['required_energy'],abs_tol=1e-8)
        count+=1
    return dict(status='PASS',two_frontier_charge_decisions=count)


def check_one(path,config):
    path=path.resolve()
    row=json.loads(path.read_text());directory=path.parent
    assert row['config']==config
    declaration_audit(row,config,directory)
    assert row['runner_returncode']==row['observer_returncode']==0
    assert not any(v for k,v in row.items() if k.endswith('_forced_shutdown'))
    for relative,expected in row['evidence_sha256'].items():assert sha(directory/relative)==expected
    result=row['result'];case=row['case']
    if case=='empty_battery':
        assert not result['success'] and result['task_phase']=='FAILED' and result['collision_events']==0
        assert all(r['battery_mode']=='FAILED' and r['battery_minimum_energy']==0 for r in result['robots'].values())
        records=[json.loads(x) for x in (directory/'ledger.jsonl').read_text().splitlines()]
        assert not any(e.get('message_type')=='navigation_goal' and e['event']=='tx' for e in records)
        communications=dict(temporal_audit=ledger_audit(directory/'ledger.jsonl'))
    else:
        communications,_=audit_original((row,config))
        if case.startswith(('fixed_','dev_')) or case in ('forced2','protocol_forced2','holdout_ideal'):
            episode_ok(result)
        if 'forced' in case:
            assert all(r['battery_charge_count']>=1 for r in result['robots'].values())
    original=json.loads((directory/'graph.json').read_text())
    audit=json.loads((Path(__file__).resolve().parents[1]/'src/multi_robot_exploration/config/p3a_forbidden_bypasses.json').read_text())
    violations=runtime_violations(Snapshot(original['nodes']),audit,result['robot_count'])
    assert not violations,violations
    native=return_audit(directory/'safety_events.jsonl',bool(config.get('native_pose_contract')))
    forecast=lookahead_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    assert result['collision_monitoring_active']
    return dict(case=case,status='PASS',git_commit=row['git_commit'],source_digests=row['source_digests'],
        result=result,raw_summary=str(path.resolve()),raw_summary_sha256=sha(path),return_audit=native,
        communication_audit=communications,lookahead_audit=forecast)


def audit_one(item):
    path,config=item
    try:return check_one(path,config),None
    except Exception as error:
        return None,dict(case=json.loads(path.read_text())['case'],error=repr(error),traceback=traceback.format_exc())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=Path(__file__).with_name('p2c_integration_manifest.json'))
    p.add_argument('--development',action='store_true')
    p.add_argument('--cases',nargs='+')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=3,choices=(1,2,3))
    a=p.parse_args()
    if a.output.exists():p.error('do not overwrite an audit')
    config=json.loads(a.manifest.read_text())
    required=set(a.cases or config['development_cases' if a.development else 'gate_cases'])
    summaries={}
    for path in a.run_root.glob('*/summary.json'):
        row=json.loads(path.read_text())
        if row['case'] in required:
            assert row['case'] not in summaries,'duplicate original cell'
            summaries[row['case']]=path
    assert set(summaries)==required,dict(missing=sorted(required-set(summaries)),extra=sorted(set(summaries)-required))
    evidence=[];errors=[]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for passed,failed in pool.map(audit_one,[(path,config) for case,path in sorted(summaries.items())]):
            if failed:errors.append(failed)
            else:evidence.append(passed)
    originals=[json.loads(path.read_text()) for path in summaries.values()]
    assert len({r['git_commit'] for r in originals})==1,'cohort must share one pushed source freeze'
    assert all(r['source_digests']==originals[0]['source_digests'] for r in originals)
    root=Path(__file__).resolve().parents[3]
    original_manifest=json.loads(subprocess.check_output(['git','show',f"{originals[0]['git_commit']}:{a.manifest.resolve().relative_to(root)}"],cwd=root))
    assert original_manifest==config
    result=dict(status='FAIL' if errors else 'PASS',scope='development' if a.development else 'integration',
        task_stack_frozen_commit=originals[0]['git_commit'],cases=len(summaries),errors=errors,evidence=evidence,
        full_declared_scope=a.cases is None,
        raw_failures_retained=True,physical_blackout_gate='separate_required_evidence',
        general_hardware_safety_guarantee=False)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence'},indent=2))
    return int(bool(errors))

if __name__=='__main__':raise SystemExit(main())
