"""Sealed four-stage reach qualification with actual waits and unchanged quotas.

The old dispatcher supplies only proven scheduling/wait/accounting primitives.
This entry has a separate plan, role registry, source contract and qualification.
"""

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import subprocess

from . import preparation as primitives
from .reach_audit_projection import project_module
from . import audit_reach_reset_workload as reset_workload
from .supervisor import (BINARY_REACH_GEOMETRY_RULE, SUPPORT_REACH_GEOMETRY_RULE,
                         validate_reach_geometry_rule, reach_geometry_rule_from_argv)
from .supervisor import (seed_rule_from_argv, start_graph_rule_from_argv,
                         validate_seed_rule, validate_start_graph_rule)

WORKSPACE, WIRELESS_RELATIVE = primitives.WORKSPACE, primitives.WIRELESS_RELATIVE
SCHEMA = "mr3-reach-preparation-plan-v1"
CONTRACT = "mr3-reach-v1"
EXECUTION_SCHEMA = "mr3-reach-preparation-execution-v1"
QUALIFICATION_SCHEMA = "mr3-reach-scientific-qualification-v1"
PREPARATION_SHA256 = "850ab8947f711033f3f2fd17ef57d32098c02d569c1bea0f5cf58aaff8acd767"
BASE_ROLES = {"full", "runtime", "information", "peer_control", "cadence", "closure"}
EXPECTED_ROLES = {name: BASE_ROLES | ({"input", "angular", "physics"}
                  if name in ("interface", "reset") else set()) for name in primitives.STAGES}
CAPS = ("2400", "1200", "6500", "7900")
NATIVE_CAPS = ("1900", "850", "5500", "6900")
BOUNDED_RESERVATION_PROFILE = "bounded-original-workload-v1"
require, sha, dump, argument = primitives.require, primitives.sha, primitives.dump, primitives.argument


SUPPORT_REACH_SOURCES = {
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_support.py",
    str(WIRELESS_RELATIVE / "mr3_learning/reach_support_replay.py"),
}


def _positive_wall_seconds(value, label):
    require(type(value) in (str, int, float, Decimal), label + " must be finite positive seconds")
    try:
        seconds = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(label + " must be finite positive seconds") from error
    require(seconds.is_finite() and seconds > 0, label + " must be finite positive seconds")
    return seconds


def _bounded_reservation(reservation, engineering_remaining_seconds):
    """Only reduce wall reservations; the original workload and gates stay fixed."""
    require(type(reservation) is dict and set(reservation) == {
        "matrix_wall_seconds", "stage_wall_seconds", "native_wall_seconds"},
        "bounded reservation fields differ")
    for key in ("stage_wall_seconds", "native_wall_seconds"):
        require(type(reservation[key]) is dict and set(reservation[key]) == set(primitives.STAGES),
                "bounded reservation requires all four stages: " + key)
    matrix = _positive_wall_seconds(reservation["matrix_wall_seconds"], "matrix reservation")
    balance = _positive_wall_seconds(engineering_remaining_seconds, "engineering remaining")
    require(matrix <= Decimal("18000") and matrix <= balance,
            "bounded matrix exceeds original ceiling/actual engineering balance")
    stages, native = [], []
    for index, name in enumerate(primitives.STAGES):
        stage = _positive_wall_seconds(reservation["stage_wall_seconds"][name], name + " stage reservation")
        work = _positive_wall_seconds(reservation["native_wall_seconds"][name], name + " native reservation")
        require(stage <= Decimal(CAPS[index]), "bounded stage exceeds original ceiling: " + name)
        require(Decimal("120") < work <= Decimal(NATIVE_CAPS[index]) and work < stage,
                "bounded native must retain closure/consumer reserves and original ceiling: " + name)
        stages.append(str(stage))
        native.append(str(work))
    require(sum(map(Decimal, stages)) <= matrix, "bounded stage allocations exceed matrix reservation")
    return str(matrix), tuple(stages), tuple(native)


def source_inventory(root=WORKSPACE):
    """All tracked component execution sources plus all learner modules.

    Independent historical helpers are additionally inherited from the original
    source registry; tests and documentation are not substituted for runtime.
    """
    root = Path(root)
    paths = subprocess.check_output(["git", "ls-files", "--",
        "ros2_ws/ros2-multi-robot-automap/src", "ros2_ws/ros2-multi-robot-automap/scripts"],
        cwd=root, text=True).splitlines()
    suffixes = {".py", ".cpp", ".hpp", ".h", ".yaml", ".xml", ".sdf", ".world", ".xacro"}
    selected = {p for p in paths if Path(p).suffix in suffixes or Path(p).name == "CMakeLists.txt"}
    selected.update(str(p.relative_to(root)) for p in
        (root / WIRELESS_RELATIVE / "mr3_learning").glob("*.py"))
    return selected


