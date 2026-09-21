from dataclasses import dataclass
import json
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
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage


OCCUPIED_THRESHOLD = 50
MIN_FRONTIER_GROUP_SIZE = 6
ROBOT_CLEARANCE_M = 0.45
PATH_CLEARANCE_M = 0.23
VIEWPOINT_SEARCH_RADIUS_M = 0.8
INFORMATION_RADIUS_M = 2.0
MIN_TARGET_SEPARATION_M = 1.2
MAX_TARGET_PATH_M = 12.0
MAX_NAVIGATION_LEG_M = 5.0
TARGET_HISTORY_SEC = 10.0
BAD_TARGET_SEC = 30.0
NO_PROGRESS_SEC = 10.0
USEFUL_TRAVEL_M = 0.75
PATH_COST_EXPONENT = 1.5
GOAL_REPLAN_SEC = 3.0
MIN_REMAINING_GAIN = 200
MIN_REMAINING_GAIN_FRACTION = 0.2
RALLY_CLEARANCE_M = 0.45
RALLY_PATH_CLEARANCE_M = 0.35
RALLY_MIN_SEPARATION_M = 0.8
RALLY_PREFERRED_SEPARATION_M = 1.2
RALLY_DYNAMIC_CLEARANCE_M = 0.6
RALLY_POSITION_TOLERANCE_M = 0.35
RALLY_LINEAR_TOLERANCE_MPS = 0.05
RALLY_ANGULAR_TOLERANCE_RADPS = 0.10
RALLY_HOLD_SEC = 5.0
RALLY_ASSIGNMENT_WAIT_SEC = 10.0
RALLY_MAX_NAVIGATION_LEG_M = 1.5
RALLY_ROUTE_SEPARATION_M = 1.2
RALLY_MAX_CONCURRENT = 2

TASK_TRANSITIONS = {
    "EXPLORE": {"FOUND_UNCONFIRMED", "FOUND", "FAILED"},
    "FOUND_UNCONFIRMED": {"EXPLORE", "FOUND", "FAILED"},
    "FOUND": {"RALLY", "FAILED"},
    "RALLY": {"COMPLETE", "FAILED"},
    "COMPLETE": set(),
    "FAILED": set(),
}


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
    navigation_x: float
    navigation_y: float


@dataclass(frozen=True)
class RallyPose:
    x: float
    y: float
    yaw: float


def valid_task_transition(current, new):
    return new == current or new in TASK_TRANSITIONS[current]


def unavailable_battery_states(received_at, now, timeout):
    return [
        name
        for name, timestamp in received_at.items()
        if timestamp is None or now - timestamp >= timeout
    ]


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

    labels, count = ndimage.label(
        frontier, structure=np.ones((3, 3), dtype=np.uint8)
    )
    sizes = np.bincount(labels.ravel())
    qualifying = [
        label
        for label in range(1, count + 1)
        if sizes[label] >= minimum_size
    ]
    qualifying.sort(key=lambda label: sizes[label], reverse=True)
    return [np.argwhere(labels == label) for label in qualifying]


def inflated_obstacle_mask(raw_grid, clearance_cells):
    occupied = raw_grid >= OCCUPIED_THRESHOLD
    offsets = np.arange(-clearance_cells, clearance_cells + 1)
    rows, columns = np.meshgrid(offsets, offsets, indexing="ij")
    footprint = rows * rows + columns * columns <= clearance_cells**2
    return ndimage.binary_dilation(occupied, structure=footprint)


def traversable_grid(raw_grid, resolution, clearance_m=ROBOT_CLEARANCE_M):
    clearance_cells = max(1, math.ceil(clearance_m / resolution))
    return (raw_grid == 0) & ~inflated_obstacle_mask(
        raw_grid, clearance_cells
    )


def block_dynamic_positions(traversable, resolution, origin, positions):
    """Return a grid with parked robots represented as safety obstacles."""
    result = traversable.copy()
    radius = max(1, math.ceil(RALLY_DYNAMIC_CLEARANCE_M / resolution))
    for x, y in positions:
        row, column = world_to_grid(
            x, y, resolution, origin[0], origin[1]
        )
        row_start = max(0, row - radius)
        row_stop = min(result.shape[0], row + radius + 1)
        column_start = max(0, column - radius)
        column_stop = min(result.shape[1], column + radius + 1)
        rows, columns = np.ogrid[
            row_start:row_stop, column_start:column_stop
        ]
        window = result[row_start:row_stop, column_start:column_stop]
        window[(rows - row) ** 2 + (columns - column) ** 2 <= radius**2] = False
    return result


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
    if not groups:
        return viewpoints

    frontier_labels = np.zeros(raw_grid.shape, dtype=np.int32)
    for group_id, group in enumerate(groups, start=1):
        frontier_labels[group[:, 0], group[:, 1]] = group_id
    distances, nearest = ndimage.distance_transform_edt(
        frontier_labels == 0, return_indices=True
    )
    nearest_groups = frontier_labels[nearest[0], nearest[1]]
    eligible = (
        traversable
        & (nearest_groups > 0)
        & (distances <= search_cells)
    )
    rows, columns = np.nonzero(eligible)
    if not rows.size:
        return viewpoints

    row0 = np.maximum(0, rows - information_cells)
    row1 = np.minimum(height, rows + information_cells + 1)
    column0 = np.maximum(0, columns - information_cells)
    column1 = np.minimum(width, columns + information_cells + 1)
    gains = (
        unknown_integral[row1, column1]
        - unknown_integral[row0, column1]
        - unknown_integral[row1, column0]
        + unknown_integral[row0, column0]
    )
    scores = gains - distances[rows, columns]
    candidate_groups = nearest_groups[rows, columns]

    for group_id, group in enumerate(groups):
        candidate_indices = np.flatnonzero(candidate_groups == group_id + 1)
        ranked_indices = candidate_indices[
            np.argsort(scores[candidate_indices])[::-1]
        ]
        selected = []
        remaining = ranked_indices
        while remaining.size and len(selected) < limit:
            index = remaining[0]
            row = int(rows[index])
            column = int(columns[index])
            frontier_row = int(nearest[0, row, column])
            frontier_column = int(nearest[1, row, column])
            if not has_known_line_of_sight(
                raw_grid,
                (row, column),
                (frontier_row, frontier_column),
            ):
                remaining = remaining[1:]
                continue
            viewpoint = Viewpoint(
                group_id,
                row,
                column,
                frontier_row,
                frontier_column,
                int(gains[index]),
                len(group),
            )
            selected.append(viewpoint)
            distance_squared = (
                (rows[remaining] - row) ** 2
                + (columns[remaining] - column) ** 2
            )
            remaining = remaining[
                distance_squared >= separation_cells * separation_cells
            ]
        if selected:
            viewpoints[group_id] = selected
    return viewpoints


