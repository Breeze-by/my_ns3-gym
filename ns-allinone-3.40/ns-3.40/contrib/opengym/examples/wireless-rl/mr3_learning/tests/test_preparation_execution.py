"""Mutations of actual-output archive/phase contracts, with synthetic bytes."""

import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning.audit_preparation import audit_execution_inputs, audit_probe_execution


def write_json(path, value):
    path.write_text(json.dumps(value) + "\n")


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class ExecutionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        write_json(self.root / "metadata.json", {"epoch": "fixture"})
        self.release = 10**10
        self.boundary = self.release + 20_000_000
        write_rows(self.root / "transitions.jsonl", [{
            "snapshot": {"epoch": "fixture", "source_stamp": 10.},
            "info": {"release_time_ns": self.release}}])
        self.topology = {
            "schema": "mr3-motion-output-topology-v1", "epoch": "fixture", "stamp": 10.,
            "endpoints": {f"/tb{i}/cmd_vel": [{
                "namespace": "/", "node": "motion_safety",
                "topic_type": "geometry_msgs/msg/Twist", "endpoint_gid": f"{i:032x}"}]
                for i in (1, 2, 3)}}
        write_json(self.root / "motion_topology.json", self.topology)
        payload = {"header": {"stamp": {"sec": 10, "nanosec": 1}, "frame_id": "map"},
                   "info": {"width": 2, "height": 1}, "data": [100, -1]}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(raw).hexdigest()
        artifact = f"execution_inputs/maps/{digest}.json.gz"
        (self.root / artifact).parent.mkdir(parents=True)
        (self.root / artifact).write_bytes(gzip.compress(raw, mtime=0))
        self.costmaps = [{"schema": "mr3-native-costmap-receipt-v1", "epoch": "fixture",
                          "robot": f"tb{i}", "layer": layer,
                          "topic": f"/tb{i}/{layer}_costmap/costmap",
                          "source_header": copy.deepcopy(payload["header"]),
                          "received_clock_ns": self.release,
                          "payload_sha256": digest, "artifact": artifact}
                         for i in (1, 2, 3) for layer in ("global", "local")]
        write_rows(self.root / "costmaps.jsonl", self.costmaps)
        ack = {"schema": "mr3-motion-safety-status-v1", "epoch": "fixture",
               "completion_scope": "publication_and_local_topic_receipt",
               "clock_ns": self.boundary, "ready": True,
               "decision_sequences": {f"tb{i}": 12 for i in (1, 2, 3)}}
        initial = {**copy.deepcopy(ack), "clock_ns": self.release,
                   "decision_sequences": {f"tb{i}": 11 for i in (1, 2, 3)}}
        self.phases = [{"kind": kind, "epoch": "fixture", "ack": copy.deepcopy(value),
                        "worker_clock_ns": value["clock_ns"],
                        "worker_physical_ns": value["clock_ns"]}
                       for value in (initial, ack) for kind in ("ack_received", "ack_consumed")]
        write_rows(self.root / "transitions.jsonl", [{
            "snapshot": {"epoch": "fixture", "source_stamp": 10.},
            "info": {"release_time_ns": self.release, "initial_motion_status": initial}}])
        write_rows(self.root / "motion_phase_worker.jsonl", self.phases)
        write_rows(self.root / "physics.jsonl", [
            {"end_time_ns": self.release}, {"end_time_ns": self.boundary}])

    def test_complete_output_bytes_and_exact_phase_pass_without_faking_source_clock(self):
        result = audit_execution_inputs(self.root)
        self.assertTrue(result["passed"])
        self.assertEqual(result["costmap_receipts"], 6)
        self.assertEqual(result["unique_costmaps"], 1)
        self.assertEqual(result["maximum_source_clock_lead_ns"], 1)

    def test_visible_behavior_bypass_is_rejected(self):
        self.topology["endpoints"]["/tb2/cmd_vel"][0]["node"] = "behavior_server"
        write_json(self.root / "motion_topology.json", self.topology)
        with self.assertRaisesRegex(ValueError, "final velocity publisher"):
            audit_execution_inputs(self.root)

    def test_missing_robot_costmap_stream_is_rejected(self):
        write_rows(self.root / "costmaps.jsonl", self.costmaps[:-1])
        with self.assertRaisesRegex(ValueError, "master outputs missing"):
            audit_execution_inputs(self.root)

    def test_replaced_source_header_does_not_match_native_bytes(self):
        self.costmaps[0]["source_header"]["stamp"]["sec"] += 1
        write_rows(self.root / "costmaps.jsonl", self.costmaps)
        with self.assertRaisesRegex(ValueError, "source header differs"):
            audit_execution_inputs(self.root)

    def test_unreceived_or_missing_phase_cannot_authorize_physics(self):
        write_rows(self.root / "motion_phase_worker.jsonl", self.phases[1:])
        with self.assertRaisesRegex(ValueError, "not actually received"):
            audit_execution_inputs(self.root)
        write_rows(self.root / "motion_phase_worker.jsonl", self.phases[:1])
        with self.assertRaisesRegex(ValueError, "without exact motion"):
            audit_execution_inputs(self.root)


class ProbeExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.snapshot = {"joint_action_mask": [index == 12 for index in range(1000)],
                         "robots": [{"activity": {"estimated_path_m": .1}}
                                    for _ in range(3)]}
        events = []
        for name in ("tb1", "tb2", "tb3"):
            events += [{"kind": "native_send", "payload": {"robot": name, "goal_id": name}},
                       {"kind": "delivery", "payload": {
                           "stream": "receipt", "source": name,
                           "payload": {"type": "accept", "value": True, "goal_id": name}}}]
        write_rows(self.root / "adapter.jsonl", events)

    def run_probe(self):
        write_rows(self.root / "transitions.jsonl", [{"snapshot": self.snapshot}])
        return audit_probe_execution(self.root)

    def test_real_sends_accepts_and_observed_movement_are_all_required(self):
        self.assertTrue(self.run_probe()["passed"])
        self.snapshot["robots"][1]["activity"]["estimated_path_m"] = .01
        with self.assertRaisesRegex(ValueError, "tb2.*no proven"):
            self.run_probe()

    def test_per_robot_candidate_does_not_replace_joint_action_legality(self):
        self.snapshot["per_robot_action_mask"] = [[True] * 10 for _ in range(3)]
        self.snapshot["joint_action_mask"] = [index == 888 for index in range(1000)]
        with self.assertRaisesRegex(ValueError, "no proven legal"):
            self.run_probe()


if __name__ == "__main__":
    unittest.main()
