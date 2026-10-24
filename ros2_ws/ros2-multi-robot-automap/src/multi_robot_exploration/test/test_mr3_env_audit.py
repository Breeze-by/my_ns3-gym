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


def terminal_samples(*, reused):
    """Two actual commands then either a late notice or a new 20ms snapshot."""
    samples = transitions()
    last = samples[-1]
    last.update(terminated=False, truncated=False)
    last["info"]["reason"] = None
    last["info"]["reward_diagnostics"].update(terminated=False, truncated=False)
    if reused:
        last = copy.deepcopy(last)
        samples.append(last)
        boundary = last["snapshot"]["source_stamp"]
        last["info"].update(terminal_observation_reused=True, action_submitted=False,
                            requested_action=888, command=None, dt=0., physical_dt=0.)
        sequence, start, dt = 3, boundary, 0.
    else:
        start, dt, sequence = 11., .02, 2
        boundary = start + dt
        last["snapshot"]["source_stamp"] = boundary
        last["snapshot"]["digest"] = AUDIT.canonical_digest(
            {key: value for key, value in last["snapshot"].items() if key != "digest"})
        # No new 10Hz state arrives during this actual 20ms interval.
        last["info"]["watermarks"]["state_sequence"] = 2
        last["info"].update(dt=dt, physical_dt=dt)
    last.update(terminated=True, truncated=False, reward=-20.)
    last["info"]["reason"] = "navigation_failure"
    last["info"]["reward_diagnostics"].update(
        sequence=sequence, reward=-20., terminated=True, truncated=False,
        reason="navigation_failure", step_start=start, effective_step_end=boundary,
        requested_step_end=boundary, delta_sim_time=dt, new_correct_free_cells=0,
        reward_terms={"coverage": 0., "failure": -20.},
        map_pairing_scope="terminal_evaluator_frozen_before_drain")
    return samples


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
                         "reward_sum": -.02, "terminated": False, "truncated": True,
                         "wall_sec_including_startup_and_closure": 3. + index,
                         "transition_wall_sec": 2.})
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


