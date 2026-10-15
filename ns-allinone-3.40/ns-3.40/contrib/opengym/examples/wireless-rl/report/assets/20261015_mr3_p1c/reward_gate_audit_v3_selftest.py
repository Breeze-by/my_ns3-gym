"""Pure scalar audit regressions; no simulator, ROS, map, or truth imports."""

import copy
import unittest

from reward_gate_audit_v3 import (
    causal_reject_deltas, ns, reject_reward_valid, reused_terminal_valid,
    zero_terminal_coverage_valid,
)


def fixture():
    snapshot = {"epoch": "epoch", "sequence": 5, "source_stamp": 212.06, "digest": "same"}
    reward = {"epoch": "epoch", "sequence": 4, "step_start": 212.06,
              "effective_step_end": 212.06, "requested_step_end": 212.06,
              "delta_sim_time": 0., "reward": -20., "reason": "navigation_failure",
              "terminated": True, "truncated": False, "new_correct_free_cells": 0,
              "reward_terms": {"coverage": 0., "failure": -20.}}
    info = {"terminal_observation_reused": True, "action_submitted": False, "command": None,
            "requested_action": 888, "bootstrap": 0, "dt": 0., "physical_dt": 0.,
            "reason": "navigation_failure", "reward_diagnostics": reward}
    row = {"snapshot": copy.deepcopy(snapshot), "terminated": True, "truncated": False,
           "reward": -20., "info": info}
    return row, snapshot


