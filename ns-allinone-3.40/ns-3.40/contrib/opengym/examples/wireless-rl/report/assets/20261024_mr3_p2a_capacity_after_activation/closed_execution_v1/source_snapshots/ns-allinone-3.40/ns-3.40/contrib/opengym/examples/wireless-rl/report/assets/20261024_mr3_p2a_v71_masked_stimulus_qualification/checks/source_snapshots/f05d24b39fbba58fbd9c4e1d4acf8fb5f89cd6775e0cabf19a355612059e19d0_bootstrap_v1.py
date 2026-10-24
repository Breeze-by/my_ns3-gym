"""Real same-PID bootstrap of the fixed matrix-only V71 parent."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSETS = WIRELESS/'report/assets/20261024_mr3_p2a_v71_masked_stimulus_qualification'
STATE = Path('/tmp/mr3_p2a_reach_v71_driver_v1')
MODULE = 'report.assets.20261024_mr3_p2a_v71_masked_stimulus_qualification.run_matrix_v1'


def identity(pid):
    tail = Path('/proc', str(pid), 'stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=pid,start_ticks=int(tail[19]),parent=int(tail[1]),
                group=int(tail[2]),session=int(tail[3]),state=tail[0])


def write(path, value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
        stream.flush();os.fsync(stream.fileno())


def canonical_location():
    return Path(__file__).resolve() == ASSETS/'bootstrap_v1.py' and Path.cwd() == WIRELESS


def main(argv=None):
    started = time.monotonic_ns()
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',required=True)
    args=parser.parse_args(argv)
    if not canonical_location() or not re.fullmatch('[0-9a-f]{40}',args.freeze):
        raise ValueError('only the canonical bootstrap from W with exact freeze may execute')
    STATE.mkdir(exist_ok=False)
    owner=None
    try:
        owner=identity(os.getpid())
        ancestors,errors,seen,pid=[],[],{owner['pid']},owner['parent']
        while pid>0 and pid not in seen and len(ancestors)<16:
            try:
                saved=identity(pid)
            except (FileNotFoundError,ProcessLookupError,ValueError,IndexError) as error:
                errors.append(dict(pid=pid,error=repr(error)));break
            ancestors.append(saved);seen.add(pid);pid=saved['parent']
        record=dict(schema='mr3-v71-pre-exec-ancestry-v1',execution_freeze=args.freeze,
            bootstrap_identity=owner,observed_ancestors=ancestors,ancestry_errors=errors,
            complete_parent_started_monotonic_ns=started,observed_monotonic_ns=time.monotonic_ns(),
            actual_bootstrap_argv=[os.fsdecode(p) for p in Path('/proc/self/cmdline').read_bytes().split(b'\0') if p],
            source_path=str(Path(__file__).resolve()),exec_preserves_PID_and_start_ticks=True,
            ancestors_nonowned=True,ancestor_absence_or_signal_authorized=False)
        write(STATE/'pre_exec_ancestry_v1.json',record)
        env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='0')
        env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        os.execve('/usr/bin/python3',['/usr/bin/python3','-B','-m',MODULE,'--freeze',args.freeze],env)
    except BaseException as error:
        ended=time.monotonic_ns()
        write(STATE/'bootstrap_failure_v1.json',dict(schema='mr3-v71-bootstrap-failure-v1',passed=False,
            execution_freeze=args.freeze,saved_identity=owner,started_monotonic_ns=started,
            ended_monotonic_ns=ended,actual_parent_seconds=str(Decimal(ended-started)/10**9),
            engineering_cumulative_seconds=None,trusted_entry_ledger_not_yet_read=True,
            native_started=False,error=repr(error)))
        raise


if __name__=='__main__':
    main()
