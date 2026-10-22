"""Disabled CPU candidate for the independent rational support reader.

No production import or runtime integration. Public directional mathematics,
precision and existing trig-cache entry semantics remain the frozen reader's.
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
    return _sqrt_interval_q(value)


@lru_cache(maxsize=256)
def _sqrt_interval_q(value):
    # The public wrapper validates and canonicalizes before a cache lookup.
    # Keys and returned pairs contain immutable exact Fractions only.
    scale = 1 << SQRT_BITS
    lower = Q(math.isqrt((value.numerator << (2*SQRT_BITS)) // value.denominator), scale)
    return lower, lower if lower*lower == value else lower+Q(1, scale)


_FAC85 = math.factorial(85)
_FAC86 = math.factorial(86)
_COS_COEFFICIENTS = tuple((-1)**k * (_FAC85 // math.factorial(2*k)) for k in range(43))
_SIN_COEFFICIENTS = tuple((-1)**k * (_FAC86 // math.factorial(2*k+1)) for k in range(43))


@lru_cache(maxsize=256)
def trig_enclosure(angle):
    """The original degree84/85 Taylor polynomials and Lagrange remainders.

For canonical p/q, homogeneous integer Horner evaluates exactly the same
polynomials over common denominators 85!*q**85 and 86!*q**86. Only the final
two bounds construct Fractions. The original public cache is retained.
"""
    angle = _q(angle)
    if not 0 <= angle <= 2:
        raise ValueError("unsupported support cone")
    p, q = angle.numerator, angle.denominator
    p2, q2 = p*p, q*q
    cosine, sine = _COS_COEFFICIENTS[-1], _SIN_COEFFICIENTS[-1]
    q_power = q2
    for k in range(41, -1, -1):
        cosine = cosine*p2 + _COS_COEFFICIENTS[k]*q_power
        sine = sine*p2 + _SIN_COEFFICIENTS[k]*q_power
        q_power *= q2
    p85, q85 = p**85, q**85
    return (Q(cosine*q-p85, _FAC85*q85),
            Q(sine*p*q+p85*p, _FAC86*q85*q))


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
