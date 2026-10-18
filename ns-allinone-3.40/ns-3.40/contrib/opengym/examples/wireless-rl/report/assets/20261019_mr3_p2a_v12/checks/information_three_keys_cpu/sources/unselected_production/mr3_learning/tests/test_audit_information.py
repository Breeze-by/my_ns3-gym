"""Short CPU checks for unchanged information predicates and explicit provenance."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from mr3_learning import audit_information as info


def selection(robot='tb1', cycle=1):
    return {'cycle_id': cycle, 'robot': robot, 'skip_reason': 'missing_odom',
            'odom_input_sequence': None, 'odom_source_ns': None,
            'tf_input_sequence': None, 'tf_source_ns': None,
            'pending_odom_input_sequences': [], 'pending_tf_input_sequences': []}


class InformationImplementationTests(unittest.TestCase):
    def test_exact_inverse_and_same_method_as_closed_four_stage_candidate(self):
        host, proof = info.load_implementation()
        self.assertTrue(proof['method_ast_inverse_exact'])
        self.assertTrue(proof['whole_original_source_inverse_exact'])
        self.assertEqual(proof['whole_original_inverse_sha256'], info.RAW_SHA)
        self.assertEqual(proof['effective_selection_method_sha256'],
            'f9ea7d7f1f6faa5114a430f80758c2d78137b1050950d745462f715aa16bc5f5')
        self.assertEqual(hashlib.sha256((info.WORKSPACE / info.HOST_RELATIVE).read_bytes()).hexdigest(), info.HOST_SHA)

    def test_one_provenance_field_preserves_every_original_pass_or_failure_field(self):
        _, proof = info.load_implementation()
        for passed in (False, True):
            original = {'passed': passed, 'errors': [] if passed else ['original failed gate'],
                'consumer_sha256': info.HOST_SHA, 'episodes': [{'passed': passed}],
                'criteria': {'state_age_limit_sec_unchanged': .5}}
            before = deepcopy(original)
            result = info.add_provenance(original, proof)
            self.assertEqual(result.pop('implementation_provenance'), proof)
            self.assertEqual(result, before)
            self.assertEqual(original, before)

    def test_full_selection_state_and_invalid_input_predicates_remain_unchanged(self):
        host, _ = info.load_implementation()
        old, new = host.RawReplay('cpu'), host.LedgerReplay('cpu')
        for robot in host.ROBOTS:
            old.selection(selection(robot), 20_000_000)
            new.selection(selection(robot), 20_000_000)
            self.assertEqual(old.selections, new.selections)
        for cls in (host.RawReplay, host.LedgerReplay):
            with self.assertRaisesRegex(ValueError, 'duplicate/invalid selection'):
                cls('cpu').selection(selection('tb4'), 1)
            replay = cls('cpu')
            replay.selections[1, 'tb2'] = {'clock_ns': 100}
            with self.assertRaisesRegex(ValueError, 'first capture clocks differ'):
                replay.selection(selection(), 101)

    def test_wrong_original_source_is_rejected_before_any_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in (info.HOST_RELATIVE, info.RAW_RELATIVE):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((info.WORKSPACE / relative).read_bytes())
            (root / info.RAW_RELATIVE).write_bytes(b'not the original helper\n')
            with self.assertRaisesRegex(ValueError, 'immutable original information source differs'):
                info.load_implementation(root)

    def test_existing_implementation_provenance_is_not_silently_replaced(self):
        with self.assertRaisesRegex(ValueError, 'unexpectedly has implementation provenance'):
            info.add_provenance({'implementation_provenance': {'old': True}}, {'new': True})


if __name__ == '__main__':
    unittest.main()
