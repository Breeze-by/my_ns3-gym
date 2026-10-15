#!/usr/bin/env python3
"""Isolated native physics/clock fixture; no robots, policy or mapping credit."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

from mr3_env_worker import ipc, ROS_ROOT, WORKSPACE
from ros_smoke_test import configure_mr3_transport_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scene", choices=("open", "rooms", "corridors"), default="open")
    parser.add_argument("--ros-domain-id", type=int, required=True)
    parser.add_argument("--gazebo-port", type=int, required=True)
    parser.add_argument("--output-root", type=Path, default=ROS_ROOT / "log/mr3_step_clock")
    args = parser.parse_args()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not args.run_id or any(char not in allowed for char in args.run_id):
        parser.error("run-id must contain only letters, digits, underscores and hyphens")
    if not 0 <= args.ros_domain_id <= 232 or not 1024 <= args.gazebo_port <= 65535:
        parser.error("invalid isolated ROS domain or Gazebo port")
    run = args.output_root / args.run_id
    run.mkdir(parents=True, exist_ok=False)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.gazebo_port)) == 0:
            raise RuntimeError("requested Gazebo master port is already in use")
    os.environ["ROS_DOMAIN_ID"] = str(args.ros_domain_id)
    os.environ["GAZEBO_MASTER_URI"] = f"http://127.0.0.1:{args.gazebo_port}"
    transport = configure_mr3_transport_environment()
    import rclpy
    from ament_index_python.packages import get_package_prefix, get_package_share_directory
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rosgraph_msgs.msg import Clock

    share = Path(get_package_share_directory("multi_robot"))
    plugin = Path(get_package_prefix("multi_robot")) / "lib/libmr3_gazebo_step.so"
    clock_parameters = share / "config/mr3_step_clock.yaml"
    command = ["gzserver", "--verbose", str(share / f"worlds/p1c_{args.scene}.world"),
               "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so",
               "-s", str(plugin), "--ros-args", "--params-file", str(clock_parameters), "--"]
    helper_command = ["ros2", "run", "multi_robot", "mr3_gazebo_step", "--jsonl", "--world",
                      f"p1c_{args.scene}", "--epoch", args.run_id, "--timeout-sec", "10"]
    metadata = {
        "scope": "isolated physics/clock fixture; no robot-count research or task credit",
        "freeze": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
        "server_command": command, "helper_command": helper_command,
        "ROS_DOMAIN_ID": args.ros_domain_id, "GAZEBO_MASTER_URI": os.environ["GAZEBO_MASTER_URI"],
        "transport_environment": transport, "expected_clock_hz": 50.,
        "physical_tick_ns": 1000000, "wall_guards_sec": {"startup": 45., "clock": 10.},
    }
    (run / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rclpy.init()
    node = rclpy.create_node("mr3_step_clock_fixture")
    clocks = []
    node.subscription = node.create_subscription(
        Clock, "/clock", lambda value: clocks.append(
            value.clock.sec * 10**9 + value.clock.nanosec),
        QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT))
    receipts = []
    error = None
    server = helper = stop_cli = None
    stop_receipt = None
    started = time.monotonic()

    def wait(predicate, timeout):
        deadline = time.monotonic() + timeout
        while not predicate():
            if server.poll() is not None:
                raise RuntimeError(f"owned gzserver exited early with {server.returncode}")
            if time.monotonic() >= deadline:
                raise TimeoutError("native clock fixture wall guard expired")
            rclpy.spin_once(node, timeout_sec=.01)

    with (run / "gzserver.log").open("x") as log, (run / "helper.log").open("x") as helper_log:
        server = subprocess.Popen(command, cwd=ROS_ROOT, stdout=log,
                                  stderr=subprocess.STDOUT, start_new_session=True)
        try:
            wait(lambda: clocks and clocks[-1] > 0, 45.)
            helper = subprocess.Popen(helper_command, cwd=ROS_ROOT, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=helper_log,
                                      start_new_session=True)
            peer = ipc.JsonLinePeer(helper.stdout.fileno(), helper.stdin.fileno())

            def step(count, require_clock):
                identity = f"q{len(receipts) + 1}"
                peer.send({"epoch": args.run_id, "request_id": identity, "steps": count})
                value = peer.receive(12.)
                if (value.get("ok") is not True or value.get("request_id") != identity
                        or value.get("epoch") != args.run_id or value.get("paused") is not True
                        or value["end_time_ns"] - value["start_time_ns"] != count * 1000000
                        or value["end_iterations"] - value["start_iterations"] != count):
                    raise RuntimeError("invalid owned physics receipt: " + json.dumps(value))
                if receipts and value["start_time_ns"] != receipts[-1]["end_time_ns"]:
                    raise RuntimeError("physics advanced outside an explicit fixture step")
                if require_clock:
                    wait(lambda: clocks and clocks[-1] >= value["end_time_ns"], 10.)
                    if clocks[-1] != value["end_time_ns"]:
                        raise RuntimeError("ROS clock differs from actual paused physics end")
                value["observed_ros_clock_ns"] = clocks[-1] if clocks else None
                value["clock_boundary_required"] = require_clock
                receipts.append(value)
                with (run / "physics.jsonl").open("a") as output:
                    output.write(json.dumps(value, sort_keys=True) + "\n")
                return value

            step(0, False)
            step(1, False)
            for _ in range(50):
                target = receipts[-1]["end_time_ns"]
                deadline = time.monotonic() + .1
                while (not clocks or clocks[-1] < target) and time.monotonic() < deadline:
                    rclpy.spin_once(node, timeout_sec=.005)
                if clocks[-1] == target:
                    break
                if clocks[-1] > target:
                    raise RuntimeError("clock led physics during real phase alignment")
                step(1, False)
            else:
                raise RuntimeError("50 Hz clock phase could not align to actual paused time")
            for _ in range(5):
                step(20, True)
            step(1000, True)
            step(0, True)
        except Exception as caught:
            error = repr(caught)
        finally:
            if helper is not None:
                try:
                    helper.stdin.close()
                    helper.wait(timeout=10.)
                    helper.stdout.close()
                    if helper.returncode:
                        error = error or f"helper exited with {helper.returncode}"
                except Exception as caught:
                    error = error or repr(caught)
                    if helper.poll() is None:
                        os.killpg(helper.pid, signal.SIGKILL)
                        helper.wait(timeout=10.)
            if server.poll() is None:
                try:
                    stop_command = ["gz", "topic", "-p", "/gazebo/server/control",
                                    "-m", "stop: true"]
                    with (run / "native_stop.log").open("x") as stop_log:
                        stop_cli = subprocess.Popen(stop_command, stdout=stop_log,
                                                    stderr=subprocess.STDOUT)
                        stop_cli.wait(timeout=15.)
                    server.wait(timeout=15.)
                    stop_receipt = {
                        "server_pid": server.pid, "server_command": command,
                        "server_returncode": server.returncode,
                        "stop_cli_pid": stop_cli.pid, "stop_cli_command": stop_command,
                        "stop_cli_returncode": stop_cli.returncode,
                    }
                    if stop_cli.returncode or server.returncode:
                        error = error or "native server/stop command did not both exit cleanly"
                except Exception as caught:
                    error = error or repr(caught)
                    if stop_cli is not None and stop_cli.poll() is None:
                        stop_cli.kill()
                        stop_cli.wait(timeout=5.)
            if server.poll() is None:
                error = error or "native server required forced cleanup"
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=10.)
    result = {**metadata, "passed": error is None and stop_receipt is not None,
              "error": error, "server_pid": server.pid, "server_returncode": server.returncode,
              "helper_pid": None if helper is None else helper.pid,
              "stop_cli_pid": None if stop_cli is None else stop_cli.pid,
              "stop_cli_returncode": None if stop_cli is None else stop_cli.returncode,
              "native_stop": stop_receipt, "receipt_count": len(receipts),
              "clock_sample_count": len(clocks), "clock_samples_ns": clocks,
              "wall_duration_sec": time.monotonic() - started}
    (run / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    node.destroy_node()
    rclpy.shutdown()
    print(json.dumps({"passed": result["passed"], "error": error, "run": str(run)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
