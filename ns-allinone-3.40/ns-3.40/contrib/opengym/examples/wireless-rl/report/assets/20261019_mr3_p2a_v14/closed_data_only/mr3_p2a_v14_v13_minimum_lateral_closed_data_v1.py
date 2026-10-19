#!/usr/bin/python3
"""Pure closed-file statistics: no ROS, simulator, training or audit imports."""
import bisect,csv,hashlib,json,math,time
from pathlib import Path
ROOT=Path('/home/zhuyulab/ns3-workspace')
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
EP=ROS/'log/mr3_ppo/mr3_p2a_v13_minimal/native/round0000/worker0/episode001_open_101'
PREFIX=Path('/tmp/mr3_p2a_v14_v13_minimum_lateral_closed_data_v1')
OUT=PREFIX.with_suffix('.json');CSV=PREFIX.with_suffix('.csv');MD=PREFIX.with_suffix('.md')
def proof(p):
 b=p.read_bytes();s=p.stat();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'dev':s.st_dev,'inode':s.st_ino,'mtime_ns':s.st_mtime_ns}
def rows(p):
 with p.open() as f:
  for i,s in enumerate(f,1):yield {'line':i,'record':json.loads(s)}
def stamp(d):
 s=d['header']['stamp'];return s['sec']*10**9+s['nanosec']
def stat(samples,metric):
 good=[x for x in samples if x[metric] is not None]
 if not good:return {'count':0,'maximum':None,'mean':None,'over_0_01_count':0,'first_over_0_01':None,'peak':None}
 peak=max(good,key=lambda x:x[metric]);bad=[x for x in good if x[metric]>.01]
 return {'count':len(good),'maximum':peak[metric],'mean':sum(x[metric] for x in good)/len(good),'over_0_01_count':len(bad),'first_over_0_01':bad[0] if bad else None,'peak':peak}
