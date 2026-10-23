"""Independent activity audit fixtures and mutation checks; no ROS jobs."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning.audit_activity import audit_episode, audit_probe_activity


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


def probe_fixture():
    records, transitions = fixture()
    raw = next(row for row in records if row["kind"] == "state_update"
               and row["payload"]["sequence"] == 2)
    receipt = next(row for row in records if row["kind"] == "activity_update"
                   and row["payload"]["state_sequence"] == 2)
    for robot in raw["payload"]["robots"]:
        robot["odometry"]["pose"]["pose"]["position"]["x"] = .3
    for robot in receipt["payload"]["robots"]:
        robot["estimated_path_m"] = robot["sample"]["x"] = .3
    for robot in transitions[-1]["snapshot"]["robots"]:
        robot["activity"]["estimated_path_m"] = .3
        robot["navigation"].update(accepted_goal_count=1, receipt_sequence=1)

    def row(kind, payload):
        return {"kind": kind, "epoch": EPOCH, "stamp": 1.1, "payload": payload}

    first_accept = next(index for index, item in enumerate(records)
                        if item["kind"] == "delivery")
    records.insert(first_accept, row("native_send", {"robot": "tb1", "goal_id": "goal1"}))
    boundary = next(index for index, item in enumerate(records)
                    if item["kind"] == "activity_snapshot_bound"
                    and item["payload"]["observation_sequence"] == 2)
    extra = []
    for name in ("tb2", "tb3"):
        goal = "goal-" + name
        extra.extend([
            row("protocol", {"type": "send_goal", "robot": name, "epoch": EPOCH,
                             "goal_id": goal}),
            row("native_send", {"robot": name, "goal_id": goal}),
            row("delivery", {"epoch": EPOCH, "stream": "receipt", "source": name,
                             "sequence": 1, "payload": {
                                 "type": "accept", "goal_id": goal, "value": True}}),
        ])
    records[boundary:boundary] = extra
    seal(transitions[-1]["snapshot"])
    return records, transitions


class ActivityAuditTests(unittest.TestCase):
    def run_fixture(self, mutate=None, *, probe=False, all_robots=False):
        records, transitions = probe_fixture() if all_robots else fixture()
        if mutate:
            mutate(records, transitions)
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "metadata.json").write_text(json.dumps({"epoch": EPOCH}))
            (directory / "adapter.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in records))
            (directory / "transitions.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in transitions))
            return audit_probe_activity(directory) if probe else audit_episode(directory)

    def test_exact_raw_odometry_and_duplicate_acceptance_replay(self):
        result = self.run_fixture()
        self.assertTrue(result["passed"])
        self.assertEqual(result["activity_updates"], 2)
        self.assertEqual(result["final_received_acceptance_counts"]["tb1"], 1)

    def test_complete_native_three_robot_probe_has_separate_availability_credit(self):
        result = self.run_fixture(probe=True, all_robots=True)
        self.assertTrue(result["passed"])
        self.assertTrue(result["integrity"]["integrity_passed"])
        self.assertTrue(result["integrity"]["availability_passed"])
        self.assertEqual(set(result["native_accepted_goal_ids"]), set(ROBOTS))

    def test_all_null_activity_is_integrity_only_even_with_real_acceptances(self):
        def mutate(records, transitions):
            for row in records:
                if row["kind"] == "state_update":
                    for robot in row["payload"]["robots"]:
                        del robot["odometry"]
                elif row["kind"] == "activity_update":
                    for robot in row["payload"]["robots"]:
                        robot.update(status="invalid_odometry", sample=None,
                                     estimated_path_m=None, sample_count=0,
                                     last_odom_source_stamp=None,
                                     path_observation_complete=False)
            for transition in transitions:
                for robot in transition["snapshot"]["robots"]:
                    robot["activity"].update(estimated_path_m=None, sample_count=0,
                                             last_odom_source_stamp=None,
                                             path_observation_complete=False)
                seal(transition["snapshot"])
        integrity = self.run_fixture(mutate, all_robots=True)
        self.assertTrue(integrity["integrity_passed"])
        self.assertFalse(integrity["availability_passed"])
        with self.assertRaisesRegex(ValueError, "unavailable/incomplete"):
            self.run_fixture(mutate, probe=True, all_robots=True)

    def test_accepted_probe_without_native_send_cannot_claim_execution(self):
        def mutate(records, transitions):
            records[:] = [row for row in records if row["kind"] != "native_send"]
        with self.assertRaisesRegex(ValueError, "preceding native send"):
            self.run_fixture(mutate, probe=True, all_robots=True)

    def test_accepted_probe_at_exact_movement_threshold_is_rejected(self):
        def mutate(records, transitions):
            raw = next(row for row in records if row["kind"] == "state_update"
                       and row["payload"]["sequence"] == 2)
            raw["payload"]["robots"][0]["odometry"]["pose"]["pose"]["position"]["x"] = .05
            receipt = next(row for row in records if row["kind"] == "activity_update"
                           and row["payload"]["state_sequence"] == 2)
            receipt["payload"]["robots"][0]["estimated_path_m"] = .05
            receipt["payload"]["robots"][0]["sample"]["x"] = .05
            transitions[-1]["snapshot"]["robots"][0]["activity"]["estimated_path_m"] = .05
            seal(transitions[-1]["snapshot"])
        with self.assertRaisesRegex(ValueError, "movement >0.05m"):
            self.run_fixture(mutate, probe=True, all_robots=True)

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
