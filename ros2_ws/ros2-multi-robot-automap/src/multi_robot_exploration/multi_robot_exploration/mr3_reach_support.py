"""Explicit cone-support-v2 separation certificate for unchanged Reach sets.

The binary-cone-v1 default remains mr3_reach_geometry.pair_certificate.
This pure module proves conditional sufficient separation, not plant validity,
actual mode delivery, provenance or complete native qualification.
Its mathematical helpers retain the independently reviewed A43 CPU algorithm.
"""
from fractions import Fraction as Q
from functools import lru_cache
import hashlib
import json
import math

from multi_robot_exploration.mr3_reach_geometry import (
    BODY, GEOMETRY_MARGIN, SPEED, SOURCE_MAX_NS, BACKUP_HORIZON,
    RESIDUAL_SPEED, STOP_LONGITUDINAL, R, Reach,
    exact, point, nonclosing, sin_cos_bounds,
)

PROFILE = 'mr3-reach-reported-line-support-v2'
REACH_GEOMETRY_RULE = 'cone-support-v2'
SQRT_BITS = 96
HEADING_RATE = Q(6, 5)
EXTRA_DIRECTION_UNCERTAINTY = True
LOG_INTERVAL_BITS = 48


def sqrt_bounds(value):
    """Exact rational enclosing sqrt; the fixed bit count is not a tolerance.

    For s=2**96, k=floor(sqrt(floor(value*s*s))) gives
    (k/s)**2 <= value < ((k+1)/s)**2. Exact grid roots have equal bounds.
    A positive root with lower=0 is unsupported for division, never rounded up.
    """
    value = exact(value)
    if value < 0:
        raise ValueError('negative squared norm')
    return _sqrt_bounds_cached(value, SQRT_BITS)


