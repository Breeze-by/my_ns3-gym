"""Validate launch contracts and smoke checks without starting ROS processes."""

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from launch import LaunchContext
from launch.actions import (
    DeclareLaunchArgument, EmitEvent, ExecuteProcess, IncludeLaunchDescription, LogInfo,
    RegisterEventHandler, TimerAction,
)
from launch.event_handlers import OnProcessStart
from launch.events import Shutdown
from launch.events.process import ProcessExited, ProcessStarted
from launch.utilities import normalize_to_list_of_substitutions, perform_substitutions
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


def mapping_actions(monkeypatch, tmp_path, stepped=False, installed_plugin=True):
    launch = load_module("mapping", MAPPING_LAUNCH)
    original_share = launch.get_package_share_directory
    monkeypatch.setattr(launch, "get_package_share_directory", lambda name: (
        str(ROOT / "src" / name) if (ROOT / "src" / name).is_dir()
        else original_share(name)
    ))
    monkeypatch.setattr(launch, "get_package_prefix", lambda name: str(tmp_path))
    plugin = tmp_path / "lib/libmr3_gazebo_step.so"
    if installed_plugin:
        plugin.parent.mkdir()
        plugin.touch()
    context = LaunchContext()
    for action in launch.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            context.launch_configurations[action.name] = perform_substitutions(
                context, action.default_value,
            )
    context.launch_configurations.update({
        "execution_mode": "adapter" if stepped else "baseline",
        "mr3_stepped": str(stepped).lower(), "gazebo_seed": "101",
        "enable_gzclient": "false", "enable_rviz": "false",
        "enable_merge_rviz": "false", "enable_drive": "false",
    })
    return launch, context, plugin


def test_stepped_server_plugin_is_a_real_option_before_ros_argument_terminator(
    monkeypatch, tmp_path
):
    launch, context, plugin = mapping_actions(monkeypatch, tmp_path, stepped=True)
    actions = launch.launch_setup(context)
    server = next(action for action in actions if isinstance(action, ExecuteProcess)
                  and perform_substitutions(context, action.cmd[0]) == "gzserver")
    argv = [perform_substitutions(context, token) for token in server.cmd]
    assert argv == [
        "gzserver", str(ROOT / "src/multi_robot/worlds/my_world.world"), "--seed=101",
        "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so",
        "-s", "libgazebo_ros_force_system.so", "-s", str(plugin),
        "--ros-args", "--params-file", str(ROOT / "src/multi_robot/config/mr3_step_clock.yaml"),
        "--",
    ]
    assert argv.index(str(plugin)) < argv.index("--ros-args") < argv.index("--")
    assert not any(token.startswith("-s ") for token in argv)
    environment = {perform_substitutions(context, key): perform_substitutions(context, value)
                   for key, value in server.additional_env}
    assert all(environment[key] for key in (
        "GAZEBO_MODEL_PATH", "GAZEBO_PLUGIN_PATH", "GAZEBO_RESOURCE_PATH"))
    started = ProcessStarted(action=server, name="gzserver-4", pid=12345, cmd=argv,
                             cwd=None, env=environment)
    on_start = next(action.event_handler for action in actions
                    if isinstance(action, RegisterEventHandler)
                    and isinstance(action.event_handler, OnProcessStart))
    messages = [perform_substitutions(context, action.msg)
                for action in on_start.handle(started, context) if isinstance(action, LogInfo)]
    record = json.loads(next(message.split("MR3_GAZEBO_SERVER_START ", 1)[1]
                             for message in messages if "MR3_GAZEBO_SERVER_START " in message))
    assert record["argv"] == argv
    assert record["pid"] == 12345
    assert record["selected_step_plugin"] == str(plugin)
    assert record["selected_clock_parameters"] == argv[-2]
    assert record["gazebo_plugin_path"] == environment["GAZEBO_PLUGIN_PATH"]


