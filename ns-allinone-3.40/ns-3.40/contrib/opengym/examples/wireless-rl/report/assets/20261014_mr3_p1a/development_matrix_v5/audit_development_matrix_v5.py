#!/usr/bin/env python3
"""Audit frozen native MR3-P1A v5 records; no simulator or policy is executed."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
import sys


FREEZE = "f7ad7fd645f0d6af832b895a37a68b14411354fc"
COMPONENTS = {"base", "lidar", "wheel_left", "wheel_right",
              "caster_back_left", "caster_back_right"}
ROBOTS = {"tb1", "tb2", "tb3"}
MANIFEST_SHA256 = "e0e609412b111dc7851e417ffb6dd7f05474f5096cbec6f31ac5c7847681b629"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    BASE = args.base.resolve()
    copy = json.loads((BASE / "copy_hash_receipt.json").read_text())
    assert copy["source_freeze"] == FREEZE
    for record in copy["raw_files"] + copy["validation_inputs"]:
        path = BASE / record["canonical_path"]
        assert path.stat().st_size == record["size_bytes"], path
        assert digest(path) == record["sha256"], path
    validator_path = BASE / "frozen_ros_smoke_test.py"
    spec = importlib.util.spec_from_file_location("frozen_v5_native_validator", validator_path)
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    manifest_path = BASE / "validation_inputs" / "runtime_component_manifest_matrix5.json"
    assert digest(manifest_path) == MANIFEST_SHA256
    manifest = json.loads(manifest_path.read_text())
    assert manifest["source_freeze"] == FREEZE
    assert len(manifest["files"]) == 462
    assert len(manifest["installed_source_identity_checks"]) == 16
    assert all(item["identical"] for item in manifest["installed_source_identity_checks"])
    profile_path = BASE / "frozen_mr3_fastdds_loopback_udp.xml"
    profile_sha256 = digest(profile_path)
    assert profile_sha256 == "443340f4c7e083c11258aa28917212feaca01d34aa30a0ce689ea02819a379ef"
    profile_records = [record for record in manifest["files"]
                       if record["scope"] == "tracked_source"
                       and Path(record["path"]).name == "mr3_fastdds_loopback_udp.xml"]
    assert len(profile_records) == 1 and profile_records[0]["sha256"] == profile_sha256
    profile_runtime_path = profile_records[0]["path"]
    cells = []
    environments = []
    families = copy["completed_families"]
    assert families == ["rooms", "corridors", "open"][:len(families)]
    for family in families:
        contract_path = BASE / "frozen_contracts" / f"{family}.json"
        contract = json.loads(contract_path.read_text())
        contract["sha256"] = digest(contract_path)
        invocation_path = BASE / "validation_inputs" / f"mr3_p1a_v5_{family}_20261014_150452_invocation.json"
        invocation = json.loads(invocation_path.read_text())
        assert invocation["source_freeze"] == FREEZE
        assert invocation["runtime_component_manifest_sha256"] == MANIFEST_SHA256
        assert invocation["seeds"] == [101, 202, 303]
        environment_path = BASE / "validation_inputs" / f"matrix5_{family}_native_environment.json"
        environment = json.loads(environment_path.read_text())
        assert environment["result"] == "PASS"
        assert environment["source_freeze"] == FREEZE
        assert environment["observed_checkout_head"] == FREEZE
        assert environment["run_id"] == invocation["run_id"]
        assert len(environment["processes"]) == 2
        roles = {record["role"]: record for record in environment["processes"]}
        assert set(roles) == {"owned_ros_launch", "owned_gzserver_descendant"}
        launch_process = roles["owned_ros_launch"]
        server_process = roles["owned_gzserver_descendant"]
        assert server_process["ppid"] == launch_process["pid"]
        assert server_process["pgid"] == launch_process["pgid"] == launch_process["pid"]
        assert any(token.startswith("evaluation_episode_id:=" + invocation["run_id"] + "_seed")
                   for token in launch_process["argv"])
        env = launch_process["environment"]
        assert server_process["environment"] == env
        for process in environment["processes"]:
            assert env["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp"
            assert env["ROS_LOCALHOST_ONLY"] == "0" and env["SKIP_DEFAULT_XML"] == "1"
            assert env["FASTRTPS_DEFAULT_PROFILES_FILE"] == profile_runtime_path
            assert env["PYTHONNOUSERSITE"] == "1" and env["TURTLEBOT3_MODEL"] == "waffle"
            assert env["ROS_DOMAIN_ID"] == str(invocation["ros_domain_id"])
            assert env["GAZEBO_MASTER_URI"] == f"http://127.0.0.1:{invocation['gazebo_port']}"
            for key in ("FASTDDS_DEFAULT_PROFILES_FILE", "RMW_FASTRTPS_USE_QOS_FROM_XML",
                        "RMW_FASTRTPS_PUBLICATION_MODE", "CYCLONEDDS_URI",
                        "FASTDDS_ENVIRONMENT_FILE", "ROS_DISCOVERY_SERVER", "ROS_SUPER_CLIENT"):
                assert env[key] is None, key
            profiles = process["explicit_profile_files"]
            assert set(profiles) == {"FASTRTPS_DEFAULT_PROFILES_FILE"}
            profile = profiles["FASTRTPS_DEFAULT_PROFILES_FILE"]
            assert profile["path"] == profile_runtime_path and profile["exists"] is True
            assert profile["sha256"] == profile_sha256
        assert invocation["fastdds_profile_sha256"] == profile_sha256
        assert all(invocation["environment"][key] == env[key] for key in invocation["environment"])
        environments.append({"family": family, "sha256": digest(environment_path),
                             "file": environment_path.name,
                             "roles": {key: value["pid"] for key, value in roles.items()},
                             "runtime_profile_load_observed": [record["runtime_profile_load_observed"]
                                                               for record in environment["processes"]]})
        assert invocation["task_contract_sha256"] == contract["sha256"]
        batch = json.loads((BASE / family / "summary.json").read_text())
        assert batch["seeds"] == [101, 202, 303]
        assert batch["run_id"] == f"mr3_p1a_v5_{family}_20261014_150452"
        transport = batch["transport_environment"]
        assert transport["profile_sha256"] == profile_sha256
        for key in ("RMW_IMPLEMENTATION", "ROS_LOCALHOST_ONLY", "FASTRTPS_DEFAULT_PROFILES_FILE",
                    "SKIP_DEFAULT_XML", "FASTDDS_DEFAULT_PROFILES_FILE",
                    "RMW_FASTRTPS_USE_QOS_FROM_XML", "RMW_FASTRTPS_PUBLICATION_MODE"):
            assert transport[key] == env[key], key
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
            started = re.findall(r"\[([^\]\n]+)\]: process started with pid \[(\d+)\]", log)
            clean = re.findall(r"\[([^\]\n]+)\]: process has finished cleanly \[pid (\d+)\]", log)
            owners = re.findall(r"Owned Gazebo server (\S+) started with pid=(\d+)", log)
            stop_cli = [identity for identity in started if identity[0].startswith("mr3_gazebo_native_stop-")]
            all_native_clean = bool(started) and set(started) == set(clean)
            owned_ack = (len(owners) == 1 and owners[0] in started and owners[0] in clean
                         and len(stop_cli) == 1 and stop_cli[0] in clean)
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
                      "runner_returncode_zero": row["runner_returncode"] == 0,
                      "all_started_native_children_exited_cleanly": all_native_clean,
                      "owned_gazebo_and_stop_cli_positive_clean_exit": owned_ack}
            native = json.loads(result_path.read_text()) if result_path.exists() else None
            warnings = []
            task_gate_diagnostics = []
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
                timestamps_valid = True
                for robot, parts in monitor["components"].items():
                    if set(parts) != COMPONENTS:
                        timestamps_valid = False
                        task_gate_diagnostics.append(robot + ": incomplete component keys")
                    for component, item in parts.items():
                        if (type(item.get("accepted_message_count")) is not int
                            or item["accepted_message_count"] < 1
                            or type(item.get("invalid_timestamp_count")) is not int
                            or item["invalid_timestamp_count"] < 0
                            or item.get("health_reason")):
                            timestamps_valid = False
                            task_gate_diagnostics.append(f"{robot}/{component}: invalid source health")
                        if (type(item.get("invalid_timestamp_count")) is int
                            and item["invalid_timestamp_count"] > 0):
                            warnings.append(f"{robot}/{component}: invalid timestamp counter includes startup; task-phase invalid time is separately latched")
                        for key in ("source_age_sec", "receipt_age_sec"):
                            value = item.get(key)
                            if not finite(value) or not 0 <= value <= .5:
                                timestamps_valid = False
                                task_gate_diagnostics.append(f"{robot}/{component}/{key}={value}")
                            if finite(value):
                                ages.append(value)
                        for key in ("max_source_gap_sec", "max_receipt_gap_sec"):
                            value = item.get(key)
                            if not finite(value) or value < 0:
                                timestamps_valid = False
                                task_gate_diagnostics.append(f"{robot}/{component}/{key}={value}")
                            else:
                                gaps.append(value)
                                if value > .5:
                                    warnings.append(f"{robot}/{component}/{key}: history includes startup; gap phase not separately recorded")
                checks["18_components_valid_timestamps_at_finalization"] = timestamps_valid
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
                "started_native_processes": started, "clean_native_processes": clean,
                "owned_gazebo_identity": owners, "stop_cli_identity": stop_cli,
                "native_json_validation_errors": validation_errors,
                "task_gate_diagnostics": task_gate_diagnostics,
                "runner_result_classification": (
                    "infrastructure_failure" if row["runner_returncode"] != 0
                    or row["termination_reason"] in ("runner_failure", "invalid_evaluation")
                    else "success" if row["success"] is True else "task_failure"),
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
                "maximum_final_source_or_receipt_age_sec": max(ages) if native and ages else None,
                "maximum_recorded_source_or_receipt_gap_sec": max(gaps) if native and gaps else None,
                "contact_reducer_raw_received_messages": sum(
                    item["received"] for item in reducer.get("topics", {}).values()),
                "contact_reducer_summary": reducer,
                "task_contract_sha256": contract["sha256"],
                "invocation_sha256": digest(invocation_path),
            })
    assert len(cells) == 3 * len(families)
    integrity_checks = (
        "native_json_present", "schema4_contract_validator", "world_hash_matches_contract",
        "world_name_matches_contract", "controller_release_start_barrier",
        "finite_task_time_within_300_seconds", "quality_flag_matches_metrics",
        "participation_flag_matches_metrics", "false_free_denominator_matches_declared_occupied_cells",
        "complete_18_source_reducer_sequence_and_count_audit",
        "no_native_child_failure_or_escalation", "runner_returncode_zero",
        "all_started_native_children_exited_cleanly",
        "owned_gazebo_and_stop_cli_positive_clean_exit",
        "contact_clock_bootstrap_started_before_task_without_overflow",
    )
    for cell in cells:
        cell["valid_task_measurement"] = all(cell["checks"].get(key) is True
                                             for key in integrity_checks)
        if (not cell["valid_task_measurement"] and not cell["native_json_success"]
            and cell["native_json"] is not None
            and finite(cell["elapsed_sim_time_sec"])
            and cell["checks"].get("finite_task_time_within_300_seconds")):
            cell["classification"] = "post_release_infrastructure_invalid_measurement"
        cell["monitoring_gate_passed"] = (
            cell["checks"].get("18_components_fresh_without_task_health_latch") is True
            and cell["checks"].get("18_components_valid_timestamps_at_finalization") is True)
        cell["has_full_zero_contact_evidence"] = (
            cell["monitoring_gate_passed"] and cell["checks"].get("zero_non_support_contact") is True)
        if (cell["valid_task_measurement"] and not cell["native_json_success"]
            and cell["native_termination_reason"] == "collision_monitoring_interrupted"):
            cell["classification"] = "conservative_monitor_abort_task_failure"
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
        "fastdds_profile_sha256": profile_sha256,
        "transport_policy": {"ROS_LOCALHOST_ONLY": "0", "SKIP_DEFAULT_XML": "1",
                             "transport": "UDPv4 interface whitelist 127.0.0.1; builtin disabled"},
        "native_original_hashes_verified": len(copy["raw_files"]),
        "attempt_count": len(cells), "planned_matrix_size": 9,
        "unstarted_cells": copy["unstarted_cells"], "unstarted_count": len(copy["unstarted_cells"]),
        "completed_families": families,
        "environment_binding_scope": "Selected owned launch/server process environment and profile file hashes; no live DDS transport/QoS introspection inferred",
        "native_json_count": sum(cell["native_json"] is not None for cell in cells),
        "native_json_success_count": sum(cell["native_json_success"] for cell in cells),
        "strict_complete_pass_count": sum(cell["strict_complete_pass"] for cell in cells),
        "valid_task_measurement_count": sum(cell["valid_task_measurement"] for cell in cells),
        "validity_basis": "Frozen success_contract/validator/runner: failed task gates remain failed outcomes when the common-start/hash/schema/reducer/native-exit evidence is valid; health is not retroactively required of every failure result",
        "monitor_abort_task_failure_count": sum(cell["classification"] == "conservative_monitor_abort_task_failure" for cell in cells),
        "monitoring_gate_failure_count": sum(cell["native_json"] is not None and not cell["monitoring_gate_passed"] for cell in cells),
        "runner_success_count": sum(cell["runner_result_classification"] == "success" for cell in cells),
        "runner_task_failure_count": sum(cell["runner_result_classification"] == "task_failure" for cell in cells),
        "runner_infrastructure_failure_count": sum(cell["runner_result_classification"] == "infrastructure_failure" for cell in cells),
        "infrastructure_invalid_measurement_count": sum(not cell["valid_task_measurement"] for cell in cells),
        "clean_real_task_failure_count": sum(cell["valid_task_measurement"] and not cell["native_json_success"] for cell in cells),
        "strict_scene_success_count": scene_passes,
        "stage_evidence_complete_not_user_acceptance": stage_ready,
        "does_not_require_nine_baseline_successes": True,
        "simulator_runs": 0, "policy_runs": 0, "originals_modified": False,
        "conclusion": ("P1A native evidence complete: nine valid measurements and each scene has a strict success"
                       if stage_ready else "P1A native evidence incomplete; failures and infrastructure defects retained"),
        "cells": cells,
    }
    with (args.output or BASE / "independent_audit.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({key: value for key, value in result.items() if key != "cells"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
