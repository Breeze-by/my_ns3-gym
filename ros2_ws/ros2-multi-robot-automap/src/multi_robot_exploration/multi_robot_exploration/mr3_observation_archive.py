"""Exact received-map evidence for an encoded observation; no ROS/store reads."""

import gzip
import hashlib
import json
from pathlib import Path

from multi_robot_exploration.mr3_observation import ROBOT_NAMES, snapshot_digest


def archive_snapshot_inputs(root, snapshot, payloads, metadata):
    """Write four frozen map payloads and a manifest in the episode audit root.

    The canonical JSON is byte-identical to ``mr3_information.map_digest``.
    Everything is validated before writing; errors propagate to the encoder
    future and prevent publication of an observation with missing evidence.
    """
    if not root:
        return
    if snapshot_digest(snapshot) != snapshot["digest"]:
        raise ValueError("archive snapshot digest mismatch")
    if (metadata["epoch"] != snapshot["epoch"]
            or metadata["map_version"] != snapshot["map_version"]
            or metadata["map_sources"] != snapshot["map"]["sources"]
            or metadata["map_source_stamp"] != snapshot["map"]["source_stamp"]
            or metadata["map_received_stamp"] != snapshot["map"]["received_stamp"]):
        raise ValueError("archive metadata does not match frozen snapshot")
    if set(payloads) != {"fused", *ROBOT_NAMES}:
        raise ValueError("archive requires fused and three own-map payloads")
    encoded, maps = {}, {}
    for name in ("fused", *ROBOT_NAMES):
        raw = json.dumps(payloads[name], allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        expected = (metadata["map_payload_sha256"] if name == "fused"
                    else metadata["map_sources"][name]["payload_sha256"])
        if digest != expected:
            raise ValueError("archive map payload digest mismatch: " + name)
        if name != "fused" and snapshot["path_maps"][name]["payload_sha256"] != expected:
            raise ValueError("archive own-map identity differs from snapshot: " + name)
        encoded[digest] = raw
        maps[name] = {"payload_sha256": digest, "artifact": f"maps/{digest}.json.gz"}
    manifest = {
        "schema": "mr3-observation-input-archive-v1",
        "scope": "encoder_result_before_publication",
        "epoch": snapshot["epoch"], "sequence": snapshot["sequence"],
        "snapshot_digest": snapshot["digest"], "candidate_version": snapshot["candidate_version"],
        "source_stamp": snapshot["source_stamp"], "metadata": metadata, "maps": maps,
    }
    manifest_raw = json.dumps(manifest, allow_nan=False, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
    root = Path(root)
    (root / "maps").mkdir(parents=True, exist_ok=True)
    (root / "snapshots").mkdir(exist_ok=True)
    for digest, raw in encoded.items():
        path = root / "maps" / f"{digest}.json.gz"
        try:
            with path.open("xb") as stream:
                stream.write(gzip.compress(raw, mtime=0))
        except FileExistsError:
            if gzip.decompress(path.read_bytes()) != raw:
                raise ValueError("archive existing blob does not match its digest: " + digest)
    path = root / "snapshots" / f"{snapshot['sequence']:08d}_{snapshot['digest']}.json"
    try:
        with path.open("xb") as stream:
            stream.write(manifest_raw + b"\n")
    except FileExistsError:
        if path.read_bytes() != manifest_raw + b"\n":
            raise ValueError("archive conflicting snapshot manifest")
