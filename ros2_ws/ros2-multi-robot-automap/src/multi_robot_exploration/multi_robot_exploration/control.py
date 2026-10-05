from dataclasses import dataclass
import json
import math
import os
import signal
import subprocess
import threading
import time
from collections import deque
from itertools import permutations

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
from scipy.spatial import cKDTree
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from .fault_model import CHARGE_REQUEST_TTL_SEC, STATE_TTL_SEC, TARGET_DETECTION_TTL_SEC

OCCUPIED_THRESHOLD = 50
MIN_FRONTIER_GROUP_SIZE = 6
ROBOT_CLEARANCE_M = 0.45
PATH_CLEARANCE_M = 0.35
VIEWPOINT_SEARCH_RADIUS_M = 0.8
INFORMATION_RADIUS_M = 2.0
MIN_TARGET_SEPARATION_M = 1.2
MAX_NAVIGATION_LEG_M = 5.0
NAVIGATION_POSITION_TOLERANCE_M = 0.02
NAVIGATION_YAW_TOLERANCE_RAD = 0.25
TARGET_HISTORY_SEC = 10.0
TARGET_OBSERVER_FRESHNESS_SEC = 5.0
BAD_TARGET_SEC = 30.0
NO_PROGRESS_SEC = 20.0
USEFUL_TRAVEL_M = 0.75
GOAL_REPLAN_SEC = 3.0
MIN_REMAINING_GAIN = 200
MIN_REMAINING_GAIN_FRACTION = 0.2
# Calibrated against the existing Nav2 loop, including planner/controller pauses.
NAVIGATION_TIME_EXPONENT = 1.5
PLANNING_OVERHEAD_SEC = 1.0
RALLY_CLEARANCE_M = 0.45
RALLY_PATH_CLEARANCE_M = 0.35
RALLY_MIN_SEPARATION_M = 0.8
RALLY_PREFERRED_SEPARATION_M = 1.2
RALLY_DYNAMIC_CLEARANCE_M = 0.6
RALLY_POSITION_TOLERANCE_M = 0.35
RALLY_LINEAR_TOLERANCE_MPS = 0.05
RALLY_ANGULAR_TOLERANCE_RADPS = 0.10
RALLY_HOLD_SEC = 5.0
RALLY_GOAL_TIMEOUT_SEC = 30.0
# A merged map can lag the local SLAM/costmap by several seconds after a
# target is found.  Keep the route failure diagnostic, but allow map delivery
# and a fresh rally-pose assignment to recover before failing the mission.
RALLY_ASSIGNMENT_WAIT_SEC = 30.0
# Whole-route feasibility searches are unbounded; dispatched navigation legs
# are capped and smoothed separately, including traffic holding points.
RALLY_MAX_NAVIGATION_LEG_M = float("inf")
RALLY_ROUTE_SEPARATION_M = 1.8
# Independent corridors may run concurrently; shared corridors remain reserved
# until the delivered live pose confirms passage.
RALLY_MAX_CONCURRENT = 2
EXPLORATION_MAX_CONCURRENT = 3

TASK_TRANSITIONS = {
    "EXPLORE": {"FOUND_UNCONFIRMED", "FOUND", "FAILED"},
    "FOUND_UNCONFIRMED": {"EXPLORE", "FOUND", "FAILED"},
    "FOUND": {"RALLY", "FAILED"},
    "RALLY": {"COMPLETE", "PARTIAL_COMPLETE", "FAILED"},
    "COMPLETE": set(),
    "PARTIAL_COMPLETE": set(),
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
    navigation_yaw: float | None = None


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
        if timestamp is None or not 0 <= now - timestamp < timeout
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


def quaternion_yaw(rotation):
    return math.atan2(
        2.0 * (rotation.w * rotation.z + rotation.x * rotation.y),
        1.0 - 2.0 * (rotation.y * rotation.y + rotation.z * rotation.z),
    )


def transform_point_2d(x, y, transform):
    """Apply a TransformStamped's planar transform to a point."""
    translation = transform.translation
    yaw = quaternion_yaw(transform.rotation)
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


def planning_grid_without_self_returns(raw_grid, resolution, origin, positions):
    """Separate isolated body-cell returns from the static planning layer.

    The caller supplies fresh delivered body poses. Only one occupied cell,
    wholly surrounded by known free cells and no larger than 0.1m diagonal,
    is eligible. Walls, connected obstacles, unknowns and the source grid
    remain untouched. Peer bodies still require their normal dynamic masks.
    This is a bounded self-return heuristic, not general obstacle recognition.
    """
    result = raw_grid
    removed = {}
    if not math.isfinite(resolution) or resolution <= 0 or resolution * math.sqrt(2) > .1:
        return result, removed
    for name, position in positions.items():
        if position is None or not all(math.isfinite(v) for v in position):
            continue
        row, column = world_to_grid(*position, resolution, *origin)
        if not (1 <= row < raw_grid.shape[0]-1 and 1 <= column < raw_grid.shape[1]-1):
            continue
        if raw_grid[row, column] < OCCUPIED_THRESHOLD:
            continue
        window = raw_grid[row-1:row+2, column-1:column+2].copy()
        window[1, 1] = 0
        if not np.all(window == 0):
            continue
        if result is raw_grid:
            result = raw_grid.copy()
        result[row, column] = 0
        removed[name] = (row, column)
    return result, removed


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


def visible_unknown_gain(raw_grid, start, radius_cells, interest=None):
    """Count informative ray cells; a search mask requires known-free sight."""
    row, column = start
    height, width = raw_grid.shape
    if not (0 <= row < height and 0 <= column < width) or raw_grid[start] != 0:
        return 0
    radius = max(1, math.ceil(radius_cells))
    angles = np.linspace(
        0, 2 * math.pi, max(32, math.ceil(2 * math.pi * radius)), endpoint=False
    )
    steps = np.arange(0.5, radius_cells + 0.25, 0.5)
    rows = np.rint(row + np.sin(angles)[:, None] * steps).astype(int)
    columns = np.rint(column + np.cos(angles)[:, None] * steps).astype(int)
    inside = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
    rows = np.clip(rows, 0, height - 1)
    columns = np.clip(columns, 0, width - 1)
    values = raw_grid[rows, columns]
    visible = np.logical_and.accumulate(
        inside & ((values < OCCUPIED_THRESHOLD) if interest is None else (values == 0)), axis=1
    )
    informative = values < 0 if interest is None else interest[rows, columns]
    unknown_cells = (rows * width + columns)[visible & informative]
    return int(np.unique(unknown_cells).size)


def known_space_search_candidates(raw_grid, resolution, origin, robot_name,
                                  position, visited, exclusions=(), blocked=(), gain_cache=None):
    """Revisit current known space when mapping frontiers cannot aid detection.

    Visited neighborhoods are a search preference, not proof of visual coverage.
    Neither expired detections nor old rally goals are inputs. The same actual
    map, dynamic clearance, distance field and short-leg admission still apply.
    A shared gain cache belongs to one immutable map/visit batch only.
    """
    traversable = block_dynamic_positions(
        traversable_grid(raw_grid, resolution, PATH_CLEARANCE_M), resolution, origin, blocked)
    start = navigation_start_cell(raw_grid, traversable,
        world_to_grid(*position, resolution, *origin), max(1, math.ceil(.6 / resolution)))
    if start is None:
        return []
    distances = path_distance_grid(traversable, start)
    rows, columns = np.indices(raw_grid.shape)
    interest = raw_grid == 0
    for x, y in visited:
        interest &= ((columns + .5) * resolution + origin[0] - x) ** 2 + (
            (rows + .5) * resolution + origin[1] - y) ** 2 > INFORMATION_RADIUS_M ** 2
    if not interest.any():
        return []
    # One sample per metre, snapped to actual reachable cells, includes narrow
    # corridors that a fixed lattice alone can miss.
    reachable = traversable & np.isfinite(distances)
    nearest = ndimage.distance_transform_edt(~reachable, return_distances=False, return_indices=True)
    stride = max(1, math.ceil(1. / resolution))
    cells = sorted(set(zip(nearest[0, ::stride, ::stride].ravel(), nearest[1, ::stride, ::stride].ravel())))
    candidates = []
    if gain_cache is None:
        gain_cache = {}
    for row, column in cells:
        distance = float(distances[row, column] * resolution)
        x, y = grid_to_world(row, column, resolution, *origin)
        if not math.isfinite(distance) or distance < USEFUL_TRAVEL_M or any(
                math.dist((x, y), point) < MIN_TARGET_SEPARATION_M for point in exclusions):
            continue
        cell = (row, column)
        if cell not in gain_cache:
            gain_cache[cell] = visible_unknown_gain(raw_grid, cell, INFORMATION_RADIUS_M / resolution, interest)
        gain = gain_cache[cell]
        if gain == 0:
            continue
        viewpoint = Viewpoint(row * raw_grid.shape[1] + column, row, column, row, column, gain, 1)
        utility = gain / (distance + 1.)
        candidates.append((utility, robot_name, viewpoint.group_id,
                           Assignment(viewpoint, x, y, distance, utility, x, y)))
    return candidates


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
        # Keep broad coverage first; fill small groups with fine alternatives.
        # Fleet target separation remains independent of viewpoint sampling.
        for spacing_cells in (separation_cells, max(1, math.ceil(0.2 / resolution))):
            remaining = ranked_indices
            for point in selected:
                squared = (
                    (rows[remaining] - point.row) ** 2
                    + (columns[remaining] - point.column) ** 2
                )
                remaining = remaining[squared >= spacing_cells * spacing_cells]
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
                    visible_unknown_gain(
                        raw_grid, (row, column), INFORMATION_RADIUS_M / resolution
                    ),
                    len(group),
                )
                selected.append(viewpoint)
                distance_squared = (
                    (rows[remaining] - row) ** 2
                    + (columns[remaining] - column) ** 2
                )
                remaining = remaining[
                    distance_squared >= spacing_cells * spacing_cells
                ]
        if selected:
            viewpoints[group_id] = selected
    return viewpoints


def exploration_utility(
    information_gain,
    group_size,
    path_distance_m,
):
    """Estimate new coverage gained per calibrated navigation-time unit."""
    departure = min(1.0, path_distance_m / USEFUL_TRAVEL_M)
    # Nav2's observed goal-to-goal latency grows super-linearly with distance
    # because long legs incur replanning and controller recovery pauses.
    travel_time = PLANNING_OVERHEAD_SEC + (
        (1.0 + path_distance_m) ** NAVIGATION_TIME_EXPONENT - 1.0
    )
    return (
        (information_gain + group_size) * departure / travel_time
    )


def target_reuse_penalty(target, excluded_targets):
    """Prefer fresh space while retaining a safe fallback in narrow maps."""
    if not excluded_targets:
        return 1.0
    nearest = min(math.dist(target, other) for other in excluded_targets)
    if nearest >= MIN_TARGET_SEPARATION_M:
        return 1.0
    ratio = max(0.0, nearest / MIN_TARGET_SEPARATION_M)
    return 0.35 + 0.65 * ratio


def goal_is_stale(initial_gain, remaining_gain, age_sec):
    if age_sec < GOAL_REPLAN_SEC or initial_gain <= 0:
        return False
    threshold = max(
        MIN_REMAINING_GAIN,
        initial_gain * MIN_REMAINING_GAIN_FRACTION,
    )
    return remaining_gain <= threshold


def interrupted_frontier_is_useful(assignment, intent, battery_factor):
    """Prioritize current frontier candidates near a preempted search intent."""
    return (
        intent is not None
        and battery_factor >= 1.0
        and math.dist((assignment.x, assignment.y), intent[:2]) <= MIN_TARGET_SEPARATION_M
        and assignment.viewpoint.information_gain > max(
            MIN_REMAINING_GAIN, intent[2] * MIN_REMAINING_GAIN_FRACTION
        )
    )


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


def exact_traversable_start(traversable, start):
    """Return a robot start cell only when the received map marks it safe."""
    if start is None:
        return None
    row, column = start
    if not (0 <= row < traversable.shape[0] and 0 <= column < traversable.shape[1]):
        return None
    return start if traversable[start] else None


def navigation_start_cell(raw_grid, traversable, start, max_radius_cells):
    """
    Choose a map path start without hiding a genuinely occupied pose.

    SLAM maps can mark the cell under a robot as free while the clearance mask
    removes it because a nearby occupied cell was inflated.  In that case a
    short escape to the nearest known-free cell is a valid navigation leg.  A
    pose whose raw cell is occupied or unknown is still rejected; snapping it
    would make the central planner disagree with Nav2 about the real start.
    """
    return navigation_start_route(
        raw_grid, traversable, start, max_radius_cells
    )[0]


