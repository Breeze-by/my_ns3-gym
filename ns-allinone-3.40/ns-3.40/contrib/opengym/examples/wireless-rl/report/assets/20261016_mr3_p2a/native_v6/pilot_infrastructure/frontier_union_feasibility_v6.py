"""Detached frontier-source feasibility only; no native/ROS/policy/observer calls."""

import ast
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import FunctionType

import numpy as np
from scipy import ndimage


ROOT = Path("/home/zhuyulab/ns3-workspace")
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
RUN = Path(__file__).resolve().parent
V5 = RUN.parent / "mr3_p2a_v5_pilot"
CAPTURE = V5 / "raw_map_observer_round0002_w3_v1"
FREEZE = "af37b2aaa3cb9980434f7f16c1f52dec2506319d"
PROTOTYPE_VERSION = "mr3-per-robot-geometric-staging-v4-offline-prototype"
OUTPUT = RUN / "frontier_union_feasibility_v6.json"
ARTIFACTS = RUN / "frontier_union_feasibility_v6"
assert not OUTPUT.exists() and not ARTIFACTS.exists(), "preserve existing diagnostics"
ARTIFACTS.mkdir()
inputs = {}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    value = path.read_bytes()
    inputs[str(path.relative_to(ROOT))] = {"bytes": len(value), "sha256": sha(value)}
    return value


def load(path):
    return json.loads(read(path))


def write(path, value):
    with path.open("x") as target:
        target.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


component = ROS / "src/multi_robot_exploration/multi_robot_exploration"
source_proof = {}
for name in ("mr3_observation.py", "mr3_episode.py"):
    path = component / name
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + str(path.relative_to(ROOT))],
                                     cwd=ROOT)
    assert read(path) == frozen
    source_proof[str(path.relative_to(ROOT))] = {"sha256": sha(frozen), "freeze": FREEZE}
sys.path.insert(0, str(component.parent))
from multi_robot_exploration import mr3_observation as m  # noqa: E402
assert "rclpy" not in sys.modules and "torch" not in sys.modules


def frontiers(grid):
    return (grid == 0) & ndimage.binary_dilation(
        grid < 0, structure=ndimage.generate_binary_structure(2, 1))


def union_frontiers(raw, resolution, origin, robot_maps):
    union = frontiers(raw)
    contributions = {"fused": {"native_frontier_cells": int(union.sum())}}
    for name in m.ROBOT_NAMES:
        entry = robot_maps[name]
        own = np.argwhere(frontiers(entry["grid"]))
        points = np.column_stack((entry["origin"][0] + (own[:, 1] + .5) * entry["resolution"],
                                  entry["origin"][1] + (own[:, 0] + .5) * entry["resolution"]))
        columns = np.floor((points[:, 0] - origin[0]) / resolution).astype(int)
        rows = np.floor((points[:, 1] - origin[1]) / resolution).astype(int)
        inside = ((rows >= 0) & (rows < raw.shape[0])
                  & (columns >= 0) & (columns < raw.shape[1]))
        projected = sorted(set(zip(rows[inside].tolist(), columns[inside].tolist())))
        free = [cell for cell in projected if raw[cell] == 0]
        before = int(union.sum())
        for cell in free:
            union[cell] = True
        contributions[name] = {
            "own_frontier_cells": len(own), "projected_unique_inside_cells": len(projected),
            "projected_fused_observed_free_cells": len(free),
            "rejected_fused_unknown_or_occupied_cells": len(projected) - len(free),
            "new_union_cells": int(union.sum()) - before,
        }
    return union, contributions


def prototype_scope(union):
    tree = ast.parse((component / "mr3_observation.py").read_bytes())
    function = copy.deepcopy(next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                                  and node.name == "_candidates"))
    changed = 0
    for node in ast.walk(function):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "frontier"):
            node.value = ast.Call(func=ast.Attribute(value=ast.Name(
                id="_offline_frontier_union", ctx=ast.Load()), attr="copy", ctx=ast.Load()),
                args=[], keywords=[])
            changed += 1
    assert changed == 1
    ast.fix_missing_locations(function)
    namespace = dict(m.__dict__)
    namespace["_offline_frontier_union"] = union.copy()
    namespace["CANDIDATE_RULE_VERSION"] = PROTOTYPE_VERSION
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 "detached-frontier-union-only", "exec"), namespace)
    build = FunctionType(m.build_snapshot.__code__, namespace, "build_snapshot",
                         m.build_snapshot.__defaults__)
    build.__kwdefaults__ = copy.deepcopy(m.build_snapshot.__kwdefaults__)
    return namespace, build


