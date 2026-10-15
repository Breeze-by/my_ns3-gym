"""Deterministic received-information observation and joint action contract.

This module has no ROS or truth input. Native observed cells determine body
clearance and paths; the four compact CNN rasters are observation features only.
Candidate selection is geometric farthest-point sampling, with no task utility,
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


SCHEMA = "mr3-observation-v2"
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
TARGET_SEPARATION_M = 2.0 * CLEARANCE_M
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
            0.0, _finite(navigation.get("commitment_until"), 0.0) - now,
        ),
        "source_stamp": nav_source, "received_stamp": nav_received,
        "source_age_sec": _age(now, nav_source),
        "received_age_sec": _age(now, nav_received),
        "missing": not bool(navigation),
        "receipt_missing": nav_source is None or nav_received is None,
        "source_metadata_missing": nav_source is None or nav_received is None,
        "receipt_sequence": navigation.get("sequence"),
        "progress_m": _finite(navigation.get("progress_m")),
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


def _candidates(raw_grid, traversable, clearance, path_lookup, resolution, origin):
    unknown = raw_grid < 0
    adjacent_unknown = ndimage.binary_dilation(
        unknown, structure=ndimage.generate_binary_structure(2, 1),
    )
    frontier = (raw_grid == 0) & adjacent_unknown
    labels, count = ndimage.label(frontier, structure=np.ones((3, 3), dtype=np.uint8))
    frontier_cells = np.argwhere(frontier)
    diagnostics = {
        "frontier_cells": int(len(frontier_cells)), "frontier_groups": int(count),
        "unsafe_or_occluded_frontier_cells": 0, "unreachable_staging_cells": 0,
        "geometric_pool_size": 0, "candidate_truncated": 0,
        "represented_frontier_groups": [], "omitted_frontier_groups": [],
    }
    if not frontier_cells.size or not np.any(traversable):
        diagnostics["unsafe_or_occluded_frontier_cells"] = int(len(frontier_cells))
        diagnostics["omitted_frontier_groups"] = list(range(1, int(count) + 1))
        return [], diagnostics
    distance, nearest = ndimage.distance_transform_edt(
        ~traversable, return_indices=True,
    )
    pool = {}
    for frontier_row, frontier_column in frontier_cells:
        row = int(nearest[0, frontier_row, frontier_column])
        column = int(nearest[1, frontier_row, frontier_column])
        if distance[frontier_row, frontier_column] * resolution > FRONTIER_STAGING_MAX_M:
            diagnostics["unsafe_or_occluded_frontier_cells"] += 1
            continue
        if not _known_line(raw_grid, (row, column), (frontier_row, frontier_column)):
            diagnostics["unsafe_or_occluded_frontier_cells"] += 1
            continue
        distances = path_lookup(row, column)
        if not any(value is not None for value in distances):
            diagnostics["unreachable_staging_cells"] += 1
            continue
        entry = pool.setdefault((row, column), {"frontier_count": 0, "groups": set()})
        entry["frontier_count"] += 1
        entry["groups"].add(int(labels[frontier_row, frontier_column]))
    # First lexicographic world x/y, then farthest from all selected points.
    # Distance ties use the same fixed lexicographic order, never robot utility.
    cells = sorted(pool, key=lambda item: (item[1], item[0]))
    diagnostics["geometric_pool_size"] = len(cells)
    diagnostics["candidate_truncated"] = max(0, len(cells) - CANDIDATE_COUNT)
    selected = []
    if cells:
        coordinates = np.asarray(cells, dtype=float) * resolution
        distances = np.full(len(cells), np.inf)
        selected_index = 0
        for _ in range(min(CANDIDATE_COUNT, len(cells))):
            selected.append(cells[selected_index])
            delta = coordinates - coordinates[selected_index]
            distances = np.minimum(distances, np.sum(delta * delta, axis=1))
            distances[[cells.index(cell) for cell in selected]] = -1.0
            selected_index = int(np.argmax(distances))
    result = []
    represented = set()
    for index, (row, column) in enumerate(selected):
        geometry = pool[row, column]
        represented.update(geometry["groups"])
        distances = path_lookup(row, column)
        result.append({
            "index": index, "valid": True, "row": row, "column": column,
            "x": float(origin[0] + (column + 0.5) * resolution),
            "y": float(origin[1] + (row + 0.5) * resolution),
            "clearance_m": float(clearance[row, column]),
            "frontier_count": geometry["frontier_count"],
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


def _own_map_paths(robot_maps, states, now, epoch, fused_resolution, fused_origin):
    """Build each graph from that robot's unchanged, explicitly delivered map."""
    if not isinstance(robot_maps, dict) or set(robot_maps) - set(ROBOT_NAMES):
        raise ValueError("robot_maps must map only tb1/tb2/tb3 to delivered maps")
    contexts, provenance, seeds_valid = [], {}, []
    for robot in states:
        name = robot["name"]
        entry = robot_maps.get(name)
        metadata = {
            "source": "delivered_own_map", "missing": True,
            "epoch": None, "sequence": None, "version": None,
            "source_stamp": None, "received_stamp": None,
            "source_age_sec": None, "received_age_sec": None,
            "source_metadata_missing": True, "payload_sha256": None,
            "geometry_sha256": None, "native_shape": None,
            "native_resolution_m": None, "native_origin_m": None,
            "unavailable_reason": "missing_received_own_map",
        }
        context = None
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
            elif grid.size:
                traversable, clearance = native_traversable(grid, resolution)
                seed = (_cell(robot["x"], robot["y"], resolution, origin, grid.shape)
                        if robot["fresh"] else None)
                seed_offset = (None if seed is None else _point_offset(
                    (robot["x"], robot["y"]), seed, resolution, origin))
                seed_valid = bool(seed is not None and traversable[seed]
                                  and clearance[seed] - seed_offset >= CLEARANCE_M)
                if seed_valid:
                    paths, ids = _path_distances(traversable, [seed], resolution)
                    context = (grid.shape, resolution, origin, traversable, clearance,
                               paths[0], ids, seed_offset)
                else:
                    metadata["unavailable_reason"] = "robot_seed_not_observed_safe"
        robot["path_map_available"] = not metadata["missing"]
        provenance[name] = metadata
        contexts.append(context)
        seeds_valid.append(seed_valid)
    cache = {}

    def lookup(row, column):
        key = (row, column)
        if key in cache:
            return cache[key]
        point = (fused_origin[0] + (column + .5) * fused_resolution,
                 fused_origin[1] + (row + .5) * fused_resolution)
        result = []
        for context in contexts:
            distance = None
            if context is not None:
                (shape, resolution, origin, traversable, clearance,
                 paths, ids, start_offset) = context
                target = _cell(*point, resolution, origin, shape)
                if target is not None and traversable[target]:
                    offset = _point_offset(point, target, resolution, origin)
                    if clearance[target] - offset >= CLEARANCE_M:
                        path = paths[ids[target]]
                        if np.isfinite(path):
                            distance = float(path + start_offset + offset)
            result.append(distance)
        cache[key] = result
        return result

    return lookup, provenance, seeds_valid


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
            why["received_own_map_missing"] = list(range(8)) + [WAIT]
        elif nav["phase"] not in ("idle", "active"):
            why["protocol_" + nav["phase"]] = list(range(8)) + [WAIT]
        elif nav["phase"] == "active" and nav["commitment_until"] > now:
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
            targets = []
            for index, choice in enumerate(choices):
                if choice < CANDIDATE_COUNT:
                    targets.append((candidates[choice]["x"], candidates[choice]["y"]))
                else:
                    nav = robots[index]["navigation"]
                    if nav["phase"] in ("active", "accepting", "canceling", "unknown"):
                        targets.append((nav["goal_x"], nav["goal_y"]))
                    else:
                        targets.append((robots[index]["x"], robots[index]["y"]))
            for first in range(3):
                for second in range(first + 1, 3):
                    # Preserve existing KEEP/WAIT ownership, including a conflict
                    # inherited from prior observations; never mask all-KEEP.
                    if choices[first] >= CANDIDATE_COUNT and choices[second] >= CANDIDATE_COUNT:
                        continue
                    if all(value is not None for value in targets[first] + targets[second]):
                        if math.dist(targets[first], targets[second]) < TARGET_SEPARATION_M:
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
                   map_sources=None, task_start=None, robot_maps=None):
    """Build one self-contained JSON snapshot; consumers save it with the action.

    Robots must be exactly tb1/tb2/tb3 with names, estimated x/y/yaw, measured
    v/w, validity, source/receive stamps and navigation ownership context. Input
    ordering does not matter. ``None`` map and missing/invalid state produce a
    valid missing-data snapshot and KEEP actions, rather than invented free map.
    Epoch and versions identify the immutable candidate/action meaning.
    When ``robot_maps`` is supplied, only each robot's explicitly delivered own
    local map defines its path; absent maps never fall back to fusion. Entries
    contain grid, resolution, origin, epoch/sequence/version, source_stamp,
    received_stamp and payload_sha256. Fused-map paths remain an explicit legacy
    API mode only when ``robot_maps is None``; runtime MR3 uses received own maps.
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
    if robot_maps is None:
        seeds = [_cell(robot["x"], robot["y"], resolution, origin, grid.shape)
                 if robot["fresh"] else None for robot in states]
        paths, ids = _path_distances(traversable, seeds, resolution)
        seeds_valid = [bool(seed is not None and traversable[seed]) for seed in seeds]
        path_maps = {name: {
            "source": "fused_map_legacy_api", "missing": missing_map or not bool(grid.size),
            "epoch": epoch, "version": int(map_version),
            "source_stamp": _finite(map_source_stamp),
            "received_stamp": _finite(map_received_stamp),
        } for name in ROBOT_NAMES}

        def path_lookup(row, column):
            return [float(value) if np.isfinite(value) else None
                    for value in paths[:, ids[row, column]]]
    else:
        path_lookup, path_maps, seeds_valid = _own_map_paths(
            robot_maps, states, now, epoch, resolution, origin,
        )
    candidates, diagnostics = _candidates(
        grid, traversable, clearance, path_lookup, resolution, origin,
    )
    while len(candidates) < CANDIDATE_COUNT:
        candidates.append({
            "index": len(candidates), "valid": False, "x": None, "y": None,
            "row": None, "column": None, "clearance_m": None,
            "frontier_count": 0, "frontier_groups": [],
            "reachable": [False] * 3, "path_distances_m": [None] * 3,
        })
    candidate_version = hashlib.sha256(json.dumps({
        "epoch": epoch, "map_version": int(map_version), "sequence": int(sequence),
        "candidates": candidates, "path_maps": path_maps,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    per_robot, joint, mask_reasons = _action_masks(states, candidates, now)
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
        "diagnostics": {**diagnostics, "mask_reasons": mask_reasons,
                        "native_safe_cells": int(np.count_nonzero(traversable)),
                        "robot_seed_traversable": seeds_valid,
                        "path_map_source": [path_maps[name]["source"] for name in ROBOT_NAMES],
                        "candidate_selection": "lexicographic-seeded geometric farthest point",
                        "clearance_m": CLEARANCE_M},
    }
    snapshot["digest"] = snapshot_digest(snapshot)
    return snapshot
