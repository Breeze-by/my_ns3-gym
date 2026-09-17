import pytest

from multi_robot_exploration.battery_manager import (
    ACTIVE,
    CHARGING,
    RETURNING,
    battery_failure_reason,
    consume_energy,
    estimated_return_energy,
    odometry_distance,
    return_attempt_failure_reason,
)


def test_energy_model_charges_distance_and_elapsed_time():
    assert consume_energy(20.0, 3.0, 10.0, 2.0, 0.1) == pytest.approx(
        13.0
    )


def test_return_reserve_includes_path_time_and_margin():
    reserve = estimated_return_energy(2.0, 1.0, 0.1, 1.5, 0.5, 4.0)

    assert reserve == pytest.approx(7.6)


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
