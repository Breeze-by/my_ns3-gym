"""Synthetic mutations for the reset-only angular aggregate; no native credit."""

import copy
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "angular_reset_matrix", Path(__file__).with_name("mr3_independent_angular_reset_matrix_v1.py"))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
CONSUMER = Path(__file__).with_name("mr3_independent_angular_interface_v1.py")
FREEZE = "a" * 40


def write(path, value, lines=False):
    path.write_text(("\n".join(json.dumps(row, allow_nan=False) for row in value) + "\n")
                    if lines else json.dumps(value, allow_nan=False))


def fixture(root):
    metadata = {"freeze": FREEZE, "workers": 2, "robots_per_worker": 3,
                "schedule": copy.deepcopy(AUDIT.SCHEDULE), "steps_per_episode": 20,
                "preparation_probe_version": AUDIT.PROBE_VERSION,
                "preparation_motion_probe": True, "terminal_probe": False,
                "deadline_probe": False, "fault_probe": False}
    summary = {**copy.deepcopy(metadata), "passed": True, "workers_results": []}
    for worker in (0, 1):
        cells = []
        for index, (scene, seed) in enumerate(AUDIT.SCHEDULE):
            directory = root / f"worker{worker}" / f"episode{index + 1:03d}_{scene}_{seed}"
            directory.mkdir(parents=True)
            epoch = f"synthetic_w{worker}_e{index}"
            cells.append({"scene": scene, "seed": seed, "epoch": epoch, "transitions": 20,
                          "terminated": False, "truncated": True})
            write(directory / "metadata.json", {"freeze": FREEZE, "epoch": epoch,
                                                "scene": scene, "seed": seed})
            transitions = [{"kind": "reset", "info": {
                "epoch": epoch, "release_time_ns": 10_000_000_000}}]
            transitions += [{"kind": "step", "terminated": False, "truncated": i == 19}
                            for i in range(20)]
            write(directory / "transitions.jsonl", transitions, True)
            write(directory / "physics.jsonl", [{"epoch": epoch,
                                                "end_time_ns": 30_000_000_000}], True)
            rows = []
            for sample in range(1, 401):
                sec, nano = divmod(10_000_000_000 + sample * 50_000_000, 10**9)
                for name in ("tb1", "tb2", "tb3"):
                    rows.append({"kind": "own_odom", "epoch": epoch, "payload": {
                        "robot": name, "message": {
                            "header": {"frame_id": "odom", "stamp": {
                                "sec": sec, "nanosec": nano}},
                            "child_frame_id": "base_footprint", "twist": {"twist": {
                                "angular": {"x": 0., "y": 0., "z": 0.}}}}}})
            write(directory / "motion_safety.jsonl", rows, True)
        summary["workers_results"].append({"worker_id": worker, "episodes": cells})
    write(root / "benchmark_metadata.json", metadata)
    write(root / "benchmark_summary.json", summary)
    return root / "worker0/episode001_open_101"


def mutate_json(path, change, lines=False):
    value = ([json.loads(line) for line in path.read_text().splitlines()]
             if lines else json.loads(path.read_text()))
    change(value)
    write(path, value, lines)


class AngularResetMatrixMutationTests(unittest.TestCase):
    def test_stationary_reset_bounds_pass_without_relabelling_missing_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            result = AUDIT.audit(root, FREEZE, CONSUMER)
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(len(result["episodes"]), 8)
            for row in result["episodes"]:
                self.assertTrue(row["sampled_bounds_passed"])
                self.assertFalse(row["stimulus_coverage_passed"])
                self.assertFalse(row["original_passed"])
                self.assertFalse(row["original_angular_audit"]["passed"])
                self.assertEqual(len(row["input_bindings"]), 4)
                self.assertEqual(row["final_physics_time_ns"], 30_000_000_000)

    def test_single_episode_complete_vector_acceleration_violation_fails_matrix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            episode = fixture(root)
            mutate_json(episode / "motion_safety.jsonl", lambda rows: rows[3]["payload"]
                        ["message"]["twist"]["twist"]["angular"].update(x=.4), True)
            result = AUDIT.audit(root, FREEZE, CONSUMER)
            self.assertFalse(result["passed"])
            row = result["episodes"][0]
            self.assertFalse(row["sampled_bounds_passed"])
            self.assertGreater(row["original_angular_audit"]["robots"]["tb1"]
                               ["max_sampled_angular_accel_rad_s2"], 7.)
            self.assertEqual(len(row["input_bindings"]), 4)
            self.assertEqual(row["final_physics_time_ns"], 30_000_000_000)

    def test_exact_source_hash_is_required_before_loading_consumer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            changed = root / "changed_consumer.py"
            changed.write_text(CONSUMER.read_text()
                               + '\nraise RuntimeError("must not execute")\n')
            result = AUDIT.audit(root, FREEZE, changed)
            self.assertFalse(result["passed"])
            self.assertIn("SHA mismatch", result["errors"][0])
            self.assertEqual(len(result["episodes"][0]["input_bindings"]), 4)

    def test_workload_type_budget_seed_version_summary_and_freeze_mutations_fail(self):
        for field, value in (("workers", 2.), ("steps_per_episode", 16),
                             ("steps_per_episode", 20.), ("preparation_probe_version", "v1"),
                             ("schedule", [["open", 101], ["open", 101],
                                           ["rooms", 202], ["corridors", 101]]),
                             ("freeze", "b" * 40), ("terminal_probe", True)):
            case = self.subTest(field=field, value=value)
            with case, tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture(root)
                mutate_json(root / "benchmark_metadata.json", lambda value_map:
                            value_map.update({field: value}))
                self.assertFalse(AUDIT.audit(root, FREEZE, CONSUMER)["passed"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            mutate_json(root / "benchmark_summary.json", lambda value: value.update(passed=False))
            self.assertFalse(AUDIT.audit(root, FREEZE, CONSUMER)["passed"])

    def test_missing_extra_directory_wrong_epoch_and_short_real_prefix_are_rejected(self):
        for fault in ("missing", "extra_worker", "extra_episode", "epoch", "short"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                episode = fixture(root)
                if fault == "missing":
                    shutil.rmtree(episode)
                elif fault == "extra_worker":
                    (root / "worker2").mkdir()
                elif fault == "extra_episode":
                    (root / "worker0/episode005_open_101").mkdir()
                elif fault == "epoch":
                    mutate_json(episode / "motion_safety.jsonl", lambda rows:
                                rows[0].update(epoch="other_epoch"), True)
                else:
                    mutate_json(episode / "transitions.jsonl", lambda rows: rows.pop(), True)
                self.assertFalse(AUDIT.audit(root, FREEZE, CONSUMER)["passed"])

    def test_compressed_raw_inputs_remain_replayable_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            for path in root.glob("worker*/episode*/*.jsonl"):
                Path(str(path) + ".gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))
                path.unlink()
            result = AUDIT.audit(root, FREEZE, CONSUMER)
            self.assertTrue(result["passed"], result["errors"])
            self.assertTrue(any(path.endswith(".gz") for path in
                                result["episodes"][0]["input_bindings"]))


if __name__ == "__main__":
    unittest.main()