def validate_plan(plan, workspace=WORKSPACE):
    geometry_rule = validate_reach_geometry_rule(
        plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE), safety_contract=CONTRACT)
    seed_rule = validate_seed_rule(plan.get("seed_rule", "legacy"))
    start_graph_rule = validate_start_graph_rule(plan.get("start_graph_rule", "original-seed-cell"),
                                                seed_rule=seed_rule)
    require(plan.get("schema") == SCHEMA and plan.get("safety_contract") == CONTRACT
            and plan.get("readiness") == {"ready": True, "pending_bindings": []},
            "reach plan is not explicitly sealed")
    require(type(plan.get("reset_workload_reader_profile")) is str
            and plan["reset_workload_reader_profile"] == reset_workload.PROFILE,
            "Reach reset workload reader profile is missing or unknown")
    require(reset_workload.SOURCE_PATHS <= plan["source_bindings"].keys(),
            "Reach reset workload reader source inventory incomplete")
    require(all(plan["source_bindings"][str(path)] == expected
                for path, expected in reset_workload.SOURCES.values()),
            "immutable reset workload reader source pin differs")
    require(plan.get("robots_per_environment") == 3 and plan.get("optimizer_steps") == 0
            and plan.get("gpu_calls") == 0 and plan.get("pilot_budget_changed") is False
            and plan.get("normal_spawn") is True and plan.get("plant_stimulus_enabled") is False
            and plan.get("physics_diagnostic_enabled") is False
            and plan.get("final_external_coordinator_absence_required") is True,
            "reach qualification scope differs")
    require([s["stage"] for s in plan["stages"]] == list(primitives.STAGES), "stage order differs")
    budget = plan["budget"]
    bounded = "reservation_profile" in budget
    if bounded:
        require(type(budget["reservation_profile"]) is str
                and budget["reservation_profile"] == BOUNDED_RESERVATION_PROFILE,
                "unknown reservation profile")
        _bounded_reservation({"matrix_wall_seconds": budget["matrix_wall_seconds"],
            "stage_wall_seconds": {stage["stage"]: stage["wall_seconds"] for stage in plan["stages"]},
            "native_wall_seconds": {stage["stage"]: argument(stage["native"]["argv"], "--work-wall-seconds")
                                    for stage in plan["stages"]}}, budget["engineering_remaining_seconds"])
    else:
        require(_positive_wall_seconds(budget["matrix_wall_seconds"], "matrix reservation") == Decimal("18000")
                and _positive_wall_seconds(budget["engineering_remaining_seconds"], "engineering remaining") >= 18000,
                "matrix budget/forward allocation differs")
    require(budget.get("borrow_unused_prior_stage_reservations") is True,
            "matrix budget/forward allocation differs")
    require(source_inventory(workspace) <= plan["source_bindings"].keys(), "incomplete runtime inventory")
    if seed_rule != "legacy":
        require({"ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/" + name
                 for name in ("mr3_observation.py", "mr3_seed_certificate.py", "mr3_reach_geometry.py", "mr3_adapter.py")}
                <= plan["source_bindings"].keys(), "exact seed rule runtime inventory incomplete")
    if start_graph_rule != "original-seed-cell":
        require("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_point_graph.py"
                in plan["source_bindings"], "point graph helper runtime inventory incomplete")
    if geometry_rule == SUPPORT_REACH_GEOMETRY_RULE:
        require(SUPPORT_REACH_SOURCES <= plan["source_bindings"].keys(),
                "support geometry producer/replay source inventory incomplete")
    outputs = [plan["output_directory"]]
    for i, stage in enumerate(plan["stages"]):
        name, jobs = stage["stage"], stage["audits"]
        if not bounded:
            require(stage["wall_seconds"] == CAPS[i], "approved base stage allocation differs")
        selected = primitives.roles(stage)
        require(len(selected) == len(set(selected)) and set(selected) == EXPECTED_ROLES[name],
                "reach scientific obligation inventory differs: " + name)
        argv = stage["native"]["argv"]
        require(seed_rule_from_argv(argv) == seed_rule,
                "native stage seed rule differs from the qualification plan: " + name)
        require(start_graph_rule_from_argv(argv) == start_graph_rule,
                "native stage start graph rule differs from the qualification plan: " + name)
        require(reach_geometry_rule_from_argv(argv) == geometry_rule,
                "native stage reach geometry rule differs from qualification plan: " + name)
        workers, schedule, steps, episodes = primitives.WORKLOADS[name]
        require(argv[:3] == [plan["learner_python"], "-m", "mr3_learning.benchmark"]
                and argument(argv, "--safety-contract") == CONTRACT
                and int(argument(argv, "--workers")) == workers
                and argument(argv, "--schedule") == schedule
                and int(argument(argv, "--steps")) == steps
                and stage["expected_episodes"] == episodes,
                "native workload/contract differs: " + name)
        require(("--preparation-motion-probe" in argv) is (name in ("interface", "reset"))
                and ("--terminal-probe" in argv) is (name == "terminal")
                and ("--deadline-probe" in argv) is (name == "deadline")
                and ("--preparation-parameter-review" in argv) is (name == "interface")
                and not any("plant-stimulus" in a or "physics-diagnostic" in a for a in argv),
                "fixture scope differs")
        if name in ("interface", "reset"):
            require(argument(argv, "--preparation-probe-version") == "mr3-p2a-reach-outward-cancel-v1",
                    "reach fixture version differs")
        if name == "interface":
            require(argument(argv, "--preparation-parameter-profile") == "gentle_turn_v1",
                    "exact actual parameter readback is required")
        require((bounded or argument(argv, "--work-wall-seconds") == NATIVE_CAPS[i])
                and argument(argv, "--close-reserve-seconds") == "120", "native reservation differs")
        require(Path(argument(argv, "--output-root")) / argument(argv, "--run-id")
                == Path(stage["run_directory"]), "run directory differs")
        ids = [j["id"] for j in jobs]
        require(len(ids) == len(set(ids)), "duplicate audit job")
        by_id = {j["id"]: j for j in jobs}
        run, local = Path(stage["run_directory"]), Path(plan["output_directory"]) / name
        expected_episodes = [run / f"worker{worker}" / (f"episode{number:03d}_" + item.replace(":", "_"))
            for worker in range(workers) for number, item in enumerate(schedule.split(","), 1)]
        fifo_ids = [f"fifo_{number:03d}" for number in range(1, episodes + 1)]
        if seed_rule != "legacy":
            expected_inputs = ({f"input_{number:03d}" for number in range(1, episodes + 1)}
                               if name in ("interface", "reset") else set())
            require({job["id"] for job in jobs if job["id"].startswith("input_")} == expected_inputs,
                    "exact input episode inventory differs")
        require({j["id"] for j in jobs if j["id"].startswith("fifo_")} == set(fifo_ids) | {"fifo_manifest"},
                "complete per-episode FIFO inventory required")
        for aggregate_id in ("peer_control", "fifo_manifest"):
            job = by_id[aggregate_id]
            require(job.get("kind") == ("aggregate" if aggregate_id == "peer_control" else "fifo_manifest")
                    and job.get("members") == job.get("depends_on") == fifo_ids,
                    "combined peer/control/FIFO aggregate omitted a real episode")
        require(by_id["fifo_manifest"].get("leaves") == [{"id": k, "episode_directory": str(p)}
                for k, p in zip(fifo_ids, expected_episodes)], "FIFO leaf episode binding differs")
        watcher = stage["watcher"]
        require(watcher["argv"][:4] == ["/usr/bin/python3", "-m", "mr3_learning.native_custody_reach", "watch"],
                "live custody entry differs")
        for flag, expected in (("--run-directory", str(run)), ("--freeze", "{freeze}"),
                ("--binding", plan["custody_binding"]), ("--ready-file", watcher["ready"]),
                ("--stop-file", watcher["stop"]), ("--output", watcher["output"])):
            require(argument(watcher["argv"], flag) == expected, "watcher declaration differs: " + flag)
        done = set()
        while len(done) < len(jobs):
            available = {j["id"] for j in jobs if j["id"] not in done
                         and set(j.get("depends_on", [])) <= done}
            require(available, "unknown/cyclic dependency")
            done.update(available)
        for job in jobs:
            require(re.fullmatch(r"[a-z][a-z0-9_]*", job["id"])
                    and job.get("result_pass_key", "passed") == "passed"
                    and (job.get("role") is None or job.get("required", True)),
                    "scientific result predicate weakened")
            if job.get("role") in ("full", "runtime", "information", "cadence", "closure"):
                expected = {"full": "audit_reach_preparation", "runtime": "audit_reach_runtime",
                            "information": "audit_reach_information", "cadence": "audit_reach_cadence",
                            "closure": "native_custody_reach"}[job["role"]]
                require(job["argv"][1:3] == ["-m", "mr3_learning." + expected],
                        "reach role routed to wrong entry")
                command = job["argv"]
                require(argument(command, "--freeze") == "{freeze}"
                        and argument(command, "--output") == job["output"], "role freeze/output differs")
                if job["role"] == "closure":
                    require(command[3] == "review" and job["depends_on"] == ["fifo_manifest"], "closure DAG differs")
                    for flag, expected in (("--run-directory", str(run)), ("--binding", plan["custody_binding"]),
                            ("--capture", watcher["output"]), ("--launch-receipt", stage["native"]["receipt"]),
                            ("--fifo-receipts", by_id["fifo_manifest"]["output"]), ("--expected-episodes", str(episodes))):
                        require(argument(command, flag) == expected, "closure binding differs: " + flag)
                    require(("--require-parameters" in command) is (name == "interface"), "parameter closure removed")
                else:
                    require(command[3] == str(run), "scientific role reads another run")
                    if job["role"] == "full":
                        require(Path(argument(command, "--plan")).is_absolute(), "full plan must be absolute")
            if job.get("role") in ("input", "angular", "physics") or job["id"].startswith("input_") or job["id"] == "physical_per_episode":
                if job.get("kind") == "aggregate":
                    expected_inputs = [f"input_{number:03d}" for number in range(1, episodes + 1)]
                    require(job["id"] == "input" and job["members"] == job["depends_on"] == expected_inputs,
                            "input aggregate omitted an episode")
                elif name == "reset" and job["id"] == "physical_per_episode":
                    original = Path(workspace) / WIRELESS_RELATIVE / "report/assets/20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py"
                    require(job.get("role") is None and job.get("required") is False
                            and job.get("depends_on") == []
                            and job["argv"] == ["/usr/bin/python3", str(original), str(run),
                                                "--output", job["output"]],
                            "reset per-episode physical report binding differs")
                elif name == "reset" and job.get("role") in ("angular", "physics"):
                    role = job["role"]
                    report = by_id["physical_per_episode"]["output"] if role == "physics" else None
                    require(job["id"] == role and job.get("required") is True
                            and job.get("depends_on") == (["physical_per_episode"] if role == "physics" else [])
                            and job["argv"] == reset_workload.command_argv(
                                role, run, "{freeze}", job["output"], report),
                            "Reach reset workload reader argv/dependency differs")
                else:
                    role = "input" if job["id"].startswith("input_") else job.get("role")
                    relative = {"input": "20261017_mr3_p2a0_v4/independent/mr3_p2a0_v4_independent_input_episode_review_v1.py",
                        "angular": ("20261017_mr3_p2a0_v4/independent/mr3_independent_angular_interface_v1.py" if name == "interface"
                                    else "20261017_mr3_p2a0_v17/independent/mr3_independent_angular_reset_matrix_v17.py"),
                        "physics": ("20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py" if name == "interface"
                                    else "20261017_mr3_p2a0_v17/independent/mr3_independent_physics_matrix_v17.py"),
                        None: "20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py"}[role]
                    expected_entry = (["/usr/bin/python3", "-m", "mr3_learning.audit_seed_inputs"]
                        if role == "input" and seed_rule != "legacy" else
                        ["/usr/bin/python3", str(Path(workspace) / WIRELESS_RELATIVE / "report/assets" / relative)])
                    require(job["argv"][:len(expected_entry)] == expected_entry,
                            "declared input/angular/physics mathematical consumer replaced")
                    if role == "input" and seed_rule != "legacy":
                        match = re.fullmatch(r"input_([0-9]{3})", job["id"])
                        require(match is not None and 1 <= int(match[1]) <= len(expected_episodes),
                                "exact input job has no declared episode")
                        episode = expected_episodes[int(match[1]) - 1]
                        require(job["argv"] == [*expected_entry, "--episode", str(episode),
                                                "--output", job["output"]],
                                "exact input episode/output binding differs")
            if job["id"].startswith("fifo_") and job.get("kind") != "fifo_manifest":
                require(job["argv"][1:3] == ["-m", "mr3_learning.audit_reach_peer_control"],
                        "FIFO/peer/control requires complete new replay")
                require(job["argv"][3] == str(expected_episodes[fifo_ids.index(job["id"])])
                        and argument(job["argv"], "--freeze") == "{freeze}", "FIFO episode/freeze differs")
            outputs.append(job["output"])
        outputs.extend([stage["native"]["output"], stage["watcher"]["output"],
                        stage["watcher"]["ready"], stage["watcher"]["stop"]])
    require(len(outputs) == len(set(outputs)), "output collision")
    return plan


