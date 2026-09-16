import time

from lifecycle_msgs.srv import GetState
import rclpy
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


def navigation_action_names(robot_count):
    return [f"/tb{index}/navigate_to_pose" for index in range(1, robot_count + 1)]


def lifecycle_service_names(robot_count):
    return [
        f"/tb{index}/bt_navigator/get_state"
        for index in range(1, robot_count + 1)
    ]


def unavailable_actions(action_clients):
    return [name for name, client in action_clients.items() if not client.server_is_ready()]


def main(args=None):
    rclpy.init(args=args)
    node = Node("nav2_ready_gate")
    robot_count = max(1, node.declare_parameter("robot_count", 2).value)
    timeout_sec = max(1.0, node.declare_parameter("timeout_sec", 180.0).value)
    action_clients = {
        name: ActionClient(node, NavigateToPose, name)
        for name in navigation_action_names(robot_count)
    }
    state_clients = {
        name: node.create_client(GetState, name)
        for name in lifecycle_service_names(robot_count)
    }
    state_labels = {name: "unavailable" for name in state_clients}
    state_requests = {}
    deadline = time.monotonic() + timeout_sec
    previous_missing = None

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.25)
            for name, (future, requested_at) in list(
                state_requests.items()
            ):
                if not future.done():
                    if time.monotonic() - requested_at >= 2.0:
                        future.cancel()
                        del state_requests[name]
                    continue
                try:
                    state_labels[name] = future.result().current_state.label
                except Exception:
                    state_labels[name] = "query failed"
                del state_requests[name]
            for name, client in state_clients.items():
                if state_labels[name] == "active" or name in state_requests:
                    continue
                action_name = name.replace(
                    "/bt_navigator/get_state", "/navigate_to_pose"
                )
                if (
                    action_clients[action_name].server_is_ready()
                    and client.service_is_ready()
                ):
                    state_requests[name] = (
                        client.call_async(GetState.Request()),
                        time.monotonic(),
                    )

            missing = unavailable_actions(action_clients)
            missing.extend(
                f"{name} ({state_labels[name]})"
                for name in state_clients
                if state_labels[name] != "active"
            )
            if not missing:
                node.get_logger().info(
                    f"All {robot_count} Nav2 stacks are active."
                )
                return 0
            if missing != previous_missing:
                node.get_logger().info("Waiting for Nav2: " + ", ".join(missing))
                previous_missing = missing
            if time.monotonic() >= deadline:
                node.get_logger().error(
                    "Nav2 readiness timed out; unavailable: " + ", ".join(missing)
                )
                return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
