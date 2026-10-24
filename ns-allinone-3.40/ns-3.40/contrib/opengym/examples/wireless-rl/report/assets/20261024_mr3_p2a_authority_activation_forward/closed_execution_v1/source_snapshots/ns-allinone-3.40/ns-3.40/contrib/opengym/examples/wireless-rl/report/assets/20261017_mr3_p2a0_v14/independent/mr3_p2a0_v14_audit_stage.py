"""Run unchanged read-only formal CLIs with at most four audit subprocesses."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSETS = WIRELESS / 'report/assets'
LOCAL = ASSETS / '20261017_mr3_p2a0_v10/independent'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('interface', 'terminal', 'reset', 'deadline'))
    parser.add_argument('freeze')
    args = parser.parse_args()
    plan_path = ASSETS / '20261017_mr3_p2a0_v14/predeclared_plan_v14.json'
    plan = json.loads(plan_path.read_text())
    assert plan['readiness']['status'] == 'ready' and not plan['readiness']['pending_bindings'], 'V14 template not finalized'
    stage = next(value for value in plan['stages'] if value['stage'] == args.stage)
    run = Path(stage['run_directory'])
    prefix = Path('/tmp') / ('mr3_p2a0_v14_' + args.stage)
    result_path = Path(str(prefix) + '_audit_execution_v1.json')
    assert not result_path.exists(), 'never overwrite real executions'
    assert subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == args.freeze
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    for binding in plan['independent_source_bindings']:
        assert sha(ROOT / binding['path']) == binding['sha256']
    commands, jobs, runner_errors = [], [], []
    lock = Lock()
    environment = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    environment.pop('PYTHONPATH', None)

    def execute(label, command, output, required=True):
        console = Path(str(prefix) + '_' + label + '_console.log')
        started = time.monotonic()
        record = {'label': label, 'argv': command, 'cwd': str(WIRELESS),
                  'console': str(console), 'output': str(output),
                  'required_success': required, 'passed': False, 'returncode': None}
        try:
            assert not output.exists(), 'never overwrite original consumer output'
            with console.open('x') as stream:
                process = subprocess.run(command, cwd=WIRELESS, env=environment,
                                         stdout=stream, stderr=subprocess.STDOUT)
            record['returncode'] = process.returncode
            record['output_exists'] = output.exists()
            if output.exists():
                record['output_sha256'] = sha(output)
                value = json.loads(output.read_text())
                record['passed'] = (process.returncode == 0 and isinstance(value, dict)
                                    and value.get('passed') is True)
        except BaseException as error:
            # subprocess.run owns and waits for its child on an exception.
            # The executor drain below also waits for every other submitted audit.
            record['error'] = repr(error)
        record['wall_seconds'] = time.monotonic() - started
        try:
            if console.exists():
                record['console_sha256'] = sha(console)
        except OSError as error:
            record['error'] = repr(error)
            record['passed'] = False
        with lock:
            commands.append(record)
            print(json.dumps(record), flush=True)
        return record

    pool = ThreadPoolExecutor(max_workers=4)

    def submit(label, command, output, required=True):
        future = pool.submit(execute, label, command, output, required)
        jobs.append(future)
        return future

    def standard(label, script, directory=run, extra=(), output=None, freeze=True, required=True):
        output = output or Path(str(prefix) + '_' + label + '.json')
        command = ['/usr/bin/python3', str(script), str(directory)]
        if freeze:
            command += ['--freeze', args.freeze]
        command += [*extra, '--output', str(output)]
        return submit(label, command, output, required=required)

    episodes = sorted(run.glob('worker*/episode*'))
    input_jobs, fifo_jobs = [], []
    try:
        full_output = Path(str(prefix) + '_full_audit.json')
        submit('full_audit', [sys.executable, '-m', 'mr3_learning.audit_preparation', str(run),
                              '--freeze', args.freeze, '--output', str(full_output)], full_output)
        standard('drive_review_v1', ASSETS / '20261017_mr3_p2a0_v13/independent/mr3_independent_drive_trace_v6.py',
                 extra=('--binary-proof', '/tmp/mr3_p2a0_v14_binaryproof.json'))
        for key in ('information', 'peer', 'control', 'settled_turn'):
            command = [value.replace('{freeze}', args.freeze)
                       for value in stage[key + '_audit_command_template']]
            output = Path(command[command.index('--output') + 1])
            submit(key + '_review_v1', command, output)
        physical_job = None
        if args.stage in ('interface', 'reset'):
            for index, episode in enumerate(episodes, 1):
                output = (Path(str(prefix) + '_input_review_v1.json') if args.stage == 'interface'
                          else Path(str(prefix) + '_episode'
                                    + str(index).zfill(3) + '_input_v1.json'))
                script = ASSETS / ('20261017_mr3_p2a0_v4/independent/'
                                   'mr3_p2a0_v4_independent_input_episode_review_v1.py')
                future = submit('input_' + str(index).zfill(3), [
                    '/usr/bin/python3', str(script), '--episode', str(episode),
                    '--output', str(output)], output)
                input_jobs.append((future, output))
            if args.stage == 'interface' and len(episodes) == 1:
                standard('fixed_angular_v1', ASSETS / '20261017_mr3_p2a0_v4/independent/'
                         'mr3_independent_angular_interface_v1.py', episodes[0], freeze=False)
                standard('fixed_physics_v1', ASSETS / '20261017_mr3_p2a0_v3/independent/'
                         'mr3_independent_physics_review.py', episodes[0], freeze=False)
            elif args.stage == 'reset':
                standard('angular_matrix_v1', ASSETS / '20261017_mr3_p2a0_v8/independent/'
                         'mr3_independent_angular_reset_matrix_v8.py')
                per_episode = Path(str(prefix) + '_physical_per_episode_v1.json')
                physical_job = standard(
                    'physical_per_episode_v1', ASSETS / '20261017_mr3_p2a0_v3/independent/'
                    'mr3_independent_physics_review.py', freeze=False, output=per_episode,
                    required=False)
        for index, episode in enumerate(episodes, 1):
            fifo_jobs.append(standard('episode' + str(index).zfill(3) + '_fifo_phase_final',
                                      LOCAL / 'mr3_v10_fifo_phase_review.py', episode))
        if physical_job is not None:
            physical_job.result()  # Original missing-coverage FAIL is still retained.
            standard('physics_matrix_v1', ASSETS / '20261017_mr3_p2a0_v8/independent/'
                     'mr3_independent_physics_matrix_v8.py',
                     extra=('--per-episode-report', str(per_episode)))
        for future in fifo_jobs:
            future.result()  # Closure consumes exact completed per-episode FIFO files.
        expected = {'interface': 1, 'terminal': 2, 'reset': 8, 'deadline': 1}[args.stage]
        command = ['/usr/bin/python3', str(ASSETS / '20261017_mr3_p2a0_v14/independent/'
                   'mr3_v14_multiepoch_closure_binary_review_v1.py'), str(run),
                   '--prefix', prefix.name, '--freeze', args.freeze,
                   '--expected-episodes', str(expected)]
        if args.stage == 'interface':
            command.append('--require-parameters')
        submit('closure_binary_review_v1', command,
               Path(str(prefix) + '_closure_binary_review_v1.json'))
    except BaseException as error:
        runner_errors.append(repr(error))
    finally:
        # No early return/cancellation: drain all submitted read-only subprocess jobs.
        for future in jobs:
            try:
                future.result()
            except BaseException as error:
                runner_errors.append(repr(error))
        while True:
            try:
                pool.shutdown(wait=True)
                break
            except BaseException as error:
                runner_errors.append(repr(error))

    if args.stage == 'reset':
        leaves = []
        for future, output in input_jobs:
            try:
                passed = future.result()['passed']
            except BaseException:
                passed = False
            leaves.append({'path': str(output), 'sha256': sha(output) if output.exists() else None,
                           'passed': passed})
        output = Path(str(prefix) + '_input_review_v1.json')
        try:
            with output.open('x') as stream:
                json.dump({'passed': len(leaves) == 8 and all(v['passed'] for v in leaves),
                           'freeze': args.freeze, 'episodes': leaves,
                           'scope': 'All eight original per-episode input CLI results; no '
                                    'substitute for any failed or missing leaf'}, stream, indent=2)
                stream.write('\n')
        except BaseException as error:
            runner_errors.append(repr(error))
    receipts = []
    for path in stage['required_audit_receipts']:
        path = Path(path)
        record = {'path': str(path), 'sha256': None, 'passed': False}
        try:
            if path.exists():
                record['sha256'] = sha(path)
                value = json.loads(path.read_text())
                record['passed'] = (isinstance(value, dict) and value.get('passed') is True
                                    and ('freeze' not in value or value['freeze'] == args.freeze))
        except (OSError, ValueError, TypeError) as error:
            record['error'] = repr(error)
        receipts.append(record)
    result = {'schema': 'mr3-p2a0-audit-execution-v14', 'freeze': args.freeze,
              'scheduling_version': 'mr3-formal-subprocess-pool-v1', 'max_workers': 4,
              'stage': args.stage, 'commands': commands, 'receipts': receipts,
              'runner_errors': runner_errors,
              'all_submitted_jobs_finished': all(f.done() for f in jobs),
              'plan_sha256': sha(plan_path),
              'passed': not runner_errors
              and all(v['passed'] for v in commands if v['required_success'])
              and all(v['passed'] for v in receipts),
              'raw_physical_report_scope': 'Reset per-episode physical report keeps every '
              'original missing-coverage FAIL. The unchanged mandatory reset matrix consumer '
              'enforces all raw/closure/eligible-response bounds and declared pooled coverage.'}
    with result_path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