def summary(samples):return {'samples':len(samples),**{k:stat(samples,k) for k in ['abs_body_vy_mps','planar_speed_mps','signed_sector_residual_mps']}}
started=time.monotonic_ns();assert not any(p.exists() for p in [OUT,CSV,MD])
inputs=[EP/n for n in ['metadata.json','summary.json','transitions.jsonl','physics.jsonl','round0000_w0_e1_e154087c.json']]
inputs += [EP/(kind+'_'+robot+'.jsonl') for robot in ['tb1','tb2','tb3'] for kind in ['drive','odometry']]
inputs += [EP/('drive_model_'+robot+'.sdf') for robot in ['tb1','tb2','tb3']]
cpp=ROS/'src/multi_robot/src/mr3_gazebo_diff_drive.cpp';inputs.append(cpp)
before={str(p):proof(p) for p in inputs}
metadata=json.loads((EP/'metadata.json').read_text());native=json.loads((EP/'summary.json').read_text());evaluation=json.loads((EP/'round0000_w0_e1_e154087c.json').read_text());trans=list(rows(EP/'transitions.jsonl'));reset=trans[0]['record'];last=trans[-1]['record']
release=reset['info']['release_time_ns'];declared_end=round(evaluation['end_sim_time_sec']*1e9);api_end=round(last['snapshot']['source_stamp']*1e9);physical_end=max(x['record']['end_time_ns'] for x in rows(EP/'physics.jsonl'))
assert release==round(evaluation['start_sim_time_sec']*1e9) and release<=declared_end<=api_end<=physical_end
windows={'declared_task_source_window':(release,declared_end),'through_terminal_api_physical_quantum':(release,api_end),'post_declared_end_through_native_close':(declared_end+1,physical_end)}
configs={};all_samples=[];selected={};unknown=[]
for robot in ['tb1','tb2','tb3']:
 drive=list(rows(EP/('drive_'+robot+'.jsonl')));odom=list(rows(EP/('odometry_'+robot+'.jsonl')));dc=drive[0]['record'];oc=odom[0]['record'];configs[robot]={'drive':dc,'odom':oc}
 assert dc['kind']=='configuration' and oc['kind']=='configuration' and dc['epoch']==metadata['epoch']==oc['epoch']
 assert oc['provider']=='WORLD' and oc['phase']=='world_update_begin_before_actuation' and oc['period_ns']==20000000
 assert oc['compiled_source_sha256']==before[str(cpp)]['sha256']==dc['compiled_source_sha256']
 actuations=[x for x in drive if x['record']['kind']=='actuation'];clocks=[x['record']['sim_time_ns'] for x in actuations]
 assert clocks==sorted(clocks) and len(clocks)==len(set(clocks))
 stored=[x for x in drive if x['record']['kind']=='command_received'];storeclocks=[x['record']['sim_time_ns'] for x in stored]
 assert storeclocks==sorted(storeclocks)
 command_by_seq={x['record']['cmd_seq']:x for x in stored};assert len(command_by_seq)==len(stored)
 for item in odom:
  d=item['record']
  if d['kind']!='publication':continue
  msg=d['odometry'];s=stamp(msg)
  if not release<=s<=physical_end:continue
  assert s==d['source_clock_ns']==d['sim_time_ns'] and d['epoch']==metadata['epoch'] and msg['header']['frame_id']=='odom' and msg['child_frame_id']=='base_footprint'
  tw=msg['twist']['twist'];vx=tw['linear']['x'];vy=tw['linear']['y'];vz=tw['linear']['z'];wz=tw['angular']['z'];assert all(math.isfinite(x) for x in [vx,vy,vz,wz])
  # WORLD odometry is published at update-begin before same-clock wheel writes.
  # Thus body measurement matches latest STRICTLY EARLIER actuation, not <=.
  ai=bisect.bisect_left(clocks,s)-1;act=actuations[ai] if ai>=0 else None;why=None
  if act is None:why='no strictly earlier actual actuation'
  elif ai+1<len(actuations) and actuations[ai+1]['record']['actuation_seq']!=act['record']['actuation_seq']+1:why='actuation sequence gap makes interval unknown'
  ar=act['record'] if act else None;command=command_by_seq.get(ar['cmd_seq']) if ar else None
  if not why and (command is None or command['line']>=act['line'] or any(command['record'][k]!=ar[k] for k in ['desired_v','desired_w','target_clock_ns','target_decision_sequence'])):why='actual consumed command reference missing or inconsistent'
  si=bisect.bisect_left(storeclocks,s)-1;store=stored[si] if si>=0 else None
  sameclock_store=[x['line'] for x in stored[bisect.bisect_left(storeclocks,s):bisect.bisect_right(storeclocks,s)]]
  target_v=ar['desired_v'] if not why else None;target_w=ar['desired_w'] if not why else None
  bucket='unknown' if why else ('actual_target_linear_zero' if target_v==0 else 'actual_target_linear_nonzero')
  wrong=None if why else (abs(vx) if target_v==0 else max(0.,-math.copysign(1.,target_v)*vx))
  residual=None if wrong is None else math.hypot(vy,wrong)
  vissued=sum(ar['applied_rim_mps'])/2 if not why else None
  row={'robot':robot,'source_ns':s,'odom_line':item['line'],'odom_record_sequence':d['record_sequence'],'vx_mps':vx,'vy_mps':vy,'vz_mps':vz,'wz_radps':wz,'abs_body_vy_mps':abs(vy),'planar_speed_mps':math.hypot(vx,vy),'unadmitted_longitudinal_mps':wrong,'signed_sector_residual_mps':residual,'actual_bucket':bucket,'actual_match_unknown_reason':why,'actuation_line':act['line'] if act else None,'actuation_source_ns':ar['sim_time_ns'] if ar else None,'actuation_age_ns':s-ar['sim_time_ns'] if ar else None,'actuation_seq':ar['actuation_seq'] if ar else None,'consumed_cmd_seq':ar['cmd_seq'] if ar else None,'actual_consumed_target_v':target_v,'actual_consumed_target_w':target_w,'actual_issued_center_v':vissued,'issued_center_bucket':('unknown' if why else ('issued_center_exact_zero' if vissued==0 else 'issued_center_nonzero')),'current_rim_mean':sum(ar['current_rim_mps'])/2 if not why else None,'storage_strict_before_line':store['line'] if store else None,'storage_strict_before_v':store['record']['desired_v'] if store else None,'storage_strict_before_w':store['record']['desired_w'] if store else None,'same_clock_storage_lines':sameclock_store,'same_clock_actuation_line_excluded':actuations[ai+1]['line'] if ai+1<len(actuations) and clocks[ai+1]==s else None}
  all_samples.append(row);selected[(robot,s)]={'odom':item,'latest_strict_before_actuation':act,'matching_stored_command':command,'latest_strict_before_storage':store}
  if why:unknown.append(row)
window_reports={};peaks={}
for name,(lo,hi) in windows.items():
 samples=sorted([x for x in all_samples if lo<=x['source_ns']<=hi],key=lambda x:(x['source_ns'],x['robot']))
 groups={}
 for robot in ['all','tb1','tb2','tb3']:
  rs=[x for x in samples if robot=='all' or x['robot']==robot]
  groups[robot]={'all_targets':summary(rs)}
  for bucket in ['actual_target_linear_zero','actual_target_linear_nonzero','unknown']:
   groups[robot][bucket]=summary([x for x in rs if x['actual_bucket']==bucket])
 window_reports[name]={'source_start_ns':lo,'source_end_ns':hi,'groups':groups}
 for robot,gs in groups.items():
  for bucket,st in gs.items():
   for metric in ['abs_body_vy_mps','planar_speed_mps','signed_sector_residual_mps']:
    x=st[metric]['peak']
    if x:peaks[x['robot']+':'+str(x['source_ns'])]=selected[(x['robot'],x['source_ns'])]
