"""One explicit exact-seed probe, with no learner or native qualification."""
import argparse
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .proxy2d_activity import phase, source_paths
from .proxy2d_capacity import activity_spec, collect
from .proxy2d_karto_activity import (
    ADAPTER, ROOT, ROS_ROOT, W, _absence, _outer, _owner, exclusive, git,
    manifest_reference, native_manifest, read, record, sha, source_file,
)
from .proxy2d_performance import admitted_seconds, profile_report
from .supervisor import process_identity

A = W / "report/assets/20261021_mr3_p2a_v33_seed_mode"
PLAN = A / "seed_probe_plan_v1.json"
OUTPUT = ROS_ROOT / "log/mr3_p2a_proxy2d_v33/seed_probe_v1"
MODULE = "mr3_learning.proxy2d_seed_activity"
RULE = "exact-point-bridge-v1"
ENTRY = "46691.4127443736018"
PHASES = {"conformity": 120, "conformity_review": 120, "collection": 900,
          "audit": 270, "description": 30}


def settings(kind="seed_probe"):
    if kind == "seed_probe":
        return A, PLAN, OUTPUT, RULE, ENTRY
    if kind == "seed_probe_v2":
        assets = W / "report/assets/20261022_mr3_p2a_v34_seed_v2"
        return (assets, assets / "seed_probe_plan_v1.json",
                ROS_ROOT / "log/mr3_p2a_proxy2d_v34/seed_probe_v2",
                "exact-point-bridge-v2", "47269.8043977356018")
    if kind in ("point_graph_profile_v1", "point_graph_probe_v1"):
        assets = W / "report/assets/20261022_mr3_p2a_v37_point_graph"
        return (assets, assets / (kind + "_plan_v1.json"),
                ROS_ROOT / "log/mr3_p2a_proxy2d_v37" / kind,
                "exact-point-bridge-v2", "47739.5359129776018")
    raise ValueError("unknown exact seed activity")


POINT_KINDS = ("point_graph_profile_v1", "point_graph_probe_v1")
POINT_START = "point-attachment-3x3-v1"


def phase_limits(kind):
    return ({"conformity": 30, "conformity_review": 20, "collection": 180,
             "audit": 40, "profile_report": 20} if kind == "point_graph_profile_v1" else PHASES)


def group_limits(kind):
    return [240] if kind == "point_graph_profile_v1" else [900]


