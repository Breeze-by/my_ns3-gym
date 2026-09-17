import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from action_msgs.msg import GoalStatus, GoalStatusArray
from gazebo_msgs.msg import ContactsState, ModelStates
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


@dataclass
class TruthGrid:
    occupied: np.ndarray
    origin_x: float
    origin_y: float
    resolution: float
    rectangle_count: int
    unsupported_collision_count: int


def _pose(element):
    pose = element.find("pose")
    values = [] if pose is None or pose.text is None else pose.text.split()
    values = [float(value) for value in values]
    return tuple((values + [0.0] * 6)[:6])


def _compose(parent, child):
    px, py, pz, proll, ppitch, pyaw = parent
    cx, cy, cz, croll, cpitch, cyaw = child
    cosine = math.cos(pyaw)
    sine = math.sin(pyaw)
    return (
        px + cosine * cx - sine * cy,
        py + sine * cx + cosine * cy,
        pz + cz,
        proll + croll,
        ppitch + cpitch,
        pyaw + cyaw,
    )


def load_truth_grid(world_path, resolution=0.05, slice_height=0.2):
    """Rasterize static SDF box collisions at the robot lidar height."""
    # ponytail: rasterize meshes only when one enters the accessible task area.
    world = ET.parse(world_path).getroot().find("world")
    if world is None:
        raise ValueError(f"No <world> in {world_path}")

    state_poses = {}
    state = world.find("state")
    if state is not None:
        state_poses = {
            model.get("name"): _pose(model)
            for model in state.findall("model")
        }

    rectangles = []
    unsupported = 0
    for model in world.findall("model"):
        model_pose = state_poses.get(model.get("name"), _pose(model))
        for link in model.findall("link"):
            link_pose = _compose(model_pose, _pose(link))
            for collision in link.findall("collision"):
                collision_pose = _compose(link_pose, _pose(collision))
                geometry = collision.find("geometry")
                box = None if geometry is None else geometry.find("box")
                if box is None:
                    if geometry is not None and geometry.find("plane") is None:
                        unsupported += 1
                    continue
                size_text = box.findtext("size")
                if not size_text:
                    continue
                size_x, size_y, size_z = map(float, size_text.split())
                center_x, center_y, center_z, roll, pitch, yaw = collision_pose
                if abs(roll) > 1e-6 or abs(pitch) > 1e-6:
                    unsupported += 1
                    continue
                intersects_slice = (
                    center_z - size_z / 2
                    <= slice_height
                    <= center_z + size_z / 2
                )
                if not intersects_slice:
                    continue
                rectangles.append((center_x, center_y, yaw, size_x, size_y))

    if not rectangles:
        raise ValueError(
            f"No box collisions intersect z={slice_height} in {world_path}"
        )

    all_x = []
    all_y = []
    for center_x, center_y, yaw, size_x, size_y in rectangles:
        cosine = math.cos(yaw)
        sine = math.sin(yaw)
        for local_x in (-size_x / 2, size_x / 2):
            for local_y in (-size_y / 2, size_y / 2):
                all_x.append(center_x + cosine * local_x - sine * local_y)
                all_y.append(center_y + sine * local_x + cosine * local_y)

    origin_x = math.floor(min(all_x) / resolution) * resolution
    origin_y = math.floor(min(all_y) / resolution) * resolution
    width = math.ceil((max(all_x) - origin_x) / resolution)
    height = math.ceil((max(all_y) - origin_y) / resolution)
    occupied = np.zeros((height, width), dtype=bool)

    for center_x, center_y, yaw, size_x, size_y in rectangles:
        radius = math.hypot(size_x, size_y) / 2
        x0 = max(0, math.floor((center_x - radius - origin_x) / resolution))
        x1 = min(width, math.ceil((center_x + radius - origin_x) / resolution))
        y0 = max(0, math.floor((center_y - radius - origin_y) / resolution))
        y1 = min(
            height,
            math.ceil((center_y + radius - origin_y) / resolution),
        )
        xs = origin_x + (np.arange(x0, x1) + 0.5) * resolution
        ys = origin_y + (np.arange(y0, y1) + 0.5) * resolution
        world_x, world_y = np.meshgrid(xs, ys)
        cosine = math.cos(yaw)
        sine = math.sin(yaw)
        dx = world_x - center_x
        dy = world_y - center_y
        local_x = cosine * dx + sine * dy
        local_y = -sine * dx + cosine * dy
        occupied[y0:y1, x0:x1] |= (
            (np.abs(local_x) <= size_x / 2)
            & (np.abs(local_y) <= size_y / 2)
        )

    return TruthGrid(
        occupied,
        origin_x,
        origin_y,
        resolution,
        len(rectangles),
        unsupported,
    )


