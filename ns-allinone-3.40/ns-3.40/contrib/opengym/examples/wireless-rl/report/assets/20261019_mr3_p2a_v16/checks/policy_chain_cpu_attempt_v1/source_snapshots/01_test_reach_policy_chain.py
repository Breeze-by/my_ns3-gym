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
import unittest

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


if __name__ == '__main__':
    unittest.main()
