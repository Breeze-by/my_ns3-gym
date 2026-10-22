"""Artificial CPU checks only. Not executed by their author.

Numerical oracles below are bug searches, not proofs of continuous-set safety.
No scene, World, actual episode, extracted native row or actor input is loaded.
"""
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
from fractions import Fraction as Q

import pytest
from multi_robot_exploration import mr3_reach_geometry as legacy

_path = Path(__file__).with_name('support_prototype_v1.py')
_spec = importlib.util.spec_from_file_location('mr3_disabled_support_prototype', _path)
candidate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(candidate)

FLAGS = {'legacy_hard_gates_passed': True, 'common_world_odom_calibrated': True}
L = legacy.STOP_LONGITUDINAL


def pair(delta, left=None, right=None, ages=(0, 0), raw=None, **flags):
    return candidate.support_pair_certificate(delta, delta if raw is None else raw, ages,
        legacy.disk() if left is None else left, legacy.disk() if right is None else right,
        **(flags or FLAGS))


def directed(axis, phi=Q(1, 5), *, raw_axis=None, role='N'):
    direction = legacy.Direction(axis, axis if raw_axis is None else raw_axis, phi)
    return (legacy.normal if role == 'N' else legacy.transition)((direction,))


@pytest.mark.parametrize('value', [Q(0), Q(1), Q(2), Q(1, 64), Q(3, 7),
                                  Q(1, 2**400), Q(10**40 + 1)])
def test_sqrt_bounds_are_exact_enclosures(value):
    lo, hi = candidate.sqrt_bounds(value)
    assert lo >= 0 and lo * lo <= value <= hi * hi
    assert hi - lo <= Q(1, 1 << candidate.SQRT_BITS)
    if lo == hi:
        assert lo * lo == value
    else:
        assert lo * lo < value < hi * hi


@pytest.mark.parametrize('value', [Q(-1), True, math.inf])
def test_sqrt_invalid_inputs_rejected(value):
    with pytest.raises(ValueError):
        candidate.sqrt_bounds(value)


@pytest.mark.parametrize('delta,axis,phi,uncertainty', [
    ((1, 0), (-1, 0), Q(0), Q(0)),
    ((3, 4), (-3, -4), Q(1, 4), Q(1, 50)),
    ((1, 0), (0, 1), Q(0), Q(0)),
    ((2, 0), (-1, 0), Q(1, 5), Q(3, 10)),
])
def test_original_nonclosing_zero_and_sector_origin_preserved(delta, axis, phi, uncertainty):
    assert legacy.nonclosing(delta, axis, phi, uncertainty)
    proof = candidate.direction_support_upper(delta, axis, phi, uncertainty, L)
    assert proof['mode'] == 'original_nonclosing_zero'
    assert Q(proof['support_upper_m']) == 0


def test_exact_extra_U_units_and_no_silent_subtraction():
    # All norms are exact rational roots, so the independent expected value is
    # exactly L*((-.075+.1)/.125)=L/5, not L*.2+U or direct extra +U.
    proof = candidate.direction_support_upper((Q(1, 8), 0), (Q(-3, 5), Q(4, 5)),
                                               Q(0), Q(1, 10), L)
    assert proof['mode'] == 'acute_negative_dot_projected_upper'
    assert Q(proof['unnormalized_support_upper']) == Q(-3, 40)
    assert Q(proof['extra_uncertainty_numerator']) == Q(1, 10)
    assert Q(proof['denominator_lower']) == Q(1, 8)
    assert Q(proof['cosine_upper']) == Q(1, 5)
    assert Q(proof['support_upper_m']) == L / 5
    p = pair((2, 0), ages=(500_000_000, 500_000_000))
    assert Q(p['uncertainty_m']) == Q(3, 10)
    assert Q(p['map']['base_reserve_m']) == 2*legacy.BODY + legacy.GEOMETRY_MARGIN + 4*legacy.R + Q(3,10)


@pytest.mark.parametrize('scale', [Q(1, 1024), Q(1), Q(7), Q(2**100)])
def test_positive_axis_scaling_does_not_change_exact_unit_fixture(scale):
    proof = candidate.direction_support_upper((Q(1, 8), 0),
        (scale * Q(-3, 5), scale * Q(4, 5)), Q(0), Q(1, 10), L)
    assert Q(proof['support_upper_m']) == L / 5


@pytest.mark.parametrize('axis', [(0, 0), (math.nan, 1), (True, 0)])
def test_zero_or_invalid_axis_never_repaired(axis):
    with pytest.raises(ValueError):
        candidate.direction_support_upper((1, 0), axis, Q(1, 5), Q(0), L)


@pytest.mark.parametrize('axis', [(1, 0), (0, 1)])
def test_closing_or_tangent_with_uncertainty_conservatively_retains_full_L(axis):
    proof = candidate.direction_support_upper((1, 0), axis, Q(1, 5), Q(1, 10), L)
    assert proof['mode'] == 'nonnegative_dot_full_L'
    assert Q(proof['support_upper_m']) == L


