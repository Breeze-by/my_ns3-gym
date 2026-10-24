"""Bounded independent review of V73 installed source and CPU artifacts only."""
from pathlib import Path
from decimal import Decimal
import ast,hashlib,json,os,re,stat
ROOT=Path('/home/zhuyulab/ns3-workspace');W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261024_mr3_p2a_v73_command_chain_description'
PREP=Path('/tmp/mr3_p2a_v73_root_preparation_v1');HERE=Path(__file__).resolve().parent
PRIVATE=Path('/tmp/mr3_p2a_v73_command_chain_candidate_v2')
FORBIDDEN=ROOT/'ros2_ws/ros2-multi-robot-automap/log';FIELDS=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
refs={}
def need(x,m):
 if not x:raise ValueError(m)
def read(p):
 p=Path(p);need(not p.is_relative_to(FORBIDDEN),'no original native/scientific path is admitted')
 need(p.is_absolute() and p.resolve(strict=True)==p,'regular resolved file required')
 a=p.lstat();need(stat.S_ISREG(a.st_mode),'link/special file rejected');raw=p.read_bytes();b=p.lstat()
 need(tuple(getattr(a,k) for k in FIELDS)==tuple(getattr(b,k) for k in FIELDS),'file changed')
 row=dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest());need(str(p) not in refs or refs[str(p)]==row,'repeated bytes changed');refs[str(p)]=row
 return raw,a
def load(p):return json.loads(read(p)[0])
def gone(saved):
 need(type(saved) is dict and all(type(saved.get(k)) is int and saved[k]>0 for k in ('pid','start_ticks')),'typed saved identity required')
 try:tail=(Path('/proc')/str(saved['pid'])/'stat').read_text().rsplit(')',1)[1].split()
 except (FileNotFoundError,ProcessLookupError):return True
 need(len(tail)>=20,'malformed saved identity observation');return int(tail[19])!=saved['start_ticks']
