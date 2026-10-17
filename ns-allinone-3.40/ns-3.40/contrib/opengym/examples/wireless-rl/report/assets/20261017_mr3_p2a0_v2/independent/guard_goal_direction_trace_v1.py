"""Conditional initial-goal directions over every real frozen motion-state phase."""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from collections import Counter

ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v2_reset"
FREEZE = "96c201e0e258bd0fe192fc03c6716fc694b7a9b7"
PREFIX = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/"
FROZEN_ROOT = Path("/tmp/mr3_p2a0_v2_guard_goal_direction_sources")
(FROZEN_ROOT / "multi_robot_exploration").mkdir(parents=True, exist_ok=True)
OUTPUT = Path("/tmp/mr3_p2a0_v2_guard_goal_direction_trace_v1.json")
assert not OUTPUT.exists()
inputs, sources = {}, {}
def read(path):
    raw = path.read_bytes()
    inputs[str(path)] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return raw
for name in ("__init__.py", "mr3_episode.py", "mr3_motion_safety.py"):
    raw = subprocess.check_output(["git", "show", FREEZE + ":" + PREFIX + name], cwd=ROOT)
    target = FROZEN_ROOT / "multi_robot_exploration" / name
    target.write_bytes(raw)
    read(target)
    sources[name] = {"freeze": FREEZE, "sha256": hashlib.sha256(raw).hexdigest()}
sys.path.insert(0, str(FROZEN_ROOT))
from multi_robot_exploration.mr3_motion_safety import guard_motion, valid_state

NAMES = ("tb1", "tb2", "tb3")
def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))
def cf(own, peers, now, epoch, candidate):
    own = copy.deepcopy(own)
    dx, dy = candidate["x"] - own["x"], candidate["y"] - own["y"]
    own["yaw"] = math.atan2(dy, dx)
    return guard_motion([.1, 0.], own, peers, now, epoch)
def angles(own, peers, candidate, decision):
    goal_dx, goal_dy = candidate["x"] - own["x"], candidate["y"] - own["y"]
    heading = math.atan2(goal_dy, goal_dx)
    return {"goal": [candidate["x"], candidate["y"]], "own_xy": [own["x"], own["y"]],
            "goal_vector": [goal_dx, goal_dy], "goal_heading_rad": heading,
            "own_actual_yaw_rad": own["yaw"], "own_actual_vw": [own["v"], own["w"]],
            "peer_geometry": [{"peer": check["peer"],
                "relative_position": [peers[check["peer"]]["x"] - own["x"], peers[check["peer"]]["y"] - own["y"]],
                "goal_to_peer_bearing_rad": wrap(math.atan2(peers[check["peer"]]["y"] - own["y"], peers[check["peer"]]["x"] - own["x"]) - heading),
                **check} for check in decision["near_peer_checks"]], "guard": decision}

