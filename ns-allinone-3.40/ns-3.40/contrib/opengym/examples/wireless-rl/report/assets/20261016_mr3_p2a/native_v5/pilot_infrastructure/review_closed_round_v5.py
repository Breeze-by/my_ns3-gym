"""Offline review of one explicitly requested, fully closed v5 pilot round."""

import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from mr3_learning.audit_ppo import (
    audit_rollout, load_native_gates, native_decisions, parameter_changes, policy_replay,
)


ROOT = Path("/home/zhuyulab/ns3-workspace")
FREEZE = "de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3"
CANDIDATE_SHA = "d852bb68139701ce6c0364c9516285c0dbf70b82180efe478011e4d4faa6a178"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mask_scopes(directory):
    transitions = [json.loads(line) for line in
                   (directory / "transitions.jsonl").read_text().splitlines()]
    snapshots, actions = [], []
    previous = transitions[0]["snapshot"]
    for row in transitions[1:]:
        if row["info"].get("action_submitted", True):
            snapshots.append(previous)
            actions.append(row["info"]["command"]["action"])
        previous = row["snapshot"]
    result = {}
    for robot, name in enumerate(("tb1", "tb2", "tb3")):
        counts, selected, paths, chosen_paths = [], [], [], []
        forced_keep = idle_zero = 0
        for snapshot, action in zip(snapshots, actions):
            component = lambda a: (a // 100, a // 10 % 10, a % 10)[robot]
            choices = sorted({component(i) for i, allowed in
                              enumerate(snapshot["joint_action_mask"]) if allowed})
            goals = [i for i in choices if i < 8]
            counts.append(len(goals))
            choice = component(action)
            selected.append(choice)
            paths.extend(snapshot["candidates"][i]["path_distances_m"][robot]
                         for i in goals if
                         snapshot["candidates"][i]["path_distances_m"][robot] is not None)
            if choice < 8:
                chosen_paths.append(snapshot["candidates"][choice]["path_distances_m"][robot])
            forced_keep += choices == [8]
            idle_zero += (snapshot["robots"][robot]["navigation"]["phase"] == "idle"
                          and not goals)
        result[name] = {
            "saved_decisions": len(actions), "eligible_GOAL_steps": sum(x > 0 for x in counts),
            "max_legal_GOAL_choices": max(counts), "legal_GOAL_choice_count_sum": sum(counts),
            "selected_GOAL": sum(x < 8 for x in selected), "selected_KEEP": selected.count(8),
            "selected_WAIT": selected.count(9), "forced_KEEP_steps": forced_keep,
            "idle_no_legal_GOAL_steps": idle_zero,
            "max_legal_observed_path_m": max(paths) if paths else None,
            "selected_observed_path_range_m": [min(chosen_paths), max(chosen_paths)]
            if chosen_paths else None,
        }
    result["scope"] = ("Actual prior saved received-only snapshots and their joint masks; "
                       "path distances are observed estimates, not truth trajectories. "
                       "These counts do not establish counterfactual policy feasibility.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, required=True)
    args = parser.parse_args()
    index = args.round
    assert index >= 0
    directory = Path(__file__).resolve().parent
    output = directory / f"round{index:04d}_native_review_v5.json"
    assert not output.exists(), "choose an unreviewed round; prior review is immutable"
    metadata, summary = load(directory / "metadata.json"), load(directory / "summary.json")
    assert metadata["freeze"] == summary["freeze"] == FREEZE
    assert metadata["gamma_per_second"] == metadata["lambda_per_second"] == 1.
    declared = [row for row in summary["rounds"] if row["round"] == index]
    listed = sorted([row for row in summary["episodes"]
                     if f"/round{index:04d}/" in row["directory"]],
                    key=lambda row: row["episode_index"])
    assert len(declared) == 1 and len(listed) == 4
    for row in listed:
        native = Path(row["directory"])
        assert (native / "summary.json").exists() and (native / "supervisor_shutdown.json").exists()
    torch.set_num_threads(1)
    phase, base, auditor, command, scalar, source = load_native_gates(ROOT, FREEZE)
    helper_path = directory / "protocol_unsent_candidate_v2.py"
    assert sha(helper_path) == CANDIDATE_SHA
    spec = importlib.util.spec_from_file_location("protocol_unsent_candidate_v2", helper_path)
    candidate_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate_module)
    original_protocol = auditor.audit_protocol
    strict = candidate_module.ProtocolAuditor(original_protocol, ROOT, FREEZE)
    collecting = directory / (f"checkpoint_{index - 1:04d}.zip" if index else "initial.zip")
    model = MaskablePPO.load(collecting, device="cpu")
    assert model.gamma == model.gae_lambda == 1.
    result = {
        "schema": "mr3-p2a-closed-round-component-review-v5", "round": index,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_freeze": FREEZE, "source_entries": len(source), "source_proof": source,
        "collecting_checkpoint": str(collecting), "collecting_checkpoint_sha256": sha(collecting),
        "gamma": model.gamma, "lambda": model.gae_lambda, "cpu_torch_threads": 1,
        "episodes": [], "original_errors": [], "strict_candidate_errors": [],
        "candidate_v2_module_sha256": sha(helper_path), "review_driver_sha256": sha(Path(__file__)),
        "candidate_status": "Separate unintegrated offline candidate; original verdicts retained.",
    }
    flat, episodes = [], []
    for recorded in listed:
        native = Path(recorded["directory"])
        meta, native_summary = load(native / "metadata.json"), load(native / "summary.json")
        shutdown = load(native / "supervisor_shutdown.json")
        task = load(native / (meta["epoch"] + ".json"))
        contract = load(ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_p1a" /
                        (meta["scene"] + ".json"))
        row = {"worker_id": recorded["worker_id"], "episode_index": recorded["episode_index"],
               "epoch": meta["epoch"], "directory": str(native), "errors": []}
        row["native_original"] = phase.corrected_audit(base, auditor, command, [native])
        try:
            auditor.audit_protocol = strict
            row["native_strict_candidate_v2"] = phase.corrected_audit(
                base, auditor, command, [native])
        finally:
            auditor.audit_protocol = original_protocol
        row["scalar"] = scalar.audit_episode(native, FREEZE)
        decisions, api = native_decisions(native)
        assert len(decisions) == recorded["decisions"] and api == recorded["api_records"]
        assert np.isclose(sum(x["reward"] for x in decisions), recorded["reward_sum"])
        assert np.isclose(sum(x["dt"] for x in decisions), recorded["simulation_seconds"])
        row["collecting_policy"] = policy_replay(model, decisions, deterministic=False)
        row["task"] = {key: task[key] for key in (
            "success", "termination_reason", "correct_free_coverage_ratio", "map_quality_pass",
            "robot_participation_pass", "collision_events", "collision_monitoring_fresh",
            "navigation_protocol_closed", "elapsed_sim_time_sec", "time_to_95_coverage_sec")}
        quality = contract["quality"]
        row["quality_checks"] = {
            "observed_accuracy": {"actual": task["observed_accuracy"],
                                  "minimum": quality["min_observed_accuracy"],
                                  "passed": task["observed_accuracy"] >= quality["min_observed_accuracy"]},
            "occupied_iou": {"actual": task["occupied_iou"],
                             "minimum": quality["min_occupied_iou"],
                             "passed": task["occupied_iou"] >= quality["min_occupied_iou"]},
            "false_free_ratio": {"actual": task["false_free_ratio"],
                                 "maximum": quality["max_false_free_ratio"],
                                 "passed": task["false_free_ratio"] <= quality["max_false_free_ratio"]},
        }
        row["failed_quality_subgates"] = [key for key, check in row["quality_checks"].items()
                                          if not check["passed"]]
        assert task["map_quality_pass"] == (not row["failed_quality_subgates"])
        assert task["schema_version"] == 4 and task["robot_count"] == 3
        assert task["coverage_threshold"] == .95 and task["max_duration_sec"] == 300.
        if task["success"]:
            assert task["correct_free_coverage_ratio"] >= .95 and task["map_quality_pass"]
            assert task["robot_participation_pass"] and task["collision_events"] == 0
            assert task["collision_monitoring_fresh"] and task["navigation_protocol_closed"]
            assert task["elapsed_sim_time_sec"] < 300.
        checks = []
        for saved in shutdown["owned_processes_seen"]:
            current = None
            try:
                fields = (Path("/proc") / str(saved["pid"]) / "stat").read_text().rsplit(")", 1)[1].split()
                current = {"start_ticks": int(fields[19]), "state": fields[0]}
            except FileNotFoundError:
                pass
            absent = current is None or current["start_ticks"] != saved["start_ticks"]
            checks.append({"pid": saved["pid"], "saved_start_ticks": saved["start_ticks"],
                           "current": current, "saved_identity_absent": absent})
            if not absent:
                row["errors"].append("saved owned process remains: " + str(saved["pid"]))
        clean = (shutdown["worker_returncode"] == 0 and not shutdown["forced_shutdown"]
                 and not shutdown["failed_sample"] and not shutdown["remaining_owned_processes"]
                 and not shutdown["remaining_owned_zombies"] and native_summary["launch_returncode"] == 0
                 and not native_summary["native_failures"])
        if not clean:
            row["errors"].append("unclean native shutdown")
        row.update(decisions=len(decisions), api_records=api,
                   effective_seconds=sum(x["dt"] for x in decisions),
                   reward_sum=sum(x["reward"] for x in decisions), terminal_dt=decisions[-1]["dt"],
                   truth_evaluation_paths_m={k: v["path_length_m"] for k, v in task["robots"].items()},
                   truth_evaluation_goal_counts={k: v["nav_goal_count"] for k, v in task["robots"].items()},
                   mask_opportunities=mask_scopes(native), failure_details=native_summary["failures"],
                   shutdown={"clean": clean, "saved_identity_checks": checks,
                             "all_saved_identities_absent": all(x["saved_identity_absent"] for x in checks)})
        row["original_errors"] = row["errors"] + row["native_original"]["errors"] + row["scalar"]["errors"]
        row["strict_candidate_errors"] = (row["errors"] + row["native_strict_candidate_v2"]["errors"]
                                          + row["scalar"]["errors"])
        row["verified_original_task_success"] = bool(task["success"] and not row["original_errors"])
        row["verified_candidate_task_success"] = bool(task["success"] and not row["strict_candidate_errors"])
        row["files_sha256"] = {f.name: sha(f) for f in native.iterdir() if f.is_file()}
        for category in ("original_errors", "strict_candidate_errors"):
            result[category] += ["worker" + str(row["worker_id"]) + ": " + x for x in row[category]]
        result["episodes"].append(row)
        flat.extend(decisions)
        episodes.append(decisions)
        print(json.dumps({"worker": row["worker_id"], "original_errors": row["original_errors"],
                          "candidate_errors": row["strict_candidate_errors"], "task": row["task"],
                          "failed_quality_subgates": row["failed_quality_subgates"]}), flush=True)
    assert len(flat) == declared[0]["decisions"]
    rollout_path = directory / f"rollout_{index:04d}.npz"
    result["rollout"] = audit_rollout(rollout_path, flat, gamma=model.gamma, gae_lambda=model.gae_lambda)
    with np.load(rollout_path, allow_pickle=False) as archive:
        buffer = {key: archive[key] for key in archive.files}
    offset = 0
    for row, decisions in zip(result["episodes"], episodes):
        count = len(decisions)
        rewards = buffer["rewards"][offset:offset + count].reshape(-1).astype(float)
        targets = buffer["returns"][offset:offset + count].reshape(-1).astype(float)
        assert decisions[-1]["terminated"] and not decisions[-1]["truncated"]
        assert buffer["next_values"][offset + count - 1] == 0.
        expected = np.cumsum(rewards[::-1])[::-1]
        assert np.allclose(targets, expected, atol=1e-4, rtol=1e-5)
        if not row["task"]["success"]:
            assert row["reward_sum"] <= -10. and targets[0] <= -10. + 1e-4
        row["mc_targets"] = {"offset": offset, "rows": count, "true_terminal": True,
                             "terminal_bootstrap": 0., "first_return": float(targets[0]),
                             "first_expected_reward_sum": float(expected[0]),
                             "max_abs_error": float(np.max(np.abs(targets - expected)))}
        offset += count
    updated_path = directory / f"checkpoint_{index:04d}.zip"
    updated = MaskablePPO.load(updated_path, device="cpu")
    changed = parameter_changes(model, updated)
    assert updated.gamma == updated.gae_lambda == 1. and changed == declared[0]["changed_parameter_tensors"] > 0
    assert updated._n_updates > model._n_updates
    steps = sorted({float(value["step"].cpu().item()) for value in
                    updated.policy.optimizer.state.values() if "step" in value})
    result["post_update"] = {"checkpoint_sha256": sha(updated_path), "changed_parameter_tensors": changed,
                             "collecting_n_updates": model._n_updates, "updated_n_updates": updated._n_updates,
                             "optimizer_parameter_step_values": steps}
    result.update(decisions=len(flat), effective_seconds=sum(x["dt"] for x in flat),
                  original_passed=not result["original_errors"],
                  strict_candidate_passed=not result["strict_candidate_errors"],
                  original_verified_task_successes=sum(x["verified_original_task_success"]
                                                       for x in result["episodes"]),
                  candidate_verified_task_successes=sum(x["verified_candidate_task_success"]
                                                        for x in result["episodes"]),
                  candidate_receipts=strict.receipts)
    result["scope"] = ("Four fully closed episodes in this requested round only; pilot remains live. "
                       "CPU replay uses the actual pre-update checkpoint. Native/original verdicts remain "
                       "separate from unintegrated reviewed candidate. No full-run reliability/generalization "
                       "or established learned-improvement claim. No ROS/simulator/GPU/control calls.")
    with output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"artifact": str(output), "sha256": sha(output),
                      "original_passed": result["original_passed"], "original_errors": result["original_errors"],
                      "candidate_passed": result["strict_candidate_passed"],
                      "candidate_errors": result["strict_candidate_errors"], "decisions": len(flat),
                      "effective_seconds": result["effective_seconds"], "post_update": result["post_update"]}),
          flush=True)


if __name__ == "__main__":
    main()
