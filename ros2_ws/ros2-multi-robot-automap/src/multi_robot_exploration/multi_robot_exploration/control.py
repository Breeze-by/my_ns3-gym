from dataclasses import dataclass
import heapq
import math
import os
import subprocess
import threading
import time

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from tf2_msgs.msg import TFMessage


OCCUPIED_THRESHOLD = 50
MIN_FRONTIER_GROUP_SIZE = 6
ROBOT_CLEARANCE_M = 0.45
PATH_CLEARANCE_M = 0.23
VIEWPOINT_SEARCH_RADIUS_M = 0.8
INFORMATION_RADIUS_M = 2.0
MIN_TARGET_SEPARATION_M = 1.2
MAX_TARGET_PATH_M = 12.0
TARGET_HISTORY_SEC = 10.0
BAD_TARGET_SEC = 30.0
NO_PROGRESS_SEC = 30.0


@dataclass(frozen=True)
class Viewpoint:
    group_id: int
    row: int
    column: int
    frontier_row: int
    frontier_column: int
    information_gain: int
    group_size: int


@dataclass(frozen=True)
class Assignment:
    viewpoint: Viewpoint
    x: float
    y: float
    path_distance_m: float
    utility: float


def grid_to_world(row, column, resolution, origin_x, origin_y):
    return (
        (column + 0.5) * resolution + origin_x,
        (row + 0.5) * resolution + origin_y,
    )


def world_to_grid(x, y, resolution, origin_x, origin_y):
    return (
        int(math.floor((y - origin_y) / resolution)),
        int(math.floor((x - origin_x) / resolution)),
    )


def transform_point_2d(x, y, transform):
    """Apply a TransformStamped's planar transform to a point."""
    translation = transform.translation
    rotation = transform.rotation
    yaw = math.atan2(
        2.0 * (rotation.w * rotation.z + rotation.x * rotation.y),
        1.0 - 2.0 * (rotation.y * rotation.y + rotation.z * rotation.z),
    )
    return (
        translation.x + math.cos(yaw) * x - math.sin(yaw) * y,
        translation.y + math.sin(yaw) * x + math.cos(yaw) * y,
    )


def frontier_groups(raw_grid, minimum_size=MIN_FRONTIER_GROUP_SIZE):
    """Return 8-connected free-cell frontiers adjacent to unknown space."""
    free = raw_grid == 0
    unknown = raw_grid < 0
    adjacent_unknown = np.zeros_like(unknown)
    adjacent_unknown[1:] |= unknown[:-1]
    adjacent_unknown[:-1] |= unknown[1:]
    adjacent_unknown[:, 1:] |= unknown[:, :-1]
    adjacent_unknown[:, :-1] |= unknown[:, 1:]
    frontier = free & adjacent_unknown

    groups = []
    seen = np.zeros_like(frontier)
    height, width = frontier.shape
    for start_row, start_column in zip(*np.nonzero(frontier)):
        if seen[start_row, start_column]:
            continue
        stack = [(start_row, start_column)]
        seen[start_row, start_column] = True
        group = []
        while stack:
            row, column = stack.pop()
            group.append((row, column))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    next_row = row + dr
                    next_column = column + dc
                    if not (
                        0 <= next_row < height
                        and 0 <= next_column < width
                    ):
                        continue
                    if (
                        frontier[next_row, next_column]
                        and not seen[next_row, next_column]
                    ):
                        seen[next_row, next_column] = True
                        stack.append((next_row, next_column))
        if len(group) >= minimum_size:
            groups.append(group)
    return sorted(groups, key=len, reverse=True)


