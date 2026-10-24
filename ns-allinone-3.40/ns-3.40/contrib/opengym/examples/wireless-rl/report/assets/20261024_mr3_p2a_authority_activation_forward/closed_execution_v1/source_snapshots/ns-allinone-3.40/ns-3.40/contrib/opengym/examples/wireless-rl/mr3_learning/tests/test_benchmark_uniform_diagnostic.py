"""CPU checks for legal random engineering inputs and fail-closed reset flow."""

import contextlib
import copy
import io
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import benchmark


class UniformDiagnosticTests(unittest.TestCase):
    def test_uniform_choice_receives_all_and_only_actual_legal_joint_actions(self):
        mask = [False] * 1000
        for action in (0, 231, 658, 888, 999):
            mask[action] = True
        snapshot = {"joint_action_mask": mask}
        original = copy.deepcopy(snapshot)
        generator = unittest.mock.Mock()
        generator.choice.return_value = 658
        self.assertEqual(benchmark.diagnostic_uniform_action(snapshot, generator), 658)
        generator.choice.assert_called_once_with([0, 231, 658, 888, 999])
        self.assertEqual(snapshot, original)

    def test_malformed_or_empty_mask_is_rejected_without_sampling(self):
        for mask in ([], [False] * 999, [False] * 1000, [0] * 1000,
                     [True] * 999 + [1], tuple([True] * 1000)):
            with self.subTest(mask_type=type(mask), length=len(mask)):
                generator = unittest.mock.Mock()
                with self.assertRaises(ValueError):
                    benchmark.diagnostic_uniform_action({"joint_action_mask": mask}, generator)
                generator.choice.assert_not_called()

    def test_conflicts_and_negative_seeds_reject_before_files_sources_or_native(self):
        conflicts = (["--preparation-motion-probe"],
                     ["--preparation-probe-version", benchmark.PREPARATION_PROBE_REACH_V1],
                     ["--preparation-parameter-review"],
                     ["--preparation-parameter-profile", "original"],
                     ["--preparation-parameter-profile=gentle_turn_v1"],
                     ["--terminal-probe"], ["--deadline-probe"], ["--fault-probe"])
        for flags in (*conflicts, ["--diagnostic-uniform-seed", "-1"]):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as root:
                args = ["--workers", "1", "--run-id", "rejected", "--output-root", root,
                        "--diagnostic-uniform-seed", "17", *flags]
                with patch.object(benchmark.Path, "mkdir") as mkdir, \
                        patch.object(benchmark, "Supervisor") as supervisor, \
                        patch.object(benchmark, "_parameter_review_binding") as review, \
                        patch.object(benchmark.subprocess, "check_output") as source, \
                        contextlib.redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as failed:
                    benchmark.main(args)
                self.assertEqual(failed.exception.code, 2)
                for operation in (mkdir, supervisor, review, source):
                    operation.assert_not_called()
                self.assertEqual(list(Path(root).iterdir()), [])

    def args(self, root, *, seed=17, steps=8):
        return SimpleNamespace(
            diagnostic_uniform_seed=seed, safety_contract="mr3-reach-v1",
            run_id="uniform_cpu", base_domain=180, base_port=14701,
            output_root=root, terminal_probe=False, deadline_probe=False,
            fault_probe=False, preparation_motion_probe=False,
            steps=steps, schedule=[("open", 101), ("open", 101)])

    def run_worker(self, *, seed=17, worker_id=0, step_result=None, reset_error=None,
                   steps=8):
        instances = []
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            class Supervisor:
                def __init__(self, **kwargs):
                    self.directory = root / "worker"
                    self.directory.mkdir()
                    self.receipts = []

            class Environment:
                def __init__(self, *, supervisor, max_steps):
                    self.supervisor, self.max_steps = supervisor, max_steps
                    self.reset_calls = self.step_calls = self.close_calls = 0
                    self.actions = []
                    instances.append(self)

                def snapshot(self):
                    # This contains no goal coordinates/rankings. Each input must use
                    # the current mask rather than an earlier episode's mask.
                    mask = [False] * 1000
                    allowed = ((0, 231, 658, 888, 999) if self.episode_steps % 2 == 0
                               else (1, 45, 123, 887, 998))
                    for action in allowed:
                        mask[action] = True
                    self.supervisor.last_result = {"snapshot": {
                        "sequence": self.episode_steps + 1,
                        "digest": f"episode{self.reset_calls}-step{self.episode_steps}",
                        "joint_action_mask": mask, "robots": []}}

                def reset(self, **kwargs):
                    self.reset_calls += 1
                    if reset_error:
                        raise reset_error
                    self.episode_steps, self._episode_done = 0, False
                    self.supervisor.episode = SimpleNamespace(
                        directory=root / f"episode{self.reset_calls}")
                    self.snapshot()
                    return None, {"epoch": f"epoch-{self.reset_calls}",
                                  "observation_digest": "cpu-only", "startup_wall_sec": 0.}

                def step(self, action):
                    if not self.supervisor.last_result["snapshot"]["joint_action_mask"][action]:
                        raise AssertionError("selected an illegal action from a stale mask")
                    self.actions.append(action)
                    self.step_calls += 1
                    self.episode_steps += 1
                    if isinstance(step_result, Exception):
                        raise step_result
                    terminated, truncated, reason = (step_result or (
                        False, self.episode_steps == self.max_steps,
                        "external_sampler_limit" if self.episode_steps == self.max_steps else None))
                    self._episode_done = terminated or truncated
                    self.snapshot()
                    return None, 1., terminated, truncated, {"dt": 1., "reason": reason}

                def close(self):
                    self.close_calls += 1

            with patch.object(benchmark, "Supervisor", Supervisor), \
                    patch.object(benchmark, "MR3Env", Environment), \
                    patch.object(benchmark, "probe_action", side_effect=AssertionError(
                        "diagnostic must not call the scripted goal ranker")):
                result = benchmark.run_worker(self.args(root, seed=seed, steps=steps), worker_id)
        return result, instances[0]

    def test_two_external_truncations_reset_normally_and_preserve_real_returns(self):
        result, instance = self.run_worker()
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (2, 16, 1))
        self.assertIsNone(result["error"])
        self.assertFalse(result["diagnostic_abort"]["requested"])
        self.assertEqual([episode["transitions"] for episode in result["episodes"]], [8, 8])
        self.assertTrue(all(episode["truncated"] and not episode["terminated"]
                            for episode in result["episodes"]))
        self.assertEqual(sum(episode["reward_sum"] for episode in result["episodes"]), 16.)

    def test_seed_reproduces_the_stream_and_each_worker_has_its_own_seed(self):
        result0, instance0 = self.run_worker(seed=41, worker_id=0)
        _, repeat = self.run_worker(seed=41, worker_id=0)
        result1, instance1 = self.run_worker(seed=41, worker_id=1)
        self.assertEqual(instance0.actions, repeat.actions)
        self.assertNotEqual(instance0.actions, instance1.actions)
        self.assertEqual(result0["diagnostic_uniform_worker_seed"], 41)
        self.assertEqual(result1["diagnostic_uniform_worker_seed"], 1000044)
        for worker, instance in ((0, instance0), (1, instance1)):
            generator = random.Random(41 + 1000003 * worker)
            expected = [generator.choice([0, 231, 658, 888, 999] if index % 2 == 0
                                         else [1, 45, 123, 887, 998]) for index in range(16)]
            self.assertEqual(instance.actions, expected)

    def test_real_task_failure_stops_before_another_step_or_reset(self):
        result, instance = self.run_worker(step_result=(True, False, "navigation_failure"))
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (1, 1, 1))
        self.assertEqual(result["episodes"][0]["transitions"], 1)
        self.assertEqual(result["episodes"][0]["reward_sum"], 1.)
        self.assertTrue(result["episodes"][0]["terminated"])
        self.assertEqual(result["diagnostic_abort"]["first_failure"]["kind"], "task_failure")

    def test_success_can_finish_early_and_continue_to_the_next_declared_episode(self):
        result, instance = self.run_worker(step_result=(True, False, "coverage_reached"))
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (2, 2, 1))
        self.assertFalse(result["diagnostic_abort"]["requested"])

    def test_unexpected_truncation_stops_the_remaining_schedule(self):
        result, instance = self.run_worker(step_result=(False, True, "other_reason"))
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (1, 1, 1))
        self.assertEqual(result["diagnostic_abort"]["first_failure"]["kind"], "unexpected_truncation")

    def test_step_exception_closes_without_inventing_a_returned_transition_or_reset(self):
        result, instance = self.run_worker(step_result=RuntimeError("actual RPC failure"))
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (1, 1, 1))
        self.assertEqual(result["episodes"][0]["transitions"], 0)
        self.assertNotIn("terminated", result["episodes"][0])
        self.assertIn("actual RPC failure", result["error"])
        self.assertEqual(result["diagnostic_abort"]["first_failure"]["kind"], "rpc_or_worker_exception")

    def test_reset_exception_closes_and_does_not_retry(self):
        result, instance = self.run_worker(reset_error=RuntimeError("actual reset failure"))
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (1, 0, 1))
        self.assertEqual(result["episodes"], [])
        self.assertIn("actual reset failure", result["error"])

    def test_cli_metadata_and_summary_keep_random_collection_ineligible_for_training(self):
        for success in (False, True):
            with self.subTest(success=success), tempfile.TemporaryDirectory() as root:
                def complete(args, worker_id, abort):
                    self.assertIsNotNone(abort)
                    return {"worker_id": worker_id, "error": None, "episodes": [
                        {"transitions": 1 if success else 2, "terminated": success,
                         "truncated": not success, "dt_values": [1.] * (1 if success else 2),
                         "reason": "coverage_reached" if success else "external_sampler_limit"}],
                        "shutdown_receipts": [{"remaining_owned_processes": [],
                            "remaining_owned_zombies": [], "forced_shutdown": False,
                            "worker_returncode": 0}]}
                with patch.object(benchmark, "run_worker", side_effect=complete), \
                        patch.object(benchmark, "resource_sample", return_value={}), \
                        patch.object(benchmark.subprocess, "check_output", return_value="a" * 40), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(benchmark.main([
                        "--workers", "1", "--schedule", "open:101", "--steps", "2",
                        "--run-id", "cpu", "--output-root", root,
                        "--diagnostic-uniform-seed", "0", "--safety-contract", "mr3-reach-v1"]), 0)
                for filename in ("benchmark_metadata.json", "benchmark_summary.json"):
                    value = json.loads((Path(root) / "cpu" / filename).read_text())
                    self.assertEqual(value["kind"], "uniform_legal_engineering_diagnostic_not_rl")
                    self.assertFalse(value["training_eligible"])
                    self.assertFalse(value["policy_reliability_credit"])
                    self.assertEqual(value["diagnostic_uniform_seed"], 0)
                    self.assertEqual((value["policy_calls"], value["optimizer_steps"], value["gpu_calls"]),
                                     (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
