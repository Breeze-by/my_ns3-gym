"""DISABLED CPU candidate: attach an unchanged estimated point to graph nodes.

This is a new point-to-graph attachment profile, not a repair or relaxation of
the existing seed-cell profile. No production caller, graph write, pose snap,
motion command, exploration goal selection, World or truth input exists here.
All geometry uses only the supplied received grid and represented point. It
does not prove tracking, localization, peer/scan safety, task or native credit.
"""
import math

import numpy as np

from multi_robot_exploration.mr3_observation import _received_grid, native_traversable
from multi_robot_exploration.mr3_seed_certificate import (
    _number, _xy, canonical_cell_centre, canonical_seed_cell, certify_estimated_segment,
)


PROFILE = "mr3-point-graph-attachment-3x3-disabled-v1"


def point_graph_attachments(grid, resolution, origin, estimated_xy):
    """Return ALL certified original-node attachments in a fixed 3x3 window.

    Preconditions are exactly one canonical in-bounds raw-free cell and an
    exact .29m point certificate. The containing cell's original traversable
    flag is diagnostic only under this NEW profile. Candidate anchors must
    independently be ORIGINAL native_traversable nodes and each complete
    estimated-point-to-exact-centre bridge must pass the unchanged .29m closed-
    square certificate. Row/column order is not a preferred anchor or policy.

    Python/NumPy finite numeric geometry has the shared helper's canonical
    semantics (including exact Fraction fixtures); Boolean numbers are invalid.
    Missing/empty maps reject. Invalid geometry raises ValueError. Inputs must
    not be concurrently mutated; this function does not mutate them.
    """
    res, offset, pose = _number(resolution), _xy(origin), _xy(estimated_xy)
    if res <= 0:
        raise ValueError("positive resolution required")
    # Keep the original received-map value/shape validation and graph kernel.
    values = np.empty((0, 0), dtype=np.int8) if grid is None else _received_grid(grid)
    result = {"schema": "mr3-point-graph-attachment-candidate-v1", "profile": PROFILE,
        "production_enabled": False, "accepted": False, "reason": None,
        "required_m_exact": "29/100", "estimated_point_exact": [str(value) for value in pose],
        "resolution_exact": str(res), "origin_exact": [str(value) for value in offset],
        "canonical_cell": None, "canonical_value": None,
        "canonical_cell_original_traversable": None, "canonical_cell_original_lower_bound_m": None,
        "point_certificate": None, "window_inclusive": None,
        "candidate_nodes": [], "anchors": [], "graph_mutated": False,
        "interpretation": "virtual start at unchanged estimated point; all anchors retained; no motion or goal"}
    if not values.size:
        result["reason"] = "empty_received_map"
        return result
    cell = canonical_seed_cell(pose, res, offset, values.shape)
    result["canonical_cell"] = None if cell is None else list(cell)
    if cell is None:
        result["reason"] = "point_outside_received_map"
        return result
    result["canonical_value"] = int(values[cell])
    if values[cell] != 0:
        result["reason"] = "canonical_cell_unknown" if values[cell] < 0 else "canonical_cell_occupied"
        return result
    # Use the unchanged graph kernel on the original represented resolution,
    # not the rationalized copy (which may change NumPy's arithmetic dtype).
    traversable, clearance = native_traversable(values, resolution)
    numeric_clearance = np.asarray(clearance, dtype=float)
    if not np.all(np.isfinite(numeric_clearance)):
        raise ValueError("original graph metric exceeds finite supported range")
    result["canonical_cell_original_traversable"] = bool(traversable[cell])
    result["canonical_cell_original_lower_bound_m"] = float(clearance[cell])
    point_certificate = certify_estimated_segment(values, res, offset, pose, pose)
    result["point_certificate"] = point_certificate
    if not point_certificate["accepted"]:
        result["reason"] = "estimated_point_body_clearance"
        return result
    row, col = cell
    r0, r1 = max(0, row - 1), min(values.shape[0] - 1, row + 1)
    c0, c1 = max(0, col - 1), min(values.shape[1] - 1, col + 1)
    result["window_inclusive"] = [r0, r1, c0, c1]
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            node = {"cell": [r, c], "value": int(values[r, c]),
                    "original_traversable": bool(traversable[r, c]),
                    "original_lower_bound_m": float(clearance[r, c]), "bridge_certificate": None}
            result["candidate_nodes"].append(node)
            if not traversable[r, c]:
                continue
            centre = canonical_cell_centre((r, c), res, offset)
            proof = certify_estimated_segment(values, res, offset, pose, centre)
            node["bridge_certificate"] = proof
            if proof["accepted"]:
                length2 = sum((centre[i] - pose[i]) ** 2 for i in range(2))
                length = math.sqrt(float(length2))
                if not math.isfinite(length):
                    raise ValueError("bridge length exceeds finite supported range")
                result["anchors"].append({"cell": [r, c], "centre_exact": [str(value) for value in centre],
                    "bridge_length_squared_exact": str(length2), "bridge_length_m": length,
                    "bridge_certificate": proof})
    result["accepted"] = bool(result["anchors"])
    result["reason"] = None if result["accepted"] else "no_certified_anchor_in_fixed_3x3"
    return result
