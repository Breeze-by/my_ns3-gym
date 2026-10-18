"""CPU child-process and plan tests; no ROS/Gazebo/GPU or native admissions."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import time
import unittest

from mr3_learning import preparation as prep
from mr3_learning import native_custody as custody


FREEZE = "a" * 40


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.events = []

    def plan(self, **kwargs):
        return prep.build_plan(output_directory=self.root / "execution", run_root=self.root / "native",
                               custody_binding=self.root / "binding.json", binary_proof=self.root / "binary.json",
                               preflight=self.root / "preflight.json", engineering_remaining_seconds="17164.4756821603982", **kwargs)

    def runner(self):
        directory = self.root / "receipts"
        directory.mkdir()
        return prep.Runner(directory, self.root, FREEZE, "b" * 64,
                           lambda **value: self.events.append(value))

    def job(self, name, *, code=0, passed=True, delay=0., depends=(), required=True):
        output = self.root / (name + "_output.json")
        script = ("import json,sys,time;from pathlib import Path;"
                  "time.sleep(float(sys.argv[2]));"
                  "Path(sys.argv[1]).write_text(json.dumps({'passed':sys.argv[3]=='true'})+'\\n');"
                  "sys.exit(int(sys.argv[4]))")
        return {"id": name, "output": str(output), "argv": [sys.executable, "-c", script,
                str(output), str(delay), str(passed).lower(), str(code)],
                "depends_on": list(depends), "required": required}

    def test_builder_preserves_original38_roles_workloads_and_draft_admission(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, "sealed and ready"):
            prep.validate_plan(plan)
        plan["readiness"] = {"ready": True}
        prep.validate_plan(plan)
        self.assertEqual([len(prep.roles(stage)) for stage in plan["stages"]], [11, 8, 11, 8])
        self.assertEqual([stage["expected_episodes"] for stage in plan["stages"]], [1, 2, 8, 1])
        self.assertGreater(len(plan["source_bindings"]), 200)
        self.assertIn(str((prep.WORKSPACE / prep.WIRELESS_RELATIVE / "mr3_learning/preparation.py").relative_to(prep.WORKSPACE)), plan["source_bindings"])
        self.assertTrue(plan["final_external_coordinator_absence_required"])

    def test_missing_role_math_replacement_or_cycle_is_rejected_before_native(self):
        for fault in ("role", "math", "cycle", "result_key", "borrow_flag"):
            with self.subTest(fault=fault):
                plan = self.plan()
                plan["readiness"] = {"ready": True}
                jobs = plan["stages"][0]["audits"]
                if fault == "role":
                    jobs[:] = [job for job in jobs if job.get("role") != "cadence"]
                elif fault == "math":
                    next(job for job in jobs if job.get("role") == "physics")["argv"][1] = "/tmp/substitute.py"
                elif fault == "cycle":
                    jobs[0]["depends_on"] = [jobs[0]["id"]]
                elif fault == "result_key":
                    jobs[0]["result_pass_key"] = "completed_requested_collection"
                else:
                    plan["budget"]["borrow_unused_prior_stage_reservations"] = "true"
                with self.assertRaises(ValueError):
                    prep.validate_plan(plan)

    def test_reset_retains_optional_raw_failure_and_eight_leaf_pooled_contract(self):
        plan = self.plan()
        stage = plan["stages"][2]
        jobs = {job["id"]: job for job in stage["audits"]}
        self.assertFalse(jobs["physical_per_episode"]["required"])
        self.assertEqual(jobs["physics"]["depends_on"], ["physical_per_episode"])
        self.assertEqual(len(jobs["input"]["members"]), 8)
        self.assertEqual(len(jobs["fifo_manifest"]["members"]), 8)
        self.assertEqual(jobs["closure"]["depends_on"], ["fifo_manifest"])

    def test_information_implementation_requires_explicit_flag_and_changes_only_four_roles(self):
        original = self.plan()
        new = self.plan(information_implementation="cycle_three_keys_v1")
        self.assertEqual(original["information_implementation"], "original")
        changed = []
        for old_stage, new_stage in zip(original["stages"], new["stages"]):
            self.assertEqual(old_stage["native"], new_stage["native"])
            for old_job, new_job in zip(old_stage["audits"], new_stage["audits"]):
                if old_job != new_job:
                    changed.append((new_stage["stage"], new_job["role"]))
                    self.assertEqual(new_job["argv"][:3], ["/usr/bin/python3", "-m", "mr3_learning.audit_information"])
                    self.assertEqual({k: v for k, v in old_job.items() if k != "argv"},
                                     {k: v for k, v in new_job.items() if k != "argv"})
        self.assertEqual(changed, [(stage, "information") for stage in prep.STAGES])
        new["readiness"] = {"ready": True}
        prep.validate_plan(new)
        new["information_implementation"] = "original"
        with self.assertRaisesRegex(ValueError, "original mathematical consumer replaced"):
            prep.validate_plan(new)

    def test_new_information_flag_cannot_replace_other_roles_or_omit_source_identity(self):
        for fault in ("source", "peer"):
            plan = self.plan(information_implementation="cycle_three_keys_v1")
            plan["readiness"] = {"ready": True}
            if fault == "source":
                del plan["source_bindings"][str(prep.WIRELESS_RELATIVE / "mr3_learning/audit_information.py")]
            else:
                peer = next(job for job in plan["stages"][0]["audits"] if job.get("role") == "peer")
                peer["argv"] = ["/usr/bin/python3", "-m", "mr3_learning.audit_information", *peer["argv"][2:]]
            with self.assertRaises(ValueError):
                prep.validate_plan(plan)

    def test_first_required_failure_drains_submitted_child_and_skips_dependant(self):
        runner = self.runner()
        jobs = [self.job("failure", code=7, passed=False), self.job("already_submitted", delay=.08),
                self.job("later", depends=("failure",))]
        completed, skipped = prep.run_audits(jobs, runner, time.monotonic_ns() + 5_000_000_000)
        self.assertEqual(completed["failure"]["returncode"], 7)
        self.assertEqual(completed["already_submitted"]["returncode"], 0)
        self.assertTrue(completed["already_submitted"]["passed"])
        self.assertEqual([row["id"] for row in skipped], ["later"])
        self.assertFalse(Path(jobs[-1]["output"]).exists())
        self.assertEqual(sum(row["event"] == "child_waited" for row in self.events), 2)

    def test_optional_real_nonzero_rc_does_not_suppress_dependent_pooled_review(self):
        runner = self.runner()
        raw = self.job("raw", code=3, passed=False, required=False)
        pooled = self.job("pooled", depends=("raw",))
        completed, skipped = prep.run_audits([raw, pooled], runner, time.monotonic_ns() + 5_000_000_000)
        self.assertEqual(completed["raw"]["returncode"], 3)
        self.assertFalse(completed["raw"]["passed"])
        self.assertTrue(completed["pooled"]["passed"])
        self.assertFalse(skipped)
        self.assertEqual(json.loads(Path(raw["output"]).read_text()), {"passed": False})

    def test_exhausted_budget_submits_no_child(self):
        runner = self.runner()
        completed, skipped = prep.run_audits([self.job("blocked")], runner, time.monotonic_ns() - 1)
        self.assertFalse(completed)
        self.assertEqual(skipped[0]["reason"], "stage_wall_allocation_exhausted")
        self.assertFalse(any(row["event"] == "child_spawned" for row in self.events))

    def test_aggregate_and_fifo_manifest_preserve_actual_members_without_inventing_rc(self):
        runner = self.runner()
        completed, _ = prep.run_audits([self.job("first"), self.job("second")], runner,
                                       time.monotonic_ns() + 5_000_000_000)
        aggregate = {"id": "input", "kind": "aggregate", "members": ["first", "second"],
                     "output": str(self.root / "aggregate.json")}
        value = runner.aggregate(aggregate, completed)
        self.assertTrue(value["passed"])
        self.assertIsNone(value["returncode"])
        self.assertEqual([row["returncode"] for row in value["members"]], [0, 0])
        manifest = {"id": "fifo", "kind": "fifo_manifest", "members": ["first", "second"],
                    "output": str(self.root / "fifo.json"), "leaves": [
                        {"id": name, "episode_directory": str(self.root / name)} for name in ("first", "second")]}
        runner.aggregate(manifest, completed)
        self.assertEqual(len(json.loads(Path(manifest["output"]).read_text())), 2)
        Path(completed["first"]["output"]).write_text('{}\n')
        aggregate["output"] = str(self.root / "changed.json")
        with self.assertRaisesRegex(ValueError, "changed/missing"):
            runner.aggregate(aggregate, completed)

    def test_command_output_cannot_override_actual_nonzero_wait_result_or_overwrite(self):
        runner = self.runner()
        job = self.job("nonzero", code=9, passed=True)
        result = runner.command(job)
        self.assertEqual(result["returncode"], 9)
        self.assertFalse(result["passed"])
        self.assertEqual(result["launcher_identity_scope"], "persistent_coordinator_not_native_owned")
        self.assertEqual(result["launcher_identity"], result["coordinator_identity"])
        self.assertEqual(result["coordinator_actual_argv"], [part.decode() for part in
            Path("/proc/self/cmdline").read_bytes().split(b"\0") if part])
        before = Path(job["output"]).read_bytes()
        with self.assertRaises(FileExistsError):
            runner.command(job)
        self.assertEqual(before, Path(job["output"]).read_bytes())

    def test_explicit_trace_capture_key_never_overrides_actual_rc_or_claims_science(self):
        runner = self.runner()
        for code in (0, 6):
            job = self.job("capture_" + str(code), code=code)
            job["argv"] = [sys.executable, "-c", "import json,sys;from pathlib import Path;"
                "Path(sys.argv[1]).write_text(json.dumps({'passed':False,'completed_requested_collection':True})+'\\n');"
                "sys.exit(int(sys.argv[2]))", job["output"], str(code)]
            job.update(result_pass_key="completed_requested_collection", result_scope="capture only; no scientific PASS")
            result = runner.command(job)
            self.assertEqual(result["passed"], code == 0)
            self.assertEqual(result["returncode"], code)
            self.assertEqual(result["result_scope"], "capture only; no scientific PASS")

    def test_actual_cpu_ready_wait_stop_and_fifo_match_production_boundary_readers(self):
        runner = self.runner()
        runner.cwd = prep.WORKSPACE / prep.WIRELESS_RELATIVE
        completed, leaves = {}, []
        for index in range(2):
            name = "boundary_" + str(index)
            output, ready = self.root / (name + ".json"), self.root / (name + "_ready.json")
            raw_path = self.root / (name + "_raw.txt")
            raw_path.write_bytes(("actual CPU boundary input " + str(index)).encode())
            binding_sha = prep.sha(raw_path)
            script = ("import json,sys;from pathlib import Path;"
                "from mr3_learning.native_custody import write_ready_receipt;"
                "write_ready_receipt(sys.argv[1],sys.argv[3],sys.argv[4]);"
                "Path(sys.argv[2]).write_text(json.dumps({'passed':True,'freeze':sys.argv[3],"
                "'epoch':sys.argv[5],'errors':[],'bindings':{sys.argv[6]:"
                "{'sha256':sys.argv[4],'bytes':Path(sys.argv[6]).stat().st_size}}})+'\\n')")
            job = {"id": name, "output": str(output), "argv": [sys.executable, "-B", "-c", script,
                str(ready), str(output), FREEZE, binding_sha, "cpu_boundary_epoch_" + str(index), str(raw_path)]}
            completed[name] = result = runner.command(job)
            self.assertTrue(result["passed"])
            self.assertEqual(result["returncode"], 0)
            read = custody.Reader()
            actual_ready = custody.read_ready_receipt(read, ready, FREEZE, binding_sha)
            self.assertEqual(actual_ready["watcher_identity"]["pid"], result["process_identity"]["pid"])
            self.assertEqual(actual_ready["watcher_identity"]["start_ticks"], result["process_identity"]["start_ticks"])
            stop_path = self.root / (name + "_stop.json")
            prep.dump(stop_path, {"schema": "mr3-native-custody-stop-v1", "freeze": FREEZE,
                "launch_receipt": {"path": result["receipt"], "sha256": prep.sha(result["receipt"])}})
            boundary = custody.read_wait_boundary(read, stop_path, result["receipt"], FREEZE)
            self.assertEqual(boundary["launch"]["returncode"], 0)
            self.assertEqual(boundary["launch"]["launcher_identity_scope"], "persistent_coordinator_not_native_owned")
            self.assertEqual(boundary["launch"]["coordinator_identity"], result["launcher_identity"])
            read.finish()
            leaves.append({"id": name, "episode_directory": str(self.root / ("cpu_episode_" + str(index)))})
        manifest = {"id": "actual_fifo", "kind": "fifo_manifest", "members": list(completed),
            "output": str(self.root / "actual_fifo_manifest.json"), "leaves": leaves}
        runner.aggregate(manifest, completed)
        read = custody.Reader()
        receipts = custody.read_fifo_receipts(read, manifest["output"], FREEZE, 2)
        self.assertEqual(set(receipts), {entry["episode_directory"] for entry in leaves})
        read.finish()
        raw_path.write_text("changed after actual CPU child returned")
        with self.assertRaisesRegex(ValueError, "raw binding changed"):
            custody.read_fifo_receipts(custody.Reader(), manifest["output"], FREEZE, 2)


class BorrowedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"budget": {"matrix_wall_seconds": "14900",
            "engineering_remaining_seconds": "16047.2815487073982",
            "borrow_unused_prior_stage_reservations": True}, "stages": [
                {"stage": name, "wall_seconds": str(cap), "native": {"argv": [
                    "python", "-m", "mr3_learning.benchmark", "--work-wall-seconds", str(native),
                    "--close-reserve-seconds", "120"]}}
                for name, cap, native in zip(prep.STAGES, (1500, 1200, 4500, 7700), (1250, 850, 3900, 6600))]}

    def budget(self, index, seconds):
        return prep.borrowed_stage_budget(self.plan, index, int(Decimal(seconds) * 10**9))

    def test_initial_source_admission_overhead_does_not_consume_later_base_reservations(self):
        value = self.budget(0, "10")
        self.assertEqual(value["unused_prior_reservations_ns"], 0)
        self.assertEqual(value["stage_remaining_ns"], 1490 * 10**9)
        self.assertEqual(value["native_allocation_ns"], 1240 * 10**9)
        self.assertEqual(value["future_base_reservations_ns"], 13400 * 10**9)
        self.assertEqual(10 * 10**9 + value["stage_remaining_ns"] + value["future_base_reservations_ns"], 14900 * 10**9)

    def test_only_actual_unused_prior_wall_can_be_borrowed(self):
        value = self.budget(1, "1000")
        self.assertEqual(value["unused_prior_reservations_ns"], 500 * 10**9)
        self.assertEqual(value["stage_remaining_ns"], 1700 * 10**9)
        self.assertEqual(value["native_allocation_ns"], 1350 * 10**9)
        self.assertEqual(value["close_reserve_ns"], 120 * 10**9)

    def test_source_and_ready_rechecks_never_move_cumulative_deadline(self):
        before, after = self.budget(1, "1000"), self.budget(1, "1025")
        self.assertEqual(before["stage_cumulative_deadline_from_matrix_entry_ns"], 2700 * 10**9)
        self.assertEqual(before["stage_cumulative_deadline_from_matrix_entry_ns"], after["stage_cumulative_deadline_from_matrix_entry_ns"])
        self.assertEqual(after["native_allocation_ns"], before["native_allocation_ns"] - 25 * 10**9)

    def test_last_stage_uses_remaining_matrix_without_raising_total_quota(self):
        value = self.budget(3, "6500")
        self.assertEqual(value["stage_remaining_ns"], 8400 * 10**9)
        self.assertEqual(value["native_allocation_ns"], 7300 * 10**9)
        self.assertEqual(value["future_base_reservations_ns"], 0)
        self.assertEqual(6500 * 10**9 + value["stage_remaining_ns"], 14900 * 10**9)
        # The same helper also supports the old14000 declaration without changing it.
        self.plan["budget"]["matrix_wall_seconds"] = "14000"
        self.plan["stages"][3]["wall_seconds"] = "6800"
        self.plan["stages"][3]["native"]["argv"][4] = "5700"
        legacy = self.budget(3, "6500")
        self.assertEqual(legacy["stage_remaining_ns"], 7500 * 10**9)
        self.assertEqual(legacy["native_allocation_ns"], 6400 * 10**9)

    def test_prior_overhead_deficit_is_debited_instead_of_leaking_past_ceiling(self):
        value = self.budget(3, "7210")
        self.assertEqual(value["unused_prior_reservations_ns"], 0)
        self.assertEqual(value["stage_remaining_ns"], 7690 * 10**9)
        self.assertEqual(value["native_allocation_ns"], 6590 * 10**9)
        self.assertEqual(value["stage_cumulative_deadline_from_matrix_entry_ns"], 14900 * 10**9)

    def test_unknown_or_exhausted_wall_never_creates_admission_or_returncode(self):
        for seconds in ("14800", "14900", "15000"):
            value = self.budget(3, seconds)
            self.assertFalse(value["native_admission_possible"])
            self.assertEqual(value["native_allocation_ns"], 0)
            self.assertLessEqual(value["stage_cumulative_deadline_from_matrix_entry_ns"], 14900 * 10**9)
            self.assertNotIn("returncode", value)
            with self.assertRaises(ValueError):
                prep.budgeted_native_job(self.plan["stages"][3]["native"], value)
        for elapsed in (-1, None, 1.2, True):
            with self.assertRaises(ValueError):
                prep.borrowed_stage_budget(self.plan, 0, elapsed)

    def test_round_down_and_copy_leave_every_other_declared_cli_argument_intact(self):
        before = deepcopy(self.plan)
        value = self.budget(1, "1000.000000123")
        self.assertEqual(value["native_allocation_ns"] % 1_000_000, 0)
        self.assertLessEqual(value["native_allocation_ns"] + value["base_consumer_reserve_ns"], value["stage_remaining_ns"])
        job = prep.budgeted_native_job(self.plan["stages"][1]["native"], value)
        expected = list(self.plan["stages"][1]["native"]["argv"])
        expected[expected.index("--work-wall-seconds") + 1] = value["native_allocation_seconds"]
        self.assertEqual(job["argv"], expected)
        self.assertEqual(self.plan, before)

    def test_engineering_remaining_is_a_separate_upper_bound(self):
        self.plan["budget"]["engineering_remaining_seconds"] = "1300"
        value = self.budget(1, "1000")
        self.assertEqual(value["stage_remaining_ns"], 300 * 10**9)
        self.assertFalse(value["native_admission_possible"])

    def test_derived_argv_and_budget_reach_real_cpu_wait_receipt_default_unchanged(self):
        value = self.budget(1, "1000")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            runner = prep.Runner(directory, directory, "a" * 40, "b" * 64, lambda **event: None)
            for with_budget in (False, True):
                name = "cpu_" + str(with_budget)
                output = directory / (name + "_output.json")
                declared = {"id": name, "output": str(output), "argv": [sys.executable, "-B", "-c",
                    "from pathlib import Path;import sys,json;Path(sys.argv[1]).write_text(json.dumps({'passed':True,'actual_seen_work':sys.argv[sys.argv.index('--work-wall-seconds')+1]})+'\\n')",
                    str(output), "--work-wall-seconds", "850", "--close-reserve-seconds", "120"]}
                job = prep.budgeted_native_job(declared, value) if with_budget else declared
                if with_budget:
                    job["receipt"], job["console"] = str(directory / "budget_wait.json"), str(directory / "budget_wait.log")
                result = runner.command(job)
                self.assertEqual(result["returncode"], 0)
                self.assertTrue(result["passed"])
                self.assertEqual("budget_allocation" in result, with_budget)
                if with_budget:
                    self.assertEqual(result["budget_allocation"], value)
                self.assertEqual(json.loads(output.read_text())["actual_seen_work"], value["native_allocation_seconds"] if with_budget else "850")
                self.assertEqual(result["argv"], job["argv"])


if __name__ == "__main__":
    unittest.main()