def test_baseline_keeps_the_gazebo_ros_include_arguments(monkeypatch, tmp_path):
    launch, context, _ = mapping_actions(monkeypatch, tmp_path)
    actions = launch.launch_setup(context)
    included = [action for action in actions if isinstance(action, IncludeLaunchDescription)]
    server = next(action for action in included
                  if "server_required" in dict(action.launch_arguments))
    assert {key: perform_substitutions(context, normalize_to_list_of_substitutions(value))
            for key, value in server.launch_arguments} == {
        "world": str(ROOT / "src/multi_robot/worlds/my_world.world"),
        "seed": "101", "server_required": "false",
    }


def test_stepped_launch_fails_before_start_if_installed_plugin_is_missing(monkeypatch, tmp_path):
    launch, context, _ = mapping_actions(
        monkeypatch, tmp_path, stepped=True, installed_plugin=False,
    )
    with pytest.raises(ValueError, match="installed MR3 stepping plugin does not exist"):
        launch.launch_setup(context)


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
        "contact_subscription_started_sim_time_sec": 1.,
        "contact_subscription_bootstrap_state": "contact_subscriptions_started",
        "contact_clock_overflow_diagnostic": None,
    }


def task_contract():
    return {
        "robots": ["tb1", "tb2", "tb3"], "world_file": "p1c_rooms.world",
        "max_duration_sec": 300., "coverage_threshold": .95,
        "participation": {"min_path_length_m": 1., "min_goal_count": 1},
        "quality": {"min_observed_accuracy": .95, "max_false_free_ratio": .02,
                    "min_occupied_iou": .20}, "sha256": "contract-hash",
    }


def reducer_summary():
    row = {
        "received": 10, "published": 10, "raw_states": 20, "compact_states": 10,
        "sequence_observed": 10, "sequence_unavailable": 0, "publisher_count": 1,
        "sequence_gaps": 0, "sequence_duplicates": 0, "sequence_regressions": 0,
    }
    components = ("base", "lidar", "wheel_left", "wheel_right",
                  "caster_back_left", "caster_back_right")
    return {"publication_sequence_supported": True, "topics": {
        f"tb{robot}/{component}": dict(row) for robot in range(1, 4) for component in components
    }}


def reducer_log(summary):
    return "[mr3_contact_reducer-2] MR3_CONTACT_REDUCER_SUMMARY " + json.dumps(summary) + "\n"


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


def gazebo_stop_launch(monkeypatch, enabled=True):
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
    context.launch_configurations["world"] = "p1c_rooms.world"
    context.launch_configurations["stop_on_evaluation_complete"] = str(enabled).lower()
    evaluators = []
    original_node = launch.Node

    def capture(**kwargs):
        node = original_node(**kwargs)
        if kwargs.get("executable") == "task_evaluator":
            evaluators.append(node)
        return node

    monkeypatch.setattr(launch, "Node", capture)
    actions = launch.launch_setup(context)
    handlers = [action.event_handler for action in actions
                if isinstance(action, RegisterEventHandler)]
    server = ExecuteProcess(cmd=["gzserver"])
    server_details = {
        "action": server, "name": "gzserver-41", "pid": 4321,
        "cmd": ["gzserver", str(ROOT / "src/multi_robot/worlds/p1c_rooms.world")],
        "cwd": None, "env": {"GAZEBO_MASTER_URI": "http://127.0.0.1:11851", "PATH": "/usr/bin"},
    }
    evaluator_event = ProcessExited(returncode=0, action=evaluators[0], name="evaluator-99",
                                    pid=7654, cmd=["task_evaluator"], cwd=None, env={})
    server_exit = ProcessExited(returncode=0, **server_details)
    on_evaluation = next(handler for handler in handlers if handler.matches(evaluator_event)
                         and not handler.matches(server_exit))
    on_start = next(handler for handler in handlers if isinstance(handler, OnProcessStart))
    on_server_exit = next(handler for handler in handlers if handler.matches(server_exit))
    return context, server_details, evaluator_event, on_start, on_evaluation, on_server_exit


def shutdown_actions(actions):
    return [action for action in actions if isinstance(action, EmitEvent)
            and isinstance(action.event, Shutdown)]


def error_markers(actions, context):
    return [perform_substitutions(context, action.msg) for action in actions
            if isinstance(action, LogInfo)
            and "MR3_GAZEBO_NATIVE_STOP_ERROR" in perform_substitutions(context, action.msg)]


