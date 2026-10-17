"""Fixed learner tensor schema for received-only ``mr3-observation-v3``.

No ROS/scipy imports, truth map, native cell indices, reward state, or policy
choice enter these tensors. Images retain overlapping binary occupancy/free/
unknown flags (not 0..255 intensities). Scalar features use fixed physical
scales. Values outside the reference scale are retained, with explicit range
flags; nothing is clipped. Missing numeric values become zero with valid=0.
NaN/Inf, future sensor times, malformed masks, and corrupt rasters are errors.

ROBOT_FIELDS, CANDIDATE_FIELDS, HISTORY_FIELDS and TASK_FIELDS enumerate every
column in order. Schema changes require a new TENSOR_SCHEMA and model contract.
IDs, epoch, snapshot/candidate hashes and versions remain replay metadata.
"""

import base64
import hashlib
import json
import math
import zlib

from gymnasium import spaces
import numpy as np


TENSOR_SCHEMA = "mr3-learning-tensors-v2"
SNAPSHOT_SCHEMA = "mr3-observation-v3"
ROBOTS = ("tb1", "tb2", "tb3")
PHASES = ("idle", "accepting", "active", "canceling", "unknown", "failed")
ROBOT_SCALARS = (
    ("x", 16.0), ("y", 16.0), ("sin_yaw", 1.0), ("cos_yaw", 1.0),
    ("v", 1.0), ("w", 2.0), ("source_age_sec", 300.0),
    ("received_age_sec", 300.0), ("path_map_source_age_sec", 300.0),
    ("tf_source_age_sec", 300.0), ("path_map_received_age_sec", 300.0),
    ("goal_x", 16.0), ("goal_y", 16.0), ("goal_distance_m", 32.0),
    ("commitment_remaining_sec", 5.0), ("goal_age_sec", 300.0),
    ("acceptance_age_sec", 300.0), ("lease_remaining_sec", 2.0),
    ("nav_source_age_sec", 300.0), ("nav_received_age_sec", 300.0),
    ("progress_m", 32.0),
    ("received_estimated_path_m", 32.0), ("received_accepted_goal_count", 64.0),
)
ROBOT_FIELDS = tuple(column for name, _ in ROBOT_SCALARS
                     for column in (name, name + "_valid")) + tuple(
    "phase_" + phase for phase in PHASES
) + (
    "phase_valid", "state_valid", "state_fresh", "state_missing", "goal_owned",
    "cancel_requested", "receipt_missing", "nav_source_metadata_missing",
    "path_map_available", "last_failure_present", "goal_present",
    "position_out_of_bounds", "motion_out_of_bounds", "age_out_of_bounds",
    "goal_out_of_bounds", "path_map_missing",
    "received_path_complete", "estimated_activity_ready", "activity_out_of_bounds",
)
CANDIDATE_VALUES = ("x", "y", "clearance_m", "frontier_count",
                    "path_tb1_m", "path_tb2_m", "path_tb3_m")
CANDIDATE_SCALES = (16.0, 16.0, 1.0, 100.0, 32.0, 32.0, 32.0)
CANDIDATE_FIELDS = CANDIDATE_VALUES + tuple(
    name + "_valid" for name in CANDIDATE_VALUES
) + ("candidate_valid", "out_of_bounds")
HISTORY_FIELDS = ("x_over_16m", "y_over_16m", "source_age_over_300s", "valid")
TASK_FIELDS = (
    "elapsed_over_300s", "elapsed_valid", "remaining_over_300s", "remaining_valid",
    "period_over_1s", "period_valid", "map_source_age_over_300s", "map_source_age_valid",
    "map_received_age_over_300s", "map_received_age_valid", "map_missing", "out_of_bounds",
)


