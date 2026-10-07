#!/usr/bin/env python3
"""Verify unchanged raw evidence and archive explicit P3C.5 derived artifacts."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sys


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024*1024), b""):
            digest.update(part)
    return digest.hexdigest()


def record(path):
    path = Path(path).resolve()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def copy_exact(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert sha(target) == sha(source), f"refuse to overwrite derived evidence: {target}"
    else:
        shutil.copyfile(source, target)


def gzip_exact(source, target):
    raw = source.read_bytes()
    compressed = gzip.compress(raw, mtime=0)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert gzip.decompress(target.read_bytes()) == raw
    else:
        target.write_bytes(compressed)
    assert gzip.decompress(target.read_bytes()) == raw
    return {"original": record(source), "archive": record(target), "lossless": True}


def findings(gate):
    rows = []
    for e in gate["episodes"]:
        a, r = e["audit"], e["result"]
        controls = sum(a["tx_cdr_bytes_by_role"].get(k, 0) for k in ("candidate", "request", "grant", "heartbeat"))
        maps = [s for s in a["strata"] if s["message_type"] in ("map_snapshot", "fused_map_snapshot")]
        compressed = sum(s["counts"].get("generated_payload_bytes", 0) for s in maps)
        raw = sum(s["counts"].get("uncompressed_payload_bytes", 0) for s in maps)
        pose = next(s for s in a["aoi_streams"] if s["message_type"] == "pose_state" and s["sender"] == "tb1")
        example = next((s for s in a["strata"] if s["phase"] == "EXPLORE" and s["message_type"] == "pose_state"
                        and s["direction"] == "uplink" and s["robot"] == "tb1"), None)
        rows.append({"case": e["case"], "native_success": r["success"], "native_phase": r["task_phase"],
            "termination_reason": r["termination_reason"], "failure_reason": r["failure_reason"],
            "completion_sec": r["completion_time_sec"], "actual_elapsed_sec": r["elapsed_sim_time_sec"],
            "measurement_duration_sec": a["duration_sec"], "rmst300_sec": r["completion_time_sec"] if r["success"] else 300,
            "mean_cdr_bps": a["total_tx_cdr_bytes"]*8/a["duration_sec"], "one_second_cdr_bps": a["one_second_cdr_bps"],
            "tx_cdr_bytes": a["total_tx_cdr_bytes"], "tx_cdr_bytes_by_role": a["tx_cdr_bytes_by_role"],
            "all_nondata_fraction": a["control_cdr_fraction"], "new_protocol_fraction": controls/a["total_tx_cdr_bytes"],
            "map_compressed_bytes": compressed, "map_raw_bytes": raw, "map_compression_fraction": compressed/raw,
            "control_retry_messages": sum(s["counts"].get("control_retry_messages", 0) for s in a["strata"]),
            "transport_retry_attempts": sum(s["counts"].get("transport_retry_attempts", 0) for s in a["strata"]),
            "drop_attempts": sum(s["counts"].get("drop_attempts", 0) for s in a["strata"]),
            "expired_attempts": sum(s["counts"].get("expired_attempts", 0) for s in a["strata"]),
            "overflow_attempts": sum(s["counts"].get("queue_overflow_attempts", 0) for s in a["strata"]),
            "protocol_full_ledger": a["protocol"], "explore_pose_tb1": example, "pose_tb1_aoi": pose["aoi"],
            "conditional_serialization_sec": {str(mbps): a["physical_accounting"]["serialization_sec_per_mbps"]/mbps
                                               for mbps in (1, 6, 54)}})
    return {"status": "PASS", "scope": gate["scope"], "episodes": rows,
            "native_success": sum(e["result"]["success"] for e in gate["episodes"]),
            "native_terminations": dict(Counter(e["result"]["termination_reason"] for e in gate["episodes"])),
            "protocol_local_offers_full_ledger": sum(e["audit"]["protocol"]["local_generated"] for e in gate["episodes"]),
            "received_bound_ap_decisions_full_ledger": sum(e["audit"]["protocol"]["ap_decisions"] for e in gate["episodes"]),
            "live_samples": sum(e["live_replay"]["samples"] for e in gate["episodes"]),
            "input_records": sum(e["live_replay"]["input_records"] for e in gate["episodes"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--findings-only", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    ros = root/"ros2_ws/ros2-multi-robot-automap"
    report = root/"ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report"
    gate = load(args.gate)
    assert gate["status"] == "PASS" and gate["original_count"] == 14
    summary = findings(gate)
    if args.findings_only:
        assert not args.findings_only.exists()
        args.findings_only.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False)+"\n")
        print(json.dumps({k: summary[k] for k in ("status", "native_success", "native_terminations", "live_samples")}))
        return
    artifacts = report/"20261007_p3c5_artifacts"
    historical = load(report/"20261007_p3c_provenance.json")
    protected = load(artifacts/"protected_user_files.json")
    assert protected == historical["protected_user_files_unchanged"]
    assert all(sha(root/p) == digest for p, digest in protected.items())
    for e in historical["original_63_unchanged"]:
        for kind in ("result", "ledger"):
            assert sha(e[kind+"_path"]) == e[kind+"_sha256"]
    previous = load(report/"20261007_p3c_gate.json")
    for e in previous["episodes"]:
        directory = Path(e["manifest"]).parent
        result = Path(load(directory/"summary.json")["result_path"])
        assert sha(directory/"ledger.jsonl") == e["ledger_sha256"]
        assert sha(result) == e["result_sha256"]
    failed = load(report/"20261007_p3c5_shutdown_failed_candidate.json")
    for e in failed["episodes"]:
        for p, digest in e["original_evidence_sha256"].items():
            assert sha(Path(e["raw_directory"])/p) == digest
    failed_v2 = load(report/"20261007_p3c5_export_grace_failed_candidate.json")
    for e in failed_v2["episodes"]:
        assert sha(Path(e["raw_directory"])/"summary.json") == e["summary_sha256"]
        for p, digest in e["original_evidence_sha256"].items():
            assert sha(Path(e["raw_directory"])/p) == digest
    sys.path.insert(0, str(ros/"src/multi_robot_exploration"))
    from multi_robot_exploration.metrics_io import flatten
    csv_checks = []
    for e in gate["episodes"]:
        directory = Path(e["raw_directory"])
        original = load(directory/"summary.json")
        assert original["git_commit"] == gate["task_cohort_commit"]
        for name, expected in original["evidence_sha256"].items():
            assert sha(directory/name) == expected
        assert sha(directory/"summary.json") == e["summary_sha256"]
        metrics = directory/"ledger_metrics"
        for stem in ("windows", "live_windows"):
            def expected_rows():
                if stem == "windows":
                    for line in (metrics/"windows.jsonl").open():
                        yield flatten(json.loads(line))
                else:
                    for line in (metrics/"live.jsonl").open():
                        sample = json.loads(line)
                        for row in sample["window"]+sample["by_type_window"]+sample["by_stream_window"]:
                            yield flatten(row)
            count = 0
            with (metrics/(stem+".csv")).open() as stream:
                actual = csv.DictReader(stream)
                for expected in expected_rows():
                    row = next(actual)
                    assert set(row) == set(expected)
                    assert all(row[k] == ("" if v is None else str(v)) for k, v in expected.items()), (e["case"], stem, count)
                    count += 1
                assert next(actual, None) is None
            csv_checks.append({"case": e["case"], "kind": stem, "status": "PASS", "rows": count,
                               "csv": record(metrics/(stem+".csv"))})
        for filename in ("manifest.json", "summary.json", "graph.json"):
            copy_exact(directory/filename, artifacts/"originals"/e["case"]/filename)
        copy_exact(Path(original["result_path"]), artifacts/"originals"/e["case"]/"result.json")
    owned = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            env = p.joinpath("environ").read_bytes().split(b"\0")
            argv = p.joinpath("cmdline").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if any(f"ROS_DOMAIN_ID={d}".encode() in env for d in (178, 179, *range(180, 194))) or any(
                f"GAZEBO_MASTER_URI=http://127.0.0.1:{port}".encode() in env for port in range(19920, 19934)) or (
                any(a.endswith(b"/run_p3c5_audit.py") for a in argv) and b"p3c5_v2" in argv):
            owned.append(int(p.name))
    assert not owned, owned
    for port in range(19920, 19934):
        with socket.socket() as sk:
            sk.settimeout(.1)
            assert sk.connect_ex(("127.0.0.1", port)) != 0, port
    archival = []
    for filename in ("attempt_costs.jsonl", "strata.jsonl", "strata.csv", "bursts.jsonl"):
        source = args.gate.parent/filename
        assert sha(source) == gate["artifacts_sha256"][filename]
        archival.append(gzip_exact(source, artifacts/args.gate.parent.name/(filename+".gz")))
    checks = ros/"log/p3c5/checks"
    for path in sorted(checks.glob("v*")):
        if path.is_file():
            if path.suffix == ".txt":
                archival.append(gzip_exact(path, artifacts/"checks"/(path.name+".gz")))
            else:
                copy_exact(path, artifacts/"checks"/path.name)
    copy_exact(args.gate, report/"20261007_p3c5_gate.json")
    (artifacts/"final_findings.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False)+"\n")
    (artifacts/"final_archival.json").write_text(json.dumps(archival, indent=2, sort_keys=True)+"\n")
    sources = [ros/"scripts"/name for name in ("check_p3c5_gate.py", "run_p3c5_audit.py", "check_p3c5_runtime.py",
               "p3c5_traffic_manifest.json", "p3c5_control_schema.json", "test_p3c5_gate.py", "test_p3c_exports.py")]
    sources += [ros/"src/multi_robot_exploration/multi_robot_exploration"/name
                for name in ("admission_protocol.py", "traffic_audit.py", "ideal_gateway.py", "metrics_node.py",
                             "gateway_metrics.py", "gateway_panel.py")]
    sources += sorted((report/"20261007_p3c5_artifact_tools").glob("*.py"))
    provenance = {"status": "PASS", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "task_frozen_commit": gate["task_cohort_commit"], "task_original_count": 14,
        "accepted_P3B5_originals_unchanged": 63, "accepted_P3C_originals_unchanged": 3,
        "failed_v1_originals_unchanged": 3, "failed_v2_originals_unchanged": 14,
        "protected_user_files_unchanged": protected,
        "csv_json_checks": csv_checks, "csv_rows": sum(e["rows"] for e in csv_checks),
        "raw_gate": record(args.gate), "current_reader_and_actor_sources": [record(p) for p in sources],
        "archive": archival, "owned_domains": [178, 179, *range(180, 194)], "owned_processes_remaining": owned,
        "artifacts": [record(p) for p in sorted(artifacts.rglob("*")) if p.is_file()]
                     + [record(p) for p in sorted(report.glob("20261007_p3c5_*.png"))]
                     + [record(report/"20261007_p3c5_gate.md"), record(report/"20261007_p3c5_gate.json")],
        "limits": gate["conclusion"]}
    (report/"20261007_p3c5_provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps({"status": "PASS", "protected": len(protected), "old_originals": 83,
                      "new_originals": 14, "csv_rows": provenance["csv_rows"], "owned_processes": len(owned)}))


if __name__ == "__main__":
    main()
