"""v15 workload adapter: v4/32 reset bounds, unchanged fixed angular criteria."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
from types import ModuleType


SCHEDULE = [["open", 101], ["open", 101], ["rooms", 101], ["corridors", 101]]
PROBE_VERSION = "mr3-p2a0-outward-cancel-v4"
CONSUMER_SHA256 = "7a472ba7efdd55addc710b98c66c89feff7f5092f214f76fd76cd4ca526343d0"
INPUTS = ("metadata.json", "transitions.jsonl", "physics.jsonl", "motion_safety.jsonl")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read(directory, name, proof, lines=False):
    variants = [path for path in (directory / name, directory / (name + ".gz"))
                if path.is_file()]
    require(len(variants) == 1, "missing/ambiguous raw input: " + str(directory / name))
    path = variants[0]
    raw = path.read_bytes()
    proof[str(path)] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if name == "motion_safety.jsonl":
        return None  # The pinned consumer parses this bound raw payload.
    data = gzip.decompress(raw) if path.suffix == ".gz" else raw
    if lines:
        require(not data or data.endswith(b"\n"), "incomplete JSONL: " + str(path))
        return [json.loads(line) for line in data.splitlines()]
    return json.loads(data)


def audit(directory, freeze, consumer_path=None):
    directory = Path(directory)
    consumer_path = (Path(consumer_path) if consumer_path else
                     Path(__file__).resolve().parents[2] / "20261017_mr3_p2a0_v4" / "independent" / "mr3_independent_angular_interface_v1.py")
    result = {
        "schema": "mr3-independent-angular-reset-matrix-v1", "directory": str(directory),
        "freeze": freeze, "passed": False, "errors": [], "episodes": [],
        "script_sha256": sha(__file__), "benchmark_inputs": {},
        "angular_consumer": {"path": str(consumer_path), "expected_sha256": CONSUMER_SHA256},
        "criteria": {"workers": 2, "schedule": SCHEDULE, "steps_per_episode": 32,
                     "probe_version": PROBE_VERSION,
                     "episode_gate": "sampled_bounds_passed is True for every exact reset episode",
                     "stimulus_coverage_is_not_a_reset_gate": True},
        "scope": ("All eight reset episodes retain the frozen angular consumer's complete "
                  "original result and raw input/physics-boundary bindings. Only sampled "
                  "bounds are aggregated here; absent stimulus coverage remains absent. "
                  "Native closure, contacts, activity, linear/chord and braking gates are "
                  "independent prerequisites. No production, ROS or truth imports; finite "
                  "source differences do not prove continuous angular acceleration.")}
    errors = result["errors"]
    consumer = None
    try:
        require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze),
                "exact 40-hex source freeze required")
        payload = consumer_path.read_bytes()
        actual_sha = hashlib.sha256(payload).hexdigest()
        result["angular_consumer"]["sha256"] = actual_sha
        require(actual_sha == CONSUMER_SHA256, "frozen angular consumer SHA mismatch")
        consumer = ModuleType("mr3_frozen_angular_consumer")
        consumer.__file__ = str(consumer_path)
        exec(compile(payload, str(consumer_path), "exec"), consumer.__dict__)
    except (OSError, ValueError, TypeError, ImportError) as error:
        errors.append("source: " + repr(error))
    try:
        metadata = read(directory, "benchmark_metadata.json", result["benchmark_inputs"])
        summary = read(directory, "benchmark_summary.json", result["benchmark_inputs"])
        declaration = {"freeze": freeze, "workers": 2, "robots_per_worker": 3,
                       "schedule": SCHEDULE, "steps_per_episode": 32,
                       "preparation_probe_version": PROBE_VERSION,
                       "preparation_motion_probe": True, "terminal_probe": False,
                       "deadline_probe": False, "fault_probe": False}
        for source in (metadata, summary):
            require(canonical({key: source.get(key) for key in declaration})
                    == canonical(declaration), "not the exact declared reset workload")
        require(summary.get("passed") is True, "native reset benchmark did not pass")
        workers = summary["workers_results"]
        require(len(workers) == 2 and {row["worker_id"] for row in workers} == {0, 1}
                and all(type(row["worker_id"]) is int for row in workers),
                "missing/duplicate reset worker summary")
        for worker in workers:
            cells = worker["episodes"]
            require(len(cells) == 4, "reset worker does not contain four episodes")
            for cell, (scene, seed) in zip(cells, SCHEDULE):
                require(canonical([cell.get("scene"), cell.get("seed"),
                                   cell.get("transitions")]) == canonical([scene, seed, 32])
                        and cell.get("terminated") is False and cell.get("truncated") is True,
                        "summary reset cell differs from the declared complete fixture")
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        errors.append("benchmark: " + repr(error))
    expected = {(f"worker{worker}", f"episode{index + 1:03d}_{scene}_{seed}")
                for worker in (0, 1) for index, (scene, seed) in enumerate(SCHEDULE)}
    actual = {tuple(path.parts[-2:]) for path in directory.glob("worker*/episode*")
              if path.is_dir()}
    workers = {path.name for path in directory.glob("worker*") if path.is_dir()}
    if actual != expected or workers != {"worker0", "worker1"}:
        errors.append("exact two-worker/eight-episode reset directories required")
    epochs = set()
    for identity in sorted(expected | actual):
        episode = directory.joinpath(*identity)
        row = {"episode": "/".join(identity), "input_bindings": {},
               "release_time_ns": None, "final_physics_time_ns": None,
               "sampled_bounds_passed": False, "errors": []}
        try:
            raw = {name: read(episode, name, row["input_bindings"], name.endswith("jsonl"))
                   for name in INPUTS}
            meta, transitions, physics = (raw[name] for name in INPUTS[:3])
            row["release_time_ns"] = transitions[0]["info"]["release_time_ns"]
            row["final_physics_time_ns"] = physics[-1]["end_time_ns"]
            row["epoch"] = meta["epoch"]
            require(identity in expected, "unplanned reset episode")
            index = int(identity[1][7:10]) - 1
            scene, seed = SCHEDULE[index]
            require(meta["freeze"] == freeze
                    and canonical([meta["scene"], meta["seed"]]) == canonical([scene, seed])
                    and type(meta["epoch"]) is str and meta["epoch"]
                    and meta["epoch"] not in epochs, "episode source/identity mismatch")
            epochs.add(meta["epoch"])
            require(len(transitions) == 33 and transitions[0]["kind"] == "reset"
                    and all(item["kind"] == "step" for item in transitions[1:])
                    and transitions[-1]["terminated"] is False
                    and transitions[-1]["truncated"] is True,
                    "episode lacks thirty-two actual nonterminal reset-step records")
            require(consumer is not None, "unverified frozen angular consumer")
            original = consumer.audit_episode(episode)
            row.update(sampled_bounds_passed=original["sampled_bounds_passed"],
                       stimulus_coverage_passed=original["stimulus_coverage_passed"],
                       original_passed=original["passed"])
            require(all(type(row[key]) is bool for key in
                        ("sampled_bounds_passed", "stimulus_coverage_passed", "original_passed")),
                    "nonboolean frozen angular result")
            canonical(original)  # Invalid/nonfinite diagnostics still yield a failure JSON.
            row["original_angular_audit"] = original
            require(original["schema"] == "mr3-independent-angular-interface-v1"
                    and original["inputs"] == row["input_bindings"]
                    and original["epoch"] == meta["epoch"]
                    and original["release_time_ns"] == row["release_time_ns"]
                    and original["final_physics_time_ns"] == row["final_physics_time_ns"],
                    "frozen angular result lost original input/boundary binding")
            for path, proof in row["input_bindings"].items():
                require(sha(path) == proof["sha256"], "raw input changed during angular audit")
            require(row["sampled_bounds_passed"] is True, "sampled angular bounds failed")
        except (OSError, ValueError, TypeError, KeyError, IndexError, gzip.BadGzipFile) as error:
            row["errors"].append(repr(error))
        errors.extend(row["episode"] + ": " + error for error in row["errors"])
        result["episodes"].append(row)
    result["passed"] = (not errors and len(result["episodes"]) == 8
                        and all(row["sampled_bounds_passed"] is True
                                for row in result["episodes"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--angular-consumer", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; do not overwrite diagnostic results")
    result = audit(args.directory, args.freeze, args.angular_consumer)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
