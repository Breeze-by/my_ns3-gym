#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import html
import subprocess
import sys
from pathlib import Path


BASELINES = [
    "random",
    "round_robin",
    "max_cqi",
    "max_queue",
    "max_delay",
    "greedy",
    "delay_aware",
]
USER_NUM = 5
DEFAULT_OUTPUT_DIR = "runtime"


def read_csv_rows(path):
    with path.open(newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return

    with path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def to_float(row, key):
    return float(row[key])


def load_summary(output_dir, agent, seed):
    path = Path(output_dir) / "summaries" / f"{agent}_seed{seed}_summary.csv"
    rows = read_csv_rows(path)
    if not rows:
        raise RuntimeError(f"Empty summary file: {path}")
    return rows[0]


def load_results(output_dir, agent, seed):
    path = Path(output_dir) / "results" / f"{agent}_seed{seed}.csv"
    return read_csv_rows(path)


def run_agent(script_dir, args, agent):
    command = [
        sys.executable,
        str(script_dir / "test.py"),
        "--agent", agent,
        "--seed", str(args.seed),
        "--simTime", str(args.simTime),
        "--stepTime", str(args.stepTime),
        "--iterations", str(args.iterations),
        "--outputDir", str(args.outputDir),
    ]

    if args.no_plot:
        command.append("--no-plot")

    print("\n" + "=" * 72)
    print("Running baseline:", agent)
    print("Command:", " ".join(command))
    print("=" * 72)

    if args.quiet:
        completed = subprocess.run(command,
                                   cwd=script_dir,
                                   text=True,
                                   capture_output=True,
                                   check=False)
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            raise SystemExit(completed.returncode)
        tail_lines = completed.stdout.splitlines()[-8:] if completed.stdout else ["done"]
        print("\n".join(tail_lines))
    else:
        completed = subprocess.run(command, cwd=script_dir, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)


def save_metric_bar_svg(path, title, ylabel, labels, values, lower_is_better=False, errors=None):
    width = 860
    height = 440
    left = 75
    right = 30
    top = 50
    bottom = 85
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_value = max(values) if values else 1.0
    if errors:
        max_value = max(value + error for value, error in zip(values, errors))
    if max_value <= 0:
        max_value = 1.0

    colors = ["#64748b", "#0f766e", "#dc2626", "#9333ea", "#ea580c", "#2563eb", "#0891b2"]
    bar_gap = 18
    bar_w = (plot_w - bar_gap * (len(values) + 1)) / max(len(values), 1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" '
        f'font-family="Arial" font-size="18" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{width / 2}" y="47" text-anchor="middle" '
        f'font-family="Arial" font-size="12" fill="#64748b">'
        f'{"lower is better" if lower_is_better else "higher is better"}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#111827"/>',
        f'<text x="18" y="{height / 2}" transform="rotate(-90 18 {height / 2})" '
        f'text-anchor="middle" font-family="Arial" font-size="12">{html.escape(ylabel)}</text>',
    ]

    for i in range(6):
        value = max_value * i / 5
        y = top + plot_h - (value / max_value) * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')

    for idx, value in enumerate(values):
        x = left + bar_gap + idx * (bar_w + bar_gap)
        bar_h = (value / max_value) * plot_h
        y = top + plot_h - bar_h
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="{colors[idx % len(colors)]}"/>')
        if errors:
            error = errors[idx]
            high_y = top + plot_h - ((value + error) / max_value) * plot_h
            low_y = top + plot_h - (max(value - error, 0.0) / max_value) * plot_h
            center_x = x + bar_w / 2
            parts.append(f'<line x1="{center_x:.2f}" y1="{high_y:.2f}" x2="{center_x:.2f}" y2="{low_y:.2f}" stroke="#111827" stroke-width="1.5"/>')
            parts.append(f'<line x1="{center_x - 7:.2f}" y1="{high_y:.2f}" x2="{center_x + 7:.2f}" y2="{high_y:.2f}" stroke="#111827" stroke-width="1.5"/>')
            parts.append(f'<line x1="{center_x - 7:.2f}" y1="{low_y:.2f}" x2="{center_x + 7:.2f}" y2="{low_y:.2f}" stroke="#111827" stroke-width="1.5"/>')
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{height - bottom + 18}" text-anchor="middle" font-family="Arial" font-size="11">{html.escape(labels[idx])}</text>')
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{height - bottom + 34}" text-anchor="middle" font-family="Arial" font-size="10">{value:.2f}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts))


def save_line_svg(path, title, ylabel, series_by_name):
    width = 980
    height = 460
    left = 75
    right = 35
    top = 50
    bottom = 60
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = {
        "random": "#64748b",
        "round_robin": "#0f766e",
        "max_cqi": "#dc2626",
        "max_queue": "#9333ea",
        "max_delay": "#ea580c",
        "greedy": "#2563eb",
        "delay_aware": "#0891b2",
    }

    all_points = [point for points in series_by_name.values() for point in points]
    if not all_points:
        return

    min_x = min(x for x, _ in all_points)
    max_x = max(x for x, _ in all_points)
    min_y = min(y for _, y in all_points)
    max_y = max(y for _, y in all_points)

    if min_x == max_x:
        max_x = min_x + 1
    if min_y == max_y:
        max_y = min_y + 1

    pad_y = (max_y - min_y) * 0.08
    min_y -= pad_y
    max_y += pad_y

    def sx(x):
        return left + (x - min_x) / (max_x - min_x) * plot_w

    def sy(y):
        return top + (max_y - y) / (max_y - min_y) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" '
        f'font-family="Arial" font-size="18" font-weight="bold">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#111827"/>',
        f'<text x="{width / 2}" y="{height - 16}" text-anchor="middle" font-family="Arial" font-size="12">step</text>',
        f'<text x="18" y="{height / 2}" transform="rotate(-90 18 {height / 2})" '
        f'text-anchor="middle" font-family="Arial" font-size="12">{html.escape(ylabel)}</text>',
    ]

    for i in range(6):
        value = min_y + (max_y - min_y) * i / 5
        y = sy(value)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')

    legend_x = left + 12
    legend_y = top + 15
    for idx, (name, points) in enumerate(series_by_name.items()):
        color = colors.get(name, "#111827")
        polyline = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{polyline}"/>')
        parts.append(f'<rect x="{legend_x}" y="{legend_y + idx * 18 - 10}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 16}" y="{legend_y + idx * 18}" font-family="Arial" font-size="12">{html.escape(name)}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts))


def save_grouped_user_svg(path, title, ylabel, summaries, value_suffix):
    width = 980
    height = 460
    left = 75
    right = 35
    top = 50
    bottom = 80
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = ["#64748b", "#0f766e", "#dc2626", "#9333ea", "#ea580c", "#2563eb", "#0891b2"]
    labels = [row["agent"] for row in summaries]

    values = []
    for row in summaries:
        values.append([float(row[f"user{i}_{value_suffix}"]) for i in range(USER_NUM)])
    max_value = max((max(row) for row in values), default=1.0)
    if max_value <= 0:
        max_value = 1.0

    group_gap = 26
    inner_gap = 4
    group_w = (plot_w - group_gap * (USER_NUM + 1)) / USER_NUM
    bar_w = (group_w - inner_gap * (len(labels) - 1)) / len(labels)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" '
        f'font-family="Arial" font-size="18" font-weight="bold">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#111827"/>',
        f'<text x="18" y="{height / 2}" transform="rotate(-90 18 {height / 2})" '
        f'text-anchor="middle" font-family="Arial" font-size="12">{html.escape(ylabel)}</text>',
    ]

    for i in range(6):
        value = max_value * i / 5
        y = top + plot_h - (value / max_value) * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')

    for user in range(USER_NUM):
        group_x = left + group_gap + user * (group_w + group_gap)
        parts.append(f'<text x="{group_x + group_w / 2:.2f}" y="{height - bottom + 20}" text-anchor="middle" font-family="Arial" font-size="12">user{user}</text>')
        for agent_idx, row_values in enumerate(values):
            value = row_values[user]
            x = group_x + agent_idx * (bar_w + inner_gap)
            bar_h = (value / max_value) * plot_h
            y = top + plot_h - bar_h
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="{colors[agent_idx % len(colors)]}"/>')

    legend_x = left
    legend_y = height - 28
    for idx, label in enumerate(labels):
        x = legend_x + idx * 150
        parts.append(f'<rect x="{x}" y="{legend_y - 10}" width="10" height="10" fill="{colors[idx % len(colors)]}"/>')
        parts.append(f'<text x="{x + 16}" y="{legend_y}" font-family="Arial" font-size="12">{html.escape(label)}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts))


def generate_comparison_outputs(output_dir, agents, seed):
    output_dir = Path(output_dir)
    comparison_dir = output_dir / "comparisons"
    plots_dir = output_dir / "plots"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    summaries = [load_summary(output_dir, agent, seed) for agent in agents]
    results_by_agent = {agent: load_results(output_dir, agent, seed) for agent in agents}

    comparison_csv = comparison_dir / f"baseline_comparison_seed{seed}.csv"
    write_csv(comparison_csv, summaries)

    metrics = [
        ("cumulative_reward", "Cumulative Reward", "reward", False),
        ("average_reward", "Average Reward", "reward", False),
        ("average_throughput", "Average Throughput", "throughput", False),
        ("average_current_queue", "Average Current Queue", "queue", True),
        ("average_reward_queue", "Average Reward Queue", "queue", True),
        ("average_total_delay", "Average Total Delay", "delay", True),
        ("average_deadline_misses", "Average Deadline Misses", "misses", True),
        ("final_current_queue", "Final Current Queue", "queue", True),
        ("final_reward_queue", "Final Reward Queue", "queue", True),
        ("final_total_delay", "Final Total Delay", "delay", True),
        ("final_deadline_misses", "Final Deadline Misses", "misses", True),
        ("service_amount_fairness", "Jain Fairness of Served Amount", "fairness", False),
    ]
    for key, title, ylabel, lower_is_better in metrics:
        save_metric_bar_svg(
            plots_dir / f"baseline_comparison_seed{seed}_{key}.svg",
            title,
            ylabel,
            agents,
            [to_float(row, key) for row in summaries],
            lower_is_better=lower_is_better,
        )

    line_specs = [
        ("totalReward", "Cumulative Reward over Time", "total reward"),
        ("currentQueue", "Current Queue over Time", "queue"),
        ("rewardQueue", "Reward Queue over Time", "queue"),
        ("totalDelay", "Total Delay over Time", "delay"),
        ("currentDelay", "Current Delay over Time", "delay"),
        ("deadlineMisses", "Deadline Misses over Time", "misses"),
        ("currentDeadlineMisses", "Current Deadline Misses over Time", "misses"),
        ("lastThroughput", "Throughput over Time", "throughput"),
    ]
    for key, title, ylabel in line_specs:
        save_line_svg(
            plots_dir / f"baseline_comparison_seed{seed}_{key}.svg",
            title,
            ylabel,
            {
                agent: [(int(row["step"]), float(row[key])) for row in rows]
                for agent, rows in results_by_agent.items()
            },
        )

    save_grouped_user_svg(
        plots_dir / f"baseline_comparison_seed{seed}_served_count_by_user.svg",
        "Served Count by User",
        "served count",
        summaries,
        "served_count",
    )
    save_grouped_user_svg(
        plots_dir / f"baseline_comparison_seed{seed}_served_amount_by_user.svg",
        "Served Amount by User",
        "served amount",
        summaries,
        "served_amount",
    )

    return comparison_csv, plots_dir


def parse_agents(value):
    agents = [item.strip() for item in value.split(",") if item.strip()]
    invalid = [agent for agent in agents if agent not in BASELINES]
    if invalid:
        raise argparse.ArgumentTypeError(f"Invalid agent(s): {', '.join(invalid)}")
    return agents


def main():
    parser = argparse.ArgumentParser(description="Run and compare wireless-rl baseline schedulers")
    parser.add_argument("--agents",
                        type=parse_agents,
                        default=BASELINES,
                        help="Comma-separated baseline list")
    parser.add_argument("--seed",
                        type=int,
                        default=1,
                        help="ns-3 random run seed, Default: 1")
    parser.add_argument("--simTime",
                        type=float,
                        default=20.0,
                        help="Simulation time in seconds, Default: 20")
    parser.add_argument("--stepTime",
                        type=float,
                        default=0.5,
                        help="Environment step time in seconds, Default: 0.5")
    parser.add_argument("--iterations",
                        type=int,
                        default=1,
                        help="Number of episodes per baseline, Default: 1")
    parser.add_argument("--outputDir",
                        default=DEFAULT_OUTPUT_DIR,
                        help="Directory for CSV summaries and plots, Default: runtime")
    parser.add_argument("--skip-run",
                        action="store_true",
                        help="Only read existing per-baseline CSV files and regenerate comparison plots")
    parser.add_argument("--no-plot",
                        action="store_true",
                        help="Do not generate per-agent plots while running test.py")
    parser.add_argument("--quiet",
                        action="store_true",
                        help="Suppress per-agent command output unless a run fails")

    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent

    if args.iterations != 1:
        parser.error("Baseline comparison currently expects --iterations 1. Use run_multi_seed.py to aggregate multiple seeds.")

    if not args.skip_run:
        for agent in args.agents:
            run_agent(script_dir, args, agent)

    comparison_csv, plots_dir = generate_comparison_outputs(args.outputDir, args.agents, args.seed)
    print("\nComparison summary:", comparison_csv)
    print("Comparison plots:", plots_dir)
    print("Agents:", ", ".join(args.agents))


if __name__ == "__main__":
    main()
