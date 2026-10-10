import math

import numpy as np
import pytest

from geometry_msgs.msg import Transform

from multi_robot_exploration import control


def static_planning_sources(node):
    """Supply original static DDS source leases for geometry-only fixtures."""
    if not hasattr(node, 'now'):
        node.now = lambda: 100.
    stamp = node.now()
    streams = ['headquarters/fused_map_snapshot', *[
        name+'/'+kind for name in node.input_robot_names()
        for kind in ('pose_state', 'frame_state', 'map_snapshot')]]
    node.input_freshness_details = lambda: {
        key: dict(source_time=stamp, age_sec=node.now()-stamp,
                  ttl_sec=control.STATE_TTL_SEC[key.rsplit('/', 1)[1]]) for key in streams}


@pytest.mark.parametrize('change', ['wall', 'connected', 'unknown', 'boundary', 'coarse', 'untracked'])
def test_body_cell_filter_preserves_static_and_unobserved_constraints(change):
    grid = np.zeros((30, 30), dtype=np.int16)
    grid[15, 15] = 100
    position = (.775, .775)
    resolution = .05
    if change == 'wall': grid[15, :] = 100
    if change == 'connected': grid[16, 16] = 100
    if change == 'unknown': grid[14, 15] = -1
    if change == 'boundary': grid[0, 0] = 100; position = (.025, .025)
    if change == 'coarse': resolution = .1; position = (1.55, 1.55)
    if change == 'untracked': position = (.525, .525)
    before = grid.copy()
    planned, cells = control.planning_grid_without_self_returns(grid, resolution, (0., 0.), {'tb1': position})
    assert not cells and np.array_equal(planned, before)
    assert np.array_equal(grid, before)


def test_isolated_self_return_does_not_release_a_peer_body():
    grid = np.zeros((80, 80), dtype=np.int16)
    grid[20, 20] = 100
    planned, cells = control.planning_grid_without_self_returns(grid, .05, (0., 0.), {'tb1': (1.025, 1.025)})
    assert cells == {'tb1': (20, 20)} and planned[20, 20] == 0 and grid[20, 20] == 100
    blocked = control.block_dynamic_positions(control.traversable_grid(planned, .05), .05, (0., 0.), [(1.025, 1.025)])
    assert not blocked[20, 20]
    assert control.navigation_start_cell(grid, control.traversable_grid(grid, .05), (20, 20), 12) is None


@pytest.mark.parametrize('stale', ['none', 'pose', 'frame', 'local_map', 'fused_map'])
def test_planning_self_return_requires_existing_source_leases(stale):
    from pathlib import Path
    from types import SimpleNamespace
    import yaml
    config = yaml.safe_load((Path(__file__).resolve().parents[2]
        / 'slam_toolbox/config/mapper_params_online_multi_async.yaml').read_text())
    params = config['$(var namespace)/slam_toolbox']['ros__parameters']
    # A full producer period plus the scan/TF offset must still fit the lease.
    map_age = params['map_update_interval'] + params['transform_timeout']
    grid = np.zeros((30, 30), dtype=np.int16); grid[15, 15] = 100
    node = SimpleNamespace(
        source_map_data=grid, map_data=grid, map_self_return_cells={}, frontier_cache=object(),
        map_received_at=100. if stale != 'fused_map' else 94.9,
        message_freshness_timeout_sec=5., enable_battery=False, resolution=.05, origin=(0., 0.),
        robot_positions={'tb1': (.775, .775)}, robot_maps={'tb1': {}},
        robot_odom_received_at={'tb1': 100. if stale != 'pose' else 97.9},
        robot_tf_received_at={'tb1': 100. if stale != 'frame' else 97.9},
        robot_map_received_at={'tb1': 100. - map_age if stale != 'local_map' else 94.9},
        now=lambda: 100., input_robot_names=lambda: ['tb1'],
    )
    node.task_state='EXPLORE'
    node.input_freshness_details=lambda: control.HeadquartersControl.input_freshness_details(node)
    node.fresh_robot_poses=lambda: control.HeadquartersControl.fresh_robot_poses(node)
    ready=control.HeadquartersControl.fresh_robot_inputs(node)
    assert ready == (stale == 'none')
    assert node.map_data[15, 15] == (0 if ready else 100)
    assert grid[15, 15] == 100


def test_found_survey_success_is_processed_before_final_poses_exist():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from action_msgs.msg import GoalStatus
    handle=object()
    node=SimpleNamespace(survey_goal_handle=handle, survey_goal_started_at=1., survey_robot='tb1',
        survey_cancel_requested=False, rally_final_targets={}, battery_modes={'tb1': 'ACTIVE'},
        rally_probe_targets=set(), rally_probe_robot=None, survey_battery_preempted=False,
        rally_prepare_started_at=1., now=lambda: 20., get_logger=lambda: Mock())
    future=SimpleNamespace(result=lambda: SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    control.HeadquartersControl.survey_goal_result(node, handle, future)
    assert node.rally_prepare_started_at == 20. and node.survey_goal_handle is None


@pytest.mark.parametrize('pending', [False, True])
def test_peer_local_return_cancels_accepted_or_pending_survey(pending):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock
    handle=None if pending else Mock()
    names=('tb1','tb2')
    node=SimpleNamespace(battery_modes=dict.fromkeys(names,'ACTIVE'), battery_states={},
        battery_state_received_at={}, goal_handles=dict.fromkeys(names), cancel_requested=dict.fromkeys(names,False),
        battery_preempted={}, rally_goal_handles=dict.fromkeys(names), rally_battery_preempted={},
        task_state='FOUND', global_battery_rally_pause=False, survey_robot='tb1', survey_goal_handle=handle,
        survey_goal_pending=pending, survey_battery_preempted=False, survey_cancel_requested=False,
        now=lambda: 100., get_logger=lambda: Mock())
    control.HeadquartersControl.battery_state_callback(node, SimpleNamespace(data=json.dumps({'mode':'RETURNING','stamp_sec':100.})), 'tb2')
    assert node.survey_cancel_requested and node.survey_battery_preempted
    if handle is not None:handle.cancel_goal_async.assert_called_once()


def test_pending_survey_late_acceptance_honors_peer_return_cancellation():
    from types import SimpleNamespace
    from unittest.mock import Mock
    handle=Mock(); handle.accepted=True
    node=SimpleNamespace(survey_goal_pending=True, survey_goal_handle=None,
        survey_robot='tb1', battery_modes={'tb1':'ACTIVE'}, survey_cancel_requested=True,
        survey_battery_preempted=True, now=lambda: 100., survey_goal_result=Mock())
    control.HeadquartersControl.survey_goal_response(node, SimpleNamespace(result=lambda: handle))
    handle.cancel_goal_async.assert_called_once()
    assert not node.survey_goal_pending and node.survey_goal_handle is handle


@pytest.mark.parametrize('energy,reservation,admitted', [(40.,False,True),(9.,False,False),(40.,True,False)])
def test_optional_survey_funds_safe_prefix_and_respects_live_reservation(energy,reservation,admitted):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from builtin_interfaces.msg import Time
    client=Mock();client.server_is_ready.return_value=True
    grid=np.zeros((100,100),dtype=np.int16)
    states={'tb1':{'energy':energy,'charge_x':1.,'charge_y':1.,'move_cost_per_m':1.,
        'idle_cost_per_sec':.02,'return_path_factor':2.,'nominal_speed_mps':.18,'return_safety_margin':8.}}
    route=tuple((2.,y/10) for y in range(70)) if reservation else ()
    node=SimpleNamespace(fresh_robot_inputs=lambda: True, fresh_target=lambda: True,
        map_data=grid, resolution=.1, origin=(0.,0.), robot_positions={'tb1':(1.,1.),'tb2':(8.,8.)},
        now=lambda:100.,map_received_at=100.,robot_odom_received_at={'tb1':100.,'tb2':100.},
        battery_modes={'tb1':'ACTIVE','tb2':'ACTIVE'}, battery_states=states, rally_charge_requested={},
        rally_leg_routes={'tb1':(),'tb2':route}, rally_goal_handles={'tb1':None,'tb2':object() if reservation else None},
        rally_goal_pending={'tb1':False,'tb2':False}, survey_goal_handle=None, survey_goal_pending=False,
        rally_position_tolerance=.35, num_robots=2, rally_max_retries=2, survey_attempts=0,
        enable_battery=True, robot_nav_clients={'tb1':client}, record_navigation_decision=Mock(),
        survey_goal_response=Mock(), get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: Time(sec=100))))
    node.exploration_battery_factor=lambda *a: control.HeadquartersControl.exploration_battery_factor(node,*a)
    actual=control.HeadquartersControl.send_survey_goal(node,'tb1',control.RallyPose(7.,1.,0.))
    assert actual is admitted
    assert client.send_goal_async.called is admitted
    if admitted:
        goal=client.send_goal_async.call_args.args[0]
        assert math.dist((goal.pose.pose.position.x,goal.pose.pose.position.y),(1.,1.)) <= 5.1


@pytest.mark.parametrize("leg_yaw,success,arrived", [(0., True, False),
    (math.pi / 2, True, True), (math.pi / 2, False, False),
    (math.pi / 2 + 2 * math.pi, True, True)])
def test_near_final_waypoint_cannot_skip_final_requested_orientation(leg_yaw, success, arrived):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from action_msgs.msg import GoalStatus

    handle = object()
    node = SimpleNamespace(
        rally_goal_handles={"tb1": handle}, rally_goal_started_at={"tb1": 1.},
        rally_leg_routes={"tb1": ((1., 1.), (2., 2.))},
        rally_leg_poses={"tb1": control.RallyPose(1.99, 2., leg_yaw)},
        rally_yield_requested={"tb1": False}, rally_battery_preempted={"tb1": False},
        rally_targets={"tb1": control.RallyPose(2., 2., math.pi / 2)},
        battery_modes={"tb1": "ACTIVE"}, rally_attempts={"tb1": 0},
        robot_positions={"tb1": (1.99, 2.)}, rally_position_tolerance=.35,
        rally_arrived={"tb1": False}, rally_probe_targets=set(), rally_yield_targets=set(),
        get_logger=lambda: Mock(),
    )
    future = SimpleNamespace(result=lambda: SimpleNamespace(status=(
        GoalStatus.STATUS_SUCCEEDED if success else GoalStatus.STATUS_ABORTED)))
    control.HeadquartersControl.rally_goal_result(node, "tb1", handle, future)
    assert node.rally_arrived["tb1"] is arrived
    assert node.rally_goal_handles["tb1"] is None and not node.rally_leg_poses


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


@pytest.mark.parametrize("mode,home,enters_rally", [
    ("RETURNING", (1., 1.), True), ("CHARGING", (1., 1.), True),
    ("RETURNING", (float("nan"), 1.), False), ("RETURNING", (100., 100.), False),
])
def test_found_plans_returning_robot_from_home_without_dispatching_it(mode, home, enters_rally):
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["tb1", "tb2"]
    positions = {"tb1": (100., 100.), "tb2": (3., 3.)}
    phases = []
    node = SimpleNamespace(
        task_state="FOUND", enable_rally=True, enable_battery=True,
        fresh_robot_inputs=lambda: True, fresh_robot_poses=lambda: True, fresh_target=lambda: True,
        last_input_availability=True, now=lambda: 10., battery_monitor_started_at=0.,
        battery_state_received_at=dict.fromkeys(names, 10.), message_freshness_timeout_sec=5.,
        map_received_at=10., target_received_source_time=10.,
        robot_odom_received_at=dict.fromkeys(names, 10.),
        robot_tf_received_at=dict.fromkeys(names, 10.),
        robot_map_received_at=dict.fromkeys(names, 10.),
        participating_robots=lambda: names, stop_target_scan=lambda: False,
        goal_handles=dict.fromkeys(names), cancel_requested=dict.fromkeys(names, False),
        robot_states=dict.fromkeys(names, "idle"), active_batteries_ready=lambda: False,
        survey_goal_handle=None, survey_goal_started_at=None, survey_goal_pending=False,
        map_data=np.zeros((60, 100), dtype=int), resolution=.1, origin=(0., 0.), target=(6., 3.),
        rally_targets={}, rally_final_targets={}, robot_positions=positions.copy(),
        battery_modes={"tb1": mode, "tb2": "ACTIVE"},
        battery_states={name: {"charge_x": home[0] if name == "tb1" else 3.,
            "charge_y": home[1] if name == "tb1" else 3., "mode": mode if name == "tb1" else "ACTIVE",
            "energy": 1000., "capacity": 1000., "charge_target_fraction": .8} for name in names},
        rally_hold_sec=5., target_observing_robot="tb2",
        last_rally_assignment_attempt=0., rally_assignment_objective="minimax",
        use_map_safe_rally_order=False, detecting_robot="tb2",
        publish_rally_assignments=lambda: None, publish_task_state=phases.append,
        send_survey_goal=lambda *args: pytest.fail("Survey must not bypass a local return"),
        get_logger=lambda: Mock(),
    )
    control.HeadquartersControl.update_mission(node)
    assert phases == (["RALLY"] if enters_rally else [])
    assert node.robot_positions == positions  # Planning never forges a pose update.
    assert bool(node.rally_targets) is enters_rally
    assert node.goal_handles == dict.fromkeys(names)  # No returning robot action.


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


