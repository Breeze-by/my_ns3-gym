from collections import deque
import csv
from dataclasses import dataclass
import io
import json
import math
import os
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

from action_msgs.msg import GoalStatus, GoalStatusArray
from gazebo_msgs.msg import ContactsState, ModelStates
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Header, String
from std_srvs.srv import Trigger

from .mr3_contacts import CONTACT_COMPONENTS, ContactMonitor, contact_topics
from .mr3_episode import TASK_FAILURE_REASONS, elapsed_ns, timestamp_ns
from .mr3_information import map_digest
from .mr3_reward import RewardLedger
from .mr3_task_contract import (
    compare_contract_occupancy_grid, load_contract_truth, load_task_contract,
    sample_contract_occupancy_grid,
)


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


def evaluation_termination_reason(
    coverage, threshold, elapsed, duration, collision_events, monitoring_active,
    control_failure="",
):
    """Apply the episode deadline and safety checks before coverage success."""
    if duration > 0 and elapsed >= duration:
        return "timeout"
    if control_failure:
        return control_failure
    if collision_events:
        return "collision"
    if threshold > 0 and coverage >= threshold:
        return (
            "coverage_reached" if monitoring_active
            else "collision_monitoring_unavailable"
        )
    return None


def mr3_quality_pass(metrics, quality):
    """Apply the declared quality gates independently of coverage reward."""
    fields = ("observed_accuracy", "occupied_iou", "false_free_ratio")
    if any(not isinstance(metrics.get(name), (int, float))
           or isinstance(metrics[name], bool) or not math.isfinite(metrics[name])
           for name in fields):
        return False
    return (
        metrics["observed_accuracy"] >= quality["min_observed_accuracy"]
        and metrics["occupied_iou"] >= quality["min_occupied_iou"]
        and metrics["false_free_ratio"] <= quality["max_false_free_ratio"]
    )


def mr3_participation_pass(path_lengths, goal_ids, participation):
    names = {"tb1", "tb2", "tb3"}
    return set(path_lengths) == names and set(goal_ids) == names and all(
        math.isfinite(path_lengths[name])
        and path_lengths[name] >= participation["min_path_length_m"]
        and len(goal_ids[name]) >= participation["min_goal_count"]
        for name in names
    )


def _yaw_from_quaternion(quaternion):
    return math.atan2(
        2 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1 - 2 * (quaternion.y ** 2 + quaternion.z ** 2),
    )


