"""Artificial received grids only; no scene, World, ROS node or experiment."""

from fractions import Fraction as Q
import math
import random

import numpy as np
import pytest

from multi_robot_exploration.mr3_observation import native_traversable, _seed_diagnostics
from multi_robot_exploration.mr3_seed_certificate import certify_seed_pose_bridge, REQUIRED_M


def _piecewise_distance_squared(start, end, box):
    """Independent oracle: minimize piecewise quadratic distance in t.

    Unlike production's slab/corner formula, partition at every box-side
    crossing, then minimize the quadratic on each closed parameter interval.
    """
    delta = tuple(end[i] - start[i] for i in range(2))
    breaks = {Q(0), Q(1)}
    for axis in range(2):
        if delta[axis]:
            for side in (box[axis], box[axis + 2]):
                t = (side - start[axis]) / delta[axis]
                if 0 < t < 1:
                    breaks.add(t)

    def value(t):
        result = Q(0)
        for axis in range(2):
            p = start[axis] + t * delta[axis]
            gap = max(box[axis] - p, Q(0), p - box[axis + 2])
            result += gap * gap
        return result

    points = sorted(breaks)
    candidates = [value(t) for t in points]
    for lo, hi in zip(points, points[1:]):
        mid = (lo + hi) / 2
        numerator = denominator = Q(0)
        for axis in range(2):
            p = start[axis] + mid * delta[axis]
            side = box[axis] if p < box[axis] else box[axis + 2] if p > box[axis + 2] else None
            if side is not None:
                numerator -= (start[axis] - side) * delta[axis]
                denominator += delta[axis] ** 2
        if denominator:
            candidates.append(value(max(lo, min(hi, numerator / denominator))))
    return min(candidates)


def _full_grid_oracle(grid, res, origin, pose, seed):
    centre = (origin[0] + (Q(seed[1]) + Q(1, 2)) * res,
              origin[1] + (Q(seed[0]) + Q(1, 2)) * res)
    right, top = origin[0] + grid.shape[1] * res, origin[1] + grid.shape[0] * res

    def outside(p):
        gap = max(Q(0), min(p[0] - origin[0], p[1] - origin[1], right - p[0], top - p[1]))
        return gap ** 2

    p2, b2 = min(REQUIRED_M ** 2, outside(pose)), min(REQUIRED_M ** 2, outside(pose), outside(centre))
    for row in range(grid.shape[0]):
        for col in range(grid.shape[1]):
            if grid[row, col] != 0:
                box = (origin[0] + col * res, origin[1] + row * res,
                       origin[0] + (col + 1) * res, origin[1] + (row + 1) * res)
                p2 = min(p2, _piecewise_distance_squared(pose, pose, box))
                b2 = min(b2, _piecewise_distance_squared(pose, centre, box))
    return p2, b2


def test_original_scalar_bound_0282843_false_negative_can_pass_exact_geometry():
    grid = np.zeros((41, 41), dtype=np.int8)
    grid[23, 26] = 100
    seed, res, origin = (20, 20), .05, (-1.025, -1.025)
    traversable, clearance = native_traversable(grid, res)
    pose = (0., -(clearance[seed] - math.sqrt(.08)))
    _, _, old = _seed_diagnostics(grid, traversable, clearance,
        {"fresh": True, "x": pose[0], "y": pose[1]}, res, origin)
    assert old["seed_rejection_reason"] == "seed_pose_body_clearance"
    assert old["seed_pose_clearance_lower_bound_m"] == pytest.approx(.282842712474619)
    result = certify_seed_pose_bridge(grid, res, origin, pose, seed,
                                     seed_cell_traversable=traversable[seed])
    assert result["accepted"] and result["seed_cell"] == list(seed)
    assert Q(result["point_distance_squared_capped_exact"]) == REQUIRED_M ** 2
    assert Q(result["bridge_distance_squared_capped_exact"]) == REQUIRED_M ** 2


@pytest.mark.parametrize("blocked", [-1, 1, 50, 100])
def test_unknown_and_every_nonzero_value_block_point_clearance(blocked):
    grid = np.zeros((7, 7), dtype=np.int16)
    grid[3, 4] = blocked
    traversable, _ = native_traversable(grid, 1.)
    assert traversable[3, 3]
    result = certify_seed_pose_bridge(grid, 1, (-Q(7, 2), -Q(7, 2)), (Q(1, 4), 0),
                                     (3, 3), seed_cell_traversable=True)
    assert result["reason"] == "seed_pose_body_clearance"
    assert Q(result["point_distance_squared_capped_exact"]) == Q(1, 16)


