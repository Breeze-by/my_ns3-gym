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
    assert phase_bucket("PARTIAL_COMPLETE") == "RALLY"


def test_collision_prevents_episode_success():
    assert episode_succeeded("task_complete", 0)
    assert not episode_succeeded("task_complete", 1)


def test_rally_mode_rejects_process_only_termination():
    assert episode_succeeded("target_found", 0)
    assert episode_succeeded("coverage_reached", 0)
    assert not episode_succeeded("target_found", 0, require_task_complete=True)
    assert not episode_succeeded(
        "coverage_reached", 0, require_task_complete=True
    )
    assert episode_succeeded("task_complete", 0, require_task_complete=True)
    assert not episode_succeeded(
        "partial_task_complete", 0, require_task_complete=True
    )


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


def test_collision_history_keeps_contact_names_without_changing_event_cooldown():
    from types import SimpleNamespace
    from multi_robot_exploration.task_evaluator import TaskEvaluator

    warnings = []
    node = SimpleNamespace(
        _now=lambda: 10.0, collision_messages={"tb1": 0},
        collision_last_time={"tb1": None}, collision_active={"tb1": False},
        collision_duration={"tb1": 0.0}, collision_last_event={"tb1": -math.inf},
        collision_events={"tb1": 0}, collision_cooldown=1.0,
        collision_history=[], task_phase="RALLY",
        get_logger=lambda: SimpleNamespace(warning=warnings.append),
    )
    contact = SimpleNamespace(collision1_name="tb1::base", collision2_name="wall::box")
    message = SimpleNamespace(states=[contact, contact])
    TaskEvaluator._collision_callback(node, message, "tb1")
    TaskEvaluator._collision_callback(node, message, "tb1")
    assert node.collision_events["tb1"] == 1
    assert node.collision_history == [{
        "robot": "tb1", "sim_time_sec": 10.0, "phase": "RALLY",
        "contacts": [("tb1::base", "wall::box")],
    }]
    assert "wall::box" in warnings[0]


