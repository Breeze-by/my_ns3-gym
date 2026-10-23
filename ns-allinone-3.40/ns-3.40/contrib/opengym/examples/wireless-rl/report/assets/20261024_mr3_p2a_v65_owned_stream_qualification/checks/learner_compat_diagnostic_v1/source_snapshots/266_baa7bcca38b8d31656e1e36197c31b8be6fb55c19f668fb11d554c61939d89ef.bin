"""Artificial measurement counterexamples, without a World, Node or episode.

These tests characterize the current endpoint mapper; they do not repair it or
relax the frozen evaluator.  An optimistic surface-only map is an evaluator-only
mathematical construction, never an actor/navigation input.  No task scene,
saved run, random scan, motion integration or private reward journal is read.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import mr3_proxy2d_world, mr3_task_contract, task_evaluator
from multi_robot_exploration.mr3_proxy2d_world import ProxyWorld, ray_box_ranges
from multi_robot_exploration.mr3_task_contract import (
    _rasterize, compare_contract_occupancy_grid,
)
from multi_robot_exploration.task_evaluator import mr3_quality_pass


RESOLUTION = .05
QUALITY = {
    "min_observed_accuracy": .95,
    "min_occupied_iou": .20,
    "max_false_free_ratio": .02,
}


def artificial_truth(rectangles, bounds):
    """Reuse the unchanged positive-area evaluator on explicit small boxes."""
    occupied = _rasterize(rectangles, bounds, RESOLUTION)
    return SimpleNamespace(
        occupied=occupied, roi_mask=np.ones(occupied.shape, dtype=bool),
        origin_x=bounds[0], origin_y=bounds[1], resolution=RESOLUTION,
    )


def metrics(truth, grid):
    height, width = grid.shape
    return compare_contract_occupancy_grid(
        truth, grid, width, height, RESOLUTION,
        (truth.origin_x, truth.origin_y),
    )


def measurement_container(truth, angles=(0.,)):
    """Only fields read by the two existing scan measurement methods.

    This is deliberately not a ProxyWorld instance: its constructor, reset,
    sensing, random generators, plant, asset loader and advance never execute.
    """
    state = SimpleNamespace(
        _laser={"frame_offset": (0., 0.), "frame_yaw": 0., "range_max": 10.},
        _angles=np.asarray(angles, dtype=float),
        origin=(truth.origin_x, truth.origin_y), resolution=RESOLUTION,
        shape=truth.occupied.shape,
        _maps={"sensor": np.full(truth.occupied.shape, -1, dtype=np.int8)},
        _last_ray_cells={},
    )
    state._sensor_pose = lambda pose: ProxyWorld._sensor_pose(state, pose)
    return state


def integrate_measurement(state, pose, ranges):
    ProxyWorld._integrate_scan(state, "sensor", pose, np.asarray(ranges, dtype=float))
    return state._maps["sensor"].copy()


def rectangle_surface_bound(thickness):
    """Tight noiseless bound for this isolated, axis-aligned artificial box.

    Both rectangle boundaries are strictly inside their corresponding cells.
    A first return from any exterior origin belongs to a perimeter cell; no
    interior cell can be an endpoint. Every perimeter cell can be hit from an
    exterior origin, so the optimistic endpoint set is attainable in this
    unrestricted static measurement model. Known free space is supplied only
    to make this evaluator-only bound optimistic. It is not a sensor map.
    """
    truth = artificial_truth([(1.01, 1.01 + thickness / 2., 0., 2., thickness)],
                             (-.5, 0., 2.5, 2.5))
    occupied = truth.occupied
    interior = np.zeros_like(occupied)
    interior[1:-1, 1:-1] = (
        occupied[1:-1, 1:-1] & occupied[:-2, 1:-1] & occupied[2:, 1:-1]
        & occupied[1:-1, :-2] & occupied[1:-1, 2:]
    )
    surface = occupied & ~interior
    optimistic = np.where(occupied, -1, 0).astype(np.int8)
    optimistic[surface] = 100
    result = metrics(truth, optimistic)
    return {
        "rectangle_size_m": [2., thickness],
        "occupied_cells": int(occupied.sum()),
        "surface_endpoint_cells": int(surface.sum()),
        "strict_interior_cells": int(interior.sum()),
        "tight_noiseless_endpoint_iou_upper_bound": float(surface.sum() / occupied.sum()),
        "optimistic_metrics": result,
        "quality_only_pass": mr3_quality_pass(result, QUALITY),
        "scope": "isolated artificial box; all exterior viewpoints and perfect free coverage; not a task or actual-scene bound",
    }


def aligned_boundary_counterexample():
    rectangle = (.375, .5, 0., .25, .5)
    truth = artificial_truth([rectangle], (0., 0., 1., 1.))
    cases = []
    for side, origin, direction in (
        ("lower_x_face", (0., .525), (1., 0.)),
        ("upper_x_face", (.75, .525), (-1., 0.)),
    ):
        ranges = ray_box_ranges(origin, np.asarray([direction]), [rectangle], 10.)
        state = measurement_container(truth)
        grid = integrate_measurement(state, (*origin, math.atan2(direction[1], direction[0])), ranges)
        endpoint_xy = state._last_ray_cells["sensor"][0, 2:4].astype(int)
        x, y = map(int, endpoint_xy)
        cases.append({
            "side": side, "origin_m": list(origin), "range_m": float(ranges[0]),
            "endpoint_cell_xy": [x, y],
            "endpoint_truth_occupied": bool(truth.occupied[y, x]),
            "endpoint_map_value": int(grid[y, x]),
            "metrics": metrics(truth, grid),
        })
    return cases


def positive_range_error_counterexample():
    # The true near face is 1 mm before a cell boundary. A 2 mm positive
    # measurement error crosses that boundary, without any physical ray having
    # traversed the true box. Two artificial rows make the denominator explicit.
    rectangle = (.399, .5, 0., .2, .5)
    truth = artificial_truth([rectangle], (0., 0., 1., 1.))
    state = measurement_container(truth)
    clean = integrate_measurement(state, (0., .325, 0.), [.299])
    first_noisy = integrate_measurement(state, (0., .325, 0.), [.301])
    noisy = integrate_measurement(state, (0., .525, 0.), [.301])
    return {
        "actual_range_m": .299, "measured_range_m": .301,
        "range_error_m": .002, "native_declared_noise_std_m": .01,
        "boundary_cell_xy": [5, 6],
        "clean_boundary_cell": int(clean[6, 5]),
        "next_noisy_boundary_cell": int(first_noisy[6, 5]),
        "two_measurement_metrics": metrics(truth, noisy),
        "scope": "prescribed artificial measurements, not a stochastic frequency estimate or a V24 causal attribution",
    }


def artificial_diagnostic():
    return {
        "schema": "mr3-proxy2d-artificial-mapping-quality-v1",
        "scope": "pure finite measurement kernels; no World/Node/actor/episode or real task replay",
        "production_modified": False, "thresholds_modified": False,
        "actual_scene_impossibility_claim": False,
        "native_or_task_qualification": False,
        "quality_gates": dict(QUALITY),
        "thick_box": rectangle_surface_bound(.8),
        "thin_box_control": rectangle_surface_bound(.1),
        "aligned_boundary": aligned_boundary_counterexample(),
        "positive_range_error": positive_range_error_counterexample(),
        "source_sha256": {
            str(Path(module.__file__).resolve()): hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (mr3_proxy2d_world, mr3_task_contract, task_evaluator)
        },
    }


def test_perfect_artificial_volume_map_still_passes_original_quality_kernel():
    truth = artificial_truth([(1.01, 1.41, 0., 2., .8)], (-.5, 0., 2.5, 2.5))
    grid = (truth.occupied * 100).astype(np.int8)
    result = metrics(truth, grid)
    assert result["occupied_iou"] == result["correct_free_coverage_ratio"] == 1.
    assert result["false_free_ratio"] == 0.
    assert mr3_quality_pass(result, QUALITY)


def test_thick_box_tight_surface_bound_fails_without_lowering_any_gate():
    result = rectangle_surface_bound(.8)
    assert result["occupied_cells"] == 41 * 17
    assert result["surface_endpoint_cells"] == 2 * (41 + 17) - 4
    assert result["strict_interior_cells"] == 39 * 15
    assert result["tight_noiseless_endpoint_iou_upper_bound"] == pytest.approx(112 / 697)
    assert result["optimistic_metrics"]["correct_free_coverage_ratio"] == 1.
    assert result["optimistic_metrics"]["observed_accuracy"] == 1.
    assert result["optimistic_metrics"]["false_free_ratio"] == 0.
    assert not result["quality_only_pass"]


def test_thin_box_control_does_not_claim_all_proxy_tasks_are_impossible():
    result = rectangle_surface_bound(.1)
    assert result["occupied_cells"] == 41 * 3
    assert result["surface_endpoint_cells"] == 84
    assert result["quality_only_pass"]


def test_actual_ray_and_scan_kernels_only_observe_front_surface_of_thick_box():
    rectangle = (1.01, 1.41, 0., 2., .8)
    truth = artificial_truth([rectangle], (-.5, 0., 2.5, 2.5))
    origin = np.array((1.01, .25))
    targets = np.column_stack((np.linspace(.015, 2.005, 100), np.full(100, 1.01)))
    directions = targets - origin
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    ranges = ray_box_ranges(origin, directions, [rectangle], 10.)
    state = measurement_container(truth, np.arctan2(directions[:, 1], directions[:, 0]))
    grid = integrate_measurement(state, (*origin, 0.), ranges)
    occupied_rows = np.flatnonzero(truth.occupied.any(axis=1))
    predicted = grid == 100
    assert predicted.sum() == 41
    assert np.all(truth.occupied[predicted])
    assert np.all(np.flatnonzero(predicted.any(axis=1)) == occupied_rows[0])
    assert not np.any(predicted[occupied_rows[1:]])


def test_exact_upper_face_endpoint_is_assigned_to_adjacent_truth_free_cell():
    lower, upper = aligned_boundary_counterexample()
    assert lower["range_m"] == upper["range_m"] == .25
    assert lower["endpoint_cell_xy"] == [5, 10]
    assert upper["endpoint_cell_xy"] == [10, 10]
    assert lower["endpoint_truth_occupied"]
    assert not upper["endpoint_truth_occupied"]
    assert upper["endpoint_map_value"] == 100
    assert lower["metrics"]["occupied_iou"] > upper["metrics"]["occupied_iou"] == 0.


def test_two_mm_range_error_can_clear_positive_area_boundary_cells():
    result = positive_range_error_counterexample()
    assert result["clean_boundary_cell"] == 100
    assert result["next_noisy_boundary_cell"] == 0
    measured = result["two_measurement_metrics"]
    assert measured["truth_occupied_cell_count"] == 50
    assert measured["false_free_cell_count"] == 2
    assert measured["false_free_ratio"] == .04 > QUALITY["max_false_free_ratio"]


def test_diagnostic_does_not_promote_artificial_results_to_task_qualification():
    result = artificial_diagnostic()
    assert not result["production_modified"]
    assert not result["thresholds_modified"]
    assert not result["actual_scene_impossibility_claim"]
    assert not result["native_or_task_qualification"]
    assert len(result["source_sha256"]) == 3
    json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # The root's actual-wait wrapper chooses a new evidence destination.
    with args.output.open("x") as handle:
        json.dump(artificial_diagnostic(), handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
