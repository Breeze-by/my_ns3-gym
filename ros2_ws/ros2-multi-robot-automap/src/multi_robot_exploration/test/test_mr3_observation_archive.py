"""Exact frozen-map provenance, content identity and optional audit persistence."""

import copy
import gzip
import hashlib
import json

import pytest

from multi_robot_exploration.mr3_observation import snapshot_digest
from multi_robot_exploration.mr3_observation_archive import archive_snapshot_inputs


def inputs(sequence=1):
    payload = {
        "header": {"frame_id": "map", "stamp": {"sec": 10, "nanosec": 0}},
        "info": {"resolution": .1, "width": 2, "height": 2,
                 "map_load_time": {"sec": 0, "nanosec": 0},
                 "origin": {"position": {"x": -1., "y": -1., "z": 0.},
                            "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}}},
        "data": [0, 0, -1, 100],
    }
    raw = json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    sources = {name: {"epoch": "episode-a", "sequence": 7, "version": 4,
                      "source_stamp": 9., "received_stamp": 9.8, "payload_sha256": digest}
               for name in ("tb1", "tb2", "tb3")}
    metadata = {"epoch": "episode-a", "map_version": 8, "map_payload_sha256": digest,
                "map_source_stamp": 9., "map_received_stamp": 9.8, "map_sources": sources}
    snapshot = {
        "epoch": "episode-a", "sequence": sequence, "source_stamp": 10., "map_version": 8,
        "candidate_version": "frozen-candidate-version",
        "map": {"source_stamp": 9., "received_stamp": 9.8, "sources": copy.deepcopy(sources)},
        "path_maps": {name: {"payload_sha256": digest} for name in sources},
    }
    snapshot["digest"] = snapshot_digest(snapshot)
    return snapshot, {name: copy.deepcopy(payload) for name in ("fused", *sources)}, metadata


def test_canonical_map_digest_and_repeated_payload_deduplication(tmp_path):
    snapshot, payloads, metadata = inputs()
    original = copy.deepcopy(snapshot)
    archive_snapshot_inputs(tmp_path, snapshot, payloads, metadata)
    blobs = list((tmp_path / "maps").iterdir())
    assert len(blobs) == 1  # All four roles bind the same full payload.
    raw = gzip.decompress(blobs[0].read_bytes())
    assert hashlib.sha256(raw).hexdigest() == metadata["map_payload_sha256"]
    assert json.loads(raw) == payloads["fused"]
    first_bytes = blobs[0].read_bytes()
    first_mtime = blobs[0].stat().st_mtime_ns
    archive_snapshot_inputs(tmp_path, snapshot, payloads, metadata)
    next_snapshot, _, _ = inputs(sequence=2)
    archive_snapshot_inputs(tmp_path, next_snapshot, payloads, metadata)
    assert list((tmp_path / "maps").iterdir()) == blobs
    assert blobs[0].read_bytes() == first_bytes
    assert blobs[0].stat().st_mtime_ns == first_mtime
    assert len(list((tmp_path / "snapshots").iterdir())) == 2
    manifest = json.loads(next((tmp_path / "snapshots").iterdir()).read_bytes())
    assert manifest["epoch"] == snapshot["epoch"]
    assert manifest["snapshot_digest"] == snapshot["digest"]
    assert manifest["metadata"] == metadata
    assert set(manifest["maps"]) == {"fused", "tb1", "tb2", "tb3"}
    assert snapshot == original


@pytest.mark.parametrize("corrupt", ["payload", "snapshot", "metadata", "own_identity"])
def test_mismatched_inputs_fail_before_any_archive_is_created(tmp_path, corrupt):
    snapshot, payloads, metadata = inputs()
    if corrupt == "payload":
        payloads["tb2"]["data"][0] = 100
    elif corrupt == "snapshot":
        snapshot["sequence"] += 1
    elif corrupt == "metadata":
        metadata["map_sources"]["tb2"]["version"] += 1
    else:
        snapshot["path_maps"]["tb2"]["payload_sha256"] = "0" * 64
        snapshot["digest"] = snapshot_digest(snapshot)
    root = tmp_path / "archive"
    with pytest.raises(ValueError, match="archive"):
        archive_snapshot_inputs(root, snapshot, payloads, metadata)
    assert not root.exists()


def test_existing_blob_corruption_is_rejected_instead_of_silently_reused(tmp_path):
    snapshot, payloads, metadata = inputs()
    archive_snapshot_inputs(tmp_path, snapshot, payloads, metadata)
    blob = next((tmp_path / "maps").iterdir())
    blob.write_bytes(gzip.compress(b"different payload", mtime=0))
    with pytest.raises(ValueError, match="existing blob"):
        archive_snapshot_inputs(tmp_path, snapshot, payloads, metadata)


def test_no_audit_root_performs_no_validation_or_filesystem_access(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("disabled archive touched the filesystem")

    monkeypatch.setattr("pathlib.Path.mkdir", unexpected)
    archive_snapshot_inputs(None, None, None, None)
    archive_snapshot_inputs("", None, None, None)


def test_v2_archives_seven_actual_navigation_roles_and_binds_their_source_metadata(tmp_path):
    snapshot, payloads, metadata = inputs()
    navigation = {name: {
        "epoch": snapshot["epoch"], "sequence": 1, "version": 1,
        "payload_sha256": metadata["map_payload_sha256"],
        "composition_version": "mr3-own-known-shared-unknown-v1"}
                  for name in ("tb1", "tb2", "tb3")}
    metadata["navigation_sources"] = copy.deepcopy(navigation)
    metadata["navigation_composition"] = {"version": "mr3-own-known-shared-unknown-v1"}
    snapshot["navigation_sources"] = copy.deepcopy(navigation)
    snapshot["candidate_rule"] = {"navigation_composition": "mr3-own-known-shared-unknown-v1"}
    snapshot["digest"] = snapshot_digest(snapshot)
    for name in navigation:
        payloads["navigation:" + name] = copy.deepcopy(payloads[name])
    archive_snapshot_inputs(tmp_path, snapshot, payloads, metadata)
    manifest = json.loads(next((tmp_path / "snapshots").iterdir()).read_bytes())
    assert manifest["schema"] == "mr3-observation-input-archive-v2"
    assert len(manifest["maps"]) == 7
    assert len(list((tmp_path / "maps").iterdir())) == 1
    payloads["navigation:tb2"]["data"][0] = 100
    with pytest.raises(ValueError, match="payload digest"):
        archive_snapshot_inputs(tmp_path, snapshot, payloads, metadata)