def inflated_obstacle_mask(raw_grid, clearance_cells):
    occupied = raw_grid >= OCCUPIED_THRESHOLD
    inflated = occupied.copy()
    height, width = occupied.shape
    for dr in range(-clearance_cells, clearance_cells + 1):
        for dc in range(-clearance_cells, clearance_cells + 1):
            if dr * dr + dc * dc > clearance_cells * clearance_cells:
                continue
            source_r0 = max(0, -dr)
            source_r1 = min(height, height - dr)
            source_c0 = max(0, -dc)
            source_c1 = min(width, width - dc)
            target_r0 = source_r0 + dr
            target_r1 = source_r1 + dr
            target_c0 = source_c0 + dc
            target_c1 = source_c1 + dc
            inflated[target_r0:target_r1, target_c0:target_c1] |= occupied[
                source_r0:source_r1, source_c0:source_c1
            ]
    return inflated


def traversable_grid(raw_grid, resolution, clearance_m=ROBOT_CLEARANCE_M):
    clearance_cells = max(1, math.ceil(clearance_m / resolution))
    return (raw_grid == 0) & ~inflated_obstacle_mask(
        raw_grid, clearance_cells
    )


def _line_cells(start, end):
    """Yield integer grid cells on a Bresenham line."""
    row0, column0 = start
    row1, column1 = end
    delta_column = abs(column1 - column0)
    delta_row = -abs(row1 - row0)
    step_column = 1 if column0 < column1 else -1
    step_row = 1 if row0 < row1 else -1
    error = delta_column + delta_row
    while True:
        yield row0, column0
        if row0 == row1 and column0 == column1:
            break
        doubled_error = 2 * error
        if doubled_error >= delta_row:
            error += delta_row
            column0 += step_column
        if doubled_error <= delta_column:
            error += delta_column
            row0 += step_row


def has_known_line_of_sight(raw_grid, start, end):
    return all(
        raw_grid[row, column] >= 0
        and raw_grid[row, column] < OCCUPIED_THRESHOLD
        for row, column in _line_cells(start, end)
    )


def _integral_image(mask):
    return np.pad(mask.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)


def _box_count(integral, row, column, radius, height, width):
    row0 = max(0, row - radius)
    row1 = min(height, row + radius + 1)
    column0 = max(0, column - radius)
    column1 = min(width, column + radius + 1)
    return int(
        integral[row1, column1]
        - integral[row0, column1]
        - integral[row1, column0]
        + integral[row0, column0]
    )


def frontier_viewpoints(raw_grid, groups, traversable, resolution, limit=12):
    """Generate safe known-free observation poses for every frontier group."""
    height, width = raw_grid.shape
    search_cells = max(1, math.ceil(VIEWPOINT_SEARCH_RADIUS_M / resolution))
    information_cells = max(1, math.ceil(INFORMATION_RADIUS_M / resolution))
    separation_cells = max(
        3, math.ceil(MIN_TARGET_SEPARATION_M / resolution)
    )
    unknown_integral = _integral_image(raw_grid < 0)
    viewpoints = {}

    for group_id, group in enumerate(groups):
        nearby = {}
        for frontier_row, frontier_column in group:
            for row in range(
                max(0, frontier_row - search_cells),
                min(height, frontier_row + search_cells + 1),
            ):
                for column in range(
                    max(0, frontier_column - search_cells),
                    min(width, frontier_column + search_cells + 1),
                ):
                    if not traversable[row, column]:
                        continue
                    distance_squared = (
                        (frontier_row - row) ** 2
                        + (frontier_column - column) ** 2
                    )
                    if distance_squared > search_cells * search_cells:
                        continue
                    previous = nearby.get((row, column))
                    if previous is None or distance_squared < previous[0]:
                        nearby[(row, column)] = (
                            distance_squared,
                            frontier_row,
                            frontier_column,
                        )
        ranked = []
        for (row, column), nearest in nearby.items():
            distance_squared, frontier_row, frontier_column = nearest
            frontier_cell = (frontier_row, frontier_column)
            if not has_known_line_of_sight(
                raw_grid, (row, column), frontier_cell
            ):
                continue
            gain = _box_count(
                unknown_integral,
                row,
                column,
                information_cells,
                height,
                width,
            )
            distance_cells = math.sqrt(distance_squared)
            score = gain - distance_cells
            ranked.append(
                (
                    score,
                    Viewpoint(
                        group_id,
                        row,
                        column,
                        frontier_row,
                        frontier_column,
                        gain,
                        len(group),
                    ),
                )
            )
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = []
        for _, viewpoint in ranked:
            if any(
                math.dist(
                    (viewpoint.row, viewpoint.column),
                    (other.row, other.column),
                )
                < separation_cells
                for other in selected
            ):
                continue
            selected.append(viewpoint)
            if len(selected) == limit:
                break
        if selected:
            viewpoints[group_id] = selected
    return viewpoints


