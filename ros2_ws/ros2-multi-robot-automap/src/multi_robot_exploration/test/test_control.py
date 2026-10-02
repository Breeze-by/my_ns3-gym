import math

import numpy as np
import pytest

from geometry_msgs.msg import Transform

from multi_robot_exploration import control


def test_failure_events_carry_complete_isolation_snapshot_once_per_robot():
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["tb1", "tb2"]
    node = SimpleNamespace(
        battery_modes=dict.fromkeys(names, "ACTIVE"), robot_states={},
        battery_preempted={}, goal_handles=dict.fromkeys(names),
        rally_goal_handles=dict.fromkeys(names), survey_robot=None,
        rally_targets={}, rally_charge_requested={}, rally_precharge_staging={},
        rally_final_targets={}, rally_arrived={}, rally_dispatch_order=names[:],
        rally_yield_targets=set(), return_yield_targets={},
        rally_probe_targets=set(), rally_probe_robot=None,
        task_state="EXPLORE", robot_failure_publisher=Mock(),
        get_logger=lambda: Mock(), fail_task=Mock(),
    )
    node.participating_robots = lambda: [
        name for name in names if node.battery_modes[name] != "FAILED"
    ]
    for name in names:
        control.HeadquartersControl.mark_robot_failed(node, name, "battery_exhausted")
    events = [json.loads(call.args[0].data) for call in node.robot_failure_publisher.publish.call_args_list]
    assert events[0]["failed_robots"] == ["tb1"]
    assert events[1]["failed_robots"] == names
    assert events[1]["remaining_robots"] == []
    control.HeadquartersControl.mark_robot_failed(node, "tb1", "battery_exhausted")
    assert node.robot_failure_publisher.publish.call_count == 2


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


def test_rally_battery_preemption_is_global():
    assert not control.all_batteries_active(
        {"tb1": "ACTIVE", "tb2": "CHARGING", "tb3": "ACTIVE"}
    )


def test_battery_assignment_reserves_a_conservative_return_budget():
    assert control.battery_assignment_is_safe(
        40.0, 3.0, 2.0, 1.0, 0.02, 2.0, 0.18, 8.0
    )
    assert not control.battery_assignment_is_safe(
        24.0, 8.0, 5.0, 1.0, 0.02, 2.0, 0.18, 8.0
    )


def test_rotate_robot_order_prevents_a_failed_robot_from_starving_others():
    order = ["tb2", "tb1", "tb3"]

    assert control.rotate_robot_order(order, 0) == order
    assert control.rotate_robot_order(order, 1) == ["tb1", "tb3", "tb2"]
    assert control.rotate_robot_order(order, 4) == ["tb1", "tb3", "tb2"]


def test_rally_recovery_reserves_temporary_and_final_poses():
    targets = {
        "tb1": control.RallyPose(1.0, 1.0, 0.0),
        "tb2": control.RallyPose(2.0, 2.0, 0.0),
    }
    finals = {
        "tb1": control.RallyPose(3.0, 3.0, 0.0),
        "tb2": targets["tb2"],
    }

    reserved = control.rally_reserved_poses(targets, finals, exclude=("tb2",))

    assert (1.0, 1.0) in reserved
    assert (3.0, 3.0) in reserved
    assert (2.0, 2.0) not in reserved


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


def test_navigation_start_allows_short_escape_from_clearance_inflation():
    raw_grid = np.zeros((40, 40), dtype=int)
    raw_grid[20, 23] = 100
    traversable = control.traversable_grid(raw_grid, 0.1, 0.35)

    start = control.navigation_start_cell(
        raw_grid, traversable, (20, 20), max_radius_cells=6
    )

    assert start is not None
    assert traversable[start]
    assert math.dist(start, (20, 20)) <= 6

    endpoint, route = control.navigation_start_route(
        raw_grid, traversable, (20, 20), max_radius_cells=6
    )
    assert endpoint == route[-1]
    assert route[0] == (20, 20)
    assert len(route) > 1


def test_navigation_start_rejects_unknown_or_occupied_pose():
    raw_grid = np.zeros((20, 20), dtype=int)
    raw_grid[8, 8] = 100
    raw_grid[12, 12] = -1
    traversable = control.traversable_grid(raw_grid, 0.1, 0.35)

    assert control.navigation_start_cell(
        raw_grid, traversable, (8, 8), max_radius_cells=6
    ) is None
    assert control.navigation_start_cell(
        raw_grid, traversable, (12, 12), max_radius_cells=6
    ) is None


def test_navigation_start_does_not_jump_across_an_occupied_wall():
    raw_grid = np.zeros((30, 30), dtype=int)
    raw_grid[:, 15] = 100
    traversable = np.zeros_like(raw_grid, dtype=bool)
    traversable[10, 20] = True

    assert control.navigation_start_cell(
        raw_grid, traversable, (10, 14), max_radius_cells=20
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


def test_rally_assignment_supports_explicit_total_path_ablation():
    grid = np.zeros((70, 70), dtype=int)
    positions = {
        "tb1": (1.0, 1.0),
        "tb2": (6.0, 1.0),
        "tb3": (3.5, 6.0),
    }

    assignments = control.assign_rally_poses(
        grid,
        0.1,
        (0.0, 0.0),
        positions,
        (3.5, 3.5),
        objective="total_path",
    )

    assert set(assignments) == set(positions)
    with pytest.raises(ValueError):
        control.assign_rally_poses(
            grid,
            0.1,
            (0.0, 0.0),
            positions,
            (3.5, 3.5),
            objective="unknown",
        )


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


def test_map_safe_rally_order_keeps_all_robots_in_the_serial_plan():
    grid = np.zeros((100, 100), dtype=int)
    targets = {
        "tb1": control.RallyPose(2.0, 8.0, 0.0),
        "tb2": control.RallyPose(4.0, 8.0, 0.0),
        "tb3": control.RallyPose(6.0, 8.0, 0.0),
    }
    positions = {
        "tb1": (1.0, 1.0),
        "tb2": (4.0, 1.0),
        "tb3": (7.0, 1.0),
    }

    order = control.map_safe_rally_dispatch_order(
        grid, 0.1, (0.0, 0.0), targets, positions, (4.0, 8.0), "tb1"
    )

    assert set(order) == set(targets)
    assert len(order) == len(targets)


def test_rally_navigation_stages_long_paths():
    grid = np.zeros((20, 130), dtype=int)
    pose = control.RallyPose(11.0, 1.0, 0.0)

    leg = control.stage_rally_leg(
        pose, grid, 0.1, (0.0, 0.0), (1.0, 1.0), max_distance_m=1.5
    )

    assert 1.3 <= math.dist((1.0, 1.0), (leg.x, leg.y)) <= 1.6
    assert math.dist((leg.x, leg.y), (pose.x, pose.y)) > 8.3

    planned_leg, route = control.plan_rally_leg(
        pose, grid, 0.1, (0.0, 0.0), (1.0, 1.0), max_distance_m=1.5
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


def test_rally_first_leg_uses_final_goal_and_retry_is_short():
    assert math.isinf(control.rally_leg_limit(0))
    assert control.rally_leg_limit(1) == pytest.approx(1.5)


def test_rally_route_reservation_stops_before_conflict():
    plan = (
        control.RallyPose(3.0, 0.0, 0.0),
        ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)),
    )
    admitted = control.reserve_rally_prefix(
        plan, [((2.8, -0.2), (2.8, 0.2))]
    )

    assert admitted is not None
    assert admitted[1][-1] == pytest.approx((1.0, 0.0))


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
    assert control.valid_task_transition("RALLY", "PARTIAL_COMPLETE")
    assert control.valid_task_transition("EXPLORE", "FAILED")
    assert control.valid_task_transition("FOUND_UNCONFIRMED", "FAILED")
    assert not control.valid_task_transition("EXPLORE", "RALLY")
    assert not control.valid_task_transition("COMPLETE", "EXPLORE")
    assert not control.valid_task_transition("PARTIAL_COMPLETE", "RALLY")


def test_missing_or_stale_battery_state_is_unavailable():
    received_at = {"tb1": 95.0, "tb2": None, "tb3": 70.0}

    assert control.unavailable_battery_states(
        received_at, now=100.0, timeout=20.0
    ) == ["tb2", "tb3"]


def test_history_discourages_but_does_not_remove_reachable_frontiers():
    grid = np.full((40, 40), -1, dtype=int)
    grid[5:35, 5:30] = 0
    args = (grid, 0.1, (0.0, 0.0), "tb1", (2.0, 2.0))
    original, _ = control.robot_candidate_assignments(*args)
    history = [(item[3].x, item[3].y) for item in original]
    repeated, _ = control.robot_candidate_assignments(*args, excluded_targets=history)
    assert len(repeated) == len(original) > 0
    assert all(0 < new[0] < old[0] for new, old in zip(repeated, original))


