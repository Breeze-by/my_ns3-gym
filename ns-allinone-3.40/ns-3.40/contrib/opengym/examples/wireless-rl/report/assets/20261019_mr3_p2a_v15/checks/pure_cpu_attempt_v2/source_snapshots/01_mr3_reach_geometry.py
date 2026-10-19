"""Exact reach geometry: necessary geometric conditions under declared sets.

Acceptance here proves a geometric implication *given* the declared reach
sets. It does not certify the plant, a delivered mode, or native admission.
No source of robot state, command generation, or simulator access exists here.
"""

from dataclasses import dataclass
from fractions import Fraction as Q
import math


BODY = Q(1, 4)
GEOMETRY_MARGIN = Q(1, 50)
SPEED = Q(3, 10)
SOURCE_MAX_NS = 500_000_000
BACKUP_HORIZON = Q(39, 50)
RESIDUAL_SPEED = Q(1, 100)
R = RESIDUAL_SPEED * BACKUP_HORIZON
STOP_LONGITUDINAL = Q(18, 125)


def exact(value):
    """A binary64 input retains its exact value; booleans never mean numbers."""
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite numeric input")
        return Q.from_float(value)
    if type(value) in (int, Q):
        return Q(value)
    raise ValueError("expected int, finite float, or exact Fraction")


