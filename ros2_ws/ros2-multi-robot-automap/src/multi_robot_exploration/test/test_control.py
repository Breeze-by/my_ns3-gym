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


def test_runtime_assignment_keeps_targets_spatially_distinct():
    viewpoint = control.Viewpoint(1, 5, 5, 5, 6, 100, 10)
    other_viewpoint = control.Viewpoint(2, 8, 8, 8, 9, 90, 8)
    first = control.Assignment(viewpoint, 1.0, 1.0, 2.0, 20.0, 1.0, 1.0)
    second = control.Assignment(viewpoint, 3.0, 1.0, 2.0, 19.0, 3.0, 1.0)
    alternative = control.Assignment(
        other_viewpoint, 5.0, 1.0, 2.0, 18.0, 5.0, 1.0
    )

    assignments = control.select_distinct_assignments(
        [
            (20.0, "tb1", 1, first),
            (19.0, "tb2", 1, second),
            (18.0, "tb2", 2, alternative),
        ]
    )

    assert set(assignments) == {"tb1", "tb2"}
    assert assignments["tb2"].viewpoint.group_id == 1


def test_goal_replans_after_information_is_observed():
    assert not control.goal_is_stale(1000, 100, 2.9)
    assert not control.goal_is_stale(1000, 300, 10.0)
    assert control.goal_is_stale(1000, 200, 10.0)


def test_coordinator_waits_for_every_robot_input_before_assignment():
    positions = {"tb1": (0.0, 0.0), "tb2": None}
    maps = {"tb1": object(), "tb2": object()}

    assert not control.all_robot_inputs_ready(positions, maps)
    positions["tb2"] = (1.0, 0.0)
    assert control.all_robot_inputs_ready(positions, maps)


def test_central_navigation_pauses_for_any_local_safety_return():
    assert control.all_batteries_active({"tb1": "ACTIVE", "tb2": "ACTIVE"})
    assert not control.all_batteries_active(
        {"tb1": "ACTIVE", "tb2": "RETURNING"}
    )


def test_rotate_robot_order_prevents_a_failed_robot_from_starving_others():
    order = ["tb2", "tb1", "tb3"]

    assert control.rotate_robot_order(order, 0) == order
    assert control.rotate_robot_order(order, 1) == ["tb1", "tb3", "tb2"]
    assert control.rotate_robot_order(order, 4) == ["tb1", "tb3", "tb2"]


def test_path_waypoint_limits_navigation_leg():
    traversable = np.ones((1, 11), dtype=bool)

    assert control.path_waypoint(traversable, (0, 0), (0, 10), 4.0) == (
        0,
        4,
    )


def test_stage_navigation_rejects_an_unsafe_actual_start():
    raw_grid = np.zeros((40, 40), dtype=int)
    raw_grid[18:23, 18:23] = 100
    viewpoint = control.Viewpoint(1, 35, 35, 35, 36, 100, 10)
    assignment = control.Assignment(
        viewpoint, 3.55, 3.55, 8.0, 10.0, 3.55, 3.55
    )

    assert control.stage_navigation_leg(
        assignment, raw_grid, 0.1, (0.0, 0.0), (2.0, 2.0)
    ) is None


def test_reassign_rally_pose_avoids_reserved_pose():
    raw_grid = np.zeros((80, 80), dtype=int)
    target = (4.0, 4.0)
    replacement = control.reassign_rally_pose(
        raw_grid,
        0.1,
        (0.0, 0.0),
        "tb1",
        (1.0, 1.0),
        target,
        reserved_poses=[(4.0, 3.0)],
    )

    assert replacement is not None
    assert math.dist((replacement.x, replacement.y), (4.0, 3.0)) >= (
        control.RALLY_MIN_SEPARATION_M
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


def test_rally_rejects_an_unsafe_actual_start_instead_of_snapping():
    grid = np.zeros((70, 70), dtype=int)
    grid[10:13, 10:13] = 100
    assignments = control.assign_rally_poses(
        grid,
        0.1,
        (0.0, 0.0),
        {"tb1": (1.05, 1.05)},
        (3.5, 3.5),
    )

    assert not assignments


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


def test_rally_yield_pose_moves_parked_robot_away_from_target():
    grid = np.zeros((100, 100), dtype=int)
    robot = (2.0, 2.0)
    target = (7.0, 7.0)

    pose = control.rally_yield_pose(
        grid, 0.1, (0.0, 0.0), robot, target, reserved_poses=[(7.0, 6.0)]
    )

    assert pose is not None
    assert math.dist((pose.x, pose.y), robot) >= 0.5
    assert math.dist((pose.x, pose.y), (7.0, 6.0)) >= (
        control.RALLY_MIN_SEPARATION_M
    )


def test_rally_survey_tries_detector_then_remaining_robots():
    positions = {"tb1": (0.0, 0.0), "tb2": (1.0, 0.0), "tb3": (2.0, 0.0)}

    assert control.survey_robot_order(positions, "tb2") == [
        "tb2",
        "tb1",
        "tb3",
    ]


def test_rally_dispatches_near_side_first_to_avoid_blocking_arrivals():
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

    assert order == ["tb1", "tb3", "tb2"]


def test_rally_dispatches_near_side_pose_before_deep_pose():
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

    assert order.index("tb2") < order.index("tb3")


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


def test_rally_route_avoids_robot_already_parked_at_its_pose():
    grid = np.zeros((60, 60), dtype=int)
    pose = control.RallyPose(5.0, 3.0, 0.0)
    blocker = (3.0, 3.0)

    _, route = control.plan_rally_leg(
        pose,
        grid,
        0.1,
        (0.0, 0.0),
        (1.0, 3.0),
        max_distance_m=float("inf"),
        blocked_positions=[blocker],
    )

    assert route[-1] == pytest.approx((pose.x, pose.y), abs=0.1)
    assert min(math.dist(point, blocker) for point in route) >= 0.55


def test_rally_does_not_bypass_disconnected_route():
    grid = np.zeros((14, 100), dtype=int)
    grid[[0, -1], :] = 100
    grid[:, 50] = 100
    leg, route = control.plan_rally_leg(
        control.RallyPose(8.0, 0.7, 0.0),
        grid,
        0.1,
        (0.0, 0.0),
        (1.0, 0.7),
    )
    assert leg is None
    assert not route


def test_rally_target_outside_updated_map_is_not_dispatched():
    leg, route = control.plan_rally_leg(
        control.RallyPose(20.0, 0.7, 0.0),
        np.zeros((14, 100), dtype=int),
        0.1,
        (0.0, 0.0),
        (1.0, 0.7),
    )
    assert leg is None
    assert not route


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
    assert control.valid_task_transition("EXPLORE", "FAILED")
    assert control.valid_task_transition("FOUND_UNCONFIRMED", "FAILED")
    assert not control.valid_task_transition("EXPLORE", "RALLY")
    assert not control.valid_task_transition("COMPLETE", "EXPLORE")


def test_missing_or_stale_battery_state_is_unavailable():
    received_at = {"tb1": 95.0, "tb2": None, "tb3": 70.0}

    assert control.unavailable_battery_states(
        received_at, now=100.0, timeout=20.0
    ) == ["tb2", "tb3"]
