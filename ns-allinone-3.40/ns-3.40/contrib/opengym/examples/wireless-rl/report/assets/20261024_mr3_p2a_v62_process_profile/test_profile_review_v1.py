"""Closed synthetic receipts/pstats only; no native sources or ROS nodes execute."""
import cProfile
import hashlib
import json
import marshal
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import fixed_integration_v1 as integration
import fixed_process_profile_v1 as core
import review_profile_v1 as reviewer

HERE = Path(__file__).resolve().parent


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


class ProfileReviewTests(unittest.TestCase):
    def test_finite_pstats_and_exact_start_including_zombie(self):
        profile = cProfile.Profile()
        profile.runcall(sum, range(12))
        value = reviewer.pstats_description(self.table(profile))
        self.assertGreater(value['function_count'], 0)
        with self.assertRaises(ValueError):
            reviewer.pstats_description(marshal.dumps({}))
        with tempfile.TemporaryDirectory(prefix='v62-proc-artificial-') as name:
            root = Path(name)
            path = root / '17/stat'
            path.parent.mkdir()
            # stat tail[19] is start_ticks; same-start Z is still present.
            path.write_text('17 (synthetic) Z ' + ' '.join(['0'] * 18 + ['41']) + '\n')
            evidence = SimpleNamespace(identities={(17, 41): [{'synthetic': True}], (18, 42): []})
            rows = reviewer.fresh_saved_identities(evidence, root)
            self.assertFalse(rows[0]['gone'])
            self.assertTrue(rows[1]['gone'])
            path.write_text('17 (synthetic) S ' + ' '.join(['0'] * 18 + ['99']) + '\n')
            self.assertTrue(reviewer.fresh_saved_identities(evidence, root)[0]['gone'])

    @staticmethod
    def table(profile):
        with tempfile.TemporaryDirectory(prefix='v62-pstats-artificial-') as name:
            path = Path(name) / 'one.pstats'
            profile.dump_stats(path)
            return path.read_bytes()

    def test_full_metadata_route_and_missing_thread_profile_fail_closed(self):
        # All bytes below are synthetic fixture copies. They are never native evidence.
        with tempfile.TemporaryDirectory(prefix='v62-closed-artificial-') as name:
            root = Path(name)
            asset, run, driver = root / 'asset', root / 'run', root / 'driver'
            asset.mkdir(); run.mkdir(); driver.mkdir()
            epoch, freeze = 'synthetic-v62-epoch', 'a' * 40
            episode = run / 'native/worker0/episode001_open_101'
            episode.mkdir(parents=True)
            # The real immutable A16 parser is copied as source, not run on real evidence.
            a16 = root / 'a16.py'
            shutil.copyfile(reviewer.A16, a16)
            sources = {}
            for path in [integration.SUPERVISOR, integration.WORKER, *[v[0] for v in core.SOURCES.values()]]:
                target = root / path.relative_to(integration.ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                sources[str(target)] = {'bytes': target.stat().st_size,
                                        'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
            programs = {}
            for role, path in core.PROGRAMS.items():
                target = root / path.relative_to(integration.ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copyfile(path, target)
                programs[role] = target
            pinned = {role: (root / path.relative_to(integration.ROOT), digest)
                      for role, (path, digest) in core.SOURCES.items()}
            write(asset / 'base_source_pins_v1.json', {'sources': sources})
            write(asset / 'scope_v1.json', {'diagnostic_profile': reviewer.PROFILE, 'run_root': str(run),
                'resource': dict(parent_cap_seconds=1800, native_allocation_seconds=1500,
                                 close_reserve_seconds=120, review_max_seconds=300)})
            before = time.monotonic_ns() - 10**9
            argv = ['/usr/bin/python3', '-B', 'synthetic_launcher.py']
            write(driver / 'entry.json', {'freeze': freeze, 'complete_parent_started_monotonic_ns': before,
                                          'actual_expected_launcher_argv': argv})
            write(driver / 'execution.json', {'schema': 'mr3-v62-profile-execution-v1', 'launcher': {
                'actual_argv': argv, 'identity': {'pid': 90000001, 'start_ticks': 1},
                'actual_waited': True, 'actual_returncode': 0, 'wait_errors': [], 'signals': [],
                'started_monotonic_ns': before + 1, 'ended_monotonic_ns': before + 2}})
            write(run / 'launcher.json', {'freeze': freeze, 'diagnostic_profile': reviewer.PROFILE,
                'scientific_qualification': False, 'capacity_qualified': False, 'nav2_parameter_readback_taken': False})
            identities = {role: {'pid': 90000002 + i, 'start_ticks': i + 2}
                          for i, role in enumerate(reviewer.LANES)}
            shutdown = {'epoch': epoch, 'worker_returncode': 0, 'forced_shutdown': False, 'failed_sample': False,
                        'remaining_owned_processes': [], 'remaining_owned_zombies': [],
                        'owned_processes_seen': list(identities.values())}
            worker = {'worker_id': 0, 'error': None, 'episodes': [{
                'epoch': epoch, 'scene': 'open', 'seed': 101, 'transitions': 8, 'truncated': True,
                'terminated': False, 'output_directory': str(episode)}]}
            summary = {'passed': True, 'workers': 1, 'valid_transitions': 8, 'steps_per_episode': 8,
                'schedule': [['open', 101]], 'freeze': freeze, 'actuation_profile': 'initial-zero-encoder-hold-v1',
                'preparation_motion_probe': False, 'training_eligible': False, 'workers_results': [worker]}
            for path, value in [(run / 'native/benchmark_metadata.json', {}),
                (run / 'native/benchmark_summary.json', summary), (run / 'native/worker0/worker_summary.json', worker),
                (episode / 'metadata.json', {}), (episode / 'supervisor_metadata.json', {}),
                (episode / 'supervisor_shutdown.json', shutdown), (episode / 'summary.json', {
                    'epoch': epoch, 'transition_count': 8, 'launch_returncode': 0, 'native_failures': [],
                    'closed': {'pending_goal_count': 0}}),
                (episode / 'nav2_shutdown.json', {}), (episode / 'native_stop.json', {})]:
                write(path, value)
            for role, lanes in reviewer.LANES.items():
                directory = episode / 'profiles' / role
                directory.mkdir(parents=True)
                program_argv = [str(programs[role])]
                receipts = {'profile_id': reviewer.PROFILE, 'role': role, 'identity': identities[role], 'parameters': []}
                write(directory / 'started.json', {**receipts, 'program_argv': program_argv,
                    'actual_argv': ['/usr/bin/python3', '-B', str(asset / 'fixed_roles_entry_v1.py'), *program_argv],
                    'sources': {str(programs[role]): {'sha256': core.PROGRAM_SHA256[role]},
                                str(pinned[role][0]): {'sha256': pinned[role][1]}}})
                profiles = []
                for lane in lanes:
                    profile = cProfile.Profile()
                    profile.runcall(sum, range(8))
                    path = directory / (lane + '.pstats')
                    profile.dump_stats(path)
                    raw = path.read_bytes()
                    profiles.append({'lane': lane, 'path': str(path), 'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest(), 'thread_exit_observed': lane != 'main', 'calls': 1})
                write(directory / 'finished.json', {**receipts, 'profile_complete': True,
                    'source_stable': True, 'profile_errors': [], 'scientific_qualification': False,
                    'profiles': profiles, 'process_cpu_ns': 1000, 'started_monotonic_ns': before,
                    'ended_monotonic_ns': before + 1})
                if role != 'worker':
                    write(directory / 'console_resolution.json', {'role': role,
                        'source_sha256': pinned[role][1], 'source_path': str(pinned[role][0].resolve()),
                        'loaded_function_is_bound_module_main': True})
            write(episode / 'profiles/adapter/encoder_hook.json', {'source_sha256': pinned['adapter'][1]})
            supervisor = root / integration.SUPERVISOR.relative_to(integration.ROOT)
            worker_source = root / integration.WORKER.relative_to(integration.ROOT)
            args = SimpleNamespace(run=run, driver=driver, scope=asset / 'scope_v1.json',
                                   output=driver / 'profile_review_v1.json', freeze=freeze)
            def git(values, *, cwd):
                if values[1] == 'rev-parse': return (freeze + '\n').encode()
                if values[1] == 'status': return b''
                if values[1] == 'show': return (root / values[2].split(':', 1)[1]).read_bytes()
                raise AssertionError(values)
            with mock.patch.multiple(reviewer, HERE=asset, CANONICAL=asset, ROOT=root, RUN=run, DRIVER=driver, A16=a16), \
                 mock.patch.multiple(integration, HERE=asset, ROOT=root, RUN=run, ENTRY=asset/'fixed_roles_entry_v1.py',
                                     SUPERVISOR=supervisor, WORKER=worker_source), \
                 mock.patch.multiple(core, OWNED_EPISODE=episode, PROGRAMS=programs, SOURCES=pinned), \
                 mock.patch.object(reviewer.subprocess, 'check_output', side_effect=git):
                for source, directory in [(supervisor, run / 'supervisor_projection'),
                    (worker_source, episode / 'profiles/worker/source_projection')]:
                    raw = source.read_bytes()
                    changed, edits = integration.project(source, raw)
                    integration.preserve_projection(directory, source, raw, changed, edits)
                result = reviewer.review(args)
                self.assertTrue(result['passed'], result['errors'])
                self.assertEqual(sum(len(v['profiles']) for v in result['roles'].values()), 5)
                self.assertFalse(result['capacity_qualified'])
                path = episode / 'profiles/worker/ros_spin.pstats'
                path.unlink()
                result = reviewer.review(args)
                self.assertFalse(result['passed'])
                self.assertTrue(result['partial'])
                self.assertFalse(result.get('all_saved_identities_fresh_gone', False))


if __name__ == '__main__':
    unittest.main()
