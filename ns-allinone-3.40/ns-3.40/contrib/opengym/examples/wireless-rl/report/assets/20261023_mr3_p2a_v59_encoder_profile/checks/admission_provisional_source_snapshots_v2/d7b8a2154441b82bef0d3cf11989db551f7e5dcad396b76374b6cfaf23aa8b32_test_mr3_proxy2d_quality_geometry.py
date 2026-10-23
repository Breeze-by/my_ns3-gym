"""Artificial exact-segment CPU tests; never consumes a real task scene."""

from fractions import Fraction
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import mr3_proxy2d_quality_geometry as geometry
from multi_robot_exploration.mr3_task_contract import _rasterize


def artificial_truth(rectangles, bounds=(-1., -1., 1., 1.), resolution=.25):
    occupied = _rasterize(rectangles, bounds, resolution)
    return SimpleNamespace(occupied=occupied, roi_mask=np.ones_like(occupied),
                           origin_x=bounds[0], origin_y=bounds[1], resolution=resolution)


def scalar_oracle_cover(start, end, shape, resolution, origin, epsilon=geometry.ENCLOSURE_EPSILON_M):
    """Independent exact orientation/edge-crossing oracle, not a slab test."""
    a, b = [tuple(Fraction(float(value)) for value in point) for point in (start, end)]
    r, e = Fraction(float(resolution)), Fraction(float(epsilon))
    ox, oy = (Fraction(float(value)) for value in origin)

    def orientation(p, q, v):
        return (q[0] - p[0]) * (v[1] - p[1]) - (q[1] - p[1]) * (v[0] - p[0])

    def on_segment(p, q, v):
        return orientation(p, q, v) == 0 and all(min(x, y) <= z <= max(x, y)
                                                for x, y, z in zip(p, q, v))

    def edges_intersect(p, q, u, v):
        first, second = orientation(p, q, u), orientation(p, q, v)
        third, fourth = orientation(u, v, p), orientation(u, v, q)
        if first * second < 0 and third * fourth < 0:
            return True
        return any((on_segment(p, q, u), on_segment(p, q, v),
                    on_segment(u, v, p), on_segment(u, v, q)))

    result = np.zeros(shape, dtype=bool)
    for row in range(shape[0]):
        for column in range(shape[1]):
            xmin, xmax = ox + column * r - e, ox + (column + 1) * r + e
            ymin, ymax = oy + row * r - e, oy + (row + 1) * r + e
            corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
            inside = lambda p: xmin <= p[0] <= xmax and ymin <= p[1] <= ymax
            result[row, column] = (inside(a) or inside(b) or any(
                edges_intersect(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4)))
    return result


@pytest.mark.parametrize("start,end", [
    ((1., 1.), (1., 2.)),  # Entirely on a vertical gridline.
    ((0., 0.), (3., 3.)),  # Passes through grid corners.
    ((1., 1.), (1., 1.)),  # Degenerate point includes corner neighbors.
    ((-2., 1.3), (5., 2.7)),  # Both endpoints outside the ROI.
    ((-.3, -.2), (3.4, 1.7)),
    ((-3., -3.), (-2., -2.)),
])
def test_segment_supercover_matches_independent_exact_edge_oracle(start, end):
    actual = geometry.segment_cell_cover(start, end, (4, 4), 1., (0., 0.))
    expected = scalar_oracle_cover(start, end, (4, 4), 1., (0., 0.))
    np.testing.assert_array_equal(actual, expected)


def test_gridline_and_corner_enclosure_deliberately_exceeds_floor_assignment():
    cover = geometry.segment_cell_cover((1., 1.), (1., 2.), (4, 4), 1., (0., 0.))
    assert set(map(tuple, np.argwhere(cover))) == {(row, column) for row in (0, 1, 2) for column in (0, 1)}
    point = geometry.segment_cell_cover((1., 1.), (1., 1.), (4, 4), 1., (0., 0.))
    assert point.sum() == 4  # Exact floor would assign a single cell.


def test_rectangle_rotation_matches_independent_diagonal_coordinates():
    unit = 1 / math.sqrt(2)
    expected = [( .1 - .5 * unit, -.2 - 1.5 * unit),
                ( .1 + 1.5 * unit, -.2 + .5 * unit),
                ( .1 + .5 * unit, -.2 + 1.5 * unit),
                ( .1 - 1.5 * unit, -.2 - .5 * unit)]
    segments = geometry.rectangle_segments((.1, -.2, math.pi / 4, 2., 1.))
    np.testing.assert_allclose([segment[0] for segment in segments], expected, atol=1e-15, rtol=0)
    assert all(segments[i][1] == segments[(i + 1) % 4][0] for i in range(4))