def rally_assignment_batteries(positions, **overrides):
    states = {name: {"mode": "ACTIVE", "energy": 80., "capacity": 100.,
        "charge_target_fraction": .8, "charge_x": .5, "charge_y": 1.5,
        "nominal_speed_mps": 1., "move_cost_per_m": 1., "idle_cost_per_sec": 0.,
        "return_path_factor": 2., "return_safety_margin": 0., "charge_duration_sec": 6.}
        for name in positions}
    for name, changes in overrides.items():
        states[name].update(changes)
    return states


def exploration_energy_node(**changes):
    from types import SimpleNamespace
    state={"energy":15., "charge_x":.5, "charge_y":1.5, "move_cost_per_m":1.,
           "idle_cost_per_sec":.02,"return_path_factor":2.,"nominal_speed_mps":.18,
           "return_safety_margin":8., **changes}
    return SimpleNamespace(enable_battery=True,battery_modes={"tb1":"ACTIVE"},
        battery_states={"tb1":state},robot_positions={"tb1":(.5,1.5)},
        map_data=np.zeros((100,100),dtype=int),resolution=.1,origin=(0.,0.),
        now=lambda:10.,map_received_at=10.,robot_odom_received_at={"tb1":10.})


def test_exploration_preference_reserves_return_from_frontier_endpoint():
    node=exploration_energy_node()
    assert control.battery_assignment_is_safe(15.,4.,0.,1.,.02,2.,.18,8.)
    required=control.battery_assignment_required_energy(4.,3.5+math.sqrt(.005),1.,.02,2.,.18,8.)
    factor=control.HeadquartersControl.exploration_battery_factor(node,"tb1",4.,(4.5,1.5))
    assert factor == pytest.approx(.25*15./required)
    assert 0 < factor < .25  # Rank useful unfunded frontiers for charge recovery.
    farther=control.HeadquartersControl.exploration_battery_factor(node,"tb1",7.,(7.5,1.5))
    assert 0 < farther < factor


def test_exploration_energy_preference_preserves_safe_and_disabled_candidates():
    node=exploration_energy_node(energy=80.)
    assert control.HeadquartersControl.exploration_battery_factor(node,"tb1",4.,(4.5,1.5)) == 1.
    node.enable_battery=False
    assert control.HeadquartersControl.exploration_battery_factor(node,"tb1",100.,(100.,1.5)) == 1.


@pytest.mark.parametrize("changes", [{"energy":float("nan")},{"nominal_speed_mps":0.},
    {"idle_cost_per_sec":-1.},{"charge_x":float("inf")}])
def test_exploration_energy_preference_rejects_invalid_context(changes):
    node=exploration_energy_node(**changes)
    assert control.HeadquartersControl.exploration_battery_factor(node,"tb1",4.,(4.5,1.5)) == 0.


@pytest.mark.parametrize("objective", ["minimax", "total_path"])
def test_rally_assignment_keeps_low_energy_observer_without_a_return(monkeypatch, objective):
    grid = np.zeros((80, 80), dtype=int)
    positions = {"tb1": (1.55, 1.55), "tb2": (5.55, 1.55), "tb3": (3.55, 1.55)}
    candidates = [control.RallyPose(x, 1.55, .25) for x in (1.55, 3.55, 5.55)]
    monkeypatch.setattr(control, "rally_pose_candidates", lambda *args, **kwargs: candidates)
    original = control.assign_rally_poses(grid, .1, (0., 0.), positions, (4., 4.), objective)
    states = rally_assignment_batteries(positions, tb2={"energy": 8.5})
    assignments = control.assign_rally_poses(grid, .1, (0., 0.), positions, (4., 4.),
        objective, battery_states=states, observer_robot="tb2")
    assert original["tb2"].x == 5.55  # Zero travel ignores its independent return reserve.
    assert assignments["tb2"].x in (1.55,3.55)
    selected=assignments["tb2"]
    home_distance,_=control.known_return_route(grid,.1,(0.,0.),(selected.x,selected.y),(.5,1.5),.8)
    assert control.battery_assignment_required_energy(abs(5.55-selected.x),home_distance,1.,0.,2.,1.,0.) < 8.5
    assert len(set(assignments.values())) == 3
    assert all(p.yaw == .25 for p in assignments.values())
    assert positions["tb2"] == (5.55, 1.55) and states["tb2"]["energy"] == 8.5


def test_rally_assignment_avoids_peer_charge_for_optional_observer_surplus(monkeypatch):
    grid = np.zeros((80, 80), dtype=int)
    positions = {"tb1": (1.55, 1.55), "tb2": (5.55, 1.55), "tb3": (3.55, 1.55)}
    candidates = [control.RallyPose(x, 1.55, .25) for x in (1.55, 3.55, 5.55)]
    monkeypatch.setattr(control, "rally_pose_candidates", lambda *args, **kwargs: candidates)
    states = rally_assignment_batteries(positions,
        tb1={"energy": 9.5}, tb2={"energy": 16.}, tb3={"energy": 9.5})
    assignments = control.assign_rally_poses(grid, .1, (0., 0.), positions, (4., 4.),
        battery_states=states, observer_robot="tb2")
    # Every stationary assignment funds its complete budget. Increasing the
    # observer's surplus by swapping would force a peer to charge needlessly.
    assert {name: (pose.x, pose.y) for name, pose in assignments.items()} == positions


@pytest.mark.parametrize("objective", ["minimax", "total_path"])
def test_rally_assignment_charged_peers_avoid_detours_for_observer_surplus(monkeypatch, objective):
    grid = np.zeros((80, 80), dtype=int)
    positions = {"tb1": (1.55, 1.55), "tb2": (5.55, 1.55), "tb3": (3.55, 1.55)}
    candidates = [control.RallyPose(x, 1.55, .25) for x in (1.55, 3.55, 5.55)]
    monkeypatch.setattr(control, "rally_pose_candidates", lambda *args, **kwargs: candidates)
    states = rally_assignment_batteries(positions)
    assignments = control.assign_rally_poses(grid, .1, (0., 0.), positions, (3.5, 3.5),
        objective, battery_states=states, observer_robot="tb2")
    # All have80 energy. Returning the observer toward home improves its
    # unused surplus, but makes two already-funded robots cross the map.
    assert {name: (pose.x, pose.y) for name, pose in assignments.items()} == positions
    assert all(pose.yaw == .25 for pose in assignments.values())


@pytest.mark.parametrize("mode", ["RETURNING", "CHARGING"])
def test_rally_assignment_inactive_observer_has_no_visual_headroom_priority(monkeypatch, mode):
    grid = np.zeros((80, 80), dtype=int)
    actual = {"tb1": (1.55, 1.55), "tb2": (5.55, 1.55), "tb3": (3.55, 1.55)}
    candidates = [control.RallyPose(x, 1.55, .25) for x in (1.55, 3.55, 5.55)]
    monkeypatch.setattr(control, "rally_pose_candidates", lambda *args, **kwargs: candidates)
    states = rally_assignment_batteries(actual, tb2={"mode": mode})
    planning = {**actual, "tb2": (.5, 1.5)}
    plain = control.assign_rally_poses(grid, .1, (0., 0.), planning, (4., 4.),
        battery_states=states, current_positions=actual)
    inactive = control.assign_rally_poses(grid, .1, (0., 0.), planning, (4., 4.),
        battery_states=states, current_positions=actual, observer_robot="tb2")
    assert inactive == plain
    assert actual["tb2"] == (5.55, 1.55)  # The home proxy never changes received poses.


@pytest.mark.parametrize("changes", [{"energy": float("nan")}, {"nominal_speed_mps": 0.},
    {"idle_cost_per_sec": -1.}, {"mode": "UNKNOWN"}, {"charge_target_fraction": 1.1},
    {"capacity": 0.}, {"charge_x": 100.}])
def test_rally_assignment_rejects_unusable_delivered_battery_context(changes):
    grid = np.zeros((70, 70), dtype=int)
    positions = {"tb1": (1.55, 1.55)}
    states = rally_assignment_batteries(positions, tb1=changes)
    assert not control.assign_rally_poses(grid, .1, (0., 0.), positions, (3.5, 3.5),
                                          battery_states=states)


def test_rally_assignment_rejects_charge_capacity_insufficient_for_safe_final_pose():
    grid = np.zeros((70, 70), dtype=int)
    positions = {"tb1": (1.55, 1.55)}
    states = rally_assignment_batteries(positions, tb1={"energy": 0., "capacity": .1})
    assert not control.assign_rally_poses(grid, .1, (0., 0.), positions, (3.5, 3.5),
                                          battery_states=states)


def test_rally_assignment_counts_peer_charge_wait_before_capacity_admission(monkeypatch):
    grid = np.zeros((70, 70), dtype=int)
    positions = {"tb1": (1.55, 1.55), "tb2": (3.55, 1.55)}
    candidates = [control.RallyPose(x, 1.55, 0.) for x in (1.55, 3.55)]
    monkeypatch.setattr(control, "rally_pose_candidates", lambda *args, **kwargs: candidates)
    states = rally_assignment_batteries(positions)
    for name, state in states.items():
        state.update(energy=0., capacity=10., move_cost_per_m=0., idle_cost_per_sec=.1,
                     charge_duration_sec=100., charge_x=positions[name][0], charge_y=1.55)
    # Either isolated trip fits an8-unit charge, but100s of the peer's charge
    # adds10 idle units. No complete assignment can satisfy the same preflight.
    assert not control.assign_rally_poses(grid, .1, (0., 0.), positions, (4., 4.),
                                          battery_states=states)


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


def test_blocked_rally_fallback_fills_deep_goals_before_parking_on_their_approach():
    grid = np.full((40, 100), 100, dtype=int)
    grid[10:21, 10:90] = 0
    positions = {"near": (3.55, 1.55), "middle": (1.55, 1.55), "deep": (2.55, 1.55)}
    targets = {name: control.RallyPose(x, 1.55, 0.)
               for name, x in (("near", 3.55), ("middle", 5.55), ("deep", 7.55))}
    order = control.map_safe_rally_dispatch_order(grid, .1, (0., 0.), targets,
                                                 positions, (8.55, 1.55), "near")
    assert order == ["deep", "middle", "near"]
    # A recovery priority is not permission to traverse the actual parked body.
    plan = control.plan_rally_leg(targets["deep"], grid, .1, (0., 0.), positions["deep"],
                                  blocked_positions=[positions["near"], positions["middle"]])
    assert plan[0] is None


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


@pytest.mark.parametrize('intermediate', [False, True])
def test_exploration_dispatch_carries_incoming_heading_only_for_intermediate_legs(monkeypatch, intermediate):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from builtin_interfaces.msg import Time

    grid = np.zeros((80, 80), dtype=int)
    if intermediate:
        grid[:55, 40] = 100
    position, target = (1., 3.), (6., 3.)
    point = control.Viewpoint(0, 30, 60, 31, 60, 1000, 10)
    assignment = control.Assignment(point, *target, 7., 10., *target)
    monkeypatch.setattr(control, 'robot_candidate_assignments', lambda *args, **kwargs:
                        ([(10., 'tb1', 0, assignment)], {'frontier_groups': 1, 'groups_with_viewpoints': 1}))
    client = Mock()
    client.server_is_ready.return_value = True
    node = SimpleNamespace(
        task_state='EXPLORE', map_data=grid, resolution=.1, origin=(0., 0.),
        robot_positions={'tb1': position}, robot_maps={'tb1': {}},
        robot_states={'tb1': 'idle'}, battery_modes={'tb1': 'ACTIVE'},
        frontier_cache=control.prepare_frontier_data(grid, .1), goal_targets={}, goal_routes={},
        goal_initial_gain={}, robot_nav_clients={'tb1': client},
        input_robot_names=lambda: ['tb1'], participating_robots=lambda: ['tb1'],
        fresh_robot_inputs=lambda: True, active_exclusions=lambda: [],
        exploration_battery_factor=lambda *args: 1., target_information_gain=lambda *args: 1000,
        get_logger=lambda: Mock(), record_navigation_decision=Mock(),
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: Time())),
    )
    node.send_goal=lambda name, goal: control.HeadquartersControl.send_goal(node, name, goal)
    static_planning_sources(node)
    control.HeadquartersControl.assign_idle_robots(node)
    admitted=node.goal_targets['tb1']
    goal=client.send_goal_async.call_args.args[0]
    actual=control.quaternion_yaw(goal.pose.pose.orientation)
    assert (goal.pose.pose.position.x, goal.pose.pose.position.y)==(admitted.navigation_x, admitted.navigation_y)
    if intermediate:
        assert admitted.navigation_yaw is not None
        assert actual==pytest.approx(control.route_arrival_yaw(node.goal_routes['tb1'], 0.))
    else:
        assert admitted.navigation_yaw is None
        frontier=control.grid_to_world(point.frontier_row, point.frontier_column, .1, 0., 0.)
        assert actual==pytest.approx(math.atan2(frontier[1]-admitted.navigation_y, frontier[0]-admitted.navigation_x))


