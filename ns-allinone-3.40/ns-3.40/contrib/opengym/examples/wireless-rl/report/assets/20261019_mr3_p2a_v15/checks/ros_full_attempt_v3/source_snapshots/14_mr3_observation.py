"""Deterministic received-information observation and joint action contract.

This module has no ROS or truth input. Native observed cells determine body
clearance and paths; the four compact CNN rasters are observation features only.
Candidate selection uses fused and already-delivered own-map frontiers, then
reserves per-robot reachable geometric representatives before farthest-point
sampling, with no task utility,
information-gain ranking, previous bad-goal memory or exploration fallback.
"""

import base64
import copy
import hashlib
import json
import math
import zlib

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from multi_robot_exploration.mr3_episode import elapsed_ns, timestamp_ns


SCHEMA = "mr3-observation-v3"
ROBOT_NAMES = ("tb1", "tb2", "tb3")
CANDIDATE_COUNT = 8
KEEP = 8
WAIT = 9
JOINT_ACTION_COUNT = 1000
POLICY_PERIOD_SEC = 1.0
COMMITMENT_SEC = 5.0
PHYSICAL_RADIUS_M = 0.25
CLEARANCE_MARGIN_M = 0.04
CLEARANCE_M = PHYSICAL_RADIUS_M + CLEARANCE_MARGIN_M
GOAL_XY_TOLERANCE_M = 0.10
TARGET_CLEARANCE_M = CLEARANCE_M + GOAL_XY_TOLERANCE_M
CANDIDATE_RULE_VERSION = "mr3-per-robot-geometric-staging-v4"
NAVIGATION_CANDIDATE_RULE_VERSION = "mr3-navigation-geometric-staging-v5"
NAVIGATION_COMPOSITION_VERSION = "mr3-own-known-shared-unknown-v1"
TARGET_SEPARATION_M = 2.0 * TARGET_CLEARANCE_M
STATE_MAX_AGE_SEC = 0.5
FRONTIER_STAGING_MAX_M = 1.0
GLOBAL_EXTENT_M = (-16.0, -16.0, 16.0, 16.0)
LOCAL_SIDE_M = 12.8
TASK_DURATION_SEC = 300.0
_PHASES = {"idle", "accepting", "active", "canceling", "unknown", "failed"}


def encode_joint_action(choices):
    """Encode tb1/tb2/tb3 digits as a1 * 100 + a2 * 10 + a3."""
    if len(choices) != 3 or any(
        isinstance(item, bool) or not isinstance(item, (int, np.integer))
        or not 0 <= item <= 9 for item in choices
    ):
        raise ValueError("three integer action digits in [0, 9] are required")
    return int(100 * choices[0] + 10 * choices[1] + choices[2])


