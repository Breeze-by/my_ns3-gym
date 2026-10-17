"""Audit P2A.0 scripted engineering evidence; no policy or training credit."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

from .audit_ppo import load_native_gates, load_rows, require
from .audit_evaluator_phase import audit_episode as audit_phase
from .audit_activity import audit_episode as audit_activity, audit_probe_activity
from .audit_motion import audit_episode as audit_motion, same_json


PREPARATION_PROBE_VERSION = "mr3-p2a0-outward-cancel-v2"
PREPARATION_PROBE_V3 = "mr3-p2a0-outward-cancel-v3"
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
    require(same_json(rows, load_rows(directory / "physics.jsonl")),
            "physics dispatch was not given the complete unchanged raw receipts")
    drive = load_rows(directory / "drive_phase_worker.jsonl")
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
        native = load_rows(directory / f"drive_{name}.jsonl")
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
        for path in directory.glob("worker*/episode*/metadata.json"):
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


def exclude_preparation_capacity_comparison(auditor):
    """The new engineering inputs are not the historical P1C capacity workload.

    Keep every native gate and the original comparison function for legacy
    inputs. Only the explicit, prospectively declared v2/v3 fixtures are excluded
    from capacity comparison; it still has to pass all episode gates.
    """
    original = auditor.comparison_statistics

    def comparison(metadata, summary):
        version = metadata.get("preparation_probe_version")
        if version not in (PREPARATION_PROBE_VERSION, PREPARATION_PROBE_V3):
            return original(metadata, summary)
        expected_steps = 32 if version == PREPARATION_PROBE_V3 else 20
        count, schedule = metadata.get("workers"), metadata.get("schedule")
        expected = ([['open', 101]] if count == 1 else
                    [['open', 101], ['open', 101], ['rooms', 101], ['corridors', 101]])
        require(type(count) is int and count in (1, 2) and schedule == expected
                and all(type(cell[1]) is int for cell in schedule)
                and type(metadata.get("steps_per_episode")) is int
                and metadata["steps_per_episode"] == expected_steps
                and metadata.get("preparation_motion_probe") is True
                and all(metadata.get(key) is False for key in
                        ("terminal_probe", "deadline_probe", "fault_probe")),
                "unknown versioned preparation workload")
        keys = ("workers", "schedule", "steps_per_episode", "preparation_motion_probe",
                "preparation_probe_version", "terminal_probe", "deadline_probe",
                "fault_probe", "freeze")
        require(json.dumps({key: summary.get(key) for key in keys}, sort_keys=True,
                           allow_nan=False)
                == json.dumps({key: metadata.get(key) for key in keys}, sort_keys=True,
                              allow_nan=False),
                "versioned preparation summary/declaration mismatch")
        return {
            "eligible": False,
            "reason": "explicit preparation fixture; no historical P1C capacity comparison",
            "preparation_probe_version": version,
            "original_comparison_source": original.__code__.co_filename,
            "native_episode_gates_unchanged": True,
        }

    auditor.comparison_statistics = comparison


def audit_execution_inputs(directory, motion_review=None):
    """Verify actual graph and complete master-costmap copies independently."""
    transitions = load_rows(directory / "transitions.jsonl")
    epoch = transitions[0]["snapshot"]["epoch"]
    topology = json.loads((directory / "motion_topology.json").read_text())
    require(topology["schema"] == "mr3-motion-output-topology-v1"
            and topology["epoch"] == epoch
            and 0 <= topology["stamp"] <= transitions[0]["snapshot"]["source_stamp"],
            "motion topology epoch/release time mismatch")
    expected = {f"/tb{index}/cmd_vel" for index in (1, 2, 3)}
    require(set(topology["endpoints"]) == expected, "motion output topics differ")
    gids = set()
    for entries in topology["endpoints"].values():
        require(len(entries) == 1, "motion output has missing/duplicate publishers")
        entry = entries[0]
        require((entry["namespace"], entry["node"]) == ("/", "motion_safety")
                and entry["topic_type"] == "geometry_msgs/msg/Twist"
                and re.fullmatch(r"[0-9a-f]{32,}", entry["endpoint_gid"])
                and int(entry["endpoint_gid"], 16) != 0,
                "native final velocity publisher differs from the reviewed gate")
        gids.add(entry["endpoint_gid"])
    require(len(gids) == 3, "velocity topics share an unexpected native endpoint")
    blobs, streams, count, last_receipt = {}, set(), 0, -1
    maximum_source_clock_lead_ns = 0
    for row in load_rows(directory / "costmaps.jsonl"):
        name, layer, digest = row["robot"], row["layer"], row["payload_sha256"]
        require(row["schema"] == "mr3-native-costmap-receipt-v1" and row["epoch"] == epoch
                and name in ("tb1", "tb2", "tb3") and layer in ("global", "local")
                and row["topic"] == f"/{name}/{layer}_costmap/costmap"
                and row["artifact"] == f"execution_inputs/maps/{digest}.json.gz"
                and re.fullmatch(r"[0-9a-f]{64}", digest),
                "invalid native costmap identity")
        if digest not in blobs:
            raw = gzip.decompress((directory / row["artifact"]).read_bytes())
            payload = json.loads(raw)
            require(raw == json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()
                    and hashlib.sha256(raw).hexdigest() == digest,
                    "native costmap bytes/digest mismatch")
            info = payload["info"]
            require(info["width"] > 0 and info["height"] > 0
                    and len(payload["data"]) == info["width"] * info["height"]
                    and all(type(value) is int and -1 <= value <= 100
                            for value in payload["data"]), "native costmap shape/value mismatch")
            blobs[digest] = payload
        payload = blobs[digest]
        require(payload["header"] == row["source_header"], "native costmap source header differs")
        receipt = row["received_clock_ns"]
        require(type(receipt) is int and receipt >= last_receipt,
                "native costmap receipt clock regressed")
        stamp = payload["header"]["stamp"]
        source = stamp["sec"] * 10**9 + stamp["nanosec"]
        maximum_source_clock_lead_ns = max(maximum_source_clock_lead_ns, source - receipt)
        last_receipt = receipt
        streams.add((name, layer))
        count += 1
    require(len(streams) == 6, "actual global/local master outputs missing for a robot")
    consumed, received = [], {}
    last_clock, last_sequences = -1, dict.fromkeys(("tb1", "tb2", "tb3"), -1)
    for row in load_rows(directory / "motion_phase_worker.jsonl"):
        ack = row["ack"]
        require(row["epoch"] == epoch and ack["epoch"] == epoch
                and ack["schema"] == "mr3-motion-safety-status-v1"
                and ack.get("completion_scope") == "publication_and_local_topic_receipt"
                and type(ack["ready"]) is bool
                and set(ack["decision_sequences"]) == set(last_sequences),
                "invalid native motion gate phase identity")
        clock = ack["clock_ns"]
        sequences = ack["decision_sequences"]
        require(type(clock) is int and clock >= 0
                and all(type(value) is int and value > 0 for value in sequences.values()),
                "invalid native motion phase clock/sequence")
        if row["kind"] == "ack_received":
            require(clock >= last_clock
                    and all(sequences[name] >= last_sequences[name] for name in sequences),
                    "native motion phase source regressed")
            if clock > last_clock:
                require(all(sequences[name] > last_sequences[name] for name in sequences),
                        "native motion clock advanced without three new decisions")
            if clock in received:
                require(received[clock] == ack, "native motion phase changed at one clock")
            received[clock] = ack
            last_clock, last_sequences = clock, sequences
        else:
            require(row["kind"] == "ack_consumed" and received.get(clock) == ack
                    and row["worker_clock_ns"] == row["worker_physical_ns"] == clock,
                    "motion phase was not actually received at exact paused clock")
            consumed.append(clock)
    release = transitions[0]["info"]["release_time_ns"]
    physics = load_rows(directory / "physics.jsonl")
    required_clocks = [row["end_time_ns"] for row in physics if row["end_time_ns"] > release]
    metadata = json.loads((directory / "metadata.json").read_text())
    protocol = metadata.get("execution_phase_protocol")
    require(protocol is None or protocol == CONTROL_PROTOCOL,
            "unknown metadata execution phase protocol")
    controlled_replay = None
    if protocol == CONTROL_PROTOCOL:
        motion_review = audit_motion(directory) if motion_review is None else motion_review
        require(motion_review.get("passed") is True and motion_review.get("epoch") == epoch,
                "controlled execution inputs lack complete actual motion replay")
        verify_motion_artifacts(motion_review)
        controlled_replay = motion_review.get("controlled_execution_replay")
        require(isinstance(controlled_replay, dict)
                and controlled_replay.get("bootstrap_zero_quanta") == 1,
                "controlled inputs lack the reviewed execution-phase proof")
        stop_clocks = set(controlled_replay["stop_clocks"])
        normal_clocks = {clock for clock in consumed if clock > release}
        require(set(required_clocks) <= normal_clocks | stop_clocks
                and normal_clocks <= set(required_clocks)
                and {clock for clock in stop_clocks if clock > release} <= set(required_clocks),
                "controlled task/cleanup quantum lacks exact normal or actual stop completion")
    else:
        require([clock for clock in consumed if clock > release] == required_clocks,
                "a task/cleanup quantum advanced without exact motion gate completion")
    initial = transitions[0]["info"]["initial_motion_status"]
    require(initial["ready"] is True and initial["clock_ns"] == release
            and received.get(release) == initial and release in consumed,
            "task release lacks exact healthy motion completion at the initial pause")
    return {"passed": True, "topology": topology, "costmap_receipts": count,
            "unique_costmaps": len(blobs), "streams": sorted(streams),
            "consumed_motion_phases": len(consumed),
            "controlled_execution_replay": controlled_replay,
            "maximum_source_clock_lead_ns": maximum_source_clock_lead_ns,
            "scope": "actual output bytes and graph; receipt clock is not planner consumption"}


def audit_probe_execution(directory):
    """Require real all-robot activity in the declared short navigation probes."""
    snapshots = [row["snapshot"] for row in load_rows(directory / "transitions.jsonl")]
    events = load_rows(directory / "adapter.jsonl")
    result = {}
    for index, name in enumerate(("tb1", "tb2", "tb3")):
        divisor = (100, 10, 1)[index]
        legal = sum(any(flag and action // divisor % 10 < 8
                        for action, flag in enumerate(snapshot["joint_action_mask"]))
                    for snapshot in snapshots)
        sent = {row["payload"]["goal_id"] for row in events
                if row["kind"] == "native_send" and row["payload"]["robot"] == name}
        accepted = {row["payload"]["payload"]["goal_id"] for row in events
                    if row["kind"] == "delivery" and row["payload"].get("stream") == "receipt"
                    and row["payload"].get("source") == name
                    and row["payload"]["payload"].get("type") == "accept"
                    and row["payload"]["payload"].get("value") is True}
        paths = [snapshot["robots"][index]["activity"]["estimated_path_m"]
                 for snapshot in snapshots]
        path = max((value for value in paths if value is not None), default=0.)
        require(legal > 0 and sent and accepted and accepted <= sent and path > .05,
                f"{name} has no proven legal/sent/accepted/moving execution in the short probe")
        result[name] = {"snapshots_with_legal_goal": legal, "native_sent_goals": len(sent),
                        "accepted_goals": len(accepted), "maximum_received_odom_path_m": path}
    return {"passed": True, "robots": result,
            "scope": ("short received-odom motion and native goal acceptance; "
                      "no 1m task participation credit")}


def audit_archives(directory):
    """Bind full received-map bytes to each actual saved actor snapshot."""
    from .navigation_archive import COMPOSITION_VERSION, reconstruct_navigation_payload

    root = directory / "observation_inputs"
    snapshots, blobs, payloads, navigation_replays = set(), {}, {}, {}
    for row in load_rows(directory / "transitions.jsonl"):
        snapshot = row["snapshot"]
        manifest = json.loads((root / "snapshots" / (
            f"{snapshot['sequence']:08d}_{snapshot['digest']}.json")).read_text())
        require(manifest["schema"] in ("mr3-observation-input-archive-v1",
                                       "mr3-observation-input-archive-v2")
                and manifest["scope"] == "encoder_result_before_publication",
                "unknown observation archive format")
        navigation_mode = manifest["schema"] == "mr3-observation-input-archive-v2"
        for key in ("epoch", "sequence", "candidate_version"):
            require(manifest[key] == snapshot[key], "archive snapshot identity mismatch")
        require(manifest["snapshot_digest"] == snapshot["digest"]
                and manifest["source_stamp"] == snapshot["source_stamp"],
                "archive snapshot digest/time mismatch")
        metadata = manifest["metadata"]
        require(metadata["epoch"] == snapshot["epoch"]
                and metadata["map_version"] == snapshot["map_version"]
                and metadata["map_sources"] == snapshot["map"]["sources"]
                and metadata["map_source_stamp"] == snapshot["map"]["source_stamp"]
                and metadata["map_received_stamp"] == snapshot["map"]["received_stamp"]
                and metadata["map_payload_sha256"] == row["info"]["watermarks"][
                    "map_payload_sha256"], "archive map metadata/watermark mismatch")
        roles = {"fused", "tb1", "tb2", "tb3"}
        if navigation_mode:
            roles.update("navigation:" + name for name in ("tb1", "tb2", "tb3"))
            require(metadata["navigation_sources"] == snapshot["navigation_sources"]
                    == row["info"]["watermarks"]["navigation_sources"],
                    "archive native navigation metadata/watermark mismatch")
            require(metadata["navigation_composition"]["version"] == COMPOSITION_VERSION
                    == snapshot["candidate_rule"]["navigation_composition"],
                    "archive navigation composition mismatch")
        require(set(manifest["maps"]) == roles, "archive received-map roles mismatch")
        for name, entry in manifest["maps"].items():
            if name == "fused":
                expected = metadata["map_payload_sha256"]
            elif name.startswith("navigation:"):
                expected = metadata["navigation_sources"][name.split(":", 1)[1]]["payload_sha256"]
            else:
                expected = (metadata["map_sources"][name]["payload_sha256"] if navigation_mode
                            else snapshot["path_maps"][name]["payload_sha256"])
            require(entry["payload_sha256"] == expected
                    and entry["artifact"] == f"maps/{expected}.json.gz",
                    "archive map identity/path mismatch")
            if expected not in blobs:
                compressed = (root / entry["artifact"]).read_bytes()
                raw = gzip.decompress(compressed)
                payload = json.loads(raw)
                canonical = json.dumps(payload, allow_nan=False, sort_keys=True,
                                       separators=(",", ":")).encode()
                require(raw == canonical and hashlib.sha256(raw).hexdigest() == expected,
                        "archive received-map payload SHA mismatch")
                info = payload["info"]
                require(len(payload["data"]) == info["width"] * info["height"],
                        "archive received-map shape mismatch")
                blobs[expected] = {"compressed_sha256": hashlib.sha256(compressed).hexdigest(),
                                   "decoded_bytes": len(raw), "info": info}
                payloads[expected] = payload
            info = blobs[expected]["info"]
            if name == "fused":
                geometry = snapshot["map"]
            elif name.startswith("navigation:"):
                geometry = snapshot["path_maps"][name.split(":", 1)[1]]
            else:
                geometry = None if navigation_mode else snapshot["path_maps"][name]
            if geometry is not None:
                require([info["height"], info["width"]] == geometry["native_shape"]
                        and info["resolution"] == geometry["native_resolution_m"]
                        and [info["origin"]["position"][axis] for axis in ("x", "y")]
                        == geometry["native_origin_m"], "archive map geometry mismatch")
        if navigation_mode:
            for name in ("tb1", "tb2", "tb3"):
                source = metadata["navigation_sources"][name]
                path = snapshot["path_maps"][name]
                own_sha = metadata["map_sources"][name]["payload_sha256"]
                shared_sha, nav_sha = metadata["map_payload_sha256"], source["payload_sha256"]
                require(source["epoch"] == snapshot["epoch"]
                        and source["composition_version"] == COMPOSITION_VERSION
                        and source["input_own_map_payload_sha256"] == own_sha
                        and source["input_shared_map_payload_sha256"] == shared_sha,
                        "archive navigation input identities mismatch")
                require(path["source"] == "delivered_navigation_map"
                        and path["payload_sha256"] == nav_sha
                        and all(path[key] == source[key] for key in (
                            "epoch", "sequence", "version", "source_stamp", "received_stamp",
                            "composition_version", "input_own_map_payload_sha256",
                            "input_shared_map_payload_sha256", "input_own_source_stamp",
                            "received_stamp_scope", "shared_map_version")),
                        "archive path map is not the actual delivered navigation map")
                identity = (own_sha, shared_sha, nav_sha)
                if identity not in navigation_replays:
                    rebuilt = reconstruct_navigation_payload(
                        payloads[own_sha], payloads[shared_sha])
                    encoded = json.dumps(rebuilt, allow_nan=False, sort_keys=True,
                                         separators=(",", ":")).encode()
                    require(rebuilt == payloads[nav_sha]
                            and hashlib.sha256(encoded).hexdigest() == nav_sha,
                            "archive navigation bytes fail independent owner-authority "
                            "reconstruction")
                    navigation_replays[identity] = {
                        "own_payload_sha256": own_sha, "shared_payload_sha256": shared_sha,
                        "navigation_payload_sha256": nav_sha,
                        "independent_numpy_projection": True,
                    }
        snapshots.add(snapshot["digest"])
    return {"passed": True, "unique_snapshots": len(snapshots), "unique_maps": len(blobs),
            "maps": blobs, "navigation_reconstructions": list(navigation_replays.values()),
            "scope": "exact received payloads, native navigation reconstruction "
                     "and snapshot identity"}


def audit(directory, root, freeze):
    phase, base, native, command, scalar, sources = load_native_gates(root, freeze)
    exclude_preparation_capacity_comparison(native)
    motion_cache = {}
    original_physics = dispatch_controlled_physics(native, [directory], motion_cache)
    try:
        result = phase.corrected_audit(base, native, command, [directory])
    finally:
        native.audit_physics = original_physics
    episodes = []
    metadata = json.loads((directory / "benchmark_metadata.json").read_text())
    motion_probe = not any(metadata.get(key) for key in (
        "terminal_probe", "deadline_probe", "fault_probe"))
    errors = ["native: " + str(error) for error in result.get("errors", [])]
    if not result.get("passed") and not errors:
        errors.append("native audit failed; see nested native evidence")
    for metadata_path in sorted(directory.glob("worker*/episode*/metadata.json")):
        episode = metadata_path.parent
        row = {"directory": str(episode)}
        try:
            row["scalar"] = scalar.audit_episode(episode, freeze)
            row["evaluator_phase"] = audit_phase(episode)
            row["observation_archives"] = audit_archives(episode)
            row["motion"] = (motion_cache[episode] if episode in motion_cache
                             else audit_motion(episode))
            row["execution_inputs"] = audit_execution_inputs(episode, row["motion"])
            row["activity"] = audit_activity(episode)
            if motion_probe:
                row["activity_availability"] = audit_probe_activity(episode)
                row["probe_execution"] = audit_probe_execution(episode)
            components = ("scalar", "evaluator_phase", "observation_archives",
                          "execution_inputs", "activity", "motion")
            if motion_probe:
                components += ("activity_availability", "probe_execution")
            for component in components:
                if row[component].get("passed") is not True:
                    errors.append(str(episode) + ": " + component + " audit failed")
        except (OSError, ValueError, TypeError, KeyError, IndexError, zlib.error) as error:
            row["error"] = repr(error)
            errors.append(str(episode) + ": " + repr(error))
        episodes.append(row)
    if not episodes:
        errors.append("no native episodes found")
    return {
        "schema": "mr3-p2a-preparation-audit-v1", "freeze": freeze,
        "passed": result.get("passed") is True and not errors,
        "errors": errors, "source_bindings": sources,
        "native": result, "episodes": episodes,
        "scope": "scripted engineering/reset/clock/reward/native closure; no policy reliability",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if re.fullmatch(r"[0-9a-f]{40}", args.freeze) is None:
        parser.error("freeze must be an exact 40-hex Git commit identity")
    if args.output.exists():
        parser.error("audit output exists; choose a new path")
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists())
    result = audit(args.directory, root, args.freeze)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
