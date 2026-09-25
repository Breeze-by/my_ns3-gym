#!/usr/bin/env python3
"""Run a bounded headless smoke test of the multi-robot ROS 2 stack."""

import argparse
import json
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


def wait_until_ready(
    process,
    robot_count,
    timeout,
    evaluation_enabled=False,
    target_detection_enabled=False,
    battery_enabled=False,
):
    expected_topics = {
        "/gateway/acks",
        "/gateway/downlink/candidates",
        "/gateway/downlink/delivered",
        "/gateway/uplink/candidates",
        "/gateway/uplink/delivered",
        "/merge_map",
        "/task_state",
    }
    for index in range(1, robot_count + 1):
        expected_topics.update(
            {
                f"/tb{index}/cmd_vel",
                f"/tb{index}/map",
                f"/tb{index}/odom",
                f"/tb{index}/scan",
                f"/tb{index}/gateway/merge_map",
                f"/gateway/received/tb{index}/map",
                f"/gateway/received/tb{index}/odom",
                f"/gateway/received/tb{index}/tf",
            }
        )
    if evaluation_enabled:
        expected_topics.add("/gazebo/model_states")
        expected_topics.update(
            f"/tb{index}/collision" for index in range(1, robot_count + 1)
        )
    if target_detection_enabled:
        expected_topics.add("/gateway/received/target_detection")
    if battery_enabled:
        expected_topics.update(
            f"/tb{index}/battery_state"
            for index in range(1, robot_count + 1)
        )

    deadline = time.monotonic() + timeout
    missing_topics = expected_topics
    inactive_nodes = []
    active_nodes = set()
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
                for server in (
                    "controller_server",
                    "planner_server",
                    "bt_navigator",
                ):
                    node = f"/tb{index}/{server}"
                    if node in active_nodes:
                        continue
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
                    else:
                        active_nodes.add(node)
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


def require_entities(names, timeout):
    result = run_ros(
        ["topic", "echo", "--once", "/gazebo/model_states", "--field", "name"],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "could not read Gazebo entities: " + result.stderr.strip()
        )
    missing = [name for name in names if name not in result.stdout]
    if missing:
        raise RuntimeError(
            "Gazebo entities were not spawned: " + ", ".join(missing)
        )


def require_bypass_audit(robot_count, timeout, graph_output=None):
    wait_sec = max(10.0, min(float(timeout), 60.0))
    arguments = [
        "run",
        "multi_robot_exploration",
        "bypass_audit",
        "--robot-count",
        str(robot_count),
        "--wait-sec",
        str(wait_sec),
    ]
    if graph_output is not None:
        arguments.extend(["--graph-output", str(graph_output)])
    result = run_ros(
        arguments,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "P3A forbidden-bypass audit failed: "
            + (result.stdout + result.stderr).strip()
        )


