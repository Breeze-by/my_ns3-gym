"""Validate launch contracts and smoke checks without starting ROS processes."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument
from launch.utilities import perform_substitutions
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
MAPPING_LAUNCH = ROOT / "src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def native_result(success=True, schema=3):
    return {
        "schema_version": schema, "success": success,
        "termination_reason": "coverage_reached" if success else "timeout",
        "failure_reason": "" if success else "timeout",
        "correct_free_coverage_ratio": .96 if schema == 4 else .91,
        "coverage_threshold": .95 if schema == 4 else .9,
        "elapsed_sim_time_sec": 1. if success else 180.,
        "max_duration_sec": 300. if schema == 4 else 180.,
        "start_sim_time_sec": 2., "end_sim_time_sec": 3. if success else 182.,
        "map_message_count": 1, "model_state_message_count": 1,
        "truth_rectangle_count": 4, "merged_map_origin_x": 0.,
        "robots": {f"tb{i}": {"path_length_m": 2., "nav_goal_count": 1}
                   for i in range(1, 4)},
        "search_overlap_ratio": 0., "total_path_length_m": 6.,
        "collision_events": 0, "collision_monitoring_active": True,
        "time_to_75_coverage_sec": .5, "robot_count": 3,
        "observed_accuracy": .98, "false_free_ratio": .001, "occupied_iou": .3,
        "map_quality_pass": True, "robot_participation_pass": True,
        "collision_monitoring_fresh": True,
        "contact_monitor_summary": {"ever_unhealthy": False},
        "task_start_barrier": "controller_release", "task_contract_sha256": "contract-hash",
        "navigation_protocol_closed": True,
    }


def task_contract():
    return {
        "robots": ["tb1", "tb2", "tb3"], "world_file": "p1c_rooms.world",
        "max_duration_sec": 300., "coverage_threshold": .95,
        "participation": {"min_path_length_m": 1., "min_goal_count": 1},
        "quality": {"min_observed_accuracy": .95, "max_false_free_ratio": .02,
                    "min_occupied_iou": .20}, "sha256": "contract-hash",
    }


@pytest.mark.parametrize("output", ["inactive [2]", "unconfigured [1]", "not active", ""])
def test_smoke_rejects_nonactive_lifecycle_state(output):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    assert not smoke.lifecycle_is_active(output)
    assert smoke.lifecycle_is_active("active [3]\n")


@pytest.mark.parametrize("count", ["0", "5", "abc"])
def test_launch_rejects_bad_robot_count_before_creating_nodes(count):
    launch = load_module("mapping", MAPPING_LAUNCH)
    context = LaunchContext()
    context.launch_configurations["robot_count"] = count
    with pytest.raises(ValueError, match="robot_count"):
        launch.launch_setup(context)


def test_all_nodes_receive_the_same_validated_robot_count(monkeypatch):
    launch = load_module("mapping", MAPPING_LAUNCH)
    original_share = launch.get_package_share_directory
    monkeypatch.setattr(launch, "get_package_share_directory", lambda name: (
        str(ROOT / "src" / name) if (ROOT / "src" / name).is_dir()
        else original_share(name)
    ))
    context = LaunchContext()
    for action in launch.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            context.launch_configurations[action.name] = perform_substitutions(
                context, action.default_value,
            )
    context.launch_configurations["robot_count"] = "4"
    nodes = []
    original = launch.Node

    def capture(**kwargs):
        nodes.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(launch, "Node", capture)
    launch.launch_setup(context)
    assert sum(node.get("executable") == "spawn_entity.py" for node in nodes) == 4
    assert not any(node.get("executable") == "joint_state_publisher" for node in nodes)
    for node in nodes:
        for parameters in node.get("parameters", []):
            if isinstance(parameters, dict) and "robot_count" in parameters:
                assert parameters["robot_count"] == 4


def test_gazebo_joint_state_source_covers_all_movable_urdf_joints():
    model = ET.parse(ROOT / "src/multi_robot/models/turtlebot3_waffle/model.sdf")
    plugin = model.find(".//plugin[@filename='libgazebo_ros_joint_state_publisher.so']")
    urdf = ET.parse(ROOT / "src/multi_robot/urdf/turtlebot3_waffle.urdf")
    required = {j.attrib["name"] for j in urdf.findall("joint") if j.attrib["type"] != "fixed"}
    assert required <= {j.text for j in plugin.findall("joint_name")}
    assert float(plugin.findtext("update_rate")) > 0


def test_four_robot_navigation_parameters_are_consistent():
    for index in range(1, 5):
        path = ROOT / f"src/multi_robot/params/nav2_params_tb{index}_0.yaml"
        data = yaml.safe_load(path.read_text())
        costmap = data["global_costmap"]["global_costmap"]["ros__parameters"]
        assert costmap["static_layer"]["map_topic"] == "/merge_map"
        assert costmap["static_layer"]["footprint_clearing_enabled"]
        assert "peer_layer" in costmap["plugins"]
        assert costmap["peer_layer"]["combination_method"] == 1
        assert not costmap["rolling_window"]
        plugin = data["planner_server"]["ros__parameters"]["GridBased"]["plugin"]
        assert plugin == "nav2_smac_planner/SmacPlanner2D"


def test_task_timeout_makes_baseline_runner_fail(monkeypatch, tmp_path):
    runner = load_module("baseline", ROOT / "scripts/run_ideal_baseline.py")
    monkeypatch.setattr(runner, "parse_args", lambda: argparse.Namespace(
        seeds=[101], robot_count=2, world="my_world.world", duration=180.,
        coverage_threshold=.9, goal_timeout=60., startup_timeout=180.,
        message_timeout=90., evaluation_wait_timeout=270., shutdown_timeout=60.,
        run_id="controlled_timeout", output_root=tmp_path,
    ))

    def child(command, **kwargs):
        output = Path(command[command.index("--evaluation-output-dir") + 1])
        episode = command[command.index("--episode-id") + 1]
        (output / f"{episode}.json").write_text(json.dumps(native_result(success=False)))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    assert runner.main() == 1
    summary = json.loads((tmp_path / "controlled_timeout/summary.json").read_text())
    assert summary["episodes"][0]["runner_returncode"] == 0


def test_evaluator_shutdown_is_enabled_by_default():
    launch = load_module("mapping", MAPPING_LAUNCH)
    argument = next(action for action in launch.generate_launch_description().entities
                    if isinstance(action, DeclareLaunchArgument)
                    and action.name == "stop_on_evaluation_complete")
    assert perform_substitutions(LaunchContext(), argument.default_value) == "true"


def test_active_launch_and_runner_defaults_select_three_robots(monkeypatch):
    launch = load_module("mapping", MAPPING_LAUNCH)
    robot_argument = next(
        action for action in launch.generate_launch_description().entities
        if isinstance(action, DeclareLaunchArgument) and action.name == "robot_count"
    )
    assert perform_substitutions(LaunchContext(), robot_argument.default_value) == "3"
    contract_argument = next(action for action in launch.generate_launch_description().entities
                             if isinstance(action, DeclareLaunchArgument)
                             and action.name == "evaluation_contract_path")
    assert perform_substitutions(LaunchContext(), contract_argument.default_value) == ""
    ready_argument = next(
        action for action in launch.generate_launch_description().entities
        if isinstance(action, DeclareLaunchArgument) and action.name == "nav2_ready_timeout_sec"
    )
    assert perform_substitutions(LaunchContext(), ready_argument.default_value) == "300.0"
    for filename in ("ros_smoke_test.py", "run_ideal_baseline.py"):
        script = load_module(filename, ROOT / "scripts" / filename)
        monkeypatch.setattr(sys, "argv", [filename])
        args = script.parse_args()
        assert args.robot_count == 3
        assert args.task_contract is None
        assert args.startup_timeout == 300.


def test_launch_forwards_the_contract_to_the_evaluator(monkeypatch):
    launch = load_module("mapping", MAPPING_LAUNCH)
    original_share = launch.get_package_share_directory
    monkeypatch.setattr(launch, "get_package_share_directory", lambda name: (
        str(ROOT / "src" / name) if (ROOT / "src" / name).is_dir()
        else original_share(name)
    ))
    context = LaunchContext()
    for action in launch.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            context.launch_configurations[action.name] = perform_substitutions(
                context, action.default_value
            )
    context.launch_configurations["evaluation_contract_path"] = "/tmp/frozen_task.json"
    captured = []
    original = launch.Node

    def capture(**kwargs):
        if kwargs.get("executable") in ("task_evaluator", "control"):
            captured.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(launch, "Node", capture)
    launch.launch_setup(context)
    evaluator = next(node for node in captured if node["executable"] == "task_evaluator")
    control = next(node for node in captured if node["executable"] == "control")
    value = evaluator["parameters"][0]["task_contract_path"]
    assert value.perform(context) == "/tmp/frozen_task.json"
    assert control["parameters"][0]["require_task_monitor_ready"] is True


def test_contract_sets_task_budget_and_rejects_explicit_cli_conflicts(tmp_path):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    path = tmp_path / "rooms.json"
    payload = json.dumps(task_contract()).encode()
    path.write_bytes(payload)
    args = argparse.Namespace(task_contract=path, robot_count=3, world="p1c_rooms.world",
                              evaluation_duration=None, coverage_threshold=None,
                              evaluation_wait_timeout=None)
    contract = smoke.resolve_task_settings(args, "evaluation_duration", 0., 0.)
    assert (args.evaluation_duration, args.coverage_threshold) == (300., .95)
    assert args.evaluation_wait_timeout == 900.
    assert contract["sha256"] == hashlib.sha256(payload).hexdigest()
    args.evaluation_duration = 180.
    with pytest.raises(ValueError, match="conflicts"):
        smoke.resolve_task_settings(args, "evaluation_duration", 0., 0.)


@pytest.mark.parametrize("payload", [[], {**task_contract(), "max_duration_sec": float("nan")},
                                     {**task_contract(), "robots": ["tb1", "tb2"]}])
def test_invalid_task_contract_is_rejected_before_launch(tmp_path, payload):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload))
    args = argparse.Namespace(task_contract=path, robot_count=3, world="p1c_rooms.world",
                              evaluation_duration=None, coverage_threshold=None)
    with pytest.raises(ValueError):
        smoke.resolve_task_settings(args, "evaluation_duration", 0., 0.)


@pytest.mark.parametrize("filename,duration_attribute,duration,coverage,watchdog", [
    ("ros_smoke_test.py", "evaluation_duration", 0., 0., 180.),
    ("run_ideal_baseline.py", "duration", 180., .9, 270.),
])
def test_legacy_task_settings_preserve_the_original_budget(
    monkeypatch, filename, duration_attribute, duration, coverage, watchdog
):
    script = load_module(filename, ROOT / "scripts" / filename)
    monkeypatch.setattr(sys, "argv", [filename])
    args = script.parse_args()
    assert script.resolve_task_settings(args, duration_attribute, duration, coverage,
                                        legacy_wait=watchdog) is None
    assert getattr(args, duration_attribute) == duration
    assert args.coverage_threshold == coverage
    assert args.evaluation_wait_timeout == watchdog


@pytest.mark.parametrize("field,value", [
    ("schema_version", 3), ("task_contract_sha256", "wrong"),
    ("map_quality_pass", False), ("robot_participation_pass", False),
    ("collision_monitoring_fresh", False), ("task_start_barrier", "first_map"),
    ("navigation_protocol_closed", False),
    ("collision_events", 1), ("elapsed_sim_time_sec", 300.),
    ("correct_free_coverage_ratio", float("nan")), ("observed_accuracy", float("inf")),
    ("observed_accuracy", .94), ("false_free_ratio", .03), ("occupied_iou", .19),
])
def test_schema_four_cannot_pass_with_a_failed_contract_gate(field, value):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    result = native_result(schema=4)
    result[field] = value
    with pytest.raises(RuntimeError):
        smoke.validate_evaluation_result(result, .95, task_contract())


def test_schema_four_requires_each_robot_and_continuous_contact_monitoring():
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    result = native_result(schema=4)
    assert smoke.validate_evaluation_result(result, .95, task_contract()) is result
    result["robots"]["tb3"]["path_length_m"] = .99
    with pytest.raises(RuntimeError, match="inactive robot"):
        smoke.validate_evaluation_result(result, .95, task_contract())
    result["robots"]["tb3"]["path_length_m"] = 2.
    result["contact_monitor_summary"]["ever_unhealthy"] = True
    with pytest.raises(RuntimeError, match="interrupted contact monitoring"):
        smoke.validate_evaluation_result(result, .95, task_contract())


def test_runner_forwards_contract_and_rejects_invalid_native_success(monkeypatch, tmp_path):
    runner = load_module("baseline", ROOT / "scripts/run_ideal_baseline.py")
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps(task_contract()))
    monkeypatch.setattr(runner, "parse_args", lambda: argparse.Namespace(
        seeds=[101], robot_count=3, world="p1c_rooms.world", duration=None,
        coverage_threshold=None, goal_timeout=60., startup_timeout=300.,
        message_timeout=90., evaluation_wait_timeout=270., shutdown_timeout=60.,
        run_id="invalid_success", output_root=tmp_path, task_contract=path,
    ))

    def child(command, **kwargs):
        assert command[command.index("--task-contract") + 1] == str(path.resolve())
        assert command[command.index("--evaluation-duration") + 1] == "300.0"
        assert command[command.index("--coverage-threshold") + 1] == "0.95"
        output = Path(command[command.index("--evaluation-output-dir") + 1])
        episode = command[command.index("--episode-id") + 1]
        result = native_result(schema=4)
        result["task_contract_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        result["robot_participation_pass"] = False
        (output / f"{episode}.json").write_text(json.dumps(result))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    assert runner.main() == 1
    summary = json.loads((tmp_path / "invalid_success/summary.json").read_text())
    assert summary["episodes"][0]["runner_returncode"] == 0
    assert summary["episodes"][0]["termination_reason"] == "invalid_evaluation"
    assert summary["episodes"][0]["success"] is False
    assert summary["episodes"][0]["native_termination_reason"] == "coverage_reached"
    assert summary["episodes"][0]["evaluation_validation_error"]


def test_runner_keeps_native_startup_failure_separate_from_invalid_measurement(
    monkeypatch, tmp_path
):
    runner = load_module("baseline", ROOT / "scripts/run_ideal_baseline.py")
    monkeypatch.setattr(runner, "parse_args", lambda: argparse.Namespace(
        seeds=[101], robot_count=3, world="p1c_rooms.world", duration=180.,
        coverage_threshold=.9, goal_timeout=60., startup_timeout=300.,
        message_timeout=90., evaluation_wait_timeout=270., shutdown_timeout=60.,
        run_id="startup_contact", output_root=tmp_path, task_contract=None,
    ))

    def child(command, **kwargs):
        output = Path(command[command.index("--evaluation-output-dir") + 1])
        episode = command[command.index("--episode-id") + 1]
        (output / f"{episode}.json").write_text(json.dumps({
            "schema_version": 3, "success": False, "termination_reason": "startup_collision",
        }))
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(runner.subprocess, "run", child)
    assert runner.main() == 1
    summary = json.loads((tmp_path / "startup_contact/summary.json").read_text())
    row = summary["episodes"][0]
    assert row["termination_reason"] == "invalid_evaluation"
    assert row["native_termination_reason"] == "startup_collision"
    assert row["evaluation_validation_error"].startswith("evaluation result is missing")
    assert Path(row["result_path"]).is_file()


def test_plain_smoke_rejects_premature_clean_launch_exit(monkeypatch, tmp_path):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    monkeypatch.setenv("ROS_DISTRO", "humble")
    monkeypatch.setattr(smoke.shutil, "which", lambda *args: "/usr/bin/ros2")
    monkeypatch.setattr(smoke, "parse_args", lambda: argparse.Namespace(
        robot_count=1, world="my_world.world", gazebo_seed=1, goal_timeout=60.,
        spawn_timeout=90., startup_timeout=180., message_timeout=30.,
        dwell_seconds=0., shutdown_timeout=30., evaluation_duration=0.,
        coverage_threshold=0., evaluation_wait_timeout=180., episode_id="plain",
        evaluation_output_dir=tmp_path / "evaluation", log_dir=tmp_path / "logs",
    ))
    monkeypatch.setattr(smoke, "run_ros", lambda *args, **kwargs: (
        subprocess.CompletedProcess([], 0, "", "")
    ))
    monkeypatch.setattr(smoke, "wait_until_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "require_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *args, **kwargs: (
        SimpleNamespace(poll=lambda: 0, returncode=0)
    ))
    assert smoke.main() == 1


def test_parent_exit_does_not_hide_native_child_shutdown_escalation():
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    assert smoke.native_launch_failures(
        "[INFO] [planner-1]: process has finished cleanly\n[WARN] failed goal"
    ) == []
    for text in (
        "process has died [exit code -6]", "process has died [exit code -9]",
        "failed to terminate '10.0' seconds after receiving 'SIGTERM'",
        "sending signal 'SIGKILL' to process",
    ):
        assert smoke.native_launch_failures(text) == [text]
