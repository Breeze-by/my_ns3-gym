"""Keep the engineering stimulus opt-in and the observer free of setters."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from test_mr3_adapter_launch import MAPPING_LAUNCH, configured_launch


def module():
    spec = importlib.util.spec_from_file_location("plant_launch_test", MAPPING_LAUNCH)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def diagnostic(tmp_path, *, observer_only=True):
    run = tmp_path / "run"
    episode = run / "worker0/episode001_open_101"
    episode.mkdir(parents=True)
    prefix = tmp_path / "install"
    (prefix / "lib").mkdir(parents=True)
    config = {
        "schema": "mr3-physics-diagnostic-config-v2" if observer_only else
                  "mr3-physics-diagnostic-config-v1",
        "mode": "observer_only" if observer_only else "iters150",
        "run_directory": str(run), "episode_relative_directory": "worker0/episode001_open_101",
        "scene": "open", "seed": 101, "capture_start_ns": 0,
        "capture_end_ns": 300_000_000_000,
    }
    for key, filename in (("observer_library", "libmr3_stop_response_observer.so"),
                          ("profile_library", "libmr3_physics_diagnostic_profile.so")):
        path = prefix / "lib" / filename
        path.write_bytes(filename.encode())
        if observer_only and key == "profile_library":
            continue
        config[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "source_sha256": "1" * 64}
    world = tmp_path / "p1c_open.world"
    world.write_text("<sdf/>")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    kwargs = dict(adapter_mode=True, stepped_mode=True, robot_count=3, epoch="test-epoch",
                  audit_path=str(episode / "adapter.jsonl"), world=str(world), seed="101",
                  package_prefix=str(prefix))
    return config, path, kwargs


def test_observer_only_has_no_profile_library_or_setter_receipt(tmp_path):
    config, path, kwargs = diagnostic(tmp_path)
    result = module().prepare_physics_diagnostic(str(path), **kwargs)
    binding = result["binding"]
    assert binding["schema"] == "mr3-physics-diagnostic-binding-v2"
    assert binding["physics_intervention"] == "none_observer_only"
    assert "profile_library" not in binding and "profile_output_path" not in binding
    assert set(binding["observer_outputs"]) == {"tb1", "tb2", "tb3"}
    assert not list(Path(binding["episode_directory"]).glob("physics_profile*"))


def test_observer_only_rejects_even_correctly_hashed_profile_injection(tmp_path):
    config, path, kwargs = diagnostic(tmp_path)
    config["profile_library"] = dict(config["observer_library"])
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="schema/fields"):
        module().prepare_physics_diagnostic(str(path), **kwargs)


def test_observer_only_verifies_actual_library_bytes(tmp_path):
    config, path, kwargs = diagnostic(tmp_path)
    Path(config["observer_library"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA mismatch"):
        module().prepare_physics_diagnostic(str(path), **kwargs)


def test_legacy_profile_binding_retains_original_schema_and_profile(tmp_path):
    _, path, kwargs = diagnostic(tmp_path, observer_only=False)
    result = module().prepare_physics_diagnostic(str(path), **kwargs)
    assert result["binding"]["schema"] == "mr3-physics-diagnostic-binding-v1"
    assert "profile_library" in result["binding"]
    assert "profile_output_path" in result["binding"]


@pytest.mark.parametrize("arm", ["continuous", "pulse", "hidden"])
def test_stimulus_rejects_ordinary_launch(monkeypatch, arm):
    with pytest.raises(ValueError, match="plant_stimulus|plant stimulus"):
        configured_launch(monkeypatch, mr3_plant_stimulus_arm=arm)


def test_ordinary_adapter_keeps_diagnostic_disabled(monkeypatch):
    _, _, nodes, _ = configured_launch(monkeypatch, execution_mode="adapter")
    guard = next(value for _, value in nodes if value["executable"] == "motion_safety")
    assert guard["parameters"][0]["mr3_diagnostic_enabled"] is False


def test_stimulus_only_rewrites_tb3_smoother_and_keeps_peer_map_rewrites(monkeypatch, tmp_path):
    context, _, nodes, includes = configured_launch(
        monkeypatch, execution_mode="adapter", mr3_stepped="true",
        training_reward_enabled="true", evaluation_contract_path="test-contract",
        enable_task_evaluator="true", world="p1c_open.world",
        mr3_audit_path=str(tmp_path / "adapter.jsonl"), mr3_episode_epoch="plant-epoch",
        mr3_plant_stimulus_arm="pulse")
    guard = next(value for _, value in nodes if value["executable"] == "motion_safety")
    assert guard["parameters"][0]["mr3_diagnostic_enabled"] is True
    bringups = [value for value in includes if "params_file" in value]
    assert len(bringups) == 3
    for value in bringups:
        name = value["namespace"].lstrip("/")
        rendered = Path(value["params_file"].perform(context))
        params = yaml.safe_load(rendered.read_text())
        smoother = params["velocity_smoother"]["ros__parameters"]
        assert smoother.get("mr3_diagnostic_enabled", False) is (name == "tb3")
        if name == "tb3":
            assert smoother["mr3_diagnostic_epoch"] == "plant-epoch"
            assert smoother["mr3_diagnostic_arm"] == "pulse"
    spawns = [value for _, value in nodes if value["executable"] == "spawn_entity.py"]
    positions = {}
    for value in spawns:
        args = value["arguments"]
        positions[args[args.index("-entity") + 1]] = (
            args[args.index("-x") + 1], args[args.index("-y") + 1])
    assert positions == {"tb1": ("-1.6", "0.0"), "tb2": ("0.0", "0.0"),
                         "tb3": ("1.6", "0.0")}
