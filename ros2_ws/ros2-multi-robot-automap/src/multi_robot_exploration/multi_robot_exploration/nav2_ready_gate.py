import time

import rclpy
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


def navigation_action_names(robot_count):
    return [f"/tb{index}/navigate_to_pose" for index in range(1, robot_count + 1)]


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
    deadline = time.monotonic() + timeout_sec
    previous_missing = None

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.25)
            missing = unavailable_actions(action_clients)
            if not missing:
                node.get_logger().info(
                    f"All {robot_count} Nav2 action servers are ready."
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
