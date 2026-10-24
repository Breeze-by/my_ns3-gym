"""One frozen Karto profile, then at most one admitted zero-learning behavior run."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .proxy2d_activity import phase, source_paths
from .proxy2d_capacity import activity_spec, collect, validate_activity_spec
from .proxy2d_performance import admitted_seconds, profile_report
from .supervisor import WORKSPACE as ROOT, ROS_ROOT, process_identity, ros_environment

W = Path(__file__).resolve().parents[1]
A = W / "report/assets/20261021_mr3_p2a_v31_karto_behavior"
PREPARATION = W / "report/assets/20261021_mr3_p2a_v30_adapter"
BUILD_RECEIPT = PREPARATION / "attempts/adapter_v2/build_receipt_v1.json"
SDK = ROS_ROOT / "src/slam_toolbox/lib/karto_sdk"
CPP = ROS_ROOT / "src/multi_robot_exploration/multi_robot_exploration/mr3_proxy2d_karto_native.cpp"
ADAPTER = Path("/tmp/mr3_p2a_v30_adapter_cpu_v2/libmr3_karto_adapter.so")
KARTO = (ROS_ROOT / "build/slam_toolbox/lib/karto_sdk/libkartoSlamToolbox.so").resolve()
MANIFEST = A / "native_manifest_v1.json"
ENTRY = "45445.4237026666018"
CAP = "52000"
BLOCK = 4500
FORENSIC_RESERVE = 300
MODULE = "mr3_learning.proxy2d_karto_activity"
KINDS = ("karto_profile", "karto_behavior")
PHASES = {
    "karto_profile": {"conformity": 60, "conformity_review": 20, "collection": 240,
                      "audit": 120, "profile_report": 40},
    "karto_behavior": {"conformity": 60, "conformity_review": 20, "collection": 2100,
                       "audit": 950, "behavior_report": 100},
}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def exclusive(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def source_file(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("source path escaped workspace")
    return path.relative_to(ROOT).as_posix()


def same_record(specification):
    if record(specification["path"]) != {key: specification[key] for key in ("path", "bytes", "sha256")}:
        raise ValueError("bound current file differs: " + specification["path"])


def manifest_reference():
    return {"path": str(MANIFEST), "sha256": sha(MANIFEST)}


def native_manifest(create=False):
    """Bind the existing successful build, not an implicit compile or CDLL load."""
    if create and not MANIFEST.exists():
        build = read(BUILD_RECEIPT)
        if (build.get("passed") is not True or build.get("source_unchanged") is not True
                or build["source_before"] != build["source_after"]
                or Path(build["binary"]["path"]).resolve() != ADAPTER.resolve()):
            raise ValueError("native preparation build is not the declared stable success")
        phases = build["phases"]
        if [row["name"] for row in phases] != ["compile", "adapter_cpu", "extra_cpu"] or any(
                row.get("returncode") != 0 or row.get("actual_waited") is not True
                or row.get("signals") != [] or row.get("identity_capture_error") is not None
                or row.get("reap_overrun") is not False for row in phases):
            raise ValueError("native preparation lacks complete successful actual waits")
        cpu_results = []
        for name, count, waited in (("adapter_result_v1.json", 14, phases[1]),
                                   ("extra_result_v1.json", 10, phases[2])):
            path = BUILD_RECEIPT.parent / name
            tested = read(path)
            if (tested.get("passed") is not True or tested.get("tests") != count
                    or tested.get("failures") != 0 or tested.get("errors") != 0
                    or tested.get("identity") != waited["saved_identity"]):
                raise ValueError("native preparation raw CPU result is incomplete")
            cpu_results.append(record(path))
        dependencies = {CPP, *SDK.joinpath("include/karto_sdk").glob("*.h"),
                        *SDK.joinpath("include/karto_sdk").glob("*.hpp")}
        built_sources = {Path(row["path"]).resolve(): row for row in build["source_after"]}
        for path in dependencies | {KARTO, Path("/usr/bin/g++").resolve()}:
            expected = built_sources[path.resolve()]
            same_record(expected)
        same_record(build["binary"])
        exclusive(MANIFEST, {"schema": "mr3-proxy2d-karto-native-manifest-v1", "abi_version": 1,
            "mapper": "karto", "model": "karto_native_addscan_fixed_grid_v1",
            "scan_budget": 6300, "artifacts": [record(ADAPTER), record(KARTO)],
            "build_receipt": {"path": str(BUILD_RECEIPT.resolve()), "sha256": sha(BUILD_RECEIPT)},
            "build_receipt_bytes": BUILD_RECEIPT.stat().st_size,
            "cpu_results": cpu_results,
            "compiler": record(Path("/usr/bin/g++").resolve()),
            "source_bindings": {source_file(path): sha(path) for path in sorted(dependencies)},
            "production_enabled": False, "qualification": False, "training_eligible": False,
            "native_credit": False})
    value = read(MANIFEST)
    if (value["schema"] != "mr3-proxy2d-karto-native-manifest-v1" or value["abi_version"] != 1
            or value["mapper"] != "karto" or value["model"] != "karto_native_addscan_fixed_grid_v1"
            or value["scan_budget"] != 6300
            or [Path(row["path"]).resolve() for row in value["artifacts"]] != [ADAPTER.resolve(), KARTO]
            or Path(value["build_receipt"]["path"]).resolve() != BUILD_RECEIPT.resolve()):
        raise ValueError("native manifest identity differs")
    for specification in [*value["artifacts"], value["compiler"]]:
        same_record(specification)
    if (sha(BUILD_RECEIPT) != value["build_receipt"]["sha256"]
            or BUILD_RECEIPT.stat().st_size != value["build_receipt_bytes"]):
        raise ValueError("native preparation receipt changed")
    dependencies = {CPP, *SDK.joinpath("include/karto_sdk").glob("*.h"),
                    *SDK.joinpath("include/karto_sdk").glob("*.hpp")}
    if set(value["source_bindings"]) != {source_file(path) for path in dependencies}:
        raise ValueError("native manifest omitted a current build dependency")
    for relative, expected in value["source_bindings"].items():
        if source_file(ROOT / relative) != relative or sha(ROOT / relative) != expected:
            raise ValueError("native source differs from successful build: " + relative)
    build = read(BUILD_RECEIPT)
    if (build.get("passed") is not True or build.get("source_unchanged") is not True
            or build["source_before"] != build["source_after"]
            or build["binary"] != value["artifacts"][0]
            or [row["name"] for row in build["phases"]] != ["compile", "adapter_cpu", "extra_cpu"]):
        raise ValueError("native artifact differs from its successful build receipt")
    built_sources = {Path(row["path"]).resolve(): row for row in build["source_after"]}
    for path in dependencies | {KARTO, Path("/usr/bin/g++").resolve()}:
        same_record(built_sources[path.resolve()])
    for specification in value["cpu_results"]:
        same_record(specification)
    if any(value[key] is not False for key in ("production_enabled", "qualification", "training_eligible", "native_credit")):
        raise ValueError("native manifest acquired qualification credit")
    return value


def plan_path(kind):
    return A / (kind + "_plan_v1.json")


def output_path(kind):
    return ROS_ROOT / "log/mr3_p2a_proxy2d_v31" / (kind + "_v1")


def bindings():
    native = native_manifest()
    paths = set(source_paths()) | {A / "scope_acceptance_v1.json", MANIFEST, BUILD_RECEIPT}
    paths.update(ROOT / relative for relative in native["source_bindings"])
    paths.update(Path(specification["path"]) for specification in native["cpu_results"])
    return {source_file(path): sha(path) for path in sorted(paths)}


def build(kind, entry=ENTRY):
    if kind not in KINDS or entry != ENTRY or Decimal(ENTRY) + BLOCK > Decimal(CAP):
        raise ValueError("Karto activity differs from the fixed engineering block")
    if plan_path(kind).exists():
        raise ValueError("plan exists; no overwrite")
    native_manifest(create=True)
    spec = activity_spec(kind)
    validate_activity_spec(spec)
    expected_seconds = 600 if kind == "karto_profile" else 3600
    if spec["activity_seconds"] != expected_seconds:
        raise ValueError("Karto activity has a changed wall ceiling")
    value = {"schema": "mr3-proxy2d-karto-plan-v1", "activity_spec": spec,
        "output": str(output_path(kind)), "phase_seconds": PHASES[kind],
        "external_reserve_seconds": 120, "cleanup_reserve_seconds": 180,
        "group_wall_seconds": [240] if kind == "karto_profile" else [2100],
        "mapper": "karto", "mapper_library": str(ADAPTER), "native_manifest": manifest_reference(),
        "engineering_entry_used_seconds": ENTRY, "engineering_ceiling_seconds": CAP,
        "engineering_block_seconds": BLOCK, "forensic_reserve_seconds": FORENSIC_RESERVE,
        "profile_required_before_behavior": True, "source_bindings": bindings(),
        "qualification": False, "training_eligible": False, "native_credit": False,
        "pilot_unchanged": True, "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    exclusive(plan_path(kind), value)
    return value


def check(kind, freeze):
    if kind not in KINDS or not isinstance(freeze, str) or not re.fullmatch("[0-9a-f]{40}", freeze):
        raise ValueError("exact activity kind and full freeze required")
    value = read(plan_path(kind))
    validate_activity_spec(value["activity_spec"])
    expected = {"schema": "mr3-proxy2d-karto-plan-v1", "activity_spec": activity_spec(kind),
        "output": str(output_path(kind)), "phase_seconds": PHASES[kind],
        "external_reserve_seconds": 120, "cleanup_reserve_seconds": 180,
        "group_wall_seconds": [240] if kind == "karto_profile" else [2100],
        "mapper": "karto", "mapper_library": str(ADAPTER), "native_manifest": manifest_reference(),
        "engineering_entry_used_seconds": ENTRY, "engineering_ceiling_seconds": CAP,
        "engineering_block_seconds": BLOCK, "forensic_reserve_seconds": FORENSIC_RESERVE,
        "profile_required_before_behavior": True, "source_bindings": bindings(),
        "qualification": False, "training_eligible": False, "native_credit": False,
        "pilot_unchanged": True, "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    if value != expected:
        raise ValueError("Karto plan/current source/native manifest differs")
    if git("rev-parse", "HEAD").decode().strip() != freeze or git("status", "--porcelain"):
        raise ValueError("Karto activity requires its clean exact freeze")
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", freeze, "origin/main"], check=True)
    for name in [source_file(plan_path(kind)), *value["source_bindings"]]:
        if git("show", freeze + ":" + name) != (ROOT / name).read_bytes():
            raise ValueError("source differs from Git freeze: " + name)
    return value


def _owner(identity):
    keys = ("pid", "parent", "group", "session", "start_ticks")
    if not isinstance(identity, dict) or any(type(identity.get(key)) is not int or identity[key] <= 0 for key in keys):
        raise ValueError("incomplete saved process identity")
    return {key: identity[key] for key in keys}


def _outer(path, expected, require_pass=True):
    value = read(path)
    start, end = value["started_monotonic_ns"], value["ended_monotonic_ns"]
    if (value.get("scope") != "engineering" or value.get("actual_waited") is not True
            or value.get("source_unchanged") is not True or value["source_before"] != value["source_after"]
            or value.get("errors") != [] or type(value.get("actual_returncode")) is not int
            or value.get("cwd") != str(W) or value.get("actual_argv") != expected
            or type(start) is not int or type(end) is not int or not 0 < start < end
            or Decimal(value["actual_child_wait_seconds"]) != Decimal(end - start) / Decimal(10**9)
            or (require_pass and (value.get("passed") is not True or value["actual_returncode"] != 0))):
        raise ValueError("exact successful engineering actual-wait binding failed")
    _owner(value["child_identity"])
    for item in value["source_after"]:
        same_record(item)
    if sha(value["console"]["path"]) != value["console"]["sha256"]:
        raise ValueError("outer console changed")
    return value


def _execute_argv(kind, freeze, references=None):
    argv = [sys.executable, "-B", "-m", MODULE, "execute", "--kind", kind, "--freeze", freeze]
    if kind == "karto_behavior":
        for flag, key in (("--profile-outer", "outer"), ("--profile-final", "final"),
                          ("--profile-final-outer", "final_outer")):
            argv += [flag, references[key]["path"]]
    return argv


def _final_argv(kind, run, outer, output):
    return [sys.executable, "-B", "-m", MODULE, "final", "--kind", kind,
            "--run", str(run), "--outer", str(outer), "--output", str(output)]


def _absence(saved):
    pid, ticks = saved["pid"], saved["start_ticks"]
    if type(pid) is not int or type(ticks) is not int or pid <= 0 or ticks <= 0:
        raise ValueError("invalid saved PID/start")
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return
    fields = raw[raw.rfind(")") + 2:].split()
    if int(fields[19]) == ticks:
        raise ValueError("saved process remains, including zombie: " + str(saved))


def profile_admission(freeze, outer_path, final_path, final_outer_path):
    if any(path is None for path in (outer_path, final_path, final_outer_path)):
        raise ValueError("behavior requires profile outer/final/final-outer actual evidence")
    paths = {key: Path(path).resolve(strict=True) for key, path in
             (("outer", outer_path), ("final", final_path), ("final_outer", final_outer_path))}
    references = {key: record(path) for key, path in paths.items()}
    run = output_path("karto_profile")
    start, result = read(run / "activity_start.json"), read(run / "activity_result.json")
    if (start["kind"] != "karto_profile" or start["freeze"] != freeze
            or start["plan_sha256"] != sha(plan_path("karto_profile"))
            or result.get("passed") is not True or result.get("source_unchanged") is not True
            or result.get("errors") != [] or set(result["phases"]) != set(PHASES["karto_profile"])
            or not all(row["passed"] is True for row in result["phases"].values())):
        raise ValueError("profile activity did not completely pass at this freeze")
    evidence_paths = [run / name for name in ("activity_start.json", "activity_result.json",
                      "independent_audit.json", "capacity_summary.json", "profile_summary.json")]
    last_end = start["started_ns"]
    for name in PHASES["karto_profile"]:
        path = run / (name + "_actual_wait.json")
        waited = read(path)
        if (waited != result["phases"][name] or waited.get("actual_waited") is not True
                or waited.get("actual_returncode") != 0 or waited.get("timed_out") is not False
                or waited.get("signals_sent") != [] or waited.get("errors") != []
                or not last_end <= waited["started_monotonic_ns"] < waited["ended_monotonic_ns"]
                       <= start["deadline_ns"]):
            raise ValueError("profile phase lacks its independent successful actual wait: " + name)
        last_end = waited["ended_monotonic_ns"]
        evidence_paths.append(path)
    outer = _outer(paths["outer"], _execute_argv("karto_profile", freeze))
    if (_owner(outer["child_identity"]) != _owner(start["coordinator_identity"])
            or not outer["started_monotonic_ns"] <= start["started_ns"] <= last_end
                   <= result["ended_ns"] <= outer["ended_monotonic_ns"]
            or result["started_ns"] != start["started_ns"]
            or result["freeze"] != freeze or result["kind"] != "karto_profile"
            or start["deadline_ns"] - start["started_ns"] != 600 * 10**9):
        raise ValueError("profile execute owner/timeline differs")
    closed = read(paths["final"])
    if (closed.get("passed") is not True or closed.get("absence_passed") is not True
            or closed.get("activity_passed") is not True or closed.get("kind") != "karto_profile"
            or closed.get("freeze") != freeze or closed.get("outer_reference") != record(paths["outer"])):
        raise ValueError("profile external final did not completely close")
    final_outer = _outer(paths["final_outer"], _final_argv("karto_profile", run, paths["outer"], paths["final"]))
    if not outer["ended_monotonic_ns"] <= final_outer["started_monotonic_ns"]:
        raise ValueError("profile external-final wait overlaps execute")
    elapsed = Decimal(final_outer["ended_monotonic_ns"] - outer["started_monotonic_ns"]) / Decimal(10**9)
    charge = Decimal(outer["actual_child_wait_seconds"]) + Decimal(final_outer["actual_child_wait_seconds"])
    if elapsed > 600 or charge > 600 or charge + 3600 + FORENSIC_RESERVE > BLOCK:
        raise ValueError("profile cost cannot admit the fixed behavior/forensic block")
    audit, summary, profile = (read(run / name) for name in
                             ("independent_audit.json", "capacity_summary.json", "profile_summary.json"))
    attempts = summary["step_attempts"]
    if (audit.get("passed") is not True or profile.get("passed") is not True
            or summary["activity_spec"] != activity_spec("karto_profile")
            or summary.get("mapper") != "karto" or summary.get("native_manifest") != manifest_reference()
            or type(attempts) is not int or not 1 <= attempts <= 8
            or summary["step_returns"] != attempts or summary["step_errors"] != 0
            or any(audit[key] != expected for key, expected in
                (("verified_action_count", attempts), ("verified_uniform_action_count", attempts),
                 ("verified_step_return_count", attempts), ("verified_actor_record_count", attempts + 1)))):
        raise ValueError("profile raw/verified/model/cost evidence is incomplete")
    for saved in [*closed["saved_identities"], outer["coordinator_identity"], outer["child_identity"],
                  final_outer["coordinator_identity"], final_outer["child_identity"]]:
        _absence(saved)
    return {"passed": True, "references": references, "profile_actual_union_seconds": str(charge),
            "profile_evidence_bindings": [record(path) for path in evidence_paths],
            "profile_observed_wall_seconds": str(elapsed), "behavior_max_seconds": 3600,
            "forensic_reserve_seconds": FORENSIC_RESERVE, "engineering_block_seconds": BLOCK,
            "minimum_remaining_seconds_after_reserved_block": str(Decimal(CAP) - Decimal(ENTRY) - BLOCK)}


def execute(kind, freeze, profile_paths=(None, None, None)):
    started = time.monotonic_ns()
    plan = check(kind, freeze)
    admission = profile_admission(freeze, *profile_paths) if kind == "karto_behavior" else None
    run = output_path(kind)
    run.mkdir(parents=True, exist_ok=False)
    deadline = started + plan["activity_spec"]["activity_seconds"] * 10**9
    state = {"schema": "mr3-proxy2d-karto-activity-v1", "kind": kind, "freeze": freeze,
        "plan_sha256": sha(plan_path(kind)), "started_ns": started, "deadline_ns": deadline,
        "coordinator_identity": process_identity(os.getpid()), "phases": {}, "errors": [],
        "profile_admission": admission, "native_manifest": plan["native_manifest"],
        "passed": False, "qualification": False, "training_eligible": False, "native_credit": False,
        "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    exclusive(run / "activity_start.json", state)
    try:
        conformity = run / "conformity.json"
        commands = {
            "conformity": ["mr3_learning.proxy2d_conformity", "--freeze", freeze, "--output", str(conformity)],
            "conformity_review": ["mr3_learning.audit_proxy2d", str(run), "--freeze", freeze,
                "--conformity-only", str(conformity), "--output", str(run / "conformity_independent.json")],
            "collection": [MODULE, "collect", "--kind", kind, "--run", str(run)],
            "audit": ["mr3_learning.audit_proxy2d", str(run), "--freeze", freeze,
                "--output", str(run / "independent_audit.json")],
            "profile_report": [MODULE, "profile_report", "--kind", kind, "--run", str(run)],
        }
        for name, maximum in PHASES[kind].items():
            if name == "collection":
                if not all(state["phases"][key]["passed"] for key in ("conformity", "conformity_review")):
                    raise RuntimeError("conformity admission failed; no collection")
                exclusive(run / "collection_context.json", {"freeze": freeze,
                    "source_bindings": plan["source_bindings"],
                    "conformity": {"path": str(conformity), "sha256": sha(conformity)},
                    "activity_started_ns": started, "deadline_ns": deadline,
                    "activity_spec": plan["activity_spec"], "group_wall_seconds": plan["group_wall_seconds"],
                    "mapper": "karto", "mapper_library": str(ADAPTER), "native_manifest": plan["native_manifest"]})
            if name == "behavior_report":
                argv = ["/usr/bin/bash", "--noprofile", "--norc", "-c",
                    'source /opt/ros/humble/setup.bash && source "$1/install/setup.bash" '
                    '&& exec /usr/bin/python3 -B -m mr3_learning.audit_proxy2d_behavior '
                    '"$2" --freeze "$3" --output "$4"', "mr3-karto-behavior", str(ROS_ROOT),
                    str(run), freeze, str(run / "behavior_report.json")]
                state["phases"][name] = phase(run, name, argv, admitted_seconds(deadline, maximum),
                                             environment=ros_environment(238, 15910))
            else:
                state["phases"][name] = phase(run, name, [sys.executable, "-B", "-m", *commands[name]],
                                             admitted_seconds(deadline, maximum))
        state["passed"] = all(row["passed"] for row in state["phases"].values())
    except Exception as error:
        state["errors"].append(repr(error))
        if kind == "karto_behavior" and "behavior_report" not in state["phases"]:
            state["behavior_report_skipped_reason"] = repr(error)
    try:
        state["source_unchanged"] = bindings() == plan["source_bindings"]
        if admission is not None:
            for specification in [*admission["references"].values(), *admission["profile_evidence_bindings"]]:
                same_record(specification)
    except Exception as error:
        state["source_unchanged"] = False
        state["errors"].append(repr(error))
    state["ended_ns"] = time.monotonic_ns()
    state["passed"] = (state["passed"] and not state["errors"] and state["source_unchanged"]
                       and state["ended_ns"] <= deadline)
    exclusive(run / "activity_result.json", state)
    return state


def final(kind, run, outer_path, output):
    run, outer_path, output = Path(run).resolve(), Path(outer_path).resolve(), Path(output).resolve()
    if output.exists() or run != output_path(kind):
        raise ValueError("exclusive final output and exact Karto run required")
    outer, start = read(outer_path), read(run / "activity_start.json")
    result = {"schema": "mr3-proxy2d-karto-external-absence-v1", "kind": kind,
        "freeze": start["freeze"], "outer_reference": record(outer_path), "errors": [],
        "qualification": False, "training_eligible": False, "native_credit": False}
    try:
        references = None if start["profile_admission"] is None else start["profile_admission"]["references"]
        _outer(outer_path, _execute_argv(kind, start["freeze"], references), require_pass=False)
        if (start["kind"] != kind or start["plan_sha256"] != sha(plan_path(kind))
                or _owner(start["coordinator_identity"]) != _owner(outer["child_identity"])):
            raise ValueError("final execute identity/plan differs")
        native_manifest()
    except Exception as error:
        result["errors"].append(repr(error))
    saved = {}
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
            visit(read(path))
        except (OSError, ValueError) as error:
            result["errors"].append({"path": str(path), "error": repr(error)})
    present = []
    for saved_identity in saved.values():
        try:
            _absence(saved_identity)
        except Exception as error:
            present.append({"identity": saved_identity, "error": repr(error)})
    now = time.monotonic_ns()
    observed = Decimal(now - outer["started_monotonic_ns"]) / Decimal(10**9)
    activity = read(run / "activity_result.json")
    result.update(saved_identities=list(saved.values()), saved_identity_count=len(saved), present=present,
        absence_passed=not present and not result["errors"], observed_wall_seconds=str(observed),
        outer_engineering_seconds=outer["actual_child_wait_seconds"], activity_passed=activity.get("passed") is True,
        accounting_requires_this_external_actual_wait=True)
    result["passed"] = (result["absence_passed"] and result["activity_passed"]
        and outer.get("passed") is True and observed <= activity_spec(kind)["activity_seconds"])
    exclusive(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "preflight", "execute", "collect", "profile_report", "final"))
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--freeze")
    parser.add_argument("--entry-seconds", default=ENTRY)
    for name in ("run", "outer", "output", "profile-outer", "profile-final", "profile-final-outer"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    profile_paths = (args.profile_outer, args.profile_final, args.profile_final_outer)
    if args.operation == "build":
        result = build(args.kind, args.entry_seconds)
    elif args.operation == "preflight":
        check(args.kind, args.freeze)
        result = (profile_admission(args.freeze, *profile_paths) if args.kind == "karto_behavior"
                  else {"passed": True})
    elif args.operation == "execute":
        result = execute(args.kind, args.freeze, profile_paths)
    elif args.operation == "collect":
        context = read(args.run / "collection_context.json")
        if (Path(args.run).resolve() != output_path(args.kind)
                or context["activity_spec"] != activity_spec(args.kind)
                or context["mapper"] != "karto" or context["mapper_library"] != str(ADAPTER)
                or context["native_manifest"] != manifest_reference()):
            raise ValueError("collection CLI differs from its frozen context")
        native_manifest()
        result = collect(args.run, context["freeze"], context["source_bindings"], context["conformity"],
            context["activity_started_ns"], context["deadline_ns"], activity_spec=context["activity_spec"],
            group_wall_seconds=context["group_wall_seconds"], profile=args.kind == "karto_profile",
            mapper="karto", mapper_library=str(ADAPTER), native_manifest=context["native_manifest"])
        result["passed"] = not result["errors"] and result.get("closed") is True
    elif args.operation == "profile_report":
        if args.kind != "karto_profile" or Path(args.run).resolve() != output_path(args.kind):
            raise ValueError("profile report requires the unique Karto profile")
        result = profile_report(args.run)
    else:
        result = final(args.kind, args.run, args.outer, args.output)
    print(json.dumps({"operation": args.operation, "kind": args.kind, "passed": result.get("passed")}))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