class ReusedTerminalTests(unittest.TestCase):
    def test_same_boundary_scalar_terminal_is_allowed_without_new_action_or_tick(self):
        row, snapshot = fixture()
        self.assertTrue(reused_terminal_valid(row, snapshot, "epoch", 4))

    def test_every_narrow_proof_is_required(self):
        changes = (
            (("terminated",), False), (("truncated",), True), (("reward",), -19.),
            (("snapshot", "sequence"), 6), (("snapshot", "digest"), "modified"),
            (("info", "terminal_observation_reused"), False),
            (("info", "action_submitted"), True), (("info", "command"), {}),
            (("info", "requested_action"), True), (("info", "requested_action"), 1000),
            (("info", "bootstrap"), 1), (("info", "bootstrap"), False),
            (("info", "dt"), .02), (("info", "dt"), False),
            (("info", "physical_dt"), .02), (("info", "physical_dt"), False),
            (("info", "reason"), "timeout"),
            (("info", "reward_diagnostics", "epoch"), "other"),
            (("info", "reward_diagnostics", "sequence"), 3),
            (("info", "reward_diagnostics", "terminated"), False),
            (("info", "reward_diagnostics", "truncated"), True),
            (("info", "reward_diagnostics", "reward"), -19.),
            (("info", "reward_diagnostics", "delta_sim_time"), .02),
            (("info", "reward_diagnostics", "delta_sim_time"), False),
            (("info", "reward_diagnostics", "step_start"), 212.060000001),
            (("info", "reward_diagnostics", "effective_step_end"), 212.060000001),
            (("info", "reward_diagnostics", "requested_step_end"), 212.060000001),
            (("info", "reward_diagnostics", "new_correct_free_cells"), 1),
            (("info", "reward_diagnostics", "new_correct_free_cells"), False),
            (("info", "reward_diagnostics", "new_correct_free_cells"), 0.),
            (("info", "reward_diagnostics", "reward_terms", "coverage"), .1),
            (("info", "reward_diagnostics", "reward_terms", "coverage"), False),
            (("info", "reward_diagnostics", "reward_terms"), None),
        )
        for path, value in changes:
            with self.subTest(path=path, value=value):
                row, snapshot = fixture()
                target = row
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.assertFalse(reused_terminal_valid(row, snapshot, "epoch", 4))

    def test_nanosecond_deadline_does_not_inherit_float_subtraction_error(self):
        self.assertLess(512.06 - 212.06, 300.)
        self.assertEqual(ns(512.06) - ns(212.06), 300000000000)

    def test_invalid_time_never_becomes_zero(self):
        for value in (None, False, -1., float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ns(value)

    def test_zero_terminal_coverage_rule_requires_explicit_typed_zero_fields(self):
        valid = {"new_correct_free_cells": 0, "reward_terms": {"coverage": 0.}}
        self.assertTrue(zero_terminal_coverage_valid(valid))
        self.assertFalse(zero_terminal_coverage_valid({}))
        self.assertFalse(zero_terminal_coverage_valid({"new_correct_free_cells": 0}))
        self.assertFalse(zero_terminal_coverage_valid({"reward_terms": {"coverage": 0.}}))
        self.assertFalse(zero_terminal_coverage_valid({
            "new_correct_free_cells": 0, "reward_terms": {},
        }))


def action_step(command_id, observation, start, end):
    return {"info": {"command": {"command_id": command_id,
                                 "observation_sequence": observation,
                                 "created_at": start},
                     "reward_diagnostics": {"effective_step_end": end}}}


def rejected(command_id, observation, stamp):
    return {"kind": "action_rejected", "stamp": stamp,
            "payload": {"command_id": command_id, "observation_sequence": observation}}


class CausalRejectionTests(unittest.TestCase):
    def test_next_command_at_previous_end_is_penalized_only_in_its_own_step(self):
        steps = [action_step(4, 4, 83.92, 84.92), action_step(5, 5, 84.92, 85.92)]
        deltas, bindings = causal_reject_deltas(steps, [rejected(5, 5, 84.92)])
        self.assertEqual(deltas, [0, 1])
        self.assertEqual(bindings, [{"step_sequence": 2, "command_id": 5,
                                    "observation_sequence": 5, "stamp": 84.92}])

    def test_earlier_command_at_its_actual_end_is_not_arbitrarily_delayed(self):
        steps = [action_step(4, 4, 83.92, 84.92), action_step(5, 5, 84.92, 85.92)]
        deltas, _ = causal_reject_deltas(steps, [rejected(4, 4, 84.92)])
        self.assertEqual(deltas, [1, 0])

    def test_each_rejection_requires_identity_observation_and_its_own_watermark(self):
        steps = [action_step(4, 4, 83.92, 84.92), action_step(5, 5, 84.92, 85.92)]
        cases = ([rejected(6, 5, 84.92)], [rejected(True, 5, 84.92)],
                 [rejected(5, 4, 84.92)], [rejected(5, True, 84.92)],
                 [rejected(5, 5, 84.919999999)], [rejected(5, 5, 85.920000001)],
                 [rejected(5, 5, 84.92), rejected(5, 5, 84.92)])
        for events in cases:
            with self.subTest(events=events), self.assertRaises(ValueError):
                causal_reject_deltas(steps, events)
        with self.assertRaises(ValueError):
            causal_reject_deltas([steps[0], steps[0]], [])

    def test_no_submitted_action_means_no_invented_rejection_for_reused_terminal(self):
        steps = [action_step(4, 4, 83.92, 84.92),
                 {"info": {"action_submitted": False, "command": None}}]
        self.assertEqual(causal_reject_deltas(steps, [rejected(4, 4, 84.92)])[0], [1, 0])
        with self.assertRaises(ValueError):
            causal_reject_deltas(steps, [rejected(5, 5, 84.92)])

    def test_count_and_penalty_are_both_checked_per_transition(self):
        reward = {"rejected_actions_delta": 1, "reward_terms": {"invalid": -.05},
                  "reward_weights": {"invalid": .05}}
        self.assertTrue(reject_reward_valid(reward, 1))
        self.assertFalse(reject_reward_valid(reward, 0))
        for key, value in (("rejected_actions_delta", True),
                           ("rejected_actions_delta", 0), ("rejected_actions_delta", 1.)):
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(reward)
                changed[key] = value
                self.assertFalse(reject_reward_valid(changed, 1))
        for value in (0., -.049, False, float("nan")):
            with self.subTest(invalid_term=value):
                changed = copy.deepcopy(reward)
                changed["reward_terms"]["invalid"] = value
                self.assertFalse(reject_reward_valid(changed, 1))


if __name__ == "__main__":
    unittest.main()
