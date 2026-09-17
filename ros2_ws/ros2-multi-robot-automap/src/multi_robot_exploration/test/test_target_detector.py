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
