"""Read-only finite sampled raw body monitoring; all results partial, no acceptance."""
import hashlib, importlib.util, json, math, sys, time
from pathlib import Path
ROOT=Path('/home/zhuyulab/ns3-workspace')
ANGULAR=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v4/independent/mr3_independent_angular_interface_v1.py'
assert hashlib.sha256(ANGULAR.read_bytes()).hexdigest()=='7a472ba7efdd55addc710b98c66c89feff7f5092f214f76fd76cd4ca526343d0'
spec=importlib.util.spec_from_file_location('fixed_angular_body_live',ANGULAR); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
run=Path(sys.argv[1]);output=Path(sys.argv[2]); result={'schema':'mr3-v7-partial-body-raw-monitor-v1','freeze':'01cfa040dcb73f8931dd11d66b69ce765cb8412f','run':str(run),'wall_monotonic_ns':time.monotonic_ns(),'episodes':[],'scope':'Read-only partial prefixes; missing coverage/pending cleanup are not failures or acceptance. Actual observed hard-bound violations are alerts. Frozen full consumers required after closure.'}
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
  meta=json.loads((ep/'metadata.json').read_bytes());assert meta['freeze_git_commit']==result['freeze'] if 'freeze_git_commit' in meta else True
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
 except Exception as e:r['diagnostic_error']=repr(e)
with output.open('x')as stream:stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'output':str(output),'episodes':[{'directory':e['directory'],'returned_records':e.get('returned_records'),'closed':e.get('closed'),'alerts':e.get('alerts'),'diagnostic_error':e.get('diagnostic_error'),'max_planar':{n:v.get('maximum_planar_speed')for n,v in e.get('robots',{}).items()}}for e in result['episodes']]}))
