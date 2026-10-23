"""Disabled A54 driver: one finite forensic child, complete parent actual fee."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W_REL = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
W = ROOT / W_REL
A = W / 'report/assets/20261023_mr3_p2a_v54_firstfault'
OLD = '1fa55bc56d5bb9e230d4b397f962d83b1604b278'
PREFIX = Path('/tmp/mr3_p2a_v54_driver_v1')
OUTER = PREFIX / 'forensic_actual_wait'
RESULT = Path('/tmp/mr3_p2a_v54_firstfault_v1.json')
SPEC = A / 'spec_v1.json'
SCOPE = A / 'scope_v1.json'
ENTRY = Decimal('90102.9195132536018')
CEILING = Decimal('120000')
CAP = Decimal('600')
CHAIN = {W_REL + '/mr3_learning/' + name for name in (
    '__init__.py', 'reach_execution.py', 'preparation.py', 'native_custody.py', 'supervisor.py', 'ipc.py')}
P = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration'
INTERPRETATION = {P + '/' + name for name in ('motion_safety.py', 'mr3_motion_control.py', 'mr3_reach_runtime.py')} | {
    'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py',
    W_REL + '/mr3_learning/benchmark.py', W_REL + '/mr3_learning/supervisor.py'}
REQUIRED_SOURCES = CHAIN | INTERPRETATION | {
    str((A / name).relative_to(ROOT)) for name in ('run_firstfault_v1.py', 'firstfault_extract_v3.py')}
ENV_POLICY = 'system Python; fixed PATH; no ROS/conda/PYTHONPATH/PYTHONHOME; CUDA hidden; no environment dump'


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path, limit=16 * 1024**2):
    require(path.stat().st_size <= limit, 'metadata exceeds fixed byte limit: ' + str(path))
    def pairs(items):
        result = dict(items)
        require(len(result) == len(items), 'duplicate metadata key')
        return result
    value = json.loads(path.read_bytes(), object_pairs_hook=pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite metadata')))
    json.dumps(value, allow_nan=False)
    return value


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def proof(path):
    before = path.stat()
    raw = path.read_bytes()
    require(path.stat() == before, 'source/metadata changed while hashing')
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def identity(pid):
    tail = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'parent': int(tail[1]), 'group': int(tail[2]),
            'session': int(tail[3]), 'start_ticks': int(tail[19])}


def same_identity(left, right):
    return (type(left) is dict and type(right) is dict
            and all(left.get(k) == right.get(k) for k in ('pid', 'parent', 'group', 'session', 'start_ticks')))


def wait_owned(child, errors):
    """An interruption/failed thin wait never licenses leaving a child unreaped."""
    while True:
        try:
            result = child.wait()
            require(type(result) is int, 'wait did not return real integer rc')
            return result
        except BaseException as error:
            if len(errors) < 32:
                errors.append('actual wait interrupted; continuing: ' + repr(error))


def parent_fee(started, ended):
    require(type(started) is int and type(ended) is int and 0 <= started <= ended, 'invalid parent interval')
    return Decimal(ended - started) / 10**9


def check_sources(scope, execution_freeze):
    require(scope.get('schema') == 'mr3-v54-firstfault-scope-v1' and scope.get('admitted') is True,
            'scope not admitted')
    require(scope.get('evidence_freeze') == OLD, 'wrong native evidence freeze')
    budget = scope.get('budget')
    require(type(budget) is dict and budget == {
        'engineering_used_seconds': str(ENTRY), 'engineering_ceiling_seconds': str(CEILING),
        'engineering_remaining_seconds': str(CEILING - ENTRY), 'reservation_seconds': '600',
        'pilot_added_seconds': '0', 'validation_added_seconds': '0'}, 'exact entry resource differs')
    require(CEILING - ENTRY >= CAP, 'complete finite diagnostic not funded')
    bindings = scope.get('source_bindings')
    require(type(bindings) is dict and set(bindings) == REQUIRED_SOURCES, 'source/import-chain set differs')
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=10).strip()
            == execution_freeze, 'actual execution HEAD differs')
    spec = read(SPEC)
    require(scope.get('input_spec') == proof(SPEC) and spec.get('admitted') is True,
            'sealed input spec differs/not admitted')
    require(spec.get('evidence_freeze') == OLD and spec.get('execution_freeze_binding') == 'required-exact-cli'
            and 0 < spec['limits']['work_seconds'] <= 590, 'consumer evidence/work limit differs')
    require(set(spec['interpretation_sources']) == INTERPRETATION, 'old source set differs')
    ref = spec['inputs']['motion']['inventory_ref']
    require(ref == spec['inputs']['startup']['inventory_ref'], 'inventory refs differ')
    configs = [proof(SCOPE), proof(SPEC), proof(Path(ref['path']))]
    require(configs[2] == ref, 'canonical inventory SHA/bytes differs')
    sources = []
    for relative, expected in bindings.items():
        path = ROOT / relative
        current = path.read_bytes()
        frozen = subprocess.check_output(['git', 'show', execution_freeze + ':' + relative], cwd=ROOT, timeout=10)
        actual = proof(path)
        require(expected == {'bytes': actual['bytes'], 'sha256': actual['sha256']}
                and current == frozen, 'current/execution Git source differs: ' + relative)
        if relative in INTERPRETATION:
            old = subprocess.check_output(['git', 'show', OLD + ':' + relative], cwd=ROOT, timeout=10)
            require(current == old and expected == spec['interpretation_sources'][relative],
                    'old interpretation bytes differ: ' + relative)
        sources.append(actual)
    for config in configs:
        relative = str(Path(config['path']).relative_to(ROOT))
        frozen = subprocess.check_output(['git', 'show', execution_freeze + ':' + relative], cwd=ROOT, timeout=10)
        require(hashlib.sha256(frozen).hexdigest() == config['sha256'] and len(frozen) == config['bytes'],
                'scope/spec/inventory differs from new execution Git')
    consumer = spec['consumer']
    require(consumer == proof(A / 'firstfault_extract_v3.py'), 'consumer path/bytes/SHA differs')
    return sorted(sources + configs, key=lambda row: row['path']), spec


def check_closed(wait, result, command, sources, spec, wrapper, owner, started, ended, rc):
    require(wait.get('schema') == 'mr3-reach-outer-actual-wait-v1'
            and wait.get('scope') == 'engineering' and wait.get('passed') is True
            and wait.get('actual_waited') is True and wait.get('actual_returncode') == rc == 0
            and wait.get('actual_argv') == command and wait.get('cwd') == str(W)
            and wait.get('source_unchanged') is True and wait.get('errors') == [], 'outer actual-wait failed')
    require(same_identity(wait['coordinator_identity'], wrapper) and wrapper['parent'] == owner['pid']
            and same_identity(wait['child_identity'], result['identity']), 'owned wrapper/consumer identity differs')
    require(started <= wait['started_monotonic_ns'] <= result['started_monotonic_ns']
            <= result['ended_monotonic_ns'] <= wait['ended_monotonic_ns'] <= ended,
            'nested intervals not inside complete parent actual wait')
    require(Decimal(wait['actual_child_wait_seconds']) == Decimal(
        wait['ended_monotonic_ns'] - wait['started_monotonic_ns']) / 10**9, 'nested elapsed receipt differs')
    expected = {row['path']: (row['bytes'], row['sha256']) for row in sources}
    require(wait['source_before'] == wait['source_after']
            and len(wait['source_before']) == len(expected)
            and {row['path']: (row['bytes'], row['sha256']) for row in wait['source_before']} == expected,
            'complete outer source set changed/differs')
    require(result.get('schema') == 'mr3-v54-firstfault-description-v1' and result.get('passed') is True
            and result.get('within_work_limit') is True and result.get('errors') == []
            and result.get('source_before') == result.get('source_after')
            and result.get('selection_complete_for_declared_rule') is True
            and len(result.get('input_reports', [])) == 2
            and all(row.get('parse_and_binding_complete') is True
                    and row.get('whole_input_read') is True for row in result['input_reports']),
            'complete two-input description not closed successfully')
    by_label = {row['input']: row for row in result['input_reports']}
    require(set(by_label) == {'motion', 'startup'}, 'actual input labels differ')
    for label, expected_input in spec['inputs'].items():
        actual = by_label[label]
        require(actual.get('path') == expected_input['path']
                and actual.get('bytes_read') == expected_input['bytes']
                and actual.get('whole_input_sha256') == expected_input['sha256']
                and actual.get('stat_before') == actual.get('stat_after')
                and actual.get('error_count') == 0 and actual.get('errors') == [],
                'closed original input SHA/stat/bytes differ: ' + label)
    require(result.get('source_before', {}).get('evidence_freeze') == OLD
            and result['source_before'].get('execution_freeze') == command[command.index('--freeze') + 1]
            and result.get('first_runtime_fault_status') in ('RECORDED', 'NOT_RECORDED')
            and result.get('first_failure_callback_status') in ('RECORDED', 'NOT_RECORDED')
            and result.get('scientific_qualification') is False, 'freeze/status/credit differs')
    # sys.argv excludes Python's -B. The full actual child command is preserved
    # independently in the real outer actual_wait receipt above.
    require(result.get('actual_argv') == [command[0], *command[2:]], 'consumer sys.argv differs')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args(argv)
    require(re.fullmatch('[0-9a-f]{40}', args.freeze), 'exact new execution freeze required')
    require(Path(__file__).resolve() == A / 'run_firstfault_v1.py' and Path.cwd() == W
            and Path(sys.executable).resolve() == Path('/usr/bin/python3').resolve(),
            'canonical installed driver/system Python/cwd required')
    driver_started = time.monotonic_ns()
    PREFIX.mkdir(exist_ok=False)
    owner = identity(os.getpid())
    errors, received_signals = [], []
    def signal_received(number, _frame):
        if len(received_signals) < 32:
            received_signals.append({'signal': signal.Signals(number).name, 'monotonic_ns': time.monotonic_ns()})
    previous = {n: signal.signal(n, signal_received) for n in (signal.SIGTERM, signal.SIGINT)}
    child, wrapper, rc, start, end, wait, result = None, None, None, None, None, None, None
    sources, after, command, wrapper_argv = [], [], None, None
    fee = Decimal(0)
    write(PREFIX / 'entry.json', {'schema': 'mr3-v54-firstfault-driver-entry-v1',
        'actual_driver_argv': [sys.executable, *sys.argv], 'cwd': str(Path.cwd()),
        'clean_environment_policy': ENV_POLICY, 'driver_identity': owner,
        'evidence_freeze': OLD, 'execution_freeze': args.freeze, 'scope': str(SCOPE),
        'engineering_used_at_entry_seconds': str(ENTRY), 'engineering_ceiling_seconds': str(CEILING),
        'parent_fee_cap_seconds': '600', 'driver_started_monotonic_ns': driver_started, 'no_retry': True})
    try:
        require(not RESULT.exists() and not RESULT.is_symlink(), 'fixed result exists; no overwrite/retry')
        scope = read(SCOPE)
        sources, spec = check_sources(scope, args.freeze)
        require(not received_signals, 'driver interrupted before submission')
        command = ['/usr/bin/python3', '-B', str(A / 'firstfault_extract_v3.py'),
                   '--spec', str(SPEC), '--freeze', args.freeze, '--output', str(RESULT)]
        wrapper_argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
                        '--scope', 'engineering', '--output', str(OUTER)]
        wrapper_argv += [part for row in sources for part in ('--source', row['path'])]
        wrapper_argv += ['--', *command]
        write(PREFIX / 'submission.json', {'actual_wrapper_argv': wrapper_argv, 'consumer_argv': command,
              'source_before': sources, 'scope': proof(SCOPE), 'input_spec': proof(SPEC)})
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
               'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
               'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
        with (PREFIX / 'wrapper_stdout.log').open('x') as console:
            start = time.monotonic_ns()  # Includes Popen, wrapper source hashes, child, drain and wait return.
            try:
                child = subprocess.Popen(wrapper_argv, cwd=W, env=env, stdout=console, stderr=subprocess.STDOUT)
                wrapper = identity(child.pid)
                write(PREFIX / 'wrapper_identity.json', wrapper)
            finally:
                if child is not None:
                    rc = wait_owned(child, errors)
                end = time.monotonic_ns()
                fee = parent_fee(start, end)
        require(child is not None and type(rc) is int, 'no real submitted/reaped wrapper')
        wait, result = read(OUTER / 'actual_wait.json'), read(RESULT, 2 * 1024**2)
        check_closed(wait, result, command, sources, spec, wrapper, owner, start, end, rc)
        after, _ = check_sources(scope, args.freeze)
        require(sources == after, 'source/scope/spec/inventory changed after actual wait')
        require(fee <= CAP, 'complete parent wait exceeds600; full overrun fee retained FAIL')
    except BaseException as error:
        errors.append(repr(error))
    finally:
        if child is not None and rc is None:
            rc = wait_owned(child, errors)
            end = time.monotonic_ns()
            fee = parent_fee(start, end)
    used = ENTRY + fee
    passed = (not errors and not received_signals and rc == 0 and fee <= CAP
              and bool(sources) and sources == after and used <= CEILING)
    metadata_end = time.monotonic_ns()
    summary = {'schema': 'mr3-v54-firstfault-driver-v1', 'passed': passed,
        'evidence_freeze': OLD, 'execution_freeze': args.freeze,
        'actual_driver_argv': [sys.executable, *sys.argv], 'cwd': str(Path.cwd()),
        'clean_environment_policy': ENV_POLICY, 'driver_identity': owner, 'wrapper_identity': wrapper,
        'consumer_identity': None if result is None else result.get('identity'),
        'actual_wrapper_argv': wrapper_argv, 'actual_consumer_argv': command,
        'actual_returncode': rc, 'actual_wrapper_waited': child is not None and type(rc) is int,
        'started_monotonic_ns': start, 'ended_monotonic_ns': end,
        'actual_parent_wait_seconds': str(fee), 'engineering_added_seconds': str(fee),
        'engineering_used_at_entry_seconds': str(ENTRY), 'engineering_ceiling_seconds': str(CEILING),
        'engineering_cumulative_used_seconds': str(used), 'engineering_remaining_seconds': str(CEILING - used),
        'pilot_added_seconds': '0', 'validation_added_seconds': '0', 'parent_fee_cap_seconds': '600',
        'source_before': sources, 'source_after': after, 'errors': errors,
        'received_parent_signals': received_signals,
        'outer_actual_wait': str(OUTER / 'actual_wait.json'), 'description_result': str(RESULT),
        'driver_started_monotonic_ns': driver_started, 'driver_metadata_end_monotonic_ns': metadata_end,
        'driver_metadata_span_seconds': str(parent_fee(driver_started, metadata_end)),
        'accounting': 'Full wrapper Popen submission through real wait return parent interval only; nested intervals not added. Entry/post metadata separate. Overrun fully charged FAIL; no hard realtime kill claim.',
        'closure_verdict': 'PENDING_EXTERNAL_DRIVER_FRESH_GONE', 'external_fresh_gone_review_required': True,
        'scientific_qualification_credit': False, 'old_failures_preserved': True,
        'worlds': 0, 'models_loaded': False, 'optimizer_updates': 0, 'no_retry': True}
    try:
        write(PREFIX / 'summary.json', summary)
        print(json.dumps({k: summary[k] for k in ('passed', 'actual_parent_wait_seconds', 'errors')}), flush=True)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    return 0 if passed and not received_signals else 1


if __name__ == '__main__':
    raise SystemExit(main())