def wait_for_evaluation(
    process,
    result_path,
    launch_log_path,
    timeout,
    coverage_threshold=0.0,
    target_detection=False,
    expect_target_found=True,
    rally=False,
    battery=False,
    require_charge=False,
):
    deadline = time.monotonic() + timeout
    log_offset = 0
    while time.monotonic() < deadline:
        if result_path.exists():
            with result_path.open() as result_file:
                result = json.load(result_file)
            required = {
                "correct_free_coverage_ratio",
                "coverage_threshold",
                "elapsed_sim_time_sec",
                "end_sim_time_sec",
                "map_message_count",
                "merged_map_origin_x",
                "model_state_message_count",
                "robots",
                "search_overlap_ratio",
                "total_overlap_ratio",
                "phase_overlap_ratios",
                "phase_path_lengths_m",
                "start_sim_time_sec",
                "termination_reason",
                "total_path_length_m",
                "truth_rectangle_count",
                "success",
                "target_found",
                "target_confirmation_frames",
                "target_field_of_view_deg",
                "target_max_distance_m",
                "time_to_detect_sec",
                "time_to_rally_sec",
                "completion_time_sec",
                "rally_assignments",
                "rally_position_tolerance_m",
                "rally_linear_tolerance_mps",
                "rally_angular_tolerance_radps",
                "rally_hold_sec",
                "rally_min_separation_m",
                "time_to_75_coverage_sec",
                "battery_enabled",
                "battery_total_returns",
                "battery_total_charges",
                "battery_minimum_energy",
                "battery_total_charging_time_sec",
            }
            missing = required - result.keys()
            if missing:
                raise RuntimeError(
                    "evaluation result is missing: "
                    + ", ".join(sorted(missing))
                )
            if result["map_message_count"] < 1:
                raise RuntimeError(
                    "evaluation result has no merged-map messages"
                )
            if result["model_state_message_count"] < 1:
                raise RuntimeError(
                    "evaluation result has no Gazebo model states"
                )
            if result["truth_rectangle_count"] < 1:
                raise RuntimeError("evaluation truth grid is empty")
            if abs(result["coverage_threshold"] - coverage_threshold) > 1e-9:
                raise RuntimeError(
                    "evaluation coverage threshold is incorrect"
                )
            successful_reasons = (
                ("task_complete",)
                if rally
                else (
                    ("target_found",)
                    if target_detection
                    else ("coverage_reached",)
                )
            )
            successful_reason = result["termination_reason"] in successful_reasons
            if result["success"] != successful_reason:
                raise RuntimeError("evaluation success state is inconsistent")
            if (
                result["success"]
                and not rally
                and result["correct_free_coverage_ratio"]
                < coverage_threshold
            ):
                raise RuntimeError("evaluation completed below its threshold")
            if target_detection:
                target_found = result["target_found"] and (
                    result["time_to_detect_sec"] is not None
                    and result["target_confirmation_frames"] >= 1
                )
                if target_found != expect_target_found:
                    raise RuntimeError(
                        "target detection result did not match expectation"
                    )
                if not expect_target_found and (
                    result["termination_reason"] != "timeout"
                    or result["success"]
                ):
                    raise RuntimeError("negative detection episode did not timeout")
            if rally:
                if (
                    result["termination_reason"] != "task_complete"
                    or result["task_phase"] != "COMPLETE"
                    or result["time_to_rally_sec"] is None
                    or result["completion_time_sec"] is None
                    or len(result["rally_assignments"])
                    != len(result["robots"])
                    or (
                        len(result["robots"]) > 1
                        and (
                            result["rally_min_separation_m"] is None
                            or result["rally_min_separation_m"] < 0.8
                        )
                    )
                    or result["collision_events"] != 0
                ):
                    raise RuntimeError("rally task did not complete safely")
                for robot in result["robots"].values():
                    if (
                        robot["rally_final_error_m"]
                        > result["rally_position_tolerance_m"]
                        or robot["final_linear_speed_mps"]
                        > result["rally_linear_tolerance_mps"]
                        or robot["final_angular_speed_radps"]
                        > result["rally_angular_tolerance_radps"]
                    ):
                        raise RuntimeError(
                            "robot did not satisfy final rally tolerances"
                        )
            if battery:
                if not result["battery_enabled"]:
                    raise RuntimeError("battery managers did not report state")
                if result["battery_minimum_energy"] <= 0:
                    raise RuntimeError("a robot exhausted its battery")
                for robot in result["robots"].values():
                    if (
                        robot["battery_message_count"] < 1
                        or robot["battery_mode"] != "ACTIVE"
                    ):
                        raise RuntimeError(
                            "battery manager did not finish in ACTIVE mode"
                        )
                if require_charge and result["battery_total_charges"] < 1:
                    raise RuntimeError("episode did not force a charge")
            return result
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


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--robot-count", type=int, choices=range(1, 5), default=1
    )
    parser.add_argument("--world", default="my_world.world")
    parser.add_argument("--gazebo-seed", type=int, default=1)
    parser.add_argument("--goal-timeout", type=float, default=60.0)
    parser.add_argument("--spawn-timeout", type=float, default=90.0)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--message-timeout", type=float, default=30.0)
    parser.add_argument("--dwell-seconds", type=float, default=5.0)
    parser.add_argument("--shutdown-timeout", type=float, default=30.0)
    parser.add_argument("--evaluation-duration", type=float, default=0.0)
    parser.add_argument("--coverage-threshold", type=float, default=0.0)
    parser.add_argument("--target-detection", action="store_true")
    parser.add_argument("--expect-target-not-found", action="store_true")
    parser.add_argument("--target-x", type=float, default=-4.0)
    parser.add_argument("--target-y", type=float, default=4.0)
    parser.add_argument("--target-max-distance", type=float, default=3.0)
    parser.add_argument("--target-field-of-view", type=float, default=90.0)
    parser.add_argument("--target-confirmation-frames", type=int, default=3)
    parser.add_argument("--rally", action="store_true")
    parser.add_argument("--rally-position-tolerance", type=float, default=0.35)
    parser.add_argument("--rally-linear-tolerance", type=float, default=0.05)
    parser.add_argument("--rally-angular-tolerance", type=float, default=0.10)
    parser.add_argument("--rally-hold", type=float, default=5.0)
    parser.add_argument("--rally-max-retries", type=int, default=2)
    parser.add_argument(
        "--rally-assignment-objective",
        choices=("minimax", "total_path"),
        default="minimax",
    )
    parser.add_argument(
        "--disable-map-safe-rally-order", action="store_true"
    )
    parser.add_argument(
        "--disable-global-battery-rally-pause", action="store_true"
    )
    parser.add_argument("--rally-max-concurrent", type=int, default=1)
    parser.add_argument("--battery", action="store_true")
    parser.add_argument("--require-charge", action="store_true")
    parser.add_argument("--battery-capacity", type=float, default=60.0)
    parser.add_argument("--battery-initial-energy", type=float, default=24.0)
    parser.add_argument("--battery-move-cost", type=float, default=1.0)
    parser.add_argument("--battery-idle-cost", type=float, default=0.02)
    parser.add_argument("--battery-safety-margin", type=float, default=5.0)
    parser.add_argument("--battery-charge-duration", type=float, default=10.0)
    parser.add_argument("--battery-charge-radius", type=float, default=0.5)
    parser.add_argument(
        "--battery-charge-target-fraction", type=float, default=0.8
    )
    parser.add_argument("--battery-return-timeout", type=float, default=120.0)
    parser.add_argument("--battery-charge-timeout", type=float, default=60.0)
    parser.add_argument("--task-regions", action="store_true")
    parser.add_argument("--evaluation-wait-timeout", type=float, default=180.0)
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
    parser.add_argument("--bypass-audit-output", type=Path)
    parser.add_argument("--gateway-mode", choices=("ideal", "fault"), default="ideal")
    parser.add_argument("--mission-mode", choices=("coverage", "target", "rally"), default="coverage")
    parser.add_argument("--gateway-seed", type=int, default=1)
    parser.add_argument("--uplink-loss-rate", type=float, default=0.0)
    parser.add_argument("--downlink-loss-rate", type=float, default=0.0)
    parser.add_argument("--uplink-delay-sec", type=float, default=0.0)
    parser.add_argument("--downlink-delay-sec", type=float, default=0.0)
    parser.add_argument("--gateway-duplicate-rate", type=float, default=0.0)
    parser.add_argument("--gateway-reorder-window", type=int, default=0)
    parser.add_argument("--gateway-ack-timeout-sec", type=float, default=1.0)
    parser.add_argument("--gateway-max-retries", type=int, default=2)
    parser.add_argument("--gateway-queue-capacity", type=int, default=0)
    parser.add_argument("--gateway-ledger-path", type=Path)
    parser.add_argument("--message-freshness-timeout-sec", type=float, default=5.0)
    parser.add_argument("--navigation-command-deadline-sec", type=float, default=90.0)
    return parser.parse_args()


