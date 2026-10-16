"""Read-only received-map reconstruction for saved Nav2 lethal-start warnings."""

import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path("/home/zhuyulab/ns3-workspace")
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
EPISODE = ROS / "log/mr3_p2a0/mr3_p2a0_20261017_reset/worker0/episode001_open_101"
FREEZE = "f8694025d618532e851796d2f01aaa3aca322800"
OUTPUT = Path("/tmp/mr3_p2a0_reset_lethal_start_forensics.json")
assert not OUTPUT.exists()
inputs, source_proof = {}, {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = path.read_bytes()
    inputs[str(path)] = {"bytes": len(raw), "sha256": sha(raw)}
    return raw


def load(path):
    return json.loads(read(path))


for relative in (
        "src/multi_robot_exploration/multi_robot_exploration/mr3_information.py",
        "src/multi_robot_exploration/multi_robot_exploration/mr3_transport.py",
        "src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py",
        "src/merge_map/merge_map/merge_map.py"):
    path = ROS / relative
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))],
                                     cwd=ROOT)
    assert read(path) == frozen
    source_proof[relative] = {"freeze": FREEZE, "sha256": sha(frozen)}
sys.path.insert(0, str(ROS / "src/multi_robot_exploration"))
sys.path.insert(0, str(ROS / "src/merge_map"))
from merge_map.merge_map import merge_maps  # noqa: E402
from nav_msgs.msg import OccupancyGrid  # noqa: E402
import rclpy  # noqa: E402
from multi_robot_exploration.mr3_information import (  # noqa: E402
    map_digest, map_payload, restore_message,
)
from multi_robot_exploration import mr3_observation as m  # noqa: E402

assert not rclpy.ok(), "This reader must never initialize ROS"
metadata = load(EPISODE / "metadata.json")
summary = load(EPISODE / "summary.json")
assert metadata["freeze"] == FREEZE and summary["closed"]
transitions = [json.loads(line) for line in read(EPISODE / "transitions.jsonl").splitlines()]
audit = [json.loads(line) for line in read(EPISODE / "adapter.jsonl").splitlines()]
snapshots = {entry["snapshot"]["sequence"]: entry["snapshot"] for entry in transitions}
native_sends = [entry for entry in audit if entry["kind"] == "native_send"]
launch_lines = read(EPISODE / "launch.log").decode().splitlines()
failures = [{"line": index, "text": line} for index, line in enumerate(launch_lines, 1)
            if "GridBased" in line and ("lethal" in line or "failed to generate" in line)]


def raw_grid(grid):
    return np.asarray(grid.data).reshape(grid.info.height, grid.info.width)


def seed(grid, point):
    info = grid.info
    cell = m._cell(point[0], point[1], info.resolution,
                   (info.origin.position.x, info.origin.position.y), raw_grid(grid).shape)
    return {"row_column": list(cell) if cell else None,
            "value": int(raw_grid(grid)[cell]) if cell else None,
            "payload_sha256": map_digest(grid)}


def contributions(output, cell, own):
    # Match the original merge_maps positive-area cell projection exactly;
    # return every input cell inspected for this one output cell, not a label
    # for the physical object that generated any occupied observation.
    row, column = cell
    resolution = output.info.resolution
    x = output.info.origin.position.x + column * resolution
    y = output.info.origin.position.y + row * resolution
    answer = {}
    for name, grid in own.items():
        first_c = math.floor((x - grid.info.origin.position.x) / resolution + 1e-9)
        last_c = math.ceil((x - grid.info.origin.position.x) / resolution + 1. - 1e-9) - 1
        first_r = math.floor((y - grid.info.origin.position.y) / resolution + 1e-9)
        last_r = math.ceil((y - grid.info.origin.position.y) / resolution + 1. - 1e-9) - 1
        cells = sorted({(first_r, first_c), (first_r, last_c),
                        (last_r, first_c), (last_r, last_c)})
        values = [{"row_column": [rr, cc], "value": (
            int(raw_grid(grid)[rr, cc]) if 0 <= rr < grid.info.height
            and 0 <= cc < grid.info.width else None)} for rr, cc in cells]
        answer[name] = {"payload_sha256": map_digest(grid), "source_cells": values,
                        "occupied_support": any(value["value"] is not None
                                                and value["value"] >= 50 for value in values)}
    return answer


