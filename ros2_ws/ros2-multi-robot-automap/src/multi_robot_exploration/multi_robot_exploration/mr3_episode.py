"""Public scalar episode rules, without reward, truth, ROS or array dependencies."""

import math


TASK_DURATION_SEC = 300.0
NANOSECONDS_PER_SECOND = 10**9
TASK_DURATION_NS = round(TASK_DURATION_SEC * NANOSECONDS_PER_SECOND)
TASK_FAILURE_REASONS = frozenset((
    "timeout", "navigation_failure", "collision", "collision_monitoring_interrupted",
    "map_contract_error", "pose_discontinuity", "task_gate_regressed_during_closure",
    "navigation_closure_timeout", "navigation_closure_invalid",
))


def finite_time(value, name):
    """Validate one finite, nonnegative simulation timestamp or duration."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite simulation time")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite nonnegative simulation time")
    return value


def timestamp_ns(stamp):
    """Recover physical nanoseconds by rounding the original endpoint.

    Subtract integer endpoints, never a floating-point difference. This adds no
    tolerance and does not extend the task duration at exact deadline boundaries.
    """
    return round(finite_time(stamp, "timestamp") * NANOSECONDS_PER_SECOND)


def elapsed_ns(start, end):
    """Signed elapsed nanoseconds; callers explicitly reject a time rewind."""
    return timestamp_ns(end) - timestamp_ns(start)
