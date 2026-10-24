"""Execute the sealed strict V44 chain once, with actual waits and no retries."""

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import time

from mr3_learning import preparation

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSETS = Path(__file__).resolve().parent
PLAN = ASSETS / 'plan_v1.json'
PREFIX = Path('/tmp/mr3_p2a_reach_v44')
MODULE = 'report.assets.20261022_mr3_p2a_v44_support_native.'
ENTRY_ENGINEERING = Decimal('50041.2338414596018')
ENGINEERING_CEILING = Decimal('75000')
PHASE_CAPS = {'pilot': Decimal('2905.9547395464029'), 'validation': Decimal('9000')}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def interval_union(rows, scope):
    intervals = sorted((row['started_monotonic_ns'], row['ended_monotonic_ns'])
                       for row in rows if row['scope'] == scope)
    total, start, end = 0, None, None
    for lo, hi in intervals:
        if start is None:
            start, end = lo, hi
        elif lo <= end:
            end = max(end, hi)
        else:
            total += end - start
            start, end = lo, hi
    if start is not None:
        total += end - start
    return Decimal(total) / 10**9


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    state = Path(str(PREFIX) + '_driver_v1')
    state.mkdir(exist_ok=False)
    plan = read(PLAN)
    python = plan['learner_python']
    qualification = Path(str(PREFIX) + '_qualification.json')
    matrix_outer = Path(str(PREFIX) + '_matrix_wait')
    sources = {ROOT / path for path in plan['source_bindings']}
    sources.update(Path(path) if Path(path).is_absolute() else ROOT / path
                   for path in plan['library_bindings'])
    sources.update([PLAN, *ASSETS.glob('*.py')])
    source_flags = [part for path in sorted(sources) for part in ('--source', str(path))]
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='0')
    env.pop('PYTHONPATH', None)
    rows, errors, completed, policy_submitted = [], [], [], []
    matrix_submitted = False
    write(state / 'entry.json', {'freeze': args.freeze, 'plan': str(PLAN),
          'driver_identity': preparation.identity(os.getpid()),
          'engineering_entry_used_seconds': str(ENTRY_ENGINEERING),
          'engineering_ceiling_seconds': str(ENGINEERING_CEILING),
          'started_monotonic_ns': time.monotonic_ns(), 'no_retry': True})

    def phase(name, scope, command, outer=None):
        outer = outer or Path(str(PREFIX) + '_' + name + '_wait')
        argv = [python, '-B', '-m', 'mr3_learning.reach_execution',
                '--scope', scope, '--output', str(outer), *source_flags, '--', *command]
        print(json.dumps({'event': 'phase_start', 'phase': name, 'scope': scope,
                          'command': command, 'outer': str(outer)}), flush=True)
        started = time.monotonic_ns()
        rc, child_identity, value, phase_errors = None, None, None, []
        try:
            child = subprocess.Popen(argv, cwd=WIRELESS, env=env)
            child_identity = preparation.identity(child.pid)
            rc = child.wait()
        except BaseException as error:
            phase_errors.append(repr(error))
            if 'child' in locals():
                # Every submitted child is drained even after an interruption.
                while True:
                    try:
                        rc = child.wait()
                        break
                    except BaseException as waiting_error:
                        phase_errors.append(repr(waiting_error))
        ended = time.monotonic_ns()
        elapsed = Decimal(ended - started) / 10**9
        try:
            value = read(outer / 'actual_wait.json')
            inner = Decimal(value['ended_monotonic_ns'] - value['started_monotonic_ns']) / 10**9
            if not (value['actual_waited'] and value['source_unchanged']
                    and value['actual_argv'] == command and value['errors'] == []
                    and Decimal(value['actual_child_wait_seconds']) == inner
                    and started <= value['started_monotonic_ns'] <= value['ended_monotonic_ns'] <= ended):
                raise ValueError('invalid actual-wait/source receipt')
        except BaseException as error:
            phase_errors.append(repr(error))
        row = {'name': name, 'scope': scope, 'outer': str(outer), 'returncode': rc,
               'actual_returncode': value.get('actual_returncode') if isinstance(value, dict) else None,
               'passed': not phase_errors and rc == 0 and isinstance(value, dict) and value.get('passed') is True,
               'wrapper_identity': child_identity, 'receipt_errors': phase_errors,
               'started_monotonic_ns': started, 'ended_monotonic_ns': ended,
               'actual_seconds': str(elapsed),
               'accounting_basis': 'parent actual wait for complete wrapper; nested child receipt is not double charged',
               'inner_actual_seconds': value.get('actual_child_wait_seconds') if isinstance(value, dict) else None}
        rows.append(row)
        with (state / 'ledger.jsonl').open('a') as stream:
            stream.write(json.dumps(row) + '\n')
        print(json.dumps({'event': 'phase_end', **row}), flush=True)
        if phase_errors:
            raise ValueError('phase receipt/launch failed after actual fee recorded: ' + name + ': ' + repr(phase_errors))
        return row['passed']

    def matrix_absence(name, extra=()):
        output = Path(str(PREFIX) + '_' + name + '.json')
        command = ['/usr/bin/python3', '-B', str(ASSETS / 'external_absence_v1.py'),
                   '--plan', str(PLAN), '--matrix-outer', str(matrix_outer), '--output', str(output)]
        for path in extra:
            if Path(path).exists():
                command.extend(['--extra', str(path)])
        return phase(name, 'engineering', command)

    passed = False
    try:
        if not phase('preflight', 'engineering', [python, '-m', MODULE + 'preflight_v1',
                     '--plan', str(PLAN), '--freeze', args.freeze,
                     '--output', plan['preflight']['path']]):
            raise ValueError('fresh frozen preflight failed; no native submitted')
        matrix_submitted = True
        matrix_ok = phase('matrix', 'engineering', [python, '-m', 'mr3_learning.reach_preparation',
                          '--plan', str(PLAN), '--freeze', args.freeze], matrix_outer)
        matrix_ok = matrix_ok and Decimal(rows[-1]['actual_seconds']) <= 18000
        absent = matrix_absence('matrix_absence')
        if not matrix_ok or not absent:
            raise ValueError('matrix or complete saved-identity absence failed')
        if not phase('qualification', 'engineering', [python, '-m', 'mr3_learning.reach_preparation',
                     '--plan', str(PLAN), '--freeze', args.freeze, '--qualify', str(matrix_outer / 'actual_wait.json'),
                     '--output', str(qualification)]):
            raise ValueError('full fresh matrix qualification failed')
        completed.append('matrix_qualification')
        external_rows = [row for row in rows if row['name'] in ('matrix_absence', 'qualification')]
        external_used = sum((Decimal(row['actual_seconds']) for row in external_rows), Decimal(0))
        matrix_row = next(row for row in rows if row['name'] == 'matrix')
        external_endpoint = Decimal(rows[-1]['ended_monotonic_ns'] - matrix_row['ended_monotonic_ns']) / 10**9
        remaining = ENGINEERING_CEILING - ENTRY_ENGINEERING - interval_union(rows, 'engineering')
        if external_used > 300 or external_endpoint > 300 or remaining < 1800 + max(Decimal(0), Decimal(300) - external_used):
            raise ValueError('full minimum plus unused external reserve is not available')
        write(state / 'minimum_admission.json', {'passed': True,
              'engineering_actual_remaining_seconds': str(remaining),
              'external_actual_seconds_already_charged': str(external_used),
              'required_minimum_reservation_seconds': '1800',
              'unused_external_reserve_seconds': str(max(Decimal(0), Decimal(300) - external_used))})
        for stage in ('minimum', 'pilot', 'validation'):
            scope = 'engineering' if stage == 'minimum' else stage
            outer = Path(str(PREFIX) + '_' + stage + '_wait')
            policy_submitted.append(stage)
            ok = phase(stage, scope, [python, '-m', 'mr3_learning.reach_policy_chain',
                       '--plan', str(PLAN), '--freeze', args.freeze,
                       '--qualification', str(qualification), '--stage', stage], outer)
            if stage == 'minimum':
                ok = ok and Decimal(rows[-1]['actual_seconds']) <= 1800
            final = Path(str(PREFIX) + '_' + stage + '_final.json')
            finalized = phase(stage + '_final', scope,
                              [python, '-m', 'mr3_learning.reach_policy_chain', '--plan', str(PLAN),
                               '--freeze', args.freeze, '--stage', stage,
                               '--finalize-outer-wait', str(outer / 'actual_wait.json'), '--output', str(final)])
            accounting_ok = True
            if stage in PHASE_CAPS:
                relevant = [row for row in rows if row['name'] in (stage, stage + '_final')]
                reserve = Decimal(plan['policy_stages'][stage]['external_finalize_reserve_seconds'])
                endpoint = Decimal(relevant[-1]['ended_monotonic_ns'] - relevant[0]['started_monotonic_ns']) / 10**9
                accounting_ok = (reserve == 300 and Decimal(relevant[-1]['actual_seconds']) <= reserve
                                 and interval_union(rows, scope) <= PHASE_CAPS[stage]
                                 and endpoint <= PHASE_CAPS[stage])
                write(state / (stage + '_actual_fee_admission.json'),
                      {'passed': accounting_ok, 'scope': scope,
                       'actual_main_and_final_union_seconds': str(interval_union(rows, scope)),
                       'complete_endpoint_seconds': str(endpoint), 'original_cap_seconds': str(PHASE_CAPS[stage]),
                       'external_reserve_seconds': str(reserve),
                       'external_actual_seconds': relevant[-1]['actual_seconds'], 'no_fee_moved_to_engineering': True})
            else:
                external_used = sum((Decimal(row['actual_seconds']) for row in rows
                                     if row['name'] in ('matrix_absence', 'qualification', 'minimum_final')), Decimal(0))
                accounting_ok = external_used <= 300
            if not ok or not finalized or not accounting_ok:
                spec = plan['policy_stages'][stage]
                matrix_absence(stage + '_failure_absence',
                               [outer, spec['output_directory'], spec['run_directory']])
                raise ValueError('required policy stage failed: ' + stage)
            completed.append(stage)
        passed = completed == ['matrix_qualification', 'minimum', 'pilot', 'validation']
    except BaseException as error:
        errors.append(repr(error))
    finally:
        if matrix_submitted:
            extras = []
            for stage in policy_submitted:
                extras.extend([Path(str(PREFIX) + '_' + stage + '_wait'),
                               plan['policy_stages'][stage]['output_directory'],
                               plan['policy_stages'][stage]['run_directory']])
                extras.append(Path(str(PREFIX) + '_' + stage + '_final_wait'))
            try:
                if not matrix_absence('chain_final_absence', extras):
                    errors.append('final complete chain saved-identity absence failed')
            except BaseException as error:
                errors.append('final absence attempt: ' + repr(error))
    engineering_external = sum((Decimal(row['actual_seconds']) for row in rows
                                if row['scope'] == 'engineering'
                                and row['name'] not in ('preflight', 'matrix', 'minimum')), Decimal(0))
    if engineering_external > 300:
        errors.append('complete engineering external actual fees exceed the reserved300: ' + str(engineering_external))
    if ENTRY_ENGINEERING + interval_union(rows, 'engineering') > ENGINEERING_CEILING:
        errors.append('actual engineering ceiling exceeded; preserve full real fees')
    for scope, cap in PHASE_CAPS.items():
        if interval_union(rows, scope) > cap:
            errors.append('actual full phase fee exceeds original quota: ' + scope)
    result = {'schema': 'mr3-v44-actual-chain-driver-result-v1', 'passed': passed and not errors,
              'freeze': args.freeze, 'plan': str(PLAN), 'completed_stages': completed,
              'errors': errors, 'actual_waits': rows,
              'engineering_added_union_seconds': str(interval_union(rows, 'engineering')),
              'engineering_cumulative_used_seconds': str(ENTRY_ENGINEERING + interval_union(rows, 'engineering')),
              'pilot_added_union_seconds': str(interval_union(rows, 'pilot')),
              'validation_added_union_seconds': str(interval_union(rows, 'validation')),
              'engineering_external_actual_seconds': str(engineering_external),
              'accounting_basis': 'scope-wise parent actual-wait interval union; nested receipts not added again; bookkeeping gaps excluded from fees and retained in phase deadlines',
              'old_failures_preserved': True, 'p2b_gateway_started': False,
              'p2a_claim_requires_independent_final_review': True,
              'driver_identity': preparation.identity(os.getpid()), 'ended_monotonic_ns': time.monotonic_ns()}
    write(state / 'summary.json', result)
    print(json.dumps({'event': 'chain_closed', 'passed': result['passed'],
                      'completed_stages': completed, 'errors': errors, 'result': str(state / 'summary.json')}), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
