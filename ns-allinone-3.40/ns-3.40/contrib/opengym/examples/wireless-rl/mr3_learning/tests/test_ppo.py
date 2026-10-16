"""CPU integration of real SB3 updates and closed-episode collection fixtures.

The environment below returns fixed contract tensors and explicit scalar
receipts. It never launches ROS, Gazebo, a reward process or a GPU operation.
"""

import copy
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from sb3_contrib import MaskablePPO
from stable_baselines3.common.logger import configure
import torch

from mr3_learning.observation import encode_snapshot, observation_space
from mr3_learning.policy import policy_kwargs
from mr3_learning.ppo import ContractSpaces, collect_episodes, infer, save_rollout
from mr3_learning.rollout import build_rollout_buffer
from mr3_learning.tests.test_observation import fixture


class ReceiptEnv:
    """Scripted API receipts with honest no-action and external-stop flags."""

    def __init__(self, script, *, epoch="fixture-episode", reset_error=None,
                 close_error=None, events=None):
        self.script = list(script)
        self.epoch = epoch
        self.reset_error = reset_error
        self.close_error = close_error
        self.events = [] if events is None else events
        self._steps = 0
        self._active_limit = None
        self.closed = 0
        self.actions = []
        self.observation = encode_snapshot(fixture())
        self.last_info = None
        self.supervisor = SimpleNamespace(
            episode=SimpleNamespace(directory=Path("/fixture") / epoch), receipts=[])

    def reset(self, *, seed, options):
        self.events.append((self.epoch, "reset", seed, options))
        if self.reset_error:
            raise self.reset_error
        self._steps = 0
        self._active_limit = options["max_steps"]
        return copy.deepcopy(self.observation), {"epoch": self.epoch}

    def step(self, action):
        self.actions.append(action)
        item = self.script[self._steps]
        if isinstance(item, Exception):
            raise item
        self._steps += 1
        item = dict(item)
        reward = item.get("reward", 1.)
        terminated = item.get("terminated", False)
        truncated = item.get("truncated", False)
        if item.get("zero_tail"):
            previous = self.last_info
            end = previous["reward_diagnostics"]["effective_step_end"]
            info = {
                **{key: copy.deepcopy(previous[key]) for key in
                   ("watermarks", "observation_sequence", "observation_digest", "candidate_version")},
                "epoch": self.epoch, "dt": 0., "physical_dt": 0.,
                "action_submitted": False, "terminal_observation_reused": True,
                "command": None, "requested_action": action, "bootstrap": 0,
                "reason": "navigation_failure",
                "reward_diagnostics": {
                    "epoch": self.epoch, "sequence": self._steps,
                    "terminated": True, "truncated": False, "reward": reward,
                    "delta_sim_time": 0., "new_correct_free_cells": 0,
                    "reward_terms": {"coverage": 0., "failure": reward},
                    "map_pairing_scope": "terminal_evaluator_frozen_before_drain",
                    "step_start": end, "effective_step_end": end,
                    "requested_step_end": end, "reason": "navigation_failure"}}
            return copy.deepcopy(self.observation), reward, True, False, info
        if not terminated and self._steps >= self._active_limit:
            truncated = True
        dt = item.get("dt", 1.)
        self.observation["task"][0] = self._steps / 300.
        info = {
            "epoch": self.epoch, "dt": dt, "physical_dt": item.get("physical_dt", dt),
            "action_submitted": True, "observation_sequence": self._steps + 1,
            "observation_digest": f"observation-{self._steps + 1}",
            "candidate_version": self._steps + 1,
            "watermarks": {"state_sequence": self._steps + 1},
            "command": {"observation_sequence": self._steps,
                        "observation_digest": f"observation-{self._steps}"},
            "reason": "task_success" if terminated else (
                "external_sampler_limit" if truncated else None),
            "reward_diagnostics": {"epoch": self.epoch, "sequence": self._steps,
                                   "step_start": float(self._steps - 1),
                                   "effective_step_end": float(self._steps - 1) + dt}}
        self.last_info = copy.deepcopy(info)
        self.events.append((self.epoch, "step", self._steps, terminated, truncated))
        return copy.deepcopy(self.observation), reward, terminated, truncated, info

    def close(self):
        self.closed += 1
        self.events.append((self.epoch, "close"))
        if self.close_error:
            raise self.close_error
        self.supervisor.receipts.append({"op": "close", "clean": True})


def tasks_for(environments, cap=10):
    return [{"scene": "open", "seed": 101 + index, "cap": cap,
             "episode_index": index, "worker_id": index}
            for index, _ in enumerate(environments)]


def fixture_infer(model, observations, *, deterministic=False):
    actions = np.array([np.flatnonzero(row["action_mask"])[0] for row in observations])
    return actions, np.full(len(actions), .25), np.full(len(actions), -.5)


