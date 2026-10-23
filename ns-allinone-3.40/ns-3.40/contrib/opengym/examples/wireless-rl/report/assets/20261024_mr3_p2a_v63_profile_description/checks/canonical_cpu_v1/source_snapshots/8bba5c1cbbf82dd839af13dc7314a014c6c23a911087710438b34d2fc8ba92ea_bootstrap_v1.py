"""Save real launch ancestry before exec of the fixed V62 driver.

This draft cannot start native work. Canonical installation and an exact clean
pushed source freeze are checked by the real driver. Ancestors are observed
transport relationships, never targets for cleanup or absence claims.
"""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
STATE = Path('/tmp/mr3_p2a_v62_parent_v1')
MODULE = 'report.assets.20261024_mr3_p2a_v62_process_profile.run_profile_v1'


def identity(pid):
    tail = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, start_ticks=int(tail[19]), parent=int(tail[1]),
                group=int(tail[2]), session=int(tail[3]), state=tail[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    if not Path(__file__).resolve().is_relative_to(ROOT) or Path.cwd() != W:
        raise ValueError('Only the canonical fixed V62 bootstrap from W may execute')
    if len(args.freeze) != 40 or any(c not in '0123456789abcdef' for c in args.freeze):
        raise ValueError('Exact 40-hex source freeze required')
    STATE.mkdir(exist_ok=False)
    started = time.monotonic_ns()
    owner = None
    try:
        owner = identity(os.getpid())
        ancestors, errors, seen, pid = [], [], {owner['pid']}, owner['parent']
        while pid > 0 and pid not in seen and len(ancestors) < 16:
            try:
                saved = identity(pid)
            except (FileNotFoundError, ProcessLookupError, ValueError, IndexError) as error:
                errors.append(dict(pid=pid, error=repr(error)))
                break
            seen.add(pid)
            ancestors.append(saved)
            pid = saved['parent']
        record = dict(schema='mr3-v62-pre-exec-ancestry-v1', execution_freeze=args.freeze,
            bootstrap_identity=owner, observed_ancestors=ancestors,
            ancestry_errors=errors, observed_monotonic_ns=time.monotonic_ns(),
            complete_parent_started_monotonic_ns=started,
            actual_bootstrap_argv=[os.fsdecode(s) for s in Path('/proc/self/cmdline').read_bytes().split(b'\0') if s],
            ancestors_nonowned=True, ancestor_absence_or_signal_authorized=False,
            source_path=str(Path(__file__).resolve()),
            exec_preserves_PID_and_start_ticks=True)
        with (STATE / 'pre_exec_ancestry_v1.json').open('x') as stream:
            json.dump(record, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', '-m', MODULE, '--freeze', args.freeze])
    except BaseException as error:
        ended = time.monotonic_ns()
        failure = dict(schema='mr3-v62-bootstrap-failure-v1', passed=False,
            execution_freeze=args.freeze, saved_identity=owner,
            started_monotonic_ns=started, ended_monotonic_ns=ended,
            actual_parent_seconds=str(Decimal(ended-started)/10**9),
            trusted_entry_ledger_not_yet_read=True, engineering_cumulative_seconds=None,
            native_started=False, error=repr(error))
        with (STATE/'bootstrap_failure_v1.json').open('x') as stream:
            json.dump(failure, stream, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        raise


if __name__ == '__main__':
    main()
