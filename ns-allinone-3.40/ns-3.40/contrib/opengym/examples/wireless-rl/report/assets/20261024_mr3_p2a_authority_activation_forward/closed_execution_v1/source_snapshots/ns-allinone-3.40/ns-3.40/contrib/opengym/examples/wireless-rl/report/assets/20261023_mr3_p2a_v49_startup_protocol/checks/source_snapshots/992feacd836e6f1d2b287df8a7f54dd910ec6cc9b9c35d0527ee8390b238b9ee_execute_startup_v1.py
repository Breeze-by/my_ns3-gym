"""Enclose the newly declared diagnostic and review in one actual-wait fee."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    scope_path = A / 'startup_scope_v1.json'
    scope = json.loads(scope_path.read_text())
    source_paths = sorted({row['path'] for row in
                           scope['source_bindings'] + scope['library_bindings']} | {str(scope_path)})
    command = [scope['expected_job'][0], '-B', '-m', 'mr3_learning.reach_execution',
        '--scope', 'engineering', '--output', '/tmp/mr3_p2a_reach_v49_startup_wait']
    for path in source_paths:
        command += ['--source', path]
    command += ['--', scope['expected_job'][0], '-B', str(A / 'run_startup_v1.py'),
                '--freeze', args.freeze]
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH', None)
    return subprocess.call(command, cwd=W, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
