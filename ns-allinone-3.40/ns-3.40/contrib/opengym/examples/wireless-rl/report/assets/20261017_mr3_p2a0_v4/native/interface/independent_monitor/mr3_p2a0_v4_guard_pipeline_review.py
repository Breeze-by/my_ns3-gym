"""Independent stdlib command/FIFO and odometry-age review of a closed episode."""

import argparse
from collections import Counter, deque
import gzip
import hashlib
import json
import math
from pathlib import Path


ROBOTS = ("tb1", "tb2", "tb3")


def require(value, message):
    if not value:
        raise ValueError(message)


def ns(value):
    require(type(value) in (int, float) and math.isfinite(value), "invalid scalar clock")
    return round(value * 10**9)


def source(message):
    stamp = message["header"]["stamp"]
    require(type(stamp["sec"]) is int and type(stamp["nanosec"]) is int,
            "noninteger original source stamp")
    return stamp["sec"] * 10**9 + stamp["nanosec"]


def pair(message):
    require(all(type(value) in (int, float) and math.isfinite(value)
                for axis in ("linear", "angular") for value in message[axis].values()),
            "nonfinite request/output")
    require(all(message[axis][key] == 0 for axis, key in (
        ("linear", "y"), ("linear", "z"), ("angular", "x"), ("angular", "y"))),
            "unsupported command axis")
    return [message["linear"]["x"], message["angular"]["z"]]


