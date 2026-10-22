#!/usr/bin/python3
"""Pure artificial V50-v4 checks. No runtime roots, /proc or subprocess calls.

Prepared but not executed by the author. Root may run this after source sealing.
Only candidate definitions and the pinned immutable A16 source are loaded.
"""
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode = True


def load(path, wanted, name):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != wanted:
        raise ValueError('self-check candidate source differs: ' + path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load('/tmp/mr3_p2a_v50_review_closed_draft_v4.py', '320eb795fa7dbc0beb1aedba6f9ba54d193f38f0df31155bb670261c3e5747e9', '_review_v4_artificial')
C = load('/tmp/mr3_p2a_v50_collect_closed_draft_v4.py', '83477102f5b6575824b3c9a954fa2cc8ba34331d33f35f6a306b927ab27e2ad3', '_collect_v4_artificial')


class ArtificialChecks(unittest.TestCase):
    def evidence(self, value):
        parser = R.load_identity_helper()
        evidence = parser.Evidence()
        evidence.visit(value, 'synthetic-original', '/root')
        return evidence

    def merged(self, value):
        evidence = self.evidence(value)
        review = R.Review()
        review.merge_a16(evidence, 'synthetic-original')
        return evidence, review

    def test_canonical_pair_is_not_missing_start(self):
        evidence, review = self.merged({'pid': 71, 'start_ticks': 91})
        self.assertIn((71, 91), review.identities)
        self.assertEqual(review.pid_only, {})
        self.assertEqual(review.a16_canonical_pid_occurrences[0]['identity_status'], 'paired_same_object')
        self.assertEqual(len(evidence.pid_only[71]), 1)  # original raw registry retained

    def test_missing_start_retains_exact_original_location(self):
        evidence, review = self.merged({'pid': 71})
        row = review.a16_canonical_pid_occurrences[0]
        self.assertEqual(row['a16_original_location'], 'synthetic-original/root')
        self.assertEqual(row['identity_status'], 'missing_same_object_start')
        self.assertEqual(row['same_object_pair_occurrences'], [])
        self.assertEqual(set(review.pid_only), {71})
        self.assertEqual(review.identities, {})

    def test_different_object_same_pid_cannot_repair_occurrence(self):
        _, review = self.merged([{'pid': 71}, {'pid': 71, 'start_ticks': 91}])
        rows = review.a16_canonical_pid_occurrences
        self.assertEqual([row['identity_status'] for row in rows],
                         ['missing_same_object_start', 'paired_same_object'])
        self.assertEqual(rows[0]['same_object_pair_occurrences'], [])
        self.assertEqual(review.pid_only[71][0]['path'], 'synthetic-original/root/0')
        # Global A16 PID coverage is separately satisfied; the first occurrence
        # still has no start and never becomes a new pair.
        self.assertEqual(set(review.pid_only) - {pid for pid, start in review.identities}, set())
        self.assertEqual(set(review.identities), {(71, 91)})

    def test_prefix_pair_does_not_assign_start_to_canonical_pid(self):
        _, review = self.merged({'pid': 71, 'worker_pid': 71, 'worker_start_ticks': 91})
        self.assertIn((71, 91), review.identities)
        self.assertEqual(review.a16_canonical_pid_occurrences[0]['identity_status'], 'missing_same_object_start')
        self.assertEqual(set(review.pid_only), {71})

    def test_prefix_pair_without_canonical_pid_has_no_raw_pid_occurrence(self):
        _, review = self.merged({'worker_pid': 71, 'worker_start_ticks': 91})
        self.assertEqual(set(review.identities), {(71, 91)})
        self.assertEqual(review.a16_canonical_pid_occurrences, [])
        self.assertEqual(review.pid_only, {})

    def test_conflicting_same_object_starts_remain_error(self):
        _, review = self.merged({'pid': 71, 'start_ticks': 91, 'process_start_ticks': 92})
        self.assertEqual(set(review.identities), {(71, 91), (71, 92)})
        self.assertEqual(review.a16_canonical_pid_occurrences[0]['identity_status'],
                         'conflicting_same_object_starts')
        self.assertTrue(any('conflicting start times' in error for error in review.identity_errors))

    def test_global_unbound_pid_is_still_distinct(self):
        _, review = self.merged([{'pid': 71}, {'pid': 72, 'start_ticks': 92}])
        self.assertEqual(set(review.pid_only) - {pid for pid, start in review.identities}, {71})

    def test_real_a16_embedded_raw_json_preserves_nested_locations(self):
        _, review = self.merged({'raw_json': '[{"pid":71},{"pid":71,"start_ticks":91}]'})
        rows = review.a16_canonical_pid_occurrences
        self.assertEqual(rows[0]['identity_status'], 'missing_same_object_start')
        self.assertEqual(rows[1]['identity_status'], 'paired_same_object')
        self.assertIn('/raw_json/@decoded_json/0', rows[0]['a16_original_location'])

    def test_false_parent_proof_cannot_grant_any_archive_or_reaped_claim(self):
        gates = R.archive_gate_results(False, [{'pid': 71, 'start_ticks': 91}], True, True, [], True)
        self.assertFalse(gates['parent_wait_proof_valid'])
        self.assertFalse(gates['parent_coordinators_actual_waited_and_fresh_gone'])
        self.assertFalse(gates['archive_evidence_preservation_admissible'])
        self.assertFalse(gates['closed_archive_eligible'])
        doc = dict(schema='mr3-v50-independent-closed-metadata-review-draft-v4', freeze=C.FREEZE,
            parent_wait_proof_valid=False, parent_coordinators_actual_waited_and_fresh_gone=True,
            exact_A16_launch_and_raw_json_extraction=True, bound_inputs_stable=True,
            metadata_membership_stable=True)
        class FakeMetadata:
            @staticmethod
            def metadata(path): return doc, {}
            @staticmethod
            def require(value, message):
                if not value: raise ValueError(message)
            @staticmethod
            def require_absent(row): raise AssertionError('must reject before process observation')
        for mode in ('closed', 'preserve-evidence'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'completed parent-wait'):
                C.closed_review(FakeMetadata(), Path('/never-read-artificial.json'), mode)

    def test_valid_receipt_with_scientific_failure_can_only_preserve(self):
        gates = R.archive_gate_results(True, [{'pid': 71, 'start_ticks': 91}], True, True,
                                       ['original scientific or metadata failure retained'], False)
        self.assertTrue(gates['archive_evidence_preservation_admissible'])
        self.assertFalse(gates['closed_archive_eligible'])
        self.assertTrue(gates['parent_coordinators_actual_waited_and_fresh_gone'])


if __name__ == '__main__':
    unittest.main()
