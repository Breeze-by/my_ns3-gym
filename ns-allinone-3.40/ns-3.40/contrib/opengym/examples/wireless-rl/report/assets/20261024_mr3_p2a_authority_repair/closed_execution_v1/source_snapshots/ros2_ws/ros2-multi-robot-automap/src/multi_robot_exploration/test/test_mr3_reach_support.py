"""Production v2 versus the immutable, reviewed A43 mathematical candidate.

Artificial inputs only; root owns actual execution/source receipts.
"""
import ast
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from multi_robot_exploration import mr3_reach_geometry as old
from multi_robot_exploration import mr3_reach_support as production


ROOT = Path(__file__).resolve().parents[5]
A43 = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/'
              '20261022_mr3_p2a_v43_support_geometry/support_prototype_v1.py')
spec = importlib.util.spec_from_file_location('frozen_a43_reach_support', A43)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
FLAGS = {'legacy_hard_gates_passed': True, 'common_world_odom_calibrated': True}


def functions(path):
    return {node.name: node for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.FunctionDef)}


def normalized(node):
    return ast.dump(node, include_attributes=False)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def enclosed(bounds, value):
    assert Q(bounds[0]) <= Q(value) <= Q(bounds[1])


def test_frozen_reference_identity_unchanged_helpers_and_pair_validation_AST():
    assert hashlib.sha256(A43.read_bytes()).hexdigest() == '6a586b69c4649955fc06d4b94379b245c6c5602f6b51a2de1b778fe56636ccc6'
    before, after = functions(A43), functions(Path(production.__file__))
    # The V49 numerical implementation changes three helper ASTs, with full
    # dictionary/JSON/hash equivalence checked against frozen A48 below and in
    # test_mr3_reach_support_optimization.py. Unchanged helpers stay byte-AST
    # checked; neither the original A43 oracle nor its assertions are removed.
    for name in ('_str_bounds', '_reach_support'):
        assert normalized(before[name]) == normalized(after[name]), name
    # The exact pair-level validation/U/two-frame conjunction also stays the
    # A43 computation; only the final admission alias and log metadata differ.
    a = before['support_pair_certificate'].body[1:-1]
    b = after['support_pair_certificate'].body[1:-2]
    assert [normalized(node) for node in a] == [normalized(node) for node in b]
    assert hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest() == 'cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a'


def cases():
    direction = old.Direction((1, 0), (1, 0), Q(249, 250))
    opposite = old.Direction((-1, 0), (-1, 0), Q(249, 250))
    mixed = old.normal((direction, opposite))
    x = old.transition((direction,))
    base = 2 * old.BODY + old.GEOMETRY_MARGIN + 4 * old.R
    return [
        ((Q(-9, 20), Q(9, 20)), (Q(-9, 20), Q(9, 20)), (50_000_000, 50_000_000), x, old.disk()),
        ((Q(-9, 20), Q(-9, 20)), (Q(-9, 20), Q(-9, 20)), (50_000_000, 50_000_000), x, old.disk()),
        ((1, 0), (Q(1, 2), 0), (0, 0), old.disk(), old.disk()),
        ((base, 0), (base, 0), (0, 0), old.disk(), old.disk()),
        ((base-Q(1, 10**10), 0), (base, 0), (0, 0), old.disk(), old.disk()),
        ((0, 0), (0, 0), (0, 0), old.normal((direction,)), old.disk()),
        ((Q(1, 2**300), 0), (1, 0), (500_000_000, 500_000_000), x, old.disk()),
        ((Q(3, 5), 0), (Q(3, 5), 0), (0, 0), mixed, mixed),
        ((2, 0), (2, 0), (500_000_000, 500_000_000), x, old.transition((opposite,))),
        ((1, 1), (1, 1), (0, 0), old.normal(), old.transition()),
        ((1, 0), (1, 0), (0, 0), old.normal((old.Direction((-1,0),(-1,0),Q(2)),)), old.disk()),
    ]


