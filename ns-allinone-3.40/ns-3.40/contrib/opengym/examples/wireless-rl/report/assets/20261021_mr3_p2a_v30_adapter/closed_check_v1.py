"""Metadata-only CPU closure; never executes a scan or simulator."""
import hashlib,json,re,subprocess
from pathlib import Path
A=Path(__file__).resolve().parent
R=next(p for p in A.parents if (p/'.git').exists())
W=A.parents[2]
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def check_record(v):
 p=Path(v['path']);assert sha(p)==v['sha256'],p
 if 'bytes' in v: assert p.stat().st_size==v['bytes'],p
saved={}
def visit(v):
 if isinstance(v,dict):
  if type(v.get('pid')) is int and type(v.get('start_ticks')) is int:saved[v['pid'],v['start_ticks']]=v
  for x in v.values():visit(x)
 elif isinstance(v,list):
  for x in v:visit(x)
checks=[]
for p in sorted((A/'checks').glob('*/actual_wait.json')):
 v=read(p);visit(v)
 assert v['scope']=='cpu' and v['actual_waited'] and v['source_unchanged'] and v['source_before']==v['source_after'],p
 fail=p.parent.name=='integration_cpu_v1'
 assert v['actual_returncode']==(1 if fail else 0) and v['passed'] is (not fail),p
 check_record(v['console']);checks.append({'path':str(p),'passed':v['passed'],'seconds':v['actual_child_wait_seconds']})
for version in (1,2):
 p=A/f'attempts/adapter_v{version}/build_receipt_v1.json';v=read(p);visit(v)
 assert v['passed'] and v['source_unchanged'] and v['source_before']==v['source_after']
 for phase in v['phases']:
  assert phase['actual_waited'] and phase['returncode']==0 and not phase['signals'] and not phase['identity_capture_error'] and not phase['reap_overrun']
  check_record(phase['stdout']);check_record(phase['stderr'])
 check_record(v['binary'])
 if version==2:
  for row in v['source_after']:check_record(row)
 else:
  for row in v['source_after']:
   p=A/'source_v1'/Path(row['path']).name
   if p.exists():assert sha(p)==row['sha256']
for p in (A/'attempts').rglob('*result*.json'):visit(read(p))
for (pid,ticks),v in saved.items():
 p=Path(f'/proc/{pid}/stat')
 if p.exists():assert int(p.read_text().rsplit(')',1)[1].split()[19])!=ticks,v
B=A.parent/'20261021_mr3_p2a_v31_karto_behavior'
for name in ('karto_profile','karto_behavior'):
 v=read(B/(name+'_plan_v1.json'))
 for relative,digest in v['source_bindings'].items():assert sha(R/relative)==digest,relative
 assert v['mapper']=='karto' and not v['training_eligible'] and v['engineering_block_seconds']==4500
for item in read(B/'native_manifest_v1.json')['artifacts']:check_record(item)
baseline='b407f40e881657746b861f92614f14de88e9089b'
old=json.loads(subprocess.check_output(['git','show',baseline+':'+str((W/'report/ARCHIVE_INDEX.json').relative_to(R))],cwd=R))
new=read(W/'report/ARCHIVE_INDEX.json')
assert all(new[k]==v for k,v in old.items())
oldlog=subprocess.check_output(['git','show',baseline+':'+str((W/'log.md').relative_to(R))],cwd=R)
assert (W/'log.md').read_bytes().startswith(oldlog)
docs=[R/'AGENTS.md',W/'AGENTS.md',W/'RESEARCH_PLAN.md',W/'IMPLEMENTATION_PLAN.md',W/'report/README.md',W/'report/20261021_mr3_p2a_v30_adapter.md',W/'report/20261021_mr3_p2a_v31_karto_behavior.md',W/'report/20261020_mr3_p2a_assessment_handoff.md']
count=0
for doc in docs:
 for link in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
  target=link.split('#')[0]
  if not target or '://' in target:continue
  assert (doc.parent/target).exists(),(doc,target)
  count+=1
files=[{'path':str(p.relative_to(A)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(A.rglob('*')) if p.is_file() and p.name not in ('static_result_v1.json','closed_check_v1.py')]
result=dict(passed=True,checks=checks,saved_identity_count=len(saved),saved_identities=list(saved.values()),all_saved_absent=True,relative_links=count,files=files,new_engineering_seconds='0',qualification=False,training_eligible=False)
with (A/'static_result_v1.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({'passed':True,'saved_identities_gone':len(saved),'links':count,'files':len(files)}))
