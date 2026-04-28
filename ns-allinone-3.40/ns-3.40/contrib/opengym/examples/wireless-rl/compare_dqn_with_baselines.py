#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path

from run_baselines import read_csv_rows, save_metric_bar_svg, write_csv


METRICS = [
    ("cumulative_reward", "Cumulative Reward", "reward", False),
    ("average_reward", "Average Reward", "reward", False),
    ("average_throughput", "Average Throughput", "throughput", False),
    ("average_reward_queue", "Average Reward Queue", "queue", True),
    ("average_total_delay", "Average Total Delay", "delay", True),
    ("average_deadline_misses", "Average Deadline Misses", "misses", True),
    ("final_reward_queue", "Final Reward Queue", "queue", True),
    ("final_total_delay", "Final Total Delay", "delay", True),
    ("final_deadline_misses", "Final Deadline Misses", "misses", True),
    ("service_amount_fairness", "Jain Fairness of Served Amount", "fairness", False),
]


def load_single_row(path):
    rows = read_csv_rows(path)
    if len(rows) != 1:
        raise RuntimeError(f"Expected exactly one row in {path}, got {len(rows)}")
    return rows[0]


def main():
    parser = argparse.ArgumentParser(description="Compare a DQN run against baseline schedulers")
    parser.add_argument("--baselineCsv",
                        default="runtime/comparisons/baseline_comparison_all_seeds.csv")
    parser.add_argument("--dqnCsv",
                        default="runtime/comparisons/dqn_eval_all_seeds.csv")
    parser.add_argument("--outputDir",
                        default="runtime")
    parser.add_argument("--tag",
                        default=None)
    args = parser.parse_args()

    baseline_rows = read_csv_rows(Path(args.baselineCsv))
    dqn_row = load_single_row(Path(args.dqnCsv))
    rows = baseline_rows + [dqn_row]

    tag = args.tag or dqn_row["agent"]
    output_dir = Path(args.outputDir)
    comparison_dir = output_dir / "comparisons"
    plots_dir = output_dir / "plots"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    output_csv = comparison_dir / f"dqn_vs_baselines_{tag}.csv"
    write_csv(output_csv, rows)

    labels = [row["agent"] for row in rows]
    for key, title, ylabel, lower_is_better in METRICS:
        save_metric_bar_svg(
            plots_dir / f"dqn_vs_baselines_{tag}_{key}.svg",
            f"{title}: Baselines vs {tag}",
            ylabel,
            labels,
            [float(row[f"mean_{key}"]) for row in rows],
            lower_is_better=lower_is_better,
            errors=[float(row[f"std_{key}"]) for row in rows],
        )

    print("Saved comparison CSV:", output_csv)
    print("Saved comparison plots:", plots_dir)


if __name__ == "__main__":
    main()
