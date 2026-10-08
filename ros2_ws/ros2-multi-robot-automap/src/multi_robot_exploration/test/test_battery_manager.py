import math

import pytest
import numpy as np

from multi_robot_exploration.battery_manager import (
    ACTIVE,
    CHARGING,
    FAILED,
    RETURNING,
    battery_failure_reason,
    charging_zone_contains,
    charge_target_energy,
    consume_energy,
    estimated_return_energy,
    odometry_distance,
    plan_charging_leg,
    return_escape_pose,
    return_attempt_failure_reason,
)


def test_energy_model_charges_distance_and_elapsed_time():
    assert consume_energy(20.0, 3.0, 10.0, 2.0, 0.1) == pytest.approx(
        13.0
    )


def test_return_reserve_includes_path_time_and_margin():
    reserve = estimated_return_energy(2.0, 1.0, 0.1, 1.5, 0.5, 4.0)

    assert reserve == pytest.approx(7.6)


def test_charge_target_is_a_fraction_of_capacity():
    assert charge_target_energy(60.0, 0.8) == pytest.approx(48.0)


def test_charging_zone_accepts_a_nearby_pose_without_exact_alignment():
    assert charging_zone_contains((0.6, 0.0), (0.0, 0.0), 0.8)
    assert not charging_zone_contains((0.81, 0.0), (0.0, 0.0), 0.8)


def test_failure_reasons_cover_exhaustion_unreachable_and_charge_timeout():
    assert battery_failure_reason(ACTIVE, 0.0, 0.0, 10.0, 20.0) == (
        "battery_exhausted"
    )
    assert battery_failure_reason(RETURNING, 1.0, 10.0, 10.0, 20.0) == (
        "battery_return_unreachable"
    )
    assert battery_failure_reason(CHARGING, 1.0, 20.0, 10.0, 20.0) == (
        "battery_charge_timeout"
    )
    assert not battery_failure_reason(ACTIVE, 1.0, 100.0, 10.0, 20.0)


def test_simulation_empty_battery_constructs_failed_without_a_navigation_goal():
    import json
    import time
    import rclpy
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import String
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from multi_robot_exploration.battery_manager import BatteryManager
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','initial_energy:=0.0'], domain_id=206)
    node = None
    try:
        node = BatteryManager()
        assert node.mode == FAILED and node.failure_reason == 'battery_exhausted'
        assert node.energy == 0 and node.minimum_energy == 0
        assert node.return_goal_handle is None and not node.return_goal_pending
        assert node.return_count == 0 and node.charge_count == 0
        # Constructor runs before the executor receives /clock. FAILED must
        # keep publishing current state after that initial zero clock stamp.
        received=[]
        qos=QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        subscription=node.create_subscription(String,'/tb1/battery_state',
            lambda message:received.append(json.loads(message.data)),qos)
        clock=node.create_publisher(Clock,'/clock',10)
        message=Clock();message.clock.sec=10
        deadline=time.monotonic()+3
        while node.now()<10 and time.monotonic()<deadline:
            clock.publish(message)
            rclpy.spin_once(node,timeout_sec=.02)
        assert node.now()==10
        node.timer_callback()
        while not any(x['stamp_sec']==10 for x in received) and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.02)
        assert any(x['mode']==FAILED and x['stamp_sec']==10 for x in received)
        assert node.mode == FAILED and node.return_count == 0
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def test_odometry_discontinuity_does_not_consume_travel_energy():
    assert odometry_distance(None, (10.0, 10.0), 1.0) == 0.0
    assert odometry_distance((0.0, 0.0), (0.3, 0.4), 1.0) == 0.5
    assert odometry_distance((0.0, 0.0), (2.0, 0.0), 1.0) == 0.0


def test_exhausted_return_retries_report_unreachable():
    assert not return_attempt_failure_reason(2, 3)
    assert return_attempt_failure_reason(3, 3) == (
        "battery_return_unreachable"
    )


