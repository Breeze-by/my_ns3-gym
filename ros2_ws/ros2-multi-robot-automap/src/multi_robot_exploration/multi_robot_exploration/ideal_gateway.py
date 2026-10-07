import json
from copy import deepcopy
import math
import os
import zlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from multi_robot_interfaces.msg import GatewayEnvelope
from nav_msgs.msg import OccupancyGrid, Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.serialization import deserialize_message, serialize_message
from std_msgs.msg import String
from rcl_interfaces.msg import SetParametersResult
from rcl_interfaces.srv import SetParametersAtomically
from rclpy.parameter import Parameter
from tf2_msgs.msg import TFMessage

from .fault_model import (
    CHARGE_REQUEST_TTL_SEC, DeterministicFaultTransport, FaultConfig,
    RELIABLE_TYPES, STATE_TYPES, STATE_TTL_SEC, TARGET_DETECTION_TTL_SEC,
    message_id, source_time,
)
from .gateway_config import FAULT_DEFAULTS, configs_for, configuration_snapshot, updated_configuration
from .admission_protocol import (
    AdmissionCoordinator, Candidate, EndpointQueue, CONTROL_TYPES, ORDINARY_TYPES, HEARTBEAT_SEC, LOCAL_CAPACITY,
)


UPLINK_CANDIDATES = "/gateway/uplink/candidates"
UPLINK_DELIVERED = "/gateway/uplink/delivered"
DOWNLINK_CANDIDATES = "/gateway/downlink/candidates"
DOWNLINK_DELIVERED = "/gateway/downlink/delivered"


@dataclass(frozen=True)
class Route:
    message_type: str
    sender: str
    recipient: str
    source_topic: str
    destination_topic: str
    message_class: type
    ttl_sec: float
    transient: bool = False
    min_interval_sec: float = 0.0
    compress: bool = False


def envelope_is_valid(envelope, now_sec, latest_sequence):
    if envelope.payload_length != len(envelope.payload):
        return False, "payload_length_mismatch"
    generated = (
        envelope.generation_time.sec
        + envelope.generation_time.nanosec / 1e9
    )
    if envelope.ttl_sec > 0 and now_sec - generated >= envelope.ttl_sec:
        return False, "expired"
    if envelope.sequence <= latest_sequence:
        return False, "stale_sequence"
    return True, ""


