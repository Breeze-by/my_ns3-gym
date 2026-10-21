"""Disabled artificial CPU hypothesis: exact pose/seed-centre bridge geometry.

No map/scene/file loading, pose snapping, new seed, graph mutation or admission.
The caller supplies the ORIGINAL seed and its unchanged traversability result.
Only grid value 0 is free; every other cell and the map exterior are blocked.
Distances are exact for the supplied numeric grid/point model, not physical
pose, sensing, motion tracking, source freshness, native safety or observation
qualification. Float distances are display only; squared Fraction comparisons
against the unchanged 29/100 m threshold decide this conditional certificate.
"""

from fractions import Fraction as Q
import math

import numpy as np

from multi_robot_exploration.mr3_reach_geometry import exact, point


REQUIRED = Q(29, 100)
MAX_CELLS = 4096  # Artificial CPU prototype only; not a production map reader.


def point_rectangle_squared(p, rectangle):
    """Point to a closed axis-aligned square/rectangle, all inputs rational."""
    x0, y0, x1, y1 = rectangle
    dx = max(x0 - p[0], Q(0), p[0] - x1)
    dy = max(y0 - p[1], Q(0), p[1] - y1)
    return dx * dx + dy * dy


def point_segment_squared(p, start, end):
    delta = tuple(b - a for a, b in zip(start, end))
    length2 = sum(value * value for value in delta)
    t = (Q(0) if not length2 else max(Q(0), min(Q(1),
        sum((p[i] - start[i]) * delta[i] for i in range(2)) / length2)))
    return sum((p[i] - start[i] - t * delta[i]) ** 2 for i in range(2))


def segment_rectangle_squared(start, end, rectangle):
    """Exact closed segment/rectangle distance, including corner/tangent hits."""
    lower, upper = Q(0), Q(1)
    intersects = True
    for axis, low, high in ((0, rectangle[0], rectangle[2]), (1, rectangle[1], rectangle[3])):
        delta = end[axis] - start[axis]
        if not delta:
            if not low <= start[axis] <= high:
                intersects = False
                break
        else:
            a, b = sorted(((low - start[axis]) / delta, (high - start[axis]) / delta))
            lower, upper = max(lower, a), min(upper, b)
            if lower > upper:
                intersects = False
                break
    if intersects:
        return Q(0)
    corners = [(x, y) for x in (rectangle[0], rectangle[2])
               for y in (rectangle[1], rectangle[3])]
    return min(point_rectangle_squared(start, rectangle),
               point_rectangle_squared(end, rectangle),
               *(point_segment_squared(corner, start, end) for corner in corners))


def _outside_squared(p, bounds):
    # Complement of the open map rectangle is a union of four closed halfplanes.
    gap = max(Q(0), min(p[0] - bounds[0], p[1] - bounds[1],
                        bounds[2] - p[0], bounds[3] - p[1]))
    return gap * gap


def certificate(grid, resolution, origin, estimated_xy, seed_cell, *, seed_cell_traversable):
    """Certify only an original traversable seed's point and straight bridge.

    The supplied seed is never changed. Its original graph/body-cell gate must
    already pass. The estimated point must lie in that closed seed square.
    This prototype does not recompute/replace the original cell certificate.
    """
    values = np.asarray(grid)
    if (values.ndim != 2 or not values.size or values.size > MAX_CELLS
            or not np.issubdtype(values.dtype, np.integer)
            or values.min() < -1 or values.max() > 100):
        raise ValueError("bounded nonempty integer occupancy grid in [-1,100] required")
    if type(seed_cell_traversable) is not bool:
        raise ValueError("explicit original seed-cell traversability required")
    res, offset, pose = exact(resolution), point(origin), point(estimated_xy)
    if res <= 0:
        raise ValueError("positive resolution required")
    if (not isinstance(seed_cell, (tuple, list)) or len(seed_cell) != 2
            or any(type(value) is not int for value in seed_cell)):
        raise ValueError("original (row,column) integer seed required")
    row, col = seed_cell
    height, width = values.shape
    if not (0 <= row < height and 0 <= col < width):
        raise ValueError("original seed outside map")
    bounds = (offset[0], offset[1], offset[0] + width * res, offset[1] + height * res)
    seed_bounds = (offset[0] + col * res, offset[1] + row * res,
                   offset[0] + (col + 1) * res, offset[1] + (row + 1) * res)
    centre = (offset[0] + (Q(col) + Q(1, 2)) * res,
              offset[1] + (Q(row) + Q(1, 2)) * res)
    pose2 = _outside_squared(pose, bounds)
    # A linear coordinate's minimum distance to an outside halfplane occurs
    # at an endpoint; if either endpoint is outside this minimum is zero.
    bridge2 = min(pose2, _outside_squared(centre, bounds))
    for r, c in np.argwhere(values != 0):
        square = (offset[0] + int(c) * res, offset[1] + int(r) * res,
                  offset[0] + (int(c) + 1) * res, offset[1] + (int(r) + 1) * res)
        pose2 = min(pose2, point_rectangle_squared(pose, square))
        bridge2 = min(bridge2, segment_rectangle_squared(pose, centre, square))
    reason = None
    if values[row, col] != 0:
        reason = "seed_cell_unknown" if values[row, col] < 0 else "seed_cell_occupied"
    elif not seed_cell_traversable:
        reason = "seed_cell_body_clearance"
    elif point_rectangle_squared(pose, seed_bounds) != 0:
        reason = "pose_not_in_original_seed_cell"
    elif pose2 < REQUIRED ** 2:
        reason = "seed_pose_body_clearance"
    elif bridge2 < REQUIRED ** 2:
        reason = "seed_bridge_body_clearance"
    return {"schema": "mr3-disabled-seed-point-bridge-hypothesis-v1",
            "accepted": reason is None, "reason": reason,
            "seed_cell": [row, col], "seed_cell_traversable": seed_cell_traversable,
            "seed_centre_exact": [str(value) for value in centre],
            "required_m_exact": str(REQUIRED),
            "point_distance_squared_exact": str(pose2),
            "bridge_distance_squared_exact": str(bridge2),
            "point_clearance_m": math.sqrt(float(pose2)),
            "bridge_clearance_m": math.sqrt(float(bridge2)),
            "production_enabled": False, "observation_qualification": False,
            "native_safety_qualification": False}
