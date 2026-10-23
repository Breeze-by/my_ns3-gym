"""Complete reach-profile PPO audit with immutable policy/optimizer mathematics.

The original reader executes in a fresh private module. Its collecting-policy,
rollout tensors, finite-task GAE, optimizer/checkpoint, scalar and task tests
are unchanged. New source admission and every independent reach episode role
are conjunctive requirements; an old-reader PASS alone grants no credit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
import zlib

from . import audit_reach_cadence, audit_reach_information, audit_reach_runtime, audit_reach_peer_control
from . import audit_reach_controlled_physics, audit_reach_preparation
from .reach_audit_projection import project_module
from .reach_gates import PPO_READER_SHA256, load_native_gates
from .supervisor import (BINARY_REACH_GEOMETRY_RULE, validate_reach_geometry_rule)


CONTRACT = "mr3-reach-v1"
SCHEMA = "mr3-reach-ppo-offline-audit-v1"
WORKSPACE = Path(__file__).resolve().parents[7]
UNCHANGED_FUNCTIONS = ("parameter_changes", "native_decisions", "policy_replay", "audit_rollout",
                       "collecting_checkpoint", "audit_run")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_impl(plan_path):
    module, proof = project_module("audit_ppo.py", PPO_READER_SHA256, ())
    module.load_native_gates = lambda root, freeze: load_native_gates(root, freeze, plan_path)
    module.dispatch_controlled_physics = audit_reach_controlled_physics.dispatch_controlled_physics
    module.dispatch_controlled_readiness = audit_reach_controlled_physics.dispatch_controlled_readiness
    module.audit_odometry_cadence = SimpleNamespace(audit=audit_reach_cadence.audit)
    proof.update(global_dispatch_changes=["load_native_gates", "dispatch_controlled_physics",
                 "dispatch_controlled_readiness", "audit_odometry_cadence"],
                 unchanged_mathematical_functions=list(UNCHANGED_FUNCTIONS))
    return module, proof


def admission(metadata, freeze, plan_path=None, qualification_path=None, *, root=WORKSPACE):
    """Use the shared new-profile qualification validator; never interpret bools."""
    from .reach_preparation import validate_qualification
    require(metadata.get("safety_contract") == CONTRACT and metadata.get("freeze") == freeze,
            "PPO run lacks the exact reach profile/freeze declaration")
    paths = []
    for name, explicit in (("reach_plan", plan_path), ("reach_qualification", qualification_path)):
        declared = metadata.get(name)
        require(type(declared) is str and declared, "PPO metadata lacks "+name)
        selected = Path(declared).resolve()
        if explicit is not None:
            require(Path(explicit).resolve() == selected, "explicit "+name+" differs from original PPO metadata")
        paths.append(selected)
    plan_path, qualification_path = paths
    snapshots = {path: path.read_bytes() for path in paths}
    for name, path in (("reach_plan", plan_path), ("reach_qualification", qualification_path)):
        require(metadata.get(name+"_sha256") == sha(snapshots[path]),
                name+" bytes differ from original PPO admission metadata")
    proof = validate_qualification(qualification_path, plan_path, freeze, root=Path(root))
    require(metadata.get("seed_rule", "legacy") == json.loads(snapshots[plan_path]).get("seed_rule", "legacy"),
            "PPO seed rule differs from its native qualification")
    require(metadata.get("start_graph_rule", "original-seed-cell") == json.loads(snapshots[plan_path]).get("start_graph_rule", "original-seed-cell"),
            "PPO start graph rule differs from its native qualification")
    require(validate_reach_geometry_rule(metadata.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE),
                safety_contract=CONTRACT) == json.loads(snapshots[plan_path]).get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE),
            "PPO reach geometry rule differs from its native qualification")
    return plan_path, qualification_path, snapshots, proof


def audit_episode_conjunction(directory, freeze, preparation, *,
                              reach_geometry_rule=BINARY_REACH_GEOMETRY_RULE):
    """Independent full episode roles, without scripted probe workload gates."""
    directory = Path(directory)
    row = {"directory": str(directory), "passed": False, "errors": []}
    operations = (
        ("information", lambda: audit_reach_information.audit_episode(directory, freeze)),
        ("runtime_drive", lambda: audit_reach_runtime.audit_episode(directory, freeze)),
        ("peer_control_fifo", lambda: audit_reach_peer_control.audit_episode(directory, freeze)),
        ("observation_archives", lambda: preparation.audit_archives(directory)),
        ("activity", lambda: preparation.audit_activity(directory)),
        ("execution_inputs", lambda: preparation.audit_execution_inputs(directory, row.get("peer_control_fifo"))),
    )
    for name, operation in operations:
        try:
            report = operation()
            row[name] = report
            require(type(report) is dict and report.get("passed") is True
                    and not report.get("errors"), name+" independent gate failed")
            if name in ("information", "peer_control_fifo"):
                require(report.get("safety_contract") == CONTRACT and report.get("freeze") == freeze,
                        name+" profile/freeze identity differs")
            if name == "runtime_drive":
                require(report.get("contract") == CONTRACT and report.get("freeze") == freeze
                        and report.get("independent_necessary_replay") is True
                        and report.get("continuous_physical_model_proved") is False
                        and report.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) == reach_geometry_rule,
                        "runtime role lacks independent conditional replay")
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError, OverflowError, zlib.error) as error:
            row["errors"].append(name+": "+str(error))
    row["passed"] = not row["errors"]
    return row


def audit_run(directory, freeze, plan_path=None, qualification_path=None):
    directory = Path(directory).resolve()
    require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze), "exact source freeze required")
    metadata_path, summary_path = directory/"metadata.json", directory/"summary.json"
    stable = {path: path.read_bytes() for path in (metadata_path, summary_path)}
    metadata = json.loads(stable[metadata_path])
    summary = json.loads(stable[summary_path])
    require(summary.get("safety_contract") == CONTRACT and summary.get("freeze") == freeze,
            "PPO summary mixes source freeze or safety contract")
    plan_path, qualification_path, admission_inputs, qualification = admission(
        metadata, freeze, plan_path, qualification_path)
    stable.update(admission_inputs)
    plan = json.loads(admission_inputs[plan_path])
    geometry_rule = validate_reach_geometry_rule(
        plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE), safety_contract=CONTRACT)
    require(summary.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) == geometry_rule,
            "PPO summary reach geometry rule differs from its native qualification")
    source_inputs = {}
    for relative, expected in plan["source_bindings"].items():
        path = WORKSPACE/relative
        raw = path.read_bytes()
        require(sha(raw) == expected, "PPO source differs from declared reach plan: "+relative)
        source_inputs[path] = raw
    require(Path(__file__).resolve() in source_inputs, "new PPO entry is absent from the reach source plan")
    discovered = sorted(path.parent.resolve() for path in (directory/"native").glob(
        "round*/worker*/episode*/metadata.json"))
    require(discovered, "no actual reach native attempts")
    for episode in discovered:
        path = episode/"metadata.json"
        raw = path.read_bytes(); stable[path] = raw
        own = json.loads(raw)
        require(own.get("freeze") == freeze and own.get("safety_contract") == CONTRACT
                and own.get("execution_phase_protocol") == "mr3-controlled-execution-phase-v2"
                and own.get("reset_handshake") == "paused-controlled-state-peer-guard-storage-v2",
                "native attempt has mixed/legacy profile identity: "+str(episode))
        require(own.get("seed_rule", "legacy") == plan.get("seed_rule", "legacy"),
                "native attempt seed rule differs from qualification plan")
        require(own.get("start_graph_rule", "original-seed-cell") == plan.get("start_graph_rule", "original-seed-cell"),
                "native attempt start graph rule differs from qualification plan")
        require(own.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) == geometry_rule,
                "native attempt reach geometry rule differs from qualification plan")
        supervisor_path = episode / "supervisor_metadata.json"
        supervisor_raw = supervisor_path.read_bytes(); stable[supervisor_path] = supervisor_raw
        require(json.loads(supervisor_raw).get("seed_rule", "legacy") == plan.get("seed_rule", "legacy"),
                "native supervisor seed rule differs from qualification plan")
        require(json.loads(supervisor_raw).get("start_graph_rule", "original-seed-cell") == plan.get("start_graph_rule", "original-seed-cell"),
                "native supervisor start graph rule differs from qualification plan")
        require(json.loads(supervisor_raw).get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) == geometry_rule,
                "native supervisor reach geometry rule differs from qualification plan")
    module, projection = load_impl(plan_path)
    preparation, preparation_proof = audit_reach_preparation.load_impl(plan_path)
    result = module.audit_run(directory, freeze)
    result.update(schema=SCHEMA, safety_contract=CONTRACT,
                  immutable_reader_projection=projection,
                  full_episode_helper_projection=preparation_proof,
                  reach_plan=str(plan_path), reach_qualification=str(qualification_path),
                  qualification_binding=qualification, reach_episodes=[],
                  continuous_physical_model_proved=False, old_profile_qualification_credit_reused=False)
    if geometry_rule != BINARY_REACH_GEOMETRY_RULE:
        result["reach_geometry_rule"] = geometry_rule
    for episode in discovered:
        report = audit_episode_conjunction(episode, freeze, preparation,
            **({"reach_geometry_rule": geometry_rule} if geometry_rule != BINARY_REACH_GEOMETRY_RULE else {}))
        result["reach_episodes"].append(report)
        if not report["passed"]:
            result["errors"].append(str(episode)+": independent reach conjunction: "+"; ".join(report["errors"]))
    require(set(Path(row["directory"]).resolve() for row in result["episodes"]) == set(discovered),
            "immutable reader omitted an actual native attempt")
    by_directory = {Path(row["directory"]).resolve(): row for row in result["reach_episodes"]}
    result["task_successes"] = sum(row.get("task", {}).get("success") is True
        and not row["errors"] and by_directory[Path(row["directory"]).resolve()]["passed"]
        for row in result["episodes"])
    result["task_failures"] = [{"epoch": row.get("epoch"), "task": row.get("task"),
        "audit_errors": row["errors"], "reach_audit_errors": by_directory[Path(row["directory"]).resolve()]["errors"]}
        for row in result["episodes"] if row["errors"] or not row.get("task", {}).get("success")
        or not by_directory[Path(row["directory"]).resolve()]["passed"]]
    unchanged = True
    for path, original in {**stable, **source_inputs}.items():
        try:
            require(path.read_bytes() == original, "PPO admission/native input changed during audit: "+str(path))
        except (OSError, ValueError) as error:
            unchanged = False
            result["errors"].append(str(error))
    result["admission_input_bindings"] = [{"path": str(path), "sha256": sha(raw), "bytes": len(raw)}
                                          for path, raw in stable.items()]
    result["reach_source_stability"] = {"files": len(source_inputs),
                                         "all_original_bytes_checked_at_end": True,
                                         "all_admission_and_source_bytes_unchanged": unchanged}
    result["passed"] = result.get("passed") is True and not result["errors"]
    result["scope"] = ("All original policy/rollout/GAE/optimizer/scalar/task and native closure gates plus new "
        "source-bound qualification, v2 physics/readiness, cadence, received information, runtime/drive, "
        "peer/control/FIFO, full observation/navigation archives, received activity and output topology/costmaps. "
        "PPO evidence only; continuous plant remains conditional, no statistical95% or network credit.")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists(): parser.error("audit output exists; preserve the original result")
    import torch
    torch.set_num_threads(1)
    result = audit_run(args.directory, args.freeze, args.plan, args.qualification)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False); output.write("\n")
    print(json.dumps({key: result[key] for key in ("passed", "native_attempts", "task_successes", "errors")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
