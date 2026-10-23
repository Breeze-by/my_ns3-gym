"""Check actual launch-selected SLAM/Nav2 settings for short MR3 subgoals."""

import importlib.util
from pathlib import Path
import re

from launch import LaunchContext
import pytest
import yaml

from multi_robot_exploration.mr3_observation import GOAL_XY_TOLERANCE_M
from test_mr3_adapter_launch import configured_launch, ROOT


@pytest.mark.parametrize("mode", ["baseline", "adapter"])
def test_all_three_launch_selected_nav2_checkers_match_candidate_acceptance_disk(
        monkeypatch, mode):
    context, _, _, includes = configured_launch(monkeypatch, execution_mode=mode)
    bringups = [arguments for arguments in includes if "params_file" in arguments]
    assert [arguments["namespace"] for arguments in bringups] == ["/tb1", "/tb2", "/tb3"]
    assert GOAL_XY_TOLERANCE_M == .10
    for arguments in bringups:
        robot = arguments["namespace"].lstrip("/")
        original = ROOT / f"src/multi_robot/params/nav2_params_{robot}_0.yaml"
        parameters = arguments["params_file"]
        if mode == "adapter":
            # Use the actual rewritten input that Nav2 receives in adapter mode.
            selected = Path(parameters.perform(context))
            try:
                document = yaml.safe_load(selected.read_text())
            finally:
                selected.unlink()
        else:
            assert parameters == str(original)
            document = yaml.safe_load(original.read_text())
        controller = document["controller_server"]["ros__parameters"]
        assert controller["goal_checker_plugins"] == ["goal_checker"]
        checker = controller["goal_checker"]
        assert checker["plugin"] == "nav2_controller::SimpleGoalChecker"
        assert checker["xy_goal_tolerance"] == GOAL_XY_TOLERANCE_M
        assert checker["yaw_goal_tolerance"] == 3.14
        # RotateToGoal rejects translation inside DWB's separate tolerance.
        # It must not latch a larger stopping window than the goal checker.
        assert "RotateToGoal" in controller["FollowPath"]["critics"]
        assert controller["FollowPath"]["xy_goal_tolerance"] == GOAL_XY_TOLERANCE_M


@pytest.mark.parametrize("robot", ["tb1", "tb2", "tb3"])
def test_actual_namespaced_slam_parameters_use_recognized_mapper_motion_keys(
        monkeypatch, robot):
    main_launch = (ROOT / "src/multi_robot/launch/"
                   "gazebo_multirobot_mapping_with_nav2.launch.py")
    slam_launch = (ROOT / "src/slam_toolbox/launch/"
                   "online_async_multirobot_launch.py")
    assert f'"{slam_launch.name}"' in main_launch.read_text()
    spec = importlib.util.spec_from_file_location("mr3_short_subgoal_slam_launch", slam_launch)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_package_share_directory",
                        lambda name: str(ROOT / "src" / name))
    nodes = []
    original_node = module.Node

    def capture_node(**arguments):
        nodes.append(arguments)
        return original_node(**arguments)

    monkeypatch.setattr(module, "Node", capture_node)
    module.generate_launch_description()
    assert len(nodes) == 1
    assert nodes[0]["executable"] == "multirobot_slam_toolbox_node"
    context = LaunchContext()
    context.launch_configurations.update(namespace="/" + robot, use_sim_time="true")
    parameter_file = nodes[0]["parameters"][0]
    selected = parameter_file.evaluate(context)
    try:
        document = yaml.safe_load(selected.read_text())
    finally:
        selected.unlink()
    assert set(document) == {"/" + robot + "/slam_toolbox"}
    parameters = document["/" + robot + "/slam_toolbox"]["ros__parameters"]
    assert parameters["minimum_travel_distance"] == .10
    assert parameters["minimum_travel_heading"] == .20
    assert parameters["minimum_time_interval"] == .5
    assert parameters["map_update_interval"] == 5.
    assert parameters["resolution"] == .05
    assert parameters["use_scan_matching"] is True
    parser = (ROOT / "src/slam_toolbox/src/slam_mapper.cpp").read_text()
    configured_keys = set(re.findall(r'node->get_parameter\("([^\"]+)"', parser))
    assert {"minimum_travel_distance", "minimum_travel_heading"} <= configured_keys
    # The ROS time throttle is not Karto's maximum-period OR-motion parameter.
    assert "minimum_time_interval" not in configured_keys
