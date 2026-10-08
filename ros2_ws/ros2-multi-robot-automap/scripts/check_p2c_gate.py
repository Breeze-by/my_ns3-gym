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


def lookahead_audit(records,require_compound_pose=False):
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
        ages=f.get('pose_source_ages_sec')
        if require_compound_pose:assert ages is not None and set(ages)=={'odom','frame'}
        if ages is None:
            assert math.isclose(e['inputs'][e['robot']+'/pose_state']['age_sec'],f['pose_age_sec'],abs_tol=1e-8)
        else:
            for key,kind in (('odom','pose_state'),('frame','frame_state')):
                if key in ages:assert math.isclose(ages[key],e['inputs'][e['robot']+'/'+kind]['age_sec'],abs_tol=1e-8)
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
        input_age=max(f['map_age_sec'],e['event_time']-local['source_time']) if local else f['map_age_sec']
        assert math.isclose(f.get('map_input_age_sec',f['map_age_sec']),input_age,abs_tol=1e-8)
        required=control.battery_assignment_required_energy(f['first_path_distance_m']+between,home_distance,
            state.get('move_cost_per_m',1.),state.get('idle_cost_per_sec',.02),state.get('return_path_factor',2.),
            state.get('nominal_speed_mps',.18),state.get('return_safety_margin',8.),
            state.get('return_recovery_wait_sec',30.),input_age,f['pose_age_sec'])
        assert math.isclose(required,f['required_energy'],abs_tol=1e-8)
        count+=1
    return dict(status='PASS',two_frontier_charge_decisions=count)


def exploration_travel_audit(records,required=False,require_commitment=False):
    """Rebuild executed frontier travel and delivered-only energy witnesses."""
    count=0;discounts=0;resumed=0
    for e in records:
        if e.get('event')!='coordinator_navigation_decision' or e.get('kind')!='exploration':continue
        f=e.get('travel_preference')
        if required:assert f is not None,'missing executed exploration travel witness'
        if f is None:continue
        assert f['strategy']=='relative_geodesic_travel'
        now=e['event_time'];geometry={}
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
        def energy(peer,d):
            state=states[peer];ages=[]
            for kind,ttl in (('pose_state',2.),('frame_state',2.),('battery_state',5.)):
                lease=e['inputs'][peer+'/'+kind];age=now-lease['source_time']
                assert 0<=age<=ttl and math.isclose(age,lease['age_sec'],abs_tol=1e-8)
                if kind!='battery_state':ages.append(age)
            assert state['mode']=='ACTIVE' and state['stamp_sec']==e['inputs'][peer+'/battery_state']['source_time']
            local=geometry.get(peer);home=(state['charge_x'],state['charge_y'])
            map_age=max(now-e['planning_map']['source_time'],now-e['return_maps'][peer]['source_time']) if local else now-e['planning_map']['source_time']
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
            cost=None if states is None else energy(peer,d)
            if cost is not None and (not math.isfinite(cost) or states[peer]['energy']<=cost):continue
            peers[peer]=dict(distance_m=d,required_energy=cost)
        assert set(peers)==set(f['peers'])
        for peer,row in peers.items():
            assert math.isclose(row['distance_m'],f['peers'][peer]['distance_m'],abs_tol=1e-8)
            if row['required_energy'] is None:assert f['peers'][peer]['required_energy'] is None
            else:assert math.isclose(row['required_energy'],f['peers'][peer]['required_energy'],abs_tol=1e-8)
        factor=control.relative_travel_factor(nominal,[r['distance_m'] for r in peers.values()])
        assert math.isclose(factor,f['factor'],abs_tol=1e-8)
        assert math.isclose(f['base_utility']*f['battery_factor']*factor,f['adjusted_utility'],abs_tol=1e-8)
        if require_commitment:
            assert math.isfinite(f['information_gain']) and f['information_gain']>0
            gain=control.visible_unknown_gain(raw['data'],cell,control.INFORMATION_RADIUS_M/raw['resolution'])
            assert gain==f['information_gain'],'current viewpoint gain differs from delivered grid'
        if 'resume_intent' in f:
            intent=f['resume_intent'];assert len(intent)==3 and all(math.isfinite(x) for x in intent)
            assert math.dist(target,intent[:2])<=control.MIN_TARGET_SEPARATION_M
            assert f['information_gain']>max(control.MIN_REMAINING_GAIN,intent[2]*control.MIN_REMAINING_GAIN_FRACTION)
            assert f['battery_factor']==1.
            resumed+=1
        if states is not None:
            cost=energy(name,planned)
            assert math.isfinite(cost) and cost<states[name]['energy']
            assert math.isclose(cost,f['required_energy'],abs_tol=1e-8)
            assert f['battery_factor']==1.
        count+=1;discounts+=int(factor<1.)
    return dict(status='PASS',executed_frontier_witnesses=count,relative_travel_discounts=discounts,
        resumed_frontier_witnesses=resumed,required=required,commitment_required=require_commitment)


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


