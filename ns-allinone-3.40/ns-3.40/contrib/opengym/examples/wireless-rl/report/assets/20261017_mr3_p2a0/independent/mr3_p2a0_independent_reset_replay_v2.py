"""Independent read-only exact received-map replay of P2A.0 native evidence."""

import copy
from collections import Counter
import gzip
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_reset"
FREEZE = "f8694025d618532e851796d2f01aaa3aca322800"
COMPONENT = ROOT / ("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/"
                    "multi_robot_exploration")
OUTPUT = Path("/tmp/mr3_p2a0_independent_reset_replay_v2.json")
assert not OUTPUT.exists()
inputs = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = path.read_bytes()
    inputs[str(path)] = {"bytes": len(raw), "sha256": sha(raw)}
    return raw


def load(path):
    return json.loads(read(path))


def rows(path):
    raw = read(path)
    assert not raw or raw.endswith(b"\n"), "partial native JSONL: " + str(path)
    return [json.loads(line) for line in raw.splitlines()]


def payload_grid(payload):
    info = payload["info"]
    return np.asarray(payload["data"], dtype=np.int16).reshape(info["height"], info["width"])


def origin(payload):
    return tuple(payload["info"]["origin"]["position"][axis] for axis in ("x", "y"))


source_proof = {}
for name in ("mr3_observation.py", "mr3_episode.py", "mr3_observation_archive.py", "mr3_adapter.py"):
    path = COMPONENT / name
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))],
                                     cwd=ROOT)
    assert frozen == read(path), "current source differs from native freeze: " + name
    source_proof[name] = {"freeze": FREEZE, "sha256": sha(frozen)}
sys.path.insert(0, str(COMPONENT.parent))
from multi_robot_exploration import mr3_observation as m  # noqa: E402