def test_return_escape_pose_moves_out_of_inflated_start_cell():
    grid = np.zeros((11, 11), dtype=np.int16)
    grid[4:7, 6:7] = 100
    assert return_escape_pose(
        grid, 0.1, (-0.5, -0.5), (0.0, 0.0), clearance_m=0.15
    ) is not None


def test_charge_contact_planning_preserves_a_reachable_home_route():
    from multi_robot_exploration.control import known_return_route
    grid = np.zeros((100, 100), dtype=np.int16)
    _, full = known_return_route(grid, .1, (-5., -5.), (3., 0.), (0., 0.), .8, include_route=True)
    leg, route = plan_charging_leg(grid, .1, (-5., -5.), (3., 0.), (0., 0.), .8)
    assert (leg.x, leg.y) == full[-1] == route[-1]
    assert math.hypot(leg.x, leg.y) <= .6
    assert sum(math.dist(a, b) for a, b in zip(route, route[1:])) < 3.


@pytest.mark.parametrize("resolution,side", [(.05, -1), (.05, 1), (.1, -1), (.1, 1)])
def test_charging_completes_known_free_clearance_escape_before_long_home_leg(resolution, side):
    from multi_robot_exploration import control
    grid = np.zeros((int(10 / resolution), int(10 / resolution)), dtype=np.int16)
    wall = int(5 / resolution)
    grid[int(4.5 / resolution):int(5.5 / resolution), wall] = 100
    position = (5 + side * .2 + resolution / 2, 5 + resolution / 2)
    home = (5 + side * 3, 2.)
    raw = grid.copy()
    safe = control.traversable_grid(grid, resolution, control.RALLY_PATH_CLEARANCE_M)
    cell = control.world_to_grid(*position, resolution, 0., 0.)
    assert grid[cell] == 0 and not safe[cell]
    endpoint, escape = control.navigation_start_route(grid, safe, cell, math.ceil(.6 / resolution))
    leg, route = plan_charging_leg(grid, resolution, (0., 0.), position, home, .8)
    assert route == tuple(control.grid_to_world(*p, resolution, 0., 0.) for p in escape)
    assert (leg.x, leg.y) == route[-1] and safe[endpoint]
    assert all(grid[p] == 0 for p in escape) and np.array_equal(grid, raw)
    assert math.dist((leg.x, leg.y), home) > 2.
    assert leg.yaw == pytest.approx(control.route_arrival_yaw(route, 0.))
    # Reaching the safe endpoint permits an ordinary home prefix on new input.
    following, _ = plan_charging_leg(grid, resolution, (0., 0.), route[-1], home, .8)
    assert following is not None and math.dist((following.x, following.y), home) <= .6


@pytest.mark.parametrize("raw_start", [-1, 100])
def test_charging_escape_never_snaps_unknown_or_occupied_start(raw_start):
    grid = np.zeros((100, 100), dtype=np.int16)
    grid[50, 50] = raw_start
    raw = grid.copy()
    assert plan_charging_leg(grid, .1, (0., 0.), (5.05, 5.05), (1., 1.), .8) == (None, ())
    assert np.array_equal(grid, raw)


def test_blocked_charger_centre_uses_a_safe_reachable_contact_pose():
    import math
    from unittest.mock import patch
    from multi_robot_exploration import control
    grid = np.zeros((100, 100), dtype=np.int16)
    grid[50, 50] = 100
    with patch.object(control, "path_distance_grid", wraps=control.path_distance_grid) as search:
        leg, route = plan_charging_leg(grid, .1, (-5., -5.), (3., 0.), (0., 0.), .8)
    assert search.call_count == 1
    assert leg is not None and route
    assert math.hypot(leg.x, leg.y) <= .6
    traversable = control.traversable_grid(grid, .1, control.RALLY_PATH_CLEARANCE_M)
    assert all(traversable[control.world_to_grid(x, y, .1, -5., -5.)] for x, y in route)


