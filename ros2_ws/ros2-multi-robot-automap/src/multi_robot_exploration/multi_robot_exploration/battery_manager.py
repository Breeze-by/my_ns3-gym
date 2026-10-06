import json
import math

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
from nav_msgs.msg import Odometry
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from .fault_model import CHARGE_REQUEST_TTL_SEC

from .control import (
    MAX_NAVIGATION_LEG_M,
    RALLY_PATH_CLEARANCE_M,
    RallyPose,
    grid_to_world,
    navigation_start_route,
    plan_rally_leg,
    route_arrival_yaw,
    traversable_grid,
    transform_point_2d,
    world_to_grid,
)


ACTIVE = "ACTIVE"
RETURNING = "RETURNING"
CHARGING = "CHARGING"
FAILED = "FAILED"
RETURN_PROGRESS_TIMEOUT_SEC = 20.0


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


def charge_target_energy(capacity, target_fraction):
    return capacity * target_fraction


def charging_zone_contains(position, charger, radius):
    """Return whether a pose is inside the charger contact zone."""
    return (
        position is not None
        and math.dist(position, charger) <= radius
    )


def return_escape_pose(
    raw_grid, resolution, origin, position, max_escape_m=0.8,
    clearance_m=0.55,
):
    """Find a nearby clearance-safe pose when the current pose is lethal."""
    if raw_grid is None or resolution is None or resolution <= 0 or position is None:
        return None
    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=clearance_m
    )
    start = world_to_grid(
        position[0], position[1], resolution, origin[0], origin[1]
    )
    endpoint, route = navigation_start_route(
        raw_grid,
        traversable,
        start,
        max(1, math.ceil(max_escape_m / resolution)),
    )
    if endpoint is None or not route or endpoint == start:
        return None
    return grid_to_world(
        endpoint[0], endpoint[1], resolution, origin[0], origin[1]
    )