for p in inputs:assert before[str(p)]==proof(p),str(p)
with CSV.open('x',newline='') as f:
 fields=list(all_samples[0]);writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(all_samples)
normal=window_reports['declared_task_source_window']['groups']['all']['actual_target_linear_nonzero']
result={'schema':'mr3-v14-v13-minimum-closed-lateral-statistics-v1','scope':'Descriptive closed native producer data only, not formal audit, new simulation, future bound, science PASS or original FAIL relabel','runtime_freeze':metadata['freeze'],'episode':str(EP),'script':proof(Path(__file__)),'raw_source_bindings':list(before.values()),'raw_source_stat_sha_unchanged_after_read':True,'epoch':metadata['epoch'],'windows':window_reports,'window_basis':{'release_time_ns':release,'evaluator_declared_end_ns':declared_end,'final_step_snapshot_physical_end_ns':api_end,'native_physics_close_end_ns':physical_end,'final_step_dt':last['info']['dt'],'final_step_physical_dt':last['info']['physical_dt'],'explanation':'Declared evaluator end uses callback clock56.98; last API physically advanced to57.0 and native close to57.2. Source56.995 failure sample is outside first window but included in second/appendix. No violation is discarded or relabelled because of window labels.'},'producer_configs':configs,'matching_rule':'Latest actual wheel update with actuation.sim_time_ns STRICTLY LESS THAN odom source_ns, because configured/code order world_update_begin_before_actuation. Matching stored cmd_seq and desired_v/w/target refs must agree. Storage separately tracked; same-clock storage ordering is unknown and never used as the actual response target.','residual_definition':{'normal_nonzero':'r=(min(0,sign(target_v)*vx),vy) in norm; retains any measured forward component opposite the actual consumed target sign','zero_target':'full hypot(vx,vy); this includes normal finite braking/settling, so >.01 here is not by itself a settled-disk counterexample','lateral':'abs(raw body linear.y), not a world component and not3D norm','purpose':'Necessary observed samples for a candidate signed-sector+residual tube; does not prove heading-sector containment, continuum or future response.'},'unknown_matches':unknown,'selected_peak_full_raw':peaks,'all_sample_csv':proof(CSV),'observed_normal_in_declared_window':{'sample_count':normal['samples'],'max_abs_body_vy_mps':normal['abs_body_vy_mps']['maximum'],'abs_body_vy_above_0_01':normal['abs_body_vy_mps']['over_0_01_count'],'max_signed_sector_residual_mps':normal['signed_sector_residual_mps']['maximum'],'residual_above_0_01':normal['signed_sector_residual_mps']['over_0_01_count']},'limits':['20ms body samples,30Hz actual actuation;1ms physics receipts are not1ms body or contact-force observer data.','Native publication does not prove DDS or guard consumption; this task classifies physical producer samples only.','A sampled maximum below.01 cannot prove continuous/future side-slip tube or bound terminal accumulated motion.','Actual target linear-zero includes brake transient and is not synonymous with active settled qualification.','Target sign is not an established heading cone and the lateral statistic alone is insufficient for r when forward motion has unadmitted sign.','No runtime/control input,truth readback or source changes; all data remain isolated closed evidence.'],'started_monotonic_ns':started,'completed_monotonic_ns':time.monotonic_ns()}
result['wall_duration_sec']=(result['completed_monotonic_ns']-started)/1e9
with OUT.open('x') as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
text=f"""# V13 minimum body lateral/residual closed-data statistics

Native frozen0063, source-time windows: release{release/1e9}→declared end{declared_end/1e9}; final API physical end{api_end/1e9}; close{physical_end/1e9}. These endpoints remain separate.

Normal actual-consumed nonzero-linear target, declared task window: samples{normal['samples']}, max|body vy|={normal['abs_body_vy_mps']['maximum']}, count>.01={normal['abs_body_vy_mps']['over_0_01_count']}; max signed-sector residual norm={normal['signed_sector_residual_mps']['maximum']}, count>.01={normal['signed_sector_residual_mps']['over_0_01_count']}. Unknown matches{len(unknown)}.

Matching is latest STRICTLY EARLIER wheel actuation; same-clock WORLD odom is published before that clock's wheel write. Actual cmd_seq and original storage reference are checked. Latest storage is reported separately and is not an instantaneous physical response.

All3robot zero/nonzero/unknown summaries and full peak raw records are inJSON; every sample's source/odomline/actualupdate/consumedtag/issuedrimmean/bodycomponents is inCSV. Zero-target samples include finite brakes and are not automatically settled-model samples.

This is descriptive20ms native publication data, not1ms motion coverage, continuous side-slip proof, new science PASS or a repair. OriginalV13 FAIL remains.
"""
with MD.open('x') as f:f.write(text)
print(json.dumps({'output':proof(OUT),'csv':proof(CSV),'markdown':proof(MD),'normal_observed':result['observed_normal_in_declared_window'],'unknown_matches':len(unknown),'internal_wall_sec':result['wall_duration_sec']},sort_keys=True))