@pytest.mark.parametrize('mapped,raw,ages,left,right', cases())
def test_complete_frame_math_and_log_summary_enclose_frozen_result(mapped, raw, ages, left, right):
    expected = frozen.support_pair_certificate(mapped, raw, ages, left, right, **FLAGS)
    actual = production.support_pair_certificate(mapped, raw, ages, left, right, **FLAGS)
    assert actual['geometric_necessary'] is actual['geometric_sufficient'] is expected['geometric_sufficient']
    assert actual['schema'] == 'mr3-reach-cone-support-separation-v2'
    assert actual['reach_geometry_rule'] == 'cone-support-v2'
    assert actual['production_enabled'] is True
    assert actual['unchanged_constants'] == expected['unchanged_constants']
    assert actual['uncertainty_m'] == expected['uncertainty_m']
    for frame in ('map', 'raw'):
        full = expected[frame]
        independent_full = production._frame_certificate(mapped if frame == 'map' else raw,
                           left, right, Q(expected['uncertainty_m']), frame)
        assert canonical(independent_full) == canonical(full)
        summary = actual[frame]
        assert summary['full_exact_frame_sha256'] == hashlib.sha256(canonical(full)).hexdigest()
        assert summary['separation_sufficient_under_declared_sets'] is full['separation_sufficient_under_declared_sets']
        assert summary['log_intervals_only'] is True
        enclosed(summary['distance_squared_bounds_m2'], full['distance_squared'])
        enclosed(summary['required_centre_distance_upper_bounds_m'], full['required_centre_distance_upper_m'])
        enclosed(summary['squared_slack_bounds_m2'], full['squared_slack_m2'])
        assert Q(summary['distance_norm_bounds_m'][0]) <= Q(full['distance_norm_bounds'][0])
        assert Q(summary['distance_norm_bounds_m'][1]) >= Q(full['distance_norm_bounds'][1])
        for side in ('left', 'right'):
            enclosed(summary[side]['support_upper_bounds_m'], full[side]['support_upper_m'])
            assert summary[side]['direction_modes'] == [row['mode'] for row in full[side]['directions']]
        assert 'sin_bounds' not in json.dumps(summary)
    # Artificial unit-scale fixture size only, not a native throughput claim.
    assert len(canonical(actual)) < 12_000


@pytest.mark.parametrize('value', [Q(-3, 7), Q(0), Q(1, 1<<200), Q(2, 3), Q(123456)])
def test_log_interval_is_outward_even_for_negative_values(value):
    bounds = production.log_interval(value)
    enclosed(bounds, value)
    assert Q(bounds[1])-Q(bounds[0]) <= Q(1, 1<<production.LOG_INTERVAL_BITS)


def test_corrupt_display_intervals_do_not_change_exact_admission_or_proof_digest(monkeypatch):
    args = cases()[0]
    before = production.support_pair_certificate(*args, **FLAGS)
    monkeypatch.setattr(production, 'log_interval', lambda value: ['-999', '-998'])
    after = production.support_pair_certificate(*args, **FLAGS)
    assert after['geometric_necessary'] is before['geometric_necessary'] is True
    for frame in ('map', 'raw'):
        assert after[frame]['full_exact_frame_sha256'] == before[frame]['full_exact_frame_sha256']
        assert after[frame]['required_centre_distance_upper_bounds_m'] == ['-999', '-998']


def test_source_and_hardgate_rejections_are_not_removed_by_production_wrapper():
    for age in (-1, 500_000_001, True, 1.):
        with pytest.raises(ValueError):
            production.support_pair_certificate((1,0),(1,0),(age,0),old.disk(),old.disk(),**FLAGS)
    for field in FLAGS:
        flags = dict(FLAGS, **{field: False})
        assert not production.support_pair_certificate((1,0),(1,0),(0,0),old.disk(),old.disk(),**flags)['geometric_necessary']
