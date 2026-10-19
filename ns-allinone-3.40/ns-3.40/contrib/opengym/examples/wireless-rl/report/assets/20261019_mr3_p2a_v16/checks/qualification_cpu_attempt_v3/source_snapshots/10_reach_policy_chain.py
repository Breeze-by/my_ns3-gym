"""Finite reach-profile PPO stages with actual waits and independent closure.

This coordinator stays alive through strict native custody review. Its stage
receipt cannot claim final absence: a separate invocation, after a real outer
wait, supplies that proof. No child is signalled or retried on deadline/failure.
"""
import argparse
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

from . import native_custody, native_custody_reach as custody
from . import reach_preparation as preparation

WORKSPACE = preparation.WORKSPACE
WIRELESS = preparation.WIRELESS_RELATIVE
CONTRACT = "mr3-reach-v1"
SCHEMA = "mr3-reach-policy-stage-execution-v1"
OUTER_SCHEMA = "mr3-reach-outer-actual-wait-v1"
FINAL_SCHEMA = "mr3-reach-policy-stage-final-absence-v1"
STAGES = ("minimum", "pilot", "validation")
CAPS = {"minimum": Decimal("1800"), "pilot": Decimal("2905.9547395464029"), "validation": Decimal("9000")}
NATIVE_CAPS = {"minimum": Decimal("1150"), "pilot": Decimal("2100"), "validation": Decimal("8500")}
require, dump, sha, argument = preparation.require, preparation.dump, preparation.sha, preparation.argument


def decimal(value):
    require(type(value) in (str, int, float) and type(value) is not bool, "finite decimal scalar required")
    result = Decimal(str(value))
    require(result.is_finite(), "nonfinite decimal budget")
    return result


def _same_identity(left, right):
    return (type(left) is dict and type(right) is dict and type(left.get("pid")) is int
            and type(left.get("start_ticks")) is int and left["pid"] > 0 and left["start_ticks"] > 0
            and all(left[k] == right.get(k) for k in ("pid", "start_ticks")))


def _read(path, bindings):
    path = Path(path).resolve()
    raw = path.read_bytes()
    spec = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    require(bindings.setdefault(str(path), spec) == spec, "bound policy input changed: " + str(path))
    return json.loads(raw)


def _bind(path, bindings):
    path = Path(path).resolve()
    spec = {"sha256": sha(path), "bytes": path.stat().st_size}
    require(bindings.setdefault(str(path), spec) == spec, "bound policy artifact changed: " + str(path))
    return spec


def _verify_bindings(bindings):
    for path, spec in bindings.items():
        require(sha(path) == spec["sha256"] and Path(path).stat().st_size == spec["bytes"],
                "policy evidence changed before verdict: " + path)


def _report_bindings(value, bindings, workspace):
    """Retain actual independent-reader file proofs, including full raw inputs."""
    if type(value) is list:
        for child in value:
            _report_bindings(child, bindings, workspace)
    elif type(value) is dict:
        if type(value.get("path")) is str and re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", ""))):
            path = Path(value["path"])
            path = path if path.is_absolute() else Path(workspace) / path
            require(sha(path) == value["sha256"], "independent reader file proof changed: " + str(path))
            if "bytes" in value:
                require(path.stat().st_size == value["bytes"], "independent reader byte count changed")
            _bind(path, bindings)
        for key, child in value.items():
            if type(key) is str and Path(key).is_absolute() and type(child) is dict and "sha256" in child:
                require(sha(key) == child["sha256"], "independent reader raw binding changed: " + key)
                _bind(key, bindings)
            _report_bindings(child, bindings, workspace)


