"""Audit P2A.0 scripted engineering evidence; no policy or training credit."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

from .audit_ppo import load_native_gates, load_rows, require
from .audit_evaluator_phase import audit_episode as audit_phase


def audit_archives(directory):
    """Bind full received-map bytes to each actual saved actor snapshot."""
    root = directory / "observation_inputs"
    snapshots, blobs = set(), {}
    for row in load_rows(directory / "transitions.jsonl"):
        snapshot = row["snapshot"]
        manifest = json.loads((root / "snapshots" / (
            f"{snapshot['sequence']:08d}_{snapshot['digest']}.json")).read_text())
        require(manifest["schema"] == "mr3-observation-input-archive-v1"
                and manifest["scope"] == "encoder_result_before_publication",
                "unknown observation archive format")
        for key in ("epoch", "sequence", "candidate_version"):
            require(manifest[key] == snapshot[key], "archive snapshot identity mismatch")
        require(manifest["snapshot_digest"] == snapshot["digest"]
                and manifest["source_stamp"] == snapshot["source_stamp"],
                "archive snapshot digest/time mismatch")
        metadata = manifest["metadata"]
        require(metadata["epoch"] == snapshot["epoch"]
                and metadata["map_version"] == snapshot["map_version"]
                and metadata["map_sources"] == snapshot["map"]["sources"]
                and metadata["map_source_stamp"] == snapshot["map"]["source_stamp"]
                and metadata["map_received_stamp"] == snapshot["map"]["received_stamp"]
                and metadata["map_payload_sha256"] == row["info"]["watermarks"][
                    "map_payload_sha256"], "archive map metadata/watermark mismatch")
        require(set(manifest["maps"]) == {"fused", "tb1", "tb2", "tb3"},
                "archive does not contain exactly four received maps")
        for name, entry in manifest["maps"].items():
            expected = (metadata["map_payload_sha256"] if name == "fused"
                        else snapshot["path_maps"][name]["payload_sha256"])
            require(entry["payload_sha256"] == expected
                    and entry["artifact"] == f"maps/{expected}.json.gz",
                    "archive map identity/path mismatch")
            if expected not in blobs:
                compressed = (root / entry["artifact"]).read_bytes()
                raw = gzip.decompress(compressed)
                payload = json.loads(raw)
                canonical = json.dumps(payload, allow_nan=False, sort_keys=True,
                                       separators=(",", ":")).encode()
                require(raw == canonical and hashlib.sha256(raw).hexdigest() == expected,
                        "archive received-map payload SHA mismatch")
                info = payload["info"]
                require(len(payload["data"]) == info["width"] * info["height"],
                        "archive received-map shape mismatch")
                blobs[expected] = {"compressed_sha256": hashlib.sha256(compressed).hexdigest(),
                                   "decoded_bytes": len(raw), "info": info}
            info = blobs[expected]["info"]
            geometry = snapshot["map"] if name == "fused" else snapshot["path_maps"][name]
            require([info["height"], info["width"]] == geometry["native_shape"]
                    and info["resolution"] == geometry["native_resolution_m"]
                    and [info["origin"]["position"][axis] for axis in ("x", "y")]
                    == geometry["native_origin_m"], "archive map geometry mismatch")
        snapshots.add(snapshot["digest"])
    return {"passed": True, "unique_snapshots": len(snapshots), "unique_maps": len(blobs),
            "maps": blobs, "scope": "exact received payloads and frozen snapshot/drain identity"}


def audit(directory, root, freeze):
    phase, base, native, command, scalar, sources = load_native_gates(root, freeze)
    result = phase.corrected_audit(base, native, command, [directory])
    episodes = []
    errors = ["native: " + str(error) for error in result.get("errors", [])]
    if not result.get("passed") and not errors:
        errors.append("native audit failed; see nested native evidence")
    for metadata_path in sorted(directory.glob("worker*/episode*/metadata.json")):
        episode = metadata_path.parent
        row = {"directory": str(episode)}
        try:
            row["scalar"] = scalar.audit_episode(episode, freeze)
            row["evaluator_phase"] = audit_phase(episode)
            row["observation_archives"] = audit_archives(episode)
            if not row["scalar"].get("passed") or not row["evaluator_phase"].get("passed"):
                errors.append(str(episode) + ": scalar/phase audit failed")
        except (OSError, ValueError, TypeError, KeyError, IndexError, zlib.error) as error:
            row["error"] = repr(error)
            errors.append(str(episode) + ": " + repr(error))
        episodes.append(row)
    if not episodes:
        errors.append("no native episodes found")
    return {
        "schema": "mr3-p2a-preparation-audit-v1", "freeze": freeze,
        "passed": result.get("passed") is True and not errors,
        "errors": errors, "source_bindings": sources,
        "native": result, "episodes": episodes,
        "scope": "scripted engineering/reset/clock/reward/native closure; no policy reliability",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if re.fullmatch(r"[0-9a-f]{40}", args.freeze) is None:
        parser.error("freeze must be an exact 40-hex Git commit identity")
    if args.output.exists():
        parser.error("audit output exists; choose a new path")
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists())
    result = audit(args.directory, root, args.freeze)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
