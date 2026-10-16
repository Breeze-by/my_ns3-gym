"""Command-bound switch audit counterexamples; no ROS, model or simulator."""

import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from mr3_learning import audit_scalar


EPOCH = "test-episode"
OLD_ERRORS = [f"step {step}: switch penalty differs from actual protocol events"
              for step in (1, 2)]


def fixture():
    def snapshot(sequence):
        return {
            "epoch": EPOCH, "sequence": sequence, "digest": f"snapshot-{sequence}",
            "candidate_version": f"candidates-{sequence}",
            "source_stamp": 9. + sequence, "joint_action_mask": [True] * 1000,
            "robots": [{"name": name, "navigation": {
                "phase": "active" if index < 2 else "idle", "owned": index < 2,
                "goal_id": f"{EPOCH}:{name}:0" if index < 2 else None}}
                for index, name in enumerate(audit_scalar.ROBOTS)],
        }

    rows = [{"kind": "reset", "snapshot": snapshot(1)}]
    events = []
    for sequence, action in ((1, 888), (2, 18)):
        source = rows[-1]["snapshot"]
        command = {"epoch": EPOCH, "command_id": sequence, "action": action,
                   "created_at": 9. + sequence, "observation_sequence": sequence,
                   "observation_digest": source["digest"]}
        count = 0 if sequence == 1 else 2
        rows.append({"kind": "step", "snapshot": snapshot(sequence + 1),
                     "terminated": False, "truncated": sequence == 2,
                     "info": {"command": command, "reward_diagnostics": {
                         "epoch": EPOCH, "sequence": sequence, "step_start": 9. + sequence,
                         "effective_step_end": 10. + sequence, "goal_switches_delta": count,
                         "reward_weights": {"switch": .01},
                         "reward_terms": {"switch": -.01 * count}}}})
        results = {name: "kept" if sequence == 1 or index == 2 else "switch_pending"
                   for index, name in enumerate(audit_scalar.ROBOTS)}
        events.append({"epoch": EPOCH, "kind": "action", "stamp": 9. + sequence,
                       "payload": {"command_id": sequence, "action": action,
                                   "choices": [action // 100, action // 10 % 10, action % 10],
                                   "observation_sequence": sequence,
                                   "candidate_version": source["candidate_version"],
                                   "observation_digest": source["digest"], "results": results}})
    for name in ("tb1", "tb2"):
        events.append({"epoch": EPOCH, "kind": "protocol", "stamp": 11., "payload": {
            "epoch": EPOCH, "type": "cancel_goal", "robot": name,
            "goal_id": f"{EPOCH}:{name}:0", "reason": "switch", "stamp": 11.}})
    return rows, events


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class ScalarAuditTests(unittest.TestCase):
    def run_wrapper(self, transitions, events, original_errors=OLD_ERRORS):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)
            write_rows(path / "transitions.jsonl", transitions)
            write_rows(path / "adapter.jsonl", events)
            original = SimpleNamespace(audit_episode=lambda *unused: {
                "epoch": EPOCH, "errors": list(original_errors), "untouched_gate": "preserved"})
            return audit_scalar.audit_episode(path, "a" * 40, original=original)

    def test_future_command_at_shared_end_is_charged_to_its_actual_action_step(self):
        transitions, events = fixture()
        result = self.run_wrapper(transitions, events)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["causal_switch"]["deltas"], [0, 2])
        self.assertEqual(result["causal_switch"]["unique_actual_switches"], 2)
        self.assertEqual(result["original_errors"], OLD_ERRORS)
        self.assertEqual(len(result["replaced_original_assertions"]), 2)
        self.assertEqual(result["untouched_gate"], "preserved")
        self.assertEqual([x["command_id"] for x in result["causal_switch"]["bindings"]], [2, 2])

    def test_old_inclusive_wrong_reward_pattern_cannot_be_hidden_by_correction(self):
        transitions, events = fixture()
        for row, count in zip(transitions[1:], (2, 0)):
            reward = row["info"]["reward_diagnostics"]
            reward["goal_switches_delta"] = count
            reward["reward_terms"]["switch"] = -.01 * count
        # The original timestamp-only switch assertion would accept [2, 0].
        result = self.run_wrapper(transitions, events, original_errors=[])
        self.assertFalse(result["passed"])
        self.assertIn("causal switch count", result["errors"][0])
        self.assertEqual(result["replaced_original_assertions"], [])

    def test_right_counts_still_require_frozen_weight_and_actual_penalty(self):
        for field, value in (("weight", .1), ("penalty", 0.), ("penalty", float("inf")),
                             ("count", True), ("count", -1)):
            with self.subTest(field=field, value=value):
                transitions, events = fixture()
                reward = transitions[2]["info"]["reward_diagnostics"]
                if field == "weight":
                    reward["reward_weights"]["switch"] = value
                    reward["reward_terms"]["switch"] = -.2
                elif field == "penalty":
                    reward["reward_terms"]["switch"] = value
                else:
                    reward["goal_switches_delta"] = value
                result = self.run_wrapper(transitions, events)
                self.assertFalse(result["passed"])
                self.assertEqual(result["original_errors"], OLD_ERRORS)
                self.assertEqual(result["replaced_original_assertions"], [])

    def test_duplicate_unbound_missing_and_late_cancellation_are_failures(self):
        for variant in ("duplicate", "unbound", "missing", "late", "before_action", "malformed"):
            with self.subTest(variant=variant):
                transitions, events = fixture()
                if variant == "duplicate":
                    events.append(copy.deepcopy(events[-1]))
                elif variant == "unbound":
                    events[-1]["payload"]["goal_id"] = EPOCH + ":tb2:unknown"
                elif variant == "missing":
                    events.pop()
                elif variant == "late":
                    events[-1]["stamp"] = events[-1]["payload"]["stamp"] = 11.02
                elif variant == "malformed":
                    events[-1]["payload"] = None
                else:
                    events.insert(1, events.pop())
                result = self.run_wrapper(transitions, events)
                self.assertFalse(result["passed"], variant)
                self.assertTrue(result["causal_switch_errors"])

    def test_command_source_mask_and_old_goal_ownership_are_mandatory(self):
        for variant in ("wrong_observation", "wrong_command", "masked", "not_goal",
                        "wrong_old_goal", "not_active", "wrong_step"):
            with self.subTest(variant=variant):
                transitions, events = fixture()
                if variant == "wrong_observation":
                    events[1]["payload"]["observation_sequence"] = 1
                elif variant == "wrong_command":
                    events[1]["payload"]["command_id"] = 99
                elif variant == "masked":
                    transitions[1]["snapshot"]["joint_action_mask"][18] = False
                elif variant == "not_goal":
                    command = transitions[2]["info"]["command"]
                    command["action"] = 888
                    events[1]["payload"].update(action=888, choices=[8, 8, 8])
                elif variant == "wrong_old_goal":
                    transitions[1]["snapshot"]["robots"][0]["navigation"]["goal_id"] += "other"
                elif variant == "not_active":
                    transitions[1]["snapshot"]["robots"][0]["navigation"]["phase"] = "idle"
                else:
                    events[1]["stamp"] = 12.
                result = self.run_wrapper(transitions, events)
                self.assertFalse(result["passed"], variant)

    def test_replacement_send_or_acceptance_is_not_the_counting_point(self):
        transitions, events = fixture()
        events.append({"epoch": EPOCH, "kind": "native_send", "stamp": 11.2,
                       "payload": {"command_id": 2, "robot": "tb1"}})
        result = self.run_wrapper(transitions, events)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["causal_switch"]["deltas"], [0, 2])

    def test_other_original_errors_are_retained_verbatim(self):
        transitions, events = fixture()
        other = ["step 1: coverage scale", "collision raw sequence gap",
                 "step 1: switch penalty differs from actual protocol events extra"]
        result = self.run_wrapper(transitions, events, OLD_ERRORS + other)
        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], other)

    def test_unexplained_original_switch_error_is_never_removed(self):
        transitions, events = fixture()
        events = events[:1]
        transitions = transitions[:2]
        original = [OLD_ERRORS[0]]
        result = self.run_wrapper(transitions, events, original)
        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], original)
        self.assertEqual(result["replaced_original_assertions"], [])

    def test_original_helper_is_unchanged_and_explicitly_hash_pinned(self):
        original = audit_scalar.load_original()
        self.assertEqual(original.__file__.split("/")[-1], "reward_gate_audit_v3.py")
        self.assertEqual(audit_scalar.ORIGINAL_SCALAR_SHA256,
                         "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665")


if __name__ == "__main__":
    unittest.main()
