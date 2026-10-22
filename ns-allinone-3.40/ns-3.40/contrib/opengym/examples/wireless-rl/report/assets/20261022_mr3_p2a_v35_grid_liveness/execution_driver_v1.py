from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path('/home/zhuyulab/ns3-workspace'); w=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'; a=w/'report/assets/20261022_mr3_p2a_v35_grid_liveness'; freeze='47dd6774e478bb714e1844e0056f2301269896a3'; scope=a/'scope_acceptance_v1.json'; s=json.loads(scope.read_text()); py='/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
def git(*args):return subprocess.check_output(['git',*args],cwd=root)
assert git('rev-parse','HEAD').decode().strip()==git('rev-parse','origin/main').decode().strip()==freeze
assert not git('status','--porcelain')
assert git('show',freeze+':'+str(scope.relative_to(root)))==scope.read_bytes()
sources=[]
for mapping in ('code_bindings','data_bindings'):
 for name,digest in s[mapping].items():
  raw=(root/name).read_bytes(); assert hashlib.sha256(raw).hexdigest()==digest and git('show',freeze+':'+name)==raw,name
  sources.append(root/name)
sources.append(scope)
env=dict(os.environ,PYTHONNOUSERSITE='1'); env.pop('PYTHONPATH',None)
main=Path('/tmp/mr3_p2a_v35_rooms_outer_v1'); mainresult=Path('/tmp/mr3_p2a_v35_rooms_forensic_v1.json'); tail=Path('/tmp/mr3_p2a_v35_rooms_final_v1.json'); final=Path('/tmp/mr3_p2a_v35_rooms_final_outer_v1')
command=[v.replace('{freeze}',freeze) for v in s['execution_argv_template']]
args=[py,'-B','-m','mr3_learning.reach_execution','--output',str(main),'--scope','engineering']
for src in sources:args+=['--source',str(src)]
main_status=subprocess.call([*args,'--',*command],cwd=w,env=env)
args=[py,'-B','-m','mr3_learning.reach_execution','--output',str(final),'--scope','engineering']
for src in [a/'forensic_final_v1.py',scope,main/'actual_wait.json',*([mainresult] if mainresult.exists() else [])]:args+=['--source',str(src)]
command=['/usr/bin/python3','-B',str(a/'forensic_final_v1.py'),'--outer',str(main/'actual_wait.json'),'--result',str(mainresult),'--scope',str(scope),'--freeze',freeze,'--output',str(tail)]
final_status=subprocess.call([*args,'--',*command],cwd=w,env=env)
print(json.dumps({'main_status':main_status,'final_status':final_status}))
raise SystemExit(0 if main_status==final_status==0 else 1)
