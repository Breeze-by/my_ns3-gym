import base64
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import zlib

import numpy as np
import pytest

from multi_robot_exploration import control as c


def fixture():
    x = json.loads((Path(__file__).parent/'fixtures/p2c_v11_endpoint_repair.json').read_text())
    e = x['event']; maps = {}
    for key in ('fused_map', 'local_map'):
        s = e[key]
        maps[key] = dict(data=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),
                                          dtype='<i2').reshape(s['shape']),
                         resolution=s['resolution'], origin=s['origin'])
    g = maps['fused_map']; state = x['snapshot']['robots']['tb2']['battery']
    args = dict(raw_grid=g['data'], resolution=g['resolution'], origin=g['origin'],
                position=x['snapshot']['robots']['tb2']['pose'], target=x['target'],
                state=state, local_map=maps['local_map'],
                map_age=max(e['inputs'][k]['age_sec'] for k in
                            ('headquarters/fused_map_snapshot', 'tb2/map_snapshot')),
                pose_age=max(e['inputs'][k]['age_sec'] for k in ('tb2/pose_state', 'tb2/frame_state')),
                reserved=[x['reserved']], blocked=[x['reserved']])
    return x, args


def test_actual_v11_maps_allow_a_funded_grid_pose_beyond_the_sampled_rings():
    x, args = fixture(); g = args['raw_grid']; before = g.copy()
    state = args['state']; home = (state['charge_x'], state['charge_y'])
    def qualified(point):
        return any(r['qualified'] for r in c.qualified_return_candidates(g, args['resolution'],
            args['origin'], point, home, state['charge_radius_m'], args['local_map']))
    assert qualified(args['position']) and not qualified(x['event']['destination'])
    old = c.rally_pose_candidates(g, args['resolution'], args['origin'], args['target'])
    assert not any(qualified((p.x, p.y)) and math.dist((p.x, p.y), x['reserved']) >= c.RALLY_MIN_SEPARATION_M
                   for p in old)
    pose, route, required = c.funded_rally_replacement(**args)
    assert math.dist(args['position'], (pose.x, pose.y)) < .2
    assert qualified((pose.x, pose.y)) and required < state['energy']
    assert math.dist((pose.x, pose.y), x['reserved']) >= c.RALLY_MIN_SEPARATION_M
    cell = c.world_to_grid(pose.x, pose.y, args['resolution'], *args['origin'])
    target = c.world_to_grid(*args['target'], args['resolution'], *args['origin'])
    assert c.traversable_grid(g, args['resolution'], clearance_m=.45)[cell]
    assert c.has_known_line_of_sight(g, cell, target)
    assert route and np.array_equal(g, before)


@pytest.mark.parametrize('key,value', [('map_age', 5.01), ('pose_age', 2.01),
    ('map_age', -.01), ('pose_age', float('nan')), ('wait_sec', -1.), ('hold_sec', float('inf'))])
def test_repair_rejects_expired_future_or_invalid_budget_inputs(key, value):
    _, args = fixture(); args[key] = value
    assert c.funded_rally_replacement(**args) is None


@pytest.mark.parametrize('change', ['unfunded', 'returning', 'no_current_return', 'body_blocked'])
def test_repair_never_uses_an_unfunded_or_unsafe_stopping_pose(change):
    _, args = fixture()
    if change == 'unfunded': args['state']['energy'] = 5.
    if change == 'returning': args['state']['mode'] = 'RETURNING'
    if change == 'no_current_return': args['raw_grid'] = np.full_like(args['raw_grid'], -1)
    if change == 'body_blocked': args['blocked'] = [args['position']]
    assert c.funded_rally_replacement(**args) is None


