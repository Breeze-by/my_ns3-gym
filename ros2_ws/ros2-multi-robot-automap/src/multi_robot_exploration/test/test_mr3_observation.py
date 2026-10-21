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
        assert candidate["clearance_m"] >= observation.TARGET_CLEARANCE_M
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


def test_per_robot_geometric_reservation_keeps_a_small_disconnected_component():
    # A small central observed island must keep a slot even when the two large
    # outer components supply most of the spatially distant frontier pool.
    grid = np.full((180, 240), -1, dtype=np.int8)
    grid[10:170, 10:100] = 0
    grid[10:170, 140:230] = 0
    grid[80:100, 110:130] = 0
    states = robots()
    for state, x in zip(states, (-7., 7., 0.)):
        state["x"] = x
    maps = own_maps(grid, origin=(-12., -9.))
    result = observation.build_snapshot(
        grid, .1, (-12., -9.), states, 10., "episode-a", 2, 4, robot_maps=maps)
    assert result["diagnostics"]["candidate_truncated"] > 0
    assert all(count > 0 for count in result["diagnostics"]["per_robot_reachable_pool_counts"])
    assert all(count > 0 for count in result["diagnostics"]["per_robot_reachable_selected_counts"])
    assert all(any(candidate["reachable"][index] for candidate in result["candidates"])
               for index in range(3))
    replay = observation.build_snapshot(
        grid.copy(), .1, (-12., -9.), list(reversed(copy.deepcopy(states))),
        10., "episode-a", 2, 4, robot_maps=dict(reversed(list(maps.items()))))
    assert replay == result


def test_occluded_nearest_staging_uses_a_visible_reachable_geometric_alternative():
    grid = np.zeros((30, 30), dtype=np.int8)
    grid[9, 10] = -1
    grid[12, 10] = 100
    _, clearance = observation.native_traversable(grid, .1)
    # For frontier(10,10), (17,10) is nearer but hidden by the occupied cell;
    # (15,16) has a free sightline. Both target arrival disks are certified.
    cells = np.asarray(((17, 10), (15, 16)))
    assert np.all(clearance[tuple(cells.T)] >= observation.TARGET_CLEARANCE_M)
    paths = np.asarray(((1., np.inf, np.inf), (1., np.inf, np.inf)))
    candidates, diagnostic = observation._candidates(
        grid, clearance, cells, paths, .1, (-1.5, -1.5), robots())
    assert diagnostic["per_robot_staging_rejections"][0]["alternate_staging_searches"] > 0
    assert any((candidate["row"], candidate["column"]) == (15, 16) for candidate in candidates)
    assert diagnostic["per_robot_reachable_pool_counts"][1:] == [0, 0]


@pytest.mark.parametrize("barrier", (-1, 100))
def test_arrival_disk_rejects_body_only_staging_without_relaxing_path_clearance(barrier):
    grid = np.full((100, 120), barrier, dtype=np.int8)
    grid[10:90, 56:64] = 0  # .8 m corridor: body fits, the arrival disk does not.
    traversable, clearance = observation.native_traversable(grid, .1)
    assert traversable.any()
    assert clearance.max() < observation.TARGET_CLEARANCE_M
    states = robots()
    for state, y in zip(states, (-2., 0., 2.)):
        state.update(x=.05, y=y + .05)
    result = snapshot(grid, states, robot_maps=own_maps(grid))
    assert result["diagnostics"]["robot_seed_traversable"] == [True] * 3
    assert not any(candidate["valid"] for candidate in result["candidates"])
    assert result["joint_action_mask"][888] and result["joint_action_mask"][999]


def test_native_own_target_requires_arrival_disk_even_if_fused_target_is_safe():
    cells = np.asarray(((50, 13), (50, 14)))
    maps = own_maps()
    paths, _, valid = observation._own_map_paths(
        maps, [observation._robot_state(robot, 10.) for robot in robots()],
        10., "episode-a", .1, (-6., -5.), cells)
    assert valid == [True] * 3
    assert np.isinf(paths[0]).all()  # .329m own-map clearance: body only.
    assert np.isfinite(paths[1]).all()  # .429m also certifies the .10m disk.


