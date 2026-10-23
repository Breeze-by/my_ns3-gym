"""Finite reach diagnostic evidence, without qualification or training credit.

Reuse the original native/contact/command/scalar/evaluator predicates and the
existing received-input readers. Independent information, cadence/runtime,
FIFO and live native custody remain separate results. No scripted movement
coverage is required and no scientific threshold is changed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zlib


SCHEMA = "mr3-reach-feasibility-diagnostic-plan-v1"
CONTRACT = "mr3-reach-v1"
WORKSPACE = Path(__file__).resolve().parents[7]
ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError,
          OverflowError, AssertionError, zlib.error, subprocess.SubprocessError)


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bound_sources(plan_path, directory, freeze, root=WORKSPACE):
    """Check the complete current inventory against both plan and Git bytes."""
    from .reach_preparation import source_inventory
    root, plan_path, directory = Path(root).resolve(), Path(plan_path).resolve(), Path(directory).resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "exact source freeze required")
    stable = {plan_path: plan_path.read_bytes()}
    plan = json.loads(stable[plan_path])
    require(plan.get("schema") == SCHEMA and plan.get("safety_contract") == CONTRACT
            and plan.get("robots_per_environment") == 3
            and plan.get("optimizer_steps") == plan.get("gpu_calls") == 0
            and plan.get("qualification") is False and plan.get("training_eligible") is False,
            "explicit non-training diagnostic scope required")
    require(Path(plan["run_directory"]).resolve() == directory
            and type(plan["expected_episodes"]) is int and plan["expected_episodes"] > 0,
            "diagnostic run/episode declaration differs")
    bindings = plan["source_bindings"]
    require(isinstance(bindings, dict) and source_inventory(root) <= bindings.keys(),
            "diagnostic runtime/source inventory is incomplete")
    paths = set(bindings) | {str(plan_path.relative_to(root)),
                            str(Path(plan["custody_binding"]).resolve().relative_to(root))}
    proof = {}
    for relative in sorted(paths):
        path = root / relative
        require(not Path(relative).is_absolute() and path.resolve().is_relative_to(root),
                "source binding is outside the workspace")
        raw = path.read_bytes()
        frozen = subprocess.check_output(["git", "show", freeze + ":" + relative],
                                         cwd=root, stderr=subprocess.PIPE)
        require(raw == frozen and (relative not in bindings or digest(raw) == bindings[relative]),
                "diagnostic source differs from plan/Git freeze: " + relative)
        stable[path] = raw
        proof[relative] = {"sha256": digest(raw), "git_source": freeze + ":" + relative}
    return plan, proof, stable


def input_inventory(directory):
    """Hash complete closed evidence bytes before and after the diagnostic."""
    result = {}
    for path in sorted(Path(directory).rglob("*")):
        if not path.is_file():
            continue
        before = path.stat()
        value = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                value.update(chunk)
        after = path.stat()
        stat = lambda entry: (entry.st_dev, entry.st_ino, entry.st_size,
                              entry.st_mtime_ns, entry.st_ctime_ns)
        require(stat(before) == stat(after), "diagnostic input changed while read: " + str(path))
        result[str(path)] = {"sha256": value.hexdigest(), "bytes": after.st_size,
                             "stat": list(stat(after))}
    return result


def fifo_results(paths, episodes, freeze):
    """Accept real, complete independent FIFO leaves and bind their raw inputs."""
    result, stable = {}, {}
    for selected in paths:
        path = Path(selected).resolve()
        raw = path.read_bytes()
        leaf = json.loads(raw)
        episode = Path(leaf["episode"]).resolve()
        require(episode in episodes and episode not in result
                and leaf.get("schema") == "mr3-reach-peer-control-fifo-review-v1"
                and leaf.get("safety_contract") == CONTRACT and leaf.get("freeze") == freeze
                and leaf.get("passed") is True and leaf.get("errors") == [],
                "independent FIFO leaf failed/mixed/duplicated")
        stable[path] = raw
        require(isinstance(leaf.get("bindings"), dict) and leaf["bindings"],
                "independent FIFO leaf has no actual input bindings")
        for name, expected in leaf["bindings"].items():
            bound = Path(name)
            content = bound.read_bytes()
            require(bound.resolve().is_relative_to(episode)
                    and digest(content) == expected["sha256"] and len(content) == expected["bytes"],
                    "independent FIFO raw binding differs")
        result[episode] = leaf
    return result, stable


def audit_episode(directory, freeze, gates, preparation, fifo=None):
    """Use the native PPO episode gates, without policy/optimizer/probe gates."""
    from . import audit_evaluator_phase, audit_reach_controlled_physics
    phase, base, native, command, scalar, _ = gates
    directory = Path(directory).resolve()
    cache = {} if fifo is None else {directory: fifo}
    row = {"directory": str(directory), "errors": [], "passed": False}

    def check(name, operation):
        try:
            value = operation()
            row[name] = value
            require(isinstance(value, dict) and value.get("passed") is True
                    and not value.get("errors"), name + " independent gate failed")
        except ERRORS as error:
            row["errors"].append(name + ": " + str(error))

    def original_native():
        original_physics = native.audit_physics
        original_readiness = native.audit_initial_inputs_ready
        try:
            audit_reach_controlled_physics.dispatch_controlled_physics(native, [directory], cache)
            audit_reach_controlled_physics.dispatch_controlled_readiness(native, [directory], cache)
            return phase.corrected_audit(base, native, command, [directory])
        finally:
            native.audit_physics = original_physics
            native.audit_initial_inputs_ready = original_readiness

    check("native", original_native)
    row["peer_control_fifo"] = cache.get(directory)
    row["fifo_source"] = "independent_result" if fifo is not None else "embedded_original_dispatch"
    check("scalar", lambda: scalar.audit_episode(directory, freeze))
    check("evaluator_phase", lambda: audit_evaluator_phase.audit_episode(directory))
    check("observation_archives", lambda: preparation.audit_archives(directory))
    check("activity", lambda: preparation.audit_activity(directory))
    check("execution_inputs", lambda: preparation.audit_execution_inputs(directory, cache.get(directory)))
    row["passed"] = not row["errors"]
    return row


def audit(directory, freeze, plan_path, *, fifo_paths=(), root=WORKSPACE):
    directory = Path(directory).resolve()
    result = {"schema": "mr3-reach-feasibility-base-audit-v1", "directory": str(directory),
              "freeze": freeze, "passed": False, "errors": [], "episodes": [],
              "qualification": False, "training_eligible": False,
              "separate_results_required": ["information", "cadence_with_runtime", "peer_control_fifo",
                                            "live_native_custody_and_closure", "external_process_absence"],
              "scripted_turn_reversal_or_minimum_motion_coverage_required": False,
              "scope": "Original native/contact/clock/command/scalar/evaluator and received-input necessities; "
                       "no policy, qualification, continuous-plant or 95% reliability credit."}
    stable, before = {}, None
    try:
        plan, source_proof, stable = bound_sources(plan_path, directory, freeze, root)
        result["source_proof"] = source_proof
        before = input_inventory(directory)
        result["input_proof"] = before
        episodes = sorted(path.resolve() for path in directory.glob("worker*/episode*") if path.is_dir())
        require(episodes, "no actual diagnostic attempts")
        if len(episodes) != plan["expected_episodes"]:
            result["errors"].append("actual diagnostic attempt inventory is incomplete")
        fifo, fifo_stable = fifo_results(fifo_paths, episodes, freeze)
        stable.update(fifo_stable)
        from .reach_gates import _load_versioned_native_gates
        from .audit_reach_preparation import load_impl
        gates = _load_versioned_native_gates(Path(root), freeze, source_proof,
                                             plan["source_bindings"], plan["custody_binding"])
        preparation, projection = load_impl(plan_path)
        result["native_gate_source_proof"] = gates[-1]
        result["preparation_helper_projection"] = projection
        for episode in episodes:
            try:
                row = audit_episode(episode, freeze, gates, preparation, fifo.get(episode))
            except ERRORS as error:
                row = {"directory": str(episode), "passed": False, "errors": [str(error)]}
            result["episodes"].append(row)
            result["errors"].extend(str(episode) + ": " + error for error in row["errors"])
    except ERRORS as error:
        result["errors"].append(str(error))
    try:
        require(stable and all(path.read_bytes() == raw for path, raw in stable.items()),
                "diagnostic source/plan/FIFO result changed before verdict")
        result["source_and_receipt_bytes_unchanged"] = True
    except ERRORS as error:
        result["source_and_receipt_bytes_unchanged"] = False
        result["errors"].append(str(error))
    try:
        require(before is not None and input_inventory(directory) == before,
                "diagnostic input inventory/bytes changed before verdict")
        result["input_bytes_unchanged"] = True
    except ERRORS as error:
        result["input_bytes_unchanged"] = False
        result["errors"].append(str(error))
    result["passed"] = bool(result["episodes"]) and not result["errors"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--fifo-result", action="append", type=Path, default=[])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.resolve().is_relative_to(args.directory.resolve()):
        parser.error("use an exclusive output outside the closed native input directory")
    result = audit(args.directory, args.freeze, args.plan, fifo_paths=args.fifo_result)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "qualification": False, "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
