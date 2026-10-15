#!/usr/bin/env python3
"""Independent offline command-time gate; no ROS, simulator, or policy execution.

Bind each submitted command to its actual epoch/command/observation receipt and
replay its bounded validity window using integer nanosecond endpoints. This
adds no goal, mask, reward, contact, or complete-episode credit. The original
auditor and historical audit outputs remain unchanged.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


METHOD = "mr3-command-time-integer-endpoints-v1"
TTL_NS = 2_000_000_000
TIME_REJECTION = "expired_or_invalid_command_time"
ROS = "ros2_ws/ros2-multi-robot-automap/"
PINNED_AUDITORS = {
    ROS + "scripts/audit_mr3_env.py":
        "25ce0b466d988595934f26a0cfb7a81a445632b1e755f2462b80698371b272e8",
    ROS + "scripts/audit_mr3_adapter_probe.py":
        "fdd415da1b01d7da6219d21a2fa8e184484b696d33c3e736bde8ca165bb65e6a",
    ROS + "scripts/ros_smoke_test.py":
        "f130b1157b4855089d51a6b1f22e57e0b5683b40624cc8697e3bb76fb3659d1a",
}


def repository_root():
    return next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists())


def load_auditor(root=None):
    """Reuse the unchanged auditor's evidence, stamp, and terminal-reuse rules."""
    root = repository_root() if root is None else Path(root)
    proof = {}
    for relative, expected in PINNED_AUDITORS.items():
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError("original auditor/dependency SHA mismatch: " + relative)
        proof[relative] = digest
    modules = {}
    scripts = root / ROS / "scripts"
    for name in ("ros_smoke_test", "audit_mr3_adapter_probe", "audit_mr3_env"):
        module_name = "mr3_command_time_base" if name == "audit_mr3_env" else name
        spec = importlib.util.spec_from_file_location(module_name, scripts / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules["audit_mr3_env"], proof


def command_window(audit, command, receipt_stamp):
    """Preserve raw stamps; separately convert their endpoints before subtraction."""
    now_ns = audit.nanoseconds(receipt_stamp)
    try:
        created_ns = audit.nanoseconds(command.get("created_at"))
        expires_ns = audit.nanoseconds(command.get("expires_at"))
    except (ValueError, TypeError, OverflowError):
        return {"valid": False, "receipt_time_ns": now_ns,
                "created_time_ns": None, "expires_time_ns": None, "ttl_ns": None,
                "invalidity": ["invalid_command_timestamp"]}
    ttl_ns = expires_ns - created_ns
    invalidity = []
    if created_ns > now_ns:
        invalidity.append("created_in_future")
    if now_ns >= expires_ns:
        invalidity.append("expired_at_receipt")
    if ttl_ns <= 0:
        invalidity.append("nonpositive_ttl")
    if ttl_ns > TTL_NS:
        invalidity.append("ttl_exceeds_two_seconds")
    return {"valid": not invalidity, "receipt_time_ns": now_ns,
            "created_time_ns": created_ns, "expires_time_ns": expires_ns,
            "ttl_ns": ttl_ns, "invalidity": invalidity}


def audit_command_times(rows, transitions, epoch, allow_incomplete=False, *, auditor=None):
    """Add this gate after the original audit_protocol; do not replace its checks."""
    audit = load_auditor()[0] if auditor is None else auditor
    require = audit.require
    require(bool(transitions) and transitions[0].get("kind") == "reset",
            "command-time gate lacks the initial reset")
    commands, excluded = {}, []
    for index, row in enumerate(transitions[1:], 1):
        require(row.get("kind") == "step", "unexpected transition in command-time replay")
        info = row["info"]
        if info.get("terminal_observation_reused") is True:
            audit.validate_reused_terminal(transitions[index - 1], row, epoch, index)
            excluded.append(index)
            continue
        require(info.get("action_submitted") is not False,
                "ordinary step falsely declares no submitted action")
        command = info.get("command")
        require(isinstance(command, dict) and command.get("epoch") == epoch,
                "submitted command missing or has wrong epoch")
        command_id, observation = command.get("command_id"), command.get("observation_sequence")
        require(type(command_id) is int and command_id >= 0 and command_id not in commands,
                "invalid or duplicate sampled command identity")
        require(type(observation) is int and observation >= 0,
                "invalid sampled command observation identity")
        previous = transitions[index - 1]["snapshot"]
        require(previous.get("epoch") == epoch and observation == previous.get("sequence")
                and command.get("observation_digest") == previous.get("digest"),
                "command does not bind its preceding delivered snapshot")
        commands[command_id] = (index, command, info, row["snapshot"])
    seen, bindings, errors = set(), [], []
    for event in rows:
        if event.get("kind") not in ("action", "action_rejected"):
            continue
        require(event.get("epoch") == epoch, "action receipt epoch mismatch")
        payload = event["payload"]
        command_id = payload.get("command_id")
        require(type(command_id) is int and command_id in commands and command_id not in seen,
                "unbound or duplicate action receipt command identity")
        step, command, info, snapshot = commands[command_id]
        require(type(payload.get("observation_sequence")) is int and
                payload["observation_sequence"] == command["observation_sequence"],
                "action receipt observation identity mismatch")
        now_ns = audit.nanoseconds(event.get("stamp"))
        require(audit.nanoseconds(info["reward_diagnostics"]["step_start"]) <= now_ns <=
                audit.nanoseconds(snapshot["source_stamp"]),
                "action receipt outside its sampled physical interval")
        seen.add(command_id)
        window = command_window(audit, command, event["stamp"])
        accepted = event["kind"] == "action"
        reason = None if accepted else payload.get("reason")
        require(accepted or isinstance(reason, str) and bool(reason),
                "action rejection lacks its original reason")
        if accepted:
            require(payload.get("action") == command.get("action") and
                    payload.get("observation_digest") == command.get("observation_digest"),
                    "accepted receipt differs from its submitted action/digest")
        failure = None
        if accepted and not window["valid"]:
            failure = "invalid_command_time_accepted"
        elif not accepted and reason == TIME_REJECTION and window["valid"]:
            failure = "valid_command_time_falsely_rejected"
        elif accepted and any(result in ("invalid_ttl", "expired")
                              for result in payload.get("results", {}).values()):
            failure = "valid_adapter_time_rejected_by_dispatcher"
        if failure:
            errors.append(f"command {command_id}/observation {command['observation_sequence']}: "
                          + failure)
        created, expires = command.get("created_at"), command.get("expires_at")
        if type(created) is float and not audit.number(created):
            created = repr(created)
        if type(expires) is float and not audit.number(expires):
            expires = repr(expires)
        bindings.append({"epoch": epoch, "step_sequence": step, "command_id": command_id,
                         "observation_sequence": command["observation_sequence"],
                         "action": command.get("action"),
                         "created_at": created, "expires_at": expires,
                         "receipt_stamp": event["stamp"],
                         "receipt_kind": event["kind"], "rejection_reason": reason,
                         **window, "failure": failure})
    require(set(commands) == seen, "submitted command lacks its actual action receipt")
    return {"method": METHOD, "passed": not errors, "errors": errors,
            "commands_checked": len(commands), "accepted_commands": sum(
                row["receipt_kind"] == "action" for row in bindings),
            "rejected_commands": sum(row["receipt_kind"] == "action_rejected"
                                     for row in bindings),
            "excluded_no_action_terminal_steps": excluded, "bindings": bindings,
            "complete_episode_credit": False,
            "scope": ("declared incomplete command prefix only" if allow_incomplete else
                      "submitted command validity and receipt reason only"),
            "other_rejection_reasons_revalidated": False,
            "reward_contact_mask_ownership_closure_revalidated": False}


def audit_episode(directory, freeze, expected_fault_prefix=False, *, auditor=None):
    audit = load_auditor()[0] if auditor is None else auditor
    evidence = audit.Evidence(directory)
    metadata = evidence.json("metadata.json")
    epoch = metadata["epoch"]
    audit.require(metadata.get("freeze") == freeze, "episode source freeze mismatch")
    transitions = evidence.rows("transitions.jsonl")
    events = evidence.rows("adapter.jsonl")
    if expected_fault_prefix:
        audit.require(not (Path(directory) / "summary.json").exists(),
                      "declared incomplete prefix has a normal summary")
    else:
        summary = evidence.json("summary.json")
        audit.require(summary.get("epoch") == epoch, "normal summary epoch mismatch")
    audit.audit_processes(evidence.json("supervisor_metadata.json"),
                          evidence.json("supervisor_shutdown.json"), epoch, expected_fault_prefix)
    result = evidence.check("command time replay", lambda: audit_command_times(
        events, transitions, epoch, expected_fault_prefix, auditor=audit))
    if result is not None:
        evidence.errors.extend(result["errors"])
    return {"directory": str(directory), "epoch": epoch, "freeze": freeze,
            "expected_infrastructure_fault": expected_fault_prefix,
            "complete_episode_credit": False, "command_time": result,
            "evidence_sha256": evidence.hashes, "passed": not evidence.errors,
            "errors": evidence.errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--expected-fault-prefix", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new evidence path")
    audit, proof = load_auditor()
    result = audit_episode(args.directory, args.freeze, args.expected_fault_prefix, auditor=audit)
    result.update({"schema": "mr3-command-time-audit-v7", "method": METHOD,
                   "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "original_auditor_sha256": proof,
                   "command": [sys.executable, "-B", str(Path(__file__)),
                               *(sys.argv[1:] if argv is None else argv)]})
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "output": str(args.output),
                      "errors": result["errors"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
