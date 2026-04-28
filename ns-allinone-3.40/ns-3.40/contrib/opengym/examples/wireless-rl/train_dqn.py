#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from ns3gym import ns3env

from dqn_common import (
    ACTION_DIM,
    QNetwork,
    ReplayBuffer,
    build_step_row,
    make_synthetic_training_batch,
    normalize_observation,
    select_dqn_action,
    summarize_rows,
)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def resolve_device(device_arg):
    if device_arg == "auto":
        return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    return torch.device(device_arg)


def parse_seeds(value):
    seeds = []
    for item in str(value).split(","):
        item = item.strip()
        if item:
            seeds.append(int(item))
    if not seeds:
        raise argparse.ArgumentTypeError("At least one eval seed is required")
    return seeds


def build_checkpoint(args, policy_net, extra=None):
    checkpoint = {
        "model_state_dict": policy_net.state_dict(),
        "hidden_size": args.hiddenSize,
        "network_type": args.networkType,
        "seed": args.seed,
        "episodes": args.episodes,
        "simTime": args.simTime,
        "stepTime": args.stepTime,
        "gamma": args.gamma,
        "rewardScale": args.rewardScale,
        "doubleDqn": args.doubleDqn,
        "pretrainSteps": args.pretrainSteps,
        "pretrainHeuristic": args.pretrainHeuristic,
        "state_dim": policy_net.feature[0].in_features,
        "action_dim": ACTION_DIM,
    }
    if extra:
        checkpoint.update(extra)
    return checkpoint


def update_dqn(policy_net,
               target_net,
               optimizer,
               replay_buffer,
               batch_size,
               gamma,
               reward_scale,
               double_dqn,
               device):
    if len(replay_buffer) < batch_size:
        return None

    states, actions, rewards, next_states, dones = replay_buffer.sample(batch_size)
    states = torch.as_tensor(states, dtype=torch.float32, device=device)
    actions = torch.as_tensor(actions, dtype=torch.long, device=device).unsqueeze(1)
    rewards = torch.as_tensor(rewards, dtype=torch.float32, device=device).unsqueeze(1) * reward_scale
    next_states = torch.as_tensor(next_states, dtype=torch.float32, device=device)
    dones = torch.as_tensor(dones, dtype=torch.float32, device=device).unsqueeze(1)

    q_values = policy_net(states).gather(1, actions)
    with torch.no_grad():
        if double_dqn:
            next_actions = policy_net(next_states).argmax(dim=1, keepdim=True)
            next_q_values = target_net(next_states).gather(1, next_actions)
        else:
            next_q_values = target_net(next_states).max(dim=1, keepdim=True)[0]
        targets = rewards + gamma * (1.0 - dones) * next_q_values

    loss = F.smooth_l1_loss(q_values, targets)
    optimizer.zero_grad()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(policy_net.parameters(), max_norm=10.0)
    optimizer.step()

    return float(loss.item())


def pretrain_policy(policy_net, optimizer, steps, batch_size, heuristic, rng, device):
    if steps <= 0:
        return []

    losses = []
    policy_net.train()
    for _ in range(steps):
        states, labels = make_synthetic_training_batch(batch_size, rng, strategy=heuristic)
        states = torch.as_tensor(states, dtype=torch.float32, device=device)
        labels = torch.as_tensor(labels, dtype=torch.long, device=device)

        logits = policy_net(states)
        loss = F.cross_entropy(logits, labels)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))

    return losses


def run_episode(args, episode, policy_net, target_net, optimizer, replay_buffer, epsilon, rng, device):
    env = ns3env.Ns3Env(
        port=0,
        stepTime=args.stepTime,
        startSim=True,
        simSeed=args.seed + episode,
        simArgs={
            "--simTime": args.simTime,
            "--envStepTime": args.stepTime,
        },
        debug=False,
    )

    rows = []
    losses = []
    total_reward = 0.0

    try:
        obs = env.reset()
        step = 0

        while True:
            state = normalize_observation(obs)
            action = select_dqn_action(policy_net, state, epsilon, rng, device)

            next_obs, reward, done, info = env.step(action)
            next_state = normalize_observation(next_obs)
            replay_buffer.add(state, action, reward, next_state, done)

            if len(replay_buffer) >= args.learningStarts:
                for _ in range(args.updatesPerStep):
                    loss = update_dqn(policy_net,
                                      target_net,
                                      optimizer,
                                      replay_buffer,
                                      args.batchSize,
                                      args.gamma,
                                      args.rewardScale,
                                      args.doubleDqn,
                                      device)
                    if loss is not None:
                        losses.append(loss)

            total_reward += float(reward)
            rows.append(build_step_row("dqn_train",
                                       args.seed,
                                       episode,
                                       step,
                                       obs,
                                       action,
                                       reward,
                                       total_reward,
                                       done,
                                       info))

            obs = next_obs
            step += 1

            if done:
                break
    finally:
        env.close()

    return rows, losses