class CollectorTests(unittest.TestCase):
    def collect(self, environments, *, deadline=None, cap=10):
        with patch("mr3_learning.ppo.infer", side_effect=fixture_infer), patch(
                "mr3_learning.ppo.next_value", return_value=.25):
            return collect_episodes(
                None, environments, tasks_for(environments, cap=cap),
                deadline=time.monotonic() + 60. if deadline is None else deadline)

    def test_same_boundary_zero_terminal_settles_previous_decision_before_return(self):
        environment = ReceiptEnv([{"reward": 2.}, {"zero_tail": True, "reward": -20.}])
        episodes, summaries = self.collect([environment])
        self.assertEqual(len(episodes[0]), 1)
        row = episodes[0][0]
        self.assertEqual(row.reward, -18.)
        self.assertEqual(row.dt, 1.)
        self.assertTrue(row.terminated)
        self.assertFalse(row.truncated)
        self.assertEqual(row.next_value, 0.)
        self.assertTrue(row.info["merged_zero_terminal"])
        self.assertEqual(summaries[0]["api_records"], 2)
        self.assertEqual(summaries[0]["decisions"], 1)
        self.assertEqual(summaries[0]["zero_terminal_events"], 1)
        self.assertEqual(summaries[0]["simulation_seconds"], 1.)
        self.assertEqual(summaries[0]["reward_sum"], -18.)
        self.assertEqual(environment.closed, 1)
        self.assertTrue(summaries[0]["shutdown"]["clean"])

    def test_executed_short_terminal_is_retained_as_an_actor_sample(self):
        environment = ReceiptEnv([
            {"reward": .2},
            {"reward": 10., "terminated": True, "dt": .011, "physical_dt": .02}])
        episodes, summaries = self.collect([environment])
        self.assertEqual(len(episodes[0]), 2)
        self.assertEqual(episodes[0][-1].dt, .011)
        self.assertEqual(episodes[0][-1].reward, 10.)
        self.assertTrue(episodes[0][-1].terminated)
        self.assertEqual(episodes[0][-1].next_value, 0.)
        self.assertEqual(summaries[0]["decisions"], 2)
        self.assertAlmostEqual(summaries[0]["simulation_seconds"], 1.011)

    def test_every_worker_closes_before_samples_can_reach_update(self):
        events = []
        environments = [ReceiptEnv([{"terminated": True}], epoch=f"episode-{index}",
                                   events=events) for index in range(2)]
        episodes, summaries = self.collect(environments)
        events.append(("optimizer", "update"))
        self.assertEqual([len(episode) for episode in episodes], [1, 1])
        for environment in environments:
            self.assertLess(events.index((environment.epoch, "close")),
                            events.index(("optimizer", "update")))
        self.assertTrue(all(summary["shutdown"]["clean"] for summary in summaries))

    def test_wall_stop_uses_external_truncation_and_retains_bootstrap(self):
        environment = ReceiptEnv([{"reward": .2}])
        episodes, summaries = self.collect([environment], deadline=0.)
        row = episodes[0][0]
        self.assertEqual(environment._active_limit, 1)
        self.assertTrue(row.truncated)
        self.assertFalse(row.terminated)
        self.assertEqual(row.dt, 1.)
        self.assertEqual(row.next_value, .25)
        self.assertEqual(summaries[0]["reason"], "external_sampler_limit")
        self.assertEqual(environment.closed, 1)

    def test_reset_step_and_shutdown_errors_propagate_without_training_samples(self):
        cases = [ReceiptEnv([], reset_error=RuntimeError("reset failed")),
                 ReceiptEnv([RuntimeError("physics failed")]),
                 ReceiptEnv([{"terminated": True}], close_error=RuntimeError("shutdown failed"))]
        for environment, reason in zip(cases, ("reset failed", "physics failed", "shutdown failed")):
            with self.subTest(reason=reason), self.assertRaisesRegex(RuntimeError, reason):
                self.collect([environment])

    def test_one_reset_failure_still_resolves_the_other_submitted_worker_reset(self):
        environments = [ReceiptEnv([], epoch="failure", reset_error=RuntimeError("bad reset")),
                        ReceiptEnv([], epoch="other")]
        with self.assertRaisesRegex(RuntimeError, "bad reset"):
            self.collect(environments)
        self.assertEqual(len(environments[1].events), 1)
        self.assertEqual(environments[1].events[0][1], "reset")

    def test_empty_or_mismatched_worker_tasks_are_rejected_before_reset(self):
        environment = ReceiptEnv([{"terminated": True}])
        for environments, tasks in (([], []), ([environment], []), ([], tasks_for([environment]))):
            with self.subTest(workers=len(environments), tasks=len(tasks)):
                with self.assertRaises(ValueError):
                    collect_episodes(None, environments, tasks, deadline=0.)
        self.assertFalse(environment.events)


class PPOIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.previous_threads)

    def model(self, batch_size=2):
        model = MaskablePPO(
            "MultiInputPolicy", ContractSpaces(), device="cpu", seed=17,
            n_steps=batch_size, batch_size=batch_size, n_epochs=2,
            policy_kwargs=policy_kwargs(), ent_coef=.01)
        model.set_logger(configure(folder=None, format_strings=[]))
        return model

    def test_infer_uses_exact_joint_masks_and_rejects_malformed_saved_masks(self):
        model = self.model()
        observation = encode_snapshot(fixture())
        actions, values, log_probs = infer(model, [observation], deterministic=True)
        self.assertTrue(observation["action_mask"][actions[0]])
        self.assertTrue(np.isfinite(values).all())
        self.assertTrue(np.isfinite(log_probs).all())
        for mask in (np.zeros(1000, dtype=np.int8), np.full(1000, 2, dtype=np.int8),
                     np.ones(999, dtype=np.int8)):
            with self.subTest(shape=mask.shape, maximum=mask.max()):
                bad = {**observation, "action_mask": mask}
                with self.assertRaisesRegex(ValueError, "binary joint mask"):
                    infer(model, [bad])

    def test_actual_sb3_update_preserves_rollout_contract_and_checkpoint_round_trip(self):
        model = self.model()
        environment = ReceiptEnv([
            {"reward": .2}, {"reward": -.1}, {"reward": .5},
            {"reward": 10., "terminated": True, "dt": .02}])
        episodes, _ = collect_episodes(
            model, [environment], tasks_for([environment]), deadline=time.monotonic() + 60.)
        self.assertEqual(environment.closed, 1)
        buffer = build_rollout_buffer(
            episodes, observation_space(), model.action_space, device="cpu")
        # PPO's exact saved sample/mask must reproduce the collecting policy's
        # probabilities before any optimizer runs.
        sample = next(buffer.get(batch_size=4))
        with torch.no_grad():
            _, reevaluated, _ = model.policy.evaluate_actions(
                sample.observations, sample.actions.long().flatten(),
                action_masks=sample.action_masks)
        torch.testing.assert_close(reevaluated, sample.old_log_prob, rtol=1e-6, atol=1e-6)
        self.assertEqual(buffer.durations[-1], .02)
        actor_before = model.policy.action_net.weight.detach().clone()
        critic_before = model.policy.value_net.weight.detach().clone()
        map_before = model.policy.features_extractor.encoder.global_encoder[0].weight.detach().clone()
        model.rollout_buffer = buffer
        model.num_timesteps = 4
        model._current_progress_remaining = .5
        updates = []

        def record_update(*unused):
            self.assertEqual(environment.closed, 1)
            updates.append(1)

        hook = model.policy.optimizer.register_step_post_hook(record_update)
        try:
            model.train()
        finally:
            hook.remove()
        self.assertEqual(len(updates), 4)
        self.assertFalse(torch.equal(actor_before, model.policy.action_net.weight))
        self.assertFalse(torch.equal(critic_before, model.policy.value_net.weight))
        self.assertFalse(torch.equal(map_before,
                                     model.policy.features_extractor.encoder.global_encoder[0].weight))
        self.assertTrue(all(torch.isfinite(parameter).all() for parameter in model.policy.parameters()))
        for key in ("train/entropy_loss", "train/approx_kl", "train/value_loss"):
            self.assertTrue(np.isfinite(model.logger.name_to_value[key]))
        observation = encode_snapshot(fixture())
        mask = observation["action_mask"].astype(bool)
        before = infer(model, [observation], deterministic=True)
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.zip"
            model.save(checkpoint)
            loaded = MaskablePPO.load(checkpoint, device="cpu")
            after = infer(loaded, [observation], deterministic=True)
            for actual, expected in zip(after, before):
                np.testing.assert_array_equal(actual, expected)
            # save_rollout is called before SB3 get() reshapes the arrays in the
            # CLI; a fresh buffer retains the native (N,1,...) audit form here.
            saved = build_rollout_buffer(episodes, observation_space(), model.action_space)
            path = Path(directory) / "rollout.npz"
            save_rollout(path, saved, episodes)
            with np.load(path) as archive:
                self.assertEqual(archive["masks"].shape, (4, 1, 1000))
                self.assertEqual(archive["dt"][-1], .02)
                np.testing.assert_array_equal(archive["obs_action_mask"].astype(bool),
                                              archive["masks"].astype(bool))
        self.assertTrue(mask[int(before[0][0])])

    def test_odd_episode_size_has_no_singleton_minibatch_or_nonfinite_sb3_update(self):
        model = self.model(batch_size=2)
        environment = ReceiptEnv([
            {"reward": .2}, {"reward": -.1}, {"reward": .5}, {"reward": -.2},
            {"reward": 10., "terminated": True}])
        episodes, _ = collect_episodes(
            model, [environment], tasks_for([environment]), deadline=time.monotonic() + 60.)
        buffer = build_rollout_buffer(episodes, observation_space(), model.action_space)
        self.assertEqual([len(batch.actions) for batch in buffer.get(2)], [2, 3])
        model.rollout_buffer = buffer
        model.num_timesteps = 5
        model._current_progress_remaining = .5
        model.train()
        self.assertEqual(model._n_updates, 2)
        self.assertTrue(all(torch.isfinite(parameter).all() for parameter in model.policy.parameters()))
        for key in ("train/policy_gradient_loss", "train/value_loss", "train/approx_kl"):
            self.assertTrue(np.isfinite(model.logger.name_to_value[key]))


if __name__ == "__main__":
    unittest.main()
