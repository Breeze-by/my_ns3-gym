"""CPU audit of closed V6 round0 only; execute only after root notification."""

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from mr3_learning.observation import encode_snapshot


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = Path(__file__).resolve().parent
OUTPUT = RUN / "round0000_learning_review_v6.json"
CAPTURE = RUN / "round0000_learning_review_v6_inputs"
FREEZE = "af37b2aaa3cb9980434f7f16c1f52dec2506319d"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ROS = "ros2_ws/ros2-multi-robot-automap/"
assert not OUTPUT.exists() and not CAPTURE.exists(), "prior receipts remain immutable"
torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)
assert not torch.cuda.is_initialized()
artifacts = {}


def read(path, mutable=False):
    payload = path.read_bytes()
    artifacts[str(path.relative_to(RUN))] = {
        "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
        "scope": "exact mutable snapshot read" if mutable else "closed-round immutable artifact"}
    return payload


def load(path, mutable=False):
    return json.loads(read(path, mutable))


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def stats(values):
    values = np.asarray(values, np.float64).reshape(-1)
    return {"count": len(values), "min": float(values.min()), "max": float(values.max()),
            "mean": float(values.mean())} if len(values) else {"count": 0}


def group(name):
    return ("actor_head" if name.startswith("action_net.") else
            "critic_head" if name.startswith("value_net.") else "shared_encoder")


meta = load(RUN / "metadata.json")
summary_payload = read(RUN / "summary.json", mutable=True)
summary = json.loads(summary_payload)
assert meta["freeze"] == summary["freeze"] == FREEZE
assert meta["gamma_per_second"] == meta["lambda_per_second"] == 1.
round_summary = [row for row in summary["rounds"] if row["round"] == 0]
assert len(round_summary) == 1, "round0 optimization has not been saved yet"
round_summary = round_summary[0]
listed = sorted([row for row in summary["episodes"] if "/round0000/" in row["directory"]],
                key=lambda row: row["worker_id"])
assert len(listed) == 4 and [row["worker_id"] for row in listed] == [0, 1, 2, 3]
assert all(row["terminated"] or row["truncated"] for row in listed)
assert (RUN / "checkpoint_0000.zip").is_file() and (RUN / "rollout_0000.npz").is_file()
CAPTURE.mkdir()
with (CAPTURE / "summary_read_snapshot.json").open("xb") as target:
    target.write(summary_payload)
source_proof = {}
for relative in [WIRELESS + "mr3_learning/" + name for name in (
        "ppo.py", "rollout.py", "policy.py", "model.py", "observation.py")] + [
        ROS + "scripts/mr3_env_worker.py", ROS + "src/multi_robot_exploration/"
        "multi_robot_exploration/mr3_episode.py"]:
    frozen = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=ROOT)
    assert (ROOT / relative).read_bytes() == frozen
    source_proof[relative] = {"git_source": FREEZE + ":" + relative, "sha256": sha(frozen)}
episode_module = ROOT / ROS / "src/multi_robot_exploration/" / (
    "multi_robot_exploration/mr3_episode.py")
failure_reasons = runpy.run_path(str(episode_module))["TASK_FAILURE_REASONS"]
read(RUN / "initial.zip")
read(RUN / "checkpoint_0000.zip")
old = MaskablePPO.load(RUN / "initial.zip", device="cpu")
new = MaskablePPO.load(RUN / "checkpoint_0000.zip", device="cpu")
for model in (old, new):
    assert model.device.type == "cpu" and model.gamma == model.gae_lambda == 1.
    model.policy.set_training_mode(False)
    assert all(torch.isfinite(value).all() for value in model.policy.state_dict().values())
assert artifacts["initial.zip"]["sha256"] == summary["initial_checkpoint_sha256"]
assert not old.policy.optimizer.state, "initial collecting policy already has optimizer state"
old_parameters = dict(old.policy.named_parameters())
new_parameters = dict(new.policy.named_parameters())
assert old_parameters.keys() == new_parameters.keys()
parameter_rows, grouped = [], defaultdict(list)
for name, parameter in old_parameters.items():
    after = new_parameters[name]
    difference = (after.detach() - parameter.detach()).double()
    state = new.policy.optimizer.state[after]
    assert all(not torch.is_tensor(value) or torch.isfinite(value).all()
               for value in state.values())
    row = {"name": name, "group": group(name), "elements": difference.numel(),
           "changed_elements": int(difference.count_nonzero()),
           "delta_l2": float(difference.norm()), "delta_max_abs": float(difference.abs().max()),
           "adam_step": int(state["step"].item()),
           "adam_exp_avg_l2": float(state["exp_avg"].double().norm())}
    parameter_rows.append(row)
    grouped[row["group"]].append(row)
