#!/usr/bin/python3
"""Disabled, artificial-only exact-support equivalence and profile harness.

No ROS/World, scenes, native inputs, models or production package imports.
Default profiles the frozen baseline only, after complete equality checks.
Candidate timing requires the explicit --compare-performance flag.
"""
import argparse
import cProfile
from copy import deepcopy
from fractions import Fraction as Q
import hashlib
import io
import json
import math
from pathlib import Path
import pstats
import sys
import time
import types
import unittest


HERE = Path(__file__).resolve().parent
BASELINE_SHA = '2b45311d33fb2c5f4c05fa39d3acde7bcfc0c17ee3c2e62e0d2bdfbd4c961f34'
GEOMETRY_SHA = 'cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a'
PACKAGE = '_mr3_v47_support_cpu_private'
CANONICAL_IMPORT = 'from multi_robot_exploration.mr3_reach_geometry import ('


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def binding(path):
    path = Path(path)
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if stamp(before) != stamp(after):
        raise ValueError('source changed while binding: ' + str(path))
    return {'path': str(path.resolve()), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'stat': list(stamp(after))}


def load_modules():
    """Use only an owned private namespace; preserve real frozen geometry."""
    names = [PACKAGE, PACKAGE + '.mr3_reach_geometry', PACKAGE + '.baseline', PACKAGE + '.candidate']
    if any(name in sys.modules for name in names):
        raise ValueError('private harness module name already exists')
    package = types.ModuleType(PACKAGE)
    package.__path__ = []
    sys.modules[PACKAGE] = package
    paths = [HERE / 'geometry_reference_v1.py', HERE / 'support_baseline_v1.py',
             HERE / 'support_candidate_v1.py']
    expected = [GEOMETRY_SHA, BASELINE_SHA, None]
    modules = []
    proofs = []
    try:
        for path, suffix, wanted in zip(paths, ('mr3_reach_geometry', 'baseline', 'candidate'), expected):
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if wanted is not None and digest != wanted:
                raise ValueError('frozen reference SHA differs: ' + path.name)
            source = raw.decode()
            changes = 0
            if suffix != 'mr3_reach_geometry':
                if source.count(CANONICAL_IMPORT) != 1:
                    raise ValueError('exact geometry import marker differs')
                source = source.replace(CANONICAL_IMPORT,
                    'from ' + PACKAGE + '.mr3_reach_geometry import (', 1)
                changes = 1
            module = types.ModuleType(PACKAGE + '.' + suffix)
            module.__file__ = str(path)
            module.__package__ = PACKAGE
            sys.modules[module.__name__] = module
            exec(compile(source, str(path), 'exec'), module.__dict__)
            modules.append(module)
            proofs.append({'path': str(path), 'raw_sha256': digest,
                           'private_import_literal_replacements': changes,
                           'projected_source_sha256': hashlib.sha256(source.encode()).hexdigest()})
    except BaseException:
        for name in reversed(names):
            sys.modules.pop(name, None)
        raise
    return (*modules, proofs)


def direction_cases():
    """Fixed inputs, declared before execution; no RNG or actual sample."""
    length = Q(18, 125)
    epsilon = Q(1, 1 << 200)
    return [
        ('zero_delta', (0, 0), (1, 0), Q(0), Q(0), length),
        ('positive_dot', (1, 0), (1, 0), Q(249, 250), Q(3, 100), length),
        ('negative_nonclosing', (-1, 0), (1, 0), Q(0), Q(0), length),
        ('perpendicular_exact_zero', (0, 1), (1, 0), Q(0), Q(0), length),
        ('perpendicular_nonzero_U', (0, 1), (1, 0), Q(0), Q(1, 100), length),
        ('triangle_projected', (-Q(9, 20), -Q(9, 20)), (1, 0), Q(249, 250), Q(3, 100), length),
        ('wide_cone', (-1, 1), (1, 0), Q(2), Q(1, 100), length),
        ('tiny_lower_zero', (-epsilon, epsilon), (1, 0), Q(1), Q(0), length),
        ('exact_nonclosing_boundary', (-Q(3, 100), 0), (1, 0), Q(0), Q(3, 100), length),
        ('projected_positive_ratio', (-Q(29, 1000), 0), (1, 0), Q(0), Q(3, 100), length),
        ('ratio_capped_at_one', (-Q(1, 100), 0), (1, 0), Q(0), Q(3, 100), length),
        ('nonunit_extra_U', (Q(1, 8), 0), (-Q(3, 5), Q(4, 5)), Q(0), Q(1, 10), length),
        ('binary_float_inputs', (-.45, .45), (.1, .3), .996, .03, .144),
        ('zero_length_still_validated', (-1, 1), (1, 0), Q(1), Q(0), Q(0)),
    ]


