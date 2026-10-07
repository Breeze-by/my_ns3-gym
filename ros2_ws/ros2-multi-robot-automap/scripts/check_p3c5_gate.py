#!/usr/bin/env python3
"""Audit every original P3C.5 cell and export stratified traffic/cost inventories."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/"src/multi_robot_exploration"))
from multi_robot_exploration.traffic_audit import audit_traffic
from check_p3b5_gate import native_completion_ok, ledger_audit
from check_p3c_gate import monitor_graph_audit
from export_gateway_metrics import verify_live


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("p3c5_traffic_manifest.json"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
    assert all(row["source_digests"] == originals[0]["source_digests"] for row in originals)
    assert all(row["config"] == config for row in originals), "executed manifest differs from predeclaration"
    evidence, strata, costs, burst_rows = [], [], [], []
    for row in sorted(originals, key=lambda item: item["case"]):
        name, result, scenario = row["case"], row["result"], config["cases"][row["case"]]
        directory = Path(row["result_path"]).parent
        assert row["runner_returncode"] == row["observer_returncode"] == 0
        assert not any(value for key, value in row.items() if key.endswith("_forced_shutdown"))
        for relative, expected in row["evidence_sha256"].items():
            assert sha(directory/relative) == expected, f"raw evidence changed: {name}/{relative}"
        assert result["collision_events"] == 0 and result["battery_minimum_energy"] > 0
        assert not result.get("battery_exhaustion_events", 0) and not result.get("failed_robot_names", [])
        assert result["rally_hold_sec"] == 5 and result["rally_position_tolerance_m"] == .35
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
        start = result["start_sim_time_sec"]
        end = start+(result["completion_time_sec"] if result["success"] else config["duration_sec"])
        audit, cost_rows = audit_traffic(records, start, end, scenario["admission_protocol"])
        temporal = ledger_audit(directory/"ledger.jsonl")
        graph = monitor_graph_audit(json.loads((directory/"graph.json").read_text()))
        live = verify_live(directory/"ledger_metrics")
        assert json.loads((directory/"ledger_metrics/summary.json").read_text())["task_result"] == result
        evidence.append({"case": name, "scenario": scenario, "raw_directory": str(directory),
            "summary_sha256": sha(directory/"summary.json"), "ledger_sha256": sha(directory/"ledger.jsonl"),
            "result_sha256": sha(row["result_path"]), "result": result, "audit": audit,
            "temporal_audit": temporal, "graph_audit": graph, "live_replay": live})
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
        "strata_rows": len(strata), "attempt_cost_rows": len(costs), "burst_rows": len(burst_rows),
        "conclusion": {"capacity_bottleneck": "not demonstrated; no serialization/MAC model exists in this gateway",
            "negative_result": "通信不是瓶颈：当前 ideal 应用传输没有带宽排队证据；Wi-Fi 是否成为瓶颈尚未测量",
            "delay_and_expiry": "injected delay/loss and finite admission handshake are measured separately from capacity contention",
            "next_research_direction": "keep the measured load; test communication savings and calibrate network before considering RL",
            "no_traffic_inflation": True, "actual_airtime_and_radio_joules": "unavailable before P4B; all bytes and conditional coefficients retained"},
        "artifacts_sha256": {path.name: sha(path) for path in args.output.iterdir()}}
    (args.output/"summary.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({key: result[key] for key in ("status", "original_count", "native_task_status_counts", "strata_rows", "attempt_cost_rows")}))


if __name__ == "__main__":
    main()