def audit(directory, freeze):
    proof = {}

    def read(name, lines=False):
        path = directory / name
        if not path.exists():
            path = Path(str(path) + ".gz")
        raw = path.read_bytes()
        proof[str(path)] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        data = gzip.decompress(raw) if path.suffix == ".gz" else raw
        require(not lines or data.endswith(b"\n"), "incomplete raw JSONL")
        return [json.loads(line) for line in data.splitlines()] if lines else json.loads(data)

    metadata = read("metadata.json")
    require(metadata["freeze"] == freeze, "different source freeze")
    epoch = metadata["epoch"]
    topology = read("motion_topology.json")["endpoints"]
    rows = read("motion_safety.jsonl", True)
    own = {name: {"odom": {}, "tf": {}} for name in ROBOTS}
    raw_requests, output_queues = dict.fromkeys(ROBOTS), {name: deque() for name in ROBOTS}
    statistics = {name: {"decisions": 0, "actual": 0, "raw_requests": 0,
                         "nonzero_actual": 0, "rotation_only_actual": 0,
                         "max_abs_actual_v": 0., "max_abs_actual_w": 0.,
                         "max_abs_raw_v": 0., "max_abs_raw_w": 0.,
                         "direction_metadata": 0, "different_source_ages": 0,
                         "reason_counts": Counter()} for name in ROBOTS}
    examples, errors = [], []
    for line, row in enumerate(rows, 1):
        try:
            require(row["epoch"] == epoch and row["record_sequence"] == line,
                    "epoch/record sequence mismatch")
            kind, value = row["kind"], row["payload"]
            if kind in ("own_odom", "own_tf"):
                own[value["robot"]]["odom" if kind == "own_odom" else "tf"][
                    value["input_sequence"]] = value["message"]
            elif kind == "raw_request":
                name = value["robot"]
                request = value["request"]
                require(pair(value["twist"]) == [request["v"], request["w"]],
                        "request differs from native Twist")
                identity = request["publisher_identity"]
                require(identity["scope"] == "graph_at_callback" and identity["valid"] is True
                        and len(identity["endpoints"]) == 1
                        and identity["endpoints"][0]["namespace"] == "/" + name
                        and identity["endpoints"][0]["node"] == "velocity_smoother",
                        "request graph differs from native smoother")
                raw_requests[name] = request
                stats = statistics[name]
                stats["raw_requests"] += 1
                stats["max_abs_raw_v"] = max(stats["max_abs_raw_v"], abs(request["v"]))
                stats["max_abs_raw_w"] = max(stats["max_abs_raw_w"], abs(request["w"]))
            elif kind == "decision":
                name, state = value["robot"], value["own_state"]
                stats = statistics[name]
                stats["decisions"] += 1
                require(value["decision_sequence"] == stats["decisions"],
                        "decision sequence gap")
                require(value["request"] == raw_requests[name], "decision lost received request")
                decision, request = value["decision"], value["request"]
                output = decision["output"]
                require(abs(output[0]) <= .26 and abs(output[1]) <= .8,
                        "actual requested publication exceeds hard limit")
                canonical = None if request is None else [request["v"], request["w"]]
                normalization = decision.get("command_normalization")
                if normalization is not None:
                    canonical = [request["v"], request["w"]]
                    changed = []
                    for axis, limit in enumerate((.26, .8)):
                        if abs(canonical[axis]) > limit:
                            require(abs(canonical[axis]) == math.nextafter(limit, math.inf),
                                    "normalization is broader than one ULP")
                            canonical[axis] = math.copysign(limit, canonical[axis])
                            changed.append(("v", "w")[axis])
                    require(normalization == {"schema": "mr3-command-one-ulp-v1",
                            "input": [request["v"], request["w"]], "canonical": canonical,
                            "normalized_axes": changed} and changed, "normalization mismatch")
                if decision["allow"]:
                    component = decision.get("component_filter")
                    if component is None:
                        require(output == canonical, "allowed output changed request")
                    else:
                        require(component["canonical_input"] == canonical
                                and canonical[0] != 0 and canonical[1] != 0
                                and output == [0., canonical[1]]
                                and component["rejected_mixed_decision"]["reason"]
                                == "peer_braking_nonclosing"
                                and component["rotation_check"]["allow"] is True
                                and component["rotation_check"]["output"] == output,
                                "component filter is not original-turn/linear-brake only")
                else:
                    require(output == [0., 0.], "rejected output is nonzero")
                stats["reason_counts"][decision["reason"]] += 1
                if state is not None:
                    odom = own[name]["odom"][state["input_sequences"]["odom"]]
                    transform = own[name]["tf"][state["input_sequences"]["tf"]]
                    odom_ns, tf_ns = source(odom), source(transform) - 200_000_000
                    require(ns(state["odom_source_stamp"]) == odom_ns
                            and ns(state["tf_source_stamp"]) == tf_ns
                            and ns(state["source_stamp"]) == min(odom_ns, tf_ns)
                            and state["w"] == odom["twist"]["twist"]["angular"]["z"],
                            "own angular/geometry source does not bind original odom/TF")
                    pending = [decision]
                    while pending:
                        check_result = pending.pop()
                        component = check_result.get("component_filter")
                        if component:
                            pending.extend([component["rejected_mixed_decision"],
                                            component["rotation_check"]])
                        for peer_check in check_result.get("near_peer_checks", []):
                            for check in peer_check["direction_checks"]:
                                geometry_age = (value["clock_ns"] - min(odom_ns, tf_ns)) / 1e9
                                angular_age = (value["clock_ns"] - odom_ns) / 1e9
                                turn = max(abs(canonical[1]), min(1.2, abs(state["w"])
                                                                  + 7 * angular_age))
                                expected = {"geometry_source_stamp": min(odom_ns, tf_ns) / 1e9,
                                            "geometry_source_age_sec": geometry_age,
                                            "angular_velocity_source_stamp": odom_ns / 1e9,
                                            "angular_velocity_source_age_sec": angular_age,
                                            "source_yaw_uncertainty_rad": 1.2 * geometry_age,
                                            "turn_bound_radps": turn, "horizon_sec": .78,
                                            "heading_half_angle_rad": 1.2 * geometry_age
                                            + turn * .78}
                                require(all(math.isclose(check[key], expected_value,
                                                         rel_tol=1e-12, abs_tol=1e-12)
                                            for key, expected_value in expected.items()),
                                        "pending turn uses wrong source age or geometry yaw age")
                                stats["direction_metadata"] += 1
                                stats["different_source_ages"] += geometry_age != angular_age
                                if geometry_age != angular_age and len(examples) < 6:
                                    examples.append({"line": line, "robot": name,
                                                     "clock_ns": value["clock_ns"], **check})
                output_queues[name].append((value["decision_sequence"], output))
            elif kind == "actual_cmd_vel":
                name = value["robot"]
                sequence, output = output_queues[name].popleft()
                actual = pair(value["twist"])
                require(value["observed_decision_sequence"] == sequence and actual == output,
                        "actual topic receipt differs from decision FIFO")
                identity = value["publisher_identity"]
                require(identity["scope"] == "graph_at_callback" and identity["valid"] is True
                        and identity["endpoints"] == topology[f"/{name}/cmd_vel"],
                        "actual publisher graph differs from startup unique endpoint")
                stats = statistics[name]
                stats["actual"] += 1
                stats["nonzero_actual"] += actual != [0., 0.]
                stats["rotation_only_actual"] += actual[0] == 0 and actual[1] != 0
                stats["max_abs_actual_v"] = max(stats["max_abs_actual_v"], abs(actual[0]))
                stats["max_abs_actual_w"] = max(stats["max_abs_actual_w"], abs(actual[1]))
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append({"line": line, "kind": row.get("kind"), "error": repr(error)})
    if any(output_queues.values()):
        errors.append({"error": "unconsumed final output FIFO"})
    return {"schema": "mr3-v4-independent-command-age-review-v1", "passed": not errors,
            "epoch": epoch, "freeze": freeze, "errors": errors, "robots": statistics,
            "different_age_original_checks": examples, "inputs": proof,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": ("Independent scalar command boundary/FIFO and original odom/TF source-time "
                      "arithmetic. Source-age comparison tolerance 1e-12 is arithmetic only. "
                      "Graph-at-callback is not packet identity or Gazebo actuator receipt. "
                      "Frozen geometry/native ACK/contact/closure and physical norm/response "
                      "audits remain separately required.")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists")
    result = audit(args.episode, args.freeze)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"][:6]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