def nearest_traversable(traversable, start, max_radius_cells):
    row, column = start
    height, width = traversable.shape
    if 0 <= row < height and 0 <= column < width and traversable[row, column]:
        return start
    best = None
    best_distance = float("inf")
    for candidate_row in range(
        max(0, row - max_radius_cells), min(height, row + max_radius_cells + 1)
    ):
        for candidate_column in range(
            max(0, column - max_radius_cells),
            min(width, column + max_radius_cells + 1),
        ):
            if not traversable[candidate_row, candidate_column]:
                continue
            distance = math.dist(
                (row, column), (candidate_row, candidate_column)
            )
            if distance < best_distance:
                best_distance = distance
                best = (candidate_row, candidate_column)
    return best


def path_distance_grid(traversable, start):
    """Return an 8-connected Dijkstra distance field in grid cells."""
    distances = np.full(traversable.shape, np.inf)
    if start is None:
        return distances
    distances[start] = 0.0
    queue = [(0.0, start[0], start[1])]
    height, width = traversable.shape
    while queue:
        distance, row, column = heapq.heappop(queue)
        if distance != distances[row, column]:
            continue
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                next_row = row + dr
                next_column = column + dc
                if not (0 <= next_row < height and 0 <= next_column < width):
                    continue
                if not traversable[next_row, next_column]:
                    continue
                step = math.sqrt(2.0) if dr and dc else 1.0
                next_distance = distance + step
                if next_distance < distances[next_row, next_column]:
                    distances[next_row, next_column] = next_distance
                    heapq.heappush(
                        queue, (next_distance, next_row, next_column)
                    )
    return distances


def robot_candidate_assignments(
    raw_grid,
    resolution,
    origin,
    robot_name,
    robot_position,
    excluded_targets=(),
):
    """Return diverse locally reachable viewpoints for every frontier group."""
    groups = frontier_groups(raw_grid)
    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=PATH_CLEARANCE_M
    )
    safe_viewpoints = traversable_grid(
        raw_grid, resolution, clearance_m=ROBOT_CLEARANCE_M
    )
    viewpoints = frontier_viewpoints(
        raw_grid, groups, safe_viewpoints, resolution
    )
    candidates = []
    start = world_to_grid(
        robot_position[0],
        robot_position[1],
        resolution,
        origin[0],
        origin[1],
    )
    start = nearest_traversable(
        traversable, start, max(1, math.ceil(1.0 / resolution))
    )
    distances = path_distance_grid(traversable, start)
    for group_id, group_viewpoints in viewpoints.items():
        for viewpoint in group_viewpoints:
            distance_cells = distances[viewpoint.row, viewpoint.column]
            if not np.isfinite(distance_cells):
                continue
            x, y = grid_to_world(
                viewpoint.row,
                viewpoint.column,
                resolution,
                origin[0],
                origin[1],
            )
            if any(
                math.dist((x, y), target) < MIN_TARGET_SEPARATION_M
                for target in excluded_targets
            ):
                continue
            path_distance_m = float(distance_cells * resolution)
            if path_distance_m > MAX_TARGET_PATH_M:
                continue
            utility = (
                viewpoint.information_gain + viewpoint.group_size
            ) / (1.0 + path_distance_m)
            assignment = Assignment(
                viewpoint, x, y, path_distance_m, utility
            )
            candidates.append(
                (assignment.utility, robot_name, group_id, assignment)
            )
    return candidates, {
        "frontier_groups": len(groups),
        "groups_with_viewpoints": len(viewpoints),
        "candidate_assignments": len(candidates),
    }


