"""Explicit 2D plant/sensor proxy; no navigation or exploration decisions.

World geometry is private to ray casting, disk-contact sampling and the
separately requested evaluation_state(). Own odometry integrates simulated
wheel encoder increments independently; mapping uses only those estimates and
range samples. This supplies no native SLAM, Nav2, DDS, body-contact or drive
receipt credit. Body commands have instantaneous kinematic response; contacts
are conservative blocked-motion proxy events, not Gazebo contact sensors.
"""

import copy
import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from .mr3_task_contract import (
    inspect_world_geometry, load_contract_truth, load_task_contract,
)


ROBOTS = ("tb1", "tb2", "tb3")
SCENES = ("open", "rooms", "corridors")
QUANTUM_NS = 20_000_000
SCAN_PERIOD_NS = 50_000_000
RESOLUTION = .05
WHEEL_SEPARATION = .287
ENCODER_SCALE_STD = .0002


def integrate_pose(pose, linear, angular, duration):
    """Exact constant-command unicycle arc, also used for sensor-time poses."""
    x, y, heading = map(float, pose)
    turn = angular * duration
    if abs(turn) < 1e-12:
        distance = linear * duration
        x += distance * math.cos(heading + turn / 2.)
        y += distance * math.sin(heading + turn / 2.)
    else:
        radius = linear / angular
        x += radius * (math.sin(heading + turn) - math.sin(heading))
        y -= radius * (math.cos(heading + turn) - math.cos(heading))
    return np.array((x, y, math.atan2(math.sin(heading + turn), math.cos(heading + turn))))


def ray_box_ranges(origin, directions, rectangles, maximum):
    """Vectorized analytic intersections with audited rotated SDF boxes."""
    directions = np.asarray(directions, dtype=float)
    boxes = np.asarray(rectangles, dtype=float).reshape((-1, 5))
    if not len(boxes):
        return np.full(len(directions), maximum, dtype=float)
    cosine, sine = np.cos(boxes[:, 2]), np.sin(boxes[:, 2])
    delta = np.asarray(origin, dtype=float) - boxes[:, :2]
    local_origin = np.stack((delta[:, 0] * cosine + delta[:, 1] * sine,
                             -delta[:, 0] * sine + delta[:, 1] * cosine), axis=-1)
    local_direction = np.stack((directions[:, 0, None] * cosine + directions[:, 1, None] * sine,
                                -directions[:, 0, None] * sine + directions[:, 1, None] * cosine), axis=-1)
    half = boxes[:, 3:] / 2.
    parallel = np.abs(local_direction) < 1e-14
    divisor = np.where(parallel, 1., local_direction)
    first = (-half - local_origin) / divisor
    second = (half - local_origin) / divisor
    low, high = np.minimum(first, second), np.maximum(first, second)
    outside = np.abs(local_origin) > half
    low = np.where(parallel, np.where(outside, np.inf, -np.inf), low)
    high = np.where(parallel, np.where(outside, -np.inf, np.inf), high)
    entry, exit_ = low.max(axis=-1), high.min(axis=-1)
    hit = (exit_ >= np.maximum(entry, 0.))
    distance = np.where(entry >= 0., entry, exit_)
    return np.minimum(np.where(hit, distance, np.inf).min(axis=1), maximum)


def ray_disk_ranges(origin, directions, centers, radius, maximum):
    """Other robot bodies appear only as ordinary local ray returns."""
    centers = np.asarray(centers, dtype=float).reshape((-1, 2))
    if not len(centers):
        return np.full(len(directions), maximum, dtype=float)
    delta = centers - np.asarray(origin)
    projection = np.asarray(directions) @ delta.T
    discriminant = projection * projection - np.sum(delta * delta, axis=1) + radius * radius
    root = np.sqrt(np.maximum(0., discriminant))
    first, second = projection - root, projection + root
    distance = np.where(first >= 0., first, second)
    hit = (discriminant >= 0.) & (distance >= 0.)
    return np.minimum(np.where(hit, distance, np.inf).min(axis=1), maximum)


