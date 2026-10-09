#!/usr/bin/env python3
"""Read-only P2C.1 original/return-budget gate; never repairs task outcomes."""
import argparse,base64,gzip,hashlib,json,math,re,subprocess,traceback,zlib
from collections import Counter
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from check_p3a6_gate import Snapshot
from check_p3b5_gate import episode_ok,ledger_audit,native_completion_ok
from check_p3c5_gate import audit_original,declaration_audit
from multi_robot_exploration import control
from multi_robot_exploration.bypass_audit import runtime_violations
from p2c_native_graph import native_tf_ingress_audit
from p2c_scan_self_filter import scan_self_filter_audit
from p2c_return_preparation import return_preparation_audit
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_rally_transit_heading import transit_heading_audit


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def navigation_capture_audit(row,directory):
    """Check the declared, completed lossless trace separately from task success."""
    if not row['config'].get('navigation_input_capture'):return None
    from run_p2d_baseline import file_digest
    path=directory/'navigation_inputs.jsonl.gz'
    assert path.name in row['evidence_sha256'] and sha(path)==row['evidence_sha256'][path.name]
    command=row['observer_command']
    assert Path(command[command.index('--navigation-input-output')+1])==path
    assert row['source_digests']['navigation_capture']==file_digest(Path(__file__).with_name('p2c_navigation_capture.py'))
    counts=Counter()
    with gzip.open(path,'rt') as stream:
        for line in stream:
            e=json.loads(line)
            assert len(base64.b64decode(e['cdr'],validate=True))>=4
            assert math.isfinite(e['received_sim_time']) and e['received_wall_ns']>0
            counts[e['topic']]+=1
    markers=[line.removeprefix('NAVIGATION_CAPTURE_CLOSED ') for line in (directory/'observer.log').read_text().splitlines()
             if line.startswith('NAVIGATION_CAPTURE_CLOSED ')]
    assert len(markers)==1 and json.loads(markers[0])==dict(counts),'incomplete navigation trace'
    if row['case']!='empty_battery':
        required={'/merge_map'}|{f'/tb{i}/{suffix}' for i in range(1,row['result']['robot_count']+1)
            for suffix in ('map','gateway/merge_map','global_costmap/costmap','local_costmap/costmap','scan','odom','tf','tf_static')}
        assert required<=counts.keys(),('missing navigation inputs',sorted(required-counts.keys()))
    return dict(status='PASS',messages=sum(counts.values()),topic_counts=dict(counts),control_input=False)


def launch_process_audit(directory):
    """Reject task-time child crashes; retain subsequent owned cleanup exits."""
    files=sorted((directory/'launch').glob('*.log'));assert files,'missing actual launch transcript'
    cleanup=[]
    for path in files:
        closing=False
        for number,line in enumerate(path.read_text().splitlines(),1):
            if '[launch]: user interrupted with ctrl-c (SIGINT)' in line:closing=True
            match=re.search(r'\[([^\]]+)\]: process has died \[pid \d+, exit code (-?\d+),',line)
            if not match:continue
            code=int(match[2])
            assert closing or code==0,('task-time child failure',str(path),number,match[1],code)
            if closing:cleanup.append(dict(file=path.name,line=number,node=match[1],exit_code=code))
        assert closing,('missing owned launch closure',str(path))
    return dict(status='PASS',launch_transcripts=len(files),task_time_nonzero_child_exits=0,
        post_task_cleanup_exits=cleanup)


def return_audit(path,require_pose_leases=False,require_map_candidates=False):
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
                if require_pose_leases and starts[key].get('reason')=='no_known_route':
                    predicted=starts[key]['budget']
                    assert not (predicted['path_distance_m']==0 and
                        starts[key]['energy']>predicted['required_energy']), 'funded temporary hold became a charger top-up'
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
                budget.get('map_input_age_sec',budget['map_age_sec']),budget['pose_age_sec'])
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
                m['path_factor'],m['nominal_speed_mps'],m['safety_margin'],m['recovery_wait_sec'],
                budget.get('map_input_age_sec',budget['map_age_sec']),
                budget.get('pose_age_sec',0.))
            assert math.isclose(rebuilt['required_energy'],budget['required_energy'],abs_tol=1e-8)
            if budget.get('route'):
                assert abs(sum(math.dist(a,b) for a,b in zip(budget['route'],budget['route'][1:]))-distance)<1e-8
            maps+=1
            candidates=saved.get('route_candidates',[])
            if require_map_candidates:assert candidates,'missing complete map-candidate evidence'
            if candidates:
                decoded={}
                for candidate in candidates:
                    s=candidate['map_evidence']
                    assert s['source'] not in decoded and 0<=e['sim_time']-s['source_time']<=5.
                    g=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
                    decoded[s['source']]=(s,g)
                local=decoded.get('local');eligible=[]
                assert set(decoded) <= {'local','delivered_fused','constrained_fused'}
                if 'constrained_fused' in decoded:
                    fused=decoded['delivered_fused'];derived,g=decoded['constrained_fused']
                    assert local is not None
                    rebuilt_grid=control.constrained_return_grid(fused[1],fused[0]['resolution'],fused[0]['origin'],
                        dict(data=local[1],resolution=local[0]['resolution'],origin=local[0]['origin']))
                    assert np.array_equal(g,rebuilt_grid), 'derived search grid changed a source obstacle'
                    assert derived['resolution']==fused[0]['resolution'] and derived['origin']==fused[0]['origin']
                    assert derived['source_time']==min(local[0]['source_time'],fused[0]['source_time'])
                    assert derived['version']==max(local[0]['version'],fused[0]['version'])
                for candidate in candidates:
                    s=candidate['map_evidence'];g=decoded[s['source']][1]
                    d,r=control.known_return_route(g,s['resolution'],s['origin'],position,e['home'],e['charge_radius_m'],include_route=True)
                    assert (d is None)==(candidate['path_distance_m'] is None)
                    if d is not None:assert math.isclose(d,candidate['path_distance_m'],abs_tol=1e-8)
                    qualified=d is not None and (s['source']=='local' or local is None
                        or control.route_respects_known_obstacles(local[1],local[0]['resolution'],local[0]['origin'],r))
                    assert candidate['qualified']==qualified
                    input_age=max(e['sim_time']-s['source_time'],e['sim_time']-local[0]['source_time']) if s['source']!='local' and local else e['sim_time']-s['source_time']
                    assert math.isclose(input_age,candidate['map_input_age_sec'],abs_tol=1e-8)
                    required=None if d is None else control.return_energy_budget(d,m['move_cost_per_m'],m['idle_cost_per_sec'],
                        m['path_factor'],m['nominal_speed_mps'],m['safety_margin'],m['recovery_wait_sec'],input_age,budget['pose_age_sec'])['required_energy']
                    if required is None:assert candidate['required_energy'] is None
                    else:assert math.isclose(required,candidate['required_energy'],abs_tol=1e-8)
                    if qualified:eligible.append((required,s['source']!='local',s))
                best=min(eligible,key=lambda row:row[:2])
                assert best[2]['source']==saved['source'] and best[2]['version']==saved['version']
                assert math.isclose(best[0],budget['required_energy'],abs_tol=1e-8)
        if kind=='return_leg_sent':
            assert budget is not None and e['energy']>e['energy_model']['safety_margin']
            assert saved is not None and e['route'];legs+=1
    assert set(starts)==set(finished),('unclosed return prediction',set(starts)-set(finished))
    return dict(status='PASS',return_triggers=len(starts),map_budget_reconstructions=maps,
        pose_lease_reconstructions=pose_checks,pose_leases_required=require_pose_leases,
        local_legs=legs,charger_returns=sum(r['outcome']=='charger_stopped' for r in rows),returns=rows)


