"""Evaluator-only, conditional endpoint-support geometry; never actor input.

No plant, node, scan, actor, episode or reward journal is constructed/replayed.
All individual box surfaces are retained, including buried and inaccessible
ones. Closed-cell coverage is an upper enclosure, not an exact floor raster or
a visibility proof. The actual noisy/biased-odometry proxy is NOT bounded by
this ideal aligned/noiseless diagnostic.
"""

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import numpy as np

from . import mr3_contacts, mr3_task_contract
from .mr3_task_contract import (
    _rasterize, inspect_world_geometry, load_contract_truth, load_task_contract,
)


SCENES = ("open", "rooms", "corridors")
ENCLOSURE_EPSILON_M = 1e-9


def _number(value, name, positive=False):
    if (isinstance(value, (bool, np.bool_)) or np.iscomplexobj(value)
            or not isinstance(value, (int, float, np.number))):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return value


def rectangle_segments(rectangle):
    if len(rectangle) != 5:
        raise ValueError("rectangle requires x/y/yaw/size_x/size_y")
    x, y, yaw = (_number(v, "rectangle coordinate") for v in rectangle[:3])
    sx, sy = (_number(v, "rectangle size", True) for v in rectangle[3:])
    c, s = math.cos(yaw), math.sin(yaw)
    corners = [(x + c * dx - s * dy, y + s * dx + c * dy)
               for dx, dy in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2),
                              (sx / 2, sy / 2), (-sx / 2, sy / 2))]
    return [(corners[i], corners[(i + 1) % 4]) for i in range(4)]


def _intersects_closed_box(start, end, lower, upper):
    """Exact rational slab test, including endpoints and parallel segments."""
    enter, leave = Fraction(0), Fraction(1)
    for a, b, low, high in zip(start, end, lower, upper):
        delta = b - a
        if not delta:
            if a < low or a > high:
                return False
            continue
        first, second = (low - a) / delta, (high - a) / delta
        enter, leave = max(enter, min(first, second)), min(leave, max(first, second))
        if enter > leave:
            return False
    return True


def roi_front_face_decision(start, end, bounds):
    """Discard a CCW box face only when the full ROI is strictly behind it."""
    a, b = [tuple(Fraction(_number(v, "face coordinate")) for v in point) for point in (start, end)]
    xmin, ymin, xmax, ymax = (Fraction(_number(v, "ROI bound")) for v in bounds)
    nx, ny = b[1] - a[1], a[0] - b[0]  # Right normal of the CCW edge.
    maximum = max(nx * (x - a[0]) + ny * (y - a[1])
                  for x, y in ((xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)))
    guard = Fraction(ENCLOSURE_EPSILON_M) * (abs(nx) + abs(ny))
    keep = maximum >= -guard
    return {"retained": keep, "maximum_roi_signed_plane_numerator_m2": float(maximum),
            "outward_plane_guard_m2": float(guard),
            "decision": "retain_front_or_ambiguous" if keep else "discard_strictly_behind"}


def segment_cell_cover(start, end, shape, resolution, origin, *, epsilon_m=ENCLOSURE_EPSILON_M):
    """Closed-cell supercover of a supplied double-precision line segment.

    Fraction conversion makes intersection/index decisions exact for those
    supplied floats. Every target cell is expanded outwards by epsilon_m; it is
    a numerical enclosure guard, not a bound on sensor/odometry error. A segment
    on a gridline deliberately includes both sides. No new ROI boundary is
    introduced by clipping: only target cell indices are clipped.
    """
    if len(shape) != 2 or any(type(n) is not int or n <= 0 for n in shape):
        raise ValueError("positive integer height/width required")
    if len(start) != 2 or len(end) != 2 or len(origin) != 2:
        raise ValueError("two-dimensional segment and origin required")
    resolution = _number(resolution, "resolution", True)
    epsilon_m = _number(epsilon_m, "epsilon_m")
    if epsilon_m < 0:
        raise ValueError("epsilon_m cannot shrink the enclosure")
    start = tuple(Fraction(_number(v, "segment coordinate")) for v in start)
    end = tuple(Fraction(_number(v, "segment coordinate")) for v in end)
    origin = tuple(Fraction(_number(v, "origin coordinate")) for v in origin)
    resolution, epsilon = Fraction(resolution), Fraction(epsilon_m)
    first = [max(0, math.floor((min(a, b) - o - epsilon) / resolution) - 1)
             for a, b, o in zip(start, end, origin)]
    last = [min(limit - 1, math.floor((max(a, b) - o + epsilon) / resolution) + 1)
            for a, b, o, limit in zip(start, end, origin, (shape[1], shape[0]))]
    cover = np.zeros(shape, dtype=bool)
    for row in range(first[1], last[1] + 1):
        for column in range(first[0], last[0] + 1):
            lower = (origin[0] + column * resolution - epsilon,
                     origin[1] + row * resolution - epsilon)
            upper = (origin[0] + (column + 1) * resolution + epsilon,
                     origin[1] + (row + 1) * resolution + epsilon)
            cover[row, column] = _intersects_closed_box(start, end, lower, upper)
    return cover