def point_profile_admission(freeze):
    """Bind the one fully closed same-freeze profile before spending short-run work."""
    kind = "point_graph_profile_v1"
    _, plan_path, run, _, entry = settings(kind)
    outer_path = Path("/tmp/mr3_p2a_v37_point_graph_profile_outer_v1/actual_wait.json")
    final_path = Path("/tmp/mr3_p2a_v37_point_graph_profile_final_v1.json")
    final_outer_path = Path("/tmp/mr3_p2a_v37_point_graph_profile_final_outer_v1/actual_wait.json")
    start, result, closed = read(run / "activity_start.json"), read(run / "activity_result.json"), read(final_path)
    outer = _outer(outer_path, [sys.executable, "-B", "-m", MODULE, "execute", "--freeze", freeze,
                                "--kind", kind])
    final_outer = _outer(final_outer_path, [sys.executable, "-B", "-m", MODULE, "final", "--kind", kind,
        "--outer", str(outer_path), "--output", str(final_path)])
    if (start["freeze"] != freeze or start["plan_sha256"] != sha(plan_path)
            or _owner(outer["child_identity"]) != _owner(start["coordinator_identity"])
            or result.get("passed") is not True or result.get("source_unchanged") is not True
            or result.get("errors") != [] or set(result["phases"]) != set(phase_limits(kind))
            or not all(item["passed"] for item in result["phases"].values())
            or closed.get("freeze") != freeze or closed.get("passed") is not True
            or closed.get("activity_passed") is not True or closed.get("absence_passed") is not True
            or closed.get("outer_reference") != record(outer_path)
            or final_outer["started_monotonic_ns"] < outer["ended_monotonic_ns"]):
        raise ValueError("new point graph profile is not completely closed at the same freeze")
    evidence = [run / name for name in ("activity_start.json", "activity_result.json", "capacity_summary.json",
        "independent_audit.json", "profile_summary.json", "conformity.json", "conformity_independent.json")]
    conformity_path = run / "conformity.json"
    expected_commands = {
        "conformity": ["mr3_learning.proxy2d_conformity", "--freeze", freeze, "--seed-rule", "exact-point-bridge-v2",
            "--output", str(conformity_path), "--start-graph-rule", POINT_START],
        "conformity_review": ["mr3_learning.audit_proxy2d", str(run), "--freeze", freeze,
            "--conformity-only", str(conformity_path), "--output", str(run / "conformity_independent.json")],
        "collection": [MODULE, "collect", "--kind", kind],
        "audit": ["mr3_learning.audit_proxy2d", str(run), "--freeze", freeze,
            "--output", str(run / "independent_audit.json")],
        "profile_report": [MODULE, "profile_report", "--kind", kind],
    }
    last_end = start["started_ns"]
    for name in phase_limits(kind):
        path = run / (name + "_actual_wait.json")
        waited = read(path)
        if (waited != result["phases"][name]
                or waited.get("actual_argv") != [sys.executable, "-B", "-m", *expected_commands[name]]
                or waited.get("cwd") != str(W) or waited.get("actual_waited") is not True
                or waited.get("actual_returncode") != 0 or waited.get("timed_out") is not False
                or waited.get("signals_sent") != [] or waited.get("errors") != []
                or not last_end <= waited["started_monotonic_ns"] < waited["ended_monotonic_ns"] <= start["deadline_ns"]):
            raise ValueError("point graph profile phase did not actually close: " + name)
        last_end = waited["ended_monotonic_ns"]
        evidence.extend([path, run / (name + ".log")])
    if (start.get("kind") != kind or result.get("kind") != kind
            or start.get("start_graph_rule") != POINT_START or result.get("start_graph_rule") != POINT_START
            or start.get("seed_rule") != "exact-point-bridge-v2"
            or result.get("freeze") != freeze or result["started_ns"] != start["started_ns"]
            or not outer["started_monotonic_ns"] <= start["started_ns"] <= last_end <= result["ended_ns"] <= outer["ended_monotonic_ns"]
            or start["deadline_ns"] - start["started_ns"] != 600 * 10**9):
        raise ValueError("point graph profile source mode or timeline differs")
    audit, summary, profile = (read(run / name) for name in (
        "independent_audit.json", "capacity_summary.json", "profile_summary.json"))
    if (not audit.get("passed") or not profile.get("passed") or summary.get("activity_spec") != activity_spec(kind)
            or summary.get("freeze") != freeze or audit.get("freeze") != freeze
            or summary.get("seed_rule") != "exact-point-bridge-v2" or audit.get("seed_rule") != "exact-point-bridge-v2"
            or audit.get("start_graph_rule") != POINT_START
            or summary.get("step_attempts") != 8 or summary.get("step_returns") != 8
            or summary.get("step_errors") != 0
            or summary.get("mapper") != "karto" or summary.get("native_manifest") != manifest_reference()
            or summary.get("start_graph_rule") != POINT_START
            or any(audit.get(key) != expected for key, expected in (
                ("verified_action_count", 8), ("verified_uniform_action_count", 8),
                ("verified_step_return_count", 8), ("verified_actor_record_count", 9),
                ("verified_point_graph_robot_checks", 27)))):
        raise ValueError("new point graph profile does not cover all eight verified returns")
    for identity in [*closed["saved_identities"], outer["coordinator_identity"], outer["child_identity"],
                     final_outer["coordinator_identity"], final_outer["child_identity"]]:
        _absence(identity)
    span = Decimal(final_outer["ended_monotonic_ns"] - outer["started_monotonic_ns"]) / 10**9
    charge = sum((Decimal(item["actual_child_wait_seconds"]) for item in (outer, final_outer)), Decimal(0))
    if span > 600 or Decimal(entry) + charge + 1800 > Decimal(52000):
        raise ValueError("profile closure or engineering reservation exceeds its bound")
    return {"passed": True, "same_freeze": freeze, "profile_actual_union_seconds": str(charge),
            "profile_observed_wall_seconds": str(span),
            "references": [record(path) for path in [outer_path, final_path, final_outer_path, *evidence]]}


def kind_arguments(kind):
    return [] if kind == "seed_probe" else ["--kind", kind]


def bindings(kind="seed_probe"):
    assets, _, _, _, _ = settings(kind)
    native_manifest()
    paths = set(source_paths()) | {Path(manifest_reference()["path"]), assets / "scope_acceptance_v1.json"}
    return {source_file(path): sha(path) for path in sorted(paths)}