results = []
for ep in sorted(RUN.glob("worker*/episode001*")):
    transitions = [json.loads(line) for line in read(ep / "transitions.jsonl").splitlines()]
    first = transitions[0]["snapshot"]
    end = transitions[-1]["snapshot"]["source_stamp"]
    now, epoch = first["source_stamp"], first["epoch"]
    candidates = first["candidates"]
    mask = first["joint_action_mask"]
    def order(action):
        digits = (action // 100, action // 10 % 10, action % 10)
        return (-sum(d < 8 for d in digits), sum(candidates[d]["path_distances_m"][i] or 0. for i, d in enumerate(digits) if d < 8), action)
    action = min((a for a, allowed in enumerate(mask) if allowed), key=order)
    digits = (action // 100, action // 10 % 10, action % 10)
    robots = {}
    temporal = []
    for i, name in enumerate(NAMES):
        legal = sorted({(a // (100, 10, 1)[i]) % 10 for a, allowed in enumerate(mask) if allowed and (a // (100, 10, 1)[i]) % 10 < 8})
        own = first["robots"][i]
        peers = {n: first["robots"][j] for j, n in enumerate(NAMES) if n != name}
        decision = cf(own, peers, now, epoch, candidates[digits[i]])
        robots[name] = {"initial_joint_legal_goal_indices": legal, "minimum_path_selected_index": digits[i],
            "snapshot_source_age_six_point_geometry": angles(own, peers, candidates[digits[i]], decision),
            "first_actual_motion_phase": None,
            "candidate_actual_phase_summary": {str(k): {"phases": 0, "valid_state_phases": 0, "clear_phases": 0, "reasons": Counter(), "first_clear": None} for k in range(8) if candidates[k]["valid"]}}
    path = ep / "motion_safety.jsonl"
    digest = hashlib.sha256(); size = 0
    with path.open("rb") as stream:
        for raw in stream:
            digest.update(raw); size += len(raw)
            row = json.loads(raw)
            if row["kind"] != "decision":
                continue
            payload = row["payload"]
            stamp = payload["clock_ns"] / 1e9
            if not payload["started"] or not now <= stamp <= end:
                continue
            name = payload["robot"]
            own, peers = payload["own_state"], payload["received_peers"]
            valid = valid_state(own, stamp, epoch) and all(valid_state(p, stamp, epoch) for p in peers.values())
            phase = {"clock_ns": payload["clock_ns"], "robot": name,
                "own_source_age_sec": stamp - own["source_stamp"],
                "peer_source_ages_sec": {n: stamp - p["source_stamp"] for n, p in peers.items()},
                "actual_own_yaw_vw": [own["yaw"], own["v"], own["w"]], "candidate_checks": []}
            for key, summary in robots[name]["candidate_actual_phase_summary"].items():
                k = int(key)
                check = cf(own, peers, stamp, epoch, candidates[k])
                summary["phases"] += 1
                summary["valid_state_phases"] += bool(valid)
                summary["clear_phases"] += check["allow"]
                summary["reasons"][check["reason"]] += 1
                if check["allow"] and summary["first_clear"] is None:
                    summary["first_clear"] = {"clock_ns": payload["clock_ns"],
                        "own_state": own, "received_peers": peers,
                        **angles(own, peers, candidates[k], check)}
                phase["candidate_checks"].append({"index": k,
                    "initial_joint_legal": k in robots[name]["initial_joint_legal_goal_indices"],
                    "allow": check["allow"], "reason": check["reason"],
                    "minimum_margin_m": check["minimum_margin_m"]})
            if robots[name]["first_actual_motion_phase"] is None:
                selected = robots[name]["minimum_path_selected_index"]
                check = cf(own, peers, stamp, epoch, candidates[selected])
                robots[name]["first_actual_motion_phase"] = {"clock_ns": payload["clock_ns"],
                    "own_state": own, "received_peers": peers, **angles(own, peers, candidates[selected], check)}
            temporal.append(phase)
    inputs[str(path)] = {"sha256": digest.hexdigest(), "bytes": size}
    results.append({"episode": str(ep), "initial_snapshot_digest": first["digest"], "minimum_sum_path_joint_action": action,
                    "robots": robots, "all_actual_motion_phase_goal_direction_checks": temporal})
for path, proof in inputs.items():
    raw = Path(path).read_bytes()
    assert len(raw) == proof["bytes"] and hashlib.sha256(raw).hexdigest() == proof["sha256"]
result = {"schema": "mr3-p2a0-v2-actual-motion-phase-goal-heading-counterfactual-v1", "passed": True,
    "freeze": FREEZE, "source_proof": sources, "inputs": inputs, "episodes": results,
    "scope": "Every actual phase's own position, measured v/w, source ages and received peers retained; only own yaw counterfactually aligned toward initial candidate.",
    "limits": ["No Nav2 trajectory or movement proof; no candidate/map/policy change.", "Initial candidates stay fixed while later received positions/timestamps are actual trace values.", "v2 received actor odometry is missing; this cannot supply that failed gate."]}
OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"output": str(OUTPUT), "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), "episodes": [{"episode": ep["episode"], "action": ep["minimum_sum_path_joint_action"], "actual_phase_rows": len(ep["all_actual_motion_phase_goal_direction_checks"]), "robots": {name: {"initial_joint_legal_goal_indices": r["initial_joint_legal_goal_indices"], "minpath_choice": r["minimum_path_selected_index"], "first_actual_phase_minpath_allow": r["first_actual_motion_phase"]["guard"]["allow"], "each_candidate_clear_phases": {k: s["clear_phases"] for k, s in r["candidate_actual_phase_summary"].items()}, "each_candidate_total_phases": {k: s["phases"] for k, s in r["candidate_actual_phase_summary"].items()}} for name, r in ep["robots"].items()}} for ep in results]}, indent=2))
