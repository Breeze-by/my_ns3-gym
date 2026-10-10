"""An expired batch lends geometry preferences, never dispatch authority."""
import copy
import json

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_exploration_charging import assignment, charge_node, install_candidates


def ready_node(monkeypatch):
    node, requests, decisions, sent = charge_node()
    node.enable_rally = False
    node.battery_states['tb1']['energy'] = 80.
    clock = [10.]
    node.now = lambda: clock[0]
    node.input_freshness_details = lambda: {
        'headquarters/fused_map_snapshot': dict(source_time=node.map_received_at, ttl_sec=5.),
        **{name+'/'+kind: dict(source_time=stamps[name], ttl_sec=ttl)
           for name in node.robot_positions for kind, stamps, ttl in (
               ('pose_state', node.robot_odom_received_at, 2.),
               ('frame_state', node.robot_tf_received_at, 2.),
               ('map_snapshot', node.robot_map_received_at, 5.),
               ('battery_state', node.battery_state_received_at, 5.))}}
    node.fresh_robot_inputs = lambda: all(
        0 <= node.now()-row['source_time'] <= row['ttl_sec']
        for row in node.input_freshness_details().values())
    goals = [assignment(6.+i*.02, 3., 4.+i*.02, utility=100.-i) for i in range(16)]
    install_candidates(monkeypatch, {'tb1': goals})
    price = node.exploration_battery_factor
    def expire(*args):
        clock[0] = 13.
        return price(*args)
    node.exploration_battery_factor = expire
    c.HeadquartersControl.assign_idle_robots(node)
    assert not requests and not sent
    proposal = node.pending_exploration_geometry
    assert proposal['generated_at'] == 10. and proposal['cursor'] == {}
    assert set(proposal) == {'context', 'generated_at', 'points', 'cursor'}
    assert proposal['points']['tb1'] and all(len(point) == 2 for point in proposal['points']['tb1'])
    assert decisions[-1]['geometry_preferences'] == json.loads(json.dumps(proposal))
    node.exploration_battery_factor = price
    return node, requests, decisions, sent, clock


def refresh(node, clock, epoch=13.):
    clock[0] = epoch
    node.map_received_at = epoch
    for stamps in (node.robot_odom_received_at, node.robot_tf_received_at,
                   node.robot_map_received_at, node.battery_state_received_at):
        stamps.update(dict.fromkeys(node.robot_positions, epoch))


def test_next_callback_uses_current_candidates_gain_utility_and_sources(monkeypatch):
    node, requests, _, sent, clock = ready_node(monkeypatch)
    refresh(node, clock)
    goals = [assignment(6.01+i*.02, 3., 4.01+i*.02, gain=1234, utility=10.-i*.1) for i in range(12)]
    install_candidates(monkeypatch, {'tb1': goals})
    c.HeadquartersControl.assign_idle_robots(node)
    assert not requests and len(sent) == 1
    goal = sent[0][1]
    assert goal.x == goals[0].x and goal.utility == pytest.approx(goals[0].utility)
    assert goal.viewpoint.information_gain == 1234
    evidence = node.exploration_travel_choices['tb1']
    assert evidence['deferred_geometry_preference']['prices_reused'] is False
    assert evidence['required_energy_evaluated_at_sec'] == 13.
    assert len(node.frontier_charge_lookahead[2]['tb1']) == len(goals)
    assert node.pending_exploration_geometry['cursor']['tb1'] == 3


@pytest.mark.parametrize('kind', ['frame', 'map', 'battery'])
def test_old_geometry_cannot_replace_a_missing_fresh_source(monkeypatch, kind):
    node, requests, _, sent, clock = ready_node(monkeypatch)
    refresh(node, clock, 16.)
    stamps = {'frame': node.robot_tf_received_at, 'map': node.robot_map_received_at,
              'battery': node.battery_state_received_at}[kind]
    stamps['tb1'] = 10.
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests
    assert node.pending_exploration_geometry['cursor'] == {}


def test_current_obstacles_reject_an_earlier_free_point(monkeypatch):
    node, requests, _, sent, clock = ready_node(monkeypatch)
    refresh(node, clock)
    blocked = np.full(node.map_data.shape, 100, dtype=np.int16)
    node.map_data = node.source_map_data = c.immutable_grid_snapshot(blocked, blocked.shape)
    node.robot_maps = {name: dict(data=node.map_data, resolution=.1, origin=(0., 0.))
                       for name in node.robot_positions}
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests


def test_current_unfundable_energy_model_rejects_an_earlier_funded_point(monkeypatch):
    node, requests, _, sent, clock = ready_node(monkeypatch)
    refresh(node, clock)
    node.battery_states['tb1'].update(energy=.1, capacity=.2, move_cost_per_m=100.)
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests


def test_expiry_during_readmission_does_not_advance_the_preference_cursor(monkeypatch):
    node, requests, _, sent, clock = ready_node(monkeypatch)
    refresh(node, clock)
    price = node.exploration_battery_factor
    def expire(*args):
        clock[0] = 16.
        return price(*args)
    node.exploration_battery_factor = expire
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests
    assert node.pending_exploration_geometry['cursor'] == {}


@pytest.mark.parametrize('change', ['phase', 'target', 'participants', 'age'])
def test_changed_context_or_expired_preference_is_discarded(monkeypatch, change):
    node, requests, _, sent, clock = ready_node(monkeypatch)
    refresh(node, clock, 21. if change == 'age' else 13.)
    if change == 'phase': node.task_state = 'FOUND_UNCONFIRMED'
    if change == 'target': node.target = (9., 9.)
    if change == 'participants':
        node.battery_modes['tb2'] = 'FAILED'
        node.participating_robots = lambda: ['tb1']
    install_candidates(monkeypatch, {})
    c.HeadquartersControl.assign_idle_robots(node)
    assert node.pending_exploration_geometry is None and not sent and not requests


def test_retained_points_are_bounded_and_do_not_alias_old_assignments():
    rows = [(i, 'tb1', i, assignment(2.+i*.01, 3., utility=i)) for i in range(150)]
    points = c.retained_exploration_geometry(rows[:2], rows)
    assert len(points['tb1']) == 128 and points['tb1'][:2] == ((2.01, 3.), (2., 3.))
    assert all(isinstance(point, tuple) and len(point) == 2 for point in points['tb1'])
    before = copy.deepcopy(points)
    rows.clear()
    assert points == before


def test_subset_uses_only_current_rows_and_bounds_each_robot():
    old = {'tb1': ((6., 3.),), 'tb2': ((5., 3.),)}
    rows = [(a.utility, name, a.viewpoint.group_id, a)
            for name in old for a in [assignment(5.5+i*.05, 3., utility=10.-i) for i in range(10)]]
    chosen = c.exploration_geometry_subset(rows, old, {})
    assert len(chosen) == 6 and all(any(row is current for current in rows) for row in chosen)
    assert all(sum(row[1] == name for row in chosen) == 3 for name in old)
    far = [(1., 'tb1', 1, assignment(20., 3.))]
    assert c.exploration_geometry_subset(far, old, {}) == far
