"""Outer PPO evidence orchestration only; imports no ROS, policy or mathematics.

Uses the frozen preparation Runner and existing native/independent consumers.
This /tmp tool is separately SHA-bound evidence, never a claim of Git identity.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

# Source-only checkout import for this standalone /tmp evidence tool. No ROS or
# conda paths are added, and child Runner environments still discard PYTHONPATH.
sys.path.insert(0, "/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl")
from mr3_learning import native_custody as custody
from mr3_learning import preparation as prep

ROOT = prep.WORKSPACE
WIRELESS = ROOT / prep.WIRELESS_RELATIVE
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
SCHEMA = "mr3-p2a-ppo-phase-execution-v1"
OUTER = "mr3-p2a-ppo-phase-actual-outer-wait-v1"
FINAL = "mr3-p2a-ppo-phase-final-absence-v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs_reader():
    read = custody.Reader()
    return read, lambda path: custody.parse(read(path))


def check_prerequisites(args, plan, read, js):
    prior, final = js(args.prior_summary), js(args.prior_final_closure)
    require(prior["freeze"] == final["freeze"] == args.freeze
            and prior.get("passed") is True and final.get("passed") is True
            and final.get("all_saved_identities_gone") is True,
            "prior phase and its real external final absence must both pass")
    if args.phase == "minimum":
        require(prior["schema"] == "mr3-preparation-execution-v1"
                and final["schema"] == "mr3-p2a-v9-final-coordinator-closure-v1"
                and prior["original_mandatory_roles"] == 34 and prior["additional_cadence_roles"] == 4
                and [s["stage"] for s in prior["stages"]] == list(prep.STAGES)
                and all(s.get("passed") is True for s in prior["stages"]),
                "minimum requires the complete four-stage38-role matrix")
    else:
        previous = "minimum" if args.phase == "pilot" else "pilot"
        require(prior["schema"] == SCHEMA and prior["phase"] == previous
                and final["schema"] == FINAL and final["phase"] == previous,
                "PPO phase order/final-absence schema differs")
    previous_binding = final["inputs"][str(args.prior_summary.resolve())]
    require(previous_binding["sha256"] == digest(args.prior_summary),
            "prior external closure did not bind this exact prior summary")
    balance = js(args.balance)
    phase = plan["ppo"][args.phase]
    require(balance["schema"] == "mr3-p2a-external-accounted-balance-v1"
            and balance["freeze"] == args.freeze and balance["for_phase"] == args.phase
            and balance["budget_pool"] == phase["budget_pool"]
            and type(balance["accounted_through_wall_monotonic_ns"]) is int
            and balance["accounted_through_wall_monotonic_ns"] >= final["wall_monotonic_ns"],
            "actual external balance must follow the prior final closure")
    available = Decimal(balance["available_wall_seconds"])
    require(available >= Decimal(phase["total_phase_wall_allocation_seconds"])
            and balance["basis"], "insufficient declared pool or missing actual accounting basis")
    for spec in balance["basis"]:
        require(hashlib.sha256(read(spec["path"])).hexdigest() == spec["sha256"],
                "external actual balance basis changed")
    if args.phase == "pilot":
        require(type(balance["available_decisions"]) is int
                and balance["available_decisions"] == phase["remaining_decisions"] == 1870
                and available <= Decimal("2905.9547395464029"), "original pilot balance changed")
    if args.phase == "validation":
        checkpoint = Path(prep.argument(phase["command"], "--checkpoint")).resolve()
        require(checkpoint == Path(prior["run_directory"]).resolve() / "final.zip"
                and digest(checkpoint) == prior["ppo_summary"]["final_checkpoint_sha256"]
                and available <= Decimal(phase["total_phase_wall_allocation_seconds"]),
                "validation must use the successful new pilot final checkpoint and original pool")
    return phase, balance


def check_ppo_counts(phase, summary, metadata, full=None):
    require(summary.get("completed") is True and summary.get("error") is None
            and summary.get("cleanup_errors") == [] and summary.get("native_accounting_errors") == [],
            "PPO did not complete with genuine clean receipts")
    require(summary["decisions"] == summary["collector_observed_decisions"]
            == summary["native_recorded_decisions"]
            and summary["api_records"] == summary["collector_observed_api_records"],
            "returned/native actor counts differ")
    if phase == "minimum":
        require(summary["decisions"] == 16 and summary["quota_reached"] is True
                and summary["optimizer_updates"] > 0, "minimum requires16 real decisions and actual updates")
    elif phase == "pilot":
        require(2 <= summary["decisions"] <= 1870 and summary["optimizer_updates"] > 0
                and metadata.get("checkpoint") is None, "pilot quota/from-scratch contract differs")
    else:
        require(summary["optimizer_updates"] == 0 and summary["schedule_completed"] is True
                and len(summary["episodes"]) == 3, "validation schedule/optimizer differs")
        if full is not None:
            require(full["task_successes"] == 3 and full["task_failures"] == [],
                    "validation did not achieve all three original95% tasks")


def run(args):
    started = time.monotonic_ns()
    args.evidence.mkdir(parents=True, exist_ok=False)
    result = {"schema": SCHEMA, "phase": args.phase, "freeze": args.freeze,
              "passed": False, "errors": [], "coordinator_identity": prep.identity(os.getpid()),
              "coordinator_actual_argv": [x.decode() for x in Path("/proc/self/cmdline").read_bytes().split(b"\0") if x],
              "tool": {"path": str(Path(__file__).resolve()), "sha256": digest(__file__)},
              "started_wall_monotonic_ns": started, "final_external_coordinator_absence_required": True,
              "overall_pass_claimed": False, "signals_sent": 0}
    read, js = inputs_reader()
    with (args.evidence / "ledger.jsonl").open("x") as ledger:
        def record(**value):
            ledger.write(json.dumps({"wall_monotonic_ns": time.monotonic_ns(), **value}) + "\n")
            ledger.flush()
        try:
            plan = js(args.plan)
            plan_sha = digest(args.plan)
            result["plan_sha256"] = plan_sha
            frozen = subprocess.check_output(["git", "show", args.freeze + ":" + str(args.plan.resolve().relative_to(ROOT))], cwd=ROOT)
            require(hashlib.sha256(frozen).hexdigest() == plan_sha, "plan differs from freeze")
            require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == args.freeze
                    and subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip() == args.freeze
                    and not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True),
                    "PPO requires the clean pushed matrix source freeze")
            require("MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE" not in os.environ, "PPO forbids diagnostic physics env")
            phase, balance = check_prerequisites(args, plan, read, js)
            require(js(args.prior_summary)["plan_sha256"] == plan_sha,
                    "prior gates belong to a different sealed plan")
            result["budget_pool"], result["opening_external_balance"] = phase["budget_pool"], balance
            cap_ns = int(Decimal(phase["total_phase_wall_allocation_seconds"]) * 10**9)
            command = phase["command"]
            run_id = prep.argument(command, "--run-id")
            output_root = Path(prep.argument(command, "--output-root")) if "--output-root" in command else ROS / "log/mr3_ppo"
            run_directory = (output_root / run_id).resolve()
            require(not run_directory.exists(), "existing PPO run must never be replayed/overwritten")
            result["run_directory"] = str(run_directory)
            binding = prep.argument(plan["stages"][0]["watcher"]["argv"], "--binding")
            runner = prep.Runner(args.evidence, WIRELESS, args.freeze, plan_sha, record)
            ready, stop, capture = [args.evidence / name for name in ("custody_ready.json", "custody_stop.json", "live_custody.json")]
            watch = runner.spawn({"id": "watcher", "output": str(capture), "argv": ["/usr/bin/python3", "-B", "-m", "mr3_learning.native_custody", "watch", "--run-directory", str(run_directory), "--freeze", args.freeze, "--binding", binding, "--ready-file", str(ready), "--stop-file", str(stop), "--output", str(capture)]})
            native = None
            try:
                limit = time.monotonic() + 30
                while True:
                    require(watch["process"] is not None and watch["process"].poll() is None, "watcher exited before ready")
                    require(time.monotonic() < limit, "watcher ready timeout")
                    if ready.exists() and ready.read_bytes().endswith(b"\n"):
                        value = custody.read_ready_receipt(custody.Reader(), ready, args.freeze, digest(binding))
                        require(all(value["watcher_identity"][k] == watch["value"]["process_identity"][k] for k in ("pid", "start_ticks")), "ready came from another watcher")
                        break
                    time.sleep(.05)
                require(started + cap_ns - time.monotonic_ns() > int(Decimal(phase["collector_soft_wall_seconds"]) * 10**9), "phase reserve exhausted before native admission")
                native = runner.command({"id": "native", "output": str(run_directory / "summary.json"), "argv": command, "result_pass_key": "completed", "result_scope": "Actual PPO wait only; quota, all independent gates and final absence remain mandatory"})
            finally:
                if native is not None and native["execution_kind"] == "subprocess_waited":
                    boundary = {"schema": "mr3-native-custody-stop-v1", "freeze": args.freeze, "launch_receipt": {"path": native["receipt"], "sha256": digest(native["receipt"])}}
                else:
                    boundary = {"schema": "mr3-native-custody-stop-v1", "freeze": args.freeze, "native_not_started": True, "reason": "pre_native_admission_failure"}
                prep.dump(stop, boundary)
                result["watcher"] = runner.finish(watch)
                result["native"] = native
            require(native is not None and native["passed"] and result["watcher"]["passed"], "native/watch failed; no later phase admission")
            summary, metadata = js(run_directory / "summary.json"), js(run_directory / "metadata.json")
            result["ppo_summary"] = summary
            require(summary["freeze"] == metadata["freeze"] == args.freeze, "PPO source freeze differs")
            check_ppo_counts(args.phase, summary, metadata)
            episodes = custody.episode_directories(run_directory)
            attempts = {Path(x["directory"]).resolve() for x in summary["native_attempts"]}
            listed = {Path(x["directory"]).resolve() for x in summary["episodes"]}
            maximum = {"minimum": 16, "pilot": 1870, "validation": 3}[args.phase]
            require(0 < len(episodes) <= maximum and set(episodes) == attempts == listed,
                    "actual Supervisor/native/listed attempt inventory differs")
            result["attempted_episode_directories"] = [str(p) for p in episodes]
            jobs, members, leaves = [], [], []
            for i, episode in enumerate(episodes):
                name, output = "fifo_" + str(i).zfill(4), args.evidence / ("fifo_" + str(i).zfill(4) + "_output.json")
                jobs.append({"id": name, "output": str(output), "argv": ["/usr/bin/python3", str(WIRELESS / "report/assets/20261017_mr3_p2a0_v10/independent/mr3_v10_fifo_phase_review.py"), str(episode), "--freeze", args.freeze, "--output", str(output)]})
                members.append(name)
                leaves.append({"id": name, "episode_directory": str(episode)})
            manifest = args.evidence / "fifo_manifest_output.json"
            jobs.append({"id": "fifo_manifest", "kind": "fifo_manifest", "output": str(manifest), "members": members, "leaves": leaves, "depends_on": members})
            closure = args.evidence / "custody_review_output.json"
            jobs.append({"id": "closure", "output": str(closure), "depends_on": ["fifo_manifest"], "argv": ["/usr/bin/python3", "-B", "-m", "mr3_learning.native_custody", "review", "--run-directory", str(run_directory), "--freeze", args.freeze, "--binding", binding, "--capture", str(capture), "--launch-receipt", native["receipt"], "--fifo-receipts", str(manifest), "--expected-episodes", str(len(episodes)), "--output", str(closure)]})
            for name, module in (("full", "mr3_learning.audit_ppo"), ("input", "mr3_learning.audit_policy_inputs")):
                output = args.evidence / (name + "_output.json")
                jobs.append({"id": name, "output": str(output), "argv": [plan["learner_python"], "-B", "-m", module, str(run_directory), "--freeze", args.freeze, "--output", str(output)]})
            completed, skipped = prep.run_audits(jobs, runner, started + cap_ns)
            result["audits"], result["skipped_audits"] = completed, skipped
            require(not skipped and all(completed.get(j["id"], {}).get("passed") is True for j in jobs), "required phase consumers failed/skipped")
            check_ppo_counts(args.phase, summary, metadata, js(args.evidence / "full_output.json"))
            require(digest(run_directory / "final.zip") == summary["final_checkpoint_sha256"], "final checkpoint changed")
            read.finish()
            result["passed"] = True
        except BaseException as error:
            result["errors"].append(repr(error))
        result["ended_wall_monotonic_ns"] = time.monotonic_ns()
        result["charged_wall_seconds"] = str(Decimal(result["ended_wall_monotonic_ns"] - started) / 10**9)
        result["input_bindings"] = read.bindings
        if "cap_ns" in locals():
            result["total_phase_wall_allocation_seconds"] = phase["total_phase_wall_allocation_seconds"]
            result["within_total_phase_wall_allocation"] = result["ended_wall_monotonic_ns"] - started <= cap_ns
            if not result["within_total_phase_wall_allocation"]:
                result["passed"] = False
                result["errors"].append("total phase wall allocation exceeded; actual cost remains charged")
        record(event="ppo_phase_closed", passed=result["passed"], errors=result["errors"])
    prep.dump(args.evidence / "summary.json", result)
    return 0 if result["passed"] else 1


def outer(args):
    require(not args.output.exists(), "outer receipt already exists")
    started = time.monotonic_ns()
    forward = args.forward[1:] if args.forward[:1] == ["--"] else args.forward
    require(prep.argument(forward, "--freeze") == args.freeze
            and prep.argument(forward, "--phase") == args.phase, "outer/inner phase arguments differ")
    argv = [sys.executable, "-B", str(Path(__file__).resolve()), "run", *forward]
    own = prep.identity(os.getpid())
    child = subprocess.Popen(argv, cwd=WIRELESS, env=dict(os.environ, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1"))
    saved = prep.identity(child.pid)
    errors = []
    while True:
        try:
            code = child.wait()
            break
        except BaseException as error:
            errors.append(repr(error))
    prep.dump(args.output, {"schema": OUTER, "freeze": args.freeze, "phase": args.phase,
        "tool_sha256": digest(__file__), "actual_coordinator_identity": saved,
        "actual_outer_identity": own, "actual_argv": argv, "returncode": code,
        "started_wall_monotonic_ns": started, "ended_wall_monotonic_ns": time.monotonic_ns(), "errors": errors})
    return code


def final_absence(args):
    read, js = inputs_reader()
    wait, phase = js(args.receipt), js(args.evidence / "summary.json")
    require(wait["schema"] == OUTER and phase["schema"] == SCHEMA
            and wait["freeze"] == phase["freeze"] == args.freeze and wait["phase"] == phase["phase"] == args.phase
            and type(wait["returncode"]) is int and wait["tool_sha256"] == phase["tool"]["sha256"]
            and all(wait["actual_coordinator_identity"][k] == phase["coordinator_identity"][k] for k in ("pid", "start_ticks")),
            "PPO outer real wait/source/phase/coordinator differs")
    require(hashlib.sha256(read(__file__)).hexdigest() == phase["tool"]["sha256"],
            "separately recorded PPO outer/final tool source differs")
    saved = {}
    def collect(value):
        if isinstance(value, dict):
            if type(value.get("pid")) is int and type(value.get("start_ticks")) is int:
                saved[(value["pid"], value["start_ticks"])] = value
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(wait)
    collect(phase)
    roots = [args.evidence]
    if phase.get("run_directory"):
        roots.append(Path(phase["run_directory"]))
    names = {"supervisor_metadata.json", "supervisor_shutdown.json", "live_custody.json", "native.json", "watcher.json", "custody_review_output.json"}
    for root in roots:
        require(root.exists(), "declared PPO evidence root missing")
        for path in sorted(root.rglob("*.json")):
            if path.name in names:
                collect(js(path))
    ledger = args.evidence / "ledger.jsonl"
    for line in read(ledger).splitlines():
        collect(custody.parse(line))
    rows = []
    for (pid, start), value in sorted(saved.items()):
        current = prep.identity(pid)
        rows.append({"saved": value, "current": current, "same_identity_present": bool(current and current["start_ticks"] == start)})
    clean = bool(rows) and all(not x["same_identity_present"] for x in rows)
    read.finish()
    ended = time.monotonic_ns()
    elapsed = ended - wait["started_wall_monotonic_ns"]
    allocation = phase.get("total_phase_wall_allocation_seconds")
    within = allocation is not None and elapsed <= int(Decimal(allocation) * 10**9)
    execution = wait["returncode"] == 0 and wait["errors"] == [] and phase["passed"] is True and within
    prep.dump(args.output, {"schema": FINAL, "freeze": args.freeze, "phase": args.phase,
        "passed": clean and execution, "closure_passed": clean, "all_saved_identities_gone": clean,
        "execution_passed": execution, "saved_identity_count": len(rows), "identities": rows,
        "inputs": read.bindings, "wall_monotonic_ns": ended,
        "phase_total_wall_seconds": str(Decimal(elapsed) / 10**9),
        "total_phase_wall_allocation_seconds": allocation,
        "within_total_phase_wall_allocation": within,
        "phase_total_wall_scope": "Conservative outer entry through independent final-absence read/rechecks; external actual final-consumer wait/write overhead is also charged by root and may still fail the allocation.",
        "scope": "Independent actual PID/start absence after actual PPO coordinator/outer wait; zombie same identity fails. Never relabelled trace/matrix."})
    return 0 if clean and execution else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    child = sub.add_parser("run")
    for name in ("plan", "evidence", "balance", "prior-summary", "prior-final-closure"):
        child.add_argument("--" + name, type=Path, required=True)
    for name in ("freeze", "phase"):
        child.add_argument("--" + name, required=True)
    parent = sub.add_parser("outer")
    for name in ("freeze", "phase"):
        parent.add_argument("--" + name, required=True)
    parent.add_argument("--output", type=Path, required=True)
    parent.add_argument("forward", nargs=argparse.REMAINDER)
    final = sub.add_parser("final-absence")
    for name in ("receipt", "evidence", "output"):
        final.add_argument("--" + name, type=Path, required=True)
    for name in ("freeze", "phase"):
        final.add_argument("--" + name, required=True)
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    require(args.phase in ("minimum", "pilot", "validation"), "unknown phase")
    return {"run": run, "outer": outer, "final-absence": final_absence}[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
