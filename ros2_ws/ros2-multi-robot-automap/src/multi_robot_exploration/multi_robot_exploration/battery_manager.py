import json
import math

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from .control import transform_point_2d


ACTIVE = "ACTIVE"
RETURNING = "RETURNING"
CHARGING = "CHARGING"
FAILED = "FAILED"


def consume_energy(energy, distance_m, elapsed_sec, move_cost, idle_cost):
    return energy - move_cost * distance_m - idle_cost * elapsed_sec


def estimated_return_energy(
    distance_m,
    move_cost,
    idle_cost,
    path_factor,
    nominal_speed_mps,
    safety_margin,
):
    return (
        distance_m * path_factor * move_cost
        + distance_m
        * path_factor
        / nominal_speed_mps
        * idle_cost
        + safety_margin
    )


def battery_failure_reason(
    mode, energy, mode_elapsed, return_timeout, charge_timeout
):
    if energy <= 0:
        return "battery_exhausted"
    if mode == RETURNING and mode_elapsed >= return_timeout:
        return "battery_return_unreachable"
    if mode == CHARGING and mode_elapsed >= charge_timeout:
        return "battery_charge_timeout"
    return ""


def odometry_distance(previous, current, max_step):
    if previous is None:
        return 0.0
    distance = math.dist(previous, current)
    return distance if distance <= max_step else 0.0


def return_attempt_failure_reason(attempts, maximum_attempts):
    return "battery_return_unreachable" if attempts >= maximum_attempts else ""


