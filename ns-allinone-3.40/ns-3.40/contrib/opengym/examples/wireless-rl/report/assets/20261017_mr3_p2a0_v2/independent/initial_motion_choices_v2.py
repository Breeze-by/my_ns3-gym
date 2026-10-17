"""Frozen initial candidate/probe diagnostics; no native motion credit."""
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
RUN = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v2_reset"
FREEZE = "96c201e0e258bd0fe192fc03c6716fc694b7a9b7"
COMPONENT = ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration"
OUTPUT = Path("/tmp/mr3_p2a0_v2_initial_motion_choices_v2.json")
assert not OUTPUT.exists()
inputs, sources = {}, {}
FROZEN_ROOT = Path("/tmp/mr3_p2a0_v2_initial_motion_frozen_sources")
(FROZEN_ROOT / "multi_robot_exploration").mkdir(parents=True, exist_ok=True)
package_raw = subprocess.check_output(["git", "show", FREEZE + ":" + str((COMPONENT / "__init__.py").relative_to(ROOT))], cwd=ROOT)
(FROZEN_ROOT / "multi_robot_exploration/__init__.py").write_bytes(package_raw)

def read(path):
    raw = path.read_bytes()
    inputs[str(path)] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return raw

for name in ("mr3_observation.py", "mr3_episode.py", "mr3_motion_safety.py"):
    path = COMPONENT / name
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))], cwd=ROOT)
    frozen_path = FROZEN_ROOT / "multi_robot_exploration" / name
    frozen_path.write_bytes(frozen)
    assert frozen == read(frozen_path)
    sources[name] = {"sha256": hashlib.sha256(frozen).hexdigest(), "git_source": FREEZE + ":" + str(path.relative_to(ROOT)), "current_worktree_matches_native_freeze": path.read_bytes() == frozen}
sys.path.insert(0, str(FROZEN_ROOT))
from multi_robot_exploration import mr3_observation as m
from multi_robot_exploration.mr3_motion_safety import guard_motion