def plan_charging_leg(raw_grid, resolution, origin, position, charger, radius):
    """Reach the charger contact region when its exact centre is blocked.

    Prefer the existing home route. Reuse its distance field for a reachable,
    clearance-safe contact point, leaving 0.2 m for goal-position error.
    Unknown/occupied cells and disconnected contact regions remain forbidden.
    """
    cache = {}
    options = dict(max_distance_m=MAX_NAVIGATION_LEG_M,
                   clearance_m=RALLY_PATH_CLEARANCE_M, visible_only=True,
                   route_cache=cache)

    def first_leg(leg, route):
        escape = cache["field"][2]
        if leg is not None and len(escape) > 1:
            # Complete the already validated known-free clearance escape
            # before asking Nav2 for a long home leg from its inflated start.
            # Replan on the next result; retain every occupied/unknown cell.
            route = tuple(grid_to_world(*cell, resolution, *origin) for cell in escape)
            leg = RallyPose(*route[-1], route_arrival_yaw(route, leg.yaw))
        return leg, route

    leg, route = plan_rally_leg(
        RallyPose(*charger, 0.0), raw_grid, resolution, origin, position,
        **options,
    )
    if leg is not None:
        return first_leg(leg, route)
    traversable, start, _, distance_data = cache["field"]
    if start is None or distance_data is None or radius <= 0.2:
        return None, ()
    distances = distance_data[0]
    rows, columns = np.nonzero(traversable & np.isfinite(distances))
    xs = origin[0] + (columns + 0.5) * resolution
    ys = origin[1] + (rows + 0.5) * resolution
    squared = (xs - charger[0]) ** 2 + (ys - charger[1]) ** 2
    candidates = np.flatnonzero(squared <= (radius - 0.2) ** 2)
    if not len(candidates):
        return None, ()
    chosen = min(candidates, key=lambda i: (squared[i], distances[rows[i], columns[i]]))
    return first_leg(*plan_rally_leg(
        RallyPose(float(xs[chosen]), float(ys[chosen]), 0.0), raw_grid,
        resolution, origin, position, **options,
    ))


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
            self.declare_parameter("capacity", 60.0).value
        )
        self.initial_energy = float(
            self.declare_parameter("initial_energy", 40.0).value
        )
        self.inject_failure_after_sec = float(
            self.declare_parameter("inject_failure_after_sec", -1.0).value
        )
        if self.inject_failure_after_sec >= 0 and not self.get_parameter("use_sim_time").value:
            raise ValueError("failure injection is simulation-only")
        self.first_odom_time = None
        self.fused_map_received_at = None
        self.move_cost = float(
            self.declare_parameter("move_cost_per_m", 1.0).value
        )
        self.idle_cost = float(
            self.declare_parameter("idle_cost_per_sec", 0.02).value
        )
        self.safety_margin = float(
            self.declare_parameter("return_safety_margin", 8.0).value
        )
        self.return_path_factor = float(
            self.declare_parameter("return_path_factor", 2.0).value
        )
        self.nominal_speed = float(
            self.declare_parameter("nominal_speed_mps", 0.18).value
        )
        self.charge_radius = float(
            self.declare_parameter("charge_radius_m", 0.8).value
        )
        self.charge_target_fraction = float(
            self.declare_parameter("charge_target_fraction", 0.8).value
        )
        self.charge_duration = float(
            self.declare_parameter("charge_duration_sec", 6.0).value
        )
        self.return_timeout = float(
            self.declare_parameter("return_timeout_sec", 180.0).value
        )
        self.charge_timeout = float(
            self.declare_parameter("charge_timeout_sec", 60.0).value
        )
        self.max_return_attempts = int(
            self.declare_parameter("max_return_attempts", 3).value
        )
        self.stationary_linear = float(
            self.declare_parameter("stationary_linear_mps", 0.15).value
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
            or not 0 <= self.initial_energy <= self.capacity
            or (self.initial_energy == 0 and not self.get_parameter('use_sim_time').value)
            or self.move_cost < 0
            or self.idle_cost < 0
            or self.safety_margin < 0
            or self.return_path_factor < 1
            or self.nominal_speed <= 0
            or self.charge_radius <= 0
            or not 0 < self.charge_target_fraction <= 1
            or self.charge_duration <= 0
            or self.return_timeout <= 0
            or self.charge_timeout <= 0
            or self.max_return_attempts < 1
            or self.max_odometry_step <= 0
            or self.stationary_linear < 0
            or self.stationary_angular < 0
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
        self.consumed_publisher = self.create_publisher(
            String, "/gateway/consumed", 100
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
            self.create_subscription(
                OccupancyGrid,
                f"/{self.robot_name}/gateway/merge_map",
                self.fused_map_callback,
                10,
            ),
            self.create_subscription(
                OccupancyGrid, f"/{self.robot_name}/map", self.local_map_callback, state_qos,
            ),
            self.create_subscription(
                String, f"/{self.robot_name}/gateway/charge_request",
                self.charge_request_callback, 10,
            ),
        ]
        self.navigation = ActionClient(
            self,
            NavigateToPose,
            f"/{self.robot_name}/navigate_to_pose",
        )
        self.mode = ACTIVE
        self.energy = self.initial_energy
        self.minimum_energy = self.energy
        self.map_to_odom = None
        self.map_position = None
        self.return_map = None
        self.return_map_resolution = None
        self.return_map_origin = None
        self.previous_odom_position = None
        self.last_odom_time = None
        self.linear_speed = 0.0
        self.angular_speed = 0.0
        self.mode_started_at = None
        self.charge_stable_started_at = None
        self.return_goal_handle = None
        self.return_goal_pending = False
        self.return_goal_target = None
        self.return_goal_started_at = None
        self.return_goal_timeout_sec = 30.0
        self.return_goal_best_distance = None
        self.return_goal_last_progress_at = None
        self.return_goal_cancel_requested = False
        self.return_goal_due_at = None
        self.return_attempts = 0
        self.return_count = 0
        self.return_stage = "charger"
        self.return_escape_target = None
        self.return_escape_failed = False
        self.return_waypoint_target = None
        self.charge_count = 0
        self.total_charging_time = 0.0
        self.mission_terminal = False
        self.last_charge_request_stamp = -float("inf")
        self.failure_reason = ""
        self.timer = self.create_timer(0.5, self.timer_callback)
        if self.energy == 0:
            self.fail('battery_exhausted')
        else:
            self.publish_state()
        self.get_logger().info(
            f"Battery manager ready for {self.robot_name}; "
            f"energy={self.energy:.2f}/{self.capacity:.2f}, "
            f"charger=({self.charge_x:.2f}, {self.charge_y:.2f})."
        )

    @property
    def charge_target(self):
        return charge_target_energy(
            self.capacity, self.charge_target_fraction
        )

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def task_state_callback(self, message):
        self.mission_terminal = message.data in (
            "COMPLETE", "PARTIAL_COMPLETE", "FAILED"
        )

    def charge_request_callback(self, message):
        """A delivered mission budget may request early local safety return."""
        try:
            event = json.loads(message.data)
            stamp = float(event["stamp_sec"])
            required = float(event["required_energy"])
            if (event["robot"] != self.robot_name
                    or event["task_phase"] not in ('EXPLORE', 'FOUND_UNCONFIRMED', 'FOUND', 'RALLY')
                    or not math.isfinite(stamp) or not math.isfinite(required)
                    or not 0 < required <= self.charge_target
                    or not 0 <= self.now() - stamp < CHARGE_REQUEST_TTL_SEC
                    or stamp <= self.last_charge_request_stamp):
                return
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return
        self.last_charge_request_stamp = stamp
        self.consumed_publisher.publish(String(data=json.dumps({
            **event.get("_gateway", {}), "event": "consumed",
            "message_type": "charge_request", "consumed_time": self.now(),
        }, sort_keys=True)))
        if (self.mission_terminal or self.mode != ACTIVE
                or self.energy > required or self.map_position is None):
            return
        reserve = estimated_return_energy(
            math.dist(self.map_position, (self.charge_x, self.charge_y)),
            self.move_cost, self.idle_cost, self.return_path_factor,
            self.nominal_speed, self.safety_margin,
        )
        self.get_logger().info(
            f"Early {event['task_phase'].lower()} charge requested: energy={self.energy:.2f}, "
            f"mission_budget={required:.2f}."
        )
        self.begin_return(reserve)

    def tf_callback(self, message):
        for stamped_transform in message.transforms:
            parent = stamped_transform.header.frame_id.lstrip("/")
            child = stamped_transform.child_frame_id.lstrip("/")
            if parent.endswith("map") and child.endswith("odom"):
                self.map_to_odom = stamped_transform.transform

    def map_callback(self, message):
        self.return_map = np.asarray(
            message.data, dtype=np.int16
        ).reshape(message.info.height, message.info.width)
        self.return_map_resolution = float(message.info.resolution)
        self.return_map_origin = (
            message.info.origin.position.x,
            message.info.origin.position.y,
        )

    def fused_map_callback(self, message):
        self.fused_map_received_at = self.now()
        self.map_callback(message)

    def local_map_callback(self, message):
        # Preserve the received fused map while live, but loss of AP contact
        # cannot remove the robot's own known path home.
        if self.fused_map_received_at is None or self.now() - self.fused_map_received_at > 5.0:
            self.map_callback(message)

    def odom_callback(self, message):
        now = self.now()
        if self.first_odom_time is None:
            self.first_odom_time = now
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
        elif self.mode == RETURNING and self.in_charging_zone():
            self.begin_charging()
        elif self.mode == CHARGING:
            self.update_charging(now)

    def at_charger_and_stopped(self):
        return (
            self.in_charging_zone()
            and self.linear_speed <= self.stationary_linear
            and self.angular_speed <= self.stationary_angular
        )

    def in_charging_zone(self, margin=0.0):
        return charging_zone_contains(
            self.map_position,
            (self.charge_x, self.charge_y),
            self.charge_radius + margin,
        )

    def begin_return(self, reserve):
        now = self.now()
        self.mode = RETURNING
        self.mode_started_at = now
        self.return_goal_due_at = now + 1.0
        self.return_attempts = 0
        self.return_count += 1
        self.return_stage = "charger"
        self.return_escape_failed = False
        self.return_escape_target = None
        self.return_waypoint_target = None
        self.publish_state()
        self.get_logger().warning(
            f"{self.robot_name} returning to charge: energy={self.energy:.2f}, "
            f"required_reserve={reserve:.2f}."
        )

    def begin_charging(self):
        now = self.now()
        handle = self.return_goal_handle
        if handle is not None:
            handle.cancel_goal_async()
        self.mode = CHARGING
        self.mode_started_at = now
        # Entering the zone is enough to stop navigation. The robot may
        # still be settling, so start the stable timer only after its speed
        # drops below the relaxed charging threshold.
        self.charge_stable_started_at = None
        self.publish_state()
        self.get_logger().info(f"{self.robot_name} started charging.")

    def update_charging(self, now):
        # Keep a small hysteresis band so map/odom jitter does not repeatedly
        # eject a robot that is already beside the charger.
        if not self.in_charging_zone(margin=0.2):
            self.mode = RETURNING
            self.mode_started_at = now
            self.charge_stable_started_at = None
            self.return_goal_due_at = now + 1.0
            return
        if (self.return_goal_pending or self.return_goal_handle is not None
                or self.linear_speed > self.stationary_linear
                or self.angular_speed > self.stationary_angular):
            self.charge_stable_started_at = None
            return
        if self.charge_stable_started_at is None:
            self.charge_stable_started_at = now
            return
        if now - self.charge_stable_started_at < self.charge_duration:
            return
        self.total_charging_time += now - self.mode_started_at
        self.energy = self.charge_target
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
            self.publish_state()
            return
        if (self.inject_failure_after_sec >= 0 and self.first_odom_time is not None
                and now - self.first_odom_time >= self.inject_failure_after_sec):
            self.fail("injected_robot_failure")
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
        if self.mode == RETURNING and self.in_charging_zone():
            self.begin_charging()
        elif self.mode == CHARGING:
            self.update_charging(now)
        if self.mode == RETURNING:
            self.monitor_return_progress(now)
        if (
            self.mode == RETURNING
            and self.return_goal_handle is None
            and not self.return_goal_pending
            and now >= self.return_goal_due_at
        ):
            self.send_return_goal()

    def monitor_return_progress(self, now):
        """Cancel a stalled local leg before repeated motion spends its reserve."""
        if (self.mode != RETURNING or self.mission_terminal
                or self.return_goal_handle is None or self.return_goal_target is None
                or self.map_position is None or self.return_goal_cancel_requested):
            return
        distance = math.dist(self.map_position, self.return_goal_target)
        if (self.return_goal_best_distance is None
                or distance < self.return_goal_best_distance - 0.1):
            self.return_goal_best_distance = distance
            self.return_goal_last_progress_at = now
        stalled = (self.return_goal_last_progress_at is not None
                   and now - self.return_goal_last_progress_at >= RETURN_PROGRESS_TIMEOUT_SEC)
        timed_out = (self.return_goal_started_at is not None
                     and now - self.return_goal_started_at >= self.return_goal_timeout_sec)
        if not (stalled or timed_out):
            return
        self.return_goal_cancel_requested = True
        self.get_logger().warning(
            f"Canceling {self.robot_name} return leg after "
            + ("timeout." if timed_out else "no waypoint progress.")
        )
        # Keep the handle until its result, so cancellation cannot overlap a
        # newly admitted local leg. The result path already replans on retry.
        self.return_goal_handle.cancel_goal_async()

    def send_return_goal(self):
        reason = return_attempt_failure_reason(
            self.return_attempts, self.max_return_attempts
        )
        if reason:
            # Nav2 can abort a return while the SLAM/global costmap is still
            # catching up, or while the previous exploration goal is being
            # canceled. Do not convert three rapid transient aborts into a
            # battery failure. Reset the short retry counter and keep the
            # robot in RETURNING until the full return timeout is reached.
            self.return_attempts = 0
            self.return_goal_due_at = self.now() + 5.0
            self.get_logger().warning(
                f"{self.robot_name} return attempt budget exhausted; "
                "waiting for Nav2 recovery before retrying."
            )
            return
        if not self.navigation.server_is_ready():
            self.get_logger().warning(
                f"{self.robot_name} local return waiting for native Nav2 server.",
                throttle_duration_sec=5.0,
            )
            return
        # Replan toward home through known free space. A valid detour may
        # initially move away from home; Euclidean convergence is not a path
        # feasibility test. Never replace a missing route with a straight line.
        if self.return_map_origin is None or self.map_position is None:
            self.get_logger().warning(
                f"{self.robot_name} local return waiting for map/pose.",
                throttle_duration_sec=5.0,
            )
            return
        staged, route = plan_charging_leg(
            self.return_map, self.return_map_resolution, self.return_map_origin,
            self.map_position, (self.charge_x, self.charge_y), self.charge_radius,
        )
        if staged is not None:
            target = (staged.x, staged.y)
            self.return_stage = "charger"
            self.return_escape_target = None
            self.return_waypoint_target = None
        elif not self.return_escape_failed:
            # The map can mark the current footprint inside inflated
            # clearance. Use a short, map-validated escape leg, then rerun
            # the charger planner. Never synthesize a geometric straight line.
            self.return_escape_target = return_escape_pose(
                self.return_map, self.return_map_resolution,
                self.return_map_origin, self.map_position,
                max_escape_m=1.5, clearance_m=RALLY_PATH_CLEARANCE_M,
            )
            if self.return_escape_target is None:
                self.get_logger().warning(
                    f"{self.robot_name} local return has no safe contact/escape route: "
                    f"position={self.map_position}, home={(self.charge_x, self.charge_y)}, "
                    f"map_shape={self.return_map.shape}, origin={self.return_map_origin}, "
                    f"energy={self.energy:.2f}.", throttle_duration_sec=5.0,
                )
                self.return_goal_due_at = self.now() + 1.0
                return
            target = self.return_escape_target
            self.return_stage = "escape"
            self.return_waypoint_target = None
        else:
            self.return_goal_due_at = self.now() + 1.0
            return
        self.return_goal_target = target
        distance = (sum(math.dist(a, b) for a, b in zip(route, route[1:]))
                    if staged is not None else math.dist(self.map_position, target))
        self.return_goal_timeout_sec = max(30.0, 2.0 * distance / self.nominal_speed + 10.0)
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = target[0]
        goal.pose.pose.position.y = target[1]
        yaw = staged.yaw if staged is not None else 0.0
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        self.get_logger().info(
            f"{self.robot_name} return leg ({self.return_stage}) "
            f"from={self.map_position} to={target}."
        )
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
        # The pose can enter the charge zone while the action request is in
        # flight. Cancel a late acceptance before it can drive out again.
        if self.mode != RETURNING or self.mission_terminal:
            handle.cancel_goal_async()
        else:
            self.return_goal_started_at = self.now()
            self.return_goal_last_progress_at = self.return_goal_started_at
            self.return_goal_best_distance = None
            self.return_goal_cancel_requested = False
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
        self.return_goal_target = None
        self.return_goal_started_at = None
        self.return_goal_last_progress_at = None
        self.return_goal_best_distance = None
        self.return_goal_cancel_requested = False
        try:
            status = future.result().status
        except Exception as error:
            status = f"exception: {error}"
        if self.mode != RETURNING:
            return
        if status == GoalStatus.STATUS_SUCCEEDED:
            if self.return_stage in ("escape", "waypoint"):
                self.return_stage = "charger"
                self.return_escape_target = None
                self.return_waypoint_target = None
                self.return_attempts = 0
                self.return_goal_due_at = self.now() + 1.0
            else:
                # Nav2's goal checker already guarantees the final pose is
                # within its configured tolerance. Map->odom can lag by a
                # few centimeters, so do not reject a successful charger
                # goal solely because the duplicated battery pose check is
                # just outside charge_radius. update_charging() still
                # requires the robot to be stationary for charge_duration.
                if self.in_charging_zone():
                    self.begin_charging()
                else:
                    self.return_goal_due_at = self.now() + 1.0
        elif return_attempt_failure_reason(
            self.return_attempts, self.max_return_attempts
        ):
            if self.return_stage == "escape":
                # A stale local escape cell can remain unreachable after
                # SLAM updates. Do not retry that exact pose forever; fall
                # back to the charger-directed short-leg planner.
                self.return_escape_failed = True
                self.return_escape_target = None
                self.return_stage = "charger"
                self.return_waypoint_target = None
            self.return_attempts = 0
            self.return_goal_due_at = self.now() + 5.0
            self.get_logger().warning(
                f"{self.robot_name} return goal was aborted; "
                "retrying after Nav2 recovery."
            )
        else:
            self.return_goal_due_at = self.now() + 1.0

    def fail(self, reason):
        if self.mode == FAILED:
            return
        self.failure_reason = reason
        self.mode = FAILED
        if self.return_goal_handle is not None:
            self.return_goal_handle.cancel_goal_async()
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
                "stamp_sec": self.now(),
                "mode": self.mode,
                "failure_reason": self.failure_reason,
                "energy": max(0.0, self.energy),
                "capacity": self.capacity,
                "charge_target_fraction": self.charge_target_fraction,
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
                "return_path_factor": self.return_path_factor,
                "nominal_speed_mps": self.nominal_speed,
                "return_safety_margin": self.safety_margin,
                "return_timeout_sec": self.return_timeout,
                "charge_duration_sec": self.charge_duration,
                "charge_radius_m": self.charge_radius,
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
