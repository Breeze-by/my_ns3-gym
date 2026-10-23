"""Synthetic in-memory only. Never opens the two fixed native inputs."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location('disabled_firstfault', HERE / 'firstfault_extract_v3.py')
m = importlib.util.module_from_spec(loader)
loader.loader.exec_module(m)


def motion(sequence, kind='configuration', payload=None, sim=244.58, wall=None):
    return {'schema': 'mr3-motion-safety-v1', 'epoch': m.EPOCH,
            'record_sequence': sequence, 'kind': kind, 'sim_time_sec': sim,
            'wall_monotonic_ns': 1000 + sequence if wall is None else wall,
            'payload': {} if payload is None else payload}


def fault(reason='synthetic reason', robot='tb3', commit=True):
    value = {'schema': 'mr3-reach-runtime-fault-v1', 'robot': robot, 'reason': reason}
    value['commit_clock_ns' if commit else 'clock_ns'] = 244580000000
    return value


def startup(kind='ready_callback', **extra):
    return {'schema': 'mr3-startup-readiness-v1', 'protocol': m.PROTOCOL,
            'epoch': m.EPOCH, 'kind': kind, 'stage': 'released',
            'clock_ns': 244580000000, 'physical_ns': 244580000000,
            'wall_monotonic_ns': 100,
            'ready': {k: True for k in ('monitor_ready', 'initial_inputs_ready',
                'motion_ready', 'odometry_recorder_ready')},
            'callback_fields_received': ['monitor_ready'], **extra}


def scan(rows, label='motion', expected_sha=None, limits=None, deadline=None):
    raw = b''.join((json.dumps(row, allow_nan=True).encode() + b'\n') if type(row) is dict else row for row in rows)
    selection = m.Selection()
    limits = dict(m.LIMITS) if limits is None else limits
    report = m.scan(io.BytesIO(raw), label, {'bytes': len(raw),
        'sha256': expected_sha or hashlib.sha256(raw).hexdigest()}, selection,
        time.monotonic() + 10 if deadline is None else deadline, limits)
    return report, selection.finish(report['parse_and_binding_complete'], limits)


def valid_spec():
    return {'schema': m.SCHEMA, 'admitted': True, 'epoch': m.EPOCH,
            'evidence_freeze': m.OLD_FREEZE, 'execution_freeze_binding': 'required-exact-cli',
            'failure_clock_ns': 244580000000, 'sim_window': ['244.48', '244.62'],
            'limits': dict(m.LIMITS),
            'inputs': {label: {'path': str(m.EP / name), 'bytes': size, 'sha256': '1' * 64,
                'inventory_ref': {'path': str(m.INVENTORY), 'sha256': '2' * 64, 'bytes': 100}}
                for label, (name, size) in m.FILES.items()},
            'consumer': {'path': str(HERE / 'firstfault_extract_v3.py'), 'sha256': '3' * 64, 'bytes': 100},
            'interpretation_sources': {name: {'sha256': '4' * 64, 'bytes': 100} for name in m.SOURCE_PATHS}}


class StrictParseTests(unittest.TestCase):
    def test_first_is_file_order_not_wall_sort_and_preserves_robot_reason(self):
        report, result = scan([
            motion(1, 'normal_control_model_invalid', fault('FIRST', 'tb2'), wall=200),
            motion(2, 'normal_control_model_invalid', fault('SECOND', 'tb1'), wall=100),
            motion(3, 'reach_model_failure', fault('LATER_OTHER_KIND', commit=False), wall=50)])
        self.assertTrue(report['parse_and_binding_complete'])
        first = result['first_runtime_fault']
        self.assertEqual(first['line_1based'], 1)
        self.assertEqual(first['record']['payload']['robot'], 'tb2')
        self.assertEqual(first['record']['payload']['reason'], 'FIRST')
        self.assertEqual(result['relevant_counts']['normal_control_model_invalid'], 2)

    def test_full_no_fault_may_say_not_recorded_only_after_full_hash(self):
        report, result = scan([motion(1), motion(2)])
        self.assertTrue(report['whole_input_read'])
        self.assertTrue(report['parse_and_binding_complete'])
        self.assertEqual(result['first_runtime_fault_status'], 'NOT_RECORDED')

    def test_duplicate_and_nonfinite_constants_and_overflow_outside_window_fail(self):
        for raw in (b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{"a":Infinity}\n',
                    b'{"a":1e999}\n'):
            with self.subTest(raw=raw):
                report, result = scan([raw])
                self.assertTrue(report['whole_input_read'])
                self.assertFalse(report['parse_and_binding_complete'])
                self.assertEqual(result['first_runtime_fault_status'], 'UNKNOWN_PARTIAL_PARSE')
        row = motion(1, sim=100.)
        raw = json.dumps(row).replace('100.0', '1e999').encode() + b'\n'
        report, _ = scan([raw])
        self.assertFalse(report['parse_and_binding_complete'])

    def test_bad_json_or_missing_epoch_does_not_hide_later_fault(self):
        for bad in (b'{bad}\n', {**motion(1), 'epoch': 'wrong'}):
            report, result = scan([bad, motion(2, 'normal_control_model_invalid', fault())])
            self.assertFalse(report['parse_and_binding_complete'])
            self.assertNotEqual(result['first_runtime_fault_status'], 'NOT_RECORDED')
        report, result = scan([b'{bad}\n', motion(1, 'normal_control_model_invalid', fault())])
        self.assertEqual(result['first_runtime_fault_status'], 'RECORDED_BUT_FIRST_UNPROVEN_PARTIAL_PARSE')
        self.assertEqual(result['first_runtime_fault']['record']['payload']['reason'], 'synthetic reason')

    def test_sim_types_negative_and_selected_fault_type_errors_reject(self):
        for value in (None, True, '244.58', -1., float('nan'), float('inf')):
            with self.subTest(value=value):
                report, _ = scan([motion(1, sim=value)])
                self.assertFalse(report['parse_and_binding_complete'])
        for payload in ({'schema': 'wrong', 'robot': 'tb3', 'reason': 'x', 'commit_clock_ns': 1},
                        fault(reason=5), fault(robot='not-a-robot')):
            report, _ = scan([motion(1, 'normal_control_model_invalid', payload)])
            self.assertFalse(report['parse_and_binding_complete'])

    def test_record_sequence_gap_regression_is_not_skipped_for_pass(self):
        for seq in ((1, 3), (2, 3), (1, 1)):
            report, _ = scan([motion(n) for n in seq])
            self.assertFalse(report['parse_and_binding_complete'])

    def test_hash_mismatch_rejects_even_valid_json(self):
        report, result = scan([motion(1)], expected_sha='0' * 64)
        self.assertTrue(report['whole_input_read'])
        self.assertFalse(report['parse_and_binding_complete'])
        self.assertIn('SHA/bytes', report['errors'][0])
        self.assertEqual(result['first_runtime_fault_status'], 'UNKNOWN_PARTIAL_PARSE')

    def test_line_byte_count_and_timeout_limits_are_partial_not_absent(self):
        for updates, rows in (({'line_bytes': 20}, [motion(1)]),
                ({'lines_per_file': 1}, [motion(1), motion(2)])):
            report, result = scan(rows, limits={**m.LIMITS, **updates})
            self.assertFalse(report['whole_input_read'])
            self.assertIsNone(report['whole_input_sha256'])
            self.assertEqual(result['first_runtime_fault_status'], 'UNKNOWN_PARTIAL_PARSE')
        report, result = scan([motion(1)], deadline=0)
        self.assertEqual(report['bytes_read'], 0)
        self.assertFalse(report['parse_and_binding_complete'])

    def test_window_is_fixed_first_and_last_per_bucket(self):
        rows = [motion(i, 'control_failure', {'error': 'synthetic'}, sim=s)
                for i, s in enumerate((244.47, 244.48, 244.50, 244.62, 244.63), 1)]
        report, result = scan(rows)
        self.assertTrue(report['parse_and_binding_complete'])
        self.assertEqual(result['window_bucket_counts']['control_failure/joint/'], 3)
        selected = [item['line_1based'] for item in result['selected_records']]
        self.assertEqual(selected, [1, 2, 4])  # Global first + fixed-window edges.

    def test_selection_limit_and_output_byte_limit_are_explicit(self):
        rows = [motion(1, 'normal_control_model_invalid', fault()),
                motion(2, 'control_failure', {'error': 'other'})]
        _, result = scan(rows, limits={**m.LIMITS, 'selected_records': 1})
        self.assertEqual(result['selected_count'], 1)
        self.assertFalse(result['selection_complete_for_declared_rule'])
        _, result = scan(rows, limits={**m.LIMITS, 'output_bytes': 20})
        self.assertEqual(result['selected_count'], 0)
        self.assertGreater(result['selection_dropped'], 0)

    def test_actual_startup_failure_string_is_preserved_without_inventing_epoch(self):
        data = '{"epoch":"' + m.EPOCH + '","reason":"actual synthetic fault"}'
        row = startup('exploration_failure_received',
            receipt={'topic': '/exploration_failure', 'data': data}, epoch_bound_to_current_startup=True)
        report, result = scan([row], label='startup')
        self.assertTrue(report['parse_and_binding_complete'])
        self.assertEqual(result['first_failure_callback']['record']['receipt']['data'], data)
        self.assertEqual(result['first_failure_callback_status'], 'RECORDED')
        bad = copy.deepcopy(row)
        bad['epoch_bound_to_current_startup'] = 'true'
        report, _ = scan([bad], label='startup')
        self.assertFalse(report['parse_and_binding_complete'])
        report, result = scan([startup()], label='startup')
        self.assertEqual(result['first_failure_callback_status'], 'NOT_RECORDED')

    def test_negative_ack_shape_is_actual_and_missing_id_rejects(self):
        ack = {'schema': 'mr3-motion-control-ack-v2', 'epoch': m.EPOCH,
            'request_id': 'boundary244580000000', 'target_time_ns': 244580000000,
            'clock_ns': 244580000000, 'operation': 'commit', 'ok': False,
            'error': 'normal_control_model_invalid', 'safety_contract': 'mr3-reach-v1',
            'intent_refs': None, 'safety_table_sha256': None}
        report, result = scan([motion(1, 'control_ack', ack)])
        self.assertTrue(report['parse_and_binding_complete'])
        self.assertEqual(result['first_fault_refs']['control_ack']['line_1based'], 1)
        del ack['request_id']
        report, _ = scan([motion(1, 'control_ack', ack)])
        self.assertFalse(report['parse_and_binding_complete'])


    def test_oversized_unknown_kind_rejects_without_retaining_large_counter_key(self):
        row = motion(1, kind='k' * (2 * 1024**2 + 100))
        report, result = scan([row])
        self.assertTrue(report['whole_input_read'])
        self.assertFalse(report['parse_and_binding_complete'])
        self.assertEqual(result['kind_counts'], {})
        self.assertEqual(result['first_runtime_fault_status'], 'UNKNOWN_PARTIAL_PARSE')

    def test_hard_output_fallback_is_small_failed_receipt_and_not_not_recorded(self):
        value = {'schema': m.RESULT_SCHEMA, 'passed': True, 'kind_counts': {'k' * 200000: 1},
                 'identity': {'pid': 1, 'parent': 0, 'group': 1, 'session': 1, 'start_ticks': 1},
                 'started_monotonic_ns': 1, 'ended_monotonic_ns': 2}
        raw = m.encode_result(value, limit=1024)
        self.assertLessEqual(len(raw) + 1, 1024)
        self.assertFalse(value['passed'])
        self.assertTrue(value['output_truncated'])
        self.assertEqual(value['first_runtime_fault_status'], 'OMITTED_OUTPUT_LIMIT')
        self.assertNotIn('kind_counts', value)


class AdmissionTests(unittest.TestCase):
    def test_exact_spec_shape_is_accepted_without_reading_actual_inputs(self):
        self.assertIs(m.validate_spec(valid_spec())['admitted'], True)

    def test_pending_sha_and_wrong_file_window_rule_reject_before_any_io(self):
        changes = [lambda s: s.update(admitted=False),
                   lambda s: s['inputs']['motion'].update(sha256=None),
                   lambda s: s['inputs']['startup'].update(path='/tmp/other.jsonl'),
                   lambda s: s.update(sim_window=['244.4', '244.7']),
                   lambda s: s.update(interpretation_sources={}),
                   lambda s: s.update(execution_freeze_binding=None)]
        for change in changes:
            value = valid_spec()
            change(value)
            with self.subTest(change=change), mock.patch('builtins.open', side_effect=AssertionError('unexpected IO')):
                with self.assertRaises(ValueError):
                    m.validate_spec(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
