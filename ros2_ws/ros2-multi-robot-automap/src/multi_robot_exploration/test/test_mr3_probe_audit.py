"""Audit evidence independently, including tampering and missing native closure."""

import gzip
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "audit_mr3_adapter_probe", SCRIPTS / "audit_mr3_adapter_probe.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


NATIVE_LOG = (
    "[INFO] [gzserver-4]: process started with pid [123]\n"
    "[INFO] [mr3_gazebo_native_stop-30]: process started with pid [456]\n"
    "[INFO] [mr3_gazebo_native_stop-30]: process has finished cleanly [pid 456]\n"
    "[INFO] [gzserver-4]: process has finished cleanly [pid 123]\n"
)


def snapshot(sequence, now):
    value = {
        "schema": "mr3-observation-v1",
        "epoch": "episode-a", "sequence": sequence, "map_version": sequence,
        "source_stamp": now,
        "robots": [{"name": name, "x": float(index * 2) + sequence * .1, "y": 0.,
                    "valid": True, "fresh": True, "source_stamp": now}
                   for index, name in enumerate(AUDIT.ROBOTS)],
        "candidates": [{"x": float(index * 2), "y": 0.0} for index in range(8)],
        "joint_action_mask": [action in (12, 888, 999) for action in range(1000)],
    }
    value["candidate_version"] = AUDIT.canonical_digest({
        key: value[key] for key in ("epoch", "map_version", "sequence", "candidates")})
    value["digest"] = AUDIT.canonical_digest(value)
    return value


