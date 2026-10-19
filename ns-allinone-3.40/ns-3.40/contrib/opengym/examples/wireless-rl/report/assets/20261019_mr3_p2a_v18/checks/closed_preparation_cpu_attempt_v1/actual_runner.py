"""One finite CPU/build preparation child; never launches simulator/GPU work itself."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time


def binding(path):
    p = Path(path)
    stat = p.stat()
    data = p.read_bytes()
    return {'path': str(p), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'stat': [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]}


def identity(pid):
    try:
        data = Path(f'/proc/{pid}/stat').read_text()
        fields = data[data.rfind(')')+2:].split()
        return {'pid': pid, 'parent': int(fields[1]), 'process_group': int(fields[2]),
                'session': int(fields[3]), 'start_ticks': int(fields[19])}
    except FileNotFoundError:
        return None


parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cwd', type=Path, required=True)
parser.add_argument('--source', type=Path, action='append', required=True)
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ['--'] else args.command
if not command:
    parser.error('missing actual CPU command')
args.output.mkdir(parents=True, exist_ok=False)
snapshots = args.output / 'source_snapshots'
snapshots.mkdir()
before = [binding(p) for p in args.source]
for number, row in enumerate(before):
    shutil.copyfile(row['path'], snapshots / f'{number:02d}_{Path(row["path"]).name}')
shutil.copyfile(__file__, args.output / 'actual_runner.py')
env = dict(os.environ)
env.pop('PYTHONPATH', None)
env['PYTHONNOUSERSITE'] = '1'
env['PYTHONDONTWRITEBYTECODE'] = '1'
started = time.monotonic_ns()
with (args.output / 'console.log').open('x') as console:
    child = subprocess.Popen(command, cwd=args.cwd, env=env, stdout=console, stderr=subprocess.STDOUT)
    child_identity = identity(child.pid)
    returncode = child.wait()
ended = time.monotonic_ns()
after = [binding(p) for p in args.source]
stable = before == after
receipt = {'schema': 'mr3-v15-finite-preparation-actual-child-wait-v1',
           'scope': 'Finite CPU/build preparation only; no simulator run, GPU update, formal native scientific role, quota change or native admission.',
           'actual_argv': command, 'cwd': str(args.cwd),
           'explicit_env': {'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': None},
           'actual_returncode': returncode, 'actual_waited': True,
           'coordinator_identity': identity(os.getpid()), 'child_identity': child_identity,
           'started_monotonic_ns': started, 'ended_monotonic_ns': ended,
           'actual_child_wait_seconds': str((ended-started)/1e9),
           'source_before': before, 'source_after': after, 'source_unchanged': stable,
           'console': binding(args.output / 'console.log'),
           'passed': returncode == 0 and stable,
           'native_admission': False}
(args.output / 'actual_wait.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'returncode': returncode, 'source_unchanged': stable,
                  'actual_child_wait_seconds': receipt['actual_child_wait_seconds'],
                  'receipt': str(args.output / 'actual_wait.json')}))
sys.exit(returncode if stable else 1)