def make_reach(g, kind, directions=()):
    if kind == 'disk':
        return g.disk()
    values = tuple(g.Direction(mapped, raw, phi) for mapped, raw, phi in directions)
    return g.transition(values) if kind == 'transition' else g.normal(values)


def pair_cases(g):
    phi = Q(249, 250)
    east = (((1, 0), (1, 0), phi),)
    west = (((-1, 0), (-1, 0), phi),)
    both = east + west
    tilted = (((Q(3, 5), Q(4, 5)), (1, 0), phi),)
    disk = make_reach(g, 'disk')
    n_east = make_reach(g, 'normal', east)
    n_west = make_reach(g, 'normal', west)
    x_east = make_reach(g, 'transition', east)
    n_both = make_reach(g, 'normal', both)
    n_tilted = make_reach(g, 'normal', tilted)
    boundary = 2*g.BODY + g.GEOMETRY_MARGIN + 4*g.R
    eps = Q(1, 1 << 100)
    # id,map_delta,raw_delta,ages,left,right,hard_gates,calibrated
    return [
        ('disk_far', (1, 0), (1, 0), (0, 0), disk, disk, True, True),
        ('disk_equal_boundary', (boundary, 0), (boundary, 0), (0, 0), disk, disk, True, True),
        ('disk_below_boundary', (boundary-eps, 0), (boundary-eps, 0), (0, 0), disk, disk, True, True),
        ('disk_above_boundary', (boundary+eps, 0), (boundary+eps, 0), (0, 0), disk, disk, True, True),
        ('zero_both_frames', (0, 0), (0, 0), (0, 0), n_east, disk, True, True),
        ('triangle_XD', (-Q(9, 20), -Q(9, 20)), (-Q(9, 20), -Q(9, 20)), (50_000_000, 50_000_000), x_east, disk, True, True),
        ('two_direction_union', (-Q(9, 20), Q(9, 20)), (-Q(9, 20), Q(9, 20)), (50_000_000, 50_000_000), n_both, n_west, True, True),
        ('raw_failure_map_pass', (2, 0), (Q(1, 4), 0), (0, 0), n_east, disk, True, True),
        ('raw_map_different_axes', (-Q(9, 20), Q(9, 20)), (-Q(9, 20), -Q(9, 20)), (20_000_001, 60_000_007), n_tilted, n_west, True, True),
        ('max_source_ages', (1, 1), (1, 1), (500_000_000, 500_000_000), n_east, n_west, True, True),
        ('hard_gate_false', (2, 0), (2, 0), (0, 0), n_east, n_west, False, True),
        ('calibration_false', (2, 0), (2, 0), (0, 0), n_east, n_west, True, False),
    ]


def run_pair(module, case):
    _, mapped, raw, ages, left, right, hard, calibrated = case
    return module.support_pair_certificate(mapped, raw, ages, left, right,
        legacy_hard_gates_passed=hard, common_world_odom_calibrated=calibrated)


def caught(call):
    try:
        return ('return', call())
    except Exception as error:
        return ('raise', type(error).__name__, str(error))


