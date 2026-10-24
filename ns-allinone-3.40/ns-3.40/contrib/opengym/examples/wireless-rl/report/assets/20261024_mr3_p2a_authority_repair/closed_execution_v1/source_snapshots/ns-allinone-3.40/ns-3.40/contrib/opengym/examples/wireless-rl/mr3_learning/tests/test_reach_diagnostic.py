"""Diagnostic admission and external bookkeeping; no native/GPU execution.

Git bytes and the runtime inventory are stubbed only for the admission fixture.
The external checks use declared synthetic wait facts and real /proc absence.
"""
import copy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import reach_diagnostic as diagnostic


FREEZE = "a" * 40
ABSENT_PID = 2147483647


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


class DiagnosticPlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mr3-diagnostic-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "plan.json"
        self.source = self.root / "execution.py"
        self.source.write_bytes(b"# explicit synthetic frozen source\n")
        self.library = self.root / "native.so"
        self.library.write_bytes(b"explicit synthetic ELF binding")
        basis = self.root / "accounting.json"
        write(basis, {"remaining_seconds": str(diagnostic.OPENING_LEFT)})
        run = self.root / "native" / "uniform_two_episodes"
        self.plan = {
            "schema": diagnostic.SCHEMA, "safety_contract": diagnostic.CONTRACT,
            "qualification": False, "training_eligible": False,
            "optimizer_steps": 0, "gpu_calls": 0, "robots_per_environment": 3,
            "expected_episodes": 2, "steps_per_episode": 32,
            "schedule": ["open:101", "open:101"], "diagnostic_uniform_seed": 41,
            "run_directory": str(run), "output_directory": str(self.root / "output"),
            "native_argv": ["/home/zhuyulab/miniconda3/envs/ns3gym/bin/python", "-m",
                "mr3_learning.benchmark", "--workers", "1", "--schedule", "open:101,open:101",
                "--steps", "32", "--run-id", run.name, "--output-root", str(run.parent),
                "--safety-contract", diagnostic.CONTRACT, "--diagnostic-uniform-seed", "41",
                "--base-domain", "224", "--base-port", "14901", "--work-wall-seconds", "3200",
                "--close-reserve-seconds", "180"],
            "source_bindings": {"execution.py": hashlib.sha256(self.source.read_bytes()).hexdigest()},
            "library_bindings": {str(self.library): diagnostic.sha(self.library)},
            "accounting_basis": str(basis),
            "budget": {"ceiling_seconds": "52000",
                "opening_used_seconds": str(diagnostic.OPENING_USED),
                "opening_remaining_seconds": str(diagnostic.OPENING_LEFT),
                "total_reservation_seconds": str(diagnostic.CAP),
                "native_work_seconds": "3200", "native_close_reserve_seconds": "180",
                "read_only_consumer_seconds_each": "900", "external_tail_reserve_seconds": "300",
                "automatic_retry": False, "pilot_and_final_only_changed": False},
        }

    def load(self, plan=None, freeze=FREEZE):
        write(self.path, self.plan if plan is None else plan)
        with patch.object(diagnostic, "ROOT", self.root), \
                patch.object(diagnostic.preparation, "source_inventory", return_value={"execution.py"}), \
                patch.object(diagnostic.subprocess, "check_output", return_value=self.source.read_bytes()):
            return diagnostic.load_plan(self.path, freeze)

    def test_exact_two_episode_engineering_scope_is_admitted_without_work(self):
        value = self.load()
        self.assertFalse(value["qualification"])
        self.assertFalse(value["training_eligible"])
        self.assertEqual(value["optimizer_steps"], 0)
        self.assertLessEqual(Decimal(value["budget"]["total_reservation_seconds"]), diagnostic.OPENING_LEFT)

    def test_ppo_training_credit_and_workload_changes_are_rejected(self):
        for fault in ("ppo", "training", "qualification", "gpu", "updates", "episodes", "steps", "seed", "workers"):
            value = copy.deepcopy(self.plan)
            if fault == "ppo": value["native_argv"][2] = "mr3_learning.ppo"
            elif fault == "training": value["training_eligible"] = True
            elif fault == "qualification": value["qualification"] = True
            elif fault == "gpu": value["gpu_calls"] = 1
            elif fault == "updates": value["optimizer_steps"] = 1
            elif fault == "episodes": value["expected_episodes"] = 1
            elif fault == "steps": value["steps_per_episode"] = 16
            elif fault == "seed": value["diagnostic_uniform_seed"] = 42
            else: value["native_argv"][value["native_argv"].index("--workers") + 1] = "2"
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.load(value)

    def test_budget_restore_output_alias_and_source_change_are_rejected(self):
        for fault in ("ceiling", "used", "left", "reservation", "output", "source", "library"):
            value = copy.deepcopy(self.plan)
            if fault == "ceiling": value["budget"]["ceiling_seconds"] = "60000"
            elif fault == "used": value["budget"]["opening_used_seconds"] = "0"
            elif fault == "left": value["budget"]["opening_remaining_seconds"] = "52000"
            elif fault == "reservation": value["budget"]["total_reservation_seconds"] = "18000"
            elif fault == "output": value["run_directory"] = str(self.root / "foreign")
            elif fault == "source": value["source_bindings"]["execution.py"] = "0" * 64
            else: value["library_bindings"][str(self.library)] = "0" * 64
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.load(value)

    def test_extra_probe_flag_or_nonexact_freeze_is_rejected_before_native(self):
        value = copy.deepcopy(self.plan)
        value["native_argv"] += ["--fault-probe"]
        with self.assertRaisesRegex(ValueError, "flags"):
            self.load(value)
        for freeze in ("main", "a" * 39, "-h", None):
            with self.subTest(freeze=freeze), self.assertRaises(ValueError):
                self.load(freeze=freeze)


class DiagnosticExternalClosureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mr3-diagnostic-closure-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plan_path = self.root / "plan.json"
        self.outer_path = self.root / "outer.json"
        self.summary_path = self.root / "output" / "summary.json"
        self.plan = {"schema": diagnostic.SCHEMA, "safety_contract": diagnostic.CONTRACT,
            "qualification": False, "training_eligible": False,
            "native_argv": ["/home/zhuyulab/miniconda3/envs/ns3gym/bin/python"],
            "output_directory": str(self.root / "output"), "run_directory": str(self.root / "native")}
        write(self.plan_path, self.plan)
        self.saved = {"pid": ABSENT_PID, "start_ticks": 123, "parent": 1, "state": "S"}
        self.summary = {"schema": "mr3-reach-feasibility-diagnostic-execution-v1",
            "freeze": FREEZE, "plan_sha256": diagnostic.sha(self.plan_path),
            "qualification": False, "training_eligible": False, "passed": True,
            "all_submitted_children_waited": True, "coordinator_identity": self.saved}
        self.outer = {"schema": "mr3-reach-outer-actual-wait-v1", "scope": "engineering",
            "safety_contract": diagnostic.CONTRACT, "actual_waited": True, "source_unchanged": True,
            "actual_returncode": 0, "passed": True, "child_identity": self.saved,
            "actual_argv": ["/home/zhuyulab/miniconda3/envs/ns3gym/bin/python", "-m",
                "mr3_learning.reach_diagnostic", "execute", "--plan", str(self.plan_path), "--freeze", FREEZE],
            "cwd": str(diagnostic.W), "started_monotonic_ns": 1000000000,
            "ended_monotonic_ns": 2234567891, "actual_child_wait_seconds": "1.234567891"}

    def final(self, *, outer=None, summary=None):
        write(self.outer_path, self.outer if outer is None else outer)
        write(self.summary_path, self.summary if summary is None else summary)
        target = self.root / "final.json"
        if target.exists(): target.unlink()
        return diagnostic.final(self.plan_path, self.outer_path, target)

    def test_absent_saved_pid_closes_and_exact_outer_nanoseconds_are_charged(self):
        value = self.final()
        self.assertTrue(value["passed"])
        self.assertEqual(value["outer_actual_engineering_seconds"], "1.234567891")
        self.assertEqual(value["saved_identity_count"], 1)
        self.assertFalse(value["qualification"])

    def test_saved_identity_still_present_cannot_be_called_gone(self):
        fields = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()
        live = {"pid": os.getpid(), "start_ticks": int(fields[19]), "state": "R"}
        self.summary["coordinator_identity"] = live
        self.outer["child_identity"] = live
        value = self.final()
        self.assertFalse(value["passed"])
        self.assertEqual(len(value["present"]), 1)

    def test_same_saved_zombie_and_unreadable_proc_both_prevent_absence_pass(self):
        with patch.object(diagnostic, "strict_identity", return_value=dict(self.saved, state="Z")):
            value = self.final()
        self.assertFalse(value["absence_passed"])
        self.assertEqual(value["present"][0]["state"], "Z")
        with patch.object(diagnostic, "strict_identity", side_effect=PermissionError("explicit unreadable fixture")):
            value = self.final()
        self.assertFalse(value["absence_passed"])
        self.assertEqual(len(value["unreadable"]), 1)

    def test_wrong_outer_or_unwaited_summary_is_rejected(self):
        for fault in ("command", "cwd", "plan", "coordinator", "unwaited"):
            outer, summary = copy.deepcopy(self.outer), copy.deepcopy(self.summary)
            if fault == "command": outer["actual_argv"][2] = "mr3_learning.reach_preparation"
            elif fault == "cwd": outer["cwd"] = "/tmp/foreign"
            elif fault == "plan": summary["plan_sha256"] = "0" * 64
            elif fault == "coordinator": outer["child_identity"]["start_ticks"] += 1
            else: summary["all_submitted_children_waited"] = False
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.final(outer=outer, summary=summary)

    def test_incorrect_or_negative_wait_duration_cannot_reduce_fee(self):
        for started, ended, declared in ((1000000000, 2234567891, "1.234567892"),
                                          (2234567891, 1000000000, "-1.234567891"),
                                          (1000000000, 1000000000, "0")):
            outer = copy.deepcopy(self.outer)
            outer.update(started_monotonic_ns=started, ended_monotonic_ns=ended,
                         actual_child_wait_seconds=declared)
            with self.subTest(started=started, ended=ended), self.assertRaises(ValueError):
                self.final(outer=outer)

    def test_failed_native_does_not_become_diagnostic_pass_when_processes_are_gone(self):
        summary = copy.deepcopy(self.summary)
        summary["passed"] = False
        outer = copy.deepcopy(self.outer)
        outer.update(actual_returncode=1, passed=False)
        value = self.final(outer=outer, summary=summary)
        self.assertFalse(value["diagnostic_passed"])
        self.assertTrue(value["absence_passed"])


if __name__ == "__main__":
    unittest.main()
