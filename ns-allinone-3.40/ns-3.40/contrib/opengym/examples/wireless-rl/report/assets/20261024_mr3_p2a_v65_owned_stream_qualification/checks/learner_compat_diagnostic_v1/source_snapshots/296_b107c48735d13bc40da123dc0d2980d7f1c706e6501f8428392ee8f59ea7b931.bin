"""Artificial missing/empty fused-map v2 fallback, without World or Node."""

from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import mr3_observation as observation


@pytest.mark.parametrize("grid", [None, np.empty((0, 0), dtype=np.int8)])
def test_fresh_state_with_missing_or_empty_fused_map_keeps_valid_snapshot(grid):
    states = [{"name": name, "x": x, "y": 0., "yaw": 0., "v": 0., "w": 0.,
               "valid": True, "source_stamp": 10., "received_stamp": 10.,
               "navigation": {"phase": "idle", "goal_id": None, "goal_x": None,
                              "goal_y": None, "commitment_until": 0.}}
              for name, x in zip(observation.ROBOT_NAMES, (-2., 0., 2.))]
    args = (grid, .05, (-4., -3.), states, 10., "epoch", 1, 1)
    legacy = observation.build_snapshot(*args)
    with patch.object(observation, "canonical_seed_cell",
                      side_effect=AssertionError("empty map reached strict geometry helper")):
        result = observation.build_snapshot(*args, seed_rule="exact-point-bridge-v2")
    assert result["joint_action_mask"][888]
    assert all(not any(mask[:8]) for mask in result["per_robot_action_mask"])
    assert not any(candidate["valid"] for candidate in result["candidates"])
    assert result["map"]["missing"]
    for name in observation.ROBOT_NAMES:
        old, new = legacy["path_maps"][name], result["path_maps"][name]
        assert new["seed_cell"] is None
        assert new["seed_rejection_reason"] == old["seed_rejection_reason"] == "pose_outside_received_map"
        assert new["seed_point_bridge_certificate"] is None
        assert new["seed_rule"] == "exact-point-bridge-v2"
    assert result["candidate_rule"]["version"] == "mr3-per-robot-geometric-staging-v6-exact-seed-v2"