def test_goals_already_inside_arrival_tolerance_are_not_actor_goal_choices():
    initial = snapshot(robot_maps=own_maps())
    state = robots()
    state[0]["x"], state[0]["y"] = initial["candidates"][0]["x"], initial["candidates"][0]["y"]
    result = snapshot(states=state, robot_maps=own_maps())
    assert result["diagnostics"]["per_robot_arrival_noop_cells"][0] > 0
    for candidate in result["candidates"]:
        if candidate["reachable"][0]:
            assert math.dist((candidate["x"], candidate["y"]),
                             (state[0]["x"], state[0]["y"])) > observation.GOAL_XY_TOLERANCE_M
    assert result["joint_action_mask"][888]


@pytest.mark.parametrize("value,reason", ((-1, "seed_cell_unknown"), (100, "seed_cell_occupied")))
def test_seed_diagnostics_identify_observed_blockage_without_changing_map(value, reason):
    maps = own_maps()
    maps["tb1"]["grid"][50, 40] = value
    original = maps["tb1"]["grid"].copy()
    result = snapshot(robot_maps=maps)
    diagnostic = result["diagnostics"]["robot_seed_diagnostics"][0]
    assert diagnostic["seed_cell"] == [50, 40]
    assert diagnostic["seed_cell_clearance_m"] == 0.
    assert diagnostic["seed_rejection_reason"] == reason
    assert result["diagnostics"]["per_robot_reachable_pool_counts"][0] == 0
    assert result["diagnostics"]["per_robot_reachable_selected_counts"][0] == 0
    assert np.array_equal(maps["tb1"]["grid"], original)


def test_seed_diagnostics_account_for_actual_pose_offset_without_snapping():
    maps = own_maps()
    maps["tb1"]["grid"][:, 36] = 100
    states = robots()
    states[0].update(x=-1.99, y=.01)
    result = snapshot(states=states, robot_maps=maps)
    diagnostic = result["path_maps"]["tb1"]
    assert diagnostic["seed_cell_clearance_m"] >= observation.CLEARANCE_M
    assert diagnostic["seed_pose_clearance_lower_bound_m"] < observation.CLEARANCE_M
    assert diagnostic["seed_pose_cell_offset_m"] > 0.
    assert diagnostic["seed_rejection_reason"] == "seed_pose_body_clearance"
    assert not any(candidate["reachable"][0] for candidate in result["candidates"])


def test_explicit_exact_seed_rule_restores_only_false_scalar_rejection_and_binds_identity():
    maps = own_maps()
    maps["tb1"]["grid"][:, 36] = 100
    states = robots()
    states[0].update(x=-1.99, y=.01)
    before = copy.deepcopy(maps)
    legacy = snapshot(states=states, robot_maps=maps)
    exact = snapshot(states=states, robot_maps=maps, seed_rule="exact-point-bridge-v1")
    old, new = legacy["path_maps"]["tb1"], exact["path_maps"]["tb1"]
    assert old["seed_rejection_reason"] == "seed_pose_body_clearance"
    assert new["seed_rejection_reason"] is None
    assert new["seed_cell"] == old["seed_cell"]
    assert new["seed_pose_clearance_lower_bound_m"] == old["seed_pose_clearance_lower_bound_m"]
    certificate = new["seed_point_bridge_certificate"]
    assert certificate["accepted"] and certificate["required_m_exact"] == "29/100"
    assert any(candidate["reachable"][0] for candidate in exact["candidates"])
    assert exact["candidate_rule"]["version"] == "mr3-per-robot-geometric-staging-v5-exact-seed-v1"
    assert exact["candidate_version"] != legacy["candidate_version"]
    assert "seed_rule" not in legacy["candidate_rule"]
    assert "seed_point_bridge_certificate" not in old
    for name in maps:
        np.testing.assert_array_equal(maps[name]["grid"], before[name]["grid"])
    assert legacy == snapshot(states=states, robot_maps=maps, seed_rule="legacy")


