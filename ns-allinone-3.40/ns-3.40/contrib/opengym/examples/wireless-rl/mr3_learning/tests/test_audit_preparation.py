"""Synthetic received-input archives exercise the actual offline consumer."""

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning.audit_preparation import audit_archives


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


if __name__ == "__main__":
    unittest.main()
