import copy
import gzip
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path("/home/zhuyulab/ns3-workspace")
BASE = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets"
ASSET = BASE / "20261017_mr3_p2a0_v8"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


launch = module("launch8", ASSET / "independent/mr3_p2a0_v8_launch_stage.py")
build = module("build8", ASSET / "independent/mr3_p2a0_v8_buildproof_preflight.py")


class Admission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.freeze = "a" * 40
        self.plan = {"max_total_wall_seconds": 100, "stages": []}
        for name in ("first", "second"):
            self.plan["stages"].append({
                "stage": name, "wall_ceiling_seconds": 50,
                "run_directory": str(self.base / (name + "_run")),
                "required_audit_receipts": [str(self.base / (name + "_formal.json"))]})
        self.previous = dict(freeze=self.freeze, stage="first", status="completed",
                             returncode=0, passed=True, wall_duration_sec=20)
        self.summary = dict(freeze=self.freeze, passed=True)
        self.formal = dict(freeze=self.freeze, passed=True)
        self.write_previous()
        self.patch = patch.object(launch, "TEMP", self.base)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write_previous(self):
        (self.base / "mr3_p2a0_v8_first_launch.json").write_text(json.dumps(self.previous))
        directory = self.base / "first_run"
        directory.mkdir(exist_ok=True)
        (directory / "benchmark_summary.json").write_text(json.dumps(self.summary))
        (self.base / "first_formal.json").write_text(json.dumps(self.formal))

    def admitted(self):
        return launch.launch_admission(self.plan, "second", self.freeze)

    def test_valid_reservation_and_bound_audits(self):
        stage, budget = self.admitted()
        self.assertEqual(stage["stage"], "second")
        self.assertEqual(budget["preceding_wall_seconds"], 20)
        self.assertEqual(budget["remaining_before_stage_seconds"], 80)
        self.assertEqual(len(budget["preceding_formal_receipts"]), 2)
        self.assertEqual(len(budget["preceding_formal_receipts"][0]["sha256"]), 64)

    def test_first_no_predecessor(self):
        (self.base / "mr3_p2a0_v8_first_launch.json").unlink()
        shutil.rmtree(self.base / "first_run")
        _, budget = launch.launch_admission(self.plan, "first", self.freeze)
        self.assertEqual(budget["preceding_wall_seconds"], 0)

    def test_prior_failure_rejected(self):
        for key, value in (("returncode", 1), ("passed", False), ("status", "running"),
                           ("freeze", "b" * 40), ("wall_duration_sec", float("nan")),
                           ("wall_duration_sec", -1), ("wall_duration_sec", 51)):
            with self.subTest(key=key, value=value):
                old = self.previous[key]
                self.previous[key] = value
                self.write_previous()
                with self.assertRaises(AssertionError):
                    self.admitted()
                self.previous[key] = old

    def test_summary_failure_rejected(self):
        self.summary["passed"] = False
        self.write_previous()
        with self.assertRaises(AssertionError):
            self.admitted()

    def test_missing_formal_rejected(self):
        (self.base / "first_formal.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.admitted()

    def test_formal_false_nonbool_and_freeze_rejected(self):
        for formal in ({"passed": False}, {"passed": 1}, {"passed": True, "freeze": "b" * 40}):
            with self.subTest(formal=formal):
                self.formal = formal
                self.write_previous()
                with self.assertRaises(AssertionError):
                    self.admitted()

    def test_missing_previous_rejected(self):
        (self.base / "mr3_p2a0_v8_first_launch.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.admitted()

    def test_no_retry_or_out_of_order(self):
        (self.base / "mr3_p2a0_v8_second_launch.json").write_text("{}")
        with self.assertRaises(AssertionError):
            self.admitted()
        with self.assertRaises(AssertionError):
            launch.launch_admission(self.plan, "first", self.freeze)

    def test_insufficient_remaining_rejected(self):
        self.plan["max_total_wall_seconds"] = 69
        with self.assertRaises(AssertionError):
            self.admitted()

    def test_existing_run_rejected(self):
        (self.base / "second_run").mkdir()
        with self.assertRaises(AssertionError):
            self.admitted()


class BinaryBinding(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git = {}
        self.build = {"schema": "mr3-drive-binary-build-v1"}
        macros = []
        for field, relative in build.COMPILED:
            relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/" + relative
            raw = ("original " + field).encode()
            self.put(relative, raw)
            self.build[field] = build.sha(raw)
            macros.append(self.build[field].encode())
        self.library = b"compiled:" + b"|".join(macros)
        self.build.update(library_path=str(self.root / "build.so"),
                          installed_path=str(self.root / "install.so"),
                          library_sha256=build.sha(self.library), library_bytes=len(self.library),
                          archived_library_gzip="old/binary.so.gz")
        for key in ("library_path", "installed_path"):
            Path(self.build[key]).write_bytes(self.library)
        blob = gzip.compress(self.library, mtime=0)
        self.put("old/binary.so.gz", blob)
        self.build["archived_library_encoded_sha256"] = build.sha(blob)
        self.plan = {"drive_contract": {"binary_build_receipt": {"path": "old/build.json"}}}
        self.write_build()
        self.patches = [patch.object(build, "ROOT", self.root),
                        patch.object(build, "git_bytes", side_effect=lambda freeze, path: self.git[path])]
        for value in self.patches:
            value.start()
            self.addCleanup(value.stop)

    def put(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        self.git[relative] = raw

    def write_build(self):
        raw = json.dumps(self.build).encode()
        self.put("old/build.json", raw)
        self.plan["drive_contract"]["binary_build_receipt"]["sha256"] = build.sha(raw)

    def check(self):
        return build.check_binary(self.plan, "a" * 40)

    def test_reused_old_receipt_bound_to_new_freeze(self):
        proof = self.check()
        self.assertEqual(proof["freeze"], "a" * 40)
        self.assertEqual(proof["library_sha256"], build.sha(self.library))

    def test_wrong_receipt_sha(self):
        self.plan["drive_contract"]["binary_build_receipt"]["sha256"] = "0" * 64
        with self.assertRaises(AssertionError):
            self.check()

    def test_receipt_differs_git(self):
        self.git["old/build.json"] = b"{}"
        with self.assertRaises(AssertionError):
            self.check()

    def test_current_library_mutations(self):
        for key in ("library_path", "installed_path"):
            with self.subTest(key=key):
                Path(self.build[key]).write_bytes(b"changed")
                with self.assertRaises(AssertionError):
                    self.check()
                Path(self.build[key]).write_bytes(self.library)

    def test_compiled_source_disk_or_git_mutation(self):
        field, relative = build.COMPILED[0]
        relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/" + relative
        old = self.git[relative]
        (self.root / relative).write_bytes(b"changed")
        with self.assertRaises(AssertionError):
            self.check()
        (self.root / relative).write_bytes(old)
        self.git[relative] = b"changed"
        with self.assertRaises(AssertionError):
            self.check()

    def test_bad_encoded_archive(self):
        (self.root / "old/binary.so.gz").write_bytes(b"changed")
        with self.assertRaises(AssertionError):
            self.check()

    def test_bad_decoded_archive_even_with_bound_encoded_sha(self):
        blob = gzip.compress(b"wrong library", mtime=0)
        self.put("old/binary.so.gz", blob)
        self.build["archived_library_encoded_sha256"] = build.sha(blob)
        self.write_build()
        with self.assertRaises(AssertionError):
            self.check()

    def test_missing_compiled_macro_even_with_bound_library_sha(self):
        self.library = b"no compiled macros"
        for key in ("library_path", "installed_path"):
            Path(self.build[key]).write_bytes(self.library)
        self.build.update(library_sha256=build.sha(self.library), library_bytes=len(self.library))
        blob = gzip.compress(self.library, mtime=0)
        self.put("old/binary.so.gz", blob)
        self.build["archived_library_encoded_sha256"] = build.sha(blob)
        self.write_build()
        with self.assertRaises(AssertionError):
            self.check()


class LaunchExecution(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.freeze = "a" * 40
        self.plan = {"schema": "mr3-p2a0-predeclaration-v8", "max_total_wall_seconds": 100,
                     "stages": [{"stage": "interface", "wall_ceiling_seconds": 50,
                                 "run_directory": str(self.base / "native_run"),
                                 "required_audit_receipts": [],
                                 "command": ["python", "-m", "fake_engineering_only"]}]}
        raw = json.dumps(self.plan).encode()
        (self.base / "predeclared_plan_v8.json").write_bytes(raw)
        (self.base / "mr3_p2a0_v8_source_preflight.json").write_text(json.dumps({
            "passed": True, "freeze": self.freeze,
            "plan_sha256": hashlib.sha256(raw).hexdigest()}))
        patches = [patch.object(launch, "TEMP", self.base),
                   patch.object(launch, "ASSET", self.base),
                   patch.object(launch, "WIRELESS", self.base),
                   patch.object(launch.sys, "argv", ["script", "interface", self.freeze]),
                   patch.dict("sys.modules", {"mr3_learning.supervisor": types.SimpleNamespace(
                       process_identity=lambda pid: {"pid": pid})})]
        for value in patches:
            value.start()
            self.addCleanup(value.stop)

    def check_output(self, command, **kwargs):
        if command[-1] == "--porcelain":
            return ""
        return self.freeze + "\n"

    def fake_popen(self, command, **kwargs):
        # The exclusive record and redirected console exist before the actual spawn call.
        record = json.loads((self.base / "mr3_p2a0_v8_interface_launch.json").read_text())
        self.assertEqual(record["status"], "reserved")
        self.assertEqual(record["command_argv"], command)
        run = self.base / "native_run"
        run.mkdir()
        (run / "benchmark_summary.json").write_text(json.dumps(
            {"passed": True, "freeze": self.freeze}))
        return types.SimpleNamespace(pid=123, wait=lambda: 0)

    def test_records_pid_command_duration_and_budget_without_native(self):
        with patch.object(launch.subprocess, "check_output", side_effect=self.check_output), \
                patch.object(launch.subprocess, "Popen", side_effect=self.fake_popen), \
                patch.object(launch.time, "monotonic", side_effect=[100., 120.]), \
                patch("builtins.print"):
            self.assertEqual(launch.main(), 0)
        record = json.loads((self.base / "mr3_p2a0_v8_interface_launch.json").read_text())
        self.assertEqual(record["benchmark_parent_pid"], 123)
        self.assertEqual(record["wall_duration_sec"], 20)
        self.assertEqual(record["cumulative_wall_seconds"], 20)
        self.assertTrue(record["within_wall_budget"])
        self.assertTrue(record["passed"])
        self.assertEqual(record["status"], "completed")

    def test_actual_duration_excess_fails_without_signal_or_retry(self):
        with patch.object(launch.subprocess, "check_output", side_effect=self.check_output), \
                patch.object(launch.subprocess, "Popen", side_effect=self.fake_popen), \
                patch.object(launch.time, "monotonic", side_effect=[100., 151.]), \
                patch("builtins.print"):
            self.assertEqual(launch.main(), 1)
        record = json.loads((self.base / "mr3_p2a0_v8_interface_launch.json").read_text())
        self.assertFalse(record["within_wall_budget"])
        self.assertFalse(record["passed"])
        with self.assertRaises(AssertionError):
            launch.launch_admission(self.plan, "interface", self.freeze)

    def test_unpushed_or_dirty_never_spawns(self):
        for field in ("unpushed", "dirty"):
            with self.subTest(field=field):
                def git(command, **kwargs):
                    if field == "unpushed" and command[-1] == "@{u}":
                        return "b" * 40
                    if field == "dirty" and command[-1] == "--porcelain":
                        return " M source.py"
                    return self.check_output(command, **kwargs)
                with patch.object(launch.subprocess, "check_output", side_effect=git), \
                        patch.object(launch.subprocess, "Popen") as popen:
                    with self.assertRaises(AssertionError):
                        launch.main()
                    popen.assert_not_called()
        self.assertFalse((self.base / "mr3_p2a0_v8_interface_launch.json").exists())


class Plan(unittest.TestCase):
    def test_stage_commands_budgets_and_preserved_old_bindings(self):
        plan = json.loads((ASSET / "predeclared_plan_v8.json").read_text())
        old = json.loads((BASE / "20261017_mr3_p2a0_v7/predeclared_plan_v7.json").read_text())
        self.assertEqual(plan["independent_source_bindings"][:18], old["independent_source_bindings"])
        self.assertEqual(plan["drive_contract"], old["drive_contract"])
        self.assertEqual(plan["pilot_budget_unchanged"], old["pilot_budget_unchanged"])
        self.assertEqual(plan["unchanged_gates"], old["unchanged_gates"])
        self.assertEqual(plan["max_api_records"], 608)
        self.assertEqual(plan["max_submitted_script_decisions"], 596)
        self.assertEqual(plan["max_total_wall_seconds"], 18000)
        self.assertEqual(sum(s["wall_ceiling_seconds"] for s in plan["stages"]), 18000)
        counts = []
        for stage, domain, port, steps in zip(plan["stages"], (200,202,204,208),
                                             (12801,12811,12821,12831), (32,4,32,300)):
            command = stage["command"]
            value = lambda flag: command[command.index(flag) + 1]
            self.assertEqual(value("--base-domain"), str(domain))
            self.assertEqual(value("--base-port"), str(port))
            self.assertEqual(value("--steps"), str(steps))
            self.assertEqual(value("--run-id"), "mr3_p2a0_20261017_v8_" + stage["stage"])
            self.assertEqual(Path(stage["run_directory"]).name, value("--run-id"))
            if stage["stage"] in ("interface", "reset"):
                self.assertEqual(value("--preparation-probe-version"), "mr3-p2a0-outward-cancel-v3")
            else:
                self.assertNotIn("--preparation-probe-version", command)
            episodes = int(value("--workers")) * len(value("--schedule").split(","))
            counts.append((episodes, episodes * steps))
            self.assertTrue(all(p.startswith("/tmp/mr3_p2a0_v8_" + stage["stage"] + "_")
                                for p in stage["required_audit_receipts"]))
        self.assertEqual(sum(x[0] for x in counts), 12)
        self.assertEqual(sum(x[1] for x in counts), 596)


if __name__ == "__main__":
    unittest.main(verbosity=2)