def test_visible_intermediate_leg_faces_its_approach_before_a_wall_bend():
    grid = np.zeros((80, 80), dtype=int)
    grid[:55, 40] = 100
    target = control.RallyPose(6.0, 1.0, -0.7)
    leg, route = control.plan_rally_leg(
        target, grid, .1, (0., 0.), (2., 1.), 3.5, visible_only=True,
    )
    assert leg is not None and (leg.x, leg.y) != (target.x, target.y)
    assert leg.yaw == pytest.approx(math.pi/2)
    across_wall = math.atan2(target.y-leg.y, target.x-leg.x)
    assert abs(math.atan2(math.sin(leg.yaw-across_wall), math.cos(leg.yaw-across_wall))) > 1.
    final, _ = control.plan_rally_leg(target, grid, .1, (0., 0.), (6., 2.), 3.5, visible_only=True)
    assert final.yaw == target.yaw


def test_reserved_prefix_faces_incoming_leg_and_retains_original_reservation():
    route = tuple((x*.1, 0.) for x in range(31)) + ((3., .1), (3., 1.))
    plan = (control.RallyPose(3., 1., math.pi/2), route)
    admitted = control.reserve_rally_prefix(plan, [((3., 1.85),)])
    assert admitted is not None and admitted[1] == route[:31]
    assert admitted[0].yaw == pytest.approx(0.)
    assert control.reserve_rally_prefix(plan, []) is plan


@pytest.mark.parametrize('wall', (False, True))
def test_rally_order_cache_keeps_each_body_mask_and_stays_within_one_snapshot(monkeypatch, wall):
    grid = np.zeros((80, 100), dtype=int)
    if wall:
        grid[:, 50] = 100
        grid[30:50, 50] = 0
    positions = {'a': (1., 1.), 'b': (1., 4.), 'c': (2., 6.)}
    targets = {n: control.RallyPose(8., y, 0.) for n, y in zip(positions, (1., 4., 6.))}
    original = control.plan_rally_leg
    contexts = {}
    calls = []

    def capture(*args, **kwargs):
        cache = kwargs['route_cache']
        context = (args[4], tuple(kwargs.get('blocked_positions', ())))
        assert id(cache) not in contexts or contexts[id(cache)] == context
        contexts[id(cache)] = context
        result = original(*args, **kwargs)
        calls.append((cache, result))
        return result

    monkeypatch.setattr(control, 'plan_rally_leg', capture)
    cached = control.map_safe_rally_dispatch_order(grid, .1, (0., 0.), targets, positions, (9., 4.))
    cached_calls = list(calls)
    assert len(contexts) < len(calls)

    def uncached(*args, **kwargs):
        kwargs.pop('route_cache')
        result = original(*args, **kwargs)
        calls.append((None, result))
        return result

    calls.clear()
    monkeypatch.setattr(control, 'plan_rally_leg', uncached)
    reference = control.map_safe_rally_dispatch_order(grid, .1, (0., 0.), targets, positions, (9., 4.))
    assert cached == reference
    assert [result for _, result in cached_calls] == [result for _, result in calls]
    # A later map cannot inherit the earlier fields, even at the same poses.
    grid[:, 50] = 100
    calls.clear()
    monkeypatch.setattr(control, 'plan_rally_leg', capture)
    control.map_safe_rally_dispatch_order(grid, .1, (0., 0.), targets, positions, (9., 4.))
    assert all(new is not old for new, _ in calls for old, _ in cached_calls)
    assert all(not result[1] for _, result in calls)


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
        exploration_battery_factor=lambda *args: True,
        goal_targets={}, goal_routes={}, goal_initial_gain={"tb1": 0, "tb2": 0},
        target_information_gain=lambda *args: 1000,
        get_logger=lambda: SimpleNamespace(info=lambda *args: None, warn=lambda *args: None),
        send_goal=lambda name, goal: sent.append((name, goal)),
    )
    static_planning_sources(node)
    control.HeadquartersControl.assign_idle_robots(node)
    assert sent and {name for name, _ in sent} <= {"tb1", "tb2"}
    assert calls == [(1.0, 3.0), (3.0, 3.0)]
    for name, route in node.goal_routes.items():
        peer = "tb2" if name == "tb1" else "tb1"
        assert min(math.dist(point, node.robot_positions[peer]) for point in route) >= 0.55
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
    def candidates(*args, **kwargs):
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
        exploration_battery_factor=lambda *args: True,
        goal_targets={}, goal_routes={}, goal_initial_gain={},
        target_information_gain=lambda *args: 1000,
        get_logger=lambda: SimpleNamespace(info=lambda *args: None),
        send_goal=lambda name, goal: sent.append((name, goal)),
    )
    static_planning_sources(node)
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
        exploration_battery_factor=lambda *args: True,
        goal_targets={}, goal_routes={}, goal_initial_gain={},
        target_information_gain=lambda *args: 1000,
        now=lambda: 0.0, last_no_assignment_log=-math.inf,
        get_logger=lambda: SimpleNamespace(info=lambda *args: None, warn=lambda *args: None),
        send_goal=lambda name, goal: sent.append((name, goal)),
    )
    static_planning_sources(node)
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
        rally_leg_routes=dict.fromkeys(("tb1", "tb2"), ()),
        rally_yield_requested=dict.fromkeys(("tb1", "tb2"), False),
        rally_max_concurrent=2,
        survey_goal_handle=None, survey_goal_pending=False,
        rally_dispatch_order=["tb1", "tb2"],
        battery_modes={"tb1": "RETURNING", "tb2": "ACTIVE"},
        battery_states={"tb1": {"charge_x": 1.0, "charge_y": 3.0}},
        map_data=grid, resolution=0.1, origin=(0, 0),
        robot_positions={"tb1": (8.0, 3.0), "tb2": (5.0, 3.0)},
        rally_yield_targets=set(), return_yield_targets={}, rally_targets={"tb2": original},
        rally_recovery_beneficiaries={},
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


def test_canceled_return_escape_can_replan_for_two_actual_returners():
    from types import SimpleNamespace
    from unittest.mock import Mock
    names = ["first", "second", "escape"]
    final = control.RallyPose(4., 5., 0.)
    sent = []
    node = SimpleNamespace(
        now=lambda: 10., fresh_robot_inputs=lambda: True,
        rally_charge_requested={}, rally_precharge_staging={},
        rally_goal_handles=dict.fromkeys(names), rally_goal_pending=dict.fromkeys(names, False),
        rally_leg_routes=dict.fromkeys(names, ()), rally_yield_requested=dict.fromkeys(names, False),
        rally_max_concurrent=2, survey_goal_handle=None, survey_goal_pending=False,
        rally_dispatch_order=names,
        battery_modes={"first": "RETURNING", "second": "RETURNING", "escape": "ACTIVE"},
        battery_states={"first": {"charge_x": 1., "charge_y": 3.},
                        "second": {"charge_x": 5., "charge_y": 1.}},
        map_data=np.zeros((100, 100), dtype=int), resolution=.1, origin=(0., 0.),
        robot_positions={"first": (8., 3.), "second": (5., 8.), "escape": (5., 3.)},
        rally_yield_targets={"escape"}, return_yield_targets={"escape": "first"},
        rally_recovery_beneficiaries={}, rally_targets={"escape": control.RallyPose(5., 5., 0.)},
        rally_final_targets={"escape": final}, rally_arrived={"escape": False},
        rally_attempts={"escape": 0}, publish_rally_assignments=lambda: None,
        get_logger=lambda: Mock(), send_rally_goal=lambda name, plan: sent.append((name, plan)),
    )
    control.HeadquartersControl.yield_to_returning_robot(node)
    assert len(sent) == 1 and sent[0][0] == "escape"
    assert node.rally_final_targets["escape"] is final
    refuge = node.rally_targets["escape"]
    protected = control.rally_return_reservations(node.map_data, .1, (0., 0.),
        node.robot_positions, node.battery_states, node.battery_modes, set())
    assert all(not control.routes_conflict(((refuge.x, refuge.y),), route,
               control.RALLY_ROUTE_SEPARATION_M) for route in protected.values())
    node.rally_goal_handles["escape"] = Mock()
    node.last_return_yield_attempt_at = 0.
    control.HeadquartersControl.yield_to_returning_robot(node)
    assert len(sent) == 1  # A live replacement must drain before another admission.


@pytest.mark.parametrize("angular,linear,position", [(.19315, 0., 0.), (0., .051, 0.), (0., 0., .36)])
def test_delivered_odom_violation_resets_hold_before_the_next_timer(angular, linear, position):
    from types import SimpleNamespace
    from geometry_msgs.msg import Transform
    from nav_msgs.msg import Odometry
    transform = Transform()
    transform.rotation.w = 1.
    node = SimpleNamespace(
        task_state="RALLY", rally_hold_started_at=95.,
        rally_targets={"tb1": control.RallyPose(0., 0., 0.)},
        rally_linear_tolerance=.05, rally_angular_tolerance=.1, rally_position_tolerance=.35,
        robot_odom_received_at={}, robot_velocities={}, map_to_odom={"tb1": transform},
        robot_positions={}, robot_yaws={}, goal_last_position={"tb1": None}, robot_states={"tb1": "idle"},
    )
    message = Odometry()
    message.header.stamp.sec = 100
    message.twist.twist.angular.z = angular
    message.twist.twist.linear.x = linear
    message.pose.pose.position.x = position
    control.HeadquartersControl.robot_odom_callback(node, message, "tb1")
    assert node.rally_hold_started_at is None
    assert node.rally_last_hold_reset["reason"] == (
        "delivered_position" if position else "delivered_velocity")
    assert node.rally_last_hold_reset["source_time"] == 100.
    message.twist.twist.angular.z = message.twist.twist.linear.x = 0.
    message.pose.pose.position.x = 0.
    control.HeadquartersControl.robot_odom_callback(node, message, "tb1")
    assert node.rally_hold_started_at is None


@pytest.mark.parametrize('odom_yaw,tf_yaw', [(2.454, -.007), (3., .4), (-3., -.4)])
def test_delivered_heading_uses_the_same_map_frame_as_rally_goals(odom_yaw, tf_yaw):
    from types import SimpleNamespace
    from nav_msgs.msg import Odometry
    transform = Transform()
    transform.rotation.z, transform.rotation.w = math.sin(tf_yaw/2), math.cos(tf_yaw/2)
    node = SimpleNamespace(task_state='EXPLORE', robot_odom_received_at={}, robot_velocities={},
        map_to_odom={'tb2': transform}, robot_positions={}, robot_yaws={},
        goal_last_position={'tb2': None}, robot_states={'tb2': 'idle'})
    message = Odometry()
    message.pose.pose.orientation.z = math.sin(odom_yaw/2)
    message.pose.pose.orientation.w = math.cos(odom_yaw/2)
    control.HeadquartersControl.robot_odom_callback(node, message, 'tb2')
    expected = math.atan2(math.sin(odom_yaw+tf_yaw), math.cos(odom_yaw+tf_yaw))
    assert node.robot_yaws['tb2'] == pytest.approx(expected)


@pytest.mark.parametrize('condition', ['drift', 'wrapped', 'centered', 'busy', 'pending',
                                     'local_return', 'stale_inputs', 'stale_pose', 'stale_target',
                                     'returning', 'no_slot', 'route_conflict', 'non_observer',
                                     'no_yaw', 'nan_yaw', 'narrow_fov', 'recent_confirmation',
                                     'five_sec_confirmation', 'missing_confirmation'])
