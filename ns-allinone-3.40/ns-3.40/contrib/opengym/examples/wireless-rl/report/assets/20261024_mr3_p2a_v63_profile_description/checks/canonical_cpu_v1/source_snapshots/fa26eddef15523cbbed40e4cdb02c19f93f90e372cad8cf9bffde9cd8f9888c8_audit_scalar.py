"""Versioned scalar audit correcting only same-boundary switch attribution.

The immutable P1C scalar-v3 auditor still runs unchanged. Its other assertions
remain mandatory. Actual switch cancellations are additionally bound to their
accepted replacement commands, rather than assigned to an earlier reward by an
inclusive simulation timestamp shared with the next action.
"""

import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re


METHOD = "mr3-scalar-command-bound-switch-v4"
ORIGINAL_SCALAR_SHA256 = "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665"
ORIGINAL_SCALAR_PATH = "report/assets/20261015_mr3_p1c/reward_gate_audit_v3.py"
SWITCH_WEIGHT = .01
ROBOTS = ("tb1", "tb2", "tb3")
OLD_SWITCH_ASSERTION = re.compile(
    r"step ([1-9][0-9]*): switch penalty differs from actual protocol events")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def ns(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            "invalid causal switch timestamp")
    result = round(value * 10**9)
    require(abs(value * 10**9 - result) < .001,
            "causal switch timestamp is not an integer nanosecond")
    return result


def load_rows(path):
    path = Path(path)
    if not path.exists():
        path = path.with_name(path.name + ".gz")
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
        return [json.loads(line) for line in source if line.strip()]


def causal_switch_deltas(transitions, events, epoch):
    """Prove each synchronous switch cancel from its command and old ownership.

    ``switch_pending`` is emitted for a GOAL that owns an active old goal and
    invokes ``_cancel(..., reason='switch')`` during that command's submit path.
    Replacement goal sending/acceptance occurs later and is not the charge
    point. No source timestamp, reward, candidate or input record is rewritten.
    """
    require(transitions and transitions[0].get("kind") == "reset", "missing causal reset")
    commands, deltas = {}, [0] * (len(transitions) - 1)
    previous = transitions[0]["snapshot"]
    for sequence, row in enumerate(transitions[1:], 1):
        require(row.get("kind") == "step", "unexpected causal transition kind")
        info, reward = row["info"], row["info"]["reward_diagnostics"]
        require(reward.get("epoch") == epoch and reward.get("sequence") == sequence,
                "causal switch reward sequence/epoch mismatch")
        if info.get("action_submitted", True) is False:
            require(info.get("terminal_observation_reused") is True and row["terminated"]
                    and not row["truncated"] and row["snapshot"] == previous,
                    "unproven no-action record in causal switch audit")
        else:
            command = info["command"]
            command_id = command.get("command_id")
            action = command.get("action")
            require(type(command_id) is int and command_id >= 0 and command_id not in commands,
                    "duplicate/invalid causal command identity")
            require(command.get("epoch") == previous.get("epoch") == epoch
                    and command.get("observation_sequence") == previous.get("sequence")
                    and command.get("observation_digest") == previous.get("digest")
                    and ns(command.get("created_at")) == ns(reward.get("step_start")),
                    "causal command is not bound to its actual source observation/step")
            require(type(action) is int and 0 <= action < 1000
                    and previous["joint_action_mask"][action] is True,
                    "causal command violates its saved joint mask")
            commands[command_id] = {"sequence": sequence, "command": command,
                                    "snapshot": previous}
        previous = row["snapshot"]
    seen_receipts, seen_goals, pending, bindings = set(), set(), {}, []
    current_command = None
    for line, event in enumerate(events, 1):
        require(isinstance(event, dict) and isinstance(event.get("payload"), dict),
                "malformed causal event envelope")
        kind, payload = event.get("kind"), event.get("payload", {})
        if kind in ("action", "action_rejected"):
            identity = payload.get("command_id")
            require(event.get("epoch") == epoch and type(identity) is int
                    and identity in commands and identity not in seen_receipts,
                    "unbound/duplicate causal action receipt")
            record = commands[identity]
            command, snapshot = record["command"], record["snapshot"]
            require(payload.get("observation_sequence") == command["observation_sequence"]
                    and ns(event.get("stamp")) == ns(command["created_at"]),
                    "causal action receipt belongs to a late/wrong step")
            seen_receipts.add(identity)
            current_command = identity
            if kind == "action_rejected":
                continue
            choices = [command["action"] // 100, command["action"] // 10 % 10,
                       command["action"] % 10]
            require(payload.get("action") == command["action"]
                    and payload.get("choices") == choices
                    and payload.get("observation_digest") == snapshot["digest"]
                    and payload.get("candidate_version") == snapshot["candidate_version"]
                    and set(payload.get("results", {})) == set(ROBOTS),
                    "causal accepted action content/source differs")
            robots = {robot["name"]: robot for robot in snapshot["robots"]}
            for robot, choice in zip(ROBOTS, choices):
                if payload["results"][robot] != "switch_pending":
                    continue
                navigation = robots[robot]["navigation"]
                old_goal = navigation.get("goal_id")
                require(choice < 8 and navigation.get("phase") == "active"
                        and navigation.get("owned") is True and isinstance(old_goal, str)
                        and old_goal.startswith(epoch + ":" + robot + ":"),
                        "switch_pending lacks a GOAL and observed active old-goal ownership")
                key = (robot, old_goal)
                require(key not in pending and old_goal not in seen_goals,
                        "duplicate pending switch for an old goal")
                pending[key] = {"step_sequence": record["sequence"], "command_id": identity,
                                "observation_sequence": command["observation_sequence"],
                                "robot": robot, "old_goal_id": old_goal,
                                "action_event_line": line, "stamp": event["stamp"]}
        elif (kind == "protocol" and payload.get("type") == "cancel_goal"
              and payload.get("reason") == "switch"):
            old_goal, robot = payload.get("goal_id"), payload.get("robot")
            require(event.get("epoch") == epoch and old_goal not in seen_goals,
                    "duplicate/cross-epoch actual switch cancellation")
            key = (robot, old_goal)
            require(key in pending, "unbound actual switch cancellation")
            binding = pending.pop(key)
            require(binding["command_id"] == current_command
                    and line > binding["action_event_line"]
                    and ns(event.get("stamp")) == ns(binding["stamp"])
                    and payload.get("epoch", epoch) == epoch
                    and ns(payload.get("stamp", event["stamp"])) == ns(binding["stamp"]),
                    "switch cancellation is late or assigned to a wrong command/step")
            seen_goals.add(old_goal)
            deltas[binding["step_sequence"] - 1] += 1
            bindings.append({**binding, "cancel_event_line": line})
    require(seen_receipts == set(commands), "submitted causal command lacks action receipt")
    require(not pending, "accepted switch_pending lacks its actual switch cancellation")
    return {"method": METHOD, "deltas": deltas, "bindings": bindings,
            "unique_actual_switches": len(bindings),
            "counting_point": "actual cancel_goal(reason=switch), not replacement send/accept"}