def laser_configuration(model_path):
    """Read current sensor parameters; explicit reach selects 20 Hz only."""
    model_path = Path(model_path)
    sensor = ET.parse(model_path).getroot().find(".//sensor[@name='hls_lfcd_lds']")
    if sensor is None:
        raise ValueError("missing actual hls_lfcd_lds sensor")
    horizontal = sensor.find("ray/scan/horizontal")
    ranges = sensor.find("ray/range")
    noise = sensor.find("ray/noise")
    pose = [float(value) for value in sensor.findtext("pose", "0 0 0 0 0 0").split()]
    if len(pose) != 6 or any(not math.isfinite(v) for v in pose):
        raise ValueError("finite six-field sensor pose required")
    value = {"samples": int(horizontal.findtext("samples")),
             "horizontal_resolution": float(horizontal.findtext("resolution")),
             "min_angle": float(horizontal.findtext("min_angle")),
             "max_angle": float(horizontal.findtext("max_angle")),
             "range_min": float(ranges.findtext("min")),
             "range_max": float(ranges.findtext("max")),
             "range_resolution": float(ranges.findtext("resolution")),
             "noise_mean": float(noise.findtext("mean")),
             "noise_std": float(noise.findtext("stddev")),
             "noise_type": noise.findtext("type"),
             "frame_offset": pose[:2], "frame_yaw": pose[5],
             "period_ns": SCAN_PERIOD_NS, "effective_rate_hz": 20,
             "base_model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
             "profile": "mr3-reach-lidar-20hz-v1"}
    if (value["samples"] != 360 or value["range_min"] != .12
            or value["range_max"] != 10. or value["noise_mean"] != 0.
            or value["noise_std"] != .01 or value["noise_type"] != "gaussian"
            or value["horizontal_resolution"] != 1. or value["min_angle"] != 0.
            or value["max_angle"] != 6.28 or value["range_resolution"] != .015
            or pose != [-.064, 0., .121, 0., 0., 0.]):
        raise ValueError("proxy requires the declared current laser model")
    return value