cases = []
for name, command_id in (("tb2", 1), ("tb3", 11)):
    native = next(entry for entry in native_sends if entry["payload"]["robot"] == name
                  and entry["payload"]["command_id"] == command_id)
    command = next(entry["info"]["command"] for entry in transitions
                   if entry["kind"] == "step" and entry["info"].get("command")
                   and entry["info"]["command"]["command_id"] == command_id)
    snapshot = snapshots[command["observation_sequence"]]
    assert snapshot["digest"] == command["observation_digest"] == m.snapshot_digest(snapshot)
    manifest = load(EPISODE / "observation_inputs/snapshots" /
                    f"{snapshot['sequence']:08d}_{snapshot['digest']}.json")
    assert manifest["snapshot_digest"] == snapshot["digest"]
    bundle = manifest["metadata"]
    assert bundle["map_version"] == snapshot["map_version"]
    assert bundle["map_sources"] == snapshot["map"]["sources"]
    transition = next(entry for entry in transitions if entry["snapshot"] == snapshot)
    assert bundle["map_payload_sha256"] == transition["info"]["watermarks"]["map_payload_sha256"]
    assert bundle["map_sources"] == transition["info"]["watermarks"]["map_sources"]
    grids, payloads = {}, {}
    for role, binding in manifest["maps"].items():
        raw = gzip.decompress(read(EPISODE / "observation_inputs" / binding["artifact"]))
        assert sha(raw) == binding["payload_sha256"]
        payloads[role] = json.loads(raw)
        grids[role] = restore_message(OccupancyGrid(), payloads[role])
        assert map_digest(grids[role]) == binding["payload_sha256"]
    own = {robot: grids[robot] for robot in m.ROBOT_NAMES}
    reconstructed_hub = merge_maps([own[robot] for robot in m.ROBOT_NAMES], "map")
    assert map_payload(reconstructed_hub) == payloads["fused"]
    assert map_digest(reconstructed_hub) == bundle["map_payload_sha256"]
    navigation = merge_maps([own[name], reconstructed_hub], "map")
    robot = next(robot for robot in snapshot["robots"] if robot["name"] == name)
    point = (robot["x"], robot["y"])
    nav_seed = seed(navigation, point)
    fused_seed = seed(reconstructed_hub, point)
    own_seed = seed(own[name], point)
    support = contributions(reconstructed_hub, fused_seed["row_column"], own)
    cases.append({
        "robot": name, "command_id": command_id, "native_send": native,
        "command": command, "snapshot_sequence": snapshot["sequence"],
        "snapshot_digest": snapshot["digest"], "snapshot_time": snapshot["source_stamp"],
        "estimated_pose_xy": list(point), "source_metadata": copy.deepcopy(bundle),
        "reconstructed_hub_payload_equals_archived_full_payload": True,
        "reconstructed_navigation_payload_sha256": map_digest(navigation),
        "navigation_equals_received_hub": map_payload(navigation) == payloads["fused"],
        "fused_seed": fused_seed, "own_seed": own_seed, "navigation_seed": nav_seed,
        "own_map_seed_diagnostics": snapshot["path_maps"][name],
        "own_map_contributions_to_fused_seed": support,
        "actual_master_costmap_or_planner_time_observation_available": False,
        "physical_identity_of_occupied_contributors_established": False,
    })
assert not rclpy.ok()
assert "torch" not in sys.modules
read(Path(__file__).resolve())
for path, binding in inputs.items():
    raw = Path(path).read_bytes()
    assert len(raw) == binding["bytes"] and sha(raw) == binding["sha256"]
result = {
    "schema": "mr3-p2a0-readonly-lethal-start-forensics-v1", "passed": True,
    "freeze": FREEZE, "source_proof": source_proof, "inputs": inputs,
    "cases": cases, "preserved_native_planning_failure_lines": failures,
    "source_inference": (
        "Ideal publish_maps sends each captured local map and immediately samples delivery; "
        "the same callback freezes local_snapshot. Same-bundle navigation is therefore replayed "
        "by the original merge_maps([own_received, hub]) function. No navigation publisher or "
        "master-costmap messages were separately captured."),
    "limits": [
        "A same-bundle occupied navigation seed is an observed-map fact, not a physical object label.",
        "Planning logs bind robot/target, but lack an exact planner invocation simulation watermark.",
        "Without original master costmaps, peer_layer/inflation and exact planner input remain unproven.",
        "No truth, map clearing, parameter changes, messages, services or native experiments were used."],
    "jobs": {"ROS_initialized": False, "ROS_messages": 0, "services": 0,
             "native_starts": 0, "process_signals": 0, "repository_writes": 0},
}
with OUTPUT.open("x") as stream:
    stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
print(json.dumps({"passed": True, "output": str(OUTPUT), "sha256": sha(OUTPUT.read_bytes()),
                  "cases": [{"robot": case["robot"], "snapshot_sequence": case["snapshot_sequence"],
                             "fused_seed": case["fused_seed"], "own_seed": case["own_seed"],
                             "navigation_seed": case["navigation_seed"],
                             "occupied_contributors": [name for name, contribution in case[
                                 "own_map_contributions_to_fused_seed"].items()
                                 if contribution["occupied_support"]]} for case in cases]}, indent=2))
