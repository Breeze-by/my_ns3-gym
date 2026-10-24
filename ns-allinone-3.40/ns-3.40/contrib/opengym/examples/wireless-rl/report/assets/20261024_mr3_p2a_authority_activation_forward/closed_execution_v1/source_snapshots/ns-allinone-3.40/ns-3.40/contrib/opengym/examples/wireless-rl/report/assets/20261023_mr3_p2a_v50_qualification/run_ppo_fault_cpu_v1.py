"""Fresh pre-update admission regressions; all native receipts are artificial."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
TESTS = ('test_reach_runtime_fault_admission', 'test_reach_training_admission',
         'test_reach_policy_chain', 'test_audit_reach_ppo')


def main():
    prior = json.loads((A.parent / '20261022_mr3_p2a_v45_preparation_classification/plan_v1.json').read_text())
    sources = {ROOT / path for path in prior['source_bindings']}
    sources.update((W / 'mr3_learning').glob('*.py'))
    sources.update((W / 'mr3_learning/tests').glob('test_*.py'))
    sources.update((ROS / 'src/multi_robot_exploration/test').glob('test_*.py'))
    sources.add(Path(__file__).resolve())
    freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    snapshots = A / 'checks/source_snapshots'
    snapshots.mkdir(parents=True, exist_ok=True)
    recovery = []
    for path in sorted(sources):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        relative = str(path.relative_to(ROOT))
        git = subprocess.run(['git', 'show', freeze + ':' + relative], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        row = dict(path=relative, sha256=digest, bytes=len(raw))
        if git.returncode == 0 and git.stdout == raw:
            row.update(kind='git_blob', freeze=freeze)
        else:
            target = snapshots / (digest + '_' + path.name)
            with target.open('xb') as stream:
                stream.write(raw)
            row.update(kind='snapshot', snapshot=str(target.relative_to(A)))
        recovery.append(row)
    with (A / 'checks/ppo_fault_cpu_v1_source_recovery.json').open('x') as stream:
        json.dump(dict(baseline_freeze=freeze, sources=recovery), stream, indent=2)
        stream.write('\n')
    command = [PYTHON, '-B', '-m', 'pytest', '-q',
               *(str(W / 'mr3_learning/tests' / (name + '.py')) for name in TESTS)]
    argv = [PYTHON, '-B', '-m', 'mr3_learning.reach_execution', '--scope', 'cpu',
            '--output', str(A / 'checks/ppo_fault_cpu_v1')]
    for path in sorted(sources):
        argv += ['--source', str(path)]
    argv += ['--', *command]
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH', None)
    return subprocess.call(argv, cwd=W, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