@pytest.mark.parametrize("yaw", [math.pi / 4, -.37])
def test_all_rotated_rectangle_segments_match_independent_cell_oracle(yaw):
    rectangle = (.15, -.13, yaw, 1.2, .45)
    truth = artificial_truth([rectangle])
    expected = np.zeros(truth.occupied.shape, dtype=bool)
    for start, end in geometry.rectangle_segments(rectangle):
        expected |= scalar_oracle_cover(start, end, truth.occupied.shape, .25, (-1., -1.))
    result = geometry.diagnose_rectangles([rectangle], truth)
    assert result["surface_cover_cells_in_roi"] == int(expected.sum())
    assert result["possible_endpoint_overlap_correct_occupied_cells"] == int((expected & truth.occupied).sum())
    assert result["possible_false_positive_surface_cells"] == int((expected & ~truth.occupied).sum())


def test_off_grid_thick_box_reproduces_analytic_surface_volume_bound():
    rectangle = (1.01, 1.41, 0., 2., .8)
    truth = artificial_truth([rectangle], (-.5, 0., 2.5, 2.5), .05)
    result = geometry.diagnose_rectangles([rectangle], truth, minimum_iou=.2)
    assert result["truth_occupied_cell_count"] == 41 * 17 == 697
    assert result["possible_endpoint_overlap_correct_occupied_cells"] == 2 * (41 + 17) - 4 == 112
    assert result["solid_occupied_cells_outside_surface_enclosure"] == 585
    assert result["conditional_occupied_iou_upper_enclosure"] == pytest.approx(112 / 697)
    assert result["conditional_enclosure_below_declared_gate"]
    assert not result["denominator_modified"]
    assert not result["actual_noisy_proxy_task_impossibility_claim"]


def test_duplicate_overlapping_solids_and_surfaces_are_union_counted():
    rectangle = (.125, .125, 0., .75, .75)
    truth = artificial_truth([rectangle])
    single = geometry.diagnose_rectangles([rectangle], truth)
    duplicate = geometry.diagnose_rectangles([rectangle, rectangle], truth, labels=["first", "duplicate"])
    assert single["truth_occupied_cell_count"] == duplicate["truth_occupied_cell_count"]
    assert single["surface_cover_sha256"] == duplicate["surface_cover_sha256"]
    assert single["conditional_occupied_iou_upper_enclosure"] == duplicate["conditional_occupied_iou_upper_enclosure"]
    assert duplicate["surface_cells_covered_by_multiple_obstacles"] == duplicate["surface_cover_cells_in_roi"]
    assert sum(item["unique_possible_correct_occupied_cells"] for item in duplicate["per_obstacle"]) == 0
    assert duplicate["per_obstacle_counts_are_not_additive"]


def test_roi_clipping_never_invents_surfaces_along_the_roi_boundary():
    rectangle = (0., 0., .17, 10., 10.)
    truth = artificial_truth([rectangle])
    result = geometry.diagnose_rectangles([rectangle], truth)
    assert result["truth_occupied_cell_count"] == 64
    assert result["surface_cover_cells_in_roi"] == 0
    assert result["conditional_occupied_iou_upper_enclosure"] == 0.


def test_box_outside_roi_keeps_zero_denominator_undefined_not_a_task_pass():
    rectangle = (3., 0., 0., 1., 1.)
    result = geometry.diagnose_rectangles([rectangle], artificial_truth([rectangle]), minimum_iou=.2)
    assert result["truth_occupied_cell_count"] == result["surface_cover_cells_in_roi"] == 0
    assert result["conditional_occupied_iou_upper_enclosure"] is None
    assert not result["conditional_enclosure_below_declared_gate"]


def test_optional_false_positive_support_is_not_forced_into_upper_bound_denominator():
    rectangle = (0., 0., 0., .5, .5)
    result = geometry.diagnose_rectangles([rectangle], artificial_truth([rectangle]))
    assert result["possible_false_positive_surface_cells"] > 0
    assert result["conditional_occupied_iou_upper_enclosure"] == (
        result["possible_endpoint_overlap_correct_occupied_cells"] / result["truth_occupied_cell_count"])


def test_roi_origin_face_filter_retains_equality_and_discards_only_strict_back_faces():
    # Upward CCW edge has outward normal to its right. A closed-ROI origin
    # on the plane is ambiguous and stays; a strict negative halfspace does not.
    edge = ((1., 0.), (1., 1.))
    assert geometry.roi_front_face_decision(*edge, (0., 0., 1., 1.))["retained"]
    assert not geometry.roi_front_face_decision(*edge, (0., 0., .5, 1.))["retained"]
    assert geometry.roi_front_face_decision(*edge, (0., 0., 2., 1.))["retained"]
    assert geometry.roi_front_face_decision(*edge, (0., 0., 1. - 1e-10, 1.))["retained"]


def test_roi_origin_variant_has_same_full_denominator_and_is_only_an_extra_condition():
    rectangle = (.875, 0., 0., .5, 1.)
    result = geometry.diagnose_rectangles([rectangle], artificial_truth([rectangle]), minimum_iou=.2)
    variant = result["roi_origin_front_face"]
    assert variant["truth_occupied_cell_count"] == result["truth_occupied_cell_count"]
    assert variant["possible_endpoint_overlap_correct_occupied_cells"] <= result["possible_endpoint_overlap_correct_occupied_cells"]
    assert any(not face["retained"] for face in result["per_obstacle"][0]["roi_origin_face_decisions"])
    assert variant["gridline_equality_and_numerical_ambiguity_retained"]
    assert not variant["roi_sensor_origin_assumption_is_guaranteed_by_current_proxy"]


