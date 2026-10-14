"""
Strict MR3 task geometry and metrics for evaluation only.

This module has no ROS imports or publishers. Its truth and feasibility arrays
must never be supplied to navigation, action masks, candidates, or an actor.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy import ndimage

from .mr3_contacts import ContactMonitor


ROBOT_NAMES = ["tb1", "tb2", "tb3"]
RASTERIZATION = "positive_area_intersection_v1"


@dataclass
class TaskContract:
    data: dict
    sha256: str
    world_path: Path


@dataclass
class ContractTruthGrid:
    occupied: np.ndarray
    origin_x: float
    origin_y: float
    resolution: float
    rectangle_count: int
    unsupported_collision_count: int
    roi_mask: np.ndarray
    world_sha256: str
    contract_sha256: str
    lidar_height_m: float
    geometry_audit: dict
    center_sampled_occupied: np.ndarray


def _finite_number(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} is below {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} is above {maximum}")
    return value


def load_task_contract(path, world_path):
    """Load a versioned, world-hash-bound task without relaxing MR3 gates."""
    payload = Path(path).read_bytes()
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("MR3 task contract must be a JSON object")
    world_path = Path(world_path).resolve()
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("MR3 contract schema_version must be 1")
    if not isinstance(data.get("contract_id"), str) or not data["contract_id"]:
        raise ValueError("contract_id is required")
    if data.get("robots") != ROBOT_NAMES:
        raise ValueError("MR3 requires exactly tb1/tb2/tb3 in that order")
    if data.get("world_file") != world_path.name:
        raise ValueError("Contract world_file does not match the selected world")
    digest = hashlib.sha256(world_path.read_bytes()).hexdigest()
    if data.get("world_sha256") != digest:
        raise ValueError("World SHA256 differs from the declared task geometry")
    if data.get("frame_id") != "map":
        raise ValueError("MR3 geometry requires the declared common map frame")
    if _finite_number(data.get("coverage_threshold"), "coverage_threshold") != .95:
        raise ValueError("MR3 coverage_threshold is fixed at 0.95")
    if _finite_number(data.get("max_duration_sec"), "max_duration_sec") != 300.0:
        raise ValueError("MR3-P1A max_duration_sec is fixed at 300")
    resolution = _finite_number(data.get("resolution"), "resolution", .001)
    _finite_number(data.get("lidar_height_m"), "lidar_height_m", 0.0)
    _finite_number(data.get("robot_radius_m"), "robot_radius_m", .001)
    _finite_number(data.get("lidar_range_m"), "lidar_range_m", .001)
    _finite_number(data.get("contact_monitor_max_age_sec"),
                   "contact_monitor_max_age_sec", .001)
    support = data.get("support_collision_names")
    if (not isinstance(support, list) or not support
            or any(not isinstance(name, str) for name in support)):
        raise ValueError("support_collision_names must be a nonempty list")
    # Reuse the contact component's exact scoped-name validation.
    ContactMonitor(ROBOT_NAMES, support, data["contact_monitor_max_age_sec"])
    if _finite_number(data.get("navigation_closure_timeout_sec"),
                      "navigation_closure_timeout_sec") != 10.0:
        raise ValueError("MR3 navigation_closure_timeout_sec is fixed at 10")
    if data.get("task_start_barrier") != "controller_release":
        raise ValueError("task_start_barrier must be controller_release")
    if data.get("truth_rasterization") != RASTERIZATION:
        raise ValueError(f"truth_rasterization must be {RASTERIZATION}")
    roi = data.get("roi", {})
    if not isinstance(roi, dict):
        raise ValueError("roi must be a JSON object")
    if roi.get("type") != "rectangle" or not roi.get("rationale"):
        raise ValueError("A physically justified rectangle ROI is required")
    bounds = roi.get("bounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError("ROI bounds must be [xmin, ymin, xmax, ymax]")
    xmin, ymin, xmax, ymax = [
        _finite_number(value, "roi.bounds") for value in bounds
    ]
    for extent in (xmax - xmin, ymax - ymin):
        if extent <= 0 or not math.isclose(
                extent / resolution, round(extent / resolution), abs_tol=1e-8):
            raise ValueError("ROI extents must be positive whole truth cells")
    starts = data.get("starts", {})
    if not isinstance(starts, dict):
        raise ValueError("starts must be a JSON object")
    if set(starts) != set(ROBOT_NAMES):
        raise ValueError("starts must declare all and only three robot positions")
    for name in ROBOT_NAMES:
        position = starts[name]
        if not isinstance(position, list) or len(position) != 2:
            raise ValueError(f"starts.{name} must be [x, y]")
        x, y = [_finite_number(value, f"starts.{name}") for value in position]
        if not xmin <= x < xmax or not ymin <= y < ymax:
            raise ValueError(f"starts.{name} is outside the task ROI")
    quality = data.get("quality", {})
    if not isinstance(quality, dict):
        raise ValueError("quality must be a JSON object")
    for key in ("min_observed_accuracy", "min_occupied_iou", "max_false_free_ratio"):
        _finite_number(quality.get(key), f"quality.{key}", 0.0, 1.0)
    participation = data.get("participation", {})
    if not isinstance(participation, dict):
        raise ValueError("participation must be a JSON object")
    _finite_number(participation.get("min_path_length_m"),
                   "participation.min_path_length_m", .001)
    count = participation.get("min_goal_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("participation.min_goal_count must be a positive integer")
    return TaskContract(data, hashlib.sha256(payload).hexdigest(), world_path)


def _pose(element):
    pose = element.find("pose")
    if pose is None:
        return (0.0,) * 6
    if pose.get("relative_to") or pose.get("frame"):
        raise ValueError("Named-frame SDF poses are not supported by this contract")
    values = [float(value) for value in (pose.text or "").split()]
    if len(values) != 6 or not all(math.isfinite(value) for value in values):
        raise ValueError("An SDF pose must have six finite values")
    if abs(values[3]) > 1e-6 or abs(values[4]) > 1e-6:
        raise ValueError("Rolled or pitched SDF geometry is unsupported")
    return tuple(values)


def _compose(parent, child):
    px, py, pz, _, _, yaw = parent
    x, y, z, _, _, child_yaw = child
    cosine, sine = math.cos(yaw), math.sin(yaw)
    return (px + cosine*x - sine*y, py + sine*x + cosine*y,
            pz + z, 0.0, 0.0, yaw + child_yaw)


def inspect_world_geometry(world_path, lidar_height_m=.131):
    """
    Audit all geometry, retaining unsupported objects instead of hiding them.

    Saved Gazebo state model/link poses are world coordinates. Unknown include
    resources, dynamic bodies, scaled states and named frames fail closed.
    """
    _finite_number(lidar_height_m, "lidar_height_m", 0.0)
    world = ET.parse(world_path).getroot().find("world")
    if world is None:
        raise ValueError(f"No world element in {world_path}")
    issues, rectangles, ignored = [], [], []
    vertical_boundaries, plane_heights = set(), set()
    states = world.findall("state")
    if len(states) > 1:
        issues.append({"object": "world", "reason": "multiple_saved_states"})
    state_models = {} if not states else {
        model.get("name"): model for model in states[0].findall("model")
    }
    for include in world.findall("include"):
        uri = include.findtext("uri", "")
        if uri in {"model://sun", "model://ground_plane"}:
            try:
                pose = _pose(include)
                if uri == "model://ground_plane":
                    vertical_boundaries.add(pose[2])
                    plane_heights.add(pose[2])
                if uri == "model://ground_plane" and pose[2] >= lidar_height_m:
                    raise ValueError("ground plane reaches the lidar slice")
                ignored.append({"object": uri, "reason": "audited_light_or_ground"})
            except ValueError as exc:
                issues.append({"object": uri, "reason": str(exc)})
        else:
            issues.append({"object": uri, "reason": "unresolved_include"})
    for actor in world.findall("actor"):
        issues.append({"object": actor.get("name"), "reason": "dynamic_actor"})
    for model in world.findall("model"):
        name = model.get("name", "")
        if model.findtext("static", "false").strip().lower() not in {"1", "true"}:
            issues.append({"object": name, "reason": "non_static_model"})
        if model.find("model") is not None or model.find("include") is not None:
            issues.append({"object": name, "reason": "nested_model_or_include"})
        state_model = state_models.get(name)
        try:
            model_pose = _pose(state_model if state_model is not None else model)
            if state_model is not None:
                scale = state_model.findtext("scale", "1 1 1").split()
                if len(scale) != 3 or any(
                        not math.isfinite(float(v)) or abs(float(v)-1) > 1e-9
                        for v in scale):
                    raise ValueError("scaled_saved_state")
        except ValueError as exc:
            issues.append({"object": name, "reason": str(exc)})
            continue
        state_links = {} if state_model is None else {
            link.get("name"): link for link in state_model.findall("link")
        }
        for link in model.findall("link"):
            link_name = link.get("name", "")
            try:
                # Gazebo state stores absolute link poses, not model-relative poses.
                if link_name in state_links:
                    link_pose = _pose(state_links[link_name])
                else:
                    link_pose = _compose(model_pose, _pose(link))
            except ValueError as exc:
                issues.append({"object": f"{name}/{link_name}", "reason": str(exc)})
                continue
            for collision in link.findall("collision"):
                identifier = f"{name}/{link_name}/{collision.get('name', '')}"
                try:
                    pose = _compose(link_pose, _pose(collision))
                    geometry = collision.find("geometry")
                    if geometry is None or len(geometry) != 1:
                        raise ValueError("missing_or_ambiguous_geometry")
                    kind = geometry[0].tag
                    if kind == "plane":
                        normal = geometry[0].findtext("normal", "").split()
                        if len(normal) != 3 or not np.allclose(
                                np.array(normal, dtype=float), [0, 0, 1]):
                            raise ValueError("unsupported_plane_normal")
                        vertical_boundaries.add(pose[2])
                        plane_heights.add(pose[2])
                        if abs(pose[2] - lidar_height_m) < 1e-6:
                            raise ValueError("plane_intersects_lidar_slice")
                        ignored.append({"object": identifier,
                                        "reason": "horizontal_plane_outside_slice"})
                        continue
                    if kind != "box":
                        raise ValueError(f"unsupported_{kind}")
                    size = [float(v) for v in geometry[0].findtext("size", "").split()]
                    if len(size) != 3 or not all(math.isfinite(v) and v > 0 for v in size):
                        raise ValueError("invalid_box_size")
                    x, y, z, _, _, yaw = pose
                    sx, sy, sz = size
                    vertical_boundaries.update((z-sz/2, z+sz/2))
                    if not z - sz/2 <= lidar_height_m <= z + sz/2:
                        ignored.append({"object": identifier, "reason": "box_outside_slice"})
                        continue
                    rectangles.append((x, y, yaw, sx, sy))
                except ValueError as exc:
                    issues.append({"object": identifier, "reason": str(exc)})
    if not rectangles:
        issues.append({"object": "world", "reason": "no_supported_slice_boxes"})
    original_bounds = None
    if rectangles:
        corners = []
        for x, y, yaw, sx, sy in rectangles:
            cosine, sine = math.cos(yaw), math.sin(yaw)
            for dx in (-sx/2, sx/2):
                for dy in (-sy/2, sy/2):
                    corners.append((x+cosine*dx-sine*dy, y+sine*dx+cosine*dy))
        original_bounds = [min(x for x, _ in corners), min(y for _, y in corners),
                           max(x for x, _ in corners), max(y for _, y in corners)]
    audit = {
        "world_file": Path(world_path).name,
        "world_sha256": hashlib.sha256(Path(world_path).read_bytes()).hexdigest(),
        "lidar_height_m": lidar_height_m,
        "saved_state_count": len(states),
        "rectangle_count": len(rectangles),
        "supported_collision_bounds": original_bounds,
        "vertical_boundaries_m": sorted(vertical_boundaries),
        "plane_heights_m": sorted(plane_heights),
        "unsupported_collision_count": len(issues),
        "unsupported": issues,
        "ignored": ignored,
    }
    return rectangles, audit


def audit_lidar_slice_invariance(world_path, minimum_height_m=.02,
                                 maximum_height_m=.25, reference_height_m=.131):
    """
    Check exact static collision slices at every possible height transition.

    This is an offline geometry check. It does not prove a robot's laser beam
    stays inside the band, and never changes the task ROI or occupied mask.
    """
    minimum = _finite_number(minimum_height_m, "minimum_height_m")
    maximum = _finite_number(maximum_height_m, "maximum_height_m")
    reference = _finite_number(reference_height_m, "reference_height_m")
    if not minimum < maximum or not minimum <= reference <= maximum:
        raise ValueError("Slice band must be ordered and contain the reference height")
    rectangles, reference_audit = inspect_world_geometry(world_path, reference)
    probes = {minimum, maximum, reference}
    for boundary in reference_audit["vertical_boundaries_m"]:
        if minimum <= boundary <= maximum:
            probes.add(boundary)
            for direction in (-math.inf, math.inf):
                adjacent = math.nextafter(boundary, direction)
                if minimum <= adjacent <= maximum:
                    probes.add(adjacent)
    plane_crossings = [height for height in reference_audit["plane_heights_m"]
                       if minimum <= height <= maximum]
    rows = []
    invariant = not reference_audit["unsupported"] and not plane_crossings
    for height in sorted(probes):
        actual, audit = inspect_world_geometry(world_path, height)
        identical = actual == rectangles
        valid = identical and not audit["unsupported"]
        invariant = invariant and valid
        rows.append({"height_m": height, "rectangle_count": len(actual),
                     "exact_rectangles_match_reference": identical,
                     "unsupported": audit["unsupported"]})
    return {
        "type": "offline_vertical_slice_invariance_not_native_sensor_proof",
        "world_file": Path(world_path).name,
        "world_sha256": reference_audit["world_sha256"],
        "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "minimum_height_m": minimum, "maximum_height_m": maximum,
        "reference_height_m": reference,
        "vertical_boundaries_m": reference_audit["vertical_boundaries_m"],
        "plane_crossings_m": plane_crossings, "probes": rows,
        "invariant": bool(invariant), "denominator_modified": False,
    }


def _rasterize(rectangles, bounds, resolution, intersection=True):
    xmin, ymin, xmax, ymax = bounds
    width = round((xmax-xmin)/resolution)
    height = round((ymax-ymin)/resolution)
    occupied = np.zeros((height, width), dtype=bool)
    half_cell = resolution/2 if intersection else 0.0
    for x, y, yaw, sx, sy in rectangles:
        cosine, sine = math.cos(yaw), math.sin(yaw)
        ac, ass = abs(cosine), abs(sine)
        half_x, half_y = sx/2, sy/2
        extent_x = half_x*ac + half_y*ass
        extent_y = half_x*ass + half_y*ac
        x0 = max(0, math.floor((x-extent_x-xmin)/resolution)-1)
        x1 = min(width, math.ceil((x+extent_x-xmin)/resolution)+1)
        y0 = max(0, math.floor((y-extent_y-ymin)/resolution)-1)
        y1 = min(height, math.ceil((y+extent_y-ymin)/resolution)+1)
        if x1 <= x0 or y1 <= y0:
            continue
        xs = xmin + (np.arange(x0, x1)+.5)*resolution
        ys = ymin + (np.arange(y0, y1)+.5)*resolution
        dx, dy = np.meshgrid(xs-x, ys-y)
        epsilon = 1e-10 if intersection else -1e-10
        # Separating-axis test between an oriented box slice and a grid cell.
        overlap = ((np.abs(dx) < extent_x+half_cell-epsilon)
                   & (np.abs(dy) < extent_y+half_cell-epsilon)
                   & (np.abs(cosine*dx+sine*dy)
                      < half_x+half_cell*(ac+ass)-epsilon)
                   & (np.abs(-sine*dx+cosine*dy)
                      < half_y+half_cell*(ac+ass)-epsilon))
        occupied[y0:y1, x0:x1] |= overlap
    return occupied


def load_contract_truth(world_path, contract):
    """Build the full declared ROI; diagnostic feasibility never trims it."""
    world_path = Path(world_path).resolve()
    world_digest = hashlib.sha256(world_path.read_bytes()).hexdigest()
    if world_path != contract.world_path or world_digest != contract.data["world_sha256"]:
        raise ValueError("Contract world path or content changed after loading")
    rectangles, audit = inspect_world_geometry(world_path, contract.data["lidar_height_m"])
    if audit["unsupported"]:
        raise ValueError("Unsupported task geometry: " + json.dumps(audit["unsupported"]))
    bounds, resolution = contract.data["roi"]["bounds"], contract.data["resolution"]
    occupied = _rasterize(rectangles, bounds, resolution)
    if not np.any(occupied) or np.all(occupied):
        raise ValueError("ROI must contain both occupied and free cells")
    return ContractTruthGrid(
        occupied, bounds[0], bounds[1], resolution, len(rectangles), 0,
        np.ones(occupied.shape, dtype=bool), world_digest, contract.sha256,
        contract.data["lidar_height_m"], audit,
        _rasterize(rectangles, bounds, resolution, intersection=False),
    )


def compare_contract_occupancy_grid(truth, data, width, height, resolution,
                                    origin, yaw=0.0):
    """Sample map cells at truth centers with ROI coverage and quality counts."""
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError("Map dimensions must be positive integers")
    resolution = _finite_number(resolution, "map resolution", .000001)
    yaw = _finite_number(yaw, "map yaw")
    if len(origin) < 2:
        raise ValueError("Map origin requires x and y")
    ox, oy = [_finite_number(value, "map origin") for value in origin[:2]]
    values = np.asarray(data)
    if values.size != width*height or not np.issubdtype(values.dtype, np.integer):
        raise ValueError("Map payload must contain exactly width*height integers")
    if np.any((values < -1) | (values > 100)):
        raise ValueError("Occupancy values must be in [-1, 100]")
    estimated = values.reshape(height, width)
    iy, ix = np.indices(truth.occupied.shape)
    dx = truth.origin_x+(ix+.5)*truth.resolution-ox
    dy = truth.origin_y+(iy+.5)*truth.resolution-oy
    cosine, sine = math.cos(yaw), math.sin(yaw)
    mx = np.floor((cosine*dx+sine*dy)/resolution).astype(int)
    my = np.floor((-sine*dx+cosine*dy)/resolution).astype(int)
    inside = (mx >= 0) & (mx < width) & (my >= 0) & (my < height)
    sampled = np.full(truth.occupied.shape, -1, dtype=np.int16)
    sampled[inside] = estimated[my[inside], mx[inside]]
    roi = truth.roi_mask
    known = (sampled >= 0) & roi
    predicted_occupied = sampled >= 50
    occupied = truth.occupied & roi
    free = ~truth.occupied & roi
    correct = known & (predicted_occupied == truth.occupied)
    correct_free = known & free & ~predicted_occupied
    false_free = known & occupied & ~predicted_occupied
    intersection = occupied & known & predicted_occupied
    union = occupied | (known & predicted_occupied)

    def count(mask):
        return int(np.count_nonzero(mask))

    def ratio(numerator, denominator):
        return count(numerator)/max(1, count(denominator))
    return {
        "truth_cell_count": count(roi), "truth_free_cell_count": count(free),
        "truth_occupied_cell_count": count(occupied),
        "known_truth_cell_count": count(known), "correct_truth_cell_count": count(correct),
        "correct_free_cell_count": count(correct_free),
        "false_free_cell_count": count(false_free),
        "known_coverage_ratio": ratio(known, roi),
        "correct_coverage_ratio": ratio(correct, roi),
        "correct_free_coverage_ratio": ratio(correct_free, free),
        "observed_accuracy": ratio(correct, known),
        "occupied_iou": ratio(intersection, union),
        "false_free_ratio": ratio(false_free, occupied),
        "false_free_denominator": "truth_occupied_cell_count",
    }


def _line_is_clear(occupied, source, target):
    """Conservative supercover traversal, including diagonal corner neighbors."""
    y, x = source
    ty, tx = target
    dx, dy = tx-x, ty-y
    sx, sy = int(np.sign(dx)), int(np.sign(dy))
    step_x = math.inf if not dx else 1/abs(dx)
    step_y = math.inf if not dy else 1/abs(dy)
    next_x, next_y = step_x/2, step_y/2
    while (y, x) != (ty, tx):
        if next_x < next_y-1e-12:
            x += sx
            next_x += step_x
        elif next_y < next_x-1e-12:
            y += sy
            next_y += step_y
        else:
            if occupied[y, x+sx] or occupied[y+sy, x]:
                return False
            x, y = x+sx, y+sy
            next_x, next_y = next_x+step_x, next_y+step_y
        if occupied[y, x]:
            return False
    return True


def diagnose_contract_geometry(truth, contract):
    """
    Offline conservative reachability/visibility evidence, never a task mask.

    Visibility is a lower bound for a continuous ideal horizontal range sensor
    at reachable centers; it does not model finite beams, SLAM or robot traffic.
    A low bound is inconclusive, not permission to remove cells from the ROI.
    """
    occupied = truth.occupied
    padded = np.pad(occupied, 1, constant_values=True)
    distance = ndimage.distance_transform_edt(~padded)[1:-1, 1:-1]*truth.resolution
    # Conservative occupied-cell squares have a half-diagonal beyond their centers.
    clearance = np.maximum(0, distance-truth.resolution/math.sqrt(2))
    traversable = (~occupied) & (clearance >= contract.data["robot_radius_m"])
    labels, components = ndimage.label(
        traversable, structure=ndimage.generate_binary_structure(2, 1))
    start_report, start_labels = {}, set()
    for name, (x, y) in contract.data["starts"].items():
        ix = math.floor((x-truth.origin_x)/truth.resolution)
        iy = math.floor((y-truth.origin_y)/truth.resolution)
        label = int(labels[iy, ix])
        if label:
            start_labels.add(label)
        start_report[name] = {"cell": [iy, ix], "traversable": bool(label),
                              "clearance_lower_bound_m": float(clearance[iy, ix])}
    reachable = np.isin(labels, list(start_labels)) & traversable
    free = ~occupied
    visible = reachable.copy()
    if np.any(reachable):
        nearest_distance, nearest = ndimage.distance_transform_edt(
            ~reachable, return_indices=True)
        for iy, ix in np.argwhere(free & ~reachable):
            if nearest_distance[iy, ix]*truth.resolution > contract.data["lidar_range_m"]:
                continue
            source = (int(nearest[0, iy, ix]), int(nearest[1, iy, ix]))
            if _line_is_clear(occupied, source, (int(iy), int(ix))):
                visible[iy, ix] = True
    else:
        nearest_distance = np.full(occupied.shape, math.inf)
    optimistic = free & (nearest_distance*truth.resolution <= contract.data["lidar_range_m"])
    free_components, free_component_count = ndimage.label(
        free, structure=ndimage.generate_binary_structure(2, 1))
    sizes = np.bincount(free_components.ravel())[1:]
    free_count = int(np.count_nonzero(free))
    rectangles, legacy_audit = inspect_world_geometry(contract.world_path, .2)
    original_bounds = legacy_audit["supported_collision_bounds"]
    legacy_counts = None
    if original_bounds:
        resolution = truth.resolution
        xmin, ymin, xmax, ymax = original_bounds
        aligned = [math.floor(xmin/resolution)*resolution,
                   math.floor(ymin/resolution)*resolution,
                   math.ceil(xmax/resolution)*resolution,
                   math.ceil(ymax/resolution)*resolution]
        legacy = _rasterize(rectangles, aligned, resolution, intersection=False)
        legacy_counts = {
            "slice_height_m": .2, "bounds": aligned,
            "free_cell_count": int(np.count_nonzero(~legacy)),
            "occupied_cell_count": int(np.count_nonzero(legacy)),
            "unsupported_collision_count": legacy_audit["unsupported_collision_count"],
            "role": "legacy_box_bounds_center_sampling_diagnostic_only",
        }
    return {
        "type": "offline_geometry_diagnostic_not_task_success",
        "truth_rasterization": RASTERIZATION,
        "roi_bounds": contract.data["roi"]["bounds"],
        "truth_free_cell_count": free_count,
        "truth_occupied_cell_count": int(np.count_nonzero(occupied)),
        "center_sampled_free_cell_count": int(
            np.count_nonzero(~truth.center_sampled_occupied)),
        "center_vs_intersection_changed_cells": int(np.count_nonzero(
            truth.center_sampled_occupied != occupied)),
        "free_component_count": int(free_component_count),
        "free_component_sizes_descending": sorted(map(int, sizes), reverse=True),
        "traversable_center_component_count": int(components),
        "reachable_center_cell_count": int(np.count_nonzero(reachable)),
        "unreachable_center_free_cell_count": int(np.count_nonzero(free & ~reachable)),
        "starts": start_report,
        "visible_free_fraction_lower_bound": float(np.count_nonzero(visible))/max(1, free_count),
        "range_only_free_fraction_upper_bound": (
            float(np.count_nonzero(optimistic))/max(1, free_count)),
        "visibility_limitations": [
            "continuous ideal lidar, no finite beam or SLAM accuracy guarantee",
            "nearest reachable center only; unproven cells may be visible from other centers",
            "center-based .25m disk and conservative grid clearance; no multi-robot traffic proof",
            "sensor offset, minimum range and body occlusion require native task evidence",
        ],
        "denominator_trimmed_by_diagnostic": False,
        "geometry_audit": truth.geometry_audit,
        "legacy_original_grid_diagnostic": legacy_counts,
    }
