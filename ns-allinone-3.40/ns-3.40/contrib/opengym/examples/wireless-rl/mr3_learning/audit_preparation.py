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
from .audit_activity import audit_episode as audit_activity
from .audit_motion import audit_episode as audit_motion


def audit_execution_inputs(directory):
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
    require([clock for clock in consumed if clock > release] == required_clocks,
            "a task/cleanup quantum advanced without exact motion gate completion")
    initial = transitions[0]["info"]["initial_motion_status"]
    require(initial["ready"] is True and initial["clock_ns"] == release
            and received.get(release) == initial and release in consumed,
            "task release lacks exact healthy motion completion at the initial pause")
    return {"passed": True, "topology": topology, "costmap_receipts": count,
            "unique_costmaps": len(blobs), "streams": sorted(streams),
            "consumed_motion_phases": len(consumed),
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
    result = phase.corrected_audit(base, native, command, [directory])
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
            row["execution_inputs"] = audit_execution_inputs(episode)
            row["activity"] = audit_activity(episode)
            row["motion"] = audit_motion(episode)
            if motion_probe:
                row["probe_execution"] = audit_probe_execution(episode)
            for component in ("scalar", "evaluator_phase", "observation_archives",
                              "execution_inputs", "activity", "motion"):
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
