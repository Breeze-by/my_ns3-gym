"""Explicit, lossless correction of an observer-only fixed-count mistake; no controls."""
from pathlib import Path
import hashlib
import json
import time

P=Path('/tmp/mr3_p2a0_v8_interface')
W=Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl')
sha=lambda b:hashlib.sha256(b).hexdigest()
formal=Path(str(P)+'_closure_binary_review_v1.json'); original=formal.read_bytes(); first=json.loads(original)
assert first['passed'] is False and first['errors']==['saved identity count differs from declared 46']
v2_path=Path(str(P)+'_closure_binary_review_v2.json'); v2_raw=v2_path.read_bytes(); v2=json.loads(v2_raw)
assert sha(original)=='febbed49c8f84d06a38a30cb7a8f7050be36768aff4a002f8bebd3f78b5c2819'
assert sha(v2_raw)=='e515e02fac9fd427ab7caf9361b4aa2b470535744b85d2e1c39f4372d927c6af'
custody=[]
for source,destination in [(formal,Path(str(P)+'_closure_binary_initial_observer_failure_v1.json')),(Path(str(P)+'_closure_binary_command_v1.json'),Path(str(P)+'_closure_binary_initial_observer_command_v1.json')),(Path(str(P)+'_closure_binary_console.log'),Path(str(P)+'_closure_binary_initial_observer_console_v1.log')),(Path('/tmp/mr3_v8_interface_closure_binary_review.py'),Path(str(P)+'_closure_binary_initial_observer_script_v1.py'))]:
    raw=source.read_bytes()
    with destination.open('xb') as f:f.write(raw)
    assert destination.read_bytes()==raw
    custody.append({'source':str(source),'preserved':str(destination),'bytes':len(raw),'sha256':sha(raw)})
command=json.loads(Path(str(P)+'_closure_binary_command_v1.json').read_bytes())
assert command['source_sha256']==custody[3]['sha256'] and command['stdout_sha256']==custody[2]['sha256']
plan_path=W/'report/assets/20261017_mr3_p2a0_v8/predeclared_plan_v8.json';plan_raw=plan_path.read_bytes();plan=json.loads(plan_raw)
assert sha(plan_raw)=='b7487cd09450044d815904e240e795f25800e3ae542bf665e7585467cbe5b60b'
assert all('owned_identity_absence' in stage['required_audits'] for stage in plan['stages'])
fresh=[]
for row in v2['identities']:
    saved=row['saved']; path=Path('/proc')/str(saved['pid'])/'stat'
    try:
        raw=path.read_text(); parts=raw[raw.rfind(')')+2:].split(); current={'pid':saved['pid'],'start_ticks':int(parts[19]),'state':parts[0]}
    except FileNotFoundError:current=None
    fresh.append({'saved':saved,'current':current,'same_identity_present':current is not None and current['start_ticks']==saved['start_ticks']})
raw_bindings_match=True
for path,entry in v2['bindings'].items():
    raw=Path(path).read_bytes();raw_bindings_match=raw_bindings_match and len(raw)==entry['bytes'] and sha(raw)==entry['sha256']
checks={'v2_passed':v2['passed'] is True,'v2_errors_empty':v2['errors']==[], 'v2_freeze_exact':v2['freeze']=='d41485dfd93797026316806916e127eb5101f3b8','all_actual_saved_identities_absent':all(not row['same_identity_present'] for row in fresh),'all_actual_saved_rows_accounted':len(fresh)==v2['saved_identity_count']==len(v2['identities']),'all_actual_native_clean':v2['native_started']==v2['native_exited_cleanly']==39 and v2['native_complete'] is True and not v2['native_missing_clean_exits'],'strict_supervisor':v2['supervisor']['worker_returncode']==0 and v2['supervisor']['forced_shutdown'] is False and v2['supervisor']['failed_sample'] is False and not v2['supervisor']['remaining_owned_processes'] and not v2['supervisor']['remaining_owned_zombies'],'launcher_closed':v2['launch_returncode']==0,'actual_library_and_source_bindings':v2['library_matches_frozen_proof'] is True and v2['actual_live_mapping_proved'] is True and v2['actual_four_source_tagged_SDF_and_topology_proved'] is True,'actual_nine_parameters':v2['actual_nine_parameter_readback_passed'] is True,'nav2_shutdown':v2['nav2_shutdown_success'] is True,'orderly_native_stop':v2['native_stop']['returncode']==0 and v2['native_stop']['server_clean_exit_recorded'] is True,'all_v2_raw_bindings_unchanged':raw_bindings_match,'original_failure_custody_verified':True}
fifo=json.loads(Path(v2['fifo_phase_review']).read_bytes());checks['actual_fifo_phase_passed']=fifo['passed'] is True and fifo['errors']==[] and fifo['freeze']==v2['freeze'] and fifo['epoch']==v2['epoch']
result=dict(v2);result.update({'schema':'mr3-v8-owned-closure-explicit-observer-correction-v1','passed':all(checks.values()),'errors':[key for key,value in checks.items() if not value],'correction_checks':checks,'correction':{'original_formal_path':str(formal),'original_result_preserved':custody[0],'original_passed':False,'original_error_unchanged':first['errors'],'corrected_review':{'path':str(v2_path),'bytes':len(v2_raw),'sha256':sha(v2_raw),'passed':v2['passed']},'reason':'The original observer incorrectly assumed exactly46 saved identities. Actual supervisor45 plus benchmark/launcher2=47; the predeclared contract requires absence of all exact saved identities, not an exact identity-count gate. All47 are independently absent; no native/task/body/conditional or acceptance gate is loosened. Original failure JSON/script/command/console remain exact, and v2 remains unchanged.','plan':{'path':str(plan_path),'sha256':sha(plan_raw),'owned_gate':'owned_identity_absence','fixed_identity_count_gate_present':False},'custody_artifacts':custody},'fresh_identity_absence':fresh,'correction_wall_monotonic_ns':time.monotonic_ns(),'correction_script_sha256':sha(Path(__file__).read_bytes())})
new=(json.dumps(result,indent=2)+'\n').encode()
formal.write_bytes(new)
assert v2_path.read_bytes()==v2_raw and Path(custody[0]['preserved']).read_bytes()==original
receipt={'schema':'mr3-v8-owned-closure-observer-correction-custody-v1','passed':True,'formal_result_passed':result['passed'],'freeze':result['freeze'],'original_formal_sha256':sha(original),'corrected_formal_sha256':sha(new),'corrected_formal_path':str(formal),'v2_preserved_sha256':sha(v2_raw),'all_contract_checks':checks,'preserved_original_artifacts':custody,'actual_saved_identity_count':len(fresh),'all_actual_saved_identities_absent':checks['all_actual_saved_identities_absent'],'correction_script':str(Path(__file__)),'correction_script_sha256':sha(Path(__file__).read_bytes()),'scope':'Explicit observer correction only, with original failure custody; no native rerun, no source/Git writes, no new physical/task credit.'}
receipt_path=Path(str(P)+'_closure_binary_correction_custody_v1.json')
with receipt_path.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps({'passed':result['passed'],'formal_sha256':sha(new),'original_sha256':sha(original),'v2_sha256':sha(v2_raw),'custody_receipt':str(receipt_path),'actual_identities':len(fresh),'errors':result['errors']}))