def node_fixture():
    x, args = fixture(); e = x['event']; name = 'tb2'
    # A constructed publication, not the original callback context: the
    # nearest AP-live state is 0.4s later. Bind its synthetic header explicitly
    # to the saved lease; keep both original source records unchanged.
    args['state'] = {**args['state'], 'stamp_sec': e['inputs'][name+'/battery_state']['source_time']}
    old = c.RallyPose(*e['destination'], 0.)
    peer = c.RallyPose(*x['reserved'], 0.)
    node = SimpleNamespace(
        now=lambda: e['event_time'], fresh_robot_inputs=lambda: True, fresh_target=lambda: True,
        target=x['target'], target_received_source_time=e['event_time']-1.,
        map_data=args['raw_grid'], resolution=args['resolution'], origin=args['origin'],
        map_received_at=e['fused_map']['source_time'], robot_maps={name: args['local_map']},
        robot_map_received_at={name: e['local_map']['source_time']},
        robot_odom_received_at={name: e['inputs'][name+'/pose_state']['source_time']},
        battery_modes={name:'ACTIVE', 'tb1':'ACTIVE'}, battery_states={name:args['state']},
        robot_positions={name: args['position'], 'tb1':x['reserved']},
        robot_states={name:'idle'}, goal_handles={name:None},
        rally_targets={name:old, 'tb1':peer}, rally_final_targets={name:old, 'tb1':peer},
        rally_arrived={name:False, 'tb1':True}, rally_observer_guard='tb1',
        rally_goal_handles={name:None}, rally_goal_pending={name:False},
        rally_charge_requested={}, rally_precharge_staging={}, return_yield_targets={},
        rally_yield_targets=set(), rally_probe_targets=set(), survey_robot=None,
        survey_goal_handle=None, survey_goal_pending=False, rally_hold_sec=5.,
        rally_wait_budgets={name:0.}, rally_route_unavailable_since={name:1.},
        rally_hold_started_at=1., rally_preflight_complete=True,
        rally_attempts={name:2}, rally_detour_budgets={name:100.},
        input_freshness_details=lambda: e['inputs'], consumed_publisher=Mock(),
        publish_rally_assignments=Mock(), get_logger=lambda: Mock())
    return node, old, peer


def test_online_repair_preserves_peer_retry_count_and_only_updates_the_proposal():
    node, old, peer = node_fixture()
    assert c.HeadquartersControl.repair_rally_return_target(node, 'tb2')
    assert node.rally_final_targets['tb2'] is not old
    assert node.rally_final_targets['tb1'] is peer and node.rally_arrived['tb1']
    assert node.rally_attempts['tb2'] == 2 and node.goal_handles['tb2'] is None
    assert node.rally_hold_started_at is None and not node.rally_preflight_complete
    assert not node.rally_detour_budgets
    node.publish_rally_assignments.assert_called_once()
    event = json.loads(node.consumed_publisher.publish.call_args[0][0].data)
    assert event['event'] == 'coordinator_rally_return_repair'
    assert event['local_map']['source_time'] == node.robot_map_received_at['tb2']
    assert event['pose_age_sec'] == max(event['inputs'][k]['age_sec'] for k in
                                       ('tb2/pose_state','tb2/frame_state'))


def test_preflight_repairs_the_invalid_endpoint_then_rechecks_it_before_admission():
    node, old, peer = node_fixture()
    node.rally_dispatch_order = ['tb2']
    node.target_observing_robot = 'tb1'
    node.charge_request_publishers = {'tb2': Mock()}
    node.fail_task = Mock()
    assert c.HeadquartersControl.prepare_rally_charges(node) == {'tb2'}
    assert node.rally_final_targets['tb2'] is not old
    assert node.rally_final_targets['tb1'] is peer
    assert c.HeadquartersControl.prepare_rally_charges(node) == set()
    assert node.rally_charge_budgets['tb2'] < node.battery_states['tb2']['energy']
    node.charge_request_publishers['tb2'].publish.assert_not_called()
    node.fail_task.assert_not_called()


@pytest.mark.parametrize('guard', ['live', 'pending', 'exploring', 'arrived', 'observer',
    'charge', 'return_yield', 'survey', 'stale_state', 'stale_target'])
def test_online_repair_does_not_preempt_live_actions_observation_or_safety(guard, monkeypatch):
    node, old, _ = node_fixture()
    if guard == 'live': node.rally_goal_handles['tb2'] = Mock()
    if guard == 'pending': node.rally_goal_pending['tb2'] = True
    if guard == 'exploring': node.robot_states['tb2'] = 'navigating'
    if guard == 'arrived': node.rally_arrived['tb2'] = True
    if guard == 'observer': node.rally_observer_guard = 'tb2'
    if guard == 'charge': node.rally_charge_requested['tb2'] = 1.
    if guard == 'return_yield': node.return_yield_targets['tb2'] = 'tb1'
    if guard == 'survey': node.survey_robot='tb2'; node.survey_goal_handle=Mock()
    if guard == 'stale_state': node.fresh_robot_inputs=lambda: False
    if guard == 'stale_target': node.fresh_target=lambda: False
    solver = Mock(); monkeypatch.setattr(c, 'funded_rally_replacement', solver)
    assert not c.HeadquartersControl.repair_rally_return_target(node, 'tb2')
    solver.assert_not_called()
    assert node.rally_final_targets['tb2'] is old
