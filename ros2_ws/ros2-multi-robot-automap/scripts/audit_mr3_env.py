#!/usr/bin/env python3
"""Read-only P1C episode/benchmark audit; no ROS, simulator or policy execution.

PASS means the saved sampling contract is internally supported, never that a
scripted policy solved the 95% task. A declared killed-worker cell can pass its
cleanup check, but is explicitly excluded from complete-episode credit.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

from audit_mr3_adapter_probe import canonical_digest, native_stop_proof
from ros_smoke_test import native_launch_failures, validate_contact_reducer_summary


ROBOTS = ("tb1", "tb2", "tb3")
COMPONENTS = ("base", "lidar", "wheel_left", "wheel_right",
              "caster_back_left", "caster_back_right")
STATUS = {4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}
NS = 10**9


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def close(left, right, tolerance=1e-7):
    return number(left) and number(right) and abs(left - right) <= tolerance


def nanoseconds(value):
    require(number(value) and value >= 0, "invalid simulation stamp")
    result = round(value * NS)
    require(abs(value * NS - result) < .001, "stamp is not an integer nanosecond")
    return result


class Evidence:
    """Accumulate independent failures while preserving all evidence sections."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.errors = []
        self.hashes = {}

    def raw(self, name):
        path = self.directory / name
        data = (path.read_bytes() if path.exists() else
                gzip.decompress(path.with_suffix(path.suffix + ".gz").read_bytes()))
        self.hashes[name] = hashlib.sha256(data).hexdigest()
        return data

    def json(self, name):
        value = json.loads(self.raw(name))
        require(isinstance(value, dict), name + " must be an object")
        return value

    def rows(self, name):
        rows = [json.loads(line) for line in self.raw(name).splitlines()]
        require(all(isinstance(row, dict) for row in rows), name + " contains non-object")
        return rows

    def check(self, label, operation):
        try:
            return operation()
        except (OSError, ValueError, TypeError, KeyError, IndexError, EOFError,
                RuntimeError, AttributeError) as error:
            self.errors.append(label + ": " + str(error))
            return None


def audit_physics(rows, epoch, release_ns):
    """Prove actual contiguous ticks, including warmup and later closure ticks."""
    require(bool(rows), "no physical receipts")
    previous = None
    boundaries = set()
    for index, row in enumerate(rows, 1):
        require(row.get("epoch") == epoch and row.get("request_id") == f"q{index}",
                f"receipt {index} epoch/request id mismatch")
        require(row.get("ok") is True and row.get("paused") is True,
                f"receipt {index} not successful and paused")
        for key in ("start_time_ns", "end_time_ns", "start_iterations", "end_iterations",
                    "steps", "step_ns"):
            require(type(row.get(key)) is int and row[key] >= 0,
                    f"receipt {index} invalid integer {key}")
        require(row["step_ns"] == 1000000, "physical tick differs from 1ms")
        require(row["end_iterations"] - row["start_iterations"] == row["steps"]
                and row["end_time_ns"] - row["start_time_ns"] == row["steps"] * 1000000,
                f"receipt {index} tick/time delta mismatch")
        if previous is not None:
            require(row["start_iterations"] == previous["end_iterations"]
                    and row["start_time_ns"] == previous["end_time_ns"],
                    f"receipt {index} physical continuity gap")
        expected = 0 if index == 1 else 1 if row["start_time_ns"] < release_ns else 20
        require(row["steps"] == expected, f"receipt {index} unexpected warmup/quantum size")
        boundaries.add(row["end_time_ns"])
        previous = row
    require(release_ns in boundaries, "release lacks a physical receipt boundary")
    return {"receipt_count": len(rows), "first_time_ns": rows[0]["start_time_ns"],
            "last_time_ns": rows[-1]["end_time_ns"],
            "total_physical_ticks": sum(row["steps"] for row in rows)}


def validate_snapshot(snapshot, epoch):
    require(snapshot.get("epoch") == epoch, "snapshot cross-epoch")
    require(snapshot.get("schema") == "mr3-observation-v2", "unexpected observation schema")
    require(type(snapshot.get("sequence")) is int and snapshot["sequence"] > 0,
            "invalid observation sequence")
    require(snapshot.get("digest") == canonical_digest(
        {key: value for key, value in snapshot.items() if key != "digest"}),
        "saved snapshot digest mismatch")
    keys = ("epoch", "map_version", "sequence", "candidates", "path_maps")
    require(snapshot.get("candidate_version") == canonical_digest(
        {key: snapshot[key] for key in keys}), "candidate digest mismatch")
    require([robot.get("name") for robot in snapshot["robots"]] == list(ROBOTS),
            "snapshot does not contain exactly tb1/tb2/tb3")
    require(len(snapshot["joint_action_mask"]) == 1000
            and all(type(flag) is bool for flag in snapshot["joint_action_mask"]),
            "invalid saved joint-action mask")


