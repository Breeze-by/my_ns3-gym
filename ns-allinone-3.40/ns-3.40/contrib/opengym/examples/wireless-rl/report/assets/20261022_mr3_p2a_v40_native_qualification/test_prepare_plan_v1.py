"""Artificial V40 declaration/receipt rejection checks; never launch native."""

import copy
import importlib

import pytest


preparing = importlib.import_module(
    'report.assets.20261022_mr3_p2a_v40_native_qualification.prepare_plan_v1')


def original_policy():
    return preparing.decode((preparing.PRIOR / 'predeclared_plan_v1.json').read_bytes())


@pytest.mark.parametrize('name', ['minimum', 'pilot', 'validation'])
def test_whole_policy_registry_has_exact_stage_contract_and_original_configuration(name):
    original = original_policy()
    before = copy.deepcopy(original['policy_stages'])
    registry = preparing.policy_registry(original)
    plan = {'policy_stages': registry, 'learner_python': registry[name]['argv'][0],
        'seed_rule': preparing.SEED_RULE, 'start_graph_rule': preparing.START_RULE}
    preparing.stage_spec(plan, preparing.PLAN, preparing.QUALIFICATION, name)
    assert original['policy_stages'] == before
    argv = registry[name]['argv']
    old = before[name]['argv']
    for flag in ('--mode', '--workers', '--schedule', '--decisions', '--episode-steps',
                 '--wall-seconds', '--seed', '--batch-size', '--epochs', '--device'):
        assert preparing.preparation.argument(argv, flag) == preparing.preparation.argument(old, flag)
    assert registry[name]['wall_seconds'] == before[name]['wall_seconds']
    assert registry[name]['tail_reserve_seconds'] == '500'
    assert registry[name]['external_finalize_reserve_seconds'] == ('0' if name == 'minimum' else '300')
    assert '--seed-rule' in argv and '--start-graph-rule' in argv
    assert not any('reach_v19' in item for item in argv)
    if name == 'validation':
        assert preparing.preparation.argument(argv, '--checkpoint') == str(
            preparing.POLICY_ROOT / 'mr3_p2a_reach_v40_pilot/final.zip')


def test_policy_registry_rejects_an_omitted_policy_stage_before_modifying_original():
    original = original_policy()
    del original['policy_stages']['pilot']
    before = copy.deepcopy(original)
    with pytest.raises(ValueError, match='incomplete'):
        preparing.policy_registry(original)
    assert original == before


@pytest.mark.parametrize('argv', [[], ['--mode', 'train', '--mode', 'evaluate'], ['--mode']])
def test_argument_replacement_rejects_absent_repeated_and_missing_value(argv):
    before = argv.copy()
    with pytest.raises(ValueError):
        preparing.replace_argument(argv, '--mode', 'train')
    assert argv == before


def valid_wait():
    return {'schema': 'mr3-reach-outer-actual-wait-v1', 'scope': 'cpu', 'safety_contract': 'mr3-reach-v1',
        'actual_waited': True, 'actual_returncode': 0, 'errors': [], 'source_unchanged': True, 'passed': True,
        'started_monotonic_ns': 1000000001, 'ended_monotonic_ns': 1000000102,
        'actual_child_wait_seconds': '0.000000101',
        'coordinator_identity': {'pid': 100, 'start_ticks': 1000},
        'child_identity': {'pid': 101, 'start_ticks': 1001, 'parent': 100},
        'actual_argv': ['/usr/bin/python3', '-m', 'synthetic_fixture'],
        'source_before': [{'path': '/synthetic/only.py', 'sha256': 'a' * 64, 'bytes': 1}],
        'source_after': [{'path': '/synthetic/only.py', 'sha256': 'a' * 64, 'bytes': 1}]}


def test_actual_wait_nanosecond_math_and_typed_parent_identity_pass():
    preparing.verify_wait(valid_wait())


@pytest.mark.parametrize('change', [
    {'scope': 'engineering'}, {'actual_returncode': True}, {'actual_returncode': 1},
    {'actual_waited': False}, {'source_unchanged': False}, {'source_after': []},
    {'actual_child_wait_seconds': '0.000000100'}, {'errors': ['failure']},
    {'child_identity': {'pid': 101, 'start_ticks': 1001, 'parent': 99}},
])
def test_cpu_preparation_rejects_failed_fabricated_or_source_changed_receipt(change):
    value = valid_wait()
    value.update(change)
    with pytest.raises(ValueError):
        preparing.verify_wait(value)


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_duplicate_and_nonfinite_json_cannot_supply_preparation_authority(raw):
    with pytest.raises(ValueError):
        preparing.decode(raw)
