import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from multi_robot_exploration.mr3_task_contract import (
    ContractTruthGrid,
    RASTERIZATION,
    audit_lidar_slice_invariance,
    compare_contract_occupancy_grid,
    diagnose_contract_geometry,
    inspect_world_geometry,
    load_contract_truth,
    load_task_contract,
)


WORLD_DIR = Path(__file__).resolve().parents[2] / "multi_robot/worlds"


def write_world(tmp_path, model_body="", state=""):
    path = tmp_path / "fixture.world"
    path.write_text(f"""<sdf version='1.6'><world name='fixture'>
    <model name='walls'><static>true</static>{model_body}</model>{state}
    </world></sdf>""")
    return path


def box(size=".1 1 1", pose="0 0 .5 0 0 0"):
    return f"""<link name='wall'><collision name='c'><pose>{pose}</pose>
    <geometry><box><size>{size}</size></box></geometry></collision></link>"""


def write_contract(tmp_path, world, bounds=None, updates=None):
    data = {
        "schema_version": 1, "contract_id": "MR3-P1A-v1",
        "robots": ["tb1", "tb2", "tb3"], "world_file": world.name,
        "world_sha256": hashlib.sha256(world.read_bytes()).hexdigest(),
        "frame_id": "map", "resolution": .05, "lidar_height_m": .131,
        "max_duration_sec": 300, "coverage_threshold": .95,
        "truth_rasterization": RASTERIZATION,
        "roi": {"type": "rectangle", "bounds": bounds or [-2, -2, 2, 2],
                "rationale": "Fixture physical room envelope, before task execution"},
        "starts": {"tb1": [-1, -.45], "tb2": [-1, .45], "tb3": [-.55, 0]},
        "robot_radius_m": .25, "lidar_range_m": 10,
        "quality": {"min_observed_accuracy": .95, "min_occupied_iou": .20,
                    "max_false_free_ratio": .02},
        "participation": {"min_path_length_m": 1, "min_goal_count": 1},
        "contact_monitor_max_age_sec": .5,
        "support_collision_names": ["ground_plane::link::collision"],
        "navigation_closure_timeout_sec": 10.0,
        "task_start_barrier": "controller_release",
    }
    data.update(updates or {})
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(data))
    return path


def test_contract_binds_world_and_fixed_three_robot_task(tmp_path):
    world = write_world(tmp_path, box())
    contract_path = write_contract(tmp_path, world)
    contract = load_task_contract(contract_path, world)
    assert contract.sha256 == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    truth = load_contract_truth(world, contract)
    assert truth.world_sha256 == contract.data["world_sha256"]
    assert truth.occupied.shape == (80, 80)
    assert np.all(truth.roi_mask)
    world.write_text(world.read_text().replace(".1 1 1", ".2 1 1"))
    with pytest.raises(ValueError, match="World SHA256"):
        load_task_contract(contract_path, world)
    with pytest.raises(ValueError, match="changed after loading"):
        load_contract_truth(world, contract)


@pytest.mark.parametrize("updates", [
    {"robots": ["tb1", "tb2"]}, {"max_duration_sec": 301},
    {"coverage_threshold": .90}, {"resolution": 0},
    {"lidar_height_m": float("nan")}, {"frame_id": "world"},
    {"truth_rasterization": "center_sampling"},
    {"quality": {"min_observed_accuracy": 2, "min_occupied_iou": .2,
                 "max_false_free_ratio": .02}},
    {"participation": {"min_path_length_m": 1, "min_goal_count": True}},
    {"roi": {"type": "rectangle", "bounds": [-2, -2, 2.01, 2],
             "rationale": "physical geometry"}},
    {"schema_version": True}, {"roi": []}, {"starts": []},
    {"quality": []}, {"participation": []},
    {"support_collision_names": None}, {"support_collision_names": []},
    {"support_collision_names": ["ground_plane"]},
    {"support_collision_names": [{}]},
    {"support_collision_names": ["tb2::wheel_left_link::wheel_left_collision"]},
    {"navigation_closure_timeout_sec": 11},
    {"navigation_closure_timeout_sec": float("nan")},
    {"task_start_barrier": "first_map"},
])
def test_contract_rejects_relaxed_or_invalid_gates(tmp_path, updates):
    world = write_world(tmp_path, box())
    with pytest.raises(ValueError):
        load_task_contract(write_contract(tmp_path, world, updates=updates), world)