def decode_joint_action(action):
    """Decode the fixed 1000-way joint action without changing robot order."""
    if isinstance(action, bool) or not isinstance(action, (int, np.integer)):
        raise ValueError("joint action must be an integer")
    if not 0 <= action < JOINT_ACTION_COUNT:
        raise ValueError("joint action must be in [0, 999]")
    return (int(action // 100), int(action // 10 % 10), int(action % 10))


def snapshot_digest(snapshot):
    """Hash the saved snapshot, excluding its own digest field."""
    payload = {key: value for key, value in snapshot.items() if key != "digest"}
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def decode_raster(raster):
    """Decode a saved raster into uint8 CHW occupancy/free/unknown flags."""
    if raster["encoding"] != "base64-zlib-u8-chw":
        raise ValueError("unknown raster encoding")
    raw = zlib.decompress(base64.b64decode(raster["data"], validate=True))
    return np.frombuffer(raw, dtype=np.uint8).reshape(raster["shape"]).copy()


def native_traversable(raw_grid, resolution):
    """Return conservative full-body free cells and clearance lower bounds.

    Any nonzero or unknown cell is blocked. Distance-to-blocked-cell-centre
    minus half its diagonal bounds distance to the blocked square. Outside the
    received map is unknown. This is deliberately independent of CNN raster size.
    """
    free = np.asarray(raw_grid) == 0
    if not free.size:
        return free, np.zeros(free.shape, dtype=float)
    padded = np.pad(free, 1, constant_values=False)
    clearance = np.maximum(
        0.0,
        ndimage.distance_transform_edt(padded)[1:-1, 1:-1] * resolution
        - resolution / math.sqrt(2.0),
    )
    return free & (clearance >= CLEARANCE_M), clearance


def _finite(value, default=None):
    if value is None:
        return default
    value = float(value)
    return value if math.isfinite(value) else default


def _age(now, stamp):
    stamp = _finite(stamp)
    return None if stamp is None else max(0.0, now - stamp)


def _robot_state(robot, now):
    navigation = robot.get("navigation") or {}
    phase = navigation.get("phase", "unknown")
    if phase not in _PHASES:
        phase = "unknown"
    source_stamp = _finite(robot.get("source_stamp"))
    received_stamp = _finite(robot.get("received_stamp"))
    values = {key: _finite(robot.get(key)) for key in ("x", "y", "yaw", "v", "w")}
    source_age = _age(now, source_stamp)
    received_age = _age(now, received_stamp)
    valid = bool(robot.get("valid", False)) and all(
        value is not None for value in values.values()
    )
    fresh = valid and source_stamp is not None and received_stamp is not None
    fresh = fresh and source_stamp <= now + 1e-6 and received_stamp <= now + 1e-6
    fresh = fresh and source_age <= STATE_MAX_AGE_SEC
    fresh = fresh and received_age <= STATE_MAX_AGE_SEC
    goal_x, goal_y = (_finite(navigation.get(key)) for key in ("goal_x", "goal_y"))
    nav_source = _finite(navigation.get("source_stamp"))
    nav_received = _finite(navigation.get("received_stamp"))
    nav = {
        "phase": phase, "goal_id": navigation.get("goal_id"),
        "goal_x": goal_x, "goal_y": goal_y,
        "commitment_until": _finite(navigation.get("commitment_until"), 0.0),
        "commitment_remaining_sec": max(
            0, elapsed_ns(now, _finite(navigation.get("commitment_until"), 0.0)),
        ) / 1e9,
        "source_stamp": nav_source, "received_stamp": nav_received,
        "source_age_sec": _age(now, nav_source),
        "received_age_sec": _age(now, nav_received),
        "missing": not bool(navigation),
        "receipt_missing": nav_source is None or nav_received is None,
        "source_metadata_missing": nav_source is None or nav_received is None,
        "receipt_sequence": navigation.get("sequence"),
        "progress_m": _finite(navigation.get("progress_m")),
        "accepted_goal_count": navigation.get("accepted_goal_count"),
        "last_failure": navigation.get("last_failure"),
    }
    for key in ("requested_at", "accepted_at", "created_at", "expires_at", "lease_until"):
        nav[key] = _finite(navigation.get(key))
    for key in (
        "command_id", "observation_version", "stop_reason", "last_terminal", "last_goal_id",
    ):
        nav[key] = copy.deepcopy(navigation.get(key))
    nav["owned"] = bool(navigation.get("owned", nav["goal_id"] is not None))
    nav["cancel_requested"] = bool(navigation.get("cancel_requested", False))
    nav["goal_age_sec"] = _age(now, nav["requested_at"])
    nav["acceptance_age_sec"] = _age(now, nav["accepted_at"])
    nav["goal_distance_m"] = (
        math.hypot(goal_x - values["x"], goal_y - values["y"])
        if None not in (goal_x, goal_y, values["x"], values["y"]) else None
    )
    history = []
    # Only already-delivered estimates supplied by the caller may enter here.
    for entry in robot.get("history", [])[-16:]:
        if not isinstance(entry, dict):
            continue
        point = {key: _finite(entry.get(key)) for key in ("x", "y", "source_stamp")}
        if all(value is not None for value in point.values()):
            history.append(point)
    return {
        "name": robot["name"], **values, "valid": bool(valid), "fresh": bool(fresh),
        "epoch": robot.get("epoch"), "sequence": robot.get("sequence"),
        "version": robot.get("version"),
        "odom_source_stamp": _finite(robot.get("odom_source_stamp")),
        "tf_source_stamp": _finite(robot.get("tf_source_stamp")),
        "tf_validity_stamp": _finite(robot.get("tf_validity_stamp")),
        "tf_validity_lead_sec": _finite(robot.get("tf_validity_lead_sec")),
        "sin_yaw": math.sin(values["yaw"]) if values["yaw"] is not None else 0.0,
        "cos_yaw": math.cos(values["yaw"]) if values["yaw"] is not None else 0.0,
        "source_stamp": source_stamp, "received_stamp": received_stamp,
        "source_age_sec": source_age, "received_age_sec": received_age,
        "missing": not valid, "navigation": nav, "history": history,
        "activity": copy.deepcopy(robot.get("activity")),
    }


def _cell(x, y, resolution, origin, shape):
    if x is None or y is None:
        return None
    row = math.floor((y - origin[1]) / resolution)
    column = math.floor((x - origin[0]) / resolution)
    return (row, column) if 0 <= row < shape[0] and 0 <= column < shape[1] else None


def _path_distances(traversable, seeds, resolution):
    """All observed-space robot paths, with eight neighbours and no corner cut."""
    ids = np.full(traversable.shape, -1, dtype=np.int32)
    ids[traversable] = np.arange(np.count_nonzero(traversable), dtype=np.int32)
    distances = np.full((len(seeds), int(np.count_nonzero(traversable))), np.inf)
    if not distances.shape[1]:
        return distances, ids
    sources, targets, weights = [], [], []
    height, width = traversable.shape
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        r0, r1 = 0, height - dr
        c0, c1 = max(0, -dc), min(width, width - dc)
        first = traversable[r0:r1, c0:c1]
        second = traversable[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
        connected = first & second
        if dr and dc:
            connected = connected & traversable[r0:r1, c0 + dc:c1 + dc]
            connected = connected & traversable[r0 + dr:r1 + dr, c0:c1]
        start = ids[r0:r1, c0:c1][connected]
        end = ids[r0 + dr:r1 + dr, c0 + dc:c1 + dc][connected]
        sources.extend((start, end))
        targets.extend((end, start))
        weight = resolution * math.hypot(dr, dc)
        weights.extend((np.full(len(start), weight), np.full(len(end), weight)))
    graph = coo_matrix((np.concatenate(weights), (
        np.concatenate(sources), np.concatenate(targets),
    )), shape=(distances.shape[1], distances.shape[1])).tocsr()
    for index, seed in enumerate(seeds):
        if seed is not None and traversable[seed]:
            distances[index] = dijkstra(graph, directed=False, indices=int(ids[seed]))
    return distances, ids


def _known_line(raw_grid, first, second):
    # Supercover: crossing a cell corner requires both side cells to be free.
    row, column = first
    end_row, end_column = second
    dx, dy = abs(end_column - column), abs(end_row - row)
    sx = 1 if end_column > column else -1
    sy = 1 if end_row > row else -1
    ix = iy = 0
    while True:
        if raw_grid[row, column] != 0:
            return False
        if ix == dx and iy == dy:
            return True
        decision = (1 + 2 * ix) * dy - (1 + 2 * iy) * dx
        if decision == 0:
            if raw_grid[row, column + sx] != 0 or raw_grid[row + sy, column] != 0:
                return False
            column += sx
            row += sy
            ix += 1
            iy += 1
        elif decision < 0:
            column += sx
            ix += 1
        else:
            row += sy
            iy += 1


def _frontiers(raw_grid):
    return (raw_grid == 0) & ndimage.binary_dilation(
        raw_grid < 0, structure=ndimage.generate_binary_structure(2, 1),
    )


def _candidate_frontiers(raw_grid, resolution, origin, robot_maps, path_maps):
    """Union received frontiers without replacing any fused occupancy value.

    Each own frontier centre projects to its containing fused native cell.
    Only a fused observed-free cell may contribute. Map eligibility and native
    geometry are the same validated delivered inputs used for own-map paths;
    unsafe robot seeds do not make an otherwise valid delivered map disappear.
    """
    frontier = _frontiers(raw_grid)
    sources = {"fused_received": {"native_frontier_cells": int(frontier.sum())}}
    if robot_maps is None:
        return frontier, sources
    for name in ROBOT_NAMES:
        metadata = path_maps[name]
        diagnostic = {
            "eligible": not metadata["missing"],
            "unavailable_reason": metadata["unavailable_reason"] if metadata["missing"] else None,
            "native_frontier_cells": 0, "projected_unique_inside_cells": 0,
            "projected_fused_free_cells": 0, "rejected_fused_unknown_or_occupied_cells": 0,
            "new_union_cells": 0,
        }
        sources[name] = diagnostic
        if metadata["missing"]:
            continue
        entry = robot_maps[name]
        own_cells = np.argwhere(_frontiers(np.asarray(entry["grid"])))
        diagnostic["native_frontier_cells"] = len(own_cells)
        points = (own_cells[:, ::-1] + .5) * metadata["native_resolution_m"]
        points += np.asarray(metadata["native_origin_m"])
        projected = np.floor((points - origin) / resolution).astype(np.int64)
        inside = ((projected[:, 0] >= 0) & (projected[:, 0] < raw_grid.shape[1])
                  & (projected[:, 1] >= 0) & (projected[:, 1] < raw_grid.shape[0]))
        cells = np.unique(projected[inside, ::-1], axis=0)
        diagnostic["projected_unique_inside_cells"] = len(cells)
        cells = cells[raw_grid[tuple(cells.T)] == 0]
        diagnostic["projected_fused_free_cells"] = len(cells)
        diagnostic["rejected_fused_unknown_or_occupied_cells"] = (
            diagnostic["projected_unique_inside_cells"] - len(cells))
        diagnostic["new_union_cells"] = int(np.count_nonzero(~frontier[tuple(cells.T)]))
        frontier[tuple(cells.T)] = True
    return frontier, sources


def _candidates(raw_grid, clearance, target_cells, target_paths, resolution, origin, states,
                *, frontier_mask=None, line_grids=None):
    """Project frontiers into each robot's reachable safe target component.

    ``target_paths`` contains native own-map paths to the fused target cells.
    Paths require body clearance; target cells additionally certify the whole
    declared Nav2 arrival disk. No robot utility or task reward ranks this pool.
    """
    frontier = _frontiers(raw_grid) if frontier_mask is None else frontier_mask
    labels, count = ndimage.label(frontier, structure=np.ones((3, 3), dtype=np.uint8))
    frontier_cells = np.argwhere(frontier)
    diagnostics = {
        "frontier_cells": int(len(frontier_cells)), "frontier_groups": int(count),
        "unsafe_or_occluded_frontier_cells": 0, "unreachable_staging_cells": 0,
        "geometric_pool_size": 0, "candidate_truncated": 0,
        "represented_frontier_groups": [], "omitted_frontier_groups": [],
        "per_robot_reachable_target_cells": [0] * 3,
        "per_robot_arrival_noop_cells": [0] * 3,
        "per_robot_reachable_pool_counts": [0] * 3,
        "per_robot_reachable_selected_counts": [0] * 3,
        "per_robot_staging_rejections": [
            {"no_reachable_safe_cells": 0, "beyond_staging_limit": 0,
             "occluded_staging_line": 0, "alternate_staging_searches": 0} for _ in states],
    }
    if not frontier_cells.size or not len(target_cells):
        diagnostics["unsafe_or_occluded_frontier_cells"] = int(len(frontier_cells))
        diagnostics["omitted_frontier_groups"] = list(range(1, int(count) + 1))
        for rejection in diagnostics["per_robot_staging_rejections"]:
            rejection["no_reachable_safe_cells"] = len(frontier_cells)
        return [], diagnostics
    target_paths = target_paths.copy()
    points = np.column_stack((origin[0] + (target_cells[:, 1] + .5) * resolution,
                              origin[1] + (target_cells[:, 0] + .5) * resolution))
    for index, robot in enumerate(states):
        if robot["x"] is not None and robot["y"] is not None:
            no_op = (np.linalg.norm(points - (robot["x"], robot["y"]), axis=1)
                     <= GOAL_XY_TOLERANCE_M)
            diagnostics["per_robot_arrival_noop_cells"][index] = int(np.count_nonzero(
                no_op & np.isfinite(target_paths[:, index])))
            target_paths[no_op, index] = np.inf
    reachable = np.isfinite(target_paths)
    diagnostics["per_robot_reachable_target_cells"] = np.count_nonzero(reachable, axis=0).tolist()
    target_ids = np.full(raw_grid.shape, -1, dtype=np.int32)
    target_ids[tuple(target_cells.T)] = np.arange(len(target_cells))
    pool = {}
    supported, occluded = set(), set()
    for robot_index in range(3):
        line_grid = raw_grid if line_grids is None else line_grids[robot_index]
        rejection = diagnostics["per_robot_staging_rejections"][robot_index]
        if not reachable[:, robot_index].any():
            rejection["no_reachable_safe_cells"] = len(frontier_cells)
            continue
        feasible = np.zeros(raw_grid.shape, dtype=bool)
        feasible_cells = target_cells[reachable[:, robot_index]]
        feasible[tuple(feasible_cells.T)] = True
        distance, nearest = ndimage.distance_transform_edt(~feasible, return_indices=True)
        alternatives = None
        for frontier_index, (frontier_row, frontier_column) in enumerate(frontier_cells):
            row = int(nearest[0, frontier_row, frontier_column])
            column = int(nearest[1, frontier_row, frontier_column])
            if distance[frontier_row, frontier_column] * resolution > FRONTIER_STAGING_MAX_M:
                rejection["beyond_staging_limit"] += 1
                continue
            if not _known_line(line_grid, (row, column), (frontier_row, frontier_column)):
                # A wall can hide the Euclidean-nearest reachable cell while
                # another equally safe cell has a known-free sightline. Search
                # the bounded geometric neighbourhood before rejecting this
                # frontier; nearest-distance/world-coordinate ties are fixed.
                rejection["alternate_staging_searches"] += 1
                if alternatives is None:
                    alternatives = cKDTree(feasible_cells.astype(float) * resolution)
                nearby = alternatives.query_ball_point(
                    np.asarray((frontier_row, frontier_column)) * resolution,
                    FRONTIER_STAGING_MAX_M)
                ordered = sorted((tuple(feasible_cells[index]) for index in nearby),
                                 key=lambda cell: (
                    (cell[0] - frontier_row) ** 2 + (cell[1] - frontier_column) ** 2,
                    cell[1], cell[0]))
                visible = next((cell for cell in ordered if _known_line(
                    line_grid, cell, (frontier_row, frontier_column))), None)
                if visible is None:
                    rejection["occluded_staging_line"] += 1
                    occluded.add(frontier_index)
                    continue
                row, column = map(int, visible)
            supported.add(frontier_index)
            entry = pool.setdefault((row, column), {"frontiers": set(), "groups": set()})
            entry["frontiers"].add(frontier_index)
            entry["groups"].add(int(labels[frontier_row, frontier_column]))
    diagnostics["unsafe_or_occluded_frontier_cells"] = len(occluded - supported)
    diagnostics["unreachable_staging_cells"] = len(frontier_cells) - len(supported | occluded)
    cells = sorted(pool, key=lambda item: (item[1], item[0]))
    diagnostics["geometric_pool_size"] = len(cells)
    diagnostics["candidate_truncated"] = max(0, len(cells) - CANDIDATE_COUNT)
    selected = []
    if cells:
        pool_ids = np.asarray([target_ids[cell] for cell in cells])
        pool_reachable = reachable[pool_ids]
        diagnostics["per_robot_reachable_pool_counts"] = np.count_nonzero(
            pool_reachable, axis=0).tolist()
        coordinates = np.asarray(cells, dtype=float) * resolution
        distances = np.full(len(cells), np.inf)
        selected_ids = []

        def select(index):
            selected_ids.append(index)
            selected.append(cells[index])
            delta = coordinates - coordinates[index]
            return np.minimum(distances, np.sum(delta * delta, axis=1))

        # Reserve a geometric representative only for a robot not yet covered.
        # Fixed robot order and lexicographic distance ties make replay stable.
        # At most three of K8 slots are reserved; no exploration goal is chosen.
        for robot_index in range(3):
            if pool_reachable[:, robot_index].any() and not any(
                    pool_reachable[index, robot_index] for index in selected_ids):
                eligible = np.where(pool_reachable[:, robot_index], distances, -1.)
                distances = select(int(np.argmax(eligible)))
                distances[selected_ids] = -1.
        while len(selected) < min(CANDIDATE_COUNT, len(cells)):
            distances = select(int(np.argmax(distances)))
            distances[selected_ids] = -1.
        diagnostics["per_robot_reachable_selected_counts"] = np.count_nonzero(
            pool_reachable[selected_ids], axis=0).tolist()
    result = []
    represented = set()
    for index, (row, column) in enumerate(selected):
        geometry = pool[row, column]
        represented.update(geometry["groups"])
        distances = [float(value) if np.isfinite(value) else None
                     for value in target_paths[target_ids[row, column]]]
        result.append({
            "index": index, "valid": True, "row": row, "column": column,
            "x": float(origin[0] + (column + 0.5) * resolution),
            "y": float(origin[1] + (row + 0.5) * resolution),
            "clearance_m": float(clearance[row, column]),
            "frontier_count": len(geometry["frontiers"]),
            "frontier_groups": sorted(geometry["groups"]),
            "reachable": [value is not None for value in distances],
            "path_distances_m": distances,
        })
    diagnostics["represented_frontier_groups"] = sorted(represented)
    diagnostics["omitted_frontier_groups"] = sorted(set(range(1, count + 1)) - represented)
    return result, diagnostics


def _received_grid(raw_grid):
    grid = np.asarray(raw_grid)
    if grid.ndim != 2 or not np.issubdtype(grid.dtype, np.integer):
        raise ValueError("received occupancy map must be a two-dimensional integer grid")
    if grid.size and (np.min(grid) < -1 or np.max(grid) > 100):
        raise ValueError("occupancy values must be in [-1, 100]")
    return grid.copy()


def _point_offset(point, cell, resolution, origin):
    centre = (origin[0] + (cell[1] + .5) * resolution,
              origin[1] + (cell[0] + .5) * resolution)
    return math.dist(point, centre)


def _seed_diagnostics(grid, traversable, clearance, robot, resolution, origin):
    """Certify the actual observed pose; never snap it to a nearby free cell."""
    seed = (_cell(robot["x"], robot["y"], resolution, origin, grid.shape)
            if robot["fresh"] else None)
    offset = (None if seed is None else _point_offset(
        (robot["x"], robot["y"]), seed, resolution, origin))
    cell_clearance = None if seed is None else float(clearance[seed])
    pose_clearance = None if seed is None else cell_clearance - offset
    reason = None
    if not robot["fresh"]:
        reason = "state_missing_or_stale"
    elif seed is None:
        reason = "pose_outside_received_map"
    elif grid[seed] != 0:
        reason = "seed_cell_unknown" if grid[seed] < 0 else "seed_cell_occupied"
    elif not traversable[seed]:
        reason = "seed_cell_body_clearance"
    elif pose_clearance < CLEARANCE_M:
        reason = "seed_pose_body_clearance"
    return seed, offset, {
        "seed_cell": None if seed is None else list(seed),
        "seed_cell_clearance_m": cell_clearance,
        "seed_pose_cell_offset_m": offset,
        "seed_pose_clearance_lower_bound_m": pose_clearance,
        "seed_required_clearance_m": CLEARANCE_M,
        "seed_rejection_reason": reason,
    }


def _own_map_paths(robot_maps, states, now, epoch, fused_resolution, fused_origin, target_cells,
                   *, source="delivered_own_map"):
    """Build each graph from that robot's unchanged, explicitly delivered map."""
    if not isinstance(robot_maps, dict) or set(robot_maps) - set(ROBOT_NAMES):
        raise ValueError("robot_maps must map only tb1/tb2/tb3 to delivered maps")
    provenance, seeds_valid = {}, []
    points = np.column_stack((fused_origin[0] + (target_cells[:, 1] + .5) * fused_resolution,
                              fused_origin[1] + (target_cells[:, 0] + .5) * fused_resolution))
    target_paths = np.full((len(target_cells), 3), np.inf)
    for robot_index, robot in enumerate(states):
        name = robot["name"]
        entry = robot_maps.get(name)
        missing_reason = ("missing_received_navigation_map"
                          if source == "delivered_navigation_map" else "missing_received_own_map")
        metadata = {
            "source": source, "missing": True,
            "epoch": None, "sequence": None, "version": None,
            "source_stamp": None, "received_stamp": None,
            "source_age_sec": None, "received_age_sec": None,
            "source_metadata_missing": True, "payload_sha256": None,
            "geometry_sha256": None, "native_shape": None,
            "native_resolution_m": None, "native_origin_m": None,
            "unavailable_reason": missing_reason,
            "seed_cell": None, "seed_cell_clearance_m": None,
            "seed_pose_cell_offset_m": None, "seed_pose_clearance_lower_bound_m": None,
            "seed_required_clearance_m": CLEARANCE_M,
            "seed_rejection_reason": missing_reason,
        }
        seed_valid = False
        if entry is not None and entry.get("grid") is not None:
            grid = _received_grid(entry["grid"])
            resolution = _finite(entry.get("resolution"))
            origin = entry.get("origin", ())
            if resolution is None or resolution <= 0 or len(origin) != 2 \
                    or any(_finite(value) is None for value in origin):
                raise ValueError("delivered own-map resolution/origin is invalid")
            origin = tuple(float(value) for value in origin)
            source_stamp = _finite(entry.get("source_stamp"))
            received_stamp = _finite(entry.get("received_stamp"))
            metadata.update({
                "missing": not bool(grid.size), "epoch": entry.get("epoch"),
                "sequence": entry.get("sequence"), "version": entry.get("version"),
                "source_stamp": source_stamp, "received_stamp": received_stamp,
                "source_age_sec": _age(now, source_stamp),
                "received_age_sec": _age(now, received_stamp),
                "source_metadata_missing": source_stamp is None or received_stamp is None,
                "payload_sha256": entry.get("payload_sha256"),
                "native_shape": list(grid.shape), "native_resolution_m": resolution,
                "native_origin_m": list(origin), "unavailable_reason": None,
            })
            geometry_hash = hashlib.sha256(json.dumps({
                "resolution": resolution, "origin": origin, "shape": list(grid.shape),
            }, sort_keys=True, separators=(",", ":")).encode())
            geometry_hash.update(np.asarray(grid, dtype="<i2").tobytes())
            metadata["geometry_sha256"] = geometry_hash.hexdigest()
            invalid_epoch = metadata["epoch"] is not None and metadata["epoch"] != epoch
            future = any(stamp is not None and stamp > now + 1e-6
                         for stamp in (source_stamp, received_stamp))
            if invalid_epoch or future:
                metadata["missing"] = True
                metadata["unavailable_reason"] = "cross_epoch" if invalid_epoch else "future_map"
                metadata["seed_rejection_reason"] = metadata["unavailable_reason"]
            elif grid.size:
                traversable, clearance = native_traversable(grid, resolution)
                seed, seed_offset, seed_diagnostics = _seed_diagnostics(
                    grid, traversable, clearance, robot, resolution, origin)
                metadata.update(seed_diagnostics)
                seed_valid = seed_diagnostics["seed_rejection_reason"] is None
                if seed_valid:
                    paths, ids = _path_distances(traversable, [seed], resolution)
                    # Project all fused target centres once, using each own
                    # map's actual origin/resolution. Vectorization keeps the
                    # per-robot staging search independent of map dimensions.
                    columns = np.floor((points[:, 0] - origin[0]) / resolution).astype(int)
                    rows = np.floor((points[:, 1] - origin[1]) / resolution).astype(int)
                    inside = ((rows >= 0) & (rows < grid.shape[0])
                              & (columns >= 0) & (columns < grid.shape[1]))
                    selected = np.flatnonzero(inside)
                    rr, cc = rows[selected], columns[selected]
                    offsets = np.hypot(points[selected, 0] - (origin[0] + (cc + .5) * resolution),
                                       points[selected, 1] - (origin[1] + (rr + .5) * resolution))
                    safe = (traversable[rr, cc]
                            & (clearance[rr, cc] - offsets >= TARGET_CLEARANCE_M))
                    selected, rr, cc, offsets = selected[safe], rr[safe], cc[safe], offsets[safe]
                    target_paths[selected, robot_index] = (
                        paths[0, ids[rr, cc]] + seed_offset + offsets)
                else:
                    metadata["unavailable_reason"] = "robot_seed_not_observed_safe"
            else:
                metadata["unavailable_reason"] = "empty_received_own_map"
                metadata["seed_rejection_reason"] = "empty_received_own_map"
        robot["path_map_available"] = not metadata["missing"]
        if source == "delivered_navigation_map":
            robot["path_map_source"] = source
            if entry is not None:
                for key in ("composition_version", "input_own_map_payload_sha256",
                            "input_shared_map_payload_sha256", "shared_map_version",
                            "received_stamp_scope", "input_own_source_stamp"):
                    metadata[key] = copy.deepcopy(entry.get(key))
        provenance[name] = metadata
        seeds_valid.append(seed_valid)
    return target_paths, provenance, seeds_valid


def _raster_integrals(raw_grid):
    return [np.pad(np.cumsum(np.cumsum(channel.astype(np.int32), axis=0), axis=1),
                   ((1, 0), (1, 0)))
            for channel in (raw_grid > 0, raw_grid == 0, raw_grid < 0)]


def _raster(integrals, shape, resolution, origin, extent, side):
    """Exact rectangular area intersection, with a flag per category present."""
    x0, y0, x1, y1 = extent
    edges_x = np.linspace(x0, x1, side + 1)
    edges_y = np.linspace(y0, y1, side + 1)
    # Numerical tolerance avoids treating touching boundaries as positive area.
    left = np.floor((edges_x[:-1] - origin[0]) / resolution + 1e-9).astype(int)
    right = np.ceil((edges_x[1:] - origin[0]) / resolution - 1e-9).astype(int)
    bottom = np.floor((edges_y[:-1] - origin[1]) / resolution + 1e-9).astype(int)
    top = np.ceil((edges_y[1:] - origin[1]) / resolution - 1e-9).astype(int)
    outside = ((bottom[:, None] < 0) | (top[:, None] > shape[0])
               | (left[None, :] < 0) | (right[None, :] > shape[1]))
    left, right = np.clip(left, 0, shape[1]), np.clip(right, 0, shape[1])
    bottom, top = np.clip(bottom, 0, shape[0]), np.clip(top, 0, shape[0])
    channels = []
    for integral in integrals:
        area = (integral[top[:, None], right[None, :]]
                - integral[bottom[:, None], right[None, :]]
                - integral[top[:, None], left[None, :]]
                + integral[bottom[:, None], left[None, :]])
        channels.append((area > 0).astype(np.uint8))
    channels[2][outside] = 1
    array = np.stack(channels)
    return {
        "encoding": "base64-zlib-u8-chw", "shape": list(array.shape),
        "channels": ["occupied", "free", "unknown"],
        "aggregation": "any-positive-area-intersection; channels may overlap",
        "extent_m": [float(value) for value in extent], "orientation": "map-axis-aligned",
        "resolution_m": [(x1 - x0) / side, (y1 - y0) / side],
        "data": base64.b64encode(zlib.compress(array.tobytes(), level=6)).decode("ascii"),
    }


def _action_masks(robots, candidates, now):
    per_robot, reasons = [], []
    for index, robot in enumerate(robots):
        nav = robot["navigation"]
        mask = [False] * 10
        mask[KEEP] = True
        why = {}
        if not robot["fresh"]:
            why["state_missing_or_stale"] = list(range(8)) + [WAIT]
        elif robot.get("path_map_available") is False:
            reason = ("received_navigation_map_missing"
                      if robot.get("path_map_source") == "delivered_navigation_map"
                      else "received_own_map_missing")
            why[reason] = list(range(8)) + [WAIT]
        elif nav["phase"] not in ("idle", "active"):
            why["protocol_" + nav["phase"]] = list(range(8)) + [WAIT]
        elif (nav["phase"] == "active"
              and timestamp_ns(nav["commitment_until"]) > timestamp_ns(now)):
            why["minimum_commitment"] = list(range(8)) + [WAIT]
        else:
            mask[WAIT] = True
            for candidate in candidates:
                action = candidate["index"]
                mask[action] = candidate["valid"] and candidate["reachable"][index]
                if not mask[action]:
                    why.setdefault("candidate_missing_or_unreachable", []).append(action)
        per_robot.append(mask)
        reasons.append(why)
    joint, conflicts = [], []
    for action in range(JOINT_ACTION_COUNT):
        choices = decode_joint_action(action)
        valid = all(per_robot[index][choice] for index, choice in enumerate(choices))
        if valid:
            targets, target_radii = [], []
            for index, choice in enumerate(choices):
                if choice < CANDIDATE_COUNT:
                    targets.append((candidates[choice]["x"], candidates[choice]["y"]))
                    target_radii.append(TARGET_CLEARANCE_M)
                else:
                    nav = robots[index]["navigation"]
                    if nav["phase"] in ("active", "accepting", "canceling", "unknown"):
                        targets.append((nav["goal_x"], nav["goal_y"]))
                        target_radii.append(TARGET_CLEARANCE_M)
                    else:
                        targets.append((robots[index]["x"], robots[index]["y"]))
                        target_radii.append(CLEARANCE_M)
            for first in range(3):
                for second in range(first + 1, 3):
                    # Preserve existing KEEP/WAIT ownership, including a conflict
                    # inherited from prior observations; never mask all-KEEP.
                    if choices[first] >= CANDIDATE_COUNT and choices[second] >= CANDIDATE_COUNT:
                        continue
                    if all(value is not None for value in targets[first] + targets[second]):
                        if math.dist(targets[first], targets[second]) < (
                                target_radii[first] + target_radii[second]):
                            valid = False
            if not valid:
                conflicts.append(action)
        joint.append(valid)
    return per_robot, joint, {
        "per_robot": reasons, "joint_target_conflict_count": len(conflicts),
        "joint_target_conflict_actions": conflicts,
    }


def build_snapshot(raw_grid, resolution, origin, robots, now, epoch, map_version,
                   sequence, *, map_source_stamp=None, map_received_stamp=None,
                   map_sources=None, task_start=None, robot_maps=None, navigation_maps=None):
    """Build one self-contained JSON snapshot; consumers save it with the action.

    Robots must be exactly tb1/tb2/tb3 with names, estimated x/y/yaw, measured
    v/w, validity, source/receive stamps and navigation ownership context. Input
    ordering does not matter. ``None`` map and missing/invalid state produce a
    valid missing-data snapshot and KEEP actions, rather than invented free map.
    Epoch and versions identify the immutable candidate/action meaning.
    Runtime ``navigation_maps`` supplies the exact delivered navigation maps
    used by Nav2 and candidate paths/arrival disks. Missing maps never fall back
    to own/fused maps. Entries include grid, resolution, origin, source identity
    and explicit composition metadata. ``robot_maps`` without navigation maps
    retains the older received-own-map interface; omitting both retains the
    fused-map legacy API. These legacy modes do not substitute for runtime data.
    """
    now, resolution = float(now), float(resolution)
    if not math.isfinite(now) or not math.isfinite(resolution) or resolution <= 0:
        raise ValueError("finite now and positive native resolution are required")
    if len(origin) != 2 or any(_finite(value) is None for value in origin):
        raise ValueError("map origin must contain finite x/y")
    if not isinstance(epoch, str) or not epoch:
        raise ValueError("a nonempty episode epoch is required")
    if any(isinstance(value, bool) or not isinstance(value, (int, np.integer))
           or value < 0 for value in (map_version, sequence)):
        raise ValueError("map_version and sequence must be nonnegative integers")
    if len(robots) != 3 or {robot.get("name") for robot in robots} != set(ROBOT_NAMES):
        raise ValueError("exactly tb1, tb2 and tb3 are required")
    by_name = {robot["name"]: robot for robot in robots}
    states = [_robot_state(by_name[name], now) for name in ROBOT_NAMES]
    missing_map = raw_grid is None
    grid = np.empty((0, 0), dtype=np.int8) if missing_map else _received_grid(raw_grid)
    traversable, clearance = native_traversable(grid, resolution)
    target_cells = np.argwhere(traversable & (clearance >= TARGET_CLEARANCE_M))
    navigation_grids = None
    if navigation_maps is not None:
        target_cells = np.argwhere(np.ones(grid.shape, dtype=bool))
        target_paths, path_maps, seeds_valid = _own_map_paths(
            navigation_maps, states, now, epoch, resolution, origin, target_cells,
            source="delivered_navigation_map")
        navigation_grids = []
        navigation_clearances = []
        for name in ROBOT_NAMES:
            entry, metadata = navigation_maps.get(name), path_maps[name]
            if metadata["missing"]:
                native = np.full(grid.shape, -1, dtype=np.int8)
            else:
                if (metadata["native_shape"] != list(grid.shape)
                        or metadata["native_resolution_m"] != resolution
                        or metadata["native_origin_m"] != list(origin)):
                    raise ValueError("navigation map must use the delivered fused native lattice")
                if entry.get("composition_version") != NAVIGATION_COMPOSITION_VERSION:
                    raise ValueError("unknown delivered navigation composition")
                native = _received_grid(entry["grid"])
            navigation_grids.append(native)
            navigation_clearances.append(native_traversable(native, resolution)[1])
    elif robot_maps is None:
        seed_data = [_seed_diagnostics(grid, traversable, clearance, robot, resolution, origin)
                     for robot in states]
        seeds_valid = [entry[2]["seed_rejection_reason"] is None for entry in seed_data]
        seeds = [entry[0] if valid else None for entry, valid in zip(seed_data, seeds_valid)]
        paths, ids = _path_distances(traversable, seeds, resolution)
        path_maps = {name: {
            "source": "fused_map_legacy_api", "missing": missing_map or not bool(grid.size),
            "epoch": epoch, "version": int(map_version),
            "source_stamp": _finite(map_source_stamp),
            "received_stamp": _finite(map_received_stamp),
            **entry[2],
        } for name, entry in zip(ROBOT_NAMES, seed_data)}
        target_paths = paths[:, ids[tuple(target_cells.T)]].T.copy()
        for index, (entry, valid) in enumerate(zip(seed_data, seeds_valid)):
            if valid:
                target_paths[:, index] += entry[1]
    else:
        target_paths, path_maps, seeds_valid = _own_map_paths(
            robot_maps, states, now, epoch, resolution, origin, target_cells,
        )
    if navigation_grids is None:
        frontier, frontier_sources = _candidate_frontiers(
            grid, resolution, origin, robot_maps, path_maps)
    else:
        individual = [_frontiers(native) for native in navigation_grids]
        frontier = np.logical_or.reduce(individual)
        frontier_sources = {name: {"native_frontier_cells": int(mask.sum()),
                                   "eligible": not path_maps[name]["missing"]}
                            for name, mask in zip(ROBOT_NAMES, individual)}
    candidates, diagnostics = _candidates(
        grid, clearance, target_cells, target_paths, resolution, origin, states,
        frontier_mask=frontier, line_grids=navigation_grids,
    )
    if navigation_grids is not None:
        for candidate in candidates:
            cell = (candidate["row"], candidate["column"])
            candidate["clearance_by_robot_m"] = [
                float(native[cell]) if candidate["reachable"][index] else None
                for index, native in enumerate(navigation_clearances)]
            candidate["clearance_m"] = min(value for value in candidate[
                "clearance_by_robot_m"] if value is not None)
    while len(candidates) < CANDIDATE_COUNT:
        candidates.append({
            "index": len(candidates), "valid": False, "x": None, "y": None,
            "row": None, "column": None, "clearance_m": None,
            "frontier_count": 0, "frontier_groups": [],
            "reachable": [False] * 3, "path_distances_m": [None] * 3,
        })
    if navigation_grids is not None:
        for candidate in candidates:
            candidate.setdefault("clearance_by_robot_m", [None] * 3)
    candidate_rule = {
        "version": CANDIDATE_RULE_VERSION, "path_body_clearance_m": CLEARANCE_M,
        "goal_xy_tolerance_m": GOAL_XY_TOLERANCE_M,
        "target_clearance_m": TARGET_CLEARANCE_M,
        "new_goal_pair_separation_m": TARGET_SEPARATION_M,
        "new_goal_idle_separation_m": TARGET_CLEARANCE_M + CLEARANCE_M,
        "frontier_staging_max_m": FRONTIER_STAGING_MAX_M,
        "frontier_sources": ["fused_received", "received_own:tb1", "received_own:tb2",
                             "received_own:tb3"],
        "frontier_projection": (
            "world cell centre to containing fused native cell; free endpoints only"),
    }
    if navigation_grids is not None:
        candidate_rule.update({
            "version": NAVIGATION_CANDIDATE_RULE_VERSION,
            "path_map_source": "delivered_navigation_map",
            "navigation_composition": NAVIGATION_COMPOSITION_VERSION,
            "frontier_sources": ["received_navigation:" + name for name in ROBOT_NAMES],
            "frontier_projection": (
                "same delivered fused native lattice; navigation-free sightlines"),
        })
    candidate_version = hashlib.sha256(json.dumps({
        "epoch": epoch, "map_version": int(map_version), "sequence": int(sequence),
        "candidate_rule": candidate_rule, "candidates": candidates, "path_maps": path_maps,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    per_robot, joint, mask_reasons = _action_masks(states, candidates, now)
    arrival_safe_count = len(target_cells)
    if navigation_grids is not None:
        arrival_safe_count = int(np.count_nonzero(np.logical_or.reduce([
            values >= TARGET_CLEARANCE_M for values in navigation_clearances])))
    integrals = _raster_integrals(grid)
    global_raster = _raster(
        integrals, grid.shape, resolution, origin, GLOBAL_EXTENT_M, 128,
    )
    locals_ = []
    for robot in states:
        x, y = robot["x"] or 0.0, robot["y"] or 0.0
        half = LOCAL_SIDE_M / 2.0
        raster = _raster(integrals, grid.shape, resolution, origin,
                         (x - half, y - half, x + half, y + half), 64)
        raster["name"] = robot["name"]
        raster["pose_missing"] = not robot["valid"]
        locals_.append(raster)
    elapsed = None if task_start is None else max(0.0, now - float(task_start))
    snapshot = {
        "schema": SCHEMA, "epoch": epoch, "sequence": int(sequence),
        "map_version": int(map_version), "candidate_version": candidate_version,
        "candidate_rule": candidate_rule,
        "source_stamp": now, "policy_period_sec": POLICY_PERIOD_SEC,
        "task_elapsed_sec": elapsed,
        "task_remaining_sec": None if elapsed is None else max(0.0, TASK_DURATION_SEC - elapsed),
        "robot_order": list(ROBOT_NAMES), "robots": states,
        "map": {
            "missing": missing_map or not bool(grid.size), "version": int(map_version),
            "source_stamp": _finite(map_source_stamp),
            "received_stamp": _finite(map_received_stamp),
            "source_age_sec": _age(now, map_source_stamp),
            "received_age_sec": _age(now, map_received_stamp),
            "source_metadata_missing": (
                _finite(map_source_stamp) is None or _finite(map_received_stamp) is None
            ),
            "sources": copy.deepcopy(map_sources or {}), "native_shape": list(grid.shape),
            "native_resolution_m": resolution,
            "native_origin_m": [float(value) for value in origin],
        },
        "maps": {"global": global_raster, "locals": locals_},
        "path_maps": path_maps,
        "candidates": candidates, "per_robot_action_mask": per_robot,
        "joint_action_mask": joint, "action_encoding": "a_tb1*100+a_tb2*10+a_tb3",
        "keep_action": KEEP, "wait_action": WAIT,
        "diagnostics": {**diagnostics, "frontier_sources": frontier_sources,
                        "mask_reasons": mask_reasons,
                        "native_safe_cells": int(np.count_nonzero(traversable)),
                        "native_arrival_safe_cells": arrival_safe_count,
                        "robot_seed_traversable": seeds_valid,
                        "robot_seed_diagnostics": [
                            {key: value for key, value in path_maps[name].items()
                             if key.startswith("seed_")}
                            for name in ROBOT_NAMES],
                        "path_map_source": [path_maps[name]["source"] for name in ROBOT_NAMES],
                        "candidate_selection": (
                            "per-robot staging/reservation; geometric farthest point"),
                        "clearance_m": CLEARANCE_M},
    }
    if navigation_maps is not None:
        snapshot["navigation_sources"] = {
            name: {key: copy.deepcopy(value) for key, value in entry.items()
                   if key not in ("grid", "resolution", "origin")}
            for name, entry in navigation_maps.items()
        }
    snapshot["digest"] = snapshot_digest(snapshot)
    return snapshot