class ProxyWorld:
    """Three local sensor estimators around a private deterministic 2D plant."""

    def __init__(self, scene, seed, quantum_sec=.02, *, asset_root=None):
        if scene not in SCENES or type(seed) is not int or seed < 0:
            raise ValueError("declared scene and nonnegative integer seed required")
        if type(quantum_sec) not in (int, float) or quantum_sec not in (.02, .01):
            raise ValueError("20ms integration, or explicit 10ms convergence comparison, required")
        assets = (Path(__file__).resolve().parents[2] / "multi_robot"
                  if asset_root is None else Path(asset_root).resolve())
        world = assets / f"worlds/p1c_{scene}.world"
        self.contract = load_task_contract(assets / f"config/mr3_p1a/{scene}.json", world)
        self._truth = load_contract_truth(world, self.contract)
        self._rectangles, audit = inspect_world_geometry(world, self.contract.data["lidar_height_m"])
        if audit["unsupported"] or self._truth.resolution != RESOLUTION:
            raise ValueError("unsupported geometry or non-0.05m native lattice")
        self.scene, self.seed = scene, seed
        self.quantum_ns = round(quantum_sec * 1e9)
        self.resolution = RESOLUTION
        self.origin = (self._truth.origin_x, self._truth.origin_y)
        self.shape = self._truth.occupied.shape
        self.starts = copy.deepcopy(self.contract.data["starts"])
        self._radius = self.contract.data["robot_radius_m"]
        self._laser = laser_configuration(assets / "models/turtlebot3_waffle/model.sdf")
        self._angles = np.linspace(self._laser["min_angle"], self._laser["max_angle"], self._laser["samples"])
        self.metadata = {"schema": "mr3-proxy2d-world-v1", "scene": scene, "seed": seed,
            "robots": list(ROBOTS), "quantum_ns": self.quantum_ns, "resolution": RESOLUTION,
            "world_sha256": self.contract.data["world_sha256"], "contract_sha256": self.contract.sha256,
            "laser": copy.deepcopy(self._laser), "encoder_scale_std": ENCODER_SCALE_STD,
            "wheel_separation": WHEEL_SEPARATION, "local_map": "range_endpoints_and_observed_ray_cells_v1",
            "motion": "instantaneous unicycle; disk collision blocks translation; wheels may slip",
            "contact": "sampled midpoint/end disk proxy; no native 18-source credit",
            "odometry": "independent biased wheel encoder integral; no truth pose correction",
            "mapping": "estimated odometry plus local ray returns; no SLAM or loop closure",
            "native_receipts": False, "policy_calls": 0, "optimizer_steps": 0}
        self.reset()

    def reset(self):
        self.time_ns = 0
        self._poses = {name: np.array((*self.starts[name], 0.), dtype=float) for name in ROBOTS}
        self._estimated = {name: value.copy() for name, value in self._poses.items()}
        self._commands = {name: (0., 0.) for name in ROBOTS}
        self._velocities = {name: (0., 0.) for name in ROBOTS}
        self._encoder_scale, self._laser_random = {}, {}
        for index, name in enumerate(ROBOTS):
            self._encoder_scale[name] = 1. + np.random.default_rng(
                np.random.SeedSequence((self.seed, index, 1))).normal(0., ENCODER_SCALE_STD, 2)
            self._laser_random[name] = np.random.default_rng(np.random.SeedSequence((self.seed, index, 2)))
        self._maps = {name: np.full(self.shape, -1, dtype=np.int8) for name in ROBOTS}
        self._map_versions = {name: 0 for name in ROBOTS}
        self._scans, self._last_ray_cells = {}, {}
        self._scan_sequence = self._odom_sequence = 0
        self._next_scan_ns = 0
        self._paths = {name: 0. for name in ROBOTS}
        self._active_contacts = set()
        self._contact_events = []
        self._sense(self._poses, self._estimated, 0)
        self._next_scan_ns = SCAN_PERIOD_NS
        return self.own_sensors()

    def apply_commands(self, commands):
        if not isinstance(commands, dict) or set(commands) != set(ROBOTS):
            raise ValueError("one complete command for each of tb1/tb2/tb3 required")
        checked = {}
        for name in ROBOTS:
            command = commands[name]
            if not isinstance(command, (tuple, list)) or len(command) != 2:
                raise ValueError("commands must be (linear, angular) pairs")
            if any(type(value) not in (int, float) or not math.isfinite(value)
                   or abs(value) > limit for value, limit in zip(command, (.20, .8))):
                raise ValueError("finite commands within declared .20m/s and .8rad/s bounds required")
            checked[name] = tuple(map(float, command))
        self._commands = checked

    def _wall_collision(self, point):
        boxes = np.asarray(self._rectangles)
        delta = np.asarray(point) - boxes[:, :2]
        cosine, sine = np.cos(boxes[:, 2]), np.sin(boxes[:, 2])
        local = np.stack((delta[:, 0] * cosine + delta[:, 1] * sine,
                          -delta[:, 0] * sine + delta[:, 1] * cosine), axis=-1)
        distance = np.maximum(np.abs(local) - boxes[:, 3:] / 2., 0.)
        return bool(np.any(np.sum(distance * distance, axis=1) <= self._radius * self._radius))

    def advance(self):
        """One bounded quantum. All returned state is local sensor estimation."""
        duration = self.quantum_ns / 1e9
        before = {name: pose.copy() for name, pose in self._poses.items()}
        estimated_before = {name: pose.copy() for name, pose in self._estimated.items()}
        proposals, middles = {}, {}
        for name in ROBOTS:
            v, w = self._commands[name]
            proposals[name] = integrate_pose(before[name], v, w, duration)
            middles[name] = integrate_pose(before[name], v, w, duration / 2.)
        contacts, blocked = set(), set()
        for name in ROBOTS:
            if self._wall_collision(proposals[name][:2]) or self._wall_collision(middles[name][:2]):
                contacts.add((name, "world")); blocked.add(name)
        for index, left in enumerate(ROBOTS):
            for right in ROBOTS[index + 1:]:
                if any(np.linalg.norm(table[left][:2] - table[right][:2]) <= 2 * self._radius
                       for table in (proposals, middles)):
                    contacts.add((left, right)); blocked.update((left, right))
        for pair in sorted(contacts - self._active_contacts):
            self._contact_events.append({"robots_or_world": list(pair),
                "source_clock_ns": self.time_ns + self.quantum_ns,
                "kind": "proxy_blocked_disk_contact", "native_contact": False})
        self._active_contacts = contacts
        measured = {}
        for name in ROBOTS:
            v, w = self._commands[name]
            actual_v = 0. if name in blocked else v
            self._poses[name] = integrate_pose(before[name], actual_v, w, duration)
            self._paths[name] += abs(actual_v) * duration
            wheel = np.array((v - w * WHEEL_SEPARATION / 2.,
                              v + w * WHEEL_SEPARATION / 2.)) * self._encoder_scale[name]
            measured[name] = ((wheel[0] + wheel[1]) / 2., (wheel[1] - wheel[0]) / WHEEL_SEPARATION)
            self._estimated[name] = integrate_pose(estimated_before[name], *measured[name], duration)
            self._velocities[name] = measured[name]
        end = self.time_ns + self.quantum_ns
        while self._next_scan_ns <= end:
            fraction = (self._next_scan_ns - self.time_ns) / 1e9
            physical, estimated = {}, {}
            for name in ROBOTS:
                v, w = self._commands[name]
                physical[name] = integrate_pose(before[name], 0. if name in blocked else v, w, fraction)
                estimated[name] = integrate_pose(estimated_before[name], *measured[name], fraction)
            self._sense(physical, estimated, self._next_scan_ns)
            self._next_scan_ns += SCAN_PERIOD_NS
        self.time_ns = end
        self._odom_sequence += 1
        return self.own_sensors()

    def _sensor_pose(self, pose):
        dx, dy = self._laser["frame_offset"]
        x, y, heading = pose
        return (x + math.cos(heading) * dx - math.sin(heading) * dy,
                y + math.sin(heading) * dx + math.cos(heading) * dy,
                heading + self._laser["frame_yaw"])

    def _sense(self, physical, estimated, clock_ns):
        self._scan_sequence += 1
        for name in ROBOTS:
            sx, sy, heading = self._sensor_pose(physical[name])
            directions = np.stack((np.cos(self._angles + heading), np.sin(self._angles + heading)), axis=-1)
            maximum = self._laser["range_max"]
            distances = np.minimum(
                ray_box_ranges((sx, sy), directions, self._rectangles, maximum),
                ray_disk_ranges((sx, sy), directions,
                    [physical[peer][:2] for peer in ROBOTS if peer != name], self._radius, maximum))
            measured = distances + self._laser_random[name].normal(0., self._laser["noise_std"], len(distances))
            # A max-range return remains max-range; no hidden hit bit reaches mapping.
            ranges = np.where(distances >= maximum, maximum, np.clip(measured, self._laser["range_min"], maximum))
            self._scans[name] = {"ranges": ranges, "angles": self._angles,
                "source_stamp": clock_ns / 1e9, "source_clock_ns": clock_ns,
                "sequence": self._scan_sequence, "range_min": self._laser["range_min"],
                "range_max": maximum, "frame_offset": list(self._laser["frame_offset"])}
            self._integrate_scan(name, estimated[name], ranges)
            self._map_versions[name] += 1

    def _integrate_scan(self, name, estimated, ranges):
        """Vectorized observed-ray carving, using no physical pose or world map."""
        sx, sy, heading = self._sensor_pose(estimated)
        directions = np.stack((np.cos(self._angles + heading), np.sin(self._angles + heading)), axis=-1)
        origin = (np.array((sx, sy)) - self.origin) / self.resolution
        start = np.floor(origin).astype(np.int64)
        end = np.floor(origin + directions * ranges[:, None] / self.resolution).astype(np.int64)
        hits = ranges < self._laser["range_max"]
        keys = np.column_stack((np.broadcast_to(start, end.shape), end, hits))
        previous = self._last_ray_cells.get(name)
        changed = np.ones(len(end), dtype=bool) if previous is None else np.any(keys != previous, axis=1)
        self._last_ray_cells[name] = keys
        if not changed.any():
            return
        end, hits = end[changed], hits[changed]
        delta = end - start
        counts = np.max(np.abs(delta), axis=1)
        steps = np.arange(int(counts.max()) + 1)
        fractions = steps[None, :] / np.maximum(counts[:, None], 1)
        points = np.rint(start + fractions[..., None] * delta[:, None, :]).astype(np.int64)
        valid = ((steps[None, :] <= counts[:, None]) & (points[..., 0] >= 0)
                 & (points[..., 0] < self.shape[1]) & (points[..., 1] >= 0)
                 & (points[..., 1] < self.shape[0]))
        free = valid & ((steps[None, :] < counts[:, None]) | ~hits[:, None])
        self._maps[name][points[..., 1][free], points[..., 0][free]] = 0
        # All current hit endpoints win conflicts with free ray cells.
        full_end = self._last_ray_cells[name][:, 2:4].astype(np.int64)
        full_hit = (self._last_ray_cells[name][:, 4].astype(bool)
                    & (full_end[:, 0] >= 0) & (full_end[:, 0] < self.shape[1])
                    & (full_end[:, 1] >= 0) & (full_end[:, 1] < self.shape[0]))
        self._maps[name][full_end[full_hit, 1], full_end[full_hit, 0]] = 100

    def own_sensors(self):
        result = {}
        for name in ROBOTS:
            x, y, heading = self._estimated[name]
            v, w = self._velocities[name]
            result[name] = {"odom": {"x": float(x), "y": float(y), "yaw": float(heading),
                "v": float(v), "w": float(w), "source_stamp": self.time_ns / 1e9,
                "source_clock_ns": self.time_ns, "sequence": self._odom_sequence},
                "scan": copy.deepcopy(self._scans[name])}
        return result

    def local_map(self, name):
        return self._maps[name].copy()

    def map_record(self, name):
        return {"grid": self.local_map(name), "resolution": self.resolution,
                "origin": self.origin, "source_stamp": self._scans[name]["source_stamp"],
                "source_clock_ns": self._scans[name]["source_clock_ns"],
                "version": self._map_versions[name]}

    def evaluation_state(self):
        """Privileged evaluator-only output; never include this in actor info."""
        return {"time_ns": self.time_ns,
            "poses": {name: {"x": float(pose[0]), "y": float(pose[1]), "yaw": float(pose[2])}
                      for name, pose in self._poses.items()},
            "path_lengths": dict(self._paths), "collision_events": len(self._contact_events),
            "contact_events": copy.deepcopy(self._contact_events), "native_contact_monitoring": False}
