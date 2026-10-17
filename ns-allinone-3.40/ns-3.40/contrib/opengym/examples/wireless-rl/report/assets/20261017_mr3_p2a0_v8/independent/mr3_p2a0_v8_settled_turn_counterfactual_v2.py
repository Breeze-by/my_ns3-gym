"""Historical-input opportunities only; never new native movement or plant credit."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import types

ROOT = Path("/home/zhuyulab/ns3-workspace")
PKG = ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration"
ROBOTS = ("tb1", "tb2", "tb3")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("episode", type=Path)
    p.add_argument("--output-directory", type=Path, required=True)
    args = p.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    sources = {name: (PKG / name).read_bytes() for name in
               ("mr3_motion_safety.py", "motion_safety.py", "mr3_episode.py")}
    for name, raw in sources.items():
        (args.output_directory / ("reviewed_" + name)).write_bytes(raw)
    package = types.ModuleType("multi_robot_exploration")
    package.__path__ = []
    sys.modules[package.__name__] = package
    for name in ("mr3_episode.py", "mr3_motion_safety.py"):
        full = "multi_robot_exploration." + name[:-3]
        module = types.ModuleType(full)
        module.__file__ = str(PKG / name)
        sys.modules[full] = module
        exec(compile(sources[name], module.__file__, "exec"), module.__dict__)
    guard = sys.modules["multi_robot_exploration.mr3_motion_safety"]
    trackers = {name: guard.SettledTurnTracker() for name in ROBOTS}
    odometry = {}
    counts = {name: {"historical_decisions": 0, "qualified_prefixes": 0,
                     "new_rotation_opportunities": 0} for name in ROBOTS}
    examples = {name: [] for name in ROBOTS}
    windows = {name: [] for name in ROBOTS}
    errors = []
    input_digest = hashlib.sha256()
    input_bytes = 0
    epoch = None
    for line, raw in enumerate((args.episode / "motion_safety.jsonl").open("rb"), 1):
        input_digest.update(raw)
        input_bytes += len(raw)
        if not raw.endswith(b"\n"):
            raise ValueError("incomplete input")
        row = json.loads(raw)
        epoch = row["epoch"] if epoch is None else epoch
        assert row["epoch"] == epoch and row["record_sequence"] == line
        value = row["payload"]
        name = value.get("robot")
        if row["kind"] == "own_odom":
            trackers[name].observe(value["message"], value["input_sequence"])
            odometry[name] = (value["message"], value["input_sequence"])
        elif row["kind"] == "release":
            for tracker in trackers.values():
                tracker.release(round(value["stamp"] * 1e9))
        elif row["kind"] == "decision":
            clock = value["clock_ns"]
            counts[name]["historical_decisions"] += 1
            certificate = trackers[name].certificate(clock)
            if certificate is not None:
                counts[name]["qualified_prefixes"] += 1
            original = value["decision"]
            if (value["started"] and value["ready"] and value["own_state"] is not None
                    and value.get("request") is not None and original["reason"] in (
                        "clear", "peer_braking_nonclosing", "peer_uncertainty_envelope",
                        "linear_brake_preserve_requested_turn")):
                own = copy.deepcopy(value["own_state"])
                source, sequence = odometry[name]
                assert own["input_sequences"]["odom"] == sequence
                linear = source["twist"]["twist"]["linear"]
                own["planar_speed_mps"] = math.hypot(linear["x"], linear["y"])
                own["settled_turn"] = certificate
                request = value["request"]
                hypothetical = guard.guard_motion([request["v"], request["w"]], own,
                                                   value["received_peers"], clock / 1e9, epoch)
                rotation = (hypothetical.get("component_filter") or {}).get("rotation_check", {})
                settled = hypothetical if hypothetical["reason"] == "settled_turn_drift_reserve" else rotation
                if (settled.get("reason") == "settled_turn_drift_reserve"
                        and hypothetical["output"] != original["output"]):
                    assert hypothetical["output"][0] == original["output"][0] == 0.
                    counts[name]["new_rotation_opportunities"] += 1
                    check = settled["settled_turn_check"]
                    item = {"line": line, "clock_ns": clock, "decision_sequence": value["decision_sequence"],
                            "original_reason": original["reason"], "original_output": original["output"],
                            "hypothetical_reason": hypothetical["reason"], "hypothetical_output": hypothetical["output"],
                            "raw_request": [request["v"], request["w"]],
                            "body_margin_m": settled["body_margin_m"],
                            "required_body_margin_m": check["required_body_margin_m"],
                            "reserve_slack_m": settled["body_margin_m"] - check["required_body_margin_m"],
                            "own_planar_speed_mps": own["planar_speed_mps"],
                            "zero_since_ns": certificate["zero_since_ns"],
                            "qualification_source_samples_ns": [r["source_ns"] for r in certificate["samples"]]}
                    if len(examples[name]) < 3:
                        examples[name].append(item)
                    if not windows[name] or clock - windows[name][-1]["end_ns"] > 20_000_000:
                        windows[name].append({"start_ns": clock, "end_ns": clock, "samples": 1,
                                              "min_reserve_slack_m": item["reserve_slack_m"]})
                    else:
                        win = windows[name][-1]
                        win["end_ns"] = clock
                        win["samples"] += 1
                        win["min_reserve_slack_m"] = min(win["min_reserve_slack_m"], item["reserve_slack_m"])
            # Only factual original linear target history is fed back. New angular
            # outputs were never executed; do not activate or claim their future plant.
            trackers[name].output(original["output"][0], clock, value["decision_sequence"])
    ordering = guard.SettledTurnTracker()
    ordering.output(0., 1_000_000_000, 1)
    ordering.output(0., 2_000_000_000, 2)
    rejected_clock = rejected_sequence = False
    try:
        ordering.output(0., 1_500_000_000, 3)
    except ValueError:
        rejected_clock = True
    try:
        ordering.output(0., 2_000_000_000, 2)
    except ValueError:
        rejected_sequence = True
    assert rejected_clock and rejected_sequence
    after = {name: sha((PKG / name).read_bytes()) for name in sources}
    before = {name: sha(raw) for name, raw in sources.items()}
    stable = before == after
    receipt = {"schema": "mr3-v8-historical-settled-turn-opportunity-v2", "passed": stable and not errors,
               "epoch": epoch, "sources_before": before, "sources_after": after, "sources_unchanged": stable,
               "original_input": {"path": str(args.episode / "motion_safety.jsonl"), "bytes": input_bytes,
                                  "sha256": input_digest.hexdigest()},
               "robot_counts": counts, "first_examples": examples, "opportunity_windows": windows,
               "ordering_cpu_checks": {"backward_output_clock_rejected": rejected_clock,
                                       "nonincreasing_output_sequence_rejected": rejected_sequence},
               "release_prefix_restarted": True, "errors": errors, "wall_sec": time.monotonic() - started,
               "scope": "Full original odom/linear-target histories plus hypothetical branch queries at historical inputs. No hypothetical angular output fed to physics or future tracker activation; windows are opportunity observations, not a replayed new closed-loop trajectory or proof of physical invariant/movement."}
    target = args.output_directory / "receipt.json"
    target.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": receipt["passed"], "counts": counts,
                      "first_times_ns": {n: (examples[n][0]["clock_ns"] if examples[n] else None) for n in ROBOTS},
                      "wall_sec": receipt["wall_sec"], "receipt": str(target)}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