def load_plan(path, workspace=WORKSPACE):
    return validate_plan(json.loads(Path(path).read_text()), workspace)


def source_check(plan, plan_path, freeze, root=WORKSPACE, require_clean=True):
    root, plan_path = Path(root), Path(plan_path)
    require(re.fullmatch(r"[0-9a-f]{40}", freeze), "exact freeze required")
    git = lambda *args: subprocess.check_output(["git", *args], cwd=root)
    if require_clean:
        require(git("rev-parse", "HEAD").decode().strip() == freeze
                == git("rev-parse", "origin/main").decode().strip()
                and not git("status", "--porcelain"), "source is not the clean pushed freeze")
    relative_plan = str(plan_path.resolve().relative_to(root))
    require(git("show", freeze + ":" + relative_plan) == plan_path.read_bytes(), "plan is not frozen")
    require(all(Path(argument(next(j for j in s["audits"] if j.get("role") == "full")["argv"],
                              "--plan")).resolve() == plan_path.resolve() for s in plan["stages"]),
            "full role refers to a different source plan")
    proof = {}
    for relative, expected in plan["source_bindings"].items():
        raw = git("show", freeze + ":" + relative)
        require(hashlib.sha256(raw).hexdigest() == sha(root / relative) == expected,
                "source binding differs: " + relative)
        proof[relative] = {"sha256": expected, "git_source": freeze + ":" + relative}
    for path, expected in plan["library_bindings"].items():
        require(sha(path) == expected, "actual installed ELF differs: " + path)
    return proof


