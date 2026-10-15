#!/usr/bin/env python3
"""Read-only scalar/receipt audit; never imports ROS, maps, or starts simulation.

Usage: python3 /tmp/mr3_p1c_reward_gate_audit.py RUN_DIRECTORY --freeze FULL_SHA
Spatial first-cell uniqueness is established by boolean-mask unit tests, not
inferred from scalar logs. This checks the native ledger arithmetic and repeated
identical map payloads, exact physics receipts, reset bindings, and clean closure.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def rows(path):
    if not path.exists() and path.suffix != ".gz":
        path = path.with_name(path.name + ".gz")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def close(left, right):
    return math.isclose(left, right, rel_tol=0., abs_tol=1e-7)


def digest(snapshot):
    value = {key: value for key, value in snapshot.items() if key != "digest"}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def audit_episode(directory, freeze):
    errors = []

    def require(condition, description):
        if not condition:
            errors.append(description)

    metadata = load(directory / "metadata.json")
    supervisor = load(directory / "supervisor_metadata.json")
    epoch = metadata["epoch"]
    require(metadata["freeze"] == freeze, "worker source freeze mismatch")
    require(supervisor["epoch"] == epoch, "supervisor epoch mismatch")
    require(supervisor["reset_kind"] == "complete_process_rebuild", "reset kind mismatch")
    require(metadata["environment"]["PYTHONNOUSERSITE"] == "1", "system Python isolation")
    transitions = rows(directory / "transitions.jsonl")
    resets = [row for row in transitions if row["kind"] == "reset"]
    require(len(resets) == 1 and transitions[0]["kind"] == "reset", "one initial reset")
    reset = resets[0]
    initial = reset["info"]["reward_diagnostics"]
    start = reset["snapshot"]["source_stamp"]
    require(reset["reward"] == 0. and reset["info"]["dt"] == 0., "reset zero reward/time")
    require(not reset["terminated"] and not reset["truncated"], "reset must be live")
    require(initial["sequence"] == 0 and initial["reset_bound"], "seq0 binding missing")
    require(close(initial["step_start"], start) and close(initial["effective_step_end"], start),
            "seq0 differs from initial physical boundary")
    require(initial["map_watermark"]["payload_sha256"] ==
            reset["info"]["watermarks"]["map_payload_sha256"], "seq0 map pairing")
    require(initial["map_watermark"]["received_stamp"] <= start + 1e-8,
            "seq0 map received after initial boundary")
    previous_end = previous_physical = start
    previous_sequence = reset["snapshot"]["sequence"]
    previous_digest = reset["snapshot"]["digest"]
    event_file = directory / "adapter.jsonl.gz"
    if not event_file.exists():
        event_file = directory / "adapter.jsonl"
    events = rows(event_file)
    require(all(event["epoch"] == epoch for event in events), "adapter event epoch")
    previous_switches = previous_rejects = 0
    newly_rewarded = 0
    initial_cells = initial["initial_correct_free_cells"]
    seen_maps = {initial["map_watermark"]["payload_sha256"]}
    term_sums = {}
    short_steps = repeated_maps = 0
    steps = [row for row in transitions if row["kind"] == "step"]
    for index, row in enumerate(transitions):
        snapshot = row["snapshot"]
        require(snapshot["epoch"] == epoch, f"row {index} cross epoch")
        require(snapshot["digest"] == digest(snapshot), f"row {index} corrupt snapshot digest")
    for sequence, row in enumerate(steps, 1):
        info, snapshot = row["info"], row["snapshot"]
        reward = info["reward_diagnostics"]
        prefix = f"step {sequence}: "
        require(reward["epoch"] == epoch and reward["sequence"] == sequence,
                prefix + "reward sequence/epoch")
        require(close(reward["step_start"], previous_end), prefix + "noncontiguous ledger")
        end = reward["effective_step_end"]
        physical_dt = snapshot["source_stamp"] - previous_physical
        dt = end - previous_end
        require(close(dt, info["dt"]) and close(dt, reward["delta_sim_time"]),
                prefix + "reward dt")
        require(close(physical_dt, info["physical_dt"]), prefix + "physical dt")
        require(snapshot["sequence"] > previous_sequence, prefix + "snapshot sequence")
        command = info["command"]
        require(command["observation_sequence"] == previous_sequence and
                command["observation_digest"] == previous_digest and
                close(command["created_at"], previous_physical),
                prefix + "action observation binding")
        require(row["terminated"] == reward["terminated"] and
                row["truncated"] == reward["truncated"] and
                not (row["terminated"] and row["truncated"]), prefix + "end flags")
        require(0. <= dt <= physical_dt + 1e-7, prefix + "reward time exceeds physical time")
        require(0. < physical_dt <= 1. + 1e-7, prefix + "physical step range")
        if row["terminated"]:
            short_steps += int(dt < 1. - 1e-7)
            require(physical_dt - dt <= .020001, prefix + "terminal detection lag >20ms")
            require(reward["map_pairing_scope"] == "terminal_evaluator_frozen_before_drain",
                    prefix + "terminal pairing scope")
        else:
            require(close(dt, 1.) and close(physical_dt, 1.),
                    prefix + "ordinary fixed one-second dt")
            require(reward["expected_map_paired"], prefix + "ordinary map not paired")
            require(reward["map_watermark"]["payload_sha256"] ==
                    info["watermarks"]["map_payload_sha256"], prefix + "ordinary map SHA")
        require(reward["expected_actor_map_sha256"] ==
                info["watermarks"]["map_payload_sha256"], prefix + "actor watermark SHA")
        require(close(sum(reward["reward_terms"].values()), row["reward"]), prefix + "term sum")
        require(close(row["reward"], reward["reward"]), prefix + "reward transport")
        applicable_events = [event for event in events if start <= event["stamp"] <= end]
        switches = len({event["payload"]["goal_id"] for event in applicable_events
                        if event["kind"] == "protocol" and
                        event["payload"].get("type") == "cancel_goal" and
                        event["payload"].get("reason") == "switch"})
        rejects = sum(event["kind"] == "action_rejected" for event in applicable_events)
        require(reward["goal_switches_delta"] == switches - previous_switches,
                prefix + "switch penalty differs from actual protocol events")
        require(reward["rejected_actions_delta"] == rejects - previous_rejects,
                prefix + "reject penalty differs from actual protocol events")
        previous_switches, previous_rejects = switches, rejects
        new_cells = reward["new_correct_free_cells"]
        newly_rewarded += new_cells
        require(new_cells >= 0 and reward["rewarded_correct_free_cells"] == newly_rewarded,
                prefix + "first-cell cumulative arithmetic")
        require(initial_cells + newly_rewarded <= reward["truth_free_cell_count"],
                prefix + "rewarded area exceeds truth denominator")
        expected_coverage = (reward["reward_weights"]["coverage"] * new_cells /
                             reward["truth_free_cell_count"])
        require(close(reward["reward_terms"]["coverage"], expected_coverage),
                prefix + "coverage scale")
        map_hash = reward["map_watermark"]["payload_sha256"]
        if map_hash in seen_maps:
            repeated_maps += 1
            require(new_cells == 0, prefix + "identical map payload rewarded twice")
        seen_maps.add(map_hash)
        for key, value in reward["reward_terms"].items():
            term_sums[key] = term_sums.get(key, 0.) + value
        if reward["reason"] == "timeout":
            require(row["terminated"] and not row["truncated"] and
                    reward["elapsed_sim_time"] >= 300., prefix + "deadline semantics")
        if row["truncated"]:
            require(reward["reward_terms"]["failure"] == 0., prefix + "external cut task penalty")
        if row["terminated"] or row["truncated"]:
            require(sequence == len(steps), prefix + "transition after sealed ledger")
        previous_end, previous_physical = end, snapshot["source_stamp"]
        previous_sequence = snapshot["sequence"]
        previous_digest = snapshot["digest"]
    require(term_sums.get("coverage", 0.) <= 10. + 1e-7, "episode coverage reward >10")
    physics = rows(directory / "physics.jsonl")
    previous_receipt = None
    physics_counts = {}
    for receipt in physics:
        count = receipt["end_iterations"] - receipt["start_iterations"]
        physics_counts[count] = physics_counts.get(count, 0) + 1
        require(receipt["ok"] and receipt["epoch"] == epoch and receipt["paused"],
                "invalid physics receipt")
        require(receipt["end_time_ns"] - receipt["start_time_ns"] == count * 1000000,
                "non-1ms physics tick")
        require(count in (0, 1, 20), "unexpected physics quantum")
        if previous_receipt:
            require(previous_receipt["end_time_ns"] == receipt["start_time_ns"] and
                    previous_receipt["end_iterations"] == receipt["start_iterations"],
                    "noncontiguous physics receipts")
        previous_receipt = receipt
    summary = load(directory / "summary.json")
    shutdown = load(directory / "supervisor_shutdown.json")
    native = load(directory / "native_stop.json")
    require(summary["epoch"] == epoch and summary["transition_count"] == len(steps),
            "episode summary transition count")
    require(summary["closed"]["pending_goal_count"] == 0, "unclosed goal ownership")
    require(summary["launch_returncode"] == 0 and not summary["native_failures"],
            "native shutdown failure")
    require(native["returncode"] == 0 and native["server_clean_exit_recorded"], "native stop")
    require(shutdown["worker_returncode"] == 0 and not shutdown["forced_shutdown"] and
            not shutdown["failed_sample"] and not shutdown["remaining_owned_processes"] and
            not shutdown["remaining_owned_zombies"], "supervisor cleanup")
    evaluation = load(directory / (epoch + ".json"))
    final_reason = evaluation["termination_reason"]
    return {"directory": str(directory), "epoch": epoch, "scene": metadata["scene"],
            "seed": metadata["seed"], "pid_identity": supervisor["worker_identity"],
            "initial_cells": initial_cells, "newly_rewarded_cells": newly_rewarded,
            "transitions": len(steps), "terminal_short_steps": short_steps,
            "repeated_map_payload_steps": repeated_maps, "reward_term_sums": term_sums,
            "physical_quantum_counts": physics_counts, "evaluation_reason": final_reason,
            "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    args = parser.parse_args()
    episodes = []
    for metadata in sorted(args.directory.glob("worker*/episode*/supervisor_metadata.json")):
        try:
            episodes.append(audit_episode(metadata.parent, args.freeze))
        except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
            episodes.append({"directory": str(metadata.parent), "errors": [repr(error)]})
    epochs = [episode["epoch"] for episode in episodes if "epoch" in episode]
    identities = [(episode["pid_identity"]["pid"], episode["pid_identity"]["start_ticks"])
                  for episode in episodes if "pid_identity" in episode]
    reset_unique = len(set(epochs)) == len(epochs) and len(set(identities)) == len(identities)
    result = {"scope": "read-only native scalar/receipt checks, no spatial truth replay",
              "freeze": args.freeze, "episodes": episodes,
              "reset_epoch_and_pid_unique": reset_unique,
              "passed_scalar_checks": bool(episodes) and reset_unique and
              all(not episode["errors"] for episode in episodes)}
    print(json.dumps(result, indent=2))
    return 0 if result["passed_scalar_checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
