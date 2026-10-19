"""EP/RUN selection and failure retention; episode mathematics are stubbed."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import audit_reach_runtime as runtime
from mr3_learning import audit_reach_information as information


FREEZE = "a"*40


def episode(path, epoch):
    path.mkdir(parents=True, exist_ok=True)
    metadata = {"epoch": epoch, "freeze": FREEZE, "safety_contract": "mr3-reach-v1",
                "execution_phase_protocol": "mr3-controlled-execution-phase-v2",
                "reset_handshake": "paused-controlled-state-peer-guard-storage-v2"}
    (path/"metadata.json").write_text(json.dumps(metadata))
    return path


def passed(path, freeze):
    metadata = json.loads((path/"metadata.json").read_text())
    return {"passed": True, "epoch": metadata["epoch"], "freeze": freeze,
            "independent_necessary_replay": True, "continuous_physical_model_proved": False}


class ReachRunDiscoveryTests(unittest.TestCase):
    def test_single_episode_public_audit_binds_metadata_without_changing_episode_api(self):
        for reader in (runtime, information):
            with self.subTest(reader=reader.__name__), tempfile.TemporaryDirectory() as temporary:
                path = episode(Path(temporary)/"episode001_open_101", "one")
                with patch.object(reader, "audit_episode", side_effect=passed) as mathematical:
                    result = reader.audit(path, FREEZE)
                mathematical.assert_called_once_with(path, FREEZE)
                self.assertTrue(result["passed"])
                self.assertEqual(result["attempted_episodes"], 1)
                self.assertEqual(result["episodes"][0]["result"]["epoch"], "one")

    def test_run_discovers_every_worker_episode_including_multiple_resets(self):
        for reader in (runtime, information):
            with self.subTest(reader=reader.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                paths = [episode(root/f"worker{w}/episode{e:03d}_open_101", f"epoch-{w}-{e}")
                         for w in range(2) for e in (1, 2)]
                with patch.object(reader, "audit_episode", side_effect=passed) as mathematical:
                    result = reader.audit(root)
                self.assertTrue(result["passed"])
                self.assertEqual(result["freeze"], FREEZE)
                self.assertEqual(result["attempted_episodes"], 4)
                self.assertEqual([call.args[0] for call in mathematical.call_args_list], paths)
                self.assertEqual(len({row["epoch"] for row in result["episodes"]}), 4)

    def test_failed_attempt_is_retained_and_does_not_skip_a_later_episode(self):
        for reader in (runtime, information):
            with self.subTest(reader=reader.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bad = episode(root/"worker0/episode001_open_101", "bad")
                good = episode(root/"worker0/episode002_open_101", "good")
                def check(path, freeze):
                    if path == bad:
                        return {"passed": False, "errors": ["saved raw source failure"], "epoch": "bad", "freeze": freeze}
                    return passed(path, freeze)
                with patch.object(reader, "audit_episode", side_effect=check) as mathematical:
                    result = reader.audit(root, FREEZE)
                self.assertFalse(result["passed"])
                self.assertEqual(mathematical.call_count, 2)
                self.assertEqual(len(result["episodes"]), 2)
                self.assertIn("saved raw source failure", repr(result["episodes"][0]))
                self.assertTrue(result["episodes"][1]["passed"])
                self.assertEqual(result["episodes"][1]["directory"], str(good))

    def test_missing_metadata_attempt_is_a_preserved_failure_not_silently_omitted(self):
        for reader in (runtime, information):
            with self.subTest(reader=reader.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                episode(root/"worker0/episode001_open_101", "one")
                missing = root/"worker0/episode002_open_101"; missing.mkdir()
                episode(root/"worker1/episode001_open_101", "three")
                with patch.object(reader, "audit_episode", side_effect=passed) as mathematical:
                    result = reader.audit(root, FREEZE)
                self.assertFalse(result["passed"])
                self.assertEqual(result["attempted_episodes"], 3)
                self.assertEqual(mathematical.call_count, 2)
                failed = next(row for row in result["episodes"] if row["directory"] == str(missing))
                self.assertFalse(failed["passed"])
                self.assertTrue(failed["errors"])

    def test_duplicate_epoch_mixed_freeze_and_legacy_declarations_cannot_share_run_credit(self):
        for reader in (runtime, information):
            for field, wrong in (("epoch", "one"), ("freeze", "b"*40), ("safety_contract", "legacy"),
                                 ("execution_phase_protocol", "mr3-controlled-execution-phase-v1")):
                with self.subTest(reader=reader.__name__, field=field), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    episode(root/"worker0/episode001_open_101", "one")
                    bad = episode(root/"worker0/episode002_open_101", "two")
                    path = bad/"metadata.json"; value = json.loads(path.read_text()); value[field] = wrong
                    path.write_text(json.dumps(value))
                    with patch.object(reader, "audit_episode", side_effect=passed) as mathematical:
                        result = reader.audit(root, FREEZE)
                    self.assertFalse(result["passed"])
                    self.assertEqual(result["attempted_episodes"], 2)
                    self.assertEqual(mathematical.call_count, 1)

    def test_declared_episode_whose_whole_directory_is_missing_cannot_be_dropped(self):
        for reader in (runtime, information):
            with self.subTest(reader=reader.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                present = episode(root/"worker0/episode001_open_101", "one")
                missing = root/"worker0/episode002_open_101"
                (root/"benchmark_summary.json").write_text(json.dumps({"workers_results": [{"episodes": [
                    {"output_directory": str(present)}, {"output_directory": str(missing)}]}]}))
                with patch.object(reader, "audit_episode", side_effect=passed): result = reader.audit(root, FREEZE)
                self.assertFalse(result["passed"])
                self.assertEqual(result["attempted_episodes"], 1)  # Never invent the absent attempt as executed.
                self.assertTrue(any("missing or unlisted" in error for error in result["errors"]))

    def test_new_episode_or_changed_metadata_during_audit_invalidates_the_frontier(self):
        for reader in (runtime, information):
            for mutation in ("new_episode", "metadata"):
                with self.subTest(reader=reader.__name__, mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary); episode(root/"worker0/episode001_open_101", "one")
                    def change(path, freeze):
                        report = passed(path, freeze)
                        if mutation == "new_episode": episode(root/"worker1/episode001_open_101", "two")
                        else: (path/"metadata.json").write_bytes((path/"metadata.json").read_bytes()+b"\n")
                        return report
                    with patch.object(reader, "audit_episode", side_effect=change): result = reader.audit(root, FREEZE)
                    self.assertFalse(result["passed"])
                    self.assertTrue(any("changed during audit" in error for error in result["errors"]))

    def test_both_clis_route_runs_to_all_episode_audits_and_keep_real_failure_exit(self):
        for reader in (runtime, information):
            with self.subTest(reader=reader.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                episode(root/"worker0/episode001_open_101", "one")
                episode(root/"worker0/episode002_open_101", "two")
                output = root/"review.json"
                def check(path, freeze):
                    if path.name.startswith("episode002"): raise ValueError("second actual attempt failed")
                    return passed(path, freeze)
                with patch.object(reader, "audit_episode", side_effect=check) as mathematical, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(reader.main([str(root), "--freeze", FREEZE, "--output", str(output)]), 1)
                self.assertEqual(mathematical.call_count, 2)
                result = json.loads(output.read_text())
                self.assertEqual(result["attempted_episodes"], 2)
                self.assertFalse(result["passed"])
                self.assertTrue(any("second actual attempt failed" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
