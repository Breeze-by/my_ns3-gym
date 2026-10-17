import copy
import unittest

import numpy as np

from mr3_learning.env import MR3Env
from mr3_learning.tests.test_observation import fixture, seal


class SupervisorFixture:
    def __init__(self):
        self.calls = []
        self.closed = 0
        self.snapshot = None
        self.terminal = False
        self.error = False
        self.step_delta = 1.0
        self.effective_dt = None

    def payload(self, truncated=False):
        return {"snapshot": copy.deepcopy(self.snapshot), "reward": 0.0,
                "terminated": self.terminal, "truncated": truncated and not self.terminal,
                "info": {"dt": self.step_delta if self.effective_dt is None else self.effective_dt,
                         "physical_dt": self.step_delta, "reward_terms": {"time": -1.0},
                         "watermarks": {"state_sequence": self.snapshot["sequence"],
                                        "map_payload_sha256": "a" * 64}}}

    def reset(self, scene, seed):
        self.calls.append(("reset", scene, seed))
        self.snapshot = fixture()
        epoch = f"supervisor-fixture-episode-{len(self.calls)}"
        self.snapshot["epoch"] = epoch
        for robot in self.snapshot["robots"]:
            robot["epoch"] = epoch
            robot["activity"]["epoch"] = epoch
        for metadata in self.snapshot["path_maps"].values():
            metadata["epoch"] = epoch
        seal(self.snapshot)
        result = self.payload()
        result["info"]["dt"] = 0.0
        result["info"]["physical_dt"] = 0.0
        return result

    def step(self, action, external_truncation=None):
        self.calls.append(("step", action, external_truncation))
        if self.error:
            raise RuntimeError("owned worker crashed")
        self.snapshot["sequence"] += 1
        # This API-only fixture advances one second. Keep the received source
        # samples fixed, and update ages honestly instead of inventing delivery.

        def age_one_second(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("source_age_sec", "received_age_sec") and item is not None:
                        value[key] = item + self.step_delta
                    else:
                        age_one_second(item)
            elif isinstance(value, list):
                for item in value:
                    age_one_second(item)
        age_one_second(self.snapshot)
        self.snapshot["source_stamp"] += self.step_delta
        seal(self.snapshot)
        return self.payload(truncated=external_truncation is not None)

    def close(self):
        self.closed += 1


class EnvironmentTests(unittest.TestCase):
    @staticmethod
    def late_terminal(env):
        stamp = env._snapshot["source_stamp"]
        return {"snapshot": copy.deepcopy(env._snapshot), "reward": -20.,
                "terminated": True, "truncated": False,
                "info": {"epoch": env._epoch, "terminal_observation_reused": True,
                         "action_submitted": False, "requested_action": 888, "command": None,
                         "dt": 0., "physical_dt": 0., "reason": "navigation_failure",
                         "watermarks": copy.deepcopy(env._watermarks),
                         "reward_diagnostics": {
                             "epoch": env._epoch, "sequence": env._steps + 1,
                             "reward": -20., "terminated": True, "truncated": False,
                             "reason": "navigation_failure", "step_start": stamp,
                             "effective_step_end": stamp, "requested_step_end": stamp,
                             "delta_sim_time": 0.,
                             "new_correct_free_cells": 0,
                             "reward_terms": {"coverage": 0., "failure": -20.},
                             "map_pairing_scope": "terminal_evaluator_frozen_before_drain"}}}

    def test_late_terminal_reuses_exact_observation_without_submitting_action(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        env.reset(seed=101)
        before, *_ = env.step(888)
        payload = self.late_terminal(env)
        supervisor.step = lambda *args, **kwargs: payload
        after, reward, terminal, truncated, info = env.step(888)
        for key in before:
            np.testing.assert_array_equal(before[key], after[key])
        self.assertEqual(reward, -20.)
        self.assertTrue(terminal)
        self.assertFalse(truncated)
        self.assertFalse(info["action_submitted"])
        self.assertIsNone(info["command"])
        with self.assertRaises(RuntimeError):
            env.step(888)

    def test_zero_duration_exception_rejects_changed_snapshot_times_watermarks_or_action(self):
        changes = {
            "missing_flag": lambda p: p["info"].pop("terminal_observation_reused"),
            "new_action": lambda p: p["info"].update(action_submitted=True),
            "command": lambda p: p["info"].update(command={"action": 888}),
            "wrong_request": lambda p: p["info"].update(requested_action=889),
            "positive_dt": lambda p: p["info"].update(dt=.001),
            "positive_physics": lambda p: p["info"].update(physical_dt=.001),
            "not_terminal": lambda p: p.update(terminated=False),
            "truncated": lambda p: p.update(terminated=False, truncated=True),
            "wrong_epoch": lambda p: p["info"].update(epoch="other"),
            "new_delivery": lambda p: p["info"]["watermarks"].update(state_sequence=999),
            "old_end": lambda p: p["info"]["reward_diagnostics"].update(
                effective_step_end=p["snapshot"]["source_stamp"] - 1e-9),
            "new_reward_sequence": lambda p: p["info"]["reward_diagnostics"].update(sequence=99),
            "new_coverage": lambda p: p["info"]["reward_diagnostics"]["reward_terms"].update(
                coverage=1.),
            "new_correct_cells": lambda p: p["info"]["reward_diagnostics"].update(
                new_correct_free_cells=1),
            "changed_snapshot": lambda p: seal(p["snapshot"] | {"sequence": 99}),
        }
        for label, change in changes.items():
            with self.subTest(case=label):
                supervisor = SupervisorFixture()
                env = MR3Env(supervisor)
                env.reset(seed=101)
                env.step(888)
                payload = self.late_terminal(env)
                if label == "changed_snapshot":
                    payload["snapshot"]["sequence"] += 1
                    seal(payload["snapshot"])
                else:
                    change(payload)
                supervisor.step = lambda *args, **kwargs: payload
                with self.assertRaises(ValueError):
                    env.step(888)

    def test_reset_rebuilds_via_supervisor_and_preserves_seed_scene_and_spaces(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        first, info = env.reset(seed=101, options={"scene": "rooms"})
        self.assertEqual(supervisor.calls[-1], ("reset", "rooms", 101))
        self.assertTrue(env.observation_space.contains(first))
        self.assertEqual(info["seed"], 101)
        env.reset(seed=202)
        self.assertEqual(supervisor.calls[-1], ("reset", "open", 202))

    def test_action_mask_is_boolean_detached_and_step_preserves_joint_action(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        observation, _ = env.reset(seed=101)
        mask = env.action_masks()
        self.assertEqual(mask.dtype, bool)
        mask[:] = False
        self.assertTrue(env.action_masks().any())
        action = int(np.flatnonzero(observation["action_mask"])[0])
        following, reward, terminal, truncated, _ = env.step(action)
        self.assertEqual(supervisor.calls[-1], ("step", action, None))
        self.assertFalse(terminal or truncated)
        self.assertEqual(reward, 0)
        self.assertFalse(np.shares_memory(observation["robots"], following["robots"]))

    def test_external_sampler_limit_is_truncated_and_task_termination_has_priority(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor, max_steps=1)
        env.reset(seed=101)
        _, _, terminal, truncated, _ = env.step(888)
        self.assertEqual(supervisor.calls[-1], ("step", 888, "external_sampler_limit"))
        self.assertFalse(terminal)
        self.assertTrue(truncated)
        with self.assertRaises(RuntimeError):
            env.step(888)
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor, max_steps=1)
        env.reset(seed=101)
        supervisor.terminal = True
        _, _, terminal, truncated, _ = env.step(888)
        self.assertTrue(terminal)
        self.assertFalse(truncated)

    def test_infrastructure_exception_is_not_a_fabricated_transition(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        env.reset(seed=101)
        supervisor.error = True
        with self.assertRaisesRegex(RuntimeError, "crashed"):
            env.step(888)
        with self.assertRaisesRegex(RuntimeError, "reset"):
            env.step(888)

    def test_unknown_options_bad_actions_and_private_info_are_rejected(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        with self.assertRaises(ValueError):
            env.reset(options={"truth_map": True})
        env.reset(seed=101)
        for action in (True, -1, 1000, 1.5):
            with self.assertRaises(ValueError):
                env.step(action)
        supervisor.payload = lambda truncated=False: {
            "snapshot": seal(supervisor.snapshot), "reward": 0.0,
            "terminated": False, "truncated": False,
            "info": {"dt": 1.0, "physical_dt": 1.0,
                     "reward": {"correct_cell_indices": [2, 4]}},
        }
        with self.assertRaisesRegex(ValueError, "private"):
            env.step(888)

    def test_close_is_idempotent_and_steps_need_reset(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        with self.assertRaises(RuntimeError):
            env.step(888)
        env.close()
        env.close()
        self.assertEqual(supervisor.closed, 1)
        with self.assertRaises(RuntimeError):
            env.reset(seed=101)

    def test_reset_cannot_reuse_an_old_episode_epoch(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        env.reset(seed=101)
        stale = supervisor.payload()
        supervisor.reset = lambda **kwargs: stale
        with self.assertRaisesRegex(ValueError, "new episode epoch"):
            env.reset(seed=202)

    def test_nonterminal_variable_step_cannot_be_used_as_a_ppo_transition(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        env.reset(seed=101)
        supervisor.step_delta = 0.8
        with self.assertRaisesRegex(ValueError, "exactly one"):
            env.step(888)

    def test_terminal_short_step_retains_actual_reward_duration_within_one_quantum(self):
        supervisor = SupervisorFixture()
        env = MR3Env(supervisor)
        env.reset(seed=101)
        supervisor.terminal = True
        supervisor.step_delta = 0.02
        supervisor.effective_dt = 0.011
        _, _, terminal, truncated, info = env.step(888)
        self.assertTrue(terminal)
        self.assertFalse(truncated)
        self.assertEqual(info["dt"], 0.011)
        self.assertEqual(info["physical_dt"], 0.02)

    def test_terminal_reward_time_cannot_be_negative_or_hide_extra_physical_time(self):
        for physical_dt, effective_dt in ((0.02, -0.001), (0.04, 0.019), (0.02, 0.03)):
            supervisor = SupervisorFixture()
            env = MR3Env(supervisor)
            env.reset(seed=101)
            supervisor.terminal = True
            supervisor.step_delta = physical_dt
            supervisor.effective_dt = effective_dt
            with self.assertRaises(ValueError):
                env.step(888)


if __name__ == "__main__":
    unittest.main()
