#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
from pathlib import Path

import numpy as np
import torch
from ns3gym import ns3env

from dqn_common import QNetwork, build_step_row, normalize_observation, summarize_rows


def parse_seeds(value):
    seeds = []
    for item in value.split(","):
        item = item.strip()
        if item:
            seeds.append(int(item))
    if not seeds:
        raise argparse.ArgumentTypeError("At least one seed is required")
    return seeds


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def resolve_device(device_arg):
    if device_arg == "auto":
        return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    return torch.device(device_arg)


def select_greedy_action(model, obs, device):
    state = normalize_observation(obs)
    with torch.no_grad():
        state_tensor = torch.as_tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
        q_values = model(state_tensor)
        return int(torch.argmax(q_values, dim=1).item())


def run_eval_seed(args, seed, model, device):
    env = ns3env.Ns3Env(
        port=0,
        stepTime=args.stepTime,
        startSim=True,
        simSeed=seed,
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
            action = select_greedy_action(model, obs, device)
            next_obs, reward, done, info = env.step(action)
            total_reward += float(reward)

            rows.append(build_step_row(args.agentName,
                                       seed,
                                       0,
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


def aggregate_summaries(summaries):
    metric_keys = [
        "cumulative_reward",
        "average_reward",
        "average_throughput",
        "average_current_queue",
        "average_reward_queue",
        "average_total_delay",
        "average_deadline_misses",
        "final_current_queue",
        "final_reward_queue",
        "final_total_delay",
        "final_deadline_misses",
        "service_amount_fairness",
    ]

    row = {
        "agent": summaries[0]["agent"],
        "num_seeds": len(summaries),
        "seeds": " ".join(str(summary["seed"]) for summary in summaries),
    }
    for key in metric_keys:
        values = np.asarray([float(summary[key]) for summary in summaries], dtype=np.float64)
        row[f"mean_{key}"] = float(np.mean(values))
        row[f"std_{key}"] = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return row


def main():
    parser = argparse.ArgumentParser(description="Evaluate a trained DQN scheduler")
    parser.add_argument("--model", default="models/dqn_seed1.pt")
    parser.add_argument("--seeds", type=parse_seeds, default=[1])
    parser.add_argument("--agentName", default="dqn")
    parser.add_argument("--simTime", type=float, default=20.0)
    parser.add_argument("--stepTime", type=float, default=0.5)
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, cuda:0, cuda:1, ...")
    parser.add_argument("--outputDir", default="runtime")
    args = parser.parse_args()

    device = resolve_device(args.device)
    checkpoint = torch.load(args.model, map_location=device)
    model = QNetwork(hidden_size=int(checkpoint.get("hidden_size", 64)),
                     network_type=checkpoint.get("network_type", "mlp")).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    output_dir = Path(args.outputDir)
    results_dir = output_dir / "results"
    summaries_dir = output_dir / "summaries"
    comparisons_dir = output_dir / "comparisons"

    summaries = []
    print("DQN evaluation")
    print("Model:", args.model)
    print("Device:", device)
    print("Seeds:", ", ".join(str(seed) for seed in args.seeds))

    for seed in args.seeds:
        rows = run_eval_seed(args, seed, model, device)
        summary = summarize_rows(rows)
        summaries.append(summary)

        result_path = results_dir / f"{args.agentName}_seed{seed}.csv"
        summary_path = summaries_dir / f"{args.agentName}_seed{seed}_summary.csv"
        write_csv(result_path, rows)
        write_csv(summary_path, [summary])

        print(
            f"seed={seed}",
            f"reward={float(summary['cumulative_reward']):.3f}",
            f"throughput={float(summary['average_throughput']):.3f}",
            f"reward_queue={float(summary['average_reward_queue']):.3f}",
            f"delay={float(summary['average_total_delay']):.3f}",
            f"misses={float(summary['average_deadline_misses']):.3f}",
            f"fairness={float(summary['service_amount_fairness']):.3f}",
        )

    aggregate = aggregate_summaries(summaries)
    aggregate_path = comparisons_dir / f"{args.agentName}_eval_all_seeds.csv"
    write_csv(aggregate_path, [aggregate])
    print("\nSaved aggregate evaluation:", aggregate_path)


if __name__ == "__main__":
    main()
