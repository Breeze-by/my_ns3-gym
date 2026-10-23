"""Synthetic driver receipt/ownership fixtures only; no child/raw invocation."""
import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location('disabled_firstfault_runner', HERE / 'run_firstfault_v1.py')
m = importlib.util.module_from_spec(loader)
loader.loader.exec_module(m)


def fixtures():
    owner = dict(pid=1, parent=0, group=1, session=1, start_ticks=10)
    wrapper = dict(pid=2, parent=1, group=1, session=1, start_ticks=20)
    consumer = dict(pid=3, parent=2, group=1, session=1, start_ticks=30)
    command = ['/usr/bin/python3', '-B', 'synthetic.py', '--spec', 'synthetic.json',
               '--freeze', 'a' * 40, '--output', 'synthetic-out.json']
    sources = [{'path': '/synthetic-source.py', 'bytes': 10, 'sha256': '1' * 64}]
    spec = {'inputs': {k: {'path': '/synthetic-' + k, 'bytes': 11, 'sha256': '2' * 64}
                       for k in ('motion', 'startup')}}
    reports = [{'input': k, **v, 'bytes_read': v['bytes'], 'whole_input_sha256': v['sha256'],
                'parse_and_binding_complete': True, 'whole_input_read': True,
                'stat_before': [1, 2, 3], 'stat_after': [1, 2, 3], 'error_count': 0, 'errors': []}
               for k, v in spec['inputs'].items()]
    result = dict(schema='mr3-v53-firstfault-description-v1', passed=True, within_work_limit=True,
        errors=[], source_before={'evidence_freeze': m.OLD, 'execution_freeze': 'a' * 40},
        source_after={'evidence_freeze': m.OLD, 'execution_freeze': 'a' * 40},
        selection_complete_for_declared_rule=True, input_reports=reports, identity=consumer,
        started_monotonic_ns=40, ended_monotonic_ns=60,
        actual_argv=[command[0], *command[2:]], first_runtime_fault_status='RECORDED',
        first_failure_callback_status='NOT_RECORDED', scientific_qualification=False)
    wait = dict(schema='mr3-reach-outer-actual-wait-v1', scope='engineering', passed=True,
        actual_waited=True, actual_returncode=0, actual_argv=command, cwd=str(m.W),
        source_unchanged=True, errors=[], coordinator_identity=wrapper, child_identity=copy.deepcopy(consumer),
        started_monotonic_ns=30, ended_monotonic_ns=70,
        actual_child_wait_seconds='0.00000004', source_before=sources, source_after=sources)
    return wait, result, command, sources, spec, wrapper, owner, 20, 80, 0


class DriverTests(unittest.TestCase):
    def test_real_closed_shape_and_complete_source_input_matching(self):
        m.check_closed(*fixtures())

    def test_hash_identity_interval_and_partial_receipts_reject(self):
        for change in (
                lambda f: f[1]['input_reports'][0].update(whole_input_sha256='9' * 64),
                lambda f: f[1]['input_reports'][0].update(error_count=1),
                lambda f: f[1].update(first_runtime_fault_status='UNKNOWN_PARTIAL_PARSE'),
                lambda f: f[1]['identity'].update(start_ticks=99),
                lambda f: f[1].update(ended_monotonic_ns=90),
                lambda f: f[0].update(source_before=[]),
                lambda f: f[0].update(actual_waited=False)):
            value = copy.deepcopy(fixtures())
            change(value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.check_closed(*value)

    def test_actual_wait_exception_is_recorded_then_wait_continues(self):
        child = mock.Mock()
        child.wait.side_effect = [KeyboardInterrupt('synthetic'), RuntimeError('synthetic wait'), 0]
        errors = []
        self.assertEqual(m.wait_owned(child, errors), 0)
        self.assertEqual(child.wait.call_count, 3)
        self.assertEqual(len(errors), 2)

    def test_complete_parent_interval_not_nested_receipt_is_fee(self):
        self.assertEqual(m.parent_fee(0, 301000000000), Decimal('301'))
        self.assertGreater(m.parent_fee(0, 301000000000), m.CAP)
        self.assertEqual(m.ENTRY + m.parent_fee(0, 301000000000), Decimal('90174.5057367926018'))
        for start, end in ((True, 1), (2, 1), (-1, 2)):
            with self.assertRaises(ValueError):
                m.parent_fee(start, end)

    def test_unadmitted_scope_rejects_before_git_or_submission(self):
        with (mock.patch.object(m.subprocess, 'check_output', side_effect=AssertionError('no Git needed')),
              mock.patch.object(m.subprocess, 'Popen', side_effect=AssertionError('no child permitted'))):
            with self.assertRaises(ValueError):
                m.check_sources({'schema': 'mr3-v53-firstfault-scope-v1', 'admitted': False}, 'a' * 40)


if __name__ == '__main__':
    unittest.main(verbosity=2)
