"""Canonical V49 support versus exact frozen A48 production bytes; no World."""
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path

from multi_robot_exploration import mr3_reach_geometry as geometry
from multi_robot_exploration import mr3_reach_support as current


ROOT = Path(__file__).resolve().parents[5]
A48 = ROOT/('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
            'report/assets/20261022_mr3_p2a_v48_support_cpu/production')


def load(name, filename, expected):
    path = A48/filename
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline = load('_v49_frozen_production_support', 'support_baseline_v1.py',
                '2b45311d33fb2c5f4c05fa39d3acde7bcfc0c17ee3c2e62e0d2bdfbd4c961f34')
fixtures = load('_v49_frozen_production_support_fixtures', 'harness_v1.py',
                '17b28a8be12f6b791051d11b6bf376ff6ebcdca0f144d12e74ad9b741f449610')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def test_canonical_sources_are_exact_admitted_A48_candidate_and_original_geometry():
    assert Path(current.__file__).read_bytes() == (A48/'support_candidate_v1.py').read_bytes()
    assert hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest() == \
        'dc32cb48831dc333a9a4674ee83cce940e35a655a1b1fb9c5e6ba9b10be13966'
    assert hashlib.sha256(Path(geometry.__file__).read_bytes()).hexdigest() == \
        'cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a'
    assert current.SQRT_BITS == 96 and current.LOG_INTERVAL_BITS == 48
    assert current.PROFILE == baseline.PROFILE
    assert current.REACH_GEOMETRY_RULE == baseline.REACH_GEOMETRY_RULE


def test_complete_public_pair_direction_frame_JSON_and_digest_equal_frozen_baseline():
    for _, *arguments in fixtures.direction_cases():
        assert canonical(current.direction_support_upper(*arguments)) == \
               canonical(baseline.direction_support_upper(*arguments))
    for case in fixtures.pair_cases(geometry):
        expected = fixtures.run_pair(baseline, case)
        actual = fixtures.run_pair(current, case)
        assert canonical(actual) == canonical(expected), case[0]
        uncertainty = geometry.SPEED*Q(sum(case[3]), 10**9)
        for frame, delta in (('map', case[1]), ('raw', case[2])):
            full = current._frame_certificate(delta, case[4], case[5], uncertainty, frame)
            old = baseline._frame_certificate(delta, case[4], case[5], uncertainty, frame)
            assert canonical(full) == canonical(old)
            assert actual[frame]['full_exact_frame_sha256'] == hashlib.sha256(canonical(old)).hexdigest()


def test_warm_cache_does_not_bypass_numeric_validation_and_stays_bounded():
    current._sqrt_bounds_cached.cache_clear()
    for value in (Q(0), Q(1), Q(1, 4)):
        assert current.sqrt_bounds(value) == baseline.sqrt_bounds(value)
    for value in (True, False, '1', None, -1, float('nan'), float('inf')):
        actual = fixtures.caught(lambda: current.sqrt_bounds(value))
        expected = fixtures.caught(lambda: baseline.sqrt_bounds(value))
        assert actual == expected and actual[0] == 'raise'
    for i in range(300):
        assert current.sqrt_bounds(Q(i, 997)) == baseline.sqrt_bounds(Q(i, 997))
    info = current._sqrt_bounds_cached.cache_info()
    assert info.maxsize == 256 and info.currsize <= 256
    for args in (((0, 0), (0, 0), 3, 0, 0), ((1, 0), (True, 0), 0, 0, 1),
                 ((1, 0), (1, 0), True, 0, 1), ((1, 0), (1, 0), 0, -1, 1)):
        actual = fixtures.caught(lambda: current.direction_support_upper(*args))
        expected = fixtures.caught(lambda: baseline.direction_support_upper(*args))
        assert actual == expected and actual[0] == 'raise'


def test_cached_numeric_values_never_share_mutable_public_proofs():
    case = fixtures.pair_cases(geometry)[6]
    expected = fixtures.run_pair(baseline, case)
    first = fixtures.run_pair(current, case)
    first['map']['left']['direction_modes'].append('external mutation')
    first['input_geometry']['raw_delta'][0] = 'external mutation'
    first['raw']['base_reserve_m'] = 'external mutation'
    assert canonical(fixtures.run_pair(current, case)) == canonical(expected)
    pair = current.sqrt_bounds(Q(2, 3))
    assert type(pair) is tuple and all(type(value) is Q for value in pair)
