#!/usr/bin/env python3
"""Run the complete ideal-communication P2D scenario matrix serially."""

import argparse
import csv
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name("p2d_scenarios.json")
DEFAULT_SEEDS = (101, 202, 303)
SUMMARY_FIELDS = (
    "scenario_id",
    "episode_id",
    "world",
    "target_x",
    "target_y",
    "robot_count",
    "gazebo_seed",
    "battery_initial_energy",
    "require_charge",
    "ros_domain_id",
    "runner_returncode",
    "infrastructure_failure",
    "prestart_failure_count",
    "success",
    "termination_reason",
    "failure_reason",
    "task_phase",
    "elapsed_sim_time_sec",
    "time_to_detect_sec",
    "time_to_rally_sec",
    "completion_time_sec",
    "coverage_at_detection",
    "correct_free_coverage_ratio",
    "total_path_length_m",
    "phase_path_lengths_m",
    "search_overlap_ratio",
    "total_overlap_ratio",
    "phase_overlap_ratios",
    "collision_events",
    "nav_goal_count",
    "nav_succeeded",
    "nav_aborted",
    "battery_total_returns",
    "battery_total_charges",
    "battery_minimum_energy",
    "battery_total_charging_time_sec",
    "robots",
    "result_path",
    "command",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scenarios", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--robot-count", type=int, choices=range(2, 4), default=3)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--goal-timeout", type=float, default=60.0)
    parser.add_argument("--startup-timeout", type=float, default=600.0)
    parser.add_argument("--message-timeout", type=float, default=90.0)
    parser.add_argument("--evaluation-wait-timeout", type=float, default=600.0)
    parser.add_argument("--shutdown-timeout", type=float, default=60.0)
    parser.add_argument("--ros-domain-base", type=int, default=100)
    parser.add_argument("--inter-episode-delay", type=float, default=5.0)
    parser.add_argument("--infrastructure-retries", type=int, default=2)
    parser.add_argument("--skip-cross-check", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "log" / "p2d_baseline",
    )
    return parser.parse_args()


def load_config(path, selected_ids):
    with path.open() as source:
        config = json.load(source)
    scenarios = config.get("scenarios", [])
    ids = [scenario.get("id") for scenario in scenarios]
    if not scenarios or len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("scenario ids must be non-empty and unique")
    if selected_ids:
        unknown = set(selected_ids) - set(ids)
        if unknown:
            raise ValueError("unknown scenarios: " + ", ".join(sorted(unknown)))
        scenarios = [scenario for scenario in scenarios if scenario["id"] in selected_ids]

    worlds = PROJECT_ROOT / "src" / "multi_robot" / "worlds"
    for scenario in scenarios:
        world_name = scenario.get("world", "")
        world_path = worlds / world_name
        if Path(world_name).name != world_name or not world_path.is_file():
            raise ValueError(f"unknown world for {scenario['id']}: {world_name}")
        float(scenario["target_x"])
        float(scenario["target_y"])
        initial_energy = float(scenario["battery_initial_energy"])
        if initial_energy <= 0:
            raise ValueError(f"invalid energy for {scenario['id']}")
    prevalidation = {
        scenario["id"]: {
            "world": scenario["world"],
            "target_x": scenario["target_x"],
            "target_y": scenario["target_y"],
            "validated_by": "test_p2d_scenario_targets_are_free_and_rallyable",
        }
        for scenario in scenarios
    }
    return config, scenarios, prevalidation