def test_joint_assignment_does_not_take_another_robots_only_target():
    viewpoint = control.Viewpoint(1, 5, 5, 5, 6, 100, 10)
    def candidate(name, x, utility):
        return (utility, name, 1,
                control.Assignment(viewpoint, x, 0.0, 2.0, utility, x, 0.0))
    selected = control.select_distinct_assignments([
        candidate("tb1", 1.0, 10.0), candidate("tb1", 4.0, 9.0),
        candidate("tb2", 1.0, 8.0),
    ])
    assert selected["tb1"].x == 4.0
    assert selected["tb2"].x == 1.0


def test_path_cannot_cut_diagonally_through_blocked_corners():
    safe = np.array([[True, False], [False, True]])
    distances = control.path_distance_grid(safe, (0, 0))
    assert not np.isfinite(distances[1, 1])


def test_distant_frontier_can_require_long_detour_through_known_space():
    grid = np.zeros((30, 230), dtype=int)
    grid[:, 220:] = -1
    candidates, _ = control.robot_candidate_assignments(
        grid, 0.1, (0.0, 0.0), "tb1", (1.0, 1.5))
    assert candidates
    assert min(item[3].path_distance_m for item in candidates) > 12.0


def test_exploration_route_excludes_a_parked_robot_sealing_a_corridor():
    grid = np.full((14, 100), 100, dtype=int)
    grid[1:-1, 1:90] = 0
    grid[1:-1, 90:] = -1
    pose = control.RallyPose(9.0, 0.7, 0.0)
    leg, route = control.plan_rally_leg(
        pose, grid, 0.1, (0.0, 0.0), (1.0, 0.7),
        max_distance_m=float("inf"), blocked_positions=[(5.0, 0.7)],
        clearance_m=control.PATH_CLEARANCE_M,
    )
    assert leg is None
    assert not route


def test_single_explorer_checks_parked_robots_after_previous_goal_finishes(monkeypatch):
    from types import SimpleNamespace

    grid = np.zeros((60, 100), dtype=int)
    viewpoint = control.Viewpoint(0, 30, 80, 30, 81, 1000, 10)
    assignment = control.Assignment(viewpoint, 8.0, 3.0, 7.0, 10.0, 8.0, 3.0)
    calls = []
    def candidates(*args, **kwargs):
        calls.append(args[4])
        return [(10.0, args[3], 0, assignment)], {
            "frontier_groups": 1, "groups_with_viewpoints": 1,
            "candidate_assignments": 1,
        }
    monkeypatch.setattr(control, "robot_candidate_assignments", candidates)
    sent = []
    node = SimpleNamespace(
        task_state="EXPLORE", map_data=grid, resolution=0.1, origin=(0.0, 0.0),
        robot_positions={"tb1": (1.0, 3.0), "tb2": (3.0, 3.0)},
        robot_maps={"tb1": {}, "tb2": {}},
        robot_states={"tb1": "idle", "tb2": "idle"},
        battery_modes={"tb1": "ACTIVE", "tb2": "ACTIVE"},
        frontier_cache=control.prepare_frontier_data(grid, 0.1),
        input_robot_names=lambda: ["tb1", "tb2"],
        participating_robots=lambda: ["tb1", "tb2"],
        fresh_robot_inputs=lambda: True, active_exclusions=lambda: [],
        battery_assignment_safe=lambda *args: True,
        goal_targets={}, goal_routes={}, goal_initial_gain={"tb1": 0, "tb2": 0},
        target_information_gain=lambda *args: 1000,
        get_logger=lambda: SimpleNamespace(info=lambda *args: None, warn=lambda *args: None),
        send_goal=lambda name, goal: sent.append((name, goal)),
    )
    control.HeadquartersControl.assign_idle_robots(node)
    assert sent and {name for name, _ in sent} <= {"tb1", "tb2"}
    assert calls == [(1.0, 3.0), (3.0, 3.0)]
    assert min(math.dist(point, (3.0, 3.0)) for point in node.goal_routes["tb1"]) >= 0.55
    node.battery_modes["tb2"] = "RETURNING"
    node.robot_states["tb1"] = "idle"
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(sent) <= 2


def test_visible_leg_stops_before_parked_robot_detour():
    grid = np.zeros((60, 100), dtype=int)
    start = (1.0, 3.0)
    blocked = [(3.0, 3.0)]
    pose, route = control.plan_rally_leg(
        control.RallyPose(8.0, 3.0, 0.0), grid, 0.1, (0.0, 0.0), start,
        max_distance_m=5.0, blocked_positions=blocked,
        clearance_m=control.PATH_CLEARANCE_M, visible_only=True,
    )
    assert pose is not None
    assert pose.x < 8.0
    mask = control.block_dynamic_positions(
        control.traversable_grid(grid, 0.1, control.PATH_CLEARANCE_M),
        0.1, (0.0, 0.0), blocked,
    )
    cells = control._line_cells(
        control.world_to_grid(*start, 0.1, 0.0, 0.0),
        control.world_to_grid(pose.x, pose.y, 0.1, 0.0, 0.0),
    )
    assert all(mask[cell] for cell in cells)
    assert route[-1] == (pose.x, pose.y)


@pytest.mark.parametrize("robot_count", (2, 3, 4))
def test_parallel_explorers_try_independent_alternative_after_conflict(monkeypatch, robot_count):
    from types import SimpleNamespace

    grid = np.zeros((260, 100), dtype=int)
    names = [f"tb{i + 1}" for i in range(robot_count)]
    viewpoint = control.Viewpoint(0, 30, 80, 30, 81, 1000, 10)
    def candidates(*args):
        name = args[3]
        index = names.index(name)
        positions = [(8.0, 3.0, 100.0 - index)]
        if index:
            positions.append((8.0, 3.0 + 6 * index, 80.0 - index))
        return [
            (utility, name, 0, control.Assignment(
                viewpoint, x, y, 7.0, utility, x, y,
            )) for x, y, utility in positions
        ], {"frontier_groups": 1, "groups_with_viewpoints": 1}
    monkeypatch.setattr(control, "robot_candidate_assignments", candidates)
    sent = []
    node = SimpleNamespace(
        task_state="EXPLORE", map_data=grid, resolution=0.1, origin=(0.0, 0.0),
        robot_positions={name: (1.0, 3.0 + 6 * index) for index, name in enumerate(names)},
        robot_maps=dict.fromkeys(names, {}), robot_states=dict.fromkeys(names, "idle"),
        battery_modes=dict.fromkeys(names, "ACTIVE"),
        frontier_cache=control.prepare_frontier_data(grid, 0.1),
        input_robot_names=lambda: names, participating_robots=lambda: names,
        fresh_robot_inputs=lambda: True, active_exclusions=lambda: [],
        battery_assignment_safe=lambda *args: True,
        goal_targets={}, goal_routes={}, goal_initial_gain={},
        target_information_gain=lambda *args: 1000,
        get_logger=lambda: SimpleNamespace(info=lambda *args: None),
        send_goal=lambda name, goal: sent.append((name, goal)),
    )
    control.HeadquartersControl.assign_idle_robots(node)
    assert [name for name, _ in sent] == names[:min(robot_count, 3)]
    assert node.goal_targets["tb2"].y == 9.0
    for i, name in enumerate(node.goal_routes):
        for other in list(node.goal_routes)[i + 1:]:
            assert not control.routes_conflict(node.goal_routes[name], node.goal_routes[other])
    # Pending actions consume capacity even before an accepted action response.
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(sent) == min(robot_count, 3)


@pytest.mark.parametrize("step, expected", ((0.0, 0), (0.005, 0), (0.05, 1), (0.2, 1)))
def test_exploration_allows_short_initial_viewpoint(monkeypatch, step, expected):
    from types import SimpleNamespace

    grid = np.zeros((80, 80), dtype=int)
    viewpoint = control.Viewpoint(0, 40, 40, 40, 41, 1000, 10)
    assignment = control.Assignment(viewpoint, 2.025 + step, 2.025, step, 10.0, 2.025 + step, 2.025)
    monkeypatch.setattr(control, "robot_candidate_assignments", lambda *args, **kwargs: (
        [(10.0, "tb1", 0, assignment)],
        {"frontier_groups": 1, "groups_with_viewpoints": 1},
    ))
    sent = []
    node = SimpleNamespace(
        task_state="EXPLORE", map_data=grid, resolution=0.05, origin=(0.0, 0.0),
        robot_positions={"tb1": (2.025, 2.025)}, robot_maps={"tb1": {}},
        robot_states={"tb1": "idle"}, battery_modes={"tb1": "ACTIVE"},
        frontier_cache=control.prepare_frontier_data(grid, 0.05),
        input_robot_names=lambda: ["tb1"], participating_robots=lambda: ["tb1"],
        fresh_robot_inputs=lambda: True, active_exclusions=lambda: [],
        battery_assignment_safe=lambda *args: True,
        goal_targets={}, goal_routes={}, goal_initial_gain={},
        target_information_gain=lambda *args: 1000,
        now=lambda: 0.0, last_no_assignment_log=-math.inf,
        get_logger=lambda: SimpleNamespace(info=lambda *args: None, warn=lambda *args: None),
        send_goal=lambda name, goal: sent.append((name, goal)),
    )
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(sent) == expected
    if sent:
        assert math.dist(node.robot_positions["tb1"], (sent[0][1].navigation_x, sent[0][1].navigation_y)) > control.NAVIGATION_POSITION_TOLERANCE_M