results = []
for episode in sorted(RUN.glob("worker*/episode001*")):
    snapshot = json.loads(read(episode / "transitions.jsonl").splitlines()[0])["snapshot"]
    assert m.snapshot_digest(snapshot) == snapshot["digest"]
    manifest = json.loads(read(episode / "observation_inputs/snapshots" / f"{snapshot['sequence']:08d}_{snapshot['digest']}.json"))
    def order(action, maximum=False):
        digits = m.decode_joint_action(action)
        distance = sum(snapshot["candidates"][digit]["path_distances_m"][index] or 0.
                       for index, digit in enumerate(digits) if digit < 8)
        return (-sum(digit < 8 for digit in digits), -distance if maximum else distance, action)
    legal = [action for action, valid in enumerate(snapshot["joint_action_mask"]) if valid]
    selected = min(legal, key=order)
    original = min(legal, key=lambda action: order(action, True))
    initial = {name: snapshot["robots"][index] for index, name in enumerate(m.ROBOT_NAMES)}
    alternatives = {}
    for mode, action in (("minimum_sum_path_motion_probe", selected), ("old_maximum_sum_path_stress", original)):
        diagnostics = {}
        for index, (name, digit) in enumerate(zip(m.ROBOT_NAMES, m.decode_joint_action(action))):
            assert digit < 8
            robot = initial[name]
            candidate = snapshot["candidates"][digit]
            dx, dy = candidate["x"] - robot["x"], candidate["y"] - robot["y"]
            heading = math.atan2(dy, dx)
            peer_states = {peer: initial[peer] for peer in m.ROBOT_NAMES if peer != name}
            aligned = copy.deepcopy(robot)
            aligned["yaw"] = heading
            decision = guard_motion([.1, 0.], aligned, peer_states, snapshot["source_stamp"], snapshot["epoch"])
            rotation = guard_motion([0., .5], robot, peer_states, snapshot["source_stamp"], snapshot["epoch"])
            role = manifest["maps"]["navigation:" + name]
            raw = gzip.decompress(read(episode / "observation_inputs" / role["artifact"]))
            assert hashlib.sha256(raw).hexdigest() == role["payload_sha256"]
            payload = json.loads(raw)
            info = payload["info"]
            grid = np.asarray(payload["data"], dtype=np.int16).reshape(info["height"], info["width"])
            origin = (info["origin"]["position"]["x"], info["origin"]["position"]["y"])
            resolution = info["resolution"]
            _, clearance = m.native_traversable(grid, resolution)
            length = math.hypot(dx, dy)
            count = max(1, math.ceil(length / (resolution / 4)))
            minimum_lower = math.inf
            for fraction in np.linspace(0., 1., count + 1):
                x, y = robot["x"] + fraction * dx, robot["y"] + fraction * dy
                row, column = m._cell(x, y, resolution, origin, grid.shape)
                centre_x = origin[0] + (column + .5) * resolution
                centre_y = origin[1] + (row + .5) * resolution
                minimum_lower = min(minimum_lower, clearance[row, column] - math.hypot(x - centre_x, y - centre_y))
            segment_lower = minimum_lower - length / count / 2
            diagnostics[name] = {
                "candidate_index": digit, "goal": [candidate["x"], candidate["y"]],
                "start": [robot["x"], robot["y"]], "delta": [dx, dy],
                "euclidean_distance_m": length, "saved_path_distance_m": candidate["path_distances_m"][index],
                "heading_rad": heading, "initial_yaw_rad": robot["yaw"],
                "heading_change_rad": math.atan2(math.sin(heading - robot["yaw"]), math.cos(heading - robot["yaw"])),
                "initial_dot_toward_each_peer_m2": {peer: dx * (state["x"] - robot["x"]) + dy * (state["y"] - robot["y"]) for peer, state in peer_states.items()},
                "aligned_heading_linear_request_mps": .1, "aligned_heading_guard_counterfactual": decision,
                "initial_pure_rotation_guard_counterfactual": rotation,
                "direct_segment_clearance_lower_bound_m": segment_lower,
                "direct_segment_body_clearance_certified": bool(segment_lower >= m.CLEARANCE_M),
                "navigation_payload_sha256": role["payload_sha256"],
                "native_execution_proven_by_this_counterfactual": False,
            }
        alternatives[mode] = {"joint_action": action, "digits": list(m.decode_joint_action(action)), "robots": diagnostics}
    results.append({"episode": str(episode), "snapshot_digest": snapshot["digest"], "sequence": snapshot["sequence"], "alternatives": alternatives})
for path, proof in inputs.items():
    raw = Path(path).read_bytes()
    assert len(raw) == proof["bytes"] and hashlib.sha256(raw).hexdigest() == proof["sha256"]
result = {"schema": "mr3-p2a0-v2-frozen-initial-motion-choice-counterfactual-v2", "passed": True,
          "freeze": FREEZE, "source_proof": sources, "inputs": inputs, "episodes": results,
          "scope": "External engineering script choice comparison only; production candidate/adapter unchanged.",
          "limits": ["Heading is counterfactually aligned; current Nav2 command/path or actual movement is not proved.", "The native delivered-odometry activity source was absent in this failed freeze; no >0.05m gate credit.", "Guard checks are conditional on frozen delivered states and declared bounds; this is not a complete trajectory guarantee."]}
OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"output": str(OUTPUT), "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), "episodes": [{"episode": item["episode"], "choices": {name: {"joint_action": value["joint_action"], "digits": value["digits"], "robots": {robot: {key: data[key] for key in ("delta", "euclidean_distance_m", "saved_path_distance_m", "heading_change_rad", "initial_dot_toward_each_peer_m2", "direct_segment_body_clearance_certified")} | {"aligned_guard_allow": data["aligned_heading_guard_counterfactual"]["allow"], "aligned_guard_reason": data["aligned_heading_guard_counterfactual"]["reason"], "rotation_allow": data["initial_pure_rotation_guard_counterfactual"]["allow"]} for robot, data in value["robots"].items()}} for name, value in item["alternatives"].items()}} for item in results]}, indent=2))