def stage_spec(plan, plan_path, qualification_path, stage):
    require(stage in STAGES and type(plan.get("policy_stages")) is dict
            and set(plan["policy_stages"]) == set(STAGES), "complete explicit policy stage registry required")
    spec = plan["policy_stages"][stage]
    require(type(spec) is dict and decimal(spec["wall_seconds"]) == CAPS[stage]
            and decimal(spec["tail_reserve_seconds"]) == 500, "policy stage/tail allocation differs")
    argv = spec["argv"]
    require(type(argv) is list and argv[:3] == [plan["learner_python"], "-m", "mr3_learning.ppo"]
            and all(type(v) is str for v in argv), "policy command is not the exact declared PPO entry")
    require(argument(argv, "--safety-contract") == CONTRACT
            and Path(argument(argv, "--reach-plan")).resolve() == Path(plan_path).resolve()
            and Path(argument(argv, "--reach-qualification")).resolve() == Path(qualification_path).resolve()
            and decimal(argument(argv, "--wall-seconds")) == NATIVE_CAPS[stage], "PPO admission/native cap differs")
    mode = argument(argv, "--mode")
    require(mode == ("evaluate" if stage == "validation" else "train"), "PPO phase mode differs")
    run = Path(spec["run_directory"]).resolve()
    require(Path(argument(argv, "--output-root")).resolve() / argument(argv, "--run-id") == run,
            "PPO run output differs from stage declaration")
    decisions, steps = int(argument(argv, "--decisions")), int(argument(argv, "--episode-steps"))
    require(1 <= steps <= 300 and decisions >= 2, "policy sampling bounds differ")
    if stage == "minimum":
        require(decisions == 16 and argument(argv, "--seed") == "41",
                "minimum requires the declared fresh seed41 sixteen native decisions")
    elif stage == "pilot":
        require(decisions <= 1870 and steps == 64, "pilot exceeds its original quota/declared external collection prefix")
    else:
        schedule = argument(argv, "--schedule").split(",")
        require(steps == 300 and decisions == 900 and schedule == ["open:401", "open:402", "open:403"],
                "final-only validation requires the original three open development seeds")
        require("--checkpoint" in argv, "validation needs the actual final pilot checkpoint")
    require(("--checkpoint" in argv) is (stage == "validation"), "training resumption/intermediate selection is undeclared")
    condition = spec["condition"]
    required = {"minimum": "matrix_qualification", "pilot": "minimum_complete", "validation": "pilot_complete"}[stage]
    keys = {"requires"} | (set() if stage == "minimum" else
        {"previous_stage_summary", "previous_stage_outer_wait", "previous_stage_final_absence"})
    require(type(condition) is dict and set(condition) == keys and condition["requires"] == required,
            "unknown/incomplete policy predecessor condition")
    output = Path(spec["output_directory"])
    require(output.is_absolute() and run.is_absolute() and output.resolve() != run,
            "policy evidence/run directories must be distinct absolute paths")
    return spec


def native_budget(spec, stage, started_ns, now_ns):
    """Only lower the declared native wall cap, leaving a real 500s tail."""
    elapsed = Decimal(now_ns - started_ns) / 10**9
    require(elapsed >= 0, "stage monotonic clock regressed")
    remaining = CAPS[stage] - elapsed
    effective = min(NATIVE_CAPS[stage], remaining - Decimal("500"))
    effective = effective.quantize(Decimal(".001"), rounding=ROUND_FLOOR)
    require(effective > 0, "stage deadline leaves no native budget after the reserved tail")
    argv = list(spec["argv"])
    argv[argv.index("--wall-seconds") + 1] = str(effective)
    return argv, {"stage_started_wall_monotonic_ns": started_ns, "derived_wall_monotonic_ns": now_ns,
        "elapsed_stage_seconds": str(elapsed), "remaining_stage_seconds": str(remaining),
        "declared_native_ceiling_seconds": str(NATIVE_CAPS[stage]), "tail_reserve_seconds": "500",
        "effective_native_seconds": str(effective), "original_argv": spec["argv"]}


def jobs_for_stage(plan, plan_path, qualification_path, spec, episodes):
    output, run = Path(spec["output_directory"]), Path(spec["run_directory"])
    def command(name, module, extra):
        destination = output / (name + "_result.json")
        return {"id": name, "required": True, "output": str(destination),
            "receipt": str(output / (name + "_command.json")), "console": str(output / (name + ".log")),
            "argv": [plan["learner_python"] if name == "full" else "/usr/bin/python3", "-m", module,
                     *map(str, extra), "--output", str(destination)]}
    full = command("full", "mr3_learning.audit_reach_ppo", (run, "--freeze", "{freeze}",
                   "--plan", Path(plan_path).resolve(), "--qualification", Path(qualification_path).resolve()))
    jobs = [full]
    leaves = []
    for index, episode in enumerate(episodes, 1):
        name = f"fifo_{index:03d}"
        jobs.append(command(name, "mr3_learning.audit_reach_peer_control", (episode, "--freeze", "{freeze}")))
        leaves.append({"id": name, "episode_directory": str(episode)})
    ids = [v["id"] for v in leaves]
    manifest = {"id": "fifo_manifest", "kind": "fifo_manifest", "required": True,
        "output": str(output / "fifo_manifest.json"), "members": ids, "depends_on": ids, "leaves": leaves}
    jobs.append(manifest)
    closure = command("closure", "mr3_learning.native_custody_reach", ("review", "--run-directory", run,
        "--freeze", "{freeze}", "--binding", plan["custody_binding"], "--capture", output / "live_custody.json",
        "--launch-receipt", output / "native_command.json", "--fifo-receipts", manifest["output"],
        "--expected-episodes", len(episodes)))
    closure["depends_on"] = ["fifo_manifest"]
    jobs.append(closure)
    return jobs


