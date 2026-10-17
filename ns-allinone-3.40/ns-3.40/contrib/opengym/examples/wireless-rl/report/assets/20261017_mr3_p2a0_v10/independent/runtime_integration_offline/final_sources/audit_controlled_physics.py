"""Shared, metadata-restricted bootstrap dispatch for unchanged native physics.

Only stdlib and the stdlib motion provenance reader are imported. Engineering
capacity exclusions remain outside this module and never enter the PPO audit.
"""

import hashlib
import json
from pathlib import Path

from .audit_motion import audit_episode as audit_motion, read, require, same_json


def _rows(path):
    path = Path(path)
    return read(path.parent, path.name, True)[0]


CONTROL_PROTOCOL = "mr3-controlled-execution-phase-v1"


def verify_motion_artifacts(motion):
    proof = motion.get("artifact_proof")
    require(isinstance(proof, dict) and proof, "motion replay has no raw input proof")
    for entry in proof.values():
        require(hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() == entry["sha256"],
                "cached motion replay raw input changed")


def controlled_bootstrap(directory, rows, epoch, release, motion):
    """Bind the single pre-release zero quantum to real callbacks/storage.

    This changes the original physics helper's setup-to-controlled threshold,
    never the task release used by transitions, contacts, reward or evaluation.
    """
    metadata = json.loads((directory / "metadata.json").read_text())
    require(metadata.get("execution_phase_protocol") == CONTROL_PROTOCOL
            and metadata.get("epoch") == epoch and motion.get("passed") is True
            and type(release) is int and release >= 0,
            "bootstrap requires reviewed controlled execution and complete motion replay")
    verify_motion_artifacts(motion)
    replay = motion.get("controlled_execution_replay", {})
    require(replay.get("bootstrap_zero_quanta") == 1,
            "bootstrap lacks complete actual motion/control provenance")
    require(same_json(rows, _rows(directory / "physics.jsonl")),
            "physics dispatch was not given the complete unchanged raw receipts")
    drive = _rows(directory / "drive_phase_worker.jsonl")
    bootstrap = [row for row in drive if row.get("kind") == "advance_permitted"
                 and row.get("control_kind") == "bootstrap_zero"]
    require(len(bootstrap) == 1, "controlled bootstrap is missing or repeated")
    item = bootstrap[0]
    status, receipts = item["expected_motion"], item["receipts"]
    start = item["start_time_ns"]
    require(type(start) is int and 0 <= start < release and item.get("epoch") == epoch
            and type(item.get("steps")) is int and item["steps"] == 20
            and item.get("worker_clock_ns") == item.get("worker_physical_ns") == start
            and status.get("clock_ns") == start and "phase_kind" not in status
            and set(status["outputs"]) == set(receipts) == {"tb1", "tb2", "tb3"}
            and all(same_json(output, {"linear_x": 0., "angular_z": 0.})
                    for output in status["outputs"].values()),
            "bootstrap was not exact paused three-zero motion")
    physical = [row for row in rows if row.get("request_id") == item["request_id"]]
    require(len(physical) == 1 and physical[0]["start_time_ns"] == start
            and physical[0]["end_time_ns"] == release and physical[0]["steps"] == 20,
            "bootstrap does not end at the actual task release")
    # Worker consumption is backed by actual subscription callbacks, not merely
    # by the expected target copied into its advance-permitted record.
    latest, consumed = {}, False
    for row in drive:
        if row["wall_monotonic_ns"] > item["wall_monotonic_ns"]:
            break
        if row["kind"] == "ack_received":
            latest[row["topic_robot"]] = row["ack"]
        elif row["kind"] == "ack_consumed" and same_json(row["expected_motion"], status):
            require(same_json(row["receipts"], receipts) and same_json(latest, receipts),
                    "bootstrap storage was not the latest actual three receipts")
            consumed = True
    require(consumed and same_json(latest, receipts),
            "bootstrap advanced without unchanged actual stored targets")
    for name, receipt in receipts.items():
        require(receipt.get("schema") == "mr3-drive-target-consumed-v1"
                and receipt.get("epoch") == epoch and receipt.get("robot") == name
                and type(receipt.get("clock_ns")) is int
                and type(receipt.get("source_clock_ns")) is int
                and receipt["clock_ns"] == receipt["source_clock_ns"] == start
                and type(receipt.get("cmd_seq")) is int and receipt["cmd_seq"] > 0
                and type(receipt.get("decision_sequence")) is int
                and receipt["decision_sequence"] == status["decision_sequences"][name]
                and type(receipt.get("linear_x")) in (int, float)
                and type(receipt.get("angular_z")) in (int, float)
                and receipt["linear_x"] == receipt["angular_z"] == 0.,
                "bootstrap native storage receipt is not exact zero/identity")
        native = _rows(directory / f"drive_{name}.jsonl")
        actual_command, actual_status = None, None
        for row in native:
            if row.get("cmd_seq") != receipt["cmd_seq"]:
                continue
            if row.get("kind") == "command_received":
                actual_command = row
            elif row.get("kind") == "status_publish" and same_json(row.get("status"), receipt):
                require(actual_command is not None
                        and actual_command["record_sequence"] < row["record_sequence"],
                        "bootstrap status has no preceding actual driver target storage")
                actual_status = row
        require(actual_command is not None and actual_status is not None
                and actual_command.get("epoch") == epoch and actual_command.get("robot") == name
                and type(actual_command.get("cmd_seq")) is int
                and type(actual_command.get("target_decision_sequence")) is int
                and type(actual_command.get("target_clock_ns")) is int
                and type(actual_command.get("sim_time_ns")) is int
                and type(actual_command.get("desired_v")) in (int, float)
                and type(actual_command.get("desired_w")) in (int, float)
                and actual_command.get("target_decision_sequence") == receipt["decision_sequence"]
                and actual_command.get("target_clock_ns") == actual_command.get("sim_time_ns")
                == start and actual_command.get("desired_v") == actual_command.get("desired_w")
                == 0., "bootstrap stored target was not found in actual native driver trace")
    return {"setup_to_controlled_time_ns": start, "actual_task_release_time_ns": release,
            "request_id": item["request_id"], "control_request_id": item["control_request_id"],
            "scope": "single real zero bootstrap; no fresh geometry or task-time credit"}


def dispatch_controlled_physics(auditor, directories, motion_cache):
    """Wrap only the quantum-switch argument; original math and rows stay intact."""
    original = auditor.audit_physics
    by_epoch = {}
    for directory in directories:
        directory = Path(directory)
        paths = ([directory / "metadata.json"] if (directory / "metadata.json").is_file()
                 else sorted(directory.glob("worker*/episode*/metadata.json")))
        for path in paths:
            metadata = json.loads(path.read_text())
            require(metadata["epoch"] not in by_epoch,
                    "duplicate native epoch for physics dispatch")
            by_epoch[metadata["epoch"]] = (path.parent, metadata)

    def physics(rows, epoch, release):
        directory, metadata = by_epoch[epoch]
        protocol = metadata.get("execution_phase_protocol")
        require(protocol is None or protocol == CONTROL_PROTOCOL,
                "unknown metadata execution phase protocol")
        if protocol is None:
            return original(rows, epoch, release)
        if directory not in motion_cache:
            motion_cache[directory] = audit_motion(directory)
        bootstrap = controlled_bootstrap(directory, rows, epoch, release, motion_cache[directory])
        result = original(rows, epoch, bootstrap["setup_to_controlled_time_ns"])
        return {**result, "controlled_bootstrap": bootstrap,
                "original_integer_continuity_quantum_math": True}

    auditor.audit_physics = physics
    return original
