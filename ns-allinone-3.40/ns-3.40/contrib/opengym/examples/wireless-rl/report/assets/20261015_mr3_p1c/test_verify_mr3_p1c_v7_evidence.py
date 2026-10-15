"""Isolated adversarial fixtures; never inspect active v7 native evidence."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


HERE = Path(__file__).resolve().parent
SUBJECT = module("v7_integrity_subject", HERE / "verify_mr3_p1c_v7_evidence.py")
ROOT = next(path for path in (Path.cwd(), *Path.cwd().parents) if (path / ".git").exists())
BASE = SUBJECT.load_legacy(ROOT)
DRIVER = module("v7_integrity_driver_fixture", ROOT / SUBJECT.ASSETS / "v7_execution_driver.py")
PLAN = BASE.read_json(ROOT / SUBJECT.ASSETS / "predeclared_native_plan_v7.json")
FREEZE = "a" * 40


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


def fixture(root):
    value = object.__new__(SUBJECT.Verifier)
    value.root, value.freeze, value.base = root, FREEZE, BASE
    value.assets, value.native = root / SUBJECT.ASSETS, root / SUBJECT.ASSETS / "native_v7"
    value.git_hashes, value.profile_sha, value.binding_sha = {}, "profile-sha", "binding-sha"
    value.driver = DRIVER
    value.stages = DRIVER.build_stages(root, PLAN, FREEZE)
    value.stage_by_name = {row["name"]: row for row in value.stages}
    value.command = SimpleNamespace(METHOD="command-method")
    return value


def episode(*, fault=False, epoch="fixture"):
    timing = {"passed": True, "errors": [], "method": "command-method",
              "complete_episode_credit": False, "commands_checked": 1,
              "accepted_commands": 1, "rejected_commands": 0,
              "bindings": [{"epoch": epoch, "failure": None, "command_id": 1,
                            "receipt_kind": "action"}]}
    result = {"passed": True, "errors": [], "freeze": FREEZE, "epoch": epoch,
              "expected_infrastructure_fault": fault, "complete_episode_credit": not fault,
              "transitions": {"complete": not fault, "submitted_action_count": 1,
                              "transition_count": 4 if fault else 1},
              "ordered_shutdown": {"proven": not fault},
              "protocol": {"accepted_action_count": 1, "rejected_action_count": 0,
                           "command_time": timing}}
    if not fault:
        result["contacts"] = {"passed": True}
    return result


def manifest_fixture(value):
    stage = value.stage_by_name["clock"]
    value.stages, value.stage_by_name = [stage], {"clock": stage}
    raw = stage["directory"] / "physics.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'{"physical":"fixture only"}\n')
    selected = value.native / "clock/physics.jsonl.gz"
    selected.parent.mkdir(parents=True)
    with gzip.open(selected, "wb") as stream:
        stream.write(raw.read_bytes())
    row = {"original": str(raw.relative_to(value.root)), "original_bytes": raw.stat().st_size,
           "original_sha256": BASE.digest(raw), "selected": str(selected.relative_to(value.root)),
           "selected_bytes": selected.stat().st_size, "selected_sha256": BASE.digest(selected),
           "encoding": "gzip; fixture", "decoded_selected_sha256": BASE.digest(raw),
           "decoded_matches_original": True}
    path = selected.with_name("manifest.json")
    payload = {"schema": "mr3-selected-native-evidence-manifest-v1", "source_freeze": FREEZE,
               "originals_modified": False,
               "original_root": str(raw.parent.relative_to(value.root)),
               "selected_root": str(selected.parent.relative_to(value.root)),
               "original_file_count": 1, "selected_artifact_count": 1, "files": [row]}
    write(path, payload)
    return path, raw, selected, payload


def journal_fixture(value):
    value.assets.mkdir(parents=True, exist_ok=True)
    matrix = write(value.assets / "matrix_v7_contact_phase_v3_audit.json", {"mock": True})
    commands = []
    for stage in value.stages:
        name = stage["name"]
        commands.append((name, "native", stage["native"]))
        if name != "clock":
            if name == "fault":
                commands.append((name, "prefix_phase3", stage["prefix"]))
            commands.extend(((name, "primary_phase3", stage["primary"]),
                             (name, "scalar_v3", stage["scalar"])))
    argv = DRIVER.phase_command(value.assets, FREEZE,
                                [value.stage_by_name[name]["directory"] for name in DRIVER.MATRIX],
                                matrix, "--matrix")
    commands.append(("matrix", "primary_phase3", argv))
    records = [{"kind": "execution_binding_verified", "binding_sha256": value.binding_sha}]
    for index, (stage, role, argv) in enumerate(commands):
        out = write(value.assets / f"fixture_{index}.stdout.json", {"mock": True})
        err = write(value.assets / f"fixture_{index}.stderr.json", {})
        records.extend(({"kind": "command_started", "stage": stage, "role": role,
                         "argv": argv, "stdout": str(out), "stderr": str(err),
                         "binding_sha256": value.binding_sha},
                        {"kind": "command_complete", "stage": stage, "role": role,
                         "returncode": 0, "stdout_sha256": BASE.digest(out),
                         "stderr_sha256": BASE.digest(err)}))
        if role == "scalar_v3":
            records.append({"kind": "stage_all_declared_gates_passed", "stage": stage})
    records.append({"kind": "all_eight_stages_and_declared_audits_complete",
                    "matrix_sha256": BASE.digest(matrix)})
    for index, row in enumerate(records):
        row.update(freeze=FREEZE, monotonic_ns=index + 1)
    path = value.assets / "v7_execution.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    return path, records


def ownership_fixture(value):
    stage = value.stage_by_name["pilot"]
    value.stages = [stage]
    directory = value.native / "pilot/worker0/episode001_open_101"
    transport = {"profile_sha256": value.profile_sha, "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp"}
    write(directory / "metadata.json", {"epoch": "owned", "freeze": FREEZE,
                                        "transport_environment": transport})
    write(directory / "supervisor_metadata.json", {
        "epoch": "owned", "worker_identity": {"pid": 900001, "start_ticks": 111}})
    receipt = {"epoch": "owned", "remaining_owned_processes": [], "remaining_owned_zombies": [],
               "owned_processes_seen": [{"pid": 900001, "start_ticks": 111}]}
    path = write(directory / "supervisor_shutdown.json", receipt)
    write(value.native / "clock/summary.json", {
        "freeze": FREEZE, "transport_environment": transport, "passed": True, "error": None,
        "server_returncode": 0, "stop_cli_returncode": 0,
        "server_pid": 900002, "helper_pid": 900003, "stop_cli_pid": 900004})
    value.assets.mkdir(parents=True, exist_ok=True)
    (value.assets / "v7_execution.jsonl").write_text(json.dumps({
        "kind": "command_complete", "stage": "pilot", "role": "native", "pid": 900005}) + "\n")
    return path, receipt


class IntegrityTests(unittest.TestCase):
    def test_source_requires_matching_git_blob_and_current_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            path = value.root / "runtime.py"
            path.write_bytes(b"fixed")
            expected = BASE.digest(path)
            with patch.object(SUBJECT.subprocess, "check_output", return_value=b"fixed"):
                result = value.verify_source("runtime.py", expected)
                self.assertTrue(result["current_bytes_checked"])
            value.git_hashes.clear()
            with patch.object(SUBJECT.subprocess, "check_output", return_value=b"other Git"):
                with self.assertRaisesRegex(ValueError, "Git source differs"):
                    value.verify_source("runtime.py", expected)
            value.git_hashes.clear()
            path.write_bytes(b"modified current")
            with patch.object(SUBJECT.subprocess, "check_output", return_value=b"fixed"):
                with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                    value.verify_source("runtime.py", expected)

    def test_final_editorial_markdown_uses_frozen_blob_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            (value.root / "contract.md").write_bytes(b"final status edit")
            expected = hashlib.sha256(b"frozen normative document").hexdigest()
            with patch.object(SUBJECT.subprocess, "check_output",
                              return_value=b"frozen normative document"):
                result = value.verify_source("contract.md", expected)
            self.assertFalse(result["current_bytes_checked"])

    def test_source_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            with self.assertRaisesRegex(ValueError, "escapes repository"):
                value.verify_source("../outside.py", "0" * 64)

    def test_legacy_verifier_is_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / SUBJECT.ASSETS / SUBJECT.LEGACY_NAME
            path.parent.mkdir(parents=True)
            path.write_text("raise AssertionError('do not import')\n")
            with self.assertRaisesRegex(ValueError, "immutable v6 verifier"):
                SUBJECT.load_legacy(root)

    def test_full_source_binding_composition_uses_only_isolated_frozen_source_fixture(self):
        binding = BASE.read_json(ROOT / SUBJECT.ASSETS / "predeclared_execution_binding_v7.json")
        checks = BASE.read_json(ROOT / DRIVER.FILES["implementation_checks"])
        phase = module("v7_integrity_phase_fixture", ROOT / DRIVER.FILES["phase_auditor"])
        paths = {item["path"] for item in [*binding["files"].values(),
                                           *binding["additional_files"],
                                           *checks["additional_files"]]}
        paths.update(checks["source_sha256"])
        paths.update(checks["documentation"]["file_sha256"])
        paths.update(phase.PINNED_RUNTIME)
        paths.update(phase.PINNED_DOCUMENTS)
        paths.update(SUBJECT.ASSETS + name for name in SUBJECT.PRIOR_FAILURES)
        blobs = {path: subprocess.check_output(
            ["git", "show", binding["freeze"] + ":" + path], cwd=ROOT) for path in paths}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path, payload in blobs.items():
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
            binding["freeze"] = FREEZE
            saved = write(root / SUBJECT.ASSETS / "fixture_binding.json", binding)
            value = SUBJECT.Verifier(root, FREEZE, saved)

            def fake_git(command, **kwargs):
                if command == ["git", "rev-parse", "HEAD"]:
                    return FREEZE + "\n"
                self.assertEqual(command[:2], ["git", "show"])
                self.assertTrue(command[2].startswith(FREEZE + ":"))
                return blobs[command[2].split(":", 1)[1]]

            with patch.object(SUBJECT.subprocess, "check_output", side_effect=fake_git), \
                    patch.object(SUBJECT.subprocess, "check_call", return_value=0):
                result = value.verify_sources()
            self.assertTrue(result["passed"])
            self.assertEqual(result["source_count"], len(checks["source_sha256"]))
            self.assertEqual(len(value.stages), 8)
            self.assertTrue(all(row["current_bytes_checked"] is False
                                for row in result["frozen_document_blobs"]))

    def test_scalar_receipt_coverage_cannot_drop_a_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            primary = episode()
            primary["protocol"]["command_time"]["bindings"][0]["receipt_kind"] = "action_rejected"
            top = {"episodes": [primary]}
            stage = value.stage_by_name["pilot"]
            scalar = {"freeze": FREEZE, "schema": "mr3-reward-scalar-audit-v3",
                      "reset_epoch_and_pid_unique": True, "passed_scalar_checks": True,
                      "episodes": [{"epoch": "fixture", "errors": [], "transitions": 1,
                                    "rejected_action_bindings": [{"command_id": 1}]}]}
            write(stage["scalar_output"], scalar)
            value.verify_scalar(stage, top)
            scalar["episodes"][0]["rejected_action_bindings"] = []
            write(stage["scalar_output"], scalar)
            with self.assertRaisesRegex(ValueError, "receipt coverage differs"):
                value.verify_scalar(stage, top)

    def test_phase_method_and_time_helper_identity_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            value.phase = SimpleNamespace(METHOD="phase-method", BASE_SHA256="base-sha",
                                          COMMAND_SHA256="time-sha")
            value.binding = {"files": {"phase_auditor": {"sha256": "phase-sha"}}}
            value.phase_proof = {"source.py": {"sha256": "source-sha"}}
            proof = {"freeze": FREEZE, "method": "phase-method", "wrapper_sha256": "phase-sha",
                     "only_overridden_functions": ["audit_contacts", "audit_protocol"],
                     "original_results_modified": False,
                     "base_v2": {"sha256": "base-sha", "contact_logic_modified": False},
                     "command_time_gate": {"sha256": "time-sha"},
                     "frozen_sources": value.phase_proof}
            row = {"schema": "mr3-p1c-contact-phase-audit-v3", "passed": True,
                   "errors": [], "offline_contact_phase_audit": proof}
            value.verify_method(row)
            proof["command_time_gate"]["sha256"] = "some-other-helper"
            with self.assertRaisesRegex(ValueError, "method/helper binding differs"):
                value.verify_method(row)

    def test_complete_manifest_hashes_raw_compressed_and_decoded_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            manifest_fixture(value)
            result = value.verify_manifests()
            self.assertTrue(result["passed"])
            self.assertTrue(result["decoded_hashes_verified"])

    def test_raw_and_selected_tampering_are_detected(self):
        for target in ("raw", "selected"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                value = fixture(Path(temporary))
                _, raw, selected, _ = manifest_fixture(value)
                path = raw if target == "raw" else selected
                path.write_bytes(path.read_bytes() + b"changed")
                with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                    value.verify_manifests()

    def test_rehashed_compressed_payload_still_requires_original_decoded_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            path, _, selected, payload = manifest_fixture(value)
            with gzip.open(selected, "wb") as stream:
                stream.write(b"wrong decoded body")
            payload["files"][0].update(selected_sha256=BASE.digest(selected),
                                       selected_bytes=selected.stat().st_size)
            write(path, payload)
            with self.assertRaisesRegex(ValueError, "decoded evidence bytes differ"):
                value.verify_manifests()

    def test_manifest_cannot_relabel_old_freeze_or_original_root(self):
        for key, changed in (("source_freeze", "b" * 40), ("original_root", "another/raw/run")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                value = fixture(Path(temporary))
                path, _, _, payload = manifest_fixture(value)
                payload[key] = changed
                write(path, payload)
                with self.assertRaises(ValueError):
                    value.verify_manifests()

    def test_missing_stage_or_episode_manifest_is_not_a_final_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            path, _, _, _ = manifest_fixture(value)
            path.unlink()
            with self.assertRaisesRegex(ValueError, "missing or unexpected"):
                value.verify_manifests()

    def test_normal_and_fault_credits_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            value.verify_episode_audit(episode())
            value.verify_episode_audit(episode(fault=True), True)
            for key in ("complete_episode_credit", "expected_infrastructure_fault"):
                tampered = episode(fault=True)
                tampered[key] = not tampered[key]
                with self.assertRaisesRegex(ValueError, "scope differs"):
                    value.verify_episode_audit(tampered, True)

    def test_prefix_never_gets_contact_or_ordered_shutdown_credit(self):
        for changed in ("contacts", "ordered"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                value = fixture(Path(temporary))
                row = episode(fault=True)
                if changed == "contacts":
                    row["contacts"] = {"passed": True}
                else:
                    row["ordered_shutdown"]["proven"] = True
                with self.assertRaises(ValueError):
                    value.verify_episode_audit(row, True)

    def test_malformed_boolean_credit_cannot_pass_identity_checks(self):
        for invalid in (None, 0, 1, "true"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                value = fixture(Path(temporary))
                row = episode()
                row["complete_episode_credit"] = invalid
                with self.assertRaisesRegex(ValueError, "scope differs"):
                    value.verify_episode_audit(row)

    def test_command_time_failure_or_missing_receipt_coverage_fails(self):
        for key, changed in (("passed", False), ("errors", ["false TTL rejection"]),
                             ("commands_checked", 2), ("bindings", [])):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                value = fixture(Path(temporary))
                row = episode()
                row["protocol"]["command_time"][key] = changed
                with self.assertRaisesRegex(ValueError, "command-time gate"):
                    value.verify_episode_audit(row)

    def test_complete_journal_contains_24_ordered_successful_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            journal_fixture(value)
            result = value.verify_journal()
            self.assertEqual(len(result["commands"]), 24)
            self.assertTrue(result["all_eight_stages_completed"])

    def test_journal_rejects_failed_missing_reordered_or_other_binding_commands(self):
        for change in ("failed", "missing", "reordered", "binding", "deadline"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                value = fixture(Path(temporary))
                path, records = journal_fixture(value)
                if change == "failed":
                    completed = next(row for row in records if row["kind"] == "command_complete")
                    completed["returncode"] = 1
                elif change == "missing":
                    records = [row for row in records if row["kind"] != "command_complete"]
                elif change == "reordered":
                    records[1], records[2] = records[2], records[1]
                elif change == "binding":
                    records[1]["binding_sha256"] = "other binding"
                else:
                    records = [row for row in records if row.get("stage") != "deadline"]
                path.write_text("".join(json.dumps(row) + "\n" for row in records))
                with self.assertRaises(ValueError):
                    value.verify_journal()

    def test_execution_stdout_hash_is_rechecked(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            _, records = journal_fixture(value)
            Path(records[1]["stdout"]).write_text("tampered audit output")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                value.verify_journal()

    def test_absent_saved_identities_pass_and_different_start_ticks_are_pid_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            ownership_fixture(value)
            with patch.object(BASE, "proc_identity", return_value=None):
                self.assertTrue(value.verify_owned_identities()["passed"])
            with patch.object(BASE, "proc_identity", side_effect=lambda pid:
                              {"state": "S", "start_ticks": 222} if pid == 900001 else None):
                self.assertTrue(value.verify_owned_identities()["passed"])

    def test_same_owned_identity_or_zombie_fails(self):
        for state in ("S", "Z"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                value = fixture(Path(temporary))
                ownership_fixture(value)
                with patch.object(BASE, "proc_identity", side_effect=lambda pid:
                                  {"state": state, "start_ticks": 111} if pid == 900001 else None):
                    result = value.verify_owned_identities()
                self.assertFalse(result["passed"])
                self.assertEqual(result["violations"][0]["pid"], 900001)

    def test_bare_clock_pid_cannot_get_a_fabricated_historical_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            ownership_fixture(value)
            with patch.object(BASE, "proc_identity", side_effect=lambda pid:
                              {"state": "S", "start_ticks": 999} if pid == 900002 else None):
                result = value.verify_owned_identities()
            self.assertFalse(result["passed"])
            self.assertIsNone(result["violations"][0]["recorded_start_ticks"])

    def test_recorded_popen_child_pid_is_checked_without_fabricating_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            ownership_fixture(value)
            with patch.object(BASE, "proc_identity", side_effect=lambda pid:
                              {"state": "S", "start_ticks": 999} if pid == 900005 else None):
                result = value.verify_owned_identities()
            self.assertFalse(result["passed"])
            row = result["violations"][0]
            self.assertIsNone(row["recorded_start_ticks"])
            self.assertIn("lacks historical identity", row["ambiguity"])

    def test_nonempty_saved_zombies_fails_before_proc_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = fixture(Path(temporary))
            path, receipt = ownership_fixture(value)
            receipt["remaining_owned_zombies"] = [{"pid": 900001}]
            write(path, receipt)
            with self.assertRaisesRegex(ValueError, "cleanup not empty"):
                value.verify_owned_identities()

    def test_existing_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "saved.json"
            output.write_text("immutable")
            with self.assertRaises(SystemExit):
                SUBJECT.main(["--freeze", FREEZE, "--binding", "unused.json",
                              "--output", str(output)])
            self.assertEqual(output.read_text(), "immutable")


if __name__ == "__main__":
    unittest.main()
