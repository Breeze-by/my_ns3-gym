"""Artificial virtual-start cost, provenance and unchanged-profile checks."""
import copy
import heapq
import math

import numpy as np
import pytest

from multi_robot_exploration import mr3_observation as obs
from test_mr3_observation import frontier_map, own_maps, robots, snapshot

NEW = "point-attachment-3x3-v1"
SEED = "exact-point-bridge-v2"


def oracle(trav, anchors, resolution):
    # Independent heap graph: a virtual source has the complete weighted
    # attachment edge set; original nodes keep eight-neighbour no-corner edges.
    result = np.full(trav.shape, np.inf)
    queue = []
    for anchor in anchors:
        row, col = anchor["cell"]
        cost = anchor["bridge_length_m"]
        if cost < result[row, col]:
            result[row, col] = cost
            heapq.heappush(queue, (cost, row, col))
    while queue:
        cost, row, col = heapq.heappop(queue)
        if cost != result[row, col]:
            continue
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = row + dr, col + dc
                if not (dr or dc) or not (0 <= rr < trav.shape[0] and 0 <= cc < trav.shape[1]):
                    continue
                if not trav[rr, cc] or (dr and dc and not (trav[row, cc] and trav[rr, col])):
                    continue
                new = cost + resolution * math.hypot(dr, dc)
                if new < result[rr, cc]:
                    result[rr, cc] = new
                    heapq.heappush(queue, (new, rr, cc))
    return result


def test_all_weighted_anchors_match_independent_augmented_graph_without_cross_robot_edges():
    trav = np.ones((5, 8), bool)
    trav[:, 3] = False
    groups = [
        {"accepted": True, "anchors": [{"cell": [2, 1], "bridge_length_m": .02},
                                        {"cell": [2, 5], "bridge_length_m": .12}]},
        {"accepted": True, "anchors": [{"cell": [3, 1], "bridge_length_m": .07}]},
        {"accepted": False, "anchors": []},
    ]
    paths, ids = obs._point_graph_distances(trav, groups, .05)
    for index, group in enumerate(groups):
        np.testing.assert_allclose(paths[index], oracle(trav, group["anchors"], .05)[trav], atol=1e-14)
    # The bridge nearest the pose cannot reach this target. All anchors must
    # survive; another robot cannot borrow the first robot's right component.
    assert paths[0, ids[2, 6]] == pytest.approx(.17)
    assert np.isinf(paths[1, ids[2, 6]])
    assert np.all(np.isinf(paths[2]))


def test_bridge_cost_is_attached_to_its_own_anchor_before_minimum():
    trav = np.ones((3, 7), bool)
    group = {"accepted": True, "anchors": [{"cell": [1, 1], "bridge_length_m": .01},
                                           {"cell": [1, 5], "bridge_length_m": .19}]}
    paths, ids = obs._point_graph_distances(trav, [group], .05)
    # min(graph distances) + min(bridge lengths) would return .01 incorrectly.
    assert paths[0, ids[1, 5]] == pytest.approx(.19)
    assert paths[0, ids[1, 1]] == pytest.approx(.01)


@pytest.mark.parametrize("seed", obs.SEED_RULES)
def test_explicit_original_start_preserves_complete_default_bytes(seed):
    a = snapshot(seed_rule=seed)
    b = snapshot(seed_rule=seed, start_graph_rule="original-seed-cell")
    assert a == b
    assert "start_graph_rule" not in a["candidate_rule"]
    assert "robot_start_graph_attached" not in a["diagnostics"]
    assert all("point_graph_attachment" not in value for value in a["path_maps"].values())


@pytest.mark.parametrize("seed,start", [("legacy", NEW), ("exact-point-bridge-v1", NEW),
    (SEED, True), (SEED, None), (SEED, "nearest-safe-cell"), (False, "original-seed-cell")])
def test_bad_mode_pairs_reject_before_build(seed, start):
    with pytest.raises(ValueError):
        snapshot(seed_rule=seed, start_graph_rule=start)


