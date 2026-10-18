"""Attempt inventory and aggregation regressions; no native processes."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import audit_policy_inputs as audit


FREEZE = "a" * 40


def fixture(directory, count=1):
    episodes = []
    for index in range(count):
        episode = directory / "native" / "round0000" / f"worker{index}" / "episode001_open_101"
        episode.mkdir(parents=True)
        (episode / "metadata.json").write_text(json.dumps({"freeze": FREEZE}))
        episodes.append(episode)
    (directory / "metadata.json").write_text(json.dumps({"freeze": FREEZE}))
    (directory / "summary.json").write_text(json.dumps({
        "freeze": FREEZE, "episodes": [{"directory": str(path)} for path in episodes]}))
    return episodes


class PolicyInputsAuditTests(unittest.TestCase):
    def consumers(self, stack):
        stack.enter_context(patch.object(audit, "verify_sources", return_value={"fixture": {}}))
        return {name: stack.enter_context(patch.object(audit, name, return_value={"passed": True}))
                for name in ("audit_archives", "audit_activity", "audit_motion",
                             "audit_execution_inputs")}

    def test_no_attempt_and_missing_or_unlisted_attempt_fail(self):
        for mutation in ("empty", "missing_metadata", "unlisted", "missing_attempt"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary, \
                    ExitStack() as stack:
                directory = Path(temporary)
                episodes = fixture(directory, count=0 if mutation == "empty" else 1)
                self.consumers(stack)
                if mutation == "missing_metadata":
                    (episodes[0] / "metadata.json").unlink()
                elif mutation == "unlisted":
                    (directory / "summary.json").write_text(json.dumps({
                        "freeze": FREEZE, "episodes": []}))
                elif mutation == "missing_attempt":
                    (episodes[0] / "metadata.json").unlink()
                    episodes[0].rmdir()
                result = audit.audit_run(directory, FREEZE)
                self.assertFalse(result["passed"])
                self.assertTrue(any("native attempts" in error for error in result["errors"]))

    def test_each_leaf_error_is_retained_and_motion_result_is_reused(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            directory = Path(temporary)
            fixture(directory, count=2)
            consumers = self.consumers(stack)
            consumers["audit_archives"].side_effect = [ValueError("bad archive"), {"passed": True}]
            consumers["audit_activity"].side_effect = [{"passed": False, "errors": ["bad activity"]},
                                                        {"passed": True}]
            motion = {"passed": True, "marker": "reuse original review"}
            consumers["audit_motion"].return_value = motion
            result = audit.audit_run(directory, FREEZE)
            self.assertFalse(result["passed"])
            self.assertIn("bad archive", " ".join(result["errors"]))
            self.assertEqual(result["episodes"][0]["activity"]["errors"], ["bad activity"])
            self.assertFalse(result["episodes"][0]["passed"])
            self.assertTrue(result["episodes"][1]["passed"])
            for consumer in consumers.values():
                self.assertEqual(consumer.call_count, 2)
            for call in consumers["audit_execution_inputs"].call_args_list:
                self.assertIs(call.kwargs["motion_review"], motion)

    def test_motion_exception_is_not_retried_by_execution_consumer(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            directory = Path(temporary)
            fixture(directory)
            consumers = self.consumers(stack)
            consumers["audit_motion"].side_effect = RuntimeError("motion failed")
            result = audit.audit_run(directory, FREEZE)
            self.assertFalse(result["passed"])
            consumers["audit_motion"].assert_called_once()
            self.assertEqual(consumers["audit_execution_inputs"].call_args.kwargs["motion_review"],
                             {"passed": False})

    def test_mixed_episode_freeze_and_active_attempt_fail(self):
        for mutation in ("episode_freeze", "top_freeze", "top_null", "episode_null",
                         "active", "duplicate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary, \
                    ExitStack() as stack:
                directory = Path(temporary)
                episodes = fixture(directory)
                self.consumers(stack)
                if mutation == "episode_freeze":
                    (episodes[0] / "metadata.json").write_text(json.dumps({"freeze": "b" * 40}))
                elif mutation == "top_freeze":
                    (directory / "metadata.json").write_text(json.dumps({"freeze": "b" * 40}))
                elif mutation == "top_null":
                    (directory / "metadata.json").write_text("null")
                elif mutation == "episode_null":
                    (episodes[0] / "metadata.json").write_text("null")
                else:
                    path = directory / "summary.json"
                    summary = json.loads(path.read_text())
                    if mutation == "active":
                        summary["active_attempts"] = [{"worker_id": 1}]
                    else:
                        summary["episodes"] *= 2
                    path.write_text(json.dumps(summary))
                self.assertFalse(audit.audit_run(directory, FREEZE)["passed"])

    def test_consumer_git_bytes_are_bound_and_mismatch_fails_closed(self):
        def frozen(command, **kwargs):
            return (kwargs["cwd"] / command[2].split(":", 1)[1]).read_bytes()

        with patch.object(audit.subprocess, "check_output", side_effect=frozen):
            proof = audit.verify_sources(FREEZE)
        self.assertEqual(len(proof), 7)
        self.assertTrue(any(path.endswith("/audit_policy_inputs.py") for path in proof))
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            directory = Path(temporary)
            fixture(directory)
            self.consumers(stack)
            stack.enter_context(patch.object(audit, "verify_sources",
                                            side_effect=ValueError("consumer changed")))
            result = audit.audit_run(directory, FREEZE)
            self.assertFalse(result["passed"])
            self.assertIn("consumer changed", " ".join(result["errors"]))
        with patch.object(audit.subprocess, "check_output", return_value=b"changed"):
            with self.assertRaisesRegex(ValueError, "differs from freeze"):
                audit.verify_sources(FREEZE)

    def test_cli_writes_failed_report_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()), patch.object(audit, "verify_sources", return_value={}):
            directory = Path(temporary)
            fixture(directory, count=0)
            output = directory / "review.json"
            arguments = [str(directory), "--freeze", FREEZE, "--output", str(output)]
            self.assertEqual(audit.main(arguments), 1)
            original = output.read_bytes()
            self.assertFalse(json.loads(original)["passed"])
            with self.assertRaises(SystemExit) as caught:
                audit.main(arguments)
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
