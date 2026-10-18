import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path('/home/zhuyulab/ns3-workspace')
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
SOURCE=Path('/tmp/mr3_p2a0_v25_smoother_clock_source_review_v1/probe')
OUT=Path('/tmp/mr3_p2a0_v25_actual_probe_compile_v1')
assert not OUT.exists()
OUT.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources={str(p):sha(p) for p in SOURCE.iterdir() if p.is_file()}
assert sources[str(SOURCE/'smoother_clock_probe.cpp')]=='59b3cdc4f3be6fce6520a9a84fc96e71aecfcbf2c075b316e473ee3a3d8b10e0'
command='''source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
cmake -S /tmp/mr3_p2a0_v25_smoother_clock_source_review_v1/probe -B /tmp/mr3_p2a0_v25_actual_probe_compile_v1/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build /tmp/mr3_p2a0_v25_actual_probe_compile_v1/build --parallel 2
'''
env=dict(os.environ)
for k in ('PYTHONPATH','CONDA_PREFIX','CONDA_DEFAULT_ENV','CONDA_PROMPT_MODIFIER','CONDA_SHLVL','_CE_CONDA','_CE_M'):env.pop(k,None)
env['PATH']='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
record=dict(schema='mr3-v25-real-probe-compile-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,sources=sources,passed=False)
(OUT/'started_v1.json').write_text(json.dumps(record,indent=2)+'\n')
t=time.monotonic()
with (OUT/'compile.stdout').open('xb') as stdout,(OUT/'compile.stderr').open('xb') as stderr:
    result=subprocess.run(['/bin/bash','--noprofile','--norc','-e','-c',command],cwd=ROS,env=env,stdout=stdout,stderr=stderr)
record.update(returncode=result.returncode,wall_seconds=time.monotonic()-t)
record['source_unchanged']=all(sha(Path(p))==s for p,s in sources.items())
probe=OUT/'build/smoother_clock_probe'
record['probe']=dict(path=str(probe),sha256=sha(probe),bytes=probe.stat().st_size) if probe.exists() else None
record['passed']=result.returncode==0 and record['source_unchanged'] and probe.exists()
for name in ('compile.stdout','compile.stderr'):
    record[name]=dict(sha256=sha(OUT/name),bytes=(OUT/name).stat().st_size)
(OUT/'compile_receipt_v1.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
raise SystemExit(0 if record['passed'] else 1)