def evidence(tmp_path):
    rows = []

    def row(kind, now, payload):
        rows.append({"kind": kind, "stamp": now, "epoch": "episode-a", "payload": payload})

    def action(sequence, now, joint, results):
        observation = snapshot(sequence, now)
        row("observation", now, observation)
        payload = {
            "command_id": sequence, "action": joint, "results": dict(zip(AUDIT.ROBOTS, results)),
            "observation_sequence": sequence, "observation_digest": observation["digest"],
            "candidate_version": observation["candidate_version"],
            "choices": [joint // 100, joint // 10 % 10, joint % 10],
        }
        row("action", now, payload)
        return payload

    def receipt(robot, goal_id, kind, value, now):
        row("delivery", now, {
            "epoch": "episode-a", "stream": "receipt", "source": robot,
            "source_stamp": now, "generated_stamp": now, "received_stamp": now,
            "payload": {"type": kind, "robot": robot, "goal_id": goal_id, "value": value},
        })

    action(1, 1., 12, ["sent"] * 3)
    for index, robot in enumerate(AUDIT.ROBOTS):
        goal_id = f"episode-a:{robot}:1"
        row("protocol", 1., {
            "type": "send_goal", "robot": robot, "goal_id": goal_id, "stamp": 1.,
            "command_id": 1, "observation_version": 1, "created_at": 1., "expires_at": 3.,
            "goal": {"x": float(index * 2), "y": 0.0},
        })
        row("native_send", 1., {"robot": robot, "goal_id": goal_id, "command_id": 1})
        receipt(robot, goal_id, "accept", True, 1.1)
    for reason in AUDIT.REQUIRED_REJECTIONS:
        row("action_rejected", 1.2, {"reason": reason})
    keep = action(2, 2., 888, ["kept"] * 3)
    row("action_duplicate", 2.1, keep)
    action(3, 6.1, 999, ["waiting"] * 3)
    for robot in AUDIT.ROBOTS:
        goal_id = f"episode-a:{robot}:1"
        row("protocol", 6.1, {"type": "cancel_goal", "robot": robot,
                              "goal_id": goal_id, "stamp": 6.1, "reason": "wait"})
        receipt(robot, goal_id, "cancel", True, 6.2)
        receipt(robot, goal_id, "result", 5, 6.3)
        row("protocol", 6.35, {"type": "protocol_terminal", "robot": robot,
                               "goal_id": goal_id, "stamp": 6.3, "status": "CANCELED"})
    closed = {"start_sim_time_sec": 0., "stop_sim_time_sec": 6.4, "pending_goal_count": 0,
              "robot_names": list(AUDIT.ROBOTS), "navigation_failure": False}
    row("task_stopped", 6.4, closed)
    rows.sort(key=lambda value: value["stamp"])
    summary = {"launch_returncode": 0, "error": None, "failures": [], "closed": closed,
               "command": ["mr3_episode_epoch:=episode-a"]}
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    (tmp_path / "native_stop.json").write_text(json.dumps({
        "returncode": 0, "method": "owned_launch_native_stop",
        "native_cli_pid": 456, "server_clean_exit_recorded": True,
    }))
    (tmp_path / "launch.log").write_text(NATIVE_LOG)
    save_rows(tmp_path, rows)
    return rows


def save_rows(run, rows):
    (run / "adapter.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def assert_failed(tmp_path, text):
    result = AUDIT.audit_run(tmp_path)
    assert not result["passed"]
    assert any(text in error for error in result["errors"]), result["errors"]


def test_valid_protocol_probe_passes_without_claiming_task_success(tmp_path):
    evidence(tmp_path)
    result = AUDIT.audit_run(tmp_path)
    assert result["passed"], result["errors"]
    assert result["snapshot_count"] == 3 and result["native_send_count"] == 3
    assert result["accepted_robots"] == list(AUDIT.ROBOTS)
    assert result["contact_monitoring"]["required"] is False
    assert result["contact_monitoring"]["task_success_claimed"] is False


def test_gzip_evidence_is_supported(tmp_path):
    evidence(tmp_path)
    path = tmp_path / "adapter.jsonl"
    (tmp_path / "adapter.jsonl.gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    path.unlink()
    assert AUDIT.audit_run(tmp_path)["passed"]


def upgrade_v2(rows):
    snapshots = {}
    for row in rows:
        if row["kind"] != "observation":
            continue
        value = row["payload"]
        value["schema"] = "mr3-observation-v2"
        value["path_maps"] = {robot: {"source": "received_own_map", "version": 1}
                              for robot in AUDIT.ROBOTS}
        value["candidate_version"] = AUDIT.canonical_digest({
            key: value[key] for key in
            ("epoch", "map_version", "sequence", "candidates", "path_maps")})
        value["digest"] = AUDIT.canonical_digest({k: v for k, v in value.items() if k != "digest"})
        snapshots[value["sequence"]] = value
    for row in rows:
        if row["kind"] in ("action", "action_duplicate"):
            value = row["payload"]
            observation = snapshots[value["observation_sequence"]]
            value["candidate_version"] = observation["candidate_version"]
            value["observation_digest"] = observation["digest"]


def test_v2_candidate_hash_includes_received_own_path_map_metadata(tmp_path):
    rows = evidence(tmp_path)
    upgrade_v2(rows)
    save_rows(tmp_path, rows)
    result = AUDIT.audit_run(tmp_path)
    assert result["passed"], result["errors"]
    assert all(value > .05 for value in result["estimated_snapshot_path_length_m"].values())


def test_v2_path_map_tampering_fails_even_when_outer_snapshot_digest_is_updated(tmp_path):
    rows = evidence(tmp_path)
    upgrade_v2(rows)
    value = rows[0]["payload"]
    value["path_maps"]["tb1"]["version"] = 2
    value["digest"] = AUDIT.canonical_digest({k: v for k, v in value.items() if k != "digest"})
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "candidate version does not match saved candidates")


def test_v3_candidate_hash_binds_exact_reviewed_rule_and_path_maps():
    value = snapshot(1, 1.)
    value.update(schema="mr3-observation-v2", path_maps={name: {} for name in AUDIT.ROBOTS},
                 candidate_rule=dict(AUDIT.CANDIDATE_RULE_V3))
    expected = AUDIT.canonical_digest({key: value[key] for key in (
        "epoch", "map_version", "sequence", "candidates", "path_maps", "candidate_rule")})
    assert AUDIT.candidate_digest(value) == expected
    value["path_maps"]["tb1"]["version"] = 9
    assert AUDIT.candidate_digest(value) != expected


@pytest.mark.parametrize("change", [
    {"version": "unknown"}, {"goal_xy_tolerance_m": .25},
    {"frontier_staging_max_m": True}, {"frontier_staging_max_m": 1}, {"extra_rule": 1.},
])
def test_unknown_or_changed_v3_rule_is_rejected_even_if_self_signed(change):
    value = snapshot(1, 1.)
    value.update(schema="mr3-observation-v2", path_maps={name: {} for name in AUDIT.ROBOTS},
                 candidate_rule={**AUDIT.CANDIDATE_RULE_V3, **change})
    with pytest.raises(ValueError, match="candidate rule"):
        AUDIT.candidate_digest(value)


def test_legacy_observation_cannot_carry_a_v3_candidate_rule():
    value = snapshot(1, 1.)
    value["candidate_rule"] = dict(AUDIT.CANDIDATE_RULE_V3)
    with pytest.raises(ValueError, match="candidate rule"):
        AUDIT.candidate_digest(value)


def test_acceptance_without_estimated_movement_is_not_navigation_execution_proof(tmp_path):
    rows = evidence(tmp_path)
    for row in rows:
        if row["kind"] == "observation":
            for robot in row["payload"]["robots"]:
                robot["x"] = robot["y"] = 0.
    upgrade_v2(rows)
    save_rows(tmp_path, rows)
    result = AUDIT.audit_run(tmp_path)
    assert not result["passed"]
    assert all(value == 0. for value in result["estimated_snapshot_path_length_m"].values())
    assert sum("estimated snapshot path" in error for error in result["errors"]) == 3


def test_observation_tampering_is_detected(tmp_path):
    rows = evidence(tmp_path)
    rows[0]["payload"]["candidates"][0]["x"] = 100.
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "observation digest mismatch")


def test_action_must_replay_saved_candidate_version(tmp_path):
    rows = evidence(tmp_path)
    next(row for row in rows if row["kind"] == "action")["payload"]["candidate_version"] = "other"
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "different candidate version")


