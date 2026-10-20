#!/usr/bin/env python3
"""Derive closure accounting and descriptive findings from closed V21 receipts."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[9]
RUN = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes"
CLOSED = HERE / "closed_execution"


def read(path):
    return json.loads(path.read_text())


def ref(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(name, data):
    (HERE / name).write_text(json.dumps(data, indent=2) + "\n")


def main():
    main_path = CLOSED / "mr3_p2a_v21_diagnostic_outer/actual_wait.json"
    final_path = CLOSED / "mr3_p2a_v21_diagnostic_final_outer/actual_wait.json"
    outers = [read(main_path), read(final_path)]
    intervals = sorted((d["started_monotonic_ns"], d["ended_monotonic_ns"]) for d in outers)
    union = []
    for start, end in intervals:
        assert start <= end
        if union and start <= union[-1][1]:
            union[-1][1] = max(end, union[-1][1])
        else:
            union.append([start, end])
    total = Decimal(sum(end - start for start, end in union)) / Decimal(10**9)
    assert all(d["actual_waited"] and d["source_unchanged"] for d in outers)
    assert all(Decimal(d["actual_child_wait_seconds"]) == Decimal(
        d["ended_monotonic_ns"] - d["started_monotonic_ns"]) / Decimal(10**9) for d in outers)
    old = Decimal("38216.5104974146018")
    used = old + total
    summary_path = CLOSED / "mr3_p2a_v21_diagnostic/summary.json"
    summary = read(summary_path)
    commands = [summary["native"], summary["watcher"], *summary["audits"].values()]
    commands = [d for d in commands if "started_wall_monotonic_ns" in d]
    assert len(commands) == 9
    assert all(outers[0]["started_monotonic_ns"] <= d["started_wall_monotonic_ns"] <=
               d["ended_wall_monotonic_ns"] <= outers[0]["ended_monotonic_ns"] for d in commands)
    write("engineering_accounting_v1.json", {
        "schema": "mr3-exact-engineering-union-accounting-v1",
        "outer_receipts": [ref(main_path), ref(final_path)], "intervals_ns": intervals,
        "union_intervals_ns": union, "charge_seconds": str(total),
        "nested_command_count": len(commands), "all_nested_intervals_inside_main": True,
        "nested_extra_charge_seconds": "0", "previous_used_seconds": str(old),
        "approved_ceiling_seconds": "52000", "cumulative_used_seconds": str(used),
        "remaining_seconds": str(Decimal(52000) - used),
        "pilot_remaining_decisions": 1870, "pilot_remaining_seconds": "2905.9547395464029",
        "final_only_unused_seeds": [401, 402, 403], "budget_extension_approved": False,
        "historical_60000_proposal_remaining_seconds": str(Decimal(60000) - used),
        "full_admission_reservation_seconds": "20100",
        "historical_60000_proposal_current_shortfall_seconds": str(used + Decimal(20100) - Decimal(60000)),
        "cpu_only_excluded": ["unit tests", "preflight", "finite forensic record extraction", "archival verification"],
        "diagnostic_passed": summary["passed"], "qualification": False, "training_eligible": False,
    })
    worker_path = RUN / "worker0/worker_summary.json"
    worker = read(worker_path)
    episodes, submitted, returned = [], 0, 0
    evaluator_keys = ("correct_free_coverage_ratio", "observed_accuracy", "occupied_iou", "false_free_ratio",
                      "map_quality_pass", "robot_participation_pass", "success", "elapsed_sim_time_sec",
                      "collision_events", "collision_monitoring_active", "collision_monitoring_fresh",
                      "nav_goal_count", "nav_succeeded", "nav_canceled", "nav_aborted", "navigation_protocol_closed")
    for episode in worker["episodes"]:
        directory = Path(episode["output_directory"])
        evaluator_path = directory / (episode["epoch"] + ".json")
        evaluator = read(evaluator_path)
        transition_path = directory / "transitions.jsonl"
        records = [json.loads(line) for line in transition_path.read_text().splitlines() if line]
        steps = [r for r in records if r["kind"] == "step"]
        actions = episode["diagnostic_uniform_actions"]
        assert len(steps) == len(actions) == 32
        submitted += sum(a["action_submitted"] for a in actions)
        returned += sum(a["step_returned"] for a in actions)
        episodes.append({
            "directory": str(directory), "epoch": episode["epoch"],
            "references": [ref(evaluator_path), ref(transition_path), ref(directory / "summary.json")],
            "api_records": len(records), "reset_records": sum(r["kind"] == "reset" for r in records),
            "step_records": len(steps), "reason": episode["reason"],
            "reward_time_seconds": sum(r["info"]["dt"] for r in steps),
            "step_physical_time_seconds": sum(r["info"]["physical_dt"] for r in steps),
            "singleton_mask_steps": sum(a["legal_joint_actions"] == 1 for a in actions),
            "keep_888_steps": sum(a["action"] == 888 for a in actions),
            "evaluator": {k: evaluator[k] for k in evaluator_keys},
            "contact_ever_unhealthy": evaluator["contact_monitor_summary"]["ever_unhealthy"],
            "robots": evaluator["robots"],
            "closure": read(directory / "summary.json")["closed"],
        })
    write("diagnostic_findings_v1.json", {
        "schema": "mr3-short-diagnostic-descriptive-findings-v1", "freeze": summary["freeze"],
        "references": [ref(worker_path), ref(summary_path)], "episodes": episodes,
        "submitted": submitted, "returned": returned,
        "native_actual_wait_seconds": summary["native"]["wall_seconds"],
        "full_activity_union_seconds": str(total),
        "returned_per_native_wall_second": str(Decimal(returned) / Decimal(summary["native"]["wall_seconds"])),
        "returned_per_full_activity_wall_second": str(Decimal(returned) / total),
        "rate_scope": "two short uniform-action diagnostic episodes, not qualified PPO training throughput",
        "diagnostic_passed": summary["passed"], "qualification": False, "training_eligible": False,
        "policy_calls": 0, "gpu_calls": summary["gpu_calls"], "optimizer_steps": summary["optimizer_steps"],
    })
    absence_path = CLOSED / "mr3_p2a_v21_diagnostic_absence.json"
    absence = read(absence_path)
    identities = absence["saved_identities"] + [outers[1]["coordinator_identity"], outers[1]["child_identity"]]
    unique = {(i["pid"], i["start_ticks"]): i for i in identities}
    present, unreadable = [], []
    observed = time.monotonic_ns()
    for (pid, ticks), identity in unique.items():
        try:
            value = Path(f"/proc/{pid}/stat").read_text()
        except FileNotFoundError:
            continue
        except OSError as error:
            unreadable.append({"identity": identity, "error": repr(error)})
            continue
        fields = value[value.rfind(")") + 2:].split()
        if int(fields[19]) == ticks:
            present.append({"identity": identity, "actual_state": fields[0]})
    write("later_identity_absence_v1.json", {
        "schema": "mr3-later-identity-absence-v1", "observed_monotonic_ns": observed,
        "references": [ref(absence_path), ref(final_path)], "saved_identity_count": len(unique),
        "saved_identities": list(unique.values()), "present": present, "unreadable": unreadable,
        "absence_passed": not present and not unreadable, "diagnostic_passed": False,
        "scope": "saved native/reader/outer identities plus the final helper and its already waited child only",
    })
    assert not present and not unreadable and len(unique) == 111
    print(f"closed FAIL; charge={total}; remaining={Decimal(52000)-used}; 111 identities absent")


if __name__ == "__main__":
    main()
