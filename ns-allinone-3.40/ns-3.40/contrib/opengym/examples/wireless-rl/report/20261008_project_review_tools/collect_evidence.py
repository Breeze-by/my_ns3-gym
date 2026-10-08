#!/usr/bin/env python3
"""Archive a read-only project review without rewriting any original report."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess


def load(path):
    return json.loads(Path(path).read_text())


def sha(path, compressed=False):
    digest = hashlib.sha256()
    with (gzip.open(path, "rb") if compressed else Path(path).open("rb")) as stream:
        for part in iter(lambda: stream.read(1024*1024), b""):
            digest.update(part)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    args.artifacts = args.artifacts.resolve()
    args.output = args.output.resolve()
    assert not args.output.exists() and not args.artifacts.exists(), "never overwrite a review"
    root, checks = args.repo.resolve(), args.checks.resolve()
    report = Path(__file__).resolve().parents[1]
    provenance = load(report/"20261007_p3c5_provenance.json")
    old_p3c = load(report/"20261007_p3c_provenance.json")
    verified = []

    def verify(path, expected):
        path = Path(path)
        assert sha(path) == expected, f"original evidence changed: {path}"
        verified.append({"path": str(path), "sha256": expected})

    for item in old_p3c["original_63_unchanged"]:
        for kind in ("result", "ledger"):
            verify(item[kind+"_path"], item[kind+"_sha256"])
    for item in load(report/"20261007_p3c_gate.json")["episodes"]:
        directory = Path(item["manifest"]).parent
        verify(directory/"ledger.jsonl", item["ledger_sha256"])
        summary = load(directory/"summary.json")
        verify(summary["result_path"], item["result_sha256"])
    for filename in ("20261007_p3c5_shutdown_failed_candidate.json", "20261007_p3c5_export_grace_failed_candidate.json"):
        for item in load(report/filename)["episodes"]:
            if "summary_sha256" in item:
                verify(Path(item["raw_directory"])/"summary.json", item["summary_sha256"])
            for path, expected in item["original_evidence_sha256"].items():
                verify(Path(item["raw_directory"])/path, expected)
    for path, expected in provenance["protected_user_files_unchanged"].items():
        verify(root/path, expected)
    for item in provenance["artifacts"]:
        verify(item["path"], item["sha256"])
    for item in provenance["archive"]:
        verify(item["archive"]["path"], item["archive"]["sha256"])
        assert sha(item["archive"]["path"], compressed=True) == item["original"]["sha256"]

    p3a, p3b, p3c, p3c5 = (load(checks/path) for path in (
        "p3a6_replay.json", "p3b5_replay/summary.json", "p3c_replay.json", "p3c5_gate/summary.json"))
    assert p3a["fixed_matrix_complete_count"] == p3a["fixed_matrix_episode_count"] == 10
    assert p3a["runtime_audit_count"] == 11 and p3a["source_audit_violations"] == []
    assert all(item["status"] == "PASS" for item in (p3b, p3c, p3c5))
    assert p3b["original_count"] == 63 and p3b["paired_tdi_checks"] == 31
    assert p3c5["native_success_count"] == 11 and p3c5["original_count"] == 14
    original_gate = load(report/"20261007_p3c5_gate.json")
    unchanged_math = {key: p3c5["artifacts_sha256"][key] == original_gate["artifacts_sha256"][key]
                      for key in p3c5["artifacts_sha256"]}
    assert all(unchanged_math.values()), "read-only repair changed traffic accounting"
    for item in p3c5["episodes"]:
        for kind in ("ledger", "result"):
            path = Path(item["raw_directory"])/("ledger.jsonl" if kind == "ledger" else Path(item["raw_directory"]).name+".json")
            verify(path, item[kind+"_sha256"])
    source = load(checks/"expanded_source_v2.json")
    assert len(source["immutable_files"]) == 150 and len(source["static_protocol_matrix"]["matrix"]) == 54
    assert source["immutable_inventory_matches_frozen_tree"]
    functional = (checks/"final_functional_v3.txt").read_text()
    assert re.search(r"749 passed, 1 skipped", functional)
    assert "4 packages finished" in (checks/"build.txt").read_text()
    reserve = load(checks/"return_reserve.json")
    assert reserve["status"] == "CONFIRMED_REQUIREMENT_GAP"
    helper_path = report/"20261007_p3c5_artifact_tools/finalize_evidence.py"
    spec = importlib.util.spec_from_file_location("original_p3c5_findings", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    findings = helper.findings(p3c5)
    archives = []
    args.artifacts.mkdir(parents=True, exist_ok=False)
    for relative in ("baseline_functional.txt", "source.json", "audit_gaps_before.json", "auditor_targeted.txt",
                     "expanded_source.json", "expanded_source_v2.json", "expanded_source_v2.txt",
                     "final_functional.txt", "final_functional_v2.txt", "final_functional_v3.txt", "build.txt",
                     "return_reserve.json", "return_reserve.txt", "p3a6_replay.json", "p3a6_replay.txt",
                     "p3b5_replay/summary.json", "p3b5_replay.txt", "p3c_replay.json", "p3c_replay.txt",
                     "p3c5_gate/summary.json", "p3c5_gate.txt", "collect_evidence_v1.txt", "collect_evidence_v2.txt"):
        original = checks/relative
        target = args.artifacts/(relative.replace("/", "_")+".gz")
        target.write_bytes(gzip.compress(original.read_bytes(), mtime=0))
        assert sha(target, compressed=True) == sha(original)
        archives.append({"original": str(original), "original_sha256": sha(original),
                         "archive": str(target.relative_to(report)), "archive_sha256": sha(target), "lossless": True})
    result = {"review_completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewed_initial_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "scope": "first-party task/network/evidence review; vendor code inspected only at relevant interfaces; no new simulator tasks",
        "technical_evidence_status": "PASS_WITH_ORIGINAL_TASK_FAILURES_RETAINED",
        "research_readiness": "CONDITIONAL; return-path energy requirement open; Wi-Fi capacity unmeasured",
        "user_acceptance": "P3C accepted; P3C.5 still pending; review is not acceptance",
        "reaudits": {"p3a6_originals": 11, "p3b5_originals": 63, "p3b5_streams": p3b["stream_count"],
            "p3b5_tdi_pairs": 31, "p3c_originals": 3,
            "p3c_live_samples": sum(e["live_replay"]["samples"] for e in p3c["episodes"]),
            "p3c5_originals": 14, "p3c5_native_status": p3c5["native_task_status_counts"],
            "p3c5_live_samples": findings["live_samples"], "p3c5_input_records": findings["input_records"]},
        "checks": {"functional_passed": 749, "functional_skipped": 1,
            "initial_combined_collection_error_retained": "final_functional.txt.gz; duplicate ROS template test module name",
            "whole_workspace_template_lint_pass_claimed": False, "build_packages": 4,
            "immutable_files": 150, "frozen_inventory_exact": True, "static_protocol_cells": 54, "targeted_passed": 40,
            "additional_inventory_counterexample_checks": 3,
            "traffic_derived_artifact_sha_unchanged": unchanged_math,
            "runtime_probes": "original ROS/Qt probes reused as unchanged actor evidence; not rerun or claimed new"},
        "return_budget_gap": reserve, "p3c5_findings": findings,
        "auditor_counterexamples_before_repair": load(checks/"audit_gaps_before.json"),
        "preservation": {"protected_user_files": provenance["protected_user_files_unchanged"],
            "historical_archives_lossless_rechecked": len(provenance["archive"]),
            "historical_artifacts_sha_rechecked": len(provenance["artifacts"]),
            "v1_failed_originals": 3, "v2_failed_originals": 14, "verified_file_records": verified},
        "statistical_cautions": {"zero_events_14_iid_one_sided_95_upper_risk_illustration": 1-.05**(1/14),
            "all_success_24_iid_wilson_95_lower_illustration": 24/(24+1.959963984540054**2),
            "illustration_is_not_a_population_interval_for_this_fixed_matrix": True},
        "future_order": ["close return safety requirement and refreeze before live closed loop", "P4A-0 packet/payload contract",
            "P4B-0 passive original-load Wi-Fi and early hardware calibration", "P4A-1 causal bridge", "P4B-1 independent calibration validation",
            "P5 strong baselines and explicit go/no-go", "conditional P6", "P7/P8 in both branches"],
        "archives": archives}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps({"technical_evidence_status": result["technical_evidence_status"],
        "research_readiness": result["research_readiness"], "preserved_files": len(verified), "archives": len(archives)}))


if __name__ == "__main__":
    main()
