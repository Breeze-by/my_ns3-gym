import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from multi_robot_exploration.control import assign_rally_poses
from multi_robot_exploration.task_evaluator import (
    TruthGrid,
    compare_occupancy_grid,
    episode_succeeded,
    load_truth_grid,
    phase_bucket,
    visited_overlap_ratio,
)


def test_truth_grid_uses_state_pose_and_height_slice(tmp_path):
    world = tmp_path / "test.world"
    world.write_text(
        """<sdf version='1.7'><world name='test'>
        <model name='walls'><pose>50 50 0 0 0 0</pose><link name='wall'>
        <collision name='low'><pose>0 0 0.5 0 0 0</pose><geometry><box>
        <size>2 1 1</size></box></geometry></collision>
        <collision name='high'><pose>0 0 2 0 0 0</pose><geometry><box>
        <size>1 1 1</size></box></geometry></collision>
        </link></model><state world_name='test'><model name='walls'>
        <pose>2 3 0 0 0 0</pose></model></state></world></sdf>"""
    )
    truth = load_truth_grid(world, resolution=0.5, slice_height=0.2)
    assert truth.rectangle_count == 1
    assert truth.origin_x == 1.0
    assert truth.origin_y == 2.5
    assert truth.occupied.shape == (2, 4)
    assert np.all(truth.occupied)


def test_occupancy_metrics_penalize_unknown_cells():
    truth = TruthGrid(
        occupied=np.array([[False, True], [False, True]]),
        origin_x=0.0,
        origin_y=0.0,
        resolution=1.0,
        rectangle_count=1,
        unsupported_collision_count=0,
    )
    metrics = compare_occupancy_grid(
        truth,
        data=[0, 100, -1, 0],
        width=2,
        height=2,
        resolution=1.0,
        origin=(0.0, 0.0),
    )
    assert metrics["known_coverage_ratio"] == 0.75
    assert metrics["correct_coverage_ratio"] == 0.5
    assert metrics["correct_free_coverage_ratio"] == 0.5
    assert metrics["observed_accuracy"] == 2 / 3
    assert metrics["occupied_iou"] == 0.5


def test_overlap_ratio_matches_research_definition():
    visited = {"tb1": {(0, 0), (1, 0)}, "tb2": {(1, 0), (2, 0)}}
    assert visited_overlap_ratio(visited) == 1 / 3


def test_task_states_map_to_stable_metric_phases():
    assert phase_bucket("EXPLORE") == "EXPLORE"
    assert phase_bucket("FOUND_UNCONFIRMED") == "EXPLORE"
    assert phase_bucket("FOUND") == "FOUND"
    assert phase_bucket("RALLY") == "RALLY"
    assert phase_bucket("COMPLETE") == "RALLY"


def test_collision_prevents_episode_success():
    assert episode_succeeded("task_complete", 0)
    assert not episode_succeeded("task_complete", 1)


@pytest.mark.parametrize(
    "world_name",
    ("p1c_open.world", "p1c_rooms.world", "p1c_corridors.world"),
)
def test_generalization_world_is_supported_connected_and_spawn_safe(world_name):
    worlds = Path(__file__).resolve().parents[2] / "multi_robot" / "worlds"
    truth = load_truth_grid(worlds / world_name)

    assert truth.unsupported_collision_count == 0
    assert ndimage.label(~truth.occupied)[1] == 1

    clearance = ndimage.distance_transform_edt(~truth.occupied)
    for x, y in ((0.0, -0.45), (0.0, 0.45), (0.45, 0.0)):
        column = int((x - truth.origin_x) / truth.resolution)
        row = int((y - truth.origin_y) / truth.resolution)
        assert clearance[row, column] * truth.resolution >= 0.45


def test_p2d_scenario_targets_are_free_and_rallyable():
    workspace = Path(__file__).resolve().parents[3]
    worlds = workspace / "src" / "multi_robot" / "worlds"
    with (workspace / "scripts" / "p2d_scenarios.json").open() as source:
        scenarios = json.load(source)["scenarios"]
    robots = {"tb1": (0.0, -0.45), "tb2": (0.0, 0.45), "tb3": (0.45, 0.0)}

    for scenario in scenarios:
        truth = load_truth_grid(worlds / scenario["world"])
        target = (scenario["target_x"], scenario["target_y"])
        column = int((target[0] - truth.origin_x) / truth.resolution)
        row = int((target[1] - truth.origin_y) / truth.resolution)
        assert not truth.occupied[row, column]
        raw_grid = np.where(truth.occupied, 100, 0).astype(np.int8)
        assignments = assign_rally_poses(
            raw_grid,
            truth.resolution,
            (truth.origin_x, truth.origin_y),
            robots,
            target,
        )
        assert len(assignments) == 3
        poses = list(assignments.values())
        assert min(
            math.dist((a.x, a.y), (b.x, b.y))
            for index, a in enumerate(poses)
            for b in poses[index + 1:]
        ) >= 0.8
