"""Post-wait metadata/byte archive only, no replay or new experiment."""
import hashlib,json,shutil,time
from pathlib import Path
from decimal import Decimal
R=Path('/home/zhuyulab/ns3-workspace')
W=R/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261021_mr3_p2a_v31_karto_behavior'
O=A/'closed_execution';O.mkdir(exist_ok=False)
saved={}
def visit(x):
 if isinstance(x,dict):
  if type(x.get('pid')) is int and type(x.get('start_ticks')) is int:saved[x['pid'],x['start_ticks']]=x
  for v in x.values():visit(v)
 elif isinstance(x,list):
  for v in x:visit(v)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
intervals=[];rows=[]
for role in ('profile','behavior'):
 run=R/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v31'/('karto_'+role+'_v1')
 shutil.copytree(run,O/('karto_'+role+'_v1'))
 for tail in ('outer','final_outer'):
  path=Path('/tmp/mr3_p2a_v31_'+role+'_'+tail)
  v=read(path/'actual_wait.json');assert v['scope']=='engineering' and v['actual_waited'] and v['source_unchanged'] and not v['errors']
  start,end=v['started_monotonic_ns'],v['ended_monotonic_ns'];assert end>start
  assert Decimal(v['actual_child_wait_seconds'])==Decimal(end-start)/10**9
  intervals.append((start,end));rows.append({'role':role+'_'+tail,'interval_ns':[start,end],'seconds':v['actual_child_wait_seconds'],'passed':v['passed']})
  shutil.copytree(path,O/(role+'_'+tail));visit(v)
 final=Path('/tmp/mr3_p2a_v31_'+role+'_final.json');shutil.copyfile(final,O/final.name)
 assert read(final)['absence_passed'] is True
 for p in run.rglob('*.json'):visit(read(p))
 for p in (O/(role+'_final_outer')).glob('*.json'):visit(read(p))
for suffix in ('forensic_outer','forensic_outer_v2'):
 path=Path('/tmp/mr3_p2a_v31_'+suffix)
 v=read(path/'actual_wait.json');assert v['scope']=='engineering' and v['actual_waited'] and v['source_unchanged'] and not v['errors']
 start,end=v['started_monotonic_ns'],v['ended_monotonic_ns']
 assert Decimal(v['actual_child_wait_seconds'])==Decimal(end-start)/10**9
 intervals.append((start,end));rows.append({'role':suffix,'interval_ns':[start,end],'seconds':v['actual_child_wait_seconds'],'passed':v['passed']})
 shutil.copytree(path,O/suffix);visit(v)
visit(read(A/'forensic_result_v1.json'))
for (pid,ticks),v in saved.items():
 p=Path(f'/proc/{pid}/stat')
 if p.exists():assert int(p.read_text().rsplit(')',1)[1].split()[19])!=ticks,v
merged=[]
for start,end in sorted(intervals):
 if merged and start<=merged[-1][1]:merged[-1][1]=max(end,merged[-1][1])
 else:merged.append([start,end])
actual_union=Decimal(sum(end-start for start,end in merged))/10**9
charge=actual_union+Decimal(2)  # Conservative supplemental discovery charge, not a measured interval.
used=Decimal('45445.4237026666018')+charge
assert charge<=4500 and used<=52000
files={str(p.relative_to(O)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(O.rglob('*')) if p.is_file()}
result={'schema':'mr3-p2a-v31-closed-metadata-v1','passed':True,'freeze':'e7dc6903c0bb4c2fe09f0eb07266f46c9d259022','actual_outer_intervals':rows,'union_intervals_ns':merged,'engineering_actual_union_seconds':str(actual_union),'discovery_conservative_upper_charge_seconds':'2','engineering_charge_seconds':str(charge),'engineering_cumulative_seconds':str(used),'engineering_remaining_seconds':str(Decimal(52000)-used),'pilot_remaining_decisions':1870,'pilot_remaining_seconds':'2905.9547395464029','final_only_unused':[401,402,403],'saved_identity_count':len(saved),'saved_identities':list(saved.values()),'all_saved_absent':True,'canonical_files':files,'qualification':False,'training_eligible':False}
with (A/'closed_metadata_v1.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:result[k] for k in ('passed','engineering_charge_seconds','engineering_cumulative_seconds','engineering_remaining_seconds','saved_identity_count')}))
