"""Truth-free geometry, immutable replay and ownership-mask contract checks."""

import copy
import json
import math

import numpy as np
import pytest

from multi_robot_exploration import mr3_observation as observation


def robots(now=10.0, phase="idle"):
    return [{
        "name": name, "x": x, "y": 0.0, "yaw": 0.0,
        "v": 0.0, "w": 0.0, "valid": True,
        "source_stamp": now, "received_stamp": now,
        "navigation": {"phase": phase, "goal_id": None,
                       "goal_x": None, "goal_y": None, "commitment_until": 0.0},
    } for name, x in zip(observation.ROBOT_NAMES, (-2.0, 0.0, 2.0))]


def frontier_map():
    grid = np.full((100, 120), -1, dtype=np.int8)
    grid[10:90, 10:110] = 0
    return grid


def snapshot(grid=None, states=None, **kwargs):
    return observation.build_snapshot(
        frontier_map() if grid is None else grid, 0.1, (-6.0, -5.0),
        robots() if states is None else states, 10.0, "episode-a", 2, 4,
        **kwargs,
    )


def test_joint_action_encoding_is_bijective_and_rejects_non_actions():
    assert observation.encode_joint_action((8, 9, 0)) == 890
    assert {observation.encode_joint_action(observation.decode_joint_action(index))
            for index in range(1000)} == set(range(1000))
    for invalid in (-1, 1000, 1.1, True):
        with pytest.raises(ValueError):
            observation.decode_joint_action(invalid)
    with pytest.raises(ValueError):
        observation.encode_joint_action((0, 1))


def test_snapshot_is_json_serializable_deterministic_and_owns_its_input():
    grid, states = frontier_map(), robots()
    result = snapshot(grid, states)
    assert result == snapshot(grid.copy(), list(reversed(copy.deepcopy(states))))
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert result["digest"] == observation.snapshot_digest(result)
    before = copy.deepcopy(result)
    grid[:] = 100
    states[0]["navigation"]["phase"] = "unknown"
    assert result == before
    assert len(json.dumps(result)) < 50000


def test_eight_candidates_are_safe_inward_spatially_representative_and_reachable():
    grid = frontier_map()
    result = snapshot(grid)
    candidates = result["candidates"]
    traversable, _ = observation.native_traversable(grid, 0.1)
    assert len(candidates) == 8
    assert all(candidate["valid"] for candidate in candidates)
    assert len({(item["row"], item["column"]) for item in candidates}) == 8
    for candidate in candidates:
        assert traversable[candidate["row"], candidate["column"]]
        assert candidate["clearance_m"] >= 0.29
        assert all(candidate["reachable"])
        assert all(value is not None and value >= 0 for value in candidate["path_distances_m"])
    points = [(item["x"], item["y"]) for item in candidates]
    assert max(item[0] for item in points) - min(item[0] for item in points) > 8
    assert max(item[1] for item in points) - min(item[1] for item in points) > 6
    assert result["diagnostics"]["candidate_truncated"] > 0
    assert result["diagnostics"]["candidate_selection"].endswith("farthest point")


def test_no_frontier_yields_no_invented_goal_and_legal_wait():
    result = snapshot(np.zeros((100, 120), dtype=np.int8))
    assert not any(item["valid"] for item in result["candidates"])
    assert result["joint_action_mask"][999]
    assert result["joint_action_mask"][888]
    assert all(mask == [False] * 8 + [True, True] for mask in result["per_robot_action_mask"])


def test_unknown_space_and_narrow_gap_are_not_observed_paths():
    grid = np.zeros((50, 80), dtype=np.int8)
    grid[:, 30:42] = 100
    grid[22:27, 30:42] = 0  # .5 m opening cannot fit a .5 m body plus margin.
    traversable, _ = observation.native_traversable(grid, 0.1)
    paths, ids = observation._path_distances(traversable, [(25, 15), None, None], 0.1)
    assert not np.isfinite(paths[0, ids[25, 60]])
    grid[:, 30:42] = -1
    traversable, _ = observation.native_traversable(grid, 0.1)
    paths, ids = observation._path_distances(traversable, [(25, 15), None, None], 0.1)
    assert not np.isfinite(paths[0, ids[25, 60]])


