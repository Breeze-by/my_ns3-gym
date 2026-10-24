"""Two fixed diagnostic runs, with live load witnessing and no retry/signals."""
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v19'
TMP = Path('/tmp')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), {'path': str(path), 'sha256': sha(raw)}


def dump(path, value, mode='x'):
    with Path(path).open(mode) as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def run_consumer(job, command, environment, console):
    started = time.monotonic()
    child, code, value, proof, errors = None, None, {}, None, []
    try:
        with console.open('x') as output:
            child = subprocess.Popen(command, cwd=W, env=environment,
                                     stdout=output, stderr=subprocess.STDOUT)
            code = child.wait()
    except BaseException as error:
        errors.append(repr(error))
    finally:
        if child is not None:
            while code is None:
                try:
                    code = child.wait()
                except BaseException as error:
                    errors.append(repr(error))
    try:
        value, proof = read(Path(job['output']))
        require(type(value) is dict, 'consumer receipt must be a JSON object')
    except BaseException as error:
        errors.append(repr(error))
        value = {}
        output_path = Path(job['output'])
        if output_path.exists():
            proof = {'path': str(output_path), 'sha256': sha(output_path.read_bytes()),
                     'invalid_receipt_preserved': True}
    record = {'label': job['label'], 'argv': command, 'returncode': code,
        'passed': code == 0 and value.get('passed') is True and not errors,
        'output': proof, 'wall_seconds': time.monotonic() - started,
        'console': str(console), 'console_sha256': sha(console.read_bytes()) if console.exists() else None,
        'required_capture_success': job['required_capture_success'], 'errors': errors}
    return record, value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('freeze')
    args = parser.parse_args()
    freeze = args.freeze
    require(re.fullmatch('[a-f0-9]{40}', freeze) is not None, 'exact40 source freeze required')
    plan_path = A / 'predeclared_plan_v19.json'
    plan, plan_proof = read(plan_path)
    require(plan.get('status') == 'ready' and not plan.get('pending'), 'unready diagnostic plan')
    require([row['stage'] for row in plan['stages']] == ['baseline', 'iters150'], 'fixed diagnostic order changed')
    preflight, preflight_proof = read(TMP / 'mr3_p2a0_v19_source_preflight.json')
    require(preflight.get('passed') is True and preflight['freeze'] == freeze
            and preflight['plan_sha256'] == plan_proof['sha256'], 'source preflight mismatch')
    bindings = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
    for path, expected in bindings.items():
        require(sha((ROOT / path).read_bytes()) == expected, 'independent source changed: ' + path)
    witness_path = A / 'independent/mr3_p2a0_v19_live_admission_v1.py'
    module_spec = importlib.util.spec_from_file_location('live_witness', witness_path)
    live = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(live)
    environment = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    environment.pop('PYTHONPATH', None)
    require('MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE' not in environment, 'diagnostic env must be command-scoped')

    def unchanged():
        require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
                == freeze == subprocess.check_output(['git', 'rev-parse', '@{u}'], cwd=ROOT, text=True).strip(),
                'source freeze is not exact pushed HEAD')
        require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'source not clean')
        require(sha(plan_path.read_bytes()) == plan_proof['sha256'], 'diagnostic plan changed')
        for path, expected in bindings.items():
            require(sha((ROOT / path).read_bytes()) == expected, 'independent source changed')
    unchanged()
    lock_path = TMP / 'mr3_p2a0_v19_diagnostics.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for stage in plan['stages']:
            require(not Path(stage['run_directory']).exists(), 'run already attempted; no retry')
            require(not (TMP / f"mr3_p2a0_v19_{stage['stage']}_execution.json").exists(), 'receipt already exists')
        total_wall = 0.0
        complete = []
        for specification in plan['stages']:
            unchanged()
            stage = specification['stage']
            prefix = TMP / ('mr3_p2a0_v19_' + stage)
            receipt_path = Path(str(prefix) + '_execution.json')
            console = Path(str(prefix) + '_console.log')
            require(plan['budget']['max_native_launcher_wall_seconds'] - total_wall >=
                    specification['native_wall_ceiling_seconds'], 'remaining wall cannot admit stage ceiling')
            started = time.monotonic()
            record = {'schema': 'mr3-isolated-diagnostic-execution-v1', 'freeze': freeze, 'stage': stage,
                'plan_sha256': plan_proof['sha256'], 'source_preflight': preflight_proof,
                'status': 'reserved', 'argv': specification['command'], 'cwd': str(W), 'console': str(console),
                'parent_identity': live.identity(os.getpid()),
                'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'scope': 'isolated physical diagnosis; no matrix/task/PPO credit'}
            dump(receipt_path, record)
            watch = {'proof': None, 'errors': []}
            stop = threading.Event()
            process = None
            thread = None
            try:
                with console.open('x') as output:
                    process = subprocess.Popen(specification['command'], cwd=W, env=environment,
                                               stdout=output, stderr=subprocess.STDOUT)
                    benchmark = live.identity(process.pid)
                    require(benchmark is not None, 'benchmark process identity unavailable')
                    record.update(status='running', benchmark_identity=benchmark)
                    dump(receipt_path, record, 'w')
                    print(json.dumps({'stage': stage, 'event': 'native_started', 'benchmark': benchmark}), flush=True)

                    def observe():
                        while not stop.is_set():
                            try:
                                proof_path, proof = live.witness(plan_path, stage, freeze, benchmark,
                                    Path(str(prefix) + '_live_witness'))
                                watch['proof'] = {'path': str(proof_path), 'sha256': sha(proof_path.read_bytes())}
                                print(json.dumps({'stage': stage, 'event': 'live_load_bound',
                                                  'owned_gzserver': proof['owned_gzserver']}), flush=True)
                                return
                            except FileNotFoundError:
                                # Startup can legitimately precede exclusive files and first flush.
                                stop.wait(1.0)
                            except BaseException as error:
                                watch['errors'].append(repr(error))
                                return
                    thread = threading.Thread(target=observe, name='readonly-native-load-witness')
                    thread.start()
                    code = process.wait()
            except BaseException as error:
                watch['errors'].append(repr(error))
                code = None
                # Reap only this exact finite child. No signal, replacement epoch or retry.
                if process is not None:
                    code = process.wait()
            finally:
                stop.set()
                if thread is not None:
                    thread.join()
            duration = time.monotonic() - started
            total_wall += duration
            record.update(status='native_closed', returncode=code, native_wall_seconds=duration,
                cumulative_native_wall_seconds=total_wall, live_witness=watch,
                benchmark_identity_after=None if process is None else live.identity(process.pid),
                within_wall_budget=duration <= specification['native_wall_ceiling_seconds'] and
                    total_wall <= plan['budget']['max_native_launcher_wall_seconds'],
                console_sha256=sha(console.read_bytes()) if console.exists() else None)
            dump(receipt_path, record, 'w')
            errors = []
            try:
                unchanged()
                summary, summary_proof = read(Path(specification['run_directory']) / 'benchmark_summary.json')
                record['benchmark_summary'] = summary_proof
                require(summary.get('passed') is True and summary.get('freeze') == freeze, 'native benchmark failed')
                require(code == 0 and record['within_wall_budget'] and watch['proof'] is not None
                        and not watch['errors'], 'native/wall/live-load binding failed')
            except BaseException as error:
                errors.append(repr(error))
            # Every attempted native run is retained. Explicit consumers are run once
            # after closure; original physical FAIL remains a scientific outcome.
            consumers = []
            for job in specification['diagnostic_consumers']:
                if job['requires_live_proof'] and watch['proof'] is None:
                    consumers.append({'label': job['label'], 'status': 'skipped_missing_live_proof', 'passed': False})
                    if job['required_capture_success']:
                        errors.append('missing live proof for ' + job['label'])
                    continue
                command = [part.replace('{freeze}', freeze).replace('{admission_proof}',
                           '' if watch['proof'] is None else watch['proof']['path']) for part in job['command']]
                job_console = TMP / f"mr3_p2a0_v19_{stage}_{job['label']}.log"
                job_record, value = run_consumer(job, command, environment, job_console)
                consumers.append(job_record)
                if job_record['errors']:
                    errors.append('consumer execution/receipt error: ' + job['label'])
                if job['required_capture_success'] and not job_record['passed']:
                    errors.append('required diagnostic capture/closure failed: ' + job['label'])
                if job.get('required_original_closure'):
                    episodes = value.get('episodes', [])
                    if (len(episodes) != 1 or episodes[0].get('error')
                            or episodes[0].get('closure', {}).get('passed') is not True):
                        errors.append('original strict native closure missing/failed: ' + job['label'])
                try:
                    unchanged()
                except BaseException as error:
                    errors.append(repr(error))
                    break
            record.update(status='completed', diagnostic_consumers=consumers, errors=errors,
                passed=not errors, pass_scope='diagnostic capture/admission/native closure, not physical response or matrix acceptance',
                end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            dump(receipt_path, record, 'w')
            complete.append({'stage': stage, 'passed': record['passed'], 'receipt': str(receipt_path),
                             'sha256': sha(receipt_path.read_bytes()), 'native_wall_seconds': duration})
            print(json.dumps(complete[-1]), flush=True)
            if errors:
                print(json.dumps({'event': 'later_diagnostic_skipped', 'failed_stage': stage,
                                  'errors': errors, 'no_retry': True}), flush=True)
                break
        final = {'schema': 'mr3-isolated-diagnostic-pair-v1', 'freeze': freeze,
                 'plan_sha256': plan_proof['sha256'], 'stages': complete,
                 'passed': len(complete) == 2 and all(row['passed'] for row in complete),
                 'native_wall_seconds': total_wall, 'matrix_credit': False, 'optimizer_updates': 0}
        dump(TMP / 'mr3_p2a0_v19_pair_execution.json', final)
        return 0 if final['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
