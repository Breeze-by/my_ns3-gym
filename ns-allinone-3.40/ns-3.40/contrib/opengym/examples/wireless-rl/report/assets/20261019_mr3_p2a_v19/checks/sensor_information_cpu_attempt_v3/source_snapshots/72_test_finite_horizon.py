"""Finite-task objective counterexamples on tiny real rollout-buffer tensors.

These CPU mathematical fixtures use two legal actions and one scalar state.
They exercise the production DecisionTransition/buffer without allocating
hundreds of MR3 maps, importing ROS, or running a policy/simulator experiment.
"""

import copy
import unittest

from gymnasium import spaces
import numpy as np

from mr3_learning.ppo import GAMMA_PER_SECOND, GAE_LAMBDA_PER_SECOND
from mr3_learning.rollout import (
    DecisionTransition, build_rollout_buffer, merge_zero_terminal,
)


OBSERVATIONS = spaces.Dict({
    "state": spaces.Box(-np.inf, np.inf, shape=(1,), dtype=np.float32),
    "action_mask": spaces.MultiBinary(2),
})
ACTIONS = spaces.Discrete(2)


def episode(rewards, *, epoch="finite-task", values=None, durations=None,
            ending="terminated", tail_value=0.):
    """Create a contiguous scalar-reward episode with consistent next values."""
    values = [0.] * len(rewards) if values is None else list(values)
    durations = [1.] * len(rewards) if durations is None else list(durations)
    rows, start_ns = [], 10_000_000_000
    for index, (reward, value, dt) in enumerate(zip(rewards, values, durations)):
        last = index == len(rewards) - 1
        end_ns = start_ns + round(dt * 10**9)
        info = {
            "epoch": epoch, "dt": dt,
            "physical_dt": .02 if last and dt < .02 else dt,
            "action_submitted": True, "observation_sequence": index + 2,
            "observation_digest": f"snapshot-{index + 2}",
            "candidate_version": f"candidates-{index + 2}",
            "watermarks": {"state_sequence": index + 2},
            "reward_diagnostics": {
                "epoch": epoch, "sequence": index + 1,
                "step_start": start_ns / 1e9, "effective_step_end": end_ns / 1e9,
            },
        }
        rows.append(DecisionTransition(
            observation={"state": np.array([index], dtype=np.float32),
                         "action_mask": np.array([1, 1], dtype=np.int8)},
            action=index % 2, reward=reward, value=value, log_prob=-.6931471805599453,
            next_value=values[index + 1] if not last else tail_value,
            dt=dt, terminated=last and ending == "terminated",
            truncated=last and ending == "truncated", info=info,
        ))
        start_ns = end_ns
    return rows


def active_buffer(episodes):
    return build_rollout_buffer(
        episodes, OBSERVATIONS, ACTIONS, gamma=GAMMA_PER_SECOND,
        gae_lambda=GAE_LAMBDA_PER_SECOND, device="cpu")


def late_failure_info(previous):
    end = previous.info["reward_diagnostics"]["effective_step_end"]
    return {
        **{key: copy.deepcopy(previous.info[key]) for key in (
            "epoch", "watermarks", "observation_sequence", "observation_digest",
            "candidate_version")},
        "dt": 0., "physical_dt": 0., "action_submitted": False,
        "terminal_observation_reused": True, "command": None, "requested_action": 1,
        "bootstrap": 0, "reason": "navigation_failure",
        "reward_diagnostics": {
            "epoch": previous.info["epoch"],
            "sequence": previous.info["reward_diagnostics"]["sequence"] + 1,
            "terminated": True, "truncated": False, "reward": -20.,
            "delta_sim_time": 0., "new_correct_free_cells": 0,
            "reward_terms": {"coverage": 0., "failure": -20.},
            "map_pairing_scope": "terminal_evaluator_frozen_before_drain",
            "reason": "navigation_failure", "step_start": end,
            "effective_step_end": end, "requested_step_end": end,
        },
    }


