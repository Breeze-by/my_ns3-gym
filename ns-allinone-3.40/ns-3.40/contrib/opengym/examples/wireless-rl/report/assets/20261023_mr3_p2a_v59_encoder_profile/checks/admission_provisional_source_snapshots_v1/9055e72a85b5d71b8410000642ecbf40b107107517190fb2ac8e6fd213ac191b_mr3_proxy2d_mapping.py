"""Sensor-only occupancy evidence candidate; not enabled by ProxyWorld.

This is a versioned CPU candidate, not SLAM or a probability model. It retains
v1's integer ray walk, changes grid-line hit ties to the forward side of the
ray, and replaces last-write-wins with bounded per-scan evidence. It cannot
distinguish persistent range/pose bias from a real obstacle disappearing.
"""

import math
import struct

import numpy as np


MODEL = "range_ray_bounded_evidence_v2"
HIT_INCREMENT = 2
FREE_DECREMENT = 1
EVIDENCE_LIMIT = 4
OCCUPIED_THRESHOLD = 2
FREE_THRESHOLD = -2
TIE_ULPS = 4
# Reject impractical inputs before allocating the vectorized ray walk.
MAX_RAY_SAMPLES = 8_000_000


def _numeric_vector(value, length=None):
    raw = np.asarray(value)
    if raw.ndim != 1 or raw.dtype.kind not in "iuf" or not raw.size:
        raise ValueError("nonempty finite real vector required")
    array = np.asarray(raw, dtype=np.float64)
    if (length is not None and len(array) != length) or not np.isfinite(array).all():
        raise ValueError("finite matching vector required")
    return array


class SensorMapperV2:
    """One local sensor stream; construct a fresh instance on episode reset.

    Inputs contain no world, true pose, obstacle model, peer state or hit bit.
    ``scan_id`` is a monotonically increasing source sequence, not a map
    version or endpoint identity. Repeated delivery of the latest exact scan
    is idempotent. Older/reused IDs with changed content are rejected.
    """

    def __init__(self, shape, resolution, origin):
        if (not isinstance(shape, (tuple, list)) or len(shape) != 2
                or any(type(v) is not int or v <= 0 for v in shape)):
            raise ValueError("positive integer (height, width) required")
        if type(resolution) not in (int, float) or not math.isfinite(resolution) or resolution <= 0:
            raise ValueError("positive finite resolution required")
        coordinates = _numeric_vector(origin, 2)
        self.shape = tuple(shape)
        self.resolution = float(resolution)
        self.origin = tuple(map(float, coordinates))
        self._score = np.zeros(self.shape, dtype=np.int8)
        self._last_scan_id = None
        self._last_payload = ()

    def integrate(self, scan_id, sensor_pose, angles, ranges, range_min=.12, range_max=10.):
        """Consume one validated scan; True for new input, False for a duplicate.

        Each cell receives at most one vote per scan; any hit wins conflicting
        free votes. Values between the free/occupied thresholds are unknown.
        A range equal to range_max supplies free evidence only. No physical
        hit flag, uncertainty dilation or guessed obstacle thickness is used.
        """
        if type(scan_id) is not int or scan_id < 0:
            raise ValueError("nonnegative integer source scan ID required")
        pose = _numeric_vector(sensor_pose, 3)
        angles = _numeric_vector(angles)
        ranges = _numeric_vector(ranges, len(angles))
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (range_min, range_max))
                or not 0 < range_min < range_max
                or np.any(ranges < range_min) or np.any(ranges > range_max)):
            raise ValueError("finite ranges within positive declared sensor limits required")
        payload = (pose.tobytes(), angles.tobytes(), ranges.tobytes(),
                   struct.pack("dd", range_min, range_max))
        if self._last_scan_id is not None:
            if scan_id < self._last_scan_id:
                raise ValueError("out-of-order source scan ID")
            if scan_id == self._last_scan_id:
                if payload != self._last_payload:
                    raise ValueError("source scan ID reused with different content")
                return False

        free, hits = self._votes(pose, angles, ranges, range_max)
        # Complete validation/rasterization before mutating any persistent state.
        flat = self._score.ravel()
        flat[free] = np.maximum(-EVIDENCE_LIMIT, flat[free] - FREE_DECREMENT)
        flat[hits] = np.minimum(EVIDENCE_LIMIT, flat[hits] + HIT_INCREMENT)
        self._last_scan_id, self._last_payload = scan_id, payload
        return True

    def _votes(self, pose, angles, ranges, maximum):
        heading = angles + pose[2]
        if not np.isfinite(heading).all():
            raise ValueError("finite sensor ray headings required")
        directions = np.stack((np.cos(heading), np.sin(heading)), axis=-1)
        with np.errstate(over="ignore", invalid="ignore"):
            origin = (pose[:2] - self.origin) / self.resolution
            endpoint = origin + directions * ranges[:, None] / self.resolution
        if (not np.isfinite(origin).all() or not np.isfinite(endpoint).all()
                or np.max(np.abs(endpoint)) > 2**30 or np.max(np.abs(origin)) > 2**30):
            raise ValueError("ray coordinates exceed supported finite integer lattice")
        hit = ranges < maximum
        # Four lattice ULPs cover numerical arithmetic at an exact grid line;
        # this is not a metric noise band. Direction cannot resolve grazing
        # surfaces/corners in general, and no truth-based choice is made.
        nearest = np.rint(endpoint)
        tolerance = TIE_ULPS * np.spacing(np.maximum(1., np.abs(endpoint)))
        ties = (np.abs(endpoint - nearest) <= tolerance) & hit[:, None] & (directions != 0.)
        endpoint = np.where(ties, nearest, endpoint)
        endpoint = np.where(ties & (directions < 0.), np.nextafter(endpoint, -np.inf), endpoint)
        start = np.floor(origin).astype(np.int64)
        end = np.floor(endpoint).astype(np.int64)
        delta = end - start
        counts = np.max(np.abs(delta), axis=1)
        samples = int(counts.max()) + 1
        if samples * len(ranges) > MAX_RAY_SAMPLES:
            raise ValueError("scan exceeds bounded ray rasterization workspace")
        steps = np.arange(samples)
        fraction = steps[None, :] / np.maximum(counts[:, None], 1)
        points = np.rint(start + fraction[..., None] * delta[:, None, :]).astype(np.int64)
        valid = ((steps[None, :] <= counts[:, None]) & (points[..., 0] >= 0)
                 & (points[..., 0] < self.shape[1]) & (points[..., 1] >= 0)
                 & (points[..., 1] < self.shape[0]))
        free = valid & ((steps[None, :] < counts[:, None]) | ~hit[:, None])
        free_cells = np.unique(points[..., 1][free] * self.shape[1] + points[..., 0][free])
        hit &= ((end[:, 0] >= 0) & (end[:, 0] < self.shape[1])
                & (end[:, 1] >= 0) & (end[:, 1] < self.shape[0]))
        hit_cells = np.unique(end[hit, 1] * self.shape[1] + end[hit, 0])
        return np.setdiff1d(free_cells, hit_cells, assume_unique=True), hit_cells

    def grid(self):
        result = np.full(self.shape, -1, dtype=np.int8)
        result[self._score <= FREE_THRESHOLD] = 0
        result[self._score >= OCCUPIED_THRESHOLD] = 100
        return result

    def evidence(self):
        return self._score.copy()

    @property
    def memory_bytes(self):
        """Persistent ndarray + exact payload bytes; excludes Python overhead."""
        return self._score.nbytes + sum(map(len, self._last_payload))
