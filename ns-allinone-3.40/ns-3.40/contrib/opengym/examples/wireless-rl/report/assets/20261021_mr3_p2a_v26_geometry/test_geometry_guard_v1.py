"""CPU-only guard fixtures: no child process, ROS import, or geometry consumer."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name("geometry_guard_v1.py")
SPEC = importlib.util.spec_from_file_location("geometry_guard_fixture", MODULE_PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
FREEZE = "a" * 40
FAKE_PID = 2147483000


class Child:
    pid = FAKE_PID

    def __init__(self, events, after_wait=None):
        self.events = list(events)
        self.timeouts = []
        self.returncode = None
        self.after_wait = after_wait
        self.direct_signals = []

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        event = self.events.pop(0)
        if event == "timeout":
            raise subprocess.TimeoutExpired("mock-only-consumer", timeout)
        self.returncode = event
        if self.after_wait:
            self.after_wait()
        return event

    def send_signal(self, number):
        self.direct_signals.append(number)


class GeometryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mr3_geometry_guard_fixture_")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "source.py"
        self.source.write_text("fixture = 1\n")
        self.output = self.directory / "guard"
        self.calls = []

    def execute(self, events=(0,), *, result=True, identity_error=False,
                popen_error=False, mutate=False, kill_error=None):
        child = Child(events, (lambda: self.source.write_text("fixture = 2\n")) if mutate else None)

        def fake_identity(pid):
            if pid == FAKE_PID and identity_error:
                raise OSError("mock identity capture failed")
            return {"pid": pid, "parent": os.getpid() if pid == FAKE_PID else 1,
                    "group": pid, "session": pid, "start_ticks": 123, "state": "S"}

        def popen(argv, **kwargs):
            self.calls.append((argv, kwargs))
            if popen_error:
                raise OSError("mock spawn failure")
            if result:
                Path(argv[-1]).write_text('{"fixture_only": true}\n')
            return child

        with mock.patch.object(guard, "identity", side_effect=fake_identity), \
             mock.patch.object(guard.subprocess, "Popen", side_effect=popen), \
             mock.patch.object(guard.os, "killpg", side_effect=kill_error) as killpg, \
             mock.patch.dict(os.environ, {"CONDA_PREFIX": "/mock/conda", "PYTHONPATH": "/mock/unsafe"}):
            receipt = guard.run(FREEZE, self.output, [self.source])
        saved = json.loads((self.output / "guard_receipt_v1.json").read_text())
        self.assertEqual(saved, receipt)
        self.assertFalse(receipt["qualification"])
        self.assertFalse(receipt["training_eligible"])
        self.assertFalse(receipt["native_credit"])
        return receipt, child, killpg

    def test_normal_completion_pins_consumer_and_clean_system_environment(self):
        receipt, child, killpg = self.execute()
        self.assertTrue(receipt["passed"])
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(receipt["actual_returncode"], 0)
        self.assertEqual(child.timeouts, [90.])
        killpg.assert_not_called()
        argv, options = self.calls[0]
        self.assertEqual(argv[0:3], ["/usr/bin/bash", "--noprofile", "--norc"])
        self.assertIn("exec /usr/bin/python3 -B -m", argv[4])
        self.assertEqual(argv[-3:], [guard.CONSUMER_MODULE, FREEZE,
                                    str(self.output / "geometry_result.json")])
        self.assertEqual(options["cwd"], guard.ROS)
        self.assertTrue(options["start_new_session"])
        self.assertNotIn("CONDA_PREFIX", options["env"])
        self.assertNotIn("PYTHONPATH", options["env"])
        self.assertEqual(options["env"]["PYTHONNOUSERSITE"], "1")
        self.assertEqual(options["env"]["CUDA_VISIBLE_DEVICES"], "")
        for name in ("guard_identity", "child_identity"):
            self.assertEqual(json.loads((self.output / (name + ".json")).read_text()), receipt[name])
        self.assertGreaterEqual(receipt["child_started_monotonic_ns"], receipt["started_monotonic_ns"])
        self.assertGreaterEqual(receipt["ended_monotonic_ns"], receipt["child_ended_monotonic_ns"])

    def test_timeout_terms_owned_group_and_actually_waits(self):
        receipt, child, killpg = self.execute(("timeout", -15))
        self.assertFalse(receipt["passed"])
        self.assertTrue(receipt["timed_out"])
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(child.timeouts, [90., 10.])
        killpg.assert_called_once_with(FAKE_PID, signal.SIGTERM)

    def test_term_timeout_kills_owned_group_then_waits_five_seconds(self):
        receipt, child, killpg = self.execute(("timeout", "timeout", -9))
        self.assertFalse(receipt["passed"])
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(child.timeouts, [90., 10., 5.])
        self.assertEqual(killpg.call_args_list, [mock.call(FAKE_PID, signal.SIGTERM),
                                               mock.call(FAKE_PID, signal.SIGKILL)])

    def test_kill_reap_overrun_is_failed_and_still_actually_reaped(self):
        receipt, child, _ = self.execute(("timeout", "timeout", "timeout", -9))
        self.assertFalse(receipt["passed"])
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(child.timeouts, [90., 10., 5., None])
        self.assertTrue(any("KILL reap allowance" in error for error in receipt["errors"]))

    def test_failed_identity_capture_still_cleans_owned_popen(self):
        receipt, child, killpg = self.execute((-15,), identity_error=True)
        self.assertFalse(receipt["passed"])
        self.assertIsNone(receipt["child_identity"])
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(child.timeouts, [10.])
        killpg.assert_called_once_with(FAKE_PID, signal.SIGTERM)
        self.assertTrue(any("identity capture failed" in error for error in receipt["errors"]))

    def test_group_signal_error_is_failed_even_if_direct_handle_cleanup_works(self):
        receipt, child, _ = self.execute(("timeout", -15), kill_error=PermissionError("mock denied"))
        self.assertFalse(receipt["passed"])
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(child.direct_signals, [signal.SIGTERM])
        self.assertTrue(receipt["errors"])

    def test_spawn_error_saves_failed_receipt_without_claiming_wait(self):
        receipt, child, killpg = self.execute(popen_error=True)
        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["actual_waited"])
        self.assertIsNone(receipt["actual_child_wait_seconds"])
        self.assertEqual(child.timeouts, [])
        killpg.assert_not_called()

    def test_source_change_is_failed_even_after_clean_exit(self):
        receipt, _, _ = self.execute(mutate=True)
        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["source_unchanged"])
        self.assertNotEqual(receipt["source_before"], receipt["source_after"])

    def test_missing_output_is_failed_even_after_clean_exit(self):
        receipt, _, _ = self.execute(result=False)
        self.assertFalse(receipt["passed"])
        self.assertIn("consumer result missing", receipt["errors"])

    def test_admission_rejects_nonexplicit_freeze_empty_source_and_existing_output(self):
        with mock.patch.object(guard.subprocess, "Popen") as popen:
            for bad in ("a" * 39, "A" * 40, "HEAD"):
                with self.assertRaises(ValueError):
                    guard.run(bad, self.output, [self.source])
            with self.assertRaises(ValueError):
                guard.run(FREEZE, self.output, [])
            with self.assertRaises(ValueError):
                guard.run(FREEZE, Path("/var/tmp/mr3_forbidden"), [self.source])
            self.output.mkdir()
            with self.assertRaises(FileExistsError):
                guard.run(FREEZE, self.output, [self.source])
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