def budget_evaluation_time(event, witness, key, required=False):
    if required:assert key in witness, ('missing budget evaluation instant', key)
    evaluated=witness.get(key,event['event_time'])
    assert math.isfinite(evaluated) and evaluated<=event['event_time']
    if not required:
        return evaluated  # Historical cohorts retain their original evidence contract.
    for stream,sample in event['inputs'].items():
        if stream=='headquarters/target_detection':continue
        assert sample['source_time'] is not None
        assert 0<=event['event_time']-sample['source_time']<=sample['ttl_sec']
        assert math.isclose(event['event_time']-sample['source_time'],sample['age_sec'],abs_tol=1e-8)
        assert 0<=evaluated-sample['source_time']<=sample['ttl_sec']
    return evaluated


def planning_lease_audit(records):
    count=0;stages={}
    for e in records:
        if e.get('event')!='coordinator_planning_lease_expired':continue
        started=e['planning_started_at_sec'];ended=e['event_time'];inputs=e['inputs_at_start']
        leases=[sample for key,sample in inputs.items() if key!='headquarters/target_detection']
        assert leases and all(sample['source_time'] is not None for sample in leases)
        for sample in leases:
            assert 0<=started-sample['source_time']<=sample['ttl_sec']
            assert math.isclose(started-sample['source_time'],sample['age_sec'],abs_tol=1e-8)
        deadline=min(sample['source_time']+sample['ttl_sec'] for sample in leases)
        assert math.isclose(deadline,e['source_deadline_sec'],abs_tol=1e-8)
        assert ended<started or ended>deadline
        stages[e['stage']]=stages.get(e['stage'],0)+1;count+=1
    return dict(status='PASS',abandoned_expired_plans=count,stages=stages)


def lookahead_audit(records,require_compound_pose=False,require_live_clock=False):
    count=0
    for e in records:
        if e.get('event')!='coordinator_charge_decision' or not e.get('opportunity_lookahead'):
            continue
        f=e['opportunity_lookahead'];saved=f['map_evidence'];state=f['battery_state']
        evaluated=budget_evaluation_time(e,f,'evaluated_at_sec',require_live_clock)
        assert f['strategy']=='two_current_frontiers' and saved['source']=='ap_delivered_planning_map'
        assert saved['encoding']=='zlib_base64_int16_le'
        assert f['first_group']!=f['second_group']
        assert math.dist(f['first_position'],f['second_position'])>=control.MIN_TARGET_SEPARATION_M
        assert math.isclose(evaluated-saved['source_time'],f['map_age_sec'],abs_tol=1e-8)
        assert e['inputs']['headquarters/fused_map_snapshot']['source_time']==saved['source_time']
        ages=f.get('pose_source_ages_sec')
        if require_compound_pose:assert ages is not None and set(ages)=={'odom','frame'}
        if ages is None:
            assert math.isclose(e['inputs'][e['robot']+'/pose_state']['age_sec']-(e['event_time']-evaluated),f['pose_age_sec'],abs_tol=1e-8)
        else:
            for key,kind in (('odom','pose_state'),('frame','frame_state')):
                if key in ages:assert math.isclose(ages[key],e['inputs'][e['robot']+'/'+kind]['age_sec']-(e['event_time']-evaluated),abs_tol=1e-8)
            assert all(math.isfinite(age) and 0<=age<=2. for age in ages.values())
            assert math.isclose(max(ages.values()),f['pose_age_sec'],abs_tol=1e-8)
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
        local=f.get('local_map_evidence')
        local_geometry=None
        if local:
            assert local['source']=='ap_delivered_robot_map'
            assert local['source_time']==e['inputs'][e['robot']+'/map_snapshot']['source_time']
            assert 0<=e['event_time']-local['source_time']<=5.
            local_raw=np.frombuffer(zlib.decompress(base64.b64decode(local['grid'])),dtype='<i2').reshape(local['shape'])
            local_geometry=dict(data=local_raw,resolution=local['resolution'],origin=local['origin'])
        candidates=control.qualified_return_candidates(raw,saved['resolution'],saved['origin'],second,
            f['home'],state.get('charge_radius_m',.8),local_geometry)
        home_distance=min((r['path_distance_m'] for r in candidates if r['qualified']),default=None)
        assert home_distance is not None and math.isclose(home_distance,f['home_distance_m'],abs_tol=1e-8)
        input_age=max(f['map_age_sec'],evaluated-local['source_time']) if local else f['map_age_sec']
        assert math.isclose(f.get('map_input_age_sec',f['map_age_sec']),input_age,abs_tol=1e-8)
        required=control.battery_assignment_required_energy(f['first_path_distance_m']+between,home_distance,
            state.get('move_cost_per_m',1.),state.get('idle_cost_per_sec',.02),state.get('return_path_factor',2.),
            state.get('nominal_speed_mps',.18),state.get('return_safety_margin',8.),
            state.get('return_recovery_wait_sec',30.),input_age,f['pose_age_sec'])
        assert math.isclose(required,f['required_energy'],abs_tol=1e-8)
        count+=1
    return dict(status='PASS',two_frontier_charge_decisions=count)


