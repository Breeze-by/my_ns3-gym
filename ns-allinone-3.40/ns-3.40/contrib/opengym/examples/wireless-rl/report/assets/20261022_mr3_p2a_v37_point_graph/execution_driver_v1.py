import hashlib,json,os,subprocess,sys
from pathlib import Path
r=Path('/home/zhuyulab/ns3-workspace');w=r/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl';a=w/'report/assets/20261022_mr3_p2a_v37_point_graph';py='/home/zhuyulab/miniconda3/envs/ns3gym/bin/python';freeze='13e95f29fcc094b19c42fbdeb7d9a76644dee0e9'
def git(*args):return subprocess.check_output(['git','-C',str(r),*args])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert git('rev-parse','HEAD').decode().strip()==git('rev-parse','origin/main').decode().strip()==freeze
assert not git('status','--porcelain')
from decimal import Decimal
scope=json.loads((a/'scope_acceptance_v1.json').read_text());assert Decimal(scope['engineering_entry_used_seconds'])+2400<=52000
results=[]
env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1');env.pop('PYTHONPATH',None)
for kind,tag in [('point_graph_profile_v1','profile'),('point_graph_probe_v1','probe')]:
 assert not git('status','--porcelain')
 plan_path=a/(kind+'_plan_v1.json');plan=json.loads(plan_path.read_text())
 assert plan['start_graph_rule']=='point-attachment-3x3-v1' and plan['seed_rule']=='exact-point-bridge-v2'
 sources={r/name for name in plan['source_bindings']}|{plan_path,w/'MR3_ENV_CONTRACT.md'}
 for src in sorted(sources):
  rel=src.relative_to(r).as_posix();b=src.read_bytes();assert b==git('show',freeze+':'+rel)
  if rel in plan['source_bindings']:assert sha(src)==plan['source_bindings'][rel]
 sources.add(Path(__file__))
 main_path=Path('/tmp/mr3_p2a_v37_point_graph_'+tag+'_outer_v1')
 final_outer_path=Path('/tmp/mr3_p2a_v37_point_graph_'+tag+'_final_outer_v1')
 final_path=Path('/tmp/mr3_p2a_v37_point_graph_'+tag+'_final_v1.json')
 def wrapped(out,command):
  argv=[py,'-B','-m','mr3_learning.reach_execution','--output',str(out),'--scope','engineering']
  for src in sorted(sources):argv+=['--source',str(src)]
  return subprocess.run([*argv,'--',*command],cwd=w,env=env).returncode
 main_rc=wrapped(main_path,[py,'-B','-m','mr3_learning.proxy2d_seed_activity','execute','--freeze',freeze,'--kind',kind])
 final_rc=wrapped(final_outer_path,[py,'-B','-m','mr3_learning.proxy2d_seed_activity','final','--kind',kind,'--outer',str(main_path/'actual_wait.json'),'--output',str(final_path)])
 results.append({'kind':kind,'main_returncode':main_rc,'external_final_returncode':final_rc,'main_outer':str(main_path/'actual_wait.json'),'final_outer':str(final_outer_path/'actual_wait.json'),'external_final':str(final_path)})
 Path('/tmp/mr3_v37_execute_results.json').write_text(json.dumps(results,indent=2)+'\n')
 if main_rc or final_rc:
  print(json.dumps({'activity':kind,'main_returncode':main_rc,'final_returncode':final_rc,'next_activity_skipped':True}),flush=True)
  raise SystemExit(1)
 print(json.dumps({'activity':kind,'complete':True}),flush=True)