@pytest.mark.parametrize("change,reason", (
    ("unknown", "seed_cell_unknown"), ("occupied", "seed_cell_occupied"),
    ("stale_state", "state_missing_or_stale"), ("epoch", "cross_epoch"),
    ("future", "future_map"), ("missing", "missing_received_own_map"),
))
def test_exact_seed_certificate_cannot_override_upstream_gates(monkeypatch, change, reason):
    maps, states = own_maps(), robots()
    if change in ("unknown", "occupied"):
        maps["tb1"]["grid"][50, 40] = -1 if change == "unknown" else 100
    elif change == "stale_state":
        states[0]["source_stamp"] = 0.
    elif change == "epoch":
        maps["tb1"]["epoch"] = "another-epoch"
    elif change == "future":
        maps["tb1"]["source_stamp"] = 11.
    else:
        del maps["tb1"]
    def forbidden(*args, **kwargs):
        raise AssertionError("certificate called before original upstream gates")
    monkeypatch.setattr(observation, "certify_seed_pose_bridge", forbidden)
    result = snapshot(states=states, robot_maps=maps, seed_rule="exact-point-bridge-v1")
    assert result["path_maps"]["tb1"]["seed_rejection_reason"] == reason
    assert result["path_maps"]["tb1"]["seed_point_bridge_certificate"] is None
    assert not any(candidate["reachable"][0] for candidate in result["candidates"])


def test_unknown_seed_rule_is_rejected_before_snapshot_generation():
    with pytest.raises(ValueError, match="seed"):
        snapshot(seed_rule="relaxed")


def test_candidate_rule_and_arrival_geometry_are_hash_bound(monkeypatch):
    result = snapshot()
    assert result["candidate_rule"]["version"] == observation.CANDIDATE_RULE_VERSION
    assert result["candidate_rule"]["goal_xy_tolerance_m"] == .10
    assert result["candidate_rule"]["target_clearance_m"] == pytest.approx(.39)
    monkeypatch.setattr(observation, "CANDIDATE_RULE_VERSION", "another-geometric-rule")
    changed = snapshot()
    assert result["candidates"] == changed["candidates"]
    assert result["candidate_version"] != changed["candidate_version"]


def test_goal_conflicts_use_arrival_radii_and_actual_idle_pose_radius():
    base = snapshot()
    states = copy.deepcopy(base["robots"])
    candidates = copy.deepcopy(base["candidates"])
    for candidate in candidates:
        candidate.update(valid=False, reachable=[False] * 3)
    candidates[0].update(valid=True, x=0., y=0., reachable=[True, False, False])
    states[0].update(x=-3., y=0.)
    states[1].update(x=.70, y=0.)
    states[2].update(x=5., y=0.)
    _, idle_mask, _ = observation._action_masks(states, candidates, 10.)
    assert idle_mask[88]  # .70m exceeds new-goal/actual-idle .39+.29m.
    states[1]["navigation"].update(phase="active", goal_x=.70, goal_y=0.)
    _, active_mask, _ = observation._action_masks(states, candidates, 10.)
    assert not active_mask[88]  # Two arrival disks require .39+.39m.
    assert active_mask[888]  # An inherited KEEP pair never removes all-KEEP.
    states[1]["navigation"]["goal_x"] = .80
    _, separated_mask, _ = observation._action_masks(states, candidates, 10.)
    assert separated_mask[88]


def frontier_source_counterexample():
    fused = np.full((100, 100), -1, dtype=np.int8)
    fused[5:95, 5:95] = 0
    small = np.full_like(fused, -1)
    small[43:57, 43:57] = 0
    states = robots()
    for state, x in zip(states, (-3.05, .05, 3.05)):
        state.update(x=x, y=.05)
    maps = own_maps(fused, origin=(-5., -5.))
    maps["tb2"]["grid"] = small
    return fused, states, maps


