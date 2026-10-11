"""First real exploration stays near home; clearance has no camera heading."""
import copy
import gzip
import json
import math
from pathlib import Path

import pytest

from multi_robot_exploration import control as c
from p2c_initial_replenishment import audit_initial_prefix
from p2c_return_preparation import audit_preparation
from test_departure_heading import publish_decision
from test_exploration_charging import assignment, install_candidates
from test_exploration_return_preparation import advance_sources, node as yield_node
from test_known_search_fallback import fallback_node


FIXTURE = json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v79_first_leg_inputs.json.gz', 'rt'))
assert FIXTURE['source_commit'] == 'fcbc3f47fd1e03bfb3574da8650142d092da8a98'


def first_node():
    h, requests, events, sent = fallback_node()
    h.battery_states['tb1'].update(energy=40., charge_count=0, charge_radius_m=.8)
    h.successful_exploration_legs = {}
    h.send_goal = lambda name, goal: publish_decision(h, sent, name, goal)
    return h, requests, events, sent


def reference_assign():
    namespace = dict(vars(c))
    exec(compile(FIXTURE['original_assign'], '<fcbc3f4 original assign>', 'exec'), namespace)
    return namespace['assign_idle_robots']


@pytest.mark.parametrize('phase', ['EXPLORE', 'FOUND_UNCONFIRMED'])
def test_same_frontier_and_complete_price_but_first_prefix_keeps_old_topup_window(monkeypatch, phase):
    install_candidates(monkeypatch, {'tb1': [assignment(4., 3., distance=2.)]})
    results = []
    for assign in (reference_assign(), c.HeadquartersControl.assign_idle_robots):
        h, requests, events, sent = first_node(); h.task_state = phase
        assign(h)
        assert len(sent) == 1 and not requests and not h.successful_exploration_legs
        event = next(e for e in events if e.get('event') == 'coordinator_navigation_decision')
        results.append((sent[0][1], event))
    old, new = (row[0] for row in results)
    assert (old.x, old.y, old.path_distance_m, old.utility) == (new.x, new.y, new.path_distance_m, new.utility)
    assert math.dist((old.navigation_x, old.navigation_y), (2., 3.)) > 1.6
    assert .35 < math.dist((new.navigation_x, new.navigation_y), (2., 3.)) <= 1.25
    assert results[0][1]['travel_preference']['required_energy'] == results[1][1]['travel_preference']['required_energy']
    assert audit_initial_prefix({'tb1': [results[1][1]]}, {}, True)['bounded_first_legs'] == 1


@pytest.mark.parametrize('reason', ['work', 'charged', 'full', 'mapping_only', 'far'])
def test_prefix_preference_does_not_change_later_or_ineligible_work(monkeypatch, reason):
    install_candidates(monkeypatch, {'tb1': [assignment(4., 3., distance=2.)]})
    h, requests, events, sent = first_node()
    if reason == 'work': h.successful_exploration_legs['tb1'] = 2
    if reason == 'charged': h.battery_states['tb1']['charge_count'] = 1
    if reason == 'full': h.battery_states['tb1']['energy'] = 80.
    if reason == 'mapping_only': h.enable_rally = False
    if reason == 'far': h.robot_positions['tb1'] = (3., 3.)
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent) == 1 and not requests
    assert sent[0][1].navigation_x == pytest.approx(4.05)
    assert h.exploration_travel_choices['tb1']['initial_replenishment_prefix'] is None


@pytest.mark.parametrize('reason', ['stale', 'unfunded', 'body', 'no_return'])
def test_short_first_leg_does_not_replace_full_trip_admission(monkeypatch, reason):
    h, requests, events, sent = first_node()
    install_candidates(monkeypatch, {'tb1': [assignment(4., 3., distance=2.)]})
    if reason == 'stale': h.clock = 12.001
    if reason == 'unfunded': h.battery_states['tb1']['energy'] = 1.
    if reason == 'body': h.robot_positions['tb2'] = (2., 3.)
    if reason == 'no_return': monkeypatch.setattr(c.HeadquartersControl, 'exploration_required_energy', lambda *a, **k: None)
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent


@pytest.mark.parametrize('tamper', ['missing', 'position', 'limit', 'source', 'prior_success', 'charged', 'bool_count', 'endpoint', 'undeclared'])
def test_independent_first_prefix_reader_rejects_invalid_authority(monkeypatch, tamper):
    h, _, events, _ = first_node()
    install_candidates(monkeypatch, {'tb1': [assignment(4., 3., distance=2.)]})
    c.HeadquartersControl.assign_idle_robots(h)
    event = copy.deepcopy(next(e for e in events if e.get('event') == 'coordinator_navigation_decision'))
    saved = event['travel_preference']['initial_replenishment_prefix']; successes = {}
    if tamper == 'missing': del event['travel_preference']['initial_replenishment_prefix']
    if tamper == 'position': saved['robot_position'][0] += .1
    if tamper == 'limit': saved['maximum_home_distance_m'] += .1
    if tamper == 'source': saved['generated_at_sec'] = 13.
    if tamper == 'prior_success': successes = {'tb1': [9.]}
    if tamper == 'charged': saved['battery_state']['charge_count'] = 1
    if tamper == 'bool_count': saved['completed_exploration_legs'] = False
    if tamper == 'endpoint': event['requested_position'] = [4., 3.]
    with pytest.raises(AssertionError):
        audit_initial_prefix({'tb1': [event]}, successes, tamper != 'undeclared')


@pytest.mark.parametrize('bad', ['completed', 'bool_completed', 'charged', 'bool_charge', 'missing', 'nan', 'radius', 'capacity', 'fraction', 'energy', 'far'])
def test_first_prefix_model_requires_valid_exact_initial_history(bad):
    state = dict(charge_count=0, charge_radius_m=.8, capacity=100., charge_target_fraction=.8, energy=40., charge_x=0., charge_y=0.)
    completed, position = 0, (0., 0.)
    if bad == 'completed': completed = 1
    if bad == 'bool_completed': completed = False
    if bad == 'charged': state['charge_count'] = 1
    if bad == 'bool_charge': state['charge_count'] = False
    if bad == 'missing': del state['charge_radius_m']
    if bad == 'nan': state['energy'] = float('nan')
    if bad == 'radius': state['charge_radius_m'] = .1
    if bad == 'capacity': state['capacity'] = -100.
    if bad == 'fraction': state['charge_target_fraction'] = 2.
    if bad == 'energy': state['energy'] = 80.
    if bad == 'far': position = (2., 0.)
    assert c.initial_replenishment_prefix(state, position, completed, .1) is None


def test_pending_refuge_uses_the_fresh_admission_position_and_keeps_zero_work_credit():
    h, events, sent, _ = yield_node()
    assert c.HeadquartersControl.prepare_exploration_return(h, 'tb1')
    proposal = h.pending_exploration_return_yield
    h.robot_positions['tb2'] = (.1, 0.)
    advance_sources(h, 13.)
    assert c.HeadquartersControl.admit_exploration_return_yield(h) and len(sent) == 1
    goal = sent[0][1]
    assert goal.navigation_yaw == math.atan2(goal.navigation_y, goal.navigation_x - .1)
    assert goal.navigation_yaw != proposal['refuge'].yaw
    assert audit_preparation(events[0], True) == 'yield'
    c.HeadquartersControl.finish_goal(h, 'tb2', True)
    assert h.successful_exploration_legs['tb2'] == 7


def test_final_reservation_endpoint_must_still_satisfy_the_near_home_window(monkeypatch):
    h, _, _, sent = first_node()
    install_candidates(monkeypatch, {'tb1': [assignment(4., 3., distance=2.)]})
    monkeypatch.setattr(c, 'reserve_rally_prefix',
        lambda plan, reservations: (c.RallyPose(3.5, 3., 0.), ((2., 3.), (3.5, 3.))))
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent) == 1 and not h.successful_exploration_legs
    assert h.exploration_travel_choices['tb1']['initial_replenishment_prefix'] is None


@pytest.mark.parametrize('index', range(4))
def test_original_lab_maps_routes_and_full_price_accept_only_motion_bearing(index):
    original = [e for e in FIXTURE['original_events']['dev_lab101'] if e.get('kind') == 'exploration_return_yield'][index]
    assert audit_preparation(original) == 'yield'
    event = copy.deepcopy(original)
    point, position = event['requested_position'], event['current_position']
    yaw = math.atan2(point[1]-position[1], point[0]-position[0])
    event['requested_yaw'] = yaw
    event['return_preparation']['motion_heading'] = dict(strategy='fresh_visible_leg_bearing', robot_position=position, yaw=yaw, evaluated_at_sec=event['event_time'])
    assert audit_preparation(event, True) == 'yield'
    assert event['return_preparation']['required_energy'] == original['return_preparation']['required_energy']
    event['requested_yaw'] = original['requested_yaw']
    with pytest.raises(AssertionError): audit_preparation(event, True)