parameter_groups = {}
for name, rows in grouped.items():
    parameter_groups[name] = {
        "unique_tensors": len(rows),
        "changed_tensors": sum(row["changed_elements"] > 0 for row in rows),
        "delta_l2": sum(row["delta_l2"] ** 2 for row in rows) ** .5,
        "adam_exp_avg_l2": sum(row["adam_exp_avg_l2"] ** 2 for row in rows) ** .5,
        "actual_adam_steps": sorted({row["adam_step"] for row in rows})}
    assert parameter_groups[name]["changed_tensors"] > 0
    assert parameter_groups[name]["delta_l2"] > 1e-10
    assert parameter_groups[name]["adam_exp_avg_l2"] > 0
with np.load(io.BytesIO(read(RUN / "rollout_0000.npz")), allow_pickle=False) as archive:
    data = {key: archive[key] for key in archive.files}
assert all(np.isfinite(value).all() for value in data.values())
rowmeta = load(RUN / "rollout_0000.json")
count = len(rowmeta)
assert count == round_summary["decisions"] == new.num_timesteps
observations = {key[4:]: value[:, 0] for key, value in data.items() if key.startswith("obs_")}
actions, masks = data["actions"].reshape(-1).astype(np.int64), data["masks"][:, 0].astype(bool)
assert np.array_equal(masks, observations["action_mask"].astype(bool))
assert masks[np.arange(count), actions].all()
codes = np.stack((np.arange(1000) // 100, np.arange(1000) // 10 % 10,
                  np.arange(1000) % 10), axis=1)
selected = codes[actions]
opportunities = np.stack([np.stack([masks[:, codes[:, robot] == choice].any(axis=1)
                                   for choice in range(8)], axis=1).sum(axis=1)
                          for robot in range(3)], axis=1)
pre_values, pre_logs, pre_probs, post_probs, post_head_only_probs = [], [], [], [], []
with torch.no_grad():
    for start in range(0, count, 16):
        stop = min(count, start + 16)
        tensors, _ = old.policy.obs_to_tensor({key: value[start:stop]
                                              for key, value in observations.items()})
        action_tensor = torch.as_tensor(actions[start:stop])
        values, logs, _ = old.policy.evaluate_actions(
            tensors, action_tensor, action_masks=masks[start:stop])
        features = old.policy.extract_features(tensors)
        pre_values.extend(values.flatten().numpy())
        pre_logs.extend(logs.numpy())
        pre_probs.extend(old.policy.get_distribution(
            tensors, action_masks=masks[start:stop]).distribution.probs.numpy())
        post_probs.extend(new.policy.get_distribution(
            tensors, action_masks=masks[start:stop]).distribution.probs.numpy())
        post_head_only_probs.extend(torch.softmax(new.policy.action_net(features).masked_fill(
            ~torch.as_tensor(masks[start:stop]), -1e8), dim=1).numpy())