def test_parked_observer_corrects_heading_through_reserved_navigation(condition):
    from types import SimpleNamespace
    from unittest.mock import Mock
    names = ['peer', 'observer']
    desired = -math.pi+.1 if condition == 'wrapped' else 1.5657124565684668
    measured = math.pi-.1 if condition == 'wrapped' else 2.447
    if condition == 'centered': measured = desired+.2
    if condition == 'narrow_fov': measured = desired+.3
    if condition == 'no_yaw': measured = None
    if condition == 'nan_yaw': measured = float('nan')
    positions = {'peer': (6.05, 5.05), 'observer': (2.05, 2.05)}
    targets = {'peer': control.RallyPose(8.05, 5.05, 0.),
               'observer': control.RallyPose(2.05, 2.05, desired)}
    handles = {'peer': Mock(), 'observer': Mock() if condition == 'busy' else None}
    sent = []
    node = SimpleNamespace(
        enable_battery=False, task_state='RALLY', fresh_robot_inputs=lambda: condition != 'stale_inputs',
        fresh_robot_poses=lambda: condition != 'stale_pose', fresh_target=lambda: condition != 'stale_target',
        stop_target_scan=lambda: False, last_input_availability=True, last_input_diagnostic_at=10.,
        consumed_publisher=Mock(), input_freshness_details=lambda: {},
        input_robot_names=lambda: names,
        now=lambda: 10., participating_robots=lambda: names,
        rally_charge_requested={}, rally_precharge_staging={}, rally_max_concurrent=1 if condition == 'no_slot' else 2,
        rally_leg_routes={'peer': ((6.05, 5.05), positions['observer'] if condition == 'route_conflict' else (8.05, 5.05)), 'observer': ()},
        rally_goal_handles=handles, rally_goal_pending={'peer': False, 'observer': condition == 'pending'},
        rally_goal_started_at={'peer': 9., 'observer': 9. if handles['observer'] else None},
        goal_timeout_sec=60., rally_goal_timeout_sec=30.,
        rally_arrived={'peer': False, 'observer': True}, rally_hold_started_at=None,
        rally_yield_targets=set(), return_yield_targets={'observer': 'returner'} if condition == 'local_return' else {},
        rally_yield_requested=dict.fromkeys(names, False), rally_probe_targets=set(),
        rally_targets=targets.copy(), rally_final_targets=targets.copy(), rally_dispatch_order=names,
        battery_modes={'peer': 'ACTIVE', 'observer': 'RETURNING' if condition == 'returning' else 'ACTIVE'},
        survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        release_return_yields=lambda: None, yield_to_returning_robot=lambda: None,
        reacquire_target_by_scanning=lambda: None, last_rally_dispatch_at=0., global_battery_rally_pause=False,
        rally_attempts=dict.fromkeys(names, 0), rally_recovery_requested=dict.fromkeys(names, False),
        rally_route_unavailable_since=dict.fromkeys(names), robot_positions=positions,
        robot_velocities=dict.fromkeys(names, (0., 0.)),
        robot_yaws={'observer': measured}, target_observing_robot='unknown' if condition == 'non_observer' else 'observer',
        target_received_source_time={'recent_confirmation': 9., 'five_sec_confirmation': 5.,
                                     'missing_confirmation': None}.get(condition, 4.),
        target_view_fov_rad=math.pi/3 if condition == 'narrow_fov' else math.pi/2,
        map_data=np.zeros((100, 100), dtype=int), resolution=.1, origin=(0., 0.),
        rally_position_tolerance=.35, target=(2.05, 4.05), get_logger=lambda: Mock(),
    )
    def send(name, plan, charge_staging=False):
        assert not charge_staging and name == 'observer'
        assert not control.routes_conflict(plan[1], node.rally_leg_routes['peer'], control.RALLY_ROUTE_SEPARATION_M)
        sent.append(plan)
        node.rally_goal_pending[name] = True
    node.send_rally_goal = send
    control.HeadquartersControl.update_mission(node)
    assert bool(sent) == (condition in ('drift', 'narrow_fov'))
    if sent:
        assert sent[0][0].yaw == pytest.approx(desired)
        assert math.dist((sent[0][0].x, sent[0][0].y), positions['observer']) < .01
        assert not node.rally_arrived['observer']
        control.HeadquartersControl.update_mission(node)
        assert len(sent) == 1
    assert node.rally_final_targets == targets


@pytest.mark.parametrize("pending", [False, True])
def test_new_local_return_preempts_only_conflicting_admitted_rally_legs(pending):
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["crossing", "disjoint", "escape", "returner"]
    handles = {name: Mock() for name in names}
    handles["returner"] = None
    if pending:
        handles["crossing"] = None
    node = SimpleNamespace(
        battery_modes=dict.fromkeys(names, "ACTIVE"),
        rally_goal_handles=handles,
        rally_goal_pending={name: pending and name == "crossing" for name in names},
        rally_yield_requested=dict.fromkeys(names, False),
        rally_leg_routes={"crossing": ((3., 4.), (3., 2.)),
                          "disjoint": ((8., 8.), (9., 8.)),
                          "escape": ((5., 2.), (5., 4.)), "returner": ()},
        robot_positions={"crossing": (3., 4.), "disjoint": (8., 8.),
                         "escape": (5., 2.), "returner": (8., 2.)},
        return_yield_targets={"escape": "returner"}, get_logger=lambda: Mock(),
    )
    node.battery_modes["returner"] = "RETURNING"
    protected = {"returner": tuple((x * .1, 2.) for x in range(10, 81))}
    control.HeadquartersControl.preempt_rally_return_conflicts(node, protected)
    assert node.rally_yield_requested == dict(crossing=True, disjoint=False, escape=False, returner=False)
    for name in ("disjoint", "escape"):
        handles[name].cancel_goal_async.assert_not_called()
    if not pending:
        handles["crossing"].cancel_goal_async.assert_called_once()
        control.HeadquartersControl.preempt_rally_return_conflicts(node, protected)
        handles["crossing"].cancel_goal_async.assert_called_once()
    # An existing escape cannot bypass a second newly appearing return.
    protected["second"] = ((5., 4.),)
    control.HeadquartersControl.preempt_rally_return_conflicts(node, protected)
    handles["escape"].cancel_goal_async.assert_called_once()


@pytest.mark.parametrize("response", ["accepted", "rejected", "error"])
def test_return_preemption_survives_late_gateway_acceptance_without_consuming_retries(response):
    from types import SimpleNamespace
    from unittest.mock import Mock

    name = "crossing"
    handle = Mock(accepted=response == "accepted")
    future = Mock()
    if response == "error":
        future.result.side_effect = RuntimeError("gateway request expired")
    else:
        future.result.return_value = handle
    node = SimpleNamespace(
        rally_goal_pending={name: True}, rally_yield_requested={name: True},
        rally_battery_preempted={name: False}, battery_modes={name: "ACTIVE"},
        rally_goal_handles={name: None}, rally_goal_started_at={name: None},
        rally_leg_routes={name: ((3., 4.), (3., 2.))}, rally_attempts={name: 0},
        rally_route_unavailable_since={name: None}, rally_recovery_requested={name: False},
        now=lambda: 10., get_logger=lambda: Mock(),
    )
    control.HeadquartersControl.rally_goal_response(node, name, future)
    assert not node.rally_goal_pending[name] and node.rally_attempts[name] == 0
    assert not node.rally_recovery_requested[name]
    if response == "accepted":
        handle.cancel_goal_async.assert_called_once()
        assert node.rally_yield_requested[name]
    else:
        assert not node.rally_yield_requested[name] and not node.rally_leg_routes[name]


@pytest.mark.parametrize("temporary_blocker", [False, True])
def test_idle_return_blocker_yields_while_an_unrelated_leg_is_still_executing(temporary_blocker):
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["returner", "blocker", "disjoint"]
    original = control.RallyPose(4., 5., 0.)
    sent = []
    live = Mock()
    node = SimpleNamespace(
        now=lambda: 10., fresh_robot_inputs=lambda: True,
        rally_charge_requested={}, rally_precharge_staging={},
        rally_goal_handles={"returner": None, "blocker": None, "disjoint": live},
        rally_goal_pending=dict.fromkeys(names, False),
        rally_yield_requested=dict.fromkeys(names, False),
        rally_leg_routes={"returner": (), "blocker": (), "disjoint": ((8., 8.), (9., 8.))},
        rally_max_concurrent=2, survey_goal_handle=None, survey_goal_pending=False,
        rally_dispatch_order=names, battery_modes={"returner": "RETURNING", "blocker": "ACTIVE", "disjoint": "ACTIVE"},
        battery_states={"returner": {"charge_x": 1., "charge_y": 3.}},
        map_data=np.zeros((100, 100), dtype=int), resolution=.1, origin=(0., 0.),
        robot_positions={"returner": (8., 3.), "blocker": (5., 3.), "disjoint": (8., 8.)},
        rally_yield_targets={"blocker"} if temporary_blocker else set(),
        return_yield_targets={}, rally_recovery_beneficiaries={},
        rally_targets={"blocker": original}, rally_arrived={"blocker": True},
        rally_attempts={"blocker": 0}, publish_rally_assignments=lambda: None,
        get_logger=lambda: Mock(), send_rally_goal=lambda name, plan: sent.append((name, plan)),
    )
    control.HeadquartersControl.yield_to_returning_robot(node)
    assert len(sent) == 1 and sent[0][0] == "blocker"
    assert not control.routes_conflict(sent[0][1][1], node.rally_leg_routes["disjoint"])
    live.cancel_goal_async.assert_not_called()
    node.rally_max_concurrent = 1
    node.rally_yield_targets.clear()
    node.return_yield_targets.clear()
    node.last_return_yield_attempt_at = 0.
    sent.clear()
    control.HeadquartersControl.yield_to_returning_robot(node)
    assert not sent


@pytest.mark.parametrize("unknown_future", [False, True])
def test_prospective_charge_intent_cannot_preempt_an_admitted_return_escape(monkeypatch, unknown_future):
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["returner", "escape", "stager"]
    actual = {"returner": ((1., 2.), (8., 2.))}
    full = {**actual, "stager": ((5., 3.), (5., 5.))}
    monkeypatch.setattr(control, "rally_return_reservations",
                        lambda *args: actual if not args[-1] else None if unknown_future else full)
    handle = Mock()
    node = SimpleNamespace(
        fresh_robot_inputs=lambda: True, now=lambda: 10.,
        battery_modes={"returner": "RETURNING", "escape": "ACTIVE", "stager": "ACTIVE"},
        rally_goal_handles={"returner": None, "escape": handle, "stager": None},
        rally_goal_pending=dict.fromkeys(names, False),
        rally_yield_requested=dict.fromkeys(names, False),
        rally_leg_routes={"returner": (), "escape": ((5., 2.), (5., 4.)), "stager": ()},
        robot_positions={"returner": (8., 2.), "escape": (5., 2.), "stager": (9., 8.)},
        return_yield_targets={"escape": "returner"}, rally_charge_requested={"stager":8.},
        rally_precharge_staging={"stager": 1.}, battery_states={},
        map_data=np.zeros((100, 100)), resolution=.1, origin=(0., 0.),
        survey_goal_handle=None, survey_goal_pending=False, rally_max_concurrent=1,
        get_logger=lambda: Mock(),
    )
    control.HeadquartersControl.yield_to_returning_robot(node)
    handle.cancel_goal_async.assert_not_called()
    assert not node.rally_yield_requested["escape"]


def test_unknown_return_geometry_drains_ordinary_motion_without_canceling_the_local_return():
    from types import SimpleNamespace
    from unittest.mock import Mock

    ordinary, returning = Mock(), Mock()
    node = SimpleNamespace(
        battery_modes={"ordinary": "ACTIVE", "returner": "RETURNING"},
        rally_goal_handles={"ordinary": ordinary, "returner": returning},
        rally_goal_pending=dict.fromkeys(("ordinary", "returner"), False),
        rally_yield_requested=dict.fromkeys(("ordinary", "returner"), False),
        rally_leg_routes={"ordinary": ((1., 1.), (2., 2.)), "returner": ()},
        robot_positions={"ordinary": (1., 1.), "returner": None},
        return_yield_targets={}, get_logger=lambda: Mock(),
    )
    control.HeadquartersControl.preempt_rally_return_conflicts(node, None)
    ordinary.cancel_goal_async.assert_called_once()
    returning.cancel_goal_async.assert_not_called()


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
        # An omitted section silently uses wall time in the velocity smoother.
        assert config["velocity_smoother"]["ros__parameters"]["use_sim_time"] is True
        assert config["controller_server"]["ros__parameters"]["use_sim_time"] is True
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
        enable_battery=True, rally_charge_requested={},
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
    assert not updates
    node.battery_modes["tb1"] = "ACTIVE"
    control.HeadquartersControl.release_return_yields(node)
    assert not updates
    node.rally_goal_pending["tb1"] = True
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


def test_observer_refuge_preserves_range_and_known_target_sight():
    grid = np.zeros((60, 100), dtype=int)
    start, target = (3., 3.), (6., 3.)
    # Use a dense path, as produced by the actual distance-field planner.
    route = tuple((x, 3.) for x in np.arange(1., 8.01, .1))
    args = (grid, .1, (0., 0.), start, target)
    nearest = control.rally_yield_pose(*args, reserved_routes=(route,), visible_only=True)
    assert math.dist((nearest.x, nearest.y), target) > 3.
    visible = control.rally_yield_pose(
        *args, reserved_routes=(route,), visible_only=True, target_view_distance=2.65,
    )
    assert visible is not None
    assert math.dist((visible.x, visible.y), target) <= 2.65
    assert min(math.dist((visible.x, visible.y), p) for p in route) >= .8
    assert visible.yaw == pytest.approx(math.atan2(target[1]-visible.y, target[0]-visible.x))
    position = (visible.x, visible.y)
    assert control.rally_target_view(grid, .1, (0., 0.), position, target, 2.65)
    cell = control.world_to_grid(*position, .1, 0., 0.)
    target_cell = control.world_to_grid(*target, .1, 0., 0.)
    middle = list(control._line_cells(cell, target_cell))[2]
    for unavailable in (100, -1):
        grid[middle] = unavailable
        assert not control.rally_target_view(grid, .1, (0., 0.), position, target, 2.65)


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