def build_arguments(raw, resolution, origin, robots, now, epoch, map_version, sequence,
                    robot_maps, **kwargs):
    return ((raw, resolution, origin, robots, now, epoch, map_version, sequence),
            {"robot_maps": robot_maps, **kwargs})


def run_case(label, arguments, expected_old=None):
    positional, keywords = arguments
    raw, resolution, origin, _, _, _, _, _ = positional
    robot_maps = keywords["robot_maps"]
    before = {name: sha(entry["grid"].tobytes()) for name, entry in robot_maps.items()}
    old = m.build_snapshot(*positional, **keywords)
    if expected_old is not None:
        assert old == expected_old, "actual v5 snapshot must replay completely before prototype"
    union, contributions = union_frontiers(raw, resolution, origin, robot_maps)
    permuted = dict(reversed(list(robot_maps.items())))
    assert np.array_equal(union, union_frontiers(raw, resolution, origin, permuted)[0])
    scope, build = prototype_scope(union)
    new = build(*positional, **keywords)
    new["candidate_rule"].update(
        frontier_sources=["fused_received"] + ["received_own:" + name for name in m.ROBOT_NAMES],
        frontier_projection="world cell centre to containing fused native cell; free endpoints only")
    keys = ("epoch", "map_version", "sequence", "candidate_rule", "candidates", "path_maps")
    new["candidate_version"] = sha(canonical({key: new[key] for key in keys}))
    new["digest"] = m.snapshot_digest(new)
    changed_fields = {"candidate_rule", "candidate_version", "candidates", "per_robot_action_mask",
                      "joint_action_mask", "diagnostics", "digest"}
    assert all(old[key] == new[key] for key in old.keys() - changed_fields)
    assert old["path_maps"] == new["path_maps"]
    assert old["maps"] == new["maps"] and old["robots"] == new["robots"]
    assert len(old["candidates"]) == len(new["candidates"]) == 8
    per_robot, joint, _ = m._action_masks(new["robots"], new["candidates"], new["source_stamp"])
    assert per_robot == new["per_robot_action_mask"] and joint == new["joint_action_mask"]
    assert all(sha(entry["grid"].tobytes()) == before[name] for name, entry in robot_maps.items())
    changes = {}
    for index, name in enumerate(m.ROBOT_NAMES):
        def choices(snapshot):
            return sorted({m.decode_joint_action(action)[index]
                           for action, allowed in enumerate(snapshot["joint_action_mask"])
                           if allowed and m.decode_joint_action(action)[index] < 8})
        changes[name] = {
            "old_joint_legal_GOAL_choices": choices(old), "new_joint_legal_GOAL_choices": choices(new),
            "old_target_cells": old["diagnostics"]["per_robot_reachable_target_cells"][index],
            "new_target_cells": new["diagnostics"]["per_robot_reachable_target_cells"][index],
            "old_pool": old["diagnostics"]["per_robot_reachable_pool_counts"][index],
            "new_pool": new["diagnostics"]["per_robot_reachable_pool_counts"][index],
            "old_selected": old["diagnostics"]["per_robot_reachable_selected_counts"][index],
            "new_selected": new["diagnostics"]["per_robot_reachable_selected_counts"][index],
        }
        assert changes[name]["old_target_cells"] == changes[name]["new_target_cells"]
    for suffix, snapshot in (("old", old), ("prototype", new)):
        write(ARTIFACTS / f"{label}_{suffix}_snapshot.json", snapshot)
    # A zero own-path/arrival intersection cannot gain reachability from any frontier source.
    traversable, clearance = m.native_traversable(raw, resolution)
    targets = np.argwhere(traversable & (clearance >= m.TARGET_CLEARANCE_M))
    states = copy.deepcopy(new["robots"])
    paths, _, _ = m._own_map_paths(robot_maps, states, new["source_stamp"], new["epoch"],
                                  resolution, origin, targets)
    empty = paths.copy()
    empty[:, 0] = np.inf
    negative, diagnostic = scope["_candidates"](
        raw, clearance, targets, empty, resolution, origin, states)
    assert diagnostic["per_robot_reachable_target_cells"][0] == 0
    assert diagnostic["per_robot_reachable_pool_counts"][0] == 0
    assert all(not candidate["reachable"][0] for candidate in negative)
    changed_mask = [index for index, (a, b) in enumerate(zip(
        old["joint_action_mask"], new["joint_action_mask"])) if a != b]
    return {"label": label, "old_native_snapshot_exact_replayed": expected_old is not None,
            "old_digest": old["digest"], "prototype_digest": new["digest"],
            "old_candidate_version": old["candidate_version"],
            "prototype_candidate_version": new["candidate_version"],
            "union_contributions": contributions, "robot_changes": changes,
            "old_candidates": old["candidates"], "prototype_candidates": new["candidates"],
            "joint_mask_changed_action_indices": changed_mask,
            "old_joint_legal_actions": sum(old["joint_action_mask"]),
            "prototype_joint_legal_actions": sum(new["joint_action_mask"]),
            "target_paths_maps_states_rasters_unmodified": True,
            "zero_intersection_negative_control_passed": True,
            "dictionary_permutation_stable": True,
            "candidate_selection_code_change": "one frontier-mask assignment only; K8/reserve/FPS unchanged"}