@pytest.mark.parametrize("first", ["stop_cli", "server"])
def test_evaluation_waits_for_both_owned_server_and_stop_cli_exits(monkeypatch, first):
    context, server, evaluation, on_start, on_evaluation, on_exit = gazebo_stop_launch(monkeypatch)
    on_start.handle(ProcessStarted(**server), context)
    context.environment["GAZEBO_MASTER_URI"] = "http://127.0.0.1:9999"
    actions = on_evaluation.handle(evaluation, context)
    assert not shutdown_actions(actions)
    stop = next(action for action in actions if isinstance(action, ExecuteProcess))
    assert [perform_substitutions(context, token) for token in stop.cmd] == [
        "gz", "topic", "-p", "/gazebo/server/control", "-m", "stop: true",
    ]
    assert {perform_substitutions(context, key): perform_substitutions(context, value)
            for key, value in stop.env} == server["env"]
    stop_handler = next(action.event_handler for action in actions
                        if isinstance(action, RegisterEventHandler))
    cli_exit = ProcessExited(returncode=0, action=stop, name="stop-100", pid=5432,
                             cmd=["gz", "topic"], cwd=None, env=server["env"])
    assert on_exit.handle(cli_exit, context) == []
    assert on_evaluation.handle(evaluation, context) == []
    server_exit = ProcessExited(returncode=0, **server)
    if first == "stop_cli":
        assert stop_handler.handle(cli_exit, context) == []
        exited_actions = on_exit.handle(server_exit, context)
    else:
        assert on_exit.handle(server_exit, context) == []
        exited_actions = stop_handler.handle(cli_exit, context)
    assert len(shutdown_actions(exited_actions)) == 1
    timer = next(action for action in actions if isinstance(action, TimerAction))
    assert timer.actions[0].execute(context) == []


@pytest.mark.parametrize("changed", ["action", "pid", "name"])
def test_gazebo_stop_rejects_foreign_exit_identity(monkeypatch, changed):
    context, server, evaluation, on_start, on_evaluation, on_exit = gazebo_stop_launch(monkeypatch)
    on_start.handle(ProcessStarted(**server), context)
    actions = on_evaluation.handle(evaluation, context)
    foreign = dict(server)
    foreign[changed] = {"action": ExecuteProcess(cmd=["gzserver"]),
                        "pid": 4322, "name": "gzserver-42"}[changed]
    assert on_exit.handle(ProcessExited(returncode=0, **foreign), context) == []
    timer = next(action for action in actions if isinstance(action, TimerAction))
    assert timer.period == 10.0
    timed_out = timer.actions[0].execute(context)
    assert len(shutdown_actions(timed_out)) == 1
    assert error_markers(timed_out, context) == [
        "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exit_timeout_10_wall_sec",
    ]


def test_failed_stop_cli_is_preserved_and_clean_cli_cannot_suppress_timeout(monkeypatch):
    context, server, evaluation, on_start, on_evaluation, _ = gazebo_stop_launch(monkeypatch)
    on_start.handle(ProcessStarted(**server), context)
    actions = on_evaluation.handle(evaluation, context)
    stop = next(action for action in actions if isinstance(action, ExecuteProcess))
    handler = next(action.event_handler for action in actions
                   if isinstance(action, RegisterEventHandler))
    failed = ProcessExited(returncode=2, action=stop, name="stop-100", pid=5432,
                           cmd=["gz", "topic"], cwd=None, env=server["env"])
    failed_actions = handler.handle(failed, context)
    assert len(shutdown_actions(failed_actions)) == 1
    assert error_markers(failed_actions, context) == [
        "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR stop_cli_exit_code=2",
    ]
    assert failed.returncode == 2
    timer = next(action for action in actions if isinstance(action, TimerAction))
    assert error_markers(timer.actions[0].execute(context), context)


