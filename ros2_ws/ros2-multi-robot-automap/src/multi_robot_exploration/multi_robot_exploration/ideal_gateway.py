import json
import os
import zlib
from dataclasses import dataclass

from multi_robot_interfaces.msg import GatewayEnvelope
from nav_msgs.msg import OccupancyGrid, Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.serialization import deserialize_message, serialize_message
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from .fault_model import (
    DeterministicFaultTransport, FaultConfig, RELIABLE_TYPES, STATE_TYPES,
    message_id, source_time,
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
        self.ack_counter = 0
        self.source_stamps = {}
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
        self.ledger_path = str(
            self.declare_parameter("ledger_path", "").value
        )
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
                    seed=seed ^ 0x13579BDF,
                    ack_timeout_sec=ack_timeout,
                    max_retries=max_retries,
                    queue_capacity=queue_capacity,
                    drop_types=drop_types,
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
                    seed=seed ^ 0x2468ACE0,
                    ack_timeout_sec=ack_timeout,
                    max_retries=max_retries,
                    queue_capacity=queue_capacity,
                    drop_types=drop_types,
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
        self.get_logger().info(
            f"Gateway ready for {self.robot_count} robots "
            f"(mode={self.network_mode}, mission_mode={self.mission_mode})."
        )

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
                        5.0,
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
                        2.0,
                        min_interval_sec=0.2,
                    ),
                    Route(
                        "frame_state",
                        robot,
                        "headquarters",
                        f"/{robot}/tf",
                        f"/gateway/received/{robot}/tf",
                        TFMessage,
                        2.0,
                        min_interval_sec=0.5,
                    ),
                    Route(
                        "battery_state",
                        robot,
                        "headquarters",
                        f"/{robot}/battery_state",
                        f"/gateway/received/{robot}/battery_state",
                        String,
                        5.0,
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
                        5.0,
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
                    60.0,
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

    def next_sequence(self, route):
        key = (route.message_type, route.sender, route.recipient)
        self.sequences[key] = self.sequences.get(key, 0) + 1
        return self.sequences[key]

    def publish_candidate(self, route, direction, message):
        key = (route.message_type, route.sender, route.recipient)
        now = self.now_sec()
        if (
            route.min_interval_sec > 0
            and now - self.last_generated_at.get(key, -float("inf"))
            < route.min_interval_sec
        ):
            return
        self.last_generated_at[key] = now
        # Preserve sensor source stamps; receiving an old sample never renews TTL.
        generated = now
        if isinstance(message, TFMessage):
            relevant = [item for item in message.transforms
                        if item.header.frame_id.lstrip("/").endswith("map")
                        and item.child_frame_id.lstrip("/").endswith("odom")]
            if not relevant:
                return
            stamp = relevant[-1].header.stamp
            generated = stamp.sec + stamp.nanosec / 1e9
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
            self.source_stamps[key] = generated
        payload = serialize_message(message)
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
        envelope.generation_time.sec = int(generated)
        envelope.generation_time.nanosec = int((generated - int(generated)) * 1e9)
        envelope.task_phase = (
            message.data
            if route.message_type == "task_state"
            else self.task_phase
        )
        envelope.payload_length = len(payload)
        envelope.encoding = encoding
        envelope.ttl_sec = route.ttl_sec
        envelope.payload = list(payload)
        self.candidate_publishers[direction].publish(envelope)
        self.publish_event("generated", direction, envelope)

    @staticmethod
    def message_id(envelope):
        return message_id(envelope)

    def accept_candidate(self, direction, envelope):
        self.transport_by_direction[direction].enqueue(
            message_id(envelope), envelope, direction, self.now_sec(),
            reliable=envelope.message_type in RELIABLE_TYPES,
            source_time=source_time(envelope), ttl_sec=float(envelope.ttl_sec),
        )

    def deliver_queued(self):
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
        if envelope.message_type == "ack":
            try:
                identity = bytes(envelope.payload).decode("utf-8")
            except UnicodeDecodeError:
                return
            reverse = "downlink" if direction == "uplink" else "uplink"
            self.transport_by_direction[reverse].acknowledge(identity, self.now_sec())
            self.ack_publisher.publish(envelope)
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
            if envelope.message_type == "target_detection":
                event = json.loads(message.data)
                event["_gateway"] = {
                    "message_id": message_id(envelope),
                    "source_time": source_time(envelope),
                    "delivery_time": self.now_sec(),
                    "sequence": envelope.sequence,
                }
                message.data = json.dumps(event, sort_keys=True)
            self.destination_publishers[route_key].publish(message)
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
        event.setdefault("mission_mode", self.mission_mode)
        event.setdefault("event_time", self.now_sec())
        message = String(data=json.dumps(event, sort_keys=True))
        self.event_publisher.publish(message)
        self._write_ledger(message.data)

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