# Reuse the exact old synthetic input, rather than adding a new native scenario.
prior_synthetic = load(V5 / "diagnostic_frontier_source_counterexample_v1.json")
assert prior_synthetic["passed"] and prior_synthetic["per_robot_reachable_target_cells"][1] == 33
fused = np.full((100, 100), -1, dtype=np.int8)
fused[5:95, 5:95] = 0
small = np.full_like(fused, -1)
small[43:57, 43:57] = 0
robots = [{"name": name, "x": x, "y": .05, "yaw": 0., "v": 0., "w": 0.,
           "valid": True, "source_stamp": 10., "received_stamp": 10.,
           "navigation": {"phase": "idle", "goal_id": None, "goal_x": None,
                          "goal_y": None, "commitment_until": 0.}}
          for name, x in zip(m.ROBOT_NAMES, (-3.05, .05, 3.05))]
maps = {name: {"grid": small.copy() if name == "tb2" else fused.copy(),
               "resolution": .1, "origin": (-5., -5.), "epoch": "counterexample",
               "source_stamp": 10., "received_stamp": 10.,
               "payload_sha256": "synthetic-delivered-" + name, "version": 1, "sequence": 1}
        for name in m.ROBOT_NAMES}
synthetic = run_case("same_v5_synthetic", build_arguments(
    fused, .1, (-5., -5.), robots, 10., "counterexample", 1, 1, maps))
assert synthetic["robot_changes"]["tb2"]["old_pool"] == 0
assert synthetic["robot_changes"]["tb2"]["new_pool"] > 0
assert synthetic["robot_changes"]["tb2"]["new_joint_legal_GOAL_choices"]

# The old raw capture is a different v5 state; never substitute it for V6 prefix inputs.
prior_forensic = load(V5 / "raw_map_forensics_round0002_w3_v1.json")
assert sha((V5 / "raw_map_forensics_round0002_w3_v1.json").read_bytes()) == (
    "e37893172139a6bb03bd11cbc697a29cc7519586f62f1b4b60c73dc0b5264058")
metadata = load(CAPTURE / "metadata.json")
events = [json.loads(line) for line in read(CAPTURE / "events.jsonl").splitlines()]
bundles = [event["payload"] for event in events if event["kind"] == "map_metadata"]
assert len(bundles) == 1
bundle = bundles[0]
actor_event = next(event for event in events if event["kind"] == "actor_snapshot"
                   and event["sequence"] == 81 and event["saved_line_proof"] is not None)
actor = json.loads(gzip.decompress(read(CAPTURE / actor_event["artifact"])))
assert actor["digest"] == "99ca848dae9f342c61ed4cd2e00a27ae54dc9a20865050cdd2579889d5d7e6cc"
assert actor["epoch"] == bundle["epoch"] == metadata["epoch"]
assert actor["map"]["sources"] == bundle["map_sources"]
proof = actor_event["saved_line_proof"]
with (Path(metadata["episode_directory"]) / "transitions.jsonl").open("rb") as source:
    source.seek(proof["complete_line_start_offset"])
    line = source.read(proof["complete_line_end_offset"] - proof["complete_line_start_offset"])
assert sha(line) == proof["line_sha256"] and json.loads(line)["snapshot"] == actor


def map_payload(digest):
    encoded = gzip.decompress(read(CAPTURE / "maps" / (digest + ".json.gz")))
    assert sha(encoded) == digest
    return json.loads(encoded)


def raw_grid(payload):
    info = payload["info"]
    return np.asarray(payload["data"], dtype=np.int16).reshape(info["height"], info["width"])


def origin(payload):
    return tuple(payload["info"]["origin"]["position"][key] for key in ("x", "y"))


fused = map_payload(bundle["map_payload_sha256"])
own = {name: map_payload(bundle["map_sources"][name]["payload_sha256"])
       for name in m.ROBOT_NAMES}
maps = {name: {"grid": raw_grid(own[name]), "resolution": own[name]["info"]["resolution"],
               "origin": origin(own[name]), "epoch": actor["epoch"], **bundle["map_sources"][name]}
        for name in m.ROBOT_NAMES}
