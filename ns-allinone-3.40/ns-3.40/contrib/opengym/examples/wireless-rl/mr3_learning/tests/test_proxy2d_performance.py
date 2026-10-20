"""Pure performance-plan/receipt fixtures; no worker, world or formal replay."""
import copy
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import sys
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import proxy2d_performance as performance


def worker_fixture():
    return sum(index * index for index in range(150))


def evaluator_fixture():
    return sum(index + 1 for index in range(120))


class PerformanceFixtures(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mr3-proxy-performance-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.episode = self.run / "episode"
        self.episode.mkdir()
        (self.episode / "episode.json").write_text(json.dumps({"profile_enabled": True}))
        (self.run / "capacity_summary.json").write_text(json.dumps({
            "activity_spec": performance.activity_spec("profile"),
            "groups": [{"episodes": [{"directory": str(self.episode)}]}],
        }))
        self.plan = self.root / "profile_plan.json"
        self.plan.write_text("{}\n")
        self.start = {
            "schema": "mr3-proxy2d-performance-activity-v1", "kind": "profile", "freeze": "a" * 40,
            "plan_sha256": hashlib.sha256(self.plan.read_bytes()).hexdigest(),
            "started_ns": 1_100_000_000, "deadline_ns": 601_100_000_000,
            "coordinator_identity": {"pid": 2147483647, "start_ticks": 123},
        }
        self.outer = {
            "actual_waited": True, "scope": "engineering", "source_unchanged": True,
            "actual_argv": [sys.executable, "-B", "-m", "mr3_learning.proxy2d_performance", "execute",
                            "--kind", "profile", "--freeze", self.start["freeze"]],
            "cwd": str(performance.W),
            "started_monotonic_ns": 1_000_000_000, "ended_monotonic_ns": 2_200_000_000,
            "actual_child_wait_seconds": "1.2000", "actual_returncode": 1,
            "child_identity": copy.deepcopy(self.start["coordinator_identity"]),
        }

    def final(self, outer=None, start=None, *, kind="profile", now=3_000_000_000, proc=None):
        (self.run / "activity_start.json").write_text(json.dumps(self.start if start is None else start))
        (self.run / "activity_result.json").write_text(json.dumps({"passed": False, "errors": ["fixture activity failure"]}))
        selected = self.root / "outer.json"
        selected.write_text(json.dumps(self.outer if outer is None else outer))
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

        with patch.object(performance.time, "monotonic_ns", return_value=now), \
                patch.object(performance, "plan_path", return_value=self.plan), \
                patch.object(Path, "read_text", read):
            return performance.final(kind, self.run, selected, target)

    def profile(self, relative, function):
        target = self.run / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        profiler = cProfile.Profile()
        profiler.runcall(function)
        profiler.dump_stats(str(target))
        return target

    def test_admission_reserves_external120_and_cleanup180_before_any_phase(self):
        now = 1_000_000_000
        for remaining_ns in (120 * 10**9, 300 * 10**9, 300_999_999_999):
            with self.subTest(remaining_ns=remaining_ns), self.assertRaises(RuntimeError):
                performance.admitted_seconds(now + remaining_ns, 240, now)
        self.assertEqual(performance.admitted_seconds(now + 301 * 10**9, 240, now), 1)
        self.assertEqual(performance.admitted_seconds(now + 450 * 10**9, 240, now), 150)
        self.assertEqual(performance.admitted_seconds(now + 1000 * 10**9, 120, now), 120)

    def test_profile_report_keeps_worker_and_evaluator_pstats_separate(self):
        worker = self.profile("episode/worker.pstats", worker_fixture)
        evaluator = self.profile("episode/evaluator.pstats", evaluator_fixture)
        result = performance.profile_report(self.run)
        self.assertTrue(result["passed"])
        self.assertEqual({item["role"] for item in result["profiles"]}, {"worker", "evaluator"})
        by_role = {item["role"]: item for item in result["profiles"]}
        for role, path, function in (("worker", worker, worker_fixture), ("evaluator", evaluator, evaluator_fixture)):
            with self.subTest(role=role):
                stats = pstats.Stats(str(path))
                self.assertEqual(by_role[role]["total_self_seconds"], stats.total_tt)
                self.assertEqual(by_role[role]["total_calls"], stats.total_calls)
                self.assertTrue(any(row["function"] == function.__name__ for row in by_role[role]["top_self"]))
                self.assertTrue(any(row["function"] == function.__name__ for row in by_role[role]["top_cumulative"]))
        self.assertNotIn("total_self_seconds", result)
        self.assertNotIn("total_cumulative_seconds", result)
        self.assertIn("must not be added", result["scope"])
        self.assertFalse(result["qualification"])
        self.assertFalse(result["training_eligible"])
        with self.assertRaises(ValueError):
            performance.profile_report(self.run)

    def test_profile_report_missing_or_duplicate_role_cannot_pass(self):
        self.profile("episode/worker.pstats", worker_fixture)
        with self.assertRaises(ValueError):
            performance.profile_report(self.run)
        self.profile("episode/evaluator.pstats", evaluator_fixture)
        self.profile("other_episode/worker.pstats", worker_fixture)
        with self.assertRaises(ValueError):
            performance.profile_report(self.run)

    def test_unknown_profile_role_is_rejected(self):
        self.profile("episode/actor.pstats", worker_fixture)
        with self.assertRaises(ValueError):
            performance.profile_report(self.run)

    def test_absence_receipt_preserves_activity_failure_and_exact_outer_seconds(self):
        result = self.final()
        self.assertTrue(result["absence_passed"])
        self.assertFalse(result["activity_passed"])
        self.assertEqual(result["outer_engineering_seconds"], "1.2000")
        self.assertTrue(result["accounting_requires_this_external_actual_wait"])
        self.assertFalse(result["qualification"])
        self.assertFalse(result["training_eligible"])

    def test_foreign_inexact_or_untyped_outer_is_rejected(self):
        faults = ("argv", "extra_argv", "cwd", "scope", "unwaited", "changed", "truthy_changed",
                  "pid", "ticks", "duration", "negative", "bool_ns", "float_ns", "start_outside",
                  "kind", "schema", "plan")
        for fault in faults:
            outer, start = copy.deepcopy(self.outer), copy.deepcopy(self.start)
            if fault == "argv": outer["actual_argv"][3] = "mr3_learning.proxy2d_activity"
            elif fault == "extra_argv": outer["actual_argv"].append("--extra")
            elif fault == "cwd": outer["cwd"] = str(self.root)
            elif fault == "scope": outer["scope"] = "cpu"
            elif fault == "unwaited": outer["actual_waited"] = False
            elif fault == "changed": outer["source_unchanged"] = False
            elif fault == "truthy_changed": outer["source_unchanged"] = "false"
            elif fault == "pid": outer["child_identity"]["pid"] -= 1
            elif fault == "ticks": outer["child_identity"]["start_ticks"] += 1
            elif fault == "duration": outer["actual_child_wait_seconds"] = "1.199999999"
            elif fault == "negative": outer["ended_monotonic_ns"] = 1
            elif fault == "bool_ns": outer["started_monotonic_ns"] = True
            elif fault == "float_ns": outer["ended_monotonic_ns"] = float(outer["ended_monotonic_ns"])
            elif fault == "start_outside": start["started_ns"] = outer["ended_monotonic_ns"] + 1
            elif fault == "kind": start["kind"] = "short_capacity"
            elif fault == "schema": start["schema"] = "other-activity"
            else: start["plan_sha256"] = "0" * 64
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.final(outer, start)

    def test_final_rejects_an_outer_which_has_not_ended_yet(self):
        with self.assertRaises(ValueError):
            self.final(now=self.outer["ended_monotonic_ns"] - 1)

    def test_same_start_zombie_and_unreadable_identity_cannot_be_absent(self):
        fields = ["Z"] + ["0"] * 18 + ["123"]
        result = self.final(proc="2147483647 (synthetic) " + " ".join(fields))
        self.assertFalse(result["absence_passed"])
        self.assertEqual(result["present"][0]["state"], "Z")
        for unreadable in (PermissionError("fixture proc permission"), "malformed fixture stat"):
            with self.subTest(unreadable=str(unreadable)):
                result = self.final(proc=unreadable)
                self.assertFalse(result["absence_passed"])
                self.assertEqual(len(result["unreadable"]), 1)

    def test_reused_pid_with_a_different_start_is_not_the_saved_process(self):
        fields = ["Z"] + ["0"] * 18 + ["124"]
        self.assertTrue(self.final(proc="2147483647 (reused) " + " ".join(fields))["absence_passed"])

    def test_external_receipt_cannot_claim_pass_after_its_bounded_clock(self):
        for kind, seconds in (("profile", 600), ("short_capacity", 1800), ("full_behavior", 3600)):
            outer, start = copy.deepcopy(self.outer), copy.deepcopy(self.start)
            start["kind"] = kind
            start["deadline_ns"] = start["started_ns"] + seconds * 10**9
            outer["actual_argv"][6] = kind
            with self.subTest(kind=kind):
                result = self.final(outer, start, kind=kind,
                    now=outer["started_monotonic_ns"] + seconds * 10**9 + 1)
                self.assertTrue(result["absence_passed"])
                self.assertFalse(result["activity_passed"])
                self.assertFalse(result["passed"])

    def test_full_behavior_plan_has_one_group_and_complete_audit_tail(self):
        scope = self.root / "scope_acceptance_v1.json"
        scope.write_text(json.dumps({"engineering_entry_used_seconds": "44068.6680536126018"}))
        with patch.object(performance, "B", self.root), \
                patch.object(performance, "bindings", return_value={"original.py": "f" * 64}), \
                patch.object(performance, "ROOT", self.root):
            result = performance.build("full_behavior", "44068.6680536126018")
        self.assertEqual(result["activity_spec"]["groups"], [3])
        self.assertEqual(result["activity_spec"]["max_attempts"], 900)
        self.assertEqual(result["group_wall_seconds"], [2100])
        self.assertEqual(result["phase_seconds"], {
            "conformity": 60, "conformity_review": 20, "collection": 2100,
            "audit": 950, "behavior_report": 100})
        self.assertEqual(result["external_reserve_seconds"], 120)
        self.assertEqual(set(result["source_bindings"]), {"original.py", "scope_acceptance_v1.json"})
        self.assertIn("mr3_p2a_proxy2d_v24/full_behavior_v1", result["output"])
        self.assertFalse(result["training_eligible"])

    def test_full_behavior_uses_clean_system_consumer_and_keeps_failed_collection(self):
        spec = performance.activity_spec("full_behavior")
        plan = {"activity_spec": spec, "output": str(self.root / "execute"),
                "phase_seconds": performance.PHASES["full_behavior"],
                "source_bindings": {}, "group_wall_seconds": [2100]}
        calls = []

        def phase(run, name, argv, seconds, **kwargs):
            calls.append((name, argv, seconds, kwargs))
            return {"passed": name != "collection"}

        with patch.object(performance, "check", return_value=plan), \
                patch.object(performance, "sha", return_value="0" * 64), \
                patch.object(performance, "activity_bindings", return_value={}), \
                patch.object(performance, "process_identity", return_value={"pid": 1, "start_ticks": 1}), \
                patch.object(performance, "phase", side_effect=phase), \
                patch.dict(performance.os.environ, {"PYTHONPATH": "/fake/conda", "CONDA_PREFIX": "/fake/conda"}):
            result = performance.execute("full_behavior", "a" * 40)
        self.assertEqual([call[0] for call in calls], list(performance.PHASES["full_behavior"]))
        self.assertFalse(result["passed"])
        report = calls[-1]
        self.assertEqual(report[1][0:4], ["/usr/bin/bash", "--noprofile", "--norc", "-c"])
        self.assertIn("exec /usr/bin/python3", report[1][4])
        self.assertIn("audit_proxy2d_behavior", report[1][4])
        self.assertEqual(report[2], 100)
        self.assertNotIn("PYTHONPATH", report[3]["environment"])
        self.assertNotIn("CONDA_PREFIX", report[3]["environment"])
        self.assertEqual(result["deadline_ns"]-result["started_ns"], 3600 * 10**9)

    def test_full_behavior_cannot_spend_more_than_the_existing_ceiling(self):
        with patch.object(performance, "B", self.root), self.assertRaises(ValueError):
            performance.build("full_behavior", "48400.000000001")

    def test_full_behavior_cannot_understate_the_accepted_entry_ledger(self):
        (self.root / "scope_acceptance_v1.json").write_text(json.dumps({
            "engineering_entry_used_seconds": "44068.6680536126018"}))
        with patch.object(performance, "B", self.root), self.assertRaises(ValueError):
            performance.check_entry("full_behavior", "44000")

    def test_collection_cli_kind_mismatch_is_rejected_before_collection(self):
        (self.run / "collection_context.json").write_text(json.dumps({
            "activity_spec": performance.activity_spec("full_behavior")}))
        with patch.object(sys, "argv", ["fixture", "collect", "--kind", "short_capacity",
                                        "--run", str(self.run)]), \
                patch.object(performance, "collect") as collect, self.assertRaises(ValueError):
            performance.main()
        collect.assert_not_called()

    def test_admission_failure_explicitly_records_why_behavior_report_was_skipped(self):
        plan = {"activity_spec": performance.activity_spec("full_behavior"),
                "output": str(self.root / "skipped"), "source_bindings": {},
                "phase_seconds": performance.PHASES["full_behavior"]}
        with patch.object(performance, "check", return_value=plan), \
                patch.object(performance, "sha", return_value="0" * 64), \
                patch.object(performance, "activity_bindings", return_value={}), \
                patch.object(performance, "process_identity", return_value={"pid": 1, "start_ticks": 1}), \
                patch.object(performance, "admitted_seconds", side_effect=RuntimeError("fixture reserve exhausted")):
            result = performance.execute("full_behavior", "a" * 40)
        self.assertFalse(result["passed"])
        self.assertIn("fixture reserve exhausted", result["behavior_report_skipped_reason"])


if __name__ == "__main__":
    unittest.main()
