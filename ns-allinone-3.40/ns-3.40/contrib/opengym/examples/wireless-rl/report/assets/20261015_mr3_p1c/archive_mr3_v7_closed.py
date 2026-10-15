"""Offline closed-stage v7 archiving; no simulator, source mutation or process control."""

import collections,gzip,hashlib,json,re,subprocess,time
from pathlib import Path
root=Path('/home/zhuyulab/ns3-workspace');ros=root/'ros2_ws/ros2-multi-robot-automap';assets=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261015_mr3_p1c'
freeze=None;sha=lambda b:hashlib.sha256(b).hexdigest();auditor=ros/'scripts/audit_mr3_env.py'
def review_episode(episode,audit):
 plan_path=assets/'predeclared_native_plan_v7.json';plan=json.loads(plan_path.read_text())
 assert sha(plan_path.read_bytes())=='f63d0892bcdd4ec5fef91ca261a1c267570667e190cacbfec18610fe3f1c5630'
 assert plan['transport_profile']['sha256']=='dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b'
 metadata=json.loads((episode/'metadata.json').read_text())
 transport=metadata['transport_environment']
 assert metadata['freeze']==freeze and transport['profile_sha256']=='dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b'
 assert transport['RMW_IMPLEMENTATION']=='rmw_fastrtps_cpp' and transport['ROS_LOCALHOST_ONLY']=='0'
 assert audit['passed'] and audit['freeze']==freeze and audit['ordered_shutdown']['required'] and audit['ordered_shutdown']['proven'] and audit['contacts']['passed'] and audit['initial_inputs_ready']['proven']
 records=[];starts={};cleans={};signals={}
 for line_no,line in enumerate((episode/'launch.log').read_text().splitlines(),1):
  if 'MR3_ORDERED_SHUTDOWN ' in line:records.append((line_no,json.loads(line.split('MR3_ORDERED_SHUTDOWN ',1)[1])))
  m=re.fullmatch(r'\[INFO\] \[([^\]]+)\]: process started with pid \[(\d+)\]',line)
  if m:assert m[1] not in starts;starts[m[1]]=(int(m[2]),line_no)
  m=re.fullmatch(r'\[INFO\] \[([^\]]+)\]: process has finished cleanly \[pid (\d+)\]',line)
  if m:assert m[1] not in cleans;cleans[m[1]]=(int(m[2]),line_no)
  m=re.fullmatch(r"\[INFO\] \[([^\]]+)\]: sending signal 'SIGINT' to process\[([^\]]+)\]",line)
  if m:assert m[1]==m[2] and m[1] not in signals;signals[m[1]]=line_no
 assert len(records)>0 and len(starts)==len(cleans)==audit['ordered_shutdown']['launch']['actual_process_starts']
 assert [z['receipt_index'] for _,z in records]==list(range(1,len(records)+1))
 assert all(z['epoch']==audit['epoch'] and z['protocol']==audit['ordered_shutdown']['protocol'] for _,z in records)
 assert all(x['wall_monotonic_ns']<=y['wall_monotonic_ns'] for (_,x),(_,y) in zip(records,records[1:]))
 live={};all_processes={};exits={};pending=None;durations=[];begin=None
 for line,z in records:
  event=z['event']
  if event=='process_started':
   assert z['pid'] not in all_processes and starts[z['process_name']][0]==z['pid']
   assert z['process_start_index']==len(all_processes)+1
   live[z['pid']]=z;all_processes[z['pid']]=z
  elif event=='process_exited':
   p=live.pop(z['pid']);assert all(z[k]==p[k] for k in ['action_id','process_start_index','process_name','role']) and z['returncode']==0
   assert cleans[z['process_name']][0]==z['pid'] and cleans[z['process_name']][1]<line
   exits[z['pid']]=z
   if z['controlled']:
    assert pending is not None and pending[1]['pid']==z['pid'] and pending[1]['signal_sequence']==z['signal_sequence']
    assert pending[0]<signals[z['process_name']]<cleans[z['process_name']][1]<line
    durations.append((z['wall_monotonic_ns']-pending[1]['wall_monotonic_ns'])/1e9);pending=None
  elif event=='begin':
   begin=z;assert z['evaluator_pid'] in exits
   assert [p['pid'] for p in sorted(live.values(),key=lambda p:-p['process_start_index']) if p['role']=='owned_ros']==[p['pid'] for p in z['remaining']]
  elif event=='signal':
   assert pending is None and z['signal']=='SIGINT' and z['pid'] in live
   assert z['process_start_index']==max(p['process_start_index'] for p in live.values() if p['role']=='owned_ros')
   pending=(line,z)
  elif event in ['ros_complete','gz_stop']:
   assert pending is None and not any(p['role']=='owned_ros' for p in live.values())
   if event=='gz_stop':assert all(cleans[p['process_name']][1]<line for p in all_processes.values() if p['role']=='owned_ros')
  elif event=='complete':assert not live and pending is None
  else:raise AssertionError(event)
 assert len(durations)==len(signals)==audit['ordered_shutdown']['launch']['serial_sigint_count']
 nav2=json.loads((episode/'nav2_shutdown.json').read_text())
 assert nav2['completed_wall_monotonic_ns']<exits[begin['evaluator_pid']]['wall_monotonic_ns']<=begin['wall_monotonic_ns']
 assert nav2['start_clock_ns']==nav2['end_clock_ns']==nav2['physical_time_ns']==audit['ordered_shutdown']['nav2']['paused_time_ns']
 for robot in nav2['robots']:
  assert robot['shutdown']['response']['success'] is True and len(robot['states'])==6
  assert all(n['state']=={'id':4,'label':'finalized'} for n in robot['states'])
 return {'plan_sha256':sha(plan_path.read_bytes()),'metadata_freeze':metadata['freeze'],'metadata_transport_profile_sha256':transport['profile_sha256'],'metadata_profile_matches_v7_plan':True,'raw_marker_count':len(records),'actual_process_starts':len(starts),'actual_process_clean_exits':len(cleans),'serial_sigint_count':len(signals),'all_identity_markers_bound_to_actual_SDK_start_clean_signal_lines':True,'strict_reverse_actual_active_start_order':True,'one_signal_then_actual_clean_exit_then_next_signal':True,'all_ROS_clean_before_native_stop':True,'nav2_success_responses':3,'nav2_actual_FINALIZED_responses':18,'nav2_finalized_before_actual_evaluator_exit_before_serial_begin':True,'paused_cleanup_ns':nav2['physical_time_ns'],'individual_signal_to_exit_wall_sec':durations,'max_individual_signal_to_exit_wall_sec':max(durations) if durations else 0,'native_server_pid':records[-1][1]['server_pid'],'native_stop_cli_pid':records[-1][1]['stop_cli_pid']}
