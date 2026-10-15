#!/usr/bin/env python3
"""System-Python ROS worker behind private learner pipes; never a policy."""

import argparse
import ctypes
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from ros_smoke_test import configure_mr3_transport_environment, native_launch_failures


ROS_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROS_ROOT.parents[1]
LEARNER = (WORKSPACE / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/"
           "wireless-rl/mr3_learning")
spec = importlib.util.spec_from_file_location("mr3_pipe_protocol", LEARNER / "ipc.py")
ipc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipc)


class Worker:
    """Coordinate real physical steps, delivered observations and isolated reward."""

    def __init__(self, directory, request):
        self.directory = directory
        self.epoch = request["epoch"]
        self.scene = request["scene"]
        self.seed = request["seed"]
        if self.scene not in ("open", "rooms", "corridors") or type(self.seed) is not int:
            raise ValueError("invalid scene or seed")
        if request.get("quantum_steps") != 20:
            raise ValueError("scheduler requires 20 physical ticks per quantum")
        self.condition = threading.Condition()
        self.clock_ns = 0
        self.monitor_ready = False
        self.snapshots = {}
        self.drains = {}
        self.rewards = {}
        self.finalize_ack = None
        self.events = []
        self.failures = []
        self.closed = None
        self.reward_ready = None
        self.callback_error = None
        self.snapshot_number = 0
        self.reward_number = 0
        self.command_number = 0
        self.physics_number = 0
        self.snapshot = None
        self.watermarks = {}
        self.finished = False
        self.launch = None
        self.helper = None
        self.outputs = []
        self.last_native_check = 0.
        self.started_wall = time.monotonic()
        self.transition_file = (directory / "transitions.jsonl").open("x", buffering=1)
        self.physics_file = (directory / "physics.jsonl").open("x", buffering=1)
        self.transport_environment = configure_mr3_transport_environment()

        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from rosgraph_msgs.msg import Clock
        from std_msgs.msg import Bool, Header, String

        rclpy.init()
        self.rclpy = rclpy
        self.String = String
        self.Header = Header
        self.node = rclpy.create_node("mr3_environment_worker", parameter_overrides=[
            Parameter("use_sim_time", Parameter.Type.BOOL, True)])
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.snapshot_pub = self.node.create_publisher(String, "/mr3/snapshot_request", 10)
        self.drain_pub = self.node.create_publisher(String, "/mr3/information_drain_request", 10)
        self.action_pub = self.node.create_publisher(String, "/mr3/action", 10)
        self.reward_pub = self.node.create_publisher(String, "/mr3/reward_request", 10)
        self.finalize_pub = self.node.create_publisher(String, "/mr3/training_finalize", 10)
        self.stop_pub = self.node.create_publisher(Header, "/exploration_stop_request", qos)

        def callback(function):
            def wrapped(message):
                try:
                    with self.condition:
                        function(message)
                        self.condition.notify_all()
                except Exception as error:
                    self.callback_error = repr(error)
            return wrapped

        def message_json(message):
            value = json.loads(message.data)
            if value.get("epoch") != self.epoch:
                return None
            return value

        def snapshot_response(message):
            value = message_json(message)
            if value:
                self.snapshots[value["request_id"]] = value

        def drain_response(message):
            value = message_json(message)
            if value:
                self.drains[value["request_id"]] = value

        def reward_response(message):
            value = message_json(message)
            if value:
                if "sequence" in value:
                    self.rewards[value["sequence"]] = value
                else:
                    self.finalize_ack = value

        def event(message):
            value = message_json(message)
            if value:
                self.events.append(value)

        def stopped(message):
            value = json.loads(message.data)
            if (value.get("epoch") == self.epoch
                    and value.get("robot_names") == ["tb1", "tb2", "tb3"]):
                self.closed = value

        def ready(message):
            value = message_json(message)
            if value:
                self.reward_ready = value

        def clock(message):
            self.clock_ns = message.clock.sec * 10**9 + message.clock.nanosec

        def monitor(message):
            self.monitor_ready = bool(message.data)

        def failure(message):
            self.failures.append(message.data)

        self.subscriptions = [
            self.node.create_subscription(
                Clock, "/clock", callback(clock),
                QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT)),
            self.node.create_subscription(Bool, "/task_monitor_ready", callback(monitor), qos),
            self.node.create_subscription(String, "/mr3/snapshot_response",
                                          callback(snapshot_response), 10),
            self.node.create_subscription(String, "/mr3/information_drained",
                                          callback(drain_response), 10),
            self.node.create_subscription(String, "/mr3/reward_response",
                                          callback(reward_response), 10),
            self.node.create_subscription(String, "/mr3/reward_ready", callback(ready), qos),
            self.node.create_subscription(String, "/mr3/events", callback(event), 100),
            self.node.create_subscription(String, "/exploration_stopped", callback(stopped), qos),
            self.node.create_subscription(String, "/exploration_failure", callback(failure), qos),
        ]
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)

        def spin():
            try:
                self.executor.spin()
            except Exception as error:
                self.callback_error = repr(error)

        self.spin_thread = threading.Thread(target=spin, name="mr3_worker_ros", daemon=True)
        self.spin_thread.start()
        self.command = [
            "ros2", "launch", "multi_robot", "gazebo_multirobot_mapping_with_nav2.launch.py",
            "execution_mode:=adapter", "mr3_stepped:=true", "training_reward_enabled:=true",
            "robot_count:=3", f"mr3_episode_epoch:={self.epoch}",
            f"mr3_audit_path:={directory / 'adapter.jsonl'}",
            f"world:=p1c_{self.scene}.world", f"gazebo_seed:={self.seed}",
            "enable_gzclient:=false", "enable_rviz:=false", "enable_merge_rviz:=false",
            "auto_save_map:=false", "enable_task_evaluator:=true",
            "evaluation_contract_path:=" + str(
                ROS_ROOT / f"src/multi_robot/config/mr3_p1a/{self.scene}.json"),
            f"evaluation_episode_id:={self.epoch}", f"evaluation_output_dir:={directory}",
        ]
        metadata = {"schema": "mr3-p1c-worker-v1", "epoch": self.epoch,
                    "scene": self.scene, "seed": self.seed, "command": self.command,
                    "freeze": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
                    "transport_environment": self.transport_environment,
                    "environment": {key: os.environ.get(key) for key in (
                        "ROS_DOMAIN_ID", "GAZEBO_MASTER_URI", "PYTHONNOUSERSITE")},
                    "python": sys.executable, "quantum_steps": 20,
                    "physical_step_ns": 1000000, "policy_step_ns": 1000000000,
                    "startup_wall_guard_sec": 420., "closure_wall_guard_sec": 90.}
        (directory / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        output = (directory / "launch.log").open("w")
        self.outputs.append(output)
        self.launch = subprocess.Popen(self.command, cwd=ROS_ROOT, stdout=output,
                                       stderr=subprocess.STDOUT)

    def _healthy(self):
        if self.callback_error:
            raise RuntimeError("ROS callback failed: " + self.callback_error)
        if time.monotonic() - self.last_native_check > .2:
            self.last_native_check = time.monotonic()
            failures = native_launch_failures(
                (self.directory / "launch.log").read_text(errors="replace"))
            if failures:
                raise RuntimeError("native child failure: " + failures[0])
        if self.launch.poll() is not None and not self.finished:
            raise RuntimeError("launch exited before episode shutdown")

    def _wait(self, predicate, timeout, label):
        deadline = time.monotonic() + timeout
        while not predicate():
            self._healthy()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(label)
            with self.condition:
                self.condition.wait(min(.02, remaining))

    def _publish(self, publisher, payload):
        publisher.publish(self.String(data=json.dumps(payload, allow_nan=False)))

    def _physics(self, steps, wait_clock=True):
        self.physics_number += 1
        request_id = f"q{self.physics_number}"
        self.helper_peer.send({"request_id": request_id, "steps": steps, "epoch": self.epoch})
        receipt = self.helper_peer.receive(15.)
        if receipt.get("ok") is not True or receipt.get("request_id") != request_id:
            raise RuntimeError("physical step rejected: " + json.dumps(receipt))
        if (receipt.get("epoch") != self.epoch or receipt.get("paused") is not True
                or receipt["end_iterations"] - receipt["start_iterations"] != steps
                or receipt["end_time_ns"] - receipt["start_time_ns"] != steps * 1000000):
            raise RuntimeError("physical iteration/time receipt mismatch")
        self.physics_file.write(json.dumps(receipt, sort_keys=True) + "\n")
        if wait_clock:
            self._wait(lambda: self.clock_ns >= receipt["end_time_ns"], 10.,
                       "ROS /clock did not reach the paused physical boundary")
            if self.clock_ns != receipt["end_time_ns"]:
                raise RuntimeError("ROS /clock advanced beyond the paused physical boundary")
        self.physical_ns = receipt["end_time_ns"]
        return receipt

    def _snapshot(self, allow_terminal=False):
        from multi_robot_exploration.mr3_observation import snapshot_digest
        self.snapshot_number += 1
        request_id = f"s{self.snapshot_number}"
        self._publish(self.drain_pub, {
            "epoch": self.epoch, "request_id": request_id, "target_time_ns": self.physical_ns})
        self._wait(lambda: request_id in self.drains, 30., "information drain guard expired")
        drained = self.drains.pop(request_id)
        if drained.get("ok") is not True:
            raise RuntimeError("information pipeline failed to drain: " + json.dumps(drained))
        minimum_state_sequence = drained["state_sequence"] - 1
        if not allow_terminal:
            minimum_state_sequence = max(
                minimum_state_sequence, self.watermarks.get("state_sequence", -1))
        payload = {"epoch": self.epoch, "request_id": request_id,
                   "target_time_ns": self.physical_ns, "allow_terminal": allow_terminal,
                   "expected_map_sha256": drained["map_payload_sha256"],
                   "minimum_state_sequence": minimum_state_sequence}
        self._publish(self.snapshot_pub, payload)
        self._wait(lambda: request_id in self.snapshots, 30., "snapshot watermark guard expired")
        response = self.snapshots.pop(request_id)
        if response.get("ok") is not True:
            raise RuntimeError("snapshot failed: " + json.dumps(response))
        snapshot = response["snapshot"]
        if (snapshot["epoch"] != self.epoch or snapshot_digest(snapshot) != snapshot["digest"]
                or abs(snapshot["source_stamp"] - self.physical_ns / 1e9) > 1e-8):
            raise RuntimeError("snapshot did not describe the frozen physical boundary")
        self.snapshot = snapshot
        self.watermarks = response["watermarks"]
        if self.watermarks["state_sequence"] < drained["state_sequence"]:
            raise RuntimeError("snapshot state is older than the information drain watermark")
        return snapshot

    def _reward(self, start, end, truncation=None, initialize=False):
        sequence = 0 if initialize else self.reward_number + 1
        payload = {"epoch": self.epoch, "sequence": sequence,
                   "step_start": start, "step_end": end,
                   "expected_map_sha256": self.watermarks["map_payload_sha256"]}
        if truncation:
            payload["external_truncation"] = truncation
        self._publish(self.reward_pub, payload)
        self._wait(lambda: sequence in self.rewards, 30., "isolated reward response guard expired")
        response = self.rewards.pop(sequence)
        if response.get("ok", True) is not True or "error" in response:
            raise RuntimeError("reward rejected: " + json.dumps(response))
        if not initialize:
            self.reward_number = sequence
        return response

    def _evaluation(self):
        path = self.directory / (self.epoch + ".json")
        return json.loads(path.read_text()) if path.exists() else None

    def reset(self):
        self._wait(lambda: self.monitor_ready and any(
            name == "mr3_adapter" for name, _ in self.node.get_node_names_and_namespaces()),
            400., "three-robot startup/monitor guard expired")
        output = (self.directory / "step_helper.log").open("w")
        self.outputs.append(output)
        self.helper = subprocess.Popen([
            "ros2", "run", "multi_robot", "mr3_gazebo_step", "--jsonl", "--world",
            f"p1c_{self.scene}", "--epoch", self.epoch, "--timeout-sec", "10"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=output)
        self.helper_peer = ipc.JsonLinePeer(self.helper.stdout.fileno(), self.helper.stdin.fileno())
        receipt = self._physics(0, wait_clock=False)
        # Match the actual clock publisher phase before task release. These
        # are real warmup ticks, never counted as policy transition time.
        for _ in range(50):
            deadline = time.monotonic() + .1
            while self.clock_ns < self.physical_ns and time.monotonic() < deadline:
                with self.condition:
                    self.condition.wait(.005)
            if self.clock_ns == self.physical_ns:
                break
            if self.clock_ns > self.physical_ns:
                raise RuntimeError("clock/physics mismatch during initial phase alignment")
            self._physics(1, wait_clock=False)
        else:
            raise RuntimeError("could not align the real /clock phase before release")
        self._snapshot()
        self.start_ns = self.physical_ns
        self._wait(lambda: self.reward_ready is not None, 10.,
                   "evaluator did not acknowledge the task release")
        if abs(self.reward_ready["start_sim_time"] - self.start_ns / 1e9) > 1e-8:
            raise RuntimeError("reward epoch start differs from the frozen initial snapshot")
        response = self._reward(self.start_ns / 1e9, self.start_ns / 1e9, initialize=True)
        if response.get("reward") != 0 or response.get("terminated") or response.get("truncated"):
            raise RuntimeError("reward reset did not initialize an empty episode ledger")
        result = {"snapshot": self.snapshot, "reward": 0., "terminated": False,
                  "truncated": False, "info": {
                      "epoch": self.epoch, "scene": self.scene, "seed": self.seed,
                      "startup_wall_sec": time.monotonic() - self.started_wall,
                      "reset_kind": "complete_process_rebuild", "dt": 0.,
                      "reward_diagnostics": response,
                      "scheduler": "mr3-physical-20ms-v1", "watermarks": self.watermarks,
                      "initial_pause_time_ns": receipt["end_time_ns"],
                      "release_time_ns": self.start_ns}}
        self.transition_file.write(json.dumps({"kind": "reset", **result}, sort_keys=True) + "\n")
        return result

    def step(self, action, external_truncation=None):
        if self.finished:
            raise RuntimeError("episode is already finalized")
        if type(action) is not int or not 0 <= action < 1000:
            raise ValueError("invalid discrete action")
        started_wall = time.monotonic()
        start_ns = self.physical_ns
        self.command_number += 1
        command = {"epoch": self.epoch, "command_id": self.command_number,
                   "observation_sequence": self.snapshot["sequence"],
                   "observation_digest": self.snapshot["digest"], "action": action,
                   "created_at": start_ns / 1e9, "expires_at": start_ns / 1e9 + 2.}
        event_index = len(self.events)
        self._publish(self.action_pub, command)

        def action_accounted():
            return any(row["kind"] in ("action", "action_rejected")
                       and row["payload"].get("command_id") == self.command_number
                       and row["payload"].get("observation_sequence") ==
                       command["observation_sequence"]
                       for row in self.events[event_index:])

        self._wait(action_accounted, 10., "adapter did not account for the explicit action")
        terminal = self._evaluation()
        while self.physical_ns < start_ns + 10**9 and terminal is None:
            self._physics(20)
            terminal = self._evaluation()
        self._snapshot(allow_terminal=terminal is not None)
        response = self._reward(start_ns / 1e9, self.physical_ns / 1e9,
                                truncation=external_truncation)
        terminated = bool(response["terminated"])
        truncated = bool(response["truncated"])
        if terminal is not None and not terminated:
            raise RuntimeError("evaluator terminal was not classified as terminated")
        if not terminated and self.physical_ns - start_ns != 10**9:
            raise RuntimeError("nonterminal policy transition is not exactly one physical second")
        effective_end = response.get("effective_step_end", self.physical_ns / 1e9)
        result = {"snapshot": self.snapshot, "reward": response["reward"],
                  "terminated": terminated, "truncated": truncated, "info": {
                      "epoch": self.epoch, "dt": effective_end - start_ns / 1e9,
                      "physical_dt": (self.physical_ns - start_ns) / 1e9,
                      "step_wall_sec": time.monotonic() - started_wall,
                      "reason": response.get("reason"), "reward_diagnostics": response,
                      "watermarks": self.watermarks, "command": command}}
        self.transition_file.write(json.dumps({"kind": "step", **result}, sort_keys=True) + "\n")
        if terminated or truncated:
            self.shutdown_episode("task_terminal" if terminated else "external_truncation")
        return result

    def truncate(self, reason):
        response = self._reward(self.physical_ns / 1e9, self.physical_ns / 1e9, truncation=reason)
        result = {"snapshot": self.snapshot, "reward": response["reward"],
                  "terminated": response["terminated"], "truncated": response["truncated"],
                  "info": {"epoch": self.epoch, "dt": 0., "reason": response.get("reason"),
                           "reward_diagnostics": response}}
        self.shutdown_episode("task_terminal" if response["terminated"] else "external_truncation")
        return result

    def shutdown_episode(self, reason):
        from run_mr3_adapter_probe import native_stop_receipt
        start = time.monotonic()
        request = self.Header()
        request.stamp.sec, request.stamp.nanosec = divmod(self.physical_ns, 10**9)
        request.frame_id = "map"
        self.stop_pub.publish(request)
        while self.closed is None:
            if time.monotonic() - start > 90.:
                raise TimeoutError("navigation ownership did not close within wall guard")
            self._physics(20)
        if self.closed["pending_goal_count"] != 0:
            raise RuntimeError("episode shutdown left unknown goal ownership")
        self.helper.stdin.close()
        self.helper.wait(timeout=10.)
        self.helper.stdout.close()
        if self.helper.returncode != 0:
            raise RuntimeError("physical step helper did not exit cleanly")
        self._publish(self.finalize_pub, {
            "epoch": self.epoch, "ack_sequence": self.reward_number, "reason": reason})
        self.launch.wait(timeout=45.)
        launch_text = (self.directory / "launch.log").read_text(errors="replace")
        failures = native_launch_failures(launch_text)
        native_stop = native_stop_receipt(launch_text)
        (self.directory / "native_stop.json").write_text(json.dumps(native_stop, indent=2) + "\n")
        if failures or self.launch.returncode != 0:
            raise RuntimeError("native shutdown failed: " + repr(failures))
        if not self.finalize_ack or self.finalize_ack.get("kind") == "training_finalize_error":
            raise RuntimeError("evaluator finalization acknowledgement is missing or failed")
        self.finished = True
        self.summary = {"epoch": self.epoch, "scene": self.scene, "seed": self.seed,
                        "closed": self.closed, "reason": reason,
                        "transition_count": self.reward_number, "failures": self.failures,
                        "launch_returncode": self.launch.returncode, "native_failures": failures,
                        "cleanup_wall_sec": time.monotonic() - start,
                        "wall_duration_sec": time.monotonic() - self.started_wall}
        (self.directory / "summary.json").write_text(json.dumps(self.summary, indent=2) + "\n")

    def close(self):
        if not self.finished and self.snapshot is not None:
            self.truncate("external_environment_close")
        self.executor.shutdown(timeout_sec=2.)
        self.spin_thread.join(timeout=2.)
        self.node.destroy_node()
        self.rclpy.shutdown()
        for output in self.outputs:
            output.close()
        self.transition_file.close()
        self.physics_file.close()
        path = self.directory / "adapter.jsonl"
        if path.exists():
            raw = path.read_bytes()
            (self.directory / "adapter.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0))
            (self.directory / "adapter.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
        # Reap any owned orphaned descendants after the launch/helper have
        # already been waited, rather than accumulating zombies across reset.
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
            except ChildProcessError:
                break
        return getattr(self, "summary", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    # Keep a private copy of the response pipe; ROS and native stdout go to
    # the worker log, including C extensions that write directly to fd 1.
    response_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER, this worker only.
    peer = ipc.JsonLinePeer(sys.stdin.fileno(), response_fd)
    worker = None
    while True:
        try:
            request = peer.receive(86400.)
        except EOFError:
            if worker:
                worker.close()
            return 0
        try:
            if worker and request["epoch"] != worker.epoch:
                raise ValueError("IPC epoch mismatch")
            if request["op"] == "reset" and worker is None:
                worker = Worker(args.run_dir, request)
                result = worker.reset()
            elif request["op"] == "step" and worker:
                result = worker.step(request["action"], request.get("external_truncation"))
            elif request["op"] == "truncate" and worker:
                result = worker.truncate(request["reason"])
            elif request["op"] == "close" and worker:
                result = worker.close()
            else:
                raise ValueError("invalid worker operation")
            peer.send({"id": request["id"], "epoch": request["epoch"],
                       "ok": True, "result": result})
            if request["op"] == "close":
                return 0
        except Exception as error:
            (args.run_dir / "infrastructure_failure.json").write_text(json.dumps({
                "request": request, "error": repr(error),
                "scope": "invalid infrastructure sample, never a task success"}, indent=2) + "\n")
            peer.send({"id": request["id"], "epoch": request["epoch"],
                       "ok": False, "error": repr(error)})
            # Keep the recorded session leader alive until the parent has
            # enumerated and signalled its owned descendants. A hard crash is
            # handled separately by the parent's live ownership monitor.
            try:
                peer.receive(10.)
            except (EOFError, TimeoutError, OSError):
                pass
            return 1  # Parent owns the remaining process group and records forced cleanup.


if __name__ == "__main__":
    sys.exit(main())
