"""Finite artificial CPU checks/timing/profile for the disabled reader candidate."""
import argparse
import cProfile
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import time
import unittest

HERE = Path(__file__).resolve().parent


def dump(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profile-dir', type=Path)
    parser.add_argument('--export-numeric-inputs', type=Path)
    args = parser.parse_args(argv)
    export = args.export_numeric_inputs
    if export is not None:
        if args.output is not None or args.profile_dir is not None or export.exists():
            parser.error('input export is an exclusive separate role')
    elif args.output is None or args.profile_dir is None or args.output.exists() or args.profile_dir.exists():
        parser.error('new output and new profile-dir are required')
    paths = sorted(HERE.glob('*.py'))
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    spec = importlib.util.spec_from_file_location('_v47_reader_tests', HERE / 'test_reader_candidate_v1.py')
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    if export is not None:
        def ratio(value):
            value = tests.Q(value)
            return [value.numerator, value.denominator]
        rows = [{'id': name, 'bearing': [ratio(x) for x in bearing],
                 'axis': [ratio(x) for x in axis], 'angle': ratio(angle),
                 'uncertainty': ratio(uncertainty), 'length': ratio(length)}
                for name, bearing, axis, angle, uncertainty, length in tests.direction_cases()]
        dump(export, {'schema': 'mr3-v47-artificial-direction-inputs-v1', 'sources': before,
                      'cases': rows, 'artificial_only': True, 'scientific_credit': False})
        return 0
    args.profile_dir.mkdir(parents=True, exist_ok=False)
    console = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.ReaderCandidateTests)
    checked = unittest.TextTestRunner(stream=console, verbosity=2).run(suite)
    records = []
    if checked.wasSuccessful():
        angles = tuple(tests.Q(index+1, 257) for index in range(64))
        norms = tuple(tests.Q(index+1, 263) for index in range(64))
        directions = tests.direction_cases()
        for label, module in (('baseline', tests.baseline), ('candidate', tests.candidate)):
            def scenario(name):
                tests.clear(module)
                if name == 'cold_trig':
                    return lambda: [module.trig_enclosure(value) for value in angles], len(angles)
                if name == 'cold_sqrt':
                    return lambda: [module.sqrt_interval(value) for value in norms], len(norms)
                if name == 'warm_sqrt':
                    for value in norms:
                        module.sqrt_interval(value)
                    return lambda: [module.sqrt_interval(value) for _ in range(4) for value in norms], 4*len(norms)
                for _, *arguments in directions:
                    module.direction_support_upper(*arguments)
                return (lambda: [module.direction_support_upper(*arguments)
                                 for _ in range(2) for _, *arguments in directions], 2*len(directions))
            for name in ('cold_trig', 'cold_sqrt', 'warm_sqrt', 'warm_direction'):
                call, calls = scenario(name)
                started = time.perf_counter_ns(); numeric = call(); ended = time.perf_counter_ns()
                numeric_sha = hashlib.sha256(tests.canonical_bytes(numeric)).hexdigest()
                cache = {'trig': module.trig_enclosure.cache_info()._asdict()}
                if hasattr(module, '_sqrt_interval_q'):
                    cache['sqrt'] = module._sqrt_interval_q.cache_info()._asdict()
                call, _ = scenario(name)
                output = args.profile_dir / (label + '_' + name + '.cprof')
                with output.open('xb'):
                    pass  # Exclusively claim before cProfile writes its own file.
                profile = cProfile.Profile()
                profile.enable()
                try:
                    profiled_numeric = call()
                finally:
                    profile.disable(); profile.dump_stats(str(output))
                if tests.canonical_bytes(profiled_numeric) != tests.canonical_bytes(numeric):
                    raise AssertionError('profile changed artificial numeric outputs')
                records.append({'model': label, 'scenario': name, 'calls': calls,
                    'unprofiled_wall_ns': ended-started, 'numeric_canonical_sha256': numeric_sha,
                    'cache_after_timing': cache, 'profile': str(output),
                    'profile_sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
        for name in ('cold_trig', 'cold_sqrt', 'warm_sqrt', 'warm_direction'):
            values = [row['numeric_canonical_sha256'] for row in records if row['scenario'] == name]
            if len(set(values)) != 1:
                raise AssertionError('benchmark numeric outputs differ: ' + name)
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    if before != after:
        raise AssertionError('candidate CPU sources changed during actual harness')
    value = {'schema': 'mr3-v47-independent-reader-artificial-cpu-v1',
        'candidate_disabled': True, 'baseline_sha256': tests.BASELINE_SHA256,
        'source_before': before, 'source_after': after, 'sources_stable': True,
        'tests': {'run': checked.testsRun, 'errors': len(checked.errors),
                  'failures': len(checked.failures), 'console': console.getvalue()},
        'passed': checked.wasSuccessful(), 'benchmarks': records,
        'scope': 'Fixed local math-only CPU calls; timings are not World/native/PPO throughput.',
        'pair_checks': 'Unchanged caller gates; artificial declared-set composition only, no source-admission claim.',
        'known_legacy_behavior': 'Public trig cache input-alias behavior is preserved. Any repair requires separate version/declaration/validation.',
        'scientific_credit': False, 'native_qualification': False, 'fees_recomputed': False}
    dump(args.output, value)
    print(json.dumps({'passed': value['passed'], 'tests': checked.testsRun,
                      'output': str(args.output), 'profile_files': len(records)}), flush=True)
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
