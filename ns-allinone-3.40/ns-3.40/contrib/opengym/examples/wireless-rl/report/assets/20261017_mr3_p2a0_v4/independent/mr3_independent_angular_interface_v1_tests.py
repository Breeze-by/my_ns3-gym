"""Mutation checks for the independent stdlib angular diagnostic consumer."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "independent_angular", Path(__file__).with_name("mr3_independent_angular_interface_v1.py"))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def fixture():
    metadata = {"epoch": "synthetic_only"}
    transitions = [{"kind": "reset", "info": {
        "epoch": metadata["epoch"], "release_time_ns": 10_000_000_000}}]
    physics = [{"epoch": metadata["epoch"], "end_time_ns": 10_400_000_000}]
    rows = []
    for index in range(8):
        for robot in AUDIT.ROBOTS:
            wz = ([.15, .15, .15, 0., -.15, -.15, -.15, 0.][index] if robot == "tb1"
                  else .2 if robot == "tb2" else -.2)
            rows.append({"kind": "own_odom", "epoch": metadata["epoch"], "payload": {
                "robot": robot, "message": {"header": {"stamp": {
                    "sec": 10, "nanosec": (index + 1) * 50_000_000}, "frame_id": "odom"},
                    "child_frame_id": "base_footprint",
                    "pose": {"diagnostic_mutation_sentinel": 0},
                    "twist": {"twist": {"angular": {"x": 0., "y": 0., "z": wz}}}}}})
    return metadata, transitions, physics, rows


class AngularMutationTests(unittest.TestCase):
    def run_fixture(self, change=None):
        arguments = fixture()
        if change:
            change(arguments[3])
        return AUDIT.audit_records(*arguments)

    def test_valid_bidirectional_stop_restart_coverage_and_original_max_pair(self):
        result = self.run_fixture()
        self.assertTrue(result["passed"])
        self.assertEqual(result["sequential_opposite_sign_span_robots"], ["tb1"])
        robot = result["robots"]["tb1"]
        self.assertEqual([span["samples"] for span in robot["sign_spans"]], [3, 3])
        self.assertAlmostEqual(robot["max_sampled_angular_accel_rad_s2"], 3.)
        self.assertIn("raw_own_odom", robot["max_acceleration_original_adjacent_samples"]["prior"])
        self.assertEqual(robot["max_source_gap_ns"], 50_000_000)

    def test_exact_raw_message_duplicate_deduplicates(self):
        result = self.run_fixture(lambda rows: rows.insert(1, copy.deepcopy(rows[0])))
        self.assertTrue(result["passed"])
        self.assertEqual(result["robots"]["tb1"]["exact_duplicate_messages_deduplicated"], 1)
        self.assertEqual(result["robots"]["tb1"]["postrelease_samples"], 8)

    def test_same_source_changed_nonangular_payload_rejected(self):
        def mutate(rows):
            duplicate = copy.deepcopy(rows[0])
            duplicate["payload"]["message"]["pose"]["diagnostic_mutation_sentinel"] = 1
            rows.insert(1, duplicate)
        result = self.run_fixture(mutate)
        self.assertFalse(result["passed"])
        self.assertIn("conflicting_duplicate_source",
                      [error["kind"] for error in result["robots"]["tb1"]["errors"]])

    def test_rewind_rejected_even_if_message_itself_is_identical(self):
        result = self.run_fixture(lambda rows: rows.insert(4, copy.deepcopy(rows[0])))
        self.assertIn("source_rewind",
                      [error["kind"] for error in result["robots"]["tb1"]["errors"]])
        self.assertFalse(result["passed"])

    def test_frame_change_rejected(self):
        def mutate(rows):
            rows[3]["payload"]["message"]["header"]["frame_id"] = "different_odom"
        result = self.run_fixture(mutate)
        self.assertIn("odom_frame_changed",
                      [error["kind"] for error in result["robots"]["tb1"]["errors"]])
        self.assertFalse(result["passed"])

    def test_complete_vector_norm_not_just_wz_is_checked(self):
        def mutate(rows):
            rows[0]["payload"]["message"]["twist"]["twist"]["angular"]["x"] = 1.21
        result = self.run_fixture(mutate)
        self.assertGreater(result["robots"]["tb1"]["max_angular_norm_rad_s"], 1.2)
        self.assertFalse(result["sampled_bounds_passed"])

    def test_complete_vector_acceleration_not_just_wz_is_checked(self):
        def mutate(rows):
            vector = rows[3]["payload"]["message"]["twist"]["twist"]["angular"]
            vector.update(x=.3, y=.3)
        result = self.run_fixture(mutate)
        self.assertLess(result["robots"]["tb1"]["max_angular_norm_rad_s"], 1.2)
        self.assertGreater(result["robots"]["tb1"]["max_sampled_angular_accel_rad_s2"], 7.)
        self.assertFalse(result["sampled_bounds_passed"])

    def test_gap_over_100ms_is_missing_not_pass(self):
        def mutate(rows):
            rows[:] = [row for row in rows if not (
                row["payload"]["robot"] == "tb2" and
                row["payload"]["message"]["header"]["stamp"]["nanosec"] in
                (100_000_000, 150_000_000, 200_000_000))]
        result = self.run_fixture(mutate)
        self.assertIn("source_gap_over_100ms", result["robots"]["tb2"]["missing"])
        self.assertFalse(result["passed"])

    def test_each_robot_needs_real_postrelease_source_samples(self):
        result = self.run_fixture(lambda rows: rows.__setitem__(
            slice(None), [row for row in rows if row["payload"]["robot"] != "tb3"]))
        self.assertIn("real_postrelease_own_odom", result["robots"]["tb3"]["missing"])
        self.assertFalse(result["passed"])

    def test_both_signs_across_robots_do_not_replace_one_robot_two_signs(self):
        def mutate(rows):
            for row in rows:
                if row["payload"]["robot"] == "tb1":
                    row["payload"]["message"]["twist"]["twist"]["angular"]["z"] = .15
        result = self.run_fixture(mutate)
        self.assertTrue(result["sampled_bounds_passed"])
        self.assertFalse(result["stimulus_coverage_passed"])
        self.assertIn("one_robot_with_sequential_opposite_sign_spans", result["missing"])

    def test_two_samples_do_not_make_a_sign_span(self):
        def mutate(rows):
            for row in rows:
                if row["payload"]["robot"] == "tb2":
                    source = row["payload"]["message"]["header"]["stamp"]["nanosec"]
                    row["payload"]["message"]["twist"]["twist"]["angular"]["z"] = (
                        .2 if source <= 100_000_000 else 0.)
        result = self.run_fixture(mutate)
        self.assertEqual(result["robots"]["tb2"]["sign_spans"], [])
        self.assertFalse(result["passed"])

    def test_nan_and_invalid_source_timestamp_fail_closed(self):
        for field in ("nan", "stamp"):
            with self.subTest(field=field):
                def mutate(rows):
                    message = rows[0]["payload"]["message"]
                    if field == "nan":
                        message["twist"]["twist"]["angular"]["x"] = float("nan")
                    else:
                        message["header"]["stamp"]["nanosec"] = 50_000_000.0
                result = self.run_fixture(mutate)
                self.assertFalse(result["passed"])
                self.assertEqual(result["robots"]["tb1"]["errors"][0]["kind"],
                                 "malformed_own_odom")

    def test_epoch_mismatch_rejected(self):
        arguments = fixture()
        arguments[3][0]["epoch"] = "other_epoch"
        with self.assertRaisesRegex(ValueError, "epoch mismatch"):
            AUDIT.audit_records(*arguments)


if __name__ == "__main__":
    unittest.main()
