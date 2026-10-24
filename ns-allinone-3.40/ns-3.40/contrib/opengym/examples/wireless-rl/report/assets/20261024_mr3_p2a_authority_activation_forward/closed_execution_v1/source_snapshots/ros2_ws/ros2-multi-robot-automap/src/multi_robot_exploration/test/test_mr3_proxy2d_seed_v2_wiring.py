"""Mock CLI/constructor forwarding only; no World, scene, SDK or child process."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from multi_robot_exploration.mr3_observation import SEED_RULES


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/mr3_proxy2d_worker.py"


def worker_module():
    spec = importlib.util.spec_from_file_location("proxy_seed_v2_worker_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("rule", SEED_RULES)
def test_worker_cli_passes_selected_rule_and_leaves_legacy_kwargs_unchanged(monkeypatch, tmp_path, rule):
    module = worker_module()
    peer = SimpleNamespace(receive=Mock(side_effect=[{"operation": "reset"}, {"operation": "close"}]), send=Mock())
    monkeypatch.setattr(module.ipc, "JsonLinePeer", Mock(return_value=peer))
    monkeypatch.setattr(module, "sys", SimpleNamespace(
        stdin=SimpleNamespace(fileno=lambda: 0), stdout=SimpleNamespace(fileno=lambda: 1)))
    args = [str(SCRIPT), "--role", "worker", "--directory", str(tmp_path),
            "--epoch", "mock-epoch", "--scene", "open", "--seed", "101"]
    if rule != "legacy":
        args += ["--seed-rule", rule]
    monkeypatch.setattr(sys, "argv", args)
    worker = SimpleNamespace(reset=Mock(return_value={"fixture": True}), close=Mock())
    constructor = Mock(return_value=worker)
    monkeypatch.setattr(module, "ProxyWorker", constructor)
    assert module.main() == 0
    expected = {"mapper": "endpoint", "mapper_library": None}
    if rule != "legacy":
        expected["seed_rule"] = rule
    constructor.assert_called_once_with(tmp_path, "mock-epoch", "open", 101, **expected)
    worker.close.assert_called_once_with()


@pytest.mark.parametrize("rule", SEED_RULES)
def test_worker_constructor_gives_same_selected_rule_to_information_and_navigation(monkeypatch, tmp_path, rule):
    module = worker_module()
    world = SimpleNamespace(metadata={})
    world_factory = Mock(return_value=world)
    information, navigation = Mock(), Mock()
    definitions = {
        "mr3_proxy2d_world": {"ProxyWorld": world_factory},
        "mr3_proxy2d_information": {"ProxyInformation": information},
        "mr3_proxy2d_navigation": {"ProxyNavigator": navigation},
        "mr3_protocol": {"GoalDispatcher": Mock(return_value=SimpleNamespace(robots=("tb1", "tb2", "tb3")))},
        "mr3_transport": {"IdealTransport": Mock(), "ReceivedStore": Mock()},
        "mr3_activity": {"ReceivedActivity": Mock()},
    }
    for suffix, fields in definitions.items():
        monkeypatch.setitem(sys.modules, "multi_robot_exploration." + suffix, SimpleNamespace(**fields))
    monkeypatch.setattr(module.gzip, "open", Mock(return_value=Mock()))
    spawn = Mock(side_effect=RuntimeError("fixture stops before evaluator launch"))
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    value = SimpleNamespace()
    with pytest.raises(RuntimeError, match="fixture stops before evaluator launch"):
        module.ProxyWorker.__init__(value, tmp_path, "mock-epoch", "open", 101, seed_rule=rule)
    value.evaluator_log.close()
    expected = {} if rule == "legacy" else {"seed_rule": rule}
    information.assert_called_once_with("mock-epoch", **expected)
    navigation.assert_called_once_with(**expected)
    if rule == "legacy":
        assert "seed_rule" not in world.metadata
    else:
        assert world.metadata["seed_rule"] == rule
    world_factory.assert_called_once_with("open", 101, mapper="endpoint", mapper_library=None, epoch="mock-epoch")


@pytest.mark.parametrize("rule", [None, True, "exact-point-bridge-v3"])
def test_worker_constructor_rejects_unknown_rule_before_any_world_constructor(monkeypatch, tmp_path, rule):
    module = worker_module()
    world_factory = Mock(side_effect=AssertionError("World must never be called"))
    monkeypatch.setitem(sys.modules, "multi_robot_exploration.mr3_proxy2d_world",
                        SimpleNamespace(ProxyWorld=world_factory))
    with pytest.raises(ValueError, match="seed rule"):
        module.ProxyWorker.__init__(SimpleNamespace(), tmp_path, "mock-epoch", "open", 101, seed_rule=rule)
    world_factory.assert_not_called()