@pytest.mark.parametrize("permanent_reassignment, refuge_available, preflight_blocked, guard, refuge_owner", [
    (True, True, False, False, None), (False, True, False, False, None),
    (True, False, False, False, None), (True, True, True, False, None), (True, True, False, True, None),
    (False, True, False, False, "tb1"), (True, False, False, False, "tb1"),
    (False, True, False, True, "tb1"), (False, True, False, False, "other"),
])
def test_idle_blocker_recovery_dispatches_motion_before_returning(
    monkeypatch, permanent_reassignment, refuge_available, preflight_blocked, guard, refuge_owner
):
    from types import SimpleNamespace

    names = ["tb1", "tb2"]
    grid = np.full((50, 100), 100, dtype=int)
    grid[19:31, 1:99] = 0
    grid[8:26, 35:46] = 0  # a dead-end refuge, not a bypass around the blocker
    if guard:
        # A narrow viewing slit exposes the target from the refuge but is
        # too narrow for a robot to bypass the blocked corridor.
        for cell in control._line_cells((16, 40), (25, 80)):
            grid[cell] = 0
    targets = {"tb1": control.RallyPose(8.0, 2.5, 0.0), "tb2": control.RallyPose(8.0, 2.0, 0.0)}
    replacements = {"tb1": targets["tb1"], "tb2": control.RallyPose(4.0, 1.5, 0.0)}
    replacement_calls = []
    def replacement(*args, local_map=None):
        replacement_calls.append(args[3])
        if not permanent_reassignment:
            return None
        return (control.RallyPose(6.0, 2.5, 0.0)
                if args[3] == "tb1" and not preflight_blocked else replacements[args[3]])
    monkeypatch.setattr(
        control, "reassign_rally_pose", replacement,
    )
    if not refuge_available:
        monkeypatch.setattr(control, "rally_yield_pose", lambda *args, **kwargs: None)
    requests = []
    node = SimpleNamespace(
        enable_battery=preflight_blocked, task_state="RALLY", fresh_robot_poses=lambda: True, fresh_target=lambda: True, stop_target_scan=lambda: False,
        last_input_availability=True,
        battery_monitor_started_at=0., battery_state_received_at=dict.fromkeys(names, 10.),
        message_freshness_timeout_sec=5.,
        rally_charge_requested={}, prepare_rally_charges=lambda: {"tb2"},
        rally_precharge_staging={},
        rally_detour_budgets={},
        rally_observer_guard="tb2" if guard else None, target_view_distance=4.6,
        rally_approach_routes={},
        rally_preflight_complete=True, rally_precharge_active=False,
        battery_states={name: {'charge_x': 1., 'charge_y': 2.5} for name in names},
        rally_max_concurrent=2, rally_probe_targets=set(),
        rally_leg_routes=dict.fromkeys(names, ()), rally_hold_started_at=None,
        active_batteries_ready=lambda: True,
        participating_robots=lambda: names, battery_modes=dict.fromkeys(names, "ACTIVE"),
        now=lambda: 10.0, survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        release_return_yields=lambda: None, rally_yield_targets=set(),
        rally_recovery_beneficiaries={},
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
    if refuge_owner:
        node.rally_yield_targets.add("tb2")
        node.return_yield_targets["tb2"] = refuge_owner
        node.rally_arrived["tb2"] = True
        monkeypatch.setattr(control, "rally_survey_pose", lambda *args, **kwargs: None)
    control.HeadquartersControl.update_mission(node)
    if refuge_owner == "other":
        assert not requests
        assert node.return_yield_targets == {"tb2": "other"}
        assert node.rally_targets["tb2"] == targets["tb2"]
        assert not node.rally_recovery_beneficiaries
        return
    if refuge_owner:
        assert not node.return_yield_targets  # The new move uses ordinary freshness/energy checks.
    if preflight_blocked:
        assert not requests and node.rally_targets == targets
        assert node.rally_hold_started_at is None
        return
    if not refuge_available:
        assert node.rally_targets["tb2"] == replacements["tb2"]
    else:
        refuge = node.rally_targets["tb2"]
        assert "tb2" in node.rally_yield_targets
        assert node.rally_recovery_beneficiaries == {"tb2": "tb1"}
        assert node.rally_final_targets["tb2"] == targets["tb2"]
        assert math.dist((refuge.x, refuge.y), (4.0, 2.5)) <= 1.1
        route = control.plan_rally_leg(
            targets["tb1"], grid, 0.1, (0.0, 0.0), (1.0, 2.5)
        )[1]
        assert min(math.dist((refuge.x, refuge.y), point) for point in route) >= 0.8
        if guard:
            assert control.rally_target_view(
                grid, .1, (0., 0.), (refuge.x, refuge.y), node.target,
                node.target_view_distance-node.rally_position_tolerance,
            )
        # The chosen endpoint actually releases the original waiting route,
        # even when a distant permanent replacement was also available.
        released = control.plan_rally_leg(
            targets["tb1"], grid, .1, (0., 0.), (1., 2.5),
            max_distance_m=float("inf"), blocked_positions=[(refuge.x, refuge.y)],
        )
        assert released[0] is not None
        assert node.rally_targets["tb1"] == node.rally_final_targets["tb1"] == targets["tb1"]
        assert not replacement_calls  # Do not invalidate the certified route.
    assert requests == ["tb2"]  # the action cannot be starved by the next timer


@pytest.mark.parametrize("conflict,slots,admitted", [(False, 2, True), (True, 2, False), (False, 1, False)])
def test_active_yield_allows_only_disjoint_rally_with_an_available_slot(conflict, slots, admitted):
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["yielding", "rallying"]
    y = 1.05 if conflict else 5.05
    targets = {"yielding": control.RallyPose(4.05, y, 0.),
               "rallying": control.RallyPose(3.05, 1.05, 0.)}
    sent = []
    node = SimpleNamespace(
        enable_battery=False, task_state="RALLY", fresh_robot_inputs=lambda: True,
        fresh_robot_poses=lambda: True, fresh_target=lambda: True, stop_target_scan=lambda: False,
        last_input_availability=True, now=lambda: 10.,
        rally_charge_requested={}, rally_precharge_staging={},
        rally_max_concurrent=slots, rally_leg_routes={"yielding": ((1.05, y), (4.05, y)), "rallying": ()},
        rally_goal_handles={"yielding": Mock(), "rallying": None},
        rally_goal_pending=dict.fromkeys(names, False),
        rally_goal_started_at={"yielding": 9., "rallying": None},
        goal_timeout_sec=60., rally_goal_timeout_sec=30.,
        rally_arrived=dict.fromkeys(names, False), rally_hold_started_at=None,
        rally_yield_targets={"yielding"}, return_yield_targets={"yielding": "returner"},
        rally_yield_requested=dict.fromkeys(names, False), rally_probe_targets=set(),
        rally_targets=targets.copy(), rally_final_targets=targets.copy(), rally_dispatch_order=names,
        battery_modes=dict.fromkeys(names, "ACTIVE"), participating_robots=lambda: names,
        survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        release_return_yields=lambda: None, yield_to_returning_robot=lambda: None,
        last_rally_dispatch_at=0., global_battery_rally_pause=False,
        rally_attempts=dict.fromkeys(names, 0), rally_recovery_requested=dict.fromkeys(names, False),
        rally_route_unavailable_since=dict.fromkeys(names),
        robot_positions={"yielding": (1.05, y), "rallying": (1.05, 1.05)},
        map_data=np.zeros((80, 80), dtype=int), resolution=.1, origin=(0., 0.),
        target=(6.05, 1.05), get_logger=lambda: Mock(),
    )
    def send(name, plan, charge_staging=False):
        assert not charge_staging
        assert not control.routes_conflict(plan[1], node.rally_leg_routes["yielding"], control.RALLY_ROUTE_SEPARATION_M)
        sent.append(name)
        node.rally_goal_pending[name] = True
    node.send_rally_goal = send
    control.HeadquartersControl.update_mission(node)
    assert sent == (["rallying"] if admitted else [])
    node.rally_goal_handles["yielding"].cancel_goal_async.assert_not_called()


@pytest.mark.parametrize("beneficiary,parked,body_blocks,admitted", [
    ("rallying", True, False, True), ("unrelated", True, False, True),
    ("rallying", False, False, False), ("unrelated", False, False, False),
    ("rallying", True, True, False), ("unrelated", True, True, False)])
@pytest.mark.parametrize("local_return_refuge", [False, True])
def test_parked_refuge_defers_future_approach_but_protects_body_and_live_leg(
    beneficiary, parked, body_blocks, admitted, local_return_refuge
):
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["yielding", "rallying"]
    refuge = control.RallyPose(4.05, 2.05 if body_blocks else 1.05, 0.)
    final = {"yielding": control.RallyPose(8.05, 2.05, 0.),
             "rallying": control.RallyPose(6.05, 2.05, 0.)}
    sent = []
    node = SimpleNamespace(
        enable_battery=False, task_state="RALLY", fresh_robot_inputs=lambda: True,
        fresh_robot_poses=lambda: True, fresh_target=lambda: True, stop_target_scan=lambda: False,
        last_input_availability=True, now=lambda: 10., rally_charge_requested={}, rally_precharge_staging={},
        rally_max_concurrent=2, rally_leg_routes=dict.fromkeys(names, ()),
        rally_goal_handles=dict.fromkeys(names), rally_goal_pending={"yielding": not parked, "rallying": False},
        rally_goal_started_at=dict.fromkeys(names),
        rally_arrived={"yielding": parked, "rallying": False}, rally_hold_started_at=None,
        rally_position_tolerance=.35,
        rally_yield_targets={"yielding"}, return_yield_targets={"yielding": beneficiary} if local_return_refuge else {},
        rally_recovery_beneficiaries={} if local_return_refuge else {"yielding": beneficiary},
        rally_yield_requested=dict.fromkeys(names, False), rally_probe_targets=set(),
        rally_targets={"yielding": refuge, "rallying": final["rallying"]},
        rally_final_targets=final, rally_dispatch_order=names,
        battery_modes=dict.fromkeys(names, "ACTIVE"), participating_robots=lambda: names,
        survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        release_return_yields=lambda: None, yield_to_returning_robot=lambda: None,
        last_rally_dispatch_at=0., global_battery_rally_pause=False,
        rally_attempts=dict.fromkeys(names, 0), rally_recovery_requested=dict.fromkeys(names, False),
        rally_route_unavailable_since=dict.fromkeys(names),
        robot_positions={"yielding": (refuge.x, refuge.y), "rallying": (3.05, 2.05)},
        map_data=np.zeros((80, 100), dtype=int), resolution=.1, origin=(0., 0.),
        target=(8.05, 3.05), get_logger=lambda: Mock(),
    )
    def send(name, plan, charge_staging=False):
        assert not charge_staging
        assert min(math.dist(p, node.robot_positions["yielding"]) for p in plan[1]) >= control.RALLY_DYNAMIC_CLEARANCE_M
        sent.append(name)
        node.rally_goal_pending[name] = True
    node.send_rally_goal = send
    if body_blocks:
        node.map_data[:] = 100
        node.map_data[14:27, 1:99] = 0  # Occupied body closes the only safe corridor.
    control.HeadquartersControl.update_mission(node)
    assert sent == (["rallying"] if admitted else [])
    assert node.rally_targets["yielding"] == refuge and node.rally_final_targets == final


@pytest.mark.parametrize("donated,physical_block,admitted", [(True, False, True),
    (False, False, False), (True, True, False)])
def test_recovery_blocker_borrows_waiter_priority_without_bypassing_its_body(donated, physical_block, admitted):
    from types import SimpleNamespace
    from unittest.mock import Mock

    names = ["waiter", "blocker"]
    grid = np.full((50, 100), 100, dtype=int)
    grid[19:31, 1:99] = 0
    grid[8:26, 35:46] = 0
    targets = {"waiter": control.RallyPose(8., 2.5, 0.), "blocker": control.RallyPose(4., 1.5, 0.)}
    sent=[]
    node=SimpleNamespace(
        enable_battery=False, task_state="RALLY", fresh_robot_inputs=lambda: True,
        fresh_robot_poses=lambda: True, fresh_target=lambda: True, stop_target_scan=lambda: False,
        last_input_availability=True, now=lambda: 10., rally_charge_requested={}, rally_precharge_staging={},
        rally_max_concurrent=2, rally_leg_routes=dict.fromkeys(names, ()),
        rally_goal_handles=dict.fromkeys(names), rally_goal_pending=dict.fromkeys(names, False),
        rally_goal_started_at=dict.fromkeys(names), rally_arrived=dict.fromkeys(names, False),
        rally_hold_started_at=None, rally_yield_targets=set(), return_yield_targets={},
        rally_recovery_beneficiaries={"blocker": "waiter"} if donated else {},
        rally_yield_requested=dict.fromkeys(names, False), rally_probe_targets=set(),
        rally_targets=targets.copy(), rally_final_targets=targets.copy(), rally_dispatch_order=names,
        battery_modes=dict.fromkeys(names, "ACTIVE"), participating_robots=lambda: names,
        survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        release_return_yields=lambda: None, yield_to_returning_robot=lambda: None,
        last_rally_dispatch_at=0., global_battery_rally_pause=False,
        rally_attempts=dict.fromkeys(names, 0), rally_recovery_requested=dict.fromkeys(names, False),
        rally_route_unavailable_since=dict.fromkeys(names),
        robot_positions={"waiter": (4., 1.5) if physical_block else (1., 2.5), "blocker": (4., 2.5)},
        map_data=grid, resolution=.1, origin=(0., 0.), target=(8., 2.5), get_logger=lambda: Mock(),
    )
    def send(name, plan, charge_staging=False):
        sent.append(name)
        node.rally_goal_pending[name]=True
    node.send_rally_goal=send
    control.HeadquartersControl.update_mission(node)
    assert ("blocker" in sent) is admitted
    assert node.rally_targets==targets and node.rally_final_targets==targets


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
        map_received_at=11.,robot_odom_received_at={"tb1":11.},
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
    assert event["required_energy"] == pytest.approx(32.9977777778)
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


def test_near_final_robot_does_not_precharge_for_an_unplanned_ten_meter_loop():
    node, messages, failures = two_robot_rally_budget_node()
    node.robot_positions["tb1"] = (7.55, 1.05)
    node.battery_states["tb1"]["energy"] = 26.
    node.battery_states["tb2"]["energy"] = 80.
    blocked = control.HeadquartersControl.prepare_rally_charges(node)
    assert "tb1" not in blocked and not messages and not failures
    assert node.rally_charge_budgets["tb1"] < 26.


def test_actual_detour_is_funded_before_admission_and_charge_restores_it():
    node, messages, failures = two_robot_rally_budget_node()
    node.rally_detour_budgets = {}
    node.robot_positions["tb1"] = (7.55, 1.05)
    node.battery_states["tb1"]["energy"] = 26.
    node.battery_states["tb2"]["energy"] = 80.
    control.HeadquartersControl.prepare_rally_charges(node)
    direct = control.plan_rally_leg(node.rally_final_targets["tb1"], node.map_data,
                                   node.resolution, node.origin, node.robot_positions["tb1"])
    assert control.HeadquartersControl.rally_plan_has_energy(node, "tb1", direct)
    detour = control.plan_rally_leg(control.RallyPose(4.05, 2.05, 0.), node.map_data,
                                   node.resolution, node.origin, node.robot_positions["tb1"])
    assert not control.HeadquartersControl.rally_plan_has_energy(node, "tb1", detour)
    assert node.rally_detour_budgets["tb1"] > 26.
    assert "tb1" in control.HeadquartersControl.prepare_rally_charges(node)
    assert messages and not failures
    # Fresh preflight after a genuine charge; no repeated detour double counting.
    node.battery_states["tb1"]["energy"] = 80.
    control.HeadquartersControl.prepare_rally_charges(node)
    assert control.HeadquartersControl.rally_plan_has_energy(node, "tb1", detour)
    assert not node.rally_detour_budgets


def test_detour_cannot_use_disconnected_final_path_or_invalid_motion_model():
    node, _, _ = two_robot_rally_budget_node()
    node.rally_detour_budgets = {}
    node.battery_states["tb1"]["energy"] = 80.
    control.HeadquartersControl.prepare_rally_charges(node)
    plan = (control.RallyPose(3.05, 1.05, 0.), ((3.05, 1.05),))
    node.map_data[:, 50:55] = 100
    assert not control.HeadquartersControl.rally_plan_has_energy(node, "tb1", plan)
    node.map_data[:] = 0
    node.battery_states["tb1"]["nominal_speed_mps"] = 0.
    assert not control.HeadquartersControl.rally_plan_has_energy(node, "tb1", plan)


def test_reassignment_rechecks_return_reserve_from_the_new_final_pose():
    node, _, _ = two_robot_rally_budget_node()
    node.rally_detour_budgets = {}
    node.robot_positions["tb1"] = (7.55, 1.05)
    node.battery_states["tb1"]["energy"] = 26.
    node.battery_states["tb2"]["energy"] = 80.
    control.HeadquartersControl.prepare_rally_charges(node)
    plan = control.plan_rally_leg(node.rally_final_targets["tb1"], node.map_data,
                                  node.resolution, node.origin, node.robot_positions["tb1"])
    assert control.HeadquartersControl.rally_plan_has_energy(node, "tb1", plan)
    node.rally_final_targets["tb1"] = control.RallyPose(9.05, 1.05, 0.)
    assert not control.HeadquartersControl.rally_plan_has_energy(node, "tb1", plan)


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
                  "battery_modes", "robot_odom_received_at"):
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
    node.map_received_at=14.
    node.robot_odom_received_at=dict.fromkeys(node.battery_modes,14.)
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