def test_duplicate_native_goal_and_keep_resubmit_are_detected(tmp_path):
    rows = evidence(tmp_path)
    event = dict(next(row for row in rows if row["kind"] == "native_send"))
    event["payload"] = {**event["payload"], "command_id": 2}
    rows.insert(4, event)
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "native goal was sent more than once")
    assert_failed(tmp_path, "KEEP command reached native send")


def test_new_protocol_goal_before_previous_terminal_fails(tmp_path):
    rows = evidence(tmp_path)
    event = next(row for row in rows if row["kind"] == "protocol")
    rows.insert(4, {**event, "payload": {**event["payload"], "goal_id": "episode-a:tb1:2"}})
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "second goal sent before old terminal")


def test_discretionary_cancel_must_obey_five_seconds_from_acceptance(tmp_path):
    rows = evidence(tmp_path)
    event = next(row for row in rows if row["payload"].get("type") == "cancel_goal")
    event["payload"]["stamp"] = 6.
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "5-second commitment")


def test_protocol_terminal_cannot_replace_missing_native_result(tmp_path):
    rows = evidence(tmp_path)
    rows = [row for row in rows if not (
        row["kind"] == "delivery" and row["payload"]["payload"].get("type") == "result")]
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "lacks a real action terminal")


def test_missing_protocol_terminal_retains_unknown_ownership(tmp_path):
    rows = evidence(tmp_path)
    rows = [row for row in rows if not (
        row["payload"].get("type") == "protocol_terminal"
        and row["payload"].get("robot") == "tb1")]
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "ownership remains unresolved")


def test_probe_without_real_cancel_does_not_claim_cancel_coverage(tmp_path):
    rows = evidence(tmp_path)
    rows = [row for row in rows if row["payload"].get("type") != "cancel_goal"]
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "real native cancellation")


@pytest.mark.parametrize(
    "mutation", ["missing_cancel_receipt", "negative_cancel_receipt", "success"])
def test_cancel_intent_or_success_race_does_not_prove_real_cancellation(tmp_path, mutation):
    rows = evidence(tmp_path)
    for row in rows:
        if row["kind"] == "delivery":
            receipt = row["payload"]["payload"]
            if receipt.get("type") == "cancel":
                if mutation == "missing_cancel_receipt":
                    receipt["type"] = "other"
                elif mutation == "negative_cancel_receipt":
                    receipt["value"] = False
            elif receipt.get("type") == "result" and mutation == "success":
                receipt["value"] = 4
        elif row["payload"].get("type") == "protocol_terminal" and mutation == "success":
            row["payload"]["status"] = "SUCCEEDED"
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "positive cancel receipt followed by CANCELED terminal")


def test_missing_rejection_probe_fails(tmp_path):
    rows = evidence(tmp_path)
    rows = [row for row in rows if row["payload"].get("reason") != "masked_action"]
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "missing rejection probes: masked_action")


