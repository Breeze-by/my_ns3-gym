import subprocess
from pathlib import Path
R=Path('/home/zhuyulab/ns3-workspace');W=R/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl';A=Path(__file__).resolve().parent
sources=sorted((W/'mr3_learning').glob('*.py'))+sorted((R/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration').rglob('*.py'))+[Path(__file__).resolve(),A/'readiness_v1.py']
args=['/usr/bin/python3','-B','-m','mr3_learning.reach_execution','--scope','cpu','--output',str(A/'checks/readiness_v1')]
for p in sources:args+=['--source',str(p)]
args+=['--','/usr/bin/python3','-B',str(A/'readiness_v1.py'),'--mode','all','--output',str(A/'checks/readiness_v1/result.json')]
raise SystemExit(subprocess.call(args,cwd=W))
