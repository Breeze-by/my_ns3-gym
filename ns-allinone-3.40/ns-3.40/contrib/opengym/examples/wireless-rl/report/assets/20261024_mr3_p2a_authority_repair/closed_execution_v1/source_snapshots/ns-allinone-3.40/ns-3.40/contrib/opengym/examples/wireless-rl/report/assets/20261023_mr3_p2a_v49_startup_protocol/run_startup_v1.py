"""One newly frozen startup diagnostic, actual wait, then independent closure."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mr3_learning.preparation import identity

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
SCOPE = A / 'startup_scope_v1.json'


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def verify_sources(scope, freeze):
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT)
    if (git('rev-parse', 'HEAD').decode().strip() != freeze
            or git('rev-parse', 'origin/main').decode().strip() != freeze
            or git('status', '--porcelain')):
        raise ValueError('startup diagnostic requires the exact clean pushed source freeze')
    rows = []
    for row in [*scope['source_bindings'], *scope['library_bindings']]:
        path = Path(row['path'])
        raw = path.read_bytes()
        if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('bound bytes differ: ' + str(path))
        if row in scope['source_bindings']:
            relative = str(path.relative_to(ROOT))
            if git('show', freeze + ':' + relative) != raw:
                raise ValueError('source not in exact Git freeze: ' + relative)
        rows.append(row)
    if git('show', freeze + ':' + str(SCOPE.relative_to(ROOT))) != SCOPE.read_bytes():
        raise ValueError('scope is not frozen')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    scope = json.loads(SCOPE.read_text())
    if len(args.freeze) != 40 or any(c not in '0123456789abcdef' for c in args.freeze):
        raise ValueError('full hexadecimal source freeze required')
    state = Path(scope['driver_dir'])
    state.mkdir(exist_ok=False)
    started = time.monotonic_ns()
    before = verify_sources(scope, args.freeze)
    active = [dict(identity=identity(os.getpid()), reason='current diagnostic driver'),
              dict(identity=identity(os.getppid()), reason='current actual-wait parent')]
    write(state / 'entry.json', dict(freeze=args.freeze, scope=str(SCOPE),
        driver_identity=identity(os.getpid()), active_exclusions=active,
        started_monotonic_ns=started, source_proof=before, no_retry=True))
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH', None)
    errors = []
    native_start = time.monotonic_ns()
    with (state / 'native.log').open('x') as output:
        child = subprocess.Popen(scope['expected_job'], cwd=W, env=env,
                                 stdout=output, stderr=subprocess.STDOUT)
        child_identity = identity(child.pid)
        while True:
            try:
                rc = child.wait()
                break
            except BaseException as error:
                errors.append(repr(error))
    native_end = time.monotonic_ns()
    write(state / 'execution.json', dict(actual_argv=scope['expected_job'],
        child_identity=child_identity, actual_returncode=rc, actual_waited=True,
        started_monotonic_ns=native_start, ended_monotonic_ns=native_end,
        actual_child_wait_seconds=str(Decimal(native_end-native_start)/10**9), errors=errors))
    review_path = state / 'closed_review.json'
    review_command = ['/usr/bin/python3', '-B', str(A / 'startup_closed_review_v1.py'),
        '--scope', str(SCOPE), '--freeze', args.freeze, '--run', scope['run_dir'],
        '--driver', str(state), '--output', str(review_path)]
    with (state / 'review.log').open('x') as output:
        review = subprocess.run(review_command, cwd=W, env=env,
                                stdout=output, stderr=subprocess.STDOUT)
    after = verify_sources(scope, args.freeze)
    ended = time.monotonic_ns()
    reviewed = json.loads(review_path.read_text()) if review_path.is_file() else {}
    elapsed = Decimal(ended-started)/10**9
    passed = (rc == 0 and review.returncode == 0 and reviewed.get('passed') is True
              and not errors and before == after and elapsed <= Decimal(scope['reservation']['total']))
    result = dict(schema='mr3-p2a-v49-startup-diagnostic-result-v1', passed=passed,
        freeze=args.freeze, scope=str(SCOPE), native_returncode=rc,
        review_returncode=review.returncode, review_path=str(review_path), errors=errors,
        all_submitted_children_waited=True, source_before=before, source_after=after,
        started_monotonic_ns=started, ended_monotonic_ns=ended,
        driver_elapsed_seconds=str(elapsed), charged_by='complete enclosing actual-wait interval',
        native_qualification=False, optimizer_steps=0, gpu_calls=0, P2A_complete=False)
    write(state / 'summary.json', result)
    print(json.dumps(dict(passed=passed, native_returncode=rc, review_returncode=review.returncode,
                          driver_elapsed_seconds=str(elapsed))))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