robots = copy.deepcopy(actor["robots"])
for robot in robots:
    robot["navigation"]["sequence"] = robot["navigation"]["receipt_sequence"]
actual = run_case("old_v5_actor81", build_arguments(
    raw_grid(fused), fused["info"]["resolution"], origin(fused), robots,
    actor["source_stamp"], actor["epoch"], actor["map_version"], actor["sequence"], maps,
    map_source_stamp=bundle["map_source_stamp"], map_received_stamp=bundle["map_received_stamp"],
    map_sources=bundle["map_sources"], task_start=actor["source_stamp"] - actor["task_elapsed_sec"]),
    expected_old=actor)
assert actual["robot_changes"]["tb1"]["old_target_cells"] == 2
assert actual["robot_changes"]["tb1"]["old_pool"] == 0
assert actual["robot_changes"]["tb1"]["new_pool"] > 0
assert actual["robot_changes"]["tb1"]["new_joint_legal_GOAL_choices"]

prefix_manifest = load(RUN / "prefix20_controllability_captured_v6/prefix_manifest.json")
prefix_limits = []
for binding in prefix_manifest:
    payload = read(RUN / "prefix20_controllability_captured_v6" / binding["capture_file"])
    assert sha(payload) == binding["sha256"] and len(payload) == binding["prefix_bytes"]
    rows = [json.loads(line) for line in payload.splitlines()]
    assert len(rows) == 21
    for robot, name in enumerate(m.ROBOT_NAMES):
        positive, empty = [], []
        for row in rows:
            snapshot = row["snapshot"]
            diagnostics = snapshot["diagnostics"]
            if diagnostics["per_robot_reachable_pool_counts"][robot] != 0:
                continue
            evidence = {"sequence": snapshot["sequence"], "digest": snapshot["digest"],
                        "target_cells": diagnostics["per_robot_reachable_target_cells"][robot],
                        "frontier_cells": diagnostics["frontier_cells"],
                        "staging_rejections": diagnostics["per_robot_staging_rejections"][robot]}
            if evidence["target_cells"] > 0:
                positive.append(evidence)
            else:
                empty.append(evidence)
        if positive or empty:
            prefix_limits.append({"worker": binding["worker"], "robot": name,
                                  "target_positive_pool_zero": positive,
                                  "target_zero_pool_zero": empty,
                                  "new_actual_candidates_or_mask": None,
                                  "reason": "Full fused/own raw grids absent in V6 prefix; counterfactual underdetermined"})
read(Path(__file__).resolve())
receipt = {
    "schema": "mr3-offline-union-frontier-feasibility-v1", "passed": True,
    "utc_recorded": datetime.now(timezone.utc).isoformat(), "source_freeze": FREEZE,
    "source_proof": source_proof, "inputs": inputs,
    "command_argv": ["rtk", "proxy", "env", "PYTHONNOUSERSITE=1", "OMP_NUM_THREADS=1",
                     "OPENBLAS_NUM_THREADS=1", "/usr/bin/python3", "-B", str(Path(__file__))],
    "synthetic_same_v5_counterexample": synthetic, "exact_old_v5_actor81": actual,
    "v6_prefix20_exact_scope_limits": prefix_limits,
    "required_future_contract": {
        "version": "new explicit v4 candidate rule; offline prototype is not a production version",
        "must_bind_in_candidate_version": ["frontier source list", "common-frame projection rule",
                                           "existing physical/staging constants", "received map identities"],
        "candidate_sizes": [8, 3, 1000], "old_weights_or_validation_reused": False},
    "originals_unchanged": True, "native_ROS_GPU_observer_optimizer_jobs": 0,
    "tracked_edits": 0, "runtime_intervention": False,
    "limits": [
        "Old v5 actor81 has full raw-map binding; it is not a V6-prefix reconstruction.",
        "Only frontier sourcing changes; own body paths, fused arrival clearance and masks stay exact.",
        "Raw navigation start occupied100 does not establish actual layered-costmap blockage.",
        "No actual master costmap, Nav2 execution, physical obstacle identity or95% success proof.",
        "V6 targetintersection0 cannot be repaired by adding frontiers alone; no grid is invented.",
        "Current V6 run, validation/checkpoint choice and all future trajectories remain untouched."]}
for relative, proof in inputs.items():
    assert sha((ROOT / relative).read_bytes()) == proof["sha256"]
assert "rclpy" not in sys.modules and "torch" not in sys.modules
write(OUTPUT, receipt)
print(json.dumps({"receipt": str(OUTPUT), "sha256": sha(OUTPUT.read_bytes()),
                  "passed": True, "synthetic": synthetic["robot_changes"],
                  "old_v5_actor81": actual["robot_changes"]}, indent=2))
