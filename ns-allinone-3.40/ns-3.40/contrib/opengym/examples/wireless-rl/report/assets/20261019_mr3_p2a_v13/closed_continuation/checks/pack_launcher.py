"""Launch only the CPU archiver, preserving each attempt and genuine child wait.

The caller must separately save actual exec/write_stdin tool return metadata.
No child-wait receipt is represented as an outer tool return.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def identity(pid):
    try:
        raw = Path('/proc/%d/stat' % pid).read_text()
    except FileNotFoundError:
        return None
    fields = raw[raw.rfind(')') + 2:].split()
    return {'pid': pid, 'start_ticks': int(fields[19]), 'parent': int(fields[1]),
            'process_group': int(fields[2]), 'session': int(fields[3])}


def bound(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to('/tmp') or output == Path('/tmp'):
        raise ValueError('exclusive /tmp output required')
    output.mkdir(exist_ok=False)
    checks = output / 'checks'
    checks.mkdir()
    original_script, original_selection = bound(args.script), bound(args.selection)
    script, selection = checks / 'pack_cpu.py', checks / 'root_closed_selection.json'
    shutil.copyfile(args.script, script)
    shutil.copyfile(args.selection, selection)
    if bound(script)['sha256'] != original_script['sha256'] or bound(selection)['sha256'] != original_selection['sha256']:
        raise ValueError('script/selection changed during launcher copy')
    shutil.copyfile(__file__, checks / 'pack_launcher.py')
    argv = [sys.executable, '-B', str(script), '--selection', str(selection), '--output', str(output)]
    started = time.monotonic_ns()
    errors = []
    with (checks / 'pack.log').open('x') as console:
        child = subprocess.Popen(argv, stdout=console, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1'))
        saved = identity(child.pid)
        while True:
            try:
                returncode = child.wait()
                break
            except BaseException as error:
                errors.append(repr(error))
    ended = time.monotonic_ns()
    receipt = {'scope': 'Actual CPU archive child wait only, not scientific/native cost or creator tool metadata.',
               'actual_argv': argv, 'coordinator_identity': identity(os.getpid()),
               'child_identity': saved, 'identity_capture_missing': saved is None,
               'started_wall_monotonic_ns': started, 'ended_wall_monotonic_ns': ended,
               'actual_child_wait_wall_seconds': str(Decimal(ended - started) / Decimal(10**9)),
               'actual_child_wait_wall_nanoseconds': ended - started,
               'actual_wait_returncode': returncode, 'wait_exceptions': errors,
               'original_script': original_script, 'original_selection': original_selection,
               'copied_script': bound(script), 'copied_selection': bound(selection),
               'console': bound(checks / 'pack.log'),
               'manifest': bound(output / 'manifest.json') if (output / 'manifest.json').is_file() else None,
               'creator_actual_tool_returncode': None,
               'creator_actual_tool_metadata_scope': 'Caller saves original actual tool results separately; never inferred from this child wait.'}
    with (checks / 'pack_actual_child_wait.json').open('x') as target:
        json.dump(receipt, target, indent=2, allow_nan=False)
        target.write('\n')
    print(json.dumps(receipt), flush=True)
    return returncode


if __name__ == '__main__':
    raise SystemExit(main())
