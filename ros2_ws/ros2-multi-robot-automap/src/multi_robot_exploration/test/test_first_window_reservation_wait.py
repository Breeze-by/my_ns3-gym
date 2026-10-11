"""A blocked first near-home leg waits finitely without earning work credit."""
import copy
import gzip
import json
from pathlib import Path

import pytest

from multi_robot_exploration import control as c
from p2c_initial_replenishment import audit_first_window_reservation_waits
from p2c_return_preparation import decode_grid
from test_exploration_charging import assignment, install_candidates
from test_first_leg_return_heading import first_node
from test_first_window_geometry_handoff import fresh

FIXTURE = json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v82_first_window_reservation_inputs.json.gz', 'rt'))
assert FIXTURE['source_commit'] == '2f4aeda579e8ec2efe2c419d8e8ab3adb844d349'


def original_assign():
    namespace = dict(vars(c))
    exec(compile(FIXTURE['original_assign'], '<original 2f4aeda assign>', 'exec'), namespace)
    return namespace['assign_idle_robots']


def node(monkeypatch):
    h, requests, events, sent = first_node();h.goal_timeout_sec = 60.
    originals = FIXTURE['original_inputs']['dev_rooms202']['original_first_navigation']
    e = next(e for e in originals if e['robot'] == 'tb1')
    peer = next(e for e in originals if e['robot'] == 'tb3')
    grid = e['planning_map'];h.map_data = decode_grid(grid);h.source_map_data = h.map_data
    h.resolution = grid['resolution'];h.origin = grid['origin']
    h.robot_positions = {name:tuple(p) for name,p in e['robot_positions'].items()}
    h.battery_states = copy.deepcopy(e['battery_states'])
    h.robot_states = {'tb1':'idle','tb2':'idle','tb3':'active'}
    h.battery_modes = dict.fromkeys(h.robot_positions,'ACTIVE')
    h.robot_maps = {name:dict(data=decode_grid(g),resolution=g['resolution'],origin=g['origin'])
        for name,g in e['return_maps'].items()}
    h.goal_handles = dict.fromkeys(h.robot_positions);h.goal_targets = dict.fromkeys(h.robot_positions)
    h.goal_routes = {'tb3':peer['outbound_map_route']['route'][1:]}
    h.participating_robots = h.input_robot_names = lambda:list(h.robot_positions)
    for field in ('robot_odom_received_at','robot_tf_received_at','robot_map_received_at','battery_state_received_at'):
        setattr(h,field,dict.fromkeys(h.robot_positions,10.))
    h.frontier_cache = c.prepare_frontier_data(h.map_data,h.resolution)
    context = ('EXPLORE', False, ('tb1', 'tb2', 'tb3'), None)
    hints = e['travel_preference']['first_window_geometry_preference']['points']
    current = e['travel_preference']['first_window_geometry_preference']['current_candidate_points']
    normal = e['travel_preference']['target']
    h.pending_exploration_geometry = dict(context=context, generated_at=10., cursor={},
        points={'tb1': [normal]}, first_window_geometry={'tb1': dict(
            points=hints, generated_at_sec=10., expired_at_sec=12.1)})
    install_candidates(monkeypatch, {'tb1':[assignment(x,y,distance=2.,utility=100.-i)
        for i,(x,y) in enumerate([*current,normal])]})
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:[])
    fresh(h, 13.)
    return h, requests, events, sent


def waits(events):
    return [e for e in events if e.get('event') == 'coordinator_first_window_reservation_wait']


def test_original_far_fallback_new_wait_then_current_near_home_dispatch(monkeypatch):
    old, old_requests, old_events, old_sent = node(monkeypatch)
    original_assign()(old)
    assert len(old_sent) == 1 and old_sent[0][1].navigation_x < -2.
    assert not old_requests and not old.successful_exploration_legs
    h, requests, events, sent = node(monkeypatch)
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and not requests and not h.successful_exploration_legs
    e = waits(events)[0]
    assert audit_first_window_reservation_waits([e], {'tb1': [e['battery_state']]}, True)['waits'] == 1
    assert h.first_window_reservation_waits['started']['tb1'] == 13.
    fresh(h, 14.);h.goal_routes['tb3'] = ()
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent) == 1
    goal = sent[0][1];state = h.battery_states['tb1']
    assert c.math.dist((goal.navigation_x,goal.navigation_y),(state['charge_x'],state['charge_y'])) <= 1.25
    assert not requests and not h.successful_exploration_legs
    assert 'tb1' not in h.first_window_reservation_waits['started']