def test_path_graph_does_not_cut_corners_and_uses_metric_distances():
    traversable = np.array([[True, False], [False, True]])
    distances, ids = observation._path_distances(traversable, [(0, 0), None, None], 0.05)
    assert np.isinf(distances[0, ids[1, 1]])
    distances, ids = observation._path_distances(np.ones((2, 2), bool), [(0, 0), None, None], 0.05)
    assert distances[0, ids[1, 1]] == pytest.approx(math.sqrt(2) * 0.05)


def test_thin_wall_is_preserved_by_coarse_raster_and_native_paths():
    grid = np.zeros((200, 240), dtype=np.int8)
    grid[:, 119] = 100  # One native .05 m column inside a .25 m CNN cell.
    result = observation.build_snapshot(
        grid, 0.05, (-6, -5), robots(), 10, "epoch", 1, 1,
    )
    coarse = observation.decode_raster(result["maps"]["global"])
    assert np.count_nonzero(coarse[0]) > 0
    traversable, _ = observation.native_traversable(grid, 0.05)
    distances, ids = observation._path_distances(traversable, [(100, 50), None, None], 0.05)
    assert np.isinf(distances[0, ids[100, 180]])


def test_metric_raster_shapes_axes_padding_and_overlap_semantics():
    result = snapshot()
    global_map = result["maps"]["global"]
    assert global_map["shape"] == [3, 128, 128]
    assert global_map["extent_m"] == [-16, -16, 16, 16]
    decoded = observation.decode_raster(global_map)
    assert decoded.dtype == np.uint8
    assert decoded[2, 0, 0] == 1 and decoded[1, 0, 0] == 0
    for local in result["maps"]["locals"]:
        assert local["shape"] == [3, 64, 64]
        assert local["extent_m"][2] - local["extent_m"][0] == pytest.approx(12.8)
        assert local["resolution_m"] == pytest.approx([0.2, 0.2])
        assert observation.decode_raster(local).shape == (3, 64, 64)


@pytest.mark.parametrize("phase", ["accepting", "canceling", "unknown", "failed"])
def test_unresolved_navigation_ownership_masks_new_goals_and_wait(phase):
    states = robots()
    states[0]["navigation"]["phase"] = phase
    result = snapshot(states=states)
    assert result["per_robot_action_mask"][0] == [False] * 8 + [True, False]
    assert result["joint_action_mask"][888]


def test_active_minimum_commitment_then_switch_and_wait():
    states = robots()
    states[0]["navigation"].update(phase="active", commitment_until=10.001)
    assert snapshot(states=states)["per_robot_action_mask"][0] == [False] * 8 + [True, False]
    states[0]["navigation"]["commitment_until"] = 10.0
    assert all(snapshot(states=states)["per_robot_action_mask"][0])


@pytest.mark.parametrize("until,locked", (
    (10.03, False), (5.03 + 5., False), (10.030000001, True), (10.029999999, False),
))
def test_commitment_mask_and_remaining_time_use_same_nanosecond_boundary(until, locked):
    states = robots(now=10.03)
    states[0]["navigation"].update(phase="active", commitment_until=until)
    result = observation.build_snapshot(
        frontier_map(), .1, (-6., -5.), states, 10.03, "episode-a", 2, 4,
    )
    assert result["per_robot_action_mask"][0][observation.WAIT] is not locked
    nav = result["robots"][0]["navigation"]
    assert nav["commitment_until"] == until
    assert nav["commitment_remaining_sec"] == (1e-9 if locked else 0.)


def test_missing_stale_or_future_state_masks_dispatch_without_breaking_keep():
    for key, value in (("valid", False), ("source_stamp", 9.49),
                       ("received_stamp", 9.49), ("source_stamp", 10.01), ("x", float("nan"))):
        states = robots()
        states[1][key] = value
        result = snapshot(states=states)
        assert not result["robots"][1]["fresh"]
        assert result["per_robot_action_mask"][1] == [False] * 8 + [True, False]
        assert result["joint_action_mask"][888]
        json.dumps(result, allow_nan=False)