def test_disconnected_charge_contact_region_never_generates_a_return_leg():
    grid = np.zeros((100, 100), dtype=np.int16)
    grid[:, 60] = 100
    assert plan_charging_leg(grid, .1, (-5., -5.), (3., 0.), (0., 0.), .8) == (None, ())


def test_unknown_charge_contact_region_never_generates_a_return_leg():
    grid = np.zeros((100, 100), dtype=np.int16)
    grid[40:60, 40:60] = -1
    assert plan_charging_leg(grid, .1, (-5., -5.), (3., 0.), (0., 0.), .8) == (None, ())


@pytest.mark.parametrize("mode", [CHARGING, FAILED])
def test_late_return_acceptance_is_canceled_after_charge_or_failure(mode):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from multi_robot_exploration.battery_manager import BatteryManager
    handle = Mock(accepted=True)
    manager = SimpleNamespace(
        mode=mode, mission_terminal=False, return_goal_pending=True,
        return_goal_handle=None, return_goal_result=Mock(), return_cancels=0)
    BatteryManager.return_goal_response(manager, Mock(result=lambda: handle))
    handle.cancel_goal_async.assert_called_once()
    assert manager.return_goal_handle is handle
    assert not manager.return_goal_pending


def test_charging_waits_for_navigation_result_before_starting_timer():
    from types import SimpleNamespace
    from multi_robot_exploration.battery_manager import BatteryManager
    manager = SimpleNamespace(
        in_charging_zone=lambda **kwargs: True,
        return_goal_pending=False, return_goal_handle=object(),
        linear_speed=0.0, angular_speed=0.0,
        stationary_linear=0.15, stationary_angular=0.1,
        charge_stable_started_at=1.0)
    BatteryManager.update_charging(manager, 20.0)
    assert manager.charge_stable_started_at is None


def test_missing_map_route_does_not_send_a_straight_line_return():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from multi_robot_exploration.battery_manager import BatteryManager
    grid = np.full((40, 40), 100, dtype=int)
    grid[20, 10] = 0
    navigation = Mock()
    manager = SimpleNamespace(
        robot_name="tb1", return_attempts=0, max_return_attempts=3, navigation=navigation,
        return_map=grid, return_map_resolution=0.1,
        return_map_origin=(0.0, 0.0), map_position=(1.0, 2.0),
        charge_x=3.0, charge_y=2.0, return_escape_failed=False,
        return_escape_target=None, return_waypoint_target=None,
        return_stage="charger", now=lambda: 10.0)
    manager.return_map_version = 1
    manager.return_route_cache = {}
    manager.audit_return = Mock()
    manager.return_map_evidence = Mock(return_value=None)
    manager.charge_radius = 0.8
    manager.energy = 20.0
    manager.get_logger = Mock()
    BatteryManager.send_return_goal(manager)
    navigation.send_goal_async.assert_not_called()
    assert manager.return_goal_due_at == 11.0


def charge_request_node():
    from types import SimpleNamespace

    returns, consumed = [], []
    node = SimpleNamespace(
        robot_name="tb1", now=lambda: 11.0, last_charge_request_stamp=-float("inf"),
        mission_terminal=False, mode=ACTIVE, energy=20.0, charge_target=80.0,
        map_position=(0., 3.), charge_x=0., charge_y=0., move_cost=1., idle_cost=.02,
        return_path_factor=2., nominal_speed=.18, safety_margin=8.,
        charge_radius=.8, return_map=np.zeros((100,100), dtype=np.int16),
        return_map_resolution=.1, return_map_origin=(-5.,-5.),
        return_map_source_time=10., return_map_source='local', return_map_version=1,
        return_route_cache={}, return_recovery_wait=30., in_charging_zone=lambda:False,
        begin_return=returns.append, consumed_publisher=SimpleNamespace(publish=consumed.append),
        get_logger=lambda: SimpleNamespace(info=lambda *args: None),
    )
    return node, returns, consumed


