"""Focused regression checks for paired scientific accounting."""
import json

import pytest

from run_p3b5_tasks import ledger_metrics, tdi


def test_holdout_commands_use_declared_independent_fault_seed(tmp_path):
    import argparse
    from pathlib import Path
    from run_p3b5_tasks import episode_command
    config=json.loads(Path(__file__).with_name('p3b5_fault_manifest.json').read_text())
    assert config['holdout_fault_seed']!=config['fault_seed']
    parser=argparse.ArgumentParser()
    parser.add_argument('--gateway-seed',type=int)
    for case in config['cases']:
        for mode in ('ideal','fault'):
            command=episode_command(case,config['scenarios'][case['scenario']],
                config['profiles'][case['profile']],mode,tmp_path/'episode',config)
            arguments,_=parser.parse_known_args(command[2:])
            assert arguments.gateway_seed==(config['holdout_fault_seed'] if case['scenario']=='holdout3' else config['fault_seed'])


def test_tdi_excludes_process_modes_and_failed_ideal():
    ideal = {"success": True, "task_phase": "COMPLETE", "mission_mode": "rally", "robot_count": 3}
    assert tdi(ideal, {"success": True, "task_phase": "COMPLETE"}) == 0
    assert tdi(ideal, {"partial_completion": True, "required_robot_count": 2}) == pytest.approx(1 / 3)
    assert tdi(ideal, {"success": False}) == 1
    assert tdi({**ideal, "success": False}, {}) is None
    assert tdi({**ideal, "mission_mode": "coverage"}, {}) is None


def test_ledger_distinguishes_receipt_attempts_and_no_information(tmp_path):
    path = tmp_path / "ledger.jsonl"
    base = {"direction": "uplink", "message_type": "pose_state", "sender": "tb1", "recipient": "headquarters"}
    events = [
        {**base, "event": "enqueue", "time": 0., "message_id": "a"},
        {**base, "event": "accepted", "time": 1., "source_time": 0., "message_id": "a"},
        {**base, "event": "delivered", "time": 1.1, "message_id": "a", "duplicate": True},
        {**base, "event": "enqueue", "time": 2., "message_id": "b"},
        {**base, "event": "drop", "time": 3., "message_id": "b", "reason": "loss"},
        {"event": "coordinator_wait", "event_time": 2.},
        {"event": "coordinator_recovered", "event_time": 4.},
        {**base, "sender": "tb2", "event": "enqueue", "time": 1., "message_id": "c"},
    ]
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    metrics = ledger_metrics(path, 0., 4.)
    first, unavailable = metrics["streams"]
    assert first["application_pdr"] == .5
    assert first["unavailable_sec"] == 1.
    assert first["mean_aoi_observed_sec"] == pytest.approx(2.5)
    assert unavailable["mean_aoi_observed_sec"] is None
    assert unavailable["unavailable_sec"] == 4.
    assert metrics["stale_wait_sec"] == 2.
