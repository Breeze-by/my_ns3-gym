"""Actual canonical V62 CPU-only round; preserves uncommitted source snapshots."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261024_mr3_p2a_v62_process_profile'
B = A / 'checks/canonical_cpu_v1'
BASE = '0ab8d8339368681d657f09814e45a38eae6b2f46'


def main():
    B.mkdir(exist_ok=False)
    fixture = A / 'artificial_cpu_v3'
    fixture.mkdir(exist_ok=False)
    sys.path.insert(0, str(A))
    import fixed_process_profile_v1 as core
    installed = Path('/opt/ros/humble/lib/python3.10/site-packages')
    ros = ROOT / 'ros2_ws/ros2-multi-robot-automap'
    a61 = W / 'report/assets/20261024_mr3_p2a_v61_cancel_forensics'
    names = ['README.md', 'base_source_pins_v1.json', 'bootstrap_v1.py', 'fixed_integration_v1.py',
        'fixed_process_profile_v1.py', 'fixed_profile_launcher_v1.py', 'fixed_roles_entry_v1.py',
        'review_profile_v1.py', 'run_profile_v1.py', 'test_benchmark_runtime_v1.py',
        'test_fixed_process_profile_v1.py', 'test_integration_static_v1.py', 'test_launch_api_v1.py',
        'test_parent_v1.py', 'test_profile_review_v1.py']
    tests = [A / name for name in names if name.startswith('test_')]
    command = ['/usr/bin/python3', '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               *map(str, tests), '--junitxml=' + str(B/'actual/pytest.xml'),
               '--basetemp=' + str(B/'pytest_tmp')]
    actual_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if actual_head != BASE:
        raise ValueError('canonical CPU base HEAD changed')
    spec = dict(schema='mr3-v62-canonical-cpu-spec-v1', scope='cpu', base_HEAD=actual_head,
        uncommitted_canonical_sources_expected=True, expected_tests=23, actual_argv=command,
        native_or_scientific_qualification=False, engineering_added_seconds='0')
    spec_path = B/'spec_v1.json'
    spec_path.open('x').write(json.dumps(spec, indent=2)+'\n')
    sources = sorted(set([*[A/name for name in names], Path(__file__).resolve(), spec_path,
        *(W/'mr3_learning').glob('*.py'),
        *(ros/'src/multi_robot_exploration/multi_robot_exploration').glob('*.py'),
        ros/'scripts/mr3_env_worker.py', *a61.glob('*.py'), a61/'closure_ledger_v1.json',
        W/'report/assets/20261019_mr3_p2a_v16/external_absence_v1.py',
        *[path for name in ('launch', 'launch_ros', 'ros2launch') for path in (installed/name).rglob('*.py')],
        Path('/usr/bin/python3'), Path('/home/zhuyulab/miniconda3/envs/ns3gym/bin/python')]))
    snapshots = B/'source_snapshots'
    snapshots.mkdir()
    rows = []
    for ordinal, path in enumerate(sources):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = snapshots / (str(ordinal).zfill(4)+'_'+digest+'_'+path.name)
        snapshot.open('xb').write(raw)
        row = dict(path=str(path), bytes=len(raw), sha256=digest, snapshot=str(snapshot))
        if path.is_relative_to(ROOT) and not path.is_relative_to(A):
            relative = str(path.relative_to(ROOT))
            if subprocess.check_output(['git', 'show', BASE+':'+relative], cwd=ROOT) != raw:
                raise ValueError('existing dependency differs from base HEAD: '+relative)
            row.update(kind='base_git_blob', base_HEAD=BASE, relative_path=relative)
        else:
            row.update(kind='uncommitted_canonical_snapshot' if path.is_relative_to(A) else 'external_snapshot')
        rows.append(row)
    (B/'source_recovery_v1.json').open('x').write(json.dumps(dict(base_HEAD=BASE,
        worktree_status_before=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
        sources=rows),indent=2)+'\n')
    (B/'runner_identity_v1.json').open('x').write(json.dumps(core.identity(),indent=2)+'\n')
    argv = [sys.executable, '-B', '-m', 'mr3_learning.reach_execution', '--scope', 'cpu',
            '--output', str(B/'actual')]
    for path in sources:
        argv.extend(['--source', str(path)])
    argv.extend(['--', *command])
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    return subprocess.call(argv, cwd=W, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
