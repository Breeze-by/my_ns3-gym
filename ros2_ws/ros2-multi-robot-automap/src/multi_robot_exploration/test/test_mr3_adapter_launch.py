"""Verify active baseline/adapter launch contracts without starting processes."""

import copy
import importlib.util
from pathlib import Path

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.events.process import ProcessExited
from launch.utilities import perform_substitutions
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
MAPPING_LAUNCH = ROOT / "src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py"


def configured_launch(monkeypatch, **overrides):
    spec = importlib.util.spec_from_file_location("mr3_mapping_launch", MAPPING_LAUNCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_share = module.get_package_share_directory
    monkeypatch.setattr(module, "get_package_share_directory", lambda name: (
        str(ROOT / "src" / name) if (ROOT / "src" / name).is_dir()
        else original_share(name)
    ))
    context = LaunchContext()
    for action in module.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            context.launch_configurations[action.name] = perform_substitutions(
                context, action.default_value)
    context.launch_configurations.update({"world": "p1c_rooms.world", **overrides})
    nodes, includes = [], []
    original_node = module.Node
    original_include = module.IncludeLaunchDescription

    def capture_node(**kwargs):
        node = original_node(**kwargs)
        nodes.append((node, kwargs))
        return node

    def capture_include(*args, **kwargs):
        includes.append(dict(kwargs.get("launch_arguments", ())))
        return original_include(*args, **kwargs)

    monkeypatch.setattr(module, "Node", capture_node)
    monkeypatch.setattr(module, "IncludeLaunchDescription", capture_include)
    actions = module.launch_setup(context)
    return context, actions, nodes, includes


def released_nodes(context, actions, nodes):
    """Inspect the actual ready-gate release; a merely constructed node is inert."""
    gate = next(node for node, arguments in nodes
                if arguments["executable"] == "nav2_ready_gate")
    event = ProcessExited(returncode=0, action=gate, name="nav2-ready-test", pid=1001,
                          cmd=["nav2_ready_gate"], cwd=None, env={})
    released = list(actions)
    for action in actions:
        if isinstance(action, RegisterEventHandler) and action.event_handler.matches(event):
            released.extend(action.event_handler.handle(event, context))
    return [arguments for node, arguments in nodes if node in released]


@pytest.mark.parametrize("mode", ["baseline", "adapter"])
def test_ready_gate_releases_exactly_one_goal_owner_and_matching_information_path(
        monkeypatch, mode):
    context, actions, nodes, _ = configured_launch(monkeypatch, execution_mode=mode)
    active = released_nodes(context, actions, nodes)
    executables = [node["executable"] for node in active]
    assert sum(executable in ("control", "mr3_adapter") for executable in executables) == 1
    assert ("mr3_adapter" in executables) == (mode == "adapter")
    assert ("control" in executables) == (mode == "baseline")
    assert ("mr3_information" in executables) == (mode == "adapter")
    assert ("merge_map" in executables) == (mode == "baseline")
    if mode == "adapter":
        for executable in ("mr3_information", "mr3_adapter"):
            arguments = next(item for item in active if item["executable"] == executable)
            parameters = arguments["parameters"][0]
            assert parameters["robot_count"] == 3
            assert parameters["episode_epoch"].perform(context) == "mr3-p1b"


@pytest.mark.parametrize("audit_enabled", [False, True])
def test_information_input_ledger_uses_the_owned_episode_directory(
        monkeypatch, tmp_path, audit_enabled):
    audit_path = str(tmp_path / "adapter.jsonl") if audit_enabled else ""
    context, actions, nodes, _ = configured_launch(
        monkeypatch, execution_mode="adapter", mr3_audit_path=audit_path)
    active = released_nodes(context, actions, nodes)
    information = next(item for item in active if item["executable"] == "mr3_information")
    expected = str(tmp_path / "information_states.jsonl") if audit_enabled else ""
    assert information["parameters"][0]["state_audit_path"] == expected


@pytest.mark.parametrize("count", ["1", "2", "4"])
def test_adapter_rejects_every_compatible_non_three_robot_configuration(monkeypatch, count):
    with pytest.raises(ValueError, match="robot_count=3"):
        configured_launch(monkeypatch, execution_mode="adapter", robot_count=count)


@pytest.mark.parametrize("stepped", [False, True])
def test_state_peer_and_guard_takeover_share_the_explicit_stepped_contract(
        monkeypatch, tmp_path, stepped):
    context, actions, nodes, _ = configured_launch(
        monkeypatch, execution_mode="adapter", mr3_stepped=str(stepped).lower(),
        mr3_audit_path=str(tmp_path / "adapter.jsonl"))
    active = released_nodes(context, actions, nodes)
    for executable in ("mr3_information", "peer_obstacles", "motion_safety"):
        parameters = next(item["parameters"][0] for item in active
                          if item["executable"] == executable)
        assert parameters["stepped_mode"] is stepped
        assert parameters["episode_epoch"].perform(context) == "mr3-p1b"
        if executable == "peer_obstacles":
            assert parameters["phase_audit_path"] == (
                str(tmp_path / "peer_phase.jsonl") if stepped else "")


@pytest.mark.parametrize("enabled", ["true", "True", "1"])
def test_adapter_rejects_every_true_launch_condition_for_another_velocity_owner(
        monkeypatch, enabled):
    with pytest.raises(ValueError, match="enable_drive=false"):
        configured_launch(monkeypatch, execution_mode="adapter", enable_drive=enabled)


def test_unknown_execution_mode_fails_before_constructing_a_launch_graph(monkeypatch):
    with pytest.raises(ValueError, match="execution_mode"):
        configured_launch(monkeypatch, execution_mode="hidden_fallback")


@pytest.mark.parametrize("seed_rule",["exact-point-bridge-v1","exact-point-bridge-v2"])
def test_exact_seed_rule_is_explicit_only_on_the_stepped_three_robot_adapter(monkeypatch,seed_rule):
    context,actions,nodes,_=configured_launch(monkeypatch,execution_mode="adapter",mr3_stepped="true",
                                             mr3_seed_rule=seed_rule)
    adapter=next(item for item in released_nodes(context,actions,nodes)
                 if item["executable"]=="mr3_adapter")
    assert adapter["parameters"][0]["seed_rule"]==seed_rule


@pytest.mark.parametrize("overrides",[
    {"mr3_seed_rule":"unknown"},
    {"mr3_seed_rule":"exact-point-bridge-v1"},
    {"execution_mode":"adapter","mr3_seed_rule":"exact-point-bridge-v1"},
])
def test_invalid_or_nonstepped_seed_rule_rejects_before_launch(monkeypatch,overrides):
    with pytest.raises(ValueError,match="seed_rule|exact-point-bridge"):
        configured_launch(monkeypatch,**overrides)


def test_default_adapter_launch_keeps_the_legacy_parameter_payload(monkeypatch):
    context,actions,nodes,_=configured_launch(monkeypatch,execution_mode="adapter")
    adapter=next(item for item in released_nodes(context,actions,nodes)
                 if item["executable"]=="mr3_adapter")
    assert "seed_rule" not in adapter["parameters"][0]
    assert "start_graph_rule" not in adapter["parameters"][0]


def test_point_attachment_launch_binds_both_rules_and_keeps_anchor_out_of_navigation_goals(monkeypatch):
    context,actions,nodes,_=configured_launch(monkeypatch,execution_mode="adapter",mr3_stepped="true",
        mr3_seed_rule="exact-point-bridge-v2",mr3_start_graph_rule="point-attachment-3x3-v1")
    adapter=next(item for item in released_nodes(context,actions,nodes) if item["executable"]=="mr3_adapter")
    assert adapter["parameters"][0]["seed_rule"]=="exact-point-bridge-v2"
    assert adapter["parameters"][0]["start_graph_rule"]=="point-attachment-3x3-v1"


@pytest.mark.parametrize("seed",["legacy","exact-point-bridge-v1"])
def test_point_attachment_rejects_cross_seed_pair_before_launch(monkeypatch,seed):
    with pytest.raises(ValueError,match="start_graph_rule"):
        configured_launch(monkeypatch,execution_mode="adapter",mr3_stepped="true",
            mr3_seed_rule=seed,mr3_start_graph_rule="point-attachment-3x3-v1")


@pytest.mark.parametrize("mode", ["baseline", "adapter"])
def test_nav2_rewrite_changes_only_the_two_global_map_inputs(monkeypatch, mode):
    context, _, _, includes = configured_launch(monkeypatch, execution_mode=mode)
    bringups = [arguments for arguments in includes if "params_file" in arguments]
    assert len(bringups) == 3
    for arguments in bringups:
        robot = arguments["namespace"].lstrip("/")
        original_path = ROOT / f"src/multi_robot/params/nav2_params_{robot}_0.yaml"
        original = yaml.safe_load(original_path.read_text())
        expected = copy.deepcopy(original)
        parameters = arguments["params_file"]
        if mode == "adapter":
            output_path = Path(parameters.perform(context))
            try:
                actual = yaml.safe_load(output_path.read_text())
            finally:
                output_path.unlink()
            global_map = expected["global_costmap"]["global_costmap"]["ros__parameters"]
            global_map["map_topic"] = f"/{robot}/navigation_map"
            global_map["static_layer"]["map_topic"] = f"/{robot}/navigation_map"
        else:
            assert Path(parameters) == original_path
            actual = yaml.safe_load(Path(parameters).read_text())
        # The full-document comparison catches accidental local sensor, safety,
        # planner, recovery, footprint, or parameter changes alongside the map.
        assert actual == expected


@pytest.mark.parametrize("mode", ["baseline", "adapter"])
def test_peer_and_evaluator_use_the_matching_delivery_and_task_start_contract(
        monkeypatch, mode):
    _, _, nodes, _ = configured_launch(monkeypatch, execution_mode=mode)
    peer = next(arguments for _, arguments in nodes
                if arguments["executable"] == "peer_obstacles")
    evaluator = next(arguments for _, arguments in nodes
                     if arguments["executable"] == "task_evaluator")
    assert peer["parameters"][0]["task_release_start"] is (mode == "adapter")
    expected_peers = {
        (f"/tb{robot}/{topic}", f"/mr3/received/tb{robot}/{topic}")
        for robot in range(1, 4) for topic in ("odom", "tf")
    } if mode == "adapter" else set()
    assert set(peer["remappings"]) == expected_peers
    assert evaluator["remappings"] == (
        [("/merge_map", "/mr3/received/map")] if mode == "adapter" else [])
