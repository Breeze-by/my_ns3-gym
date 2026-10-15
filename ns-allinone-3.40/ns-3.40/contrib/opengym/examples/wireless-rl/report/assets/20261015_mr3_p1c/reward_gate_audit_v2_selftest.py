"""Pure scalar audit regressions; no simulator, ROS, map, or truth imports."""

import copy
import unittest

from reward_gate_audit_v2 import ns, reused_terminal_valid, zero_terminal_coverage_valid


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


if __name__ == "__main__":
    unittest.main()