def audit_transitions(rows, physics, epoch, allow_incomplete=False):
    require(bool(rows) and rows[0].get("kind") == "reset", "missing initial reset")
    reset = rows[0]
    require(reset.get("reward") == 0 and reset.get("terminated") is False
            and reset.get("truncated") is False and reset["info"].get("dt") == 0,
            "reset must have zero dt/reward and no episode end")
    require(reset["info"].get("reset_kind") == "complete_process_rebuild",
            "reset does not declare full process rebuild")
    release = reset["info"]["release_time_ns"]
    require(type(release) is int and nanoseconds(reset["snapshot"]["source_stamp"]) == release,
            "release and reset physical snapshot differ")
    require(reset["info"]["initial_pause_time_ns"] == physics[0]["end_time_ns"],
            "initial pause receipt differs from reset diagnostic")
    boundaries = {row["end_time_ns"] for row in physics}
    previous, done = None, False
    state_sequence = -1
    total_reward = 0.
    terminal_exceptions = 0
    for index, row in enumerate(rows):
        require(not done, "transition follows terminated/truncated sample")
        require(row.get("kind") == ("reset" if index == 0 else "step"),
                "unexpected transition kind (close dt0 is not a training sample)")
        snapshot, info = row["snapshot"], row["info"]
        validate_snapshot(snapshot, epoch)
        require(info.get("epoch") == epoch, "transition info cross-epoch")
        end_ns = nanoseconds(snapshot["source_stamp"])
        require(end_ns in boundaries, "snapshot lacks physical paused boundary")
        watermark = info["watermarks"]
        require(re.fullmatch(r"[0-9a-f]{64}", watermark["map_payload_sha256"]) is not None,
                "invalid actor map watermark")
        require(type(watermark["state_sequence"]) is int
                and watermark["state_sequence"] > state_sequence,
                "state delivery sequence did not advance")
        state_sequence = watermark["state_sequence"]
        reward = info["reward_diagnostics"]
        require(reward.get("epoch") == epoch and reward.get("sequence") == index,
                "reward epoch/sequence mismatch; reset binding must be seq0")
        require(number(row.get("reward")) and close(row["reward"], reward.get("reward")),
                "reward payload and transition differ")
        require(type(row.get("terminated")) is bool and type(row.get("truncated")) is bool
                and not (row["terminated"] and row["truncated"]), "invalid ending flags")
        require(row["terminated"] == reward.get("terminated")
                and row["truncated"] == reward.get("truncated"), "reward ending flags differ")
        actor_sha = watermark["map_payload_sha256"]
        reward_sha = reward["map_watermark"]["payload_sha256"]
        if index == 0:
            require(reward.get("kind") == "reward_reset_binding"
                    and reward.get("reset_bound") is True and reward_sha == actor_sha
                    and close(reward.get("step_start"), snapshot["source_stamp"])
                    and close(reward.get("effective_step_end"), snapshot["source_stamp"])
                    and reward.get("delta_sim_time") == 0,
                    "seq0 reward ledger is not bound to the initial actor map/time")
        else:
            start = previous["snapshot"]["source_stamp"]
            physical_dt = snapshot["source_stamp"] - start
            dt = info.get("dt")
            require(snapshot["sequence"] > previous["snapshot"]["sequence"],
                    "observation sequence did not advance")
            require(close(info.get("physical_dt"), physical_dt), "physical dt diagnostic differs")
            require(close(reward.get("step_start"), start)
                    and close(reward.get("effective_step_end"), start + dt)
                    and close(reward.get("delta_sim_time"), dt), "reward time interval differs")
            require(close(reward.get("requested_step_end"), snapshot["source_stamp"]),
                    "reward request does not end at physical snapshot")
            if row["terminated"]:
                require(0 < physical_dt <= 1.0000001 and number(dt)
                        and 0 <= dt <= physical_dt + 1e-7
                        and physical_dt - dt <= .020001,
                        "terminal effective/physical dt exceeds one 20ms detection quantum")
                require(reward.get("map_pairing_scope") ==
                        "terminal_evaluator_frozen_before_drain",
                        "terminal reward lacks frozen-evaluator scope")
                terminal_exceptions += reward_sha != actor_sha
            else:
                require(close(physical_dt, 1.) and close(dt, 1.),
                        "normal/truncated sample is not exactly one second")
                require(reward_sha == actor_sha and reward.get("expected_map_paired") is True
                        and reward.get("map_pairing_scope") == "current_actor_map_paired",
                        "nonterminal reward map differs from actor watermark")
            require(reward.get("expected_actor_map_sha256") == actor_sha,
                    "reward request did not bind the actor map SHA")
            command = info["command"]
            require(command.get("epoch") == epoch and command.get("command_id") == index
                    and command.get("observation_sequence") == previous["snapshot"]["sequence"]
                    and command.get("observation_digest") == previous["snapshot"]["digest"]
                    and close(command.get("created_at"), start)
                    and close(command.get("expires_at"), start + 2.),
                    "command does not bind prior frozen observation and 2s TTL")
            require(type(command.get("action")) is int and 0 <= command["action"] < 1000,
                    "command action outside Discrete(1000)")
            terms = reward["reward_terms"]
            require(all(number(value) for value in terms.values())
                    and close(sum(terms.values()), row["reward"]), "reward terms do not sum")
            total_reward += row["reward"]
        done = row["terminated"] or row["truncated"]
        previous = row
    require(allow_incomplete or done, "complete episode has no terminal/truncated sample")
    return {"transition_count": len(rows) - 1, "complete": done,
            "release_time_ns": release, "reward_sum": total_reward,
            "sampled_physical_time_sec": (nanoseconds(rows[-1]["snapshot"]["source_stamp"])
                                          - release) / NS,
            "terminal_map_sha_exception_count": terminal_exceptions,
            "terminal_map_scope": "frozen evaluator map; later actor map is diagnostic only"}


