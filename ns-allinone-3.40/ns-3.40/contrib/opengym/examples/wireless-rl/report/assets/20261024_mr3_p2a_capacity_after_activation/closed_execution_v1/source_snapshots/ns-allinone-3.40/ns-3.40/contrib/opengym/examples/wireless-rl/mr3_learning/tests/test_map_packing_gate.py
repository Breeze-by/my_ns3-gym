"""Source-only map packing admission; no World, ROS node or trace replay."""

import hashlib
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import audit_ppo, reach_gates as gates, reach_preparation


ROOT = Path(gates.__file__).resolve().parents[7]
PACKED_FREEZE = '291b9e32ea3df8c107f804a339d4bd1e93405f3a'
OLD_FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class MapPackingGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Only frozen source bytes, not saved observations or native artifacts.
        cls.packed = (ROOT / gates.MERGE_MAP_SOURCE).read_bytes()
        cls.original = subprocess.check_output(
            ['git', 'show', OLD_FREEZE + ':' + gates.MERGE_MAP_SOURCE], cwd=ROOT)

    def legacy(self):
        return SimpleNamespace(PREPARATION_RUNTIME_PINS={
            gates.MERGE_MAP_SOURCE: gates.MERGE_MAP_LEGACY_SHA256,
            'unchanged/runtime.py': 'a' * 64})

    def bindings(self):
        return {gates.MERGE_MAP_SOURCE: gates.MERGE_MAP_PACKED_SHA256}

    def test_whole_inverse_equals_real_original_git_bytes_not_only_expected_hash(self):
        old, proof = gates.project_map_output_packing(self.packed)
        self.assertEqual(old, self.original)
        self.assertEqual(digest(old), gates.MERGE_MAP_LEGACY_SHA256)
        self.assertEqual(proof['whole_source_inverse_sha256'], gates.MERGE_MAP_LEGACY_SHA256)
        self.assertEqual(proof['literal_inverse_replacements'], 3)
        self.assertEqual(proof['old_source_bytes'], len(self.original))
        self.assertEqual(proof['new_source_bytes'], len(self.packed))

    def test_unreviewed_bytes_and_old_source_are_not_the_new_packing_profile(self):
        for raw in (self.original, self.packed + b'\n', self.packed.replace(b'100', b'99', 1), bytearray(self.packed)):
            with self.subTest(kind=type(raw).__name__, size=len(raw)):
                with self.assertRaisesRegex(ValueError, 'source SHA'):
                    gates.project_map_output_packing(raw)

    def test_each_inverse_literal_has_exactly_one_occurrence(self):
        for current, _ in gates.MAP_OUTPUT_PACKING_INVERSE:
            for raw in (self.packed.replace(current, b'', 1), self.packed + current):
                with self.subTest(literal=current[:30], repeated=raw.endswith(current)):
                    # Exercise the inverse guard itself independently of the
                    # fixed input SHA guard, without changing real source bytes.
                    with patch.object(gates, 'MERGE_MAP_PACKED_SHA256', digest(raw)):
                        with self.assertRaisesRegex(ValueError, 'occurrence'):
                            gates.project_map_output_packing(raw)

    def test_inverse_rejects_an_unrelated_algorithm_change_even_with_declared_input_hash(self):
        raw = self.packed.replace(b'merged = np.maximum(merged, resampled)',
                                 b'merged = np.minimum(merged, resampled)', 1)
        self.assertNotEqual(raw, self.packed)
        with patch.object(gates, 'MERGE_MAP_PACKED_SHA256', digest(raw)):
            with self.assertRaisesRegex(ValueError, 'complete old source'):
                gates.project_map_output_packing(raw)

    def test_unknown_profile_and_nonexact_freeze_refuse_before_git(self):
        cases = [('array-v2', PACKED_FREEZE), (True, PACKED_FREEZE),
                 (gates.MAP_OUTPUT_PACKING_PROFILE, 'main'),
                 (gates.MAP_OUTPUT_PACKING_PROFILE, 'A' * 40)]
        for profile, freeze in cases:
            legacy = self.legacy()
            before = legacy.PREPARATION_RUNTIME_PINS.copy()
            with self.subTest(profile=profile, freeze=freeze), \
                    patch.object(gates.subprocess, 'check_output') as git, self.assertRaises(ValueError):
                gates.version_map_output_packing(legacy, ROOT, freeze, self.bindings(), profile)
            git.assert_not_called()
            self.assertEqual(legacy.PREPARATION_RUNTIME_PINS, before)

    def test_actual_frozen_git_current_and_declared_source_match_before_private_pin_changes(self):
        legacy = self.legacy()
        before = legacy.PREPARATION_RUNTIME_PINS.copy()
        proof = gates.version_map_output_packing(legacy, ROOT, PACKED_FREEZE,
            self.bindings(), gates.MAP_OUTPUT_PACKING_PROFILE)
        self.assertEqual(legacy.PREPARATION_RUNTIME_PINS,
            {**before, gates.MERGE_MAP_SOURCE: gates.MERGE_MAP_PACKED_SHA256})
        self.assertEqual(proof['source'], PACKED_FREEZE + ':' + gates.MERGE_MAP_SOURCE)
        self.assertTrue(proof['plan_frozen_worktree_source_equal'])
        self.assertFalse(proof['scientific_native_credit'])
        self.assertFalse(proof['original_mathematical_predicates_changed'])

    def test_each_declared_frozen_or_worktree_mismatch_refuses_without_pin_mutation(self):
        for component in ('declared', 'frozen', 'worktree'):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / gates.MERGE_MAP_SOURCE
                target.parent.mkdir(parents=True)
                target.write_bytes(self.packed + (b'\n' if component == 'worktree' else b''))
                bindings = self.bindings()
                if component == 'declared':
                    bindings[gates.MERGE_MAP_SOURCE] = gates.MERGE_MAP_LEGACY_SHA256
                frozen = self.packed + (b'\n' if component == 'frozen' else b'')
                legacy = self.legacy()
                before = legacy.PREPARATION_RUNTIME_PINS.copy()
                with patch.object(gates.subprocess, 'check_output', return_value=frozen), self.assertRaises(ValueError):
                    gates.version_map_output_packing(legacy, root, PACKED_FREEZE,
                        bindings, gates.MAP_OUTPUT_PACKING_PROFILE)
                self.assertEqual(legacy.PREPARATION_RUNTIME_PINS, before)

    def test_original_legacy_pin_must_match_before_versioning(self):
        legacy = self.legacy()
        legacy.PREPARATION_RUNTIME_PINS[gates.MERGE_MAP_SOURCE] = '0' * 64
        before = legacy.PREPARATION_RUNTIME_PINS.copy()
        with patch.object(gates.subprocess, 'check_output') as git, self.assertRaisesRegex(ValueError, 'legacy'):
            gates.version_map_output_packing(legacy, ROOT, PACKED_FREEZE,
                self.bindings(), gates.MAP_OUTPUT_PACKING_PROFILE)
        git.assert_not_called()
        self.assertEqual(legacy.PREPARATION_RUNTIME_PINS, before)

    def test_inverse_failure_does_not_partially_mutate_the_private_pin_table(self):
        legacy = self.legacy()
        before = legacy.PREPARATION_RUNTIME_PINS.copy()
        with patch.object(gates.subprocess, 'check_output', return_value=self.packed), \
                patch.object(gates, 'project_map_output_packing', side_effect=ValueError('inverse failure')), \
                self.assertRaisesRegex(ValueError, 'inverse failure'):
            gates.version_map_output_packing(legacy, ROOT, PACKED_FREEZE,
                self.bindings(), gates.MAP_OUTPUT_PACKING_PROFILE)
        self.assertEqual(legacy.PREPARATION_RUNTIME_PINS, before)

    def test_omitted_profile_keeps_old_pin_and_performs_no_source_substitution(self):
        legacy = self.legacy()
        table = legacy.PREPARATION_RUNTIME_PINS
        with patch.object(gates.subprocess, 'check_output') as git:
            self.assertIsNone(gates.version_map_output_packing(legacy, ROOT, PACKED_FREEZE, self.bindings()))
        git.assert_not_called()
        self.assertIs(legacy.PREPARATION_RUNTIME_PINS, table)
        self.assertEqual(table[gates.MERGE_MAP_SOURCE], gates.MERGE_MAP_LEGACY_SHA256)

    def test_private_table_copy_cannot_modify_the_immutable_legacy_module_constant(self):
        table = audit_ppo.PREPARATION_RUNTIME_PINS
        before = table.copy()
        legacy = SimpleNamespace(PREPARATION_RUNTIME_PINS=table)
        gates.version_map_output_packing(legacy, ROOT, PACKED_FREEZE,
            self.bindings(), gates.MAP_OUTPUT_PACKING_PROFILE)
        self.assertIsNot(legacy.PREPARATION_RUNTIME_PINS, table)
        self.assertEqual(audit_ppo.PREPARATION_RUNTIME_PINS, before)
        self.assertEqual(table[gates.MERGE_MAP_SOURCE], gates.MERGE_MAP_LEGACY_SHA256)

    def test_real_immutable_legacy_source_gate_still_refuses_packed_source(self):
        with self.assertRaisesRegex(ValueError, 'freeze/worktree SHA mismatch'):
            audit_ppo.verify_frozen_pins(ROOT, PACKED_FREEZE,
                {gates.MERGE_MAP_SOURCE: gates.MERGE_MAP_LEGACY_SHA256}, 'legacy map fixture')

    def test_old_declared_source_cannot_borrow_new_profile(self):
        legacy = self.legacy()
        with self.assertRaisesRegex(ValueError, 'exact declared source'):
            gates.version_map_output_packing(legacy, ROOT, OLD_FREEZE,
                {gates.MERGE_MAP_SOURCE: gates.MERGE_MAP_LEGACY_SHA256}, gates.MAP_OUTPUT_PACKING_PROFILE)

    def public_plan(self, **extra):
        return {'source_bindings': self.bindings(), 'custody_binding': '/unused/binding',
            'seed_rule': 'exact-point-bridge-v2', 'start_graph_rule': 'point-attachment-3x3-v1', **extra}

    def test_public_gate_forwards_only_the_explicit_packing_profile_after_plan_source_check(self):
        plan = self.public_plan(map_output_packing_profile=gates.MAP_OUTPUT_PACKING_PROFILE)
        with patch.object(reach_preparation, 'load_plan', return_value=plan), \
                patch.object(reach_preparation, 'source_check', return_value={'source_checked': True}) as source, \
                patch.object(gates, '_load_versioned_native_gates', return_value='definitions') as inner:
            self.assertEqual(gates.load_native_gates(ROOT, PACKED_FREEZE, '/unused/plan'), 'definitions')
        source.assert_called_once()
        self.assertEqual(inner.call_args.kwargs, {'seed_rule': 'exact-point-bridge-v2',
            'start_graph_rule': 'point-attachment-3x3-v1',
            'map_output_packing_profile': gates.MAP_OUTPUT_PACKING_PROFILE})

    def test_public_undeclared_profile_keeps_the_original_dispatch_default(self):
        with patch.object(reach_preparation, 'load_plan', return_value=self.public_plan()), \
                patch.object(reach_preparation, 'source_check', return_value={}), \
                patch.object(gates, '_load_versioned_native_gates', return_value='old dispatch') as inner:
            self.assertEqual(gates.load_native_gates(ROOT, PACKED_FREEZE, '/unused/plan'), 'old dispatch')
        self.assertNotIn('map_output_packing_profile', inner.call_args.kwargs)

    def test_public_unknown_or_null_declaration_cannot_enter_private_dispatch(self):
        for value in (None, '', 'array-v2', True):
            with self.subTest(value=value), \
                    patch.object(reach_preparation, 'load_plan', return_value=self.public_plan(map_output_packing_profile=value)), \
                    patch.object(reach_preparation, 'source_check', return_value={}), \
                    patch.object(gates, '_load_versioned_native_gates') as inner, self.assertRaises(ValueError):
                gates.load_native_gates(ROOT, PACKED_FREEZE, '/unused/plan')
            inner.assert_not_called()

    def test_map_is_not_added_to_the_automatic_runtime_override_set(self):
        self.assertNotIn(gates.MERGE_MAP_SOURCE, gates.REVISED_RUNTIME)

    def test_immutable_reader_file_hash_is_still_the_original(self):
        self.assertEqual(digest(Path(audit_ppo.__file__).read_bytes()), gates.PPO_READER_SHA256)


if __name__ == '__main__':
    unittest.main()
