"""One closed-V41 descriptive read, with actual complete-wrapper fees."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from mr3_learning import preparation

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
PREFIX = Path('/tmp/mr3_p2a_v42_native_diagnosis')


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    plan = json.loads((A / 'scope_v1.json').read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != args.freeze or len(args.freeze) != 40:
        raise ValueError('exact current frozen source required')
    sources = {ROOT / rel for rel in plan['source_bindings']}
    sources.add(A / 'scope_v1.json')
    for path in sources:
        raw = path.read_bytes()
        frozen = subprocess.check_output(['git', 'show', head + ':' + str(path.relative_to(ROOT))], cwd=ROOT)
        if raw != frozen:
            raise ValueError('source differs from exact freeze: ' + str(path))
        expected = plan['source_bindings'].get(str(path.relative_to(ROOT)))
        if expected and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('source differs from prospective scope: ' + str(path))
    PREFIX.mkdir(exist_ok=False)
    outer = PREFIX / 'actual_read_wait'
    result_path = PREFIX / 'extract_v1.json'
    command = ['/usr/bin/python3', '-B', str(A / 'closed_native_extract_v1.py'),
               '--episode-directory', plan['episode_directory'], '--output', str(result_path)]
    argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
            '--scope', 'engineering', '--output', str(outer)]
    for path in sorted(sources):
        argv.extend(['--source', str(path)])
    argv.extend(['--', *command])
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    write(PREFIX / 'entry.json', {'freeze': head, 'scope': str(A / 'scope_v1.json'),
          'driver_identity': preparation.identity(os.getpid()), 'no_retry': True})
    start = time.monotonic_ns()
    child, child_identity, returncode, launch_errors = None, None, None, []
    try:
        child = subprocess.Popen(argv, cwd=W, env=env)
        child_identity = preparation.identity(child.pid)
        returncode = child.wait()
    except BaseException as error:
        launch_errors.append(repr(error))
        if child is not None:
            while True:
                try:
                    returncode = child.wait()
                    break
                except BaseException as waiting_error:
                    launch_errors.append(repr(waiting_error))
    end = time.monotonic_ns()
    fee = Decimal(end - start) / 10**9
    errors = launch_errors[:]
    result, wait = {}, {}
    try:
        wait = json.loads((outer / 'actual_wait.json').read_text())
        result = json.loads(result_path.read_text())
        assert wait['passed'] and wait['actual_argv'] == command and wait['actual_waited']
        assert wait['source_unchanged'] and start <= wait['started_monotonic_ns'] <= wait['ended_monotonic_ns'] <= end
        assert result['passed_extraction_only'] and result['sources_unchanged']
        assert result['evidence_freeze'] == plan['evidence_freeze']
        inventory = json.loads(Path(plan['closed_inventory']).read_text())
        originals = {row['original']: row for row in inventory['entries']}
        assert len(result['inputs']) == 9
        for row in result['inputs']:
            original = originals[row['path']]
            assert row['complete'] and row['bytes'] == original['original_bytes']
            assert row['sha256'] == original['original_sha256']
        assert returncode == 0 and fee <= Decimal(plan['main_actual_parent_ceiling_seconds'])
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        errors.append(repr(error))
    used = Decimal(plan['engineering_used_at_entry_seconds']) + fee
    summary = {'schema': 'mr3-v42-descriptive-actual-wait-result-v1', 'passed': not errors,
               'freeze': head, 'evidence_freeze': plan['evidence_freeze'],
               'driver_identity': preparation.identity(os.getpid()), 'wrapper_identity': child_identity,
               'actual_returncode': returncode, 'started_monotonic_ns': start, 'ended_monotonic_ns': end,
               'actual_parent_wait_seconds': str(fee), 'engineering_added_seconds': str(fee),
               'engineering_cumulative_used_seconds': str(used),
               'engineering_remaining_seconds': str(Decimal('75000') - used),
               'accounting': 'Complete parent wait; nested receipt not double charged. Static bookkeeping excluded.',
               'errors': errors, 'outer': str(outer), 'result': str(result_path),
               'worlds': 0, 'optimizer_updates': 0, 'scientific_qualification_credit': False,
               'old_failures_unchanged': True, 'external_driver_absence_review_required': True}
    write(PREFIX / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('passed', 'actual_parent_wait_seconds', 'errors')}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
