#!/usr/bin/env python3
"""Run frozen ideal/fault pairs serially and retain every outcome and ledger."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
import subprocess
import sys
from types import SimpleNamespace

from run_p2d_baseline import PROJECT_ROOT, build_manifest, file_digest

CONFIG = Path(__file__).with_name("p3b5_fault_manifest.json")


def stamp(event):
    return float(event.get("time", event.get("event_time", 0.)))


def ledger_metrics(path, start, end):
    """Unique application receipt PDR, attempt loss, source AoI and wait intervals.

    AoI is integrated over receiver-accepted source versions. No receipt is
    explicitly unavailable, never zero AoI. ACKs remain in separate streams.
    """
    streams = defaultdict(lambda: {"events": Counter(), "reasons": Counter(),
                                   "born": set(), "accepted": {}, "updates": []})
    waits, waiting = [], None
    last_sequence = {}
    reorder_count = 0
    local_events = Counter()
    failures = Counter()
    with path.open() as source:
        for line in source:
            event = json.loads(line)
            when = stamp(event)
            kind = event["event"]
            if kind in ("coordinator_wait", "coordinator_recovered"):
                if kind == "coordinator_wait" and waiting is None:
                    waiting = when
                elif kind == "coordinator_recovered" and waiting is not None:
                    waits.append((waiting, when))
                    waiting = None
            if start <= when <= end:
                local_events[kind] += 1
                if event.get("reason"):
                    failures[event["reason"]] += 1
            if "direction" not in event or "message_type" not in event:
                continue
            key = (event["direction"], event["message_type"],
                   event.get("sender", ""), event.get("recipient", ""))
            state = streams[key]
            identity = event.get("message_id")
            if start <= when <= end:
                state["events"][kind] += 1
                if event.get("reason"):
                    state["reasons"][event["reason"]] += 1
                if kind == "enqueue":
                    state["born"].add(identity)
                if kind == "delivered" and "sequence" in event:
                    previous = last_sequence.get(key, 0)
                    reorder_count += event["sequence"] < previous
                    last_sequence[key] = max(previous, event["sequence"])
            if kind == "accepted" and "source_time" in event and when <= end:
                state["accepted"].setdefault(identity, (when, event["source_time"]))
                state["updates"].append((when, float(event["source_time"])))
    if waiting is not None:
        waits.append((waiting, end))
    result = []
    for key, state in sorted(streams.items()):
        born = state["born"]
        receipts = state["accepted"]
        delivered = born & receipts.keys()
        ages = [receipts[identity][0] - receipts[identity][1] for identity in delivered]
        # Integrate age only after information exists; separately account for
        # the unavailable prefix. Out-of-order source stamps never reduce age.
        current_source, cursor, area, unavailable = None, start, 0., 0.
        for when, generated in sorted(state["updates"]):
            when = max(start, when)
            delta = max(0., when - cursor)
            if current_source is None:
                unavailable += delta
            else:
                area += delta * (cursor - current_source) + delta * delta / 2
            current_source = generated if current_source is None else max(current_source, generated)
            cursor = when
        delta = max(0., end - cursor)
        if current_source is None:
            unavailable += delta
        else:
            area += delta * (cursor - current_source) + delta * delta / 2
        observed_duration = end - start - unavailable
        events = dict(state["events"])
        result.append({"direction": key[0], "message_type": key[1], "sender": key[2],
                       "recipient": key[3], "events": events, "drop_reasons": dict(state["reasons"]),
                       "generated_unique": len(born), "accepted_unique": len(delivered),
                       "application_pdr": len(delivered) / len(born) if born else None,
                       "mean_source_delay_sec": sum(ages) / len(ages) if ages else None,
                       "mean_aoi_observed_sec": area / observed_duration if observed_duration > 0 else None,
                       "unavailable_sec": unavailable})
    return {"streams": result, "events": dict(local_events), "reasons": dict(failures),
            "reordered_delivery_attempts": reorder_count,
            "stale_wait_sec": sum(max(0., min(end, b) - max(start, a)) for a, b in waits),
            "wait_intervals": waits, "ledger_sha256": file_digest(path)}


def tdi(ideal, fault):
    # Process-mode success and collision-marked COMPLETE never qualify.
    if ideal.get("mission_mode") != "rally" or not ideal.get("success") or ideal.get("task_phase") != "COMPLETE":
        return None
    if fault.get("success") and fault.get("task_phase") == "COMPLETE":
        return 0.
    if fault.get("partial_completion"):
        return 1 - fault["required_robot_count"] / ideal["robot_count"]
    return 1.


def mean_ci(values):
    if not values:
        return {"n": 0, "mean": None, "ci95": None}
    mean = sum(values) / len(values)
    rng = random.Random(17011)
    bootstrap = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(10000))
    return {"n": len(values), "mean": mean, "ci95": [bootstrap[249], bootstrap[9749]],
            "method": "paired episode percentile bootstrap, seed17011; descriptive fixed matrix"}


def pair_statistics(config, pairs, episodes):
    rows, values = [], []
    for case_id, pair in pairs.items():
        ideal, fault = (episodes.get(pair[mode], {}).get("result") for mode in ("ideal", "fault"))
        if not ideal or not fault:
            rows.append({"case_id": case_id, "infrastructure_failure": True, **pair})
            continue
        value = tdi(ideal, fault)
        if value is not None:
            values.append(value)
        rows.append({"case_id": case_id, **pair, "tdi": value,
                     "ideal_status": ideal["termination_reason"], "fault_status": fault["termination_reason"],
                     "ideal_complete": ideal.get("success") and ideal["task_phase"] == "COMPLETE",
                     "fault_complete": fault.get("success") and fault["task_phase"] == "COMPLETE",
                     "fault_partial": fault.get("partial_completion", False),
                     "horizon_penalized_time_delta_sec": (
                         fault["completion_time_sec"] if fault.get("success") and fault.get("completion_time_sec") is not None
                         else config["duration_sec"]
                     ) - (ideal["completion_time_sec"] if ideal.get("success") and ideal.get("completion_time_sec") is not None
                          else config["duration_sec"])})
    return {"pairs": rows, "tdi": mean_ci(values)}


def episode_command(case, scenario, profile, mode, directory, config):
    identity = directory.name
    command = [sys.executable, str(PROJECT_ROOT / "scripts/ros_smoke_test.py"),
               "--world", scenario["world"], "--robot-count", str(scenario["robot_count"]),
               "--gazebo-seed", str(scenario["seed"]), "--startup-timeout", "600",
               "--message-timeout", "90", "--shutdown-timeout", "60",
               "--evaluation-duration", str(config["duration_sec"]), "--evaluation-wait-timeout", "900",
               "--coverage-threshold", str(config["coverage_threshold"] if case["mode"] == "coverage" else 0),
               "--mission-mode", case["mode"], "--gateway-mode", mode,
               "--gateway-seed", str(config["fault_seed"]), "--battery", "--battery-capacity", "100",
               "--battery-initial-energy", str(scenario["energy"]),
               "--target-x", str(scenario["target_x"]), "--target-y", str(scenario["target_y"]),
               "--rally-max-concurrent", "2", "--disable-global-battery-rally-pause",
               "--episode-id", identity, "--collect-fault-result", "--dwell-seconds", "0",
               "--evaluation-output-dir", str(directory), "--log-dir", str(directory / "launch"),
               "--gateway-ledger-path", str(directory / "ledger.jsonl"),
               "--bypass-audit-output", str(directory / "graph.json")]
    if case["mode"] in ("target", "rally"):
        command.append("--target-detection")
    if case["mode"] == "rally":
        command.append("--rally")
    for key, option in (("charge_duration", "battery-charge-duration"),
                        ("safety_margin", "battery-safety-margin"), ("return_timeout", "battery-return-timeout")):
        if key in scenario:
            command += ["--" + option, str(scenario[key])]
    for key, value in profile.items():
        # Ideal has the same TTL/deadline and load but no injected physical
        # robot failure. Such failure is part of the fault intervention.
        if mode == "ideal" and key.startswith("inject_failure"):
            continue
        command += ["--" + key.replace("_", "-"), json.dumps(value) if isinstance(value, list) else str(value)]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--ros-domain-base", type=int, default=170)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    cases = config["cases"]
    if args.cases:
        if set(args.cases) - {case["id"] for case in cases}:
            parser.error("unknown case")
        cases = [case for case in cases if case["id"] in args.cases]
    if not args.run_id or Path(args.run_id).name != args.run_id:
        parser.error("run id must be a single directory name")
    base = PROJECT_ROOT / "log/p3b5" / args.run_id
    episodes, pairs, planned = {}, {}, {}
    for case in cases:
        scenario = config["scenarios"][case["scenario"]]
        profile = config["profiles"][case["profile"]]
        pair = {}
        for mode in ("ideal", "fault"):
            # Reuse one exact same physical/protocol ideal control where the
            # sole difference between cases is the network intervention.
            settings = {"scenario": scenario, "mission_mode": case["mode"],
                        "deadline": profile.get("navigation_command_deadline_sec", 90),
                        "capacity": profile.get("gateway_queue_capacity", 0)}
            digest = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:10]
            identity = f"{args.run_id}_ideal_{case['scenario']}_{case['mode']}_{digest}" if mode == "ideal" else f"{args.run_id}_{case['id']}_fault"
            pair[mode] = identity
            planned.setdefault(identity, {"case": case, "scenario": scenario, "profile": profile,
                                         "mode": mode, "settings": settings})
        pairs[case["id"]] = pair
    if args.validate_only:
        for item in planned.values():
            world = PROJECT_ROOT / "src/multi_robot/worlds" / item["scenario"]["world"]
            if not world.is_file():
                parser.error(f"missing world {world}")
        print(json.dumps({"cases": len(cases), "episodes": len(planned), "pairs": pairs}, indent=2))
        return 0
    if base.exists() and not args.resume:
        parser.error("run exists; never overwrite evidence")
    base.mkdir(parents=True, exist_ok=True)
    manifest_args = SimpleNamespace(robot_count=3, duration=config["duration_sec"], goal_timeout=60,
        startup_timeout=600, message_timeout=90, evaluation_wait_timeout=900, shutdown_timeout=60,
        ros_domain_base=args.ros_domain_base, seeds=[101, 202, 303, 707], scenarios=list(config["scenarios"]),
        skip_cross_check=True, rally_assignment_objective="minimax", disable_map_safe_rally_order=False,
        enable_global_battery_rally_pause=False, disable_global_battery_rally_pause=True, rally_max_concurrent=2)
    manifest = build_manifest(args.config, manifest_args)
    manifest["task_stack_clean"] = all(line.startswith("?? 260929_report/") or line.startswith('?? "260929_report/')
                                       for line in manifest["worktree_status"])
    manifest["permitted_untracked_user_materials"] = "260929_report/ (recorded, untouched, excluded from task stack)"
    manifest["p3b5_runner_sha256"] = file_digest(Path(__file__))
    manifest["world_sha256"] = {name: file_digest(PROJECT_ROOT / "src/multi_robot/worlds" / scenario["world"])
                                  for name, scenario in config["scenarios"].items()}
    if not manifest["task_stack_clean"]:
        parser.error("commit task-stack changes before experiments")
    summary_path = base / "summary.json"
    if args.resume:
        previous = json.loads(summary_path.read_text())
        if (previous["manifest"]["git_commit"] != manifest["git_commit"]
                or previous["manifest"]["source_digests"] != manifest["source_digests"]
                or previous["config"] != config or previous["pairs"] != pairs):
            parser.error("resume requires exact original commit/config/cases")
        episodes = previous["episodes"]
        manifest = previous["manifest"]
    summary = {"schema_version": 1, "config": config, "manifest": manifest,
               "pairs": pairs, "episodes": episodes,
               "created_at_utc": datetime.now(timezone.utc).isoformat()}
    (base / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    for index, (identity, item) in enumerate(planned.items()):
        if identity in episodes:
            continue
        directory = base / identity
        directory.mkdir()
        command = episode_command(item["case"], item["scenario"], item["profile"], item["mode"], directory, config)
        env = os.environ.copy()
        env["ROS_DOMAIN_ID"] = str(20 + (args.ros_domain_base + index - 20) % 210)
        row = {**item, "command": shlex.join(command), "ros_domain_id": env["ROS_DOMAIN_ID"],
               "gazebo_master_uri": env.get("GAZEBO_MASTER_URI"), "result_path": str(directory / (identity + ".json"))}
        print(f"RUN {index + 1}/{len(planned)} {identity}", flush=True)
        with (directory / "runner.log").open("w") as log:
            process = subprocess.run(command, env=env, cwd=PROJECT_ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        row["runner_returncode"] = process.returncode
        result_path = directory / (identity + ".json")
        row["infrastructure_failure"] = not result_path.exists() or process.returncode != 0
        if result_path.exists():
            row["result"] = json.loads(result_path.read_text())
            row["result_sha256"] = file_digest(result_path)
            result = row["result"]
            if (directory / "ledger.jsonl").exists():
                row["communication"] = ledger_metrics(directory / "ledger.jsonl", result["start_sim_time_sec"], result["end_sim_time_sec"])
            row["graph_sha256"] = file_digest(directory / "graph.json") if (directory / "graph.json").exists() else None
        episodes[identity] = row
        summary["statistics"] = pair_statistics(config, pairs, episodes)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"RESULT {identity} infra={row['infrastructure_failure']} status={row.get('result', {}).get('termination_reason')}", flush=True)
    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary["statistics"] = pair_statistics(config, pairs, episodes)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"summary": str(summary_path), "tdi": summary["statistics"]["tdi"]}), flush=True)
    return int(any(row["infrastructure_failure"] for row in episodes.values()))


if __name__ == "__main__":
    raise SystemExit(main())
