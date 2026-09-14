#!/usr/bin/env python3
"""Run a bounded headless smoke test of the multi-robot ROS 2 stack."""

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_ros(arguments, timeout=10, discard_output=False):
    return subprocess.run(
        ["ros2", *arguments],
        check=False,
        text=True,
        stdout=subprocess.DEVNULL if discard_output else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def wait_until_ready(process, robot_count, timeout):
    expected_topics = {"/merge_map"}
    for index in range(1, robot_count + 1):
        expected_topics.update(
            {
                f"/tb{index}/cmd_vel",
                f"/tb{index}/map",
                f"/tb{index}/odom",
                f"/tb{index}/scan",
            }
        )

    deadline = time.monotonic() + timeout
    missing_topics = expected_topics
    inactive_nodes = []
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"launch exited early with status {process.returncode}"
            )

        topic_result = run_ros(["topic", "list", "--no-daemon"])
        topics = (
            set(topic_result.stdout.splitlines())
            if topic_result.returncode == 0
            else set()
        )
        missing_topics = expected_topics - topics

        inactive_nodes = []
        if not missing_topics:
            for index in range(1, robot_count + 1):
                for server in ("controller_server", "planner_server"):
                    node = f"/tb{index}/{server}"
                    try:
                        result = run_ros(
                            ["lifecycle", "get", node], timeout=10
                        )
                    except subprocess.TimeoutExpired:
                        result = None
                    if (
                        result is None
                        or result.returncode != 0
                        or "active" not in result.stdout.lower()
                    ):
                        inactive_nodes.append(node)
            if not inactive_nodes:
                return

        time.sleep(2)

    details = []
    if missing_topics:
        details.append("missing topics: " + ", ".join(sorted(missing_topics)))
    if inactive_nodes:
        details.append(
            "inactive lifecycle nodes: " + ", ".join(inactive_nodes)
        )
    raise TimeoutError("; ".join(details) or "ROS graph did not become ready")


def require_message(topic, timeout, qos_arguments=()):
    result = run_ros(
        ["topic", "echo", "--once", *qos_arguments, topic],
        timeout=timeout,
        discard_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"no message received from {topic}: {result.stderr.strip()}"
        )


def stop_launch(process, timeout):
    if process.poll() is not None:
        return True
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        return False


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--robot-count", type=int, choices=range(1, 5), default=1
    )
    parser.add_argument("--gazebo-seed", type=int, default=1)
    parser.add_argument("--spawn-timeout", type=float, default=90.0)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--message-timeout", type=float, default=30.0)
    parser.add_argument("--dwell-seconds", type=float, default=5.0)
    parser.add_argument("--shutdown-timeout", type=float, default=30.0)
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=PROJECT_ROOT / "log" / "smoke",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if shutil.which("ros2") is None or "ROS_DISTRO" not in os.environ:
        raise SystemExit(
            "source /opt/ros/humble/setup.bash and install/setup.bash first"
        )

    package = run_ros(["pkg", "prefix", "multi_robot"], timeout=10)
    if package.returncode != 0:
        raise SystemExit(
            "multi_robot is not installed; run colcon build and source "
            "install/setup.bash"
        )

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_name = (
        f"robots{args.robot_count}_seed{args.gazebo_seed}_{stamp}.log"
    )
    log_path = args.log_dir / log_name
    command = [
        "ros2",
        "launch",
        "multi_robot",
        "gazebo_multirobot_mapping_with_nav2.launch.py",
        f"robot_count:={args.robot_count}",
        "enable_gzclient:=false",
        "enable_rviz:=false",
        "enable_merge_rviz:=false",
        "auto_save_map:=false",
        f"gazebo_seed:={args.gazebo_seed}",
        f"spawn_timeout:={args.spawn_timeout}",
    ]

    print("Command:", " ".join(command), flush=True)
    print("Launch log:", log_path, flush=True)
    passed = False
    clean_shutdown = False
    with log_path.open("w") as log_file:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        try:
            wait_until_ready(process, args.robot_count, args.startup_timeout)
            print("ROS graph and Nav2 lifecycle nodes are ready.", flush=True)
            require_message(
                "/tb1/scan",
                args.message_timeout,
                ("--qos-reliability", "best_effort"),
            )
            require_message(
                "/merge_map",
                args.message_timeout,
                (
                    "--qos-reliability",
                    "reliable",
                    "--qos-durability",
                    "transient_local",
                ),
            )
            print("Received lidar and merged-map messages.", flush=True)
            time.sleep(args.dwell_seconds)
            if process.poll() is not None:
                raise RuntimeError(
                    "launch exited during dwell with status "
                    f"{process.returncode}"
                )
            passed = True
        except (
            RuntimeError,
            TimeoutError,
            subprocess.TimeoutExpired,
        ) as error:
            print(f"FAIL: {error}", file=sys.stderr, flush=True)
        finally:
            clean_shutdown = stop_launch(process, args.shutdown_timeout)

    if not clean_shutdown:
        print(
            "FAIL: launch required SIGTERM/SIGKILL during shutdown",
            file=sys.stderr,
        )
        return 1
    if not passed:
        print("Inspect launch log:", log_path, file=sys.stderr)
        return 1

    print(f"PASS: {args.robot_count}-robot headless smoke test", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