def watcher_job(plan, spec, freeze):
    output, run = Path(spec["output_directory"]), Path(spec["run_directory"])
    return {"id": "watcher", "required": True, "output": str(output / "live_custody.json"),
        "receipt": str(output / "watcher_command.json"), "console": str(output / "watcher.log"),
        "argv": ["/usr/bin/python3", "-m", "mr3_learning.native_custody_reach", "watch", "--run-directory", str(run),
                 "--freeze", freeze, "--binding", plan["custody_binding"], "--ready-file", str(output / "ready.json"),
                 "--stop-file", str(output / "stop.json"), "--output", str(output / "live_custody.json")]}


def native_job(spec, argv, allocation):
    output, run = Path(spec["output_directory"]), Path(spec["run_directory"])
    return {"id": "native", "argv": argv, "required": True, "output": str(run / "summary.json"),
        "receipt": str(output / "native_command.json"), "console": str(output / "native.log"),
        "result_pass_key": "completed", "budget_allocation": allocation,
        "result_scope": "native PPO completion only; independent scientific, live custody and external absence remain necessary"}


def policy_artifacts(run):
    run = Path(run)
    return sorted({p.resolve() for pattern in ("metadata.json", "summary.json", "initial.zip", "final.zip",
        "checkpoint_*.zip", "rollout_*.npz", "rollout_*.json", "resources.json") for p in run.glob(pattern)})


def closed_episode_artifacts(episodes):
    """Exact closed native files, including observation maps and manifests."""
    return sorted({p.absolute() for episode in episodes for p in Path(episode).rglob("*") if p.is_file()})


def check_native_result(stage, metadata, native, audit, episodes, spec):
    """No ``completed`` boolean substitutes for eligible samples or real audits."""
    require(metadata.get("safety_contract") == native.get("safety_contract") == CONTRACT
            and metadata.get("mode") == native.get("mode") == ("evaluate" if stage == "validation" else "train")
            and native.get("completed") is True and native.get("error") is None
            and native.get("cleanup_errors") == [] and native.get("native_accounting_errors") == [],
            "native PPO result is incomplete/ineligible")
    require(audit.get("schema") == "mr3-reach-ppo-offline-audit-v1" and audit.get("safety_contract") == CONTRACT
            and audit.get("passed") is True and audit.get("errors") == []
            and audit.get("native_attempts") == len(episodes), "complete independent PPO audit required")
    listed = [Path(row["directory"]).resolve() for row in native["native_attempts"]]
    require(len(listed) == len(set(listed)) and set(listed) == set(episodes)
            and {Path(row["directory"]).resolve() for row in native["episodes"]} == set(episodes)
            and len(native["episodes"]) == len(episodes), "native attempt/eligible episode inventory differs")
    require(all(row.get("training_eligibility", {}).get("training_eligible") is True for row in native["episodes"]),
            "every closed episode requires its actual training-eligibility receipt")
    decisions = native.get("decisions")
    require(type(decisions) is int and decisions == native.get("closed_episode_decisions")
            == native.get("native_recorded_decisions") == sum(row["decisions"] for row in native["episodes"])
            and native.get("api_records") == native.get("native_api_records")
            == sum(row["api_records"] for row in native["episodes"]), "eligible/native decision accounting differs")
    updates = native.get("optimizer_updates")
    require(type(updates) is int, "typed optimizer update count required")
    if stage == "minimum":
        require(decisions == 16 and updates > 0, "minimum needs sixteen eligible decisions and positive real updates")
    elif stage == "pilot":
        require(2 <= decisions <= int(argument(spec["argv"], "--decisions")) <= 1870 and updates > 0,
                "pilot exceeds original quota or lacks positive eligible updates")
    else:
        require(updates == 0 and native.get("schedule_completed") is True and len(episodes) == 3
                and metadata.get("schedule") == [["open", 401], ["open", 402], ["open", 403]]
                and [(row.get("scene"), row.get("seed")) for row in native["episodes"]]
                    == [("open", 401), ("open", 402), ("open", 403)]
                and audit.get("task_successes") == 3 and audit.get("task_failures") == [],
                "final-only validation requires all three original open seeds strict successes and zero updates")
    return {"eligible_decisions": decisions, "api_records": native["api_records"], "optimizer_updates": updates,
            "native_attempts": len(episodes), "strict_task_successes": audit.get("task_successes")}


