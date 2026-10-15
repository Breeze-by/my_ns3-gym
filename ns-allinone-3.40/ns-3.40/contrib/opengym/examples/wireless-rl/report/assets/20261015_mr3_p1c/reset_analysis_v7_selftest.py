"""Synthetic v7 binding/orchestration checks; never analyse native directories."""

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
SPEC = importlib.util.spec_from_file_location(
    "reset_v7_test_subject", HERE / "reset_analysis_v7.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
FREEZE = "a" * 40
CORE = R.load_core(ROOT, FREEZE)


def episode(identity, epoch, scene="open", worker=0):
    return {"directory": epoch, "epoch": epoch, "scene": scene,
            "seed": {"open": 101, "rooms": 202, "corridors": 303}[scene], "worker_id": worker,
            "processes": {"owned_pid_identities": [identity]},
            "configuration": {"semantic_input_sha256": "same-" + scene},
            "robots": {name: {"x": 0., "y": 0., "yaw": 0.} for name in CORE.ROBOTS},
            "map_payload_sha256": "map", "map_sources": {
                name: {"payload_sha256": "map"} for name in CORE.ROBOTS},
            "path_maps": {name: {"geometry_sha256": "geometry"} for name in CORE.ROBOTS}}


class ResetV7Tests(unittest.TestCase):
    def test_immutable_v6_core_and_new_phase_hashes_are_fixed(self):
        self.assertEqual(hashlib.sha256((HERE / R.CORE_NAME).read_bytes()).hexdigest(), R.CORE_SHA)
        self.assertEqual(hashlib.sha256((HERE / R.PHASE_NAME).read_bytes()).hexdigest(),
                         R.PHASE_SHA)

    def test_freeze_and_lock_hash_are_explicit_exact_identifiers(self):
        for value in (None, "HEAD", "", "A" * 40, "a" * 39):
            with self.subTest(value=value), self.assertRaises(ValueError):
                R.exact_hex(value, 40, "source freeze")
        with self.assertRaises(ValueError):
            R.exact_hex("a" * 63, 64, "implementation SHA")
        with self.assertRaises(SystemExit):
            R.main(["--output", "never-created.json"])

    def catalogue(self, mutate=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            source.write_bytes(b"fixed source")
            lock = {"schema": "mr3-p1c-implementation-checks-v7",
                    "source_sha256": {"source.py": R.sha(source.read_bytes())}}
            checks = root / "checks.json"
            checks.write_text(json.dumps(lock))
            payload = checks.read_bytes()
            expected = R.sha(payload)
            git = {"checks.json": payload, "source.py": source.read_bytes()}
            if mutate:
                expected = mutate(root, checks, source, git, expected)

            def read(command, **kwargs):
                self.assertEqual(command[:2], ["git", "show"])
                self.assertTrue(command[2].startswith(FREEZE + ":"))
                return git[command[2].split(":", 1)[1]]

            with patch.object(R, "extra_inputs", return_value=[]), patch.object(
                    R.subprocess, "check_output", side_effect=read):
                return R.frozen_catalogue(CORE, root, FREEZE, checks, expected)

    def test_lock_git_blob_and_current_source_bytes_all_match(self):
        blobs, proof, lock = self.catalogue()
        self.assertEqual(blobs, {"source.py": b"fixed source"})
        self.assertTrue(proof["source.py"]["current_bytes_match"])
        self.assertEqual(lock["source_count"], 1)
        self.assertTrue(lock["git_object"].startswith(FREEZE + ":"))

    def test_wrong_expected_lock_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "implementation lock changed"):
            self.catalogue(lambda *args: "0" * 64)

    def test_lock_git_blob_cannot_differ_from_supplied_pinned_file(self):
        def mutate(root, checks, source, git, expected):
            git["checks.json"] += b" "
            return expected
        with self.assertRaisesRegex(ValueError, "lock/Git freeze mismatch"):
            self.catalogue(mutate)

    def test_source_git_blob_cannot_differ_from_implementation_pin(self):
        def mutate(root, checks, source, git, expected):
            git["source.py"] = b"different Git source"
            return expected
        with self.assertRaisesRegex(ValueError, "frozen lock/blob mismatch"):
            self.catalogue(mutate)

    def test_matching_git_and_lock_do_not_hide_changed_running_source(self):
        def mutate(root, checks, source, git, expected):
            source.write_bytes(b"changed running source")
            return expected
        with self.assertRaisesRegex(ValueError, "current input/source changed"):
            self.catalogue(mutate)

    def test_old_lock_schema_is_rejected_even_with_matching_new_external_hash(self):
        def mutate(root, checks, source, git, expected):
            lock = json.loads(checks.read_text())
            lock["schema"] = "mr3-p1c-implementation-checks-v6"
            checks.write_text(json.dumps(lock))
            git["checks.json"] = checks.read_bytes()
            return R.sha(checks.read_bytes())
        with self.assertRaisesRegex(ValueError, "invalid v7 implementation"):
            self.catalogue(mutate)

    def test_reused_pair_logic_preserves_full_pid_identity_and_config_rules(self):
        left, right = episode([123, 100], "old"), episode([123, 200], "new")
        self.assertTrue(CORE.pair(left, right)["new_epoch_and_disjoint_saved_process_identities"])
        right["processes"]["owned_pid_identities"] = [[123, 100]]
        with self.assertRaisesRegex(ValueError, "identity reused"):
            CORE.pair(left, right)
        right["processes"]["owned_pid_identities"] = [[123, 200]]
        right["configuration"]["semantic_input_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            CORE.pair(left, right)
        self.assertFalse(CORE.pair(left, right, False)["same_seed_comparison"])

    def test_new_phase_loader_receives_same_exact_freeze_and_returns_inherited_context(self):
        base, audit, proof = object(), object(), {"pinned": True}

        def components(freeze, root):
            self.assertEqual(freeze, FREEZE)
            self.assertEqual(root, ROOT)
            return base, audit, object(), proof

        phase = SimpleNamespace(COMMAND_SHA256=R.COMMAND_SHA, load_components=components)
        with patch.object(R, "load_pinned", return_value=phase):
            result = R.load_phase(ROOT, FREEZE)
        self.assertEqual(result, (base, audit, proof))

    def test_primary_link_requires_new_schema_freeze_phase_and_command_gate(self):
        original = {"schema": "mr3-p1c-contact-phase-audit-v3", "passed": True,
                    "freeze": FREEZE, "offline_contact_phase_audit": {
                        "freeze": FREEZE, "wrapper_sha256": R.PHASE_SHA,
                        "command_time_gate": {"sha256": R.COMMAND_SHA},
                        "only_overridden_functions": ["audit_contacts", "audit_protocol"],
                        "original_results_modified": False}}
        for key in (None, "schema", "passed", "freeze", "wrapper", "command", "overrides"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = root / R.ASSETS / "workers2_v7_contact_phase_v3_benchmark_audit.json"
                path.parent.mkdir(parents=True)
                payload = copy.deepcopy(original)
                if key in ("schema", "freeze"):
                    payload[key] = "old"
                elif key == "passed":
                    payload[key] = False
                elif key == "wrapper":
                    payload["offline_contact_phase_audit"]["wrapper_sha256"] = "old"
                elif key == "command":
                    payload["offline_contact_phase_audit"]["command_time_gate"]["sha256"] = "old"
                elif key == "overrides":
                    payload["offline_contact_phase_audit"]["only_overridden_functions"] = []
                path.write_text(json.dumps(payload))
                if key:
                    with self.assertRaisesRegex(ValueError, "phase3/command-time"):
                        R.primary_audit_link(CORE, root, 2, FREEZE)
                else:
                    self.assertEqual(R.primary_audit_link(CORE, root, 2, FREEZE)["sha256"],
                                     R.sha(path.read_bytes()))

    def synthetic_matrix(self, fault=None):
        records = {}

        class Reader:
            def __init__(self, directory):
                self.directory, self.files = directory, {}

            def json(self, filename):
                workers = int(self.directory.name.removeprefix("workers"))
                schedule = [["open", 101], ["open", 101]]
                if workers == 1:
                    schedule += [["rooms", 202], ["corridors", 303]]
                if fault == "schedule":
                    schedule[0][1] = 999
                return {"workers": workers, "freeze": FREEZE, "schedule": schedule}

        def summarize(root, path, *args):
            worker = int(path.parent.name.removeprefix("worker"))
            scene = path.name.split("_")[1]
            number = len(records) + 1
            row = episode([number, 100], "epoch" + str(number), scene, worker)
            if fault == "identity" and number == 2:
                row["processes"]["owned_pid_identities"] = [[1, 100]]
            if fault == "epoch" and number == 2:
                row["epoch"] = "epoch1"
            records[number] = row
            return row

        core = SimpleNamespace(Reader=Reader, summarize_episode=summarize, pair=CORE.pair,
                               INITIALIZATION_SCOPE=CORE.INITIALIZATION_SCOPE)
        with patch.object(R, "load_core", return_value=core), patch.object(
                R, "frozen_catalogue", return_value=({}, {}, {})), patch.object(
                R, "load_phase", return_value=(object(), object(), {})), patch.object(
                R, "primary_audit_link", return_value={}):
            return R.analyse(ROOT, Path("synthetic-v7"), FREEZE, Path("checks.json"), "b" * 64)

    def test_normal_matrix_preserves16_cells7_pairs2_cross_scene_and91_open_pairs(self):
        result = self.synthetic_matrix()
        self.assertTrue(result["passed"])
        self.assertEqual(result["observed_cells"], 16)
        self.assertEqual(len(result["same_seed_pairs"]), 7)
        self.assertEqual(len(result["cross_scene_isolation"]), 2)
        self.assertEqual(result["all_open101_pairwise_maxima"]["pair_count"], 91)
        self.assertFalse(result["current_proc_snapshot_performed"])

    def test_matrix_identity_or_epoch_reuse_is_failure_not_discarded(self):
        for fault in ("identity", "epoch"):
            with self.subTest(fault=fault):
                result = self.synthetic_matrix(fault)
                self.assertFalse(result["passed"])
                self.assertTrue(result["errors"])

    def test_matrix_schedule_cannot_silently_change(self):
        with self.assertRaisesRegex(ValueError, "schedule changed"):
            self.synthetic_matrix("schedule")

    def test_cli_defaults_only_to_v7_and_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            argv = ["--freeze", FREEZE, "--implementation-checks", "checks.json",
                    "--implementation-checks-sha256", "b" * 64, "--output", str(output)]
            with patch.object(R, "analyse", return_value={"passed": True, "errors": []}) as run:
                self.assertEqual(R.main(argv), 0)
                self.assertEqual(run.call_args.args[1], ROOT / R.ASSETS / "native_v7")
                self.assertEqual(run.call_args.args[2:],
                                 (FREEZE, Path("checks.json"), "b" * 64))
            saved = output.read_bytes()
            with self.assertRaises(SystemExit):
                R.main(argv)
            self.assertEqual(output.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
