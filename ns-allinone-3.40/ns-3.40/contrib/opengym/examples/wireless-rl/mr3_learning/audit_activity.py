"""Independently replay received odometry/acceptance features from saved inputs.

No production tracker, ROS, truth, reward or policy module is imported. Local
odom chords are an observation estimate; this audit never changes task gates.
"""

import gzip
import hashlib
import json
import math
from pathlib import Path


ROBOTS = ("tb1", "tb2", "tb3")
SCHEMA = "mr3-received-activity-v1"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _ns(value):
    _require(not isinstance(value, bool) and isinstance(value, (int, float))
             and math.isfinite(value), "nonfinite/invalid activity time")
    return round(value * 1000000000)


def _load(path):
    path = path if path.exists() else Path(str(path) + ".gz")
    raw = path.read_bytes()
    return gzip.decompress(raw) if path.suffix == ".gz" else raw


def _decode(robot):
    """Read untouched received odometry, independently of tracker audit rows."""
    odom = robot["odometry"]
    stamp = odom["header"]["stamp"]
    _require(type(stamp["sec"]) is int and type(stamp["nanosec"]) is int
             and 0 <= stamp["nanosec"] < 1000000000, "bad raw odom stamp")
    clock = stamp["sec"] * 1000000000 + stamp["nanosec"]
    _require(clock > 0 and clock == _ns(robot["odom_source_stamp"]), "raw odom stamp mismatch")
    point = odom["pose"]["pose"]["position"]
    for value in (point["x"], point["y"]):
        _require(not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value), "invalid raw odom xy")
    _require(bool(odom["header"]["frame_id"]) and bool(odom["child_frame_id"]),
             "missing raw odom frame")
    return clock, {
        "source_stamp": clock / 1e9, "x": float(point["x"]), "y": float(point["y"]),
        "frame": odom["header"]["frame_id"], "child_frame": odom["child_frame_id"],
    }


def _same(actual, expected, label):
    _require(set(actual) == set(expected), label + ": activity fields differ")
    for key, value in expected.items():
        if key == "estimated_path_m" and value is not None:
            observed = actual[key]
            _require(not isinstance(observed, bool) and isinstance(observed, (float, int))
                     and math.isfinite(observed)
                     and math.isclose(observed, value, rel_tol=1e-12, abs_tol=1e-10),
                     label + ": local-odom path mismatch")
        else:
            same_type = (type(actual[key]) is type(value) if type(value) in (bool, int) else True)
            _require(same_type and actual[key] == value, label + ": mismatched " + key)


def _activity_history(records, epoch, started_at):
    sources = {}
    for index, row in enumerate(records):
        if row["kind"] == "state_update":
            sequence = row["payload"]["sequence"]
            _require(type(sequence) is int and sequence not in sources,
                     "duplicate/invalid received state sequence")
            sources[sequence] = (index, row)
    saved = {name: {"path": 0., "count": 0, "complete": True, "last": None}
             for name in ROBOTS}
    history, previous = {}, -1
    for index, row in enumerate(records):
        if row["kind"] != "activity_update":
            continue
        payload = row["payload"]
        sequence = payload["state_sequence"]
        _require(payload["epoch"] == epoch and type(sequence) is int and sequence > previous
                 and sequence in sources, "activity epoch/sequence has no received input")
        previous = sequence
        source_index, source = sources[sequence]
        _require(source_index < index, "activity recorded before its raw received input")
        _require(_ns(source["stamp"]) <= _ns(row["stamp"]), "activity used future delivery")
        robots = source["payload"]["robots"]
        _require(len(robots) == 3 and {r["name"] for r in robots} == set(ROBOTS),
                 "raw activity source robot set")
        observed = {r["name"]: r for r in payload["robots"]}
        _require(len(payload["robots"]) == 3 and set(observed) == set(ROBOTS),
                 "activity receipt robot set")
        expected = {}
        for robot in robots:
            name = robot["name"]
            item, sample, status = saved[name], None, "invalid_odometry"
            try:
                _require(robot["epoch"] == epoch and robot["valid"] is True, "raw identity")
                stamp, sample = _decode(robot)
                old = item["last"]
                if stamp < _ns(started_at):
                    status = "before_release"
                elif stamp > _ns(row["stamp"]):
                    raise ValueError("future odom")
                elif old is not None and stamp < _ns(old["source_stamp"]):
                    status = "older_source_ignored"
                elif old is not None and stamp == _ns(old["source_stamp"]):
                    status = "duplicate_source_ignored" if sample == old else "source_conflict"
                    item["complete"] &= sample == old
                else:
                    status = "anchor"
                    if old is not None:
                        if (sample["frame"], sample["child_frame"]) != (
                                old["frame"], old["child_frame"]):
                            item["complete"] = False
                            status = "frame_changed_anchor"
                        else:
                            length = item["path"] + math.hypot(sample["x"] - old["x"],
                                                               sample["y"] - old["y"])
                            _require(math.isfinite(length), "raw odom path overflow")
                            item["path"] = length
                            item["complete"] &= stamp - _ns(old["source_stamp"]) <= 500000000
                            status = "accumulated"
                    item["last"] = sample
                    item["count"] += 1
            except (ValueError, TypeError, KeyError, OverflowError):
                item["complete"] = False
            last = item["last"]
            expected[name] = {
                "schema": SCHEMA, "epoch": epoch, "started_at": started_at,
                "state_sequence": sequence,
                "estimated_path_m": None if last is None else item["path"],
                "path_observation_complete": bool(last is not None and item["complete"]),
                "sample_count": item["count"],
                "last_odom_source_stamp": None if last is None else last["source_stamp"],
            }
            _same(observed[name], {"name": name, "status": status, "sample": sample,
                                   **expected[name]}, name + ": activity receipt")
        history[sequence] = expected
    _require(bool(history), "no received activity updates")
    release_line = next(i for i, r in enumerate(records) if r["kind"] == "task_start")
    _require(all(sequence in history for sequence, (index, _) in sources.items()
                 if index > release_line), "received task state omitted from activity history")
    return history


