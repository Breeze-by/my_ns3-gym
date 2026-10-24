"""Finite CPU/protocol checks; these fixtures supply no native/scientific PASS."""
import copy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import reach_policy_chain as chain

FREEZE = 'a' * 40


def plan_fixture(root):
    plan_path, qualification = root / 'plan.json', root / 'qualification.json'
    plan = {'learner_python': sys.executable, 'custody_binding': str(root / 'binding.json'), 'policy_stages': {}}
    for stage in chain.STAGES:
        run, output = root / (stage + '_run'), root / (stage + '_evidence')
        mode = 'evaluate' if stage == 'validation' else 'train'
        schedule = 'open:401,open:402,open:403' if stage == 'validation' else 'open:101'
        argv = [sys.executable, '-m', 'mr3_learning.ppo', '--run-id', run.name, '--output-root', str(root),
            '--mode', mode, '--safety-contract', chain.CONTRACT, '--reach-plan', str(plan_path),
            '--reach-qualification', str(qualification), '--wall-seconds', str(chain.NATIVE_CAPS[stage]),
            '--decisions', {'minimum': '16', 'pilot': '1870', 'validation': '900'}[stage],
            '--episode-steps', {'minimum': '8', 'pilot': '64', 'validation': '300'}[stage],
            '--schedule', schedule, '--seed', '41']
        if stage == 'validation':
            argv += ['--checkpoint', str(root / 'pilot_run/final.zip')]
        condition = {'requires': {'minimum': 'matrix_qualification', 'pilot': 'minimum_complete', 'validation': 'pilot_complete'}[stage]}
        if stage != 'minimum':
            previous = 'minimum' if stage == 'pilot' else 'pilot'
            condition.update(previous_stage_summary=str(root / (previous + '_evidence/summary.json')),
                previous_stage_outer_wait=str(root / (previous + '_wait/actual_wait.json')),
                previous_stage_final_absence=str(root / (previous + '_final.json')))
        plan['policy_stages'][stage] = {'argv': argv, 'run_directory': str(run), 'output_directory': str(output),
            'wall_seconds': str(chain.CAPS[stage]), 'tail_reserve_seconds': '500', 'condition': condition}
    return plan, plan_path, qualification


def native_fixture(stage='minimum'):
    scenes = [('open', 401), ('open', 402), ('open', 403)] if stage == 'validation' else [('open', 101), ('open', 101)]
    episodes = [Path('/synthetic/native/round0000') / f'worker{i}' / f'episode001_{scene}_{seed}'
                for i, (scene, seed) in enumerate(scenes)]
    counts = [300] * 3 if stage == 'validation' else [8, 8]
    rows = [{'directory': str(path), 'scene': scene, 'seed': seed, 'decisions': count, 'api_records': count,
             'training_eligibility': {'training_eligible': True}}
            for path, (scene, seed), count in zip(episodes, scenes, counts)]
    count = sum(counts)
    mode = 'evaluate' if stage == 'validation' else 'train'
    metadata = {'safety_contract': chain.CONTRACT, 'mode': mode, 'schedule': [list(x) for x in scenes]}
    native = {'safety_contract': chain.CONTRACT, 'mode': mode, 'completed': True, 'error': None,
        'cleanup_errors': [], 'native_accounting_errors': [], 'native_attempts': [{'directory': str(p)} for p in episodes],
        'episodes': rows, 'decisions': count, 'closed_episode_decisions': count, 'native_recorded_decisions': count,
        'api_records': count, 'native_api_records': count, 'optimizer_updates': 0 if stage == 'validation' else 4,
        'schedule_completed': stage == 'validation'}
    audit = {'schema': 'mr3-reach-ppo-offline-audit-v1', 'safety_contract': chain.CONTRACT, 'passed': True,
             'errors': [], 'native_attempts': len(episodes), 'task_successes': 3 if stage == 'validation' else 0,
             'task_failures': []}
    spec = {'argv': ['--decisions', '1870' if stage == 'pilot' else str(count)]}
    return metadata, native, audit, episodes, spec


