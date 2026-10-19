"""Synthetic received-input archives exercise the actual offline consumer."""

import gzip
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
from types import SimpleNamespace

from mr3_learning.audit_preparation import (
    audit_archives, audit_execution_inputs, controlled_bootstrap, dispatch_controlled_physics,
)
from mr3_learning.audit_motion import _audit_records
from mr3_learning.audit_ppo import TASK_BASE_FREEZE, require
from mr3_learning.tests.test_audit_motion import (
    helper_module, write_controlled_fixture, write_files,
)


def canonical(value):
    return json.dumps(value, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode()


def write_fixture(directory):
    """Write four tiny received payloads and two distinct actor manifests."""
    archive = directory / "observation_inputs"
    (archive / "maps").mkdir(parents=True)
    (archive / "snapshots").mkdir()
    entries, geometries, payload_paths = {}, {}, {}
    for index, name in enumerate(("fused", "tb1", "tb2", "tb3")):
        info = {"height": 2, "width": 2, "resolution": .05,
                "origin": {"position": {"x": float(index), "y": 0.}}}
        raw = canonical({"info": info, "data": [0, 100, -1, index]})
        digest = hashlib.sha256(raw).hexdigest()
        relative = f"maps/{digest}.json.gz"
        payload_paths[name] = archive / relative
        payload_paths[name].write_bytes(gzip.compress(raw, mtime=0))
        entries[name] = {"payload_sha256": digest, "artifact": relative}
        geometries[name] = {"native_shape": [2, 2], "native_resolution_m": .05,
                            "native_origin_m": [float(index), 0.],
                            "payload_sha256": digest}
    transitions, manifests = [], []
    for sequence in (1, 2):
        snapshot = {"epoch": "fixture-episode", "sequence": sequence,
                    "source_stamp": float(sequence), "candidate_version": f"c{sequence}",
                    "map_version": sequence,
                    "map": {**geometries["fused"], "sources": ["tb1", "tb2", "tb3"],
                            "source_stamp": 1., "received_stamp": 1.},
                    "path_maps": {name: geometries[name] for name in ("tb1", "tb2", "tb3")}}
        snapshot["digest"] = hashlib.sha256(canonical(snapshot)).hexdigest()
        metadata = {"epoch": snapshot["epoch"], "map_version": sequence,
                    "map_sources": snapshot["map"]["sources"], "map_source_stamp": 1.,
                    "map_received_stamp": 1.,
                    "map_payload_sha256": entries["fused"]["payload_sha256"]}
        manifest = {"schema": "mr3-observation-input-archive-v1",
                    "scope": "encoder_result_before_publication", "epoch": snapshot["epoch"],
                    "sequence": sequence, "source_stamp": snapshot["source_stamp"],
                    "candidate_version": snapshot["candidate_version"],
                    "snapshot_digest": snapshot["digest"], "metadata": metadata, "maps": entries}
        path = archive / "snapshots" / f"{sequence:08d}_{snapshot['digest']}.json"
        path.write_bytes(canonical(manifest))
        manifests.append(path)
        transitions.append({"kind": "reset" if sequence == 1 else "step",
                            "snapshot": snapshot,
                            "info": {"watermarks": {
                                "map_payload_sha256": metadata["map_payload_sha256"]}}})
    (directory / "transitions.jsonl").write_bytes(
        b"".join(canonical(row) + b"\n" for row in transitions))
    return manifests, payload_paths


class ReceivedArchiveTests(unittest.TestCase):
    def test_four_payloads_bind_two_snapshots_and_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, paths = write_fixture(directory)
            result = audit_archives(directory)
            self.assertTrue(result["passed"])
            self.assertEqual(result["unique_snapshots"], 2)
            self.assertEqual(result["unique_maps"], 4)
            for path in paths.values():
                compressed = path.read_bytes()
                raw = gzip.decompress(compressed)
                saved = result["maps"][hashlib.sha256(raw).hexdigest()]
                self.assertEqual(saved["decoded_bytes"], len(raw))
                self.assertEqual(saved["compressed_sha256"],
                                 hashlib.sha256(compressed).hexdigest())

    def test_modified_decoded_payload_and_noncanonical_raw_bytes_are_rejected(self):
        for corruption in ("data", "noncanonical", "broken_gzip"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                _, paths = write_fixture(directory)
                path = paths["tb2"]
                payload = json.loads(gzip.decompress(path.read_bytes()))
                if corruption == "data":
                    payload["data"][0] = 100
                    path.write_bytes(gzip.compress(canonical(payload), mtime=0))
                elif corruption == "noncanonical":
                    path.write_bytes(gzip.compress(json.dumps(payload, indent=2).encode(),
                                                   mtime=0))
                else:
                    path.write_bytes(b"not a gzip stream")
                with self.assertRaises((ValueError, gzip.BadGzipFile)):
                    audit_archives(directory)

    def test_snapshot_identity_and_map_metadata_must_match_actual_transition(self):
        mutations = ((None, "epoch", "old-episode"), (None, "sequence", 99),
                     (None, "candidate_version", "old-candidates"),
                     (None, "snapshot_digest", "old-snapshot"), (None, "source_stamp", 9.),
                     ("metadata", "epoch", "old-episode"), ("metadata", "map_version", 99),
                     ("metadata", "map_sources", ["tb1"]),
                     ("metadata", "map_source_stamp", 9.),
                     ("metadata", "map_received_stamp", 9.),
                     ("metadata", "map_payload_sha256", "0" * 64))
        for section, key, value in mutations:
            with self.subTest(section=section, field=key), \
                    tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                manifests, _ = write_fixture(directory)
                path = manifests[0]
                manifest = json.loads(path.read_text())
                target = manifest if section is None else manifest[section]
                target[key] = value
                path.write_bytes(canonical(manifest))
                with self.assertRaisesRegex(ValueError, "archive (snapshot|map metadata)"):
                    audit_archives(directory)

    def test_missing_transition_manifest_or_received_payload_is_rejected(self):
        for missing in ("transition", "manifest", "payload"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                manifests, paths = write_fixture(directory)
                path = (directory / "transitions.jsonl" if missing == "transition" else
                        manifests[0] if missing == "manifest" else paths["tb3"])
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    audit_archives(directory)


class ControlledPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = helper_module()
        root = Path(__file__).resolve().parents[8]
        relative = "ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py"
        raw = subprocess.check_output(["git", "show", TASK_BASE_FREEZE + ":" + relative], cwd=root)
        tree = ast.parse(raw)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "audit_physics")
        namespace = {"require": require}
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     TASK_BASE_FREEZE + ":" + relative, "exec"), namespace)
        cls.original_physics = staticmethod(namespace["audit_physics"])

    def setup_episode(self, root):
        directory = root / "worker0/episode001_open_101"
        directory.mkdir(parents=True)
        files = write_controlled_fixture(directory, self.helper)
        motion = _audit_records(directory, self.helper, {})
        return directory, files, motion

    def test_single_bootstrap_uses_original_integer_continuity_and_quantum_function(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory, files, motion = self.setup_episode(root)
            rows, epoch, release = (files["physics.jsonl"], files["metadata.json"]["epoch"],
                                    1_020_000_000)
            with self.assertRaisesRegex(ValueError, "warmup/quantum"):
                self.original_physics(rows, epoch, release)
            auditor = SimpleNamespace(audit_physics=self.original_physics)
            original = dispatch_controlled_physics(auditor, [root], {directory: motion})
            self.assertIs(original, self.original_physics)
            result = auditor.audit_physics(rows, epoch, release)
            self.assertEqual(result["total_physical_ticks"], 60)
            self.assertEqual(result["controlled_bootstrap"]["actual_task_release_time_ns"],
                             release)
            self.assertEqual(result["controlled_bootstrap"]["setup_to_controlled_time_ns"],
                             1_000_000_000)
            self.assertTrue(result["original_integer_continuity_quantum_math"])

    def test_bootstrap_native_storage_repetition_and_release_mutations_are_rejected(self):
        for mutation in ("repeated", "no_driver_status", "bool_storage", "wrong_release"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory, files, motion = self.setup_episode(Path(temporary))
                release = 1_020_000_000
                if mutation == "repeated":
                    files["drive_phase_worker.jsonl"].append(next(
                        row for row in files["drive_phase_worker.jsonl"]
                        if row.get("control_kind") == "bootstrap_zero"))
                elif mutation == "no_driver_status":
                    files["drive_tb1.jsonl"] = [row for row in files["drive_tb1.jsonl"]
                                                if row["kind"] != "status_publish"]
                elif mutation == "bool_storage":
                    row = next(row for row in files["drive_phase_worker.jsonl"]
                               if row.get("control_kind") == "bootstrap_zero")
                    row["receipts"]["tb1"]["cmd_seq"] = True
                else:
                    release += 20_000_000
                write_files(directory, files)
                if mutation in ("no_driver_status", "bool_storage"):
                    motion = _audit_records(directory, self.helper, {})
                with self.assertRaises(ValueError):
                    controlled_bootstrap(directory, files["physics.jsonl"],
                                         files["metadata.json"]["epoch"], release, motion)

    def test_legacy_protocol_retains_original_threshold_and_unknown_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory, files, _ = self.setup_episode(root)
            for protocol in (None, "unknown-controlled-protocol"):
                if protocol is None:
                    files["metadata.json"].pop("execution_phase_protocol")
                else:
                    files["metadata.json"]["execution_phase_protocol"] = protocol
                write_files(directory, files)
                auditor = SimpleNamespace(audit_physics=self.original_physics)
                dispatch_controlled_physics(auditor, [root], {})
                with self.assertRaises(ValueError):
                    auditor.audit_physics(files["physics.jsonl"],
                                          files["metadata.json"]["epoch"], 1_020_000_000)

    def test_stop_cleanup_coverage_requires_full_actual_motion_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory, files, motion = self.setup_episode(Path(temporary))
            payload = {"header": {"stamp": {"sec": 1, "nanosec": 0}, "frame_id": "map"},
                       "info": {"width": 1, "height": 1}, "data": [0]}
            raw = canonical(payload)
            digest = hashlib.sha256(raw).hexdigest()
            target = directory / "execution_inputs/maps" / (digest + ".json.gz")
            target.parent.mkdir(parents=True)
            target.write_bytes(gzip.compress(raw, mtime=0))
            files["costmaps.jsonl"] = [
                {"schema": "mr3-native-costmap-receipt-v1",
                 "epoch": files["metadata.json"]["epoch"],
                 "robot": name, "layer": layer, "payload_sha256": digest,
                 "topic": f"/{name}/{layer}_costmap/costmap",
                 "artifact": f"execution_inputs/maps/{digest}.json.gz",
                 "source_header": payload["header"], "received_clock_ns": 1_020_000_000}
                for name in ("tb1", "tb2", "tb3") for layer in ("global", "local")]
            write_files(directory, files)
            result = audit_execution_inputs(directory, motion)
            self.assertTrue(result["passed"])
            self.assertIn(1_060_000_000, result["controlled_execution_replay"]["stop_clocks"])
            # The same stopped cleanup cannot be laundered through a proof
            # captured before an actual local output FIFO mutation.
            row = next(row for row in files["motion_safety.jsonl"]
                       if row["kind"] == "actual_cmd_vel"
                       and row["payload"]["observed_decision_sequence"] == 5)
            row["payload"]["twist"]["linear"]["x"] = .01
            write_files(directory, files)
            with self.assertRaisesRegex(ValueError, "raw input changed"):
                audit_execution_inputs(directory, motion)


if __name__ == "__main__":
    unittest.main()
