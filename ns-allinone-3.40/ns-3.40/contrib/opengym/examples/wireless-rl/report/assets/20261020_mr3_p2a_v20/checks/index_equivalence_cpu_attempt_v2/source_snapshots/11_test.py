#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import html
import math
from pathlib import Path

import numpy as np
from ns3gym import ns3env


USER_NUM = 5
FEATURES_PER_USER = 3
DEFAULT_OUTPUT_DIR = "runtime"


def split_observation(obs):
    """
    Observation format:
        [cqi0, queue0, delay0, cqi1, queue1, delay1, ...]

    Return:
        cqi   = [cqi0, cqi1, ..., cqi4]
        queue = [queue0, queue1, ..., queue4]
        delay = [delay0, delay1, ..., delay4]
    """
    obs = np.asarray(obs, dtype=np.float32)
    cqi = obs[0::FEATURES_PER_USER]
    queue = obs[1::FEATURES_PER_USER]
    delay = obs[2::FEATURES_PER_USER]
    return cqi, queue, delay


def select_action(obs, agent, step_idx):
    """
    Select scheduling action according to different baseline policies.

    action i means serving user i in this time slot.
    """
    cqi, queue, delay = split_observation(obs)

    if agent == "random":
        return None

    if agent == "round_robin":
        return int(step_idx % USER_NUM)

    if agent == "greedy":
        # Jointly consider channel quality and backlog.
        score = cqi * queue
        if np.sum(queue) == 0:
            score = cqi
        return int(np.argmax(score))

    if agent == "max_cqi":
        return int(np.argmax(cqi))

    if agent == "max_queue":
        return int(np.argmax(queue))

    if agent == "max_delay":
        if np.max(delay) <= 0:
            if np.max(queue) > 0:
                return int(np.argmax(queue))
            return int(np.argmax(cqi))
        return int(np.argmax(delay))

    if agent == "delay_aware":
        score = cqi * queue + 20.0 * delay
        if np.max(score) <= 0:
            score = cqi
        return int(np.argmax(score))

    raise ValueError(f"Unknown agent type: {agent}")


def parse_info(info):
    """
    Parse ns-3 extra info strings like:
        step=1|lastServedUser=4|lastThroughput=8|rewardQueue=20
    """
    parsed = {}
    if not info:
        return parsed

    if isinstance(info, dict):
        return info

    for item in str(info).split("|"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        try:
            number = float(value)
            if number.is_integer():
                number = int(number)
            parsed[key] = number
        except ValueError:
            parsed[key] = value

    return parsed


def make_output_paths(output_dir, agent, seed, episode, iterations):
    root = Path(output_dir)
    results_dir = root / "results"
    summaries_dir = root / "summaries"
    plots_dir = root / "plots"

    for directory in (results_dir, summaries_dir, plots_dir):
        directory.mkdir(parents=True, exist_ok=True)

    suffix = f"{agent}_seed{seed}"
    if iterations > 1:
        suffix += f"_ep{episode}"

    return {
        "root": root,
        "results": results_dir / f"{suffix}.csv",
        "summary": summaries_dir / f"{suffix}_summary.csv",
        "plot_prefix": plots_dir / suffix,
    }


def write_rows_csv(path, rows):
    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary_csv(path, summary):
    with path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)


def jain_fairness(values):
    values = [float(v) for v in values]
    denominator = len(values) * sum(v * v for v in values)
    if denominator == 0:
        return 0.0
    return (sum(values) ** 2) / denominator


