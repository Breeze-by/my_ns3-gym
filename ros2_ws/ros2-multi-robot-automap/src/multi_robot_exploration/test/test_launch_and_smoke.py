"""Validate launch contracts and smoke checks without starting ROS processes."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
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
    spec.loader.exec_module(module)
    return module


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
        (output / f"{episode}.json").write_text(json.dumps({
            "success": False, "termination_reason": "timeout", "failure_reason": "timeout",
        }))
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
