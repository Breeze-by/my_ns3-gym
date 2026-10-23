"""Independent archive reconstruction rejects self-consistent forged nav bytes."""

import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning.audit_preparation import audit_archives
from mr3_learning.navigation_archive import COMPOSITION_VERSION, reconstruct_navigation_payload


def canonical(value):
    return json.dumps(value, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode()


def payload(cells, width=2, origin=0., stamp=1):
    return {
        "header": {"frame_id": "map", "stamp": {"sec": stamp, "nanosec": 0}},
        "info": {"map_load_time": {"sec": stamp, "nanosec": 0},
                 "width": width, "height": len(cells) // width, "resolution": 1.,
                 "origin": {"position": {"x": origin, "y": 0., "z": 0.},
                            "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}}},
        "data": cells,
    }


def write_fixture(directory, mutation=None):
    archive = directory / "observation_inputs"
    (archive / "maps").mkdir(parents=True)
    (archive / "snapshots").mkdir()
    own, shared = payload([0, 100, -1, -1]), payload([100, 0, 100, -1], stamp=2)
    navigation = payload([0, 100, 100, -1], stamp=2)
    if mutation == "own_occupied_cleared":
        navigation["data"][1] = 0
    elif mutation == "both_unknown_filled":
        navigation["data"][3] = 0
    elif mutation == "own_free_lost":
        navigation["data"][0] = 100
    entries = {}
    messages = {"fused": shared, **dict.fromkeys(("tb1", "tb2", "tb3"), own),
                **dict.fromkeys(("navigation:tb1", "navigation:tb2", "navigation:tb3"),
                                navigation)}
    for name, message in messages.items():
        raw = canonical(message)
        digest = hashlib.sha256(raw).hexdigest()
        artifact = f"maps/{digest}.json.gz"
        (archive / artifact).write_bytes(gzip.compress(raw, mtime=0))
        entries[name] = {"payload_sha256": digest, "artifact": artifact}
    sources, nav_sources, paths = {}, {}, {}
    for name in ("tb1", "tb2", "tb3"):
        sources[name] = {"payload_sha256": entries[name]["payload_sha256"]}
        nav_sources[name] = {
            "epoch": "received-fixture", "sequence": 7, "version": 7,
            "source_stamp": 1., "received_stamp": 2.,
            "received_stamp_scope": "shared_map_delivery_used_by_navigation",
            "composition_version": COMPOSITION_VERSION, "shared_map_version": 7,
            "input_own_source_stamp": 1.,
            "input_own_map_payload_sha256": entries[name]["payload_sha256"],
            "input_shared_map_payload_sha256": entries["fused"]["payload_sha256"],
            "payload_sha256": entries["navigation:" + name]["payload_sha256"],
        }
        paths[name] = {**nav_sources[name], "source": "delivered_navigation_map",
                       "native_shape": [2, 2], "native_resolution_m": 1.,
                       "native_origin_m": [0., 0.]}
    snapshot = {
        "epoch": "received-fixture", "sequence": 8, "source_stamp": 3.,
        "candidate_version": "test-v5", "digest": "snapshot-digest", "map_version": 7,
        "map": {"sources": sources, "source_stamp": 1., "received_stamp": 2.,
                "native_shape": [2, 2], "native_resolution_m": 1.,
                "native_origin_m": [0., 0.]}, "path_maps": paths,
        "candidate_rule": {"navigation_composition": COMPOSITION_VERSION},
        "navigation_sources": nav_sources,
    }
    metadata = {
        "epoch": snapshot["epoch"], "map_version": 7, "map_sources": sources,
        "map_source_stamp": 1., "map_received_stamp": 2.,
        "map_payload_sha256": entries["fused"]["payload_sha256"],
        "navigation_composition": {"version": COMPOSITION_VERSION},
        "navigation_sources": nav_sources,
    }
    manifest = {
        "schema": "mr3-observation-input-archive-v2", "scope": "encoder_result_before_publication",
        "epoch": snapshot["epoch"], "sequence": 8, "source_stamp": 3.,
        "candidate_version": snapshot["candidate_version"],
        "snapshot_digest": snapshot["digest"], "metadata": metadata, "maps": entries,
    }
    row = {"snapshot": snapshot, "info": {"watermarks": {
        "map_payload_sha256": metadata["map_payload_sha256"], "navigation_sources": nav_sources}}}
    return archive, manifest, row


def save_fixture(directory, manifest, row):
    path = directory / "observation_inputs/snapshots/00000008_snapshot-digest.json"
    path.write_bytes(canonical(manifest))
    (directory / "transitions.jsonl").write_bytes(canonical(row) + b"\n")


class NavigationArchiveTests(unittest.TestCase):
    def test_owner_known_shared_unknown_and_header_are_rebuilt(self):
        own, shared = payload([0, 100, -1, -1]), payload([100, 0, 100, -1], stamp=2)
        before = copy.deepcopy((own, shared))
        self.assertEqual(reconstruct_navigation_payload(own, shared),
                         payload([0, 100, 100, -1], stamp=2))
        self.assertEqual((own, shared), before)

    def test_fractional_overlap_requires_full_free_and_preserves_own_obstacle(self):
        own = payload([100, 0, 0], width=3, origin=.4)
        shared = payload([0, 100, 100, 100], width=4, stamp=2)
        self.assertEqual(reconstruct_navigation_payload(own, shared),
                         payload([100, 100, 0, 100], width=4, stamp=2))

    def test_seven_roles_deduplicate_and_receipt_excludes_full_arrays(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, manifest, row = write_fixture(directory)
            save_fixture(directory, manifest, row)
            result = audit_archives(directory)
            self.assertTrue(result["passed"])
            self.assertEqual(result["unique_maps"], 3)
            self.assertEqual(len(result["navigation_reconstructions"]), 1)
            self.assertNotIn('"data"', json.dumps(result))

    def test_self_consistent_forged_nav_hashes_cannot_replace_independent_rebuild(self):
        for mutation in ("own_occupied_cleared", "both_unknown_filled", "own_free_lost"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                _, manifest, row = write_fixture(directory, mutation)
                save_fixture(directory, manifest, row)
                with self.assertRaisesRegex(ValueError, "independent owner-authority"):
                    audit_archives(directory)

    def test_roles_input_identities_actual_path_source_and_geometry_are_required(self):
        for mutation in ("missing_role", "extra_role", "own_sha", "shared_sha", "path_source",
                         "path_geometry", "raw_geometry", "unknown_composition"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                archive, manifest, row = write_fixture(directory)
                source = manifest["metadata"]["navigation_sources"]["tb1"]
                if mutation == "missing_role":
                    manifest["maps"].pop("tb3")
                elif mutation == "extra_role":
                    manifest["maps"]["truth"] = manifest["maps"]["fused"]
                elif mutation in ("own_sha", "shared_sha"):
                    key = "input_" + ("own" if mutation == "own_sha" else "shared")
                    source[key + "_map_payload_sha256"] = "0" * 64
                elif mutation == "path_source":
                    row["snapshot"]["path_maps"]["tb1"]["source"] = "delivered_own_map"
                elif mutation == "path_geometry":
                    row["snapshot"]["path_maps"]["tb1"]["native_shape"] = [1, 4]
                elif mutation == "unknown_composition":
                    manifest["metadata"]["navigation_composition"]["version"] = "unknown"
                else:
                    entry = manifest["maps"]["tb1"]
                    raw = gzip.decompress((archive / entry["artifact"]).read_bytes())
                    invalid = json.loads(raw)
                    invalid["info"]["origin"]["orientation"]["z"] = .5
                    raw = canonical(invalid)
                    digest = hashlib.sha256(raw).hexdigest()
                    for name in ("tb1", "tb2", "tb3"):
                        manifest["maps"][name] = {
                            "payload_sha256": digest, "artifact": f"maps/{digest}.json.gz"}
                        manifest["metadata"]["map_sources"][name]["payload_sha256"] = digest
                        source = manifest["metadata"]["navigation_sources"][name]
                        source["input_own_map_payload_sha256"] = digest
                        row["snapshot"]["path_maps"][name]["input_own_map_payload_sha256"] = digest
                    (archive / f"maps/{digest}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
                save_fixture(directory, manifest, row)
                with self.assertRaises(ValueError):
                    audit_archives(directory)


if __name__ == "__main__":
    unittest.main()
