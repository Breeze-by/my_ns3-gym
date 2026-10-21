"""Exact, local received-grid certificate for an unchanged seed's pose bridge.

Use only after the original seed cell is free and passes its UNCHANGED cell/
graph gate, when the old scalar pose bound alone rejected it. This module never
selects a seed, snaps a pose, changes graph membership or changes a map. Only
zero-valued cells are free; all other integer cells and the map exterior block.

The result proves distance >= 29/100 m for the supplied estimated point and its
whole straight segment to that SAME seed centre, under this observed-square
model. It does not establish physical pose, tracking, source freshness, peer
safety, native qualification, or an exploration policy. Squared distances are
exact but capped at the threshold; no global nearest-distance claim is made.
"""

from fractions import Fraction as Q
import math

import numpy as np

from .mr3_reach_geometry import exact


REQUIRED_M = Q(29, 100)
REQUIRED_SQUARED = REQUIRED_M ** 2


def _number(value):
    """Preserve actual numeric values; never silently round wider floats."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("boolean is not a geometric number")
    if isinstance(value, np.integer):
        value = int(value)
    elif isinstance(value, np.floating):
        if value.dtype.itemsize > 8:
            raise ValueError("floating geometry wider than binary64 is unsupported")
        value = float(value)  # Exact widening for float16/32; unchanged float64.
    return exact(value)


def _xy(value):
    if isinstance(value, np.ndarray):
        if value.ndim != 1 or value.size != 2:
            raise ValueError("two-dimensional XY vector required")
    elif not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("two-dimensional XY vector required")
    return tuple(_number(item) for item in value)


def _seed(value):
    if isinstance(value, np.ndarray):
        if value.ndim != 1 or value.size != 2:
            raise ValueError("original row/column seed required")
    elif not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("original row/column seed required")
    result = []
    for item in value:
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, (int, np.integer)):
            raise ValueError("original seed indices must be integers")
        result.append(int(item))
    return tuple(result)


def _point_rectangle_squared(p, box):
    dx = max(box[0] - p[0], Q(0), p[0] - box[2])
    dy = max(box[1] - p[1], Q(0), p[1] - box[3])
    return dx * dx + dy * dy


def _point_segment_squared(p, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    t = Q(0) if not length2 else max(Q(0), min(Q(1),
        ((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / length2))
    return (p[0] - start[0] - t * dx) ** 2 + (p[1] - start[1] - t * dy) ** 2


def _segment_rectangle_squared(start, end, box):
    lower, upper = Q(0), Q(1)
    intersects = True
    for axis, lo, hi in ((0, box[0], box[2]), (1, box[1], box[3])):
        delta = end[axis] - start[axis]
        if not delta:
            if not lo <= start[axis] <= hi:
                intersects = False
                break
        else:
            a, b = sorted(((lo - start[axis]) / delta, (hi - start[axis]) / delta))
            lower, upper = max(lower, a), min(upper, b)
            if lower > upper:
                intersects = False
                break
    if intersects:
        return Q(0)
    return min(_point_rectangle_squared(start, box), _point_rectangle_squared(end, box),
        *(_point_segment_squared((x, y), start, end)
          for x in (box[0], box[2]) for y in (box[1], box[3])))


def _outside_squared(p, box):
    gap = max(Q(0), min(p[0] - box[0], p[1] - box[1],
                        box[2] - p[0], box[3] - p[1]))
    return gap * gap


def _floor(value):
    return value.numerator // value.denominator


def _candidate_interval(lo, hi, origin, resolution, count):
    # Closed cell [o+i*r,o+(i+1)*r] intersects closed [lo,hi] iff
    # ceil((lo-o)/r)-1 <= i <= floor((hi-o)/r). Include both gridline sides.
    first = -_floor(-(lo - origin) / resolution) - 1
    last = _floor((hi - origin) / resolution)
    return max(0, first), min(count - 1, last)


def certify_seed_pose_bridge(grid, resolution, origin, estimated_xy, seed_cell, *,
                             seed_cell_traversable):
    """Return an exact threshold certificate; never override the original gate.

    Accept Python int/finite float/Fraction and NumPy integer/float16/32/64
    geometry, rejecting Boolean numeric values. The explicit gate itself must
    be bool/np.bool_. Any nonzero integer map value is blocked, including unknown.
    Inputs are read without mutation; callers must not concurrently mutate them.
    """
    values = np.asarray(grid)
    if values.ndim != 2 or not values.size or not np.issubdtype(values.dtype, np.integer):
        raise ValueError("nonempty two-dimensional integer received grid required")
    if not isinstance(seed_cell_traversable, (bool, np.bool_)):
        raise ValueError("explicit original seed-cell traversability required")
    traversable = bool(seed_cell_traversable)
    res, offset, pose = _number(resolution), _xy(origin), _xy(estimated_xy)
    if res <= 0:
        raise ValueError("positive resolution required")
    row, col = _seed(seed_cell)
    height, width = values.shape
    result = {"schema": "mr3-seed-pose-bridge-certificate-v1", "accepted": False,
        "reason": None, "seed_cell": [row, col], "seed_cell_traversable": traversable,
        "required_m_exact": str(REQUIRED_M), "resolution_exact": str(res),
        "point_distance_squared_capped_exact": None,
        "bridge_distance_squared_capped_exact": None, "candidate_bounds": None,
        "point_clearance_capped_m": None, "bridge_clearance_capped_m": None,
        "checked_cells": 0, "checked_nonfree_cells": 0}
    if not (0 <= row < height and 0 <= col < width):
        result["reason"] = "pose_outside_received_map"
        return result
    if values[row, col] != 0:
        result["reason"] = "seed_cell_unknown" if values[row, col] < 0 else "seed_cell_occupied"
        return result
    if not traversable:
        result["reason"] = "seed_cell_body_clearance"
        return result
    centre = (offset[0] + (Q(col) + Q(1, 2)) * res,
              offset[1] + (Q(row) + Q(1, 2)) * res)
    seed_box = (offset[0] + col * res, offset[1] + row * res,
                offset[0] + (col + 1) * res, offset[1] + (row + 1) * res)
    if _point_rectangle_squared(pose, seed_box):
        result["reason"] = "pose_not_in_original_seed_cell"
        return result
    bounds = (offset[0], offset[1], offset[0] + width * res, offset[1] + height * res)
    point2 = min(REQUIRED_SQUARED, _outside_squared(pose, bounds))
    # For each outside halfplane, minimum segment clearance is at an endpoint.
    bridge2 = min(point2, _outside_squared(centre, bounds))
    c0, c1 = _candidate_interval(min(pose[0], centre[0]) - REQUIRED_M,
        max(pose[0], centre[0]) + REQUIRED_M, offset[0], res, width)
    r0, r1 = _candidate_interval(min(pose[1], centre[1]) - REQUIRED_M,
        max(pose[1], centre[1]) + REQUIRED_M, offset[1], res, height)
    result["candidate_bounds"] = [r0, r1, c0, c1]  # Inclusive, clipped to map.
    result["checked_cells"] = (r1 - r0 + 1) * (c1 - c0 + 1)
    # Every omitted closed square is disjoint from the threshold-expanded
    # segment AABB. It has a coordinate gap > REQUIRED_M from every segment
    # point, hence Euclidean distance > REQUIRED_M. Its point/bridge distance
    # cannot change either capped minimum or the >= threshold decision.
    for dr, dc in np.argwhere(values[r0:r1 + 1, c0:c1 + 1] != 0):
        r, c = r0 + int(dr), c0 + int(dc)
        box = (offset[0] + c * res, offset[1] + r * res,
               offset[0] + (c + 1) * res, offset[1] + (r + 1) * res)
        point2 = min(point2, _point_rectangle_squared(pose, box))
        bridge2 = min(bridge2, _segment_rectangle_squared(pose, centre, box))
        result["checked_nonfree_cells"] += 1
    result.update(point_distance_squared_capped_exact=str(point2),
        bridge_distance_squared_capped_exact=str(bridge2),
        point_clearance_capped_m=math.sqrt(float(point2)),
        bridge_clearance_capped_m=math.sqrt(float(bridge2)))
    result["reason"] = ("seed_pose_body_clearance" if point2 < REQUIRED_SQUARED else
                        "seed_bridge_body_clearance" if bridge2 < REQUIRED_SQUARED else None)
    result["accepted"] = result["reason"] is None
    return result
