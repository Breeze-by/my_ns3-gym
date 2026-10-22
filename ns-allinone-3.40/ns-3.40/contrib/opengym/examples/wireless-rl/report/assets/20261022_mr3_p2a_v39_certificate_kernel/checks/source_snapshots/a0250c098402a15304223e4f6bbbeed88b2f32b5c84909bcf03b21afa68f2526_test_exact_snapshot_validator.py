"""Artificial snapshots through the real immutable validator; no native inputs."""

import base64
import copy
import gzip
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
import zlib

import numpy as np

from mr3_learning import audit_ppo, audit_protocol
from mr3_learning.reach_audit_projection import project_module
from mr3_learning.reach_gates import PPO_READER_SHA256, extend_exact_snapshot_validator
from mr3_learning.supervisor import EXACT_SEED_VERSIONS, candidate_version_for_rules


ROOT = Path(audit_ppo.__file__).resolve().parents[7]
VERSION = "mr3-navigation-geometric-staging-v6-exact-seed-v1"


class ExactSnapshotValidatorTests(unittest.TestCase):
    def setUp(self):
        names = ("ros_smoke_test", "audit_mr3_adapter_probe")
        previous = {name: sys.modules.get(name) for name in names}

        def restore():
            for name, value in previous.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value

        self.addCleanup(restore)
        smoke = ROOT / audit_ppo.ROS / "scripts/ros_smoke_test.py"
        audit_ppo.load_pinned("ros_smoke_test", smoke, audit_ppo.sha(smoke))
        relative = audit_ppo.ROS + "scripts/audit_mr3_adapter_probe.py"
        self.candidate = audit_ppo.load_pinned("audit_mr3_adapter_probe", ROOT / relative,
                                             audit_ppo.CURRENT_AUDITOR_PINS[relative])
        relative = audit_ppo.ROS + "scripts/audit_mr3_env.py"
        raw = subprocess.check_output(["git", "show", audit_ppo.TASK_BASE_FREEZE + ":" + relative], cwd=ROOT)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), audit_protocol.ORIGINAL_AUDITOR_SHA)
        self.auditor = ModuleType("artificial_exact_snapshot_original_auditor")
        self.auditor.__file__ = str(ROOT / relative)
        exec(compile(raw, audit_ppo.TASK_BASE_FREEZE + ":" + relative, "exec"), self.auditor.__dict__)
        self.original = self.auditor.validate_snapshot
        self.reader, proof = project_module("audit_ppo.py", PPO_READER_SHA256, ())
        self.assertTrue(proof["whole_source_inverse_equal"])
        self.assertEqual(proof["literal_changes"], [])
        self.calls = []

        def original(snapshot, epoch):
            self.calls.append(copy.deepcopy(snapshot))
            return self.original(snapshot, epoch)

        self.auditor.validate_snapshot = original
        self.record_original=original
        self.select_seed_rule("exact-point-bridge-v1")

    def select_seed_rule(self,seed_rule,start_graph_rule="original-seed-cell"):
        self.auditor.validate_snapshot=self.record_original
        extend_exact_snapshot_validator(self.reader.extend_snapshot_validator, self.auditor,
                                        self.candidate,seed_rule=seed_rule,start_graph_rule=start_graph_rule)

    def seal(self, snapshot):
        keys = ("epoch", "map_version", "sequence", "candidate_rule", "candidates", "path_maps")
        snapshot["candidate_version"] = self.candidate.canonical_digest({key: snapshot[key] for key in keys})
        snapshot["digest"] = self.candidate.canonical_digest(
            {key: value for key, value in snapshot.items() if key != "digest"})
        return snapshot

    def snapshot(self,seed_rule="exact-point-bridge-v1",start_graph_rule="original-seed-cell"):
        def raster(side, name=None):
            value = {"encoding": "base64-zlib-u8-chw", "shape": [3, side, side],
                     "channels": ["occupied", "free", "unknown"],
                     "data": base64.b64encode(zlib.compress(bytes(3 * side * side))).decode()}
            if name is not None:
                value["name"] = name
            return value

        robots = [{"name": name, "epoch": "artificial", "valid": False, "fresh": False, "missing": True,
                   "navigation": {"phase": "unknown", "owned": False, "cancel_requested": False,
                                  "receipt_missing": True, "source_metadata_missing": True},
                   "history": [], "activity": None}
                  for name in ("tb1", "tb2", "tb3")]
        candidates = [{"index": index, "valid": False, "x": None, "y": None, "clearance_m": None,
                       "frontier_count": 0, "path_distances_m": [None] * 3, "reachable": [False] * 3}
                      for index in range(8)]
        return self.seal({"schema": "mr3-observation-v3", "epoch": "artificial", "sequence": 1,
            "map_version": 1, "source_stamp": 0., "robot_order": ["tb1", "tb2", "tb3"],
            "robots": robots, "path_maps": {name: {"missing": True, "seed_rule": seed_rule,
                "seed_point_bridge_certificate": None} for name in ("tb1", "tb2", "tb3")},
            "candidates": candidates, "joint_action_mask": [index == 888 for index in range(1000)],
            "map": {"missing": True}, "task_elapsed_sec": 0., "task_remaining_sec": 300., "policy_period_sec": 1.,
            "maps": {"global": raster(128), "locals": [raster(64, name) for name in ("tb1", "tb2", "tb3")]},
            "candidate_rule": copy.deepcopy(self.candidate.CANDIDATE_RULES[
                candidate_version_for_rules(seed_rule,start_graph_rule)])})

    def complete_point_graph_snapshot(self):
        from mr3_learning.audit_proxy2d import PureBuilder, sha
        from mr3_learning.proxy2d_conformity import point_graph_parameters

        params = point_graph_parameters("free_centre")
        grid = np.zeros((80, 80), dtype=np.int16)
        grid[[0, -1], :] = -1
        grid[:, 0] = -1
        grid[:, 70:] = -1
        grid[20, 20] = 100
        params.update(raw_grid=grid, resolution=.05, origin=[-1., -1.],
                      start_graph_rule="point-attachment-3x3-v1")
        # The tb3 pose is safe, while its original cell centre is not. This is
        # the fixed artificial counterexample from the observation tests, with
        # distant unknown boundaries supplying real reachable frontier goals.
        for robot, (x, y) in zip(params["robots"], ((.8, .8), (1.4, .8), (.349, .149))):
            robot.update(x=x, y=y)
        for maps in (params["robot_maps"], params["navigation_maps"]):
            for entry in maps.values():
                entry.update(grid=grid.copy(), resolution=.05, origin=[-1., -1.],
                             payload_sha256=sha(grid.tobytes(order="C")))
        builder = PureBuilder()
        self.addCleanup(builder.close)
        snapshot = builder(**params)
        entry = snapshot["path_maps"]["tb3"]
        self.assertFalse(snapshot["diagnostics"]["robot_seed_traversable"][2])
        self.assertEqual(entry["seed_rejection_reason"], "seed_cell_body_clearance")
        self.assertTrue(entry["point_graph_attachment"]["accepted"])
        self.assertFalse(entry["point_graph_attachment"]["canonical_cell_original_traversable"])
        self.assertTrue(snapshot["diagnostics"]["robot_start_graph_attached"][2])
        self.assertTrue(all(not metadata["missing"] for metadata in snapshot["path_maps"].values()))
        self.assertTrue(any(candidate["valid"] and candidate["reachable"][2]
                            for candidate in snapshot["candidates"]))
        self.assertTrue(any(snapshot["per_robot_action_mask"][2][:8]))
        return builder, params, snapshot

    def test_complete_point_graph_reachable_snapshot_passes_real_encoder_and_original_gate(self):
        _, params, snapshot = self.complete_point_graph_snapshot()
        self.select_seed_rule(params["seed_rule"], params["start_graph_rule"])
        before = copy.deepcopy(snapshot)
        with patch.object(self.reader, "encode_snapshot", wraps=self.reader.encode_snapshot) as encode:
            self.auditor.validate_snapshot(snapshot, params["epoch"])
        encode.assert_called_once_with(snapshot)
        self.assertEqual(snapshot, before)
        self.assertEqual(len(self.calls), 1)
        legacy = self.calls[0]
        self.assertEqual(legacy["schema"], "mr3-observation-v2")
        self.assertNotIn("candidate_rule", legacy)
        self.assertEqual(legacy["path_maps"], snapshot["path_maps"])
        self.assertEqual(legacy["candidates"], snapshot["candidates"])
        self.assertEqual(legacy["joint_action_mask"], snapshot["joint_action_mask"])

    def test_complete_point_graph_tamper_cannot_bypass_digest_or_encoder_predicates(self):
        _, params, snapshot = self.complete_point_graph_snapshot()
        self.select_seed_rule(params["seed_rule"], params["start_graph_rule"])
        index = next(candidate["index"] for candidate in snapshot["candidates"]
                     if candidate["valid"] and candidate["reachable"][2])
        for fault in ("attachment", "candidate"):
            changed = copy.deepcopy(snapshot)
            if fault == "attachment":
                changed["path_maps"]["tb3"]["point_graph_attachment"]["anchors"] = []
            else:
                changed["candidates"][index]["x"] += .125
            # A newly sealed whole snapshot cannot hide a stale candidate
            # digest, which also binds every original attachment field.
            changed["digest"] = self.candidate.canonical_digest(
                {key: value for key, value in changed.items() if key != "digest"})
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, "versioned candidate digest"):
                self.auditor.validate_snapshot(changed, params["epoch"])
        for fault in ("reachability", "path", "geometry"):
            changed = copy.deepcopy(snapshot)
            candidate = changed["candidates"][index]
            if fault == "reachability":
                candidate["reachable"][2] = False
            elif fault == "path":
                candidate["path_distances_m"][2] = None
            else:
                candidate["x"] = None
            self.seal(changed)
            with self.subTest(fault=fault), self.assertRaisesRegex(
                    ValueError, "reachability and path metadata|valid candidate is missing its geometry"):
                self.auditor.validate_snapshot(changed, params["epoch"])
        self.assertEqual(self.calls, [])

    def test_resealed_point_geometry_still_requires_independent_received_input_replay(self):
        from mr3_learning import audit_proxy2d as audit
        from mr3_learning.proxy2d_codec import encode_arrays

        builder, params, snapshot = self.complete_point_graph_snapshot()
        self.select_seed_rule(params["seed_rule"], params["start_graph_rule"])
        index = next(candidate["index"] for candidate in snapshot["candidates"]
                     if candidate["valid"] and candidate["reachable"][2])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = audit.canonical(encode_arrays(params))
            digest = audit.sha(raw)
            relative = f"inputs/{digest}.json.gz"
            path = directory / relative
            path.parent.mkdir()
            path.write_bytes(gzip.compress(raw, mtime=0))
            for fault in ("attachment", "candidate", "path"):
                changed = copy.deepcopy(snapshot)
                if fault == "attachment":
                    changed["path_maps"]["tb3"]["point_graph_attachment"]["anchors"] = []
                elif fault == "candidate":
                    changed["candidates"][index]["x"] += .125
                else:
                    changed["candidates"][index]["path_distances_m"][2] += .125
                self.seal(changed)
                # The private validator proves hashes/encoding/structure, not
                # received-map geometry. Its necessary independent replay gate
                # must reject even a fully resealed, well-typed forgery.
                self.auditor.validate_snapshot(changed, params["epoch"])
                row = {"epoch": params["epoch"], "snapshot": changed,
                       "actor_input_ref": {"path": relative, "sha256": digest},
                       "tensor_proofs": audit.tensor_proofs(changed)}
                expected = "certificate differs" if fault == "attachment" else "full snapshot replay differs"
                with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, expected):
                    audit.actor_record(directory, row, rebuild=True, builder=builder)

    def test_real_point_graph_rule_cannot_borrow_the_original_v2_or_v1_rule(self):
        seed,start="exact-point-bridge-v2","point-attachment-3x3-v1"
        self.select_seed_rule(seed,start)
        snapshot=self.snapshot(seed,start)
        self.assertEqual(snapshot["candidate_rule"]["version"],"mr3-navigation-geometric-staging-v8-point-graph-v1")
        self.assertEqual(snapshot["candidate_rule"]["start_graph_profile"],"mr3-point-graph-attachment-3x3-v1")
        self.auditor.validate_snapshot(snapshot,"artificial")
        for changed in (self.snapshot(seed),self.snapshot("exact-point-bridge-v1")):
            with self.assertRaisesRegex(ValueError,"declared exact seed candidate rule"):
                self.auditor.validate_snapshot(changed,"artificial")
        for key,value in (("start_graph_rule","original-seed-cell"),
                          ("start_graph_profile","unreviewed"),("start_graph_cost","zero-cost-snap")):
            changed=copy.deepcopy(snapshot);changed["candidate_rule"][key]=value;self.seal(changed)
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.auditor.validate_snapshot(changed,"artificial")
        self.select_seed_rule(seed)
        with self.assertRaises(ValueError):self.auditor.validate_snapshot(snapshot,"artificial")

    def test_both_real_exact_rules_validate_only_with_their_declared_mode(self):
        for seed_rule,version in EXACT_SEED_VERSIONS.items():
            with self.subTest(seed_rule=seed_rule):
                self.select_seed_rule(seed_rule)
                snapshot=self.snapshot(seed_rule)
                self.assertEqual(snapshot["candidate_rule"],
                    {**self.candidate.CANDIDATE_RULE_V5,"version":version,"seed_rule":seed_rule})
                self.assertEqual(self.candidate.candidate_digest(snapshot),snapshot["candidate_version"])
                before=copy.deepcopy(snapshot)
                self.auditor.validate_snapshot(snapshot,"artificial")
                self.assertEqual(snapshot,before)
                other=next(name for name in EXACT_SEED_VERSIONS if name!=seed_rule)
                with self.assertRaisesRegex(ValueError,"declared exact seed candidate rule"):
                    self.auditor.validate_snapshot(self.snapshot(other),"artificial")
                changed=copy.deepcopy(snapshot);changed["candidate_rule"]["path_body_clearance_m"]=.28
                self.seal(changed)
                with self.assertRaisesRegex(ValueError,"declared exact seed candidate rule"):
                    self.auditor.validate_snapshot(changed,"artificial")
        self.assertEqual(len(self.calls),2)

    def test_real_v6_digest_and_encoder_then_original_snapshot_validator(self):
        snapshot = self.snapshot(); before = copy.deepcopy(snapshot)
        self.assertEqual(self.candidate.candidate_digest(snapshot), snapshot["candidate_version"])
        self.auditor.validate_snapshot(snapshot, "artificial")
        self.assertEqual(snapshot, before)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["schema"], "mr3-observation-v2")
        self.assertNotIn("candidate_rule", self.calls[0])
        self.assertEqual(self.calls[0]["path_maps"], snapshot["path_maps"])

    def test_rule_changes_remain_rejected_even_with_all_digests_resealed(self):
        for key, value in (("version", "mr3-navigation-geometric-staging-v5"),
                           ("seed_rule", "legacy"), ("path_body_clearance_m", .28),
                           ("unreviewed_rule", True)):
            snapshot = self.snapshot(); snapshot["candidate_rule"][key] = value; self.seal(snapshot)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.auditor.validate_snapshot(snapshot, "artificial")
        self.assertEqual(self.calls, [])

    def test_real_candidate_or_whole_digest_corruption_cannot_enter_original_gate(self):
        for field in ("candidate_version", "digest"):
            snapshot = self.snapshot(); snapshot[field] = "0" * 64
            if field == "candidate_version":
                snapshot["digest"] = self.candidate.canonical_digest(
                    {key: value for key, value in snapshot.items() if key != "digest"})
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.auditor.validate_snapshot(snapshot, "artificial")
        self.assertEqual(self.calls, [])

    def test_real_schema_encoder_and_original_epoch_gates_remain_necessary(self):
        snapshot = self.snapshot(); snapshot["schema"] = "mr3-observation-v2"; self.seal(snapshot)
        with self.assertRaises(ValueError):self.auditor.validate_snapshot(snapshot, "artificial")
        snapshot = self.snapshot(); snapshot["maps"]["global"]["encoding"] = "unknown"; self.seal(snapshot)
        with self.assertRaises(ValueError):self.auditor.validate_snapshot(snapshot, "artificial")
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, "cross-epoch"):
            self.auditor.validate_snapshot(self.snapshot(), "other-epoch")
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
