import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path('/home/zhuyulab/ns3-workspace');W=R/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl';A=W/'report/assets/20261023_mr3_p2a_v59_encoder_profile';PY='/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
OUT=A/'checks/admission_provisional_cpu_v2';OUT.mkdir(exist_ok=False)
S=A/'checks/admission_provisional_source_snapshots_v2';S.mkdir(exist_ok=False)
source_dirs=(W/'mr3_learning',W/'mr3_learning/tests',R/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration',R/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test',A)
sources={p for d in source_dirs for p in d.glob('*.py')};sources.add(Path(__file__).resolve())
rows=[]
for source in sorted(sources):
 raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest();target=S/(sha+'_'+source.name)
 if target.exists():assert target.read_bytes()==raw
 else:target.write_bytes(raw)
 rows.append({'path':str(source),'sha256':sha,'bytes':len(raw),'snapshot':str(target)})
(OUT/'sources_v1.json').write_text(json.dumps(rows,indent=2)+'\n')
cmd=[PY,'-B','-m','pytest','-q',str(A/'test_activity_resource_entry_v1.py'),'--junitxml',str(OUT/'pytest.xml')]
argv=[PY,'-B','-m','mr3_learning.reach_execution','--scope','cpu','--output',str(OUT/'actual_wait')]
for source in sorted(sources):argv+=['--source',str(source)]
argv+=['--',*cmd]
env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='');env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
(OUT/'argv_v1.json').write_text(json.dumps(argv,indent=2)+'\n')
started=time.monotonic_ns();child=subprocess.Popen(argv,cwd=W,env=env);rc=child.wait();ended=time.monotonic_ns()
(OUT/'parent_tool_wait_v1.json').write_text(json.dumps({'actual_argv':argv,'actual_waited':True,'actual_returncode':rc,'started_monotonic_ns':started,'ended_monotonic_ns':ended,'only_provisional_source_credit':True},indent=2)+'\n')
raise SystemExit(rc)