def exploration_travel_audit(records,required=False,require_commitment=False,require_bounded_commitment=False,
        require_initial_search=False,require_diversity=False,require_camera_search=False,require_live_clock=False):
    """Rebuild executed frontier travel and delivered-only energy witnesses."""
    count=0;discounts=0;resumed=0;visual_count=0;diversity_count=0;camera_count=0
    for e in records:
        if e.get('event')!='coordinator_navigation_decision' or e.get('kind') not in ('exploration','initial_visual_search'):continue
        f=e.get('travel_preference')
        if required:assert f is not None,'missing executed exploration travel witness'
        if f is None:continue
        assert f['strategy']=='relative_geodesic_travel'
        now=e['event_time'];geometry={}
        ranked_at=budget_evaluation_time(e,f,'ranking_time_sec',require_live_clock)
        for key,stream,source,s in [
            ('planning','headquarters/fused_map_snapshot','ap_delivered_planning_map',e['planning_map']),
            ('source','headquarters/fused_map_snapshot','ap_delivered_fused_map',e['source_map']),
            *[(name,name+'/map_snapshot','ap_delivered_robot_map',s) for name,s in e['return_maps'].items()]]:
            assert s['source']==source and s['encoding']=='zlib_base64_int16_le'
            assert s['source_time']==e['inputs'][stream]['source_time'] and 0<=now-s['source_time']<=5.
            g=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
            geometry[key]=dict(data=g,resolution=s['resolution'],origin=s['origin'])
        raw=geometry['planning'];original=geometry['source']['data'].copy()
        assert raw['resolution']==geometry['source']['resolution'] and raw['origin']==geometry['source']['origin']
        for r,c in e['self_return_cells'].values():
            assert 1<=r<original.shape[0]-1 and 1<=c<original.shape[1]-1
            assert original[r,c]>=control.OCCUPIED_THRESHOLD
            window=original[r-1:r+2,c-1:c+2].copy();window[1,1]=0
            assert np.all(window==0) and raw['resolution']*math.sqrt(2)<=.1
            original[r,c]=0
        assert np.array_equal(original,raw['data'])
        positions=e['robot_positions'];name=e['robot'];target=f['target']
        assert np.allclose(positions[name],e['current_position'],rtol=0,atol=1e-8)
        blocked=[p for peer,p in positions.items() if peer!=name and p is not None]
        assert f['blocked_positions']==blocked
        assert f['nominal_blocked_positions'] in ([],blocked)
        traversable=control.traversable_grid(raw['data'],raw['resolution'],control.PATH_CLEARANCE_M)
        cell=control.world_to_grid(*target,raw['resolution'],*raw['origin'])
        def distance(peer,blocks=()):
            mask=control.block_dynamic_positions(traversable,raw['resolution'],raw['origin'],blocks)
            field=control.exploration_distance_field(raw['data'],mask,raw['resolution'],raw['origin'],positions[peer])
            return float('inf') if field is None else float(field[cell])
        nominal=distance(name,f['nominal_blocked_positions']);planned=distance(name,blocked)
        assert math.isfinite(nominal) and math.isfinite(planned)
        assert math.isclose(nominal,f['own_nominal_distance_m'],abs_tol=1e-8)
        assert math.isclose(planned,f['planned_distance_m'],abs_tol=1e-8)
        states=e['battery_states']
        def energy(peer,d,evaluated):
            state=states[peer];ages=[]
            for kind,ttl in (('pose_state',2.),('frame_state',2.),('battery_state',5.)):
                lease=e['inputs'][peer+'/'+kind];age=evaluated-lease['source_time']
                assert 0<=age<=ttl and math.isclose(now-lease['source_time'],lease['age_sec'],abs_tol=1e-8)
                if kind!='battery_state':ages.append(age)
            assert state['mode']=='ACTIVE' and state['stamp_sec']==e['inputs'][peer+'/battery_state']['source_time']
            local=geometry.get(peer);home=(state['charge_x'],state['charge_y'])
            map_age=max(evaluated-e['planning_map']['source_time'],evaluated-e['return_maps'][peer]['source_time']) if local else evaluated-e['planning_map']['source_time']
            def budget(task_distance,destination):
                candidates=control.qualified_return_candidates(raw['data'],raw['resolution'],raw['origin'],destination,
                    home,state.get('charge_radius_m',.8),local)
                contact=min((r['path_distance_m'] for r in candidates if r['qualified']),default=None)
                if contact is None:return float('inf')
                return control.battery_assignment_required_energy(task_distance,contact,
                    state.get('move_cost_per_m',1.),state.get('idle_cost_per_sec',.02),state.get('return_path_factor',2.),
                    state.get('nominal_speed_mps',.18),state.get('return_safety_margin',8.),
                    state.get('return_recovery_wait_sec',30.),map_age,max(ages))
            return max(budget(d,target),budget(0.,positions[peer]))
        peers={}
        assert name in f['eligible_robot_names'] and len(set(f['eligible_robot_names']))==len(f['eligible_robot_names'])
        for peer in f['eligible_robot_names']:
            if peer==name:continue
            d=distance(peer)
            if not math.isfinite(d) or d>=nominal:continue
            cost=None if states is None else energy(peer,d,ranked_at)
            if cost is not None and (not math.isfinite(cost) or states[peer]['energy']<=cost):continue
            peers[peer]=dict(distance_m=d,required_energy=cost)
        assert set(peers)==set(f['peers'])
        for peer,row in peers.items():
            assert math.isclose(row['distance_m'],f['peers'][peer]['distance_m'],abs_tol=1e-8)
            if row['required_energy'] is None:assert f['peers'][peer]['required_energy'] is None
            else:assert math.isclose(row['required_energy'],f['peers'][peer]['required_energy'],abs_tol=1e-8)
        factor=control.relative_travel_factor(nominal,[r['distance_m'] for r in peers.values()])
        assert math.isclose(factor,f['factor'],abs_tol=1e-8)
        diversity=f.get('mission_spatial_diversity');diversity_factor=1.
        if require_diversity:assert diversity is not None,'missing executed mission spatial preference'
        if diversity is not None:
            visits=diversity['visits'];bins=set()
            for visit in visits:
                assert visit['source']=='ap_delivered_pose_history' and visit['robot'] in positions
                p=visit['position'];assert len(p)==2 and all(math.isfinite(v) for v in p)
                observed=visit['observed_at_sec'];assert 0<=observed<=now
                assert all(0<=observed-visit[k]<=2. for k in ('pose_source_time','frame_source_time'))
                key=tuple(math.floor(v/control.INITIAL_SEARCH_VISIT_BIN_M) for v in p)
                assert key not in bins;bins.add(key)
            rebuilt=control.mission_search_diversity(target,states,visits,
                raw['data'],raw['resolution'],raw['origin'])
            assert rebuilt==diversity,'spatial preference differs from delivered models/history'
            diversity_factor=rebuilt['factor'];diversity_count+=1
        assert math.isclose(f['base_utility']*f['battery_factor']*factor*diversity_factor,f['adjusted_utility'],abs_tol=1e-8)
        visual=e['kind']=='initial_visual_search'
        if visual:
            if require_bounded_commitment:assert require_initial_search,'undeclared initial visual search'
            if diversity is not None:assert diversity['visits']==f['initial_search_visits']
            assert f['search_kind']=='known_space'
            assert control.traversable_grid(raw['data'],raw['resolution'],control.ROBOT_CLEARANCE_M)[cell]
            visits=f['initial_search_visits'];bins=set()
            for visit in visits:
                assert visit['source']=='ap_delivered_pose_history' and visit['robot'] in positions
                p=visit['position'];assert len(p)==2 and all(math.isfinite(v) for v in p)
                observed=visit['observed_at_sec'];assert 0<=observed<=now
                assert all(0<=observed-visit[k]<=2. for k in ('pose_source_time','frame_source_time'))
                key=tuple(math.floor(v/control.INITIAL_SEARCH_VISIT_BIN_M) for v in p)
                assert key not in bins;bins.add(key)
            points=[v['position'] for v in visits]+[p for p in positions.values() if p is not None]
            views=f.get('initial_search_views')
            if require_camera_search:assert views,'missing delivered camera heading history'
            if views is not None:
                assert f['search_view_model']==dict(radius_m=control.INFORMATION_RADIUS_M,
                    fov_rad=control.INITIAL_SEARCH_VIEW_FOV_RAD,heading_bins=16)
                bins=set()
                for view in views:
                    assert view['source']=='ap_delivered_pose_and_heading_history' and view['robot'] in positions
                    p=view['position'];yaw=view['yaw'];observed=view['observed_at_sec']
                    assert len(p)==2 and all(math.isfinite(v) for v in p) and -math.pi<=yaw<=math.pi
                    assert 0<=observed<=now
                    assert all(0<=observed-view[k]<=2. for k in ('pose_source_time','frame_source_time'))
                    key=(*(math.floor(v/control.INITIAL_SEARCH_VISIT_BIN_M) for v in p),
                        math.floor((yaw+math.pi)/(2.*math.pi/16))%16)
                    assert key not in bins;bins.add(key)
                interest=control.camera_search_interest(raw['data'],raw['resolution'],raw['origin'],views)
                camera_count+=1
            else:
                interest=control.known_search_interest(raw['data'],raw['resolution'],raw['origin'],points)
            gain,yaw=control.known_search_view(raw['data'],cell,control.INFORMATION_RADIUS_M/raw['resolution'],interest)
            assert gain==f['information_gain'] and gain>0
            assert math.isclose(yaw,f['view_yaw'],abs_tol=1e-8)
            assert f['nominal_blocked_positions']==blocked
            if control.world_to_grid(*e['requested_position'],raw['resolution'],*raw['origin'])==cell:
                delta=math.atan2(math.sin(e['requested_yaw']-yaw),math.cos(e['requested_yaw']-yaw))
                assert abs(delta)<1e-8
            visual_count+=1
        elif require_commitment:
            assert math.isfinite(f['information_gain']) and f['information_gain']>0
            gain=control.visible_unknown_gain(raw['data'],cell,control.INFORMATION_RADIUS_M/raw['resolution'])
            assert gain==f['information_gain'],'current viewpoint gain differs from delivered grid'
        if 'resume_intent' in f:
            intent=f['resume_intent'];assert len(intent)==3 and all(math.isfinite(x) for x in intent)
            assert math.dist(target,intent[:2])<=control.MIN_TARGET_SEPARATION_M
            assert f['information_gain']>max(control.MIN_REMAINING_GAIN,intent[2]*control.MIN_REMAINING_GAIN_FRACTION)
            assert f['battery_factor']==1.
            resumed+=1
        if require_bounded_commitment:
            group=f['frontier_group_id']
            if visual:
                assert group==cell[0]*raw['data'].shape[1]+cell[1] and f['frontier_group_size']==1
            else:
                groups=control.frontier_groups(raw['data'])
                assert isinstance(group,int) and 0<=group<len(groups)
                assert f['frontier_group_size']==len(groups[group])
            exclusions=f['excluded_targets']
            assert all(len(p)==2 and all(math.isfinite(v) for v in p) for p in exclusions)
            if visual:
                assert all(math.dist(target,p)>=control.MIN_TARGET_SEPARATION_M for p in exclusions)
                base=f['information_gain']/(nominal+1.)
            else:
                base=control.exploration_utility(f['information_gain'],f['frontier_group_size'],nominal)
                base*=control.target_reuse_penalty(target,exclusions)
            assert math.isclose(base,f['base_utility'],abs_tol=1e-8),'base utility differs from delivered geometry'
            weight=control.FRONTIER_CONTINUATION_WEIGHT if 'resume_intent' in f else 1.
            assert f['continuation_weight']==weight
            score=control.frontier_scheduling_score(f['adjusted_utility'],'resume_intent' in f)
            assert math.isclose(score,f['scheduling_score'],abs_tol=1e-8)
        if states is not None:
            priced_at=budget_evaluation_time(e,f,'required_energy_evaluated_at_sec',require_live_clock)
            cost=energy(name,planned,priced_at)
            assert math.isfinite(cost) and cost<states[name]['energy']
            assert math.isclose(cost,f['required_energy'],abs_tol=1e-8)
            assert f['battery_factor']==1.
        count+=1;discounts+=int(factor<1.)
    return dict(status='PASS',executed_frontier_witnesses=count,relative_travel_discounts=discounts,
        resumed_frontier_witnesses=resumed,required=required,commitment_required=require_commitment,
        bounded_commitment_required=require_bounded_commitment,initial_visual_witnesses=visual_count,
        initial_search_required=require_initial_search,spatial_diversity_witnesses=diversity_count,
        camera_aware_visual_witnesses=camera_count,camera_search_required=require_camera_search)


