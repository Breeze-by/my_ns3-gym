import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
SOURCE = Path('/tmp/mr3_p2a0_v25_smoother_clock_source_review_v1')
OUT = Path('/tmp/mr3_p2a0_v25_actual_overlay_build_v1')
DEST = ROS / 'src/nav2_velocity_smoother'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def identity(p):
    s = p.stat()
    return dict(path=str(p), resolved=str(p.resolve()), sha256=sha(p), bytes=s.st_size,
                stat=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns])

assert subprocess.check_output(['git','status','--porcelain'],cwd=ROOT) == b''
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip() == '94a5e26b99402e49b4e116931f8b8f625e603b0d'
assert not DEST.exists() and not OUT.exists()
assert sha(SOURCE/'proposed_package/src/velocity_smoother.cpp') == 'b49f5d345391ccf62dcd4111cfa82c49065efad997d4723f60c7dab3edc15cec'
OUT.mkdir()
shutil.copytree(SOURCE/'proposed_package',DEST)
(DEST/'MR3_PROVENANCE.md').write_text('''# MR3 Nav2 velocity smoother overlay

Upstream: https://github.com/ros-navigation/navigation2/tree/1.1.20/nav2_velocity_smoother
Tag commit: `a097086719c88f781aa59788eca29ac6ca5e56db` (1.1.20).
The upstream Apache 2.0 license and package sources are retained.

MR3 changes only two timer factories in `src/velocity_smoother.cpp` and adds
`rclcpp/create_timer.hpp`: activation and dynamic frequency reconfiguration use
the node clock through `rclcpp::create_timer`. With `use_sim_time=true`, paused
simulation time must not accumulate wall-time OPEN_LOOP velocity increments.
Normal real-time operation uses the same node clock contract.

The constraints algorithm, parameters, topics, lifecycle, dependencies and
executable name remain upstream 1.1.20. This change does not prove physical
velocity or task success; those retain independent native acceptance gates.
''')
before = [identity(p) for p in sorted((ROS/'install/multi_robot/lib').glob('libmr3*.so'))]
assert len(before) == 6, before
files = [identity(p) for p in sorted(DEST.rglob('*')) if p.is_file()]
record = dict(schema='mr3-v25-canonical-smoother-build-v1', utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              source_base_commit='94a5e26b99402e49b4e116931f8b8f625e603b0d', sources=files,
              previous_mr3_libraries=before, passed=False, source_build_only=True)
command = '''source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select nav2_velocity_smoother --allow-overriding nav2_bringup nav2_velocity_smoother --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_TESTING=OFF
'''
record['command'] = command
(OUT/'started_v1.json').write_text(json.dumps(record,indent=2)+'\n')
environment = dict(os.environ)
for key in ('PYTHONPATH','CONDA_PREFIX','CONDA_DEFAULT_ENV','CONDA_PROMPT_MODIFIER','CONDA_SHLVL','_CE_CONDA','_CE_M'):
    environment.pop(key,None)
environment['PATH']='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
t = time.monotonic()
with (OUT/'build.stdout').open('xb') as out, (OUT/'build.stderr').open('xb') as err:
    result = subprocess.run(['/bin/bash','--noprofile','--norc','-c',command],cwd=ROS,env=environment,stdout=out,stderr=err)
record['wall_seconds']=time.monotonic()-t
record['returncode']=result.returncode
record['stdout']=identity(OUT/'build.stdout')
record['stderr']=identity(OUT/'build.stderr')
record['sources_after']=[identity(Path(row['path'])) for row in files]
record['mr3_libraries_after']=[identity(Path(row['path'])) for row in before]
record['unchanged_mr3']=record['mr3_libraries_after']==before
record['unchanged_sources']=record['sources_after']==files
outputs=[ROS/'install/nav2_velocity_smoother/lib/libvelocity_smoother_core.so',ROS/'install/nav2_velocity_smoother/lib/nav2_velocity_smoother/velocity_smoother']
record['outputs']=[identity(p) for p in outputs if p.exists()]
record['passed']=result.returncode==0 and len(record['outputs'])==2 and record['unchanged_mr3'] and record['unchanged_sources']
(OUT/'build_receipt_v1.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(passed=record['passed'],wall_seconds=record['wall_seconds'],receipt=str(OUT/'build_receipt_v1.json'),outputs=record['outputs'])))
raise SystemExit(0 if record['passed'] else 1)
