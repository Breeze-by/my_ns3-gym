"""Task-local activity estimates from delivered odometry, never evaluator truth.

The path is the sum of planar chords between increasing delivered local-odom
samples after task release. It is neither physical path length nor a success
gate. Missing samples may hide motion; TF/map corrections cannot add distance.
"""

import copy
import math

from .mr3_episode import timestamp_ns


ROBOTS = ("tb1", "tb2", "tb3")
SCHEMA = "mr3-received-activity-v1"
MAX_CONTIGUOUS_GAP_NS = 500000000


class ReceivedActivity:
    """Keep one epoch's observed odometry history, independent of ROS/reward."""

    def __init__(self, epoch):
        if not isinstance(epoch, str) or not epoch:
            raise ValueError("activity requires a nonempty epoch")
        self.epoch = epoch
        self.started_at = None
        self.last_sequence = -1
        self._robots = {
            name: {"estimated_path_m": 0., "sample_count": 0, "complete": True,
                   "last": None} for name in ROBOTS
        }

    def start(self, now):
        """Exclude warmup; the first post-release source sample is an anchor."""
        timestamp_ns(now)
        if self.started_at is not None:
            if timestamp_ns(self.started_at) != timestamp_ns(now):
                raise ValueError("activity task release is already bound")
            return
        self.started_at = float(now)

    def snapshot(self, robot):
        state = self._robots[robot]
        last = state["last"]
        return {
            "schema": SCHEMA, "epoch": self.epoch, "started_at": self.started_at,
            "state_sequence": self.last_sequence,
            "estimated_path_m": state["estimated_path_m"] if last is not None else None,
            "path_observation_complete": bool(last is not None and state["complete"]),
            "sample_count": state["sample_count"],
            "last_odom_source_stamp": None if last is None else last["source_stamp"],
        }

    def update(self, state, now):
        """Accept a new delivery sequence; duplicates/older samples add nothing."""
        if self.started_at is None:
            return None
        now_ns = timestamp_ns(now)
        sequence = state.get("sequence")
        if (state.get("epoch") != self.epoch or type(sequence) is not int
                or sequence <= self.last_sequence):
            return None
        robots = state.get("robots", [])
        if len(robots) != 3 or {r.get("name") for r in robots} != set(ROBOTS):
            raise ValueError("activity requires exactly three delivered robots")
        self.last_sequence = sequence
        results = []
        for robot in robots:
            name = robot["name"]
            saved = self._robots[name]
            sample = None
            status = "invalid_odometry"
            try:
                odom = robot["odometry"]
                stamp = odom["header"]["stamp"]
                sec, nanosec = stamp["sec"], stamp["nanosec"]
                if (robot.get("valid") is not True or robot.get("epoch") != self.epoch
                        or type(sec) is not int or type(nanosec) is not int
                        or not 0 <= nanosec < 1000000000):
                    raise ValueError("invalid delivered odometry identity/time")
                source_ns = sec * 1000000000 + nanosec
                if source_ns != timestamp_ns(robot["odom_source_stamp"]) or source_ns <= 0:
                    raise ValueError("odometry payload/source time mismatch")
                point = odom["pose"]["pose"]["position"]
                x, y = point["x"], point["y"]
                if any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in (x, y)):
                    raise ValueError("invalid delivered odometry position")
                sample = {
                    "source_stamp": source_ns / 1e9, "x": float(x), "y": float(y),
                    "frame": odom["header"]["frame_id"], "child_frame": odom["child_frame_id"],
                }
                if not sample["frame"] or not sample["child_frame"]:
                    raise ValueError("odometry frame is missing")
                last = saved["last"]
                if source_ns < timestamp_ns(self.started_at):
                    status = "before_release"
                elif source_ns > now_ns:
                    raise ValueError("future delivered odometry")
                elif last is not None and source_ns < timestamp_ns(last["source_stamp"]):
                    status = "older_source_ignored"
                elif last is not None and source_ns == timestamp_ns(last["source_stamp"]):
                    status = "duplicate_source_ignored" if sample == last else "source_conflict"
                    if sample != last:
                        saved["complete"] = False
                else:
                    if last is None:
                        status = "anchor"
                    elif (sample["frame"], sample["child_frame"]) != (
                            last["frame"], last["child_frame"]):
                        status = "frame_changed_anchor"
                        saved["complete"] = False
                    else:
                        total = saved["estimated_path_m"] + math.hypot(
                            sample["x"] - last["x"], sample["y"] - last["y"])
                        if not math.isfinite(total):
                            raise ValueError("odometry path estimate overflow")
                        saved["estimated_path_m"] = total
                        if source_ns - timestamp_ns(last["source_stamp"]) > MAX_CONTIGUOUS_GAP_NS:
                            saved["complete"] = False
                        status = "accumulated"
                    saved["last"] = sample
                    saved["sample_count"] += 1
            except (ValueError, TypeError, KeyError, OverflowError):
                saved["complete"] = False
            results.append({"name": name, "status": status, "sample": copy.deepcopy(sample),
                            **self.snapshot(name)})
        return {"epoch": self.epoch, "state_sequence": sequence, "robots": results}
