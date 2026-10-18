"""Fresh near-peer collection of eight fixed V7 actions; never policy training.

This is a new engineering collection under the current freeze, not a replay of
the old physical trajectory and not evidence that the V7 failure was reproduced.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .benchmark import _abort_requested, _new_preparation_abort, _preparation_failure, _wall_admission
from .env import MR3Env
from .plant_probe import PHYSICS_CONFIG_ENV, physics_config
from .supervisor import ROS_ROOT, WORKSPACE, Supervisor


ACTIONS = (231, 888, 888, 889, 880, 658, 888, 888)
WALL_SECONDS = 700.
CLOSE_RESERVE_SECONDS = 120.


def _clean_receipts(receipts, epoch):
    return bool(epoch) and len(receipts) == 1 and all(
        receipt.get("epoch") == epoch
        and receipt.get("worker_returncode") == 0
        and receipt.get("forced_shutdown") is False
        and receipt.get("failed_sample") is False
        and receipt.get("remaining_owned_processes") == []
        and receipt.get("remaining_owned_zombies") == [] for receipt in receipts)


def run_trace(args, *, started_ns=None):
    started_ns = time.monotonic_ns() if started_ns is None else started_ns
    args.close_reserve_seconds = CLOSE_RESERVE_SECONDS
    args.allocation_deadline_monotonic_ns = started_ns + round(WALL_SECONDS * 1e9)
    config_path, config = physics_config(args.physics_config) if args.physics_config else (None, None)
    directory = args.output_root / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    summary_path = directory / "action_trace_summary.json"
    abort = _new_preparation_abort()
    supervisor = environment = None
    prior_config = os.environ.get(PHYSICS_CONFIG_ENV)
    if config_path is None:
        os.environ.pop(PHYSICS_CONFIG_ENV, None)
    else:
        os.environ[PHYSICS_CONFIG_ENV] = str(config_path)
    summary = {
        "schema": "mr3-fixed-action-trace-v1", "scene": "open", "seed": 101,
        "robots": ["tb1", "tb2", "tb3"], "actions": list(ACTIONS),
        "spawn": "unchanged normal near-peer launch spawn; no plant stimulus arm",
        "policy_calls": 0, "optimizer_steps": 0, "training_eligible": False,
        "scope": __doc__, "validity_audit_required": True,
        "run_directory": str(directory), "command": [sys.executable, *sys.argv],
        "started_wall_monotonic_ns": started_ns,
        "wall_limit_seconds": WALL_SECONDS, "close_reserve_seconds": CLOSE_RESERVE_SECONDS,
        "work_deadline_monotonic_ns": args.allocation_deadline_monotonic_ns
        - round(CLOSE_RESERVE_SECONDS * 1e9),
        "allocation_deadline_monotonic_ns": args.allocation_deadline_monotonic_ns,
        "rpc_admission_upper_bounds_seconds": {"reset": 420., "step": 90.},
        "physics_config": config, "mask_checks": [], "steps": [],
        "native_decisions_requested": len(ACTIONS), "native_decisions_returned": 0,
        "completed_requested_collection": False, "outcome": "INCOMPLETE",
        "cleanup_errors": [], "shutdown_receipts": [], "first_failure": None,
    }

    def save():
        summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")

    def failure(kind, reason):
        _preparation_failure(abort, 0, kind, reason, 0, summary.get("epoch"))

    try:
        summary["freeze"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip()
        summary["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        summary["source_bindings"] = {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("action_trace.py", "benchmark.py", "env.py", "supervisor.py", "plant_probe.py")}
        metadata_keys = set(summary) - {
            "mask_checks", "steps", "native_decisions_returned", "completed_requested_collection",
            "outcome", "cleanup_errors", "shutdown_receipts", "first_failure"}
        (directory / "action_trace_metadata.json").write_text(json.dumps(
            {key: value for key, value in summary.items() if key in metadata_keys},
            indent=2, allow_nan=False) + "\n")
        save()
        supervisor = Supervisor(run_id=args.run_id, domain_id=args.domain, gazebo_port=args.port,
                                output_root=args.output_root, startup_timeout=420., request_timeout=90.)
        environment = MR3Env(supervisor=supervisor, scene="open", max_steps=len(ACTIONS))
        if _wall_admission(args, abort, 0, "reset", episode_index=0):
            _, info = environment.reset(seed=101, options={"scene": "open"})
            summary["epoch"] = info["epoch"]
            summary["initial_info"] = info
            summary["episode_directory"] = str(supervisor.episode.directory)
            save()
            _wall_admission(args, abort, 0, "after_rpc", episode_index=0, epoch=summary["epoch"])
            for decision, action in enumerate(ACTIONS):
                if not _wall_admission(args, abort, 0, "step", episode_index=0,
                                       epoch=summary["epoch"]):
                    break
                mask = environment.action_masks()
                check = {"decision": decision, "action": action,
                         "observation_digest": info["observation_digest"],
                         "observation_sequence": info.get("observation_sequence"),
                         "joint_action_mask": [bool(value) for value in mask],
                         "legal": len(mask) == 1000 and bool(mask[action])}
                summary["mask_checks"].append(check)
                save()
                if not check["legal"]:
                    failure("fixed_action_illegal", f"decision {decision}, action {action}")
                    break
                if not _wall_admission(args, abort, 0, "step", episode_index=0,
                                       epoch=summary["epoch"]):
                    break
                step_started_ns = time.monotonic_ns()
                _, reward, terminated, truncated, info = environment.step(action)
                summary["native_decisions_returned"] += 1
                summary["steps"].append({
                    "decision": decision, "action": action, "reward": reward,
                    "terminated": terminated, "truncated": truncated, "info": info,
                    "started_wall_monotonic_ns": step_started_ns,
                    "returned_wall_monotonic_ns": time.monotonic_ns()})
                save()
                if terminated:
                    failure("unexpected_termination", info.get("reason"))
                elif truncated and decision + 1 < len(ACTIONS):
                    failure("early_truncation", info.get("reason"))
                _wall_admission(args, abort, 0, "after_rpc", episode_index=0,
                                epoch=summary["epoch"])
                if _abort_requested(abort) or terminated or truncated:
                    break
            summary["completed_requested_collection"] = (
                len(summary["steps"]) == len(ACTIONS)
                and summary["steps"][-1]["terminated"] is False
                and summary["steps"][-1]["truncated"] is True)
            if not summary["completed_requested_collection"] and not _abort_requested(abort):
                failure("missing_final_external_truncation", "eight real steps must close externally")
    except Exception as error:
        summary["error"] = repr(error)
        failure("rpc_or_runner_exception", repr(error))
    finally:
        try:
            if environment is not None:
                environment.close()
            elif supervisor is not None:
                supervisor.close()
        except Exception as error:
            summary["cleanup_errors"].append(repr(error))
            failure("cleanup_exception", repr(error))
        if supervisor is not None:
            summary["shutdown_receipts"] = supervisor.receipts
        ended_ns = time.monotonic_ns()
        summary["ended_wall_monotonic_ns"] = ended_ns
        summary["wall_sec_including_startup_and_close"] = (ended_ns - started_ns) / 1e9
        summary["wall_limit_exceeded"] = ended_ns > args.allocation_deadline_monotonic_ns
        summary["shutdown_clean"] = _clean_receipts(summary["shutdown_receipts"], summary.get("epoch"))
        if summary["wall_limit_exceeded"]:
            failure("wall_allocation_exceeded", "actual wall including close exceeded 700 seconds")
        if not summary["shutdown_clean"]:
            failure("unclean_shutdown", "missing or non-clean native shutdown receipt")
        summary["first_failure"] = abort["first_failure"]
        if summary["completed_requested_collection"] and not _abort_requested(abort):
            summary["outcome"] = "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT"
        elif any(step["terminated"] for step in summary["steps"]) or summary["wall_limit_exceeded"]:
            summary["outcome"] = "FAIL"
        save()
        if prior_config is None:
            os.environ.pop(PHYSICS_CONFIG_ENV, None)
        else:
            os.environ[PHYSICS_CONFIG_ENV] = prior_config
    return summary


def main(argv=None):
    started_ns = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--domain", type=int, default=180)
    parser.add_argument("--port", type=int, default=14001)
    parser.add_argument("--output-root", type=Path, default=ROS_ROOT / "log/mr3_action_trace")
    parser.add_argument("--physics-config", type=Path)
    args = parser.parse_args(argv)
    if not args.run_id or any(character not in
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in args.run_id):
        parser.error("run-id must be a safe unique path component")
    result = run_trace(args, started_ns=started_ns)
    print(json.dumps({key: result.get(key) for key in (
        "run_directory", "outcome", "native_decisions_returned", "first_failure",
        "wall_sec_including_startup_and_close", "shutdown_clean")}, allow_nan=False))
    return 0 if result["outcome"] == "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