def specification(kind="seed_probe"):
    _, _, output, rule, entry = settings(kind)
    value = {"schema": "mr3-proxy2d-exact-seed-plan-v1", "activity_spec": activity_spec(kind),
        "output": str(output), "phase_seconds": phase_limits(kind), "group_wall_seconds": group_limits(kind),
        "external_reserve_seconds": 120, "cleanup_reserve_seconds": 180,
        "engineering_entry_used_seconds": entry, "engineering_ceiling_seconds": "52000",
        "mapper": "karto", "mapper_library": str(ADAPTER), "seed_rule": rule,
        "native_manifest": manifest_reference(), "source_bindings": bindings(kind),
        "qualification": False, "training_eligible": False, "native_credit": False,
        "pilot_unchanged": True, "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    if kind in POINT_KINDS:
        value.update(start_graph_rule=POINT_START, combined_reservation_seconds=2400,
                     profile_required_before_probe=True)
    return value


def build(kind="seed_probe"):
    _, plan_path, _, _, entry = settings(kind)
    value = specification(kind)
    reservation = value.get("combined_reservation_seconds", value["activity_spec"]["activity_seconds"])
    if Decimal(entry) + reservation > Decimal("52000"):
        raise ValueError("seed probe exceeds the approved engineering balance")
    exclusive(plan_path, value)
    return value


def check(freeze, kind="seed_probe"):
    _, plan_path, _, _, _ = settings(kind)
    if not isinstance(freeze, str) or not re.fullmatch("[0-9a-f]{40}", freeze):
        raise ValueError("full source freeze required")
    plan = read(plan_path)
    if plan != specification(kind):
        raise ValueError("seed probe plan, sources or native artifact changed")
    if git("rev-parse", "HEAD").decode().strip() != freeze or git("status", "--porcelain"):
        raise ValueError("seed probe requires its clean exact freeze")
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", freeze, "origin/main"], check=True)
    for relative in [source_file(plan_path), *plan["source_bindings"]]:
        if git("show", freeze + ":" + relative) != (ROOT / relative).read_bytes():
            raise ValueError("seed probe source differs from freeze: " + relative)
    return plan


def execute(freeze, kind="seed_probe"):
    _, plan_path, output, rule, _ = settings(kind)
    started = time.monotonic_ns()
    plan = check(freeze, kind)
    admission = point_profile_admission(freeze) if kind == "point_graph_probe_v1" else None
    output.mkdir(parents=True, exist_ok=False)
    deadline = started + activity_spec(kind)["activity_seconds"] * 10**9
    state = {"schema": "mr3-proxy2d-exact-seed-activity-v1", "freeze": freeze,
        "plan_sha256": sha(plan_path), "started_ns": started, "deadline_ns": deadline,
        "coordinator_identity": process_identity(os.getpid()), "seed_rule": rule,
        "phases": {}, "errors": [], "passed": False,
        "qualification": False, "training_eligible": False, "native_credit": False,
        "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    if kind in POINT_KINDS:
        state.update(kind=kind, start_graph_rule=POINT_START, profile_admission=admission)
    exclusive(output / "activity_start.json", state)
    conformity = output / "conformity.json"
    commands = {
        "conformity": ["mr3_learning.proxy2d_conformity", "--freeze", freeze, "--seed-rule", rule,
                       "--output", str(conformity)],
        "conformity_review": ["mr3_learning.audit_proxy2d", str(output), "--freeze", freeze,
            "--conformity-only", str(conformity), "--output", str(output / "conformity_independent.json")],
        "collection": [MODULE, "collect", *kind_arguments(kind)],
        "audit": ["mr3_learning.audit_proxy2d", str(output), "--freeze", freeze,
                  "--output", str(output / "independent_audit.json")],
        "description": [MODULE, "describe", *kind_arguments(kind)],
    }
    if kind in POINT_KINDS:
        commands["conformity"] += ["--start-graph-rule", POINT_START]
    if kind == "point_graph_profile_v1":
        commands["profile_report"] = [MODULE, "profile_report", *kind_arguments(kind)]
    try:
        for name, maximum in phase_limits(kind).items():
            if name == "collection":
                if not all(row["passed"] for row in state["phases"].values()):
                    raise RuntimeError("conformity admission failed; no collection")
                context = {"freeze": freeze,
                    "source_bindings": plan["source_bindings"],
                    "conformity": {"path": str(conformity), "sha256": sha(conformity)},
                    "activity_started_ns": started, "deadline_ns": deadline,
                    "activity_spec": plan["activity_spec"], "group_wall_seconds": group_limits(kind),
                    "mapper": "karto", "mapper_library": str(ADAPTER), "seed_rule": rule,
                    "native_manifest": plan["native_manifest"]}
                if kind in POINT_KINDS:
                    context["start_graph_rule"] = POINT_START
                exclusive(output / "collection_context.json", context)
            state["phases"][name] = phase(output, name, [sys.executable, "-B", "-m", *commands[name]],
                                          admitted_seconds(deadline, maximum))
    except Exception as error:
        state["errors"].append(repr(error))
    try:
        state["source_unchanged"] = bindings(kind) == plan["source_bindings"]
    except (OSError, ValueError, KeyError) as error:
        state["source_unchanged"] = False
        state["errors"].append(repr(error))
    state["ended_ns"] = time.monotonic_ns()
    state["passed"] = (set(state["phases"]) == set(phase_limits(kind))
        and all(row["passed"] for row in state["phases"].values()) and not state["errors"]
        and state["source_unchanged"] and state["ended_ns"] <= deadline)
    exclusive(output / "activity_result.json", state)
    return state


def describe(kind="seed_probe"):
    """Describe all admitted records, without selecting seeds or claiming task success."""
    _, _, output, rule, _ = settings(kind)
    summary = read(output / "capacity_summary.json")
    audit_path = output / "independent_audit.json"
    audited = read(audit_path)
    verified = {Path(row["directory"]).resolve(): row for row in audited["episodes"]}
    rows, errors = [], []
    for group in summary["groups"]:
        for episode in group["episodes"]:
            directory = Path(episode["directory"])
            report = verified.get(directory.resolve(), {})
            trace_path = directory / "trace.jsonl.gz"
            trace_raw = trace_path.read_bytes()
            trace_digest = hashlib.sha256(trace_raw).hexdigest()
            trace_matches = trace_digest == report.get("trace_sha256")
            prefix = (report.get("validated_prefix_records", 0)
                      if trace_matches and report.get("bound_bytes_unchanged") else 0)
            if not trace_matches:
                errors.append("trace differs from independently audited bytes: " + str(trace_path))
            reasons, certificate_results, point_results = Counter(), Counter(), Counter()
            no_goals = [0, 0, 0]
            records = raw_records = 0
            last = None
            for raw in gzip.decompress(trace_raw).splitlines():
                event = json.loads(raw)
                if event["event"] not in ("reset", "step_return"):
                    continue
                raw_records += 1
                if event["event_sequence"] > prefix:
                    continue
                records += 1
                last = event
                snap = event["snapshot"]
                for index, name in enumerate(("tb1", "tb2", "tb3")):
                    item = snap["path_maps"][name]
                    reasons[name, item["seed_rejection_reason"] or "accepted"] += 1
                    certificate = item["seed_point_bridge_certificate"]
                    if certificate is not None:
                        certificate_results[name, "accepted" if certificate["accepted"] else certificate["reason"]] += 1
                    if kind in POINT_KINDS:
                        point_results[name, item["start_graph_rejection_reason"] or "accepted"] += 1
                    no_goals[index] += not any(snap["per_robot_action_mask"][index][:8])
            rows.append({"scene": episode["scene"], "seed": episode["seed"], "raw_actor_records": raw_records,
                "trace_matches_independent_audit": trace_matches,
                "trace_reference": {"path": str(trace_path), "sha256": trace_digest, "bytes": len(trace_raw)},
                "verified_prefix_actor_records": records, "validated_prefix_records": prefix,
                "independent_episode_passed": report.get("passed", False),
                "no_legal_goal_records_per_robot": no_goals,
                "seed_reasons": [{"robot": name, "reason": reason, "count": count}
                                 for (name, reason), count in sorted(reasons.items())],
                "certificate_results": [{"robot": name, "reason": reason, "count": count}
                                 for (name, reason), count in sorted(certificate_results.items())],
                "last_robots": last["snapshot"]["robots"] if last else None,
                "last_reward_diagnostics": last["reward_diagnostics"] if last else None})
            if kind in POINT_KINDS:
                rows[-1]["point_graph_results"] = [{"robot": name, "reason": reason, "count": count}
                    for (name, reason), count in sorted(point_results.items())]
    value = {"schema": "mr3-exact-seed-probe-description-v1", "freeze": summary["freeze"],
        "seed_rule": rule, "episodes": rows, "errors": errors, "passed": audited["passed"] and not errors,
        "independent_audit_reference": record(audit_path),
        "scope": "verified prefixes only; raw counts separate; descriptive only, no task qualification"}
    if kind in POINT_KINDS:
        value.update(start_graph_rule=POINT_START,
            seed_results_scope="original seed-cell diagnostic; distinct from point_graph_results admission")
    exclusive(output / "seed_description.json", value)
    return value


def final(outer_path, output, kind="seed_probe"):
    _, plan_path, activity_output, _, _ = settings(kind)
    outer, start = read(outer_path), read(activity_output / "activity_start.json")
    errors, saved = [], {}
    activity = {"passed": False}
    try:
        _outer(outer_path, [sys.executable, "-B", "-m", MODULE, "execute", "--freeze", start["freeze"],
                          *kind_arguments(kind)],
               require_pass=False)
        if (_owner(outer["child_identity"]) != _owner(start["coordinator_identity"])
                or start["plan_sha256"] != sha(plan_path)):
            raise ValueError("outer execute identity/plan differs")
        activity = read(activity_output / "activity_result.json")
        native_manifest()
    except (OSError, ValueError, KeyError) as error:
        errors.append(repr(error))
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
    for path in activity_output.rglob("*.json"):
        try:
            visit(read(path))
        except (OSError, ValueError) as error:
            errors.append(str(path) + ": " + repr(error))
    for identity in saved.values():
        try:
            _absence(identity)
        except ValueError as error:
            errors.append(str(error))
    try:
        for relative, digest in read(plan_path)["source_bindings"].items():
            if sha(ROOT / relative) != digest:
                errors.append("source changed: " + relative)
    except (OSError, ValueError, KeyError) as error:
        errors.append(repr(error))
    if kind == "point_graph_probe_v1" and activity.get("passed"):
        try:
            if activity.get("profile_admission") != point_profile_admission(start["freeze"]):
                raise ValueError("profile evidence changed during probe")
        except (OSError, ValueError, KeyError) as error:
            errors.append(repr(error))
    elapsed = Decimal(time.monotonic_ns() - outer["started_monotonic_ns"]) / 10**9
    value = {"schema": "mr3-exact-seed-probe-external-final-v1", "freeze": start["freeze"],
        "outer_reference": record(outer_path), "saved_identities": list(saved.values()),
        "absence_passed": not errors, "activity_passed": activity["passed"], "errors": errors,
        "observed_wall_seconds": str(elapsed), "passed": not errors and outer["passed"]
        and activity["passed"] and elapsed <= activity_spec(kind)["activity_seconds"], "qualification": False,
        "training_eligible": False, "native_credit": False}
    exclusive(output, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "preflight", "execute", "collect", "describe", "profile_report", "final"))
    parser.add_argument("--freeze")
    parser.add_argument("--outer", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--kind", choices=("seed_probe", "seed_probe_v2", *POINT_KINDS), default="seed_probe")
    args = parser.parse_args()
    _, _, output, rule, _ = settings(args.kind)
    if args.operation == "build":
        value = build(args.kind)
    elif args.operation == "preflight":
        check(args.freeze, args.kind)
        value = {"passed": True}
    elif args.operation == "execute":
        value = execute(args.freeze, args.kind)
    elif args.operation == "collect":
        context = read(output / "collection_context.json")
        if (context["activity_spec"] != activity_spec(args.kind) or context["seed_rule"] != rule
                or context["mapper_library"] != str(ADAPTER) or context["native_manifest"] != manifest_reference()):
            raise ValueError("seed probe collection context differs")
        if context.get("start_graph_rule", "original-seed-cell") != (POINT_START if args.kind in POINT_KINDS else "original-seed-cell"):
            raise ValueError("start graph collection context differs")
        native_manifest()
        value = collect(output, context["freeze"], context["source_bindings"], context["conformity"],
            context["activity_started_ns"], context["deadline_ns"], activity_spec=context["activity_spec"],
            group_wall_seconds=group_limits(args.kind), profile=args.kind == "point_graph_profile_v1",
            mapper="karto", mapper_library=str(ADAPTER),
            native_manifest=context["native_manifest"], seed_rule=rule,
            **({"start_graph_rule": POINT_START} if args.kind in POINT_KINDS else {}))
        value["passed"] = not value["errors"] and value["closed"]
    elif args.operation == "describe":
        value = describe(args.kind)
    elif args.operation == "profile_report":
        if args.kind != "point_graph_profile_v1":
            raise ValueError("only the declared point graph profile can report performance")
        value = profile_report(output)
    else:
        value = final(args.outer, args.output, args.kind)
    print(json.dumps({"operation": args.operation, "passed": value.get("passed", True)}))
    return 0 if value.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
