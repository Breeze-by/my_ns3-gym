"""Exact, local received-grid certificate for an unchanged seed's pose bridge.

The seed bridge is used only after the original cell/graph gate, when the old
scalar pose bound alone rejected it. Explicit v2 also provides rational floor
for a single containing cell and exact segments for supplied-goal execution.
There is no seed search, pose snap, graph mutation or map mutation. Only zero-
valued cells are free; all other integer cells and the map exterior block.

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


def canonical_seed_cell(estimated_xy, resolution, origin, shape):
    """Return the single exact half-open containing cell, or None outside.

    The represented numeric inputs are authoritative: division is rational,
    with no rounded quotient, gridline tolerance, neighbour search or pose
    snap. Explicit v2 callers must apply the original cell/graph gates anew at
    this returned cell. Legacy/v1 callers retain their original float floor.
    """
    pose, res, offset = _xy(estimated_xy), _number(resolution), _xy(origin)
    height, width = _seed(shape)
    if res <= 0 or height <= 0 or width <= 0:
        raise ValueError("positive resolution and nonempty shape required")
    row, col = (_floor((pose[1] - offset[1]) / res),
                _floor((pose[0] - offset[0]) / res))
    return (row, col) if 0 <= row < height and 0 <= col < width else None


def canonical_cell_centre(cell, resolution, origin):
    """Exact centre on the same represented received-grid geometry."""
    row, col = _seed(cell)
    res, offset = _number(resolution), _xy(origin)
    if res <= 0:
        raise ValueError("positive resolution required")
    return (offset[0] + (Q(col) + Q(1, 2)) * res,
            offset[1] + (Q(row) + Q(1, 2)) * res)


def _candidate_interval(lo, hi, origin, resolution, count):
    # Closed cell [o+i*r,o+(i+1)*r] intersects closed [lo,hi] iff
    # ceil((lo-o)/r)-1 <= i <= floor((hi-o)/r). Include both gridline sides.
    first = -_floor(-(lo - origin) / resolution) - 1
    last = _floor((hi - origin) / resolution)
    return max(0, first), min(count - 1, last)


def _grid(value):
    values = np.asarray(value)
    if values.ndim != 2 or not values.size or not np.issubdtype(values.dtype, np.integer):
        raise ValueError("nonempty two-dimensional integer received grid required")
    return values


def _segment_measurements(values, res, offset, start, end):
    """Shared exact kernel; all numbers are already canonical Fractions."""
    height, width = values.shape
    bounds = (offset[0], offset[1], offset[0] + width * res, offset[1] + height * res)
    point2 = min(REQUIRED_SQUARED, _outside_squared(start, bounds))
    # For each outside halfplane, minimum segment clearance is at an endpoint.
    segment2 = min(point2, _outside_squared(end, bounds))
    c0, c1 = _candidate_interval(min(start[0], end[0]) - REQUIRED_M,
        max(start[0], end[0]) + REQUIRED_M, offset[0], res, width)
    r0, r1 = _candidate_interval(min(start[1], end[1]) - REQUIRED_M,
        max(start[1], end[1]) + REQUIRED_M, offset[1], res, height)
    nonfree = 0
    nonempty = r0 <= r1 and c0 <= c1
    # Every omitted closed square is disjoint from the threshold-expanded
    # segment AABB. It has a coordinate gap > REQUIRED_M from every segment
    # point, hence Euclidean distance > REQUIRED_M. Its point/segment distance
    # cannot change either capped minimum or the >= threshold decision.
    if nonempty:
        for dr, dc in np.argwhere(values[r0:r1 + 1, c0:c1 + 1] != 0):
            r, c = r0 + int(dr), c0 + int(dc)
            box = (offset[0] + c * res, offset[1] + r * res,
                   offset[0] + (c + 1) * res, offset[1] + (r + 1) * res)
            point2 = min(point2, _point_rectangle_squared(start, box))
            segment2 = min(segment2, _segment_rectangle_squared(start, end, box))
            nonfree += 1
    return point2, segment2, {
        "candidate_bounds": [r0, r1, c0, c1] if nonempty else None,
        "checked_cells": (r1 - r0 + 1) * (c1 - c0 + 1) if nonempty else 0,
        "checked_nonfree_cells": nonfree}


def certify_estimated_segment(grid, resolution, origin, start_xy, end_xy):
    """Certify one proposed estimated straight segment under the same .29 gate.

    This does not select a graph edge or replace any seed-cell/bridge gate. The
    v1 proxy navigator uses it after its seed bridge passes. Explicit v2 uses
    it after the unchanged canonical-cell/graph gates for supplied-goal route
    segments, and again for every fixed 20ms straight translation proposal.
    """
    values, res, offset = _grid(grid), _number(resolution), _xy(origin)
    if res <= 0:
        raise ValueError("positive resolution required")
    start, end = _xy(start_xy), _xy(end_xy)
    point2, segment2, counts = _segment_measurements(values, res, offset, start, end)
    return {"schema": "mr3-estimated-straight-segment-certificate-v1",
        "accepted": segment2 >= REQUIRED_SQUARED,
        "required_m_exact": str(REQUIRED_M),
        "point_distance_squared_capped_exact": str(point2),
        "segment_distance_squared_capped_exact": str(segment2), **counts}


def certify_seed_pose_bridge(grid, resolution, origin, estimated_xy, seed_cell, *,
                             seed_cell_traversable):
    """Return an exact threshold certificate; never override the original gate.

    Accept Python int/finite float/Fraction and NumPy integer/float16/32/64
    geometry, rejecting Boolean numeric values. The explicit gate itself must
    be bool/np.bool_. Any nonzero integer map value is blocked, including unknown.
    Inputs are read without mutation; callers must not concurrently mutate them.
    """
    values = _grid(grid)
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
    point2, bridge2, counts = _segment_measurements(values, res, offset, pose, centre)
    result.update(counts)
    result.update(point_distance_squared_capped_exact=str(point2),
        bridge_distance_squared_capped_exact=str(bridge2),
        point_clearance_capped_m=math.sqrt(float(point2)),
        bridge_clearance_capped_m=math.sqrt(float(bridge2)))
    result["reason"] = ("seed_pose_body_clearance" if point2 < REQUIRED_SQUARED else
                        "seed_bridge_body_clearance" if bridge2 < REQUIRED_SQUARED else None)
    result["accepted"] = result["reason"] is None
    return result