def diagnose_rectangles(rectangles, truth, *, labels=None, minimum_iou=None):
    """Full fixed-denominator, all-surfaces conditional IoU upper enclosure."""
    rectangles = [tuple(rectangle) for rectangle in rectangles]
    occupied, roi = np.asarray(truth.occupied), np.asarray(truth.roi_mask)
    if occupied.ndim != 2 or occupied.dtype != bool or roi.dtype != bool or roi.shape != occupied.shape:
        raise ValueError("original boolean occupied/ROI arrays of equal shape required")
    resolution = _number(truth.resolution, "resolution", True)
    origin = (_number(truth.origin_x, "origin_x"), _number(truth.origin_y, "origin_y"))
    bounds = (*origin, origin[0] + occupied.shape[1] * resolution,
              origin[1] + occupied.shape[0] * resolution)
    if not np.array_equal(_rasterize(rectangles, bounds, resolution), occupied):
        raise ValueError("supplied truth does not match the unchanged original rasterizer")
    labels = [f"rectangle_{i:03d}" for i in range(len(rectangles))] if labels is None else list(labels)
    if len(labels) != len(rectangles) or any(not isinstance(label, str) for label in labels):
        raise ValueError("one string label per rectangle required")
    if minimum_iou is not None:
        minimum_iou = _number(minimum_iou, "minimum_iou")
        if not 0 <= minimum_iou <= 1:
            raise ValueError("minimum_iou must be in [0, 1]")
    covers, roi_covers, solids, face_decisions = [], [], [], []
    for rectangle in rectangles:
        cover = np.zeros(occupied.shape, dtype=bool)
        roi_cover = np.zeros(occupied.shape, dtype=bool)
        decisions = []
        for start, end in rectangle_segments(rectangle):
            segment_cover = segment_cell_cover(start, end, tuple(occupied.shape), resolution, origin)
            cover |= segment_cover
            decision = roi_front_face_decision(start, end, bounds)
            decisions.append(decision)
            if decision["retained"]:
                roi_cover |= segment_cover
        covers.append(cover & roi)
        roi_covers.append(roi_cover & roi)
        solids.append(_rasterize([rectangle], bounds, resolution) & roi)
        face_decisions.append(decisions)
    multiplicity = np.zeros(occupied.shape, dtype=np.int32)
    roi_surface = np.zeros(occupied.shape, dtype=bool)
    for cover in covers:
        multiplicity += cover
    for cover in roi_covers:
        roi_surface |= cover
    surface = multiplicity > 0
    occupied_roi, free_roi = occupied & roi, ~occupied & roi
    denominator = int(occupied_roi.sum())
    correct = int((surface & occupied_roi).sum())
    upper = correct / denominator if denominator else None
    per_obstacle = []
    for index, (label, rectangle, cover, solid, roi_cover, decisions) in enumerate(
            zip(labels, rectangles, covers, solids, roi_covers, face_decisions)):
        per_obstacle.append({
            "index": index, "source_collision": label, "rectangle_xy_yaw_sx_sy": list(rectangle),
            "solid_occupied_cells_in_roi": int(solid.sum()),
            "own_surface_cover_cells_in_roi": int(cover.sum()),
            "own_solid_cells_in_own_surface_cover": int((solid & cover).sum()),
            "own_solid_cells_outside_own_surface_cover": int((solid & ~cover).sum()),
            "own_solid_cells_outside_all_surface_covers": int((solid & ~surface).sum()),
            "possible_correct_occupied_cells_in_global_truth": int((cover & occupied_roi).sum()),
            "unique_possible_correct_occupied_cells": int((cover & occupied_roi & (multiplicity == 1)).sum()),
            "possible_false_positive_surface_cells": int((cover & free_roi).sum()),
            "roi_origin_face_decisions": decisions,
            "roi_origin_possible_correct_occupied_cells": int((roi_cover & occupied_roi).sum()),
            "roi_origin_possible_false_positive_surface_cells": int((roi_cover & free_roi).sum()),
        })
    roi_correct = int((roi_surface & occupied_roi).sum())
    roi_upper = roi_correct / denominator if denominator else None
    return {
        "method": "all_individual_box_segments_closed_cell_upper_enclosure_v1",
        "grid_shape": list(occupied.shape), "resolution_m": resolution, "origin_m": list(origin),
        "roi_cell_count": int(roi.sum()), "truth_occupied_cell_count": denominator,
        "truth_free_cell_count": int(free_roi.sum()), "rectangle_count": len(rectangles),
        "surface_cover_cells_in_roi": int(surface.sum()),
        "possible_endpoint_overlap_correct_occupied_cells": correct,
        "solid_occupied_cells_outside_surface_enclosure": denominator - correct,
        "possible_false_positive_surface_cells": int((surface & free_roi).sum()),
        "surface_cells_covered_by_multiple_obstacles": int((multiplicity > 1).sum()),
        "surface_cover_sha256": hashlib.sha256(np.ascontiguousarray(surface).tobytes()).hexdigest(),
        "conditional_occupied_iou_upper_enclosure": upper,
        "declared_minimum_occupied_iou": minimum_iou,
        "conditional_enclosure_below_declared_gate": bool(denominator and minimum_iou is not None and upper < minimum_iou),
        "epsilon_m_outward_only": ENCLOSURE_EPSILON_M,
        "denominator_modified": False, "reachability_or_visibility_restriction_applied": False,
        "per_obstacle_counts_are_not_additive": True, "per_obstacle": per_obstacle,
        "roi_origin_front_face": {
            "method": "retain_faces_unless_all_closed_roi_corners_strictly_behind_outward_plane_v1",
            "surface_cover_cells_in_roi": int(roi_surface.sum()),
            "possible_endpoint_overlap_correct_occupied_cells": roi_correct,
            "solid_occupied_cells_outside_surface_enclosure": denominator - roi_correct,
            "possible_false_positive_surface_cells": int((roi_surface & free_roi).sum()),
            "truth_occupied_cell_count": denominator,
            "conditional_occupied_iou_upper_enclosure": roi_upper,
            "conditional_enclosure_below_declared_gate": bool(denominator and minimum_iou is not None and roi_upper < minimum_iou),
            "additional_assumption": "every sensor origin is in the closed original rectangular ROI and outside all static solids",
            "roi_sensor_origin_assumption_is_guaranteed_by_current_proxy": False,
            "gridline_equality_and_numerical_ambiguity_retained": True,
            "robot_reachability_restriction_applied": False,
        },
        "assumptions": [
            "zero range error and exact common-frame estimated/physical sensor pose alignment",
            "ideal endpoints lie on the reported static rectangle segments, within the numerical enclosure guard",
            "range_min clipping is inactive; legal sensor origins and other returning bodies do not lie inside static solids",
            "local maps and fused output share the original origin/shape/resolution with zero yaw and no support-expanding resampling",
            "all potential surface cells may be accumulated; free carving can only remove occupied support",
        ],
        "limitations": [
            "all individual surfaces include buried, occluded and body-unreachable exterior surfaces; this is generous, not achievable coverage",
            "closed cells include both gridline sides and corner neighbors; not an exact floor endpoint raster or a tight bound",
            "possible false-positive cells are optional support, not mandatory predictions; the optimistic IoU denominator remains full truth occupied only",
            "other exterior object returns may add free-space false positives; those cannot raise this conditional IoU upper bound",
            "Gaussian range noise and fixed random wheel-encoder biases have no finite hard error bound; the actual proxy can place endpoints outside this enclosure",
            "a bound above the gate proves neither visibility, quality feasibility, 95percent coverage nor task success",
            "the numerical guard encloses supplied double-precision segments; this is not a certification of all simulator floating-point operations",
        ],
        "actual_noisy_proxy_task_impossibility_claim": False,
        "qualification": False, "training_eligible": False, "native_credit": False,
    }


