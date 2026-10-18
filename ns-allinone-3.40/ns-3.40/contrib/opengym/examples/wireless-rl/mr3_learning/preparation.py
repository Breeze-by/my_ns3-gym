"""One new-plan four-stage engineering matrix; never policy training.

All subprocesses use explicit argv, exclusive artifacts and actual wait results.
The first required failure stops new submissions and later stages. Already
submitted work is always drained; no timeout is turned into a fabricated rc.
"""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from .native_custody import Reader, read_ready_receipt


WORKSPACE = Path(__file__).resolve().parents[7]
WIRELESS_RELATIVE = Path("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl")
STAGES = ("interface", "terminal", "reset", "deadline")
BASE_ROLES = {"full", "drive", "settled", "closure", "information", "peer", "control"}
EXPECTED_ROLES = {name: BASE_ROLES | {"cadence"} | (
    {"input", "angular", "physics"} if name in ("interface", "reset") else set()) for name in STAGES}
WORKLOADS = {"interface": (1, "open:101", 32, 1),
             "terminal": (1, "open:101,open:101", 4, 2),
             "reset": (2, "open:101,open:101,rooms:101,corridors:101", 32, 8),
             "deadline": (1, "open:101", 300, 1)}
LEGACY = {
    "drive": "20261017_mr3_p2a0_v13/independent/mr3_independent_drive_trace_v6.py",
    "settled": "20261017_mr3_p2a0_v8/independent/mr3_independent_settled_turn_v3.py",
    "information": "20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py",
    "peer": "20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py",
    "control": "20261017_mr3_p2a0_v11/independent/mr3_independent_control_phase_v2.py",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def identity(pid):
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": int(pid), "parent": int(fields[1]), "group": int(fields[2]),
                "session": int(fields[3]), "start_ticks": int(fields[19]), "state": fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def argument(argv, name):
    require(argv.count(name) == 1, "missing/repeated argument " + name)
    return argv[argv.index(name) + 1]


def roles(stage):
    return [job["role"] for job in stage["audits"] if job.get("role") is not None]


def validate_plan(plan, workspace=WORKSPACE):
    readiness = plan.get("readiness", {})
    ready = (readiness.get("ready") is True and readiness.get("status") in (None, "ready")
             or readiness.get("status") == "ready" and readiness.get("ready", True) is True)
    require(plan.get("schema") == "mr3-preparation-plan-v1" and ready
            and not readiness.get("pending_bindings", []),
            "new preparation plan is not sealed and ready")
    require(plan.get("final_external_coordinator_absence_required") is True,
            "overall matrix needs external coordinator absence after its actual exit")
    require([stage["stage"] for stage in plan["stages"]] == list(STAGES), "four-stage order differs")
    require(Decimal(plan["budget"]["matrix_wall_seconds"]) > 0
            and Decimal(plan["budget"]["engineering_remaining_seconds"])
            >= Decimal(plan["budget"]["matrix_wall_seconds"]), "matrix is not within actual engineering balance")
    require(sum(Decimal(stage["wall_seconds"]) for stage in plan["stages"])
            <= Decimal(plan["budget"]["matrix_wall_seconds"]), "stage allocations exceed matrix allocation")
    all_outputs = [Path(plan["output_directory"])]
    assets = workspace / WIRELESS_RELATIVE / "report/assets"
    for stage in plan["stages"]:
        name = stage["stage"]
        selected = roles(stage)
        require(len(selected) == len(set(selected)) and set(selected) == EXPECTED_ROLES[name],
                "original34 plus four cadence roles changed: " + name)
        native = stage["native"]
        require(native.get("result_pass_key", "passed") == "passed",
                "matrix native result must retain its original passed predicate")
        argv = native["argv"]
        require(argv[:3] == [plan["learner_python"], "-m", "mr3_learning.benchmark"],
                "native entry is not the declared benchmark")
        workers, schedule, steps, episodes = WORKLOADS[name]
        require(int(argument(argv, "--workers")) == workers
                and argument(argv, "--schedule") == schedule
                and int(argument(argv, "--steps")) == steps
                and stage["expected_episodes"] == episodes, "original matrix workload changed: " + name)
        run = Path(argument(argv, "--output-root")) / argument(argv, "--run-id")
        require(run == Path(stage["run_directory"]) and not run.exists(), "native run exists/differs")
        require(not any("plant-stimulus" in value or "physics-diagnostic" in value for value in argv),
                "regular matrix forbids diagnostic stimulus/physics")
        require(("--preparation-motion-probe" in argv) is (name in ("interface", "reset"))
                and ("--terminal-probe" in argv) is (name == "terminal")
                and ("--deadline-probe" in argv) is (name == "deadline")
                and ("--preparation-parameter-review" in argv) is (name == "interface"),
                "matrix fixture flags changed")
        if name in ("interface", "reset"):
            require(argument(argv, "--preparation-probe-version") == "mr3-p2a0-outward-cancel-v6",
                    "original received-only V6 stimulus changed")
        work = Decimal(argument(argv, "--work-wall-seconds"))
        reserve = Decimal(argument(argv, "--close-reserve-seconds"))
        require(0 < reserve < work < Decimal(stage["wall_seconds"]),
                "native must reserve closure and consumer wall time")
        jobs = stage["audits"]
        ids = [job["id"] for job in jobs]
        require(len(ids) == len(set(ids)) and all(re.fullmatch(r"[a-z][a-z0-9_]*", value)
                and value not in ("native", "watcher", "stage") for value in ids), "duplicate/invalid audit job id")
        done = set()
        while len(done) < len(jobs):
            available = [job for job in jobs if job["id"] not in done
                         and set(job.get("depends_on", [])) <= done]
            require(available, "cyclic/unknown audit dependency")
            done.update(job["id"] for job in available)
        for job in jobs:
            require(type(job.get("required", True)) is bool
                    and (job.get("role") is None or job.get("required", True)), "mandatory role made optional")
            require(job.get("result_pass_key", "passed") == "passed", "matrix scientific passed predicate changed")
            require(job.get("kind", "command") in ("command", "aggregate", "fifo_manifest"), "unknown audit job kind")
            if job.get("kind", "command") != "command":
                require(set(job["members"]) <= set(job.get("depends_on", []))
                        and bool(job["members"]), "aggregate/manifest lacks completed member dependencies")
                if job.get("role") == "input":
                    require(name == "reset" and job["kind"] == "aggregate" and len(job["members"]) == 8,
                            "original eight input leaves are required")
                continue
            command = job["argv"]
            role = job.get("role")
            require(isinstance(command, list) and all(isinstance(value, str) for value in command), "argv must be strings")
            if role in LEGACY:
                require(command[0] == "/usr/bin/python3" and command[1] == str(assets / LEGACY[role]),
                        "original mathematical consumer replaced: " + str(role))
                require(("--peer-only" in command) is (role == "peer"), "peer/control mode changed")
            elif role in ("input", "angular", "physics") or job["id"].startswith("input_"):
                path = {
                    "input": "20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py",
                    "angular": ("20261017_mr3_p2a0_v4/independent/mr3_independent_angular_interface_v1.py"
                                if name == "interface" else "20261017_mr3_p2a0_v17/independent/mr3_independent_angular_reset_matrix_v17.py"),
                    "physics": ("20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py"
                                if name == "interface" else "20261017_mr3_p2a0_v17/independent/mr3_independent_physics_matrix_v17.py"),
                }["input" if job["id"].startswith("input_") else role]
                require(command[:2] == ["/usr/bin/python3", str(assets / path)],
                        "original input/angular/physical mathematical consumer replaced")
            elif role in ("full", "cadence", "closure"):
                interpreter = plan["learner_python"] if role == "full" else "/usr/bin/python3"
                module = {"full": "audit_preparation", "cadence": "audit_odometry_cadence", "closure": "native_custody"}[role]
                require(command[:3] == [interpreter, "-m", "mr3_learning." + module], "new identity/math entry differs")
            if role == "settled" and name == "interface":
                require("--require-use" in command, "interface conditional activation coverage removed")
        for spec in (native, stage["watcher"], *jobs):
            all_outputs.append(Path(spec["output"]))
            all_outputs.extend(Path(spec[key]) for key in ("receipt", "console") if key in spec)
        all_outputs.extend(Path(stage["watcher"][key]) for key in ("ready", "stop"))
    require(sum(len(roles(stage)) for stage in plan["stages"]) == 38, "38 mandatory roles required")
    require(all(path.is_absolute() for path in all_outputs) and len(all_outputs) == len(set(all_outputs))
            and all(not path.exists() for path in all_outputs), "output is relative, reused, duplicated or already exists")
    return plan


class Runner:
    """Finite child custody and exclusive receipts; no simulator-specific control."""

    def __init__(self, directory, cwd, freeze, plan_sha, record):
        self.directory, self.cwd = Path(directory), Path(cwd)
        self.freeze, self.plan_sha, self.record = freeze, plan_sha, record
        self.env = dict(os.environ, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
        self.env.pop("PYTHONPATH", None)

    def spawn(self, job):
        receipt = Path(job.get("receipt", self.directory / (job["id"] + ".json")))
        console = Path(job.get("console", self.directory / (job["id"] + ".log")))
        for path in (Path(job["output"]), receipt, console):
            if path.exists():
                raise FileExistsError(str(path))
        argv = [self.freeze if value == "{freeze}" else value for value in job["argv"]]
        value = {"schema": "mr3-preparation-command-receipt-v1", "freeze": self.freeze,
                 "plan_sha256": self.plan_sha, "id": job["id"], "role": job.get("role"),
                 "argv": argv, "command_argv": argv, "cwd": str(self.cwd),
                 "output": job["output"], "receipt": str(receipt), "console": str(console),
                 "required": job.get("required", True), "started_wall_monotonic_ns": time.monotonic_ns(),
                 "launcher_identity": identity(os.getpid()), "errors": [], "returncode": None, "passed": False,
                 "result_pass_key": job.get("result_pass_key", "passed"),
                 "result_scope": job.get("result_scope", "declared command result only; independent scientific and final closure gates remain necessary")}
        value.update(coordinator_identity=value["launcher_identity"],
                     coordinator_actual_argv=[part.decode(errors="replace") for part in
                         Path("/proc/self/cmdline").read_bytes().split(b"\0") if part],
                     launcher_identity_scope="persistent_coordinator_not_native_owned")
        handle = {"value": value, "receipt": receipt, "console": None, "process": None}
        try:
            require(not Path(job["output"]).exists(), "output exists; never overwrite")
            handle["console"] = console.open("x")
            process = subprocess.Popen(argv, cwd=self.cwd, env=self.env,
                                       stdout=handle["console"], stderr=subprocess.STDOUT)
            handle["process"] = process
            value["benchmark_parent"] = value["process_identity"] = identity(process.pid)
            value["pid"] = process.pid
        except BaseException as error:
            value["errors"].append(repr(error))
        self.record(event="child_spawned" if handle["process"] is not None else "child_not_spawned", **value)
        return handle

    def finish(self, handle):
        value, process = handle["value"], handle["process"]
        if process is not None:
            while True:
                try:
                    value["returncode"] = process.wait()
                    break
                except BaseException as error:
                    value["errors"].append(repr(error))
        if handle["console"] is not None:
            handle["console"].close()
        value["ended_wall_monotonic_ns"] = time.monotonic_ns()
        value["wall_seconds"] = str(Decimal(value["ended_wall_monotonic_ns"] - value["started_wall_monotonic_ns"]) / 10**9)
        value["execution_kind"] = "subprocess_waited" if process is not None else "not_spawned"
        try:
            path = Path(value["output"])
            if path.exists():
                value["output_sha256"] = sha(path)
                output = json.loads(path.read_text())
                value["passed"] = (not value["errors"] and value["returncode"] == 0
                                   and isinstance(output, dict) and output.get(value["result_pass_key"]) is True
                                   and output.get("freeze", self.freeze) == self.freeze)
            else:
                value["errors"].append("declared result missing")
        except BaseException as error:
            value["errors"].append(repr(error))
            value["passed"] = False
        try:
            dump(handle["receipt"], value)
        except BaseException as error:
            value["errors"].append("receipt write failed: " + repr(error))
            value["passed"] = False
        self.record(event="child_waited", **value)
        return value

    def command(self, job):
        return self.finish(self.spawn(job))

    def aggregate(self, job, completed):
        members = [{"id": name, "path": completed[name]["output"],
                    "sha256": completed[name].get("output_sha256"),
                    "passed": completed[name]["passed"],
                    "returncode": completed[name].get("returncode"),
                    "execution_kind": completed[name]["execution_kind"]} for name in job["members"]]
        require(all(member["sha256"] is not None and sha(member["path"]) == member["sha256"]
                    for member in members), "completed member artifact changed/missing before aggregation")
        if job["kind"] == "fifo_manifest":
            value = [{"episode_directory": member["episode_directory"], "path": member["path"],
                      "sha256": member["sha256"]} for member in (
                dict(member, episode_directory=next(spec["episode_directory"] for spec in job["leaves"]
                                                    if spec["id"] == member["id"])) for member in members)]
        else:
            value = {"schema": "mr3-preparation-role-aggregate-v1", "freeze": self.freeze,
                     "passed": all(member["passed"] for member in members), "members": members}
        dump(job["output"], value)
        record = {"id": job["id"], "role": job.get("role"), "output": job["output"],
                  "output_sha256": sha(job["output"]), "passed": all(member["passed"] for member in members),
                  "execution_kind": job["kind"], "returncode": None, "members": members}
        self.record(event="aggregate_written", **record)
        return record


def run_audits(jobs, runner, deadline_ns):
    completed, pending, active = {}, {job["id"]: job for job in jobs}, {}
    failed = False
    with ThreadPoolExecutor(max_workers=4) as pool:
        while pending or active:
            if not failed and time.monotonic_ns() < deadline_ns:
                for name, job in list(pending.items()):
                    if len(active) == 4 or time.monotonic_ns() >= deadline_ns:
                        break
                    if not set(job.get("depends_on", [])) <= completed.keys():
                        continue
                    operation = (lambda job=job: runner.command(job)) if job.get("kind", "command") == "command" else (
                        lambda job=job: runner.aggregate(job, completed))
                    active[pool.submit(operation)] = job
                    del pending[name]
            if not active:
                break
            ready, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in ready:
                job = active.pop(future)
                try:
                    value = future.result()
                except BaseException as error:
                    value = {"id": job["id"], "output": job["output"], "passed": False,
                             "returncode": None, "execution_kind": "runner_error", "error": repr(error)}
                    runner.record(event="runner_error", **value)
                completed[job["id"]] = value
                failed = failed or (job.get("required", True) and not value["passed"])
        # Every submitted future has actually completed before returning; no cancellation.
    skipped = [{"id": name, "role": job.get("role"), "status": "SKIPPED",
                "reason": "earlier_required_failure" if failed else "stage_wall_allocation_exhausted"}
               for name, job in pending.items()]
    for value in skipped:
        runner.record(event="audit_skipped", **value)
    return completed, skipped


def build_plan(*, output_directory, run_root, custody_binding, binary_proof, preflight,
               engineering_remaining_seconds, run_prefix="mr3_p2a_odom50", workspace=WORKSPACE):
    """Draft a new plan from the exact original workload, not its old admission code.

    Root must seal current source/library bindings and readiness before execution.
    This function only prepares JSON; it cannot start a native process.
    """
    workspace, output_directory, run_root = map(lambda value: Path(value).resolve(),
                                               (workspace, output_directory, run_root))
    assets = workspace / WIRELESS_RELATIVE / "report/assets"
    original_path = assets / "20261018_mr3_p2a0_v26_capture/predeclared_plan_v26.json"
    original = json.loads(original_path.read_text())
    learner = str(Path("/home/zhuyulab/miniconda3/envs/ns3gym/bin/python"))
    plan = {"schema": "mr3-preparation-plan-v1",
            "readiness": {"ready": False, "pending_bindings": ["root_source_library_and_buildproof_seal"]},
            "output_directory": str(output_directory), "learner_python": learner,
            "preflight": {"path": str(Path(preflight).resolve()), "schema": "mr3-p2a-v9-preflight-v1"},
            "source_bindings": {}, "library_bindings": {},
            "budget": {"matrix_wall_seconds": "14000", "engineering_remaining_seconds": str(engineering_remaining_seconds),
                       "engineering_remaining_basis": "conservative floor after reserving full trace700; actual charged separately"},
            "historical_workload_reference": {"path": str(original_path), "sha256": sha(original_path),
                "scope": "workload and original34 mathematical role reference only; old admission/output/source pins are not active"},
            "robots_per_environment": 3, "optimizer_steps": 0, "gpu_calls": 0,
            "pilot_budget_changed": False, "normal_spawn": True, "plant_stimulus_enabled": False,
            "physics_diagnostic_enabled": False, "final_external_coordinator_absence_required": True,
            "stages": []}
    caps = (1500, 1200, 4500, 6800)
    allocations = (1250, 850, 3900, 5700)
    domains, ports = (190, 192, 194, 198), (14101, 14111, 14121, 14131)
    direct_sources = {original_path, Path(__file__).resolve()}
    for index, prior in enumerate(original["stages"]):
        name = prior["stage"]
        require(name == STAGES[index], "original V26 stage order differs")
        command = list(prior["command"])
        for flag, value in (("--output-root", str(run_root)), ("--run-id", run_prefix + "_" + name),
                            ("--base-domain", str(domains[index])), ("--base-port", str(ports[index]))):
            command[command.index(flag) + 1] = value
        command += ["--work-wall-seconds", str(allocations[index]), "--close-reserve-seconds", "120"]
        run, local = run_root / (run_prefix + "_" + name), output_directory / name
        native_receipt = local / "native.json"
        stage = {"stage": name, "run_directory": str(run), "wall_seconds": str(caps[index]),
                 "expected_episodes": WORKLOADS[name][3],
                 "native": {"argv": command, "output": str(run / "benchmark_summary.json"),
                            "receipt": str(native_receipt), "console": str(local / "native.log")},
                 "audits": []}
        capture = local / "live_custody.json"
        ready, stop = local / "custody_ready.json", local / "custody_stop.json"
        stage["watcher"] = {"argv": ["/usr/bin/python3", "-m", "mr3_learning.native_custody", "watch",
            "--run-directory", str(run), "--freeze", "{freeze}", "--binding", str(Path(custody_binding).resolve()),
            "--ready-file", str(ready), "--stop-file", str(stop), "--output", str(capture)],
            "ready": str(ready), "stop": str(stop), "output": str(capture),
            "receipt": str(local / "watcher.json"), "console": str(local / "watcher.log")}

        def add(job_id, argv=None, *, role=None, output=None, depends=(), required=True, **extra):
            destination = Path(output or local / (job_id + "_result.json"))
            job = {"id": job_id, "role": role, "output": str(destination), "required": required,
                   "depends_on": list(depends), **extra}
            if argv is not None:
                job.update(argv=[str(value) for value in (*argv, "--output", destination)],
                           receipt=str(local / (job_id + "_command.json")), console=str(local / (job_id + ".log")))
                if len(argv) > 1 and Path(str(argv[1])).is_file():
                    direct_sources.add(Path(str(argv[1])))
            stage["audits"].append(job)
            return job

        def legacy(role, path, directory=run, extra=(), freeze=True, **kwargs):
            args = ["/usr/bin/python3", assets / path, directory]
            if freeze:
                args += ["--freeze", "{freeze}"]
            return add(role, [*args, *extra], role=role, **kwargs)

        add("full", [learner, "-m", "mr3_learning.audit_preparation", run, "--freeze", "{freeze}"], role="full")
        legacy("drive", LEGACY["drive"], extra=("--binary-proof", str(Path(binary_proof).resolve())))
        for role in ("information", "peer", "control", "settled"):
            extra = (("--peer-only",) if role == "peer" else
                     ("--require-use",) if role == "settled" and name == "interface" else ())
            legacy(role, LEGACY[role], extra=extra)
        add("cadence", ["/usr/bin/python3", "-m", "mr3_learning.audit_odometry_cadence", run,
                        "--freeze", "{freeze}"], role="cadence")
        schedule = argument(command, "--schedule").split(",")
        episodes = [run / ("worker" + str(worker)) / (
            "episode" + str(number).zfill(3) + "_" + item.replace(":", "_"))
            for worker in range(WORKLOADS[name][0]) for number, item in enumerate(schedule, 1)]
        input_jobs, fifo_jobs = [], []
        for number, episode in enumerate(episodes, 1):
            if name in ("interface", "reset"):
                job_id = "input_" + str(number).zfill(3)
                add(job_id, ["/usr/bin/python3", assets / (
                    "20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py"),
                    "--episode", episode], role="input" if name == "interface" else None)
                input_jobs.append(job_id)
            job_id = "fifo_" + str(number).zfill(3)
            add(job_id, ["/usr/bin/python3", assets / (
                "20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py"), episode,
                "--freeze", "{freeze}"])
            fifo_jobs.append(job_id)
        if name == "interface":
            legacy("angular", "20261017_mr3_p2a0_v4/independent/mr3_independent_angular_interface_v1.py",
                   episodes[0], freeze=False)
            legacy("physics", "20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py",
                   episodes[0], freeze=False)
        elif name == "reset":
            add("input", role="input", kind="aggregate", members=input_jobs, depends=input_jobs)
            legacy("angular", "20261017_mr3_p2a0_v17/independent/mr3_independent_angular_reset_matrix_v17.py")
            raw = add("physical_per_episode", ["/usr/bin/python3", assets / (
                "20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py"), run], required=False)
            legacy("physics", "20261017_mr3_p2a0_v17/independent/mr3_independent_physics_matrix_v17.py",
                   extra=("--per-episode-report", raw["output"]), depends=(raw["id"],))
        manifest = add("fifo_manifest", kind="fifo_manifest", members=fifo_jobs, depends=fifo_jobs,
                       leaves=[{"id": job_id, "episode_directory": str(episode)} for job_id, episode in zip(fifo_jobs, episodes)])
        closure = ["/usr/bin/python3", "-m", "mr3_learning.native_custody", "review",
            "--run-directory", run, "--freeze", "{freeze}", "--binding", Path(custody_binding).resolve(),
            "--capture", capture, "--launch-receipt", native_receipt, "--fifo-receipts", manifest["output"],
            "--expected-episodes", str(stage["expected_episodes"])]
        if name == "interface":
            closure.append("--require-parameters")
        add("closure", closure, role="closure", depends=(manifest["id"],))
        plan["stages"].append(stage)
    # Every immutable original helper (including transitive checked imports) stays
    # bound to its approved bytes. Old runtime/installed pins are deliberately not
    # copied: root seals those for the genuinely new source/ELF configuration.
    plan["source_bindings"] = {row["path"]: row["sha256"] for row in original["independent_source_bindings"]
                               if "/report/assets/" in row["path"]}
    for relative, expected in plan["source_bindings"].items():
        require(sha(workspace / relative) == expected, "immutable original helper changed: " + relative)
    for path in sorted(direct_sources):
        relative = str(path.relative_to(workspace))
        require(relative not in plan["source_bindings"] or plan["source_bindings"][relative] == sha(path),
                "direct original consumer differs from approved byte binding")
        plan["source_bindings"][relative] = sha(path)
    for path in sorted((workspace / WIRELESS_RELATIVE / "mr3_learning").glob("*.py")):
        plan["source_bindings"][str(path.relative_to(workspace))] = sha(path)
    for path in sorted((assets / "20261019_mr3_p2a_v9").glob("*.py")):
        plan["source_bindings"][str(path.relative_to(workspace))] = sha(path)
    return plan


def execute_plan(plan_path, freeze, workspace=WORKSPACE):
    matrix_started_ns = time.monotonic_ns()
    require(re.fullmatch(r"[0-9a-f]{40}", freeze), "exact40hex freeze required")
    require("MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE" not in os.environ,
            "regular matrix forbids diagnostic physics configuration")
    plan_path, workspace = Path(plan_path).resolve(), Path(workspace).resolve()
    plan = validate_plan(json.loads(plan_path.read_text()), workspace)
    plan_sha = sha(plan_path)

    def source_check():
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=workspace, text=True).strip()
        require(git("rev-parse", "HEAD") == git("rev-parse", "origin/main") == freeze
                and not git("status", "--porcelain"), "source is not the clean pushed freeze")
        require(sha(plan_path) == plan_sha, "sealed plan changed")
        for relative, digest in plan["source_bindings"].items():
            require(sha(workspace / relative) == digest, "source binding differs: " + relative)
            frozen = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=workspace)
            require(hashlib.sha256(frozen).hexdigest() == digest, "source is not the declared Git byte: " + relative)
        for path, digest in plan["library_bindings"].items():
            require(sha(path) == digest, "installed binary differs: " + path)

    source_check()
    preflight = json.loads(Path(plan["preflight"]["path"]).read_text())
    require(preflight.get("schema") == plan["preflight"]["schema"] and preflight.get("passed") is True
            and preflight.get("freeze") == freeze and preflight.get("plan_sha256") == plan_sha,
            "actual preflight does not bind this new plan/freeze")
    output = Path(plan["output_directory"])
    output.mkdir(exist_ok=False)
    lock = threading.Lock()
    result = {"schema": "mr3-preparation-execution-v1", "freeze": freeze, "plan_sha256": plan_sha,
              "stages": [], "original_mandatory_roles": 34, "additional_cadence_roles": 4,
              "gpu_calls": 0, "optimizer_steps": 0, "signals_sent": 0,
              "coordinator_identity": identity(os.getpid()),
              "final_external_coordinator_absence_required": True, "overall_pass_claimed": False}
    charged_ns = 0
    opening = Decimal(plan["budget"]["engineering_remaining_seconds"])
    failed = False
    with (output / "ledger.jsonl").open("x") as ledger:
        def record(**value):
            with lock:
                ledger.write(json.dumps({"freeze": freeze, "plan_sha256": plan_sha,
                                         "wall_monotonic_ns": time.monotonic_ns(), **value}) + "\n")
                ledger.flush()
        record(event="matrix_started", coordinator_identity=identity(os.getpid()),
               plan_path=str(plan_path), preflight_path=plan["preflight"]["path"])
        for stage in plan["stages"]:
            name = stage["stage"]
            cap_ns = int(Decimal(stage["wall_seconds"]) * 10**9)
            charged_ns = time.monotonic_ns() - matrix_started_ns
            if (failed or opening - Decimal(charged_ns) / 10**9 < Decimal(stage["wall_seconds"])
                    or Decimal(plan["budget"]["matrix_wall_seconds"]) - Decimal(charged_ns) / 10**9
                    < Decimal(stage["wall_seconds"])):
                result["stages"].append({"stage": name, "status": "SKIPPED", "reason": "prior_failure_or_insufficient_balance"})
                record(event="stage_skipped", stage=name)
                failed = True
                continue
            started = time.monotonic_ns()
            try:
                source_check()
            except BaseException as error:
                failed = True
                result["stages"].append({"stage": name, "status": "FAIL", "error": repr(error),
                                         "reason": "pre_native_source_admission_failure"})
                record(event="stage_admission_failed", stage=name, error=repr(error))
                continue
            directory = output / name
            directory.mkdir()
            runner = Runner(directory, workspace / WIRELESS_RELATIVE, freeze, plan_sha, record)
            watcher = dict(stage["watcher"], id="watcher")
            watch = runner.spawn(watcher)
            native_value, audit_values, skipped, error = None, {}, [], None
            try:
                ready_deadline = time.monotonic() + watcher.get("ready_timeout_seconds", 30.)
                ready = None
                while ready is None:
                    require(watch["process"] is not None and watch["process"].poll() is None,
                            "custody watcher exited before actual readiness")
                    require(time.monotonic() < ready_deadline, "custody watcher readiness timeout")
                    if Path(watcher["ready"]).exists():
                        raw = Path(watcher["ready"]).read_bytes()
                        if raw.endswith(b"\n"):
                            ready = read_ready_receipt(Reader(), watcher["ready"], freeze,
                                sha(argument(watcher["argv"], "--binding")))
                            require(all(ready["watcher_identity"][key] ==
                                        watch["value"]["process_identity"][key]
                                        for key in ("pid", "start_ticks")),
                                    "ready receipt is not the actually submitted watcher")
                            break
                    time.sleep(.05)
                native_value = runner.command(dict(stage["native"], id="native"))
            except BaseException as failure:
                error = repr(failure)
            finally:
                if native_value is not None and native_value["execution_kind"] == "subprocess_waited":
                    receipt = Path(native_value["receipt"])
                    stop = {"schema": "mr3-native-custody-stop-v1", "freeze": freeze,
                            "launch_receipt": {"path": str(receipt), "sha256": sha(receipt)}}
                else:
                    stop = {"schema": "mr3-native-custody-stop-v1", "freeze": freeze,
                            "native_not_started": True, "reason": "watcher_ready_timeout" if error
                            and "readiness timeout" in error else "pre_native_admission_failure"}
                dump(watcher["stop"], stop)
                watch_value = runner.finish(watch)
            if not error and native_value["passed"] and watch_value["passed"]:
                audit_values, skipped = run_audits(stage["audits"], runner, started + cap_ns)
            ended = time.monotonic_ns()
            duration = ended - started
            charged_ns = time.monotonic_ns() - matrix_started_ns
            passed = (error is None and native_value is not None and native_value["passed"]
                      and watch_value["passed"] and not skipped and duration <= cap_ns
                      and all(audit_values.get(job["id"], {}).get("passed") is True
                              for job in stage["audits"] if job.get("required", True)))
            value = {"stage": name, "status": "PASS" if passed else "FAIL", "passed": passed,
                     "wall_seconds": str(Decimal(duration) / 10**9), "native": native_value,
                     "watcher": watch_value, "audits": audit_values, "skipped_audits": skipped,
                     "error": error, "within_stage_wall_allocation": duration <= cap_ns}
            result["stages"].append(value)
            dump(directory / "stage.json", value)
            record(event="stage_completed", stage=name, passed=passed, wall_seconds=value["wall_seconds"])
            failed = failed or not passed
        try:
            source_check()
        except BaseException as error:
            failed = True
            result["source_end_error"] = repr(error)
        charged_ns = time.monotonic_ns() - matrix_started_ns
        within_matrix = Decimal(charged_ns) / 10**9 <= Decimal(plan["budget"]["matrix_wall_seconds"])
        result.update(passed=not failed and within_matrix, charged_wall_seconds=str(Decimal(charged_ns) / 10**9),
                      within_matrix_wall_allocation=within_matrix,
                      remaining_engineering_seconds_lower_bound=str(opening - Decimal(charged_ns) / 10**9),
                      remaining_engineering_seconds_basis=plan["budget"].get("engineering_remaining_basis",
                          "explicit plan opening; external actual engineering ledger remains authoritative"),
                      all_submitted_children_waited=True)
        record(event="matrix_completed", passed=result["passed"], charged_wall_seconds=result["charged_wall_seconds"])
    dump(output / "summary.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--freeze")
    parser.add_argument("--build-plan", type=Path)
    parser.add_argument("--execution-directory", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--custody-binding", type=Path)
    parser.add_argument("--binary-proof", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--engineering-remaining-seconds")
    parser.add_argument("--run-prefix", default="mr3_p2a_odom50")
    args = parser.parse_args(argv)
    if args.build_plan is not None:
        if args.plan is not None or args.freeze is not None or any(value is None for value in (
                args.execution_directory, args.run_root, args.custody_binding, args.binary_proof,
                args.preflight, args.engineering_remaining_seconds)):
            parser.error("build needs execution-directory/run-root/custody-binding/binary-proof/preflight/engineering-remaining-seconds; no execution plan/freeze")
        value = build_plan(output_directory=args.execution_directory, run_root=args.run_root,
                           custody_binding=args.custody_binding, binary_proof=args.binary_proof,
                           preflight=args.preflight, engineering_remaining_seconds=args.engineering_remaining_seconds,
                           run_prefix=args.run_prefix)
        dump(args.build_plan, value)
        print(json.dumps({"draft_plan": str(args.build_plan), "native_admitted": False}))
        return 0
    if args.plan is None or args.freeze is None:
        parser.error("execution requires --plan and --freeze")
    result = execute_plan(args.plan, args.freeze)
    print(json.dumps({"passed": result["passed"], "charged_wall_seconds": result["charged_wall_seconds"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