def exploration_utility(information_gain, group_size, path_distance_m):
    """Prefer useful travel over goals already covered by the current scan."""
    departure = min(1.0, path_distance_m / USEFUL_TRAVEL_M)
    return (
        (information_gain + group_size)
        * departure
        / (1.0 + path_distance_m) ** PATH_COST_EXPONENT
    )


def goal_is_stale(initial_gain, remaining_gain, age_sec):
    if age_sec < GOAL_REPLAN_SEC or initial_gain <= 0:
        return False
    threshold = max(
        MIN_REMAINING_GAIN,
        initial_gain * MIN_REMAINING_GAIN_FRACTION,
    )
    return remaining_gain <= threshold


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


def path_distance_grid(traversable, start, return_predecessors=False):
    """Return an 8-connected Dijkstra distance field in grid cells."""
    height, width = traversable.shape
    if start is None:
        return np.full(traversable.shape, np.inf)

    cell_ids = np.arange(height * width).reshape(height, width)
    sources = []
    targets = []
    weights = []
    for dr, dc, weight in (
        (0, 1, 1.0),
        (1, 0, 1.0),
        (1, 1, math.sqrt(2.0)),
        (1, -1, math.sqrt(2.0)),
    ):
        source_r0 = max(0, -dr)
        source_r1 = min(height, height - dr)
        source_c0 = max(0, -dc)
        source_c1 = min(width, width - dc)
        target_r0 = source_r0 + dr
        target_r1 = source_r1 + dr
        target_c0 = source_c0 + dc
        target_c1 = source_c1 + dc
        connected = (
            traversable[source_r0:source_r1, source_c0:source_c1]
            & traversable[target_r0:target_r1, target_c0:target_c1]
        )
        sources.append(
            cell_ids[source_r0:source_r1, source_c0:source_c1][connected]
        )
        targets.append(
            cell_ids[target_r0:target_r1, target_c0:target_c1][connected]
        )
        weights.append(np.full(np.count_nonzero(connected), weight))

    graph = coo_matrix(
        (
            np.concatenate(weights),
            (np.concatenate(sources), np.concatenate(targets)),
        ),
        shape=(height * width, height * width),
    ).tocsr()
    start_id = int(cell_ids[start])
    result = dijkstra(
        graph,
        directed=False,
        indices=start_id,
        return_predecessors=return_predecessors,
    )
    if return_predecessors:
        distances, predecessors = result
        return (
            distances.reshape(height, width),
            predecessors.reshape(height, width),
        )
    return result.reshape(height, width)


def path_waypoint_route(traversable, start, target, max_distance_cells):
    """Return a limited waypoint and its shortest grid path from start."""
    distances, predecessors = path_distance_grid(
        traversable, start, return_predecessors=True
    )
    if not np.isfinite(distances[target]):
        return None, ()
    width = traversable.shape[1]
    current = target[0] * width + target[1]
    while distances.flat[current] > max_distance_cells:
        predecessor = int(predecessors.flat[current])
        if predecessor < 0 or predecessor == current:
            return None, ()
        current = predecessor
    waypoint = divmod(current, width)
    route = []
    start_id = start[0] * width + start[1]
    while current != start_id:
        route.append(divmod(current, width))
        current = int(predecessors.flat[current])
        if current < 0:
            return None, ()
    route.append(start)
    route.reverse()
    return waypoint, tuple(route)


def path_waypoint(traversable, start, target, max_distance_cells):
    """Return the farthest path cell within one reliable navigation leg."""
    return path_waypoint_route(
        traversable, start, target, max_distance_cells
    )[0]


