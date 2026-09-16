import math

import numpy as np
import pytest

from geometry_msgs.msg import Transform

from multi_robot_exploration import control


def test_transform_point_2d_applies_map_to_odom_transform():
    transform = Transform()
    transform.translation.x = 4.0
    transform.translation.y = -2.0
    transform.rotation.z = 2**-0.5
    transform.rotation.w = 2**-0.5

    x, y = control.transform_point_2d(3.0, 1.0, transform)

    assert x == pytest.approx(3.0)
    assert y == pytest.approx(1.0)


def test_frontier_groups_keep_all_qualifying_groups():
    grid = np.full((20, 30), -1, dtype=int)
    grid[2:6, 2:8] = 0
    grid[12:16, 20:28] = 0

    groups = control.frontier_groups(grid, minimum_size=6)

    assert len(groups) == 2


def test_viewpoint_is_safe_and_has_known_line_of_sight():
    grid = np.full((30, 30), -1, dtype=int)
    grid[5:25, 5:20] = 0
    grid[5:25, 5] = 100
    groups = control.frontier_groups(grid)
    traversable = control.traversable_grid(grid, resolution=0.1)

    viewpoints = control.frontier_viewpoints(
        grid, groups, traversable, resolution=0.1
    )

    assert viewpoints
    for candidates in viewpoints.values():
        for candidate in candidates:
            assert traversable[candidate.row, candidate.column]
            assert control.has_known_line_of_sight(
                grid,
                (candidate.row, candidate.column),
                (candidate.frontier_row, candidate.frontier_column),
            )


def test_coordinator_assigns_distinct_reachable_frontiers():
    grid = np.zeros((60, 80), dtype=int)
    grid[[0, -1], :] = 100
    grid[:, [0, -1]] = 100
    grid[10:16, 10:16] = -1
    grid[40:46, 60:66] = -1
    positions = {
        "tb1": (2.0, 3.0),
        "tb2": (6.0, 3.0),
    }

    assignments, diagnostics = control.coordinate_assignments(
        grid,
        resolution=0.1,
        origin=(0.0, 0.0),
        robot_positions=positions,
    )

    assert len(assignments) == 2
    assert diagnostics["frontier_groups"] >= 2
    assert len(
        {assignment.viewpoint.group_id for assignment in assignments.values()}
    ) == 2


def test_large_frontier_provides_spatially_diverse_candidates():
    grid = np.full((80, 80), -1, dtype=int)
    grid[10:70, 10:70] = 0

    candidates, diagnostics = control.robot_candidate_assignments(
        grid,
        resolution=0.1,
        origin=(0.0, 0.0),
        robot_name="tb1",
        robot_position=(4.0, 4.0),
    )

    assert diagnostics["frontier_groups"] >= 1
    assert len(candidates) >= 2
    targets = [(candidate[3].x, candidate[3].y) for candidate in candidates]
    assert any(
        math.dist(first, second) >= control.MIN_TARGET_SEPARATION_M
        for index, first in enumerate(targets)
        for second in targets[index + 1:]
    )
