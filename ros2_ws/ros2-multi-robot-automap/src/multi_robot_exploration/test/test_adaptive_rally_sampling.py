"""Bounded outer-ring refinement keeps the original geometric requirements."""
import math

import numpy as np
import pytest

from multi_robot_exploration import control as c


def test_visible_arc_boundary_adds_points_without_reordering_old_candidates(monkeypatch):
    grid = np.zeros((160, 160), dtype=np.int16)
    target = (4.025, 4.025)
    resolution = .05
    def visible(raw, cell, target_cell):
        x, y = c.grid_to_world(*cell, resolution, 0., 0.)
        angle = math.degrees(math.atan2(y-target[1], x-target[0])) % 360
        return 11 < angle < 28
    monkeypatch.setattr(c, 'has_known_line_of_sight', visible)
    old = c.rally_pose_candidates(grid, resolution, (0., 0.), target)
    new = c.rally_pose_candidates(grid, resolution, (0., 0.), target, adaptive_outer=True)
    assert new[:len(old)] == old and len(new) > len(old)
    assert all(visible(grid, c.world_to_grid(p.x, p.y, resolution, 0., 0.), None)
               for p in new[len(old):])
    assert all(abs(math.dist((p.x, p.y), target)-2.6) <= resolution
               for p in new[len(old):])


def test_fully_visible_ring_and_recovery_tiers_are_unchanged():
    grid = np.zeros((160, 160), dtype=np.int16)
    args = (grid, .05, (0., 0.), (4.025, 4.025))
    for dense, stratified in ((False, False), (False, True), (True, False)):
        assert c.rally_pose_candidates(*args, dense, stratified, True) == \
               c.rally_pose_candidates(*args, dense, stratified)


@pytest.mark.parametrize('seed', range(12))
def test_unknown_and_obstacles_preserve_clearance_visibility_uniqueness_and_bound(seed):
    rng = np.random.default_rng(seed)
    grid = np.zeros((180, 180), dtype=np.int16)
    for _ in range(14):
        row, column = rng.integers(10, 160, size=2)
        grid[row:row+8, column:column+8] = rng.choice([-1, 100])
    target = (4.525, 4.525)
    args = (grid, .05, (0., 0.), target)
    old = c.rally_pose_candidates(*args)
    new = c.rally_pose_candidates(*args, adaptive_outer=True)
    assert new[:len(old)] == old and len(new)-len(old) <= 48
    cells = [c.world_to_grid(p.x, p.y, .05, 0., 0.) for p in new]
    assert len(cells) == len(set(cells))
    safe = c.traversable_grid(grid, .05, c.RALLY_CLEARANCE_M)
    target_cell = c.world_to_grid(*target, .05, 0., 0.)
    for pose, cell in zip(new, cells):
        assert safe[cell] and grid[cell] == 0
        assert c.has_known_line_of_sight(grid, cell, target_cell)
        assert pose.yaw == pytest.approx(math.atan2(target[1]-pose.y, target[0]-pose.x))


def test_outside_target_stays_unavailable():
    assert not c.rally_pose_candidates(np.zeros((20, 20)), .05, (0., 0.),
                                       (-1., 1.), adaptive_outer=True)