pre_values, pre_logs = np.asarray(pre_values), np.asarray(pre_logs)
value_error = float(np.max(np.abs(pre_values - data["values"].reshape(-1))))
log_error = float(np.max(np.abs(pre_logs - data["log_probs"].reshape(-1))))
assert np.allclose(pre_values, data["values"].reshape(-1), atol=2e-6, rtol=2e-6)
assert np.allclose(pre_logs, data["log_probs"].reshape(-1), atol=2e-6, rtol=2e-6)
full_tv = .5 * np.abs(np.asarray(post_probs) - np.asarray(pre_probs)).sum(axis=1)
head_tv = .5 * np.abs(np.asarray(post_head_only_probs) - np.asarray(pre_probs)).sum(axis=1)
cursor, workers = 0, []
for recorded in listed:
    directory = Path(recorded["directory"])
    native = [json.loads(line) for line in read(directory / "transitions.jsonl").splitlines()]
    worker_meta = load(directory / "metadata.json")
    shutdown = load(directory / "supervisor_shutdown.json")
    assert worker_meta["freeze"] == FREEZE
    assert shutdown["remaining_owned_processes"] == shutdown["remaining_owned_zombies"] == []
    assert shutdown["worker_returncode"] == 0 and not shutdown["forced_shutdown"]
    evaluator = load(directory / (recorded["epoch"] + ".json"))
    assert native[0]["kind"] == "reset" and native[-1]["terminated"] == recorded["terminated"]
    previous, episode = native[0]["snapshot"], []
    for returned in native[1:]:
        info = returned["info"]
        if info.get("action_submitted", True) is False:
            assert episode and info["command"] is None and returned["snapshot"] == previous
            assert info["dt"] == info["physical_dt"] == 0 and returned["terminated"]
            episode[-1].update(reward=episode[-1]["reward"] + returned["reward"],
                               terminated=True, truncated=False)
        else:
            command = info["command"]
            assert command["observation_digest"] == previous["digest"]
            assert command["observation_sequence"] == previous["sequence"]
            assert rowmeta[cursor]["observation_digest"] == previous["digest"]
            assert rowmeta[cursor]["observation_sequence"] == previous["sequence"]
            assert rowmeta[cursor]["epoch"] == recorded["epoch"] == info["epoch"]
            assert command["action"] == actions[cursor] == rowmeta[cursor]["action"]
            encoded = encode_snapshot(previous)
            assert all(np.array_equal(encoded[key], observations[key][cursor]) for key in encoded)
            episode.append({"index": cursor, "reward": returned["reward"], "dt": info["dt"],
                            "terminated": returned["terminated"],
                            "truncated": returned["truncated"],
                            "following": encode_snapshot(returned["snapshot"])})
            cursor += 1
        previous = returned["snapshot"]
    assert len(episode) == recorded["decisions"]
    indices = np.asarray([row["index"] for row in episode])
    for key in ("terminated", "truncated", "dt"):
        assert np.array_equal(data[key][indices], [row[key] for row in episode])
    native_rewards = np.asarray([row["reward"] for row in episode], np.float64)
    assert np.allclose(data["rewards"][indices, 0], native_rewards, atol=1e-6, rtol=1e-6)
    replay_next = []
    with torch.no_grad():
        for start in range(0, len(episode), 16):
            batch = episode[start:start + 16]
            tensors, _ = old.policy.obs_to_tensor({
                key: np.stack([row["following"][key] for row in batch])
                for key in observations})
            values = old.policy.predict_values(tensors).flatten().numpy()
            replay_next.extend(0. if row["terminated"] else float(value)
                               for row, value in zip(batch, values))
    next_error = float(np.max(np.abs(data["next_values"][indices] - replay_next)))
    assert np.allclose(data["next_values"][indices], replay_next, atol=2e-6, rtol=2e-6)
    tail = 0. if episode[-1]["terminated"] else float(data["next_values"][indices[-1]])
    # Direct MC suffix sums, not a restatement of the GAE recurrence.
    expected_returns = np.asarray([sum(native_rewards[start:]) + tail
                                   for start in range(len(episode))])
    return_error = float(np.max(np.abs(data["returns"][indices, 0] - expected_returns)))
    assert np.allclose(data["returns"][indices, 0], expected_returns, atol=3e-5, rtol=2e-6)
    reason = recorded["reason"]
    failure_bound_applies = bool(episode[-1]["terminated"] and reason in failure_reasons)
    failed_bound = None
    if failure_bound_applies:
        failed_bound = bool(expected_returns.max() <= -10. + 1e-8)
        assert failed_bound, "closed actual failure violated undiscounted -10 suffix bound"
    worker = {"worker": recorded["worker_id"], "epoch": recorded["epoch"],
              "all_samples_collected_before_round0_update": True,
              "decisions": len(episode), "api_records": len(native) - 1,
              "terminated": episode[-1]["terminated"], "truncated": episode[-1]["truncated"],
              "reason": reason, "one_tail_bootstrap": tail,
              "true_failure_bound_applicable": failure_bound_applies,
              "all_true_failure_suffix_returns_le_minus10": failed_bound,
              "native_reward_sum": float(native_rewards.sum()),
              "first_MC_target": float(expected_returns[0]),
              "return_target_range": stats(expected_returns),
              "MC_target_max_abs_error": return_error, "next_value_max_abs_error": next_error,
              "advantages": stats(data["advantages"][indices]),
              "forced_single_choice_rows": int((masks[indices].sum(axis=1) == 1).sum()),
              "per_robot_opportunities": [{
                  "robot": name,
                  "legal_GOAL_rows": int((opportunities[indices, robot] > 0).sum()),
                  "selected_GOAL_components": int((selected[indices, robot] < 8).sum())}
                  for robot, name in enumerate(("tb1", "tb2", "tb3"))],
              "native_task": {key: evaluator[key] for key in (
                  "success", "termination_reason", "correct_free_coverage_ratio",
                  "map_quality_pass", "robot_participation_pass", "collision_events",
                  "collision_monitoring_fresh", "navigation_protocol_closed")},
              "all_owned_shutdown_empty": True}
    workers.append(worker)
