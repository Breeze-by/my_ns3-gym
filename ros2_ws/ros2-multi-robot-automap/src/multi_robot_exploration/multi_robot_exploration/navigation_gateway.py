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

from .ideal_gateway import (
    DOWNLINK_CANDIDATES,
    DOWNLINK_DELIVERED,
    UPLINK_CANDIDATES,
    UPLINK_DELIVERED,
    envelope_is_valid,
)


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
        self.downlink_sequence = 0
        self.uplink_sequence = 0
        self.latest_downlink = {}
        self.latest_uplink = {}
        self.last_feedback_at = -float("inf")
        self.contexts = {}
        self.local_goal_handles = {}
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
        )
        self.downlink_publisher.publish(envelope)

        while rclpy.ok() and not context.result_event.wait(0.1):
            if server_goal_handle.is_cancel_requested and not context.cancel_sent:
                self.publish_cancel(command_id)
                context.cancel_sent = True

        status = context.status
        if status == GoalStatus.STATUS_SUCCEEDED:
            server_goal_handle.succeed()
        elif status == GoalStatus.STATUS_CANCELED:
            server_goal_handle.canceled()
        else:
            server_goal_handle.abort()
        self.contexts.pop(command_id, None)
        self.local_goal_handles.pop(command_id, None)
        return NavigateToPose.Result()

    def cancel_callback(self, server_goal_handle):
        for command_id, context in self.contexts.items():
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
        key = envelope.message_type
        latest = self.latest_downlink.get(key, 0)
        valid, _ = envelope_is_valid(envelope, self.now_sec(), latest)
        if not valid:
            return
        self.latest_downlink[key] = envelope.sequence
        if envelope.message_type == "navigation_cancel":
            handle = self.local_goal_handles.get(envelope.correlation_id)
            if handle is not None:
                handle.cancel_goal_async()
            return
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
        context = self.contexts.get(command_id)
        if context is not None and context.cancel_sent:
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
        self.publish_result(command_id, status)

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
        key = envelope.message_type
        latest = self.latest_uplink.get(key, 0)
        valid, _ = envelope_is_valid(envelope, self.now_sec(), latest)
        if not valid:
            return
        self.latest_uplink[key] = envelope.sequence
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
