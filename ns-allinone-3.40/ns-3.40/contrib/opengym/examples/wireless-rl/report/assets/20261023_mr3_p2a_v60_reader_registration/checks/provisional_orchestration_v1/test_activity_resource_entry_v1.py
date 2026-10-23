"""Artificial admission-only V60 fixtures; no models, CUDA or native activity.

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

PACKAGE = 'report.assets.20261023_mr3_p2a_v60_reader_registration.'
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
        self.root_wait_file = self.a / 'toy_root_wait.json'
        self.inventory_file = self.a / 'toy_inventory.json'
        # Four actual-parent fixtures: overlap is counted once and gaps are
        # excluded. Individual waits sum to11, the union is10, whole span13.
        self.phases = [dict(name=name, scope='engineering', started_monotonic_ns=lo*10**9,
            ended_monotonic_ns=hi*10**9, actual_seconds=str(hi-lo), passed=rc == 0,
            actual_returncode=rc) for name,lo,hi,rc in (
                ('preflight',1,3,0), ('matrix',4,9,1),
                ('matrix_absence',8,10,0), ('chain_final_absence',12,14,0))]
        self.write(self.driver_file, {
            'schema':'mr3-v59-actual-chain-driver-result-v1','passed':False,'freeze':FREEZE,
            'actual_waits':self.phases,'engineering_added_union_seconds':'10',
            'engineering_cumulative_used_seconds':'100','pilot_added_union_seconds':'0',
            'validation_added_union_seconds':'0','errors':['artificial required full FAIL'],
            'old_failures_preserved':True,'p2b_gateway_started':False})
        self.write(self.root_wait_file, {'schema':'mr3-v59-root-actual-tool-wait-v1',
            'actual_waited':True,'actual_returncode_observed':1})
        original_specs = {key:self.f.spec(path) for key,path in
            (('driver_summary',self.driver_file),('root_actual_tool_wait',self.root_wait_file))}
        self.write(self.review_file, {
            'schema':'mr3-v59-independent-closed-metadata-review-draft-v2','passed':True,'freeze':FREEZE,
            'review_errors':[],'resource_violations':[],'activity_passed':False,
            'parent_wait_proof_valid':True,'all_saved_owned_PID_start_identities_fresh_gone':True,
            'identity_inventory_complete_under_A16_rules':True,'source_before_after_checked':True,
            'bound_inputs_stable':True,'metadata_membership_stable':True,
            'engineering_added_parent_union_seconds':'10','engineering_cumulative_seconds':'100',
            'engineering_remaining_seconds':'900','pilot_added_parent_union_seconds':'0',
            'validation_added_parent_union_seconds':'0','actual_parent_intervals':self.phases,
            'scientific_results_recomputed':False,'models_loaded':False,'actor_inputs_read':False,
            'raw_telemetry_read':False,'independent_P2A_scientific_acceptance_inferred':False,
            'native_runs':0,'gpu_calls':0,'root_tool_actual_returncode_observed':1,
            'root_actual_tool_wait':dict(original_specs['root_actual_tool_wait'],path=str(self.root_wait_file))})
        self.write(self.inventory_file, {'schema':'mr3-v59-closed-byte-archive-draft-v2',
            'byte_archive_complete':True,'freeze':FREEZE,'original_activity_passed':False,
            'original_scientific_or_closure_FAIL_rejudged':False,'entries':[
            {'original':str(path),'codec':'original-bytes','original_sha256':spec['sha256'],
             'canonical_sha256':spec['sha256'],'original_bytes':spec['bytes'],
             'canonical_bytes':spec['bytes'],'canonical':path.name}
            for key,path in (('driver_summary',self.driver_file),('root_actual_tool_wait',self.root_wait_file))
            for spec in (original_specs[key],)]})
        self.ledger = {
            'schema':'mr3-engineering-closure-ledger-v1','passed':True,'activity_passed':False,
            'root_actual_returncode':1,'engineering_entry_seconds':'90','engineering_added_seconds':'10',
            'engineering_cumulative_seconds':'100','engineering_remaining_seconds':'900',
            'engineering_ceiling_seconds':'1000','old_FAIL_and_pending_fields_preserved':True,
            'all_saved_main_identities_fresh_gone':True,'native_qualification_credit':False,'P2A_complete':False,
            'optimizer_updates':0,'p2b_gateway_started':False,
            'execution_freeze':FREEZE,'pilot_added_seconds':'0','validation_added_seconds':'0',
            'engineering_fee_intervals':self.phases,**original_specs,
            'closed_metadata_review':self.f.spec(self.review_file),'closed_inventory':self.f.spec(self.inventory_file)}
        self.write(self.f.ledger,self.ledger)
        originals = {**original_specs,'closed_metadata_review':self.f.spec(self.review_file),
                     'closure_ledger':self.f.spec(self.f.ledger)}
        self.f.value['previous_accounting'] = self.f.spec(self.f.ledger)
        self.f.seal(self.f.value)
        for module, key, value in [
                (preparing, 'A', self.a), (preparing, 'RESOURCE', self.f.resource_path),
                (preparing, 'NORMALIZED_PRIOR', self.f.ledger),
                (preparing, 'PLAN', self.plan_path), (preparing, 'BINDING', self.a / 'not_created_binding.json'),
                (preparing, 'PRIOR_ORIGINAL_SHA256', {k: v['sha256'] for k, v in originals.items()}),
                (preparing, 'PRIOR_ORIGINAL_PATHS', {'driver_summary':str(self.driver_file),
                    'root_actual_tool_wait':str(self.root_wait_file)}),
                (preflight, 'A', self.a), (checking, 'ASSETS', self.a),
                (driver, 'PLAN', self.plan_path), (driver, 'PREFIX', self.a / 'not_created_driver')]:
            self.stack.enter_context(patch.object(module, key, value))
        self.scope = {
            'schema': 'mr3-p2a-v60-native-qualification-scope-v1',
            'engineering_resource': self.f.spec(self.f.resource_path),
            'robots_per_environment': 3, 'mandatory_roles': 30, 'matrix_episodes': 12,
            'minimum_decisions': 16, 'pilot_requested_decisions': 64,
            'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
            'final_only_schedule': ['open:401', 'open:402', 'open:403'], 'mapping_target': .95,
            'acceptance_gates_unchanged': True, 'old_failures_preserved': True,
            'no_retry_on_required_failure': True, 'p2b_gateway_authorized': False,
            'prior_native_credit_reused': False, 'seed_rule': preparing.SEED_RULE,
            'start_graph_rule': preparing.START_RULE, 'reach_geometry_rule': preparing.REACH_GEOMETRY_RULE,
            'reset_workload_reader_profile': reach_preparation.reset_workload.PROFILE,
            'actuation_profile': preparing.ACTUATION_PROFILE}
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
        binding_path = self.f.kwargs()['custody_binding']
        self.write(binding_path, {
            'reach_geometry_rule': preparing.REACH_GEOMETRY_RULE,
            'actuation_profile': preparing.ACTUATION_PROFILE, 'binaries': {},
            'source_bindings': [self.f.spec(reach_preparation.WORKSPACE / relative)
                for relative in sorted(reach_preparation.SUPPORT_REACH_SOURCES)]})
        self.plan = reach_preparation.build_plan(**dict(self.f.kwargs(), plan_path=self.plan_path),
            engineering_remaining_seconds='40000',
            reservation_profile=reach_preparation.AUTONOMOUS_RESOURCE_PROFILE,
            engineering_resource=self.f.spec(self.f.resource_path), seed_rule=preparing.SEED_RULE,
            start_graph_rule=preparing.START_RULE, reach_geometry_rule=preparing.REACH_GEOMETRY_RULE,
            actuation_profile=preparing.ACTUATION_PROFILE)
        self.plan['budget']['full_minimum_reservation_available_at_plan_entry'] = True
        self.plan['map_output_packing_profile'] = preparing.PACKING_PROFILE
        self.plan['actuation_profile'] = preparing.ACTUATION_PROFILE
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
        self.assertEqual(result['budget']['total_engineering_reservation_at_entry_seconds'], '32220')

    def test_current_python_classification_includes_untracked(self):
        import tempfile
        current_python_sources = importlib.import_module(PACKAGE+'classification_admission_v1').current_python_sources
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            paths=('ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/fresh.py',
                   'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_fresh.py',
                   'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/fresh.py',
                   'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/tests/test_fresh.py')
            for name in paths:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# fixture only')
            runtime,tests=current_python_sources(root)
            self.assertEqual(runtime,{paths[0],paths[2]})
            self.assertEqual(tests,{paths[1],paths[3]})
            extra=Path(paths[1]).with_name('test_created_before_git_add.py')
            (root/extra).write_text('# still untracked')
            self.assertIn(str(extra),current_python_sources(root)[1])

    def test_forged_prior_or_parent_fee_is_rejected(self):
        for key, value in [('engineering_added_seconds', '9'),
                           ('engineering_entry_seconds', '91'),
                           ('engineering_fee_intervals', [dict(self.phases[0], ended_monotonic_ns=2_000_000_000), *self.phases[1:]])]:
            ledger = dict(self.ledger, **{key: value})
            self.write(self.f.ledger, ledger)
            resource = dict(self.f.value, previous_accounting=self.f.spec(self.f.ledger))
            self.f.seal(resource)
            with self.subTest(key=key), self.assertRaises(ValueError):
                with patch.dict(preparing.PRIOR_ORIGINAL_SHA256, {'closure_ledger':self.f.spec(self.f.ledger)['sha256']}):
                    preparing.entry_budget(preparing.Inputs())
        self.write(self.f.ledger, self.ledger)
        changed = json.loads(self.driver_file.read_text())
        changed['passed'] = True
        changed['engineering_added_seconds'] = '9'
        self.write(self.driver_file, changed)
        self.f.seal(dict(self.f.value, previous_accounting=self.f.spec(self.f.ledger)))
        with self.assertRaisesRegex(ValueError, 'input binding differs'):
            preparing.entry_budget(preparing.Inputs())

    def test_phase_union_excludes_overlap_and_gaps_without_rejudging_prior_fail(self):
        _, _, used, remaining = preparing.entry_budget(preparing.Inputs())
        self.assertEqual(str(used), '100')
        self.assertEqual(str(remaining), '40000')
        self.assertEqual(sum(int(row['actual_seconds']) for row in self.phases), 11)
        self.assertFalse(json.loads(self.driver_file.read_text())['passed'])
        self.assertEqual(json.loads(self.root_wait_file.read_text())['actual_returncode_observed'], 1)

    def test_prior_typed_wait_fail_and_phase_identity_cannot_be_reinterpreted(self):
        for key, bad in (('activity_passed',True),('root_actual_returncode',True),
                         ('root_actual_returncode',0),('optimizer_updates',True)):
            value = dict(self.ledger, **{key:bad})
            self.write(self.f.ledger,value)
            self.f.seal(dict(self.f.value,previous_accounting=self.f.spec(self.f.ledger)))
            with self.subTest(key=key,bad=bad), patch.dict(preparing.PRIOR_ORIGINAL_SHA256,
                    {'closure_ledger':self.f.spec(self.f.ledger)['sha256']}), self.assertRaises(ValueError):
                preparing.entry_budget(preparing.Inputs())
        for key,bad in (('started_monotonic_ns',True),('actual_seconds','NaN'),
                        ('actual_returncode',True),('passed',1),('scope','pilot')):
            value = copy.deepcopy(self.ledger)
            value['engineering_fee_intervals'][0][key] = bad
            self.write(self.f.ledger,value)
            self.f.seal(dict(self.f.value,previous_accounting=self.f.spec(self.f.ledger)))
            with self.subTest(key=key,bad=bad), patch.dict(preparing.PRIOR_ORIGINAL_SHA256,
                    {'closure_ledger':self.f.spec(self.f.ledger)['sha256']}), self.assertRaises(ValueError):
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
        plan['policy_stages'] = {name: {'external_finalize_reserve_seconds': '0' if name == 'minimum' else '300',
                                     'actuation_profile':preparing.ACTUATION_PROFILE}
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
                (preflight.native_custody_reach, 'verify_binding', {
                    'actuation_profile':preparing.ACTUATION_PROFILE,'reach_build_bridge_proof':{
                        'actuation_profile':preparing.ACTUATION_PROFILE,'new_build_executed':True,
                        'initial_encoder_compiled_source':{'sha256':'1'*64}}}),
                (preflight.reach_preparation, 'load_executor', (None, {})),
                (preflight.audit_reach_controlled_physics, 'load_impl', (None, {})),
                (preflight.audit_reach_preparation, 'load_impl', (None, {})),
                (preflight.audit_reach_peer_control, 'load_impl', (None, {})),
                (preflight.audit_reach_cadence, 'load_implementation', (None, {})),
                (preflight.audit_reach_runtime, 'source_proof', {preflight.audit_reach_runtime.ENCODER_HEADER_SOURCE:{'sha256':'1'*64}}),
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
            preflight.audit_reach_cadence.load_implementation.assert_called_once_with(
                preflight.ROOT, actuation_profile=preparing.ACTUATION_PROFILE)
            preflight.native_custody_reach.verify_binding.assert_called_once_with(
                preflight.ROOT, FREEZE, plan['custody_binding'])
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
