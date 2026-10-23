"""Produce the explicit new-driver bridge/binding; exact-freeze admission runs afterwards."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from mr3_learning import native_custody, native_custody_reach as gate

ROOT = gate.WORKSPACE
A = ROOT / gate.WIRELESS / "report/assets/20261024_mr3_p2a_v65_owned_stream_qualification"
MANIFEST = A.parent / "20261023_mr3_p2a_v59_encoder_profile/checks/native_build_v1/build_manifest_v1.json"
BRIDGE = A / "native_build_bridge_v1.json"


def proof(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {"path":str(path), "bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest()}


def load_bound(spec):
    actual = proof(spec["path"])
    gate.require(all(actual[k] == spec[k] for k in ("path", "bytes", "sha256")), "builder reference changed")
    return json.loads(Path(spec["path"]).read_text())


def update_driver_binding(base_binding, manifest_path=MANIFEST, bridge_path=BRIDGE):
    """Update only the new driver role, six driver sources and separate seventh helper.

    This current-byte producer does not claim exact-freeze or native admission.
    The committed result must pass gate.verify_build_bridge on the actual new freeze.
    """
    manifest_path, bridge_path = Path(manifest_path).resolve(), Path(bridge_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    gate.require(manifest.get("schema") == gate.INITIAL_ENCODER_MANIFEST_SCHEMA and
                 manifest.get("passed") is True and manifest.get("source_unchanged") is True and
                 manifest.get("actuation_profile") == gate.INITIAL_ENCODER_ACTUATION_PROFILE,
                 "builder needs the actual successful new-profile driver manifest")
    wait = load_bound(manifest["actual_wait"])
    gate.require(wait.get("schema") == "mr3-reach-outer-actual-wait-v1" and wait.get("scope") == "cpu" and
                 wait.get("actual_waited") is True and wait.get("actual_returncode") == 0 and
                 wait.get("passed") is True and wait.get("errors") == [] and
                 wait.get("source_before") == wait.get("source_after"), "actual new build wait failed")
    gate.require(set(manifest["compiled_sources"]["driver"]) == gate.COMPILED_FIELDS["driver"],
                 "new manifest must retain exactly the original six driver fields")
    updated = copy.deepcopy(base_binding)
    old_driver = updated["binaries"]["driver"]
    actual = {"path":old_driver["path"], **native_custody.file_proof(old_driver["path"])}
    library = manifest["library"]
    gate.require(actual["path"] == library["path"] and actual["resolved_path"] == library["real_path"] and
                 actual["sha256"] == library["sha256"] and actual["bytes"] == library["bytes"],
                 "installed new driver differs from its actual build manifest")
    updated["binaries"]["driver"] = actual
    fields = {}
    for field,spec in manifest["compiled_sources"]["driver"].items():
        current = proof(spec["path"])
        gate.require(all(current[k] == spec[k] for k in ("path","sha256","bytes")), "new driver source changed")
        fields[field] = {"path":str(Path(current["path"]).relative_to(ROOT)), "sha256":current["sha256"]}
    extra = manifest["initial_encoder_compiled_source"]
    current = proof(extra["path"])
    gate.require(all(current[k] == extra[k] for k in ("path","sha256","bytes")) and
                 str(Path(current["path"]).relative_to(ROOT)) == gate.INITIAL_ENCODER_HEADER,
                 "new driver seventh helper source changed")
    updated["compiled_sources"]["driver"] = fields
    updated["initial_encoder_compiled_source"] = {"path":gate.INITIAL_ENCODER_HEADER,"sha256":current["sha256"]}
    updated["actuation_profile"] = gate.INITIAL_ENCODER_ACTUATION_PROFILE
    bridge = {"schema":gate.SCHEMA_BUILD_BRIDGE,"safety_contract":gate.CONTRACT,"passed":True,
        "scope":gate.INITIAL_ENCODER_BUILD_SCOPE,"actuation_profile":gate.INITIAL_ENCODER_ACTUATION_PROFILE,
        "actual_wait":manifest["actual_wait"],"manifest":proof(manifest_path),
        "compiler_flags_archive":manifest["compiler_flags_archive"],
        "source_derivation":proof(ROOT/gate.INITIAL_ENCODER_SOURCE_PROFILE),
        "commands":[{"argv":wait["actual_argv"],"returncode":0,"observed_returncode":0}],
        "passed_scope":"actual build/current-byte facts; exact source freeze is rechecked on admission",
        "native_admission":False,"historical_driver_build_credit_reused":False}
    gate.require(bridge["source_derivation"]["sha256"] == gate.INITIAL_ENCODER_SOURCE_PROFILE_SHA256,
                 "builder source derivation is not the sealed profile")
    encoded = json.dumps(bridge,indent=2)+"\n"
    if bridge_path.exists():
        gate.require(bridge_path.read_text() == encoded, "existing new driver bridge differs; preserve it")
    else:
        bridge_path.write_text(encoded)
    gate.require(updated["build_receipts"], "base binding has no original build receipt slot")
    updated["build_receipts"][0] = {"path":str(bridge_path.relative_to(ROOT)),"sha256":proof(bridge_path)["sha256"]}
    gate.require({k:v for k,v in updated["binaries"].items() if k != "driver"} ==
                 {k:v for k,v in base_binding["binaries"].items() if k != "driver"}, "unchanged native roles were modified")
    return updated


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-binding",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    gate.require(not args.output.exists(), "new binding output exists")
    value=update_driver_binding(json.loads(args.base_binding.read_text()))
    args.output.write_text(json.dumps(value,indent=2)+"\n")


if __name__ == "__main__":
    main()
