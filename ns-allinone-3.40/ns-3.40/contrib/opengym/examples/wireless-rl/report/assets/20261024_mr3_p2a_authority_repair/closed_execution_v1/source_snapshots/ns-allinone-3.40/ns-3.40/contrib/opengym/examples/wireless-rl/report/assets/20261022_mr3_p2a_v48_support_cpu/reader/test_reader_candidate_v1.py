"""Artificial exact-reader equivalence only; no production imports or native data."""
import ast
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import unittest


HERE = Path(__file__).resolve().parent
BASELINE_SHA256 = '555327657319000a313acba44fc35d548743ab04f0689d9ea1aa3b8c2e3864ed'
L, R = Q(18, 125), Q(39, 5000)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline = load('_v47_frozen_independent_reader', HERE / 'reader_baseline_v1.py')
candidate = load('_v47_candidate_independent_reader', HERE / 'reader_candidate_v1.py')


def clear(module):
    module.trig_enclosure.cache_clear()
    if hasattr(module, '_sqrt_interval_q'):
        module._sqrt_interval_q.cache_clear()


def outcome(function, *args):
    try:
        return ('return', function(*args))
    except Exception as error:
        return ('raise', type(error).__name__, str(error))


def canonical(value):
    if type(value) is Q:
        # Full exact integer values, including subnormal-angle denominators,
        # without depending on the interpreter's decimal-digit safety limit.
        return {'numerator_hex': format(value.numerator, 'x'),
                'denominator_hex': format(value.denominator, 'x')}
    if isinstance(value, (tuple, list)):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    return value


def canonical_bytes(value):
    return json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def direction_cases():
    fixed = [
        ('zero_delta', (0, 0), (-1, 1), Q(1), Q(3, 100), L),
        ('tangent_zero', (1, 0), (0, 1), Q(0), Q(0), L),
        ('closing', (1, 0), (1, 0), Q(1, 5), Q(0), L),
        ('wide_cone', (1, 0), (-1, 0), Q(2), Q(0), L),
        ('nonclosing', (1, 0), (-1, 0), Q(0), Q(1, 10), L),
        ('extra_U_units', (Q(1, 8), 0), (Q(-3, 5), Q(4, 5)), Q(0), Q(1, 10), L),
        ('cap_one', (Q(1, 1000), 0), (-1, 1), Q(1), Q(3, 10), L),
        ('tiny_delta', (Q(1, 2**300), 0), (-1, 1), Q(1), Q(1, 100), L),
        ('tiny_axis', (1, 0), (-Q(1, 2**300), Q(1, 2**300)), Q(1), Q(1, 100), L),
        ('zero_length', (1, 0), (-1, 1), Q(1), Q(1, 100), Q(0)),
        ('axis_scale_small', (Q(1, 8), 0), (Q(-3, 5120), Q(4, 5120)), Q(0), Q(1, 10), L),
        ('axis_scale_large', (Q(1, 8), 0), (-3*2**100, 4*2**100), Q(0), Q(1, 10), L),
    ]
    generator = random.Random(20261022)
    for index in range(64):
        bearing = tuple(Q(generator.randint(-100, 100), 37) for _ in range(2))
        axis = tuple(Q(generator.randint(-10, 10), 7) for _ in range(2))
        if axis == (0, 0):
            axis = (Q(1), Q(0))
        fixed.append(('fixed_random_' + str(index), bearing, axis,
            Q(generator.randint(0, 200), 100), Q(generator.randint(0, 30), 100), L))
    return fixed


