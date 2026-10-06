#!/usr/bin/env python3
"""Strict P3C evidence gate: native regressions, live configuration and accounting."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from check_p3b5_gate import episode_ok, native_completion_ok, ledger_audit
from export_gateway_metrics import digest, verify_live
from multi_robot_exploration.gateway_metrics import LedgerMetrics


def load(path):
    return json.loads(Path(path).read_text())


def monitor_graph_audit(graph):
    nodes = graph["nodes"]
    node = nodes["/gateway_metrics"]
    assert {name for name, _ in node["publishers"]} <= {"/rosout", "/parameter_events", "/gateway/metrics"}
    assert not node["clients"] and not node["action_clients"] and not node["action_servers"]
    assert "/gazebo/model_states" not in {name for name, _ in node["subscribers"]}
    assert "/gateway_monitor" not in nodes, "formal headless run unexpectedly started GUI"
    if "/gateway_configure_cli" in nodes:
        cli = nodes["/gateway_configure_cli"]
        assert {name for name, _ in cli["publishers"]} <= {"/rosout", "/parameter_events"}
        assert not cli["action_clients"]
        assert {name for name, _ in cli["clients"]} == {"/gateway/configure"}
    return {"status": "PASS", "metrics_application_publishers": ["/gateway/metrics"], "headless": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, nargs=3, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("never overwrite an audit")
    source = load(args.source)
    runtime = load(args.runtime / "checks.json")
    replay = load(args.replay / "summary.json")
    assert source["status"] == runtime["status"] == replay["status"] == "PASS"
    assert replay["original_count"] == 63 and replay["paired_tdi_checks"] == 31
    assert len(source["static_protocol_matrix"]["matrix"]) == 54
    assert runtime["gui_closed_collection_continues"] and runtime["live_replay"]["samples"] > 0
    assert runtime["actual_qt_apply_and_service_ack"] and runtime["metrics_shutdown_wall_sec"] < 5
    rows = [load(path) for path in args.episodes]
    assert {row["case"] for row in rows} == {"ideal", "forced", "dynamic"}
    assert len({row["git_commit"] for row in rows}) == 1
    assert all(row["source_digests"] == rows[0]["source_digests"] for row in rows)
    evidence = []
    for row in rows:
        assert row["runner_returncode"] == row["observer_returncode"] == row.get("configuration_returncode", 0) == 0
        assert not any(value for key, value in row.items() if key.endswith("_forced_shutdown"))
        result = row["result"]
        directory = Path(row["result_path"]).parent
        assert result["collision_events"] == 0 and result["battery_minimum_energy"] > 0
        if row["case"] in ("ideal", "forced"):
            assert result["rally_hold_sec"] == 5 and result["rally_position_tolerance_m"] == .35
            episode_ok(result)
        elif result["success"]:
            episode_ok(result)
        elif result.get("partial_completion"):
            native_completion_ok(result)
        if row["case"] == "forced":
            assert all(robot["battery_charge_count"] >= 1 for robot in result["robots"].values())
        for name, old_sha in row["evidence_sha256"].items():
            assert digest(directory / name) == old_sha, f"original task evidence changed: {name}"
        ledger = directory / "ledger.jsonl"
        temporal = ledger_audit(ledger)
        live_dir = directory / "ledger_metrics"
        live = verify_live(live_dir)
        final = load(live_dir / "summary.json")
        assert final["task_result"] == result and final["conservation"]["status"] == "PASS"
        engine = LedgerMetrics()
        for line in (live_dir / "inputs.jsonl").read_text().splitlines():
            engine.ingest(json.loads(line))
        assert engine.audit() == final["conservation"]
        graph = monitor_graph_audit(load(directory / "graph.json"))
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        assert any(e["event"] == "gateway_stop" for e in records)
        applied = [e for e in records if e["event"] == "configuration_applied"]
        if row["case"] == "dynamic":
            responses = [json.loads(line) for line in (directory / "configuration.jsonl").read_text().splitlines()
                         if json.loads(line)["event"] == "configuration_response"]
            assert len(responses) == len(applied) == 4 and all(e["successful"] for e in responses)
            assert [e["configuration"]["revision"] for e in applied] == [1, 2, 3, 4]
            assert all(any(s["configuration"].get("revision") == e["configuration"]["revision"]
                           for s in final["directions"]) or
                       any(json.loads(line)["window"][0]["configuration"].get("revision") == e["configuration"]["revision"]
                           for line in (live_dir / "live.jsonl").read_text().splitlines()) for e in applied)
        else:
            assert not applied
        evidence.append({"case": row["case"], "raw_summary": str(directory / "summary.json"),
                         "manifest": str(directory / "manifest.json"), "result_sha256": digest(row["result_path"]),
                         "ledger_sha256": digest(ledger), "live_metrics_sha256": digest(live_dir / "live.jsonl"),
                         "result": result, "temporal_audit": temporal, "live_replay": live,
                         "conservation": final["conservation"], "monitor_graph": graph,
                         "configuration_applied": applied, "first_events": final["first_events"],
                         "first_freshness_by_stream": [{key: r[key] for key in ("direction", "message_type", "sender", "recipient", "aoi")}
                                                        for r in final["streams"]]})
    accepted = load(replay["accepted_report"])
    qualified = [pair for pair in accepted["paired_results"] if pair["tdi"] is not None]
    originals = {item["episode_id"]: load(item["raw_result_path"]) for item in accepted["episode_summaries"]}
    fault_tasks = [originals[pair["fault"]] for pair in qualified]
    ideal_tasks = [originals[pair["ideal"]] for pair in qualified]
    task_rates = {"cohort": "22 qualified fixed rally pairs, original P3B.5 unchanged", "n": len(qualified),
                  "fault_success_rate": sum(task["success"] for task in fault_tasks)/len(qualified),
                  "fault_partial_rate": sum(task["partial_completion"] for task in fault_tasks)/len(qualified),
                  "mean_fault_rmst300_sec": sum(task["completion_time_sec"] if task["success"] else 300 for task in fault_tasks)/len(qualified),
                  "mean_ideal_rmst300_sec": sum(task["completion_time_sec"] for task in ideal_tasks)/len(qualified),
                  "original_tdi": accepted["combined_tdi"]}
    output = {"status": "PASS", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "frozen_commit": rows[0]["git_commit"], "source_audit": source, "runtime_probe": runtime,
              "accepted_replay": replay, "new_original_task_count": 3, "episodes": evidence,
              "task_rates": task_rates, "limits": ["application payload/fault sensitivity, not Wi-Fi PHY/MAC",
                  "integration seeds and descriptive pairs, no causal or worst-case guarantee",
                  "legacy queue occupancy and ACK accepted events unavailable, explicitly marked",
                  "low-sample p95/p99 remain null; no interpolation of missing delivery ages",
                  "real-time prefixes retained separately from complete-ledger reconstruction"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"status": "PASS", "new_tasks": 3, "accepted_originals": 63,
                      "live_samples": sum(e["live_replay"]["samples"] for e in evidence)}))


if __name__ == "__main__":
    main()