def stage_navigation_leg(
    assignment, raw_grid, resolution, origin, robot_position
):
    if assignment.path_distance_m <= MAX_NAVIGATION_LEG_M:
        return assignment
    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=PATH_CLEARANCE_M
    )
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
    target = world_to_grid(
        assignment.x,
        assignment.y,
        resolution,
        origin[0],
        origin[1],
    )
    if start is None:
        return assignment
    waypoint = path_waypoint(
        traversable,
        start,
        target,
        MAX_NAVIGATION_LEG_M / resolution,
    )
    if waypoint is None:
        return assignment
    navigation_x, navigation_y = grid_to_world(
        waypoint[0], waypoint[1], resolution, origin[0], origin[1]
    )
    return Assignment(
        assignment.viewpoint,
        assignment.x,
        assignment.y,
        assignment.path_distance_m,
        assignment.utility,
        navigation_x,
        navigation_y,
    )


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
            utility = exploration_utility(
                viewpoint.information_gain,
                viewpoint.group_size,
                path_distance_m,
            )
            assignment = Assignment(
                viewpoint, x, y, path_distance_m, utility, x, y
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


def rally_pose_candidates(raw_grid, resolution, origin, target):
    """Return known-free, target-facing poses around the target."""
    safe = traversable_grid(
        raw_grid, resolution, clearance_m=RALLY_CLEARANCE_M
    )
    target_cell = world_to_grid(
        target[0], target[1], resolution, origin[0], origin[1]
    )
    height, width = raw_grid.shape
    if not (
        0 <= target_cell[0] < height and 0 <= target_cell[1] < width
    ):
        return []

    candidates = []
    seen_cells = set()
    for index in range(24):
        for radius in (1.0, 1.8, 2.6):
            angle = 2.0 * math.pi * index / 24
            x = target[0] + radius * math.cos(angle)
            y = target[1] + radius * math.sin(angle)
            cell = world_to_grid(
                x, y, resolution, origin[0], origin[1]
            )
            if cell in seen_cells:
                continue
            seen_cells.add(cell)
            row, column = cell
            if not (
                0 <= row < height
                and 0 <= column < width
                and safe[row, column]
                and has_known_line_of_sight(raw_grid, cell, target_cell)
            ):
                continue
            pose_x, pose_y = grid_to_world(
                row, column, resolution, origin[0], origin[1]
            )
            candidates.append(
                RallyPose(
                    pose_x,
                    pose_y,
                    math.atan2(target[1] - pose_y, target[0] - pose_x),
                )
            )
    return candidates


def assign_rally_poses(raw_grid, resolution, origin, robot_positions, target):
    """Minimize total reachable path length with distinct rally poses."""
    names = sorted(robot_positions)
    candidates = rally_pose_candidates(
        raw_grid, resolution, origin, target
    )
    if len(candidates) < len(names):
        return {}

    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=RALLY_PATH_CLEARANCE_M
    )
    options = {}
    for name in names:
        position = robot_positions[name]
        start = world_to_grid(
            position[0], position[1], resolution, origin[0], origin[1]
        )
        start = nearest_traversable(
            traversable, start, max(1, math.ceil(1.0 / resolution))
        )
        distances = path_distance_grid(traversable, start)
        reachable = []
        for index, pose in enumerate(candidates):
            row, column = world_to_grid(
                pose.x, pose.y, resolution, origin[0], origin[1]
            )
            distance = distances[row, column]
            if np.isfinite(distance):
                reachable.append((float(distance), index))
        reachable.sort()
        if not reachable:
            return {}
        options[name] = reachable

    search_order = sorted(names, key=lambda name: len(options[name]))
    best = {}
    best_score = (float("inf"), float("inf"))

    def search(assignments, used_indices, separation_penalty, cost):
        nonlocal best, best_score
        if (separation_penalty, cost) >= best_score:
            return
        if len(assignments) == len(search_order):
            best = assignments.copy()
            best_score = (separation_penalty, cost)
            return
        name = search_order[len(assignments)]
        for distance, candidate_index in options[name]:
            if candidate_index in used_indices:
                continue
            pose = candidates[candidate_index]
            if any(
                math.dist((pose.x, pose.y), (other.x, other.y))
                < RALLY_MIN_SEPARATION_M
                for other in assignments.values()
            ):
                continue
            assignments[name] = pose
            used_indices.add(candidate_index)
            added_penalty = sum(
                max(
                    0.0,
                    RALLY_PREFERRED_SEPARATION_M
                    - math.dist((pose.x, pose.y), (other.x, other.y)),
                )
                for other_name, other in assignments.items()
                if other_name != name
            )
            search(
                assignments,
                used_indices,
                separation_penalty + added_penalty,
                cost + distance,
            )
            used_indices.remove(candidate_index)
            del assignments[name]

    search({}, set(), 0.0, 0.0)
    if not best:
        return {}
    return {name: best[name] for name in names}


def rally_survey_pose(raw_grid, resolution, origin, robot_position, target):
    """Choose a known, reachable pose that moves the detector toward target."""
    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=RALLY_PATH_CLEARANCE_M
    )
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
    if start is None:
        return None
    distances = path_distance_grid(traversable, start)
    target_cell = world_to_grid(
        target[0], target[1], resolution, origin[0], origin[1]
    )
    height, width = raw_grid.shape
    if not (
        0 <= target_cell[0] < height and 0 <= target_cell[1] < width
    ):
        return None

    current_distance = math.dist(robot_position, target)
    candidates = []
    for row, column in np.argwhere(traversable & np.isfinite(distances)):
        x, y = grid_to_world(
            row, column, resolution, origin[0], origin[1]
        )
        target_distance = math.dist((x, y), target)
        if (
            target_distance < 0.7
            or target_distance > current_distance - 0.4
        ):
            continue
        candidates.append((target_distance, distances[row, column], x, y))
    if not candidates:
        return None
    _, _, x, y = min(candidates)
    return RallyPose(x, y, math.atan2(target[1] - y, target[0] - x))


def survey_robot_order(robot_positions, detecting_robot):
    return sorted(
        robot_positions,
        key=lambda name: (name != detecting_robot, name),
    )


def rally_dispatch_order(
    targets, robot_positions, target, priority_robot=None
):
    """Move the detector first, then fill far-side poses safely."""
    center_x = sum(position[0] for position in robot_positions.values()) / len(
        robot_positions
    )
    center_y = sum(position[1] for position in robot_positions.values()) / len(
        robot_positions
    )
    approach_x = target[0] - center_x
    approach_y = target[1] - center_y
    norm = math.hypot(approach_x, approach_y) or 1.0
    approach_x /= norm
    approach_y /= norm
    return sorted(
        targets,
        key=lambda name: (
            name != priority_robot,
            -(
                (targets[name].x - target[0]) * approach_x
                + (targets[name].y - target[1]) * approach_y
            ),
            -math.dist(
                robot_positions[name],
                (targets[name].x, targets[name].y),
            ),
            name,
        ),
    )


def stage_rally_leg(
    pose,
    raw_grid,
    resolution,
    origin,
    robot_position,
    max_distance_m=RALLY_MAX_NAVIGATION_LEG_M,
):
    """Limit a rally action to one reliable map-path leg."""
    return plan_rally_leg(
        pose,
        raw_grid,
        resolution,
        origin,
        robot_position,
        max_distance_m,
    )[0]


def plan_rally_leg(
    pose,
    raw_grid,
    resolution,
    origin,
    robot_position,
    max_distance_m=RALLY_MAX_NAVIGATION_LEG_M,
    blocked_positions=(),
    clearance_m=RALLY_PATH_CLEARANCE_M,
):
    """Return a staged rally pose and the map path reserved for it."""
    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=clearance_m
    )
    traversable = block_dynamic_positions(
        traversable, resolution, origin, blocked_positions
    )
    start = nearest_traversable(
        traversable,
        world_to_grid(
            robot_position[0],
            robot_position[1],
            resolution,
            origin[0],
            origin[1],
        ),
        max(1, math.ceil(1.0 / resolution)),
    )
    target = world_to_grid(
        pose.x, pose.y, resolution, origin[0], origin[1]
    )
    if start is None:
        return pose, (robot_position, (pose.x, pose.y))
    waypoint, route = path_waypoint_route(
        traversable,
        start,
        target,
        max_distance_m / resolution,
    )
    if waypoint is None:
        return pose, (robot_position, (pose.x, pose.y))
    x, y = grid_to_world(
        waypoint[0], waypoint[1], resolution, origin[0], origin[1]
    )
    world_route = tuple(
        grid_to_world(row, column, resolution, origin[0], origin[1])
        for row, column in route
    )
    return (
        RallyPose(x, y, math.atan2(pose.y - y, pose.x - x)),
        world_route,
    )


