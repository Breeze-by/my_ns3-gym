"""Retained order preferences must reprove current complete serial geometry."""
import copy
import gzip
import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from multi_robot_exploration import control as c
from check_p2c_gate import rally_proposal_audit
from p2c_outbound_routes import check_route, decode
from test_rally_proposal_handoff import node_fixture, records, renew_delivered_inputs


def test_original_current_proposal_has_three_complete_body_masked_local_routes():
    p = Path(__file__).with_name('fixtures')/'p2c_v63_rally_intent_input.json.gz'
    with gzip.open(p, 'rt') as stream:
        e = json.load(stream)['original_proposal']
    s = e['planning_map']; grid = decode(s)
    targets = {name: c.RallyPose(*values) for name, values in e['assignment'].items()}
    maps = {name: dict(data=decode(saved), resolution=saved['resolution'], origin=saved['origin'])
            for name, saved in e['return_maps'].items()}
    routes = c.serial_rally_routes(grid, s['resolution'], s['origin'], targets,
                                  e['robot_positions'], e['dispatch_order'], maps)
    assert set(routes) == set(targets)
    for name, route in routes.items():
        assert tuple(route[0]) == tuple(e['robot_positions'][name])
        assert tuple(route[-1]) == pytest.approx((targets[name].x, targets[name].y))
        check_route(s, route); check_route(e['return_maps'][name], route, local=True)
    assert grid.tobytes() == decode(s).tobytes()


@pytest.mark.parametrize('change', ['order', 'missing', 'body', 'local_obstacle', 'unknown'])
def test_serial_preference_cannot_bypass_current_bodies_or_known_local_geometry(change):
    grid = np.full((50, 100), 100, dtype=np.int16); grid[19:31, 1:99] = 0
    positions = {'front': (4., 2.5), 'rear': (1., 2.5)}
    targets = {'front': c.RallyPose(8.05, 2.55, 0.), 'rear': c.RallyPose(6.05, 2.55, 0.)}
    order = ['front', 'rear']; local = grid.copy()
    if change == 'order': order = ['front', 'front']
    if change == 'missing': positions['front'] = None
    if change == 'body': order.reverse()
    if change == 'local_obstacle': local[25, 80] = 100
    if change == 'unknown': grid[25, 80] = -1
    maps = dict.fromkeys(targets, dict(data=local, resolution=.1, origin=(0., 0.)))
    assert c.serial_rally_routes(grid, .1, (0., 0.), targets, positions, order, maps) is None


def admit_after_expired_search(monkeypatch):
    node, clock, _, assignment = node_fixture(); node.use_map_safe_rally_order = True
    proposal = dict(assignment=assignment, target=node.target, evaluated_at=10.)
    c.HeadquartersControl.record_rally_assignment(node, node.robot_positions, node.robot_maps, 0., assignment, 10.)
    original = c.map_safe_rally_dispatch_order
    def slow(*args, **kwargs):
        result = original(*args, **kwargs); clock[0] = 12.1; return result
    search = Mock(side_effect=slow); monkeypatch.setattr(c, 'map_safe_rally_dispatch_order', search)
    assert not c.HeadquartersControl.admit_rally_proposal(node, proposal)
    assert proposal['dispatch_order_preference'] and not node.rally_targets
    renew_delivered_inputs(node, clock)
    assert c.HeadquartersControl.admit_rally_proposal(node, proposal)
    assert search.call_count == 1
    event = records(node)[-1]
    assert event['order_source'] == 'current_serial_revalidation' and not event['budget_reused']
    return node, clock, proposal


def test_expired_order_search_retains_only_preference_then_reproves_new_sources(monkeypatch):
    node, _, _ = admit_after_expired_search(monkeypatch)
    result = rally_proposal_audit(iter(records(node)), True, True, require_order_source=True)
    assert result['admitted_proposals'] == 1
    assert all(sample['source_time'] == 12. for key, sample in records(node)[-1]['inputs'].items()
               if key != 'headquarters/target_detection')
    assert not node.rally_charge_requested and all(handle is None for handle in node.goal_handles.values())


@pytest.mark.parametrize('mutation', ['endpoint', 'shortcut', 'preference', 'source', 'expired', 'body'])
def test_serial_order_reader_rejects_forged_current_proof(monkeypatch, mutation):
    node, _, _ = admit_after_expired_search(monkeypatch); rows = copy.deepcopy(records(node)); e = rows[-1]
    if mutation == 'endpoint': e['serial_routes']['tb1'][-1] = [0., 0.]
    if mutation == 'shortcut': e['serial_routes']['tb1'] = [e['robot_positions']['tb1'], e['assignment']['tb1'][:2]]
    if mutation == 'preference': e['previous_order_preference'].reverse()
    if mutation == 'source': del e['order_source']
    if mutation == 'expired': e['inputs']['tb1/pose_state']['source_time'] -= 3.
    if mutation == 'body': e['robot_positions']['tb1'][0] += .2
    with pytest.raises((AssertionError, ValueError)):
        rally_proposal_audit(iter(rows), True, True, require_order_source=True)


@pytest.mark.parametrize('stage', ['serial_geometry', 'publication'])
def test_serial_revalidation_and_publication_must_fit_original_source_deadlines(monkeypatch, stage):
    node, clock, _, assignment = node_fixture(); node.use_map_safe_rally_order = True
    proposal = dict(assignment=assignment, target=node.target, evaluated_at=10.,
                    dispatch_order_preference=['tb1', 'tb2'])
    if stage == 'serial_geometry':
        original = c.serial_rally_routes
        def late(*args, **kwargs):
            routes = original(*args, **kwargs); clock[0] = 12.1; return routes
        monkeypatch.setattr(c, 'serial_rally_routes', late)
    else:
        node.consumed_publisher.publish.side_effect = lambda msg: clock.__setitem__(0, 12.1)
    assert not c.HeadquartersControl.admit_rally_proposal(node, proposal)
    assert not node.rally_targets
    node.publish_rally_assignments.assert_not_called()


def test_invalid_preference_uses_original_current_search(monkeypatch):
    node, _, _, assignment = node_fixture(); node.use_map_safe_rally_order = True
    proposal = dict(assignment=assignment, target=node.target, evaluated_at=10.,
                    dispatch_order_preference=['tb1', 'tb1'])
    search = Mock(wraps=c.map_safe_rally_dispatch_order); monkeypatch.setattr(c, 'map_safe_rally_dispatch_order', search)
    assert c.HeadquartersControl.admit_rally_proposal(node, proposal)
    assert search.call_count == 1 and records(node)[-1]['order_source'] == 'current_map_search'