def _validate_predecessor(plan, plan_path, qualification_path, freeze, stage, workspace):
    spec = stage_spec(plan, plan_path, qualification_path, stage)
    if stage == "minimum":
        return None
    previous = "minimum" if stage == "pilot" else "pilot"
    condition = spec["condition"]
    expected_summary = Path(plan["policy_stages"][previous]["output_directory"]) / "summary.json"
    require(Path(condition["previous_stage_summary"]).resolve() == expected_summary.resolve(),
            "predecessor summary is from another policy stage")
    actual = stage_evidence(plan_path, freeze, previous, condition["previous_stage_outer_wait"], workspace)
    recorded = json.loads(Path(condition["previous_stage_final_absence"]).read_text())
    require(recorded == actual and recorded.get("passed") is True, "predecessor lacks exact independent final closure")
    if stage == "validation":
        checkpoint = Path(plan["policy_stages"]["pilot"]["run_directory"]).resolve() / "final.zip"
        require(Path(argument(spec["argv"], "--checkpoint")).resolve() == checkpoint
                and sha(checkpoint) == recorded["final_checkpoint"]["sha256"], "validation selected another/intermediate checkpoint")
    return {"stage": previous, "final_absence": str(Path(condition["previous_stage_final_absence"]).resolve()),
            "sha256": sha(condition["previous_stage_final_absence"]), "checkpoint": actual["final_checkpoint"]}


