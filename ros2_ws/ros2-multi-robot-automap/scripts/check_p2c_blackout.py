#!/usr/bin/env python3
"""Strict supplemental P2C local-return pair; no mission/TDI success claim."""
import argparse,hashlib,json,math,shlex,subprocess,traceback
from pathlib import Path

from check_p2c_gate import check_one
from check_p3b5_gate import physical_return_audit,staging_audit,staging_source_audit
from run_p2d_baseline import PROJECT_ROOT,file_digest


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def nav2_readiness_audit(records,staging,poses):
    """Check actual Nav2 bounds before each unchanged gateway staging leg."""
    latest={};proof=[]
    for event in records:
        assert event['event']=='nav2_staging_readiness' and event['robot'] in poses
        assert math.isfinite(event['observer_time'])
        latest.setdefault(event['robot'],[]).append(event)
    for event in staging:
        if event['event']!='staging_requested':continue
        matches=[r for r in latest.get(event['robot'],[]) if r['observer_time']<=event['observer_time']]
        assert matches,'missing Nav2 readiness before staging'
        row=matches[-1]
        assert row['ready'] is True and 0<=event['observer_time']-row['observer_time']<2.
        assert row['frame']=='map' and 0<=row['observer_time']-row['map_header_time']<=2.
        assert all(math.isfinite(v) for v in [row['map_header_time'],row['resolution'],*row['origin'],*row['orientation']])
        assert row['resolution']>0 and row['width']>0 and row['height']>0
        assert row['data_length']==row['width']*row['height']
        assert all(abs(v)<=1e-6 for v in row['orientation'][:3]) and abs(abs(row['orientation'][3])-1.)<=1e-6
        for x,y,_ in poses.values():
            column=math.floor((x-row['origin'][0])/row['resolution'])
            line=math.floor((y-row['origin'][1])/row['resolution'])
            assert 0<=column<row['width'] and 0<=line<row['height'],'Nav2 bounds exclude staging pose'
        proof.append(dict(robot=event['robot'],request_time=event['observer_time'],readiness=row))
    assert {row['robot'] for row in proof}==set(poses),'missing robot readiness proof'
    return proof


def probe_detail(path,config):
    path=path.resolve()
    row=json.loads(path.read_text());directory=path.parent;result=row['result']
    evidence=check_one(path,config)
    assert row['staging_returncode']==row['physics_returncode']==0
    assert not any(v for k,v in row.items() if k.endswith('_forced_shutdown'))
    assert all(r['battery_charge_count']>=1 for r in result['robots'].values())
    root=PROJECT_ROOT.parents[1]
    fixture=PROJECT_ROOT/'scripts'/config.get('staging_apparatus_script','stage_p3b5_return_probe.py')
    physics=PROJECT_ROOT/'scripts/observe_p3b5_return_physics.py'
    for source,expected in ((fixture,config['staging_apparatus_content_sha256']),
                            (physics,config['physical_observer_content_sha256'])):
        frozen=subprocess.check_output(['git','show',row['git_commit']+':'+str(source.relative_to(root))],cwd=root)
        assert hashlib.sha256(frozen).hexdigest()==expected and source.read_bytes()==frozen
    if fixture.name=='stage_p3b5_return_probe.py':
        source_proof=staging_source_audit(row,config['staging_apparatus_content_sha256'])
    else:
        assert fixture.name=='stage_p2c_return_probe.py'
        base=PROJECT_ROOT/'scripts/stage_p3b5_return_probe.py'
        frozen=subprocess.check_output(['git','show',row['git_commit']+':'+str(base.relative_to(root))],cwd=root)
        assert frozen==base.read_bytes() and sha(base)==config['staging_base_content_sha256']
        assert row['staging_source'].encode()==fixture.read_bytes()
        assert row['staging_source_sha256']==file_digest(fixture)
        command=shlex.split(row['staging_command'])
        assert Path(command[1]).resolve()==fixture.resolve()
        source_proof=dict(source_matches_predeclared_apparatus=True,
            source_content_sha256=sha(fixture),source_file_digest_sha256=file_digest(fixture),
            frozen_legacy_stimulus_base_sha256=sha(base),command_source_path=str(fixture))
    assert row['staging_content_sha256']==config['staging_apparatus_content_sha256']
    assert row['source_digests']['staging_apparatus']==file_digest(fixture)
    assert row['source_digests']['physics_observer']==file_digest(physics)
    staging_command=shlex.split(row['staging_command'])
    assert int(staging_command[staging_command.index('--owner-pid')+1])==row['owner_pid']
    assert Path(staging_command[staging_command.index('--output')+1]).resolve()==(directory/'staging.jsonl').resolve()
    config_path=Path(staging_command[staging_command.index('--config')+1]).resolve()
    assert json.loads(config_path.read_text())==config
    assert row['physics_command'][1:]==[str(physics),'--output',str(directory/'physics.jsonl'),
        '--robot-count',str(result['robot_count'])]
    assert row['environment']['ROS_DOMAIN_ID']!='222'
    assert config['predeclared_at_utc']<row['started_at_utc']
    epoch=next(json.loads(line)['event_time'] for line in (directory/'ledger.jsonl').open()
               if json.loads(line)['event']=='fault_epoch')
    staging=[json.loads(line) for line in (directory/'staging.jsonl').open()]
    staged=staging_audit(staging,epoch,config['return_staging'])
    assert set(staged)==set(result['robots'])
    readiness=None
    if fixture.name=='stage_p2c_return_probe.py':
        readiness_path=directory/'nav2_readiness.jsonl'
        readiness=nav2_readiness_audit([json.loads(line) for line in readiness_path.open()],
                                     staging,config['return_staging']['poses'])
        source_proof.update(nav2_readiness=readiness,nav2_readiness_sha256=sha(readiness_path))
    mode=config['cases'][row['case']]['mode'];motion=None
    if mode=='fault':
        window=config['physical_verification']['return_motion_window_sec']
        interval=config['cases'][row['case']]['profile']['gateway_blackout_intervals'][0]
        assert window==[interval[0]+2,interval[1]-2]
        homes={n:(r['battery_charge_x'],r['battery_charge_y']) for n,r in result['robots'].items()}
        motion=physical_return_audit([json.loads(line) for line in (directory/'physics.jsonl').open()],
                                   epoch,homes,window=window)
    evidence['physical_probe']=dict(staging_source=source_proof,prepared=staged,local_return_motion=motion,
        physics_sha256=sha(directory/'physics.jsonl'),staging_sha256=sha(directory/'staging.jsonl'),
        scope='Controlled supplemental safety exposure; excluded from mission/TDI.')
    return evidence


