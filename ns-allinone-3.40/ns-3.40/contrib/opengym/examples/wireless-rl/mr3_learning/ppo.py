"""Closed-episode MaskablePPO pilot on the native three-robot MR3 environment.

Only inference and SB3 optimization run in conda. Every environment delegates
physics, navigation and isolated rewards to the existing system-ROS worker.
Complete episodes settle late no-action terminal events before any PPO update.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import gymnasium as gym
import numpy as np
import torch
from sb3_contrib import MaskablePPO
from stable_baselines3.common.logger import configure

from .benchmark import resource_sample
from .env import MR3Env
from .observation import observation_space
from .policy import policy_kwargs
from .rollout import DecisionTransition, build_rollout_buffer, merge_zero_terminal
from .supervisor import SCENES, Supervisor, WORKSPACE


class ContractSpaces(gym.Env):
    """Describe the tensor contract without starting or sampling a simulator."""

    observation_space = observation_space()
    action_space = gym.spaces.Discrete(1000)

    def reset(self, **kwargs):
        raise RuntimeError("use the closed-episode collector, not SB3 learn()")

    def step(self, action):
        raise RuntimeError("use the closed-episode collector, not SB3 learn()")


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policy_sha(model):
    digest = hashlib.sha256()
    for key, value in sorted(model.policy.state_dict().items()):
        if not torch.isfinite(value).all():
            raise ValueError("nonfinite policy state: " + key)
        digest.update(key.encode())
        digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def infer(model, observations, *, deterministic=False):
    """Sample in stable worker order; masks come from these exact observations."""
    batch = {key: np.stack([obs[key] for obs in observations]) for key in observations[0]}
    masks = batch["action_mask"].astype(bool)
    if (masks.shape != (len(observations), 1000) or not masks.any(axis=1).all()
            or not np.isin(batch["action_mask"], [0, 1]).all()):
        raise ValueError("each exact observation requires a nonempty binary joint mask")
    model.policy.set_training_mode(False)
    with torch.no_grad():
        tensors, _ = model.policy.obs_to_tensor(batch)
        actions, values, log_probs = model.policy(
            tensors, deterministic=deterministic, action_masks=masks)
    return (actions.cpu().numpy().reshape(-1), values.cpu().numpy().reshape(-1),
            log_probs.cpu().numpy().reshape(-1))


def next_value(model, observation):
    with torch.no_grad():
        tensors, _ = model.policy.obs_to_tensor(observation)
        return float(model.policy.predict_values(tensors).cpu().item())


def collect_episodes(model, environments, tasks, *, deadline, deterministic=False,
                     progress=None):
    """Collect a fixed round, retaining every task outcome and API receipt.

    No optimizer runs until all workers close. A wall stop is requested through
    the existing external truncation path on the next physical step, followed
    by bounded native cancellation and cleanup; it is not a task failure.
    """
    if not tasks or len(environments) != len(tasks):
        raise ValueError("collector requires one environment per nonempty task")
    episodes = [[] for _ in tasks]
    summaries = [{} for _ in tasks]
    observations = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        resets = [pool.submit(env.reset, seed=task["seed"], options={
            "scene": task["scene"], "max_steps": task["cap"]})
            for env, task in zip(environments, tasks)]
        # Resolve every future, including failures; the caller owns all cleanup.
        errors = []
        for i, future in enumerate(resets):
            try:
                obs, info = future.result()
                observations[i] = obs
                summaries[i] = {**tasks[i], "epoch": info["epoch"], "api_records": 0,
                                "decisions": 0, "simulation_seconds": 0.,
                                "reward_sum": 0., "zero_terminal_events": 0,
                                "directory": str(environments[i].supervisor.episode.directory)}
            except Exception as error:
                summaries[i] = {**tasks[i], "infrastructure_error": repr(error)}
                errors.append(error)
        if progress:
            progress(summaries)
        if errors:
            raise errors[0]
        while observations:
            indices = sorted(observations)
            actions, values, log_probs = infer(
                model, [observations[i] for i in indices], deterministic=deterministic)
            if time.monotonic() >= deadline:
                for i in indices:
                    environments[i]._active_limit = environments[i]._steps + 1
            futures = [pool.submit(environments[i].step, int(actions[j]))
                       for j, i in enumerate(indices)]
            errors = []
            for j, (i, future) in enumerate(zip(indices, futures)):
                try:
                    following, reward, terminated, truncated, info = future.result()
                    summary = summaries[i]
                    summary["api_records"] += 1
                    summary["simulation_seconds"] += info["dt"]
                    summary["reward_sum"] += reward
                    if info.get("action_submitted", True) is False:
                        if not episodes[i]:
                            raise ValueError("no submitted decision precedes terminal settlement")
                        episodes[i][-1] = merge_zero_terminal(episodes[i][-1], reward, info)
                        summary["zero_terminal_events"] += 1
                    else:
                        episodes[i].append(DecisionTransition(
                            observation=observations[i], action=int(actions[j]), reward=reward,
                            value=float(values[j]), log_prob=float(log_probs[j]),
                            next_value=0. if terminated else next_value(model, following),
                            dt=info["dt"], terminated=terminated, truncated=truncated, info=info))
                        summary["decisions"] += 1
                    if terminated or truncated:
                        summary.update(terminated=terminated, truncated=truncated,
                                       reason=info.get("reason"),
                                       final_diagnostics=info.get("reward_diagnostics", {}))
                        del observations[i]
                    else:
                        observations[i] = following
                except Exception as error:
                    summaries[i]["infrastructure_error"] = repr(error)
                    errors.append(error)
            if progress:
                progress(summaries)
            if errors:
                raise errors[0]
    # Reap and verify native closure before allowing any sample to reach PPO.
    for environment, summary in zip(environments, summaries):
        environment.close()
        summary["shutdown"] = environment.supervisor.receipts[-1]
    return episodes, summaries


def save_rollout(path, buffer, episodes):
    """Store the actual sampled tensors/masks and PPO targets for offline audit."""
    rows = [row for episode in episodes for row in episode]
    np.savez_compressed(path,
                        **{"obs_" + key: value for key, value in buffer.observations.items()},
                        actions=buffer.actions, masks=buffer.action_masks,
                        rewards=buffer.rewards, values=buffer.values,
                        log_probs=buffer.log_probs, advantages=buffer.advantages,
                        returns=buffer.returns,
                        dt=np.array([row.dt for row in rows]),
                        terminated=np.array([row.terminated for row in rows]),
                        truncated=np.array([row.truncated for row in rows]),
                        next_values=np.array([row.next_value for row in rows]))
    write_json(path.with_suffix(".json"), [{
        "epoch": row.info["epoch"], "action": row.action,
        "observation_sequence": row.info.get("command", {}).get("observation_sequence"),
        "observation_digest": row.info.get("command", {}).get("observation_digest"),
        "candidate_version_at_end": row.info.get("candidate_version"),
        "reward_sequence": row.info.get("reward_diagnostics", {}).get("sequence"),
        "merged_zero_terminal": row.info.get("merged_zero_terminal", False),
        "terminal_settlement_info": row.info.get("terminal_settlement_info"),
    } for row in rows])


def parse_schedule(text):
    try:
        schedule = [(scene, int(seed)) for scene, seed in
                    (part.split(":") for part in text.split(","))]
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError("expected scene:seed comma-separated pairs") from error
    if not schedule or any(scene not in SCENES or seed < 0 for scene, seed in schedule):
        raise argparse.ArgumentTypeError("use declared development scenes and nonnegative seeds")
    return schedule


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=("train", "evaluate"), default="train")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--workers", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--schedule", type=parse_schedule, default=parse_schedule("open:101"))
    parser.add_argument("--decisions", type=int, required=True)
    parser.add_argument("--episode-steps", type=int, default=300)
    parser.add_argument("--wall-seconds", type=float, required=True)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--base-domain", type=int, default=160)
    parser.add_argument("--base-port", type=int, default=12301)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    if (args.decisions < 2 or not 1 <= args.episode_steps <= 300
            or not np.isfinite(args.wall_seconds) or args.wall_seconds <= 0
            or args.batch_size < 2 or args.epochs <= 0 or args.seed < 0):
        parser.error("invalid finite sampling/optimizer budget")
    if args.mode == "evaluate" and args.checkpoint is None:
        parser.error("evaluation requires a frozen --checkpoint")
    if args.mode == "train" and args.checkpoint:
        parser.error("pilot starts from scratch; resumption needs a separate declared run")
    if args.base_domain < 0 or args.base_domain + args.workers > 233:
        parser.error("worker ROS domains outside supported range")
    if args.base_port < 1024 or args.base_port + args.workers > 65536:
        parser.error("worker Gazebo ports outside supported range")
    if args.mode == "evaluate" and args.decisions != len(args.schedule) * args.episode_steps:
        parser.error("evaluation decision cap must cover each declared scheduled episode")

    started = time.monotonic()
    deadline = started + args.wall_seconds
    root = args.output_root or WORKSPACE / "ros2_ws/ros2-multi-robot-automap/log/mr3_ppo"
    # Validate safe run IDs and create exclusively before initializing any model.
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not args.run_id or any(c not in allowed for c in args.run_id):
        parser.error("run-id must be a safe path component")
    directory = root / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    freeze = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=WORKSPACE,
                                     text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                                    cwd=WORKSPACE, text=True)
    if dirty:
        parser.error("native training/evaluation requires a clean, committed source freeze")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    metadata = {**vars(args), "output_root": str(root),
                "checkpoint": str(args.checkpoint) if args.checkpoint else None,
                "kind": "mr3-p2a-closed-episode-maskable-ppo-v1", "freeze": freeze,
                "utc_start": datetime.now(timezone.utc).isoformat(),
                "command": [sys.executable, "-m", "mr3_learning.ppo", *(argv or sys.argv[1:])],
                "robots_per_worker": 3, "normalization": "frozen physical tensor scales only",
                "gamma_per_second": .99, "lambda_per_second": .95,
                "learning_rate": .0003, "entropy_coefficient": .01,
                "versions": {name: importlib.metadata.version(name) for name in
                             ("torch", "gymnasium", "stable-baselines3", "sb3-contrib", "numpy")}}
    write_json(directory / "metadata.json", metadata)
    resources = []
    stop = threading.Event()

    def sample_resources():
        while not stop.is_set():
            resources.append(resource_sample())
            stop.wait(2.)

    sampler = threading.Thread(target=sample_resources, daemon=True)
    sampler.start()
    result = {"freeze": freeze, "mode": args.mode, "episodes": [], "rounds": [],
              "decisions": 0, "api_records": 0, "optimizer_updates": 0, "error": None}
    environments = []
    model = None
    try:
        if args.mode == "train":
            model = MaskablePPO("MultiInputPolicy", ContractSpaces(),
                                policy_kwargs=policy_kwargs(), seed=args.seed, device=args.device,
                                n_steps=args.batch_size, batch_size=args.batch_size, n_epochs=args.epochs,
                                gamma=.99, gae_lambda=.95, learning_rate=.0003, ent_coef=.01,
                                target_kl=.03, verbose=0)
        else:
            model = MaskablePPO.load(args.checkpoint, device=args.device)
            result["input_checkpoint_sha256"] = file_sha(args.checkpoint)
        model.set_logger(configure(str(directory), ["json"]))
        optimizer_steps = [0]
        optimizer_hook = model.policy.optimizer.register_step_post_hook(
            lambda *unused: optimizer_steps.__setitem__(0, optimizer_steps[0] + 1))
        model.save(directory / "initial.zip")
        result["initial_checkpoint_sha256"] = file_sha(directory / "initial.zip")
        result["initial_policy_sha256"] = policy_sha(model)
        episode_index = 0
        round_index = 0
        while result["decisions"] < args.decisions and time.monotonic() < deadline:
            if args.mode == "evaluate" and episode_index >= len(args.schedule):
                break
            remaining = args.decisions - result["decisions"]
            count = min(args.workers, remaining)
            if args.mode == "evaluate":
                count = min(count, len(args.schedule) - episode_index)
            caps = [min(args.episode_steps, remaining // count + (i < remaining % count))
                    for i in range(count)]
            tasks = []
            environments = []
            for i, cap in enumerate(caps):
                scene, seed = args.schedule[episode_index % len(args.schedule)]
                tasks.append({"scene": scene, "seed": seed, "cap": cap,
                              "episode_index": episode_index, "worker_id": i})
                # A new supervisor per round keeps paths exclusive and ownership local.
                supervisor = Supervisor(run_id=f"round{round_index:04d}", worker_id=i,
                                        domain_id=args.base_domain + i,
                                        gazebo_port=args.base_port + i,
                                        output_root=directory / "native")
                environments.append(MR3Env(supervisor))
                episode_index += 1

            def progress(summaries):
                result["active_episodes"] = summaries
                write_json(directory / "progress.json", {
                    "completed_decisions": result["decisions"], "round": round_index,
                    "active_episodes": summaries, "elapsed_wall_sec": time.monotonic() - started})
            result["active_attempts"] = tasks
            write_json(directory / "summary.json", result)
            episodes, summaries = collect_episodes(
                model, environments, tasks, deadline=deadline,
                deterministic=args.mode == "evaluate", progress=progress)
            decisions = sum(len(episode) for episode in episodes)
            result["episodes"].extend(summaries)
            result["decisions"] += decisions
            result["api_records"] += sum(row["api_records"] for row in summaries)
            buffer = build_rollout_buffer(episodes, observation_space(),
                                          gym.spaces.Discrete(1000), device=args.device)
            save_rollout(directory / f"rollout_{round_index:04d}.npz", buffer, episodes)
            if args.mode == "train" and decisions >= 2:
                model.rollout_buffer = buffer
                model.num_timesteps = result["decisions"]
                model._current_progress_remaining = max(0., 1. - result["decisions"] / args.decisions)
                before = {key: value.detach().clone() for key, value in model.policy.state_dict().items()}
                model.train()
                policy_sha(model)  # Refuse nonfinite parameters before recording an update.
                changed = sum(not torch.equal(before[key], value) for key, value in
                              model.policy.state_dict().items())
                metrics = {}
                for key, value in model.logger.name_to_value.items():
                    if isinstance(value, (float, int, np.floating, np.integer)):
                        if np.isfinite(value):
                            metrics[key] = float(value)
                        elif key == "train/explained_variance":
                            metrics[key] = None  # Undefined for constant return targets.
                        else:
                            raise ValueError("nonfinite PPO metric: " + key)
                model.logger.dump(result["decisions"])
                result["optimizer_updates"] = optimizer_steps[0]
                result["ppo_epochs"] = model._n_updates
                result["rounds"].append({"round": round_index, "decisions": decisions,
                                         "changed_parameter_tensors": changed, "metrics": metrics})
                model.save(directory / f"checkpoint_{round_index:04d}.zip")
                if not changed:
                    raise RuntimeError("PPO update changed no policy parameters")
            result.pop("active_attempts", None)
            result.pop("active_episodes", None)
            write_json(directory / "summary.json", result)
            round_index += 1
            environments = []
        model.save(directory / "final.zip")
        optimizer_hook.remove()
        result["final_checkpoint_sha256"] = file_sha(directory / "final.zip")
        result["final_policy_sha256"] = policy_sha(model)
        if args.mode == "evaluate" and file_sha(args.checkpoint) != result["input_checkpoint_sha256"]:
            raise RuntimeError("evaluation changed the frozen checkpoint file")
        if args.mode == "evaluate" and (
                optimizer_steps[0] != 0
                or result["final_policy_sha256"] != result["initial_policy_sha256"]):
            raise RuntimeError("evaluation changed policy parameters or called optimizer.step")
    except BaseException as error:
        result["error"] = repr(error)
    finally:
        cleanup_errors = []
        for environment in environments:
            try:
                environment.close()
            except Exception as error:
                cleanup_errors.append(repr(error))
        result["cleanup_errors"] = cleanup_errors
        stop.set()
        sampler.join(timeout=10.)
        result["wall_sec_including_all_attempts"] = time.monotonic() - started
        result["quota_reached"] = result["decisions"] == args.decisions
        result["schedule_completed"] = (
            args.mode == "evaluate" and len(result["episodes"]) == len(args.schedule)
            and all(row.get("terminated") for row in result["episodes"]))
        result["stop_reason"] = (
            "infrastructure_error" if result["error"] or cleanup_errors
            else "schedule_completed" if result["schedule_completed"]
            else "decision_budget" if result["quota_reached"] else "wall_budget")
        result["completed"] = (
            result["error"] is None and not cleanup_errors
            and (result["schedule_completed"] if args.mode == "evaluate"
                 else result["decisions"] >= 2 and result["optimizer_updates"] > 0))
        write_json(directory / "resources.json", resources)
        write_json(directory / "summary.json", result)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("episodes", "rounds")}, indent=2))
    return 0 if result["completed"] else 1


if __name__ == "__main__":
    sys.exit(main())
