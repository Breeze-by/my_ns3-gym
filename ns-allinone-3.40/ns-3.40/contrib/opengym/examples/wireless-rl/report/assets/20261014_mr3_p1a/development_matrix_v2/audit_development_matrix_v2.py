#!/usr/bin/env python3
"""Audit frozen native MR3-P1A v2 records; no simulator or policy is executed."""

import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
FREEZE = "3f24eaa9fae6f7d282f85f991273734d71b9439d"
COMPONENTS = {"base", "lidar", "wheel_left", "wheel_right",
              "caster_back_left", "caster_back_right"}
ROBOTS = {"tb1", "tb2", "tb3"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def main():
    copy = json.loads((BASE / "copy_hash_receipt.json").read_text())
    assert copy["source_freeze"] == FREEZE
    for record in copy["raw_files"] + copy["validation_inputs"]:
        path = BASE / record["canonical_path"]
        assert path.stat().st_size == record["size_bytes"], path
        assert digest(path) == record["sha256"], path
    validator_path = BASE / "frozen_ros_smoke_test_3f24eaa.py"
    spec = importlib.util.spec_from_file_location("frozen_v2_native_validator", validator_path)
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    cells = []
    for family in ("rooms", "corridors", "open"):
        contract_path = BASE / "frozen_contracts" / f"{family}.json"
        contract = json.loads(contract_path.read_text())
        contract["sha256"] = digest(contract_path)
        invocation_path = BASE.parent / f"mr3_p1a_v2_{family}_20261014_123944_invocation.json"
        invocation = json.loads(invocation_path.read_text())
        assert invocation["source_freeze"] == FREEZE
        assert invocation["task_contract_sha256"] == contract["sha256"]
        batch = json.loads((BASE / family / "summary.json").read_text())
        assert batch["seeds"] == [101, 202, 303]
        assert batch["task_contract_sha256"] == contract["sha256"]
        assert len(batch["episodes"]) == 3
        assert {row["gazebo_seed"] for row in batch["episodes"]} == {101, 202, 303}
        for row in batch["episodes"]:
            seed = row["gazebo_seed"]
            result_path = BASE / family / "episodes" / f"{row['episode_id']}.json"
            logs = list((BASE / family / "launch_logs").glob(f"robots3_seed{seed}_*.log"))
            assert len(logs) == 1, (family, seed, logs)
            log = logs[0].read_text(errors="replace")
            failures = validator.native_launch_failures(log)
            reducer = validator.validate_contact_reducer_summary(log)
            checks = {"complete_18_source_reducer_sequence_and_count_audit": True,
                      "no_native_child_failure_or_escalation": not failures,
                      "runner_returncode_zero": row["runner_returncode"] == 0}
            native = json.loads(result_path.read_text()) if result_path.exists() else None
            warnings = []
            if native is None:
                checks["native_json_present"] = False
            else:
                validator.validate_evaluation_result(native, .95, contract)
                checks["native_json_present"] = True
                checks["schema4_contract_validator"] = True
                checks["world_hash_matches_contract"] = (
                    native["world_sha256"] == contract["world_sha256"])
                checks["world_name_matches_contract"] = (
                    Path(native["world_file"]).name == contract["world_file"])
                checks["controller_release_start_barrier"] = (
                    native["task_start_barrier"] == "controller_release")
                start, end, elapsed = (native[name] for name in
                                       ("start_sim_time_sec", "end_sim_time_sec",
                                        "elapsed_sim_time_sec"))
                checks["finite_task_time_within_300_seconds"] = (
                    all(finite(v) for v in (start, end, elapsed))
                    and 0 <= elapsed <= 300
                    and math.isclose(end-start, elapsed, rel_tol=0, abs_tol=1e-6))
                quality = contract["quality"]
                quality_pass = (native["observed_accuracy"] >= quality["min_observed_accuracy"]
                                and native["occupied_iou"] >= quality["min_occupied_iou"]
                                and native["false_free_ratio"] <= quality["max_false_free_ratio"])
                checks["quality_flag_matches_metrics"] = native["map_quality_pass"] == quality_pass
                participation = contract["participation"]
                participant_pass = all(
                    robot["path_length_m"] >= participation["min_path_length_m"]
                    and robot["nav_goal_count"] >= participation["min_goal_count"]
                    for robot in native["robots"].values())
                checks["participation_flag_matches_metrics"] = (
                    native["robot_participation_pass"] == participant_pass)
                checks["zero_non_support_contact"] = (
                    native["collision_events"] == 0
                    and native["collision_duration_sec"] == 0
                    and all(robot["collision_events"] == 0
                            and robot["collision_duration_sec"] == 0
                            for robot in native["robots"].values()))
                monitor = native["contact_monitor_summary"]
                checks["18_components_fresh_without_task_health_latch"] = (
                    set(monitor["components"]) == ROBOTS
                    and monitor["fresh"] is True and monitor["ever_unhealthy"] is False
                    and monitor["latched_issues"] == {} and monitor["event_count"] == 0)
                ages, gaps = [], []
                for robot, parts in monitor["components"].items():
                    assert set(parts) == COMPONENTS, robot
                    for component, item in parts.items():
                        assert item["accepted_message_count"] >= 1
                        assert item["invalid_timestamp_count"] == 0
                        assert not item["health_reason"]
                        for key in ("source_age_sec", "receipt_age_sec"):
                            assert finite(item[key]) and 0 <= item[key] <= .5
                            ages.append(item[key])
                        for key in ("max_source_gap_sec", "max_receipt_gap_sec"):
                            assert finite(item[key]) and item[key] >= 0
                            gaps.append(item[key])
                            if item[key] > .5:
                                warnings.append(f"{robot}/{component}/{key} includes startup history")
                checks["18_components_valid_timestamps_at_finalization"] = True
                checks["false_free_denominator_matches_declared_occupied_cells"] = (
                    native["false_free_denominator"] == "truth_occupied_cell_count")
                if native["success"]:
                    acknowledgment = native["navigation_stop_acknowledgment"]
                    request = native["navigation_stop_requested_sim_time_sec"]
                    checks["success_closure_timing_and_ownership"] = (
                        start <= request <= acknowledgment["stop_sim_time_sec"] <= end
                        and acknowledgment["pending_goal_count"] == 0
                        and acknowledgment["navigation_failure"] is False
                        and math.isclose(acknowledgment["start_sim_time_sec"], start,
                                         rel_tol=0, abs_tol=1e-9)
                        and acknowledgment["robot_names"] == ["tb1", "tb2", "tb3"])
            native_success = native is not None and native["success"] is True
            strict = native_success and all(checks.values())
            if strict:
                classification = "strict_complete_pass"
            elif native_success:
                classification = "native_task_achieved_but_cleanup_infrastructure_invalid"
            elif native is None:
                classification = "startup_infrastructure_failure_missing_native_json"
            elif failures or row["runner_returncode"] != 0:
                classification = "task_failure_with_cleanup_infrastructure_failure"
            else:
                classification = "task_failure_clean_exit"
            cells.append({
                "family": family, "seed": seed, "classification": classification,
                "strict_complete_pass": strict, "native_json_success": native_success,
                "native_json": str(result_path.relative_to(BASE)) if native is not None else None,
                "launch_log": str(logs[0].relative_to(BASE)),
                "runner_returncode": row["runner_returncode"], "checks": checks,
                "native_child_failures": failures, "warnings": warnings,
                "native_termination_reason": native["termination_reason"] if native else None,
                "control_failure": native.get("control_failure") if native else None,
                "elapsed_sim_time_sec": native["elapsed_sim_time_sec"] if native else None,
                "time_to_95_coverage_sec": native.get("time_to_95_coverage_sec") if native else None,
                "correct_free_coverage_ratio": native["correct_free_coverage_ratio"] if native else None,
                "observed_accuracy": native["observed_accuracy"] if native else None,
                "occupied_iou": native["occupied_iou"] if native else None,
                "false_free_ratio": native["false_free_ratio"] if native else None,
                "robot_path_lengths_m": {name: values["path_length_m"]
                                         for name, values in native["robots"].items()} if native else None,
                "robot_goal_counts": {name: values["nav_goal_count"]
                                      for name, values in native["robots"].items()} if native else None,
                "maximum_final_source_or_receipt_age_sec": max(ages) if native else None,
                "maximum_recorded_source_or_receipt_gap_sec": max(gaps) if native else None,
                "contact_reducer_raw_received_messages": sum(
                    item["received"] for item in reducer["topics"].values()),
                "contact_reducer_summary": reducer,
                "task_contract_sha256": contract["sha256"],
                "invocation_sha256": digest(invocation_path),
            })
    expected_passes = {("rooms", 101), ("rooms", 303), ("corridors", 101), ("open", 303)}
    assert {(cell["family"], cell["seed"]) for cell in cells
            if cell["strict_complete_pass"]} == expected_passes
    assert len(cells) == 9
    result = {
        "type": "independent_frozen_native_artifact_audit_not_new_experiment",
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_freeze": FREEZE, "auditor_sha256": digest(Path(__file__)),
        "frozen_validator_sha256": digest(validator_path),
        "copy_hash_receipt_sha256": digest(BASE / "copy_hash_receipt.json"),
        "native_original_hashes_verified": len(copy["raw_files"]),
        "attempt_count": 9, "native_json_count": sum(cell["native_json"] is not None for cell in cells),
        "native_json_success_count": sum(cell["native_json_success"] for cell in cells),
        "strict_complete_pass_count": sum(cell["strict_complete_pass"] for cell in cells),
        "simulator_runs": 0, "policy_runs": 0, "originals_modified": False,
        "conclusion": "v2 has four strict complete passes; native task success never overrides cleanup failure",
        "cells": cells,
    }
    with (BASE / "independent_audit.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({key: value for key, value in result.items() if key != "cells"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
