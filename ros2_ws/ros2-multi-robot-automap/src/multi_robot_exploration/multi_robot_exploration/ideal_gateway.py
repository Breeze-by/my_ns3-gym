import json
import zlib
from collections import deque
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
    if envelope.ttl_sec > 0 and now_sec - generated > envelope.ttl_sec:
        return False, "expired"
    if envelope.sequence <= latest_sequence:
        return False, "stale_sequence"
    return True, ""


class IdealGateway(Node):
    """Zero-loss explicit message transport and received-information store."""

    def __init__(self):
        super().__init__("ideal_gateway")
        self.robot_count = self.declare_parameter("robot_count", 2).value
        if self.robot_count < 1:
            raise ValueError("robot_count must be positive")

        self.task_phase = "EXPLORE"
        self.sequences = {}
        self.latest_sequences = {}
        self.last_generated_at = {}
        self.queues = {
            "uplink": deque(),
            "downlink": deque(),
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
            lambda message: self.queues["uplink"].append(message),
            reliable,
        )
        self.create_subscription(
            GatewayEnvelope,
            DOWNLINK_CANDIDATES,
            lambda message: self.queues["downlink"].append(message),
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
            f"Ideal gateway ready for {self.robot_count} robots."
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
        envelope.generation_time = self.get_clock().now().to_msg()
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

    def deliver_queued(self):
        for direction, queue in self.queues.items():
            while queue:
                envelope = queue.popleft()
                self.delivered_publishers[direction].publish(envelope)
                self.publish_event("delivered", direction, envelope)

    def receive_envelope(self, envelope):
        key = (
            envelope.message_type,
            envelope.sender,
            envelope.recipient,
        )
        latest = self.latest_sequences.get(key, 0)
        valid, reason = envelope_is_valid(
            envelope, self.now_sec(), latest
        )
        direction = (
            "uplink"
            if envelope.recipient == "headquarters"
            else "downlink"
        )
        if not valid:
            self.publish_event(reason, direction, envelope)
            return
        self.latest_sequences[key] = envelope.sequence
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
            self.destination_publishers[route_key].publish(message)
        self.publish_ack(envelope)

    def publish_ack(self, received):
        ack = GatewayEnvelope()
        ack.message_type = "ack"
        ack.sender = received.recipient
        ack.recipient = received.sender
        ack.sequence = received.sequence
        ack.correlation_id = received.correlation_id
        ack.generation_time = self.get_clock().now().to_msg()
        ack.task_phase = self.task_phase
        ack.ack_sequence = received.sequence
        self.ack_publisher.publish(ack)

    def publish_event(self, event, direction, envelope):
        message = String()
        message.data = json.dumps(
            {
                "event": event,
                "direction": direction,
                "message_type": envelope.message_type,
                "sender": envelope.sender,
                "recipient": envelope.recipient,
                "sequence": envelope.sequence,
                "correlation_id": envelope.correlation_id,
                "generation_time": (
                    envelope.generation_time.sec
                    + envelope.generation_time.nanosec / 1e9
                ),
                "task_phase": envelope.task_phase,
                "payload_length": envelope.payload_length,
                "encoding": envelope.encoding,
                "ttl_sec": envelope.ttl_sec,
            },
            sort_keys=True,
        )
        self.event_publisher.publish(message)


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
