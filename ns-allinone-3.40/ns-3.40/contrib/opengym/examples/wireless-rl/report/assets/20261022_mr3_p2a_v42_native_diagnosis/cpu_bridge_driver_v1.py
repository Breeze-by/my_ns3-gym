"""Artificial regression for the system-reader bridge; no saved native inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
MODULES = ('test_audit_reach_system_replay', 'test_reach_controlled_dispatch', 'test_audit_reach_ppo')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9_]+', args.name):
        raise ValueError('invalid exclusive check name')
    sources = set((W / 'mr3_learning').glob('*.py'))
    sources.update((ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration').glob('*.py'))
    sources.update(W / 'mr3_learning/tests' / (name + '.py') for name in (*MODULES, 'test_audit_seed_inputs'))
    sources.add(Path(__file__).resolve())
    checks = A / 'checks'
    snapshots = checks / 'source_snapshots'
    snapshots.mkdir(parents=True, exist_ok=True)
    freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    recovery = []
    for path in sorted(sources):
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        relative = str(path.relative_to(ROOT))
        old = subprocess.run(['git', 'show', freeze + ':' + relative], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        row = {'path': relative, 'sha256': sha, 'bytes': len(raw)}
        if old.returncode == 0 and old.stdout == raw:
            row.update(kind='git_blob', freeze=freeze)
        else:
            target = snapshots / (sha + '_' + path.name)
            if target.exists():
                if target.read_bytes() != raw:
                    raise ValueError('source snapshot collision')
            else:
                with target.open('xb') as stream:
                    stream.write(raw)
            row.update(kind='snapshot', snapshot=str(target.relative_to(A)))
        recovery.append(row)
    with (checks / (args.name + '_source_recovery.json')).open('x') as stream:
        json.dump({'baseline_freeze': freeze, 'sources': recovery}, stream, indent=2)
        stream.write('\n')
    command = [PYTHON, '-B', '-m', 'unittest', *('mr3_learning.tests.' + item for item in MODULES)]
    argv = [PYTHON, '-B', '-m', 'mr3_learning.reach_execution', '--scope', 'cpu',
            '--output', str(checks / args.name)]
    for path in sorted(sources):
        argv.extend(['--source', str(path)])
    argv.extend(['--', *command])
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH', None)
    return subprocess.call(argv, cwd=W, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
