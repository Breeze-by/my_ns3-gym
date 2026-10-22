"""Artificial admission-only V52 fixtures; no models, CUDA or native activity.

Prior original SHA anchors are explicitly replaced with artificial anchors.
This tests validation logic and invocation order, never historical credit.
"""
import contextlib
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import pytest

from mr3_learning import reach_preparation
from mr3_learning.tests import test_reach_engineering_block as block_fixtures

PACKAGE = 'report.assets.20261023_mr3_p2a_v52_qualification.'
preparing = importlib.import_module(PACKAGE + 'prepare_plan_v1')
preflight = importlib.import_module(PACKAGE + 'preflight_v1')
checking = importlib.import_module(PACKAGE + 'plan_check_v1')
driver = importlib.import_module(PACKAGE + 'execute_chain_v1')
FREEZE = 'a' * 40


class AcceptedBoundary(Exception):
    pass


class ActivityResourceEntryTests(unittest.TestCase):
    def setUp(self):
        self.f = block_fixtures.EngineeringBlockTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.a = self.f.root
        self.plan_path = self.a / 'plan_v1.json'
        self.stack.enter_context(patch.object(preparing, 'W', reach_preparation.WORKSPACE))
        self.driver_file = self.a / 'toy_driver.json'
        self.review_file = self.a / 'toy_closed_review.json'
        self.write(self.driver_file, {
            'schema': 'mr3-single-ep-runtime-profile-driver-v1', 'passed': True,
            'started_monotonic_ns': 1_000_000_000, 'ended_monotonic_ns': 11_000_000_000,
            'actual_parent_wait_seconds': '10', 'engineering_added_seconds': '10',
            'engineering_used_at_entry_seconds': '90', 'engineering_cumulative_used_seconds': '100',
            'engineering_remaining_seconds': '900', 'engineering_ceiling_seconds': '1000',
            'actual_returncode': 0, 'actual_wrapper_waited': True, 'errors': [],
            'profiling_execution_freeze': FREEZE, 'native_evidence_freeze': FREEZE})
        self.write(self.review_file, {
            'schema': 'mr3-v51-independent-closed-metadata-review-v1', 'passed': True,
            'actual_wrapper_waited': True, 'scope_and_sources_unchanged': True,
            'all_saved_identities_fresh_gone': True, 'closed_guard_and_child_passed': True,
            'engineering_cumulative_used_seconds': '100', 'engineering_remaining_seconds': '900',
            'engineering_added_parent_wait_seconds': '10', 'execution_freeze': FREEZE,
            'native_evidence_freeze': FREEZE, 'external_scientific_tail_actual_seconds': '0',
            'pilot_added_seconds': '0', 'validation_added_seconds': '0'})
        originals = {}
        for key, path in [('driver_summary', self.driver_file), ('closed_metadata_review', self.review_file)]:
            row = self.f.spec(path)
            row['path'] = str(path.relative_to(preparing.W))
            originals[key] = row
        self.ledger = {
            'schema': 'mr3-engineering-closure-ledger-v1', 'passed': True,
            'engineering_previous_cumulative_seconds': '90', 'engineering_added_seconds': '10',
            'engineering_cumulative_seconds': '100', 'engineering_remaining_seconds': '900',
            'engineering_ceiling_seconds': '1000', 'old_failures_and_cumulative_ledger_preserved': True,
            'scientific_qualification_credit': False, 'execution_freeze': FREEZE,
            'native_evidence_freeze': FREEZE, 'external_scientific_tail_actual_seconds': '0',
            'pilot_added_seconds': '0', 'validation_added_seconds': '0',
            'actual_parent_intervals': [{'started_monotonic_ns': 1_000_000_000,
                'ended_monotonic_ns': 11_000_000_000, 'actual_seconds': '10'}], **originals}
        self.write(self.f.ledger, self.ledger)
        self.f.value['previous_accounting'] = self.f.spec(self.f.ledger)
        self.f.seal(self.f.value)
        for module, key, value in [
                (preparing, 'A', self.a), (preparing, 'RESOURCE', self.f.resource_path),
                (preparing, 'NORMALIZED_PRIOR', self.f.ledger),
                (preparing, 'PLAN', self.plan_path), (preparing, 'BINDING', self.a / 'not_created_binding.json'),
                (preparing, 'PRIOR_ORIGINAL_SHA256', {k: v['sha256'] for k, v in originals.items()}),
                (preflight, 'A', self.a), (checking, 'ASSETS', self.a),
                (driver, 'PLAN', self.plan_path), (driver, 'PREFIX', self.a / 'not_created_driver')]:
            self.stack.enter_context(patch.object(module, key, value))
        self.scope = {
            'schema': 'mr3-p2a-v52-native-qualification-scope-v1',
            'engineering_resource': self.f.spec(self.f.resource_path),
            'robots_per_environment': 3, 'mandatory_roles': 30, 'matrix_episodes': 12,
            'minimum_decisions': 16, 'pilot_requested_decisions': 64,
            'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
            'final_only_schedule': ['open:401', 'open:402', 'open:403'], 'mapping_target': .95,
            'acceptance_gates_unchanged': True, 'old_failures_preserved': True,
            'no_retry_on_required_failure': True, 'p2b_gateway_authorized': False,
            'prior_native_credit_reused': False, 'seed_rule': preparing.SEED_RULE,
            'start_graph_rule': preparing.START_RULE, 'reach_geometry_rule': preparing.REACH_GEOMETRY_RULE,
            'reset_workload_reader_profile': reach_preparation.reset_workload.PROFILE}
        self.authorization = {
            'schema': 'mr3-p2a-autonomous-continuation-authorization-v1',
            'status': 'AUTHORIZED_BY_USER_CONTINUATION',
            'user_exact_text': '你一直继续执行就好了，直到把P2A完成，不需要问我是否批准',
            'numeric_user_approval_claimed': False,
            'engineering_resource': self.f.spec(self.f.resource_path),
            'acceptance_gates_unchanged': True, 'old_failures_preserved': True,
            'p2b_gateway_authorized': False}
        self.write(self.a / 'scope_v1.json', self.scope)
        self.write(self.a / 'authorization_v1.json', self.authorization)
        self.plan = reach_preparation.build_plan(**dict(self.f.kwargs(), plan_path=self.plan_path),
            engineering_remaining_seconds='40000',
            reservation_profile=reach_preparation.AUTONOMOUS_RESOURCE_PROFILE,
            engineering_resource=self.f.spec(self.f.resource_path), seed_rule=preparing.SEED_RULE,
            start_graph_rule=preparing.START_RULE, reach_geometry_rule=preparing.REACH_GEOMETRY_RULE)
        self.plan['budget']['full_minimum_reservation_available_at_plan_entry'] = True
        self.plan['map_output_packing_profile'] = preparing.PACKING_PROFILE
        self.plan['agent_resource_decision_evidence'] = self.f.spec(self.f.resource_path)
        self.plan['authorization_evidence'] = self.f.spec(self.a / 'authorization_v1.json')
        self.plan['activity_scope'] = self.f.spec(self.a / 'scope_v1.json')
        self.write(self.plan_path, self.plan)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value) + '\n')

    def invoke(self, module, output):
        if module is preparing:
            saved = self.plan_path.read_bytes()
            self.plan_path.unlink()
            try:
                return module.main(['--engineering-resource-sha256', self.f.spec(self.f.resource_path)['sha256']])
            finally:
                self.plan_path.write_bytes(saved)
        if module is preflight:
            return module.main(['--plan', str(self.plan_path), '--freeze', FREEZE, '--output', str(output)])
        argv = ['fixture', '--output', str(output)] if module is checking else ['fixture', '--freeze', FREEZE]
        with patch.object(checking, 'ASSETS', self.plan_path.parent), patch.object(sys, 'argv', argv):
            return module.main()

    def test_prior_carry_and_one_resource_are_accepted(self):
        result, _ = preparing.verify_plan_resource(self.plan)
        self.assertEqual(result['budget']['engineering_cumulative_ceiling_seconds'], '40100')
        self.assertEqual(result['budget']['engineering_used_at_plan_entry_seconds'], '100')
        self.assertNotIn('approved_cumulative_engineering_seconds', self.plan['budget'])
        # V50's five legal replacements must be established independently
        # before their older V49 SHA mismatches can inherit CPU credit.
        w = reach_preparation.WORKSPACE / reach_preparation.WIRELESS_RELATIVE
        old = self.a / 'artificial_v50_cpu'
        (old / 'checks/ppo_fault_cpu_v1').mkdir(parents=True)
        console = old / 'console.log'
        console.write_text('artificial finite CPU receipt\n')
        paths = [w / 'mr3_learning/ppo.py', *(w / 'mr3_learning/tests' / (n + '.py')
            for n in preparing.PRESERVED_PPO_TESTS)]
        rows = [dict(self.f.spec(path), path=str(path)) for path in paths]
        recovery = [dict(row, path=str(Path(row['path']).relative_to(reach_preparation.WORKSPACE)))
                    for row in rows]
        wait = {'schema': 'mr3-reach-outer-actual-wait-v1', 'scope': 'cpu',
            'safety_contract': 'mr3-reach-v1', 'actual_waited': True, 'actual_returncode': 0,
            'errors': [], 'source_unchanged': True, 'passed': True,
            'started_monotonic_ns': 1_000_000_000, 'ended_monotonic_ns': 2_000_000_000,
            'actual_child_wait_seconds': '1', 'coordinator_identity': {'pid': 41, 'start_ticks': 1},
            'child_identity': {'pid': 42, 'parent': 41, 'start_ticks': 2},
            'actual_argv': ['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python', '-B', '-m', 'pytest', '-q',
                *(str(path) for path in paths[1:])],
            'source_before': rows, 'source_after': rows, 'console': self.f.spec(console)}
        wait_path = old / 'checks/ppo_fault_cpu_v1/actual_wait.json'
        self.write(wait_path, wait)
        self.write(old / 'checks/ppo_fault_cpu_v1_source_recovery.json', {'sources': recovery})
        with patch.object(preparing, 'PRESERVED_PPO_ASSETS', old), patch.object(preparing, 'W', w):
            expected = {str(path.relative_to(reach_preparation.WORKSPACE)) for path in paths}
            self.assertEqual(preparing.verify_preserved_ppo_cpu(preparing.Inputs()), expected)
            wait['source_before'][0]['sha256'] = '0' * 64
            self.write(wait_path, wait)
            with self.assertRaisesRegex(ValueError, 'replacement differs'):
                preparing.verify_preserved_ppo_cpu(preparing.Inputs())

    def test_forged_prior_or_parent_fee_is_rejected(self):
        for key, value in [('engineering_added_seconds', '9'),
                           ('engineering_previous_cumulative_seconds', '91'),
                           ('actual_parent_intervals', [])]:
            ledger = dict(self.ledger, **{key: value})
            self.write(self.f.ledger, ledger)
            resource = dict(self.f.value, previous_accounting=self.f.spec(self.f.ledger))
            self.f.seal(resource)
            with self.subTest(key=key), self.assertRaises(ValueError):
                preparing.entry_budget(preparing.Inputs())
        self.write(self.f.ledger, self.ledger)
        changed = json.loads(self.driver_file.read_text())
        changed['passed'] = True
        changed['engineering_added_seconds'] = '9'
        self.write(self.driver_file, changed)
        self.f.seal(dict(self.f.value, previous_accounting=self.f.spec(self.f.ledger)))
        with self.assertRaisesRegex(ValueError, 'input binding differs'):
            preparing.entry_budget(preparing.Inputs())

    def boundary(self, module, stack):
        if module in (preparing, preflight):
            return stack.enter_context(patch.object(preparing, 'verify_classification', side_effect=AcceptedBoundary))
        if module is checking:
            return stack.enter_context(patch.object(checking.policy, 'stage_spec', side_effect=AcceptedBoundary))
        return stack.enter_context(patch.object(driver.Path, 'mkdir', side_effect=AcceptedBoundary))

    def git_only_subprocess(self, stack):
        original = subprocess.Popen
        def readonly(argv, *args, **kwargs):
            if not isinstance(argv, (list, tuple)) or argv[:2] != ['git', 'ls-files']:
                raise AssertionError('fixture forbids subprocess: ' + repr(argv))
            return original(argv, *args, **kwargs)
        return stack.enter_context(patch.object(subprocess, 'Popen', side_effect=readonly))

    def test_all_four_real_entries_accept_only_to_pre_model_boundary(self):
        # The fixed plan-check filename is part of its public activity contract.
        self.write(self.a / 'plan_v1.json', self.plan)
        for module in (preparing, preflight, checking, driver):
            with self.subTest(module=module.__name__), contextlib.ExitStack() as stack:
                boundary = self.boundary(module, stack)
                self.git_only_subprocess(stack)
                with self.assertRaises(AcceptedBoundary):
                    self.invoke(module, self.a / 'not_created_output.json')
                boundary.assert_called_once()

    def test_all_four_real_entries_reject_overbudget_before_effects(self):
        value = dict(self.f.value, engineering_remaining_seconds='30000', engineering_ceiling_seconds='30100')
        self.f.seal(value)
        for module in (preparing, preflight, checking, driver):
            with self.subTest(module=module.__name__), contextlib.ExitStack() as stack:
                boundary = self.boundary(module, stack)
                self.git_only_subprocess(stack)
                with self.assertRaises(ValueError):
                    self.invoke(module, self.a / 'not_created_output.json')
                boundary.assert_not_called()

    def test_conflicting_plan_budget_is_rejected(self):
        for key, bad in [('engineering_remaining_seconds', '40001'),
                         ('approved_cumulative_engineering_seconds', '75000')]:
            plan = copy.deepcopy(self.plan)
            plan['budget'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                reach_preparation.validate_plan(plan)

    def test_preflight_really_calls_both_reset_reader_readiness_and_keeps_receipt(self):
        plan = copy.deepcopy(self.plan)
        proof, classification = {'fixture': 'cpu'}, {'fixture': 'classification'}
        plan['prospective_preparation_requirement'] = proof
        plan['prospective_classification_regression'] = classification
        plan['map_output_packing_profile'] = preparing.PACKING_PROFILE
        plan['policy_stages'] = {name: {'external_finalize_reserve_seconds': '0' if name == 'minimum' else '300'}
                                  for name in ('minimum', 'pilot', 'validation')}
        condition = {'admit_only_if': 'actual_engineering_remaining_seconds >= 1800 + unused_external_reserve_seconds',
                     'minimum_stage_reservation_seconds': '1800', 'external_reserve_initial_seconds': '300'}
        plan['post_qualification'] = {'fresh_minimum': {'engineering_balance_condition': condition},
                                    'external_final_and_accounting_reservation_seconds': '300'}
        self.write(self.plan_path, plan)
        prior = self.a / 'toy_policy_inputs'
        prior.mkdir()
        self.write(prior / 'predeclared_plan_v1.json', {'artificial': True})
        output = self.a / 'preflight_fixture.json'
        marker = {'schema': 'artificial-reset-entry', 'passed': True, 'audit_calls': 0}
        import torch
        with contextlib.ExitStack() as stack:
            for owner, key, value in [
                (preparing, 'verify_classification', classification),
                (preparing, 'policy_registry', plan['policy_stages']),
                (preflight.reach_preparation, 'source_check', {}),
                (preflight.native_custody_reach, 'verify_binding', {}),
                (preflight.reach_preparation, 'load_executor', (None, {})),
                (preflight.audit_reach_controlled_physics, 'load_impl', (None, {})),
                (preflight.audit_reach_preparation, 'load_impl', (None, {})),
                (preflight.audit_reach_peer_control, 'load_impl', (None, {})),
                (preflight.audit_reach_cadence, 'load_implementation', (None, {})),
                (preflight.audit_reach_runtime, 'source_proof', {'fixture': 'runtime-source'}),
                (preflight.audit_reach_cadence, 'source_proof', {'fixture': 'cadence-source'}),
                (preflight.audit_reach_ppo, 'load_impl', (None, {})),
                (preflight.reach_gates, 'load_native_gates', ({},)),
                (torch.cuda, 'is_available', True), (torch.cuda, 'device_count', 1),
                (torch.cuda, 'get_device_name', 'artificial-no-GPU')]:
                stack.enter_context(patch.object(owner, key, return_value=value))
            stack.enter_context(patch.object(preparing, 'PRIOR', prior))
            stack.enter_context(patch.object(preparing, 'verify_preparation_evidence', return_value=(proof, None)))
            stack.enter_context(patch.object(preflight, 'stage_spec', return_value={}))
            actual = stack.enter_context(patch.object(preflight.audit_reach_reset_workload,
                'verify_reader_readiness', return_value=marker))
            self.invoke(preflight, output)
            actual.assert_called_once()
            self.assertEqual(actual.call_args.args, (plan, FREEZE))
        result = json.loads(output.read_text())
        self.assertEqual(result['dispatch_projections']['reset_reader'], marker)
        self.assertFalse(result['scientific_native_credit'])


@pytest.mark.parametrize('module', ['prepare_plan_v1', 'preflight_v1', 'plan_check_v1', 'execute_chain_v1'])
def test_all_four_real_module_help(module):
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    result = subprocess.run([sys.executable, '-B', '-m', PACKAGE + module, '--help'],
        cwd=reach_preparation.WORKSPACE / reach_preparation.WIRELESS_RELATIVE,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert '--help' in result.stdout and 'usage:' in result.stdout


if __name__ == '__main__':
    unittest.main()