def test_contract_rejects_non_object_json_root(tmp_path):
    world = write_world(tmp_path, box())
    path = tmp_path / "contract.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="JSON object"):
        load_task_contract(path, world)


def test_saved_state_model_and_absolute_link_poses_are_not_double_transformed(tmp_path):
    world = write_world(tmp_path,
                        "<pose>50 50 0 0 0 0</pose>" + box("2 1 1"),
                        """<state world_name='fixture'><model name='walls'>
                        <pose>2 3 0 0 0 0</pose><link name='wall'>
                        <pose>4 5 0 0 0 0</pose></link></model></state>""")
    rectangles, audit = inspect_world_geometry(world)
    assert rectangles == [(4, 5, 0, 2, 1)]
    assert audit["saved_state_count"] == 1
    assert audit["unsupported_collision_count"] == 0


def test_rotated_parent_coordinates_and_height_slice_are_respected(tmp_path):
    world = write_world(tmp_path, "<pose>2 3 0 0 0 1.5707963267948966</pose>" +
                        box("2 1 1", "1 0 .5 0 0 0"))
    rectangles, _ = inspect_world_geometry(world)
    assert rectangles[0][0] == pytest.approx(2)
    assert rectangles[0][1] == pytest.approx(4)
    assert rectangles[0][2] == pytest.approx(np.pi/2)
    assert not inspect_world_geometry(world, 2)[0]


@pytest.mark.parametrize("body", [
    "<link name='wall'><collision name='c'><geometry><mesh><uri>x.obj</uri>"
    "</mesh></geometry></collision></link>",
    "<pose>0 0 0 .1 0 0</pose>" + box(),
    "<pose relative_to='other'>0 0 0 0 0 0</pose>" + box(),
])
def test_unsupported_truth_fails_closed_with_object_and_reason(tmp_path, body):
    world = write_world(tmp_path, body)
    _, audit = inspect_world_geometry(world)
    assert audit["unsupported"]
    contract = load_task_contract(write_contract(tmp_path, world), world)
    with pytest.raises(ValueError, match="Unsupported task geometry"):
        load_contract_truth(world, contract)


def test_thin_boxes_survive_positive_area_cell_rasterization(tmp_path):
    world = write_world(tmp_path, box(".01 1 1", "0 0 .5 0 0 0"))
    truth = load_contract_truth(world, load_task_contract(write_contract(tmp_path, world), world))
    assert np.count_nonzero(truth.occupied) == 40
    assert np.count_nonzero(truth.center_sampled_occupied) == 0
    # Only positive area intersections count: no third column at a tangent edge.
    world.write_text(world.read_text().replace(".01 1 1", ".1 1 1"))
    truth = load_contract_truth(world, load_task_contract(write_contract(tmp_path, world), world))
    assert np.count_nonzero(truth.occupied) == 40


def small_truth():
    occupied = np.array([[False, True], [False, True]])
    return ContractTruthGrid(occupied, 0, 0, 1, 1, 0,
                             np.ones_like(occupied), "world", "contract", .131,
                             {}, occupied.copy())


def test_map_metrics_preserve_unknown_penalty_and_count_false_free():
    metrics = compare_contract_occupancy_grid(small_truth(), [0, 100, -1, 0],
                                              2, 2, 1, [0, 0])
    assert metrics["correct_free_coverage_ratio"] == .5
    assert metrics["observed_accuracy"] == 2/3
    assert metrics["occupied_iou"] == .5
    assert metrics["false_free_cell_count"] == 1
    assert metrics["false_free_ratio"] == .5
    assert metrics["false_free_denominator"] == "truth_occupied_cell_count"


def test_rotated_map_and_outside_unknown_sampling():
    # A map rotated pi/2 covers x=[0,2], y=[0,2] from origin (2,0).
    metrics = compare_contract_occupancy_grid(small_truth(), [100, 100, 0, 0],
                                              2, 2, 1, [2, 0], np.pi/2)
    assert metrics["correct_coverage_ratio"] == 1
    metrics = compare_contract_occupancy_grid(small_truth(), [0], 1, 1, 1, [10, 10])
    assert metrics["known_truth_cell_count"] == 0
    assert metrics["correct_free_coverage_ratio"] == 0


@pytest.mark.parametrize("values", [[101, 0, 0, 0], [-2, 0, 0, 0],
                                    [0.0, 0.0, 0.0, 0.0], [0, 0, 0]])
def test_map_metrics_reject_invalid_or_partial_payload(values):
    with pytest.raises(ValueError):
        compare_contract_occupancy_grid(small_truth(), values, 2, 2, 1, [0, 0])


