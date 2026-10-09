"""Preserve controlled exposure; reject missing/forced/fabricated proof."""
import copy,hashlib,json,shlex,sys
from pathlib import Path

import pytest

import check_p2c_blackout as g
from run_p2d_baseline import PROJECT_ROOT,file_digest
from run_p3c5_audit import main as expand_original,return_probe_commands


def config():return json.loads((PROJECT_ROOT/'scripts/p2c_blackout_manifest.json').read_text())


def test_physical_declaration_preserves_all_existing_stimuli_and_safety_thresholds():
    m=config();p=PROJECT_ROOT/'scripts/p3b5_staged_return_probe_manifest.json';old=json.loads(p.read_text())
    assert m['stimulus_manifest_content_sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert m['return_staging']==old['return_staging'] and m['physical_verification']==old['physical_verification']
    assert m['duration_sec']==300 and m['physical_verification']['return_motion_window_sec']==[62,248]
    for case in m['cases'].values():
        assert all(case[k]==v for k,v in old['scenarios']['forced2'].items())
        assert case['profile']==old['profiles']['physical_outage']


@pytest.mark.parametrize('probe',[False,True])
def test_owner_validation_adds_only_opt_in_owned_staging_and_read_only_physics(monkeypatch,capsys,probe):
    manifest=PROJECT_ROOT/'scripts'/('p2c_blackout_manifest.json' if probe else 'p2c_integration_manifest.json')
    case='physical_fault' if probe else 'dev_forced2'
    monkeypatch.setattr(sys,'argv',['run_p2c_tasks.py','--case',case,'--run-id','component_only',
        '--domain','180','--gazebo-port','20400','--validate-only','--manifest',str(manifest)])
    assert expand_original(log_category='p2c')==0
    result=json.loads(capsys.readouterr().out);command=result['command']
    assert float(command[command.index('--evaluation-duration')+1])==300.
    assert float(command[command.index('--shutdown-timeout')+1])==120.
    if probe:
        assert '--enable-return-probe-pause' in command
        assert str(result['owner_pid']) in shlex.split(result['staging_command'])
        assert 'observe_p3b5_return_physics.py' in result['physics_command'][1]
        assert result['staging_content_sha256']==config()['staging_apparatus_content_sha256']
    else:
        assert '--enable-return-probe-pause' not in command and 'physics_command' not in result
        assert return_probe_commands(result['config'],result['config']['cases'][case],Path('/tmp'),123,manifest)=={}


def test_missing_physical_originals_cannot_pass_the_pair(tmp_path):
    with pytest.raises(AssertionError,match='missing physical original'):g.check_pair(tmp_path)


def probe_files(tmp_path):
    m=config();m['predeclared_at_utc']='2026-10-08T00:00:00+00:00'
    fixture=PROJECT_ROOT/'scripts/stage_p3b5_return_probe.py';physics=PROJECT_ROOT/'scripts/observe_p3b5_return_physics.py'
    # Legacy evidence remains auditable after the prospective apparatus changes.
    m['staging_apparatus_script']=fixture.name
    m['staging_apparatus_content_sha256']=hashlib.sha256(fixture.read_bytes()).hexdigest()
    cfg=tmp_path/'manifest_config.json';cfg.write_text(json.dumps(m))
    events=[];robots={}
    for name,pose in m['return_staging']['poses'].items():
        sign=-1 if name=='tb1' else 1
        robots[name]=dict(battery_charge_count=1,battery_charge_x=0.,battery_charge_y=sign*.45)
        events.extend([dict(event='staging_requested',robot=name,observer_time=10.,
            current_position=[0.,sign*.45],waypoint=[0.,sign*1.15],
            inputs={k:dict(source_time=10.,age_sec=0.,ttl_sec=t) for k,t in
                (('map_snapshot',5.),('pose_state',2.),('frame_state',2.),('battery_state',5.))}),
            dict(event='staged',robot=name,observer_time=30.,position=pose[:2])])
    events.extend([dict(event='both_charged',observer_time=110.),dict(event='coordinator_resumed',observer_time=111.)])
    (tmp_path/'staging.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    (tmp_path/'ledger.jsonl').write_text(json.dumps(dict(event='fault_epoch',event_time=0.))+'\n')
    motion=[dict(event='physics',observer_time=100.+k*.5,robots={name:dict(x=0.,
        y=(-1 if name=='tb1' else 1)*(2.45-k*.1),battery=dict(mode='RETURNING',return_count=1),
        nav2_status=[dict(status=2)]) for name in robots}) for k in range(8)]
    (tmp_path/'physics.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in motion))
    row=dict(case='physical_fault',git_commit=m['stimulus_frozen_commit'],owner_pid=1234,
        runner_returncode=0,observer_returncode=0,staging_returncode=0,physics_returncode=0,
        environment={'ROS_DOMAIN_ID':'180'},started_at_utc='2026-10-09T00:00:00+00:00',
        result=dict(robot_count=2,robots=robots),staging_source=fixture.read_text(),
        staging_source_sha256=file_digest(fixture),staging_content_sha256=m['staging_apparatus_content_sha256'],
        staging_command=shlex.join([sys.executable,str(fixture),'--owner-pid','1234','--config',str(cfg),
            '--output',str(tmp_path/'staging.jsonl')]),
        physics_command=[sys.executable,str(physics),'--output',str(tmp_path/'physics.jsonl'),'--robot-count','2'],
        source_digests={'staging_apparatus':file_digest(fixture),'physics_observer':file_digest(physics)})
    return m,row,motion


@pytest.mark.parametrize('corruption',[None,'staging_exit','physics_exit','forced','charge','owner',
    'source','physics_command','static','nav2_not_executing','outside_guard','unstaged'])
def test_physical_adapter_rejects_invalid_originals_and_native_motion(tmp_path,monkeypatch,corruption):
    m,row,motion=probe_files(tmp_path)
    monkeypatch.setattr(g,'check_one',lambda *args:{'component_scope':'adapter only; common task audit tested separately'})
    if corruption=='staging_exit':row['staging_returncode']=1
    if corruption=='physics_exit':row['physics_returncode']=-2
    if corruption=='forced':row['physics_forced_shutdown']=True
    if corruption=='charge':row['result']['robots']['tb1']['battery_charge_count']=0
    if corruption=='owner':row['owner_pid']=5678
    if corruption=='source':row['staging_source']+='\n# changed\n'
    if corruption=='physics_command':row['physics_command'][-1]='3'
    if corruption=='static':
        for e in motion:e['robots']['tb1']['y']=-2.45
    if corruption=='nav2_not_executing':
        for e in motion:e['robots']['tb1']['nav2_status']=[dict(status=4)]
    if corruption=='outside_guard':
        for e in motion:e['observer_time']-=50.
    if corruption=='unstaged':(tmp_path/'staging.jsonl').write_text('')
    (tmp_path/'physics.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in motion))
    path=tmp_path/'summary.json';path.write_text(json.dumps(row))
    if corruption is None:
        result=g.probe_detail(path,m)['physical_probe']
        assert set(result['local_return_motion'])=={'tb1','tb2'}
        assert result['local_return_motion']['tb1']['nav2_executing_motion_m']==pytest.approx(.7)
    else:
        with pytest.raises((AssertionError,KeyError)):g.probe_detail(path,m)
