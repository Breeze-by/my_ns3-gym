#!/usr/bin/env python3
"""System-Python ROS worker behind private learner pipes; never a policy."""

import argparse
import ctypes
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from ros_smoke_test import configure_mr3_transport_environment, native_launch_failures
from multi_robot_exploration.mr3_evaluator_phase import (
    PHASE_PROTOCOL, PHASE_WALL_GUARD_SEC, PhaseClient,
)


ROS_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROS_ROOT.parents[1]
LEARNER = (WORKSPACE / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/"
           "wireless-rl/mr3_learning")
SHUTDOWN_PROTOCOL = "nav2-finalized_then_serial-ros_then_gazebo-v1"
NAV2_NODES = ("controller_server", "planner_server", "behavior_server",
              "bt_navigator", "waypoint_follower", "velocity_smoother")
NAV2_SHUTDOWN_WALL_GUARD_SEC = 30.
MOTION_OUTPUT_PUBLISHER = ("/", "motion_safety")
MOTION_PHASE_COMPLETION = "publication_and_local_topic_receipt"
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
        self.terminal_probe = request.get("terminal_probe", False)
        if type(self.terminal_probe) is not bool:
            raise ValueError("terminal_probe must be a boolean")
        self.probe_armed = False
        self.probe_number = 0
        self.task_terminal = None
        self.evaluator_phase = PhaseClient(self.epoch)
        self.condition = threading.Condition()
        self.clock_ns = 0
        self.monitor_ready = False
        self.motion_ready = False
        self.motion_status = None
        self.initial_inputs_ready = None
        self.snapshots = {}
        self.drains = {}
        self.rewards = {}
        self.finalize_ack = None
        self.events = []
        self.failures = []
        self.closed = None
        self.closed_received_clock_ns = None
        self.closed_received_wall_monotonic_ns = None
        self.nav2_shutdown_clients = []
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
        self.execution_map_digests = set()
        self.execution_costmap_file = (directory / "costmaps.jsonl").open("x", buffering=1)
        self.outputs.append(self.execution_costmap_file)
        self.last_native_check = 0.
        self.started_wall = time.monotonic()
        self.transition_file = (directory / "transitions.jsonl").open("x", buffering=1)
        self.physics_file = (directory / "physics.jsonl").open("x", buffering=1)
        self.evaluator_phase_file = (directory / "evaluator_phase_worker.jsonl").open(
            "x", buffering=1)
        self.motion_phase_file = (directory / "motion_phase_worker.jsonl").open("x", buffering=1)
        self.transport_environment = configure_mr3_transport_environment()

        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from rosgraph_msgs.msg import Clock
        from std_msgs.msg import Bool, Header, String
        from lifecycle_msgs.srv import GetState
        from nav2_msgs.srv import ManageLifecycleNodes
        from nav_msgs.msg import OccupancyGrid
        from multi_robot_exploration.mr3_information import map_payload

        rclpy.init()
        self.rclpy = rclpy
        self.String = String
        self.Header = Header
        self.GetState = GetState
        self.ManageLifecycleNodes = ManageLifecycleNodes
        self.map_payload = map_payload
        self.node = rclpy.create_node("mr3_environment_worker", parameter_overrides=[
            Parameter("use_sim_time", Parameter.Type.BOOL, True)])
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.snapshot_pub = self.node.create_publisher(String, "/mr3/snapshot_request", 10)
        self.drain_pub = self.node.create_publisher(String, "/mr3/information_drain_request", 10)
        self.action_pub = self.node.create_publisher(String, "/mr3/action", 10)
        self.reward_pub = self.node.create_publisher(String, "/mr3/reward_request", 10)
        self.finalize_pub = self.node.create_publisher(String, "/mr3/training_finalize", 10)
        self.evaluator_phase_pub = self.node.create_publisher(
            String, "/mr3/evaluator_phase_request", 10)
        self.probe_pub = (self.node.create_publisher(String, "/mr3/diagnostic_failure", 10)
                          if self.terminal_probe else None)
        self.stop_pub = self.node.create_publisher(Header, "/exploration_stop_request", qos)

        def callback(function):
            def wrapped(message):
                with self.condition:
                    try:
                        function(message)
                    except Exception as error:
                        self.callback_error = repr(error)
                    finally:
                        self.condition.notify_all()
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
                self.closed_received_clock_ns = self.clock_ns
                self.closed_received_wall_monotonic_ns = time.monotonic_ns()

        def ready(message):
            value = message_json(message)
            if value:
                self.reward_ready = value

        def initial_inputs(message):
            value = message_json(message)
            if value:
                self.receive_initial_inputs(value)

        def task_terminal(message):
            value = message_json(message)
            if value:
                self.receive_terminal(value)

        def evaluator_phase(message):
            value = json.loads(message.data)
            self._trace_evaluator_phase("ack_received", ack=value)
            self.evaluator_phase.receive(value, self.physical_ns, self.clock_ns)

        def clock(message):
            self.clock_ns = message.clock.sec * 10**9 + message.clock.nanosec

        def monitor(message):
            self.monitor_ready = bool(message.data)

        def motion_ready(message):
            self.motion_ready = bool(message.data)

        def motion_status(message):
            self.receive_motion_status(json.loads(message.data))

        def failure(message):
            self.failures.append(message.data)

        self.subscriptions = [
            self.node.create_subscription(
                Clock, "/clock", callback(clock),
                QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT)),
            self.node.create_subscription(Bool, "/task_monitor_ready", callback(monitor), qos),
            self.node.create_subscription(Bool, "/motion_safety/ready",
                                          callback(motion_ready), qos),
            self.node.create_subscription(String, "/motion_safety/status",
                                          callback(motion_status), qos),
            self.node.create_subscription(String, "/mr3/snapshot_response",
                                          callback(snapshot_response), 10),
            self.node.create_subscription(String, "/mr3/information_drained",
                                          callback(drain_response), 10),
            self.node.create_subscription(String, "/mr3/reward_response",
                                          callback(reward_response), 10),
            self.node.create_subscription(String, "/mr3/reward_ready", callback(ready), qos),
            self.node.create_subscription(String, "/mr3/initial_inputs_ready",
                                          callback(initial_inputs), qos),
            self.node.create_subscription(String, "/mr3/task_terminal",
                                          callback(task_terminal), qos),
            self.node.create_subscription(String, "/mr3/evaluator_phase_ack",
                                          callback(evaluator_phase), 10),
            self.node.create_subscription(String, "/mr3/events", callback(event), 100),
            self.node.create_subscription(String, "/exploration_stopped", callback(stopped), qos),
            self.node.create_subscription(String, "/exploration_failure", callback(failure), qos),
        ]
        for name in ("tb1", "tb2", "tb3"):
            for layer in ("global", "local"):
                self.subscriptions.append(self.node.create_subscription(
                    OccupancyGrid, f"/{name}/{layer}_costmap/costmap",
                    callback(lambda grid, name=name, layer=layer:
                             self.record_costmap(name, layer, grid)),
                    QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                               reliability=ReliabilityPolicy.RELIABLE)))
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)

        def spin():
            try:
                self.executor.spin()
            except Exception as error:
                with self.condition:
                    self.callback_error = repr(error)
                    self.condition.notify_all()

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
        if self.terminal_probe:
            self.command.append("training_terminal_probe:=true")
        metadata = {"schema": "mr3-p1c-worker-v1", "epoch": self.epoch,
                    "scene": self.scene, "seed": self.seed, "command": self.command,
                    "freeze": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
                    "transport_environment": self.transport_environment,
                    "environment": {key: os.environ.get(key) for key in (
                        "ROS_DOMAIN_ID", "GAZEBO_MASTER_URI", "PYTHONNOUSERSITE")},
                    "python": sys.executable, "quantum_steps": 20,
                    "reset_handshake": "delivered_inputs_before_pause-v1",
                    "terminal_protocol": "mr3-task-terminal-v1",
                    "evaluator_phase_protocol": PHASE_PROTOCOL,
                    "evaluator_phase_wall_guard_sec": PHASE_WALL_GUARD_SEC,
                    "shutdown_protocol": SHUTDOWN_PROTOCOL,
                    "nav2_shutdown_wall_guard_sec": NAV2_SHUTDOWN_WALL_GUARD_SEC,
                    "terminal_probe": self.terminal_probe,
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

    def _trace_evaluator_phase(self, kind, **payload):
        with self.condition:
            self.evaluator_phase_file.write(json.dumps({
                "kind": kind, "epoch": self.epoch, "wall_monotonic_ns": time.monotonic_ns(),
                "worker_clock_ns": self.clock_ns,
                "worker_physical_ns": getattr(self, "physical_ns", None), **payload,
            }, sort_keys=True, allow_nan=False) + "\n")

    def _evaluator_phase(self):
        """Wait paused for the evaluator's real clock and serialized frozen terminal."""
        with self.condition:
            request = self.evaluator_phase.begin(self.physical_ns)
            self._trace_evaluator_phase("request", request=request)
        self._publish(self.evaluator_phase_pub, request)
        self._wait(lambda: self.evaluator_phase.response is not None,
                   PHASE_WALL_GUARD_SEC, "evaluator phase ACK wall guard expired")
        with self.condition:
            if self.callback_error:
                raise RuntimeError("ROS callback failed: " + self.callback_error)
            response = self.evaluator_phase.consume()
            self._trace_evaluator_phase("ack_consumed", ack=response)
            if response["terminal"] is not None:
                self.receive_terminal(response["terminal"])
        return response

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
        if wait_clock:
            self.wait_motion_phase()
        return receipt

    def receive_motion_status(self, value):
        """Receive a real gate-executor completion, never synthesize its clock."""
        if value.get("epoch") != self.epoch:
            return
        sequences = value.get("decision_sequences")
        if (value.get("schema") != "mr3-motion-safety-status-v1"
                or value.get("completion_scope") != MOTION_PHASE_COMPLETION
                or type(value.get("clock_ns")) is not int or value["clock_ns"] < 0
                or type(value.get("ready")) is not bool or not isinstance(sequences, dict)
                or set(sequences) != {"tb1", "tb2", "tb3"}
                or any(type(sequence) is not int or sequence <= 0
                       for sequence in sequences.values())):
            raise ValueError("invalid motion gate phase status")
        previous = self.motion_status
        if previous is not None:
            if value["clock_ns"] < previous["clock_ns"]:
                raise ValueError("motion gate phase clock regressed")
            if any(sequences[name] < previous["decision_sequences"][name]
                   for name in sequences):
                raise ValueError("motion gate phase sequence regressed")
            if (value["clock_ns"] > previous["clock_ns"]
                    and any(sequences[name] <= previous["decision_sequences"][name]
                            for name in sequences)):
                raise ValueError("motion gate clock advanced without new decisions")
            if value["clock_ns"] == previous["clock_ns"] and value != previous:
                raise ValueError("motion gate phase changed within one clock")
        self.motion_status = value
        self.motion_phase_file.write(json.dumps({
            "kind": "ack_received", "epoch": self.epoch, "ack": value,
            "worker_clock_ns": self.clock_ns,
            "worker_physical_ns": getattr(self, "physical_ns", None),
            "wall_monotonic_ns": time.monotonic_ns(),
        }, sort_keys=True) + "\n")

    def wait_motion_phase(self):
        """Hold physical pause until this exact clock's three decisions complete.

        This proves gate output publication, not Gazebo actuator consumption.
        The latter remains checked through native measured motion traces.
        """
        target = self.physical_ns
        self._wait(lambda: self.motion_status is not None
                   and self.motion_status["clock_ns"] >= target, 10.,
                   "motion gate exact-clock phase wall guard expired")
        ack = self.motion_status
        if ack["clock_ns"] != target or self.clock_ns != target:
            raise RuntimeError("motion gate advanced beyond the paused physical boundary")
        self.motion_phase_file.write(json.dumps({
            "kind": "ack_consumed", "epoch": self.epoch, "ack": ack,
            "worker_clock_ns": self.clock_ns, "worker_physical_ns": target,
            "wall_monotonic_ns": time.monotonic_ns(),
        }, sort_keys=True) + "\n")
        return ack

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

    def receive_terminal(self, value):
        """Only the isolated evaluator may announce the frozen task boundary."""
        if value.get("epoch") != self.epoch:
            return
        end = value.get("end_sim_time_sec")
        reason = value.get("termination_reason")
        if (set(value) != {"epoch", "end_sim_time_sec", "termination_reason"}
                or type(end) not in (int, float) or not math.isfinite(end) or end < 0
                or not isinstance(reason, str) or not reason
                or reason in ("training_external_truncation", "shutdown", "no_data")):
            raise ValueError("invalid evaluator terminal notice")
        if self.task_terminal is not None and self.task_terminal != value:
            raise ValueError("evaluator terminal boundary changed")
        self.task_terminal = value

    def _evaluation(self):
        notice = self.task_terminal
        if (notice is not None
                and round(notice["end_sim_time_sec"] * 1e9)
                <= min(getattr(self, "physical_ns", -1), self.clock_ns)):
            return notice
        return None

    def arm_failure_probe(self):
        if not self.terminal_probe or self.finished or self.snapshot is None or self.probe_armed:
            raise ValueError("failure probe is disabled, unavailable or already armed")
        self.probe_armed = True
        return {"epoch": self.epoch, "armed": True}

    def trigger_failure_probe(self):
        if not self.terminal_probe or self.finished or self.snapshot is None or self._evaluation():
            raise ValueError("failure probe is disabled or unavailable")
        self.probe_number += 1
        request = {"epoch": self.epoch, "request_id": f"failure{self.probe_number}",
                   "target_time_ns": self.physical_ns, "reason": "P1C_DIAGNOSTIC_FAILURE"}
        path = self.directory / "diagnostic_failure.jsonl"
        with path.open("a") as output:
            output.write(json.dumps({"kind": "sent", **request}) + "\n")
        self._publish(self.probe_pub, request)
        self._wait(lambda: self._evaluation() is not None, 30.,
                   "diagnostic failure did not produce a causal evaluator terminal")
        notice = self._evaluation()
        if (round(notice["end_sim_time_sec"] * 1e9) != self.physical_ns
                or notice["termination_reason"] != "navigation_failure"):
            raise RuntimeError("diagnostic failure did not freeze at the requested clock")
        with path.open("a") as output:
            output.write(json.dumps({"kind": "terminal_received", **notice}) + "\n")
        return notice

    def receive_initial_inputs(self, value):
        """A node appearing in the graph does not prove its inputs were delivered."""
        if value.get("epoch") != self.epoch:
            return
        if (value.get("schema") != "mr3-initial-inputs-ready-v1"
                or type(value.get("state_sequence")) is not int
                or value["state_sequence"] <= 0
                or type(value.get("stamp")) not in (int, float)
                or not math.isfinite(value["stamp"]) or value["stamp"] < 0
                or not isinstance(value.get("map_payload_sha256"), str)
                or len(value["map_payload_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in value["map_payload_sha256"])
                or [robot.get("name") for robot in value.get("robots", [])]
                != ["tb1", "tb2", "tb3"]):
            raise ValueError("invalid initial delivered-input acknowledgement")
        for robot in value["robots"]:
            for key in ("source_stamp", "received_stamp"):
                stamp = robot.get(key)
                if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                        or not 0 <= stamp <= value["stamp"] + 1e-8):
                    raise ValueError("initial delivered-input source time is invalid")
        if self.initial_inputs_ready is not None and self.initial_inputs_ready != value:
            raise ValueError("initial delivered-input acknowledgement changed within epoch")
        self.initial_inputs_ready = value

    def record_costmap(self, name, layer, grid):
        """Archive actual Nav2 master outputs without inventing a planner barrier.

        Header source time and the worker's receipt clock are distinct. These
        diagnostic copies never enter the actor, candidate or reward pipeline.
        """
        payload = self.map_payload(grid)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
        digest = hashlib.sha256(raw).hexdigest()
        if digest not in self.execution_map_digests:
            root = self.directory / "execution_inputs" / "maps"
            root.mkdir(parents=True, exist_ok=True)
            with (root / (digest + ".json.gz")).open("xb") as output:
                output.write(gzip.compress(raw, mtime=0))
            self.execution_map_digests.add(digest)
        row = {"schema": "mr3-native-costmap-receipt-v1", "epoch": self.epoch,
               "robot": name, "layer": layer,
               "topic": f"/{name}/{layer}_costmap/costmap",
               "source_header": payload["header"],
               "received_clock_ns": self.clock_ns,
               "payload_sha256": digest,
               "artifact": f"execution_inputs/maps/{digest}.json.gz",
               "scope": "published Nav2 master costmap; no exact planner-consumption ACK"}
        self.execution_costmap_file.write(json.dumps(row, sort_keys=True) + "\n")

    def verify_motion_output_topology(self):
        """Refuse task release while any bottom-level velocity bypass exists.

        The check inspects discovered DDS endpoints after Nav2 has become
        active. A launch remapping alone is not evidence of the native graph.
        Missing discovery is allowed to settle within a wall guard; a visible
        unexpected publisher is an immediate error.
        """
        endpoints = {}

        def ready():
            for name in ("tb1", "tb2", "tb3"):
                topic = f"/{name}/cmd_vel"
                entries = self.node.get_publishers_info_by_topic(topic)
                identities = [(entry.node_namespace, entry.node_name) for entry in entries]
                if any(identity != MOTION_OUTPUT_PUBLISHER for identity in identities):
                    raise RuntimeError(f"unguarded velocity publisher on {topic}: {identities}")
                endpoints[topic] = [{
                    "namespace": entry.node_namespace, "node": entry.node_name,
                    "topic_type": entry.topic_type,
                    "endpoint_gid": bytes(entry.endpoint_gid).hex(),
                } for entry in entries]
            return all(len(entries) == 1 for entries in endpoints.values())

        self._wait(ready, 10., "unique final motion gate publishers were not discovered")
        receipt = {"schema": "mr3-motion-output-topology-v1", "epoch": self.epoch,
                   "stamp": self.clock_ns / 1e9,
                   "scope": "native discovered cmd_vel publishers before task release",
                   "endpoints": endpoints}
        with (self.directory / "motion_topology.json").open("x") as output:
            json.dump(receipt, output, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")

    def reset(self):
        self._wait(lambda: self.monitor_ready and self.initial_inputs_ready is not None
                   and self.motion_ready,
                   400., "three-robot delivered-input startup guard expired")
        self.verify_motion_output_topology()
        output = (self.directory / "step_helper.log").open("w")
        self.outputs.append(output)
        self.helper = subprocess.Popen([
            "ros2", "run", "multi_robot", "mr3_gazebo_step", "--jsonl", "--world",
            f"p1c_{self.scene}", "--epoch", self.epoch, "--timeout-sec", "10"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=output)
        self.helper_peer = ipc.JsonLinePeer(self.helper.stdout.fileno(),
                                            self.helper.stdin.fileno())
        receipt = self._physics(0, wait_clock=False)
        if receipt["end_time_ns"] / 1e9 < self.initial_inputs_ready["stamp"] - 1e-8:
            raise RuntimeError("initial input acknowledgement is ahead of physical pause")
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
        initial_motion_status = self.wait_motion_phase()
        if initial_motion_status["ready"] is not True:
            raise RuntimeError("initial paused motion inputs are not ready for task release")
        self._snapshot()
        if self.watermarks["state_sequence"] < self.initial_inputs_ready["state_sequence"]:
            raise RuntimeError("initial snapshot predates delivered-input acknowledgement")
        self.start_ns = self.physical_ns
        self._wait(lambda: self.reward_ready is not None, 10.,
                   "evaluator did not acknowledge the task release")
        if abs(self.reward_ready["start_sim_time"] - self.start_ns / 1e9) > 1e-8:
            raise RuntimeError("reward epoch start differs from the frozen initial snapshot")
        response = self._reward(self.start_ns / 1e9, self.start_ns / 1e9, initialize=True)
        if response.get("reward") != 0 or response.get("terminated") or response.get("truncated"):
            raise RuntimeError("reward reset did not initialize an empty episode ledger")
        if self._evaluator_phase()["status"] != "LIVE":
            raise RuntimeError("initial evaluator phase is already terminal")
        result = {"snapshot": self.snapshot, "reward": 0., "terminated": False,
                  "truncated": False, "info": {
                      "epoch": self.epoch, "scene": self.scene, "seed": self.seed,
                      "startup_wall_sec": time.monotonic() - self.started_wall,
                      "reset_kind": "complete_process_rebuild", "dt": 0.,
                      "reward_diagnostics": response,
                      "scheduler": "mr3-physical-20ms-v1", "watermarks": self.watermarks,
                      "initial_pause_time_ns": receipt["end_time_ns"],
                      "initial_inputs_ready": self.initial_inputs_ready,
                      "initial_motion_status": initial_motion_status,
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
        terminal = self._evaluation()
        if terminal is not None:
            if round(terminal["end_sim_time_sec"] * 1e9) != start_ns:
                raise RuntimeError("late task terminal predates the last returned sample boundary")
            response = self._reward(start_ns / 1e9, start_ns / 1e9,
                                    truncation=external_truncation)
            if not response["terminated"] or response["truncated"]:
                raise RuntimeError("existing task terminal was not settled as terminated")
            if round(response.get("effective_step_end", -1.) * 1e9) != start_ns:
                raise RuntimeError("existing task terminal changed the settled sample boundary")
            result = {"snapshot": self.snapshot, "reward": response["reward"],
                      "terminated": True, "truncated": False, "info": {
                          "epoch": self.epoch, "dt": 0., "physical_dt": 0.,
                          "step_wall_sec": time.monotonic() - started_wall,
                          "reason": response.get("reason"), "reward_diagnostics": response,
                          "watermarks": self.watermarks, "command": None,
                          "terminal_observation_reused": True, "action_submitted": False,
                          "requested_action": action, "bootstrap": 0}}
            self.transition_file.write(json.dumps({"kind": "step", **result}, sort_keys=True)
                                       + "\n")
            self.shutdown_episode("task_terminal")
            return result
        self.command_number += 1
        command = {"epoch": self.epoch, "command_id": self.command_number,
                   "observation_sequence": self.snapshot["sequence"],
                   "observation_digest": self.snapshot["digest"], "action": action,
                   "created_at": start_ns / 1e9,
                   "expires_at": (start_ns + 2_000_000_000) / 1e9}
        event_index = len(self.events)
        self._publish(self.action_pub, command)

        def action_accounted():
            return any(row["kind"] in ("action", "action_rejected")
                       and row["payload"].get("command_id") == self.command_number
                       and row["payload"].get("observation_sequence") ==
                       command["observation_sequence"]
                       for row in self.events[event_index:])

        self._wait(action_accounted, 10., "adapter did not account for the explicit action")
        # A submitted action advances to at least the next real quantum boundary.
        # A terminal that arrives during its acknowledgement can therefore have
        # zero effective reward time and up to 20ms of honest physical lag.
        terminal = None
        while self.physical_ns < start_ns + 10**9:
            if self.callback_error:
                raise RuntimeError("ROS callback failed: " + self.callback_error)
            self.evaluator_phase.before_advance(self.physical_ns)
            self._trace_evaluator_phase("advance_permitted", next_target_time_ns=(
                self.physical_ns + 20_000_000))
            self._physics(20)
            if self.probe_armed:
                self.probe_armed = False
                self.trigger_failure_probe()
            self._evaluator_phase()
            terminal = self._evaluation()
            if terminal is not None:
                break
        # Permission alone never enables stale input: the adapter additionally
        # requires the evaluator's matching, causally arrived terminal notice.
        self._snapshot(allow_terminal=True)
        response = self._reward(start_ns / 1e9, self.physical_ns / 1e9,
                                truncation=external_truncation)
        terminated = bool(response["terminated"])
        truncated = bool(response["truncated"])
        if terminal is not None and not terminated:
            raise RuntimeError("evaluator terminal was not classified as terminated")
        if not terminated and self.physical_ns - start_ns != 10**9:
            raise RuntimeError("nonterminal policy transition is not exactly one physical second")
        effective_end = response.get("effective_step_end", self.physical_ns / 1e9)
        effective_dt = (round(effective_end * 1e9) - start_ns) / 1e9
        result = {"snapshot": self.snapshot, "reward": response["reward"],
                  "terminated": terminated, "truncated": truncated, "info": {
                      "epoch": self.epoch, "dt": effective_dt,
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

    def _shutdown_nav2(self):
        """Finalize real managed nodes while physics stays at the cleanup pause.

        This application shutdown barrier does not repair Fast DDS internally.
        It follows goal terminal closure and precedes the helper/finalize ACK;
        its physical watermark can therefore be later than the last RL sample.
        The later process exit protocol still owns the surviving clock readers.
        """
        with self.condition:
            started = time.monotonic_ns()
            paused = self.physical_ns
            closed = self.closed
            closed_clock_ns = self.closed_received_clock_ns
            closed_wall_ns = self.closed_received_wall_monotonic_ns
            start_clock_ns = self.clock_ns
        deadline = started + round(NAV2_SHUTDOWN_WALL_GUARD_SEC * 1e9)
        proof = {
            "schema": "mr3-nav2-shutdown-v1", "protocol": SHUTDOWN_PROTOCOL,
            "epoch": self.epoch, "physical_time_ns": paused, "start_clock_ns": start_clock_ns,
            "goal_ownership_closed": closed,
            "goal_ownership_closed_received_clock_ns": closed_clock_ns,
            "goal_ownership_closed_received_wall_monotonic_ns": closed_wall_ns,
            "started_wall_monotonic_ns": started,
            "wall_guard_sec": NAV2_SHUTDOWN_WALL_GUARD_SEC,
            "robots": [], "success": False, "failures": [],
            "scope": "post-goal cleanup pause, outside reward time; not a DDS-internal fix",
        }

        def remaining():
            if self.physical_ns != paused or self.clock_ns != paused:
                raise RuntimeError("physical/ROS clock changed during paused Nav2 shutdown")
            duration = (deadline - time.monotonic_ns()) / 1e9
            if duration <= 0:
                raise TimeoutError("Nav2 lifecycle shutdown exceeded its total wall guard")
            return duration

        def rpc(service_type, request, row):
            row["started_wall_monotonic_ns"] = time.monotonic_ns()
            try:
                remaining()
                self._healthy()
                client = self.node.create_client(service_type, row["service"])
                # Keep clients alive through ordered process shutdown. Destroying
                # them here would add endpoint teardown beside the server RPC.
                self.nav2_shutdown_clients.append(client)
                self._wait(client.service_is_ready, remaining(),
                           "Nav2 shutdown service unavailable: " + row["service"])
                remaining()
                row["request_clock_ns"] = self.clock_ns
                row["request_wall_monotonic_ns"] = time.monotonic_ns()
                future = client.call_async(request)
                self._wait(future.done, remaining(),
                           "Nav2 shutdown service response timeout: " + row["service"])
                response = future.result()
                row["response_clock_ns"] = self.clock_ns
                remaining()
                if response is None:
                    raise RuntimeError("Nav2 shutdown service returned no response")
                return response
            except Exception as error:
                row["error"] = repr(error)
                raise
            finally:
                row["completed_wall_monotonic_ns"] = time.monotonic_ns()
                row["wall_duration_sec"] = (row["completed_wall_monotonic_ns"]
                                            - row["started_wall_monotonic_ns"]) / 1e9

        path = self.directory / "nav2_shutdown.json"
        with path.open("x") as output:
            try:
                if (not isinstance(closed, dict) or closed.get("epoch") != self.epoch
                        or type(closed.get("pending_goal_count")) is not int
                        or closed.get("pending_goal_count") != 0
                        or closed.get("robot_names") != ["tb1", "tb2", "tb3"]
                        or type(closed_clock_ns) is not int or closed_clock_ns > paused
                        or type(closed_wall_ns) is not int or closed_wall_ns > started):
                    raise RuntimeError("Nav2 shutdown requires real closed-goal acknowledgement")
                remaining()
                for robot in ("tb1", "tb2", "tb3"):
                    request = self.ManageLifecycleNodes.Request()
                    request.command = self.ManageLifecycleNodes.Request.SHUTDOWN
                    if request.command != 4:
                        raise RuntimeError("unexpected native Nav2 SHUTDOWN command constant")
                    row = {"robot": robot, "shutdown": {
                        "service": f"/{robot}/lifecycle_manager_navigation/manage_nodes",
                        "command": request.command}, "states": []}
                    proof["robots"].append(row)
                    response = rpc(self.ManageLifecycleNodes, request, row["shutdown"])
                    row["shutdown"]["response"] = {"success": response.success}
                    if response.success is not True:
                        raise RuntimeError("Nav2 lifecycle manager rejected shutdown: " + robot)
                    for node in NAV2_NODES:
                        state = {"node": node, "service": f"/{robot}/{node}/get_state"}
                        row["states"].append(state)
                        response = rpc(self.GetState, self.GetState.Request(), state)
                        state["state"] = {"id": response.current_state.id,
                                          "label": response.current_state.label}
                        if state["state"] != {"id": 4, "label": "finalized"}:
                            raise RuntimeError("Nav2 node did not finalize: " + state["service"])
                remaining()
                proof["success"] = True
            except Exception as error:
                proof["failures"].append(repr(error))
                raise
            finally:
                proof["end_clock_ns"] = self.clock_ns
                proof["completed_wall_monotonic_ns"] = time.monotonic_ns()
                proof["wall_duration_sec"] = (proof["completed_wall_monotonic_ns"] - started) / 1e9
                expired = proof["success"] and proof["completed_wall_monotonic_ns"] > deadline
                if expired:
                    proof["success"] = False
                    proof["failures"].append(
                        "Nav2 lifecycle shutdown exceeded its total wall guard")
                self.nav2_shutdown_receipt = proof
                json.dump(proof, output, indent=2, sort_keys=True, allow_nan=False)
                output.write("\n")
                if expired:
                    raise TimeoutError(proof["failures"][-1])
        return proof

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
        self._shutdown_nav2()
        self.helper.stdin.close()
        self.helper.wait(timeout=10.)
        self.helper.stdout.close()
        if self.helper.returncode != 0:
            raise RuntimeError("physical step helper did not exit cleanly")
        self.finalize_request = {
            "epoch": self.epoch, "ack_sequence": self.reward_number, "reason": reason}
        self._publish(self.finalize_pub, self.finalize_request)
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
                        "shutdown_protocol": SHUTDOWN_PROTOCOL,
                        "nav2_shutdown": self.nav2_shutdown_receipt,
                        "training_finalize_request": self.finalize_request,
                        "training_finalize_ack": self.finalize_ack,
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
        self.evaluator_phase_file.close()
        self.motion_phase_file.close()
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
            elif request["op"] == "arm_failure_probe" and worker:
                result = worker.arm_failure_probe()
            elif request["op"] == "trigger_failure_probe" and worker:
                result = worker.trigger_failure_probe()
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