def build_plan(*, plan_path, seed_rule="legacy", start_graph_rule="original-seed-cell",
               reach_geometry_rule=BINARY_REACH_GEOMETRY_RULE, reservation=None, **kwargs):
    validate_seed_rule(seed_rule)
    validate_start_graph_rule(start_graph_rule, seed_rule=seed_rule)
    validate_reach_geometry_rule(reach_geometry_rule, safety_contract=CONTRACT)
    matrix_seconds, stage_seconds, native_seconds = "18000", CAPS, NATIVE_CAPS
    if reservation is not None:
        matrix_seconds, stage_seconds, native_seconds = _bounded_reservation(
            reservation, kwargs["engineering_remaining_seconds"])
    plan = primitives.build_plan(**kwargs, information_implementation="admitted_index_three_keys_v1",
                                 nav2_parameter_profile="gentle_turn_v1")
    plan.update(schema=SCHEMA, safety_contract=CONTRACT,
                reset_workload_reader_profile=reset_workload.PROFILE,
                custody_binding=str(Path(kwargs["custody_binding"]).resolve()),
                readiness={"ready": True, "pending_bindings": []},
                role_registry={"mandatory_roles": sum(map(len, EXPECTED_ROLES.values())),
                    "combined_runtime": "six-source drive, paired actuation, calibration and independent reach geometry",
                    "combined_peer_control": "complete peer cloud/scan, v2 causal phase and final command FIFO",
                    "old_profile_credit_reused": False})
    if seed_rule != "legacy":
        plan["seed_rule"] = seed_rule
    if start_graph_rule != "original-seed-cell":
        plan["start_graph_rule"] = start_graph_rule
    if reach_geometry_rule != BINARY_REACH_GEOMETRY_RULE:
        plan["reach_geometry_rule"] = reach_geometry_rule
    plan["preflight"]["schema"] = "mr3-reach-preflight-v1"
    plan["budget"].update(matrix_wall_seconds=matrix_seconds, borrow_unused_prior_stage_reservations=True,
        engineering_remaining_basis="Approved 52000 cumulative engineering ceiling; all native/read-only/closure tails charged")
    if reservation is not None:
        plan["budget"]["reservation_profile"] = BOUNDED_RESERVATION_PROFILE
    for i, stage in enumerate(plan["stages"]):
        name, run = stage["stage"], Path(stage["run_directory"])
        local = Path(plan["output_directory"]) / name
        argv = stage["native"]["argv"]
        argv[argv.index("--work-wall-seconds") + 1] = native_seconds[i]
        argv += ["--safety-contract", CONTRACT]
        if seed_rule != "legacy":
            argv += ["--seed-rule", seed_rule]
        if start_graph_rule != "original-seed-cell":
            argv += ["--start-graph-rule", start_graph_rule]
        if reach_geometry_rule != BINARY_REACH_GEOMETRY_RULE:
            argv += ["--reach-geometry-rule", reach_geometry_rule]
        if name in ("interface", "reset"):
            argv[argv.index("--preparation-probe-version") + 1] = "mr3-p2a-reach-outward-cancel-v1"
        stage["wall_seconds"] = stage_seconds[i]
        stage["watcher"]["argv"][2] = "mr3_learning.native_custody_reach"
        retained = [j for j in stage["audits"] if j.get("role") in ("input", "angular", "physics")
                    or j["id"].startswith("input_") or j["id"] == "physical_per_episode"]
        if seed_rule != "legacy":
            for job in retained:
                if job.get("kind") != "aggregate" and (job.get("role") == "input" or job["id"].startswith("input_")):
                    job["argv"] = ["/usr/bin/python3", "-m", "mr3_learning.audit_seed_inputs", *job["argv"][2:]]
        if name == "reset":
            per_episode = next(job["output"] for job in retained if job["id"] == "physical_per_episode")
            for job in retained:
                if job.get("role") in ("angular", "physics"):
                    report = per_episode if job["role"] == "physics" else None
                    job["argv"] = reset_workload.command_argv(
                        job["role"], run, "{freeze}", job["output"], report)
        stage["audits"] = retained

        def add(job_id, module=None, *, role=None, depends=(), extra=(), **fields):
            destination = local / (job_id + "_result.json")
            job = {"id": job_id, "role": role, "output": str(destination),
                   "required": True, "depends_on": list(depends), **fields}
            if module:
                job.update(argv=[plan["learner_python"] if role == "full" else "/usr/bin/python3",
                    "-m", "mr3_learning." + module, *map(str, extra), "--output", str(destination)],
                    receipt=str(local / (job_id + "_command.json")), console=str(local / (job_id + ".log")))
            stage["audits"].append(job)
            return job

        add("full", "audit_reach_preparation", role="full",
            extra=(run, "--freeze", "{freeze}", "--plan", Path(plan_path).resolve()))
        for role, module in (("runtime", "audit_reach_runtime"), ("information", "audit_reach_information"),
                             ("cadence", "audit_reach_cadence")):
            add(role, module, role=role, extra=(run, "--freeze", "{freeze}"))
        schedule = argument(argv, "--schedule").split(",")
        episodes = [run / f"worker{worker}" / (f"episode{number:03d}_" + item.replace(":", "_"))
                    for worker in range(primitives.WORKLOADS[name][0])
                    for number, item in enumerate(schedule, 1)]
        ids = []
        for number, episode in enumerate(episodes, 1):
            job_id = f"fifo_{number:03d}"
            add(job_id, "audit_reach_peer_control", extra=(episode, "--freeze", "{freeze}"))
            ids.append(job_id)
        add("peer_control", role="peer_control", kind="aggregate", members=ids, depends=ids)
        manifest = add("fifo_manifest", kind="fifo_manifest", members=ids, depends=ids,
            leaves=[{"id": job_id, "episode_directory": str(ep)} for job_id, ep in zip(ids, episodes)])
        closure = ["review", "--run-directory", run, "--freeze", "{freeze}",
            "--binding", plan["custody_binding"], "--capture", stage["watcher"]["output"],
            "--launch-receipt", stage["native"]["receipt"], "--fifo-receipts", manifest["output"],
            "--expected-episodes", str(stage["expected_episodes"])]
        if name == "interface":
            closure.append("--require-parameters")
        add("closure", "native_custody_reach", role="closure", depends=("fifo_manifest",), extra=closure)
    root = kwargs.get("workspace", WORKSPACE)
    for path in source_inventory(root) | reset_workload.SOURCE_PATHS:
        plan["source_bindings"][path] = sha(Path(root) / path)
    if seed_rule != "legacy":
        for name in ("mr3_observation.py", "mr3_seed_certificate.py", "mr3_reach_geometry.py", "mr3_adapter.py"):
            relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/" + name
            plan["source_bindings"][relative] = sha(Path(root) / relative)
    if start_graph_rule != "original-seed-cell":
        relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_point_graph.py"
        plan["source_bindings"][relative] = sha(Path(root) / relative)
    if reach_geometry_rule == SUPPORT_REACH_GEOMETRY_RULE:
        for relative in SUPPORT_REACH_SOURCES:
            plan["source_bindings"][relative] = sha(Path(root) / relative)
    binding = json.loads(Path(kwargs["custody_binding"]).read_text())
    require(validate_reach_geometry_rule(binding.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE),
                safety_contract=CONTRACT) == reach_geometry_rule, "custody binding reach geometry rule differs")
    if reach_geometry_rule == SUPPORT_REACH_GEOMETRY_RULE:
        bound = {str(Path(row["path"]).relative_to(root)) if Path(row["path"]).is_absolute()
                 else row["path"]: row["sha256"] for row in binding["source_bindings"]}
        require(SUPPORT_REACH_SOURCES <= bound.keys() and all(
                bound[path] == plan["source_bindings"][path] for path in SUPPORT_REACH_SOURCES),
                "custody binding lacks exact support producer/replay sources")
    for row in binding["source_bindings"]:
        path = Path(row["path"])
        relative = str(path.relative_to(root)) if path.is_absolute() else str(path)
        plan["source_bindings"][relative] = row["sha256"]
    plan["source_bindings"][str(Path(kwargs["custody_binding"]).resolve().relative_to(root))] = sha(kwargs["custody_binding"])
    plan["library_bindings"] = {spec["path"]: spec["sha256"] for spec in binding["binaries"].values()}
    return validate_plan(plan, root)


