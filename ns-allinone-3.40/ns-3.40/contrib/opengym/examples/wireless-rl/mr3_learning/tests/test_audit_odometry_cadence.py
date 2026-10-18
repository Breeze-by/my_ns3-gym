"""Artifact-only regressions for independent publication, delivery and selection."""

import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning import audit_odometry_cadence as audit


FREEZE = "a" * 40
EPOCH = "cadence-fixture"
BEGIN = 1_000_000_000
END = BEGIN + 200_000_000


def write(path, value):
    path.write_text(json.dumps(value) + "\n")


def lines(path, values):
    with path.open("w") as stream:
        for value in values:
            stream.write(json.dumps(value) + "\n")


def mutate(path, operation):
    values = [json.loads(value) for value in path.read_text().splitlines()]
    operation(values)
    lines(path, values)


def message(clock):
    return {"header": {"stamp": {"sec": clock // 1_000_000_000,
                                  "nanosec": clock % 1_000_000_000}, "frame_id": "odom"},
            "child_frame_id": "base_footprint", "pose": {"pose": {
                "position": {"x": clock / 1e12, "y": 0., "z": .01},
                "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}}, "covariance": [0.] * 36},
            "twist": {"twist": {"linear": {"x": .001, "y": .002, "z": 0.},
                                  "angular": {"x": 0., "y": 0., "z": .1}}, "covariance": [0.] * 36}}


def fixture(directory):
    write(directory / "metadata.json", {"epoch": EPOCH, "freeze": FREEZE})
    lines(directory / "transitions.jsonl", [
        {"kind": "reset", "info": {"release_time_ns": BEGIN}, "snapshot": {"source_stamp": BEGIN / 1e9}},
        {"kind": "step", "snapshot": {"source_stamp": END / 1e9}}])
    lines(directory / "physics.jsonl", [{"epoch": EPOCH, "steps": 20, "step_ns": 1_000_000,
                                         "ok": True, "paused": True, "start_time_ns": clock,
                                         "end_time_ns": clock + audit.PERIOD}
                                        for clock in range(BEGIN, END, audit.PERIOD)])
    clocks = list(range(BEGIN - 5_000_000, END, audit.PERIOD))
    receipts = []
    guard, information = [], []
    for robot_index, robot in enumerate(audit.ROBOTS, 1):
        compiled = {key: str(index) * 64 for index, key in enumerate(audit.COMPILED, 1)}
        compiled["loaded_library_path"] = "/fixture/libmr3_gazebo_diff_drive.so"
        producer = [{"schema": "mr3-world-odometry-publication-v1", "epoch": EPOCH,
                     "robot": robot, "kind": "configuration", "record_sequence": 1,
                     "provider": "WORLD", "period_ns": audit.PERIOD,
                     "phase": "world_update_begin_before_actuation",
                     "odometry_frame": "odom", "robot_base_frame": "base_footprint",
                     "actuation_update_rate_hz": 30., **compiled}]
        for sequence, clock in enumerate(clocks, 1):
            odom = message(clock)
            transform = {"header": odom["header"], "child_frame_id": odom["child_frame_id"],
                         "transform": {"translation": odom["pose"]["pose"]["position"],
                                       "rotation": odom["pose"]["pose"]["orientation"]}}
            producer.append({"schema": "mr3-world-odometry-publication-v1", "epoch": EPOCH,
                             "robot": robot, "kind": "publication", "record_sequence": sequence + 1,
                             "publication_sequence": sequence,
                             "publication_scope": "actual_publisher_calls_returned_not_delivery",
                             "source_clock_ns": clock, "sim_time_ns": clock, "odometry": odom,
                             "transform": transform, "odom_published": True, "odom_tf_published": True})
            for kind, payload in (("odom", odom), ("tf", transform)):
                gid = (str(robot_index) + ("1" if kind == "odom" else "2")) * 24
                endpoints = [{"namespace": "/" + robot, "node": "turtlebot3_diff_drive",
                              "topic_type": "nav_msgs/msg/Odometry" if kind == "odom" else "tf2_msgs/msg/TFMessage",
                              "endpoint_gid": gid}]
                if kind == "tf":
                    endpoints.append({"namespace": "/" + robot, "node": "robot_state_publisher",
                                      "topic_type": "tf2_msgs/msg/TFMessage", "endpoint_gid": "fe" * 24})
                receipt = {"schema": "mr3-driver-odometry-receipt-v1", "epoch": EPOCH,
                                 "robot": robot, "kind": kind, "record_sequence": len(receipts) + 1,
                                 "topic": f"/{robot}/{kind}", "message": payload, "publisher_gid": gid,
                                 "clock_ns": clock, "wall_monotonic_ns": clock,
                                 "driver_identity_match": True, "driver_gid_stable": True,
                                 "from_intra_process": False,
                                 "publisher_graph": {"topic": f"/{robot}/{kind}", "endpoints": endpoints}}
                if kind == "tf":
                    receipt.update(transform_index=0, tf_message={"transforms": [payload]})
                receipts.append(receipt)
        lines(directory / ("odometry_" + robot + ".jsonl"), producer)
        driver = [{"schema": "mr3-drive-actuation-v2", "epoch": EPOCH, "robot": robot,
                   "kind": "configuration", "update_rate_hz": 30.,
                   "mr3_odometry_period_ns": audit.PERIOD,
                   "actuation_algorithm": "measured_joint_rim_paired_common_fraction_v1", **compiled}]
        driver += [{"schema": "mr3-drive-actuation-v2", "epoch": EPOCH, "robot": robot,
                    "kind": "actuation", "dt_ns": audit.ACTUATION, "sim_time_ns": clock}
                   for clock in range(BEGIN + 7_000_000, END, audit.ACTUATION)]
        lines(directory / ("drive_" + robot + ".jsonl"), driver)
        (directory / ("drive_model_" + robot + ".sdf")).write_text(
            '<sdf><model><plugin name="turtlebot3_diff_drive"><update_rate>30</update_rate>'
            '<mr3_tagged_commands>true</mr3_tagged_commands></plugin></model></sdf>')
        # The first two sources are already received at the first query: source time
        # need not follow callback/query ordering, and future source may not be used.
        for sequence, clock in enumerate(clocks, 1):
            guard.append({"epoch": EPOCH, "kind": "own_odom", "payload": {
                "robot": robot, "input_sequence": sequence, "message": message(clock)}})
            information.append({"epoch": EPOCH, "kind": "odom_ingress", "payload": {
                "robot": robot, "input_sequence": sequence, "source_ns": clock,
                "raw": message(clock), "admission": "queued"}})
        for clock in range(BEGIN, END + audit.PERIOD, audit.PERIOD):
            source = max(value for value in clocks if value <= clock)
            sequence = clocks.index(source) + 1
            guard.append({"epoch": EPOCH, "kind": "decision", "payload": {
                "robot": robot, "clock_ns": clock, "started": True,
                "own_state": {"input_sequences": {"odom": sequence}, "odom_source_stamp": source / 1e9}}})
            information.append({"epoch": EPOCH, "kind": "state_selection", "clock_ns": clock,
                                "payload": {"robot": robot, "odom_input_sequence": sequence,
                                            "odom_source_ns": source}})
    receipts.sort(key=lambda row: (audit.stamp(row["message"]), row["robot"], row["kind"]))
    gids = [next(row["publisher_gid"] for row in receipts if row["robot"] == robot and row["kind"] == kind)
            for robot in audit.ROBOTS for kind in ("odom", "tf")]
    receipts.insert(6, {"schema": "mr3-driver-odometry-receipt-v1", "epoch": EPOCH,
                        "robot": "", "kind": "ready", "clock_ns": BEGIN - 5_000_000,
                        "wall_monotonic_ns": BEGIN - 5_000_000, "publisher_gids": gids})
    receipts.insert(0, {"schema": "mr3-driver-odometry-receipt-v1", "epoch": EPOCH,
                        "robot": "", "kind": "configuration", "clock_ns": 0, "wall_monotonic_ns": 0,
                        "use_sim_time": True, "robots": list(audit.ROBOTS),
                        "compiled_source_sha256": "f" * 64,
                        "compiled_odometry_json_sha256": "5" * 64})
    for sequence, row in enumerate(receipts, 1):
        row["record_sequence"] = sequence
    lines(directory / "driver_odometry_receipts.jsonl", receipts)
    lines(directory / "motion_safety.jsonl", guard)
    lines(directory / "information_states.jsonl", information)


class OdometryCadenceTests(unittest.TestCase):
    def case(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        fixture(directory)
        return directory

    def test_relative20ms_phase_shared_tf_publishers_and_future_ingress_are_valid(self):
        result = audit.audit(self.case(), FREEZE)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["episodes"][0]["robots"]["tb3"]["publications"], 10)
        self.assertEqual(result["episodes"][0]["robots"]["tb3"]["actuation_period_ns"], 34_000_000)

    def test20ms_publication_gap_is_not_hidden_by_nominal_configuration(self):
        directory = self.case()
        def remove(rows):
            rows.pop(5)
            for index, row in enumerate(rows, 1):
                row["record_sequence"] = index
                if row["kind"] == "publication":
                    row["publication_sequence"] = index - 1
        mutate(directory / "odometry_tb3.jsonl", remove)
        result = audit.audit(directory, FREEZE)
        self.assertFalse(result["passed"])
        self.assertIn("complete exact20ms", result["errors"][0]["error"])

    def test_tf_stamp_or_actual_received_payload_mismatch_fails(self):
        for fault in ("stamp", "received_payload"):
            with self.subTest(fault=fault):
                directory = self.case()
                if fault == "stamp":
                    mutate(directory / "odometry_tb3.jsonl", lambda rows: rows[3]["transform"]["header"]["stamp"].update(nanosec=999))
                else:
                    def change(rows):
                        next(row for row in rows if row["kind"] == "tf")["message"]["transform"]["translation"]["x"] = 99.
                    mutate(directory / "driver_odometry_receipts.jsonl", change)
                self.assertFalse(audit.audit(directory, FREEZE)["passed"])

    def test_graph_identity_cannot_replace_missing_or_spoofed_packet_gid(self):
        for gid in ("00" * 24, "fe" * 24):
            with self.subTest(gid=gid):
                directory = self.case()
                mutate(directory / "driver_odometry_receipts.jsonl", lambda rows: rows[2].update(publisher_gid=gid))
                self.assertFalse(audit.audit(directory, FREEZE)["passed"])

    def test_removed_period_option_and_untagged_mode_cannot_claim_fixed20ms(self):
        for declaration in ("<mr3_odometry_period_ns/>",
                            "<mr3_odometry_period_ns>20000000</mr3_odometry_period_ns>"):
            with self.subTest(declaration=declaration):
                directory = self.case()
                path = directory / "drive_model_tb3.sdf"
                path.write_text(path.read_text().replace("</plugin>", declaration + "</plugin>"))
                self.assertFalse(audit.audit(directory, FREEZE)["passed"])
        directory = self.case()
        path = directory / "drive_model_tb3.sdf"
        path.write_text(path.read_text().replace("<mr3_tagged_commands>true</mr3_tagged_commands>",
                                               "<mr3_tagged_commands>false</mr3_tagged_commands>"))
        self.assertFalse(audit.audit(directory, FREEZE)["passed"])

    def test_wheel20ms_change_cannot_be_counted_as_unchanged30hz_actuation(self):
        directory = self.case()
        mutate(directory / "drive_tb3.jsonl", lambda rows: rows[1].update(dt_ns=20_000_000))
        self.assertFalse(audit.audit(directory, FREEZE)["passed"])

    def test_guard_and_information_must_select_latest_actual_received_causal_source(self):
        for filename in ("motion_safety.jsonl", "information_states.jsonl"):
            with self.subTest(filename=filename):
                directory = self.case()
                def old(rows):
                    row = next(row for row in rows if row["kind"] in ("decision", "state_selection")
                               and row.get("clock_ns", row["payload"].get("clock_ns")) == BEGIN + audit.PERIOD)
                    value = row["payload"]
                    if row["kind"] == "decision":
                        value["own_state"]["input_sequences"]["odom"] = 1
                        value["own_state"]["odom_source_stamp"] = (BEGIN - 5_000_000) / 1e9
                    else:
                        value.update(odom_input_sequence=1, odom_source_ns=BEGIN - 5_000_000)
                mutate(directory / filename, old)
                self.assertFalse(audit.audit(directory, FREEZE)["passed"])

    def test_missing_real_receipt_artifact_stays_incomplete(self):
        directory = self.case()
        (directory / "driver_odometry_receipts.jsonl").unlink()
        result = audit.audit(directory, FREEZE)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["passed"])

    def test_permanent_stop_is_not_required_to_select_an_own_motion_source(self):
        directory = self.case()
        mutate(directory / "motion_safety.jsonl", lambda rows: rows.append({
            "epoch": EPOCH, "kind": "decision", "payload": {
                "robot": "tb3", "clock_ns": END, "started": True,
                "phase_kind": "stop", "own_state": None}}))
        result = audit.audit(directory, FREEZE)
        self.assertTrue(result["passed"], result["errors"])


if __name__ == "__main__":
    unittest.main()
