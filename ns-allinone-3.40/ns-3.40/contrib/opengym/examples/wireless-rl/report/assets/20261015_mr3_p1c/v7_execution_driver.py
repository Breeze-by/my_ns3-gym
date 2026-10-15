#!/usr/bin/env python3
"""Run the eight prospectively bound v7 stages, stopping at the first failure.

--dry-run prints command arguments only. It never executes a child, opens the
journal, appends the shared log or requires a not-yet-created execution binding.
The explicit --freeze avoids a Git-SHA self-reference in committed driver code.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time


WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
ROS = "ros2_ws/ros2-multi-robot-automap"
ASSETS = WIRELESS + "/report/assets/20261015_mr3_p1c"
PROFILE = ROS + "/src/multi_robot/config/mr3_fastdds_loopback_udp.xml"
SCALAR_SHA = "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665"
SUBSET_SHA = "ccaf95b736df86ef355e81bd8499d06c6437fae2af7a9606025ca1f2a4588fae"
BASE_SHA = "3ce800bfa0455d25a1c3257635c7c4d593478082bbbf1c4dab6a10eed2fc6991"
FILES = {
    "plan": ASSETS + "/predeclared_native_plan_v7.json",
    "implementation_checks": ASSETS + "/implementation_checks_v7.json",
    "phase_auditor": ASSETS + "/audit_mr3_env_contact_phase_v3.py",
    "command_time_auditor": ASSETS + "/audit_command_time_v7.py",
    "scalar_auditor": ASSETS + "/reward_gate_audit_v3.py",
    "scalar_fault_subset": ASSETS + "/reward_gate_audit_v3_fault_subset.py",
    "profile": PROFILE,
    "driver": ASSETS + "/v7_execution_driver.py",
}
MATRIX = ("terminal", "workers1", "workers2", "workers4", "fault", "deadline")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(path):
    value = json.loads(path.read_text())
    require(isinstance(value, dict), "JSON object required: " + str(path))
    return value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound_path(root, value):
    path = (root / value).resolve()
    require(path.is_relative_to(root), "binding path escapes repository")
    return path


def verify_binding(root, freeze, path, initial_sha):
    require(sha(path) == initial_sha, "execution binding changed")
    binding = load(path)
    require(binding.get("schema") == "mr3-p1c-v7-execution-binding-v1"
            and binding.get("freeze") == freeze, "execution binding identity differs")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(head == freeze, "HEAD changed from the prospectively bound freeze")
    git_hashes = {}

    def verify_file(relative, expected):
        file = bound_path(root, relative)
        relative = str(file.relative_to(root))
        require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None
                and sha(file) == expected, "bound file SHA mismatch: " + relative)
        if relative not in git_hashes:
            blob = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
            git_hashes[relative] = hashlib.sha256(blob).hexdigest()
        require(git_hashes[relative] == expected, "bound Git blob SHA mismatch: " + relative)

    for key, relative in FILES.items():
        item = binding["files"][key]
        require(bound_path(root, item["path"]) == root / relative, "wrong bound path: " + key)
    for item in [*binding["files"].values(), *binding.get("additional_files", [])]:
        verify_file(item["path"], item["sha256"])
    require(binding["files"]["scalar_auditor"]["sha256"] == SCALAR_SHA
            and binding["files"]["scalar_fault_subset"]["sha256"] == SUBSET_SHA,
            "immutable scalar auditor/subset changed")
    verify_file(ASSETS + "/audit_mr3_env_contact_phase_v2.py", BASE_SHA)
    plan = load(root / FILES["plan"])
    require(plan["transport_profile"]["sha256"] == binding["files"]["profile"]["sha256"],
            "plan/profile binding differs")
    checks = load(root / FILES["implementation_checks"])
    require(checks["prospective_native_plan_sha256"] == binding["files"]["plan"]["sha256"],
            "implementation checks/plan binding differs")
    require(checks["source_sha256"], "empty implementation source inventory")
    for relative, expected in checks["source_sha256"].items():
        verify_file(relative, expected)
    return binding


def shell_command(lines):
    return ["rtk", "proxy", "/usr/bin/bash", "--noprofile", "--norc", "-c",
            "\n".join(["set -e", *lines])]


def build_stages(root, plan, freeze):
    """Pure command construction; experiment parameters come from the plan."""
    assets, ros = root / ASSETS, root / ROS
    declarations = {"clock_fixture": ("clock", plan["clock_fixture"]),
                    "pilot": ("pilot", plan["pilot"]),
                    "terminal_probe": ("terminal", plan["terminal_probe"]),
                    "fault_probe": ("fault", plan["fault_probe"]),
                    "deadline_probe": ("deadline", plan["deadline_probe"])}
    for row in plan["throughput_matrix"]:
        name = "workers" + str(row["workers"])
        require("throughput_matrix " + name not in declarations, "duplicate throughput stage")
        declarations["throughput_matrix " + name] = (name, row)
    order = plan["execution_order"]
    require(len(order) == len(declarations) == 8 and set(order) == set(declarations),
            "execution order must contain exactly the eight declared stages")
    stages = []
    for key in order:
        name, row = declarations[key]
        require(row["run_id"] == "mr3_p1c_v7_" + name, "unexpected run namespace")
        stage = {"name": name, "declaration": row, "cwd": root / WIRELESS}
        if name == "clock":
            stage["directory"] = ros / "log/mr3_step_clock" / row["run_id"]
            command = ["/usr/bin/python3", str(ros / "scripts/check_mr3_step_clock.py"),
                       "--run-id", row["run_id"], "--ros-domain-id", str(row["ros_domain"]),
                       "--gazebo-port", str(row["gazebo_port"])]
            stage["native"] = shell_command([
                "unset PYTHONPATH PYTHONHOME", "source /opt/ros/humble/setup.bash",
                "source " + shlex.quote(str(ros / "install/setup.bash")),
                "source /usr/share/gazebo/setup.sh", "export PYTHONNOUSERSITE=1",
                "exec " + shlex.join(command)])
        else:
            stage["directory"] = ros / "log/mr3_learning" / row["run_id"]
            command = ["/home/zhuyulab/miniconda3/envs/ns3gym/bin/python", "-m",
                       "mr3_learning.benchmark", "--workers", str(row["workers"]),
                       "--schedule", row["schedule"], "--steps", str(row["steps"]),
                       "--base-domain", str(row["base_domain"]),
                       "--base-port", str(row["base_port"]), "--run-id", row["run_id"]]
            flag = {"terminal": "--terminal-probe", "fault": "--fault-probe",
                    "deadline": "--deadline-probe"}.get(name)
            if flag:
                command.append(flag)
            stage["native"] = shell_command([
                "source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh",
                "conda activate ns3gym", "export PYTHONNOUSERSITE=1",
                "unset PYTHONPATH PYTHONHOME", "exec " + shlex.join(command)])
            stage["primary_output"] = assets / f"{name}_v7_contact_phase_v3_benchmark_audit.json"
            stage["primary"] = phase_command(
                assets, freeze, [stage["directory"]], stage["primary_output"])
            stage["scalar_output"] = assets / f"{name}_v7_scalar_v3_audit.json"
            if name == "fault":
                stage["prefix_output"] = assets / "fault_w0_e1_v7_contact_phase_v3_audit.json"
                prefix = stage["directory"] / "worker0/episode001_open_101"
                stage["prefix"] = phase_command(assets, freeze, [prefix],
                                                stage["prefix_output"], "--expected-fault")
                stage["scalar"] = ["rtk", "proxy", "/usr/bin/python3",
                                   str(assets / "reward_gate_audit_v3_fault_subset.py"),
                                   str(stage["directory"]), "--freeze", freeze,
                                   "--main-prefix-audit", str(stage["prefix_output"]),
                                   "--output", str(stage["scalar_output"])]
            else:
                stage["scalar"] = ["rtk", "proxy", "/usr/bin/python3",
                                   str(assets / "reward_gate_audit_v3.py"),
                                   str(stage["directory"]), "--freeze", freeze]
        stages.append(stage)
    return stages


def phase_command(assets, freeze, directories, output, flag=None):
    result = ["rtk", "proxy", "/usr/bin/python3",
              str(assets / "audit_mr3_env_contact_phase_v3.py"),
              *(str(path) for path in directories), "--freeze", freeze, "--output", str(output)]
    return [*result, flag] if flag else result


def run_subprocess(argv, cwd, stdout, stderr):
    with stdout.open("x") as out, stderr.open("x") as err:
        process = subprocess.Popen(argv, cwd=cwd, stdout=out, stderr=err,
                                   start_new_session=True)
        try:
            code = process.wait()
        except BaseException:
            # Abort only this Popen-owned group. This is failure cleanup, never
            # normal shutdown/episode credit or a replacement for owned receipts.
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                    process.wait(timeout=90)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                except ProcessLookupError:
                    process.wait()
            raise
    return {"returncode": code, "pid": process.pid}


class Driver:
    def __init__(self, root, freeze, binding_path, journal, runner=run_subprocess):
        self.root, self.freeze = root, freeze
        self.assets = root / ASSETS
        self.binding_path, self.binding_sha = binding_path, sha(binding_path)
        self.plan = load(root / FILES["plan"])
        self.stages = build_stages(root, self.plan, freeze)
        self.journal_path, self.runner = journal, runner
        self.logs = self.assets / "v7_execution_logs"
        self.matrix_output = self.assets / "matrix_v7_contact_phase_v3_audit.json"

    def emit(self, kind, **fields):
        row = {"kind": kind, "utc": datetime.now(timezone.utc).isoformat(),
               "monotonic_ns": time.monotonic_ns(), "freeze": self.freeze, **fields}
        self.journal.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        self.journal.flush()
        print(json.dumps(row, sort_keys=True), flush=True)

    def log(self, message):
        with (self.root / WIRELESS / "log.md").open("a") as output:
            output.write(message)

    def guard(self):
        self.binding = verify_binding(self.root, self.freeze, self.binding_path, self.binding_sha)

    def command(self, stage, role, argv, stdout=None):
        self.guard()
        out = stdout or self.logs / f"{stage}_{role}.stdout.log"
        err = self.logs / f"{stage}_{role}.stderr.log"
        cwd = self.root / WIRELESS if role == "native" else self.root
        self.emit("command_started", stage=stage, role=role, argv=argv, cwd=str(cwd),
                  stdout=str(out), stderr=str(err), binding_sha256=self.binding_sha)
        self.log(f"\n### MR3-P1C v7 {stage} {role} started\n\n"
                 f"Freeze `{self.freeze}`; cwd `{cwd}`. Exact command:\n\n"
                 f"```bash\n{shlex.join(argv)}\n```\n")
        started = time.monotonic()
        try:
            result = self.runner(argv, cwd, out, err)
        except BaseException as error:
            self.emit("command_interrupted_or_failed", stage=stage, role=role, error=repr(error))
            self.log(f"\n{stage}/{role} aborted: `{error!r}`. No PASS or retry.\n")
            raise
        result = {**result, "outer_wall_sec": time.monotonic() - started,
                  "stdout_sha256": sha(out), "stderr_sha256": sha(err)}
        self.emit("command_complete", stage=stage, role=role, **result)
        self.log(f"\n{stage}/{role} actual result: `{json.dumps(result, sort_keys=True)}`.\n")
        require(result["returncode"] == 0, f"{stage}/{role} command failed")

    def phase_gate(self, path, prefix=False):
        result = load(path)
        proof = result["offline_contact_phase_audit"]
        require(result["passed"] is True and result["errors"] == []
                and proof["freeze"] == self.freeze
                and proof["wrapper_sha256"] == self.binding["files"]["phase_auditor"]["sha256"]
                and proof["command_time_gate"]["sha256"] ==
                self.binding["files"]["command_time_auditor"]["sha256"],
                "new phase3/independent time gate failed or binding differs")
        if prefix:
            require(result["expected_infrastructure_fault"] is True
                    and result["complete_episode_credit"] is False
                    and result["transitions"]["complete"] is False
                    and result["transitions"]["transition_count"] == 4,
                    "fault prefix scope changed")
        return result

    def native_gate(self, stage):
        directory = stage["directory"]
        clock = stage["name"] == "clock"
        summary = load(directory / ("summary.json" if clock else "benchmark_summary.json"))
        require(summary["passed"] is True and summary["freeze"] == self.freeze,
                "native summary failed or source freeze differs")
        paths = ([directory / "metadata.json"] if clock else
                 sorted(directory.glob("worker*/episode*/metadata.json")))
        require(paths, "native metadata missing")
        for path in paths:
            value = load(path)
            require(value["freeze"] == self.freeze and
                    value["transport_environment"]["profile_sha256"] ==
                    self.binding["files"]["profile"]["sha256"] and
                    value["transport_environment"]["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp",
                    "native metadata source/profile/backend mismatch")
        if clock:
            require(summary["error"] is None and summary["server_returncode"] == 0
                    and summary["stop_cli_returncode"] == 0, "clock native closure failed")
        else:
            row = stage["declaration"]
            require(summary["workers"] == row["workers"]
                    and summary["steps_per_episode"] == row["steps"]
                    and summary["schedule"] == [[scene, int(seed)] for scene, seed in
                                                (cell.split(":") for cell in
                                                 row["schedule"].split(","))],
                    "native workload differs from declaration")
        self.emit("native_summary_gate_passed", stage=stage["name"], summary=str(directory),
                  scope="isolated clock only" if clock else "declared team workload")

    def run(self):
        with self.journal_path.open("x") as self.journal:
            try:
                self.guard()
                require(not self.logs.exists(), "execution log directory already exists")
                require(not self.matrix_output.exists(), "matrix output already exists")
                for stage in self.stages:
                    require(not stage["directory"].exists(), "native run already exists")
                    for key in ("primary_output", "scalar_output", "prefix_output"):
                        require(key not in stage or not stage[key].exists(), "audit output exists")
                self.logs.mkdir()
                self.emit("execution_binding_verified", binding=str(self.binding_path),
                          binding_sha256=self.binding_sha, stage_count=len(self.stages))
                for stage in self.stages:
                    name = stage["name"]
                    self.command(name, "native", stage["native"])
                    self.native_gate(stage)
                    if name == "clock":
                        continue
                    if name == "fault":
                        self.command(name, "prefix_phase3", stage["prefix"])
                        self.phase_gate(stage["prefix_output"], prefix=True)
                    self.command(name, "primary_phase3", stage["primary"])
                    self.phase_gate(stage["primary_output"])
                    scalar_stdout = None if name == "fault" else stage["scalar_output"]
                    self.command(name, "scalar_v3", stage["scalar"], scalar_stdout)
                    scalar = load(stage["scalar_output"])
                    field = ("completed_subset_scalar_checks_passed" if name == "fault"
                             else "passed_scalar_checks")
                    require(scalar[field] is True and scalar["freeze"] == self.freeze,
                            "immutable scalar v3 gate failed")
                    if name == "fault":
                        require(scalar["completed_subset_transitions"] == 24
                                and scalar["whole_fault_benchmark_reward_audit_performed"] is False,
                                "fault scalar subset scope differs")
                    self.emit("stage_all_declared_gates_passed", stage=name,
                              primary=str(stage["primary_output"]),
                              scalar=str(stage["scalar_output"]))
                directories = {stage["name"]: stage["directory"] for stage in self.stages}
                command = phase_command(self.assets, self.freeze,
                                        [directories[name] for name in MATRIX],
                                        self.matrix_output, "--matrix")
                self.command("matrix", "primary_phase3", command)
                matrix = self.phase_gate(self.matrix_output)
                require(len(matrix["benchmarks"]) == 6 and
                        {Path(row["directory"]).resolve() for row in matrix["benchmarks"]} ==
                        {directories[name].resolve() for name in MATRIX}, "matrix scope differs")
                self.emit("all_eight_stages_and_declared_audits_complete",
                          matrix=str(self.matrix_output), matrix_sha256=sha(self.matrix_output),
                          scope="Scripted engineering evidence; no automatic P1C acceptance")
                return 0
            except BaseException as error:
                self.emit("stopped_after_failure", error=repr(error), automatic_retry=False)
                self.log(f"\nv7 driver stopped: `{error!r}`. Outputs retained; no retry/skip.\n")
                return 130 if isinstance(error, KeyboardInterrupt) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.freeze):
        parser.error("--freeze requires the exact 40-hex pushed commit")
    root = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
    assets = root / ASSETS
    if args.dry_run:
        stages = build_stages(root, load(root / FILES["plan"]), args.freeze)
        commands = [{k: str(v) if isinstance(v, Path) else v for k, v in row.items()}
                    for row in stages]
        matrix = phase_command(assets, args.freeze,
                               [next(row["directory"] for row in stages if row["name"] == name)
                                for name in MATRIX],
                               assets / "matrix_v7_contact_phase_v3_audit.json", "--matrix")
        print(json.dumps({"dry_run": True, "native_executed": False,
                          "stages": commands, "matrix": matrix}, indent=2))
        return 0
    binding = args.binding or assets / "predeclared_execution_binding_v7.json"
    journal = args.journal or assets / "v7_execution.jsonl"
    return Driver(root, args.freeze, binding, journal).run()


if __name__ == "__main__":
    raise SystemExit(main())