def summarize_episode(rows):
    rewards = [float(row["reward"]) for row in rows]
    throughputs = [float(row["lastThroughput"]) for row in rows]
    current_queues = [float(row["currentQueue"]) for row in rows]
    reward_queues = [float(row["rewardQueue"]) for row in rows]
    total_delays = [float(row["totalDelay"]) for row in rows]
    deadline_misses = [float(row["deadlineMisses"]) for row in rows]

    service_counts = [0 for _ in range(USER_NUM)]
    service_amounts = [0.0 for _ in range(USER_NUM)]
    for row in rows:
        user = int(row["lastServedUser"])
        if 0 <= user < USER_NUM:
            service_counts[user] += 1
            service_amounts[user] += float(row["lastThroughput"])

    summary = {
        "agent": rows[0]["agent"],
        "seed": rows[0]["seed"],
        "episode": rows[0]["episode"],
        "steps": len(rows),
        "average_reward": np.mean(rewards) if rewards else 0.0,
        "cumulative_reward": rows[-1]["totalReward"] if rows else 0.0,
        "average_throughput": np.mean(throughputs) if throughputs else 0.0,
        "average_current_queue": np.mean(current_queues) if current_queues else 0.0,
        "average_reward_queue": np.mean(reward_queues) if reward_queues else 0.0,
        "average_total_delay": np.mean(total_delays) if total_delays else 0.0,
        "average_deadline_misses": np.mean(deadline_misses) if deadline_misses else 0.0,
        "final_current_queue": current_queues[-1] if current_queues else 0.0,
        "final_reward_queue": reward_queues[-1] if reward_queues else 0.0,
        "final_total_delay": total_delays[-1] if total_delays else 0.0,
        "final_deadline_misses": deadline_misses[-1] if deadline_misses else 0.0,
        "service_amount_fairness": jain_fairness(service_amounts),
    }

    for user in range(USER_NUM):
        summary[f"user{user}_served_count"] = service_counts[user]
        summary[f"user{user}_served_amount"] = service_amounts[user]

    return summary


def format_float(value):
    if isinstance(value, float):
        return f"{value:.6g}"
    return value


