"""Artificial V39 production checks against an immutable, pre-change kernel.

The old public functions and globals are loaded from the exact a44 Git blob;
the current production module is never used as the expected kernel. The
existing independent piecewise-quadratic oracle additionally checks geometry.
"""

from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import mr3_seed_certificate as production


ROOT = Path(__file__).resolve().parents[5]
ASSETS = ROOT / ("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
    "report/assets/20261022_mr3_p2a_v39_certificate_kernel")
FROZEN_SHA256 = "99bd4fdda76a5974d394a2e40177e7cbd5fb12308258c2ee096c5232c568e3cb"
FROZEN_PATH = ASSETS / "frozen_reference_v1.py"
assert hashlib.sha256(FROZEN_PATH.read_bytes()).hexdigest() == FROZEN_SHA256


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = _load("multi_robot_exploration._v39_frozen_seed_certificate_a44", FROZEN_PATH)
cases = _load("v39_certificate_cases", ASSETS / "certificate_cases_v1.py")
oracle = _load("v39_independent_quadratic_oracle",
    Path(__file__).with_name("test_mr3_seed_certificate.py"))
SEGMENTS = cases.segment_cases()
SEEDS = cases.seed_cases()


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _compare(name, *args, **kwargs):
    expected = getattr(reference, name)(*args, **kwargs)
    actual = getattr(production, name)(*args, **kwargs)
    assert actual == expected
    assert _json_bytes(actual) == _json_bytes(expected)
    return actual


def test_true_frozen_baseline_and_canonical_production_kernel_are_independent():
    expected_path = Path(__file__).resolve().parents[1] / "multi_robot_exploration/mr3_seed_certificate.py"
    assert Path(production.__file__).resolve() == expected_path
    assert Path(reference.__file__).resolve() == FROZEN_PATH
    assert len(FROZEN_PATH.read_bytes()) == 11508
    assert production.REQUIRED_M == reference.REQUIRED_M == Q(29, 100)
    assert production.REQUIRED_SQUARED == reference.REQUIRED_SQUARED == Q(29, 100) ** 2
    for name in ("_segment_measurements", "certify_estimated_segment", "certify_seed_pose_bridge"):
        assert getattr(reference, name) is not getattr(production, name)
        assert getattr(reference, name).__globals__ is reference.__dict__
        assert getattr(production, name).__globals__ is production.__dict__
    assert reference._segment_measurements.__code__.co_code != production._segment_measurements.__code__.co_code


def test_both_production_public_certificates_execute_actual_production_kernel():
    grid = np.zeros((7, 7), np.int8)
    kernel = production._segment_measurements
    with patch.object(production, "_segment_measurements", wraps=kernel) as spy:
        _compare("certify_estimated_segment", grid, 1, (-Q(7, 2), -Q(7, 2)), (0, 0), (0, 0))
        spy.assert_called_once()
        spy.reset_mock()
        _compare("certify_seed_pose_bridge", grid, 1, (-Q(7, 2), -Q(7, 2)),
            (0, 0), (3, 3), seed_cell_traversable=True)
        spy.assert_called_once()


@pytest.mark.parametrize("name,args", SEGMENTS, ids=[item[0] for item in SEGMENTS])
def test_complete_segment_dict_and_json_equal_frozen_baseline(name, args):
    before = args[0].copy()
    actual = _compare("certify_estimated_segment", *args)
    np.testing.assert_array_equal(args[0], before)
    if name.startswith("threshold-"):
        assert actual["accepted"] is (name != "threshold-1")


@pytest.mark.parametrize("name,args,gate", SEEDS, ids=[item[0] for item in SEEDS])
def test_complete_seed_bridge_dict_and_json_equal_frozen_baseline(name, args, gate):
    before = args[0].copy()
    actual = _compare("certify_seed_pose_bridge", *args, seed_cell_traversable=gate)
    np.testing.assert_array_equal(args[0], before)
    if name.startswith("threshold-"):
        assert actual["accepted"] is (name != "threshold-1")
    if name == "unsafe-bridge-interior":
        assert actual["reason"] == "seed_bridge_body_clearance"
        assert Q(actual["bridge_distance_squared_capped_exact"]) == Q(16641, 200000)