def routes_conflict(
    first, second, min_separation=RALLY_ROUTE_SEPARATION_M
):
    return any(
        math.dist(first_point, second_point) < min_separation
        for first_point in first
        for second_point in second
    )


def select_nonconflicting_routes(
    routes, order, reserved_routes=(), max_count=None
):
    """Greedily reserve every route that is safe to run concurrently."""
    selected = []
    reservations = list(reserved_routes)
    for name in order:
        if max_count is not None and len(selected) >= max_count:
            break
        route = routes.get(name)
        if route is None or any(
            routes_conflict(route, reserved) for reserved in reservations
        ):
            continue
        selected.append(name)
        reservations.append(route)
    return selected


def robots_that_must_yield(
    positions,
    active_names,
    priority_order,
    min_separation=RALLY_ROUTE_SEPARATION_M,
):
    """Return lower-priority moving robots that became too close."""
    priority = {name: index for index, name in enumerate(priority_order)}
    yielding = set()
    names = [name for name in active_names if positions.get(name) is not None]
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            if math.dist(positions[first], positions[second]) >= min_separation:
                continue
            yielding.add(
                first if priority[first] > priority[second] else second
            )
    return yielding


def robots_stable(
    positions,
    velocities,
    targets,
    position_tolerance=RALLY_POSITION_TOLERANCE_M,
    linear_tolerance=RALLY_LINEAR_TOLERANCE_MPS,
    angular_tolerance=RALLY_ANGULAR_TOLERANCE_RADPS,
):
    return bool(targets) and all(
        name in positions
        and name in velocities
        and math.dist(positions[name], (target.x, target.y))
        <= position_tolerance
        and velocities[name][0] <= linear_tolerance
        and velocities[name][1] <= angular_tolerance
        for name, target in targets.items()
    )


def all_robot_inputs_ready(robot_positions, robot_maps):
    return all(
        robot_positions[name] is not None and robot_maps[name] is not None
        for name in robot_positions
    )


