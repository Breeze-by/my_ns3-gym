"""Offline binding regressions; no clean Git freeze or native process needed."""

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

        def components(source_freeze, source_root):
            self.assertEqual((source_freeze, source_root), (freeze, root))
            return None, None, None, {task: {"sha256": document_digest}}

        phase.load_components = components

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


if __name__ == "__main__":
    unittest.main()