def test_visual_handoff_charges_peer_first_then_releases_previous_observer():
    import json
    from types import SimpleNamespace

    node, messages, failures = two_robot_rally_budget_node()
    node.target_observing_robot = "tb2"  # nearest charger is also the last observer
    node.target_received_source_time = 10.5
    events = []
    node.consumed_publisher = SimpleNamespace(publish=events.append)
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb1", "tb2"}
    assert node.rally_observer_guard == "tb2"
    assert json.loads(messages[-1].data)["robot"] == "tb1"
    assert json.loads(events[-1].data)["event"] == "coordinator_observer_handoff_wait"
    node.rally_charge_requested.clear()
    node.battery_states["tb1"]["energy"] = 80.
    node.target_observing_robot = "tb1"  # new real confirmation performs handoff
    node.target_received_source_time = 10.8
    assert control.HeadquartersControl.prepare_rally_charges(node) == {"tb2"}
    assert json.loads(messages[-1].data)["robot"] == "tb2"
    assert not failures


@pytest.mark.parametrize("stamp,mode,peer,expected", [
    (95., "ACTIVE", "ACTIVE", "tb1"),
    (94.99, "ACTIVE", "ACTIVE", None),
    (40., "ACTIVE", "ACTIVE", None),
    (39.99, "ACTIVE", "ACTIVE", None),
    (100.01, "ACTIVE", "ACTIVE", None),
    (float("nan"), "ACTIVE", "ACTIVE", None),
    (99., "RETURNING", "ACTIVE", None),
    (99., "ACTIVE", "FAILED", None),
    (99., "ACTIVE", "UNKNOWN", None),
    (99., "ACTIVE", "RETURNING", "tb1"),
    (99., "ACTIVE", "CHARGING", "tb1"),
])
def test_observation_guard_needs_recent_confirmation_and_healthy_peer(stamp, mode, peer, expected):
    assert control.rally_observation_guard("tb1", stamp, 100., {"tb1": mode, "tb2": peer}) == expected


def test_observation_guard_does_not_cancel_admitted_return_or_relax_capacity():
    from types import SimpleNamespace
    node, messages, failures = two_robot_rally_budget_node()
    node.target_observing_robot = "tb2"
    node.target_received_source_time = 10.5
    node.consumed_publisher = SimpleNamespace(publish=lambda m: None)
    node.rally_charge_requested["tb2"] = 8.
    control.HeadquartersControl.prepare_rally_charges(node)
    assert node.rally_observer_guard is None and messages
    node.rally_charge_requested.clear()
    node.battery_states["tb2"]["capacity"] = 1.
    control.HeadquartersControl.prepare_rally_charges(node)
    assert failures == ["rally_energy_capacity_insufficient:tb2"]


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


@pytest.mark.parametrize('conflicting, observer', [(False, False), (True, False), (False, True), (False, 'camera_gap')])
def test_waiting_precharge_moves_only_along_a_safe_home_prefix(conflicting, observer):
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
        rally_observer_guard='waiter' if observer is True else None,
        target_observing_robot='waiter' if observer else None,
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
    def send(name, plan, charge_staging=False):
        assert charge_staging
        sent.append((name, plan))
        node.rally_goal_pending[name] = True
    node.send_rally_goal = send
    control.HeadquartersControl.update_mission(node)
    if conflicting or observer:
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
        active_exclusions=lambda: [], exploration_battery_factor=lambda *a: True,
        goal_routes={}, goal_targets={}, goal_initial_gain={},
        target_information_gain=lambda *a: 1000,
        now=lambda: 100., last_no_assignment_log=-math.inf,
        get_logger=lambda: SimpleNamespace(info=lambda *a: None, warn=lambda *a: None),
        send_goal=lambda name, goal: sent.append((name, goal)))
    static_planning_sources(node)
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
    def deliver(stamp, target=(1., 2.), robot="tb1", distance=3., fov=90.):
        event = {"robot": robot, "target_x": target[0], "target_y": target[1],
                 "max_distance_m": distance, "field_of_view_deg": fov,
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
    deliver(99., robot="tb2")
    assert node.detecting_robot == "tb1" and node.target_observing_robot == "tb2"
    deliver(90., robot="tb1")
    assert node.target_observing_robot == "tb2"  # old repeats cannot steal handoff
    assert [json.loads(m.data)["event"] for m in emitted] == ["consumed", "target_reconfirmed", "target_reconfirmed"]
    deliver(99.5, robot="tb2", distance=1.5)
    assert node.target_view_distance == 1.5 and node.target_received_source_time == 99.5
    for distance in (float("inf"), float("nan"), 0., -1.):
        deliver(99.9, robot="tb1", distance=distance)
        assert node.target_received_source_time == 99.5
        assert node.target_view_distance == 1.5 and node.target_observing_robot == "tb2"
    for fov in (float('inf'), float('nan'), 0., -1., 360.1):
        deliver(99.9, robot='tb1', fov=fov)
        assert node.target_received_source_time == 99.5 and node.target_view_fov_rad == pytest.approx(math.pi/2)
    deliver(99.9, robot='tb2', distance=1.5, fov=60.)
    assert node.target_view_fov_rad == pytest.approx(math.pi/3)


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
        record_navigation_decision=lambda *args: (decisions.append(args) or True))
    node.now = lambda: node.clock
    import queue
    node.shutdown_requested = False
    node.action_done_callbacks = queue.SimpleQueue()
    node.action_done_guard = SimpleNamespace(trigger=lambda:
        control.HeadquartersControl.drain_action_done_callbacks(node))
    node.target_scan_response = lambda f: control.HeadquartersControl.target_scan_response(node, f)
    node.target_scan_result = lambda f: control.HeadquartersControl.target_scan_result(node, f)
    node.finish_target_scan = lambda: control.HeadquartersControl.finish_target_scan(node)
    node.stop_target_scan = lambda: control.HeadquartersControl.stop_target_scan(node)
    return node, goals, decisions


def test_blind_scan_holds_live_position_and_covers_four_headings_without_old_target_geometry():
    node, goals, decisions = target_scan_node()
    for index in range(4):
        control.HeadquartersControl.reacquire_target_by_scanning(node)
        name = "tb1"
        pose = goals[-1].pose.pose
        assert (pose.position.x, pose.position.y) == node.robot_positions[name]
        yaw = (index % 4)*math.pi/2
        assert pose.orientation.z == pytest.approx(math.sin(yaw/2))
        assert pose.orientation.w == pytest.approx(math.cos(yaw/2))
        assert decisions[-1][:2] == (name, "target_reacquisition_scan")
        assert node.target == (1000., -1000.)
        node.finish_target_scan()
    control.HeadquartersControl.reacquire_target_by_scanning(node)
    assert len(goals) == 4 and node.target_search_active
    node.clock = 130.001
    control.HeadquartersControl.reacquire_target_by_scanning(node)
    assert len(goals) == 4  # move to fresh frontiers instead of scanning forever


def test_recovery_scan_prioritizes_the_robot_that_just_travelled():
    node, goals, decisions = target_scan_node()
    node.target_scan_next_robot = "tb2"
    for _ in range(4):
        control.HeadquartersControl.reacquire_target_by_scanning(node)
        assert decisions[-1][:2] == ("tb2", "target_reacquisition_scan")
        assert (goals[-1].pose.pose.position.x, goals[-1].pose.pose.position.y) == (3., 3.)
        node.finish_target_scan()
    assert node.target_search_active and node.target_scan_next_robot is None


@pytest.mark.parametrize("fully_known", [False, True])
def test_target_reacquisition_frontiers_do_not_depend_on_old_target_and_keep_return_priority(fully_known):
    from types import SimpleNamespace

    def search(old_target, fresh=True, returning=False):
        grid = np.full((80, 120), -1, dtype=int)
        grid[5:75, 5:100] = 0
        if fully_known:
            grid.fill(0)
            grid[[0, -1], :] = 100
            grid[:, [0, -1]] = 100
        sent = []
        node = SimpleNamespace(
            task_state="RALLY", target=old_target, target_search_active=True,
            target_search_visits=[],
            fresh_target=lambda: False, target_scan_robot=None,
            rally_goal_handles={}, rally_goal_pending={}, survey_goal_handle=None,
            survey_goal_pending=False, map_data=grid, resolution=.1, origin=(0., 0.),
            robot_positions={"tb1": (2., 3.), "tb2": (5., 3.)},
            robot_maps={"tb1": {}, "tb2": {}},
            robot_states=dict.fromkeys(("tb1", "tb2"), "idle"),
            battery_modes={"tb1": "ACTIVE", "tb2": "RETURNING" if returning else "ACTIVE"},
            frontier_cache=None, input_robot_names=lambda: ["tb1", "tb2"],
            participating_robots=lambda: ["tb1", "tb2"],
            fresh_robot_inputs=lambda: fresh, active_exclusions=lambda: [],
            exploration_battery_factor=lambda *args: True, goal_targets={}, goal_routes={},
            goal_initial_gain={}, target_information_gain=lambda *args: 100,
            get_logger=lambda: SimpleNamespace(info=lambda *a: None, warn=lambda *a: None),
            send_goal=lambda name, goal: sent.append((name, goal)),
        )
        static_planning_sources(node)
        control.HeadquartersControl.assign_idle_robots(node)
        return sent, node

    one, node = search((10000., -10000.))
    other, _ = search((-10000., 10000.))
    assert len(one) == 1 and one == other
    assert node.task_state == "RALLY"
    assert node.target_search_basis == ("current_map_known_free_sweep" if fully_known else "current_map_frontiers")
    assert math.dist(node.robot_positions[one[0][0]],
                     (one[0][1].navigation_x, one[0][1].navigation_y)) <= control.MAX_NAVIGATION_LEG_M + .1
    assert search((0., 0.), fresh=False)[0] == []
    assert search((0., 0.), returning=True)[0] == []