def test_server_exit_cannot_disable_watchdog_for_a_live_stop_cli(monkeypatch):
    context, server, evaluation, on_start, on_evaluation, on_exit = gazebo_stop_launch(monkeypatch)
    on_start.handle(ProcessStarted(**server), context)
    actions = on_evaluation.handle(evaluation, context)
    assert on_exit.handle(ProcessExited(returncode=0, **server), context) == []
    timer = next(action for action in actions if isinstance(action, TimerAction))
    timed_out = timer.actions[0].execute(context)
    assert len(shutdown_actions(timed_out)) == 1
    assert error_markers(timed_out, context) == [
        "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR stop_cli_exit_timeout_10_wall_sec",
    ]


def test_server_exit_zero_before_evaluation_fails_without_waiting_for_clock(monkeypatch):
    context, server, evaluation, on_start, on_evaluation, on_exit = gazebo_stop_launch(monkeypatch)
    on_start.handle(ProcessStarted(**server), context)
    early_exit = ProcessExited(returncode=0, **server)
    early_actions = on_exit.handle(early_exit, context)
    assert early_exit.returncode == 0
    assert len(shutdown_actions(early_actions)) == 1
    assert error_markers(early_actions, context) == [
        "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exited_before_evaluation exit_code=0",
    ]
    actions = on_evaluation.handle(evaluation, context)
    assert not any(isinstance(action, ExecuteProcess) for action in actions)
    assert len(shutdown_actions(actions)) == 1
    assert error_markers(actions, context) == [
        "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exited_before_evaluation",
    ]


def test_gazebo_abort_keeps_nonzero_native_exit_and_marks_failure(monkeypatch):
    context, server, evaluation, on_start, on_evaluation, on_exit = gazebo_stop_launch(monkeypatch)
    on_start.handle(ProcessStarted(**server), context)
    on_evaluation.handle(evaluation, context)
    abort = ProcessExited(returncode=-6, **server)
    actions = on_exit.handle(abort, context)
    assert abort.returncode == -6
    assert len(shutdown_actions(actions)) == 1
    assert error_markers(actions, context) == [
        "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exit_code=-6",
    ]


def test_stop_disabled_does_not_request_native_stop_or_shutdown(monkeypatch):
    context, _, evaluation, _, on_evaluation, _ = gazebo_stop_launch(monkeypatch, enabled=False)
    assert on_evaluation.handle(evaluation, context) == []


def test_missing_owned_server_fails_without_publishing_to_another_master(monkeypatch):
    context, server, evaluation, on_start, on_evaluation, _ = gazebo_stop_launch(monkeypatch)
    server["cmd"] = ["gzserver", "/another/world.world"]
    assert on_start.handle(ProcessStarted(**server), context) == []
    actions = on_evaluation.handle(evaluation, context)
    assert len(shutdown_actions(actions)) == 1
    assert not any(isinstance(action, ExecuteProcess) for action in actions)
    assert error_markers(actions, context) == [
        "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR owned_server_not_started",
    ]


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
    ("contact_subscription_started_sim_time_sec", None),
    ("contact_subscription_started_sim_time_sec", 0.),
    ("contact_subscription_started_sim_time_sec", 3.),
    ("contact_subscription_started_sim_time_sec", float("nan")),
    ("contact_subscription_bootstrap_state", "waiting_for_simulation_clock"),
    ("contact_clock_overflow_diagnostic", {}),
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


@pytest.mark.parametrize("field", [
    "contact_subscription_started_sim_time_sec", "contact_subscription_bootstrap_state",
    "contact_clock_overflow_diagnostic",
])
def test_schema_four_cannot_pass_without_contact_bootstrap_evidence(field):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    result = native_result(schema=4)
    del result[field]
    with pytest.raises(RuntimeError, match="missing"):
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
            "control_failure": "contact_clock_desynchronization",
        }))
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(runner.subprocess, "run", child)
    assert runner.main() == 1
    summary = json.loads((tmp_path / "startup_contact/summary.json").read_text())
    row = summary["episodes"][0]
    assert row["termination_reason"] == "invalid_evaluation"
    assert row["native_termination_reason"] == "startup_collision"
    assert row["native_control_failure"] == "contact_clock_desynchronization"
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
        "ERROR: MR3_ROS_SHUTDOWN_ERROR missing_clean_exit",
    ):
        assert smoke.native_launch_failures(text) == [text]


