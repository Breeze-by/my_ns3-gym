"""P1C terminal-failure injection must be explicitly enabled, never a default."""

import pytest

from test_launch_and_smoke import ROOT, mapping_actions


def test_terminal_probe_launch_defaults_off_and_requires_rewards(monkeypatch, tmp_path):
    launch, context, _ = mapping_actions(monkeypatch, tmp_path, stepped=True)
    assert context.launch_configurations["training_terminal_probe"] == "false"
    context.launch_configurations["training_terminal_probe"] = "true"
    with pytest.raises(ValueError, match="requires isolated rewards and stepped mode"):
        launch.launch_setup(context)


def test_terminal_probe_launch_passes_explicit_flag_to_contract_evaluator(monkeypatch, tmp_path):
    launch, context, _ = mapping_actions(monkeypatch, tmp_path, stepped=True)
    context.launch_configurations.update({
        "training_terminal_probe": "true", "training_reward_enabled": "true",
        "enable_task_evaluator": "true",
        "evaluation_contract_path": str(ROOT / "src/multi_robot/config/mr3_p1a/open.json"),
    })
    original = launch.Node
    captured = []

    def capture(**arguments):
        captured.append(arguments)
        return original(**arguments)

    monkeypatch.setattr(launch, "Node", capture)
    launch.launch_setup(context)
    evaluator = next(node for node in captured if node["executable"] == "task_evaluator")
    assert evaluator["parameters"][0]["training_terminal_probe"] is True
    assert evaluator["parameters"][0]["training_reward_enabled"] is True