def test_leg_candidates_reuse_one_snapshot_distance_field(monkeypatch):
    original = control.path_distance_grid
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(control, "path_distance_grid", counted)
    grid = np.zeros((60, 100), dtype=int)
    cache = {}
    for target in [(8.0, 3.0), (8.0, 4.0), (8.0, 5.0)]:
        plan = control.plan_rally_leg(
            control.RallyPose(*target, 0), grid, 0.1, (0, 0), (1.0, 3.0),
            5.0, visible_only=True, route_cache=cache,
        )
        reference = control.plan_rally_leg(
            control.RallyPose(*target, 0), grid, 0.1, (0, 0), (1.0, 3.0),
            5.0, visible_only=True,
        )
        assert plan == reference
    assert len(calls) == 4  # one shared field plus three uncached references


def test_returning_robot_drains_other_active_exploration():
    import json
    from types import SimpleNamespace

    canceled = []
    handle = SimpleNamespace(cancel_goal_async=lambda: canceled.append("tb2"))
    node = SimpleNamespace(
        battery_modes={"tb1": "ACTIVE", "tb2": "ACTIVE"},
        battery_states={}, battery_state_received_at={},
        goal_handles={"tb1": None, "tb2": handle},
        cancel_requested={"tb1": False, "tb2": False},
        battery_preempted={"tb1": False, "tb2": False},
        rally_goal_handles={"tb1": None, "tb2": None},
        task_state="EXPLORE", survey_robot=None, now=lambda: 1.0,
    )
    message = SimpleNamespace(data=json.dumps({"mode": "RETURNING"}))
    control.HeadquartersControl.battery_state_callback(node, message, "tb1")
    control.HeadquartersControl.battery_state_callback(node, message, "tb1")
    assert canceled == ["tb2"]
    assert node.battery_preempted["tb2"]


def test_pending_explorer_is_canceled_when_another_robot_starts_returning():
    from types import SimpleNamespace

    canceled = []
    result = SimpleNamespace(add_done_callback=lambda callback: None)
    handle = SimpleNamespace(
        accepted=True, cancel_goal_async=lambda: canceled.append("tb2"),
        get_result_async=lambda: result,
    )
    node = SimpleNamespace(
        goal_targets={"tb2": None}, goal_handles={}, goal_started_at={},
        goal_last_progress_at={}, goal_best_distance={}, goal_last_position={},
        goal_known_count={}, map_known_count=1, cancel_requested={},
        robot_positions={"tb2": (1.0, 1.0)}, battery_preempted={},
        battery_modes={"tb1": "RETURNING", "tb2": "ACTIVE"}, now=lambda: 2.0,
    )
    control.HeadquartersControl.goal_response_callback(
        node, "tb2", SimpleNamespace(result=lambda: handle),
    )
    assert canceled == ["tb2"]
    assert node.battery_preempted["tb2"]


def test_return_corridor_yield_uses_nearby_off_route_refuge():
    from types import SimpleNamespace

    grid = np.zeros((60, 100), dtype=int)
    sent = []
    original = control.RallyPose(4.0, 5.0, 0.0)
    node = SimpleNamespace(
        global_battery_rally_pause=True, now=lambda:1., rally_charge_requested=set(), rally_precharge_staging={}, fresh_robot_inputs=lambda: True,
        rally_goal_handles={"tb1": None, "tb2": None},
        rally_goal_pending={"tb1": False, "tb2": False},
        survey_goal_handle=None, survey_goal_pending=False,
        rally_dispatch_order=["tb1", "tb2"],
        battery_modes={"tb1": "RETURNING", "tb2": "ACTIVE"},
        battery_states={"tb1": {"charge_x": 1.0, "charge_y": 3.0}},
        map_data=grid, resolution=0.1, origin=(0, 0),
        robot_positions={"tb1": (8.0, 3.0), "tb2": (5.0, 3.0)},
        rally_yield_targets=set(), return_yield_targets={}, rally_targets={"tb2": original},
        rally_final_targets={"tb2": original}, rally_arrived={"tb2": True},
        rally_attempts={"tb2": 2}, publish_rally_assignments=lambda: None,
        get_logger=lambda: SimpleNamespace(info=lambda *args: None),
        send_rally_goal=lambda name, plan: sent.append((name, plan)),
    )
    control.HeadquartersControl.yield_to_returning_robot(node)
    assert sent and sent[0][0] == "tb2"
    refuge = node.rally_targets["tb2"]
    _, route = control.plan_rally_leg(
        control.RallyPose(1.0, 3.0, 0), grid, 0.1, (0, 0), (8.0, 3.0),
    )
    assert min(math.dist((refuge.x, refuge.y), point) for point in route) >= control.RALLY_ROUTE_SEPARATION_M
    assert math.dist((5.0, 3.0), (refuge.x, refuge.y)) < 2.2
    assert node.rally_final_targets["tb2"] is original
    assert not node.rally_arrived["tb2"]
    assert node.rally_yield_targets == {"tb2"}


def test_return_heartbeat_does_not_cancel_an_active_yield():
    import json
    from types import SimpleNamespace

    canceled = []
    handle = SimpleNamespace(cancel_goal_async=lambda: canceled.append("tb2"))
    node = SimpleNamespace(
        battery_modes={"tb1": "RETURNING", "tb2": "ACTIVE"},
        battery_states={}, battery_state_received_at={},
        goal_handles={"tb1": None, "tb2": None},
        cancel_requested={"tb1": False, "tb2": False},
        battery_preempted={"tb1": False, "tb2": False},
        rally_goal_handles={"tb1": None, "tb2": handle},
        global_battery_rally_pause=True, task_state="RALLY",
        survey_robot=None, now=lambda: 1.0,
    )
    for mode in ["RETURNING", "RETURNING", "CHARGING"]:
        control.HeadquartersControl.battery_state_callback(
            node, SimpleNamespace(data=json.dumps({"mode": mode})), "tb1",
        )
    assert not canceled


def test_navigation_footprint_covers_gazebo_body_and_rpp_cost_scale():
    from pathlib import Path
    import xml.etree.ElementTree as ET
    import yaml

    src = Path(__file__).resolve().parents[2]
    model = ET.parse(src / "multi_robot/models/turtlebot3_waffle/model.sdf")
    body = model.find(".//collision[@name='base_collision']")
    offset = [float(v) for v in body.findtext("pose").split()[:2]]
    size = [float(v) for v in body.findtext("geometry/box/size").split()[:2]]
    required_radius = max(
        math.hypot(offset[0] + sx * size[0] / 2, offset[1] + sy * size[1] / 2)
        for sx in [-1, 1] for sy in [-1, 1]
    )
    for index in range(1, 5):
        config = yaml.safe_load((src / f"multi_robot/params/nav2_params_tb{index}_0.yaml").read_text())
        local = config["local_costmap"]["local_costmap"]["ros__parameters"]
        global_map = config["global_costmap"]["global_costmap"]["ros__parameters"]
        assert local["robot_radius"] >= required_radius
        assert global_map["robot_radius"] >= required_radius
        controller = config["controller_server"]["ros__parameters"]["FollowPath"]
        tolerance = config["controller_server"]["ros__parameters"]["goal_checker"]["xy_goal_tolerance"]
        assert tolerance == control.NAVIGATION_POSITION_TOLERANCE_M
        yaw_tolerance = config["controller_server"]["ros__parameters"]["goal_checker"]["yaw_goal_tolerance"]
        assert yaw_tolerance == control.NAVIGATION_YAW_TOLERANCE_RAD
        # A quarter-turn visual scan must not succeed while facing away.
        assert yaw_tolerance < math.pi / 4
        assert tolerance < local["resolution"] / 2
        assert controller["use_collision_detection"]
        assert controller["inflation_cost_scaling_factor"] == local["inflation_layer"]["cost_scaling_factor"]
        assert controller["cost_scaling_dist"] <= local["inflation_layer"]["inflation_radius"]


def test_return_yield_restores_final_goal_after_charger_reached():
    from types import SimpleNamespace

    final = control.RallyPose(4.0, 3.0, 0.0)
    updates = []
    node = SimpleNamespace(
        return_yield_targets={"tb2": "tb1"},
        battery_modes={"tb1": "RETURNING", "tb2": "ACTIVE"},
        rally_arrived={"tb2": True}, rally_goal_handles={"tb2": None},
        rally_goal_pending={"tb2": False}, rally_yield_targets={"tb2"},
        rally_targets={"tb2": control.RallyPose(1.0, 1.0, 0.0)},
        rally_final_targets={"tb2": final}, rally_route_unavailable_since={},
        publish_rally_assignments=lambda: updates.append(1),
    )
    control.HeadquartersControl.release_return_yields(node)
    assert not updates
    node.battery_modes["tb1"] = "CHARGING"
    control.HeadquartersControl.release_return_yields(node)
    assert node.rally_targets["tb2"] is final
    assert not node.rally_arrived["tb2"]
    assert not node.rally_yield_targets and not node.return_yield_targets
    assert updates == [1]


