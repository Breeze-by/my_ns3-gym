"""Portable synthetic mutations against the immutable W7 protocol function."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from mr3_learning import audit_protocol as candidate


HERE = Path(__file__).resolve().parent
ROOT = next(parent for parent in HERE.parents if (parent / ".git").exists())
FIXTURE_FREEZE = "a" * 40  # Synthetic source identity; never native evidence.
EPOCH = "portable-fixture-epoch"


def load_original():
    payload = subprocess.check_output(
        ["git", "show", candidate.W7 + ":" + candidate.AUDITOR], cwd=ROOT)
    assert hashlib.sha256(payload).hexdigest() == candidate.ORIGINAL_AUDITOR_SHA
    namespace = {"__name__": "normative_w7_protocol_unit_fixture"}
    scripts = str(ROOT / candidate.ROS / "scripts")
    sys.path.insert(0, scripts)
    try:
        exec(compile(payload, "normative-original", "exec"), namespace)
    finally:
        sys.path.remove(scripts)
    return namespace


def fixture(original, *, suppress=True):
    """Six real-goal-shaped unit lifecycles and one proven-unsent unit lifecycle.

    These are isolated test dictionaries, never native evidence or receipts.
    Every snapshot passes the unchanged original snapshot validator.
    """
    rows, transitions = [], []
    sequences = dict.fromkeys(candidate.ROBOTS, 0)
    canonical = original["canonical_digest"]

    def snapshot(sequence, stamp):
        navigation = {"goal_id": None, "owned": False, "command_id": None,
                      "lease_until": None, "accepted_at": None, "requested_at": None,
                      "phase": "idle", "last_goal_id": None, "last_terminal": None}
        robots = [{"name": name, "navigation": copy.deepcopy(navigation)}
                  for name in candidate.ROBOTS]
        if sequence == 4 and suppress:
            robots[2]["navigation"].update(last_goal_id=f"{EPOCH}:tb3:3",
                                           last_terminal="CANCELED")
        value = {"schema": "mr3-observation-v2", "epoch": EPOCH, "sequence": sequence,
                 "map_version": sequence, "source_stamp": stamp,
                 "candidates": [{"x": float(index), "y": 1.} for index in range(8)],
                 "path_maps": {name: {"epoch": EPOCH} for name in candidate.ROBOTS},
                 "robots": robots, "joint_action_mask": [True] * 1000}
        keys = ("epoch", "map_version", "sequence", "candidates", "path_maps")
        value["candidate_version"] = canonical({key: value[key] for key in keys})
        value["digest"] = canonical(value)
        return value

    def event(kind, stamp, payload):
        rows.append({"kind": kind, "stamp": stamp, "epoch": EPOCH, "payload": payload})

    def envelope(name, stream, payload, stamp):
        if stream == "command":
            sequences[name] += 1
        number = sequences[name]
        event("delivery", stamp, {"epoch": EPOCH, "stream": stream, "source": name,
                                  "sequence": number, "version": number,
                                  "source_stamp": stamp, "generated_stamp": stamp,
                                  "received_stamp": stamp, "payload": copy.deepcopy(payload)})

    source = snapshot(1, 10.)
    transitions.append({"kind": "reset", "snapshot": source})
    for index in range(1, 4):
        now = 9. + index
        event("observation", now, source)
        action = 12 if index < 3 else 880
        choices = [action // 100, action // 10 % 10, action % 10]
        command = {"epoch": EPOCH, "command_id": index, "action": action,
                   "created_at": now, "expires_at": now + 2.,
                   "observation_sequence": source["sequence"],
                   "observation_digest": source["digest"]}
        event("action", now, {"command_id": index, "action": action, "choices": choices,
                              "observation_sequence": source["sequence"],
                              "observation_digest": source["digest"],
                              "candidate_version": source["candidate_version"],
                              "results": {name: "sent" if choice < 8 else "kept"
                                          for name, choice in zip(candidate.ROBOTS, choices)}})
        for name, choice in zip(candidate.ROBOTS, choices):
            if choice >= 8:
                continue
            goal = f"{EPOCH}:{name}:{index}"
            target = source["candidates"][choice]
            send = {"epoch": EPOCH, "type": "send_goal", "robot": name, "goal_id": goal,
                    "command_id": index, "goal": target.copy(), **target,
                    "observation_version": source["sequence"], "stamp": now,
                    "created_at": now, "expires_at": now + 2., "lease_until": now + 2.}
            event("protocol", now, send)
            if index == 3 and suppress:
                event("safety_stop", now, {"reason": json.dumps({
                    "component": "peer_obstacles", "reason": "peer_body_envelopes_overlap"})})
            envelope(name, "command", send, now)
            if index == 3 and suppress:
                event("edge_goal_not_sent", now, {"goal_id": goal, "reason": "stopped"})
                event("protocol", now, {
                    "epoch": EPOCH, "robot": name, "goal_id": goal,
                    "type": "protocol_terminal", "command_id": index,
                    "stamp": now, "status": "CANCELED"})
                continue
            event("native_send", now, {"robot": name, "goal_id": goal, "command_id": index,
                  "pose": {"frame_id": "map", "stamp": now, **target,
                           "orientation": [0., 0., 0., 1.]}})
            envelope(name, "receipt", {
                "type": "accept", "robot": name, "goal_id": goal, "value": True}, now + .02)
            cancel = {"epoch": EPOCH, "robot": name, "goal_id": goal,
                      "type": "cancel_goal", "reason": "task_stop", "stamp": now + .2}
            event("protocol", now + .2, cancel)
            envelope(name, "command", cancel, now + .2)
            envelope(name, "receipt", {
                "type": "cancel", "robot": name, "goal_id": goal, "value": True}, now + .21)
            envelope(name, "receipt", {
                "type": "result", "robot": name, "goal_id": goal, "value": 5}, now + .22)
            event("protocol", now + .24, {"type": "protocol_terminal", "robot": name,
                                          "goal_id": goal, "status": "CANCELED"})
        source = snapshot(index + 1, 10. + index if index < 3 else 12.5)
        transitions.append({"kind": "step", "snapshot": source, "terminated": index == 3,
                            "truncated": False, "info": {"command": command,
                                                         "reason": "navigation_failure"}})
    event("observation", 12.5, source)
    rows.sort(key=lambda row: row["stamp"])
    return rows, transitions


class UnsentProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        git_output = subprocess.check_output

        def fixture_sources(command, **kwargs):
            if command[:2] == ["git", "show"] and command[2].startswith(FIXTURE_FREEZE + ":"):
                return (ROOT / command[2].split(":", 1)[1]).read_bytes()
            return git_output(command, **kwargs)

        # Test the real explicit source pins before a new commit can exist.
        # The immutable W7 function still comes from its actual Git object;
        # unknown/replaced sources and worktree mismatches remain rejected.
        patcher = patch.object(candidate.subprocess, "check_output", fixture_sources)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.normative = load_original()
        cls.original = staticmethod(cls.normative["audit_protocol"])
        cls.events, cls.transitions = fixture(cls.normative)
        cls.epoch = cls.events[0]["epoch"]
        cls.goal = cls.epoch + ":tb3:3"
        cls.wrapper = candidate.ProtocolAuditor(cls.original, ROOT, FIXTURE_FREEZE)

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
        expected = [index + 1 for index, row in enumerate(self.rows)
                    if row["kind"] == "protocol" and row["payload"].get("goal_id") == self.goal]
        self.assertEqual(receipt["detached_view_removed_lines"], expected)
        self.assertEqual(result["goal_count"], 6)
        self.assertEqual(result["native_terminal_count"], 6)
        self.assertEqual(result["confirmed_cancellation_count"], 6)
        self.assertEqual(self.rows, before)

    def test_normal_closed_episode_uses_original_unchanged(self):
        rows, steps = fixture(self.normative, suppress=False)
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
        native = {"epoch": self.epoch, "stamp": 12., "kind": "native_send", "payload": {
            "robot": "tb3", "goal_id": self.goal, "command_id": 3,
            "pose": {"frame_id": "map", "stamp": 12.,
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
                    row = {"epoch": self.epoch, "stamp": 12., "kind": "delivery",
                           "payload": {"stream": "receipt", "payload": {
                               "goal_id": self.goal, "robot": "tb3", "type": kind,
                               "value": True if kind == "accept" else 5}}}
                else:
                    row = {"epoch": self.epoch, "stamp": 12., "kind": kind,
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
                self.assertEqual(len(prefix), 5)
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
                              and row["payload"]["command_id"] == 3][0]
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
        with self.assertRaisesRegex(ValueError, "Git source unavailable"):
            candidate.ProtocolAuditor(self.original, ROOT, "0" * 40)
        with self.assertRaisesRegex(ValueError, "not the immutable"):
            candidate.ProtocolAuditor(lambda *args: {}, ROOT, FIXTURE_FREEZE)

    def test_new_freeze_with_exact_four_source_pins_records_its_git_provenance(self):
        new_freeze = "a" * 40
        git_output = subprocess.check_output

        def new_commit_same_reviewed_sources(command, **kwargs):
            if command[:2] == ["git", "show"] and command[2].startswith(new_freeze + ":"):
                return (ROOT / command[2].split(":", 1)[1]).read_bytes()
            return git_output(command, **kwargs)

        with patch.object(candidate.subprocess, "check_output", new_commit_same_reviewed_sources):
            wrapper = candidate.ProtocolAuditor(self.original, ROOT, new_freeze)
        result = wrapper(self.rows, self.steps, self.epoch)
        self.assertEqual(result["versioned_unsent_audit"]["audited_freeze"], new_freeze)
        self.assertEqual(len(candidate.PINS), 4)
        for relative, digest in candidate.PINS.items():
            self.assertEqual(wrapper.source_proof[relative], {
                "sha256": digest, "git_source": new_freeze + ":" + relative})
        self.assertTrue(wrapper.source_proof["original_protocol_function"][
            "executable_code_identity_equal"])

    def test_each_changed_frozen_source_is_rejected_even_at_new_freeze(self):
        new_freeze = "a" * 40
        git_output = subprocess.check_output
        for changed in candidate.PINS:
            with self.subTest(changed=changed):
                def changed_commit_source(command, **kwargs):
                    if command[:2] == ["git", "show"] and command[2].startswith(new_freeze + ":"):
                        relative = command[2].split(":", 1)[1]
                        return (ROOT / relative).read_bytes() + (
                            b"\n# unreviewed semantic source" if relative == changed else b"")
                    return git_output(command, **kwargs)

                with patch.object(candidate.subprocess, "check_output", changed_commit_source):
                    with self.assertRaisesRegex(ValueError, "differs from exact unsent proof"):
                        candidate.ProtocolAuditor(self.original, ROOT, new_freeze)

    def test_current_worktree_mismatch_cannot_be_hidden_by_matching_frozen_source(self):
        relative = next(iter(candidate.PINS))
        path = ROOT / relative
        read_bytes = Path.read_bytes

        def changed_worktree(source):
            return read_bytes(source) + (b"\n# changed" if source == path else b"")

        with patch.object(Path, "read_bytes", changed_worktree):
            with self.assertRaisesRegex(ValueError, "runtime/current source differs"):
                candidate.ProtocolAuditor(self.original, ROOT, FIXTURE_FREEZE)

    def test_original_nonclosure_error_is_preserved_and_never_replaced(self):
        action = next(row for row in self.rows if row["kind"] == "action")
        action["payload"]["observation_digest"] = "wrong-observation"
        with self.assertRaisesRegex(ValueError, "accepted action does not replay"):
            self.run_candidate()
        receipt = self.wrapper.receipts[-1]
        self.assertEqual(receipt["original_errors"], [
            "accepted action does not replay from saved candidate/mask"])
        self.assertFalse(receipt["passed"])
        self.assertNotIn("detached_view_removed_lines", receipt)

    def test_invalid_git_identity_is_rejected_before_any_git_lookup(self):
        for freeze in ("HEAD", "de7a805", "-" * 40, None):
            with self.subTest(freeze=freeze):
                with patch.object(candidate.subprocess, "check_output") as git:
                    with self.assertRaisesRegex(ValueError, "exact Git commit identity"):
                        candidate.ProtocolAuditor(self.original, ROOT, freeze)
                    git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
