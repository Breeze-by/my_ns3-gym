import json
import threading
from dataclasses import dataclass, field

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from multi_robot_interfaces.msg import GatewayEnvelope
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.serialization import deserialize_message, serialize_message
from std_msgs.msg import String

from .fault_model import message_id, source_time
from .ideal_gateway import (
    DOWNLINK_CANDIDATES,
    DOWNLINK_DELIVERED,
    UPLINK_CANDIDATES,
    UPLINK_DELIVERED,
    envelope_is_valid,
)


def battery_mode_allows_navigation(mode):
    """Network commands cannot preempt robot-local safety navigation."""
    return mode == "ACTIVE"


@dataclass
class GoalContext:
    server_goal_handle: object
    result_event: threading.Event = field(default_factory=threading.Event)
    status: int = GoalStatus.STATUS_UNKNOWN
    cancel_sent: bool = False


class NavigationGateway(Node):
    """Bridge gateway navigation envelopes to a robot-local Nav2 action."""

    def __init__(self):
        super().__init__("navigation_gateway")
        self.robot_name = self.declare_parameter("robot_name", "tb1").value
        if not self.robot_name:
            raise ValueError("robot_name is required")
        self.task_phase = "EXPLORE"
        self.command_deadline_sec = float(
            self.declare_parameter("command_deadline_sec", 90.0).value
        )
        if self.command_deadline_sec <= 0:
            raise ValueError("command_deadline_sec must be positive")
        self.downlink_sequence = 0
        self.uplink_sequence = 0
        self.latest_downlink = {}
        self.latest_uplink = {}
        self.last_feedback_at = -float("inf")
        self.contexts = {}
        self.local_goal_handles = {}
        self.local_deadlines = {}
        self.local_canceled = set()
        self.local_seen = set()
        self.local_battery_mode = "ACTIVE"
        self.state_lock = threading.RLock()
        self.callback_group = ReentrantCallbackGroup()

        qos = QoSProfile(depth=100)
        qos.reliability = ReliabilityPolicy.RELIABLE
        state_qos = QoSProfile(depth=1)
        state_qos.reliability = ReliabilityPolicy.RELIABLE
        state_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.downlink_publisher = self.create_publisher(
            GatewayEnvelope, DOWNLINK_CANDIDATES, qos
        )
        self.uplink_publisher = self.create_publisher(
            GatewayEnvelope, UPLINK_CANDIDATES, qos
        )
        self.create_subscription(
            GatewayEnvelope,
            DOWNLINK_DELIVERED,
            self.downlink_callback,
            qos,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            GatewayEnvelope,
            UPLINK_DELIVERED,
            self.uplink_callback,
            qos,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            String,
            f"/{self.robot_name}/gateway/task_state",
            self.task_state_callback,
            state_qos,
            callback_group=self.callback_group,
        )
        self.local_navigation = ActionClient(
            self,
            NavigateToPose,
            f"/{self.robot_name}/navigate_to_pose",
            callback_group=self.callback_group,
        )
        self.event_publisher = self.create_publisher(String, "/gateway/consumed", 100)
        # Local safety authority never needs an AP round trip.
        self.create_subscription(
            String, f"/{self.robot_name}/battery_state", self.local_battery_callback,
            state_qos, callback_group=self.callback_group,
        )
        self.create_timer(0.1, self.expire_local_commands, callback_group=self.callback_group)
        self.server = ActionServer(
            self,
            NavigateToPose,
            f"/gateway/{self.robot_name}/navigate_to_pose",
            execute_callback=self.execute_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.callback_group,
        )
        self.get_logger().info(
            f"Navigation gateway ready for {self.robot_name}."
        )

    def now_sec(self):
        return self.get_clock().now().nanoseconds / 1e9

    def record_local_event(self, event, command_id, **extra):
        self.event_publisher.publish(String(data=json.dumps({
            "event": event, "message_type": "navigation_goal",
            "sender": "headquarters", "recipient": self.robot_name,
            "correlation_id": command_id, "event_time": self.now_sec(), **extra,
        }, sort_keys=True)))

    def task_state_callback(self, message):
        self.task_phase = message.data

    def make_envelope(
        self,
        message_type,
        sender,
        recipient,
        sequence,
        correlation_id,
        payload=b"",
        ttl_sec=10.0,
    ):
        envelope = GatewayEnvelope()
        envelope.message_type = message_type
        envelope.sender = sender
        envelope.recipient = recipient
        envelope.sequence = sequence
        envelope.correlation_id = correlation_id
        envelope.generation_time = self.get_clock().now().to_msg()
        envelope.task_phase = self.task_phase
        envelope.payload_length = len(payload)
        envelope.encoding = "cdr"
        envelope.ttl_sec = ttl_sec
        envelope.payload = list(payload)
        return envelope

    def execute_callback(self, server_goal_handle):
        self.downlink_sequence += 1
        command_id = self.downlink_sequence
        context = GoalContext(server_goal_handle)
        self.contexts[command_id] = context
        payload = serialize_message(server_goal_handle.request.pose)
        envelope = self.make_envelope(
            "navigation_goal",
            "headquarters",
            self.robot_name,
            self.downlink_sequence,
            command_id,
            payload,
            ttl_sec=self.command_deadline_sec,
        )
        self.downlink_publisher.publish(envelope)

        deadline = self.now_sec() + self.command_deadline_sec + 5.0
        while rclpy.ok() and not context.result_event.wait(0.1):
            if server_goal_handle.is_cancel_requested and not context.cancel_sent:
                self.publish_cancel(command_id)
                context.cancel_sent = True
            if self.now_sec() >= deadline:
                self.publish_cancel(command_id)
                context.status = GoalStatus.STATUS_ABORTED
                self.get_logger().error(
                    f"Navigation command {command_id} timed out after "
                    f"{self.command_deadline_sec:.1f}s."
                )
                break

        status = context.status
        # A central cancel and the local Nav2 result can arrive in either
        # order. Only transition an active server handle; otherwise the
        # action server has already completed the request.
        if server_goal_handle.is_active:
            if status == GoalStatus.STATUS_SUCCEEDED:
                server_goal_handle.succeed()
            elif (
                status == GoalStatus.STATUS_CANCELED
                and server_goal_handle.is_cancel_requested
            ):
                server_goal_handle.canceled()
            else:
                server_goal_handle.abort()
        self.contexts.pop(command_id, None)
        return NavigateToPose.Result()

    def cancel_callback(self, server_goal_handle):
        for command_id, context in list(self.contexts.items()):
            if context.server_goal_handle is server_goal_handle:
                if not context.cancel_sent:
                    self.publish_cancel(command_id)
                    context.cancel_sent = True
                break
        return CancelResponse.ACCEPT

    def publish_cancel(self, command_id):
        self.downlink_sequence += 1
        envelope = self.make_envelope(
            "navigation_cancel",
            "headquarters",
            self.robot_name,
            self.downlink_sequence,
            command_id,
        )
        self.downlink_publisher.publish(envelope)

    def downlink_callback(self, envelope):
        if (
            envelope.recipient != self.robot_name
            or envelope.sender != "headquarters"
            or envelope.message_type
            not in ("navigation_goal", "navigation_cancel")
        ):
            return
        key = (envelope.message_type, envelope.correlation_id)
        latest = self.latest_downlink.get(key, 0)
        valid, _ = envelope_is_valid(envelope, self.now_sec(), latest)
        if not valid:
            self.record_local_event("command_rejected", envelope.correlation_id,
                                    reason="stale_command")
            return
        self.latest_downlink[key] = envelope.sequence
        self.record_local_event("accepted", envelope.correlation_id,
                                message_type=envelope.message_type, direction="downlink",
                                message_id=message_id(envelope), source_time=source_time(envelope),
                                sequence=envelope.sequence)
        if envelope.message_type == "navigation_cancel":
            self.local_canceled.add(envelope.correlation_id)
            handle = self.local_goal_handles.get(envelope.correlation_id)
            if handle is not None:
                handle.cancel_goal_async()
            return
        command_id = envelope.correlation_id
        with self.state_lock:
            if command_id in self.local_seen:
                return
            self.local_seen.add(command_id)
            if command_id in self.local_canceled or not battery_mode_allows_navigation(
                self.local_battery_mode
            ):
                self.publish_result(command_id, GoalStatus.STATUS_ABORTED)
                return
            self.local_deadlines[command_id] = (
                envelope.generation_time.sec + envelope.generation_time.nanosec / 1e9
                + envelope.ttl_sec
            )
        self.record_local_event("command_accepted", command_id,
                                deadline=self.local_deadlines[command_id])
        try:
            pose = deserialize_message(bytes(envelope.payload), PoseStamped)
        except Exception as error:
            self.get_logger().error(f"Invalid navigation goal: {error}")
            self.publish_result(
                envelope.correlation_id, GoalStatus.STATUS_ABORTED
            )
            return
        if not self.local_navigation.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("Robot-local Nav2 action is unavailable.")
            self.publish_result(
                envelope.correlation_id, GoalStatus.STATUS_ABORTED
            )
            return
        goal = NavigateToPose.Goal()
        goal.pose = pose
        future = self.local_navigation.send_goal_async(
            goal,
            feedback_callback=lambda feedback, command_id=(
                envelope.correlation_id
            ): self.local_feedback_callback(command_id, feedback),
        )
        future.add_done_callback(
            lambda result, command_id=envelope.correlation_id: (
                self.local_goal_response(command_id, result)
            )
        )

    def local_goal_response(self, command_id, future):
        try:
            goal_handle = future.result()
        except Exception as error:
            self.get_logger().error(f"Local navigation request failed: {error}")
            self.publish_result(command_id, GoalStatus.STATUS_ABORTED)
            return
        if goal_handle is None or not goal_handle.accepted:
            self.publish_result(command_id, GoalStatus.STATUS_ABORTED)
            return
        self.local_goal_handles[command_id] = goal_handle
        # Never read central GoalContext here: it is not delivered information.
        if (command_id in self.local_canceled
                or self.now_sec() >= self.local_deadlines.get(command_id, 0.0)
                or not battery_mode_allows_navigation(self.local_battery_mode)):
            goal_handle.cancel_goal_async()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result, selected=command_id: self.local_goal_result(
                selected, result
            )
        )

    def local_feedback_callback(self, command_id, feedback_message):
        now = self.now_sec()
        if now - self.last_feedback_at < 0.5:
            return
        self.last_feedback_at = now
        self.uplink_sequence += 1
        envelope = self.make_envelope(
            "navigation_feedback",
            self.robot_name,
            "headquarters",
            self.uplink_sequence,
            command_id,
            serialize_message(feedback_message.feedback),
            ttl_sec=2.0,
        )
        self.uplink_publisher.publish(envelope)

    def local_goal_result(self, command_id, future):
        try:
            status = future.result().status
        except Exception as error:
            self.get_logger().error(f"Local navigation result failed: {error}")
            status = GoalStatus.STATUS_ABORTED
        self.local_goal_handles.pop(command_id, None)
        self.local_deadlines.pop(command_id, None)
        self.publish_result(command_id, status)

    def local_battery_callback(self, message):
        try:
            mode = json.loads(message.data)["mode"]
        except (KeyError, TypeError, json.JSONDecodeError):
            return
        previous_mode = self.local_battery_mode
        self.local_battery_mode = mode
        # Battery state is published periodically. Cancel the old
        # exploration command only on the transition into a safety mode; do
        # not cancel the new return-to-charger command on every heartbeat.
        if (
            mode != "ACTIVE"
            and mode != previous_mode
        ):
            for command_id, handle in list(self.local_goal_handles.items()):
                self.local_canceled.add(command_id)
                self.record_local_event("local_safety_cancel", command_id, mode=mode)
                handle.cancel_goal_async()

    def expire_local_commands(self):
        for command_id, deadline in list(self.local_deadlines.items()):
            if self.now_sec() >= deadline and command_id not in self.local_canceled:
                self.local_canceled.add(command_id)
                self.record_local_event("navigation_deadline", command_id, deadline=deadline)
                handle = self.local_goal_handles.get(command_id)
                if handle is not None:
                    handle.cancel_goal_async()
                self.publish_result(command_id, GoalStatus.STATUS_ABORTED)

    def publish_result(self, command_id, status):
        result = String()
        result.data = json.dumps({"status": int(status)})
        self.uplink_sequence += 1
        envelope = self.make_envelope(
            "navigation_result",
            self.robot_name,
            "headquarters",
            self.uplink_sequence,
            command_id,
            serialize_message(result),
            ttl_sec=60.0,
        )
        self.uplink_publisher.publish(envelope)

    def uplink_callback(self, envelope):
        if (
            envelope.sender != self.robot_name
            or envelope.recipient != "headquarters"
            or envelope.message_type
            not in ("navigation_feedback", "navigation_result")
        ):
            return
        key = (envelope.message_type, envelope.correlation_id)
        latest = self.latest_uplink.get(key, 0)
        valid, _ = envelope_is_valid(envelope, self.now_sec(), latest)
        if not valid:
            return
        self.latest_uplink[key] = envelope.sequence
        self.record_local_event("accepted", envelope.correlation_id,
                                message_type=envelope.message_type, sender=self.robot_name,
                                recipient="headquarters", direction="uplink",
                                message_id=message_id(envelope), source_time=source_time(envelope),
                                sequence=envelope.sequence)
        context = self.contexts.get(envelope.correlation_id)
        if context is None:
            return
        if envelope.message_type == "navigation_feedback":
            try:
                feedback = deserialize_message(
                    bytes(envelope.payload), NavigateToPose.Feedback
                )
            except Exception as error:
                self.get_logger().error(
                    f"Invalid navigation feedback: {error}"
                )
                return
            context.server_goal_handle.publish_feedback(feedback)
            return
        try:
            result = deserialize_message(bytes(envelope.payload), String)
            context.status = int(json.loads(result.data)["status"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.get_logger().error(f"Invalid navigation result: {error}")
            context.status = GoalStatus.STATUS_ABORTED
        context.result_event.set()

    def destroy_node(self):
        self.server.destroy()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = NavigationGateway()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