def target_survey_audit(records, declared=False, radius_m=None, position_tolerance_m=None, require_live_clock=False):
    """Rebuild target-local gain and the actually admitted, funded survey leg."""
    count=0
    for e in records:
        if e.get('event')!='coordinator_navigation_decision' or e.get('kind')!='target_information_survey':continue
        assert declared,'undeclared target information survey'
        assert e['task_phase']=='FOUND'
        s=e['target_survey_selection'];name=e['robot'];now=e['event_time']
        assert s['strategy']=='target_area_gain_per_travel'
        if radius_m is not None:assert s['radius_m']==radius_m
        if position_tolerance_m is not None:assert s['position_tolerance_m']==position_tolerance_m
        lease=e['inputs']['headquarters/target_detection'];age=now-lease['source_time']
        assert 0<=age<=60. and math.isclose(age,lease['age_sec'],abs_tol=1e-8)
        geometry={}
        for key,stream,source,saved in [
            ('planning','headquarters/fused_map_snapshot','ap_delivered_planning_map',e['planning_map']),
            ('source','headquarters/fused_map_snapshot','ap_delivered_fused_map',e['source_map']),
            *[(peer,peer+'/map_snapshot','ap_delivered_robot_map',g) for peer,g in e['return_maps'].items()]]:
            assert saved['source']==source and saved['encoding']=='zlib_base64_int16_le'
            assert saved['source_time']==e['inputs'][stream]['source_time'] and 0<=now-saved['source_time']<=5.
            raw=np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape'])
            geometry[key]=dict(data=raw,resolution=saved['resolution'],origin=saved['origin'])
        g=geometry['planning'];source=geometry['source'];rebuilt=source['data'].copy()
        assert g['resolution']==source['resolution'] and g['origin']==source['origin']
        for row,column in e['self_return_cells'].values():
            assert 1<=row<rebuilt.shape[0]-1 and 1<=column<rebuilt.shape[1]-1
            assert rebuilt[row,column]>=control.OCCUPIED_THRESHOLD
            window=rebuilt[row-1:row+2,column-1:column+2].copy();window[1,1]=0
            assert np.all(window==0) and g['resolution']*math.sqrt(2)<=.1
            rebuilt[row,column]=0
        assert np.array_equal(rebuilt,g['data'])
        positions=e['robot_positions'];modes=e['battery_modes'];choice=s['choice']
        assert choice['robot']==name and modes[name]=='ACTIVE'
        assert np.allclose(positions[name],e['current_position'],rtol=0,atol=1e-8)
        for peer,mode in modes.items():
            if mode!='ACTIVE':continue
            for kind,ttl in (('pose_state',2.),('frame_state',2.),('map_snapshot',5.)):
                lease=e['inputs'][peer+'/'+kind];age=now-lease['source_time']
                assert 0<=age<=ttl and math.isclose(age,lease['age_sec'],abs_tol=1e-8)
        ranked=control.target_survey_candidates(g['data'],g['resolution'],g['origin'],
            positions,modes,s['target'],s['radius_m'],s['position_tolerance_m'])
        assert choice in ranked,'survey gain/travel/ranking does not match delivered inputs'
        blocked=[p for peer,p in positions.items() if peer!=name and p is not None]
        desired=control.RallyPose(*choice['desired_position'],choice['desired_yaw'])
        matched=False;limit=control.MAX_NAVIGATION_LEG_M
        while limit>=control.USEFUL_TRAVEL_M:
            plan=control.plan_rally_leg(desired,g['data'],g['resolution'],g['origin'],
                positions[name],limit,blocked_positions=blocked,visible_only=True)
            plan=control.reserve_rally_prefix(plan,s['reserved_routes'])
            if plan is not None and plan[0] is not None:
                pose,route=plan
                if (len(route)==len(s['admitted_route'])
                        and np.allclose(route,s['admitted_route'],rtol=0,atol=1e-8)
                        and np.allclose((pose.x,pose.y),e['requested_position'],rtol=0,atol=1e-8)):
                    matched=True;break
            limit/=2
        assert matched,'survey prefix does not match known-free body/reservation plan'
        route=s['admitted_route'];distance=math.dist(positions[name],route[0])+sum(
            math.dist(a,b) for a,b in zip(route,route[1:]))
        assert math.isclose(distance,s['admitted_distance_m'],abs_tol=1e-8)
        assert math.dist(positions[name],e['requested_position'])>s['position_tolerance_m']
        states=e['battery_states']
        if states is None:assert s['required_energy'] is None
        else:
            evaluated=budget_evaluation_time(e,s,'required_energy_evaluated_at_sec',require_live_clock)
            state=states[name];lease=e['inputs'][name+'/battery_state']
            assert state['mode']=='ACTIVE' and state['stamp_sec']==lease['source_time']
            assert 0<=now-lease['source_time']<=5.
            pose_age=max(evaluated-e['inputs'][name+'/'+kind]['source_time'] for kind in ('pose_state','frame_state'))
            local=geometry.get(name);map_age=max(evaluated-e['planning_map']['source_time'],
                evaluated-e['return_maps'][name]['source_time']) if local else evaluated-e['planning_map']['source_time']
            def budget(task_distance,destination):
                candidates=control.qualified_return_candidates(g['data'],g['resolution'],g['origin'],
                    destination,(state['charge_x'],state['charge_y']),state.get('charge_radius_m',.8),local)
                contact=min((r['path_distance_m'] for r in candidates if r['qualified']),default=None)
                assert contact is not None,'survey has no qualified whole return'
                return control.battery_assignment_required_energy(task_distance,contact,
                    state.get('move_cost_per_m',1.),state.get('idle_cost_per_sec',.02),
                    state.get('return_path_factor',2.),state.get('nominal_speed_mps',.18),
                    state.get('return_safety_margin',8.),state.get('return_recovery_wait_sec',30.),map_age,pose_age)
            required=max(budget(distance,e['requested_position']),budget(0.,positions[name]))
            assert math.isclose(required,s['required_energy'],abs_tol=1e-8) and state['energy']>required
        count+=1
    return dict(status='PASS',target_information_survey_witnesses=count,declared=declared)