def pair_measurements(module, raw_bearing, map_bearing, left, right):
    """Artificial declared-set composition, not state/source admission.

    Mirrors the unchanged reader's two-frame AND, per-end sign union max,
    .52 base, original U and 2R/4R reserves. No state validators are bypassed
    in production because this helper is never wired into any auditor.
    """
    age_left, role_left, signs_left, axes_left = left
    age_right, role_right, signs_right, axes_right = right
    uncertainty = Q(3, 10) * Q(age_left + age_right, 10**9)
    frames = []
    for frame, bearing in enumerate((raw_bearing, map_bearing)):
        margin = Q(13, 25) + uncertainty
        supports = []
        for age, role, signs, axes, toward in (
                (*left, bearing), (*right, tuple(-x for x in bearing))):
            margin += 4*R if role == 'X' else 2*R
            contribution = Q(0)
            if role not in ('HOLD', 'D'):
                phi = Q(6, 5) * (Q(age, 10**9) + Q(39, 50))
                contribution = max(module.direction_support_upper(toward,
                    tuple(sign*x for x in axes[frame]), phi, uncertainty, L) for sign in signs)
            supports.append(contribution)
            margin += contribution
        distance2 = sum(x*x for x in bearing)
        frames.append({'support': supports, 'required': margin, 'distance2': distance2,
                       'slack2': distance2-margin*margin, 'admitted': distance2 >= margin*margin})
    return {'frames': frames, 'both_frames': all(frame['admitted'] for frame in frames)}


