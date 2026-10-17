"""Shared, metadata-restricted bootstrap dispatch for unchanged native physics.

Only stdlib and the stdlib motion provenance reader are imported. Engineering
capacity exclusions remain outside this module and never enter the PPO audit.
"""

import gzip
import hashlib
import json
from pathlib import Path

from .audit_motion import audit_episode as audit_motion, ns, read, require, same_json


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


CONTROLLED_HANDSHAKE = "paused-controlled-state-peer-guard-storage-v1"


def _one(rows, predicate, message):
    values = [row for row in rows if predicate(row)]
    require(len(values) == 1, message)
    return values[0]


def _prefix(directory, name, end_wall, proof):
    """Read only the startup prefix, binding the complete original file bytes."""
    path = directory / name
    if not path.exists():
        path = Path(str(path) + ".gz")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    proof[name] = {"path": str(path), "sha256": digest.hexdigest()}
    values = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["wall_monotonic_ns"] > end_wall:
                break
            values.append(row)
    return values


def _phase_receipt(rows, component, operation, clock, epoch):
    consumed = _one(rows, lambda row: row.get("kind") == "ack_consumed"
                    and row.get("component") == component
                    and row.get("ack", {}).get("operation") == operation
                    and row["ack"].get("target_time_ns") == clock,
                    "readiness lacks unique actual phase consumption")
    ack = consumed["ack"]
    schema = ("mr3-motion-control-ack-v1" if component == "motion"
              else f"mr3-{component}-phase-ack-v1")
    require(ack.get("schema") == schema and ack.get("epoch") == epoch
            and ack.get("ok") is True and type(ack.get("clock_ns")) is int
            and type(ack.get("target_time_ns")) is int
            and ack["clock_ns"] == ack["target_time_ns"] == clock
            and consumed.get("epoch") == epoch
            and consumed.get("worker_clock_ns") == consumed.get("worker_physical_ns") == clock,
            "readiness phase ACK identity/clock is invalid")
    request = _one(rows, lambda row: row.get("kind") == "request"
                   and row.get("component") == component
                   and row.get("request", {}).get("request_id") == ack["request_id"],
                   "readiness phase has no unique actual worker request")
    req = request["request"]
    require(all(same_json(req[key], ack[key]) for key in (
        "epoch", "request_id", "operation", "target_time_ns")),
        "readiness phase request differs from consumed ACK")
    received = [row for row in rows if row.get("kind") == "ack_received"
                and row.get("component") == component and same_json(row.get("ack"), ack)
                and request["wall_monotonic_ns"] <= row["wall_monotonic_ns"]
                <= consumed["wall_monotonic_ns"]]
    require(received, "readiness consumption lacks actual subscription receipt")
    return req, ack, request["wall_monotonic_ns"], received[-1]["wall_monotonic_ns"], \
        consumed["wall_monotonic_ns"]


def _producer_receipt(rows, component, phase, epoch):
    req, ack, sent, received, consumed = phase
    request_kind = "state_phase_request" if component == "state" else "request_received"
    ack_kind = "state_phase_ack" if component == "state" else "ack_published"
    request = _one(rows, lambda row: row.get("kind") == request_kind
                   and same_json(row.get("payload", {}).get("request", row.get("payload")), req),
                   "readiness lacks actual producer request callback")
    publication = _one(rows, lambda row: row.get("kind") == ack_kind
                       and same_json(row.get("payload", {}).get("ack"), ack)
                       and not row["payload"].get("cached", False),
                       "readiness lacks original actual producer ACK publication")
    start = publication["payload"]["publish_started_wall_monotonic_ns"]
    end = publication["payload"]["publish_completed_wall_monotonic_ns"]
    require(type(start) is int and type(end) is int
            and sent <= request["wall_monotonic_ns"] <= start <= end
            and start <= received <= consumed and publication.get("epoch") == epoch,
            "readiness producer/callback publication window is not causal")
    # DDS delivery may precede publish() return: receipt is bounded by start,
    # never by the later return/log timestamp.
    return publication


