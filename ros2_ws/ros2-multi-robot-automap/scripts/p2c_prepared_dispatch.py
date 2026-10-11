"""Rebuild original batch geometry and exact funded legs before recovery."""
import json
import math
import numpy as np
from multi_robot_exploration import control as c
from p2c_outbound_routes import bind_original_maps, decode


def exact_budget(event, dispatched, grid, maps):
    name=dispatched['robot'];budget=dispatched['budget'];assert budget is not None
    state=event['battery_states'][name];inputs=event['inputs'];priced=budget['priced_at_sec']
    assert event['evaluated_at_sec']<=priced<=event['event_time']
    assert state['mode']=='ACTIVE' and state['stamp_sec']==inputs[name+'/battery_state']['source_time']
    position=event['robot_positions'][name];goal=dispatched['position'];final=c.RallyPose(*event['final_targets'][name])
    saved=event['planning_map'];res=saved['resolution'];origin=saved['origin']
    _,remaining=c.plan_rally_leg(final,grid,res,origin,goal,local_map=maps[name])
    assert remaining and np.allclose(remaining,budget['remaining_route'],atol=1e-10,rtol=0.)
    distance=lambda points:sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    actual=distance((position,*dispatched['route']))+distance((goal,*remaining))
    assert math.isclose(actual,budget['actual_distance_m'],rel_tol=0.,abs_tol=1e-8)
    move,idle,speed,factor,margin,recovery=(float(state.get(k,d)) for k,d in (
        ('move_cost_per_m',1.),('idle_cost_per_sec',.02),('nominal_speed_mps',.18),
        ('return_path_factor',2.),('return_safety_margin',8.),('return_recovery_wait_sec',30.)))
    assert all(math.isfinite(v) for v in (move,idle,speed,factor,margin,recovery))
    assert min(move,idle,margin,recovery)>=0 and speed>0 and factor>=1
    map_age=priced-min(saved['source_time'],event['return_maps'][name]['source_time'])
    pose_age=priced-min(inputs[name+'/pose_state']['source_time'],inputs[name+'/frame_state']['source_time'])
    assert 0<=map_age<=5. and 0<=pose_age<=2.
    candidates=c.qualified_return_candidates(grid,res,origin,(final.x,final.y),
        (float(state['charge_x']),float(state['charge_y'])),float(state.get('charge_radius_m',.8)),maps[name])
    returned=min((row['path_distance_m'] for row in candidates if row['qualified']),default=None)
    assert returned is not None
    motion=returned*factor+c.RETURN_MAX_LINEAR_MPS*(pose_age+c.RETURN_REACTION_SEC)
    wait=recovery+map_age+pose_age+c.RETURN_REACTION_SEC
    requirement=actual*1.25*(move+idle/speed)+motion*move+(motion/speed+wait)*idle+margin
    hold=budget['hold_sec'];assert hold==event['hold_sec']==5.
    waited=budget['wait_budget_sec'];assert math.isfinite(waited) and waited>=0 and waited==event['wait_budgets_sec'][name]
    requirement+=idle*(hold+waited)
    assert math.isclose(requirement,budget['required_energy'],rel_tol=0.,abs_tol=1e-8)
    assert budget['available_energy']==float(state['energy'])>requirement


