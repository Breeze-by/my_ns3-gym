"""Pure admission/outer-receipt fixtures; no child, world or formal replay."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import proxy2d_activity as activity


class ActivityFixtures(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mr3-proxy-activity-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.start = {"freeze": "a" * 40, "started_ns": 1_100_000_000,
                      "coordinator_identity": {"pid": 2147483647, "start_ticks": 123}}
        self.outer = {"actual_waited": True, "scope": "engineering", "source_unchanged": True,
            "actual_argv": [sys.executable, "-B", "-m", "mr3_learning.proxy2d_activity", "execute",
                            "--freeze", self.start["freeze"]],
            "started_monotonic_ns": 1_000_000_000, "ended_monotonic_ns": 2_200_000_000,
            "actual_child_wait_seconds": "1.2000", "actual_returncode": 1,
            "child_identity": copy.deepcopy(self.start["coordinator_identity"])}

    def final(self, outer=None, start=None, *, now=3_000_000_000, proc=None):
        (self.run / "activity_start.json").write_text(json.dumps(start or self.start))
        (self.run / "activity_result.json").write_text(json.dumps({"passed": False}))
        selected = self.root / "outer.json"
        selected.write_text(json.dumps(outer or self.outer))
        target = self.root / "final.json"
        if target.exists():
            target.unlink()
        original = Path.read_text
        def read(path, *args, **kwargs):
            if str(path).startswith("/proc/"):
                if isinstance(proc, Exception):
                    raise proc
                if proc is not None:
                    return proc
                raise FileNotFoundError(str(path))
            return original(path, *args, **kwargs)
        with patch.object(activity.time, "monotonic_ns", return_value=now), patch.object(Path, "read_text", read):
            return activity.final(self.run, selected, target)

    def test_phase_admission_reserves_external_and_cleanup_before_any_work(self):
        now = 1_000_000_000
        for remaining in (300, 480, 480.999):
            with self.subTest(remaining=remaining), self.assertRaises(RuntimeError):
                activity.admitted_seconds(now + round(remaining * 1e9), 600, now)
        self.assertEqual(activity.admitted_seconds(now + 481_000_000_000, 600, now), 1)
        self.assertEqual(activity.admitted_seconds(now + 650_000_000_000, 600, now), 170)
        self.assertEqual(activity.admitted_seconds(now + 1000_000_000_000, 180, now), 180)

    def test_source_admission_time_is_inside_the_single_activity_clock(self):
        clock = [1_000_000_000]
        plan_path = self.root / "plan.json"
        plan_path.write_text("{}")
        plan = {"output": str(self.root / "execute"), "source_bindings": {}}
        def check(*args):
            clock[0] = 31_000_000_000  # Explicit synthetic source-check cost.
            return plan
        with patch.object(activity.time, "monotonic_ns", side_effect=lambda: clock[0]), \
                patch.object(activity, "check", side_effect=check), \
                patch.object(activity, "sha", return_value="0" * 64), \
                patch.object(activity, "process_identity", return_value={"pid": 1, "start_ticks": 1}), \
                patch.object(activity, "phase", return_value={"passed": True}) as phase:
            result = activity.execute(plan_path, "a" * 40)
        self.assertEqual(result["started_ns"], 1_000_000_000)
        self.assertEqual(result["deadline_ns"] - result["started_ns"], 3600 * 10**9)
        self.assertEqual(phase.call_count, 4)

    def test_valid_exact_outer_can_close_absence_without_hiding_activity_failure(self):
        result = self.final()
        self.assertTrue(result["absence_passed"])
        self.assertFalse(result["activity_passed"])
        self.assertEqual(result["outer_actual_returncode"], 1)
        self.assertTrue(result["budget_observed_within_3600"])
        self.assertFalse(result["training_eligible"])
        self.assertFalse(result["qualification"])

    def test_foreign_or_inexact_outer_is_rejected_before_billing_or_absence_claim(self):
        for fault in ("argv", "scope", "unwaited", "changed", "pid", "ticks", "duration", "negative", "bool", "start_outside"):
            outer, start = copy.deepcopy(self.outer), copy.deepcopy(self.start)
            if fault == "argv": outer["actual_argv"][3] = "mr3_learning.reach_diagnostic"
            elif fault == "scope": outer["scope"] = "cpu"
            elif fault == "unwaited": outer["actual_waited"] = False
            elif fault == "changed": outer["source_unchanged"] = False
            elif fault == "pid": outer["child_identity"]["pid"] -= 1
            elif fault == "ticks": outer["child_identity"]["start_ticks"] += 1
            elif fault == "duration": outer["actual_child_wait_seconds"] = "1.199999999"
            elif fault == "negative": outer["ended_monotonic_ns"] = 1
            elif fault == "bool": outer["started_monotonic_ns"] = True
            else: start["started_ns"] = outer["ended_monotonic_ns"] + 1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.final(outer, start)

    def test_same_saved_zombie_or_unreadable_proc_cannot_be_called_absent(self):
        fields = ["Z"] + ["0"] * 18 + ["123"]
        result = self.final(proc="2147483647 (synthetic) " + " ".join(fields))
        self.assertFalse(result["absence_passed"])
        self.assertEqual(result["present"][0]["actual_state"], "Z")
        result = self.final(proc=PermissionError("synthetic unreadable proc"))
        self.assertFalse(result["absence_passed"])
        self.assertEqual(len(result["unreadable"]), 1)

    def test_external_close_cannot_claim_the_activity_budget_after_3600_seconds(self):
        result = self.final(now=self.outer["started_monotonic_ns"] + 3600 * 10**9 + 1)
        self.assertTrue(result["absence_passed"])
        self.assertFalse(result["budget_observed_within_3600"])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