def add_initial_inputs_handshake(directory, change=None, omit_record=False):
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["reset_handshake"] = "delivered_inputs_before_pause-v1"
    path.write_text(json.dumps(metadata))
    ack = {"schema": "mr3-initial-inputs-ready-v1", "epoch": EPOCH, "stamp": 9.8,
           "state_sequence": 1, "map_payload_sha256": SHA, "map_version": 1,
           "map_source_stamp": 9.5, "map_received_stamp": 9.7,
           "robots": [{"name": name, "source_stamp": 9.7, "received_stamp": 9.75}
                      for name in AUDIT.ROBOTS],
           "map_sources": {name: {"sequence": 1, "version": 1, "source_stamp": 9.5,
                                  "received_stamp": 9.7, "payload_sha256": SHA}
                           for name in AUDIT.ROBOTS}}
    if change:
        change(ack)
    samples = transitions()
    samples[0]["info"]["initial_inputs_ready"] = ack
    (directory / "transitions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in samples))
    rows = adapter_rows(samples)
    if not omit_record:
        rows.append({"kind": "initial_inputs_ready", "stamp": ack["stamp"],
                     "epoch": EPOCH, "payload": ack})
    rows.sort(key=lambda row: row["stamp"])
    (directory / "adapter.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


class AuditEvidenceTests(unittest.TestCase):
    def test_late_terminal_replays_exact_snapshot_without_fabricating_a_command(self):
        samples = terminal_samples(reused=True)
        detail = AUDIT.audit_transitions(samples, physics(), EPOCH)
        self.assertEqual(detail["zero_duration_terminal_count"], 1)
        self.assertEqual(detail["submitted_action_count"], 2)
        rows = adapter_rows(transitions())
        result = AUDIT.audit_protocol(rows, samples, EPOCH)
        self.assertEqual(result["accepted_action_count"], 2)
        invented = copy.deepcopy(next(row for row in rows if row["kind"] == "action"))
        invented["stamp"] = 12.
        invented["payload"]["command_id"] = 3
        rows.append(invented)
        rows.sort(key=lambda row: row["stamp"])
        with self.assertRaisesRegex(ValueError, "lacks sampled command"):
            AUDIT.audit_protocol(rows, samples, EPOCH)

    def test_zero_terminal_rejects_refreshed_delivery_changed_snapshot_or_action(self):
        variants = (
            ("new_delivery", lambda row: row["info"]["watermarks"].update(state_sequence=4)),
            ("new_action", lambda row: row["info"].update(action_submitted=True)),
            ("command", lambda row: row["info"].update(command={"action": 888})),
            ("nonterminal", lambda row: row.update(terminated=False)),
            ("old_reward_end", lambda row: row["info"]["reward_diagnostics"].update(
                effective_step_end=12. - 1e-9)),
            ("nonzero_dt", lambda row: row["info"].update(dt=.001)),
            ("wrong_requested_type", lambda row: row["info"].update(requested_action=True)),
            ("coverage_reward", lambda row: row["info"]["reward_diagnostics"][
                "reward_terms"].update(coverage=1.)),
            ("new_correct_cells", lambda row: row["info"]["reward_diagnostics"].update(
                new_correct_free_cells=1)),
        )
        for label, change in variants:
            with self.subTest(case=label):
                samples = terminal_samples(reused=True)
                change(samples[-1])
                with self.assertRaises(ValueError):
                    AUDIT.audit_transitions(samples, physics(), EPOCH)
        samples = terminal_samples(reused=True)
        samples[-1]["snapshot"]["robots"][0]["x"] = 1.
        samples[-1]["snapshot"]["digest"] = AUDIT.canonical_digest({
            key: value for key, value in samples[-1]["snapshot"].items() if key != "digest"})
        with self.assertRaisesRegex(ValueError, "unchanged-snapshot"):
            AUDIT.audit_transitions(samples, physics(), EPOCH)

    def test_real_short_terminal_uses_new_snapshot_but_may_keep_last_10hz_state(self):
        samples = terminal_samples(reused=False)
        detail = AUDIT.audit_transitions(samples, physics(), EPOCH)
        self.assertEqual(detail["zero_duration_terminal_count"], 0)
        self.assertEqual(detail["submitted_action_count"], 2)
        self.assertEqual(detail["final_physical_dt"], .02)
        samples[-1]["terminated"] = False
        samples[-1]["truncated"] = True
        samples[-1]["info"]["reward_diagnostics"].update(terminated=False, truncated=True)
        with self.assertRaisesRegex(ValueError, "state delivery sequence"):
            AUDIT.audit_transitions(samples, physics(), EPOCH)
        samples = terminal_samples(reused=False)
        samples[-1]["snapshot"] = copy.deepcopy(samples[-2]["snapshot"])
        with self.assertRaisesRegex(ValueError, "state delivery sequence|observation sequence"):
            AUDIT.audit_transitions(samples, physics(), EPOCH)

    def test_terminal_probe_tail_accounting_is_separate_from_normal_comparison(self):
        for index, reused in enumerate((False, True)):
            detail = AUDIT.audit_transitions(terminal_samples(reused=reused), physics(), EPOCH)
            # The native declaration uses three complete initial steps, then its
            # fourth tail; this local fixture isolates the tail and adds counts.
            detail.update(transition_count=4, submitted_action_count=4 - int(reused))
            cell = {"terminal_sample": {
                "dt": detail["final_dt"], "physical_dt": detail["final_physical_dt"],
                "terminal_observation_reused": reused, "action_submitted": not reused}}
            result = AUDIT.audit_terminal_probe_cell(detail, cell, index, True)
            self.assertFalse(result["normal_comparison_credit"])
            for field, value in (("final_physical_dt", .04),
                                 ("final_action_submitted", reused),
                                 ("submitted_action_count", 5)):
                tampered = {**detail, field: value}
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    AUDIT.audit_terminal_probe_cell(tampered, cell, index, True)
        metadata = {"terminal_probe": True, "schedule": [["open", 101]] * 2}
        self.assertFalse(AUDIT.comparison_statistics(metadata, {})["eligible"])

    def test_terminal_probe_requires_independent_exact_boundary_and_diagnostic_reason(self):
        samples = terminal_samples(reused=False)
        stamp = samples[-1]["snapshot"]["source_stamp"]
        target = AUDIT.nanoseconds(stamp)
        notice = {"epoch": EPOCH, "end_sim_time_sec": stamp,
                  "termination_reason": "navigation_failure"}
        records = [{"kind": "sent", "epoch": EPOCH, "request_id": "failure1",
                    "target_time_ns": target, "reason": "P1C_DIAGNOSTIC_FAILURE"},
                   {"kind": "terminal_received", **notice}]
        adapter = [{"kind": kind, "epoch": EPOCH, "stamp": stamp, "payload": notice}
                   for kind in ("task_terminal_received", "task_terminal")]
        evaluator = {**notice, "control_failure": "P1C_DIAGNOSTIC_FAILURE"}
        proof = AUDIT.audit_terminal_probe_events(records, adapter, samples, evaluator, EPOCH)
        self.assertEqual(proof["target_time_ns"], target)
        cases = ("request_epoch", "target_ns", "missing_adapter", "wrong_adapter",
                 "missing_evaluator_failure", "wrong_terminal_time")
        for case in cases:
            with self.subTest(case=case):
                trial_records, trial_adapter, trial_evaluator = copy.deepcopy(
                    (records, adapter, evaluator))
                if case == "request_epoch":
                    trial_records[0]["epoch"] = "foreign"
                elif case == "target_ns":
                    trial_records[0]["target_time_ns"] += 1
                elif case == "missing_adapter":
                    trial_adapter.pop()
                elif case == "wrong_adapter":
                    trial_adapter[0]["payload"]["epoch"] = "foreign"
                elif case == "missing_evaluator_failure":
                    trial_evaluator.pop("control_failure")
                else:
                    trial_records[1]["end_sim_time_sec"] += 1e-9
                with self.assertRaises(ValueError):
                    AUDIT.audit_terminal_probe_events(
                        trial_records, trial_adapter, samples, trial_evaluator, EPOCH)

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
            self.assertFalse(result["initial_inputs_ready"]["required"])
            self.assertFalse(result["initial_inputs_ready"]["proven"])

    def test_v3_ready_ack_binds_adapter_event_before_pause_and_snapshot_state_sequence(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_fixture(directory)
            add_initial_inputs_handshake(directory)
            result = AUDIT.audit_episode(directory)
            self.assertTrue(result["passed"], result["errors"])
            self.assertTrue(result["initial_inputs_ready"]["proven"])
            self.assertLessEqual(result["initial_inputs_ready"]["ack_stamp"],
                                 result["initial_inputs_ready"]["initial_pause_stamp"])

    def test_v3_declaration_rejects_missing_late_cross_epoch_future_or_unrecorded_ack(self):
        variants = (
            ("late", lambda ack: ack.update(stamp=10.1)),
            ("cross_epoch", lambda ack: ack.update(epoch="other")),
            ("snapshot_before_ack_state", lambda ack: ack.update(state_sequence=2)),
            ("bad_digest", lambda ack: ack.update(map_payload_sha256="z" * 64)),
            ("future_map", lambda ack: ack.update(map_received_stamp=10.1)),
            ("future_robot", lambda ack: ack["robots"][0].update(source_stamp=10.)),
        )
        for label, change in variants:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                write_fixture(directory)
                add_initial_inputs_handshake(directory, change)
                result = AUDIT.audit_episode(directory)
                self.assertFalse(result["passed"])
                self.assertTrue(any("handshake" in error for error in result["errors"]))
        for omit in ("worker_ack", "adapter_record", "record_mismatch"):
            with self.subTest(case=omit), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                write_fixture(directory)
                add_initial_inputs_handshake(directory, omit_record=omit == "adapter_record")
                if omit == "worker_ack":
                    path = directory / "transitions.jsonl"
                    rows = [json.loads(line) for line in path.read_text().splitlines()]
                    del rows[0]["info"]["initial_inputs_ready"]
                    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                elif omit == "record_mismatch":
                    path = directory / "adapter.jsonl"
                    rows = [json.loads(line) for line in path.read_text().splitlines()]
                    rows[0]["payload"]["map_version"] = 999
                    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                result = AUDIT.audit_episode(directory)
                self.assertFalse(result["passed"])
                self.assertTrue(any("handshake" in error for error in result["errors"]))

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

    def test_waited_unsampled_stop_cli_has_alternative_exit_proof_without_fake_proc_row(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_fixture(directory)
            path = directory / "supervisor_shutdown.json"
            shutdown = json.loads(path.read_text())
            shutdown["owned_processes_seen"] = [
                row for row in shutdown["owned_processes_seen"] if row["pid"] != 333]
            path.write_text(json.dumps(shutdown))
            before = path.read_bytes()
            result = AUDIT.audit_episode(directory)
            self.assertTrue(result["passed"], result["errors"])
            alternative = result["closure"]["unsampled_stop_cli_alternative_evidence"]
            self.assertEqual(len(alternative), 1)
            self.assertEqual(alternative[0]["pid"], 333)
            self.assertEqual(alternative[0]["matched_owned_server_pid"], 222)
            self.assertFalse(alternative[0]["proc_sample_observed"])
            self.assertNotIn("start_ticks", alternative[0])
            self.assertEqual(result["processes"]["owned_pid_identities"],
                             [[111, 11100], [222, 22200]])
            self.assertEqual(path.read_bytes(), before)

    def test_unsampled_stop_cli_rejects_missing_exit_wrong_pid_server_or_other_child(self):
        cases = ("cli_not_clean", "wrong_cli_pid", "server_pid_mismatch", "server_not_owned",
                 "other_child_missing", "wrong_method", "nonzero_returncode")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                write_fixture(directory)
                shutdown_path = directory / "supervisor_shutdown.json"
                shutdown = json.loads(shutdown_path.read_text())
                shutdown["owned_processes_seen"] = [
                    row for row in shutdown["owned_processes_seen"] if row["pid"] != 333]
                log_path = directory / "launch.log"
                log = log_path.read_text()
                native_path = directory / "native_stop.json"
                native = json.loads(native_path.read_text())
                if case == "cli_not_clean":
                    log = log.replace(
                        "[INFO] [mr3_gazebo_native_stop-2]: "
                        "process has finished cleanly [pid 333]\n",
                        "")
                elif case == "wrong_cli_pid":
                    native["native_cli_pid"] = 444
                elif case == "server_pid_mismatch":
                    log = log.replace("gzserver-1]: process has finished cleanly [pid 222]",
                                      "gzserver-1]: process has finished cleanly [pid 999]")
                elif case == "server_not_owned":
                    shutdown["owned_processes_seen"] = [
                        row for row in shutdown["owned_processes_seen"] if row["pid"] != 222]
                elif case == "other_child_missing":
                    log += ("[INFO] [other_child-3]: process started with pid [444]\n"
                            "[INFO] [other_child-3]: process has finished cleanly [pid 444]\n")
                elif case == "wrong_method":
                    native["method"] = "unowned_cli"
                elif case == "nonzero_returncode":
                    native["returncode"] = 1
                shutdown_path.write_text(json.dumps(shutdown))
                native_path.write_text(json.dumps(native))
                log_path.write_text(log)
                result = AUDIT.audit_episode(directory)
                self.assertFalse(result["passed"], result)
                self.assertTrue(any("closure" in error for error in result["errors"]),
                                result["errors"])

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
            self.assertEqual(result["wall_sec_including_all_attempts"], 10.)
            self.assertEqual(result["comparison"]["denominator_wall_sec"], 7.)
            self.assertAlmostEqual(result["comparison"]["effective_transition_per_wall_sec"],
                                   4 / 7)
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
                    "freeze": "same", "schedule": [["open", 101], ["open", 101]],
                    "steps_per_episode": 16, "comparison": {"eligible": True}}
                   for n in (1, 2, 4)]
        results[0]["schedule"] += [["rooms", 202], ["corridors", 303]]
        with patch.object(AUDIT, "audit_benchmark", side_effect=copy.deepcopy(results)):
            self.assertTrue(AUDIT.audit_matrix(["one", "two", "four"])["passed"])
        results[1]["freeze"] = "other"
        results[2]["schedule"] = [["rooms", 101]]
        with patch.object(AUDIT, "audit_benchmark", side_effect=results):
            result = AUDIT.audit_matrix(["one", "two", "four"])
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["errors"]), 2)

    def test_comparison_excludes_slow_cross_scene_reset_regressions(self):
        def cell(scene, seed, wall):
            return {"scene": scene, "seed": seed, "transitions": 16, "terminated": False,
                    "truncated": True, "wall_sec_including_startup_and_closure": wall,
                    "transition_wall_sec": 2.}

        metadata = {"workers": 1, "steps_per_episode": 16,
                    "schedule": [["open", 101], ["open", 101], ["rooms", 202], ["corridors", 303]]}
        worker = {"worker_id": 0, "episodes": [
            cell("open", 101, 10.), cell("open", 101, 20.),
            cell("rooms", 202, 1000.), cell("corridors", 303, 2000.)]}
        summary = {"workers_results": [worker], "wall_sec_including_all_attempts": 4000.}
        result = AUDIT.comparison_statistics(metadata, summary)
        self.assertEqual(result["valid_transitions"], 32)
        self.assertEqual(result["denominator_wall_sec"], 30.)
        self.assertAlmostEqual(result["effective_transition_per_wall_sec"], 32 / 30)
        self.assertEqual(result["reset_regression_only_transitions"], 32)
        self.assertFalse(result["exact_end_to_end_process_span"])
        self.assertIsNone(result["final_supervisor_cleanup_wall_sec"])
        worker["episodes"][3]["wall_sec_including_startup_and_closure"] = 20000.
        unchanged = AUDIT.comparison_statistics(metadata, summary)
        self.assertEqual(result, unchanged)

    def test_parallel_comparison_uses_elapsed_bottleneck_not_worker_time_sum(self):
        metadata = {"workers": 2, "steps_per_episode": 16,
                    "schedule": [["open", 101], ["open", 101]]}
        workers = []
        for worker_id, durations in enumerate(((4., 6.), (8., 12.))):
            workers.append({"worker_id": worker_id, "episodes": [
                {"scene": "open", "seed": 101, "transitions": 16, "terminated": False,
                 "truncated": True, "wall_sec_including_startup_and_closure": duration,
                 "transition_wall_sec": 1.} for duration in durations]})
        summary = {"workers_results": workers, "wall_sec_including_all_attempts": 22.}
        result = AUDIT.comparison_statistics(metadata, summary)
        self.assertEqual(result["valid_transitions"], 64)
        self.assertEqual(result["denominator_wall_sec"], 20.)
        self.assertEqual(result["effective_transition_per_wall_sec"], 3.2)
        workers[0]["episodes"][0]["wall_sec_including_startup_and_closure"] = .5
        with self.assertRaisesRegex(ValueError, "elapsed times"):
            AUDIT.comparison_statistics(metadata, summary)

    def test_comparison_rejects_wrong_prefix_budget_or_extra_parallel_scenes(self):
        results = [{"passed": True, "workers": n, "fault_probe": False, "deadline_probe": False,
                    "freeze": "same", "schedule": [["open", 101], ["open", 101]],
                    "steps_per_episode": 16, "comparison": {"eligible": True}}
                   for n in (1, 2, 4)]
        results[2]["steps_per_episode"] = 8
        with patch.object(AUDIT, "audit_benchmark", side_effect=results):
            self.assertFalse(AUDIT.audit_matrix(["one", "two", "four"])["passed"])
        metadata = {"workers": 2, "steps_per_episode": 16,
                    "schedule": [["open", 101], ["open", 101], ["rooms", 202], ["corridors", 303]]}
        with self.assertRaisesRegex(ValueError, "serial reset regression"):
            AUDIT.comparison_statistics(metadata, {})
        metadata["schedule"] = [["rooms", 101], ["open", 101]]
        self.assertFalse(AUDIT.comparison_statistics(metadata, {})["eligible"])

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
