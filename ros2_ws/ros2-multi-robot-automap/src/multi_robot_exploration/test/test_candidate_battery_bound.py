import dataclasses
import copy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control
from test_exploration_resume import conditional_snapshot_node


REFERENCE = json.loads((Path(__file__).parent / 'fixtures/p2c_v36_charge_pricing_reference.json').read_text())


def reference_assign():
    assert hashlib.sha256(REFERENCE['function'].encode()).hexdigest() == REFERENCE['function_sha256']
    namespace = dict(vars(control))
    exec(compile(REFERENCE['function'], '<7a7fde6 independent assign reference>', 'exec'), namespace)
    return namespace['assign_idle_robots']


def conditional_charge(event, assign):
    d = event['diagnostic_inputs']
    e = dict(d, inputs=event['inputs_at_start'], event_time=event['planning_started_at_sec'])
    node, sent = conditional_snapshot_node(e, d['exploration_resume_intents'].copy())
    node.robot_states = d['robot_states'].copy()
    node.battery_modes = d['battery_modes'].copy()
    node.active_exclusions = lambda: d['exclusions']
    node.enable_rally = d['enable_rally']
    node.initial_search_next = d['initial_search_next'].copy()
    node.initial_search_visits = dict(enumerate(d['initial_search_visits']))
    node.initial_search_views = dict(enumerate(d['initial_search_views']))
    node.target_search_visits = d['target_search_visits'].copy()
    node.successful_exploration_legs = d['successful_exploration_legs'].copy()
    node.rally_charge_requested = d['rally_charge_requested'].copy()
    node.goal_routes = d['goal_routes'].copy()
    node.goal_targets = {n: None if a is None else control.Assignment(
        **{**a, 'viewpoint': control.Viewpoint(**a['viewpoint'])}) for n, a in d['goal_targets'].items()}
    requests = []
    node.exploration_charge_budgets = {}
    node.charge_request_publishers = {n: SimpleNamespace(publish=lambda msg: requests.append(json.loads(msg.data)))
                                    for n in d['battery_states']}
    assign(node)
    return json.loads(json.dumps(dict(sent=sent, requests=requests, choices=node.exploration_travel_choices),
                                default=dataclasses.asdict))


@pytest.mark.parametrize('stage', sorted(REFERENCE['snapshots']))
def test_original_charge_intent_and_provisional_search_are_preserved(stage):
    event = REFERENCE['snapshots'][stage]
    expected = conditional_charge(event, reference_assign())
    actual = conditional_charge(event, control.HeadquartersControl.assign_idle_robots)
    assert not expected['sent'] and expected['requests'] and actual == expected


@pytest.mark.parametrize('energy', [12., 20., 80.])
def test_synthetic_funded_alternatives_are_not_hidden_by_a_charge_intent(energy):
    event = copy.deepcopy(REFERENCE['snapshots']['candidate_budget'])
    event['diagnostic_inputs']['battery_states']['tb2']['energy'] = energy
    assert conditional_charge(event, control.HeadquartersControl.assign_idle_robots) == conditional_charge(event, reference_assign())


def test_sources_expiring_inside_price_abort_before_tighter_heap_bound():
    event = REFERENCE['snapshots']['candidate_budget']
    records = []
    def expire(node):
        current = [event['planning_started_at_sec']]
        node.now = lambda: current[0]
        node.consumed_publisher = SimpleNamespace(publish=lambda msg: records.append(json.loads(msg.data)))
        def price(*args):
            current[0] = event['source_deadline_sec']+.01
            return 1.  # Even an unexpectedly high stale price never enters the heap.
        node.exploration_battery_factor = price
        control.HeadquartersControl.assign_idle_robots(node)
    result = conditional_charge(event, expire)
    assert not result['sent'] and not result['requests']
    assert any(row['event']=='coordinator_planning_lease_expired' and row['stage']=='candidate_budget' for row in records)


@pytest.mark.parametrize('seed', range(12))
def test_bound_dominates_full_qualified_path_price_and_later_source_ages(seed):
    rng = np.random.default_rng(seed)
    for _ in range(80):
        pos, dest, home = [tuple(rng.uniform(-10., 10., 2)) for _ in range(3)]
        d = rng.uniform(.1, 20.); radius = rng.uniform(.21, 1.5)
        state = dict(energy=rng.uniform(.01, 100.), charge_x=home[0], charge_y=home[1],
                     charge_radius_m=radius, move_cost_per_m=rng.uniform(.1, 2.),
                     idle_cost_per_sec=rng.uniform(0., .2), return_path_factor=rng.uniform(1., 3.),
                     nominal_speed_mps=rng.uniform(.1, .4), return_safety_margin=rng.uniform(1., 10.),
                     return_recovery_wait_sec=rng.uniform(0., 30.))
        map_age, pose_age = rng.uniform(0., 4.), rng.uniform(0., 1.)
        bound = control.exploration_battery_factor_bound(state, pos, d, dest, map_age, pose_age)
        def price(approach, point):
            # Full detours are independent of the implementation's lower bound.
            contact = max(0., math.dist(point, home)-radius)+rng.uniform(0., 8.)
            return control.battery_assignment_required_energy(approach, contact,
                state['move_cost_per_m'], state['idle_cost_per_sec'], state['return_path_factor'],
                state['nominal_speed_mps'], state['return_safety_margin'], state['return_recovery_wait_sec'],
                map_age+.5, pose_age+.5)
        required = max(price(d, dest), price(0., pos))
        factor = 1. if state['energy'] > required else .25*state['energy']/required
        assert 0. <= factor <= bound <= 1.
        if bound < 1.:
            assert factor < 1.  # A resolved charge may not hide a funded option.


@pytest.mark.parametrize('override', [dict(energy=float('nan')), dict(charge_radius_m=.1),
    dict(return_path_factor=.5), dict(nominal_speed_mps=0.), dict(move_cost_per_m=-1.),
    dict(idle_cost_per_sec=-1.), dict(return_recovery_wait_sec=-1.)])
def test_invalid_model_keeps_neutral_computational_bound(override):
    state = {**dict(energy=1., charge_x=0., charge_y=0.), **override}
    assert control.exploration_battery_factor_bound(state, (0., 0.), 10., (10., 0.), 0., 0.) == 1.


@pytest.mark.parametrize('ages', [(5.1, 0.), (0., 2.1), (-1., 0.), (None, 0.)])
def test_invalid_source_age_cannot_be_used_as_budget_evidence(ages):
    state = dict(energy=1., charge_x=0., charge_y=0.)
    assert control.exploration_battery_factor_bound(state, (0., 0.), 10., (10., 0.), *ages) == 1.


def test_missing_model_cannot_discard_candidates():
    assert control.exploration_battery_factor_bound({}, (0., 0.), 10., (10., 0.), 0., 0.) == 1.


def test_known_route_is_still_required_even_for_a_geometric_return():
    e = REFERENCE['snapshots']['candidate_budget']
    d = e['diagnostic_inputs']; node, _ = conditional_snapshot_node(
        dict(d, inputs=e['inputs_at_start'], event_time=e['planning_started_at_sec']), {})
    node.map_data = node.source_map_data = np.full(node.map_data.shape, -1, dtype=np.int16)
    node.robot_maps = {}
    state = node.battery_states['tb1']
    assert control.exploration_battery_factor_bound(state, (0., 0.), .1, (.1, 0.), 0., 0.) == 1.
    assert control.HeadquartersControl.exploration_required_energy(node, 'tb1', .1, (.1, 0.)) is None
