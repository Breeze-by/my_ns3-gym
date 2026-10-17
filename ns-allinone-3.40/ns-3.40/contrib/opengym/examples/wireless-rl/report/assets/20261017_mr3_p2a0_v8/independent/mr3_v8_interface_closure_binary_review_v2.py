"""Read-only exact owned shutdown and actual actuator binary provenance after close."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--prefix',required=True);p.add_argument('--freeze',required=True);a=p.parse_args();errors=[];bindings={}
    def check(value,message):
        if not value:errors.append(message)
    def read(path):
        raw=path.read_bytes();bindings[str(path)]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()};return raw
    def js(path):return json.loads(read(path))
    prefix=Path('/tmp')/a.prefix;launch=js(Path(str(prefix)+'_launch.json'));binary=js(Path('/tmp/mr3_p2a0_v8_binaryproof.json'));episodes=list(a.run.glob('worker*/episode*'));check(len(episodes)==1,'expected exactly one interface episode');ep=episodes[0];meta=js(ep/'metadata.json');epoch=meta['epoch'];check(meta['freeze']==launch['freeze']==binary['freeze']==a.freeze,'freeze differs')
    shutdown=js(ep/'supervisor_shutdown.json');native_stop=js(ep/'native_stop.json');nav=js(ep/'nav2_shutdown.json');worker=js(ep/'supervisor_metadata.json');params=js(ep/'actual_nav2_parameters.json');log=read(ep/'launch.log').decode();starts={int(pid):node for node,pid in re.findall(r'\[INFO\] \[([^]]+)\]: process started with pid \[(\d+)\]',log)};clean={int(pid):node for node,pid in re.findall(r'\[INFO\] \[([^]]+)\]: process has finished cleanly \[pid (\d+)\]',log)}
    check(len(starts)==39 and starts.keys()==clean.keys(),'native 39 starts/clean exit set mismatch');check(not re.search(r'process has died|process has been terminated|escalating to SIG|killing process',log),'native failure/forced signal in launch log')
    spec=importlib.util.spec_from_file_location('observer','/tmp/mr3_readonly_v8_drive_process_monitor.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    saved=shutdown['owned_processes_seen']+[launch['benchmark_parent'],launch['launcher_identity']];byid={(x['pid'],x['start_ticks']):x for x in saved};identities=[{'saved':x,'current':mod.proc_identity(x['pid']),'same_identity_present':mod.same(x) is not None} for x in byid.values()];gone=not any(x['same_identity_present'] for x in identities);check(len(byid)==len(saved),'duplicate saved PID/start identities');check(set(starts).issubset({x['pid'] for x in shutdown['owned_processes_seen']}),'native start identity missing from owned ledger');check(worker['worker_identity']['pid'] in {x['pid'] for x in shutdown['owned_processes_seen']},'worker identity missing from owned ledger');check(gone,'saved owned identity still present');check(shutdown['worker_returncode']==0 and shutdown['forced_shutdown'] is False and shutdown['failed_sample'] is False and not shutdown['remaining_owned_processes'] and not shutdown['remaining_owned_zombies'],'supervisor closure failed');check(launch['returncode']==0 and launch.get('benchmark_parent_after') is None,'launcher/parent did not finish cleanly')
    check(native_stop.get('returncode')==0 and native_stop.get('method')=='owned_launch_native_stop' and native_stop.get('server_clean_exit_recorded') is True,'native orderly stop failed');check(nav.get('epoch')==epoch and not nav.get('failures'),'Nav2 shutdown failed')
    states=[]
    for robot in nav['robots']:
        check(robot['shutdown']['response']['success'] is True,'Nav2 shutdown response failed '+robot['robot'])
        states.extend(robot['states'])
    check(len(states)==18 and all(x['state']['id']==4 and x['state']['label']=='finalized' for x in states),'18 finalized Nav2 states missing')
    actual_sha=hashlib.sha256(read(Path(binary['library_path']))).hexdigest();check(actual_sha==binary['library_sha256'],'current library differs from frozen proof');monitors=[];live_mapped=False;full_provenance=False
    for path in sorted(Path('/tmp').glob(a.prefix+'_process_monitor_*.json')):
        d=js(path);check(d['freeze']==a.freeze and not d['errors'],'live monitor error/freeze mismatch');monitors.append(str(path));
        for g in d['gazebo_mapped_libraries']:
            if g['new_drive_mapped'] and not g['old_system_drive_mapped'] and g['identity_still_same_after_maps'] and all(x['matches_declared_binary'] for x in g['mappings']):live_mapped=True
        for episode in d['episodes']:
            if len(episode['drivers'])==3 and all(x.get('compiled_match') is True and x.get('tagged_match') is True and x.get('library_match') is True for x in episode['drivers'].values()) and all(episode['evidence'].get(k,{}).get('valid') is True for k in ('drive_topology','model_tb1','model_tb2','model_tb3')):full_provenance=True
    check(live_mapped,'actual owned gzserver mapped library proof missing');check(full_provenance,'actual four-source/tagged topology/SDF proof missing');check(params.get('passed') is True and params.get('freeze')==a.freeze and params.get('epoch')==epoch and len(params.get('nodes',{}))==9,'actual nine parameter readback failed')
    for name in ('drive_topology.json','motion_topology.json','drive_model_tb1.sdf','drive_model_tb2.sdf','drive_model_tb3.sdf','drive_tb1.jsonl','drive_tb2.jsonl','drive_tb3.jsonl','drive_targets.jsonl','drive_phase_worker.jsonl','motion_phase_worker.jsonl','physics.jsonl','transitions.jsonl'):read(ep/name)
    fifo_path=Path(str(prefix)+'_fifo_phase_final.json');fifo=js(fifo_path);check(fifo.get('passed') is True and fifo['freeze']==a.freeze and fifo['epoch']==epoch,'actual FIFO/phase fact review failed')
    result={'schema':'mr3-v8-final-owned-closure-binary-review-v2','prior_observer_result':'/tmp/'+a.prefix+'_closure_binary_review_v1.json','observer_correction':'The actual owned ledger has45 plus parent/launcher=47. Original fixed46 assumption corrected to complete exact saved identity absence with all39 native starts and worker identity covered; no predeclared gate changed.','passed':not errors,'freeze':a.freeze,'epoch':epoch,'capture_wall_monotonic_ns':time.monotonic_ns(),'reviewer_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'monitor_source_sha256':hashlib.sha256(Path('/tmp/mr3_readonly_v8_drive_process_monitor.py').read_bytes()).hexdigest(),'fifo_reviewer_source_sha256':hashlib.sha256(Path('/tmp/mr3_v8_interface_fifo_phase_review.py').read_bytes()).hexdigest(),'saved_identity_count':len(byid),'identities':identities,'all_saved_identities_gone':gone,'owned_seen_unique':len(shutdown['owned_processes_seen']),'native_started':len(starts),'native_exited_cleanly':len(clean),'native_missing_clean_exits':sorted(starts.keys()-clean.keys()),'native_complete':starts.keys()==clean.keys(),'supervisor':{k:shutdown[k] for k in ('worker_returncode','forced_shutdown','failed_sample','remaining_owned_processes','remaining_owned_zombies')},'launch_returncode':launch['returncode'],'launch_wall_sec':launch.get('wall_duration_sec'),'library_actual_sha256':actual_sha,'library_matches_frozen_proof':actual_sha==binary['library_sha256'],'actual_live_mapping_proved':live_mapped,'actual_four_source_tagged_SDF_and_topology_proved':full_provenance,'actual_nine_parameter_readback_passed':params.get('passed'),'native_stop':native_stop,'nav2_shutdown_success':not nav['failures'],'monitor_bindings':monitors,'fifo_phase_review':str(fifo_path),'bindings':bindings,'errors':sorted(set(errors)),'scope':'Strict native shutdown, exact saved PID/start absence, raw-byte provenance and actual live maps/topology/SDF/fourcompiled hashes plus telemetry FIFO/phase facts. No task, body, braking, conditional-model or overall matrix PASS inferred.'}
    out=Path(str(prefix)+'_closure_binary_review_v2.json');
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('passed','freeze','saved_identity_count','all_saved_identities_gone','native_started','native_exited_cleanly','errors')}))


if __name__=='__main__':main()