def observation_space():
    return spaces.Dict({
        "global_map": spaces.Box(0, 1, shape=(3, 128, 128), dtype=np.uint8),
        "local_maps": spaces.Box(0, 1, shape=(3, 3, 64, 64), dtype=np.uint8),
        "robots": spaces.Box(-np.inf, np.inf, shape=(3, len(ROBOT_FIELDS)), dtype=np.float32),
        "candidates": spaces.Box(-np.inf, np.inf, shape=(8, 16), dtype=np.float32),
        "history": spaces.Box(-np.inf, np.inf, shape=(3, 16, 4), dtype=np.float32),
        "task": spaces.Box(-np.inf, np.inf, shape=(12,), dtype=np.float32),
        "action_mask": spaces.MultiBinary(1000),
    })


def _number(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{label} must be numeric or explicitly missing")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _bit(value, label):
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be an explicit boolean")
    return float(value)


def _pair(value, scale, label):
    value = _number(value, label)
    return (0.0, 0.0) if value is None else (value / scale, 1.0)


def _age(now, stamp, label):
    stamp = _number(stamp, label)
    if stamp is None:
        return None
    if stamp > now + 1e-6:
        raise ValueError(f"{label} refers to a future source")
    return max(0.0, now - stamp)


def _record_age(record, now, kind, label):
    """Compute age at the saved snapshot time and verify its declared metadata."""
    stamp_key = "source_stamp" if kind == "source" else "received_stamp"
    age_key = "source_age_sec" if kind == "source" else "received_age_sec"
    expected = _age(now, record.get(stamp_key), label + "." + stamp_key)
    declared = _number(record.get(age_key), label + "." + age_key)
    if ((expected is None) != (declared is None)
            or expected is not None and not math.isclose(expected, declared, abs_tol=1e-6)):
        raise ValueError(f"{label} age and timestamp metadata disagree")
    return expected


def _decode_raster(raster, shape):
    if (raster.get("encoding") != "base64-zlib-u8-chw"
            or raster.get("shape") != list(shape)
            or raster.get("channels") != ["occupied", "free", "unknown"]):
        raise ValueError("raster shape, encoding, or channels mismatch")
    expected = math.prod(shape)
    data = raster["data"]
    if not isinstance(data, str) or len(data) > 2 * expected + 1024:
        raise ValueError("raster payload exceeds its declared shape")
    try:
        compressed = base64.b64decode(data, validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, expected + 1)
    except (ValueError, zlib.error) as error:
        raise ValueError("invalid raster payload") from error
    if (len(raw) != expected or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError("raster byte count or compressed boundary mismatch")
    array = np.frombuffer(raw, dtype=np.uint8).reshape(shape).copy()
    if np.any(array > 1):
        raise ValueError("map channels must retain their binary flag semantics")
    return array


def _history(robot, now):
    history = robot.get("history", [])
    if not isinstance(history, list) or len(history) > 16:
        raise ValueError("history must contain at most 16 delivered points")
    output = np.zeros((16, 4), dtype=np.float32)
    for index, point in enumerate(history):
        values = (_number(point.get("x"), "history.x"),
                  _number(point.get("y"), "history.y"),
                  _age(now, point.get("source_stamp"), "history.source_stamp"))
        if all(value is not None for value in values):
            output[index] = (values[0] / 16.0, values[1] / 16.0, values[2] / 300.0, 1.0)
    return output


def _robot(robot, now, path_map):
    nav = robot["navigation"]
    yaw = _number(robot.get("yaw"), "robot.yaw")
    lease_until = _number(nav.get("lease_until"), "navigation.lease_until")
    values = {name: robot.get(name) for name, _ in ROBOT_SCALARS}
    activity = robot.get("activity")
    if activity is not None:
        if (not isinstance(activity, dict) or activity.get("schema") != "mr3-received-activity-v1"
                or activity.get("epoch") != robot.get("epoch")):
            raise ValueError("cross-epoch or unknown received activity")
        if (type(activity.get("state_sequence")) is not int or activity["state_sequence"] < 0
                or type(activity.get("sample_count")) is not int or activity["sample_count"] < 0):
            raise ValueError("received activity source sequence/sample count is invalid")
        started = _number(activity.get("started_at"), "activity.started_at")
        source = _number(activity.get("last_odom_source_stamp"), "activity.odom_source_stamp")
        if started is None or started > now or source is not None and not started <= source <= now:
            raise ValueError("activity source is outside the released task interval")
    path = _number(None if activity is None else activity.get("estimated_path_m"), "activity.path")
    count = _number(nav.get("accepted_goal_count"), "navigation.accepted_goal_count")
    if (path is not None and path < 0
            or count is not None and (count < 0 or not count.is_integer())):
        raise ValueError("received activity counters must be nonnegative")
    complete = (False if activity is None else bool(_bit(
        activity.get("path_observation_complete"), "activity.path_observation_complete")))
    if complete and path is None:
        raise ValueError("complete activity requires an observed path")
    values["received_estimated_path_m"] = path
    values["received_accepted_goal_count"] = count
    values.update({
        "sin_yaw": None if yaw is None else math.sin(yaw),
        "cos_yaw": None if yaw is None else math.cos(yaw),
        "source_age_sec": _record_age(robot, now, "source", "robot"),
        "received_age_sec": _record_age(robot, now, "received", "robot"),
        "path_map_source_age_sec": _record_age(path_map or {}, now, "source", "path_map"),
        "tf_source_age_sec": _age(now, robot.get("tf_source_stamp"), "tf_source_stamp"),
        "path_map_received_age_sec": _record_age(path_map or {}, now, "received", "path_map"),
        "lease_remaining_sec": None if lease_until is None else lease_until - now,
        "nav_source_age_sec": _record_age(nav, now, "source", "navigation"),
        "nav_received_age_sec": _record_age(nav, now, "received", "navigation"),
    })
    for name in ("goal_x", "goal_y", "goal_distance_m", "commitment_remaining_sec",
                 "goal_age_sec", "acceptance_age_sec", "progress_m"):
        values[name] = nav.get(name)
    pairs = [_pair(values[name], scale, name) for name, scale in ROBOT_SCALARS]
    output = [value for pair in pairs for value in pair]
    phase = nav.get("phase")
    output.extend(float(phase == candidate) for candidate in PHASES)
    output.append(float(phase in PHASES))
    for container, name in ((robot, "valid"), (robot, "fresh"), (robot, "missing"),
                            (nav, "owned"), (nav, "cancel_requested"),
                            (nav, "receipt_missing"), (nav, "source_metadata_missing")):
        output.append(_bit(container.get(name), name))
    path_missing = path_map is None or path_map.get("missing") is True
    output.extend((float(not path_missing), float(nav.get("last_failure") is not None),
                   float(nav.get("goal_id") is not None)))
    scaled = {name: pair[0] for (name, _), pair in zip(ROBOT_SCALARS, pairs)}
    output.extend(float(any(abs(scaled[name]) > 1.0 for name in group)) for group in (
        ("x", "y"), ("v", "w"),
        tuple(name for name in scaled if "age" in name), ("goal_x", "goal_y"),
    ))
    output.append(float(path_missing))
    output.extend((float(complete), float(complete and path is not None and path >= 1.
                                          and count is not None and count >= 1.),
                   float(path is not None and path > 32. or count is not None and count > 64.)))
    return output


def _candidate(candidate, index):
    if candidate.get("index") != index:
        raise ValueError("candidate order must preserve the saved action meaning")
    distances = candidate.get("path_distances_m")
    reachable = candidate.get("reachable")
    if (not isinstance(distances, list) or len(distances) != 3
            or not isinstance(reachable, list) or len(reachable) != 3):
        raise ValueError("candidate requires three received-state path entries")
    values = [candidate.get(name) for name in CANDIDATE_VALUES[:4]] + distances
    pairs = [_pair(value, scale, name) for value, scale, name
             in zip(values, CANDIDATE_SCALES, CANDIDATE_VALUES)]
    if any(pair[1] and pair[0] < 0 for pair in pairs[2:]):
        raise ValueError("clearance, frontier count and path distances must be nonnegative")
    for path, available in zip(pairs[4:], reachable):
        if _bit(available, "candidate.reachable") != path[1]:
            raise ValueError("candidate reachability and path metadata disagree")
    valid = _bit(candidate.get("valid"), "candidate.valid")
    if valid and not all(pair[1] for pair in pairs[:4]):
        raise ValueError("valid candidate is missing its geometry")
    scaled = [pair[0] for pair in pairs]
    return scaled + [pair[1] for pair in pairs] + [valid, float(any(abs(v) > 1 for v in scaled))]


def encode_snapshot(snapshot):
    """Validate and detach one immutable policy snapshot into fixed tensors."""
    if snapshot.get("schema") != SNAPSHOT_SCHEMA or snapshot.get("robot_order") != list(ROBOTS):
        raise ValueError("unsupported snapshot contract")
    encoded = json.dumps({key: value for key, value in snapshot.items() if key != "digest"},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest() != snapshot.get("digest"):
        raise ValueError("snapshot digest mismatch")
    robots = snapshot["robots"]
    if len(robots) != 3 or tuple(robot.get("name") for robot in robots) != ROBOTS:
        raise ValueError("robot order must remain tb1/tb2/tb3")
    epoch = snapshot.get("epoch")
    if not isinstance(epoch, str) or not epoch:
        raise ValueError("snapshot requires an episode epoch")
    if any(robot.get("epoch") != epoch for robot in robots):
        raise ValueError("cross-epoch robot state")
    if type(snapshot.get("sequence")) is not int or snapshot["sequence"] < 1:
        raise ValueError("snapshot sequence must be a positive integer")
    for metadata in snapshot.get("path_maps", {}).values():
        if not metadata.get("missing", True) and metadata.get("epoch") != epoch:
            raise ValueError("cross-epoch received path map")
    now = _number(snapshot.get("source_stamp"), "snapshot.source_stamp")
    if now is None or now < 0:
        raise ValueError("snapshot needs a nonnegative simulation timestamp")
    local_rasters = snapshot["maps"]["locals"]
    if len(local_rasters) != 3 or tuple(r.get("name") for r in local_rasters) != ROBOTS:
        raise ValueError("local raster order mismatch")
    if len(snapshot["candidates"]) != 8:
        raise ValueError("the fixed action contract requires eight candidate slots")
    mask = snapshot["joint_action_mask"]
    if (len(mask) != 1000 or any(type(value) is not bool for value in mask) or not any(mask)):
        raise ValueError("joint mask must contain 1000 booleans and a legal action")
    map_info = snapshot["map"]
    task_pairs = [_pair(value, scale, name) for value, scale, name in (
        (snapshot.get("task_elapsed_sec"), 300.0, "elapsed"),
        (snapshot.get("task_remaining_sec"), 300.0, "remaining"),
        (snapshot.get("policy_period_sec"), 1.0, "period"),
        (_record_age(map_info, now, "source", "map"), 300.0, "map_source_age"),
        (_record_age(map_info, now, "received", "map"), 300.0, "map_received_age"),
    )]
    task = [value for pair in task_pairs for value in pair] + [
        _bit(map_info.get("missing"), "map.missing"),
        float(any(abs(pair[0]) > 1 for pair in task_pairs)),
    ]
    observation = {
        "global_map": _decode_raster(snapshot["maps"]["global"], (3, 128, 128)),
        "local_maps": np.stack([_decode_raster(raster, (3, 64, 64))
                                for raster in local_rasters]),
        "robots": np.asarray([_robot(robot, now, snapshot.get("path_maps", {}).get(name))
                              for robot, name in zip(robots, ROBOTS)], dtype=np.float32),
        "candidates": np.asarray([_candidate(candidate, index) for index, candidate
                                  in enumerate(snapshot["candidates"])], dtype=np.float32),
        "history": np.stack([_history(robot, now) for robot in robots]),
        "task": np.asarray(task, dtype=np.float32),
        "action_mask": np.asarray(mask, dtype=np.int8),
    }
    if any(not np.all(np.isfinite(value)) for value in observation.values()):
        raise ValueError("feature scaling exceeded finite float32 range")
    return observation
