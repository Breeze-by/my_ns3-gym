"""Artificial v2 compatibility inputs only; no World or original-data consumer."""

import copy
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from mr3_learning import audit_proxy2d as audit
from mr3_learning import proxy2d_conformity as conformity
from mr3_learning.tests import test_proxy2d_seed_compatibility as v1


class SeedV2CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = audit.PureBuilder()

    @classmethod
    def tearDownClass(cls):
        cls.builder.close()

    def helper(self):
        helper = v1.SeedCompatibilityTests()
        helper.builder = self.builder
        return helper

    def boundary_params(self):
        params = self.helper().artificial_params()
        grid = np.zeros((61, 81), dtype=np.int8)
        grid[43, 66] = 100
        params.update(raw_grid=grid, resolution=.05, origin=[-2., -2.])
        for robot in params["robots"]:
            robot.update(x=1., y=0.)
        for entry in params["navigation_maps"].values():
            entry.update(grid=grid.copy(), resolution=.05, origin=[-2., -2.])
        return params

    def test_v1_boundary_rejection_retained_and_v2_uses_exact_floor(self):
        helper = self.helper()
        params = self.boundary_params()
        expected_cell = [int((Fraction(value) - Fraction(-2.)) // Fraction(.05)) for value in (0., 1.)]
        self.assertEqual(expected_cell, [39, 59])
        with tempfile.TemporaryDirectory() as temporary:
            old = helper.save_actor(Path(temporary), {**params, "seed_rule": audit.EXACT_SEED_RULE})
            new = helper.save_actor(Path(temporary), {**params, "seed_rule": audit.EXACT_SEED_RULE_V2})
            for name in ("tb1", "tb2", "tb3"):
                before, after = (row["snapshot"]["path_maps"][name] for row in (old, new))
                self.assertEqual(before["seed_cell"], [40, 60])
                self.assertEqual(before["seed_point_bridge_certificate"]["reason"], "pose_not_in_original_seed_cell")
                self.assertEqual(after["seed_cell"], expected_cell)
                self.assertIsNone(after["seed_rejection_reason"])
                self.assertEqual(after["seed_rule"], audit.EXACT_SEED_RULE_V2)
            for row in (old, new):
                checked, _ = audit.actor_record(temporary, row, builder=self.builder)
                self.assertEqual(checked["exact_seed_robot_checks"], 3)

    def test_v2_canonical_seed_still_requires_original_free_cell_graph_gate(self):
        params = self.boundary_params()
        params["seed_rule"] = audit.EXACT_SEED_RULE_V2
        params["navigation_maps"]["tb1"]["grid"][39, 59] = -1
        with tempfile.TemporaryDirectory() as temporary:
            row = self.helper().save_actor(Path(temporary), params)
            checked, _ = audit.actor_record(temporary, row, builder=self.builder)
            actual = row["snapshot"]["path_maps"]["tb1"]
            self.assertEqual(actual["seed_cell"], [39, 59])
            self.assertEqual(actual["seed_rejection_reason"], "seed_cell_unknown")
            self.assertIsNone(actual["seed_point_bridge_certificate"])
            self.assertEqual(checked["exact_seed_robot_checks"], 3)

    def test_v2_light_checks_selected_rule_without_full_candidate_replay(self):
        params = self.helper().artificial_params()
        params["seed_rule"] = audit.EXACT_SEED_RULE_V2
        with tempfile.TemporaryDirectory() as temporary:
            row = self.helper().save_actor(Path(temporary), params)
            before = self.builder.build_calls
            checked, _ = audit.actor_record(temporary, row, builder=self.builder)
            self.assertEqual(self.builder.build_calls, before)
            self.assertFalse(checked["full_snapshot_rebuilt"])
            self.assertEqual(checked["seed_rule"], audit.EXACT_SEED_RULE_V2)
            self.assertEqual(row["snapshot"]["candidate_rule"]["version"],
                             "mr3-navigation-geometric-staging-v7-exact-seed-v2")

    def test_v1_v2_actor_versions_and_rule_fields_cannot_be_mixed(self):
        params = self.helper().artificial_params(); params["seed_rule"] = audit.EXACT_SEED_RULE_V2
        with tempfile.TemporaryDirectory() as temporary:
            row = self.helper().save_actor(Path(temporary), params)
            for key, value in (("version", audit.EXACT_NAVIGATION_RULE), ("seed_rule", audit.EXACT_SEED_RULE)):
                with self.subTest(key=key):
                    altered = copy.deepcopy(row)
                    altered["snapshot"]["candidate_rule"][key] = value
                    with self.assertRaises(ValueError):
                        audit.actor_record(temporary, altered, builder=self.builder)

    def test_probe_kind_requires_its_exact_v1_or_v2_rule_and_fixed_schedule(self):
        for kind, rule in audit.SEED_PROBE_RULES.items():
            with self.subTest(kind=kind):
                summary = self.helper().seed_probe_summary()
                summary["activity_kind"] = summary["activity_spec"]["kind"] = kind
                summary["seed_rule"] = rule
                if kind == audit.POINT_GRAPH_KIND:
                    summary["start_graph_rule"] = audit.POINT_START_GRAPH
                selected = audit._activity_contract(summary)
                self.assertEqual(selected["group_wall_seconds"], [900])
                self.assertEqual((selected["steps_per_episode"], selected["max_attempts"], selected["activity_seconds"]),
                                 (64, 192, 1800))
                summary["seed_rule"] = next(other for other in audit.EXACT_SEED_RULES if other != rule)
                with self.assertRaises(ValueError):
                    audit._activity_contract(summary)

    def test_v2_conformity_preserves_whole_legacy_reference_and_independent_exact_six(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            formal, git = self.helper().exact_formal_fixture(directory, audit.EXACT_SEED_RULE_V2)
            path = directory / "formal.json"; path.write_bytes(audit.canonical(formal))
            with patch.object(audit.subprocess, "check_output", side_effect=git):
                result = audit.audit_conformity(directory, path, "a" * 40)
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["seed_rule"], audit.EXACT_SEED_RULE_V2)
            self.assertEqual(len(result["native_records"]), 6)
            self.assertEqual(len(result["exact_records"]), 6)
            self.assertTrue(all(row["seed_rule"] == audit.EXACT_SEED_RULE_V2
                                and row["current_legacy_snapshot_and_tensors_equal_original"]
                                for row in result["exact_records"]))
            self.assertEqual(result["additional_native_runs"], 0)
            self.assertFalse(result["qualification"])
            self.assertFalse(result["training_eligible"])

    def test_v2_conformity_cannot_borrow_one_v1_exact_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            formal, git = self.helper().exact_formal_fixture(directory, audit.EXACT_SEED_RULE_V2)
            formal["exact_records"][0]["seed_rule"] = audit.EXACT_SEED_RULE
            path = directory / "formal.json"; path.write_bytes(audit.canonical(formal))
            with patch.object(audit.subprocess, "check_output", side_effect=git):
                result = audit.audit_conformity(directory, path, "a" * 40)
            self.assertFalse(result["passed"])
            self.assertTrue(any("version/reference source differs" in error for error in result["errors"]))
            self.assertTrue(result["pure_builder_failure_wait"]["actual_waited"])

    def test_v2_source_admission_does_not_remove_legacy_whole_byte_gate(self):
        helper = self.helper()
        with patch.object(conformity.subprocess, "check_output", side_effect=helper.fake_git()):
            with self.assertRaisesRegex(ValueError, "V21 observation/encoder source changed"):
                conformity.source_bindings("a" * 40, "legacy")
            proof, _ = conformity.source_bindings("a" * 40, audit.EXACT_SEED_RULE_V2)
        relative = (audit.PURE / "mr3_observation.py").relative_to(audit.ROOT).as_posix()
        self.assertEqual(proof[relative]["legacy_reference"]["sha256"],
                         audit.sha(b"immutable manufactured V21 observation source\n"))


if __name__ == "__main__":
    unittest.main()
