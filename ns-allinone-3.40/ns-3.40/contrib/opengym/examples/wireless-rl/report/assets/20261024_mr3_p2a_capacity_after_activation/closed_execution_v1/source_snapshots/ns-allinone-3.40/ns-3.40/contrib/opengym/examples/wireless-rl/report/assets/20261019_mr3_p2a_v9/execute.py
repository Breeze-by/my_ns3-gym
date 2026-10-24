"""Finite outer wait receipt; the final closure reader runs after this exits."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / '.git').exists())
W = HERE.parents[2]
sys.path.insert(0, str(W))
from mr3_learning.preparation import dump, identity, sha


def main():
    started = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--scope', choices=('trace', 'matrix'), required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error('wait receipt exists; never overwrite')
    plan = json.loads(args.plan.read_text())
    command = [args.freeze if value == '{freeze}' else value for value in plan[args.scope + '_command']]
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    value = {'schema': 'mr3-p2a-v9-outer-actual-wait-v1', 'freeze': args.freeze,
             'scope': args.scope, 'plan_sha256': sha(args.plan), 'argv': command,
             'owner_identity': identity(os.getpid()), 'started_wall_monotonic_ns': started,
             'errors': [], 'returncode': None}
    process = subprocess.Popen(command, cwd=W, env=env)
    value['process_identity'] = identity(process.pid)
    while value['returncode'] is None:
        try:
            value['returncode'] = process.wait()
        except BaseException as error:
            value['errors'].append(repr(error))
    value['ended_wall_monotonic_ns'] = time.monotonic_ns()
    value['wall_seconds'] = str(Decimal(value['ended_wall_monotonic_ns'] - started) / 10**9)
    dump(args.receipt, value)
    print(json.dumps({k: value[k] for k in ('scope', 'returncode', 'wall_seconds')}))
    return value['returncode'] if value['returncode'] else int(bool(value['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