def _acceptance_history(records, epoch):
    owners = dict.fromkeys(ROBOTS)
    seen = {name: set() for name in ROBOTS}
    counts = {name: {} for name in ROBOTS}
    boundaries = {}
    for row in records:
        event = row["payload"]
        if row["kind"] == "protocol":
            name = event["robot"]
            if event["type"] == "send_goal":
                _require(event["epoch"] == epoch and owners[name] is None,
                         "new goal while prior owner remains")
                owners[name] = event["goal_id"]
            elif event["type"] == "protocol_terminal" and owners[name] == event["goal_id"]:
                owners[name] = None
        elif row["kind"] == "delivery" and event.get("stream") == "receipt":
            name, sequence = event["source"], event["sequence"]
            _require(event["epoch"] == epoch and type(sequence) is int
                     and (not counts[name] or sequence > max(counts[name])),
                     "receipt epoch/sequence regressed")
            receipt = event["payload"]
            if owners[name] == receipt["goal_id"]:
                if receipt["type"] == "accept":
                    if receipt["value"] is True:
                        seen[name].add(receipt["goal_id"])
                    else:
                        owners[name] = None
                elif receipt["type"] == "result":
                    owners[name] = None
            counts[name][sequence] = len(seen[name])
        elif row["kind"] == "activity_snapshot_bound":
            sequence = event["observation_sequence"]
            _require(type(sequence) is int and sequence not in boundaries,
                     "duplicate activity snapshot freeze boundary")
            boundaries[sequence] = {
                "state_sequence": event["state_sequence"], "stamp": row["stamp"],
                "counts": {name: len(goals) for name, goals in seen.items()},
            }
    return counts, boundaries


def audit_episode(directory):
    """Check raw received inputs, tracker receipts and saved actor snapshots."""
    directory = Path(directory)
    metadata = json.loads(_load(directory / "metadata.json"))
    epoch = metadata["epoch"]
    adapter = _load(directory / "adapter.jsonl")
    transitions = _load(directory / "transitions.jsonl")
    records = [json.loads(line) for line in adapter.splitlines()]
    releases = [r["payload"]["start_sim_time_sec"] for r in records if r["kind"] == "task_start"]
    _require(len(releases) == 1 and all(r["epoch"] == epoch for r in records),
             "activity requires one released epoch")
    history = _activity_history(records, epoch, releases[0])
    acceptances, boundaries = _acceptance_history(records, epoch)
    snapshots = set()
    for row in (json.loads(line) for line in transitions.splitlines()):
        snapshot = row["snapshot"]
        _require(snapshot["schema"] == "mr3-observation-v3" and snapshot["epoch"] == epoch,
                 "wrong actor activity schema/epoch")
        raw = json.dumps({k: v for k, v in snapshot.items() if k != "digest"},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        _require(hashlib.sha256(raw).hexdigest() == snapshot["digest"], "activity snapshot digest")
        boundary = boundaries.get(snapshot["sequence"])
        _require(boundary is not None and boundary["stamp"] == snapshot["source_stamp"],
                 "snapshot activity has no actual encoding freeze boundary")
        _require(len(snapshot["robots"]) == 3
                 and {r["name"] for r in snapshot["robots"]} == set(ROBOTS),
                 "activity snapshot robots")
        for robot in snapshot["robots"]:
            name, activity = robot["name"], robot["activity"]
            sequence = activity["state_sequence"]
            _require(robot["epoch"] == epoch and sequence in history
                     and sequence == row["info"]["watermarks"]["state_sequence"]
                     and sequence == boundary["state_sequence"],
                     "snapshot activity has no matching received-history boundary")
            _same(activity, history[sequence][name], name + ": saved snapshot")
            receipt_sequence = robot["navigation"]["receipt_sequence"]
            count = 0 if receipt_sequence is None else acceptances[name].get(receipt_sequence)
            observed_count = robot["navigation"]["accepted_goal_count"]
            _require(count is not None and type(observed_count) is int and observed_count == count
                     and count == boundary["counts"][name],
                     name + ": accepted goals differ from delivered unique receipts")
        snapshots.add(snapshot["digest"])
    _require(bool(snapshots), "no saved actor snapshots for activity audit")
    return {
        "schema": "mr3-received-activity-audit-v1", "passed": True, "epoch": epoch,
        "activity_updates": len(history), "unique_snapshots": len(snapshots),
        "final_received_acceptance_counts": {
            n: max(c.values(), default=0) for n, c in acceptances.items()},
        "adapter_sha256": hashlib.sha256(adapter).hexdigest(),
        "transitions_sha256": hashlib.sha256(transitions).hexdigest(),
        "path_numeric_comparison": "relative 1e-12 / absolute 1e-10 metre arithmetic tolerance",
        "scope": ("raw delivered local odom/unique acceptance observations; "
                  "no truth/task-success assertion"),
    }