def execute_stage(plan_path, freeze, qualification_path, stage, workspace=WORKSPACE):
    started_ns = time.monotonic_ns()
    workspace, plan_path, qualification_path = map(lambda p: Path(p).resolve(), (workspace, plan_path, qualification_path))
    plan = preparation.load_plan(plan_path, workspace)
    spec = stage_spec(plan, plan_path, qualification_path, stage)
    output, run = Path(spec["output_directory"]), Path(spec["run_directory"])
    require(not output.exists() and not run.exists(), "policy output/run already exists; no retry/overwrite")
    preparation.source_check(plan, plan_path, freeze, workspace, require_clean=True)
    qualification = preparation.validate_qualification(qualification_path, plan_path, freeze, root=workspace)
    predecessor = _validate_predecessor(plan, plan_path, qualification_path, freeze, stage, workspace)
    executor, executor_proof = preparation.load_executor()
    output.mkdir(parents=True, exist_ok=False)
    bindings = {}
    _read(plan_path, bindings); _read(qualification_path, bindings)
    coordinator = preparation.primitives.identity(os.getpid())
    require(coordinator is not None and coordinator["state"] != "Z", "actual stage coordinator identity unavailable")
    deadline_ns = started_ns + int(CAPS[stage] * 10**9)
    ledger = output / "ledger.jsonl"
    ledger_stream = ledger.open("x")
    ledger_lock = threading.Lock()
    def record(**value):
        with ledger_lock:
            ledger_stream.write(json.dumps({"wall_monotonic_ns": time.monotonic_ns(), **value}, allow_nan=False) + "\n")
            ledger_stream.flush()
    runner = executor.Runner(output, workspace / WIRELESS, freeze, sha(plan_path), record)
    watch_spec = watcher_job(plan, spec, freeze)
    watch, native_value, watch_value = None, None, None
    watch_submitted = native_submitted = False
    audits, skipped, jobs, episodes, errors, allocation = {}, [], [], [], [], None
    scientific, artifact_paths, episode_paths = None, [], []
    try:
        require(time.monotonic_ns() < deadline_ns, "stage deadline exhausted before watcher submission")
        watch_submitted = True
        watch = runner.spawn(watch_spec)
        try:
            ready_deadline = min(deadline_ns, time.monotonic_ns() + 30_000_000_000)
            while True:
                require(watch["process"] is not None and watch["process"].poll() is None, "watcher exited before readiness")
                require(time.monotonic_ns() < ready_deadline, "custody watcher readiness timeout")
                ready_path = output / "ready.json"
                if ready_path.exists() and ready_path.read_bytes().endswith(b"\n"):
                    ready = custody.read_ready_receipt(custody.Reader(), ready_path, freeze, sha(plan["custody_binding"]))
                    require(_same_identity(ready["watcher_identity"], watch["value"]["process_identity"]),
                            "ready receipt borrows another watcher identity")
                    break
                time.sleep(.05)
            argv, allocation = native_budget(spec, stage, started_ns, time.monotonic_ns())
            native_submitted = True
            native_value = runner.command(native_job(spec, argv, allocation))
        except BaseException as error:
            errors.append(repr(error))
        finally:
            if native_value is not None and native_value["execution_kind"] == "subprocess_waited":
                stop = {"schema": custody.SCHEMA_STOP, "safety_contract": CONTRACT, "freeze": freeze,
                    "launch_receipt": {"path": native_value["receipt"], "sha256": sha(native_value["receipt"])}}
            else:
                stop = {"schema": custody.SCHEMA_STOP, "safety_contract": CONTRACT, "freeze": freeze,
                    "native_not_started": True, "reason": "watcher_ready_timeout" if any("readiness timeout" in e for e in errors)
                    else "pre_native_admission_failure"}
            dump(output / "stop.json", stop)
            watch_value = runner.finish(watch)
        episodes = native_custody.episode_directories(run) if run.exists() else []
        if native_value is not None and native_value["passed"] and watch_value["passed"] and not errors:
            require(episodes, "completed PPO has no actual Supervisor episodes")
            jobs = jobs_for_stage(plan, plan_path, qualification_path, spec, episodes)
            audits, skipped = executor.run_audits(jobs, runner, deadline_ns)
        else:
            skipped = [{"id": "full/episode_FIFO/strict_custody", "reason": "native_or_watcher_not_passed", "status": "SKIPPED"}]
        episode_paths = closed_episode_artifacts(episodes)
        for path in episode_paths:
            _bind(path, bindings)
        for child in [native_value, watch_value, *audits.values()]:
            if child is None:
                continue
            for key in ("receipt", "console"):
                if child.get(key) and Path(child[key]).exists():
                    _bind(child[key], bindings)
            if Path(child["output"]).exists():
                report = _read(child["output"], bindings)
                if child.get("output_sha256"):
                    require(sha(child["output"]) == child["output_sha256"], "child output changed after real wait")
                _report_bindings(report, bindings, workspace)
        artifact_paths = policy_artifacts(run)
        for path in artifact_paths:
            _bind(path, bindings)
        native_summary, native_metadata = None, None
        if native_value is not None and native_value["passed"] and audits.get("full", {}).get("passed"):
            native_summary = _read(run / "summary.json", bindings)
            native_metadata = _read(run / "metadata.json", bindings)
            full = _read(audits["full"]["output"], bindings)
            scientific = check_native_result(stage, native_metadata, native_summary, full, episodes, spec)
            require(native_metadata["freeze"] == native_summary["freeze"] == freeze
                    and native_metadata["reach_plan_sha256"] == sha(plan_path)
                    and native_metadata["reach_qualification_sha256"] == sha(qualification_path)
                    and native_metadata["command"] == native_value["argv"],
                    "PPO admission metadata changed plan/qualification/freeze")
            final = run / "final.zip"
            require(final.stat().st_size > 0 and sha(final) == native_summary["final_checkpoint_sha256"],
                    "completed native final checkpoint changed")
            _bind(final, bindings)
        preparation.source_check(plan, plan_path, freeze, workspace, require_clean=False)
        _verify_bindings(bindings)
    except BaseException as error:
        errors.append(repr(error))
    finally:
        # Runner.command/run_audits always drain submitted processes. The only
        # persistent child, watcher, is closed in the inner finally above.
        ledger_stream.close()
    for path in (ledger, output / "ready.json", output / "stop.json"):
        if path.exists():
            _bind(path, bindings)
    ended_ns = time.monotonic_ns()
    passed = (not errors and native_value is not None and native_value["passed"] and watch_value is not None
        and watch_value["passed"] and scientific is not None and not skipped and bool(jobs)
        and all(audits.get(job["id"], {}).get("passed") is True for job in jobs)
        and ended_ns <= deadline_ns)
    result = {"schema": SCHEMA, "safety_contract": CONTRACT, "freeze": freeze, "stage": stage,
        "plan": str(plan_path), "plan_sha256": sha(plan_path), "qualification": str(qualification_path),
        "qualification_sha256": sha(qualification_path), "coordinator_identity": coordinator,
        "coordinator_actual_argv": [p.decode(errors="replace") for p in Path("/proc/self/cmdline").read_bytes().split(b"\0") if p],
        "run_directory": str(run), "output_directory": str(output), "native": native_value, "watcher": watch_value,
        "audits": audits, "jobs": jobs, "actual_episode_directories": list(map(str, episodes)),
        "skipped_audits": skipped, "errors": errors, "scientific_result": scientific,
        "started_wall_monotonic_ns": started_ns, "ended_wall_monotonic_ns": ended_ns,
        "wall_seconds": str(Decimal(ended_ns - started_ns) / 10**9), "wall_allocation_seconds": str(CAPS[stage]),
        "within_stage_wall_allocation": ended_ns <= deadline_ns, "native_budget_allocation": allocation,
        "all_submitted_children_waited": ((not watch_submitted or (watch is not None
            and (watch["process"] is None or watch["process"].poll() is not None)))
            and (not native_submitted or native_value is not None)
            and all(v.get("execution_kind") in ("subprocess_waited", "not_spawned", "fifo_manifest")
                    for v in audits.values())),
        "final_external_absence_required": True,
        "overall_claim": False, "external_actual_accounting_required": True,
        "passed": passed, "predecessor": predecessor, "bindings": bindings,
        "policy_artifact_paths": list(map(str, artifact_paths)),
        "closed_episode_file_paths": list(map(str, episode_paths)),
        "executor_projection": executor_proof, "qualification_schema": qualification["schema"],
        "old_profile_credit_reused": False}
    dump(output / "summary.json", result)
    return result


