#!/usr/bin/env python3
"""Audit frozen native MR3-P1A v4 records; no simulator or policy is executed."""

import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
FREEZE = "a43de1e3f4dd5e15a6df311044ec750500780cf5"
COMPONENTS = {"base", "lidar", "wheel_left", "wheel_right",
              "caster_back_left", "caster_back_right"}
ROBOTS = {"tb1", "tb2", "tb3"}
MANIFEST_SHA256 = "f3c2b079a692ede7a41a7ebca88bc351d27e1d4ff6d399d82ac31fe9ac7c4767"


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
    validator_path = BASE / "frozen_ros_smoke_test.py"
    spec = importlib.util.spec_from_file_location("frozen_v4_native_validator", validator_path)
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    manifest_path = BASE / "validation_inputs" / "runtime_component_manifest_matrix4.json"
    assert digest(manifest_path) == MANIFEST_SHA256
    manifest = json.loads(manifest_path.read_text())
    assert manifest["source_freeze"] == FREEZE
    assert len(manifest["files"]) == 459
    assert len(manifest["installed_source_identity_checks"]) == 15
    assert all(item["identical"] for item in manifest["installed_source_identity_checks"])
    stop_path = BASE / "validation_inputs" / "matrix4_owned_stop.json"
    stop_outcome_path = BASE / "validation_inputs" / "matrix4_owned_stop_outcome.json"
    stop = json.loads(stop_path.read_text())
    stop_outcome = json.loads(stop_outcome_path.read_text())
    assert stop["source_freeze"] == FREEZE and stop["targets"] == []
    assert stop_outcome["owned_stop_targets"] == [] and stop_outcome["signals_sent"] == 0
    assert stop_outcome["rooms303_native_success"] is True
    assert math.isclose(stop_outcome["rooms303_elapsed_sim_time_sec"], 135.9, abs_tol=1e-9)
    cells = []
    environments = []
    for family in ("rooms",):
        contract_path = BASE / "frozen_contracts" / f"{family}.json"
        contract = json.loads(contract_path.read_text())
        contract["sha256"] = digest(contract_path)
        invocation_path = BASE / "validation_inputs" / f"mr3_p1a_v4_{family}_20261014_140924_invocation.json"
        invocation = json.loads(invocation_path.read_text())
        assert invocation["source_freeze"] == FREEZE
        assert invocation["runtime_component_manifest_sha256"] == MANIFEST_SHA256
        assert invocation["seeds"] == [101, 202, 303]
        environment_path = BASE / "validation_inputs" / f"matrix4_{family}_native_environment.json"
        environment = json.loads(environment_path.read_text())
        assert environment["result"] == "PASS"
        assert len(environment["processes"]) == 1
        process = environment["processes"][0]
        env = process["environment"]
        assert env["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp"
        assert env["ROS_LOCALHOST_ONLY"] == "1"
        assert env["PYTHONNOUSERSITE"] == "1"
        assert env["TURTLEBOT3_MODEL"] == "waffle"
        assert env["ROS_DOMAIN_ID"] == str(invocation["ros_domain_id"])
        assert env["GAZEBO_MASTER_URI"] == f"http://127.0.0.1:{invocation['gazebo_port']}"
        for key in ("FASTRTPS_DEFAULT_PROFILES_FILE", "FASTDDS_DEFAULT_PROFILES_FILE",
                    "RMW_FASTRTPS_USE_QOS_FROM_XML", "SKIP_DEFAULT_XML",
                    "RMW_FASTRTPS_PUBLICATION_MODE", "CYCLONEDDS_URI"):
            assert env[key] is None, key
        assert process["explicit_profile_sha256"] == {}
        assert all(value is None for value in process["default_profile_files"].values())
        environments.append({"family": family, "sha256": digest(environment_path),
                             "file": environment_path.name})
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
            validation_errors = []
            try:
                reducer = validator.validate_contact_reducer_summary(log)
                reducer_valid = True
            except (RuntimeError, ValueError, TypeError, KeyError) as error:
                reducer = {}
                reducer_valid = False
                validation_errors.append("contact_reducer: " + str(error))
            checks = {"complete_18_source_reducer_sequence_and_count_audit": reducer_valid,
                      "no_native_child_failure_or_escalation": not failures,
                      "runner_returncode_zero": row["runner_returncode"] == 0}
            native = json.loads(result_path.read_text()) if result_path.exists() else None
            warnings = []
            if native is None:
                checks["native_json_present"] = False
            else:
                checks["native_json_present"] = True
                try:
                    validator.validate_evaluation_result(native, .95, contract)
                    checks["schema4_contract_validator"] = True
                except (RuntimeError, ValueError, TypeError, KeyError) as error:
                    checks["schema4_contract_validator"] = False
                    validation_errors.append(str(error))
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
                contact_start = native["contact_subscription_started_sim_time_sec"]
                checks["contact_clock_bootstrap_started_before_task_without_overflow"] = (
                    finite(contact_start) and finite(start) and 0 < contact_start <= start
                    and native["contact_subscription_bootstrap_state"] == "contact_subscriptions_started"
                    and native["contact_clock_overflow_diagnostic"] is None)
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
                    and monitor["latched_issues"] == {})
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
            elif not finite(native.get("start_sim_time_sec")):
                classification = "startup_infrastructure_failure_before_task_barrier"
            elif validation_errors:
                classification = "native_result_invalid_measurement"
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
                "native_json_validation_errors": validation_errors,
                "native_termination_reason": native["termination_reason"] if native else None,
                "control_failure": native.get("control_failure") if native else None,
                "contact_subscription_started_sim_time_sec": native.get("contact_subscription_started_sim_time_sec") if native else None,
                "contact_subscription_bootstrap_state": native.get("contact_subscription_bootstrap_state") if native else None,
                "contact_clock_overflow_diagnostic": native.get("contact_clock_overflow_diagnostic") if native else None,
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
                    item["received"] for item in reducer.get("topics", {}).values()),
                "contact_reducer_summary": reducer,
                "task_contract_sha256": contract["sha256"],
                "invocation_sha256": digest(invocation_path),
            })
    assert len(cells) == 3
    integrity_checks = (
        "native_json_present", "schema4_contract_validator", "world_hash_matches_contract",
        "world_name_matches_contract", "controller_release_start_barrier",
        "finite_task_time_within_300_seconds", "quality_flag_matches_metrics",
        "participation_flag_matches_metrics", "false_free_denominator_matches_declared_occupied_cells",
        "complete_18_source_reducer_sequence_and_count_audit",
        "no_native_child_failure_or_escalation", "runner_returncode_zero",
        "18_components_fresh_without_task_health_latch",
        "18_components_valid_timestamps_at_finalization",
        "contact_clock_bootstrap_started_before_task_without_overflow",
    )
    for cell in cells:
        cell["valid_task_measurement"] = all(cell["checks"].get(key) is True
                                             for key in integrity_checks)
    scene_passes = {family: sum(cell["strict_complete_pass"] for cell in cells
                               if cell["family"] == family)
                    for family in ("rooms", "corridors", "open")}
    stage_ready = (len(cells) == 9 and all(cell["valid_task_measurement"] for cell in cells)
                   and all(count >= 1 for count in scene_passes.values()))
    result = {
        "type": "independent_frozen_native_artifact_audit_not_new_experiment",
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_freeze": FREEZE, "auditor_sha256": digest(Path(__file__)),
        "frozen_validator_sha256": digest(validator_path),
        "copy_hash_receipt_sha256": digest(BASE / "copy_hash_receipt.json"),
        "runtime_component_manifest_sha256": digest(manifest_path),
        "runtime_component_manifest_file_count": len(manifest["files"]),
        "runtime_installed_identity_check_count": len(manifest["installed_source_identity_checks"]),
        "native_environment_bindings": environments,
        "native_original_hashes_verified": len(copy["raw_files"]),
        "attempt_count": len(cells), "planned_matrix_size": 9,
        "unstarted_cells": copy["unstarted_cells"], "unstarted_count": len(copy["unstarted_cells"]),
        "owned_stop_intent_sha256": digest(stop_path),
        "owned_stop_outcome_sha256": digest(stop_outcome_path),
        "owned_stop_targets": stop["targets"], "owned_signals_sent": stop_outcome["signals_sent"],
        "rooms303_completed_naturally_not_interrupted": True,
        "scope": "v4 room batch diagnostics only; six cells unstarted; no cross-freeze task-success credit",
        "native_json_count": sum(cell["native_json"] is not None for cell in cells),
        "native_json_success_count": sum(cell["native_json_success"] for cell in cells),
        "strict_complete_pass_count": sum(cell["strict_complete_pass"] for cell in cells),
        "valid_task_measurement_count": sum(cell["valid_task_measurement"] for cell in cells),
        "infrastructure_invalid_measurement_count": sum(not cell["valid_task_measurement"] for cell in cells),
        "clean_real_task_failure_count": sum(cell["valid_task_measurement"] and not cell["native_json_success"] for cell in cells),
        "strict_scene_success_count": scene_passes,
        "stage_evidence_complete_not_user_acceptance": stage_ready,
        "does_not_require_nine_baseline_successes": True,
        "simulator_runs": 0, "policy_runs": 0, "originals_modified": False,
        "conclusion": ("P1A native evidence complete: nine valid measurements and each scene has a strict success"
                       if stage_ready else "v4 incomplete: three room attempts, one strict complete success, two infrastructure-invalid; six cells unstarted. Gazebo ABRT success remains invalid; no native task was interrupted by owned-stop intent."),
        "cells": cells,
    }
    with (BASE / "independent_audit.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({key: value for key, value in result.items() if key != "cells"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