def ap_return_veto_audit(records):
    count=0
    for e in records:
        if e.get('event')!='coordinator_return_map_veto':continue
        maps=[]
        for key,stream,source in (('fused_map','headquarters/fused_map_snapshot','ap_delivered_planning_map'),
                                  ('local_map',e['robot']+'/map_snapshot','ap_delivered_robot_map')):
            s=e[key];assert s['source']==source and s['encoding']=='zlib_base64_int16_le'
            assert s['source_time']==e['inputs'][stream]['source_time']
            assert 0<=e['event_time']-s['source_time']<=5.
            g=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
            maps.append(dict(data=g,resolution=s['resolution'],origin=s['origin']))
        fused,local=maps
        actual=control.qualified_return_candidates(fused['data'],fused['resolution'],fused['origin'],
            e['destination'],e['home'],e['radius'],local)
        assert len(actual)==len(e['candidates']) and len(actual)>=2
        for rebuilt,saved in zip(actual,e['candidates']):
            assert rebuilt['source']==saved['source'] and rebuilt['qualified']==saved['qualified']
            assert (rebuilt['path_distance_m'] is None)==(saved['path_distance_m'] is None)
            if rebuilt['path_distance_m'] is not None:
                assert math.isclose(rebuilt['path_distance_m'],saved['path_distance_m'],abs_tol=1e-8)
            assert np.allclose(rebuilt['route'],saved['route'])
        assert not any(r['qualified'] for r in actual) and any(r['path_distance_m'] is not None for r in actual)
        count+=1
    return dict(status='PASS',delivered_return_vetoes=count)