def test_received_own_frontier_restores_choice_when_fused_frontiers_are_too_far():
    # A robot's small, fully safe own component can have no candidate near the
    # expanding fused frontier. Its received frontiers preserve geometric choices
    # while all paths and arrival disks still use the unchanged conservative maps.
    fused, states, maps = frontier_source_counterexample()
    before = fused.copy()
    result = observation.build_snapshot(
        fused, .1, (-5., -5.), states, 10., "episode-a", 2, 4, robot_maps=maps)
    traversable, clearance = observation.native_traversable(fused, .1)
    targets = np.argwhere(traversable & (clearance >= observation.TARGET_CLEARANCE_M))
    paths, _, _ = observation._own_map_paths(
        maps, copy.deepcopy(result["robots"]), 10., "episode-a", .1, (-5., -5.), targets)
    _, old = observation._candidates(
        fused, clearance, targets, paths, .1, (-5., -5.), result["robots"])
    assert old["per_robot_reachable_target_cells"][1] == 33
    assert old["per_robot_reachable_pool_counts"][1] == 0
    assert result["diagnostics"]["per_robot_reachable_target_cells"][1] == 33
    assert result["diagnostics"]["per_robot_reachable_pool_counts"][1] == 20
    assert any(allowed and observation.decode_joint_action(action)[1] < 8
               for action, allowed in enumerate(result["joint_action_mask"]))
    assert np.array_equal(fused, before)
    replay = observation.build_snapshot(
        fused, .1, (-5., -5.), list(reversed(states)), 10., "episode-a", 2, 4,
        robot_maps=dict(reversed(list(maps.items()))))
    assert replay == result


@pytest.mark.parametrize("edit,reason", [
    ({"epoch": "previous-episode"}, "cross_epoch"),
    ({"source_stamp": 10.01}, "future_map"),
    ({"received_stamp": 10.01}, "future_map"),
])
def test_unavailable_received_map_cannot_contribute_candidate_frontiers(edit, reason):
    fused, states, maps = frontier_source_counterexample()
    maps["tb2"].update(edit)
    result = observation.build_snapshot(
        fused, .1, (-5., -5.), states, 10., "episode-a", 2, 4, robot_maps=maps)
    contribution = result["diagnostics"]["frontier_sources"]["tb2"]
    assert not contribution["eligible"]
    assert contribution["unavailable_reason"] == reason
    assert contribution["native_frontier_cells"] == contribution["new_union_cells"] == 0
    assert result["diagnostics"]["per_robot_reachable_selected_counts"][1] == 0


@pytest.mark.parametrize("barrier", (-1, 100))
def test_received_frontier_union_does_not_clear_fused_unknown_or_obstacles(barrier):
    fused = np.full((100, 120), barrier, dtype=np.int8)
    original = fused.copy()
    result = snapshot(fused, robot_maps=own_maps())
    assert result["diagnostics"]["robot_seed_traversable"] == [True] * 3
    assert not any(candidate["valid"] for candidate in result["candidates"])
    for name in observation.ROBOT_NAMES:
        contribution = result["diagnostics"]["frontier_sources"][name]
        assert contribution["native_frontier_cells"] > 0
        assert contribution["projected_fused_free_cells"] == 0
        assert contribution["rejected_fused_unknown_or_occupied_cells"] > 0
    assert result["joint_action_mask"][888]
    assert np.array_equal(fused, original)


def test_frontier_projection_uses_each_received_map_origin_and_resolution():
    fused = np.zeros((60, 80), dtype=np.int8)
    maps = own_maps(np.full((40, 60), -1, dtype=np.int8), .05, (-1.0375, -.5375))
    for entry in maps.values():
        entry["grid"][5:35, 5:55] = 0
    result = observation.build_snapshot(
        fused, .1, (-3., -2.), robots(), 10., "episode-a", 2, 4, robot_maps=maps)
    frontier, sources = observation._candidate_frontiers(
        fused, .1, (-3., -2.), maps, result["path_maps"])
    own_cells = np.argwhere(observation._frontiers(maps["tb1"]["grid"]))
    expected = np.zeros_like(frontier)
    for row, column in own_cells:
        x = maps["tb1"]["origin"][0] + (column + .5) * .05
        y = maps["tb1"]["origin"][1] + (row + .5) * .05
        expected[math.floor((y + 2.) / .1), math.floor((x + 3.) / .1)] = True
    assert np.array_equal(frontier, expected)
    assert sources["tb1"]["new_union_cells"] == int(expected.sum())
    assert sources["tb2"]["new_union_cells"] == sources["tb3"]["new_union_cells"] == 0