def test_fresh_confirmation_drains_pending_and_accepted_frontier_search_once():
    from types import SimpleNamespace
    from unittest.mock import Mock

    handle = Mock(accepted=True)
    node = SimpleNamespace(
        target_search_active=True, fresh_target=lambda: True,
        target_search_visits=[(1., 1.)],
        robot_states={"tb1": "active"}, goal_handles={"tb1": None},
        cancel_requested={"tb1": False}, target_scan_steps={"tb1": 4},
        target_scan_finished_at={"tb1": 100.}, goal_targets={"tb1": None},
        goal_started_at={}, goal_last_progress_at={}, goal_best_distance={},
        goal_last_position={}, goal_known_count={}, map_known_count=1,
        robot_positions={"tb1": (1., 1.)}, battery_preempted={},
        battery_modes={"tb1": "ACTIVE"}, now=lambda: 101.,
    )
    assert control.HeadquartersControl.stop_target_search(node)
    control.HeadquartersControl.goal_response_callback(node, "tb1", SimpleNamespace(result=lambda: handle))
    handle.cancel_goal_async.assert_called_once()
    assert control.HeadquartersControl.stop_target_search(node)
    handle.cancel_goal_async.assert_called_once()
    node.robot_states["tb1"] = "idle"
    node.goal_handles["tb1"] = None
    assert not control.HeadquartersControl.stop_target_search(node)
    assert not node.target_search_active and node.target_scan_steps == {}
    assert not node.target_search_visits


def test_known_space_search_uses_only_reachable_known_cells_and_releases_visited_neighborhoods():
    grid = np.zeros((80, 120), dtype=int)
    grid[[0, -1], :] = 100
    grid[:, [0, -1]] = 100
    grid[:, 60] = 100  # The entire right component is unreachable.
    grid[20:30, 20:30] = -1
    unchanged = grid.copy()
    visited = [(1., 4.)]
    candidates = control.known_space_search_candidates(grid, .1, (0., 0.), "tb1", (1., 4.), visited)
    assert candidates
    for _, _, _, assignment in candidates:
        cell = control.world_to_grid(assignment.x, assignment.y, .1, 0., 0.)
        assert grid[cell] == 0 and assignment.x < 6.
        assert math.isfinite(assignment.path_distance_m)
    best = max(candidates)[-1]
    visited.append((best.x, best.y))
    after = control.known_space_search_candidates(grid, .1, (0., 0.), "tb1", (1., 4.), visited)
    before_gains = {candidate[2]: candidate[3].viewpoint.information_gain for candidate in candidates}
    assert all(candidate[3].viewpoint.information_gain <= before_gains[candidate[2]] for candidate in after)
    assert all(math.dist((best.x, best.y), (x, y)) > .6 for _, _, _, a in
               control.known_space_search_candidates(grid, .1, (0., 0.), "tb1", (1., 4.), [(1.,4.)], blocked=[(best.x,best.y)])
               for x,y in [(a.x,a.y)])
    np.testing.assert_array_equal(grid, unchanged)


def test_known_space_search_information_rays_cannot_see_through_unknown_cells():
    grid = np.full((9, 15), 100, dtype=int)
    grid[3:6, 1:14] = 0
    grid[:, 7] = -1
    interest = np.zeros(grid.shape, dtype=bool)
    interest[3:6, 8:14] = True
    assert control.visible_unknown_gain(grid, (4, 3), 12., interest) == 0
    grid[3:6, 7] = 0
    assert control.visible_unknown_gain(grid, (4, 3), 12., interest) > 0


def test_search_ray_cache_preserves_candidates_under_distinct_robot_dynamic_masks():
    grid = np.zeros((80, 100), dtype=int)
    grid[[0, -1], :] = 100
    grid[:, [0, -1]] = 100
    positions = {"tb1": (1., 3.), "tb2": (4., 3.)}
    visited = list(positions.values())
    cache = {}
    for name, position in positions.items():
        arguments = (grid, .1, (0., 0.), name, position, visited)
        blocked = [p for other,p in positions.items() if other != name]
        plain = control.known_space_search_candidates(*arguments, blocked=blocked)
        shared = control.known_space_search_candidates(*arguments, blocked=blocked, gain_cache=cache)
        assert plain == shared and plain
    assert cache


def test_successful_recovery_waypoint_requires_a_new_real_heading_scan():
    from types import SimpleNamespace
    name = "tb1"
    dictionaries = {field: {name: None} for field in (
        "goal_handles", "goal_started_at", "goal_last_progress_at", "goal_best_distance",
        "goal_last_position", "goal_known_count", "goal_initial_gain", "goal_routes",
        "cancel_requested", "battery_preempted", "robot_states")}
    assignment = control.Assignment(control.Viewpoint(1, 20, 20, 20, 20, 10, 1), 2., 2., 3., 10., 2., 2.)
    node = SimpleNamespace(**dictionaries, goal_targets={name: assignment},
        target_search_active=True, target_search_visits=[], target_scan_steps={name: 4},
        fresh_target=lambda: False, fresh_robot_poses=lambda: True,
        robot_positions={name: (2., 2.)}, battery_modes={name: "ACTIVE"},
        now=lambda: 10., target_history=[], check_exploration_completion=lambda: None)
    control.HeadquartersControl.finish_goal(node, name, success=True)
    assert node.target_search_visits == [(2., 2.)]
    assert node.target_scan_steps[name] == 0 and not node.target_search_active
    assert node.target_scan_next_robot == name
    assert node.robot_states[name] == "idle"


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


def test_multi_robot_preflight_keeps_peer_wait_without_a_phantom_recovery():
    node, messages, failures = two_robot_rally_budget_node()
    for state in node.battery_states.values():
        state["energy"] = 40.0
    blocked = control.HeadquartersControl.prepare_rally_charges(node)
    assert not blocked and not messages and not failures
    # Nominal trip plus the actual peer travel wait stays reserved.
    distance = 7.0
    state = node.battery_states["tb2"]
    nominal = control.HeadquartersControl.task_return_required_energy(
        node,"tb2",distance,(node.rally_final_targets["tb2"].x,node.rally_final_targets["tb2"].y)) + .02 * 5
    assert nominal < 40.
    assert node.rally_charge_budgets["tb2"] > nominal
    assert node.rally_charge_budgets["tb2"] < 40.


@pytest.mark.parametrize('obstruction', [None, 'occupied', 'unknown', 'range', 'no_target'])
def test_intermediate_heading_centers_only_a_current_map_visible_target(obstruction):
    grid=np.zeros((80,80),dtype=int)
    pose=control.RallyPose(1.05,1.05,0.)
    target=(1.05,3.05)
    if obstruction in ('occupied','unknown'):grid[20,10]=100 if obstruction=='occupied' else -1
    if obstruction=='range':target=(1.05,4.05)
    if obstruction=='no_target':target=None
    original=grid.copy()
    heading=control.rally_observation_heading(pose,target,grid,.1,(0.,0.),3.)
    np.testing.assert_array_equal(grid,original)
    assert (heading.x,heading.y)==(pose.x,pose.y)
    if obstruction is None:assert heading.yaw==pytest.approx(math.pi/2)
    else:assert heading is pose


@pytest.mark.parametrize('kind', ['ordinary','final','quantized_final','charge_staging','local_return_yield','stale_target'])
def test_observation_heading_preserves_final_safety_and_freshness_branches(kind):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from builtin_interfaces.msg import Time
    final=control.RallyPose(1.05,1.35,.3)
    intermediate=control.RallyPose(1.05,1.05,0.)
    pose=final if kind=='final' else control.RallyPose(1.05, 1.35, .3) if kind=='quantized_final' else intermediate
    if kind=='quantized_final':final=control.RallyPose(1.026, 1.328, .3)
    client=Mock()
    client.server_is_ready.return_value=True
    node=SimpleNamespace(
        task_state='RALLY',fresh_robot_inputs=lambda:True,
        fresh_target=lambda:kind!='stale_target',
        return_yield_targets={'tb1':'tb2'} if kind=='local_return_yield' else {},
        battery_modes={'tb1':'ACTIVE'},rally_max_retries=2,rally_attempts={'tb1':0},
        robot_nav_clients={'tb1':client},enable_battery=False,
        rally_targets={'tb1':final},map_data=np.zeros((80,80),dtype=int),resolution=.1,
        origin=(0.,0.),target=(1.05,3.05),target_view_distance=3.,
        get_logger=lambda:Mock(),
        get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(to_msg=lambda:Time(sec=10))),
        rally_leg_routes={},rally_leg_poses={},rally_goal_pending={},
        record_navigation_decision=Mock(),
    )
    route=((pose.x,pose.y),)
    control.HeadquartersControl.send_rally_goal(node,'tb1',(pose,route),charge_staging=kind=='charge_staging')
    if kind=='stale_target':
        client.send_goal_async.assert_not_called()
        return
    sent=client.send_goal_async.call_args.args[0].pose.pose
    yaw=2*math.atan2(sent.orientation.z,sent.orientation.w)
    assert yaw==pytest.approx(math.pi/2 if kind=='ordinary' else pose.yaw)
    assert (sent.position.x,sent.position.y)==(pose.x,pose.y)
    assert node.rally_leg_routes['tb1'] is route
    assert node.rally_targets['tb1'] is final


@pytest.mark.parametrize('reservation', ['staging', 'pending', 'RETURNING', 'CHARGING'])
def test_home_staging_does_not_seal_a_charged_peers_disjoint_live_leg(reservation):
    from types import SimpleNamespace
    from unittest.mock import Mock
    names=['stager','charged']
    targets={'stager':control.RallyPose(4.05,5.05,0.),
             'charged':control.RallyPose(3.05,1.05,0.)}
    positions={'stager':(1.05,5.05),'charged':(1.05,1.05)}
    sent=[]
    node=SimpleNamespace(
        enable_battery=True,task_state='RALLY',fresh_robot_inputs=lambda:True,
        fresh_robot_poses=lambda:True,fresh_target=lambda:True,stop_target_scan=lambda:False,
        last_input_availability=True,now=lambda:10.,message_freshness_timeout_sec=5.,
        battery_monitor_started_at=0.,battery_state_received_at=dict.fromkeys(names,10.),
        battery_modes={'stager':reservation if reservation in ('RETURNING','CHARGING') else 'ACTIVE','charged':'ACTIVE'},
        battery_states={'stager':{'charge_x':1.05,'charge_y':1.05},
                        'charged':{'charge_x':7.05,'charge_y':7.05}},
        participating_robots=lambda:names,
        rally_charge_requested={'stager':8.} if reservation=='pending' else {},
        rally_precharge_staging={'stager':40.},prepare_rally_charges=lambda:{'stager'},
        rally_approach_routes={'stager':((1.05,5.05),(4.05,5.05))},
        rally_preflight_complete=True,rally_precharge_active=True,
        rally_max_concurrent=2,rally_leg_routes={'stager':((1.05,5.05),(4.05,5.05)),'charged':()},
        rally_goal_handles={'stager':Mock(),'charged':None},rally_goal_pending=dict.fromkeys(names,False),
        rally_goal_started_at={'stager':9.,'charged':None},goal_timeout_sec=60.,rally_goal_timeout_sec=30.,
        rally_arrived=dict.fromkeys(names,False),rally_hold_started_at=None,
        rally_yield_targets=set(),return_yield_targets={},rally_yield_requested=dict.fromkeys(names,False),
        rally_probe_targets=set(),rally_targets=targets.copy(),rally_final_targets=targets.copy(),
        rally_dispatch_order=names,survey_robot=None,survey_goal_handle=None,survey_goal_pending=False,
        release_return_yields=lambda:None,yield_to_returning_robot=lambda:None,last_rally_dispatch_at=0.,
        global_battery_rally_pause=False,rally_attempts=dict.fromkeys(names,0),
        rally_recovery_requested=dict.fromkeys(names,False),rally_route_unavailable_since=dict.fromkeys(names),
        robot_positions=positions,map_data=np.zeros((80,80),dtype=int),resolution=.1,origin=(0.,0.),
        target=(6.05,1.05),get_logger=lambda:Mock(),active_batteries_ready=lambda:False)
    def send(name,plan,charge_staging=False):
        assert not charge_staging
        assert not control.routes_conflict(plan[1],node.rally_leg_routes['stager'])
        sent.append(name);node.rally_goal_pending[name]=True
    node.send_rally_goal=send
    control.HeadquartersControl.update_mission(node)
    # CHARGING reserves the actual body, not an outbound route that is not executing.
    assert sent==(['charged'] if reservation in ('staging','CHARGING') else [])
    assert node.rally_targets==targets and node.rally_final_targets==targets


