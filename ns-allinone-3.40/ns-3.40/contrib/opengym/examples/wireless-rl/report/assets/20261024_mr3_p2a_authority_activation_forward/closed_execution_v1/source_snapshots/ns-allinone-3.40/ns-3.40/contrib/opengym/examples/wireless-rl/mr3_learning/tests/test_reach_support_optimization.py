"""Canonical independent reader exact optimization; no production math import."""
import ast
from fractions import Fraction as Q
import hashlib
import importlib.util
from pathlib import Path
import unittest

from mr3_learning import reach_support_replay as current


A48 = Path(__file__).resolve().parents[2]/'report/assets/20261022_mr3_p2a_v48_support_cpu/reader'
BASELINE_SHA = '555327657319000a313acba44fc35d548743ab04f0689d9ea1aa3b8c2e3864ed'
CANDIDATE_SHA = '47ea22da40bde3a794565d5d11bb06fd6fc591e3000e0daa40ec3f377bee10b2'
path = A48/'reader_baseline_v1.py'
assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE_SHA
spec = importlib.util.spec_from_file_location('_v49_frozen_independent_support', path)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def outcome(function, value):
    try:
        return ('return', function(value))
    except Exception as error:
        return ('raise', type(error).__name__, str(error))


class CanonicalSupportOptimizationTests(unittest.TestCase):
    def test_exact_admitted_candidate_and_unchanged_direction_validation_AST(self):
        raw = Path(current.__file__).read_bytes()
        self.assertEqual(raw, (A48/'reader_candidate_v1.py').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CANDIDATE_SHA)
        self.assertEqual(current.SQRT_BITS, 96)
        old = {n.name:n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)}
        new = {n.name:n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef)}
        for name in ('_q', '_point', 'direction_support_upper'):
            self.assertEqual(ast.dump(old[name], include_attributes=False),
                             ast.dump(new[name], include_attributes=False))
        imports = {n.module for n in ast.walk(ast.parse(raw)) if isinstance(n, ast.ImportFrom)}
        imports.update(alias.name for n in ast.walk(ast.parse(raw)) if isinstance(n, ast.Import) for alias in n.names)
        self.assertEqual(imports, {'fractions', 'functools', 'math'})

    def test_all_64_contract_age_angles_exact_trig_and_direction_equal_baseline(self):
        for i in range(64):
            age = i*500_000_000//63
            phi = Q(6, 5)*(Q(39, 50)+Q(age, 10**9))
            with self.subTest(age_ns=age):
                self.assertEqual(current.trig_enclosure(phi), baseline.trig_enclosure(phi))
                for axis in ((Q(3, 5), Q(4, 5)), (.6, .8)):
                    arguments = ((-Q(9, 20), -Q(9, 20)), axis, phi,
                                 Q(3, 10)*Q(2*age, 10**9), Q(18, 125))
                    self.assertEqual(current.direction_support_upper(*arguments),
                                     baseline.direction_support_upper(*arguments))

    def test_exact_sqrt_cache_warm_validation_eviction_and_immutable_results(self):
        current._sqrt_interval_q.cache_clear()
        for value in (Q(0), Q(1), Q(1, 4), Q(2), Q(1, 1 << 400), Q((1 << 300)+1)):
            self.assertEqual(current.sqrt_interval(value), baseline.sqrt_interval(value))
            self.assertEqual(current.sqrt_interval(value), baseline.sqrt_interval(value))
            result = current.sqrt_interval(value)
            self.assertIs(type(result), tuple)
            self.assertTrue(all(type(x) is Q for x in result))
        for value in (True, False, '1', None, -1, float('nan'), float('inf')):
            self.assertEqual(outcome(current.sqrt_interval, value), outcome(baseline.sqrt_interval, value))
            self.assertEqual(outcome(current.sqrt_interval, value)[0], 'raise')
        for i in range(300):
            self.assertEqual(current.sqrt_interval(Q(i, 997)), baseline.sqrt_interval(Q(i, 997)))
        info = current._sqrt_interval_q.cache_info()
        self.assertEqual(info.maxsize, 256)
        self.assertLessEqual(info.currsize, 256)

    def test_trig_endpoints_bad_inputs_and_existing_cache_alias_behavior_preserved(self):
        for module in (baseline, current):
            module.trig_enclosure.cache_clear()
        for value in (Q(0), Q(2), 0., 2., Q(1, 1 << 300)):
            self.assertEqual(current.trig_enclosure(value), baseline.trig_enclosure(value))
        for value in (-1, 3, float('nan'), float('inf'), None, '1'):
            self.assertEqual(outcome(current.trig_enclosure, value), outcome(baseline.trig_enclosure, value))
        # Preserve the historical public-cache alias behavior, rather than
        # silently changing its validation semantics during optimization.
        for module in (baseline, current):
            module.trig_enclosure.cache_clear()
            module.trig_enclosure(Q(1))
        self.assertEqual(outcome(current.trig_enclosure, True), outcome(baseline.trig_enclosure, True))


if __name__ == '__main__':
    unittest.main()