def test_nonacute_cone_retains_full_L():
    proof = candidate.direction_support_upper((1, 0), (-1, 0), Q(2), Q(0), L)
    assert proof['mode'] == 'nonacute_cone_full_L'
    assert Q(proof['support_upper_m']) == L


@pytest.mark.parametrize('reach', [legacy.disk(), legacy.normal(), legacy.transition()])
def test_absent_direction_is_not_assumed_away(reach):
    proof = pair((2, 0), left=reach)
    assert Q(proof['map']['left']['support_upper_m']) == reach.longitudinal_m
    assert proof['map']['left']['union_rule'] == 'no_directions_full_L'


def test_tiny_positive_norm_lower_falls_back_without_division():
    proof = candidate.direction_support_upper((Q(1, 2**300), 0), (-1, 1),
                                              Q(1), Q(1, 100), L)
    assert proof['delta_norm_bounds'][0] == '0'
    assert proof['mode'] == 'nonpositive_norm_lower_full_L'
    assert Q(proof['support_upper_m']) == L


def test_zero_reported_delta_cannot_define_a_separating_normal():
    proof = pair((0, 0), left=directed((-1, 0)))
    assert proof['geometric_sufficient'] is False
    assert proof['map']['reported_normal_defined'] is False


def test_large_robust_upper_clamps_to_full_L_not_unbounded_or_negative():
    proof = candidate.direction_support_upper((Q(1, 10), 0), (Q(-1, 10), 1),
                                              Q(7, 5), Q(3, 10), L)
    assert proof['mode'] == 'acute_negative_dot_projected_upper'
    assert Q(proof['cosine_upper']) == 1
    assert Q(proof['support_upper_m']) == L


def test_union_uses_max_not_min_or_sum():
    away = legacy.Direction((-1, 0), (-1, 0), Q(1, 5))
    closing = legacy.Direction((1, 0), (1, 0), Q(1, 5))
    mixed = pair((Q(3, 5), 0), left=legacy.normal((away, closing)))
    assert Q(mixed['map']['left']['support_upper_m']) == L
    assert mixed['geometric_sufficient'] is False
    duplicated = pair((Q(3, 5), 0), left=legacy.normal((closing, closing)))
    assert Q(duplicated['map']['left']['support_upper_m']) == L
    assert len(duplicated['map']['left']['directions']) == 2


def test_right_support_uses_opposite_normal():
    left, right = directed((-1, 0)), directed((1, 0))
    assert pair((Q(3, 5), 0), left, right)['geometric_sufficient'] is True
    assert pair((Q(3, 5), 0), left, directed((-1, 0)))['geometric_sufficient'] is False


def test_map_raw_cannot_borrow_each_others_certificate():
    left = directed((-1, 0), raw_axis=(1, 0))
    proof = pair((Q(3, 5), 0), left=left)
    assert proof['map']['separation_sufficient_under_declared_sets'] is True
    assert proof['raw']['separation_sufficient_under_declared_sets'] is False
    assert proof['geometric_sufficient'] is False


@pytest.mark.parametrize('epsilon,expected', [(Q(0), True), (Q(-1, 10**10), False)])
def test_exact_distance_threshold_includes_equality_without_epsilon(epsilon, expected):
    base = 2 * legacy.BODY + legacy.GEOMETRY_MARGIN + 4 * legacy.R
    proof = pair((base + epsilon, 0))
    assert proof['geometric_sufficient'] is expected
    assert Q(proof['map']['required_centre_distance_upper_m']) == base


@pytest.mark.parametrize('gates', [
    {'legacy_hard_gates_passed': False, 'common_world_odom_calibrated': True},
    {'legacy_hard_gates_passed': True, 'common_world_odom_calibrated': False},
    {'legacy_hard_gates_passed': False, 'common_world_odom_calibrated': False},
])
def test_original_hard_flags_still_block(gates):
    proof = pair((2, 0), **gates)
    assert proof['map']['separation_sufficient_under_declared_sets'] is True
    assert proof['geometric_sufficient'] is False


@pytest.mark.parametrize('ages', [(-1, 0), (500_000_001, 0), (True, 0),
                                 (0.0, 0), (0,), (0, 0, 0)])
def test_original_source_ages_strictly_validated(ages):
    with pytest.raises(ValueError):
        pair((2, 0), ages=ages)


@pytest.mark.parametrize('flags', [
    {'legacy_hard_gates_passed': 1, 'common_world_odom_calibrated': True},
    {'legacy_hard_gates_passed': True, 'common_world_odom_calibrated': None},
])
def test_hard_flags_are_not_truthy_substitutes(flags):
    with pytest.raises(ValueError):
        pair((2, 0), **flags)


