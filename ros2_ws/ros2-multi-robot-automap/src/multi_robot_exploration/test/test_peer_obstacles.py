"""Check that observed peer bodies are distinct from static map evidence."""

import json
import math
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
import numpy as np
import pytest

from multi_robot_exploration.control import (
    PEER_BODY_RADIUS_M, grid_with_peers, peer_safety_radius,
)
from multi_robot_exploration.peer_obstacles import PeerObstacles, body_points, overlap_diagnostic
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


@pytest.mark.parametrize("distance,failed", [(.499, True), (.5, False), (.501, False)])
def test_overlap_diagnostic_preserves_strict_gate_and_exact_received_inputs(distance, failed):
    poses = {"tb1": (0., 0., .2, 1.), "tb2": (distance, 0., -.1, 1.)}
    odometry = {name: Odometry() for name in poses}
    transforms = {name: TransformStamped() for name in poses}
    for name in poses:
        odometry[name].header.stamp.sec = 1
        transforms[name].header.stamp.sec = 1
        transforms[name].header.stamp.nanosec = 200000000
        odometry[name].twist.twist.linear.x = .12
    result = overlap_diagnostic(poses, odometry, transforms, 1.1, .2)
    if not failed:
        assert result is None
        return
    assert result["pairs"] == [{"robots": ["tb1", "tb2"],
                                "centre_distance_m": distance, "threshold_m": .5}]
    assert result["received_inputs"]["tb1"]["estimated_map_pose"]["yaw"] == .2
    assert result["received_inputs"]["tb1"]["tf_source_stamp_sec"] == 1.
    assert result["received_inputs"]["tb1"]["odom_twist"]["linear"]["x"] == .12
    assert result["transport_epoch_missing"] and result["transport_sequence_missing"]
    odometry["tb1"].twist.twist.linear.z = float("nan")
    result = overlap_diagnostic(poses, odometry, transforms, 1.1, .2)
    assert result["received_inputs"]["tb1"]["odom_twist"]["linear"]["z"] is None
    json.dumps(result, allow_nan=False)


def peer_fixture():
    names = ["tb1", "tb2", "tb3"]
    published = []
    odometry = {name: Odometry() for name in names}
    transforms = {name: TransformStamped() for name in names}
    for name, x in zip(names, (0., .499, 4.)):
        odometry[name].header.stamp.sec = 1
        odometry[name].pose.pose.orientation.w = 1.
        odometry[name].pose.pose.position.x = x
        transforms[name].header.stamp.sec = 1
        transforms[name].header.stamp.nanosec = 200000000
        transforms[name].transform.rotation.w = 1.
        transforms[name].transform.translation.y = 2.
    node = SimpleNamespace(
        names=names, odometry=odometry, transforms=transforms, failed=False,
        mission_started=True, tf_source_lead_sec=.2,
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=1100000000)),
        get_logger=lambda: SimpleNamespace(error=lambda message: None),
        failure_publisher=SimpleNamespace(publish=published.append),
    )
    return node, published


def test_peer_callback_records_actual_transformed_gate_inputs_and_latches_failure():
    node, published = peer_fixture()
    PeerObstacles.publish_obstacles(node)
    assert node.failed and len(published) == 1
    failure = json.loads(published[0].data)
    assert failure["reason"] == "peer_body_envelopes_overlap"
    inputs = failure["diagnostic"]["received_inputs"]
    assert inputs["tb1"]["estimated_map_pose"] == {"x": 0., "y": 2., "yaw": 0.}
    assert inputs["tb2"]["estimated_map_pose"]["x"] == .499
    PeerObstacles.publish_obstacles(node)
    assert len(published) == 1


@pytest.mark.parametrize("fault", [
    "missing", "zero_odom", "stale_odom", "future_odom", "stale_tf", "future_tf"])
def test_peer_input_health_gate_still_precedes_overlap_diagnostic(fault):
    node, published = peer_fixture()
    if fault == "missing":
        del node.odometry["tb1"]
    elif fault in ("zero_odom", "stale_odom"):
        node.odometry["tb1"].header.stamp.sec = 0
        if fault == "stale_odom":
            node.odometry["tb1"].header.stamp.nanosec = 400000000
    elif fault == "future_odom":
        node.odometry["tb1"].header.stamp.sec = 2
    elif fault == "stale_tf":
        node.transforms["tb1"].header.stamp.sec = 0
    else:
        node.transforms["tb1"].header.stamp.sec = 2
    PeerObstacles.publish_obstacles(node)
    assert node.failed and len(published) == 1
    assert json.loads(published[0].data) == {
        "component": "peer_obstacles", "reason": "peer_state_unavailable"}


def test_evaluator_failure_truth_diagnostic_has_receipt_scope_and_no_feedback():
    from gazebo_msgs.msg import ModelStates
    from geometry_msgs.msg import Pose
    from std_msgs.msg import String

    now = [1.]
    evaluator = SimpleNamespace(
        finalized=False, model_state_message_count=0, robot_names=["tb1"], positions={},
        start_sim_time=None, _maybe_start=lambda stamp: None, _now=lambda: now[0],
        task_contract=None, finalize=lambda reason: setattr(evaluator, "finalized", True),
    )
    pose = Pose()
    pose.position.x = 3.
    pose.orientation.w = 1.
    TaskEvaluator._model_states_callback(evaluator, ModelStates(name=["tb1"], pose=[pose]))
    now[0] = 1.1
    failure = String(data='{"reason":"peer_body_envelopes_overlap"}')
    TaskEvaluator._control_failure_callback(evaluator, failure)
    diagnostic = evaluator.control_failure_truth_diagnostic
    assert evaluator.finalized and evaluator.control_failure == failure.data
    assert diagnostic["failure_received_sim_time_sec"] == 1.1
    latest = diagnostic["latest_model_states"]
    assert latest["received_sim_time_sec"] == 1.
    assert latest["source_stamp_missing"]
    assert latest["poses"]["tb1"]["position"]["x"] == 3.
    # A new model state cannot mutate the already-frozen diagnostic.
    pose.position.x = 9.
    TaskEvaluator._model_states_callback(evaluator, ModelStates(name=["tb1"], pose=[pose]))
    assert latest["poses"]["tb1"]["position"]["x"] == 3.


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
