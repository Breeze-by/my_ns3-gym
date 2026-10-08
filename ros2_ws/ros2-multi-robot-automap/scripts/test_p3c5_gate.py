"""Read-only gate counterexamples using the unchanged native delayed task result."""
import json
from pathlib import Path

import pytest

from check_p3c5_gate import declaration_audit, native_interval, native_safety_ok
from run_p3c5_audit import main as expand_original
from run_p3b5_tasks import episode_command


def failed_mission():
    path = Path(__file__).parents[1]/"src/multi_robot_exploration/test/fixtures/p3c5_native_early_failure.json"
    return json.loads(path.read_text())


@pytest.fixture
def declared_original(tmp_path):
    config = json.loads((Path(__file__).with_name("p3c5_traffic_manifest.json")).read_text())
    directory = tmp_path/"original_delay_lab2"
    directory.mkdir()
    result = failed_mission()
    result["episode_id"] = directory.name
    scenario = config["cases"]["delay_lab2"]
    command = episode_command({"id": "delay_lab2", "scenario": "delay_lab2", "mode": "rally", "profile": "online"},
                              scenario, scenario["profile"], scenario["mode"], directory, config)
    command[command.index("--shutdown-timeout")+1] = str(config["owner_shutdown_timeout_sec"])
    command.append("--gateway-admission-protocol")
    row = {"case": "delay_lab2", "config": config, "command": command,
           "result": result, "result_path": str(directory/(directory.name+".json"))}
    Path(row["result_path"]).write_text(json.dumps(result))
    (directory/"manifest.json").write_text(json.dumps({k: row[k] for k in ("case", "config", "command")}))
    return row, config, directory


def test_declaration_binding_keeps_the_real_early_failure(declared_original):
    row, config, directory = declared_original
    assert declaration_audit(row, config, directory)["status"] == "PASS"
    assert not row["result"]["success"] and row["result"]["completion_time_sec"] is None


@pytest.mark.parametrize("mutation", ["cache", "manifest", "seed", "world", "energy", "target",
                                     "horizon", "delay", "protocol_flag", "extra_argument"])
def test_declaration_binding_rejects_wrong_native_or_executed_cell(declared_original, mutation):
    row, config, directory = declared_original
    if mutation == "cache":
        row["result"]["gazebo_seed"] += 1
    elif mutation == "manifest":
        manifest = json.loads((directory/"manifest.json").read_text())
        manifest["case"] = "lab2"
        (directory/"manifest.json").write_text(json.dumps(manifest))
    elif mutation in ("seed", "world", "energy", "target"):
        if mutation == "seed":
            row["result"]["gazebo_seed"] += 1
        elif mutation == "world":
            row["result"]["world_file"] = "p1c_rooms.world"
        elif mutation == "energy":
            row["result"]["robots"]["tb1"]["battery_initial_energy"] += 1
        else:
            row["result"]["target_x"] = 10
        Path(row["result_path"]).write_text(json.dumps(row["result"]))
    else:
        command = row["command"]
        if mutation in ("horizon", "delay"):
            command[command.index("--evaluation-duration" if mutation == "horizon" else "--uplink-delay-sec")+1] = "100"
        elif mutation == "protocol_flag":
            command.remove("--gateway-admission-protocol")
        else:
            command += ["--rally-max-concurrent", "1"]
        (directory/"manifest.json").write_text(json.dumps({k: row[k] for k in ("case", "config", "command")}))
    with pytest.raises(AssertionError):
        declaration_audit(row, config, directory)


def test_real_early_mission_failure_is_retained_without_fabricated_tail():
    result = failed_mission()
    assert not result["success"] and result["termination_reason"] == "mission_failed"
    native_safety_ok(result)
    start, end = native_interval(result, 300)
    assert end == result["end_sim_time_sec"]
    assert end-start == pytest.approx(274.9)
    assert end < start+300


@pytest.mark.parametrize('mutation',[None,'success','partial_completion','proof','numeric_hold','rally_phase'])
def test_unassigned_native_timeout_retains_null_hold_without_inventing_success(mutation):
    result=failed_mission()
    result.update(task_phase='EXPLORE',termination_reason='timeout',rally_assignments={},native_rally_hold_proof=None)
    for k in ('rally_hold_sec','rally_position_tolerance_m','rally_linear_tolerance_mps','rally_angular_tolerance_radps'):
        result[k]=None
    if mutation in ('success','partial_completion'):result[mutation]=True
    if mutation=='proof':result['native_rally_hold_proof']={'observed_duration_sec':5.}
    if mutation=='numeric_hold':result['rally_hold_sec']=5.
    if mutation=='rally_phase':result['task_phase']='RALLY'
    if mutation is None:native_safety_ok(result)
    else:
        with pytest.raises(AssertionError):native_safety_ok(result)


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
