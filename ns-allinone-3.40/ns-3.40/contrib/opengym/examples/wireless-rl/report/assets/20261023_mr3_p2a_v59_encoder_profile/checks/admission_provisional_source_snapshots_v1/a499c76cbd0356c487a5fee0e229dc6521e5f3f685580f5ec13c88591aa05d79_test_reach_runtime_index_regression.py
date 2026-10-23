"""Synthetic equivalence attacks against the exact frozen runtime reader.

No episode, native process, source qualification, or scientific consumer runs
here. The independent oracle is the whole verified 3631 reader module, rather
than old functions linked to candidate numeric or indexing helpers.
"""
import copy
from decimal import Decimal
from fractions import Fraction
import hashlib
from pathlib import Path
import subprocess
import types
import unittest

from mr3_learning import audit_reach_runtime as candidate
from mr3_learning.tests.test_audit_reach_runtime import (
    BEGIN, END, EPOCH, fixture,
)


FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'
FROZEN_SHA = '62f4a7e010e1b339eb7bbe7754c56e71baea46dc084b3792d44ec3f1e7ae89d8'


class RuntimeIndexRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(candidate.__file__).resolve()
        root = next(p for p in source.parents if (p / '.git').exists())
        blob = subprocess.check_output([
            'git', '-C', str(root), 'show',
            FREEZE + ':' + source.relative_to(root).as_posix(),
        ])
        if hashlib.sha256(blob).hexdigest() != FROZEN_SHA:
            raise AssertionError('frozen runtime oracle bytes differ')
        original = types.ModuleType('frozen_3631_runtime_index_oracle')
        original.__file__ = str(source)
        exec(compile(blob, 'frozen-3631/audit_reach_runtime.py', 'exec'), vars(original))
        cls.original = original

    @staticmethod
    def renumber(rows):
        for sequence, row in enumerate(rows, 1):
            row['record_sequence'] = sequence

    @staticmethod
    def renumber_inputs(rows, kind, robot='tb1'):
        sequence = 0
        for row in rows:
            if row['kind'] == kind and row['payload']['robot'] == robot:
                sequence += 1
                row['payload']['input_sequence'] = sequence

    @staticmethod
    def outcome(function, *args, **kwargs):
        args, kwargs = copy.deepcopy((args, kwargs))
        before = copy.deepcopy((args, kwargs))
        try:
            result = ('returned', function(*args, **kwargs))
        except Exception as error:
            result = ('error', type(error).__name__, str(error))
        if (args, kwargs) != before:
            raise AssertionError('reader changed a synthetic input')
        return result

    def equivalent(self, name, *args, error=None, **kwargs):
        before = self.outcome(getattr(self.original, name), *args, **kwargs)
        after = self.outcome(getattr(candidate, name), *args, **kwargs)
        self.assertEqual(before, after)
        if error is None:
            self.assertEqual(after[0], 'returned', after)
        else:
            self.assertEqual(after[0], 'error', after)
            self.assertIn(error, after[2])
        return after

    def audit_case(self, case, *, error=None):
        return self.equivalent('_audit_records', error=error, **case)

    @staticmethod
    def first_decision(rows, clock=BEGIN, robot='tb1'):
        return next(row for row in rows if row['kind'] == 'reach_decision'
                    and row['payload']['robot'] == robot
                    and row['payload']['clock_ns'] == clock)

    def insert_tf(self, case, message, *, before=None):
        rows = case['motion']
        template = next(row for row in rows if row['kind'] == 'own_tf'
                        and row['payload']['robot'] == 'tb1')
        added = copy.deepcopy(template)
        added['payload']['message'] = copy.deepcopy(message)
        at = len(rows) if before is None else rows.index(before)
        rows.insert(at, added)
        self.renumber_inputs(rows, 'own_tf')
        self.renumber(rows)
        return added

    def test_complete_declared_prefix_matches_frozen_report(self):
        self.audit_case(fixture())

    def test_native_command_must_precede_actual_record_not_just_clock(self):
        case = fixture()
        rows = case['drivers']['tb1']
        actual = next(row for row in rows if row['kind'] == 'actuation')
        chosen = next(row for row in rows if row['kind'] == 'command_received'
                      and row['cmd_seq'] == actual['cmd_seq'])
        self.assertLess(chosen['sim_time_ns'], actual['sim_time_ns'])
        rows.remove(chosen)
        rows.insert(rows.index(actual) + 1, chosen)
        self.renumber(rows)
        self.equivalent('native_index', case['drivers'], case['odometry_rows'], EPOCH,
                        error='actuation has no earlier native command')

    def test_same_clock_later_command_cannot_replace_strict_prior_command(self):
        case = fixture()
        rows = case['drivers']['tb1']
        actual = next(row for row in rows if row['kind'] == 'actuation')
        future = next(row for row in rows if row['kind'] == 'command_received'
                      and row['cmd_seq'] == actual['cmd_seq'] + 1)
        future['sim_time_ns'] = actual['sim_time_ns']
        self.renumber(rows)
        self.equivalent('native_index', case['drivers'], case['odometry_rows'], EPOCH)
        rows.remove(future)
        rows.insert(rows.index(actual), future)
        self.renumber(rows)
        self.equivalent('native_index', case['drivers'], case['odometry_rows'], EPOCH,
                        error='native actuation did not select the latest stored command')

    def test_unused_malformed_native_command_tail_is_still_rejected(self):
        case = fixture()
        rows = case['drivers']['tb1']
        tail = copy.deepcopy(next(row for row in reversed(rows)
                                  if row['kind'] == 'command_received'))
        tail['cmd_seq'] += 2
        rows.append(tail)
        self.renumber(rows)
        self.equivalent('native_index', case['drivers'], case['odometry_rows'], EPOCH,
                        error='native command sequence gap')

    def test_repeated_raw_source_counts_every_callback(self):
        case = fixture()
        rows = case['motion']
        first = next(row for row in rows if row['kind'] == 'own_odom'
                     and row['payload']['robot'] == 'tb1')
        rows.insert(rows.index(first) + 1, copy.deepcopy(first))
        self.renumber_inputs(rows, 'own_odom')
        self.renumber(rows)
        self.audit_case(case)
        native = self.original.native_index(case['drivers'], case['odometry_rows'], EPOCH)
        result = self.equivalent('ingress_index', rows, native, EPOCH)
        self.assertEqual(len(result[1]['tb1']['raw'][BEGIN]), 2)

    def test_duplicate_source_does_not_hide_a_callback_sequence_gap(self):
        case = fixture()
        rows = case['motion']
        first = next(row for row in rows if row['kind'] == 'own_odom'
                     and row['payload']['robot'] == 'tb1')
        duplicate = copy.deepcopy(first)
        duplicate['payload']['input_sequence'] = 2
        rows.insert(rows.index(first) + 1, duplicate)
        # The original next source still says callback 2, rather than 3.
        self.renumber(rows)
        self.audit_case(case, error='own raw callback sequence gap')

    def test_each_causal_raw_calibration_and_applied_receipt_must_be_prior(self):
        for feed in ('raw', 'calibration', 'applied'):
            with self.subTest(feed=feed):
                case = fixture()
                rows = case['motion']
                clock = BEGIN + candidate.RAW
                if feed == 'raw':
                    selected = next(row for row in rows if row['kind'] == 'own_odom'
                                    and row['payload']['robot'] == 'tb1'
                                    and candidate.source(row['payload']['message']) == clock)
                else:
                    selected = next(row for row in rows if row['kind'] == 'reach_driver_ingress'
                                    and row['payload']['robot'] == 'tb1'
                                    and row['payload']['kind'] == feed
                                    and (feed == 'applied'
                                         or row['payload']['message']['source_clock_ns'] == clock))
                decision = self.first_decision(rows, clock)
                self.assertLess(rows.index(selected), rows.index(decision))
                rows.remove(selected)
                rows.insert(rows.index(decision) + 1, selected)
                self.renumber(rows)
                expected = ('normal decision closed before a real causal application receipt'
                            if feed == 'applied' else
                            'normal decision closed before an actual causal raw/calibration source')
                self.audit_case(case, error=expected)

    def test_missing_source_and_application_receipts_remain_failures(self):
        for feed in ('raw', 'calibration', 'applied'):
            with self.subTest(feed=feed):
                case = fixture()
                rows = case['motion']
                if feed == 'raw':
                    selected = next(row for row in reversed(rows) if row['kind'] == 'own_odom'
                                    and row['payload']['robot'] == 'tb1')
                else:
                    selected = next(row for row in reversed(rows)
                                    if row['kind'] == 'reach_driver_ingress'
                                    and row['payload']['robot'] == 'tb1'
                                    and row['payload']['kind'] == feed)
                rows.remove(selected)
                self.renumber(rows)
                expected = ('normal decision closed before a real causal application receipt'
                            if feed == 'applied' else
                            'normal decision closed before an actual causal raw/calibration source')
                self.audit_case(case, error=expected)

    def test_no_receipt_requirement_is_invented_beyond_the_closed_window(self):
        case = fixture()
        rows = case['odometry_rows']['tb1']
        tail = copy.deepcopy(rows[-1])
        clock = END + candidate.RAW
        tail.update(record_sequence=tail['record_sequence']+1,
                    publication_sequence=tail['publication_sequence']+1,
                    source_clock_ns=clock, sim_time_ns=clock)
        tail['odometry']['header']['stamp'] = {'sec':clock//10**9, 'nanosec':clock%10**9}
        rows.append(tail)
        self.audit_case(case)

    @staticmethod
    def bad_first_actual_time_case():
        # The frozen native_index does not inspect the first actual timestamp
        # when previous is None. Keep that exact accepted boundary; do not use
        # a mock to pretend a stronger native type invariant already exists.
        case = fixture()
        rows = case['drivers']['tb1']
        first = next(row for row in rows if row['kind'] == 'actuation')
        rows[:] = [row for row in rows if row['kind'] != 'actuation' or row is first]
        first['sim_time_ns'] = None
        RuntimeIndexRegressionTests.renumber(rows)
        case['motion'][:] = [row for row in case['motion']
                            if not (row['kind'] == 'reach_driver_ingress'
                                    and row['payload']['kind'] == 'applied')]
        RuntimeIndexRegressionTests.renumber(case['motion'])
        return case

    def test_unused_bad_actual_time_does_not_preempt_no_decision_failure(self):
        case = self.bad_first_actual_time_case()
        case['motion'][:] = [row for row in case['motion'] if row['kind'] != 'reach_decision']
        self.renumber(case['motion'])
        self.audit_case(case, error='advance lacked a fresh joint20ms reach status')

    def test_stop_and_nonready_still_evaluate_original_actual_time_condition(self):
        # The original condition compares time before testing phase/readiness.
        # Moving the whole check under ready-normal would silently change it.
        for phase, ready in (('stop', True), ('normal', False)):
            with self.subTest(phase=phase, ready=ready):
                case = self.bad_first_actual_time_case()
                first = self.first_decision(case['motion'])
                first['payload'].update(phase_kind=phase, ready=ready)
                self.audit_case(case, error="'<=' not supported between instances of 'int' and 'NoneType'")

    def test_unknown_phase_is_rejected_before_bad_actual_time(self):
        case = self.bad_first_actual_time_case()
        self.first_decision(case['motion'])['payload']['phase_kind'] = 'unknown'
        self.audit_case(case, error='unknown decision phase')

    def test_missing_raw_gate_precedes_bad_actual_timestamp(self):
        case = self.bad_first_actual_time_case()
        rows = case['motion']
        rows[:] = [row for row in rows
                   if not (row['kind'] == 'own_odom' and row['payload']['robot'] == 'tb1')]
        self.renumber(rows)
        self.audit_case(case, error='normal decision closed before an actual causal raw/calibration source')

    def test_duplicate_receipt_after_decision_cannot_erase_earliest_arrival(self):
        for feed in ('calibration', 'applied'):
            with self.subTest(feed=feed):
                case = fixture()
                rows = case['motion']
                receipt = next(row for row in rows if row['kind'] == 'reach_driver_ingress'
                               and row['payload']['robot'] == 'tb1'
                               and row['payload']['kind'] == feed)
                rows.append(copy.deepcopy(receipt))
                self.renumber(rows)
                self.audit_case(case)

    def test_tf_equal_header_chooses_latest_prior_callback(self):
        case = fixture()
        decision = self.first_decision(case['motion'])
        changed = copy.deepcopy(decision['payload']['own_state']['transform'])
        changed['header']['frame_id'] = 'same-header-newest-callback'
        self.insert_tf(case, changed, before=decision)
        decision['payload']['own_state']['transform'] = changed
        self.audit_case(case)
        decision['payload']['own_state']['transform']['header']['frame_id'] = 'map'
        self.audit_case(case, error='guard selected unreceived/noncausal own TF')

    def test_tf_future_header_and_later_old_header_do_not_override_max_eligible(self):
        for offset in (-100_000_000, 10_000_000_000):
            with self.subTest(offset=offset):
                case = fixture()
                decision = self.first_decision(case['motion'])
                message = copy.deepcopy(decision['payload']['own_state']['transform'])
                clock = BEGIN + 200_000_000 + offset
                message['header']['stamp'] = {'sec':clock//10**9, 'nanosec':clock%10**9}
                message['header']['frame_id'] = 'must-not-be-selected'
                self.insert_tf(case, message, before=decision)
                self.audit_case(case)

    def test_tf_arriving_after_decision_cannot_supply_that_decision(self):
        case = fixture()
        rows = case['motion']
        decision = self.first_decision(rows)
        current = copy.deepcopy(decision['payload']['own_state']['transform'])
        current['header']['frame_id'] = 'future-arrival'
        added = self.insert_tf(case, current, before=decision)
        rows.remove(added)
        rows.insert(rows.index(decision) + 1, added)
        self.renumber(rows)
        decision['payload']['own_state']['transform'] = current
        self.audit_case(case, error='guard selected unreceived/noncausal own TF')

    def test_unused_malformed_tf_tail_is_not_eagerly_parsed(self):
        case = fixture()
        decision = self.first_decision(case['motion'])
        message = copy.deepcopy(decision['payload']['own_state']['transform'])
        message['header']['stamp'] = {'sec':True, 'nanosec':0}
        self.insert_tf(case, message)
        self.audit_case(case)

    def test_malformed_prior_tf_is_rejected_even_when_not_selected(self):
        case = fixture()
        decision = self.first_decision(case['motion'])
        message = copy.deepcopy(decision['payload']['own_state']['transform'])
        message['header']['stamp'] = {'sec':True, 'nanosec':0}
        self.insert_tf(case, message, before=decision)
        self.audit_case(case, error='invalid integer identity')

    def test_tf_query_clock_can_regress_without_losing_older_eligible_header(self):
        case = fixture()
        rows = case['motion']
        first = self.first_decision(rows)
        first_bundle = next(row for row in rows if row['kind'] == 'received_states')
        ingress = next(row for row in rows if row['kind'] == 'reach_state_ingress')
        rows.extend((copy.deepcopy(ingress), copy.deepcopy(first_bundle)))
        owner = copy.deepcopy(next(row for row in reversed(rows)
                                   if row['kind'] == 'reach_intent_publish'
                                   and row['payload']['robot'] == 'tb1'))
        clock = BEGIN + 1_000_000
        value = owner['payload']['intent']
        value['intent_sequence'] += 1
        value['source_clock_ns'] = clock
        value['target'].update(clock_ns=clock, decision_sequence=value['intent_sequence'])
        owner['payload']['payload_sha256'] = candidate.digest(value)
        rows.append(owner)
        regressed = copy.deepcopy(first)
        regressed['payload'].update(clock_ns=clock,
            decision_sequence=value['intent_sequence'], intent=copy.deepcopy(value), ready=False)
        rows.append(regressed)
        self.renumber(rows)
        self.audit_case(case)

    def test_number_cache_preserves_exact_type_validation_and_fraction_values(self):
        values = [1, 1., 0, 0., -0., 2**53+1, float(2**53), .1, -1.,
                  True, False, [], {}, Decimal('1'), Fraction(1), '1', None,
                  float('nan'), float('inf'), -float('inf'), 10**1000]
        # Warm equal numeric keys before invalid bools, including both orders.
        for sequence in (values, list(reversed(values)), values):
            for value in sequence:
                with self.subTest(type=type(value).__name__, value=repr(value)):
                    before = self.outcome(self.original.number, value)
                    after = self.outcome(candidate.number, value)
                    self.assertEqual(before, after)
                    if before[0] == 'returned':
                        self.assertIs(type(after[1]), Fraction)

    def test_number_cache_eviction_does_not_admit_a_bool_or_nonfinite(self):
        for value in range(4200):
            self.assertEqual(self.original.number(value), candidate.number(value))
        for value in (True, False, float('nan'), float('inf')):
            self.assertEqual(self.outcome(self.original.number, value),
                             self.outcome(candidate.number, value))


if __name__ == '__main__':
    unittest.main()
