"""Check that observed peer bodies are distinct from static map evidence."""

import math
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from multi_robot_exploration.control import (
    PEER_BODY_RADIUS_M, grid_with_peers, peer_safety_radius,
)
from multi_robot_exploration.peer_obstacles import body_points
from multi_robot_exploration.task_evaluator import TaskEvaluator


def test_body_points_fill_full_peer_instead_of_only_lidar_cylinder():
    points = body_points([(1., 0., 0.)])
    assert np.min(np.linalg.norm(points[:, :2] - (1., 0.), axis=1)) < .03
    assert np.max(np.linalg.norm(points[:, :2] - (1., 0.), axis=1)) > .4
    assert len(points) > 100


def test_peer_source_age_increases_conservative_envelope():
    assert peer_safety_radius(.2) > peer_safety_radius(0)


def test_peer_radius_contains_actual_base_collision_corners():
    model = Path(__file__).resolve().parents[2] / "multi_robot/models/turtlebot3_waffle/model.sdf"
    collision = ET.parse(model).find(".//collision[@name='base_collision']")
    x, y, *_ = map(float, collision.findtext("pose").split())
    sx, sy, _ = map(float, collision.findtext("geometry/box/size").split())
    assert max(math.hypot(x + dx * sx / 2, y + dy * sy / 2)
               for dx in (-1, 1) for dy in (-1, 1)) < PEER_BODY_RADIUS_M


def test_peer_overlay_preserves_static_obstacles_and_input_grid():
    original = np.zeros((30, 30), dtype=np.int16)
    original[0, 0] = 100
    result = grid_with_peers(original, .1, (0., 0.), [(1.5, 1.5, 0.)])
    assert result[0, 0] == 100
    assert result[15, 15] == 100
    assert original[15, 15] == 0


def test_no_peer_has_no_marking_points():
    assert body_points([]).shape == (0, 3)


def test_inside_peer_envelope_does_not_report_free_rays():
    assert len(body_points([(0., 0., 0.)])) > 100


def test_evaluator_callback_returns_without_shutting_down_context(monkeypatch):
    called = []
    monkeypatch.setattr("rclpy.shutdown", lambda: pytest.fail("callback context shutdown"))
    evaluator = SimpleNamespace(
        finalized=False, task_contract=None, start_sim_time=0., _now=lambda: 20.,
        _map_metrics=lambda: {"correct_free_coverage_ratio": .2},
        coverage_threshold=.9, max_duration=20., collision_events={"tb1": 0},
        collision_messages={"tb1": 10}, control_failure="", finalize=called.append,
    )
    TaskEvaluator._timer_callback(evaluator)
    assert called == ["timeout"]
