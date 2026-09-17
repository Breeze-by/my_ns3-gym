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


def test_exploration_utility_penalizes_trivial_motion():
    short_hop = control.exploration_utility(1000, 100, 0.2)
    useful_hop = control.exploration_utility(1000, 100, 0.75)

    assert useful_hop > short_hop


def test_goal_replans_after_information_is_observed():
    assert not control.goal_is_stale(1000, 100, 2.9)
    assert not control.goal_is_stale(1000, 300, 10.0)
    assert control.goal_is_stale(1000, 200, 10.0)


def test_path_waypoint_limits_navigation_leg():
    traversable = np.ones((1, 11), dtype=bool)

    assert control.path_waypoint(traversable, (0, 0), (0, 10), 4.0) == (
        0,
        4,
    )


def test_rally_assigns_distinct_safe_target_facing_poses():
    grid = np.zeros((70, 70), dtype=int)
    grid[[0, -1], :] = 100
    grid[:, [0, -1]] = 100
    target = (3.5, 3.5)
    positions = {
        "tb1": (1.0, 1.0),
        "tb2": (6.0, 1.0),
        "tb3": (3.5, 6.0),
    }

    assignments = control.assign_rally_poses(
        grid, 0.1, (0.0, 0.0), positions, target
    )

    assert set(assignments) == set(positions)
    poses = list(assignments.values())
    assert all(
        math.dist((first.x, first.y), (second.x, second.y))
        >= control.RALLY_MIN_SEPARATION_M
        for index, first in enumerate(poses)
        for second in poses[index + 1:]
    )
    for pose in poses:
        expected_yaw = math.atan2(target[1] - pose.y, target[0] - pose.x)
        assert pose.yaw == pytest.approx(expected_yaw)


def test_rally_rejects_blocked_target_area():
    grid = np.full((30, 30), 100, dtype=int)
    grid[15, 15] = 0

    assert not control.assign_rally_poses(
        grid,
        0.1,
        (0.0, 0.0),
        {"tb1": (1.55, 1.55)},
        (1.55, 1.55),
    )


def test_rally_supports_a_narrow_known_approach_fan():
    grid = np.full((80, 80), -1, dtype=int)
    grid[10:52, 34:47] = 0
    target = (4.0, 5.0)
    positions = {
        "tb1": (3.7, 1.5),
        "tb2": (4.0, 2.0),
        "tb3": (4.3, 2.5),
    }

    assignments = control.assign_rally_poses(
        grid, 0.1, (0.0, 0.0), positions, target
    )

    assert set(assignments) == set(positions)
    assert max(
        math.dist((pose.x, pose.y), target)
        for pose in assignments.values()
    ) > 2.0


def test_rally_survey_moves_detector_toward_target_on_known_space():
    grid = np.full((80, 80), -1, dtype=int)
    grid[10:55, 34:47] = 0
    target = (4.0, 5.0)
    robot = (4.0, 1.5)

    pose = control.rally_survey_pose(
        grid, 0.1, (0.0, 0.0), robot, target
    )

    assert pose is not None
    assert math.dist((pose.x, pose.y), target) < math.dist(robot, target) - 0.4


def test_rally_dispatches_far_side_first_to_avoid_blocking_arrivals():
    targets = {
        "tb1": control.RallyPose(0.0, 2.6, 0.0),
        "tb2": control.RallyPose(0.0, 1.0, 0.0),
        "tb3": control.RallyPose(1.0, 0.0, 0.0),
    }
    positions = {
        "tb1": (0.0, 0.0),
        "tb2": (5.0, 5.0),
        "tb3": (1.1, 0.0),
    }

    order = control.rally_dispatch_order(targets, positions, (0.0, 0.0))

    assert order == ["tb2", "tb3", "tb1"]


def test_rally_dispatches_deep_pose_before_near_side_pose():
    targets = {
        "tb1": control.RallyPose(-4.0, 1.4, 0.0),
        "tb2": control.RallyPose(-4.0, 3.0, 0.0),
        "tb3": control.RallyPose(-5.0, 3.75, 0.0),
    }
    positions = {
        "tb1": (-3.5, 3.0),
        "tb2": (3.0, 3.5),
        "tb3": (-2.0, 1.7),
    }

    order = control.rally_dispatch_order(targets, positions, (-4.0, 4.0))

    assert order.index("tb3") < order.index("tb2")


