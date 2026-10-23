"""Run the fixed V69 entry-only fixtures and real module help before sealing a plan."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .classification_admission_v1 import current_python_sources, CONFIG_FILES

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'


def main():
    spec = json.loads((A / 'admission_cpu_spec_v1.json').read_text())
    if spec.get('schema') != 'mr3-v69-admission-cpu-spec-v1' or spec['actual_argv'][:5] != [PYTHON, '-B', '-m', 'pytest', '-q']:
        raise ValueError('unexpected V69 artificial CPU declaration')
    runtime, tests = current_python_sources(ROOT)
    sources = {ROOT / relative for relative in runtime | tests}
    sources.update(A.glob('*.py'))
    sources.add(A / 'admission_cpu_spec_v1.json')
    sources.update(CONFIG_FILES)
    sources.add(ROS / 'scripts/mr3_env_worker.py')
    sources.add(ROS / 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py')
    sources.add(ROS / 'src/merge_map/merge_map/merge_map.py')
    sources.add(ROS / 'src/merge_map/test/test_merge_map.py')
    sources.add(A.parent / '20261023_mr3_p2a_v50_qualification/external_absence_v1.py')
    if not set(spec['expected_source_hashes']) <= {str(p.relative_to(ROOT)) for p in sources}:
        raise ValueError('entry sources absent from actual CPU binding')
    for relative, digest in spec['expected_source_hashes'].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise ValueError('sealed entry source changed before CPU launch: ' + relative)
    checks = A / 'checks'
    snapshots = checks / 'source_snapshots'
    snapshots.mkdir(parents=True, exist_ok=True)
    freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    rows = []
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
                    raise ValueError('CPU source snapshot collision')
            else:
                with target.open('xb') as stream:
                    stream.write(raw)
            row.update(kind='snapshot', snapshot=str(target.relative_to(A)))
        rows.append(row)
    recovery = checks / 'admission_cpu_v1_source_recovery.json'
    with recovery.open('x') as stream:
        json.dump({'baseline_freeze': freeze, 'sources': rows}, stream, indent=2)
        stream.write('\n')
    argv = [PYTHON, '-B', '-m', 'mr3_learning.reach_execution', '--scope', 'cpu',
            '--output', str(checks / 'admission_cpu_v1')]
    for path in sorted(sources):
        argv.extend(['--source', str(path)])
    argv.extend(['--', *spec['actual_argv']])
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    return subprocess.call(argv, cwd=W, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