def main():
 proof=load(PREP/'canonical_CPU_postreap_proof_v1.json');wait=load(PREP/'canonical_cpu_v1/actual_wait.json');recovery=load(PREP/'canonical_cpu_source_recovery_v1.json')
 obj=proof['actual_tool_objects'];need(obj['initial']['session_id']==17796 and type(obj['final']['exit_code']) is int and obj['final']['exit_code']==0 and obj['final'].get('session_id') is None,'actual Root return differs')
 need(proof['actual_tests']==17 and proof['consumer_tests']==13 and proof['parent_tests']==4 and proof['bound_source_count']==97,'actual original scope differs')
 need(wait['schema']=='mr3-reach-outer-actual-wait-v1' and wait['scope']=='cpu' and wait['actual_waited'] is True and wait['actual_returncode']==0 and wait['passed'] is True and wait['errors']==[],'actual CPU receipt did not pass')
 need(wait['source_unchanged'] is True and wait['source_before']==wait['source_after'] and len(wait['source_before'])==97,'actual source before/after scope differs')
 need(Decimal(wait['actual_child_wait_seconds'])==Decimal(wait['ended_monotonic_ns']-wait['started_monotonic_ns'])/10**9==Decimal('4.140205043'),'CPU actual interval differs')
 saved={x['path']:x for x in recovery['sources']};need(len(saved)==97 and set(saved)=={x['path'] for x in wait['source_before']},'recovery scope differs')
 for row in wait['source_before']:
  raw,s=read(row['path']);need(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'] and [getattr(s,k) for k in FIELDS]==row['stat'],'current CPU source differs')
  x=saved[row['path']];need((x['bytes'],x['sha256'])==(row['bytes'],row['sha256']),'recovery pin differs');need(read(x['recovery_path'])[0]==raw,'restored source bytes differ')
 identities=[];roles={x['role']:x for x in proof['saved_CPU_identities']};need(set(roles)=={'coordinator_identity','child_identity'},'saved CPU role set differs')
 for role in roles:
  s=wait[role];need(roles[role]['saved']==s and roles[role]['freshgone'] is True and gone(s),'saved CPU still present or differs');identities.append(dict(role=role,saved=s,freshgone=True))
 console=read(PREP/'canonical_cpu_v1/console.log')[0].decode();need(re.findall(r'Ran (\d+) tests in ',console)==['17'] and console.rstrip().endswith('OK'),'not17 actual passing cases')
 need(console.count('(test_describe_motion_chain_v1.MotionDescriptionTests)')==13 and console.count('(test_parent_v1.ParentBoundaryTests)')==4,'13+4 actual case partition differs')
 for name in ('describe_motion_chain_v1.py','test_describe_motion_chain_v1.py','run_fixture_cpu_v1.py'):need(read(A/name)[0]==read(PRIVATE/name)[0],'installed consumer/test/runner differs from sealedv2')
 parent=read(A/'run_description_v1.py')[0];need(len(parent)==21016 and hashlib.sha256(parent).hexdigest()=='8ffbe87dc8ef5e44de9e3615f74a93a7d5f69dc3083d2db5e5d13311a3e15915','installed parent differs')
 parentmanifest=load('/tmp/mr3_p2a_v73_description_parent_candidate_v2/copy_ready_manifest_v2.json')
 for row in parentmanifest['source_files']:
  if Path(row['canonical_path']).suffix=='.py' or Path(row['canonical_path']).name=='previous_ledger_fixture_v1.json':
   raw,_=read(row['canonical_path']);need(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'installed parent fixture/test differs')
 sr,sstat=read(A/'description_spec_v1.json');spec=json.loads(sr);private=load(PRIVATE/'description_spec_draft_v1.json')
 delta=sorted(k for k in set(spec)|set(private) if spec.get(k)!=private.get(k));need(delta==['admitted','status'] and spec['admitted'] is True,'actual spec changes beyond Root admission/status')
 blob=load(A/'source_blob_manifest_v1.json');expected={ROOT/x['path']:x['sha256'] for x in spec['source_bindings']}
 need(len(expected)==21 and blob['interpretation_and_consumer_count']==21,'actual interpretation scope differs')
 expected[A/'description_spec_v1.json']=hashlib.sha256(sr).hexdigest();expected[A/'run_description_v1.py']=hashlib.sha256(parent).hexdigest()
 for key in ('inventory','previous_accounting','fixed_input_reference'):
  row=spec[key];raw,_=read(row['path']);need((len(raw),hashlib.sha256(raw).hexdigest())==(row['bytes'],row['sha256']),'fixed metadata pin changed');expected[Path(row['path'])]=row['sha256']
 need(len(expected)==26 and blob['source_bindings']=={str(p.relative_to(ROOT)):h for p,h in expected.items()},'runtime26 differs from reviewed parent expected equation')
 need({x['path'] for x in spec['inputs']}.isdisjoint(map(str,expected)),'actual motion included as source')
 for path,h in expected.items():need(hashlib.sha256(read(path)[0]).hexdigest()==h,'runtime current SHA differs')
 ledger=load(spec['previous_accounting']['path']);fixed=load(spec['fixed_input_reference']['path'])
 need(ledger['execution_freeze']=='74c8f710114bac3c2c91a5a1df8ebc6c63ec7637' and ledger['activity_passed'] is True and ledger['description_passed'] is True and ledger['original_activity_execution_freeze']=='b3707dcf258c832f35ef60f47a5dc8dc52296629' and ledger['original_activity_passed']=={'present':True,'value':False} and ledger['scientific_qualification_credit'] is False,'previous description/native activity mixed')
 need(fixed['schema']=='mr3-v73-fixed-input-references-from-actual-v71-archive-v1' and fixed['inventory']==spec['inventory'],'fixed original reference differs')
 need([(x['original_path'],x['original_bytes'],x['original_sha256']) for x in fixed['inputs']]==[(x['path'],x['expected_bytes'],x['expected_sha256']) for x in spec['inputs']],'input reference relation differs')
 result=dict(schema='mr3-v73-independent-canonical-CPU-runtime-review-v1',passed=True,actual_Root_session=17796,actual_cases=17,consumer_cases=13,parent_cases=4,actual_child_wait_seconds=wait['actual_child_wait_seconds'],original_CPU_source_count=97,source_before_after_current_equal=True,all_recovery_bytes_equal=True,saved_CPU_identities=identities,installed_consumer_parent_tests_equal_sealed_candidates=True,spec_only_forward_fields=delta,runtime_source_count=26,runtime_set_equal_reviewed_parent_expected=True,original_motion_excluded_from_source_and_all_reads=True,previous_description_G_separate_from_native_evidence_G=True,consumer_main_tests_or_World_run_by_this_review=False,original_raw_or_old342_read=False,new_scientific_or_capacity_credit=False,Git_or_INDEX_freeze_claimed=False,engineering_added_seconds='0',checked_file_bindings=list(refs.values()))
 (HERE/'review_v1.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checked_file_bindings'}))
if __name__=='__main__':main()
