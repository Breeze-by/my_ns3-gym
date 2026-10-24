"""Run declared real consumers sequentially; retain every exit and original output."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
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
    plan_path = ASSETS / '20261017_mr3_p2a0_v11/predeclared_plan_v11.json'
    plan = json.loads(plan_path.read_text())
    stage = next(value for value in plan['stages'] if value['stage'] == args.stage)
    run = Path(stage['run_directory'])
    prefix = Path('/tmp') / ('mr3_p2a0_v11_' + args.stage)
    result_path = Path(str(prefix) + '_audit_execution_v1.json')
    assert not result_path.exists(), 'never overwrite real executions'
    assert subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == args.freeze
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    for binding in plan['independent_source_bindings']:
        assert sha(ROOT / binding['path']) == binding['sha256']
    commands = []
    environment = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    environment.pop('PYTHONPATH', None)

    def execute(label, command, output, required=True):
        console = Path(str(prefix) + '_' + label + '_console.log')
        started = time.monotonic()
        with console.open('x') as stream:
            process = subprocess.run(command, cwd=WIRELESS, env=environment,
                                     stdout=stream, stderr=subprocess.STDOUT)
        record = {'label': label, 'argv': command, 'cwd': str(WIRELESS),
                  'returncode': process.returncode, 'wall_seconds': time.monotonic() - started,
                  'console': str(console), 'console_sha256': sha(console),
                  'output': str(output), 'output_exists': output.exists(),
                  'required_success': required}
        if output.exists():
            record['output_sha256'] = sha(output)
            try:
                value = json.loads(output.read_text())
                record['passed'] = process.returncode == 0 and value.get('passed') is True
            except (ValueError, TypeError):
                record['passed'] = False
        else:
            record['passed'] = False
        commands.append(record)
        print(json.dumps(record), flush=True)
        return record['passed']

    def standard(label, script, directory=run, extra=(), output=None, freeze=True, required=True):
        output = output or Path(str(prefix) + '_' + label + '.json')
        command = ['/usr/bin/python3', str(script), str(directory)]
        if freeze:
            command += ['--freeze', args.freeze]
        command += [*extra, '--output', str(output)]
        execute(label, command, output, required=required)

    full_output = Path(str(prefix) + '_full_audit.json')
    full_command = [sys.executable, '-m', 'mr3_learning.audit_preparation', str(run),
                    '--freeze', args.freeze, '--output', str(full_output)]
    execute('full_audit', full_command, full_output)
    standard('drive_review_v1', LOCAL / 'mr3_independent_drive_trace_v5.py',
             extra=('--binary-proof', '/tmp/mr3_p2a0_v11_binaryproof.json'))
    for key in ('information', 'peer', 'control', 'settled_turn'):
        template = stage[key + '_audit_command_template']
        command = [value.replace('{freeze}', args.freeze) for value in template]
        output = Path(command[command.index('--output') + 1])
        execute(key + '_review_v1', command, output)
    episodes = sorted(run.glob('worker*/episode*'))
    if args.stage in ('interface', 'reset'):
        leaves = []
        for index, episode in enumerate(episodes, 1):
            output = (Path(str(prefix) + '_input_review_v1.json') if args.stage == 'interface'
                      else Path(str(prefix) + '_episode' + str(index).zfill(3) + '_input_v1.json'))
            input_consumer = ASSETS / ('20261017_mr3_p2a0_v4/independent/'
                                       'mr3_p2a0_v4_independent_input_episode_review_v1.py')
            execute('input_' + str(index).zfill(3), [
                '/usr/bin/python3', str(input_consumer),
                '--episode', str(episode), '--output', str(output)], output)
            leaves.append({'path': str(output), 'sha256': sha(output) if output.exists() else None,
                           'passed': commands[-1]['passed']})
        if args.stage == 'reset':
            output = Path(str(prefix) + '_input_review_v1.json')
            with output.open('x') as stream:
                json.dump({'passed': len(leaves) == 8 and all(v['passed'] for v in leaves),
                           'freeze': args.freeze, 'episodes': leaves,
                           'scope': 'All eight original per-episode input CLI results; no '
                                    'substitute for any failed or missing leaf'}, stream, indent=2)
                stream.write('\n')
        if args.stage == 'interface' and len(episodes) == 1:
            standard('fixed_angular_v1', ASSETS / '20261017_mr3_p2a0_v4/independent/'
                     'mr3_independent_angular_interface_v1.py', episodes[0], freeze=False)
            standard('fixed_physics_v1', ASSETS / '20261017_mr3_p2a0_v3/independent/'
                     'mr3_independent_physics_review.py', episodes[0], freeze=False)
        elif args.stage == 'reset':
            standard('angular_matrix_v1', ASSETS / '20261017_mr3_p2a0_v8/independent/'
                     'mr3_independent_angular_reset_matrix_v8.py')
            per_episode = Path(str(prefix) + '_physical_per_episode_v1.json')
            standard('physical_per_episode_v1', ASSETS / '20261017_mr3_p2a0_v3/independent/'
                     'mr3_independent_physics_review.py', freeze=False, output=per_episode,
                     required=False)
            standard('physics_matrix_v1', ASSETS / '20261017_mr3_p2a0_v8/independent/'
                     'mr3_independent_physics_matrix_v8.py',
                     extra=('--per-episode-report', str(per_episode)))
    for index, episode in enumerate(episodes, 1):
        standard('episode' + str(index).zfill(3) + '_fifo_phase_final',
                 LOCAL / 'mr3_v10_fifo_phase_review.py', episode)
    expected = {'interface': 1, 'terminal': 2, 'reset': 8, 'deadline': 1}[args.stage]
    closure = ASSETS / ('20261017_mr3_p2a0_v11/independent/'
                        'mr3_v11_multiepoch_closure_binary_review_v1.py')
    command = ['/usr/bin/python3', str(closure),
               str(run), '--prefix', prefix.name, '--freeze', args.freeze,
               '--expected-episodes', str(expected)]
    if args.stage == 'interface':
        command.append('--require-parameters')
    execute('closure_binary_review_v1', command,
            Path(str(prefix) + '_closure_binary_review_v1.json'))
    receipts = []
    for path in stage['required_audit_receipts']:
        path = Path(path)
        value = json.loads(path.read_text()) if path.exists() else {}
        receipts.append({'path': str(path), 'sha256': sha(path) if path.exists() else None,
                         'passed': value.get('passed') is True
                         and ('freeze' not in value or value['freeze'] == args.freeze)})
    result = {'schema': 'mr3-p2a0-audit-execution-v11', 'freeze': args.freeze,
              'stage': args.stage, 'commands': commands, 'receipts': receipts,
              'plan_sha256': sha(plan_path),
              'passed': all(v['passed'] for v in commands if v['required_success'])
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
