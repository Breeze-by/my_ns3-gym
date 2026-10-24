"""One sealed engineering diagnostic; never scientific qualification or PPO.

Use the existing reach actual-wait runner, native custody and independent
readers. The smaller workload cannot satisfy the unchanged qualification plan.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from . import native_custody_reach as custody, reach_preparation as preparation
from .preparation import identity

ROOT = preparation.WORKSPACE
W = ROOT / preparation.WIRELESS_RELATIVE
SCHEMA = "mr3-reach-feasibility-diagnostic-plan-v1"
CONTRACT = "mr3-reach-v1"
OPENING_USED = Decimal("38216.5104974146018")
OPENING_LEFT = Decimal("13783.4895025853982")
CAP = Decimal("6500")
require, dump, sha = preparation.require, preparation.dump, preparation.sha


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def strict_identity(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")")+2:].split()
    return {"pid":pid, "start_ticks":int(fields[19]), "state":fields[0]}


def load_plan(path, freeze, *, clean=False):
    require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}",freeze), "exact source freeze required")
    path = Path(path).resolve()
    plan = json.loads(path.read_bytes())
    require(plan.get("schema") == SCHEMA and plan.get("safety_contract") == CONTRACT
            and plan.get("qualification") is False and plan.get("training_eligible") is False
            and plan.get("optimizer_steps") == 0 and plan.get("gpu_calls") == 0
            and plan.get("robots_per_environment") == 3, "not the nonqualifying diagnostic plan")
    require(plan.get("expected_episodes") == 2 and plan.get("steps_per_episode") == 32
            and plan.get("schedule") == ["open:101", "open:101"]
            and plan.get("diagnostic_uniform_seed") == 41, "declared workload changed")
    command = plan["native_argv"]
    require(command[:3] == ["/home/zhuyulab/miniconda3/envs/ns3gym/bin/python", "-m", "mr3_learning.benchmark"],
            "diagnostic cannot invoke policy training")
    flags = {"--workers", "--schedule", "--steps", "--run-id", "--output-root", "--safety-contract",
             "--diagnostic-uniform-seed", "--base-domain", "--base-port", "--work-wall-seconds", "--close-reserve-seconds"}
    require(len(command) == 3+2*len(flags) and set(command[3::2]) == flags,
            "undeclared diagnostic native flags")
    for flag,value in (("--workers","1"),("--schedule","open:101,open:101"),("--steps","32"),
            ("--safety-contract",CONTRACT),("--diagnostic-uniform-seed","41"),
            ("--work-wall-seconds","3200"),("--close-reserve-seconds","180")):
        require(command.count(flag) == 1 and preparation.argument(command,flag) == value,
                "diagnostic native scope differs: "+flag)
    require(Path(preparation.argument(command,"--output-root")) / preparation.argument(command,"--run-id")
            == Path(plan["run_directory"]), "diagnostic native output differs")
    budget = plan["budget"]
    require(budget["ceiling_seconds"] == "52000"
            and Decimal(budget["opening_used_seconds"]) == OPENING_USED
            and Decimal(budget["opening_remaining_seconds"]) == OPENING_LEFT
            and Decimal(budget["total_reservation_seconds"]) == CAP <= OPENING_LEFT,
            "unapproved/restored diagnostic budget")
    require(preparation.source_inventory(ROOT) <= plan["source_bindings"].keys(),
            "diagnostic source inventory incomplete")
    for name, expected in plan["source_bindings"].items():
        raw = (ROOT / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected
                and subprocess.check_output(["git", "show", freeze+":"+name], cwd=ROOT) == raw,
                "diagnostic current/Git/declared source differs: "+name)
    for name, expected in plan["library_bindings"].items():
        require(sha(name) == expected, "diagnostic installed ELF differs: "+name)
    require(json.loads(Path(plan["accounting_basis"]).read_bytes())["remaining_seconds"]
            == str(OPENING_LEFT), "opening accounting changed")
    if clean:
        require(git("rev-parse", "HEAD") == git("rev-parse", "origin/main") == freeze
                and not git("status", "--porcelain"), "diagnostic requires a clean pushed exact freeze")
        require(subprocess.check_output(["git", "show", freeze+":"+str(path.relative_to(ROOT))],
                                       cwd=ROOT) == path.read_bytes(), "plan is not frozen")
    return plan


def build(path):
    """Refresh current source declarations; retain the actual unchanged ELF/build proof."""
    path = Path(path).resolve()
    require(not path.exists(), "diagnostic plan already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    original = W / "report/assets/20261019_mr3_p2a_v19/native_custody_binding_v1.json"
    binding = json.loads(original.read_bytes())
    native, _ = custody.load_implementation()
    for spec in binding["binaries"].values():
        actual = native.file_proof(spec["path"])
        require(actual["sha256"] == spec["sha256"] and actual["bytes"] == spec["bytes"],
                "diagnostic does not authorize changed native ELF")
        spec.update(actual)
    names = set(preparation.source_inventory(ROOT))
    names.update(row["path"] for row in binding["source_bindings"])
    names.add(str(Path(__file__).resolve().relative_to(ROOT)))
    sources = {name: sha(ROOT / name) for name in sorted(names)}
    binding["source_bindings"] = [{"path": p, "sha256": d} for p,d in sources.items()]
    binding["qualification_wrappers"] = [row for row in binding["source_bindings"]
        if row["path"].startswith(str(preparation.WIRELESS_RELATIVE / "mr3_learning"))]
    binding_path = path.with_name("native_custody_binding_v1.json")
    dump(binding_path, binding)
    sources[str(binding_path.relative_to(ROOT))] = sha(binding_path)
    output = Path("/tmp/mr3_p2a_v21_diagnostic")
    run = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes"
    learner = "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python"
    command = [learner, "-m", "mr3_learning.benchmark", "--workers", "1",
        "--schedule", "open:101,open:101", "--steps", "32", "--run-id", run.name,
        "--output-root", str(run.parent), "--safety-contract", CONTRACT,
        "--diagnostic-uniform-seed", "41", "--base-domain", "224", "--base-port", "14901",
        "--work-wall-seconds", "3200", "--close-reserve-seconds", "180"]
    plan = {"schema": SCHEMA, "safety_contract": CONTRACT, "qualification": False,
        "training_eligible": False, "robots_per_environment": 3, "gpu_calls": 0, "optimizer_steps": 0,
        "expected_episodes": 2, "steps_per_episode": 32, "schedule": ["open:101", "open:101"],
        "diagnostic_uniform_seed": 41, "run_directory": str(run), "output_directory": str(output),
        "preflight": str(output.with_name(output.name+"_preflight.json")),
        "custody_binding": str(binding_path), "source_bindings": sources,
        "library_bindings": {v["resolved_path"]: v["sha256"] for v in binding["binaries"].values()},
        "accounting_basis": str(W/"report/assets/20261020_mr3_p2a_v20/engineering_accounting_v2.json"),
        "budget": {"ceiling_seconds": "52000", "opening_used_seconds": str(OPENING_USED),
            "opening_remaining_seconds": str(OPENING_LEFT), "total_reservation_seconds": str(CAP),
            "native_work_seconds": "3200", "native_close_reserve_seconds": "180",
            "read_only_consumer_seconds_each": "900", "external_tail_reserve_seconds": "300",
            "automatic_retry": False, "pilot_and_final_only_changed": False},
        "native_argv": command,
        "consumers": ["peer_control_fifo_per_episode", "information_per_episode",
            "cadence_including_runtime", "native_scalar_evaluator_archives_activity_inputs",
            "live_actual_ELF_custody_and_closure", "external_saved_identity_absence"],
        "stop_rule": "First native task/infra failure prevents further resets; all submitted work is waited. No retry. Missing/failed audits or wall overrun remain failures.",
        "claim_scope": "Two short uniform-legal-action engineering episodes only; no PPO, learning, continuous safety, full qualification,95% reliability or network credit."}
    dump(path, plan)
    return plan


def execute(path, freeze):
    started = time.monotonic_ns()
    plan = load_plan(path, freeze, clean=True)
    preflight = json.loads(Path(plan["preflight"]).read_bytes())
    require(preflight.get("passed") is True and preflight.get("freeze") == freeze
            and preflight.get("plan_sha256") == sha(path) and preflight.get("qualification") is False,
            "missing exact diagnostic preflight")
    output, run = Path(plan["output_directory"]), Path(plan["run_directory"])
    require(not output.exists() and not run.exists(), "diagnostic output exists; no retry")
    output.mkdir()
    module, projection = preparation.load_executor()
    lock = threading.Lock()
    with (output/"ledger.jsonl").open("x") as ledger:
        def record(**row):
            with lock:
                ledger.write(json.dumps({"wall_monotonic_ns": time.monotonic_ns(), **row})+"\n")
                ledger.flush()
        runner = module.Runner(output, W, freeze, sha(path), record)
        def job(name, argv, result=None, depends=()):
            return {"id": name, "argv": list(map(str, argv)), "output": str(result or output/(name+"_result.json")),
                "receipt": str(output/(name+"_command.json")), "console": str(output/(name+".log")),
                "required": True, "depends_on": list(depends)}
        def bounded(name, argv, result=None, depends=()):
            helper = W/"report/assets/20261020_mr3_p2a_v20/bounded_read_only_child_v1.py"
            return job(name, ["/usr/bin/python3", helper, "--output", output/(name+"_supervision"),
                "--wall-seconds", "900", "--", *argv], result, depends)
        common = ["/usr/bin/python3", "-m", "mr3_learning.native_custody_reach"]
        capture, ready, stop = (output/n for n in ("live_custody.json", "ready.json", "stop.json"))
        watcher = runner.spawn(job("watcher", [*common, "watch", "--run-directory", run,
            "--freeze", freeze, "--binding", plan["custody_binding"], "--ready-file", ready,
            "--stop-file", stop, "--output", capture], capture))
        native_value, watcher_value, error = None, None, None
        try:
            deadline = time.monotonic()+30
            while not ready.exists():
                require(watcher["process"] is not None and watcher["process"].poll() is None
                        and time.monotonic() < deadline, "watcher readiness failed")
                time.sleep(.05)
            actual = custody.read_ready_receipt(custody.Reader(), ready, freeze, sha(plan["custody_binding"]))
            require(all(actual["watcher_identity"][k] == watcher["value"]["process_identity"][k]
                        for k in ("pid", "start_ticks")), "foreign watcher ready")
            native_value = runner.command(job("native", plan["native_argv"], run/"benchmark_summary.json"))
        except Exception as failure:
            error = repr(failure)
        finally:
            boundary = ({"launch_receipt": {"path": native_value["receipt"], "sha256": sha(native_value["receipt"])}}
                        if native_value else {"native_not_started": True, "reason": "pre_native_admission_failure"})
            dump(stop, {"schema": custody.SCHEMA_STOP, "safety_contract": CONTRACT, "freeze": freeze, **boundary})
            watcher_value = runner.finish(watcher)
        episodes = sorted(run.glob("worker*/episode*/metadata.json"))
        jobs, fifo_ids = [], []
        for number, meta in enumerate(episodes, 1):
            episode = meta.parent
            for kind, module_name in (("fifo", "audit_reach_peer_control"), ("information", "audit_reach_information")):
                name = f"{kind}_{number:03d}"
                target = output/(name+"_result.json")
                jobs.append(bounded(name, ["/usr/bin/python3", "-m", "mr3_learning."+module_name,
                    episode, "--freeze", freeze, "--output", target], target))
                if kind == "fifo": fifo_ids.append(name)
        if episodes:
            manifest = output/"fifo_manifest.json"
            jobs.append({"id": "fifo_manifest", "kind": "fifo_manifest", "required": True,
                "output": str(manifest), "members": fifo_ids, "depends_on": fifo_ids,
                "leaves": [{"id": name, "episode_directory": str(meta.parent)} for name,meta in zip(fifo_ids,episodes)]})
            target = output/"native_episode_checks_result.json"
            argv = [plan["native_argv"][0], "-m", "mr3_learning.audit_reach_diagnostic", run,
                "--freeze", freeze, "--plan", str(path), "--output", str(target)]
            for name in fifo_ids: argv += ["--fifo-result", str(output/(name+"_result.json"))]
            jobs.append(bounded("native_episode_checks", argv, target, fifo_ids))
            target = output/"cadence_result.json"
            jobs.append(bounded("cadence", ["/usr/bin/python3", "-m", "mr3_learning.audit_reach_cadence",
                run, "--freeze", freeze, "--output", target], target))
            target = output/"closure_result.json"
            jobs.append(bounded("closure", [*common, "review", "--run-directory", run, "--freeze", freeze,
                "--binding", plan["custody_binding"], "--capture", capture, "--launch-receipt", output/"native_command.json",
                "--fifo-receipts", manifest, "--expected-episodes", str(len(episodes)), "--output", target],
                target, ["fifo_manifest"]))
        completed, skipped = ({}, [])
        if episodes and watcher_value.get("passed") and time.monotonic_ns() < started+int((CAP-300)*10**9):
            completed, skipped = module.run_audits(jobs, runner, started+int((CAP-300)*10**9))
        else:
            skipped = [{"id": j["id"], "reason": "no_bound_native_or_watcher_or_time"} for j in jobs]
        source_stable = True
        try:
            load_plan(path, freeze, clean=True)
        except Exception as failure:
            source_stable, error = False, repr(failure)
        elapsed = Decimal(time.monotonic_ns()-started)/10**9
        passed = (error is None and native_value is not None and native_value.get("passed") is True
            and watcher_value.get("passed") is True and len(episodes) == 2 and not skipped
            and bool(completed) and all(v.get("passed") for v in completed.values()) and elapsed <= CAP-300)
        summary = {"schema": "mr3-reach-feasibility-diagnostic-execution-v1", "freeze": freeze,
            "plan_sha256": sha(path), "qualification": False, "training_eligible": False,
            "passed": passed, "coordinator_identity": identity(os.getpid()), "error": error,
            "native": native_value, "watcher": watcher_value, "audits": completed, "skipped_audits": skipped,
            "actual_attempted_episodes": len(episodes), "expected_episodes": 2,
            "source_unchanged": source_stable, "all_submitted_children_waited": True,
            "elapsed_seconds": str(elapsed), "capacity_requires_external_actual_wait": True,
            "executor_projection": projection, "gpu_calls": 0, "optimizer_steps": 0}
        dump(output/"summary.json", summary)
    return summary


def final(path, outer, output):
    """Read the real outer wait, then check every saved identity including zombies."""
    plan = json.loads(Path(path).read_bytes())
    receipt = json.loads(Path(outer).read_bytes())
    require(receipt.get("scope") == "engineering" and receipt.get("actual_waited") is True
            and receipt.get("source_unchanged") is True, "missing/changed actual engineering outer wait")
    summary = json.loads((Path(plan["output_directory"])/"summary.json").read_bytes())
    freeze = summary["freeze"]
    require(receipt.get("actual_argv") == [plan["native_argv"][0], "-m", "mr3_learning.reach_diagnostic",
            "execute", "--plan", str(Path(path).resolve()), "--freeze", freeze]
            and Path(receipt["cwd"]).resolve() == W
            and summary.get("plan_sha256") == sha(path)
            and summary.get("all_submitted_children_waited") is True
            and all(summary["coordinator_identity"][k] == receipt["child_identity"][k]
                    for k in ("pid", "start_ticks")), "foreign/incomplete diagnostic actual wait")
    values = [receipt]
    for directory in (Path(plan["output_directory"]), Path(plan["run_directory"])):
        values += [json.loads(p.read_bytes()) for p in directory.rglob("*.json")
                   if p.name.endswith(("_command.json", "actual_wait.json", "shutdown_receipt.json"))
                   or p.name in ("summary.json", "worker_summary.json", "live_custody.json")]
    identities = {}
    def collect(value):
        if isinstance(value, list):
            for child in value: collect(child)
        elif isinstance(value, dict):
            if type(value.get("pid")) is int and type(value.get("start_ticks")) is int:
                identities[(value["pid"],value["start_ticks"])] = value
            for child in value.values(): collect(child)
    for value in values: collect(value)
    present, unreadable = [], []
    for key,value in sorted(identities.items()):
        try:
            actual = strict_identity(key[0])
        except FileNotFoundError:
            continue
        except (OSError, ValueError, IndexError) as error:
            unreadable.append({"identity":value,"error":repr(error)}); continue
        if actual["start_ticks"] == key[1]: present.append(actual)
    start,end = receipt["started_monotonic_ns"],receipt["ended_monotonic_ns"]
    require(type(start) is int and type(end) is int and 0 < start < end, "invalid outer wait ns interval")
    elapsed = Decimal(end-start)/10**9
    declared = Decimal(receipt["actual_child_wait_seconds"])
    require(declared.is_finite() and elapsed == declared, "outer actual ns fee differs")
    result = {"schema": "mr3-reach-diagnostic-external-absence-v1", "qualification": False,
        "passed": not present and not unreadable, "saved_identity_count": len(identities),
        "saved_identities": [v for _,v in sorted(identities.items())],
        "present": present, "unreadable": unreadable, "outer_actual_engineering_seconds": str(elapsed),
        "outer_actual_returncode": receipt["actual_returncode"],
        "absence_passed": not present and not unreadable,
        "diagnostic_passed": summary.get("passed") is True and receipt.get("actual_returncode") == 0
            and receipt.get("passed") is True and not present and not unreadable,
        "accounting_requires_this_external_actual_wait": True}
    dump(output,result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "preflight", "execute", "final"))
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--freeze")
    parser.add_argument("--outer", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "build":
        build(args.plan); return 0
    if args.mode == "preflight":
        plan = load_plan(args.plan,args.freeze,clean=True)
        from .audit_reach_diagnostic import bound_sources
        from .reach_gates import _load_versioned_native_gates
        _, proof, _ = bound_sources(args.plan, plan["run_directory"], args.freeze)
        gates = _load_versioned_native_gates(ROOT,args.freeze,proof,plan["source_bindings"],plan["custody_binding"])
        result = custody.verify_binding(ROOT,args.freeze,plan["custody_binding"])
        dump(args.output, {"schema":"mr3-reach-diagnostic-preflight-v1","passed":True,
            "freeze":args.freeze,"plan_sha256":sha(args.plan),"qualification":False,
            "binding":result,"native_gate_source_proof":gates[-1]})
    elif args.mode == "execute": result = execute(args.plan,args.freeze)
    else: result = final(args.plan,args.outer,args.output)
    print(json.dumps({k:result[k] for k in ("passed",) if k in result}))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
