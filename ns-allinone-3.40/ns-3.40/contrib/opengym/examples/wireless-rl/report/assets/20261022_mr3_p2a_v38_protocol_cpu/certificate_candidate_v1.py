"""DISABLED exact-kernel CPU candidate; never imported by production.

The only mathematical shortcuts are exact segment-AABB distance pruning and
the identity distance(point, rectangle) == distance(zero segment, rectangle).
All public certificate construction/validation remains in the bound reference
module. No World, scene, input archive, graph, safety gate or cache is added.
"""
import json
import time

import numpy as np

from multi_robot_exploration import mr3_seed_certificate as reference


PROFILE = "mr3-exact-segment-aabb-disabled-v1"


def fast_segment_measurements(values, res, offset, start, end):
    """Reference kernel's exact capped minima and ALL diagnostic counts.

    Inputs have the same already-validated NumPy grid/canonical Fraction
    preconditions as reference._segment_measurements. No input is mutated.
    Every selected nonfree cell is counted and its point distance evaluated,
    even when its segment distance is provably unable to improve the minimum.
    """
    height, width = values.shape
    bounds = (offset[0], offset[1], offset[0] + width * res, offset[1] + height * res)
    point2 = min(reference.REQUIRED_SQUARED, reference._outside_squared(start, bounds))
    segment2 = min(point2, reference._outside_squared(end, bounds))
    min_x, max_x = min(start[0], end[0]), max(start[0], end[0])
    min_y, max_y = min(start[1], end[1]), max(start[1], end[1])
    c0, c1 = reference._candidate_interval(min_x - reference.REQUIRED_M,
        max_x + reference.REQUIRED_M, offset[0], res, width)
    r0, r1 = reference._candidate_interval(min_y - reference.REQUIRED_M,
        max_y + reference.REQUIRED_M, offset[1], res, height)
    nonfree = 0
    nonempty = r0 <= r1 and c0 <= c1
    zero_length = start == end
    if nonempty:
        for dr, dc in np.argwhere(values[r0:r1 + 1, c0:c1 + 1] != 0):
            r, c = r0 + int(dr), c0 + int(dc)
            box = (offset[0] + c * res, offset[1] + r * res,
                   offset[0] + (c + 1) * res, offset[1] + (r + 1) * res)
            point2 = min(point2, reference._point_rectangle_squared(start, box))
            if zero_length:
                segment2 = point2
            else:
                # The closed segment is a subset of this closed AABB. Hence
                # distance²(AABB, box) <= distance²(segment, box). Equality at
                # the current minimum is enough to skip; no epsilon is used.
                dx = max(box[0] - max_x, reference.Q(0), min_x - box[2])
                dy = max(box[1] - max_y, reference.Q(0), min_y - box[3])
                lower2 = dx * dx + dy * dy
                if lower2 < segment2:
                    segment2 = min(segment2, reference._segment_rectangle_squared(start, end, box))
            nonfree += 1
    return point2, segment2, {
        "candidate_bounds": [r0, r1, c0, c1] if nonempty else None,
        "checked_cells": (r1 - r0 + 1) * (c1 - c0 + 1) if nonempty else 0,
        "checked_nonfree_cells": nonfree}


def fixed_microbenchmark():
    """Only an explicit later CPU invocation may call this fixed small batch.

    It reports local old/new kernel timing, not episode or training capacity.
    The two orderings reduce an elementary warm-up/order bias; no winner-based
    workload selection, runtime tuning or source modification occurs.
    """
    q = reference.Q
    grid = np.zeros((21, 21), dtype=np.int8)
    grid[6:15, 6:15] = 100
    grid[8:13, 8:13] = 0
    corner = np.zeros((21, 21), dtype=np.int8)
    corner[13:, 16:] = 100
    res, origin = q(1, 20), (-q(21, 40), -q(21, 40))
    cases = [((q(0), q(0)), (q(x, 1000), q(y, 1000)))
             for x, y in ((0, 0), (2, 0), (0, 2), (25, 25), (-25, 25), (50, 0),
                          (100, 100), (-100, 0))]
    workloads = [(values, start, end) for values in (corner, grid) for start, end in cases]
    records = []
    for order in (("reference", "candidate"), ("candidate", "reference")):
        for name in order:
            function = reference._segment_measurements if name == "reference" else fast_segment_measurements
            started = time.perf_counter_ns()
            last = None
            for _ in range(2):
                for values, start, end in workloads:
                    last = function(values, res, origin, start, end)
            ended = time.perf_counter_ns()
            records.append({"implementation": name, "calls": 32,
                "elapsed_ns": ended - started, "last_point_squared_exact": str(last[0]),
                "last_segment_squared_exact": str(last[1]), "last_counts": last[2]})
    return {"schema": "mr3-exact-kernel-local-microbenchmark-v1", "profile": PROFILE,
            "production_enabled": False, "qualification": False, "records": records,
            "workloads": ["corner_obstacle", "dense_unsafe_ring"],
            "scope": "fixed artificial CPU only; no episode/training capacity claim"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microbenchmark", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(fixed_microbenchmark(), indent=2, allow_nan=False))
