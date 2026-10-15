"""Synthetic arithmetic/storage validation only; never simulator execution."""

import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "resource_helper", Path(__file__).with_name("resource_analysis_v2.py"))
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class HelperTests(unittest.TestCase):
    def test_terminal_diagnostic_resources_are_kept_without_fair_throughput_credit(self):
        for terminal_probe in (False, True):
            with self.subTest(terminal_probe=terminal_probe), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                steps = 4 if terminal_probe else 16
                metadata = {"freeze": "synthetic", "workers": 1,
                            "schedule": [["open", 101]] * 2,
                            "terminal_probe": terminal_probe, "fault_probe": False,
                            "deadline_probe": False}
                cells = []
                for index in range(2):
                    episode = directory / "worker0" / f"episode{index + 1:03d}_open_101"
                    episode.mkdir(parents=True)
                    cell = {"scene": "open", "seed": 101, "epoch": f"synthetic{index}",
                            "transitions": steps, "startup_wall_sec": 1.,
                            "wall_sec_including_startup_and_closure": 3. + index,
                            "transition_wall_sec": 1., "terminated": terminal_probe,
                            "truncated": not terminal_probe}
                    cells.append(cell)
                    rows = [{"kind": "reset" if step == 0 else "step",
                             "snapshot": {"source_stamp": 10. + step},
                             "terminated": terminal_probe and step == steps,
                             "truncated": not terminal_probe and step == steps,
                             "info": {"step_wall_sec": .1}}
                            for step in range(steps + 1)]
                    (episode / "transitions.jsonl").write_text(
                        "".join(json.dumps(row) + "\n" for row in rows))
                    (episode / "supervisor_shutdown.json").write_text("{}")
                    (episode / "summary.json").write_text('{"cleanup_wall_sec": 0.2}')
                summary = {"passed": True, "valid_transitions": steps * 2,
                           "wall_sec_including_all_attempts": 8.,
                           "effective_transition_per_wall_sec": steps / 4.,
                           "workers_results": [{"worker_id": 0, "episodes": cells}]}
                for path, value in (("benchmark_metadata.json", metadata),
                                    ("benchmark_summary.json", summary), ("resources.json", [])):
                    (directory / path).write_text(json.dumps(value))
                result = HELPER.analyze(directory)
                self.assertGreater(result["storage"]["logical_raw_bytes"], 0)
                self.assertEqual(result["valid_transitions"], steps * 2)
                self.assertEqual(result["terminal_probe"], terminal_probe)
                self.assertEqual(result["fair_comparison"]["eligible"], not terminal_probe)
                self.assertEqual(result["conditional_16_vs_300_step_projections"][
                    "source_episode_count"], 0 if terminal_probe else 2)

    def test_process_scan_summary_preserves_real_maxima_and_legacy_missing_values(self):
        first = {"process_scan_statistics": {"count": 12, "max_scan_wall_sec": .3,
                                             "max_observed_interval_sec": 1.25}}
        second = {"process_scan_statistics": {"count": 20, "max_scan_wall_sec": .7,
                                              "max_observed_interval_sec": .8}}
        result = HELPER.process_scan_summary([first, second])
        self.assertEqual(result["count"], 32)
        self.assertEqual(result["max_scan_wall_sec"], .7)
        self.assertEqual(result["max_observed_interval_sec"], 1.25)
        self.assertTrue(result["all_receipts_measured"])
        legacy = HELPER.process_scan_summary([{}, {}])
        self.assertEqual(legacy["unmeasured_receipt_count"], 2)
        self.assertIsNone(legacy["count"])
        self.assertIsNone(legacy["max_scan_wall_sec"])
        self.assertIsNone(legacy["max_observed_interval_sec"])
        mixed = HELPER.process_scan_summary([first, {}])
        self.assertEqual(mixed["count"], 12)
        self.assertEqual(mixed["measured_receipt_count"], 1)
        self.assertFalse(mixed["all_receipts_measured"])
        with self.assertRaises(ValueError):
            HELPER.process_scan_summary([{"process_scan_statistics": {
                "count": 1, "max_scan_wall_sec": float("nan"), "max_observed_interval_sec": .05}}])

    def test_cpu_weighted_utilization_memory_and_gpu_are_host_wide(self):
        samples = []
        for now, total, idle, available, gpu in (
                (1., 100, 10, 800, [0, 10, 30, 1000]),
                (2., 200, 60, 700, [0, 80, 20, 1000]),
                (4., 500, 60, 900, [0, 40, 70, 1000])):
            samples.append({"monotonic": now, "cpu_total_ticks": total, "cpu_idle_ticks": idle,
                            "mem_total_kib": 1000, "mem_available_kib": available, "gpu": [gpu]})
        result = HELPER.resource_summary(samples)
        self.assertEqual(result["host_cpu_tick_weighted_utilization_percent"], 87.5)
        self.assertEqual(result["host_cpu_interval_utilization_percent"]["mean"], 75.)
        self.assertEqual(result["host_mem_available_min_bytes"], 700 * 1024)
        self.assertEqual(result["host_mem_used_estimate_peak_bytes"], 300 * 1024)
        self.assertEqual(result["gpu_driver_per_card"]["0"]["peak_used_mib"], 70)
        self.assertEqual(result["gpu_driver_per_card"]["0"]["max_utilization_percent"], 80)
        self.assertIsNone(result["owned_rss_bytes"])

    def test_raw_and_compressed_copy_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            payload = b"same native evidence\n" * 100
            (directory / "one.log").write_bytes(payload)
            compressed = gzip.compress(payload, mtime=0)
            (directory / "one.log.gz").write_bytes(compressed)
            result = HELPER.storage_totals(HELPER.storage_inventory(directory))
            self.assertEqual(result["logical_raw_bytes"], len(payload))
            self.assertEqual(result["gzip_copy_bytes"], len(compressed))
            self.assertEqual(result["physical_apparent_bytes"], len(payload) + len(compressed))
            self.assertEqual(result["compact_archive_bytes"], len(compressed))
            (directory / "one.log.gz").write_bytes(gzip.compress(b"different", mtime=0))
            result = HELPER.storage_inventory(directory)
            self.assertFalse(result[0]["gzip_matches_raw"])
            self.assertEqual(result[0]["compact_archive_bytes"], len(payload))

    def test_300_step_projection_amortizes_identified_fixed_cost(self):
        parts = {"fixed": 160., "per_step": 1600., "unattributed": 160.}
        cell = {"valid_for_extrapolation": True,
                "time_cost_model": {"recorded_fixed_wall_sec": 126.,
                                    "recorded_variable_wall_sec_per_transition": 7.},
                "phase_storage": {"bytes": {"raw": parts, "compact_ratio_held": parts}}}
        result = HELPER.projections([cell])["1500000"]
        self.assertEqual(result["16"]["serial_recorded_wall_sec_range"], [22312500., 22312500.])
        self.assertEqual(result["300"]["serial_recorded_wall_sec_range"], [11130000., 11130000.])
        self.assertEqual(result["16"]["storage_bytes_envelope"]["raw"], [180000000., 180000000.])
        self.assertEqual(result["300"]["storage_bytes_envelope"]["raw"], [151600000., 165800000.])


if __name__ == "__main__":
    unittest.main()
