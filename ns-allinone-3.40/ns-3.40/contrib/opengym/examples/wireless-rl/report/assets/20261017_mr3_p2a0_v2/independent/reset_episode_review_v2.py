"""Independent read-only exact received-map replay of P2A.0 native evidence."""

import argparse
from collections import Counter
import copy
import re
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path("/home/zhuyulab/ns3-workspace")
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument("--episode", type=Path, required=True)
PARSER.add_argument("--output", type=Path, required=True)
ARGS = PARSER.parse_args()
RUN = ARGS.episode.parent.parent
FREEZE = "96c201e0e258bd0fe192fc03c6716fc694b7a9b7"
COMPONENT = ROOT / ("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/"
                    "multi_robot_exploration")
OUTPUT = ARGS.output
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


FROZEN_ROOT = Path("/tmp/mr3_p2a0_v2_frozen_replay_sources") / ARGS.output.stem
FROZEN_COMPONENT = FROZEN_ROOT / "multi_robot_exploration"
FROZEN_COMPONENT.mkdir(parents=True, exist_ok=True)
package_raw = subprocess.check_output(["git", "show", FREEZE + ":" + str(
    (COMPONENT / "__init__.py").relative_to(ROOT))], cwd=ROOT)
(FROZEN_COMPONENT / "__init__.py").write_bytes(package_raw)
source_proof = {}
for name in ("mr3_observation.py", "mr3_episode.py", "mr3_observation_archive.py", "mr3_adapter.py",
             "mr3_information.py", "mr3_activity.py"):
    path = COMPONENT / name
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))],
                                     cwd=ROOT)
    frozen_path = FROZEN_COMPONENT / name
    frozen_path.write_bytes(frozen)
    assert frozen == read(frozen_path)
    source_proof[name] = {"freeze": FREEZE, "sha256": sha(frozen),
                          "source": FREEZE + ":" + str(path.relative_to(ROOT)),
                          "current_worktree_matches_native_freeze": path.read_bytes() == frozen}
sys.path.insert(0, str(FROZEN_ROOT))
from multi_robot_exploration import mr3_observation as m  # noqa: E402
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
(FROZEN_ROOT / "mr3_learning").mkdir(exist_ok=True)
package_raw = subprocess.check_output(["git", "show", FREEZE + ":" + str(
    (WIRELESS / "mr3_learning/__init__.py").relative_to(ROOT))], cwd=ROOT)
(FROZEN_ROOT / "mr3_learning/__init__.py").write_bytes(package_raw)
for relative in ("mr3_learning/navigation_archive.py", "mr3_learning/audit_activity.py"):
    path = WIRELESS / relative
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))],
                                     cwd=ROOT)
    frozen_path = FROZEN_ROOT / relative
    frozen_path.write_bytes(frozen)
    assert frozen == read(frozen_path)
    source_proof[relative] = {"freeze": FREEZE, "sha256": sha(frozen),
                              "source": FREEZE + ":" + str(path.relative_to(ROOT))}
from mr3_learning.navigation_archive import reconstruct_navigation_payload  # noqa: E402
from mr3_learning.audit_activity import audit_episode as audit_activity  # noqa: E402

