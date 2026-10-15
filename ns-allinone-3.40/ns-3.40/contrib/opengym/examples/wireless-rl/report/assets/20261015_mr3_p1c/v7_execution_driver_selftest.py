"""Temporary synthetic files and injected runners only; never launch a child."""

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest import mock

import v7_execution_driver as D


ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".git").exists())
PLAN = D.load(ROOT / D.FILES["plan"])
FREEZE = "f" * 40


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as output:
        json.dump(value, output)


class Harness:
    def __init__(self, root, failure=None):
        self.root, self.failure, self.calls = root, failure, []
        self.assets = root / D.ASSETS
        write(root / D.FILES["plan"], PLAN)
        self.binding = {"schema": "mr3-p1c-v7-execution-binding-v1", "freeze": FREEZE,
                        "files": {name: {"path": path, "sha256": "1" * 64}
                                  for name, path in D.FILES.items()}}
        self.binding["files"]["command_time_auditor"]["sha256"] = "2" * 64
        self.binding["files"]["profile"]["sha256"] = "3" * 64
        self.binding_path = self.assets / "binding.json"
        write(self.binding_path, self.binding)
        self.driver = D.Driver(root, FREEZE, self.binding_path,
                               self.assets / "journal.jsonl", self.runner)

    def proof(self):
        return {"freeze": FREEZE, "wrapper_sha256": "1" * 64,
                "command_time_gate": {"sha256": "2" * 64}}

    def runner(self, argv, cwd, stdout, stderr):
        rendered = " ".join(argv)
        name = next((row["name"] for row in self.driver.stages
                     if row["declaration"]["run_id"] in rendered), "matrix")
        if "--matrix" in argv:
            role, name = "matrix", "matrix"
        elif argv[2] == "/usr/bin/bash":
            role = "native"
        elif "--expected-fault" in argv:
            role = "prefix"
        elif "audit_mr3_env_contact_phase_v3.py" in rendered:
            role = "primary"
        elif "fault_subset.py" in rendered:
            role = "subset"
        else:
            role = "scalar"
        self.calls.append((name, role, list(argv)))
        with stdout.open("x") as out, stderr.open("x"):
            if role == "native":
                stage = next(row for row in self.driver.stages if row["name"] == name)
                directory, declaration = stage["directory"], stage["declaration"]
                value = {"freeze": FREEZE, "passed": True, "error": None,
                         "server_returncode": 0, "stop_cli_returncode": 0}
                metadata = {"freeze": FREEZE, "transport_environment": {
                    "profile_sha256": "3" * 64, "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp"}}
                if name == "clock":
                    write(directory / "summary.json", value)
                    write(directory / "metadata.json", metadata)
                else:
                    cells = (x.split(":") for x in declaration["schedule"].split(","))
                    value.update(workers=declaration["workers"],
                                 steps_per_episode=declaration["steps"],
                                 schedule=[[scene, int(seed)] for scene, seed in cells])
                    write(directory / "benchmark_summary.json", value)
                    write(directory / "worker0/episode001_open_101/metadata.json", metadata)
                out.write("synthetic native output\n")
            elif role in ("primary", "prefix", "matrix"):
                value = {"passed": self.failure != (name, role), "errors": [],
                         "offline_contact_phase_audit": self.proof()}
                if role == "prefix":
                    value.update(expected_infrastructure_fault=True, complete_episode_credit=False,
                                 transitions={"complete": False, "transition_count": 4})
                if role == "matrix":
                    value["benchmarks"] = [{"directory": str(row["directory"])}
                                           for row in self.driver.stages if row["name"] in D.MATRIX]
                write(Path(argv[argv.index("--output") + 1]), value)
                out.write("{}\n")
            elif role == "scalar":
                json.dump({"freeze": FREEZE, "passed_scalar_checks":
                           self.failure != (name, role)}, out)
            else:
                prefix = Path(argv[argv.index("--main-prefix-audit") + 1])
                assert D.load(prefix)["complete_episode_credit"] is False
                value = {"freeze": FREEZE, "completed_subset_scalar_checks_passed":
                         self.failure != (name, role), "completed_subset_transitions": 24,
                         "whole_fault_benchmark_reward_audit_performed": False}
                write(Path(argv[argv.index("--output") + 1]), value)
                out.write("{}\n")
        return {"returncode": 1 if self.failure == (name, "returncode") else 0, "pid": None}

    def run(self, guard=None):
        with mock.patch.object(D, "verify_binding", side_effect=guard,
                               return_value=self.binding), redirect_stdout(io.StringIO()):
            return self.driver.run()