def test_same_candidate_conflicts_and_existing_keep_conflicts_stay_legal():
    result = snapshot()
    assert not result["joint_action_mask"][0]  # All three request candidate zero.
    states = robots()
    for state in states:
        state["navigation"].update(phase="active", goal_x=1.0, goal_y=1.0)
    result = snapshot(states=states)
    assert result["joint_action_mask"][888]
    assert result["diagnostics"]["mask_reasons"]["joint_target_conflict_count"] > 0


def test_new_target_conflicts_with_retained_goal_or_stationary_idle_wait():
    initial = snapshot()
    candidate = initial["candidates"][0]
    states = robots()
    states[1]["navigation"].update(phase="active", goal_x=candidate["x"], goal_y=candidate["y"])
    result = snapshot(states=states)
    assert not result["joint_action_mask"][88]  # tb1 -> candidate 0, tb2/tb3 KEEP.
    assert not result["joint_action_mask"][98]  # Pending WAIT still owns old tb2 goal.
    states[1]["navigation"]["phase"] = "idle"
    states[1]["x"], states[1]["y"] = candidate["x"], candidate["y"]
    result = snapshot(states=states)
    # Moving a robot can alter geometric reachability metadata, but not this pool.
    assert result["candidates"][0]["x"] == candidate["x"]
    assert not result["joint_action_mask"][98]


def test_path_reachability_is_per_robot_without_changing_goal_ranking():
    grid = frontier_map()
    grid[:, 59:61] = 100
    states = robots()
    states[1]["x"] = -1.0
    result = snapshot(grid=grid, states=states)
    assert any(item["reachable"][0] and not item["reachable"][2]
               for item in result["candidates"] if item["valid"])
    assert any(item["reachable"][2] and not item["reachable"][0]
               for item in result["candidates"] if item["valid"])
    for candidate in result["candidates"]:
        for index in range(3):
            assert (result["per_robot_action_mask"][index][candidate["index"]]
                    == candidate["reachable"][index])


def test_versions_source_ages_deadline_and_digest_preserve_replay_meaning():
    result = snapshot(map_source_stamp=9.0, map_received_stamp=9.8, task_start=3.0,
                      map_sources={"tb1": {"sequence": 12}})
    assert result["map"]["source_age_sec"] == 1.0
    assert result["map"]["received_age_sec"] == pytest.approx(0.2)
    assert result["task_remaining_sec"] == 293.0
    old = result["candidate_version"]
    changed = observation.build_snapshot(frontier_map(), .1, (-6, -5), robots(), 10,
                                         "episode-a", 2, 5)
    assert changed["candidate_version"] != old
    tampered = copy.deepcopy(result)
    tampered["joint_action_mask"][888] = False
    assert observation.snapshot_digest(tampered) != result["digest"]


def test_empty_received_map_has_unknown_padding_and_no_goal_fallback():
    result = observation.build_snapshot(None, .05, (0, 0), robots(), 10, "epoch", 0, 0)
    assert result["map"]["missing"]
    assert result["map"]["source_metadata_missing"]
    assert not any(item["valid"] for item in result["candidates"])
    assert observation.decode_raster(result["maps"]["global"])[2].all()
    assert result["joint_action_mask"][888]


@pytest.mark.parametrize("names", [
    ("tb1", "tb2"), ("tb1", "tb2", "tb4"), ("tb1", "tb1", "tb3"),
])
def test_team_contract_rejects_other_counts_or_duplicate_names(names):
    states = robots()[:len(names)]
    for state, name in zip(states, names):
        state["name"] = name
    with pytest.raises(ValueError, match="exactly tb1"):
        snapshot(states=states)


