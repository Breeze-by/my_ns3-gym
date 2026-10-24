"""Fresh affected ROS/learner suites with exact source snapshots; CPU only."""
import gzip,hashlib,json,subprocess,sys
from pathlib import Path
R=Path('/home/zhuyulab/ns3-workspace');W=R/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS=R/'ros2_ws/ros2-multi-robot-automap';A=Path(__file__).resolve().parent
OLD=W/'report/assets/20261024_mr3_p2a_v71_masked_stimulus_qualification'
kind=sys.argv[1];group=json.loads((OLD/'fresh_cpu_spec_v1.json').read_text())['groups'][0 if kind=='ros' else 1]
out=A/'checks'/('activation_'+kind+'_v1');argv=[v.replace(str(OLD),str(A)).replace('fresh_'+kind+'_cpu_v1','activation_'+kind+'_v1') for v in group['actual_argv']]
if kind=='ros':
    argv=['/bin/bash','--noprofile','--norc','-e','-c','source /opt/ros/humble/setup.bash && source '+str(ROS/'install/setup.bash')+' && exec /usr/bin/python3 -B -m pytest -q '+str(ROS/'src/multi_robot_exploration/test/test_mr3_motion_authority_callbacks.py')+' '+str(ROS/'src/multi_robot_exploration/test/test_mr3_authority_activation.py')+' --junitxml '+str(out/'junit.xml')]
else:
    argv=['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python','-B','-m','pytest','-q',str(W/'mr3_learning/tests/test_motion_authority_audit.py'),str(W/'mr3_learning/tests/test_audit_reach_information.py'),'--junitxml',str(out/'junit.xml')]
sources=sorted((W/'mr3_learning').glob('*.py'))+sorted((W/'mr3_learning/tests').glob('*.py'))+sorted((ROS/'src/multi_robot_exploration').rglob('*.py'))+sorted((ROS/'scripts').glob('*.py'))+[Path(__file__).resolve()]
snap=A/'checks/source_snapshots';snap.mkdir(exist_ok=True)
for p in sources:
    raw=p.read_bytes();dest=snap/(hashlib.sha256(raw).hexdigest()+'.gz')
    if not dest.exists():dest.write_bytes(gzip.compress(raw,mtime=0))
command=['/usr/bin/python3','-B','-m','mr3_learning.reach_execution','--scope','cpu','--output',str(out)]
for p in sources:command+=['--source',str(p)]
raise SystemExit(subprocess.call(command+['--']+argv,cwd=W))