def test_parked_robot_seals_corridor_until_it_yields():
    grid = np.full((50, 100), 100, dtype=int)
    grid[19:31, 1:99] = 0
    target = control.RallyPose(8.0, 2.5, 0.0)
    args = (target, grid, 0.1, (0.0, 0.0), (1.0, 2.5), 5.0)
    blocked = control.plan_rally_leg(*args, blocked_positions=[(4.0, 2.5)], visible_only=True)
    released = control.plan_rally_leg(*args, visible_only=True)
    assert blocked == (None, ())
    assert released[0] is not None


def test_unknown_gain_stops_at_known_walls_and_recovers_through_door():
    grid = np.full((100, 100), -1, dtype=int)
    grid[40:60, 40:60] = 0
    grid[39:61, 39] = grid[39:61, 60] = 100
    grid[39, 39:61] = grid[60, 39:61] = 100
    assert control.visible_unknown_gain(grid, (50, 50), 40) == 0
    grid[39, 46:55] = 0
    assert control.visible_unknown_gain(grid, (50, 50), 40) > 0


def test_unknown_gain_counts_unique_cells_without_wrapping_map_boundaries():
    grid = np.full((30, 30), -1, dtype=int)
    grid[:5, :5] = 0
    gain = control.visible_unknown_gain(grid, (2, 2), 10)
    assert 0 < gain <= np.count_nonzero(grid[:13, :13] < 0)
    assert control.visible_unknown_gain(grid, (-1, 2), 10) == 0
    assert control.visible_unknown_gain(grid, (20, 20), 10) == 0
    assert control.visible_unknown_gain(np.zeros((30, 30)), (2, 2), 10) == 0


def test_viewpoint_gain_uses_obstacle_visibility():
    grid = np.full((60, 60), -1, dtype=int)
    grid[10:50, 10:40] = 0
    grid[10:50, 10] = 100
    groups = control.frontier_groups(grid)
    viewpoints = control.frontier_viewpoints(grid, groups, control.traversable_grid(grid, 0.1), 0.1)
    assert viewpoints
    for group in viewpoints.values():
        for point in group:
            assert point.information_gain == control.visible_unknown_gain(grid, (point.row, point.column), 20)


@pytest.mark.parametrize("permanent_reassignment, preflight_blocked", [
    (True, False), (False, False), (True, True),
])
def test_idle_blocker_recovery_dispatches_motion_before_returning(
    monkeypatch, permanent_reassignment, preflight_blocked
):
    from types import SimpleNamespace

    names = ["tb1", "tb2"]
    grid = np.full((50, 100), 100, dtype=int)
    grid[19:31, 1:99] = 0
    grid[8:26, 35:46] = 0  # a dead-end refuge, not a bypass around the blocker
    targets = {"tb1": control.RallyPose(8.0, 2.5, 0.0), "tb2": control.RallyPose(8.0, 2.0, 0.0)}
    replacements = {"tb1": targets["tb1"], "tb2": control.RallyPose(4.0, 1.5, 0.0)}
    monkeypatch.setattr(
        control, "reassign_rally_pose",
        lambda *args: replacements[args[3]] if permanent_reassignment else None,
    )
    requests = []
    node = SimpleNamespace(
        enable_battery=preflight_blocked, task_state="RALLY", fresh_robot_poses=lambda: True, fresh_target=lambda: True, stop_target_scan=lambda: False,
        last_input_availability=True,
        battery_monitor_started_at=0., battery_state_received_at=dict.fromkeys(names, 10.),
        message_freshness_timeout_sec=5.,
        rally_charge_requested={}, prepare_rally_charges=lambda: {"tb2"},
        rally_precharge_staging={},
        rally_approach_routes={},
        rally_preflight_complete=True, rally_precharge_active=False,
        battery_states={name: {'charge_x': 1., 'charge_y': 2.5} for name in names},
        rally_max_concurrent=2, rally_probe_targets=set(),
        rally_leg_routes=dict.fromkeys(names, ()), rally_hold_started_at=None,
        active_batteries_ready=lambda: True,
        participating_robots=lambda: names, battery_modes=dict.fromkeys(names, "ACTIVE"),
        now=lambda: 10.0, survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        release_return_yields=lambda: None, rally_yield_targets=set(),
        return_yield_targets={}, rally_arrived=dict.fromkeys(names, False),
        rally_goal_handles=dict.fromkeys(names), rally_goal_pending=dict.fromkeys(names, False),
        rally_dispatch_order=names, rally_yield_requested=dict.fromkeys(names, False),
        rally_goal_started_at=dict.fromkeys(names), rally_targets=targets.copy(),
        rally_final_targets=targets.copy(), robot_positions={"tb1": (1.0, 2.5), "tb2": (4.0, 2.5)},
        yield_to_returning_robot=lambda: None, last_rally_dispatch_at=0,
        fresh_robot_inputs=lambda: True, global_battery_rally_pause=False,
        rally_recovery_requested=dict.fromkeys(names, False), rally_attempts=dict.fromkeys(names, 0),
        map_data=grid, resolution=0.1, origin=(0.0, 0.0), target=(8.0, 2.5),
        rally_route_unavailable_since={"tb1": 0.0, "tb2": None},
        rally_position_tolerance=0.35, publish_rally_assignments=lambda: None,
        get_logger=lambda: SimpleNamespace(warn=lambda *args: None),
        send_rally_goal=lambda name, *args: requests.append(name),
    )
    control.HeadquartersControl.update_mission(node)
    if preflight_blocked:
        assert not requests and node.rally_targets == targets
        assert node.rally_hold_started_at is None
        return
    if permanent_reassignment:
        assert node.rally_targets["tb2"] == replacements["tb2"]
    else:
        refuge = node.rally_targets["tb2"]
        assert "tb2" in node.rally_yield_targets
        assert math.dist((refuge.x, refuge.y), (4.0, 2.5)) <= 1.1
        route = control.plan_rally_leg(
            targets["tb1"], grid, 0.1, (0.0, 0.0), (1.0, 2.5)
        )[1]
        assert min(math.dist((refuge.x, refuge.y), point) for point in route) >= 0.8
    assert requests == ["tb2"]  # the action cannot be starved by the next timer


def test_small_frontier_pocket_keeps_nonzero_local_alternatives():
    grid = np.full((30, 30), -1)
    grid[5:25, 5:25] = 0
    data = control.prepare_frontier_data(grid, 0.1)
    points = next(iter(data[2].values()))
    assert 1 < len(points) <= 12
    position = control.grid_to_world(points[0].row, points[0].column, 0.1, 0, 0)
    candidates, _ = control.robot_candidate_assignments(
        grid, 0.1, (0, 0), "tb1", position, [], data
    )
    assert candidates and all(a.path_distance_m > 0 for _, _, _, a in candidates)
    assert any(0 < a.path_distance_m < 0.75 for _, _, _, a in candidates)
    assert all(data[1][point.row, point.column] for point in points)


def test_farthest_clear_waypoint_survives_an_earlier_occluded_grid_bend():
    grid = np.zeros((60, 100), dtype=int)
    grid[[0, -1], :] = 100
    grid[:, [0, -1]] = 100
    for row, column, height, width in (
        (30, 32, 2, 7), (38, 27, 7, 4), (19, 49, 4, 2),
        (31, 38, 5, 3), (12, 32, 3, 3), (28, 39, 3, 2),
    ):
        grid[row:row + height, column:column + width] = 100
    pose, route = control.plan_rally_leg(
        control.RallyPose(8.05, 4.05, 0), grid, 0.1, (0, 0), (1.05, 1.05),
        5, visible_only=True,
    )
    assert pose is not None and pose.x >= 5
    assert math.dist((1.05, 1.05), (pose.x, pose.y)) <= 5
    mask = control.traversable_grid(grid, 0.1, control.PATH_CLEARANCE_M)
    assert all(mask[control.world_to_grid(x, y, 0.1, 0, 0)] for x, y in route)
    assert len(route) > 2


def test_observation_candidates_have_no_zero_utility():
    grid = np.full((30, 30), -1)
    grid[5:25, 5:25] = 0
    data = control.prepare_frontier_data(grid, 0.1)
    point = next(iter(data[2].values()))[0]
    position = control.grid_to_world(point.row, point.column, 0.1, 0, 0)
    candidates, _ = control.robot_candidate_assignments(
        grid, 0.1, (0, 0), "tb1", position, [], data
    )
    assert all(utility > 0 for utility, *_ in candidates)


