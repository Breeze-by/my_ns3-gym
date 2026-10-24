"""Read-only source-time angular sampler; stdlib only, no ROS/control/truth imports."""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROBOTS = ("tb1", "tb2", "tb3")
MAX_NORM = 1.2
MAX_SAMPLED_ACCEL = 7.0
MAX_GAP_NS = 100_000_000
SIGN_THRESHOLD = .1
MIN_SIGN_SAMPLES = 3


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def source_ns(message):
    stamp = message["header"]["stamp"]
    sec, nano = stamp["sec"], stamp["nanosec"]
    if type(sec) is not int or type(nano) is not int or sec < 0 or not 0 <= nano < 10**9:
        raise ValueError("invalid integer source stamp")
    return sec * 10**9 + nano


def angular_vector(message):
    angular = message["twist"]["twist"]["angular"]
    vector = [angular[axis] for axis in ("x", "y", "z")]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
        raise ValueError("nonfinite or nonnumeric angular vector")
    return vector


def robot_audit(rows, name, release, final):
    samples, errors, missing, duplicates = [], [], [], 0
    for line, row in rows:
        message = row["payload"]["message"]
        try:
            clock = source_ns(message)
            vector = angular_vector(message)
            frames = [message["header"]["frame_id"], message["child_frame_id"]]
            if any(type(frame) is not str or not frame for frame in frames):
                raise ValueError("empty/nonstring odometry frame")
            serialized = canonical(message)
        except (KeyError, TypeError, ValueError) as error:
            errors.append({"kind": "malformed_own_odom", "line": line, "error": str(error)})
            continue
        sample = {"source_ns": clock, "angular_xyz": vector,
                  "angular_norm": math.sqrt(sum(value * value for value in vector)),
                  "frames": frames, "line": line, "raw_own_odom": row}
        if samples:
            prior = samples[-1]
            if clock < prior["source_ns"]:
                errors.append({"kind": "source_rewind", "prior": prior, "current": sample})
                continue
            if clock == prior["source_ns"]:
                if serialized != canonical(prior["raw_own_odom"]["payload"]["message"]):
                    errors.append({"kind": "conflicting_duplicate_source",
                                   "prior": prior, "current": sample})
                else:
                    duplicates += 1
                continue
            if frames != prior["frames"]:
                errors.append({"kind": "odom_frame_changed", "prior": prior, "current": sample})
        samples.append(sample)
    task = [sample for sample in samples if release <= sample["source_ns"] <= final]
    if not any(sample["source_ns"] > release for sample in task):
        missing.append("real_postrelease_own_odom")
    if task:
        if task[0]["source_ns"] - release > MAX_GAP_NS:
            missing.append("fresh_release_boundary_sample")
        if final - task[-1]["source_ns"] > MAX_GAP_NS:
            missing.append("fresh_final_physics_boundary_sample")
    pairs = []
    for prior, current in zip(task, task[1:]):
        gap = current["source_ns"] - prior["source_ns"]
        pair = {"gap_ns": gap, "sampled_angular_accel_rad_s2":
                math.dist(prior["angular_xyz"], current["angular_xyz"]) / (gap / 1e9),
                "prior": prior, "current": current}
        pairs.append(pair)
        if gap > MAX_GAP_NS:
            missing.append("source_gap_over_100ms")
        if pair["sampled_angular_accel_rad_s2"] > MAX_SAMPLED_ACCEL:
            errors.append({"kind": "sampled_angular_acceleration_over_7", "pair": pair})
    if not pairs:
        missing.append("adjacent_postrelease_source_samples")
    for sample in task:
        if sample["angular_norm"] > MAX_NORM:
            errors.append({"kind": "angular_norm_over_1.2", "sample": sample})
    runs, active = [], None
    for sample in task:
        wz = sample["angular_xyz"][2]
        sign = 1 if wz >= SIGN_THRESHOLD else -1 if wz <= -SIGN_THRESHOLD else 0
        contiguous = (active is not None and sign == active["sign"] and
                      sample["source_ns"] - active["end_source_ns"] <= MAX_GAP_NS)
        if not sign:
            active = None
        elif contiguous:
            active["samples"] += 1
            active["end_source_ns"] = sample["source_ns"]
            active["end_line"] = sample["line"]
            active["min_abs_wz"] = min(active["min_abs_wz"], abs(wz))
            active["max_abs_wz"] = max(active["max_abs_wz"], abs(wz))
        else:
            active = {"sign": sign, "samples": 1, "start_source_ns": sample["source_ns"],
                      "end_source_ns": sample["source_ns"], "start_line": sample["line"],
                      "end_line": sample["line"], "min_abs_wz": abs(wz), "max_abs_wz": abs(wz)}
            runs.append(active)
    spans = [run for run in runs if run["samples"] >= MIN_SIGN_SAMPLES]
    if not spans:
        missing.append("three_fresh_consecutive_same_sign_samples_abs_wz_at_least_0.1")
    maximum_sample = max(task, key=lambda sample: sample["angular_norm"], default=None)
    maximum_pair = max(pairs, key=lambda pair: pair["sampled_angular_accel_rad_s2"], default=None)
    return {"robot": name, "bounds_passed": not errors and not any(
                reason != "three_fresh_consecutive_same_sign_samples_abs_wz_at_least_0.1"
                for reason in missing),
            "errors": errors, "missing": sorted(set(missing)),
            "raw_unique_samples": len(samples),
            "exact_duplicate_messages_deduplicated": duplicates,
            "postrelease_samples": len(task), "sign_spans": spans,
            "maximum_sign_run_samples": max((run["samples"] for run in runs), default=0),
            "max_angular_norm_rad_s": (None if maximum_sample is None else
                                       maximum_sample["angular_norm"]),
            "max_norm_original_sample": maximum_sample,
            "max_sampled_angular_accel_rad_s2": (
                None if maximum_pair is None else maximum_pair["sampled_angular_accel_rad_s2"]),
            "max_acceleration_original_adjacent_samples": maximum_pair,
            "max_source_gap_ns": max((pair["gap_ns"] for pair in pairs), default=None)}


