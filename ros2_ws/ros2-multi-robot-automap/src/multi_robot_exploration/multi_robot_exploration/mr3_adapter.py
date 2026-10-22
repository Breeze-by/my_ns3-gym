"""Ideal MR3 policy boundary; only explicit joint actions select exploration goals.

ROS action clients below are the ideal robot execution endpoints. Receipts pass
through the same ideal transport before updating the backend dispatcher. P3A
will split these endpoints and serialize bytes; this node claims no DDS isolation.
"""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import math
from pathlib import Path
from time import monotonic

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, Header, String

from multi_robot_exploration.mr3_observation import (
    build_snapshot, NAVIGATION_COMPOSITION_VERSION, SEED_RULES,
)
from multi_robot_exploration.mr3_observation_archive import archive_snapshot_inputs
from multi_robot_exploration.mr3_information import map_digest, map_payload
from multi_robot_exploration.mr3_owner import acquire_navigation_owner
from multi_robot_exploration.mr3_activity import ReceivedActivity
from multi_robot_exploration.mr3_protocol import GoalDispatcher
from multi_robot_exploration.mr3_episode import (
    TASK_DURATION_NS, TASK_FAILURE_REASONS, elapsed_ns, timestamp_ns,
)
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


ROBOTS = ("tb1", "tb2", "tb3")


def encode_snapshot(*args, archive=None, **kwargs):
    """Encode and archive the same frozen inputs without accessing live ROS state."""
    snapshot = build_snapshot(*args, **kwargs)
    if archive is not None:
        archive_snapshot_inputs(snapshot=snapshot, **archive)
    return snapshot


