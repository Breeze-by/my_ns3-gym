import pytest
import numpy as np

from multi_robot_exploration.battery_manager import (
    ACTIVE,
    CHARGING,
    RETURNING,
    battery_failure_reason,
    charging_zone_contains,
    charge_target_energy,
    consume_energy,
    estimated_return_energy,
    odometry_distance,
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


def test_late_return_acceptance_is_canceled_after_entering_charge_zone():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from multi_robot_exploration.battery_manager import BatteryManager
    handle = Mock(accepted=True)
    manager = SimpleNamespace(
        mode=CHARGING, mission_terminal=False, return_goal_pending=True,
        return_goal_handle=None, return_goal_result=Mock())
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
        return_attempts=0, max_return_attempts=3, navigation=navigation,
        return_map=grid, return_map_resolution=0.1,
        return_map_origin=(0.0, 0.0), map_position=(1.0, 2.0),
        charge_x=3.0, charge_y=2.0, return_escape_failed=False,
        return_escape_target=None, return_waypoint_target=None,
        return_stage="charger", now=lambda: 10.0)
    BatteryManager.send_return_goal(manager)
    navigation.send_goal_async.assert_not_called()
    assert manager.return_goal_due_at == 11.0
