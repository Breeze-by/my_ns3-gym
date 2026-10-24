"""Disabled sensor-only fixed-grid adapter to the existing Karto kernel.

This is not scan matching or native SLAM. The caller supplies an explicit
locally built ABI library, its own estimated body pose and its own scan. No
world geometry, physical pose, peer data or privileged evaluation is accepted.
Create a fresh object for each robot/epoch; there is no in-place epoch reset.
"""

import ctypes as C
from functools import wraps
import math
from pathlib import Path
from threading import RLock

import numpy as np


MODEL = "karto_native_addscan_fixed_grid_v1"
MAX_CELLS = 2_000_000
MAX_BEAMS = 4096
MAX_SCANS = 6300  # 315 s at 20 Hz: initial scan, .1 s warmup, 300 s task, close tail.


def _vector(value, size):
    raw = np.asarray(value)
    if raw.ndim != 1 or raw.size != size or raw.dtype.kind not in "iuf":
        raise ValueError("matching real vector required")
    result = np.array(raw, dtype=np.float64, order="C", copy=True)
    if not np.isfinite(result).all():
        raise ValueError("finite vector required")
    return result


def _real(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("finite real scalar required")
    return float(value)


def _serialized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


def _library(path):
    path = Path(path).resolve(strict=True)
    library = C.CDLL(str(path))
    library.mr3_karto_abi_version.restype = C.c_uint32
    if library.mr3_karto_abi_version() != 1:
        raise ValueError("unsupported Karto adapter ABI")
    library.mr3_karto_create.argtypes = [C.c_int32, C.c_int32] + [C.c_double] * 3 + [
        C.c_uint32] + [C.c_double] * 8 + [C.c_uint64]
    library.mr3_karto_create.restype = C.c_uint64
    library.mr3_karto_add_scan.argtypes = [C.c_uint64, C.POINTER(C.c_double),
        C.c_uint32, C.c_double, C.c_double, C.c_double]
    library.mr3_karto_add_scan.restype = C.c_int32
    library.mr3_karto_export.argtypes = [C.c_uint64, C.POINTER(C.c_uint32),
        C.POINTER(C.c_uint32), C.POINTER(C.c_int8), C.c_uint64]
    library.mr3_karto_export.restype = C.c_int32
    library.mr3_karto_destroy.argtypes = [C.c_uint64]
    library.mr3_karto_destroy.restype = C.c_int32
    library.mr3_karto_error.argtypes = []
    library.mr3_karto_error.restype = C.c_char_p
    library.mr3_karto_world_to_grid.argtypes = [C.c_uint64, C.c_double, C.c_double,
        C.POINTER(C.c_int32), C.POINTER(C.c_int32)]
    library.mr3_karto_world_to_grid.restype = C.c_int32
    return library, path


class KartoSensorMapper:
    """Source-idempotent, bounded native AddScan; explicit partial consumption.

    SDK lattice centers are public boundary-origin + resolution/2. SDK Round
    remains half-away-from-zero, including asymmetric ties at the outer edge.
    Native min/max skip, threshold tolerance and per-beam counting are retained.
    A partial/out-of-map scan is consumed once and may have changed the map.
    """

    def __init__(self, shape, resolution, origin, *, library_path, epoch,
                 angles, range_min=.12, range_max=10., range_threshold=None,
                 frame_offset=(-.064, 0.), frame_yaw=0., max_scans=MAX_SCANS):
        self._lock = RLock()
        self._handle = 0
        if (not isinstance(shape, (tuple, list)) or len(shape) != 2
                or any(type(v) is not int or v <= 0 for v in shape)
                or math.prod(shape) > MAX_CELLS):
            raise ValueError("bounded positive integer (height, width) required")
        if not isinstance(epoch, str) or not epoch:
            raise ValueError("explicit nonempty robot/epoch identity required")
        if type(max_scans) is not int or not 1 <= max_scans <= MAX_SCANS:
            raise ValueError("finite scan budget required")
        self.shape, self.epoch = tuple(shape), epoch
        self.resolution = _real(resolution)
        self.origin = tuple(_vector(origin, 2))
        self.range_min, self.range_max = _real(range_min), _real(range_max)
        threshold = self.range_max if range_threshold is None else _real(range_threshold)
        if not (self.resolution > 0 and 0 < self.range_min < self.range_max
                and self.range_min < threshold <= self.range_max):
            raise ValueError("positive resolution and ordered sensor limits required")
        raw = np.asarray(angles)
        if raw.ndim != 1 or not 1 <= raw.size <= MAX_BEAMS:
            raise ValueError("bounded uniform-angle scan required")
        self._angles = _vector(angles, raw.size)
        step = (self._angles[-1] - self._angles[0]) / (raw.size - 1) if raw.size > 1 else .1
        if not math.isfinite(step) or step <= 0:
            raise ValueError("positive finite angular increment required")
        expected = self._angles[0] + np.arange(raw.size) * step
        tolerance = 4 * np.spacing(np.maximum(1., np.abs(expected)))
        if np.any(np.abs(self._angles - expected) > tolerance):
            raise ValueError("nonuniform angles unsupported; no resampling")
        offset, yaw = _vector(frame_offset, 2), _real(frame_yaw)
        self.max_scans, self.version = max_scans, 0
        self._last_id = self._last_clock = self._last_payload = None
        self.last_status = None
        self._lib, self.library_path = _library(library_path)
        self._handle = self._lib.mr3_karto_create(shape[1], shape[0], self.resolution,
            *self.origin, raw.size, self._angles[0], step, self.range_min, self.range_max,
            threshold, *offset, yaw, max_scans)
        if not self._handle:
            raise RuntimeError(self._error())

    def _error(self):
        return (self._lib.mr3_karto_error() or b"native adapter failure").decode("utf-8", "replace")

    def _open(self):
        if not self._handle:
            raise RuntimeError("Karto mapper is closed")

    @_serialized
    def close(self):
        if self._handle:
            if self._lib.mr3_karto_destroy(self._handle) != 0:
                raise RuntimeError(self._error())
            self._handle = 0

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        try:
            self.close()
        except RuntimeError:
            pass  # Explicit close/context exit reports SDK cleanup failures.

    @_serialized
    def integrate(self, scan_id, source_clock_ns, estimated_body_pose, angles, ranges):
        self._open()
        if any(type(v) is not int or v < 0 for v in (scan_id, source_clock_ns)):
            raise ValueError("nonnegative integer source ID/clock required")
        pose = _vector(estimated_body_pose, 3)
        angles = _vector(angles, len(self._angles))
        ranges = _vector(ranges, len(self._angles))
        if not np.array_equal(angles, self._angles):
            raise ValueError("scan angles differ from the configured sensor")
        if np.any(ranges < self.range_min) or np.any(ranges > self.range_max):
            raise ValueError("ranges outside declared sensor limits")
        payload = (source_clock_ns, pose.tobytes(), angles.tobytes(), ranges.tobytes())
        if self._last_id is not None:
            if scan_id < self._last_id:
                raise ValueError("out-of-order source scan ID")
            if scan_id == self._last_id:
                if payload != self._last_payload:
                    raise ValueError("source scan ID reused with changed payload")
                return False
            if source_clock_ns <= self._last_clock:
                raise ValueError("new scans require increasing source clocks")
        if self.version >= self.max_scans:
            raise ValueError("finite scan budget exhausted")
        status = self._lib.mr3_karto_add_scan(self._handle,
            ranges.ctypes.data_as(C.POINTER(C.c_double)), len(ranges), *pose)
        if status < 0:
            message = self._error()
            # The C boundary may have failed after mutation. Never retry it.
            self.close()
            raise RuntimeError(message)
        if status not in (0, 1):
            self.close()
            raise RuntimeError("unexpected native AddScan status")
        self._last_id, self._last_clock, self._last_payload = scan_id, source_clock_ns, payload
        self.version += 1
        self.last_status = "partial_out_of_map" if status else "complete"
        return True

    @_serialized
    def snapshot(self):
        self._open()
        passes, hits = (np.empty(self.shape, dtype=np.uint32) for _ in range(2))
        grid = np.empty(self.shape, dtype=np.int8)
        code = self._lib.mr3_karto_export(self._handle,
            passes.ctypes.data_as(C.POINTER(C.c_uint32)),
            hits.ctypes.data_as(C.POINTER(C.c_uint32)),
            grid.ctypes.data_as(C.POINTER(C.c_int8)), grid.size)
        if code != 0:
            raise RuntimeError(self._error())
        return {"grid": grid, "passes": passes, "hits": hits,
            "model": MODEL, "epoch": self.epoch, "resolution": self.resolution,
            "origin": self.origin, "source_scan_id": self._last_id,
            "source_clock_ns": self._last_clock, "version": self.version,
            "status": self.last_status}

    def grid(self):
        return self.snapshot()["grid"]

    @_serialized
    def world_to_grid(self, x, y):
        """Expose the actual SDK conversion for phase verification only."""
        self._open()
        ix, iy = C.c_int32(), C.c_int32()
        code = self._lib.mr3_karto_world_to_grid(self._handle, _real(x), _real(y),
                                              C.byref(ix), C.byref(iy))
        if code != 0:
            raise ValueError(self._error())
        return ix.value, iy.value