def test_original_cell_gate_is_not_replaced_even_when_exact_pose_and_bridge_would_pass():
    grid = np.zeros((3, 3), dtype=np.int8)
    traversable, _ = native_traversable(grid, .2)
    assert not traversable[1, 1]
    result = certify_seed_pose_bridge(grid, Q(1, 5), (0, 0), (Q(3, 10), Q(3, 10)), (1, 1),
                                     seed_cell_traversable=traversable[1, 1])
    assert not result["accepted"] and result["reason"] == "seed_cell_body_clearance"
    assert result["checked_cells"] == 0


def test_bridge_interior_can_fail_when_point_and_seed_centre_both_pass():
    grid = np.zeros((5, 5), dtype=np.int8)
    grid[1, 3] = 100
    traversable, _ = native_traversable(grid, .43)
    assert traversable[2, 2]
    result = certify_seed_pose_bridge(grid, Q(43, 100), (-Q(43, 40), -Q(43, 40)),
        (Q(43, 250), Q(43, 500)), (2, 2), seed_cell_traversable=True)
    assert result["reason"] == "seed_bridge_body_clearance"
    assert Q(result["point_distance_squared_capped_exact"]) == REQUIRED_M ** 2
    assert Q(result["bridge_distance_squared_capped_exact"]) == Q(16641, 200000)


def test_diagonal_corner_clearance_uses_closed_square_not_occupied_centre():
    grid = np.zeros((7, 7), dtype=np.int8)
    grid[4, 4] = 100
    result = certify_seed_pose_bridge(grid, 1, (-Q(7, 2), -Q(7, 2)), (Q(2, 5), Q(2, 5)),
                                     (3, 3), seed_cell_traversable=True)
    assert result["reason"] == "seed_pose_body_clearance"
    assert Q(result["point_distance_squared_capped_exact"]) == Q(1, 50)


@pytest.mark.parametrize("offset,accepted", [(Q(0), True), (Q(1, 10**12), False), (-Q(1, 10**12), True)])
def test_exact_threshold_equality_and_either_side_have_no_float_tolerance(offset, accepted):
    grid = np.zeros((7, 7), dtype=np.int8)
    grid[3, 4] = 100
    result = certify_seed_pose_bridge(grid, 1, (-Q(7, 2), -Q(7, 2)), (Q(21, 100) + offset, 0),
                                     (3, 3), seed_cell_traversable=True)
    assert result["accepted"] is accepted
    if not offset:
        assert Q(result["point_distance_squared_capped_exact"]) == REQUIRED_M ** 2


@pytest.mark.parametrize("x", [-Q(1, 100), Q(0), Q(1, 100)])
def test_outside_boundary_and_near_map_exterior_always_reject(x):
    result = certify_seed_pose_bridge(np.zeros((7, 7), dtype=np.int8), 1, (0, 0), (x, Q(1, 2)),
                                     (0, 0), seed_cell_traversable=True)
    assert not result["accepted"]


def test_no_new_seed_or_pose_snap_on_mismatched_original_seed():
    result = certify_seed_pose_bridge(np.zeros((7, 7), dtype=np.int8), 1, (0, 0),
                                     (Q(9, 2), Q(7, 2)), (3, 3), seed_cell_traversable=True)
    assert result["reason"] == "pose_not_in_original_seed_cell"
    assert result["seed_cell"] == [3, 3]