def select_distinct_assignments(candidates):
    """Greedily select one spatially distinct target per robot."""
    assignments = {}
    used_targets = []
    for _, robot_name, _, assignment in sorted(
        candidates, reverse=True, key=lambda item: item[0]
    ):
        if robot_name in assignments:
            continue
        if any(
            math.dist((assignment.x, assignment.y), target)
            < MIN_TARGET_SEPARATION_M
            for target in used_targets
        ):
            continue
        assignments[robot_name] = assignment
        used_targets.append((assignment.x, assignment.y))
    return assignments


def coordinate_assignments(
    raw_grid,
    resolution,
    origin,
    robot_positions,
    excluded_targets=(),
):
    """Assign distinct reachable frontier groups on a shared test grid."""
    candidates = []
    diagnostics = None
    for robot_name, position in robot_positions.items():
        robot_candidates, robot_diagnostics = robot_candidate_assignments(
            raw_grid,
            resolution,
            origin,
            robot_name,
            position,
            excluded_targets,
        )
        candidates.extend(robot_candidates)
        diagnostics = robot_diagnostics

    assignments = {}
    used_groups = set()
    used_targets = []
    for _, robot_name, group_id, assignment in sorted(
        candidates, reverse=True, key=lambda item: item[0]
    ):
        if robot_name in assignments or group_id in used_groups:
            continue
        if any(
            math.dist((assignment.x, assignment.y), target)
            < MIN_TARGET_SEPARATION_M
            for target in used_targets
        ):
            continue
        assignments[robot_name] = assignment
        used_groups.add(group_id)
        used_targets.append((assignment.x, assignment.y))
    diagnostics = diagnostics or {
        "frontier_groups": 0,
        "groups_with_viewpoints": 0,
        "candidate_assignments": 0,
    }
    diagnostics["candidate_assignments"] = len(candidates)
    return assignments, diagnostics


