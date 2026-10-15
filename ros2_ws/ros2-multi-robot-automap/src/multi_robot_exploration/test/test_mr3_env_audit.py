"""Independent saved-evidence fixtures: no ROS, Gazebo, conda or GPU execution."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("audit_mr3_env", SCRIPTS / "audit_mr3_env.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
EPOCH = "fixture_w0_e1"
SHA = "a" * 64


def snapshot(sequence):
    value = {
        "schema": "mr3-observation-v2", "epoch": EPOCH, "sequence": sequence,
        "map_version": sequence, "source_stamp": 9. + sequence,
        "candidates": [{"x": float(index), "y": 1.} for index in range(8)],
        "path_maps": {name: {"epoch": EPOCH} for name in AUDIT.ROBOTS},
        "robots": [{"name": name} for name in AUDIT.ROBOTS],
        "joint_action_mask": [action in (12, 888) for action in range(1000)],
    }
    keys = ("epoch", "map_version", "sequence", "candidates", "path_maps")
    value["candidate_version"] = AUDIT.canonical_digest({key: value[key] for key in keys})
    value["digest"] = AUDIT.canonical_digest(value)
    return value


def reward(index):
    value = {"schema": "mr3-reward-v1", "epoch": EPOCH, "sequence": index,
             "reward": 0. if index == 0 else -.01, "terminated": False,
             "truncated": index == 2, "step_start": 10. if index == 0 else 9. + index,
             "effective_step_end": 10. + index, "delta_sim_time": 0. if index == 0 else 1.,
             "map_watermark": {"payload_sha256": SHA}}
    if index == 0:
        value.update(kind="reward_reset_binding", reset_bound=True)
    else:
        value.update(requested_step_end=10. + index, expected_actor_map_sha256=SHA,
                     expected_map_paired=True, map_pairing_scope="current_actor_map_paired",
                     reward_terms={"time": -.01})
    return value


def physics():
    rows = []
    for index in range(102):
        start = 10 * AUDIT.NS + max(0, index - 1) * 20000000
        steps = 0 if index == 0 else 20
        rows.append({"epoch": EPOCH, "request_id": f"q{index + 1}", "ok": True,
                     "paused": True, "start_time_ns": start,
                     "end_time_ns": start + steps * 1000000,
                     "start_iterations": start // 1000000,
                     "end_iterations": start // 1000000 + steps,
                     "steps": steps, "step_ns": 1000000})
    return rows


def transitions():
    rows = []
    for index in range(3):
        diag = reward(index)
        info = {"epoch": EPOCH, "dt": 0. if index == 0 else 1.,
                "reward_diagnostics": diag,
                "watermarks": {"map_payload_sha256": SHA, "state_sequence": index + 1}}
        if index == 0:
            info.update(reset_kind="complete_process_rebuild", initial_pause_time_ns=10 * AUDIT.NS,
                        release_time_ns=10 * AUDIT.NS)
        else:
            old = snapshot(index)
            info.update(physical_dt=1., reason="external_sampler_limit" if index == 2 else None,
                        command={"epoch": EPOCH, "command_id": index,
                                 "observation_sequence": old["sequence"],
                                 "observation_digest": old["digest"],
                                 "created_at": 9. + index, "expires_at": 11. + index,
                                 "action": 12 if index == 1 else 888})
        rows.append({"kind": "reset" if index == 0 else "step", "snapshot": snapshot(index + 1),
                     "reward": diag["reward"], "terminated": False,
                     "truncated": index == 2, "info": info})
    return rows


def adapter_rows(samples):
    rows = []

    def event(kind, stamp, payload):
        rows.append({"kind": kind, "stamp": stamp, "epoch": EPOCH, "payload": payload})

    def receipt(name, goal_id, kind, value, now):
        event("delivery", now, {
            "source_stamp": now, "generated_stamp": now, "received_stamp": now,
            "stream": "receipt", "source": name,
            "payload": {"type": kind, "robot": name, "goal_id": goal_id, "value": value}})

    for index, sample in enumerate(samples):
        event("observation", sample["snapshot"]["source_stamp"], sample["snapshot"])
        if index == len(samples) - 1:
            continue
        command = samples[index + 1]["info"]["command"]
        now = command["created_at"]
        first = index == 0
        event("action", now, {"command_id": index + 1, "action": command["action"],
              "choices": [0, 1, 2] if first else [8, 8, 8],
              "observation_sequence": sample["snapshot"]["sequence"],
              "observation_digest": sample["snapshot"]["digest"],
              "candidate_version": sample["snapshot"]["candidate_version"],
              "results": {name: "sent" if first else "kept" for name in AUDIT.ROBOTS}})
        if first:
            for robot_index, name in enumerate(AUDIT.ROBOTS):
                goal_id = f"{EPOCH}:{name}:1"
                target = {"x": float(robot_index), "y": 1.}
                event("protocol", now, {
                    "type": "send_goal", "robot": name, "goal_id": goal_id,
                    "command_id": 1, "goal": target, "observation_version": 1, "expires_at": 12.})
                event("native_send", now, {
                    "robot": name, "goal_id": goal_id, "command_id": 1,
                    "pose": {"frame_id": "map", "stamp": now, **target,
                             "orientation": [0., 0., 0., 1.]}})
                receipt(name, goal_id, "accept", True, now + .02)
    for name in AUDIT.ROBOTS:
        goal_id = f"{EPOCH}:{name}:1"
        event("protocol", 12., {"type": "cancel_goal", "robot": name,
              "goal_id": goal_id, "reason": "task_stop"})
        receipt(name, goal_id, "cancel", True, 12.001)
        receipt(name, goal_id, "result", 5, 12.002)
        event("protocol", 12.003, {"type": "protocol_terminal", "robot": name,
              "goal_id": goal_id, "status": "CANCELED"})
    event("task_stopped", 12.02, {"epoch": EPOCH, "pending_goal_count": 0,
          "robot_names": list(AUDIT.ROBOTS), "navigation_failure": False})
    return sorted(rows, key=lambda row: row["stamp"])


def contact_fixture():
    raw = {"publication_sequence_supported": True, "topics": {}}
    components = {}
    for name in AUDIT.ROBOTS:
        components[name] = {}
        for part in AUDIT.COMPONENTS:
            raw["topics"][name + "/" + part] = {
                "received": 20, "published": 20, "raw_states": 20, "compact_states": 0,
                "sequence_observed": 20, "sequence_unavailable": 0, "publisher_count": 1,
                "sequence_gaps": 0, "sequence_duplicates": 0, "sequence_regressions": 0}
            components[name][part] = {
                "accepted_message_count": 20, "invalid_timestamp_count": 0,
                "duplicate_message_count": 0, "health_reason": "", "source_age_sec": .02,
                "receipt_age_sec": .0, "max_source_gap_sec": .02, "max_receipt_gap_sec": .02}
    evaluator = {"schema_version": 4, "episode_id": EPOCH, "robot_count": 3,
                 "contact_component_count_per_robot": 6, "collision_events": 0,
                 "collision_monitoring_active": True, "collision_monitoring_fresh": True,
                 "success": False, "termination_reason": "training_external_truncation",
                 "contact_monitor_summary": {
                     "components": components, "fresh": True, "ever_unhealthy": False,
                     "latched_issues": {}, "max_age_sec": .5, "event_count": 0}}
    return evaluator, "MR3_CONTACT_REDUCER_SUMMARY " + json.dumps(raw) + "\n"


def write_fixture(directory):
    def save(name, value):
        (directory / name).write_text(json.dumps(value))

    def save_rows(name, value):
        (directory / name).write_text("".join(json.dumps(row) + "\n" for row in value))

    samples = transitions()
    owned = [{"pid": pid, "start_ticks": pid * 100, "state": "S"} for pid in (111, 222, 333)]
    save("metadata.json", {"epoch": EPOCH, "freeze": "fixture", "scene": "open", "seed": 101})
    save("supervisor_metadata.json", {
        "epoch": EPOCH, "worker_identity": owned[0], "reset_kind": "complete_process_rebuild"})
    save("supervisor_shutdown.json", {
        "epoch": EPOCH, "worker_returncode": 0, "forced_shutdown": False, "failed_sample": False,
        "owned_processes_seen": owned, "remaining_owned_processes": [],
        "remaining_owned_zombies": []})
    save_rows("transitions.jsonl", samples)
    save_rows("physics.jsonl", physics())
    save_rows("adapter.jsonl", adapter_rows(samples))
    closed = {"epoch": EPOCH, "pending_goal_count": 0, "robot_names": list(AUDIT.ROBOTS),
              "navigation_failure": False}
    save("summary.json", {"epoch": EPOCH, "launch_returncode": 0,
                          "native_failures": [], "failures": [], "closed": closed})
    save("native_stop.json", {"returncode": 0, "method": "owned_launch_native_stop",
                              "native_cli_pid": 333, "server_clean_exit_recorded": True})
    evaluator, log = contact_fixture()
    save(EPOCH + ".json", evaluator)
    (directory / "launch.log").write_text(
        log +
        "[INFO] [gzserver-1]: process started with pid [222]\n"
        "[INFO] [mr3_gazebo_native_stop-2]: process started with pid [333]\n"
        "[INFO] [gzserver-1]: process has finished cleanly [pid 222]\n"
        "[INFO] [mr3_gazebo_native_stop-2]: process has finished cleanly [pid 333]\n")


def benchmark_fixture(directory):
    episodes, receipts = [], []
    for index in range(2):
        episode = directory / "worker0" / f"episode{index + 1:03d}_open_101"
        episode.mkdir(parents=True)
        epoch = f"fixture_w0_e{index + 1}"
        with patch.dict(globals(), EPOCH=epoch):
            write_fixture(episode)
        if index:
            # A full reset uses new PID/start identities for every owned child.
            for filename in ("supervisor_metadata.json", "supervisor_shutdown.json",
                             "native_stop.json"):
                path = episode / filename
                value = path.read_text()
                for pid in (111, 222, 333):
                    value = value.replace(str(pid), str(pid + 1000))
                path.write_text(value)
            path = episode / "launch.log"
            path.write_text(path.read_text().replace("222", "1222").replace("333", "1333"))
        receipts.append(json.loads((episode / "supervisor_shutdown.json").read_text()))
        episodes.append({"epoch": epoch, "scene": "open", "seed": 101, "transitions": 2,
                         "reward_sum": -.02, "terminated": False, "truncated": True})
    metadata = {"workers": 1, "robots_per_worker": 3, "freeze": "fixture",
                "schedule": [["open", 101], ["open", 101]], "steps_per_episode": 2,
                "fault_probe": False, "deadline_probe": False}
    summary = {**metadata, "passed": True, "valid_transitions": 4,
               "wall_sec_including_all_attempts": 10., "effective_transition_per_wall_sec": .4,
               "workers_results": [{"worker_id": 0, "episodes": episodes,
                                    "shutdown_receipts": receipts, "error": None}]}
    for filename, value in (("benchmark_metadata.json", metadata),
                            ("benchmark_summary.json", summary), ("resources.json", [{}])):
        (directory / filename).write_text(json.dumps(value))


class AuditEvidenceTests(unittest.TestCase):
    def test_complete_sampling_episode_is_not_a_task_success_claim(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_fixture(directory)
            result = AUDIT.audit_episode(directory)
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["transitions"]["transition_count"], 2)
            self.assertEqual(result["protocol"]["confirmed_cancellation_count"], 3)
            self.assertTrue(result["contacts"]["zero_contact"])
            self.assertFalse(result["contacts"]["task_success"])

    def test_tick_gap_request_identity_and_cross_epoch_are_rejected(self):
        for field, value in (("start_iterations", 10099), ("request_id", "q1"),
                             ("epoch", "old-epoch"), ("end_time_ns", 999999999)):
            rows = physics()
            rows[4][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                AUDIT.audit_physics(rows, EPOCH, 10 * AUDIT.NS)

    def test_one_second_clock_jump_without_matching_ticks_is_rejected(self):
        rows = physics()
        for row in rows[10:]:
            row["start_time_ns"] += AUDIT.NS
            row["end_time_ns"] += AUDIT.NS
        with self.assertRaisesRegex(ValueError, "continuity"):
            AUDIT.audit_physics(rows, EPOCH, 10 * AUDIT.NS)

    def test_reset_ledger_must_bind_sequence_zero_initial_map(self):
        for field, value in (("sequence", 1), ("reset_bound", False), ("reward", 3.)):
            rows = transitions()
            rows[0]["info"]["reward_diagnostics"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                AUDIT.audit_transitions(rows, physics(), EPOCH)
        rows = transitions()
        rows[0]["info"]["reward_diagnostics"]["map_watermark"]["payload_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "seq0"):
            AUDIT.audit_transitions(rows, physics(), EPOCH)

    def test_stale_reward_map_and_nonunit_normal_dt_are_rejected(self):
        rows = transitions()
        rows[1]["info"]["reward_diagnostics"]["map_watermark"]["payload_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "reward map"):
            AUDIT.audit_transitions(rows, physics(), EPOCH)
        rows = transitions()
        rows[1]["info"]["dt"] = .8
        with self.assertRaises(ValueError):
            AUDIT.audit_transitions(rows, physics(), EPOCH)

    def test_terminal_frozen_map_scope_and_detection_bound(self):
        rows = transitions()
        last = rows[-1]
        last["terminated"], last["truncated"] = True, False
        last["info"]["dt"] = .99
        diag = last["info"]["reward_diagnostics"]
        diag.update(terminated=True, truncated=False, effective_step_end=11.99,
                    delta_sim_time=.99, map_pairing_scope="terminal_evaluator_frozen_before_drain",
                    expected_map_paired=False)
        diag["map_watermark"]["payload_sha256"] = "b" * 64
        result = AUDIT.audit_transitions(rows, physics(), EPOCH)
        self.assertEqual(result["terminal_map_sha_exception_count"], 1)
        last["info"]["dt"] = .97
        diag.update(effective_step_end=11.97, delta_sim_time=.97)
        with self.assertRaisesRegex(ValueError, "20ms"):
            AUDIT.audit_transitions(rows, physics(), EPOCH)

    def test_native_pose_tamper_and_missing_cancel_receipt_fail(self):
        samples = transitions()
        rows = adapter_rows(samples)
        next(row["payload"] for row in rows if row["kind"] == "native_send")["pose"]["x"] = 99.
        with self.assertRaisesRegex(ValueError, "native goal coordinates"):
            AUDIT.audit_protocol(rows, samples, EPOCH)
        rows = [row for row in adapter_rows(samples) if not (
            row["kind"] == "delivery" and row["payload"]["payload"]["type"] == "cancel")]
        with self.assertRaisesRegex(ValueError, "positive cancel"):
            AUDIT.audit_protocol(rows, samples, EPOCH)

    def test_commitment_violation_and_keep_resend_fail(self):
        samples = transitions()
        rows = adapter_rows(samples)
        next(row["payload"] for row in rows if row["kind"] == "protocol"
             and row["payload"]["type"] == "cancel_goal")["reason"] = "wait"
        with self.assertRaisesRegex(ValueError, "5s commitment"):
            AUDIT.audit_protocol(rows, samples, EPOCH)
        rows = adapter_rows(samples)
        goal = copy.deepcopy(next(row for row in rows if row["kind"] == "protocol"))
        goal["stamp"] = 11.1
        goal["payload"].update(command_id=2, goal_id=EPOCH + ":tb1:2")
        rows.append(goal)
        rows.sort(key=lambda row: row["stamp"])
        with self.assertRaisesRegex(ValueError, "KEEP/WAIT"):
            AUDIT.audit_protocol(rows, samples, EPOCH)

    def test_digest_tamper_and_missing_adapter_snapshot_fail(self):
        samples = transitions()
        samples[1]["snapshot"]["candidates"][0]["x"] = 99.
        with self.assertRaisesRegex(ValueError, "digest"):
            AUDIT.audit_transitions(samples, physics(), EPOCH)
        samples = transitions()
        rows = [row for row in adapter_rows(samples) if row["kind"] != "observation"]
        with self.assertRaisesRegex(ValueError, "snapshot absent"):
            AUDIT.audit_protocol(rows, samples, EPOCH)

    def test_contact_raw_gap_freshness_and_collision_are_distinct(self):
        evaluator, log = contact_fixture()
        log = log.replace('"sequence_gaps": 0', '"sequence_gaps": 1', 1)
        result = AUDIT.audit_contacts(evaluator, log, EPOCH)
        self.assertFalse(result["raw_sequence_audit_passed"])
        self.assertTrue(result["continuous_freshness_passed"])
        self.assertTrue(result["zero_contact"])
        evaluator, log = contact_fixture()
        evaluator["contact_monitor_summary"]["components"]["tb1"]["lidar"]["source_age_sec"] = .51
        result = AUDIT.audit_contacts(evaluator, log, EPOCH)
        self.assertTrue(result["raw_sequence_audit_passed"])
        self.assertFalse(result["continuous_freshness_passed"])
        evaluator, log = contact_fixture()
        evaluator["collision_events"] = 1
        evaluator["contact_monitor_summary"]["event_count"] = 1
        self.assertFalse(AUDIT.audit_contacts(evaluator, log, EPOCH)["zero_contact"])

    def test_zombie_receipt_prevents_complete_episode_credit(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_fixture(directory)
            path = directory / "supervisor_shutdown.json"
            value = json.loads(path.read_text())
            value["remaining_owned_zombies"] = [{"pid": 222, "start_ticks": 22200}]
            path.write_text(json.dumps(value))
            result = AUDIT.audit_episode(directory)
            self.assertFalse(result["passed"])
            self.assertFalse(result["complete_episode_credit"])
            self.assertTrue(any("zombies" in error for error in result["errors"]))

    def test_declared_fault_has_prefix_and_cleanup_but_no_complete_episode_credit(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_fixture(directory)
            samples = transitions()[:2]
            path = directory / "transitions.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in samples))
            rows = [row for row in adapter_rows(transitions()) if row["stamp"] <= 11.
                    and not (row["kind"] == "action" and row["payload"]["command_id"] == 2)]
            (directory / "adapter.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows))
            path = directory / "supervisor_shutdown.json"
            value = json.loads(path.read_text())
            value.update(failed_sample=True, forced_shutdown=True, worker_returncode=-9)
            path.write_text(json.dumps(value))
            result = AUDIT.audit_episode(directory, expected_fault=True)
            self.assertTrue(result["passed"], result["errors"])
            self.assertFalse(result["complete_episode_credit"])
            self.assertFalse(result["transitions"]["complete"])
            self.assertTrue(result["processes"]["forced_cleanup"])

    def test_benchmark_reset_identity_and_all_attempts_denominator(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            benchmark_fixture(directory)
            result = AUDIT.audit_benchmark(directory)
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["complete_episode_count"], 2)
            path = directory / "benchmark_summary.json"
            value = json.loads(path.read_text())
            value["effective_transition_per_wall_sec"] = .8
            path.write_text(json.dumps(value))
            result = AUDIT.audit_benchmark(directory)
            self.assertFalse(result["passed"])
            self.assertTrue(any("throughput" in error for error in result["errors"]))

    def test_benchmark_cannot_reuse_epoch_or_cleanup_receipt(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            benchmark_fixture(directory)
            path = directory / "benchmark_summary.json"
            value = json.loads(path.read_text())
            worker = value["workers_results"][0]
            worker["episodes"][1]["epoch"] = worker["episodes"][0]["epoch"]
            worker["shutdown_receipts"][1] = worker["shutdown_receipts"][0]
            path.write_text(json.dumps(value))
            result = AUDIT.audit_benchmark(directory)
            self.assertFalse(result["passed"])
            self.assertTrue(any("epoch" in error for error in result["errors"]))
            self.assertTrue(any("cleanup" in error for error in result["errors"]))

    def test_matrix_rejects_mixed_freeze_or_schedule(self):
        results = [{"passed": True, "workers": n, "fault_probe": False, "deadline_probe": False,
                    "freeze": "same", "schedule": [["open", 101]], "steps_per_episode": 16}
                   for n in (1, 2, 4)]
        with patch.object(AUDIT, "audit_benchmark", side_effect=copy.deepcopy(results)):
            self.assertTrue(AUDIT.audit_matrix(["one", "two", "four"])["passed"])
        results[1]["freeze"] = "other"
        results[2]["schedule"] = [["rooms", 101]]
        with patch.object(AUDIT, "audit_benchmark", side_effect=results):
            result = AUDIT.audit_matrix(["one", "two", "four"])
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["errors"]), 2)

    def test_audit_missing_evidence_fails_and_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.assertFalse(AUDIT.audit_episode(directory)["passed"])
            write_fixture(directory)
            output = directory / "audit.json"
            with patch("builtins.print"):
                self.assertEqual(AUDIT.main([str(directory), "--output", str(output)]), 0)
            before = output.read_bytes()
            with self.assertRaises(SystemExit):
                AUDIT.main([str(directory), "--output", str(output)])
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