def load_executor():
    module, proof = project_module("preparation.py", PREPARATION_SHA256, (
        ("from .native_custody import Reader, read_ready_receipt",
         "from .native_custody_reach import Reader, read_ready_receipt", 1),
        ("mr3-preparation-command-receipt-v1", "mr3-reach-native-wait-v1", 1),
        ('"plan_sha256": self.plan_sha, "id": job["id"]',
         '"safety_contract": "mr3-reach-v1", "plan_sha256": self.plan_sha, "id": job["id"]', 1),
        ("mr3-native-custody-stop-v1", "mr3-reach-native-custody-stop-v1", 2),
        ('"mr3-reach-native-custody-stop-v1", "freeze": freeze,',
         '"mr3-reach-native-custody-stop-v1", "safety_contract": "mr3-reach-v1", "freeze": freeze,', 2),
        ("mr3-preparation-execution-v1", EXECUTION_SCHEMA, 1),
        ('"original_mandatory_roles": 34, "additional_cadence_roles": 4,',
         '"reach_mandatory_roles": 30, "old_profile_credit_reused": False,', 1),
    ))
    module.validate_plan = validate_plan
    return module, proof


def execute_plan(plan_path, freeze, workspace=WORKSPACE):
    module, _ = load_executor()
    return module.execute_plan(plan_path, freeze, workspace)


