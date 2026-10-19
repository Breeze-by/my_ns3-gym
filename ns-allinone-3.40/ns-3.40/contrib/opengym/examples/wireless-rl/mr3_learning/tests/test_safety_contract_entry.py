"""Supervisor profile validation and exact reset forwarding; no worker launches."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning.supervisor import Supervisor


class SafetyContractEntryTests(unittest.TestCase):
    def test_invalid_profiles_are_rejected_before_any_directory_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/"not-created"
            for invalid in (None, True, 1, {}, [], "", "reach", "legacy "):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    Supervisor(output_root=root, safety_contract=invalid)
                self.assertFalse(root.exists())

    def test_default_profile_is_legacy_without_starting_an_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            supervisor = Supervisor(output_root=temporary, run_id="default-profile")
            self.assertEqual(supervisor.safety_contract, "legacy")
            self.assertIsNone(supervisor.episode)

    def test_metadata_and_reset_rpc_bind_the_selected_profile_without_legacy_extra_fields(self):
        for contract in ("legacy", "mr3-reach-v1"):
            with self.subTest(contract=contract), tempfile.TemporaryDirectory() as temporary:
                supervisor = Supervisor(output_root=temporary, run_id="profile-fixture",
                                        safety_contract=contract)
                identity = {"pid": 43121, "parent": 1, "group": 43121, "session": 43121,
                            "start_ticks": 123, "state": "S"}
                process = Mock(pid=identity["pid"])
                process.stdout.fileno.return_value = 9
                process.stdin.fileno.return_value = 10
                requests = []

                def rpc(operation, **payload):
                    requests.append((operation, payload))
                    return {"snapshot": {"epoch": supervisor.episode.epoch}}

                with patch("mr3_learning.supervisor.subprocess.Popen", return_value=process) as popen, \
                        patch("mr3_learning.supervisor.process_identity", return_value=identity), \
                        patch("mr3_learning.supervisor.JsonLinePeer", return_value=SimpleNamespace()), \
                        patch("mr3_learning.supervisor.threading.Thread"), \
                        patch.object(supervisor, "close"), patch.object(supervisor, "_rpc", side_effect=rpc):
                    try:
                        result = supervisor.reset("open", 101)
                        metadata = json.loads((supervisor.episode.directory/
                                               "supervisor_metadata.json").read_text())
                        self.assertEqual(metadata["safety_contract"], contract)
                        self.assertEqual(metadata["epoch"], result["snapshot"]["epoch"])
                        self.assertEqual(requests[0][0], "reset")
                        self.assertEqual(requests[0][1]["quantum_steps"], 20)
                        if contract == "legacy":
                            self.assertNotIn("safety_contract", requests[0][1])
                        else:
                            self.assertEqual(requests[0][1]["safety_contract"], contract)
                        self.assertEqual(popen.call_count, 1)  # Stub only, no process executed.
                    finally:
                        if supervisor.episode is not None:
                            supervisor.episode.output.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
