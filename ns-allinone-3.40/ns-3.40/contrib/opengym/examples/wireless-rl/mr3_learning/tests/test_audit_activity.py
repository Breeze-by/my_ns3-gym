"""Independent activity audit fixtures and mutation checks; no ROS jobs."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning.audit_activity import audit_episode


ROBOTS = ("tb1", "tb2", "tb3")
EPOCH = "activity-epoch"


def seal(snapshot):
    payload = {key: value for key, value in snapshot.items() if key != "digest"}
    snapshot["digest"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return snapshot


def fixture():
    records, transitions = [], []

    def record(kind, payload, now):
        records.append({"kind": kind, "epoch": EPOCH, "stamp": now, "payload": payload})

    for sequence, stamp, x in ((1, 1., 0.), (2, 1.1, .3)):
        robots, receipts, actor = [], [], []
        for name in ROBOTS:
            position = x if name == "tb1" else 0.
            robots.append({
                "name": name, "epoch": EPOCH, "valid": True, "odom_source_stamp": stamp,
                "odometry": {"header": {
                    "stamp": {"sec": 1, "nanosec": 0 if sequence == 1 else 100000000},
                    "frame_id": "odom"},
                             "child_frame_id": "base_footprint",
                             "pose": {"pose": {"position": {"x": position, "y": 0.}}}},
            })
            activity = {
                "schema": "mr3-received-activity-v1", "epoch": EPOCH, "started_at": 1.,
                "state_sequence": sequence, "estimated_path_m": position,
                "path_observation_complete": True, "sample_count": sequence,
                "last_odom_source_stamp": stamp,
            }
            receipts.append({"name": name, "status": "anchor" if sequence == 1 else "accumulated",
                             "sample": {"source_stamp": stamp, "x": position, "y": 0.,
                                        "frame": "odom", "child_frame": "base_footprint"},
                             **activity})
            actor.append({"name": name, "epoch": EPOCH, "activity": activity,
                          "navigation": {"accepted_goal_count": int(
                              sequence == 2 and name == "tb1"),
                                         "receipt_sequence": 1 if sequence == 2 and name == "tb1"
                                         else None}})
        record("state_update", {"sequence": sequence, "robots": robots}, stamp)
        record("activity_update", {"epoch": EPOCH, "state_sequence": sequence,
                                   "robots": receipts}, stamp)
        if sequence == 1:
            record("task_start", {"start_sim_time_sec": 1.}, stamp)
        else:
            record("protocol", {"type": "send_goal", "robot": "tb1", "epoch": EPOCH,
                                "goal_id": "goal1"}, stamp)
            for receipt_sequence in (1, 2):
                record("delivery", {"epoch": EPOCH, "stream": "receipt", "source": "tb1",
                                    "sequence": receipt_sequence,
                                    "payload": {"type": "accept", "goal_id": "goal1",
                                                "value": True}}, stamp)
        record("activity_snapshot_bound", {"observation_sequence": sequence,
                                           "state_sequence": sequence}, stamp)
        snapshot = seal({"schema": "mr3-observation-v3", "epoch": EPOCH,
                         "source_stamp": stamp, "sequence": sequence, "robots": actor})
        transitions.append({"kind": "reset" if sequence == 1 else "step", "snapshot": snapshot,
                            "info": {"watermarks": {"state_sequence": sequence}}})
    return records, transitions


class ActivityAuditTests(unittest.TestCase):
    def run_fixture(self, mutate=None):
        records, transitions = fixture()
        if mutate:
            mutate(records, transitions)
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "metadata.json").write_text(json.dumps({"epoch": EPOCH}))
            (directory / "adapter.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in records))
            (directory / "transitions.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in transitions))
            return audit_episode(directory)

    def test_exact_raw_odometry_and_duplicate_acceptance_replay(self):
        result = self.run_fixture()
        self.assertTrue(result["passed"])
        self.assertEqual(result["activity_updates"], 2)
        self.assertEqual(result["final_received_acceptance_counts"]["tb1"], 1)

    def test_changed_snapshot_path_or_count_is_rejected_even_with_new_digest(self):
        for changed in ("path", "count", "epoch", "boundary"):
            def mutate(records, transitions):
                snapshot = transitions[-1]["snapshot"]
                robot = snapshot["robots"][0]
                if changed == "path":
                    robot["activity"]["estimated_path_m"] += 1.
                elif changed == "count":
                    robot["navigation"]["accepted_goal_count"] += 1
                elif changed == "epoch":
                    robot["activity"]["epoch"] = "wrong-epoch"
                else:
                    robot["activity"] = copy.deepcopy(transitions[0]["snapshot"]["robots"][0][
                        "activity"])
                seal(snapshot)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.run_fixture(mutate)

    def test_map_pose_cannot_substitute_for_the_raw_odom_source(self):
        def mutate(records, transitions):
            row = next(r for r in records if r["kind"] == "state_update"
                       and r["payload"]["sequence"] == 2)
            row["payload"]["robots"][0]["odometry"]["pose"]["pose"]["position"]["x"] = 50.
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.run_fixture(mutate)

    def test_unowned_or_rejected_acceptance_cannot_pay_a_goal_count(self):
        def mutate(records, transitions):
            for row in records:
                if row["kind"] == "delivery":
                    row["payload"]["payload"]["value"] = False
        with self.assertRaisesRegex(ValueError, "accepted goals"):
            self.run_fixture(mutate)

    def test_changing_count_and_receipt_metadata_cannot_relabel_an_old_snapshot(self):
        def mutate(records, transitions):
            snapshot = transitions[-1]["snapshot"]
            snapshot["robots"][0]["navigation"].update(
                accepted_goal_count=0, receipt_sequence=None)
            seal(snapshot)
        with self.assertRaisesRegex(ValueError, "accepted goals"):
            self.run_fixture(mutate)

    def test_wrong_received_epoch_cannot_enter_the_activity_ledger(self):
        def mutate(records, transitions):
            receipt = next(r for r in records if r["kind"] == "activity_update")
            receipt["payload"]["epoch"] = "old"
        with self.assertRaisesRegex(ValueError, "epoch"):
            self.run_fixture(mutate)

    def test_same_clock_activity_cannot_precede_its_raw_received_input(self):
        def mutate(records, transitions):
            raw_index = next(i for i, row in enumerate(records)
                             if row["kind"] == "state_update"
                             and row["payload"]["sequence"] == 2)
            activity_index = next(i for i, row in enumerate(records)
                                  if row["kind"] == "activity_update"
                                  and row["payload"]["state_sequence"] == 2)
            records[raw_index], records[activity_index] = (
                records[activity_index], records[raw_index])
        with self.assertRaisesRegex(ValueError, "before its raw received input"):
            self.run_fixture(mutate)

    def test_incomplete_missing_odom_is_explicit_and_does_not_invent_motion(self):
        def mutate(records, transitions):
            raw = next(r for r in records if r["kind"] == "state_update"
                       and r["payload"]["sequence"] == 2)
            del raw["payload"]["robots"][0]["odometry"]
            receipt = next(r for r in records if r["kind"] == "activity_update"
                           and r["payload"]["state_sequence"] == 2)["payload"]["robots"][0]
            receipt.update(status="invalid_odometry", sample=None, estimated_path_m=0.,
                           sample_count=1, last_odom_source_stamp=1.,
                           path_observation_complete=False)
            snapshot = transitions[-1]["snapshot"]
            snapshot["robots"][0]["activity"] = {
                k: v for k, v in receipt.items() if k not in {"name", "status", "sample"}}
            seal(snapshot)
        self.assertTrue(self.run_fixture(mutate)["passed"])


if __name__ == "__main__":
    unittest.main()
