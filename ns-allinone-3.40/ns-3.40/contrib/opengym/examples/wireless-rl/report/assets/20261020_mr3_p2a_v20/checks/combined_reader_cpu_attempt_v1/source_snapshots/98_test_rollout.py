"""Adversarial CPU checks for mask replay, terminal settlement and GAE."""

import copy
from dataclasses import replace
import unittest

from gymnasium import spaces
import numpy as np
import torch
from sb3_contrib.common.maskable.buffers import MaskableDictRolloutBuffer

from mr3_learning.rollout import DecisionTransition, build_rollout_buffer, merge_zero_terminal


OBSERVATIONS = spaces.Dict({
    "state": spaces.Box(-100., 100., shape=(2,), dtype=np.float32),
    "action_mask": spaces.Box(0, 1, shape=(4,), dtype=np.int8),
})
ACTIONS = spaces.Discrete(4)


def decision(*, epoch="episode-a", index=1, reward=1., value=0., next_value=0., dt=1.,
             terminated=False, truncated=False, physical_dt=None, mask=None):
    mask = np.asarray([1, 0, 1, 0] if mask is None else mask, dtype=np.int8)
    info = {
        "epoch": epoch, "dt": dt, "physical_dt": dt if physical_dt is None else physical_dt,
        "observation_sequence": index + 1, "observation_digest": f"digest-{index + 1}",
        "candidate_version": f"candidate-{index + 1}", "watermarks": {"state_sequence": index},
        "command": {"command_id": index},
        "reward_diagnostics": {"epoch": epoch, "sequence": index,
                               "step_start": 79. + index,
                               "effective_step_end": 79. + index + dt},
    }
    return DecisionTransition(
        observation={"state": np.array([index, 1], dtype=np.float32), "action_mask": mask},
        action=0, reward=reward, value=value, log_prob=-.7, next_value=next_value,
        dt=dt, terminated=terminated, truncated=truncated, info=info,
    )


def settlement(previous, *, reward=-20.):
    end = previous.info["reward_diagnostics"]["effective_step_end"]
    return {
        "epoch": previous.info["epoch"], "dt": 0., "physical_dt": 0.,
        "action_submitted": False, "terminal_observation_reused": True,
        "requested_action": 2, "command": None, "bootstrap": 0, "reason": "navigation_failure",
        "watermarks": copy.deepcopy(previous.info["watermarks"]),
        **{key: previous.info[key] for key in
           ("observation_sequence", "observation_digest", "candidate_version")},
        "reward_diagnostics": {
            "epoch": previous.info["epoch"],
            "sequence": previous.info["reward_diagnostics"]["sequence"] + 1,
            "terminated": True, "truncated": False, "reward": reward,
            "delta_sim_time": 0., "step_start": end, "effective_step_end": end,
            "requested_step_end": end, "new_correct_free_cells": 0,
            "reward_terms": {"coverage": 0., "failure": reward},
            "map_pairing_scope": "terminal_evaluator_frozen_before_drain",
            "reason": "navigation_failure",
        },
    }


