"""v2 rational robot-cell ownership on artificial received grids only."""

from fractions import Fraction as Q
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import mr3_observation as observation
from multi_robot_exploration.mr3_seed_certificate import (
    canonical_cell_centre, canonical_seed_cell, certify_seed_pose_bridge,
)


V2 = "exact-point-bridge-v2"


def test_binary64_division_rounding_cannot_assign_the_adjacent_cell():
    point, resolution = .45, .05
    quotient = Q.from_float(point) / Q.from_float(resolution)
    assert quotient < 9 and point / resolution == 9.
    assert canonical_seed_cell((point, point), resolution, (0, 0), (32, 32)) == (8, 8)
    assert observation._cell(point, point, resolution, (0, 0), (32, 32)) == (9, 9)
    # Decimal-rational geometry is a different, explicitly represented input.
    assert canonical_seed_cell((Q(9, 20), Q(9, 20)), Q(1, 20), (0, 0), (32, 32)) == (9, 9)
    centre = canonical_cell_centre((8, 8), resolution, (0, 0))
    assert centre == (Q(17, 2) * Q.from_float(resolution),) * 2


@pytest.mark.parametrize("point,resolution,origin,shape,expected", [
    ((0, 0), 1, (0, 0), (3, 4), (0, 0)),
    ((4, 1), 1, (0, 0), (3, 4), None),
    ((-Q(1, 1000), 1), 1, (0, 0), (3, 4), None),
    ((-Q(1, 2), Q(1, 2)), 1, (-1, -1), (3, 4), (1, 0)),
    ((-Q(3, 2), -Q(1, 2)), Q(1, 2), (-2, -2), (6, 6), (3, 1)),
    ((np.float32(.45), np.float64(.45)), np.float64(.05), (0, 0),
     (np.int32(32), np.int64(32)), (8, 8)),
])
def test_exact_floor_signed_origin_gridline_and_numpy_inputs(point, resolution, origin, shape, expected):
    assert canonical_seed_cell(point, resolution, origin, shape) == expected


@pytest.mark.parametrize("point,resolution,origin,shape", [
    ((True, 0), 1, (0, 0), (3, 4)),
    ((0, 0), np.bool_(True), (0, 0), (3, 4)),
    ((0, 0), 1, (False, 0), (3, 4)),
    ((0, 0), 1, (0, 0), (True, 4)),
    ((0, 0), 1, (0, 0), (0, 4)),
    ((0, 0), 0, (0, 0), (3, 4)),
    ((np.nan, 0), 1, (0, 0), (3, 4)),
    ((0, 0), 1, (np.inf, 0), (3, 4)),
    ((0, 0, 0), 1, (0, 0), (3, 4)),
    ((0, 0), 1, (0, 0), (3., 4)),
])
def test_canonical_cell_rejects_invalid_geometry_without_boolean_numbers(point, resolution, origin, shape):
    with pytest.raises(ValueError):
        canonical_seed_cell(point, resolution, origin, shape)


def test_observation_uses_the_one_canonical_cell_and_keeps_v1_float_ownership():
    grid = np.zeros((32, 32), dtype=np.int8)
    traversable, clearance = observation.native_traversable(grid, .05)
    robot = {"fresh": True, "x": .45, "y": .45}
    before = grid.copy()
    v1 = observation._seed_diagnostics(grid, traversable, clearance, robot, .05, (0, 0),
                                       seed_rule="exact-point-bridge-v1")
    v2 = observation._seed_diagnostics(grid, traversable, clearance, robot, .05, (0, 0),
                                       seed_rule=V2)
    assert v1[0] == (9, 9) and v2[0] == (8, 8)
    assert v2[2]["seed_rejection_reason"] is None
    assert v1[2]["seed_rule"] == "exact-point-bridge-v1" and v2[2]["seed_rule"] == V2
    np.testing.assert_array_equal(grid, before)
    assert robot == {"fresh": True, "x": .45, "y": .45}


