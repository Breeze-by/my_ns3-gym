"""Fixed artificial received inputs only; no World, scene or native archive."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from mr3_learning import audit_proxy2d as audit
from mr3_learning import proxy2d_capacity as capacity
from mr3_learning import proxy2d_conformity as conformity
from mr3_learning.proxy2d import ProxySupervisor
from mr3_learning.proxy2d_codec import encode_arrays


class PointGraphProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = audit.PureBuilder()

    @classmethod
    def tearDownClass(cls):
        cls.builder.close()

    def params(self):
        params = conformity.point_graph_parameters("free_centre")
        params["start_graph_rule"] = audit.POINT_START_GRAPH
        return params

    def save_actor(self, directory, params):
        encoded = audit.canonical(encode_arrays(params))
        relative = "inputs/" + audit.sha(encoded) + ".json.gz"
        path = directory / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(gzip.compress(encoded, mtime=0))
        snapshot = self.builder(**params)
        return {"epoch": params["epoch"], "snapshot": snapshot,
                "actor_input_ref": {"path": relative, "sha256": audit.sha(encoded)},
                "tensor_proofs": audit.tensor_proofs(snapshot)}

    def summary(self, kind):
        spec = capacity.activity_spec(kind)
        return {"activity_spec": spec, "activity_kind": kind,
                "profile_enabled": kind == audit.POINT_GRAPH_PROFILE,
                "scheduled_cells": spec["cells"], "seed_rule": audit.EXACT_SEED_RULE_V2,
                "start_graph_rule": audit.POINT_START_GRAPH}

    def test_profile_and_short_exact_fixed_specs_match_only_their_original_schedules(self):
        for new, old, walls in ((audit.POINT_GRAPH_PROFILE, "karto_profile", [240]),
                                (audit.POINT_GRAPH_KIND, "seed_probe_v2", [900])):
            with self.subTest(kind=new):
                spec = capacity.activity_spec(new)
                baseline = capacity.activity_spec(old)
                self.assertEqual({**baseline, "kind": new}, spec)
                self.assertEqual(audit._activity_contract(self.summary(new))["group_wall_seconds"], walls)
                altered = copy.deepcopy(spec)
                altered["steps_per_episode"] += 1
                with self.assertRaises(ValueError):
                    capacity.validate_activity_spec(altered)

    def test_activity_and_rule_pair_cannot_borrow_old_spec(self):
        for kind in (audit.POINT_GRAPH_PROFILE, audit.POINT_GRAPH_KIND):
            summary = self.summary(kind)
            for key, value in (("seed_rule", audit.EXACT_SEED_RULE),
                               ("start_graph_rule", audit.ORIGINAL_START_GRAPH)):
                forged = {**summary, key: value}
                with self.subTest(kind=kind, key=key), self.assertRaises(ValueError):
                    audit._activity_contract(forged)
        old = self.summary("seed_probe_v2")
        with self.assertRaises(ValueError):
            audit._activity_contract(old)

    def test_supervisor_refuses_wrong_seed_before_directory_or_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "must_not_exist"
            for seed in ("legacy", audit.EXACT_SEED_RULE):
                with self.subTest(seed=seed), self.assertRaises(ValueError):
                    ProxySupervisor(directory, seed_rule=seed, start_graph_rule=audit.POINT_START_GRAPH)
                self.assertFalse(directory.exists())

    def test_collector_refuses_missing_new_start_before_collection(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(capacity, "collect_worker") as collect_worker:
                with self.assertRaisesRegex(ValueError, "start graph rule"):
                    capacity.collect(Path(temporary), "a" * 40, {}, {}, 1, 600_000_000_001,
                        activity_spec=capacity.activity_spec(audit.POINT_GRAPH_PROFILE),
                        group_wall_seconds=[240], profile=True, seed_rule=audit.EXACT_SEED_RULE_V2)
                collect_worker.assert_not_called()

    def test_default_original_start_snapshot_bytes_and_metadata_remain_omitted(self):
        for seed in ("legacy", audit.EXACT_SEED_RULE, audit.EXACT_SEED_RULE_V2):
            params = conformity.point_graph_parameters("free_centre")
            if seed == "legacy":
                params.pop("seed_rule")
            else:
                params["seed_rule"] = seed
            default = self.builder(**params)
            explicit = self.builder(**params, start_graph_rule=audit.ORIGINAL_START_GRAPH)
            self.assertEqual(audit.canonical(default), audit.canonical(explicit))
            self.assertNotIn("start_graph_rule", default["candidate_rule"])
            self.assertTrue(all("point_graph_attachment" not in entry for entry in default["path_maps"].values()))

    def test_new_actor_all_three_attachment_checks_without_full_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            row = self.save_actor(Path(temporary), self.params())
            before = self.builder.build_calls
            report, _ = audit.actor_record(temporary, row, builder=self.builder)
            self.assertEqual(self.builder.build_calls, before)
            self.assertEqual(report["point_graph_robot_checks"], 3)
            self.assertEqual(report["exact_seed_robot_checks"], 3)
            self.assertEqual(row["snapshot"]["candidate_rule"]["version"], audit.POINT_NAVIGATION_RULE)
            self.assertTrue(all(entry["point_graph_attachment"]["accepted"]
                                for entry in row["snapshot"]["path_maps"].values()))

    def test_rehashed_attachment_tamper_is_rejected_by_light_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            row = self.save_actor(Path(temporary), self.params())
            row["snapshot"]["path_maps"]["tb1"]["point_graph_attachment"]["anchors"] = []
            row["snapshot"]["digest"] = audit.sha(audit.canonical({
                key: value for key, value in row["snapshot"].items() if key != "digest"}))
            row["tensor_proofs"] = audit.tensor_proofs(row["snapshot"])
            with self.assertRaisesRegex(ValueError, "certificate differs"):
                audit.actor_record(temporary, row, builder=self.builder)

    def test_light_start_metadata_retains_missing_empty_epoch_future_and_stale_state(self):
        for case, reason in (("missing", "missing_received_navigation_map"),
                             ("empty", "empty_received_own_map"), ("epoch", "cross_epoch"),
                             ("future", "future_map"), ("state", "state_missing_or_stale")):
            params = self.params()
            entry = params["navigation_maps"]["tb1"]
            if case == "missing":
                del params["navigation_maps"]["tb1"]
            elif case == "empty":
                entry["grid"] = np.empty((0, 0), dtype=np.int16)
            elif case == "epoch":
                entry["epoch"] = "wrong"
            elif case == "future":
                entry["source_stamp"] = 2.
            else:
                params["robots"][0]["source_stamp"] = 0.
            with self.subTest(case=case):
                checked = self.builder.seed_checks(**params)["tb1"]
                self.assertEqual(checked["start_graph_rejection_reason"], reason)
                self.assertIsNone(checked["point_graph_attachment"])

    def fake_git(self, argv, **unused):
        relative = argv[-1].split(":", 1)[1]
        return (audit.ROOT / relative).read_bytes()

    def test_six_artificial_pairs_rebuilt_independently_without_native_or_world(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "formal.json"
            with patch.object(conformity.subprocess, "check_output", side_effect=self.fake_git), \
                    patch.object(conformity, "NativeInputs", side_effect=AssertionError("native forbidden")), \
                    patch.object(conformity, "synthetic_cases", side_effect=AssertionError("World forbidden")):
                formal = conformity.run_point_graph("a" * 40, output)
                self.assertTrue(formal["passed"], formal["errors"])
                # Deliberately false producer flag: comparisons determine review.
                formal["passed"] = False
                output.write_bytes(audit.canonical(formal))
                review, _ = audit.verify_conformity(temporary, {
                    "path": str(output), "sha256": audit.sha(output.read_bytes())}, "a" * 40)
            self.assertTrue(review["passed"])
            self.assertEqual(review["full_snapshots_rebuilt"], 12)
            self.assertEqual(review["point_graph_robot_checks"], 18)
            self.assertEqual([record["id"] for record in review["pair_records"]], list(conformity.POINT_GRAPH_CASES))
            self.assertFalse(review["native_reference_checked"])
            self.assertFalse(review["native_credit"])
            self.assertTrue(review["independent_point_graph_builder_actual_wait"]["actual_waited"])

    def test_new_cli_dispatch_cannot_reuse_old_native_or_world_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "formal.json"
            result = {"passed": True}
            with patch.object(conformity, "run_point_graph", return_value=result) as run, \
                    patch.object(conformity, "run", side_effect=AssertionError("old entry forbidden")):
                self.assertEqual(conformity.main(["--freeze", "a" * 40, "--seed-rule", audit.EXACT_SEED_RULE_V2,
                    "--start-graph-rule", audit.POINT_START_GRAPH, "--output", str(output)]), 0)
                run.assert_called_once_with("a" * 40, output)


if __name__ == "__main__":
    unittest.main()