def copy_files(source,target):
 files=[]
 for path in sorted(source.rglob('*')):
  if not path.is_file():continue
  raw=path.read_bytes();rel=path.relative_to(source);compressed=path.suffix in {'.log','.jsonl'};existing=None
  if compressed:
   existing=path.with_name(path.name+'.gz');out=existing.read_bytes() if existing.exists() else gzip.compress(raw,mtime=0);assert gzip.decompress(out)==raw;rel=rel.with_name(rel.name+'.gz')
  else:out=raw
  dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  if dest.exists():assert dest.read_bytes()==out,str(dest)
  else:
   with dest.open('xb') as f:f.write(out)
  assert sha(path.read_bytes())==sha(raw)
  files.append({'original':str(path.relative_to(root)),'original_bytes':len(raw),'original_sha256':sha(raw),'selected':str(dest.relative_to(root)),'selected_bytes':len(out),'selected_sha256':sha(out),'encoding':'gzip (existing source gzip retained)' if compressed and existing.exists() else 'gzip; mtime=0' if compressed else 'identity','decoded_selected_sha256':sha(raw),'decoded_matches_original':(gzip.decompress(out) if compressed else out)==raw})
 return files
def write_new(path,data):
 with path.open('x') as output:json.dump(data,output,ensure_ascii=False,indent=2);output.write('\n')
def verify_files(files):
 for f in files:assert sha((root/f['original']).read_bytes())==f['original_sha256'] and sha((root/f['selected']).read_bytes())==f['selected_sha256']

