"""Physical-nanosecond deadline regressions; pure CPU, no ROS or simulator."""

import math
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

from multi_robot_exploration.mr3_reward import RewardLedger, elapsed_ns, timestamp_ns
from multi_robot_exploration import mr3_episode, mr3_reward


class RewardNanosecondTests(unittest.TestCase):
    def test_public_episode_rules_import_without_reward_truth_or_array_dependencies(self):
        source = Path(mr3_episode.__file__).resolve()
        script = (
            "import importlib.util,sys; "
            "s=importlib.util.spec_from_file_location('episode_rules',sys.argv[1]); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "assert m.elapsed_ns(212.06,512.06)==300000000000; "
            "assert 'numpy' not in sys.modules; "
            "assert not any(n.endswith('mr3_reward') for n in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-I", "-c", script, str(source)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(mr3_reward._finite_time, mr3_episode.finite_time)
        self.assertIs(mr3_reward.timestamp_ns, mr3_episode.timestamp_ns)
        self.assertIs(mr3_reward.elapsed_ns, mr3_episode.elapsed_ns)
        self.assertIs(mr3_reward.TASK_FAILURE_REASONS, mr3_episode.TASK_FAILURE_REASONS)

    @staticmethod
    def ledger(start=212.06):
        return RewardLedger("epoch", start, np.ones((2, 2), bool), np.zeros((2, 2), bool))

    @staticmethod
    def advance(book, start, end, sequence=1, **kwargs):
        return book.advance(epoch="epoch", sequence=sequence, step_start=start, step_end=end,
                            current_correct_free_mask=np.zeros((2, 2), bool),
                            collision_events=0, goal_switches=0, rejected_actions=0, **kwargs)

    def test_original_float_counterexample_recovers_exact_endpoint_nanoseconds(self):
        self.assertLess(512.06 - 212.06, 300.)
        self.assertEqual(timestamp_ns(212.06), 212060000000)
        self.assertEqual(timestamp_ns(512.06), 512060000000)
        self.assertEqual(elapsed_ns(212.06, 512.06), 300000000000)
        self.assertEqual(elapsed_ns(512.06, 212.06), -300000000000)

    def test_exact_deadline_terminates_before_success_or_external_truncation(self):
        result = self.advance(self.ledger(), 212.06, 512.06,
                              terminal_reason="coverage_reached", external_truncation="sampler")
        self.assertTrue(result["terminated"])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["reason"], "timeout")
        self.assertEqual(result["elapsed_sim_time"], 300.)
        self.assertEqual(result["remaining_sim_time"], 0.)
        self.assertEqual(result["delta_sim_time"], 300.)
        self.assertEqual(result["reward_terms"]["time"], -1.)
        self.assertEqual(result["reward_terms"]["success"], 0.)
        self.assertEqual(result["effective_step_end"], 512.06)
        self.assertIsInstance(result["effective_step_end"], float)
        self.assertIsInstance(result["delta_sim_time"], float)

    def test_one_nanosecond_before_deadline_is_not_artificially_timed_out(self):
        end = 512059999999 / 1e9
        result = self.advance(self.ledger(), 212.06, end, external_truncation="sampler")
        self.assertFalse(result["terminated"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["remaining_sim_time"], 1e-9)
        success = self.advance(self.ledger(), 212.06, end, terminal_reason="coverage_reached")
        self.assertEqual(success["reason"], "coverage_reached")

    def test_one_nanosecond_after_deadline_does_not_extend_the_task(self):
        result = self.advance(self.ledger(), 212.06, 512060000001 / 1e9,
                              external_truncation="sampler")
        self.assertTrue(result["terminated"])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["reason"], "timeout")

    def test_300_physical_steps_keep_unit_durations_and_exact_final_elapsed(self):
        book = self.ledger()
        start_ns = timestamp_ns(book.start_sim_time)
        previous = book.start_sim_time
        for sequence in range(1, 301):
            end = (start_ns + sequence * 10**9) / 1e9
            result = self.advance(book, previous, end, sequence=sequence,
                                  external_truncation="sampler" if sequence == 300 else None)
            self.assertEqual(result["delta_sim_time"], 1.)
            self.assertEqual(result["elapsed_sim_time"], float(sequence))
            self.assertEqual(result["terminated"], sequence == 300)
            self.assertFalse(result["truncated"])
            previous = end
        self.assertEqual(result["reason"], "timeout")

    def test_one_nanosecond_gap_or_rewind_is_rejected_without_advancing_ledger(self):
        book = self.ledger()
        self.advance(book, 212.06, 213.06)
        with self.assertRaisesRegex(ValueError, "contiguous"):
            self.advance(book, 213060000001 / 1e9, 214.06, sequence=2)
        self.assertEqual(book.last_sequence, 1)
        with self.assertRaisesRegex(ValueError, "backwards"):
            self.advance(self.ledger(), 212.06, 212059999999 / 1e9)

    def test_zero_physical_duration_needs_an_explicit_ending(self):
        with self.assertRaisesRegex(ValueError, "advance simulation time"):
            self.advance(self.ledger(), 212.06, 212.06 + 1e-10)
        result = self.advance(self.ledger(), 212.06, 212.06,
                              external_truncation="environment_close")
        self.assertEqual(result["delta_sim_time"], 0.)
        self.assertTrue(result["truncated"])

    def test_late_zero_terminal_map_cannot_pay_new_coverage_and_penalty_is_idempotent(self):
        book = self.ledger()
        initial_gain = np.array([[True, False], [False, False]])
        fields = {"epoch": "epoch", "collision_events": 0, "goal_switches": 0,
                  "rejected_actions": 0}
        first = book.advance(**fields, sequence=1, step_start=212.06, step_end=213.06,
                             current_correct_free_mask=initial_gain)
        self.assertEqual(first["new_correct_free_cells"], 1)
        self.assertEqual(first["reward_terms"]["coverage"], 2.5)
        request = {**fields, "sequence": 2, "step_start": 213.06, "step_end": 213.06,
                   "current_correct_free_mask": np.ones((2, 2), bool),
                   "terminal_reason": "navigation_failure"}
        last = book.advance(**request)
        self.assertEqual(last["delta_sim_time"], 0.)
        self.assertEqual(last["current_correct_free_cells"], 4)
        self.assertEqual(last["new_correct_free_cells"], 0)
        self.assertEqual(last["rewarded_correct_free_cells"], 1)
        self.assertEqual(last["reward_terms"]["coverage"], 0.)
        self.assertEqual(last["reward_terms"]["failure"], -20.)
        self.assertEqual(last["reward"], -20.)
        last["reward_terms"]["failure"] = -999.
        self.assertEqual(book.advance(**request)["reward"], -20.)
        self.assertEqual(book.rewarded_correct_count, 1)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            book.advance(**{**request, "current_correct_free_mask": initial_gain})

    def test_positive_short_terminal_still_pays_first_correct_coverage(self):
        book = self.ledger()
        last = book.advance(epoch="epoch", sequence=1, step_start=212.06, step_end=212.08,
                            current_correct_free_mask=np.ones((2, 2), bool),
                            collision_events=0, goal_switches=0, rejected_actions=0,
                            terminal_reason="navigation_failure")
        self.assertEqual(last["delta_sim_time"], .02)
        self.assertEqual(last["new_correct_free_cells"], 4)
        self.assertEqual(last["reward_terms"]["coverage"], 10.)
        self.assertEqual(last["reward_terms"]["failure"], -20.)

    def test_terminal_duplicate_and_payload_conflict_semantics_are_preserved(self):
        book = self.ledger()
        result = self.advance(book, 212.06, 512.06, external_truncation="sampler")
        result["reward_terms"]["time"] = 999.
        duplicate = self.advance(book, 212.06, 512.06, external_truncation="sampler")
        self.assertEqual(duplicate["reward_terms"]["time"], -1.)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.advance(book, 212.06, 512.06 + 1e-10, external_truncation="sampler")
        self.assertTrue(book.sealed)

    def test_timestamp_conversion_rejects_invalid_times(self):
        for value in (True, -1., math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                timestamp_ns(value)


if __name__ == "__main__":
    unittest.main()