class HeadquartersControl(Node):
    def __init__(self):
        super().__init__("headquarters_control")
        self.num_robots = self.declare_parameter("robot_count", 2).value
        self.goal_timeout_sec = self.declare_parameter(
            "goal_timeout_sec", 60.0
        ).value
        self.auto_save_map = self.declare_parameter(
            "auto_save_map", True
        ).value
        self.save_map_interval_sec = self.declare_parameter(
            "save_map_interval_sec", 60.0
        ).value

        self.map_data = None
        self.resolution = None
        self.origin = None
        self.map_width = None
        self.map_height = None
        self.map_known_count = 0
        self.last_no_assignment_log = -float("inf")
        self.last_save_time = time.monotonic()
        self.save_in_progress = False
        self.target_history = []
        self.bad_targets = []

        self.map_sub = self.create_subscription(
            OccupancyGrid, "/merge_map", self.map_callback, 10
        )
        self.robot_positions = {}
        self.map_to_odom = {}
        self.robot_maps = {}
        self.robot_states = {}
        self.robot_nav_clients = {}
        self.goal_handles = {}
        self.goal_started_at = {}
        self.goal_last_progress_at = {}
        self.goal_best_distance = {}
        self.goal_last_position = {}
        self.goal_known_count = {}
        self.goal_targets = {}
        self.cancel_requested = {}
        self.robot_subscriptions = []

        for index in range(self.num_robots):
            robot_name = f"tb{index + 1}"
            self.robot_positions[robot_name] = None
            self.map_to_odom[robot_name] = None
            self.robot_maps[robot_name] = None
            self.robot_states[robot_name] = "idle"
            self.goal_handles[robot_name] = None
            self.goal_started_at[robot_name] = None
            self.goal_last_progress_at[robot_name] = None
            self.goal_best_distance[robot_name] = None
            self.goal_last_position[robot_name] = None
            self.goal_known_count[robot_name] = 0
            self.goal_targets[robot_name] = None
            self.cancel_requested[robot_name] = False
            self.robot_nav_clients[robot_name] = ActionClient(
                self, NavigateToPose, f"/{robot_name}/navigate_to_pose"
            )
            self.robot_subscriptions.append(
                self.create_subscription(
                    Odometry,
                    f"/{robot_name}/odom",
                    lambda msg, name=robot_name: self.robot_odom_callback(
                        msg, name
                    ),
                    10,
                )
            )
            self.robot_subscriptions.append(
                self.create_subscription(
                    TFMessage,
                    f"/{robot_name}/tf",
                    lambda msg, name=robot_name: self.robot_tf_callback(
                        msg, name
                    ),
                    20,
                )
            )
            self.robot_subscriptions.append(
                self.create_subscription(
                    OccupancyGrid,
                    f"/{robot_name}/map",
                    lambda msg, name=robot_name: self.robot_map_callback(
                        msg, name
                    ),
                    10,
                )
            )

        self.assignment_timer = self.create_timer(2.0, self.assign_idle_robots)
        self.goal_timeout_timer = self.create_timer(
            1.0, self.cancel_stalled_goals
        )
        self.get_logger().info(
            "Central cooperative frontier coordinator initialized."
        )

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def map_callback(self, msg):
        self.map_data = np.asarray(msg.data, dtype=np.int16).reshape(
            msg.info.height, msg.info.width
        )
        self.resolution = msg.info.resolution
        self.origin = (
            msg.info.origin.position.x,
            msg.info.origin.position.y,
        )
        self.map_width = msg.info.width
        self.map_height = msg.info.height
        self.map_known_count = int(np.count_nonzero(self.map_data >= 0))

    def robot_odom_callback(self, msg, robot_name):
        transform = self.map_to_odom[robot_name]
        if transform is None:
            return
        odom_position = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
        )
        position = transform_point_2d(*odom_position, transform)
        self.robot_positions[robot_name] = position
        last_position = self.goal_last_position[robot_name]
        if (
            self.robot_states[robot_name] == "active"
            and last_position is not None
            and math.dist(position, last_position) >= 0.1
        ):
            self.goal_last_position[robot_name] = position
            self.goal_last_progress_at[robot_name] = self.now()

    def robot_tf_callback(self, msg, robot_name):
        for stamped_transform in msg.transforms:
            parent = stamped_transform.header.frame_id.lstrip("/")
            child = stamped_transform.child_frame_id.lstrip("/")
            if parent.endswith("map") and child.endswith("odom"):
                self.map_to_odom[robot_name] = stamped_transform.transform

    def robot_map_callback(self, msg, robot_name):
        self.robot_maps[robot_name] = {
            "data": np.asarray(msg.data, dtype=np.int16).reshape(
                msg.info.height, msg.info.width
            ),
            "resolution": msg.info.resolution,
            "origin": (
                msg.info.origin.position.x,
                msg.info.origin.position.y,
            ),
        }

    def active_exclusions(self):
        now = self.now()
        self.target_history = [
            item for item in self.target_history if item[2] > now
        ]
        self.bad_targets = [item for item in self.bad_targets if item[2] > now]
        exclusions = [(item[0], item[1]) for item in self.target_history]
        exclusions.extend((item[0], item[1]) for item in self.bad_targets)
        exclusions.extend(
            (target.x, target.y)
            for target in self.goal_targets.values()
            if target is not None
        )
        return exclusions

    def assign_idle_robots(self):
        if self.map_data is None:
            return
        idle_positions = {
            name: self.robot_positions[name]
            for name, state in self.robot_states.items()
            if (
                state == "idle"
                and self.robot_positions[name] is not None
                and self.robot_maps[name] is not None
            )
        }
        if not idle_positions:
            return
        exclusions = self.active_exclusions()
        candidates = []
        diagnostics = {
            "frontier_groups": 0,
            "groups_with_viewpoints": 0,
            "candidate_assignments": 0,
        }
        global_unknown = _integral_image(self.map_data < 0)
        global_radius = max(
            1, math.ceil(INFORMATION_RADIUS_M / self.resolution)
        )
        for robot_name, position in idle_positions.items():
            robot_map = self.robot_maps[robot_name]
            robot_candidates, robot_diagnostics = robot_candidate_assignments(
                robot_map["data"],
                robot_map["resolution"],
                robot_map["origin"],
                robot_name,
                position,
                exclusions,
            )
            diagnostics["frontier_groups"] += robot_diagnostics[
                "frontier_groups"
            ]
            diagnostics["groups_with_viewpoints"] += robot_diagnostics[
                "groups_with_viewpoints"
            ]
            for _, _, group_id, assignment in robot_candidates:
                row, column = world_to_grid(
                    assignment.x,
                    assignment.y,
                    self.resolution,
                    self.origin[0],
                    self.origin[1],
                )
                if not (
                    0 <= row < self.map_height
                    and 0 <= column < self.map_width
                ):
                    continue
                global_gain = _box_count(
                    global_unknown,
                    row,
                    column,
                    global_radius,
                    self.map_height,
                    self.map_width,
                )
                utility = (
                    global_gain + assignment.viewpoint.group_size
                ) / (1.0 + assignment.path_distance_m)
                coordinated = Assignment(
                    assignment.viewpoint,
                    assignment.x,
                    assignment.y,
                    assignment.path_distance_m,
                    utility,
                )
                candidates.append(
                    (utility, robot_name, group_id, coordinated)
                )
        diagnostics["candidate_assignments"] = len(candidates)
        assignments = select_distinct_assignments(candidates)
        if not assignments:
            now = self.now()
            if now - self.last_no_assignment_log >= 10.0:
                self.get_logger().warn(
                    "No cooperative frontier assignment: "
                    f"{diagnostics}"
                )
                self.last_no_assignment_log = now
            return
        for robot_name, assignment in assignments.items():
            self.robot_states[robot_name] = "active"
            self.goal_targets[robot_name] = assignment
            self.get_logger().info(
                f"Assigned {robot_name} to group "
                f"{assignment.viewpoint.group_id} at "
                f"({assignment.x:.2f}, {assignment.y:.2f}); "
                f"path={assignment.path_distance_m:.2f} m, "
                f"gain={assignment.viewpoint.information_gain}, "
                f"utility={assignment.utility:.1f}"
            )
            self.send_goal(robot_name, assignment)

    def send_goal(self, robot_name, assignment):
        client = self.robot_nav_clients[robot_name]
        if not client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn(
                f"Navigation action server for {robot_name} is unavailable."
            )
            self.robot_states[robot_name] = "idle"
            self.goal_targets[robot_name] = None
            return

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = assignment.x
        goal.pose.pose.position.y = assignment.y
        goal.pose.pose.orientation.w = 1.0
        future = client.send_goal_async(
            goal,
            feedback_callback=lambda feedback, name=robot_name: (
                self.feedback_callback(name, feedback)
            ),
        )
        future.add_done_callback(
            lambda result, name=robot_name: self.goal_response_callback(
                name, result
            )
        )

    def goal_response_callback(self, robot_name, future):
        assignment = self.goal_targets[robot_name]
        try:
            goal_handle = future.result()
        except Exception as error:
            self.get_logger().error(
                f"{robot_name} goal request failed: {error}"
            )
            self.finish_goal(robot_name, success=False)
            return
        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warn(f"{robot_name} rejected its frontier goal.")
            self.finish_goal(robot_name, success=False, blacklist=False)
            return

        now = self.now()
        self.goal_handles[robot_name] = goal_handle
        self.goal_started_at[robot_name] = now
        self.goal_last_progress_at[robot_name] = now
        self.goal_best_distance[robot_name] = None
        self.goal_last_position[robot_name] = self.robot_positions[robot_name]
        self.goal_known_count[robot_name] = self.map_known_count
        self.cancel_requested[robot_name] = False
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result, name=robot_name, target=assignment: (
                self.goal_result_callback(name, target, result)
            )
        )

    def feedback_callback(self, robot_name, feedback_msg):
        distance = float(feedback_msg.feedback.distance_remaining)
        best = self.goal_best_distance[robot_name]
        if best is None or distance < best - 0.1:
            self.goal_best_distance[robot_name] = distance
            self.goal_last_progress_at[robot_name] = self.now()

    def goal_result_callback(self, robot_name, assignment, future):
        try:
            result = future.result()
            success = result.status == GoalStatus.STATUS_SUCCEEDED
            status = result.status
        except Exception as error:
            success = False
            status = f"exception: {error}"
        coverage_gain = (
            self.map_known_count - self.goal_known_count[robot_name]
        )
        if success:
            self.get_logger().info(
                f"{robot_name} reached cooperative frontier goal; "
                f"known-cell delta={coverage_gain}."
            )
        else:
            self.get_logger().warn(
                f"{robot_name} failed cooperative frontier goal with "
                f"status {status}."
            )
        self.finish_goal(robot_name, success=success)

    def finish_goal(self, robot_name, success, blacklist=True):
        assignment = self.goal_targets[robot_name]
        if assignment is not None:
            expiry = self.now() + (
                TARGET_HISTORY_SEC if success else BAD_TARGET_SEC
            )
            entry = (assignment.x, assignment.y, expiry)
            if success:
                self.target_history.append(entry)
            elif blacklist:
                self.bad_targets.append(entry)
        self.goal_handles[robot_name] = None
        self.goal_started_at[robot_name] = None
        self.goal_last_progress_at[robot_name] = None
        self.goal_best_distance[robot_name] = None
        self.goal_last_position[robot_name] = None
        self.goal_known_count[robot_name] = 0
        self.goal_targets[robot_name] = None
        self.cancel_requested[robot_name] = False
        self.robot_states[robot_name] = "idle"
        self.check_exploration_completion()

    def cancel_stalled_goals(self):
        now = self.now()
        for robot_name, goal_handle in self.goal_handles.items():
            started_at = self.goal_started_at[robot_name]
            last_progress = self.goal_last_progress_at[robot_name]
            if goal_handle is None or started_at is None:
                continue
            timed_out = now - started_at >= self.goal_timeout_sec
            stalled = (
                last_progress is not None
                and now - started_at >= 10.0
                and now - last_progress >= NO_PROGRESS_SEC
            )
            if not (timed_out or stalled) or self.cancel_requested[robot_name]:
                continue
            reason = "timeout" if timed_out else "no progress"
            self.get_logger().warn(
                f"Canceling {robot_name} goal after {reason}."
            )
            self.cancel_requested[robot_name] = True
            goal_handle.cancel_goal_async()

    def check_exploration_completion(self):
        now = time.monotonic()
        if (
            self.auto_save_map
            and self.map_data is not None
            and all(state == "idle" for state in self.robot_states.values())
            and now - self.last_save_time >= self.save_map_interval_sec
            and not self.save_in_progress
        ):
            self.save_in_progress = True
            self.last_save_time = now
            threading.Thread(target=self.save_map, daemon=True).start()

    def save_map(self):
        map_name = (
            "multi_robot_autonomous_mapping_of_"
            f"{self.num_robots}_robots"
        )
        try:
            subprocess.run(
                [
                    "ros2",
                    "run",
                    "nav2_map_server",
                    "map_saver_cli",
                    "-t",
                    "/merge_map",
                    "-f",
                    os.path.join(
                        get_package_share_directory("multi_robot"),
                        "../../../../src/saved_map/" + map_name,
                    ),
                    "--ros-args",
                    "-p",
                    "map_subscribe_transient_local:=true",
                ],
                check=True,
            )
        except (subprocess.CalledProcessError, OSError) as error:
            self.get_logger().error(f"Failed to save merged map: {error}")
        finally:
            self.save_in_progress = False


def main(args=None):
    rclpy.init(args=args)
    control = HeadquartersControl()
    try:
        rclpy.spin(control)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        control.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