import argparse,importlib.util,sys
BINDING_SHA='09a9f2263385a1a9d4bae02676fc26f23d64a026f8633634f8dd3a310bff1117'
def reference(path):return {'path':str(path.relative_to(root)),'sha256':sha(path.read_bytes())}
def binding_guard(expected_freeze):
 path=assets/'predeclared_execution_binding_v7.json'
 assert sha(path.read_bytes())==BINDING_SHA
 binding=json.loads(path.read_text());driver_path=root/binding['files']['driver']['path']
 assert sha(driver_path.read_bytes())==binding['files']['driver']['sha256']
 spec=importlib.util.spec_from_file_location('archive_pinned_v7_driver',driver_path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module.verify_binding(root,expected_freeze,path,BINDING_SHA)
def archive_clock(binding):
 source=ros/'log/mr3_step_clock/mr3_p1c_v7_clock';target=assets/'native_v7/clock'
 summary=json.loads((source/'summary.json').read_text());metadata=json.loads((source/'metadata.json').read_text())
 assert summary['passed'] is True and summary['error'] is None
 for value in [metadata,summary]:
  assert value['freeze']==freeze and value['transport_environment']['profile_sha256']==binding['files']['profile']['sha256']
  assert value['transport_environment']['RMW_IMPLEMENTATION']=='rmw_fastrtps_cpp'
 assert summary['server_returncode']==summary['stop_cli_returncode']==0
 receipts=[json.loads(line) for line in (source/'physics.jsonl').read_text().splitlines()]
 required=[];previous=None
 for index,row in enumerate(receipts,1):
  assert row['ok'] is True and row['paused'] is True and row['epoch']=='mr3_p1c_v7_clock'
  assert row['request_id']==f'q{index}' and row['step_ns']==1000000
  assert row['end_iterations']-row['start_iterations']==row['steps']
  assert row['end_time_ns']-row['start_time_ns']==row['steps']*row['step_ns']
  assert row['start_time_ns']==row['start_iterations']*row['step_ns']
  assert row['end_time_ns']==row['end_iterations']*row['step_ns']
  if previous:
   assert row['start_time_ns']==previous['end_time_ns'] and row['start_iterations']==previous['end_iterations']
  if row['clock_boundary_required']:
   assert row['observed_ros_clock_ns']==row['end_time_ns'];required.append(row)
  previous=row
 assert [row['steps'] for row in required]==[20,20,20,20,20,1000,0]
 assert receipts[-1]['steps']==0 and receipts[-1]['start_time_ns']==receipts[-1]['end_time_ns']
 clocks=summary['clock_samples_ns']
 assert len(receipts)==summary['receipt_count'] and len(clocks)==summary['clock_sample_count']
 assert len(clocks)>1 and all(b-a==20000000 for a,b in zip(clocks,clocks[1:]))
 target.mkdir(parents=True,exist_ok=False);files=copy_files(source,target)
 review={'schema':'mr3-p1c-clock-independent-review-v1','passed':True,'source_freeze':freeze,
  'scope':'Saved isolated physical/clock component replay. No new native execution, robot-team/contact/Nav2/95%/training/network/SDK-fix credit.',
  'binding':reference(assets/'predeclared_execution_binding_v7.json'),
  'metadata_freeze_profile_match_binding':True,'receipt_count':len(receipts),
  'required_clock_boundary_count':len(required),'required_step_counts':[row['steps'] for row in required],
  'all_receipts_paused':True,'physical_tick_ns':1000000,
  'iteration_time_arithmetic_and_contiguity_exact':True,'required_observed_clock_matches_physics':True,
  'clock_sample_count':len(clocks),'clock_gap_ns':20000000,'clock_first_ns':clocks[0],'clock_last_ns':clocks[-1],
  'setup_alignment_receipts':len(receipts)-len(required),
  'setup_scope':'Setup may observe older ROS-clock delivery; only required boundaries assert equality.',
  'final_zero_step_preserves_time':True,'freeze_scope':'No separate sustained wall-duration pause trace saved.',
  'server_pid':summary['server_pid'],'server_returncode':summary['server_returncode'],
  'helper_pid':summary['helper_pid'],'helper_exit_scope':'Checker passed/errornull; pinned checker requires helper.wait return0, but summary has no helper_returncode field.',
  'stop_cli_pid':summary['stop_cli_pid'],'stop_cli_returncode':summary['stop_cli_returncode'],
  'wall_duration_sec':summary['wall_duration_sec'],'archive_tool':{'path':str(Path(__file__)),'sha256':sha(Path(__file__).read_bytes())},
  'reused_method':'v6 selected evidence gzip/identity+decoded SHA and independent exact tick/clock review; originals unchanged.'}
 rp=target/'independent_review.json';write_new(rp,review)
 manifest={'schema':'mr3-selected-native-evidence-manifest-v1','scope':'Complete closed v7 isolated clock fixture only; logs/JSONL gzip, original bytes/hash retained. Review is an additional derivative.',
  'source_freeze':freeze,'original_root':str(source.relative_to(root)),'selected_root':str(target.relative_to(root)),
  'originals_modified':False,'original_file_count':len(files),'selected_original_artifact_count':len({f['selected'] for f in files}),
  'files':files,'independent_review':reference(rp)}
 mp=target/'manifest.json';write_new(mp,manifest);verify_files(files)
 print(json.dumps({'stage':'clock','passed':True,'wall_sec':summary['wall_duration_sec'],'receipts':len(receipts),
  'clocks':len(clocks),'original_files':len(files),'selected_artifacts':manifest['selected_original_artifact_count'],
  'manifest_sha256':sha(mp.read_bytes()),'review_sha256':sha(rp.read_bytes())}))
def archive_team(stage,binding):
 source=ros/f'log/mr3_learning/mr3_p1c_v7_{stage}';target=assets/f'native_v7/{stage}'
 summary=json.loads((source/'benchmark_summary.json').read_text())
 assert summary['passed'] is True and summary['freeze']==freeze
 primary_path=assets/f'{stage}_v7_contact_phase_v3_benchmark_audit.json';primary=json.loads(primary_path.read_text())
 scalar_path=assets/f'{stage}_v7_scalar_v3_audit.json';scalar=json.loads(scalar_path.read_text())
 proof=primary['offline_contact_phase_audit']
 assert primary['passed'] is True and primary['errors']==[] and primary['freeze']==freeze
 assert proof['freeze']==freeze and proof['wrapper_sha256']==binding['files']['phase_auditor']['sha256']
 assert proof['command_time_gate']['sha256']==binding['files']['command_time_auditor']['sha256']
 assert scalar['freeze']==freeze
 scalar_field='completed_subset_scalar_checks_passed' if stage=='fault' else 'passed_scalar_checks'
 assert scalar[scalar_field] is True
 if stage=='fault':
  assert scalar['completed_subset_transitions']==24 and scalar['whole_fault_benchmark_reward_audit_performed'] is False
 episodes=[];identities=set();epochs=set()
 for audit in primary['episodes']:
  episode=Path(audit['directory']);assert episode.is_relative_to(source)
  assert audit['passed'] is True and audit['freeze']==freeze and audit['protocol']['command_time']['passed'] is True
  metadata=json.loads((episode/'metadata.json').read_text())
  assert metadata['transport_environment']['profile_sha256']==binding['files']['profile']['sha256']
  assert metadata['freeze']==freeze and metadata['transport_environment']['RMW_IMPLEMENTATION']=='rmw_fastrtps_cpp'
  shutdown=json.loads((episode/'supervisor_shutdown.json').read_text())
  assert not shutdown['remaining_owned_processes'] and not shutdown['remaining_owned_zombies']
  assert audit['epoch'] not in epochs;epochs.add(audit['epoch'])
  rows={(p['pid'],p['start_ticks']) for p in shutdown['owned_processes_seen']}
  assert not rows.intersection(identities);identities.update(rows)
  if audit['complete_episode_credit']:
   assert shutdown['worker_returncode']==0 and shutdown['forced_shutdown'] is False
   episode_proof=review_episode(episode,audit)
   assert audit['contacts']['raw_stream_count']==18
   episodes.append({'epoch':audit['epoch'],'directory':str(episode.relative_to(root)),
     'complete_episode_credit':True,'raw_SDK_lifecycle_profile_proof':episode_proof,
     'transitions':audit['transitions'],'protocol':audit['protocol'],'contacts':audit['contacts'],
     'initial_inputs_ready':audit['initial_inputs_ready'],'ordered_shutdown':audit['ordered_shutdown']})
  else:
   assert stage=='fault' and episode.relative_to(source)==Path('worker0/episode001_open_101')
   assert shutdown['worker_returncode']==-9 and shutdown['forced_shutdown'] is True and shutdown['failed_sample'] is True
   assert audit['transitions']['transition_count']==4 and audit['ordered_shutdown']['proven'] is False
   assert not(episode/'summary.json').exists() and not(episode/'native_stop.json').exists()
   episodes.append({'epoch':audit['epoch'],'directory':str(episode.relative_to(root)),
     'complete_episode_credit':False,'normal_native_shutdown_credit':False,'complete_contact_credit':False,
     'transitions':audit['transitions'],'protocol':audit['protocol'],'forced_owned_cleanup':True})
 target.mkdir(parents=True,exist_ok=True);assert not(target/'manifest.json').exists()
 prior={str(p.relative_to(root)):sha(p.read_bytes()) for p in target.rglob('*') if p.is_file()}
 files=copy_files(source,target)
 audit_dir=target/'audits';audit_dir.mkdir(exist_ok=False);audits=[]
 sources=[primary_path,scalar_path]
 if stage=='fault':sources.append(assets/'fault_w0_e1_v7_contact_phase_v3_audit.json')
 for path in sources:
  selected=audit_dir/path.name
  with selected.open('xb') as output:output.write(path.read_bytes())
  audits.append({'original':reference(path),'selected':reference(selected),'encoding':'identity'})
 review={'schema':'mr3-p1c-independent-v7-native-review-v1','passed_declared_audits':True,'source_freeze':freeze,
  'scope':'Complete closed v7 scripted engineering probe; no new native execution, policy training, SDK fix, network or 95% success credit. Fault killed prefix retains incomplete scope.',
  'binding':reference(assets/'predeclared_execution_binding_v7.json'),'primary_audit':reference(primary_path),'scalar_audit':reference(scalar_path),
  'returned_API_transitions':summary['valid_transitions'],'complete_episode_count':primary['complete_episode_count'],
  'wall_sec_including_all_attempts':summary['wall_sec_including_all_attempts'],
  'all_metadata_freeze_profile_matches_binding':True,'all_owned_final_live_and_zombie_sets_empty':True,
  'episodes':episodes,'prior_files_retained_without_overwrite':prior,
  'contact_scope':'Frozen latch/paused release proof; numeric task-only gap maxima and individual compact time endpoints not saved.',
  'archive_tool':{'path':str(Path(__file__)),'sha256':sha(Path(__file__).read_bytes())}}
 rp=target/'independent_review.json';write_new(rp,review)
 for item in episodes:
  episode=root/item['directory'];relative=episode.relative_to(source);mp=target/relative/'manifest.json'
  ef=[f for f in files if f['original'].startswith(str(episode.relative_to(root))+'/')]
  if mp.exists():
   previous=json.loads(mp.read_text())
   assert {(f['original'],f['original_sha256'],f['selected_sha256']) for f in previous['files']}=={(f['original'],f['original_sha256'],f['selected_sha256']) for f in ef}
  else:
   write_new(mp,{'schema':'mr3-selected-native-evidence-manifest-v1','source_freeze':freeze,
    'scope':'Closed v7 episode original artifacts; incomplete fault prefix never receives full episode/normal exit/contact credit.',
    'original_root':str(episode.relative_to(root)),'selected_root':str((target/relative).relative_to(root)),
    'originals_modified':False,'original_file_count':len(ef),'selected_artifact_count':len({f['selected'] for f in ef}),
    'files':ef,'complete_episode_credit':item['complete_episode_credit'],'primary_audit':reference(primary_path)})
 manifest={'schema':'mr3-selected-native-evidence-manifest-v1','scope':'Complete closed v7 stage including final resources and benchmark/worker summaries. CSV byte-identical, JSONL/log gzip; derivative reviews/audits separate.',
  'source_freeze':freeze,'original_root':str(source.relative_to(root)),'selected_root':str(target.relative_to(root)),
  'originals_modified':False,'original_file_count':len(files),'selected_artifact_count':len({f['selected'] for f in files}),
  'files':files,'independent_review':reference(rp),'audits_copied_losslessly':audits}
 mp=target/'manifest.json';write_new(mp,manifest);verify_files(files)
 for name,digest in prior.items():assert sha((root/name).read_bytes())==digest
 print(json.dumps({'stage':stage,'passed_declared_audits':True,'returned_API':summary['valid_transitions'],
  'complete_episodes':primary['complete_episode_count'],'original_files':len(files),
  'selected_artifacts':manifest['selected_artifact_count'],'manifest_sha256':sha(mp.read_bytes()),'review_sha256':sha(rp.read_bytes())}))
def main():
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('clock','pilot','terminal','workers1','workers2','workers4','fault','deadline'))
 parser.add_argument('--freeze',required=True);args=parser.parse_args()
 global freeze
 freeze=args.freeze;binding=binding_guard(freeze)
 if args.stage=='clock':archive_clock(binding)
 else:archive_team(args.stage,binding)
if __name__=='__main__':main()