class MR3Adapter(Node):
    def __init__(self):
        super().__init__("mr3_adapter")
        self.navigation_owner = acquire_navigation_owner()
        if self.declare_parameter("robot_count", 3).value != 3:
            raise ValueError("MR3 adapter requires exactly three robots")
        self.epoch = str(self.declare_parameter("episode_epoch", "mr3-p1b").value)
        self.stepped_mode = self.declare_parameter("stepped_mode", False).value
        self.seed_rule = self.declare_parameter("seed_rule", "legacy").value
        if type(self.seed_rule) is not str or self.seed_rule not in SEED_RULES:
            raise ValueError("seed_rule must be legacy, exact-point-bridge-v1 or exact-point-bridge-v2")
        if self.seed_rule != "legacy" and not self.stepped_mode:
            raise ValueError("exact-point-bridge rules require stepped mode")
        self.snapshot_timeout_sec = self.declare_parameter("snapshot_timeout_sec", 10.).value
        if not math.isfinite(self.snapshot_timeout_sec) or self.snapshot_timeout_sec <= 0:
            raise ValueError("snapshot_timeout_sec must be finite and positive")
        self.pending_snapshot = None
        self.encoding_request = None
        self.snapshot_responses = {}
        self.map_metadata = None
        self.last_snapshot_target_ns = None
        self.initial_inputs_ready = False
        self.task_terminal_notice = None
        self.pending_task_terminal_notice = None
        self.require_monitor = self.declare_parameter("require_task_monitor_ready", False).value
        self.monitor_ready = not self.require_monitor
        audit_path = self.declare_parameter("audit_path", "").value
        self.audit_file = None
        if audit_path:
            Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
            self.audit_file = open(audit_path, "x", buffering=1)
        self.events = deque()
        self.dispatcher = GoalDispatcher(
            self.epoch, self.events.append,
            response_timeout_sec=self.declare_parameter(
                "navigation_response_timeout_sec", 10.).value,
            cancel_timeout_sec=self.declare_parameter("navigation_cancel_timeout_sec", 10.).value,
            execution_timeout_sec=self.declare_parameter("goal_timeout_sec", 60.).value,
        )
        self.transport = IdealTransport(self.epoch)
        self.received = ReceivedStore(self.epoch)
        self.navigation_clients = {
            name: ActionClient(self, NavigateToPose, f"/{name}/navigate_to_pose")
            for name in ROBOTS
        }
        self.handles = {}
        self.map = None
        self.map_digest = None
        self.local_maps = {}
        self.local_map_digests = {}
        self.navigation_maps = {}
        self.navigation_map_digests = {}
        self.state = None
        self.snapshot = None
        self.sequence = 0
        self.started_at = None
        self.stop_requested = False
        self.stop_acknowledged = False
        self.pending_stop = None
        self.last_command_id = -1
        self.command_receipt = None
        self.command_payload = None
        self.last_heartbeat = -math.inf
        self.receipt_metadata = {name: {} for name in ROBOTS}
        self.history = {name: deque(maxlen=16) for name in ROBOTS}
        self.activity = ReceivedActivity(self.epoch)
        self.encoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mr3_observation")
        self.encoding = None
        task_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.observation_pub = self.create_publisher(String, "/mr3/observation", 2)
        self.snapshot_response_pub = self.create_publisher(String, "/mr3/snapshot_response", 2)
        self.initial_inputs_ready_pub = self.create_publisher(
            String, "/mr3/initial_inputs_ready", task_qos)
        self.event_pub = self.create_publisher(String, "/mr3/events", 100)
        self.start_pub = self.create_publisher(Header, "/exploration_start", task_qos)
        self.stop_pub = self.create_publisher(String, "/exploration_stopped", task_qos)
        self.failure_pub = self.create_publisher(String, "/exploration_failure", task_qos)
        self.subscriptions_ = [
            self.create_subscription(
                OccupancyGrid, "/mr3/received/map", self.receive_map, task_qos),
            self.create_subscription(String, "/mr3/received/states", self.receive_states, 10),
            self.create_subscription(String, "/mr3/action", self.receive_action, 10),
            self.create_subscription(
                String, "/mr3/snapshot_request", self.receive_snapshot_request, 2),
            self.create_subscription(
                String, "/mr3/map_metadata", self.receive_map_metadata, task_qos),
            self.create_subscription(Bool, "/task_monitor_ready", self.receive_ready, task_qos),
            self.create_subscription(
                String, "/mr3/task_terminal", self.receive_task_terminal, task_qos),
            self.create_subscription(
                Header, "/exploration_stop_request", self.receive_stop, task_qos),
            self.create_subscription(
                String, "/exploration_failure", self.receive_failure, task_qos),
        ]
        self.subscriptions_.extend(self.create_subscription(
            OccupancyGrid, f"/mr3/received/{name}/map",
            lambda message, name=name: self.receive_local_map(name, message), task_qos,
        ) for name in ROBOTS)
        self.subscriptions_.extend(self.create_subscription(
            OccupancyGrid, f"/{name}/navigation_map",
            lambda message, name=name: self.receive_navigation_map(name, message), task_qos,
        ) for name in ROBOTS)
        timer_clock = Clock(clock_type=ClockType.STEADY_TIME) if self.stepped_mode else None
        self.timer = self.create_timer(
            .02 if self.stepped_mode else .05, self.maintain, clock=timer_clock)
        self.observation_timer = None
        if not self.stepped_mode:
            self.observation_timer = self.create_timer(1., self.publish_observation)

    def receive_map_metadata(self, message):
        try:
            metadata = json.loads(message.data)
            if metadata["epoch"] == self.epoch:
                self.map_metadata = metadata
        except (ValueError, KeyError, TypeError):
            self.record("invalid_map_metadata", {})

    def receive_snapshot_request(self, message):
        try:
            request = json.loads(message.data)
            if not self.stepped_mode or request["epoch"] != self.epoch:
                raise ValueError("wrong_mode_or_epoch")
            if not isinstance(request["request_id"], str) or not request["request_id"]:
                raise ValueError("invalid_request_id")
            if type(request["target_time_ns"]) is not int or request["target_time_ns"] < 0:
                raise ValueError("invalid_target_time")
            if type(request.get("minimum_state_sequence", -1)) is not int:
                raise ValueError("invalid_minimum_state_sequence")
            if type(request.get("allow_terminal", False)) is not bool:
                raise ValueError("invalid_allow_terminal")
            expected = request.get("expected_map_sha256")
            if expected is not None and (
                    not isinstance(expected, str) or len(expected) != 64
                    or any(char not in "0123456789abcdef" for char in expected)):
                raise ValueError("invalid_expected_map_sha256")
            cached = self.snapshot_responses.get(request["request_id"])
            if cached is not None:
                if cached["target_time_ns"] != request["target_time_ns"]:
                    raise ValueError("request_id_conflict")
                self.snapshot_response_pub.publish(String(data=json.dumps(cached)))
                return
            previous = self.last_snapshot_target_ns
            if previous is not None and request["target_time_ns"] <= previous:
                raise ValueError("snapshot_target_not_advanced")
            if self.pending_snapshot is not None:
                if self.pending_snapshot["request_id"] == request["request_id"]:
                    if self.pending_snapshot["target_time_ns"] != request["target_time_ns"]:
                        raise ValueError("request_id_conflict")
                    return
                raise ValueError("snapshot_busy")
            self.pending_snapshot = {**request, "requested_wall": monotonic()}
            self.record("snapshot_requested", request)
        except (ValueError, KeyError, TypeError) as error:
            response = {"epoch": self.epoch, "ok": False, "error": str(error)}
            try:
                response.update({key: request.get(key)
                                 for key in ("request_id", "target_time_ns")})
            except (UnboundLocalError, AttributeError):
                pass
            self.snapshot_response_pub.publish(String(data=json.dumps(response)))

    def poll_snapshot(self):
        request = getattr(self, "pending_snapshot", None)
        if request is None or self.encoding is not None:
            return
        now_ns = self.get_clock().now().nanoseconds
        reason = None
        if now_ns > request["target_time_ns"]:
            reason = "snapshot_target_already_passed"
        elif monotonic() - request["requested_wall"] >= self.snapshot_timeout_sec:
            reason = "snapshot_watermark_timeout"
        elif now_ns == request["target_time_ns"] and (
                self.states_fresh(now_ns / 1e9) or self.terminal_snapshot_allowed()):
            minimum = request.get("minimum_state_sequence", -1)
            expected = request.get("expected_map_sha256")
            map_matches = expected is None or (
                self.map_metadata is not None
                and self.map_metadata.get("map_payload_sha256") == expected
                and self.map_digest == expected)
            if map_matches and self.state["sequence"] > minimum:
                self.publish_observation()
                if self.encoding is not None:
                    self.encoding_request = {
                        **request, "state_sequence": self.state["sequence"],
                        "map_payload_sha256": self.map_digest,
                    }
        if reason is not None:
            self.respond_snapshot(request, error=reason)

    def terminal_snapshot_allowed(self):
        request = getattr(self, "pending_snapshot", None)
        return bool(request and request.get("allow_terminal") is True
                    and self.started_at is not None and self.task_terminal_notice is not None
                    and timestamp_ns(self.task_terminal_notice["end_sim_time_sec"])
                    <= self.get_clock().now().nanoseconds)

    def respond_snapshot(self, request, snapshot=None, error=None):
        response = {"epoch": self.epoch, "request_id": request["request_id"],
                    "target_time_ns": request["target_time_ns"], "ok": error is None}
        if error is not None:
            response["error"] = error
            if error == "snapshot_watermark_timeout":
                response["diagnostics"] = self.snapshot_diagnostics(request)
        else:
            response["snapshot"] = snapshot
            self.last_snapshot_target_ns = request["target_time_ns"]
            response["watermarks"] = {
                "state_sequence": request["state_sequence"],
                "map_payload_sha256": request["map_payload_sha256"],
                "map_version": snapshot["map_version"], "map_sources": snapshot["map"]["sources"],
                "robots": [{key: robot[key] for key in
                            ("name", "source_stamp", "received_stamp")}
                           for robot in snapshot["robots"]],
            }
            if "navigation_sources" in snapshot:
                response["watermarks"]["navigation_sources"] = snapshot["navigation_sources"]
        self.snapshot_responses[request["request_id"]] = response
        while len(self.snapshot_responses) > 16:
            del self.snapshot_responses[next(iter(self.snapshot_responses))]
        self.pending_snapshot = None
        self.encoding_request = None
        self.snapshot_response_pub.publish(String(data=json.dumps(response, allow_nan=False)))
        self.record("snapshot_completed", {key: value for key, value in response.items()
                                           if key != "snapshot"})

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def record(self, kind, payload):
        row = {"kind": kind, "stamp": self.now(), "epoch": self.epoch, "payload": payload}
        if self.audit_file:
            self.audit_file.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        if kind not in ("observation", "state_update"):
            message = String()
            message.data = json.dumps(row, sort_keys=True, allow_nan=False)
            self.event_pub.publish(message)

    def receive_map(self, message):
        self.map = message
        self.map_digest = map_digest(message)

    def receive_local_map(self, name, message):
        self.local_maps[name] = message
        self.local_map_digests[name] = map_digest(message)

    def receive_navigation_map(self, name, message):
        self.navigation_maps[name] = message
        self.navigation_map_digests[name] = map_digest(message)

    def receive_states(self, message):
        try:
            state = json.loads(message.data)
            if (state["epoch"] == self.epoch
                    and {r["name"] for r in state["robots"]} == set(ROBOTS)
                    and (self.state is None or state["sequence"] > self.state["sequence"])):
                self.state = state
                self.record("state_update", {
                    "sequence": state["sequence"],
                    "information_diagnostics": state.get("information_diagnostics"),
                    "robots": [{key: robot.get(key) for key in (
                        "name", "source_stamp", "received_stamp", "odom_source_stamp",
                        "tf_source_stamp", "tf_validity_stamp", "valid", "epoch", "odometry")}
                        for robot in state["robots"]],
                })
                activity = self.activity.update(state, self.now())
                if activity is not None:
                    self.record("activity_update", activity)
                for robot in state["robots"]:
                    history = self.history[robot["name"]]
                    if robot["valid"] and (not history or
                                           robot["source_stamp"] > history[-1]["source_stamp"]):
                        history.append({key: robot[key] for key in ("x", "y", "source_stamp")})
        except (ValueError, KeyError, TypeError):
            self.record("invalid_state", {})

    def receive_ready(self, message):
        self.monitor_ready = bool(message.data)

    def receive_task_terminal(self, message):
        """Accept only the isolated evaluator's epoch-bound, scalar terminal."""
        try:
            notice = json.loads(message.data)
            if not isinstance(notice, dict) or set(notice) != {
                    "epoch", "end_sim_time_sec", "termination_reason"}:
                raise ValueError("invalid_task_terminal_fields")
            if not self.stepped_mode or notice["epoch"] != self.epoch:
                return
            if self.started_at is None:
                raise ValueError("task_terminal_before_release")
            if (notice["termination_reason"] not in TASK_FAILURE_REASONS
                    and notice["termination_reason"] != "coverage_reached"):
                raise ValueError("invalid_task_terminal_reason")
            if timestamp_ns(notice["end_sim_time_sec"]) < timestamp_ns(self.started_at):
                raise ValueError("task_terminal_precedes_release")
            previous = self.task_terminal_notice or self.pending_task_terminal_notice
            if previous is not None:
                if previous != notice:
                    raise ValueError("conflicting_task_terminal")
                return
            self.pending_task_terminal_notice = notice
            self.record("task_terminal_received", notice)
            self.poll_task_terminal()
        except (ValueError, TypeError, KeyError) as error:
            self.record("invalid_task_terminal", {"reason": str(error)})

    def poll_task_terminal(self):
        notice = self.pending_task_terminal_notice
        if (notice is None or self.started_at is None
                or timestamp_ns(notice["end_sim_time_sec"]) > self.get_clock().now().nanoseconds):
            return
        self.pending_task_terminal_notice = None
        self.task_terminal_notice = notice
        self.stop_requested = True
        self.dispatcher.safety_stop(self.now(), "task_terminal:" + notice["termination_reason"])
        self.record("task_terminal", notice)

    def receive_stop(self, message):
        stamp = message.stamp.sec + message.stamp.nanosec / 1e9
        if self.started_at is not None and stamp > self.now() and message.frame_id == "map":
            self.pending_stop = message
            return
        if self.started_at is not None and self.started_at <= stamp <= self.now() \
                and message.frame_id == "map":
            self.stop_requested = True
            self.dispatcher.safety_stop(self.now(), "task_stop")

    def receive_failure(self, message):
        self.record("safety_stop", {"reason": message.data})
        self.stop_requested = True
        self.dispatcher.safety_stop(self.now(), "external_safety_failure")

    def map_inputs_match(self, metadata):
        """Require actually delivered fused/own/navigation maps in one bundle."""
        if (self.map is None or metadata is None
                or self.map_digest != metadata.get("map_payload_sha256")):
            return False
        sources = metadata.get("map_sources", {})
        navigation = metadata.get("navigation_sources", {})
        return (metadata.get("navigation_composition", {}).get("version")
                == NAVIGATION_COMPOSITION_VERSION and all(
                    name in self.local_maps and self.local_map_digests.get(name) is not None
                    and self.local_map_digests[name] == sources.get(name, {}).get("payload_sha256")
                    and name in self.navigation_maps
                    and self.navigation_map_digests.get(name) == navigation.get(
                        name, {}).get("payload_sha256")
                    and navigation.get(name, {}).get("composition_version")
                    == NAVIGATION_COMPOSITION_VERSION for name in ROBOTS))

    def publish_initial_inputs_ready(self, now):
        """Acknowledge real input receipt before the worker pauses physics."""
        if (not self.stepped_mode or self.initial_inputs_ready or self.started_at is not None
                or self.stop_requested or not self.monitor_ready or not self.states_fresh(now)
                or not self.map_inputs_match(self.map_metadata)
                or not all(client.server_is_ready()
                           for client in self.navigation_clients.values())):
            return
        metadata = self.map_metadata
        payload = {
            "schema": "mr3-initial-inputs-ready-v1", "epoch": self.epoch, "stamp": now,
            "state_sequence": self.state["sequence"], "map_version": metadata["map_version"],
            "map_payload_sha256": self.map_digest,
            "map_source_stamp": metadata["map_source_stamp"],
            "map_received_stamp": metadata["map_received_stamp"],
            "map_sources": metadata["map_sources"],
            "navigation_composition": metadata["navigation_composition"],
            "navigation_sources": metadata["navigation_sources"],
            "robots": [{key: robot[key] for key in (
                "name", "source_stamp", "received_stamp", "odom_source_stamp",
                "tf_source_stamp", "tf_validity_stamp", "tf_validity_lead_sec",
            ) if key in robot} for robot in self.state["robots"]],
        }
        self.initial_inputs_ready = True
        self.initial_inputs_ready_pub.publish(String(data=json.dumps(payload, allow_nan=False)))
        self.record("initial_inputs_ready", payload)

    def snapshot_diagnostics(self, request):
        """Report actual gate state without manufacturing a delivery or age."""
        now_ns = self.get_clock().now().nanoseconds
        metadata = self.map_metadata if self.stepped_mode else self.state
        sources = metadata.get("map_sources", {}) if metadata is not None else {}
        navigation = metadata.get("navigation_sources", {}) if metadata is not None else {}
        expected = request.get("expected_map_sha256")
        metadata_digest = metadata.get("map_payload_sha256") if metadata is not None else None
        return {
            "actual_clock_ns": now_ns, "state_received": self.state is not None,
            "state_sequence": self.state["sequence"] if self.state is not None else None,
            "states_fresh": self.states_fresh(now_ns / 1e9),
            "state_watermark_satisfied": self.state is not None and (
                self.state["sequence"] > request.get("minimum_state_sequence", -1)),
            "map_received": self.map is not None, "map_payload_sha256": self.map_digest,
            "metadata_received": metadata is not None,
            "metadata_map_payload_sha256": metadata_digest,
            "expected_map_matches": expected is None or (
                metadata_digest == expected and self.map_digest == expected),
            "map_inputs_match": self.map_inputs_match(metadata),
            "local_maps": {name: {
                "received": name in self.local_maps,
                "payload_sha256": self.local_map_digests.get(name),
                "expected_payload_sha256": sources.get(name, {}).get("payload_sha256"),
                "matches": name in self.local_maps and self.local_map_digests.get(name) is not None
                and self.local_map_digests[name] == sources.get(name, {}).get("payload_sha256"),
            } for name in ROBOTS},
            "navigation_maps": {name: {
                "received": name in self.navigation_maps,
                "payload_sha256": self.navigation_map_digests.get(name),
                "expected_payload_sha256": navigation.get(name, {}).get("payload_sha256"),
                "matches": name in self.navigation_maps
                and self.navigation_map_digests.get(name) is not None
                and self.navigation_map_digests[name] == navigation.get(
                    name, {}).get("payload_sha256"),
            } for name in ROBOTS},
            "monitor_ready": self.monitor_ready, "started_at": self.started_at,
            "stop_requested": self.stop_requested,
            "task_terminal_notice": self.task_terminal_notice,
            "pending_task_terminal_notice": self.pending_task_terminal_notice,
            "navigation_servers_ready": {name: client.server_is_ready()
                                         for name, client in self.navigation_clients.items()},
        }

    def publish_observation(self):
        if self.encoding is not None:
            return
        if (self.map is None or self.state is None
                or (not self.monitor_ready and not self.terminal_snapshot_allowed())):
            return
        metadata = self.map_metadata if getattr(self, "stepped_mode", False) else self.state
        if not self.map_inputs_match(metadata):
            return
        map_sources = metadata["map_sources"]
        robots = self.state["robots"]
        now = self.now()
        if self.started_at is None:
            if not self.states_fresh(now):
                return
            if not all(client.server_is_ready() for client in self.navigation_clients.values()):
                return
            if "/headquarters_control" in [
                "/" + n for n, _ in self.get_node_names_and_namespaces()
            ]:
                raise RuntimeError("Handcrafted controller present in adapter mode")
            self.started_at = now
            self.activity.start(now)
            activity = self.activity.update(self.state, now)
            if activity is not None:
                self.record("activity_update", activity)
            start = Header()
            start.stamp = self.get_clock().now().to_msg()
            start.frame_id = "map"
            self.start_pub.publish(start)
            self.record("task_start", {"start_sim_time_sec": now})
        navigation = self.dispatcher.navigation(now)
        robots = [{**robot, "navigation": {
            **navigation[robot["name"]], **self.receipt_metadata[robot["name"]],
            "last_failure": navigation[robot["name"]].get("failure"),
        }, "history": list(self.history[robot["name"]]),
            "activity": self.activity.snapshot(robot["name"])} for robot in robots]
        self.sequence += 1
        path_maps = {}
        navigation_maps = {}
        audit_file = getattr(self, "audit_file", None)
        archive = None
        if audit_file is not None:
            archive = {
                "root": Path(audit_file.name).parent / "observation_inputs",
                "payloads": {"fused": map_payload(self.map)},
                "metadata": copy.deepcopy({
                    "epoch": self.epoch, "map_version": metadata["map_version"],
                    "map_payload_sha256": metadata["map_payload_sha256"],
                    "map_source_stamp": metadata["map_source_stamp"],
                    "map_received_stamp": metadata["map_received_stamp"],
                    "map_sources": map_sources,
                    "navigation_composition": metadata["navigation_composition"],
                    "navigation_sources": metadata["navigation_sources"],
                }),
            }
        for name in ROBOTS:
            message = self.local_maps[name]
            if archive is not None:
                archive["payloads"][name] = map_payload(message)
            path_maps[name] = {
                "grid": np.asarray(message.data, dtype=np.int16).reshape(
                    message.info.height, message.info.width),
                "resolution": message.info.resolution,
                "origin": (message.info.origin.position.x, message.info.origin.position.y),
                "epoch": self.epoch, **map_sources[name],
            }
            navigation_message = self.navigation_maps[name]
            if archive is not None:
                archive["payloads"]["navigation:" + name] = map_payload(navigation_message)
            navigation_maps[name] = {
                "grid": np.asarray(navigation_message.data, dtype=np.int16).reshape(
                    navigation_message.info.height, navigation_message.info.width),
                "resolution": navigation_message.info.resolution,
                "origin": (navigation_message.info.origin.position.x,
                           navigation_message.info.origin.position.y),
                "epoch": self.epoch, **metadata["navigation_sources"][name],
            }
        # CPU map/path encoding must not block source deliveries, lease renewals
        # or action callbacks. The worker receives a detached frozen snapshot.
        self.record("activity_snapshot_bound", {
            "observation_sequence": self.sequence, "state_sequence": self.activity.last_sequence,
        })
        self.encoding = self.encoder.submit(
            encode_snapshot,
            np.asarray(self.map.data, dtype=np.int16).reshape(
                self.map.info.height, self.map.info.width),
            self.map.info.resolution,
            (self.map.info.origin.position.x, self.map.info.origin.position.y),
            robots, now, self.epoch, metadata["map_version"], self.sequence,
            map_source_stamp=metadata["map_source_stamp"],
            map_received_stamp=metadata["map_received_stamp"],
            map_sources=map_sources, task_start=self.started_at,
            robot_maps=path_maps, navigation_maps=navigation_maps, archive=archive,
            **({"seed_rule": self.seed_rule} if self.seed_rule != "legacy" else {}),
        )

    def finish_observation(self):
        if self.encoding is None or not self.encoding.done():
            return
        request = getattr(self, "encoding_request", None)
        try:
            snapshot = self.encoding.result()
        except Exception as error:
            self.encoding = None
            if request is None:
                raise
            self.respond_snapshot(request, error="snapshot_encoding_failed: " + repr(error))
            return
        self.encoding = None
        if request is not None and self.get_clock().now().nanoseconds != request["target_time_ns"]:
            self.respond_snapshot(request, error="clock_advanced_during_snapshot")
            return
        self.snapshot = snapshot
        self.record("observation", snapshot)
        message = String()
        message.data = json.dumps(snapshot, sort_keys=True, allow_nan=False)
        self.observation_pub.publish(message)
        if request is not None:
            self.respond_snapshot(request, snapshot=snapshot)

    def states_fresh(self, now):
        return self.state is not None and len(self.state["robots"]) == 3 and all(
            robot["valid"] and robot["source_stamp"] is not None
            and robot["received_stamp"] is not None
            and 0 <= now - robot["source_stamp"] <= .5
            and 0 <= now - robot["received_stamp"] <= .5
            for robot in self.state["robots"]
        )

    def receive_action(self, message):
        command = None
        try:
            command = json.loads(message.data)
            now = self.now()
            if (self.started_at is not None
                    and elapsed_ns(self.started_at, now) >= TASK_DURATION_NS):
                self.stop_requested = True
                self.dispatcher.safety_stop(now, "task_deadline")
                raise ValueError("task_deadline")
            if command["epoch"] != self.epoch:
                raise ValueError("wrong_epoch")
            command_id = command["command_id"]
            if type(command_id) is not int or command_id < 0:
                raise ValueError("invalid_command_id")
            if command_id == self.last_command_id:
                if json.dumps(command, sort_keys=True) != getattr(self, "command_payload", None):
                    raise ValueError("command_id_conflict")
                self.record("action_duplicate", self.command_receipt)
                return
            if command_id < self.last_command_id:
                raise ValueError("old_command")
            if self.stop_requested or self.started_at is None:
                raise ValueError("not_running")
            times = [command[key] for key in ("created_at", "expires_at")]
            try:
                if any(type(value) not in (int, float) for value in times):
                    raise ValueError("command timestamps must be numeric")
                created_ns, expires_ns = (timestamp_ns(value) for value in times)
            except (ValueError, OverflowError):
                raise ValueError("expired_or_invalid_command_time") from None
            if not (created_ns <= timestamp_ns(now) < expires_ns
                    and 0 < expires_ns - created_ns <= 2_000_000_000):
                raise ValueError("expired_or_invalid_command_time")
            snapshot = self.snapshot
            if (command["observation_sequence"] != snapshot["sequence"]
                    or command["observation_digest"] != snapshot["digest"]):
                raise ValueError("stale_observation")
            action = command["action"]
            if type(action) is not int or not 0 <= action < 1000:
                raise ValueError("invalid_joint_action")
            if not snapshot["joint_action_mask"][action]:
                raise ValueError("masked_action")
            choices = (action // 100, action // 10 % 10, action % 10)
            navigation = self.dispatcher.navigation(now)
            for robot in snapshot["robots"]:
                old = robot["navigation"]
                current = navigation[robot["name"]]
                if any(old.get(key) != current.get(key) for key in ("phase", "goal_id")):
                    raise ValueError("navigation_changed_since_observation")
            results = {}
            for name, choice in zip(ROBOTS, choices):
                target = snapshot["candidates"][choice] if choice < 8 else None
                results[name] = self.dispatcher.submit(
                    name, "GOAL" if choice < 8 else "KEEP" if choice == 8 else "WAIT",
                    now, snapshot["sequence"], command_id, command["expires_at"],
                    goal={"x": target["x"], "y": target["y"]} if target else None,
                    command_epoch=self.epoch, created_at=command["created_at"],
                )
            self.last_command_id = command_id
            self.command_payload = json.dumps(command, sort_keys=True)
            self.command_receipt = {
                "command_id": command_id, "action": action, "results": results,
                "observation_sequence": snapshot["sequence"],
                "observation_digest": snapshot["digest"],
                "candidate_version": snapshot["candidate_version"], "choices": list(choices),
            }
            self.record("action", self.command_receipt)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            identity = {}
            for key in ("command_id", "observation_sequence"):
                value = command.get(key) if isinstance(command, dict) else None
                identity[key] = value if type(value) is int and value >= 0 else None
            self.record("action_rejected", {"reason": str(error), **identity})

    def receipt(self, kind, robot, goal_id, value):
        # Ideal receipt delivery: preserves source time and identity. P3A moves
        # this endpoint to the robot edge; no Future is exposed to the policy.
        now = self.now()
        self.transport.send("receipt", robot, {
            "type": kind, "robot": robot, "goal_id": goal_id, "value": value,
        }, source_stamp=now, now=now)

    def accepted(self, future, robot, goal_id):
        try:
            handle = future.result()
            if handle.accepted:
                self.handles[goal_id] = handle
                result = handle.get_result_async()
                result.add_done_callback(lambda f: self.completed(f, robot, goal_id))
            self.receipt("accept", robot, goal_id, bool(handle.accepted))
        except Exception as error:
            self.record("rpc_error", {"reason": repr(error), "goal_id": goal_id})
            self.dispatcher.fail(robot, self.now(), "accept_rpc_error")
            self.stop_requested = True

    def completed(self, future, robot, goal_id):
        try:
            self.receipt("result", robot, goal_id, int(future.result().status))
            self.handles.pop(goal_id, None)
        except Exception as error:
            self.record("rpc_error", {"reason": repr(error), "goal_id": goal_id})
            self.stop_requested = True
            self.dispatcher.fail(robot, self.now(), "result_rpc_error")

    def canceled(self, future, robot, goal_id):
        try:
            response = future.result()
            handle = self.handles.get(goal_id)
            accepted = handle is not None and any(
                bytes(entry.goal_id.uuid) == bytes(handle.goal_id.uuid)
                for entry in response.goals_canceling)
            self.receipt("cancel", robot, goal_id, accepted)
        except Exception as error:
            self.record("rpc_error", {"reason": repr(error), "goal_id": goal_id})
            self.stop_requested = True
            self.dispatcher.fail(robot, self.now(), "cancel_rpc_error")

    def flush_protocol_events(self, now):
        while self.events:
            event = self.events.popleft()
            self.record("protocol", event)
            kind = event["type"]
            name = event.get("robot")
            if kind in ("send_goal", "cancel_goal"):
                self.transport.send("command", name, event, source_stamp=event["stamp"], now=now)
            elif kind == "protocol_failure":
                self.stop_requested = True
                message = String()
                message.data = json.dumps(event)
                self.failure_pub.publish(message)

    def maintain(self):
        now = self.now()
        self.poll_task_terminal()
        self.publish_initial_inputs_ready(now)
        self.finish_observation()
        self.poll_snapshot()
        if self.started_at is None and not self.stop_requested:
            return
        if (self.started_at is not None and elapsed_ns(self.started_at, now) >= TASK_DURATION_NS
                and not self.stop_requested):
            self.stop_requested = True
            self.dispatcher.safety_stop(now, "task_deadline")
        if self.pending_stop is not None:
            pending = self.pending_stop
            stamp = pending.stamp.sec + pending.stamp.nanosec / 1e9
            if stamp <= now:
                self.pending_stop = None
                self.receive_stop(pending)
        if not self.stop_requested and not self.states_fresh(now):
            self.record("state_stale", {
                "state_sequence": self.state["sequence"] if self.state else None,
                "robots": [{key: robot.get(key) for key in (
                    "name", "source_stamp", "received_stamp", "odom_source_stamp",
                    "tf_source_stamp", "tf_validity_stamp", "valid")}
                    for robot in self.state["robots"]] if self.state else [],
            })
            self.stop_requested = True
            self.dispatcher.safety_stop(now, "received_state_stale")
            failure = String()
            failure.data = json.dumps({
                "component": "mr3_adapter", "reason": "received_state_stale"})
            self.failure_pub.publish(failure)
        heartbeat_due = (not math.isfinite(self.last_heartbeat)
                         or elapsed_ns(self.last_heartbeat, now) >= 200_000_000)
        if heartbeat_due and not self.stop_requested:
            self.last_heartbeat = now
            for name, nav in self.dispatcher.navigation(now).items():
                if nav["goal_id"] and nav["phase"] in ("active", "accepting"):
                    self.transport.send("heartbeat", name, {
                        "goal_id": nav["goal_id"],
                        "expires_at": (timestamp_ns(now) + 2_000_000_000) / 1e9,
                    }, source_stamp=now, now=now)
        self.dispatcher.tick(now)
        self.flush_protocol_events(now)
        for envelope in self.transport.deliver(self.received, now):
            self.record("delivery", envelope.to_dict())
            event = envelope.payload
            name = envelope.source
            goal_id = event.get("goal_id")
            if envelope.stream == "heartbeat":
                self.dispatcher.renew(name, goal_id, self.epoch, now, event["expires_at"])
            elif envelope.stream == "receipt":
                self.receipt_metadata[name] = {
                    "source_stamp": envelope.source_stamp,
                    "received_stamp": envelope.received_stamp,
                    "sequence": envelope.sequence,
                }
                callback = {
                    "accept": self.dispatcher.on_accept, "result": self.dispatcher.on_result,
                    "cancel": self.dispatcher.on_cancel_response,
                }[event["type"]]
                callback(name, goal_id, event["value"], now)
            elif event["type"] == "send_goal":
                navigation = self.dispatcher.navigation(now)[name]
                if self.dispatcher.stopped or navigation["cancel_requested"]:
                    self.record("edge_goal_not_sent", {"goal_id": goal_id, "reason": "stopped"})
                    self.dispatcher.on_result(name, goal_id, "CANCELED", now)
                    continue
                if timestamp_ns(event["expires_at"]) <= timestamp_ns(now):
                    self.record("edge_goal_not_sent", {"goal_id": goal_id, "reason": "expired"})
                    self.dispatcher.on_accept(name, goal_id, False, now)
                    continue
                pose = PoseStamped()
                pose.header.frame_id = "map"
                pose.header.stamp = self.get_clock().now().to_msg()
                pose.pose.position.x = float(event["goal"]["x"])
                pose.pose.position.y = float(event["goal"]["y"])
                pose.pose.orientation.w = 1.
                goal = NavigateToPose.Goal()
                goal.pose = pose
                self.record("native_send", {"robot": name, "goal_id": goal_id,
                                            "command_id": event["command_id"],
                                            "pose": {
                                                "frame_id": goal.pose.header.frame_id,
                                                "stamp": now,
                                                "x": goal.pose.pose.position.x,
                                                "y": goal.pose.pose.position.y,
                                                "orientation": [
                                                    goal.pose.pose.orientation.x,
                                                    goal.pose.pose.orientation.y,
                                                    goal.pose.pose.orientation.z,
                                                    goal.pose.pose.orientation.w,
                                                ],
                                            }})
                self.navigation_clients[name].send_goal_async(goal).add_done_callback(
                    lambda future, name=name, goal_id=goal_id: self.accepted(
                        future, name, goal_id))
            elif event["type"] == "cancel_goal" and goal_id in self.handles:
                payload = {"robot": name, "goal_id": goal_id, "stamp": now,
                           "scope": "native_cancel_call_attempt"}
                if "command_id" in event:
                    payload["command_id"] = event["command_id"]
                self.record("native_cancel", payload)
                self.handles[goal_id].cancel_goal_async().add_done_callback(
                    lambda future, name=name, goal_id=goal_id: self.canceled(
                        future, name, goal_id))
        self.flush_protocol_events(now)
        if self.stop_requested and self.dispatcher.closed and not self.stop_acknowledged:
            self.stop_acknowledged = True
            payload = {"epoch": self.epoch,
                       "start_sim_time_sec": self.started_at, "stop_sim_time_sec": now,
                       "pending_goal_count": 0, "robot_names": list(ROBOTS),
                       "navigation_failure": self.dispatcher.failed}
            message = String()
            message.data = json.dumps(payload)
            self.stop_pub.publish(message)
            self.record("task_stopped", payload)

    def destroy_node(self):
        try:
            if self.audit_file:
                self.audit_file.close()
            self.encoder.shutdown(wait=True, cancel_futures=True)
            return super().destroy_node()
        finally:
            self.navigation_owner.close()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = MR3Adapter()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
