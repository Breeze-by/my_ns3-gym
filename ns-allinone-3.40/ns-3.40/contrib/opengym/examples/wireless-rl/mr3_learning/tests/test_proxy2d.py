"""Stubbed process/pipe custody fixtures; no proxy, ROS or native episode."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from mr3_learning import proxy2d


def identity(pid, parent=1):
    return {"pid": pid, "parent": parent, "group": pid if parent == 1 else parent,
            "session": pid if parent == 1 else parent, "start_ticks": pid * 10, "state": "S"}


class Process:
    """Only wait outcomes are synthetic; no OS process is created."""

    def __init__(self, pid, waits=(0,)):
        self.pid, self.returncode = pid, None
        self.stdin, self.stdout = Mock(), Mock()
        self.stdin.fileno.return_value, self.stdout.fileno.return_value = 8, 9
        self.waits, self.wait_calls = list(waits), []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        outcome = self.waits.pop(0) if self.waits else 0
        if isinstance(outcome, Exception):
            raise outcome
        self.returncode = outcome
        self.on_reaped()
        return outcome


class ProxySupervisorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mr3-proxy2d-supervisor-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.owner = proxy2d.ProxySupervisor(self.root / "env0")
        self.processes, self.observed = [], {}
        self.peer = Mock()
        self.peer.receive.return_value = {"ok": True, "result": {"closed": True}}
        for target, value in (("ros_environment", {}), ("JsonLinePeer", self.peer)):
            selected = patch.object(proxy2d, target, return_value=value)
            self.addCleanup(selected.stop)
            selected.start()
        selected = patch.object(proxy2d, "process_identity", side_effect=lambda pid: copy.deepcopy(self.observed.get(pid)))
        self.addCleanup(selected.stop)
        selected.start()
        selected = patch.object(proxy2d.subprocess, "Popen", side_effect=self.spawn)
        self.addCleanup(selected.stop)
        selected.start()
        selected = patch.object(proxy2d.os, "killpg")
        self.addCleanup(selected.stop)
        self.killpg = selected.start()
        for name, replacement in (("pidfd_open", Mock(return_value=123)),
                                  ("pidfd_send_signal", Mock())):
            selected = patch.object(proxy2d, name, replacement)
            self.addCleanup(selected.stop)
            selected.start()
            setattr(self, name, replacement)
        selected = patch.object(proxy2d.os, "close")
        self.addCleanup(selected.stop)
        self.close_fd = selected.start()
        self.poller = Mock()
        self.poller.poll.return_value = [(123, 1)]
        selected = patch.object(proxy2d.select, "poll", return_value=self.poller)
        self.addCleanup(selected.stop)
        selected.start()

    def spawn(self, *args, **kwargs):
        process = self.processes[len([p for p in self.processes if getattr(p, "selected", False)])]
        process.selected = True
        return process

    def add_process(self, pid, waits=(0,)):
        process = Process(pid, waits)
        self.processes.append(process)
        self.observed[pid] = identity(pid)
        def reaped():
            self.observed.pop(pid, None)
            if not getattr(process, "orphan_survives", False):
                self.observed.pop(pid + 10000, None)
        process.on_reaped = reaped
        return process

    def reset_result(self, operation, **fields):
        if operation == "close":
            return {"closed": True}
        self.assertEqual(operation, "reset")
        process = self.owner.process
        child = identity(process.pid + 10000, process.pid)
        self.observed[child["pid"]] = child
        (self.owner.directory / "evaluator_identity.json").write_text(json.dumps(child))
        metadata = json.loads((self.owner.directory / "episode.json").read_text())
        return {"snapshot": {"epoch": metadata["epoch"]}, "terminated": False,
                "truncated": False, "info": {"epoch": metadata["epoch"],
                                              "training_eligible": False, "proxy_only": True}}

    def successful_reset(self, scene="open", seed=101):
        with patch.object(self.owner, "_rpc", side_effect=self.reset_result):
            return self.owner.reset(scene, seed)

    def test_two_episode_identity_history_does_not_choose_the_current_owner_by_list_offset(self):
        first = self.add_process(51001)
        second = self.add_process(51002, (
            subprocess.TimeoutExpired("declared CPU fixture", 12.), 0))
        self.successful_reset()
        first_directory = self.owner.directory
        self.successful_reset("rooms", 103)
        self.assertEqual(first.returncode, 0)
        second_directory = self.owner.directory
        # A third historical observer must not alter which group is owned now.
        self.owner.identities.append(identity(99999))
        self.owner.close(failed=True)
        self.killpg.assert_called_once_with(second.pid, 15)
        self.assertEqual(second.wait_calls, [12., 10.])
        self.assertTrue((first_directory / "supervisor_close.json").exists())
        receipt = json.loads((second_directory / "supervisor_close.json").read_text())
        self.assertTrue(receipt["actual_waited"])
        self.assertTrue(receipt["forced"])
        self.assertFalse(receipt["passed"])

    def test_reset_failure_before_evaluator_identity_still_waits_and_cleans_current_worker(self):
        process = self.add_process(52001, (subprocess.TimeoutExpired("reset fixture", 12.), 0))
        self.owner.identities.extend((identity(10001), identity(10002)))
        with patch.object(self.owner, "_rpc", side_effect=proxy2d.InfrastructureError("reset failed before evaluator")):
            with self.assertRaisesRegex(proxy2d.InfrastructureError, "before evaluator"):
                self.owner.reset()
        self.killpg.assert_called_once_with(process.pid, 15)
        self.assertIsNone(self.owner.process)
        self.assertIsNone(self.owner.last_result)
        self.assertEqual(process.wait_calls, [12., 10.])

    def test_error_response_invalidates_previous_step_and_cannot_be_reused(self):
        self.add_process(53001)
        self.successful_reset()
        self.peer.receive.return_value = {"ok": False, "error": "explicit failed step response"}
        with self.assertRaisesRegex(proxy2d.InfrastructureError, "failed step"):
            self.owner.step(888)
        self.assertIsNone(self.owner.last_result)
        self.assertIsNone(self.owner.process)
        with self.assertRaisesRegex(RuntimeError, "reset required"):
            self.owner.step(888)
        self.assertEqual(self.peer.send.call_count, 1)

    def test_rpc_timeout_after_step_is_not_an_eligible_previous_observation(self):
        self.add_process(54001)
        self.successful_reset()
        self.peer.receive.side_effect = TimeoutError("CPU fixture response deadline")
        with self.assertRaises(TimeoutError):
            self.owner.step(888)
        self.assertIsNone(self.owner.last_result)
        self.assertIsNone(self.owner.process)
        self.assertFalse(self.owner.training_eligible)
        self.assertFalse(self.owner.native_qualification)

    def test_term_timeout_escalates_only_saved_owner_group_and_actually_waits(self):
        process = self.add_process(55001, (
            subprocess.TimeoutExpired("term fixture", 12.),
            subprocess.TimeoutExpired("term fixture", 10.), -9))
        self.successful_reset()
        directory = self.owner.directory
        self.owner.close(failed=True)
        self.assertEqual([call.args for call in self.killpg.call_args_list], [(process.pid, 15), (process.pid, 9)])
        self.assertEqual(process.wait_calls[:2], [12., 10.])
        self.assertEqual(len(process.wait_calls), 3)
        receipt = json.loads((directory / "supervisor_close.json").read_text())
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(receipt["returncode"], -9)
        self.assertFalse(receipt["passed"])

    def test_wrong_parent_evaluator_is_rejected_without_claiming_training_credit(self):
        process = self.add_process(56001)
        def foreign(operation, **fields):
            response = self.reset_result(operation, **fields)
            if operation == "reset":
                self.observed[process.pid + 10000]["parent"] = 42
            return response
        with patch.object(self.owner, "_rpc", side_effect=foreign):
            with self.assertRaises(proxy2d.InfrastructureError):
                self.owner.reset()
        self.assertIsNone(self.owner.process)
        self.assertIsNone(self.owner.last_result)
        metadata = json.loads((self.owner.directory / "episode.json").read_text())
        self.assertTrue(metadata["proxy_only"])
        self.assertFalse(metadata["training_eligible"])
        self.killpg.assert_not_called()

    def test_reused_pid_identity_never_authorizes_signaling_a_foreign_group(self):
        process = self.add_process(57001, (subprocess.TimeoutExpired("mismatch fixture", 12.), 0))
        self.successful_reset()
        self.observed[process.pid]["start_ticks"] += 1
        self.owner.close(failed=True)
        self.killpg.assert_not_called()
        self.assertIsNone(self.owner.process)

    def test_popen_failure_closes_console_and_leaves_no_reusable_result(self):
        with patch.object(proxy2d.subprocess, "Popen", side_effect=OSError("explicit spawn failure")):
            with self.assertRaisesRegex(OSError, "spawn failure"):
                self.owner.reset()
        self.assertTrue(self.owner.console is None or self.owner.console.closed)
        self.assertIsNone(self.owner.process)
        self.assertIsNone(self.owner.last_result)

    def test_normal_reaped_evaluator_never_opens_or_signals_a_pidfd(self):
        self.add_process(58001)
        self.successful_reset()
        directory = self.owner.directory
        self.owner.close(failed=True)
        self.pidfd_open.assert_not_called()
        self.pidfd_send_signal.assert_not_called()
        receipt = json.loads((directory / "supervisor_close.json").read_text())
        self.assertTrue(receipt["passed"])
        self.assertFalse(receipt["forced"])

    def test_live_owned_orphan_gets_verified_pidfd_cleanup_and_forced_failure(self):
        process = self.add_process(59001)
        process.orphan_survives = True
        self.successful_reset()
        directory = self.owner.directory
        self.poller.poll.side_effect = [[], [(123, 1)]]
        self.owner.close(failed=True)
        self.pidfd_open.assert_called_once_with(process.pid + 10000)
        self.assertEqual([call.args for call in self.pidfd_send_signal.call_args_list], [(123, 15), (123, 9)])
        self.close_fd.assert_called_once_with(123)
        receipt = json.loads((directory / "supervisor_close.json").read_text())
        self.assertTrue(receipt["actual_waited"])
        self.assertTrue(receipt["forced"])
        self.assertFalse(receipt["passed"])


if __name__ == "__main__":
    unittest.main()