assert (ARGS.episode / "summary.json").exists(), "episode not closed yet"
episodes = []
short_steps, zero_tails, replay_count = 0, 0, 0
for metadata_path in (ARGS.episode / "metadata.json",):
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
        assert manifest["schema"] == "mr3-observation-input-archive-v2"
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
        assert set(manifest["maps"]) == {"fused", *m.ROBOT_NAMES,
                                          *("navigation:" + name for name in m.ROBOT_NAMES)}
        assert bundle["navigation_sources"] == snapshot["navigation_sources"] == info[
            "watermarks"]["navigation_sources"]
        assert bundle["navigation_composition"] == {"version": m.NAVIGATION_COMPOSITION_VERSION}
        payloads = {}
        for name, binding in manifest["maps"].items():
            expected = (bundle["map_payload_sha256"] if name == "fused" else
                        bundle["navigation_sources"][name.split(":", 1)[1]]["payload_sha256"]
                        if name.startswith("navigation:") else
                        bundle["map_sources"][name]["payload_sha256"])
            assert binding == {"payload_sha256": expected, "artifact": f"maps/{expected}.json.gz"}
            path = archive / binding["artifact"]
            decoded = gzip.decompress(read(path))
            assert sha(decoded) == expected
            payloads[name] = json.loads(decoded)
            canonical = json.dumps(payloads[name], sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode()
            assert decoded == canonical
            if name == "fused" or name.startswith("navigation:"):
                shape = payload_grid(payloads[name]).shape
                geometry = (snapshot["map"] if name == "fused" else
                            snapshot["path_maps"][name.split(":", 1)[1]])
                assert list(shape) == geometry["native_shape"]
                assert payloads[name]["info"]["resolution"] == geometry["native_resolution_m"]
                assert list(origin(payloads[name])) == geometry["native_origin_m"]
                if name != "fused":
                    assert geometry["payload_sha256"] == expected
            referenced.add(path)
        for name in m.ROBOT_NAMES:
            source = bundle["navigation_sources"][name]
            assert source["input_own_map_payload_sha256"] == bundle["map_sources"][name]["payload_sha256"]
            assert source["input_shared_map_payload_sha256"] == bundle["map_payload_sha256"]
            assert source["composition_version"] == m.NAVIGATION_COMPOSITION_VERSION
            rebuilt = reconstruct_navigation_payload(payloads[name], payloads["fused"])
            assert rebuilt == payloads["navigation:" + name]
            assert sha(json.dumps(rebuilt, allow_nan=False, sort_keys=True,
                                  separators=(",", ":")).encode()) == source["payload_sha256"]
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
            navigation_maps = {name: {
                "grid": payload_grid(payloads["navigation:" + name]),
                "resolution": payloads["navigation:" + name]["info"]["resolution"],
                "origin": origin(payloads["navigation:" + name]),
                **bundle["navigation_sources"][name],
            } for name in m.ROBOT_NAMES}
            replay = m.build_snapshot(
                payload_grid(payloads["fused"]), payloads["fused"]["info"]["resolution"],
                origin(payloads["fused"]), robots, snapshot["source_stamp"], snapshot["epoch"],
                snapshot["map_version"], snapshot["sequence"],
                map_source_stamp=bundle["map_source_stamp"],
                map_received_stamp=bundle["map_received_stamp"],
                map_sources=bundle["map_sources"], task_start=starts[0], robot_maps=maps,
                navigation_maps=navigation_maps)
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
                assert dt == info["physical_dt"]
                assert abs(dt / .02 - round(dt / .02)) < 1e-9
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
    activity_proof = audit_activity(episode)
    assert activity_proof["passed"]
    for path in (episode / "adapter.jsonl", episode / "transitions.jsonl"):
        read(path)
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
        final_robot = published[-1]["robots"][robot_index]
        activity = final_robot["activity"]
        robot_diagnostics[name] = {
            "final_received_activity": activity,
            "received_path_gt_0_05m": activity["estimated_path_m"] is not None and activity["estimated_path_m"] > .05,
            "final_received_accepted_goal_count": final_robot["navigation"]["accepted_goal_count"],
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
                     "activity_independent_replay": activity_proof,
                     "actual_navigation_maps_reconstructed_independently": True,
                     "transition_rows": len(transitions), "unique_snapshots": len(unique),
                     "manifest_files": len(manifests), "unique_full_payloads": len(referenced),
                     "zero_tail_rows": zero_tail_rows, "short_20ms_terminal_rows": short_rows,
                     "no_extra_or_duplicate_manifest_or_blob": True,
                     "full_observation_replayed_exact": True,
                     "per_robot": robot_diagnostics,
                     "isolated_evaluation_outcome_only": {key: evaluation.get(key) for key in (
                         "success", "termination_reason", "control_failure", "failure_reason",
                         "elapsed_sim_time_sec", "navigation_protocol_closed")},
                     "preserved_native_navigation_failure_lines": planning_failures,
                     "all_candidates_nav2_executable_proven": False})
assert len(episodes) == 1
assert "rclpy" not in sys.modules and "torch" not in sys.modules
script_raw = read(Path(__file__).resolve())
for path, binding in inputs.items():
    current = Path(path).read_bytes()
    assert len(current) == binding["bytes"] and sha(current) == binding["sha256"]
result = {
    "schema": "mr3-p2a0-v2-independent-reset-episode-review-v2", "passed": True,
    "freeze": FREEZE, "benchmark_complete": (RUN / "benchmark_summary.json").exists(),
    "source_proof": source_proof, "inputs": inputs, "script_sha256": sha(script_raw),
    "exact_full_snapshot_replays": replay_count, "short_20ms_terminal_steps": short_steps,
    "zero_duration_reused_terminal_tails": zero_tails, "episodes": episodes,
    "jobs": {"ROS_messages": 0, "services": 0, "native_starts": 0, "process_signals": 0,
             "GPU": 0, "repository_writes": 0},
    "scope": "Independent seven-map/native-navigation NumPy provenance, full candidate/mask/raster/activity replay and terminal reuse",
    "limits": ["No policy efficacy, physical safety envelope, 95% success or multi-day stability claim.",
               "The benchmark's complete native/scalar/ACK gates are audited separately."],
}
with OUTPUT.open("x") as stream:
    stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
print(json.dumps({"passed": True, "output": str(OUTPUT), "sha256": sha(OUTPUT.read_bytes()),
                  "exact_full_snapshot_replays": replay_count,
                  "episodes": [{"directory": entry["directory"],
                                "snapshots": entry["unique_snapshots"],
                                "native_warning_lines": len(entry["preserved_native_navigation_failure_lines"]),
                                "robots": {name: {key: robot[key] for key in (
                                    "snapshots_with_zero_target_intersection", "snapshots_with_joint_legal_goal",
                                    "submitted_goal_components", "actual_accepted_goal_ids",
                                    "actual_result_status_counts", "final_received_activity", "received_path_gt_0_05m")}
                                           for name, robot in entry["per_robot"].items()}}
                               for entry in episodes]}, indent=2))
