"""Independent artifact fixtures for publication/guard/storage/plant separation."""

import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning import plant_probe_audit as audit


FREEZE = "a" * 40
EPOCH = "fixture-epoch"
ORIGIN = 10_005_000_000  # A valid relative phase need not be absolute-20ms aligned.
SOURCE = "b" * 64


def write(path, value):
    path.write_text(json.dumps(value) + "\n")


def lines(path, rows):
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")


def mutate(path, operation):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    operation(rows)
    lines(path, rows)


def fixture(root, arm):
    write(root / "metadata.json", {"epoch": EPOCH, "freeze": FREEZE, "plant_stimulus_arm": arm})
    lines(root / "transitions.jsonl", [{"kind": "reset", "info": {
        "epoch": EPOCH, "release_time_ns": ORIGIN}}])
    graph = {"valid": True, "scope": "graph_at_callback", "topic": "/tb3/cmd_vel_unguarded", "endpoints": [{
        "namespace": "/tb3", "node": "velocity_smoother", "endpoint_gid": "12" * 24,
        "topic_type": "geometry_msgs/msg/Twist"}]}
    receipt_graph = {"scope": "graph_at_callback_not_per_packet_identity",
                     "topic": "/motion_safety/diagnostic_request_receipt", "endpoints": [{
                         "namespace": "/", "node": "motion_safety", "type": "std_msgs/msg/String",
                         "endpoint_gid": "34" * 24}]}
    stimulus, guard, phases, physics = [], [], [], []
    drivers = {robot: [] for robot in audit.ROBOTS}
    bootstrap = {"epoch": EPOCH, "kind": "advance_permitted", "control_kind": "bootstrap_zero",
                 "start_time_ns": ORIGIN - audit.QUANTUM, "request_id": "bootstrap", "steps": 20}
    phases.append(bootstrap)

    def physical(clock, request):
        return {"epoch": EPOCH, "request_id": request, "steps": 20, "step_ns": audit.TICK,
                "ok": True, "paused": True, "start_time_ns": clock,
                "end_time_ns": clock + audit.QUANTUM, "start_iterations": clock // audit.TICK,
                "end_iterations": clock // audit.TICK + 20}

    physics.append(physical(ORIGIN - audit.QUANTUM, "bootstrap"))
    for index, relative in enumerate(range(0, audit.CHAIN_END, audit.QUANTUM), 1):
        clock = ORIGIN + relative
        milli = audit.angular(arm, relative)
        request = {"epoch": EPOCH, "arm": arm, "sequence": index, "clock_ns": clock,
                   "angular_millirad": milli}
        ack = {**request, "schema": "mr3-smoother-diagnostic-ack-v1", "robot": "tb3",
               "linear_x": 0., "publication_clock_ns": clock,
               "publication_started_wall_monotonic_ns": clock + 1,
               "publication_completed_wall_monotonic_ns": clock + 2,
               "output_topic": "/tb3/cmd_vel_unguarded",
               "completion_scope": "smoother_publication_only_not_guard_or_storage"}
        receipt = {"schema": "mr3-guard-diagnostic-receipt-v1", "epoch": EPOCH,
                   "robot": "tb3", "clock_ns": clock, "input_sequence": index,
                   "v": 0., "w": milli / 1000., "supported": True, "publisher_identity": graph}
        for offset, kind, payload in (
                (0, "source_request", {"request": request}),
                (3, "guard_request_receipt_received", {"receipt": receipt,
                                                        "receipt_publisher_graph": receipt_graph}),
                (4, "service_ack", {"ack": ack}),
                (5, "boundary_consumed", {"source_request": request, "smoother_ack": ack,
                                            "guard_receipt": receipt})):
            stimulus.append({"schema": "mr3-plant-stimulus-worker-v1", "epoch": EPOCH,
                             "arm": arm, "worker_clock_ns": clock,
                             "worker_physical_ns": clock, "origin_ns": ORIGIN,
                             "relative_ns": relative, "wall_monotonic_ns": clock + offset,
                             "kind": kind, **payload})
        actual_request = {"v": 0., "w": milli / 1000., "sequence": index,
                          "received_stamp": clock / 1e9, "supported": True,
                          "publisher_identity": graph}
        guard.append({"epoch": EPOCH, "kind": "raw_request", "record_sequence": len(guard) + 1,
                      "wall_monotonic_ns": clock + 2,
                      "payload": {"robot": "tb3", "request": actual_request}})
        # Real guard logging may finish after worker callback reception and before its decision.
        guard.append({"epoch": EPOCH, "kind": "diagnostic_request_receipt",
                      "record_sequence": len(guard) + 1, "wall_monotonic_ns": clock + 4,
                      "payload": receipt})
        statuses, outputs, sequences = {}, {}, {}
        for robot in audit.ROBOTS:
            w = milli / 1000. if robot == "tb3" else 0.
            decision = {"output": [0., w], "allow": True, "reason": "clear"}
            guard.append({"epoch": EPOCH, "kind": "decision", "record_sequence": len(guard) + 1,
                          "wall_monotonic_ns": clock + 6, "payload": {
                              "robot": robot, "clock_ns": clock, "decision_sequence": index,
                              "request": actual_request if robot == "tb3" else None,
                              "decision": decision, "ready": True}})
            status = {"schema": "mr3-drive-target-consumed-v1", "epoch": EPOCH,
                      "robot": robot, "clock_ns": clock, "source_clock_ns": clock,
                      "cmd_seq": index, "decision_sequence": index, "linear_x": 0., "angular_z": w}
            statuses[robot] = status
            outputs[robot] = {"linear_x": 0., "angular_z": w}
            sequences[robot] = index
            drivers[robot].extend([
                {"epoch": EPOCH, "robot": robot, "kind": "command_received",
                 "target_clock_ns": clock, "target_decision_sequence": index,
                 "cmd_seq": index, "desired_v": 0., "desired_w": w},
                {"epoch": EPOCH, "robot": robot, "kind": "status_publish",
                 "target_clock_ns": clock, "status": status}])
        phases.append({"epoch": EPOCH, "kind": "advance_permitted", "control_kind": "normal",
                       "start_time_ns": clock, "request_id": "q" + str(index), "steps": 20,
                       "receipts": statuses, "expected_motion": {
                           "decision_sequences": sequences, "outputs": outputs}})
        physics.append(physical(clock, "q" + str(index)))
    for robot in audit.ROBOTS:
        for relative in range(34_000_000, audit.CHAIN_END, 34_000_000):
            target_relative = relative // audit.QUANTUM * audit.QUANTUM
            sequence = target_relative // audit.QUANTUM + 1
            w = audit.angular(arm, target_relative) / 1000. if robot == "tb3" else 0.
            drivers[robot].append({"epoch": EPOCH, "robot": robot, "kind": "actuation",
                                  "sim_time_ns": ORIGIN + relative,
                                  "target_clock_ns": ORIGIN + target_relative,
                                  "target_decision_sequence": sequence, "cmd_seq": sequence,
                                  "desired_v": 0., "desired_w": w,
                                  "current_rim_mps": [0., 0.], "applied_rim_mps": [0., 0.]})
        lines(root / ("drive_" + robot + ".jsonl"), drivers[robot])
    lines(root / "plant_stimulus_worker.jsonl", stimulus)
    lines(root / "motion_safety.jsonl", guard)
    lines(root / "drive_phase_worker.jsonl", phases)
    lines(root / "physics.jsonl", physics)
    write(root / "physics_diagnostic_binding.json", {
        "schema": "mr3-physics-diagnostic-binding-v2", "epoch": EPOCH,
        "mode": "observer_only", "physics_intervention": "none_observer_only",
        "observer_paused_only": True, "observer_library": {"source_sha256": SOURCE}})
    write(root / "plant_fixture_binding.json", {
        "schema": "mr3-fixed-sparse-plant-fixture-v1", "epoch": EPOCH, "arm": arm,
        "world_path": "/fixture/open.world", "world_sha256": "c" * 64,
        "launch_source_sha256": "d" * 64,
        "spawn_argument_values": {robot: dict(zip(
            ("x_pose", "y_pose", "z_pose", "roll", "pitch", "yaw"),
            map(str, (*position, 0., 0., 0.)))) for robot, position in audit.SPAWNS.items()}})
    for robot in audit.ROBOTS:
        rows = [{"epoch": EPOCH, "robot": robot, "schema": "mr3-stop-response-observer-v1",
                 "kind": "configuration", "record_sequence": 1, "paused_only": True,
                 "read_only": True, "compiled_source_sha256": SOURCE,
                 "physics_type": "ode", "max_step_size_sec": .001,
                 "native_ode": {"available": True, "values": {"iters": 150}}}]
        for pair, relative in enumerate(range(audit.TICK, audit.CHAIN_END + audit.TICK, audit.TICK), 1):
            before = 2 * pair
            for phase in ("before_physics_after_collision",
                          "world_update_end_after_physics_and_pose_propagation"):
                rows.append({"epoch": EPOCH, "robot": robot,
                             "schema": "mr3-stop-response-observer-v1", "kind": "sample",
                             "record_sequence": len(rows) + 1, "sim_time_ns": ORIGIN + relative,
                             "world_iterations": (ORIGIN + relative) // audit.TICK,
                             "pair_sequence": pair, "before_record_sequence": before,
                             "phase": phase, "measurements_finite": True, "physics_enabled": True,
                             "native_ode": {"available": True, "values": {"iters": 150}},
                             "model": {"name": robot, "world_linear_velocity_xyz": [.002, 0., 0.],
                                       "world_pose": {"position_xyz": list(audit.SPAWNS[robot])}},
                             "joints_right_left": []})
        lines(root / ("physics_" + robot + ".jsonl"), rows)


class PlantProbeAuditTests(unittest.TestCase):
    def case(self, arm="pulse"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        fixture(root, arm)
        return root

    def test_two_realized_arms_are_valid_without_claiming_plant_pass(self):
        for arm in ("continuous", "pulse"):
            with self.subTest(arm=arm):
                result = audit.audit(self.case(arm), FREEZE, arm)
                self.assertEqual(result["status"], "VALID", result["errors"])
                self.assertFalse(result["plant_pass_claimed"])
                self.assertEqual(result["raw_response"]["tb3"]["complete_1ms_pairs"], 4000)
                self.assertEqual(len(result["raw_response"]["tb3"]["comparison_samples"]), 220)

    def test_storage_pulse_without_actual_wheel_consumption_is_incomplete(self):
        root = self.case()
        mutate(root / "drive_tb3.jsonl", lambda rows: rows.__setitem__(slice(None), [
            row for row in rows if not (row["kind"] == "actuation" and row["desired_w"] == 0.
                and ORIGIN + audit.PULSE_START <= row["sim_time_ns"] < ORIGIN + audit.PULSE_END)]))
        result = audit.audit(root, FREEZE, "pulse")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("wheel update did not consume pulse/continuous intervention",
                      result["layers"]["actual_wheel_actuation"]["incomplete"])

    def test_guard_rejection_is_incomplete_instead_of_a_fabricated_waveform_pass(self):
        root = self.case("continuous")
        target = ORIGIN + audit.PULSE_START
        def reject(rows):
            for row in rows:
                if row["kind"] == "decision" and row["payload"]["robot"] == "tb3" and row["payload"]["clock_ns"] == target:
                    row["payload"]["decision"].update(output=[0., 0.], allow=False, reason="peer_braking_nonclosing")
        mutate(root / "motion_safety.jsonl", reject)
        result = audit.audit(root, FREEZE, "continuous")
        self.assertFalse(result["layers"]["actual_guard_decisions"]["complete"])
        self.assertTrue(result["layers"]["actual_guard_decisions"]["incomplete"])
        self.assertFalse(result["passed"])

    def test_actual_guard_older_request_cannot_be_replaced_by_service_ack(self):
        root = self.case()
        def older(rows):
            for row in rows:
                if row["kind"] == "decision" and row["payload"]["robot"] == "tb3" and row["payload"]["clock_ns"] == ORIGIN + audit.PULSE_START:
                    row["payload"]["request"]["sequence"] -= 1
        mutate(root / "motion_safety.jsonl", older)
        result = audit.audit(root, FREEZE, "pulse")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertTrue(any("older/different" in value for value in result["layers"]["actual_guard_decisions"]["incomplete"]))

    def test_missing_one_ms_pair_is_incomplete_and_startup_is_not_required(self):
        root = self.case()
        mutate(root / "physics_tb3.jsonl", lambda rows: rows.__setitem__(slice(None), [
            row for row in rows if row.get("sim_time_ns") != ORIGIN + 2_201_000_000]))
        result = audit.audit(root, FREEZE, "pulse")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertTrue(any("1ms observer gap" in value for value in result["layers"]["passive_1ms_observation"]["incomplete"]))

    def test_forged_epoch_wrong_output_topic_and_physics_setter_binding_are_invalid(self):
        for fault in ("epoch", "topic", "profile"):
            with self.subTest(fault=fault):
                root = self.case()
                if fault == "epoch":
                    mutate(root / "drive_tb3.jsonl", lambda rows: rows[0].update(epoch="other"))
                elif fault == "topic":
                    def wrong_topic(rows):
                        for row in rows:
                            if row["kind"] == "service_ack":
                                row["ack"]["output_topic"] = "/tb3/cmd_vel"
                                break
                    mutate(root / "plant_stimulus_worker.jsonl", wrong_topic)
                else:
                    path = root / "physics_diagnostic_binding.json"
                    value = json.loads(path.read_text()); value["profile_library"] = "setter.so"
                    write(path, value)
                self.assertEqual(audit.audit(root, FREEZE, "pulse")["status"], "INVALID_EVIDENCE")

    def test_raw_response_exceedance_is_preserved_without_relabelling_validity_as_physics(self):
        root = self.case()
        def peak(rows):
            for row in rows:
                if row.get("sim_time_ns") == ORIGIN + 2_221_000_000:
                    row["model"]["world_linear_velocity_xyz"] = [.02, .003, 0.]
        mutate(root / "physics_tb3.jsonl", peak)
        result = audit.audit(root, FREEZE, "pulse")
        self.assertEqual(result["status"], "VALID", result["errors"])
        self.assertEqual(result["raw_response"]["tb3"]["samples_above_point01_mps"], 1)
        self.assertEqual(result["raw_response"]["tb3"]["comparison_samples"][100]["model"]["world_linear_velocity_xyz"], [.02, .003, 0.])

    def test_receipt_graph_must_be_unique_nonzero_stable_actual_guard(self):
        root = self.case()
        def forged(rows):
            for row in rows:
                if row["kind"] == "guard_request_receipt_received":
                    row["receipt_publisher_graph"]["endpoints"][0]["endpoint_gid"] = "00" * 24
                    break
        mutate(root / "plant_stimulus_worker.jsonl", forged)
        result = audit.audit(root, FREEZE, "pulse")
        self.assertEqual(result["status"], "INVALID_EVIDENCE")
        self.assertTrue(any("sole actual guard" in error for error in result["errors"]))

    def test_worker_receipt_requires_complete_original_guard_object(self):
        for fault in ("missing", "substituted"):
            with self.subTest(fault=fault):
                root = self.case()
                def change(rows):
                    if fault == "missing":
                        rows[:] = [row for row in rows if row["kind"] != "diagnostic_request_receipt"]
                    else:
                        next(row["payload"] for row in rows if row["kind"] == "diagnostic_request_receipt")["extra_original_field"] = "not-in-worker"
                mutate(root / "motion_safety.jsonl", change)
                result = audit.audit(root, FREEZE, "pulse")
                self.assertEqual(result["status"], "INCOMPLETE" if fault == "missing" else "INVALID_EVIDENCE")

    def test_full_four_second_rest_and_actual_sparse_pose_are_required(self):
        for fault in ("old_three_second_tail", "spawn_argument", "native_pose"):
            with self.subTest(fault=fault):
                root = self.case()
                if fault == "old_three_second_tail":
                    mutate(root / "physics_tb3.jsonl", lambda rows: rows.__setitem__(slice(None), [
                        row for row in rows if row.get("sim_time_ns", 0) <= ORIGIN + 3_000_000_000]))
                elif fault == "spawn_argument":
                    path = root / "plant_fixture_binding.json"
                    value = json.loads(path.read_text())
                    value["spawn_argument_values"]["tb3"]["x_pose"] = "0.5"
                    write(path, value)
                else:
                    def displaced(rows):
                        for row in rows:
                            if row.get("sim_time_ns") == ORIGIN + audit.TICK:
                                row["model"]["world_pose"]["position_xyz"][0] -= .2
                    mutate(root / "physics_tb3.jsonl", displaced)
                result = audit.audit(root, FREEZE, "pulse")
                self.assertEqual(result["status"], "INVALID_EVIDENCE" if fault == "spawn_argument" else "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