def _qualification_evidence(plan_path, freeze, outer_wait, root=WORKSPACE):
    plan_path, root = Path(plan_path), Path(root)
    plan = load_plan(plan_path, root)
    source_check(plan, plan_path, freeze, root, require_clean=False)
    bindings, gone = {}, []

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        spec = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        require(bindings.setdefault(str(path.resolve()), spec) == spec, "qualification input changed")
        return json.loads(raw)

    def absent(saved):
        require(type(saved) is dict and type(saved.get("pid")) is int
                and saved["pid"] > 0 and type(saved.get("start_ticks")) is int
                and saved["start_ticks"] > 0, "saved process identity missing")
        actual = primitives.identity(saved["pid"])
        require(actual is None or actual["start_ticks"] != saved["start_ticks"],
                "saved process still present at external qualification")
        gone.append(saved)

    summary_path = Path(plan["output_directory"]) / "summary.json"
    summary = read(summary_path)
    outer = read(outer_wait)
    require(outer.get("schema") == "mr3-reach-outer-actual-wait-v1"
            and outer.get("scope") == "engineering" and outer.get("safety_contract") == CONTRACT
            and outer.get("actual_waited") is True and outer.get("actual_returncode") == 0
            and outer.get("passed") is True and outer.get("source_unchanged") is True,
            "matrix outer actual wait is not passed")
    require(outer["actual_argv"][1:3] == ["-m", "mr3_learning.reach_preparation"]
            and argument(outer["actual_argv"], "--freeze") == freeze
            and Path(argument(outer["actual_argv"], "--plan")).resolve() == plan_path.resolve(),
            "outer wait is for another matrix")
    require(summary.get("schema") == EXECUTION_SCHEMA and summary.get("freeze") == freeze
            and summary.get("plan_sha256") == sha(plan_path) and summary.get("passed") is True
            and summary.get("all_submitted_children_waited") is True
            and summary.get("within_matrix_wall_allocation") is True
            and summary.get("reach_mandatory_roles") == 30
            and summary.get("old_profile_credit_reused") is False,
            "matrix is not complete new-profile qualification evidence")
    require(all(outer["child_identity"][k] == summary["coordinator_identity"][k]
                for k in ("pid", "start_ticks")), "outer wait does not bind matrix process")
    absent(outer["child_identity"])
    require(len(summary["stages"]) == 4, "matrix stage count differs")
    roles, episodes, episode_files = 0, [], {}
    for declared, completed in zip(plan["stages"], summary["stages"]):
        require(completed.get("stage") == declared["stage"] and completed.get("status") == "PASS"
                and completed.get("passed") is True and not completed.get("skipped_audits")
                and completed.get("within_stage_wall_allocation") is True,
                "required stage is incomplete/failed")
        children = [completed["native"], completed["watcher"], *completed["audits"].values()]
        native_spec = dict(declared["native"], id="native")
        allocation = completed.get("budget_allocation")
        require(allocation == primitives.borrowed_stage_budget(plan,
                primitives.STAGES.index(declared["stage"]), allocation["elapsed_matrix_wall_ns"]),
                "native forward budget was not derived by declared arithmetic")
        native_spec = primitives.budgeted_native_job(native_spec, allocation)
        specs = {j["id"]: j for j in declared["audits"]}
        require(set(completed["audits"]) == set(specs), "submitted audit inventory differs")
        specs.update(native=native_spec, watcher=dict(declared["watcher"], id="watcher"))
        for child in children:
            require(child.get("passed") is True or child.get("id") == "physical_per_episode",
                    "submitted required child failed")
            result = read(child["output"])
            require(sha(child["output"]) == child.get("output_sha256"), "scientific output changed")
            if child.get("execution_kind") == "subprocess_waited":
                receipt = read(child["receipt"])
                spec = specs[child["id"]]
                expected_argv = [freeze if part == "{freeze}" else part for part in spec["argv"]]
                actual_passed = (not receipt.get("errors") and receipt.get("returncode") == 0
                    and type(result) is dict and result.get(spec.get("result_pass_key", "passed")) is True
                    and result.get("freeze", freeze) == freeze)
                require(receipt == child and receipt.get("schema") == "mr3-reach-native-wait-v1"
                        and receipt.get("safety_contract") == CONTRACT
                        and type(receipt.get("returncode")) is int
                        and receipt.get("passed") is actual_passed
                        and receipt.get("freeze") == freeze and receipt.get("plan_sha256") == sha(plan_path)
                        and receipt.get("argv") == receipt.get("command_argv") == expected_argv
                        and receipt.get("output") == spec["output"] and receipt.get("receipt") == spec["receipt"]
                        and receipt.get("cwd") == str(root / WIRELESS_RELATIVE)
                        and receipt.get("role") == spec.get("role")
                        and all(receipt["launcher_identity"][k] == summary["coordinator_identity"][k]
                                for k in ("pid", "start_ticks")), "actual child wait receipt differs")
                absent(child["process_identity"])
            else:
                require(child.get("execution_kind") in ("aggregate", "fifo_manifest"), "unknown child wait")
        for job in declared["audits"]:
            value = completed["audits"].get(job["id"], {})
            require(not job.get("required", True) or value.get("passed") is True, "required audit absent")
            roles += job.get("role") is not None
        native_episodes = sorted(Path(declared["run_directory"]).glob("worker*/episode*/metadata.json"))
        require(len(native_episodes) == declared["expected_episodes"], "native episode inventory differs")
        for path in native_episodes:
            meta = read(path)
            require(meta.get("freeze") == freeze and meta.get("safety_contract") == CONTRACT
                    and meta.get("execution_phase_protocol") == "mr3-controlled-execution-phase-v2",
                    "episode source/contract differs")
            require(meta.get("seed_rule", "legacy") == plan.get("seed_rule", "legacy"),
                    "native episode seed rule differs from qualification plan")
            require(meta.get("start_graph_rule", "original-seed-cell") == plan.get("start_graph_rule", "original-seed-cell"),
                    "native episode start graph rule differs from qualification plan")
            require(meta.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE)
                    == plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE),
                    "native episode reach geometry rule differs from qualification plan")
            supervisor_meta = read(path.parent / "supervisor_metadata.json")
            require(supervisor_meta.get("seed_rule", "legacy") == plan.get("seed_rule", "legacy"),
                    "native supervisor seed rule differs from qualification plan")
            require(supervisor_meta.get("start_graph_rule", "original-seed-cell") == plan.get("start_graph_rule", "original-seed-cell"),
                    "native supervisor start graph rule differs from qualification plan")
            require(supervisor_meta.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE)
                    == plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE),
                    "native supervisor reach geometry rule differs from qualification plan")
            episodes.append({"directory": str(path.parent), "epoch": meta["epoch"]})
            files = sorted(p for p in path.parent.rglob("*") if p.is_file())
            episode_files[str(path.parent)] = [str(p.relative_to(path.parent)) for p in files]
            for artifact in files:
                spec = {"sha256": sha(artifact), "bytes": artifact.stat().st_size}
                require(bindings.setdefault(str(artifact.resolve()), spec) == spec,
                        "closed episode archive changed after scientific review")
    require(roles == 30 and len(episodes) == 12 and len({e["epoch"] for e in episodes}) == 12,
            "full scientific role/episode inventory differs")
    for path, spec in bindings.items():
        require(sha(path) == spec["sha256"] and Path(path).stat().st_size == spec["bytes"],
                "qualification input changed before verdict")
    for directory, names in episode_files.items():
        require(sorted(str(p.relative_to(directory)) for p in Path(directory).rglob("*") if p.is_file()) == names,
                "closed episode archive inventory changed before verdict")
    return {"freeze": freeze, "safety_contract": CONTRACT, "plan": str(plan_path.resolve()),
        "plan_sha256": sha(plan_path), "outer_wait": str(Path(outer_wait).resolve()),
        "mandatory_roles": roles, "episodes": episodes, "bindings": bindings,
        **({"reach_geometry_rule": plan["reach_geometry_rule"]}
           if plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) != BINARY_REACH_GEOMETRY_RULE else {}),
        "complete_closed_episode_file_inventories": episode_files,
        "saved_process_identities_gone": gone, "old_profile_credit_reused": False,
        "passed": True, "engineering_only": True, "policy_reliability_credit": False}


def qualify(plan_path, freeze, outer_wait, output, root=WORKSPACE):
    value = _qualification_evidence(plan_path, freeze, outer_wait, root)
    value["schema"] = QUALIFICATION_SCHEMA
    dump(output, value)
    return value


def validate_qualification(path, plan_path, freeze, root=WORKSPACE):
    value = json.loads(Path(path).read_text())
    require(value.get("schema") == QUALIFICATION_SCHEMA, "old/missing qualification schema")
    actual = _qualification_evidence(plan_path, freeze, value["outer_wait"], root)
    require(value == dict(actual, schema=QUALIFICATION_SCHEMA), "qualification receipt differs from actual evidence")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--qualify", type=Path, help="outer actual matrix wait receipt")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.qualify is not None:
        require(args.output is not None, "qualification needs exclusive --output")
        result = qualify(args.plan, args.freeze, args.qualify, args.output)
    else:
        require(args.output is None, "execution output is declared by sealed plan")
        result = execute_plan(args.plan, args.freeze)
    print(json.dumps({"passed": result["passed"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
