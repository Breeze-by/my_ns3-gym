"""Time preference never replaces full return qualification or budget closure."""
import gzip
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pytest

from multi_robot_exploration import control as c
from p2c_return_preparation import decode_grid

SAVED = json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v76_rally_arrival.json.gz', 'rt'))


def original_arguments(immutable=True):
    e = SAVED['original_event']
    def decode(row):
        grid = decode_grid(row)
        return c.immutable_grid_snapshot(grid, grid.shape) if immutable else grid.copy()
    return dict(raw_grid=decode(e['planning_map']), resolution=e['planning_map']['resolution'],
        origin=e['planning_map']['origin'], robot_positions=e['robot_positions'], target=e['target'],
        objective=e['objective'], battery_states=e['battery_states'], observer_robot=e['observer_robot'],
        current_positions=e['current_positions'], hold_sec=e['hold_sec'], return_maps={n:dict(
            data=decode(row), resolution=row['resolution'], origin=row['origin']) for n,row in e['return_maps'].items()})


@pytest.mark.parametrize('immutable', [False, True])
def test_original_found_snapshot_reproduces_frozen_failure_and_candidate(immutable):
    arguments = original_arguments(immutable)
    results = {}
    for label, literal in SAVED['variants'].items():
        scope = dict(vars(c))
        exec(compile(literal, '<frozen '+label+'>', 'exec'), scope)
        exec(compile(SAVED['wrapper'], '<frozen wrapper>', 'exec'), scope)
        results[label] = scope['assign_rally_poses'](**arguments)
    actual = c.assign_rally_poses(**arguments)
    for n,p in results['frozen'].items():
        assert (p.x,p.y,p.yaw) == tuple(SAVED['original_event']['assignment'][n])
    assert actual == results['arrival_first']
    assert actual != results['frozen']
    for n,p in actual.items():
        state = arguments['battery_states'][n]
        routes = c.qualified_return_candidates(arguments['raw_grid'], arguments['resolution'],
            arguments['origin'], (p.x,p.y), (state['charge_x'],state['charge_y']),
            state['charge_radius_m'], arguments['return_maps'][n])
        assert any(r['qualified'] for r in routes)
        for peers in (arguments['current_positions'], {n:(p.x,p.y) for n,p in actual.items()}):
            assert c.plan_rally_leg(p, arguments['raw_grid'], arguments['resolution'],
                arguments['origin'], arguments['robot_positions'][n],
                blocked_positions=[point for other,point in peers.items() if other!=n],
                local_map=arguments['return_maps'][n])[1]


@pytest.mark.parametrize('objective', ['minimax', 'total_path'])
def test_without_batteries_preserves_original_distance_objective(objective):
    arguments = original_arguments()
    arguments.update(battery_states=None, objective=objective)
    scope = dict(vars(c))
    exec(compile(SAVED['variants']['frozen'], '<8ea distance>', 'exec'), scope)
    exec(compile(SAVED['wrapper'], '<8ea wrapper>', 'exec'), scope)
    assert c.assign_rally_poses(**arguments) == scope['assign_rally_poses'](**arguments)


@pytest.mark.parametrize('speeds', [(.18,.18), (.08,.3), (.3,.08)])
@pytest.mark.parametrize('energy_modes', [(80.,80.,'ACTIVE'), (1.,80.,'ACTIVE'),
                                         (80.,1.,'ACTIVE'), (80.,1.,'CHARGING')])
