#!/usr/bin/env python3
"""Run a bounded headless smoke test of the multi-robot ROS 2 stack."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def resolve_task_settings(args, duration_attribute, legacy_duration, legacy_coverage, legacy_wait=180.0):
    """Resolve a declared task before launching, rejecting conflicting CLI values."""
    contract_path = getattr(args, "task_contract", None)
    contract = None
    if contract_path:
        contract_path = Path(contract_path).expanduser().resolve()
        payload = contract_path.read_bytes()
        contract = json.loads(payload)
        if not isinstance(contract, dict):
            raise ValueError("task contract must be a JSON object")
        if contract.get("robots") != ["tb1", "tb2", "tb3"] or args.robot_count != 3:
            raise ValueError("MR3 task contracts require exactly tb1/tb2/tb3")
        duration = contract["max_duration_sec"]
        coverage = contract["coverage_threshold"]
        if not finite_number(duration) or duration <= 0:
            raise ValueError("task contract max_duration_sec must be finite and positive")
        if not finite_number(coverage) or coverage != .95:
            raise ValueError("MR3 task contract coverage_threshold must be 0.95")
        if contract.get("world_file") != args.world:
            raise ValueError(f"world is not declared by the task contract: {args.world}")
        quality = contract["quality"]
        if any(not finite_number(quality[field]) or not 0 <= quality[field] <= 1 for field in
               ("min_observed_accuracy", "max_false_free_ratio", "min_occupied_iou")):
            raise ValueError("task contract quality thresholds must be finite ratios")
        participation = contract["participation"]
        if not finite_number(participation["min_path_length_m"]) or participation["min_path_length_m"] <= 0:
            raise ValueError("task contract minimum participation path must be positive")
        if type(participation["min_goal_count"]) is not int or participation["min_goal_count"] < 1:
            raise ValueError("task contract minimum participation goal count must be positive")
        contract = {**contract, "sha256": hashlib.sha256(payload).hexdigest()}
        args.task_contract = contract_path
        for name, expected in ((duration_attribute, duration), ("coverage_threshold", coverage)):
            supplied = getattr(args, name)
            if supplied is not None and not math.isclose(supplied, expected, rel_tol=0, abs_tol=1e-9):
                raise ValueError(f"--{name.replace('_', '-')} conflicts with the task contract")
            setattr(args, name, expected)
    else:
        if getattr(args, duration_attribute) is None:
            setattr(args, duration_attribute, legacy_duration)
        if args.coverage_threshold is None:
            args.coverage_threshold = legacy_coverage
    duration = getattr(args, duration_attribute)
    if not finite_number(duration) or duration < 0 or (legacy_duration > 0 and duration == 0):
        raise ValueError("task duration must be finite and positive; plain smoke may use zero")
    if not finite_number(args.coverage_threshold) or not 0 <= args.coverage_threshold <= 1:
        raise ValueError("coverage threshold must be a finite ratio")
    if getattr(args, "evaluation_wait_timeout", None) is None:
        args.evaluation_wait_timeout = 900.0 if contract else legacy_wait
    if not finite_number(args.evaluation_wait_timeout) or args.evaluation_wait_timeout <= 0:
        raise ValueError("evaluation wait timeout must be finite and positive wall seconds")
    return contract


def validate_evaluation_result(result, coverage_threshold=0.0, task_contract=None):
    """Check native task evidence independently of the parent launch exit code."""
    if not isinstance(result, dict):
        raise RuntimeError("evaluation result must be a JSON object")
    required = {
        "schema_version", "correct_free_coverage_ratio", "coverage_threshold",
        "elapsed_sim_time_sec", "end_sim_time_sec", "map_message_count",
        "merged_map_origin_x", "model_state_message_count", "robots",
        "search_overlap_ratio", "start_sim_time_sec", "termination_reason",
        "total_path_length_m", "truth_rectangle_count", "success",
        "collision_events", "collision_monitoring_active", "max_duration_sec",
        "time_to_75_coverage_sec",
    }
    if task_contract:
        required.update({
            "task_contract_sha256", "map_quality_pass", "robot_participation_pass",
            "collision_monitoring_fresh", "task_start_barrier", "robot_count",
            "contact_monitor_summary", "observed_accuracy", "false_free_ratio", "occupied_iou",
            "navigation_protocol_closed",
        })
    missing = required - result.keys()
    if missing:
        raise RuntimeError("evaluation result is missing: " + ", ".join(sorted(missing)))
    expected_schema = 4 if task_contract else 3
    if type(result["schema_version"]) is not int or result["schema_version"] != expected_schema:
        raise RuntimeError(f"evaluation schema must be version {expected_schema}")
    for field in ("map_message_count", "model_state_message_count", "truth_rectangle_count"):
        if type(result[field]) is not int or result[field] < 1:
            raise RuntimeError(f"evaluation result has no valid {field}")
    for field in ("coverage_threshold", "correct_free_coverage_ratio", "elapsed_sim_time_sec", "max_duration_sec"):
        if not finite_number(result[field]):
            raise RuntimeError(f"evaluation result has invalid {field}")
    if abs(result["coverage_threshold"] - coverage_threshold) > 1e-9:
        raise RuntimeError("evaluation coverage threshold is incorrect")
    if not 0 <= result["correct_free_coverage_ratio"] <= 1:
        raise RuntimeError("evaluation coverage must be a ratio")
    if type(result["success"]) is not bool or result["success"] != (
        result["termination_reason"] == "coverage_reached"
    ):
        raise RuntimeError("evaluation success state is inconsistent")
    if result["success"] and result["correct_free_coverage_ratio"] < coverage_threshold:
        raise RuntimeError("evaluation completed below its threshold")
    if result["success"] and (
        result["collision_events"] != 0
        or result["collision_monitoring_active"] is not True
        or result.get("control_failure")
        or result["elapsed_sim_time_sec"] < 0
        or (result["max_duration_sec"] > 0
            and result["elapsed_sim_time_sec"] >= result["max_duration_sec"])
    ):
        raise RuntimeError("evaluation success violates safety or deadline")
    if task_contract:
        if result["task_contract_sha256"] != task_contract["sha256"]:
            raise RuntimeError("evaluation used a different task contract")
        if abs(result["max_duration_sec"] - task_contract["max_duration_sec"]) > 1e-9:
            raise RuntimeError("evaluation task duration is incorrect")
        if type(result["robot_count"]) is not int or result["robot_count"] != 3 or not isinstance(result["robots"], dict) or set(result["robots"]) != {"tb1", "tb2", "tb3"}:
            raise RuntimeError("MR3 evaluation requires exactly tb1/tb2/tb3")
        if result["task_start_barrier"] != "controller_release":
            raise RuntimeError("MR3 evaluation did not use the controller release barrier")
        gates = ("map_quality_pass", "robot_participation_pass", "collision_monitoring_fresh", "navigation_protocol_closed")
        if any(type(result[field]) is not bool for field in gates):
            raise RuntimeError("MR3 evaluation gates must be booleans")
        if result["success"]:
            if not all(result[field] for field in gates):
                raise RuntimeError("MR3 evaluation success violates a task gate")
            start, end = result["start_sim_time_sec"], result["end_sim_time_sec"]
            if any(not finite_number(value)
                   for value in (start, end)) or not math.isclose(
                       end - start, result["elapsed_sim_time_sec"], rel_tol=0, abs_tol=1e-6):
                raise RuntimeError("MR3 evaluation task time is inconsistent")
            if not isinstance(result["contact_monitor_summary"], dict) or result["contact_monitor_summary"].get("ever_unhealthy") is not False:
                raise RuntimeError("MR3 evaluation success has interrupted contact monitoring")
            participation = task_contract["participation"]
            if any(not isinstance(metrics, dict) or not finite_number(metrics.get("path_length_m"))
                   or metrics["path_length_m"] < participation["min_path_length_m"]
                   or type(metrics.get("nav_goal_count")) is not int
                   or metrics["nav_goal_count"] < participation["min_goal_count"]
                   for metrics in result["robots"].values()):
                raise RuntimeError("MR3 evaluation success has an inactive robot")
            quality = task_contract["quality"]
            if any(not finite_number(result[field]) or not 0 <= result[field] <= 1 for field in
                   ("observed_accuracy", "false_free_ratio", "occupied_iou")) or (
                result["observed_accuracy"] < quality["min_observed_accuracy"]
                or result["false_free_ratio"] > quality["max_false_free_ratio"]
                or result["occupied_iou"] < quality["min_occupied_iou"]
            ):
                raise RuntimeError("MR3 evaluation success violates map quality")
    return result


def lifecycle_is_active(output):
    return re.fullmatch(r"active\s*\[3\]", output.strip()) is not None


def run_ros(arguments, timeout=10, discard_output=False):
    return subprocess.run(
        ["ros2", *arguments],
        check=False,
        text=True,
        stdout=subprocess.DEVNULL if discard_output else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def wait_until_ready(process, robot_count, timeout, evaluation_enabled=False):
    import rclpy
    from multi_robot_exploration.nav2_ready_gate import wait_for_nav2
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState

    expected_topics = {"/merge_map"}
    for index in range(1, robot_count + 1):
        expected_topics.update(
            {
                f"/tb{index}/cmd_vel",
                f"/tb{index}/map",
                f"/tb{index}/odom",
                f"/tb{index}/scan",
                f"/tb{index}/joint_states",
            }
        )
    if evaluation_enabled:
        expected_topics.add("/gazebo/model_states")
        expected_topics.update(
            f"/tb{index}/collision" for index in range(1, robot_count + 1)
        )

    rclpy.init()
    node = Node("smoke_readiness")
    joint_messages = set()
    joint_subscriptions = []
    for index in range(1, robot_count + 1):
        topic = f"/tb{index}/joint_states"

        def receive_joints(message, topic=topic):
            if {"wheel_left_joint", "wheel_right_joint"}.issubset(message.name):
                joint_messages.add(topic)

        joint_subscriptions.append(node.create_subscription(
            JointState, topic, receive_joints, qos_profile_sensor_data,
        ))

    def graph_check():
        if process.poll() is not None:
            raise RuntimeError(
                f"launch exited early with status {process.returncode}"
            )
        topics = {name for name, _ in node.get_topic_names_and_types()}
        missing = [f"missing topic {name}" for name in sorted(expected_topics - topics)]
        missing.extend(f"missing wheel states /tb{index}" for index in range(1, robot_count + 1)
                       if f"/tb{index}/joint_states" not in joint_messages)
        return missing

    try:
        if wait_for_nav2(node, robot_count, timeout, graph_check) != 0:
            raise TimeoutError("ROS graph or Nav2 lifecycle did not become ready")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


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


def wait_for_evaluation(
    process, result_path, launch_log_path, timeout, coverage_threshold=0.0, task_contract=None
):
    deadline = time.monotonic() + timeout
    log_offset = 0
    while time.monotonic() < deadline:
        if result_path.exists():
            with result_path.open() as result_file:
                result = json.load(result_file)
            return validate_evaluation_result(result, coverage_threshold, task_contract)
        if process.poll() is not None:
            raise RuntimeError(
                "launch exited before evaluation result with "
                f"{process.returncode}"
            )
        with launch_log_path.open(errors="replace") as launch_log:
            launch_log.seek(log_offset)
            new_log = launch_log.read()
            log_offset = launch_log.tell()
        evaluator_died = any(
            "task_evaluator-" in line and "process has died" in line
            for line in new_log.splitlines()
        )
        if evaluator_died:
            raise RuntimeError(
                "task_evaluator process died before writing a result"
            )
        time.sleep(1)
    raise TimeoutError(f"evaluation result was not written: {result_path}")


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


def native_launch_failures(log_text):
    return [line for line in log_text.splitlines() if (
        "process has died" in line or "failed to terminate" in line
        or "sending signal 'SIGTERM'" in line or "sending signal 'SIGKILL'" in line
    )]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--robot-count", type=int, choices=range(1, 5), default=3
    )
    parser.add_argument("--world", default="my_world.world")
    parser.add_argument("--gazebo-seed", type=int, default=1)
    parser.add_argument("--goal-timeout", type=float, default=60.0)
    parser.add_argument("--spawn-timeout", type=float, default=90.0)
    parser.add_argument("--startup-timeout", type=float, default=300.0)
    parser.add_argument("--message-timeout", type=float, default=30.0)
    parser.add_argument("--dwell-seconds", type=float, default=5.0)
    parser.add_argument("--shutdown-timeout", type=float, default=30.0)
    parser.add_argument("--evaluation-duration", type=float, default=None)
    parser.add_argument("--coverage-threshold", type=float, default=None)
    parser.add_argument("--task-contract", type=Path, help="MR3 task contract; enables schema 4 evaluation")
    parser.add_argument("--evaluation-wait-timeout", type=float, default=None,
                        help="Wall watchdog: 900s for MR3 contracts, 180s for legacy smoke")
    parser.add_argument("--episode-id")
    parser.add_argument(
        "--evaluation-output-dir",
        type=Path,
        default=PROJECT_ROOT / "log" / "evaluation",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=PROJECT_ROOT / "log" / "smoke",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        task_contract = resolve_task_settings(args, "evaluation_duration", 0.0, 0.0)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"invalid task settings: {error}") from error
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
    episode_id = args.episode_id or (
        f"smoke_robots{args.robot_count}_seed{args.gazebo_seed}_{stamp}"
    )
    if re.fullmatch(r"[A-Za-z0-9_.-]+", episode_id) is None:
        raise SystemExit("--episode-id must contain only letters, digits, '.', '-', '_'")
    if args.evaluation_duration > 0 and any(
        (args.evaluation_output_dir / f"{episode_id}{suffix}").exists()
        for suffix in (".json", ".csv")
    ):
        raise SystemExit("evaluation output already exists; use a new episode id")
    log_name = (
        f"robots{args.robot_count}_seed{args.gazebo_seed}_{stamp}.log"
    )
    log_path = args.log_dir / log_name
    command = [
        "ros2",
        "launch",
        "multi_robot",
        "gazebo_multirobot_mapping_with_nav2.launch.py",
        f"world:={args.world}",
        f"robot_count:={args.robot_count}",
        "enable_gzclient:=false",
        "enable_rviz:=false",
        "enable_merge_rviz:=false",
        "auto_save_map:=false",
        f"gazebo_seed:={args.gazebo_seed}",
        f"spawn_timeout:={args.spawn_timeout}",
        f"nav2_ready_timeout_sec:={args.startup_timeout}",
        f"exploration_goal_timeout_sec:={args.goal_timeout}",
        f"enable_task_evaluator:={str(args.evaluation_duration > 0).lower()}",
        f"evaluation_episode_id:={episode_id}",
        f"evaluation_output_dir:={args.evaluation_output_dir}",
        f"evaluation_duration_sec:={args.evaluation_duration}",
        f"evaluation_coverage_threshold:={args.coverage_threshold}",
    ]

    if task_contract:
        command.append(f"evaluation_contract_path:={args.task_contract}")

    print("Command:", " ".join(command), flush=True)
    print("Launch log:", log_path, flush=True)
    launch_environment = os.environ.copy()
    launch_environment["PATH"] = os.pathsep.join(
        ("/usr/bin", "/bin", launch_environment["PATH"])
    )
    passed = False
    clean_shutdown = False
    cleanup_timeout = args.shutdown_timeout
    with log_path.open("w") as log_file:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
            env=launch_environment,
        )
        try:
            wait_until_ready(
                process,
                args.robot_count,
                args.startup_timeout,
                evaluation_enabled=args.evaluation_duration > 0,
            )
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
            if args.evaluation_duration > 0:
                result_path = args.evaluation_output_dir / f"{episode_id}.json"
                result = wait_for_evaluation(
                    process,
                    result_path,
                    log_path,
                    args.evaluation_wait_timeout,
                    args.coverage_threshold,
                    task_contract,
                )
                print(
                    "Evaluation result:",
                    result_path,
                    f"coverage={result['correct_free_coverage_ratio']:.3f}",
                    f"path={result['total_path_length_m']:.3f}m",
                    f"termination={result['termination_reason']}",
                    flush=True,
                )
                try:
                    process.wait(timeout=args.shutdown_timeout)
                except subprocess.TimeoutExpired:
                    cleanup_timeout = 0
                    raise RuntimeError("evaluator finished but owned launch did not shut down")
            if args.evaluation_duration <= 0:
                time.sleep(args.dwell_seconds)
            status = process.poll()
            if status is not None and (args.evaluation_duration <= 0 or status != 0):
                raise RuntimeError(
                    "launch exited during dwell with status "
                    f"{process.returncode}"
                )
            passed = True
        except (
            RuntimeError,
            TimeoutError,
            subprocess.TimeoutExpired,
            ValueError,
            TypeError,
            KeyError,
        ) as error:
            print(f"FAIL: {error}", file=sys.stderr, flush=True)
        finally:
            clean_shutdown = stop_launch(process, cleanup_timeout)

    if not clean_shutdown:
        print(
            "FAIL: launch required SIGTERM/SIGKILL during shutdown",
            file=sys.stderr,
        )
        return 1
    native_failures = native_launch_failures(log_path.read_text(errors="replace"))
    if native_failures:
        print("FAIL: native launch process failure: " + native_failures[0], file=sys.stderr)
        return 1
    if not passed:
        print("Inspect launch log:", log_path, file=sys.stderr)
        return 1

    print(f"PASS: {args.robot_count}-robot headless smoke test", flush=True)
    if args.evaluation_duration > 0:
        print(
            f"Task result: {'PASS' if result['success'] else 'FAIL'} "
            f"({result['termination_reason']})",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