def charge_message(**changes):
    import json
    from std_msgs.msg import String

    return String(data=json.dumps({"robot": "tb1", "stamp_sec": 10.0,
                                  "required_energy": 40., "task_phase": "RALLY", **changes}))


def test_delivered_charge_request_is_idempotent_and_late_retry_cannot_recharge():
    from multi_robot_exploration.battery_manager import BatteryManager

    node, returns, consumed = charge_request_node()
    BatteryManager.charge_request_callback(node, charge_message())
    BatteryManager.charge_request_callback(node, charge_message())
    from multi_robot_exploration.control import return_energy_budget
    expected = return_energy_budget(2.5 + math.sqrt(.05 ** 2 * 2), 1., .02, 2., .18, 8., source_age_sec=1.)
    assert returns == [pytest.approx(expected['required_energy'])] and len(consumed) == 1
    node.mode = RETURNING
    BatteryManager.charge_request_callback(node, charge_message(stamp_sec=10.2))
    assert len(returns) == 1
    node.mode, node.energy = ACTIVE, 80.0
    BatteryManager.charge_request_callback(node, charge_message(stamp_sec=10.3))
    assert len(returns) == 1


@pytest.mark.parametrize("changes", [
    {"stamp_sec": 1.0}, {"robot": "tb2"}, {"required_energy": float("nan")},
    {"required_energy": 1000}, {"task_phase": "COMPLETE"}, {"stamp_sec": "bad"},
    {"stamp_sec": 11.1},
])
def test_charge_request_rejects_expired_wrong_robot_and_invalid_budget(changes):
    from multi_robot_exploration.battery_manager import BatteryManager

    node, returns, consumed = charge_request_node()
    BatteryManager.charge_request_callback(node, charge_message(**changes))
    assert not returns and not consumed


def test_charge_request_after_mission_terminal_never_starts_return():
    from multi_robot_exploration.battery_manager import BatteryManager

    node, returns, _ = charge_request_node()
    node.mission_terminal = True
    BatteryManager.charge_request_callback(node, charge_message())
    assert not returns


@pytest.mark.parametrize('phase',['EXPLORE','FOUND_UNCONFIRMED','FOUND','RALLY'])
def test_frontier_and_rally_requests_share_local_idempotent_safety_return(phase):
    from multi_robot_exploration.battery_manager import BatteryManager

    node,returns,consumed=charge_request_node()
    BatteryManager.charge_request_callback(node,charge_message(task_phase=phase))
    BatteryManager.charge_request_callback(node,charge_message(task_phase=phase))
    assert len(returns)==len(consumed)==1


def test_safety_return_falls_back_to_own_map_after_ap_loss():
    from types import SimpleNamespace
    from nav_msgs.msg import OccupancyGrid
    from multi_robot_exploration.battery_manager import BatteryManager
    applied=[]
    manager=SimpleNamespace(now=lambda: 10., fused_map_received_at=8., map_callback=applied.append)
    grid=OccupancyGrid()
    BatteryManager.local_map_callback(manager, grid)
    assert applied == [grid]
    manager.fused_map_received_at=4.
    BatteryManager.local_map_callback(manager, grid)
    assert applied == [grid, grid]


def test_physical_failure_cancels_owned_safety_return_once():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from multi_robot_exploration.battery_manager import BatteryManager, FAILED
    handle=Mock()
    manager=SimpleNamespace(mode=RETURNING,return_goal_handle=handle,robot_name="tb1",
                            publish_state=Mock(),failure_publisher=Mock(),get_logger=Mock(),finish_return_audit=Mock(),return_cancels=0,return_goal_cancel_requested=False)
    BatteryManager.fail(manager,"battery_exhausted")
    BatteryManager.fail(manager,"battery_return_unreachable")
    assert manager.mode==FAILED and manager.failure_reason=="battery_exhausted"
    handle.cancel_goal_async.assert_called_once()
    manager.publish_state.assert_called_once()
    assert manager.failure_publisher.publish.call_args.args[0].data=="battery_exhausted:tb1"