def suite(g, baseline, candidate):
    class Checks(unittest.TestCase):
        def test_all_direction_fields_and_canonical_bytes(self):
            for name, *args in direction_cases():
                with self.subTest(case=name):
                    old = baseline.direction_support_upper(*args)
                    new = candidate.direction_support_upper(*args)
                    self.assertEqual(old, new)
                    self.assertEqual(canonical(old), canonical(new))

        def test_all_pair_fields_intervals_and_exact_frame_hashes(self):
            for case in pair_cases(g):
                with self.subTest(case=case[0]):
                    old, new = run_pair(baseline, case), run_pair(candidate, case)
                    self.assertEqual(old, new)
                    self.assertEqual(canonical(old), canonical(new))
                    for frame in ('map', 'raw'):
                        self.assertEqual(old[frame]['full_exact_frame_sha256'], new[frame]['full_exact_frame_sha256'])

        def test_frame_full_dict_before_compaction(self):
            for case in pair_cases(g):
                for frame, delta in (('map', case[1]), ('raw', case[2])):
                    with self.subTest(case=case[0], frame=frame):
                        u = g.SPEED*Q(sum(case[3]), 10**9)
                        old = baseline._frame_certificate(delta, case[4], case[5], u, frame)
                        new = candidate._frame_certificate(delta, case[4], case[5], u, frame)
                        self.assertEqual(old, new)
                        self.assertEqual(canonical(old), canonical(new))

        def test_sqrt_exact_bounds_cold_warm_and_bit_key(self):
            values = (0, 1, Q(1, 4), 2, Q(2, 3), Q(1, 1 << 300), .1)
            candidate._sqrt_bounds_cached.cache_clear()
            for _ in range(2):
                for value in values:
                    with self.subTest(value=str(value)):
                        self.assertEqual(baseline.sqrt_bounds(value), candidate.sqrt_bounds(value))
                        self.assertIsInstance(candidate.sqrt_bounds(value), tuple)
            self.assertGreater(candidate._sqrt_bounds_cached.cache_info().hits, 0)
            for bits in (96, 48, 96):
                old_bits, new_bits = baseline.SQRT_BITS, candidate.SQRT_BITS
                try:
                    baseline.SQRT_BITS = candidate.SQRT_BITS = bits
                    self.assertEqual(baseline.sqrt_bounds(Q(2, 3)), candidate.sqrt_bounds(Q(2, 3)))
                finally:
                    baseline.SQRT_BITS, candidate.SQRT_BITS = old_bits, new_bits

        def test_sqrt_eviction_and_validation_before_cache_hits(self):
            candidate._sqrt_bounds_cached.cache_clear()
            for i in range(300):
                value = Q(i, 997)
                self.assertEqual(baseline.sqrt_bounds(value), candidate.sqrt_bounds(value))
            info = candidate._sqrt_bounds_cached.cache_info()
            self.assertEqual(info.maxsize, 256)
            self.assertLessEqual(info.currsize, 256)
            for value in (Q(0), Q(1), Q(1, 4)):
                candidate.sqrt_bounds(value)
            for value in (True, False, '1', None, -1, float('inf'), float('nan')):
                with self.subTest(invalid=repr(value)):
                    old = caught(lambda: baseline.sqrt_bounds(value))
                    new = caught(lambda: candidate.sqrt_bounds(value))
                    self.assertEqual(old, new)
                    self.assertEqual(old[0], 'raise')

        def test_mutable_proofs_are_fresh_and_inputs_unmodified(self):
            case = pair_cases(g)[6]
            expected = run_pair(baseline, case)
            value = run_pair(candidate, case)
            value['map']['left']['direction_modes'].append('external mutation')
            value['raw']['base_reserve_m'] = 'external mutation'
            value['input_geometry']['map_delta'][0] = 'external mutation'
            self.assertEqual(expected, run_pair(candidate, case))
            delta, axis = [Q(-9, 20), Q(9, 20)], [Q(1), Q(0)]
            before = deepcopy((delta, axis))
            value = candidate.direction_support_upper(delta, axis, Q(249, 250), Q(3, 100), Q(18, 125))
            value['axis'][0] = 'external mutation'
            self.assertEqual(before, (delta, axis))
            self.assertEqual(baseline.direction_support_upper(delta, axis, Q(249, 250), Q(3, 100), Q(18, 125)),
                             candidate.direction_support_upper(delta, axis, Q(249, 250), Q(3, 100), Q(18, 125)))

        def test_direction_invalid_inputs_and_precedence_match(self):
            valid = [(-1, 0), (1, 0), Q(1), Q(0), Q(18, 125)]
            variants = [(0, None), (0, (1,)), (0, (True, 0)), (1, (0, 0)),
                        (2, True), (2, Q(-1)), (2, Q(3)), (3, Q(-1)), (4, Q(-1)),
                        (2, float('nan'))]
            for index, value in variants:
                args = list(valid); args[index] = value
                with self.subTest(index=index, value=repr(value)):
                    old = caught(lambda: baseline.direction_support_upper(*args))
                    new = caught(lambda: candidate.direction_support_upper(*args))
                    self.assertEqual(old, new)
                    self.assertEqual(old[0], 'raise')
            self.assertEqual(caught(lambda: baseline.direction_support_upper((0, 0), (0, 0), 3, 0, 0)),
                             caught(lambda: candidate.direction_support_upper((0, 0), (0, 0), 3, 0, 0)))

        def test_pair_invalid_hard_gates_ages_and_reach_match(self):
            case = pair_cases(g)[0]
            for ages, left, hard, calibrated in (((True, 0), case[4], True, True),
                    ((-1, 0), case[4], True, True), ((500_000_001, 0), case[4], True, True),
                    ((0,), case[4], True, True), ((0, 0), object(), True, True),
                    ((0, 0), case[4], 1, True), ((0, 0), case[4], True, 1)):
                altered = (*case[:3], ages, left, case[5], hard, calibrated)
                old = caught(lambda: run_pair(baseline, altered))
                new = caught(lambda: run_pair(candidate, altered))
                self.assertEqual(old, new)
                self.assertEqual(old[0], 'raise')

        def test_large_exact_values_and_repeat_history_preserve_results(self):
            huge = Q((1 << 300)+1, (1 << 250)+3)
            args = ((-huge, huge), (Q(3, 5), Q(4, 5)), Q(249, 250), Q(3, 100), Q(18, 125))
            expected = baseline.direction_support_upper(*args)
            for case in reversed(direction_cases()):
                candidate.direction_support_upper(*case[1:])
            self.assertEqual(expected, candidate.direction_support_upper(*args))

    return unittest.defaultTestLoader.loadTestsFromTestCase(Checks)