class BatteryManager(Node):
    def __init__(self):
        super().__init__("battery_manager")
        self.robot_name = self.declare_parameter("robot_name", "tb1").value
        self.charge_x = float(
            self.declare_parameter("charge_x", 0.0).value
        )
        self.charge_y = float(
            self.declare_parameter("charge_y", 0.0).value
        )
        self.capacity = float(
            self.declare_parameter("capacity", 100.0).value
        )
        self.initial_energy = float(
            self.declare_parameter("initial_energy", 100.0).value
        )
        self.move_cost = float(
            self.declare_parameter("move_cost_per_m", 1.0).value
        )
        self.idle_cost = float(
            self.declare_parameter("idle_cost_per_sec", 0.02).value
        )
        self.safety_margin = float(
            self.declare_parameter("return_safety_margin", 5.0).value
        )
        self.return_path_factor = float(
            self.declare_parameter("return_path_factor", 1.5).value
        )
        self.nominal_speed = float(
            self.declare_parameter("nominal_speed_mps", 0.18).value
        )
        self.charge_radius = float(
            self.declare_parameter("charge_radius_m", 0.25).value
        )
        self.charge_duration = float(
            self.declare_parameter("charge_duration_sec", 10.0).value
        )
        self.return_timeout = float(
            self.declare_parameter("return_timeout_sec", 120.0).value
        )
        self.charge_timeout = float(
            self.declare_parameter("charge_timeout_sec", 60.0).value
        )
        self.max_return_attempts = int(
            self.declare_parameter("max_return_attempts", 3).value
        )
        self.stationary_linear = float(
            self.declare_parameter("stationary_linear_mps", 0.05).value
        )
        self.stationary_angular = float(
            self.declare_parameter("stationary_angular_radps", 0.10).value
        )
        self.max_odometry_step = float(
            self.declare_parameter("max_odometry_step_m", 1.0).value
        )
        if (
            not self.robot_name
            or self.capacity <= 0
            or not 0 < self.initial_energy <= self.capacity
            or self.move_cost < 0
            or self.idle_cost < 0
            or self.safety_margin < 0
            or self.return_path_factor < 1
            or self.nominal_speed <= 0
            or self.charge_radius <= 0
            or self.charge_duration <= 0
            or self.return_timeout <= 0
            or self.charge_timeout <= 0
            or self.max_return_attempts < 1
            or self.max_odometry_step <= 0
        ):
            raise ValueError("invalid battery parameters")

        state_qos = QoSProfile(depth=1)
        state_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        state_qos.reliability = ReliabilityPolicy.RELIABLE
        self.state_publisher = self.create_publisher(
            String, f"/{self.robot_name}/battery_state", state_qos
        )
        self.failure_publisher = self.create_publisher(
            String, "/battery_failure", state_qos
        )
        self.input_subscriptions = [
            self.create_subscription(
                Odometry,
                f"/{self.robot_name}/odom",
                self.odom_callback,
                10,
            ),
            self.create_subscription(
                TFMessage,
                f"/{self.robot_name}/tf",
                self.tf_callback,
                20,
            ),
            self.create_subscription(
                String,
                f"/{self.robot_name}/gateway/task_state",
                self.task_state_callback,
                state_qos,
            ),
        ]
        self.navigation = ActionClient(
            self, NavigateToPose, f"/{self.robot_name}/navigate_to_pose"
        )
        self.mode = ACTIVE
        self.energy = self.initial_energy
        self.minimum_energy = self.energy
        self.map_to_odom = None
        self.map_position = None
        self.previous_odom_position = None
        self.last_odom_time = None
        self.linear_speed = 0.0
        self.angular_speed = 0.0
        self.mode_started_at = None
        self.charge_stable_started_at = None
        self.return_goal_handle = None
        self.return_goal_pending = False
        self.return_goal_due_at = None
        self.return_attempts = 0
        self.return_count = 0
        self.charge_count = 0
        self.total_charging_time = 0.0
        self.mission_terminal = False
        self.timer = self.create_timer(0.5, self.timer_callback)
        self.publish_state()
        self.get_logger().info(
            f"Battery manager ready for {self.robot_name}; "
            f"energy={self.energy:.2f}/{self.capacity:.2f}, "
            f"charger=({self.charge_x:.2f}, {self.charge_y:.2f})."
        )

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def task_state_callback(self, message):
        self.mission_terminal = message.data in ("COMPLETE", "FAILED")

    def tf_callback(self, message):
        for stamped_transform in message.transforms:
            parent = stamped_transform.header.frame_id.lstrip("/")
            child = stamped_transform.child_frame_id.lstrip("/")
            if parent.endswith("map") and child.endswith("odom"):
                self.map_to_odom = stamped_transform.transform

    def odom_callback(self, message):
        now = self.now()
        odom_time = (
            message.header.stamp.sec
            + message.header.stamp.nanosec / 1e9
        )
        odom_position = (
            message.pose.pose.position.x,
            message.pose.pose.position.y,
        )
        twist = message.twist.twist
        self.linear_speed = math.hypot(twist.linear.x, twist.linear.y)
        self.angular_speed = abs(twist.angular.z)
        if self.map_to_odom is not None:
            self.map_position = transform_point_2d(
                *odom_position, self.map_to_odom
            )

        if self.last_odom_time is not None and self.mode != CHARGING:
            elapsed = max(0.0, odom_time - self.last_odom_time)
            measured_distance = (
                0.0
                if self.previous_odom_position is None
                else math.dist(self.previous_odom_position, odom_position)
            )
            distance = odometry_distance(
                self.previous_odom_position,
                odom_position,
                self.max_odometry_step,
            )
            if measured_distance > self.max_odometry_step:
                self.get_logger().warning(
                    f"Ignoring {measured_distance:.2f} m odometry discontinuity."
                )
            self.energy = consume_energy(
                self.energy,
                distance,
                elapsed,
                self.move_cost,
                self.idle_cost,
            )
            self.minimum_energy = min(self.minimum_energy, self.energy)
        self.last_odom_time = odom_time
        self.previous_odom_position = odom_position

        if self.mode == FAILED or self.mission_terminal:
            return
        reason = battery_failure_reason(
            self.mode,
            self.energy,
            0.0 if self.mode_started_at is None else now - self.mode_started_at,
            self.return_timeout,
            self.charge_timeout,
        )
        if reason:
            self.fail(reason)
            return
        if self.mode == ACTIVE and self.map_position is not None:
            distance_home = math.dist(
                self.map_position, (self.charge_x, self.charge_y)
            )
            reserve = estimated_return_energy(
                distance_home,
                self.move_cost,
                self.idle_cost,
                self.return_path_factor,
                self.nominal_speed,
                self.safety_margin,
            )
            if self.energy <= reserve:
                self.begin_return(reserve)
        elif self.mode == RETURNING and self.at_charger_and_stopped():
            self.begin_charging()
        elif self.mode == CHARGING:
            self.update_charging(now)

    def at_charger_and_stopped(self):
        return (
            self.map_position is not None
            and math.dist(
                self.map_position, (self.charge_x, self.charge_y)
            )
            <= self.charge_radius
            and self.linear_speed <= self.stationary_linear
            and self.angular_speed <= self.stationary_angular
        )

    def begin_return(self, reserve):
        now = self.now()
        self.mode = RETURNING
        self.mode_started_at = now
        self.return_goal_due_at = now + 1.0
        self.return_attempts = 0
        self.return_count += 1
        self.publish_state()
        self.get_logger().warning(
            f"{self.robot_name} returning to charge: energy={self.energy:.2f}, "
            f"required_reserve={reserve:.2f}."
        )

    def begin_charging(self):
        now = self.now()
        handle = self.return_goal_handle
        self.return_goal_handle = None
        if handle is not None:
            handle.cancel_goal_async()
        self.mode = CHARGING
        self.mode_started_at = now
        self.charge_stable_started_at = now
        self.publish_state()
        self.get_logger().info(f"{self.robot_name} started charging.")

    def update_charging(self, now):
        if not self.at_charger_and_stopped():
            self.charge_stable_started_at = None
            return
        if self.charge_stable_started_at is None:
            self.charge_stable_started_at = now
            return
        if now - self.charge_stable_started_at < self.charge_duration:
            return
        self.total_charging_time += now - self.mode_started_at
        self.energy = self.capacity
        self.charge_count += 1
        self.mode = ACTIVE
        self.mode_started_at = now
        self.charge_stable_started_at = None
        self.publish_state()
        self.get_logger().info(
            f"{self.robot_name} charged and resumed its retained task state."
        )

    def timer_callback(self):
        now = self.now()
        if self.mode == FAILED:
            return
        self.publish_state()
        if self.mission_terminal:
            return
        reason = battery_failure_reason(
            self.mode,
            self.energy,
            0.0 if self.mode_started_at is None else now - self.mode_started_at,
            self.return_timeout,
            self.charge_timeout,
        )
        if reason:
            self.fail(reason)
            return
        if (
            self.mode == RETURNING
            and self.return_goal_handle is None
            and not self.return_goal_pending
            and now >= self.return_goal_due_at
        ):
            self.send_return_goal()

    def send_return_goal(self):
        reason = return_attempt_failure_reason(
            self.return_attempts, self.max_return_attempts
        )
        if reason:
            self.fail(reason)
            return
        if not self.navigation.server_is_ready():
            return
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = self.charge_x
        goal.pose.pose.position.y = self.charge_y
        goal.pose.pose.orientation.w = 1.0
        self.return_attempts += 1
        self.return_goal_pending = True
        future = self.navigation.send_goal_async(goal)
        future.add_done_callback(self.return_goal_response)

    def return_goal_response(self, future):
        self.return_goal_pending = False
        try:
            handle = future.result()
        except Exception as error:
            self.get_logger().error(f"Battery return request failed: {error}")
            self.return_goal_due_at = self.now() + 1.0
            return
        if handle is None or not handle.accepted:
            self.return_goal_due_at = self.now() + 1.0
            return
        self.return_goal_handle = handle
        result = handle.get_result_async()
        result.add_done_callback(
            lambda completed, goal_handle=handle: self.return_goal_result(
                goal_handle, completed
            )
        )

    def return_goal_result(self, goal_handle, future):
        if self.return_goal_handle is not goal_handle:
            return
        self.return_goal_handle = None
        try:
            status = future.result().status
        except Exception as error:
            status = f"exception: {error}"
        if self.mode != RETURNING:
            return
        if status == GoalStatus.STATUS_SUCCEEDED and self.at_charger_and_stopped():
            self.begin_charging()
        elif return_attempt_failure_reason(
            self.return_attempts, self.max_return_attempts
        ):
            self.fail("battery_return_unreachable")
        else:
            self.return_goal_due_at = self.now() + 1.0

    def fail(self, reason):
        if self.mode == FAILED:
            return
        self.mode = FAILED
        self.publish_state()
        message = String()
        message.data = f"{reason}:{self.robot_name}"
        self.failure_publisher.publish(message)
        self.get_logger().error(message.data)

    def publish_state(self):
        charging_time = self.total_charging_time
        if self.mode == CHARGING and self.mode_started_at is not None:
            charging_time += max(0.0, self.now() - self.mode_started_at)
        message = String()
        message.data = json.dumps(
            {
                "robot": self.robot_name,
                "mode": self.mode,
                "energy": max(0.0, self.energy),
                "capacity": self.capacity,
                "initial_energy": self.initial_energy,
                "minimum_energy": max(0.0, self.minimum_energy),
                "return_count": self.return_count,
                "charge_count": self.charge_count,
                "charging_time_sec": charging_time,
                "charge_x": self.charge_x,
                "charge_y": self.charge_y,
                "move_cost_per_m": self.move_cost,
                "idle_cost_per_sec": self.idle_cost,
                "tx_cost_per_byte": 0.0,
            },
            sort_keys=True,
        )
        self.state_publisher.publish(message)


def main(args=None):
    rclpy.init(args=args)
    manager = BatteryManager()
    try:
        rclpy.spin(manager)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        manager.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
