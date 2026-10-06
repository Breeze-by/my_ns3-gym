#!/usr/bin/env python3
"""Read-only conservation audit and curve exports from accepted P3B.5 originals."""

import argparse
import ast
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import shlex
import subprocess

from export_gateway_metrics import export, compare, digest
from run_p3b5_tasks import tdi

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/multi_robot_exploration"))
from multi_robot_exploration.gateway_metrics import LedgerMetrics, task_degradation_index


def protocol_declaration(command):
    """Use the frozen command/defaults, preserving null undetected observations."""
    project = Path(__file__).resolve().parents[1]
    relative = (project / "scripts/ros_smoke_test.py").relative_to(project.parents[1])
    source = subprocess.check_output(["git", "show", f"d8d361b:{relative}"], cwd=project)
    options = {"--target-max-distance": "target_max_distance_m", "--target-field-of-view": "target_field_of_view_deg",
               "--target-confirmation-frames": "target_confirmation_frames",
               "--rally-position-tolerance": "rally_position_tolerance_m", "--rally-linear-tolerance": "rally_linear_tolerance_mps",
               "--rally-angular-tolerance": "rally_angular_tolerance_radps", "--rally-hold": "rally_hold_sec"}
    defaults = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument" and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in options:
            defaults[node.args[0].value] = next(ast.literal_eval(k.value) for k in node.keywords if k.arg == "default")
    arguments = shlex.split(command)
    return {key: type(defaults[option])(arguments[arguments.index(option)+1]) if option in arguments else defaults[option]
            for option, key in options.items()}, hashlib.sha256(source).hexdigest()


def audit_one(arguments):
    row, directory, full_export = arguments
    result_path, ledger = Path(row["raw_result_path"]), Path(row["raw_ledger_path"])
    assert digest(result_path) == row["raw_result_sha256"], "accepted result changed"
    assert digest(ledger) == row["raw_ledger_sha256"], "accepted ledger changed"
    result = json.loads(result_path.read_text())
    context = {"episode_id": result["episode_id"], "gazebo_seed": result["gazebo_seed"],
               "world": Path(result["world_file"]).name, "mission_mode": result["mission_mode"],
               "robot_count": result["robot_count"], "episode_start_sim_time": result["start_sim_time_sec"]}
    # Historical active fault state was not telemetry. Preserve declarations,
    # explicitly marking unavailable fields instead of fabricating new samples.
    pool_path = result_path.parent.parent / "summary.json"
    if pool_path.is_file():
        pool = json.loads(pool_path.read_text())
        episodes = pool.get("episodes", {})
        if isinstance(episodes, dict):
            old = episodes.get(result["episode_id"], {})
            settings = dict(old.get("settings") or {})
            if old.get("command"):
                settings["protocol"], smoke_sha = protocol_declaration(old["command"])
            else:
                smoke_sha = None
            context["configuration"] = {"legacy_declared_mode": old.get("mode"),
                                         "profile": old.get("profile"), "settings": settings,
                                         "manifest_path": str(pool_path), "manifest_sha256": digest(pool_path),
                                         "command": old.get("command"), "frozen_smoke_sha256": smoke_sha}
    metrics = LedgerMetrics(context)
    for line in ledger.read_text().splitlines():
        metrics.ingest(json.loads(line))
    audit = metrics.audit()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    evidence = {"episode_id": result["episode_id"], "cohort": row["cohort"],
                "result_path": str(result_path), "ledger_path": str(ledger),
                "result_sha256": digest(result_path), "ledger_sha256": digest(ledger),
                "record_count": len(metrics.events), "conservation": audit,
                "native_task_phase": result["task_phase"], "native_success": result["success"],
                "first_events": metrics.first_events,
                "streams": [metrics.report(result["start_sim_time_sec"], result["end_sim_time_sec"], *key)
                            for key in sorted(metrics.routes)]}
    (directory / "audit.json").write_text(json.dumps(evidence, indent=2, sort_keys=True)+"\n")
    if full_export:
        events = result_path.parent / "safety_events.jsonl"
        summary, _ = export(ledger, directory / "curves", result_path,
                            events if events.is_file() else None, context)
        evidence["export_directory"] = str(directory / "curves")
    assert digest(result_path) == row["raw_result_sha256"] and digest(ledger) == row["raw_ledger_sha256"]
    return {key: evidence[key] for key in ("episode_id", "cohort", "result_path", "ledger_path", "result_sha256",
            "ledger_sha256", "record_count", "native_task_phase", "native_success")} | {
                "status": audit["status"], "stream_count": len(audit["streams"]), "errors": audit["errors"],
                "audit_path": str(directory / "audit.json"), "export_directory": evidence.get("export_directory")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    accepted = json.loads(args.accepted_report.read_text())
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    requested = {"up10_rooms", "down10_rooms", "up100_lab", "down100_lab", "ttl_lab", "overflow_rooms", "single_failure_rooms"}
    selected_pairs = [pair for pair in accepted["paired_results"] if pair["case_id"] in requested]
    assert {pair["case_id"] for pair in selected_pairs} == requested
    selected = {pair[mode] for pair in selected_pairs for mode in ("ideal", "fault")}
    rows = accepted["episode_summaries"]
    assert len(rows) == len({row["episode_id"] for row in rows}) == 63
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        audits = list(pool.map(audit_one, [(row, str(root / row["episode_id"]), row["episode_id"] in selected) for row in rows]))
    by_id = {row["episode_id"]: row for row in rows}
    comparisons = []
    for pair in accepted["paired_results"]:
        ideal, fault = [json.loads(Path(by_id[pair[mode]]["raw_result_path"]).read_text()) for mode in ("ideal", "fault")]
        value = task_degradation_index(ideal, fault)
        assert value == tdi(ideal, fault) == pair["tdi"], f"frozen TDI changed: {pair['case_id']}"
        comparison = {"case_id": pair["case_id"], "tdi": value, "ideal": pair["ideal"], "fault": pair["fault"]}
        if pair in selected_pairs:
            ideal_dir, fault_dir = [root / pair[mode] / "curves" for mode in ("ideal", "fault")]
            reference = json.loads((ideal_dir / "summary.json").read_text())
            reference["export_directory"] = str(ideal_dir)
            current = json.loads((fault_dir / "summary.json").read_text())
            comparison["comparison"] = compare(current, reference, fault_dir)
            comparison["figure"] = str(fault_dir / "comparison.svg")
        comparisons.append(comparison)
    summary = {"status": "PASS" if all(row["status"] == "PASS" for row in audits) else "FAIL",
               "accepted_report": str(args.accepted_report.resolve()), "accepted_report_sha256": digest(args.accepted_report),
               "original_count": len(audits), "stream_count": sum(row["stream_count"] for row in audits),
               "curve_episode_count": len(selected), "paired_tdi_checks": len(comparisons),
               "audits": audits, "pairs": comparisons,
               "limits": ["application payload, not Wi-Fi", "legacy queue occupancy unavailable",
                          "legacy ACK receiver acceptance uninstrumented", "fixed descriptive matrix, not new task trials"]}
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")
    print(json.dumps({key: summary[key] for key in ("status", "original_count", "stream_count", "curve_episode_count", "paired_tdi_checks")}))
    if summary["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
