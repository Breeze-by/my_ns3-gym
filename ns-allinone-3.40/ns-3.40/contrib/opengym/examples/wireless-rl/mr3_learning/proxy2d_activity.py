"""One approved, source-frozen proxy conformity/capacity activity; zero updates."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .proxy2d_codec import canonical_bytes
from .proxy2d_process import pidfd_open, pidfd_send_signal
from .supervisor import WORKSPACE as ROOT, ROS_ROOT, process_identity

W = Path(__file__).resolve().parents[1]
A = W / "report/assets/20261020_mr3_p2a_v22_proxy2d"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def source_paths():
    paths = set((W / "mr3_learning").glob("*.py"))
    paths.update((ROS_ROOT / "src/multi_robot_exploration/multi_robot_exploration").glob("*.py"))
    paths.update((ROS_ROOT / "src/merge_map/merge_map").glob("*.py"))
    paths.add(ROS_ROOT / "scripts/mr3_proxy2d_worker.py")
    paths.update((ROS_ROOT / "src/multi_robot/config/mr3_p1a").glob("*.json"))
    paths.update((ROS_ROOT / "src/multi_robot/worlds").glob("p1c_*.world"))
    paths.add(ROS_ROOT / "src/multi_robot/models/turtlebot3_waffle/model.sdf")
    # Model path is deliberately checked, never replaced by a remembered laser.
    for path in paths:
        if not path.is_file():
            raise ValueError("required proxy source missing: " + str(path))
    paths.add(A / "scope_acceptance_v1.json")
    return sorted(paths)


def build(path):
    if path.exists():
        raise ValueError("plan exists; no overwrite")
    plan = {"schema": "mr3-proxy2d-plan-v1", "qualification": False, "training_eligible": False,
        "native_credit": False, "max_env_step_attempts": 9000, "activity_seconds": 3600,
        "phase_seconds": {"conformity": 720, "conformity_review": 180, "capacity": 1800, "audit": 600, "external": 300},
        "schedule": [[scene, seed] for scene in ("open", "rooms", "corridors") for seed in (101, 103)],
        "groups": [1, 4], "steps_per_episode": 300, "action_seed": 41,
        "output": str(ROS_ROOT / "log/mr3_p2a_proxy2d_v22/run_v1"),
        "engineering_entry_used_seconds": "41480.3336378496018", "engineering_ceiling_seconds": "52000",
        "pilot_unchanged": True, "gpu_calls": 0, "optimizer_steps": 0,
        "source_bindings": {str(p.relative_to(ROOT)): sha(p) for p in source_paths()}}
    write(path, plan)
    return plan


def check(plan_path, freeze, require_clean=True):
    plan = json.loads(plan_path.read_text())
    assert plan["schema"] == "mr3-proxy2d-plan-v1" and plan["max_env_step_attempts"] == 9000
    assert plan["activity_seconds"] == 3600 and plan["groups"] == [1, 4]
    assert plan["phase_seconds"] == {"conformity": 720, "conformity_review": 180, "capacity": 1800, "audit": 600, "external": 300}
    assert plan["schedule"] == [[s, n] for s in ("open", "rooms", "corridors") for n in (101, 103)]
    assert not plan["qualification"] and not plan["training_eligible"] and not plan["native_credit"]
    assert plan["steps_per_episode"] == 300 and plan["action_seed"] == 41
    assert plan["output"] == str(ROS_ROOT / "log/mr3_p2a_proxy2d_v22/run_v1")
    assert set(plan["source_bindings"]) == {str(path.relative_to(ROOT)) for path in source_paths()}
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == freeze
    if require_clean:
        assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        subprocess.run(["git", "merge-base", "--is-ancestor", freeze, "origin/main"], cwd=ROOT, check=True)
    relative_plan = str(plan_path.resolve().relative_to(ROOT))
    assert subprocess.check_output(["git", "show", freeze + ":" + relative_plan], cwd=ROOT) == plan_path.read_bytes()
    for name, digest in plan["source_bindings"].items():
        raw = (ROOT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest, name
        assert subprocess.check_output(["git", "show", freeze + ":" + name], cwd=ROOT) == raw, name
    return plan


def phase(run, name, argv, seconds):
    started = time.monotonic_ns()
    signals = []
    with (run / (name + ".log")).open("xb") as console:
        child = subprocess.Popen(argv, cwd=W, stdout=console, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "CUDA_VISIBLE_DEVICES": "",
                 "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        saved = process_identity(child.pid)
        if saved is None:
            child.wait()
            raise RuntimeError("phase child lost before identity capture")
        descriptor = pidfd_open(child.pid)
        timed_out = False
        try:
            try:
                rc = child.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                pidfd_send_signal(descriptor, signal.SIGINT)
                signals.append("SIGINT")
                try:
                    rc = child.wait(timeout=180.)
                except subprocess.TimeoutExpired:
                    pidfd_send_signal(descriptor, signal.SIGKILL)
                    signals.append("SIGKILL")
                    rc = child.wait()
        finally:
            os.close(descriptor)
    ended = time.monotonic_ns()
    result = {"actual_argv": argv, "cwd": str(W), "child_identity": saved,
        "started_monotonic_ns": started, "ended_monotonic_ns": ended,
        "actual_child_wait_seconds": str(Decimal(ended - started) / Decimal(10**9)),
        "actual_returncode": rc, "actual_waited": True, "timed_out": timed_out,
        "signals_sent": signals, "passed": rc == 0 and not timed_out}
    write(run / (name + "_actual_wait.json"), result)
    return result


def admitted_seconds(deadline, allowance, now=None):
    """Reserve external closure and the phase's full cooperative cleanup tail."""
    now = time.monotonic_ns() if now is None else now
    available = (deadline - now) // 1_000_000_000 - 300 - 180
    if available <= 0:
        raise RuntimeError("phase skipped: insufficient time for cleanup and external closure")
    return min(allowance, available)