def rally_assignment_audit(records):
    count=0;chosen=0;wall=[]
    for e in records:
        if e.get('event') not in ('coordinator_rally_assignment_failed','coordinator_rally_assignment_chosen'):continue
        geometry={}
        declared=[('planning_map','headquarters/fused_map_snapshot','ap_delivered_planning_map',e['planning_map']),
                  ('source_map','headquarters/fused_map_snapshot','ap_delivered_fused_map',e['source_map'])]
        declared.extend((name,name+'/map_snapshot','ap_delivered_robot_map',s) for name,s in e['return_maps'].items())
        for key,stream,source,s in declared:
            assert s['source']==source and s['encoding']=='zlib_base64_int16_le'
            assert s['source_time']==e['inputs'][stream]['source_time']
            assert 0<=e['event_time']-s['source_time']<=5.
            raw=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
            geometry[key]=dict(data=raw,resolution=s['resolution'],origin=s['origin'])
        planned,source=geometry['planning_map'],geometry['source_map']
        assert planned['resolution']==source['resolution'] and planned['origin']==source['origin']
        original=source['data'].copy()
        for cell in e['self_return_cells'].values():
            r,c=cell;assert 1<=r<original.shape[0]-1 and 1<=c<original.shape[1]-1
            assert original[r,c]>=control.OCCUPIED_THRESHOLD
            window=original[r-1:r+2,c-1:c+2].copy();window[1,1]=0
            assert np.all(window==0) and planned['resolution']*math.sqrt(2)<=.1
            original[r,c]=0
        assert np.array_equal(original,planned['data'])
        rebuilt=control.assign_rally_poses(planned['data'],planned['resolution'],planned['origin'],
            e['robot_positions'],e['target'],objective=e['objective'],
            battery_states=e['battery_states'],observer_robot=e['observer_robot'],
            current_positions=e['current_positions'],hold_sec=e['hold_sec'],
            return_maps={name:geometry[name] for name in e['return_maps']})
        if e['event']=='coordinator_rally_assignment_failed':
            assert len(rebuilt)!=len(e['robot_positions']);count+=1
        else:
            assert len(rebuilt)==len(e['robot_positions'])
            assert set(e['assignment'])==set(rebuilt)
            for name,pose in rebuilt.items():
                assert np.allclose(e['assignment'][name],(pose.x,pose.y,pose.yaw),atol=1e-8,rtol=0)
            chosen+=1
        assert math.isfinite(e['computation_wall_sec']) and e['computation_wall_sec']>=0
        wall.append(e['computation_wall_sec'])
    return dict(status='PASS',failed_assignments_rebuilt=count,chosen_assignments_rebuilt=chosen,computation_wall_sec=wall)