def rally_budget_node(energy=25.0):
    from types import SimpleNamespace

    messages, failures = [], []
    state = {"energy": energy, "capacity": 100.0, "charge_target_fraction": .8,
             "charge_x": 1.05, "charge_y": 1.05, "move_cost_per_m": 1.0,
             "idle_cost_per_sec": .02, "return_path_factor": 2.0,
             "nominal_speed_mps": .18, "return_safety_margin": 8.0}
    node = SimpleNamespace(
        rally_dispatch_order=["tb1"], rally_charge_requested={}, now=lambda: 11.0,
        rally_precharge_staging={},
        battery_modes={"tb1": "ACTIVE"}, battery_states={"tb1": state},
        battery_state_received_at={}, robot_positions={"tb1": (1.05, 1.05)},
        rally_goal_handles={"tb1": None}, rally_goal_pending={"tb1": False},
        rally_final_targets={"tb1": control.RallyPose(8.05, 1.05, 0)},
        map_data=np.zeros((30, 100), dtype=int), resolution=.1, origin=(0., 0.),
        rally_hold_sec=5.0, fail_task=failures.append,
        charge_request_publishers={"tb1": SimpleNamespace(publish=messages.append)},
        get_logger=lambda: SimpleNamespace(warn=lambda *args: None, info=lambda *args: None),
    )
    return node, messages, failures


def test_rally_preflight_reserves_return_from_final_pose_and_holds_until_resume():
    import json
    from types import SimpleNamespace

    node, messages, failures = rally_budget_node()
    # The old current-home budget admits this trip; its final-home budget does not.
    assert control.battery_assignment_is_safe(25, 7, 0, 1, .02, 2, .18, 8)
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1"}
    event = json.loads(messages[0].data)
    assert event["required_energy"] == pytest.approx(33.3777777778)
    assert event["available_energy"] == 25 and not failures
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1"}
    assert len(messages) == 1  # retries cannot flood the command route
    node.battery_modes["tb1"] = "CHARGING"
    node.rally_precharge_staging['tb1'] = event['required_energy']
    control.HeadquartersControl.battery_state_callback(node, SimpleNamespace(data=json.dumps({
        **node.battery_states["tb1"], "mode": "ACTIVE", "energy": 80.0, "stamp_sec": 12.0,
    })), "tb1")
    assert not node.rally_charge_requested
    assert not node.rally_precharge_staging
    assert control.HeadquartersControl.prepare_rally_charges(node) == set()
    assert len(messages) == 1


def test_rally_preflight_does_not_request_charge_with_sufficient_energy():
    node, messages, failures = rally_budget_node(energy=40.0)
    assert control.HeadquartersControl.prepare_rally_charges(node) == set()
    assert not messages and not failures


def test_rally_preflight_blocks_invalid_battery_state_without_making_a_command():
    node, messages, failures = rally_budget_node()
    del node.battery_states["tb1"]["energy"]
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1"}
    assert not messages and not failures


def test_rally_preflight_reports_a_trip_that_even_full_charge_cannot_support():
    node, messages, failures = rally_budget_node()
    node.battery_states["tb1"]["move_cost_per_m"] = 10.0
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1"}
    assert failures == ["rally_energy_capacity_insufficient:tb1"] and not messages


def test_rally_preflight_leaves_an_active_leg_and_unknown_route_to_existing_safety():
    node, messages, failures = rally_budget_node()
    node.rally_goal_handles["tb1"] = object()
    assert control.HeadquartersControl.prepare_rally_charges(node) == set()
    node.rally_goal_handles["tb1"] = None
    node.map_data[:, 50:55] = 100
    assert control.HeadquartersControl.prepare_rally_charges(node) == set()
    assert not messages and not failures


def two_robot_rally_budget_node():
    node, messages, failures = rally_budget_node()
    node.rally_dispatch_order.append("tb2")
    for field in ("battery_states", "robot_positions", "rally_goal_handles",
                  "rally_goal_pending", "rally_final_targets", "charge_request_publishers",
                  "battery_modes"):
        values = getattr(node, field)
        values["tb2"] = dict(values["tb1"]) if field == "battery_states" else values["tb1"]
    node.robot_positions["tb1"] = (3.05, 1.05)
    return node, messages, failures


def test_early_rally_charges_are_serialized_and_nearest_charger_goes_first():
    import json
    node, messages, failures = two_robot_rally_budget_node()
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1", "tb2"}
    assert [json.loads(m.data)["robot"] for m in messages] == ["tb2"]
    # While delivery is pending only its owner can retry, even if priorities change.
    node.now = lambda: 14.0
    node.robot_positions["tb1"] = (1.05, 1.05)
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1", "tb2"}
    assert [json.loads(m.data)["robot"] for m in messages] == ["tb2", "tb2"]
    node.battery_modes["tb2"] = "RETURNING"
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1", "tb2"}
    assert len(messages) == 2
    node.battery_modes["tb2"] = "CHARGING"
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1", "tb2"}
    assert len(messages) == 2
    node.battery_modes["tb2"] = "ACTIVE"
    node.battery_states["tb2"]["energy"] = 80.0
    node.rally_charge_requested.clear()  # delivered ACTIVE transition clears it
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1"}
    assert json.loads(messages[-1].data)["robot"] == "tb1"
    assert not failures


@pytest.mark.parametrize("mode", ["RETURNING", "CHARGING"])
def test_existing_local_safety_return_defers_new_early_charge(mode):
    node, messages, failures = two_robot_rally_budget_node()
    node.battery_modes["tb2"] = mode
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1"}
    assert not messages and not failures


def test_contact_loss_waits_without_isolating_a_healthy_robot():
    from types import SimpleNamespace
    from unittest.mock import Mock
    node = SimpleNamespace(
        enable_battery=True, task_state="RALLY", fresh_target=lambda: True, stop_target_scan=lambda: False, fresh_robot_inputs=lambda: False,
        last_input_availability=False, now=lambda: 100.,
        last_input_diagnostic_at=100.,
        battery_monitor_started_at=0., battery_state_received_at={"tb1": 0.},
        battery_modes={"tb1": "ACTIVE"}, mark_robot_failed=Mock(),
        rally_hold_started_at=95.,
    )
    control.HeadquartersControl.update_mission(node)
    node.mark_robot_failed.assert_not_called()
    assert node.battery_modes == {"tb1": "ACTIVE"}
    assert node.rally_hold_started_at is None


def test_rally_wait_budget_prevents_a_parked_robot_returning_during_peer_charge():
    # tb2 can fund its own route and home reserve, but not tb1's 40s route
    # plus 60s return/charge. Previously it parked and later had to leave.
    states={"tb1":{"energy":25.,"idle_cost_per_sec":.02},
            "tb2":{"energy":21.,"idle_cost_per_sec":.02}}
    requirements, waits=control.rally_wait_requirements(
        {"tb1":30.,"tb2":20.},states,dict.fromkeys(states,"ACTIVE"),
        {"tb1":40.,"tb2":0.},{"tb1":60.,"tb2":60.})
    assert waits=={"tb1":60.,"tb2":100.}
    assert requirements==pytest.approx({"tb1":31.2,"tb2":22.})
    assert states["tb2"]["energy"]>20. and states["tb2"]["energy"]<requirements["tb2"]


def test_rally_wait_budget_does_not_charge_own_route_twice_or_include_failed_robot():
    requirements, waits=control.rally_wait_requirements(
        {"tb1":30.},{"tb1":{"energy":40.,"idle_cost_per_sec":.02}},
        {"tb1":"ACTIVE","tb2":"FAILED"},{"tb1":40.},{"tb1":60.,"tb2":100.})
    assert requirements=={"tb1":30.} and waits=={"tb1":0.}


def test_moving_leader_uses_short_corridor_prefix_instead_of_static_detour():
    grid = np.full((50, 100), 100, dtype=int)
    grid[19:31, 1:99] = 0
    grid[0:12, 17:89] = 0
    grid[0:31, 17:29] = grid[0:31, 77:89] = 0
    positions = {'follower': (1., 2.5), 'leader': (4., 2.5)}
    target = control.RallyPose(9., 2.5, 0.)
    static = control.plan_rally_leg(target, grid, .1, (0., 0.), positions['follower'],
        blocked_positions=control.rally_stationary_positions(positions, 'follower', set()))
    moving = control.plan_rally_leg(target, grid, .1, (0., 0.), positions['follower'],
        blocked_positions=control.rally_stationary_positions(positions, 'follower', {'leader'}))
    length = lambda route: sum(math.dist(a, b) for a, b in zip(route, route[1:]))
    assert length(static[1]) > length(moving[1]) + 2.
    reservation = ((4., 2.5), (5., 2.5), (6., 2.5), (7., 2.5), (8., 2.5))
    admitted = control.reserve_rally_prefix(moving, [reservation])
    assert admitted is not None and admitted[0].x < 3.3
    assert not control.routes_conflict(admitted[1], reservation)


def test_precharging_allows_safe_progress_but_protects_return_corridor():
    grid = np.zeros((80, 100), dtype=int)
    positions = {'ready': (1., 1.), 'returning': (5., 4.)}
    states = {'returning': {'charge_x': 5., 'charge_y': 1.}}
    routes = control.rally_return_reservations(grid, .1, (0., 0.), positions, states,
        {'ready': 'ACTIVE', 'returning': 'RETURNING'}, set())
    safe = control.plan_rally_leg(control.RallyPose(3., 1., 0.), grid, .1, (0., 0.), positions['ready'])
    crossing = control.plan_rally_leg(control.RallyPose(8., 1., 0.), grid, .1, (0., 0.), positions['ready'])
    assert control.reserve_rally_prefix(safe, list(routes.values())) == safe
    prefix = control.reserve_rally_prefix(crossing, list(routes.values()))
    assert prefix is not None and prefix[0].x < 4.3
    assert not control.routes_conflict(prefix[1], routes['returning'])
    # A not-yet-started early return gets the same protection.
    future = control.rally_return_reservations(grid, .1, (0., 0.), positions, states,
        dict.fromkeys(positions, 'ACTIVE'), {'returning'})
    assert future == routes