def execute(plan_path, freeze):
    started = time.monotonic_ns()
    plan = check(plan_path, freeze)
    run = Path(plan["output"])
    run.mkdir(parents=True, exist_ok=False)
    deadline = started + 3_600_000_000_000
    state = {"schema": "mr3-proxy2d-activity-v1", "freeze": freeze, "plan_sha256": sha(plan_path),
        "started_ns": started, "deadline_ns": deadline, "coordinator_identity": process_identity(os.getpid()),
        "qualification": False, "training_eligible": False, "native_credit": False,
        "phases": {}, "passed": False, "errors": [], "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    write(run / "activity_start.json", state)
    try:
        conformity = run / "conformity.json"
        argv = [sys.executable, "-B", "-m", "mr3_learning.proxy2d_conformity", "--freeze", freeze, "--output", str(conformity)]
        state["phases"]["conformity"] = phase(run, "conformity", argv, admitted_seconds(deadline, 720))
        argv = [sys.executable, "-B", "-m", "mr3_learning.audit_proxy2d", str(run), "--freeze", freeze,
                "--conformity-only", str(conformity), "--output", str(run / "conformity_independent.json")]
        state["phases"]["conformity_review"] = phase(run, "conformity_review", argv, admitted_seconds(deadline, 180))
        if not all(state["phases"][name]["passed"] for name in ("conformity", "conformity_review")):
            raise RuntimeError("conformity or independent review failed; no capacity admission")
        write(run / "collection_context.json", {"freeze": freeze, "source_bindings": plan["source_bindings"],
            "conformity": {"path": str(conformity), "sha256": sha(conformity)},
            "activity_started_ns": started, "deadline_ns": deadline})
        argv = [sys.executable, "-B", "-m", "mr3_learning.proxy2d_activity", "collect", "--run", str(run)]
        state["phases"]["capacity"] = phase(run, "capacity", argv, admitted_seconds(deadline, 1800))
        audit_seconds = admitted_seconds(deadline, 600)
        argv = [sys.executable, "-B", "-m", "mr3_learning.audit_proxy2d", str(run), "--freeze", freeze,
                "--output", str(run / "independent_audit.json")]
        state["phases"]["audit"] = phase(run, "audit", argv, audit_seconds)
        state["passed"] = all(item["passed"] for item in state["phases"].values())
    except Exception as error:
        state["errors"].append(repr(error))
    state["source_unchanged"] = all(sha(ROOT / name) == digest for name, digest in plan["source_bindings"].items())
    state["ended_ns"] = time.monotonic_ns()
    state["passed"] = state["passed"] and state["source_unchanged"] and state["ended_ns"] <= deadline
    write(run / "activity_result.json", state)
    return state


def final(run, outer_path, output):
    if output.exists():
        raise ValueError("final output exists")
    outer = json.loads(outer_path.read_text())
    start = json.loads((run / "activity_start.json").read_text())
    argv = outer["actual_argv"]
    if (outer.get("actual_waited") is not True or outer.get("scope") != "engineering"
            or argv[:5] != [sys.executable, "-B", "-m", "mr3_learning.proxy2d_activity", "execute"]
            or argv[5:] != ["--freeze", start["freeze"]]
            or outer.get("source_unchanged") is not True):
        raise ValueError("final requires the exact actual engineering execute wait")
    began, ended = outer["started_monotonic_ns"], outer["ended_monotonic_ns"]
    child = outer["child_identity"]
    coordinator = start["coordinator_identity"]
    if (type(began) is not int or type(ended) is not int or not 0 < began < ended
            or Decimal(outer["actual_child_wait_seconds"]) != Decimal(ended - began) / Decimal(10**9)
            or not began <= start["started_ns"] <= ended
            or (child["pid"], child["start_ticks"]) != (coordinator["pid"], coordinator["start_ticks"])):
        raise ValueError("outer timing or coordinator identity binding failed")
    identities = {}

    def visit(value):
        if isinstance(value, dict):
            if type(value.get("pid")) is int and type(value.get("start_ticks")) is int:
                identities[value["pid"], value["start_ticks"]] = value
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    metadata_errors = []
    visit(outer)
    for path in run.rglob("*.json"):
        try:
            visit(json.loads(path.read_text()))
        except (OSError, ValueError) as error:
            metadata_errors.append({"path": str(path), "error": repr(error)})
    present, unreadable = [], []
    for (pid, ticks), identity in identities.items():
        try:
            raw = Path(f"/proc/{pid}/stat").read_text()
        except FileNotFoundError:
            continue
        except OSError as error:
            unreadable.append({"identity": identity, "error": repr(error)})
            continue
        try:
            fields = raw[raw.rfind(")") + 2:].split()
            if int(fields[19]) == ticks:
                present.append({"identity": identity, "actual_state": fields[0]})
        except (ValueError, IndexError) as error:
            unreadable.append({"identity": identity, "error": repr(error)})
    activity_path = run / "activity_result.json"
    activity = json.loads(activity_path.read_text()) if activity_path.exists() else None
    result = {"schema": "mr3-proxy2d-external-absence-v1", "saved_identities": list(identities.values()),
        "saved_identity_count": len(identities), "present": present, "unreadable": unreadable,
        "metadata_errors": metadata_errors,
        "absence_passed": not present and not unreadable and not metadata_errors,
        "activity_passed": activity.get("passed", False) if activity else False,
        "outer_engineering_seconds": outer["actual_child_wait_seconds"],
        "outer_actual_returncode": outer["actual_returncode"],
        "budget_observed_seconds": str(Decimal(time.monotonic_ns() - began) / Decimal(10**9)),
        "qualification": False, "training_eligible": False,
        "accounting_requires_this_external_actual_wait": True}
    result["budget_observed_within_3600"] = Decimal(result["budget_observed_seconds"]) <= 3600
    result["passed"] = result["absence_passed"] and result["budget_observed_within_3600"]
    write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "preflight", "execute", "collect", "final"))
    parser.add_argument("--plan", type=Path, default=A / "predeclared_plan_v1.json")
    parser.add_argument("--freeze")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--outer", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.operation == "build":
        result = build(args.plan)
    elif args.operation == "preflight":
        check(args.plan, args.freeze)
        result = {"passed": True, "native_runs": 0, "gpu_calls": 0}
    elif args.operation == "execute":
        result = execute(args.plan, args.freeze)
    elif args.operation == "final":
        result = final(args.run, args.outer, args.output)
    else:
        from .proxy2d_capacity import collect
        context = json.loads((args.run / "collection_context.json").read_text())
        result = collect(args.run, context["freeze"], context["source_bindings"], context["conformity"],
                         context["activity_started_ns"], context["deadline_ns"])
        result["passed"] = not result["errors"]
    print(json.dumps({"passed": result.get("passed"), "operation": args.operation}))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