def select_eval_action(model, obs, device):
    state = normalize_observation(obs)
    with torch.no_grad():
        state_tensor = torch.as_tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
        q_values = model(state_tensor)
        return int(torch.argmax(q_values, dim=1).item())


def run_eval_episode(args, policy_net, eval_seed, episode, device):
    env = ns3env.Ns3Env(
        port=0,
        stepTime=args.stepTime,
        startSim=True,
        simSeed=eval_seed,
        simArgs={
            "--simTime": args.simTime,
            "--envStepTime": args.stepTime,
        },
        debug=False,
    )

    rows = []
    total_reward = 0.0

    try:
        obs = env.reset()
        step = 0

        while True:
            action = select_eval_action(policy_net, obs, device)
            next_obs, reward, done, info = env.step(action)
            total_reward += float(reward)

            rows.append(build_step_row("dqn_validation",
                                       eval_seed,
                                       episode,
                                       step,
                                       obs,
                                       action,
                                       reward,
                                       total_reward,
                                       done,
                                       info))
            obs = next_obs
            step += 1

            if done:
                break
    finally:
        env.close()

    return rows


def evaluate_policy(args, policy_net, episode, device):
    if args.evalInterval <= 0:
        return {}

    was_training = policy_net.training
    policy_net.eval()
    summaries = []
    try:
        for eval_seed in args.evalSeeds:
            rows = run_eval_episode(args, policy_net, eval_seed, episode, device)
            summaries.append(summarize_rows(rows))
    finally:
        if was_training:
            policy_net.train()

    metric_keys = [
        "cumulative_reward",
        "average_reward",
        "average_throughput",
        "average_reward_queue",
        "average_total_delay",
        "average_deadline_misses",
        "service_amount_fairness",
    ]
    metrics = {}
    for key in metric_keys:
        values = np.asarray([float(summary[key]) for summary in summaries], dtype=np.float64)
        metrics[f"eval_mean_{key}"] = float(np.mean(values))
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Train a DQN scheduler for the wireless-rl ns3-gym environment")
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--simTime", type=float, default=20.0)
    parser.add_argument("--stepTime", type=float, default=0.5)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--learningRate", type=float, default=1e-3)
    parser.add_argument("--batchSize", type=int, default=64)
    parser.add_argument("--bufferSize", type=int, default=10000)
    parser.add_argument("--epsilonStart", type=float, default=1.0)
    parser.add_argument("--epsilonEnd", type=float, default=0.05)
    parser.add_argument("--epsilonDecay", type=float, default=0.995)
    parser.add_argument("--targetUpdateInterval", type=int, default=20)
    parser.add_argument("--hiddenSize", type=int, default=64)
    parser.add_argument("--networkType", choices=["mlp", "dueling"], default="dueling")
    parser.add_argument("--doubleDqn", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rewardScale", type=float, default=0.1)
    parser.add_argument("--updatesPerStep", type=int, default=1)
    parser.add_argument("--learningStarts", type=int, default=64)
    parser.add_argument("--pretrainSteps", type=int, default=0)
    parser.add_argument("--pretrainHeuristic",
                        choices=["max_service", "greedy", "delay_aware", "max_delay", "max_queue", "max_cqi"],
                        default="max_service")
    parser.add_argument("--evalInterval",
                        type=int,
                        default=0,
                        help="Evaluate and save a best checkpoint every N episodes; 0 disables validation")
    parser.add_argument("--evalSeeds",
                        type=parse_seeds,
                        default=[1001, 1002, 1003],
                        help="Comma-separated validation seeds used when evalInterval > 0")
    parser.add_argument("--runName", default=None)
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, cuda:0, cuda:1, ...")
    parser.add_argument("--outputDir", default="runtime")
    parser.add_argument("--modelDir", default="models")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    device = resolve_device(args.device)
    rng = np.random.default_rng(args.seed)

    policy_net = QNetwork(hidden_size=args.hiddenSize, network_type=args.networkType).to(device)
    target_net = QNetwork(hidden_size=args.hiddenSize, network_type=args.networkType).to(device)
    target_net.load_state_dict(policy_net.state_dict())
    target_net.eval()

    optimizer = torch.optim.Adam(policy_net.parameters(), lr=args.learningRate)
    replay_buffer = ReplayBuffer(args.bufferSize, args.seed)

    pretrain_losses = pretrain_policy(policy_net,
                                      optimizer,
                                      args.pretrainSteps,
                                      args.batchSize,
                                      args.pretrainHeuristic,
                                      rng,
                                      device)
    target_net.load_state_dict(policy_net.state_dict())

    train_rows = []
    epsilon = args.epsilonStart
    best_eval_reward = None
    best_eval_episode = None
    best_model_state = None

    print("DQN training")
    print("Device:", device)
    print("Episodes:", args.episodes)
    print("Network:", args.networkType)
    print("Double DQN:", args.doubleDqn)
    print("State dim:", policy_net.feature[0].in_features)
    print("Action dim:", ACTION_DIM)
    if pretrain_losses:
        print("Pretrain steps:", args.pretrainSteps)
        print("Pretrain heuristic:", args.pretrainHeuristic)
        print("Pretrain final loss:", f"{pretrain_losses[-1]:.6f}")

    for episode in range(args.episodes):
        rows, losses = run_episode(args,
                                   episode,
                                   policy_net,
                                   target_net,
                                   optimizer,
                                   replay_buffer,
                                   epsilon,
                                   rng,
                                   device)

        total_reward = float(rows[-1]["totalReward"]) if rows else 0.0
        average_reward = total_reward / len(rows) if rows else 0.0
        average_throughput = float(np.mean([float(row["lastThroughput"]) for row in rows])) if rows else 0.0
        average_queue = float(np.mean([float(row["rewardQueue"]) for row in rows])) if rows else 0.0
        average_total_delay = float(np.mean([float(row["totalDelay"]) for row in rows])) if rows else 0.0
        average_deadline_misses = float(np.mean([float(row["deadlineMisses"]) for row in rows])) if rows else 0.0
        final_total_delay = float(rows[-1]["totalDelay"]) if rows else 0.0
        final_deadline_misses = float(rows[-1]["deadlineMisses"]) if rows else 0.0
        average_loss = float(np.mean(losses)) if losses else 0.0
        eval_metrics = {}
        should_eval = args.evalInterval > 0 and ((episode + 1) % args.evalInterval == 0 or episode == args.episodes - 1)
        if should_eval:
            eval_metrics = evaluate_policy(args, policy_net, episode, device)
            eval_reward = eval_metrics.get("eval_mean_cumulative_reward")
            if eval_reward is not None and (best_eval_reward is None or eval_reward > best_eval_reward):
                best_eval_reward = eval_reward
                best_eval_episode = episode
                best_model_state = {
                    key: value.detach().cpu().clone()
                    for key, value in policy_net.state_dict().items()
                }

        train_row = {
            "episode": episode,
            "simSeed": args.seed + episode,
            "steps": len(rows),
            "total_reward": total_reward,
            "average_reward": average_reward,
            "epsilon": epsilon,
            "average_throughput": average_throughput,
            "average_queue": average_queue,
            "average_total_delay": average_total_delay,
            "average_deadline_misses": average_deadline_misses,
            "final_total_delay": final_total_delay,
            "final_deadline_misses": final_deadline_misses,
            "average_loss": average_loss,
            "buffer_size": len(replay_buffer),
        }
        train_row.update(eval_metrics)
        train_rows.append(train_row)

        if (episode + 1) % args.targetUpdateInterval == 0:
            target_net.load_state_dict(policy_net.state_dict())

        epsilon = max(args.epsilonEnd, epsilon * args.epsilonDecay)

        if not args.quiet:
            print(
                f"episode={episode:04d}",
                f"reward={total_reward:.3f}",
                f"avg_reward={average_reward:.3f}",
                f"epsilon={epsilon:.3f}",
                f"throughput={average_throughput:.3f}",
                f"queue={average_queue:.3f}",
                f"delay={average_total_delay:.3f}",
                f"misses={average_deadline_misses:.3f}",
                f"loss={average_loss:.5f}",
            )
            if eval_metrics:
                print(
                    f"validation_episode={episode:04d}",
                    f"eval_reward={eval_metrics['eval_mean_cumulative_reward']:.3f}",
                    f"eval_delay={eval_metrics['eval_mean_average_total_delay']:.3f}",
                    f"eval_misses={eval_metrics['eval_mean_average_deadline_misses']:.3f}",
                )

    output_dir = Path(args.outputDir)
    model_dir = Path(args.modelDir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    run_name = args.runName or f"dqn_seed{args.seed}"
    train_csv = output_dir / f"{run_name}_train.csv"
    model_path = model_dir / f"{run_name}.pt"
    best_model_path = model_dir / f"{run_name}_best.pt"
    write_csv(train_csv, train_rows)

    torch.save(build_checkpoint(args, policy_net), model_path)

    if best_model_state is not None:
        torch.save(build_checkpoint(args, policy_net, {
            "model_state_dict": best_model_state,
            "bestEvalEpisode": best_eval_episode,
            "bestEvalMeanCumulativeReward": best_eval_reward,
            "evalSeeds": args.evalSeeds,
            "evalInterval": args.evalInterval,
        }), best_model_path)

    print("\nSaved model:", model_path)
    if best_model_state is not None:
        print("Saved best validation model:", best_model_path)
        print("Best validation episode:", best_eval_episode)
        print("Best validation mean cumulative reward:", f"{best_eval_reward:.6f}")
    print("Saved training log:", train_csv)


if __name__ == "__main__":
    main()