def rebuild(event):
    assert event['admission']=='original_send_rally_goal' and event['native_credit_added'] is False
    now=event['event_time'];assert 0<=now-event['evaluated_at_sec']<=2.
    order=event['dispatch_order'];assert len(order)==len(set(order))
    assert set(order)==set(event['targets'])==set(event['final_targets'])
    blocked=event['blocked_robot'];assert blocked in order and blocked not in event['prepared_plans']
    assert event['prepared_plans'] and all(order.index(n)<order.index(blocked) for n in event['prepared_plans'])
    assert 0<=event['max_concurrent']<=c.RALLY_MAX_CONCURRENT
    inputs=event['inputs']
    for key,sample in inputs.items():
        limit=60. if key=='headquarters/target_detection' else 2. if key.endswith(('/pose_state','/frame_state')) else 5.
        assert 0<sample['ttl_sec']<=limit and 0<=now-sample['source_time']<=sample['ttl_sec']
        assert math.isclose(sample['age_sec'],now-sample['source_time'],rel_tol=0.,abs_tol=1e-8)
    saved=event['planning_map'];grid=decode(saved);res=saved['resolution'];origin=saved['origin']
    assert saved['source_time']==inputs['headquarters/fused_map_snapshot']['source_time']
    maps={n:dict(data=decode(m),resolution=m['resolution'],origin=m['origin']) for n,m in event['return_maps'].items()}
    for n,m in event['return_maps'].items():assert m['source_time']==inputs[n+'/map_snapshot']['source_time']
    positions=event['robot_positions'];assert set(order)<=positions.keys() and set(order)<=maps.keys()
    assert all(p is not None and len(p)==2 and np.isfinite(p).all() for p in positions.values())
    reserved=[c.remaining_rally_route(route,positions[n]) for n,route in event['existing_leg_routes'].items() if route]
    names=set(event['reserved_names']);assert names=={n for n,r in event['existing_leg_routes'].items() if r}
    slots=max(0,event['max_concurrent']-len(reserved));original_names=set(names)
    returns=event['return_reservations'];assert returns is not None
    staged=set(event['stage_names']);headings=set(event['heading_corrections'])
    modes=event['battery_modes'];assert modes=={n:s['mode'] for n,s in event['battery_states'].items()}
    rebuilt_returns=c.rally_return_reservations(grid,res,origin,positions,event['battery_states'],modes,
        set(event['charge_requested']),return_maps=maps)
    assert rebuilt_returns is not None and set(rebuilt_returns)==set(returns)
    assert all(np.allclose(rebuilt_returns[n],r,atol=1e-10,rtol=0.) for n,r in returns.items())
    for name,prepared in event['prepared_plans'].items():
        expected=c.plan_rally_leg(c.RallyPose(*event['planning_targets'][name]),grid,res,origin,positions[name],
            c.MAX_NAVIGATION_LEG_M if name in staged else min(c.MAX_NAVIGATION_LEG_M,c.rally_leg_limit(event['rally_attempts'][name])),
            c.rally_stationary_positions(positions,name,original_names|(set(returns) if name in staged else set())),
            visible_only=name in staged|headings|set(event['yield_targets'])|set(event['return_yield_targets']),local_map=maps[name])
        assert expected[0] is not None
        assert np.allclose((expected[0].x,expected[0].y,expected[0].yaw),prepared['goal'],atol=1e-10,rtol=0.)
        assert np.allclose(expected[1],prepared['route'],atol=1e-10,rtol=0.)
    actual={row['robot']:row for row in event['dispatched']};assert actual and len(actual)==len(event['dispatched'])
    rebuilt=set();bindings=[]
    for name in order:
        if slots==0:break
        if name not in event['prepared_plans']:continue
        prepared=event['prepared_plans'][name]
        plan=(c.RallyPose(*prepared['goal']),tuple(map(tuple,prepared['route'])))
        priority=[] if name in staged|headings else c.rally_priority_reservations(order,name,event['approach_routes'],
            set(event['completed_approaches'])|{b for y,b in event['recovery_beneficiaries'].items() if y==name and not event['arrived'][y]})
        if priority is None:continue
        if names!=original_names:
            plan=c.plan_rally_leg(c.RallyPose(*event['planning_targets'][name]),grid,res,origin,positions[name],
                min(c.MAX_NAVIGATION_LEG_M,c.rally_leg_limit(event['rally_attempts'][name])),
                c.rally_stationary_positions(positions,name,names|(set(returns) if name in staged else set())),
                visible_only=name in staged|headings|set(event['yield_targets'])|set(event['return_yield_targets']),local_map=maps[name])
        admitted=c.reserve_rally_prefix(plan,[*reserved,*priority,*(r for n,r in returns.items() if n!=name)])
        if admitted is None:continue
        pose,route=admitted
        if name in actual:
            row=actual[name];assert np.allclose((pose.x,pose.y),row['position'],atol=1e-10,rtol=0.)
            assert np.allclose(route,row['route'],atol=1e-10,rtol=0.)
            if name not in staged|set(event['return_yield_targets']):exact_budget(event,row,grid,maps)
            rebuilt.add(name);bindings.append(dict(robot=name,outbound_map_route=dict(local_map=event['return_maps'][name],planning_map=saved),planning_map_self_return_cells=event['planning_map_self_return_cells']))
        reserved.append(route);names.add(name);slots-=1
    assert rebuilt==set(actual),'private dispatch does not match original admitted batch'
    return bindings


def prepared_dispatch_audit(path,declared=False,capture=None,native_capture=None):
    events=[json.loads(line) for line in path.open()]
    checks=[e for e in events if e.get('event')=='coordinator_rally_prepared_batch_before_recovery']
    if not declared:
        assert not checks,'undeclared early normal batch'
        return None
    bindings=[];goals=0;budgets=0
    for event in checks:
        bindings.extend(rebuild(event))
        for row in event['dispatched']:
            wanted=[e for e in events if e.get('event')=='coordinator_navigation_decision'
                and e.get('robot')==row['robot'] and e.get('kind') in ('rally','local_return_yield')
                and event['evaluated_at_sec']<=e['event_time']<=event['event_time']
                and np.allclose(e['requested_position'],row['position'],atol=1e-10,rtol=0.)]
            assert len(wanted)==1,'missing or ambiguous original public navigation decision'
            assert all(wanted[0]['inputs'][k]['source_time']==v['source_time'] for k,v in event['inputs'].items())
            goals+=1;budgets+=int(row['budget'] is not None)
    # Bind every body/map used to the actual original CDR, not only the dispatched owner.
    all_maps=[dict(robot=n,outbound_map_route=dict(local_map=m,planning_map=e['planning_map']),
        planning_map_self_return_cells=e['planning_map_self_return_cells']) for e in checks for n,m in e['return_maps'].items()]
    maps=bind_original_maps(all_maps,capture) if checks and capture is not None else 0
    poses=native=0
    if checks and capture is not None:
        from p2c_preparation_approach import bind_original_positions
        poses=bind_original_positions([dict(inputs=e['inputs'],rally_preparation=dict(robot_positions=e['robot_positions'])) for e in checks],capture,.2)
    if checks and native_capture is not None:
        originals={}
        for line in native_capture.open():
            r=json.loads(line)
            if r['topic'].endswith('/battery_state'):originals.setdefault(r['topic'].split('/')[1],[]).append(r['data'])
        for e in checks:
            for n,state in e['battery_states'].items():
                assert state in originals.get(n,[]),'missing exact native batch battery source'
                native+=1
    return dict(status='PASS',attempts_with_submitted_goals=len(checks),submitted_goals=goals,
        exact_original_leg_budgets=budgets,original_source_maps=maps,original_pose_frame_sources=poses,
        original_native_battery_sources=native,scope='Original batch geometry/reservations and exact full leg+remaining+wait+hold+contact-return budget; original public decision and raw source binding. No task timing or execution-connectivity guarantee.')