@pytest.mark.parametrize("sample", range(8))
def test_local_capped_distances_equal_independent_full_grid_oracle(sample):
    rng = random.Random(1201 + sample)
    grid = np.zeros((11, 13), dtype=np.int16)
    for row in range(11):
        for col in range(13):
            if (row - 5) ** 2 + (col - 6) ** 2 >= 5 and rng.random() < .2:
                grid[row, col] = rng.choice((-1, 50, 100))
    seed, res, origin = (5, 6), Q(1, 5), (-Q(13, 10), -Q(11, 10))
    pose = (Q(rng.randint(-99, 99), 1000), Q(rng.randint(-99, 99), 1000))
    traversable, _ = native_traversable(grid, float(res))
    assert traversable[seed]
    expected = _full_grid_oracle(grid, res, origin, pose, seed)
    actual = certify_seed_pose_bridge(grid, res, origin, pose, seed, seed_cell_traversable=True)
    assert (Q(actual["point_distance_squared_capped_exact"]),
            Q(actual["bridge_distance_squared_capped_exact"])) == expected
    assert actual["accepted"] is all(distance >= REQUIRED_M ** 2 for distance in expected)


def test_local_window_excludes_far_cells_without_scanning_geometry_for_entire_map():
    grid = np.zeros((61, 61), dtype=np.int8)
    grid[0, 0] = 100
    before = grid.copy()
    result = certify_seed_pose_bridge(grid, Q(1, 20), (-Q(61, 40), -Q(61, 40)),
                                     (Q(1, 50), Q(1, 100)), (30, 30), seed_cell_traversable=True)
    assert result["accepted"] and result["checked_cells"] < 225 < grid.size
    assert result["checked_nonfree_cells"] == 0
    np.testing.assert_array_equal(grid, before)


def test_closed_local_window_keeps_both_sides_when_expansion_lands_on_gridlines():
    result = certify_seed_pose_bridge(np.zeros((7, 7), dtype=np.int8), Q(29, 50),
        (-Q(203, 100), -Q(203, 100)), (0, 0), (3, 3), seed_cell_traversable=True)
    assert result["accepted"] and result["candidate_bounds"] == [2, 4, 2, 4]


def test_numpy_geometry_is_canonicalized_without_mutating_noncontiguous_grid_or_inputs():
    grid = np.zeros((17, 19), dtype=np.int8)[:, ::-1]
    origin = np.array([-4., -4.], dtype=np.float64)
    pose = np.array([.25, .25], dtype=np.float32)
    seed = np.array([8, 8], dtype=np.int64)
    original = (grid.copy(), origin.copy(), pose.copy(), seed.copy())
    result = certify_seed_pose_bridge(grid, np.float32(.5), origin, pose, seed,
                                     seed_cell_traversable=np.bool_(True))
    assert result["accepted"]
    assert Q(result["resolution_exact"]) == Q.from_float(float(np.float32(.5)))
    for old, new in zip(original, (grid, origin, pose, seed)):
        np.testing.assert_array_equal(old, new)


@pytest.mark.parametrize("changes", [dict(resolution=True), dict(resolution=np.bool_(True)),
    dict(resolution=0), dict(resolution=-1), dict(resolution=float("inf")),
    dict(origin=(0, float("nan"))), dict(estimated_xy=(True, 0)),
    dict(estimated_xy=(np.bool_(False), 0)), dict(seed_cell=(True, 1)),
    dict(seed_cell=(1., 1)), dict(seed_cell_traversable=1), dict(grid=np.zeros((3, 3), dtype=bool)),
    dict(grid=np.zeros((3, 3), dtype=float)), dict(grid=np.zeros((0, 3), dtype=np.int8))])
def test_invalid_numeric_shapes_and_boolean_numbers_reject_without_mutation(changes):
    config = dict(grid=np.zeros((3, 3), dtype=np.int8), resolution=1, origin=(0, 0),
                  estimated_xy=(Q(3, 2), Q(3, 2)), seed_cell=(1, 1), seed_cell_traversable=True)
    config.update(changes)
    before = config["grid"].copy()
    with pytest.raises(ValueError):
        certify_seed_pose_bridge(**config)
    np.testing.assert_array_equal(before, config["grid"])


def test_wider_numpy_float_is_not_silently_rounded_to_binary64():
    kwargs = dict(grid=np.zeros((7, 7), dtype=np.int8), resolution=np.longdouble(1),
        origin=(0, 0), estimated_xy=(Q(7, 2), Q(7, 2)), seed_cell=(3, 3), seed_cell_traversable=True)
    if np.dtype(np.longdouble).itemsize > 8:
        with pytest.raises(ValueError, match="wider than binary64"):
            certify_seed_pose_bridge(**kwargs)
    else:
        assert certify_seed_pose_bridge(**kwargs)["accepted"]