def test_native_reducer_summary_requires_one_complete_supported_transport():
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    summary = reducer_summary()
    assert smoke.validate_contact_reducer_summary(reducer_log(summary)) == summary
    for text in ("", reducer_log(summary) * 2, "MR3_CONTACT_REDUCER_SUMMARY broken JSON\n"):
        with pytest.raises(RuntimeError):
            smoke.validate_contact_reducer_summary(text)
    summary["publication_sequence_supported"] = False
    with pytest.raises(RuntimeError, match="not supported"):
        smoke.validate_contact_reducer_summary(reducer_log(summary))


@pytest.mark.parametrize("field,value", [
    ("received", 0), ("received", True), ("published", 9), ("sequence_observed", 9),
    ("sequence_unavailable", 1), ("sequence_gaps", 1), ("sequence_duplicates", 1),
    ("sequence_regressions", 1), ("publisher_count", 2), ("compact_states", 21),
    ("raw_states", float("nan")), ("compact_states", float("inf")),
])
def test_native_reducer_summary_rejects_incomplete_or_invalid_delivery(field, value):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    summary = reducer_summary()
    summary["topics"]["tb2/caster_back_left"][field] = value
    with pytest.raises(RuntimeError):
        smoke.validate_contact_reducer_summary(reducer_log(summary))


def test_native_reducer_summary_rejects_missing_or_unexpected_components_and_counters():
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    summary = reducer_summary()
    del summary["topics"]["tb3/lidar"]
    with pytest.raises(RuntimeError, match="18 components"):
        smoke.validate_contact_reducer_summary(reducer_log(summary))
    summary = reducer_summary()
    summary["topics"]["tb4/base"] = summary["topics"]["tb1/base"]
    with pytest.raises(RuntimeError, match="18 components"):
        smoke.validate_contact_reducer_summary(reducer_log(summary))
    summary = reducer_summary()
    del summary["topics"]["tb1/base"]["sequence_observed"]
    with pytest.raises(RuntimeError, match="invalid counters"):
        smoke.validate_contact_reducer_summary(reducer_log(summary))