def audit_protocol(rows, transitions, epoch, allow_incomplete=False):
    snapshots = {row["snapshot"]["sequence"]: row["snapshot"] for row in transitions}
    commands = {row["info"]["command"]["command_id"]: row["info"]["command"]
                for row in transitions[1:]}
    accepted, rejected, goals, native, results, canceled, positive = {}, {}, {}, {}, {}, {}, set()
    owners = {name: None for name in ROBOTS}
    accepted_at, protocol_terminals, keep = {}, {}, set()
    previous_time = -math.inf
    observed = set()
    for row in rows:
        require(row.get("epoch") == epoch and number(row.get("stamp"))
                and row["stamp"] >= previous_time, "adapter event epoch/time regression")
        now, kind, event = row["stamp"], row["kind"], row["payload"]
        previous_time = now
        if kind == "observation":
            validate_snapshot(event, epoch)
            if event["sequence"] in snapshots:
                require(event == snapshots[event["sequence"]], "saved actor snapshots differ")
                observed.add(event["sequence"])
        elif kind in ("action", "action_rejected"):
            command_id = event["command_id"]
            require(command_id in commands, "action receipt lacks sampled command")
            command = commands[command_id]
            require(event.get("observation_sequence") == command["observation_sequence"],
                    "action receipt observation identity mismatch")
            require(command_id not in accepted and command_id not in rejected,
                    "command accounted more than once")
            if kind == "action_rejected":
                require(bool(event.get("reason")), "action rejection lacks reason")
                rejected[command_id] = event
                continue
            snapshot = snapshots[command["observation_sequence"]]
            action = command["action"]
            choices = [action // 100, action // 10 % 10, action % 10]
            require(event.get("action") == action and event.get("choices") == choices
                    and event.get("observation_digest") == snapshot["digest"]
                    and event.get("candidate_version") == snapshot["candidate_version"]
                    and snapshot["joint_action_mask"][action] is True,
                    "accepted action does not replay from saved candidate/mask")
            require(set(event["results"]) == set(ROBOTS), "action lacks three receipts")
            for name, choice in zip(ROBOTS, choices):
                result = event["results"][name]
                require(result in (("sent", "switch_pending") if choice < 8 else
                                   ("kept",) if choice == 8 else ("waiting",)),
                        "action result does not match GOAL/KEEP/WAIT")
                if choice == 8:
                    keep.add((name, command_id))
            accepted[command_id] = event
        elif kind == "action_duplicate":
            require(accepted.get(event.get("command_id")) == event,
                    "duplicate action is not an identical cached receipt")
        elif kind == "protocol":
            event_type, name, goal_id = event["type"], event["robot"], event.get("goal_id")
            require(name in owners, "unknown protocol robot")
            if event_type == "send_goal":
                command_id = event["command_id"]
                require(command_id in accepted, "protocol goal lacks accepted command")
                action = accepted[command_id]
                choice = action["choices"][ROBOTS.index(name)]
                require(choice < 8 and (name, command_id) not in keep,
                        "KEEP/WAIT re-submitted a goal")
                require(owners[name] is None and goal_id not in goals,
                        "new goal before old owned terminal")
                require(goal_id == f"{epoch}:{name}:{command_id}", "goal identity mismatch")
                snapshot = snapshots[action["observation_sequence"]]
                target = snapshot["candidates"][choice]
                require(event["goal"] == {"x": target["x"], "y": target["y"]}
                        and event["observation_version"] == snapshot["sequence"],
                        "protocol goal differs from chosen saved candidate")
                owners[name], goals[goal_id] = goal_id, event
            elif event_type == "cancel_goal":
                require(owners[name] == goal_id and goal_id not in canceled,
                        "cancellation lacks unique owned goal")
                if event.get("reason") in ("wait", "switch"):
                    require(goal_id in accepted_at
                            and now >= accepted_at[goal_id] + 5. - 1e-7,
                            "discretionary cancellation violates 5s commitment")
                canceled[goal_id] = event
            elif event_type == "protocol_terminal":
                require(owners[name] == goal_id and goal_id not in protocol_terminals,
                        "protocol terminal lacks unique owned goal")
                require(event.get("status") in tuple(STATUS.values()) + ("REJECTED",),
                        "invalid protocol terminal")
                owners[name], protocol_terminals[goal_id] = None, event
            elif event_type == "protocol_failure":
                raise ValueError("protocol failure: " + str(event.get("reason")))
        elif kind == "native_send":
            goal_id = event["goal_id"]
            require(goal_id in goals and goal_id not in native, "unowned/duplicate native goal")
            prior = goals[goal_id]
            require(event.get("robot") == prior["robot"]
                    and event.get("command_id") == prior["command_id"]
                    and now < prior["expires_at"], "native goal identity or TTL mismatch")
            pose = event.get("pose", {})
            require(pose.get("frame_id") == "map"
                    and {key: pose.get(key) for key in ("x", "y")} == prior["goal"]
                    and pose.get("orientation") == [0., 0., 0., 1.]
                    and close(pose.get("stamp"), now),
                    "native goal coordinates/frame differ from saved candidate")
            native[goal_id] = event
        elif kind == "delivery":
            stamps = [event.get(key) for key in
                      ("source_stamp", "generated_stamp", "received_stamp")]
            require(all(number(value) for value in stamps)
                    and 0 <= stamps[0] <= stamps[1] <= stamps[2] <= now + 1e-7,
                    "delivery source/generation/receive time is noncausal")
            if event.get("stream") != "receipt":
                continue
            receipt = event["payload"]
            goal_id = receipt["goal_id"]
            require(goal_id in native and receipt["robot"] == goals[goal_id]["robot"],
                    "native receipt lacks matching goal")
            if receipt["type"] == "accept":
                require(receipt["value"] is True, "native goal rejected")
                accepted_at[goal_id] = event["received_stamp"]
            elif receipt["type"] == "cancel" and receipt["value"] is True:
                positive.add(goal_id)
            elif receipt["type"] == "result":
                status = STATUS.get(receipt["value"], receipt["value"])
                require(status in STATUS.values(), "nonterminal native result")
                results[goal_id] = status
    require(observed == set(snapshots), "transition snapshot absent from adapter audit")
    require(set(commands) == set(accepted) | set(rejected), "sampled command lacks action receipt")
    if not allow_incomplete:
        require(not any(owners.values()), "unresolved goal ownership at episode end")
        require(set(goals) == set(native) == set(results) == set(protocol_terminals),
                "goal lacks native send/result/protocol terminal closure")
        for goal_id in goals:
            require(results[goal_id] == protocol_terminals[goal_id]["status"],
                    "native/protocol terminal status differs")
            if goal_id in canceled and results[goal_id] == "CANCELED":
                require(goal_id in positive, "CANCELED terminal lacks positive cancel receipt")
    return {"accepted_action_count": len(accepted), "rejected_action_count": len(rejected),
            "goal_count": len(goals), "native_terminal_count": len(results),
            "keep_robot_command_count": len(keep), "cancel_count": len(canceled),
            "confirmed_cancellation_count": len(positive),
            "scope": "goal payload audit, not an action-server network trace"}


def audit_processes(metadata, shutdown, epoch, expected_fault=False):
    require(metadata.get("epoch") == epoch and shutdown.get("epoch") == epoch,
            "supervisor metadata/shutdown epoch mismatch")
    require(metadata.get("reset_kind") == "complete_process_rebuild", "reset mode mismatch")
    seen = shutdown["owned_processes_seen"]
    identities = [(row["pid"], row["start_ticks"]) for row in seen]
    require(identities and len(set(identities)) == len(identities)
            and all(type(pid) is int and pid > 0 and type(tick) is int and tick >= 0
                    for pid, tick in identities), "invalid/duplicate owned PID identities")
    worker = metadata["worker_identity"]
    require((worker["pid"], worker["start_ticks"]) in identities,
            "worker PID/start identity missing from ownership ledger")
    require(shutdown.get("remaining_owned_processes") == []
            and shutdown.get("remaining_owned_zombies") == [],
            "owned processes or zombies remain")
    if expected_fault:
        require(shutdown.get("failed_sample") is True
                and shutdown.get("forced_shutdown") is True
                and shutdown.get("worker_returncode") == -9,
                "declared SIGKILL fault lacks failed-sample/forced-cleanup proof")
    else:
        require(shutdown.get("failed_sample") is False
                and shutdown.get("forced_shutdown") is False
                and shutdown.get("worker_returncode") == 0, "normal worker did not exit cleanly")
    return {"owned_pid_identities": [list(pair) for pair in identities],
            "worker_identity": worker, "no_live_or_zombie_leftovers": True,
            "forced_cleanup": shutdown["forced_shutdown"],
            "scope": "saved PID/start identities and cleanup receipt; no live /proc inference"}


def audit_contacts(evaluator, launch_text, epoch):
    checks = Evidence(".")
    raw = checks.check("raw contact sequence", lambda:
                       validate_contact_reducer_summary(launch_text))

    def freshness():
        require(evaluator.get("schema_version") == 4 and evaluator.get("episode_id") == epoch
                and evaluator.get("robot_count") == 3
                and evaluator.get("contact_component_count_per_robot") == 6,
                "evaluator identity/schema/component count mismatch")
        summary = evaluator["contact_monitor_summary"]
        require(evaluator.get("collision_monitoring_active") is True
                and evaluator.get("collision_monitoring_fresh") is True
                and summary.get("fresh") is True and summary.get("ever_unhealthy") is False
                and summary.get("latched_issues") == {} and close(summary.get("max_age_sec"), .5),
                "contact monitoring stale, interrupted or gate changed")
        require(set(summary["components"]) == set(ROBOTS), "contact robot coverage differs")
        for name in ROBOTS:
            require(set(summary["components"][name]) == set(COMPONENTS),
                    "contact component coverage differs")
            for part in COMPONENTS:
                row = summary["components"][name][part]
                require(row.get("accepted_message_count", 0) > 0
                        and row.get("invalid_timestamp_count") == 0
                        and row.get("duplicate_message_count") == 0
                        and row.get("health_reason") == "",
                        "invalid contact source " + name + part)
                for key in ("source_age_sec", "receipt_age_sec", "max_source_gap_sec",
                            "max_receipt_gap_sec"):
                    require(number(row.get(key)) and 0 <= row[key] <= .500001,
                            "contact freshness bound failed: " + name + "/" + part + "/" + key)
        return True

    fresh = checks.check("continuous contact freshness", freshness) is True
    zero = (evaluator.get("collision_events") == 0
            and evaluator.get("contact_monitor_summary", {}).get("event_count") == 0)
    return {"passed": not checks.errors, "errors": checks.errors,
            "raw_sequence_audit_passed": raw is not None,
            "raw_stream_count": len(raw["topics"]) if raw else None,
            "continuous_freshness_passed": fresh, "zero_contact": zero,
            "collision_events": evaluator.get("collision_events"),
            "task_success": evaluator.get("success") is True,
            "termination_reason": evaluator.get("termination_reason"),
            "scope": "contact validity separate from mapping success and scripted sampling"}


def audit_launch_process_coverage(launch_text, native, shutdown):
    """A waited stop CLI may exit between /proc samples; other children may not.

    Only the uniquely named stop CLI gets this alternative evidence path: its
    launch start and clean-exit PID/suffix must match the successful native stop
    receipt, and the unique owned Gazebo server must independently have a
    matching start/clean exit and an actual supervisor PID/start ledger entry.
    This does not manufacture a /proc observation or Linux start tick.
    """
    proof, errors = native_stop_proof(launch_text, native)
    require(not errors, "; ".join(errors))
    seen_pids = {row["pid"] for row in shutdown["owned_processes_seen"]}
    started = [(name, suffix, int(pid)) for name, suffix, pid in re.findall(
        r"\[INFO\] \[([^\]\s]+)-(\d+)\]: process started with pid \[(\d+)\]", launch_text)]
    missing = [row for row in started if row[2] not in seen_pids]
    alternative = []
    if missing:
        cli = proof["mr3_gazebo_native_stop"]["started"][0]
        server = proof["gzserver"]["started"][0]
        expected = ("mr3_gazebo_native_stop", cli["suffix"], cli["pid"])
        require(missing == [expected],
                "launch child PID absent from supervisor ownership ledger (not sole stop CLI)")
        require(native.get("method") == "owned_launch_native_stop"
                and type(native.get("returncode")) is int and native["returncode"] == 0
                and native.get("native_cli_pid") == cli["pid"]
                and native.get("server_clean_exit_recorded") is True
                and server["pid"] in seen_pids and server["pid"] != cli["pid"],
                "unsampled stop CLI lacks matching successful CLI/owned-server exit proof")
        alternative = [{"process_name": f"mr3_gazebo_native_stop-{cli['suffix']}",
                        "pid": cli["pid"], "proc_sample_observed": False,
                        "evidence": "unique launch start/clean exit, native stop receipt code 0",
                        "matched_owned_server_pid": server["pid"]}]
    return {"native_shutdown_proof": proof,
            "launch_start_count": len(started),
            "unsampled_stop_cli_alternative_evidence": alternative,
            "other_launch_children_require_proc_identity": True}


def audit_initial_inputs_ready(metadata, transitions, adapter_rows, epoch):
    """A declared v3 reset requires a delivered-input ACK before first pause."""
    declaration = metadata.get("reset_handshake")
    if declaration is None:
        return {"required": False, "proven": False,
                "scope": "legacy reset; no delivered-input-before-pause handshake credit"}
    require(declaration == "delivered_inputs_before_pause-v1", "unknown reset handshake")
    require(bool(transitions) and transitions[0].get("kind") == "reset", "missing reset for ACK")
    info = transitions[0]["info"]
    ack = info["initial_inputs_ready"]
    require(ack.get("schema") == "mr3-initial-inputs-ready-v1" and ack.get("epoch") == epoch,
            "initial-input ACK schema/epoch mismatch")
    stamp = ack.get("stamp")
    require(number(stamp) and 0 <= stamp <= info["initial_pause_time_ns"] / NS + 1e-8,
            "initial-input ACK is later than first physical pause")
    require(type(ack.get("state_sequence")) is int and ack["state_sequence"] > 0
            and info["watermarks"]["state_sequence"] >= ack["state_sequence"],
            "first snapshot state sequence predates initial-input ACK")
    digest = ack.get("map_payload_sha256")
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
            "initial-input ACK map digest invalid")
    require(type(ack.get("map_version")) is int and ack["map_version"] > 0,
            "initial-input ACK map version invalid")
    require(number(ack.get("map_source_stamp")) and number(ack.get("map_received_stamp"))
            and 0 <= ack["map_source_stamp"] <= ack["map_received_stamp"] <= stamp + 1e-8,
            "initial-input ACK map times are noncausal")
    require([row.get("name") for row in ack.get("robots", [])] == list(ROBOTS),
            "initial-input ACK robot coverage differs")
    for robot in ack["robots"]:
        source, received = robot.get("source_stamp"), robot.get("received_stamp")
        require(number(source) and number(received) and 0 <= source <= received <= stamp + 1e-8
                and stamp - source <= .500001, "initial-input ACK has stale/future robot source")
    require(set(ack.get("map_sources", {})) == set(ROBOTS),
            "initial-input ACK lacks three delivered local maps")
    for source in ack["map_sources"].values():
        require(number(source.get("source_stamp")) and number(source.get("received_stamp"))
                and 0 <= source["source_stamp"] <= source["received_stamp"] <= stamp + 1e-8,
                "initial-input ACK local-map times are noncausal")
        require(isinstance(source.get("payload_sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", source["payload_sha256"]),
                "initial-input ACK local-map digest invalid")
    records = [row for row in adapter_rows if row.get("kind") == "initial_inputs_ready"]
    require(len(records) == 1 and records[0].get("epoch") == epoch
            and records[0].get("payload") == ack,
            "initial-input ACK is not the unique matching adapter record")
    return {"required": True, "proven": True, "protocol": declaration,
            "ack_stamp": stamp, "initial_pause_stamp": info["initial_pause_time_ns"] / NS,
            "ack_state_sequence": ack["state_sequence"],
            "first_snapshot_state_sequence": info["watermarks"]["state_sequence"],
            "ack_map_payload_sha256": digest,
            "scope": "input readiness before pause; first snapshot may use newer delivery"}


def audit_episode(directory, expected_fault=False):
    evidence = Evidence(directory)
    metadata = evidence.check("metadata", lambda: evidence.json("metadata.json")) or {}
    supervisor = evidence.check("supervisor metadata", lambda:
                                evidence.json("supervisor_metadata.json")) or {}
    epoch = supervisor.get("epoch")
    require_fault = bool(expected_fault)
    result = {"schema": "mr3-p1c-episode-audit-v1", "directory": str(Path(directory).resolve()),
              "epoch": epoch, "expected_infrastructure_fault": require_fault,
              "freeze": metadata.get("freeze"), "scene": metadata.get("scene"),
              "seed": metadata.get("seed"),
              "complete_episode_credit": not require_fault,
              "scope": "scripted sampling/reset; no RL, throughput or 95% success inference"}
    shutdown = evidence.check("shutdown receipt", lambda:
                              evidence.json("supervisor_shutdown.json")) or {}
    result["processes"] = evidence.check(
        "process cleanup", lambda: audit_processes(supervisor, shutdown, epoch, require_fault))
    transitions = evidence.check("transitions JSONL", lambda:
                                 evidence.rows("transitions.jsonl")) or []
    physics = evidence.check("physics JSONL", lambda: evidence.rows("physics.jsonl")) or []
    evidence.check("epoch", lambda: require(isinstance(epoch, str) and bool(epoch)
                   and metadata.get("epoch") == epoch, "worker epoch mismatch"))
    if transitions and physics:
        release = transitions[0].get("info", {}).get("release_time_ns")
        result["physics"] = evidence.check("physical receipts", lambda:
                                           audit_physics(physics, epoch, release))
        result["transitions"] = evidence.check("transition replay", lambda:
                                               audit_transitions(transitions, physics, epoch,
                                                                 require_fault))
    rows = evidence.check("adapter JSONL", lambda: evidence.rows("adapter.jsonl")) or []
    result["initial_inputs_ready"] = evidence.check(
        "initial delivered-input handshake", lambda:
        audit_initial_inputs_ready(metadata, transitions, rows, epoch))
    if rows:
        if (Path(directory) / "adapter.sha256").exists():
            evidence.check("adapter digest", lambda: require(
                (Path(directory) / "adapter.sha256").read_text().strip() ==
                evidence.hashes["adapter.jsonl"], "adapter byte checksum mismatch"))
        result["protocol"] = evidence.check(
            "protocol replay", lambda: audit_protocol(rows, transitions, epoch, require_fault))
    if not require_fault:
        summary = evidence.check("episode summary", lambda: evidence.json("summary.json")) or {}
        native = evidence.check("native stop", lambda: evidence.json("native_stop.json")) or {}
        text = evidence.check("launch log", lambda: evidence.raw("launch.log").decode(
            "utf8", errors="replace")) or ""

        def closure():
            require(summary.get("epoch") == epoch and summary.get("launch_returncode") == 0
                    and summary.get("native_failures") == [], "native launch failed")
            closed = summary["closed"]
            require(closed.get("epoch") == epoch and closed.get("pending_goal_count") == 0
                    and closed.get("robot_names") == list(ROBOTS), "navigation not closed")
            require([row["payload"] for row in rows if row["kind"] == "task_stopped"] == [closed],
                    "adapter task_stopped does not match worker closure")
            require(not native_launch_failures(text) and native.get("returncode") == 0,
                    "native child failure or native stop failed")
            coverage = audit_launch_process_coverage(text, native, shutdown)
            return {**coverage, "navigation_closed": True,
                    "navigation_failure": closed.get("navigation_failure"),
                    "safety_failures": summary.get("failures")}

        result["closure"] = evidence.check("native/navigation closure", closure)
        evaluator = evidence.check("evaluator", lambda: evidence.json(str(epoch) + ".json")) or {}
        result["contacts"] = evidence.check("contact monitoring", lambda:
                                            audit_contacts(evaluator, text, epoch))
        if result["contacts"]:
            evidence.errors.extend(result["contacts"]["errors"])
        if transitions and transitions[-1].get("terminated"):
            evidence.check("terminal classification", lambda: require(
                close(evaluator.get("end_sim_time_sec"), transitions[-1]["info"][
                    "reward_diagnostics"]["effective_step_end"])
                and evaluator.get("termination_reason") == transitions[-1]["info"]["reason"],
                "terminal sample differs from frozen evaluator result"))
    result.update(passed=not evidence.errors, errors=evidence.errors,
                  evidence_sha256=evidence.hashes,
                  supervisor_shutdown_digest=canonical_digest(shutdown))
    result["complete_episode_credit"] = bool(result["passed"] and not require_fault)
    return result


def comparison_statistics(metadata, summary):
    """Use the declared two-cell workload, never serial reset-only regressions.

    Concurrent workers' elapsed times are not additive. The largest recorded
    two-cell duration is a comparable elapsed-time proxy, not an exact global
    process span: these records omit the final Supervisor reap tail and do not
    contain absolute monotonic start/end stamps. Shutdown receipts prove PID
    cleanup but do not record its duration, so that tail remains unknown.
    """
    common = [["open", 101], ["open", 101]]
    schedule = metadata.get("schedule", [])
    if (metadata.get("fault_probe") is True or metadata.get("deadline_probe") is True
            or schedule[:2] != common):
        return {"eligible": False, "reason": "not the declared normal two-open101 workload"}
    count, steps = metadata["workers"], metadata["steps_per_episode"]
    require(type(steps) is int and steps > 0, "invalid comparison step budget")
    tail = schedule[2:]
    require(tail == [] or (count == 1 and tail == [["rooms", 202], ["corridors", 303]]),
            "extra scenes differ from the declared serial reset regression")
    workers = summary["workers_results"]
    require(len(workers) == count, "comparison worker count differs")
    per_worker = []
    excluded = 0
    for worker in workers:
        cells = worker["episodes"][:2]
        require(len(cells) == 2, "comparison requires two cells per worker")
        elapsed, active = 0., 0.
        for cell in cells:
            require([cell.get("scene"), cell.get("seed")] == ["open", 101]
                    and cell.get("transitions") == steps
                    and cell.get("truncated") is True and cell.get("terminated") is False,
                    "comparison cell workload or completion differs")
            wall = cell.get("wall_sec_including_startup_and_closure")
            transition_wall = cell.get("transition_wall_sec")
            require(number(wall) and wall > 0 and number(transition_wall)
                    and 0 < transition_wall <= wall, "comparison cell has invalid elapsed times")
            elapsed += wall
            active += transition_wall
        per_worker.append({"worker_id": worker["worker_id"], "valid_transitions": 2 * steps,
                           "cell_recorded_wall_sec": elapsed,
                           "transition_only_wall_sec": active,
                           "transition_only_rate_per_active_wall_sec": 2 * steps / active})
        excluded += sum(cell["transitions"] for cell in worker["episodes"][2:])
    denominator = max(worker["cell_recorded_wall_sec"] for worker in per_worker)
    require(number(summary.get("wall_sec_including_all_attempts"))
            and denominator <= summary["wall_sec_including_all_attempts"] + 1e-7,
            "comparison cell span exceeds the entire benchmark wall time")
    total = 2 * steps * count
    return {"eligible": True, "schedule": common, "episode_indices": [0, 1],
            "steps_per_episode": steps, "valid_transitions": total,
            "denominator_wall_sec": denominator,
            "effective_transition_per_wall_sec": total / denominator,
            "denominator_scope": "max_worker(sum of first two recorded cell elapsed times)",
            "includes": "cell startup, next-reset cleanup of prior worker, native goal closure",
            "excludes": "final Supervisor reap tail and all later serial scene regressions",
            "exact_end_to_end_process_span": False,
            "final_supervisor_cleanup_wall_sec": None,
            "final_cleanup_timing_available": False,
            "per_worker": sorted(per_worker, key=lambda row: row["worker_id"]),
            "reset_regression_only_schedule": tail,
            "reset_regression_only_transitions": excluded}


def audit_benchmark(directory):
    evidence = Evidence(directory)
    metadata = evidence.check("benchmark metadata", lambda:
                              evidence.json("benchmark_metadata.json")) or {}
    summary = evidence.check("benchmark summary", lambda:
                             evidence.json("benchmark_summary.json")) or {}
    episodes, epochs, identities, all_owned_identities = [], set(), set(), set()
    workers = summary.get("workers_results", [])
    count = metadata.get("workers")
    fault = metadata.get("fault_probe") is True
    evidence.check("benchmark declaration", lambda: require(
        count in (1, 2, 4) and metadata.get("robots_per_worker") == 3
        and summary.get("workers") == count and summary.get("freeze") == metadata.get("freeze")
        and summary.get("passed") is True and len(workers) == count
        and sorted(worker["worker_id"] for worker in workers) == list(range(count)),
        "benchmark declaration/worker count/freeze/result mismatch"))
    transitions = 0
    for worker in workers:
        worker_id = worker.get("worker_id")
        evidence.check(f"worker {worker_id}", lambda: require(
            not worker.get("error") and not worker.get("cleanup_error")
            and len(worker["episodes"]) == len(metadata["schedule"])
            and len(worker["shutdown_receipts"]) == len(worker["episodes"]),
            "worker error or missing reset/cleanup episode"))
        previous_worker_identity = None
        for index, cell in enumerate(worker.get("episodes", [])):
            expected_fault = fault and worker_id == 0 and index == 0
            # Resolve by relative owned layout, so selected evidence can be relocated.
            directories = sorted((Path(directory) / f"worker{worker_id}").glob(
                f"episode{index + 1:03d}_*"))
            if len(directories) != 1:
                evidence.errors.append(
                    f"worker {worker_id} episode {index}: unique directory missing")
                continue
            audit = audit_episode(directories[0], expected_fault)
            episodes.append(audit)
            if not audit["passed"]:
                evidence.errors.append(f"worker {worker_id} episode {index} audit failed")
            epoch = audit.get("epoch")
            evidence.check("new reset epoch", lambda: require(
                epoch not in epochs and epoch == cell.get("epoch"), "epoch reused or differs"))
            epochs.add(epoch)
            process = audit.get("processes") or {}
            current = process.get("worker_identity", {})
            pair = (current.get("pid"), current.get("start_ticks"))
            evidence.check("new reset process", lambda: require(
                pair != previous_worker_identity and pair not in identities,
                "worker process identity reused across reset"))
            previous_worker_identity = pair
            identities.add(pair)
            owned_pairs = {tuple(pair) for pair in process.get("owned_pid_identities", [])}
            evidence.check("reset process ownership isolation", lambda: require(
                not owned_pairs.intersection(all_owned_identities),
                "owned child PID/start identity reused across episode epochs"))
            all_owned_identities.update(owned_pairs)
            evidence.check("episode declaration", lambda: require(
                audit["freeze"] == metadata.get("freeze")
                and [audit["scene"], audit["seed"]] == metadata["schedule"][index]
                and audit["scene"] == cell.get("scene") and audit["seed"] == cell.get("seed")
                and audit["supervisor_shutdown_digest"] == canonical_digest(
                    worker["shutdown_receipts"][index]),
                "episode freeze/scene/seed/cleanup differs from benchmark declaration"))
            detail = audit.get("transitions") or {}
            n = detail.get("transition_count", -1)
            evidence.check("episode sampler accounting", lambda: require(
                n == cell.get("transitions") and close(detail.get("reward_sum"),
                                                       cell.get("reward_sum"))
                and ((expected_fault and n == 4 and cell.get("expected_infrastructure_fault")
                      and worker.get("fault_verified") is True)
                     or (not expected_fault and n == metadata["steps_per_episode"]
                         and detail.get("complete") is True
                         and ((metadata.get("deadline_probe") is True
                               and cell.get("terminated") is True
                               and cell.get("truncated") is False
                               and cell.get("reason") == "timeout")
                              or (metadata.get("deadline_probe") is not True
                                  and cell.get("truncated") is True
                                  and cell.get("terminated") is False)))),
                "sampler transition/reward/fault count mismatch"))
            transitions += max(0, n)
    wall = summary.get("wall_sec_including_all_attempts")
    evidence.check("throughput denominator", lambda: require(
        number(wall) and wall > 0 and summary.get("valid_transitions") == transitions
        and close(summary.get("effective_transition_per_wall_sec"), transitions / wall),
        "throughput omits attempts or differs from valid saved transition count"))
    evidence.check("resource trace", lambda: require(
        bool(json.loads(evidence.raw("resources.json"))), "resource samples missing"))
    comparison = evidence.check("comparison accounting", lambda:
                                comparison_statistics(metadata, summary))
    return {"schema": "mr3-p1c-benchmark-audit-v1", "directory": str(Path(directory).resolve()),
            "passed": not evidence.errors, "errors": evidence.errors, "episodes": episodes,
            "workers": count, "freeze": metadata.get("freeze"), "fault_probe": fault,
            "schedule": metadata.get("schedule"),
            "steps_per_episode": metadata.get("steps_per_episode"),
            "deadline_probe": metadata.get("deadline_probe") is True,
            "valid_transitions": transitions, "wall_sec_including_all_attempts": wall,
            "effective_transition_per_wall_sec": summary.get("effective_transition_per_wall_sec"),
            "comparison": comparison,
            "complete_episode_count": sum(row["complete_episode_credit"] for row in episodes),
            "fault_scope": "injected cell excluded; forced cleanup, recovery and peer audited",
            "evidence_sha256": evidence.hashes}


def audit_matrix(directories):
    results = [audit_benchmark(directory) for directory in directories]
    normal = [row for row in results if not row["fault_probe"] and not row["deadline_probe"]]
    errors = []
    if not all(row["passed"] for row in results):
        errors.append("one or more benchmark audits failed")
    if sorted(row["workers"] for row in normal) != [1, 2, 4]:
        errors.append("comparison requires exactly one normal 1/2/4-worker benchmark")
    if len({row["freeze"] for row in results}) != 1:
        errors.append("benchmark matrix mixes source freezes")
    common = [["open", 101], ["open", 101]]
    if (any((row.get("schedule") or [])[:2] != common
            or not (row.get("comparison") or {}).get("eligible")
            for row in normal)
            or len({row["steps_per_episode"] for row in normal}) != 1):
        errors.append("normal comparison requires two open101 cells and the same step budget")
    return {"schema": "mr3-p1c-matrix-audit-v1", "passed": not errors, "errors": errors,
            "benchmarks": results,
            "comparison": [{"workers": row["workers"], **(row.get("comparison") or {})}
                           for row in sorted(normal, key=lambda value: value["workers"])],
            "scope": "scripted sampler throughput, not RL or 95% task success"}


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--expected-fault", action="store_true")
    options = parser.parse_args(args)
    if options.output.exists():
        parser.error("audit output exists; choose a new path")
    if options.matrix:
        if options.expected_fault:
            parser.error("matrix identifies declared faults from benchmark metadata")
        result = audit_matrix(options.directories)
    else:
        if len(options.directories) != 1:
            parser.error("multiple directories require --matrix")
        directory = options.directories[0]
        result = (audit_benchmark(directory) if (directory / "benchmark_metadata.json").exists()
                  else audit_episode(directory, options.expected_fault))
    with options.output.open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "audit": str(options.output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
