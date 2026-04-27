#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

from run_baselines import (
    BASELINES,
    DEFAULT_OUTPUT_DIR,
    parse_agents,
    read_csv_rows,
    save_metric_bar_svg,
    write_csv,
)


AGGREGATE_METRICS = [
    ("cumulative_reward", "Cumulative Reward", "reward", False),
    ("average_reward", "Average Reward", "reward", False),
    ("average_throughput", "Average Throughput", "throughput", False),
    ("average_current_queue", "Average Current Queue", "queue", True),
    ("average_reward_queue", "Average Reward Queue", "queue", True),
    ("final_current_queue", "Final Current Queue", "queue", True),
    ("final_reward_queue", "Final Reward Queue", "queue", True),
    ("service_amount_fairness", "Jain Fairness of Served Amount", "fairness", False),
]


def parse_seeds(value):
    seeds = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        seeds.append(int(item))
    if not seeds:
        raise argparse.ArgumentTypeError("At least one seed is required")
    return seeds


def load_seed_rows(output_dir, seed):
    path = Path(output_dir) / "comparisons" / f"baseline_comparison_seed{seed}.csv"
    rows = read_csv_rows(path)
    if not rows:
        raise RuntimeError(f"Empty comparison file: {path}")
    return rows


def run_seed(script_dir, args, seed):
    command = [
        sys.executable,
        str(script_dir / "run_baselines.py"),
        "--seed", str(seed),
        "--simTime", str(args.simTime),
        "--stepTime", str(args.stepTime),
        "--iterations", "1",
        "--outputDir", str(args.outputDir),
        "--agents", ",".join(args.agents),
    ]

    if args.no_plot:
        command.append("--no-plot")
    if args.quiet:
        command.append("--quiet")

    print("\n" + "=" * 72)
    print("Running multi-seed batch for seed:", seed)
    print("Command:", " ".join(command))
    print("=" * 72)

    completed = subprocess.run(command, cwd=script_dir, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def aggregate_rows(rows_by_seed, agents, seeds):
    summaries = []

    for agent in agents:
        agent_rows = []
        for seed in seeds:
            seed_rows = rows_by_seed[seed]
            matched_rows = [row for row in seed_rows if row["agent"] == agent]
            if not matched_rows:
                raise RuntimeError(f"Missing agent '{agent}' in seed {seed} comparison output")
            agent_rows.append(matched_rows[0])

        summary = {
            "agent": agent,
            "num_seeds": len(seeds),
            "seeds": " ".join(str(seed) for seed in seeds),
        }

        for key, _, _, _ in AGGREGATE_METRICS:
            values = np.asarray([float(row[key]) for row in agent_rows], dtype=np.float64)
            summary[f"mean_{key}"] = float(np.mean(values))
            summary[f"std_{key}"] = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0

        summaries.append(summary)

    return summaries


def save_aggregate_plots(output_dir, summaries):
    plots_dir = Path(output_dir) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for key, title, ylabel, lower_is_better in AGGREGATE_METRICS:
        save_metric_bar_svg(
            plots_dir / f"baseline_comparison_all_seeds_{key}.svg",
            f"{title} across Seeds",
            ylabel,
            [row["agent"] for row in summaries],
            [float(row[f"mean_{key}"]) for row in summaries],
            lower_is_better=lower_is_better,
            errors=[float(row[f"std_{key}"]) for row in summaries],
        )


def main():
    parser = argparse.ArgumentParser(description="Run wireless-rl baseline comparisons across multiple seeds")
    parser.add_argument("--agents",
                        type=parse_agents,
                        default=BASELINES,
                        help="Comma-separated baseline list")
    parser.add_argument("--seeds",
                        type=parse_seeds,
                        default=[1, 2, 3, 4, 5],
                        help="Comma-separated random seed list, Default: 1,2,3,4,5")
    parser.add_argument("--simTime",
                        type=float,
                        default=20.0,
                        help="Simulation time in seconds, Default: 20")
    parser.add_argument("--stepTime",
                        type=float,
                        default=0.5,
                        help="Environment step time in seconds, Default: 0.5")
    parser.add_argument("--outputDir",
                        default=DEFAULT_OUTPUT_DIR,
                        help="Directory for CSV summaries and plots, Default: runtime")
    parser.add_argument("--skip-run",
                        action="store_true",
                        help="Only read existing per-seed comparison CSV files and regenerate aggregate outputs")
    parser.add_argument("--no-plot",
                        action="store_true",
                        help="Do not generate per-agent plots while running the per-seed baseline script")
    parser.add_argument("--quiet",
                        action="store_true",
                        help="Pass quiet mode through to the per-seed baseline script")

    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent

    if not args.skip_run:
        for seed in args.seeds:
            run_seed(script_dir, args, seed)

    rows_by_seed = {seed: load_seed_rows(args.outputDir, seed) for seed in args.seeds}
    aggregate_rows_out = aggregate_rows(rows_by_seed, args.agents, args.seeds)

    comparison_dir = Path(args.outputDir) / "comparisons"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    aggregate_path = comparison_dir / "baseline_comparison_all_seeds.csv"
    write_csv(aggregate_path, aggregate_rows_out)
    save_aggregate_plots(args.outputDir, aggregate_rows_out)

    print("\nAggregate summary:", aggregate_path)
    print("Aggregate plots:", Path(args.outputDir) / "plots")
    print("Agents:", ", ".join(args.agents))
    print("Seeds:", ", ".join(str(seed) for seed in args.seeds))


if __name__ == "__main__":
    main()