benchmark = load(RUN / "benchmark_summary.json")
assert benchmark["freeze"] == FREEZE
episodes = []
short_steps, zero_tails, replay_count = 0, 0, 0
for metadata_path in sorted(RUN.glob("worker*/episode*/metadata.json")):
    episode = metadata_path.parent
    metadata = load(metadata_path)
    assert metadata["freeze"] == FREEZE
    transitions = rows(episode / "transitions.jsonl")
    audit = rows(episode / "adapter.jsonl")
    starts = [entry["payload"]["start_sim_time_sec"] for entry in audit if entry["kind"] == "task_start"]
    assert len(starts) == 1
    archive = episode / "observation_inputs"
    snapshot_dir = archive / "snapshots"
    unique, referenced, zero_tail_rows, short_rows = {}, set(), [], []
    previous = None
    for index, transition in enumerate(transitions):
        snapshot = transition["snapshot"]
        info = transition["info"]
        assert snapshot["epoch"] == metadata["epoch"]
        assert m.snapshot_digest(snapshot) == snapshot["digest"]
        manifest_path = snapshot_dir / f"{snapshot['sequence']:08d}_{snapshot['digest']}.json"
        manifest = load(manifest_path)
        assert manifest["schema"] == "mr3-observation-input-archive-v1"
        assert manifest["scope"] == "encoder_result_before_publication"
        for key in ("epoch", "sequence", "candidate_version", "source_stamp"):
            assert manifest[key] == snapshot[key]
        assert manifest["snapshot_digest"] == snapshot["digest"]
        bundle = manifest["metadata"]
        assert bundle["epoch"] == snapshot["epoch"]
        assert bundle["map_version"] == snapshot["map_version"] == info["watermarks"]["map_version"]
        assert bundle["map_sources"] == snapshot["map"]["sources"] == info["watermarks"]["map_sources"]
        assert bundle["map_source_stamp"] == snapshot["map"]["source_stamp"]
        assert bundle["map_received_stamp"] == snapshot["map"]["received_stamp"]
        assert bundle["map_payload_sha256"] == info["watermarks"]["map_payload_sha256"]
        assert set(manifest["maps"]) == {"fused", *m.ROBOT_NAMES}
        payloads = {}
        for name, binding in manifest["maps"].items():
            expected = (bundle["map_payload_sha256"] if name == "fused"
                        else bundle["map_sources"][name]["payload_sha256"])
            assert binding == {"payload_sha256": expected, "artifact": f"maps/{expected}.json.gz"}
            path = archive / binding["artifact"]
            decoded = gzip.decompress(read(path))
            assert sha(decoded) == expected
            payloads[name] = json.loads(decoded)
            canonical = json.dumps(payloads[name], sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode()
            assert decoded == canonical
            shape = payload_grid(payloads[name]).shape
            geometry = snapshot["map"] if name == "fused" else snapshot["path_maps"][name]
            assert list(shape) == geometry["native_shape"]
            assert payloads[name]["info"]["resolution"] == geometry["native_resolution_m"]
            assert list(origin(payloads[name])) == geometry["native_origin_m"]
            if name != "fused":
                assert snapshot["path_maps"][name]["payload_sha256"] == expected
            referenced.add(path)
        if snapshot["digest"] not in unique:
            robots = copy.deepcopy(snapshot["robots"])
            for robot in robots:
                robot["navigation"]["sequence"] = robot["navigation"]["receipt_sequence"]
            maps = {name: {
                "grid": payload_grid(payloads[name]),
                "resolution": payloads[name]["info"]["resolution"],
                "origin": origin(payloads[name]), "epoch": snapshot["epoch"],
                **bundle["map_sources"][name],
            } for name in m.ROBOT_NAMES}
            replay = m.build_snapshot(
                payload_grid(payloads["fused"]), payloads["fused"]["info"]["resolution"],
                origin(payloads["fused"]), robots, snapshot["source_stamp"], snapshot["epoch"],
                snapshot["map_version"], snapshot["sequence"],
                map_source_stamp=bundle["map_source_stamp"],
                map_received_stamp=bundle["map_received_stamp"],
                map_sources=bundle["map_sources"], task_start=starts[0], robot_maps=maps)
            assert replay == snapshot, "full received-map replay mismatch: " + str(manifest_path)
            unique[snapshot["digest"]] = snapshot["sequence"]
            replay_count += 1
        if transition["kind"] == "step":
            dt = info["dt"]
            if dt == 0:
                assert transition["terminated"] and not transition["truncated"]
                assert info["action_submitted"] is False and info["command"] is None
                assert info["physical_dt"] == 0 and info["terminal_observation_reused"] is True
                assert snapshot == previous
                zero_tails += 1
                zero_tail_rows.append(index)
            elif dt < 1:
                dt_ns = m.timestamp_ns(dt)
                assert 0 < dt_ns < 1_000_000_000 and dt_ns % 20_000_000 == 0
                assert m.timestamp_ns(info["physical_dt"]) in (dt_ns, dt_ns + 20_000_000)
                assert transition["terminated"] and info.get("action_submitted", True)
                short_steps += 1
                short_rows.append(index)
        previous = snapshot
    manifests = sorted(snapshot_dir.glob("*.json"))
    assert len(manifests) == len(unique)
    assert len(set(unique.values())) == len(unique)
    assert set((archive / "maps").glob("*.json.gz")) == referenced
    published = [entry["payload"] for entry in audit if entry["kind"] == "observation"]
    assert len(published) == len(unique)
    assert {value["digest"] for value in published} == set(unique)
    assert all(value in [row["snapshot"] for row in transitions] for value in published)
    completed = [entry["payload"] for entry in audit if entry["kind"] == "snapshot_completed"]
    assert len(completed) == len(unique)
    assert all(entry["ok"] for entry in completed)
    robot_diagnostics = {}
    for robot_index, name in enumerate(m.ROBOT_NAMES):
        availability = []
        for snapshot in published:
            goal_choices = sorted({m.decode_joint_action(action)[robot_index]
                                   for action, allowed in enumerate(snapshot["joint_action_mask"])
                                   if allowed and m.decode_joint_action(action)[robot_index] < 8})
            availability.append({
                "sequence": snapshot["sequence"], "digest": snapshot["digest"],
                "phase": snapshot["robots"][robot_index]["navigation"]["phase"],
                "target_intersection_cells": snapshot["diagnostics"][
                    "per_robot_reachable_target_cells"][robot_index],
                "reachable_pool": snapshot["diagnostics"][
                    "per_robot_reachable_pool_counts"][robot_index],
                "reachable_selected": snapshot["diagnostics"][
                    "per_robot_reachable_selected_counts"][robot_index],
                "joint_legal_goal_choices": goal_choices,
                "own_seed_reason": snapshot["path_maps"][name]["seed_rejection_reason"],
            })
        commands = [row["info"]["command"] for row in transitions if row["kind"] == "step"
                    and row["info"].get("action_submitted", True)]
        digits = [m.decode_joint_action(command["action"])[robot_index] for command in commands]
        by_digest = {entry["digest"]: entry for entry in availability}
        source_opportunities = [by_digest[command["observation_digest"]] for command in commands]
        for digit, opportunity in zip(digits, source_opportunities):
            if digit < 8:
                assert digit in opportunity["joint_legal_goal_choices"]
        sent = [entry["payload"] for entry in audit if entry["kind"] == "native_send"
                and entry["payload"]["robot"] == name]
        delivered = [entry["payload"] for entry in audit if entry["kind"] == "delivery"
                     and entry["payload"]["stream"] == "receipt"
                     and entry["payload"]["source"] == name]
        accepted = [entry for entry in delivered if entry["payload"]["type"] == "accept"]
        results = [entry for entry in delivered if entry["payload"]["type"] == "result"]
        robot_diagnostics[name] = {
            "unique_snapshots": len(availability),
            "snapshots_with_target_intersection": sum(
                entry["target_intersection_cells"] > 0 for entry in availability),
            "snapshots_with_zero_target_intersection": sum(
                entry["target_intersection_cells"] == 0 for entry in availability),
            "snapshots_with_joint_legal_goal": sum(
                bool(entry["joint_legal_goal_choices"]) for entry in availability),
            "snapshots_with_pool_zero": sum(entry["reachable_pool"] == 0 for entry in availability),
            "own_seed_reason_counts": dict(Counter(
                str(entry["own_seed_reason"]) for entry in availability)),
            "submitted_action_digits": digits,
            "actual_decision_sources": len(source_opportunities),
            "decision_sources_with_joint_legal_goal": sum(
                bool(entry["joint_legal_goal_choices"]) for entry in source_opportunities),
            "decision_sources_with_zero_target_intersection": sum(
                entry["target_intersection_cells"] == 0 for entry in source_opportunities),
            "submitted_goal_components": sum(digit < 8 for digit in digits),
            "native_sends": sent,
            "actual_accept_receipts": accepted,
            "actual_accepted_goal_ids": sorted({entry["payload"]["goal_id"] for entry in accepted
                                                if entry["payload"]["value"] is True}),
            "actual_result_receipts": results,
            "actual_result_status_counts": dict(Counter(
                str(entry["payload"]["value"]) for entry in results)),
            "snapshot_geometry_and_mask_diagnostics": availability,
        }
    launch_lines = read(episode / "launch.log").decode().splitlines()
    planning_failures = [{"line": index, "text": line}
                         for index, line in enumerate(launch_lines, 1)
                         if re.search(r"tb[123]\.(planner_server|controller_server|bt_navigator)", line)
                         and any(word in line.lower() for word in (
                             "failed", "lethal", "aborting", "no valid", "error"))]
    evaluation = load(episode / f"{metadata['epoch']}.json")
    episodes.append({"directory": str(episode), "epoch": metadata["epoch"],
                     "transition_rows": len(transitions), "unique_snapshots": len(unique),
                     "manifest_files": len(manifests), "unique_full_payloads": len(referenced),
                     "zero_tail_rows": zero_tail_rows, "short_terminal_rows_in_20ms_quanta": short_rows,
                     "no_extra_or_duplicate_manifest_or_blob": True,
                     "full_observation_replayed_exact": True,
                     "per_robot": robot_diagnostics,
                     "isolated_evaluation_outcome_only": {key: evaluation.get(key) for key in (
                         "success", "termination_reason", "control_failure", "failure_reason",
                         "elapsed_sim_time_sec", "navigation_protocol_closed")},
                     "preserved_native_navigation_failure_lines": planning_failures,
                     "all_candidates_nav2_executable_proven": False})
assert len(episodes) == 4
assert "rclpy" not in sys.modules and "torch" not in sys.modules
script_raw = read(Path(__file__).resolve())
for path, binding in inputs.items():
    current = Path(path).read_bytes()
    assert len(current) == binding["bytes"] and sha(current) == binding["sha256"]
result = {
    "schema": "mr3-p2a0-independent-reset-native-map-archive-replay-v1", "passed": True,
    "freeze": FREEZE, "benchmark_passed": benchmark["passed"],
    "source_proof": source_proof, "inputs": inputs, "script_sha256": sha(script_raw),
    "exact_full_snapshot_replays": replay_count,
    "short_terminal_steps_in_20ms_quanta": short_steps,
    "zero_duration_reused_terminal_tails": zero_tails, "episodes": episodes,
    "jobs": {"ROS_messages": 0, "services": 0, "native_starts": 0, "process_signals": 0,
             "GPU": 0, "repository_writes": 0},
    "scope": "Independent received-map replay and descriptive scripted goal/Nav2 diagnostics",
    "limits": ["No policy efficacy, physical safety envelope,95% success or multi-day stability claim.",
               "The benchmark's complete native/scalar/ACK gates are audited separately.",
               "Target intersection/GOAL mask and actual acceptance do not prove Nav2 execution.",
               "Scripted short runs are not learned policy evaluations."],
}
with OUTPUT.open("x") as stream:
    stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
print(json.dumps({"passed": True, "output": str(OUTPUT), "sha256": sha(OUTPUT.read_bytes()),
                  "exact_full_snapshot_replays": replay_count,
                  "episodes": [{"directory": row["directory"],
                                "snapshots": row["unique_snapshots"],
                                "planner_failure_lines": len(row[
                                    "preserved_native_navigation_failure_lines"]),
                                "robots": {name: {key: diagnostic[key] for key in (
                                    "snapshots_with_zero_target_intersection",
                                    "snapshots_with_joint_legal_goal", "submitted_goal_components",
                                    "actual_accepted_goal_ids", "actual_result_status_counts")}
                                           for name, diagnostic in row["per_robot"].items()}}
                               for row in episodes]}, indent=2))