class ExecutionTests(unittest.TestCase):
    def test_native_argument_lists_use_exact_declared_workloads_and_environments(self):
        stages = D.build_stages(ROOT, PLAN, FREEZE)
        for stage in stages:
            row, script = stage["declaration"], stage["native"][-1]
            argv = shlex.split(next(line for line in script.splitlines()
                                    if line.startswith("exec ")))[1:]
            self.assertEqual(argv[argv.index("--run-id") + 1], row["run_id"])
            if stage["name"] == "clock":
                self.assertEqual(argv[0], "/usr/bin/python3")
                self.assertIn("source /opt/ros/humble/setup.bash", script)
                fields = {"--ros-domain-id": "ros_domain", "--gazebo-port": "gazebo_port"}
            else:
                self.assertEqual(argv[0], "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python")
                self.assertIn("conda activate ns3gym", script)
                fields = {"--workers": "workers", "--steps": "steps", "--schedule": "schedule",
                          "--base-domain": "base_domain", "--base-port": "base_port"}
            for flag, key in fields.items():
                self.assertEqual(argv[argv.index(flag) + 1], str(row[key]))
            self.assertNotIn("gpu_probe", script)

    def test_all_eight_native_stages_and_twenty_four_commands_match_plan_and_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp))
            self.assertEqual(h.run(), 0)
            self.assertEqual(len(h.calls), 24)
            self.assertEqual([name for name, role, _ in h.calls if role == "native"],
                             ["clock", "pilot", "terminal", "workers1", "workers2",
                              "workers4", "fault", "deadline"])
            self.assertEqual([role for name, role, _ in h.calls if name == "fault"],
                             ["native", "prefix", "primary", "subset"])
            self.assertEqual(h.calls[-1][:2], ("matrix", "matrix"))
            self.assertEqual(len(D.load(h.driver.matrix_output)["benchmarks"]), 6)
            journal = [json.loads(line) for line in h.driver.journal_path.read_text().splitlines()]
            self.assertEqual(journal[-1]["kind"], "all_eight_stages_and_declared_audits_complete")
            log = (h.root / D.WIRELESS / "log.md").read_text()
            self.assertEqual(log.count("Exact command:"), 24)
            self.assertEqual(log.count("actual result:"), 24)

    def test_scalar_false_with_exit_zero_stops_before_next_native(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp), ("pilot", "scalar"))
            self.assertEqual(h.run(), 1)
            self.assertEqual(h.calls[-1][:2], ("pilot", "scalar"))
            self.assertFalse(any(name == "terminal" for name, _, _ in h.calls))
            self.assertFalse(D.load(h.driver.stages[1]["scalar_output"])["passed_scalar_checks"])

    def test_primary_false_with_exit_zero_stops_without_scalar_or_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp), ("pilot", "primary"))
            self.assertEqual(h.run(), 1)
            self.assertEqual(h.calls[-1][:2], ("pilot", "primary"))
            self.assertEqual(len([x for x in h.calls if x[:2] == ("pilot", "native")]), 1)

    def test_fault_subset_false_does_not_start_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp), ("fault", "subset"))
            self.assertEqual(h.run(), 1)
            self.assertEqual(h.calls[-1][:2], ("fault", "subset"))
            self.assertFalse(any(name == "deadline" for name, _, _ in h.calls))

    def test_existing_journal_refuses_a_second_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp))
            self.assertEqual(h.run(), 0)
            original = h.driver.journal_path.read_bytes()
            with self.assertRaises(FileExistsError):
                h.run()
            self.assertEqual(h.driver.journal_path.read_bytes(), original)
            self.assertEqual(len(h.calls), 24)

    def test_nonzero_native_does_not_gain_credit_from_true_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp), ("clock", "returncode"))
            self.assertEqual(h.run(), 1)
            self.assertEqual(len(h.calls), 1)

    def test_existing_artifact_is_preserved_and_blocks_all_native(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp))
            old = h.driver.stages[1]["scalar_output"]
            write(old, {"old": True})
            self.assertEqual(h.run(), 1)
            self.assertEqual(D.load(old), {"old": True})
            self.assertEqual(h.calls, [])

    def test_guard_change_between_commands_stops_before_scalar(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(Path(temp))
            count = 0

            def guard(*args):
                nonlocal count
                count += 1
                if count == 5:
                    raise ValueError("source pin changed")
                return h.binding

            self.assertEqual(h.run(guard), 1)
            self.assertEqual(h.calls[-1][:2], ("pilot", "primary"))

    def test_dry_run_has_no_runner_journal_log_or_binding_requirement(self):
        with mock.patch.object(D, "Driver", side_effect=AssertionError("must not execute")), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(D.main(["--freeze", FREEZE, "--dry-run"]), 0)
        value = json.loads(output.getvalue())
        self.assertTrue(value["dry_run"])
        self.assertFalse(value["native_executed"])
        self.assertEqual(len(value["stages"]), 8)


class BindingTests(unittest.TestCase):
    def test_matching_worktree_and_binding_cannot_hide_any_wrong_git_blob(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = copy.deepcopy(PLAN)
            for name, relative in D.FILES.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if name in ("scalar_auditor", "scalar_fault_subset"):
                    path.write_bytes((ROOT / relative).read_bytes())
                else:
                    path.write_bytes(("synthetic " + name).encode())
            base = root / D.ASSETS / "audit_mr3_env_contact_phase_v2.py"
            base.write_bytes((ROOT / D.ASSETS / base.name).read_bytes())
            plan["transport_profile"]["sha256"] = D.sha(root / D.PROFILE)
            (root / D.FILES["plan"]).write_text(json.dumps(plan))
            source = root / "source.py"
            source.write_text("unmodified source")
            extra = root / "extra.json"
            extra.write_text("{}")
            checks = {"source_sha256": {"source.py": D.sha(source)},
                      "prospective_native_plan_sha256": D.sha(root / D.FILES["plan"])}
            (root / D.FILES["implementation_checks"]).write_text(json.dumps(checks))
            binding = {"schema": "mr3-p1c-v7-execution-binding-v1", "freeze": FREEZE,
                       "files": {name: {"path": relative, "sha256": D.sha(root / relative)}
                                 for name, relative in D.FILES.items()},
                       "additional_files": [{"path": "extra.json", "sha256": D.sha(extra)}]}
            path = root / "postpush_binding.json"
            write(path, binding)
            wrong = None

            def git(argv, **kwargs):
                if argv[1] == "rev-parse":
                    return FREEZE + "\n"
                relative = argv[2].split(":", 1)[1]
                if relative == wrong:
                    return b"different committed bytes"
                return (root / relative).read_bytes()

            with mock.patch.object(D.subprocess, "check_output", side_effect=git):
                self.assertEqual(D.verify_binding(root, FREEZE, path, D.sha(path)), binding)
                for wrong in [*D.FILES.values(), "source.py", "extra.json",
                              str(base.relative_to(root))]:
                    with self.subTest(wrong_git_blob=wrong):
                        with self.assertRaisesRegex(ValueError, "Git blob SHA mismatch"):
                            D.verify_binding(root, FREEZE, path, D.sha(path))


if __name__ == "__main__":
    unittest.main()