def point(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("expected XY point")
    return tuple(exact(x) for x in value)


def residual_components(vx, vy, admitted_signs):
    """Orthogonal body-frame decomposition in a declared calibrated basis.

    This is not a world/body conversion of a ROS payload. The prospective
    physical model has to justify that basis separately. A stop target keeps
    the previously admitted signs; it does not instantly remove braking vx.
    """
    vx, vy = exact(vx), exact(vy)
    if (not isinstance(admitted_signs, tuple)
            or any(type(s) is not int or s not in (-1, 1) for s in admitted_signs)
            or len(set(admitted_signs)) != len(admitted_signs)):
        raise ValueError("signs must be a fixed, duplicate-free tuple of -1/+1")
    sign = 1 if vx > 0 else -1 if vx < 0 else 0
    longitudinal = vx if sign in admitted_signs else Q(0)
    rx = vx - longitudinal
    return longitudinal, (rx, vy)


def residual_within_bound(vx, vy, admitted_signs):
    _, (rx, ry) = residual_components(vx, vy, admitted_signs)
    return rx*rx + ry*ry <= RESIDUAL_SPEED*RESIDUAL_SPEED


def sin_cos_bounds(angle):
    """Certified alternating-series bounds on 0 <= angle <= 2 radians.

    The omitted tails after the selected truncations decrease on this
    interval (the first cosine term need not). Forty-two terms give certified
    lower/upper rational bounds, without libm trigonometry or an epsilon.
    Wider cones are conservatively unsupported.
    """
    x = exact(angle)
    if not 0 <= x <= 2:
        raise ValueError("unsupported cone angle")
    sine, cosine = Q(0), Q(0)
    st, ct = x, Q(1)
    sin_lo = sin_hi = cos_lo = cos_hi = None
    for n in range(42):
        sign = 1 if n % 2 == 0 else -1
        sine += sign * st
        cosine += sign * ct
        if n % 2:
            sin_lo, cos_lo = sine, cosine
        else:
            sin_hi, cos_hi = sine, cosine
        st *= x * x / ((2*n + 2) * (2*n + 3))
        ct *= x * x / ((2*n + 1) * (2*n + 2))
    return sin_lo, sin_hi, cos_lo, cos_hi


def nonclosing(delta, axis, half_angle, position_uncertainty):
    """Every unit direction in the cone is nonclosing for the uncertainty disk.

    For dot(axis,delta)<0 and a cone narrower than pi/2, an upper bound on
    the unnormalised support is dot*cos_lower + abs(cross)*sin_upper.
    Squaring compares its negative to U*norm(axis) exactly. The stricter
    original position-uncertainty contribution is retained in this test.
    """
    dx, dy = point(delta)
    ax, ay = point(axis)
    uncertainty = exact(position_uncertainty)
    if uncertainty < 0 or ax*ax + ay*ay == 0:
        raise ValueError("invalid direction or uncertainty")
    dot = ax*dx + ay*dy
    if dot >= 0:
        # A perpendicular exact zero-width direction at U=0 is also valid.
        return dot == 0 and exact(half_angle) == 0 and uncertainty == 0
    sin_lo, sin_hi, cos_lo, cos_hi = sin_cos_bounds(half_angle)
    if cos_lo <= 0:
        return False
    support_upper = dot * cos_lo + abs(ax*dy - ay*dx) * sin_hi
    return (support_upper <= 0 and support_upper*support_upper
            >= uncertainty*uncertainty*(ax*ax + ay*ay))


@dataclass(frozen=True)
class Direction:
    map_axis: tuple
    raw_axis: tuple
    half_angle: Q

    def __post_init__(self):
        for name in ("map_axis", "raw_axis"):
            axis = point(getattr(self, name))
            x, y = axis
            if x*x + y*y == 0:
                raise ValueError("zero heading axis")
            object.__setattr__(self, name, axis)
        angle = exact(self.half_angle)
        if not 0 <= angle <= 2:
            raise ValueError("unsupported cone angle")
        object.__setattr__(self, "half_angle", angle)


@dataclass(frozen=True)
class Reach:
    """Minkowski sum of longitudinal sectors and an isotropic residual ball.

    buffer_m must include every transient and terminal component promised by
    the prospective plant contract. An absent direction leaves the full
    longitudinal distance isotropic. This class never infers that a robot
    has committed to this reach set from a velocity or a storage ACK.
    """
    kind: str
    buffer_m: Q
    longitudinal_m: Q
    directions: tuple = ()

    def __post_init__(self):
        if self.kind not in ("disk", "normal", "transition", "isotropic_stop"):
            raise ValueError("unknown reach kind")
        buffer = exact(self.buffer_m)
        longitudinal = exact(self.longitudinal_m)
        if buffer < 0 or longitudinal < 0:
            raise ValueError("negative reach bound")
        if any(not isinstance(d, Direction) for d in self.directions):
            raise ValueError("invalid direction declaration")
        if self.kind == "disk" and (longitudinal != 0 or buffer < 2*R):
            raise ValueError("a fixed-anchor disk needs its complete 2R diameter")
        if self.kind != "disk" and (longitudinal < STOP_LONGITUDINAL
                or buffer < (4*R if self.kind == "transition" else 2*R)):
            raise ValueError("transient, terminal, and bridge reserves cannot be omitted")
        if self.kind == "isotropic_stop" and self.directions:
            raise ValueError("an isotropic stop has no directional discount")
        object.__setattr__(self, "buffer_m", buffer)
        object.__setattr__(self, "longitudinal_m", longitudinal)
        object.__setattr__(self, "directions", tuple(self.directions))


def disk():
    return Reach("disk", 2*R, Q(0))


def normal(directions=()):
    # PROSPECTIVE assumption: finite transient residual R plus terminal disk R.
    # These components are intentionally not claimed established by old data.
    return Reach("normal", 2*R, STOP_LONGITUDINAL, tuple(directions))


def transition(directions=()):
    # Old disk may move 2R before actual actuation, then the new normal set.
    return Reach("transition", 4*R, STOP_LONGITUDINAL, tuple(directions))


def _one_geometry(delta, left, right, uncertainty, frame):
    dx, dy = point(delta)
    d2 = dx*dx + dy*dy
    longitudinal = []
    direction_checks = []
    for reach, toward in ((left, (dx, dy)), (right, (-dx, -dy))):
        checks = [nonclosing(toward, getattr(d, frame + "_axis"), d.half_angle,
                             uncertainty) for d in reach.directions]
        # A union of possible signs/headings needs all components nonclosing.
        omitted = bool(checks) and all(checks)
        longitudinal.append(Q(0) if omitted else exact(reach.longitudinal_m))
        direction_checks.append(checks)
    required = (2*BODY + GEOMETRY_MARGIN + uncertainty + exact(left.buffer_m)
                + exact(right.buffer_m) + sum(longitudinal))
    return {"necessary_condition_met": d2 >= required*required,
            "distance_squared": str(d2), "required_centre_distance_m": str(required),
            "retained_longitudinal_m": [str(x) for x in longitudinal],
            "direction_checks": direction_checks}


def pair_certificate(map_delta, raw_delta, ages_ns, left, right, *,
                     legacy_hard_gates_passed, common_world_odom_calibrated):
    """Conjunction of map and same-envelope raw geometric necessary checks.

    All non-geometric obligations (actual mode commitment, backup witnesses,
    continuous physical model, source provenance and handoff) remain separate.
    `geometric_necessary` is only a necessary geometric condition. It proves no
    plant model, transport delivery, calibration provenance or mode commitment.
    """
    if (type(legacy_hard_gates_passed) is not bool
            or type(common_world_odom_calibrated) is not bool):
        raise ValueError("explicit hard-gate and calibration declarations required")
    if (not isinstance(ages_ns, (tuple, list)) or len(ages_ns) != 2
            or any(type(x) is not int or not 0 <= x <= SOURCE_MAX_NS for x in ages_ns)):
        raise ValueError("future/stale or invalid geometry source")
    if not isinstance(left, Reach) or not isinstance(right, Reach):
        raise ValueError("two declared reach sets required")
    uncertainty = SPEED * Q(sum(ages_ns), 1_000_000_000)
    mapped = _one_geometry(map_delta, left, right, uncertainty, "map")
    raw = _one_geometry(raw_delta, left, right, uncertainty, "raw")
    return {"schema": "mr3-reach-geometric-necessary-v1",
            "geometric_necessary": (legacy_hard_gates_passed and common_world_odom_calibrated
                         and mapped["necessary_condition_met"] and raw["necessary_condition_met"]),
            "conditional_on_declared_reach_sets": True,
            "uncertainty_m": str(uncertainty), "map": mapped, "raw": raw}
