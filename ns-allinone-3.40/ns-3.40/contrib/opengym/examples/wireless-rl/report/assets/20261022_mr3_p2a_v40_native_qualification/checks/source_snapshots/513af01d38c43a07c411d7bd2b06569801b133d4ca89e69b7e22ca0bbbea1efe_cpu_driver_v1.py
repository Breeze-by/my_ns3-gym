"""Finite V40 metadata/plan checks; no World or policy execution."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
ASSETS = Path(__file__).resolve().parent
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'


def main():
    name = sys.argv[1]
    if name == 'readiness_cpu_v1':
        command = [PYTHON, '-B', str(ASSETS / 'readiness_v1.py'),
                   '--output', str(ASSETS / 'checks/readiness_result_v1.json')]
    elif name == 'plan_check_cpu_v1':
        command = [PYTHON, '-B', str(ASSETS / 'plan_check_v1.py'),
                   '--output', str(ASSETS / 'checks/plan_check_result_v1.json')]
    elif name == 'prepare_plan_cpu_v1':
        command = [PYTHON, '-B', str(ASSETS / 'prepare_plan_v1.py')]
    else:
        raise ValueError(name)
    sources = set((WIRELESS / 'mr3_learning').glob('*.py'))
    sources.update((ROS / 'src/multi_robot_exploration/multi_robot_exploration').glob('*.py'))
    sources.update([Path(__file__).resolve(), ASSETS / 'readiness_v1.py',
                    ASSETS / 'authorization_v1.json', ASSETS / 'scope_v1.json'])
    if name != 'readiness_cpu_v1':
        sources.update(ASSETS.glob('*.py'))
        sources.update(ASSETS.glob('*.json'))
    checks = ASSETS / 'checks'
    snapshots = checks / 'source_snapshots'
    snapshots.mkdir(parents=True, exist_ok=True)
    freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    recovery = []
    for path in sorted(sources):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        relative = str(path.relative_to(ROOT))
        old = subprocess.run(['git', 'show', freeze + ':' + relative], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        row = {'path': relative, 'sha256': digest, 'bytes': len(raw)}
        if old.returncode == 0 and old.stdout == raw:
            row.update(kind='git_blob', freeze=freeze)
        else:
            target = snapshots / (digest + '_' + path.name)
            if target.exists():
                if target.read_bytes() != raw:
                    raise ValueError('source snapshot collision')
            else:
                with target.open('xb') as stream:
                    stream.write(raw)
            row.update(kind='snapshot', snapshot=str(target.relative_to(ASSETS)))
        recovery.append(row)
    with (checks / (name + '_source_recovery.json')).open('x') as stream:
        json.dump({'baseline_freeze': freeze, 'sources': recovery}, stream, indent=2)
        stream.write('\n')
    argv = [PYTHON, '-B', '-m', 'mr3_learning.reach_execution', '--scope', 'cpu',
            '--output', str(checks / name)]
    for path in sorted(sources):
        argv.extend(['--source', str(path)])
    argv.extend(['--', *command])
    env = dict(os.environ, PYTHONNOUSERSITE='1', CUDA_VISIBLE_DEVICES='0')
    return subprocess.call(argv, cwd=WIRELESS, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