def test_fixed_artificial_triangle_refines_binary_discount_without_changing_constants():
    # Deliberately artificial exact geometry, not a replay of a source row.
    ages = (50_000_000, 50_000_000)
    left = candidate.declared_reach('X', (1, 0), (1, 0), ages[0], (1,))
    right = legacy.disk()
    assert left.directions[0].half_angle == Q(249, 250)
    for sign in (-1, 1):
        delta = (Q(-9, 20), sign * Q(9, 20))
        old = legacy.pair_certificate(delta, delta, ages, left, right, **FLAGS)
        new = pair(delta, left, right, ages)
        assert old['geometric_necessary'] is False
        assert new['geometric_sufficient'] is True
        assert Q(new['map']['base_reserve_m']) == Q(373, 625)
        assert new['unchanged_constants']['heading_rate_radps'] == '6/5'
        assert new['production_enabled'] is False
        assert new['native_qualification_credit'] is False


def test_stale_uncertain_triangle_still_rejected_and_both_X_reserves_preserved():
    ages = (500_000_000, 500_000_000)
    left = candidate.declared_reach('X', (1, 0), (1, 0), ages[0], (1,))
    right = candidate.declared_reach('X', (-1, 0), (-1, 0), ages[1], (1,))
    proof = pair((Q(-9, 20), Q(9, 20)), left, right, ages)
    assert proof['geometric_sufficient'] is False
    assert Q(proof['map']['base_reserve_m']) == 2*legacy.BODY + legacy.GEOMETRY_MARGIN + Q(3,10) + 8*legacy.R


def numeric_sector_support(delta, axis, phi, length):
    """Independent analytic-angle libm oracle, only an approximate bug detector."""
    bearing = math.atan2(float(delta[1]), float(delta[0]))
    heading = math.atan2(float(axis[1]), float(axis[0]))
    difference = math.atan2(math.sin(bearing-heading), math.cos(bearing-heading))
    angle = float(phi)
    cosine = (1. if abs(difference) <= angle else
              max(math.cos(difference-angle), math.cos(difference+angle)))
    return float(length) * max(0., cosine)


_NUMERIC_CASES = list(itertools.product(
    [(Q(1), Q(0)), (Q(-3, 5), Q(4, 5))],
    [(Q(-1), Q(1,5)), (Q(1,5), Q(-7,10)), (Q(4), Q(3)), (Q(-4), Q(-3))],
    [Q(0), Q(3,10), Q(6,5), Q(2)], [Q(0), Q(3,100)]))


@pytest.mark.parametrize('delta,axis,phi,uncertainty', _NUMERIC_CASES)
def test_rational_upper_dominates_independent_numeric_cone_oracle(delta, axis, phi, uncertainty):
    proof = candidate.direction_support_upper(delta, axis, phi, uncertainty, L)
    upper = Q(proof['support_upper_m'])
    assert 0 <= upper <= L
    approximate = numeric_sector_support(delta, axis, phi, L)
    # Tolerance belongs only to the independently rounded numeric oracle.
    assert float(upper) + 1e-12 >= approximate


def test_fixed_random_old_PASS_implies_new_PASS_and_new_support_is_capped():
    generator = random.Random(4301)
    old_passes = 0
    for _ in range(80):
        delta = (Q(generator.randint(-25, 25), 20), Q(generator.randint(-25, 25), 20))
        if delta == (0, 0):
            delta = (Q(1), Q(0))
        reaches = []
        for _robot in range(2):
            role = generator.choice(('D', 'N', 'X'))
            if role == 'D':
                reaches.append(legacy.disk())
                continue
            axes = (generator.choice((-3, -1, 1, 3)), generator.choice((-2, 0, 2)))
            phi = generator.choice((Q(0), Q(1,5), Q(9,10), Q(13,10), Q(2)))
            reaches.append(directed(axes, phi, role=role))
        ages = tuple(generator.choice((0, 20_000_000, 250_000_000, 500_000_000)) for _robot in range(2))
        old = legacy.pair_certificate(delta, delta, ages, *reaches, **FLAGS)
        new = pair(delta, *reaches, ages)
        if old['geometric_necessary']:
            old_passes += 1
            assert new['geometric_sufficient']
        for frame in ('map', 'raw'):
            for side, reach in zip(('left', 'right'), reaches):
                assert 0 <= Q(new[frame][side]['support_upper_m']) <= reach.longitudinal_m
        json.dumps(new, sort_keys=True, allow_nan=False)
    assert old_passes > 0


def test_original_default_function_and_source_are_unchanged():
    reference = legacy.pair_certificate
    source = Path(legacy.__file__).resolve()
    assert source == Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_geometry.py')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    expected = reference((1, 0), (1, 0), (0, 0), legacy.disk(), legacy.disk(), **FLAGS)
    candidate_result = pair((1, 0))
    assert candidate_result['profile'] == candidate.PROFILE
    assert legacy.pair_certificate is reference
    assert reference((1, 0), (1, 0), (0, 0), legacy.disk(), legacy.disk(), **FLAGS) == expected
    assert expected['schema'] == 'mr3-reach-geometric-necessary-v1'
    assert 'geometric_sufficient' not in expected
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
