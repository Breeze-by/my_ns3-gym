"""Adversarial pure offline tests for command-time receipt semantics."""

import copy
import contextlib
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("command_time_v7", HERE / "audit_command_time_v7.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
BASE, _ = CHECKER.load_auditor()
EPOCH = "offline-fixture"


def fixture(start=254.6, *, expires=None, created=None, reason=None):
    end = (round(start * 1e9) + 1_000_000_000) / 1e9
    command = {"epoch": EPOCH, "command_id": 1, "observation_sequence": 11,
               "observation_digest": "snapshot-11", "action": 888,
               "created_at": start if created is None else created,
               "expires_at": ((round(start * 1e9) + 2_000_000_000) / 1e9
                              if expires is None else expires)}
    reset = {"kind": "reset", "terminated": False, "truncated": False,
             "snapshot": {"epoch": EPOCH, "sequence": 11,
                          "digest": "snapshot-11", "source_stamp": start},
             "info": {"watermarks": {"delivery": 11}}}
    step = {"kind": "step", "terminated": False, "truncated": False,
            "snapshot": {"epoch": EPOCH, "sequence": 12,
                         "digest": "snapshot-12", "source_stamp": end},
            "info": {"epoch": EPOCH, "command": command,
                     "reward_diagnostics": {"step_start": start},
                     "watermarks": {"delivery": 12}}}
    payload = {"command_id": 1, "observation_sequence": 11}
    if reason is None:
        payload.update({"action": 888, "observation_digest": "snapshot-11",
                        "results": {robot: "kept" for robot in BASE.ROBOTS}})
    else:
        payload["reason"] = reason
    event = {"epoch": EPOCH, "stamp": start,
             "kind": "action" if reason is None else "action_rejected", "payload": payload}
    return [reset, step], [event]


def replay(transitions, events, **kwargs):
    return CHECKER.audit_command_times(events, transitions, EPOCH, auditor=BASE, **kwargs)


def zero_terminal(previous, sequence):
    boundary = previous["snapshot"]["source_stamp"]
    diagnostic = {"epoch": EPOCH, "sequence": sequence, "terminated": True, "truncated": False,
                  "new_correct_free_cells": 0, "reward_terms": {"coverage": 0.},
                  "delta_sim_time": 0., "reason": "navigation_failure",
                  "step_start": boundary, "effective_step_end": boundary,
                  "requested_step_end": boundary}
    return {"kind": "step", "terminated": True, "truncated": False,
            "snapshot": copy.deepcopy(previous["snapshot"]),
            "info": {"terminal_observation_reused": True, "action_submitted": False,
                     "command": None, "requested_action": 888, "dt": 0., "physical_dt": 0.,
                     "reason": "navigation_failure", "reward_diagnostics": diagnostic,
                     "watermarks": copy.deepcopy(previous["info"]["watermarks"])}}


def save_episode(directory, *, reason=None, fault=False):
    transitions, events = fixture(reason=reason)
    objects = {"metadata.json": {"epoch": EPOCH, "freeze": "offline-freeze"},
               "supervisor_metadata.json": {"epoch": EPOCH,
                                            "reset_kind": "complete_process_rebuild",
                                            "worker_identity": {"pid": 123, "start_ticks": 456}},
               "supervisor_shutdown.json": {"epoch": EPOCH,
                                            "owned_processes_seen": [{"pid": 123,
                                                                      "start_ticks": 456}],
                                            "remaining_owned_processes": [],
                                            "remaining_owned_zombies": [],
                                            "forced_shutdown": fault, "failed_sample": fault,
                                            "worker_returncode": -9 if fault else 0}}
    if not fault:
        objects["summary.json"] = {"epoch": EPOCH}
    for name, payload in objects.items():
        (directory / name).write_text(json.dumps(payload))
    for name, records in (("transitions.jsonl", transitions), ("adapter.jsonl", events)):
        (directory / name).write_text("".join(json.dumps(row) + "\n" for row in records))


class CommandTimeTests(unittest.TestCase):
    def test_exact_two_seconds_crossing_power_of_two_is_accepted(self):
        for start in (6.03, 254.6, 255.6, 510.6, 511.6):
            with self.subTest(start=start):
                result = replay(*fixture(start))
                self.assertTrue(result["passed"])
                self.assertEqual(result["bindings"][0]["ttl_ns"], 2_000_000_000)

    def test_native_v6_false_rejections_are_detected(self):
        for start in (254.6, 255.6):
            with self.subTest(start=start):
                result = replay(*fixture(start, reason=CHECKER.TIME_REJECTION))
                self.assertFalse(result["passed"])
                self.assertEqual(result["bindings"][0]["failure"],
                                 "valid_command_time_falsely_rejected")

    def test_valid_time_one_ns_before_expiry_is_accepted(self):
        transitions, events = fixture(start=254.6)
        events[0]["stamp"] = 256.599999999
        transitions[1]["snapshot"]["source_stamp"] = 256.6
        self.assertTrue(replay(transitions, events)["passed"])

    def test_expiry_equality_and_after_are_invalid(self):
        for now in (256.6, 256.600000001):
            for reason in (None, CHECKER.TIME_REJECTION):
                with self.subTest(now=now, reason=reason):
                    transitions, events = fixture(reason=reason)
                    events[0]["stamp"] = now
                    transitions[1]["snapshot"]["source_stamp"] = 257.6
                    result = replay(transitions, events)
                    self.assertEqual(result["passed"], reason is not None)
                    self.assertIn("expired_at_receipt", result["bindings"][0]["invalidity"])

    def test_real_one_ns_excess_ttl_is_not_hidden_by_epsilon(self):
        for overshoot in (1, 2, 1_000_000_000):
            for reason in (None, CHECKER.TIME_REJECTION):
                with self.subTest(overshoot=overshoot, reason=reason):
                    expires = (254_600_000_000 + CHECKER.TTL_NS + overshoot) / 1e9
                    result = replay(*fixture(expires=expires, reason=reason))
                    self.assertEqual(result["passed"], reason is not None)
                    self.assertEqual(result["bindings"][0]["ttl_ns"], CHECKER.TTL_NS + overshoot)

    def test_one_ns_below_maximum_ttl_is_valid(self):
        result = replay(*fixture(expires=256.599999999))
        self.assertTrue(result["passed"])
        self.assertEqual(result["bindings"][0]["ttl_ns"], CHECKER.TTL_NS - 1)

    def test_future_creation_one_ns_is_invalid(self):
        for reason in (None, CHECKER.TIME_REJECTION):
            result = replay(*fixture(created=254.600000001, reason=reason))
            self.assertEqual(result["passed"], reason is not None)
            self.assertIn("created_in_future", result["bindings"][0]["invalidity"])

    def test_nonpositive_ttl_is_invalid(self):
        for expires in (254.6, 254.599999999):
            result = replay(*fixture(expires=expires, reason=CHECKER.TIME_REJECTION))
            self.assertTrue(result["passed"])
            self.assertIn("nonpositive_ttl", result["bindings"][0]["invalidity"])

    def test_invalid_timestamp_types_are_rejected_without_coercion(self):
        for value in (True, False, None, "254.6", -1., float("nan"), float("inf"), 1e300):
            with self.subTest(value=value):
                transitions, events = fixture(reason=CHECKER.TIME_REJECTION)
                transitions[1]["info"]["command"]["created_at"] = value
                result = replay(transitions, events)
                self.assertTrue(result["passed"])
                self.assertEqual(result["bindings"][0]["invalidity"],
                                 ["invalid_command_timestamp"])
                json.dumps(result, allow_nan=False)

    def test_other_real_rejection_reason_is_preserved(self):
        result = replay(*fixture(reason="masked_action"))
        self.assertTrue(result["passed"])
        self.assertEqual(result["bindings"][0]["rejection_reason"], "masked_action")
        self.assertFalse(result["other_rejection_reasons_revalidated"])

    def test_time_invalid_action_cannot_escape_through_another_reason(self):
        result = replay(*fixture(created=254.600000001))
        self.assertFalse(result["passed"])
        self.assertEqual(result["bindings"][0]["failure"], "invalid_command_time_accepted")

    def test_dispatcher_ttl_rejection_inside_action_receipt_fails(self):
        for rejected in ("invalid_ttl", "expired"):
            transitions, events = fixture()
            events[0]["payload"]["results"]["tb2"] = rejected
            result = replay(transitions, events)
            self.assertFalse(result["passed"])
            self.assertEqual(result["bindings"][0]["failure"],
                             "valid_adapter_time_rejected_by_dispatcher")

    def test_cross_epoch_receipt_fails(self):
        transitions, events = fixture()
        events[0]["epoch"] = "another-epoch"
        with self.assertRaisesRegex(ValueError, "epoch mismatch"):
            replay(transitions, events)

    def test_wrong_command_identity_fails(self):
        transitions, events = fixture()
        events[0]["payload"]["command_id"] = 2
        with self.assertRaisesRegex(ValueError, "command identity"):
            replay(transitions, events)

    def test_wrong_observation_identity_fails(self):
        transitions, events = fixture()
        events[0]["payload"]["observation_sequence"] = 12
        with self.assertRaisesRegex(ValueError, "observation identity"):
            replay(transitions, events)

    def test_prior_snapshot_binding_is_required(self):
        transitions, events = fixture()
        transitions[0]["snapshot"]["digest"] = "some-other-observation"
        with self.assertRaisesRegex(ValueError, "preceding delivered snapshot"):
            replay(transitions, events)

    def test_accepted_action_and_digest_must_match_command(self):
        for key, value in (("action", 889), ("observation_digest", "wrong")):
            transitions, events = fixture()
            events[0]["payload"][key] = value
            with self.assertRaisesRegex(ValueError, "action/digest"):
                replay(transitions, events)

    def test_duplicate_receipt_or_missing_receipt_fails(self):
        transitions, events = fixture()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            replay(transitions, events + copy.deepcopy(events))
        with self.assertRaisesRegex(ValueError, "lacks its actual action receipt"):
            replay(transitions, [])

    def test_receipt_cannot_be_moved_to_another_step_by_same_boundary_stamp(self):
        transitions, events = fixture()
        other, receipt = fixture(start=255.6, reason="masked_action")
        command = other[1]["info"]["command"]
        command.update({"command_id": 2, "observation_sequence": 12,
                        "observation_digest": "snapshot-12"})
        other[1]["snapshot"]["sequence"] = 13
        receipt[0]["payload"].update({"command_id": 2, "observation_sequence": 12})
        result = replay(transitions + [other[1]], events + receipt)
        self.assertTrue(result["passed"])
        self.assertEqual([row["step_sequence"] for row in result["bindings"]], [1, 2])
        self.assertEqual(result["bindings"][1]["receipt_stamp"],
                         transitions[1]["snapshot"]["source_stamp"])

    def test_receipt_outside_physical_step_fails(self):
        for stamp in (254.599999999, 255.600000001):
            transitions, events = fixture()
            events[0]["stamp"] = stamp
            with self.assertRaisesRegex(ValueError, "physical interval"):
                replay(transitions, events)

    def test_only_proven_zero_action_terminal_is_excluded(self):
        transitions, events = fixture()
        transitions.append(zero_terminal(transitions[-1], 2))
        result = replay(transitions, events)
        self.assertTrue(result["passed"])
        self.assertEqual(result["commands_checked"], 1)
        self.assertEqual(result["excluded_no_action_terminal_steps"], [2])

    def test_zero_tail_must_not_hide_a_command_or_nonzero_coverage(self):
        for mutate in ("command", "coverage", "physical_dt", "watermark"):
            transitions, events = fixture()
            tail = zero_terminal(transitions[-1], 2)
            if mutate == "command":
                tail["info"]["command"] = transitions[-1]["info"]["command"]
            elif mutate == "coverage":
                tail["info"]["reward_diagnostics"]["reward_terms"]["coverage"] = .1
            elif mutate == "physical_dt":
                tail["info"]["physical_dt"] = .02
            else:
                tail["info"]["watermarks"] = {"delivery": 13}
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                replay(transitions + [tail], events)

    def test_no_action_flag_without_zero_terminal_proof_fails(self):
        transitions, events = fixture()
        transitions[1]["info"]["action_submitted"] = False
        with self.assertRaisesRegex(ValueError, "ordinary step falsely"):
            replay(transitions, events)

    def test_prefix_has_no_full_episode_or_closure_credit(self):
        result = replay(*fixture(), allow_incomplete=True)
        self.assertTrue(result["passed"])
        self.assertEqual(result["scope"], "declared incomplete command prefix only")
        self.assertFalse(result["complete_episode_credit"])
        self.assertFalse(result["reward_contact_mask_ownership_closure_revalidated"])

    def test_helper_pins_original_auditor_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in CHECKER.PINNED_AUDITORS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((CHECKER.repository_root() / relative).read_bytes())
            path.write_text(path.read_text() + "\n# mutation\n")
            with self.assertRaisesRegex(ValueError, "dependency SHA mismatch"):
                CHECKER.load_auditor(root)

    def test_episode_cli_writes_sha_bound_output_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_episode(directory)
            output = directory / "new-audit.json"
            argv = [str(directory), "--freeze", "offline-freeze", "--output", str(output)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(CHECKER.main(argv), 0)
            saved = output.read_bytes()
            result = json.loads(saved)
            self.assertTrue(result["passed"])
            self.assertEqual(result["command_time"]["commands_checked"], 1)
            self.assertEqual(result["original_auditor_sha256"], CHECKER.PINNED_AUDITORS)
            self.assertIn("adapter.jsonl", result["evidence_sha256"])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                CHECKER.main(argv)
            self.assertEqual(output.read_bytes(), saved)

    def test_episode_cli_retains_false_rejection_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_episode(directory, reason=CHECKER.TIME_REJECTION)
            output = directory / "negative-audit.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(CHECKER.main([str(directory), "--freeze", "offline-freeze",
                                               "--output", str(output)]), 1)
            result = json.loads(output.read_text())
            self.assertFalse(result["passed"])
            self.assertEqual(result["command_time"]["bindings"][0]["ttl_ns"], CHECKER.TTL_NS)
            self.assertIn("valid_command_time_falsely_rejected", result["errors"][0])

    def test_actual_killed_prefix_is_bound_and_never_gets_full_credit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_episode(directory, fault=True)
            result = CHECKER.audit_episode(directory, "offline-freeze", True, auditor=BASE)
            self.assertTrue(result["passed"])
            self.assertFalse(result["complete_episode_credit"])
            self.assertTrue(result["expected_infrastructure_fault"])
            (directory / "summary.json").write_text(json.dumps({"epoch": EPOCH}))
            with self.assertRaisesRegex(ValueError, "normal summary"):
                CHECKER.audit_episode(directory, "offline-freeze", True, auditor=BASE)

    def test_incomplete_prefix_requires_real_kill_returncode(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_episode(directory, fault=True)
            path = directory / "supervisor_shutdown.json"
            receipt = json.loads(path.read_text())
            receipt["worker_returncode"] = 0
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "SIGKILL fault"):
                CHECKER.audit_episode(directory, "offline-freeze", True, auditor=BASE)

    def test_freeze_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_episode(directory)
            with self.assertRaisesRegex(ValueError, "source freeze mismatch"):
                CHECKER.audit_episode(directory, "different-freeze", auditor=BASE)

    def test_compressed_selected_evidence_uses_original_evidence_reader(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_episode(directory)
            for name in ("transitions.jsonl", "adapter.jsonl"):
                path = directory / name
                with gzip.open(path.with_suffix(".jsonl.gz"), "wb") as stream:
                    stream.write(path.read_bytes())
                path.unlink()
            result = CHECKER.audit_episode(directory, "offline-freeze", auditor=BASE)
            self.assertTrue(result["passed"])
            self.assertIn("transitions.jsonl", result["evidence_sha256"])


if __name__ == "__main__":
    unittest.main()
