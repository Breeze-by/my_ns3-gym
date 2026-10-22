import hashlib, json, os, shlex, subprocess, sys
from pathlib import Path
root=Path('/home/zhuyulab/ns3-workspace'); w=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'; ros=root/'ros2_ws/ros2-multi-robot-automap'; pure=ros/'src/multi_robot_exploration'; a=w/'report/assets/20261022_mr3_p2a_v34_seed_v2'; py='/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
name=sys.argv[1]
ros_tests=['test_mr3_proxy2d_information.py','test_mr3_proxy2d_worker.py','test_mr3_proxy2d_karto_integration.py','test_mr3_adapter.py','test_mr3_adapter_launch.py','test_mr3_proxy2d_seed_v2_wiring.py']
learner_tests=['test_reach_qualification','test_reach_policy_chain','test_reach_training_admission','test_reach_preparation_entry','test_audit_reach_ppo','test_exact_snapshot_validator','test_audit_proxy2d','test_proxy2d_conformity','test_proxy2d_capacity','test_proxy2d','test_proxy2d_karto_activity','test_proxy2d_seed_activity','test_proxy2d_seed_compatibility','test_proxy2d_seed_v2_compatibility','test_proxy2d_seed_v2_wiring']
setup='source /opt/ros/humble/setup.bash && source '+shlex.quote(str(ros/'install/setup.bash'))+' && exec '
if name=='ros_wiring_cpu_v1':
 command=['/usr/bin/bash','--noprofile','--norc','-e','-c',setup+'/usr/bin/python3 -B -m pytest -q '+' '.join(shlex.quote(str(pure/'test'/t)) for t in ros_tests)]
elif name=='native_reader_cpu_v1':
 command=['/usr/bin/bash','--noprofile','--norc','-e','-c',setup+'/usr/bin/python3 -B -m unittest mr3_learning.tests.test_audit_seed_inputs']
elif name=='learner_cpu_v1':
 command=[py,'-B','-m','unittest',*['mr3_learning.tests.'+t for t in learner_tests]]
else: raise ValueError(name)
sources=set((w/'mr3_learning').glob('*.py'))|set((pure/'multi_robot_exploration').glob('*.py'))|{w/'MR3_ENV_CONTRACT.md',ros/'scripts/mr3_proxy2d_worker.py',ros/'scripts/mr3_env_worker.py',ros/'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py',a/'scope_acceptance_v1.json'}
sources.update(w/'mr3_learning/tests'/ (t+'.py') for t in learner_tests)
sources.add(w/'mr3_learning/tests/test_audit_seed_inputs.py')
sources.update(pure/'test'/t for t in ros_tests)
snapshots=a/'checks/source_snapshots'; snapshots.mkdir(parents=True,exist_ok=True)
for src in sorted(sources):
 raw=src.read_bytes(); digest=hashlib.sha256(raw).hexdigest(); target=snapshots/(digest+'_'+src.name)
 try:
  with target.open('xb') as f: f.write(raw)
 except FileExistsError:
  if target.read_bytes()!=raw: raise ValueError('snapshot collision')
argv=[py,'-B','-m','mr3_learning.reach_execution','--output',str(a/'checks'/name),'--scope','cpu']
for src in sorted(sources): argv+=['--source',str(src)]
argv+=['--',*command]
os.environ['PYTHONNOUSERSITE']='1'
raise SystemExit(subprocess.call(argv,cwd=w))