def test_native_child_failure_is_not_hidden_by_parent_exit_zero(tmp_path):
    evidence(tmp_path)
    (tmp_path / "launch.log").write_text(
        NATIVE_LOG + "[ERROR] [gzserver]: process has died [exit code -6]\n")
    assert_failed(tmp_path, "native launch failures")


@pytest.mark.parametrize("change", [
    lambda text: text.replace("cleanly [pid 123]", "cleanly [pid 124]"),
    lambda text: text.replace("[gzserver-4]: process has finished",
                              "[gzserver-5]: process has finished"),
    lambda text: text + "[INFO] [gzserver-5]: process started with pid [789]\n",
    lambda text: text.replace("[INFO] [gzserver-4]: process has finished cleanly [pid 123]\n", ""),
])
def test_native_server_clean_exit_must_match_unique_started_identity(tmp_path, change):
    evidence(tmp_path)
    (tmp_path / "launch.log").write_text(change(NATIVE_LOG))
    assert_failed(tmp_path, "native gzserver unique start/clean-exit identity is not proven")


def test_native_cli_clean_exit_must_match_unique_started_identity(tmp_path):
    evidence(tmp_path)
    (tmp_path / "launch.log").write_text(
        NATIVE_LOG.replace("cleanly [pid 456]", "cleanly [pid 457]"))
    assert_failed(tmp_path, "native mr3_gazebo_native_stop unique start/clean-exit identity")


@pytest.mark.parametrize("change,error", [
    ({"native_cli_pid": 999}, "receipt CLI pid differs"),
    ({"server_clean_exit_recorded": False}, "does not confirm server clean exit"),
])
def test_native_stop_receipt_is_bound_to_log_identity(tmp_path, change, error):
    evidence(tmp_path)
    path = tmp_path / "native_stop.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), **change}))
    assert_failed(tmp_path, error)


def test_zero_native_goals_cannot_pass_scripted_navigation_probe(tmp_path):
    rows = evidence(tmp_path)
    rows = [row for row in rows if row["kind"] not in ("native_send", "delivery")]
    save_rows(tmp_path, rows)
    assert_failed(tmp_path, "native accept receipts do not cover all three robots")
    assert_failed(tmp_path, "real native cancellation")


def test_contact_gate_is_explicit_and_accepts_healthy_interrupted_schema4(tmp_path):
    evidence(tmp_path)
    assert not AUDIT.audit_run(tmp_path, require_contact_monitoring=True)["passed"]
    contact = {"schema_version": 4, "robot_count": 3, "success": False,
               "termination_reason": "shutdown", "collision_events": 0,
               "collision_monitoring_active": True, "collision_monitoring_fresh": True,
               "navigation_protocol_closed": False, "contact_component_count_per_robot": 6}
    (tmp_path / "episode-a.json").write_text(json.dumps(contact))
    fields = {"received": 10, "published": 10, "raw_states": 10, "compact_states": 1,
              "sequence_observed": 10, "sequence_unavailable": 0, "publisher_count": 1,
              "sequence_gaps": 0, "sequence_duplicates": 0, "sequence_regressions": 0}
    components = ("base", "lidar", "wheel_left", "wheel_right",
                  "caster_back_left", "caster_back_right")
    raw_summary = {"publication_sequence_supported": True,
                   "topics": {f"{robot}/{component}": fields
                              for robot in AUDIT.ROBOTS for component in components}}
    (tmp_path / "launch.log").write_text(
        NATIVE_LOG + "MR3_CONTACT_REDUCER_SUMMARY " + json.dumps(raw_summary))
    result = AUDIT.audit_run(tmp_path, require_contact_monitoring=True)
    assert result["passed"], result["errors"]
    assert result["contact_monitoring"]["passed"]
    assert not result["contact_monitoring"]["task_success_claimed"]


def test_cli_refuses_to_overwrite_canonical_audit(tmp_path):
    evidence(tmp_path)
    assert AUDIT.main([str(tmp_path)]) == 0
    original = (tmp_path / "audit.json").read_bytes()
    with pytest.raises(SystemExit):
        AUDIT.main([str(tmp_path)])
    assert (tmp_path / "audit.json").read_bytes() == original
    assert AUDIT.main([str(tmp_path), "--output", str(tmp_path / "audit_second.json")]) == 0
