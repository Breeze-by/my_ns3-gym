"""Check drive implementation/audit wiring without loading Gazebo or ROS nodes."""

from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from launch.actions import RegisterEventHandler
from launch.event_handlers import OnShutdown
from launch.events import Shutdown
import pytest

from test_mr3_adapter_launch import ROOT, configured_launch


GIT_ROOT = ROOT.parents[1]
MODEL = ROOT / "src/multi_robot/models/turtlebot3_waffle/model.sdf"
ORIGINAL_FREEZE = "57b7c7f372aef4d84acd25fcd97a9944fa1fe9bb"


def original_model():
    return subprocess.check_output([
        "git", "show", f"{ORIGINAL_FREEZE}:{MODEL.relative_to(GIT_ROOT).as_posix()}"],
        cwd=GIT_ROOT)


def original_physical_bytes(rendered):
    restored = rendered.replace("libmr3_gazebo_diff_drive.so", "libgazebo_ros_diff_drive.so")
    for tag in ("mr3_audit_path", "mr3_epoch", "mr3_tagged_commands", "mr3_odometry_period_ns"):
        restored, count = re.subn(
            rf"      <{tag}(?:/>|>.*?</{tag}>)\n", "", restored, flags=re.DOTALL)
        assert count == 1
    return restored.encode()


def spawned_models(nodes):
    models = {}
    for _, node in nodes:
        if node["executable"] != "spawn_entity.py":
            continue
        arguments = node["arguments"]
        models[arguments[arguments.index("-entity") + 1]] = Path(
            arguments[arguments.index("-file") + 1])
    return models


def test_physical_model_preserved_with_explicit_empty_sensor_protocol_tags():
    current = MODEL.read_text()
    assert original_physical_bytes(current) == original_model()
    plugin = ET.fromstring(current).find(".//plugin[@name='turtlebot3_diff_drive']")
    assert plugin.attrib["filename"] == "libmr3_gazebo_diff_drive.so"
    assert plugin.findtext("mr3_audit_path") == ""
    assert plugin.findtext("mr3_epoch") == ""
    assert plugin.findtext("mr3_tagged_commands") == ""
    assert plugin.findtext("mr3_odometry_period_ns") == ""
    assert {tag: plugin.findtext(tag) for tag in (
        "update_rate", "wheel_separation", "wheel_diameter", "max_wheel_acceleration",
        "max_wheel_torque", "odometry_source")} == {
            "update_rate": "30", "wheel_separation": "0.287", "wheel_diameter": "0.066",
            "max_wheel_acceleration": "1.0", "max_wheel_torque": "20", "odometry_source": "1"}


def test_actual_spawn_paths_preserve_three_effective_models_and_adapter_epoch(
        monkeypatch, tmp_path):
    evidence = tmp_path / "evidence&received"
    evidence.mkdir()
    context, actions, nodes, _ = configured_launch(
        monkeypatch, execution_mode="adapter", mr3_audit_path=str(evidence / "adapter.jsonl"),
        mr3_episode_epoch="same-epoch<&received>")
    models = spawned_models(nodes)
    assert set(models) == {"tb1", "tb2", "tb3"}
    adapter = next(node for _, node in nodes if node["executable"] == "mr3_adapter")
    epoch = adapter["parameters"][0]["episode_epoch"].perform(context)
    for name, path in models.items():
        assert path == evidence / f"drive_model_{name}.sdf"
        rendered = path.read_text()
        assert original_physical_bytes(rendered) == original_model()
        plugin = ET.fromstring(rendered).find(".//plugin[@name='turtlebot3_diff_drive']")
        assert plugin.findtext("mr3_audit_path") == str(evidence / f"drive_{name}.jsonl")
        assert plugin.findtext("mr3_epoch") == epoch
        assert plugin.findtext("mr3_tagged_commands") == "true"
        assert plugin.findtext("mr3_odometry_period_ns") == "20000000"
    assert not list(evidence.glob("*tb4*"))
    assert len(list(evidence.iterdir())) == 3
    assert not any(isinstance(action, RegisterEventHandler)
                   and isinstance(action.event_handler, OnShutdown) for action in actions)


def test_enabled_drive_model_evidence_never_overwrites_prior_file(monkeypatch, tmp_path):
    retained = tmp_path / "drive_model_tb2.sdf"
    retained.write_bytes(b"retained-original-attempt")
    with pytest.raises(FileExistsError):
        configured_launch(monkeypatch, execution_mode="adapter",
                          mr3_audit_path=str(tmp_path / "adapter.jsonl"),
                          mr3_episode_epoch="same-epoch")
    assert retained.read_bytes() == b"retained-original-attempt"
    assert not (tmp_path / "drive_model_tb3.sdf").exists()


def test_empty_audit_baseline_uses_owned_temp_files_and_shutdown_cleanup(monkeypatch):
    context, actions, nodes, _ = configured_launch(
        monkeypatch, execution_mode="baseline", mr3_audit_path="", mr3_episode_epoch="")
    models = spawned_models(nodes)
    assert len(set(models.values())) == 3
    for path in models.values():
        rendered = path.read_text()
        assert original_physical_bytes(rendered) == original_model()
        plugin = ET.fromstring(rendered).find(".//plugin[@name='turtlebot3_diff_drive']")
        assert plugin.findtext("mr3_audit_path") == ""
        assert plugin.findtext("mr3_epoch") == ""
        assert plugin.findtext("mr3_tagged_commands") == "false"
        assert plugin.findtext("mr3_odometry_period_ns") == ""
    handlers = [action.event_handler for action in actions
                if isinstance(action, RegisterEventHandler)
                and isinstance(action.event_handler, OnShutdown)]
    assert len(handlers) == 3
    for handler in handlers:
        handler.handle(Shutdown(reason="headless test cleanup"), context)
    assert not any(path.exists() for path in models.values())
