#!/usr/bin/env python3
"""Verify finalized v6 evidence bytes and recorded process identities, offline.

This does not rerun native experiments or expand any existing audit's scope.
Run only after all eight stages and canonical archives have finished. Extra JSON
evidence is hashed and parsed without interpreting its independent conclusions.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import time


FREEZE = "c8d483228ecb0105c905459578eddbb4a23d4520"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ASSETS = WIRELESS + "report/assets/20261015_mr3_p1c/"
PROFILE = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/" \
          "mr3_fastdds_loopback_udp.xml"
STAGES = ("pilot", "terminal", "workers1", "workers2", "workers4", "fault", "deadline")
MATRIX_STAGES = frozenset(STAGES) - {"pilot"}
METHOD = "mr3-contact-task-phase-frozen-latch-v2"
PINNED = {
    ASSETS + "implementation_checks_v6.json":
        "3fa50ea70ca1716d73826f4c45cba0ddf88f9dbe4c9b33fc644f60bd0250516d",
    ASSETS + "predeclared_native_plan_v6.json":
        "7e8bd75d17ce393ae2e7a7e487fc40cdaf03f16c174dcf435766f23aed443302",
    PROFILE: "dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b",
    ASSETS + "audit_mr3_env_contact_phase_v2.py":
        "3ce800bfa0455d25a1c3257635c7c4d593478082bbbf1c4dab6a10eed2fc6991",
    ASSETS + "predeclared_offline_contact_phase_v1.json":
        "a8cfe1b100d88cfd72c907a0dd7fabe7a3d684cd922b06d074e5408762307ed5",
    ASSETS + "reward_gate_audit_v3.py":
        "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665",
    ASSETS + "resource_analysis_v2.py":
        "f92b7a9c4f3ec1e06c423d846d810b6f0799bdf08e7c44ba27b507d155b24fdf",
    ASSETS + "workers2_v6_benchmark_audit.json":
        "227fe6bcba7d4dfa21a5359761e9a3159cd1d19704649f4d7fcfc31c61762f35",
    ASSETS + "worker2_w0_e2_v6_audit.json":
        "173d45b2366a6b6bcab9f805976ab02a4f739ec3a88c1f713f8b3a6d7bfc8f5d",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_json(path):
    return json.loads(path.read_text())


def digest(path, decoded=False):
    before = path.stat()
    result = hashlib.sha256()
    opener = gzip.open if decoded else open
    with opener(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino), "file changed: " + str(path))
    return result.hexdigest()


def repository_path(root, name):
    path = (root / name).resolve()
    require(path.is_relative_to(root), "evidence path escapes repository: " + str(name))
    return path


def verify_hash(root, name, expected):
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
            "invalid SHA256 for " + str(name))
    path = repository_path(root, name)
    require(digest(path) == expected, "SHA256 mismatch: " + str(name))
    return {"path": str(path.relative_to(root)), "sha256": expected}


def verify_pins(root):
    checked = [verify_hash(root, name, value) for name, value in PINNED.items()]
    checks = read_json(root / ASSETS / "implementation_checks_v6.json")
    sources = checks["source_sha256"]
    require(isinstance(sources, dict) and len(sources) == 48, "source inventory changed")
    source_proof = [verify_hash(root, name, value) for name, value in sources.items()]
    declaration = read_json(root / ASSETS / "predeclared_offline_contact_phase_v1.json")
    verify_hash(root, ASSETS + declaration["new_helper"], declaration["helper_sha256"])
    verify_hash(root, ASSETS + declaration["checks_receipt"],
                declaration["checks_receipt_sha256"])
    verify_hash(root, ASSETS + "test_audit_mr3_env_contact_phase_v2.py",
                declaration["test_sha256"])
    for name, value in declaration["frozen_source_sha256"].items():
        # Later editorial headers may change; the existing phase audit binds the
        # normative documents to c8d Git blobs, not the current edited Markdown.
        if not name.endswith(".md"):
            verify_hash(root, name, value)
    require(checks["prospective_native_plan_sha256"] ==
            PINNED[ASSETS + "predeclared_native_plan_v6.json"], "plan/check binding changed")
    require(checks["independent_reward_auditor_v3_sha256"] ==
            PINNED[ASSETS + "reward_gate_audit_v3.py"], "reward helper binding changed")
    require(checks["independent_resource_analysis_v2_sha256"] ==
            PINNED[ASSETS + "resource_analysis_v2.py"], "resource helper binding changed")
    for name in ("workers2_v6_benchmark_audit.json", "worker2_w0_e2_v6_audit.json"):
        require(read_json(root / ASSETS / name)["passed"] is False, "old FAIL relabeled")
    return {"immutable_artifacts": checked, "source_count": len(sources),
            "source_files": source_proof, "old_two_failures_retained": True}


def verify_manifest_references(root, value):
    """Check derivative references in addition to raw manifest file records."""
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and "sha256" in value:
            verify_hash(root, value["path"], value["sha256"])
        for key, child in value.items():
            if isinstance(key, str) and "/" in key and isinstance(child, str) \
                    and re.fullmatch(r"[0-9a-f]{64}", child):
                verify_hash(root, key, child)
            verify_manifest_references(root, child)
    elif isinstance(value, list):
        for child in value:
            verify_manifest_references(root, child)


def verify_manifests(root):
    native = root / ASSETS / "native_v6"
    for stage in ("clock",) + STAGES:
        require((native / stage / "manifest.json").is_file(), "incomplete archive: " + stage)
    results, originals, selected = [], set(), set()
    for path in sorted(native.rglob("manifest.json")):
        manifest = read_json(path)
        require(manifest["schema"] == "mr3-selected-native-evidence-manifest-v1"
                and manifest["source_freeze"] == FREEZE
                and manifest["originals_modified"] is False, "manifest identity: " + str(path))
        files = manifest["files"]
        require(isinstance(files, list) and files and manifest["original_file_count"] == len(files),
                "manifest original count differs: " + str(path))
        for row in files:
            original = repository_path(root, row["original"])
            copy = repository_path(root, row["selected"])
            verify_hash(root, row["original"], row["original_sha256"])
            verify_hash(root, row["selected"], row["selected_sha256"])
            require(original.stat().st_size == row["original_bytes"] and
                    copy.stat().st_size == row["selected_bytes"], "manifest size mismatch")
            encoding = row["encoding"]
            require(encoding == "identity" or encoding.startswith("gzip"),
                    "unknown manifest encoding: " + encoding)
            decoded = digest(copy, decoded=encoding.startswith("gzip"))
            require(decoded == row["decoded_selected_sha256"] == row["original_sha256"]
                    and row["decoded_matches_original"] is True, "decoded bytes mismatch")
            originals.add(row["original"])
            selected.add(row["selected"])
        count = manifest.get("selected_artifact_count",
                             manifest.get("selected_original_artifact_count"))
        require(count == len({row["selected"] for row in files}), "selected count differs")
        verify_manifest_references(root, manifest)
        results.append({"path": str(path.relative_to(root)), "sha256": digest(path),
                        "original_records": len(files), "selected_artifacts": count})
    return {"manifests": results, "unique_original_files": len(originals),
            "unique_selected_artifacts": len(selected), "decoded_hashes_verified": True}


def verify_audit_evidence(root, row):
    directory = repository_path(root, row["directory"])
    for name, expected in row["evidence_sha256"].items():
        path = repository_path(root, directory / name)
        if path.exists():
            actual = digest(path)
        else:
            actual = digest(path.with_suffix(path.suffix + ".gz"), decoded=True)
        require(actual == expected, "audited evidence changed: " + str(path))
    for episode in row.get("episodes", []):
        verify_audit_evidence(root, episode)


def verify_method(row, declaration):
    proof = row["offline_contact_phase_audit"]
    require(row["schema"] == "mr3-p1c-contact-phase-audit-v2" and
            row["passed"] is True and row["errors"] == [], "phase audit did not pass")
    require(proof["freeze"] == FREEZE and proof["method"] == METHOD and
            proof["wrapper_sha256"] == PINNED[ASSETS + "audit_mr3_env_contact_phase_v2.py"]
            and proof["only_overridden_function"] == "audit_contacts"
            and proof["original_results_modified"] is False, "phase method binding differs")
    require({name: value["sha256"] for name, value in proof["frozen_sources"].items()} ==
            declaration["frozen_source_sha256"], "phase source pins differ")


def original_result(row):
    result = dict(row)
    proof = result.pop("offline_contact_phase_audit")
    result["schema"] = proof["original_auditor_schema"]
    return result


def verify_audits(root, matrix_path):
    declaration = read_json(root / ASSETS / "predeclared_offline_contact_phase_v1.json")
    tops, results = {}, []
    for stage in STAGES:
        path = root / ASSETS / f"{stage}_v6_contact_phase_v2_benchmark_audit.json"
        row = read_json(path)
        verify_method(row, declaration)
        require(row["freeze"] == FREEZE and
                Path(row["directory"]).name == "mr3_p1c_v6_" + stage, "wrong benchmark stage")
        verify_audit_evidence(root, row)
        tops[stage] = row
        results.append({"stage": stage, "path": str(path.relative_to(root)),
                        "sha256": digest(path), "passed": True})
    matrix = read_json(matrix_path)
    verify_method(matrix, declaration)
    benchmarks = matrix["benchmarks"]
    require(len(benchmarks) == 6, "matrix must contain exactly six declared groups")
    stages = []
    for row in benchmarks:
        name = Path(row["directory"]).name
        require(name.startswith("mr3_p1c_v6_"), "matrix contains another run namespace")
        stage = name.removeprefix("mr3_p1c_v6_")
        require(stage in MATRIX_STAGES and original_result(tops[stage]) == row,
                "matrix differs from its separately passed phase2 top: " + stage)
        stages.append(stage)
    require(set(stages) == MATRIX_STAGES, "matrix group coverage differs")
    return {"seven_top_audits": results, "matrix": {"path": str(matrix_path),
            "sha256": digest(matrix_path), "passed": True, "stages": stages},
            "scope": "Existing audit verdicts and evidence hashes; no new native/task gate."}


def proc_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except FileNotFoundError:
        return None
    return {"state": fields[0], "start_ticks": int(fields[19])}


def verify_transport_metadata(value):
    require(value["freeze"] == FREEZE and
            value["transport_environment"]["profile_sha256"] == PINNED[PROFILE] and
            value["transport_environment"]["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp",
            "native metadata freeze/profile/backend differs from v6")


def verify_owned_identities(root):
    native = root / ASSETS / "native_v6"
    identities, bare_pids, receipts = {}, {}, []

    def add(identity, path):
        pid, ticks = identity["pid"], identity["start_ticks"]
        require(type(pid) is int and pid > 0 and type(ticks) is int and ticks > 0,
                "invalid saved PID/start identity: " + str(path))
        identities.setdefault((pid, ticks), set()).add(str(path.relative_to(root)))

    for path in sorted(native.glob("*/worker*/episode*/supervisor_metadata.json")):
        value = read_json(path)
        metadata = read_json(path.with_name("metadata.json"))
        verify_transport_metadata(metadata)
        require(metadata["epoch"] == value["epoch"], "canonical metadata epoch differs")
        add(value["worker_identity"], path)
        receipt_path = path.with_name("supervisor_shutdown.json")
        receipt = read_json(receipt_path)
        require(receipt["epoch"] == value["epoch"] and
                receipt["remaining_owned_processes"] == [] and
                receipt["remaining_owned_zombies"] == [], "saved cleanup not empty")
        for identity in receipt["owned_processes_seen"]:
            add(identity, receipt_path)
        receipts.append({"path": str(receipt_path.relative_to(root)),
                         "sha256": digest(receipt_path)})
    require(receipts, "no saved v6 supervisor ownership receipts")
    for path in sorted(native.glob("*/worker*/episode*/native_stop.json")):
        value = read_json(path)
        pid = value["native_cli_pid"]
        require(type(pid) is int and pid > 0, "invalid native-stop PID")
        bare_pids.setdefault(pid, set()).add(str(path.relative_to(root)))
    clock = native / "clock/summary.json"
    clock_summary = read_json(clock)
    verify_transport_metadata(clock_summary)
    require(clock_summary["passed"] is True and clock_summary["error"] is None,
            "clock component did not pass")
    for key in ("server_pid", "helper_pid", "stop_cli_pid"):
        pid = clock_summary[key]
        require(type(pid) is int and pid > 0, "invalid clock PID")
        bare_pids.setdefault(pid, set()).add(str(clock.relative_to(root)) + ":" + key)
    started = time.monotonic_ns()
    observed, violations = [], []
    for (pid, ticks), sources in sorted(identities.items()):
        current = proc_identity(pid)
        same = current is not None and current["start_ticks"] == ticks
        row = {"pid": pid, "recorded_start_ticks": ticks, "sources": sorted(sources),
               "current_proc": current, "recorded_identity_still_exists": same}
        observed.append(row)
        if same:
            violations.append(row)
    unbound = []
    for pid, sources in sorted(bare_pids.items()):
        current = proc_identity(pid)
        row = {"pid": pid, "recorded_start_ticks": None, "sources": sorted(sources),
               "current_proc": current, "scope": "Bare saved PID; no historical start fabricated"}
        unbound.append(row)
        if current is not None:
            violations.append(row)
    return {"passed": not violations, "snapshot_started_monotonic_ns": started,
            "snapshot_finished_monotonic_ns": time.monotonic_ns(),
            "recorded_identity_count": len(identities), "identities": observed,
            "bare_pids_without_recorded_start_ticks": unbound, "violations": violations,
            "cleanup_receipts": receipts,
            "scope": "Current /proc snapshot of actual saved identities, including zombies. "
                     "Different start_ticks means PID reuse, not an owned survivor. Bare "
                     "unbound PIDs must be absent; no fabricated identity or process control."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-audit", required=True, type=Path)
    parser.add_argument("--extra-evidence", action="append", default=[], type=Path,
                        help="Parse/hash this JSON only; no unagreed schema/verdict assertion")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new evidence filename")
    root = next(path for path in Path(__file__).resolve().parents if (path / ".git").exists())
    report = {"schema": "mr3-p1c-v6-final-evidence-verification-v1", "source_freeze": FREEZE,
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "verifier_sha256": digest(Path(__file__)), "sections": {}, "errors": [],
              "scope": "Evidence SHA/completeness and saved-identity cleanup validation. "
                       "No extra native gate, native run, training/GPU call or scope expansion."}
    operations = (("immutable_sources", lambda: verify_pins(root)),
                  ("canonical_manifests", lambda: verify_manifests(root)),
                  ("formal_audits", lambda: verify_audits(root, args.matrix_audit.resolve())),
                  ("owned_identity_snapshot", lambda: verify_owned_identities(root)))
    for name, operation in operations:
        try:
            result = operation()
            report["sections"][name] = result
            if result.get("passed") is False:
                report["errors"].append(
                    name + ": recorded process still exists or bare PID ambiguous")
        except (OSError, ValueError, TypeError, KeyError, IndexError, EOFError) as error:
            report["sections"][name] = {"passed": False, "error": str(error)}
            report["errors"].append(name + ": " + str(error))
    report["extra_evidence"] = []
    for path in args.extra_evidence:
        try:
            read_json(path)
            report["extra_evidence"].append({
                "path": str(path.resolve()), "sha256": digest(path),
                "scope": "JSON exists/parses; conclusions not inferred"})
        except (OSError, ValueError) as error:
            report["errors"].append("extra evidence " + str(path) + ": " + str(error))
    report["passed"] = not report["errors"]
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": report["passed"], "errors": report["errors"],
                      "output": str(args.output)}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
