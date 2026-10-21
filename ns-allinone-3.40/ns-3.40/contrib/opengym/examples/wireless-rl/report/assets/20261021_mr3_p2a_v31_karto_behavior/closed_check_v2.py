"""Post-closure metadata/byte checks only; no mapper or episode execution."""
from decimal import Decimal
import hashlib,json,re,subprocess
from pathlib import Path
A=Path(__file__).resolve().parent
R=next(p for p in A.parents if (p/'.git').exists());W=A.parents[2]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'closed_metadata_v1.json');assert m['passed'] and m['all_saved_absent'] and m['saved_identity_count']==36
for rel,v in m['canonical_files'].items():
 p=A/'closed_execution'/rel;assert p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],p
for who in m['saved_identities']:
 p=Path(f"/proc/{who['pid']}/stat")
 if p.exists():assert int(p.read_text().rsplit(')',1)[1].split()[19])!=who['start_ticks']
assert sum(Decimal(x['seconds']) for x in m['actual_outer_intervals'])==Decimal(m['engineering_actual_union_seconds'])==Decimal('1243.989041707')
assert Decimal(m['engineering_charge_seconds'])==Decimal(m['engineering_actual_union_seconds'])+2
assert Decimal(m['engineering_cumulative_seconds'])+Decimal(m['engineering_remaining_seconds'])==52000
assert Decimal(m['engineering_cumulative_seconds'])==Decimal('45445.4237026666018')+Decimal(m['engineering_charge_seconds'])
for kind,steps,actors in (('karto_profile',8,9),('karto_behavior',900,903)):
 root=A/'closed_execution'/(kind+'_v1');s=read(root/'capacity_summary.json');a=read(root/'independent_audit.json');v=read(root/'activity_result.json')
 assert v['passed'] and v['source_unchanged'] and not v['errors']
 assert s['step_attempts']==s['step_returns']==steps and s['step_errors']==0
 assert a['passed'] and a['bound_bytes_unchanged'] and not a['errors']
 assert a['verified_action_count']==a['verified_uniform_action_count']==a['verified_step_return_count']==steps and a['verified_actor_record_count']==actors
 for rel,digest in s['source_bindings'].items():
  raw=(R/rel).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest and raw==subprocess.check_output(['git','show',m['freeze']+':'+rel],cwd=R),rel
for x in read(A/'native_manifest_v1.json')['artifacts']:assert sha(Path(x['path']))==x['sha256']
b=read(A/'closed_execution/karto_behavior_v1/behavior_report.json');assert b['passed'] and not b['proxy_task_success'] and b['bound_bytes_unchanged']
for ep in b['episodes']:
 t=ep['terminal_assessment'];assert ep['passed'] and t['full_task_terminal'] and t['reason']=='timeout' and t['elapsed_ns']==300000000000 and not t['unsafe_observed']
 assert ep['final_metrics']['proxy_contact_events']==0 and ep['backend_closure']['navigation_closed']
f=read(A/'forensic_result_v1.json');assert f['passed'] and sum(len(e['selected']) for e in f['episodes'])==9
for rel,v in f['source_files'].items():assert sha(Path(rel))==v['sha256'] and Path(rel).stat().st_size==v['bytes']
old=json.loads(subprocess.check_output(['git','show',m['freeze']+':'+str((W/'report/ARCHIVE_INDEX.json').relative_to(R))],cwd=R));new=read(W/'report/ARCHIVE_INDEX.json')
assert all(new[k]==v for k,v in old.items() if k!='mr3_p2a_v31_karto_behavior_20261021')
assert (W/'log.md').read_bytes().startswith(subprocess.check_output(['git','show',m['freeze']+':'+str((W/'log.md').relative_to(R))],cwd=R))
links=0
for p in (R/'AGENTS.md',W/'AGENTS.md',W/'RESEARCH_PLAN.md',W/'IMPLEMENTATION_PLAN.md',W/'report/README.md',W/'report/20261020_mr3_p2a_assessment_handoff.md',W/'report/20261021_mr3_p2a_v31_karto_behavior.md',W/'report/20261021_mr3_p2a_v32_seed_certificate.md',R/'ros2_ws/ros2-multi-robot-automap/AGENTS.md',R/'ros2_ws/ros2-multi-robot-automap/launch_commands.md',R/'ros2_ws/ros2-multi-robot-automap/user_guide.md'):
 for url in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  url=url.split('#')[0]
  if not url or '://' in url:continue
  assert (p.parent/url).exists(),(p,url)
  links+=1
result=dict(passed=True,canonical_files=len(m['canonical_files']),saved_identities_gone=36,relative_links=links,engineering_used=m['engineering_cumulative_seconds'],engineering_remaining=m['engineering_remaining_seconds'],new_engineering_seconds='0',qualification=False)
with (A/'static_result_v2.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(result))
