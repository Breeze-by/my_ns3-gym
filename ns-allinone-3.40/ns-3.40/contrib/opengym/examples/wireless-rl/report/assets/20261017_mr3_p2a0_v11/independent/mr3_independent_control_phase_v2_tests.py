#!/usr/bin/env python3
"""Retain all58 old checks and exercise only the new actual-ACK-prefix gate."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__)
SPEC = importlib.util.spec_from_file_location('control_v2', HERE.with_name(
    'mr3_independent_control_phase_v2.py'))
V2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V2)
OLD_TEST_SHA = '9d89029457a7975d22dd78e8963a3b92ce1a16352d9db9355c995740a5e6eed3'
OLD_TEST = V2.OLD_PATH.with_name('mr3_independent_control_phase_v1_tests.py')
assert hashlib.sha256(OLD_TEST.read_bytes()).hexdigest() == OLD_TEST_SHA
TEST_SPEC = importlib.util.spec_from_file_location('pinned_v10_58_tests', OLD_TEST)
LEGACY = importlib.util.module_from_spec(TEST_SPEC)
TEST_SPEC.loader.exec_module(LEGACY)
RED = LEGACY.M
LEGACY.M = V2.BASE
InheritedCausalTests = LEGACY.CausalTests


def run_fixture(fixture, module):
    previous = LEGACY.M
    try:
        LEGACY.M = module
        return fixture.replay()
    finally:
        LEGACY.M = previous


def abandoned_negative():
    """Replay the V10 original standalone counterexample, preserving all58 data rules."""
    f = LEGACY.Fixture()
    stop_index = next(i for i, row in enumerate(f.worker) if row['kind'] == 'request'
                      and row['request']['operation'] == 'stop')
    stop_wall = f.worker[stop_index]['wall_monotonic_ns']
    target = 1_040_000_000
    request = {'schema': 'mr3-state-phase-request-v1', 'epoch': f.epoch,
               'request_id': 'abandoned_state', 'operation': 'commit',
               'target_time_ns': target}
    row = {'schema': 'mr3-controlled-execution-phase-v1', 'kind': 'request', 'epoch': f.epoch,
           'worker_physical_ns': target, 'worker_clock_ns': target,
           'wall_monotonic_ns': stop_wall-2, 'component': 'state', 'request': request}
    f.worker.insert(stop_index, row)
    f.info.append({'kind': 'state_phase_request', 'epoch': f.epoch, 'clock_ns': target,
                   'wall_monotonic_ns': stop_wall-1,
                   'payload': {'request': request, 'duplicate': False}})
    ack = f.ack('state', 'commit', target, 'abandoned_state', error='state_phase_target_passed')
    ack.update(ok=False, clock_ns=1_060_000_000)
    f.iack(ack)
    f.wrow('ack_received', 1_060_000_000, component='state', ack=ack)
    return f, ack


def write_fixture(directory, fixture):
    files = {'metadata.json': {'epoch': fixture.epoch, 'freeze': 'synthetic-freeze'},
             'summary.json': {}, 'transitions.jsonl': [], 'physics.jsonl': fixture.physics,
             'information_states.jsonl': fixture.info, 'peer_phase.jsonl': fixture.peer,
             'motion_safety.jsonl': fixture.motion, 'control_phase_worker.jsonl': fixture.worker,
             'drive_phase_worker.jsonl': fixture.drive,
             **{'drive_'+r+'.jsonl': fixture.native[r] for r in RED.ROBOTS}}
    for name, value in files.items():
        data = (''.join(json.dumps(row)+'\n' for row in value) if name.endswith('jsonl')
                else json.dumps(value))
        (directory/name).write_text(data)


class StickyExtensionTests(unittest.TestCase):
    def test_original_standalone_counterexample_red_green(self):
        fixture, _ = abandoned_negative()
        red = run_fixture(fixture, RED)
        self.assertEqual(red['permanent_stop_advances'], 1)
        with self.assertRaisesRegex(ValueError, 'sticky, including abandoned'):
            run_fixture(fixture, V2.BASE)

    def test_actual_worker_wrapper_rejects_same_counterexample(self):
        fixture, ack = abandoned_negative()
        path = V2.ROOT/'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py'
        tree = ast.parse(path.read_text())
        method = next(method for node in tree.body if isinstance(node, ast.ClassDef)
                      for method in node.body if isinstance(method, ast.FunctionDef)
                      and method.name == 'receive_control_phase')
        namespace = {'canonical': lambda value: json.dumps(value, sort_keys=True)}
        module = ast.Module(body=[method], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
        from types import SimpleNamespace
        worker = SimpleNamespace(epoch=fixture.epoch, _trace_control_phase=lambda *a, **k: None)
        with self.assertRaisesRegex(RuntimeError, 'actual controlled execution failure'):
            namespace['receive_control_phase'](worker, 'state', ack)

    def test_full_audit_and_cli_red_green_preserve_peer_scope(self):
        fixture, _ = abandoned_negative()
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_fixture(directory, fixture)
            self.assertTrue(RED.audit(directory, 'synthetic-freeze')['passed'])
            result = V2.audit(directory, 'synthetic-freeze')
            self.assertFalse(result['passed'])
            self.assertIn('sticky, including abandoned', result['episodes'][0]['errors'][0])
            self.assertTrue(V2.audit(directory, 'synthetic-freeze', True)['passed'])
            output = directory/'result.json'
            call = subprocess.run([sys.executable, str(HERE.with_name(
                'mr3_independent_control_phase_v2.py')), str(directory),
                '--freeze', 'synthetic-freeze', '--output', str(output)],
                capture_output=True, text=True)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertFalse(json.loads(output.read_text())['passed'])
            inherited = json.loads(output.read_text())['inherited_reader']
            self.assertEqual(inherited['sha256'], V2.OLD_SHA)

    def test_actual_pending_negative_callback_cannot_wait_for_ack_rejected_row(self):
        fixture, _ = abandoned_negative()
        row = fixture.worker[-1]
        for component in ('state', 'peer', 'motion'):
            candidate = copy.deepcopy(row)
            candidate['component'] = component
            with self.assertRaisesRegex(ValueError, 'real control failure'):
                V2.check_sticky_negative_callback(candidate, fixture.epoch)

    def test_negative_typed_boolean_required(self):
        fixture, _ = abandoned_negative()
        for value in (0, 0., None, 'false', [], {}):
            row = copy.deepcopy(fixture.worker[-1])
            row['ack']['ok'] = value
            with self.assertRaisesRegex(ValueError, 'typed boolean'):
                V2.check_sticky_negative_callback(row, fixture.epoch)

    def test_terminal_candidate_still_needs_original_actual_notice_matching(self):
        fixture, _ = abandoned_negative()
        row = fixture.worker[-1]
        ack = row['ack']
        ack.update(error='state_phase_task_terminal',
                   scope='terminal_cancelled_uncommitted_state_phase',
                   terminal_notice={'epoch': fixture.epoch, 'end_sim_time_sec': 1.04,
                                    'termination_reason': 'navigation_failure'})
        V2.check_sticky_negative_callback(row, fixture.epoch)
        with self.assertRaisesRegex(ValueError, 'no actual prior information notice'):
            run_fixture(fixture, V2.BASE)

    def test_terminal_exception_cannot_be_relabelled_to_peer_or_wrong_scope(self):
        fixture, _ = abandoned_negative()
        row = fixture.worker[-1]
        row['ack'].update(error='state_phase_task_terminal',
                          scope='terminal_cancelled_uncommitted_state_phase',
                          terminal_notice={})
        row['component'] = 'peer'
        with self.assertRaisesRegex(ValueError, 'real control failure'):
            V2.check_sticky_negative_callback(row, fixture.epoch)
        row['component'] = 'state'
        row['ack']['scope'] = 'ordinary_timeout'
        with self.assertRaisesRegex(ValueError, 'real control failure'):
            V2.check_sticky_negative_callback(row, fixture.epoch)

    def test_cross_epoch_ignored_raw_callback_gains_no_receipt_credit(self):
        fixture, _ = abandoned_negative()
        row = copy.deepcopy(fixture.worker[-1])
        row['ack']['epoch'] = 'other-epoch'
        V2.check_sticky_negative_callback(row, fixture.epoch)
        normal = LEGACY.Fixture()
        normal.worker.append(row)
        run_fixture(normal, V2.BASE)

    def test_inherited_files_unchanged(self):
        self.assertEqual(hashlib.sha256(V2.OLD_PATH.read_bytes()).hexdigest(), V2.OLD_SHA)
        self.assertEqual(hashlib.sha256(OLD_TEST.read_bytes()).hexdigest(), OLD_TEST_SHA)


if __name__ == '__main__':
    unittest.main()
