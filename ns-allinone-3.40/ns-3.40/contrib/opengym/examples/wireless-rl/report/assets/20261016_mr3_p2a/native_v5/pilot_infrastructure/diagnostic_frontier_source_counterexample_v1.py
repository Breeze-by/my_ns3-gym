#!/usr/bin/env python3
"""Synthetic CPU source counterexample; never launches ROS/Gazebo or a learner.

Run with -B; output must be a fresh path. This demonstrates a general frontier
source restriction. It does not diagnose actual v5 w0/tb2, whose zero target
intersection precedes frontier projection, nor prove a production repair.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    native = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/"
    relatives = [native + "multi_robot_exploration/" + name
                 for name in ("mr3_observation.py", "mr3_episode.py")]
    proof = {}
    for relative in relatives:
        current = (workspace / relative).read_bytes()
        frozen = subprocess.check_output(
            ["git", "show", args.freeze + ":" + relative], cwd=workspace)
        if current != frozen:
            raise ValueError("Source bytes differ from requested freeze: " + relative)
        proof[relative] = {"current_sha256": sha(current),
                           "freeze_sha256": sha(frozen),
                           "freeze_worktree_equal": True}
    sys.path.insert(0, str(workspace / native))
    import numpy as np
    import scipy
    from multi_robot_exploration import mr3_observation as m

    # Three fixed synthetic robots, with tb2's delivered own map smaller than
    # fusion. This is observed-map interface input, not simulator truth.
    fused = np.full((100, 100), -1, dtype=np.int8)
    fused[5:95, 5:95] = 0
    small = np.full_like(fused, -1)
    small[43:57, 43:57] = 0
    robots = [{
        "name": name, "x": x, "y": .05, "yaw": 0., "v": 0., "w": 0.,
        "valid": True, "source_stamp": 10., "received_stamp": 10.,
        "navigation": {"phase": "idle", "goal_id": None, "goal_x": None,
                       "goal_y": None, "commitment_until": 0.},
    } for name, x in zip(m.ROBOT_NAMES, (-3.05, .05, 3.05))]
    maps = {name: {
        "grid": small.copy() if name == "tb2" else fused.copy(),
        "resolution": .1, "origin": (-5., -5.), "epoch": "counterexample",
        "source_stamp": 10., "received_stamp": 10.,
        "payload_sha256": "synthetic-delivered-" + name,
        "version": 1, "sequence": 1,
    } for name in m.ROBOT_NAMES}
    original = {name: entry["grid"].copy() for name, entry in maps.items()}
    snap = m.build_snapshot(fused, .1, (-5., -5.), robots, 10.,
                            "counterexample", 1, 1, robot_maps=maps)
    diagnostic = snap["diagnostics"]
    assert diagnostic["per_robot_reachable_target_cells"][1] > 0
    assert diagnostic["per_robot_reachable_pool_counts"][1] == 0
    assert not any(snap["per_robot_action_mask"][1][:8])
    fused_traversable, fused_clearance = m.native_traversable(fused, .1)
    _, own_clearance = m.native_traversable(small, .1)
    states = [m._robot_state(robot, 10.) for robot in robots]
    cells = np.argwhere(fused_traversable & (fused_clearance >= m.TARGET_CLEARANCE_M))
    paths, provenance, _ = m._own_map_paths(
        maps, states, 10., "counterexample", .1, (-5., -5.), cells)
    # An illustrative safe own-frontier staging point; production generator
    # is never changed or monkeypatched, and no goal is sent anywhere.
    target, frontier = (51, 51), (51, 56)
    index = np.flatnonzero(np.all(cells == target, axis=1))[0]
    point = (-5 + (target[1] + .5) * .1, -5 + (target[0] + .5) * .1)
    assert np.isfinite(paths[index, 1])
    assert fused_clearance[target] >= .39 and own_clearance[target] >= .39
    assert m._known_line(small, target, frontier)
    assert math.dist(target, frontier) * .1 <= 1
    assert math.dist(point, (.05, .05)) > .1
    candidate = {"index": 0, "valid": True, "x": point[0], "y": point[1],
                 "reachable": np.isfinite(paths[index]).tolist()}
    _, joint_mask, _ = m._action_masks(states, [candidate], 10.)
    action = m.encode_joint_action((m.KEEP, 0, m.KEEP))
    assert joint_mask[action]
    assert all(np.array_equal(entry["grid"], original[name])
               for name, entry in maps.items())
    command = ["rtk", "proxy", "/usr/bin/python3", "-B", str(Path(__file__).resolve()),
               "--workspace", str(workspace), "--freeze", args.freeze,
               "--output", str(args.output.resolve())]
    result = {
        "schema": "mr3-p2a-synthetic-frontier-source-counterexample-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Synthetic pure-CPU source counterexample, not native evidence or a production repair.",
        "actual_w0_cause_proven": False,
        "actual_w0_caveat": "Reported actual w0/tb2 reachable_target_cells=0 is an upstream fused/own safe-target intersection issue; this fixture has33 targets and isolates the later frontier-only restriction.",
        "production_behavior_changed": False,
        "simulator_or_native_jobs": 0, "gpu_calls": 0,
        "input_origin": "Fully synthetic occupancy and three fixed synthetic delivered-state/map entries; no actual or truth-derived input.",
        "robot_count": 3,
        "fixed_robot_xy": {robot["name"]: [robot["x"], robot["y"]] for robot in robots},
        "source_freeze": args.freeze, "source_proof": proof,
        "script_sha256": sha(Path(__file__).read_bytes()),
        "exact_command": shlex.join(command),
        "versions": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__},
        "candidate_rule": snap["candidate_rule"],
        "robot_seed_traversable": diagnostic["robot_seed_traversable"],
        "tb2_seed_clearance_m": provenance["tb2"]["seed_pose_clearance_lower_bound_m"],
        "per_robot_reachable_target_cells": diagnostic["per_robot_reachable_target_cells"],
        "per_robot_reachable_pool_counts": diagnostic["per_robot_reachable_pool_counts"],
        "per_robot_reachable_selected_counts": diagnostic["per_robot_reachable_selected_counts"],
        "tb2_legal_GOAL_count": sum(snap["per_robot_action_mask"][1][:8]),
        "tb2_staging_rejections": diagnostic["per_robot_staging_rejections"][1],
        "own_frontier_staging_example": {
            "target_xy": point, "target_grid_rc": target, "own_frontier_grid_rc": frontier,
            "fused_clearance_m": float(fused_clearance[target]),
            "own_clearance_m": float(own_clearance[target]),
            "own_path_m": float(paths[index, 1]),
            "distance_to_own_frontier_m": math.dist(target, frontier) * .1,
            "known_free_own_line": True, "joint_KEEP_GOAL_KEEP_legal": True,
            "joint_action": action,
            "actual_goal_submitted": False,
        },
        "received_maps_unchanged": True,
        "passed": True,
    }
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.output.open("x") as output:
        output.write(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
