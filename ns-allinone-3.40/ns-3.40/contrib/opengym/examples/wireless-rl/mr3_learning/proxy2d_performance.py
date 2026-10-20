"""Two prospectively frozen, zero-update P2A performance activities."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import pstats
import subprocess
import sys
import time

from .proxy2d_activity import phase, sha, source_paths, write
from .proxy2d_capacity import activity_spec, collect, validate_activity_spec
from .supervisor import WORKSPACE as ROOT, ROS_ROOT, process_identity

W = Path(__file__).resolve().parents[1]
A = W / "report/assets/20261020_mr3_p2a_v23_performance"
PHASES = {
    "profile": {"conformity": 60, "conformity_review": 20, "collection": 240, "audit": 120, "profile_report": 40},
    "short_capacity": {"conformity": 60, "conformity_review": 20, "collection": 1200, "audit": 300},
}


def bindings():
    paths = set(source_paths()) | {A / "scope_acceptance_v1.json"}
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(paths)}


def plan_path(kind):
    return A / (kind + "_plan_v1.json")


def build(kind, entry):
    path = plan_path(kind)
    if path.exists():
        raise ValueError("plan exists; no overwrite")
    spec = activity_spec(kind)
    if Decimal(entry) + spec["activity_seconds"] > 52000:
        raise ValueError("engineering admission exceeds existing ceiling")
    value = {"schema": "mr3-proxy2d-performance-plan-v1", "activity_spec": spec,
             "output": str(ROS_ROOT / "log/mr3_p2a_proxy2d_v23" / (kind + "_v1")),
             "phase_seconds": PHASES[kind], "external_reserve_seconds": 120,
             "group_wall_seconds": [240] if kind == "profile" else [400, 800],
             "engineering_entry_used_seconds": entry, "engineering_ceiling_seconds": "52000",
             "source_bindings": bindings(), "qualification": False, "training_eligible": False,
             "native_credit": False, "pilot_unchanged": True, "optimizer_steps": 0}
    write(path, value)
    return value


def check(kind, freeze):
    path = plan_path(kind)
    plan = json.loads(path.read_text())
    validate_activity_spec(plan["activity_spec"])
    assert plan["activity_spec"] == activity_spec(kind)
    assert plan["phase_seconds"] == PHASES[kind] and plan["external_reserve_seconds"] == 120
    assert plan["group_wall_seconds"] == ([240] if kind == "profile" else [400, 800])
    assert not plan["qualification"] and not plan["training_eligible"] and not plan["native_credit"]
    assert plan["pilot_unchanged"] and plan["optimizer_steps"] == 0
    assert Decimal(plan["engineering_entry_used_seconds"]) + plan["activity_spec"]["activity_seconds"] <= 52000
    assert plan["output"] == str(ROS_ROOT / "log/mr3_p2a_proxy2d_v23" / (kind + "_v1"))
    assert plan["source_bindings"] == bindings()
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == freeze
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
    subprocess.run(["git", "merge-base", "--is-ancestor", freeze, "origin/main"], cwd=ROOT, check=True)
    for name in [str(path.relative_to(ROOT)), *plan["source_bindings"]]:
        assert subprocess.check_output(["git", "show", freeze + ":" + name], cwd=ROOT) == (ROOT / name).read_bytes()
    return plan


def admitted_seconds(deadline, planned, now=None):
    now = time.monotonic_ns() if now is None else now
    available = (deadline - now) // 10**9 - 120 - 180
    if available <= 0:
        raise RuntimeError("phase skipped: insufficient cleanup/external closure reserve")
    return min(planned, available)


def execute(kind, freeze):
    started = time.monotonic_ns()
    plan = check(kind, freeze)
    run = Path(plan["output"])
    run.mkdir(parents=True, exist_ok=False)
    deadline = started + plan["activity_spec"]["activity_seconds"] * 10**9
    state = {"schema": "mr3-proxy2d-performance-activity-v1", "kind": kind, "freeze": freeze,
             "plan_sha256": sha(plan_path(kind)), "started_ns": started, "deadline_ns": deadline,
             "coordinator_identity": process_identity(os.getpid()), "phases": {}, "errors": [],
             "passed": False, "qualification": False, "training_eligible": False, "native_credit": False,
             "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    write(run / "activity_start.json", state)
    try:
        conformity = run / "conformity.json"
        commands = {
            "conformity": ["mr3_learning.proxy2d_conformity", "--freeze", freeze, "--output", str(conformity)],
            "conformity_review": ["mr3_learning.audit_proxy2d", str(run), "--freeze", freeze,
                                  "--conformity-only", str(conformity), "--output", str(run / "conformity_independent.json")],
            "collection": ["mr3_learning.proxy2d_performance", "collect", "--kind", kind, "--run", str(run)],
            "audit": ["mr3_learning.audit_proxy2d", str(run), "--freeze", freeze, "--output", str(run / "independent_audit.json")],
            "profile_report": ["mr3_learning.proxy2d_performance", "profile_report", "--kind", kind, "--run", str(run)],
        }
        for name, maximum in plan["phase_seconds"].items():
            if name == "collection":
                if not all(state["phases"][n]["passed"] for n in ("conformity", "conformity_review")):
                    raise RuntimeError("conformity admission failed; no collection")
                write(run / "collection_context.json", {"freeze": freeze, "source_bindings": plan["source_bindings"],
                    "conformity": {"path": str(conformity), "sha256": sha(conformity)},
                    "activity_started_ns": started, "deadline_ns": deadline, "activity_spec": plan["activity_spec"],
                    "group_wall_seconds": plan["group_wall_seconds"]})
            argv = [sys.executable, "-B", "-m", *commands[name]]
            state["phases"][name] = phase(run, name, argv, admitted_seconds(deadline, maximum))
        state["passed"] = all(item["passed"] for item in state["phases"].values())
    except Exception as error:
        state["errors"].append(repr(error))
    state["source_unchanged"] = bindings() == plan["source_bindings"]
    state["ended_ns"] = time.monotonic_ns()
    state["passed"] = state["passed"] and state["source_unchanged"] and state["ended_ns"] <= deadline
    write(run / "activity_result.json", state)
    return state


def profile_report(run):
    summary = json.loads((run / "capacity_summary.json").read_text())
    if summary.get("activity_spec") != activity_spec("profile"):
        raise ValueError("profile summary must bind the single profile activity")
    episodes = [item for group in summary["groups"] for item in group["episodes"]]
    if len(episodes) != 1:
        raise ValueError("profile must have exactly one attempted episode")
    directory = Path(episodes[0]["directory"]).resolve()
    if not directory.is_relative_to(run.resolve()):
        raise ValueError("profile episode escaped run")
    metadata = json.loads((directory / "episode.json").read_text())
    if metadata.get("profile_enabled") is not True:
        raise ValueError("profile episode was not explicitly enabled")
    paths = sorted(run.rglob("*.pstats"))
    if {path.resolve() for path in paths} != {directory / "worker.pstats", directory / "evaluator.pstats"}:
        raise ValueError("profile must contain exactly the owned worker and evaluator files")
    reports = []
    for path in paths:
        if path.name not in ("worker.pstats", "evaluator.pstats"):
            raise ValueError("unexpected profile role")
        stats = pstats.Stats(str(path))
        rows = [{"file": name[0], "line": name[1], "function": name[2], "primitive_calls": item[0],
                 "calls": item[1], "self_seconds": item[2], "cumulative_seconds": item[3]}
                for name, item in stats.stats.items()]
        reports.append({"path": str(path), "sha256": sha(path), "role": path.stem,
                        "total_self_seconds": stats.total_tt, "total_calls": stats.total_calls,
                        "top_self": sorted(rows, key=lambda row: row["self_seconds"], reverse=True)[:40],
                        "top_cumulative": sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:40]})
    result = {"schema": "mr3-proxy2d-profile-report-v1", "profiles": reports,
              "passed": sorted(report["role"] for report in reports) == ["evaluator", "worker"],
              "scope": "Instrumented single open101 episode, not uninstrumented capacity. "
              "Cumulative functions overlap; worker/evaluator waiting intervals overlap and must not be added.",
              "qualification": False, "training_eligible": False}
    if (run / "profile_summary.json").exists():
        raise ValueError("profile report exists")
    write(run / "profile_summary.json", result)
    return result


def final(kind, run, outer_path, output):
    if output.exists():
        raise ValueError("final output exists")
    outer = json.loads(outer_path.read_text())
    start = json.loads((run / "activity_start.json").read_text())
    expected = [sys.executable, "-B", "-m", "mr3_learning.proxy2d_performance", "execute", "--kind", kind,
                "--freeze", start["freeze"]]
    now = time.monotonic_ns()
    began, ended = outer["started_monotonic_ns"], outer["ended_monotonic_ns"]
    child, owner = outer["child_identity"], start["coordinator_identity"]
    if (start.get("schema") != "mr3-proxy2d-performance-activity-v1" or start.get("kind") != kind
            or start.get("plan_sha256") != sha(plan_path(kind))
            or outer.get("cwd") != str(W)
            or outer["scope"] != "engineering" or outer["actual_waited"] is not True
            or outer["source_unchanged"] is not True
            or outer["actual_argv"] != expected or type(began) is not int or type(ended) is not int
            or not 0 < began <= start["started_ns"] < ended <= now
            or Decimal(outer["actual_child_wait_seconds"]) != Decimal(ended - began) / Decimal(10**9)
            or (child["pid"], child["start_ticks"]) != (owner["pid"], owner["start_ticks"])):
        raise ValueError("exact actual engineering execute wait/identity binding failed")
    saved, errors = {}, []
    def visit(value):
        if isinstance(value, dict):
            if type(value.get("pid")) is int and type(value.get("start_ticks")) is int:
                saved[value["pid"], value["start_ticks"]] = value
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(outer)
    for path in run.rglob("*.json"):
        try:
            visit(json.loads(path.read_text()))
        except (OSError, ValueError) as error:
            errors.append({"path": str(path), "error": repr(error)})
    present, unreadable = [], []
    for (pid, ticks), value in saved.items():
        try:
            raw = Path(f"/proc/{pid}/stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            if int(fields[19]) == ticks:
                present.append({"identity": value, "state": fields[0]})
        except FileNotFoundError:
            continue
        except (OSError, ValueError, IndexError) as error:
            unreadable.append({"identity": value, "error": repr(error)})
    observed = Decimal(now - began) / Decimal(10**9)
    result = {"schema": "mr3-proxy2d-performance-external-absence-v1", "kind": kind,
              "saved_identities": list(saved.values()), "saved_identity_count": len(saved),
              "present": present, "unreadable": unreadable, "metadata_errors": errors,
              "absence_passed": not present and not unreadable and not errors,
              "observed_wall_seconds": str(observed), "outer_engineering_seconds": outer["actual_child_wait_seconds"],
              "activity_passed": json.loads((run / "activity_result.json").read_text())["passed"],
              "accounting_requires_this_external_actual_wait": True, "qualification": False, "training_eligible": False}
    result["passed"] = result["absence_passed"] and observed <= activity_spec(kind)["activity_seconds"]
    write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "preflight", "execute", "collect", "profile_report", "final"))
    parser.add_argument("--kind", choices=("profile", "short_capacity"), required=True)
    parser.add_argument("--freeze")
    parser.add_argument("--entry-seconds")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--outer", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.operation == "build":
        result = build(args.kind, args.entry_seconds)
    elif args.operation == "preflight":
        check(args.kind, args.freeze)
        result = {"passed": True}
    elif args.operation == "execute":
        result = execute(args.kind, args.freeze)
    elif args.operation == "collect":
        context = json.loads((args.run / "collection_context.json").read_text())
        result = collect(args.run, context["freeze"], context["source_bindings"], context["conformity"],
                         context["activity_started_ns"], context["deadline_ns"], activity_spec=context["activity_spec"],
                         group_wall_seconds=context["group_wall_seconds"], profile=args.kind == "profile")
        result["passed"] = not result["errors"]
    elif args.operation == "profile_report":
        result = profile_report(args.run)
    else:
        result = final(args.kind, args.run, args.outer, args.output)
    print(json.dumps({"operation": args.operation, "kind": args.kind, "passed": result.get("passed")}))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
