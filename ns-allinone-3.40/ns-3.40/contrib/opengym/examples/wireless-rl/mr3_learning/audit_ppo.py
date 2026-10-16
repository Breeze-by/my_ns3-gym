"""Offline P2A provenance, native-gate and collecting-policy audit.

No ROS or simulator is imported. Original P1C helpers remain immutable; this
wrapper pins their bytes and the accepted environment document separately.
Task failure remains a failure even when its measurement/provenance audit passes.
"""

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from .observation import encode_snapshot, observation_space


WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ENV_DOCUMENT_SHA256 = "fa39665fab65d2970e86a2654d047ada2ae5d3670fe644b7c06d5a1e3abb3beb"
PHASE_SHA256 = "4e2a24e3465fa45c06c05c37b57b8b77b6e462845b3227be10c1fecb85c2c7d7"
SCALAR_SHA256 = "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665"
POLICY_ATOL = 1e-4  # CPU replay of CUDA collecting inference; never a task tolerance.
POLICY_RTOL = 1e-5


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parameter_changes(before, after):
    left, right = before.policy.state_dict(), after.policy.state_dict()
    require(left.keys() == right.keys(), "checkpoint policy parameter names differ")
    return sum(not torch.equal(left[key], right[key]) for key in left)


def load_json(path):
    return json.loads(Path(path).read_text())


def load_rows(path):
    path = Path(path)
    if not path.exists():
        path = path.with_name(path.name + ".gz")
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
        return [json.loads(line) for line in source if line.strip()]


