"""A funded final return cannot excuse an occupied intermediate waypoint."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
from geometry_msgs.msg import PoseStamped

from multi_robot_exploration import control as c
from test_navigation_dispatch_boundary import boundary_node
from test_rally_full_budget import rally_budget_node
from test_rally_computation import REFERENCE as OLD_CASES, saved_arguments, original_assign
from p2c_outbound_routes import audit_outbound, check_route, decode


REFERENCE = json.loads((Path(__file__).parent/'fixtures/p2c_v49_outbound_reference.json').read_text())


def geometry(saved):
    return dict(data=c.immutable_grid_snapshot(decode(saved), saved['shape']),
                resolution=saved['resolution'], origin=saved['origin'])


@pytest.mark.parametrize('row', REFERENCE['decisions'][:2], ids=lambda row: str(row['event_time']))
def test_original_pre_failure_maps_have_an_obstacle_safe_alternative(row):
    fused, local = geometry(row['fused_map']), geometry(row['local_map'])
    originals = fused['data'].copy(), local['data'].copy()
    start = row['original_decision']['current_position']
    old = c.plan_rally_leg(c.RallyPose(*REFERENCE['assignment']), fused['data'],
        fused['resolution'], fused['origin'], start, visible_only=True)
    with pytest.raises(AssertionError):
        check_route(row['local_map'], (start, *old[1]), local=True)
    new = c.plan_rally_leg(c.RallyPose(*REFERENCE['assignment']), fused['data'],
        fused['resolution'], fused['origin'], start, visible_only=True, local_map=local)
    assert new[0] and new[0] != old[0]
    check_route(row['local_map'], (start, *new[1]), local=True)
    assert np.array_equal(fused['data'], originals[0]) and np.array_equal(local['data'], originals[1])


def test_original_occupied_pose_is_not_cleared_to_create_an_escape():
    row = REFERENCE['decisions'][-1];fused, local = geometry(row['fused_map']), geometry(row['local_map'])
    assert c.plan_rally_leg(c.RallyPose(*REFERENCE['assignment']), fused['data'],
        fused['resolution'], fused['origin'], row['original_decision']['current_position'],
        visible_only=True, local_map=local) == (None, ())


def synthetic_maps():
    fused = c.immutable_grid_snapshot(np.zeros((60, 80), dtype=int), (60, 80))
    local = fused.copy();local[20, 30] = 100
    return fused, dict(data=c.immutable_grid_snapshot(local, local.shape), resolution=.1, origin=(0., 0.))


def test_reused_candidate_field_tracks_the_local_source_without_poisoning_the_grid():
    fused, local = synthetic_maps();cache = {}
    plan = lambda: c.plan_rally_leg(c.RallyPose(5.05, 2.05, 0.), fused, .1, (0., 0.),
        (1.05, 2.05), max_distance_m=float('inf'), local_map=local, route_cache=cache)
    first = plan(); assert first[0]
    local['data'] = c.immutable_grid_snapshot(np.zeros((60, 80)), (60, 80))
    second = plan();assert second[0] and second[1] != first[1]
    distance = lambda route: sum(np.linalg.norm(np.subtract(a,b)) for a,b in zip(route,route[1:]))
    assert distance(second[1]) < distance(first[1])
    assert np.all(fused == 0)


def test_unknown_local_cells_preserve_the_original_fused_extension():
    fused, local = synthetic_maps();local['data'] = c.immutable_grid_snapshot(np.full(fused.shape, -1), fused.shape)
    args = c.RallyPose(5.05, 2.05, 0.), fused, .1, (0., 0.), (1.05, 2.05)
    assert c.plan_rally_leg(*args, local_map=local) == c.plan_rally_leg(*args)


def test_full_rally_budget_prices_the_known_local_detour():
    node, _, _ = rally_budget_node(energy=80.)
    node.map_data, local = synthetic_maps();node.robot_positions['tb1'] = (1.05, 2.05)
    node.robot_maps = {'tb1':local};node.robot_map_received_at = {'tb1':11.}
    node.rally_final_targets['tb1'] = c.RallyPose(5.05, 2.05, 0.)
    node.battery_states['tb1'].update(charge_x=1.05, charge_y=2.05)
    assert not c.HeadquartersControl.prepare_rally_charges(node)
    route = node.rally_approach_routes['tb1']
    assert sum(np.linalg.norm(np.subtract(a,b)) for a,b in zip(route,route[1:])) > 4.
    saved = c.grid_audit_evidence(local['data'], .1, (0., 0.), 'test', 11., 1)
    check_route(saved, route, local=True)


@pytest.mark.parametrize('change', ['none', 'occupied', 'expired', 'missing', 'endpoint'])
def test_final_publication_rejects_old_or_missing_local_route_without_an_owner(change):
    node, clock, _, events, client, _ = boundary_node()
    node.enable_battery = True;node.map_data, local = synthetic_maps()
    node.robot_maps = {'tb1':local};node.robot_map_received_at = {'tb1':10.};node.map_received_at = 10.
    node.robot_positions['tb1'] = (1.05, 2.05)
    node.rally_targets['tb1'] = c.RallyPose(5.05, 2.05, 0.)
    node.rally_plan_has_energy = lambda *_: True
    plan = c.plan_rally_leg(node.rally_targets['tb1'], node.map_data, .1, (0.,0.),
                           node.robot_positions['tb1'], visible_only=True, local_map=local)
    if change == 'occupied':
        plan = c.plan_rally_leg(node.rally_targets['tb1'], node.map_data, .1, (0.,0.), node.robot_positions['tb1'])
    elif change == 'expired':clock[0] = 15.1
    elif change == 'missing':node.robot_maps = {}
    elif change == 'endpoint':plan = plan[0], (node.robot_positions['tb1'],)
    c.HeadquartersControl.send_rally_goal(node, 'tb1', plan)
    assert client.send_goal_async.call_count == int(change == 'none')
    assert node.rally_goal_pending['tb1'] == (change == 'none') and node.rally_attempts['tb1'] == 0
    if change == 'none':
        assert audit_outbound(events[-1]) > 1
    elif change == 'occupied':assert events[-1]['event'] == 'coordinator_navigation_map_veto'


@pytest.mark.parametrize('case', OLD_CASES['cases'], ids=lambda case: case['name'])
def test_saved_assignments_use_local_obstacle_safe_whole_approaches(case):
    args = saved_arguments(case['event']);answer = c.assign_rally_poses(**args)
    if case['event']['assignment'] is None:
        assert answer == original_assign(**args) == {}
        return
    assert answer
    for name, pose in answer.items():
        local = args['return_maps'].get(name)
        if local is None:continue
        plan = c.plan_rally_leg(pose, args['raw_grid'], args['resolution'], args['origin'],
            args['robot_positions'][name], max_distance_m=float('inf'), local_map=local)
        assert plan[0]
        witness = c.grid_audit_evidence(local['data'], local['resolution'],local['origin'],'test',10.,1)
        check_route(witness, (args['robot_positions'][name], *plan[1]), local=True)
