#!/usr/bin/env python3
"""Offline c8d contact-phase correction; no ROS initialization or simulation.

Only the frozen auditor's audit_contacts is replaced. Lifetime gap maxima remain
unaltered diagnostics. Task health is proved from the frozen started/latch
invariant plus the actual paused release/seq0/physics evidence, not reconstructed
per-message gap endpoints. Original audit outputs and failures are never edited.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


FREEZE = "c8d483228ecb0105c905459578eddbb4a23d4520"
METHOD = "mr3-contact-task-phase-frozen-latch-v2"
ROS = "ros2_ws/ros2-multi-robot-automap/"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
PINNED_RUNTIME = {
    ROS + "scripts/audit_mr3_env.py":
        "25ce0b466d988595934f26a0cfb7a81a445632b1e755f2462b80698371b272e8",
    ROS + "scripts/audit_mr3_adapter_probe.py":
        "fdd415da1b01d7da6219d21a2fa8e184484b696d33c3e736bde8ca165bb65e6a",
    ROS + "scripts/ros_smoke_test.py":
        "f130b1157b4855089d51a6b1f22e57e0b5683b40624cc8697e3bb76fb3659d1a",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_contacts.py":
        "9d661498b3748d409dbb59ccd59524d5152d85ec93ee30128aebaf0a8a09fa17",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py":
        "bd0c2e43dbbb4258e4e1ee537fbdbe512211576eb930d5f8862d787dc73e48af",
    ROS + "scripts/mr3_env_worker.py":
        "f8f1fe4da9cb27f9cb7b0d30d20eca8cd72cc92fe670815ad21c2b7d40af1fad",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py":
        "ddd2e48d0ae8d9c7b09b60e3c44116e5a575d0c91d3bde6c81fdfe1a5d7d2226",
}
PINNED_DOCUMENTS = {
    WIRELESS + "MR3_TASK_CONTRACT.md":
        "fcc1cedbc524a3d55443c887201f13f58fbd442e5600f1d8ad5cad84b7346c48",
    WIRELESS + "MR3_ENV_CONTRACT.md":
        "3119e295538dacd412407ce6b3c9ecf371adb08b47a1f5efab1bbff749841739",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def repository_root():
    return next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists())


def verify_sources(root):
    """Executable sources must match; normative docs come from immutable git blobs."""
    proof = {}
    for relative, expected in PINNED_RUNTIME.items():
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        require(digest == expected, "frozen runtime/source SHA mismatch: " + relative)
        proof[relative] = {"sha256": digest, "source": "worktree bytes matching " + FREEZE}
    for relative, expected in PINNED_DOCUMENTS.items():
        payload = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=root)
        digest = hashlib.sha256(payload).hexdigest()
        require(digest == expected, "frozen document SHA mismatch: " + relative)
        proof[relative] = {"sha256": digest, "source": FREEZE + ":" + relative}
    return proof


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_auditor(root):
    proof = verify_sources(root)
    scripts = root / ROS / "scripts"
    # Explicit paths avoid ambient sys.path or cached modules selecting another source.
    load_module("ros_smoke_test", scripts / "ros_smoke_test.py")
    load_module("audit_mr3_adapter_probe", scripts / "audit_mr3_adapter_probe.py")
    return load_module("mr3_c8d_env_audit", scripts / "audit_mr3_env.py"), proof


def release_context(audit, directory):
    """Bind the frozen pause->release->ready wait->seq0 order to saved endpoints."""
    evidence = audit.Evidence(directory)
    metadata = evidence.json("metadata.json")
    epoch = metadata["epoch"]
    require(metadata.get("freeze") == FREEZE, "contact phase requires the c8d runtime freeze")
    arguments = {}
    for argument in metadata["command"]:
        if ":=" in argument:
            key, value = argument.split(":=", 1)
            require(key not in arguments, "ambiguous launch parameter " + key)
            arguments[key] = value
    expected = {"execution_mode": "adapter", "mr3_stepped": "true",
                "training_reward_enabled": "true", "enable_task_evaluator": "true",
                "robot_count": "3", "evaluation_episode_id": epoch, "mr3_episode_epoch": epoch}
    require(all(arguments.get(key) == value for key, value in expected.items()),
            "release is not the frozen stepped three-robot evaluator path")
    transitions, physics = evidence.rows("transitions.jsonl"), evidence.rows("physics.jsonl")
    require(bool(transitions) and transitions[0].get("kind") == "reset", "missing release reset")
    reset, info = transitions[0], transitions[0]["info"]
    release = info["release_time_ns"]
    require(type(release) is int and release > 0 and info.get("epoch") == epoch
            and info.get("scheduler") == "mr3-physical-20ms-v1"
            and audit.nanoseconds(reset["snapshot"]["source_stamp"]) == release,
            "initial snapshot/release epoch/time mismatch")
    audit.audit_physics(physics, epoch, release)
    require(info.get("initial_pause_time_ns") == physics[0]["end_time_ns"] <= release,
            "initial pause does not bind release physics")
    boundary = [index for index, row in enumerate(physics) if row["end_time_ns"] == release]
    require(len(boundary) == 1 and boundary[0] + 1 < len(physics)
            and physics[boundary[0] + 1]["start_time_ns"] == release
            and physics[boundary[0] + 1]["steps"] == 20,
            "release lacks a unique paused boundary before the first policy quantum")
    diagnostic = info["reward_diagnostics"]
    require(diagnostic.get("kind") == "reward_reset_binding"
            and diagnostic.get("reset_bound") is True and diagnostic.get("epoch") == epoch
            and type(diagnostic.get("sequence")) is int and diagnostic["sequence"] == 0
            and diagnostic.get("reward") == 0 and diagnostic.get("delta_sim_time") == 0
            and diagnostic.get("terminated") is False and diagnostic.get("truncated") is False
            and all(audit.nanoseconds(diagnostic.get(key)) == release
                    for key in ("step_start", "effective_step_end"))
            and diagnostic["map_watermark"]["payload_sha256"] ==
            info["watermarks"]["map_payload_sha256"],
            "actual seq0 does not bind evaluator start to paused release")
    adapter = evidence.rows("adapter.jsonl")
    starts = [row for row in adapter if row.get("kind") == "task_start"]
    require(len(starts) == 1 and starts[0].get("epoch") == epoch
            and audit.nanoseconds(starts[0].get("stamp")) == release
            and audit.nanoseconds(starts[0]["payload"].get("start_sim_time_sec")) == release,
            "actual adapter task_start does not bind paused release")
    observations = [row for row in adapter if row.get("kind") == "observation"
                    and row.get("payload", {}).get("sequence") == reset["snapshot"]["sequence"]]
    require(len(observations) == 1 and adapter.index(starts[0]) < adapter.index(observations[0]),
            "initial observation does not follow the actual release")
    readiness = audit.audit_initial_inputs_ready(metadata, transitions, adapter, epoch)
    require(readiness.get("required") is True and readiness.get("proven") is True,
            "release lacks the actual initial delivered-input handshake")
    return {"epoch": epoch, "release_time_ns": release,
            "initial_pause_time_ns": info["initial_pause_time_ns"],
            "actual_seq0_binding": True, "actual_task_start": True,
            "independent_raw_reward_ready_payload_available": False,
            "ready_wait_proof": "pinned worker/evaluator causal order plus saved seq0 response",
            "no_positive_physics_window": "worker waits for ready/seq0 while physics is paused",
            "context_evidence_sha256": evidence.hashes}


def audit_contact_phase(audit, evaluator, launch_text, epoch, context):
    """Preserve raw/age/latch gates; separate lifetime maxima from task health."""
    checks = audit.Evidence(".")
    raw = checks.check("raw contact sequence", lambda:
                       audit.validate_contact_reducer_summary(launch_text))
    lifetime = {}

    def freshness():
        require(isinstance(context, dict) and "error" not in context,
                "paused release proof unavailable: " + str(context))
        require(context["epoch"] == epoch and evaluator.get("schema_version") == 4
                and evaluator.get("episode_id") == epoch and evaluator.get("robot_count") == 3
                and evaluator.get("contact_component_count_per_robot") == 6,
                "evaluator identity/schema/component count mismatch")
        release = context["release_time_ns"]
        require(audit.nanoseconds(evaluator.get("start_sim_time_sec")) == release
                and evaluator.get("task_start_barrier") == "controller_release",
                "evaluator task start differs from paused release")
        subscribed = evaluator.get("contact_subscription_started_sim_time_sec")
        require(evaluator.get("contact_subscription_bootstrap_state") ==
                "contact_subscriptions_started" and audit.number(subscribed)
                and 0 < subscribed <= release / audit.NS
                and "contact_clock_overflow_diagnostic" in evaluator
                and evaluator["contact_clock_overflow_diagnostic"] is None
                and evaluator.get("control_failure") != "contact_clock_desynchronization",
                "invalid contact bootstrap or contact-clock overflow/desynchronization")
        end = evaluator.get("end_sim_time_sec")
        require(audit.number(end) and audit.nanoseconds(end) >= release,
                "evaluator end precedes release")
        summary = evaluator["contact_monitor_summary"]
        require(evaluator.get("collision_monitoring_active") is True
                and evaluator.get("collision_monitoring_fresh") is True
                and summary.get("fresh") is True and summary.get("ever_unhealthy") is False
                and summary.get("latched_issues") == {}
                and audit.close(summary.get("max_age_sec"), .5),
                "contact monitoring stale, interrupted or gate changed")
        require(set(summary["components"]) == set(audit.ROBOTS), "contact robot coverage differs")
        for name in audit.ROBOTS:
            require(set(summary["components"][name]) == set(audit.COMPONENTS),
                    "contact component coverage differs")
            for part in audit.COMPONENTS:
                row = summary["components"][name][part]
                require(type(row.get("accepted_message_count")) is int
                        and row["accepted_message_count"] > 0
                        and type(row.get("invalid_timestamp_count")) is int
                        and row["invalid_timestamp_count"] == 0
                        and type(row.get("duplicate_message_count")) is int
                        and row["duplicate_message_count"] == 0 and row.get("health_reason") == "",
                        "invalid contact source " + name + "/" + part)
                for age, stamp in (("source_age_sec", "last_source_time_sec"),
                                   ("receipt_age_sec", "last_receipt_time_sec")):
                    require(audit.number(row.get(age)) and 0 <= row[age] <= .500001
                            and audit.number(row.get(stamp)) and 0 < row[stamp] <= end
                            and audit.close(end - row[stamp], row[age]),
                            "current contact freshness failed: " + name + "/" + part + "/" + age)
                gaps = {key: row.get(key) for key in ("max_source_gap_sec", "max_receipt_gap_sec")}
                require(all(audit.number(value) and value >= 0 for value in gaps.values()),
                        "invalid lifetime gap diagnostic " + name + "/" + part)
                lifetime[name + "/" + part] = gaps
        return True

    fresh = checks.check("task-phase continuous contact freshness", freshness) is True
    zero = (evaluator.get("collision_events") == 0
            and evaluator.get("contact_monitor_summary", {}).get("event_count") == 0)
    return {"passed": not checks.errors, "errors": checks.errors,
            "raw_sequence_audit_passed": raw is not None,
            "raw_stream_count": len(raw["topics"]) if raw else None,
            "continuous_freshness_passed": fresh, "zero_contact": zero,
            "collision_events": evaluator.get("collision_events"),
            "task_success": evaluator.get("success") is True,
            "termination_reason": evaluator.get("termination_reason"),
            "contact_phase_proof": {
                "method": METHOD, "task_gap_limit_sec": .5,
                "task_gap_bound_from_frozen_latch_invariant": fresh,
                "lifetime_gap_diagnostics": lifetime, "task_gap_numeric_maxima": None,
                "gap_endpoints_available": False,
                "gap_endpoints_scope": "not saved in the original evidence; unavailable",
                "paused_release": context,
            },
            "scope": "frozen started/latch invariant and endpoint ages; no raw timing replay"}


def corrected_audit(audit, directories, *, matrix=False, expected_fault=False):
    contexts = {}
    for directory in directories:
        paths = ([path.parent for path in sorted(directory.glob("worker*/episode*/metadata.json"))]
                 if (directory / "benchmark_metadata.json").exists() else [directory])
        for path in paths:
            try:
                metadata = audit.Evidence(path).json("metadata.json")
                epoch = metadata["epoch"]
                require(metadata.get("freeze") == FREEZE,
                        "all contact-phase samples, including fault prefixes, require c8d")
                require(epoch not in contexts, "duplicate contact-context epoch")
                try:
                    contexts[epoch] = release_context(audit, path)
                except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
                    contexts[epoch] = {"error": str(error)}
            except (OSError, ValueError, TypeError, KeyError) as error:
                raise ValueError("contact context discovery failed: " + str(error)) from error
    original = audit.audit_contacts
    try:
        audit.audit_contacts = lambda evaluator, text, epoch: audit_contact_phase(
            audit, evaluator, text, epoch, contexts.get(epoch, {"error": "missing epoch context"}))
        if matrix:
            return audit.audit_matrix(directories)
        directory = directories[0]
        benchmark = (directory / "benchmark_metadata.json").exists()
        return (audit.audit_benchmark(directory) if benchmark
                else audit.audit_episode(directory, expected_fault))
    finally:
        audit.audit_contacts = original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--expected-fault", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("audit output exists; choose a new path")
    if (args.matrix and args.expected_fault) or (not args.matrix and len(args.directories) != 1):
        parser.error("use --matrix for multiple directories; faults come from benchmark metadata")
    root = repository_root()
    audit, proof = load_auditor(root)
    result = corrected_audit(audit, args.directories, matrix=args.matrix,
                             expected_fault=args.expected_fault)
    original_schema = result["schema"]
    result["schema"] = "mr3-p1c-contact-phase-audit-v2"
    result["offline_contact_phase_audit"] = {
        "method": METHOD,
        "wrapper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "freeze": FREEZE, "frozen_sources": proof, "original_auditor_schema": original_schema,
        "only_overridden_function": "audit_contacts", "original_results_modified": False,
        "source_invariant": (
            "start once; no monitor/latch reset; every task gap/age failure latches"),
        "ready_payload_limitation": "raw initial reward_ready payload was not saved",
        "scope": (
            "offline task-phase correction; no new native, truth timing replay or task success"),
    }
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "audit": str(args.output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