def test_target_mode_terminates_only_after_central_consumption(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from std_msgs.msg import String
    from multi_robot_exploration import task_evaluator
    node=SimpleNamespace(task_phase="EXPLORE", start_sim_time=1., _now=lambda: 5.,
                         stop_on_target_found=True, finalize=Mock())
    monkeypatch.setattr(task_evaluator.rclpy, "shutdown", Mock())
    task_evaluator.TaskEvaluator._task_state_callback(node, String(data="FOUND"))
    node.finalize.assert_called_once_with("target_found")


def test_evaluation_starts_without_any_delivered_map():
    from collections import defaultdict
    from types import SimpleNamespace
    from multi_robot_exploration.task_evaluator import TaskEvaluator
    node=SimpleNamespace(start_sim_time=None, positions={"tb1": (0.,0.)}, robot_names=["tb1"],
                         task_phase="EXPLORE",
                         latest_map=None, visit_resolution=.2, visited=defaultdict(set),
                         phase_visited={"EXPLORE": defaultdict(set)}, episode_id="loss100",
                         get_logger=lambda: SimpleNamespace(info=lambda *args: None))
    TaskEvaluator._maybe_start(node, 5.)
    assert node.start_sim_time == 5.


@pytest.mark.parametrize("reason_first", [False, True])
def test_startup_failure_waits_for_native_start_and_drains_events(monkeypatch, reason_first):
    from collections import defaultdict
    from types import SimpleNamespace
    from unittest.mock import Mock
    from std_msgs.msg import String
    from multi_robot_exploration import task_evaluator

    clock = [5.0]
    node = SimpleNamespace(
        start_sim_time=None, positions={"tb1": (0., 0.)}, robot_names=["tb1"],
        task_phase="EXPLORE", failure_pending_since=None, task_failure_reason=None,
        visit_resolution=.2, visited=defaultdict(set),
        phase_visited={"EXPLORE": defaultdict(set)}, episode_id="empty_battery",
        get_logger=lambda: SimpleNamespace(info=lambda *args: None),
        _now=lambda: clock[0], stop_on_task_complete=True, finalize=Mock(),
        failed_robots=set(), required_robot_names={"tb1"},
        battery_states={"tb1": {"robot": "tb1", "mode": "FAILED", "energy": 0.}},
        _map_metrics=lambda: {}, coverage_threshold=0, max_duration=300,
    )
    shutdown = Mock()
    monkeypatch.setattr(task_evaluator.rclpy, "shutdown", shutdown)
    state = lambda: task_evaluator.TaskEvaluator._task_state_callback(node, String(data="FAILED"))
    reason = lambda: task_evaluator.TaskEvaluator._task_failure_callback(node, String(data="all_robots_failed"))
    for callback in ([reason, state] if reason_first else [state, reason]):
        callback()
    task_evaluator.TaskEvaluator._timer_callback(node)
    node.finalize.assert_not_called()
    task_evaluator.TaskEvaluator._maybe_start(node, clock[0])
    task_evaluator.TaskEvaluator._robot_failure_callback(node, String(data='{"robot":"tb1"}'))
    clock[0] = 5.4
    task_evaluator.TaskEvaluator._timer_callback(node)
    node.finalize.assert_not_called()
    clock[0] = 5.5
    task_evaluator.TaskEvaluator._timer_callback(node)
    assert node.failed_robots == {"tb1"}
    assert node.task_failure_reason == "all_robots_failed"
    node.finalize.assert_called_once_with("mission_failed")
    shutdown.assert_called_once()


@pytest.mark.parametrize("late_state,horizon", [(None, 300.), (None, 2.), ({}, 300.),
    ({"robot": "tb1", "mode": "ACTIVE", "energy": 0.}, 300.)])
def test_failure_drains_late_native_battery_without_inference_or_unbounded_wait(monkeypatch, late_state, horizon):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock
    from std_msgs.msg import String
    from multi_robot_exploration import task_evaluator as module
    clock = [5.]
    node = SimpleNamespace(start_sim_time=5., failure_pending_since=5., task_phase="FAILED",
        robot_names=["tb1", "tb2"], failed_robots={"tb1", "tb2"}, required_robot_names=set(),
        battery_states={"tb1": late_state or {}, "tb2": {"robot": "tb2", "mode": "FAILED", "energy": 0.}},
        battery_message_counts={"tb1": int(bool(late_state)), "tb2": 1}, max_duration=horizon,
        _now=lambda: clock[0], finalize=Mock())
    shutdown = Mock(); monkeypatch.setattr(module.rclpy, "shutdown", shutdown)
    clock[0] = 5.6
    module.TaskEvaluator._timer_callback(node)
    node.finalize.assert_not_called()
    module.TaskEvaluator._task_state_callback(node, String(data="FAILED"))
    assert node.failure_pending_since == 5.
    if late_state is not None:
        message = String(data=json.dumps({"robot": "tb1", "mode": "FAILED", "energy": 0.}))
        module.TaskEvaluator._battery_callback(node, message, "tb1")
        assert node.battery_message_counts["tb1"] == int(bool(late_state)) + 1
    else:
        clock[0] = 5. + min(horizon, module.STATE_TTL_SEC["battery_state"])
    module.TaskEvaluator._timer_callback(node)
    node.finalize.assert_called_once_with("mission_failed")
    shutdown.assert_called_once()
    assert node.battery_states["tb1"] == ({} if late_state is None else json.loads(message.data))


def test_late_failure_snapshot_is_complete_and_irreversible():
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock
    from std_msgs.msg import String
    from multi_robot_exploration.task_evaluator import TaskEvaluator

    logger = Mock()
    node = SimpleNamespace(
        robot_names=["tb1", "tb2"], failed_robots=set(),
        required_robot_names={"tb1", "tb2"}, get_logger=lambda: logger,
    )
    latest = String(data=json.dumps({"robot": "tb2", "failed_robots": ["tb1", "tb2"]}))
    TaskEvaluator._robot_failure_callback(node, latest)
    assert node.failed_robots == {"tb1", "tb2"}
    assert node.required_robot_names == set()
    for message in (String(data='{"robot":"tb1","failed_robots":["tb1"]}'), latest):
        TaskEvaluator._robot_failure_callback(node, message)
        assert node.failed_robots == {"tb1", "tb2"}
        assert node.required_robot_names == set()
    logger.error.assert_not_called()


@pytest.mark.parametrize("event", [
    {"robot": "tb1", "failed_robots": "tb1"},
    {"robot": "tb1", "failed_robots": ["tb2"]},
    {"robot": "tb1", "failed_robots": ["tb1", "foreign"]},
    {"robot": "tb1", "failed_robots": ["tb1", {}]},
    {"robot": "foreign"},
])
def test_invalid_failure_snapshot_does_not_partially_isolate(event):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock
    from std_msgs.msg import String
    from multi_robot_exploration.task_evaluator import TaskEvaluator

    logger = Mock()
    node = SimpleNamespace(
        robot_names=["tb1", "tb2"], failed_robots=set(),
        required_robot_names={"tb1", "tb2"}, get_logger=lambda: logger,
    )
    TaskEvaluator._robot_failure_callback(node, String(data=json.dumps(event)))
    assert node.failed_robots == set()
    assert node.required_robot_names == {"tb1", "tb2"}
    logger.error.assert_called_once()


def native_hold_node():
    from types import SimpleNamespace
    from unittest.mock import Mock
    return SimpleNamespace(
        start_sim_time=90., _now=lambda: 105., task_phase="RALLY",
        robot_names=["tb1"], required_robot_names={"tb1"}, failed_robots=set(),
        positions={"tb1": (0., 0.)}, velocities={"tb1": (0., 0.)},
        rally_assignments={"tb1": {"x": 0., "y": 0.}},
        rally_position_tolerance=.35, rally_linear_tolerance=.05,
        rally_angular_tolerance=.1, rally_hold_sec=5.,
        battery_states={"tb1": {"mode": "ACTIVE", "energy": 40.}},
        battery_message_counts={"tb1": 0},
        native_model_state_received_at=None, native_rally_hold=None,
        native_rally_qualified_hold=None, coordinator_completion_time=None,
        completion_time=None, max_duration=300., stop_on_task_complete=True,
        stop_on_target_found=False, finalize=Mock(),
    )


@pytest.mark.parametrize("violation", ["angular", "linear", "position", "nonfinite", "missing_body"])
def test_native_completion_rejects_a_transient_between_timer_ticks(monkeypatch, violation):
    from unittest.mock import Mock
    from std_msgs.msg import String
    from multi_robot_exploration import task_evaluator as module
    node = native_hold_node()
    monkeypatch.setattr(module.rclpy, "shutdown", Mock())
    update = lambda t, names={"tb1"}: module.TaskEvaluator._update_native_rally_hold(node, t, names)
    for t in (100., 101., 102., 103., 104., 104.9):
        update(t)
    if violation == "angular": node.velocities["tb1"] = (0., .1931509963150803)
    if violation == "linear": node.velocities["tb1"] = (.051, 0.)
    if violation == "position": node.positions["tb1"] = (.36, 0.)
    if violation == "nonfinite": node.velocities["tb1"] = (0., math.nan)
    update(104.95, set() if violation == "missing_body" else {"tb1"})
    node.positions["tb1"] = (0., 0.)
    node.velocities["tb1"] = (0., 0.)
    module.TaskEvaluator._task_state_callback(node, String(data="COMPLETE"))
    assert node.coordinator_completion_time == 15. and node.completion_time is None
    node.finalize.assert_not_called()
    for t in (105., 106., 107., 108., 109., 109.99): update(t)
    node.finalize.assert_not_called()
    update(110.)
    assert node.completion_time == 20.
    assert node.native_rally_qualified_hold["observed_duration_sec"] == 5.
    assert node.native_rally_qualified_hold["start_observer_sim_time_sec"] == 105.
    node.finalize.assert_called_once_with("task_complete")


def test_native_observation_gap_cannot_extend_the_hold(monkeypatch):
    from unittest.mock import Mock
    from multi_robot_exploration import task_evaluator as module
    monkeypatch.setattr(module.rclpy, "shutdown", Mock())
    node = native_hold_node()
    node.task_phase = "COMPLETE"
    node.coordinator_completion_time = 10.
    update = lambda t: module.TaskEvaluator._update_native_rally_hold(node, t, {"tb1"})
    for t in (100., 101., 102., 103., 104.): update(t)
    update(106.01)
    assert node.native_rally_hold["start_observer_sim_time_sec"] == 106.01
    node.finalize.assert_not_called()


def test_native_hold_uses_current_assignment_and_battery_state():
    from std_msgs.msg import String
    from multi_robot_exploration.task_evaluator import TaskEvaluator
    node = native_hold_node()
    TaskEvaluator._update_native_rally_hold(node, 100., {"tb1"})
    event = {"poses": node.rally_assignments, "position_tolerance_m": .35,
             "linear_tolerance_mps": .05, "angular_tolerance_radps": .1, "hold_sec": 5.}
    TaskEvaluator._rally_assignments_callback(node, String(data=json.dumps(event)))
    assert node.native_rally_hold is not None  # Identical publication preserves the window.
    event["poses"] = {"tb1": {"x": 1., "y": 0.}}
    TaskEvaluator._rally_assignments_callback(node, String(data=json.dumps(event)))
    assert node.native_rally_hold is None
    node.positions["tb1"] = (1., 0.)
    TaskEvaluator._update_native_rally_hold(node, 101., {"tb1"})
    TaskEvaluator._battery_callback(node, String(data='{"robot":"tb1","mode":"RETURNING","energy":30}'), "tb1")
    assert node.native_rally_hold is None
    node.failed_robots = {"tb1"}
    TaskEvaluator._rally_assignments_callback(node, String(data=json.dumps(event)))
    assert node.required_robot_names == set()


def test_native_completion_never_extends_the_original_horizon(monkeypatch):
    from unittest.mock import Mock
    from multi_robot_exploration import task_evaluator as module
    monkeypatch.setattr(module.rclpy, "shutdown", Mock())
    node = native_hold_node()
    node.task_phase = "COMPLETE"
    node.coordinator_completion_time = 299.
    for t in (386., 387., 388., 389., 390., 391.):
        module.TaskEvaluator._update_native_rally_hold(node, t, {"tb1"})
    node.finalize.assert_not_called()
    assert node.completion_time is None


def test_partial_completion_qualifies_only_the_healthy_roster(monkeypatch):
    from unittest.mock import Mock
    from multi_robot_exploration import task_evaluator as module
    monkeypatch.setattr(module.rclpy, "shutdown", Mock())
    node = native_hold_node()
    node.robot_names.append("tb2")
    node.failed_robots = {"tb2"}
    node.task_phase = "PARTIAL_COMPLETE"
    node.coordinator_completion_time = 10.
    for t in range(100, 106):
        module.TaskEvaluator._update_native_rally_hold(node, float(t), {"tb1"})
    node.finalize.assert_called_once_with("partial_task_complete")
    assert node.native_rally_qualified_hold["required_robot_names"] == ["tb1"]