@lru_cache(maxsize=256)
def _sqrt_bounds_cached(value, bits):
    """Validated exact keys and immutable numeric results only; no proofs."""
    scale = 1 << bits
    k = math.isqrt(value.numerator * scale * scale // value.denominator)
    lower = Q(k, scale)
    upper = lower if lower * lower == value else Q(k + 1, scale)
    return lower, upper


def _str_bounds(bounds):
    return [str(bounds[0]), str(bounds[1])]


def direction_support_upper(delta, axis, half_angle, uncertainty, longitudinal):
    """JSON proof record, upper-bounding one origin-containing sector support.

    The upper bound is along n=reported_delta/|reported_delta|. It deliberately
    also includes the old robust-direction U as a conservative *cosine* term,
    while the full centre-position U remains in the outer distance reserve.
    It is NOT an exact sector distance or a native permission.
    """
    dx, dy = point(delta)
    ax, ay = point(axis)
    phi, uncertainty, longitudinal = map(exact, (half_angle, uncertainty, longitudinal))
    if not 0 <= phi <= 2 or uncertainty < 0 or longitudinal < 0:
        raise ValueError('unsupported cone/negative uncertainty/length')
    axis2, delta2 = ax * ax + ay * ay, dx * dx + dy * dy
    if axis2 == 0:
        raise ValueError('zero heading axis')
    dot, cross = ax * dx + ay * dy, ax * dy - ay * dx
    axis_bounds, delta_bounds = sqrt_bounds(axis2), sqrt_bounds(delta2)
    record = {'axis': [str(ax), str(ay)], 'delta': [str(dx), str(dy)],
              'half_angle_rad': str(phi), 'uncertainty_m': str(uncertainty),
              'longitudinal_m': str(longitudinal), 'dot': str(dot), 'cross': str(cross),
              'axis_norm_bounds': _str_bounds(axis_bounds),
              'delta_norm_bounds': _str_bounds(delta_bounds),
              'extra_direction_uncertainty_in_cosine': True}

    def finish(mode, ratio):
        # All callers pass an exact enclosing ratio; cap1 is independently valid
        # because no unit projection of a radius<=L sector can exceed L.
        ratio = max(Q(0), min(Q(1), ratio))
        record.update(mode=mode, cosine_upper=str(ratio),
                      support_upper_m=str(longitudinal * ratio))
        return record

    if delta2 == 0:
        return finish('zero_reported_delta_full_L', Q(1))
    if dot >= 0:
        # The original nonclosing function admits this exact perpendicular
        # zero-width/U=0 special case before the nonnegative-dot fallback.
        if dot == 0 and phi == 0 and uncertainty == 0:
            return finish('original_nonclosing_zero', Q(0))
        return finish('nonnegative_dot_full_L', Q(1))
    sin_lo, sin_hi, cos_lo, cos_hi = sin_cos_bounds(phi)
    h_upper = None
    if cos_lo > 0:
        # Same exact original nonclosing predicate, calculated once. Retain
        # its early-return field shape before adding the projected proof.
        h_upper = dot * cos_lo + abs(cross) * sin_hi
        if (h_upper <= 0 and h_upper * h_upper
                >= uncertainty * uncertainty * axis2):
            return finish('original_nonclosing_zero', Q(0))
    record.update(sin_bounds=[str(sin_lo), str(sin_hi)],
                  cos_bounds=[str(cos_lo), str(cos_hi)])
    if cos_lo <= 0:
        return finish('nonacute_cone_full_L', Q(1))
    if axis_bounds[0] <= 0 or delta_bounds[0] <= 0:
        return finish('nonpositive_norm_lower_full_L', Q(1))
    extra = uncertainty * axis_bounds[1]
    numerator = h_upper + extra
    denominator = axis_bounds[0] * delta_bounds[0]
    # For a negative numerator, zero is a valid upper bound after including
    # radius zero. Dividing that negative number by a lower bound is unnecessary.
    ratio = Q(0) if numerator <= 0 else numerator / denominator
    record.update(unnormalized_support_upper=str(h_upper),
                  extra_uncertainty_numerator=str(extra),
                  numerator_upper=str(numerator), denominator_lower=str(denominator))
    return finish('acute_negative_dot_projected_upper', ratio)


def _reach_support(delta, reach, frame, uncertainty):
    if not isinstance(reach, Reach):
        raise ValueError('expected original validated Reach')
    if not reach.directions:
        # D is L=0. N/X without directions retain their full isotropic L.
        return {'kind': reach.kind, 'buffer_m': str(reach.buffer_m),
                'longitudinal_m': str(reach.longitudinal_m),
                'support_upper_m': str(reach.longitudinal_m),
                'union_rule': 'no_directions_full_L', 'directions': []}
    rows = [direction_support_upper(delta, getattr(direction, frame + '_axis'),
                direction.half_angle, uncertainty, reach.longitudinal_m)
            for direction in reach.directions]
    # Different admitted signs/headings form a UNION, not a sum or intersection.
    upper = max(Q(row['support_upper_m']) for row in rows)
    return {'kind': reach.kind, 'buffer_m': str(reach.buffer_m),
            'longitudinal_m': str(reach.longitudinal_m),
            'support_upper_m': str(upper), 'union_rule': 'maximum', 'directions': rows}


def _frame_certificate(delta, left, right, uncertainty, frame):
    dx, dy = point(delta)
    delta2 = dx * dx + dy * dy
    l = _reach_support((dx, dy), left, frame, uncertainty)
    r = _reach_support((-dx, -dy), right, frame, uncertainty)
    base = 2 * BODY + GEOMETRY_MARGIN + uncertainty + left.buffer_m + right.buffer_m
    required = base + Q(l['support_upper_m']) + Q(r['support_upper_m'])
    required_squared = required * required
    # No displayed float/root upper bound is used to admit a pair.
    passed = delta2 > 0 and delta2 >= required_squared
    return {'frame': frame, 'reported_normal_defined': delta2 > 0,
            'distance_squared': str(delta2), 'distance_norm_bounds': _str_bounds(sqrt_bounds(delta2)),
            'base_reserve_m': str(base), 'required_centre_distance_upper_m': str(required),
            'squared_slack_m2': str(delta2 - required_squared),
            'separation_sufficient_under_declared_sets': passed,
            'left': l, 'right': r}


def log_interval(value):
    """Outward rational display enclosure only; never used for admission."""
    value = exact(value)
    scale = 1 << LOG_INTERVAL_BITS
    scaled = value * scale
    lower = scaled.numerator // scaled.denominator
    upper = -((-scaled.numerator) // scaled.denominator)
    return [str(Q(lower, scale)), str(Q(upper, scale))]


def _support_summary(full):
    return {key: full[key] for key in ('kind', 'buffer_m', 'longitudinal_m', 'union_rule')} | {
        'support_upper_bounds_m': log_interval(Q(full['support_upper_m'])),
        'direction_modes': [row['mode'] for row in full['directions']]}


def _frame_summary(full):
    """Compact log-only enclosures plus a digest of the complete exact proof.

    Independent audit recomputes from original inputs, not these intermediates.
    Taylor fractions are intentionally not repeated at every 50Hz decision.
    """
    encoded = json.dumps(full, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    distance = full['distance_norm_bounds']
    return {'frame': full['frame'], 'reported_normal_defined': full['reported_normal_defined'],
            'separation_sufficient_under_declared_sets': full['separation_sufficient_under_declared_sets'],
            'log_intervals_only': True, 'log_interval_bits': LOG_INTERVAL_BITS,
            'distance_squared_bounds_m2': log_interval(Q(full['distance_squared'])),
            'distance_norm_bounds_m': [log_interval(Q(distance[0]))[0], log_interval(Q(distance[1]))[1]],
            'base_reserve_m': full['base_reserve_m'],
            'required_centre_distance_upper_bounds_m': log_interval(Q(full['required_centre_distance_upper_m'])),
            'squared_slack_bounds_m2': log_interval(Q(full['squared_slack_m2'])),
            'left': _support_summary(full['left']), 'right': _support_summary(full['right']),
            'full_exact_frame_sha256': hashlib.sha256(encoded).hexdigest()}


def support_pair_certificate(map_delta, raw_delta, ages_ns, left, right, *,
                             legacy_hard_gates_passed, common_world_odom_calibrated):
    """Conditional geometry only, with original hard gates, U and frame AND.

    The runtime caller still enforces all original role/driver/source/
    calibration/plant obligations; this pure certificate performs none of them.
    """
    if type(legacy_hard_gates_passed) is not bool or type(common_world_odom_calibrated) is not bool:
        raise ValueError('explicit original hard-gate/calibration bools required')
    if (not isinstance(ages_ns, (tuple, list)) or len(ages_ns) != 2
            or any(type(age) is not int or not 0 <= age <= SOURCE_MAX_NS for age in ages_ns)):
        raise ValueError('original source-age bounds required')
    if not isinstance(left, Reach) or not isinstance(right, Reach):
        raise ValueError('expected original Reach instances')
    uncertainty = SPEED * Q(sum(ages_ns), 1_000_000_000)
    mapped = _frame_certificate(map_delta, left, right, uncertainty, 'map')
    raw = _frame_certificate(raw_delta, left, right, uncertainty, 'raw')
    geometry = (mapped['separation_sufficient_under_declared_sets']
                and raw['separation_sufficient_under_declared_sets'])
    admission = legacy_hard_gates_passed and common_world_odom_calibrated and geometry
    return {'schema': 'mr3-reach-cone-support-separation-v2', 'profile': PROFILE,
            'reach_geometry_rule': REACH_GEOMETRY_RULE, 'production_enabled': True,
            'conditional_on_declared_reach_sets': True,
            'extra_direction_uncertainty_in_cosine': True, 'sqrt_bits': SQRT_BITS,
            'legacy_hard_gates_passed': legacy_hard_gates_passed,
            'common_world_odom_calibrated': common_world_odom_calibrated,
            'ages_ns': list(ages_ns), 'uncertainty_m': str(uncertainty),
            'input_geometry': {'map_delta': [str(value) for value in point(map_delta)],
                               'raw_delta': [str(value) for value in point(raw_delta)]},
            'geometric_sufficient': admission, 'geometric_necessary': admission,
            'geometric_necessary_semantics':
                'historical_runtime_admission_boolean; v2 is conditional sufficient separation',
            'map': _frame_summary(mapped), 'raw': _frame_summary(raw),
            'unchanged_constants': {
                'body_m': str(BODY), 'geometry_margin_m': str(GEOMETRY_MARGIN),
                'position_age_speed_mps': str(SPEED), 'source_max_ns': SOURCE_MAX_NS,
                'backup_horizon_sec': str(BACKUP_HORIZON), 'heading_rate_radps': str(HEADING_RATE),
                'residual_speed_mps': str(RESIDUAL_SPEED), 'R_m': str(R),
                'stop_longitudinal_m': str(STOP_LONGITUDINAL),
                'normal_disk_buffer_m': str(2 * R), 'transition_buffer_m': str(4 * R)}}
