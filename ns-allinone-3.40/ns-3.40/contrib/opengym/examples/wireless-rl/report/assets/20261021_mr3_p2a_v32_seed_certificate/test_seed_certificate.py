"""Artificial maps only; never load a scene/trace or instantiate a World."""

from fractions import Fraction as Q
import math

import numpy as np
import pytest

from seed_certificate import certificate, point_rectangle_squared, segment_rectangle_squared
from multi_robot_exploration.mr3_observation import native_traversable, _seed_diagnostics


def test_original_pose_bound_0282843_rejects_but_exact_point_and_bridge_pass():
    grid = np.zeros((41, 41), dtype=np.int8)
    grid[23, 26] = 100
    res, origin, seed = .05, (-1.025, -1.025), (20, 20)
    traversable, clearance = native_traversable(grid, res)
    assert bool(traversable[seed])
    offset = float(clearance[seed] - math.sqrt(.08))
    pose = (0., -offset)
    original_seed, _, diagnostic = _seed_diagnostics(grid, traversable, clearance,
        {"fresh": True, "x": pose[0], "y": pose[1]}, res, origin)
    assert original_seed == seed
    assert diagnostic["seed_pose_clearance_lower_bound_m"] == pytest.approx(.282842712474619)
    assert diagnostic["seed_rejection_reason"] == "seed_pose_body_clearance"
    result = certificate(grid, res, origin, pose, seed, seed_cell_traversable=True)
    assert result["accepted"]
    assert Q(result["point_distance_squared_exact"]) >= Q(29, 100) ** 2
    assert Q(result["bridge_distance_squared_exact"]) >= Q(29, 100) ** 2
    assert not result["production_enabled"] and not result["observation_qualification"]


@pytest.mark.parametrize("blocked", [-1, 1, 100])
def test_unknown_or_nonfree_square_with_insufficient_pose_clearance_rejects(blocked):
    grid = np.zeros((7, 7), dtype=np.int8)
    grid[3, 4] = blocked
    traversable, _ = native_traversable(grid, 1.)
    assert bool(traversable[3, 3])
    result = certificate(grid, Q(1), (-Q(7, 2), -Q(7, 2)), (Q(1, 4), 0), (3, 3),
                         seed_cell_traversable=True)
    assert not result["accepted"] and result["reason"] == "seed_pose_body_clearance"
    assert Q(result["point_distance_squared_exact"]) == Q(1, 16)


def test_closed_corner_and_tangent_have_exact_squared_distances():
    rectangle = (Q(0), Q(0), Q(1), Q(1))
    assert point_rectangle_squared((Q(-3), Q(-4)), rectangle) == 25
    assert segment_rectangle_squared((Q(-1), Q(0)), (Q(0), Q(0)), rectangle) == 0
    assert segment_rectangle_squared((Q(-1), Q(2)), (Q(2), Q(-1)), rectangle) == 0
    assert segment_rectangle_squared((Q(-1), Q(2)), (Q(2), Q(2)), rectangle) == 1


def test_diagonal_closed_square_corner_rejects_insufficient_pose_clearance():
    grid = np.zeros((7, 7), dtype=np.int8)
    grid[4, 4] = 100
    traversable, _ = native_traversable(grid, 1.)
    assert bool(traversable[3, 3])
    result = certificate(grid, 1, (-Q(7, 2), -Q(7, 2)), (Q(2, 5), Q(2, 5)),
                         (3, 3), seed_cell_traversable=True)
    assert result["reason"] == "seed_pose_body_clearance"
    assert Q(result["point_distance_squared_exact"]) == Q(1, 50)


def test_bridge_middle_fails_even_when_both_endpoints_and_original_cell_pass():
    grid = np.zeros((5, 5), dtype=np.int8)
    grid[1, 3] = 100
    res, origin = Q(43, 100), (-Q(43, 40), -Q(43, 40))
    pose = (Q(43, 250), Q(43, 500))
    traversable, _ = native_traversable(grid, float(res))
    assert bool(traversable[2, 2])
    square = (Q(43, 200), -Q(129, 200), Q(129, 200), -Q(43, 200))
    assert point_rectangle_squared(pose, square) >= Q(29, 100) ** 2
    assert point_rectangle_squared((Q(0), Q(0)), square) >= Q(29, 100) ** 2
    result = certificate(grid, res, origin, pose, (2, 2), seed_cell_traversable=True)
    assert result["reason"] == "seed_bridge_body_clearance"
    assert Q(result["bridge_distance_squared_exact"]) == Q(16641, 200000)


def test_original_cell_gate_false_is_not_replaced_even_when_exact_geometry_passes():
    grid = np.zeros((3, 3), dtype=np.int8)
    traversable, _ = native_traversable(grid, .2)
    assert not bool(traversable[1, 1])
    result = certificate(grid, Q(1, 5), (0, 0), (Q(3, 10), Q(3, 10)),
                         (1, 1), seed_cell_traversable=False)
    assert not result["accepted"] and result["reason"] == "seed_cell_body_clearance"
    assert Q(result["point_distance_squared_exact"]) >= Q(29, 100) ** 2
    assert Q(result["bridge_distance_squared_exact"]) >= Q(29, 100) ** 2


@pytest.mark.parametrize("pose", [(Q(-1, 100), Q(1, 2)), (Q(0), Q(1, 2)),
                                  (Q(1, 100), Q(1, 2))])
def test_outside_closed_boundary_and_near_outside_blocked_region_reject(pose):
    result = certificate(np.zeros((7, 7), dtype=np.int8), 1, (0, 0), pose, (0, 0),
                         seed_cell_traversable=True)
    assert not result["accepted"]
    assert Q(result["point_distance_squared_exact"]) < Q(29, 100) ** 2


def test_supplied_seed_is_not_replaced_or_snapped_and_input_map_is_unchanged():
    grid = np.zeros((7, 7), dtype=np.int8)
    before = grid.copy()
    result = certificate(grid, 1, (0, 0), (Q(9, 2), Q(7, 2)), (3, 3),
                         seed_cell_traversable=True)
    assert result["reason"] == "pose_not_in_original_seed_cell"
    assert result["seed_cell"] == [3, 3]
    np.testing.assert_array_equal(grid, before)


@pytest.mark.parametrize("pose", [(float("nan"), 0), (True, 0)])
def test_nonfinite_or_boolean_pose_is_rejected(pose):
    with pytest.raises(ValueError):
        certificate(np.zeros((3, 3), dtype=np.int8), 1, (0, 0), pose, (1, 1),
                    seed_cell_traversable=True)