@pytest.mark.parametrize("sample", range(8))
def test_production_and_frozen_match_independent_full_grid_quadratic_oracle(sample):
    grid, res, origin, start, end = cases.random_case(sample, seed=3880, density=.15)
    right, top = origin[0] + grid.shape[1] * res, origin[1] + grid.shape[0] * res

    def outside(point):
        return max(Q(0), min(point[0] - origin[0], point[1] - origin[1],
            right - point[0], top - point[1])) ** 2

    point2 = min(Q(29, 100) ** 2, outside(start))
    segment2 = min(point2, outside(end))
    for row in range(grid.shape[0]):
        for col in range(grid.shape[1]):
            if grid[row, col] != 0:
                box = (origin[0] + col * res, origin[1] + row * res,
                    origin[0] + (col + 1) * res, origin[1] + (row + 1) * res)
                point2 = min(point2, oracle._piecewise_distance_squared(start, start, box))
                segment2 = min(segment2, oracle._piecewise_distance_squared(start, end, box))
    actual = _compare("certify_estimated_segment", grid, res, origin, start, end)
    assert (Q(actual["point_distance_squared_capped_exact"]),
        Q(actual["segment_distance_squared_capped_exact"])) == (point2, segment2)
    cell = reference.canonical_seed_cell(start, res, origin, grid.shape)
    centre = reference.canonical_cell_centre(cell, res, origin)
    bridge_oracle = oracle._full_grid_oracle(grid, res, origin, start, cell)
    for module in (reference, production):
        assert module._segment_measurements(grid, res, origin, start, centre)[:2] == bridge_oracle


@pytest.mark.parametrize("zero_length", [True, False])
def test_zero_length_and_exact_aabb_equality_skip_projection_with_identical_counts(zero_length):
    grid = np.zeros((5, 5), np.int8)
    grid[2, 3] = 100
    start = (Q(21, 100), Q(0) if zero_length else -Q(1, 10))
    end = start if zero_length else (Q(21, 100), Q(1, 10))
    args = grid, Q(1), (-Q(5, 2), -Q(5, 2)), start, end
    expected = reference._segment_measurements(*args)
    with patch.object(production, "_segment_rectangle_squared", side_effect=AssertionError("unneeded projection")):
        actual = production._segment_measurements(*args)
    assert actual == expected
    assert actual[0] == actual[1] == Q(29, 100) ** 2
    assert actual[2]["checked_nonfree_cells"] == 1


def test_zero_minimum_still_visits_every_selected_nonfree_cell_and_preserves_counts():
    grid = np.full((7, 7), 100, np.int8)
    args = grid, Q(1, 10), (-Q(7, 20), -Q(7, 20)), (Q(0), Q(0)), (Q(1, 10), Q(0))
    expected = reference._segment_measurements(*args)
    actual = production._segment_measurements(*args)
    assert actual == expected
    assert actual[0] == actual[1] == 0
    assert actual[2]["checked_nonfree_cells"] == actual[2]["checked_cells"] > 1


def test_point_updates_and_lower_than_current_bound_still_use_full_exact_segment():
    grid = np.zeros((5, 5), np.int8)
    grid[2, 3] = 100
    args = grid, 1, (-Q(5, 2), -Q(5, 2)), (Q(3, 10), Q(0)), (Q(1, 10), Q(0))
    with patch.object(production, "_segment_rectangle_squared", wraps=production._segment_rectangle_squared) as spy:
        actual = _compare("certify_estimated_segment", *args)
    spy.assert_called_once()
    assert Q(actual["point_distance_squared_capped_exact"]) == Q(1, 25)
    assert Q(actual["segment_distance_squared_capped_exact"]) == Q(1, 25)


def test_numpy_binary_geometry_noncontiguous_grid_and_inputs_preserve_exact_output():
    grid = np.zeros((17, 19), np.int8)[:, ::-1]
    grid[9, 11] = -1
    res = np.float32(.1)
    origin = np.array([-.85, -.85], dtype=np.float64)
    point = np.array([0., 0.], dtype=np.float32)
    end = np.array([.01, .02], dtype=np.float64)
    before = (grid.copy(), origin.copy(), point.copy(), end.copy())
    _compare("certify_estimated_segment", grid, res, origin, point, end)
    cell = np.array(reference.canonical_seed_cell(point, res, origin, grid.shape), dtype=np.int64)
    _compare("certify_seed_pose_bridge", grid, res, origin, point, cell,
        seed_cell_traversable=np.bool_(True))
    for old, current in zip(before, (grid, origin, point, end)):
        np.testing.assert_array_equal(old, current)