def test_input_map_source_metadata_cannot_mutate_saved_snapshot():
    metadata = {"tb1": {"sequence": 12}}
    result = snapshot(map_sources=metadata)
    digest = result["digest"]
    metadata["tb1"]["sequence"] = 99
    assert result["map"]["sources"]["tb1"]["sequence"] == 12
    assert observation.snapshot_digest(result) == digest


def test_navigation_ownership_lease_terminal_and_delivered_state_versions_survive():
    states = robots()
    states[0].update(epoch="episode-a", sequence=41, version=9,
                     odom_source_stamp=9.9, tf_source_stamp=10.0)
    states[0]["navigation"].update(
        phase="active", goal_id="episode-a:tb1:1", goal_x=1.0, goal_y=4.0,
        requested_at=5.0, accepted_at=6.0, commitment_until=11.0,
        lease_until=12.0, owned=True, cancel_requested=False,
        last_terminal="SUCCEEDED", last_goal_id="episode-a:tb1:0",
    )
    state = snapshot(states=states)["robots"][0]
    assert state["sequence"] == 41 and state["version"] == 9
    assert state["tf_source_stamp"] == 10.0
    nav = state["navigation"]
    assert nav["owned"] and nav["lease_until"] == 12.0
    assert nav["goal_age_sec"] == 5.0 and nav["acceptance_age_sec"] == 4.0
    assert nav["goal_distance_m"] == 5.0
    assert nav["last_terminal"] == "SUCCEEDED"


def test_navigation_context_and_missing_receipt_metadata_are_distinct():
    states = robots()
    initial = snapshot(states=states)["robots"][0]["navigation"]
    assert not initial["missing"]  # Initial idle ownership is known locally.
    assert initial["receipt_missing"] and initial["source_metadata_missing"]
    assert initial["source_age_sec"] is None
    states[0]["navigation"].update(source_stamp=9.8, received_stamp=9.9, sequence=7)
    delivered = snapshot(states=states)["robots"][0]["navigation"]
    assert not delivered["receipt_missing"] and not delivered["source_metadata_missing"]
    assert delivered["receipt_sequence"] == 7
    assert delivered["source_age_sec"] == pytest.approx(.2)
    assert delivered["received_age_sec"] == pytest.approx(.1)
    states[0]["navigation"]["source_stamp"] = float("nan")
    assert snapshot(states=states)["robots"][0]["navigation"]["source_metadata_missing"]


def own_maps(grid=None, resolution=.1, origin=(-6., -5.)):
    return {name: {
        "grid": frontier_map() if grid is None else grid.copy(),
        "resolution": resolution, "origin": origin, "epoch": "episode-a",
        "version": 5, "sequence": 7, "source_stamp": 9.0,
        "received_stamp": 9.8, "payload_sha256": "received-payload-digest-" + name,
    } for name in observation.ROBOT_NAMES}


def test_delivered_own_maps_do_not_snap_or_erase_peer_body_in_fused_map():
    fused = frontier_map()
    for column in (40, 60):
        fused[50, column] = 100  # Peer observations of another robot's own body.
    original = fused.copy()
    assert snapshot(fused)["diagnostics"]["robot_seed_traversable"] == [False, False, True]
    result = snapshot(fused, robot_maps=own_maps())
    assert result["diagnostics"]["robot_seed_traversable"] == [True] * 3
    assert all(any(candidate["reachable"][index] for candidate in result["candidates"])
               for index in range(3))
    assert np.array_equal(fused, original)
    for candidate in result["candidates"]:
        assert fused[candidate["row"], candidate["column"]] == 0
        assert candidate["clearance_m"] >= .29
    assert result["diagnostics"]["path_map_source"] == ["delivered_own_map"] * 3


def test_missing_delivered_own_map_never_falls_back_to_fused_path():
    maps = own_maps()
    del maps["tb2"]
    result = snapshot(robot_maps=maps)
    assert result["path_maps"]["tb2"]["missing"]
    assert result["per_robot_action_mask"][1] == [False] * 8 + [True, False]
    assert all(not candidate["reachable"][1] for candidate in result["candidates"])
    assert result["joint_action_mask"][888]
    missing_all = snapshot(robot_maps={})
    assert not any(candidate["valid"] for candidate in missing_all["candidates"])
    assert sum(missing_all["joint_action_mask"]) == 1


