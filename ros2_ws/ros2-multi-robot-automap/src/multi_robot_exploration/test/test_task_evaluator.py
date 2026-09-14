import numpy as np

from multi_robot_exploration.task_evaluator import (
    TruthGrid,
    compare_occupancy_grid,
    load_truth_grid,
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