def test_mismatched_truth_invalid_geometry_and_negative_enclosure_are_rejected():
    truth = artificial_truth([(0., 0., 0., .5, .5)])
    truth.occupied[0, 0] = True
    with pytest.raises(ValueError, match="unchanged original rasterizer"):
        geometry.diagnose_rectangles([(0., 0., 0., .5, .5)], truth)
    with pytest.raises(ValueError, match="cannot shrink"):
        geometry.segment_cell_cover((0., 0.), (1., 1.), (4, 4), 1., (0., 0.), epsilon_m=-.01)
    with pytest.raises(ValueError, match="positive"):
        geometry.rectangle_segments((0., 0., 0., -1., 1.))
    with pytest.raises(ValueError, match="finite"):
        geometry.rectangle_segments((float("nan"), 0., 0., 1., 1.))
    with pytest.raises(ValueError, match="finite"):
        geometry.rectangle_segments((np.complex128(1 + 2j), 0., 0., 1., 1.))


@pytest.mark.parametrize("fail_scene", [None, "rooms"])
def test_mock_only_cli_keeps_real_identity_source_bindings_and_partial_failure(tmp_path, monkeypatch, fail_scene):
    # All source/asset files are artificial bytes. No scene loader, Git child,
    # World, node or subprocess is executed; real identity calls exercise the
    # production CLI construction (including os.getsid(0)).
    root = tmp_path / "workspace"
    ros = root / "ros2_ws/ros2-multi-robot-automap"
    package = ros / "src/multi_robot_exploration/multi_robot_exploration"
    module = package / "mr3_proxy2d_quality_geometry.py"
    task = package / "mr3_task_contract.py"
    contacts = package / "mr3_contacts.py"
    files = [module, task, contacts, package / "mr3_proxy2d_world.py",
             package / "mr3_proxy2d_information.py", package / "mr3_information.py",
             ros / "src/merge_map/merge_map/merge_map.py", ros / "scripts/mr3_proxy2d_worker.py"]
    files += [ros / "src/multi_robot" / relative for scene in geometry.SCENES
              for relative in (f"worlds/p1c_{scene}.world", f"config/mr3_p1a/{scene}.json")]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("artificial binding: " + str(path.relative_to(root))).encode())
    monkeypatch.setattr(geometry, "__file__", str(module))
    monkeypatch.setattr(geometry.mr3_task_contract, "__file__", str(task))
    monkeypatch.setattr(geometry.mr3_contacts, "__file__", str(contacts))
    freeze = "a" * 40

    def fake_git(argv, *, cwd, timeout):
        assert Path(cwd) == root and timeout == 5
        if argv == ["git", "rev-parse", "HEAD"]:
            return (freeze + "\n").encode()
        assert argv[:2] == ["git", "show"]
        version, relative = argv[2].split(":", 1)
        assert version == freeze
        return (root / relative).read_bytes()

    called = []

    def fake_scene(scene, asset_root):
        assert asset_root == ros / "src/multi_robot"
        called.append(scene)
        if scene == fail_scene:
            raise ValueError("synthetic scene failure")
        return {"scene": scene, "artificial_test_only": True}

    monkeypatch.setattr(geometry.subprocess, "check_output", fake_git)
    monkeypatch.setattr(geometry, "diagnose_scene", fake_scene)
    output = tmp_path / "new_report.json"
    returncode = geometry.main(["--freeze", freeze, "--output", str(output)])
    report = json.loads(output.read_bytes())
    assert report["freeze"] == freeze and report["bound_bytes_unchanged"]
    assert len(report["source_and_asset_bindings"]) == 14
    assert report["consumer_identity"]["pid"] == os.getpid()
    assert report["consumer_identity"]["session"] == os.getsid(0)
    assert report["consumer_identity"]["start_ticks"] > 0
    assert not report["qualification"] and not report["training_eligible"] and not report["native_credit"]
    assert report["worlds_created"] == report["nodes_created"] == report["episodes"] == report["actor_calls"] == 0
    assert report["reward_replays"] == 0
    if fail_scene is None:
        assert returncode == 0 and report["passed"] and not report["errors"]
        assert called == list(geometry.SCENES) and len(report["scenes"]) == 3
    else:
        assert returncode == 1 and not report["passed"]
        assert called == ["open", "rooms"] and len(report["scenes"]) == 1
        assert report["errors"] == ["ValueError: synthetic scene failure"]


def test_cli_refuses_to_overwrite_an_existing_output_before_consuming_inputs(tmp_path):
    output = tmp_path / "old.json"
    output.write_bytes(b"preserved")
    with pytest.raises(FileExistsError):
        geometry.main(["--freeze", "a" * 40, "--output", str(output)])
    assert output.read_bytes() == b"preserved"
