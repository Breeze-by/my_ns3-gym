from pathlib import Path
import os,subprocess,json,hashlib
r=Path('/home/zhuyulab/ns3-workspace');w=r/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl';a=w/'report/assets/20261022_mr3_p2a_v38_protocol_cpu';scope_path=a/'scope_acceptance_v1.json';py='/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
def git(*argv):return subprocess.check_output(['git','-C',str(r),*argv])
freeze=git('rev-parse','HEAD').decode().strip();assert freeze.startswith('a44e1b844') and git('rev-parse','origin/main').decode().strip()==freeze;assert not git('status','--porcelain')
scope=json.loads(scope_path.read_text());sources={scope_path}
for rel,digest in {**scope['source_bindings'],**scope['data_bindings']}.items():
 p=r/rel;raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest and git('show',freeze+':'+rel)==raw;sources.add(p)
sources.add(Path(__file__))
env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1');env.pop('PYTHONPATH',None)
def wrapped(out,argv):
 cmd=[py,'-B','-m','mr3_learning.reach_execution','--output',str(out),'--scope','engineering']
 for p in sorted(sources):cmd+=['--source',str(p)]
 return subprocess.run([*cmd,'--',*argv],cwd=w,env=env).returncode
main=Path('/tmp/mr3_p2a_v38_protocol_outer_v1');final=Path('/tmp/mr3_p2a_v38_protocol_final_outer_v1');result=Path('/tmp/mr3_p2a_v38_protocol_forensic_v1.json');closed=Path('/tmp/mr3_p2a_v38_protocol_final_v1.json')
rc=wrapped(main,[x.replace('{freeze}',freeze) for x in scope['execution_argv_template']])
final_rc=wrapped(final,['/usr/bin/python3','-B',str(w/'report/assets/20261022_mr3_p2a_v35_grid_liveness/forensic_final_v1.py'),'--outer',str(main/'actual_wait.json'),'--result',str(result),'--scope',str(scope_path),'--freeze',freeze,'--output',str(closed)])
print(json.dumps({'freeze':freeze,'main_returncode':rc,'final_returncode':final_rc}))
raise SystemExit(bool(rc or final_rc))
