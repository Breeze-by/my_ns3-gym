"""Disabled V61 parent: one actual engineering wait, complete measured parent fee.

AST-only candidate. No old activity/run function or old budget is invoked.
Admission requires a new clean source/spec/scope freeze and the actual V60
closure ledger. Raw encoded inputs are read only by the streaming consumer.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

from mr3_learning.proxy2d_process import pidfd_open, pidfd_send_signal


ROOT = Path('/home/zhuyulab/ns3-workspace')
W_REL = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
W = ROOT / W_REL
A = W / 'report/assets/20261024_mr3_p2a_v61_cancel_forensics'
EVIDENCE_FREEZE = '935b466bd076002afdfe161b55a508938de2a8b0'
SCOPE = A / 'scope_v1.json'
SPEC = A / 'extraction_spec_v1.json'
CONSUMER = A / 'cancel_window_extract_v4.py'
DRIVER = A / 'run_cancel_forensics_v1.py'
PREFIX = Path('/tmp/mr3_p2a_v61_cancel_parent_v1')
OUTER = PREFIX / 'extractor_actual_wait'
RESULT = Path('/tmp/mr3_p2a_v61_cancel_description_v1.json')
V60_LEDGER = W / 'report/assets/20261023_mr3_p2a_v60_reader_registration/closure_ledger_v1.json'
CAP, WORK, STOP_AT = Decimal('660'), 480, Decimal('600')
MAX_METADATA = 64 * 1024 * 1024
CHAIN = {W_REL + '/mr3_learning/' + name for name in (
    '__init__.py', 'reach_execution.py', 'preparation.py', 'native_custody.py',
    'supervisor.py', 'ipc.py', 'proxy2d_process.py')}
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
       'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(s):
    # Stable fields only. No atime/full-stat equality or unsupported attribution.
    return [s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def proof(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and path == path.resolve(strict=True), 'noncanonical/symlink source path')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_METADATA,
            'source/metadata is not a bounded regular file')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as reader:
        require(fingerprint(os.fstat(reader.fileno())) == fingerprint(before), 'opened source identity changed')
        raw = reader.read(MAX_METADATA + 1)
        require(fingerprint(os.fstat(reader.fileno())) == fingerprint(before), 'source changed while open')
    require(fingerprint(path.lstat()) == fingerprint(before) and len(raw) == before.st_size,
            'source/metadata changed while hashing')
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def read(path):
    bound = proof(path)
    raw = Path(path).read_bytes()
    require(len(raw) == bound['bytes'] and sha(raw) == bound['sha256'], 'metadata changed between reads')
    def pairs(items):
        result = dict(items)
        require(len(result) == len(items), 'duplicate metadata key')
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite metadata')))


def write(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    require(len(raw) <= MAX_METADATA, 'parent metadata output exceeds fixed bound')
    with path.open('xb') as stream:
        require(stream.write(raw) == len(raw), 'short parent metadata write')
        stream.flush()
        os.fsync(stream.fileno())


def elapsed(start, end):
    require(type(start) is int and type(end) is int and 0 < start <= end, 'invalid parent clock interval')
    return Decimal(end - start) / 10**9


def identity(pid):
    tail = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'parent': int(tail[1]), 'group': int(tail[2]),
            'session': int(tail[3]), 'start_ticks': int(tail[19])}


def same(left, right):
    return type(left) is dict and type(right) is dict and all(
        type(left.get(k)) is int and left[k] > 0 and left[k] == right.get(k)
        for k in ('pid', 'parent', 'group', 'session', 'start_ticks'))


def current(saved):
    try:
        tail = Path('/proc', str(saved['pid']), 'stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return None
    if int(tail[19]) != saved['start_ticks']:
        return None
    return tail[0]  # A matching Z remains present.


def owned_signal(saved, number):
    descriptor = None
    try:
        descriptor = pidfd_open(saved['pid'])
        if current(saved) is not None:
            pidfd_send_signal(descriptor, number)
            return True
        return False
    except ProcessLookupError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def git_bytes(freeze, relative, deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'parent source-check deadline exhausted')
    return subprocess.check_output(['git', 'show', freeze + ':' + relative],
        cwd=ROOT, timeout=min(10, remaining))


def frozen(path, execution_freeze, deadline):
    actual = proof(path)
    relative = str(Path(path).relative_to(ROOT))
    raw = git_bytes(execution_freeze, relative, deadline)
    require(len(raw) == actual['bytes'] and sha(raw) == actual['sha256'],
            'current source/config differs from execution Git: ' + relative)
    return actual


def bound(ref, execution_freeze, deadline):
    require(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'}
            and type(ref['path']) is str and Path(ref['path']).is_absolute()
            and type(ref['bytes']) is int and ref['bytes'] > 0
            and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}', ref['sha256']),
            'missing exact bounded metadata reference')
    require(frozen(Path(ref['path']), execution_freeze, deadline) == ref, 'bound metadata differs')
    return read(Path(ref['path']))


def clean_freeze(execution_freeze):
    require(re.fullmatch('[0-9a-f]{40}', execution_freeze) and execution_freeze != EVIDENCE_FREEZE,
            'new exact forensic execution freeze required')
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, timeout=10)
    require(git('rev-parse', 'HEAD').decode().strip() == execution_freeze
            == git('rev-parse', 'origin/main').decode().strip()
            and not git('status', '--porcelain'), 'source must be clean at its pushed new freeze')


def check_sources(scope, execution_freeze, deadline):
    require(scope.get('schema') == 'mr3-v61-cancel-forensics-scope-v1'
            and type(scope.get('admitted')) is bool and scope['admitted'] is True,
            'pending scope is not admitted')
    require(scope.get('evidence_freeze') == EVIDENCE_FREEZE
            and scope.get('budget') == {'reservation_seconds': '660', 'work_seconds': 480,
                'owned_stop_after_parent_seconds': '600', 'signal_step_seconds': '10',
                'pilot_added_seconds': '0', 'validation_added_seconds': '0'},
            'fixed bounded forensic scope differs')
    clean_freeze(execution_freeze)
    ledger = bound(scope['entry_ledger'], execution_freeze, deadline)
    require(Path(scope['entry_ledger']['path']) == V60_LEDGER
            and ledger.get('schema') == 'mr3-engineering-closure-ledger-v1'
            and ledger.get('execution_freeze') == EVIDENCE_FREEZE
            and ledger.get('passed') is True and ledger.get('activity_passed') is False
            and ledger.get('all_saved_main_identities_fresh_gone') is True
            and ledger.get('old_FAIL_and_pending_fields_preserved') is True
            and ledger.get('P2A_complete') is False, 'actual closed V60 ledger is not ready')
    require(all(type(ledger.get(key)) is str for key in ('engineering_cumulative_seconds',
            'engineering_ceiling_seconds', 'engineering_remaining_seconds')),
            'ledger balances must be the exact decimal text')
    entry = Decimal(ledger['engineering_cumulative_seconds'])
    ceiling = Decimal(ledger['engineering_ceiling_seconds'])
    remaining = Decimal(ledger['engineering_remaining_seconds'])
    require(all(v.is_finite() for v in (entry, ceiling, remaining))
            and 0 <= entry < ceiling and remaining == ceiling - entry and remaining >= CAP,
            'actual V60 ledger cannot fund the complete new finite parent')
    spec = bound(scope['input_spec'], execution_freeze, deadline)
    require(Path(scope['input_spec']['path']) == SPEC and spec.get('admitted') is True
            and spec.get('schema') == 'mr3-cancel-window-extraction-spec-v1'
            and spec.get('evidence_freeze') == EVIDENCE_FREEZE
            and spec.get('execution_freeze_binding') == 'required-new-clean-cli'
            and spec.get('limits', {}).get('work_seconds') == WORK
            and set(spec.get('inputs', {})) == {'adapter', 'motion', 'drive', 'odom', 'launch'},
            'actual admitted extractor specification differs')
    require(spec['consumer'] == proof(CONSUMER), 'consumer source differs')
    refs = [scope['entry_ledger'], scope['input_spec']]
    for name, ledger_name in (('closed_inventory', 'closed_inventory'),
                              ('closed_quiescence_review', 'closed_metadata_review')):
        ref = {key: spec[name][key] for key in ('path', 'bytes', 'sha256')}
        bound(ref, execution_freeze, deadline)
        declared = ledger[ledger_name]
        require(all(ref[k] == declared[k] for k in ('bytes', 'sha256')),
                'extractor old closed reference differs from its actual V60 ledger')
        refs.append(ref)
    interpretation = set(spec['interpretation_sources'])
    required = CHAIN | interpretation | {str(DRIVER.relative_to(ROOT)), str(CONSUMER.relative_to(ROOT))}
    bindings = scope.get('source_bindings')
    require(type(bindings) is dict and set(bindings) == required, 'source/import/interpretation set differs')
    sources = []
    for relative, expected in bindings.items():
        require(type(relative) is str and not Path(relative).is_absolute() and '..' not in Path(relative).parts,
                'noncanonical relative source binding')
        actual = frozen(ROOT / relative, execution_freeze, deadline)
        require(expected == {k: actual[k] for k in ('bytes', 'sha256')}, 'source binding differs')
        if relative in interpretation:
            old = git_bytes(EVIDENCE_FREEZE, relative, deadline)
            require(old == (ROOT / relative).read_bytes()
                    and expected == spec['interpretation_sources'][relative],
                    'old E interpretation differs from its declared/current bytes')
        sources.append(actual)
    sources += [frozen(SCOPE, execution_freeze, deadline), *refs]
    by_path = {row['path']: row for row in sources}
    require(len(by_path) == len(sources), 'duplicate declared source/config reference')
    # No encoded raw trace is a reach_execution --source: that wrapper reads
    # its sources eagerly, so including raw would create an undeclared pass.
    raw_paths = {item['path'] for item in spec['inputs'].values()}
    require(not raw_paths.intersection(by_path), 'raw inputs must be streamed once by the consumer only')
    return sorted(sources, key=lambda row: row['path']), spec, entry, ceiling


def capture_consumer(wrapper, command):
    """V57 direct-child observation pattern; signal only saved owned PID/start."""
    try:
        pids = Path('/proc', str(wrapper['pid']), 'task', str(wrapper['pid']), 'children').read_text().split()
    except FileNotFoundError:
        return []
    rows = []
    for pid in pids:
        try:
            row = identity(int(pid))
            if current(row) == 'Z':
                continue  # Actual wrapper wait will reap it; do not infer missing argv.
            actual = Path('/proc', pid, 'cmdline').read_bytes().split(b'\0')
        except FileNotFoundError:
            continue  # Exited during observation; later original actual-wait identity is authoritative.
        require(row['parent'] == wrapper['pid'] and row['group'] == wrapper['pid']
                == row['session'], 'unexpected wrapper child ownership')
        require([part.decode() for part in actual if part] == command,
                'owned direct child does not have the exact consumer argv')
        rows.append(row)
    require(len(rows) <= 1, 'unexpected extra direct wrapper child')
    return rows


def wait_owned(child, wrapper, command, start, stop_requested, records, signals, errors):
    rc, first_stop, sent = None, None, set()
    while rc is None:
        try:
            rc = child.wait(timeout=.1)
        except subprocess.TimeoutExpired:
            pass
        except BaseException as exc:
            if len(errors) < 32:
                errors.append('actual wait interrupted; still draining: ' + repr(exc))
        try:
            if wrapper is not None and not records:
                for row in capture_consumer(wrapper, command):
                    if not any(same(row, old) for old in records):
                        records.append(row)
                        write(PREFIX / ('observed_consumer_%03d.json' % len(records)), row)
            now = time.monotonic_ns()
            if (stop_requested() or elapsed(start, now) >= STOP_AT) and first_stop is None:
                first_stop = now
                errors.append('owned self-exit guard requested; real return still required')
            if first_stop is not None:
                delay = elapsed(first_stop, now)
                number = signal.SIGKILL if delay >= 20 else signal.SIGTERM if delay >= 10 else signal.SIGINT
                for row in records:
                    key = row['pid'], row['start_ticks'], int(number)
                    if key not in sent:
                        signals.append({'identity': row, 'signal': int(number),
                                        'sent': owned_signal(row, number), 'monotonic_ns': now})
                        sent.add(key)
        except BaseException as exc:
            if len(errors) < 32:
                errors.append('owned observation/guard failure: ' + repr(exc))
    require(type(rc) is int, 'actual wait did not return an integer')
    return rc


def check_receipts(wait, result, command, sources, owner, wrapper, rc, parent_start):
    require(wait.get('schema') == 'mr3-reach-outer-actual-wait-v1'
            and wait.get('scope') == 'engineering' and wait.get('actual_waited') is True
            and type(wait.get('actual_returncode')) is int and wait.get('actual_argv') == command
            and wait.get('cwd') == str(W) and wait.get('errors') == []
            and wait.get('source_unchanged') is True and wait.get('source_before') == wait.get('source_after')
            and same(wait.get('coordinator_identity'), wrapper) and wrapper['parent'] == owner['pid'],
            'inner actual-wait/source/owned-wrapper proof differs')
    expected = {row['path']: (row['bytes'], row['sha256']) for row in sources}
    require(len(wait['source_before']) == len(expected)
            and {row['path']: (row['bytes'], row['sha256']) for row in wait['source_before']} == expected,
            'inner source set differs')
    require(Decimal(wait['actual_child_wait_seconds']) == elapsed(
            wait['started_monotonic_ns'], wait['ended_monotonic_ns'])
            and parent_start <= wait['started_monotonic_ns'] <= wait['ended_monotonic_ns'] <= time.monotonic_ns(),
            'inner elapsed or nesting differs')
    require(rc == (0 if wait.get('passed') is True else 1), 'real wrapper rc contradicts saved receipt')
    require(result.get('schema') == 'mr3-cancel-window-description-v1'
            and same(result.get('consumer_identity'), wait.get('child_identity'))
            and result.get('actual_argv') == [command[0], *command[2:]]
            and wait['started_monotonic_ns'] <= result['started_monotonic_ns']
            <= result['ended_monotonic_ns'] <= wait['ended_monotonic_ns'],
            'consumer identity/argv/clock receipt differs')
    require(result.get('source_before', {}).get('execution_freeze')
            == command[command.index('--freeze') + 1]
            and result.get('source_before', {}).get('evidence_freeze') == EVIDENCE_FREEZE,
            'consumer mixes forensic execution and old evidence freezes')
    return (rc == wait['actual_returncode'] == 0 and wait.get('passed') is True
            and result.get('passed') is True and result.get('description_complete') is True
            and result.get('scientific_qualification') is False and result.get('root_cause_proved') is False
            and result.get('old_FAIL_rejudged') is False and result.get('errors') == []
            and result.get('selection_drop_count') == 0 and result.get('unrestored_dependencies') == []
            and result.get('source_before') == result.get('source_after')
            and len(result.get('input_reports', [])) == 5
            and all(row.get('whole_binding_and_parse_complete') is True
                    and row.get('whole_input_read') is True for row in result['input_reports']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args(argv)
    require(Path(__file__).resolve() == DRIVER and Path.cwd() == W
            and Path(sys.executable).resolve() == Path('/usr/bin/python3').resolve(),
            'canonical installed driver/system Python/cwd required; /tmp draft cannot execute')
    start = time.monotonic_ns()  # Before ledger/source/spec admission, not merely before Popen.
    PREFIX.mkdir(exist_ok=False)
    owner = identity(os.getpid())
    errors, received, signal_rows, observed = [], [], [], []
    previous = {n: signal.signal(n, lambda number, frame: received.append(
        {'signal': int(number), 'monotonic_ns': time.monotonic_ns()}))
        for n in (signal.SIGTERM, signal.SIGINT)}
    scope = spec = wait = result = None
    source_before, source_after = [], []
    entry = ceiling = None
    child = wrapper = command = wrapper_argv = None
    rc = None
    receipt_passed = False
    write(PREFIX / 'entry.json', {'schema': 'mr3-v61-cancel-parent-entry-v1',
        'execution_freeze': args.freeze, 'evidence_freeze': EVIDENCE_FREEZE,
        'driver_identity': owner, 'started_monotonic_ns': start,
        'entry_budget_source': 'actual bound V60 closure ledger only; not yet inferred',
        'actual_driver_argv': [sys.executable, *sys.argv], 'no_retry': True})
    try:
        require(not RESULT.exists() and not RESULT.is_symlink(), 'exclusive result already exists')
        scope = read(SCOPE)
        source_before, spec, entry, ceiling = check_sources(scope, args.freeze, time.monotonic() + 60)
        require(not received, 'parent interrupted before submission')
        command = ['/usr/bin/python3', '-B', str(CONSUMER), '--spec', str(SPEC),
                   '--freeze', args.freeze, '--output', str(RESULT)]
        wrapper_argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
                        '--scope', 'engineering', '--output', str(OUTER)]
        wrapper_argv += [part for row in source_before for part in ('--source', row['path'])] + ['--', *command]
        write(PREFIX / 'submission.json', {'actual_wrapper_argv': wrapper_argv,
            'consumer_argv': command, 'source_before': source_before,
            'actual_ledger_entry': str(entry), 'actual_ceiling': str(ceiling),
            'raw_encoded_inputs_not_in_eager_wrapper_sources': True})
        with (PREFIX / 'wrapper_stdout.log').open('x') as console:
            child = subprocess.Popen(wrapper_argv, cwd=W, env=ENV, stdout=console,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            wrapper = identity(child.pid)
            require(wrapper['parent'] == owner['pid'] and wrapper['group'] == wrapper['pid']
                    == wrapper['session'], 'fresh owned wrapper session not observed')
            write(PREFIX / 'wrapper_identity.json', wrapper)
            rc = wait_owned(child, wrapper, command, start, lambda: bool(received),
                            observed, signal_rows, errors)
        wait = read(OUTER / 'actual_wait.json')
        result = read(RESULT)
        receipt_passed = check_receipts(wait, result, command, source_before, owner, wrapper, rc, start)
        if not receipt_passed:
            errors.append('descriptive extraction incomplete/failed; old science verdict unchanged')
    except BaseException as exc:
        errors.append(repr(exc))
    finally:
        if child is not None and rc is None:
            rc = wait_owned(child, wrapper, command, start, lambda: True,
                            observed, signal_rows, errors)
        if scope is not None and source_before:
            try:
                remaining_tail = max(.001, 650 - float(elapsed(start, time.monotonic_ns())))
                source_after, _, after_entry, after_ceiling = check_sources(
                    scope, args.freeze, time.monotonic() + remaining_tail)
                require(after_entry == entry and after_ceiling == ceiling and source_after == source_before,
                        'ledger/source/spec/closed-reference drift after actual wait')
            except BaseException as exc:
                errors.append('source-after: ' + repr(exc))
        known = ([wrapper] if wrapper is not None else []) + observed
        if wait is not None and type(wait.get('child_identity')) is dict:
            if not any(same(wait['child_identity'], row) for row in known):
                known.append(wait['child_identity'])  # Original same-object saved start from actual wait.
        absence = []
        for row in known:
            try:
                state = current(row)
                absence.append({'identity': row, 'current_state': state,
                                'original_identity_gone': state is None,
                                'observed_monotonic_ns': time.monotonic_ns()})
                require(state is None, 'saved owned process remains present/Z')
            except BaseException as exc:
                errors.append('owned-close: ' + repr(exc))
        write(PREFIX / 'work_close.json', {'source_after': source_after, 'owned_observations': absence,
              'signals': signal_rows, 'errors': errors, 'actual_wrapper_returncode': rc,
              'actual_wrapper_waited': child is not None and type(rc) is int})
    end = time.monotonic_ns()  # Includes source-before/after, refs, actual wait, cleanup and work_close fsync.
    fee = elapsed(start, end)
    passed = (not errors and not received and receipt_passed and source_before == source_after
              and bool(source_before) and entry is not None and ceiling is not None
              and fee <= CAP and entry + fee <= ceiling)
    summary = {'schema': 'mr3-v61-cancel-parent-result-v1', 'passed': passed,
        'execution_freeze': args.freeze, 'evidence_freeze': EVIDENCE_FREEZE,
        'driver_identity': owner, 'wrapper_identity': wrapper,
        'consumer_identity': None if wait is None else wait.get('child_identity'),
        'actual_wrapper_argv': wrapper_argv, 'consumer_argv': command,
        'actual_wrapper_returncode': rc, 'actual_wrapper_waited': child is not None and type(rc) is int,
        'started_monotonic_ns': start, 'ended_monotonic_ns': end,
        'actual_parent_seconds': str(fee), 'engineering_added_seconds': str(fee),
        'engineering_entry_seconds': None if entry is None else str(entry),
        'engineering_ceiling_seconds': None if ceiling is None else str(ceiling),
        'engineering_cumulative_seconds': None if entry is None else str(entry + fee),
        'engineering_remaining_seconds': None if entry is None or ceiling is None else str(ceiling-entry-fee),
        'entry_ledger': None if scope is None else scope.get('entry_ledger'),
        'complete_parent_reservation_seconds': '660', 'consumer_work_seconds': 480,
        'pilot_added_seconds': '0', 'validation_added_seconds': '0',
        'source_before': source_before, 'source_after': source_after,
        'errors': errors, 'received_signals': received,
        'outer_actual_wait': str(OUTER / 'actual_wait.json'), 'description_result': str(RESULT),
        'accounting': 'One measured parent interval before admission/source checks through post-source/owned-close and work_close fsync; inner engineering wait is nested, never added again. Final immutable summary emission is the receipt boundary, not a fabricated root-tool interval. Overrun is fully charged FAIL.',
        'owned_guard': 'Only direct live-saved consumer PID/start via pidfd; at600 INT, then10 TERM, then10 KILL. Always actual wrapper wait. Cooperative guard, no hard realtime bound or process-group signals.',
        'root_cause_proved': False, 'scientific_qualification_credit': False,
        'old_failures_preserved': True, 'models_loaded': False, 'worlds': 0,
        'optimizer_updates': 0, 'no_retry': True,
        'external_actual_tool_reap_and_driver_fresh_gone_required': True}
    try:
        write(PREFIX / 'summary.json', summary)
        print(json.dumps({'passed': passed, 'actual_parent_seconds': str(fee), 'errors': errors}), flush=True)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