@pytest.mark.parametrize('owner_mode,owner_departure,refuge_arrived,release', [
    ('ACTIVE','pending',True,True),('ACTIVE','accepted',True,True),
    ('ACTIVE','arrived',True,True),('ACTIVE','idle',True,False),
    ('CHARGING','pending',True,False),('RETURNING','accepted',True,False),
    ('UNKNOWN','idle',True,False),('FAILED','idle',True,True),
    ('ACTIVE','pending',False,False)])
def test_return_refuge_without_joint_plan_waits_for_owner_departure(owner_mode,owner_departure,refuge_arrived,release):
    from types import SimpleNamespace
    final=control.RallyPose(4.,3.,0.)
    refuge=control.RallyPose(1.,1.,0.)
    updates=[]
    node=SimpleNamespace(return_yield_targets={'yielding':'owner'},
        enable_battery=True,rally_charge_requested={},
        battery_modes={'owner':owner_mode,'yielding':'ACTIVE'},
        rally_arrived={'yielding':refuge_arrived,'owner':owner_departure=='arrived'},
        rally_goal_handles={'yielding':None,'owner':object() if owner_departure=='accepted' else None},
        rally_goal_pending={'yielding':False,'owner':owner_departure=='pending'},
        rally_yield_targets={'yielding'},rally_targets={'yielding':refuge},
        rally_final_targets={'yielding':final},rally_route_unavailable_since={},
        publish_rally_assignments=lambda:updates.append(True))
    control.HeadquartersControl.release_return_yields(node)
    assert bool(updates) is release
    assert node.rally_targets['yielding'] is (final if release else refuge)
    assert bool(node.return_yield_targets) is (not release)


@pytest.mark.parametrize('pending', [False, True])
def test_postcharge_rally_drains_original_legs_before_reordering(monkeypatch, pending):
    from types import SimpleNamespace
    from unittest.mock import Mock
    names = ['far', 'near']
    handle = Mock()
    targets = {'far': control.RallyPose(8., 3., 0.), 'near': control.RallyPose(2., 3., 0.)}
    positions = {name: (pose.x, pose.y) for name, pose in targets.items()}
    reordered = []
    def order(grid, resolution, origin, goals, current, target, detector, return_maps=None):
        reordered.append(current.copy())
        return ['near', 'far']
    monkeypatch.setattr(control, 'map_safe_rally_dispatch_order', order)
    node = SimpleNamespace(
        enable_battery=True, task_state='RALLY', now=lambda:10.,
        fresh_robot_inputs=lambda:True, fresh_robot_poses=lambda:True, fresh_target=lambda:True,
        stop_target_scan=lambda:False, last_input_availability=True,
        battery_monitor_started_at=0., message_freshness_timeout_sec=5.,
        battery_state_received_at=dict.fromkeys(names,10.), battery_modes=dict.fromkeys(names,'ACTIVE'),
        participating_robots=lambda:names, battery_states={}, prepare_rally_charges=lambda:set(),
        rally_charge_requested={}, rally_precharge_staging={}, rally_approach_routes={},
        rally_preflight_complete=False, rally_precharge_active=True,
        rally_dispatch_order=names.copy(), rally_targets=targets.copy(), rally_final_targets=targets.copy(),
        rally_goal_handles={'far':None if pending else handle, 'near':None},
        rally_goal_pending={'far':pending, 'near':False}, rally_goal_started_at={'far':9., 'near':None},
        rally_arrived={'far':False, 'near':True}, rally_leg_routes={'far':((8.,3.),(9.,3.)), 'near':()},
        rally_yield_targets=set(), return_yield_targets={}, rally_probe_targets=set(),
        rally_yield_requested=dict.fromkeys(names,False), rally_hold_started_at=9.,
        survey_goal_handle=None, survey_goal_pending=False, survey_robot=None,
        release_return_yields=lambda:None, yield_to_returning_robot=Mock(), last_rally_dispatch_at=0.,
        global_battery_rally_pause=False, goal_timeout_sec=60., rally_goal_timeout_sec=30.,
        rally_max_concurrent=2, robot_positions=positions, get_logger=lambda:Mock(),
        use_map_safe_rally_order=True, detecting_robot='near', target=(5.,4.),
        map_data=np.zeros((100,100),dtype=int), resolution=.1, origin=(0.,0.),
        send_rally_goal=Mock(), robot_velocities=dict.fromkeys(names,(0.,0.)),
        rally_position_tolerance=.35, rally_linear_tolerance=.05, rally_angular_tolerance=.1,
        rally_hold_sec=5., active_batteries_ready=lambda:True,
    )
    control.HeadquartersControl.update_mission(node)
    assert not reordered and not node.rally_preflight_complete
    assert node.rally_hold_started_at is None and node.rally_dispatch_order == names
    node.send_rally_goal.assert_not_called()
    handle.cancel_goal_async.assert_not_called()
    node.yield_to_returning_robot.assert_called_once()
    # Only the original completion/acceptance callbacks clear these fields.
    node.rally_goal_handles['far'] = None
    node.rally_goal_pending['far'] = False
    node.rally_arrived['far'] = True
    node.now = lambda:12.
    control.HeadquartersControl.update_mission(node)
    assert reordered == [positions] and node.rally_preflight_complete
    assert node.rally_dispatch_order == ['near','far']
    assert node.rally_hold_started_at == 12.
    node.send_rally_goal.assert_not_called()
    # A later future-only reservation can recreate the same wait after the
    # charge cycle. Repair it through the same drain, preserving the live leg.
    node.robot_positions = {'far':(1.05,3.05), 'near':(5.05,3.05)}
    node.rally_targets = {'far':control.RallyPose(9.05,3.05,0.),
                          'near':control.RallyPose(7.05,3.85,0.)}
    node.rally_final_targets = node.rally_targets.copy()
    node.rally_dispatch_order = names.copy()
    node.rally_arrived = dict.fromkeys(names,False)
    node.rally_goal_handles['far'] = None if pending else handle
    node.rally_goal_pending['far'] = pending
    node.rally_leg_routes['far'] = ((1.05,3.05),(2.05,3.05))
    node.rally_approach_routes = {
        name:control.plan_rally_leg(node.rally_targets[name],node.map_data,.1,(0.,0.),
                                    node.robot_positions[name])[1] for name in names}
    node.rally_attempts = dict.fromkeys(names,0)
    node.rally_recovery_requested = dict.fromkeys(names,False)
    node.rally_route_unavailable_since = dict.fromkeys(names)
    node.rally_preflight_complete = True
    node.rally_precharge_active = False
    node.now = lambda:14.
    control.HeadquartersControl.update_mission(node)
    assert not node.rally_preflight_complete and node.rally_precharge_active
    assert node.rally_dispatch_order == names
    node.send_rally_goal.assert_not_called()
    handle.cancel_goal_async.assert_not_called()


@pytest.mark.parametrize('live_leg', ['none', 'pending', 'accepted'])
def test_quiescent_rally_repair_releases_ready_peer_while_observer_waits(live_leg):
    from types import SimpleNamespace
    from unittest.mock import Mock
    names = ['far', 'near', 'observer']
    positions = {'far': (1.05,3.05), 'near': (5.05,3.05), 'observer': (10.05,6.05)}
    targets = {'far': control.RallyPose(9.05,3.05,0.),
               'near': control.RallyPose(7.05,3.85,0.),
               'observer': control.RallyPose(10.05,6.05,0.)}
    grid = np.full((100,120),100,dtype=int)
    grid[26:35,5:115] = 0
    grid[26:90,65:115] = 0
    states = {name: dict(mode='ACTIVE',stamp_sec=10.,energy=80.,capacity=100.,
        charge_target_fraction=.8,charge_x=1.05,charge_y=1.05,charge_radius_m=.8,
        move_cost_per_m=1.,idle_cost_per_sec=.02,nominal_speed_mps=.18,
        return_path_factor=2.,return_safety_margin=8.,return_recovery_wait_sec=30.) for name in names}
    handle = Mock()
    node = SimpleNamespace(
        enable_battery=True,task_state='RALLY',now=lambda:10.,
        fresh_robot_inputs=lambda:True,fresh_robot_poses=lambda:True,fresh_target=lambda:True,
        stop_target_scan=lambda:False,last_input_availability=True,battery_monitor_started_at=0.,
        message_freshness_timeout_sec=5.,battery_state_received_at=dict.fromkeys(names,10.),
        battery_modes=dict.fromkeys(names,'ACTIVE'),participating_robots=lambda:names,battery_states=states,
        prepare_rally_charges=lambda:{'observer'},rally_charge_requested={},rally_precharge_staging={},
        rally_preflight_complete=True,rally_precharge_active=False,rally_dispatch_order=names.copy(),
        rally_targets=targets.copy(),rally_final_targets=targets.copy(),
        rally_goal_handles={'far':handle if live_leg=='accepted' else None,'near':None,'observer':None},
        rally_goal_pending={'far':live_leg=='pending','near':False,'observer':False},
        rally_goal_started_at={'far':9.,'near':None,'observer':None},
        rally_arrived=dict.fromkeys(names,False),rally_leg_routes={name:() for name in names},
        rally_yield_targets=set(),return_yield_targets={},rally_probe_targets=set(),
        rally_yield_requested=dict.fromkeys(names,False),rally_hold_started_at=None,
        survey_goal_handle=None,survey_goal_pending=False,survey_robot=None,
        release_return_yields=lambda:None,yield_to_returning_robot=lambda:None,last_rally_dispatch_at=0.,
        global_battery_rally_pause=False,goal_timeout_sec=60.,rally_goal_timeout_sec=30.,rally_max_concurrent=2,
        robot_positions=positions,get_logger=lambda:Mock(),consumed_publisher=Mock(),
        input_freshness_details=lambda:{},use_map_safe_rally_order=True,detecting_robot='observer',
        target=(10.05,8.05),target_observing_robot='observer',rally_observer_guard='observer',
        robot_yaws=dict.fromkeys(names,0.),target_received_source_time=10.,map_data=grid,
        resolution=.1,origin=(0.,0.),robot_maps={},robot_map_received_at={},
        rally_attempts=dict.fromkeys(names,0),rally_recovery_requested=dict.fromkeys(names,False),
        rally_route_unavailable_since=dict.fromkeys(names),robot_velocities=dict.fromkeys(names,(0.,0.)),
        rally_position_tolerance=.35,rally_linear_tolerance=.05,rally_angular_tolerance=.1,
        rally_hold_sec=5.,active_batteries_ready=lambda:False,
    )
    node.rally_approach_routes = {name: control.plan_rally_leg(pose,grid,.1,(0.,0.),positions[name],
        max_distance_m=float('inf'))[1] for name,pose in targets.items()}
    if live_leg != 'none':
        node.rally_leg_routes['far'] = ((1.05,3.05),(2.05,3.05))
    sent = []
    def send(name,plan,charge_staging=False):
        assert not charge_staging and name != 'observer'
        assert not control.routes_conflict(plan[1],(positions['far'],),control.RALLY_DYNAMIC_CLEARANCE_M)
        sent.append(name)
        node.rally_goal_pending[name] = True
    node.send_rally_goal = send
    control.HeadquartersControl.update_mission(node)
    assert not sent and not node.rally_preflight_complete and node.rally_precharge_active
    if live_leg != 'none':
        assert node.rally_dispatch_order == names
        handle.cancel_goal_async.assert_not_called()
    else:
        assert node.rally_dispatch_order == ['observer','near','far']
        node.now = lambda:11.
        control.HeadquartersControl.update_mission(node)
        assert sent == ['near'] and node.rally_dispatch_order == ['near','far','observer']
        assert not node.rally_preflight_complete


def test_map_safe_order_releases_ahead_robot_before_behind_future_reservation():
    grid = np.zeros((80, 120), dtype=int)
    positions = {'behind': (1.05,3.05), 'ahead': (5.05,3.05)}
    targets = {'behind': control.RallyPose(9.05,3.05,0.),
               'ahead': control.RallyPose(7.05,3.85,0.)}
    order = control.map_safe_rally_dispatch_order(
        grid,.1,(0.,0.),targets,positions,(9.05,5.05),'behind')
    assert order == ['ahead','behind']
    # The preference does not authorize a route through the remaining body.
    occupied = positions.copy()
    for name in order:
        pose, route = control.plan_rally_leg(
            targets[name],grid,.1,(0.,0.),positions[name],
            blocked_positions=[p for peer,p in occupied.items() if peer != name])
        assert pose is not None and route
        occupied[name] = (targets[name].x, targets[name].y)
