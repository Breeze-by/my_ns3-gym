from pathlib import Path
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import ndimage

from multi_robot_exploration.task_evaluator import (
    TruthGrid,
    compare_occupancy_grid,
    load_truth_grid,
    visited_overlap_ratio,
    evaluation_termination_reason,
    TaskEvaluator,
)
from multi_robot_exploration import task_evaluator


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
    for x, y in ((0.0, -0.45), (0.0, 0.45), (0.45, 0.0), (-0.45, 0.0)):
        column = int((x - truth.origin_x) / truth.resolution)
        row = int((y - truth.origin_y) / truth.resolution)
        assert clearance[row, column] * truth.resolution >= 0.45


@pytest.mark.parametrize(
    "elapsed,collisions,monitored,expected",
    [(179.9, 0, True, "coverage_reached"),
     (180.0, 0, True, "timeout"), (181.0, 0, True, "timeout"),
     (10.0, 1, True, "collision"),
     (10.0, 0, False, "collision_monitoring_unavailable")],
)
def test_coverage_success_respects_deadline_and_safety(elapsed, collisions, monitored, expected):
    assert evaluation_termination_reason(.91, .9, elapsed, 180., collisions, monitored) == expected


def test_navigation_failure_prevents_coverage_success():
    assert evaluation_termination_reason(
        .91, .9, 10., 180., 0, True, "navigation_failure",
    ) == "navigation_failure"


def test_late_coverage_does_not_create_a_milestone():
    evaluator = SimpleNamespace(
        start_sim_time=0., max_duration=180., _now=lambda: 181.,
        _map_metrics=lambda: {"correct_free_coverage_ratio": .91},
        coverage_times={.75: None, .8: None, .9: None, .95: None},
    )
    TaskEvaluator._update_coverage_times(evaluator)
    assert evaluator.coverage_times[.9] is None


def test_result_publication_keeps_existing_evidence(tmp_path):
    evaluator = SimpleNamespace(
        output_dir=tmp_path, episode_id="immutable_result",
        get_logger=lambda: SimpleNamespace(info=lambda *args: None),
    )
    result = {"schema_version": 3, "success": False, "robots": {}}
    TaskEvaluator._write_outputs(evaluator, result)
    original = (tmp_path / "immutable_result.json").read_bytes()
    assert json.loads(original)["schema_version"] == 3
    assert (tmp_path / "immutable_result.csv").is_file()
    with pytest.raises(FileExistsError):
        TaskEvaluator._write_outputs(evaluator, {**result, "success": True})
    assert (tmp_path / "immutable_result.json").read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("finalize_error", [None, OSError("result disk unavailable")])
def test_main_cleans_resources_even_when_result_finalization_fails(monkeypatch, finalize_error):
    lifecycle = SimpleNamespace(context_live=True, node_live=True, executor_live=True,
                                finalize_called=False, shutdown_timeout=None)

    class Evaluator:
        finalized = False

        def finalize(self, reason):
            assert lifecycle.node_live and lifecycle.context_live
            lifecycle.finalize_called = True
            if finalize_error:
                raise finalize_error

        def destroy_node(self):
            assert not lifecycle.executor_live
            lifecycle.node_live = False

    evaluator = Evaluator()

    class Executor:
        def add_node(self, node):
            assert node is evaluator

        def spin_once(self, timeout_sec):
            evaluator.finalized = True

        def shutdown(self, timeout_sec):
            lifecycle.shutdown_timeout = timeout_sec
            lifecycle.executor_live = False
            return True

    def shutdown_context():
        assert not lifecycle.node_live and not lifecycle.executor_live
        lifecycle.context_live = False

    monkeypatch.setattr(task_evaluator, "TaskEvaluator", lambda: evaluator)
    monkeypatch.setattr(task_evaluator, "SingleThreadedExecutor", Executor)
    monkeypatch.setattr(task_evaluator.rclpy, "init", lambda **kwargs: None)
    monkeypatch.setattr(task_evaluator.rclpy, "ok", lambda: lifecycle.context_live)
    monkeypatch.setattr(task_evaluator.rclpy, "shutdown", shutdown_context)
    if finalize_error:
        with pytest.raises(OSError, match="result disk unavailable"):
            task_evaluator.main()
    else:
        task_evaluator.main()
    assert lifecycle.finalize_called
    assert lifecycle.shutdown_timeout == 1.0
    assert not lifecycle.node_live and not lifecycle.executor_live and not lifecycle.context_live


def test_main_preserves_external_shutdown_and_still_releases_resources(monkeypatch):
    lifecycle = SimpleNamespace(context_live=True, executor_closed=False, node_destroyed=False)

    class Evaluator:
        finalized = False

        def finalize(self, reason):
            assert reason == "shutdown"

        def destroy_node(self):
            assert lifecycle.executor_closed
            lifecycle.node_destroyed = True

    class Executor:
        def add_node(self, node):
            pass

        def spin_once(self, timeout_sec):
            lifecycle.context_live = False
            raise task_evaluator.ExternalShutdownException()

        def shutdown(self, timeout_sec):
            lifecycle.executor_closed = True
            return True

    monkeypatch.setattr(task_evaluator, "TaskEvaluator", Evaluator)
    monkeypatch.setattr(task_evaluator, "SingleThreadedExecutor", Executor)
    monkeypatch.setattr(task_evaluator.rclpy, "init", lambda **kwargs: None)
    monkeypatch.setattr(task_evaluator.rclpy, "ok", lambda: lifecycle.context_live)
    monkeypatch.setattr(
        task_evaluator.rclpy, "shutdown", lambda: pytest.fail("context already stopped")
    )
    task_evaluator.main()
    assert lifecycle.executor_closed and lifecycle.node_destroyed
