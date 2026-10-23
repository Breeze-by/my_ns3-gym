"""One explicit initial-encoder-servo plant diagnostic; no retry or qualification."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261023_mr3_p2a_v58_encoder_hold'
SCOPE = A / 'scope_v1.json'
PREFIX = Path('/tmp/mr3_p2a_v58_driver_v1')
OLD = '1fa55bc56d5bb9e230d4b397f962d83b1604b278'
ENTRY, CEILING, CAP = map(Decimal, ('91317.7804195576018', '120000', '2100'))
ARMS = ('quick150',)
URI = 'http://127.0.0.1:11555'
CHAIN = {str((W / 'mr3_learning' / name).relative_to(ROOT)) for name in (
    '__init__.py', 'reach_execution.py', 'preparation.py', 'native_custody.py',
    'supervisor.py', 'ipc.py', 'proxy2d_process.py')}
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
P = ROS / 'src/multi_robot_exploration/multi_robot_exploration'
OLD_CORE = {str(path.relative_to(ROOT)) for path in (
    P / 'motion_safety.py', P / 'mr3_motion_control.py', P / 'mr3_reach_runtime.py',
    ROS / 'scripts/mr3_env_worker.py',
    ROS / 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py',
    W / 'mr3_learning/benchmark.py', W / 'mr3_learning/supervisor.py')}
OLD_INPUTS = (ROS / 'src/multi_robot/models/turtlebot3_waffle/model.sdf',
              Path('/usr/share/gazebo-11/models/ground_plane/model.sdf'),
              ROS / 'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp',
              ROS / 'src/multi_robot/src/mr3_gazebo_diff_drive.cpp')
sys.path.insert(0, str(W))
from mr3_learning.preparation import identity
from mr3_learning.proxy2d_process import pidfd_open, pidfd_send_signal


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path, limit=1024 * 1024):
    path = Path(path)
    require(path.lstat().st_size <= limit, 'metadata limit: ' + str(path))
    def pairs(items):
        result = dict(items)
        require(len(result) == len(items), 'duplicate JSON key')
        return result
    result = json.loads(path.read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))
    json.dumps(result, allow_nan=False)
    return result


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def proof(path):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'regular non-symlink source required')
    raw = path.read_bytes()
    after = path.lstat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    require(all(getattr(before, k) == getattr(after, k) for k in keys), 'source changed while hashing')
    return {'path': str(path.absolute()), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def bound(row):
    require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and
            type(row['path']) is str and Path(row['path']).is_absolute() and
            type(row['bytes']) is int and row['bytes'] >= 0 and
            type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
            'invalid exact source binding')
    require(proof(row['path']) == row, 'bound bytes differ: ' + row['path'])


def same(left, right):
    return (type(left) is dict and type(right) is dict and all(
        type(left.get(k)) is int and left[k] > 0 and left[k] == right.get(k)
        for k in ('pid', 'parent', 'group', 'session', 'start_ticks')))


def current(saved):
    """None is genuinely absent/reused; unreadable is an error; matching Z is live."""
    try:
        raw = Path('/proc', str(saved['pid']), 'stat').read_text()
    except FileNotFoundError:
        return None
    end = raw.rfind(')')
    require(end >= 0 and int(raw[:raw.index('(')].strip()) == saved['pid'], 'malformed proc identity')
    fields = raw[end + 2:].split()
    return fields[0] if int(fields[19]) == saved['start_ticks'] else None


def owned_signal(saved, number):
    descriptor = None
    try:
        descriptor = pidfd_open(saved['pid'])
        if current(saved) is not None:
            pidfd_send_signal(descriptor, number)
            return True
        return False
    except ProcessLookupError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def fee(start, end):
    require(type(start) is int and type(end) is int and 0 <= start <= end, 'invalid actual interval')
    return Decimal(end - start) / 10**9


def port_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test:
        test.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        test.bind(('127.0.0.1', 11555))


def git_bound(row, freeze):
    bound(row)
    relative = str(Path(row['path']).relative_to(ROOT))
    raw = subprocess.check_output(['git', 'show', freeze + ':' + relative], cwd=ROOT, timeout=10)
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'current/frozen bytes differ: ' + relative)


def library_sources(manifest):
    rows = []
    for original in manifest['shared_libraries']:
        resolved = proof(Path(original['path']).resolve(strict=True))
        require((resolved['bytes'], resolved['sha256']) == (original['bytes'], original['sha256']),
                'linked-library alias bytes differ')
        rows.append(resolved)
    return rows


def verify_inputs(scope, freeze):
    require(scope.get('schema') == 'mr3-v58-passive-pair-scope-v1' and scope.get('admitted') is True,
            'scope is not admitted')
    require(scope.get('evidence_freeze') == OLD and scope.get('gazebo_master_uri') == URI and
            scope.get('arms') == list(ARMS) and scope.get('no_retry') is True and
            scope.get('per_case_outer_stop_seconds') == 1800 and
            scope.get('interrupt_to_TERM_seconds') == 10 and scope.get('TERM_to_KILL_seconds') == 10,
            'fixed pair/cleanup scope differs')
    require(scope.get('budget') == {
        'engineering_used_seconds': str(ENTRY), 'engineering_ceiling_seconds': str(CEILING),
        'engineering_remaining_seconds': str(CEILING - ENTRY), 'reservation_seconds': str(CAP),
        'pilot_added_seconds': '0', 'validation_added_seconds': '0'}, 'exact entry budget differs')
    require(CEILING - ENTRY >= CAP, 'pair is not funded')
    git_bound(scope['entry_ledger'], freeze)
    require(read(scope['entry_ledger']['path'])['engineering_cumulative_seconds'] == str(ENTRY),
            'previous actual ledger entry differs')
    bound(scope['prepared_spec']); spec = read(scope['prepared_spec']['path'])
    require(spec.get('schema') == 'mr3-v58-passive-plant-spec-v1' and
            [r['path'] for r in spec['input_sources']] == [str(p) for p in OLD_INPUTS] and
            [r['path'] for r in spec['execution_sources']] == [str(A / 'prepare_passive_plant_v1.py'), str(A / 'passive_plant_v1.cpp'), str(A / 'initial_zero_encoder_servo_v1.hpp')] and
            [r['arm'] for r in spec['worlds']] == list(ARMS), 'prepared input/world membership differs')
    expected = {'native_seed': 101, 'settle_seconds': 45, 'hold_seconds': 310,
        'native_steps_per_arm': 355000, 'step_ns': 1000000,
        'csv_sample_period_ns': 20000000, 'motor_update_period_ns': 34000000,
        'work_wall_seconds_per_arm': 1500, 'complete_pair_parent_reservation_seconds': 2100,
        'physics_seed_api': 'gazebo::physics::PhysicsEngine::SetSeed',
        'physics_seed_readback_claimed': False,
        'gazebo_master_uri': URI, 'physical_model_tree_preserved': True,
        'omitted_nonphysical_elements': ['plugin', 'sensor', 'visual']}
    require(all(type(spec.get(k)) is type(v) and spec[k] == v for k, v in expected.items()),
            'prepared protocol parameters differ')
    bound(scope['elf']); bound(scope['build_actual_wait']); bound(scope['build_manifest'])
    manifest = read(scope['build_manifest']['path'])
    require(manifest.get('schema') == 'mr3-v58-native-build-manifest-v1' and
            manifest.get('passed') is True and manifest.get('source_unchanged') is True and
            manifest['actual_wait'] == scope['build_actual_wait'] and manifest['elf'] == scope['elf'],
            'actual native build manifest differs')
    bound(manifest['build_entry'])
    require(read(manifest['build_entry']['path'])['compiler_argv'] == scope['actual_compile_argv'],
            'actual compiler entry argv differs')
    require(manifest['compiled_sources'] == [spec['execution_sources'][1], spec['input_sources'][2], spec['execution_sources'][2]],
            'manifest compiled CPP/header differ from prepared source pins')
    packed = manifest['archived_elf_gzip']
    require(packed['raw_bytes'] == scope['elf']['bytes'] and packed['raw_sha256'] == scope['elf']['sha256'],
            'canonical ELF raw-byte mapping differs')
    packed_ref = {k: packed[k] for k in ('path', 'bytes', 'sha256')}
    bound(packed_ref)
    require(type(manifest['shared_libraries']) is list and manifest['shared_libraries'], 'actual linked library pins missing')
    libraries = library_sources(manifest)
    require(Path(scope['elf']['path']).read_bytes()[:4] == b'\x7fELF' and
            os.access(scope['elf']['path'], os.X_OK), 'actual executable ELF required')
    build = read(scope['build_actual_wait']['path'])
    require(build.get('schema') == 'mr3-reach-outer-actual-wait-v1' and build.get('scope') == 'cpu' and
            build.get('passed') is True and build.get('actual_waited') is True and
            type(build.get('actual_returncode')) is int and build['actual_returncode'] == 0 and
            build.get('errors') == [] and build.get('source_unchanged') is True and
            build['source_before'] == build['source_after'] and
            build['actual_argv'] == scope['actual_compile_argv'], 'actual compile wait not bound')
    argv = build['actual_argv']
    require(argv.count('-o') == 1 and argv[argv.index('-o') + 1] == scope['elf']['path'] and
            str(A / 'passive_plant_v1.cpp') in argv, 'compiler target/source differ')
    require(Decimal(build['actual_child_wait_seconds']) == fee(build['started_monotonic_ns'], build['ended_monotonic_ns']),
            'build actual interval differs')
    require(proof(build['console']['path'])['sha256'] == build['console']['sha256'], 'build console differs')
    build_sources = {r['path']: (r['bytes'], r['sha256']) for r in build['source_before']}
    for row in (spec['execution_sources'][1], spec['input_sources'][2], spec['execution_sources'][2]):
        require(build_sources.get(row['path']) == (row['bytes'], row['sha256']), 'compiled CPP/header not source-bound')
    old_paths = OLD_CORE | {str(p.relative_to(ROOT)) for p in (OLD_INPUTS[0], OLD_INPUTS[2], OLD_INPUTS[3])}
    required = CHAIN | old_paths | {str((A / name).relative_to(ROOT)) for name in
        ('run_passive_pair_v1.py', 'prepare_passive_plant_v1.py', 'passive_plant_v1.cpp', 'initial_zero_encoder_servo_v1.hpp')}
    require(type(scope.get('source_bindings')) is dict and set(scope['source_bindings']) == required,
            'complete source/import membership differs')
    require(set(scope.get('old_source_bindings', {})) == old_paths, 'old production/model/header pins differ')
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=10).strip() == freeze,
            'actual HEAD differs from exact execution freeze')
    rows = []
    for relative, pin in scope['source_bindings'].items():
        row = {'path': str(ROOT / relative), **pin}; bound(row)
        git_bound(row, freeze)
        if relative in old_paths:
            require(pin == scope['old_source_bindings'][relative] and
                    Path(row['path']).read_bytes() == subprocess.check_output(['git', 'show', OLD + ':' + relative], cwd=ROOT, timeout=10),
                    'old production/model/header bytes differ: ' + relative)
        rows.append(row)
    for row in spec['input_sources'] + spec['execution_sources']:
        bound(row)
        if row['path'] in [str(p) for p in (OLD_INPUTS[0], OLD_INPUTS[2], OLD_INPUTS[3])]:
            require(row in rows, 'prepared old input differs from old Git pin')
    configs = [proof(SCOPE), scope['entry_ledger'], scope['prepared_spec'], scope['build_manifest'], manifest['build_entry'], packed_ref] + [
        {k: row[k] for k in ('path', 'bytes', 'sha256')} for row in spec['worlds']]
    for row in configs:
        git_bound(row, freeze)
    # Build receipt/ELF and installed ground are exact byte bindings; no false claim they are old Git sources.
    rows += configs + [scope['elf'], scope['build_actual_wait'], spec['input_sources'][1]] + libraries
    unique = {}
    for row in rows:
        require(row['path'] not in unique or unique[row['path']] == row, 'conflicting source bindings')
        unique[row['path']] = row
    return spec, sorted(unique.values(), key=lambda row: row['path'])


def capture_cpp(wrapper, case_dir, command):
    """Observe real direct children before signalling; never manufacture a saved start."""
    children = []
    try:
        pids = Path('/proc', str(wrapper['pid']), 'task', str(wrapper['pid']), 'children').read_text().split()
    except FileNotFoundError:
        pids = []
    for pid in pids:
        row = identity(int(pid))
        require(row is not None and row['parent'] == wrapper['pid'] and
                row['group'] == wrapper['pid'] and row['session'] == wrapper['pid'], 'unexpected wrapper child owner')
        children.append(row)
    require(len(children) <= 1, 'CPP forked an unexpected external process')
    saved_path = case_dir / 'identity.json'
    if saved_path.exists():
        try:
            saved = read(saved_path)
        except (json.JSONDecodeError, ValueError):
            return children  # The exclusive first write may still be in progress; final verification is strict.
        row = saved['identity']
        require(saved['actual_argv'] == command and row['parent'] == wrapper['pid'] and
                row['group'] == wrapper['pid'] and row['session'] == wrapper['pid'], 'CPP saved owner/argv differs')
        if children:
            require(same(row, children[0]), 'observed CPP and same-object saved identity differ')
        children = [row]
    return children


def validate_case(wait, summary, command, sources, wrapper, case_start, case_end, rc):
    require(wait['schema'] == 'mr3-reach-outer-actual-wait-v1' and wait['scope'] == 'engineering' and
            wait['actual_waited'] is True and type(wait['actual_returncode']) is int and
            wait['actual_returncode'] == rc and wait['actual_argv'] == command and wait['cwd'] == str(W),
            'actual case wait/argv differs')
    require(same(wait['coordinator_identity'], wrapper) and same(wait['child_identity'], summary['identity']),
            'same-object wrapper/CPP identity differs')
    require(case_start <= wait['started_monotonic_ns'] < wait['ended_monotonic_ns'] <= case_end and
            Decimal(wait['actual_child_wait_seconds']) == fee(wait['started_monotonic_ns'], wait['ended_monotonic_ns']),
            'nested actual case interval differs')
    expected = {r['path']: (r['bytes'], r['sha256']) for r in sources}
    require(wait['source_before'] == wait['source_after'] and wait['source_unchanged'] is True and
            len(wait['source_before']) == len(expected) and
            {r['path']: (r['bytes'], r['sha256']) for r in wait['source_before']} == expected, 'case source set changed')
    require(summary['schema'] == 'mr3-v58-passive-plant-result-v1' and
            summary['actual_argv'] == command and type(summary['execution_passed']) is bool,
            'actual CPP argv/execution result differs')
    libraries = summary.get('loaded_library_paths', [])
    expected_paths = {row['path'] for row in sources}
    for path in libraries:
        require(str(Path(path).resolve(strict=True)) in expected_paths,
                'loaded library is not bound to the observed shared-library objects')
    if summary['execution_passed']:
        arm = command[command.index('--arm') + 1]
        parameters = summary['actual_physics_parameters']
        require(rc == 0 and wait['passed'] is True and wait['errors'] == [] and
                summary['actual_step_count'] == 355000 and summary['completed_sim_ns'] == 355000000000 and
                summary['update_end_calls'] == 355000 and summary['native_seed'] == 101 and
                summary['physics_seed_api'] == 'gazebo::physics::PhysicsEngine::SetSeed' and
                summary['physics_seed_set_call_completed'] is True and
                summary['physics_seed_readback_claimed'] is False and
                summary['first_update_end_clock_ns'] == 1000000 and
                summary['last_update_end_clock_ns'] == 355000000000 and
                summary['gazebo_shutdown_returned'] is True and summary['received_signal'] == 0 and
                summary['completion_status'] == 'COMPLETE' and summary['errors'] == [] and
                0 <= summary['wall_seconds_to_shutdown'] <= 1500 and
                parameters['solver_type'] == ('quick' if arm == 'quick150' else 'world') and
                parameters['engine'] == 'ode' and (arm != 'quick150' or parameters['iters'] == 150) and
                libraries and
                parameters['max_step_size'] == .001 and parameters['real_time_update_rate'] == 0 and
                sorted(row['robot'] for row in summary['robots']) == ['tb1', 'tb2', 'tb3'] and
                all(row['anchor_clock_ns'] == 45000000000 and row['post_anchor_observations'] == 310001
                    for row in summary['robots']),
                'complete CPP execution lacks fixed step/time receipt')
    # within_R is an observation. It is deliberately absent from this execution predicate.


def run_case(arm, scope, spec, sources, owner, pair_start, stop_requested):
    case_dir = PREFIX / 'arms' / arm  # CPP owns creation of this exclusive leaf.
    require(not case_dir.exists() and not case_dir.is_symlink(), 'case output already exists; no retry')
    port_free()
    world = next(row for row in spec['worlds'] if row['arm'] == arm)
    command = [scope['elf']['path'], '--arm', arm, '--world', world['path'],
               '--output', str(case_dir), '--work-seconds', '1500']
    outer = PREFIX / 'waits' / arm
    wrapper_argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
                    '--scope', 'engineering', '--output', str(outer)]
    wrapper_argv += [part for row in sources for part in ('--source', row['path'])] + ['--', *command]
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': '',
        'DISPLAY': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
        'HOME': str(PREFIX / 'home'), 'ALSOFT_DRIVERS': 'null',
        'LD_LIBRARY_PATH': '/opt/ros/humble/lib:/opt/ros/humble/lib/x86_64-linux-gnu',
        'GAZEBO_MASTER_URI': URI, 'GAZEBO_MODEL_DATABASE_URI': '',
        'GAZEBO_MODEL_PATH': str(ROS / 'src/multi_robot/models') + ':/usr/share/gazebo-11/models',
        'GAZEBO_PLUGIN_PATH': ''}
    errors, children, signal_rows, rc, wrapper, child = [], [], [], None, None, None
    first_stop = None; sent = set()
    with (PREFIX / (arm + '_wrapper_stdout.log')).open('x') as output:
        started = time.monotonic_ns()  # First Popen through last real wait is the continuous fee.
        if pair_start is None:
            pair_start = started
        try:
            child = subprocess.Popen(wrapper_argv, cwd=W, env=env, stdout=output,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            wrapper = identity(child.pid)  # Capture ownership before any fallible metadata write.
            write(PREFIX / (arm + '_submission.json'), {'actual_wrapper_argv': wrapper_argv,
                  'actual_CPP_argv': command, 'source_before': sources, 'master_uri': URI,
                  'started_monotonic_ns': started, 'pair_started_monotonic_ns': pair_start,
                  'actual_environment': env})
            require(wrapper is not None and wrapper['parent'] == owner['pid'] and
                    wrapper['group'] == wrapper['pid'] == wrapper['session'], 'fresh owned wrapper session not observed')
            write(PREFIX / (arm + '_wrapper_identity.json'), wrapper)
            while rc is None:
                try:
                    rc = child.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    pass
                except BaseException as error:
                    errors.append('actual wait interrupted; draining: ' + repr(error))
                try:
                    observed = capture_cpp(wrapper, case_dir, command)
                    for row in observed:
                        if not any(same(row, old) for old in children):
                            children.append(row)
                            write(PREFIX / (arm + '_CPP_identity.json'), row)
                    now = time.monotonic_ns()
                    if (stop_requested() or fee(started, now) >= 1800 or fee(pair_start, now) >= CAP - 20) and first_stop is None:
                        first_stop = now
                        errors.append('declared stop requested; no timeout converted to a fabricated returncode')
                    if first_stop is not None:
                        elapsed = fee(first_stop, now)
                        number = signal.SIGKILL if elapsed >= 20 else signal.SIGTERM if elapsed >= 10 else signal.SIGINT
                        for row in children:
                            key = (row['pid'], row['start_ticks'], number)
                            if key not in sent:
                                signal_rows.append({'saved_identity': row, 'signal': number,
                                    'sent': owned_signal(row, number), 'monotonic_ns': now})
                                sent.add(key)
                except BaseException as error:
                    if len(errors) < 32:
                        errors.append('owned observation/cleanup error: ' + repr(error))
        except BaseException as error:
            errors.append(repr(error))
        finally:
            if child is not None and rc is None:
                # Own direct Popen is never abandoned, even if identity/setup/receipt handling failed.
                while rc is None:
                    try:
                        rc = child.wait(timeout=.1)
                    except subprocess.TimeoutExpired:
                        try:
                            if wrapper is not None:
                                for row in capture_cpp(wrapper, case_dir, command):
                                    owned_signal(row, signal.SIGKILL)
                        except BaseException as error:
                            if len(errors) < 32:
                                errors.append('final owned cleanup observation: ' + repr(error))
                    except BaseException as error:
                        if len(errors) < 32:
                            errors.append('final wait interrupted; continuing: ' + repr(error))
    ended = time.monotonic_ns()
    summary = wait = None
    try:
        wait = read(outer / 'actual_wait.json')
        summary = read(case_dir / 'summary.json')
        validate_case(wait, summary, command, sources, wrapper, started, ended, rc)
        saved = read(case_dir / 'identity.json')
        require(same(saved['identity'], summary['identity']) and saved['actual_argv'] == command,
                'early/late CPP same-object identity differs')
        require(current(summary['identity']) is None, 'CPP still present, including Z')
        port_free()
    except BaseException as error:
        errors.append('closed case receipt: ' + repr(error))
    execution_passed = bool(summary is not None and summary.get('execution_passed') is True and rc == 0 and not errors)
    report = {'arm': arm, 'execution_passed': execution_passed,
        'actual_wrapper_returncode': rc, 'actual_wrapper_waited': child is not None and type(rc) is int,
        'wrapper_identity': wrapper, 'CPP_identities_observed': children,
        'CPP_identity_from_actual_wait': None if wait is None else wait.get('child_identity'),
        'actual_CPP_returncode': None if wait is None else wait.get('actual_returncode'),
        'actual_CPP_summary': summary, 'summary_path': str(case_dir / 'summary.json'),
        'actual_wrapper_argv': wrapper_argv, 'actual_CPP_argv': command,
        'started_monotonic_ns': started, 'ended_monotonic_ns': ended,
        'actual_case_parent_wall_seconds': str(fee(started, ended)),
        'pair_started_monotonic_ns': pair_start, 'source_before': sources,
        'signals': signal_rows, 'errors': errors, 'no_retry': True}
    write(PREFIX / (arm + '_pair_receipt.json'), report)
    return report, pair_start, ended


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args(argv)
    require(re.fullmatch('[0-9a-f]{40}', args.freeze), 'exact new execution freeze required')
    require(Path(__file__).resolve() == A / 'run_passive_pair_v1.py' and Path.cwd() == W
            and Path(sys.executable).resolve() == Path('/usr/bin/python3').resolve(),
            'canonical installed driver/system Python/cwd required')
    PREFIX.mkdir(exist_ok=False)
    (PREFIX / 'arms').mkdir()
    (PREFIX / 'home').mkdir()  # Valid private HOME for Gazebo DiagnosticManager; no reused user config.
    owner = identity(os.getpid()); require(owner is not None, 'driver identity unavailable')
    entry_started = time.monotonic_ns()
    write(PREFIX / 'entry.json', {'schema': 'mr3-v58-passive-pair-entry-v1',
        'driver_identity': owner, 'actual_driver_argv': [sys.executable, *sys.argv],
        'actual_driver_program_argument': sys.argv[0], 'cwd': str(Path.cwd()),
        'execution_freeze': args.freeze, 'evidence_freeze': OLD, 'scope': str(SCOPE),
        'entry_started_monotonic_ns': entry_started})
    received = []
    previous = {number: signal.signal(number, lambda n, _f: received.append(n))
                for number in (signal.SIGINT, signal.SIGTERM)}
    reports, errors, sources, after = [], [], [], []
    pair_start = pair_end = None
    try:
        scope = read(SCOPE)
        spec, sources = verify_inputs(scope, args.freeze)
        port_free()
        for arm in ARMS:
            if received or (pair_start is not None and CAP - fee(pair_start, time.monotonic_ns()) < 1800):
                errors.append('not submitted ' + arm + ': interruption or insufficient declared remaining pair wall')
                break
            report, pair_start, pair_end = run_case(arm, scope, spec, sources, owner, pair_start, lambda: bool(received))
            reports.append(report)
            if not report['actual_wrapper_waited']:
                errors.append('owned wrapper was not actually waited; no later case submitted')
                break
            # A baseline R excess is not an execution failure and is never inspected here.
            if any(current(row) is not None for row in report['CPP_identities_observed']):
                errors.append('CPP ownership not closed; no later case submitted')
                break
            port_free()
    except BaseException as error:
        errors.append(repr(error))
    finally:
        if sources:
            try:
                after = [proof(row['path']) for row in sources]
                require(after == sources, 'source/ELF/world/build receipt changed after pair')
                for row in library_sources(read(scope['build_manifest']['path'])):
                    require(row in sources, 'linked-library alias target changed after pair')
            except BaseException as error:
                errors.append('source-after receipt: ' + repr(error))
    charged = Decimal('0') if pair_start is None else fee(pair_start, pair_end if pair_end is not None else time.monotonic_ns())
    passed = (not errors and not received and [r['arm'] for r in reports] == list(ARMS) and
              all(r['execution_passed'] for r in reports) and sources == after and charged <= CAP)
    summary = {'schema': 'mr3-v58-passive-pair-result-v1', 'passed': passed,
        'diagnostic_only': True, 'driver_identity': owner, 'actual_driver_argv': [sys.executable, *sys.argv],
        'actual_driver_program_argument': sys.argv[0], 'execution_freeze': args.freeze,
        'evidence_freeze': OLD, 'arms': reports, 'errors': errors, 'received_parent_signals': received,
        'source_before': sources, 'source_after': after,
        'pair_started_monotonic_ns': pair_start, 'pair_ended_monotonic_ns': pair_end,
        'engineering_added_parent_wall_seconds': str(charged),
        'engineering_entry_seconds': str(ENTRY), 'engineering_ceiling_seconds': str(CEILING),
        'engineering_cumulative_seconds': str(ENTRY + charged),
        'engineering_remaining_seconds': str(CEILING - ENTRY - charged),
        'within_pair_parent_cap': charged <= CAP, 'complete_parent_cap_seconds': str(CAP),
        'accounting': 'One continuous first-wrapper Popen through last real wrapper wait span, including all inter-case gaps and metadata; nested case waits are not added. Entry/post metadata spans separate.',
        'entry_started_monotonic_ns': entry_started, 'metadata_ended_monotonic_ns': time.monotonic_ns(),
        'closure_verdict': 'PENDING_EXTERNAL_ROOT_TOOL_REAP_AND_FRESH_GONE',
        'no_retry': True, 'learner_models_loaded': False, 'optimizer_updates': 0,
        'gazebo_worlds_submitted': len(reports), 'gazebo_robots_per_world': 3,
        'pilot_added_seconds': '0', 'validation_added_seconds': '0',
        'native_qualification_credit': False, 'p2a_complete': False}
    try:
        write(PREFIX / 'summary.json', summary)
        print(json.dumps({k: summary[k] for k in ('passed', 'engineering_added_parent_wall_seconds', 'errors')}))
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
