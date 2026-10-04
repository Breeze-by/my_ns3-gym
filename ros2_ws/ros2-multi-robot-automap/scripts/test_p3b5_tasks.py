"""Focused regression checks for paired scientific accounting."""
import json

import pytest

from run_p3b5_tasks import CONFIG, episode_command, ledger_metrics, tdi


@pytest.mark.parametrize('base,count,expected',[(18,2,[18,19]),(229,2,[229,230])])
def test_declared_domains_match_native_observer_domains_without_modulo_aliases(base,count,expected):
    from run_p3b5_tasks import episode_domains
    assert episode_domains(base,count)==expected


@pytest.mark.parametrize('base,count',[(-1,2),(232,2)])
def test_domain_plans_reject_invalid_or_overflowed_ids(base,count):
    from run_p3b5_tasks import episode_domains
    with pytest.raises(ValueError,match='without wrapping'):episode_domains(base,count)


@pytest.mark.parametrize('base,valid',[(18,True),(232,False)])
def test_domain_validation_happens_before_any_episode_directory_or_spawn(tmp_path,monkeypatch,capsys,base,valid):
    import sys
    import run_p3b5_tasks as runner
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'cases':[{'id':'basic','scenario':'lab','mode':'coverage','profile':'zero'}],
        'scenarios':{'lab':{'world':'my_world.world','energy':40}},'profiles':{'zero':{}}}))
    run='domain_check_never_start'
    monkeypatch.setattr(sys,'argv',['run_p3b5_tasks','--config',str(config),'--run-id',run,
        '--validate-only','--ros-domain-base',str(base)])
    if valid:
        assert runner.main()==0
        assert json.loads(capsys.readouterr().out)['ros_domain_ids']==[18,19]
    else:
        with pytest.raises(SystemExit) as error:runner.main()
        assert error.value.code==2
        assert 'without wrapping' in capsys.readouterr().err
    assert not (runner.PROJECT_ROOT/'log/p3b5'/run).exists()


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


@pytest.mark.parametrize('seed',[303,809])
def test_manifest_records_actual_selected_seed_without_historical_or_unused_seeds(tmp_path,monkeypatch,seed):
    import sys
    import run_p3b5_tasks as runner
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'duration_sec':300,'coverage_threshold':.8,
        'cases':[{'id':'basic','scenario':'selected','mode':'coverage','profile':'zero'}],
        'scenarios':{'selected':{'world':'my_world.world','energy':45,'seed':seed},
                     'unused':{'world':'p3a5_holdout.world','energy':45,'seed':707}},
        'profiles':{'zero':{}}}))
    captured={}
    def capture_manifest(path,args):
        captured['seeds']=args.seeds
        raise RuntimeError('captured_before_any_spawn')
    monkeypatch.setattr(runner,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(runner,'build_manifest',capture_manifest)
    monkeypatch.setattr(sys,'argv',['run_p3b5_tasks','--config',str(config),'--run-id','metadata_only'])
    with pytest.raises(RuntimeError,match='captured_before_any_spawn'):runner.main()
    assert captured['seeds']==[seed]


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


def test_only_supplemental_return_fixture_enables_dispatch_pause(tmp_path):
    config = json.loads(CONFIG.read_text())
    for case in config["cases"]:
        for mode in ("ideal", "fault"):
            command = episode_command(case, config["scenarios"][case["scenario"]],
                config["profiles"][case["profile"]], mode, tmp_path / "normal", config)
            assert "--enable-return-probe-pause" not in command
    fixture = json.loads(CONFIG.with_name("p3b5_staged_return_probe_manifest.json").read_text())
    case = fixture["cases"][0]
    for mode in ("ideal", "fault"):
        command = episode_command(case, fixture["scenarios"][case["scenario"]],
            fixture["profiles"][case["profile"]], mode, tmp_path / "supplemental", fixture)
        assert command.count("--enable-return-probe-pause") == 1