def navigation_start_route(raw_grid, traversable, start, max_radius_cells):
    """Return a known-free escape route and its clearance-safe endpoint."""
    if start is None:
        return None, ()
    row, column = start
    if not (0 <= row < raw_grid.shape[0] and 0 <= column < raw_grid.shape[1]):
        return None, ()
    if raw_grid[start] != 0:
        return None, ()
    queue = deque([start])
    predecessors = {start: None}
    distances = {start: 0}
    while queue:
        current = queue.popleft()
        if traversable[current]:
            route = []
            while current is not None:
                route.append(current)
                current = predecessors[current]
            route.reverse()
            return route[-1], tuple(route)
        if distances[current] >= max_radius_cells:
            continue
        row, column = current
        for delta_row, delta_column in (
            (-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ):
            next_cell = (row + delta_row, column + delta_column)
            if next_cell in predecessors or not (
                0 <= next_cell[0] < raw_grid.shape[0]
                and 0 <= next_cell[1] < raw_grid.shape[1]
            ):
                continue
            if raw_grid[next_cell] != 0:
                continue
            if delta_row and delta_column and (
                raw_grid[row, next_cell[1]] != 0
                or raw_grid[next_cell[0], column] != 0
            ):
                continue
            predecessors[next_cell] = current
            distances[next_cell] = distances[current] + 1
            queue.append(next_cell)
    return None, ()


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
        if dr and dc:
            connected &= (
                traversable[source_r0:source_r1, target_c0:target_c1]
                & traversable[target_r0:target_r1, source_c0:source_c1]
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


def path_waypoint_route(traversable, start, target, max_distance_cells, distance_data=None):
    """Return a limited waypoint and its shortest grid path from start."""
    height, width = traversable.shape
    if (
        start is None
        or not (0 <= target[0] < height and 0 <= target[1] < width)
        or not traversable[target]
    ):
        return None, ()
    distances, predecessors = (
        distance_data if distance_data is not None else path_distance_grid(
            traversable, start, return_predecessors=True
        )
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
    # A known-free pose can be inside the clearance inflation of a nearby
    # obstacle; navigation_start_cell provides a short escape in that case.
    start, _ = navigation_start_route(
        raw_grid,
        traversable,
        start,
        max(1, math.ceil(0.6 / resolution)),
    )
    if start is None:
        return None
    target = world_to_grid(
        assignment.x,
        assignment.y,
        resolution,
        origin[0],
        origin[1],
    )
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


def prepare_frontier_data(raw_grid, resolution):
    """Build map-derived frontier data once for each map snapshot."""
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
    return groups, traversable, viewpoints


def robot_candidate_assignments(
    raw_grid,
    resolution,
    origin,
    robot_name,
    robot_position,
    excluded_targets=(),
    frontier_data=None,
    blocked_positions=None,
):
    """Return diverse locally reachable viewpoints for every frontier group."""
    if frontier_data is None:
        frontier_data = prepare_frontier_data(raw_grid, resolution)
    groups, traversable, viewpoints = frontier_data
    candidates = []
    if blocked_positions is not None:
        traversable = block_dynamic_positions(
            traversable, resolution, origin, blocked_positions
        )
    start = world_to_grid(
        robot_position[0],
        robot_position[1],
        resolution,
        origin[0],
        origin[1],
    )
    start = navigation_start_cell(
        raw_grid,
        traversable,
        start,
        max(1, math.ceil(0.6 / resolution)),
    )
    if start is None:
        return [], {
            "frontier_groups": len(groups),
            "groups_with_viewpoints": len(viewpoints),
            "candidate_assignments": 0,
        }
    distances = path_distance_grid(traversable, start)
    if blocked_positions is not None:
        # Global top-K viewpoints can all lie in blocked/disconnected areas.
        # Refine within this robot’s safe reachable component only on demand.
        safe = traversable_grid(raw_grid, resolution, ROBOT_CLEARANCE_M)
        safe &= traversable & np.isfinite(distances)
        viewpoints = frontier_viewpoints(raw_grid, groups, safe, resolution)
    for group_id, group_viewpoints in viewpoints.items():
        for viewpoint in group_viewpoints:
            if viewpoint.information_gain <= 0:
                continue
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
            path_distance_m = float(distance_cells * resolution)
            utility = exploration_utility(
                viewpoint.information_gain,
                viewpoint.group_size,
                path_distance_m,
            )
            if utility <= 0:
                continue
            utility *= target_reuse_penalty((x, y), excluded_targets)
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
    """Maximize fleet utility over spatially separated observation targets.

    All robots bid on the same target set. Optimal bipartite matching avoids
    a greedy robot taking the only reachable target of another robot.
    """
    if not candidates:
        return {}
    targets = []
    for _, _, _, assignment in sorted(candidates, key=lambda item: -item[0]):
        target = (assignment.x, assignment.y)
        if all(math.dist(target, other) >= MIN_TARGET_SEPARATION_M
               for other in targets):
            targets.append(target)
    names = sorted({item[1] for item in candidates})
    target_indices = {target: index for index, target in enumerate(targets)}
    name_indices = {name: index for index, name in enumerate(names)}
    utilities = np.zeros((len(names), len(targets) + len(names)))
    options = {}
    for utility, name, _, assignment in candidates:
        column = target_indices.get((assignment.x, assignment.y))
        if column is None:
            continue
        row = name_indices[name]
        if utility > utilities[row, column]:
            utilities[row, column] = utility
            options[row, column] = assignment
    rows, columns = linear_sum_assignment(utilities, maximize=True)
    return {
        names[row]: options[row, column]
        for row, column in zip(rows, columns)
        if (row, column) in options
    }


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


def assign_rally_poses(
    raw_grid,
    resolution,
    origin,
    robot_positions,
    target,
    objective="minimax",
    battery_states=None,
    observer_robot=None,
    current_positions=None,
    hold_sec=RALLY_HOLD_SEC,
):
    """Assign separated visible poses, accounting for serial charge waits.

    With delivered batteries, preserve an ACTIVE observer when feasible, then
    minimize predicted charges and serial travel/charge time, then compare
    its remaining budget headroom before the chosen path objective. Extra
    observer surplus must not force a funded peer to charge or take a detour.
    These estimates never authorize a navigation or return.
    """
    if objective not in ("minimax", "total_path"):
        raise ValueError(f"unknown rally assignment objective: {objective}")
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
        # Unknown and occupied starts remain rejected; only a known-free pose
        # may use the bounded clearance escape above.
        start, escape_route = navigation_start_route(
            raw_grid,
            traversable,
            start,
            max(1, math.ceil(0.6 / resolution)),
        )
        distances = path_distance_grid(traversable, start)
        escape_distance = 0.0
        for first, second in zip(escape_route, escape_route[1:]):
            escape_distance += math.dist(first, second)
        reachable = []
        for index, pose in enumerate(candidates):
            row, column = world_to_grid(
                pose.x, pose.y, resolution, origin[0], origin[1]
            )
            distance = distances[row, column]
            if np.isfinite(distance):
                reachable.append((float(distance + escape_distance), index))
        reachable.sort()
        if not reachable:
            return {}
        options[name] = reachable

    energy_options, modes, charge_times, charge_targets = {}, {}, {}, {}
    if battery_states is not None:
        current_positions = current_positions or robot_positions
        try:
            if not math.isfinite(hold_sec) or hold_sec < 0:
                return {}
            for name in names:
                state = battery_states[name]
                mode = state["mode"]
                energy = float(state["energy"])
                home = (float(state["charge_x"]), float(state["charge_y"]))
                speed = float(state.get("nominal_speed_mps", .18))
                idle = float(state.get("idle_cost_per_sec", .02))
                move = float(state.get("move_cost_per_m", 1.))
                factor = float(state.get("return_path_factor", 2.))
                margin = float(state.get("return_safety_margin", 8.))
                duration = float(state.get("charge_duration_sec", 6.))
                capacity = float(state["capacity"])
                fraction = float(state["charge_target_fraction"])
                values = (*home, energy, speed, idle, move, factor, margin,
                          duration, capacity, fraction, *current_positions[name])
                if (not all(math.isfinite(v) for v in values)
                        or mode not in ("ACTIVE", "RETURNING", "CHARGING")
                        or min(energy, idle, move, margin, duration) < 0
                        or speed <= 0 or capacity <= 0 or factor < 1
                        or not 0 < fraction <= 1):
                    return {}
                home_start, escape = navigation_start_route(
                    raw_grid, traversable, world_to_grid(*home, resolution, *origin),
                    max(1, math.ceil(.6 / resolution)))
                home_distances = path_distance_grid(traversable, home_start)
                home_escape = sum(math.dist(a, b) for a, b in zip(escape, escape[1:]))
                modes[name] = mode
                charge_times[name] = duration
                if mode != "CHARGING":
                    charge_times[name] += math.dist(current_positions[name], home) * factor / speed
                charge_targets[name] = capacity * fraction
                energy_options[name] = {}
                for distance, index in options[name]:
                    pose = candidates[index]
                    cell = world_to_grid(pose.x, pose.y, resolution, *origin)
                    home_distance = (home_distances[cell] + home_escape) * resolution
                    if not math.isfinite(home_distance):
                        continue
                    required = battery_assignment_required_energy(
                        distance * resolution, math.dist((pose.x, pose.y), home),
                        move, idle, factor, speed, margin) + idle * hold_sec
                    travel = distance * resolution / speed
                    after_charge = home_distance / speed
                    energy_options[name][index] = (required, travel, after_charge)
                options[name] = [(distance, index) for distance, index in options[name]
                                 if index in energy_options[name]]
                if not options[name]:
                    return {}
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return {}

    # Resolve the leading observer budget first so its monotone bound
    # prunes peer combinations before expensive complete energy closures.
    search_order = sorted(names, key=lambda name: (
        battery_states is not None and observer_robot in names and name != observer_robot,
        len(options[name])))
    best = {}
    best_score = (float("inf"),) * (7 if battery_states is not None else 3)
    selected_indices = {}
    minimum_energy_options = {
        name: tuple(min(values[column] for values in choices.values()) for column in range(3))
        for name, choices in energy_options.items()
    }
    parked_route_caches = {}
    parked_detour_costs = {}

    def parked_peer_delay(needed):
        # Any funded peer may park before a charged robot comes back from home.
        # Sum single-body detour costs, reusing fields by body pose/home source.
        # Combined-body interactions are still checked at actual dispatch;
        # this nominal additive preference never authorizes a navigation leg.
        delay = 0.0
        for parked in names:
            if parked in needed or modes[parked] != 'ACTIVE':
                continue
            parked_index = selected_indices[parked]
            body = candidates[parked_index]
            for name in names:
                if name not in needed:
                    continue
                index = selected_indices[name]
                key = (parked_index, name, index)
                if key not in parked_detour_costs:
                    state = battery_states[name]
                    _, route = plan_rally_leg(
                        candidates[index], raw_grid, resolution, origin,
                        (float(state["charge_x"]), float(state["charge_y"])),
                        blocked_positions=[(body.x, body.y)],
                        route_cache=parked_route_caches.setdefault((parked_index, name), {}),
                    )
                    speed = float(state.get("nominal_speed_mps", .18))
                    cost = (sum(math.dist(a, b) for a, b in zip(route, route[1:])) / speed
                            - energy_options[name][index][2]) if route else RALLY_GOAL_TIMEOUT_SEC
                    # Missing masked paths keep the finite recovery preference,
                    # not a false infeasibility proof. Partial bounds omit this
                    # nonnegative term and remain optimistic.
                    parked_detour_costs[key] = max(0.0, cost)
                delay += parked_detour_costs[key]
        return delay

    def search(
        assignments,
        used_indices,
        separation_penalty,
        cost,
        longest_path,
    ):
        nonlocal best, best_score
        score = (
            (longest_path, separation_penalty, cost)
            if objective == "minimax"
            else (separation_penalty, cost, longest_path)
        )
        if battery_states is not None:
            # Independent per-column minima may refer to different candidates;
            # that only makes this an optimistic, admissible partial bound.
            # At a complete leaf every entry is the actual selected option.
            estimates = {name: energy_options[name][selected_indices[name]]
                         if name in selected_indices else minimum_energy_options[name]
                         for name in names}
            requirements, _ = rally_wait_requirements(
                {name: values[0] for name, values in estimates.items()},
                battery_states, modes,
                {name: values[1] for name, values in estimates.items()}, charge_times)
            needed = {name for name in names if modes[name] != "ACTIVE"
                      or float(battery_states[name]["energy"]) <= requirements[name]}
            if any(requirements[name] > charge_targets[name] for name in needed):
                return
            observer_headroom = (max(0., float(battery_states[observer_robot]["energy"])
                                     - requirements[observer_robot])
                                 if modes.get(observer_robot) == "ACTIVE" else 0.)
            complete = len(assignments) == len(search_order)
            time_bound = sum(charge_times[name] + values[2] if name in needed
                             else values[1] if complete
                             else min(values[1], charge_times[name] + values[2])
                             for name, values in estimates.items())
            observer_charge = int(observer_robot in needed and modes.get(observer_robot) == "ACTIVE")
            score = (observer_charge, len(needed), time_bound, -observer_headroom, *score)
        if score >= best_score:
            return
        if len(assignments) == len(search_order):
            if battery_states is not None:
                score = (score[0], score[1], score[2] + parked_peer_delay(needed), *score[3:])
                if score >= best_score:
                    return
            best = assignments.copy()
            best_score = score
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
            selected_indices[name] = candidate_index
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
                max(longest_path, distance),
            )
            used_indices.remove(candidate_index)
            del assignments[name]
            del selected_indices[name]

    search({}, set(), 0.0, 0.0, 0.0)
    if not best:
        return {}
    return {name: best[name] for name in names}


def reassign_rally_pose(
    raw_grid,
    resolution,
    origin,
    robot_name,
    robot_position,
    target,
    reserved_poses=(),
    blocked_positions=(),
):
    """Choose a fresh reachable pose when a delivered map invalidates one."""
    candidates = rally_pose_candidates(raw_grid, resolution, origin, target)
    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=RALLY_PATH_CLEARANCE_M
    )
    start = world_to_grid(robot_position[0], robot_position[1], resolution,
                          origin[0], origin[1])
    start = navigation_start_cell(raw_grid, traversable, start,
                                  max(1, math.ceil(0.6 / resolution)))
    if start is None:
        return None
    distances = path_distance_grid(traversable, start)
    route_cache = {}
    best = None
    for pose in candidates:
        if any(
            math.dist((pose.x, pose.y), other) < RALLY_MIN_SEPARATION_M
            for other in reserved_poses
        ):
            continue
        plan = plan_rally_leg(
            pose,
            raw_grid,
            resolution,
            origin,
            robot_position,
            max_distance_m=float("inf"),
            blocked_positions=blocked_positions,
            route_cache=route_cache,
        )
        if plan[0] is None:
            continue
        cell = world_to_grid(pose.x, pose.y, resolution, origin[0], origin[1])
        distance = distances[cell] if (
            0 <= cell[0] < traversable.shape[0]
            and 0 <= cell[1] < traversable.shape[1]
        ) else np.inf
        if not np.isfinite(distance):
            continue
        if best is None or distance < best[0]:
            best = (float(distance), pose)
    return None if best is None else best[1]


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
    start, _ = navigation_start_route(
        raw_grid,
        traversable,
        start,
        max(1, math.ceil(0.6 / resolution)),
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


def rally_target_view(raw_grid, resolution, origin, position, target, max_distance):
    """Predict visibility only from the delivered map and detector range."""
    return (math.dist(position, target) <= max_distance
            and has_known_line_of_sight(
                raw_grid, world_to_grid(*position, resolution, *origin),
                world_to_grid(*target, resolution, *origin)))


def rally_yield_pose(
    raw_grid,
    resolution,
    origin,
    robot_position,
    target,
    reserved_poses=(),
    blocked_positions=(),
    reserved_routes=(),
    route_separation_m=RALLY_MIN_SEPARATION_M,
    visible_only=False,
    target_view_distance=None,
):
    """Choose a reachable refuge outside parked poses and reserved corridors."""
    traversable = traversable_grid(
        raw_grid, resolution, clearance_m=RALLY_PATH_CLEARANCE_M
    )
    traversable = block_dynamic_positions(
        traversable, resolution, origin, blocked_positions
    )
    start = world_to_grid(
        robot_position[0], robot_position[1], resolution,
        origin[0], origin[1],
    )
    start = navigation_start_cell(
        raw_grid,
        traversable,
        start,
        max(1, math.ceil(0.6 / resolution)),
    )
    if start is None:
        return None
    distances = path_distance_grid(traversable, start)
    route_points = [point for route in reserved_routes for point in route]
    route_tree = cKDTree(route_points) if route_points else None
    candidates = []
    for row, column in np.argwhere(np.isfinite(distances)):
        path_distance = float(distances[row, column] * resolution)
        if path_distance < 0.5 or path_distance > 5.0:
            continue
        x, y = grid_to_world(row, column, resolution, origin[0], origin[1])
        target_distance = math.dist((x, y), target)
        if target_distance < 0.7:
            continue
        if target_view_distance is not None and target_distance > target_view_distance:
            continue
        if any(
            math.dist((x, y), pose) < RALLY_MIN_SEPARATION_M
            for pose in (*reserved_poses, *blocked_positions)
        ):
            continue
        if route_tree is not None and route_tree.query((x, y))[0] < route_separation_m:
            continue
        candidates.append((target_distance, path_distance, x, y))
    if not candidates:
        return None
    if reserved_routes:
        candidates.sort(key=lambda item: item[1])
    else:
        candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    # Verify nearest refuges in order, stopping at the first feasible one.
    # Testing line geometry for every free cell stalls the gateway executor.
    for _, _, x, y in candidates:
        if target_view_distance is not None and not rally_target_view(
                raw_grid, resolution, origin, (x, y), target, target_view_distance):
            continue
        if visible_only:
            cell = world_to_grid(x, y, resolution, origin[0], origin[1])
            line = tuple(_line_cells(start, cell))
            if not all(traversable[point] for point in line):
                continue
            if route_tree is not None:
                points = [grid_to_world(r, c, resolution, origin[0], origin[1]) for r, c in line]
                separation = route_tree.query(points)[0]
                # Escape on this side, without crossing the occupied corridor
                # or stopping at an intermediate bend still inside it.
                if any(b + resolution < min(a, route_separation_m)
                       for a, b in zip(separation, separation[1:])):
                    continue
        return RallyPose(x, y, math.atan2(target[1] - y, target[0] - x))
    return None


def rally_observation_heading(pose, target, grid, resolution, origin, max_distance):
    """Center a delivered target in the camera at a visible intermediate pose."""
    if target is None or not rally_target_view(
            grid, resolution, origin, (pose.x, pose.y), target,
            max_distance - NAVIGATION_POSITION_TOLERANCE_M):
        return pose
    return RallyPose(pose.x, pose.y, math.atan2(target[1] - pose.y, target[0] - pose.x))


def survey_robot_order(robot_positions, detecting_robot):
    return sorted(
        robot_positions,
        key=lambda name: (name != detecting_robot, name),
    )


def rotate_robot_order(order, cursor):
    """Rotate a deterministic robot order so one failed robot cannot starve others."""
    if not order:
        return []
    offset = cursor % len(order)
    return list(order[offset:]) + list(order[:offset])


def rally_reserved_poses(rally_targets, rally_final_targets, exclude=()):
    """Keep active and pending final poses reserved during recovery."""
    excluded = set(exclude)
    reserved = []
    for name, pose in rally_targets.items():
        if name in excluded:
            continue
        reserved.append((pose.x, pose.y))
        final_pose = rally_final_targets.get(name)
        if final_pose is not None:
            reserved.append((final_pose.x, final_pose.y))
    return reserved


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
            (
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


def rally_approach_inversions(order, positions, routes):
    """Count a behind intent reserving the body of a one-way ahead robot."""
    return sum(
        routes_conflict(routes[leader], (positions[follower],), RALLY_ROUTE_SEPARATION_M)
        and not routes_conflict(routes[follower], (positions[leader],), RALLY_ROUTE_SEPARATION_M)
        for index, leader in enumerate(order)
        for follower in order[index + 1:]
        if leader in routes and follower in routes
    )


def map_safe_rally_dispatch_order(
    raw_grid,
    resolution,
    origin,
    targets,
    robot_positions,
    target,
    priority_robot=None,
):
    """
    Select a serial rally order whose successive routes stay reachable.

    A pose that is safe in isolation can still seal the only approach to a
    later pose.  Evaluate the small permutation space once at RALLY entry and
    keep already placed robots as dynamic obstacles while checking the next
    route. If current parked bodies prevent every complete order, minimize
    final-pose obstructions on later intent routes. Actual blockage still
    belongs to the existing body/route checks and safe recovery state machine.
    """
    names = list(targets)
    if len(names) < 2:
        return names
    route_caches = {}

    def plan_for(name, blocked=()):
        # Each field is valid only for this snapshot, start and exact body mask.
        # Permutations often revisit the same first or last mover context.
        blocked = tuple(sorted(tuple(position) for position in blocked))
        return plan_rally_leg(
            targets[name], raw_grid, resolution, origin, robot_positions[name],
            max_distance_m=float("inf"), blocked_positions=blocked,
            route_cache=route_caches.setdefault((name, blocked), {}),
        )

    intent_routes = {}
    for name in names:
        if robot_positions.get(name) is not None:
            _, route = plan_for(name)
            if route:
                intent_routes[name] = route
    # A robot already ahead on a shared approach must not wait for a robot
    # behind whose future reservation passes through that parked body. This
    # preference only ranks complete body-masked serial plans below; it never
    # exempts a live leg, return, body or source-age admission check.
    best = None
    for order in permutations(names):
        occupied = dict(robot_positions)
        total_distance = 0.0
        feasible = True
        for name in order:
            position = robot_positions.get(name)
            if position is None:
                feasible = False
                break
            blocked = [
                other_position
                for other_name, other_position in occupied.items()
                if other_name != name and other_position is not None
            ]
            plan = plan_for(name, blocked)
            if plan[0] is None:
                feasible = False
                break
            route = plan[1]
            total_distance += sum(
                math.dist(first, second)
                for first, second in zip(route, route[1:])
            )
            occupied[name] = (targets[name].x, targets[name].y)
        if not feasible:
            continue
        # Preserve the original priority as a tie breaker, while allowing a
        # route-feasible order to move another robot first when necessary.
        priority_penalty = (
            0.0
            if priority_robot is None or order[0] == priority_robot
            else 0.25
        )
        score = (rally_approach_inversions(order, robot_positions, intent_routes),
                 total_distance + priority_penalty, order)
        if best is None or score < best[0]:
            best = (score, order)
    if best is not None:
        return list(best[1])
    # When current parked bodies prevent every complete serial plan, compare
    # future final-pose obstructions instead of filling the entrance first.
    # This chooses recovery priority only: live body/route admission is still
    # mandatory, including any safe refuge needed by the first mover.
    routes = intent_routes
    if len(routes) == len(names):
        def recovery_score(order):
            obstructions = sum(
                routes_conflict(routes[follower], ((targets[leader].x, targets[leader].y),),
                                min_separation=RALLY_DYNAMIC_CLEARANCE_M)
                for index, leader in enumerate(order) for follower in order[index + 1:])
            return (obstructions, priority_robot is not None and order[0] != priority_robot, order)
        return list(min(permutations(names), key=recovery_score))
    return rally_dispatch_order(
        targets, robot_positions, target, priority_robot
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
    visible_only=False,
    route_cache=None,
):
    """Plan a leg; a cache may be shared within one immutable planning snapshot."""
    if route_cache is None:
        route_cache = {}
    if not route_cache:
        traversable = traversable_grid(
            raw_grid, resolution, clearance_m=clearance_m
        )
        traversable = block_dynamic_positions(
            traversable, resolution, origin, blocked_positions
        )
        start = world_to_grid(
            robot_position[0],
            robot_position[1],
            resolution,
            origin[0],
            origin[1],
        )
        start, escape_route = navigation_start_route(
            raw_grid,
            traversable,
            start,
            max(1, math.ceil(0.6 / resolution)),
        )
        distance_data = (
            path_distance_grid(traversable, start, return_predecessors=True)
            if start is not None else None
        )
        route_cache["field"] = traversable, start, escape_route, distance_data
    traversable, start, escape_route, distance_data = route_cache["field"]
    target = world_to_grid(
        pose.x, pose.y, resolution, origin[0], origin[1]
    )
    if start is None:
        return None, ()
    waypoint, route = path_waypoint_route(
        traversable,
        start,
        target,
        max_distance_m / resolution,
        distance_data=distance_data,
    )
    if waypoint is None:
        return None, ()
    if visible_only:
        # Pull the path to its farthest clear waypoint; a grid-path bend can
        # temporarily occlude a nearer point even when a later point is clear.
        for candidate in reversed(route):
            direct = tuple(_line_cells(start, candidate))
            if all(traversable[cell] for cell in direct):
                waypoint, route = candidate, direct
                break
    x, y = grid_to_world(
        waypoint[0], waypoint[1], resolution, origin[0], origin[1]
    )
    world_route = tuple(
        grid_to_world(row, column, resolution, origin[0], origin[1])
        for row, column in (*escape_route[:-1], *route)
    )
    # The escape segment may traverse cells removed by static clearance
    # inflation. It must still keep clear of moving robot footprints; the
    # current pose is exempt because that is where the escape starts.
    if any(
        math.dist(point, blocked) < clearance_m
        for point in world_route[1:]
        for blocked in blocked_positions
    ):
        return None, ()
    return (
        RallyPose(
            x,
            y,
            pose.yaw if waypoint == target else route_arrival_yaw(
                world_route, math.atan2(pose.y - y, pose.x - x)
            ),
        ),
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


def remaining_rally_route(route, position):
    """Release travelled cells, retaining the live pose and remaining path.

    A deviation from the reserved path retains the old reservation, so a
    neighbouring robot cannot be admitted on a spurious nearest-point jump.
    """
    if not route or position is None:
        return route
    nearest = min(
        range(len(route)), key=lambda i: math.dist(position, route[i])
    )
    if math.dist(position, route[nearest]) > RALLY_PATH_CLEARANCE_M:
        return (position, *route)
    return (position, *route[nearest:])


def route_arrival_yaw(route, fallback_yaw):
    """Face along the actual incoming leg at a temporary stop, not across a wall."""
    if len(route) < 2:
        return fallback_yaw
    x, y = route[-1]
    # A short terminal chord avoids eight-connected single-cell yaw jumps.
    for previous_x, previous_y in reversed(route[:-1]):
        if math.dist((x, y), (previous_x, previous_y)) >= 0.3:
            break
    if math.dist((x, y), (previous_x, previous_y)) < 1e-6:
        return fallback_yaw
    return math.atan2(y - previous_y, x - previous_x)


def reserve_rally_prefix(plan, reservations, min_travel=0.75):
    """Allow approach to a conflict, stopping before the reserved corridor.

    Reservations include stationary endpoints. Thus a follower cannot plan
    through a stopped leader, and a crossing is released only after passage.
    """
    pose, route = plan
    if pose is None or not route:
        return None
    for index, point in enumerate(route):
        if not any(
            routes_conflict((point,), reserved) for reserved in reservations
        ):
            continue
        prefix = route[:index]
        if len(prefix) < 2 or math.dist(prefix[0], prefix[-1]) < min_travel:
            return None
        x, y = prefix[-1]
        return RallyPose(x, y, route_arrival_yaw(prefix, pose.yaw)), prefix
    return plan


def rally_leg_limit(attempts):
    return float("inf") if attempts == 0 else 1.5 / attempts


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


def motion_energy(distance_m, move_cost, idle_cost, path_factor, nominal_speed):
    """Conservative energy for moving a path and paying its travel time."""
    distance_m = max(0.0, float(distance_m)) * max(1.0, float(path_factor))
    return distance_m * float(move_cost) + (
        distance_m / float(nominal_speed) * float(idle_cost)
    )


def battery_assignment_required_energy(
    assignment_distance_m,
    home_distance_m,
    move_cost,
    idle_cost,
    path_factor,
    nominal_speed,
    safety_margin,
):
    """Budget navigation and the same conservative local return reserve."""
    task_cost = motion_energy(
        assignment_distance_m, move_cost, idle_cost, 1.25, nominal_speed
    )
    return_cost = motion_energy(
        home_distance_m, move_cost, idle_cost, path_factor, nominal_speed
    ) + float(safety_margin)
    return task_cost + return_cost


def battery_assignment_is_safe(
    energy, assignment_distance_m, home_distance_m, move_cost, idle_cost,
    path_factor, nominal_speed, safety_margin,
):
    return float(energy) > battery_assignment_required_energy(
        assignment_distance_m, home_distance_m, move_cost, idle_cost,
        path_factor, nominal_speed, safety_margin,
    )


def rally_wait_requirements(base, states, modes, travel_times, charge_times):
    """Reserve idle energy for other routes and serial returns/charges.

    A newly required charge increases the other robots' wait. Iterate this
    monotone set at most once per robot; the robot's own route/return is already
    included in its base budget. These are nominal planning estimates; the local
    battery reserve remains the safety authority.
    """
    charging = {name for name, mode in modes.items()
                if mode in ("RETURNING", "CHARGING")}
    requirements, waits = dict(base), {}
    for _ in range(len(base) + 1):
        for name, required in base.items():
            wait = sum(value for other, value in travel_times.items() if other != name)
            wait += sum(charge_times.get(other, 0.0) for other in charging if other != name)
            waits[name] = wait
            requirements[name] = required + float(states[name].get("idle_cost_per_sec", .02)) * wait
        needed = charging | {name for name in base
                             if float(states[name]["energy"]) <= requirements[name]}
        if needed == charging:
            break
        charging = needed
    return requirements, waits


def rally_stationary_positions(positions, robot_name, reserved_names):
    """Moving peers are protected by their live route, not a static detour mask."""
    return [position for name, position in positions.items()
            if name != robot_name and name not in reserved_names and position is not None]


def rally_priority_reservations(order, robot_name, routes, completed):
    """Keep followers from parking on an unfinished leader's later approach.

    These intent routes supplement live short-leg/body reservations; they never
    authorize motion through a stationary robot. Unknown leader geometry waits.
    """
    reservations = []
    for leader in order:
        if leader == robot_name:
            return reservations
        if leader in completed:
            continue
        route = routes.get(leader)
        if not route:
            return None
        reservations.append(route)
    return reservations


def rally_observation_guard(observer, source_time, now, modes, freshness_sec=TARGET_OBSERVER_FRESHNESS_SEC):
    """Keep the last live visual observer until a peer confirms a handoff."""
    if (observer not in modes or modes[observer] != "ACTIVE"
            or source_time is None or not math.isfinite(source_time)
            or not 0 <= now - source_time <= min(freshness_sec, TARGET_OBSERVER_FRESHNESS_SEC)
            or not any(name != observer and mode in ("ACTIVE", "RETURNING", "CHARGING")
                       for name, mode in modes.items())):
        return None
    return observer


def rally_energy_ready_order(order, energy_unready, modes):
    """Ready robots lead approaches; every safety return keeps its reservation."""
    return sorted(order, key=lambda name: (
        name in energy_unready or modes[name] != "ACTIVE"
    ))


def rally_return_reservations(grid, resolution, origin, positions, states, modes, pending):
    """Protect current and future serial safety returns before allowing rally progress.

    Unknown return geometry means wait. Charging robots retain their physical
    position; local safety still owns execution and can preempt network goals.
    """
    routes = {}
    names = set(pending) | {name for name, mode in modes.items()
                            if mode in ('RETURNING', 'CHARGING')}
    for name in names:
        if modes[name] == 'FAILED':
            continue
        position = positions.get(name)
        if position is None:
            return None
        if modes[name] == 'CHARGING':
            routes[name] = (position,)
            continue
        try:
            home = (float(states[name]['charge_x']), float(states[name]['charge_y']))
            if not all(math.isfinite(v) for v in home):
                return None
        except (KeyError, TypeError, ValueError):
            return None
        _, route = plan_rally_leg(RallyPose(*home, 0.), grid, resolution, origin, position)
        if not route:
            return None
        routes[name] = route
    return routes


class HeadquartersControl(Node):
    def __init__(self):
        super().__init__("headquarters_control")
        self.num_robots = self.declare_parameter("robot_count", 2).value
        self.return_probe_paused = self.declare_parameter(
            "enable_return_probe_pause", False
        ).value
        if self.return_probe_paused:
            if not self.get_parameter("use_sim_time").value:
                raise ValueError("Return probe pause is simulation-only")
            signal.signal(signal.SIGUSR2, self.resume_return_probe)
        self.goal_timeout_sec = self.declare_parameter(
            "goal_timeout_sec", 60.0
        ).value
        self.rally_goal_timeout_sec = self.declare_parameter(
            "rally_goal_timeout_sec", RALLY_GOAL_TIMEOUT_SEC
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
        self.message_freshness_timeout_sec = self.declare_parameter(
            "message_freshness_timeout_sec", 5.0
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
        self.rally_assignment_objective = self.declare_parameter(
            "rally_assignment_objective", "minimax"
        ).value
        self.use_map_safe_rally_order = self.declare_parameter(
            "use_map_safe_rally_order", True
        ).value
        self.global_battery_rally_pause = self.declare_parameter(
            "global_battery_rally_pause", False
        ).value
        self.rally_max_concurrent = self.declare_parameter(
            "rally_max_concurrent", RALLY_MAX_CONCURRENT
        ).value
        if (
            self.num_robots < 1
            or self.rally_position_tolerance <= 0
            or self.rally_linear_tolerance < 0
            or self.rally_angular_tolerance < 0
            or self.rally_hold_sec <= 0
            or self.rally_goal_timeout_sec <= 0
            or self.rally_max_retries < 0
            or self.rally_assignment_objective not in ("minimax", "total_path")
            or self.rally_max_concurrent < 1
        ):
            raise ValueError("invalid robot or rally parameters")

        self.map_data = None
        self.source_map_data = None
        self.map_self_return_cells = {}
        self.resolution = None
        self.origin = None
        self.map_width = None
        self.map_height = None
        self.map_known_count = 0
        self.frontier_cache = None
        self.map_received_at = None
        self.last_no_assignment_log = -float("inf")
        self.last_save_time = time.monotonic()
        self.save_in_progress = False
        self.target_history = []
        self.bad_targets = []

        state_qos = QoSProfile(depth=1)
        state_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        state_qos.reliability = ReliabilityPolicy.RELIABLE
        self.consumed_publisher = self.create_publisher(
            String, "/gateway/consumed", 100
        )
        self.task_state_publisher = self.create_publisher(
            String, "/task_state", state_qos
        )
        self.rally_assignment_publisher = self.create_publisher(
            String, "/rally_assignments", state_qos
        )
        failure_qos = QoSProfile(
            depth=self.num_robots,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.robot_failure_publisher = self.create_publisher(
            String, "/robot_failure", failure_qos
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
        self.last_input_availability = None
        self.last_input_diagnostic_at = -float("inf")
        self.target = None
        self.target_received_source_time = None
        self.target_observing_robot = None
        self.target_view_distance = 3.0
        self.target_view_fov_rad = math.pi / 2
        self.rally_observer_guard = None
        self.detecting_robot = None
        self.rally_targets = {}
        self.rally_final_targets = {}
        self.rally_yield_targets = set()
        self.rally_recovery_beneficiaries = {}
        self.return_yield_targets = {}
        self.rally_probe_targets = set()
        self.rally_probe_robot = None
        self.rally_goal_handles = {}
        self.rally_goal_pending = {}
        self.rally_goal_started_at = {}
        self.rally_leg_routes = {}
        self.rally_leg_poses = {}
        self.rally_route_unavailable_since = {}
        self.rally_recovery_requested = {}
        self.rally_yield_requested = {}
        self.rally_battery_preempted = {}
        self.rally_charge_requested = {}
        self.exploration_charge_budgets = {}
        self.successful_exploration_legs = {}
        self.rally_precharge_staging = {}
        self.rally_detour_budgets = {}
        self.rally_wait_budgets = {}
        self.rally_preflight_complete = False
        self.rally_precharge_active = False
        self.charge_request_publishers = {}
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
        self.target_scan_robot = None
        self.target_scan_handle = None
        self.target_scan_cancel_requested = False
        self.target_scan_steps = {}
        self.target_scan_next_robot = None
        self.target_search_active = False
        self.target_search_visits = []
        self.target_search_basis = "current_map_frontiers"
        self.survey_goal_started_at = None
        self.survey_attempts = 0
        self.survey_dispatch_cursor = 0
        self.survey_robot = None
        self.survey_battery_preempted = False
        self.survey_cancel_requested = False

        self.map_sub = self.create_subscription(
            OccupancyGrid, "/merge_map", self.map_callback, 10
        )
        self.robot_positions = {}
        self.robot_yaws = {}
        self.map_to_odom = {}
        self.robot_maps = {}
        self.robot_odom_received_at = {}
        self.robot_tf_received_at = {}
        self.robot_map_received_at = {}
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
        self.exploration_resume_intents = {}
        self.cancel_requested = {}
        self.robot_subscriptions = []

        for index in range(self.num_robots):
            robot_name = f"tb{index + 1}"
            self.charge_request_publishers[robot_name] = self.create_publisher(
                String, f"/gateway/request/{robot_name}/charge", 10
            )
            self.robot_positions[robot_name] = None
            self.robot_yaws[robot_name] = None
            self.map_to_odom[robot_name] = None
            self.robot_maps[robot_name] = None
            self.robot_odom_received_at[robot_name] = None
            self.robot_tf_received_at[robot_name] = None
            self.robot_map_received_at[robot_name] = None
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
            self.rally_route_unavailable_since[robot_name] = None
            self.rally_recovery_requested[robot_name] = False
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

    def resume_return_probe(self, _signal=None, _frame=None):
        # Only enabled for the owned supplemental fixture. Keep DDS and all
        # received-state callbacks alive while mission dispatch is paused.
        self.return_probe_paused = False

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

    def participating_robots(self):
        """Robots that still belong to the current mission."""
        return [
            name for name in self.robot_positions
            if self.battery_modes[name] != "FAILED"
        ]

    def input_robot_names(self):
        return [
            name for name in self.robot_positions
            if self.battery_modes[name] in ("ACTIVE", "UNKNOWN")
        ]

    def active_batteries_ready(self):
        names = self.participating_robots()
        return bool(names) and all(
            self.battery_modes[name] == "ACTIVE" for name in names
        )

    def active_inputs_ready(self):
        names = self.input_robot_names()
        return all(
            self.robot_positions[name] is not None
            and self.robot_maps[name] is not None
            for name in names
        )

    def exploration_battery_factor(self, robot_name, distance_m, destination):
        """Weight trip budgets; frontier admission separately requests charging."""
        if not self.enable_battery:
            return 1.0
        required = HeadquartersControl.exploration_required_energy(
            self, robot_name, distance_m, destination)
        if required is None:
            return 0.0
        energy = float(self.battery_states[robot_name]['energy'])
        return 1.0 if energy > required else .25 * energy / required if required > 0 else 0.0

    def exploration_required_energy(self, robot_name, distance_m, destination):
        """Price the whole current frontier approach and endpoint return reserve."""
        if self.battery_modes[robot_name] != "ACTIVE":
            return None
        state = self.battery_states[robot_name]
        position = self.robot_positions.get(robot_name)
        if position is None or "energy" not in state:
            return None
        try:
            home = (float(state["charge_x"]), float(state["charge_y"]))
            energy = float(state["energy"])
            move = float(state.get("move_cost_per_m", 1.0))
            idle = float(state.get("idle_cost_per_sec", .02))
            factor = float(state.get("return_path_factor", 2.0))
            speed = float(state.get("nominal_speed_mps", .18))
            margin = float(state.get("return_safety_margin", 8.0))
            if (not all(math.isfinite(v) for v in (*home, *position, *destination,
                    energy, distance_m, move, idle, factor, speed, margin))
                    or min(energy, distance_m, move, idle, margin) < 0
                    or speed <= 0 or factor < 1):
                return None
            required = battery_assignment_required_energy(
                distance_m, max(math.dist(position, home), math.dist(destination, home)),
                move, idle, factor, speed, margin,
            )
            if not math.isfinite(required):
                return None
            return required
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None

    def exploration_charge_budget(self, name, assignment, allow_opportunity=False):
        """Return a valid frontier budget that charging can actually fund."""
        required = HeadquartersControl.exploration_required_energy(
            self, name, assignment.path_distance_m, (assignment.x, assignment.y))
        if required is None:
            return None
        state = self.battery_states[name]
        try:
            energy = float(state['energy'])
            capacity = float(state['capacity'])
            fraction = float(state['charge_target_fraction'])
            charge_target = capacity * fraction
            home = (float(state['charge_x']), float(state['charge_y']))
            if (not all(math.isfinite(v) for v in (energy, capacity, fraction, charge_target, *home))
                    or not 0 < fraction <= 1 or capacity <= 0
                    or not required < charge_target):
                return None
            if energy > required:
                # A low battery passing home can avoid a later distant return.
                # Require real exploration first; never top up at initial spawn.
                radius = float(state.get('charge_radius_m', 0.0))
                if (not allow_opportunity
                        or self.task_state not in ('EXPLORE', 'FOUND_UNCONFIRMED')
                        or not getattr(self, 'successful_exploration_legs', {}).get(name, 0)
                        or energy > .25 * charge_target
                        or not math.isfinite(radius) or radius <= .2
                        or not PATH_CLEARANCE_M < math.dist(self.robot_positions[name], home) <= 2. * radius):
                    return None
                leg, _ = plan_rally_leg(
                    RallyPose(*home, 0.0), self.map_data, self.resolution, self.origin,
                    self.robot_positions[name], 2. * radius,
                    blocked_positions=[p for peer, p in self.robot_positions.items()
                                       if peer != name and p is not None],
                    clearance_m=PATH_CLEARANCE_M, visible_only=True,
                )
                if leg is None or math.dist((leg.x, leg.y), home) > radius - .2:
                    return None
                required = max(required, .25 * charge_target)
            if energy > required:
                return None
            return energy, required, home
        except (KeyError, TypeError, ValueError):
            return None

    def request_exploration_charge(self, candidates):
        """Charge one idle robot for an otherwise admissible current frontier.

        Call after a needed idle peer has no funded admission and live actions
        drain. New funded work must not starve a peer's charging window.
        Reuse the rally return owner so a phase change cannot admit traffic for
        a robot whose gateway charge request is still pending.
        """
        if (not self.enable_battery or not self.fresh_robot_inputs()
                or self.task_state not in ('EXPLORE', 'FOUND_UNCONFIRMED', 'FOUND', 'RALLY')
                or any(mode in ('RETURNING', 'CHARGING') for mode in self.battery_modes.values())
                or any(state == 'active' for state in self.robot_states.values())):
            return False
        choices = []
        for name, assignment in candidates:
            if self.rally_charge_requested and name not in self.rally_charge_requested:
                continue
            budget = HeadquartersControl.exploration_charge_budget(
                self, name, assignment, allow_opportunity=True)
            if budget is None:
                continue
            energy, required, home = budget
            choices.append((math.dist(self.robot_positions[name], home),
                            -assignment.utility, name, assignment, energy, required))
        if not choices:
            return False
        _, _, name, assignment, energy, required = min(choices, key=lambda choice: choice[:3])
        now = self.now()
        if now - self.rally_charge_requested.get(name, -float('inf')) < 2.0:
            return True
        self.rally_charge_requested[name] = now
        self.exploration_charge_budgets[name] = required
        self.exploration_resume_intents[name] = (
            assignment.x, assignment.y, assignment.viewpoint.information_gain)
        self.charge_request_publishers[name].publish(String(data=json.dumps({
            'robot': name, 'stamp_sec': now, 'task_phase': self.task_state,
            'reason': 'exploration_energy_budget', 'required_energy': required,
            'available_energy': energy,
        }, sort_keys=True)))
        self.consumed_publisher.publish(String(data=json.dumps({
            'event': 'coordinator_charge_decision', 'event_time': now,
            'robot': name, 'task_phase': self.task_state,
            'required_energy': required, 'available_energy': energy,
            'frontier_position': [assignment.x, assignment.y],
            'inputs': {key: sample for key, sample in self.input_freshness_details().items()
                       if key != 'headquarters/target_detection'},
        }, sort_keys=True)))
        self.get_logger().warn(
            f'Requesting early exploration charge for {name}: energy={energy:.2f}, '
            f'whole_frontier_budget={required:.2f}.')
        return True

    def target_observation_callback(self, message):
        if self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED"):
            return
        if message.data in ("EXPLORE", "FOUND_UNCONFIRMED"):
            self.publish_task_state(message.data)

    def fresh_target(self):
        stamp = self.target_received_source_time
        return stamp is not None and 0 <= self.now() - stamp <= TARGET_DETECTION_TTL_SEC

    def stop_target_scan(self):
        """Drain a blind scan before resuming a freshly confirmed mission."""
        if self.target_scan_robot is None:
            return False
        if not self.target_scan_cancel_requested:
            self.target_scan_cancel_requested = True
            if self.target_scan_handle is not None:
                self.target_scan_handle.cancel_goal_async()
        return True  # A late action response must also be drained.

    def reacquire_target_by_scanning(self):
        """Look around current safe poses; never aim using the expired target."""
        if getattr(self, "target_search_active", False):
            return
        if self.target_scan_robot is not None:
            if self.battery_modes[self.target_scan_robot] != "ACTIVE":
                self.stop_target_scan()
            return
        if (not self.fresh_robot_inputs() or any(
                mode == "RETURNING" for mode in self.battery_modes.values())
                or any(self.goal_handles.values())
                or any(state == "active" for state in self.robot_states.values())
                or any(self.rally_goal_handles.values())
                or any(self.rally_goal_pending.values())
                or self.survey_goal_handle is not None or self.survey_goal_pending):
            return
        for name in sorted(self.participating_robots(), key=lambda candidate:
                           candidate != getattr(self, "target_scan_next_robot", None)):
            if self.battery_modes[name] != "ACTIVE":
                continue
            if self.target_scan_steps.get(name, 0) >= 4:
                continue
            position = self.robot_positions.get(name)
            if position is None:
                continue
            cell = world_to_grid(*position, self.resolution, *self.origin)
            if not (0 <= cell[0] < self.map_data.shape[0]
                    and 0 <= cell[1] < self.map_data.shape[1]) or self.map_data[cell] != 0:
                continue
            client = self.robot_nav_clients[name]
            if not client.server_is_ready():
                continue
            # Four absolute headings cover a full turn independently of the
            # old target position, last detector or target-directed routes.
            yaw = self.target_scan_steps.get(name, 0) * math.pi / 2
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = "map"
            goal.pose.header.stamp = self.get_clock().now().to_msg()
            goal.pose.pose.position.x, goal.pose.pose.position.y = position
            goal.pose.pose.orientation.z = math.sin(yaw / 2)
            goal.pose.pose.orientation.w = math.cos(yaw / 2)
            self.target_scan_robot = name
            self.target_scan_cancel_requested = False
            self.record_navigation_decision(name, "target_reacquisition_scan", goal.pose)
            client.send_goal_async(goal).add_done_callback(self.target_scan_response)
            self.get_logger().info(f"Scanning {name}'s current pose for a fresh target confirmation.")
            return

    def target_scan_response(self, future):
        try:
            handle = future.result()
        except Exception as error:
            self.get_logger().warning(f"Target scan request failed: {error}")
            self.finish_target_scan()
            return
        if handle is None or not handle.accepted:
            self.finish_target_scan()
            return
        self.target_scan_handle = handle
        if (self.target_scan_cancel_requested or self.fresh_target()
                or self.task_state not in ("FOUND", "RALLY")
                or self.battery_modes[self.target_scan_robot] != "ACTIVE"):
            self.target_scan_cancel_requested = True
            handle.cancel_goal_async()
        handle.get_result_async().add_done_callback(self.target_scan_result)

    def target_scan_result(self, future):
        try:
            future.result()
        except Exception as error:
            self.get_logger().warning(f"Target scan result failed: {error}")
        self.finish_target_scan()

    def finish_target_scan(self):
        name = self.target_scan_robot
        if name is not None:
            self.target_scan_steps[name] = self.target_scan_steps.get(name, 0) + 1
            if self.target_scan_steps[name] >= 4:
                # Looking around cannot rediscover a target outside sensor
                # range. Continue the ordinary fresh-map frontier search,
                # without rolling back mission phase or using old target data.
                self.target_search_active = True
                self.target_scan_next_robot = None
        self.target_scan_robot = None
        self.target_scan_handle = None
        self.target_scan_cancel_requested = False

    def stop_target_search(self):
        """Drain accepted and pending frontier actions before resuming rally."""
        active = False
        for name, state in self.robot_states.items():
            if state != "active":
                continue
            active = True
            handle = self.goal_handles[name]
            if handle is not None and not self.cancel_requested[name]:
                self.cancel_requested[name] = True
                handle.cancel_goal_async()
        if not active:
            self.target_search_active = False
            self.target_scan_steps.clear()
            self.target_scan_next_robot = None
            self.target_search_visits.clear()
        return active

    def target_detection_callback(self, message):
        if self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED", "FOUND", "RALLY"):
            return
        try:
            event = json.loads(message.data)
            target = (float(event["target_x"]), float(event["target_y"]))
            gateway = event["_gateway"]
            stamp = float(gateway["source_time"])
            if (not all(math.isfinite(value) for value in (*target, stamp))
                    or not 0 <= self.now() - stamp <= TARGET_DETECTION_TTL_SEC):
                return
            if self.target_received_source_time is not None and stamp <= self.target_received_source_time:
                return
            # This task uses a stationary target. Renew its source lease only
            # from a newly delivered observation of the same physical target.
            if self.target is not None and target != self.target:
                self.get_logger().error("Changed target requires a new task episode.")
                return
            robot = str(event["robot"])
            view_distance = float(event.get("max_distance_m", 3.0))
            if not math.isfinite(view_distance) or view_distance <= 0:
                raise ValueError("invalid detector range")
            view_fov = math.radians(float(event.get("field_of_view_deg", 90.0)))
            if not math.isfinite(view_fov) or not 0 < view_fov <= 2 * math.pi:
                raise ValueError("invalid detector field of view")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.get_logger().error(f"Invalid target detection: {error}")
            return
        initial = self.task_state in ("EXPLORE", "FOUND_UNCONFIRMED")
        self.target = target
        self.target_received_source_time = stamp
        self.target_observing_robot = robot
        self.target_view_distance = view_distance
        self.target_view_fov_rad = view_fov
        if initial:
            self.detecting_robot = robot
        self.consumed_publisher.publish(String(data=json.dumps({
            **gateway, "event": "consumed" if initial else "target_reconfirmed",
            "message_type": "target_detection",
            "robot": robot,
            "consumed_time": max(self.now(), gateway.get("delivery_time", self.now())),
            "local_confirm_time": event.get("stamp_sec"),
        }, sort_keys=True)))
        if not initial:
            return
        self.publish_task_state("FOUND")
        if not self.enable_rally:
            return
        self.rally_prepare_started_at = self.now()
        self.get_logger().info(
            f"Preparing rally around target {self.target}."
        )

    def battery_failure_callback(self, message):
        reason, separator, robot_name = message.data.partition(":")
        if separator and robot_name in self.battery_modes:
            self.mark_robot_failed(robot_name, reason)
        else:
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
        self.battery_states[robot_name] = event
        self.battery_state_received_at[robot_name] = event.get("stamp_sec", self.now())
        if mode == "FAILED":
            self.battery_modes[robot_name] = previous
            self.mark_robot_failed(
                robot_name,
                event.get("failure_reason", "battery_failure"),
            )
            return
        self.battery_modes[robot_name] = mode
        if mode not in ("RETURNING", "CHARGING"):
            # Target discovery may move the mission to RALLY while an earlier
            # exploration charge request is lost. A new ACTIVE source after
            # its lease ends proves it can no longer initiate a local return.
            pending = self.rally_charge_requested.get(robot_name)
            source = self.battery_state_received_at[robot_name]
            if (mode == 'ACTIVE' and robot_name in getattr(self, 'exploration_charge_budgets', {})
                    and pending is not None and isinstance(source, (int, float))
                    and math.isfinite(source) and source >= pending + CHARGE_REQUEST_TTL_SEC
                    and self.now() - pending >= CHARGE_REQUEST_TTL_SEC):
                self.rally_charge_requested.pop(robot_name, None)
                self.exploration_charge_budgets.pop(robot_name, None)
            if mode == "ACTIVE" and previous != "ACTIVE":
                self.rally_charge_requested.pop(robot_name, None)
                getattr(self, 'exploration_charge_budgets', {}).pop(robot_name, None)
                self.rally_precharge_staging.pop(robot_name, None)
                getattr(self, "rally_detour_budgets", {}).pop(robot_name, None)
                self.get_logger().info(
                    f"{robot_name} resumed after charging."
                )
            return

        goal_handle = self.goal_handles[robot_name]
        if goal_handle is not None and not self.cancel_requested[robot_name]:
            self.battery_preempted[robot_name] = True
            self.cancel_requested[robot_name] = True
            goal_handle.cancel_goal_async()
        if mode == "RETURNING":
            # Return routes are owned locally and have no central frontier
            # reservation. Drain other exploration actions before admitting
            # more traffic; a pending response is canceled on acceptance too.
            for other_name, other_handle in self.goal_handles.items():
                if other_name == robot_name or other_handle is None:
                    continue
                if not self.cancel_requested[other_name]:
                    self.battery_preempted[other_name] = True
                    self.cancel_requested[other_name] = True
                    other_handle.cancel_goal_async()
        rally_handle = self.rally_goal_handles[robot_name]
        if rally_handle is not None:
            self.rally_battery_preempted[robot_name] = True
            rally_handle.cancel_goal_async()
        if (self.task_state == "RALLY" and self.global_battery_rally_pause
                and mode == "RETURNING" and previous != mode):
            self.get_logger().warn(
                f"Pausing other rally legs while {robot_name} returns to charge."
            )
            for other_name, other_handle in self.rally_goal_handles.items():
                if other_handle is None or other_name == robot_name:
                    continue
                if self.rally_battery_preempted[other_name]:
                    continue
                self.rally_battery_preempted[other_name] = True
                other_handle.cancel_goal_async()
        if (self.survey_robot == robot_name or mode == "RETURNING") and (
            getattr(self, 'survey_goal_handle', None) is not None or getattr(self, 'survey_goal_pending', False)
        ):
            self.survey_battery_preempted = True
            self.survey_cancel_requested = True
            if self.survey_goal_handle is not None:
                self.survey_goal_handle.cancel_goal_async()

    def mark_robot_failed(self, robot_name, reason):
        if robot_name not in self.battery_modes:
            self.fail_task(f"unknown_robot_failure:{robot_name}")
            return
        already_failed = self.battery_modes[robot_name] == "FAILED"
        self.battery_modes[robot_name] = "FAILED"
        self.robot_states[robot_name] = "failed"
        self.battery_preempted[robot_name] = True
        goal_handle = self.goal_handles[robot_name]
        if goal_handle is not None:
            self.cancel_requested[robot_name] = True
            goal_handle.cancel_goal_async()
        rally_handle = self.rally_goal_handles[robot_name]
        if rally_handle is not None:
            self.rally_battery_preempted[robot_name] = True
            rally_handle.cancel_goal_async()
        if self.survey_robot == robot_name and self.survey_goal_handle is not None:
            self.survey_battery_preempted = True
            self.survey_cancel_requested = True
            self.survey_goal_handle.cancel_goal_async()

        self.rally_targets.pop(robot_name, None)
        self.rally_charge_requested.pop(robot_name, None)
        getattr(self, 'exploration_charge_budgets', {}).pop(robot_name, None)
        self.rally_precharge_staging.pop(robot_name, None)
        self.rally_final_targets.pop(robot_name, None)
        self.rally_arrived.pop(robot_name, None)
        self.rally_dispatch_order = [
            name for name in self.rally_dispatch_order if name != robot_name
        ]
        self.rally_yield_targets.discard(robot_name)
        getattr(self, "rally_recovery_beneficiaries", {}).pop(robot_name, None)
        self.return_yield_targets.pop(robot_name, None)
        self.rally_probe_targets.discard(robot_name)
        if self.rally_probe_robot == robot_name:
            self.rally_probe_robot = None
        if not already_failed:
            event = String()
            event.data = json.dumps({
                "robot": robot_name,
                "reason": reason,
                # Every event carries the irreversible isolation snapshot so
                # a late subscriber can recover even from only the last event.
                "failed_robots": sorted(
                    name for name, mode in self.battery_modes.items()
                    if mode == "FAILED"
                ),
                "remaining_robots": self.participating_robots(),
                "task_state": self.task_state,
            }, sort_keys=True)
            self.robot_failure_publisher.publish(event)
            self.get_logger().error(
                f"Isolating failed robot {robot_name}: {reason}; "
                f"remaining={self.participating_robots()}"
            )
        if not self.participating_robots():
            self.fail_task("all_robots_failed")
        elif self.task_state == "RALLY":
            self.publish_rally_assignments()

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
                "required_robot_count": len(self.rally_targets),
                "failed_robots": [
                    name for name, mode in self.battery_modes.items()
                    if mode == "FAILED"
                ],
                "poses": {
                    name: {"x": pose.x, "y": pose.y, "yaw": pose.yaw}
                    for name, pose in self.rally_targets.items()
                },
            },
            sort_keys=True,
        )
        self.rally_assignment_publisher.publish(message)

    def fail_task(self, reason):
        if self.task_state in ("COMPLETE", "PARTIAL_COMPLETE", "FAILED"):
            return
        message = String()
        message.data = reason
        self.task_failure_publisher.publish(message)
        self.publish_task_state("FAILED")
        self.get_logger().error(f"Mission failed: {reason}")

    def release_return_yields(self):
        """Keep the refuge until its charged returner can depart on a reserved leg."""
        released = False
        for name, returning in list(self.return_yield_targets.items()):
            mode = self.battery_modes[returning]
            if mode not in ("ACTIVE", "FAILED"):
                continue
            if (mode == "ACTIVE" and not (
                    self.rally_goal_handles.get(returning) is not None
                    or self.rally_goal_pending.get(returning, False)
                    or self.rally_arrived.get(returning, False))):
                continue
            if (not self.rally_arrived[name] or self.rally_goal_handles[name] is not None
                    or self.rally_goal_pending[name]):
                continue
            self.rally_targets[name] = self.rally_final_targets[name]
            self.rally_yield_targets.discard(name)
            getattr(self, "rally_recovery_beneficiaries", {}).pop(name, None)
            del self.return_yield_targets[name]
            self.rally_arrived[name] = False
            self.rally_route_unavailable_since[name] = None
            released = True
        if released:
            self.publish_rally_assignments()

    def preempt_rally_return_conflicts(self, protected):
        """Revalidate admitted legs when independent local returns appear.

        A pending gateway request retains this flag until its late acceptance.
        An escape already certified for its returner may continue clearing that
        corridor, but must still respect every other return reservation.
        """
        for name, handle in self.rally_goal_handles.items():
            if (self.battery_modes[name] != "ACTIVE"
                    or not (handle is not None or self.rally_goal_pending[name])
                    or self.rally_yield_requested[name]):
                continue
            route = remaining_rally_route(
                self.rally_leg_routes[name], self.robot_positions[name])
            escape_for = self.return_yield_targets.get(name)
            if protected is not None and route and not any(
                routes_conflict(route, reserved)
                for returning, reserved in protected.items()
                if returning not in (name, escape_for)
            ):
                continue
            self.rally_yield_requested[name] = True
            self.get_logger().warn(
                f"Canceling {name} rally leg for a fresh safety-return corridor.")
            if handle is not None:
                handle.cancel_goal_async()

    def yield_to_returning_robot(self):
        """Drain conflicting legs and move idle blockers off local returns."""
        if not self.fresh_robot_inputs():
            return
        if not any(mode == 'RETURNING' for mode in self.battery_modes.values()):
            return
        protected = rally_return_reservations(
            self.map_data, self.resolution, self.origin, self.robot_positions,
            self.battery_states, self.battery_modes,
            set(self.rally_charge_requested),
        )
        # Pending return requests constrain new admission, but cannot
        # revoke an existing safe escape. Only actual local returns/charging
        # acquire priority over an already admitted ordinary leg.
        actual_returns = {
            name: route for name, route in protected.items()
            if self.battery_modes[name] in ("RETURNING", "CHARGING")
        } if protected is not None else rally_return_reservations(
            self.map_data, self.resolution, self.origin, self.robot_positions,
            self.battery_states, self.battery_modes, set())
        HeadquartersControl.preempt_rally_return_conflicts(self, actual_returns)
        if protected is None:
            protected = actual_returns
            if protected is None:
                return
        if self.survey_goal_handle is not None or self.survey_goal_pending:
            return
        active_routes = [remaining_rally_route(self.rally_leg_routes[name],
                                               self.robot_positions[name])
                         for name, handle in self.rally_goal_handles.items()
                         if handle is not None or self.rally_goal_pending[name]]
        if len(active_routes) >= self.rally_max_concurrent:
            return
        now = self.now()
        if now - getattr(self, 'last_return_yield_attempt_at', -float('inf')) < 1.:
            return
        self.last_return_yield_attempt_at = now
        return_clearance = max(RALLY_ROUTE_SEPARATION_M,
            max((float(self.battery_states.get(name, {}).get('charge_radius_m', .8))
                 for name in protected), default=.8) + RALLY_DYNAMIC_CLEARANCE_M)
        for returning in self.rally_dispatch_order:
            if self.battery_modes[returning] != "RETURNING":
                continue
            state = self.battery_states[returning]
            if "charge_x" not in state or "charge_y" not in state:
                continue
            home = RallyPose(float(state["charge_x"]), float(state["charge_y"]), 0.0)
            route = protected.get(returning)
            if not route:
                continue
            for name in self.rally_dispatch_order:
                position = self.robot_positions[name]
                if (name == returning or self.battery_modes[name] != "ACTIVE"
                        or position is None
                        or self.rally_goal_handles[name] is not None
                        or self.rally_goal_pending[name]):
                    continue
                if not routes_conflict((position,), route, RALLY_ROUTE_SEPARATION_M):
                    continue
                blocked = [p for other, p in self.robot_positions.items()
                           if other != name and p is not None]
                refuge = rally_yield_pose(
                    self.map_data, self.resolution, self.origin, position,
                    (home.x, home.y), blocked_positions=blocked,
                    reserved_routes=(*active_routes, *(path for other, path in protected.items() if other != name)),
                    route_separation_m=return_clearance,
                    visible_only=True,
                )
                if refuge is None:
                    continue
                plan = plan_rally_leg(
                    refuge, self.map_data, self.resolution, self.origin,
                    position, MAX_NAVIGATION_LEG_M, blocked, visible_only=True,
                )
                if plan[0] is None:
                    continue
                if any(routes_conflict(plan[1], live) for live in active_routes):
                    continue
                if any(routes_conflict(((plan[0].x, plan[0].y),), other_route,
                        return_clearance)
                       for other, other_route in protected.items() if other != name):
                    continue
                self.rally_targets[name] = refuge
                self.rally_yield_targets.add(name)
                self.return_yield_targets[name] = returning
                self.rally_recovery_beneficiaries.pop(name, None)
                self.rally_arrived[name] = False
                self.rally_attempts[name] = 0
                self.publish_rally_assignments()
                self.get_logger().info(f"Yielding {name} out of {returning}'s return corridor.")
                self.send_rally_goal(name, plan)
                return

    def update_mission(self):
        if getattr(self, "return_probe_paused", False):
            return
        state_ready = self.fresh_robot_inputs()
        target_ready = self.task_state not in ("FOUND", "RALLY") or self.fresh_target()
        ready = state_ready and target_ready
        if ready != self.last_input_availability:
            self.last_input_availability = ready
            self.consumed_publisher.publish(String(data=json.dumps({
                "event": "coordinator_recovered" if ready else "coordinator_wait",
                "event_time": self.now(), "task_phase": self.task_state,
                "reason": "fresh_inputs" if ready else "stale_state",
                "required_robots": self.input_robot_names(),
            }, sort_keys=True)))
        if not ready and self.now() - self.last_input_diagnostic_at >= 5.0:
            self.last_input_diagnostic_at = self.now()
            details = self.input_freshness_details()
            self.consumed_publisher.publish(String(data=json.dumps({
                "event": "coordinator_stale_inputs", "event_time": self.now(),
                "task_phase": self.task_state, "inputs": details,
            }, sort_keys=True)))
            self.get_logger().warning(
                "Waiting for fresh gateway inputs: " + json.dumps(details, sort_keys=True)
            )
        if self.enable_battery and self.task_state not in (
            "COMPLETE", "PARTIAL_COMPLETE", "FAILED"
        ):
            now = self.now()
            if self.battery_monitor_started_at is None:
                self.battery_monitor_started_at = now
            if now - self.battery_monitor_started_at >= 20.0:
                unavailable = unavailable_battery_states(
                    {
                        name: timestamp
                        for name, timestamp in self.battery_state_received_at.items()
                        if self.battery_modes[name] != "FAILED"
                    },
                    now,
                    20.0,
                )
                if unavailable:
                    # Silence proves loss of contact, not a physical failure.
                    # Keep the robot in the required set and its occupied space;
                    # only delivered explicit failure may isolate it.
                    self.rally_hold_started_at = None
                    return
        # A stationary SLAM map need not be regenerated to prove that robots
        # have stopped at their assigned poses. New routes still require all
        # fresh inputs below; completion and live yielding require fresh poses.
        if (
            self.task_state == "FOUND" and not self.fresh_robot_inputs()
            or self.task_state == "RALLY" and not self.fresh_robot_poses()
            or self.enable_battery and unavailable_battery_states(
                {name: self.battery_state_received_at[name] for name in self.participating_robots()},
                self.now(), min(self.message_freshness_timeout_sec, STATE_TTL_SEC["battery_state"]),
            )
        ):
            self.rally_hold_started_at = None
            return
        if not target_ready:
            self.rally_hold_started_at = None
            # A stale target blocks mission decisions, never local battery
            # safety or an off-route refuge for a robot already returning.
            if state_ready and self.task_state == "RALLY":
                self.yield_to_returning_robot()
            if state_ready:
                self.reacquire_target_by_scanning()
            return
        if self.task_state in ("FOUND", "RALLY") and self.stop_target_scan():
            self.rally_hold_started_at = None
            return
        if getattr(self, "target_search_active", False) and self.stop_target_search():
            self.rally_hold_started_at = None
            return
        if self.task_state == "FOUND" and self.enable_rally:
            for name, handle in self.goal_handles.items():
                if handle is not None and not self.cancel_requested[name]:
                    self.cancel_requested[name] = True
                    handle.cancel_goal_async()
            if not all(
                state in ("idle", "failed")
                for name, state in self.robot_states.items()
                if name in self.participating_robots() or state == "failed"
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
                self.survey_cancel_requested = True
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
                        for name, position in self.robot_positions.items()
                        if name in self.participating_robots()
                    )
                ):
                    return
                if now - self.last_rally_assignment_attempt < 1.0:
                    return
                self.last_rally_assignment_attempt = now
                active_names = self.participating_robots()
                active_positions = {
                    name: self.robot_positions[name] for name in active_names
                }
                # Assign returning robots from their known charging pose.
                # This is future route intent, never a received current pose.
                # RALLY still reserves their actual body/return corridor and
                # dispatches only ACTIVE robots after the energy preflight.
                for name in active_names:
                    if self.battery_modes[name] in ("RETURNING", "CHARGING"):
                        try:
                            state = self.battery_states[name]
                            home = (float(state["charge_x"]), float(state["charge_y"]))
                            if not all(math.isfinite(v) for v in home):
                                return
                        except (KeyError, TypeError, ValueError):
                            return
                        active_positions[name] = home
                self.rally_targets = assign_rally_poses(
                    self.map_data,
                    self.resolution,
                    self.origin,
                    active_positions,
                    self.target,
                    objective=self.rally_assignment_objective,
                    battery_states=self.battery_states if self.enable_battery else None,
                    observer_robot=getattr(self, "target_observing_robot", None),
                    current_positions=self.robot_positions,
                    hold_sec=self.rally_hold_sec,
                )
                self.rally_final_targets = dict(self.rally_targets)
                if len(self.rally_targets) != len(active_names):
                    if not self.active_batteries_ready():
                        return  # Surveys do not reserve independent returns.
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
                    survey_order = rotate_robot_order(
                        survey_robot_order(
                            active_positions, self.detecting_robot
                        ),
                        self.survey_dispatch_cursor,
                    )
                    for survey_robot in survey_order:
                        if self.battery_modes[survey_robot] != "ACTIVE":
                            continue
                        survey_pose = rally_survey_pose(
                            self.map_data,
                            self.resolution,
                            self.origin,
                            self.robot_positions[survey_robot],
                            self.target,
                        )
                        if survey_pose is not None and self.send_survey_goal(survey_robot, survey_pose):
                            return
                    if (
                        self.rally_prepare_started_at is not None
                        and now - self.rally_prepare_started_at
                        < RALLY_ASSIGNMENT_WAIT_SEC
                    ):
                        return
                    self.fail_task("insufficient_rally_poses")
                    return
                if self.use_map_safe_rally_order:
                    self.rally_dispatch_order = map_safe_rally_dispatch_order(
                        self.map_data,
                        self.resolution,
                        self.origin,
                        self.rally_targets,
                        {
                            name: self.robot_positions[name]
                            for name in self.rally_targets
                        },
                        self.target,
                        self.detecting_robot,
                    )
                else:
                    self.rally_dispatch_order = rally_dispatch_order(
                        self.rally_targets,
                        {
                            name: self.robot_positions[name]
                            for name in self.rally_targets
                        },
                        self.target,
                        self.detecting_robot,
                    )
                self.get_logger().info(
                    "Selected conflict-aware rally order: "
                    + ", ".join(self.rally_dispatch_order)
                )
                self.publish_rally_assignments()
            self.publish_task_state("RALLY")
            return

        if self.task_state != "RALLY":
            return
        if not self.participating_robots():
            self.fail_task("all_robots_failed")
            return
        if not any(
            self.battery_modes[name] == "ACTIVE"
            for name in self.rally_dispatch_order
        ):
            self.rally_hold_started_at = None
            return
        now = self.now()
        energy_unready = (
            set(self.rally_charge_requested) if self.enable_battery else set()
        )
        if (
            self.survey_goal_handle is not None
            and self.survey_goal_started_at is not None
            and now - self.survey_goal_started_at >= self.goal_timeout_sec
        ):
            survey_robot = self.survey_robot
            self.get_logger().warn(
                f"Canceling {survey_robot} rally survey after timeout."
            )
            self.survey_goal_started_at = None
            self.survey_cancel_requested = True
            self.survey_goal_handle.cancel_goal_async()
        self.release_return_yields()
        yielded_names = [
            name for name in self.rally_yield_targets
            if self.rally_arrived[name] and name not in self.return_yield_targets
        ]
        if yielded_names:
            active_rally = any(
                self.rally_goal_handles[name] is not None
                or self.rally_goal_pending[name]
                for name in self.rally_dispatch_order
            )
            non_yield_names = [
                name for name in self.rally_dispatch_order
                if name not in self.rally_yield_targets
            ]
            if (
                not active_rally
                and all(self.rally_arrived[name] for name in non_yield_names)
            ):
                for name in yielded_names:
                    self.rally_targets[name] = self.rally_final_targets[name]
                    self.rally_yield_targets.discard(name)
                    getattr(self, "rally_recovery_beneficiaries", {}).pop(name, None)
                    self.rally_arrived[name] = False
                    self.rally_route_unavailable_since[name] = None
                self.publish_rally_assignments()
                return
        yield_recovery_active = any(
            name in self.rally_yield_targets and not self.rally_arrived[name]
            for name in self.rally_dispatch_order
        )
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

        heading_corrections = set()
        last_confirmation = getattr(self, "target_received_source_time", None)
        confirmation_gap = (last_confirmation is not None
                            and TARGET_OBSERVER_FRESHNESS_SEC < now - last_confirmation <= TARGET_DETECTION_TTL_SEC)
        for name, handle in self.rally_goal_handles.items():
            if name not in self.rally_targets:
                continue
            started_at = self.rally_goal_started_at[name]
            if (
                handle is not None
                and started_at is not None
                and now - started_at >= min(
                    self.goal_timeout_sec, self.rally_goal_timeout_sec
                )
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
            yaw = getattr(self, "robot_yaws", {}).get(name)
            if (confirmation_gap and yaw is not None and math.isfinite(yaw) and position is not None
                    and math.dist(position, (target.x, target.y)) <= self.rally_position_tolerance
                    and name in (getattr(self, "rally_observer_guard", None),
                                 getattr(self, "target_observing_robot", None))
                    and handle is None and not self.rally_goal_pending[name]
                    and name not in self.return_yield_targets
                    and self.battery_modes[name] == "ACTIVE"
                    and self.fresh_robot_inputs()
                    and abs(math.atan2(math.sin(target.yaw - yaw),
                                       math.cos(target.yaw - yaw)))
                    > getattr(self, "target_view_fov_rad", math.pi / 2) / 4):
                # Healthy delivered confirmations already prove observation.
                # Let those parked robots settle; reopen the reserved/energy-
                # checked final leg only after the 5s observer heartbeat gap,
                # before the 60s target lease expires. Never use native truth.
                if self.rally_arrived[name]:
                    self.get_logger().info(f"Correcting parked {name}'s observer heading.")
                self.rally_arrived[name] = False
                heading_corrections.add(name)

        self.yield_to_returning_robot()
        if (
            now - self.last_rally_dispatch_at >= 1.0
            and self.fresh_robot_inputs()
            and (
                not self.global_battery_rally_pause
                or self.active_batteries_ready()
                or yield_recovery_active
            )
        ):
            self.last_rally_dispatch_at = now
            if self.enable_battery:
                energy_unready |= self.prepare_rally_charges()
                if self.task_state != "RALLY":
                    return
                charging = any(mode in ("RETURNING", "CHARGING")
                               for mode in self.battery_modes.values())
                if charging:
                    self.rally_preflight_complete = False
                if not self.rally_preflight_complete:
                    self.rally_precharge_active |= bool(energy_unready or charging)
                    if (self.rally_precharge_active and not energy_unready and not charging
                            and (any(self.rally_goal_handles.values())
                                 or any(self.rally_goal_pending.values()))):
                        # Drain existing legs once after charging, otherwise
                        # admitting a new leg at each callback can prevent the
                        # current-map approach order from ever being recomputed.
                        # Local safety/yields and accepted actions remain live.
                        self.rally_hold_started_at = None
                        return
                    if (not any(self.rally_goal_handles.values())
                            and not any(self.rally_goal_pending.values())):
                        # A waiting leader's future outbound route must not
                        # strand a charged observer behind it. Change approach
                        # priorities only between legs; separate return/body
                        # reservations below still protect charging traffic.
                        self.rally_dispatch_order = rally_energy_ready_order(
                            self.rally_dispatch_order, energy_unready,
                            self.battery_modes,
                        )
                    if (not energy_unready and not charging
                            and not any(self.rally_goal_handles.values())
                            and not any(self.rally_goal_pending.values())):
                        if self.rally_precharge_active:
                            positions = {name: self.robot_positions[name] for name in self.rally_final_targets}
                            if self.use_map_safe_rally_order:
                                self.rally_dispatch_order = map_safe_rally_dispatch_order(
                                    self.map_data, self.resolution, self.origin,
                                    self.rally_final_targets, positions, self.target, self.detecting_robot,
                                )
                            else:
                                self.rally_dispatch_order = rally_dispatch_order(
                                    self.rally_final_targets, positions, self.target, self.detecting_robot,
                                )
                            self.get_logger().info("Rally order after precharging: "
                                                   + ", ".join(self.rally_dispatch_order))
                        self.rally_preflight_complete = True
            return_reservations = (rally_return_reservations(
                self.map_data, self.resolution, self.origin, self.robot_positions,
                self.battery_states, self.battery_modes,
                set(self.rally_charge_requested),
            ) if self.enable_battery else {})
            if self.enable_battery:
                approach_routes = self.rally_approach_routes
            else:
                approach_routes = {
                    name: plan_rally_leg(
                        self.rally_final_targets[name], self.map_data,
                        self.resolution, self.origin, self.robot_positions[name],
                    )[1]
                    for name in self.rally_dispatch_order
                    if self.robot_positions[name] is not None
                }
            completed_approaches = {
                name for name in self.rally_dispatch_order
                if self.battery_modes[name] == 'FAILED'
                or self.rally_arrived[name]
            } | heading_corrections
            # A parked temporary refuge waits for traffic to clear before
            # restoring its final goal. Its deferred approach must not seal
            # unrelated traffic; its actual body remains in every plan mask.
            reserved_names = {name for name in self.rally_dispatch_order
                              if self.battery_modes[name] == 'ACTIVE'
                              and (self.rally_goal_handles[name] is not None
                                   or self.rally_goal_pending[name])
                              and self.rally_leg_routes[name]}
            plans = {}
            planning_targets = {}
            stage_names = set()
            for name in self.rally_dispatch_order:
                if (
                    self.rally_arrived[name]
                    or self.rally_goal_handles[name] is not None
                    or self.rally_goal_pending[name]
                    or (
                        self.survey_robot == name
                        and (self.survey_goal_pending or self.survey_goal_handle)
                    )
                    or self.survey_goal_pending
                    or self.survey_goal_handle is not None
                    or self.robot_positions[name] is None
                    or self.battery_modes[name] != "ACTIVE"
                    or return_reservations is None
                ):
                    continue
                staging = name in energy_unready and name not in self.rally_yield_targets
                if staging:
                    if name in (getattr(self, "rally_observer_guard", None),
                                getattr(self, "target_observing_robot", None)):
                        # A brief camera gap must not stage the last observer
                        # away while a charged peer is approaching. The target
                        # lease is still fresh here; local reserve may preempt.
                        continue
                    # Waiting for a serial charge need not mean waiting far
                    # away. The same route/body reservations protect a normal
                    # gateway navigation prefix toward home; local safety may
                    # preempt it, and only one early return is still requested.
                    if name in self.rally_charge_requested or not (
                        self.rally_charge_requested
                        or any(mode in ('RETURNING', 'CHARGING')
                               for mode in self.battery_modes.values())
                    ):
                        continue
                    state = self.battery_states[name]
                    home = RallyPose(float(state['charge_x']), float(state['charge_y']), 0.)
                    if math.dist(self.robot_positions[name], (home.x, home.y)) <= 1.25:
                        continue
                    plan = plan_rally_leg(
                        home, self.map_data, self.resolution, self.origin,
                        self.robot_positions[name], MAX_NAVIGATION_LEG_M,
                        rally_stationary_positions(
                            self.robot_positions, name,
                            reserved_names | set(return_reservations),
                        ), visible_only=True,
                    )
                    if plan[0] is not None:
                        plans[name] = plan
                        planning_targets[name] = home
                        stage_names.add(name)
                    continue
                if self.rally_recovery_requested[name]:
                    plan = (None, ())
                    self.rally_recovery_requested[name] = False
                else:
                    plan = plan_rally_leg(
                        self.rally_targets[name],
                        self.map_data,
                        self.resolution,
                        self.origin,
                        self.robot_positions[name],
                        min(MAX_NAVIGATION_LEG_M, rally_leg_limit(self.rally_attempts[name])),
                        rally_stationary_positions(self.robot_positions, name, reserved_names),
                        visible_only=True,
                    )
                if plan[0] is None:
                    if return_reservations:
                        # Local safety traffic may temporarily seal this route.
                        # Yielding has its own verified escape path above;
                        # reassignment/probe shortcuts must not bypass returns.
                        self.rally_route_unavailable_since[name] = None
                        continue
                    since = self.rally_route_unavailable_since[name]
                    if since is None:
                        self.rally_route_unavailable_since[name] = now
                        self.get_logger().warn(
                            f"No safe rally route for {name}; "
                            f"position={self.robot_positions[name]}, "
                            f"target={self.rally_targets[name]}."
                        )
                    elif now - since >= 2.0:
                        if any(
                            self.rally_goal_handles[other_name] is not None
                            or self.rally_goal_pending[other_name]
                            for other_name in self.rally_dispatch_order
                        ):
                            continue
                        # A parked robot can seal a narrow corridor for a
                        # remaining leg.  Move that blocker to another safe
                        # separated rally pose before giving up on the leg.
                        parked_names = [
                            other_name
                            for other_name in self.rally_dispatch_order
                            if other_name != name
                            and self.battery_modes[other_name] == "ACTIVE"
                            and other_name not in energy_unready
                            and self.robot_positions[other_name] is not None
                        ]
                        possible_blockers = [
                            other_name
                            for other_name in parked_names
                            if (other_name not in self.rally_yield_targets
                                or self.return_yield_targets.get(other_name) == name)
                            and plan_rally_leg(
                                self.rally_targets[name],
                                self.map_data,
                                self.resolution,
                                self.origin,
                                self.robot_positions[name],
                                rally_leg_limit(self.rally_attempts[name]),
                                [
                                    position
                                    for candidate_name, position in self.robot_positions.items()
                                    if candidate_name not in (name, other_name)
                                    and position is not None
                                ],
                            )[0]
                            is not None
                        ]
                        if not possible_blockers:
                            possible_blockers = [
                                other_name
                                for other_name in parked_names
                                if (other_name not in self.rally_yield_targets
                                    or self.return_yield_targets.get(other_name) == name)
                            ]
                        for blocker in possible_blockers:
                            blocker_reserved = rally_reserved_poses(
                                self.rally_targets,
                                self.rally_final_targets,
                                exclude=(blocker,),
                            )
                            blocker_positions = [
                                self.robot_positions[other_name]
                                for other_name in parked_names
                                if other_name != blocker
                            ]
                            blocker_positions.append(self.robot_positions[name])
                            view_distance = (
                                getattr(self, "target_view_distance", 3.0) - self.rally_position_tolerance
                                if blocker == getattr(self, "rally_observer_guard", None) else None
                            )
                            # Clear the waiting approach first. A distant new
                            # final pose can keep the blocker on that approach
                            # for several legs, starving the waiting robot.
                            waiting_plan = plan_rally_leg(
                                self.rally_targets[name], self.map_data,
                                self.resolution, self.origin,
                                self.robot_positions[name],
                                max_distance_m=float("inf"),
                                blocked_positions=[
                                    position for other, position
                                    in self.robot_positions.items()
                                    if other not in (name, blocker)
                                    and position is not None
                                ],
                            )
                            blocker_replacement = None
                            if waiting_plan[0] is not None:
                                blocker_replacement = rally_yield_pose(
                                    self.map_data, self.resolution, self.origin,
                                    self.robot_positions[blocker], self.target,
                                    blocker_reserved, blocker_positions,
                                    reserved_routes=(waiting_plan[1],), visible_only=True,
                                    target_view_distance=view_distance,
                                )
                            permanent_reassignment = blocker_replacement is None
                            if permanent_reassignment:
                                blocker_replacement = reassign_rally_pose(
                                    self.map_data, self.resolution, self.origin,
                                    blocker, self.robot_positions[blocker],
                                    self.target, blocker_reserved, blocker_positions,
                                )
                            if blocker_replacement is None:
                                continue
                            if math.dist(self.robot_positions[blocker],
                                         (blocker_replacement.x, blocker_replacement.y)) < self.rally_position_tolerance:
                                continue
                            blocker_plan = plan_rally_leg(
                                blocker_replacement, self.map_data, self.resolution,
                                self.origin, self.robot_positions[blocker],
                                min(MAX_NAVIGATION_LEG_M, rally_leg_limit(self.rally_attempts[blocker])),
                                [position for other, position in self.robot_positions.items()
                                 if other != blocker and position is not None],
                                visible_only=True,
                            )
                            if blocker_plan[0] is None:
                                continue
                            if view_distance is not None and not rally_target_view(
                                    self.map_data, self.resolution, self.origin,
                                    (blocker_plan[0].x, blocker_plan[0].y), self.target,
                                    view_distance):
                                continue
                            if permanent_reassignment:
                                self.rally_final_targets[blocker] = blocker_replacement
                            else:
                                self.rally_yield_targets.add(blocker)
                            # Its inbound refuge may block the charged owner's
                            # outbound approach. This new move is ordinary rally
                            # recovery, with fresh-target and energy checks;
                            # do not retain the local-return safety exception.
                            self.return_yield_targets.pop(blocker, None)
                            self.rally_recovery_beneficiaries[blocker] = name
                            self.rally_targets[blocker] = blocker_replacement
                            self.rally_arrived[blocker] = False
                            self.rally_route_unavailable_since[name] = now
                            self.publish_rally_assignments()
                            self.get_logger().warn(
                                f"{'Reassigning' if permanent_reassignment else 'Yielding'} "
                                f"parked {blocker} to "
                                f"({blocker_replacement.x:.2f}, "
                                f"{blocker_replacement.y:.2f}) so {name} "
                                "can reach its rally pose."
                            )
                            # A temporary refuge was certified against this
                            # beneficiary's original route. Keep that goal;
                            # choosing a new one can cross the very refuge we
                            # just selected and invalidate its certificate.
                            if permanent_reassignment:
                                current_reserved = rally_reserved_poses(
                                    self.rally_targets,
                                    self.rally_final_targets,
                                    exclude=(name,),
                                )
                                current_replacement = reassign_rally_pose(
                                    self.map_data,
                                    self.resolution,
                                    self.origin,
                                    name,
                                    self.robot_positions[name],
                                    self.target,
                                    current_reserved,
                                    [
                                        self.robot_positions[other_name]
                                        for other_name in parked_names
                                        if other_name != blocker
                                    ],
                                )
                                if current_replacement is not None:
                                    self.rally_targets[name] = current_replacement
                                    self.rally_final_targets[name] = current_replacement
                                    self.rally_route_unavailable_since[name] = now
                                    self.rally_recovery_requested[name] = True
                                    self.publish_rally_assignments()
                                    self.get_logger().warn(
                                        f"Reassigned {name} to a reachable rally "
                                        f"pose ({current_replacement.x:.2f}, "
                                        f"{current_replacement.y:.2f}) after parked "
                                        "robot yield."
                                    )
                            # Dispatch the blocker now: returning first would let
                            # the earlier waiting robot reassign it every tick.
                            # No other rally/probe action is active at this point.
                            self.send_rally_goal(blocker, blocker_plan)
                            return
                        else:
                            reserved_poses = rally_reserved_poses(
                                self.rally_targets,
                                self.rally_final_targets,
                                exclude=(name,),
                            )
                            replacement = reassign_rally_pose(
                                self.map_data,
                                self.resolution,
                                self.origin,
                                name,
                                self.robot_positions[name],
                                self.target,
                                reserved_poses,
                                [
                                    self.robot_positions[other_name]
                                    for other_name in parked_names
                                ],
                            )
                            if replacement is not None:
                                self.rally_targets[name] = replacement
                                self.rally_final_targets[name] = replacement
                                self.rally_route_unavailable_since[name] = None
                                self.publish_rally_assignments()
                                self.get_logger().warn(
                                    f"Reassigned {name} to a fresh reachable "
                                    f"rally pose ({replacement.x:.2f}, "
                                    f"{replacement.y:.2f}) after map update."
                                )
                                continue
                        probe = rally_survey_pose(
                            self.map_data,
                            self.resolution,
                            self.origin,
                            self.robot_positions[name],
                            self.target,
                        )
                        if (
                            name not in self.rally_probe_targets
                            and
                            probe is not None
                            and math.dist(
                                self.robot_positions[name], (probe.x, probe.y)
                            ) > self.rally_position_tolerance
                        ):
                            self.rally_probe_targets.add(name)
                            self.rally_probe_robot = name
                            self.rally_route_unavailable_since[name] = now
                            self.get_logger().warn(
                                f"Probing a reachable rally survey pose for "
                                f"{name} ({probe.x:.2f}, {probe.y:.2f}) "
                                "before retrying its final pose."
                            )
                            if self.send_survey_goal(name, probe):
                                continue
                            self.rally_probe_targets.discard(name)
                            self.rally_probe_robot = None
                    if now - self.rally_route_unavailable_since[name] >= RALLY_ASSIGNMENT_WAIT_SEC:
                        self.fail_task(f"rally_route_unavailable:{name}")
                        return
                    continue
                self.rally_route_unavailable_since[name] = None
                plans[name] = plan
                planning_targets[name] = self.rally_targets[name]
            if self.survey_goal_pending or self.survey_goal_handle is not None:
                return
            routes = {name: plan[1] for name, plan in plans.items()}
            reserved_routes = [
                remaining_rally_route(
                    self.rally_leg_routes[name], self.robot_positions[name]
                )
                for name in self.rally_dispatch_order
                if (
                    self.rally_goal_handles[name] is not None
                    or self.rally_goal_pending[name]
                )
                and self.rally_leg_routes[name]
            ]
            slots = max(0, self.rally_max_concurrent - len(reserved_routes))
            admitted_names = set(reserved_names)
            for name in self.rally_dispatch_order:
                if slots == 0:
                    break
                if name not in plans:
                    continue
                # The requesting waiter lends its future priority until the
                # blocker clears it. Parked refuges defer their approaches;
                # real bodies/live legs and safety returns stay protected.
                priority_routes = [] if name in stage_names | heading_corrections else rally_priority_reservations(
                    self.rally_dispatch_order, name, approach_routes,
                    completed_approaches | {
                        beneficiary for yielding, beneficiary in
                        getattr(self, "rally_recovery_beneficiaries", {}).items()
                        if yielding == name and not self.rally_arrived[yielding]
                    },
                )
                if priority_routes is None:
                    continue
                plan = plans[name]
                if admitted_names != reserved_names:
                    # A newly reserved leader can clear this corridor. Prefer
                    # a safe prefix of the short route over a static detour.
                    plan = plan_rally_leg(
                        planning_targets[name], self.map_data, self.resolution,
                        self.origin, self.robot_positions[name],
                        min(MAX_NAVIGATION_LEG_M, rally_leg_limit(self.rally_attempts[name])),
                        rally_stationary_positions(
                            self.robot_positions, name, admitted_names
                            | (set(return_reservations) if name in stage_names else set()),
                        ),
                        visible_only=True,
                    )
                reservations = [*reserved_routes, *priority_routes, *(route for other, route in
                                (return_reservations or {}).items() if other != name)]
                admitted = reserve_rally_prefix(plan, reservations)
                if admitted is None:
                    live_reservations = [*reserved_routes, *(route for other, route in
                                         (return_reservations or {}).items() if other != name)]
                    inversions = rally_approach_inversions(
                        self.rally_dispatch_order, self.robot_positions, approach_routes)
                    if (self.enable_battery and inversions and getattr(self, "use_map_safe_rally_order", True)
                            and priority_routes and reserve_rally_prefix(plan, live_reservations) is not None):
                        repaired = map_safe_rally_dispatch_order(
                            self.map_data, self.resolution, self.origin, self.rally_final_targets,
                            self.robot_positions, self.target, self.detecting_robot)
                        if rally_approach_inversions(repaired, self.robot_positions, approach_routes) < inversions:
                            # Only future priority is blocking a viable leg.
                            # Do not change order while old legs execute; drain
                            # them, then re-evaluate all current body-masked plans.
                            self.rally_preflight_complete = False
                            self.rally_precharge_active = True
                            self.get_logger().info("Draining rally legs to release an ahead robot's approach.")
                            return
                    continue
                self.send_rally_goal(name, admitted, name in stage_names)
                if name in stage_names and self.rally_goal_pending[name]:
                    self.rally_precharge_staging.setdefault(name, self.rally_charge_budgets[name])
                    self.get_logger().info(f"Staging {name} along its reserved home approach before serial charging.")
                reserved_routes.append(admitted[1])
                admitted_names.add(name)
                slots -= 1

        navigation_quiescent = (
            not any(
                self.rally_goal_handles[name] is not None
                or self.rally_goal_pending[name]
                for name in self.rally_dispatch_order
            )
            and self.survey_goal_handle is None
            and not self.survey_goal_pending
            and not self.rally_yield_targets
            and not self.rally_probe_targets
            and all(
                self.rally_arrived[name]
                for name in self.rally_dispatch_order
            )
        )
        stable = navigation_quiescent and robots_stable(
            self.robot_positions,
            self.robot_velocities,
            self.rally_targets,
            self.rally_position_tolerance,
            self.rally_linear_tolerance,
            self.rally_angular_tolerance,
        )
        stable = (stable and self.active_batteries_ready() and not energy_unready
                  and (not self.enable_battery or self.rally_preflight_complete))
        if not stable:
            self.rally_hold_started_at = None
            return
        if self.rally_hold_started_at is None:
            self.rally_hold_started_at = now
            return
        if now - self.rally_hold_started_at >= self.rally_hold_sec:
            completion_state = (
                "PARTIAL_COMPLETE"
                if any(mode == "FAILED" for mode in self.battery_modes.values())
                else "COMPLETE"
            )
            self.publish_task_state(completion_state)

    def prepare_rally_charges(self):
        """Check the whole final route before admitting another navigation leg."""
        blocked = set(self.rally_charge_requested) | set(self.rally_precharge_staging)
        candidates = []
        budgets, travel_times, charge_times = {}, {}, {}
        self.rally_approach_routes = {}
        now = self.now()
        self.rally_observer_guard = rally_observation_guard(
            getattr(self, "target_observing_robot", None),
            getattr(self, "target_received_source_time", None),
            now, self.battery_modes,
            getattr(self, "message_freshness_timeout_sec", 5.0),
        )
        if self.rally_observer_guard in self.rally_charge_requested:
            self.rally_observer_guard = None  # Never revoke an admitted safety return.
        for name in self.rally_dispatch_order:
            if self.battery_modes[name] == "FAILED" or self.robot_positions[name] is None:
                continue
            target = self.rally_final_targets[name]
            state = self.battery_states[name]
            try:
                speed = float(state.get("nominal_speed_mps", .18))
                factor = float(state.get("return_path_factor", 2.0))
                home = (float(state["charge_x"]), float(state["charge_y"]))
                charge_time = float(state.get("charge_duration_sec", 6.0))
                if not all(math.isfinite(v) for v in (*home, speed, factor, charge_time)) or speed <= 0 or min(factor, charge_time) < 0:
                    raise ValueError("invalid charge time estimate")
                charge_times[name] = charge_time
                if self.battery_modes[name] != "CHARGING":
                    charge_times[name] += math.dist(self.robot_positions[name], home) * factor / speed
            except (KeyError, TypeError, ValueError) as error:
                blocked.add(name)
                self.get_logger().warn(f"Invalid rally charge-time budget for {name}: {error}")
                continue
            position = self.robot_positions[name] if self.battery_modes[name] == "ACTIVE" else home
            _, route = plan_rally_leg(
                target, self.map_data, self.resolution, self.origin,
                position,
            )
            if not route:
                continue  # The existing route/map recovery still owns this case.
            self.rally_approach_routes[name] = (position, *route)
            distance = sum(math.dist(a, b) for a, b in zip(route, route[1:]))
            travel_times[name] = distance / speed
            if (self.battery_modes[name] != "ACTIVE"
                    or ((self.rally_goal_handles[name] is not None or self.rally_goal_pending[name])
                        and name not in self.rally_precharge_staging)):
                continue
            try:
                energy = float(state["energy"])
                idle_cost = float(state.get("idle_cost_per_sec", 0.02))
                charge_target = (
                    float(state["capacity"]) * float(state["charge_target_fraction"])
                )
                required = battery_assignment_required_energy(
                    distance, math.dist((target.x, target.y), home),
                    float(state.get("move_cost_per_m", 1.0)), idle_cost,
                    float(state.get("return_path_factor", 2.0)),
                    float(state.get("nominal_speed_mps", 0.18)),
                    float(state.get("return_safety_margin", 8.0)),
                ) + idle_cost * self.rally_hold_sec
                if (not all(math.isfinite(value)
                            for value in (required, energy, charge_target))
                        or charge_target <= 0):
                    raise ValueError("nonfinite energy budget")
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
                blocked.add(name)
                self.get_logger().warn(
                    f"Invalid rally battery budget for {name}: {error}"
                )
                continue
            budgets[name] = (energy, required, charge_target, idle_cost, home)
        requirements, waits = rally_wait_requirements(
            {name: budget[1] for name, budget in budgets.items()},
            self.battery_states, self.battery_modes, travel_times, charge_times,
        )
        self.rally_wait_budgets = waits
        self.rally_charge_budgets = {**self.rally_precharge_staging, **requirements}
        for name, (energy, _, charge_target, idle_cost, home) in budgets.items():
            required = max(requirements[name], self.rally_precharge_staging.get(name, 0.),
                           getattr(self, "rally_detour_budgets", {}).get(name, 0.))
            self.rally_charge_budgets[name] = required
            if energy > required:
                continue
            blocked.add(name)
            if required > charge_target:
                self.fail_task(f"rally_energy_capacity_insufficient:{name}")
                return blocked
            if name == self.rally_observer_guard:
                if now - getattr(self, "last_observer_handoff_wait_at", -float("inf")) >= 5.0:
                    self.last_observer_handoff_wait_at = now
                    self.consumed_publisher.publish(String(data=json.dumps({
                        "event": "coordinator_observer_handoff_wait", "event_time": now,
                        "robot": name, "observer_source_time": self.target_received_source_time,
                        "available_energy": energy, "required_energy": required,
                    }, sort_keys=True)))
                    self.get_logger().info(f"Preserving {name}'s fresh visual contact while a peer approaches.")
                continue  # The local reserve may still preempt without permission.
            candidates.append((math.dist(self.robot_positions[name], home),
                               name, energy, required))
        # Independent local returns do not share route reservations. Admit one
        # early return at a time, including its charging/settling interval. The
        # existing return-corridor yields can then clear parked robots safely.
        if any(mode in ("RETURNING", "CHARGING")
               for mode in self.battery_modes.values()):
            return blocked
        if self.rally_charge_requested:
            candidates = [candidate for candidate in candidates
                          if candidate[1] in self.rally_charge_requested]
        if not candidates:
            return blocked
        _, name, energy, required = min(candidates)
        if now - self.rally_charge_requested.get(name, -float("inf")) < 2.0:
            return blocked
        self.rally_charge_requested[name] = now
        self.rally_preflight_complete = False
        self.rally_precharge_active = True
        self.charge_request_publishers[name].publish(String(data=json.dumps({
            "robot": name, "stamp_sec": now, "task_phase": "RALLY",
            "reason": "rally_energy_budget", "required_energy": required,
            "available_energy": energy,
            "waiting_time_budget_sec": waits[name],
        }, sort_keys=True)))
        self.get_logger().warn(
            f"Requesting early charge for {name}: energy={energy:.2f}, "
            f"whole_rally_budget={required:.2f}."
        )
        return blocked

    def rally_plan_has_energy(self, robot_name, plan):
        """Fund the actual proposed detour, the final approach and its reserve.

        The nominal trip/wait budget is checked before planning. A longer route
        around a peer must additionally fund its actual extra distance before
        admission, instead of making every robot precharge for a phantom loop.
        """
        wait = self.rally_wait_budgets.get(robot_name)
        if wait is None:
            return False
        pose, route = plan
        _, remaining = plan_rally_leg(
            self.rally_final_targets[robot_name], self.map_data, self.resolution,
            self.origin, (pose.x, pose.y),
        )
        if not remaining:
            return False
        distance = lambda points: sum(math.dist(a, b) for a, b in zip(points, points[1:]))
        actual = distance((self.robot_positions[robot_name], *route)) + distance(remaining)
        state = self.battery_states[robot_name]
        try:
            move = float(state.get("move_cost_per_m", 1.))
            idle = float(state.get("idle_cost_per_sec", .02))
            speed = float(state.get("nominal_speed_mps", .18))
            if not all(math.isfinite(v) for v in (move, idle, speed)) or min(move, idle) < 0 or speed <= 0:
                return False
            final = self.rally_final_targets[robot_name]
            home = (float(state["charge_x"]), float(state["charge_y"]))
            required = battery_assignment_required_energy(
                actual, math.dist((final.x, final.y), home), move, idle,
                float(state.get("return_path_factor", 2.)), speed,
                float(state.get("return_safety_margin", 8.)),
            ) + idle * (self.rally_hold_sec + wait)
            energy = float(state["energy"])
            if not all(math.isfinite(v) for v in (required, energy)):
                return False
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return False
        if energy <= required:
            self.rally_detour_budgets[robot_name] = required
            return False  # Next preflight owns serial charging/capacity checks.
        self.rally_detour_budgets.pop(robot_name, None)
        return True

    def send_survey_goal(self, robot_name, pose):
        if not self.fresh_robot_inputs() or not self.fresh_target():
            return False
        if self.survey_goal_handle is not None or self.survey_goal_pending:
            return False
        if self.battery_modes[robot_name] != "ACTIVE":
            return False
        protected = rally_return_reservations(
            self.map_data, self.resolution, self.origin, self.robot_positions,
            self.battery_states, self.battery_modes, set(self.rally_charge_requested))
        if protected is None:
            return False
        reservations = list(protected.values()) + [
            remaining_rally_route(route, self.robot_positions[name])
            for name, route in self.rally_leg_routes.items() if name != robot_name
            and (self.rally_goal_handles[name] is not None or self.rally_goal_pending[name])]
        blocked = [position for name, position in self.robot_positions.items()
                   if name != robot_name and position is not None]
        # Fund the dispatched prefix and its own conservative return. Shorten
        # an optional survey instead of sending an unfunded whole-route goal.
        cache = {}
        length = MAX_NAVIGATION_LEG_M
        plan = (None, ())
        while length >= USEFUL_TRAVEL_M:
            plan = plan_rally_leg(pose, self.map_data, self.resolution, self.origin,
                                  self.robot_positions[robot_name], length,
                                  blocked_positions=blocked, visible_only=True,
                                  route_cache=cache)
            plan = reserve_rally_prefix(plan, reservations)
            if plan is not None and plan[0] is not None:
                distance = sum(math.dist(a, b) for a, b in zip(
                    (self.robot_positions[robot_name], *plan[1]), plan[1]))
                if (math.dist(self.robot_positions[robot_name], (plan[0].x, plan[0].y)) > self.rally_position_tolerance
                        and self.exploration_battery_factor(robot_name, distance,
                            (plan[0].x, plan[0].y)) == 1.):
                    break
            length /= 2
        else:
            return False
        pose = plan[0]
        allowed_attempts = self.num_robots * (1 + self.rally_max_retries)
        if self.survey_attempts >= allowed_attempts:
            self.fail_task(
                f"rally_survey_failed:{robot_name}"
            )
            return False
        client = self.robot_nav_clients[robot_name]
        if not client.server_is_ready():
            self.survey_attempts += 1
            return False
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
        self.survey_cancel_requested = False
        self.survey_goal_pending = True
        self.record_navigation_decision(robot_name, "target_survey", goal.pose)
        future = client.send_goal_async(goal)
        future.add_done_callback(self.survey_goal_response)
        return True

    def survey_goal_response(self, future):
        self.survey_goal_pending = False
        try:
            goal_handle = future.result()
        except Exception as error:
            self.get_logger().error(f"Rally survey request failed: {error}")
            survey_robot = self.survey_robot
            self.survey_robot = None
            if survey_robot in self.rally_probe_targets:
                self.rally_probe_targets.discard(survey_robot)
                if self.rally_probe_robot == survey_robot:
                    self.rally_probe_robot = None
                self.rally_route_unavailable_since[survey_robot] = self.now() - 2.0
                self.rally_recovery_requested[survey_robot] = True
            else:
                self.survey_dispatch_cursor += 1
            return
        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warn("Rally survey goal was rejected.")
            survey_robot = self.survey_robot
            self.survey_robot = None
            if survey_robot in self.rally_probe_targets:
                self.rally_probe_targets.discard(survey_robot)
                if self.rally_probe_robot == survey_robot:
                    self.rally_probe_robot = None
                self.rally_route_unavailable_since[survey_robot] = self.now() - 2.0
                self.rally_recovery_requested[survey_robot] = True
            else:
                self.survey_dispatch_cursor += 1
            return
        self.survey_goal_handle = goal_handle
        self.survey_goal_started_at = self.now()
        survey_robot = self.survey_robot
        if (
            self.survey_cancel_requested
            or survey_robot not in self.battery_modes
            or self.battery_modes[survey_robot] != "ACTIVE"
        ):
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
        canceled = self.survey_cancel_requested
        self.survey_cancel_requested = False
        self.survey_robot = None
        try:
            status = future.result().status
        except Exception as error:
            status = f"exception: {error}"
        if (
            survey_robot is None
            or self.battery_modes[survey_robot] == "FAILED"
        ):
            return
        if survey_robot in self.rally_probe_targets and survey_robot not in self.rally_final_targets:
            return
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.survey_battery_preempted = False
            if survey_robot == self.rally_probe_robot:
                self.rally_probe_robot = None
                self.rally_probe_targets.discard(survey_robot)
                self.rally_targets[survey_robot] = self.rally_final_targets[
                    survey_robot
                ]
                self.rally_route_unavailable_since[survey_robot] = self.now()
                self.publish_rally_assignments()
                self.get_logger().info(
                    f"{survey_robot} completed a rally probe; restoring its "
                    "final rally pose."
                )
            else:
                self.rally_prepare_started_at = self.now()
                self.get_logger().info(
                    f"{survey_robot} completed a target-area survey leg."
                )
        elif self.survey_battery_preempted:
            self.survey_battery_preempted = False
            self.survey_attempts -= 1
            self.get_logger().info("Target-area survey paused for charging.")
        elif canceled and survey_robot in self.rally_probe_targets:
            self.rally_probe_targets.discard(survey_robot)
            if self.rally_probe_robot == survey_robot:
                self.rally_probe_robot = None
            self.rally_route_unavailable_since[survey_robot] = self.now() - 2.0
            self.rally_recovery_requested[survey_robot] = True
            self.get_logger().warn(
                f"Rally probe for {survey_robot} was canceled; retrying "
                "through the recovery path."
            )
        else:
            self.survey_dispatch_cursor += 1
            self.get_logger().warn(
                f"Target-area survey failed with status {status}."
            )

    def send_rally_goal(self, robot_name, plan=None, charge_staging=False):
        if not self.fresh_robot_inputs():
            return
        local_return_yield = robot_name in self.return_yield_targets
        if not local_return_yield and not self.fresh_target():
            return
        if (
            self.task_state != "RALLY"
            or self.battery_modes[robot_name] != "ACTIVE"
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
            blocked_positions = [
                self.robot_positions[name]
                for name in self.rally_dispatch_order
                if name != robot_name
                and self.robot_positions[name] is not None
            ]
            plan = plan_rally_leg(
                self.rally_targets[robot_name],
                self.map_data,
                self.resolution,
                self.origin,
                self.robot_positions[robot_name],
                min(MAX_NAVIGATION_LEG_M, rally_leg_limit(self.rally_attempts[robot_name])),
                blocked_positions, visible_only=True,
            )
        target, route = plan
        if target is None:
            return
        if (self.enable_battery and not local_return_yield and not charge_staging
                and not self.rally_plan_has_energy(robot_name, plan)):
            return
        if not self.fresh_robot_inputs() or (not local_return_yield and not self.fresh_target()):
            return
        final = self.rally_targets[robot_name]
        if (not local_return_yield and not charge_staging
                and world_to_grid(target.x, target.y, self.resolution, *self.origin)
                != world_to_grid(final.x, final.y, self.resolution, *self.origin)):
            target = rally_observation_heading(
                target, getattr(self, "target", None), self.map_data,
                self.resolution, self.origin, getattr(self, "target_view_distance", 3.0))
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
        self.rally_leg_poses[robot_name] = target
        self.rally_goal_pending[robot_name] = True
        self.record_navigation_decision(robot_name, "local_return_yield" if local_return_yield else "rally", goal.pose)
        future = client.send_goal_async(goal)
        future.add_done_callback(
            lambda result, name=robot_name: self.rally_goal_response(name, result)
        )

    def rally_goal_response(self, robot_name, future):
        self.rally_goal_pending[robot_name] = False
        preempted = (self.rally_yield_requested[robot_name]
                     or self.rally_battery_preempted[robot_name]
                     or self.battery_modes[robot_name] != "ACTIVE")
        try:
            goal_handle = future.result()
        except Exception as error:
            self.rally_leg_routes[robot_name] = ()
            self.rally_yield_requested[robot_name] = False
            self.rally_battery_preempted[robot_name] = False
            if not preempted:
                self.rally_attempts[robot_name] += 1
                self.rally_route_unavailable_since[robot_name] = self.now() - 2.0
                self.rally_recovery_requested[robot_name] = True
            self.get_logger().error(
                f"{robot_name} rally request failed: {error}"
            )
            return
        if goal_handle is None or not goal_handle.accepted:
            self.rally_leg_routes[robot_name] = ()
            self.rally_yield_requested[robot_name] = False
            self.rally_battery_preempted[robot_name] = False
            if not preempted:
                self.rally_attempts[robot_name] += 1
                self.rally_route_unavailable_since[robot_name] = self.now() - 2.0
                self.rally_recovery_requested[robot_name] = True
            self.get_logger().warn(f"{robot_name} rejected its rally goal.")
            return
        self.rally_goal_handles[robot_name] = goal_handle
        self.rally_goal_started_at[robot_name] = self.now()
        if self.battery_modes[robot_name] != "ACTIVE":
            self.rally_battery_preempted[robot_name] = True
        if preempted:
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
        leg_pose = self.rally_leg_poses.pop(robot_name, None)
        yielded = self.rally_yield_requested[robot_name]
        self.rally_yield_requested[robot_name] = False
        battery_preempted = self.rally_battery_preempted[robot_name]
        self.rally_battery_preempted[robot_name] = False
        if (
            robot_name not in self.rally_targets
            or self.battery_modes[robot_name] == "FAILED"
        ):
            self.rally_arrived[robot_name] = False
            return
        try:
            status = future.result().status
        except Exception as error:
            status = f"exception: {error}"
        success = status == GoalStatus.STATUS_SUCCEEDED
        if success:
            # An intermediate waypoint proves that the route is alive.  Do
            # not let earlier transient failures consume all later retries.
            self.rally_attempts[robot_name] = 0
        target = self.rally_targets[robot_name]
        position = self.robot_positions.get(robot_name)
        self.rally_arrived[robot_name] = (
            success
            and leg_pose is not None
            and abs(math.atan2(math.sin(leg_pose.yaw - target.yaw),
                               math.cos(leg_pose.yaw - target.yaw))) < 1e-6
            and position is not None
            and math.dist(position, (target.x, target.y))
            <= self.rally_position_tolerance
        )
        if self.rally_arrived[robot_name] and robot_name in self.rally_probe_targets:
            self.rally_yield_targets.discard(robot_name)
            getattr(self, "rally_recovery_beneficiaries", {}).pop(robot_name, None)
            self.rally_probe_targets.discard(robot_name)
            self.rally_targets[robot_name] = self.rally_final_targets[robot_name]
            self.rally_arrived[robot_name] = False
            self.publish_rally_assignments()
            self.get_logger().info(
                f"{robot_name} completed a yield move; restoring its final "
                "rally pose."
            )
            return
        if self.rally_arrived[robot_name] and robot_name in self.rally_yield_targets:
            self.get_logger().info(
                f"{robot_name} reached its temporary yield pose; holding "
                "until the reserved traffic clears."
            )
            return
        if self.rally_arrived[robot_name]:
            getattr(self, "rally_recovery_beneficiaries", {}).pop(robot_name, None)
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
            if self.rally_attempts[robot_name] >= 2:
                self.rally_route_unavailable_since[robot_name] = self.now() - 2.0
                self.rally_recovery_requested[robot_name] = True
            self.get_logger().warn(
                f"{robot_name} rally goal failed with status {status}."
            )

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def fresh_robot_inputs(self):
        """Only allocate from pose/TF/map data delivered within the TTL window."""
        now = self.now()
        timeout = self.message_freshness_timeout_sec
        if (self.map_received_at is None or not 0 <= now - self.map_received_at
                <= min(timeout, STATE_TTL_SEC["fused_map_snapshot"])):
            return False
        if self.enable_battery and unavailable_battery_states(
            {name: self.battery_state_received_at[name] for name in self.participating_robots()},
            now, min(timeout, STATE_TTL_SEC["battery_state"]),
        ):
            return False
        ready = self.fresh_robot_poses() and all(
            self.robot_map_received_at[name] is not None
            and 0 <= now - self.robot_map_received_at[name] <= min(timeout, STATE_TTL_SEC["map_snapshot"])
            for name in self.input_robot_names()
        )
        if ready:
            HeadquartersControl.refresh_planning_map(self)
        return ready

    def fresh_robot_poses(self):
        """Require live pose/TF for traffic safety and the final hold gate."""
        now = self.now()
        # A delivered sample does not acquire a new lease on reception.
        # Apply the same source-age TTL used by the transport, even if the
        # configured general freshness bound is more permissive.
        for name in self.input_robot_names():
            timestamps = (
                (self.robot_odom_received_at[name], STATE_TTL_SEC["pose_state"]),
                (self.robot_tf_received_at[name], STATE_TTL_SEC["frame_state"]),
            )
            if any(stamp is None or not 0 <= now - stamp <= min(self.message_freshness_timeout_sec, ttl)
                   for stamp, ttl in timestamps):
                return False
        return True

    def input_freshness_details(self):
        """Expose missing/stale delivered inputs without renewing their stamps."""
        now = self.now()
        inputs = {"headquarters/fused_map_snapshot": (self.map_received_at, "fused_map_snapshot")}
        for name in self.input_robot_names():
            for kind, times in (("pose_state", self.robot_odom_received_at),
                                ("frame_state", self.robot_tf_received_at),
                                ("map_snapshot", self.robot_map_received_at)):
                inputs[f"{name}/{kind}"] = (times[name], kind)
        if self.enable_battery:
            for name in self.participating_robots():
                inputs[f"{name}/battery_state"] = (self.battery_state_received_at[name], "battery_state")
        if self.task_state in ("FOUND", "RALLY"):
            inputs["headquarters/target_detection"] = (self.target_received_source_time, "target_detection")
        return {key: {"source_time": stamp, "age_sec": None if stamp is None else now - stamp,
                      "ttl_sec": TARGET_DETECTION_TTL_SEC if kind == "target_detection" else min(self.message_freshness_timeout_sec, STATE_TTL_SEC[kind])}
                for key, (stamp, kind) in inputs.items()}

    def refresh_planning_map(self):
        source = getattr(self, "source_map_data", None)
        if source is None:
            return
        now = self.now()
        positions = {}
        for name in self.input_robot_names():
            if all(stamp is not None and 0 <= now-stamp <= min(self.message_freshness_timeout_sec, ttl)
                   for stamp, ttl in ((self.robot_odom_received_at[name], STATE_TTL_SEC['pose_state']),
                                      (self.robot_tf_received_at[name], STATE_TTL_SEC['frame_state']),
                                      (self.robot_map_received_at[name], STATE_TTL_SEC['map_snapshot']))):
                positions[name] = self.robot_positions[name]
        planning, cells = planning_grid_without_self_returns(source, self.resolution, self.origin, positions)
        if not np.array_equal(self.map_data, planning):
            self.frontier_cache = None
        self.map_data = planning
        self.map_self_return_cells = cells

    def map_callback(self, msg):
        self.map_data = np.asarray(msg.data, dtype=np.int16).reshape(
            msg.info.height, msg.info.width
        )
        self.source_map_data = self.map_data
        self.map_self_return_cells = {}
        self.resolution = msg.info.resolution
        self.origin = (
            msg.info.origin.position.x,
            msg.info.origin.position.y,
        )
        self.map_width = msg.info.width
        self.map_height = msg.info.height
        self.map_known_count = int(np.count_nonzero(self.map_data >= 0))
        self.frontier_cache = None
        self.map_received_at = (
            msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        )

    def robot_odom_callback(self, msg, robot_name):
        self.robot_odom_received_at[robot_name] = (
            msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        )
        twist = msg.twist.twist
        self.robot_velocities[robot_name] = (
            math.hypot(twist.linear.x, twist.linear.y),
            abs(twist.angular.z),
        )
        if (self.task_state == "RALLY" and self.rally_hold_started_at is not None
                and robot_name in self.rally_targets
                and not all(math.isfinite(value) and value <= limit
                            for value, limit in zip(self.robot_velocities[robot_name],
                                (self.rally_linear_tolerance, self.rally_angular_tolerance)))):
            self.rally_hold_started_at = None
        transform = self.map_to_odom[robot_name]
        if transform is None:
            return
        odom_position = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
        )
        position = transform_point_2d(*odom_position, transform)
        self.robot_positions[robot_name] = position
        yaw = quaternion_yaw(msg.pose.pose.orientation) + quaternion_yaw(transform.rotation)
        self.robot_yaws[robot_name] = math.atan2(math.sin(yaw), math.cos(yaw))
        if (self.task_state == "RALLY" and self.rally_hold_started_at is not None
                and robot_name in self.rally_targets):
            target = self.rally_targets[robot_name]
            distance = math.dist(position, (target.x, target.y))
            if not math.isfinite(distance) or distance > self.rally_position_tolerance:
                self.rally_hold_started_at = None
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
                stamp = stamped_transform.header.stamp
                self.robot_tf_received_at[robot_name] = stamp.sec + stamp.nanosec / 1e9

    def robot_map_callback(self, msg, robot_name):
        self.robot_map_received_at[robot_name] = (
            msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        )
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
        return visible_unknown_gain(
            self.map_data, (row, column), INFORMATION_RADIUS_M / self.resolution
        )

    def assign_idle_robots(self):
        if getattr(self, "return_probe_paused", False):
            return
        search = (
            getattr(self, "target_search_active", False)
            and self.task_state in ("FOUND", "RALLY")
            and not self.fresh_target()
        )
        if self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED") and not search:
            return
        if search and (
            self.target_scan_robot is not None
            or any(self.rally_goal_handles.values())
            or any(self.rally_goal_pending.values())
            or self.survey_goal_handle is not None or self.survey_goal_pending
        ):
            return
        if self.map_data is None:
            return
        active_names = self.input_robot_names()
        if not all_robot_inputs_ready(
            {name: self.robot_positions[name] for name in active_names},
            {name: self.robot_maps[name] for name in active_names},
        ):
            return
        if not self.fresh_robot_inputs():
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
        active_explorers = sum(
            state == "active"
            for name, state in self.robot_states.items()
            if name in self.participating_robots()
        )
        max_concurrent = 1 if search else EXPLORATION_MAX_CONCURRENT
        if active_explorers >= max_concurrent or any(
            mode == "RETURNING" for mode in self.battery_modes.values()
        ):
            return
        if not idle_positions:
            return
        exclusions = self.active_exclusions()
        candidates = []
        diagnostics = {
            "frontier_groups": 0,
            "groups_with_viewpoints": 0,
            "candidate_assignments": 0,
        }
        if self.frontier_cache is None:
            self.frontier_cache = prepare_frontier_data(
                self.map_data, self.resolution
            )
        frontier_data = self.frontier_cache
        search_gain_cache = {}  # One immutable map/visit mask per admission batch.
        resume_intents = getattr(self, "exploration_resume_intents", {})
        charge_candidates = {}
        for refine in ((False, True, "known_space") if search else (False, True)):
            candidates = []
            resume_candidates = set()
            unfunded_candidates = set()
            diagnostics["frontier_groups"] = 0
            diagnostics["groups_with_viewpoints"] = 0
            for robot_name, position in idle_positions.items():
                robot_exclusions = list(exclusions)
                robot_exclusions.extend(
                    other_position
                    for other_name, other_position in self.robot_positions.items()
                    if (
                        other_name != robot_name
                        and other_name in self.participating_robots()
                        and self.robot_states[other_name] == "active"
                        and other_position is not None
                    )
                )
                if refine == "known_space":
                    robot_candidates = known_space_search_candidates(
                        self.map_data, self.resolution, self.origin, robot_name, position,
                        [*self.target_search_visits, *[p for p in self.robot_positions.values() if p is not None]],
                        robot_exclusions, [p for name,p in self.robot_positions.items() if name != robot_name and p is not None],
                        gain_cache=search_gain_cache)
                    robot_diagnostics = dict(frontier_groups=0, groups_with_viewpoints=0)
                else:
                    robot_candidates, robot_diagnostics = robot_candidate_assignments(
                        self.map_data,
                        self.resolution,
                        self.origin,
                        robot_name,
                        position,
                        robot_exclusions,
                        frontier_data,
                        **({"blocked_positions": [
                            other for name, other in self.robot_positions.items()
                            if name != robot_name and other is not None
                        ]} if refine else {}),
                    )
                diagnostics["frontier_groups"] += robot_diagnostics[
                    "frontier_groups"
                ]
                diagnostics["groups_with_viewpoints"] += robot_diagnostics[
                    "groups_with_viewpoints"
                ]
                for _, _, group_id, assignment in robot_candidates:
                    # Preserve reachability analysis for an unfunded frontier,
                    # but request charging instead of executing a trip that is
                    # already expected to be interrupted by local reserve.
                    battery_factor = self.exploration_battery_factor(
                        robot_name, assignment.path_distance_m,
                        (assignment.x, assignment.y),
                    )
                    if battery_factor <= 0:
                        continue
                    utility = assignment.utility * battery_factor
                    coordinated = Assignment(
                        assignment.viewpoint,
                        assignment.x,
                        assignment.y,
                        assignment.path_distance_m,
                        utility,
                        assignment.navigation_x,
                        assignment.navigation_y,
                    )
                    if battery_factor < 1.0:
                        unfunded_candidates.add((robot_name, coordinated))
                    if not search and interrupted_frontier_is_useful(
                        coordinated, resume_intents.get(robot_name), battery_factor
                    ):
                        resume_candidates.add((robot_name, coordinated))
                    candidates.append(
                        (utility, robot_name, group_id, coordinated)
                    )
            diagnostics["candidate_assignments"] = len(candidates)
            diagnostics["reachable_refinement"] = refine
            diagnostics["rejected_routes"] = 0
            diagnostics["stationary_candidates"] = 0
            # Reserve immediately after admission. A rejected high-utility route
            # must not hide the same robot's independent, lower-utility frontier.
            plans = {}
            routes = {}
            selected = []
            resuming_names = set()
            route_caches = {name: {} for name in idle_positions}
            reservations = [
                remaining_rally_route(route, self.robot_positions[name])
                for name, route in self.goal_routes.items()
                if self.robot_states[name] == "active" and route
            ]
            for _, name, _, assignment in sorted(candidates, key=lambda item: (
                (item[1], item[3]) not in resume_candidates, -item[0]
            )):
                if name in plans:
                    continue
                unfunded = (name, assignment) in unfunded_candidates
                previous_charge = charge_candidates.get(name)
                if (unfunded and previous_charge is not None
                        and assignment.utility <= previous_charge.utility):
                    continue  # One best feasible charge intent per idle peer.
                if any(
                    math.dist((assignment.x, assignment.y), (other.x, other.y))
                    < MIN_TARGET_SEPARATION_M for other in plans.values()
                ):
                    continue
                blocked = [
                    position for other_name, position in self.robot_positions.items()
                    if other_name != name and position is not None
                ]
                plan = plan_rally_leg(
                    RallyPose(assignment.x, assignment.y, 0.0),
                    self.map_data, self.resolution, self.origin,
                    self.robot_positions[name], MAX_NAVIGATION_LEG_M,
                    blocked_positions=blocked, clearance_m=PATH_CLEARANCE_M,
                    visible_only=True, route_cache=route_caches[name],
                )
                admitted = reserve_rally_prefix(plan, reservations)
                if admitted is None:
                    diagnostics["rejected_routes"] += 1
                    continue
                pose, route = admitted
                if (
                    math.dist(self.robot_positions[name], (pose.x, pose.y))
                    <= NAVIGATION_POSITION_TOLERANCE_M
                ):
                    diagnostics["stationary_candidates"] += 1
                    continue
                if unfunded:
                    if HeadquartersControl.exploration_charge_budget(self, name, assignment) is not None:
                        charge_candidates[name] = assignment
                    continue
                if name in getattr(self, 'rally_charge_requested', {}):
                    continue
                plans[name] = Assignment(
                    assignment.viewpoint, assignment.x, assignment.y,
                    assignment.path_distance_m, assignment.utility, pose.x, pose.y,
                    (pose.yaw if world_to_grid(pose.x, pose.y, self.resolution, *self.origin)
                     != world_to_grid(assignment.x, assignment.y, self.resolution, *self.origin)
                     else None),
                )
                routes[name] = route
                selected.append(name)
                if (name, assignment) in resume_candidates:
                    resuming_names.add(name)
                reservations.append(route)
                if len(selected) + active_explorers >= max_concurrent:
                    break
            if selected:
                if search:
                    self.target_search_basis = ("current_map_known_free_sweep" if refine == "known_space"
                                                else "current_map_frontiers")
                break
        # A robot with its own funded alternative still explores normally.
        # Otherwise stop new admissions until accepted peer actions drain,
        # including when those peers have enough energy for further work.
        charge_candidates = {name: assignment for name, assignment in charge_candidates.items()
                             if name not in plans}
        if not search:
            for name, assignment in plans.items():
                if (getattr(self, 'enable_battery', False) and HeadquartersControl.exploration_charge_budget(
                        self, name, assignment, allow_opportunity=True) is not None):
                    charge_candidates[name] = assignment
        if charge_candidates:
            if active_explorers or any(mode == 'CHARGING' for mode in self.battery_modes.values()):
                return
            if HeadquartersControl.request_exploration_charge(self, list(charge_candidates.items())):
                return
        if not selected:
            now = self.now()
            if now - self.last_no_assignment_log >= 10.0:
                self.get_logger().warn(
                    f"No safe cooperative frontier assignment: {diagnostics}; "
                    f"positions={self.robot_positions}; "
                    f"candidates={[(name, round(a.x, 3), round(a.y, 3)) for _, name, _, a in candidates[:12]]}"
                )
                self.last_no_assignment_log = now
            return
        for robot_name in selected:
            assignment = plans[robot_name]
            if robot_name not in resuming_names:
                resume_intents.pop(robot_name, None)
            else:
                self.get_logger().info(
                    f"Resuming {robot_name}'s interrupted search with a current, funded frontier."
                )
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

    def record_navigation_decision(self, robot_name, kind, goal_pose=None):
        event = {
            "event": "coordinator_navigation_decision", "event_time": self.now(),
            "robot": robot_name, "kind": kind, "task_phase": self.task_state,
            "inputs": self.input_freshness_details(),
        }
        if getattr(self, "map_self_return_cells", {}):
            event['planning_map_self_return_cells'] = self.map_self_return_cells
            event['planning_map_resolution_m'] = self.resolution
            event['planning_map_origin'] = self.origin
        if goal_pose is not None:
            event["requested_position"] = [goal_pose.pose.position.x, goal_pose.pose.position.y]
            event["current_position"] = list(self.robot_positions[robot_name])
            q = goal_pose.pose.orientation
            event["requested_yaw"] = math.atan2(
                2 * (q.w * q.z + q.x * q.y),
                1 - 2 * (q.y * q.y + q.z * q.z),
            )
        if kind == "target_reacquisition_exploration":
            event["search_basis"] = getattr(self, "target_search_basis", "current_map_frontiers")
            event["search_route"] = self.goal_routes[robot_name]
            event["map_resolution_m"] = self.resolution
        self.consumed_publisher.publish(String(data=json.dumps(event, sort_keys=True)))

    def send_goal(self, robot_name, assignment):
        if not self.fresh_robot_inputs():
            self.robot_states[robot_name] = "idle"
            self.goal_targets[robot_name] = None
            self.goal_routes[robot_name] = ()
            return
        if self.battery_modes[robot_name] != "ACTIVE":
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
        frontier = grid_to_world(
            assignment.viewpoint.frontier_row, assignment.viewpoint.frontier_column,
            self.resolution, *self.origin,
        )
        yaw = math.atan2(frontier[1] - assignment.navigation_y,
                         frontier[0] - assignment.navigation_x)
        if assignment.navigation_yaw is not None:
            yaw = assignment.navigation_yaw
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        self.record_navigation_decision(
            robot_name,
            "target_reacquisition_exploration"
            if getattr(self, "target_search_active", False) else "exploration",
            goal.pose,
        )
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
        if self.battery_modes[robot_name] != "ACTIVE" or any(
            mode == "RETURNING" for mode in self.battery_modes.values()
        ) or (getattr(self, "target_search_active", False) and self.fresh_target()):
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
        if (success and assignment is not None
                and getattr(self, 'task_state', None) in ('EXPLORE', 'FOUND_UNCONFIRMED')):
            completed = getattr(self, 'successful_exploration_legs', {})
            completed[robot_name] = completed.get(robot_name, 0) + 1
        resume_intents = getattr(self, "exploration_resume_intents", {})
        if self.battery_modes[robot_name] == "FAILED":
            resume_intents.pop(robot_name, None)
        elif (assignment is not None and not success
                and self.battery_preempted[robot_name]
                and getattr(self, "task_state", None) in ("EXPLORE", "FOUND_UNCONFIRMED")):
            # This is a future search preference, never an old navigation goal
            # to replay. Admission reselects current map candidates and checks
            # fresh inputs, complete energy budgets and live route reservations.
            resume_intents[robot_name] = (
                assignment.x, assignment.y, assignment.viewpoint.information_gain
            )
        elif (success and robot_name in resume_intents and assignment is not None
              and math.dist((assignment.navigation_x, assignment.navigation_y),
                            resume_intents[robot_name][:2]) <= MIN_TARGET_SEPARATION_M):
            resume_intents.pop(robot_name)
        if (success and getattr(self, "target_search_active", False)
                and not self.fresh_target() and self.fresh_robot_poses()):
            # A travelled search waypoint deserves a real full-heading scan;
            # map coverage or a visited neighborhood cannot replace detection.
            self.target_search_visits.append(self.robot_positions[robot_name])
            self.target_scan_steps[robot_name] = 0
            self.target_scan_next_robot = robot_name
            self.target_search_active = False
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
        self.robot_states[robot_name] = (
            "failed"
            if self.battery_modes[robot_name] == "FAILED"
            else "idle"
        )
        self.check_exploration_completion()

    def cancel_stalled_goals(self):
        if (self.task_state not in ("EXPLORE", "FOUND_UNCONFIRMED")
                and not getattr(self, "target_search_active", False)):
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
                if assignment is not None and self.fresh_robot_inputs()
                else 0
            )
            stale = self.fresh_robot_inputs() and goal_is_stale(
                self.goal_initial_gain[robot_name],
                remaining_gain,
                now - started_at,
            ) and (
                last_progress is not None
                and now - last_progress >= NO_PROGRESS_SEC
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
            and all(
                state in ("idle", "failed")
                for state in self.robot_states.values()
            )
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
