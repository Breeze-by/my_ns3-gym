import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

parser=argparse.ArgumentParser();parser.add_argument('label');parser.add_argument('argv',nargs=argparse.REMAINDER);a=parser.parse_args()
root=Path('/home/zhuyulab/ns3-workspace');ros=root/'ros2_ws/ros2-multi-robot-automap'
paths=['src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py','src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py','src/multi_robot_exploration/test/test_mr3_phase_qos.py','src/multi_robot_exploration/test/test_mr3_adapter.py']
sha=lambda raw:hashlib.sha256(raw).hexdigest()
before={p:sha((ros/p).read_bytes()) for p in paths}
stem='/tmp/mr3_p2a0_v11_runtime_'+a.label;log=Path(stem+'.log');assert not log.exists();start=time.monotonic()
env=os.environ.copy();env.pop('PYTHONPATH',None);env['PYTHONNOUSERSITE']='1';env['PYTHONDONTWRITEBYTECODE']='1'
with log.open('xb') as f: process=subprocess.run(a.argv,cwd=ros,env=env,stdout=f,stderr=subprocess.STDOUT)
after={p:sha((ros/p).read_bytes()) for p in paths}
result={'argv':a.argv,'cwd':str(ros),'env':{'PYTHONPATH':None,'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'},'returncode':process.returncode,'wall_sec':time.monotonic()-start,'stdout':str(log),'stdout_sha256':sha(log.read_bytes()),'source_before':before,'source_after':after,'source_stable':before==after,'scope':'System ROS CPU endpoint/method regression only; no Gazebo/native run or training'}
Path(stem+'.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
