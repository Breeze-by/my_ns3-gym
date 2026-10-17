"""New engineering inputs cannot acquire historical capacity comparison credit."""

import ast
import copy
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from mr3_learning import audit_ppo
from mr3_learning.audit_preparation import (
    PREPARATION_PROBE_VERSION, PREPARATION_PROBE_V3, exclude_preparation_capacity_comparison,
)


class PreparationComparisonTests(unittest.TestCase):
    def setUp(self):
        def legacy(metadata, summary):
            return {"eligible": True, "legacy": metadata, "summary": summary}
        self.original = legacy
        self.native_gate = Mock()
        self.auditor = SimpleNamespace(comparison_statistics=legacy,
                                       audit_episode=self.native_gate)
        exclude_preparation_capacity_comparison(self.auditor)

    def fixture(self, workers=2):
        schedule = [['open', 101]]
        if workers == 2:
            schedule += [['open', 101], ['rooms', 101], ['corridors', 101]]
        metadata = {"workers": workers, "schedule": schedule, "steps_per_episode": 20,
                    "preparation_motion_probe": True,
                    "preparation_probe_version": PREPARATION_PROBE_VERSION,
                    "terminal_probe": False, "deadline_probe": False, "fault_probe": False,
                    "freeze": "a" * 40}
        return metadata, copy.deepcopy(metadata)

    def test_only_declared_new_fixtures_are_ineligible_without_changing_episode_gate(self):
        for workers in (1, 2):
            metadata, summary = self.fixture(workers)
            result = self.auditor.comparison_statistics(metadata, summary)
            self.assertFalse(result["eligible"])
            self.assertTrue(result["native_episode_gates_unchanged"])
            self.assertIs(self.auditor.audit_episode, self.native_gate)

    def test_v3_only_excludes_its_32_step_workload_and_preserves_native_gates(self):
        for workers in (1, 2):
            metadata, summary = self.fixture(workers)
            for row in (metadata, summary):
                row.update(preparation_probe_version=PREPARATION_PROBE_V3, steps_per_episode=32)
            result = self.auditor.comparison_statistics(metadata, summary)
            self.assertFalse(result["eligible"])
            self.assertEqual(result["preparation_probe_version"], PREPARATION_PROBE_V3)
            self.assertIs(self.auditor.audit_episode, self.native_gate)
            for steps in (20, 40, 32.):
                metadata["steps_per_episode"] = summary["steps_per_episode"] = steps
                with self.subTest(workers=workers, steps=steps), self.assertRaises(ValueError):
                    self.auditor.comparison_statistics(metadata, summary)

    def test_legacy_and_old_preparation_records_keep_original_comparison(self):
        for metadata in ({}, {"preparation_motion_probe": True, "steps_per_episode": 16},
                         {"preparation_motion_probe": True, "steps_per_episode": 16,
                          "preparation_probe_version": "mr3-p2a0-outward-cancel-v1"}):
            summary = {"retained": "old result"}
            self.assertEqual(self.auditor.comparison_statistics(metadata, summary),
                             self.original(metadata, summary))

    def test_unknown_budget_seed_flags_or_summary_cannot_skip_comparison(self):
        for field, value in (("workers", 4), ("steps_per_episode", 16),
                             ("preparation_motion_probe", False), ("fault_probe", True),
                             ("schedule", [['open', 101], ['open', 101],
                                           ['rooms', 202], ['corridors', 303]])):
            metadata, summary = self.fixture()
            metadata[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.auditor.comparison_statistics(metadata, summary)
        metadata, summary = self.fixture()
        summary["freeze"] = "b" * 40
        with self.assertRaises(ValueError):
            self.auditor.comparison_statistics(metadata, summary)

    def test_numeric_aliases_and_summary_type_or_flag_changes_are_rejected(self):
        for field, value in (("workers", True), ("workers", 2.),
                             ("steps_per_episode", 20.),
                             ("schedule", [['open', 101.], ['open', 101],
                                           ['rooms', 101], ['corridors', 101]])):
            for side in ("metadata", "summary"):
                metadata, summary = self.fixture(1 if value is True else 2)
                (metadata if side == "metadata" else summary)[field] = value
                with self.subTest(side=side, field=field), self.assertRaises(ValueError):
                    self.auditor.comparison_statistics(metadata, summary)
        for field in ("terminal_probe", "deadline_probe", "fault_probe"):
            metadata, summary = self.fixture()
            summary[field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.auditor.comparison_statistics(metadata, summary)

    def test_real_immutable_legacy_comparison_keeps_old_sixteen_step_failure(self):
        root = next(parent for parent in Path(__file__).resolve().parents
                    if (parent / ".git").exists())
        relative = audit_ppo.ROS + "scripts/audit_mr3_env.py"
        source = subprocess.check_output(
            ["git", "show", audit_ppo.TASK_BASE_FREEZE + ":" + relative], cwd=root, text=True)
        definitions = [node for node in ast.parse(source).body
                       if isinstance(node, ast.FunctionDef)
                       and node.name in ("require", "number", "comparison_statistics")]
        self.assertEqual(len(definitions), 3)
        namespace = {"math": math}
        exec(compile(ast.Module(body=definitions, type_ignores=[]),
                     audit_ppo.TASK_BASE_FREEZE + ":" + relative, "exec"), namespace)
        original = namespace["comparison_statistics"]
        auditor = SimpleNamespace(comparison_statistics=original, audit_episode=self.native_gate)
        exclude_preparation_capacity_comparison(auditor)
        metadata, summary = self.fixture()
        metadata.pop("preparation_probe_version")
        metadata["steps_per_episode"] = 16
        for comparison in (original, auditor.comparison_statistics):
            with self.assertRaisesRegex(ValueError, "extra scenes differ"):
                comparison(metadata, summary)
        self.assertIs(auditor.audit_episode, self.native_gate)


if __name__ == "__main__":
    unittest.main()
