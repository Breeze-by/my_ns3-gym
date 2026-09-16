#!/usr/bin/env python3
"""Run repeatable ideal-communication exploration episodes serially."""

import argparse
import csv
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = (101, 202, 303)
SUMMARY_FIELDS = (
    "episode_id",
    "gazebo_seed",
    "runner_returncode",
    "success",
    "termination_reason",
    "failure_reason",
    "elapsed_sim_time_sec",
    "correct_free_coverage_ratio",
    "time_to_75_coverage_sec",
    "time_to_80_coverage_sec",
    "time_to_90_coverage_sec",
    "time_to_95_coverage_sec",
    "total_path_length_m",
    "search_overlap_ratio",
    "collision_events",
    "nav_goal_count",
    "nav_succeeded",
    "nav_aborted",
    "result_path",
    "command",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument(
        "--robot-count", type=int, choices=range(1, 5), default=2
    )
    parser.add_argument("--world", default="my_world.world")
    parser.add_argument("--duration", type=float, default=180.0)
    parser.add_argument("--coverage-threshold", type=float, default=0.90)
    parser.add_argument("--goal-timeout", type=float, default=60.0)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--message-timeout", type=float, default=90.0)
    parser.add_argument(
        "--evaluation-wait-timeout", type=float, default=270.0
    )
    parser.add_argument("--shutdown-timeout", type=float, default=60.0)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "log" / "ideal_baseline",
    )
    return parser.parse_args()


def write_summary(run_dir, metadata, rows):
    with (run_dir / "summary.json").open("w") as output:
        json.dump({**metadata, "episodes": rows}, output, indent=2)
    with (run_dir / "summary.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    if not 0.0 < args.coverage_threshold <= 1.0:
        raise SystemExit("--coverage-threshold must be in (0, 1]")
    world_path = (
        PROJECT_ROOT / "src" / "multi_robot" / "worlds" / args.world
    )
    if Path(args.world).name != args.world or not world_path.is_file():
        raise SystemExit(f"unknown world filename: {args.world}")
    run_id = args.run_id or time.strftime("ideal_%Y%m%d-%H%M%S")
    if re.fullmatch(r"[A-Za-z0-9_.-]+", run_id) is None:
        raise SystemExit(
            "--run-id may contain only letters, digits, '.', '-', '_'"
        )

    run_dir = args.output_root / run_id
    episode_dir = run_dir / "episodes"
    launch_log_dir = run_dir / "launch_logs"
    if run_dir.exists():
        raise SystemExit(f"output already exists: {run_dir}")
    episode_dir.mkdir(parents=True)
    launch_log_dir.mkdir()

    metadata = {
        "run_id": run_id,
        "baseline": "ideal_unlimited_communication",
        "world": args.world,
        "robot_count": args.robot_count,
        "seeds": args.seeds,
        "max_duration_sec": args.duration,
        "coverage_threshold": args.coverage_threshold,
        "goal_timeout_sec": args.goal_timeout,
        "message_timeout_sec": args.message_timeout,
        "charging_area": {"center_x": 0.0, "center_y": 0.0, "radius_m": 1.0},
    }
    rows = []
    smoke = PROJECT_ROOT / "scripts" / "ros_smoke_test.py"

    for seed in args.seeds:
        episode_id = f"{run_id}_seed{seed}"
        result_path = episode_dir / f"{episode_id}.json"
        command = [
            sys.executable,
            str(smoke),
            "--robot-count",
            str(args.robot_count),
            "--world",
            args.world,
            "--gazebo-seed",
            str(seed),
            "--goal-timeout",
            str(args.goal_timeout),
            "--startup-timeout",
            str(args.startup_timeout),
            "--message-timeout",
            str(args.message_timeout),
            "--shutdown-timeout",
            str(args.shutdown_timeout),
            "--evaluation-duration",
            str(args.duration),
            "--coverage-threshold",
            str(args.coverage_threshold),
            "--evaluation-wait-timeout",
            str(args.evaluation_wait_timeout),
            "--evaluation-output-dir",
            str(episode_dir),
            "--log-dir",
            str(launch_log_dir),
            "--episode-id",
            episode_id,
        ]
        print("Running:", shlex.join(command), flush=True)
        completed = subprocess.run(command, check=False)
        result = {}
        if result_path.exists():
            with result_path.open() as result_file:
                result = json.load(result_file)
        row = {
            field: result.get(field, "")
            for field in SUMMARY_FIELDS
        }
        row.update(
            {
                "episode_id": episode_id,
                "gazebo_seed": seed,
                "runner_returncode": completed.returncode,
                "success": result.get("success", False),
                "termination_reason": result.get(
                    "termination_reason", "runner_failure"
                ),
                "failure_reason": result.get(
                    "failure_reason", "missing evaluation result"
                ),
                "result_path": str(result_path),
                "command": shlex.join(command),
            }
        )
        rows.append(row)
        write_summary(run_dir, metadata, rows)

    infrastructure_failures = sum(
        row["runner_returncode"] != 0
        or row["termination_reason"] == "runner_failure"
        for row in rows
    )
    successes = sum(bool(row["success"]) for row in rows)
    print(
        f"Completed {len(rows)} episodes: {successes} success, "
        f"{infrastructure_failures} infrastructure failure."
    )
    print("Summary:", run_dir / "summary.json")
    return 1 if infrastructure_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
