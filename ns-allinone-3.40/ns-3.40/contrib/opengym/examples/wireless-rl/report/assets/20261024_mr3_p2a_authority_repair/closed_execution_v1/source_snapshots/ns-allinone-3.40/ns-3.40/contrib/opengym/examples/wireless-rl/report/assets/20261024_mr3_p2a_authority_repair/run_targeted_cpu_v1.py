import json,subprocess,sys
from pathlib import Path
R=Path('/home/zhuyulab/ns3-workspace')
W=R/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS=R/'ros2_ws/ros2-multi-robot-automap'
kind=sys.argv[1];out=Path('/tmp/mr3_authority_repair_'+kind+'_v1')
sources=sorted((W/'mr3_learning').glob('*.py'))+sorted((W/'mr3_learning/tests').glob('*.py'))+sorted((ROS/'src/multi_robot_exploration').rglob('*.py'))+sorted((ROS/'scripts').glob('*.py'))
if kind=='ros':
    command=['/bin/bash','--noprofile','--norc','-c', 'source /opt/ros/humble/setup.bash && source '+str(ROS/'install/setup.bash')+' && exec /usr/bin/python3 -B -m pytest -q '+str(ROS/'src/multi_robot_exploration/test/test_mr3_motion_authority_callbacks.py')+' '+str(ROS/'src/multi_robot_exploration/test/test_mr3_worker_shutdown.py')+' --junitxml='+str(out/'junit.xml')]
else:
    command=['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python','-B','-m','pytest','-q','mr3_learning/tests/test_motion_authority_audit.py','mr3_learning/tests/test_motion_authority_metadata.py','mr3_learning/tests/test_authority_public_reader_wiring.py','--junitxml='+str(out/'junit.xml')]
argv=['/usr/bin/python3','-B','-m','mr3_learning.reach_execution','--scope','cpu','--output',str(out)]
for p in sources:argv+=['--source',str(p)]
raise SystemExit(subprocess.call(argv+['--']+command,cwd=W))