def test_unknown_return_route_waits_and_charging_keeps_physical_footprint():
    grid = np.full((40, 40), 100, dtype=int)
    grid[8:13, 8:13] = 0
    positions = {'tb1': (1., 1.)};states = {'tb1': {'charge_x': 3., 'charge_y': 3.}}
    assert control.rally_return_reservations(grid, .1, (0., 0.), positions, states,
        {'tb1': 'RETURNING'}, set()) is None
    assert control.rally_return_reservations(grid, .1, (0., 0.), positions, states,
        {'tb1': 'CHARGING'}, set()) == {'tb1': ((1., 1.),)}


def test_follower_cannot_park_across_a_leaders_later_leg():
    # The leader's first 1m leg is clear, but its next leg needs the follower's
    # final parking cell. Reserving only the current leg caused priority inversion.
    full = tuple((float(x), 0.) for x in range(5))
    follower = (control.RallyPose(3., 0., 0.),
                ((3., 3.), (3., 2.), (3., 1.), (3., 0.)))
    assert control.reserve_rally_prefix(follower, [full[:2]]) == follower
    intents = control.rally_priority_reservations(
        ['leader', 'follower'], 'follower', {'leader': full}, set())
    admitted = control.reserve_rally_prefix(follower, intents)
    assert admitted is not None and admitted[0].y == 2.
    assert not control.routes_conflict(admitted[1], full)
    disjoint = (control.RallyPose(4., 3., 0.), ((3., 3.), (4., 3.)))
    assert control.reserve_rally_prefix(disjoint, intents) == disjoint


def test_priority_approach_releases_only_completed_or_failed_leaders():
    order = ['leader', 'follower']
    assert control.rally_priority_reservations(order, 'leader', {}, set()) == []
    assert control.rally_priority_reservations(order, 'follower', {}, set()) is None
    assert control.rally_priority_reservations(order, 'follower', {}, {'leader'}) == []
    # An unfinished returning/charging leader reserves its future post-charge
    # approach too; a parked temporary yield is not a completed final approach.
    future = ((0., 0.), (1., 0.))
    assert control.rally_priority_reservations(
        order, 'follower', {'leader': future}, set()) == [future]


def test_energy_planning_reuses_complete_approaches_for_dispatch():
    node, _, _ = two_robot_rally_budget_node()
    control.HeadquartersControl.prepare_rally_charges(node)
    assert set(node.rally_approach_routes) == {'tb1', 'tb2'}
    for name, route in node.rally_approach_routes.items():
        assert route[0] == node.robot_positions[name]
        target = node.rally_final_targets[name]
        assert math.dist(route[-1], (target.x, target.y)) < node.resolution


def test_staged_motion_keeps_its_proven_charge_budget_and_serial_request():
    node, messages, failures = two_robot_rally_budget_node()
    node.rally_precharge_staging['tb1'] = 50.
    node.rally_goal_handles['tb1'] = object()
    node.battery_modes['tb2'] = 'CHARGING'
    assert control.HeadquartersControl.prepare_rally_charges(node) == {'tb1'}
    assert node.rally_charge_budgets['tb1'] == 50.
    assert not messages and not failures
    node.battery_modes['tb2'] = 'ACTIVE'
    node.battery_states['tb2']['energy'] = 80.
    node.rally_charge_requested.clear()
    control.HeadquartersControl.prepare_rally_charges(node)
    import json
    assert json.loads(messages[-1].data)['robot'] == 'tb1'
    assert json.loads(messages[-1].data)['required_energy'] == 50.


def test_staged_charge_intent_survives_an_unavailable_final_rally_route():
    node, messages, failures = rally_budget_node()
    node.rally_precharge_staging['tb1'] = 40.
    node.map_data[:, 50:55] = 100
    assert control.HeadquartersControl.prepare_rally_charges(node) == {'tb1'}
    assert node.rally_charge_budgets['tb1'] == 40.
    assert not messages and not failures


@pytest.mark.parametrize('conflicting', [False, True])
def test_waiting_precharge_moves_only_along_a_safe_home_prefix(conflicting):
    from types import SimpleNamespace
    names = ['returner', 'waiter']
    grid = np.zeros((80, 120), dtype=int)
    positions = {'returner': (2.05, 1.05 if conflicting else 5.05),
                 'waiter': (8.05, 1.05)}
    targets = dict.fromkeys(names, control.RallyPose(10.05, 1.05, 0.))
    sent = []
    node = SimpleNamespace(
        enable_battery=True, task_state='RALLY', fresh_robot_inputs=lambda: True,
        fresh_robot_poses=lambda: True, fresh_target=lambda: True, stop_target_scan=lambda: False, message_freshness_timeout_sec=5.,
        battery_state_received_at=dict.fromkeys(names, 10.),
        last_input_availability=True, now=lambda: 10., battery_monitor_started_at=0.,
        battery_modes={'returner': 'RETURNING', 'waiter': 'ACTIVE'},
        participating_robots=lambda: names,
        rally_dispatch_order=names, rally_charge_requested={}, rally_precharge_staging={},
        prepare_rally_charges=lambda: {'waiter'}, rally_charge_budgets={'waiter': 40.},
        rally_approach_routes={}, rally_preflight_complete=False, rally_precharge_active=False,
        battery_states={'returner': {'charge_x': 9.05, 'charge_y': positions['returner'][1]},
                        'waiter': {'charge_x': 1.05, 'charge_y': 1.05}},
        rally_max_concurrent=2, rally_leg_routes=dict.fromkeys(names, ()),
        rally_goal_handles=dict.fromkeys(names), rally_goal_pending=dict.fromkeys(names, False),
        rally_goal_started_at=dict.fromkeys(names), rally_arrived=dict.fromkeys(names, False),
        rally_hold_started_at=None, rally_yield_targets=set(), return_yield_targets={},
        rally_yield_requested=dict.fromkeys(names, False), rally_probe_targets=set(),
        rally_targets=targets.copy(), rally_final_targets=targets.copy(),
        survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        release_return_yields=lambda: None, yield_to_returning_robot=lambda: None,
        last_rally_dispatch_at=0., global_battery_rally_pause=False,
        rally_attempts=dict.fromkeys(names, 0), robot_positions=positions,
        map_data=grid, resolution=.1, origin=(0., 0.),
        get_logger=lambda: SimpleNamespace(info=lambda *a: None, warn=lambda *a: None),
    )
    def send(name, plan):
        sent.append((name, plan))
        node.rally_goal_pending[name] = True
    node.send_rally_goal = send
    control.HeadquartersControl.update_mission(node)
    if conflicting:
        assert not sent and not node.rally_precharge_staging
    else:
        assert sent[0][0] == 'waiter' and sent[0][1][0].x < positions['waiter'][0]
        assert node.rally_precharge_staging == {'waiter': 40.}
    assert node.rally_final_targets == targets and not node.rally_preflight_complete


@pytest.mark.parametrize('radius', [.8, 2.])
def test_return_refuge_protects_entire_charge_zone_and_visible_escape(radius):
    grid=np.zeros((120,120),dtype=int)
    origin=(-6.,-6.);resolution=.1
    position=(-.6,-.4);home=(0.,.45)
    _, route=control.plan_rally_leg(control.RallyPose(*home,0.),grid,resolution,origin,(-3.,-2.7))
    separation=max(control.RALLY_ROUTE_SEPARATION_M,radius+control.RALLY_DYNAMIC_CLEARANCE_M)
    refuge=control.rally_yield_pose(grid,resolution,origin,position,home,
        blocked_positions=[(-3.,-2.7)],reserved_routes=(route,),
        route_separation_m=separation,visible_only=True)
    assert refuge is not None
    pose,path=control.plan_rally_leg(refuge,grid,resolution,origin,position,
        control.MAX_NAVIGATION_LEG_M,[(-3.,-2.7)],visible_only=True)
    assert pose is not None
    assert math.dist((pose.x,pose.y),(refuge.x,refuge.y))<.05
    assert min(math.dist((pose.x,pose.y),point) for point in route)>=separation
    assert math.dist((pose.x,pose.y),home)>=radius+control.RALLY_DYNAMIC_CLEARANCE_M
    distances=[min(math.dist(point,p) for p in route) for point in path]
    assert all(b+resolution>=min(a,separation) for a,b in zip(distances,distances[1:]))