def _saved_identities(value):
    if type(value) is dict:
        if type(value.get("pid")) is int and type(value.get("start_ticks")) is int:
            require(value["pid"] > 0 and value["start_ticks"] > 0, "invalid saved PID/start")
            yield value
        for child in value.values():
            yield from _saved_identities(child)
    elif type(value) is list:
        for child in value:
            yield from _saved_identities(child)


def check_waited_child(child, spec, freeze, plan_sha, coordinator, coordinator_argv, workspace, bindings):
    """Recompute the actual Runner predicate and exact command binding."""
    receipt = _read(child["receipt"], bindings)
    expected_argv = [freeze if value == "{freeze}" else value for value in spec["argv"]]
    require(receipt == child and receipt.get("schema") == custody.SCHEMA_WAIT
            and receipt.get("safety_contract") == CONTRACT and receipt.get("freeze") == freeze
            and receipt.get("plan_sha256") == plan_sha and receipt.get("id") == spec["id"]
            and receipt.get("role") == spec.get("role") and receipt.get("required") == spec.get("required", True)
            and receipt.get("argv") == receipt.get("command_argv") == expected_argv
            and receipt.get("cwd") == str(Path(workspace) / WIRELESS)
            and receipt.get("output") == spec["output"] and receipt.get("receipt") == spec["receipt"]
            and receipt.get("console") == spec["console"]
            and receipt.get("result_pass_key") == spec.get("result_pass_key", "passed")
            and receipt.get("launcher_identity_scope") == "persistent_coordinator_not_native_owned"
            and _same_identity(receipt.get("launcher_identity"), coordinator)
            and receipt.get("coordinator_identity") == receipt.get("launcher_identity")
            and receipt.get("coordinator_actual_argv") == coordinator_argv,
            "submitted command actual wait/spec binding differs")
    if child["execution_kind"] == "subprocess_waited":
        require(type(child.get("returncode")) is int and _same_identity(child.get("process_identity"), child.get("benchmark_parent"))
                and child["process_identity"]["parent"] == coordinator["pid"], "actual child wait/PID/parent missing")
    else:
        require(child["execution_kind"] == "not_spawned" and child.get("returncode") is None
                and not child.get("process_identity"), "unstarted child has fabricated returncode/identity")
    result = _read(child["output"], bindings) if Path(child["output"]).exists() else None
    actual_passed = (child.get("errors") == [] and child.get("returncode") == 0 and type(result) is dict
        and result.get(spec.get("result_pass_key", "passed")) is True and result.get("freeze", freeze) == freeze)
    require(child.get("passed") is actual_passed, "child saved passed differs from actual rc/errors/result")
    if result is not None:
        require(sha(child["output"]) == child.get("output_sha256"), "waited child result SHA changed")
    if Path(child["console"]).exists():
        _bind(child["console"], bindings)
    else:
        require(child["execution_kind"] == "not_spawned", "started child console evidence missing")
    return result