def test_smoke_rejects_reducer_gap_after_clean_exit_without_changing_native_result(
    monkeypatch, tmp_path
):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps(task_contract()))
    output = tmp_path / "evaluation"
    native = native_result(schema=4)
    native["task_contract_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = json.dumps(native)
    args = argparse.Namespace(
        robot_count=3, world="p1c_rooms.world", gazebo_seed=101, goal_timeout=60.,
        spawn_timeout=90., startup_timeout=300., message_timeout=30.,
        dwell_seconds=0., shutdown_timeout=30., evaluation_duration=None,
        coverage_threshold=None, evaluation_wait_timeout=900., episode_id="native_success",
        evaluation_output_dir=output, log_dir=tmp_path / "logs", task_contract=path,
    )
    monkeypatch.setattr(smoke, "parse_args", lambda: args)
    monkeypatch.setenv("ROS_DISTRO", "humble")
    monkeypatch.setattr(smoke.shutil, "which", lambda *args: "/usr/bin/ros2")
    monkeypatch.setattr(smoke, "run_ros", lambda *args, **kwargs: (
        subprocess.CompletedProcess([], 0, "", "")
    ))
    monkeypatch.setattr(smoke, "wait_until_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "require_message", lambda *args, **kwargs: None)

    def start(command, **kwargs):
        output.mkdir()
        (output / "native_success.json").write_text(payload)
        summary = reducer_summary()
        summary["topics"]["tb2/caster_back_left"]["sequence_gaps"] = 1
        kwargs["stdout"].write(reducer_log(summary))
        kwargs["stdout"].flush()
        return SimpleNamespace(poll=lambda: 0, wait=lambda **kwargs: 0, returncode=0)

    monkeypatch.setattr(smoke.subprocess, "Popen", start)
    assert smoke.main() == 1
    assert (output / "native_success.json").read_text() == payload


@pytest.mark.parametrize("outcome", [
    "message", "cli_error", "timeout", "terminal_json", "launch_exit",
])
def test_message_probe_observes_terminal_state_and_keeps_real_failures(
    monkeypatch, tmp_path, outcome
):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    clock = [0.0]
    process = SimpleNamespace(returncode=None)
    process.poll = lambda: process.returncode
    probe = SimpleNamespace(returncode=None, stderr=io.StringIO())
    commands, stopped = [], []
    result_path = tmp_path / "terminal.json"
    environment = {"PATH": "/usr/bin:/bin", "ROS_DOMAIN_ID": "224"}

    def communicate(timeout):
        clock[0] += timeout
        if outcome == "message":
            probe.returncode = 0
            return None, ""
        if outcome == "cli_error":
            probe.returncode = 2
            return None, "incompatible topic type"
        if outcome == "terminal_json":
            result_path.write_text("{}")
        if outcome == "launch_exit":
            process.returncode = 1
        raise subprocess.TimeoutExpired("owned probe", timeout)

    probe.communicate = communicate

    def start(command, **kwargs):
        commands.append((command, kwargs))
        return probe

    def stop(owned, timeout):
        stopped.append((owned, timeout))
        owned.returncode = 0 if owned.returncode == 0 else -2
        return True

    monkeypatch.setattr(smoke.subprocess, "Popen", start)
    monkeypatch.setattr(smoke, "stop_launch", stop)
    monkeypatch.setattr(smoke.time, "monotonic", lambda: clock[0])
    arguments = ("/merge_map", .2, ("--qos-reliability", "reliable"),
                 process, result_path, environment)
    if outcome == "cli_error":
        with pytest.raises(RuntimeError, match="incompatible topic type"):
            smoke.require_message(*arguments)
    elif outcome == "timeout":
        with pytest.raises(TimeoutError, match="within 0.2 seconds"):
            smoke.require_message(*arguments)
    else:
        assert smoke.require_message(*arguments) is (outcome == "message")
    assert len(commands) == 1
    assert commands[0][0] == [
        "ros2", "topic", "echo", "--once", "--qos-reliability", "reliable", "/merge_map",
    ]
    assert commands[0][1]["env"] is environment
    assert commands[0][1]["start_new_session"] is True
    assert stopped == [(probe, 2.0)]
    assert probe.stderr.closed
    assert process.returncode == (1 if outcome == "launch_exit" else None)


def test_terminal_result_before_probe_does_not_start_a_cli(monkeypatch, tmp_path):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    result_path = tmp_path / "terminal.json"
    result_path.write_text("{}")

    def unexpected(*args, **kwargs):
        raise AssertionError("a completed evaluation must not start a topic probe")

    monkeypatch.setattr(smoke.subprocess, "Popen", unexpected)
    assert smoke.require_message("/merge_map", 90, result_path=result_path) is False


def test_probe_forced_cleanup_does_not_replace_its_original_cli_error(monkeypatch, capsys):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    probe = SimpleNamespace(returncode=2, stderr=io.StringIO(),
                            communicate=lambda **kwargs: (None, "incompatible topic type"))
    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *args, **kwargs: probe)
    monkeypatch.setattr(smoke, "stop_launch", lambda *args: False)
    with pytest.raises(RuntimeError, match="incompatible topic type"):
        smoke.require_message("/merge_map", 90)
    assert "owned topic probe" in capsys.readouterr().err
    assert probe.stderr.closed


@pytest.mark.parametrize("outcome", ["terminal_json", "launch_exit", "runtime_error", "timeout"])
def test_readiness_exits_for_terminal_evidence_without_suppressing_other_errors(
    monkeypatch, tmp_path, outcome
):
    import multi_robot_exploration.nav2_ready_gate as gate
    import rclpy
    import rclpy.node

    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    result_path = tmp_path / "terminal.json"
    if outcome in ("terminal_json", "runtime_error"):
        result_path.write_text("{}")
    process = SimpleNamespace(returncode=1 if outcome == "launch_exit" else None)
    process.poll = lambda: process.returncode
    destroyed = []
    node = SimpleNamespace(create_subscription=lambda *args: None,
                           destroy_node=lambda: destroyed.append(True))
    monkeypatch.setattr(rclpy, "init", lambda: None)
    monkeypatch.setattr(rclpy, "ok", lambda: False)
    monkeypatch.setattr(rclpy.node, "Node", lambda *args: node)

    def wait(node, robot_count, timeout, extra_check):
        if outcome == "runtime_error":
            raise RuntimeError("live-context callback error")
        if outcome == "timeout":
            return 1
        extra_check()
        raise AssertionError("terminal evidence must end readiness immediately")

    monkeypatch.setattr(gate, "wait_for_nav2", wait)
    if outcome == "runtime_error":
        with pytest.raises(RuntimeError, match="live-context callback error"):
            smoke.wait_until_ready(process, 3, 300, True, result_path)
    elif outcome == "timeout":
        with pytest.raises(TimeoutError, match="did not become ready"):
            smoke.wait_until_ready(process, 3, 300, True, result_path)
    else:
        assert smoke.wait_until_ready(process, 3, 300, True, result_path) is False
    assert destroyed == [True]


@pytest.mark.parametrize("phase", ["readiness", "scan_probe"])
@pytest.mark.parametrize("outcome", [
    "startup_failure", "native_exit", "native_child_failure", "reducer_gap",
])
def test_early_terminal_evaluation_preserves_json_and_all_native_checks(
    monkeypatch, tmp_path, capsys, phase, outcome
):
    smoke = load_module("smoke", ROOT / "scripts/ros_smoke_test.py")
    contract_path = tmp_path / "rooms.json"
    contract_path.write_text(json.dumps(task_contract()))
    output = tmp_path / "evaluation"
    output.mkdir()
    result_path = output / "early.json"
    native = native_result(schema=4)
    native["task_contract_sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if outcome == "startup_failure":
        native.update(success=False, termination_reason="navigation_failure",
                      control_failure="contact_clock_desynchronization",
                      model_state_message_count=0, start_sim_time_sec=None,
                      elapsed_sim_time_sec=0.)
    payload = json.dumps(native)
    args = argparse.Namespace(
        robot_count=3, world="p1c_rooms.world", gazebo_seed=202, goal_timeout=60.,
        spawn_timeout=90., startup_timeout=300., message_timeout=90.,
        dwell_seconds=0., shutdown_timeout=30., evaluation_duration=None,
        coverage_threshold=None, evaluation_wait_timeout=900., episode_id="early",
        evaluation_output_dir=output, log_dir=tmp_path / "logs", task_contract=contract_path,
    )
    monkeypatch.setattr(smoke, "parse_args", lambda: args)
    monkeypatch.setenv("ROS_DISTRO", "humble")
    monkeypatch.setattr(smoke.shutil, "which", lambda *args: "/usr/bin/ros2")
    monkeypatch.setattr(smoke, "run_ros", lambda *args, **kwargs: (
        subprocess.CompletedProcess([], 0, "", "")
    ))
    probe_topics = []

    def ready(*args, **kwargs):
        if phase == "readiness":
            result_path.write_text(payload)
            return False
        return True

    def probe(topic, *args, **kwargs):
        probe_topics.append(topic)
        assert topic == "/tb1/scan"
        result_path.write_text(payload)
        return False

    def start(command, **kwargs):
        summary = reducer_summary()
        if outcome == "reducer_gap":
            summary["topics"]["tb2/caster_back_left"]["sequence_gaps"] = 1
        kwargs["stdout"].write(reducer_log(summary))
        if outcome == "native_child_failure":
            kwargs["stdout"].write("[ERROR] [planner-1]: process has died [exit code -6]\n")
        kwargs["stdout"].flush()
        return SimpleNamespace(poll=lambda: 1 if outcome == "native_exit" else 0,
                               wait=lambda **kwargs: 0,
                               returncode=1 if outcome == "native_exit" else 0)

    monkeypatch.setattr(smoke, "wait_until_ready", ready)
    monkeypatch.setattr(smoke, "require_message", probe)
    monkeypatch.setattr(smoke.subprocess, "Popen", start)
    assert smoke.main() == 1
    assert probe_topics == (["/tb1/scan"] if phase == "scan_probe" else [])
    assert result_path.read_text() == payload
    if outcome == "startup_failure":
        error = capsys.readouterr().err
        assert "contact_clock_desynchronization" in error
        assert "termination_reason='navigation_failure'" in error
        assert "no valid model_state_message_count" in error
