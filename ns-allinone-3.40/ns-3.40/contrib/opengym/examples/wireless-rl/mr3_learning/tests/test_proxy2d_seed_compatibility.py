"""Artificial received inputs only; no World, scene or historical consumer.

The existing archive fixture manufactures all seven payload roles locally.
Git/source reads below are mocked; they never certify an actual source freeze.
"""

import copy
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from mr3_learning import audit_proxy2d as audit
from mr3_learning import proxy2d_conformity as conformity
from mr3_learning.proxy2d_codec import encode_arrays
from mr3_learning.tests import test_audit_proxy2d as actors
from mr3_learning.tests import test_proxy2d_conformity as archives


class SeedCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = audit.PureBuilder()

    @classmethod
    def tearDownClass(cls):
        cls.builder.close()

    def artificial_params(self, sequence=1, now=1.):
        helper = actors.ProxyAuditTests()
        params = helper.params(sequence, now)
        grid = np.zeros((41, 41), dtype=np.int8)
        grid[23, 26] = 100
        # Same fixed positive counterexample as the independently-oracled
        # kernel tests: old triangle lower bound <.29, exact point+bridge safe.
        params.update(raw_grid=grid, resolution=.05, origin=[-1.025, -1.025])
        for robot in params["robots"]:
            robot.update(x=0., y=-.01152683769727414)
        for entry in params["navigation_maps"].values():
            entry.update(grid=grid.copy(), resolution=.05, origin=params["origin"])
        return params

    def save_actor(self, directory, params):
        encoded = audit.canonical(encode_arrays(params))
        digest = audit.sha(encoded)
        path = directory / f"inputs/{digest}.json.gz"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(gzip.compress(encoded, mtime=0))
        snapshot = self.builder(**params)
        return {"epoch": params["epoch"], "snapshot": snapshot,
                "tensor_proofs": audit.tensor_proofs(snapshot),
                "actor_input_ref": {"path": str(path.relative_to(directory)), "sha256": digest}}

    def test_default_and_explicit_legacy_canonical_bytes_are_identical(self):
        params = self.artificial_params()
        default = self.builder(**params)
        explicit = self.builder(**params, seed_rule="legacy")
        self.assertEqual(audit.canonical(default), audit.canonical(explicit))
        self.assertNotIn("seed_rule", default["candidate_rule"])

    def test_exact_actor_has_all_robot_seed_checks_without_full_candidate_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            params = self.artificial_params()
            params["seed_rule"] = audit.EXACT_SEED_RULE
            row = self.save_actor(Path(temporary), params)
            before = self.builder.build_calls
            report, _ = audit.actor_record(temporary, row, builder=self.builder)
            self.assertFalse(report["full_snapshot_rebuilt"])
            self.assertEqual(report["exact_seed_robot_checks"], 3)
            self.assertEqual(self.builder.build_calls, before)
            self.assertEqual(row["snapshot"]["candidate_rule"]["version"], audit.EXACT_NAVIGATION_RULE)
            for metadata in row["snapshot"]["path_maps"].values():
                self.assertLess(metadata["seed_pose_clearance_lower_bound_m"], .29)
                self.assertIsNone(metadata["seed_rejection_reason"])
                self.assertTrue(metadata["seed_point_bridge_certificate"]["accepted"])

    def test_seed_only_provenance_rejects_stale_cross_epoch_and_future_map(self):
        for case in ("state", "epoch", "future", "unknown", "cell_gate", "empty"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                params = self.artificial_params()
                params["seed_rule"] = audit.EXACT_SEED_RULE
                entry = params["navigation_maps"]["tb1"]
                if case == "state":
                    params["robots"][0]["source_stamp"] = 0.
                elif case == "epoch":
                    entry["epoch"] = "another-epoch"
                elif case == "future":
                    entry["source_stamp"] = 2.
                elif case == "unknown":
                    entry["grid"][20, 20] = -1
                elif case == "cell_gate":
                    entry["grid"][20, 21] = 100
                else:
                    entry["grid"] = np.empty((0, 0), dtype=np.int8)
                if case == "future":
                    # The pure builder/seed reader both preserve the future-map
                    # refusal. The existing encoder additionally refuses to
                    # encode that future-source snapshot at all; it must not be
                    # manufactured into a supposedly legal actor record.
                    checked = self.builder.seed_checks(**params)["tb1"]
                    self.assertEqual(checked["seed_rejection_reason"], "future_map")
                    self.assertEqual(checked["seed_rule"], audit.EXACT_SEED_RULE)
                    self.assertIsNone(checked["seed_point_bridge_certificate"])
                    with self.assertRaisesRegex(ValueError, "refers to a future source"):
                        self.save_actor(Path(temporary), params)
                    continue
                row = self.save_actor(Path(temporary), params)
                report, _ = audit.actor_record(temporary, row, builder=self.builder)
                self.assertEqual(report["exact_seed_robot_checks"], 3)
                self.assertIsNotNone(row["snapshot"]["path_maps"]["tb1"]["seed_rejection_reason"])

    def test_rehashed_forged_certificate_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            params = self.artificial_params(); params["seed_rule"] = audit.EXACT_SEED_RULE
            row = self.save_actor(Path(temporary), params)
            row["snapshot"]["path_maps"]["tb1"]["seed_point_bridge_certificate"]["accepted"] = False
            row["snapshot"]["digest"] = audit.sha(audit.canonical(
                {key: value for key, value in row["snapshot"].items() if key != "digest"}))
            row["tensor_proofs"] = audit.tensor_proofs(row["snapshot"])
            with self.assertRaisesRegex(ValueError, "point/bridge certificate differs"):
                audit.actor_record(temporary, row, builder=self.builder)

    def test_actor_seed_parameter_and_snapshot_contract_cannot_be_mixed(self):
        for case in ("version", "field", "unknown"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                params = self.artificial_params(); params["seed_rule"] = audit.EXACT_SEED_RULE
                row = self.save_actor(Path(temporary), params)
                if case == "version":
                    row["snapshot"]["candidate_rule"]["version"] = "mr3-navigation-geometric-staging-v5"
                elif case == "field":
                    del row["snapshot"]["candidate_rule"]["seed_rule"]
                else:
                    params["seed_rule"] = "unversioned"
                    raw = audit.canonical(encode_arrays(params)); digest = audit.sha(raw)
                    path = Path(temporary) / f"inputs/{digest}.json.gz"
                    path.write_bytes(gzip.compress(raw, mtime=0))
                    row["actor_input_ref"] = {"path": str(path.relative_to(temporary)), "sha256": digest}
                with self.assertRaises(ValueError):
                    audit.actor_record(temporary, row, builder=self.builder)

    def test_exact_trace_preserves_three_full_rebuilds_and_all_seed_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            helper = actors.ProxyAuditTests(); helper.builder = self.builder
            original = helper.params
            def exact_params(*args, **kwargs):
                return {**original(*args, **kwargs), "seed_rule": audit.EXACT_SEED_RULE}
            helper.params = exact_params
            rows = helper.fixture(directory, count=4)
            helper.write(directory, rows)
            result = audit.audit_episode(directory, "a" * 40, verify_sources=False, builder=self.builder)
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["full_rebuild_event_sequences"], [1, 3, 9])
            self.assertEqual(result["verified_exact_seed_actor_records"], 5)
            self.assertEqual(result["verified_exact_seed_robot_checks"], 15)

    def fake_git(self, inventory=None):
        def read(argv, **unused):
            version, relative = argv[-1].split(":", 1)
            if relative.endswith("report/assets/20261020_mr3_p2a_v21/native_inventory_v1.json"):
                return inventory
            if version == conformity.NATIVE_FREEZE and relative.endswith("/mr3_observation.py"):
                return b"immutable manufactured V21 observation source\n"
            return (audit.ROOT / relative).read_bytes()
        return read

    def test_original_v1_whole_source_gate_still_rejects_changed_observation(self):
        with patch.object(conformity.subprocess, "check_output", side_effect=self.fake_git()):
            with self.assertRaisesRegex(ValueError, "V21 observation/encoder source changed"):
                conformity.source_bindings("a" * 40)
            proof, _ = conformity.source_bindings("a" * 40, audit.EXACT_SEED_RULE)
        relative = (audit.PURE / "mr3_observation.py").relative_to(audit.ROOT).as_posix()
        self.assertEqual(proof[relative]["legacy_reference"]["sha256"],
                         audit.sha(b"immutable manufactured V21 observation source\n"))
        self.assertNotIn("native_git_source", proof[relative])

    def seed_probe_summary(self):
        cells = [["open", 101], ["rooms", 101], ["corridors", 101]]
        spec = {"schema": "mr3-proxy2d-activity-spec-v1", "kind": "seed_probe", "groups": [3],
                "cells": cells, "worker_cells": [[[["open", 101]], [["rooms", 101]], [["corridors", 101]]]],
                "steps_per_episode": 64, "max_attempts": 192, "activity_seconds": 1800}
        return {"activity_kind": "seed_probe", "activity_spec": spec, "profile_enabled": False,
                "scheduled_cells": cells, "seed_rule": audit.EXACT_SEED_RULE}

    def test_seed_probe_has_exact_fixed_schedule_and_short_credit_scope(self):
        contract = audit._activity_contract(self.seed_probe_summary())
        self.assertEqual(contract["group_wall_seconds"], [900])
        self.assertEqual(contract["steps_per_episode"], 64)
        self.assertEqual(contract["max_attempts"], 192)
        self.assertEqual(contract["groups"], [3])

    def test_seed_probe_cannot_change_rule_schedule_budget_or_add_spec_fields(self):
        for case in ("rule", "workers", "seed", "steps", "budget", "extra"):
            with self.subTest(case=case):
                summary = self.seed_probe_summary()
                spec = summary["activity_spec"]
                if case == "rule": summary["seed_rule"] = "legacy"
                elif case == "workers": spec["groups"] = [1, 4]
                elif case == "seed": spec["worker_cells"][0][1][0][1] = 103
                elif case == "steps": spec["steps_per_episode"] = 65
                elif case == "budget": spec["activity_seconds"] = 1801
                else: spec["allow_retry"] = True
                with self.assertRaises(ValueError):
                    audit._activity_contract(summary)

    def exact_formal_fixture(self, directory):
        """Reuse existing v1 synthetic receipts and complete invented archive."""
        helper = actors.ProxyAuditTests(); helper.builder = self.builder
        formal, _ = helper.conformity_fixture(directory / "synthetic_fixture")
        archive_helper = archives.ConformityTests(); archive_helper.builder = self.builder
        inputs, _ = archive_helper.archive_fixture(directory / "archive")
        inventory_raw = inputs.inventory_path.read_bytes()
        git = self.fake_git(inventory_raw)
        with patch.object(conformity.subprocess, "check_output", side_effect=git):
            proof, _ = conformity.source_bindings("a" * 40, audit.EXACT_SEED_RULE)
        formal.update(schema="mr3-proxy2d-conformity-v2", seed_rule=audit.EXACT_SEED_RULE,
            source_proof=proof, native_inventory={"path": str(inputs.inventory_path),
                "sha256": audit.sha(inventory_raw), "bytes": len(inventory_raw)},
            native_records=conformity.replay_native(inputs, self.builder),
            exact_records=conformity.replay_exact_native(inputs, self.builder, directory / "exact"))
        formal["native_input_index"] = inputs.proofs
        # Make the existing hidden-actor comparison explicit about exact mode.
        case = next(case for case in formal["synthetic_cases"]
                    if case["id"] == "hidden_obstacle_same_received_actor")
        actor = {"parameters": {"seed_rule": audit.EXACT_SEED_RULE},
                 "snapshot": {"candidate_rule": {"seed_rule": audit.EXACT_SEED_RULE,
                              "version": audit.EXACT_NAVIGATION_RULE}}}
        hashes = {"actor_parameters_sha256": audit.sha(audit.canonical(actor["parameters"])),
                  "snapshot_sha256": audit.sha(audit.canonical(actor["snapshot"]))}
        for spec in case["input_refs"]:
            if Path(spec["path"]).name.startswith("hidden_actor_"):
                raw = audit.canonical(actor); Path(spec["path"]).write_bytes(raw)
                spec.update(sha256=audit.sha(raw), bytes=len(raw))
        case.update(expected=hashes, actual=copy.deepcopy(hashes))
        synthetic = {"cases": formal["synthetic_cases"], "native_runs": 0, "gpu_calls": 0,
                     "optimizer_steps": 0, "seed_rule": audit.EXACT_SEED_RULE}
        raw = audit.canonical(synthetic); spec = formal["synthetic_result_ref"]
        Path(spec["path"]).write_bytes(raw); spec.update(sha256=audit.sha(raw), bytes=len(raw))
        return formal, git

    def test_v2_independent_review_binds_same_inputs_and_rebuilds_exact_six(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            formal, git = self.exact_formal_fixture(directory)
            path = directory / "formal.json"; path.write_bytes(audit.canonical(formal))
            with patch.object(audit.subprocess, "check_output", side_effect=git):
                report = audit.audit_conformity(directory, path, "a" * 40)
            self.assertTrue(report["passed"], report["errors"])
            self.assertEqual(len(report["native_records"]), 6)
            self.assertEqual(len(report["exact_records"]), 6)
            self.assertEqual(report["additional_native_snapshot_replays"], 6)
            self.assertEqual(report["additional_native_runs"], 0)
            self.assertEqual(report["additional_current_version_snapshot_replays"], 6)
            self.assertFalse(report["formal_producer_pass_flags_used"])
            self.assertFalse(report["native_credit"])

    def test_v2_altered_exact_input_hash_fails_and_closes_its_builder(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            formal, git = self.exact_formal_fixture(directory)
            formal["exact_records"][0]["legacy_parameters_sha256"] = "0" * 64
            path = directory / "formal.json"; path.write_bytes(audit.canonical(formal))
            with patch.object(audit.subprocess, "check_output", side_effect=git):
                report = audit.audit_conformity(directory, path, "a" * 40)
            self.assertFalse(report["passed"])
            self.assertTrue(any("same original sufficient parameters" in error for error in report["errors"]))
            self.assertTrue(report["pure_builder_failure_wait"]["actual_waited"])


if __name__ == "__main__":
    unittest.main()
