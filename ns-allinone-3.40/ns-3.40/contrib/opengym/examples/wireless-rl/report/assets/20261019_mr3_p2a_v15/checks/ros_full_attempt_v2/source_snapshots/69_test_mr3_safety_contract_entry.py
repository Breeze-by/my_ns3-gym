"""Explicit reach-profile launch admission, without starting ROS processes."""
import pytest

from test_mr3_adapter_launch import configured_launch, released_nodes


@pytest.mark.parametrize("contract", ["legacy", "mr3-reach-v1"])
def test_explicit_profile_reaches_all_three_real_safety_nodes(monkeypatch, tmp_path, contract):
    context, actions, nodes, _ = configured_launch(
        monkeypatch, execution_mode="adapter", mr3_stepped="true",
        mr3_safety_contract=contract, mr3_audit_path=str(tmp_path/"adapter.jsonl"))
    active = released_nodes(context, actions, nodes)
    for executable in ("mr3_information", "peer_obstacles", "motion_safety"):
        parameters = next(item["parameters"][0] for item in active
                          if item["executable"] == executable)
        assert parameters["safety_contract"] == contract
        assert parameters["stepped_mode"] is True


def test_omitted_profile_keeps_legacy_explicitly(monkeypatch):
    context, actions, nodes, _ = configured_launch(monkeypatch, execution_mode="adapter")
    active = released_nodes(context, actions, nodes)
    assert context.launch_configurations["mr3_safety_contract"] == "legacy"
    for executable in ("mr3_information", "peer_obstacles", "motion_safety"):
        parameters = next(item["parameters"][0] for item in active
                          if item["executable"] == executable)
        assert parameters["safety_contract"] == "legacy"


@pytest.mark.parametrize("overrides", [
    {"execution_mode": "baseline", "mr3_stepped": "true"},
    {"execution_mode": "adapter", "mr3_stepped": "false"},
    {"execution_mode": "adapter", "mr3_stepped": "true", "robot_count": "2"},
    {"execution_mode": "adapter", "mr3_stepped": "true", "robot_count": "4"},
])
def test_reach_profile_rejects_every_other_execution_topology(monkeypatch, overrides):
    with pytest.raises(ValueError, match="mr3-reach-v1 requires"):
        configured_launch(monkeypatch, mr3_safety_contract="mr3-reach-v1", **overrides)


@pytest.mark.parametrize("contract", ["", "reach", "MR3-REACH-V1", "legacy ", "true"])
def test_unknown_contract_is_not_silently_downgraded(monkeypatch, contract):
    with pytest.raises(ValueError, match="mr3_safety_contract"):
        configured_launch(monkeypatch, mr3_safety_contract=contract)
