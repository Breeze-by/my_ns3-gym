"""Only observe existing V22 runs and /proc; never launch native/formal or control a PID."""
import argparse
import fcntl
import re
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import time

ROOT=Path('/home/zhuyulab/ns3-workspace')
FREEZE=None
OBSERVER=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v13/independent/mr3_readonly_v13_drive_shim_process_monitor_v2.py'
SHIM_BINDING=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v13/independent/mr3_v13_shim_binding_v1.json'
OBSERVER_SHA=None
BINARY=Path('/tmp/mr3_p2a0_v24_binaryproof.json')
STAGES=('interface','terminal','reset','deadline')
BASE=ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0'
TEMP=Path('/tmp')
LOG=TEMP/'mr3_p2a0_v24_cross_stage_mapping_calls_v1.jsonl'
SUMMARY=TEMP/'mr3_p2a0_v24_cross_stage_mapping_summary_v1.json'
START=TEMP/'mr3_p2a0_v24_cross_stage_mapping_start_v1.json'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
proofs={stage:{}for stage in STAGES}
processed=set()
closed=set()
seen_running=set()
confirmation_attempted=set()


def load_checked_corrector(read):
    """Load the separately bound custody supplement; original monitor/math stays intact."""
    root = Path('/home/zhuyulab/ns3-workspace')
    asset = ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
             'report/assets/20261018_mr3_p2a0_v24_install/')
    plan = json.loads(read(root / (asset + 'predeclared_plan_v24.json')))
    pins = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
    custody_asset = asset
    relative = custody_asset + 'independent/mr3_v24_corrector_custody_v3.py'
    binding = root / (custody_asset + 'independent/mr3_v24_corrector_binding_v1.json')
    raw = read(root / relative)
    if pins.get(relative) != hashlib.sha256(raw).hexdigest():
        raise ValueError('corrector custody source/plan SHA differs')
    if pins.get(str(binding.relative_to(root))) != hashlib.sha256(read(binding)).hexdigest():
        raise ValueError('corrector custody binding/plan SHA differs')
    spec = importlib.util.spec_from_file_location('v22_corrector_custody', root / relative)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(root / relative), 'exec'), module.__dict__)
    return module, binding


