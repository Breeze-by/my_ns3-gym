"""Bounded received-only prefix diagnosis; no truth, ROS node, policy or control."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = Path(__file__).resolve().parent
FREEZE = "af37b2aaa3cb9980434f7f16c1f52dec2506319d"
PACKAGE = ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration"
ROBOTS = ("tb1", "tb2", "tb3")


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode())


def write_exclusive(path, value):
    with path.open("x") as target:
        target.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def complete_prefix(path):
    lines = []
    with path.open("rb") as source:
        for _ in range(21):
            line = source.readline()
            if not line or not line.endswith(b"\n"):
                break
            lines.append(line)
    if len(lines) != 21:
        raise ValueError(f"WAIT_ROOT_NOTIFICATION: {path}: only {len(lines)} complete lines")
    return b"".join(lines)


def span(values):
    finite = [value for value in values if type(value) in (int, float) and math.isfinite(value)]
    return {"count": len(finite), "min": min(finite) if finite else None,
            "max": max(finite) if finite else None}


def zero_pool_reason(snapshot, robot):
    diagnostics, name = snapshot["diagnostics"], ROBOTS[robot]
    path = snapshot["path_maps"][name]
    frontier = diagnostics["frontier_cells"]
    target = diagnostics["per_robot_reachable_target_cells"][robot]
    noop = diagnostics["per_robot_arrival_noop_cells"][robot]
    rejected = diagnostics["per_robot_staging_rejections"][robot]
    if frontier == 0:
        return "no_fused_frontier; target counter may return before projection"
    if diagnostics["native_arrival_safe_cells"] == 0:
        return "no_fused_full_arrival_disk_safe_target_cells"
    if path["unavailable_reason"] is not None:
        return "own_map_or_seed_unavailable:" + path["unavailable_reason"]
    if path["seed_rejection_reason"] is not None:
        return "own_seed_rejected:" + path["seed_rejection_reason"]
    if target == 0:
        return ("all_pre_noop_targets_within_actual_arrival_tolerance" if noop else
                "own_path_and_fused_arrival_target_intersection_empty_before_frontier_staging")
    if rejected["beyond_staging_limit"] == frontier:
        return "reachable_targets_exist_but_all_fused_frontiers_beyond_1m_staging_limit"
    if rejected["beyond_staging_limit"] + rejected["occluded_staging_line"] == frontier:
        return "reachable_targets_exist_but_all_frontiers_fail_distance_or_known_free_line"
    return "saved_pool_zero; full_raw_grids_not_retained_for_further_attribution"


def travel(snapshots, robot):
    first, final = snapshots[0]["robots"][robot], snapshots[-1]["robots"][robot]
    lower, upper = round(first["source_stamp"] * 1e9), round(final["source_stamp"] * 1e9)
    positions = {}
    for snapshot in snapshots:
        state = snapshot["robots"][robot]
        records = list(state.get("history", [])) + [state]
        for point in records:
            stamp, x, y = point.get("source_stamp"), point.get("x"), point.get("y")
            if not all(type(value) in (int, float) and math.isfinite(value)
                       for value in (stamp, x, y)):
                continue
            ns = round(stamp * 1e9)
            if lower <= ns <= upper:
                positions.setdefault(ns, set()).add((x, y))
    ambiguous = [(ns, sorted(values)) for ns, values in sorted(positions.items())
                 if len(values) > 1]
    points = [(ns, next(iter(values))) for ns, values in sorted(positions.items())]
    legs = [math.dist(first[1], second[1]) for first, second in zip(points, points[1:])]
    received_positions = [(snapshot["robots"][robot]["x"], snapshot["robots"][robot]["y"])
                          for snapshot in snapshots]
    snapshot_legs = [math.dist(first, second)
                     for first, second in zip(received_positions, received_positions[1:])]
    return {"scope": "Delivered estimated XY at21 actor snapshots in frozen observation order",
            "snapshot_position_polyline_m": sum(snapshot_legs),
            "snapshot_max_leg_m": max(snapshot_legs, default=0.),
            "net_displacement_m": math.dist(received_positions[0], received_positions[-1]),
            "unique_source_positions": sum(len(values) for values in positions.values()),
            "source_start_ns": lower, "source_end_ns": upper,
            "history_polyline_m": sum(legs) if not ambiguous else None,
            "history_conservative_stamp_with_multiple_positions_count": len(ambiguous),
            "history_ambiguous_stamp_examples": ambiguous[:3],
            "history_limit": "No history-only distance if one source watermark binds multiple XY",
            "isolated_task_participation_gate_inferred": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-captured", action="store_true")
    parser.add_argument("--output", type=Path,
                        default=RUN / "prefix20_controllability_review_v6.json")
    args = parser.parse_args()
    assert not args.output.exists(), "prior receipt must not be overwritten"
    captured = RUN / "prefix20_controllability_captured_v6"
    metadata_payload = (RUN / "metadata.json").read_bytes()
    assert json.loads(metadata_payload)["freeze"] == FREEZE
    proof = {}
    for filename in ("mr3_observation.py", "mr3_episode.py"):
        source = PACKAGE / "multi_robot_exploration" / filename
        relative = str(source.relative_to(ROOT))
        frozen = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=ROOT)
        assert source.read_bytes() == frozen
        proof[relative] = {"sha256": sha(frozen), "git_source": FREEZE + ":" + relative}
    sys.path.insert(0, str(PACKAGE))
    from multi_robot_exploration.mr3_observation import _action_masks, snapshot_digest
    assert "rclpy" not in sys.modules and "torch" not in sys.modules
    prefixes = []
    if args.replay_captured:
        bindings = json.loads((captured / "prefix_manifest.json").read_text())
        for binding in bindings:
            payload = (captured / binding["capture_file"]).read_bytes()
            assert len(payload) == binding["prefix_bytes"] and sha(payload) == binding["sha256"]
            prefixes.append((binding, payload))
    else:
        files = sorted((RUN / "native/round0000").glob("worker*/episode*/transitions.jsonl"))
        assert len(files) == 4, "all four existing workers are required"
        for path in files:
            payload = complete_prefix(path)
            worker = int(path.parent.parent.name.removeprefix("worker"))
            binding = {"worker": worker, "source_path": str(path), "start_offset": 0,
                       "end_offset_exclusive": len(payload), "prefix_bytes": len(payload),
                       "complete_newline_records": 21, "sha256": sha(payload),
                       "capture_file": f"worker{worker}_reset_plus20.jsonl"}
            prefixes.append((binding, payload))
        captured.mkdir()
        for binding, payload in prefixes:
            with (captured / binding["capture_file"]).open("xb") as target:
                target.write(payload)
        write_exclusive(captured / "prefix_manifest.json", [binding for binding, _ in prefixes])
    workers = []
    for binding, payload in prefixes:
        rows = [json.loads(line) for line in payload.splitlines()]
        assert rows[0]["kind"] == "reset" and all(row["kind"] == "step" for row in rows[1:])
        snapshots = [row["snapshot"] for row in rows]
        epoch = snapshots[0]["epoch"]
        for snapshot in snapshots:
            assert snapshot["epoch"] == epoch
            assert snapshot_digest(snapshot) == snapshot["digest"]
            keys = ("epoch", "map_version", "sequence", "candidate_rule",
                    "candidates", "path_maps")
            assert canonical({key: snapshot[key] for key in keys}) == snapshot["candidate_version"]
            per_robot, joint, reasons = _action_masks(
                snapshot["robots"], snapshot["candidates"], snapshot["source_stamp"])
            assert per_robot == snapshot["per_robot_action_mask"]
            assert joint == snapshot["joint_action_mask"]
            assert reasons == snapshot["diagnostics"]["mask_reasons"]
        decision_rows = []
        for previous, returned in zip(snapshots, rows[1:]):
            info = returned["info"]
            if info.get("action_submitted", True) is False:
                assert info["command"] is None and returned["terminated"]
                continue
            command = info["command"]
            assert command["observation_sequence"] == previous["sequence"]
            assert command["observation_digest"] == previous["digest"]
            action = command["action"]
            assert previous["joint_action_mask"][action] is True
            codes = [(index // 100, index // 10 % 10, index % 10)
                     for index, legal in enumerate(previous["joint_action_mask"]) if legal]
            chosen = (action // 100, action // 10 % 10, action % 10)
            decision_rows.append({
                "source_observation_sequence": previous["sequence"],
                "source_observation_digest": previous["digest"], "action": action,
                "sampled_components": list(chosen), "joint_legal_action_count": len(codes),
                "per_robot_legal_GOAL_components": [sorted({code[i] for code in codes
                                                            if code[i] < 8}) for i in range(3)],
            })
        robots = {}
        for index, name in enumerate(ROBOTS):
            paths = [snapshot["path_maps"][name] for snapshot in snapshots]
            states = [snapshot["robots"][index] for snapshot in snapshots]
            diagnostics = [snapshot["diagnostics"] for snapshot in snapshots]
            choices = [row["sampled_components"][index] for row in decision_rows]
            eligible = [row for row in decision_rows
                        if row["per_robot_legal_GOAL_components"][index]]
            declined = [row for row in eligible if row["sampled_components"][index] >= 8]
            zero = [row for row in decision_rows
                    if not row["per_robot_legal_GOAL_components"][index]]
            zero_causes, pool_causes, idle_declined = Counter(), Counter(), []
            by_sequence = {snapshot["sequence"]: snapshot for snapshot in snapshots}
            for row in zero:
                snapshot = by_sequence[row["source_observation_sequence"]]
                local = snapshot["per_robot_action_mask"][index][:8]
                if any(local):
                    zero_causes["all_local_GOAL_choices_removed_by_joint_target_conflicts"] += 1
                else:
                    reasons = snapshot["diagnostics"]["mask_reasons"]["per_robot"][index]
                    for reason in reasons:
                        zero_causes[reason] += 1
            for row in declined:
                if by_sequence[row["source_observation_sequence"]]["robots"][index][
                        "navigation"]["phase"] == "idle":
                    idle_declined.append(row["source_observation_sequence"])
            for snapshot in snapshots:
                if snapshot["diagnostics"]["per_robot_reachable_pool_counts"][index] == 0:
                    pool_causes[zero_pool_reason(snapshot, index)] += 1
            robots[name] = {
                "snapshots": 21, "submitted_decisions": len(choices),
                "own_map": {
                    "missing_snapshots": sum(path["missing"] for path in paths),
                    "unavailable_reason_counts": dict(Counter(
                        str(path["unavailable_reason"]) for path in paths)),
                    "seed_rejection_counts": dict(Counter(
                        str(path["seed_rejection_reason"]) for path in paths)),
                    "seed_pose_clearance_lower_bound_m": span([
                        path["seed_pose_clearance_lower_bound_m"] for path in paths]),
                    "required_body_clearance_m": .29,
                    "source_age_sec": span([path["source_age_sec"] for path in paths]),
                    "received_age_sec": span([path["received_age_sec"] for path in paths]),
                    "unique_geometry_sha256": sorted({path["geometry_sha256"] for path in paths}),
                    "state_fresh_snapshots": sum(state["fresh"] for state in states),
                },
                "candidate_geometry": {
                    "target_cells": [d["per_robot_reachable_target_cells"][index]
                                     for d in diagnostics],
                    "pool_counts": [d["per_robot_reachable_pool_counts"][index]
                                    for d in diagnostics],
                    "selected_counts": [d["per_robot_reachable_selected_counts"][index]
                                        for d in diagnostics],
                    "arrival_noop_cells": [d["per_robot_arrival_noop_cells"][index]
                                           for d in diagnostics],
                    "pool_zero_saved_attribution_counts": dict(pool_causes),
                },
                "opportunities": {
                    "legal_GOAL_steps": len(eligible), "zero_legal_GOAL_steps": len(zero),
                    "selected_GOAL_components": sum(choice < 8 for choice in choices),
                    "selected_KEEP_components": choices.count(8),
                    "selected_WAIT_components": choices.count(9),
                    "legal_GOAL_but_selected_KEEP_or_WAIT_steps": len(declined),
                    "idle_legal_GOAL_but_selected_KEEP_or_WAIT_sequences": idle_declined,
                    "legal_GOAL_sequences": [row["source_observation_sequence"]
                                             for row in eligible],
                    "zero_legal_GOAL_sequences": [row["source_observation_sequence"]
                                                  for row in zero],
                    "zero_GOAL_mask_reason_counts": dict(zero_causes),
                },
                "delivered_state_travel": travel(snapshots, index),
                "navigation_phase_counts": dict(Counter(state["navigation"]["phase"]
                                                        for state in states)),
            }
        workers.append({"worker": binding["worker"], "epoch": epoch, "prefix": binding,
                        "first_actor_time": snapshots[0]["source_stamp"],
                        "last_actor_time": snapshots[-1]["source_stamp"],
                        "last_prefix_transition_terminated": rows[-1]["terminated"],
                        "last_prefix_transition_truncated": rows[-1]["truncated"],
                        "robots": robots, "submitted_action_evidence": decision_rows})
        if not args.replay_captured:
            with Path(binding["source_path"]).open("rb") as source:
                assert source.read(binding["prefix_bytes"]) == payload
    receipt = {
        "schema": "mr3-v6-pilot-fixed-prefix20-controllability-v1", "freeze": FREEZE,
        "utc_recorded": datetime.now(timezone.utc).isoformat(), "passed": True,
        "metadata_sha256": sha(metadata_payload), "source_proof": proof,
        "script_sha256": sha(Path(__file__).read_bytes()),
        "command_argv": ["rtk", "proxy", "env", "PYTHONNOUSERSITE=1",
                         "/usr/bin/python3", str(Path(__file__).resolve()), *sys.argv[1:]],
        "workers": workers, "snapshots_mask_replayed_exact": 84,
        "prefix_manifest_sha256": sha((captured / "prefix_manifest.json").read_bytes()),
        "native_prefixes_unchanged_after_read": not args.replay_captured,
        "whole_growing_transition_file_sha256_used": False,
        "jobs": {"ROS_nodes": 0, "native": 0, "GPU": 0, "optimizer": 0,
                 "signals": 0, "tracked_writes": 0},
        "limits": [
            "Only reset plus first20 complete transition lines per worker; no later trajectories.",
            "Geometry and opportunities use saved received-only actor data, never isolated truth.",
            "Pool causes are existing counters/source semantics; full raw maps/costmaps absent.",
            "No obstacle-identity, actual Nav2-costmap route, or repair claim.",
            "Travel uses delivered estimated states; no isolated participation certification.",
            "No complete outcome, learning benefit, intervention or plan change claim.",
            "All native originals and future rows retained; this binding is diagnostic only."]}
    assert "rclpy" not in sys.modules and "torch" not in sys.modules
    write_exclusive(args.output, receipt)
    print(json.dumps({"receipt": str(args.output), "sha256": sha(args.output.read_bytes()),
                      "passed": True, "workers": len(workers)}, indent=2))


if __name__ == "__main__":
    main()