def test_closed_region_is_retained_and_visibility_diagnostic_is_inconclusive(tmp_path):
    # A full room partition leaves real free cells outside the start component.
    world = write_world(tmp_path, box(".1 4 1"))
    contract = load_task_contract(write_contract(tmp_path, world), world)
    truth = load_contract_truth(world, contract)
    before = truth.occupied.copy()
    report = diagnose_contract_geometry(truth, contract)
    assert report["free_component_count"] == 2
    assert report["visible_free_fraction_lower_bound"] < .6
    assert report["range_only_free_fraction_upper_bound"] == 1
    assert report["denominator_trimmed_by_diagnostic"] is False
    assert np.array_equal(before, truth.occupied)
    assert report["truth_free_cell_count"] == np.count_nonzero(~before)


@pytest.mark.parametrize("name,bounds", [
    ("p1c_open.world", [-6.1, -5.1, 6.1, 5.1]),
    ("p1c_rooms.world", [-7.1, -5.1, 7.1, 5.1]),
    ("p1c_corridors.world", [-6.6, -5.1, 6.6, 5.1]),
])
def test_declared_development_worlds_have_connected_centers_and_visible_free_space(
        tmp_path, name, bounds):
    world = WORLD_DIR/name
    path = write_contract(tmp_path, world, bounds,
                          {"starts": {"tb1": [0, -.45], "tb2": [0, .45],
                                      "tb3": [.45, 0]}})
    contract = load_task_contract(path, world)
    truth = load_contract_truth(world, contract)
    report = diagnose_contract_geometry(truth, contract)
    assert report["free_component_count"] == 1
    assert all(entry["traversable"] for entry in report["starts"].values())
    assert report["visible_free_fraction_lower_bound"] >= .95
    assert report["geometry_audit"]["unsupported_collision_count"] == 0


def test_my_world_mesh_is_explicitly_unsupported():
    _, audit = inspect_world_geometry(WORLD_DIR/"my_world.world")
    assert any(issue["object"] == "suv/link/collision" and
               issue["reason"] == "unsupported_mesh" for issue in audit["unsupported"])
    assert audit["saved_state_count"] == 1


def test_slice_invariance_catches_narrow_hidden_vertical_object(tmp_path):
    world = write_world(tmp_path, box() +
                        box(".1 .1 .00002", "1 1 .17 0 0 0"))
    # The extra object is absent at both endpoints and the reference height.
    for height in (.02, .25, .131):
        assert len(inspect_world_geometry(world, height)[0]) == 1
    result = audit_lidar_slice_invariance(world)
    assert not result["invariant"]
    assert any(row["rectangle_count"] == 2 for row in result["probes"])
    assert result["denominator_modified"] is False


@pytest.mark.parametrize("plane", [
    "<include><uri>model://ground_plane</uri></include>",
    "<model name='floor'><static>true</static><link name='floor'>"
    "<collision name='c'><geometry><plane><normal>0 0 1</normal>"
    "<size>10 10</size></plane></geometry></collision></link></model>",
])
def test_slice_invariance_rejects_a_band_crossing_ground_plane(tmp_path, plane):
    world = write_world(tmp_path, box())
    world.write_text(world.read_text().replace("</world>", plane + "</world>"))
    result = audit_lidar_slice_invariance(world, 0, .25, .131)
    assert not result["invariant"]
    assert result["plane_crossings_m"] == [0]


def test_slice_invariance_rejects_unsupported_geometry():
    result = audit_lidar_slice_invariance(WORLD_DIR / "my_world.world")
    assert not result["invariant"]
    assert any(row["unsupported"] for row in result["probes"])


@pytest.mark.parametrize("band", [
    (.25, .02, .131), (.02, .25, .3), (float("nan"), .25, .131),
])
def test_slice_invariance_rejects_invalid_height_bands(band):
    with pytest.raises(ValueError):
        audit_lidar_slice_invariance(WORLD_DIR / "p1c_open.world", *band)


def test_all_twelve_declared_box_worlds_have_identical_slices_in_verified_band():
    paths = [WORLD_DIR / f"p1c_{family}.world" for family in ("open", "rooms", "corridors")]
    paths.extend(sorted(WORLD_DIR.glob("mr3_*.world")))
    assert len(paths) == 12
    for world in paths:
        result = audit_lidar_slice_invariance(world)
        assert result["invariant"], (world.name, result)
        assert result["world_sha256"] == hashlib.sha256(world.read_bytes()).hexdigest()