def test_partial_bounds_match_independent_complete_assignment_enumeration(monkeypatch, speeds, energy_modes):
    grid = np.zeros((100,100), dtype=np.int16)
    resolution, origin = .1, (0.,0.)
    positions = {'tb1':(1.05,2.05), 'tb2':(2.05,4.05)}
    target = (5.05,5.05)
    poses = [c.RallyPose(x,y,math.atan2(target[1]-y,target[0]-x))
             for x,y in ((3.05,3.05),(4.05,3.05),(3.05,4.05),(4.05,4.05))]
    monkeypatch.setattr(c, 'rally_pose_candidates', lambda *args, **kwargs: poses)
    states = {n:dict(mode='ACTIVE' if i==0 else energy_modes[2], energy=energy_modes[i],
        charge_x=p[0],charge_y=p[1],capacity=100.,charge_target_fraction=.8,
        nominal_speed_mps=speeds[i],idle_cost_per_sec=.02,move_cost_per_m=1.,
        return_path_factor=2.,return_safety_margin=8.,charge_duration_sec=6.,
        charge_radius_m=.8,return_recovery_wait_sec=30.) for i,(n,p) in enumerate(positions.items())}
    modes = {n:s['mode'] for n,s in states.items()}
    fields = {n:c.path_distance_grid(c.traversable_grid(grid,resolution,c.RALLY_PATH_CLEARANCE_M),
              c.world_to_grid(*p,resolution,*origin)) for n,p in positions.items()}
    charge_times = {n:s['charge_duration_sec'] + (0. if s['mode']=='CHARGING' else
        s['return_recovery_wait_sec']) for n,s in states.items()}
    complete = []
    for chosen in itertools.permutations(poses, len(positions)):
        plan = dict(zip(positions,chosen))
        if any(math.dist((p.x,p.y),(q.x,q.y))<.8 for p,q in itertools.combinations(chosen,2)):
            continue
        distances = {n:float(fields[n][c.world_to_grid(p.x,p.y,resolution,*origin)]*resolution)
                     for n,p in plan.items()}
        travel = {n:d/states[n]['nominal_speed_mps'] for n,d in distances.items()}
        requirements = {}
        for n,p in plan.items():
            s = states[n]
            routes = c.qualified_return_candidates(grid,resolution,origin,(p.x,p.y),positions[n],.8)
            contact = min(r['path_distance_m'] for r in routes if r['qualified'])
            requirements[n] = c.battery_assignment_required_energy(distances[n],contact,1.,.02,
                2.,s['nominal_speed_mps'],8.,30.) + .02*5.
        requirements,_ = c.rally_wait_requirements(requirements,states,modes,travel,charge_times)
        needed = {n for n in states if modes[n]!='ACTIVE' or states[n]['energy']<=requirements[n]}
        if any(requirements[n]>80. for n in needed):
            continue
        times = [travel[n]+(charge_times[n] if n in needed else 0.) for n in positions]
        delay = 0.
        for parked in positions.keys()-needed:
            if modes[parked]!='ACTIVE':
                continue
            for n in needed:
                p = plan[parked]
                route = c.plan_rally_leg(plan[n],grid,resolution,origin,positions[n],
                    blocked_positions=[(p.x,p.y)])[1]
                masked = (sum(math.dist(a,b) for a,b in zip((positions[n],*route),route))
                          / states[n]['nominal_speed_mps']-travel[n]) if route else c.RALLY_GOAL_TIMEOUT_SEC
                delay += max(0.,masked)
        headroom = max(0.,states['tb1']['energy']-requirements['tb1'])
        separation = sum(max(0.,1.2-math.dist((p.x,p.y),(q.x,q.y)))
                         for p,q in itertools.combinations(chosen,2))
        # All-free maps have zero narrow-return exposure. Enumerate complete
        # assignments directly; no partial search or pruning is used here.
        rank = (int('tb1' in needed),len(needed),max(times)+delay,sum(times)+delay,
                0.,-headroom,max(distances.values())/resolution,separation,
                sum(distances.values())/resolution)
        complete.append((rank,plan))
    assert complete
    expected = min(complete,key=lambda row:row[0])[1]
    actual = c.assign_rally_poses(grid,resolution,origin,positions,target,
        battery_states=states,observer_robot='tb1',current_positions=positions)
    assert actual == expected


@pytest.mark.parametrize('invalid', ['nonfinite_energy','negative_energy','zero_speed','mode','target_fraction'])
def test_time_preference_rejects_invalid_original_budget_inputs(invalid):
    arguments = original_arguments()
    arguments['battery_states'] = {n:dict(s) for n,s in arguments['battery_states'].items()}
    key,value = {'nonfinite_energy':('energy',float('nan')), 'negative_energy':('energy',-1.),
                 'zero_speed':('nominal_speed_mps',0.),'mode':('mode','FAILED'),
                 'target_fraction':('charge_target_fraction',1.1)}[invalid]
    arguments['battery_states']['tb2'][key] = value
    assert c.assign_rally_poses(**arguments) == {}