class ReaderCandidateTests(unittest.TestCase):
    def setUp(self):
        clear(baseline); clear(candidate)

    def equal_result(self, name, *args):
        old = outcome(getattr(baseline, name), *args)
        new = outcome(getattr(candidate, name), *args)
        self.assertEqual(old, new)
        self.assertEqual(canonical_bytes(old), canonical_bytes(new))
        return new

    def test_actual_frozen_source_and_unchanged_direction_validator_AST(self):
        old_path = HERE / 'reader_baseline_v1.py'
        self.assertEqual(hashlib.sha256(old_path.read_bytes()).hexdigest(), BASELINE_SHA256)
        trees = [ast.parse(path.read_text()) for path in (old_path, HERE / 'reader_candidate_v1.py')]
        for name in ('_q', '_point', 'direction_support_upper'):
            values = [next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                           and node.name == name) for tree in trees]
            self.assertEqual(ast.dump(values[0]), ast.dump(values[1]))
        for tree in trees:
            imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            imports += [item.name for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names]
            self.assertEqual(set(imports), {'fractions', 'functools', 'math'})
        self.assertEqual(baseline.SQRT_BITS, 96)
        self.assertEqual(candidate.SQRT_BITS, 96)

    def test_exact_sqrt_perfect_nonperfect_tiny_and_large(self):
        for value in (Q(0), Q(1, 64), Q(2), Q(3, 7), Q(1, 2**400), Q(10**40+1),
                      Q(1, 2**5000), Q(2**192-1, 2**192), Q(2**192+1, 2**192)):
            with self.subTest(value=str(value)):
                _, (lo, hi) = self.equal_result('sqrt_interval', value)
                self.assertLessEqual(lo*lo, value); self.assertGreaterEqual(hi*hi, value)
                self.assertLessEqual(hi-lo, Q(1, 2**96))

    def test_trig_all_original_Fractions_match_at_fixed_boundaries_and_binary_inputs(self):
        values = [0, 1, 2, Q(1, 2**400), Q(1, 10), Q(249, 250), Q(192, 125),
                  math.nextafter(0., 1.), math.nextafter(2., 0.), math.pi/2]
        values += [Q(index, 64) for index in range(129)]
        generator = random.Random(20261023)
        for _ in range(48):
            denominator = generator.randint(1, 10**9)
            values.append(Q(generator.randint(0, 2*denominator), denominator))
        for value in values:
            with self.subTest(value=str(value)):
                self.equal_result('trig_enclosure', value)

    def test_public_direction_all_return_values_and_JSON_equal(self):
        for name, *arguments in direction_cases():
            with self.subTest(case=name):
                self.equal_result('direction_support_upper', *arguments)
        self.assertEqual(candidate.direction_support_upper((Q(1, 8), 0),
            (Q(-3, 5), Q(4, 5)), 0, Q(1, 10), L), L/5)

    def test_cold_bad_inputs_same_exception_type_and_message(self):
        class IntegerSubclass(int):
            pass
        for value in (True, False, None, math.inf, math.nan, '1/2', [], {}, 1j, IntegerSubclass(1)):
            for name in ('sqrt_interval', 'trig_enclosure'):
                clear(baseline); clear(candidate)
                with self.subTest(name=name, value=repr(value)):
                    self.equal_result(name, value)
        for arguments in (((1, 0), (0, 0), 0, 0, L),
                ((True, 0), (-1, 1), 0, 0, L), ((1, 0), (-1, 1), -1, 0, L),
                ((1, 0), (-1, 1), 3, 0, L), ((1, 0), (-1, 1), 0, -1, L),
                ((1, 0), (-1, 1), 0, 0, -1), ([1], (-1, 1), 0, 0, L)):
            self.equal_result('direction_support_upper', *arguments)

    def test_existing_public_trig_cache_alias_semantics_are_preserved_not_fixed(self):
        for warm in (Q(0), Q(1), 1, 1., Q(2)):
            for later in (True, False, 1., Q(1), 1):
                clear(baseline); clear(candidate)
                self.equal_result('trig_enclosure', warm)
                self.equal_result('trig_enclosure', later)
        # Public sqrt validates before its new private cache, including hits.
        candidate.sqrt_interval(Q(1))
        for value in (True, False):
            self.assertEqual(outcome(baseline.sqrt_interval, value), outcome(candidate.sqrt_interval, value))

    def test_both_bounded_caches_evict_without_changing_exact_values(self):
        first = None
        for index in range(257):
            value = Q(index+1, 258)
            self.equal_result('trig_enclosure', value)
            self.equal_result('sqrt_interval', value)
            if index == 0:
                first = candidate.sqrt_interval(value)
        for module in (baseline, candidate):
            info = module.trig_enclosure.cache_info()
            self.assertEqual((info.maxsize, info.currsize, info.misses), (256, 256, 257))
        info = candidate._sqrt_interval_q.cache_info()
        self.assertEqual((info.maxsize, info.currsize), (256, 256))
        misses = info.misses
        self.assertEqual(candidate.sqrt_interval(Q(1, 258)), first)
        self.assertEqual(candidate._sqrt_interval_q.cache_info().misses, misses+1)
        self.equal_result('trig_enclosure', Q(1, 258))
        for module in (baseline, candidate):
            self.assertEqual(module.trig_enclosure.cache_info().misses, 258)

    def test_cached_values_are_only_immutable_Fractions_and_not_mutable_proofs(self):
        value = candidate.sqrt_interval(Q(2))
        self.assertIs(type(value), tuple)
        self.assertTrue(all(type(item) is Q for item in value))
        with self.assertRaises(TypeError):
            value[0] = Q(0)
        external = {'bounds': list(value)}
        external['bounds'][0] = Q(99)
        self.assertEqual(candidate.sqrt_interval(Q(2)), baseline.sqrt_interval(Q(2)))

    def test_artificial_both_frames_union_roles_age_and_threshold_full_dict_equal(self):
        axis = ((Q(1), Q(0)), (Q(1), Q(0)))
        roles = [(0, 'HOLD', (), axis), (0, 'D', (), axis),
                 (0, 'X', (1,), axis), (500_000_000, 'N', (1, -1), axis)]
        boundary = Q(689, 1250)
        bearings = [((boundary+delta, Q(0)), (boundary+delta, Q(0)))
                    for delta in (-Q(1, 2**100), Q(0), Q(1, 2**100))]
        bearings += [((Q(-9, 20), Q(9, 20)), (Q(9, 20), Q(9, 20))),
                     ((Q(0), Q(0)), (Q(1), Q(0)))]
        for left in roles:
            for right in roles:
                for raw, mapped in bearings:
                    old = pair_measurements(baseline, raw, mapped, left, right)
                    new = pair_measurements(candidate, raw, mapped, left, right)
                    self.assertEqual(old, new)
                    self.assertEqual(canonical_bytes(old), canonical_bytes(new))


if __name__ == '__main__':
    unittest.main()
