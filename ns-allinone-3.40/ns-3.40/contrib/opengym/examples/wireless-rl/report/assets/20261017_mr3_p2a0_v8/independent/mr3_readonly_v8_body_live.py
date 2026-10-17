"""Read-only finite sampled raw body monitoring; all results partial, no acceptance."""
import hashlib, importlib.util, json, math, sys, time
from pathlib import Path
ROOT=Path('/home/zhuyulab/ns3-workspace')
ANGULAR=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_independent_angular_interface_v1.py'
assert hashlib.sha256(ANGULAR.read_bytes()).hexdigest()=='7a472ba7efdd55addc710b98c66c89feff7f5092f214f76fd76cd4ca526343d0'
spec=importlib.util.spec_from_file_location('fixed_angular_body_live',ANGULAR); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
SETTLED=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v8/independent/mr3_independent_settled_turn_v3.py'
assert hashlib.sha256(SETTLED.read_bytes()).hexdigest()=='c43fadbb74bef948f14c39e74fefb64fc9103b45191f593b8c089a63127b0a69'
settled_spec=importlib.util.spec_from_file_location('fixed_settled_live',SETTLED); settled=importlib.util.module_from_spec(settled_spec);settled_spec.loader.exec_module(settled)
run=Path(sys.argv[1]);output=Path(sys.argv[2]); result={'schema':'mr3-v8-partial-body-raw-monitor-v1','freeze':'d41485dfd93797026316806916e127eb5101f3b8','run':str(run),'wall_monotonic_ns':time.monotonic_ns(),'episodes':[],'scope':'Read-only partial prefixes; missing coverage/pending cleanup are not failures or acceptance. Actual observed hard-bound violations are alerts. Frozen full consumers required after closure.'}
def rows(path):
 if not path.exists():return [],None
 b=path.read_bytes(); lines=b.splitlines(); complete=b.endswith(b'\n') or not b
 if not complete:lines=lines[:-1]
 return [json.loads(x) for x in lines if x.strip()],{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'complete_final_record':complete}