assert cursor == count
assert np.allclose(data["advantages"], data["returns"] - data["values"], atol=1e-6, rtol=1e-6)
actual_steps = sorted({row["adam_step"] for row in parameter_rows})
assert len(actual_steps) == 1 and actual_steps[0] > 0
expected_steps = new.n_epochs * ((count + new.batch_size - 1) // new.batch_size)
assert actual_steps == [expected_steps]
assert new._n_updates - old._n_updates == new.n_epochs
read(Path(__file__).resolve())
for relative, record in artifacts.items():
    if record["scope"] != "exact mutable snapshot read":
        assert sha((RUN / relative).read_bytes()) == record["sha256"]
assert not torch.cuda.is_initialized()
receipt = {
    "schema": "mr3-v6-round0000-closed-learning-review-v1", "passed": True,
    "utc_recorded": datetime.now(timezone.utc).isoformat(), "freeze": FREEZE,
    "scope": "Closed round0 only; all4 episodes sampled from initial.zip before any update",
    "source_proof": source_proof, "artifacts": artifacts, "round_summary": round_summary,
    "summary_snapshot": {"sha256": sha(summary_payload),
                         "closed_decisions_at_read": summary["decisions"],
                         "optimizer_steps_at_read": summary["optimizer_updates"],
                         "path": str(CAPTURE / "summary_read_snapshot.json")},
    "gamma": old.gamma, "gae_lambda": old.gae_lambda, "saved_actor_samples": count,
    "unique_parameter_rows": parameter_rows, "parameter_groups": parameter_groups,
    "actual_checkpoint_adam_steps": actual_steps,
    "expected_full_epoch_minibatch_steps": expected_steps,
    "checkpoint_SB3_epoch_updates": new._n_updates,
    "old_value_max_abs_error": value_error, "old_logprob_max_abs_error": log_error,
    "native_tensor_mask_action_bindings_exact": count,
    "fixed_old_features_new_actor_head_TV": stats(head_tv),
    "full_postupdate_policy_TV": stats(full_tv),
    "nontrivial_choice_head_only_TV": stats(head_tv[masks.sum(axis=1) > 1]),
    "workers": workers,
    "command_argv": ["rtk", "proxy", "env", "PYTHONNOUSERSITE=1", "CUDA_VISIBLE_DEVICES=",
                     sys.executable, "-c",
                     'import runpy,sys;runpy.run_path(sys.argv[1],run_name="__main__")',
                     str(Path(__file__).resolve())],
    "execution": {"device": "cpu", "cuda_initialized": False, "optimizer_calls": 0,
                  "native_or_ROS_jobs": 0, "signals": 0, "tracked_writes": 0},
    "limits": ["Round0 mechanics only; mutable run summary copied, no final-run completion claim.",
               "Initial-policy outcomes only; no postupdate native evaluation.",
               "Postupdate probability changes are offline diagnostics, not performance evidence.",
               "External truncation is distinct from terminal failure and bootstraps once.",
               "Frozen collector closes all4 environments before train; no optimizer replay here.",
               "Adam moments establish accumulated gradients; no per-minibatch gradient trace."]}
with OUTPUT.open("x") as target:
    target.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
print(json.dumps({"receipt": str(OUTPUT), "sha256": sha(OUTPUT.read_bytes()),
                  "passed": True, "actor_samples": count, "actual_adam_steps": actual_steps,
                  "parameter_groups": parameter_groups}, indent=2))