def stage_evidence(plan_path, freeze, stage, outer_wait, workspace=WORKSPACE):
    """Recheck exact closed-stage artifacts and all saved identities, no rerun."""
    workspace, plan_path = Path(workspace).resolve(), Path(plan_path).resolve()
    plan = preparation.load_plan(plan_path, workspace)
    bindings = {}
    spec = plan["policy_stages"][stage]
    summary = _read(Path(spec["output_directory"]) / "summary.json", bindings)
    qualification_path = Path(summary["qualification"])
    stage_spec(plan, plan_path, qualification_path, stage)
    preparation.source_check(plan, plan_path, freeze, workspace, require_clean=False)
    preparation.validate_qualification(qualification_path, plan_path, freeze, root=workspace)
    _read(plan_path, bindings); _read(qualification_path, bindings)
    require(summary.get("schema") == SCHEMA and summary.get("safety_contract") == CONTRACT
            and summary.get("freeze") == freeze and summary.get("stage") == stage
            and summary.get("plan_sha256") == sha(plan_path)
            and summary.get("qualification_sha256") == sha(qualification_path)
            and summary.get("all_submitted_children_waited") is True
            and summary.get("final_external_absence_required") is True and summary.get("overall_claim") is False,
            "policy stage summary lacks exact actual-wait scope")
    outer = _read(outer_wait, bindings)
    require(outer.get("schema") == OUTER_SCHEMA and outer.get("safety_contract") == CONTRACT
            and outer.get("scope") == ("engineering" if stage == "minimum" else stage)
            and outer.get("actual_waited") is True and outer.get("errors") == []
            and type(outer.get("actual_returncode")) is int
            and outer["actual_returncode"] == (0 if summary["passed"] else 1)
            and outer.get("source_unchanged") is True and _same_identity(outer.get("child_identity"), summary["coordinator_identity"]),
            "policy outer actual wait identity/returncode differs")
    require(outer.get("passed") is (summary["passed"] is True)
            and outer.get("source_before") == outer.get("source_after")
            and type(outer.get("source_before")) is list, "outer actual result/source stability differs")
    outer_sources = {Path(row["path"]).resolve(): row for row in outer["source_before"]}
    require({plan_path, Path(__file__).resolve()} <= outer_sources.keys(), "outer wait did not bind plan and this policy coordinator source")
    _report_bindings(outer["source_before"], bindings, workspace)
    argv = outer["actual_argv"]
    require(argv[:3] == [plan["learner_python"], "-m", "mr3_learning.reach_policy_chain"]
            and argv == summary["coordinator_actual_argv"]
            and Path(argument(argv, "--plan")).resolve() == plan_path
            and argument(argv, "--freeze") == freeze and argument(argv, "--stage") == stage
            and Path(argument(argv, "--qualification")).resolve() == qualification_path.resolve()
            and "--finalize-outer-wait" not in argv, "outer wait is for another policy invocation")
    require(type(outer.get("started_monotonic_ns")) is int
            and type(outer.get("ended_monotonic_ns")) is int
            and outer["started_monotonic_ns"] <= summary["started_wall_monotonic_ns"]
            <= summary["ended_wall_monotonic_ns"] <= outer["ended_monotonic_ns"],
            "outer actual wait does not enclose complete stage")
    outer_wall = Decimal(outer["ended_monotonic_ns"] - outer["started_monotonic_ns"]) / 10**9
    require(outer_wall >= 0 and decimal(outer["actual_child_wait_seconds"]) == outer_wall, "outer wall clock/accounting differs")
    _verify_bindings(summary["bindings"])
    bindings.update(summary["bindings"])
    require(list(map(str, policy_artifacts(spec["run_directory"]))) == summary["policy_artifact_paths"],
            "policy checkpoint/rollout artifact inventory changed after scientific audit")
    require(summary["predecessor"] == _validate_predecessor(plan, plan_path, qualification_path, freeze, stage, workspace),
            "policy predecessor evidence changed since admission")
    identities = [summary["coordinator_identity"], outer["coordinator_identity"]]
    children = [summary["native"], summary["watcher"], *summary["audits"].values()]
    actual_episodes = native_custody.episode_directories(Path(spec["run_directory"]))
    require(list(map(str, actual_episodes)) == summary["actual_episode_directories"], "attempt inventory changed after stage exit")
    require(list(map(str, closed_episode_artifacts(actual_episodes))) == summary["closed_episode_file_paths"],
            "closed episode file inventory changed after scientific audit")
    require(all(str(path.resolve()) in summary["bindings"] for path in closed_episode_artifacts(actual_episodes)),
            "closed native/observation archive file lacks actual byte binding")
    expected_jobs = jobs_for_stage(plan, plan_path, qualification_path, spec, actual_episodes) if summary["jobs"] else []
    require(summary["jobs"] == expected_jobs and set(summary["audits"]) <= {j["id"] for j in expected_jobs},
            "policy scientific command registry changed")
    child_specs = {j["id"]: j for j in expected_jobs}
    child_specs["watcher"] = watcher_job(plan, spec, freeze)
    if summary["native"] is not None:
        allocation = summary["native_budget_allocation"]
        effective, derived = native_budget(spec, stage, summary["started_wall_monotonic_ns"], allocation["derived_wall_monotonic_ns"])
        require(allocation == derived, "native budget derivation changed")
        child_specs["native"] = native_job(spec, effective, derived)
    for child in children:
        if child is None:
            continue
        if child.get("execution_kind") in ("subprocess_waited", "not_spawned"):
            result = check_waited_child(child, child_specs[child["id"]], freeze, sha(plan_path), summary["coordinator_identity"],
                summary["coordinator_actual_argv"], workspace, bindings)
            if child.get("execution_kind") == "subprocess_waited":
                identities.append(child["process_identity"])
        elif child.get("execution_kind") == "fifo_manifest":
            job = child_specs[child["id"]]
            members = [{"id": name, "path": summary["audits"][name]["output"],
                "sha256": summary["audits"][name]["output_sha256"], "passed": summary["audits"][name]["passed"],
                "returncode": summary["audits"][name]["returncode"],
                "execution_kind": summary["audits"][name]["execution_kind"]} for name in job["members"]]
            require(child.get("members") == members and child.get("output") == job["output"]
                    and child.get("passed") is all(member["passed"] for member in members), "FIFO aggregate result differs")
            result = _read(child["output"], bindings)
            expected_manifest = [{"episode_directory": leaf["episode_directory"], "path": member["path"], "sha256": member["sha256"]}
                                 for leaf, member in zip(job["leaves"], members)]
            require(result == expected_manifest and sha(child["output"]) == child.get("output_sha256"), "FIFO manifest input/leaf set changed")
        else:
            require(summary["passed"] is False and child.get("execution_kind") == "runner_error", "unknown submitted execution kind")
            result = None
        if child.get("id") == "watcher" and result is not None:
            identities.extend(_saved_identities(result.get("episodes", [])))
    for episode in actual_episodes:
        saved = _read(episode / "supervisor_metadata.json", bindings)
        identities.append(saved["worker_identity"])
        shutdown = _read(episode / "supervisor_shutdown.json", bindings)
        identities.extend(shutdown["owned_processes_seen"])
    unique = {(i["pid"], i["start_ticks"]): i for i in identities}
    gone = []
    for identity in unique.values():
        current = preparation.primitives.identity(identity["pid"])
        absent = current is None or current["start_ticks"] != identity["start_ticks"]
        require(absent, "saved policy identity remains present, including zombie: " + str(identity["pid"]))
        gone.append({"saved": identity, "gone": True})
    scientific, checkpoint, strict_closed = None, None, False
    if summary["audits"].get("closure") is not None:
        closure = _read(summary["audits"]["closure"]["output"], bindings)
        strict_closed = (closure.get("schema") == custody.SCHEMA_CLOSURE and closure.get("safety_contract") == CONTRACT
                         and closure.get("passed") is True and closure.get("errors") == [] and closure.get("all_native_owned_gone") is True)
    if summary["passed"]:
        require(not summary["errors"] and not summary["skipped_audits"] and summary["within_stage_wall_allocation"] is True,
                "stage falsely claims complete scientific execution")
        jobs = jobs_for_stage(plan, plan_path, qualification_path, spec, actual_episodes)
        require(summary["jobs"] == jobs and set(summary["audits"]) == {j["id"] for j in jobs}
                and all(v.get("passed") is True for v in summary["audits"].values()), "required scientific job inventory differs")
        native = _read(Path(spec["run_directory"]) / "summary.json", bindings)
        metadata = _read(Path(spec["run_directory"]) / "metadata.json", bindings)
        full = _read(summary["audits"]["full"]["output"], bindings)
        scientific = check_native_result(stage, metadata, native, full, actual_episodes, spec)
        require(strict_closed, "native strict custody closure did not pass")
        allocation = summary["native_budget_allocation"]
        effective, derived = native_budget(spec, stage, summary["started_wall_monotonic_ns"], allocation["derived_wall_monotonic_ns"])
        require(allocation == derived and summary["native"]["argv"] == effective,
                "native effective wall cap was not the declared downward derivation")
        final_path = Path(spec["run_directory"]) / "final.zip"
        require(final_path.stat().st_size > 0 and sha(final_path) == native["final_checkpoint_sha256"], "final-only checkpoint changed")
        checkpoint = {"path": str(final_path), **_bind(final_path, bindings)}
    _verify_bindings(bindings)
    return {"schema": FINAL_SCHEMA, "safety_contract": CONTRACT, "freeze": freeze, "stage": stage,
        "plan_sha256": sha(plan_path), "summary": str(Path(spec["output_directory"]) / "summary.json"),
        "summary_sha256": sha(Path(spec["output_directory"]) / "summary.json"),
        "outer_wait": str(Path(outer_wait).resolve()), "outer_wait_sha256": sha(outer_wait),
        "actual_outer_wall_seconds": str(outer_wall), "within_stage_wall_allocation": outer_wall <= CAPS[stage],
        "all_saved_identities_gone": True, "identities": gone, "strict_custody_passed": strict_closed,
        "scientific_result": scientific, "final_checkpoint": checkpoint, "bindings": bindings,
        "external_actual_fee_accounting_required": True, "old_profile_credit_reused": False,
        "passed": summary["passed"] is True and strict_closed and outer_wall <= CAPS[stage]}


def finalize_stage(plan_path, freeze, stage, outer_wait, output, workspace=WORKSPACE):
    require(not Path(output).exists(), "final policy absence output exists; preserve original")
    value = stage_evidence(plan_path, freeze, stage, outer_wait, workspace)
    dump(output, value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--finalize-outer-wait", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.finalize_outer_wait is not None:
        require(args.output is not None, "external finalization needs exclusive --output")
        result = finalize_stage(args.plan, args.freeze, args.stage, args.finalize_outer_wait, args.output)
    else:
        require(args.qualification is not None and args.output is None, "execution needs qualification and plan-declared output")
        result = execute_stage(args.plan, args.freeze, args.qualification, args.stage)
    print(json.dumps({"passed": result["passed"], "stage": args.stage, "schema": result["schema"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
