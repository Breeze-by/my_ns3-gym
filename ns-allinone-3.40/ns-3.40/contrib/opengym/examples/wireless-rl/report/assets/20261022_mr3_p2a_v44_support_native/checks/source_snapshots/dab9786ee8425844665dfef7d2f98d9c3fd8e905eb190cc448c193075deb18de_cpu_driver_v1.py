"""Finite V44 metadata/plan checks; no World or policy execution."""

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
ASSETS = Path(__file__).resolve().parent
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
PURE = ROS / 'src/multi_robot_exploration'
GEOMETRY = ['test_mr3_point_graph.py', 'test_mr3_point_graph_observation.py',
            'test_mr3_proxy2d_navigation_point_graph.py', 'test_mr3_seed_v2.py',
            'test_mr3_proxy2d_navigation_seed_v2.py', 'test_mr3_observation.py',
            'test_mr3_seed_certificate.py', 'test_mr3_proxy2d_navigation_cache.py',
            'test_mr3_proxy2d_navigation_seed.py', 'test_mr3_seed_v2_missing_map.py',
            'test_mr3_seed_certificate_kernel_equivalence.py',
            'test_mr3_reach_support.py', 'test_mr3_reach_support_runtime.py',
            'test_mr3_reach_support_wiring.py', 'test_mr3_reach_geometry.py',
            'test_mr3_reach_runtime_independent.py', 'test_motion_safety_reach.py',
            'test_mr3_reach_terminal_tail.py', 'test_mr3_motion_control.py']
LEARNER = ['test_proxy2d_seed_compatibility', 'test_proxy2d_seed_v2_compatibility',
           'test_proxy2d_point_graph', 'test_reach_qualification',
           'test_reach_training_admission', 'test_reach_policy_chain',
           'test_map_packing_gate', 'test_audit_reach_runtime', 'test_audit_reach_cadence',
           'test_native_custody_reach', 'test_audit_reach_ppo',
           'test_reach_controlled_dispatch', 'test_audit_reach_system_replay']


def main():
    name = sys.argv[1]
    setup = ('source /opt/ros/humble/setup.bash && source '
             + shlex.quote(str(ROS / 'install/setup.bash')) + ' && exec ')
    if name.startswith('readiness_cpu_'):
        command = [PYTHON, '-B', str(ASSETS / 'readiness_v1.py'),
                   '--output', str(ASSETS / 'checks' / (name + '_result.json'))]
    elif name == 'plan_check_cpu_v1':
        command = [PYTHON, '-B', '-m',
                   'report.assets.20261022_mr3_p2a_v44_support_native.plan_check_v1',
                   '--output', str(ASSETS / 'checks/plan_check_result_v1.json')]
    elif name == 'prepare_plan_cpu_v1':
        command = [PYTHON, '-B', '-m',
                   'report.assets.20261022_mr3_p2a_v44_support_native.prepare_plan_v1',
                   '--engineering-remaining-seconds', '24958.7661585403982']
    elif name == 'geometry_cpu_v1':
        command = ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c',
                   setup + '/usr/bin/python3 -B -m pytest -q '
                   + ' '.join(shlex.quote(str(PURE / 'test' / item)) for item in GEOMETRY)
                   + ' ' + shlex.quote(str(ROS / 'src/merge_map/test/test_merge_map.py'))]
    elif name.startswith('reader_cpu_'):
        command = ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c',
                   setup + '/usr/bin/python3 -B -m unittest mr3_learning.tests.test_audit_seed_inputs']
    elif name.startswith('snapshot_cpu_'):
        command = [PYTHON, '-B', '-m', 'unittest', 'mr3_learning.tests.test_exact_snapshot_validator']
    elif name == 'learner_cpu_v1':
        command = [PYTHON, '-B', '-m', 'unittest',
                   *('mr3_learning.tests.' + item for item in LEARNER),
                   *('mr3_learning.tests.' + path.stem for path in
                     sorted((WIRELESS / 'mr3_learning/tests').glob('test_*support*.py')))]
    else:
        raise ValueError(name)
    sources = set((WIRELESS / 'mr3_learning').glob('*.py'))
    sources.update((ROS / 'src/multi_robot_exploration/multi_robot_exploration').glob('*.py'))
    sources.update((WIRELESS / 'mr3_learning/tests').glob('test_*.py'))
    sources.update((PURE / 'test').glob('test_*.py'))
    sources.add(ROS / 'scripts/ros_smoke_test.py')
    sources.update([ROS / 'scripts/mr3_env_worker.py',
                    ROS / 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'])
    sources.update([Path(__file__).resolve(), ASSETS / 'readiness_v1.py',
                    ASSETS / 'authorization_v1.json', ASSETS / 'scope_v1.json'])
    sources.update(PURE / 'test' / item for item in GEOMETRY)
    sources.update([ROS / 'src/merge_map/merge_map/merge_map.py',
                    ROS / 'src/merge_map/test/test_merge_map.py'])
    sources.update(WIRELESS / 'mr3_learning/tests' / (item + '.py')
                   for item in LEARNER + ['test_audit_seed_inputs', 'test_exact_snapshot_validator', 'test_audit_reach_ppo'])
    sources.add(ASSETS.parent / '20261022_mr3_p2a_v43_support_geometry/support_prototype_v1.py')
    old_assets = ASSETS.parent / '20261022_mr3_p2a_v39_certificate_kernel'
    sources.update(old_assets / item for item in ('certificate_cases_v1.py', 'frozen_reference_v1.py'))
    if not name.startswith('readiness_cpu_'):
        sources.update(ASSETS.glob('*.py'))
        sources.update(ASSETS.glob('*.json'))
        # These evidence files are outputs of plan preparation, not its inputs.
        if name == 'prepare_plan_cpu_v1':
            sources.discard(ASSETS / 'plan_v1.json')
            sources.discard(ASSETS / 'native_custody_binding_v1.json')
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
            temporary = target.with_name(target.name + '.' + str(os.getpid()) + '.tmp')
            with temporary.open('xb') as stream:
                stream.write(raw)
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
    with (checks / (name + '_source_recovery.json')).open('x') as stream:
        json.dump({'baseline_freeze': freeze, 'sources': recovery}, stream, indent=2)
        stream.write('\n')
    argv = [PYTHON, '-B', '-m', 'mr3_learning.reach_execution', '--scope', 'cpu',
            '--output', str(checks / name)]
    for path in sorted(sources):
        argv.extend(['--source', str(path)])
    argv.extend(['--', *command])
    env = dict(os.environ, PYTHONNOUSERSITE='1',
               CUDA_VISIBLE_DEVICES='0' if name.startswith('readiness_cpu_') else '')
    return subprocess.call(argv, cwd=WIRELESS, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