def observe_corrector(monitor, output):
    bindings = {}
    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        identity = {'sha256': sha(raw), 'bytes': len(raw)}
        previous = bindings.get(str(path))
        if previous is not None and previous != identity:
            raise ValueError('corrector observation input changed across reads: ' + str(path))
        bindings.setdefault(str(path), identity)
        return raw
    module, binding = load_checked_corrector(read)
    proof = module.observe(monitor, binding, FREEZE, read)
    for path, identity in bindings.items():
        raw = Path(path).read_bytes()
        if {'sha256': sha(raw), 'bytes': len(raw)} != identity:
            raise ValueError('corrector observation input changed before write: ' + path)
    with output.open('x') as stream:
        json.dump(proof, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return {'output': str(output), 'output_sha256': sha(output.read_bytes()),
            'passed': proof.get('passed') is True}


def read_json(path):
    try:return json.loads(path.read_bytes())
    except(FileNotFoundError,json.JSONDecodeError):return None


def identity(pid):
    try:
        text=Path(f'/proc/{pid}/stat').read_text();fields=text[text.rfind(')')+2:].split()
        return{'pid':pid,'start_ticks':int(fields[19]),'parent':int(fields[1]),'state':fields[0]}
    except(FileNotFoundError,ProcessLookupError):return None


def harvest(stage):
    prefix=f'mr3_p2a0_v24_{stage}'
    for path in sorted(TEMP.glob(prefix+'_process_monitor_*.json')):
        if str(path)in processed:continue
        data=read_json(path)
        if data is None:continue
        assert data['freeze']==FREEZE, str(path)+' wrong freeze'
        processed.add(str(path))
        processes={row['identity']['pid']:row['identity']for row in data['owned_current_processes']}
        gazebo=[g for g in data['gazebo_mapped_libraries']if g['new_drive_mapped']and not g['old_system_drive_mapped']and g['identity_still_same_after_maps']and g['mappings']and all(v['matches_declared_binary']for v in g['mappings'])]
        for episode in data['episodes']:
            directory=Path(episode['directory'])
            meta=read_json(directory/'metadata.json');supervisor=read_json(directory/'supervisor_metadata.json')
            if not meta or not supervisor:continue
            assert meta['freeze']==FREEZE
            worker=supervisor['worker_identity'];ancestry=[]
            for g in gazebo:
                pid=g['identity']['pid'];visited=set()
                while pid in processes and pid not in visited:
                    visited.add(pid);current=processes[pid]
                    if(current['pid'],current['start_ticks'])==(worker['pid'],worker['start_ticks']):ancestry.append(g['identity'])
                    pid=current['parent']
            sources=all(all(episode['drivers'][robot].get(key)is True for key in('available','compiled_match','library_match','tagged_match'))for robot in('tb1','tb2','tb3'))
            evidence=all(episode['evidence'].get(name,{}).get('valid')is True for name in('drive_topology','model_tb1','model_tb2','model_tb3'))
            shim=[row for row in data.get('shim_mapping',{}).get('episodes',[])
                  if row.get('directory')==str(directory)and row.get('epoch')==meta['epoch']
                  and row.get('complete')is True and row.get('active_worker')is True
                  and(row.get('worker_identity',{}).get('pid'),row.get('worker_identity',{}).get('start_ticks'))
                  ==(worker['pid'],worker['start_ticks'])]
            if not ancestry or not sources or not evidence or data['errors']or not shim:continue
            key=(str(directory),meta['epoch'],worker['pid'],worker['start_ticks'])
            proof={'monitor':str(path),'monitor_sha256':sha(path.read_bytes()),'actual_gz_identities':ancestry,'worker_identity':worker,'metadata_sha256':sha((directory/'metadata.json').read_bytes()),'supervisor_metadata_sha256':sha((directory/'supervisor_metadata.json').read_bytes())}
            proofs[stage].setdefault(key,[]).append(proof)


def actual_workers(stage):
    result=[]
    run=BASE/f'mr3_p2a0_20261018_v24_{stage}'
    for directory in sorted(run.glob('worker*/episode*')):
        meta=read_json(directory/'metadata.json');supervisor=read_json(directory/'supervisor_metadata.json')
        if not meta or not supervisor:continue
        assert meta['freeze']==FREEZE
        worker=supervisor['worker_identity'];key=(str(directory),meta['epoch'],worker['pid'],worker['start_ticks'])
        result.append((key,worker))
    return result


def capture(stage,kind,stream):
    launch_path=TEMP/f'mr3_p2a0_v24_{stage}_launch.json'
    launch=read_json(launch_path);assert launch and launch['freeze']==FREEZE
    assert launch['status']=='running'or(kind=='closed_final'and launch['status']in('completed','failed'))
    assert sha(OBSERVER.read_bytes())==OBSERVER_SHA
    binary=read_json(BINARY);assert binary and binary['freeze']==FREEZE
    prefix=f'mr3_p2a0_v24_{stage}'
    index=1
    while True:
        output=TEMP/(prefix+f'_process_monitor_{index:03d}.json');console=output.with_suffix('.console.log')
        if not output.exists()and not console.exists():break
        index+=1
    command=['/usr/bin/python3',str(OBSERVER),str(BASE/f'mr3_p2a0_20261018_v24_{stage}'),'--launch',str(launch_path),'--binary-proof',str(BINARY),'--shim-binding',str(SHIM_BINDING),'--output',str(output)]
    started=time.monotonic_ns();record={'stage':stage,'capture_kind':kind,'argv':command,'console':str(console),'output':str(output),'started_wall_monotonic_ns':started}
    try:
        with console.open('x')as out:
            process=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1'),timeout=45)
        record['returncode']=process.returncode
    except Exception as error:record['observer_error']=repr(error)
    if output.exists():
        data=read_json(output);record['output_sha256']=sha(output.read_bytes());record['errors']=data.get('errors')if data else['incomplete observer output']
    if output.exists():
        corrector_output = TEMP / (prefix + f'_corrector_mapping_{index:03d}.json')
        try:
            record['corrector_observation'] = observe_corrector(output, corrector_output)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            record['corrector_observation_error'] = repr(error)
    record['finished_wall_monotonic_ns']=time.monotonic_ns()
    stream.write(json.dumps(record)+'\n');stream.flush();print(json.dumps(record),flush=True)
    harvest(stage)


def stage_summary(stage):
    rows=[]
    for key,worker in actual_workers(stage):
        observed=proofs[stage].get(key,[])
        rows.append({'directory':key[0],'epoch':key[1],'worker_identity':worker,'active_complete_proof_count':len(observed),'actual_active_mapping_observed':bool(observed),'two_snapshot_preference_met':len(observed)>=2,'proofs':observed})
    return{'schema':'mr3-v24-stage-mapping-observation-summary-v1','stage':stage,'freeze':FREEZE,'launch':read_json(TEMP/f'mr3_p2a0_v24_{stage}_launch.json'),'actual_workers':rows,'corrector_mapping_outputs':[str(path) for path in sorted(TEMP.glob(f'mr3_p2a0_v24_{stage}_corrector_mapping_*.json'))],'each_actual_worker_active_mapping_observed':bool(rows)and all(v['actual_active_mapping_observed']for v in rows),'two_snapshot_preference_met':bool(rows)and all(v['two_snapshot_preference_met']for v in rows),'scope':'Read-only active mapped driver/worker ancestry, source/SDF/topology and per-episode actual three-controller loaded Shim custody only. Two snapshots are a monitoring preference, not a new acceptance gate or independent experiments. Original formal closure requires an actual active proof per real worker; full/body/physics/control/task gates remain separate.'}


def main():
    global FREEZE,OBSERVER_SHA
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',required=True);a=parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}',a.freeze);FREEZE=a.freeze
    plan=read_json(Path(__file__).parent.parent/'predeclared_plan_v24.json')
    bindings={str(ROOT/row['path']):row['sha256']for row in plan['independent_source_bindings']}
    assert plan['readiness']['status']=='ready'and not plan['readiness']['pending_bindings']
    asset = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install/independent'
    for path in(Path(__file__).resolve(),OBSERVER.resolve(),SHIM_BINDING.resolve(),asset/'mr3_v24_corrector_custody_v3.py',asset/'mr3_v24_corrector_binding_v1.json'):
        assert sha(path.read_bytes())==bindings[str(path)]
    OBSERVER_SHA=bindings[str(OBSERVER.resolve())]
    assert not LOG.exists()and not START.exists()and not SUMMARY.exists()
    assert sha(OBSERVER.read_bytes())==OBSERVER_SHA
    start={'schema':'mr3-v24-cross-stage-mapping-start-v1','freeze':FREEZE,'argv':['/usr/bin/python3',str(Path(__file__)),'--freeze',FREEZE],'source_sha256':sha(Path(__file__).read_bytes()),'observer':str(OBSERVER),'observer_sha256':OBSERVER_SHA,'primary_cadence_seconds':20,'satisfied_cadence_seconds':20,'first_complete_readonly_confirmation_delay_seconds':1,'confirmation_scope':'Two real snapshots improve monitoring robustness only, never independent native experiments or new formal gates.','native_or_formal_started':0,'native_process_control':False,'capture_wall_monotonic_ns':time.monotonic_ns()}
    START.write_text(json.dumps(start,indent=2)+'\n')
    began=time.monotonic();stop_reason=None
    with(TEMP/'mr3_p2a0_v24_cross_stage_mapping.lock').open('a')as lock,LOG.open('x')as stream:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while time.monotonic()-began<30000:
            for stage in STAGES:
                if stage in closed:continue
                launch=read_json(TEMP/f'mr3_p2a0_v24_{stage}_launch.json')
                harvest(stage)
                if not launch:continue
                assert launch['freeze']==FREEZE
                state=launch['status']
                if state=='running':
                    seen_running.add(stage)
                    capture(stage,'active',stream)
                    first=[key for key in proofs[stage]if len(proofs[stage][key])==1 and key not in confirmation_attempted]
                    if first:
                        confirmation_attempted.update(first);time.sleep(1)
                        latest=read_json(TEMP/f'mr3_p2a0_v24_{stage}_launch.json')
                        if latest and latest['status']=='running':capture(stage,'active_confirmation',stream)
                elif state in('completed','failed'):
                    if stage in seen_running or proofs[stage]:capture(stage,'closed_final',stream)
                    harvest(stage);summary=stage_summary(stage)
                    path=TEMP/f'mr3_p2a0_v24_{stage}_mapping_summary_v1.json'
                    assert not path.exists();path.write_text(json.dumps(summary,indent=2)+'\n');closed.add(stage)
                    print(json.dumps({'stage_closed':stage,'summary':str(path),'actual_workers':len(summary['actual_workers']),'each_actual_worker_active_mapping_observed':summary['each_actual_worker_active_mapping_observed'],'two_snapshot_preference_met':summary['two_snapshot_preference_met']}),flush=True)
                    if launch.get('passed')is False:stop_reason=stage+' launch failed; original admission stops later native stages'
                audit=read_json(TEMP/f'mr3_p2a0_v24_{stage}_audit_execution_v1.json')
                if audit and audit['freeze']==FREEZE and audit.get('passed')is False:stop_reason=stage+' original mandatory audit failed; no later version stage admission'
            ledger=TEMP/'mr3_p2a0_v24_remaining_matrix_v1.jsonl'
            if ledger.exists():
                for line in ledger.read_bytes().splitlines(keepends=True):
                    if not line.endswith(b'\n'):break
                    row=json.loads(line)
                    assert row.get('freeze')==FREEZE
                    if row.get('event')=='version_failed_later_stages_skip':
                        stop_reason='actual matrix ledger declares version failure and later stages skip'
            if len(closed)==len(STAGES)or stop_reason:break
            time.sleep(20)
    result={'schema':'mr3-v24-cross-stage-mapping-complete-v1','freeze':FREEZE,'closed_stages':sorted(closed),'stop_reason':stop_reason or('all stages observed closed'if len(closed)==len(STAGES)else'bounded readonly watcher time expired'),'stage_summaries':{stage:stage_summary(stage)for stage in closed},'wall_seconds':time.monotonic()-began,'native_or_formal_started':0,'native_process_control':False}
    SUMMARY.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'watcher_finished':True,'closed_stages':sorted(closed),'stop_reason':result['stop_reason'],'summary':str(SUMMARY)}),flush=True)

if __name__=='__main__':main()
