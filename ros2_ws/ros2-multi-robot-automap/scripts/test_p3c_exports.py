import json
from pathlib import Path

import pytest

from export_gateway_metrics import compare, verify_live
from multi_robot_exploration.gateway_metrics import validate_pair_configuration


@pytest.mark.parametrize("row_key", ["directions", "window", "cumulative"])
def test_pair_validation_reads_protocol_from_real_export_and_live_row_shapes(row_key):
    context = {"gazebo_seed": 101, "world": "p1c_rooms.world", "mission_mode": "rally", "robot_count": 3}
    legacy = {"context": context}
    direct = {"context": context, row_key: [{"configuration": {"admission_protocol": False}}]}
    admitted = {"context": context, row_key: [{"configuration": {"admission_protocol": True}}]}
    validate_pair_configuration(direct, legacy)
    validate_pair_configuration(admitted, admitted)
    with pytest.raises(ValueError, match="admission_protocol differs"):
        validate_pair_configuration(admitted, direct)
    with pytest.raises(ValueError, match="admission_protocol differs"):
        validate_pair_configuration(legacy, admitted)


@pytest.mark.parametrize("invalid", [None, 0, 1, "true", []])
def test_pair_validation_rejects_invalid_protocol_declarations(invalid):
    context = {"gazebo_seed": 101, "world": "p1c_rooms.world", "mission_mode": "rally", "robot_count": 3}
    current = {"context": context, "directions": [{"configuration": {"admission_protocol": invalid}}]}
    with pytest.raises(ValueError, match="admission_protocol invalid"):
        validate_pair_configuration(current, {"context": context})


def test_pair_validation_rejects_conflicting_protocol_metadata():
    context = {"gazebo_seed": 101, "world": "p1c_rooms.world", "mission_mode": "rally", "robot_count": 3,
               "configuration": {"admission_protocol": True}}
    current = {"context": context, "directions": [{"configuration": {"admission_protocol": False}}]}
    with pytest.raises(ValueError, match="admission_protocol invalid or conflicting"):
        validate_pair_configuration(current, current)


def test_pair_validation_uses_declared_target_without_fabricating_undetected_truth(tmp_path):
    context = {"gazebo_seed": 303, "world": "my_world.world", "mission_mode": "rally", "robot_count": 2,
               "configuration": {"settings": {"scenario": {"target_x": -4, "target_y": 4},
                                                "protocol": {"target_max_distance_m": 3, "target_field_of_view_deg": 90,
                                                             "target_confirmation_frames": 3, "rally_position_tolerance_m": .35,
                                                             "rally_linear_tolerance_mps": .05, "rally_angular_tolerance_radps": .1,
                                                             "rally_hold_sec": 5}}}}
    ideal = {"mission_mode": "rally", "success": True, "task_phase": "COMPLETE", "robot_count": 2,
             "target_x": -4, "target_y": 4, "completion_time_sec": 100}
    fault = {"mission_mode": "rally", "success": False, "task_phase": "EXPLORE", "robot_count": 2,
             "target_x": None, "target_y": None, "completion_time_sec": None}
    (tmp_path / "windows.jsonl").write_text("")
    reference = {"context": context, "task_result": ideal, "export_directory": str(tmp_path)}
    current = {"context": context, "task_result": fault}
    result = compare(current, reference, tmp_path)
    assert result["tdi"] == 1 and result["rmst_300_delta_sec"] == 200
    assert result["fault_task"]["target_x"] is None
    current["context"] = {**context, "configuration": {"settings": {"scenario": {"target_x": 5, "target_y": 4}}}}
    with pytest.raises(ValueError, match="configured target_x"):
        compare(current, reference, tmp_path)


def test_empty_live_data_cannot_pass_same_source_verification(tmp_path):
    (tmp_path / "inputs.jsonl").write_text("")
    (tmp_path / "live.jsonl").write_text("")
    with pytest.raises(AssertionError, match="no live samples"):
        verify_live(tmp_path)


def test_console_keeps_new_service_revision_when_an_old_topic_update_arrives():
    from types import SimpleNamespace
    from std_msgs.msg import String
    from multi_robot_exploration.gateway_panel import FaultControlNode
    node = SimpleNamespace(configuration={"revision": 4, "ledger_path": "run-a", "requested": {"uplink_loss_rate": 0}})
    FaultControlNode.receive(node, String(data=json.dumps({"revision": 3, "ledger_path": "run-a", "requested": {"uplink_loss_rate": 1}})))
    assert node.configuration["revision"] == 4 and node.configuration["requested"]["uplink_loss_rate"] == 0
    node.receive = lambda message: FaultControlNode.receive(node, message)
    future = SimpleNamespace(result=lambda: SimpleNamespace(result=SimpleNamespace(successful=True, reason=json.dumps(
        {"revision": 3, "effective_sim_time": 10, "ledger_path": "run-a", "requested": {"uplink_loss_rate": 1}}))))
    FaultControlNode.applied(node, future)
    assert node.configuration["revision"] == 4 and node.pending is None
    FaultControlNode.receive(node, String(data=json.dumps({"revision": 0, "ledger_path": "run-b"})))
    assert node.configuration["ledger_path"] == "run-b"
