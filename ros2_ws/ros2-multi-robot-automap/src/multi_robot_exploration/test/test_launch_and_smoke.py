"""Validate launch contracts and smoke checks without starting ROS processes."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

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
    for node in nodes:
        for parameters in node.get("parameters", []):
            if isinstance(parameters, dict) and "robot_count" in parameters:
                assert parameters["robot_count"] == 4


def test_four_robot_navigation_parameters_are_consistent():
    for index in range(1, 5):
        path = ROOT / f"src/multi_robot/params/nav2_params_tb{index}_0.yaml"
        data = yaml.safe_load(path.read_text())
        costmap = data["global_costmap"]["global_costmap"]["ros__parameters"]
        assert costmap["static_layer"]["map_topic"] == "/merge_map"
        assert costmap["static_layer"]["footprint_clearing_enabled"]
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