class IdealGateway(Node):
    """
    Explicit message transport and received-information store.

    The default is the P3A zero-loss gateway.  P3B enables the same node with
    deterministic delay/loss parameters; no ROS topic or message meaning
    changes between the two modes.
    """

    def __init__(self):
        super().__init__("ideal_gateway")
        self.robot_count = self.declare_parameter("robot_count", 2).value
        if self.robot_count < 1:
            raise ValueError("robot_count must be positive")

        self.task_phase = "EXPLORE"
        self.admission_protocol_enabled = bool(self.declare_parameter("admission_protocol", False).value)
        self.wire_metadata = {}
        self.seen_controls = set()
        self.next_heartbeat = -math.inf
        self.ack_counter = 0
        self.source_stamps = {}
        self.frame_stamp_offset_sec = float(
            self.declare_parameter("frame_stamp_offset_sec", 0.0).value
        )
        if not math.isfinite(self.frame_stamp_offset_sec) or self.frame_stamp_offset_sec < 0:
            raise ValueError("frame stamp offset must be finite and non-negative")
        self.network_mode = str(
            self.declare_parameter("network_mode", "ideal").value
        ).lower()
        self.mission_mode = str(
            self.declare_parameter("mission_mode", "coverage").value
        ).lower()
        if self.mission_mode not in ("coverage", "target", "rally"):
            raise ValueError("mission_mode must be coverage, target, or rally")
        if self.network_mode not in ("ideal", "fault"):
            raise ValueError("network_mode must be ideal or fault")
        drop_types = tuple(filter(None, str(
            self.declare_parameter("drop_message_types", "").value
        ).split(",")))
        blackout_intervals = tuple(tuple(pair) for pair in json.loads(str(
            self.declare_parameter("blackout_intervals", "[]").value
        )))
        self.fault_epoch = None
        self.fault_blackout_intervals = blackout_intervals
        seed = int(self.declare_parameter("fault_seed", 1).value)
        loss_up = float(self.declare_parameter("uplink_loss_rate", 0.0).value)
        loss_down = float(self.declare_parameter("downlink_loss_rate", 0.0).value)
        delay_up = float(self.declare_parameter("uplink_delay_sec", 0.0).value)
        delay_down = float(self.declare_parameter("downlink_delay_sec", 0.0).value)
        duplicate_rate = float(
            self.declare_parameter("duplicate_rate", 0.0).value
        )
        reorder_window = int(
            self.declare_parameter("reorder_window", 0).value
        )
        reorder_step = float(self.declare_parameter("reorder_step_sec", 0.05).value)
        ack_timeout = float(
            self.declare_parameter("ack_timeout_sec", 5.0).value
        )
        max_retries = int(self.declare_parameter("max_retries", 2).value)
        queue_capacity = int(
            self.declare_parameter("queue_capacity", 0).value
        )
        queue_capacity = queue_capacity if queue_capacity > 0 else 4096
        if self.network_mode == "ideal":
            loss_up = loss_down = 0.0
            delay_up = delay_down = 0.0
            duplicate_rate = 0.0
            reorder_window = 0
            drop_types = ()
            blackout_intervals = ()
            self.fault_blackout_intervals = ()
            queue_capacity = 4096  # Queue overflow is a fault intervention.
        self.ledger_path = str(
            self.declare_parameter("ledger_path", "").value
        )
        self.episode_id = str(self.declare_parameter("episode_id", "episode").value)
        self.gazebo_seed = int(self.declare_parameter("gazebo_seed", 1).value)
        self.world = str(self.declare_parameter("world", "unknown").value)
        if not self.ledger_path:
            session = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
            self.ledger_path = str(Path("/tmp/multi_robot_gateway") / f"{session}_{os.getpid()}" / "messages.jsonl")
        self.ledger_index = 0
        self.configuration_revision = 0
        self.configuration_effective_time = self.now_sec()
        self.requested_fault_configuration = {name: self.get_parameter(name).value for name in FAULT_DEFAULTS}
        self.enable_fault_control = bool(self.declare_parameter("enable_fault_control", True).value)
        self.sequences = {}
        self.latest_sequences = {}
        self.last_generated_at = {}
        self.transport_by_direction = {
            "uplink": DeterministicFaultTransport(
                FaultConfig(
                    loss_rate=loss_up,
                    delay_sec=delay_up,
                    duplicate_rate=duplicate_rate,
                    reorder_window=reorder_window,
                    reorder_step_sec=reorder_step,
                    seed=seed ^ 0x13579BDF,
                    ack_timeout_sec=ack_timeout,
                    max_retries=max_retries,
                    queue_capacity=queue_capacity,
                    drop_types=drop_types,
                    blackout_intervals=(),
                ),
                event_callback=lambda event, direction="uplink": self.publish_transport_event(
                    direction, event
                ),
            ),
            "downlink": DeterministicFaultTransport(
                FaultConfig(
                    loss_rate=loss_down,
                    delay_sec=delay_down,
                    duplicate_rate=duplicate_rate,
                    reorder_window=reorder_window,
                    reorder_step_sec=reorder_step,
                    seed=seed ^ 0x2468ACE0,
                    ack_timeout_sec=ack_timeout,
                    max_retries=max_retries,
                    queue_capacity=queue_capacity,
                    drop_types=drop_types,
                    blackout_intervals=(),
                ),
                event_callback=lambda event, direction="downlink": self.publish_transport_event(
                    direction, event
                ),
            ),
        }
        self.routes = self._routes()
        self.route_by_key = {
            (route.message_type, route.sender, route.recipient): route
            for route in self.routes
        }

        reliable = QoSProfile(depth=100)
        reliable.reliability = ReliabilityPolicy.RELIABLE
        self.candidate_publishers = {
            "uplink": self.create_publisher(
                GatewayEnvelope, UPLINK_CANDIDATES, reliable
            ),
            "downlink": self.create_publisher(
                GatewayEnvelope, DOWNLINK_CANDIDATES, reliable
            ),
        }
        self.delivered_publishers = {
            "uplink": self.create_publisher(
                GatewayEnvelope, UPLINK_DELIVERED, reliable
            ),
            "downlink": self.create_publisher(
                GatewayEnvelope, DOWNLINK_DELIVERED, reliable
            ),
        }
        self.ack_publisher = self.create_publisher(
            GatewayEnvelope, "/gateway/acks", reliable
        )
        self.event_publisher = self.create_publisher(
            String, "/gateway/message_events", reliable
        )
        self.admission_observation_publisher = self.create_publisher(
            String, "/gateway/admission_observation", reliable
        )
        self.admission_coordinator = AdmissionCoordinator(self.emit_control, self._record)
        self.endpoint_queues = {
            f"tb{index+1}": EndpointQueue(f"tb{index+1}", self.emit_control,
                lambda envelope: self.enqueue_transport("uplink", envelope), self._record)
            for index in range(self.robot_count)
        }
        self.create_subscription(
            GatewayEnvelope,
            UPLINK_CANDIDATES,
            lambda message: self.accept_candidate("uplink", message),
            reliable,
        )
        self.create_subscription(
            GatewayEnvelope,
            DOWNLINK_CANDIDATES,
            lambda message: self.accept_candidate("downlink", message),
            reliable,
        )
        self.create_subscription(
            GatewayEnvelope,
            UPLINK_DELIVERED,
            self.receive_envelope,
            reliable,
        )
        self.create_subscription(
            GatewayEnvelope,
            DOWNLINK_DELIVERED,
            self.receive_envelope,
            reliable,
        )

        self.create_subscription(
            String, "/gateway/consumed",
            lambda message: self._record(json.loads(message.data)), reliable,
        )
        self.destination_publishers = {}
        self.source_subscriptions = []
        for route in self.routes:
            qos = self._topic_qos(route.transient)
            self.destination_publishers[
                (route.message_type, route.sender, route.recipient)
            ] = self.create_publisher(
                route.message_class, route.destination_topic, qos
            )
            direction = (
                "uplink" if route.recipient == "headquarters" else "downlink"
            )
            self.source_subscriptions.append(
                self.create_subscription(
                    route.message_class,
                    route.source_topic,
                    lambda message, selected=route, flow=direction: (
                        self.publish_candidate(selected, flow, message)
                    ),
                    qos,
                )
            )

        self.create_subscription(
            String,
            "/task_state",
            self.task_state_callback,
            self._topic_qos(True),
        )
        self.transport_timer = self.create_timer(0.01, self.deliver_queued)
        self.configuration_publisher = self.create_publisher(String, "/gateway/fault_configuration", self._topic_qos(True))
        if self.enable_fault_control:
            self.configuration_service = self.create_service(SetParametersAtomically, "/gateway/configure", self.configure_callback)
        # Startup ROS parameters are immutable. Active faults have one authoritative
        # transactional service, avoiding silently changed but ineffective parameters.
        self.add_on_set_parameters_callback(lambda _: SetParametersResult(
            successful=False, reason="Startup parameters are frozen; use /gateway/configure for communication faults."))
        self.telemetry_timer = self.create_timer(1.0, self.publish_telemetry)
        self._record({"event": "gateway_start", "configuration": self.active_configuration(),
                      "episode_id": self.episode_id, "gazebo_seed": self.gazebo_seed, "world": self.world,
                      "fault_seed": seed, "robot_count": self.robot_count,
                      "ledger_path": self.ledger_path, "fault_control_enabled": self.enable_fault_control,
                      "admission_protocol": self.admission_protocol_enabled,
                      "airtime_model": "unavailable: no PHY/MAC before P4B",
                      "radio_energy_model": "unavailable: task energy is distance/time, not radio joules"})
        self.publish_configuration()
        self.get_logger().info(
            f"Gateway ready for {self.robot_count} robots "
            f"(mode={self.network_mode}, mission_mode={self.mission_mode})."
        )

    def active_configuration(self):
        state = configuration_snapshot(self.requested_fault_configuration, self.transport_by_direction,
                                       self.configuration_revision, self.configuration_effective_time)
        state.update(ledger_path=self.ledger_path, episode_id=self.episode_id, mission_mode=self.mission_mode,
                     gazebo_seed=self.gazebo_seed, world=self.world, fault_seed=self.get_parameter("fault_seed").value,
                     fault_control_enabled=self.enable_fault_control, admission_protocol=self.admission_protocol_enabled)
        return state

    def publish_configuration(self):
        self.configuration_publisher.publish(String(data=json.dumps(self.active_configuration(), sort_keys=True)))

    def configure_callback(self, request, response):
        try:
            changes = {}
            for message in request.parameters:
                parameter = Parameter.from_parameter_msg(message)
                if parameter.name in changes:
                    raise ValueError("duplicate parameter names in atomic request")
                changes[parameter.name] = parameter.value
            expected = changes.pop("expected_revision", self.configuration_revision)
            if type(expected) is not int or expected != self.configuration_revision:
                raise ValueError("configuration revision changed; refresh before applying")
            if not changes:
                response.result = SetParametersResult(successful=True, reason=json.dumps(self.active_configuration(), sort_keys=True))
                return response
            updated = updated_configuration(self.requested_fault_configuration, changes)
            configs = configs_for(updated, int(self.get_parameter("fault_seed").value), self.fault_epoch)
        except (ValueError, TypeError, KeyError) as error:
            response.result = SetParametersResult(successful=False, reason=str(error))
            self._record({"event": "configuration_rejected", "reason": str(error)})
            return response
        # All due old events settle under old faults before the atomic boundary.
        self.deliver_queued()
        self.configuration_revision += 1
        self.configuration_effective_time = self.now_sec()
        for direction, transport in self.transport_by_direction.items():
            transport.reconfigure(configs[direction], self.configuration_revision)
        self.requested_fault_configuration = updated
        self.network_mode = updated["network_mode"]
        self.fault_blackout_intervals = tuple(tuple(pair) for pair in json.loads(updated["blackout_intervals"])) if self.network_mode == "fault" else ()
        state = self.active_configuration()
        self._record({"event": "configuration_applied", "configuration": state, "changes": changes})
        self.publish_configuration()
        response.result = SetParametersResult(successful=True, reason=json.dumps(state, sort_keys=True))
        return response

    def publish_telemetry(self):
        self._record({"event": "metrics_tick", "task_phase": self.task_phase,
                      "queues": {key: transport.queue_state() for key, transport in self.transport_by_direction.items()}})
        if self.admission_protocol_enabled:
            observation = self.admission_coordinator.observation(self.now_sec())
            observation["ap_local_downlink_pending_count"] = 0  # Always-grant local admission is immediate.
            self.admission_observation_publisher.publish(String(data=json.dumps(observation, sort_keys=True)))
            self._record({"event": "admission_observation", "observation": observation})
            self._record({"event": "local_queue_audit", "visibility": "offline audit only; not AP observation",
                          "pending": {robot: len(queue.pending) for robot, queue in self.endpoint_queues.items()}})

    def destroy_node(self):
        for queue in self.endpoint_queues.values():
            queue.close()
        self.ledger_index += 1
        self._write_ledger(json.dumps({"event": "gateway_stop", "event_time": self.now_sec(),
                                     "ledger_index": self.ledger_index, "mission_mode": self.mission_mode}))
        super().destroy_node()

    @staticmethod
    def _topic_qos(transient):
        qos = QoSProfile(depth=10)
        qos.reliability = ReliabilityPolicy.RELIABLE
        if transient:
            qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        return qos

    def _routes(self):
        routes = []
        for index in range(self.robot_count):
            robot = f"tb{index + 1}"
            routes.extend(
                [
                    Route(
                        "map_snapshot",
                        robot,
                        "headquarters",
                        f"/{robot}/map",
                        f"/gateway/received/{robot}/map",
                        OccupancyGrid,
                        STATE_TTL_SEC["map_snapshot"],
                        True,
                        1.0,
                        True,
                    ),
                    Route(
                        "pose_state",
                        robot,
                        "headquarters",
                        f"/{robot}/odom",
                        f"/gateway/received/{robot}/odom",
                        Odometry,
                        STATE_TTL_SEC["pose_state"],
                        min_interval_sec=0.2,
                    ),
                    Route(
                        "frame_state",
                        robot,
                        "headquarters",
                        f"/{robot}/gateway/source_tf",
                        f"/gateway/received/{robot}/tf",
                        TFMessage,
                        STATE_TTL_SEC["frame_state"],
                        min_interval_sec=0.5,
                    ),
                    Route(
                        "battery_state",
                        robot,
                        "headquarters",
                        f"/{robot}/battery_state",
                        f"/gateway/received/{robot}/battery_state",
                        String,
                        STATE_TTL_SEC["battery_state"],
                        True,
                        0.5,
                    ),
                    Route(
                        "fused_map_snapshot",
                        "headquarters",
                        robot,
                        "/merge_map",
                        f"/{robot}/gateway/merge_map",
                        OccupancyGrid,
                        STATE_TTL_SEC["fused_map_snapshot"],
                        True,
                        1.0,
                        True,
                    ),
                    Route(
                        "task_state",
                        "headquarters",
                        robot,
                        "/task_state",
                        f"/{robot}/gateway/task_state",
                        String,
                        10.0,
                        True,
                    ),
                    Route(
                        "charge_request", "headquarters", robot,
                        f"/gateway/request/{robot}/charge",
                        f"/{robot}/gateway/charge_request",
                        String, CHARGE_REQUEST_TTL_SEC,
                    ),
                ]
            )
        routes.extend(
            [
                Route(
                    "target_observation",
                    "robot_detector",
                    "headquarters",
                    "/target_observation",
                    "/gateway/received/target_observation",
                    String,
                    5.0,
                    True,
                ),
                Route(
                    "target_detection",
                    "robot_detector",
                    "headquarters",
                    "/target_detection",
                    "/gateway/received/target_detection",
                    String,
                    TARGET_DETECTION_TTL_SEC,
                    True,
                ),
                Route(
                    "battery_failure",
                    "robot_battery",
                    "headquarters",
                    "/battery_failure",
                    "/gateway/received/battery_failure",
                    String,
                    60.0,
                    True,
                ),
            ]
        )
        return routes

    def now_sec(self):
        return self.get_clock().now().nanoseconds / 1e9

    def task_state_callback(self, message):
        self.task_phase = message.data
        if self.fault_epoch is None and message.data == "EXPLORE":
            self.fault_epoch = self.now_sec()
            intervals = tuple((self.fault_epoch + start, self.fault_epoch + end)
                              for start, end in self.fault_blackout_intervals)
            for transport in self.transport_by_direction.values():
                transport.config = replace(transport.config, blackout_intervals=intervals)
            self._record({"event": "fault_epoch", "event_time": self.fault_epoch,
                          "blackout_intervals": intervals, "reference": "first central EXPLORE",
                          "configuration": self.active_configuration()})
            self.publish_configuration()

    def next_sequence(self, route):
        key = (route.message_type, route.sender, route.recipient)
        self.sequences[key] = self.sequences.get(key, 0) + 1
        return self.sequences[key]

    def publish_candidate(self, route, direction, message):
        key = (route.message_type, route.sender, route.recipient)
        now = self.now_sec()
        # Preserve sensor source stamps; receiving an old sample never renews TTL.
        generated = now
        if isinstance(message, TFMessage):
            relevant = [item for item in message.transforms
                        if item.header.frame_id.lstrip("/").endswith("map")
                        and item.child_frame_id.lstrip("/").endswith("odom")]
            if not relevant:
                return
            # SLAM Toolbox stamps map->odom as scan_time + transform_timeout;
            # that future validity stamp is not the generation time. Only the
            # AP copy is normalized; robot-local Nav2 retains its native TF.
            offset_ns = round(self.frame_stamp_offset_sec * 1e9)
            stamp = relevant[-1].header.stamp
            original = stamp.sec * 10**9 + stamp.nanosec
            if original < offset_ns:
                return
            generated = (original - offset_ns) / 1e9
        elif hasattr(message, "header"):
            stamp = message.header.stamp
            generated = stamp.sec + stamp.nanosec / 1e9
        elif isinstance(message, String):
            try:
                generated = float(json.loads(message.data).get("stamp_sec", now))
            except (ValueError, TypeError, AttributeError):
                pass
        if route.message_type in STATE_TYPES:
            if generated <= self.source_stamps.get(key, -float("inf")):
                return
        # Only eligible new source samples consume the rate-limit window.
        # Interleaved odom/base TF and repeated scans must not starve map/odom.
        if (
            route.min_interval_sec > 0
            and now - self.last_generated_at.get(key, -float("inf"))
            < route.min_interval_sec
        ):
            return
        if isinstance(message, TFMessage):
            # Copy only eligible observations, never every native TF callback.
            message = deepcopy(message)
            for item in message.transforms:
                if (item.header.frame_id.lstrip('/').endswith('map')
                        and item.child_frame_id.lstrip('/').endswith('odom')):
                    original = item.header.stamp.sec*10**9+item.header.stamp.nanosec
                    if original < offset_ns:
                        return
                    item.header.stamp.sec, item.header.stamp.nanosec = divmod(original-offset_ns, 10**9)
        self.last_generated_at[key] = now
        if route.message_type in STATE_TYPES:
            self.source_stamps[key] = generated
        payload = serialize_message(message)
        uncompressed_payload_length = len(payload)
        encoding = "cdr"
        if route.compress:
            payload = zlib.compress(payload, level=1)
            encoding = "cdr+zlib"
        envelope = GatewayEnvelope()
        envelope.message_type = route.message_type
        envelope.sender = route.sender
        if route.message_type == "target_detection":
            try:
                envelope.sender = str(json.loads(message.data)["robot"])
            except (KeyError, TypeError, json.JSONDecodeError):
                pass
        envelope.recipient = route.recipient
        envelope.sequence = self.next_sequence(route)
        envelope.generation_time.sec, envelope.generation_time.nanosec = divmod(
            round(generated * 1e9), 10**9
        )
        envelope.task_phase = (
            message.data
            if route.message_type == "task_state"
            else self.task_phase
        )
        envelope.payload_length = len(payload)
        envelope.encoding = encoding
        envelope.ttl_sec = route.ttl_sec
        envelope.payload = list(payload)
        metadata = self.describe_envelope(envelope, uncompressed_payload_length)
        if isinstance(message, String):
            try:
                robot = json.loads(message.data).get("robot")
                if robot in self.endpoint_queues:
                    metadata["application_robot"] = robot
            except (ValueError, TypeError, AttributeError):
                pass
        self.candidate_publishers[direction].publish(envelope)
        self.publish_event("generated", direction, envelope)

    @staticmethod
    def message_id(envelope):
        return message_id(envelope)

    def accept_candidate(self, direction, envelope):
        self.describe_envelope(envelope)
        if self.admission_protocol_enabled and envelope.message_type in ORDINARY_TYPES:
            identity = message_id(envelope)
            if direction == "uplink":
                queue = self.endpoint_queues.get(envelope.sender)
                if queue is None:
                    self.publish_event("local_discard", direction, envelope,
                                       candidate_id=identity, reason="unknown_endpoint")
                    return
                candidate = Candidate(identity, envelope.message_type, envelope.sender, envelope.recipient,
                    int(envelope.sequence), source_time(envelope), source_time(envelope)+float(envelope.ttl_sec),
                    int(envelope.payload_length), envelope.task_phase)
                queue.offer(candidate, envelope, self.now_sec())
                return
            # AP owns its downlink queue. Local decisions consume no on-wire
            # candidate/request/grant bytes and must not pretend otherwise.
            self._record({"event": "ap_local_admission", "candidate_id": identity,
                          "visibility": "AP local queue", "policy": "always_grant", "local_wait_sec": 0.0})
        self.enqueue_transport(direction, envelope)

    def enqueue_transport(self, direction, envelope):
        self.transport_by_direction[direction].enqueue(
            message_id(envelope), envelope, direction, self.now_sec(),
            reliable=envelope.message_type in RELIABLE_TYPES,
            source_time=source_time(envelope), ttl_sec=float(envelope.ttl_sec),
        )

    def deliver_queued(self):
        if self.admission_protocol_enabled:
            now = self.now_sec()
            for queue in self.endpoint_queues.values():
                queue.tick(now)
            if now >= self.next_heartbeat:
                self.next_heartbeat = now + HEARTBEAT_SEC
                self.admission_coordinator.prune(now)
                for robot, queue in self.endpoint_queues.items():
                    self.emit_control("heartbeat", robot, "headquarters", {"pending_count": len(queue.pending)}, now, 2.0)
                    self.emit_control("heartbeat", "headquarters", robot, {"pending_count": 0}, now, 2.0)
        for direction, transport in self.transport_by_direction.items():
            for attempt in transport.poll(self.now_sec()):
                self.delivered_publishers[direction].publish(attempt.envelope)

    def receive_envelope(self, envelope):
        key = (
            envelope.message_type,
            envelope.sender,
            envelope.recipient,
        )
        direction = "uplink" if envelope.recipient == "headquarters" else "downlink"
        if envelope.message_type in CONTROL_TYPES:
            self.receive_control(direction, envelope)
            return
        if envelope.message_type == "ack":
            try:
                identity = bytes(envelope.payload).decode("utf-8")
            except UnicodeDecodeError:
                return
            reverse = "downlink" if direction == "uplink" else "uplink"
            self.transport_by_direction[reverse].acknowledge(identity, self.now_sec())
            self.ack_publisher.publish(envelope)
            self.publish_event("accepted", direction, envelope)
            return
        # Validate before acknowledging: an expired reliable packet must be retried
        # or reported failed instead of being silently accepted.
        latest = self.latest_sequences.get(key, 0)
        valid, reason = envelope_is_valid(envelope, self.now_sec(), latest)
        if not valid:
            if reason == "stale_sequence" and envelope.message_type in RELIABLE_TYPES:
                self.publish_ack(envelope, direction)
            self.publish_event(reason, direction, envelope)
            return
        if envelope.message_type in RELIABLE_TYPES:
            self.publish_ack(envelope, direction)
        if envelope.message_type.startswith("navigation_"):
            return  # Robot adapter owns command deduplication and decode results.
        route = self.route_by_key.get(key)
        if route is None and envelope.message_type == "target_detection":
            route = self.route_by_key.get(
                ("target_detection", "robot_detector", "headquarters")
            )
        if route is not None:
            try:
                payload = bytes(envelope.payload)
                if envelope.encoding == "cdr+zlib":
                    payload = zlib.decompress(payload)
                elif envelope.encoding != "cdr":
                    raise ValueError(
                        f"unsupported encoding {envelope.encoding}"
                    )
                message = deserialize_message(payload, route.message_class)
                if envelope.message_type in ("target_detection", "charge_request"):
                    event = json.loads(message.data)
                    event["_gateway"] = {
                        "message_id": message_id(envelope),
                        "source_time": source_time(envelope),
                        "delivery_time": self.now_sec(),
                        "sequence": envelope.sequence,
                    }
                    message.data = json.dumps(event, sort_keys=True)
            except Exception as error:
                self.get_logger().error(
                    f"Failed to decode {envelope.message_type}: {error}"
                )
                self.publish_event("decode_error", direction, envelope)
                return
            route_key = (
                route.message_type,
                route.sender,
                route.recipient,
            )
            self.latest_sequences[key] = envelope.sequence
            self.destination_publishers[route_key].publish(message)
            self.publish_event("accepted", direction, envelope)
            if direction == "uplink" and self.admission_protocol_enabled:
                self.admission_coordinator.note_delivery(envelope.sender, envelope.message_type,
                    message_id(envelope), source_time(envelope), self.now_sec())

    def describe_envelope(self, envelope, uncompressed_payload_length=None):
        identity = message_id(envelope)
        role = (envelope.message_type if envelope.message_type in CONTROL_TYPES else
                "feedback" if envelope.message_type == "ack" else
                "data" if envelope.message_type in ORDINARY_TYPES else "critical-event")
        metadata = self.wire_metadata.setdefault(identity, {
            "message_type": envelope.message_type, "sender": envelope.sender, "recipient": envelope.recipient,
            "direction": "uplink" if envelope.recipient == "headquarters" else "downlink",
            "payload_length": int(envelope.payload_length), "version": int(envelope.sequence),
            "source_time": source_time(envelope), "task_phase": envelope.task_phase,
            "envelope_cdr_bytes": len(serialize_message(envelope)), "control_role": role,
            "deadline": source_time(envelope)+float(envelope.ttl_sec),
            "airtime_sec": None, "radio_energy_j": None,
            "physical_accounting_status": "not modeled before P4B; all control and data bytes retained",
        })
        if uncompressed_payload_length is not None:
            metadata["uncompressed_payload_length"] = uncompressed_payload_length
        elif envelope.encoding != "cdr+zlib":
            metadata.setdefault("uncompressed_payload_length", int(envelope.payload_length))
        metadata["serialization_sec_per_mbps"] = metadata["envelope_cdr_bytes"]*8/1e6
        metadata["tx_energy_j_per_watt_per_mbps"] = metadata["serialization_sec_per_mbps"]
        return metadata

    def emit_control(self, role, sender, recipient, payload, now, ttl, candidate_id=None, control_attempt=1):
        envelope = GatewayEnvelope()
        envelope.message_type, envelope.sender, envelope.recipient = role, sender, recipient
        key = (role, sender, recipient)
        self.sequences[key] = self.sequences.get(key, 0)+1
        envelope.sequence = self.sequences[key]
        envelope.generation_time.sec, envelope.generation_time.nanosec = divmod(round(now*1e9), 10**9)
        envelope.task_phase, envelope.encoding, envelope.ttl_sec = self.task_phase, "utf8+json", float(ttl)
        envelope.payload = list(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        envelope.payload_length = len(envelope.payload)
        metadata = self.describe_envelope(envelope, envelope.payload_length)
        metadata.update(candidate_id=candidate_id, control_attempt=control_attempt)
        direction = "uplink" if recipient == "headquarters" else "downlink"
        self.publish_event("generated", direction, envelope, control_payload=payload)
        self.enqueue_transport(direction, envelope)
        return message_id(envelope)

    def receive_control(self, direction, envelope):
        valid, reason = envelope_is_valid(envelope, self.now_sec(), 0)
        identity = message_id(envelope)
        if not valid:
            self.publish_event(reason, direction, envelope)
            return
        if not self.admission_protocol_enabled or identity in self.seen_controls:
            self.publish_event("stale_sequence", direction, envelope)
            return
        try:
            if envelope.encoding != "utf8+json":
                raise ValueError("invalid control encoding")
            payload = json.loads(bytes(envelope.payload))
            self.publish_event("control_received", direction, envelope)
            if direction == "uplink":
                if envelope.sender not in self.endpoint_queues or envelope.message_type == "grant":
                    raise ValueError("invalid AP control endpoint")
                self.admission_coordinator.receive(envelope.message_type, envelope.sender, payload,
                    self.now_sec(), identity, source_time(envelope))
            elif envelope.sender != "headquarters" or envelope.recipient not in self.endpoint_queues:
                raise ValueError("invalid robot control endpoint")
            elif envelope.message_type == "grant":
                self.endpoint_queues[envelope.recipient].receive_grant(payload, self.now_sec(), identity)
            elif envelope.message_type != "heartbeat":
                raise ValueError("unsupported robot control role")
            elif (set(payload) != {"pending_count"} or type(payload["pending_count"]) is not int
                    or not 0 <= payload["pending_count"] <= LOCAL_CAPACITY):
                raise ValueError("invalid AP heartbeat")
        except (ValueError, TypeError, KeyError) as error:
            self.publish_event("decode_error", direction, envelope, reason=str(error))
            return
        self.seen_controls.add(identity)
        self.publish_event("accepted", direction, envelope)

    def publish_ack(self, received, direction):
        ack = GatewayEnvelope()
        ack.message_type = "ack"
        ack.sender = received.recipient
        ack.recipient = received.sender
        self.ack_counter += 1
        ack.sequence = self.ack_counter
        ack.correlation_id = received.correlation_id
        ack.generation_time = self.get_clock().now().to_msg()
        ack.ttl_sec = 10.0
        ack.encoding = "utf8"
        ack.ack_sequence = received.sequence
        ack.payload = list(message_id(received).encode())
        ack.payload_length = len(ack.payload)
        reverse = "downlink" if direction == "uplink" else "uplink"
        self.accept_candidate(reverse, ack)

    def publish_transport_event(self, direction, event):
        event_name = event.get("event")
        timestamp_key = {
            "admitted": "admit_time",
            "tx": "tx_time",
            "drop": "drop_time",
            "retry_scheduled": "retry_time",
        }.get(event_name, "event_time")
        event = {
            **event,
            "direction": direction,
            timestamp_key: event.get("time"),
        }
        message = String()
        message.data = json.dumps(
            event,
            sort_keys=True,
        )
        self._record(json.loads(message.data))

    def _record(self, event):
        metadata = self.wire_metadata.get(event.get("message_id", event.get("candidate_id")), {})
        event = {**metadata, **event}
        event.setdefault("mission_mode", self.mission_mode)
        event.setdefault("event_time", self.now_sec())
        self.ledger_index += 1
        event["ledger_index"] = self.ledger_index
        event.setdefault("fault_revision", self.configuration_revision)
        message = String(data=json.dumps(event, sort_keys=True))
        # The file is authoritative, including pending-queue closure after
        # SIGINT has invalidated DDS. Never lose it because publication stopped.
        self._write_ledger(message.data)
        if self.context.ok():
            try:
                self.event_publisher.publish(message)
            except RuntimeError:
                if self.context.ok():
                    raise  # Preserve active-context failures, tolerate only shutdown races.

    def _write_ledger(self, data):
        if not self.ledger_path:
            return
        directory = os.path.dirname(self.ledger_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.ledger_path, "a", encoding="utf-8") as stream:
            stream.write(data + "\n")

    def publish_event(self, event, direction, envelope, **extra):
        message = String()
        message.data = json.dumps(
            {
                "event": event,
                "direction": direction,
                "message_type": envelope.message_type,
                "message_id": self.message_id(envelope),
                "version": envelope.sequence,
                "sender": envelope.sender,
                "recipient": envelope.recipient,
                "sequence": envelope.sequence,
                "correlation_id": envelope.correlation_id,
                "generation_time": (
                    envelope.generation_time.sec
                    + envelope.generation_time.nanosec / 1e9
                ),
                "source_time": (
                    envelope.generation_time.sec
                    + envelope.generation_time.nanosec / 1e9
                ),
                "task_phase": envelope.task_phase,
                "payload_length": envelope.payload_length,
                "encoding": envelope.encoding,
                "ttl_sec": envelope.ttl_sec,
                **extra,
            },
            sort_keys=True,
        )
        self._record(json.loads(message.data))


def main(args=None):
    rclpy.init(args=args)
    node = IdealGateway()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
