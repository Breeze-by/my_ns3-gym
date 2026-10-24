"""One frozen fixed-action trace and its real consumers; no policy/optimizer."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / '.git').exists())
W = HERE.parents[2]
sys.path.insert(0, str(W))
from mr3_learning.preparation import Runner, dump, identity, run_audits, sha


def main():
    began = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--preflight', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    trace = plan['trace']
    pf = json.loads(args.preflight.read_text())
    if pf['freeze'] != args.freeze or pf['passed'] is not True or pf['plan_sha256'] != sha(args.plan):
        raise ValueError('actual preflight does not bind trace plan/freeze')
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != args.freeze
            or subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip() != args.freeze
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)):
        raise ValueError('trace requires clean pushed freeze')
    for path, expected in plan['source_bindings'].items():
        raw = (ROOT / path).read_bytes()
        if sha(ROOT / path) != expected or subprocess.check_output(['git', 'show', args.freeze + ':' + path], cwd=ROOT) != raw:
            raise ValueError('trace source differs: ' + path)
    for path, expected in plan['library_bindings'].items():
        if sha(path) != expected:
            raise ValueError('trace library differs: ' + path)
    output = Path(trace['output_directory'])
    output.mkdir(exist_ok=False)
    result = {'schema': 'mr3-p2a-v9-fixed-trace-execution-v1', 'freeze': args.freeze,
              'plan_sha256': sha(args.plan), 'coordinator_identity': identity(__import__('os').getpid()),
              'final_external_coordinator_absence_required': True, 'audits': {}, 'errors': [],
              'passed': False, 'optimizer_steps': 0, 'policy_calls': 0}
    with (output / 'ledger.jsonl').open('x') as ledger:
        lock = threading.Lock()
        def record(**value):
            with lock:
                ledger.write(json.dumps({'freeze': args.freeze, 'wall_monotonic_ns': time.monotonic_ns(), **value}) + '\n')
                ledger.flush()
        runner = Runner(output, W, args.freeze, sha(args.plan), record)
        watch = runner.spawn(dict(trace['watcher'], id='watcher'))
        native = None
        try:
            ready_path = Path(trace['watcher']['ready'])
            ready_end = time.monotonic() + 30.
            ready = None
            while ready is None:
                if watch['process'] is None or watch['process'].poll() is not None or time.monotonic() >= ready_end:
                    raise RuntimeError('trace watcher never became ready')
                if ready_path.exists():
                    raw = ready_path.read_bytes()
                    if raw.endswith(b'\n'):
                        ready = json.loads(raw)
                        break
                time.sleep(.05)
            if ready['freeze'] != args.freeze:
                raise ValueError('trace watcher freeze differs')
            spec = dict(trace['native'], id='native')
            # The native summary declares capture, not scientific PASS.
            spec['result_pass_key'] = 'completed_requested_collection'
            native = runner.command(spec)
            result['native'] = native
            summary = json.loads(Path(spec['output']).read_text())
            result['collection_completed'] = (native['returncode'] == 0
                and summary['outcome'] == 'CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT')
        except Exception as error:
            result['errors'].append(repr(error))
        finally:
            if native is not None and native['execution_kind'] == 'subprocess_waited':
                stop = {'schema': 'mr3-native-custody-stop-v1', 'freeze': args.freeze,
                        'launch_receipt': {'path': native['receipt'], 'sha256': sha(native['receipt'])}}
            else:
                stop = {'schema': 'mr3-native-custody-stop-v1', 'freeze': args.freeze,
                        'native_not_started': True, 'reason': 'trace_pre_native_admission_failure'}
            dump(trace['watcher']['stop'], stop)
            result['watcher'] = runner.finish(watch)
        # FIFO and strict closure are collected first, even if the fixed actions
        # were incomplete; their real failure remains a failure. Other scientific
        # readers run only with complete native capture and live custody.
        deadline = began + 700 * 10**9
        if native is not None:
            closed, skipped = run_audits(trace['closure_audits'], runner, deadline)
            result['audits'].update(closed)
            result['skipped_closure_audits'] = skipped
        if result.get('collection_completed') and result['watcher']['passed']:
            science, skipped = run_audits(trace['scientific_audits'], runner, deadline)
            result['audits'].update(science)
            result['skipped_scientific_audits'] = skipped
        else:
            result['errors'].append('fixed collection or actual live custody incomplete')
        result['wall_seconds'] = str(Decimal(time.monotonic_ns() - began) / 10**9)
        required = trace['closure_audits'] + trace['scientific_audits']
        result['passed'] = (not result['errors'] and Decimal(result['wall_seconds']) <= 700
            and all(result['audits'].get(job['id'], {}).get('passed') is True for job in required))
        record(event='trace_completed', passed=result['passed'], wall_seconds=result['wall_seconds'])
    dump(output / 'summary.json', result)
    print(json.dumps({k: result[k] for k in ('passed', 'wall_seconds', 'errors')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