def all_batteries_active(battery_modes):
    return all(mode == "ACTIVE" for mode in battery_modes.values())


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
        self.enable_rally = self.declare_parameter(
            "enable_rally", False
        ).value
        self.enable_battery = self.declare_parameter(
            "enable_battery", False
        ).value
        self.rally_position_tolerance = self.declare_parameter(
            "rally_position_tolerance_m", RALLY_POSITION_TOLERANCE_M
        ).value
        self.rally_linear_tolerance = self.declare_parameter(
            "rally_linear_tolerance_mps", RALLY_LINEAR_TOLERANCE_MPS
        ).value
        self.rally_angular_tolerance = self.declare_parameter(
            "rally_angular_tolerance_radps", RALLY_ANGULAR_TOLERANCE_RADPS
        ).value
        self.rally_hold_sec = self.declare_parameter(
            "rally_hold_sec", RALLY_HOLD_SEC
        ).value
        self.rally_max_retries = self.declare_parameter(
            "rally_max_retries", 2
        ).value
        if (
            self.num_robots < 1
            or self.rally_position_tolerance <= 0
            or self.rally_linear_tolerance < 0
            or self.rally_angular_tolerance < 0
            or self.rally_hold_sec <= 0
            or self.rally_max_retries < 0
        ):
            raise ValueError("invalid robot or rally parameters")

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

        state_qos = QoSProfile(depth=1)
        state_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        state_qos.reliability = ReliabilityPolicy.RELIABLE
        self.task_state_publisher = self.create_publisher(
            String, "/task_state", state_qos
        )
        self.rally_assignment_publisher = self.create_publisher(
            String, "/rally_assignments", state_qos
        )
        self.task_failure_publisher = self.create_publisher(
            String, "/task_failure", state_qos
        )
        self.task_subscriptions = [
            self.create_subscription(
                String,
                "/gateway/received/target_observation",
                self.target_observation_callback,
                state_qos,
            ),
            self.create_subscription(
                String,
                "/gateway/received/target_detection",
                self.target_detection_callback,
                state_qos,
            ),
            self.create_subscription(
                String,
                "/gateway/received/battery_failure",
                self.battery_failure_callback,
                state_qos,
            ),
        ]
        self.task_state = "EXPLORE"
        self.target = None
        self.detecting_robot = None
        self.rally_targets = {}
        self.rally_goal_handles = {}
        self.rally_goal_pending = {}
        self.rally_goal_started_at = {}
        self.rally_leg_routes = {}
        self.rally_yield_requested = {}
        self.rally_battery_preempted = {}
        self.rally_attempts = {}
        self.rally_arrived = {}
        self.rally_dispatch_order = []
        self.rally_hold_started_at = None
        self.rally_prepare_started_at = None
        self.last_rally_dispatch_at = -float("inf")
        self.last_rally_candidate_log = -float("inf")
        self.last_rally_assignment_attempt = -float("inf")
        self.survey_goal_handle = None
        self.survey_goal_pending = False
        self.survey_goal_started_at = None
        self.survey_attempts = 0
        self.survey_robot = None
        self.survey_battery_preempted = False

        self.map_sub = self.create_subscription(
            OccupancyGrid, "/merge_map", self.map_callback, 10
        )
        self.robot_positions = {}
        self.map_to_odom = {}
        self.robot_maps = {}
        self.robot_velocities = {}
        self.robot_states = {}
        self.battery_modes = {}
        self.battery_states = {}
        self.battery_state_received_at = {}
        self.battery_preempted = {}
        self.battery_monitor_started_at = None
        self.robot_nav_clients = {}
        self.goal_handles = {}
        self.goal_started_at = {}
        self.goal_last_progress_at = {}
        self.goal_best_distance = {}
        self.goal_last_position = {}
        self.goal_known_count = {}
        self.goal_initial_gain = {}
        self.goal_targets = {}
        self.goal_routes = {}
        self.cancel_requested = {}
        self.robot_subscriptions = []

        for index in range(self.num_robots):
            robot_name = f"tb{index + 1}"
            self.robot_positions[robot_name] = None
            self.map_to_odom[robot_name] = None
            self.robot_maps[robot_name] = None
            self.robot_velocities[robot_name] = None
            self.robot_states[robot_name] = "idle"
            self.battery_modes[robot_name] = (
                "UNKNOWN" if self.enable_battery else "ACTIVE"
            )
            self.battery_states[robot_name] = {}
            self.battery_state_received_at[robot_name] = None
            self.battery_preempted[robot_name] = False
            self.goal_handles[robot_name] = None
            self.goal_started_at[robot_name] = None
            self.goal_last_progress_at[robot_name] = None
            self.goal_best_distance[robot_name] = None
            self.goal_last_position[robot_name] = None
            self.goal_known_count[robot_name] = 0
            self.goal_initial_gain[robot_name] = 0
            self.goal_targets[robot_name] = None
            self.goal_routes[robot_name] = ()
            self.cancel_requested[robot_name] = False
            self.rally_goal_handles[robot_name] = None
            self.rally_goal_pending[robot_name] = False
            self.rally_goal_started_at[robot_name] = None
            self.rally_leg_routes[robot_name] = ()
            self.rally_yield_requested[robot_name] = False
            self.rally_battery_preempted[robot_name] = False
            self.rally_attempts[robot_name] = 0
            self.rally_arrived[robot_name] = False
            self.robot_nav_clients[robot_name] = ActionClient(
                self,
                NavigateToPose,
                f"/gateway/{robot_name}/navigate_to_pose",
            )
            self.robot_subscriptions.append(
                self.create_subscription(
                    Odometry,
                    f"/gateway/received/{robot_name}/odom",
                    lambda msg, name=robot_name: self.robot_odom_callback(
                        msg, name
                    ),
                    10,
                )
            )
            self.robot_subscriptions.append(
                self.create_subscription(
                    TFMessage,
                    f"/gateway/received/{robot_name}/tf",
                    lambda msg, name=robot_name: self.robot_tf_callback(
                        msg, name
                    ),
                    20,
                )
            )
            self.robot_subscriptions.append(
                self.create_subscription(
                    OccupancyGrid,
                    f"/gateway/received/{robot_name}/map",
                    lambda msg, name=robot_name: self.robot_map_callback(
                        msg, name
                    ),
                    10,
                )
            )
            self.robot_subscriptions.append(
                self.create_subscription(
                    String,
                    f"/gateway/received/{robot_name}/battery_state",
                    lambda msg, name=robot_name: self.battery_state_callback(
                        msg, name
                    ),
                    state_qos,
                )
            )

        self.assignment_timer = self.create_timer(1.0, self.assign_idle_robots)
        self.goal_timeout_timer = self.create_timer(
            1.0, self.cancel_stalled_goals
        )
        self.mission_timer = self.create_timer(0.2, self.update_mission)
        self.publish_task_state("EXPLORE", force=True)
        self.get_logger().info(
            "Central cooperative frontier coordinator initialized."
        )

    def publish_task_state(self, state, force=False):
        if not valid_task_transition(self.task_state, state):
            self.get_logger().error(
                f"Invalid task transition {self.task_state} -> {state}"
            )
            return False
        if state == self.task_state and not force:
            return True
        self.task_state = state
        message = String()
        message.data = state
        self.task_state_publisher.publish(message)
        self.get_logger().info(f"Task state: {state}")
        return True

    def target_observation_callback(self, message):
        if self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED"):
            return
        if message.data in ("EXPLORE", "FOUND_UNCONFIRMED"):
            self.publish_task_state(message.data)

    def target_detection_callback(self, message):
        if self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED"):
            return
        try:
            event = json.loads(message.data)
            self.target = (float(event["target_x"]), float(event["target_y"]))
            self.detecting_robot = str(event["robot"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.get_logger().error(f"Invalid target detection: {error}")
            return
        self.publish_task_state("FOUND")
        if not self.enable_rally:
            return
        self.rally_prepare_started_at = self.now()
        self.get_logger().info(
            f"Preparing rally around target {self.target}."
        )

    def battery_failure_callback(self, message):
        self.fail_task(message.data)

    def battery_state_callback(self, message, robot_name):
        try:
            event = json.loads(message.data)
            mode = str(event["mode"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            self.get_logger().error(
                f"Invalid battery state for {robot_name}: {error}"
            )
            return
        if mode not in ("ACTIVE", "RETURNING", "CHARGING", "FAILED"):
            self.get_logger().error(
                f"Invalid battery mode for {robot_name}: {mode}"
            )
            return
        previous = self.battery_modes[robot_name]
        self.battery_modes[robot_name] = mode
        self.battery_states[robot_name] = event
        self.battery_state_received_at[robot_name] = self.now()
        if mode not in ("RETURNING", "CHARGING"):
            if mode == "ACTIVE" and previous != "ACTIVE":
                self.get_logger().info(
                    f"{robot_name} resumed after charging."
                )
            return

        for name, goal_handle in self.goal_handles.items():
            if goal_handle is not None and not self.cancel_requested[name]:
                self.battery_preempted[name] = True
                self.cancel_requested[name] = True
                goal_handle.cancel_goal_async()
        for name, rally_handle in self.rally_goal_handles.items():
            if rally_handle is not None:
                self.rally_battery_preempted[name] = True
                rally_handle.cancel_goal_async()
        if self.survey_goal_handle is not None:
            self.survey_battery_preempted = True
            self.survey_goal_handle.cancel_goal_async()

    def publish_rally_assignments(self):
        message = String()
        message.data = json.dumps(
            {
                "target_x": self.target[0],
                "target_y": self.target[1],
                "position_tolerance_m": self.rally_position_tolerance,
                "linear_tolerance_mps": self.rally_linear_tolerance,
                "angular_tolerance_radps": self.rally_angular_tolerance,
                "hold_sec": self.rally_hold_sec,
                "poses": {
                    name: {"x": pose.x, "y": pose.y, "yaw": pose.yaw}
                    for name, pose in self.rally_targets.items()
                },
            },
            sort_keys=True,
        )
        self.rally_assignment_publisher.publish(message)

    def fail_task(self, reason):
        if self.task_state in ("COMPLETE", "FAILED"):
            return
        message = String()
        message.data = reason
        self.task_failure_publisher.publish(message)
        self.publish_task_state("FAILED")
        self.get_logger().error(f"Mission failed: {reason}")

    def update_mission(self):
        if self.enable_battery and self.task_state not in ("COMPLETE", "FAILED"):
            now = self.now()
            if self.battery_monitor_started_at is None:
                self.battery_monitor_started_at = now
            if now - self.battery_monitor_started_at >= 20.0:
                unavailable = unavailable_battery_states(
                    self.battery_state_received_at, now, 20.0
                )
                if unavailable:
                    self.fail_task(
                        "battery_state_unavailable:" + ",".join(unavailable)
                    )
                    return
        if self.task_state == "FOUND" and self.enable_rally:
            for name, handle in self.goal_handles.items():
                if handle is not None and not self.cancel_requested[name]:
                    self.cancel_requested[name] = True
                    handle.cancel_goal_async()
            if not all(
                state == "idle" for state in self.robot_states.values()
            ):
                return
            if not all(
                mode == "ACTIVE" for mode in self.battery_modes.values()
            ):
                return
            now = self.now()
            if (
                self.survey_goal_handle is not None
                and self.survey_goal_started_at is not None
                and now - self.survey_goal_started_at
                >= self.goal_timeout_sec
            ):
                self.survey_goal_started_at = None
                self.survey_goal_handle.cancel_goal_async()
            if (
                self.survey_goal_handle is not None
                or self.survey_goal_pending
            ):
                return

            if not self.rally_targets:
                if (
                    self.map_data is None
                    or self.target is None
                    or any(
                        position is None
                        for position in self.robot_positions.values()
                    )
                ):
                    return
                if now - self.last_rally_assignment_attempt < 1.0:
                    return
                self.last_rally_assignment_attempt = now
                self.rally_targets = assign_rally_poses(
                    self.map_data,
                    self.resolution,
                    self.origin,
                    self.robot_positions,
                    self.target,
                )
                if len(self.rally_targets) != self.num_robots:
                    candidate_count = len(
                        rally_pose_candidates(
                            self.map_data,
                            self.resolution,
                            self.origin,
                            self.target,
                        )
                    )
                    if now - self.last_rally_candidate_log >= 2.0:
                        self.get_logger().warn(
                            "Waiting for a complete target-area map; "
                            f"currently {candidate_count} safe candidates."
                        )
                        self.last_rally_candidate_log = now
                    for survey_robot in survey_robot_order(
                        self.robot_positions, self.detecting_robot
                    ):
                        if self.battery_modes[survey_robot] != "ACTIVE":
                            continue
                        survey_pose = rally_survey_pose(
                            self.map_data,
                            self.resolution,
                            self.origin,
                            self.robot_positions[survey_robot],
                            self.target,
                        )
                        if survey_pose is not None:
                            self.send_survey_goal(survey_robot, survey_pose)
                            return
                    if (
                        self.rally_prepare_started_at is not None
                        and now - self.rally_prepare_started_at
                        < RALLY_ASSIGNMENT_WAIT_SEC
                    ):
                        return
                    self.fail_task("insufficient_rally_poses")
                    return
                self.rally_dispatch_order = rally_dispatch_order(
                    self.rally_targets,
                    self.robot_positions,
                    self.target,
                    self.detecting_robot,
                )
                self.publish_rally_assignments()
            self.publish_task_state("RALLY")
            return

        if self.task_state != "RALLY":
            return
        if not all_batteries_active(self.battery_modes):
            self.rally_hold_started_at = None
            return
        now = self.now()
        active_names = [
            name
            for name in self.rally_dispatch_order
            if self.rally_goal_handles[name] is not None
            and not self.rally_yield_requested[name]
            and self.battery_modes[name] == "ACTIVE"
        ]
        for name in robots_that_must_yield(
            self.robot_positions,
            active_names,
            self.rally_dispatch_order,
        ):
            self.rally_yield_requested[name] = True
            self.get_logger().info(
                f"Yielding {name} to a higher-priority nearby robot."
            )
            self.rally_goal_handles[name].cancel_goal_async()

        for name, handle in self.rally_goal_handles.items():
            started_at = self.rally_goal_started_at[name]
            if (
                handle is not None
                and started_at is not None
                and now - started_at >= self.goal_timeout_sec
            ):
                self.get_logger().warn(
                    f"Canceling {name} rally leg after timeout."
                )
                self.rally_goal_started_at[name] = None
                handle.cancel_goal_async()
            target = self.rally_targets[name]
            position = self.robot_positions.get(name)
            if (
                self.rally_arrived[name]
                and position is not None
                and math.dist(position, (target.x, target.y))
                > self.rally_position_tolerance
            ):
                self.rally_arrived[name] = False

        if now - self.last_rally_dispatch_at >= 1.0:
            self.last_rally_dispatch_at = now
            plans = {}
            arrived_positions = [
                self.robot_positions[name]
                for name in self.rally_dispatch_order
                if self.rally_arrived[name]
                and self.robot_positions[name] is not None
            ]
            for name in self.rally_dispatch_order:
                if (
                    self.rally_arrived[name]
                    or self.rally_goal_handles[name] is not None
                    or self.rally_goal_pending[name]
                    or self.robot_positions[name] is None
                    or self.battery_modes[name] != "ACTIVE"
                ):
                    continue
                plans[name] = plan_rally_leg(
                    self.rally_targets[name],
                    self.map_data,
                    self.resolution,
                    self.origin,
                    self.robot_positions[name],
                    RALLY_MAX_NAVIGATION_LEG_M
                    / (self.rally_attempts[name] + 1),
                    arrived_positions,
                )
            routes = {name: plan[1] for name, plan in plans.items()}
            reserved_routes = [
                self.rally_leg_routes[name]
                for name in self.rally_dispatch_order
                if (
                    self.rally_goal_handles[name] is not None
                    or self.rally_goal_pending[name]
                )
                and self.rally_leg_routes[name]
            ]
            for name in select_nonconflicting_routes(
                routes,
                self.rally_dispatch_order,
                reserved_routes,
                max_count=max(
                    0, RALLY_MAX_CONCURRENT - len(reserved_routes)
                ),
            ):
                self.send_rally_goal(name, plans[name])

        stable = robots_stable(
            self.robot_positions,
            self.robot_velocities,
            self.rally_targets,
            self.rally_position_tolerance,
            self.rally_linear_tolerance,
            self.rally_angular_tolerance,
        )
        stable = stable and all(
            mode == "ACTIVE" for mode in self.battery_modes.values()
        )
        if not stable:
            self.rally_hold_started_at = None
            return
        if self.rally_hold_started_at is None:
            self.rally_hold_started_at = now
            return
        if now - self.rally_hold_started_at >= self.rally_hold_sec:
            self.publish_task_state("COMPLETE")

    def send_survey_goal(self, robot_name, pose):
        allowed_attempts = self.num_robots * (1 + self.rally_max_retries)
        if self.survey_attempts >= allowed_attempts:
            self.fail_task(
                f"rally_survey_failed:{robot_name}"
            )
            return
        if not all_batteries_active(self.battery_modes):
            return
        client = self.robot_nav_clients[robot_name]
        if not client.server_is_ready():
            self.survey_attempts += 1
            return
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = pose.x
        goal.pose.pose.position.y = pose.y
        goal.pose.pose.orientation.z = math.sin(pose.yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(pose.yaw / 2.0)
        self.survey_attempts += 1
        self.survey_robot = robot_name
        self.survey_goal_pending = True
        future = client.send_goal_async(goal)
        future.add_done_callback(self.survey_goal_response)

    def survey_goal_response(self, future):
        self.survey_goal_pending = False
        try:
            goal_handle = future.result()
        except Exception as error:
            self.get_logger().error(f"Rally survey request failed: {error}")
            return
        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warn("Rally survey goal was rejected.")
            return
        self.survey_goal_handle = goal_handle
        self.survey_goal_started_at = self.now()
        if not all_batteries_active(self.battery_modes):
            self.survey_battery_preempted = True
            goal_handle.cancel_goal_async()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result, handle=goal_handle: self.survey_goal_result(
                handle, result
            )
        )

    def survey_goal_result(self, goal_handle, future):
        if self.survey_goal_handle is not goal_handle:
            return
        self.survey_goal_handle = None
        self.survey_goal_started_at = None
        survey_robot = self.survey_robot
        try:
            status = future.result().status
        except Exception as error:
            status = f"exception: {error}"
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.survey_battery_preempted = False
            self.rally_prepare_started_at = self.now()
            self.get_logger().info(
                f"{survey_robot} completed a target-area survey leg."
            )
        elif self.survey_battery_preempted:
            self.survey_battery_preempted = False
            self.survey_attempts -= 1
            self.get_logger().info("Target-area survey paused for charging.")
        else:
            self.get_logger().warn(
                f"Target-area survey failed with status {status}."
            )

    def send_rally_goal(self, robot_name, plan=None):
        if (
            self.task_state != "RALLY"
            or not all_batteries_active(self.battery_modes)
        ):
            return
        allowed_attempts = 1 + self.rally_max_retries
        if self.rally_attempts[robot_name] >= allowed_attempts:
            self.fail_task(f"rally_navigation_failed:{robot_name}")
            return
        client = self.robot_nav_clients[robot_name]
        if not client.server_is_ready():
            self.rally_attempts[robot_name] += 1
            return

        if plan is None:
            arrived_positions = [
                self.robot_positions[name]
                for name in self.rally_dispatch_order
                if self.rally_arrived[name]
                and name != robot_name
                and self.robot_positions[name] is not None
            ]
            plan = plan_rally_leg(
                self.rally_targets[robot_name],
                self.map_data,
                self.resolution,
                self.origin,
                self.robot_positions[robot_name],
                RALLY_MAX_NAVIGATION_LEG_M
                / (self.rally_attempts[robot_name] + 1),
                arrived_positions,
            )
        target, route = plan
        self.get_logger().info(
            f"Sending {robot_name} rally leg to "
            f"({target.x:.2f}, {target.y:.2f}); final="
            f"({self.rally_targets[robot_name].x:.2f}, "
            f"{self.rally_targets[robot_name].y:.2f})."
        )
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = target.x
        goal.pose.pose.position.y = target.y
        goal.pose.pose.orientation.z = math.sin(target.yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(target.yaw / 2.0)
        self.rally_leg_routes[robot_name] = route
        self.rally_goal_pending[robot_name] = True
        future = client.send_goal_async(goal)
        future.add_done_callback(
            lambda result, name=robot_name: self.rally_goal_response(name, result)
        )

    def rally_goal_response(self, robot_name, future):
        self.rally_goal_pending[robot_name] = False
        try:
            goal_handle = future.result()
        except Exception as error:
            self.rally_leg_routes[robot_name] = ()
            self.get_logger().error(
                f"{robot_name} rally request failed: {error}"
            )
            return
        if goal_handle is None or not goal_handle.accepted:
            self.rally_leg_routes[robot_name] = ()
            self.get_logger().warn(f"{robot_name} rejected its rally goal.")
            return
        self.rally_goal_handles[robot_name] = goal_handle
        self.rally_goal_started_at[robot_name] = self.now()
        if not all_batteries_active(self.battery_modes):
            self.rally_battery_preempted[robot_name] = True
            goal_handle.cancel_goal_async()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result, name=robot_name, handle=goal_handle: (
                self.rally_goal_result(name, handle, result)
            )
        )

    def rally_goal_result(self, robot_name, goal_handle, future):
        if self.rally_goal_handles[robot_name] is not goal_handle:
            return
        self.rally_goal_handles[robot_name] = None
        self.rally_goal_started_at[robot_name] = None
        self.rally_leg_routes[robot_name] = ()
        yielded = self.rally_yield_requested[robot_name]
        self.rally_yield_requested[robot_name] = False
        battery_preempted = self.rally_battery_preempted[robot_name]
        self.rally_battery_preempted[robot_name] = False
        try:
            status = future.result().status
        except Exception as error:
            status = f"exception: {error}"
        success = status == GoalStatus.STATUS_SUCCEEDED
        target = self.rally_targets[robot_name]
        position = self.robot_positions.get(robot_name)
        self.rally_arrived[robot_name] = (
            success
            and position is not None
            and math.dist(position, (target.x, target.y))
            <= self.rally_position_tolerance
        )
        if self.rally_arrived[robot_name]:
            self.get_logger().info(f"{robot_name} reached its rally pose.")
        elif success:
            self.get_logger().info(
                f"{robot_name} reached an intermediate rally waypoint."
            )
        elif yielded:
            self.get_logger().info(
                f"{robot_name} stopped to yield; replanning next leg."
            )
        elif battery_preempted:
            self.get_logger().info(
                f"{robot_name} rally leg stopped for a safety charge."
            )
        else:
            self.rally_attempts[robot_name] += 1
            self.get_logger().warn(
                f"{robot_name} rally goal failed with status {status}."
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
        twist = msg.twist.twist
        self.robot_velocities[robot_name] = (
            math.hypot(twist.linear.x, twist.linear.y),
            abs(twist.angular.z),
        )
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

    def target_information_gain(self, x, y):
        if self.map_data is None:
            return 0
        row, column = world_to_grid(
            x,
            y,
            self.resolution,
            self.origin[0],
            self.origin[1],
        )
        if not (
            0 <= row < self.map_height
            and 0 <= column < self.map_width
        ):
            return 0
        radius = max(1, math.ceil(INFORMATION_RADIUS_M / self.resolution))
        return _box_count(
            _integral_image(self.map_data < 0),
            row,
            column,
            radius,
            self.map_height,
            self.map_width,
        )

    def assign_idle_robots(self):
        if self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED"):
            return
        if self.map_data is None:
            return
        if not all_robot_inputs_ready(self.robot_positions, self.robot_maps):
            return
        if not all_batteries_active(self.battery_modes):
            return
        idle_positions = {
            name: self.robot_positions[name]
            for name, state in self.robot_states.items()
            if (
                state == "idle"
                and self.robot_positions[name] is not None
                and self.robot_maps[name] is not None
                and self.battery_modes[name] == "ACTIVE"
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
            robot_exclusions = list(exclusions)
            robot_exclusions.extend(
                other_position
                for other_name, other_position in self.robot_positions.items()
                if other_name != robot_name and other_position is not None
            )
            robot_candidates, robot_diagnostics = robot_candidate_assignments(
                self.map_data,
                self.resolution,
                self.origin,
                robot_name,
                position,
                robot_exclusions,
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
                utility = exploration_utility(
                    global_gain,
                    assignment.viewpoint.group_size,
                    assignment.path_distance_m,
                )
                coordinated = Assignment(
                    assignment.viewpoint,
                    assignment.x,
                    assignment.y,
                    assignment.path_distance_m,
                    utility,
                    assignment.navigation_x,
                    assignment.navigation_y,
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
        plans = {}
        routes = {}
        for robot_name, assignment in assignments.items():
            staged = stage_navigation_leg(
                assignment,
                self.map_data,
                self.resolution,
                self.origin,
                self.robot_positions[robot_name],
            )
            plans[robot_name] = staged
            _, routes[robot_name] = plan_rally_leg(
                RallyPose(
                    staged.navigation_x,
                    staged.navigation_y,
                    0.0,
                ),
                self.map_data,
                self.resolution,
                self.origin,
                self.robot_positions[robot_name],
                max_distance_m=float("inf"),
                clearance_m=PATH_CLEARANCE_M,
            )
        reserved_routes = [
            route
            for name, route in self.goal_routes.items()
            if self.robot_states[name] == "active" and route
        ]
        selected = select_nonconflicting_routes(
            routes,
            list(plans),
            reserved_routes,
        )
        for robot_name in selected:
            assignment = plans[robot_name]
            self.robot_states[robot_name] = "active"
            self.goal_targets[robot_name] = assignment
            self.goal_routes[robot_name] = routes[robot_name]
            self.goal_initial_gain[robot_name] = self.target_information_gain(
                assignment.navigation_x, assignment.navigation_y
            )
            self.get_logger().info(
                f"Assigned {robot_name} to group "
                f"{assignment.viewpoint.group_id} at "
                f"({assignment.x:.2f}, {assignment.y:.2f}); "
                f"navigation=({assignment.navigation_x:.2f}, "
                f"{assignment.navigation_y:.2f}), "
                f"path={assignment.path_distance_m:.2f} m, "
                f"gain={assignment.viewpoint.information_gain}, "
                f"utility={assignment.utility:.1f}"
            )
            self.send_goal(robot_name, assignment)

    def send_goal(self, robot_name, assignment):
        if not all_batteries_active(self.battery_modes):
            self.robot_states[robot_name] = "idle"
            self.goal_targets[robot_name] = None
            self.goal_routes[robot_name] = ()
            return
        client = self.robot_nav_clients[robot_name]
        if not client.server_is_ready():
            self.get_logger().warn(
                f"Navigation action server for {robot_name} is unavailable."
            )
            self.robot_states[robot_name] = "idle"
            self.goal_targets[robot_name] = None
            self.goal_routes[robot_name] = ()
            return

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = assignment.navigation_x
        goal.pose.pose.position.y = assignment.navigation_y
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
        if not all_batteries_active(self.battery_modes):
            self.battery_preempted[robot_name] = True
            self.cancel_requested[robot_name] = True
            goal_handle.cancel_goal_async()
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
        battery_preempted = self.battery_preempted[robot_name]
        self.finish_goal(
            robot_name,
            success=success,
            blacklist=not battery_preempted,
        )

    def finish_goal(self, robot_name, success, blacklist=True):
        assignment = self.goal_targets[robot_name]
        if assignment is not None:
            expiry = self.now() + (
                TARGET_HISTORY_SEC if success else BAD_TARGET_SEC
            )
            entry = (
                assignment.navigation_x if success else assignment.x,
                assignment.navigation_y if success else assignment.y,
                expiry,
            )
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
        self.goal_initial_gain[robot_name] = 0
        self.goal_targets[robot_name] = None
        self.goal_routes[robot_name] = ()
        self.cancel_requested[robot_name] = False
        self.battery_preempted[robot_name] = False
        self.robot_states[robot_name] = "idle"
        self.check_exploration_completion()

    def cancel_stalled_goals(self):
        if self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED"):
            return
        now = self.now()
        for robot_name, goal_handle in self.goal_handles.items():
            started_at = self.goal_started_at[robot_name]
            last_progress = self.goal_last_progress_at[robot_name]
            if goal_handle is None or started_at is None:
                continue
            timed_out = now - started_at >= self.goal_timeout_sec
            assignment = self.goal_targets[robot_name]
            remaining_gain = (
                self.target_information_gain(
                    assignment.navigation_x, assignment.navigation_y
                )
                if assignment is not None
                else 0
            )
            stale = goal_is_stale(
                self.goal_initial_gain[robot_name],
                remaining_gain,
                now - started_at,
            )
            stalled = (
                last_progress is not None
                and now - started_at >= 10.0
                and now - last_progress >= NO_PROGRESS_SEC
            )
            if (
                not (timed_out or stalled or stale)
                or self.cancel_requested[robot_name]
            ):
                continue
            if timed_out:
                reason = "timeout"
            elif stalled:
                reason = "no progress"
            else:
                reason = "frontier already observed"
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