def compare_occupancy_grid(
    truth, data, width, height, resolution, origin, yaw=0.0
):
    estimated = np.asarray(data, dtype=np.int16).reshape(height, width)
    truth_y, truth_x = np.indices(truth.occupied.shape)
    world_x = truth.origin_x + (truth_x + 0.5) * truth.resolution
    world_y = truth.origin_y + (truth_y + 0.5) * truth.resolution
    dx = world_x - origin[0]
    dy = world_y - origin[1]
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    map_x = np.floor((cosine * dx + sine * dy) / resolution).astype(int)
    map_y = np.floor((-sine * dx + cosine * dy) / resolution).astype(int)
    inside = (map_x >= 0) & (map_x < width) & (map_y >= 0) & (map_y < height)

    sampled = np.full(truth.occupied.shape, -1, dtype=np.int16)
    sampled[inside] = estimated[map_y[inside], map_x[inside]]
    known = sampled >= 0
    predicted_occupied = sampled >= 50
    correct = known & (predicted_occupied == truth.occupied)
    truth_free = ~truth.occupied
    correct_free = known & truth_free & ~predicted_occupied
    intersection = truth.occupied & known & predicted_occupied
    union = truth.occupied | (known & predicted_occupied)

    def ratio(numerator, denominator):
        return float(numerator) / max(1, int(denominator))

    return {
        "truth_cell_count": int(truth.occupied.size),
        "truth_free_cell_count": int(np.count_nonzero(truth_free)),
        "truth_occupied_cell_count": int(np.count_nonzero(truth.occupied)),
        "known_truth_cell_count": int(np.count_nonzero(known)),
        "correct_truth_cell_count": int(np.count_nonzero(correct)),
        "known_coverage_ratio": ratio(np.count_nonzero(known), known.size),
        "correct_coverage_ratio": ratio(np.count_nonzero(correct), known.size),
        "correct_free_coverage_ratio": ratio(
            np.count_nonzero(correct_free), np.count_nonzero(truth_free)
        ),
        "observed_accuracy": ratio(
            np.count_nonzero(correct), np.count_nonzero(known)
        ),
        "occupied_iou": ratio(
            np.count_nonzero(intersection), np.count_nonzero(union)
        ),
    }


def visited_overlap_ratio(visited_by_robot):
    total = sum(len(cells) for cells in visited_by_robot.values())
    union = (
        set().union(*visited_by_robot.values())
        if visited_by_robot
        else set()
    )
    return (total - len(union)) / max(1, len(union))


def _yaw_from_quaternion(quaternion):
    return math.atan2(
        2 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1 - 2 * (quaternion.y ** 2 + quaternion.z ** 2),
    )


