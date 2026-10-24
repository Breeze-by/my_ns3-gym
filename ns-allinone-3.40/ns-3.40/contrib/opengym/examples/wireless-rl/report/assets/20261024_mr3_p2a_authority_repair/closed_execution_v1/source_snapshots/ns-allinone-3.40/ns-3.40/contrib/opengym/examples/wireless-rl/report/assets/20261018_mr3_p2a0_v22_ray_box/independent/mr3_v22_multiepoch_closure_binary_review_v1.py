"""Read-only multi-epoch native closure and actual mapped-driver provenance; no controls."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET


def load_checked_shim(read):
    """Reuse immutable A13 reader bytes and its original MONITOR/BINDING rules."""
    root = Path('/home/zhuyulab/ns3-workspace')
    relative = ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
                'report/assets/20261017_mr3_p2a0_v13/independent/'
                'mr3_v13_shim_mapping_review_v1.py')
    plan_path = root / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
                        'report/assets/20261018_mr3_p2a0_v22_ray_box/predeclared_plan_v22.json')
    plan = json.loads(read(plan_path))
    pins = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
    reader_path = root / relative
    raw = read(reader_path)
    expected = '775a5f012e6098f7083735cd2064e1963d855a9c5b5356af99eebd21e4737282'
    if pins.get(relative) != expected or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('immutable A13 Shim reader source/plan SHA differs')
    spec = importlib.util.spec_from_file_location('shim_review', reader_path)
    result = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(reader_path), 'exec'), result.__dict__)
    return result


def call_shim_review(supplement, run, prefix, freeze, read):
    """Only the new binary-proof CLI path changes; strict reader math is reused."""
    original = supplement.BINARY
    if original != Path('/tmp/mr3_p2a0_v13_binaryproof.json'):
        raise ValueError('immutable A13 Shim reader binary-proof default differs')
    try:
        supplement.BINARY = Path('/tmp/mr3_p2a0_v22_binaryproof.json')
        return supplement.review(run, prefix, freeze, read)
    finally:
        supplement.BINARY = original


def load_checked_corrector(read):
    """Load the separately bound custody supplement; original monitor/math stays intact."""
    root = Path('/home/zhuyulab/ns3-workspace')
    asset = ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
             'report/assets/20261018_mr3_p2a0_v22_ray_box/')
    plan = json.loads(read(root / (asset + 'predeclared_plan_v22.json')))
    pins = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
    relative = asset + 'independent/mr3_v22_corrector_custody_v2.py'
    binding = root / (asset + 'independent/mr3_v22_corrector_binding_v1.json')
    raw = read(root / relative)
    if pins.get(relative) != hashlib.sha256(raw).hexdigest():
        raise ValueError('corrector custody source/plan SHA differs')
    if pins.get(str(binding.relative_to(root))) != hashlib.sha256(read(binding)).hexdigest():
        raise ValueError('corrector custody binding/plan SHA differs')
    spec = importlib.util.spec_from_file_location('v22_corrector_custody', root / relative)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(root / relative), 'exec'), module.__dict__)
    return module, binding


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('--prefix',required=True);parser.add_argument('--freeze',required=True);parser.add_argument('--expected-episodes',type=int,required=True);parser.add_argument('--require-parameters',action='store_true');a=parser.parse_args();errors=[];bindings={};prefix=Path('/tmp')/a.prefix
    def check(value,message):
        if not value:errors.append(message)
    def read(path):
        raw = path.read_bytes()
        entry = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        previous = bindings.get(str(path))
        if previous is not None and previous != entry:
            raise ValueError('input changed across reads: ' + str(path))
        bindings.setdefault(str(path), entry)
        return raw
    def js(path):return json.loads(read(path))
    launch=js(Path(str(prefix)+'_launch.json'));binary=js(Path('/tmp/mr3_p2a0_v22_binaryproof.json'));check(launch['freeze']==binary['freeze']==a.freeze,'launch/binary freeze differs');check(launch['returncode']==0,'benchmark launcher returned nonzero (overall stage FAIL)')
    spec=importlib.util.spec_from_file_location('observer','/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_readonly_v10_drive_process_monitor.py');observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
    monitor_paths=sorted(Path('/tmp').glob(a.prefix+'_process_monitor_*.json'));monitors=[js(x) for x in monitor_paths];mapped_workers={};
    for index,d in enumerate(monitors):
        check(d['freeze']==a.freeze and not d['errors'],'live monitor freeze/error differs')
        procs={x['identity']['pid']:x['identity'] for x in d['owned_current_processes']}
        for g in d['gazebo_mapped_libraries']:
            if not (g['new_drive_mapped'] and not g['old_system_drive_mapped'] and g['identity_still_same_after_maps'] and g['mappings'] and all(x['matches_declared_binary'] for x in g['mappings'])):continue
            identity=g['identity'];pid=identity['pid'];seen=set()
            while pid in procs and pid not in seen:
                seen.add(pid);saved=procs[pid];mapped_workers.setdefault((saved['pid'],saved['start_ticks']),[]).append({'monitor':str(monitor_paths[index]),'gzserver_identity':identity});pid=saved['parent']
    actual_sha=hashlib.sha256(read(Path(binary['library_path']))).hexdigest();check(actual_sha==binary['library_sha256'],'current library bytes differ');directories=sorted(a.run.glob('worker*/episode*'));check(len(directories)==a.expected_episodes,'attempted episode count differs from predeclared workload');all_saved=[launch['benchmark_parent'],launch['launcher_identity']];episodes=[]
    for episode_index,ep in enumerate(directories,1):
        local=[]
        def c(value,message):
            if not value:local.append(message);errors.append(ep.name+': '+message)
        meta=js(ep/'metadata.json');epoch=meta['epoch'];sh=js(ep/'supervisor_shutdown.json');native=js(ep/'native_stop.json');nav=js(ep/'nav2_shutdown.json');sm=js(ep/'supervisor_metadata.json');log=read(ep/'launch.log').decode();starts={int(p):n for n,p in re.findall(r'\[INFO\] \[([^]]+)\]: process started with pid \[(\d+)\]',log)};clean={int(p):n for n,p in re.findall(r'\[INFO\] \[([^]]+)\]: process has finished cleanly \[pid (\d+)\]',log)}
        c(meta['freeze']==a.freeze and sh['epoch']==epoch,'metadata/shutdown identity differs');c(bool(starts) and starts.keys()==clean.keys(),'native started/clean exit sets differ');c(not re.search(r'process has died|process has been terminated|escalating to SIG|killing process',log),'native failure/forced signal recorded');c(set(starts).issubset({x['pid'] for x in sh['owned_processes_seen']}),'native start missing from saved owned ledger');c(sh['worker_returncode']==0 and sh['forced_shutdown'] is False and sh['failed_sample'] is False and not sh['remaining_owned_processes'] and not sh['remaining_owned_zombies'],'strict supervisor closure failed');c(native.get('returncode')==0 and native.get('server_clean_exit_recorded') is True and native.get('method')=='owned_launch_native_stop','native orderly stop failed');c(nav['epoch']==epoch and not nav['failures'],'Nav2 closure failed')
        states=[x for robot in nav['robots'] for x in robot['states']];c(len(nav['robots'])==3 and all(robot['shutdown']['response']['success'] is True for robot in nav['robots']) and len(states)==18 and all(x['state']['id']==4 and x['state']['label']=='finalized' for x in states),'three robot/18state finalized evidence incomplete');worker=sm['worker_identity'];c(worker['parent']==launch['benchmark_parent']['pid'],'saved worker not benchmark descendant');c((worker['pid'],worker['start_ticks']) in mapped_workers,'no live actual mapped library proof tied to this exact worker ancestry')
        topology=js(ep/'drive_topology.json');c(topology['epoch']==epoch and topology['schema']=='mr3-drive-topology-v1','drive topology epoch/schema differs');sources={};models={};
        for name in ('tb1','tb2','tb3'):
            driver=('/'+name,'turtlebot3_diff_drive');target='/'+name+'/mr3_drive/target';status='/'+name+'/mr3_drive/status'
            for entries,owner in ((topology['publishers'][target],('/','motion_safety')),(topology['publishers'][status],driver),(topology['target_subscribers'][target],driver)):
                c(len(entries)==1 and all((x['namespace'],x['node'])==owner and x['topic_type']=='std_msgs/msg/String' for x in entries),'target/status native endpoint differs '+name)
            c(not any((x['namespace'],x['node'])==driver for x in topology['legacy_subscribers']['/'+name+'/cmd_vel']),'tagged driver still subscribes Twist '+name)
            raw=read(ep/('drive_'+name+'.jsonl'));cfg=json.loads(raw.splitlines()[0]);keys=('compiled_source_sha256','compiled_header_sha256','compiled_helper_sha256','compiled_target_contract_sha256');valid=cfg['kind']=='configuration' and cfg['schema']=='mr3-drive-actuation-v2' and cfg['epoch']==epoch and cfg['robot']==name and cfg['loaded_library_path']==binary['library_path'] and cfg['command_mode']=='tagged' and cfg['command_topic']==target and cfg['status_topic']==status and all(cfg[k]==binary[k] for k in keys);c(valid,'actual driver source/config differs '+name);sources[name]={'passed':valid,'four_compiled_sources':{k:cfg.get(k) for k in keys},'loaded_library_path':cfg.get('loaded_library_path')}
            raw=read(ep/('drive_model_'+name+'.sdf'));plugins=ET.fromstring(raw).findall(".//plugin[@name='turtlebot3_diff_drive']");valid=len(plugins)==1
            if valid:
                plugin=plugins[0];valid=plugin.get('filename')=='libmr3_gazebo_diff_drive.so' and plugin.findtext('mr3_tagged_commands')=='true' and plugin.findtext('mr3_epoch')==epoch and plugin.findtext('mr3_audit_path')==str(ep/('drive_'+name+'.jsonl'))
            c(valid,'actual tagged SDF differs '+name);models[name]={'passed':valid,'sha256':hashlib.sha256(raw).hexdigest()}
        fifo_path=Path(str(prefix)+'_episode'+str(episode_index).zfill(3)+'_fifo_phase_final.json');fifo=js(fifo_path);c(fifo.get('passed') is True and fifo['errors']==[] and fifo['freeze']==a.freeze and fifo['epoch']==epoch,'actual FIFO/phase facts failed');
        for path,entry in fifo['bindings'].items():
            raw=read(Path(path));c(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],'FIFO bound raw bytes changed '+Path(path).name)
        if a.require_parameters:
            parameters=js(ep/'actual_nav2_parameters.json');c(parameters.get('passed') is True and parameters.get('freeze')==a.freeze and parameters.get('epoch')==epoch and len(parameters.get('nodes',{}))==9,'actual nine parameter readback failed')
        read(ep/'motion_topology.json');all_saved.extend(sh['owned_processes_seen']);episodes.append({'directory':str(ep),'epoch':epoch,'passed':not local,'native_started':len(starts),'native_clean_exits':len(clean),'owned_identity_rows':len(sh['owned_processes_seen']),'worker_identity':worker,'live_library_mapping':mapped_workers.get((worker['pid'],worker['start_ticks']),[]),'sources':sources,'models':models,'fifo_phase_review':str(fifo_path),'native_stop':native,'supervisor':{k:sh[k] for k in ('worker_returncode','forced_shutdown','failed_sample','remaining_owned_processes','remaining_owned_zombies')},'errors':local})
    supplement = load_checked_shim(read)
    try:
        shim_review = call_shim_review(supplement, a.run, prefix, a.freeze, read)
    except (OSError, ValueError, KeyError, TypeError) as error:
        shim_review = {'schema': 'mr3-v22-shim-mapping-review-v1', 'passed': False,
                       'freeze': a.freeze, 'errors': [str(error)]}
    shim_output = Path(str(prefix) + '_shim_mapping_review_v1.json')
    with shim_output.open('x') as stream:
        json.dump(shim_review, stream, indent=2, allow_nan=False)
        stream.write('\n')
    read(shim_output)
    check(shim_review.get('passed') is True, 'per-episode actual loaded Shim custody failed')
    try:
        corrector_module, corrector_binding = load_checked_corrector(read)
        corrector_review = corrector_module.review(a.run, prefix, a.freeze, corrector_binding, read)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        corrector_review = {'schema': 'mr3-v22-corrector-custody-review-failed-v1',
                            'passed': False, 'freeze': a.freeze, 'errors': [str(error)]}
    corrector_output = Path(str(prefix) + '_corrector_custody_review_v1.json')
    with corrector_output.open('x') as stream:
        json.dump(corrector_review, stream, indent=2, allow_nan=False)
        stream.write('\n')
    read(corrector_output)
    check(corrector_review.get('passed') is True, 'per-episode native corrector/ODE custody failed')
    for bound_path, expected in list(bindings.items()):
        try:
            final_raw = Path(bound_path).read_bytes()
            check(len(final_raw) == expected['bytes']
                  and hashlib.sha256(final_raw).hexdigest() == expected['sha256'],
                  'bound input changed before final verdict: ' + bound_path)
        except OSError as error:
            check(False, 'bound input unavailable before final verdict: ' + bound_path + ': ' + str(error))
    byid={(x['pid'],x['start_ticks']):x for x in all_saved};identities=[{'saved':x,'current':observer.proc_identity(x['pid']),'same_identity_present':observer.same(x) is not None} for x in byid.values()];gone=all(not x['same_identity_present'] for x in identities);check(gone,'actual saved PID/start identity remains');result={'schema':'mr3-v22-multiepoch-owned-closure-binary-review-v1','passed':not errors,'freeze':a.freeze,'capture_wall_monotonic_ns':time.monotonic_ns(),'run':str(a.run),'attempted_episodes':len(directories),'episodes':episodes,'saved_identity_count':len(byid),'identities':identities,'all_saved_identities_gone':gone,'native_closure_and_binary_children_passed':gone and all(x['passed'] for x in episodes),'native_started_total':sum(x['native_started'] for x in episodes),'native_clean_exits_total':sum(x['native_clean_exits'] for x in episodes),'launch_returncode':launch['returncode'],'launch_wall_sec':launch.get('wall_duration_sec'),'library_actual_sha256':actual_sha,'library_matches_frozen_proof':actual_sha==binary['library_sha256'],'shim_mapping_required':True,'shim_mapping_review':str(shim_output),'shim_mapping_passed':shim_review.get('passed') is True,'corrector_custody_review':str(corrector_output),'corrector_custody_passed':corrector_review.get('passed') is True,'input_bindings_rechecked':True,'bindings':bindings,'reviewer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'errors':sorted(set(errors)),'scope':'All actual saved identities checked without a fixed identity-count assumption; exact per-epoch native close, live mapped driver ancestry, SDF/graph/four source provenance and FIFO/phase facts; independent original-wrapper equality and per-episode three-controller loaded Shim custody are additionally required. Parameter hook is checked only when explicitly required (interface); no inferred motion/braking credit. Original launcher nonzero reports overall failure separately from strict child closure facts. No task/body/conditional or full-stage PASS inferred. Additional per-episode native corrector/ODE maps and closed install/callback ledger custody are required independently of all original gates.'};out=Path(str(prefix)+'_closure_binary_review_v1.json')
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('passed','freeze','attempted_episodes','saved_identity_count','all_saved_identities_gone','native_started_total','native_clean_exits_total','errors')}))


if __name__=='__main__':main()
