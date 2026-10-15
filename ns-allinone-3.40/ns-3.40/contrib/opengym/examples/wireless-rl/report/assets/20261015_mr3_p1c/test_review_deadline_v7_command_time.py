"""Pure counterexamples for the scoped deadline review; no native execution."""

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "deadline_review", Path(__file__).with_name("review_deadline_v7_command_time.py"))
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)
TIME = REVIEW.load_time_helper()
AUDIT, _ = TIME.load_auditor()
EPOCH = "synthetic-only"


def fixture():
    start = 81_420_000_000
    reset = {"kind": "reset", "snapshot": {"epoch": EPOCH, "sequence": 1,
             "digest": "s1", "source_stamp": start / 1e9},
             "info": {"epoch": EPOCH, "reward_diagnostics": {"sequence": 0,
                      "reward": 0., "initial_correct_free_cells": 1987}}}
    transitions, events = [reset], []
    for sequence in range(1, 301):
        begin, end = start + (sequence - 1) * 10**9, start + sequence * 10**9
        command = {"epoch": EPOCH, "command_id": sequence, "action": 888,
                   "observation_sequence": sequence, "observation_digest": f"s{sequence}",
                   "created_at": begin / 1e9, "expires_at": (begin + 2_000_000_000) / 1e9}
        terminal = sequence == 300
        terms = {"invalid": 0., "coverage": 0., "failure": -20. if terminal else 0.,
                 "time": -1. / 300.}
        reward = {"epoch": EPOCH, "sequence": sequence, "step_start": begin / 1e9,
                  "effective_step_end": end / 1e9, "requested_step_end": end / 1e9,
                  "delta_sim_time": 1., "terminated": terminal, "truncated": False,
                  "reason": "timeout" if terminal else None, "rejected_actions_delta": 0,
                  "new_correct_free_cells": 0, "rewarded_correct_free_cells": 0,
                  "initial_correct_free_cells": 1987, "reward_terms": terms,
                  "reward_weights": {"failure": 20.}, "remaining_sim_time": 300. - sequence,
                  "elapsed_sim_time": float(sequence)}
        transitions.append({"kind": "step", "terminated": terminal, "truncated": False,
                            "reward": sum(terms.values()),
                            "snapshot": {"epoch": EPOCH, "sequence": sequence + 1,
                                         "digest": f"s{sequence + 1}", "source_stamp": end / 1e9},
                            "info": {"command": command, "dt": 1., "physical_dt": 1.,
                                     "reward_diagnostics": reward}})
        events.append({"epoch": EPOCH, "stamp": begin / 1e9, "kind": "action",
                       "payload": {"command_id": sequence, "observation_sequence": sequence,
                                   "action": 888, "choices": [8, 8, 8],
                                   "observation_digest": f"s{sequence}",
                                   "results": {robot: "kept" for robot in AUDIT.ROBOTS}}})
    return transitions, events


class DeadlineReviewTests(unittest.TestCase):
    def test_valid_fixture_discovers_actual_float_boundary_shape(self):
        result = REVIEW.review_rows(TIME, AUDIT, *fixture(), EPOCH)
        self.assertEqual([row["command_id"] for row in
                          result["correctly_accepted_float_boundary_witnesses"]], [174, 175])
        self.assertEqual(result["failure_penalty_sequences"], [300])
        self.assertEqual(result["elapsed_ns"], 300_000_000_000)

    def test_invalid_penalty_cannot_be_hidden_by_an_accepted_receipt(self):
        transitions, events = fixture()
        transitions[174]["info"]["reward_diagnostics"]["reward_terms"]["invalid"] = -.05
        with self.assertRaisesRegex(ValueError, "rejection penalty"):
            REVIEW.review_rows(TIME, AUDIT, transitions, events, EPOCH)

    def test_real_one_ns_excess_ttl_cannot_pass(self):
        transitions, events = fixture()
        transitions[174]["info"]["command"]["expires_at"] = 256.420000001
        with self.assertRaisesRegex(ValueError, "legal and accepted"):
            REVIEW.review_rows(TIME, AUDIT, transitions, events, EPOCH)

    def test_task_timeout_cannot_be_relabelled_external_truncation(self):
        transitions, events = fixture()
        transitions[-1]["truncated"] = True
        with self.assertRaisesRegex(ValueError, "terminal classification"):
            REVIEW.review_rows(TIME, AUDIT, transitions, events, EPOCH)

    def test_failure_must_be_paid_once_only(self):
        transitions, events = fixture()
        transitions[2]["info"]["reward_diagnostics"]["reward_terms"]["failure"] = -20.
        with self.assertRaisesRegex(ValueError, "failure term only once"):
            REVIEW.review_rows(TIME, AUDIT, transitions, events, EPOCH)

    def test_hidden_goal_send_is_rejected(self):
        transitions, events = fixture()
        events.append({"kind": "protocol", "payload": {"type": "send_goal"}})
        with self.assertRaisesRegex(ValueError, "unexpectedly sent"):
            REVIEW.review_rows(TIME, AUDIT, transitions, events, EPOCH)


if __name__ == "__main__":
    unittest.main()