class TaskEvaluator(Node):
    def __init__(self):
        super().__init__("task_evaluator")
        self.robot_count = self.declare_parameter("robot_count", 2).value
        self.episode_id = self.declare_parameter("episode_id", "episode").value
        self.world_file = self.declare_parameter("world_file", "").value
        self.gazebo_seed = self.declare_parameter("gazebo_seed", 1).value
        self.output_dir = Path(
            self.declare_parameter(
                "output_dir", "/tmp/multi_robot_evaluation"
            ).value
        )
        self.max_duration = self.declare_parameter(
            "max_duration_sec", 0.0
        ).value
        self.coverage_threshold = self.declare_parameter(
            "coverage_threshold", 0.0
        ).value
        self.truth_resolution = self.declare_parameter(
            "truth_resolution", 0.05
        ).value
        self.visit_resolution = self.declare_parameter(
            "visit_resolution", 0.1
        ).value
        self.collision_cooldown = self.declare_parameter(
            "collision_cooldown_sec", 1.0
        ).value
        self.max_position_step = self.declare_parameter(
            "max_position_step_m", 1.0
        ).value
        self.stop_on_target_found = self.declare_parameter(
            "stop_on_target_found", False
        ).value
        self.stop_on_task_complete = self.declare_parameter(
            "stop_on_task_complete", False
        ).value

        if self.robot_count < 1:
            raise ValueError("robot_count must be positive")
        if not self.world_file:
            raise ValueError("world_file is required")
        if not 0.0 <= self.coverage_threshold <= 1.0:
            raise ValueError("coverage_threshold must be between 0 and 1")
        self.truth = load_truth_grid(self.world_file, self.truth_resolution)
        self.robot_names = [
            f"tb{index}" for index in range(1, self.robot_count + 1)
        ]
        self.positions = {}
        self.velocities = {}
        self.start_positions = {}
        self.previous_positions = {}
        self.path_lengths = {name: 0.0 for name in self.robot_names}
        self.visited = {name: set() for name in self.robot_names}
        self.teleport_jumps = {name: 0 for name in self.robot_names}
        self.goal_ids = {name: set() for name in self.robot_names}
        self.terminal_goal_ids = {name: set() for name in self.robot_names}
        self.nav_succeeded = {name: 0 for name in self.robot_names}
        self.nav_canceled = {name: 0 for name in self.robot_names}
        self.nav_aborted = {name: 0 for name in self.robot_names}
        self.collision_events = {name: 0 for name in self.robot_names}
        self.collision_active = {name: False for name in self.robot_names}
        self.collision_last_time = {name: None for name in self.robot_names}
        self.collision_last_event = {
            name: -math.inf for name in self.robot_names
        }
        self.collision_duration = {name: 0.0 for name in self.robot_names}
        self.collision_messages = {name: 0 for name in self.robot_names}
        self.latest_map = None
        self.map_message_count = 0
        self.model_state_message_count = 0
        self.start_sim_time = None
        self.coverage_times = {0.75: None, 0.8: None, 0.9: None, 0.95: None}
        self.task_phase = "EXPLORE"
        self.target_found = False
        self.time_to_detect = None
        self.detecting_robot = ""
        self.target_x = None
        self.target_y = None
        self.target_confirmation_frames = None
        self.target_max_distance = None
        self.target_field_of_view = None
        self.time_to_rally = None
        self.completion_time = None
        self.rally_assignments = {}
        self.rally_position_tolerance = None
        self.rally_linear_tolerance = None
        self.rally_angular_tolerance = None
        self.rally_hold_sec = None
        self.task_failure_reason = ""
        self.failure_pending_since = None
        self.finalized = False

        map_qos = QoSProfile(depth=1)
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        self.input_subscriptions = [
            self.create_subscription(
                OccupancyGrid, "/merge_map", self._map_callback, map_qos
            ),
            self.create_subscription(
                ModelStates,
                "/gazebo/model_states",
                self._model_states_callback,
                10,
            ),
            self.create_subscription(
                String, "/task_state", self._task_state_callback, map_qos
            ),
            self.create_subscription(
                String,
                "/target_detection",
                self._target_detection_callback,
                map_qos,
            ),
            self.create_subscription(
                String,
                "/rally_assignments",
                self._rally_assignments_callback,
                map_qos,
            ),
            self.create_subscription(
                String,
                "/task_failure",
                self._task_failure_callback,
                map_qos,
            ),
        ]
        for name in self.robot_names:
            self.input_subscriptions.append(
                self.create_subscription(
                    GoalStatusArray,
                    f"/{name}/navigate_to_pose/_action/status",
                    lambda message, robot=name: self._status_callback(
                        message, robot
                    ),
                    10,
                )
            )
            self.input_subscriptions.append(
                self.create_subscription(
                    ContactsState,
                    f"/{name}/collision",
                    lambda message, robot=name: self._collision_callback(
                        message, robot
                    ),
                    10,
                )
            )
        self.timer = self.create_timer(0.5, self._timer_callback)
        self.get_logger().info(
            f"Loaded {self.truth.rectangle_count} truth rectangles from "
            f"{self.world_file}"
        )

    def _now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def _map_callback(self, message):
        self.latest_map = message
        self.map_message_count += 1
        self._maybe_start(self._now())
        self._update_coverage_times()

    def _model_states_callback(self, message):
        self.model_state_message_count += 1
        for name in self.robot_names:
            if name in message.name:
                index = message.name.index(name)
                pose = message.pose[index]
                self.positions[name] = (pose.position.x, pose.position.y)
                twist = message.twist[index]
                self.velocities[name] = (
                    math.hypot(twist.linear.x, twist.linear.y),
                    abs(twist.angular.z),
                )

        now = self._now()
        if self.start_sim_time is None:
            self._maybe_start(now)
            return

        for name in self.robot_names:
            current = self.positions.get(name)
            previous = self.previous_positions.get(name)
            if current is None or previous is None:
                continue
            distance = math.dist(previous, current)
            if distance <= self.max_position_step:
                self.path_lengths[name] += distance
            else:
                self.teleport_jumps[name] += 1
            self.previous_positions[name] = current
            self.visited[name].add(
                (
                    math.floor(current[0] / self.visit_resolution),
                    math.floor(current[1] / self.visit_resolution),
                )
            )

    def _maybe_start(self, now):
        if (
            self.start_sim_time is not None
            or now <= 0.0
            or self.latest_map is None
            or any(name not in self.positions for name in self.robot_names)
        ):
            return
        self.start_sim_time = now
        self.start_positions = self.positions.copy()
        self.previous_positions = self.positions.copy()
        for name, position in self.positions.items():
            self.visited[name].add(
                (
                    math.floor(position[0] / self.visit_resolution),
                    math.floor(position[1] / self.visit_resolution),
                )
            )
        self.get_logger().info(f"Episode {self.episode_id} evaluation started")

    def _status_callback(self, message, robot):
        for status in message.status_list:
            goal_id = bytes(status.goal_info.goal_id.uuid)
            self.goal_ids[robot].add(goal_id)
            if goal_id in self.terminal_goal_ids[robot]:
                continue
            if status.status == GoalStatus.STATUS_SUCCEEDED:
                self.nav_succeeded[robot] += 1
            elif status.status == GoalStatus.STATUS_CANCELED:
                self.nav_canceled[robot] += 1
            elif status.status == GoalStatus.STATUS_ABORTED:
                self.nav_aborted[robot] += 1
            else:
                continue
            self.terminal_goal_ids[robot].add(goal_id)

    def _task_state_callback(self, message):
        self.task_phase = message.data
        if self.start_sim_time is None:
            return
        elapsed = max(0.0, self._now() - self.start_sim_time)
        if message.data == "RALLY" and self.time_to_rally is None:
            self.time_to_rally = elapsed
        elif message.data == "COMPLETE" and self.completion_time is None:
            self.completion_time = elapsed
            if self.stop_on_task_complete:
                self.finalize("task_complete")
                rclpy.shutdown()
        elif message.data == "FAILED" and self.stop_on_task_complete:
            self.failure_pending_since = self._now()

    def _rally_assignments_callback(self, message):
        event = json.loads(message.data)
        self.rally_assignments = event["poses"]
        self.rally_position_tolerance = event["position_tolerance_m"]
        self.rally_linear_tolerance = event["linear_tolerance_mps"]
        self.rally_angular_tolerance = event["angular_tolerance_radps"]
        self.rally_hold_sec = event["hold_sec"]

    def _task_failure_callback(self, message):
        self.task_failure_reason = message.data
        if self.task_phase == "FAILED" and self.stop_on_task_complete:
            self.finalize("mission_failed")
            rclpy.shutdown()

    def _target_detection_callback(self, message):
        if self.target_found:
            return
        event = json.loads(message.data)
        self.target_found = True
        self.task_phase = "FOUND"
        self.detecting_robot = event["robot"]
        self.target_x = event["target_x"]
        self.target_y = event["target_y"]
        self.target_confirmation_frames = event["confirmation_frames"]
        self.target_max_distance = event["max_distance_m"]
        self.target_field_of_view = event["field_of_view_deg"]
        if self.start_sim_time is not None:
            self.time_to_detect = max(0.0, self._now() - self.start_sim_time)
        if self.stop_on_target_found:
            self.finalize("target_found")
            rclpy.shutdown()

    def _collision_callback(self, message, robot):
        now = self._now()
        self.collision_messages[robot] += 1
        previous_time = self.collision_last_time[robot]
        if self.collision_active[robot] and previous_time is not None:
            self.collision_duration[robot] += max(0.0, now - previous_time)
        active = bool(message.states)
        if (
            active
            and not self.collision_active[robot]
            and now - self.collision_last_event[robot]
            >= self.collision_cooldown
        ):
            self.collision_events[robot] += 1
            self.collision_last_event[robot] = now
            self.get_logger().warning(
                f"Collision event for {robot} during {self.task_phase}."
            )
        self.collision_active[robot] = active
        self.collision_last_time[robot] = now

    def _timer_callback(self):
        if self.start_sim_time is None:
            return
        if (
            self.failure_pending_since is not None
            and self._now() - self.failure_pending_since >= 0.5
        ):
            self.finalize("mission_failed")
            rclpy.shutdown()
            return
        coverage = self._map_metrics().get("correct_free_coverage_ratio", 0.0)
        if self.coverage_threshold > 0 and coverage >= self.coverage_threshold:
            self.finalize("coverage_reached")
            rclpy.shutdown()
            return
        if (
            self.max_duration > 0
            and self._now() - self.start_sim_time >= self.max_duration
        ):
            self.finalize("timeout")
            rclpy.shutdown()

    def _update_coverage_times(self):
        if self.start_sim_time is None:
            return
        coverage = self._map_metrics().get("correct_free_coverage_ratio", 0.0)
        elapsed = max(0.0, self._now() - self.start_sim_time)
        for threshold in self.coverage_times:
            first_crossing = self.coverage_times[threshold] is None
            if first_crossing and coverage >= threshold:
                self.coverage_times[threshold] = elapsed

    def _map_metrics(self):
        if self.latest_map is None:
            return {}
        info = self.latest_map.info
        yaw = _yaw_from_quaternion(info.origin.orientation)
        metrics = compare_occupancy_grid(
            self.truth,
            self.latest_map.data,
            info.width,
            info.height,
            info.resolution,
            (info.origin.position.x, info.origin.position.y),
            yaw,
        )
        metrics.update(
            {
                "merged_map_frame": self.latest_map.header.frame_id,
                "merged_map_width": info.width,
                "merged_map_height": info.height,
                "merged_map_resolution": info.resolution,
                "merged_map_origin_x": info.origin.position.x,
                "merged_map_origin_y": info.origin.position.y,
                "merged_map_origin_yaw": yaw,
            }
        )
        return metrics

    def finalize(self, termination_reason):
        if self.finalized:
            return
        self.finalized = True
        end_time = self._now()
        if self.start_sim_time is None:
            termination_reason = "no_data"
            elapsed = 0.0
        else:
            elapsed = max(0.0, end_time - self.start_sim_time)

        robots = {}
        for name in self.robot_names:
            start = self.start_positions.get(name, (None, None))
            end = self.positions.get(name, (None, None))
            velocity = self.velocities.get(name, (None, None))
            rally_target = self.rally_assignments.get(name, {})
            rally_error = None
            if end[0] is not None and "x" in rally_target:
                rally_error = math.dist(
                    end, (rally_target["x"], rally_target["y"])
                )
            robots[name] = {
                "start_x": start[0],
                "start_y": start[1],
                "end_x": end[0],
                "end_y": end[1],
                "path_length_m": self.path_lengths[name],
                "visited_cell_count": len(self.visited[name]),
                "teleport_jump_count": self.teleport_jumps[name],
                "nav_goal_count": len(self.goal_ids[name]),
                "nav_succeeded": self.nav_succeeded[name],
                "nav_canceled": self.nav_canceled[name],
                "nav_aborted": self.nav_aborted[name],
                "collision_events": self.collision_events[name],
                "collision_duration_sec": self.collision_duration[name],
                "collision_message_count": self.collision_messages[name],
                "final_linear_speed_mps": velocity[0],
                "final_angular_speed_radps": velocity[1],
                "rally_target_x": rally_target.get("x"),
                "rally_target_y": rally_target.get("y"),
                "rally_target_yaw": rally_target.get("yaw"),
                "rally_final_error_m": rally_error,
            }

        success = termination_reason in (
            "coverage_reached",
            "target_found",
            "task_complete",
        )
        rally_poses = list(self.rally_assignments.values())
        rally_separations = [
            math.dist(
                (first["x"], first["y"]),
                (second["x"], second["y"]),
            )
            for index, first in enumerate(rally_poses)
            for second in rally_poses[index + 1:]
        ]
        result = {
            "schema_version": 4,
            "episode_id": self.episode_id,
            "world_file": self.world_file,
            "gazebo_seed": self.gazebo_seed,
            "robot_count": self.robot_count,
            "task_phase": (
                "COMPLETE"
                if termination_reason == "coverage_reached"
                else self.task_phase
            ),
            "success": success,
            "termination_reason": termination_reason,
            "failure_reason": (
                ""
                if success
                else self.task_failure_reason or termination_reason
            ),
            "coverage_threshold": self.coverage_threshold,
            "target_found": self.target_found,
            "time_to_detect_sec": self.time_to_detect,
            "detecting_robot": self.detecting_robot,
            "target_x": self.target_x,
            "target_y": self.target_y,
            "target_confirmation_frames": self.target_confirmation_frames,
            "target_max_distance_m": self.target_max_distance,
            "target_field_of_view_deg": self.target_field_of_view,
            "time_to_rally_sec": self.time_to_rally,
            "completion_time_sec": self.completion_time,
            "rally_assignments": self.rally_assignments,
            "rally_position_tolerance_m": self.rally_position_tolerance,
            "rally_linear_tolerance_mps": self.rally_linear_tolerance,
            "rally_angular_tolerance_radps": self.rally_angular_tolerance,
            "rally_hold_sec": self.rally_hold_sec,
            "rally_min_separation_m": (
                min(rally_separations) if rally_separations else None
            ),
            "time_to_75_coverage_sec": self.coverage_times[0.75],
            "time_to_80_coverage_sec": self.coverage_times[0.8],
            "time_to_90_coverage_sec": self.coverage_times[0.9],
            "time_to_95_coverage_sec": self.coverage_times[0.95],
            "start_sim_time_sec": self.start_sim_time,
            "end_sim_time_sec": end_time,
            "elapsed_sim_time_sec": elapsed,
            "map_message_count": self.map_message_count,
            "model_state_message_count": self.model_state_message_count,
            "truth_resolution": self.truth.resolution,
            "truth_origin_x": self.truth.origin_x,
            "truth_origin_y": self.truth.origin_y,
            "truth_width": self.truth.occupied.shape[1],
            "truth_height": self.truth.occupied.shape[0],
            "truth_rectangle_count": self.truth.rectangle_count,
            "truth_unsupported_collision_count": (
                self.truth.unsupported_collision_count
            ),
            "total_path_length_m": sum(self.path_lengths.values()),
            "visit_resolution": self.visit_resolution,
            "union_visited_cell_count": len(
                set().union(*self.visited.values())
            ),
            "search_overlap_ratio": visited_overlap_ratio(self.visited),
            "collision_events": sum(self.collision_events.values()),
            "collision_duration_sec": sum(self.collision_duration.values()),
            "collision_monitoring_active": all(
                count > 0 for count in self.collision_messages.values()
            ),
            "nav_goal_count": sum(len(ids) for ids in self.goal_ids.values()),
            "nav_succeeded": sum(self.nav_succeeded.values()),
            "nav_canceled": sum(self.nav_canceled.values()),
            "nav_aborted": sum(self.nav_aborted.values()),
            **self._map_metrics(),
            "robots": robots,
        }
        self._write_outputs(result)

    def _write_outputs(self, result):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.episode_id)
        json_path = self.output_dir / f"{safe_id}.json"
        csv_path = self.output_dir / f"{safe_id}.csv"
        with json_path.open("w") as output:
            json.dump(result, output, indent=2, sort_keys=True)

        row = {key: value for key, value in result.items() if key != "robots"}
        for robot, metrics in result["robots"].items():
            for key, value in metrics.items():
                row[f"{robot}_{key}"] = value
        with csv_path.open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=row.keys())
            writer.writeheader()
            writer.writerow(row)
        self.get_logger().info(
            f"Evaluation saved to {json_path} and {csv_path}"
        )


def main(args=None):
    rclpy.init(args=args)
    evaluator = TaskEvaluator()
    try:
        rclpy.spin(evaluator)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        evaluator.finalize("shutdown")
        evaluator.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