class FiniteHorizonTests(unittest.TestCase):
    def test_active_coefficients_select_full_finite_episode_credit(self):
        self.assertEqual(GAMMA_PER_SECOND, 1.)
        self.assertEqual(GAE_LAMBDA_PER_SECOND, 1.)
        buffer = active_buffer([episode([1., -20.])])
        self.assertEqual(buffer.gamma, 1.)
        self.assertEqual(buffer.gae_lambda, 1.)
        np.testing.assert_allclose(buffer.returns[:, 0], [-19., -20.], atol=1e-6)

    def test_old_discounted_failure_can_be_positive_but_active_mc_return_is_negative(self):
        rewards = [8. - 1 / 300] + [-1 / 300] * 298 + [-20. - 1 / 300]
        # Analytic exact discounted values: the time-cost geometric series and
        # the final failure penalty. With exact V, lambda cannot fix the wrong
        # positive discounted objective: all nonterminal TD residuals are zero.
        values = [-(1 - .99 ** (300 - index)) / 3
                  - 20 * .99 ** (299 - index) + (8. if index == 0 else 0.)
                  for index in range(300)]
        rows = episode(rewards, values=values)
        legacy = build_rollout_buffer(
            [rows], OBSERVATIONS, ACTIONS, gamma=.99, gae_lambda=.95, device="cpu")
        active = active_buffer([rows])
        self.assertAlmostEqual(float(legacy.returns[0, 0]), 6.6922884986038484, places=5)
        self.assertGreater(legacy.returns[0, 0], 0.)
        self.assertAlmostEqual(float(active.returns[0, 0]), -13., places=5)
        self.assertTrue(np.all(active.returns[:, 0] <= -10. + 1e-5))

    def test_maximum_first_correct_coverage_still_cannot_pay_for_terminal_failure(self):
        rewards = [10. - 1 / 300] + [-1 / 300] * 298 + [-20. - 1 / 300]
        buffer = active_buffer([episode(rewards)])
        self.assertAlmostEqual(float(buffer.returns[0, 0]), -11., places=5)
        self.assertTrue(np.all(buffer.returns[:, 0] <= -10. + 1e-5))

    def test_full_terminal_credit_propagates_without_old_trace_attenuation(self):
        rows = episode([0.] * 299 + [-20.])
        legacy = build_rollout_buffer(
            [rows], OBSERVATIONS, ACTIONS, gamma=.99, gae_lambda=.95, device="cpu")
        active = active_buffer([rows])
        # This is the old zero-baseline GAE target, distinct from the discounted
        # return in the previous test: both gamma and lambda attenuate this tail.
        self.assertAlmostEqual(float(legacy.returns[0, 0]), -2.1642686154955804e-7,
                               delta=1e-12)
        np.testing.assert_allclose(active.returns[:, 0], [-20.] * 300, atol=1e-6)

    def test_consistent_arbitrary_critic_estimates_telescope_out_of_closed_targets(self):
        rewards = [8., -1., -20.]
        zero = active_buffer([episode(rewards, values=[0., 0., 0.])])
        varied = active_buffer([episode(rewards, values=[123., -50., 7.])])
        np.testing.assert_allclose(zero.returns[:, 0], [-13., -21., -20.], atol=1e-6)
        np.testing.assert_allclose(varied.returns, zero.returns, atol=1e-6)

    def test_short_and_zero_effective_submitted_terminal_remain_actor_decisions(self):
        for dt, expected in ((.011, -18.00337), (0., -18.003333333333334)):
            with self.subTest(terminal_dt=dt):
                rows = episode([2. - 1 / 300, -20. - dt / 300],
                               values=[13., -7.], durations=[1., dt])
                buffer = active_buffer([rows])
                self.assertEqual(buffer.buffer_size, 2)
                self.assertEqual(rows[-1].info["physical_dt"], .02)
                self.assertTrue(rows[-1].info["action_submitted"])
                np.testing.assert_array_equal(buffer.durations, [1., dt])
                self.assertAlmostEqual(float(buffer.returns[0, 0]), expected, places=5)
                self.assertAlmostEqual(float(buffer.returns[1, 0]), -20. - dt / 300,
                                       places=5)

    def test_same_boundary_no_action_failure_settles_previous_decision_without_extra_sample(self):
        pending = episode([8. - 1 / 300, -1 / 300],
                          values=[9., 4.], ending="open", tail_value=30.)
        settled = pending[:-1] + [merge_zero_terminal(
            pending[-1], -20., late_failure_info(pending[-1]))]
        equivalent = episode([8. - 1 / 300, -20. - 1 / 300], values=[9., 4.])
        merged, direct = active_buffer([settled]), active_buffer([equivalent])
        self.assertEqual(merged.buffer_size, 2)
        self.assertTrue(settled[-1].info["merged_zero_terminal"])
        self.assertEqual(settled[-1].next_value, 0.)
        np.testing.assert_array_equal(merged.durations, [1., 1.])
        np.testing.assert_allclose(merged.returns, direct.returns, atol=1e-6)
        self.assertAlmostEqual(float(merged.returns[0, 0]), -12.006666666666666, places=5)

    def test_ten_extra_seconds_idle_before_same_failure_reduce_return_by_time_cost(self):
        short = active_buffer([episode([8. - 1 / 300, -20. - 1 / 300])])
        longer = active_buffer([episode(
            [8. - 1 / 300] + [-1 / 300] * 10 + [-20. - 1 / 300])])
        self.assertAlmostEqual(float(short.returns[0, 0]), -12.006666666666666, places=5)
        self.assertAlmostEqual(float(longer.returns[0, 0]), -12.04, places=5)
        self.assertAlmostEqual(float(longer.returns[0, 0] - short.returns[0, 0]),
                               -.03333333333333333, places=5)

    def test_external_truncation_preserves_value_bootstrap_and_has_no_failure_bound(self):
        rows = episode([2., 3.], values=[-7., 9.], ending="truncated", tail_value=100.)
        buffer = active_buffer([rows])
        np.testing.assert_allclose(buffer.returns[:, 0], [105., 103.], atol=1e-6)
        self.assertTrue(buffer.truncated[-1])
        self.assertFalse(buffer.terminated[-1])
        self.assertEqual(buffer.next_values[-1], 100.)
        self.assertGreater(buffer.returns[0, 0], -10.)

    def test_closed_episode_boundaries_do_not_leak_returns_in_either_order(self):
        failure = episode([1., -20.], epoch="failed", values=[4., 9.])
        truncated = episode([50., 10.], epoch="cut", values=[-13., 17.],
                            ending="truncated", tail_value=100.)
        forward = active_buffer([failure, truncated])
        reverse = active_buffer([truncated, failure])
        np.testing.assert_allclose(forward.returns[:, 0], [-19., -20., 160., 110.], atol=1e-6)
        np.testing.assert_allclose(reverse.returns[:, 0], [160., 110., -19., -20.], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
