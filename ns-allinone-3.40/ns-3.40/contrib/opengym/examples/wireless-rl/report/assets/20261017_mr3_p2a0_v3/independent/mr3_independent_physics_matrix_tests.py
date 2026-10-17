"""Synthetic aggregate fixtures keep per-episode missing while requiring matrix coverage."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from mr3_independent_physics_matrix import audit, CONSUMER_SHA256, ROBOTS, SCHEDULE

FREEZE = "a" * 40


def fixture(directory):
    declaration = {"freeze": FREEZE, "workers": 2, "schedule": SCHEDULE,
                   "steps_per_episode": 16, "preparation_motion_probe": True,
                   "terminal_probe": False, "deadline_probe": False, "fault_probe": False}
    (directory / "benchmark_metadata.json").write_text(json.dumps(declaration))
    (directory / "benchmark_summary.json").write_text(json.dumps({**declaration, "passed": True}))
    episodes = []
    for worker in (0, 1):
        for index, (scene, seed) in enumerate(SCHEDULE):
            path = directory / f"worker{worker}" / f"episode{index + 1:03d}_{scene}_{seed}"
            path.mkdir(parents=True)
            epoch = f"fixture_{worker}_{index}"
            (path / "metadata.json").write_text(json.dumps({"freeze": FREEZE, "epoch": epoch}))
            robots = {}
            for robot_index, name in enumerate(ROBOTS):
                credited = worker == 0 and index == robot_index
                event = {"event_category": "A_final_linear_zero", "eligible": True,
                         "status": "sampled_response_within_declared_bounds",
                         "initial_observed_planar_speed": .2,
                         "prior_nonzero_command_span_ns": 200000000,
                         "observed_latency_sec": .5, "observed_odom_polyline_m": .06,
                         "maximum_observation_gap_ns": 34000000, "event_clock_ns": 2000000000}
                robots[name] = {
                    "errors": [], "task_odom_samples": 100, "raw_unique_odom_samples": 150,
                    "maximum_planar_speed_task": .2, "maximum_angular_norm_task": .9,
                    "maximum_abs_angular_z_task": .9, "maximum_raw_odom_chord_speed_task": .2,
                    "maximum_planar_speed_all": .2, "maximum_angular_norm_all": .9,
                    "maximum_abs_angular_z_all": .9, "maximum_task_source_gap_ns": 34000000,
                    "bound_violation_counts": {"planar_speed_over_.30": 0,
                        "angular_norm_over_1.2": 0, "chord_speed_over_.30": 0},
                    "stop_responses": [event] if credited else [], "cancel_stop_responses": [],
                    "eligible_stop_events": int(credited), "credited_sampled_stop_events": int(credited),
                    "eligible_cancel_stop_events": 0, "credited_cancel_stop_events": 0,
                    "physical_evidence_complete": credited,
                }
            episodes.append({"directory": str(path), "epoch": epoch,
                "passed": False, "physical_evidence_complete": False, "robots": robots,
                "closure": {"passed": True, "errors": [], "checks": {"all_native": True},
                            "still_present_saved_identities": [], "started_processes": 39,
                            "exited_processes": 39}})
    report = {"schema": "mr3-independent-raw-physics-closure-review-v1", "passed": False,
              "script_sha256": CONSUMER_SHA256, "episodes": episodes}
    path = directory / "physics.json"
    path.write_text(json.dumps(report))
    return path, report


class MatrixTests(unittest.TestCase):
    def test_cross_matrix_coverage_preserves_every_strict_episode_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, report = fixture(directory)
            result = audit(directory, path, FREEZE)
            self.assertTrue(result["passed"])
            self.assertFalse(result["source_report_passed"])
            self.assertTrue(all(not row["original_per_episode_physical_evidence_complete"]
                                for row in result["episodes"]))
            self.assertTrue(all(row["A"] == 1 and row["B"] == 0
                                for row in result["robot_stop_coverage"].values()))
            self.assertEqual(result["episodes"][0]["missing_meaningful_stop_robots"], ["tb2", "tb3"])

    def test_missing_robot_stop_bound_violation_and_failed_closure_are_rejected(self):
        for mutation in ("missing_robot", "stop_bound", "closure", "raw_limit"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                path, report = fixture(directory)
                if mutation == "missing_robot":
                    robot = report["episodes"][2]["robots"]["tb3"]
                    robot["stop_responses"] = []
                    robot["eligible_stop_events"] = robot["credited_sampled_stop_events"] = 0
                    robot["physical_evidence_complete"] = False
                elif mutation == "stop_bound":
                    robot = report["episodes"][0]["robots"]["tb1"]
                    robot["stop_responses"][0].update(status="observed_bound_violation",
                                                     observed_nonrest_beyond_horizon=True)
                    robot["credited_sampled_stop_events"] = 0
                elif mutation == "closure":
                    report["episodes"][4]["closure"].update(passed=False, errors=["forced"])
                else:
                    report["episodes"][7]["robots"]["tb2"]["maximum_planar_speed_task"] = .31
                path.write_text(json.dumps(report))
                result = audit(directory, path, FREEZE)
                self.assertFalse(result["passed"])
                expected = {"missing_robot": "no meaningful", "stop_bound": "violated stop bound",
                            "closure": "strict native closure", "raw_limit": "missing or exceeded"}
                self.assertTrue(any(expected[mutation] in error for error in result["errors"]))

    def test_terminal_pooling_or_missing_eighth_episode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, report = fixture(directory)
            report["episodes"].pop()
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                audit(directory, path, FREEZE)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, report = fixture(directory)
            metadata = json.loads((directory / "benchmark_metadata.json").read_text())
            metadata["terminal_probe"] = True
            (directory / "benchmark_metadata.json").write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                audit(directory, path, FREEZE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