def main():
    args = parse_args()
    if shutil.which("ros2") is None or "ROS_DISTRO" not in os.environ:
        raise SystemExit(
            "source /opt/ros/humble/setup.bash and install/setup.bash first"
        )
    if args.target_detection and args.evaluation_duration <= 0:
        raise SystemExit("--target-detection requires --evaluation-duration")
    if args.expect_target_not_found and not args.target_detection:
        raise SystemExit("--expect-target-not-found requires --target-detection")
    if args.rally and not args.target_detection:
        raise SystemExit("--rally requires --target-detection")
    if args.target_detection and args.coverage_threshold > 0:
        raise SystemExit(
            "--target-detection and --rally modes require "
            "--coverage-threshold 0"
        )
    if args.rally and args.expect_target_not_found:
        raise SystemExit("--rally cannot expect an invisible target")
    if args.rally_max_concurrent < 1:
        raise SystemExit("--rally-max-concurrent must be positive")
    if args.battery and args.evaluation_duration <= 0:
        raise SystemExit("--battery requires --evaluation-duration")
    if args.require_charge and not args.battery:
        raise SystemExit("--require-charge requires --battery")
    for name in ("uplink_loss_rate", "downlink_loss_rate", "gateway_duplicate_rate"):
        if not 0.0 <= getattr(args, name) <= 1.0:
            raise SystemExit(f"--{name.replace('_', '-')} must be in [0, 1]")
    if args.uplink_delay_sec < 0 or args.downlink_delay_sec < 0:
        raise SystemExit("gateway delays must be non-negative")
    if args.gateway_reorder_window < 0 or args.gateway_max_retries < 0:
        raise SystemExit("gateway reorder window and retries must be non-negative")
    if args.gateway_queue_capacity < 0:
        raise SystemExit("gateway queue capacity must be non-negative")
    mission_mode = args.mission_mode
    inferred_mode = "rally" if args.rally else (
        "target" if args.target_detection else "coverage"
    )
    if mission_mode == "coverage" and inferred_mode != "coverage":
        mission_mode = inferred_mode
    elif mission_mode != inferred_mode and inferred_mode != "coverage":
        raise SystemExit(
            "mission mode must match target/rally smoke termination semantics"
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
        f"enable_task_regions:={str(args.task_regions).lower()}",
        "enable_status_panel:=false",
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
        f"enable_target_detection:={str(args.target_detection).lower()}",
        f"enable_rally:={str(args.rally).lower()}",
        "evaluation_stop_on_target_found:="
        f"{str(args.target_detection and not args.rally).lower()}",
        f"evaluation_stop_on_task_complete:={str(args.rally).lower()}",
        f"target_x:={args.target_x}",
        f"target_y:={args.target_y}",
        f"target_max_distance_m:={args.target_max_distance}",
        f"target_field_of_view_deg:={args.target_field_of_view}",
        f"target_confirmation_frames:={args.target_confirmation_frames}",
        f"rally_position_tolerance_m:={args.rally_position_tolerance}",
        f"rally_linear_tolerance_mps:={args.rally_linear_tolerance}",
        f"rally_angular_tolerance_radps:={args.rally_angular_tolerance}",
        f"rally_hold_sec:={args.rally_hold}",
        f"rally_max_retries:={args.rally_max_retries}",
        f"rally_assignment_objective:={args.rally_assignment_objective}",
        "use_map_safe_rally_order:="
        f"{str(not args.disable_map_safe_rally_order).lower()}",
        "global_battery_rally_pause:="
        f"{str(not args.disable_global_battery_rally_pause).lower()}",
        f"rally_max_concurrent:={args.rally_max_concurrent}",
        f"enable_battery:={str(args.battery).lower()}",
        f"battery_capacity:={args.battery_capacity}",
        f"battery_initial_energy:={args.battery_initial_energy}",
        f"battery_move_cost_per_m:={args.battery_move_cost}",
        f"battery_idle_cost_per_sec:={args.battery_idle_cost}",
        f"battery_return_safety_margin:={args.battery_safety_margin}",
        f"battery_charge_duration_sec:={args.battery_charge_duration}",
        f"battery_charge_radius_m:={args.battery_charge_radius}",
        "battery_charge_target_fraction:="
        f"{args.battery_charge_target_fraction}",
        f"battery_return_timeout_sec:={args.battery_return_timeout}",
        f"battery_charge_timeout_sec:={args.battery_charge_timeout}",
        f"gateway_mode:={args.gateway_mode}",
        f"mission_mode:={mission_mode}",
        f"gateway_seed:={args.gateway_seed}",
        f"uplink_loss_rate:={args.uplink_loss_rate}",
        f"downlink_loss_rate:={args.downlink_loss_rate}",
        f"uplink_delay_sec:={args.uplink_delay_sec}",
        f"downlink_delay_sec:={args.downlink_delay_sec}",
        f"gateway_duplicate_rate:={args.gateway_duplicate_rate}",
        f"gateway_reorder_window:={args.gateway_reorder_window}",
        f"gateway_ack_timeout_sec:={args.gateway_ack_timeout_sec}",
        f"gateway_max_retries:={args.gateway_max_retries}",
        f"gateway_queue_capacity:={args.gateway_queue_capacity}",
        f"message_freshness_timeout_sec:={args.message_freshness_timeout_sec}",
        f"navigation_command_deadline_sec:={args.navigation_command_deadline_sec}",
    ]
    if args.gateway_ledger_path is not None:
        command.append(f"gateway_ledger_path:={args.gateway_ledger_path}")

    print("Command:", " ".join(command), flush=True)
    print("Launch log:", log_path, flush=True)
    launch_environment = os.environ.copy()
    launch_environment["PATH"] = os.pathsep.join(
        ("/usr/bin", "/bin", launch_environment["PATH"])
    )
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
            env=launch_environment,
        )
        try:
            wait_until_ready(
                process,
                args.robot_count,
                args.startup_timeout,
                evaluation_enabled=args.evaluation_duration > 0,
                target_detection_enabled=args.target_detection,
                battery_enabled=args.battery,
            )
            print("ROS graph and Nav2 lifecycle nodes are ready.", flush=True)
            require_bypass_audit(
                args.robot_count,
                args.message_timeout,
                args.bypass_audit_output,
            )
            print("P3A forbidden-bypass audit passed.", flush=True)
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
            if args.battery:
                for index in range(1, args.robot_count + 1):
                    require_message(
                        f"/tb{index}/battery_state",
                        args.message_timeout,
                        (
                            "--qos-reliability",
                            "reliable",
                            "--qos-durability",
                            "transient_local",
                        ),
                    )
            if args.task_regions:
                regions = [
                    "task_region_start_charge",
                    *(
                        f"task_region_charger_tb{index}"
                        for index in range(1, args.robot_count + 1)
                    ),
                ]
                if args.target_detection:
                    regions.append("task_region_target_detection")
                require_entities(regions, args.message_timeout)
            print("Received lidar and merged-map messages.", flush=True)
            if args.evaluation_duration > 0:
                result_path = args.evaluation_output_dir / f"{episode_id}.json"
                result = wait_for_evaluation(
                    process,
                    result_path,
                    log_path,
                    args.evaluation_wait_timeout,
                    args.coverage_threshold,
                    args.target_detection,
                    not args.expect_target_not_found,
                    args.rally,
                    args.battery,
                    args.require_charge,
                )
                print(
                    "Evaluation result:",
                    result_path,
                    f"coverage={result['correct_free_coverage_ratio']:.3f}",
                    f"path={result['total_path_length_m']:.3f}m",
                    f"termination={result['termination_reason']}",
                    f"detection={result['time_to_detect_sec']}",
                    f"rally={result['time_to_rally_sec']}",
                    f"completion={result['completion_time_sec']}",
                    f"charges={result['battery_total_charges']}",
                    flush=True,
                )
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
