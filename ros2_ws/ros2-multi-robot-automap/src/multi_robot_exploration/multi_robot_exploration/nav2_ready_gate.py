import time

from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState, GetState
import rclpy
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


NAVIGATION_NODES = (
    "controller_server",
    "planner_server",
    "behavior_server",
    "bt_navigator",
    "waypoint_follower",
    "velocity_smoother",
)


def navigation_action_names(robot_count):
    return [f"/tb{index}/navigate_to_pose" for index in range(1, robot_count + 1)]


def lifecycle_service_names(robot_count):
    return [
        f"/tb{index}/{node_name}/get_state"
        for index in range(1, robot_count + 1)
        for node_name in NAVIGATION_NODES
    ]


def lifecycle_change_service_names(robot_count):
    return [
        f"/tb{index}/{node_name}/change_state"
        for index in range(1, robot_count + 1)
        for node_name in NAVIGATION_NODES
    ]


def unavailable_actions(action_clients):
    return [name for name, client in action_clients.items() if not client.server_is_ready()]


def recovery_transition(state_labels):
    for service_name, label in state_labels.items():
        if label == "unconfigured":
            return service_name, Transition.TRANSITION_CONFIGURE
    if all(label in ("inactive", "active") for label in state_labels.values()):
        for service_name, label in state_labels.items():
            if label == "inactive":
                return service_name, Transition.TRANSITION_ACTIVATE
    return None


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
    change_clients = {
        name: node.create_client(ChangeState, name)
        for name in lifecycle_change_service_names(robot_count)
    }
    state_labels = {name: "unavailable" for name in state_clients}
    state_requests = {}
    change_requests = {}
    recovery_ready_at = {index: None for index in range(1, robot_count + 1)}
    recovery_last_requested = {
        index: -float("inf") for index in range(1, robot_count + 1)
    }
    deadline = time.monotonic() + timeout_sec
    previous_missing = None

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.25)
            now = time.monotonic()
            for name, (future, requested_at) in list(state_requests.items()):
                if not future.done():
                    if now - requested_at >= 2.0:
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
                if client.service_is_ready():
                    state_requests[name] = (
                        client.call_async(GetState.Request()),
                        now,
                    )

            for robot_index, (future, requested_at, service_name) in list(
                change_requests.items()
            ):
                if not future.done():
                    if now - requested_at >= 5.0:
                        future.cancel()
                        del change_requests[robot_index]
                    continue
                try:
                    if not future.result().success:
                        node.get_logger().warn(
                            f"Nav2 lifecycle recovery failed via {service_name}."
                        )
                except Exception as error:
                    node.get_logger().warn(
                        f"Nav2 lifecycle recovery error via {service_name}: {error}"
                    )
                del change_requests[robot_index]

            for robot_index in range(1, robot_count + 1):
                prefix = f"/tb{robot_index}/"
                robot_states = {
                    name: label
                    for name, label in state_labels.items()
                    if name.startswith(prefix)
                }
                robot_changes = {
                    name: client
                    for name, client in change_clients.items()
                    if name.startswith(prefix)
                }
                if all(label == "active" for label in robot_states.values()):
                    continue
                if not all(
                    client.service_is_ready() for client in robot_changes.values()
                ):
                    recovery_ready_at[robot_index] = None
                    continue
                if recovery_ready_at[robot_index] is None:
                    recovery_ready_at[robot_index] = now
                    continue
                if (
                    robot_index in change_requests
                    or now - recovery_ready_at[robot_index] < 20.0
                    or now - recovery_last_requested[robot_index] < 5.0
                ):
                    continue
                transition = recovery_transition(robot_states)
                if transition is None:
                    continue
                state_service, transition_id = transition
                change_service = state_service.replace("/get_state", "/change_state")
                request = ChangeState.Request()
                request.transition.id = transition_id
                change_requests[robot_index] = (
                    change_clients[change_service].call_async(request),
                    now,
                    change_service,
                )
                recovery_last_requested[robot_index] = now
                action = (
                    "configure"
                    if transition_id == Transition.TRANSITION_CONFIGURE
                    else "activate"
                )
                node.get_logger().warn(
                    f"Retrying Nav2 lifecycle {action} via {change_service}."
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