def load_pinned(name, path, digest):
    require(sha(path) == digest, "immutable offline helper changed: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_native_gates(root, freeze):
    directory = root / WIRELESS / "report/assets/20261015_mr3_p1c"
    phase = load_pinned("mr3_p2a_phase_v3", directory /
                        "audit_mr3_env_contact_phase_v3.py", PHASE_SHA256)
    # Only the delivery-status text changed. All original runtime pins and
    # the original v2 contact and v7 command-time implementations are retained.
    phase.PINNED_DOCUMENTS = {
        **phase.PINNED_DOCUMENTS,
        WIRELESS + "MR3_ENV_CONTRACT.md": ENV_DOCUMENT_SHA256}
    base, auditor, command, proof = phase.load_components(freeze, root)
    scalar = load_pinned("mr3_p2a_scalar_v3", directory / "reward_gate_audit_v3.py",
                         SCALAR_SHA256)
    require(sha(root / WIRELESS / "MR3_ENV_CONTRACT.md") == ENV_DOCUMENT_SHA256,
            "current accepted environment document differs from explicit P2A pin")
    for filename in ("ppo.py", "rollout.py", "policy.py", "model.py", "env.py",
                     "observation.py", "supervisor.py", "requirements-env.txt",
                     "requirements-ppo.txt"):
        relative = WIRELESS + "mr3_learning/" + filename
        blob = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        digest = hashlib.sha256(blob).hexdigest()
        require(digest == sha(root / relative), "learner worktree differs from freeze: " + filename)
        proof[relative] = {"sha256": digest, "git_source": freeze + ":" + relative}
    return phase, base, auditor, command, scalar, proof


def native_decisions(directory):
    """Reconstruct inputs and settlements from actual system-ROS receipts."""
    transitions = load_rows(directory / "transitions.jsonl")
    require(transitions and transitions[0]["kind"] == "reset", "native reset missing")
    previous = transitions[0]["snapshot"]
    decisions = []
    for row in transitions[1:]:
        require(row["kind"] == "step", "unexpected native transition kind")
        info = row["info"]
        if info.get("action_submitted", True) is False:
            require(decisions and row["terminated"] and not row["truncated"]
                    and info["dt"] == 0 and row["snapshot"] == previous,
                    "unproven no-action terminal settlement")
            decisions[-1].update(reward=decisions[-1]["reward"] + row["reward"],
                                 terminated=True, truncated=False)
        else:
            command = info["command"]
            require(command["observation_digest"] == previous["digest"]
                    and command["observation_sequence"] == previous["sequence"],
                    "submitted action not bound to preceding native snapshot")
            decisions.append({"observation": encode_snapshot(previous),
                              "following": encode_snapshot(row["snapshot"]),
                              "action": command["action"], "reward": row["reward"],
                              "dt": info["dt"], "terminated": row["terminated"],
                              "truncated": row["truncated"],
                              "snapshot_digest": previous["digest"]})
        previous = row["snapshot"]
    require(decisions and (decisions[-1]["terminated"] or decisions[-1]["truncated"]),
            "native decision episode is incomplete")
    return decisions, len(transitions) - 1


def policy_replay(model, decisions, *, deterministic):
    """Evaluate saved actions using the policy that actually collected them."""
    model.policy.set_training_mode(False)
    for start in range(0, len(decisions), 16):
        rows = decisions[start:start + 16]
        batch = {key: np.stack([row["observation"][key] for row in rows])
                 for key in observation_space().spaces}
        masks = batch["action_mask"].astype(bool)
        actions = np.asarray([row["action"] for row in rows], dtype=np.int64)
        require(np.all((actions >= 0) & (actions < 1000))
                and masks[np.arange(len(rows)), actions].all(),
                "native selected action violates its actual saved mask")
        with torch.no_grad():
            tensors, _ = model.policy.obs_to_tensor(batch)
            values, log_probs, _ = model.policy.evaluate_actions(
                tensors, torch.as_tensor(actions), action_masks=masks)
            if deterministic:
                predicted, _ = model.predict(batch, deterministic=True, action_masks=masks)
                require(np.array_equal(predicted, actions),
                        "evaluation action differs from frozen deterministic policy")
        for index, row in enumerate(rows):
            row["value"] = float(values[index].cpu().item())
            row["log_prob"] = float(log_probs[index].cpu().item())
            require(np.isfinite(row["value"]) and np.isfinite(row["log_prob"]),
                    "policy replay produced nonfinite outputs")
            if row["terminated"]:
                row["next_value"] = 0.
            else:
                with torch.no_grad():
                    following, _ = model.policy.obs_to_tensor(row["following"])
                    row["next_value"] = float(model.policy.predict_values(following).cpu().item())
    goal_components = sum(sum(choice < 8 for choice in (
        row["action"] // 100, row["action"] // 10 % 10, row["action"] % 10)) for row in decisions)
    return {"decisions": len(decisions), "legal_actions": len(decisions),
            "candidate_choice_components": goal_components,
            "deterministic_actions_verified": deterministic,
            "input_scope": "encode_snapshot of original preceding native snapshot only"}


def audit_rollout(path, decisions, *, gamma=.99, gae_lambda=.95):
    """Bind stored actor samples, masks, rewards and duration-aware GAE to native data."""
    with np.load(path, allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    count = len(decisions)
    require(count >= 1, "rollout needs a submitted decision")
    for key, array in data.items():
        require(np.isfinite(array).all(), "nonfinite rollout field: " + key)
    expected_keys = {"obs_" + key for key in observation_space().spaces} | {
        "actions", "masks", "rewards", "values", "log_probs", "advantages", "returns",
        "dt", "terminated", "truncated", "next_values"}
    require(set(data) == expected_keys, "rollout fields differ from declared actor/target contract")
    for key in observation_space().spaces:
        expected = np.stack([row["observation"][key] for row in decisions])[:, None]
        require(np.array_equal(data["obs_" + key], expected),
                "rollout tensor differs from native received snapshot: " + key)
    masks = data["masks"]
    require(np.array_equal(masks, data["obs_action_mask"])
            and np.isin(masks, (0, 1)).all(), "saved mask differs from actor observation mask")
    exact = {"actions": np.asarray([row["action"] for row in decisions])[:, None, None],
             "dt": np.asarray([row["dt"] for row in decisions]),
             "terminated": np.asarray([row["terminated"] for row in decisions]),
             "truncated": np.asarray([row["truncated"] for row in decisions])}
    for key, expected in exact.items():
        require(np.array_equal(data[key], expected), "native rollout mismatch: " + key)
    discrepancies = {}
    for key, field in (("rewards", "reward"), ("values", "value"),
                       ("log_probs", "log_prob"), ("next_values", "next_value")):
        expected = np.asarray([row[field] for row in decisions]).reshape(data[key].shape)
        require(np.allclose(data[key], expected, atol=POLICY_ATOL, rtol=POLICY_RTOL),
                "native/pre-update collecting-policy mismatch: " + key)
        discrepancies[key] = float(np.max(np.abs(data[key] - expected)))
    advantages = np.zeros(count)
    carry = 0.
    for index in reversed(range(count)):
        row = decisions[index]
        value = float(data["values"][index, 0])
        next_value = 0. if row["terminated"] else float(data["next_values"][index])
        discount = gamma ** row["dt"]
        delta = float(data["rewards"][index, 0]) + discount * next_value - value
        closed = row["terminated"] or row["truncated"]
        carry = delta + (0. if closed else discount * gae_lambda ** row["dt"] * carry)
        advantages[index] = carry
    require(np.allclose(data["advantages"].reshape(-1), advantages, atol=1e-4, rtol=1e-5),
            "duration-aware GAE/closed-episode recursion differs")
    require(np.allclose(data["returns"], data["advantages"] + data["values"],
                        atol=1e-5, rtol=1e-5), "returns do not equal saved advantages plus values")
    return {"path": str(path), "sha256": sha(path), "decisions": count,
            "all_fields_finite": True, "native_tensors_exact": True,
            "sampling_masks_exact": True, "duration_gae_verified": True,
            "pre_update_replay_max_abs_error": discrepancies,
            "policy_cpu_atol": POLICY_ATOL, "policy_cpu_rtol": POLICY_RTOL}


def audit_run(directory, freeze):
    directory = Path(directory).resolve()
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
    require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "exact source freeze required")
    metadata, summary = load_json(directory / "metadata.json"), load_json(directory / "summary.json")
    require(metadata["freeze"] == summary["freeze"] == freeze, "run source freeze mismatch")
    phase, base, native_auditor, command, scalar, proof = load_native_gates(root, freeze)
    result = {"schema": "mr3-p2a-ppo-offline-audit-v1", "directory": str(directory),
              "freeze": freeze, "mode": metadata["mode"], "errors": [], "episodes": [],
              "rounds": [], "source_proof": proof, "original_helpers_modified": False,
              "native_gates": "unchanged phase-v2 contact + phase-v3 command + scalar-v3",
              "helper_sha256": {"phase_v3": PHASE_SHA256, "scalar_v3": SCALAR_SHA256},
              "task_success_credit": "only original evaluator success with passed native gates"}

    def check(label, operation):
        try:
            return operation()
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as error:
            result["errors"].append(label + ": " + str(error))
            return None

    listed = {Path(row["directory"]).resolve(): row for row in summary["episodes"]}
    discovered = sorted(path.parent.resolve() for path in (directory / "native").glob(
        "round*/worker*/episode*/metadata.json"))
    check("native attempts", lambda: require(discovered and set(discovered) == set(listed),
          "every attempted native episode, including failures, must appear in summary"))
    rounds = {}
    for native in discovered:
        row = {"directory": str(native), "errors": []}
        try:
            native_meta = load_json(native / "metadata.json")
            epoch = native_meta["epoch"]
            row.update(epoch=epoch, scene=native_meta["scene"], seed=native_meta["seed"])
            row["native"] = phase.corrected_audit(base, native_auditor, command, [native])
            row["scalar"] = scalar.audit_episode(native, freeze)
            evaluation = load_json(native / (epoch + ".json"))
            row["task"] = {key: evaluation[key] for key in (
                "success", "termination_reason", "correct_free_coverage_ratio", "map_quality_pass",
                "robot_participation_pass", "collision_events", "collision_monitoring_fresh",
                "navigation_protocol_closed", "elapsed_sim_time_sec", "time_to_95_coverage_sec")}
            require(row["native"]["passed"], "original native gates: " +
                    "; ".join(row["native"]["errors"]))
            require(not row["scalar"]["errors"], "original scalar gates: " +
                    "; ".join(row["scalar"]["errors"]))
            require(evaluation["schema_version"] == 4 and evaluation["robot_count"] == 3
                    and evaluation["coverage_threshold"] == .95
                    and evaluation["max_duration_sec"] == 300., "task contract gate changed")
            if evaluation["success"]:
                require(evaluation["correct_free_coverage_ratio"] >= .95
                        and evaluation["map_quality_pass"] and evaluation["robot_participation_pass"]
                        and evaluation["collision_events"] == 0
                        and evaluation["collision_monitoring_fresh"]
                        and evaluation["navigation_protocol_closed"]
                        and evaluation["elapsed_sim_time_sec"] < 300.,
                        "claimed task success violates original task gates")
            decisions, api_count = native_decisions(native)
            recorded = listed[native]
            require(recorded["decisions"] == len(decisions) and recorded["api_records"] == api_count,
                    "run/native decision and API counts differ")
            require(np.isclose(recorded["reward_sum"], sum(x["reward"] for x in decisions))
                    and np.isclose(recorded["simulation_seconds"], sum(x["dt"] for x in decisions)),
                    "run/native reward or simulation-duration totals differ")
            round_id = int(native.parent.parent.name.removeprefix("round"))
            rounds.setdefault(round_id, []).append((recorded["episode_index"], decisions, row))
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as error:
            row["errors"].append(str(error))
            result["errors"].append(str(native) + ": " + str(error))
        result["episodes"].append(row)
    previous = directory / "initial.zip"
    check("initial checkpoint hash", lambda: require(
        sha(previous) == summary["initial_checkpoint_sha256"], "initial checkpoint hash differs"))
    for index, entries in sorted(rounds.items()):
        checkpoint = previous if metadata["mode"] == "train" else directory / "initial.zip"
        round_result = {"round": index, "collecting_checkpoint": str(checkpoint)}

        def replay_round():
            model = MaskablePPO.load(checkpoint, device="cpu")
            decisions = []
            for _, episode, episode_result in sorted(entries, key=lambda entry: entry[0]):
                episode_result["policy"] = policy_replay(
                    model, episode, deterministic=metadata["mode"] == "evaluate")
                decisions.extend(episode)
            round_result["collecting_checkpoint_sha256"] = sha(checkpoint)
            round_result["rollout"] = audit_rollout(
                directory / f"rollout_{index:04d}.npz", decisions,
                gamma=metadata["gamma_per_second"], gae_lambda=metadata["lambda_per_second"])
            if metadata["mode"] == "train" and len(decisions) >= 2:
                updated_path = directory / f"checkpoint_{index:04d}.zip"
                updated = MaskablePPO.load(updated_path, device="cpu")
                changed = parameter_changes(model, updated)
                declared = [row for row in summary["rounds"] if row["round"] == index]
                require(len(declared) == 1 and changed > 0
                        and declared[0]["changed_parameter_tensors"] == changed
                        and updated._n_updates > model._n_updates,
                        "post-update checkpoint lacks the declared real parameter/optimizer change")
                round_result.update(updated_checkpoint_sha256=sha(updated_path),
                                    changed_parameter_tensors=changed)
            return decisions
        check("round " + str(index), replay_round)
        if metadata["mode"] == "train" and (directory / f"checkpoint_{index:04d}.zip").exists():
            previous = directory / f"checkpoint_{index:04d}.zip"
        result["rounds"].append(round_result)
    check("completed run", lambda: require(summary["completed"] and summary["error"] is None
          and not summary["cleanup_errors"], "run has an error/incomplete native closure"))
    check("decision totals", lambda: require(summary["decisions"] == sum(
          row["decisions"] for row in summary["episodes"]) and summary["api_records"] == sum(
          row["api_records"] for row in summary["episodes"]), "summary count totals differ"))
    if metadata["mode"] == "train":
        check("optimizer evidence", lambda: require(summary["optimizer_updates"] > 0
              and summary["rounds"] and all(row["changed_parameter_tensors"] > 0
              and all((value is None and key == "train/explained_variance")
                      or (value is not None and np.isfinite(value))
                      for key, value in row["metrics"].items())
              for row in summary["rounds"]), "no finite real PPO optimizer update evidence"))
    else:
        check("evaluation schedule", lambda: require(
            len(summary["episodes"]) == len(metadata["schedule"])
            and all((row["scene"], row["seed"]) == tuple(task)
                    for row, task in zip(summary["episodes"], metadata["schedule"])),
            "evaluation did not retain the complete declared schedule"))
        check("evaluation optimizer", lambda: require(summary["optimizer_updates"] == 0,
                                                      "evaluation performed optimizer updates"))
        check("input checkpoint hash", lambda: require(sha(metadata["checkpoint"]) ==
              summary["input_checkpoint_sha256"], "frozen evaluation checkpoint changed"))
        check("evaluation frozen weights", lambda: require(
            parameter_changes(MaskablePPO.load(directory / "initial.zip", device="cpu"),
                              MaskablePPO.load(directory / "final.zip", device="cpu")) == 0
            and parameter_changes(MaskablePPO.load(directory / "initial.zip", device="cpu"),
                                  MaskablePPO.load(metadata["checkpoint"], device="cpu")) == 0,
            "evaluation weights differ from original frozen input checkpoint"))
    check("final checkpoint hash", lambda: require(sha(directory / "final.zip") ==
          summary["final_checkpoint_sha256"], "final checkpoint hash differs"))
    result["native_attempts"] = len(discovered)
    result["task_successes"] = sum(
        row.get("task", {}).get("success", False) and not row["errors"] for row in result["episodes"])
    result["task_failures"] = [{"epoch": row.get("epoch"), "task": row.get("task"),
                                "audit_errors": row["errors"]} for row in result["episodes"]
                               if row["errors"] or not row.get("task", {}).get("success", False)]
    result["passed"] = not result["errors"]
    result["scope"] = "pilot audit only; no statistical baseline superiority or network credit"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("audit output exists; choose a new path")
    torch.set_num_threads(1)
    result = audit_run(args.directory, args.freeze)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": result["passed"], "native_attempts": result["native_attempts"],
                      "task_successes": result["task_successes"], "errors": result["errors"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
