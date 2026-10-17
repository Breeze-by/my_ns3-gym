"""Read-only live diagnostics; frozen canonical consumers determine final acceptance."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path("/home/zhuyulab/ns3-workspace")
PARAMETER_SCRIPT = ROOT / ("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
    "report/assets/20261017_mr3_p2a0_v4/independent/mr3_actual_nav2_parameters_v4.py")
ROBOTS = ("tb1", "tb2", "tb3")


def rows(path):
    if not path.exists():
        return
    with path.open() as stream:
        for line in stream:
            if not line.endswith("\n"):
                break
            if line.strip():
                yield json.loads(line)


def same_identity(pid, start):
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return False
    return int(raw[raw.rfind(")") + 2:].split()[19]) == start


def inspect_episode(directory, metadata):
    errors, pending = [], []
    transitions = list(rows(directory / "transitions.jsonl"))
    release = transitions[0]["info"]["release_time_ns"] if transitions else None
    parameter_path = directory / "actual_nav2_parameters.json"
    parameter = {"available": parameter_path.exists()}
    if parameter_path.exists():
        report = json.loads(parameter_path.read_text())
        spec = importlib.util.spec_from_file_location("readonly_parameter_rules", PARAMETER_SCRIPT)
        rules = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rules)
        identities = set()
        try:
            rules.require(report["passed"] is True and not report["errors"], "parameter review not PASS")
            rules.require(report["freeze"] == metadata["freeze"] and report["source_clock_ns"] == release,
                          "parameter review freeze/release mismatch")
            binding = metadata["preparation_parameter_review_source"]
            actual_sha = hashlib.sha256(PARAMETER_SCRIPT.read_bytes()).hexdigest()
            rules.require(report["script_sha256"] == binding["sha256"] == actual_sha,
                          "actual parameter script binding differs")
            rules.require(binding["freeze"] == metadata["freeze"], "parameter script source epoch mismatch")
            rules.require(all(report["cleanup"].values()) and not report["cleanup_errors"], "parameter cleanup")
            for row in report["nodes"]:
                parts = row["node"].split("/")
                rules.require(len(parts) == 3 and parts[1] in ROBOTS and parts[2] in rules.EXPECTED,
                              "parameter actual namespace/name")
                rules.require(row["node"] not in identities, "duplicate actual parameter node")
                identities.add(row["node"])
                rules.require(row["epoch"] == report["epoch"] == transitions[0]["snapshot"]["epoch"]
                              and row["source_clock_ns"] == release
                              and row["service"] == row["node"] + "/get_parameters",
                              "actual parameter response identity/source mismatch")
                rules.validate_parameters(parts[2], row["typed_parameters"])
            rules.require(len(identities) == 9, "all nine actual nodes required")
            for status in report["motion_status_receipts"]:
                rules.validate_status(status["status"], report["epoch"], release)
            rules.require(bool(report["motion_status_receipts"]), "no actual paused status received")
            parameter.update(passed=True, nodes=sorted(identities), source_clock_ns=release,
                             script_sha256=actual_sha, cleanup=report["cleanup"])
        except (ValueError, TypeError, KeyError, IndexError) as error:
            errors.append("parameter readback: " + repr(error))
            parameter.update(passed=False, error=repr(error))
    else:
        pending.append("actual parameter readback not yet returned")
    robot = {name: {"raw_odom_messages": 0, "unique_source_samples": 0,
                   "maximum_planar_speed": 0., "maximum_angular_norm": 0.,
                   "maximum_abs_wz": 0., "maximum_sampled_angular_vector_acceleration": 0.,
                   "maximum_actual_abs_linear": 0., "maximum_actual_abs_angular": 0.,
                   "violations": []} for name in ROBOTS}
    previous = {}
    for row in rows(directory / "motion_safety.jsonl"):
        payload = row["payload"]
        if row["kind"] == "actual_cmd_vel":
            name = payload["robot"]
            twist = payload["twist"]
            v, w = twist["linear"]["x"], twist["angular"]["z"]
            robot[name]["maximum_actual_abs_linear"] = max(robot[name]["maximum_actual_abs_linear"], abs(v))
            robot[name]["maximum_actual_abs_angular"] = max(robot[name]["maximum_actual_abs_angular"], abs(w))
            if abs(v) > .26 or abs(w) > .8:
                robot[name]["violations"].append({"kind": "actual command bound", "original": row})
        if row["kind"] != "own_odom":
            continue
        name, message = payload["robot"], payload["message"]
        current = robot[name]
        current["raw_odom_messages"] += 1
        stamp = message["header"]["stamp"]
        source = stamp["sec"] * 10**9 + stamp["nanosec"]
        angular = [message["twist"]["twist"]["angular"][axis] for axis in ("x", "y", "z")]
        linear = [message["twist"]["twist"]["linear"][axis] for axis in ("x", "y")]
        if not all(math.isfinite(value) for value in angular + linear):
            current["violations"].append({"kind": "nonfinite actual odometry", "original": row})
            continue
        norm, speed = math.sqrt(sum(value * value for value in angular)), math.hypot(*linear)
        if norm > current["maximum_angular_norm"]:
            current["maximum_angular_norm"] = norm
            current["maximum_angular_original"] = row
        current["maximum_abs_wz"] = max(current["maximum_abs_wz"], abs(angular[2]))
        current["maximum_planar_speed"] = max(current["maximum_planar_speed"], speed)
        if norm > 1.2 or speed > .30:
            current["violations"].append({"kind": "raw physical speed bound", "source_ns": source,
                                           "planar_speed": speed, "angular_norm": norm, "original": row})
        frame = (message["header"]["frame_id"], message["child_frame_id"])
        old = previous.get(name)
        if old and source == old["source"]:
            if message != old["row"]["payload"]["message"]:
                current["violations"].append({"kind": "same-source conflicting raw odometry", "original": row})
            continue
        current["unique_source_samples"] += 1
        if old and source > old["source"] and frame == old["frame"]:
            acceleration = math.sqrt(sum((a-b)**2 for a, b in zip(angular, old["angular"]))) / ((source-old["source"])/1e9)
            if acceleration > current["maximum_sampled_angular_vector_acceleration"]:
                current["maximum_sampled_angular_vector_acceleration"] = acceleration
                current["maximum_acceleration_original_pair"] = [old["row"], row]
            if release is not None and old["source"] >= release and acceleration > 7.:
                current["violations"].append({"kind": "task sampled angular vector acceleration bound",
                    "acceleration": acceleration, "original_pair": [old["row"], row]})
        previous[name] = {"source": source, "frame": frame, "angular": angular, "row": row}
    supervisor = directory / "supervisor_shutdown.json"
    closure = {"available": supervisor.exists()}
    if supervisor.exists():
        value = json.loads(supervisor.read_text())
        closure.update({key: value[key] for key in ("worker_returncode", "forced_shutdown", "failed_sample",
                                                   "remaining_owned_processes", "remaining_owned_zombies")})
        remaining = [entry for entry in value["owned_processes_seen"]
                     if same_identity(entry["pid"], entry["start_ticks"])]
        closure["same_saved_identities_still_present"] = remaining
        closure["unique_saved_identities"] = len({(v["pid"], v["start_ticks"]) for v in value["owned_processes_seen"]})
        closure["strict_supervisor_passed"] = (value["worker_returncode"] == 0
            and value["forced_shutdown"] is False and value["failed_sample"] is False
            and not value["remaining_owned_processes"] and not value["remaining_owned_zombies"] and not remaining)
        if not closure["strict_supervisor_passed"]:
            errors.append("strict supervisor closure failed")
    else:
        pending.append("worker native/owned shutdown still in progress")
    return {"directory": str(directory), "release_time_ns": release, "parameters": parameter,
            "robots": robot, "closure": closure, "errors": errors, "pending": pending}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--parent-start-ticks", type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists")
    metadata = json.loads((args.run / "benchmark_metadata.json").read_text())
    phase_path = args.output.with_name(args.output.stem + "_fifo_phase.json")
    completed = subprocess.run([sys.executable, "/tmp/mr3_readonly_terminal_live.py", str(args.run), str(phase_path)],
                               capture_output=True, text=True, check=True)
    result = {"schema": "mr3-v4-interface-readonly-runtime-diagnostic-v1", "freeze": metadata["freeze"],
              "run": str(args.run), "observed_wall_monotonic_ns": time.monotonic_ns(),
              "episodes": [inspect_episode(ep, metadata) for ep in sorted(args.run.glob("worker*/episode*"))],
              "fifo_phase": json.loads(phase_path.read_text()),
              "scope": "live read-only diagnostic; incomplete cross-file snapshots are pending. "
                       "Original raw measured-limit violations remain real failures. "
                       "Final frozen canonical audits still required; no braking or policy credit"}
    if args.parent_pid and args.parent_start_ticks:
        result["benchmark_parent"] = {"pid": args.parent_pid, "start_ticks": args.parent_start_ticks,
            "same_identity_present": same_identity(args.parent_pid, args.parent_start_ticks)}
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "episodes": len(result["episodes"]),
        "raw_violation_counts": [{name: len(value["violations"]) for name, value in row["robots"].items()}
                                 for row in result["episodes"]]}))


if __name__ == "__main__":
    main()