def clear_caches(g, module):
    g._sin_cos_bounds.cache_clear()
    if hasattr(module, '_sqrt_bounds_cached'):
        module._sqrt_bounds_cached.cache_clear()


def profile_inputs(g, mode):
    cases = pair_cases(g)
    if mode == 'warm_repeated':
        return [cases[5], cases[6], cases[8]] * 4
    # Twelve exact angles, no age bucketing/RNG; within each pair the same
    # angle is naturally reused across frames/signs, as in the source API.
    result = []
    for i in range(12):
        phi = Q(6, 5)*(Q(20_000_001+17_003*i, 10**9)+Q(39, 50))
        reach = g.normal((g.Direction((1, 0), (Q(3, 5), Q(4, 5)), phi),))
        result.append(('distinct_'+str(i), (-Q(9, 20), Q(9, 20)),
            (-Q(9, 20), Q(9, 20)), (20_000_001+17_003*i, 40_000_007+19_001*i),
            reach, g.disk(), True, True))
    return result


def profile_module(g, module, label, directory):
    reports = []
    for mode in ('warm_repeated', 'cold_distinct_angles'):
        cases = profile_inputs(g, mode)
        for round_index in range(3):
            clear_caches(g, module)
            if mode == 'warm_repeated':
                for case in cases[:3]:
                    run_pair(module, case)
            digest = hashlib.sha256()
            profiler = cProfile.Profile()
            start = time.perf_counter_ns()
            profiler.enable()
            for case in cases:
                digest.update(canonical(run_pair(module, case)))
            profiler.disable()
            end = time.perf_counter_ns()
            destination = directory/(label+'_'+mode+'_round'+str(round_index)+'.pstats')
            profiler.dump_stats(str(destination))
            text = io.StringIO()
            pstats.Stats(profiler, stream=text).strip_dirs().sort_stats('cumulative').print_stats(25)
            summary = destination.with_suffix('.txt')
            with summary.open('x') as stream:
                stream.write(text.getvalue())
            reports.append({'implementation': label, 'mode': mode, 'round': round_index,
                'actual_public_pair_calls': len(cases), 'actual_profiled_wall_ns': end-start,
                'public_result_sha256': digest.hexdigest(), 'pstats': binding(destination),
                'top25_cumulative': binding(summary),
                'trig_cache': g._sin_cos_bounds.cache_info()._asdict(),
                'sqrt_cache': module._sqrt_bounds_cached.cache_info()._asdict()
                    if hasattr(module, '_sqrt_bounds_cached') else None})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--profile-directory', type=Path)
    parser.add_argument('--compare-performance', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output exists; preserve original')
    if args.profile_directory is not None and args.profile_directory.exists():
        parser.error('profile directory exists; preserve original')
    if args.compare_performance and args.profile_directory is None:
        parser.error('candidate timing requires a new profile directory')
    sources = sorted(HERE.glob('*.py')) + [HERE/'frozen_reference_manifest_v1.json']
    before = [binding(path) for path in sources]
    g, baseline, candidate, projection = load_modules()
    capture = io.StringIO()
    result = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite(g, baseline, candidate))
    profiles = []
    if result.wasSuccessful() and args.profile_directory is not None:
        args.profile_directory.mkdir(parents=True, exist_ok=False)
        # Baseline cProfile is always generated first. No source/parameters
        # are tuned after observing it in this invocation.
        profiles.extend(profile_module(g, baseline, 'baseline', args.profile_directory))
        if args.compare_performance:
            profiles.extend(profile_module(g, candidate, 'candidate', args.profile_directory))
    after = [binding(path) for path in sources]
    stable = before == after
    payload = {'schema':'mr3-v47-disabled-support-cpu-v1',
        'passed':result.wasSuccessful() and stable, 'tests_run':result.testsRun,
        'failures':[(str(case), error) for case, error in result.failures],
        'errors':[(str(case), error) for case, error in result.errors],
        'skipped':[(str(case), reason) for case, reason in result.skipped],
        'console':capture.getvalue(), 'source_before':before, 'source_after':after,
        'source_stable':stable, 'private_namespace_projection':projection,
        'direction_fixture_count':len(direction_cases()), 'pair_fixture_count':len(pair_cases(g)),
        'profiles':profiles, 'profiled_timing_is_ENV_throughput':False,
        'qualification':False, 'native_or_World_run':False, 'learning_updates':0,
        'production_enabled':False, 'raw_originals_read':False,
        'independent_reader_imported':False, 'candidate_timing_requested':args.compare_performance,
        'notes':'Artificial fixed inputs only. Full public dict/canonical bytes/frame hashes/exceptions checked; bounded exact numeric cache. No task, physical model or native qualification credit.'}
    with args.output.open('x') as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:payload[k] for k in ('passed','tests_run','source_stable','qualification')}))
    return 0 if payload['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
