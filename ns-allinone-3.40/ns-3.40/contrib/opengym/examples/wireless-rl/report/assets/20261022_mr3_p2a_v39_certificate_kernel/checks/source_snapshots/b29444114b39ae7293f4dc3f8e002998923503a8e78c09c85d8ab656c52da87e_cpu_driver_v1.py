"""Run only the declared artificial CPU checks, retaining source identities."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
PURE = ROS / 'src/multi_robot_exploration'
ASSETS = Path(__file__).resolve().parent
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'

GEOMETRY = [
    'test_mr3_point_graph.py', 'test_mr3_point_graph_observation.py',
    'test_mr3_proxy2d_navigation_point_graph.py', 'test_mr3_seed_v2.py',
    'test_mr3_proxy2d_navigation_seed_v2.py', 'test_mr3_observation.py',
    'test_mr3_seed_certificate.py', 'test_mr3_proxy2d_navigation_cache.py',
    'test_mr3_proxy2d_navigation_seed.py', 'test_mr3_seed_v2_missing_map.py',
]
LEARNER = [
    'test_proxy2d_seed_compatibility', 'test_proxy2d_seed_v2_compatibility',
    'test_proxy2d_point_graph', 'test_reach_qualification',
    'test_reach_training_admission', 'test_reach_policy_chain',
]
READERS = ['test_audit_seed_inputs', 'test_exact_snapshot_validator']


def main():
    name = sys.argv[1]
    setup = ('source /opt/ros/humble/setup.bash && source '
             + shlex.quote(str(ROS / 'install/setup.bash')) + ' && exec ')
    new_tests = [PURE / 'test/test_mr3_seed_certificate_kernel_equivalence.py']
    if not all(path.is_file() for path in new_tests):
        raise ValueError('missing new frozen-reference equivalence tests')
    if name.startswith('geometry_cpu_'):
        command = ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c',
                   setup + '/usr/bin/python3 -B -m pytest -q '
                   + ' '.join(shlex.quote(str(path)) for path in
                              [*(PURE / 'test' / item for item in GEOMETRY), *new_tests])]
    elif name.startswith('reader_cpu_'):
        command = ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c',
                   setup + '/usr/bin/python3 -B -m unittest '
                   + ' '.join('mr3_learning.tests.' + item for item in READERS)]
    elif name.startswith('learner_cpu_'):
        command = [PYTHON, '-B', '-m', 'unittest',
                   *('mr3_learning.tests.' + item for item in LEARNER)]
    elif name.startswith('microbenchmark_cpu_'):
        command = ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c',
                   setup + '/usr/bin/python3 -B '
                   + shlex.quote(str(ASSETS / 'microbenchmark_v1.py'))
                   + ' --output ' + shlex.quote(str(ASSETS / 'checks/microbenchmark_result_v1.json'))]
    else:
        raise ValueError(name)

    sources = set((WIRELESS / 'mr3_learning').glob('*.py'))
    sources.update((PURE / 'multi_robot_exploration').glob('*.py'))
    sources.update(PURE / 'test' / item for item in GEOMETRY)
    sources.update(new_tests)
    sources.update(WIRELESS / 'mr3_learning/tests' / (item + '.py')
                   for item in LEARNER + READERS)
    sources.update(ASSETS.glob('*.py'))
    sources.update([ASSETS / 'scope_v1.json', WIRELESS / 'MR3_ENV_CONTRACT.md',
                    ROS / 'scripts/mr3_env_worker.py',
                    ROS / 'scripts/mr3_proxy2d_worker.py',
                    ROS / 'scripts/audit_mr3_env.py'])

    recovery = []
    snapshot_dir = ASSETS / 'checks/source_snapshots'
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    baseline = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for source in sorted(sources):
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        relative = str(source.relative_to(ROOT))
        blob = subprocess.run(['git', 'show', baseline + ':' + relative],
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        row = {'path': relative, 'sha256': digest, 'bytes': len(raw)}
        if blob.returncode == 0 and blob.stdout == raw:
            row.update(kind='git_blob', freeze=baseline)
        else:
            target = snapshot_dir / (digest + '_' + source.name)
            temporary = target.with_name(target.name + '.' + str(os.getpid()) + '.tmp')
            temporary.write_bytes(raw)
            try:
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    if target.read_bytes() != raw:
                        raise ValueError('source snapshot collision')
            finally:
                temporary.unlink()
            row.update(kind='snapshot', snapshot=str(target.relative_to(ASSETS)))
        recovery.append(row)
    recovery_path = ASSETS / 'checks' / (name + '_source_recovery.json')
    with recovery_path.open('x') as stream:
        json.dump({'baseline_freeze': baseline, 'sources': recovery}, stream, indent=2)
        stream.write('\n')

    argv = [PYTHON, '-B', '-m', 'mr3_learning.reach_execution',
            '--output', str(ASSETS / 'checks' / name), '--scope', 'cpu']
    for source in sorted(sources):
        argv.extend(['--source', str(source)])
    argv.extend(['--', *command])
    env = dict(os.environ, PYTHONNOUSERSITE='1', CUDA_VISIBLE_DEVICES='')
    return subprocess.call(argv, cwd=WIRELESS, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