def _collision_labels(world, audit):
    ignored = {row["object"] for row in audit["ignored"] if row["reason"] == "box_outside_slice"}
    labels = []
    for model in ET.parse(world).getroot().find("world").findall("model"):
        for link in model.findall("link"):
            for collision in link.findall("collision"):
                label = f"{model.get('name', '')}/{link.get('name', '')}/{collision.get('name', '')}"
                if collision.find("geometry/box") is not None and label not in ignored:
                    labels.append(label)
    if len(labels) != audit["rectangle_count"]:
        raise ValueError("source collision attribution does not match audited rectangles")
    return labels


def diagnose_scene(scene, asset_root):
    if scene not in SCENES:
        raise ValueError("only the fixed three declared scenes are supported")
    assets = Path(asset_root)
    world, config = assets / f"worlds/p1c_{scene}.world", assets / f"config/mr3_p1a/{scene}.json"
    contract = load_task_contract(config, world)
    truth = load_contract_truth(world, contract)
    if truth.resolution != .05 or not truth.roi_mask.all():
        raise ValueError("original full-ROI 0.05m proxy lattice required")
    rectangles, audit = inspect_world_geometry(world, contract.data["lidar_height_m"])
    if audit["unsupported"]:
        raise ValueError("unsupported actual geometry")
    result = diagnose_rectangles(rectangles, truth, labels=_collision_labels(world, audit),
                                 minimum_iou=contract.data["quality"]["min_occupied_iou"])
    return {"scene": scene, "world_sha256": contract.data["world_sha256"],
            "contract_sha256": contract.sha256, "quality_gates": contract.data["quality"],
            "original_roi_bounds": contract.data["roi"]["bounds"], **result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch("[0-9a-f]{40}", args.freeze):
        parser.error("--freeze requires a complete lowercase Git SHA")
    if args.output.exists():
        raise FileExistsError(args.output)
    root = Path(__file__).resolve().parents[5]
    ros = root / "ros2_ws/ros2-multi-robot-automap"
    assets = ros / "src/multi_robot"
    dependencies = [Path(__file__).resolve(), Path(mr3_task_contract.__file__).resolve(),
                    Path(mr3_contacts.__file__).resolve(),
                    ros / "src/multi_robot_exploration/multi_robot_exploration/mr3_proxy2d_world.py",
                    ros / "src/multi_robot_exploration/multi_robot_exploration/mr3_proxy2d_information.py",
                    ros / "src/multi_robot_exploration/multi_robot_exploration/mr3_information.py",
                    ros / "src/merge_map/merge_map/merge_map.py", ros / "scripts/mr3_proxy2d_worker.py"]
    dependencies += [assets / relative for scene in SCENES
                     for relative in (f"worlds/p1c_{scene}.world", f"config/mr3_p1a/{scene}.json")]
    before = {str(path.relative_to(root)): path.read_bytes() for path in dependencies}
    proc_tail = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    report = {"schema": "mr3-proxy2d-quality-geometry-v1", "freeze": args.freeze,
              "scope": "source-only conditional aligned/noiseless endpoint geometry; passed means consumer integrity, never task feasibility",
              "consumer_identity": {"pid": os.getpid(), "parent": os.getppid(),
                                    "group": os.getpgrp(), "session": os.getsid(0),
                                    "start_ticks": int(proc_tail[19])},
              "scenes": [], "errors": [], "passed": False,
              "qualification": False, "training_eligible": False, "native_credit": False,
              "worlds_created": 0, "nodes_created": 0, "episodes": 0,
              "actor_calls": 0, "reward_replays": 0, "policy_calls": 0,
              "gpu_calls": 0, "optimizer_steps": 0}
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, timeout=5).decode().strip()
        if head != args.freeze:
            raise ValueError("declared freeze differs from current Git HEAD")
        for relative, payload in before.items():
            frozen = subprocess.check_output(["git", "show", f"{args.freeze}:{relative}"], cwd=root, timeout=5)
            if payload != frozen:
                raise ValueError(f"current input differs from declared freeze: {relative}")
        for scene in SCENES:
            report["scenes"].append(diagnose_scene(scene, assets))
    except Exception as error:
        report["errors"].append(f"{type(error).__name__}: {error}")
    report["source_and_asset_bindings"] = {
        relative: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        for relative, payload in before.items()}
    report["bound_bytes_unchanged"] = all((root / relative).read_bytes() == payload
                                           for relative, payload in before.items())
    if not report["bound_bytes_unchanged"]:
        report["errors"].append("bound source or asset bytes changed during the consumer")
    report["passed"] = not report["errors"] and len(report["scenes"]) == 3
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
