"""Counterfactual frozen-map navigation/candidate replay; never starts ROS."""

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument("--root", type=Path)
PARSER.add_argument("--input", type=Path)
PARSER.add_argument("--output", required=True, type=Path)
ARGS = PARSER.parse_args()
ROOT = ARGS.root or next(parent for parent in Path(__file__).resolve().parents
                         if (parent / ".git").is_dir())
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
RUN = ARGS.input or WIRELESS / "report/assets/20261017_mr3_p2a0/native/reset"
OUTPUT = ARGS.output
assert not OUTPUT.exists()
SOURCE_PATHS = (
    ROS / "src/merge_map/merge_map/merge_map.py",
    ROS / "src/multi_robot_exploration/multi_robot_exploration/mr3_information.py",
    ROS / "src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py",
    WIRELESS / "mr3_learning/navigation_archive.py",
)
source_proof = {str(path.relative_to(ROOT)): {
    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in SOURCE_PATHS}
sys.path.insert(0, str(ROS / "src/merge_map"))
sys.path.insert(0, str(ROS / "src/multi_robot_exploration"))
sys.path.insert(0, str(WIRELESS))
from merge_map.merge_map import merge_maps, merge_navigation_map, _resample_grid  # noqa: E402
from nav_msgs.msg import OccupancyGrid  # noqa: E402
from multi_robot_exploration.mr3_information import map_digest, map_payload, restore_message  # noqa: E402
from multi_robot_exploration import mr3_observation as m  # noqa: E402
import rclpy  # noqa: E402
from mr3_learning.navigation_archive import reconstruct_navigation_payload  # noqa: E402

assert not rclpy.ok()
inputs = {}


def read(path):
    selected_gzip = not path.exists() and Path(str(path) + ".gz").exists()
    if selected_gzip:
        path = Path(str(path) + ".gz")
    raw = path.read_bytes()
    inputs[str(path)] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return gzip.decompress(raw) if selected_gzip else raw


def load(path):
    return json.loads(read(path))


def grid(message):
    return np.asarray(message.data, dtype=np.int16).reshape(message.info.height, message.info.width)


def origin(message):
    return (message.info.origin.position.x, message.info.origin.position.y)


cases = []
for relative, sequence, target in (
        ("worker0/episode001_open_101", 1, "tb2"),
        ("worker0/episode001_open_101", 11, "tb3"),
        ("worker0/episode002_open_101", 1, "tb2"),
        ("worker1/episode002_open_101", 1, "tb2")):
    episode = RUN / relative
    transitions = [json.loads(line) for line in read(episode / "transitions.jsonl").splitlines()]
    old = next(row["snapshot"] for row in transitions if row["snapshot"]["sequence"] == sequence)
    manifest = load(episode / "observation_inputs/snapshots" /
                    f"{old['sequence']:08d}_{old['digest']}.json")
    bundle = manifest["metadata"]
    maps = {}
    for name, entry in manifest["maps"].items():
        raw = gzip.decompress(read(episode / "observation_inputs" / entry["artifact"]))
        assert hashlib.sha256(raw).hexdigest() == entry["payload_sha256"]
        maps[name] = restore_message(OccupancyGrid(), json.loads(raw))
    unchanged = {name: map_digest(message) for name, message in maps.items()}
    hub = merge_maps([maps[name] for name in m.ROBOT_NAMES])
    assert map_payload(hub) == map_payload(maps["fused"])
    assert map_digest(hub) == bundle["map_payload_sha256"]
    navigation = {name: merge_navigation_map(maps[name], hub) for name in m.ROBOT_NAMES}
    own_entries, nav_entries, conservation = {}, {}, {}
    for name in m.ROBOT_NAMES:
        own = maps[name]
        own_entries[name] = {
            "grid": grid(own), "resolution": own.info.resolution, "origin": origin(own),
            "epoch": old["epoch"], **bundle["map_sources"][name],
        }
        nav = navigation[name]
        rebuilt = reconstruct_navigation_payload(map_payload(own), map_payload(hub))
        assert rebuilt == map_payload(nav)
        nav_entries[name] = {
            "grid": grid(nav), "resolution": nav.info.resolution, "origin": origin(nav),
            "epoch": old["epoch"], "version": bundle["map_version"], "sequence": sequence,
            "source_stamp": min(bundle["map_source_stamp"],
                                bundle["map_sources"][name]["source_stamp"]),
            "received_stamp": bundle["map_received_stamp"],
            "received_stamp_scope": "counterfactual_frozen_received_bundle_not_native_publication",
            "payload_sha256": map_digest(nav), "composition_version": m.NAVIGATION_COMPOSITION_VERSION,
            "input_own_map_payload_sha256": map_digest(own),
            "input_shared_map_payload_sha256": map_digest(hub),
            "shared_map_version": bundle["map_version"],
        }
        rr, cc = np.indices(grid(nav).shape)
        projected = _resample_grid(own, rr, cc, *origin(nav), nav.info.resolution)
        output = grid(nav)
        shared = grid(hub)
        assert np.all(output[projected >= 0] == projected[projected >= 0])
        assert np.all(output[(projected < 0) & (shared < 0)] == -1)
        assert np.all(output[projected >= 50] >= 50)
        conservation[name] = {
            "independent_numpy_reconstruction_matches": True,
            "own_occupied_output_cells": int(np.count_nonzero(projected >= 50)),
            "own_occupied_lost": int(np.count_nonzero((projected >= 50) & (output < 50))),
            "both_unknown_promoted": int(np.count_nonzero(
                (projected < 0) & (shared < 0) & (output >= 0))),
            "known_own_free_shared_occupied_conflicts": int(np.count_nonzero(
                (projected == 0) & (shared >= 50))),
        }
    robots = copy.deepcopy(old["robots"])
    for robot in robots:
        robot["navigation"]["sequence"] = robot["navigation"]["receipt_sequence"]
    new = m.build_snapshot(
        grid(hub), hub.info.resolution, origin(hub), robots, old["source_stamp"], old["epoch"],
        old["map_version"], old["sequence"], map_source_stamp=bundle["map_source_stamp"],
        map_received_stamp=bundle["map_received_stamp"], map_sources=bundle["map_sources"],
        task_start=old["source_stamp"] - old["task_elapsed_sec"],
        robot_maps=own_entries, navigation_maps=nav_entries)
    index = m.ROBOT_NAMES.index(target)
    choices = sorted({m.decode_joint_action(action)[index] for action, allowed in enumerate(
        new["joint_action_mask"]) if allowed and m.decode_joint_action(action)[index] < 8})
    assert choices
    assert new["diagnostics"]["per_robot_reachable_target_cells"][index] > 0
    assert new["candidate_rule"]["version"] == "mr3-navigation-geometric-staging-v5"
    assert unchanged == {name: map_digest(message) for name, message in maps.items()}
    point = (old["robots"][index]["x"], old["robots"][index]["y"])
    cell = m._cell(*point, hub.info.resolution, origin(hub), grid(hub).shape)
    cases.append({
        "episode": relative, "sequence": sequence, "robot": target,
        "old_snapshot_digest": old["digest"], "new_counterfactual_snapshot_digest": new["digest"],
        "old_target_intersection": old["diagnostics"]["per_robot_reachable_target_cells"][index],
        "new_navigation_target_intersection": new["diagnostics"]["per_robot_reachable_target_cells"][index],
        "old_pool": old["diagnostics"]["per_robot_reachable_pool_counts"][index],
        "new_pool": new["diagnostics"]["per_robot_reachable_pool_counts"][index],
        "new_joint_legal_goal_choices": choices,
        "estimated_seed": list(cell), "old_hub_seed_value": int(grid(hub)[cell]),
        "new_navigation_seed_value": int(grid(navigation[target])[cell]),
        "new_navigation_seed_diagnostics": new["path_maps"][target],
        "candidate_rule": new["candidate_rule"], "conservation": conservation,
        "global_hub_payload_sha256_unchanged": map_digest(hub),
        "actual_new_native_navigation_or_policy_run": False,
    })
assert not rclpy.ok() and "torch" not in sys.modules
for path in SOURCE_PATHS:
    raw = read(path)
    assert hashlib.sha256(raw).hexdigest() == source_proof[str(path.relative_to(ROOT))]["sha256"]
read(Path(__file__).resolve())
for path, proof in inputs.items():
    raw = Path(path).read_bytes()
    assert len(raw) == proof["bytes"] and hashlib.sha256(raw).hexdigest() == proof["sha256"]
result = {
    "schema": "mr3-owner-authoritative-navigation-counterfactual-replay-v1", "passed": True,
    "baseline_native_freeze": "f8694025d618532e851796d2f01aaa3aca322800",
    "candidate_source_proof": source_proof, "inputs": inputs, "cases": cases,
    "command": [sys.executable, *sys.argv],
    "environment": "system ROS Humble Python; PYTHONNOUSERSITE=1; no ROS initialization",
    "scope": "Frozen received-map method replay; production-native validation remains separate",
    "limits": ["Own observed free is local SLAM authority, not proof of physical free space.",
               "No own occupied cells or both-unknown cells are cleared/promoted by this rule.",
               "Global occupied-wins evaluation maps are byte-identical to the baseline native inputs.",
               "The old native failures remain; this is not a new native Nav2 execution or 95% result."],
    "jobs": {"ROS_initialized": False, "native_starts": 0, "messages": 0,
             "services": 0, "process_signals": 0, "GPU": 0, "repository_source_writes": 0, "evidence_json_writes": 1},
}
with OUTPUT.open("x") as stream:
    stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
print(json.dumps({"passed": True, "output": str(OUTPUT),
                  "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                  "cases": [{key: value for key, value in case.items() if key in (
                      "episode", "sequence", "robot", "old_target_intersection",
                      "new_navigation_target_intersection", "old_pool", "new_pool",
                      "new_joint_legal_goal_choices", "old_hub_seed_value",
                      "new_navigation_seed_value")} for case in cases]}, indent=2))
