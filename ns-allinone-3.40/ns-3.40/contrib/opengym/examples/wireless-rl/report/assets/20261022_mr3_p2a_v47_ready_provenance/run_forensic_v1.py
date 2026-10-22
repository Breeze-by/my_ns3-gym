"""One declared closed-ready-provenance read, charging the complete actual outer wait."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
PREFIX = Path('/tmp/mr3_p2a_v47_ready_provenance')


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def identity(pid):
    fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0],
            'parent': int(fields[1]), 'group': int(fields[2]), 'session': int(fields[3])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    plan = json.loads((A / 'scope_v1.json').read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != args.freeze or len(head) != 40:
        raise ValueError('exact current frozen source required')
    sources = {ROOT / relative for relative in plan['source_bindings']}
    sources.add(A / 'scope_v1.json')
    for path in sorted(sources):
        raw = path.read_bytes()
        frozen = subprocess.check_output(['git', 'show', head + ':' + str(path.relative_to(ROOT))], cwd=ROOT)
        if raw != frozen:
            raise ValueError('source differs from exact freeze: ' + str(path))
        expected = plan['source_bindings'].get(str(path.relative_to(ROOT)))
        if expected and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('source differs from prospective scope: ' + str(path))
    PREFIX.mkdir(exist_ok=False)
    outer, result_path = PREFIX / 'actual_read_wait', PREFIX / 'extract_v1.json'
    command = ['/usr/bin/python3', '-B', str(A / 'closed_ready_extract_v1.py'),
               '--source-freeze', head, '--output', str(result_path)]
    argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
            '--scope', 'engineering', '--output', str(outer)]
    for path in sorted(sources):
        argv.extend(['--source', str(path)])
    argv.extend(['--', *command])
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    write(PREFIX / 'entry.json', {'freeze': head, 'scope': str(A / 'scope_v1.json'),
          'driver_identity': identity(os.getpid()), 'no_retry': True})
    start = time.monotonic_ns()
    child, child_identity, returncode, errors = None, None, None, []
    try:
        child = subprocess.Popen(argv, cwd=W, env=env)
        child_identity = identity(child.pid)
        returncode = child.wait()
    except BaseException as error:
        errors.append(repr(error))
        if child is not None:
            while True:
                try:
                    returncode = child.wait()
                    break
                except BaseException as waiting_error:
                    errors.append(repr(waiting_error))
    end = time.monotonic_ns()
    fee = Decimal(end - start) / 10**9
    try:
        wait = json.loads((outer / 'actual_wait.json').read_text())
        result = json.loads(result_path.read_text())
        assert wait['passed'] and wait['actual_argv'] == command and wait['actual_waited']
        assert wait['source_unchanged'] and start <= wait['started_monotonic_ns'] <= wait['ended_monotonic_ns'] <= end
        assert result['diagnostic_only'] and not result['scientific_qualification_claimed']
        assert result['source_freeze'] == head and result['native_freeze'] == plan['evidence_freeze']
        originals = {row['original']: row for row in json.loads(Path(plan['closed_inventory']).read_text())['entries']}
        assert len(result['inputs']) == 2 and set(row['path'] for row in result['inputs']) == set(plan['input_paths'])
        for row in result['inputs']:
            original = originals[row['path']]
            assert row['bytes'] == original['original_bytes'] and row['sha256'] == original['original_sha256']
            assert row['stat_before'] == row['stat_after']
        assert returncode == 0 and fee <= Decimal(plan['main_actual_parent_ceiling_seconds'])
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        errors.append(repr(error))
    used = Decimal(plan['engineering_used_at_entry_seconds']) + fee
    summary = {'schema': 'mr3-v47-ready-provenance-actual-wait-v1', 'passed': not errors,
        'freeze': head, 'evidence_freeze': plan['evidence_freeze'],
        'driver_identity': identity(os.getpid()), 'wrapper_identity': child_identity,
        'actual_returncode': returncode, 'started_monotonic_ns': start, 'ended_monotonic_ns': end,
        'actual_parent_wait_seconds': str(fee), 'engineering_added_seconds': str(fee),
        'engineering_cumulative_used_seconds': str(used),
        'engineering_remaining_seconds': str(Decimal('75000') - used),
        'accounting': 'Complete parent actual wait; nested wait not double charged.',
        'errors': errors, 'outer': str(outer), 'result': str(result_path),
        'worlds': 0, 'optimizer_updates': 0, 'scientific_qualification_credit': False,
        'old_failures_preserved': True, 'external_driver_absence_review_required': True}
    write(PREFIX / 'summary.json', summary)
    print(json.dumps({key: summary[key] for key in ('passed', 'actual_parent_wait_seconds', 'errors')}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
