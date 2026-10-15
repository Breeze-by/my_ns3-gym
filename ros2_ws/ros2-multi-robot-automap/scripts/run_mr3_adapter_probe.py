#!/usr/bin/env python3
"""Bounded scripted P1B navigation probe, never an RL or 95% task evaluation."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from ros_smoke_test import configure_mr3_transport_environment, native_launch_failures


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=("open", "rooms", "corridors"), required=True)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "log/mr3_adapter")
    args = parser.parse_args()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not args.run_id or any(c not in allowed for c in args.run_id):
        parser.error("run-id must contain only letters, digits, underscores and hyphens")
    run = args.output_root / args.run_id
    run.mkdir(parents=True, exist_ok=False)
    transport_environment = configure_mr3_transport_environment()
    # Import ROS after applying the exact process discovery/transport profile.
    import rclpy
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import Header, String
    from multi_robot_exploration.mr3_observation import snapshot_digest

    freeze = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    command = [
        "ros2", "launch", "multi_robot", "gazebo_multirobot_mapping_with_nav2.launch.py",
        "execution_mode:=adapter", "robot_count:=3", f"mr3_episode_epoch:={args.run_id}",
        f"mr3_audit_path:={run / 'adapter.jsonl'}", f"world:=p1c_{args.scene}.world",
        f"gazebo_seed:={args.seed}", "enable_gzclient:=false", "enable_rviz:=false",
        "enable_merge_rviz:=false", "auto_save_map:=false", "enable_task_evaluator:=true",
        "evaluation_contract_path:=" + str(
            ROOT / "src/multi_robot/config/mr3_p1a" / (args.scene + ".json")),
        f"evaluation_episode_id:={args.run_id}", f"evaluation_output_dir:={run}",
    ]
    metadata = {"kind": "scripted_adapter_probe_not_rl_or_task_success", "freeze": freeze,
                "scene": args.scene, "seed": args.seed, "command": command,
                "transport_environment": transport_environment,
                "environment": {key: os.environ.get(key) for key in
                                ("ROS_DOMAIN_ID", "GAZEBO_MASTER_URI", "PYTHONNOUSERSITE")},
                "policy": "first lexicographic legal joint candidate action; KEEP; WAIT after10s; "
                          "new candidates after15s; deliberate stop after25s",
                "startup_wall_guard_sec": 420., "closure_wall_guard_sec": 90.}
    (run / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rclpy.init()
    node = rclpy.create_node("mr3_adapter_scripted_probe")
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    action_pub = node.create_publisher(String, "/mr3/action", 10)
    stop_pub = node.create_publisher(Header, "/exploration_stop_request", qos)
    state = {"snapshot": None, "closed": None, "failures": [], "events": [], "checked": 0}

    def observation(message):
        value = json.loads(message.data)
        if value["epoch"] != args.run_id:
            return
        if snapshot_digest(value) != value["digest"]:
            raise ValueError("saved observation digest mismatch")
        state["snapshot"] = value
        state["checked"] += 1

    node.probe_subscriptions = [
        node.create_subscription(String, "/mr3/observation", observation, 2),
        node.create_subscription(String, "/mr3/events", lambda msg: state["events"].append(
            json.loads(msg.data)), 100),
        node.create_subscription(String, "/exploration_stopped", lambda msg: state.update(
            closed=json.loads(msg.data)), qos),
        node.create_subscription(String, "/exploration_failure", lambda msg:
                                 state["failures"].append(msg.data), qos),
    ]
    started = time.monotonic()
    last_sequence = -1
    command_id = 0
    stop_wall = None
    probes_sent = False
    commitment_probe_sent = False
    run_error = None
    last_observation_wall = started
    observed_sequence = -1
    with (run / "launch.log").open("w") as output:
        process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            while process.poll() is None:
                rclpy.spin_once(node, timeout_sec=.1)
                snapshot = state["snapshot"]
                if time.monotonic() - started > 900.:
                    raise TimeoutError("overall wall guard expired")
                if snapshot is None:
                    if time.monotonic() - started > 420.:
                        raise TimeoutError("startup guard expired before observation")
                    continue
                if snapshot["sequence"] != observed_sequence:
                    observed_sequence = snapshot["sequence"]
                    last_observation_wall = time.monotonic()
                elif time.monotonic() - last_observation_wall > 90.:
                    raise TimeoutError("observation or simulation clock stopped progressing")
                # Probe clock uses the message's simulation time, not node wall time.
                now = snapshot["source_stamp"]
                elapsed = snapshot["task_elapsed_sec"]
                if state["failures"] or elapsed >= 25.:
                    if stop_wall is None:
                        request = Header()
                        request.stamp.sec = int(now)
                        request.stamp.nanosec = int((now - int(now)) * 1e9)
                        request.frame_id = "map"
                        stop_pub.publish(request)
                        stop_wall = time.monotonic()
                    if state["closed"]:
                        break
                    if time.monotonic() - stop_wall > 90.:
                        raise TimeoutError("owned navigation did not close")
                    continue
                if snapshot["sequence"] == last_sequence:
                    continue
                last_sequence = snapshot["sequence"]
                mask = snapshot["joint_action_mask"]
                if elapsed < 1.5 or elapsed >= 15.:
                    legal = [a for a, valid in enumerate(mask) if valid]
                    action = min(legal, key=lambda a: (
                        -sum(d < 8 for d in (a // 100, a // 10 % 10, a % 10)), a))
                elif elapsed >= 10.:
                    action = next((a for a in range(999, -1, -1) if mask[a]), 888)
                else:
                    action = 888
                command_id += 1
                payload = {"epoch": args.run_id, "observation_sequence": last_sequence,
                           "observation_digest": snapshot["digest"], "command_id": command_id,
                           "created_at": now, "expires_at": now + 2., "action": action}
                message = String()
                message.data = json.dumps(payload)
                action_pub.publish(message)
                if not commitment_probe_sent and 1.5 <= elapsed < 5. and not mask[999]:
                    invalid = String()
                    invalid.data = json.dumps({**payload, "command_id": command_id + 20000,
                                               "action": 999})
                    action_pub.publish(invalid)
                    commitment_probe_sent = True
                if not probes_sent:
                    action_pub.publish(message)  # same command ID must be idempotent
                    for edit in ({"epoch": "old-episode"}, {"expires_at": now - 1.}):
                        invalid = String()
                        invalid.data = json.dumps({
                            **payload, "command_id": command_id + 10000, **edit})
                        action_pub.publish(invalid)
                    probes_sent = True
        except Exception as error:
            run_error = repr(error)
        finally:
            # Stop only this launch's server via its isolated Gazebo master,
            # then signal its own process group. Keep all native exit records.
            if process.poll() is None:
                try:
                    result = subprocess.run([
                        "gz", "topic", "-p", "/gazebo/server/control", "-m", "stop: true",
                    ], capture_output=True, text=True, timeout=15.)
                    (run / "native_stop.json").write_text(json.dumps({
                        "returncode": result.returncode, "stdout": result.stdout,
                        "stderr": result.stderr,
                    }, indent=2) + "\n")
                    if result.returncode:
                        run_error = run_error or "native stop CLI failed"
                    time.sleep(2.)
                except Exception as error:
                    run_error = run_error or repr(error)
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=45.)
                except subprocess.TimeoutExpired:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10.)
                    except subprocess.TimeoutExpired:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=10.)
                    run_error = run_error or "owned launch required forced shutdown"
    native_errors = native_launch_failures((run / "launch.log").read_text(errors="replace"))
    if process.returncode or native_errors:
        run_error = run_error or "native launch/process exit failure"
    summary = {**metadata, "launch_returncode": process.returncode, "error": run_error,
               "native_failures": native_errors,
               "snapshots_verified": state["checked"], "closed": state["closed"],
               "failures": state["failures"], "event_count": len(state["events"]),
               "wall_duration_sec": time.monotonic() - started}
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (run / "events.json").write_text(json.dumps(state["events"], indent=2) + "\n")
    node.destroy_node()
    rclpy.shutdown()
    print(json.dumps(summary, indent=2))
    # Retain exact observation/protocol bytes compactly, with an integrity hash.
    audit = run / "adapter.jsonl"
    if audit.exists():
        raw = audit.read_bytes()
        (run / "adapter.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0))
        (run / "adapter.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    return 0 if not run_error and state["closed"] and not state["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
