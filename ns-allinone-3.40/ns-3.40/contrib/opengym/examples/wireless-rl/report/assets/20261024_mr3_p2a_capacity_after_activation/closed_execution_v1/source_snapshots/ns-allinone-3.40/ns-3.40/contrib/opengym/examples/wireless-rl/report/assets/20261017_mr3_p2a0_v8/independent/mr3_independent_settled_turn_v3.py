"""Independent settled-turn conditional body-invariant consumer, stdlib only.

This is one additional gate. The frozen full native/driver/physics consumers
remain required; a past rest sample is not a theorem about future body motion.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROBOTS = ("tb1", "tb2", "tb3")
REST = .01
HORIZON = .78
SETTLE_NS = 940_000_000
NATIVE_SETTLE_NS = 780_000_000
FRESH_NS = 100_000_000
DELIVERY_NS = 160_000_000
OWN_RESERVE = REST * HORIZON
PEER_RESERVE = .30 * (.16 + .02) + .30 ** 2 / (2 * .5)
REQUIRED_MARGIN = OWN_RESERVE + PEER_RESERVE


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label)
    return value


def number(value, label):
    require(type(value) in (int, float) and math.isfinite(value), label)
    return value


def ns(value):
    return round(number(value, "invalid finite timestamp") * 1_000_000_000)


def exact(left, right):
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(message):
    return hashlib.sha256(json.dumps(message, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def odom_sample(row, line):
    payload = row["payload"]
    message = payload["message"]
    stamp = message["header"]["stamp"]
    sec = integer(stamp["sec"], "odom sec")
    nano = integer(stamp["nanosec"], "odom nanosec")
    require(nano < 10**9, "odom nanosec range")
    vector = message["twist"]["twist"]["linear"]
    xyz = [number(vector[axis], "finite complete own linear vector") for axis in ("x", "y", "z")]
    position = message["pose"]["pose"]["position"]
    xyz_position = [number(position[axis], "finite raw odometry position") for axis in ("x", "y", "z")]
    frames = (message["header"]["frame_id"], message["child_frame_id"])
    require(all(type(frame) is str and frame for frame in frames), "own odom frames")
    return {"source_ns": sec * 10**9 + nano,
            "input_sequence": integer(payload["input_sequence"], "own input sequence", 1),
            "planar_speed_mps": math.hypot(xyz[0], xyz[1]),
            "odom_sha256": digest(message), "line": line, "frames": frames,
            "position_xy": xyz_position[:2], "linear_xyz": xyz}


def canonical_request(request):
    pair = []
    for name, bound in (("v", .26), ("w", .8)):
        value = number(request[name], "request finite")
        if abs(value) > bound:
            require(abs(value) == math.nextafter(bound, math.inf), "unsupported request")
            value = math.copysign(bound, value)
        pair.append(value)
    return pair


def rotation_decision(decision):
    if decision.get("reason") == "settled_turn_drift_reserve":
        return decision
    component = decision.get("component_filter")
    if isinstance(component, dict):
        rotation = component.get("rotation_check")
        if isinstance(rotation, dict) and rotation.get("reason") == "settled_turn_drift_reserve":
            require(decision["reason"] == "linear_brake_preserve_requested_turn",
                    "invalid mixed-filter reason")
            return rotation
    return None


def geometry(own, peers, clock, epoch):
    require(set(peers) == set(ROBOTS) - {own["name"]}, "missing or extra peer")
    states = [own, *peers.values()]
    for state in states:
        require(state["epoch"] == epoch and state["valid"] is True, "state epoch/valid")
        for key in ("x", "y", "yaw", "v", "w", "source_stamp"):
            number(state[key], "nonfinite geometry state")
        require(abs(state["v"]) <= .30 and abs(state["w"]) <= 1.2, "original body bounds")
        require(0 < ns(state["source_stamp"]) <= clock
                and clock - ns(state["source_stamp"]) <= 500_000_000, "state source age")
        for key in ("odom_source_stamp", "tf_source_stamp"):
            if key in state:
                require(0 < ns(state[key]) <= clock
                        and clock - ns(state[key]) <= 500_000_000, "state component source age")
    margins = {}
    for name, peer in peers.items():
        distance = math.hypot(peer["x"] - own["x"], peer["y"] - own["y"])
        own_age = (clock - ns(own["source_stamp"])) / 1e9
        peer_age = (clock - ns(peer["source_stamp"])) / 1e9
        uncertainty = .30 * (own_age + peer_age)
        margin = distance - .50 - uncertainty - .02
        require(margin >= REQUIRED_MARGIN, "insufficient original pair body margin")
        margins[name] = {"centre_distance_m": distance, "source_uncertainty_m": uncertainty,
                         "body_margin_m": margin}
    return margins


def audit_records(metadata, motion, publications, native, physics_end, require_use=False):
    epoch = metadata["epoch"]
    require(type(epoch) is str and epoch, "episode epoch")
    integer(physics_end, "physics end")
    require(set(native) == set(ROBOTS), "three native drive sources required")
    native_by_target = {}
    for robot, records in native.items():
        previous_record = previous_cmd = 0
        zero_since = None
        for row in records:
            require(row["epoch"] == epoch and row["robot"] == robot, "native epoch/robot")
            require(integer(row["record_sequence"], "native record sequence", 1)
                    == previous_record + 1, "native record sequence continuity")
            previous_record = row["record_sequence"]
            if row["kind"] != "command_received":
                continue
            cmd = integer(row["cmd_seq"], "native cmd seq", 1)
            require(cmd > previous_cmd, "native command order")
            previous_cmd = cmd
            clock = integer(row["sim_time_ns"], "native storage clock")
            source = integer(row["target_clock_ns"], "native target clock")
            sequence = integer(row["target_decision_sequence"], "native target seq", 1)
            v = number(row["desired_v"], "native finite v")
            w = number(row["desired_w"], "native finite w")
            require(abs(v) <= .26 and abs(w) <= .8 and source <= clock, "native target bounds")
            if v == 0.:
                if zero_since is None:
                    zero_since = clock
            else:
                zero_since = None
            key = (robot, sequence)
            require(key not in native_by_target, "duplicate native target storage identity")
            native_by_target[key] = {"row": row, "zero_since_ns": zero_since,
                                     "record_index": previous_record}
    published = {}
    for row in publications:
        require(row["epoch"] == epoch, "publication epoch")
        target = json.loads(row["target_json"])
        require(target["epoch"] == epoch and target["robot"] in ROBOTS, "target epoch/robot")
        key = (target["robot"], integer(target["decision_sequence"], "published decision seq", 1))
        require(key not in published, "duplicate publication identity")
        published[key] = target
    histories = {name: {"zero_since": None, "last_zero_seq": None,
                         "active_since": None, "active_anchor": None,
                         "samples": [], "input_seq": 0,
                         "decision_seq": 0} for name in ROBOTS}
    grants = []
    release_seen = None
    expected_release = integer(metadata["release_time_ns"], "reset release clock", 1)
    previous_record = 0
    for line, row in enumerate(motion, 1):
        require(row["epoch"] == epoch, "motion epoch")
        require(integer(row["record_sequence"], "motion record sequence", 1)
                == previous_record + 1, "motion record sequence continuity")
        previous_record = row["record_sequence"]
        kind = row["kind"]
        payload = row["payload"]
        if kind == "release":
            require(release_seen is None, "duplicate task release")
            release_seen = ns(payload["stamp"])
            require(release_seen == expected_release, "motion release differs from reset release")
            for history in histories.values():
                require(history["active_since"] is None, "release after activation")
                if history["zero_since"] is not None:
                    history["zero_since"] = max(history["zero_since"], release_seen)
        if kind == "settled_turn_model_failure":
            raise ValueError("production recorded settled-turn model failure: " + str(payload))
        if kind == "own_odom":
            robot = payload["robot"]
            require(robot in ROBOTS, "unknown own odom robot")
            history = histories[robot]
            sample = odom_sample(row, line)
            require(sample["source_ns"] <= physics_end, "raw own source beyond actual final physics")
            require(sample["input_sequence"] == history["input_seq"] + 1,
                    "own odom input sequence continuity")
            history["input_seq"] = sample["input_sequence"]
            prior = history["samples"][-1] if history["samples"] else None
            if prior is not None:
                require(sample["source_ns"] >= prior["source_ns"], "own odom source rewind")
                if sample["source_ns"] == prior["source_ns"]:
                    require(sample["odom_sha256"] == prior["odom_sha256"],
                            "conflicting duplicate own source")
                    continue
                require(sample["frames"] == prior["frames"], "own odom frame change")
            history["samples"].append(sample)
        if kind != "decision":
            continue
        robot = payload["robot"]
        require(robot in ROBOTS, "unknown decision robot")
        history = histories[robot]
        sequence = integer(payload["decision_sequence"], "decision sequence", 1)
        require(sequence == history["decision_seq"] + 1, "decision sequence continuity")
        history["decision_seq"] = sequence
        clock = integer(payload["clock_ns"], "decision clock")
        decision = payload["decision"]
        output = decision["output"]
        require(isinstance(output, list) and len(output) == 2, "decision output pair")
        v, w = [number(value, "finite output") for value in output]
        require(abs(v) <= .26 and abs(w) <= .8, "output hard limit")
        publication = published[(robot, sequence)]
        require(publication["clock_ns"] == clock and publication["linear_x"] == v
                and publication["angular_z"] == w, "publication/output history mismatch")
        rotation = rotation_decision(decision)
        if rotation is not None:
            require(release_seen is not None and clock >= release_seen,
                    "qualified rotation precedes unique task release")
            require(payload["started"] is True and payload["ready"] is True,
                    "qualified rotation only in ready task")
            original = canonical_request(payload["request"])
            require(v == 0. and w != 0. and w == original[1],
                    "qualified output must preserve only requested angular direction/value")
            require(rotation["allow"] is True and rotation["output"] == output,
                    "rotation output mismatch")
            own = payload["own_state"]
            require(own["name"] == robot, "own identity")
            certificate = own["settled_turn"]
            integer(certificate["zero_since_ns"], "certificate zero clock")
            integer(certificate["last_zero_decision_sequence"], "certificate prior sequence", 1)
            number(certificate["active_path_m"], "finite certificate active path")
            require(certificate["schema"] == "mr3-settled-turn-v1", "certificate schema")
            require(certificate["zero_since_ns"] == history["zero_since"]
                    and certificate["last_zero_decision_sequence"] == history["last_zero_seq"],
                    "certificate lacks exact prior zero publication history")
            require(history["zero_since"] is not None
                    and clock - history["zero_since"] >= SETTLE_NS, "zero publications too short")
            require(certificate["active_since_ns"] == history["active_since"],
                    "certificate active history mismatch")
            anchor = history["active_anchor"]
            active_path = 0.
            if anchor is not None:
                previous = anchor
                for actual_sample in history["samples"]:
                    if anchor["source_ns"] < actual_sample["source_ns"] <= clock:
                        active_path += math.hypot(actual_sample["position_xy"][0] - previous["position_xy"][0],
                                                  actual_sample["position_xy"][1] - previous["position_xy"][1])
                        previous = actual_sample
            require(certificate.get("active_anchor_source_ns")
                    == (anchor["source_ns"] if anchor is not None else None)
                    and certificate.get("active_path_m") == active_path,
                    "certificate active anchor/path differs from raw history")
            samples = [sample for sample in history["samples"] if sample["source_ns"] <= clock]
            require(len(samples) >= 3, "three actual past own sources required")
            samples = samples[-3:]
            for index, sample in enumerate(samples):
                require(sample["source_ns"] >= history["zero_since"] + SETTLE_NS,
                        "rest sources precede full publication settle")
                require(sample["planar_speed_mps"] <= REST, "full planar rest bound")
                require(0 <= clock - sample["source_ns"] <= FRESH_NS, "all three rest sources fresh")
                if index:
                    require(0 < sample["source_ns"] - samples[index - 1]["source_ns"] <= FRESH_NS,
                            "three source rest gap")
            require(0 <= clock - samples[-1]["source_ns"] <= FRESH_NS, "stale rest source")
            expected = [{key: sample[key] for key in ("source_ns", "input_sequence",
                        "planar_speed_mps", "odom_sha256")} for sample in samples]
            require(exact(certificate["samples"], expected), "certificate differs from raw own samples")
            require(ns(own["odom_source_stamp"]) == samples[-1]["source_ns"]
                    and own["planar_speed_mps"] == samples[-1]["planar_speed_mps"]
                    and own["v"] == samples[-1]["linear_xyz"][0],
                    "own latest raw source binding")
            detail = rotation["settled_turn_check"]
            require(detail == {"schema": "mr3-settled-turn-check-v1", "certificate": certificate,
                               "horizon_sec": HORIZON, "own_drift_reserve_m": OWN_RESERVE,
                               "peer_braking_reserve_m": PEER_RESERVE,
                               "required_body_margin_m": REQUIRED_MARGIN},
                    "conditional reserve metadata changed")
            margins = geometry(own, payload["received_peers"], clock, epoch)
            target = published[(robot, sequence)]
            require(target["clock_ns"] == clock and target["linear_x"] == 0.
                    and target["angular_z"] == w, "qualified publication differs from final output")
            storage = native_by_target[(robot, sequence)]
            actual = storage["row"]
            require(actual["target_clock_ns"] == clock and actual["desired_v"] == 0.
                    and actual["desired_w"] == w, "qualified native storage differs from publication")
            require(0 <= actual["sim_time_ns"] - clock <= DELIVERY_NS,
                    "actual storage producer age exceeds160ms")
            require(storage["zero_since_ns"] is not None
                    and clock - storage["zero_since_ns"] >= NATIVE_SETTLE_NS,
                    "actual zero storage history shorter than780ms")
            if history["active_since"] is None:
                history["active_since"] = clock
                history["active_anchor"] = samples[-1]
                grants.append({"robot": robot, "clock_ns": clock, "decision_sequence": sequence,
                               "actual_storage_clock_ns": actual["sim_time_ns"],
                               "actual_record_index": storage["record_index"],
                               "native_zero_since_ns": storage["zero_since_ns"],
                               "last_entry_sample": samples[-1], "pair_margins": margins})
        if v != 0.:
            history["zero_since"] = history["last_zero_seq"] = history["active_since"] = None
            history["active_anchor"] = None
        else:
            if history["zero_since"] is None:
                history["zero_since"] = clock
            history["last_zero_seq"] = sequence
    require(release_seen == expected_release, "missing unique task release")
    intervals = []
    for grant in grants:
        robot = grant["robot"]
        stop = physics_end
        for row in native[robot]:
            if (row["kind"] == "command_received"
                    and row["record_sequence"] > grant["actual_record_index"]
                    and row["desired_v"] != 0.):
                stop = min(stop, row["sim_time_ns"])
                break
        require(stop >= grant["clock_ns"], "native interval end before grant")
        anchor = grant["last_entry_sample"]
        samples = [sample for sample in histories[robot]["samples"]
                   if anchor["source_ns"] < sample["source_ns"] <= stop]
        previous = anchor
        maximum = anchor["planar_speed_mps"]
        sampled_path = 0.
        for sample in samples:
            require(sample["planar_speed_mps"] <= REST,
                    "activated actual-zero interval exceeds full planar .01 invariant")
            require(0 < sample["source_ns"] - previous["source_ns"] <= FRESH_NS,
                    "activated actual-zero interval raw source gap")
            chord = math.hypot(sample["position_xy"][0] - previous["position_xy"][0],
                               sample["position_xy"][1] - previous["position_xy"][1])
            require(chord / ((sample["source_ns"] - previous["source_ns"]) / 1e9) <= REST,
                    "activated raw odom chord speed exceeds full planar .01 invariant")
            sampled_path += chord
            require(sampled_path <= OWN_RESERVE,
                    "activated entire actual-zero interval cumulative odom drift exceeds7.8mm")
            maximum = max(maximum, sample["planar_speed_mps"])
            previous = sample
        require(0 <= stop - previous["source_ns"] <= FRESH_NS,
                "activated interval lacks final fresh raw source")
        intervals.append({**grant, "actual_zero_interval_end_ns": stop,
                          "future_raw_unique_samples": len(samples),
                          "maximum_planar_speed_mps": maximum,
                          "whole_interval_sampled_odom_polyline_m": sampled_path,
                          "drift_anchor_source_ns": anchor["source_ns"]})
    coverage = bool(intervals)
    return {"schema": "mr3-independent-settled-turn-v3", "passed": not require_use or coverage,
            "coverage_errors": ([] if not require_use or coverage else
                                ["no real settled-turn use: trigger coverage absent"]),
            "integrity_and_sampled_model_bounds_passed": True,
            "stimulus_coverage_passed": bool(intervals), "qualification_intervals": intervals,
            "criteria": {"published_settle_ns": SETTLE_NS, "actual_settle_ns": NATIVE_SETTLE_NS,
                         "rest_speed_mps": REST, "own_drift_reserve_m": OWN_RESERVE,
                         "peer_full_reserve_m": PEER_RESERVE, "pair_required_body_margin_m": REQUIRED_MARGIN},
            "scope": "Additional conditional body-invariant sampled evidence only. Entire zero-only interval speed and cumulative raw odom chords are checked, on the closed sampled interval after the entry anchor through the actual nonzero-storage/final-physics endpoint, with no budget reset at repeated grants. Chords are a sampled lower bound, not proof of a continuous upper path bound. Full driver/native/physical/task consumers required; no continuous-body theorem or overall task credit."}


def audit_episode(directory, freeze, require_use=False):
    inputs = {}
    def read(name, lines=False):
        path = directory / name
        if not path.exists():
            path = Path(str(path) + ".gz")
        raw = path.read_bytes()
        inputs[str(path)] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        data = gzip.decompress(raw) if path.suffix == ".gz" else raw
        if lines:
            require(not data or data.endswith(b"\n"), "incomplete JSONL: " + name)
            return [json.loads(line) for line in data.splitlines() if line.strip()]
        return json.loads(data)
    metadata = None
    final = None
    try:
        metadata = read("metadata.json")
        transitions = read("transitions.jsonl", True)
        require(transitions and transitions[0]["kind"] == "reset"
                and transitions[0]["info"]["epoch"] == metadata["epoch"], "original reset record")
        release = integer(transitions[0]["info"]["release_time_ns"], "reset release", 1)
        if "release_time_ns" in metadata:
            require(metadata["release_time_ns"] == release, "metadata/reset release mismatch")
        metadata = {**metadata, "release_time_ns": release}
        require(metadata["freeze"] == freeze and len(freeze) == 40
                and all(character in "0123456789abcdef" for character in freeze),
                "exact frozen metadata required")
        physics = read("physics.jsonl", True)
        require(physics and all(row["epoch"] == metadata["epoch"] for row in physics), "physics epoch")
        final = physics[-1]["end_time_ns"]
        result = audit_records(metadata, read("motion_safety.jsonl", True),
                               read("drive_targets.jsonl", True),
                               {name: read("drive_" + name + ".jsonl", True) for name in ROBOTS},
                               final, require_use)
    except Exception as error:
        result = {"schema": "mr3-independent-settled-turn-v3", "passed": False,
                  "integrity_and_sampled_model_bounds_passed": False, "error": repr(error)}
    for path, binding in inputs.items():
        try:
            stable = hashlib.sha256(Path(path).read_bytes()).hexdigest() == binding["sha256"]
        except OSError:
            stable = False
        if not stable:
            result.update(passed=False, integrity_and_sampled_model_bounds_passed=False,
                          error="input changed while auditing: " + path)
    return {**result, "directory": str(directory),
            "epoch": metadata.get("epoch") if isinstance(metadata, dict) else None,
            "freeze": freeze, "inputs": inputs, "final_physics_time_ns": final}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-use", action="store_true")
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists; failure cannot be overwritten")
    episodes = [args.directory] if (args.directory / "metadata.json").exists() or (args.directory / "metadata.json.gz").exists() else sorted(args.directory.glob("worker*/episode*"))
    try:
        require(episodes, "no episodes")
        results = [audit_episode(ep, args.freeze, args.require_use) for ep in episodes]
        result = {"schema": "mr3-independent-settled-turn-run-v3",
                  "passed": all(result["passed"] for result in results), "episodes": results}
    except Exception as error:
        result = {"schema": "mr3-independent-settled-turn-run-v3", "passed": False, "error": repr(error)}
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