def test_wait_reaches_original_timeout_without_renewing_its_start(monkeypatch):
    h, requests, events, sent = node(monkeypatch)
    hints = copy.deepcopy(h.pending_exploration_geometry)
    c.HeadquartersControl.assign_idle_robots(h)
    fresh(h, 14.);c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and h.first_window_reservation_waits['started']['tb1'] == 13.
    fresh(h, 23.)
    h.pending_exploration_geometry = hints
    h.pending_exploration_geometry['generated_at'] = 22.
    h.pending_exploration_geometry['first_window_geometry']['tb1'].update(generated_at_sec=22., expired_at_sec=22.1)
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent) == 1 and sent[0][1].navigation_x < -2.
    assert not requests and not h.successful_exploration_legs
    assert len(waits(events)) == 2


@pytest.mark.parametrize('change', ['success', 'charged', 'full_energy', 'far', 'mapping_only'])
def test_ineligible_first_window_uses_original_normal_admission(monkeypatch, change):
    results = []
    for use_original in (True, False):
        h, requests, events, sent = node(monkeypatch)
        if change == 'success':h.successful_exploration_legs['tb1'] = 2
        elif change == 'charged':h.battery_states['tb1']['charge_count'] = 1
        elif change == 'full_energy':h.battery_states['tb1']['energy'] = 80.
        elif change == 'far':h.robot_positions['tb1'] = (-2., 0.)
        else:h.enable_rally = False
        assign = original_assign() if use_original else c.HeadquartersControl.assign_idle_robots
        assign(h)
        assert not waits(events)
        results.append((sent, requests))
    assert results[0] == results[1]


@pytest.mark.parametrize('change', ['stale', 'unfunded', 'no_return'])
def test_wait_has_no_authority_from_unusable_current_inputs(monkeypatch, change):
    h, requests, events, sent = node(monkeypatch)
    if change == 'stale':h.clock = 15.001
    elif change == 'unfunded':h.battery_states['tb1']['energy'] = 1.
    else:monkeypatch.setattr(c.HeadquartersControl, 'exploration_required_energy', lambda *a, **k: None)
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and not waits(events)


@pytest.mark.parametrize('tamper', ['undeclared', 'native', 'charged', 'count', 'expired', 'source', 'motion', 'credit', 'routes'])
def test_reader_rejects_forged_wait_authority(monkeypatch, tamper):
    h, _, events, _ = node(monkeypatch);c.HeadquartersControl.assign_idle_robots(h)
    e = copy.deepcopy(waits(events)[0]);native = {'tb1': [copy.deepcopy(e['battery_state'])]}
    if tamper == 'native':native['tb1'][0]['energy'] += 1.
    elif tamper == 'charged':e['battery_state']['charge_count'] = 1
    elif tamper == 'count':e['completed_exploration_legs'] = False
    elif tamper == 'expired':
        e['planning_started_at_sec'] = e['event_time'] = e['started_at_sec']+e['wait_timeout_sec']
    elif tamper == 'source':e['inputs']['tb1/pose_state']['source_time'] -= 3.
    elif tamper == 'motion':e['movement_authorized'] = True
    elif tamper == 'credit':e['native_credit_added'] = True
    elif tamper == 'routes':e['reserved_routes'] = []
    with pytest.raises((AssertionError, KeyError)):
        audit_first_window_reservation_waits([e], native, tamper != 'undeclared')


def test_original_corridor_pool_has_safe_geometry_outside_three_blocked_hints():
    data = FIXTURE['original_reservation_geometry']['cases']
    assert data['dev_corridors303']['shortlist']['admitted'] == 0
    assert data['dev_corridors303']['full_pool']['admitted'] == 33
    assert data['dev_rooms202']['shortlist']['admitted'] == data['dev_rooms202']['full_pool']['admitted'] == 0
