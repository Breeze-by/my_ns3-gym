import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

root = Path('/home/zhuyulab/ns3-workspace')
wireless = root / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
files = ['mr3_learning/' + name for name in (
    'audit_controlled_physics.py', 'audit_preparation.py', 'audit_ppo.py',
    'tests/test_audit_controlled_physics.py', 'tests/test_audit_controlled_readiness.py')]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before = {name: sha(wireless / name) for name in files}
environment = {**os.environ, 'PYTHONNOUSERSITE': '1'}
environment.pop('PYTHONPATH', None)
commands = [
    ('focused_final', ['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python', '-m', 'unittest',
                       'mr3_learning.tests.test_audit_controlled_readiness',
                       'mr3_learning.tests.test_audit_controlled_physics', '-v']),
    ('style_final', ['/usr/bin/python3', '-m', 'flake8', '--max-line-length=100',
                     '--ignore=E128,E129,W503,W504', *files]),
    ('diff_final', ['git', 'diff', '--check']),
]
rows = []
for kind, command in commands:
    output = Path('/tmp/mr3_p2a0_v12_readiness_' + kind + '.log')
    began = time.monotonic()
    with output.open('xb') as stream:
        result = subprocess.run(command, cwd=wireless, env=environment,
                                stdout=stream, stderr=subprocess.STDOUT, check=False)
    rows.append({'kind': kind, 'argv': command, 'cwd': str(wireless),
                 'returncode': result.returncode, 'wall_sec': time.monotonic() - began,
                 'output': str(output), 'output_sha256': sha(output)})
after = {name: sha(wireless / name) for name in files}
report = {'passed': all(row['returncode'] == 0 for row in rows) and before == after,
          'source_before': before, 'source_after': after, 'source_unchanged': before == after,
          'environment': {'PYTHONNOUSERSITE': '1', 'PYTHONPATH': None}, 'checks': rows,
          'scope': 'pure CPU only; no ROS/simulator/GPU/PPO training',
          'historical_checks': [
              {'path': '/tmp/mr3_p2a0_v12_readiness_focused_01.log',
               'result': 'FAIL initial fixture peer bundle SHA not synchronized; all originals kept'},
              {'path': '/tmp/mr3_p2a0_v12_readiness_focused_02.log', 'result': '11 PASS development'},
              {'path': '/tmp/mr3_p2a0_v12_readiness_focused_03.log',
               'result': '19 PASS development includes repeated imported 5-case TestCase; not 19 unique'},
              {'path': '/tmp/mr3_p2a0_v12_readiness_style_01.log',
               'result': 'FAIL style; initial command additionally omitted legacy W504 ignore'},
              {'path': '/tmp/mr3_p2a0_v12_readiness_style_02.log',
               'result': 'FAIL remaining two test style findings'},
          ]}
Path('/tmp/mr3_p2a0_v12_readiness_checks_final_v1.json').write_text(
    json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': report['passed'], 'checks': rows}))
raise SystemExit(0 if report['passed'] else 1)