def controlled_readiness(directory, metadata, transitions, adapter_rows, epoch, motion):
    """Prove the real controlled release, without rewriting any native artifact.

    The unchanged W7 prewarm ACK predicate is invoked separately by the installer.
    Its source-bound monitor implication is not an archived monitor Bool packet.
    """
    directory = Path(directory)
    proof = {}
    for name in ("metadata.json", "transitions.jsonl", "adapter.jsonl", "physics.jsonl",
                 "control_phase_worker.jsonl", "drive_phase_worker.jsonl",
                 "evaluator_phase_worker.jsonl", "drive_tb1.jsonl", "drive_tb2.jsonl",
                 "drive_tb3.jsonl"):
        path = directory / name
        if not path.exists():
            path = Path(str(path) + ".gz")
        proof[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    require(metadata.get("execution_phase_protocol") == CONTROL_PROTOCOL
            and metadata.get("reset_handshake") == CONTROLLED_HANDSHAKE
            and metadata.get("epoch") == epoch and motion.get("passed") is True,
            "unreviewed controlled readiness declaration")
    require(same_json(metadata, read(directory, "metadata.json")[0])
            and same_json(transitions, _rows(directory / "transitions.jsonl"))
            and same_json(adapter_rows, _rows(directory / "adapter.jsonl")),
            "readiness was not given the unchanged complete native inputs")
    reset = _one(transitions, lambda row: row.get("kind") == "reset",
                 "controlled readiness requires exactly one reset")
    info, snapshot = reset["info"], reset["snapshot"]
    release = info["release_time_ns"]
    require(type(release) is int and ns(snapshot["source_stamp"]) == release
            and snapshot.get("epoch") == epoch,
            "readiness reset does not bind actual task release")
    physics = _rows(directory / "physics.jsonl")
    bootstrap = controlled_bootstrap(directory, physics, epoch, release, motion)
    require(type(info.get("initial_pause_time_ns")) is int
            and physics[0]["steps"] == 0
            and info["initial_pause_time_ns"] == physics[0]["end_time_ns"]
            <= bootstrap["setup_to_controlled_time_ns"],
            "readiness initial pause is not the actual first paused receipt")
    control = _rows(directory / "control_phase_worker.jsonl")
    phases = {}
    for operation, clock in (("takeover", bootstrap["setup_to_controlled_time_ns"]),
                             ("commit", release)):
        for component in ("state", "peer", "motion"):
            phases[operation, component] = _phase_receipt(
                control, component, operation, clock, epoch)
        require(len({phases[operation, name][1]["request_id"]
                     for name in ("state", "peer", "motion")}) == 1,
                "readiness paused chain request identities differ")
    takeover_end = max(phases["takeover", name][4] for name in ("state", "peer", "motion"))
    drive = _rows(directory / "drive_phase_worker.jsonl")
    advance = _one(drive, lambda row: row.get("kind") == "advance_permitted"
                   and row.get("control_kind") == "bootstrap_zero",
                   "readiness bootstrap is missing or repeated")
    require(takeover_end <= advance["wall_monotonic_ns"]
            and phases["commit", "state"][2] > advance["wall_monotonic_ns"],
            "readiness bootstrap precedes takeover or commit precedes bootstrap")
    end_wall = phases["commit", "motion"][4]
    state_rows = _prefix(directory, "information_states.jsonl", end_wall, proof)
    peer_rows = _prefix(directory, "peer_phase.jsonl", end_wall, proof)
    for operation in ("takeover", "commit"):
        for component, rows in (("state", state_rows), ("peer", peer_rows)):
            _producer_receipt(rows, component, phases[operation, component], epoch)
    require(phases["takeover", "state"][1].get("scope")
            == "periodic_state_publication_disabled"
            and phases["takeover", "peer"][1].get("scope")
            == "automatic_obstacle_timer_disabled"
            and same_json(phases["takeover", "motion"][1].get("status"),
                          advance["expected_motion"]),
            "readiness takeover did not disable timers and retain the actual zero completion")
    state = phases["commit", "state"][1]
    peer = phases["commit", "peer"][1]
    guard_req, guard, guard_sent, _, guard_done = phases["commit", "motion"]
    require(type(state.get("state_sequence")) is int and state["state_sequence"] > 0
            and state.get("scope") == "actual_state_and_side_publish_calls_returned"
            and type(peer.get("commit_sequence")) is int and peer["commit_sequence"] > 0
            and peer.get("scope") == "actual_obstacle_publish_calls_returned"
            and same_json(peer.get("state_commit"), state)
            and same_json(guard_req.get("state_commit"), state)
            and same_json(guard_req.get("peer_commit"), peer)
            and phases["commit", "state"][4] <= phases["commit", "peer"][2]
            and phases["commit", "peer"][4] <= guard_sent,
            "readiness state/obstacle/guard dependency chain differs")
    publication = _one(state_rows, lambda row: row.get("kind") == "state_publish"
                       and row["payload"].get("message_sha256") == state["bundle_sha256"],
                       "readiness committed bundle was not actually published")
    bundle = publication["payload"]["message"]
    bundle_digest = hashlib.sha256(json.dumps(
        bundle, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    require(bundle_digest == state["bundle_sha256"]
            and bundle.get("epoch") == epoch
            and type(bundle.get("sequence")) is int
            and bundle["sequence"] == state["state_sequence"]
            and publication.get("clock_ns") == release
            and publication["payload"].get("scope") == "actual_publish_calls_returned",
            "readiness state bundle SHA/identity is invalid")
    state_payload = publication["payload"]
    require(set(state.get("robots", {})) == {"tb1", "tb2", "tb3"}
            and same_json(state_payload.get("side_publish_started_wall_monotonic_ns"),
                          state.get("side_publish_started_wall_monotonic_ns"))
            and same_json(state_payload.get("publish_started_wall_monotonic_ns"),
                          state.get("bundle_publish_started_wall_monotonic_ns"))
            and same_json(state_payload.get("publish_completed_wall_monotonic_ns"),
                          state.get("bundle_publish_completed_wall_monotonic_ns")),
            "readiness state ACK does not bind actual side/bundle publication windows")
    sides = state_payload.get("side_publications", [])
    require(len(sides) == 3 and {item.get("robot") for item in sides} == set(state["robots"]),
            "readiness state publisher lacks three actual side publications")
    inputs = peer.get("inputs", {})
    require(set(inputs) == {"bundle", *[f"{kind}:{name}" for kind in ("odom", "tf")
                                      for name in ("tb1", "tb2", "tb3")]},
            "readiness peer did not receive all actual side inputs")
    for name, reference in state["robots"].items():
        side = next(item for item in sides if item["robot"] == name)
        require(type(reference.get("sequence")) is int and reference["sequence"] > 0
                and all(type(reference.get(key)) is int and 0 <= reference[key] <= release
                        for key in ("source_ns", "odom_source_ns", "tf_source_ns"))
                and release - reference["source_ns"] <= 500_000_000
                and side.get("envelope_sequence") == reference["sequence"],
                "readiness side publication sequence differs from state ACK")
        for kind in ("odom", "tf"):
            require(side.get(kind + "_sha256") == reference.get(kind + "_sha256")
                    and side.get(kind + "_topic") == reference.get(kind + "_topic")
                    == f"/mr3/received/{name}/{kind}",
                    "readiness actual state side publication differs from ACK")
            receipt = inputs[f"{kind}:{name}"]
            callback = _one(peer_rows, lambda row: row.get("kind") == "received_" + kind
                            and row.get("payload", {}).get("robot") == name
                            and row["payload"].get("input_sequence") == receipt["input_sequence"],
                            "readiness side input has no unique real peer callback")
            value = callback["payload"]
            require(type(receipt.get("input_sequence")) is int and receipt["input_sequence"] > 0
                    and value.get("raw_sha256") == receipt.get("raw_sha256")
                    == reference[kind + "_sha256"]
                    and hashlib.sha256(json.dumps(value["raw"], sort_keys=True,
                                                  separators=(",", ":"), allow_nan=False)
                                       .encode()).hexdigest() == value["raw_sha256"]
                    and value.get("received_wall_monotonic_ns")
                    == receipt.get("received_wall_monotonic_ns")
                    and state["side_publish_started_wall_monotonic_ns"]
                    <= receipt["received_wall_monotonic_ns"]
                    <= phases["commit", "peer"][4],
                    "readiness peer callback is not causally bound to published side bytes")
    bundle_input = inputs["bundle"]
    actual_bundle = _one(peer_rows, lambda row: row.get("kind") == "received_state_bundle"
                         and row.get("payload", {}).get("received_wall_monotonic_ns")
                         == bundle_input.get("received_wall_monotonic_ns"),
                         "readiness committed bundle lacks actual peer subscription callback")
    require(same_json(actual_bundle["payload"].get("message"), bundle)
            and bundle_input.get("message_sha256") == state["bundle_sha256"]
            and bundle_input.get("state_sequence") == state["state_sequence"]
            and state["bundle_publish_started_wall_monotonic_ns"]
            <= bundle_input["received_wall_monotonic_ns"] <= phases["commit", "peer"][4],
            "readiness peer received another bundle or noncausal publication")
    matched = _one(peer_rows, lambda row: row.get("kind") == "inputs_matched"
                   and same_json(row["payload"].get("request"), phases["commit", "peer"][0]),
                   "readiness peer has no actual matched input callbacks")
    obstacles = _one(peer_rows, lambda row: row.get("kind") == "obstacles_published"
                     and row["payload"].get("request_id") == peer["request_id"],
                     "readiness peer has no actual obstacle publications")
    require(same_json(matched["payload"].get("inputs"), peer.get("inputs"))
            and same_json(obstacles["payload"].get("publications"), peer.get("publications"))
            and publication["payload"]["publish_started_wall_monotonic_ns"]
            <= matched["wall_monotonic_ns"] <= obstacles["wall_monotonic_ns"]
            <= phases["commit", "peer"][4],
            "readiness actual peer publication/input provenance differs")
    status = info["initial_motion_status"]
    require(same_json(guard.get("status"), status) and status.get("ready") is True
            and "phase_kind" not in status and status.get("clock_ns") == release
            and set(status["outputs"]) == {"tb1", "tb2", "tb3"}
            and all(same_json(output, {"linear_x": 0., "angular_z": 0.})
                    for output in status["outputs"].values()),
            "readiness initial guard output is not the real ready three-zero completion")
    stored = _one(drive, lambda row: row.get("kind") == "ack_consumed"
                  and same_json(row.get("expected_motion"), status),
                  "readiness initial three native storage receipts are missing")
    require(same_json(stored.get("receipts"), info.get("initial_drive_receipts"))
            and guard_done <= stored["wall_monotonic_ns"],
            "readiness reset native storage differs from actual worker consumption")
    for name, receipt in stored["receipts"].items():
        require(name in status["outputs"] and receipt.get("robot") == name
                and receipt.get("epoch") == epoch
                and receipt.get("schema") == "mr3-drive-target-consumed-v1"
                and type(receipt.get("cmd_seq")) is int and receipt["cmd_seq"] > 0
                and type(receipt.get("decision_sequence")) is int
                and receipt["decision_sequence"] == status["decision_sequences"][name]
                and type(receipt.get("clock_ns")) is int
                and type(receipt.get("source_clock_ns")) is int
                and receipt["clock_ns"] == receipt["source_clock_ns"] == release
                and same_json({key: receipt[key] for key in ("linear_x", "angular_z")},
                              status["outputs"][name]),
                "readiness initial native target is not exact zero/identity")
        actual_received = [row for row in drive if row.get("kind") == "ack_received"
                           and row.get("topic_robot") == name
                           and same_json(row.get("ack"), receipt)
                           and guard_sent <= row["wall_monotonic_ns"]
                           <= stored["wall_monotonic_ns"]]
        require(actual_received, "readiness native storage lacks actual subscription callback")
        native = _rows(directory / f"drive_{name}.jsonl")
        command = _one(native, lambda row: row.get("kind") == "command_received"
                       and row.get("cmd_seq") == receipt["cmd_seq"],
                       "readiness native target storage is missing or repeated")
        published = _one(native, lambda row: row.get("kind") == "status_publish"
                         and same_json(row.get("status"), receipt),
                         "readiness native stored target ACK was not actually published")
        require(command["record_sequence"] < published["record_sequence"]
                and command.get("epoch") == epoch and command.get("robot") == name
                and command.get("target_clock_ns") == command.get("sim_time_ns") == release
                and command.get("target_decision_sequence") == receipt["decision_sequence"]
                and same_json([command.get("desired_v"), command.get("desired_w")], [0., 0.]),
                "readiness driver storage identity/value differs from actual initial target")
    require(set(stored["receipts"]) == {"tb1", "tb2", "tb3"},
            "readiness initial native storage does not contain all three robots")
    # Full motion replay binds guard output to actual same-clock self receipts.
    evaluator = _rows(directory / "evaluator_phase_worker.jsonl")
    evaluation = _one(evaluator, lambda row: row.get("kind") == "ack_consumed"
                      and row.get("ack", {}).get("target_time_ns") == release,
                      "readiness initial evaluator acknowledgement is missing")
    eval_request = _one(evaluator, lambda row: row.get("kind") == "request"
                        and row.get("request", {}).get("target_time_ns") == release,
                        "readiness initial evaluator request is missing")
    require(stored["wall_monotonic_ns"] <= eval_request["wall_monotonic_ns"]
            <= evaluation["wall_monotonic_ns"]
            and evaluation["ack"].get("schema") == "mr3-evaluator-clock-terminal-ack-v1"
            and evaluation["ack"].get("request_id") == eval_request["request"]["request_id"]
            and evaluation["ack"].get("epoch") == epoch
            and evaluation["ack"].get("status") == "LIVE"
            and evaluation["ack"].get("ok") is True
            and type(evaluation["ack"].get("evaluator_clock_ns")) is int
            and evaluation["ack"]["evaluator_clock_ns"] == release
            and evaluation["ack"].get("terminal") is None
            and any(row.get("kind") == "ack_received"
                    and same_json(row.get("ack"), evaluation["ack"])
                    and eval_request["wall_monotonic_ns"] <= row["wall_monotonic_ns"]
                    <= evaluation["wall_monotonic_ns"] for row in evaluator),
            "readiness evaluator LIVE response is not actual/causal")
    first_advance = _one(drive, lambda row: row.get("kind") == "advance_permitted"
                         and row.get("start_time_ns") == release,
                         "readiness first task quantum permit is missing or repeated")
    require(first_advance.get("control_kind") == "normal"
            and evaluation["wall_monotonic_ns"] <= first_advance["wall_monotonic_ns"]
            and same_json(first_advance.get("expected_motion"), status)
            and same_json(first_advance.get("receipts"), stored["receipts"])
            and any(row.get("request_id") == first_advance.get("request_id")
                    and row.get("start_time_ns") == release and row.get("steps") == 20
                    for row in physics),
            "readiness first task physics precedes real evaluator LIVE/storage binding")
    # Adapter rows have native record order and sim stamps, not cross-process
    # wall stamps. Bind their real state/snapshot/task prefix without inventing
    # a cross-process snapshot publication timestamp.
    projection = {"sequence": bundle["sequence"],
                  "information_diagnostics": bundle.get("information_diagnostics"),
                  "robots": [{key: robot.get(key) for key in (
                      "name", "source_stamp", "received_stamp", "odom_source_stamp",
                      "tf_source_stamp", "tf_validity_stamp", "valid", "epoch", "odometry")}
                      for robot in bundle["robots"]]}
    updates = [i for i, row in enumerate(adapter_rows) if row.get("kind") == "state_update"
               and same_json(row.get("payload"), projection)]
    requested = _one(adapter_rows, lambda row: row.get("kind") == "snapshot_requested"
                     and row["payload"].get("target_time_ns") == release,
                     "readiness initial snapshot request is missing")
    completed = _one(adapter_rows, lambda row: row.get("kind") == "snapshot_completed"
                     and row["payload"].get("request_id") == requested["payload"]["request_id"],
                     "readiness initial snapshot completion is missing")
    task = _one(adapter_rows, lambda row: row.get("kind") == "task_start",
                "readiness actual task release is not unique")
    observation = _one(adapter_rows, lambda row: row.get("kind") == "observation"
                       and row["payload"].get("sequence") == snapshot.get("sequence"),
                       "readiness initial observation is missing")
    indexes = [adapter_rows.index(value) for value in (requested, task, observation, completed)]
    require(updates and max(updates) < indexes[0] < indexes[1] < indexes[2] < indexes[3]
            and ns(task["payload"]["start_sim_time_sec"]) == release
            and same_json(observation["payload"], snapshot)
            and completed["payload"].get("ok") is True
            and same_json(completed["payload"].get("watermarks"), info["watermarks"])
            and type(info["watermarks"].get("state_sequence")) is int
            and info["watermarks"]["state_sequence"] == state["state_sequence"]
            and type(info["watermarks"].get("map_version")) is int
            and type(snapshot.get("map_version")) is int
            and type(snapshot.get("map", {}).get("version")) is int
            and requested["payload"].get("expected_map_sha256")
            == info["watermarks"]["map_payload_sha256"]
            and snapshot.get("map_version") == snapshot.get("map", {}).get("version")
            == info["watermarks"]["map_version"],
            "readiness actual adapter state/snapshot/release watermark order differs")
    reward = info["reward_diagnostics"]
    require(reward.get("kind") == "reward_reset_binding" and reward.get("epoch") == epoch
            and type(reward.get("sequence")) is int and reward["sequence"] == 0
            and type(reward.get("reward")) in (int, float) and reward["reward"] == 0.
            and reward.get("reset_bound") is True and reward.get("delta_sim_time") == 0
            and reward.get("terminated") is False and reward.get("truncated") is False
            and ns(reward["step_start"]) == ns(reward["effective_step_end"]) == release
            and reward["map_watermark"]["payload_sha256"]
            == info["watermarks"]["map_payload_sha256"],
            "readiness actual reward sequence-zero binding differs")
    verify_motion_artifacts({"artifact_proof": proof})
    return {"bootstrap": bootstrap, "state_sequence": state["state_sequence"],
            "state_bundle_sha256": state["bundle_sha256"], "initial_storage": stored["receipts"],
            "initial_evaluator_state": "LIVE", "artifact_proof": proof,
            "scope": "real controlled release; monitor implication from pinned source, "
                     "not archived raw Bool proof"}


def dispatch_controlled_readiness(auditor, directories, motion_cache):
    """Install one restricted hook shared by original episode/contact consumers."""
    original = auditor.audit_initial_inputs_ready
    by_epoch, cache = {}, {}
    for directory in map(Path, directories):
        paths = ([directory / "metadata.json"] if (directory / "metadata.json").is_file()
                 else sorted(directory.glob("worker*/episode*/metadata.json")))
        for path in paths:
            metadata = json.loads(path.read_text())
            require(metadata["epoch"] not in by_epoch, "duplicate readiness epoch")
            by_epoch[metadata["epoch"]] = path.parent

    def readiness(metadata, transitions, adapter_rows, epoch):
        protocol = metadata.get("execution_phase_protocol")
        handshake = metadata.get("reset_handshake")
        if protocol is None and handshake != CONTROLLED_HANDSHAKE:
            return original(metadata, transitions, adapter_rows, epoch)
        require(protocol == CONTROL_PROTOCOL and handshake == CONTROLLED_HANDSHAKE,
                "unknown or mixed controlled readiness declarations")
        directory = by_epoch[epoch]
        if directory not in motion_cache:
            motion_cache[directory] = audit_motion(directory)
        if epoch not in cache:
            cache[epoch] = controlled_readiness(directory, metadata, transitions, adapter_rows,
                                                epoch, motion_cache[directory])
        else:
            verify_motion_artifacts(motion_cache[directory])
            verify_motion_artifacts(cache[epoch])
            require(same_json(metadata, read(directory, "metadata.json")[0])
                    and same_json(transitions, _rows(directory / "transitions.jsonl"))
                    and same_json(adapter_rows, _rows(directory / "adapter.jsonl")),
                    "cached readiness native inputs changed")
        # This metadata view selects only the immutable W7 ACK subpredicate.
        # It is not raw metadata, a modern handshake proof, or a protocol upgrade.
        view = dict(metadata, reset_handshake="delivered_inputs_before_pause-v1")
        prewarm = original(view, transitions, adapter_rows, epoch)
        require(prewarm.get("required") is True and prewarm.get("proven") is True,
                "controlled readiness lacks original prewarm input ACK proof")
        return {**prewarm, "protocol": CONTROLLED_HANDSHAKE,
                "prewarm_ack_subpredicate": {**prewarm, "scope":
                    "immutable W7 prewarm ACK predicate on explicit metadata view only"},
                "controlled_release": cache[epoch],
                "scope": "controlled release proof plus original prewarm ACK; "
                         "contact math unchanged"}

    auditor.audit_initial_inputs_ready = readiness
    return original