for ep in sorted(run.glob('worker*/episode*')):
 r={'directory':str(ep),'inputs':{},'robots':{},'alerts':[]};result['episodes'].append(r)
 try:
  ts,r['inputs']['transitions.jsonl']=rows(ep/'transitions.jsonl'); phy,r['inputs']['physics.jsonl']=rows(ep/'physics.jsonl'); motion,r['inputs']['motion_safety.jsonl']=rows(ep/'motion_safety.jsonl')
  if not ts:r['stage']='startup before returned reset';continue
  meta=json.loads((ep/'metadata.json').read_bytes());assert meta['freeze']==result['freeze']
  release=ts[0]['info']['release_time_ns']; end=phy[-1]['end_time_ns'] if phy else release;r.update(release_time_ns=release,physics_end_ns=end,returned_records=len(ts),closed=(ep/'supervisor_shutdown.json').exists(),epoch=meta['epoch'])
  for name in mod.ROBOTS:
   own=[(i,row) for i,row in enumerate(motion,1) if row['kind']=='own_odom' and row['payload']['robot']==name]
   ang=mod.robot_audit(own,name,release,end); task=[];seen={}
   for line,row in own:
    m=row['payload']['message'];stamp=mod.source_ns(m)
    if not release<=stamp<=end:continue
    if stamp in seen:continue
    seen[stamp]=True;v=m['twist']['twist']['linear']; speed=math.hypot(v['x'],v['y']);task.append((speed,line,row))
   peak=max(task,key=lambda x:x[0],default=None)
   rr={'raw_own_odom_records':len(own),'task_unique_own_odom':len(task),'maximum_planar_speed':peak[0] if peak else None,'planar_peak_original':peak[2] if peak else None,'frozen_angular':ang}
   actual=[row['payload']['twist'] for row in motion if row['kind']=='actual_cmd_vel' and row['payload']['robot']==name]
   rr['maximum_observed_actual_abs_v']=max((abs(x['linear']['x'])for x in actual),default=None);rr['maximum_observed_actual_abs_w']=max((abs(x['angular']['z'])for x in actual),default=None)
   if peak and peak[0]>.30:r['alerts'].append({'robot':name,'kind':'raw_planar_speed_gt_0.30','maximum':peak[0]})
   for key in ('errors','bound_violations'):
    if ang.get(key):r['alerts'].append({'robot':name,'kind':'frozen_angular_'+key,'value':ang[key]})
   r['robots'][name]=rr
  r['settled_intervals']=[]
  for row in motion:
   if row['kind']=='settled_turn_model_failure':r['alerts'].append({'kind':'production_settled_turn_model_failure','original':row})
  for name in mod.ROBOTS:
   native,r['inputs']['drive_'+name+'.jsonl']=rows(ep/('drive_'+name+'.jsonl'))
   receipts=[row for row in native if row['kind']=='command_received']
   raw_own=[settled.odom_sample(row,index)for index,row in enumerate(motion,1)if row['kind']=='own_odom' and row['payload']['robot']==name]
   dedup=[]
   for sample in raw_own:
    if dedup and sample['source_ns']==dedup[-1]['source_ns']:continue
    dedup.append(sample)
   seen_segments=set()
   for row in motion:
    if row['kind']!='decision' or row['payload']['robot']!=name:continue
    payload=row['payload']
    if settled.rotation_decision(payload['decision'])is None:continue
    sequence=payload['decision_sequence']; current=next((x for x in receipts if x['target_decision_sequence']==sequence),None)
    if current is None:continue
    prior_nonzero=[x for x in receipts if x['record_sequence']<current['record_sequence'] and x['desired_v']!=0.]
    segment=prior_nonzero[-1]['record_sequence']if prior_nonzero else 0
    if segment in seen_segments:continue
    seen_segments.add(segment)
    certificate=payload['own_state']['settled_turn']; anchor_ns=certificate['samples'][-1]['source_ns']; anchor=next(x for x in dedup if x['source_ns']==anchor_ns)
    future_nonzero=[x for x in receipts if x['record_sequence']>current['record_sequence']and x['desired_v']!=0.]
    stop=min(end,future_nonzero[0]['sim_time_ns'])if future_nonzero else end
    previous=anchor;path=0.;maximum=anchor['planar_speed_mps'];chord_max=0.;interval_errors=[];count=0
    for sample in dedup:
     if not anchor_ns<sample['source_ns']<=stop:continue
     gap=sample['source_ns']-previous['source_ns'];chord=math.hypot(sample['position_xy'][0]-previous['position_xy'][0],sample['position_xy'][1]-previous['position_xy'][1]);chord_speed=chord/(gap/1e9)if gap>0 else float('inf');path+=chord;maximum=max(maximum,sample['planar_speed_mps']);chord_max=max(chord_max,chord_speed);count+=1
     if sample['planar_speed_mps']>.01:interval_errors.append({'kind':'planar_speed','source_ns':sample['source_ns'],'value':sample['planar_speed_mps']})
     if chord_speed>.01:interval_errors.append({'kind':'chord_speed','source_ns':sample['source_ns'],'value':chord_speed})
     if path>settled.OWN_RESERVE:interval_errors.append({'kind':'whole_segment_path','source_ns':sample['source_ns'],'value':path})
     if not 0<gap<=100000000:interval_errors.append({'kind':'source_gap','source_ns':sample['source_ns'],'value':gap})
     previous=sample
    interval={'robot':name,'first_grant_sequence':sequence,'first_grant_clock_ns':payload['clock_ns'],'anchor_source_ns':anchor_ns,'latest_cut_physics_end_ns':stop,'complete_raw_sources':count,'maximum_full_planar_speed':maximum,'maximum_adjacent_chord_speed':chord_max,'whole_segment_sampled_odom_path_m':path,'errors':interval_errors,'complete_interval':bool(future_nonzero)or r['closed']}
    r['settled_intervals'].append(interval)
    if interval_errors:r['alerts'].append({'kind':'observed_settled_turn_model_violation','robot':name,'interval':interval})
 except Exception as e:r['diagnostic_error']=repr(e)
with output.open('x')as stream:stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'output':str(output),'episodes':[{'directory':e['directory'],'returned_records':e.get('returned_records'),'closed':e.get('closed'),'alerts':e.get('alerts'),'diagnostic_error':e.get('diagnostic_error'),'max_planar':{n:v.get('maximum_planar_speed')for n,v in e.get('robots',{}).items()}}for e in result['episodes']]}))
