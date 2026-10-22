"""Artificial stdlib lifecycle checks; never imports the original audit reader.

Prepared only. Root must source-seal and actually wait this CPU command before
claiming results. Every toy process belongs to this invocation and is waited.
"""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time
import traceback
from unittest.mock import patch
import uuid

HERE = Path(__file__).resolve().parent
GUARD = HERE / 'profile_guard_v3.py'
V1 = Path('/tmp/mr3_p2a_single_ep_runtime_profile_candidate')
V2 = Path('/tmp/mr3_p2a_single_ep_runtime_profile_candidate_v2')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def sha(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def sources():
    paths = [HERE / name for name in ('profile_common_v1.py', 'runtime_child_v1.py',
        'profile_guard_v3.py', 'lifecycle_selfcheck_v1.py', 'v2_preservation_manifest.json')]
    manifest = json.loads((HERE / 'v2_preservation_manifest.json').read_text())
    for expected in manifest['sources']:
        actual = sha(Path(expected['path']))
        require(actual == expected, 'v2 original changed: ' + expected['path'])
    original = json.loads((V2 / 'v1_preservation_manifest.json').read_text())
    for expected in original['sources']:
        require(sha(Path(expected['path'])) == expected, 'v1 original changed: ' + expected['path'])
    paths += [Path(row['path']) for row in manifest['sources']]
    paths += [Path(row['path']) for row in original['sources']]
    return [sha(path) for path in sorted(set(paths))]


def load_guard():
    # Isolated artificial package for relative stdlib helper import only. No
    # sys.path change, production module injection or original reader import.
    name = '_mr3_artificial_profile_lifecycle_v3'
    spec = importlib.util.spec_from_file_location(name, GUARD,
        submodule_search_locations=[str(HERE)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(output):
    output.mkdir(exist_ok=False)
    started = time.monotonic_ns()
    before = sources()
    guard = load_guard()
    parent = guard.common.identity(os.getpid())
    children, rows, outer_signals, fatal_errors, fixture_outputs = [], [], [], [], []

    def receive(number, _frame):
        outer_signals.append(dict(signal=signal.Signals(number).name, monotonic_ns=time.monotonic_ns()))
    previous = {number: signal.signal(number, receive) for number in (signal.SIGTERM, signal.SIGINT)}

    def launch(mode):
        code = "import signal,sys\n"
        if mode == 'ignore-term':
            code += 'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
        code += "print('READY',flush=True)\n"
        code += 'raise SystemExit(7)\n' if mode == 'normal' else 'sys.stdin.read()\n'
        argv = ['/usr/bin/python3', '-B', '-c', code]
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=True,
            env=guard.common.clean_environment())
        record = dict(actual_argv=argv, started_monotonic_ns=time.monotonic_ns(), process=child)
        children.append(record)
        record['identity'] = guard.common.identity(child.pid)
        require(record['identity']['group'] == record['identity']['session'] == child.pid,
                'toy did not enter its owned session')
        require(select.select([child.stdout], [], [], 5.)[0], 'toy READY timeout')
        require(child.stdout.readline() == b'READY\n', 'toy failed before READY')
        return child, record

    def reap_record(child, record, rc):
        require(type(rc) is int and child.returncode == rc, 'no actual integer Popen.wait result')
        record.update(actual_returncode=rc, actual_waited=True, ended_monotonic_ns=time.monotonic_ns())
        try:
            current = guard.common.identity(record['identity']['pid'])
            gone = current['start_ticks'] != record['identity']['start_ticks']
            record['fresh_observation'] = current
        except (FileNotFoundError, ProcessLookupError):
            gone = True
            record['fresh_observation'] = 'absent_proc_stat'
        record['original_identity_gone'] = gone
        require(gone, 'real waited toy identity remains present, including Z')

    def check_normal():
        child, record = launch('normal')
        rc = child.wait(timeout=5.)
        reap_record(child, record, rc)
        require(rc == 7, 'nonzero normal return was changed')
        return dict(observed_returncode=rc)

    def check_term():
        child, record = launch('term')
        errors, sent = [], []
        rc = guard.stop_and_wait(child, errors, sent)
        reap_record(child, record, rc)
        require(rc == -signal.SIGTERM and [row['signal'] for row in sent] == ['SIGTERM'] and not errors,
                'default-TERM toy did not preserve its real signal rc')
        return dict(actual_returncode=rc, sent=sent, cleanup_errors=errors)

    def check_ignore_term_and_cleanup_parent_signals():
        child, record = launch('ignore-term')
        waiting, sender_errors, sent_to_parent, captured = threading.Event(), [], [], {}

        class Observer:
            pid = child.pid
            def send_signal(self, number):
                return child.send_signal(number)
            def wait(self, timeout=None):
                waiting.set()
                return child.wait(timeout=timeout)

        def sender():
            try:
                require(waiting.wait(5.), 'never entered cleanup wait')
                for number in (signal.SIGTERM, signal.SIGINT):
                    current = guard.common.identity(parent['pid'])
                    require(current['start_ticks'] == parent['start_ticks'], 'test parent identity changed')
                    os.kill(parent['pid'], number)
                    sent_to_parent.append(dict(signal=signal.Signals(number).name, monotonic_ns=time.monotonic_ns()))
            except BaseException as error:
                sender_errors.append(repr(error))

        def artificial_run(_scope, _freeze, _output, received_signals):
            errors, signals_sent = [], []
            thread = threading.Thread(target=sender)
            thread.start()
            try:
                rc = guard.stop_and_wait(Observer(), errors, signals_sent)
                reap_record(child, record, rc)
            finally:
                thread.join()  # No lingering test sender may signal another case.
            captured.update(actual_returncode=rc, cleanup_errors=errors, sent_to_child=signals_sent,
                received_parent_signals=list(received_signals), sent_to_parent=sent_to_parent,
                sender_errors=sender_errors)
            return dict(passed=False, actual_returncode=rc,
                        actual_guard_seconds=str(Decimal(time.monotonic_ns()-record['started_monotonic_ns'])/10**9))

        argv = ['artificial-guard', '--scope', '/unused/toy-scope', '--execution-freeze', 'a'*40,
                '--output', '/unused/toy-output']
        with patch.object(guard, 'run', side_effect=artificial_run), patch.object(sys, 'argv', argv):
            main_rc = guard.main()  # Install and use the real production parent handler.
        require(main_rc == 1 and captured['actual_returncode'] == -signal.SIGKILL,
                'interrupted cleanup must reap real KILL and remain FAIL')
        require(not sender_errors and {row['signal'] for row in captured['received_parent_signals']}
                == {'SIGTERM', 'SIGINT'}, 'both real parent signals were not retained')
        signals_sent = captured['sent_to_child']
        require([row['signal'] for row in signals_sent] == ['SIGTERM', 'SIGKILL'], 'TERM/KILL ordering differs')
        require(signals_sent[1]['monotonic_ns'] - signals_sent[0]['monotonic_ns'] >= 10_000_000_000,
                'real ten-second TERM grace was shortened')
        require(not captured['cleanup_errors'], 'unexpected cleanup exception')
        return captured

    def check_wait_exceptions_then_actual_wait():
        child, record = launch('term')
        injected, observed = [InterruptedError('toy interrupted'), KeyboardInterrupt('toy interrupt'),
                             RuntimeError('toy runtime interruption')], []
        class Delegate:
            pid = child.pid
            def send_signal(self, number):
                return child.send_signal(number)
            def wait(self, timeout=None):
                if injected:
                    error = injected.pop(0)
                    observed.append(type(error).__name__)
                    raise error
                return child.wait(timeout=timeout)
        errors, sent = [], []
        rc = guard.stop_and_wait(Delegate(), errors, sent)
        reap_record(child, record, rc)
        require(rc == -signal.SIGTERM and len(errors) == 3 and not injected,
                'wait exceptions were dropped or rc was fabricated')
        return dict(actual_returncode=rc, injected_exception_types=observed, cleanup_errors=errors)

    def check_invalid_scope_cannot_launch():
        fake_root = output / 'invalid_fixture'
        fake_root.mkdir()
        receipts = []
        for number, payload in enumerate((None, {}, {'schema': 'mr3-single-ep-runtime-profile-scope-v1',
                'native_evidence_freeze': guard.common.EVIDENCE_FREEZE,
                'episode': str(guard.common.EPISODE), 'epoch': None})):
            scope = fake_root / f'scope{number}.json'
            write(scope, payload)
            destination = Path('/tmp') / ('mr3_single_ep_runtime_profile_selfcheck_' + uuid.uuid4().hex)
            fixture_outputs.append(str(destination))
            with patch.object(guard.common, 'ROOT', fake_root), patch.object(guard.common, 'W', Path.cwd()), \
                    patch.object(guard, '__package__', 'report.assets.artificial_lifecycle_fixture'), \
                    patch.object(guard.common, 'source_rows', return_value=[]), \
                    patch.object(guard, 'parent_admission', return_value={}), \
                    patch.object(guard.common, 'input_rows', return_value=[]), \
                    patch.object(guard.subprocess, 'check_output') as git, \
                    patch.object(guard.subprocess, 'Popen') as popen:
                result = guard.run(scope, 'a'*40, destination)
            popen.assert_not_called(); git.assert_not_called()
            require(result['passed'] is False and result['actual_waited'] is False
                    and result['child_identity'] is None, 'invalid scope was credited as a real profile')
            receipts.append(dict(guard_receipt=str(destination/'guard_receipt.json'), errors=result['errors']))
        return dict(artificial_postchecks_stubbed=True, invalid_scope_receipts=receipts)

    def check_signal_after_passed_computation_forces_final_rc():
        captured = {}
        def artificial_run(_scope, _freeze, _output, received_signals):
            result = dict(passed=True, actual_returncode=0, actual_guard_seconds='0')
            os.kill(os.getpid(), signal.SIGTERM)  # Actual handler event in the old race window.
            write(output/'artificial_early_passed_receipt.json', dict(result,
                received_parent_signals=received_signals, fixture_only=True))
            captured['received_parent_signals'] = list(received_signals)
            return result
        argv = ['artificial-guard', '--scope', '/unused', '--execution-freeze', 'a'*40, '--output', '/unused']
        with patch.object(guard, 'run', side_effect=artificial_run), patch.object(sys, 'argv', argv):
            rc = guard.main()
        require(rc == 1 and captured['received_parent_signals'], 'late recorded signal retained rc0')
        return dict(actual_guard_main_returncode=rc, **captured)

    try:
        for name, function in (
                ('normal_real_wait', check_normal), ('TERM_real_wait', check_term),
                ('ignore_TERM_KILL_and_cleanup_parent_TERM_INT', check_ignore_term_and_cleanup_parent_signals),
                ('delegated_wait_exceptions_then_real_wait', check_wait_exceptions_then_actual_wait),
                ('invalid_null_scope_no_launch', check_invalid_scope_cannot_launch),
                ('late_signal_final_return_FAIL', check_signal_after_passed_computation_forces_final_rc)):
            row = dict(id=name, started_monotonic_ns=time.monotonic_ns(), passed=False, fixture_only=True)
            rows.append(row)
            try:
                row['result'] = function()
                row['passed'] = True
            except BaseException as error:
                row['error'] = repr(error); row['traceback'] = traceback.format_exc()
            finally:
                row['ended_monotonic_ns'] = time.monotonic_ns()
    finally:
        # No assertion, failed READY, injected wait exception or test signal can
        # leave an owned toy unreaped. These are actual process waits, not mocks.
        for record in children:
            child = record['process']
            try:
                rc = child.wait() if child.returncode is not None else guard.stop_and_wait(child, fatal_errors, [])
                reap_record(child, record, rc)
            except BaseException as error:
                fatal_errors.append('toy final cleanup: ' + repr(error))
                while child.returncode is None:
                    try:
                        rc = guard.stop_and_wait(child, fatal_errors, [])
                        reap_record(child, record, rc)
                    except BaseException as again:
                        fatal_errors.append('continuing actual toy wait: ' + repr(again))
            finally:
                for stream in (child.stdin, child.stdout):
                    if stream is not None:
                        stream.close()
        for number, handler in previous.items():
            signal.signal(number, handler)
    after = sources()
    children_json = [{key: value for key, value in row.items() if key != 'process'} for row in children]
    ended = time.monotonic_ns()
    passed = (len(rows) == 6 and all(row['passed'] for row in rows) and before == after
        and not fatal_errors and not outer_signals and all(row.get('actual_waited') is True
        and row.get('original_identity_gone') is True for row in children_json))
    result = dict(schema='mr3-single-ep-profile-lifecycle-artificial-selfcheck-v1', passed=passed,
        source_before=before, source_after=after, source_unchanged=before==after,
        v1_v2_original_hashes_preserved=True, parent_identity=parent, cases=rows,
        actual_toy_children=children_json, fixture_output_dirs=fixture_outputs,
        external_parent_signals=outer_signals, cleanup_errors=fatal_errors,
        started_monotonic_ns=started, ended_monotonic_ns=ended,
        actual_selfcheck_seconds=str(Decimal(ended-started)/10**9),
        raw_V50_inputs_read=False, original_runtime_imported=False, world_or_model_started=False,
        qualification_credit=False, proof_scope='Artificial owned-process lifecycle and admission rejection only.')
    write(output/'result.json', result)
    print(json.dumps(dict(passed=passed, cases=len(rows), actual_toy_children=len(children_json),
                         output=str(output/'result.json'))), flush=True)
    return 0 if passed and not outer_signals else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.output.is_absolute() and args.output.parent == Path('/tmp'), 'new exclusive /tmp output required')
    return run(args.output)


if __name__ == '__main__':
    raise SystemExit(main())
