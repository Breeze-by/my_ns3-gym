"""Independent rational sector-support upper bounds for cone-support-v2.

No production geometry, tracker or support implementation is imported. These
bounds check the declared sets only; they establish no plant or native credit.
"""
from fractions import Fraction as Q
from functools import lru_cache
import math


SQRT_BITS = 96


def _q(value):
    if type(value) is float and math.isfinite(value):
        return Q.from_float(value)
    if type(value) in (int, Q):
        return Q(value)
    raise ValueError("invalid exact support scalar")


def _point(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("support requires XY vectors")
    return tuple(_q(x) for x in value)


def sqrt_interval(value):
    value = _q(value)
    if value < 0:
        raise ValueError("negative support squared norm")
    scale = 1 << SQRT_BITS
    lower = Q(math.isqrt((value.numerator << (2*SQRT_BITS)) // value.denominator), scale)
    return lower, lower if lower*lower == value else lower+Q(1, scale)


@lru_cache(maxsize=256)
def trig_enclosure(angle):
    """Independent Taylor/Lagrange bounds, not production alternating tails.

    The degree84 cosine and degree85 sine polynomials have absolute Lagrange
    remainders at most x**85/85! and x**86/86!, since all derivatives <=1.
    These are deliberately tighter than the original 42-term zero certificate
    on [0,2], while using a separate remainder argument.
    """
    angle = _q(angle)
    if not 0 <= angle <= 2:
        raise ValueError("unsupported support cone")
    cosine = sum((-1)**k*angle**(2*k)/math.factorial(2*k) for k in range(43))
    sine = sum((-1)**k*angle**(2*k+1)/math.factorial(2*k+1) for k in range(43))
    return cosine-angle**85/math.factorial(85), sine+angle**86/math.factorial(86)


def direction_support_upper(bearing, direction, angle, uncertainty, length):
    """Upper length along the reported bearing, with original extra-U reserve.

    The origin belongs to the sector. Unknown/closing/nonacute directions keep
    the whole length. A positive numerator is divided only by norm lower
    bounds; U times the axis norm upper is retained inside that numerator.
    """
    dx, dy = _point(bearing)
    ax, ay = _point(direction)
    angle, uncertainty, length = map(_q, (angle, uncertainty, length))
    if not 0 <= angle <= 2 or uncertainty < 0 or length < 0:
        raise ValueError("invalid support angle/reserve/length")
    axis2, delta2 = ax*ax+ay*ay, dx*dx+dy*dy
    if axis2 == 0:
        raise ValueError("zero support axis")
    if delta2 == 0:
        return length
    dot, cross = ax*dx+ay*dy, ax*dy-ay*dx
    if dot == 0 and angle == 0 and uncertainty == 0:
        return Q(0)
    if dot >= 0:
        return length
    cosine_lower, sine_upper = trig_enclosure(angle)
    if cosine_lower <= 0:
        return length
    projection_upper = dot*cosine_lower+abs(cross)*sine_upper
    if projection_upper <= 0 and projection_upper**2 >= uncertainty**2*axis2:
        return Q(0)
    axis_lower, axis_upper = sqrt_interval(axis2)
    delta_lower, _ = sqrt_interval(delta2)
    if axis_lower <= 0 or delta_lower <= 0:
        return length
    numerator = projection_upper+uncertainty*axis_upper
    if numerator <= 0:
        return Q(0)
    return length*min(Q(1), numerator/(axis_lower*delta_lower))
