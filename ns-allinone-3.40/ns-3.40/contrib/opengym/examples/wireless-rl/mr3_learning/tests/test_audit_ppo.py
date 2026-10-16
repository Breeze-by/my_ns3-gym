"""Offline binding regressions; no clean Git freeze or native process needed."""

import ast
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import audit_ppo


class NativeBindingTests(unittest.TestCase):
    def loader(self, document_digest, *, machine_changed=False):
        """Mock document bytes/hashes, retaining the real loader's gate logic."""
        root = Path("/offline-fixture")
        freeze = "a" * 40
        task = audit_ppo.WIRELESS + "MR3_TASK_CONTRACT.md"
        config = ("ros2_ws/ros2-multi-robot-automap/src/multi_robot/"
                  "config/mr3_p1a/open.json")
        document_payload = b"mock-known-status-revision"
        machine_payload = b"unchanged-frozen-machine-contract"
        learner_payload = b"unchanged-collecting-learner"
        machine_digest = hashlib.sha256(machine_payload).hexdigest()
        learner_digest = hashlib.sha256(learner_payload).hexdigest()
        original_sha256 = hashlib.sha256
        phase = SimpleNamespace(PINNED_DOCUMENTS={"original-pin": "preserved"})

        def components(source_phase, source_root, source_freeze):
            self.assertIs(source_phase, phase)
            self.assertEqual((source_freeze, source_root), (freeze, root))
            return None, None, None, {task: {"sha256": document_digest}}

        def git_output(command, **kwargs):
            self.assertEqual(kwargs["cwd"], root)
            if command[1] == "ls-tree":
                return config + "\n"
            revision, relative = command[2].split(":", 1)
            if relative == task:
                return document_payload
            if "/mr3_learning/" in relative:
                return learner_payload
            if machine_changed and revision == freeze and relative == config:
                return machine_payload + b"changed"
            return machine_payload

        def digest(payload):
            if payload == document_payload:
                return SimpleNamespace(hexdigest=lambda: document_digest)
            return original_sha256(payload)

        def file_digest(path):
            if path.name == "MR3_TASK_CONTRACT.md":
                return audit_ppo.TASK_DOCUMENT_SHA256
            if path.name == "MR3_ENV_CONTRACT.md":
                return audit_ppo.ENV_DOCUMENT_SHA256
            if "/mr3_learning/" in str(path):
                return learner_digest
            return machine_digest

        with patch.object(audit_ppo, "load_pinned", side_effect=[phase, None]), \
                patch.object(audit_ppo, "load_compatible_components", components), \
                patch.object(audit_ppo.subprocess, "check_output", git_output), \
                patch.object(audit_ppo.hashlib, "sha256", digest), \
                patch.object(audit_ppo, "sha", file_digest):
            result = audit_ppo.load_native_gates(root, freeze)
        self.assertEqual(phase.PINNED_DOCUMENTS["original-pin"], "preserved")
        self.assertEqual(phase.PINNED_DOCUMENTS[task], document_digest)
        return result[-1], task, config

    def test_both_exact_status_pins_keep_machine_geometry_bound(self):
        for digest in (audit_ppo.TASK_DOCUMENT_SHA256,
                       audit_ppo.PRIOR_TASK_DOCUMENT_SHA256):
            with self.subTest(document_digest=digest):
                proof, task, config = self.loader(digest)
                self.assertEqual(proof[task]["native_document_sha256"], digest)
                self.assertEqual(proof[task]["current_status_sha256"],
                                 audit_ppo.TASK_DOCUMENT_SHA256)
                self.assertTrue(proof[config]["normative_source"].startswith(
                    audit_ppo.TASK_BASE_FREEZE + ":"))

    def test_unknown_status_document_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "explicitly pinned"):
            self.loader("0" * 64)

    def test_known_status_pin_cannot_authorize_changed_machine_contract(self):
        with self.assertRaisesRegex(ValueError, "machine task/geometry changed"):
            self.loader(audit_ppo.TASK_DOCUMENT_SHA256, machine_changed=True)


class VersionedNativeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = next(parent for parent in Path(audit_ppo.__file__).parents
                        if (parent / ".git").exists())
        cls.directory = cls.root / audit_ppo.WIRELESS / "report/assets/20261015_mr3_p1c"
        phase_path = cls.directory / "audit_mr3_env_contact_phase_v3.py"
        phase = audit_ppo.load_pinned(
            "mr3_test_original_phase_v3", phase_path, audit_ppo.PHASE_SHA256)
        cls.original_runtime_pins = dict(phase.PINNED_RUNTIME)
        phase.PINNED_DOCUMENTS = {}  # Status-document gates have separate tests above.
        git_output = audit_ppo.subprocess.check_output
        freeze = "a" * 40

        def pretend_committed_worktree(command, **kwargs):
            if command[:2] == ["git", "show"] and command[2].startswith(freeze + ":"):
                return (cls.root / command[2].split(":", 1)[1]).read_bytes()
            return git_output(command, **kwargs)

        with patch.object(audit_ppo.subprocess, "check_output", pretend_committed_worktree):
            cls.base, cls.auditor, cls.command, cls.proof = audit_ppo.load_compatible_components(
                phase, cls.root, freeze)
        cls.candidates = audit_ppo.sys.modules["mr3_p2a_current_candidate_rules"]

    def legacy_snapshot(self):
        value = {"schema": "mr3-observation-v2", "epoch": "episode", "sequence": 1,
                 "map_version": 1, "candidates": [{"index": i} for i in range(8)],
                 "path_maps": {name: {} for name in ("tb1", "tb2", "tb3")},
                 "robots": [{"name": name} for name in ("tb1", "tb2", "tb3")],
                 "joint_action_mask": [index == 888 for index in range(1000)]}
        return self.seal(value)

    def seal(self, snapshot):
        keys = ["epoch", "map_version", "sequence", "candidates", "path_maps"]
        if "candidate_rule" in snapshot:
            keys.append("candidate_rule")
        snapshot["candidate_version"] = self.auditor.canonical_digest({
            key: snapshot[key] for key in keys})
        snapshot["digest"] = self.auditor.canonical_digest({
            key: value for key, value in snapshot.items() if key != "digest"})
        return snapshot

    def versioned_snapshot(self):
        value = self.legacy_snapshot()
        value["candidate_rule"] = copy.deepcopy(self.candidates.CANDIDATE_RULE_V3)
        return self.seal(value)

    def test_explicit_runtime_extensions_keep_original_helpers_exact(self):
        self.assertEqual(self.base.PINNED_RUNTIME[audit_ppo.OBSERVATION_SOURCE],
                         audit_ppo.OBSERVATION_V3_SHA256)
        self.assertEqual(self.base.PINNED_RUNTIME[audit_ppo.REWARD_SOURCE],
                         audit_ppo.W7_REWARD_SHA256)
        self.assertEqual(self.proof[audit_ppo.REWARD_SOURCE]["normative_source"],
                         audit_ppo.TASK_BASE_FREEZE + ":" + audit_ppo.REWARD_SOURCE)
        for path, digest in self.original_runtime_pins.items():
            if path != audit_ppo.OBSERVATION_SOURCE and path not in audit_ppo.EVALUATOR_PHASE_PINS:
                self.assertEqual(self.base.PINNED_RUNTIME[path], digest)
        for function in (self.auditor.audit_physics, self.auditor.audit_contacts,
                         self.auditor.audit_protocol.original):
            self.assertTrue(function.__code__.co_filename.startswith(audit_ppo.TASK_BASE_FREEZE))
        self.assertEqual(audit_ppo.sha(self.directory / "audit_mr3_env_contact_phase_v3.py"),
                         audit_ppo.PHASE_SHA256)
        self.assertEqual(audit_ppo.sha(self.directory / "reward_gate_audit_v3.py"),
                         audit_ppo.SCALAR_SHA256)
        for path, digest in audit_ppo.EXECUTION_CONFIG_PINS.items():
            self.assertEqual(self.proof[path]["sha256"], digest)
            self.assertEqual(self.proof[path]["worktree_sha256"], digest)
        for path, digest in audit_ppo.EVALUATOR_PHASE_PINS.items():
            self.assertEqual(self.base.PINNED_RUNTIME[path], digest)
            self.assertEqual(self.proof[path]["sha256"], digest)

    def test_legacy_and_exact_v3_validate_without_changing_saved_snapshot(self):
        for snapshot in (self.legacy_snapshot(), self.versioned_snapshot()):
            with self.subTest(version=snapshot.get("candidate_rule")):
                before = copy.deepcopy(snapshot)
                self.auditor.validate_snapshot(snapshot, "episode")
                self.assertEqual(snapshot, before)

    def test_mapper_config_pin_is_the_actual_multirobot_launch_selection(self):
        def strings(path):
            return {node.value for node in ast.walk(ast.parse(path.read_text()))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)}

        ros = self.root / audit_ppo.ROS
        main = ros / "src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py"
        self.assertIn("online_async_multirobot_launch.py", strings(main))
        launch = ros / "src/slam_toolbox/launch/online_async_multirobot_launch.py"
        filename = "mapper_params_online_multi_async.yaml"
        self.assertIn(filename, strings(launch))
        self.assertIn(audit_ppo.ROS + "src/slam_toolbox/config/" + filename,
                      audit_ppo.EXECUTION_CONFIG_PINS)
        self.assertNotIn(audit_ppo.ROS + "src/slam_toolbox/config/mapper_params_online_async.yaml",
                         audit_ppo.EXECUTION_CONFIG_PINS)

    def test_unknown_changed_extra_or_noncanonical_candidate_rules_are_rejected(self):
        changes = ({"version": "unknown"}, {"goal_xy_tolerance_m": .25},
                   {"frontier_staging_max_m": True}, {"frontier_staging_max_m": 1},
                   {"unreviewed_rule": 1.})
        for change in changes:
            with self.subTest(change=change):
                snapshot = self.versioned_snapshot()
                snapshot["candidate_rule"].update(change)
                self.seal(snapshot)  # Even correctly self-signed unknown rules must fail.
                with self.assertRaisesRegex(ValueError, "candidate rule"):
                    self.auditor.validate_snapshot(snapshot, "episode")

    def test_version_extension_cannot_bypass_original_snapshot_gates(self):
        snapshot = self.versioned_snapshot()
        snapshot["robots"] = [{"name": "tb1"}]
        self.seal(snapshot)
        with self.assertRaisesRegex(ValueError, "exactly tb1/tb2/tb3"):
            self.auditor.validate_snapshot(snapshot, "episode")
        snapshot = self.versioned_snapshot()
        snapshot["joint_action_mask"] = [True]
        self.seal(snapshot)
        with self.assertRaisesRegex(ValueError, "joint-action mask"):
            self.auditor.validate_snapshot(snapshot, "episode")
        snapshot = self.versioned_snapshot()
        snapshot["digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "snapshot digest"):
            self.auditor.validate_snapshot(snapshot, "episode")

    def test_source_freeze_and_worktree_must_both_match_explicit_config_pin(self):
        path = next(iter(audit_ppo.EXECUTION_CONFIG_PINS))
        expected = audit_ppo.EXECUTION_CONFIG_PINS[path]
        payload = (self.root / path).read_bytes()
        variants = ((payload + b"changed", expected), (payload, "0" * 64))
        for git_bytes, worktree_digest in variants:
            with self.subTest(git_changed=git_bytes != payload), \
                    patch.object(audit_ppo.subprocess, "check_output", return_value=git_bytes), \
                    patch.object(audit_ppo, "sha", return_value=worktree_digest), \
                    self.assertRaisesRegex(ValueError, "source freeze/worktree"):
                audit_ppo.verify_frozen_pins(self.root, "a" * 40, {path: expected}, "config")


if __name__ == "__main__":
    unittest.main()
