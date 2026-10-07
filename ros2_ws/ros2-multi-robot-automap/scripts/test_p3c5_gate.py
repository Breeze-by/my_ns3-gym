"""Read-only gate counterexamples using the unchanged native delayed task result."""
import json
from pathlib import Path

import pytest

from check_p3c5_gate import native_interval, native_safety_ok
from run_p3c5_audit import main as expand_original


def failed_mission():
    path = Path(__file__).parents[1]/"src/multi_robot_exploration/test/fixtures/p3c5_native_early_failure.json"
    return json.loads(path.read_text())


def test_real_early_mission_failure_is_retained_without_fabricated_tail():
    result = failed_mission()
    assert not result["success"] and result["termination_reason"] == "mission_failed"
    native_safety_ok(result)
    start, end = native_interval(result, 300)
    assert end == result["end_sim_time_sec"]
    assert end-start == pytest.approx(274.9)
    assert end < start+300


def test_timeout_polling_overrun_is_not_extra_measured_time():
    result = failed_mission()
    result["end_sim_time_sec"] = result["start_sim_time_sec"]+300.3
    result["elapsed_sim_time_sec"] = 300.3
    start, end = native_interval(result, 300)
    assert end-start == pytest.approx(300)


def test_cleanup_wait_expands_beyond_metrics_grace_without_extending_native_horizon(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["run_p3c5_audit.py", "--case", "delay_rooms3", "--run-id", "check_only",
                                    "--domain", "190", "--gazebo-port", "19930", "--validate-only"])
    assert expand_original() == 0
    expanded = json.loads(capsys.readouterr().out)
    command, config = expanded["command"], expanded["config"]
    assert float(command[command.index("--shutdown-timeout")+1]) == config["owner_shutdown_timeout_sec"]
    assert config["metrics_sigint_grace_sec"] < config["owner_shutdown_timeout_sec"]
    assert float(command[command.index("--evaluation-duration")+1]) == 300


@pytest.mark.parametrize("tamper", ["real_failed_robots_field", "positive_energy_failed_mode",
                                   "hidden_per_robot_exhaustion", "hidden_per_robot_contact", "missing_measurement"])
def test_native_safety_counterexamples_cannot_hide_in_positive_global_summary(tamper):
    result = failed_mission()
    robot = result["robots"]["tb2"]
    if tamper == "real_failed_robots_field":
        result["failed_robots"] = ["tb2"]
    elif tamper == "positive_energy_failed_mode":
        robot["battery_mode"] = "FAILED"
    elif tamper == "hidden_per_robot_exhaustion":
        robot["battery_minimum_energy"] = 0
    elif tamper == "hidden_per_robot_contact":
        robot["collision_events"] = 1
    elif tamper == "missing_measurement":
        del robot["battery_minimum_energy"]
    with pytest.raises((AssertionError, KeyError)):
        native_safety_ok(result)
