import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
OUT = Path('/tmp/mr3_p2a0_v24_canonical_audit_unit_v1')
assert not OUT.exists()
OUT.mkdir()
sources = [W / 'mr3_learning/audit_ppo.py', W / 'mr3_learning/tests/test_audit_ppo.py', W / 'MR3_ENV_CONTRACT.md']
before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
argv = ['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python', '-B', '-m', 'unittest', 'mr3_learning.tests.test_audit_ppo']
environment = os.environ.copy()
environment.pop('PYTHONPATH', None)
environment.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
start = time.monotonic()
with (OUT / 'stdout.txt').open('x') as stdout, (OUT / 'stderr.txt').open('x') as stderr:
    process = subprocess.run(argv, cwd=W, env=environment, stdout=stdout, stderr=stderr)
after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
result = {'schema': 'mr3-v24-canonical-conda-audit-unit-execution-v1', 'scope': 'Original relevant audit unit module against actual promoted V24 production auditor/ENV; CPU only, no ROS/SDK/native/GPU.', 'argv': argv, 'cwd': str(W), 'environment': {'PYTHONPATH': None, 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': ''}, 'returncode': process.returncode, 'wall_seconds': time.monotonic() - start, 'sources_before': before, 'sources_after': after, 'source_stable': before == after}
(OUT / 'execution.json').write_text(json.dumps(result, indent=2) + '\n')
print((OUT / 'stdout.txt').read_text())
print((OUT / 'stderr.txt').read_text())
print(json.dumps(result))
raise SystemExit(process.returncode if before == after else 1)
