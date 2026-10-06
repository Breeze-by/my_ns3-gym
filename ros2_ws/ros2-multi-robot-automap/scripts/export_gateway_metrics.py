#!/usr/bin/env python3
"""Read-only gateway replay/export and same-configuration task comparison."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/multi_robot_exploration"))
from multi_robot_exploration.gateway_metrics import LedgerMetrics, event_stamp, task_degradation_index, validate_pair_configuration
from multi_robot_exploration.metrics_io import render_svg, save_final, windows


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(ledger, output, episode=None, task_events=None, context=None):
    result = json.loads(Path(episode).read_text()) if episode else None
    metadata = dict(context or {})
    if result:
        metadata.update(episode_id=result["episode_id"], gazebo_seed=result["gazebo_seed"],
                        world=Path(result["world_file"]).name, mission_mode=result["mission_mode"],
                        robot_count=result["robot_count"], episode_start_sim_time=result["start_sim_time_sec"])
    metrics = LedgerMetrics(metadata)
    for line in Path(ledger).read_text().splitlines():
        metrics.ingest(json.loads(line))
    if task_events:
        last_battery = {}
        for line in Path(task_events).read_text().splitlines():
            raw = json.loads(line)
            topic, data = raw["topic"], raw["data"]
            when = float(raw["observer_time"])
            if topic == "/task_state":
                metrics.add_task_event({"event": "task_phase", "phase": data, "event_time": when})
            elif topic == "/robot_failure":
                metrics.add_task_event({"event": "robot_failure", "data": data, "event_time": when})
            elif topic.endswith("/battery_state"):
                robot = topic.split("/")[1]
                state = (data.get("mode"), data.get("return_count"), data.get("charge_count"))
                if last_battery.get(robot) != state:
                    metrics.add_task_event({"event": "battery_transition", "robot": robot, "data": data, "event_time": when})
                    last_battery[robot] = state
    start = result["start_sim_time_sec"] if result else metadata.get("episode_start_sim_time")
    end = result["end_sim_time_sec"] if result else None
    summary = save_final(metrics, output, start, end, result)
    summary["source_sha256"] = {"ledger": digest(ledger), "episode": digest(episode) if episode else None,
                                "task_events": digest(task_events) if task_events else None}
    consumed = [e for e in metrics.events if e.get("event") == "consumed" and e.get("message_type") == "target_detection"]
    summary["detection_chain"] = [
        {"message_id": e.get("message_id"), "local_confirm_time": e.get("local_confirm_time"),
         "delivery_time": e.get("delivery_time"), "consumed_time": e.get("consumed_time"),
         "confirm_to_delivery_sec": e.get("delivery_time", 0) - e.get("local_confirm_time", 0)
           if e.get("delivery_time") is not None and e.get("local_confirm_time") is not None else None,
         "delivery_to_consumed_sec": e.get("consumed_time", 0)-e.get("delivery_time", 0)
           if e.get("consumed_time") is not None and e.get("delivery_time") is not None else None}
        for e in consumed]
    (Path(output) / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return summary, metrics


def compare(current, reference, output):
    validate_pair_configuration(current, reference)
    ideal, fault = reference.get("task_result"), current.get("task_result")
    result = {"tdi": task_degradation_index(ideal, fault) if ideal and fault else None,
              "ideal_task": ideal, "fault_task": fault,
              "scope": "descriptive same-configuration pair; application fault model, not Wi-Fi"}
    result["task_metrics"] = {mode: {key: task.get(key) for key in (
        "success", "partial_completion", "failure_reason", "termination_reason", "task_phase", "completion_time_sec",
        "time_to_detect_sec", "time_to_rally_sec", "correct_free_coverage_ratio", "total_path_length_m",
        "battery_minimum_energy", "battery_total_returns", "battery_total_charges", "collision_events")}
        for mode, task in (("ideal", ideal), ("fault", fault)) if task}
    if ideal and fault:
        result["rmst_300_delta_sec"] = (fault["completion_time_sec"] if fault.get("success") else 300) - (
            ideal["completion_time_sec"] if ideal.get("success") else 300)
        result["deltas"] = {key: fault.get(key) - ideal.get(key) if isinstance(fault.get(key), (int, float))
                            and isinstance(ideal.get(key), (int, float)) else None for key in
                            ("correct_free_coverage_ratio", "total_path_length_m", "battery_minimum_energy", "collision_events")}
    (Path(output) / "comparison.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = [json.loads(line) for line in (Path(output) / "windows.jsonl").read_text().splitlines()]
    ref_dir = Path(reference["export_directory"])
    ref = [json.loads(line) for line in (ref_dir / "windows.jsonl").read_text().splitlines()]
    render_svg(Path(output) / "comparison.svg", rows, reference=ref)
    return result


def verify_live(directory):
    directory = Path(directory)
    records = [json.loads(line) for line in (directory / "inputs.jsonl").read_text().splitlines()]
    metrics, cursor, count = LedgerMetrics(), 0, 0
    for line in (directory / "live.jsonl").open():
        sample = json.loads(line)
        count += 1
        stop = sample["ledger_record_count"]
        for event in records[cursor:stop]:
            metrics.ingest(event)
        cursor = stop
        start, when = sample["context"]["episode_start_sim_time"], sample["sim_time"]
        expected = [metrics.report(max(start, when-1), when, d) for d in ("uplink", "downlink")]
        if expected != sample["window"]:
            raise AssertionError(f"live/replay source mismatch at {when}")
    if not count:
        raise AssertionError("no live samples to verify")
    return {"status": "PASS", "samples": count, "input_records": len(records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--episode", type=Path)
    parser.add_argument("--task-events", type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--verify-live", type=Path)
    args = parser.parse_args()
    if args.verify_live:
        print(json.dumps(verify_live(args.verify_live), sort_keys=True))
        return
    if args.ledger is None or args.output is None:
        parser.error("--ledger and --output are required for export")
    if args.output.exists():
        parser.error("output exists; never overwrite evidence")
    context = json.loads(args.context.read_text()) if args.context else {}
    summary, _ = export(args.ledger, args.output, args.episode, args.task_events, context)
    if args.reference:
        reference = json.loads((args.reference / "summary.json").read_text())
        reference["export_directory"] = str(args.reference)
        compare(summary, reference, args.output)
    print(json.dumps({"status": summary["conservation"]["status"], "output": str(args.output),
                      "streams": len(summary["conservation"]["streams"])}))
    if summary["conservation"]["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