def write_summary(run_dir, metadata, rows):
    with (run_dir / "summary.json").open("w") as output:
        json.dump({**metadata, "episodes": rows}, output, indent=2)
    with (run_dir / "summary.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_episode(scenario, seed, robot_count, cross_check=False):
    suffix = f"{robot_count}r_seed{seed}"
    if cross_check:
        suffix += "_crosscheck"
    return {
        "scenario": scenario,
        "seed": seed,
        "robot_count": robot_count,
        "suffix": suffix,
    }


def main():
    args = parse_args()
    if not 0 <= args.ros_domain_base <= 231:
        raise SystemExit("--ros-domain-base must be between 0 and 231")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if args.inter_episode_delay < 0:
        raise SystemExit("--inter-episode-delay must be non-negative")
    if args.infrastructure_retries < 0:
        raise SystemExit("--infrastructure-retries must be non-negative")
    try:
        config, scenarios, prevalidation = load_config(
            args.config, args.scenarios
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid P2D config: {error}") from error

    print(json.dumps(prevalidation, indent=2), flush=True)
    if args.validate_only:
        return 0

    run_id = args.run_id or time.strftime("p2d_%Y%m%d-%H%M%S")
    if re.fullmatch(r"[A-Za-z0-9_.-]+", run_id) is None:
        raise SystemExit("--run-id contains unsupported characters")
    run_dir = args.output_root / run_id
    if run_dir.exists():
        raise SystemExit(f"output already exists: {run_dir}")
    episode_dir = run_dir / "episodes"
    launch_log_dir = run_dir / "launch_logs"
    episode_dir.mkdir(parents=True)
    launch_log_dir.mkdir()

    episodes = [
        build_episode(scenario, seed, args.robot_count)
        for scenario in scenarios
        for seed in args.seeds
    ]
    cross_check = config.get("cross_check")
    if cross_check and not args.skip_cross_check:
        scenario_by_id = {scenario["id"]: scenario for scenario in scenarios}
        scenario = scenario_by_id.get(cross_check["scenario_id"])
        if scenario is not None:
            episodes.append(
                build_episode(
                    scenario,
                    int(cross_check["seed"]),
                    int(cross_check["robot_count"]),
                    cross_check=True,
                )
            )

    metadata = {
        "run_id": run_id,
        "baseline": "p2d_ideal_complete_task",
        "scenario_config": str(args.config),
        "seeds": args.seeds,
        "max_duration_sec": args.duration,
        "inter_episode_delay_sec": args.inter_episode_delay,
        "infrastructure_retries": args.infrastructure_retries,
        "retry_rule": "missing evaluation result only",
        "prevalidation": prevalidation,
    }
    rows = []
    smoke = PROJECT_ROOT / "scripts" / "ros_smoke_test.py"
    for index, episode in enumerate(episodes):
        if index:
            time.sleep(args.inter_episode_delay)
        scenario = episode["scenario"]
        episode_id = f"{run_id}_{scenario['id']}_{episode['suffix']}"
        result_path = episode_dir / f"{episode_id}.json"
        command = [
            sys.executable,
            str(smoke),
            "--world",
            scenario["world"],
            "--robot-count",
            str(episode["robot_count"]),
            "--gazebo-seed",
            str(episode["seed"]),
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
            "0",
            "--evaluation-wait-timeout",
            str(args.evaluation_wait_timeout),
            "--target-detection",
            "--rally",
            "--battery",
            # Keep the frozen P2D matrix reproducible after lowering the
            # interactive launch default battery capacity.
            "--battery-capacity",
            "100.0",
            "--battery-initial-energy",
            str(scenario["battery_initial_energy"]),
            "--target-x",
            str(scenario["target_x"]),
            "--target-y",
            str(scenario["target_y"]),
            "--evaluation-output-dir",
            str(episode_dir),
            "--log-dir",
            str(launch_log_dir),
            "--episode-id",
            episode_id,
        ]
        if scenario.get("require_charge", False):
            command.append("--require-charge")
        domain_id = (args.ros_domain_base + index) % 232
        environment = os.environ.copy()
        environment["ROS_DOMAIN_ID"] = str(domain_id)
        attempt_count = 0
        while True:
            attempt_count += 1
            print(
                f"Running attempt {attempt_count}: {shlex.join(command)}",
                flush=True,
            )
            completed = subprocess.run(command, check=False, env=environment)
            if result_path.exists() or attempt_count > args.infrastructure_retries:
                break
            print(
                "Retrying identical episode after pre-start infrastructure "
                "failure; prior launch log retained.",
                flush=True,
            )
            time.sleep(args.inter_episode_delay)
        result = {}
        if result_path.exists():
            with result_path.open() as result_file:
                result = json.load(result_file)
        infrastructure_failure = not result or result.get(
            "termination_reason"
        ) == "no_data"
        success = completed.returncode == 0 and bool(result.get("success"))
        failure_reason = result.get("failure_reason", "")
        if not success and not failure_reason:
            failure_reason = (
                "missing evaluation result"
                if infrastructure_failure
                else "runner validation failed"
            )
        row = {
            field: result.get(field, "") for field in SUMMARY_FIELDS
        }
        row.update(
            {
                "scenario_id": scenario["id"],
                "episode_id": episode_id,
                "world": scenario["world"],
                "target_x": scenario["target_x"],
                "target_y": scenario["target_y"],
                "robot_count": episode["robot_count"],
                "gazebo_seed": episode["seed"],
                "battery_initial_energy": scenario[
                    "battery_initial_energy"
                ],
                "require_charge": scenario.get("require_charge", False),
                "ros_domain_id": domain_id,
                "runner_returncode": completed.returncode,
                "infrastructure_failure": infrastructure_failure,
                "prestart_failure_count": attempt_count - 1,
                "success": success,
                "failure_reason": failure_reason,
                "phase_path_lengths_m": json.dumps(
                    result.get("phase_path_lengths_m", {}), sort_keys=True
                ),
                "phase_overlap_ratios": json.dumps(
                    result.get("phase_overlap_ratios", {}), sort_keys=True
                ),
                "robots": json.dumps(
                    result.get("robots", {}), sort_keys=True
                ),
                "result_path": str(result_path),
                "command": shlex.join(command),
            }
        )
        rows.append(row)
        write_summary(run_dir, metadata, rows)

    successes = sum(bool(row["success"]) for row in rows)
    infrastructure_failures = sum(
        bool(row["infrastructure_failure"]) for row in rows
    )
    print(
        f"Completed {len(rows)} episodes: {successes} success, "
        f"{infrastructure_failures} infrastructure failure.",
        flush=True,
    )
    print("Summary:", run_dir / "summary.json", flush=True)
    return 0 if successes == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
