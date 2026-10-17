#!/usr/bin/python3
"""Only fixed V21 selection and receipt identity; inherited codec not rerun."""
import copy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path('/tmp/mr3_p2a0_v21_ray_pack_closed_v1.py')
spec = importlib.util.spec_from_file_location('v21_custody_selection', SOURCE)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def execution():
    ep = helper.FIXED_RUN / 'worker0/episode001_open_101'
    return {'schema': 'mr3-startup-sensor-execution-v1', 'status': 'completed',
            'stage': 'iters150', 'freeze': helper.FIXED_FREEZE, 'passed': True,
            'capture_process_completed': True, 'strict_native_closure_passed': True,
            'benchmark_summary': {'path': str(helper.FIXED_RUN / 'benchmark_summary.json')},
            'actual_workload': {'protocol': {'path': str(ep / 'transitions.jsonl')}},
            'recorder_final': {'path': str(helper.FIXED_CAPTURE / 'final.json')},
            'ray_measurement_availability': {'passed': True, 'robots': {
                robot: {'passed': True, 'path': str(ep / ('ray_' + robot + '.jsonl')),
                        'process_id': 123, 'configuration': 1, 'sensor_connected': 1,
                        'scans': 1, 'sensor_identity': {'parent': robot + '::base_scan',
                            'scoped_name': 'p1c_open::' + robot + '::base_scan::hls_lfcd_lds'}}
                for robot in ('tb1', 'tb2', 'tb3')}}}


class FixedSelectionTests(unittest.TestCase):
    def test_exact_two_sources(self):
        for kind, source, suffix in [('native', helper.FIXED_RUN, '/native/iters150'),
                                     ('sensor_capture', helper.FIXED_CAPTURE, '/sensor_capture')]:
            helper.validate_selection(source, Path('/tmp/new_v21_custody_fixture'),
                                      helper.A21 + suffix, helper.FIXED_EXECUTION, kind)
        helper.validate_execution_identity(execution())

    def test_same_basename_other_origin_is_not_accepted(self):
        with self.assertRaises(AssertionError):
            helper.validate_selection(Path('/tmp') / helper.FIXED_RUN.name,
                Path('/tmp/new_v21_custody_fixture'), helper.A21 + '/native/iters150',
                helper.FIXED_EXECUTION, 'native')

    def test_old_v20_prefix_or_execution_rejected(self):
        for prefix, receipt in [(helper.A21.replace('v21_ray', 'v20_sensor') + '/sensor_capture',
                                 helper.FIXED_EXECUTION),
                                (helper.A21 + '/sensor_capture', Path('/tmp/other_execution.json'))]:
            with self.assertRaises(AssertionError):
                helper.validate_selection(helper.FIXED_CAPTURE, Path('/tmp/new_v21_custody_fixture'),
                                          prefix, receipt, 'sensor_capture')

    def test_target_must_be_separate_tmp_destination(self):
        for target in [helper.FIXED_CAPTURE, helper.FIXED_CAPTURE / 'nested', Path('/var/tmp/x')]:
            with self.assertRaises(AssertionError):
                helper.validate_selection(helper.FIXED_CAPTURE, target,
                    helper.A21 + '/sensor_capture', helper.FIXED_EXECUTION, 'sensor_capture')

    def test_receipt_freeze_and_typed_verdict(self):
        for key, value in [('freeze', '0' * 40), ('passed', 1), ('status', 'native_running'),
                           ('capture_process_completed', 1), ('strict_native_closure_passed', 1)]:
            item = execution()
            item[key] = value
            with self.assertRaises(AssertionError):
                helper.validate_execution_identity(item)
        item = execution()
        item['passed'] = False
        item['ray_measurement_availability']['passed'] = False
        helper.validate_execution_identity(item)  # Custody preserves an original False.

    def test_ray_identity_cannot_borrow_other_robot_or_file(self):
        for key, value in [('process_id', True), ('scans', True), ('path', '/tmp/elsewhere.jsonl'),
                           ('sensor_identity', {'parent': 'tb1::base_scan',
                            'scoped_name': 'p1c_open::tb1::base_scan::hls_lfcd_lds'})]:
            item = copy.deepcopy(execution())
            item['ray_measurement_availability']['robots']['tb2'][key] = value
            with self.assertRaises(AssertionError):
                helper.validate_execution_identity(item)


if __name__ == '__main__':
    unittest.main()