def verify_switch_rewards(transitions, causal):
    for sequence, (row, expected) in enumerate(zip(transitions[1:], causal["deltas"]), 1):
        reward = row["info"]["reward_diagnostics"]
        count = reward.get("goal_switches_delta")
        require(type(count) is int and count >= 0 and count == expected,
                f"step {sequence}: causal switch count differs from actual command-bound cancels")
        weight = reward.get("reward_weights", {}).get("switch")
        penalty = reward.get("reward_terms", {}).get("switch")
        require(type(weight) in (int, float) and weight == SWITCH_WEIGHT,
                f"step {sequence}: declared switch weight differs from frozen .01")
        require(type(penalty) in (int, float) and math.isfinite(penalty)
                and math.isclose(penalty, -SWITCH_WEIGHT * expected, rel_tol=0., abs_tol=1e-12),
                f"step {sequence}: switch penalty differs from frozen weight times causal count")


def same_boundary_corrections(transitions, events, causal):
    """Explain only the original inclusive-end attribution errors by exact ties."""
    start = transitions[0]["snapshot"]["source_stamp"]
    previous_cumulative, previous_future = 0, 0
    corrections = {}
    for sequence, row in enumerate(transitions[1:], 1):
        end = row["info"]["reward_diagnostics"]["effective_step_end"]
        cumulative = len({event["payload"]["goal_id"] for event in events
                          if start <= event["stamp"] <= end and event["kind"] == "protocol"
                          and event["payload"].get("type") == "cancel_goal"
                          and event["payload"].get("reason") == "switch"})
        future = sum(binding["step_sequence"] > sequence and ns(binding["stamp"]) == ns(end)
                     for binding in causal["bindings"])
        old_delta = cumulative - previous_cumulative
        expected = causal["deltas"][sequence - 1]
        if old_delta != expected and old_delta == expected + future - previous_future:
            corrections[sequence] = {"original_timestamp_delta": old_delta,
                                     "command_bound_delta": expected,
                                     "future_command_switches_at_end": future,
                                     "previous_end_future_command_switches": previous_future}
        previous_cumulative, previous_future = cumulative, future
    return corrections


def load_original():
    path = Path(__file__).resolve().parents[1] / ORIGINAL_SCALAR_PATH
    require(hashlib.sha256(path.read_bytes()).hexdigest() == ORIGINAL_SCALAR_SHA256,
            "immutable original scalar-v3 helper SHA mismatch")
    spec = importlib.util.spec_from_file_location("mr3_original_scalar_v3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_episode(directory, freeze, *, original=None):
    """Run every original gate and replace only independently proved tie errors."""
    original = load_original() if original is None else original
    result = copy.deepcopy(original.audit_episode(Path(directory), freeze))
    original_errors = list(result["errors"])
    new_errors, replaced, causal, corrections = [], [], None, {}
    try:
        transitions = load_rows(Path(directory) / "transitions.jsonl")
        events = load_rows(Path(directory) / "adapter.jsonl")
        causal = causal_switch_deltas(transitions, events, result["epoch"])
        verify_switch_rewards(transitions, causal)
        corrections = same_boundary_corrections(transitions, events, causal)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        new_errors.append("causal switch gate: " + str(error))
    retained = []
    for error in original_errors:
        match = OLD_SWITCH_ASSERTION.fullmatch(error)
        if not new_errors and match and int(match.group(1)) in corrections:
            replaced.append({"original_error": error,
                             **corrections[int(match.group(1))]})
        else:
            retained.append(error)
    result.update(scalar_method=METHOD, original_scalar_sha256=ORIGINAL_SCALAR_SHA256,
                  original_scalar_path=ORIGINAL_SCALAR_PATH, original_errors=original_errors,
                  replaced_original_assertions=replaced, causal_switch=causal,
                  causal_switch_errors=new_errors, errors=retained + new_errors,
                  original_helper_modified=False)
    result["passed"] = not result["errors"]
    return result