def native_tf_ingress_audit(graph,robot_count,required=False):
    if not required:return dict(status='LEGACY_RAW_INPUT',required=False)
    nodes=graph['nodes'];verified=[]
    for index in range(1,robot_count+1):
        robot=f'tb{index}';topic=f'/{robot}/battery/source_tf';battery=f'/{robot}/battery_manager'
        producer=f'/{robot}/gateway_tf_ingress'
        subscribers={row[0] for row in nodes[battery]['subscribers']}
        assert topic in subscribers and f'/{robot}/tf' not in subscribers
        assert f'/{robot}/tf' in {row[0] for row in nodes[producer]['subscribers']}
        outputs={row[0] for row in nodes[producer]['publishers']}
        assert {topic,f'/{robot}/gateway/source_tf'}<=outputs
        consumers=[name for name,node in nodes.items() if topic in {row[0] for row in node['subscribers']}]
        assert consumers==[battery],('native TF leaked to another consumer',topic,consumers)
        verified.append(robot)
    return dict(status='PASS',required=True,robot_local_filtered_tf=verified,
        ap_native_tf_consumers=0,source_time_renewal=False)


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
    ingress=native_tf_ingress_audit(original,result['robot_count'],bool(config.get('native_filtered_tf')))
    native=return_audit(directory/'safety_events.jsonl',bool(config.get('native_pose_contract')),
        bool(config.get('return_source_selection')))
    energy=energy_audit(directory/'safety_events.jsonl',result,
        bool(config.get('native_energy_accounting')) and case!='empty_battery')
    forecast=lookahead_audit((json.loads(line) for line in (directory/'ledger.jsonl').open()),
        bool(config.get('ap_pose_budget_contract')))
    vetoes=ap_return_veto_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    assignments=rally_assignment_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    if config.get('rally_return_objective') and result.get('rally_assignments'):
        assert assignments['chosen_assignments_rebuilt']>=1, 'missing exact delivered assignment choice'
    repairs=rally_repair_audit(json.loads(line) for line in (directory/'ledger.jsonl').open())
    travel=exploration_travel_audit((json.loads(line) for line in (directory/'ledger.jsonl').open()),
        bool(config.get('exploration_travel_preference')),bool(config.get('exploration_frontier_commitment')))
    assert result['collision_monitoring_active']
    return dict(case=case,status='PASS',git_commit=row['git_commit'],source_digests=row['source_digests'],
        result=result,raw_summary=str(path.resolve()),raw_summary_sha256=sha(path),return_audit=native,
        communication_audit=communications,lookahead_audit=forecast,native_energy_audit=energy,
        ap_return_veto_audit=vetoes,rally_assignment_audit=assignments,rally_repair_audit=repairs,
        exploration_travel_audit=travel,native_tf_ingress_audit=ingress)


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
