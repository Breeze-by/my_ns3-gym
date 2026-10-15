#!/usr/bin/env python3
"""Audit saved P1B scripted-adapter evidence without starting ROS or a simulator.

This checks an interrupted protocol probe, not RL performance or 95% mapping.
Contact monitoring is reported separately and can be required explicitly.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

from ros_smoke_test import native_launch_failures, validate_contact_reducer_summary


ROBOTS = ("tb1", "tb2", "tb3")
TERMINALS = (4, 5, 6, "SUCCEEDED", "CANCELED", "ABORTED")
REQUIRED_REJECTIONS = {"wrong_epoch", "expired_or_invalid_command_time", "masked_action"}


def canonical_digest(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def audit_run(run_dir, require_contact_monitoring=False):
    """Return evidence checks and failures; never mutate the run directory."""
    run_dir = Path(run_dir)
    errors = []

    def fail(reason):
        errors.append(reason)

    def read_json(path, required=True):
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError("expected a JSON object")
            return value
        except (OSError, ValueError, TypeError) as error:
            if required:
                fail(f"{path.name}: {error}")
            return {}

    summary = read_json(run_dir / "summary.json")
    native_stop = read_json(run_dir / "native_stop.json")
    if summary.get("launch_returncode") != 0:
        fail("launch did not exit with code 0")
    if summary.get("error"):
        fail("probe runner reported an error: " + str(summary["error"]))
    if summary.get("failures") != []:
        fail("probe runner did not report an empty safety-failure list")
    closed = summary.get("closed")
    if (not isinstance(closed, dict) or closed.get("pending_goal_count") != 0
            or closed.get("robot_names") != list(ROBOTS)
            or closed.get("navigation_failure") is not False):
        fail("runner closure does not prove three-robot ownership closure without failure")
    if native_stop.get("returncode") != 0:
        fail("native Gazebo stop command did not exit with code 0")
    try:
        launch_text = (run_dir / "launch.log").read_text(errors="replace")
    except OSError as error:
        fail("launch.log: " + str(error))
        launch_text = ""
    native_failures = native_launch_failures(launch_text)
    if native_failures:
        fail("native launch failures: " + native_failures[0])

    rows = []
    audit_path = run_dir / "adapter.jsonl"
    try:
        raw = (audit_path.read_bytes() if audit_path.exists()
               else gzip.decompress((run_dir / "adapter.jsonl.gz").read_bytes()))
        expected_path = run_dir / "adapter.sha256"
        if (expected_path.exists()
                and expected_path.read_text().strip() != hashlib.sha256(raw).hexdigest()):
            fail("adapter byte digest does not match adapter.sha256")
        previous_stamp = -math.inf
        for index, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
                if (not isinstance(row, dict) or not isinstance(row.get("payload"), dict)
                        or not _number(row.get("stamp")) or row["stamp"] < 0
                        or not isinstance(row.get("kind"), str)):
                    raise ValueError("invalid event envelope")
                if row["stamp"] < previous_stamp:
                    fail(f"audit line {index}: simulation event time regressed")
                previous_stamp = row["stamp"]
                rows.append(row)
            except (ValueError, TypeError) as error:
                fail(f"audit line {index}: {error}")
    except (OSError, ValueError, EOFError, UnicodeError) as error:
        raw = b""
        fail("adapter JSONL: " + str(error))

    snapshots, actions = {}, {}
    sent, native, accepted, canceled, terminal, native_terminal = {}, {}, {}, {}, {}, {}
    owners = {name: None for name in ROBOTS}
    keep_pairs, rejection_reasons = set(), set()
    duplicates = 0
    epoch = None
    task_stopped = []
    for index, row in enumerate(rows, 1):
        kind, payload, now = row["kind"], row["payload"], row["stamp"]
        if kind == "delivery":
            stamps = [payload.get(key) for key in
                      ("source_stamp", "generated_stamp", "received_stamp")]
            if (not all(_number(value) for value in stamps)
                    or not 0 <= stamps[0] <= stamps[1] <= stamps[2] <= now + 1e-8):
                fail(f"delivery line {index}: noncausal source/generation/delivery time")
        if epoch is None and kind == "observation":
            epoch = payload.get("epoch")
        if kind == "observation":
            try:
                sequence = payload["sequence"]
                if type(sequence) is not int or sequence < 0 or sequence in snapshots:
                    raise ValueError("duplicate or invalid observation sequence")
                actual = canonical_digest({k: v for k, v in payload.items() if k != "digest"})
                if actual != payload.get("digest"):
                    raise ValueError("saved observation digest mismatch")
                candidate_digest = canonical_digest({
                    key: payload[key] for key in ("epoch", "map_version", "sequence", "candidates")
                })
                if payload.get("candidate_version") != candidate_digest:
                    raise ValueError("candidate version does not match saved candidates")
                snapshots[sequence] = payload
            except (KeyError, ValueError, TypeError) as error:
                fail(f"observation line {index}: {error}")
        elif kind == "action":
            try:
                command_id = payload["command_id"]
                if type(command_id) is not int or command_id < 0 or command_id in actions:
                    raise ValueError("duplicate or invalid accepted command id")
                snapshot = snapshots[payload["observation_sequence"]]
                if payload["observation_digest"] != snapshot["digest"]:
                    raise ValueError("action references a different observation digest")
                if payload["candidate_version"] != snapshot["candidate_version"]:
                    raise ValueError("action references a different candidate version")
                action = payload["action"]
                if type(action) is not int or not 0 <= action < 1000:
                    raise ValueError("invalid joint action")
                choices = [action // 100, action // 10 % 10, action % 10]
                if payload["choices"] != choices:
                    raise ValueError("joint action digit decoding mismatch")
                mask = snapshot["joint_action_mask"]
                if len(mask) != 1000 or mask[action] is not True:
                    raise ValueError("accepted action was masked in its saved observation")
                if set(payload["results"]) != set(ROBOTS):
                    raise ValueError("accepted action lacks three robot receipts")
                for robot, choice in zip(ROBOTS, choices):
                    result = payload["results"][robot]
                    if choice == 8:
                        keep_pairs.add((robot, command_id))
                        if result != "kept":
                            raise ValueError("KEEP was not acknowledged as kept")
                    elif choice == 9 and result != "waiting":
                        raise ValueError("WAIT was not acknowledged as waiting")
                    elif choice < 8 and result not in ("sent", "switch_pending"):
                        raise ValueError("candidate goal was not sent or awaiting old terminal")
                actions[command_id] = payload
            except (KeyError, ValueError, TypeError, IndexError) as error:
                fail(f"action line {index}: {error}")
        elif kind == "action_duplicate":
            duplicates += 1
            original = actions.get(payload.get("command_id"))
            if original is None or original != payload:
                fail(f"line {index}: duplicate command receipt differs from original")
        elif kind == "action_rejected":
            if isinstance(payload.get("reason"), str):
                rejection_reasons.add(payload["reason"])
            else:
                fail(f"line {index}: rejection is missing its explicit reason")
        elif kind == "native_send":
            robot, goal_id = payload.get("robot"), payload.get("goal_id")
            if goal_id in native:
                fail(f"line {index}: native goal was sent more than once: {goal_id}")
            native[goal_id] = payload
            prior = sent.get(goal_id)
            if prior is None or prior.get("robot") != robot:
                fail(f"line {index}: native send lacks preceding owned protocol goal")
            elif payload.get("command_id") != prior.get("command_id"):
                fail(f"line {index}: native send command id differs from protocol goal")
            elif not _number(prior.get("expires_at")) or now >= prior["expires_at"]:
                fail(f"line {index}: expired goal reached native action client")
        elif kind == "protocol":
            event_type = payload.get("type")
            robot, goal_id = payload.get("robot"), payload.get("goal_id")
            if robot not in owners:
                fail(f"line {index}: unknown protocol robot")
                continue
            if event_type == "send_goal":
                if goal_id != f"{epoch}:{robot}:{payload.get('command_id')}":
                    fail(f"line {index}: goal id does not bind epoch/robot/command")
                if owners[robot] is not None or goal_id in sent:
                    fail(f"line {index}: second goal sent before old terminal for {robot}")
                owners[robot] = goal_id
                sent[goal_id] = payload
                try:
                    action = actions[payload["command_id"]]
                    snapshot = snapshots[action["observation_sequence"]]
                    choice = action["choices"][ROBOTS.index(robot)]
                    if choice >= 8:
                        raise ValueError("KEEP/WAIT emitted send_goal")
                    candidate = snapshot["candidates"][choice]
                    if payload["goal"] != {"x": candidate["x"], "y": candidate["y"]}:
                        raise ValueError("sent goal differs from chosen saved candidate")
                    if payload["observation_version"] != snapshot["sequence"]:
                        raise ValueError("sent goal observation version mismatch")
                except (KeyError, ValueError, TypeError, IndexError) as error:
                    fail(f"protocol send line {index}: {error}")
            elif event_type == "cancel_goal":
                if owners[robot] != goal_id:
                    fail(f"line {index}: cancellation has no matching owned goal")
                if goal_id in canceled:
                    fail(f"line {index}: repeated cancellation of the same goal")
                canceled[goal_id] = payload
                if payload.get("reason") in ("wait", "switch"):
                    accepted_at = accepted.get(goal_id)
                    if (accepted_at is None
                            or payload.get("stamp", now) < accepted_at + 5. - 1e-8):
                        fail(f"line {index}: discretionary cancellation violated "
                             "5-second commitment")
            elif event_type == "protocol_terminal":
                if payload.get("status") not in TERMINALS + ("REJECTED",):
                    fail(f"line {index}: invalid protocol terminal status")
                if owners[robot] != goal_id:
                    fail(f"line {index}: terminal does not match currently owned goal")
                if goal_id in terminal:
                    fail(f"line {index}: repeated protocol terminal")
                terminal[goal_id] = payload
                owners[robot] = None
            elif event_type == "protocol_failure":
                fail("protocol failure: " + str(payload.get("reason")))
        elif kind == "delivery" and payload.get("stream") == "receipt":
            event = payload.get("payload", {})
            goal_id, robot = event.get("goal_id"), event.get("robot", payload.get("source"))
            if goal_id not in sent or sent[goal_id].get("robot") != robot:
                fail(f"line {index}: native receipt has no matching protocol goal")
                continue
            if event.get("type") == "accept":
                if event.get("value") is True:
                    accepted[goal_id] = payload.get("received_stamp", now)
                else:
                    fail(f"line {index}: native goal was rejected")
            elif event.get("type") == "result":
                if event.get("value") not in TERMINALS:
                    fail(f"line {index}: native result is not terminal")
                else:
                    native_terminal[goal_id] = event["value"]
        elif kind == "task_stopped":
            task_stopped.append(payload)

    if not snapshots:
        fail("no valid saved observation snapshots")
    if not actions:
        fail("no accepted replayable joint actions")
    if epoch is None or any(row.get("epoch") != epoch for row in rows):
        fail("audit records do not share one episode epoch")
    expected_epoch = next((arg.split(":=", 1)[1] for arg in summary.get("command", [])
                           if isinstance(arg, str) and arg.startswith("mr3_episode_epoch:=")), None)
    if expected_epoch is not None and expected_epoch != epoch:
        fail("runner launch epoch differs from saved observation epoch")
    accepted_robots = {sent[goal_id]["robot"] for goal_id in accepted}
    if accepted_robots != set(ROBOTS):
        fail("native accept receipts do not cover all three robots")
    for goal_id, event in sent.items():
        if (event.get("robot"), event.get("command_id")) in keep_pairs:
            fail("KEEP command resubmitted a goal: " + str(goal_id))
        if goal_id not in terminal:
            fail("protocol goal lacks terminal closure: " + str(goal_id))
    for goal_id, event in native.items():
        if (event.get("robot"), event.get("command_id")) in keep_pairs:
            fail("KEEP command reached native send: " + str(goal_id))
        if goal_id not in native_terminal:
            fail("native goal lacks a real action terminal: " + str(goal_id))
        elif goal_id in terminal:
            status_names = {4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}
            actual = status_names.get(native_terminal[goal_id], native_terminal[goal_id])
            reported = terminal[goal_id].get("status")
            if status_names.get(reported, reported) != actual:
                fail("protocol terminal differs from native result: " + str(goal_id))
    if any(owners.values()):
        fail("protocol ownership remains unresolved at end of audit")
    if not keep_pairs:
        fail("probe did not exercise KEEP")
    if not duplicates:
        fail("probe did not exercise duplicate command idempotency")
    if not any(goal_id in native and goal_id in native_terminal for goal_id in canceled):
        fail("probe did not exercise a real native cancellation followed by terminal closure")
    missing_rejections = REQUIRED_REJECTIONS - rejection_reasons
    if missing_rejections:
        fail("missing rejection probes: " + ", ".join(sorted(missing_rejections)))
    if len(task_stopped) != 1 or task_stopped[0] != closed:
        fail("audit task_stopped acknowledgment does not match runner closure")

    contact = {"required": bool(require_contact_monitoring), "available": False,
               "task_success_claimed": False, "scope": "interrupted scripted adapter probe"}
    candidates = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name in ("summary.json", "metadata.json", "native_stop.json", "audit.json"):
            continue
        value = read_json(path, required=False)
        if value.get("schema_version") == 4:
            candidates.append((path, value))
    if len(candidates) == 1:
        path, value = candidates[0]
        contact.update({
            "available": True, "file": path.name,
            "schema_version": value.get("schema_version"),
            "termination_reason": value.get("termination_reason"),
            "evaluator_success": value.get("success"),
            "collision_events": value.get("collision_events"),
            "monitoring_active": value.get("collision_monitoring_active"),
            "monitoring_fresh": value.get("collision_monitoring_fresh"),
            "navigation_protocol_closed_in_evaluator": value.get("navigation_protocol_closed"),
        })
    try:
        raw_monitor = validate_contact_reducer_summary(launch_text)
        contact["raw_stream_audit_passed"] = True
        contact["raw_stream_count"] = len(raw_monitor["topics"])
    except RuntimeError as error:
        contact["raw_stream_audit_passed"] = False
        contact["raw_stream_error"] = str(error)
    contact["passed"] = bool(
        len(candidates) == 1 and contact.get("collision_events") == 0
        and contact.get("monitoring_active") is True and contact.get("monitoring_fresh") is True
        and candidates[0][1].get("robot_count") == 3
        and candidates[0][1].get("contact_component_count_per_robot") == 6
        and contact["raw_stream_audit_passed"]
    )
    if require_contact_monitoring and not contact["passed"]:
        fail("required contact monitoring evidence is incomplete or unhealthy")
    return {
        "schema": "mr3-p1b-probe-audit-v1", "passed": not errors, "errors": errors,
        "run_directory": str(run_dir.resolve()), "epoch": epoch,
        "scope": "scripted P1B adapter protocol; no RL or 95% task-success credit",
        "adapter_sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot_count": len(snapshots), "action_count": len(actions),
        "protocol_goal_count": len(sent), "native_send_count": len(native),
        "accepted_robots": sorted(accepted_robots), "native_terminal_count": len(native_terminal),
        "cancel_goal_count": len(canceled), "keep_robot_command_count": len(keep_pairs),
        "duplicate_command_count": duplicates, "rejection_reasons": sorted(rejection_reasons),
        "native_launch_failures": native_failures, "contact_monitoring": contact,
    }


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-contact-monitoring", action="store_true")
    options = parser.parse_args(args)
    output = options.output or options.run_dir / "audit.json"
    if output.exists():
        parser.error("audit output already exists; choose a new --output path")
    result = audit_run(options.run_dir, options.require_contact_monitoring)
    with output.open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "audit": str(output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
