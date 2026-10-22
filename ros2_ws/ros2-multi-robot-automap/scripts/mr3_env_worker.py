#!/usr/bin/env python3
"""System-Python ROS worker behind private learner pipes; never a policy."""

import argparse
import copy
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
from multi_robot_exploration.mr3_drive_phase import (
    DrivePhaseClient, PROTOCOL as DRIVE_PROTOCOL, WALL_GUARD_SEC as DRIVE_WALL_GUARD_SEC,
    valid_output,
)
from multi_robot_exploration.mr3_control_phase import (
    ControlPhaseClient, PROTOCOL as CONTROL_PROTOCOL,
    WALL_GUARD_SEC as CONTROL_WALL_GUARD_SEC, canonical, valid_motion_status,
    protocol_version,
)
from multi_robot_exploration.mr3_safety_intent import (
    parse_json, payload_sha256, validate_intent, validate_intent_refs,
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
PLANT_QUANTUM_NS = 20_000_000


def plant_stimulus_angular(arm, relative_ns):
    """Fixed from-rest engineering waveform; no state/truth-dependent trigger."""
    if arm not in ("continuous", "pulse") or type(relative_ns) is not int or relative_ns < 0:
        raise ValueError("invalid fixed plant stimulus coordinate")
    turning = 1_200_000_000 <= relative_ns < 2_740_000_000
    pulse = arm == "pulse" and 2_200_000_000 <= relative_ns < 2_240_000_000
    return 800 if turning and not pulse else 0
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
        self.safety_contract = request.get("safety_contract", "legacy")
        self.seed_rule = request.get("seed_rule", "legacy")
        if type(self.seed_rule) is not str or self.seed_rule not in (
                "legacy", "exact-point-bridge-v1", "exact-point-bridge-v2"):
            raise ValueError("invalid seed_rule")
        self.start_graph_rule = request.get("start_graph_rule", "original-seed-cell")
        if (type(self.start_graph_rule) is not str or self.start_graph_rule not in
                ("original-seed-cell", "point-attachment-3x3-v1")
                or (self.start_graph_rule == "point-attachment-3x3-v1"
                    and self.seed_rule != "exact-point-bridge-v2")):
            raise ValueError("invalid seed_rule/start_graph_rule pair")
        self.control_version = protocol_version(self.safety_contract)
        self.safety_intents = {}
        self.safety_intent_publishers = {}
        self.bootstrap_intent_refs = None
        if self.scene not in ("open", "rooms", "corridors") or type(self.seed) is not int:
            raise ValueError("invalid scene or seed")
        if request.get("quantum_steps") != 20:
            raise ValueError("scheduler requires 20 physical ticks per quantum")
        self.terminal_probe = request.get("terminal_probe", False)
        if type(self.terminal_probe) is not bool:
            raise ValueError("terminal_probe must be a boolean")
        self.plant_stimulus_arm = request.get("plant_stimulus_arm")
        if self.plant_stimulus_arm not in (None, "continuous", "pulse"):
            raise ValueError("invalid plant stimulus arm")
        if self.plant_stimulus_arm is not None and (
                self.terminal_probe or (self.scene, self.seed) != ("open", 101)):
            raise ValueError("plant stimulus requires its exclusive open seed101 fixture")
        self.plant_stimulus_work_deadline_ns = request.get("plant_stimulus_work_deadline_ns")
        if self.plant_stimulus_arm is not None and (
                type(self.plant_stimulus_work_deadline_ns) is not int
                or not time.monotonic_ns() < self.plant_stimulus_work_deadline_ns
                <= time.monotonic_ns() + 1_680_000_000_000):
            raise ValueError("plant stimulus requires its bounded work deadline")
        if self.plant_stimulus_arm is None and self.plant_stimulus_work_deadline_ns is not None:
            raise ValueError("plant work deadline requires the explicit diagnostic arm")
        self.plant_stimulus_sequence = 0
        self.plant_stimulus_origin_ns = None
        self.plant_stimulus_pending = None
        self.plant_stimulus_receipt = None
        self.plant_stimulus_input_sequence = None
        self.plant_stimulus_publisher_gid = None
        self.plant_stimulus_receipt_publisher_gid = None
        self.probe_armed = False
        self.probe_number = 0
        self.task_terminal = None
        self.evaluator_phase = PhaseClient(self.epoch)
        self.condition = threading.Condition()
        self.clock_ns = 0
        self.monitor_ready = False
        self.motion_ready = False
        self.odometry_recorder_ready = False
        self.motion_status = None
        self.stop_status = None
        self.controlled = False
        self.stopping = False
        self.cleanup_mode = False
        self.cleanup_deadline = None
        self.control_phase = ControlPhaseClient(self.epoch, safety_contract=self.safety_contract)
        self.state_commit = None
        self.peer_commit = None
        self.drive_phase = DrivePhaseClient(self.epoch)
        self.consumed_drive_phase = None
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
        self.plant_stimulus_file = None
        if self.plant_stimulus_arm is not None:
            self.plant_stimulus_file = (directory / "plant_stimulus_worker.jsonl").open(
                "x", buffering=1)
            self.outputs.append(self.plant_stimulus_file)
        self.transition_file = (directory / "transitions.jsonl").open("x", buffering=1)
        self.physics_file = (directory / "physics.jsonl").open("x", buffering=1)
        self.evaluator_phase_file = (directory / "evaluator_phase_worker.jsonl").open(
            "x", buffering=1)
        self.motion_phase_file = (directory / "motion_phase_worker.jsonl").open("x", buffering=1)
        self.drive_phase_file = (directory / "drive_phase_worker.jsonl").open("x", buffering=1)
        self.outputs.append(self.drive_phase_file)
        self.control_phase_file = (directory / "control_phase_worker.jsonl").open("x", buffering=1)
        self.outputs.append(self.control_phase_file)
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
        from rcl_interfaces.srv import SetParametersAtomically
        from multi_robot_exploration.mr3_information import map_payload

        rclpy.init()
        self.rclpy = rclpy
        self.String = String
        self.Header = Header
        self.GetState = GetState
        self.ManageLifecycleNodes = ManageLifecycleNodes
        self.Parameter = Parameter
        self.SetParametersAtomically = SetParametersAtomically
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
        self.control_publishers = {
            name: self.node.create_publisher(String, topic, 10) for name, topic in (
                ("state", "/mr3/state_phase_request"),
                ("peer", "/mr3/peer_phase_request"),
                ("motion", "/motion_safety/control_request"))}
        self.infrastructure_abort_pub = self.node.create_publisher(
            String, "/mr3/infrastructure_abort", 10)
        self.probe_pub = (self.node.create_publisher(String, "/mr3/diagnostic_failure", 10)
                          if self.terminal_probe else None)
        self.stop_pub = self.node.create_publisher(Header, "/exploration_stop_request", qos)
        self.plant_stimulus_client = (
            self.node.create_client(SetParametersAtomically,
                                    "/tb3/velocity_smoother/mr3_diagnostic_apply")
            if self.plant_stimulus_arm is not None else None)

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

        def odometry_recorder_ready(message):
            self.odometry_recorder_ready = bool(message.data)

        def motion_status(message):
            self.receive_motion_status(parse_json(message.data) if getattr(self, "control_version", 1) == 2 else json.loads(message.data))

        def stop_status(message):
            self.receive_stop_status(parse_json(message.data) if getattr(self, "control_version", 1) == 2 else json.loads(message.data))

        def failure(message):
            self.failures.append(message.data)

        self.subscriptions = [
            self.node.create_subscription(
                Clock, "/clock", callback(clock),
                QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT)),
            self.node.create_subscription(Bool, "/task_monitor_ready", callback(monitor), qos),
            self.node.create_subscription(Bool, "/motion_safety/ready",
                                          callback(motion_ready), qos),
            self.node.create_subscription(Bool, "/mr3/odometry_recorder/ready",
                                          callback(odometry_recorder_ready), qos),
            self.node.create_subscription(String, "/motion_safety/status",
                                          callback(motion_status), qos),
            self.node.create_subscription(String, "/motion_safety/stop_status",
                                          callback(stop_status), qos),
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
        for name, topic in (("state", "/mr3/state_phase_ack"),
                            ("peer", "/mr3/peer_phase_ack"),
                            ("motion", "/motion_safety/control_ack")):
            self.subscriptions.append(self.node.create_subscription(
                String, topic, callback(lambda message, name=name: self.receive_control_phase(
                    name, parse_json(message.data) if getattr(self, "control_version", 1) == 2 else json.loads(message.data))),
                qos))
        if self.plant_stimulus_arm is not None:
            self.subscriptions.append(self.node.create_subscription(
                String, "/motion_safety/diagnostic_request_receipt",
                callback(lambda message: self.receive_plant_stimulus_receipt(
                    json.loads(message.data))), 20))
        for name in ("tb1", "tb2", "tb3"):
            if self.safety_contract == "mr3-reach-v1":
                self.subscriptions.append(self.node.create_subscription(
                    String, f"/{name}/mr3/safety_intent",
                    callback(lambda message, name=name: self.receive_safety_intent(name, message)),
                    QoSProfile(depth=256, durability=DurabilityPolicy.VOLATILE,
                               reliability=ReliabilityPolicy.RELIABLE)))
            self.subscriptions.append(self.node.create_subscription(
                String, f"/{name}/mr3_drive/status",
                callback(lambda message, name=name: self.receive_drive_status(
                    name, json.loads(message.data))), qos))
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
            f"mr3_safety_contract:={self.safety_contract}",
        ]
        if self.seed_rule != "legacy":
            self.command.append(f"mr3_seed_rule:={self.seed_rule}")
        if self.start_graph_rule != "original-seed-cell":
            self.command.append(f"mr3_start_graph_rule:={self.start_graph_rule}")
        if self.terminal_probe:
            self.command.append("training_terminal_probe:=true")
        if self.plant_stimulus_arm is not None:
            self.command.append(f"mr3_plant_stimulus_arm:={self.plant_stimulus_arm}")
        metadata = {"schema": "mr3-p1c-worker-v1", "epoch": self.epoch,
                    "scene": self.scene, "seed": self.seed, "command": self.command,
                    "freeze": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
                    "transport_environment": self.transport_environment,
                    "environment": {key: os.environ.get(key) for key in (
                        "ROS_DOMAIN_ID", "GAZEBO_MASTER_URI", "PYTHONNOUSERSITE")},
                    "python": sys.executable, "quantum_steps": 20,
                    "reset_handshake": "paused-controlled-state-peer-guard-storage-v1",
                    "execution_phase_protocol": (CONTROL_PROTOCOL if self.control_version == 1 else
                                                 "mr3-controlled-execution-phase-v2"),
                    "execution_phase_wall_guard_sec": CONTROL_WALL_GUARD_SEC,
                    "terminal_protocol": "mr3-task-terminal-v1",
                    "evaluator_phase_protocol": PHASE_PROTOCOL,
                    "evaluator_phase_wall_guard_sec": PHASE_WALL_GUARD_SEC,
                    "shutdown_protocol": SHUTDOWN_PROTOCOL,
                    "nav2_shutdown_wall_guard_sec": NAV2_SHUTDOWN_WALL_GUARD_SEC,
                    "terminal_probe": self.terminal_probe,
                    "plant_stimulus_arm": self.plant_stimulus_arm,
                    "plant_stimulus_work_deadline_ns": self.plant_stimulus_work_deadline_ns,
                    "physical_step_ns": 1000000, "policy_step_ns": 1000000000,
                    "startup_wall_guard_sec": 420., "closure_wall_guard_sec": 90.}
        if self.seed_rule != "legacy":
            metadata["seed_rule"] = self.seed_rule
        if self.start_graph_rule != "original-seed-cell":
            metadata["start_graph_rule"] = self.start_graph_rule
        if self.control_version == 2:
            metadata["safety_contract"] = self.safety_contract
            metadata["reset_handshake"] = "paused-controlled-state-peer-guard-storage-v2"
        (directory / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        output = (directory / "launch.log").open("w")
        self.outputs.append(output)
        self.launch = subprocess.Popen(self.command, cwd=ROS_ROOT, stdout=output,
                                       stderr=subprocess.STDOUT)

    def _healthy(self):
        if getattr(self, "cleanup_mode", False):
            if time.monotonic() >= self.cleanup_deadline:
                raise TimeoutError("infrastructure cleanup total wall guard expired")
            if self.launch.poll() is not None and not self.finished:
                raise RuntimeError("launch exited during infrastructure cleanup")
            return
        if (getattr(self, "plant_stimulus_arm", None) is not None
                and time.monotonic_ns() >= self.plant_stimulus_work_deadline_ns):
            raise TimeoutError("plant diagnostic work cutoff; 120s reserved for closure")
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
        while True:
            self._healthy()
            if predicate():
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(label)
            with self.condition:
                self.condition.wait(min(.02, remaining))

    def _publish(self, publisher, payload):
        publisher.publish(self.String(data=json.dumps(payload, allow_nan=False)))

    def _trace_control_phase(self, kind, **payload):
        self.control_phase_file.write(json.dumps({
            "schema": (CONTROL_PROTOCOL if getattr(self, "safety_contract", "legacy") == "legacy"
                       else "mr3-controlled-execution-phase-v2"), "kind": kind, "epoch": self.epoch,
            "worker_clock_ns": self.clock_ns,
            "worker_physical_ns": getattr(self, "physical_ns", None),
            "wall_monotonic_ns": time.monotonic_ns(), **payload,
        }, sort_keys=True, allow_nan=False) + "\n")

    def receive_control_phase(self, component, value):
        self._trace_control_phase("ack_received", component=component, ack=value)
        if (isinstance(value, dict) and value.get("epoch") == self.epoch
                and value.get("ok") is False
                and not (component == "state"
                         and value.get("error") == "state_phase_task_terminal"
                         and value.get("scope") == "terminal_cancelled_uncommitted_state_phase"
                         and isinstance(value.get("terminal_notice"), dict))):
            raise RuntimeError("actual controlled execution failure: " + canonical(value))
        self.control_phase.receive(component, value, getattr(self, "physical_ns", None),
                                   self.clock_ns)

    def receive_safety_intent(self, name, message):
        """Keep refs from actual owner-topic callbacks; never manufacture an intent."""
        if self.safety_contract != "mr3-reach-v1" or name not in ("tb1", "tb2", "tb3"):
            raise ValueError("unexpected safety intent subscription")
        value = parse_json(message.data)
        if type(value) is not dict:
            raise ValueError("safety intent is not an object")
        if value.get("epoch") != self.epoch:
            return
        value = validate_intent(value, epoch=self.epoch, robot=name)
        topic = f"/{name}/mr3/safety_intent"
        entries = self.node.get_publishers_info_by_topic(topic)
        graph = [{"namespace": entry.node_namespace, "node": entry.node_name,
                  "type": entry.topic_type, "endpoint_gid": bytes(entry.endpoint_gid).hex()} for entry in entries]
        if (len(graph) != 1 or graph[0]["namespace"] != "/" or graph[0]["node"] != "motion_safety"
                or graph[0]["type"] != "std_msgs/msg/String" or not graph[0]["endpoint_gid"]):
            raise ValueError("safety intent owner graph differs")
        previous_gid = self.safety_intent_publishers.get(name)
        if previous_gid is not None and previous_gid != graph[0]["endpoint_gid"]:
            raise ValueError("safety intent owner graph identity changed")
        self.safety_intent_publishers[name] = graph[0]["endpoint_gid"]
        previous = self.safety_intents.get(name)
        if previous is not None and value != previous and (
                value["intent_sequence"] <= previous["intent_sequence"]
                or value["source_clock_ns"] < previous["source_clock_ns"]):
            raise ValueError("actual safety intent regressed or changed identity")
        self.safety_intents[name] = value
        self._trace_control_phase("owner_intent_received", robot=name, intent=value,
                                  payload_sha256=payload_sha256(value), publisher_graph=graph,
                                  identity_scope="graph_at_callback_not_per_packet_identity")

    def release_intent_refs(self, release_ns):
        """Only three actually subscribed post-release HOLDs can bootstrap refs."""
        if type(release_ns) is not int or release_ns < 0:
            raise ValueError("release clock must be an actual nonnegative integer")
        refs = {}
        for name in ("tb1", "tb2", "tb3"):
            value = self.safety_intents.get(name)
            if (value is None or value["role"] != "HOLD"
                    or value["lineage"].get("release_clock_ns") != release_ns):
                return None
            validate_intent(value, epoch=self.epoch, robot=name, now_ns=release_ns)
            refs[name] = {"intent_sequence": value["intent_sequence"], "payload_sha256": payload_sha256(value)}
        return validate_intent_refs(refs, robots=("tb1", "tb2", "tb3"))

    def receive_stop_status(self, value, origin="stop_topic"):
        if not isinstance(value, dict):
            raise ValueError("invalid permanent stop notification")
        if value.get("epoch") != self.epoch:
            return
        target = value.get("clock_ns")
        if (type(target) is not int
                or not valid_motion_status(value, self.epoch, target, stop=True,
                        safety_contract=getattr(self, "safety_contract", "legacy"))):
            raise ValueError("invalid permanent stop status")
        normal = self.motion_status
        if normal is not None and any(
                value["decision_sequences"][name] <= normal["decision_sequences"][name]
                for name in ("tb1", "tb2", "tb3")):
            raise ValueError("permanent stop does not supersede the normal target")
        previous = self.stop_status
        if previous is not None:
            if canonical(previous) == canonical(value):
                self._trace_control_phase("stop_observed", status=value, origin=origin,
                                          duplicate=True)
                return
            if (target < previous["clock_ns"] or any(
                    value["decision_sequences"][name] <= previous["decision_sequences"][name]
                    for name in ("tb1", "tb2", "tb3"))):
                raise ValueError("permanent stop status regressed or changed identity")
        self.stop_status = copy.deepcopy(value)
        self.stopping = True
        self._trace_control_phase("stop_observed", status=value, origin=origin, duplicate=False)

    def _control_rpc(self, component, operation, request_id=None, **references):
        target = self.physical_ns
        with self.condition:
            if self.clock_ns != target:
                raise RuntimeError("execution request requires an exact paused clock")
            request = self.control_phase.begin(component, operation, target,
                                               request_id=request_id, **references)
            self._trace_control_phase("request", component=component, request=request)
        self._publish(self.control_publishers[component], request)
        self._wait(lambda: self.control_phase.response is not None or (
            operation != "stop" and self.stopping), CONTROL_WALL_GUARD_SEC,
            component + " controlled execution phase wall guard expired")
        with self.condition:
            if self.control_phase.response is None:
                self.control_phase.abandon_for_stop()
                return None
            response = self.control_phase.consume(allow_error=True)
            if response["ok"] is not True:
                self._trace_control_phase("ack_rejected", component=component, ack=response)
                notice = response.get("terminal_notice")
                if (component == "state" and response.get("error") == "state_phase_task_terminal"
                        and response.get("scope") == "terminal_cancelled_uncommitted_state_phase"
                        and isinstance(notice, dict)):
                    self._wait(lambda: self.task_terminal is not None, CONTROL_WALL_GUARD_SEC,
                               "state cancellation has no actual evaluator terminal notice")
                    if (canonical(notice) != canonical(self.task_terminal)
                            or self._evaluation() is None):
                        raise RuntimeError("state cancellation differs from actual task terminal")
                    self.stopping = True
                    self.control_phase.abandon_for_stop()
                    self._trace_control_phase("terminal_cancelled", component=component,
                                              ack=response, terminal_notice=self.task_terminal)
                    return None
                raise RuntimeError("execution phase rejected: " + canonical(response))
            self._trace_control_phase("ack_consumed", component=component, ack=response)
            return response

    def _execution_motion(self):
        return self.stop_status if getattr(self, "stopping", False) else self.motion_status

    def _commit_stop(self, reason):
        self.stopping = True
        if self.control_phase.pending is not None:
            self.control_phase.abandon_for_stop()
        cached = getattr(self, "stop_control_ack", None)
        if (cached is None or cached["clock_ns"] != self.physical_ns
                or canonical(cached["status"]) != canonical(self.stop_status)):
            response = self._control_rpc("motion", "stop", request_id=(
                f"stop{self.physical_ns}"), reason=reason)
            self.receive_stop_status(response["status"], origin="control_ack")
            self.stop_control_ack = response
        self.execution_request_id = self.stop_control_ack["request_id"]
        self.wait_drive_phase(self.stop_status)
        return self.stop_status

    def _commit_boundary(self):
        if self.stopping:
            return self._commit_stop("permanent_stop")
        if getattr(self, "plant_stimulus_arm", None) is not None:
            self._apply_plant_stimulus()
        identity = f"boundary{self.physical_ns}"
        references = {}
        if getattr(self, "safety_contract", "legacy") == "mr3-reach-v1":
            expected = (self.bootstrap_intent_refs if self.bootstrap_intent_refs is not None
                        else self.motion_status["intent_refs"])
            references["expected_intents"] = validate_intent_refs(expected, robots=("tb1", "tb2", "tb3"))
        state = self._control_rpc("state", "commit", request_id=identity, **references)
        if state is None or self.stopping:
            return self._commit_stop("stop_during_state_commit")
        if references:
            self.bootstrap_intent_refs = None
        peer = self._control_rpc("peer", "commit", request_id=identity, state_commit=state)
        if peer is None or self.stopping:
            return self._commit_stop("stop_during_peer_commit")
        motion = self._control_rpc("motion", "commit", request_id=identity,
                                   state_commit=state, peer_commit=peer)
        if motion is None or motion["status"].get("phase_kind") == "stop" or self.stopping:
            if motion is not None and motion["status"].get("phase_kind") == "stop":
                self.receive_stop_status(motion["status"], origin="control_ack")
            return self._commit_stop("stop_during_guard_commit")
        self.state_commit, self.peer_commit = state, peer
        self.execution_request_id = motion["request_id"]
        self.receive_motion_status(motion["status"])
        self.wait_motion_phase()
        self.wait_drive_phase(self.motion_status)
        return self._execution_motion()

    def _trace_plant_stimulus(self, kind, **payload):
        with self.condition:
            self.plant_stimulus_file.write(json.dumps({
                "schema": "mr3-plant-stimulus-worker-v1", "kind": kind,
                "epoch": self.epoch, "arm": self.plant_stimulus_arm,
                "worker_clock_ns": self.clock_ns, "worker_physical_ns": self.physical_ns,
                "origin_ns": self.plant_stimulus_origin_ns,
                "relative_ns": (None if self.plant_stimulus_origin_ns is None else
                                self.physical_ns - self.plant_stimulus_origin_ns),
                "wall_monotonic_ns": time.monotonic_ns(), **payload,
            }, sort_keys=True, allow_nan=False) + "\n")

    def receive_plant_stimulus_receipt(self, receipt):
        topic = "/motion_safety/diagnostic_request_receipt"
        entries = self.node.get_publishers_info_by_topic(topic)
        graph = {"scope": "graph_at_callback_not_per_packet_identity", "topic": topic,
                 "endpoints": [{"namespace": value.node_namespace, "node": value.node_name,
                                "type": value.topic_type,
                                "endpoint_gid": bytes(value.endpoint_gid).hex()}
                               for value in entries]}
        self._trace_plant_stimulus("guard_request_receipt_received", receipt=receipt,
                                  receipt_publisher_graph=graph)
        if (len(entries) != 1 or entries[0].node_namespace != "/"
                or entries[0].node_name != "motion_safety"
                or entries[0].topic_type != "std_msgs/msg/String"
                or not any(bytes(entries[0].endpoint_gid))
                or (self.plant_stimulus_receipt_publisher_gid is not None
                    and bytes(entries[0].endpoint_gid).hex()
                    != self.plant_stimulus_receipt_publisher_gid)):
            raise RuntimeError("diagnostic receipt lacks its unique actual guard publisher")
        self.plant_stimulus_receipt_publisher_gid = bytes(entries[0].endpoint_gid).hex()
        pending = self.plant_stimulus_pending
        identity = receipt.get("publisher_identity", {})
        endpoints = identity.get("endpoints", [])
        expected_sequence = self.plant_stimulus_input_sequence
        if (pending is None or self.plant_stimulus_receipt is not None
                or receipt.get("schema") != "mr3-guard-diagnostic-receipt-v1"
                or receipt.get("epoch") != self.epoch or receipt.get("robot") != "tb3"
                or receipt.get("clock_ns") != pending["clock_ns"]
                or self.clock_ns != self.physical_ns or self.clock_ns != pending["clock_ns"]
                or receipt.get("v") != 0. or receipt.get("w") != pending["angular_millirad"] / 1000.
                or receipt.get("supported") is not True
                or type(receipt.get("input_sequence")) is not int
                or receipt["input_sequence"] <= 0
                or (expected_sequence is not None
                    and receipt["input_sequence"] != expected_sequence + 1)
                or identity.get("valid") is not True
                or identity.get("topic") != "/tb3/cmd_vel_unguarded"
                or len(endpoints) != 1 or endpoints[0].get("namespace") != "/tb3"
                or endpoints[0].get("node") != "velocity_smoother"
                or not endpoints[0].get("endpoint_gid")
                or not any(value != "0" for value in endpoints[0]["endpoint_gid"])
                or (self.plant_stimulus_publisher_gid is not None
                    and endpoints[0]["endpoint_gid"] != self.plant_stimulus_publisher_gid)):
            raise RuntimeError("diagnostic source lacks its exact real guard consumption receipt")
        self.plant_stimulus_publisher_gid = endpoints[0]["endpoint_gid"]
        self.plant_stimulus_receipt = receipt

    def _apply_plant_stimulus(self):
        """Publish only through the genuine smoother, then wait for real guard input."""
        if self.clock_ns != self.physical_ns:
            raise RuntimeError("diagnostic stimulus requires the exact paused physical clock")
        if self.plant_stimulus_origin_ns is None:
            self.plant_stimulus_origin_ns = self.physical_ns
        relative_ns = self.physical_ns - self.plant_stimulus_origin_ns
        if relative_ns != self.plant_stimulus_sequence * PLANT_QUANTUM_NS:
            raise RuntimeError("diagnostic source lost its fixed 20ms boundary sequence")
        request = {"epoch": self.epoch, "arm": self.plant_stimulus_arm,
                   "sequence": self.plant_stimulus_sequence + 1,
                   "clock_ns": self.physical_ns,
                   "angular_millirad": plant_stimulus_angular(
                       self.plant_stimulus_arm, relative_ns)}
        self.plant_stimulus_pending = request
        self.plant_stimulus_receipt = None
        self._trace_plant_stimulus("source_request", request=request)
        self._wait(self.plant_stimulus_client.service_is_ready, 10.,
                   "genuine smoother diagnostic service is unavailable")
        service_request = self.SetParametersAtomically.Request()
        service_request.parameters = [self.Parameter(name, value=value).to_parameter_msg()
                                      for name, value in request.items()]
        future = self.plant_stimulus_client.call_async(service_request)
        self._wait(future.done, 10., "genuine smoother diagnostic publication ACK expired")
        response = future.result()
        if response is None or response.result.successful is not True:
            raise RuntimeError("genuine smoother rejected diagnostic publication: " +
                               repr(response))
        ack = json.loads(response.result.reason)
        self._trace_plant_stimulus("service_ack", ack=ack)
        if (ack.get("schema") != "mr3-smoother-diagnostic-ack-v1"
                or any(ack.get(key) != value for key, value in request.items())
                or ack.get("robot") != "tb3" or ack.get("linear_x") != 0.
                or ack.get("publication_clock_ns") != request["clock_ns"]
                or ack.get("completion_scope") != "smoother_publication_only_not_guard_or_storage"
                or ack.get("output_topic") != "/tb3/cmd_vel_unguarded"):
            raise RuntimeError("genuine smoother diagnostic publication identity mismatch")
        self._wait(lambda: self.plant_stimulus_receipt is not None, 10.,
                   "real guard diagnostic request consumption ACK expired")
        receipt = self.plant_stimulus_receipt
        self.plant_stimulus_input_sequence = receipt["input_sequence"]
        self.plant_stimulus_sequence = request["sequence"]
        self._trace_plant_stimulus("boundary_consumed", source_request=request,
                                  smoother_ack=ack, guard_receipt=receipt)
        self.plant_stimulus_pending = None

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
        if getattr(self, "safety_contract", "legacy") == "mr3-reach-v1":
            if type(steps) is not int or steps < 0 or type(wait_clock) is not bool:
                raise ValueError("invalid reach physical step request")
            if (steps > 0 and wait_clock and getattr(self, "controlled", False)
                    and not self.stopping and steps != 20):
                raise ValueError("reach normal execution requires exactly one 20ms quantum")
        self.physics_number += 1
        request_id = f"q{self.physics_number}"
        if steps > 0 and wait_clock:
            with self.condition:
                if getattr(self, "controlled", False) and self.stopping:
                    self._commit_stop("before_physics_advance")
                motion = self._execution_motion()
                receipts = self.wait_drive_phase(motion)
                motion = self._execution_motion()
                if ((self.callback_error and not getattr(self, "cleanup_mode", False))
                        or any(receipts[name]["decision_sequence"]
                               != motion["decision_sequences"][name] for name in receipts)):
                    raise RuntimeError("native drive callback failed or guard target changed")
                control = {}
                if getattr(self, "controlled", False):
                    bootstrap = getattr(self, "bootstrap_pending", False) and not self.stopping
                    if bootstrap:
                        if (steps != 20 or set(self.takeover_acks) != {"state", "peer", "motion"}
                                or any(output != {"linear_x": 0., "angular_z": 0.}
                                       for output in motion["outputs"].values())):
                            raise RuntimeError("bootstrap needs three takeovers and actual zeros")
                        self.bootstrap_pending = False
                    elif (getattr(self, "safety_contract", "legacy") == "mr3-reach-v1" and not self.stopping
                          and not valid_motion_status(motion, self.epoch, self.physical_ns,
                              safety_contract=self.safety_contract, require_table=True)):
                        raise RuntimeError("normal physical quantum has no actual bound safety table")
                    control = {"control_kind": ("bootstrap_zero" if bootstrap else
                                                "stop" if self.stopping else "normal"),
                               "control_request_id": self.execution_request_id}
                self._trace_drive_phase(
                    "advance_permitted", request_id=request_id, steps=steps,
                    start_time_ns=self.physical_ns, expected_motion=motion, receipts=receipts,
                    **control)
                self.helper_peer.send({"request_id": request_id, "steps": steps,
                                       "epoch": self.epoch})
        else:
            self.helper_peer.send({"request_id": request_id, "steps": steps, "epoch": self.epoch})
        receipt = self.helper_peer.receive(15.)
        if receipt.get("ok") is not True or receipt.get("request_id") != request_id:
            raise RuntimeError("physical step rejected: " + json.dumps(receipt))
        if (receipt.get("epoch") != self.epoch or receipt.get("paused") is not True
                or receipt["end_iterations"] - receipt["start_iterations"] != steps
                or receipt["end_time_ns"] - receipt["start_time_ns"] != steps * 1000000):
            raise RuntimeError("physical iteration/time receipt mismatch")
        self.physics_file.write(json.dumps(receipt, sort_keys=True) + "\n")
        self._trace_drive_phase("physics_completed", receipt=receipt)
        if wait_clock:
            self._wait(lambda: self.clock_ns >= receipt["end_time_ns"], 10.,
                       "ROS /clock did not reach the paused physical boundary")
            if self.clock_ns != receipt["end_time_ns"]:
                raise RuntimeError("ROS /clock advanced beyond the paused physical boundary")
        self.physical_ns = receipt["end_time_ns"]
        if wait_clock:
            if getattr(self, "controlled", False):
                self._commit_boundary()
            else:
                self.wait_motion_phase()
        return receipt

    def receive_motion_status(self, value):
        """Receive a real gate-executor completion, never synthesize its clock."""
        if not isinstance(value, dict):
            raise ValueError("invalid motion gate phase status")
        if value.get("epoch") != self.epoch:
            return
        sequences = value.get("decision_sequences")
        outputs = value.get("outputs")
        if not valid_motion_status(value, self.epoch, value.get("clock_ns"),
                safety_contract=getattr(self, "safety_contract", "legacy")):
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
        self.motion_status = copy.deepcopy(value)
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

    def _trace_drive_phase(self, kind, **payload):
        with self.condition:
            self.drive_phase_file.write(json.dumps({
                "kind": kind, "epoch": self.epoch, "wall_monotonic_ns": time.monotonic_ns(),
                "worker_clock_ns": self.clock_ns,
                "worker_physical_ns": getattr(self, "physical_ns", None), **payload,
            }, sort_keys=True, allow_nan=False) + "\n")

    def receive_drive_status(self, name, value):
        if not isinstance(value, dict) or value.get("robot") != name:
            raise ValueError("native drive receipt does not match its subscribed robot")
        self.drive_phase.receive(value)
        self._trace_drive_phase("ack_received", topic_robot=name, ack=value)

    def wait_drive_phase(self, motion):
        """Require each actual driver to store this exact tagged guard target."""
        if (getattr(self, "stopping", False) and isinstance(motion, dict)
                and motion.get("phase_kind") != "stop"):
            self._commit_stop("stop_before_native_storage_wait")
            return self.consumed_drive_phase["receipts"]

        def paused():
            if ((self.callback_error and not getattr(self, "cleanup_mode", False))
                    or motion is None or self._execution_motion() != motion
                    or self.clock_ns != motion["clock_ns"]
                    or self.physical_ns != motion["clock_ns"]):
                raise RuntimeError("native drive boundary has failed or changed")

        paused()
        if (self.consumed_drive_phase is not None
                and self.consumed_drive_phase["expected_motion"] == motion
                and all(self.drive_phase.latest.get(name) == ack for name, ack in
                        self.consumed_drive_phase["receipts"].items())):
            return self.consumed_drive_phase["receipts"]
        self._wait(lambda: (getattr(self, "stopping", False)
                            and motion.get("phase_kind") != "stop")
                   or self.drive_phase.matching(motion) is not None,
                   DRIVE_WALL_GUARD_SEC, "native drive exact-target phase wall guard expired")
        with self.condition:
            if getattr(self, "stopping", False) and motion.get("phase_kind") != "stop":
                self._commit_stop("stop_during_native_storage_wait")
                return self.consumed_drive_phase["receipts"]
            paused()
            receipts = self.drive_phase.consume(motion)
            self.consumed_drive_phase = {"expected_motion": motion, "receipts": receipts}
            self._trace_drive_phase("ack_consumed", expected_motion=motion, receipts=receipts)
        return receipts

    def _snapshot(self, allow_terminal=False):
        from multi_robot_exploration.mr3_observation import snapshot_digest
        self.snapshot_number += 1
        request_id = f"s{self.snapshot_number}"
        self._publish(self.drain_pub, {
            "epoch": self.epoch, "request_id": request_id, "target_time_ns": self.physical_ns,
            "allow_terminal": allow_terminal})
        self._wait(lambda: request_id in self.drains, 30., "information drain guard expired")
        drained = self.drains.pop(request_id)
        if drained.get("ok") is not True:
            raise RuntimeError("information pipeline failed to drain: " + json.dumps(drained))
        if (getattr(self, "controlled", False) and not allow_terminal
                and (self.state_commit is None
                     or canonical(drained["state_sequence"])
                     != canonical(self.state_commit["state_sequence"])
                     or drained.get("state_bundle_sha256") != self.state_commit["bundle_sha256"])):
            raise RuntimeError("snapshot drain changed the committed execution state")
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
        self.last_reward_response = response
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

    def verify_drive_topology(self):
        """Bind tagged targets and receipts to the actual unique native endpoints."""
        publishers, subscribers, legacy_subscribers = {}, {}, {}

        def endpoint(entry):
            return {"namespace": entry.node_namespace, "node": entry.node_name,
                    "topic_type": entry.topic_type,
                    "endpoint_gid": bytes(entry.endpoint_gid).hex()}

        def ready():
            for name in ("tb1", "tb2", "tb3"):
                driver = (f"/{name}", "turtlebot3_diff_drive")
                target, status = f"/{name}/mr3_drive/target", f"/{name}/mr3_drive/status"
                for topic, owner in ((target, MOTION_OUTPUT_PUBLISHER), (status, driver)):
                    entries = self.node.get_publishers_info_by_topic(topic)
                    if any((entry.node_namespace, entry.node_name) != owner
                           or entry.topic_type != "std_msgs/msg/String" for entry in entries):
                        raise RuntimeError(f"unexpected native drive publisher on {topic}")
                    publishers[topic] = [endpoint(entry) for entry in entries]
                entries = self.node.get_subscriptions_info_by_topic(target)
                if any((entry.node_namespace, entry.node_name) != driver
                       or entry.topic_type != "std_msgs/msg/String" for entry in entries):
                    raise RuntimeError(f"unexpected native drive target subscriber on {target}")
                subscribers[target] = [endpoint(entry) for entry in entries]
                legacy = self.node.get_subscriptions_info_by_topic(f"/{name}/cmd_vel")
                if any((entry.node_namespace, entry.node_name) == driver for entry in legacy):
                    raise RuntimeError("tagged native driver still consumes an untagged Twist")
                legacy_subscribers[f"/{name}/cmd_vel"] = [endpoint(entry) for entry in legacy]
            return all(len(rows) == 1 for rows in (*publishers.values(), *subscribers.values()))

        self._wait(ready, 10., "unique native drive target/status endpoints were not discovered")
        receipt = {"schema": "mr3-drive-topology-v1", "epoch": self.epoch,
                   "clock_ns": self.clock_ns, "publishers": publishers,
                   "target_subscribers": subscribers, "legacy_subscribers": legacy_subscribers}
        with (self.directory / "drive_topology.json").open("x") as output:
            json.dump(receipt, output, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")

    def _start_step_helper(self):
        output = (self.directory / "step_helper.log").open("x")
        self.outputs.append(output)
        self.helper = subprocess.Popen([
            "ros2", "run", "multi_robot", "mr3_gazebo_step", "--jsonl", "--world",
            f"p1c_{self.scene}", "--epoch", self.epoch, "--timeout-sec", "10"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=output)
        self.helper_peer = ipc.JsonLinePeer(self.helper.stdout.fileno(),
                                            self.helper.stdin.fileno())

    def _align_initial_clock(self):
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

    def reset(self):
        self._wait(lambda: self.monitor_ready and self.initial_inputs_ready is not None
                   and self.motion_ready and self.odometry_recorder_ready,
                   400., "three-robot delivered-input startup guard expired")
        self.verify_motion_output_topology()
        self.verify_drive_topology()
        self._start_step_helper()
        receipt = self._physics(0, wait_clock=False)
        if receipt["end_time_ns"] / 1e9 < self.initial_inputs_ready["stamp"] - 1e-8:
            raise RuntimeError("initial input acknowledgement is ahead of physical pause")
        self._align_initial_clock()
        # Freeze already-issued T0 output. Re-running the timer here could
        # overwrite a clock which its real observers have already acknowledged.
        identity = f"takeover{self.physical_ns}"
        takeover = self._control_rpc("motion", "takeover", request_id=identity)
        if takeover is None or takeover["status"].get("phase_kind") == "stop":
            raise RuntimeError("motion stopped during controlled execution takeover")
        self.receive_motion_status(takeover["status"])
        if any(output != {"linear_x": 0., "angular_z": 0.}
               for output in takeover["status"]["outputs"].values()):
            raise RuntimeError("pre-release takeover contains a nonzero actuator target")
        self.takeover_acks = {"motion": takeover}
        references = ({"expected_intents": takeover["status"]["intent_refs"]}
                      if getattr(self, "safety_contract", "legacy") == "mr3-reach-v1" else {})
        self.takeover_acks["state"] = self._control_rpc("state", "takeover", request_id=identity, **references)
        self.takeover_acks["peer"] = self._control_rpc("peer", "takeover", request_id=identity)
        self.controlled = True
        self.execution_request_id = identity
        self.bootstrap_pending = True
        self.wait_drive_phase(takeover["status"])
        self._physics(20)
        initial_motion_status = self._execution_motion()
        if initial_motion_status["ready"] is not True or self.stopping:
            raise RuntimeError("initial controlled motion inputs are not ready for task release")
        initial_drive_receipts = self.wait_drive_phase(initial_motion_status)
        self._snapshot()
        if self.watermarks["state_sequence"] < self.initial_inputs_ready["state_sequence"]:
            raise RuntimeError("initial snapshot predates delivered-input acknowledgement")
        self.start_ns = self.physical_ns
        self._wait(lambda: self.reward_ready is not None, 10.,
                   "evaluator did not acknowledge the task release")
        if abs(self.reward_ready["start_sim_time"] - self.start_ns / 1e9) > 1e-8:
            raise RuntimeError("reward epoch start differs from the frozen initial snapshot")
        if getattr(self, "safety_contract", "legacy") == "mr3-reach-v1":
            self._wait(lambda: self.release_intent_refs(self.start_ns) is not None, 10.,
                       "three actual owner post-release HOLD intents were not delivered")
            with self.condition:
                self.bootstrap_intent_refs = self.release_intent_refs(self.start_ns)
                if self.bootstrap_intent_refs is None:
                    raise RuntimeError("post-release intent bootstrap changed before capture")
                self._trace_control_phase("release_intents_captured", release_clock_ns=self.start_ns,
                                          intent_refs=self.bootstrap_intent_refs)
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
                      "drive_phase_protocol": DRIVE_PROTOCOL,
                      "initial_drive_receipts": initial_drive_receipts,
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

    def shutdown_episode(self, reason, infrastructure=False):
        from run_mr3_adapter_probe import native_stop_receipt
        start = time.monotonic()
        if getattr(self, "controlled", False):
            self._commit_stop(reason)
        if infrastructure:
            self._wait(lambda: self.infrastructure_abort_pub.get_subscription_count() > 0,
                       10., "infrastructure abort evaluator subscriber unavailable")
            self._publish(self.infrastructure_abort_pub, {
                "epoch": self.epoch, "reason": "infrastructure_failure", "operation": "begin"})
            self._wait(lambda: self.finalize_ack is not None and self.finalize_ack.get("kind") in (
                "training_infrastructure_abort_started", "training_infrastructure_abort_error"),
                10., "infrastructure abort begin acknowledgement missing")
            if self.finalize_ack["kind"] != "training_infrastructure_abort_started":
                raise RuntimeError("evaluator rejected infrastructure abort: "
                                   + json.dumps(self.finalize_ack))
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
        if infrastructure:
            self.finalize_request = {"epoch": self.epoch, "reason": reason,
                                     "operation": "finalize"}
            self._publish(self.infrastructure_abort_pub, self.finalize_request)
        else:
            self._publish(self.finalize_pub, self.finalize_request)
        wait = min(45., max(.001, self.cleanup_deadline - time.monotonic())) if (
            getattr(self, "cleanup_mode", False)) else 45.
        self.launch.wait(timeout=wait)
        launch_text = (self.directory / "launch.log").read_text(errors="replace")
        failures = native_launch_failures(launch_text)
        native_stop = native_stop_receipt(launch_text)
        (self.directory / "native_stop.json").write_text(json.dumps(native_stop, indent=2) + "\n")
        if failures or self.launch.returncode != 0:
            raise RuntimeError("native shutdown failed: " + repr(failures))
        expected_ack = ("training_infrastructure_abort_ack" if infrastructure
                        else "training_finalize_ack")
        if not self.finalize_ack or self.finalize_ack.get("kind") != expected_ack:
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

    def abort_cleanup(self, error):
        """Attempt real zero/goal/native closure without inventing a reset or reward.

        A failed attempt stays an infrastructure failure. The parent retains its
        existing bounded owned-process fallback if any required endpoint is gone.
        """
        self.cleanup_mode = True
        self.cleanup_deadline = time.monotonic() + 60.
        self.control_phase.abandon_for_stop()
        self._trace_control_phase("infrastructure_abort_started", error=repr(error))
        if self.helper is None:
            self._start_step_helper()
            self._physics(0, wait_clock=False)
            self._align_initial_clock()
        if self.clock_ns != self.physical_ns:
            raise RuntimeError("cannot stop infrastructure failure without an exact paused clock")
        self.controlled = True
        self._commit_stop("infrastructure_failure")
        response = getattr(self, "last_reward_response", None)
        if response and (response.get("terminated") or response.get("truncated")):
            # A ledger already sealed by a real reward response keeps its
            # original finalization protocol. The surrounding RPC stays failed.
            self.shutdown_episode("task_terminal" if response["terminated"]
                                  else "external_truncation")
        else:
            self.shutdown_episode("infrastructure_failure", infrastructure=True)
        self._trace_control_phase("infrastructure_abort_closed", invalid_sample=True)

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
            if worker is not None and not worker.finished:
                cleanup = {"epoch": worker.epoch, "original_error": repr(error),
                           "scope": "best-effort ordered invalid-sample cleanup; no reward/sample",
                           "wall_guard_sec": 60., "passed": False}
                started = time.monotonic()
                try:
                    worker.abort_cleanup(error)
                    worker.close()
                    cleanup["passed"] = True
                except Exception as cleanup_error:
                    cleanup["cleanup_error"] = repr(cleanup_error)
                cleanup["wall_sec"] = time.monotonic() - started
                (args.run_dir / "infrastructure_cleanup.json").write_text(
                    json.dumps(cleanup, indent=2) + "\n")
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