def audit_records(metadata, transitions, physics, motion):
    epoch = metadata["epoch"]
    if not transitions or transitions[0]["kind"] != "reset":
        raise ValueError("missing original reset record")
    info = transitions[0]["info"]
    release = info["release_time_ns"]
    if info["epoch"] != epoch or type(release) is not int or release < 0:
        raise ValueError("release epoch/integer mismatch")
    if not physics:
        raise ValueError("missing final physics record")
    final = physics[-1]["end_time_ns"]
    if type(final) is not int or final < release:
        raise ValueError("final physics boundary invalid")
    if any(row["epoch"] != epoch for row in physics):
        raise ValueError("physics epoch mismatch")
    own = {name: [] for name in ROBOTS}
    for line, row in enumerate(motion, 1):
        if row["epoch"] != epoch:
            raise ValueError("motion log epoch mismatch")
        if row["kind"] == "own_odom":
            name = row["payload"]["robot"]
            if name not in ROBOTS:
                raise ValueError("unexpected own odometry robot")
            own[name].append((line, row))
    robots = {name: robot_audit(own[name], name, release, final) for name in ROBOTS}
    positive = [name for name, row in robots.items()
                if any(span["sign"] == 1 for span in row["sign_spans"])]
    negative = [name for name, row in robots.items()
                if any(span["sign"] == -1 for span in row["sign_spans"])]
    bidirectional = [name for name, row in robots.items()
                     if {span["sign"] for span in row["sign_spans"]} == {-1, 1}]
    missing = []
    if not positive:
        missing.append("positive_sign_span_across_three_robots")
    if not negative:
        missing.append("negative_sign_span_across_three_robots")
    if not bidirectional:
        missing.append("one_robot_with_sequential_opposite_sign_spans")
    covered = all(row["sign_spans"] for row in robots.values()) and not missing
    return {"schema": "mr3-independent-angular-interface-v1", "epoch": epoch,
            "release_time_ns": release, "final_physics_time_ns": final,
            "passed": covered and all(row["bounds_passed"] for row in robots.values()),
            "sampled_bounds_passed": all(row["bounds_passed"] for row in robots.values()),
            "stimulus_coverage_passed": covered, "missing": missing, "robots": robots,
            "positive_span_robots": positive, "negative_span_robots": negative,
            "sequential_opposite_sign_span_robots": bidirectional,
            "criteria": {"angular_norm_rad_s_max": MAX_NORM,
                         "sampled_vector_angular_accel_rad_s2_max": MAX_SAMPLED_ACCEL,
                         "maximum_source_gap_ns": MAX_GAP_NS,
                         "minimum_sign_abs_wz_rad_s": SIGN_THRESHOLD,
                         "minimum_sign_consecutive_fresh_samples": MIN_SIGN_SAMPLES,
                         "every_robot_requires_a_sign_span": True,
                         "at_least_one_robot_requires_sequential_opposite_sign_spans": True},
            "scope": ("Only raw local own_odom diagnostics in source time. Opposite sign spans "
                      "are stop/restart coverage, not peak-to-peak direct reversal or continuous "
                      "acceleration proof. No control/truth/production actor imports. Whole-body "
                      "linear/chord/strict-close and three-robot >0.05m activity gates are "
                      "independently required elsewhere.")}


def audit_episode(directory):
    inputs = {}

    def read(name, lines=False):
        path = directory / name
        if not path.exists():
            path = Path(str(path) + ".gz")
        raw = path.read_bytes()
        inputs[str(path)] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        data = gzip.decompress(raw) if path.suffix == ".gz" else raw
        if lines:
            if data and not data.endswith(b"\n"):
                raise ValueError("incomplete JSONL record: " + str(path))
            return [json.loads(line) for line in data.splitlines()]
        return json.loads(data)

    result = audit_records(read("metadata.json"), read("transitions.jsonl", True),
                           read("physics.jsonl", True), read("motion_safety.jsonl", True))
    return {**result, "directory": str(directory), "inputs": inputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; diagnostic failures cannot be overwritten")
    try:
        result = audit_episode(args.episode)
    except Exception as error:
        result = {"schema": "mr3-independent-angular-interface-v1", "passed": False,
                  "directory": str(args.episode), "error": repr(error)}
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
