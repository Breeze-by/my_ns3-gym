"""Synthetic composition/source-binding checks; no native evidence replay."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PHASE = load("phase_v3_test_subject", "audit_mr3_env_contact_phase_v3.py")
COMMAND = load("phase_v3_test_command", PHASE.COMMAND_NAME)
FIXTURE = load("phase_v3_command_fixtures", "test_audit_command_time_v7.py")
FREEZE = "a" * 40


class PhaseV3Tests(unittest.TestCase):
    def test_original_helpers_are_exact_immutable_sources(self):
        for name, expected in ((PHASE.BASE_NAME, PHASE.BASE_SHA256),
                               (PHASE.COMMAND_NAME, PHASE.COMMAND_SHA256)):
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), expected)

    def test_invalid_or_missing_explicit_freeze_is_rejected(self):
        for value in (None, "", "HEAD", "c8d4832", "A" * 40, "a" * 39, "a" * 41):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "exact40-hex"):
                PHASE.validate_freeze(value)
        with self.assertRaises(SystemExit):
            PHASE.main(["synthetic", "--output", "unused-output.json"])

    def test_prior_v6_git_source_cannot_be_relabelled_as_new_runtime(self):
        with self.assertRaisesRegex(ValueError, "Git runtime/source SHA mismatch"):
            PHASE.verify_git_runtime(PHASE.repository_root(),
                                     "c8d483228ecb0105c905459578eddbb4a23d4520")

    def test_claimed_git_runtime_blob_must_match_even_when_worktree_would_match(self):
        with patch.object(PHASE, "PINNED_RUNTIME", {"source.py": hashlib.sha256(
                b"matching worktree").hexdigest()}), patch.object(
                PHASE.subprocess, "check_output", return_value=b"different Git blob"):
            with self.assertRaisesRegex(ValueError, "Git runtime/source SHA mismatch"):
                PHASE.verify_git_runtime(Path("."), FREEZE)

    def test_verified_git_proof_uses_the_explicit_exact_freeze(self):
        payload = b"fixed source"
        with patch.object(PHASE, "PINNED_RUNTIME", {
                "source.py": hashlib.sha256(payload).hexdigest()}), patch.object(
                PHASE.subprocess, "check_output", return_value=payload) as read:
            self.assertEqual(PHASE.verify_git_runtime(Path("."), FREEZE),
                             {"source.py": hashlib.sha256(payload).hexdigest()})
            self.assertEqual(read.call_args.args[0], ["git", "show", FREEZE + ":source.py"])

    def test_helper_hash_tamper_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "mutated.py"
            source.write_text("raise AssertionError('must not execute')\n")
            with self.assertRaisesRegex(ValueError, "helper SHA mismatch"):
                PHASE.load_pinned_module("must_not_execute", source, "0" * 64)

    def test_v2_is_loaded_as_separate_instances(self):
        first = PHASE.load_pinned_module("phase_v3_isolation_one", HERE / PHASE.BASE_NAME,
                                         PHASE.BASE_SHA256)
        second = PHASE.load_pinned_module("phase_v3_isolation_two", HERE / PHASE.BASE_NAME,
                                          PHASE.BASE_SHA256)
        first.FREEZE = FREEZE
        first.PINNED_RUNTIME.clear()
        self.assertEqual(second.FREEZE, "c8d483228ecb0105c905459578eddbb4a23d4520")
        self.assertEqual(len(second.PINNED_RUNTIME), 7)

    def test_component_loading_rebinds_both_source_sets_and_records_git_proof(self):
        root = PHASE.repository_root()

        def synthetic_git(command, **kwargs):
            self.assertEqual(command[:2], ["git", "show"])
            self.assertTrue(command[2].startswith(FREEZE + ":"))
            return (root / command[2].split(":", 1)[1]).read_bytes()

        with patch.object(PHASE.subprocess, "check_output", side_effect=synthetic_git):
            base, audit, command, proof = PHASE.load_components(FREEZE)
        self.assertEqual(base.FREEZE, FREEZE)
        self.assertEqual(base.PINNED_RUNTIME, PHASE.PINNED_RUNTIME)
        self.assertEqual(base.PINNED_DOCUMENTS, PHASE.PINNED_DOCUMENTS)
        self.assertEqual(len(proof), 12)
        self.assertEqual(command.METHOD, COMMAND.METHOD)
        self.assertTrue(callable(audit.audit_protocol))
        for path in PHASE.PINNED_RUNTIME:
            self.assertEqual(proof[path]["git_source"], FREEZE + ":" + path)

    def compose(self, transitions, events, *, original_error=None, command=COMMAND,
                matrix=False, expected_fault=False):
        calls = []

        def original(rows, samples, epoch, incomplete=False):
            calls.append(("original", incomplete))
            if original_error:
                raise ValueError(original_error)
            return {"accepted_action_count": 1}

        audit = SimpleNamespace(audit_protocol=original)
        for name in ("require", "nanoseconds", "number", "validate_reused_terminal"):
            setattr(audit, name, getattr(FIXTURE.BASE, name))

        def inherited(selected, directories, **kwargs):
            calls.append(("base", kwargs))
            self.assertIs(selected, audit)
            return selected.audit_protocol(events, transitions, FIXTURE.EPOCH, expected_fault)

        base = SimpleNamespace(corrected_audit=inherited)
        try:
            result = PHASE.corrected_audit(base, audit, command, [Path("synthetic")],
                                           matrix=matrix, expected_fault=expected_fault)
        finally:
            self.assertIs(audit.audit_protocol, original)
        return result, calls

    def test_real_command_gate_runs_after_original_and_attaches_result(self):
        result, calls = self.compose(*FIXTURE.fixture())
        self.assertEqual(calls[1], ("original", False))
        self.assertTrue(result["command_time"]["passed"])
        self.assertEqual(result["command_time"]["commands_checked"], 1)

    def test_actual_v6_style_legal_ttl_false_rejection_cannot_pass_composition(self):
        for start in (254.6, 255.6):
            with self.subTest(start=start), self.assertRaisesRegex(
                    ValueError, "valid_command_time_falsely_rejected"):
                self.compose(*FIXTURE.fixture(start, reason=COMMAND.TIME_REJECTION))

    def test_illegal_ttl_accepted_cannot_pass_composition(self):
        with self.assertRaisesRegex(ValueError, "invalid_command_time_accepted"):
            self.compose(*FIXTURE.fixture(expires=256.600000001))

    def test_original_protocol_failure_prevents_command_gate_and_restores_hook(self):
        command = SimpleNamespace(audit_command_times=lambda *args, **kwargs:
                                  self.fail("command gate ran after base rejection"))
        with self.assertRaisesRegex(ValueError, "original ownership failure"):
            self.compose(*FIXTURE.fixture(), original_error="original ownership failure",
                         command=command)

    def test_command_gate_exception_restores_hook(self):
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic checker error")
        with self.assertRaisesRegex(RuntimeError, "synthetic checker error"):
            self.compose(*FIXTURE.fixture(), command=SimpleNamespace(audit_command_times=fail))

    def test_fault_prefix_and_matrix_flags_are_forwarded_without_full_credit(self):
        result, calls = self.compose(*FIXTURE.fixture(), expected_fault=True, matrix=True)
        self.assertEqual(calls[0], ("base", {"matrix": True, "expected_fault": True}))
        self.assertEqual(calls[1], ("original", True))
        self.assertFalse(result["command_time"]["complete_episode_credit"])

    def test_genuine_zero_tail_excludes_only_its_no_action_branch(self):
        transitions, events = FIXTURE.fixture()
        transitions.append(FIXTURE.zero_terminal(transitions[-1], 2))
        result, _ = self.compose(transitions, events)
        self.assertEqual(result["command_time"]["excluded_no_action_terminal_steps"], [2])
        tampered = copy.deepcopy(transitions)
        tampered[-1]["info"]["command"] = transitions[1]["info"]["command"]
        with self.assertRaises(ValueError):
            self.compose(tampered, events)

    def test_cli_provenance_is_distinct_and_output_is_exclusive(self):
        fake = {"schema": "original-schema", "passed": True, "errors": []}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new.json"
            with patch.object(PHASE, "load_components", return_value=(
                    object(), object(), SimpleNamespace(METHOD=COMMAND.METHOD), {})), patch.object(
                    PHASE, "corrected_audit", return_value=copy.deepcopy(fake)):
                self.assertEqual(PHASE.main(["synthetic", "--freeze", FREEZE,
                                             "--output", str(output)]), 0)
            original = output.read_bytes()
            payload = json.loads(original)
            proof = payload["offline_contact_phase_audit"]
            self.assertEqual(payload["schema"], "mr3-p1c-contact-phase-audit-v3")
            self.assertEqual(proof["freeze"], FREEZE)
            self.assertEqual(proof["only_overridden_functions"],
                             ["audit_contacts", "audit_protocol"])
            self.assertFalse(proof["base_v2"]["contact_logic_modified"])
            self.assertFalse(proof["original_results_modified"])
            with self.assertRaises(SystemExit):
                PHASE.main(["synthetic", "--freeze", FREEZE, "--output", str(output)])
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