class RolloutTests(unittest.TestCase):
    def test_snapshot_mask_and_metadata_are_detached_from_later_updates(self):
        row = decision()
        observation = {key: value.copy() for key, value in row.observation.items()}
        mask = observation["action_mask"]
        info = copy.deepcopy(row.info)
        saved = replace(row, observation=observation, info=info, action_mask=mask)
        mask[:] = 0
        observation["state"][:] = 99
        info["watermarks"]["state_sequence"] = 999
        np.testing.assert_array_equal(saved.action_mask, [1, 0, 1, 0])
        np.testing.assert_array_equal(saved.observation["state"], [1., 1.])
        self.assertEqual(saved.info["watermarks"]["state_sequence"], 1)
        with self.assertRaises(ValueError):
            saved.action_mask[0] = False
        with self.assertRaises(ValueError):
            saved.observation["state"][0] = 2

    def test_illegal_action_and_recomputed_mask_are_rejected(self):
        row = decision()
        with self.assertRaisesRegex(ValueError, "legal"):
            replace(row, action=1)
        with self.assertRaisesRegex(ValueError, "sampling"):
            replace(row, action_mask=np.ones(4, dtype=bool))
        for value in (float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(row, reward=value)

    def test_only_true_submitted_terminal_can_have_zero_effective_dt(self):
        row = decision(dt=0., physical_dt=.02, terminated=True, reward=-20.)
        buffer = build_rollout_buffer([[row]], OBSERVATIONS, ACTIONS)
        self.assertEqual(buffer.buffer_size, 1)
        self.assertEqual(buffer.durations[0], 0.)
        self.assertEqual(buffer.returns[0, 0], -20.)
        for changes in ({"terminated": False}, {"info": row.info | {"physical_dt": 0.}},
                        {"info": row.info | {"action_submitted": False}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(row, **changes)

    def test_live_or_externally_truncated_variable_duration_is_rejected(self):
        for dt in (0., .02, .99, 1.01):
            for truncated in (False, True):
                with self.subTest(dt=dt, truncated=truncated), self.assertRaises(ValueError):
                    decision(dt=dt, truncated=truncated)

    def test_zero_terminal_settles_prior_action_once_without_extra_discount(self):
        previous = decision(reward=2., value=.5, next_value=3.)
        tail_info = settlement(previous)
        merged = merge_zero_terminal(previous, -20., tail_info)
        self.assertEqual(merged.reward, -18.)
        self.assertTrue(merged.terminated)
        self.assertFalse(merged.truncated)
        self.assertEqual(merged.next_value, 0.)
        self.assertEqual(merged.action, previous.action)
        self.assertEqual(merged.log_prob, previous.log_prob)
        self.assertEqual(merged.dt, 1.)
        np.testing.assert_array_equal(merged.action_mask, previous.action_mask)
        self.assertEqual(previous.reward, 2.)
        self.assertFalse(previous.terminated)
        buffer = build_rollout_buffer([[merged]], OBSERVATIONS, ACTIONS, gamma=.5, gae_lambda=1.)
        self.assertEqual(buffer.buffer_size, 1)
        self.assertAlmostEqual(buffer.returns[0, 0], -18.)
        self.assertAlmostEqual(buffer.advantages[0, 0], -18.5)
        with self.assertRaises(ValueError):
            merge_zero_terminal(None, -20., tail_info)
        with self.assertRaises(ValueError):
            merge_zero_terminal(merged, -20., tail_info)

    def test_zero_terminal_does_not_create_rollout_boundary_or_extra_gamma(self):
        first = decision(index=1, reward=1., value=0., next_value=2.)
        second = decision(index=2, reward=2., value=2., next_value=9.)
        merged = merge_zero_terminal(second, -20., settlement(second))
        buffer = build_rollout_buffer([[first, merged]], OBSERVATIONS, ACTIONS,
                                      gamma=.5, gae_lambda=1.)
        np.testing.assert_allclose(buffer.returns[:, 0], [-8., -18.])
        self.assertEqual(buffer.buffer_size, 2)
        self.assertEqual(sum(row.get("merged_zero_terminal", False)
                             for row in buffer.transition_metadata), 1)

    def test_zero_terminal_rejects_invalid_no_action_or_boundary_proofs(self):
        previous = decision()
        changes = {
            "positive_dt": lambda p: p.update(dt=.001),
            "physical_advance": lambda p: p.update(physical_dt=.02),
            "submitted": lambda p: p.update(action_submitted=True),
            "new_command": lambda p: p.update(command={"command_id": 2}),
            "new_snapshot": lambda p: p.update(observation_digest="new"),
            "new_watermark": lambda p: p["watermarks"].update(state_sequence=2),
            "cross_epoch": lambda p: p.update(epoch="other"),
            "wrong_sequence": lambda p: p["reward_diagnostics"].update(sequence=9),
            "past_boundary": lambda p: p["reward_diagnostics"].update(step_start=80.999999999),
            "future_boundary": lambda p: p["reward_diagnostics"].update(effective_step_end=81.000000001),
            "new_coverage": lambda p: p["reward_diagnostics"]["reward_terms"].update(coverage=.1),
            "new_cells": lambda p: p["reward_diagnostics"].update(new_correct_free_cells=1),
            "bootstrap": lambda p: p.update(bootstrap=1),
            "truncated": lambda p: p["reward_diagnostics"].update(terminated=False, truncated=True),
        }
        for label, change in changes.items():
            with self.subTest(case=label):
                proof = settlement(previous)
                change(proof)
                with self.assertRaises(ValueError):
                    merge_zero_terminal(previous, -20., proof)

    def test_short_submitted_terminal_retains_actor_row_and_correct_return(self):
        first = decision(index=1, reward=1., value=.2, next_value=.4)
        final = decision(index=2, reward=10., value=.4, next_value=999.,
                         dt=.011, physical_dt=.02, terminated=True)
        buffer = build_rollout_buffer([[first, final]], OBSERVATIONS, ACTIONS,
                                      gamma=.9, gae_lambda=1.)
        self.assertEqual(buffer.buffer_size, 2)
        np.testing.assert_allclose(buffer.durations, [1., .011])
        np.testing.assert_allclose(buffer.returns[:, 0], [10., 10.], atol=1e-6)
        self.assertEqual(buffer.actions.shape, (2, 1, 1))

    def test_truncation_bootstraps_once_without_cross_episode_gae(self):
        truncated = decision(epoch="a", reward=1., value=.5, next_value=4., truncated=True)
        terminal = decision(epoch="b", reward=100., value=2., next_value=999., terminated=True)
        buffer = build_rollout_buffer([[truncated], [terminal]], OBSERVATIONS, ACTIONS,
                                      gamma=.5, gae_lambda=1.)
        np.testing.assert_allclose(buffer.returns[:, 0], [3., 100.])
        np.testing.assert_allclose(buffer.advantages[:, 0], [2.5, 98.])
        np.testing.assert_array_equal(buffer.episode_starts[:, 0], [1., 1.])

    def test_fixed_second_gae_matches_stock_maskable_buffer(self):
        rows = [decision(index=1, reward=1., value=.4, next_value=.7),
                decision(index=2, reward=-.2, value=.7, next_value=.9),
                decision(index=3, reward=2., value=.9, terminated=True)]
        ours = build_rollout_buffer([rows], OBSERVATIONS, ACTIONS, gamma=.93, gae_lambda=.87)
        stock = MaskableDictRolloutBuffer(3, OBSERVATIONS, ACTIONS, device="cpu",
                                          gamma=.93, gae_lambda=.87)
        for index, row in enumerate(rows):
            stock.add({key: value[np.newaxis] for key, value in row.observation.items()},
                      np.array([[row.action]]), np.array([row.reward]), np.array([index == 0]),
                      torch.tensor([row.value]), torch.tensor([row.log_prob]),
                      action_masks=row.action_mask[np.newaxis])
        stock.compute_returns_and_advantage(torch.tensor([999.]), np.array([True]))
        np.testing.assert_allclose(ours.advantages, stock.advantages, rtol=1e-6)
        np.testing.assert_allclose(ours.returns, stock.returns, rtol=1e-6)

    def test_exact_buffer_replays_every_saved_mask_in_sb3_batches(self):
        rows = [decision(index=1, next_value=.2, mask=[1, 0, 0, 0]),
                decision(index=2, value=.2, next_value=.3, mask=[1, 1, 0, 0]),
                decision(index=3, value=.3, terminated=True, mask=[1, 0, 1, 1])]
        buffer = build_rollout_buffer([rows], OBSERVATIONS, ACTIONS)
        self.assertIsInstance(buffer, MaskableDictRolloutBuffer)
        self.assertTrue(buffer.full)
        self.assertEqual(buffer.size(), 3)
        seen = 0
        for batch in buffer.get(2):
            seen += len(batch.actions)
            np.testing.assert_array_equal(batch.action_masks.numpy(),
                                          batch.observations["action_mask"].numpy())
            np.testing.assert_allclose(batch.old_log_prob.numpy(), -.7)
        self.assertEqual(seen, 3)
        self.assertEqual(sum(len(batch.actions) for batch in buffer.get(2)), 3)

    def test_final_singleton_is_merged_with_previous_minibatch(self):
        rows = [decision(index=index + 1, terminated=index == 6) for index in range(7)]
        buffer = build_rollout_buffer([rows], OBSERVATIONS, ACTIONS)
        self.assertEqual([len(batch.actions) for batch in buffer.get(3)], [3, 4])
        self.assertEqual([len(batch.actions) for batch in buffer.get(2)], [2, 2, 3])
        with self.assertRaisesRegex(ValueError, "two decisions"):
            list(buffer.get(1))

    def test_single_decision_episode_has_targets_but_cannot_normalize_minibatch(self):
        buffer = build_rollout_buffer([[decision(terminated=True)]], OBSERVATIONS, ACTIONS)
        self.assertEqual(buffer.buffer_size, 1)
        with self.assertRaisesRegex(ValueError, "two decisions"):
            list(buffer.get(64))

    def test_adjacency_and_duplicate_episode_proofs_are_required(self):
        first, final = decision(index=1), decision(index=2, terminated=True)
        for field, value in (("step_start", 80.), ("effective_step_end", 82.000000001),
                             ("sequence", 7), ("epoch", "other")):
            with self.subTest(field=field):
                info = copy.deepcopy(final.info)
                info["reward_diagnostics"][field] = value
                with self.assertRaises(ValueError):
                    build_rollout_buffer([[first, replace(final, info=info)]],
                                         OBSERVATIONS, ACTIONS)
        with self.assertRaisesRegex(ValueError, "twice"):
            build_rollout_buffer([[replace(first, terminated=True)], [replace(first, terminated=True)]],
                                 OBSERVATIONS, ACTIONS)

    def test_incomplete_cross_epoch_or_inconsistent_value_rollouts_are_rejected(self):
        invalid = (
            [], [[]], [[decision()]],
            [[decision(terminated=True), decision(terminated=True)]],
            [[decision(next_value=2.), decision(index=2, value=1., terminated=True)]],
            [[decision(), decision(index=2, epoch="b", terminated=True)]],
        )
        for episodes in invalid:
            with self.subTest(episodes=episodes), self.assertRaises(ValueError):
                build_rollout_buffer(episodes, OBSERVATIONS, ACTIONS)


if __name__ == "__main__":
    unittest.main()
