"""Pure stdlib admission/cleanup regressions; never starts benchmark/ROS/Gazebo."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
DRAFT = Path(__file__).resolve().parent
PLAN = DRAFT / 'predeclared_plan_v11.json'
if not PLAN.exists():
    PLAN = DRAFT.parent / 'predeclared_plan_v11.json'
ROOT = Path('/home/zhuyulab/ns3-workspace')
OLD = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
              'report/assets/20261017_mr3_p2a0_v8')
spec = importlib.util.spec_from_file_location(
    'v11launcher', DRAFT / 'mr3_p2a0_v11_launch_stage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FREEZE = 'f' * 40


class AdmissionTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mr3v11_cpu_')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.old_temp = m.TEMP
        m.TEMP = self.root
        self.addCleanup(setattr, m, 'TEMP', self.old_temp)
        self.plan = {
            'max_total_wall_seconds': 18000,
            'stages': [{'stage': name, 'wall_ceiling_seconds': ceiling,
                        'run_directory': str(self.root / name),
                        'required_audit_receipts': [str(self.root / (name + '_formal.json'))]}
                       for (name, ceiling) in [('interface', 1800), ('terminal', 1800),
                                               ('reset', 6400), ('deadline', 8000)]]}

    def receipt(self, index, **overrides):
        st = self.plan['stages'][index]
        run = Path(st['run_directory'])
        run.mkdir()
        (run / 'benchmark_summary.json').write_text(json.dumps({'passed': True, 'freeze': FREEZE}))
        Path(st['required_audit_receipts'][0]).write_text(
            json.dumps({'passed': True, 'freeze': FREEZE}))
        r = {'freeze': FREEZE, 'stage': st['stage'], 'status': 'completed',
             'returncode': 0, 'passed': True,
             'wall_duration_sec': st['wall_ceiling_seconds']}
        r.update(overrides)
        (self.root / ('mr3_p2a0_v11_' + st['stage'] + '_launch.json')).write_text(json.dumps(r))

    def test_fresh_stage_admitted_with_full_reserved_ceiling(self):
        (st, budget) = m.launch_admission(self.plan, 'interface', FREEZE)
        self.assertEqual(st['stage'], 'interface')
        self.assertEqual(budget['remaining_before_stage_seconds'], 18000)

    def test_same_stage_or_later_attempt_prevents_retry(self):
        for name in ('interface', 'deadline'):
            path = self.root / ('mr3_p2a0_v11_' + name + '_launch.json')
            path.write_text('{}')
            with self.assertRaisesRegex(AssertionError, 'already attempted'):
                m.launch_admission(self.plan, 'interface', FREEZE)
            path.unlink()

    def test_failed_incomplete_or_over_ceiling_predecessor_rejected(self):
        for override in ({'passed': False}, {'returncode': 1}, {'status': 'running'},
                         {'wall_duration_sec': 1800.0000001}):
            with self.subTest(override=override):
                self.receipt(0, **override)
                with self.assertRaises(AssertionError):
                    m.launch_admission(self.plan, 'terminal', FREEZE)
                import shutil
                shutil.rmtree(self.root / 'interface')
                (self.root / 'mr3_p2a0_v11_interface_launch.json').unlink()
                (self.root / 'interface_formal.json').unlink()

    def test_formal_missing_false_or_wrong_freeze_rejected(self):
        self.receipt(0)
        path = self.root / 'interface_formal.json'
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            m.launch_admission(self.plan, 'terminal', FREEZE)
        for receipt in ({'passed': False, 'freeze': FREEZE}, {'passed': True, 'freeze': '0' * 40}):
            path.write_text(json.dumps(receipt))
            with self.assertRaises(AssertionError):
                m.launch_admission(self.plan, 'terminal', FREEZE)

    def test_each_previous_formal_is_required_and_exact_budget_is_allowed(self):
        for index in range(3):
            self.receipt(index)
        (_, budget) = m.launch_admission(self.plan, 'deadline', FREEZE)
        self.assertEqual(budget['remaining_before_stage_seconds'], 8000)
        self.assertEqual(len(budget['preceding_formal_receipts']), 6)

    def test_insufficient_budget_or_existing_run_rejected(self):
        self.plan['max_total_wall_seconds'] = 1799
        with self.assertRaisesRegex(AssertionError, 'insufficient'):
            m.launch_admission(self.plan, 'interface', FREEZE)
        self.plan['max_total_wall_seconds'] = 18000
        (self.root / 'interface').mkdir()
        with self.assertRaisesRegex(AssertionError, 'already exists'):
            m.launch_admission(self.plan, 'interface', FREEZE)


class LauncherCleanupTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mr3v11_cleanup_cpu_')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.asset = self.root / 'asset'
        self.asset.mkdir()
        self.wireless = self.root / 'wireless'
        self.wireless.mkdir()
        self.run = self.root / 'run'
        self.plan = {
            'schema': 'mr3-p2a0-predeclaration-v11', 'max_total_wall_seconds': 18000,
            'stages': [{'stage': 'interface', 'command': ['python', '-m', 'fake_benchmark'],
                        'wall_ceiling_seconds': 1800, 'run_directory': str(self.run),
                        'required_audit_receipts': []}]}
        raw = (json.dumps(self.plan) + '\n').encode()
        (self.asset / 'predeclared_plan_v11.json').write_bytes(raw)
        (self.root / 'mr3_p2a0_v11_source_preflight.json').write_text(
            json.dumps({'passed': True, 'freeze': FREEZE,
                        'plan_sha256': hashlib.sha256(raw).hexdigest()}))
        self.fake = types.ModuleType('mr3_learning.supervisor')
        self.fake.process_identity = (
            lambda pid: None if pid == 999999 else {'pid': pid, 'start_ticks': 1})
        self.process = types.SimpleNamespace(pid=999999, wait=self.wait)
        self.waits = 0
        self.write_summary = True

    def wait(self):
        self.waits += 1
        if self.write_summary:
            self.run.mkdir(exist_ok=True)
            (self.run / 'benchmark_summary.json').write_text(
                json.dumps({'passed': True, 'freeze': FREEZE}))
        return 0

    def call(self, print_hook=None, popen_error=None):

        def git(argv, **kwargs):
            return '' if argv[1:] == ['status', '--porcelain'] else FREEZE + '\n'
        with contextlib.ExitStack() as stack:
            for (key, value) in [('ASSET', self.asset), ('TEMP', self.root),
                                 ('WIRELESS', self.wireless)]:
                stack.enter_context(patch.object(m, key, value))
            stack.enter_context(patch.object(m.sys, 'argv', ['launcher', 'interface', FREEZE]))
            stack.enter_context(patch.dict(sys.modules, {'mr3_learning.supervisor': self.fake}))
            stack.enter_context(patch.object(m.subprocess, 'check_output', side_effect=git))
            popen = stack.enter_context(patch.object(
                m.subprocess, 'Popen', side_effect=popen_error, return_value=self.process))
            if print_hook:
                stack.enter_context(patch('builtins.print', side_effect=print_hook))
            else:
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return (m.main(), popen)

    def result(self):
        return json.loads((self.root / 'mr3_p2a0_v11_interface_launch.json').read_text())

    def test_normal_wait_and_success_are_recorded(self):
        (code, _) = self.call()
        self.assertEqual(code, 0)
        self.assertEqual(self.waits, 1)
        self.assertTrue(self.result()['passed'])
        self.assertEqual(self.result()['status'], 'completed')

    def test_post_spawn_reporting_error_waits_same_child_and_keeps_failure(self):

        def broken(*args, **kwargs):
            raise BrokenPipeError('observer stdout closed')
        with self.assertRaises(BrokenPipeError):
            self.call(print_hook=broken)
        r = self.result()
        self.assertFalse(r['passed'])
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(self.waits, 1)
        self.assertEqual(r['exception_owned_cleanup']['benchmark_parent_pid'], 999999)
        self.assertEqual(r['exception_owned_cleanup']['returncode'], 0)
        with self.assertRaisesRegex(AssertionError, 'already attempted'):
            self.call()

    def test_pre_spawn_failure_records_failed_reservation_without_wait(self):
        with self.assertRaises(OSError):
            self.call(popen_error=OSError('synthetic spawn failure'))
        self.assertEqual(self.waits, 0)
        self.assertEqual(self.result()['status'], 'failed')
        self.assertFalse(self.result()['passed'])

    def test_missing_summary_remains_failure_and_child_is_reaped(self):
        self.write_summary = False
        with self.assertRaises(FileNotFoundError):
            self.call()
        r = self.result()
        self.assertFalse(r['passed'])
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['exception_owned_cleanup']['returncode'], 0)
        self.assertGreaterEqual(self.waits, 1)


class VersioningTests(unittest.TestCase):

    def test_all_old_27_bindings_and_gates_preserved(self):
        old = json.loads((OLD / 'predeclared_plan_v8.json').read_text())
        new = json.loads(PLAN.read_text())
        self.assertEqual(new['independent_source_bindings'][:27],
                         old['independent_source_bindings'])
        old_v9 = json.loads((ROOT / (
            'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
            'report/assets/20261017_mr3_p2a0_v9/predeclared_plan_v9.json')).read_text())
        self.assertEqual(new['independent_source_bindings'][:33],
                         old_v9['independent_source_bindings'])
        self.assertEqual(new['unchanged_gates'], old['unchanged_gates'])
        self.assertEqual(new['pilot_budget_unchanged'], old['pilot_budget_unchanged'])
        budget_fields = ('max_total_wall_seconds', 'max_api_records',
                         'max_submitted_script_decisions')
        self.assertEqual([new[k] for k in budget_fields], [18000, 608, 596])
        for (a, b) in zip(old['stages'], new['stages']):
            self.assertTrue(set(a['required_audits']).issubset(b['required_audits']))
            self.assertEqual(a['wall_ceiling_seconds'], b['wall_ceiling_seconds'])
            self.assertEqual(a['stage'], b['stage'])
            self.assertEqual(a['command'][a['command'].index('--steps') + 1],
                             b['command'][b['command'].index('--steps') + 1])
            self.assertEqual(b['required_audit_receipts'][-1],
                             '/tmp/mr3_p2a0_v11_' + b['stage'] + '_control_review_v1.json')

    def test_domains_ports_distinct_and_bindings_exact(self):
        new = json.loads(PLAN.read_text())
        self.assertEqual([(s['worker_bindings'][0]['domain'], s['worker_bindings'][0]['port'])
                          for s in new['stages']],
                         [(120, 13101), (122, 13111), (124, 13121), (128, 13131)])
        for b in new['independent_source_bindings'][33:]:
            self.assertEqual(
                hashlib.sha256((ROOT / b['path']).read_bytes()).hexdigest(),
                b['sha256'])

    def test_preflight_keeps_old_checks_and_requires_information_ready(self):
        old = (OLD / 'independent/mr3_p2a0_v8_buildproof_preflight.py').read_text()
        new = (DRAFT / 'mr3_p2a0_v11_buildproof_preflight.py').read_text()
        ready_gate = ('    assert plan[\"information_selection_audit\"][\"status\"] '
                      '== \"ready\", \\\n'
                      '        \"information consumer/schema/bindings not frozen\"\n')
        self.assertIn(ready_gate, new)
        new = new.replace(ready_gate, '')
        control_gate = ready_gate.replace(
            'information_selection_audit', 'controlled_execution_audit')
        control_gate = control_gate.replace(
            'information consumer', 'controlled execution consumer')
        self.assertIn(control_gate, new)
        new = new.replace(control_gate, '')
        self.assertEqual(
            new.replace('mr3_p2a0_v11', 'mr3_p2a0_v8')
            .replace('predeclared_plan_v11', 'predeclared_plan_v8')
            .replace('predeclaration-v11', 'predeclaration-v8')
            .replace('/tmp v11 receipts', '/tmp v8 receipts'), old)


if __name__ == '__main__':
    unittest.main(verbosity=2)