def save_line_svg(path, title, ylabel, series_by_name):
    width = 900
    height = 420
    left = 70
    right = 25
    top = 45
    bottom = 55
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c"]

    all_points = []
    for points in series_by_name.values():
        all_points.extend(points)

    if not all_points:
        return

    min_x = min(x for x, _ in all_points)
    max_x = max(x for x, _ in all_points)
    min_y = min(y for _, y in all_points)
    max_y = max(y for _, y in all_points)

    if min_x == max_x:
        max_x = min_x + 1
    if math.isclose(min_y, max_y):
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
        f'<text x="{width / 2}" y="26" text-anchor="middle" '
        f'font-family="Arial" font-size="18" font-weight="bold">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#111827"/>',
        f'<text x="{width / 2}" y="{height - 12}" text-anchor="middle" font-family="Arial" font-size="12">step</text>',
        f'<text x="18" y="{height / 2}" transform="rotate(-90 18 {height / 2})" '
        f'text-anchor="middle" font-family="Arial" font-size="12">{html.escape(ylabel)}</text>',
    ]

    for i in range(6):
        y_value = min_y + (max_y - min_y) * i / 5
        y = sy(y_value)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{y_value:.2f}</text>')

    legend_x = left + 10
    legend_y = top + 15
    for idx, (name, points) in enumerate(series_by_name.items()):
        color = colors[idx % len(colors)]
        polyline = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{polyline}"/>')
        parts.append(f'<rect x="{legend_x}" y="{legend_y + idx * 18 - 10}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 16}" y="{legend_y + idx * 18}" font-family="Arial" font-size="12">{html.escape(name)}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts))


def save_bar_svg(path, title, ylabel, labels, values):
    width = 760
    height = 420
    left = 70
    right = 30
    top = 45
    bottom = 65
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_value = max(values) if values else 1
    if max_value <= 0:
        max_value = 1

    bar_gap = 18
    bar_w = (plot_w - bar_gap * (len(values) + 1)) / max(len(values), 1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="26" text-anchor="middle" '
        f'font-family="Arial" font-size="18" font-weight="bold">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#111827"/>',
        f'<text x="18" y="{height / 2}" transform="rotate(-90 18 {height / 2})" '
        f'text-anchor="middle" font-family="Arial" font-size="12">{html.escape(ylabel)}</text>',
    ]

    for i in range(6):
        y_value = max_value * i / 5
        y = top + plot_h - (y_value / max_value) * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{y_value:.2f}</text>')

    for idx, value in enumerate(values):
        x = left + bar_gap + idx * (bar_w + bar_gap)
        bar_h = (value / max_value) * plot_h
        y = top + plot_h - bar_h
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="#2563eb"/>')
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{height - bottom + 20}" text-anchor="middle" font-family="Arial" font-size="12">{html.escape(labels[idx])}</text>')
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{y - 6:.2f}" text-anchor="middle" font-family="Arial" font-size="11">{value:.2f}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts))


def save_plots(plot_prefix, rows, summary):
    steps = [int(row["step"]) for row in rows]
    save_line_svg(
        plot_prefix.with_name(plot_prefix.name + "_reward.svg"),
        "Reward per Step",
        "reward",
        {
            "reward": list(zip(steps, [float(row["reward"]) for row in rows])),
            "totalReward": list(zip(steps, [float(row["totalReward"]) for row in rows])),
        },
    )
    save_line_svg(
        plot_prefix.with_name(plot_prefix.name + "_queue.svg"),
        "Queue Backlog",
        "queue",
        {
            "currentQueue": list(zip(steps, [float(row["currentQueue"]) for row in rows])),
            "rewardQueue": list(zip(steps, [float(row["rewardQueue"]) for row in rows])),
        },
    )
    save_line_svg(
        plot_prefix.with_name(plot_prefix.name + "_throughput.svg"),
        "Throughput per Step",
        "throughput",
        {
            "lastThroughput": list(zip(steps, [float(row["lastThroughput"]) for row in rows])),
        },
    )
    save_line_svg(
        plot_prefix.with_name(plot_prefix.name + "_delay.svg"),
        "Delay per Step",
        "delay",
        {
            "totalDelay": list(zip(steps, [float(row["totalDelay"]) for row in rows])),
            "currentDelay": list(zip(steps, [float(row["currentDelay"]) for row in rows])),
        },
    )
    save_line_svg(
        plot_prefix.with_name(plot_prefix.name + "_deadline_misses.svg"),
        "Deadline Misses per Step",
        "misses",
        {
            "deadlineMisses": list(zip(steps, [float(row["deadlineMisses"]) for row in rows])),
            "currentDeadlineMisses": list(zip(steps, [float(row["currentDeadlineMisses"]) for row in rows])),
        },
    )

    labels = [f"user{i}" for i in range(USER_NUM)]
    save_bar_svg(
        plot_prefix.with_name(plot_prefix.name + "_served_count.svg"),
        "Served Count per User",
        "count",
        labels,
        [float(summary[f"user{i}_served_count"]) for i in range(USER_NUM)],
    )
    save_bar_svg(
        plot_prefix.with_name(plot_prefix.name + "_served_amount.svg"),
        "Served Amount per User",
        "served amount",
        labels,
        [float(summary[f"user{i}_served_amount"]) for i in range(USER_NUM)],
    )


def build_row(episode, step_idx, args, cqi, queue, delay, action, reward, total_reward, done, info):
    parsed_info = parse_info(info)
    row = {
        "episode": episode,
        "step": step_idx,
        "agent": args.agent,
        "seed": args.seed,
        "action": int(action),
        "reward": float(reward),
        "totalReward": float(total_reward),
        "lastServedUser": int(parsed_info.get("lastServedUser", action)),
        "lastThroughput": float(parsed_info.get("lastThroughput", 0.0)),
        "rewardQueue": float(parsed_info.get("rewardQueue", np.sum(queue))),
        "currentQueue": float(parsed_info.get("currentQueue", np.sum(queue))),
        "totalDelay": float(parsed_info.get("totalDelay", np.sum(delay))),
        "currentDelay": float(parsed_info.get("currentDelay", np.sum(delay))),
        "deadlineMisses": int(parsed_info.get("deadlineMisses", 0)),
        "currentDeadlineMisses": int(parsed_info.get("currentDeadlineMisses", 0)),
        "done": bool(done),
        "info": str(info),
        "cqi": " ".join(str(int(v)) for v in cqi),
        "queue": " ".join(str(int(v)) for v in queue),
        "delay": " ".join(str(int(v)) for v in delay),
    }

    for user in range(USER_NUM):
        row[f"cqi{user}"] = int(cqi[user])
        row[f"queue{user}"] = int(queue[user])
        row[f"delay{user}"] = int(delay[user])

    return row


parser = argparse.ArgumentParser(description="Wireless resource allocation agent")

parser.add_argument("--start",
                    type=int,
                    default=1,
                    help="Start ns-3 simulation script 0/1, Default: 1")
parser.add_argument("--iterations",
                    type=int,
                    default=1,
                    help="Number of episodes, Default: 1")
parser.add_argument("--agent",
                    choices=[
                        "random",
                        "round_robin",
                        "max_cqi",
                        "max_queue",
                        "max_delay",
                        "greedy",
                        "delay_aware",
                    ],
                    default="greedy",
                    help="Scheduling policy, Default: greedy")
parser.add_argument("--port",
                    type=int,
                    default=0,
                    help="OpenGym port. Use 0 to pick a free port when --start=1")
parser.add_argument("--simTime",
                    type=float,
                    default=20.0,
                    help="Simulation time in seconds, Default: 20")
parser.add_argument("--stepTime",
                    type=float,
                    default=0.5,
                    help="Environment step time in seconds, Default: 0.5")
parser.add_argument("--seed",
                    type=int,
                    default=1,
                    help="ns-3 random run seed, Default: 1")
parser.add_argument("--outputDir",
                    default=DEFAULT_OUTPUT_DIR,
                    help="Directory for CSV summaries and plots, Default: runtime")
parser.add_argument("--no-save",
                    action="store_true",
                    help="Disable CSV and plot output")
parser.add_argument("--no-plot",
                    action="store_true",
                    help="Disable SVG plot output")

args = parser.parse_args()

startSim = bool(args.start)
port = args.port

if not startSim and port == 0:
    port = 5555

simArgs = {
    "--simTime": args.simTime,
    "--envStepTime": args.stepTime,
}

debug = False

env = ns3env.Ns3Env(
    port=port,
    stepTime=args.stepTime,
    startSim=startSim,
    simSeed=args.seed,
    simArgs=simArgs,
    debug=debug
)

np.random.seed(args.seed)
action_rng = np.random.default_rng(args.seed)
try:
    env.action_space.seed(args.seed)
except AttributeError:
    pass

ob_space = env.observation_space
ac_space = env.action_space

print("Observation space: ", ob_space, ob_space.dtype)
print("Action space: ", ac_space, ac_space.dtype)
print("Agent:", args.agent)
print("StartSim:", startSim)
print("Port:", port)
print("Simulation time:", args.simTime)
print("Step time:", args.stepTime)
print("Seed:", args.seed)
print("Output dir:", args.outputDir)
if args.iterations > 1:
    print("Note: multi-episode files use an _ep suffix; baseline comparison scripts assume --iterations 1.")

try:
    for currIt in range(args.iterations):
        print("\n==============================")
        print("Start iteration:", currIt)
        print("==============================")

        paths = make_output_paths(args.outputDir, args.agent, args.seed, currIt, args.iterations)

        obs = env.reset()
        totalReward = 0.0
        stepIdx = 0
        rows = []

        while True:
            cqi, queue, delay = split_observation(obs)
            action = select_action(obs, args.agent, stepIdx)

            if action is None:
                action = int(action_rng.integers(0, USER_NUM))

            print(
                "Step:", stepIdx,
                "cqi:", cqi.astype(int).tolist(),
                "queue:", queue.astype(int).tolist(),
                "delay:", delay.astype(int).tolist(),
                "action:", int(action)
            )

            obs, reward, done, info = env.step(action)
            totalReward += reward

            row = build_row(currIt,
                            stepIdx,
                            args,
                            cqi,
                            queue,
                            delay,
                            action,
                            reward,
                            totalReward,
                            done,
                            info)
            rows.append(row)

            print(
                "---reward:", round(float(reward), 3),
                "totalReward:", round(float(totalReward), 3),
                "throughput:", row["lastThroughput"],
                "currentQueue:", row["currentQueue"],
                "totalDelay:", row["totalDelay"],
                "deadlineMisses:", row["deadlineMisses"],
                "done:", done,
                "info:", info
            )

            stepIdx += 1

            if done:
                summary = summarize_episode(rows)
                print("Episode finished. Total reward:",
                      round(float(totalReward), 3))
                print("Average reward:", round(float(summary["average_reward"]), 3))
                print("Average throughput:", round(float(summary["average_throughput"]), 3))
                print("Average current queue:", round(float(summary["average_current_queue"]), 3))
                print("Average total delay:", round(float(summary["average_total_delay"]), 3))
                print("Average deadline misses:", round(float(summary["average_deadline_misses"]), 3))
                print("Final current queue:", round(float(summary["final_current_queue"]), 3))
                print("Final total delay:", round(float(summary["final_total_delay"]), 3))
                print("Service counts:",
                      [summary[f"user{i}_served_count"] for i in range(USER_NUM)])
                print("Service amounts:",
                      [format_float(summary[f"user{i}_served_amount"]) for i in range(USER_NUM)])

                if not args.no_save:
                    write_rows_csv(paths["results"], rows)
                    write_summary_csv(paths["summary"], summary)
                    print("Saved CSV:", paths["results"])
                    print("Saved summary:", paths["summary"])

                    if not args.no_plot:
                        save_plots(paths["plot_prefix"], rows, summary)
                        print("Saved plots:", paths["plot_prefix"].parent)

                break

    print("\nFinished all iterations")

except KeyboardInterrupt:
    print("Ctrl-C -> Exit")

finally:
    env.close()
    print("Done")
