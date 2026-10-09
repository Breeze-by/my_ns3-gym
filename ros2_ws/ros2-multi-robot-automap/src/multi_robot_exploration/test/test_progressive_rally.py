"""Coarse feasible proposals may stop; infeasible ones must expand safely."""
import math

import numpy as np
import pytest

from multi_robot_exploration import control as c


def test_feasible_old_rings_stop_before_global_soft_cost_search(monkeypatch):
    coarse = c.RallyPose(5.05, 4.05, math.pi)
    fine = c.RallyPose(3.05, 4.05, 0.)
    levels = []
    def poses(*args):
        levels.append(args[-1])
        return [fine, coarse] if args[-1] else [coarse]
    monkeypatch.setattr(c, 'rally_pose_candidates', poses)
    grid = np.zeros((100, 100), dtype=np.int16)
    args = (grid, .1, (0., 0.), {'tb1': (1.05, 1.05)}, (4.05, 4.05))
    assert c.assign_rally_poses(*args) == {'tb1': coarse}
    assert levels == [False]
    assert c._assign_rally_poses(*args, stratified=True) == {'tb1': fine}


def test_coarse_separation_failure_expands_to_visible_sliver_representatives(monkeypatch):
    near = [c.RallyPose(5.05, 4.05, math.pi), c.RallyPose(5.05, 4.15, math.pi)]
    other = c.RallyPose(3.05, 4.05, 0.)
    levels = []
    def poses(*args):
        levels.append(args[-1])
        return near + [other] if args[-1] else near
    monkeypatch.setattr(c, 'rally_pose_candidates', poses)
    grid = np.zeros((100, 100), dtype=np.int16)
    result = c.assign_rally_poses(grid, .1, (0., 0.),
        {'tb1': (1.05, 1.05), 'tb2': (1.05, 2.05)}, (4.05, 4.05))
    assert levels == [False, True] and len(result) == 2
    a, b = result.values()
    assert math.dist((a.x, a.y), (b.x, b.y)) >= c.RALLY_MIN_SEPARATION_M


def test_coarse_unfunded_return_expands_instead_of_accepting_nominal_short_leg(monkeypatch):
    distant, funded = c.RallyPose(8.05, 8.05, 0.), c.RallyPose(3.05, 4.05, 0.)
    levels = []
    def poses(*args):
        levels.append(args[-1])
        return [funded, distant] if args[-1] else [distant]
    monkeypatch.setattr(c, 'rally_pose_candidates', poses)
    grid = np.zeros((120, 120), dtype=np.int16)
    state = dict(mode='ACTIVE', energy=20., charge_x=4.05, charge_y=4.05,
        capacity=20., charge_target_fraction=.4, nominal_speed_mps=.18,
        idle_cost_per_sec=.02, move_cost_per_m=1., return_path_factor=2.,
        return_safety_margin=8., charge_duration_sec=6.)
    assigned = c.assign_rally_poses(grid, .1, (0., 0.),
        {'tb1': (4.05, 4.05)}, (4.05, 4.05), battery_states={'tb1': state}, observer_robot='tb1')
    assert assigned == {'tb1': funded} and levels == [False, True]
    contact, _ = c.known_return_route(grid, .1, (0., 0.), (funded.x, funded.y), (4.05, 4.05), .8)
    budget = c.battery_assignment_required_energy(1., contact, 1., .02, 2., .18, 8.) + .02 * 5.
    assert budget < state['energy']


def test_both_levels_missing_geometry_remain_failure(monkeypatch):
    levels = []
    def poses(*args):
        levels.append(args[-1])
        return []
    monkeypatch.setattr(c, 'rally_pose_candidates', poses)
    assert not c.assign_rally_poses(np.zeros((30, 30)), .1, (0., 0.), {'tb1': (1., 1.)}, (2., 2.))
    assert levels == [False, True]
