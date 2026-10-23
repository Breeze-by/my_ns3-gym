"""Tiny CPU fixtures: no Gazebo, compiler, child process, actor or original inputs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('v57_pair_fixture_driver', Path(__file__).with_name('run_passive_pair_v1.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DriverTests(unittest.TestCase):
    def scope_prefix(self):
        return {'schema': 'mr3-v57-passive-pair-scope-v1', 'admitted': True,
            'evidence_freeze': d.OLD, 'gazebo_master_uri': d.URI, 'arms': list(d.ARMS),
            'no_retry': True, 'per_case_outer_stop_seconds': 720,
            'interrupt_to_TERM_seconds': 10, 'TERM_to_KILL_seconds': 10,
            'budget': {'engineering_used_seconds': str(d.ENTRY),
                'engineering_ceiling_seconds': str(d.CEILING),
                'engineering_remaining_seconds': str(d.CEILING - d.ENTRY),
                'reservation_seconds': '1800', 'pilot_added_seconds': '0', 'validation_added_seconds': '0'}}

    def test_unadmitted_scope_never_submits(self):
        with patch.object(d.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'not admitted'):
                d.verify_inputs({'admitted': False}, 'a' * 40)
            popen.assert_not_called()

    def test_exact_budget_rejects_bool_and_old_ceiling(self):
        for value in (True, '75000'):
            scope = self.scope_prefix(); scope['budget']['engineering_ceiling_seconds'] = value
            with self.assertRaisesRegex(ValueError, 'entry budget'):
                d.verify_inputs(scope, 'a' * 40)

    def test_git_binding_rejects_different_full_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source.py'; source.write_bytes(b'whole current source\n')
            row = d.proof(source)
            with patch.object(d, 'ROOT', root), patch.object(d.subprocess, 'check_output', return_value=b'other Git source\n'):
                with self.assertRaisesRegex(ValueError, 'frozen bytes differ'):
                    d.git_bound(row, 'a' * 40)

    def test_partial_rc_survives_interrupted_wait_without_retry(self):
        class FakeChild:
            pid = 901
            calls = 0
            def wait(self, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise KeyboardInterrupt('fixture interruption')
                return 1
        child = FakeChild()
        owner = {'pid': 800, 'parent': 799, 'group': 799, 'session': 799, 'start_ticks': 1}
        wrapper = {'pid': 901, 'parent': 800, 'group': 901, 'session': 901, 'start_ticks': 2}
        native = {'pid': 902, 'parent': 901, 'group': 901, 'session': 901, 'start_ticks': 3}
        command = ['/fake/ELF', '--arm', 'quick150', '--world', '/fake/world', '--output', 'unused', '--work-seconds', '600']
        partial = {'execution_passed': False, 'actual_step_count': 7, 'identity': native}
        def fake_read(path, *args):
            if Path(path).name == 'actual_wait.json': return {'actual_returncode': 1, 'child_identity': native}
            if Path(path).name == 'summary.json': return partial
            return {'identity': native, 'actual_argv': command}
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            command[command.index('--output') + 1] = str(prefix / 'arms/quick150')
            with patch.object(d, 'PREFIX', prefix), patch.object(d, 'port_free'), \
                 patch.object(d, 'identity', return_value=wrapper), patch.object(d, 'capture_cpp', return_value=[]), \
                 patch.object(d, 'current', return_value=None), patch.object(d, 'read', side_effect=fake_read), \
                 patch.object(d, 'validate_case'), patch.object(d.subprocess, 'Popen', return_value=child) as popen:
                row, _, _ = d.run_case('quick150', {'elf': {'path': '/fake/ELF'}},
                    {'worlds': [{'arm': 'quick150', 'path': '/fake/world'}]}, [], owner, None, lambda: False)
            self.assertEqual(popen.call_count, 1)
            self.assertEqual(popen.call_args.kwargs['env']['HOME'], str(prefix / 'home'))
            self.assertNotIn('PYTHONPATH', popen.call_args.kwargs['env'])
            self.assertEqual(child.calls, 2)
            self.assertTrue(row['actual_wrapper_waited'])
            self.assertEqual(row['actual_wrapper_returncode'], 1)
            self.assertEqual(row['actual_CPP_returncode'], 1)
            self.assertEqual(row['actual_CPP_summary']['actual_step_count'], 7)
            self.assertFalse(row['execution_passed'])
            self.assertTrue(row['errors'])

    def test_continuous_pair_gap_and_overrun_fee_not_nested_sum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); prefix = root / 'run'; source = root / 'source'; source.write_bytes(b'bound')
            rows = [d.proof(source)]
            def fake_case(arm, *_args):
                # Native intervals could sum 200s; continuous parent includes gaps and is 1901s.
                return {'arm': arm, 'execution_passed': True, 'actual_wrapper_waited': True,
                        'CPP_identities_observed': []}, 1000000000, 101000000000 if arm == 'quick150' else 1902000000000
            with patch.object(d, 'PREFIX', prefix), patch.object(d, 'identity', return_value={'pid': 1}), \
                 patch.object(d, 'read', return_value={'build_manifest': {'path': '/fake/build'}}), \
                 patch.object(d, 'verify_inputs', return_value=({}, rows)), \
                 patch.object(d, 'port_free'), patch.object(d, 'run_case', side_effect=fake_case) as cases, \
                 patch.object(d, 'library_sources', return_value=[]), \
                 patch.object(d.time, 'monotonic_ns', return_value=10000000000), patch.object(d.signal, 'signal'):
                rc = d.main(['--freeze', 'a' * 40])
            result = json.loads((prefix / 'summary.json').read_text())
            self.assertEqual(cases.call_count, 2)
            self.assertEqual(rc, 1)
            self.assertFalse(result['within_pair_parent_cap'])
            self.assertEqual(result['engineering_added_parent_wall_seconds'], '1901')
            self.assertEqual(result['engineering_cumulative_seconds'], str(d.ENTRY + 1901))

    def test_baseline_radius_excess_is_valid_execution_measurement(self):
        wrapper = {'pid': 901, 'parent': 800, 'group': 901, 'session': 901, 'start_ticks': 2}
        native = {'pid': 902, 'parent': 901, 'group': 901, 'session': 901, 'start_ticks': 3}
        command = ['/fake/ELF', '--arm', 'quick150']
        wait = {'schema': 'mr3-reach-outer-actual-wait-v1', 'scope': 'engineering', 'actual_waited': True,
            'actual_returncode': 0, 'actual_argv': command, 'cwd': str(d.W), 'coordinator_identity': wrapper,
            'child_identity': native, 'started_monotonic_ns': 100, 'ended_monotonic_ns': 200,
            'actual_child_wait_seconds': '.0000001', 'source_before': [], 'source_after': [],
            'source_unchanged': True, 'passed': True, 'errors': []}
        result = {'schema': 'mr3-v57-passive-plant-result-v1', 'identity': native, 'actual_argv': command,
            'execution_passed': True, 'actual_step_count': 355000, 'completed_sim_ns': 355000000000,
            'update_end_calls': 355000, 'native_seed': 101, 'gazebo_shutdown_returned': True,
            'physics_seed_api': 'gazebo::physics::PhysicsEngine::SetSeed',
            'physics_seed_set_call_completed': True, 'physics_seed_readback_claimed': False,
            'first_update_end_clock_ns': 1000000, 'last_update_end_clock_ns': 355000000000,
            'received_signal': 0, 'completion_status': 'COMPLETE', 'errors': [], 'wall_seconds_to_shutdown': 2,
            'actual_physics_parameters': {'engine': 'ode', 'solver_type': 'quick', 'iters': 150,
                                          'max_step_size': .001, 'real_time_update_rate': 0},
            'robots': [{'robot': name, 'anchor_clock_ns': 45000000000, 'post_anchor_observations': 310001,
                        'within_R_observed': False}
                       for name in ('tb1', 'tb2', 'tb3')]}
        with tempfile.TemporaryDirectory() as directory:
            lib = Path(directory) / 'libfixture.so'; lib.write_bytes(b'library fixture only')
            sources = [d.proof(lib)]
            wait['source_before'] = wait['source_after'] = sources
            result['loaded_library_paths'] = [str(lib)]
            d.validate_case(wait, result, command, sources, wrapper, 1, 300, 0)
            result['identity'] = dict(native, start_ticks=99)
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                d.validate_case(wait, result, command, sources, wrapper, 1, 300, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
