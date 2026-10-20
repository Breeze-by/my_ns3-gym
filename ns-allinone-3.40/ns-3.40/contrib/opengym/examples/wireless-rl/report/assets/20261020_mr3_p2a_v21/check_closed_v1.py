#!/usr/bin/env python3
"""Finite static closure verification; never substitutes for native gates."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[9]
W = HERE.parents[2]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    archive = read(HERE / "archive_verification_v1.json")
    inventory = read(HERE / "native_inventory_v1.json")
    assert archive["byte_verification_passed"] and archive["all_member_bytes_verified"]
    assert archive["native_file_count"] == inventory["file_count"] == len(inventory["files"]) == 1033
    assert inventory["total_bytes"] == sum(v["bytes"] for v in inventory["files"].values()) == 2041262832
    whole = hashlib.sha256()
    for part in archive["parts"]:
        path = HERE / part["path"]
        assert path.stat().st_size == part["bytes"] < 100 * 1024 * 1024
        assert sha(path) == part["sha256"]
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                whole.update(block)
    assert whole.hexdigest() == archive["archive_sha256"]
    copies = read(HERE / "auxiliary_copy_index_v1.json")["files"]
    assert len(copies) == archive["auxiliary_file_count"] == 53
    for entry in copies:
        path = HERE / entry["copy"]
        assert path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"]
        assert sha(Path(entry["original"])) == entry["sha256"]
    closed = HERE / "closed_execution/mr3_p2a_v21_diagnostic"
    summary = read(closed / "summary.json")
    cadence = read(closed / "cadence_result.json")
    assert not summary["passed"] and summary["source_unchanged"]
    assert summary["all_submitted_children_waited"] and not summary["skipped_audits"]
    assert summary["gpu_calls"] == summary["optimizer_steps"] == 0
    assert not summary["qualification"] and not summary["training_eligible"]
    assert not cadence["passed"] and len(cadence["errors"]) == len(cadence["episodes"]) == 1
    assert "unreceived storage ACK" in cadence["errors"][0]["error"]
    assert "episode001" in cadence["errors"][0]["episode"]
    assert "episode002" in cadence["episodes"][0]["directory"]
    account = read(HERE / "engineering_accounting_v1.json")
    assert account["charge_seconds"] == "3263.823140435"
    assert account["cumulative_used_seconds"] == "41480.3336378496018"
    assert account["remaining_seconds"] == "10519.6663621503982"
    identities = read(HERE / "later_identity_absence_v1.json")
    assert identities["absence_passed"] and identities["saved_identity_count"] == 111
    assert not identities["present"] and not identities["unreadable"]
    failed = read(HERE / "checks/guard_storage_barrier_cpu_v1/actual_wait.json")
    passed = read(HERE / "checks/guard_storage_barrier_cpu_v2/actual_wait.json")
    assert failed["actual_returncode"] == 1 and not failed["passed"]
    assert passed["actual_returncode"] == 0 and passed["passed"] and passed["source_unchanged"]
    assert "132 passed" in (HERE / "checks/guard_storage_barrier_cpu_v2/console.log").read_text()
    for source in passed["source_after"]:
        assert sha(ROOT / source["path"]) == source["sha256"]
        ast.parse((ROOT / source["path"]).read_text())
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text())
    json_count = 0
    for path in HERE.rglob("*.json"):
        read(path)
        json_count += 1
    old_log = subprocess.check_output(["git", "show", "HEAD:" + str((W / "log.md").relative_to(ROOT))], cwd=ROOT)
    assert (W / "log.md").read_bytes().startswith(old_log)
    diff = subprocess.check_output(["git", "diff", "--unified=0", "--", "*.md"], cwd=ROOT, text=True)
    added, current = [], None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = ROOT / line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((current, line[1:]))
    for name in ("20261020_mr3_p2a_next_route_proposal.md",):
        path = W / "report" / name
        added.extend((path, line) for line in path.read_text().splitlines())
    links = 0
    for path, line in added:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", line):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            target = unquote(target.split("#", 1)[0].strip("<>"))
            assert (path.parent / target).exists(), (path, target)
            links += 1
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    output = {"schema": "mr3-v21-finite-static-closure-v1", "static_checks_passed": True,
              "diagnostic_passed": False, "qualification": False, "training_eligible": False,
              "archive_parts_verified": len(archive["parts"]), "auxiliary_copies_verified": len(copies),
              "json_files_parsed": json_count, "added_document_links_verified": links,
              "failed_cpu_attempt_retained": True, "guard_cpu_passes": 132,
              "log_append_only": True,
              "scope": "static bytes, accounting, evidence and documentation; no new native or formal replay"}
    (HERE / "closed_integrity_v1.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