def test_missing_received_maps_have_no_frontier_fallback():
    result = snapshot(robot_maps={})
    assert all(not result["diagnostics"]["frontier_sources"][name]["eligible"]
               for name in observation.ROBOT_NAMES)
    assert result["candidate_rule"]["frontier_sources"] == [
        "fused_received", "received_own:tb1", "received_own:tb2", "received_own:tb3"]
    assert result["candidate_rule"]["frontier_projection"] == (
        "world cell centre to containing fused native cell; free endpoints only")
    assert sum(result["joint_action_mask"]) == 1


def navigation_maps(grid=None):
    maps = own_maps(grid)
    for entry in maps.values():
        entry.update(composition_version=observation.NAVIGATION_COMPOSITION_VERSION,
                     input_own_map_payload_sha256="own-delivered-payload",
                     input_shared_map_payload_sha256="shared-delivered-payload",
                     shared_map_version=2)
    return maps


def test_navigation_candidates_certify_actual_path_map_instead_of_fused_start_conflicts():
    fused = frontier_map()
    fused[48:53, 58:63] = 100
    original = fused.copy()
    maps = navigation_maps()
    result = snapshot(fused, robot_maps=own_maps(), navigation_maps=maps)
    assert result["candidate_rule"]["version"] == observation.NAVIGATION_CANDIDATE_RULE_VERSION
    assert result["diagnostics"]["path_map_source"] == ["delivered_navigation_map"] * 3
    assert result["path_maps"]["tb2"]["seed_rejection_reason"] is None
    assert result["diagnostics"]["per_robot_reachable_target_cells"][1] > 0
    assert any(allowed and observation.decode_joint_action(action)[1] < 8
               for action, allowed in enumerate(result["joint_action_mask"]))
    assert np.array_equal(fused, original)
    assert observation.snapshot_digest(result) == result["digest"]
    for candidate in result["candidates"]:
        for index, value in enumerate(candidate["clearance_by_robot_m"]):
            assert (value is not None) == candidate["reachable"][index]
            if value is not None:
                assert value >= observation.TARGET_CLEARANCE_M


def test_navigation_occupied_own_seed_cannot_be_cleared_or_snapped_by_fused_map():
    maps = navigation_maps()
    maps["tb2"]["grid"][50, 60] = 100
    before = maps["tb2"]["grid"].copy()
    result = snapshot(navigation_maps=maps)
    assert result["path_maps"]["tb2"]["seed_rejection_reason"] == "seed_cell_occupied"
    assert not any(candidate["reachable"][1] for candidate in result["candidates"])
    assert np.array_equal(maps["tb2"]["grid"], before)


def test_missing_navigation_map_does_not_fall_back_to_own_or_fused_paths():
    maps = navigation_maps()
    del maps["tb2"]
    result = snapshot(navigation_maps=maps, robot_maps=own_maps())
    assert result["path_maps"]["tb2"]["unavailable_reason"] == "missing_received_navigation_map"
    assert result["per_robot_action_mask"][1] == [False] * 8 + [True, False]
    assert result["joint_action_mask"][888]


@pytest.mark.parametrize("edit", [{"origin": (-5.99, -5.)}, {"resolution": .05},
                                  {"composition_version": "unreviewed-rule"}])
def test_navigation_map_lattice_and_composition_are_explicit_not_silently_resampled(edit):
    maps = navigation_maps()
    maps["tb2"].update(edit)
    with pytest.raises(ValueError, match="navigation"):
        snapshot(navigation_maps=maps)


def test_navigation_known_line_uses_that_robots_obstacles_not_fused_free_cells():
    grid = np.zeros((30, 30), dtype=np.int8)
    grid[9, 10] = -1
    native = grid.copy()
    native[12, :] = 100
    _, clearance = observation.native_traversable(grid, .1)
    cells = np.asarray(((17, 10),))
    candidates, diagnostics = observation._candidates(
        grid, clearance, cells, np.asarray(((1., np.inf, np.inf),)),
        .1, (-1.5, -1.5), robots(), line_grids=[native, grid, grid])
    assert not candidates
    assert diagnostics["per_robot_staging_rejections"][0]["occluded_staging_line"] > 0