def test_return_refuge_does_not_choose_an_occluded_intermediate_stop():
    grid=np.zeros((80,100),dtype=int)
    grid[10:70,48:52]=100
    position=(4.,4.);route=((4.,3.),(4.,4.),(4.,5.))
    refuge=control.rally_yield_pose(grid,.1,(0.,0.),position,(4.,5.),
        reserved_routes=(route,),route_separation_m=1.8,visible_only=True)
    assert refuge is not None
    pose,path=control.plan_rally_leg(refuge,grid,.1,(0.,0.),position,visible_only=True)
    assert pose is not None and math.dist((pose.x,pose.y),(refuge.x,refuge.y))<.05
    assert min(math.dist((pose.x,pose.y),p) for p in route)>=1.8





def test_local_return_wait_does_not_enter_unreserved_rally_recovery(monkeypatch):
    from types import SimpleNamespace
    names=['returner','waiter'];targets=dict.fromkeys(names,control.RallyPose(10.,1.,0.))
    monkeypatch.setattr(control,'rally_return_reservations',lambda *args:{'returner':((2.,1.),(9.,1.))})
    monkeypatch.setattr(control,'plan_rally_leg',lambda *args,**kwargs:(None,()))
    node=SimpleNamespace(
        enable_battery=True,task_state='RALLY',fresh_robot_inputs=lambda:True,
        fresh_robot_poses=lambda:True,fresh_target=lambda:True,stop_target_scan=lambda:False,message_freshness_timeout_sec=5.,
        battery_state_received_at=dict.fromkeys(names,10.),last_input_availability=True,
        now=lambda:10.,battery_monitor_started_at=0.,participating_robots=lambda:names,
        battery_modes={'returner':'RETURNING','waiter':'ACTIVE'},battery_states={},
        rally_dispatch_order=names,rally_charge_requested={},rally_precharge_staging={},
        prepare_rally_charges=lambda:set(),rally_approach_routes={},
        rally_preflight_complete=False,rally_precharge_active=False,
        rally_max_concurrent=2,rally_leg_routes=dict.fromkeys(names,()),
        rally_goal_handles=dict.fromkeys(names),rally_goal_pending=dict.fromkeys(names,False),
        rally_goal_started_at=dict.fromkeys(names),rally_arrived=dict.fromkeys(names,False),
        rally_hold_started_at=None,rally_yield_targets=set(),return_yield_targets={},
        rally_yield_requested=dict.fromkeys(names,False),rally_probe_targets=set(),
        rally_targets=targets.copy(),rally_final_targets=targets.copy(),
        rally_route_unavailable_since=dict.fromkeys(names,0.),
        rally_recovery_requested=dict.fromkeys(names,False),rally_attempts=dict.fromkeys(names,0),
        survey_robot=None,survey_goal_handle=None,survey_goal_pending=False,
        release_return_yields=lambda:None,yield_to_returning_robot=lambda:None,
        last_rally_dispatch_at=0.,global_battery_rally_pause=False,
        robot_positions={'returner':(2.,1.),'waiter':(8.,1.)},
        map_data=np.zeros((20,120),dtype=int),resolution=.1,origin=(0.,0.),
        get_logger=lambda:SimpleNamespace(info=lambda *a:None,warn=lambda *a:None),
        send_rally_goal=lambda *args:pytest.fail('unsafe recovery dispatch'),
        send_survey_goal=lambda *args:pytest.fail('unsafe probe dispatch'),
        fail_task=lambda *args:pytest.fail('temporary return obstruction is not route failure'))
    control.HeadquartersControl.update_mission(node)
    assert node.rally_route_unavailable_since['waiter'] is None
    assert node.rally_targets==targets and node.rally_final_targets==targets
@pytest.mark.parametrize("kind", ["pose_state", "frame_state"])
def test_received_pose_and_tf_keep_their_two_second_source_lease(kind):
    from types import SimpleNamespace
    node = SimpleNamespace(
        now=lambda: 100., message_freshness_timeout_sec=5.,
        input_robot_names=lambda: ["tb1"],
        robot_odom_received_at={"tb1": 100.}, robot_tf_received_at={"tb1": 100.},
    )
    timestamps = node.robot_odom_received_at if kind == "pose_state" else node.robot_tf_received_at
    timestamps["tb1"] = 98.
    assert control.HeadquartersControl.fresh_robot_poses(node)
    timestamps["tb1"] = 97.999
    assert not control.HeadquartersControl.fresh_robot_poses(node)
    timestamps["tb1"] = 100.001
    assert not control.HeadquartersControl.fresh_robot_poses(node)
    node.message_freshness_timeout_sec = 1.
    timestamps["tb1"] = 98.9
    assert not control.HeadquartersControl.fresh_robot_poses(node)


@pytest.mark.parametrize("field", ["map_received_at", "robot_map_received_at", "battery_state_received_at"])
def test_general_freshness_setting_cannot_extend_map_or_battery_ttl(field):
    from types import SimpleNamespace
    node = SimpleNamespace(
        now=lambda: 100., message_freshness_timeout_sec=10., enable_battery=True,
        map_received_at=100., robot_map_received_at={"tb1": 100.},
        battery_state_received_at={"tb1": 100.},
        participating_robots=lambda: ["tb1"], input_robot_names=lambda: ["tb1"],
        fresh_robot_poses=lambda: True, fresh_target=lambda: True, stop_target_scan=lambda: False,
    )
    if field == "map_received_at": node.map_received_at = 94.999
    else: getattr(node, field)["tb1"] = 94.999
    assert not control.HeadquartersControl.fresh_robot_inputs(node)


def test_freshness_diagnostics_preserve_missing_and_expired_source_stamps():
    from types import SimpleNamespace
    node = SimpleNamespace(
        now=lambda: 100., message_freshness_timeout_sec=5., enable_battery=True, task_state="EXPLORE",
        map_received_at=99., robot_map_received_at={"tb1": 99.},
        robot_odom_received_at={"tb1": 99.}, robot_tf_received_at={"tb1": None},
        battery_state_received_at={"tb1": 90.},
        participating_robots=lambda: ["tb1"], input_robot_names=lambda: ["tb1"],
    )
    details = control.HeadquartersControl.input_freshness_details(node)
    assert details["tb1/frame_state"] == {"source_time": None, "age_sec": None, "ttl_sec": 2.}
    assert details["tb1/battery_state"] == {"source_time": 90., "age_sec": 10., "ttl_sec": 5.}


def test_blocked_coarse_viewpoint_is_refined_in_the_safe_reachable_component():
    from types import SimpleNamespace
    grid = np.full((100, 100), -1, dtype=int)
    grid[20:80, 20:80] = 0
    groups, mask, _ = control.prepare_frontier_data(grid, .1)
    point = control.Viewpoint(0, 50, 78, 50, 79, 1000, len(groups[0]))
    coarse = (groups, mask, {0: [point]})
    positions = {"tb1": (3.05, 5.05), "parked": (7.85, 5.05)}
    candidates, _ = control.robot_candidate_assignments(
        grid, .1, (0., 0.), "tb1", positions["tb1"], frontier_data=coarse)
    assert candidates
    for _, _, _, candidate in candidates:
        assert control.plan_rally_leg(
            control.RallyPose(candidate.x, candidate.y, 0.), grid, .1, (0., 0.),
            positions["tb1"], blocked_positions=[positions["parked"]])[0] is None
    sent = []
    node = SimpleNamespace(
        task_state="EXPLORE", map_data=grid, resolution=.1, origin=(0., 0.),
        robot_positions=positions, robot_maps=dict.fromkeys(positions, {}),
        robot_states=dict.fromkeys(positions, "idle"),
        battery_modes={"tb1": "ACTIVE", "parked": "CHARGING"},
        frontier_cache=coarse, input_robot_names=lambda: ["tb1"],
        participating_robots=lambda: list(positions), fresh_robot_inputs=lambda: True,
        active_exclusions=lambda: [], battery_assignment_safe=lambda *a: True,
        goal_routes={}, goal_targets={}, goal_initial_gain={},
        target_information_gain=lambda *a: 1000,
        now=lambda: 100., last_no_assignment_log=-math.inf,
        get_logger=lambda: SimpleNamespace(info=lambda *a: None, warn=lambda *a: None),
        send_goal=lambda name, goal: sent.append((name, goal)))
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(sent) == 1 and sent[0][0] == "tb1"
    route = node.goal_routes["tb1"]
    assert math.dist(route[0], route[-1]) > control.NAVIGATION_POSITION_TOLERANCE_M
    assert all(math.dist(p, positions["parked"]) >= .6 for p in route)
    assert sent[0][1].viewpoint.information_gain > 0