def rally_proposal_audit(records, required=False):
    """Bind retained points to their original search and a new delivered epoch."""
    proposals={};count=0;deferred=0
    for e in records:
        if e.get('event')=='coordinator_rally_assignment_chosen':
            proposals[e['event_time']]=e
        if e.get('event')!='coordinator_rally_proposal_admitted':continue
        original=proposals[e['proposal_evaluated_at_sec']]
        assert e['assignment']==original['assignment'] and e['target']==original['target']
        assert set(e['required_robots'])==set(e['assignment'])==set(original['robot_positions'])
        assert len(e['dispatch_order'])==len(e['assignment']) and set(e['dispatch_order'])==set(e['assignment'])
        assert e['event_time']>=original.get('computation_completed_at_sec',original['event_time'])
        assert e['budget_reused'] is False
        required_inputs={'headquarters/fused_map_snapshot','headquarters/target_detection'}|{
            name+'/'+kind for name in e['required_robots'] for kind in ('pose_state','frame_state','map_snapshot')}
        if original['battery_states'] is not None:
            required_inputs|={name+'/battery_state' for name in e['required_robots']}
        assert required_inputs<=e['inputs'].keys()
        for stream,sample in e['inputs'].items():
            kind=stream.split('/')[-1]
            ttl=control.TARGET_DETECTION_TTL_SEC if kind=='target_detection' else control.STATE_TTL_SEC[kind]
            assert sample['source_time'] is not None and 0<=sample['ttl_sec']<=ttl
            age=e['event_time']-sample['source_time']
            assert 0<=age<=sample['ttl_sec'] and math.isclose(age,sample['age_sec'],abs_tol=1e-8)
        maps=[]
        for key,source in [('planning_map','ap_delivered_planning_map'),('source_map','ap_delivered_fused_map')]:
            saved=e[key]
            assert saved['source']==source and saved['encoding']=='zlib_base64_int16_le'
            assert saved['source_time']==e['inputs']['headquarters/fused_map_snapshot']['source_time']
            maps.append(np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape']))
        saved=e['planning_map'];source=e['source_map']
        assert saved['resolution']==source['resolution'] and saved['origin']==source['origin']
        rebuilt=maps[1].copy()
        for cell in e['self_return_cells'].values():
            r,c=cell;assert 1<=r<rebuilt.shape[0]-1 and 1<=c<rebuilt.shape[1]-1
            assert rebuilt[r,c]>=control.OCCUPIED_THRESHOLD
            window=rebuilt[r-1:r+2,c-1:c+2].copy();window[1,1]=0
            assert np.all(window==0) and saved['resolution']*math.sqrt(2)<=.1
            rebuilt[r,c]=0
        assert np.array_equal(rebuilt,maps[0])
        safe=control.traversable_grid(maps[0],saved['resolution'],clearance_m=control.RALLY_CLEARANCE_M)
        points=[]
        poses={name:control.RallyPose(*values) for name,values in e['assignment'].items()}
        assert 0<e['target_view_distance_m']<=3.
        for pose in poses.values():
            point=(pose.x,pose.y);assert all(math.isfinite(v) for v in (*point,pose.yaw))
            cell=control.world_to_grid(*point,saved['resolution'],*saved['origin'])
            assert 0<=cell[0]<safe.shape[0] and 0<=cell[1]<safe.shape[1] and safe[cell]
            assert control.rally_target_view(maps[0],saved['resolution'],saved['origin'],point,e['target'],e['target_view_distance_m'])
            heading=math.atan2(e['target'][1]-pose.y,e['target'][0]-pose.x)
            assert abs(math.atan2(math.sin(pose.yaw-heading),math.cos(pose.yaw-heading)))<=1e-8
            assert all(math.dist(point,peer)>=control.RALLY_MIN_SEPARATION_M for peer in points)
            points.append(point)
        expected=(control.map_safe_rally_dispatch_order(maps[0],saved['resolution'],saved['origin'],poses,
            e['robot_positions'],e['target'],e['detecting_robot']) if e['map_safe_order'] else
            control.rally_dispatch_order(poses,e['robot_positions'],e['target'],e['detecting_robot']))
        assert expected==e['dispatch_order']
        count+=1
        deferred+=e['event_time']>original.get('computation_completed_at_sec',original['event_time'])
    assert not required or count>=1,'missing fresh geometric proposal admission'
    return dict(status='PASS',admitted_proposals=count,deferred_proposals=deferred,budget_reused=False)


def rally_repair_audit(records):
    count=0
    for e in records:
        if e.get('event')!='coordinator_rally_return_repair':continue
        name=e['robot'];maps=[]
        for key,stream,source in (('fused_map','headquarters/fused_map_snapshot','ap_delivered_planning_map'),
                                  ('local_map',name+'/map_snapshot','ap_delivered_robot_map')):
            s=e[key];assert s['source']==source and s['encoding']=='zlib_base64_int16_le'
            assert s['source_time']==e['inputs'][stream]['source_time']
            assert 0<=e['event_time']-s['source_time']<=5.
            g=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
            maps.append(dict(data=g,resolution=s['resolution'],origin=s['origin']))
        for stream,ttl in ((name+'/pose_state',2.),(name+'/frame_state',2.),(name+'/battery_state',5.)):
            lease=e['inputs'][stream];age=e['event_time']-lease['source_time']
            assert 0<=age<=ttl and math.isclose(age,lease['age_sec'],abs_tol=1e-8)
        map_age=max(e['event_time']-e[k]['source_time'] for k in ('fused_map','local_map'))
        pose_age=max(e['inputs'][name+'/'+k]['age_sec'] for k in ('pose_state','frame_state'))
        assert math.isclose(map_age,e['map_age_sec'],abs_tol=1e-8)
        assert math.isclose(pose_age,e['pose_age_sec'],abs_tol=1e-8)
        assert 0<=e['event_time']-e['target_source_time']<=60.
        state=e['state'];assert state['mode']=='ACTIVE' and state['stamp_sec']==e['inputs'][name+'/battery_state']['source_time']
        fused,local=maps;home=(state['charge_x'],state['charge_y'])
        old=control.qualified_return_candidates(fused['data'],fused['resolution'],fused['origin'],
            e['old_target'][:2],home,state.get('charge_radius_m',.8),local)
        assert not any(r['qualified'] for r in old),'Repaired an already qualified endpoint'
        rebuilt=control.funded_rally_replacement(fused['data'],fused['resolution'],fused['origin'],
            e['current_position'],e['target'],state,local,map_age,pose_age,e['reserved'],e['blocked'],
            e['hold_sec'],e['wait_sec'])
        assert rebuilt is not None
        pose,route,required=rebuilt
        assert np.allclose((pose.x,pose.y,pose.yaw),e['replacement'],atol=1e-8,rtol=0)
        assert np.allclose(route,e['route'],atol=1e-8,rtol=0)
        assert math.isclose(required,e['required_energy'],abs_tol=1e-8) and required<state['energy']
        count+=1
    return dict(status='PASS',funded_endpoint_repairs=count)


def energy_audit(path,result,required=False):
    snapshots={name:[] for name in result['robots']}
    for line in path.open():
        event=json.loads(line)['data']
        if not isinstance(event,dict) or event.get('event')!='energy_accounting':continue
        model=event['energy_model']
        spent=event['actual_distance_m']*model['move_cost_per_m']+event['actual_elapsed_sec']*model['idle_cost_per_sec']
        expected=max(0.,event['initial_energy']+event['charged_energy_added']-spent)
        assert math.isfinite(expected) and math.isclose(event['energy'],expected,abs_tol=1e-6)
        assert event['actual_distance_m']>=0 and event['actual_elapsed_sec']>=0
        assert 0<=event['pending_native_inputs']<=128
        assert event['initial_energy']==result['robots'][event['robot']]['battery_initial_energy']
        assert all(event.get(k) is None or event[k]<=event['sim_time']
                   for k in ('odom_source_time','frame_source_time'))
        rows=snapshots[event['robot']]
        if rows:
            assert event['energy_model']==rows[-1]['energy_model']
            assert event['actual_distance_m']>=rows[-1]['actual_distance_m']
            assert event['actual_elapsed_sec']>=rows[-1]['actual_elapsed_sec']
            assert event['charged_energy_added']>=rows[-1]['charged_energy_added']
        rows.append(event)
    if required:
        for name,robot in result['robots'].items():
            rows=snapshots[name];assert rows,('missing native energy accounting',name)
            assert rows[-1]['sim_time']>=result['end_sim_time_sec']-6.
            # Native truth motion cannot coexist with a frozen local energy meter.
            if robot['path_length_m']>1.:
                assert rows[-1]['actual_distance_m']>.1 and rows[-1]['actual_elapsed_sec']>0.
                assert rows[-1]['odom_source_time'] is not None
    return dict(status='PASS' if any(snapshots.values()) else 'LEGACY_NOT_INSTRUMENTED',
        required=required,snapshots=sum(len(rows) for rows in snapshots.values()),
        robots={name:dict(samples=len(rows),last=rows[-1] if rows else None) for name,rows in snapshots.items()})




def check_one(path,config):
    path=path.resolve()
    row=json.loads(path.read_text());directory=path.parent
    assert row['config']==config
    declaration_audit(row,config,directory)
    assert row['runner_returncode']==row['observer_returncode']==0
    assert not any(v for k,v in row.items() if k.endswith('_forced_shutdown'))
    for relative,expected in row['evidence_sha256'].items():assert sha(directory/relative)==expected
    navigation_inputs=navigation_capture_audit(row,directory)
    scan_filter=scan_self_filter_audit(row,directory)
    processes=launch_process_audit(directory) if config.get('task_child_process_audit') else None
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
    native_graph=original
    if config.get('native_tf_graph_capture'):
        graph_path=directory/'native_graph.json'
        assert graph_path.name in row['evidence_sha256'],'missing prospective native graph evidence'
        native_graph=json.loads(graph_path.read_text())
        assert '--native-tf-graph-output' in row['observer_command']
        assert Path(row['observer_command'][row['observer_command'].index('--native-tf-graph-output')+1])==graph_path
        assert not runtime_violations(Snapshot(native_graph['nodes']),audit,result['robot_count'])
        for key,filename in (('safety_observer','observe_p3b5.py'),('native_graph_reader','p2c_native_graph.py')):
            from run_p2d_baseline import file_digest
            assert row['source_digests'][key]==file_digest(Path(__file__).with_name(filename))
    ingress=native_tf_ingress_audit(native_graph,result['robot_count'],bool(config.get('native_filtered_tf')))
    native=return_audit(directory/'safety_events.jsonl',bool(config.get('native_pose_contract')),
        bool(config.get('return_source_selection')))
    energy=energy_audit(directory/'safety_events.jsonl',result,
        bool(config.get('native_energy_accounting')) and case!='empty_battery')
    forecast=lookahead_audit((json.loads(line) for line in (directory/'ledger.jsonl').open()),
        bool(config.get('ap_pose_budget_contract')),bool(config.get('coordinator_live_clock')))
    vetoes=ap_return_veto_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    assignments=rally_assignment_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    proposals=rally_proposal_audit((json.loads(line) for line in (directory/'ledger.jsonl').open()),
        bool(config.get('rally_proposal_handoff') and result.get('rally_assignments')))
    if config.get('rally_return_objective') and result.get('rally_assignments'):
        assert assignments['chosen_assignments_rebuilt']>=1, 'missing exact delivered assignment choice'
    repairs=rally_repair_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    travel=exploration_travel_audit((json.loads(line) for line in (directory/'ledger.jsonl').open()),
        bool(config.get('exploration_travel_preference')),bool(config.get('exploration_frontier_commitment')),
        bool(config.get('exploration_bounded_commitment')),bool(config.get('initial_known_space_search')),
        bool(config.get('mission_spatial_diversity')),bool(config.get('camera_aware_known_search')),
        bool(config.get('coordinator_live_clock')))
    surveys=target_survey_audit((json.loads(line) for line in (directory/'ledger.jsonl').open()),
        bool(config.get('target_information_survey')),result['target_max_distance_m'],result['rally_position_tolerance_m'],
        bool(config.get('coordinator_live_clock')))
    headings=observer_heading_audit((json.loads(line) for line in (directory/'ledger.jsonl').open()),
        bool(config.get('observer_heading_confirmation_gap')),result['target_max_distance_m'],
        result['rally_position_tolerance_m'],None if result['target_field_of_view_deg'] is None
        else math.radians(result['target_field_of_view_deg']))
    leases=planning_lease_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    preparations=return_preparation_audit(directory/'ledger.jsonl',bool(config.get('exploration_return_preparation')))
    dispatches=navigation_dispatch_audit(directory/'ledger.jsonl',bool(config.get('navigation_dispatch_boundary')))
    transit=transit_heading_audit(directory/'ledger.jsonl',bool(config.get('observed_rally_transit_heading')))
    if config.get('observed_rally_transit_heading'):
        from run_p2d_baseline import file_digest
        assert row['source_digests']['rally_transit_reader']==file_digest(Path(__file__).with_name('p2c_rally_transit_heading.py'))
    if config.get('navigation_dispatch_boundary'):
        from run_p2d_baseline import file_digest
        assert row['source_digests']['navigation_dispatch_reader']==file_digest(Path(__file__).with_name('p2c_navigation_dispatch.py'))
    if config.get('exploration_return_preparation'):
        from run_p2d_baseline import file_digest
        assert row['source_digests']['return_preparation_reader']==file_digest(Path(__file__).with_name('p2c_return_preparation.py'))
    assert result['collision_monitoring_active']
    return dict(case=case,status='PASS',git_commit=row['git_commit'],source_digests=row['source_digests'],
        result=result,raw_summary=str(path.resolve()),raw_summary_sha256=sha(path),return_audit=native,
        communication_audit=communications,lookahead_audit=forecast,native_energy_audit=energy,
        ap_return_veto_audit=vetoes,rally_assignment_audit=assignments,rally_proposal_audit=proposals,rally_repair_audit=repairs,
        exploration_travel_audit=travel,target_survey_audit=surveys,observer_heading_audit=headings,
        planning_lease_audit=leases,
        native_tf_ingress_audit=ingress,launch_process_audit=processes,navigation_input_audit=navigation_inputs,
        native_scan_self_filter_audit=scan_filter,exploration_return_preparation_audit=preparations,
        navigation_dispatch_boundary_audit=dispatches,observed_rally_transit_heading_audit=transit)


def observer_heading_audit(records,required=False,radius_m=3.,position_tolerance_m=.35,fov_rad=math.pi/2):
    """A recent delivered confirmation stays quiet; a lapsed heartbeat may turn."""
    quiet=turns=0
    if not required:return dict(status='PASS',required=False,quiet_holds=0,heading_turns=0)
    for e in records:
        is_quiet=e.get('event')=='coordinator_observer_heading_quiet_hold'
        is_turn=e.get('event')=='coordinator_navigation_decision' and e.get('kind')=='target_observation_heading'
        if not (is_quiet or is_turn):continue
        assert (radius_m is not None and fov_rad is not None
                and math.isfinite(radius_m) and radius_m>0
                and math.isfinite(fov_rad) and 0<fov_rad<=2*math.pi), 'heading witness lacks camera metadata'
        now=e['event_time'];name=e['robot'];inputs=e['inputs']
        lease=inputs['headquarters/target_detection'];age=now-lease['source_time']
        assert math.isclose(age,lease['age_sec'],abs_tol=1e-8) and 0<=age<=60.
        for kind,ttl in (('pose_state',2.),('frame_state',2.),('battery_state',5.)):
            state=inputs[name+'/'+kind];elapsed=now-state['source_time']
            assert 0<=elapsed<=ttl and math.isclose(elapsed,state['age_sec'],abs_tol=1e-8)
        if is_quiet:
            assert age<=5. and e['target_source_time']==lease['source_time']
            position=e['position'];target=e['target']
            heading=math.atan2(target[1]-position[1],target[0]-position[0])
            assert math.dist(position,target)<=radius_m-position_tolerance_m
            assert math.isclose(heading,e['desired_yaw'],abs_tol=1e-8)
            delta=math.atan2(math.sin(heading-e['yaw']),math.cos(heading-e['yaw']))
            assert abs(delta)>fov_rad/4.
            quiet+=1
        else:
            assert age>5.,'unnecessary observer turn during healthy delivered confirmation'
            assert np.allclose(e['current_position'],e['requested_position'],rtol=0,atol=1e-8)
            turns+=1
    return dict(status='PASS',required=True,quiet_holds=quiet,heading_turns=turns)


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
    p.add_argument('--blackout-root',type=Path)
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
    if config.get('initial_known_space_search') and a.cases is None and not errors:
        if not any(row['exploration_travel_audit']['initial_visual_witnesses'] for row in evidence):
            errors.append(dict(case='initial_known_space_search',error='new search algorithm was never exercised'))
    if config.get('target_information_survey') and a.cases is None and not errors:
        if not any(row['target_survey_audit']['target_information_survey_witnesses'] for row in evidence):
            errors.append(dict(case='target_information_survey',error='new survey algorithm was never exercised'))
    physical=None
    if not a.development and a.cases is None:
        try:
            assert a.blackout_root is not None,'full P2C integration requires --blackout-root with both new physical originals'
            from check_p2c_blackout import check_pair
            physical=check_pair(a.blackout_root,expected_commit=originals[0]['git_commit'],
                                reference_source_digests=originals[0]['source_digests'])
        except Exception as error:
            errors.append(dict(case='physical_blackout_pair',error=repr(error),traceback=traceback.format_exc()))
    result=dict(status='FAIL' if errors else 'PASS',scope='development' if a.development else 'integration',
        task_stack_frozen_commit=originals[0]['git_commit'],cases=len(summaries),errors=errors,evidence=evidence,
        full_declared_scope=a.cases is None,
        raw_failures_retained=True,physical_blackout_gate=physical or 'required_before_full_integration',
        general_hardware_safety_guarantee=False)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence'},indent=2))
    return int(bool(errors))

if __name__=='__main__':raise SystemExit(main())
