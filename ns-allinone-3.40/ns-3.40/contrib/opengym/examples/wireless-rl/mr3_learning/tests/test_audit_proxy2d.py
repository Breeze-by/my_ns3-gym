"""Synthetic actor/trace fixtures only; no proxy environment or native run."""

import copy
import gzip
import json
from pathlib import Path
import random
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from mr3_learning import audit_proxy2d as audit
from mr3_learning.proxy2d_codec import encode_arrays


class ProxyAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = audit.PureBuilder()

    @classmethod
    def tearDownClass(cls):
        cls.builder.close()

    def params(self, sequence, now):
        grid = np.zeros((16, 16), dtype=np.int8)
        robots = [{"name": name, "epoch": "fixture-epoch", "x": float(index - 1), "y": 0.,
                   "yaw": 0., "v": 0., "w": 0., "valid": True,
                   "source_stamp": now, "received_stamp": now,
                   "navigation": {"phase": "idle"}, "history": []}
                  for index, name in enumerate(("tb1", "tb2", "tb3"))]
        navigation = {name: {"grid": grid.copy(), "resolution": .5, "origin": [-4., -4.],
                            "epoch": "fixture-epoch", "version": sequence,
                            "source_stamp": now, "received_stamp": now,
                            "payload_sha256": "b" * 64,
                            "composition_version": audit.CONTRACT}
                      for name in ("tb1", "tb2", "tb3")}
        return {"raw_grid": grid, "resolution": .5, "origin": [-4., -4.], "robots": robots,
                "now": now, "epoch": "fixture-epoch", "map_version": sequence,
                "sequence": sequence, "map_source_stamp": now, "map_received_stamp": now,
                "map_sources": {}, "task_start": 1., "navigation_maps": navigation}

    def actor(self, directory, sequence, now, event, event_sequence):
        params = self.params(sequence, now)
        snapshot = self.builder(**params)
        encoded = audit.canonical(encode_arrays(params))
        digest = audit.sha(encoded)
        relative = f"inputs/{digest}.json.gz"
        path = directory / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(gzip.compress(encoded, mtime=0))
        return {"schema": audit.SCHEMA, "event": event, "event_sequence": event_sequence,
                "env_id": 0, "episode_index": 1, "epoch": "fixture-epoch", "proxy_only": True,
                "actor_input_ref": {"path": relative, "sha256": digest}, "snapshot": snapshot,
                "tensor_proofs": audit.tensor_proofs(snapshot), "dt": 0. if event == "reset" else 1.,
                "physical_dt": 0. if event == "reset" else 1., "reward": 0.,
                "terminated": False, "truncated": False, "reason": None}

    def fixture(self, directory, count=2):
        rows = [self.actor(directory, 1, 1., "reset", 1)]
        for index in range(count):
            previous = rows[-1]["snapshot"]
            action = next(i for i, valid in enumerate(previous["joint_action_mask"]) if valid)
            rows.append({"schema": audit.SCHEMA, "event": "step_attempt",
                         "event_sequence": len(rows) + 1, "env_id": 0, "episode_index": 1,
                         "epoch": "fixture-epoch", "proxy_only": True,
                         "action": action, "preceding_digest": previous["digest"],
                         "candidate_version": previous["candidate_version"],
                         "joint_action_mask": previous["joint_action_mask"]})
            rows.append(self.actor(directory, index + 2, index + 2., "step_return", len(rows) + 1))
        rows[-1].update(truncated=True, reason="external_sampler_limit")
        rows.append({"schema": audit.SCHEMA, "event": "close", "event_sequence": len(rows) + 1,
                     "env_id": 0, "episode_index": 1, "epoch": "fixture-epoch", "proxy_only": True,
                     "closed": True})
        return rows

    @staticmethod
    def write(directory, rows):
        (directory / "trace.jsonl.gz").write_bytes(gzip.compress(
            b"\n".join(audit.canonical(row) for row in rows) + b"\n", mtime=0))

    def review(self, directory, rows):
        self.write(directory, rows)
        return audit.audit_episode(directory, "a" * 40, verify_sources=False, builder=self.builder)

    def test_valid_fixture_checks_all_tensors_and_three_selected_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = self.review(directory, self.fixture(directory))
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["step_attempts"], 2)
            self.assertEqual(result["step_returns"], 2)
            self.assertEqual(result["full_rebuild_event_sequences"], [1, 3, 5])
            self.assertFalse(result["qualification"])
            self.assertFalse(result["training_eligible"])
            self.assertFalse(result["native_credit"])
            self.assertEqual(result["verified_action_count"], 2)
            self.assertEqual(result["verified_uniform_action_count"], 0)
            self.assertEqual(result["verified_actor_record_count"], 3)
            self.assertEqual(result["verified_step_return_count"], 2)
            self.assertTrue(result["raw_event_counts_complete"])
            self.assertEqual(result["raw_closed_true_records"], 1)
            self.assertTrue(result["verified_close"])
            self.assertTrue(result["causal_validation_complete"])
            self.assertEqual(result["validated_prefix_records"], 6)

    def test_rehashed_mask_change_still_fails_actual_input_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = self.fixture(directory)
            snapshot = rows[0]["snapshot"]
            index = next(i for i, valid in enumerate(snapshot["joint_action_mask"]) if not valid)
            snapshot["joint_action_mask"][index] = True
            snapshot["digest"] = audit.sha(audit.canonical({k: v for k, v in snapshot.items() if k != "digest"}))
            rows[0]["tensor_proofs"] = audit.tensor_proofs(snapshot)
            result = self.review(directory, rows)
            self.assertFalse(result["passed"])
            self.assertTrue(any("snapshot replay differs" in error for error in result["errors"]))
            self.assertEqual((result["step_attempts"], result["step_returns"]), (2, 2))

    def test_saved_action_requires_exact_preceding_mask_and_candidate_version(self):
        for field in ("joint_action_mask", "candidate_version", "preceding_digest"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                rows = self.fixture(directory)
                if field == "joint_action_mask":
                    rows[1][field] = list(rows[1][field]); rows[1][field][888] = not rows[1][field][888]
                else:
                    rows[1][field] = "c" * 64
                result = self.review(directory, rows)
                self.assertFalse(result["passed"])
                self.assertTrue(any("preceding actor snapshot" in error for error in result["errors"]))

    def test_dtype_tensor_digest_and_cross_epoch_tampering_fail(self):
        for case in ("dtype", "tensor_sha", "epoch"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                rows = self.fixture(directory)
                if case == "epoch":
                    rows[2]["epoch"] = "other epoch"
                else:
                    proof = rows[2]["tensor_proofs"]["robots"]
                    proof["dtype" if case == "dtype" else "sha256"] = "float64" if case == "dtype" else "0" * 64
                result = self.review(directory, rows)
                self.assertFalse(result["passed"])

    def test_unsampled_middle_snapshot_still_has_all_tensor_bytes_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = self.fixture(directory, count=3)
            rows[4]["tensor_proofs"]["robots"]["sha256"] = "0" * 64
            result = self.review(directory, rows)
            self.assertFalse(result["passed"])
            self.assertTrue(any("tensor dtype/shape/bytes differ" in error for error in result["errors"]))

    def test_native_int16_grid_values_are_preserved_in_proxy_codec(self):
        from mr3_learning.proxy2d_codec import decode_arrays
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            row = self.actor(directory, 1, 1., "reset", 1)
            encoded = json.loads(gzip.decompress((directory / row["actor_input_ref"]["path"]).read_bytes()))
            params = decode_arrays(encoded)
            params["raw_grid"] = params["raw_grid"].astype(np.int16)
            for navigation in params["navigation_maps"].values():
                navigation["grid"] = navigation["grid"].astype(np.int16)
            raw = audit.canonical(encode_arrays(params))
            digest = audit.sha(raw)
            path = directory / f"inputs/{digest}.json.gz"
            path.write_bytes(gzip.compress(raw, mtime=0))
            row["actor_input_ref"] = {"path": str(path.relative_to(directory)), "sha256": digest}
            report, _ = audit.actor_record(directory, row, rebuild=True, builder=self.builder)
            self.assertTrue(report["full_snapshot_rebuilt"])

    def test_error_attempt_is_counted_and_retained_without_return_or_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = self.fixture(directory)
            rows = rows[:2] + [{"schema": audit.SCHEMA, "event": "step_error", "event_sequence": 3,
                               "env_id": 0, "episode_index": 1, "epoch": "fixture-epoch", "proxy_only": True,
                               "error": "genuine proxy exception"},
                              {"schema": audit.SCHEMA, "event": "close", "event_sequence": 4,
                               "env_id": 0, "episode_index": 1, "epoch": "fixture-epoch", "proxy_only": True,
                               "closed": True}]
            result = self.review(directory, rows)
            self.assertFalse(result["passed"])
            self.assertEqual((result["step_attempts"], result["step_returns"], result["step_errors"]), (1, 0, 1))
            self.assertTrue(any("genuine proxy exception" in error for error in result["errors"]))

    def test_unsettled_attempt_and_deadline_truncation_fail(self):
        for case in ("unsettled", "deadline"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                rows = self.fixture(directory)
                if case == "unsettled":
                    rows = rows[:2] + [rows[-1]]
                    rows[-1]["event_sequence"] = 3
                else:
                    rows[-2]["reason"] = "timeout"
                result = self.review(directory, rows)
                self.assertFalse(result["passed"])

    def test_truth_in_actor_inputs_rejected_even_with_new_valid_content_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            row = self.actor(directory, 1, 1., "reset", 1)
            path = directory / row["actor_input_ref"]["path"]
            data = json.loads(gzip.decompress(path.read_bytes()))
            data["robots"][0]["ground_truth_pose"] = {"x": 12., "y": 13.}
            raw = audit.canonical(data)
            digest = audit.sha(raw)
            new_path = directory / f"inputs/{digest}.json.gz"
            new_path.write_bytes(gzip.compress(raw, mtime=0))
            row["actor_input_ref"] = {"path": str(new_path.relative_to(directory)), "sha256": digest}
            with self.assertRaisesRegex(ValueError, "private truth"):
                audit.actor_record(directory, row, rebuild=True, builder=self.builder)

    def conformity_fixture(self, directory):
        """Manufactured evidence only; never reads V21 or integrates a world."""
        from mr3_learning import proxy2d_conformity
        native_index, files, records = {}, {}, []

        def reference(path, value, inventory_relative=None):
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = value if isinstance(value, bytes) else audit.canonical(encode_arrays(value))
            path.write_bytes(raw)
            spec = {"path": str(path), "sha256": audit.sha(raw), "bytes": len(raw)}
            if inventory_relative is not None:
                spec["inventory_relative_path"] = inventory_relative
                native_index[inventory_relative] = spec
                files[inventory_relative] = {"sha256": spec["sha256"], "bytes": spec["bytes"]}
            return spec

        snapshots = [self.builder(**self.params(n, float(n))) for n in (1, 2, 3)]
        for episode_index in (1, 2):
            episode = f"worker0/episode{episode_index:03d}_open_101"
            rows = [snapshots[0], snapshots[1], *([snapshots[2]] * 31)]
            raw = b"\n".join(audit.canonical({"snapshot": snapshot}) for snapshot in rows) + b"\n"
            transitions = reference(directory / episode / "transitions.jsonl", raw,
                                    episode + "/transitions.jsonl")
            for selection, line in (("reset", 1), ("first_step", 2), ("last_step", 33)):
                snapshot = rows[line - 1]
                manifest = reference(directory / episode / f"manifest_{line}.json",
                    {"snapshot_digest": snapshot["digest"], "sequence": snapshot["sequence"]},
                    episode + f"/manifest_{line}.json")
                expected = {"snapshot_canonical_sha256": audit.sha(audit.canonical(snapshot)),
                            "tensor_proofs": audit.tensor_proofs(snapshot)}
                records.append({"episode": episode, "selection": selection,
                    "native_freeze": proxy2d_conformity.NATIVE_FREEZE,
                    "native_snapshot_ref": {**transitions, "line_1based": line,
                                            "line_sha256": audit.sha(raw.splitlines()[line - 1])},
                    "manifest_ref": manifest, "expected": expected, "actual": copy.deepcopy(expected),
                    "candidate_mask_full_snapshot_equal": False,
                    "robot_recovery_scope": "manufactured CPU fixture"})
        inventory = reference(directory / "inventory.json", {"schema": "mr3-closed-byte-inventory-v1", "files": files})
        state = {"poses": {name: {"x": 0., "y": 0., "yaw": 0.} for name in ("tb1", "tb2", "tb3")},
                 "path_lengths": {name: 0. for name in ("tb1", "tb2", "tb3")}, "collision_events": 0}
        bounds = {"pose_error_m": 1e-10, "yaw_error_rad": 1e-10, "path_error_m": 1e-10,
                  "collision_count_difference": 0, "stop_displacement_m": 0}
        states = reference(directory / "convergence_states.json",
                           {key: state for key in ("first", "second", "stop_before", "stop_after")})
        actor = {"parameters": {"fixture": 1}, "snapshot": {"fixture": 2}}
        hashes = {"actor_parameters_sha256": audit.sha(audit.canonical(actor["parameters"])),
                  "snapshot_sha256": audit.sha(audit.canonical(actor["snapshot"]))}
        actors = [reference(directory / f"hidden_actor_{n}.json", actor) for n in (0, 1)]
        worlds = [reference(directory / f"world{n}/p1c_open.world", str(n).encode()) for n in (0, 1)]
        truth = [np.ones((2, 2), dtype=bool), np.array([[True, True], [True, False]])]
        correct = np.array([[True, False], [False, False]])
        reward_inputs = {"truth_free": truth, "correct": correct,
            "initial_correct": np.zeros((2, 2), dtype=bool), "epoch": "isolated", "sequence": 1,
            "start_sim_time": 0., "step_start": 0., "step_end": 1., "collision_events": 0,
            "goal_switches": 0, "rejected_actions": 0, "terminal_reason": None, "external_truncation": None,
            "actor_before": actor["parameters"], "actor_after": actor["parameters"],
            "snapshot_before": actor["snapshot"], "snapshot_after": actor["snapshot"]}
        reward_ref = reference(directory / "reward_truth_inputs.json", reward_inputs)
        cases = [
            {"id": "forward_turn_stop_halved_integration", "comparison": "upper_bounds", "expected": bounds,
             "actual": {key: 0. for key in bounds}, "input_refs": [states], "passed": False},
            {"id": "hidden_obstacle_same_received_actor", "comparison": "equal", "expected": hashes,
             "actual": copy.deepcopy(hashes), "input_refs": actors + worlds, "passed": False},
            {"id": "reward_truth_only_reward_branch", "comparison": "equal",
             "expected": {**hashes, "rewards": [10. / 4. - 1. / 300., 10. / 3. - 1. / 300.]},
             "actual": {**hashes, "rewards": [10. / 4. - 1. / 300., 10. / 3. - 1. / 300.]},
             "input_refs": [reward_ref], "passed": False}]
        synthetic = reference(directory / "synthetic.json", {"cases": cases, "native_runs": 0,
                                                             "gpu_calls": 0, "optimizer_steps": 0})
        inventory_bytes = Path(inventory["path"]).read_bytes()

        def git_fixture(argv, **unused):
            relative = argv[-1].split(":", 1)[1]
            if relative.endswith("report/assets/20261020_mr3_p2a_v21/native_inventory_v1.json"):
                return inventory_bytes
            return (audit.ROOT / relative).read_bytes()

        with patch.object(audit.subprocess, "check_output", side_effect=git_fixture):
            sources, _ = proxy2d_conformity.source_bindings("a" * 40)
        wait = {"child_identity": {"pid": 123, "start_ticks": 456}, "started_monotonic_ns": 1,
                "ended_monotonic_ns": 2, "returncode": 0, "actual_waited": True}
        formal = {"schema": "mr3-proxy2d-conformity-v1", "freeze": "a" * 40,
                  "qualification": False, "training_eligible": False, "native_credit": False,
                  "passed": False, "errors": [], "input_bytes_unchanged": True, "source_proof": sources,
                  "native_inventory": inventory, "native_input_index": native_index, "native_records": records,
                  "synthetic_result_ref": synthetic, "synthetic_cases": cases,
                  "pure_builder_actual_wait": wait, "synthetic_actual_wait": copy.deepcopy(wait)}
        return formal, git_fixture

    def test_conformity_independently_compares_originals_without_trusting_any_pass_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            formal, git_fixture = self.conformity_fixture(directory)
            path = directory / "formal.json"
            path.write_bytes(audit.canonical(formal))
            with patch.object(audit.subprocess, "check_output", side_effect=git_fixture):
                report = audit.audit_conformity(directory, path, "a" * 40)
            self.assertTrue(report["passed"], report["errors"])
            self.assertFalse(report["formal_producer_pass_flags_used"])
            self.assertEqual(report["additional_native_snapshot_replays"], 0)
            self.assertEqual(len(report["native_records"]), 6)

    def test_conformity_tampered_expected_actual_and_reference_all_fail(self):
        for case in ("native_pair", "relaxed_bounds", "reference", "reward_initial"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                formal, git_fixture = self.conformity_fixture(directory)
                if case == "native_pair":
                    formal["native_records"][0]["expected"]["snapshot_canonical_sha256"] = "0" * 64
                    formal["native_records"][0]["actual"]["snapshot_canonical_sha256"] = "0" * 64
                elif case == "relaxed_bounds":
                    formal["synthetic_cases"][0]["expected"]["pose_error_m"] = 1.
                elif case == "reference":
                    formal["synthetic_cases"][1]["input_refs"][0]["sha256"] = "0" * 64
                else:
                    ref = formal["synthetic_cases"][2]["input_refs"][0]
                    value = audit.parse(Path(ref["path"]).read_bytes())
                    value["step_end"] = 2.
                    raw = audit.canonical(value)
                    Path(ref["path"]).write_bytes(raw)
                    ref.update(sha256=audit.sha(raw), bytes=len(raw))
                # Keep the helper copy byte consistent so the independent
                # oracle, rather than a stale outer checksum, rejects changes.
                synthetic = formal["synthetic_result_ref"]
                raw = audit.canonical({"cases": formal["synthetic_cases"], "native_runs": 0,
                                       "gpu_calls": 0, "optimizer_steps": 0})
                Path(synthetic["path"]).write_bytes(raw)
                synthetic.update(sha256=audit.sha(raw), bytes=len(raw))
                formal["passed"] = True
                path = directory / "formal.json"
                path.write_bytes(audit.canonical(formal))
                with patch.object(audit.subprocess, "check_output", side_effect=git_fixture):
                    report = audit.audit_conformity(directory, path, "a" * 40)
                self.assertFalse(report["passed"])
                self.assertTrue(report["errors"])

    def test_failure_receipt_is_written_by_conformity_only_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output = directory / "audit.json"
            result = audit.main([str(directory), "--conformity-only", str(directory / "absent.json"),
                                 "--freeze", "a" * 40, "--output", str(output)])
            self.assertEqual(result, 1)
            self.assertFalse(json.loads(output.read_text())["passed"])

    def test_incomplete_failed_run_still_counts_all_later_saved_traces(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            started = time.monotonic_ns() - 1_000_000_000
            groups = []
            for workers in (1, 4):
                episode = directory / f"group{workers}/worker0/episode001_open_101"
                episode.mkdir(parents=True)
                rows = self.fixture(episode)
                if workers == 1:
                    rows[0]["tensor_proofs"]["robots"]["sha256"] = "0" * 64
                self.write(episode, rows)
                groups.append({"workers": workers, "started_ns": started + workers * 1000,
                    "ended_ns": started + workers * 1000 + 100,
                    "episodes": [{"directory": str(episode), "env_id": 0, "episode_index": 1,
                                  "scene": "open", "seed": 101, "action_seed": 41}]})
            summary = {"schema": "mr3-proxy2d-capacity-summary-v1", "freeze": "a" * 40,
                "qualification": False, "training_eligible": False, "native_credit": False,
                "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0,
                "source_bindings": {"fixture": "fixture"}, "conformity": {},
                "activity_started_ns": started, "activity_deadline_ns": started + 3600 * 10**9,
                "collection_deadline_ns": started + 2700 * 10**9, "closed": True, "errors": [],
                "forbidden_framework_imports": [], "groups": groups,
                "step_attempts": 4, "step_returns": 4, "step_errors": 0}
            (directory / "capacity_summary.json").write_bytes(audit.canonical(summary))
            stable = {Path(audit.__file__): Path(audit.__file__).read_bytes()}
            with patch.object(audit, "source_proof", return_value=({}, stable)), \
                    patch.object(audit, "verify_run_sources", return_value=({}, {}, ["manufactured fixture"])), \
                    patch.object(audit, "verify_conformity", return_value=({"passed": True}, {})):
                report = audit.audit_run(directory, "a" * 40)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["episodes"]), 2)
            self.assertEqual((report["step_attempts"], report["step_returns"]), (4, 4))
            self.assertEqual(len(report["group_capacity"]), 2)
            self.assertTrue(report["pure_builder_actual_wait"]["actual_waited"])

    def test_fourth_return_failure_does_not_claim_raw284_verified_or_unobserved_lateness(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            episode = directory / "group1/worker0/episode001_open_101"
            episode.mkdir(parents=True)
            rows = self.fixture(episode, count=284)
            started = time.monotonic_ns() - 1_000_000_000
            rng, attempt = random.Random(41), 0
            for row in rows:
                if row["event"] == "step_attempt":
                    attempt += 1
                    row["action"] = rng.choice([index for index, legal in enumerate(row["joint_action_mask"]) if legal])
                    row["started_wall_ns"] = started + attempt * 1000
                elif row["event"] == "step_return":
                    row["ended_wall_ns"] = started + attempt * 1000 + 100
            rows[8]["physical_dt"] = .98  # original duration predicate must still reject return4
            self.write(episode, rows)
            groups = [
                {"workers": 1, "started_ns": started, "ended_ns": started + 1_000_000,
                 "episodes": [{"directory": str(episode), "env_id": 0, "episode_index": 1,
                               "scene": "open", "seed": 101, "action_seed": 41}]},
                {"workers": 4, "started_ns": started + 2_000_000, "ended_ns": started + 3_000_000,
                 "episodes": []}]
            summary = {"schema": "mr3-proxy2d-capacity-summary-v1", "freeze": "a" * 40,
                "qualification": False, "training_eligible": False, "native_credit": False,
                "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0,
                "source_bindings": {"fixture": "fixture"}, "conformity": {},
                "activity_started_ns": started, "activity_deadline_ns": started + 3600 * 10**9,
                "collection_deadline_ns": started + 2700 * 10**9, "closed": True, "errors": [],
                "forbidden_framework_imports": [], "groups": groups,
                "step_attempts": 284, "step_returns": 284, "step_errors": 0}
            (directory / "capacity_summary.json").write_bytes(audit.canonical(summary))
            stable = {Path(audit.__file__): Path(audit.__file__).read_bytes()}
            with patch.object(audit, "source_proof", return_value=({}, stable)), \
                    patch.object(audit, "verify_run_sources", return_value=({}, {}, ["manufactured fixture"])), \
                    patch.object(audit, "verify_conformity", return_value=({"passed": True}, {})):
                report = audit.audit_run(directory, "a" * 40)
            self.assertFalse(report["passed"])
            checked = report["episodes"][0]
            self.assertEqual((checked["step_attempts"], checked["step_returns"]), (284, 284))
            self.assertEqual(checked["verified_action_count"], 4)
            self.assertEqual(checked["verified_uniform_action_count"], 4)
            self.assertEqual(checked["verified_actor_record_count"], 4)
            self.assertEqual(checked["verified_step_return_count"], 3)
            self.assertEqual(checked["validated_prefix_records"], 8)
            self.assertEqual(checked["full_rebuild_event_sequences"], [1, 3])
            self.assertEqual(checked["raw_close_records"], 1)
            self.assertEqual(checked["raw_closed_true_records"], 1)
            self.assertFalse(checked["verified_close"])
            self.assertFalse(checked["causal_validation_complete"])
            self.assertEqual(report["uniform_actions_independently_replayed"], 4)
            self.assertEqual(report["verified_step_return_count"], 3)
            for name, count in (("attempt_start", 4), ("return_end", 3)):
                coverage = checked["wall_timestamp_coverage"][name]
                self.assertFalse(coverage["coverage_complete"])
                self.assertEqual(coverage["expected_raw_count"], 284)
                self.assertEqual(coverage["verified_timestamp_count"], count)
                self.assertEqual(coverage["observed_out_of_bounds_count"], 0)
            self.assertTrue(any("transition physical/reward time differs" in error for error in report["errors"]))
            self.assertTrue(any("coverage incomplete" in error for error in report["errors"]))
            self.assertFalse(any("outside" in error or "not recorded before" in error for error in report["errors"]))
            self.assertFalse(report["qualification"])
            self.assertFalse(report["training_eligible"])

    def test_actual_timestamp_violation_is_reported_separately_from_coverage(self):
        result = audit._trace_wall_coverage({"attempt_start_wall_ns": [99, 201], "return_end_wall_ns": [301],
            "step_attempts": 4, "step_returns": 3, "raw_event_counts_complete": True}, 100, 200, 300)
        self.assertFalse(result["attempt_start"]["coverage_complete"])
        self.assertEqual(result["attempt_start"]["observed_out_of_bounds_count"], 2)
        self.assertFalse(result["return_end"]["coverage_complete"])
        self.assertEqual(result["return_end"]["observed_out_of_bounds_count"], 1)

    def test_legal_action_failing_uniform_comparison_has_no_uniform_credit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = self.fixture(directory)
            legal = [index for index, valid in enumerate(rows[1]["joint_action_mask"]) if valid]
            expected = random.Random(41).choice(legal)
            rows[1]["action"] = next(index for index in legal if index != expected)
            self.write(directory, rows)
            report = audit.audit_episode(directory, "a" * 40, verify_sources=False,
                                         builder=self.builder, rng=random.Random(41))
            self.assertFalse(report["passed"])
            self.assertEqual(report["verified_action_count"], 1)
            self.assertEqual(report["verified_uniform_action_count"], 0)
            self.assertEqual(report["verified_actor_record_count"], 1)
            self.assertEqual(report["verified_step_return_count"], 0)
            self.assertEqual(report["validated_prefix_records"], 1)


if __name__ == "__main__":
    unittest.main()