def check_pair(run_root,manifest_path=None,expected_commit=None,reference_source_digests=None):
    manifest_path=manifest_path or Path(__file__).with_name('p2c_blackout_manifest.json')
    config=json.loads(manifest_path.read_text());paths={}
    assert config['cases']['physical_ideal']['mode']=='ideal' and config['cases']['physical_fault']['mode']=='fault'
    for path in run_root.glob('*/summary.json'):
        case=json.loads(path.read_text())['case']
        assert case in config['cases'] and case not in paths,'extra/duplicate physical original'
        paths[case]=path
    assert set(paths)==set(config['cases'])=={'physical_ideal','physical_fault'},'missing physical original'
    rows=[json.loads(p.read_text()) for p in paths.values()]
    assert len({r['git_commit'] for r in rows})==1
    commit=rows[0]['git_commit'];root=PROJECT_ROOT.parents[1]
    if expected_commit is not None:assert commit==expected_commit,'physical/formal source freezes differ'
    frozen=json.loads(subprocess.check_output(['git','show',commit+':'+str(manifest_path.resolve().relative_to(root))],cwd=root))
    assert frozen==config
    original=PROJECT_ROOT/'scripts'/config['stimulus_manifest']
    old=json.loads(original.read_text());assert sha(original)==config['stimulus_manifest_content_sha256']
    prior=subprocess.check_output(['git','show',config['stimulus_frozen_commit']+':'+str(original.relative_to(root))],cwd=root)
    assert prior==original.read_bytes(),'original physical stimulus was modified'
    assert config['return_staging']==old['return_staging'] and config['physical_verification']==old['physical_verification']
    for case in config['cases'].values():
        assert all(case[k]==v for k,v in old['scenarios']['forced2'].items())
        assert case['profile']==old['profiles']['physical_outage']
    assert all(r['source_digests']==rows[0]['source_digests'] for r in rows)
    if reference_source_digests is not None:
        assert set(reference_source_digests)==set(rows[0]['source_digests'])
        assert all(v==rows[0]['source_digests'][k] for k,v in reference_source_digests.items() if k!='manifest')
    evidence=[probe_detail(paths[name],config) for name in sorted(paths)]
    return dict(status='PASS',scope='supplemental physical safety only',task_stack_frozen_commit=commit,
                cases=2,original_stimulus_and_thresholds_unchanged=True,evidence=evidence)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=Path(__file__).with_name('p2c_blackout_manifest.json'))
    p.add_argument('--expected-commit')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('do not overwrite an audit')
    try:result=check_pair(a.run_root,a.manifest,a.expected_commit)
    except Exception as error:result=dict(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence'},indent=2))
    return int(result['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
