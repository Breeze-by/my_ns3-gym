"""Artificial V41 declaration/receipt rejection checks; never launch native."""

import copy
import importlib
import json

import pytest


preparing = importlib.import_module(
    'report.assets.20261022_mr3_p2a_v41_packing_gate.prepare_plan_v1')


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
    assert not any('reach_v40' in item for item in argv)
    if name == 'validation':
        assert preparing.preparation.argument(argv, '--checkpoint') == str(
            preparing.POLICY_ROOT / 'mr3_p2a_reach_v41_pilot/final.zip')


def authorization_fixture():
    authorization = {'schema': 'mr3-p2a-autonomous-continuation-authorization-v1',
        'status': 'AUTHORIZED_BY_USER_CONTINUATION',
        'user_exact_text': '你一直继续执行就好了，直到把P2A完成，不需要问我是否批准',
        'engineering_current_block_ceiling_seconds': '75000',
        'engineering_used_at_entry_seconds': '48282.3965638106018',
        'engineering_remaining_at_entry_seconds': '26717.6034361893982',
        'acceptance_gates_unchanged': True, 'old_failures_preserved': True,
        'p2b_gateway_authorized': False}
    budget = {'schema': 'mr3-p2a-reach-engineering-budget-acceptance-v1', 'authorization': {},
        'engineering_ceiling_wall_seconds': '75000', 'opening_used_wall_seconds': '48282.3965638106018',
        'opening_remaining_wall_seconds': '26717.6034361893982',
        'reservations': {'total': '20900', 'qualification_minimum_external_total': '20100',
                         'preparation_and_bounded_forensic_separate_ceiling': '800'},
        'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
        'final_only_schedule': ['open:401', 'open:402', 'open:403']}

    class ArtificialInputs:
        # Only bookkeeping records are supplied, never actual authority or
        # source admission. Production Inputs.bound retains the real SHA gate.
        def read(self, path):
            return json.dumps(authorization if path.name == 'authorization_v1.json' else budget).encode()

        def bound(self, spec, expected):
            assert expected == preparing.A / 'authorization_v1.json'

    return authorization, budget, ArtificialInputs()


def test_new_entry_accounts_for_v40_failure_and_the_full_20900_reservation():
    _, _, inputs = authorization_fixture()
    preparing.verify_authorization(inputs, preparing.Decimal('26717.6034361893982'))
    with pytest.raises(ValueError, match='must fund'):
        preparing.verify_authorization(inputs, preparing.Decimal('20100'))


@pytest.mark.parametrize('fault', ['old_opening', 'omit_preparation_reserve', 'increase_pilot'])
def test_old_entry_or_incomplete_new_reservation_cannot_admit_v41(fault):
    authorization, budget, inputs = authorization_fixture()
    if fault == 'old_opening':
        authorization['engineering_used_at_entry_seconds'] = '48259.9538193466018'
    elif fault == 'omit_preparation_reserve':
        budget['reservations']['total'] = '20100'
    else:
        budget['pilot_remaining_decisions'] = 1871
    with pytest.raises(ValueError):
        preparing.verify_authorization(inputs, preparing.OPENING_REMAINING)


@pytest.mark.parametrize('index', [
    {'schema': 'mr3-p2a-v40-cpu-validation-index-v1', 'entries': []},
    {'schema': 'mr3-p2a-v41-cpu-validation-index-v1',
     'entries': [{'id': 'v40_geometry'}, {'id': 'v40_native_reader'}, {'id': 'v40_learner'},
                 {'id': 'v40_snapshot'}, {'id': 'v40_readiness_cpu'}]},
])
def test_v40_cpu_receipts_cannot_supply_fresh_v41_preparation(index):
    class ArtificialIndex:
        def read(self, path):
            return json.dumps(index).encode()
    with pytest.raises(ValueError, match='schema|five explicitly selected'):
        preparing.verify_preparation_evidence(inputs=ArtificialIndex())


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