def test_target_lease_requires_new_delivered_confirmation_and_keeps_task_phase():
    import json
    from types import SimpleNamespace
    from std_msgs.msg import String
    emitted, phases = [], []
    node = SimpleNamespace(
        task_state="EXPLORE", target=None, target_received_source_time=None,
        now=lambda: 100., enable_rally=True,
        consumed_publisher=SimpleNamespace(publish=emitted.append),
        get_logger=lambda: SimpleNamespace(error=lambda *a: None, info=lambda *a: None))
    def phase(value):
        phases.append(value)
        node.task_state = value
    node.publish_task_state = phase
    def deliver(stamp, target=(1., 2.)):
        event = {"robot": "tb1", "target_x": target[0], "target_y": target[1],
                 "stamp_sec": stamp, "_gateway": {"source_time": stamp, "delivery_time": 100.}}
        control.HeadquartersControl.target_detection_callback(node, String(data=json.dumps(event)))
    deliver(39.9)
    assert node.target is None and not phases
    deliver(40.)
    assert phases == ["FOUND"] and node.target == (1., 2.)
    assert control.HeadquartersControl.fresh_target(node)
    node.task_state = "RALLY"
    node.now = lambda: 100.001
    assert not control.HeadquartersControl.fresh_target(node)
    deliver(40.)  # Receipt of an old version does not renew the lease.
    assert node.target_received_source_time == 40.
    deliver(90., (3., 4.))
    assert node.target_received_source_time == 40. and node.target == (1., 2.)
    deliver(90.)
    assert node.task_state == "RALLY" and phases == ["FOUND"]
    assert control.HeadquartersControl.fresh_target(node)
    assert [json.loads(m.data)["event"] for m in emitted] == ["consumed", "target_reconfirmed"]


def test_expired_target_blocks_rally_decisions_without_blocking_local_return_yield():
    from types import SimpleNamespace
    yields = []
    node = SimpleNamespace(
        task_state="RALLY", enable_battery=False, fresh_robot_inputs=lambda: True,
        fresh_robot_poses=lambda: True, fresh_target=lambda: False, reacquire_target_by_scanning=lambda: None,
        last_input_availability=False, last_input_diagnostic_at=100., now=lambda: 100.,
        rally_hold_started_at=95., yield_to_returning_robot=lambda: yields.append(True))
    control.HeadquartersControl.update_mission(node)
    assert node.rally_hold_started_at is None and yields == [True]


def target_scan_node():
    from types import SimpleNamespace
    from builtin_interfaces.msg import Time
    goals, decisions = [], []
    request = SimpleNamespace(add_done_callback=lambda callback: None)
    client = SimpleNamespace(server_is_ready=lambda: True,
                             send_goal_async=lambda goal: (goals.append(goal) or request))
    node = SimpleNamespace(
        task_state="FOUND", target=(1000., -1000.), fresh_target=lambda: False,
        fresh_robot_inputs=lambda: True, clock=100., resolution=.1, origin=(0., 0.),
        map_data=np.zeros((50, 50), dtype=int),
        battery_modes={"tb1": "ACTIVE", "tb2": "ACTIVE"},
        participating_robots=lambda: ["tb1", "tb2"],
        robot_positions={"tb1": (1., 1.), "tb2": (3., 3.)},
        robot_states={"tb1": "idle", "tb2": "idle"},
        goal_handles={}, rally_goal_handles={}, rally_goal_pending={},
        survey_goal_handle=None, survey_goal_pending=False,
        robot_nav_clients=dict.fromkeys(("tb1", "tb2"), client),
        target_scan_robot=None, target_scan_handle=None, target_scan_cancel_requested=False,
        target_scan_steps={}, target_scan_finished_at={},
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: Time(sec=100))),
        get_logger=lambda: SimpleNamespace(info=lambda *a: None, warning=lambda *a: None),
        record_navigation_decision=lambda *args: decisions.append(args))
    node.now = lambda: node.clock
    node.target_scan_response = lambda f: control.HeadquartersControl.target_scan_response(node, f)
    node.target_scan_result = lambda f: control.HeadquartersControl.target_scan_result(node, f)
    node.finish_target_scan = lambda: control.HeadquartersControl.finish_target_scan(node)
    node.stop_target_scan = lambda: control.HeadquartersControl.stop_target_scan(node)
    return node, goals, decisions


def test_blind_scan_holds_live_position_and_covers_four_headings_without_old_target_geometry():
    node, goals, decisions = target_scan_node()
    for index in range(8):
        control.HeadquartersControl.reacquire_target_by_scanning(node)
        name = "tb1" if index < 4 else "tb2"
        pose = goals[-1].pose.pose
        assert (pose.position.x, pose.position.y) == node.robot_positions[name]
        yaw = (index % 4)*math.pi/2
        assert pose.orientation.z == pytest.approx(math.sin(yaw/2))
        assert pose.orientation.w == pytest.approx(math.cos(yaw/2))
        assert decisions[-1][:2] == (name, "target_reacquisition_scan")
        assert node.target == (1000., -1000.)
        node.finish_target_scan()
    control.HeadquartersControl.reacquire_target_by_scanning(node)
    assert len(goals) == 8  # finite full turns, then cooldown, not a busy loop
    node.clock = 130.001
    control.HeadquartersControl.reacquire_target_by_scanning(node)
    assert len(goals) == 9 and node.target_scan_robot == "tb1"


@pytest.mark.parametrize("block", ["stale", "return", "explore", "rally", "survey", "unknown_cell"])
def test_scan_waits_for_fresh_safe_idle_inputs_and_never_preempts_local_return(block):
    node, goals, _ = target_scan_node()
    if block == "stale": node.fresh_robot_inputs = lambda: False
    elif block == "return": node.battery_modes["tb2"] = "RETURNING"
    elif block == "explore": node.robot_states["tb2"] = "active"
    elif block == "rally": node.rally_goal_pending["tb2"] = True
    elif block == "survey": node.survey_goal_pending = True
    else: node.map_data[:] = -1
    control.HeadquartersControl.reacquire_target_by_scanning(node)
    assert not goals and node.target_scan_robot is None


def test_scan_cancel_persists_across_a_late_goal_acceptance_and_drains_before_resume():
    from types import SimpleNamespace
    node, goals, _ = target_scan_node()
    control.HeadquartersControl.reacquire_target_by_scanning(node)
    assert node.stop_target_scan() and node.target_scan_cancel_requested
    cancellations, completions = [], []
    handle = SimpleNamespace(accepted=True, cancel_goal_async=lambda: cancellations.append(True),
        get_result_async=lambda: SimpleNamespace(add_done_callback=completions.append))
    node.target_scan_response(SimpleNamespace(result=lambda: handle))
    assert cancellations == [True] and node.stop_target_scan()
    assert cancellations == [True]  # idempotent cancellation
    completions[0](SimpleNamespace(result=lambda: None))
    assert node.target_scan_robot is None and not node.stop_target_scan()


def test_charged_observer_is_not_blocked_by_waiting_outbound_intent():
    order = ["waiting", "charged"]
    modes = {"waiting": "ACTIVE", "charged": "ACTIVE"}
    routes = {"charged": ((0., 0.), (4., 0.))}
    # An unplanned future route for the old leader stopped all ready progress.
    assert control.rally_priority_reservations(order, "charged", routes, set()) is None
    ready = control.rally_energy_ready_order(order, {"waiting"}, modes)
    assert ready == ["charged", "waiting"]
    reservations = control.rally_priority_reservations(ready, "charged", routes, set())
    plan = (control.RallyPose(4., 0., 0.), ((0., 0.), (1., 0.), (2., 0.), (3., 0.), (4., 0.)))
    assert control.reserve_rally_prefix(plan, reservations) == plan
    # Ready priority cannot bypass a real safety-return corridor.
    protected_return = ((2., -1.), (2., 1.))
    limited = control.reserve_rally_prefix(plan, [protected_return])
    assert limited is None or limited[0].x < 2.


def test_ready_approach_partition_preserves_order_and_defers_inactive_robots():
    order = ["returner", "charged", "charging", "waiting", "also_ready"]
    modes = dict.fromkeys(order, "ACTIVE")
    modes.update(returner="RETURNING", charging="CHARGING")
    assert control.rally_energy_ready_order(order, {"waiting"}, modes) == [
        "charged", "also_ready", "returner", "charging", "waiting",
    ]
    assert order == ["returner", "charged", "charging", "waiting", "also_ready"]


def test_return_fixture_pauses_only_dispatch_and_resumes_without_stopping_dds():
    from types import SimpleNamespace
    node = SimpleNamespace(return_probe_paused=True)
    # No input accesses or goal dispatch while preparing the supplemental probe.
    control.HeadquartersControl.assign_idle_robots(node)
    control.HeadquartersControl.update_mission(node)
    control.HeadquartersControl.resume_return_probe(node)
    assert node.return_probe_paused is False


def test_multi_robot_preflight_budgets_one_extra_recovery_leg_out_and_back():
    node, messages, failures = two_robot_rally_budget_node()
    for state in node.battery_states.values():
        state["energy"] = 40.0
    blocked = control.HeadquartersControl.prepare_rally_charges(node)
    assert blocked and messages and not failures
    # Before contingency, tb2 could fund the nominal trip plus the peer wait.
    distance = 7.0
    state = node.battery_states["tb2"]
    nominal = control.battery_assignment_required_energy(distance, distance, 1., .02, 2., .18, 8.) + .02 * 5
    assert nominal < 40.
    allowance = 2 * control.MAX_NAVIGATION_LEG_M * (1. + .02 / .18)
    assert node.rally_charge_budgets["tb2"] >= nominal + allowance