class TaskEvaluator(Node):
    def __init__(self):
        super().__init__("task_evaluator")
        self.robot_count = self.declare_parameter("robot_count", 3).value
        self.task_contract_path = self.declare_parameter("task_contract_path", "").value
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

        if self.robot_count < 1:
            raise ValueError("robot_count must be positive")
        if not self.world_file:
            raise ValueError("world_file is required")
        if not 0.0 <= self.coverage_threshold <= 1.0:
            raise ValueError("coverage_threshold must be between 0 and 1")
        for name, value, positive in (
            ("max_duration_sec", self.max_duration, False),
            ("truth_resolution", self.truth_resolution, True),
            ("visit_resolution", self.visit_resolution, True),
            ("max_position_step_m", self.max_position_step, True),
            ("collision_cooldown_sec", self.collision_cooldown, False),
        ):
            if not math.isfinite(value) or value < 0 or (positive and value == 0):
                raise ValueError(f"Invalid {name}: {value}")
        self.task_contract = None
        self.contact_monitor = None
        self.pending_contacts = []
        self.contact_subscription_started_sim_time_sec = None
        self.contact_subscription_bootstrap_state = "waiting_for_active_sim_clock"
        self.contact_clock_overflow_diagnostic = None
        self.navigation_protocol_closed = False
        self.stop_requested_sim_time = None
        self.stop_acknowledgment = None
        self.map_contract_failure = ""
        self.initial_map_metrics = None
        self.task_ready_published = None
        self.legacy_truth = load_truth_grid(self.world_file, self.truth_resolution)
        self.truth = self.legacy_truth
        if self.task_contract_path:
            self.task_contract = load_task_contract(self.task_contract_path, self.world_file)
            contract = self.task_contract.data
            if self.robot_count != 3:
                raise ValueError("MR3 task requires exactly three robots")
            if self.max_duration not in (0.0, contract["max_duration_sec"]):
                raise ValueError("max_duration_sec conflicts with the frozen MR3 contract")
            if self.coverage_threshold not in (0.0, contract["coverage_threshold"]):
                raise ValueError("coverage_threshold conflicts with the frozen MR3 contract")
            if self.truth_resolution != contract["resolution"]:
                raise ValueError("truth_resolution conflicts with the frozen MR3 contract")
            self.max_duration = contract["max_duration_sec"]
            self.coverage_threshold = contract["coverage_threshold"]
            self.truth = load_contract_truth(self.world_file, self.task_contract)
            self.contact_monitor = ContactMonitor(
                contract["robots"], contract["support_collision_names"],
                contract["contact_monitor_max_age_sec"],
                compact=True,
            )
        self.robot_names = [
            f"tb{index}" for index in range(1, self.robot_count + 1)
        ]
        self.positions = {}
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
        self.latest_map_received_sim_time = None
        self.map_message_count = 0
        self.model_state_message_count = 0
        self.start_sim_time = None
        self.coverage_times = {0.75: None, 0.8: None, 0.9: None, 0.95: None}
        self.finalized = False
        self.final_result = None
        self.training_reward_enabled = self.declare_parameter(
            "training_reward_enabled", False,
        ).value
        self.training_terminal_probe = self.declare_parameter(
            "training_terminal_probe", False,
        ).value
        self.training_ack_wall_guard_sec = self.declare_parameter(
            "training_ack_wall_guard_sec", 90.,
        ).value
        if self.training_reward_enabled and self.task_contract is None:
            raise ValueError("Training rewards require the explicit MR3 task contract")
        if self.training_terminal_probe and not self.training_reward_enabled:
            raise ValueError("Training terminal probe requires isolated training rewards")
        if (not math.isfinite(self.training_ack_wall_guard_sec)
                or self.training_ack_wall_guard_sec <= 0):
            raise ValueError("training_ack_wall_guard_sec must be finite and positive")
        self.reward_ledger = None
        self.reward_reset_bound = False
        self.reward_map_cache = deque(maxlen=8)
        self.reward_requests = {}
        self.pending_reward_requests = {}
        self.reward_events = []
        self.reward_switch_goal_ids = set()
        self.training_external_cut = None
        self.training_acknowledged = False
        self.training_ack_deadline_wall = None
        self.pending_training_finalize = None
        self.task_terminal_notice_published = False
        self.diagnostic_failure_request = None
        self.pending_diagnostic_failure = None
        self.probe_finalize_service = None
        if self.declare_parameter("allow_probe_finalize", False).value:
            if self.task_contract is None:
                raise ValueError("Probe finalization requires an explicit MR3 task contract")
            self.probe_finalize_service = self.create_service(
                Trigger, "/mr3/probe_finalize", self._probe_finalize_callback)
        self.control_failure = ""

        map_qos = QoSProfile(depth=1)
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        self.input_subscriptions = [
            self.create_subscription(
                OccupancyGrid, "/merge_map", self._map_callback, map_qos
            ),
            self.create_subscription(
                String, "/exploration_failure", self._control_failure_callback,
                map_qos,
            ),
            self.create_subscription(
                ModelStates,
                "/gazebo/model_states",
                self._model_states_callback,
                10,
            ),
        ]
        if self.task_contract:
            self.task_ready_publisher = self.create_publisher(Bool, "/task_monitor_ready", map_qos)
            self.task_stop_publisher = self.create_publisher(
                Header, "/exploration_stop_request", map_qos
            )
            self.input_subscriptions.extend([
                self.create_subscription(
                    Header, "/exploration_start", self._release_callback, map_qos
                ),
                self.create_subscription(
                    String, "/exploration_stopped", self._stopped_callback, map_qos
                ),
            ])
        if self.training_reward_enabled:
            self.task_terminal_publisher = self.create_publisher(
                String, "/mr3/task_terminal", map_qos,
            )
            self.reward_response_publisher = self.create_publisher(
                String, "/mr3/reward_response", 20,
            )
            self.reward_ready_publisher = self.create_publisher(
                String, "/mr3/reward_ready", map_qos,
            )
            self.input_subscriptions.extend([
                self.create_subscription(
                    String, "/mr3/reward_request", self._reward_request_callback, 20,
                ),
                self.create_subscription(
                    String, "/mr3/training_finalize", self._training_finalize_callback, 20,
                ),
                self.create_subscription(String, "/mr3/events", self._reward_event_callback, 100),
            ])
            self.reward_clock_timer = self.create_timer(.02, self._drain_reward_requests)
            if self.training_terminal_probe:
                self.input_subscriptions.append(self.create_subscription(
                    String, "/mr3/diagnostic_failure", self._diagnostic_failure_callback, 10,
                ))
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
            if not self.task_contract:
                self.input_subscriptions.append(self.create_subscription(
                    ContactsState, f"/{name}/collision",
                    lambda message, robot=name: self._collision_callback(message, robot), 10,
                ))
        self.timer = self.create_timer(0.1 if self.task_contract else 0.5, self._timer_callback)
        self.get_logger().info(
            f"Loaded {self.truth.rectangle_count} truth rectangles from "
            f"{self.world_file}"
        )

    def _now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def _mr3_contact_callback(self, message, robot, component):
        if self.finalized:
            return
        now = self._now()
        self._drain_contacts(now)
        stamp = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
        # /clock and sensor DDS topics can arrive in either order. Never apply
        # a future contact sample or rewrite its source stamp to receipt time.
        if stamp > now:
            self.pending_contacts.append((stamp, robot, component, message))
            if len(self.pending_contacts) > 256:
                self.control_failure = "contact_clock_desynchronization"
                if self.contact_clock_overflow_diagnostic is None:
                    sources = [entry[0] for entry in self.pending_contacts]
                    self.contact_clock_overflow_diagnostic = {
                        "now_sim_time_sec": now,
                        "pending_count": len(sources),
                        "min_source_sim_time_sec": min(sources),
                        "max_source_sim_time_sec": max(sources),
                        "contact_subscription_bootstrap_state": (
                            self.contact_subscription_bootstrap_state
                        ),
                        "contact_subscription_started_sim_time_sec": (
                            self.contact_subscription_started_sim_time_sec
                        ),
                        "start_sim_time_sec": self.start_sim_time,
                    }
                self.finalize("navigation_failure")
            return
        self.contact_monitor.update(robot, component, message, now)

    def _drain_contacts(self, now):
        pending, self.pending_contacts = self.pending_contacts, []
        for stamp, robot, component, message in sorted(pending, key=lambda entry: entry[0]):
            if stamp <= now:
                self.contact_monitor.update(robot, component, message, now)
            else:
                self.pending_contacts.append((stamp, robot, component, message))

    def _release_callback(self, message):
        if self.finalized or self.start_sim_time is not None:
            return
        stamp = message.stamp.sec + message.stamp.nanosec / 1e9
        now = self._now()
        if not math.isfinite(stamp) or stamp <= 0 or message.frame_id != "map":
            self.finalize("invalid_task_release")
            return
        if (
            self.contact_subscription_started_sim_time_sec is None
            or self.task_ready_published is not True
        ):
            self.finalize("invalid_task_release")
            return
        if stamp > now:
            # Retain the release until /clock reaches it, just like sensors.
            self.pending_release = message
            return
        self._drain_contacts(now)
        self.start_sim_time = stamp
        self.start_positions = self.positions.copy()
        self.previous_positions = self.positions.copy()
        self.contact_monitor.start(now)
        self.initial_map_metrics = self._map_metrics()
        if getattr(self, "training_reward_enabled", False):
            self.reward_ledger = RewardLedger(
                self.episode_id, stamp, ~self.truth.occupied & self.truth.roi_mask,
                self._reward_correct_free_mask(),
            )
            self.reward_ready_publisher.publish(String(data=json.dumps({
                "schema": "mr3-reward-ready-v1", "epoch": self.episode_id,
                "start_sim_time": stamp, "task_contract_sha256": self.task_contract.sha256,
                "world_sha256": self.truth.world_sha256, "reset_bound": False,
                "initial_map_payload_sha256": map_digest(self.latest_map),
            }, sort_keys=True)))
        self.get_logger().info(
            f"Episode {self.episode_id} released at sim_time={stamp:.9f}"
        )
        self._update_coverage_times()
        self._timer_callback()
        if getattr(self, "training_reward_enabled", False):
            self._drain_reward_requests()

    def _stopped_callback(self, message):
        external_cut = getattr(self, "training_external_cut", None)
        requested_stop = self.stop_requested_sim_time
        if requested_stop is None and external_cut is not None:
            requested_stop = external_cut
        if self.finalized or requested_stop is None:
            return
        try:
            acknowledgment = json.loads(message.data)
            start = acknowledgment["start_sim_time_sec"]
            stop = acknowledgment["stop_sim_time_sec"]
            valid = (
                type(acknowledgment["pending_goal_count"]) is int
                and acknowledgment["pending_goal_count"] == 0
                and acknowledgment["robot_names"] == self.robot_names
                and acknowledgment["navigation_failure"] is False
                and math.isfinite(start) and math.isfinite(stop)
                and math.isclose(start, self.start_sim_time, abs_tol=1e-9)
                and requested_stop <= stop
            )
        except (ValueError, TypeError, KeyError):
            valid = False
        if not valid:
            self.finalize("navigation_closure_invalid")
            return
        if stop > self._now():
            self.pending_stop_ack = message
            return
        self.stop_acknowledgment = acknowledgment
        self.navigation_protocol_closed = True
        self._timer_callback()
        if getattr(self, "pending_training_finalize", None) is not None:
            pending = self.pending_training_finalize
            self.pending_training_finalize = None
            self._training_finalize_callback(String(data=json.dumps(pending)))

    def _map_callback(self, message):
        if self.finalized:
            return
        if self.task_contract and message.header.frame_id.lstrip("/") != "map":
            self.map_contract_failure = "unexpected_map_frame"
            self.finalize("map_contract_error")
            return
        self.latest_map = message
        self.latest_map_received_sim_time = self._now()
        self.map_message_count += 1
        if getattr(self, "training_reward_enabled", False):
            self.reward_map_cache.append({
                "message": message, "received_stamp": self.latest_map_received_sim_time,
                "received_sequence": self.map_message_count, "payload_sha256": None,
            })
        self._maybe_start(self._now())
        self._update_coverage_times()
        self._timer_callback()
        if getattr(self, "training_reward_enabled", False):
            self._drain_reward_requests()

    def _model_states_callback(self, message):
        if self.finalized:
            return
        self.model_state_message_count += 1
        for name in self.robot_names:
            if name in message.name:
                pose = message.pose[message.name.index(name)]
                self.positions[name] = (pose.position.x, pose.position.y)

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
        if self.task_contract:
            return  # MR3 starts only at the controller's common release.
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
        if self.finalized:
            return
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

    def _collision_callback(self, message, robot):
        if self.finalized:
            return
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
        self.collision_active[robot] = active
        self.collision_last_time[robot] = now
        if active:
            self._timer_callback()

    def _control_failure_callback(self, message):
        if self.finalized:
            return
        self.control_failure = message.data
        if self.task_contract:
            self._timer_callback()
        if not self.finalized:
            self.finalize("navigation_failure")

    def _diagnostic_failure_callback(self, message):
        """Explicit, disabled-by-default P1C terminal IPC probe; never contact data."""
        if not self.training_terminal_probe:
            return
        try:
            request = json.loads(message.data)
            if not isinstance(request, dict) or set(request) != {
                    "epoch", "request_id", "target_time_ns", "reason"}:
                raise ValueError("invalid_diagnostic_failure_fields")
            if request["epoch"] != self.episode_id:
                raise ValueError("wrong_diagnostic_failure_epoch")
            if (not isinstance(request["request_id"], str) or not request["request_id"]
                    or type(request["target_time_ns"]) is not int
                    or request["target_time_ns"] < 0
                    or request["reason"] != "P1C_DIAGNOSTIC_FAILURE"):
                raise ValueError("invalid_diagnostic_failure_request")
            if self.diagnostic_failure_request is not None:
                if request != self.diagnostic_failure_request:
                    raise ValueError("conflicting_diagnostic_failure_request")
                return
            if self.finalized or self.start_sim_time is None:
                raise ValueError("diagnostic_failure_requires_live_released_task")
            if request["target_time_ns"] < timestamp_ns(self._now()):
                raise ValueError("diagnostic_failure_target_passed")
            self.diagnostic_failure_request = request
            self.pending_diagnostic_failure = request
            self._poll_diagnostic_failure()
        except (ValueError, TypeError, KeyError) as error:
            self.get_logger().error("Rejected P1C diagnostic failure: " + str(error))

    def _poll_diagnostic_failure(self):
        pending = self.pending_diagnostic_failure
        if not self.training_terminal_probe or pending is None or self.finalized:
            return
        now_ns = timestamp_ns(self._now())
        if now_ns < pending["target_time_ns"]:
            return
        self.pending_diagnostic_failure = None
        if now_ns != pending["target_time_ns"]:
            self.get_logger().error("Rejected P1C diagnostic failure: target watermark passed")
            return
        self._control_failure_callback(String(data=pending["reason"]))

    def _timer_callback(self):
        if self.finalized:
            return
        if self.task_contract:
            self._mr3_timer_callback()
            return
        if self.start_sim_time is None:
            return
        coverage = self._map_metrics().get("correct_free_coverage_ratio", 0.0)
        reason = evaluation_termination_reason(
            coverage, self.coverage_threshold,
            self._now() - self.start_sim_time, self.max_duration,
            sum(self.collision_events.values()),
            all(count > 0 for count in self.collision_messages.values()),
            "navigation_failure" if self.control_failure else "",
        )
        if reason:
            self.finalize(reason)

    def _mr3_timer_callback(self):
        now = self._now()
        if self.contact_subscription_started_sim_time_sec is None:
            if not self.get_clock().ros_time_is_active or not math.isfinite(now) or now <= 0:
                return
            self.contact_subscription_bootstrap_state = "starting_contact_subscriptions"
            for name in self.robot_names:
                for component, topic in contact_topics(name, compact=True).items():
                    self.input_subscriptions.append(self.create_subscription(
                        ContactsState, topic,
                        lambda message, robot=name, part=component: self._mr3_contact_callback(
                            message, robot, part
                        ),
                        20,
                    ))
            self.contact_subscription_started_sim_time_sec = now
            self.contact_subscription_bootstrap_state = "contact_subscriptions_started"
            return
        self._drain_contacts(now)
        pending_ack = getattr(self, "pending_stop_ack", None)
        if pending_ack is not None and json.loads(pending_ack.data)["stop_sim_time_sec"] <= now:
            self.pending_stop_ack = None
            self._stopped_callback(pending_ack)
            return
        pending_release = getattr(self, "pending_release", None)
        if pending_release is not None and (
            pending_release.stamp.sec + pending_release.stamp.nanosec / 1e9 <= now
        ):
            self.pending_release = None
            self._release_callback(pending_release)
            return
        summary = self.contact_monitor.summary(now)
        ready = (
            summary["fresh"] and not summary["ever_unhealthy"]
            and summary["event_count"] == 0 and not self.control_failure
            and self.latest_map is not None and not self.map_contract_failure
            and all(name in self.positions for name in self.robot_names)
        )
        if ready != self.task_ready_published:
            message = Bool()
            message.data = ready
            self.task_ready_publisher.publish(message)
            self.task_ready_published = ready
        if self.start_sim_time is None:
            if summary["event_count"]:
                self.finalize("startup_collision")
            elif self.control_failure:
                self.finalize("navigation_failure")
            return
        elapsed = elapsed_ns(self.start_sim_time, now) / 1e9
        reason = self._mr3_termination_reason(elapsed, summary)
        if reason:
            self.finalize(reason)

    def _mr3_termination_reason(self, elapsed, summary):
        # Deadline precedence includes the bounded terminal-goal handshake.
        if elapsed >= self.max_duration:
            return "timeout"
        if elapsed < 0:
            return "simulation_clock_regressed"
        if self.control_failure:
            return "navigation_failure"
        if summary["event_count"]:
            return "collision"
        if summary["ever_unhealthy"] or not summary["fresh"]:
            return "collision_monitoring_interrupted"
        if self.map_contract_failure:
            return "map_contract_error"
        if any(self.teleport_jumps.values()):
            return "pose_discontinuity"
        if getattr(self, "training_external_cut", None) is not None:
            return None  # Sealed external cut cannot later turn into coverage success.
        metrics = self._map_metrics()
        contract = self.task_contract.data
        eligible = (
            metrics.get("correct_free_coverage_ratio", 0.0) >= self.coverage_threshold
            and mr3_quality_pass(metrics, contract["quality"])
            and mr3_participation_pass(self.path_lengths, self.goal_ids, contract["participation"])
        )
        if self.stop_requested_sim_time is not None:
            if not eligible:
                return "task_gate_regressed_during_closure"
            if self.navigation_protocol_closed:
                return "coverage_reached"
            closure_elapsed = elapsed_ns(self.stop_requested_sim_time, self._now()) / 1e9
            if closure_elapsed >= contract["navigation_closure_timeout_sec"]:
                return "navigation_closure_timeout"
            return None
        if eligible:
            self.stop_requested_sim_time = self._now()
            request = Header()
            request.stamp = self.get_clock().now().to_msg()
            request.frame_id = "map"
            self.task_stop_publisher.publish(request)
        return None

    def _update_coverage_times(self):
        if self.start_sim_time is None:
            return
        coverage = self._map_metrics().get("correct_free_coverage_ratio", 0.0)
        elapsed = max(0.0, elapsed_ns(self.start_sim_time, self._now()) / 1e9)
        if self.max_duration > 0 and elapsed >= self.max_duration:
            return
        for threshold in self.coverage_times:
            first_crossing = self.coverage_times[threshold] is None
            if first_crossing and coverage >= threshold:
                self.coverage_times[threshold] = elapsed

    def _map_metrics(self):
        if self.latest_map is None:
            return {}
        info = self.latest_map.info
        yaw = _yaw_from_quaternion(info.origin.orientation)
        compare = compare_contract_occupancy_grid if self.task_contract else compare_occupancy_grid
        metrics = compare(
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

    def _probe_finalize_callback(self, request, response):
        """End an explicit bounded adapter diagnostic, always as incomplete."""
        self.finalize("adapter_probe_shutdown")
        response.success = True
        response.message = "Incomplete adapter probe diagnostic saved; no task success credit"
        return response

    def _reward_correct_free_mask(self, grid=None):
        grid = self.latest_map if grid is None else grid
        if grid is None:
            return np.zeros(self.truth.occupied.shape, dtype=bool)
        info = grid.info
        sampled = sample_contract_occupancy_grid(
            self.truth, grid.data, info.width, info.height, info.resolution,
            (info.origin.position.x, info.origin.position.y),
            _yaw_from_quaternion(info.origin.orientation),
        )
        return ((sampled >= 0) & (sampled < 50)
                & ~self.truth.occupied & self.truth.roi_mask)

    def _reward_event_callback(self, message):
        try:
            event = json.loads(message.data)
            if event["epoch"] != self.episode_id or self.start_sim_time is None:
                return
            stamp = event["stamp"]
            if isinstance(stamp, bool) or not math.isfinite(stamp) \
                    or stamp < self.start_sim_time:
                return
            kind, payload = event["kind"], event["payload"]
            if kind == "action_rejected":
                self.reward_events.append((float(stamp), "rejected_actions"))
            elif (kind == "protocol" and payload.get("type") == "cancel_goal"
                  and payload.get("reason") == "switch"):
                identity = payload["goal_id"]
                if identity not in self.reward_switch_goal_ids:
                    self.reward_switch_goal_ids.add(identity)
                    self.reward_events.append((float(stamp), "goal_switches"))
        except (ValueError, TypeError, KeyError):
            self.get_logger().error("Invalid training reward event")

    def _publish_reward_response(self, response):
        self.reward_response_publisher.publish(String(data=json.dumps(
            response, sort_keys=True, allow_nan=False,
        )))

    def _reward_map_watermark(self, record=None):
        if record is None:
            record = next((entry for entry in reversed(self.reward_map_cache)
                           if entry["message"] is self.latest_map), None)
        grid = self.latest_map if record is None else record["message"]
        digest = None
        if grid is not None:
            digest = map_digest(grid) if record is None else record["payload_sha256"]
            if digest is None:
                digest = record["payload_sha256"] = map_digest(grid)
        return {
            "missing": grid is None,
            "header_stamp": (None if grid is None else
                             grid.header.stamp.sec + grid.header.stamp.nanosec / 1e9),
            "received_stamp": (self.latest_map_received_sim_time if record is None
                               else record["received_stamp"]),
            "received_sequence": (self.map_message_count if record is None
                                  else record["received_sequence"]),
            "payload_sha256": digest,
            "source_version": None, "source_version_missing": True,
        }

    def _reward_expected_record(self, digest):
        for record in reversed(self.reward_map_cache):
            if self._reward_map_watermark(record)["payload_sha256"] == digest:
                return record
        return None

    def _queue_reward_request(self, sequence, request):
        previous = self.pending_reward_requests.get(sequence)
        if previous is not None and previous["request"] != request:
            raise ValueError("reward_sequence_conflict")
        if len(self.pending_reward_requests) >= 8 and previous is None:
            raise ValueError("future_reward_queue_overflow")
        if previous is None:
            self.pending_reward_requests[sequence] = {
                "request": request, "deadline_wall": time.monotonic() + 5.,
            }

    def _reward_request_callback(self, message):
        request = None
        try:
            request = json.loads(message.data)
            if not isinstance(request, dict) or set(request) - {
                "epoch", "sequence", "step_start", "step_end", "external_truncation",
                "expected_map_sha256",
            }:
                raise ValueError("invalid_reward_request_fields")
            if request["epoch"] != self.episode_id:
                raise ValueError("wrong_reward_epoch")
            sequence = request["sequence"]
            if type(sequence) is not int or sequence < 0:
                raise ValueError("invalid_reward_sequence")
            fingerprint = json.dumps(
                request, allow_nan=False, sort_keys=True, separators=(",", ":"),
            )
            previous = self.reward_requests.get(sequence)
            if previous is not None:
                if previous[0] != fingerprint:
                    raise ValueError("reward_sequence_conflict")
                self._publish_reward_response(previous[1])
                return
            if self.reward_ledger is None:
                raise ValueError("reward_task_not_started")
            requested_end = request["step_end"]
            start = request["step_start"]
            if (isinstance(requested_end, bool) or isinstance(start, bool)
                    or not math.isfinite(requested_end) or not math.isfinite(start)):
                raise ValueError("invalid_reward_step_time")
            if requested_end > self._now() + 1e-8 and not self.finalized:
                self._queue_reward_request(sequence, request)
                return
            expected = request.get("expected_map_sha256")
            if expected is not None and (not isinstance(expected, str)
                                         or not re.fullmatch("[0-9a-f]{64}", expected)):
                raise ValueError("invalid_expected_map_sha256")
            watermark = self._reward_map_watermark()
            expected_record = self._reward_expected_record(expected) if expected else None
            if sequence == 0:
                if self.reward_reset_bound or self.reward_ledger.last_sequence:
                    raise ValueError("reward_reset_already_bound")
                if (self.finalized or request.get("external_truncation")
                        or not math.isclose(start, self.start_sim_time, rel_tol=0., abs_tol=1e-8)
                        or not math.isclose(requested_end, self.start_sim_time,
                                            rel_tol=0., abs_tol=1e-8)):
                    raise ValueError("invalid_reward_reset_binding_time")
                if expected is None:
                    raise ValueError("reward_reset_requires_expected_map_sha256")
                if expected_record is None:
                    self._queue_reward_request(sequence, request)
                    return
                if expected_record["received_stamp"] > requested_end + 1e-8:
                    raise ValueError("reward_reset_map_is_from_the_future")
                self.reward_ledger = RewardLedger(
                    self.episode_id, self.start_sim_time,
                    ~self.truth.occupied & self.truth.roi_mask,
                    self._reward_correct_free_mask(expected_record["message"]),
                )
                self.reward_reset_bound = True
                response = {
                    "schema": "mr3-reward-v1", "kind": "reward_reset_binding",
                    "epoch": self.episode_id, "sequence": 0, "reward": 0.,
                    "terminated": False, "truncated": False, "reason": None,
                    "step_start": start, "effective_step_end": requested_end,
                    "delta_sim_time": 0., "reset_bound": True,
                    "map_watermark": self._reward_map_watermark(expected_record),
                    "initial_correct_free_cells": self.reward_ledger.initial_correct_count,
                }
                self.reward_requests[0] = (fingerprint, response)
                self._publish_reward_response(response)
                self.reward_ready_publisher.publish(String(data=json.dumps({
                    "schema": "mr3-reward-ready-v1", "epoch": self.episode_id,
                    "start_sim_time": self.start_sim_time, "reset_bound": True,
                    "initial_map_payload_sha256": expected,
                }, sort_keys=True)))
                return
            if not self.reward_reset_bound:
                raise ValueError("reward_reset_not_bound")
            self._timer_callback()  # Apply unchanged task gates at this clock watermark.
            if (not self.finalized and expected is not None
                    and expected != watermark["payload_sha256"]):
                if expected_record is not None:
                    raise ValueError("reward_expected_map_is_older_than_current_map")
                self._queue_reward_request(sequence, request)
                return
            if self.finalized:
                end = self.final_result["end_sim_time_sec"]
                if requested_end < end - 1e-8:
                    raise ValueError("reward_request_precedes_frozen_terminal_map")
                terminal_reason = self.final_result["termination_reason"]
                collisions = self.final_result["collision_events"]
            else:
                end = self._now()
                if not math.isclose(requested_end, end, rel_tol=0., abs_tol=1e-8):
                    raise ValueError("reward_request_is_not_current_simulation_watermark")
                terminal_reason = None
                collisions = self.contact_monitor.summary(end)["event_count"]
            switches = sum(stamp <= end and kind == "goal_switches"
                           for stamp, kind in self.reward_events)
            rejects = sum(stamp <= end and kind == "rejected_actions"
                          for stamp, kind in self.reward_events)
            response = self.reward_ledger.advance(
                epoch=self.episode_id, sequence=sequence, step_start=start, step_end=end,
                current_correct_free_mask=self._reward_correct_free_mask(),
                collision_events=int(collisions), goal_switches=switches,
                rejected_actions=rejects, terminal_reason=terminal_reason,
                external_truncation=request.get("external_truncation"),
            )
            response["requested_step_end"] = float(requested_end)
            response["map_watermark"] = watermark
            response["expected_actor_map_sha256"] = expected
            response["expected_map_paired"] = (
                expected is not None and expected == watermark["payload_sha256"]
            )
            response["map_pairing_scope"] = (
                "terminal_evaluator_frozen_before_drain" if self.finalized else
                "current_actor_map_paired" if expected is not None else
                "legacy_unpaired_reward_request"
            )
            metrics = self._map_metrics()
            response["metrics"] = {key: metrics.get(key) for key in (
                "correct_free_coverage_ratio", "known_coverage_ratio", "observed_accuracy",
                "occupied_iou", "false_free_ratio",
            )}
            response["metrics"].update({
                "map_quality_pass": mr3_quality_pass(metrics, self.task_contract.data["quality"]),
                "robot_participation_pass": mr3_participation_pass(
                    self.path_lengths, self.goal_ids, self.task_contract.data["participation"],
                ),
                "navigation_protocol_closed": self.navigation_protocol_closed,
            })
            if response["truncated"]:
                self.training_external_cut = end
            if response["terminated"] or response["truncated"]:
                self.training_ack_deadline_wall = (
                    time.monotonic() + self.training_ack_wall_guard_sec
                )
            self.reward_requests[sequence] = (fingerprint, response)
            self._publish_reward_response(response)
        except (ValueError, TypeError, KeyError) as error:
            self._publish_reward_response({
                "epoch": self.episode_id,
                "sequence": request.get("sequence") if isinstance(request, dict) else None,
                "error": str(error),
            })

    def _drain_reward_requests(self):
        now = self._now()
        for sequence, pending in sorted(tuple(self.pending_reward_requests.items())):
            request = pending["request"]
            if time.monotonic() >= pending["deadline_wall"]:
                del self.pending_reward_requests[sequence]
                self._publish_reward_response({
                    "epoch": self.episode_id, "sequence": sequence,
                    "error": "reward_map_or_clock_watermark_wall_timeout",
                })
                continue
            if self.finalized or request["step_end"] <= now + 1e-8:
                del self.pending_reward_requests[sequence]
                self._reward_request_callback(String(data=json.dumps(request)))
                if sequence in self.pending_reward_requests:
                    self.pending_reward_requests[sequence]["deadline_wall"] = (
                        pending["deadline_wall"]
                    )

    def _training_finalize_callback(self, message):
        request = None
        try:
            request = json.loads(message.data)
            if request["epoch"] != self.episode_id:
                raise ValueError("wrong_reward_epoch")
            sequence = request["ack_sequence"]
            if type(sequence) is not int or self.reward_ledger is None \
                    or not self.reward_ledger.sealed \
                    or sequence != self.reward_ledger.last_sequence:
                raise ValueError("invalid_training_finalize_sequence")
            response = self.reward_requests[sequence][1]
            reason = "external_truncation" if response["truncated"] else "task_terminal"
            if request["reason"] != reason:
                raise ValueError("invalid_training_finalize_reason")
            if not self.finalized:
                if not self.navigation_protocol_closed:
                    self.pending_training_finalize = request
                    return
                self.finalize("training_external_truncation")
            self.training_acknowledged = True
            self._publish_reward_response({
                "epoch": self.episode_id, "ack_sequence": sequence,
                "kind": "training_finalize_ack", "reason": reason,
            })
        except (ValueError, TypeError, KeyError) as error:
            self._publish_reward_response({
                "epoch": self.episode_id, "kind": "training_finalize_error", "error": str(error),
            })

    def training_exit_ready(self):
        """Keep terminal RPC available until worker ACK, with an independent wall guard."""
        if self.training_reward_enabled:
            if getattr(self, "training_terminal_probe", False):
                self._poll_diagnostic_failure()
            # The worker can pause on a 20ms boundary before the 100ms task
            # timer is due. DDS may deliver a release/stop ACK before this
            # process receives its real /clock watermark; replay only those
            # messages whose unchanged source time has now actually arrived.
            now = self._now()
            pending_ack = getattr(self, "pending_stop_ack", None)
            if not self.finalized and pending_ack is not None and (
                    json.loads(pending_ack.data)["stop_sim_time_sec"] <= now):
                self.pending_stop_ack = None
                self._stopped_callback(pending_ack)
            pending_release = getattr(self, "pending_release", None)
            if not self.finalized and pending_release is not None and (
                    pending_release.stamp.sec + pending_release.stamp.nanosec / 1e9 <= now):
                self.pending_release = None
                self._release_callback(pending_release)
            self._drain_reward_requests()
        if (self.training_reward_enabled and not self.training_acknowledged
                and self.training_ack_deadline_wall is not None
                and time.monotonic() >= self.training_ack_deadline_wall):
            raise RuntimeError("Training evaluator finalization ACK exceeded its wall guard")
        if not self.finalized:
            return False
        if not self.training_reward_enabled or self.training_acknowledged:
            return True
        if self.training_ack_deadline_wall is None:
            self.training_ack_deadline_wall = time.monotonic() + self.training_ack_wall_guard_sec
        return False

    def publish_task_terminal_notice(self):
        """Publish only the frozen scalar task terminal, independent of file I/O."""
        if (not getattr(self, "training_reward_enabled", False) or not self.finalized
                or self.start_sim_time is None or self.task_terminal_notice_published
                or self.training_external_cut is not None):
            return
        result = self.final_result
        reason = result["termination_reason"]
        if reason not in TASK_FAILURE_REASONS and reason != "coverage_reached":
            return
        self.task_terminal_publisher.publish(String(data=json.dumps({
            "epoch": self.episode_id, "end_sim_time_sec": result["end_sim_time_sec"],
            "termination_reason": reason,
        }, sort_keys=True, allow_nan=False)))
        self.task_terminal_notice_published = True

    def finalize(self, termination_reason):
        if self.finalized:
            return
        self.finalized = True
        end_time = self._now()
        if self.start_sim_time is None:
            if termination_reason == "shutdown":
                termination_reason = "no_data"
            elapsed = 0.0
        else:
            elapsed = max(0.0, elapsed_ns(self.start_sim_time, end_time) / 1e9)
        if self.task_contract and self.start_sim_time is not None and elapsed >= self.max_duration:
            termination_reason = "timeout"
        contact_summary = self.contact_monitor.summary(end_time) if self.task_contract else None
        if contact_summary:
            for name in self.robot_names:
                self.collision_events[name] = contact_summary["robots"][name]["event_count"]
                self.collision_duration[name] = contact_summary["robots"][name]["duration_sec"]
                self.collision_messages[name] = sum(
                    row["message_count"] for row in contact_summary["components"][name].values()
                )
        monitoring_active = (
            contact_summary["fresh"] and not contact_summary["ever_unhealthy"]
            if contact_summary else all(count > 0 for count in self.collision_messages.values())
        )
        map_metrics = self._map_metrics()
        if termination_reason == "coverage_reached":
            if self.task_contract:
                termination_reason = self._mr3_termination_reason(elapsed, contact_summary)
                termination_reason = termination_reason or "coverage_not_reached"
            else:
                termination_reason = evaluation_termination_reason(
                    map_metrics.get("correct_free_coverage_ratio", 0.0),
                    self.coverage_threshold, elapsed, self.max_duration,
                    sum(self.collision_events.values()), monitoring_active,
                    "navigation_failure" if self.control_failure else "",
                ) or "coverage_not_reached"

        robots = {}
        for name in self.robot_names:
            start = self.start_positions.get(name, (None, None))
            end = self.positions.get(name, (None, None))
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
            }

        success = termination_reason == "coverage_reached"
        result = {
            "schema_version": 4 if self.task_contract else 3,
            "episode_id": self.episode_id,
            "world_file": self.world_file,
            "gazebo_seed": self.gazebo_seed,
            "robot_count": self.robot_count,
            "task_phase": "COMPLETE" if success else "EXPLORE",
            "success": success,
            "termination_reason": termination_reason,
            "failure_reason": "" if success else termination_reason,
            "coverage_threshold": self.coverage_threshold,
            "max_duration_sec": self.max_duration,
            "control_failure": self.control_failure,
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
            "trajectory_overlap_ratio": visited_overlap_ratio(self.visited),
            "collision_events": sum(self.collision_events.values()),
            "collision_duration_sec": sum(self.collision_duration.values()),
            "collision_monitoring_active": monitoring_active,
            "nav_goal_count": sum(len(ids) for ids in self.goal_ids.values()),
            "nav_succeeded": sum(self.nav_succeeded.values()),
            "nav_canceled": sum(self.nav_canceled.values()),
            "nav_aborted": sum(self.nav_aborted.values()),
            **map_metrics,
            "robots": robots,
        }
        if self.task_contract:
            info = self.latest_map.info if self.latest_map is not None else None
            legacy = compare_occupancy_grid(
                self.legacy_truth, self.latest_map.data, info.width, info.height,
                info.resolution, (info.origin.position.x, info.origin.position.y),
                _yaw_from_quaternion(info.origin.orientation),
            ) if info is not None else {}
            contract = self.task_contract.data
            result.update({
                "task_contract_id": contract["contract_id"],
                "task_contract_sha256": self.task_contract.sha256,
                "world_sha256": self.truth.world_sha256,
                "task_start_barrier": "controller_release",
                "roi_bounds": contract["roi"]["bounds"],
                "lidar_height_m": self.truth.lidar_height_m,
                "truth_rasterization": contract["truth_rasterization"],
                "map_quality_pass": mr3_quality_pass(map_metrics, contract["quality"]),
                "robot_participation_pass": mr3_participation_pass(
                    self.path_lengths, self.goal_ids, contract["participation"]
                ),
                "collision_monitoring_fresh": monitoring_active,
                "contact_monitor_summary": contact_summary,
                "contact_component_count_per_robot": len(CONTACT_COMPONENTS),
                "contact_subscription_started_sim_time_sec": (
                    self.contact_subscription_started_sim_time_sec
                ),
                "contact_subscription_bootstrap_state": self.contact_subscription_bootstrap_state,
                "contact_clock_overflow_diagnostic": self.contact_clock_overflow_diagnostic,
                "navigation_protocol_closed": self.navigation_protocol_closed,
                "navigation_stop_requested_sim_time_sec": self.stop_requested_sim_time,
                "navigation_stop_acknowledgment": self.stop_acknowledgment,
                "initial_map_metrics": self.initial_map_metrics,
                "legacy_schema3_map_metrics": legacy,
                "legacy_schema3_scope": (
                    "original .2m slice, center sampling, all-box bounds; diagnostic only"
                ),
                "map_contract_failure": self.map_contract_failure,
            })
        self.final_result = result
        self.publish_task_terminal_notice()
        self._write_outputs(result)

    def _write_outputs(self, result):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.episode_id)
        json_path = self.output_dir / f"{safe_id}.json"
        csv_path = self.output_dir / f"{safe_id}.csv"
        row = {key: value for key, value in result.items() if key != "robots"}
        for robot, metrics in result["robots"].items():
            for key, value in metrics.items():
                row[f"{robot}_{key}"] = value
        csv_output = io.StringIO(newline="")
        writer = csv.DictWriter(csv_output, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)
        # Publish complete files without overwriting prior evidence. JSON is
        # linked last so the runner only sees a fully written result pair.
        for path, contents in (
            (csv_path, csv_output.getvalue()),
            (json_path, json.dumps(result, indent=2, sort_keys=True)),
        ):
            temporary = path.with_suffix(path.suffix + ".tmp")
            with temporary.open("x") as output:
                output.write(contents)
            try:
                os.link(temporary, path)
            finally:
                temporary.unlink()
        self.get_logger().info(
            f"Evaluation saved to {json_path} and {csv_path}"
        )


def main(args=None):
    rclpy.init(args=args)
    evaluator = None
    executor = None
    try:
        evaluator = TaskEvaluator()
        executor = SingleThreadedExecutor()
        executor.add_node(evaluator)
        # Context shutdown inside an executor callback can wait for that same
        # callback to finish. Return from it, then close the context here.
        while rclpy.ok():
            if getattr(evaluator, "training_reward_enabled", False):
                if evaluator.training_exit_ready():
                    break
            elif evaluator.finalized:
                break
            executor.spin_once(timeout_sec=0.5)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if evaluator is not None:
                evaluator.finalize("shutdown")
        finally:
            try:
                if executor is not None and not executor.shutdown(timeout_sec=1.0):
                    raise RuntimeError("Task evaluator executor shutdown exceeded one second")
            finally:
                try:
                    if evaluator is not None:
                        evaluator.destroy_node()
                finally:
                    if rclpy.ok():
                        rclpy.shutdown()


if __name__ == "__main__":
    main()