class ReachPolicyChainTests(unittest.TestCase):
    def test_point_attachment_minimum_pilot_and_final_cannot_borrow_original_v2(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan,path,qualification=plan_fixture(Path(temporary))
            plan.update(seed_rule='exact-point-bridge-v2',start_graph_rule='point-attachment-3x3-v1')
            for stage in chain.STAGES:
                plan['policy_stages'][stage]['argv'] += ['--seed-rule',plan['seed_rule'],
                    '--start-graph-rule',plan['start_graph_rule']]
                chain.stage_spec(plan,path,qualification,stage)
                changed=copy.deepcopy(plan);argv=changed['policy_stages'][stage]['argv']
                argv[argv.index('--start-graph-rule')+1]='original-seed-cell'
                with self.subTest(stage=stage),self.assertRaisesRegex(ValueError,'start graph rule differs'):
                    chain.stage_spec(changed,path,qualification,stage)
        metadata,native,audit,episodes,spec=native_fixture()
        metadata['seed_rule']='exact-point-bridge-v2'
        spec['argv'] += ['--seed-rule','exact-point-bridge-v2','--start-graph-rule','point-attachment-3x3-v1']
        with self.assertRaisesRegex(ValueError,'start graph rule differs'):
            chain.check_native_result('minimum',metadata,native,audit,episodes,spec)
        metadata['start_graph_rule']='point-attachment-3x3-v1'
        self.assertEqual(chain.check_native_result('minimum',metadata,native,audit,episodes,spec)['eligible_decisions'],16)

    def test_v2_minimum_pilot_and_final_are_bound_to_the_same_qualification_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan,path,qualification=plan_fixture(Path(temporary))
            plan['seed_rule']='exact-point-bridge-v2'
            for stage in chain.STAGES:
                plan['policy_stages'][stage]['argv'] += ['--seed-rule','exact-point-bridge-v2']
                chain.stage_spec(plan,path,qualification,stage)
                changed=copy.deepcopy(plan)
                argv=changed['policy_stages'][stage]['argv']
                argv[argv.index('--seed-rule')+1]='exact-point-bridge-v1'
                with self.subTest(stage=stage),self.assertRaisesRegex(ValueError,'seed rule differs'):
                    chain.stage_spec(changed,path,qualification,stage)

    def test_all_policy_stages_use_the_qualification_seed_rule(self):
        with tempfile.TemporaryDirectory() as temporary:
            original,path,qualification=plan_fixture(Path(temporary))
            original['seed_rule']='exact-point-bridge-v1'
            for stage in chain.STAGES:
                original['policy_stages'][stage]['argv'] += ['--seed-rule',original['seed_rule']]
                chain.stage_spec(original,path,qualification,stage)
                changed=copy.deepcopy(original)
                argv=changed['policy_stages'][stage]['argv']
                argv[argv.index('--seed-rule')+1]='legacy'
                with self.subTest(stage=stage),self.assertRaisesRegex(ValueError,'seed rule differs'):
                    chain.stage_spec(changed,path,qualification,stage)

    def test_native_policy_result_cannot_claim_a_different_seed_rule(self):
        metadata,native,audit,episodes,spec=native_fixture()
        spec['argv'] += ['--seed-rule','exact-point-bridge-v1']
        with self.assertRaisesRegex(ValueError,'seed rule differs'):
            chain.check_native_result('minimum',metadata,native,audit,episodes,spec)
        metadata['seed_rule']='exact-point-bridge-v1'
        self.assertEqual(chain.check_native_result('minimum',metadata,native,audit,episodes,spec)['eligible_decisions'],16)

    def test_explicit_phase_contract_keeps_prefix_and_original_three_open_seeds(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, path, qualification = plan_fixture(Path(temporary))
            for stage in chain.STAGES:
                self.assertIs(chain.stage_spec(plan, path, qualification, stage), plan['policy_stages'][stage])
            pilot = plan['policy_stages']['pilot']['argv']
            pilot[pilot.index('--episode-steps') + 1] = '300'
            with self.assertRaisesRegex(ValueError, 'external collection prefix'):
                chain.stage_spec(plan, path, qualification, 'pilot')
            validation = plan['policy_stages']['validation']['argv']
            validation[validation.index('--schedule') + 1] = 'open:101,rooms:101,corridors:101'
            with self.assertRaisesRegex(ValueError, 'original three open'):
                chain.stage_spec(plan, path, qualification, 'validation')

    def test_minimum_quota_seed_and_qualification_paths_are_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, path, qualification = plan_fixture(Path(temporary))
            for flag, value in (('--decisions', '15'), ('--seed', '17'), ('--reach-qualification', '/synthetic/other.json')):
                plan = copy.deepcopy(original); argv = plan['policy_stages']['minimum']['argv']
                argv[argv.index(flag) + 1] = value
                with self.subTest(flag=flag), self.assertRaises(ValueError):
                    chain.stage_spec(plan, path, qualification, 'minimum')

    def test_downward_budget_counts_admission_and_preserves_five_hundred_tail(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, _, _ = plan_fixture(Path(temporary))
            start = 1000
            argv, proof = chain.native_budget(plan['policy_stages']['validation'], 'validation', start, start + 1_234_567_890)
            self.assertEqual(chain.argument(argv, '--wall-seconds'), '8498.765')
            self.assertEqual(proof['tail_reserve_seconds'], '500')
            self.assertEqual(proof['original_argv'], plan['policy_stages']['validation']['argv'])
            with self.assertRaises(ValueError):
                chain.native_budget(plan['policy_stages']['minimum'], 'minimum', start, start + 1300*10**9)

    def test_budget_cannot_expand_or_accept_nonfinite(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, _, _ = plan_fixture(Path(temporary))
            argv, _ = chain.native_budget(plan['policy_stages']['minimum'], 'minimum', 1, 1)
            self.assertEqual(chain.argument(argv, '--wall-seconds'), '1150.000')
            with self.assertRaises(ValueError): chain.native_budget(plan['policy_stages']['minimum'], 'minimum', 2, 1)
        for value in (True, 'NaN', 'Infinity'):
            with self.subTest(value=value), self.assertRaises(ValueError): chain.decimal(value)

    def test_external_reserve_default_and_explicit_zero_preserve_the_original_budget_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, path, qualification = plan_fixture(Path(temporary))
            for stage in chain.STAGES:
                spec = plan['policy_stages'][stage]
                original = chain.native_budget(spec, stage, 1, 1_234_567_891)
                spec['external_finalize_reserve_seconds'] = '0'
                self.assertIs(chain.stage_spec(plan, path, qualification, stage), spec)
                self.assertEqual(chain.native_budget(spec, stage, 1, 1_234_567_891), original)
                self.assertNotIn('external_finalize_reserve_seconds', original[1])
                self.assertNotIn('main_wall_allocation_seconds', original[1])

    def test_external_reserve_and_admission_time_leave_the_original_internal_tail(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, path, qualification = plan_fixture(Path(temporary))
            for stage, elapsed, main, native in (
                    ('pilot', 30_123_456_789, '2605.9547395464029', '2075.831'),
                    ('validation', 1_234_567_890, '8700', '8198.765')):
                spec = plan['policy_stages'][stage]
                before = copy.deepcopy(spec['argv'])
                spec['external_finalize_reserve_seconds'] = '300'
                chain.stage_spec(plan, path, qualification, stage)
                argv, proof = chain.native_budget(spec, stage, 1, 1 + elapsed)
                self.assertEqual(chain.argument(argv, '--wall-seconds'), native)
                self.assertEqual(proof['main_wall_allocation_seconds'], main)
                self.assertEqual(proof['external_finalize_reserve_seconds'], '300')
                self.assertEqual(proof['tail_reserve_seconds'], '500')
                self.assertEqual(proof['declared_native_ceiling_seconds'], str(chain.NATIVE_CAPS[stage]))
                self.assertEqual(spec['argv'], before)
                self.assertLessEqual(Decimal(native), chain.NATIVE_CAPS[stage])
                self.assertLessEqual(Decimal(native) + Decimal(elapsed) / 10**9 + 500, Decimal(main))
            self.assertEqual(chain.NATIVE_CAPS, {'minimum': Decimal('1150'),
                'pilot': Decimal('2100'), 'validation': Decimal('8500')})

    def test_external_reserve_rejects_nonfinite_negative_or_unfunded_declarations(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, path, qualification = plan_fixture(Path(temporary))
            for stage in chain.STAGES:
                spec = plan['policy_stages'][stage]
                for value in (True, None, 'NaN', 'Infinity', '-1', str(chain.CAPS[stage] - 500),
                              str(chain.CAPS[stage])):
                    spec['external_finalize_reserve_seconds'] = value
                    with self.subTest(stage=stage, value=value):
                        with self.assertRaises(ValueError):
                            chain.stage_spec(plan, path, qualification, stage)
                        with self.assertRaises(ValueError):
                            chain.native_budget(spec, stage, 1, 1)

    def test_external_reserved_time_cannot_be_borrowed_for_more_native_sampling(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, _, _ = plan_fixture(Path(temporary))
            for stage, elapsed in (('pilot', 2106), ('validation', 8200)):
                spec = plan['policy_stages'][stage]
                # The same elapsed time still permits a positive original
                # allocation, but not after the external reserve is declared.
                chain.native_budget(spec, stage, 1, 1 + elapsed * 10**9)
                spec['external_finalize_reserve_seconds'] = '300'
                with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, 'leaves no native budget'):
                    chain.native_budget(spec, stage, 1, 1 + elapsed * 10**9)

    def test_main_deadline_cannot_submit_a_watcher_during_external_reserved_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, path, qualification = plan_fixture(root)
            spec = plan['policy_stages']['validation']
            spec['external_finalize_reserve_seconds'] = '300'
            path.write_text(json.dumps(plan) + '\n')
            qualification.write_text('{}\n')
            runner = Mock()
            executor = SimpleNamespace(Runner=Mock(return_value=runner))
            # Only the initial admission/source bookkeeping is synthetic. No
            # watcher/native consumer is permitted to start in this fixture.
            clocks = iter((1,))
            late = 8700 * 10**9 + 2
            with patch.object(chain.time, 'monotonic_ns', side_effect=lambda: next(clocks, late)), \
                    patch.object(chain.preparation, 'load_plan', return_value=plan), \
                    patch.object(chain.preparation, 'source_check'), \
                    patch.object(chain.preparation, 'validate_qualification', return_value={'schema': 'fixture'}), \
                    patch.object(chain, '_validate_predecessor', return_value=None), \
                    patch.object(chain.preparation, 'load_executor', return_value=(executor, {})), \
                    patch.object(chain.preparation.primitives, 'identity', return_value={
                        'pid': 123, 'start_ticks': 456, 'state': 'S'}):
                result = chain.execute_stage(path, FREEZE, qualification, 'validation')
            runner.spawn.assert_not_called()
            runner.command.assert_not_called()
            self.assertFalse(result['passed'])
            self.assertFalse(result['within_stage_wall_allocation'])
            self.assertIn('stage deadline exhausted before watcher submission', result['errors'][0])
            self.assertEqual(result['wall_allocation_seconds'], '9000')
            self.assertEqual(result['main_wall_allocation_seconds'], '8700')
            self.assertEqual(result['external_finalize_reserve_seconds'], '300')
            self.assertTrue(result['external_finalize_actual_wait_required'])
            self.assertFalse(result['external_finalize_fee_included_in_this_verdict'])
            self.assertFalse(result['main_and_external_fee_budget_pass_claimed'])

    def test_external_evidence_refuses_changed_reserve_or_self_certified_future_fee(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, path, qualification = plan_fixture(Path(temporary))
            spec = plan['policy_stages']['pilot']
            spec['external_finalize_reserve_seconds'] = '300'
            output = Path(spec['output_directory']); output.mkdir()
            summary = {'qualification': str(qualification), 'wall_allocation_seconds': str(chain.CAPS['pilot']),
                'main_wall_allocation_seconds': '2605.9547395464029', 'external_finalize_reserve_seconds': '300',
                'external_finalize_actual_wait_required': True, 'external_finalize_fee_included_in_this_verdict': False,
                'main_and_external_fee_budget_pass_claimed': False}
            summary_path = output / 'summary.json'
            def save(value):
                summary_path.write_text(json.dumps(value) + '\n')
            with patch.object(chain.preparation, 'load_plan', return_value=plan), \
                    patch.object(chain.preparation, 'source_check', side_effect=RuntimeError('after reservation scope')):
                save(summary)
                with self.assertRaisesRegex(RuntimeError, 'after reservation scope'):
                    chain.stage_evidence(path, FREEZE, 'pilot', '/unused/outer.json')
                for key, value in (('main_wall_allocation_seconds', str(chain.CAPS['pilot'])),
                        ('external_finalize_reserve_seconds', '0'), ('external_finalize_actual_wait_required', False),
                        ('external_finalize_fee_included_in_this_verdict', True),
                        ('main_and_external_fee_budget_pass_claimed', True)):
                    changed = dict(summary); changed[key] = value; save(changed)
                    with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'external fee reservation/scope'):
                        chain.stage_evidence(path, FREEZE, 'pilot', '/unused/outer.json')

    def test_minimum_requires_real_positive_updates_and_exact_eligible_native_sixteen(self):
        values = native_fixture()
        self.assertEqual(chain.check_native_result('minimum', *values)['eligible_decisions'], 16)
        for key, value in (('optimizer_updates', 0), ('decisions', 15), ('native_recorded_decisions', 17), ('completed', False)):
            metadata, native, audit, episodes, spec = copy.deepcopy(values)
            native[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                chain.check_native_result('minimum', metadata, native, audit, episodes, spec)

    def test_known_model_ineligibility_cannot_be_hidden_by_native_completed(self):
        metadata, native, audit, episodes, spec = native_fixture()
        native['episodes'][0]['training_eligibility']['training_eligible'] = False
        with self.assertRaisesRegex(ValueError, 'training-eligibility'):
            chain.check_native_result('minimum', metadata, native, audit, episodes, spec)

    def test_pilot_may_finish_wall_before_quota_but_never_exceed_old_balance(self):
        values = native_fixture('pilot')
        values[1].update(quota_reached=False, stop_reason='wall_budget')
        self.assertEqual(chain.check_native_result('pilot', *values)['eligible_decisions'], 16)
        values[4]['argv'] = ['--decisions', '1871']
        with self.assertRaises(ValueError): chain.check_native_result('pilot', *values)

    def test_validation_is_exact_final_only_three_seed_zero_update_strict_success(self):
        values = native_fixture('validation')
        self.assertEqual(chain.check_native_result('validation', *values)['strict_task_successes'], 3)
        for failure in ('update', 'task', 'seed', 'missing_attempt'):
            metadata, native, audit, episodes, spec = copy.deepcopy(values)
            if failure == 'update': native['optimizer_updates'] = 1
            elif failure == 'task': audit['task_successes'] = 2
            elif failure == 'seed': metadata['schedule'][1] = ['rooms', 402]
            else: native['native_attempts'].pop()
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                chain.check_native_result('validation', metadata, native, audit, episodes, spec)

    def test_real_episode_inventory_has_no_archive_or_missing_supervisor_credit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / 'native/round0000/worker0/episode001_open_101'
            ignored = root / 'archive/native/round0000/worker0/episode001_open_101'
            for path in (actual, ignored):
                path.mkdir(parents=True); (path / 'supervisor_metadata.json').write_text('{}\n')
            no_supervisor = root / 'native/round0000/worker1/episode001_open_101'
            no_supervisor.mkdir(parents=True); (no_supervisor / 'metadata.json').write_text('{}\n')
            self.assertEqual(chain.native_custody.episode_directories(root), [actual.resolve()])

    def test_whole_episode_fifo_manifest_and_strict_closure_dag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan, path, qualification = plan_fixture(root)
            spec = plan['policy_stages']['minimum']; episodes = [root / 'native/round0000/worker0/episode001_open_101', root / 'native/round0000/worker1/episode001_open_101']
            jobs = chain.jobs_for_stage(plan, path, qualification, spec, episodes)
            by_id = {j['id']: j for j in jobs}
            self.assertEqual(by_id['fifo_manifest']['members'], ['fifo_001', 'fifo_002'])
            self.assertEqual(by_id['closure']['depends_on'], ['fifo_manifest'])
            self.assertEqual(chain.argument(by_id['closure']['argv'], '--expected-episodes'), '2')
            self.assertIn('mr3_learning.audit_reach_ppo', by_id['full']['argv'])

    def test_every_checkpoint_and_rollout_file_is_bound_including_intermediate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = ['initial.zip', 'final.zip', 'checkpoint_0000.zip', 'rollout_0000.npz', 'rollout_0000.json']
            bindings = {}
            for name in names: (root / name).write_bytes(name.encode())
            self.assertEqual({p.name for p in chain.policy_artifacts(root)}, set(names))
            for path in chain.policy_artifacts(root): chain._bind(path, bindings)
            (root / 'checkpoint_0000.zip').write_bytes(b'changed')
            with self.assertRaises(ValueError): chain._verify_bindings(bindings)
            # Full native inventory also binds archive files not named by the
            # original maps report's compressed_sha256-only return shape.
            episode = root / 'native/round0000/worker0/episode001_open_101'
            archive = episode / 'observation_inputs/maps'; archive.mkdir(parents=True)
            (archive / 'map.json.gz').write_bytes(b'synthetic compressed map')
            manifest = episode / 'observation_inputs/snapshots'; manifest.mkdir()
            (manifest / 'snapshot.json').write_text('{}\n')
            paths = chain.closed_episode_artifacts([episode])
            self.assertEqual({p.name for p in paths}, {'map.json.gz', 'snapshot.json'})
            native_bindings = {}
            for path in paths: chain._bind(path, native_bindings)
            (archive / 'map.json.gz').write_bytes(b'tampered map')
            with self.assertRaises(ValueError): chain._verify_bindings(native_bindings)
            (manifest / 'extra.json').write_text('{}\n')
            self.assertNotEqual(chain.closed_episode_artifacts([episode]), paths)

    def test_real_cpu_runner_wait_receipt_and_recomputed_command_predicate(self):
        executor, proof = chain.preparation.load_executor()
        self.assertTrue(proof['whole_source_inverse_equal'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / 'cpu.json'
            # A real finite CPU child writes only its test protocol result.
            # Its passed bool proves no scientific or native role.
            code = 'import json,sys; open(sys.argv[1],"x").write(json.dumps({"passed":True,"freeze":sys.argv[2]})+"\\n")'
            job = {'id': 'finite_cpu', 'required': True, 'argv': [sys.executable, '-c', code, str(output), FREEZE],
                'output': str(output), 'receipt': str(root / 'cpu_command.json'), 'console': str(root / 'cpu.log')}
            runner = executor.Runner(root, chain.WORKSPACE / chain.WIRELESS, FREEZE, 'b'*64, lambda **value: None)
            child = runner.command(job)
            self.assertEqual(child['execution_kind'], 'subprocess_waited')
            self.assertEqual(child['returncode'], 0)
            self.assertEqual(child['schema'], chain.custody.SCHEMA_WAIT)
            self.assertTrue(child['passed'])
            self.assertIsNone(chain.preparation.primitives.identity(child['process_identity']['pid']))
            bindings = {}
            result = chain.check_waited_child(child, job, FREEZE, 'b'*64, child['launcher_identity'],
                child['coordinator_actual_argv'], chain.WORKSPACE, bindings)
            self.assertTrue(result['passed'])
            imposter = dict(job, argv=[sys.executable, '-c', 'pass'])
            with self.assertRaises(ValueError): chain.check_waited_child(child, imposter, FREEZE, 'b'*64,
                child['launcher_identity'], child['coordinator_actual_argv'], chain.WORKSPACE, {})

    def test_expired_deadline_submits_nothing_and_fabricates_no_child_returncode(self):
        executor, _ = chain.preparation.load_executor()
        class NoSubmit:
            def command(self, job): raise AssertionError('deadline submitted a child')
            def record(self, **value): pass
        completed, skipped = executor.run_audits([{'id': 'never', 'output': '/unused'}], NoSubmit(), time.monotonic_ns()-1)
        self.assertEqual(completed, {})
        self.assertEqual(skipped[0]['reason'], 'stage_wall_allocation_exhausted')
        self.assertNotIn('returncode', skipped[0])

    def test_real_finite_cpu_outer_wait_uses_actual_generic_schema_and_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'bound_source.txt'; source.write_bytes(b'finite CPU boundary only\n')
            output = root / 'outer'
            argv = [sys.executable, '-m', 'mr3_learning.reach_execution', '--output', str(output),
                '--scope', 'cpu', '--source', str(source), '--', sys.executable, '-c', 'print("finite CPU child")']
            result = subprocess.run(argv, cwd=chain.WORKSPACE / chain.WIRELESS, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((output / 'actual_wait.json').read_text())
            self.assertEqual(receipt['schema'], chain.OUTER_SCHEMA)
            self.assertTrue(receipt['actual_waited'])
            self.assertEqual(receipt['actual_returncode'], 0)
            self.assertEqual(receipt['source_before'], receipt['source_after'])
            self.assertEqual(Decimal(receipt['actual_child_wait_seconds']),
                Decimal(receipt['ended_monotonic_ns'] - receipt['started_monotonic_ns']) / 10**9)
            for saved in (receipt['child_identity'], receipt['coordinator_identity']):
                current = chain.preparation.primitives.identity(saved['pid'])
                self.assertTrue(current is None or current['start_ticks'] != saved['start_ticks'])

    def test_unstarted_child_cannot_have_real_returncode_or_pid(self):
        self.assertFalse(chain._same_identity({'pid': True, 'start_ticks': 1}, {'pid': 1, 'start_ticks': 1}))
        self.assertFalse(chain._same_identity({'pid': 1, 'start_ticks': 2}, {'pid': 1, 'start_ticks': 3}))
        self.assertTrue(chain._same_identity({'pid': 1, 'start_ticks': 2}, {'pid': 1, 'start_ticks': 2}))

    def test_failed_or_missing_closure_output_has_no_pass_fact(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'closure.json'
            for child in (None, {'passed': False, 'output': str(path)}, {'passed': True, 'output': str(path)}):
                self.assertFalse(chain.strict_custody_fact(child, {}))
            path.write_text(json.dumps({'schema': chain.custody.SCHEMA_CLOSURE, 'safety_contract': chain.CONTRACT,
                'passed': True, 'errors': [], 'all_native_owned_gone': True})+'\n')
            self.assertFalse(chain.strict_custody_fact({'passed': False, 'output': str(path)}, {}))
            self.assertTrue(chain.strict_custody_fact({'passed': True, 'output': str(path)}, {}))


if __name__ == '__main__':
    unittest.main()