def test_own_map_fractional_origins_and_different_resolution_use_world_coordinates():
    # Own observations cover the entire candidate region; their pixel centres
    # deliberately do not coincide with the fused .1 m grid's centres.
    maps = own_maps(np.zeros((220, 260), dtype=np.int8), .05, (-6.5125, -5.5125))
    result = snapshot(robot_maps=maps)
    assert len([item for item in result["candidates"] if item["valid"]]) == 8
    for candidate in result["candidates"]:
        assert all(candidate["reachable"])
        for robot_index, state in enumerate(robots()):
            distance = candidate["path_distances_m"][robot_index]
            direct = math.dist((state["x"], state["y"]), (candidate["x"], candidate["y"]))
            assert distance >= direct - 1e-8
    assert result["path_maps"]["tb1"]["native_origin_m"] == [-6.5125, -5.5125]
    assert result["path_maps"]["tb1"]["native_resolution_m"] == .05


def test_own_map_one_cell_wall_and_unknown_cells_are_not_fused_free_paths():
    maps = own_maps()
    maps["tb1"]["grid"][:, 59] = 100
    result = snapshot(robot_maps=maps)
    assert any(item["valid"] and item["x"] > 1 and not item["reachable"][0]
               for item in result["candidates"])
    assert any(item["valid"] and item["x"] < -1 and item["reachable"][0]
               for item in result["candidates"])
    maps["tb1"]["grid"][:, 59] = -1
    unknown = snapshot(robot_maps=maps)
    assert all(not item["reachable"][0] for item in unknown["candidates"]
               if item["valid"] and item["x"] > 1)


def test_unsafe_own_map_seed_has_no_nearest_free_cell_recovery():
    maps = own_maps()
    maps["tb1"]["grid"][50, 40] = 100
    original = maps["tb1"]["grid"].copy()
    result = snapshot(robot_maps=maps)
    assert not result["diagnostics"]["robot_seed_traversable"][0]
    assert result["path_maps"]["tb1"]["unavailable_reason"] == "robot_seed_not_observed_safe"
    assert not any(item["reachable"][0] for item in result["candidates"])
    assert np.array_equal(original, maps["tb1"]["grid"])


def test_delivered_own_map_provenance_is_detached_and_part_of_snapshot_digest():
    maps = own_maps()
    result = snapshot(robot_maps=maps)
    provenance = result["path_maps"]["tb1"]
    assert provenance["version"] == 5 and provenance["sequence"] == 7
    assert provenance["source_age_sec"] == 1.
    assert provenance["received_age_sec"] == pytest.approx(.2)
    assert provenance["payload_sha256"] == "received-payload-digest-tb1"
    assert len(provenance["geometry_sha256"]) == 64
    maps["tb1"]["grid"][:] = 100
    maps["tb1"]["version"] = 6
    assert observation.snapshot_digest(result) == result["digest"]
    assert provenance["version"] == 5


@pytest.mark.parametrize("edit", [{"epoch": "old-episode"}, {"source_stamp": 11.}])
def test_cross_epoch_or_future_delivered_own_map_is_unavailable(edit):
    maps = own_maps()
    maps["tb1"].update(edit)
    result = snapshot(robot_maps=maps)
    assert result["path_maps"]["tb1"]["missing"]
    assert not any(item["reachable"][0] for item in result["candidates"])
    assert result["per_robot_action_mask"][0] == [False] * 8 + [True, False]


def test_tf_source_and_validity_stamp_are_both_observable():
    states = robots()
    states[0].update(tf_source_stamp=9.8, tf_validity_stamp=10.0, tf_validity_lead_sec=.2)
    state = snapshot(states=states)["robots"][0]
    assert state["tf_source_stamp"] == 9.8
    assert state["tf_validity_stamp"] == 10.
    assert state["tf_validity_lead_sec"] == .2
