#!/usr/bin/env python3
"""Audit every original P3C.5 cell and export stratified traffic/cost inventories."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/"src/multi_robot_exploration"))
from multi_robot_exploration.traffic_audit import audit_traffic
from check_p3b5_gate import native_completion_ok, ledger_audit
from check_p3c_gate import monitor_graph_audit
from export_gateway_metrics import verify_live
from run_p3b5_tasks import episode_command


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_interval(result, horizon):
    """Measure the actual native episode; clip timeout polling beyond its horizon."""
    start, end = result["start_sim_time_sec"], result["end_sim_time_sec"]
    assert end > start and abs(end-start-result["elapsed_sim_time_sec"]) < 1e-6
    return start, min(end, start+horizon)


def native_safety_ok(result):
    """Mission failure remains measurable; native robot safety must still pass."""
    assert result["battery_enabled"] and result["collision_monitoring_active"]
    assert result["collision_events"] == 0 and result["battery_minimum_energy"] > 0
    assert not result["failed_robots"]
    assert len(result["robots"]) == result["robot_count"] == result["required_robot_count"]
    assert set(result["robots"]) == set(result["required_robot_names"])
    for robot in result["robots"].values():
        assert robot["battery_message_count"] > 0 and robot["collision_message_count"] > 0
        assert robot["battery_minimum_energy"] > 0 and robot["battery_final_energy"] > 0
        assert robot["battery_mode"] != "FAILED" and robot["collision_events"] == 0
    assert result["rally_hold_sec"] == 5 and result["rally_position_tolerance_m"] == .35
    assert result["rally_linear_tolerance_mps"] == .05 and result["rally_angular_tolerance_radps"] == .1


def declaration_audit(row, config, directory):
    """Bind the cached result and executed command to the original declaration."""
    manifest = json.loads((directory/"manifest.json").read_text())
    assert all(row[key] == value for key, value in manifest.items()), "summary differs from original manifest"
    assert row["config"] == config
    result_path = directory/(directory.name+".json")
    assert Path(row["result_path"]).resolve() == result_path.resolve(), "native result path mismatch"
    result = json.loads(result_path.read_text())
    assert row["result"] == result, "cached native result differs from original file"
    name, scenario = row["case"], config["cases"][row["case"]]
    case = {"id": name, "scenario": name, "mode": "rally", "profile": "online"}
    expected = episode_command(case, scenario, scenario.get("profile", {}), scenario["mode"], directory, config)
    expected[expected.index("--shutdown-timeout")+1] = str(config.get("owner_shutdown_timeout_sec", 60))
    if scenario["admission_protocol"]:
        expected.append("--gateway-admission-protocol")
    assert row["command"] == expected, "executed command differs from predeclared cell"
    assert result["episode_id"] == directory.name and result["mission_mode"] == "rally"
    assert result["gazebo_seed"] == scenario["seed"] and result["robot_count"] == scenario["robot_count"]
    assert Path(result["world_file"]).name == scenario["world"]
    for key in ("target_x", "target_y"):
        assert result[key] is None or result[key] == scenario[key], "observed target differs from declaration"
    for robot in result["robots"].values():
        assert robot["battery_initial_energy"] == scenario["energy"] and robot["battery_capacity"] == 100
    return {"status": "PASS", "manifest_command_and_native_result_bound": True}


def audit_original(item):
    row, config = item
    began = time.monotonic()
    name, result, scenario = row["case"], row["result"], config["cases"][row["case"]]
    directory = Path(row["result_path"]).parent
    assert row["runner_returncode"] == row["observer_returncode"] == 0
    assert not any(value for key, value in row.items() if key.endswith("_forced_shutdown"))
    for relative, expected in row["evidence_sha256"].items():
        assert sha(directory/relative) == expected, f"raw evidence changed: {name}/{relative}"
    declaration = declaration_audit(row, config, directory)
    native_safety_ok(result)
    assert result["robot_count"] == scenario["robot_count"]
    if result["success"] or result.get("partial_completion"):
        native_completion_ok(result)
    if name == "forced2":
        assert all(robot["battery_charge_count"] >= 1 for robot in result["robots"].values())
    records = [json.loads(line) for line in (directory/"ledger.jsonl").read_text().splitlines()]
    assert any(e["event"] == "gateway_stop" for e in records), "gateway did not close"
    launch_text = "\n".join(path.read_text() for path in (directory/"launch").glob("*.log"))
    for node in ("ideal_gateway", "gateway_metrics"):
        assert re.search(r"\["+node+r"-\d+\]: process has finished cleanly", launch_text), f"{node} did not exit cleanly"
        assert not re.search(r"\["+node+r"-\d+\].*(?:failed to terminate|process has died)", launch_text), f"{node} shutdown was forced"
    start, end = native_interval(result, config["duration_sec"])
    audit, cost_rows = audit_traffic(records, start, end, scenario["admission_protocol"])
    temporal = ledger_audit(directory/"ledger.jsonl")
    graph = monitor_graph_audit(json.loads((directory/"graph.json").read_text()))
    live = verify_live(directory/"ledger_metrics")
    assert json.loads((directory/"ledger_metrics/summary.json").read_text())["task_result"] == result
    evidence = {"case": name, "scenario": scenario, "raw_directory": str(directory),
        "summary_sha256": sha(directory/"summary.json"), "ledger_sha256": sha(directory/"ledger.jsonl"),
        "result_sha256": sha(row["result_path"]), "result": result, "audit": audit,
        "declaration_audit": declaration, "temporal_audit": temporal, "graph_audit": graph, "live_replay": live,
        "audit_wall_sec": time.monotonic()-began}
    print(json.dumps({"case": name, "audit": "PASS", "native_success": result["success"],
                      "native_phase": result["task_phase"], "live_samples": live["samples"],
                      "audit_wall_sec": evidence["audit_wall_sec"]}), flush=True)
    return evidence, cost_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("p3c5_traffic_manifest.json"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3, choices=(1, 2, 3))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("never overwrite an audit")
    config = json.loads(args.manifest.read_text())
    source, runtime = (json.loads(path.read_text()) for path in (args.source, args.runtime/"checks.json"))
    assert source["status"] == runtime["status"] == "PASS"
    summaries = list(args.run_root.glob("*/summary.json"))
    originals = [json.loads(path.read_text()) for path in summaries]
    assert len(originals) == len(config["cases"]) and {row["case"] for row in originals} == set(config["cases"])
    assert len({row["git_commit"] for row in originals}) == 1, "task cohort not frozen at one commit"
    root = PROJECT.parents[1]
    relative = args.manifest.resolve().relative_to(root)
    frozen_manifest = subprocess.check_output(["git", "show", f"{originals[0]['git_commit']}:{relative}"], cwd=root)
    assert json.loads(frozen_manifest) == config, "manifest was not committed at the task freeze"
    assert all(row["source_digests"] == originals[0]["source_digests"] for row in originals)
    assert all(row["config"] == config for row in originals), "executed manifest differs from predeclaration"
    evidence, strata, costs, burst_rows = [], [], [], []
    items = [(row, config) for row in sorted(originals, key=lambda item: item["case"])]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for episode, cost_rows in pool.map(audit_original, items):
            name, audit = episode["case"], episode["audit"]
            evidence.append(episode)
            strata.extend({"case": name, **item} for item in audit["strata"])
            costs.extend({"case": name, **item} for item in cost_rows)
            burst_rows.extend({"case": name, **item} for item in audit["bursts"])
    args.output.mkdir(parents=True, exist_ok=False)
    for filename, rows in (("strata.jsonl", strata), ("attempt_costs.jsonl", costs), ("bursts.jsonl", burst_rows)):
        with (args.output/filename).open("w") as stream:
            for item in rows:
                stream.write(json.dumps(item, sort_keys=True)+"\n")
    with (args.output/"strata.csv").open("w", newline="") as stream:
        fields = ["case", "phase", "message_type", "direction", "robot", "phase_duration_sec",
                  "generated_hz", "offered_payload_bps", "tx_envelope_cdr_bps", "compression_payload_fraction"]
        count_fields = sorted({key for row in strata for key in row["counts"]})
        writer = csv.DictWriter(stream, fieldnames=fields+count_fields)
        writer.writeheader()
        for row in strata:
            writer.writerow({**{key: row[key] for key in fields}, **row["counts"]})
    statuses = Counter(row["result"]["task_phase"] for row in evidence)
    result = {"status": "PASS", "checkpoint": "P3C.5", "scope": "application/protocol/observability audit, not Wi-Fi calibration",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "task_cohort_commit": originals[0]["git_commit"],
        "traffic_manifest_sha256": sha(args.manifest), "source_digests": originals[0]["source_digests"],
        "source_audit": source, "runtime_probe": runtime, "original_count": len(evidence),
        "native_task_status_counts": dict(statuses), "episodes": evidence,
        "native_success_count": sum(e["result"]["success"] for e in evidence),
        "native_termination_counts": dict(Counter(e["result"]["termination_reason"] for e in evidence)),
        "read_only_audit_workers": args.workers,
        "strata_rows": len(strata), "attempt_cost_rows": len(costs), "burst_rows": len(burst_rows),
        "conclusion": {"capacity_bottleneck": "not demonstrated; no serialization/MAC model exists in this gateway",
        "capacity_measurement_status": "not testable in this application model; Wi-Fi capacity has not been measured",
            "delay_and_expiry": "injected delay/loss and finite admission handshake are measured separately from capacity contention",
            "next_research_direction": "keep the measured load; test communication savings and calibrate network before considering RL",
            "no_traffic_inflation": True, "actual_airtime_and_radio_joules": "unavailable before P4B; all bytes and conditional coefficients retained"},
        "artifacts_sha256": {path.name: sha(path) for path in args.output.iterdir()}}
    (args.output/"summary.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({key: result[key] for key in ("status", "original_count", "native_task_status_counts", "strata_rows", "attempt_cost_rows")}))


if __name__ == "__main__":
    main()
