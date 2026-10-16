"""Independent closed V6 CPU review; never runs an optimizer, ROS or a simulator."""

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from mr3_learning.observation import encode_snapshot


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = Path(__file__).resolve().parent
OUTPUT = RUN / "independent_review_v6.json"
FREEZE = "af37b2aaa3cb9980434f7f16c1f52dec2506319d"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ROS = "ros2_ws/ros2-multi-robot-automap/"
assert not OUTPUT.exists(), "prior independent receipt must not be overwritten"
torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)
assert not torch.cuda.is_initialized()
manifest = {}
review = {"schema": "mr3-v6-minimal-independent-learning-review-v1", "passed": False,
          "freeze": FREEZE, "utc_recorded": datetime.now(timezone.utc).isoformat(),
          "command_argv": ["rtk", "proxy", "env", "PYTHONNOUSERSITE=1",
                           "CUDA_VISIBLE_DEVICES=", sys.executable, "-c",
                           "import runpy,sys;runpy.run_path(sys.argv[1],run_name='__main__')",
                           str(Path(__file__).resolve())],
          "artifact_manifest": manifest, "errors": []}


def read(path):
    value = path.read_bytes()
    manifest[str(path.relative_to(RUN))] = {
        "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    return value


def load(path):
    return json.loads(read(path))


def proc_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": int(fields[19]), "state": fields[0]}
    except FileNotFoundError:
        return None


def parameter_group(name):
    return ("actor_head" if name.startswith("action_net.") else
            "critic_head" if name.startswith("value_net.") else "shared_encoder")


def model(path):
    read(path)
    result = MaskablePPO.load(path, device="cpu")
    result.policy.set_training_mode(False)
    assert result.device.type == "cpu" and result.gamma == result.gae_lambda == 1.
    assert all(torch.isfinite(value).all() for value in result.policy.state_dict().values())
    return result


try:
    metadata, summary = load(RUN / "metadata.json"), load(RUN / "summary.json")
    assert metadata["freeze"] == summary["freeze"] == FREEZE
    assert summary.get("completed") is True and summary.get("error") is None, summary.get("error")
    assert summary["cleanup_errors"] == summary["native_accounting_errors"] == []
    assert metadata["gamma_per_second"] == metadata["lambda_per_second"] == 1.
    assert summary["decisions"] == summary["native_recorded_decisions"] == (
        summary["collector_observed_decisions"]) == 16
    assert (RUN / "final.zip").is_file()
    review["run_summary"] = {key: summary[key] for key in (
        "decisions", "api_records", "native_recorded_decisions", "optimizer_updates",
        "ppo_epochs", "stop_reason", "completed", "wall_sec_including_all_attempts")}
    sources = [
        WIRELESS + "mr3_learning/" + name for name in (
            "ppo.py", "rollout.py", "model.py", "policy.py", "observation.py", "env.py",
            "supervisor.py", "requirements-env.txt", "requirements-ppo.txt")]
    sources += [ROS + "scripts/mr3_env_worker.py"]
    sources += [ROS + "src/multi_robot_exploration/multi_robot_exploration/" + name
                for name in ("task_evaluator.py", "mr3_evaluator_phase.py", "mr3_episode.py",
                             "mr3_observation.py", "mr3_information.py", "mr3_adapter.py",
                             "mr3_protocol.py", "mr3_transport.py", "mr3_reward.py")]
    sources += [ROS + f"src/multi_robot/params/nav2_params_tb{i}_0.yaml" for i in (1, 2, 3)]
    proof = {}
    for relative in sources:
        frozen = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=ROOT)
        assert (ROOT / relative).read_bytes() == frozen, relative
        proof[relative] = {"sha256": hashlib.sha256(frozen).hexdigest(),
                           "git_source": FREEZE + ":" + relative,
                           "current_bytes_equal_frozen": True}
    review["source_proof"] = proof
    for path in sorted((RUN / "native").rglob("*")):
        if path.is_file():
            read(path)
    for name in ("resources.json", "progress.json", "sb3_metrics/progress.json"):
        if (RUN / name).exists():
            read(RUN / name)

    old = model(RUN / "initial.zip")
    assert manifest["initial.zip"]["sha256"] == summary["initial_checkpoint_sha256"]
    rounds, identities, native_count, archive_count = [], {}, 0, 0
    for declared in summary["rounds"]:
        index = declared["round"]
        native = [row for row in summary["episodes"]
                  if f"/round{index:04d}/" in row["directory"]]
        native.sort(key=lambda row: row["episode_index"])
        row_metadata = load(RUN / f"rollout_{index:04d}.json")
        with np.load(io.BytesIO(read(RUN / f"rollout_{index:04d}.npz")),
                     allow_pickle=False) as archive:
            saved = {key: archive[key] for key in archive.files}
        assert all(np.isfinite(array).all() for array in saved.values())
        sampled, episodes = [], []
        for recorded in native:
            directory = Path(recorded["directory"])
            worker_metadata = load(directory / "metadata.json")
            assert worker_metadata["freeze"] == FREEZE
            shutdown = load(directory / "supervisor_shutdown.json")
            assert shutdown["remaining_owned_processes"] == []
            assert shutdown["remaining_owned_zombies"] == []
            assert shutdown["worker_returncode"] == 0 and not shutdown["forced_shutdown"]
            for identity in shutdown["owned_processes_seen"]:
                identities[(identity["pid"], identity["start_ticks"])] = identity
            transitions = [json.loads(line) for line in read(
                directory / "transitions.jsonl").splitlines()]
            previous, episode = transitions[0]["snapshot"], []
            for returned in transitions[1:]:
                info = returned["info"]
                if info.get("action_submitted", True) is False:
                    assert episode and returned["snapshot"] == previous and info["dt"] == 0
                    assert returned["terminated"] and not returned["truncated"]
                    episode[-1].update(reward=episode[-1]["reward"] + returned["reward"],
                                       terminated=True, truncated=False)
                else:
                    command = info["command"]
                    assert command["observation_digest"] == previous["digest"]
                    assert command["observation_sequence"] == previous["sequence"]
                    episode.append({"observation": encode_snapshot(previous),
                                    "following": encode_snapshot(returned["snapshot"]),
                                    "action": command["action"], "reward": returned["reward"],
                                    "dt": info["dt"], "terminated": returned["terminated"],
                                    "truncated": returned["truncated"],
                                    "digest": previous["digest"]})
                previous = returned["snapshot"]
            assert len(episode) == recorded["decisions"]
            assert episode[-1]["terminated"] or episode[-1]["truncated"]
            episodes.append(episode)
            sampled.extend(episode)
            native_count += len(transitions) - 1

        count = len(sampled)
        archive_count += count
        assert count == declared["decisions"] == len(row_metadata)
        actions = np.asarray([row["action"] for row in sampled])
        masks = saved["masks"][:, 0].astype(bool)
        assert np.array_equal(saved["actions"].reshape(-1), actions)
        assert masks[np.arange(count), actions].all()
        for key in sampled[0]["observation"]:
            expected = np.stack([row["observation"][key] for row in sampled])[:, None]
            assert np.array_equal(saved["obs_" + key], expected), key
        assert np.array_equal(saved["masks"], saved["obs_action_mask"])
        assert [row["observation_digest"] for row in row_metadata] == [
            row["digest"] for row in sampled]
        for key in ("dt", "terminated", "truncated"):
            assert np.array_equal(saved[key], np.asarray([row[key] for row in sampled]))
        assert np.allclose(saved["rewards"].reshape(-1), [row["reward"] for row in sampled],
                           atol=1e-6, rtol=1e-6)
        replay_values, replay_logs, replay_next = [], [], []
        with torch.no_grad():
            for row in sampled:
                tensors, _ = old.policy.obs_to_tensor(row["observation"])
                values, logs, _ = old.policy.evaluate_actions(
                    tensors, torch.as_tensor([row["action"]]),
                    action_masks=row["observation"]["action_mask"].astype(bool)[None])
                following, _ = old.policy.obs_to_tensor(row["following"])
                replay_values.append(values.item())
                replay_logs.append(logs.item())
                replay_next.append(0. if row["terminated"] else old.policy.predict_values(
                    following).item())
        discrepancies = {}
        for key, expected in (("values", replay_values), ("log_probs", replay_logs),
                              ("next_values", replay_next)):
            actual = saved[key].reshape(-1)
            discrepancies[key] = float(np.max(np.abs(actual - expected)))
            assert np.allclose(actual, expected, atol=2e-6, rtol=2e-6), (key, discrepancies[key])
        expected_returns, bootstrap_rows = [], []
        offset = 0
        for episode in episodes:
            last = offset + len(episode) - 1
            tail = 0. if episode[-1]["terminated"] else float(saved["next_values"][last])
            # Independent closed-form suffix reward sums, one tail value per episode.
            rewards = [row["reward"] for row in episode]
            expected_returns.extend(sum(rewards[start:]) + tail for start in range(len(episode)))
            bootstrap_rows.append({"terminated": episode[-1]["terminated"],
                                   "truncated": episode[-1]["truncated"],
                                   "tail_value_added_once": tail, "decisions": len(episode)})
            offset = last + 1
        return_error = float(np.max(np.abs(saved["returns"].reshape(-1) - expected_returns)))
        assert np.allclose(saved["returns"].reshape(-1), expected_returns,
                           atol=1e-5, rtol=2e-6), return_error
        assert np.allclose(saved["advantages"], saved["returns"] - saved["values"],
                           atol=1e-6, rtol=1e-6)
        new = model(RUN / f"checkpoint_{index:04d}.zip")
        groups = {}
        for name, before in old.policy.named_parameters():
            after = dict(new.policy.named_parameters())[name]
            group = groups.setdefault(parameter_group(name), {
                "unique_tensors": 0, "changed_tensors": 0, "delta_l2_squared": 0.,
                "adam_exp_avg_l2_squared": 0., "adam_steps": set()})
            delta = (after.detach() - before.detach()).double()
            group["unique_tensors"] += 1
            group["changed_tensors"] += int(torch.count_nonzero(delta) > 0)
            group["delta_l2_squared"] += float(delta.square().sum())
            state = new.policy.optimizer.state[after]
            assert all(not torch.is_tensor(value) or torch.isfinite(value).all()
                       for value in state.values())
            group["adam_exp_avg_l2_squared"] += float(state["exp_avg"].double().square().sum())
            group["adam_steps"].add(int(state["step"].item()))
        for group in groups.values():
            group["delta_l2"] = group.pop("delta_l2_squared") ** .5
            group["adam_exp_avg_l2"] = group.pop("adam_exp_avg_l2_squared") ** .5
            group["adam_steps"] = sorted(group["adam_steps"])
            assert group["changed_tensors"] > 0 and group["delta_l2"] > 1e-10
            assert group["adam_exp_avg_l2"] > 0
        rounds.append({"round": index, "decisions": count, "parameter_groups": groups,
                       "mask_and_native_tensors_exact": True,
                       "preupdate_cpu_replay_max_abs_errors": discrepancies,
                       "undiscounted_suffix_return_max_abs_error": return_error,
                       "episode_bootstraps": bootstrap_rows,
                       "forced_single_choice_rows": int((masks.sum(axis=1) == 1).sum())})
        old = new
    assert archive_count == summary["decisions"] and native_count == summary["api_records"]
    final = model(RUN / "final.zip")
    assert manifest["final.zip"]["sha256"] == summary["final_checkpoint_sha256"]
    assert all(torch.equal(value, final.policy.state_dict()[name])
               for name, value in old.policy.state_dict().items())
    assert {int(state["step"].item()) for state in final.policy.optimizer.state.values()} == {
        summary["optimizer_updates"]}
    assert all(not torch.is_tensor(value) or torch.isfinite(value).all()
               for state in final.policy.optimizer.state.values() for value in state.values())
    process_rows = []
    for (pid, start), saved in sorted(identities.items()):
        current = proc_identity(pid)
        assert current is None or current["start_ticks"] != start, (saved, current)
        process_rows.append({"pid": pid, "saved_start_ticks": start, "current_identity": current,
                             "saved_identity_absent": True})
    assert not torch.cuda.is_initialized()
    review.update(rounds=rounds, unique_owned_process_identities=len(identities),
                  process_identity_checks=process_rows,
                  final_equals_last_checkpoint_policy=True, final_policy_and_adam_finite=True,
                  gamma=1., gae_lambda=1., native_records=native_count,
                  saved_actor_samples=archive_count, passed=True)
    read(Path(__file__).resolve())
    for relative, record in manifest.items():
        assert hashlib.sha256((RUN / relative).read_bytes()).hexdigest() == record["sha256"]
    review["original_artifacts_unchanged_during_read"] = True
except Exception as error:
    review["passed"] = False
    review["errors"].append(repr(error))
finally:
    review["cpu_only"] = {"cuda_initialized": torch.cuda.is_initialized(),
                          "optimizer_calls": 0, "ROS_native_jobs": 0, "signals": 0,
                          "tracked_writes": 0}
    review["limits"] = [
        "This bounded minimal run is an engineering sample, not a reliable95% task policy.",
        "CPU replay allows float32 device/batch roundoff; masks/tensors/actions are exact.",
        "Source checks and numerical health do not replace root's full native/scalar/ACK audit."]
    with OUTPUT.open("x") as target:
        target.write(json.dumps(review, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"receipt": str(OUTPUT), "passed": review["passed"],
                      "errors": review["errors"], "sha256": hashlib.sha256(
                          OUTPUT.read_bytes()).hexdigest()}, indent=2))
sys.exit(0 if review["passed"] else 1)
