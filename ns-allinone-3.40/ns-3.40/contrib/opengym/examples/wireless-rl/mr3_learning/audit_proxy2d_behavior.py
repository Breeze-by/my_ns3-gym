"""Independent full-duration proxy behavior consumer; no world or learner runs.

Scientific responses are recalculated with the frozen original ProxyReward,
truth/quality functions and RewardLedger. Tensor/candidate replay credit remains
exactly the preceding independent interface audit's verified prefix.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import inspect
import io
import json
import math
from pathlib import Path
import re
import statistics
import sys

from .audit_proxy2d import (ROOT, PURE, ERRORS, canonical, parse, process_identity,
                            require, verify_run_sources)
from .proxy2d_codec import decode_arrays


ROBOTS = ("tb1", "tb2", "tb3")
CELLS = (("open", 101), ("rooms", 101), ("corridors", 101))
SPEC = {"schema": "mr3-proxy2d-activity-spec-v1", "kind": "full_behavior", "groups": [3],
        "cells": [list(cell) for cell in CELLS], "worker_cells": [[[list(cell)] for cell in CELLS]],
        "steps_per_episode": 300, "max_attempts": 900, "activity_seconds": 3600}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class BoundFiles:
    def __init__(self, directory):
        self.directory, self.files = Path(directory).resolve(), {}

    def read(self, path):
        path = Path(path).resolve()
        require(path.is_relative_to(self.directory), "behavior input escaped its current run")
        raw = path.read_bytes()
        require(self.files.setdefault(path, raw) == raw, "input changed between reads: " + str(path))
        return raw

    def json(self, path):
        return parse(self.read(path))

    def rows(self, path):
        raw = self.read(path)
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            for number, line in enumerate(stream, 1):
                value = parse(line)
                require(isinstance(value, dict), "journal row is not an object")
                yield number, value

    def verify(self):
        require(all(path.read_bytes() == raw for path, raw in self.files.items()),
                "current-run originals changed during behavior consumption")

    def index(self):
        return [{"path": path.relative_to(self.directory).as_posix(), "bytes": len(raw), "sha256": sha(raw)}
                for path, raw in sorted(self.files.items())]


def reward_factory(scene, epoch):
    # Import only inside the source-bound system ROS consumer. These modules
    # define helpers/classes; no ROS Node or ProxyWorld is instantiated.
    from multi_robot_exploration.mr3_proxy2d_reward import ProxyReward
    for name in ("mr3_proxy2d_reward", "mr3_reward", "mr3_episode", "mr3_task_contract", "task_evaluator"):
        module = sys.modules["multi_robot_exploration." + name]
        require(Path(inspect.getfile(module)).resolve().read_bytes() == (PURE / (name + ".py")).read_bytes(),
                "imported scientific module differs from the frozen source: " + name)
    return ProxyReward(scene, epoch)


def snapshot_digest(snapshot):
    return sha(canonical({key: value for key, value in snapshot.items() if key != "digest"}))


def actor_inputs(bound, episode, row):
    ref = row["actor_input_ref"]
    relative = Path(ref["path"])
    require(not relative.is_absolute() and relative.parts[0] == "inputs", "invalid actor input reference")
    raw = bound.read(episode / relative)
    payload = gzip.decompress(raw)
    value = parse(payload)
    require(canonical(value) == payload and sha(payload) == ref["sha256"]
            and relative.name == ref["sha256"] + ".json.gz", "actor input canonical bytes differ")
    require(snapshot_digest(row["snapshot"]) == row["snapshot"]["digest"], "saved snapshot digest differs")
    return value, {"input_encoded_sha256": sha(raw), "input_canonical_sha256": sha(payload),
                   "input_bytes": len(raw), "snapshot_digest": row["snapshot"]["digest"],
                   "tensor_proofs": row["tensor_proofs"], "input_path": str((episode / relative).resolve())}


def protocol_summary(bound, episode, epoch):
    kinds, events, accepted = Counter(), Counter(), {name: {} for name in ROBOTS}
    previous = -1
    for _, row in bound.rows(episode / "protocol.jsonl.gz"):
        clock = row["clock_ns"]
        require(row["epoch"] == epoch and type(clock) is int and clock >= previous, "protocol identity/clock regressed")
        previous = clock
        kinds[row["kind"]] += 1
        if row["kind"] == "dispatcher_event":
            event = row["event"]
            require(event["epoch"] == epoch and event["robot"] in ROBOTS, "dispatcher event identity differs")
            events[event["type"]] += 1
        elif row["kind"] == "proxy_delivery":
            envelope = row["envelope"]
            require(envelope["epoch"] == epoch and envelope["source"] in ROBOTS, "protocol envelope identity differs")
            payload = envelope["payload"]
            if envelope["stream"] == "receipt" and payload.get("type") == "accept" and payload.get("value") is True:
                goal = payload["goal_id"]
                require(isinstance(goal, str) and goal, "accepted goal has no identity")
                accepted[envelope["source"]].setdefault(goal, clock)
    return {"row_kinds": dict(kinds), "dispatcher_events": dict(events),
            "unique_accepted_goals": {name: len(goals) for name, goals in accepted.items()}}, accepted


def terminal_assessment(reset_time, final_row, expected, unsafe, *, closure_time=None):
    elapsed = round(final_row["snapshot"]["source_stamp"] * 1e9) - round(reset_time * 1e9)
    reason = expected["reason"]
    coverage_closed_before_deadline = (closure_time is not None
        and round(closure_time * 1e9) - round(reset_time * 1e9) < 300_000_000_000)
    complete = (expected["terminated"] is True and expected["truncated"] is False
                and ((reason == "timeout" and elapsed == 300_000_000_000)
                     or (reason == "coverage_reached" and 0 <= elapsed < 300_000_000_000
                         and coverage_closed_before_deadline and expected.get("proxy_task_success") is True)))
    return {"elapsed_ns": elapsed, "reason": reason, "full_task_terminal": bool(complete),
            "unsafe_observed": sorted(set(unsafe)),
            "coverage_closed_before_deadline": coverage_closed_before_deadline if reason == "coverage_reached" else None,
            "proxy_task_success": bool(complete and not unsafe and reason == "coverage_reached"
                                       and expected.get("proxy_task_success") is True)}


def replay_evaluator(records, evaluator, returns, reset_row, params_for_row, accepted, epoch):
    """Recalculate every saved operation, retaining a real failure and counts."""
    result = {"raw_operation_counts": {}, "recomputed_operation_counts": {}, "errors": [],
              "recomputed_advance_count": 0, "trace_matched_advance_count": 0,
              "closed": False, "timeline": [], "unsafe_observed": [], "same_clock_acceptance_boundaries": []}
    raw_counts, verified = Counter(), Counter()
    initialized, failed, previous_check_ns, start_ns = False, False, None, None
    previous_paths = {name: 0. for name in ROBOTS}
    try:
        for number, row in records:
            operation = row.get("operation")
            raw_counts[str(operation)] += 1
            if failed:
                continue
            try:
                require(not result["closed"], "private evaluator record after close")
                fields = decode_arrays(row["request"])
                response = row["response"]
                require(response.get("ok") is True, "actual private evaluator failure retained: " + str(response))
                require(operation in ("initialize", "check", "inspect", "advance", "close"), "unknown evaluator operation")
                require(initialized or operation == "initialize", "evaluator did not initialize first")
                if operation == "initialize":
                    require(not initialized, "private evaluator initialized twice")
                    initialized = True
                    start_ns = round(fields["start_time"] * 1e9)
                physical = fields.get("physical_state")
                if physical is not None:
                    now_ns = physical["time_ns"]
                    require(type(now_ns) is int and physical.get("native_contact_monitoring") is False,
                            "private state changed its proxy clock/contact scope")
                    paths, contacts = physical["path_lengths"], physical["collision_events"]
                    require(set(paths) == set(ROBOTS) and type(contacts) is int and contacts >= 0
                            and len(physical["contact_events"]) == contacts, "private physical counters differ")
                    require(all(type(paths[name]) in (int, float) and math.isfinite(paths[name])
                                and paths[name] >= previous_paths[name] for name in ROBOTS), "physical path regressed")
                    previous_paths = dict(paths)
                    if contacts:
                        result["unsafe_observed"].append("proxy_contact")
                    if operation == "check":
                        require(round(fields["now"] * 1e9) == now_ns, "private check clock differs from its physical sample")
                        require(now_ns - (start_ns if previous_check_ns is None else previous_check_ns) == 20_000_000,
                                "private 20ms check clock has a gap")
                        previous_check_ns = now_ns
                        if fields.get("navigation_failed"):
                            result["unsafe_observed"].append("navigation_failure")
                if operation in ("initialize", "advance"):
                    index = 0 if operation == "initialize" else fields["sequence"]
                    target = reset_row if index == 0 else returns[index - 1]
                    params = params_for_row(target)
                    require(np_equal(fields["grid"], params["raw_grid"])
                            and fields["resolution"] == params["resolution"]
                            and list(fields["origin"]) == list(params["origin"]), "private reward map differs from actual actor boundary input")
                    if operation == "initialize":
                        require(round(fields["start_time"] * 1e9) == round(target["snapshot"]["source_stamp"] * 1e9),
                                "reward seq0 is not the reset boundary")
                    else:
                        require(fields["sequence"] == result["recomputed_advance_count"] + 1,
                                "private reward sequence is not contiguous")
                        require(round(fields["step_end"] * 1e9) == round(target["snapshot"]["source_stamp"] * 1e9)
                                == physical["time_ns"], "reward physical/snapshot endpoint differs")
                        require(previous_check_ns is not None and physical["time_ns"] <= previous_check_ns
                                <= physical["time_ns"] + 10_000_000_000,
                                "reward boundary lacks completed checks or its close drain exceeded10s")
                        goals = fields["goal_counts"]
                        captured = {robot["name"]: robot["navigation"]["accepted_goal_count"]
                                    for robot in target["snapshot"]["robots"]}
                        require(set(captured) == set(ROBOTS) and goals == captured,
                                "reward goal counts differ from the same captured actor boundary")
                        before = {name: sum(clock < physical["time_ns"] for clock in accepted[name].values()) for name in ROBOTS}
                        through = {name: sum(clock <= physical["time_ns"] for clock in accepted[name].values()) for name in ROBOTS}
                        require(all(before[name] <= goals[name] <= through[name] for name in ROBOTS),
                                "captured goal counts are outside delivered-receipt causal bounds")
                        if before != through:
                            result["same_clock_acceptance_boundaries"].append({"sequence": fields["sequence"],
                                "boundary_ns": physical["time_ns"], "strictly_before_counts": before,
                                "through_same_clock_counts": through, "captured_boundary_counts": goals})
                expected = {} if operation == "close" else getattr(evaluator, operation)(**fields)
                require(canonical(expected) == canonical(response["result"]), "private " + str(operation) + " response differs from independent recalculation")
                verified[operation] += 1
                if operation == "close":
                    result["closed"] = True
                elif operation in ("initialize", "advance"):
                    if operation == "advance":
                        result["recomputed_advance_count"] += 1
                    diagnostic = target["reward_diagnostics"]
                    require(canonical(diagnostic) == canonical(expected), "trace reward_diagnostics differs from independent evaluator")
                    require(all(target[key] == expected[key] for key in ("reward", "terminated", "truncated", "reason"))
                            and target["dt"] == expected["delta_sim_time"], "trace reward/terminal scalars differ")
                    if operation == "advance":
                        result["trace_matched_advance_count"] += 1
                        result["last_response"] = expected
                        result["last_physical_paths"] = dict(physical["path_lengths"])
                        result["last_goal_counts"] = dict(fields["goal_counts"])
                        result["timeline"].append({"sequence": fields["sequence"], "elapsed_sec": expected["elapsed_sim_time"],
                            "dt": expected["delta_sim_time"], "reward": expected["reward"],
                            "new_correct_free_cells": expected.get("new_correct_free_cells", 0),
                            "metrics": expected["metrics"], "physical_paths_m": dict(physical["path_lengths"]),
                            "accepted_goal_counts": dict(fields["goal_counts"])})
            except ERRORS as error:
                result["errors"].append(f"private row {number}: {error}")
                failed = True
    except ERRORS as error:
        result["errors"].append("private journal read: " + str(error))
    result.update(raw_operation_counts=dict(raw_counts), recomputed_operation_counts=dict(verified))
    result["unsafe_observed"] = sorted(set(result["unsafe_observed"]))
    return result


def np_equal(left, right):
    import numpy as np
    return isinstance(left, np.ndarray) and isinstance(right, np.ndarray) and left.dtype == right.dtype \
        and left.shape == right.shape and np.array_equal(left, right)


def prefix_statistics(actors, returns, replay):
    """Only the interface-verified prefix; candidate diagnostics are saved facts."""
    timeline, reasons = [], Counter()
    for row in actors:
        snapshot = row["snapshot"]
        diag, candidates = snapshot.get("diagnostics", {}), snapshot["candidates"]
        legal_goals = [sum(mask[:8]) for mask in snapshot["per_robot_action_mask"]]
        for entry in diag.get("mask_reasons", {}).get("per_robot", []):
            reasons.update(entry.keys())
        timeline.append({"elapsed_sec": snapshot["task_elapsed_sec"], "map_version": snapshot["map_version"],
            "valid_candidates": sum(candidate["valid"] for candidate in candidates),
            "reachable_candidates_by_robot": [sum(candidate["valid"] and candidate["reachable"][i]
                                                  for candidate in candidates) for i in range(3)],
            "legal_goal_actions_by_robot": legal_goals, "legal_joint_actions": sum(snapshot["joint_action_mask"]),
            "geometric_pool_size": diag.get("geometric_pool_size"), "candidate_truncated": diag.get("candidate_truncated"),
            "seed_rejections": [entry.get("seed_rejection_reason") for entry in diag.get("robot_seed_diagnostics", [])]})
    longest = {"zero_new_correct_cells_sec": 0., "zero_physical_translation_sec": 0., "no_legal_goal_sec": 0.}
    running, previous = dict.fromkeys(longest, 0.), {name: 0. for name in ROBOTS}
    matched = replay["timeline"][:len(returns)]
    for index, step in enumerate(matched):
        flags = {"zero_new_correct_cells_sec": step["new_correct_free_cells"] == 0,
                 "zero_physical_translation_sec": step["physical_paths_m"] == previous,
                 "no_legal_goal_sec": not any(timeline[index]["legal_goal_actions_by_robot"])}
        for key, flag in flags.items():
            running[key] = running[key] + step["dt"] if flag else 0.
            longest[key] = max(longest[key], running[key])
        previous = step["physical_paths_m"]
    costs = [(row["ended_wall_ns"] - attempt["started_wall_ns"]) / 1e9 for attempt, row in returns]
    thirds = []
    for index, name in enumerate(("early", "middle", "late")):
        values = costs[index * len(costs) // 3:(index + 1) * len(costs) // 3]
        thirds.append({"segment": name, "steps": len(values), "mean_wall_seconds": statistics.mean(values) if values else None,
                       "max_wall_seconds": max(values) if values else None})
    return {"actor_observations": len(actors), "verified_returns": len(returns), "candidate_map_timeline": timeline,
            "mask_reason_observation_counts": dict(reasons), "longest_observed_windows": longest,
            "step_wall_cost_thirds": thirds,
            "last_received_activity": ({} if not actors else
                {robot["name"]: {"activity": robot.get("activity"),
                    "accepted_goal_count": robot.get("navigation", {}).get("accepted_goal_count")}
                 for robot in actors[-1]["snapshot"].get("robots", [])}),
            "scope": "saved verified-prefix candidate diagnostics; only base reset/first/last construction replays; "
                     "zero translation permits rotation; KEEP may continue a goal; no inference about RL learnability"}


def inspect_episode(bound, episode, descriptor, base, evaluator_factory, freeze):
    result = {"directory": str(episode), "errors": [], "passed": False, "proxy_task_success": False,
              "raw_counts": {}, "base_verified_credit": {key: base.get(key, 0) for key in (
                  "verified_action_count", "verified_uniform_action_count", "verified_actor_record_count", "verified_step_return_count")}}
    try:
        for filename in ("episode.json", "trace.jsonl.gz", "private_evaluator.jsonl.gz", "protocol.jsonl.gz", "backend_summary.json"):
            try:
                bound.read(episode / filename)
            except ERRORS as error:
                result["errors"].append("input binding: " + str(error))
        for path in sorted((episode / "inputs").glob("*.json.gz")):
            bound.read(path)
        metadata = bound.json(episode / "episode.json")
        epoch, scene, seed = metadata["epoch"], descriptor["scene"], descriptor["seed"]
        require(all(type(metadata[key]) is type(descriptor[key]) and metadata[key] == descriptor[key]
                    for key in ("scene", "seed", "env_id", "episode_index"))
                and metadata["freeze"] == freeze and metadata["profile_enabled"] is False,
                "episode metadata differs from fixed assignment/freeze")
        rows = [row for _, row in bound.rows(episode / "trace.jsonl.gz")]
        require(base.get("trace_sha256") in (None, sha(bound.files[episode / "trace.jsonl.gz"])), "base audit bound another trace")
        result["raw_counts"] = dict(Counter(row.get("event") for row in rows))
        actors = [row for row in rows if row["event"] in ("reset", "step_return")]
        returns = [row for row in rows if row["event"] == "step_return"]
        require(actors and actors[0]["event"] == "reset", "behavior trace lacks its reset")
        require(all(row["epoch"] == epoch for row in rows), "mixed trace epoch")
        inputs, credit = {}, 0
        for index, row in enumerate(actors):
            encoded, proof = actor_inputs(bound, episode, row)
            # All original input bytes are bound above; scalar reward replay
            # needs only the delivered fused map, not six extra map copies.
            inputs[row["snapshot"]["sequence"]] = {key: encoded[key] for key in ("raw_grid", "resolution", "origin")}
            if index < len(base.get("actor_records", [])):
                record = base["actor_records"][index]
                require(all(record[key] == value for key, value in proof.items()), "base actor/input/tensor credit does not bind this trace")
                credit += 1
        result["bound_actor_input_count"] = len(inputs)
        result["base_actor_credit_matched"] = credit
        protocol, accepted = protocol_summary(bound, episode, epoch)
        result["protocol_summary"] = protocol
        replay = replay_evaluator(bound.rows(episode / "private_evaluator.jsonl.gz"), evaluator_factory(scene, epoch),
            returns, actors[0], lambda row: decode_arrays(inputs[row["snapshot"]["sequence"]]), accepted, epoch)
        result["evaluator_recalculation"] = replay
        result["errors"].extend(replay["errors"])
        count = min(base.get("verified_step_return_count", 0), max(0, credit - 1))
        settled, pending = [], None
        for row in rows:
            if row["event"] == "step_attempt":
                pending = row
            elif row["event"] == "step_return":
                settled.append((pending, row))
                pending = None
        result["verified_prefix_statistics"] = prefix_statistics(actors[:credit], settled[:count], replay)
        backend = bound.json(episode / "backend_summary.json")
        result["backend_closure"] = backend
        unsafe = list(replay["unsafe_observed"])
        if backend.get("navigation_failed"):
            unsafe.append("backend_navigation_failure")
        if protocol["dispatcher_events"].get("protocol_failure", 0):
            unsafe.append("protocol_failure")
        if returns and replay.get("last_response"):
            matched = replay["trace_matched_advance_count"]
            final = terminal_assessment(actors[0]["snapshot"]["source_stamp"], returns[matched - 1], replay["last_response"], unsafe,
                                        closure_time=backend["final_physical_time"])
            result["terminal_assessment"] = final
            result["terminal_assessment_is_final"] = matched == len(returns)
            result["last_recomputed_metrics"] = replay["last_response"]["metrics"]
            result["last_recomputed_physical_paths_m"] = replay["last_physical_paths"]
            result["last_recomputed_accepted_goal_counts"] = replay["last_goal_counts"]
            if matched == len(returns):
                result["final_metrics"] = replay["last_response"]["metrics"]
                result["final_physical_paths_m"] = replay["last_physical_paths"]
                result["final_accepted_goal_counts"] = replay["last_goal_counts"]
            require(replay["recomputed_advance_count"] == replay["trace_matched_advance_count"] == len(returns)
                    and replay["closed"], "private evaluator replay/close is incomplete")
            require(final["full_task_terminal"], "full behavior ended without a real300s timeout or qualified early coverage terminal")
            require(not unsafe, "unsafe proxy observations retained: " + str(unsafe))
            require(backend["epoch"] == epoch and backend["returned_steps"] == len(returns)
                    and backend["navigation_closed"] is True and backend["evaluator_returncode"] == 0
                    and round(backend["final_snapshot_time"] * 1e9) == round(returns[-1]["snapshot"]["source_stamp"] * 1e9)
                    and 0 <= backend["closure_tail_seconds"] <= 10.
                    and round(backend["final_physical_time"] * 1e9) - round(backend["final_snapshot_time"] * 1e9)
                        == round(backend["closure_tail_seconds"] * 1e9), "backend closure/counter/physical tail differs")
            require(base.get("passed") is True and base.get("causal_validation_complete") is True
                    and count == len(returns) and credit == len(actors), "preceding interface audit is failed/incomplete; prefix credit retained")
            result.update(passed=not result["errors"], proxy_task_success=final["proxy_task_success"])
        else:
            result["errors"].append("no fully recalculated final transition")
    except ERRORS as error:
        result["errors"].append(str(error))
    return result


def audit_behavior(directory, freeze, *, evaluator_factory=reward_factory, source_validator=verify_run_sources):
    directory = Path(directory).resolve()
    bound = BoundFiles(directory)
    result = {"schema": "mr3-proxy2d-full-behavior-audit-v1", "directory": str(directory), "freeze": freeze,
              "consumer_identity": process_identity(__import__("os").getpid()), "passed": False, "errors": [],
              "qualification": False, "training_eligible": False, "native_credit": False, "episodes": [],
              "proxy_task_success": False, "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0,
              "scope": "isolated2D full-duration random-action behavior only; engineering completeness differs from task success; "
                       "no native/learned-policy/95percent reliability or RL learnability conclusion"}
    sources = {}
    try:
        require(isinstance(freeze, str) and re.fullmatch("[0-9a-f]{40}", freeze), "exact40-character source freeze required")
        summary = bound.json(directory / "capacity_summary.json")
        require(summary["freeze"] == freeze and canonical(summary["activity_spec"]) == canonical(SPEC)
                and summary["activity_kind"] == "full_behavior", "behavior summary freeze/fixed specification differs")
        require(all(type(summary[key]) is int and summary[key] == 0 for key in ("policy_calls", "gpu_calls", "optimizer_steps"))
                and all(summary[key] is False for key in ("qualification", "training_eligible", "native_credit")), "behavior acquired learning/qualification credit")
        proof, sources, _ = source_validator(summary["source_bindings"], freeze)
        result["source_bindings"] = proof
        try:
            base = bound.json(directory / "independent_audit.json")
            require(base["schema"] == "mr3-proxy2d-capacity-audit-v1" and Path(base["directory"]).resolve() == directory
                    and base["freeze"] == freeze and base["run_source_bindings"] == summary["source_bindings"],
                    "base interface audit source/path identity differs")
        except ERRORS as error:
            base = {}
            result["errors"].append("base interface audit unavailable: " + str(error))
        result["base_interface_audit"] = {key: base.get(key) for key in ("passed", "errors", "step_attempts", "step_returns", "verified_action_count",
            "verified_uniform_action_count", "verified_actor_record_count", "verified_step_return_count")}
        if base.get("passed") is not True or base.get("errors") != [] or base.get("bound_bytes_unchanged") is not True:
            result["errors"].append("preceding independent interface audit did not pass")
        planned = [entry for group in summary["groups"] for entry in group["episodes"]]
        require([group["workers"] for group in summary["groups"]] == [3], "full behavior must use exactly3 parallel environments")
        start, deadline, collection_start, collection_end = (summary[key] for key in (
            "activity_started_ns", "activity_deadline_ns", "collection_started_ns", "collection_deadline_ns"))
        group = summary["groups"][0]
        if not (all(type(value) is int for value in (start, deadline, collection_start, collection_end))
                and deadline - start == 3600 * 10**9 and start <= collection_start
                and collection_end - collection_start == 2100 * 10**9 and collection_end <= deadline - 120 * 10**9
                and group["wall_budget_seconds"] == 2100
                and group["deadline_ns"] == min(collection_end, group["started_ns"] + 2100 * 10**9)
                and group["started_ns"] <= group["ended_ns"] <= group["deadline_ns"]):
            result["errors"].append("full behavior wall reservation differs or was exceeded; partial evidence retained")
        expected = {(index, 1, scene, seed) for index, (scene, seed) in enumerate(CELLS)}
        if {(entry["env_id"], entry["episode_index"], entry["scene"], entry["seed"]) for entry in planned} != expected or len(planned) != 3:
            result["errors"].append("full behavior fixed three-cell inventory is incomplete/duplicated")
        base_by_path = {str(Path(entry["directory"]).resolve()): entry for entry in base.get("episodes", [])}
        for entry in planned:
            episode = Path(entry["directory"]).resolve()
            report = inspect_episode(bound, episode, entry, base_by_path.get(str(episode), {}), evaluator_factory, freeze)
            result["episodes"].append(report)
            result["errors"].extend(str(episode) + ": " + error for error in report["errors"])
        require(summary["step_attempts"] <= 900, "behavior exceeded900 attempted steps")
        result["raw_summary_counts"] = {key: summary[key] for key in ("step_attempts", "step_returns", "step_errors")}
        result["raw_trace_counts"] = {key: sum(entry["raw_counts"].get(event, 0) for entry in result["episodes"])
                                      for key, event in (("step_attempts", "step_attempt"), ("step_returns", "step_return"), ("step_errors", "step_error"))}
        require(result["raw_trace_counts"] == result["raw_summary_counts"], "summary raw counters differ from bound traces")
        result["passed"] = len(result["episodes"]) == 3 and all(entry["passed"] for entry in result["episodes"]) and not result["errors"]
        result["proxy_task_success"] = result["passed"] and all(entry["proxy_task_success"] for entry in result["episodes"])
    except ERRORS as error:
        result["errors"].append(str(error))
    try:
        bound.verify()
        require(all(path.read_bytes() == raw for path, raw in sources.items()), "frozen source bytes changed during behavior consumption")
        result["bound_bytes_unchanged"] = True
    except ERRORS as error:
        result["bound_bytes_unchanged"] = False
        result["errors"].append(str(error))
        result["passed"] = result["proxy_task_success"] = False
    result["input_bindings"] = bound.index()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "preserve the original behavior report")
    result = audit_behavior(args.directory, args.freeze)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