def test_rally_dispatches_detecting_robot_first():
    targets = {
        "tb1": control.RallyPose(-4.0, 3.0, 0.0),
        "tb2": control.RallyPose(-5.0, 3.75, 0.0),
    }
    positions = {"tb1": (-3.5, 3.0), "tb2": (3.0, 3.5)}

    order = control.rally_dispatch_order(
        targets, positions, (-4.0, 4.0), priority_robot="tb1"
    )

    assert order[0] == "tb1"


def test_rally_navigation_stages_long_paths():
    grid = np.zeros((20, 130), dtype=int)
    pose = control.RallyPose(11.0, 1.0, 0.0)

    leg = control.stage_rally_leg(
        pose, grid, 0.1, (0.0, 0.0), (1.0, 1.0)
    )

    assert 1.3 <= math.dist((1.0, 1.0), (leg.x, leg.y)) <= 1.6
    assert math.dist((leg.x, leg.y), (pose.x, pose.y)) > 8.3

    planned_leg, route = control.plan_rally_leg(
        pose, grid, 0.1, (0.0, 0.0), (1.0, 1.0)
    )
    assert planned_leg == leg
    assert route[-1] == pytest.approx((leg.x, leg.y))

    retry_leg = control.stage_rally_leg(
        pose,
        grid,
        0.1,
        (0.0, 0.0),
        (1.0, 1.0),
        max_distance_m=0.75,
    )
    assert 0.6 <= math.dist((1.0, 1.0), (retry_leg.x, retry_leg.y)) <= 0.8


def test_rally_selects_disjoint_routes_in_parallel():
    routes = {
        "tb1": ((0.0, 0.0), (1.0, 0.0)),
        "tb2": ((0.0, 2.0), (1.0, 2.0)),
    }

    assert control.select_nonconflicting_routes(
        routes, ["tb1", "tb2"]
    ) == ["tb1", "tb2"]


def test_rally_limits_parallel_navigation_capacity():
    routes = {
        "tb1": ((0.0, 0.0), (1.0, 0.0)),
        "tb2": ((0.0, 2.0), (1.0, 2.0)),
        "tb3": ((0.0, 4.0), (1.0, 4.0)),
    }

    assert control.select_nonconflicting_routes(
        routes, ["tb1", "tb2", "tb3"], max_count=2
    ) == ["tb1", "tb2"]


def test_rally_yields_only_the_conflicting_route():
    routes = {
        "tb1": ((0.0, 0.0), (1.0, 0.0)),
        "tb2": ((0.5, -1.0), (0.5, 1.0)),
        "tb3": ((0.0, 2.0), (1.0, 2.0)),
    }

    assert control.select_nonconflicting_routes(
        routes, ["tb1", "tb2", "tb3"]
    ) == ["tb1", "tb3"]


def test_rally_yields_lower_priority_robot_if_positions_converge():
    positions = {"tb1": (0.0, 0.0), "tb2": (0.9, 0.0)}

    assert control.robots_that_must_yield(
        positions, ["tb1", "tb2"], ["tb1", "tb2"]
    ) == {"tb2"}


def test_rally_stability_checks_pose_and_both_speeds():
    targets = {"tb1": control.RallyPose(1.0, 2.0, 0.0)}
    positions = {"tb1": (1.2, 2.0)}

    assert control.robots_stable(
        positions, {"tb1": (0.04, 0.09)}, targets
    )
    assert not control.robots_stable(
        positions, {"tb1": (0.06, 0.09)}, targets
    )
    assert not control.robots_stable(
        positions, {"tb1": (0.04, 0.11)}, targets
    )
    assert not control.robots_stable(
        {"tb1": (1.4, 2.0)}, {"tb1": (0.0, 0.0)}, targets
    )


def test_task_state_transitions_do_not_skip_or_reopen_terminal_states():
    assert control.valid_task_transition("EXPLORE", "FOUND_UNCONFIRMED")
    assert control.valid_task_transition("FOUND_UNCONFIRMED", "FOUND")
    assert control.valid_task_transition("FOUND", "RALLY")
    assert control.valid_task_transition("RALLY", "COMPLETE")
    assert not control.valid_task_transition("EXPLORE", "RALLY")
    assert not control.valid_task_transition("COMPLETE", "EXPLORE")
