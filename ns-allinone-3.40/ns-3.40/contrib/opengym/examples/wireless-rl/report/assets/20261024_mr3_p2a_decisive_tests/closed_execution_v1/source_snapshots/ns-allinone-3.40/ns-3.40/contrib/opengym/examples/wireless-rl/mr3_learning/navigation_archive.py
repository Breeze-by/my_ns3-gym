"""Independent NumPy reconstruction of archived owner-authoritative navigation."""

import copy
import math

import numpy as np


COMPOSITION_VERSION = "mr3-own-known-shared-unknown-v1"


def _validate(payload):
    info = payload["info"]
    if payload["header"]["frame_id"].lstrip("/") != "map":
        raise ValueError("navigation archive map frame mismatch")
    if (type(info["width"]) is not int or type(info["height"]) is not int
            or info["width"] <= 0 or info["height"] <= 0
            or not math.isfinite(info["resolution"]) or info["resolution"] <= 0):
        raise ValueError("navigation archive invalid native geometry")
    position, quaternion = info["origin"]["position"], info["origin"]["orientation"]
    if (any(not math.isfinite(position[axis]) for axis in ("x", "y"))
            or any(not math.isfinite(quaternion[axis]) or abs(quaternion[axis]) > 1e-6
                   for axis in ("x", "y", "z"))
            or not math.isclose(abs(quaternion["w"]), 1., abs_tol=1e-6)):
        raise ValueError("navigation archive map requires registration")
    values = np.asarray(payload["data"])
    if (not np.issubdtype(values.dtype, np.integer)
            or values.size != info["width"] * info["height"]
            or np.any((values < -1) | (values > 100))):
        raise ValueError("navigation archive invalid native occupancy cells")
    return values.astype(np.int16).reshape(info["height"], info["width"])


def _project(payload, cells, left, bottom, resolution):
    """Project by output-cell world intervals, independently of ROS merger code."""
    info = payload["info"]
    first_x = np.floor((left - info["origin"]["position"]["x"]) / resolution + 1e-9).astype(int)
    last_x = np.ceil((left + resolution - info["origin"]["position"]["x"])
                     / resolution - 1e-9).astype(int) - 1
    first_y = np.floor((bottom - info["origin"]["position"]["y"]) / resolution + 1e-9).astype(int)
    last_y = np.ceil((bottom + resolution - info["origin"]["position"]["y"])
                     / resolution - 1e-9).astype(int) - 1
    shape = (len(bottom), len(left))
    maximum = np.full(shape, -1, dtype=np.int16)
    fully_free = np.ones(shape, dtype=bool)
    for rows in (first_y, last_y):
        for columns in (first_x, last_x):
            rr, cc = np.broadcast_arrays(rows[:, None], columns[None, :])
            inside = ((rr >= 0) & (rr < info["height"])
                      & (cc >= 0) & (cc < info["width"]))
            sample = np.full(shape, -1, dtype=np.int16)
            sample[inside] = cells[rr[inside], cc[inside]]
            fully_free &= inside & (sample >= 0) & (sample < 50)
            np.maximum(maximum, sample, out=maximum)
    maximum[(maximum < 50) & ~fully_free] = -1
    return maximum


def reconstruct_navigation_payload(own, shared):
    """Rebuild exact output geometry/header/cells without importing production ROS."""
    own_cells, shared_cells = _validate(own), _validate(shared)
    info = own["info"]
    resolution = info["resolution"]
    if not math.isclose(shared["info"]["resolution"], resolution):
        raise ValueError("navigation archive resolution mismatch")
    xmin = min(payload["info"]["origin"]["position"]["x"] for payload in (own, shared))
    ymin = min(payload["info"]["origin"]["position"]["y"] for payload in (own, shared))
    xmax = max(payload["info"]["origin"]["position"]["x"]
               + payload["info"]["width"] * resolution for payload in (own, shared))
    ymax = max(payload["info"]["origin"]["position"]["y"]
               + payload["info"]["height"] * resolution for payload in (own, shared))
    width = math.ceil((xmax - xmin) / resolution - 1e-9)
    height = math.ceil((ymax - ymin) / resolution - 1e-9)
    left, bottom = xmin + np.arange(width) * resolution, ymin + np.arange(height) * resolution
    own_projected = _project(own, own_cells, left, bottom, resolution)
    shared_projected = _project(shared, shared_cells, left, bottom, resolution)
    navigation = np.where(own_projected >= 0, own_projected, shared_projected)
    latest = max((own, shared), key=lambda payload: (
        payload["header"]["stamp"]["sec"] * 1_000_000_000
        + payload["header"]["stamp"]["nanosec"]))
    origin = copy.deepcopy(info["origin"])
    origin["position"].update(x=xmin, y=ymin)
    return {
        "header": {"frame_id": "map", "stamp": copy.deepcopy(latest["header"]["stamp"])},
        "info": {"map_load_time": copy.deepcopy(latest["info"]["map_load_time"]),
                 "resolution": resolution, "width": width, "height": height, "origin": origin},
        "data": navigation.ravel().tolist(),
    }
