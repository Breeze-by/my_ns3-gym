"""Whole-route budgets and contact reservations must outlive a short Nav2 leg."""
import math

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_control import rally_budget_node


def test_return_reserves_later_segments_and_reachable_contact_not_blocked_centre():
    grid = np.zeros((90, 140), dtype=np.int16)
    home = (11.05, 4.05)
    grid[40, 110] = 100
    position = (1.05, 4.05)
    state = dict(charge_x=home[0], charge_y=home[1], charge_radius_m=.8)
    assert not c.plan_rally_leg(c.RallyPose(*home, 0.), grid, .1, (0., 0.), position)[1]
    caches = {}
    reserved = c.rally_return_reservations(grid, .1, (0., 0.), {'tb1': position},
        {'tb1': state}, {'tb1': 'RETURNING'}, set(), caches)['tb1']
    cost, expected = c.known_return_route(grid, .1, (0., 0.), position, home, .8,
        include_route=True)
    assert reserved == expected and caches['tb1']['delivered_fused']['field'] is not None
    assert cost > 9. and sum(math.dist(a, b) for a, b in zip(reserved, reserved[1:])) == pytest.approx(cost)
    assert .35 < math.dist(reserved[-1], home) <= .6 + 1e-8
    assert c.routes_conflict(reserved, ((9.05, 4.05),))
    future = c.rally_return_reservations(grid, .1, (0., 0.), {'tb1': position},
        {'tb1': state}, {'tb1': 'ACTIVE'}, {'tb1'}, caches)
    assert future == {'tb1': reserved}


def test_preflight_prices_whole_approach_and_position_to_grid_offset():
    node, messages, failures = rally_budget_node(energy=33.01)
    node.robot_positions['tb1'] = (1.06, 1.06)
    _, prefix = c.plan_rally_leg(node.rally_final_targets['tb1'], node.map_data,
        node.resolution, node.origin, node.robot_positions['tb1'], max_distance_m=5.)
    assert sum(math.dist(a, b) for a, b in zip(prefix, prefix[1:])) <= 5.
    required = c.HeadquartersControl.task_return_required_energy(node, 'tb1', 7. + math.sqrt(2) * .01, (8.05, 1.05)) + .02 * 5.
    assert required > 33.01
    assert c.HeadquartersControl.prepare_rally_charges(node) == {'tb1'}
    assert node.rally_charge_budgets['tb1'] == pytest.approx(required)
    assert node.rally_approach_routes['tb1'][-1] == pytest.approx((8.05, 1.05))
    assert len(messages) == 1 and not failures


def test_leg_admission_prices_entire_remaining_approach():
    node, _, _ = rally_budget_node(energy=40.)
    node.rally_detour_budgets = {}
    c.HeadquartersControl.prepare_rally_charges(node)
    # Only the first metre is dispatched; the other six still need funding.
    plan = (c.RallyPose(2.05, 1.05, 0.), ((1.05, 1.05), (2.05, 1.05)))
    assert c.HeadquartersControl.rally_plan_has_energy(node, 'tb1', plan)
    node.battery_states['tb1']['energy'] = 32.
    assert not c.HeadquartersControl.rally_plan_has_energy(node, 'tb1', plan)
    assert node.rally_detour_budgets['tb1'] > 32.
