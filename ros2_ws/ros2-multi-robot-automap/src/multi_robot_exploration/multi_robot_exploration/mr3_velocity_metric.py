"""Conditional metric check for the existing WORLD-odom velocity conversion.

The producer's *actual* finite coefficients c/s must be supplied by a future
same-source calibration receipt. This module never estimates them from yaw.
It assumes IEEE binary64 round-to-nearest, no overflow/fast-math/flush-to-zero,
and a separately established world component bound V. The returned implication
does not prove those assumptions or a continuous physical velocity bound.
"""
from fractions import Fraction as Q
from .mr3_reach_geometry import exact, point, RESIDUAL_SPEED, SPEED


UNIT_ROUNDOFF = Q(1, 2**53)
HALF_MIN_SUBNORMAL = Q(1, 2**1075)


def conversion_error(c, s, world_component_bound=SPEED):
    """Per output of fl(c*x+s*y), including two products and the sum.

    For each finite rounded operation, |fl(z)-z| <= u|z|+eta.
    With |x|,|y|<=V and S=V(|c|+|s|), two products then a sum give
    E=(2u+u²)S+(3+2u)eta. A single fused multiply-add has no larger
    error. This does not cover arbitrary reassociation or fast-math.
    """
    c, s, bound = exact(c), exact(s), exact(world_component_bound)
    if c*c+s*s == 0 or bound < 0 or abs(c) > 1 or abs(s) > 1:
        raise ValueError("invalid calibrated coefficients or component bound")
    u, eta = UNIT_ROUNDOFF, HALF_MIN_SUBNORMAL
    return (2*u+u*u)*bound*(abs(c)+abs(s))+(3+2*u)*eta


def residual_certificate(body_x, body_y, c, s, admitted_signs, *,
                         world_component_bound=SPEED,
                         residual_limit=RESIDUAL_SPEED):
    """Conservative residual in the normalised calibrated c/s body basis.

    A=[[c,s],[-s,c]], A*A^T=q*I. The unrounded A*w is inside the
    rectangle (body_x±E,body_y±E). Dividing its residual norm² by q
    checks the physical metric without a rounded square root. A stop
    retains its previously admitted signs. Continuous plant bounds and
    the difference from the physical heading cone remain external.
    """
    if (not isinstance(admitted_signs, tuple)
            or any(type(v) is not int or v not in (-1, 1) for v in admitted_signs)
            or len(set(admitted_signs)) != len(admitted_signs)):
        raise ValueError("fixed duplicate-free signed longitudinal set required")
    bx, by, c, s, limit = (exact(v) for v in (body_x, body_y, c, s, residual_limit))
    if limit < 0:
        raise ValueError("negative residual limit")
    error = conversion_error(c, s, world_component_bound)
    lower, upper = bx-error, bx+error
    rx = max(Q(0), -lower if -1 not in admitted_signs else Q(0),
             upper if 1 not in admitted_signs else Q(0))
    ry = max(abs(by-error), abs(by+error))
    q = c*c+s*s
    numerator = rx*rx+ry*ry
    return {
        "schema": "mr3-velocity-metric-necessary-v1",
        "metric_necessary": numerator <= limit*limit*q,
        "residual_norm_squared_upper": str(numerator/q),
        "coefficient_norm_squared": str(q),
        "per_component_rounding_error_bound": str(error),
        "declared_world_component_bound": str(exact(world_component_bound)),
        "conditional_calibrated_basis_only": True,
        "physical_heading_cone_calibration_proved": False,
    }


def physical_residual_certificate(body_x, body_y, c, s, heading_axis, admitted_signs, *,
                                  world_component_bound=SPEED,
                                  residual_limit=RESIDUAL_SPEED):
    """Bound residual in the supplied physical-heading basis, not c/s's basis.

    For A=[[c,s],[-s,c]], inverse A=A^T/q. The raw quaternion-derived
    heading h is supplied separately: no sinf accuracy or unit-coefficient
    assumption aligns A with h. Exact projection of A^T*b and its rounding
    rectangle gives a squared physical residual bound, without a square root.
    The actual quaternion/heading calibration, WORLD component bound, IEEE
    conversion semantics and continuous physical model remain external.
    """
    if (not isinstance(admitted_signs, tuple)
            or any(type(v) is not int or v not in (-1, 1) for v in admitted_signs)
            or len(set(admitted_signs)) != len(admitted_signs)):
        raise ValueError("fixed duplicate-free signed longitudinal set required")
    bx, by, c, s, limit = (exact(v) for v in (body_x, body_y, c, s, residual_limit))
    hx, hy = point(heading_axis)
    h2 = hx*hx+hy*hy
    if h2 == 0 or limit < 0:
        raise ValueError("nonzero physical heading and nonnegative residual required")
    error = conversion_error(c, s, world_component_bound)
    f0, f1 = hx*c+hy*s, -hx*s+hy*c
    l0, l1 = -hy*c+hx*s, hy*s+hx*c
    forward, lateral = f0*bx+f1*by, l0*bx+l1*by
    forward_error = error*(abs(f0)+abs(f1))
    lateral_error = error*(abs(l0)+abs(l1))
    lower, upper = forward-forward_error, forward+forward_error
    wrong = max(Q(0), -lower if -1 not in admitted_signs else Q(0),
                upper if 1 not in admitted_signs else Q(0))
    side = max(abs(lateral-lateral_error), abs(lateral+lateral_error))
    numerator = wrong*wrong+side*side
    q = c*c+s*s
    denominator = q*q*h2
    return {
        "schema": "mr3-physical-heading-residual-necessary-v1",
        "metric_necessary": numerator <= limit*limit*denominator,
        "residual_norm_squared_upper": str(numerator/denominator),
        "coefficient_norm_squared": str(q),
        "heading_axis_norm_squared": str(h2),
        "per_component_rounding_error_bound": str(error),
        "forward_projection_error_bound": str(forward_error),
        "lateral_projection_error_bound": str(lateral_error),
        "declared_world_component_bound": str(exact(world_component_bound)),
        "conditional_on_heading_and_world_component_bound": True,
        "physical_heading_calibration_proved": False,
    }
