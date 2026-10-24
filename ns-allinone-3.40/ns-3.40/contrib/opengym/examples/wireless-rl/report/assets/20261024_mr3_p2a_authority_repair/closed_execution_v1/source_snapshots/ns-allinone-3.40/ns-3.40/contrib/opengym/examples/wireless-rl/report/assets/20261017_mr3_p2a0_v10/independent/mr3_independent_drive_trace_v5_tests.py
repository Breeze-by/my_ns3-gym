"""Immutable v4's full mutation suite plus explicit permanent-stop mutations."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('drive_v5',
                                             Path(__file__).with_name('mr3_independent_drive_trace_v5.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
SPEC = importlib.util.spec_from_file_location('immutable_drive_tests',
                                             M.LEGACY.with_name('mr3_independent_drive_trace_v4_tests.py'))
OLD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OLD)
OLD.M = M.BASE
EPOCH = OLD.EPOCH


def stop_fixture():
    rows = []

    def add(kind, payload, clock=100_000_000):
        value = {'schema': 'mr3-motion-safety-v1', 'epoch': EPOCH,
                 'record_sequence': len(rows) + 1, 'kind': kind,
                 'wall_monotonic_ns': 1000 + (len(rows) + 1) * 100,
                 'sim_time_sec': clock / 1e9, 'payload': payload}
        rows.append(value)
        return value

    def outputs(clock, sequence, stop):
        for name in M.ROBOTS:
            add('decision', {'robot': name, 'clock_ns': clock, 'decision_sequence': sequence,
                            'started': True, 'ready': not stop,
                            'decision': {'output': [0., 0.] if stop else [.1, .2]},
                            **({'phase_kind': 'stop'} if stop else {})}, clock)
        if stop:
            for name in M.ROBOTS:
                add('actual_cmd_vel', {'robot': name, 'observed_decision_sequence': sequence,
                    'twist': {'linear': dict.fromkeys(('x', 'y', 'z'), 0.),
                              'angular': dict.fromkeys(('x', 'y', 'z'), 0.)},
                    'publisher_identity': {'valid': True, 'scope': 'graph_at_callback',
                        'topic': f'/{name}/cmd_vel', 'endpoints': [
                            {'namespace': '/', 'node': 'motion_safety',
                             'topic_type': 'geometry_msgs/msg/Twist', 'endpoint_gid': '01' * 24}]}}, clock)
            wall = 1000 + (len(rows) + 1) * 100
            add('output_completed', {'status': {
                'schema': 'mr3-motion-safety-status-v1', 'epoch': EPOCH,
                'clock_ns': clock, 'ready': False, 'phase_kind': 'stop',
                'completion_scope': 'publication_and_local_topic_receipt',
                'decision_sequences': dict.fromkeys(M.ROBOTS, sequence),
                'outputs': {name: {'linear_x': 0., 'angular_z': 0.} for name in M.ROBOTS}},
                'publish_started_wall_monotonic_ns': wall - 2,
                'publish_completed_wall_monotonic_ns': wall - 1}, clock)

    outputs(100_000_000, 1, False)
    add('control_request', {'schema': 'mr3-motion-control-request-v1', 'epoch': EPOCH,
        'request_id': 'stop100000000', 'target_time_ns': 100_000_000, 'operation': 'stop'})
    outputs(100_000_000, 2, True)
    outputs(120_000_000, 3, True)
    return rows


class StopTests(unittest.TestCase):
    def setUp(self):
        self.rows = stop_fixture()

    def parse(self, rows=None):
        return M.guard_outputs(self.rows if rows is None else rows, EPOCH, 100_000_000)

    def mutate(self, kind, change, index=0):
        rows = copy.deepcopy(self.rows)
        change([row for row in rows if row['kind'] == kind][index]['payload'])
        return rows

    def test_explicit_same_clock_stop_with_real_zero_self_receipts_passes(self):
        result = self.parse()
        self.assertEqual(result['tb1'][0]['output'], [.1, .2])
        self.assertEqual(result['tb1'][1]['phase_kind'], 'stop')
        self.assertEqual(result['tb1'][0]['clock_ns'], result['tb1'][1]['clock_ns'])

    def test_stopping_tag_without_prior_real_cause_rejected(self):
        rows = [row for row in copy.deepcopy(self.rows) if row['kind'] != 'control_request']
        for index, row in enumerate(rows, 1):
            row['record_sequence'] = index
        with self.assertRaisesRegex(ValueError, 'prior cause'):
            self.parse(rows)

    def test_nonzero_or_ready_stop_rejected(self):
        for change in (lambda p: p['decision'].update(output=[.001, 0.]),
                       lambda p: p.update(ready=True), lambda p: p.update(phase_kind='other')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.parse(self.mutate('decision', change, index=3))

    def test_unmarked_postrelease_same_clock_still_rejected(self):
        with self.assertRaises(ValueError):
            self.parse(self.mutate('decision', lambda p: p.pop('phase_kind'), index=3))

    def test_normal_resumption_after_stop_rejected_even_if_zero(self):
        with self.assertRaisesRegex(ValueError, 'normal decision after'):
            self.parse(self.mutate('decision', lambda p: p.pop('phase_kind'), index=6))

    def test_stop_sequences_and_clock_cannot_regress(self):
        for change in (lambda p: p.update(decision_sequence=1),
                       lambda p: p.update(clock_ns=99_000_000)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.parse(self.mutate('decision', change, index=3))

    def test_stop_whole_twist_and_actual_graph_identity_are_required(self):
        for change in (lambda p: p['twist']['linear'].update(y=.001),
                       lambda p: p['publisher_identity'].update(valid=False),
                       lambda p: p['publisher_identity'].update(topic='/tb2/cmd_vel'),
                       lambda p: p.update(observed_decision_sequence=99)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.parse(self.mutate('actual_cmd_vel', change))

    def test_missing_actual_self_receipt_cannot_make_completed_status(self):
        rows = copy.deepcopy(self.rows)
        removed = next(row for row in rows if row['kind'] == 'actual_cmd_vel')
        rows.remove(removed)
        for index, row in enumerate(rows, 1):
            row['record_sequence'] = index
        with self.assertRaises(ValueError):
            self.parse(rows)

    def test_stop_status_must_bind_all_three_actual_zero_decisions(self):
        for change in (lambda p: p['status']['outputs']['tb1'].update(angular_z=.01),
                       lambda p: p['status']['decision_sequences'].update(tb2=1),
                       lambda p: p['status'].update(ready=True)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.parse(self.mutate('output_completed', change))

    def test_actual_callback_channel_keeps_original_normal_status_immutable(self):
        guards = self.parse()
        normal = {'schema': 'mr3-motion-safety-status-v1', 'epoch': EPOCH,
                  'clock_ns': 100_000_000, 'ready': True,
                  'completion_scope': 'publication_and_local_topic_receipt',
                  'decision_sequences': dict.fromkeys(M.ROBOTS, 1),
                  'outputs': {name: {'linear_x': .1, 'angular_z': .2} for name in M.ROBOTS}}
        stop = next(row['payload']['status'] for row in self.rows if row['kind'] == 'output_completed')
        motion = [{'kind': 'ack_received', 'epoch': EPOCH, 'ack': normal}]
        control = [{'kind': 'stop_observed', 'epoch': EPOCH, 'origin': 'stop_topic', 'status': stop}]
        self.assertTrue(M.stop_worker_bindings(motion, control, guards, EPOCH)['passed'])
        motion.append({'kind': 'ack_received', 'epoch': EPOCH, 'ack': stop})
        with self.assertRaisesRegex(ValueError, 'overwrote normal'):
            M.stop_worker_bindings(motion, control, guards, EPOCH)
        motion.pop()
        motion[0]['ack']['outputs']['tb1']['linear_x'] = 0.
        with self.assertRaisesRegex(ValueError, 'changed actual guard output'):
            M.stop_worker_bindings(motion, control, guards, EPOCH)

    def test_control_ack_stop_needs_actual_preceding_ack_callback(self):
        guards = self.parse()
        stop = next(row['payload']['status'] for row in self.rows if row['kind'] == 'output_completed')
        control = [{'kind': 'stop_observed', 'epoch': EPOCH, 'origin': 'control_ack', 'status': stop}]
        with self.assertRaisesRegex(ValueError, 'no actual control ACK'):
            M.stop_worker_bindings([], control, guards, EPOCH)
        control.insert(0, {'kind': 'ack_received', 'epoch': EPOCH, 'component': 'motion',
                           'ack': {'schema': 'mr3-motion-control-ack-v1', 'epoch': EPOCH,
                                   'request_id': 'stop100000000', 'operation': 'stop',
                                   'ok': True, 'clock_ns': stop['clock_ns'],
                                   'target_time_ns': stop['clock_ns'],
                                   'status': copy.deepcopy(stop)}})
        self.assertTrue(M.stop_worker_bindings([], control, guards, EPOCH)['passed'])
        control[0]['ack']['clock_ns'] += 1
        with self.assertRaisesRegex(ValueError, 'identity/clock'):
            M.stop_worker_bindings([], control, guards, EPOCH)

    def test_legacy_native_math_applies_unchanged_to_same_clock_stop_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = Path(temporary)/'lib.so'
            compiled = {key: 'a' * 64 for key in M.BASE.SOURCE_PATHS}
            rows, guards = OLD.fixture('tb1', compiled, library)
            normal_initial = copy.deepcopy(next(row['status'] for row in rows
                if row['kind'] == 'status_publish' and row['sim_time_ns'] == 100_000_000))
            for row in guards:
                if row['clock_ns'] > 100_000_000:
                    row.update(output=[0., 0.], phase_kind='stop',
                               decision_sequence=row['decision_sequence'] + 1)
            guards.insert(5, {'clock_ns': 100_000_000, 'output': [0., 0.],
                             'decision_sequence': 6, 'line': 6, 'phase_kind': 'stop'})
            extra = []
            for row in rows:
                if row['kind'] in ('command_received', 'status_publish'):
                    if row['sim_time_ns'] > 100_000_000:
                        row.update(cmd_seq=row['cmd_seq']+1, desired_v=0., desired_w=0.,
                                   target_decision_sequence=row['target_decision_sequence']+1)
                        if row['kind'] == 'status_publish':
                            row['status'].update(cmd_seq=row['cmd_seq'],
                                decision_sequence=row['target_decision_sequence'], linear_x=0., angular_z=0.)
                    elif row['sim_time_ns'] == 100_000_000:
                        zero = copy.deepcopy(row)
                        zero.update(cmd_seq=6, desired_v=0., desired_w=0., target_decision_sequence=6)
                        if row['kind'] == 'status_publish':
                            zero['status'].update(cmd_seq=6, decision_sequence=6, linear_x=0., angular_z=0.)
                        extra.append(zero)
                elif row['kind'] == 'actuation' and row['sim_time_ns'] > 100_000_000:
                    latest = max((g for g in guards if g['clock_ns'] <= row['sim_time_ns']),
                                 key=lambda g: (g['clock_ns'], g['decision_sequence']))
                    row.update(cmd_seq=latest['decision_sequence'], desired_v=0., desired_w=0.,
                               target_decision_sequence=latest['decision_sequence'],
                               target_clock_ns=latest['clock_ns'], desired_rim_mps=[0., 0.],
                               applied_rim_mps=[0., 0.], alpha=1.)
            rows.extend(extra)
            rows.sort(key=lambda row: (row['sim_time_ns'], row.get('cmd_seq', 0)))
            for index, row in enumerate(rows, 1):
                row['record_sequence'] = index
            result = M.BASE.robot_audit(rows, guards, 'tb1', EPOCH, 100_000_000,
                204_000_000, 1_000_000, compiled, {'library_path': str(library)}, False, normal_initial)
            self.assertTrue(result['passed'])
            self.assertFalse(result['world_body_response_credit'])

    def test_whole_v5_review_keeps_pinned_v4_binary_models_and_all_three_robots(self):
        fixture = OLD.DriveMutationTests('test_all_three_valid_and_no_world_body_credit')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch.object(M.BASE, 'ROOT', fixture.root), patch.object(
                M.BASE, 'git_blob', side_effect=fixture.blob):
            result = M.review(fixture.directory, OLD.FREEZE, fixture.proof_path)
        self.assertTrue(result['passed'])
        self.assertEqual(result['schema'], 'mr3-independent-drive-trace-review-v5')
        self.assertEqual(result['immutable_physics_provenance_base']['sha256'], M.LEGACY_SHA)
        self.assertFalse(result['world_body_response_credit'])


if __name__ == '__main__':
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(OLD),
                               unittest.defaultTestLoader.loadTestsFromTestCase(StopTests)])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
