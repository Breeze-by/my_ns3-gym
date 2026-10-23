"""One bounded debugger observation of the unchanged V55 startup crash."""
import argparse
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261023_mr3_p2a_v56_startup_gdb'
PRIOR = W / 'report/assets/20261023_mr3_p2a_v55_passive_plant'
PREFIX = Path('/tmp/mr3_p2a_v56_startup_gdb_v1')
ENTRY = Decimal('90370.2852481186018')
CEILING, CAP = Decimal('120000'), Decimal('300')
module = importlib.util.spec_from_file_location('v56_original_source_admission', PRIOR / 'run_passive_pair_v1.py')
d = importlib.util.module_from_spec(module)
module.loader.exec_module(d)
from mr3_learning.supervisor import descendants


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    d.require(len(args.freeze) == 40 and all(c in '0123456789abcdef' for c in args.freeze), 'exact freeze required')
    d.require(Path(__file__).resolve() == A / 'run_startup_gdb_v1.py' and Path.cwd() == W,
              'canonical driver/cwd required')
    PREFIX.mkdir(exist_ok=False)
    owner = d.identity(os.getpid())
    d.write(PREFIX / 'entry.json', {'schema': 'mr3-v56-gdb-entry-v1',
        'identity': owner, 'actual_argv': [sys.executable, *sys.argv],
        'freeze': args.freeze, 'engineering_entry_seconds': str(ENTRY),
        'engineering_ceiling_seconds': str(CEILING), 'parent_cap_seconds': str(CAP)})
    received = []
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda n, _f: received.append(n))
    errors, rows, after, observed, sent = [], [], [], {}, set()
    child = wrapper = None
    rc = started = ended = None
    outer = PREFIX / 'actual_wait'
    try:
        spec = d.read(A / 'spec_v1.json')
        d.require(spec['engineering_entry_seconds'] == str(ENTRY) and
                  spec['parent_cap_seconds'] == str(CAP) and CEILING - ENTRY >= CAP,
                  'debugger entry budget differs')
        # Reuse only the original byte admission, never its old activity fee or run_case.
        _, rows = d.verify_inputs(d.read(d.SCOPE), args.freeze)
        for path in (A / 'spec_v1.json', Path(__file__).resolve()):
            row = d.proof(path)
            d.git_bound(row, args.freeze)
            rows.append(row)
        for row in spec['tool_bindings']:
            d.bound(row)
            rows.append(row)
        d.git_bound(spec['entry_ledger'], args.freeze)
        rows.append(spec['entry_ledger'])
        d.require(spec['inferior_elf'] in rows and spec['inferior_world'] in rows,
                  'unchanged ELF/world not admitted')
        d.port_free()
        command = spec['command']
        expected = [spec['inferior_elf']['path'], '--arm', 'quick50', '--world',
                    spec['inferior_world']['path'], '--output', str(PREFIX / 'native'),
                    '--work-seconds', '600']
        d.require(command[command.index('--args') + 1:] == expected,
                  'fixed debugger inferior argv differs')
        argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
                '--scope', 'engineering', '--output', str(outer)]
        argv += [part for row in rows for part in ('--source', row['path'])] + ['--', *command]
        env = dict(spec['environment'])
        d.write(PREFIX / 'submission.json', {'argv': argv, 'environment': env, 'source_before': rows})
        with (PREFIX / 'wrapper_stdout.log').open('x') as console:
            started = time.monotonic_ns()
            child = subprocess.Popen(argv, cwd=W, env=env, stdout=console,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            wrapper = d.identity(child.pid)
            d.require(wrapper is not None and wrapper['parent'] == owner['pid'], 'owned wrapper identity unavailable')
            d.write(PREFIX / 'wrapper_identity.json', wrapper)
            while rc is None:
                try:
                    rc = child.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    pass
                except BaseException as error:
                    errors.append('wait interrupted; draining: ' + repr(error))
                for row in descendants(child.pid):
                    observed.setdefault((row['pid'], row['start_ticks']), row)
                elapsed = d.fee(started, time.monotonic_ns())
                if received or elapsed >= 150:
                    # Only identities actually observed under this owned Popen.
                    for key, row in reversed(list(observed.items())):
                        if key in sent or row['pid'] == child.pid and elapsed < 180:
                            continue
                        d.owned_signal(row, signal.SIGKILL)
                        sent.add(key)
            ended = time.monotonic_ns()
        wait = d.read(outer / 'actual_wait.json')
        d.require(wait['actual_waited'] is True and wait['actual_returncode'] == rc and
                  wait['actual_argv'] == command and wait['source_unchanged'] is True,
                  'debugger actual-wait receipt differs')
        after = [d.proof(row['path']) for row in rows]
        d.require(rows == after, 'debugger/native/source bytes changed')
    except BaseException as error:
        errors.append(repr(error))
    finally:
        if child is not None and rc is None:
            # Popen remains owned even when receipt/observation handling failed.
            while rc is None:
                for row in descendants(child.pid):
                    observed.setdefault((row['pid'], row['start_ticks']), row)
                for row in reversed(list(observed.values())):
                    if row['pid'] != child.pid:
                        d.owned_signal(row, signal.SIGKILL)
                try:
                    rc = child.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    if d.fee(started, time.monotonic_ns()) >= 180 and wrapper is not None:
                        d.owned_signal(wrapper, signal.SIGKILL)
                except BaseException as error:
                    errors.append('final wait interrupted: ' + repr(error))
            ended = time.monotonic_ns()
    wait_returned = ended
    for row in reversed(list(observed.values())):
        if d.current(row) is not None:
            d.owned_signal(row, signal.SIGKILL)
            errors.append('saved owned identity still present after debugger wait: ' + str(row['pid']))
    if started is not None:
        ended = time.monotonic_ns()  # Includes post-source proof and any owned cleanup.
    fee = Decimal(0) if started is None else d.fee(started, ended)
    console = outer / 'console.log'
    text = console.read_text(errors='replace') if console.exists() and console.stat().st_size <= 16 * 1024**2 else ''
    signal_seen = 'received signal SIGSEGV' in text
    stack_seen = '#0 ' in text
    result = {'schema': 'mr3-v56-gdb-result-v1',
        'passed': not errors and not received and rc == 0 and fee <= CAP and signal_seen and stack_seen,
        'errors': errors, 'received_signals': received, 'actual_wrapper_returncode': rc,
        'actual_wrapper_waited': child is not None and type(rc) is int,
        'driver_identity': owner, 'wrapper_identity': wrapper,
        'observed_owned_identities': list(observed.values()),
        'started_monotonic_ns': started, 'ended_monotonic_ns': ended,
        'actual_popen_wait_returned_monotonic_ns': wait_returned,
        'engineering_added_seconds': str(fee), 'engineering_cumulative_seconds': str(ENTRY + fee),
        'engineering_remaining_seconds': str(CEILING - ENTRY - fee),
        'source_before': rows, 'source_after': after,
        'inferior_SIGSEGV_observed': signal_seen, 'backtrace_observed': stack_seen,
        'inferior_natural_exit_claimed': False, 'native_qualification_credit': False,
        'old_failure_preserved': True, 'pilot_added_seconds': '0', 'validation_added_seconds': '0',
        'closure_verdict': 'PENDING_EXTERNAL_TOOL_REAP_AND_FRESH_GONE'}
    d.write(PREFIX / 'summary.json', result)
    print(json.dumps({k: result[k] for k in ('passed', 'errors', 'engineering_added_seconds')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
