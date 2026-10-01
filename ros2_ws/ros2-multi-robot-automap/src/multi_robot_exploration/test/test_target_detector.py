import math

import numpy as np

from multi_robot_exploration.target_detector import (
    line_of_sight_clear,
    target_visible,
    update_confirmation,
)
from multi_robot_exploration.task_evaluator import TruthGrid


def truth_grid():
    return TruthGrid(
        occupied=np.zeros((10, 10), dtype=bool),
        origin_x=0.0,
        origin_y=0.0,
        resolution=1.0,
        rectangle_count=0,
        unsupported_collision_count=0,
    )


def test_visibility_requires_range_field_of_view_and_clear_path():
    truth = truth_grid()

    assert target_visible((1.5, 1.5, 0.0), (3.5, 1.5), truth, 3.0, math.pi / 2)
    assert not target_visible(
        (1.5, 1.5, 0.0), (5.5, 1.5), truth, 3.0, math.pi / 2
    )
    assert not target_visible(
        (1.5, 1.5, math.pi), (3.5, 1.5), truth, 3.0, math.pi / 2
    )

    truth.occupied[1, 2] = True
    assert not line_of_sight_clear(truth, (1.5, 1.5), (3.5, 1.5))
    assert not target_visible(
        (1.5, 1.5, 0.0), (3.5, 1.5), truth, 3.0, math.pi / 2
    )


def test_confirmation_requires_consecutive_frames_and_resets():
    streaks = {"tb1": 0, "tb2": 0}

    assert update_confirmation(streaks, {"tb1"}, 3) is None
    assert update_confirmation(streaks, set(), 3) is None
    assert update_confirmation(streaks, {"tb1"}, 3) is None
    assert update_confirmation(streaks, {"tb1"}, 3) is None
    assert update_confirmation(streaks, {"tb1"}, 3) == "tb1"


def test_reconfirmation_requires_current_visibility_and_preserves_original_first_event():
    import json
    from types import SimpleNamespace
    from gazebo_msgs.msg import ModelStates
    from geometry_msgs.msg import Pose
    from multi_robot_exploration.target_detector import TargetDetector
    robot, target = Pose(), Pose()
    robot.position.x = robot.position.y = 1.5
    robot.orientation.w = 1.
    target.position.x, target.position.y = 3.5, 1.5
    message = ModelStates(name=["tb1", "search_target"], pose=[robot, target])
    emitted = []
    node = SimpleNamespace(
        target_model="search_target", robot_names=["tb1"], truth=truth_grid(),
        max_distance=3., field_of_view=math.pi/2, field_of_view_degrees=90.,
        streaks={"tb1": 0}, required_frames=3, confirmed=False,
        last_confirmation_at=-math.inf, observation_state="EXPLORE", clock=1.,
        detection_publisher=SimpleNamespace(publish=emitted.append),
        _publish_observation=lambda state: None,
        get_logger=lambda: SimpleNamespace(info=lambda *a: None))
    node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=int(node.clock*1e9)))
    for _ in range(3): TargetDetector._model_states_callback(node, message)
    assert len(emitted) == 1 and json.loads(emitted[0].data)["stamp_sec"] == 1.
    node.clock = 1.5
    TargetDetector._model_states_callback(node, message)
    assert len(emitted) == 1  # at most one new confirmation per second
    node.truth.occupied[1, 2] = True
    node.clock = 10.
    TargetDetector._model_states_callback(node, message)
    assert len(emitted) == 1 and node.last_confirmation_at == 1.
    node.truth.occupied[1, 2] = False
    for _ in range(2): TargetDetector._model_states_callback(node, message)
    assert len(emitted) == 1
    TargetDetector._model_states_callback(node, message)
    assert len(emitted) == 2 and json.loads(emitted[-1].data)["stamp_sec"] == 10.
    assert json.loads(emitted[0].data)["stamp_sec"] == 1.