@pytest.mark.parametrize("failure,reason", [
    ("unknown", "seed_cell_unknown"), ("occupied", "seed_cell_occupied"),
    ("cell", "seed_cell_body_clearance"), ("stale", "state_missing_or_stale"),
])
def test_new_cell_is_strictly_regated_without_reusing_the_old_cell_gate(failure, reason):
    grid = np.zeros((32, 32), dtype=np.int8)
    traversable, clearance = np.ones(grid.shape, bool), np.full(grid.shape, 1.)
    robot = {"fresh": failure != "stale", "x": .45, "y": .45}
    if failure in ("unknown", "occupied"):
        grid[8, 8] = -1 if failure == "unknown" else 100
    if failure == "cell":
        traversable[8, 8] = False
    assert grid[9, 9] == 0 and traversable[9, 9]
    with patch.object(observation, "certify_seed_pose_bridge", side_effect=AssertionError("gate bypass")):
        _, _, diagnostic = observation._seed_diagnostics(
            grid, traversable, clearance, robot, .05, (0, 0), seed_rule=V2)
    assert diagnostic["seed_rejection_reason"] == reason
    assert diagnostic["seed_point_bridge_certificate"] is None


def test_v2_fixes_containment_without_changing_the_v1_certificate_contract():
    grid = np.zeros((40, 40), dtype=np.int8)
    args = (grid, .05, (0, 0), (.45, .45))
    old = certify_seed_pose_bridge(*args, (9, 9), seed_cell_traversable=True)
    new = certify_seed_pose_bridge(*args, canonical_seed_cell((.45, .45), .05, (0, 0), grid.shape),
                                   seed_cell_traversable=True)
    assert old["reason"] == "pose_not_in_original_seed_cell"
    assert new["accepted"] and new["schema"] == old["schema"]
    assert set(new) == set(old)


@pytest.mark.parametrize("navigation", [False, True])
def test_v2_snapshot_has_explicit_version_without_extra_candidate_rule_fields(navigation):
    grid = np.zeros((60, 80), dtype=np.int8)
    grid[:4, :] = -1
    states = [{"name": name, "x": x, "y": 0., "yaw": 0., "v": 0., "w": 0.,
               "valid": True, "source_stamp": 10., "received_stamp": 10.,
               "navigation": {"phase": "idle", "goal_id": None, "goal_x": None,
                              "goal_y": None, "commitment_until": 0.}}
              for name, x in zip(observation.ROBOT_NAMES, (-2., 0., 2.))]
    entries = {name: {"grid": grid.copy(), "resolution": .1, "origin": (-4., -3.),
                      "epoch": "epoch", "sequence": 1, "version": 1,
                      "source_stamp": 10., "received_stamp": 10., "payload_sha256": name,
                      "composition_version": observation.NAVIGATION_COMPOSITION_VERSION}
               for name in observation.ROBOT_NAMES}
    kwargs = {"robot_maps": entries}
    if navigation:
        kwargs["navigation_maps"] = entries
    args = (grid, .1, (-4., -3.), states, 10., "epoch", 1, 1)
    v1 = observation.build_snapshot(*args, seed_rule="exact-point-bridge-v1", **kwargs)
    v2 = observation.build_snapshot(*args, seed_rule=V2, **kwargs)
    assert set(v1["candidate_rule"]) == set(v2["candidate_rule"])
    assert {k: v for k, v in v1["candidate_rule"].items() if k not in ("version", "seed_rule")} == {
        k: v for k, v in v2["candidate_rule"].items() if k not in ("version", "seed_rule")}
    assert v2["candidate_rule"]["version"] == (
        "mr3-navigation-geometric-staging-v7-exact-seed-v2" if navigation
        else "mr3-per-robot-geometric-staging-v6-exact-seed-v2")
    assert v2["candidate_rule"]["seed_rule"] == V2
    assert v2["candidate_version"] != v1["candidate_version"]
