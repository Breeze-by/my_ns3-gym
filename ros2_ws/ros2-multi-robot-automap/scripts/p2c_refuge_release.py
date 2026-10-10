"""Independently reconstruct conditional serial release of charged refuges."""
import json
import math

import numpy as np
from multi_robot_exploration import control
from p2c_outbound_routes import bind_original_maps, check_route, decode


def audit_eligibility(event):
    now, priced = event['event_time'], event['required_energy_evaluated_at_sec']
    assert 0 <= now-priced <= 2.
    name, owner = event['robot'], event['charged_owner']
    positions, states, modes = (event[k] for k in ('robot_positions', 'battery_states', 'battery_modes'))
    assert name != owner and all(mode == 'ACTIVE' for mode in modes.values())
    assert all(p is not None and len(p) == 2 and np.isfinite(p).all() for p in positions.values())
    assert event['refuge_arrived'] and not event['charge_requested']
    assert not event['active_rally_goals'] and not event['active_frontier_goals'] and not event['survey_active']
    assert not event['target_scan_active']
    assert set(event['order']) == set(event['final_targets']) and event['order'].index(name) < event['order'].index(owner)
    assert len(event['order']) == len(set(event['order']))
    assert event['hold_sec'] == 5.
    inputs = event['inputs']
    for key, row in inputs.items():
        limit = 60. if key == 'headquarters/target_detection' else 2. if key.endswith(('/pose_state', '/frame_state')) else 5.
        assert 0 < row['ttl_sec'] <= limit and 0 <= now-row['source_time'] <= row['ttl_sec']
    saved = event['planning_map']; grid = decode(saved)
    assert saved['source_time'] == inputs['headquarters/fused_map_snapshot']['source_time']
    res, origin = saved['resolution'], saved['origin']
    maps = {n:dict(data=decode(m), resolution=m['resolution'], origin=m['origin']) for n,m in event['return_maps'].items()}
    for n,m in event['return_maps'].items():
        assert m['source_time'] == inputs[n+'/map_snapshot']['source_time']
    targets = {n:control.RallyPose(*p) for n,p in event['final_targets'].items()}
    occupied = dict(positions)
    bindings = []
    for robot in (name, owner):
        final = targets[robot]
        pose, route = control.plan_rally_leg(final, grid, res, origin, positions[robot],
            max_distance_m=float('inf'), blocked_positions=[p for n,p in occupied.items() if n != robot],
            local_map=maps[robot])
        assert pose is not None
        actual = event['routes'][robot]
        assert np.allclose((positions[robot], *route), actual, atol=1e-10, rtol=0.)
        assert math.dist(actual[-1], (final.x, final.y)) <= res*math.sqrt(2)
        check_route(saved, actual)
        check_route(event['return_maps'][robot], actual, local=True)
        occupied[robot] = (final.x, final.y)
        state = states[robot]
        assert state['mode'] == 'ACTIVE' and math.isfinite(float(state['energy']))
        move, idle, speed, factor, margin, recovery = (float(state.get(k,d)) for k,d in (
            ('move_cost_per_m',1.), ('idle_cost_per_sec',.02), ('nominal_speed_mps',.18),
            ('return_path_factor',2.), ('return_safety_margin',8.), ('return_recovery_wait_sec',30.)))
        assert all(math.isfinite(v) for v in (move, idle, speed, factor, margin, recovery))
        assert min(move, idle, margin, recovery) >= 0 and speed > 0 and factor >= 1
        map_age = priced-min(saved['source_time'], event['return_maps'][robot]['source_time'])
        pose_age = priced-min(inputs[robot+'/pose_state']['source_time'], inputs[robot+'/frame_state']['source_time'])
        assert 0 <= map_age <= 5. and 0 <= pose_age <= 2.
        home = (float(state['charge_x']), float(state['charge_y']))
        def price(distance, point):
            candidates = control.qualified_return_candidates(grid, res, origin, point, home,
                float(state.get('charge_radius_m',.8)), maps[robot])
            returned = min((r['path_distance_m'] for r in candidates if r['qualified']), default=None)
            assert returned is not None
            motion = returned*factor + control.RETURN_MAX_LINEAR_MPS*(pose_age+control.RETURN_REACTION_SEC)
            wait = recovery+map_age+pose_age+control.RETURN_REACTION_SEC
            return distance*1.25*(move+idle/speed) + motion*move + (motion/speed+wait)*idle + margin
        distance = sum(math.dist(a,b) for a,b in zip(actual,actual[1:]))
        wait = event['wait_budgets_sec'][robot]; assert math.isfinite(wait) and wait >= 0
        required = max(price(distance, (final.x,final.y))+idle*(5.+wait), price(0., positions[robot]))
        assert math.isclose(required, event['required_energy'][robot], rel_tol=0., abs_tol=1e-8)
        assert float(state['energy']) > required
        bindings.append(dict(robot=robot, current_position=positions[robot],
            outbound_map_route=dict(local_map=event['return_maps'][robot], planning_map=saved),
            planning_map_self_return_cells=event['planning_map_self_return_cells']))
    return bindings


def refuge_release_audit(path, required=False, capture=None):
    if not required:
        return None
    events = [json.loads(line) for line in path.open()]
    checks = [event for event in events if event.get('event') == 'coordinator_return_refuge_release_eligibility']
    bindings = [binding for event in checks for binding in audit_eligibility(event)]
    sources = bind_original_maps(bindings, capture) if bindings and capture is not None else 0
    return dict(status='PASS', eligibility_checks=len(checks), original_source_maps=sources,
        scope='Fresh, funded complete serial geometry at the conditional release; ordinary dispatch and native holding remain required')
