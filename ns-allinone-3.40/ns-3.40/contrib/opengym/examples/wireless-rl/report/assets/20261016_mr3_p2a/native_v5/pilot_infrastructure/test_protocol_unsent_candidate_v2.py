"""Offline mutation tests against the actual immutable W7 protocol function."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

from mr3_learning.audit_ppo import load_native_gates


HERE = Path(__file__).resolve().parent
ROOT = Path("/home/zhuyulab/ns3-workspace")
spec = importlib.util.spec_from_file_location(
    "protocol_unsent_candidate_v2", HERE / "protocol_unsent_candidate_v2.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class UnsentProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, auditor, _, _, cls.source_proof = load_native_gates(ROOT, candidate.FREEZE)
        cls.original = staticmethod(auditor.audit_protocol)
        cls.directory = HERE / "native/round0000/worker1/episode001_open_101"
        cls.events = [json.loads(line) for line in
                      (cls.directory / "adapter.jsonl").read_text().splitlines()]
        cls.transitions = [json.loads(line) for line in
                           (cls.directory / "transitions.jsonl").read_text().splitlines()]
        cls.epoch = cls.events[0]["epoch"]
        cls.goal = cls.epoch + ":tb3:11"
        cls.wrapper = candidate.ProtocolAuditor(cls.original, ROOT, candidate.FREEZE)

    def setUp(self):
        self.rows = copy.deepcopy(self.events)
        self.steps = copy.deepcopy(self.transitions)
        self.wrapper.receipts.clear()

    def run_candidate(self):
        return self.wrapper(self.rows, self.steps, self.epoch)

    def only(self, kind, *, goal=None, protocol_type=None):
        matches = [row for row in self.rows if row["kind"] == kind
                   and (goal is None or row["payload"].get("goal_id") == goal)
                   and (protocol_type is None or row["payload"].get("type") == protocol_type)]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_real_original_failure_retained_and_all_six_native_owners_replayed(self):
        with self.assertRaisesRegex(ValueError, candidate.OLD_CLOSURE_ERROR):
            self.original(self.rows, self.steps, self.epoch)
        before = copy.deepcopy(self.rows)
        result = self.run_candidate()
        receipt = result["versioned_unsent_audit"]
        self.assertTrue(receipt["passed"])
        self.assertFalse(receipt["original_passed"])
        self.assertEqual(receipt["original_errors"], [candidate.OLD_CLOSURE_ERROR])
        self.assertEqual(receipt["detached_view_removed_lines"], [330, 339])
        self.assertEqual(result["goal_count"], 6)
        self.assertEqual(result["native_terminal_count"], 6)
        self.assertEqual(result["confirmed_cancellation_count"], 5)
        self.assertEqual(self.rows, before)

    def test_normal_closed_episode_uses_original_unchanged(self):
        d = HERE / "native/round0000/worker2/episode001_open_101"
        rows = [json.loads(x) for x in (d / "adapter.jsonl").read_text().splitlines()]
        steps = [json.loads(x) for x in (d / "transitions.jsonl").read_text().splitlines()]
        original = self.original(rows, steps, rows[0]["epoch"])
        result = self.wrapper(rows, steps, rows[0]["epoch"])
        self.assertEqual({k: v for k, v in result.items() if k != "versioned_unsent_audit"},
                         original)
        self.assertTrue(result["versioned_unsent_audit"]["original_passed"])

    def test_missing_suppression_cannot_explain_closure_failure(self):
        self.rows.remove(self.only("edge_goal_not_sent", goal=self.goal))
        with self.assertRaisesRegex(ValueError, "no unsent proof"):
            self.run_candidate()

    def test_duplicate_suppression_fails(self):
        row = self.only("edge_goal_not_sent", goal=self.goal)
        self.rows.insert(self.rows.index(row), copy.deepcopy(row))
        with self.assertRaisesRegex(ValueError, "duplicate unsent suppression"):
            self.run_candidate()

    def test_unbound_suppression_fails(self):
        self.only("edge_goal_not_sent", goal=self.goal)["payload"]["goal_id"] += "-wrong"
        with self.assertRaisesRegex(ValueError, "unique logical lifecycle"):
            self.run_candidate()

    def test_nonstop_expiry_branch_is_not_accepted(self):
        self.only("edge_goal_not_sent", goal=self.goal)["payload"]["reason"] = "expired"
        with self.assertRaisesRegex(ValueError, "exact stopped"):
            self.run_candidate()

    def test_missing_or_non_peer_safety_stop_fails(self):
        for mutation in ("missing", "other_reason"):
            with self.subTest(mutation=mutation):
                self.rows = copy.deepcopy(self.events)
                stop = self.only("safety_stop")
                if mutation == "missing":
                    self.rows.remove(stop)
                else:
                    stop["payload"]["reason"] = '{"component":"other","reason":"other"}'
                with self.assertRaisesRegex(ValueError, "safety stop"):
                    self.run_candidate()

    def test_actual_native_send_without_result_never_gets_unsent_credit(self):
        send = self.only("protocol", goal=self.goal, protocol_type="send_goal")
        native = {"epoch": self.epoch, "stamp": 79.1, "kind": "native_send", "payload": {
            "robot": "tb3", "goal_id": self.goal, "command_id": 11,
            "pose": {"frame_id": "map", "stamp": 79.1,
                     "x": send["payload"]["goal"]["x"],
                     "y": send["payload"]["goal"]["y"],
                     "orientation": [0., 0., 0., 1.]}}}
        self.rows.insert(self.rows.index(send) + 1, native)
        with self.assertRaisesRegex(ValueError, "actually native-sent"):
            self.run_candidate()

    def test_native_receipt_or_rpc_handle_evidence_fails(self):
        for kind in ("accept", "result", "rpc_error", "handle_created"):
            with self.subTest(kind=kind):
                self.rows = copy.deepcopy(self.events)
                edge = self.only("edge_goal_not_sent", goal=self.goal)
                if kind in ("accept", "result"):
                    row = {"epoch": self.epoch, "stamp": 79.1, "kind": "delivery",
                           "payload": {"stream": "receipt", "payload": {
                               "goal_id": self.goal, "robot": "tb3", "type": kind,
                               "value": True if kind == "accept" else 5}}}
                else:
                    row = {"epoch": self.epoch, "stamp": 79.1, "kind": kind,
                           "payload": {"goal_id": self.goal}}
                self.rows.insert(self.rows.index(edge) + 1, row)
                with self.assertRaises(ValueError):
                    candidate.prove_unsent(self.rows, self.steps, self.epoch)

    def test_adversarial_v1_envelope_loopholes_fail(self):
        for mutation in ("epoch", "zero_sequence", "source_zero", "both_times_zero",
                         "wrong_version", "skipped_sequence", "boolean_sequence"):
            with self.subTest(mutation=mutation):
                self.rows = copy.deepcopy(self.events)
                envelope = [row["payload"] for row in self.rows
                            if row["kind"] == "delivery"
                            and row["payload"].get("stream") == "command"
                            and row["payload"]["payload"].get("goal_id") == self.goal][0]
                if mutation == "epoch":
                    envelope["epoch"] = "wrong-epoch"
                elif mutation == "zero_sequence":
                    envelope["sequence"] = envelope["version"] = 0
                elif mutation == "source_zero":
                    envelope["source_stamp"] = 0
                elif mutation == "both_times_zero":
                    envelope["source_stamp"] = envelope["generated_stamp"] = 0
                elif mutation == "wrong_version":
                    envelope["version"] = 0
                elif mutation == "skipped_sequence":
                    envelope["sequence"] = envelope["version"] = 100
                else:
                    envelope["sequence"] = envelope["version"] = True
                with self.assertRaisesRegex(ValueError, "command envelope"):
                    self.run_candidate()

    def test_prior_stream_watermark_duplicate_or_regression_fails(self):
        for mutation in ("duplicate_sequence", "source_regression", "epoch"):
            with self.subTest(mutation=mutation):
                self.rows = copy.deepcopy(self.events)
                prefix = [row["payload"] for row in self.rows
                          if row["kind"] == "delivery"
                          and row["payload"].get("stream") == "command"
                          and row["payload"].get("source") == "tb3"]
                self.assertEqual(len(prefix), 4)
                if mutation == "duplicate_sequence":
                    prefix[1]["sequence"] = prefix[1]["version"] = 1
                elif mutation == "source_regression":
                    prefix[1]["source_stamp"] = 0
                else:
                    prefix[1]["epoch"] = "wrong-epoch"
                with self.assertRaisesRegex(ValueError, "command envelope"):
                    self.run_candidate()

    def test_wrong_terminal_or_missing_terminal_fails(self):
        for mutation in ("status", "identity", "missing", "duplicate"):
            with self.subTest(mutation=mutation):
                self.rows = copy.deepcopy(self.events)
                terminal = self.only("protocol", goal=self.goal,
                                     protocol_type="protocol_terminal")
                if mutation == "status":
                    terminal["payload"]["status"] = "SUCCEEDED"
                elif mutation == "identity":
                    terminal["payload"]["command_id"] = 12
                elif mutation == "missing":
                    self.rows.remove(terminal)
                else:
                    self.rows.insert(self.rows.index(terminal), copy.deepcopy(terminal))
                with self.assertRaises(ValueError):
                    self.run_candidate()

    def test_suppression_before_actual_stop_fails(self):
        edge = self.only("edge_goal_not_sent", goal=self.goal)
        self.rows.remove(edge)
        stop = self.only("safety_stop")
        self.rows.insert(self.rows.index(stop), edge)
        with self.assertRaisesRegex(ValueError, "safety stop"):
            self.run_candidate()

    def test_wrong_lease_and_target_and_action_binding_fail(self):
        for mutation in ("lease", "target", "candidate_version", "command"):
            with self.subTest(mutation=mutation):
                self.rows = copy.deepcopy(self.events)
                send = self.only("protocol", goal=self.goal, protocol_type="send_goal")
                if mutation == "lease":
                    send["payload"]["lease_until"] = 82.9
                elif mutation == "target":
                    send["payload"]["goal"]["x"] += .1
                elif mutation == "command":
                    send["payload"]["command_id"] = 12
                else:
                    action = [row for row in self.rows if row["kind"] == "action"
                              and row["payload"]["command_id"] == 11][0]
                    action["payload"]["candidate_version"] = "wrong"
                with self.assertRaises(ValueError):
                    self.run_candidate()

    def test_saved_owner_or_lease_not_released_fails_independent_proof(self):
        for field, value in (("goal_id", self.goal), ("lease_until", 80.9),
                             ("owned", True), ("last_terminal", "SUCCEEDED")):
            with self.subTest(field=field):
                self.rows = copy.deepcopy(self.events)
                observed = [row for row in self.rows if row["kind"] == "observation"][-1]
                observed["payload"]["robots"][2]["navigation"][field] = value
                with self.assertRaisesRegex(ValueError, "not released|resurrected"):
                    candidate.prove_unsent(self.rows, self.steps, self.epoch)

    def test_other_native_owner_missing_result_still_fails(self):
        receipt = [row for row in self.rows if row["kind"] == "delivery"
                   and row["payload"].get("stream") == "receipt"
                   and row["payload"]["payload"]["type"] == "result"][0]
        self.rows.remove(receipt)
        with self.assertRaisesRegex(ValueError, "set difference"):
            self.run_candidate()

    def test_rerun_preserves_native_terminal_status_and_positive_cancel_checks(self):
        for mutation in ("terminal_status", "cancel_positive"):
            with self.subTest(mutation=mutation):
                self.rows = copy.deepcopy(self.events)
                receipts = [row for row in self.rows if row["kind"] == "delivery"
                            and row["payload"].get("stream") == "receipt"]
                if mutation == "terminal_status":
                    selected = [row for row in receipts
                                if row["payload"]["payload"]["type"] == "result"][0]
                    selected["payload"]["payload"]["value"] = 6
                    expected = "native/protocol terminal status differs"
                else:
                    selected = [row for row in receipts
                                if row["payload"]["payload"]["type"] == "cancel"][0]
                    selected["payload"]["payload"]["value"] = False
                    expected = "CANCELED terminal lacks positive cancel receipt"
                # Original first exits at unsent set equality. Its detached
                # replay must still execute and fail the later native checks.
                with self.assertRaisesRegex(ValueError, expected):
                    self.run_candidate()
                self.assertEqual(self.wrapper.receipts[-1]["original_errors"],
                                 [candidate.OLD_CLOSURE_ERROR])
                self.assertIn(expected, self.wrapper.receipts[-1]["new_error"])

    def test_no_incomplete_credit_or_unknown_source_or_replaced_original(self):
        with self.assertRaises(ValueError):
            self.wrapper(self.rows, self.steps, self.epoch, allow_incomplete=True)
        with self.assertRaisesRegex(ValueError, "explicitly reviewed"):
            candidate.ProtocolAuditor(self.original, ROOT, "0" * 40)
        with self.assertRaisesRegex(ValueError, "not the immutable"):
            candidate.ProtocolAuditor(lambda *args: {}, ROOT, candidate.FREEZE)


if __name__ == "__main__":
    unittest.main()