def test_rejected_original_cell_remains_false_when_actual_point_attaches():
    grid = np.zeros((60, 60), np.int8)
    grid[20, 20] = 100
    states = robots()
    states[0].update(x=.349, y=.149)
    rawstates = [obs._robot_state(state, 10.) for state in states]
    maps = {"tb1": {"grid": grid, "resolution": .05, "origin": (-1., -1.),
            "epoch": "episode-a", "sequence": 1, "version": 1,
            "source_stamp": 10., "received_stamp": 10.}}
    target = np.array([[40, 40]])
    before = copy.deepcopy(maps)
    old, oldmeta, oldvalid = obs._own_map_paths(maps, copy.deepcopy(rawstates), 10., "episode-a",
        .05, (-1., -1.), target, seed_rule=SEED)
    new, metadata, valid = obs._own_map_paths(maps, rawstates, 10., "episode-a", .05, (-1., -1.),
        target, seed_rule=SEED, start_graph_rule=NEW)
    entry = metadata["tb1"]
    assert not oldvalid[0] and not valid[0] and np.isinf(old[0, 0])
    assert entry["seed_rejection_reason"] == "seed_cell_body_clearance"
    assert entry["point_graph_attachment"]["accepted"] and np.isfinite(new[0, 0])
    assert not entry["missing"] and entry["unavailable_reason"] is None
    assert entry["point_graph_attachment"]["canonical_cell_original_traversable"] is False
    np.testing.assert_array_equal(maps["tb1"]["grid"], before["tb1"]["grid"])
    assert metadata["tb2"]["missing"] and metadata["tb2"]["point_graph_attachment"] is None


@pytest.mark.parametrize("change,reason", [("epoch", "cross_epoch"), ("future", "future_map"),
    ("stale", "state_missing_or_stale"), ("missing", "missing_received_own_map")])
def test_upstream_gates_do_not_invoke_attachment(monkeypatch, change, reason):
    from multi_robot_exploration import mr3_point_graph
    maps, states = own_maps(), robots()
    if change == "epoch": maps["tb1"]["epoch"] = "other"
    elif change == "future": maps["tb1"]["source_stamp"] = 11.
    elif change == "stale": states[0]["source_stamp"] = 0.
    else: del maps["tb1"]
    real = mr3_point_graph.point_graph_attachments
    called = []
    def capture(grid, res, origin, xy):
        called.append(tuple(xy))
        return real(grid, res, origin, xy)
    monkeypatch.setattr(mr3_point_graph, "point_graph_attachments", capture)
    result = snapshot(states=states, robot_maps=maps, seed_rule=SEED, start_graph_rule=NEW)
    entry = result["path_maps"]["tb1"]
    assert entry["start_graph_rejection_reason"] == reason
    assert entry["point_graph_attachment"] is None
    assert tuple((states[0]["x"], states[0]["y"])) not in called
    assert not result["diagnostics"]["robot_start_graph_attached"][0]


@pytest.mark.parametrize("mode", ["fused", "own", "navigation"])
def test_new_snapshot_binds_rule_all_attachments_and_preserves_pose(mode):
    kwargs = {}
    if mode != "fused":
        kwargs["robot_maps"] = own_maps()
    if mode == "navigation":
        maps = own_maps()
        for value in maps.values(): value["composition_version"] = obs.NAVIGATION_COMPOSITION_VERSION
        kwargs["navigation_maps"] = maps
    result = snapshot(seed_rule=SEED, start_graph_rule=NEW, **kwargs)
    assert result["candidate_rule"]["version"] == obs.candidate_version_for_rules(SEED, NEW, navigation=mode == "navigation")
    assert result["candidate_rule"]["start_graph_cost"] == obs.POINT_GRAPH_COST
    assert result["candidate_rule"]["start_graph_profile"] == obs.POINT_GRAPH_PROFILE
    assert result["diagnostics"]["robot_start_graph_attached"] == [True] * 3
    assert [state["x"] for state in result["robots"]] == [-2., 0., 2.]
    assert result["digest"] == obs.snapshot_digest(result)
    changed = copy.deepcopy(result)
    changed["path_maps"]["tb1"]["point_graph_attachment"]["anchors"][0]["bridge_length_m"] += .001
    assert obs.snapshot_digest(changed) != result["digest"]


@pytest.mark.parametrize("grid", [None, np.empty((0, 0), np.int8)])
def test_empty_fused_map_keeps_no_goal_and_missing_truth(grid):
    result = obs.build_snapshot(grid, .05, (0., 0.), robots(), 10., "epoch", 0, 0,
        seed_rule=SEED, start_graph_rule=NEW)
    assert result["map"]["missing"]
    assert result["diagnostics"]["robot_start_graph_attached"] == [False] * 3
    assert result["joint_action_mask"][888]
    assert not any(candidate["valid"] for candidate in result["candidates"])
