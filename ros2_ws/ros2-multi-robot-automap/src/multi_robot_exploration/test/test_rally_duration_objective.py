"""Real route counterexample: soft exposure must not dominate mission time."""
import math

import numpy as np
import pytest

from multi_robot_exploration import control as c


def test_global_duration_objective_keeps_funded_observer_at_legal_view(monkeypatch):
    resolution = .05
    grid = np.zeros((400, 400), dtype=np.int16)
    grid[[0, -1], :] = 100
    grid[:, [0, -1]] = 100
    grid[1:-1, 200] = 100
    grid[40:56, 200] = 0  # Lower .8m drive-through doorway.
    grid[320:329, 200] = 0  # Upper camera slit cannot admit a robot.
    position, target = (9.025, 16.225), (10.025, 16.225)
    poses = [c.RallyPose(9.025, 16.225, 0.), c.RallyPose(11.025, 16.225, math.pi)]
    state = dict(mode='ACTIVE', energy=80., capacity=100., charge_target_fraction=.8,
        charge_x=11.025, charge_y=2.425, charge_radius_m=.8, nominal_speed_mps=.18,
        move_cost_per_m=1., idle_cost_per_sec=.02, return_path_factor=2.,
        return_safety_margin=5., return_recovery_wait_sec=30., charge_duration_sec=10.)
    travel = []
    for pose in poses:
        assert c.rally_target_view(grid, resolution, (0., 0.), (pose.x, pose.y), target, 2.65)
        cell = c.world_to_grid(pose.x, pose.y, resolution, 0., 0.)
        assert c.traversable_grid(grid, resolution, c.RALLY_CLEARANCE_M)[cell]
        _, route = c.plan_rally_leg(pose, grid, resolution, (0., 0.), position)
        full = (position, *route)
        assert c.route_respects_known_obstacles(grid, resolution, (0., 0.), full)
        distance = sum(math.dist(a, b) for a, b in zip(full, full[1:]))
        returns = c.qualified_return_candidates(grid, resolution, (0., 0.),
            (pose.x, pose.y), (state['charge_x'], state['charge_y']), .8)
        contact = min(row['path_distance_m'] for row in returns if row['qualified'])
        required = c.battery_assignment_required_energy(distance, contact,
            1., .02, 2., .18, 5., 30.) + .02 * 5.
        assert required < state['energy']
        travel.append(distance / state['nominal_speed_mps'])
    assert travel[0] == pytest.approx(0.)
    assert travel[1] > 150.
    # Restrict enumeration to two independently legal poses; all approach,
    # qualified return, energy and waiting calculations remain real.
    monkeypatch.setattr(c, 'rally_pose_candidates', lambda *args, **kwargs: poses)
    arguments = dict(raw_grid=grid, resolution=resolution, origin=(0., 0.),
        robot_positions={'tb1': position}, target=target,
        battery_states={'tb1': state}, observer_robot='tb1')
    historical = c.assign_rally_poses(**arguments)
    assert historical == {'tb1': poses[1]}
    assert c.assign_rally_poses(**arguments, resource_objective='return_exposure') == historical
    assert c.assign_rally_poses(**arguments, resource_objective='serial_time') == {'tb1': poses[0]}
    # Funding/observer protection still outranks both optional preferences.
    state['energy'] = 50.
    assert c.assign_rally_poses(**arguments) == {'tb1': poses[0]}
    assert c.assign_rally_poses(**arguments, resource_objective='serial_time') == {'tb1': poses[0]}


def test_unknown_resource_objective_is_rejected():
    with pytest.raises(ValueError, match='unknown rally resource objective'):
        c.assign_rally_poses(np.zeros((40, 40)), .1, (0., 0.),
            {'tb1': (1.25, 1.25)}, (2., 2.), resource_objective='unknown')
