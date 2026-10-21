"""Artificial snapshots through the real immutable validator; no native inputs."""

import base64
import copy
import hashlib
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import unittest
import zlib

from mr3_learning import audit_ppo, audit_protocol
from mr3_learning.reach_audit_projection import project_module
from mr3_learning.reach_gates import PPO_READER_SHA256, extend_exact_snapshot_validator


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
        extend_exact_snapshot_validator(self.reader.extend_snapshot_validator, self.auditor, self.candidate)

    def seal(self, snapshot):
        keys = ("epoch", "map_version", "sequence", "candidate_rule", "candidates", "path_maps")
        snapshot["candidate_version"] = self.candidate.canonical_digest({key: snapshot[key] for key in keys})
        snapshot["digest"] = self.candidate.canonical_digest(
            {key: value for key, value in snapshot.items() if key != "digest"})
        return snapshot

    def snapshot(self):
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
            "robots": robots, "path_maps": {name: {"missing": True, "seed_rule": "exact-point-bridge-v1",
                "seed_point_bridge_certificate": None} for name in ("tb1", "tb2", "tb3")},
            "candidates": candidates, "joint_action_mask": [index == 888 for index in range(1000)],
            "map": {"missing": True}, "task_elapsed_sec": 0., "task_remaining_sec": 300., "policy_period_sec": 1.,
            "maps": {"global": raster(128), "locals": [raster(64, name) for name in ("tb1", "tb2", "tb3")]},
            "candidate_rule": copy.deepcopy(self.candidate.CANDIDATE_RULES[VERSION])})

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
