"""Executed graph paths must come from the same original shared declaration."""
import copy
import gzip
import json
from pathlib import Path

import pytest
from check_p3c5_gate import declaration_audit
from run_p3b5_tasks import episode_command
from run_p3c5_audit import main


def original():
    p=Path(__file__).resolve().parents[1]/'src/multi_robot_exploration/test/fixtures/p2c_v67_graph_command.json.gz'
    with gzip.open(p,'rt') as stream:return json.load(stream)


def copied(tmp_path):
    d=original();row=copy.deepcopy(d['summary']);directory=tmp_path/Path(row['result_path']).parent.name;directory.mkdir()
    old_dir=Path(row['result_path']).parent
    for key in ('command','observer_command'):
        row[key]=[v.replace(str(old_dir),str(directory)) for v in row[key]]
    row['result_path']=str(directory/(directory.name+'.json'))
    manifest=copy.deepcopy(d['manifest'])
    for key in ('command','observer_command'):manifest[key]=copy.deepcopy(row[key])
    (directory/'manifest.json').write_text(json.dumps(manifest))
    Path(row['result_path']).write_text(json.dumps(row['result']))
    return row,row['config'],directory


def test_original_complete_task_is_bound_without_modifying_its_native_result(tmp_path):
    row,config,directory=copied(tmp_path);before=copy.deepcopy(row['result'])
    assert original()['original_strict']=='FAIL'
    assert declaration_audit(row,config,directory)['status']=='PASS'
    assert row['result']==before and row['result']['task_phase']=='COMPLETE'


@pytest.mark.parametrize('complete',[False,True])
def test_legacy_and_complete_graph_paths_are_generated_in_the_shared_builder(complete,tmp_path):
    d=original();config=copy.deepcopy(d['summary']['config']);config['complete_application_graph']=complete
    scenario=config['cases']['dev_forced2'];case=dict(id='dev_forced2',scenario='dev_forced2',mode='rally',profile='online')
    command=episode_command(case,scenario,scenario.get('profile',{}),scenario['mode'],tmp_path,config)
    assert Path(command[command.index('--bypass-audit-output')+1]).name==('initial_bypass_graph.json' if complete else 'graph.json')
    other=copy.deepcopy(config);other['complete_application_graph']=not complete
    comparison=episode_command(case,scenario,scenario.get('profile',{}),scenario['mode'],tmp_path,other)
    assert len(command)==len(comparison) and sum(a!=b for a,b in zip(command,comparison))==1


@pytest.mark.parametrize('change',['graph_path','horizon','hold','clearance','energy','robot_count','seed','world','protocol','native_cache'])
def test_fix_does_not_allow_a_different_predeclared_cell(tmp_path,change):
    row,config,directory=copied(tmp_path)
    flags={'graph_path':('--bypass-audit-output','graph.json'),'horizon':('--evaluation-duration','301'),
        'energy':('--battery-initial-energy','50'),'robot_count':('--robot-count','3'),
        'seed':('--gazebo-seed','202'),'world':('--world','p1c_rooms.world')}
    if change in flags:
        flag,value=flags[change];row['command'][row['command'].index(flag)+1]=value
    elif change=='hold':row['command']+=['--rally-hold','1']
    elif change=='clearance':row['command']+=['--rally-position-tolerance','.5']
    elif change=='protocol':row['command']+=['--gateway-admission-protocol']
    else:row['result']['elapsed_sim_time_sec']-=1.
    manifest=json.loads((directory/'manifest.json').read_text());manifest['command']=copy.deepcopy(row['command']);(directory/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(AssertionError):declaration_audit(row,config,directory)


def test_owner_and_shared_declaration_match_for_prospective_complete_capture(monkeypatch,capsys):
    manifest=Path(__file__).with_name('p2c_integration_manifest.json')
    monkeypatch.setattr('sys.argv',['run_p3c5_audit.py','--manifest',str(manifest),'--case','dev_forced2','--run-id','graph_command_component','--domain','218','--gazebo-port','20318','--validate-only'])
    assert main()==0;row=json.loads(capsys.readouterr().out);config=row['config'];scenario=config['cases'][row['case']]
    directory=Path(row['command'][row['command'].index('--evaluation-output-dir')+1]);case=dict(id=row['case'],scenario=row['case'],mode='rally',profile='online')
    expected=episode_command(case,scenario,scenario.get('profile',{}),scenario['mode'],directory,config)
    expected[expected.index('--shutdown-timeout')+1]=str(config['owner_shutdown_timeout_sec'])
    if scenario['admission_protocol']:expected.append('--gateway-admission-protocol')
    assert row['command']==expected
    from run_p2d_baseline import file_digest
    assert row['source_digests']['episode_command_builder']==file_digest(Path(__file__).with_name('run_p3b5_tasks.py'))
