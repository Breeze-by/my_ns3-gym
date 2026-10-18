import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path('/home/zhuyulab/ns3-workspace')
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
OUT=Path('/tmp/mr3_p2a0_v25_overlay_resolution_v1')
OUT.mkdir(exist_ok=False)
cmd='''source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 -B -c 'from ament_index_python.packages import get_package_prefix; from launch_ros.substitutions import ExecutableInPackage; from launch import LaunchContext; import json,os; p=get_package_prefix("nav2_velocity_smoother"); e=ExecutableInPackage(package="nav2_velocity_smoother",executable="velocity_smoother").perform(LaunchContext()); print(json.dumps(dict(package_prefix=p,executable=e,LD_LIBRARY_PATH=os.environ.get("LD_LIBRARY_PATH"),AMENT_PREFIX_PATH=os.environ.get("AMENT_PREFIX_PATH"))))'
ldd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/nav2_velocity_smoother/lib/nav2_velocity_smoother/velocity_smoother
'''
result=subprocess.run(['env','-u','PYTHONPATH','-u','CONDA_PREFIX','-u','CONDA_DEFAULT_ENV','PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','/bin/bash','--noprofile','--norc','-e','-c',cmd],cwd=ROS,capture_output=True)
(OUT/'stdout.txt').write_bytes(result.stdout)
(OUT/'stderr.txt').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
data=json.loads(result.stdout.splitlines()[0])
expected=ROS/'install/nav2_velocity_smoother'
assert Path(data['package_prefix'])==expected
assert Path(data['executable'])==expected/'lib/nav2_velocity_smoother/velocity_smoother'
lines=[x for x in result.stdout.decode().splitlines() if 'libvelocity_smoother_core.so =>' in x]
assert len(lines)==1 and str(expected/'lib/libvelocity_smoother_core.so') in lines[0]
files=[]
for rel in ('CMakeCache.txt','compile_commands.json','CMakeFiles/velocity_smoother_core.dir/link.txt','CMakeFiles/velocity_smoother.dir/link.txt'):
    p=ROS/'build/nav2_velocity_smoother'/rel
    raw=p.read_bytes()
    dst=OUT/rel.replace('/','_')
    dst.write_bytes(raw)
    files.append(dict(source=str(p),selected=str(dst),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
record=dict(schema='mr3-v25-actual-overlay-resolution-v1',passed=True,command=cmd,returncode=result.returncode,resolution=data,core_ldd=lines[0],build_inputs=files,scope='Read-only package/launch/ELF resolution. No node or DDS participant started.')
(OUT/'resolution_v1.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
