#!/usr/bin/env python3
"""Replay versioned candidate sources on preserved raw maps; never start ROS."""

import argparse
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
ASSETS = ROOT / ("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
                 "report/assets/20261016_mr3_p2a")
FREEZE = "af37b2aaa3cb9980434f7f16c1f52dec2506319d"
COMPONENT = ROS / "src/multi_robot_exploration/multi_robot_exploration"
sys.path.insert(0, str(COMPONENT.parent))
from multi_robot_exploration import mr3_observation as current  # noqa: E402


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("preserve existing diagnostic output: " + str(args.output))
    inputs = {}

    def read(path):
        path = path if path.exists() else Path(str(path) + ".gz")
        encoded = path.read_bytes()
        raw = gzip.decompress(encoded) if path.suffix == ".gz" else encoded
        inputs[str(path.relative_to(ROOT))] = {
            "bytes": len(encoded), "sha256": sha(encoded),
            "decoded_bytes": len(raw), "decoded_sha256": sha(raw),
        }
        return raw

    def load(path):
        return json.loads(read(path))

    old_bytes = subprocess.check_output([
        "git", "show", FREEZE + ":" + str((COMPONENT / "mr3_observation.py").relative_to(ROOT)),
    ], cwd=ROOT)
    episode_bytes = subprocess.check_output([
        "git", "show", FREEZE + ":" + str((COMPONENT / "mr3_episode.py").relative_to(ROOT)),
    ], cwd=ROOT)
    assert read(COMPONENT / "mr3_episode.py") == episode_bytes
    new_bytes = read(COMPONENT / "mr3_observation.py")
    old = ModuleType("frozen_mr3_observation")
    exec(compile(old_bytes, "git:" + FREEZE + ":mr3_observation.py", "exec"), old.__dict__)
    old_functions = {item.name: item for item in ast.parse(old_bytes).body
                     if isinstance(item, ast.FunctionDef)}
    new_functions = {item.name: item for item in ast.parse(new_bytes).body
                     if isinstance(item, ast.FunctionDef)}
    unchanged = ["native_traversable", "_path_distances", "_known_line", "_own_map_paths",
                 "_seed_diagnostics", "_action_masks"]
    assert all(ast.dump(old_functions[name]) == ast.dump(new_functions[name])
               for name in unchanged)
    # The only change inside selection itself is its initial frontier source.
    assert [ast.dump(item) for item in old_functions["_candidates"].body[4:]] == [
        ast.dump(item) for item in new_functions["_candidates"].body[2:]]

    def choices(snapshot, index):
        return sorted({current.decode_joint_action(action)[index]
                       for action, allowed in enumerate(snapshot["joint_action_mask"])
                       if allowed and current.decode_joint_action(action)[index] < 8})

    def run_case(label, positional, keywords, expected_old=None, expected_prototype=None):
        raw = positional[0]
        initial = raw.copy()
        own_before = {name: entry["grid"].copy()
                      for name, entry in keywords["robot_maps"].items()}
        before = old.build_snapshot(*positional, **keywords)
        after = current.build_snapshot(*positional, **keywords)
        if expected_old is not None:
            assert before == expected_old
        if expected_prototype is not None:
            for key in ("candidates", "per_robot_action_mask", "joint_action_mask"):
                assert after[key] == expected_prototype[key]
        for key in ("map", "maps", "path_maps", "robots", "task_elapsed_sec",
                    "task_remaining_sec"):
            assert before[key] == after[key]
        assert np.array_equal(raw, initial)
        assert all(np.array_equal(entry["grid"], own_before[name])
                   for name, entry in keywords["robot_maps"].items())
        replay_args = list(positional)
        replay_args[3] = list(reversed(copy.deepcopy(positional[3])))
        replay_kw = {**keywords,
                     "robot_maps": dict(reversed(list(keywords["robot_maps"].items())))}
        assert current.build_snapshot(*replay_args, **replay_kw) == after
        return {
            "label": label, "old_digest": before["digest"], "new_digest": after["digest"],
            "old_exact_snapshot_replayed": expected_old is not None,
            "old_offline_prototype_candidates_and_masks_replayed": (
                expected_prototype is not None),
            "new_candidate_rule": after["candidate_rule"],
            "new_frontier_sources": after["diagnostics"]["frontier_sources"],
            "robots": {name: {
                "target_cells": after["diagnostics"]["per_robot_reachable_target_cells"][index],
                "old_pool": before["diagnostics"]["per_robot_reachable_pool_counts"][index],
                "new_pool": after["diagnostics"]["per_robot_reachable_pool_counts"][index],
                "old_selected": before["diagnostics"][
                    "per_robot_reachable_selected_counts"][index],
                "new_selected": after["diagnostics"][
                    "per_robot_reachable_selected_counts"][index],
                "old_legal_goal_choices": choices(before, index),
                "new_legal_goal_choices": choices(after, index),
            } for index, name in enumerate(current.ROBOT_NAMES)},
            "joint_mask_changed_actions": [index for index, (first, second) in enumerate(zip(
                before["joint_action_mask"], after["joint_action_mask"])) if first != second],
            "maps_states_rasters_and_task_inputs_unchanged": True,
            "dictionary_permutation_replayed": True,
        }

    prior = ASSETS / "native_v6/pilot_infrastructure"
    saved = prior / "frontier_union_feasibility_v6"
    fused = np.full((100, 100), -1, dtype=np.int8)
    fused[5:95, 5:95] = 0
    small = np.full_like(fused, -1)
    small[43:57, 43:57] = 0
    robots = [{"name": name, "x": x, "y": .05, "yaw": 0., "v": 0., "w": 0.,
               "valid": True, "source_stamp": 10., "received_stamp": 10.,
               "navigation": {"phase": "idle", "goal_id": None, "goal_x": None,
                              "goal_y": None, "commitment_until": 0.}}
              for name, x in zip(current.ROBOT_NAMES, (-3.05, .05, 3.05))]
    maps = {name: {"grid": small.copy() if name == "tb2" else fused.copy(),
                   "resolution": .1, "origin": (-5., -5.), "epoch": "counterexample",
                   "source_stamp": 10., "received_stamp": 10., "version": 1, "sequence": 1,
                   "payload_sha256": "synthetic-delivered-" + name}
            for name in current.ROBOT_NAMES}
    synthetic = run_case(
        "preserved_v5_synthetic", (fused, .1, (-5., -5.), robots, 10., "counterexample", 1, 1),
        {"robot_maps": maps}, load(saved / "same_v5_synthetic_old_snapshot.json"),
        load(saved / "same_v5_synthetic_prototype_snapshot.json"))
    assert synthetic["robots"]["tb2"]["old_pool"] == 0
    assert synthetic["robots"]["tb2"]["new_pool"] == 20
    assert synthetic["robots"]["tb2"]["new_legal_goal_choices"]

    capture = ASSETS / "native_v5/pilot_infrastructure/raw_map_observer_round0002_w3_v1"
    events = [json.loads(line) for line in read(capture / "events.jsonl").splitlines()]
    bundles = [event["payload"] for event in events if event["kind"] == "map_metadata"]
    assert len(bundles) == 1
    bundle = bundles[0]
    actor_event = next(event for event in events if event["kind"] == "actor_snapshot"
                       and event["sequence"] == 81 and event["saved_line_proof"] is not None)
    actor = load(capture / actor_event["artifact"])
    assert actor["digest"] == "99ca848dae9f342c61ed4cd2e00a27ae54dc9a20865050cdd2579889d5d7e6cc"
    assert old.snapshot_digest(actor) == actor["digest"]
    assert actor["map"]["sources"] == bundle["map_sources"]

    def payload(digest):
        raw = read(capture / "maps" / (digest + ".json.gz"))
        assert sha(raw) == digest
        return json.loads(raw)

    def grid(value):
        info = value["info"]
        return np.asarray(value["data"], dtype=np.int16).reshape(info["height"], info["width"])

    def origin(value):
        return tuple(value["info"]["origin"]["position"][key] for key in ("x", "y"))

    fused_payload = payload(bundle["map_payload_sha256"])
    own = {name: payload(bundle["map_sources"][name]["payload_sha256"])
           for name in current.ROBOT_NAMES}
    maps = {name: {"grid": grid(own[name]), "resolution": own[name]["info"]["resolution"],
                   "origin": origin(own[name]), "epoch": actor["epoch"],
                   **bundle["map_sources"][name]} for name in current.ROBOT_NAMES}
    robots = copy.deepcopy(actor["robots"])
    for robot in robots:
        robot["navigation"]["sequence"] = robot["navigation"]["receipt_sequence"]
    actual = run_case(
        "preserved_v5_actor81", (
            grid(fused_payload), fused_payload["info"]["resolution"], origin(fused_payload),
            robots, actor["source_stamp"], actor["epoch"],
            actor["map_version"], actor["sequence"]),
        {"robot_maps": maps, "map_source_stamp": bundle["map_source_stamp"],
         "map_received_stamp": bundle["map_received_stamp"], "map_sources": bundle["map_sources"],
         "task_start": actor["source_stamp"] - actor["task_elapsed_sec"]}, actor,
        load(saved / "old_v5_actor81_prototype_snapshot.json"))
    assert actual["robots"]["tb1"]["old_pool"] == 0
    assert actual["robots"]["tb1"]["new_pool"] == 2
    assert actual["joint_mask_changed_actions"] == [88]
    fused_grid = grid(fused_payload)
    cell = current._cell(
        robots[0]["x"], robots[0]["y"], fused_payload["info"]["resolution"],
        origin(fused_payload), fused_grid.shape)
    assert fused_grid[cell] == 100
    actual["fused_seed_occupancy_unchanged"] = {
        "tb1_cell": list(cell), "value": int(fused_grid[cell])}
    actual["navigation_executability_established"] = False

    prefix_dir = prior / "prefix20_controllability_captured_v6"
    prefixes = []
    for entry in load(prefix_dir / "prefix_manifest.json"):
        raw = read(prefix_dir / entry["capture_file"])
        assert sha(raw) == entry["sha256"] and len(raw) == entry["prefix_bytes"]
        rows = [json.loads(line) for line in raw.splitlines()]
        assert len(rows) == 21
        counts = {name: 0 for name in current.ROBOT_NAMES}
        for row in rows:
            snapshot = row["snapshot"]
            assert old.snapshot_digest(snapshot) == snapshot["digest"]
            per_robot, joint, _ = old._action_masks(
                snapshot["robots"], snapshot["candidates"], snapshot["source_stamp"])
            assert per_robot == snapshot["per_robot_action_mask"]
            assert joint == snapshot["joint_action_mask"]
            for index, name in enumerate(current.ROBOT_NAMES):
                counts[name] += bool(choices(snapshot, index))
        prefixes.append({"worker": entry["worker"], "snapshots": len(rows),
                         "snapshots_with_legal_goal": counts, "new_rule_counterfactual": None})
    assert next(item for item in prefixes if item["worker"] == 1)[
        "snapshots_with_legal_goal"]["tb2"] == 0
    read(Path(__file__).resolve())
    assert "rclpy" not in sys.modules and "torch" not in sys.modules
    result = {
        "schema": "mr3-p2a0-production-candidate-frontiers-replay-v1", "passed": True,
        "old_freeze": FREEZE, "old_observation_sha256": sha(old_bytes),
        "current_observation_sha256": sha(new_bytes), "inputs": inputs,
        "unchanged_function_asts": unchanged,
        "candidate_staging_reservation_fps_and_clearance_statements_unchanged": True,
        "synthetic": synthetic, "preserved_raw_case": actual, "v6_prefixes": prefixes,
        "native_ROS_GPU_observer_optimizer_jobs": 0,
        "limits": [
            "V6 prefixes lack full raw maps: no new-rule improvement can be inferred.",
            "The exact V5 candidate improvement leaves its fused/navigation seed occupied.",
            "Geometric candidate availability does not establish Nav2 execution or95% success.",
            "No trained weights or prior validation are reused for the new candidate version."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": True, "output": str(args.output),
                      "sha256": sha(args.output.read_bytes()),
                      "synthetic_tb2": synthetic["robots"]["tb2"],
                      "preserved_raw_tb1": actual["robots"]["tb1"]}, indent=2))


if __name__ == "__main__":
    main()
