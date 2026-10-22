"""Complete reference/candidate certificate equivalence on artificial data."""
from fractions import Fraction as Q
import importlib.util
import json
from pathlib import Path
import random
from unittest.mock import patch

import numpy as np
import pytest


spec = importlib.util.spec_from_file_location("v38_certificate_candidate", str(Path(__file__).with_name("certificate_candidate_v1.py")))
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
reference = candidate.reference
oracle_path = Path(reference.__file__).resolve().parent.parent / "test/test_mr3_seed_certificate.py"
oracle_spec = importlib.util.spec_from_file_location("v38_independent_quadratic_oracle", oracle_path)
oracle = importlib.util.module_from_spec(oracle_spec)
oracle_spec.loader.exec_module(oracle)


def compare_public(function, *args, **kwargs):
    expected = function(*args, **kwargs)
    with patch.object(reference, "_segment_measurements", candidate.fast_segment_measurements):
        actual = function(*args, **kwargs)
    assert actual == expected
    assert json.dumps(actual, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        expected, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return expected


@pytest.mark.parametrize("start,end", [
    ((0, 0), (0, 0)), ((0, 0), (Q(1, 10), Q(1, 10))),
    ((Q(1, 1000), -Q(1, 1000)), (Q(2, 1000), Q(3, 1000))),
    ((Q(1, 10**30), 0), (0, Q(1, 10**30))),
    ((-10, -10), (-9, -9)), ((-10, -10), (10, 10)),
    ((Q(7, 2), 0), (Q(7, 2), 0)), ((0, 0), (7, 0)),
])
def test_full_segment_certificate_dict_matches_on_degenerate_tiny_outside_and_crossing(start, end):
    grid = np.zeros((7, 7), np.int8)
    grid[1, 2], grid[3, 4], grid[5, 5] = -1, 100, 1
    before = grid.copy()
    compare_public(reference.certify_estimated_segment, grid, 1, (-Q(7, 2), -Q(7, 2)), start, end)
    np.testing.assert_array_equal(grid, before)


@pytest.mark.parametrize("delta", [Q(0), Q(1, 10**30), -Q(1, 10**30)])
def test_all_fields_equal_at_exact_threshold_and_tiny_rational_neighbors(delta):
    grid = np.zeros((7, 7), np.int8)
    grid[3, 4] = 100
    point = (Q(21, 100) + delta, Q(0))
    compare_public(reference.certify_estimated_segment, grid, 1, (-Q(7, 2), -Q(7, 2)), point, point)
    compare_public(reference.certify_seed_pose_bridge, grid, 1, (-Q(7, 2), -Q(7, 2)),
        point, (3, 3), seed_cell_traversable=True)


@pytest.mark.parametrize("gate", [True, False])
@pytest.mark.parametrize("value", [-1, 0, 1, 100])
def test_complete_seed_certificate_preserves_original_gates_and_all_metadata(gate, value):
    grid = np.zeros((7, 7), np.int8)
    grid[3, 3], grid[3, 4] = value, 100
    compare_public(reference.certify_seed_pose_bridge, grid, .5, (-1.75, -1.75),
        (-.2, 0.), (3, 3), seed_cell_traversable=gate)


def test_bridge_interior_minimum_remains_exact_even_with_safe_endpoints():
    grid = np.zeros((5, 5), np.int8)
    grid[1, 3] = 100
    result = compare_public(reference.certify_seed_pose_bridge, grid, Q(43, 100),
        (-Q(43, 40), -Q(43, 40)), (Q(43, 250), Q(43, 500)), (2, 2), seed_cell_traversable=True)
    assert result["reason"] == "seed_bridge_body_clearance"
    assert Q(result["bridge_distance_squared_capped_exact"]) == Q(16641, 200000)


@pytest.mark.parametrize("sample", range(16))
def test_fixed_random_full_certificate_byte_equivalence(sample):
    rng = random.Random(3800 + sample)
    grid = np.zeros((9, 11), np.int16)
    for r in range(grid.shape[0]):
        for c in range(grid.shape[1]):
            if rng.random() < .3:
                grid[r, c] = rng.choice((-1, 1, 25, 100))
    start = (Q(rng.randint(-400, 400), 1000), Q(rng.randint(-400, 400), 1000))
    end = start if sample % 3 == 0 else (Q(rng.randint(-500, 500), 1000), Q(rng.randint(-500, 500), 1000))
    args = (grid, Q(1, 5), (-Q(11, 10), -Q(9, 10)))
    compare_public(reference.certify_estimated_segment, *args, start, end)
    cell = reference.canonical_seed_cell(start, args[1], args[2], grid.shape)
    compare_public(reference.certify_seed_pose_bridge, *args, start, cell, seed_cell_traversable=True)


def test_aabb_equality_prunes_full_projection_but_still_counts_and_updates_point():
    grid = np.zeros((5, 5), np.int8)
    grid[2, 3] = 100
    # Cell left edge=.5 and point=.21: exact lower bound is exactly .29².
    start = end = (Q(21, 100), Q(0))
    args = (grid, Q(1), (-Q(5, 2), -Q(5, 2)), start, end)
    expected = reference._segment_measurements(*args)
    with patch.object(reference, "_segment_rectangle_squared", side_effect=AssertionError("unneeded corner projection")):
        actual = candidate.fast_segment_measurements(*args)
    assert actual == expected and actual[2]["checked_nonfree_cells"] == 1
    assert actual[0] == actual[1] == Q(29, 100) ** 2


def test_nonzero_segment_aabb_equality_skips_projection_without_changing_dict():
    grid = np.zeros((5, 5), np.int8)
    grid[2, 3] = 100
    start, end = (Q(21, 100), -Q(1, 10)), (Q(21, 100), Q(1, 10))
    args = (grid, Q(1), (-Q(5, 2), -Q(5, 2)), start, end)
    expected = reference._segment_measurements(*args)
    with patch.object(reference, "_segment_rectangle_squared", side_effect=AssertionError("equal lower bound")):
        actual = candidate.fast_segment_measurements(*args)
    assert actual == expected and actual[2]["checked_nonfree_cells"] == 1


def test_zero_minimum_keeps_later_nonfree_diagnostic_counts():
    grid = np.full((7, 7), 100, np.int8)
    args = (grid, Q(1, 10), (-Q(7, 20), -Q(7, 20)), (Q(0), Q(0)), (Q(1, 10), Q(0)))
    expected = reference._segment_measurements(*args)
    actual = candidate.fast_segment_measurements(*args)
    assert actual == expected and actual[0] == actual[1] == 0
    assert actual[2]["checked_nonfree_cells"] > 1


def test_point_update_cannot_be_lost_when_aabb_does_not_prune():
    grid = np.zeros((5, 5), np.int8)
    grid[2, 3] = 100
    start, end = (Q(3, 10), Q(0)), (Q(1, 10), Q(0))
    result = compare_public(reference.certify_estimated_segment, grid, 1, (-Q(5, 2), -Q(5, 2)), start, end)
    assert Q(result["point_distance_squared_capped_exact"]) == Q(1, 25)
    assert Q(result["segment_distance_squared_capped_exact"]) == Q(1, 25)


@pytest.mark.parametrize("sample", range(8))
def test_candidate_kernel_matches_existing_independent_full_grid_quadratic_oracle(sample):
    rng = random.Random(3880 + sample)
    grid = np.zeros((9, 11), np.int8)
    for r in range(grid.shape[0]):
        for c in range(grid.shape[1]):
            if rng.random() < .15:
                grid[r, c] = rng.choice((-1, 1, 100))
    res, origin = Q(1, 5), (-Q(11, 10), -Q(9, 10))
    point = (Q(rng.randint(-300, 300), 1000), Q(rng.randint(-300, 300), 1000))
    cell = reference.canonical_seed_cell(point, res, origin, grid.shape)
    centre = (origin[0] + (Q(cell[1]) + Q(1, 2)) * res,
              origin[1] + (Q(cell[0]) + Q(1, 2)) * res)
    expected = oracle._full_grid_oracle(grid, res, origin, point, cell)
    result = candidate.fast_segment_measurements(grid, res, origin, point, centre)
    assert result[:2] == expected
