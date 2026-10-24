"""Bounded startup-only metadata/identity review; no qualification or telemetry replay."""

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
ASSETS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets'
ABSENCE = ASSETS / '20261019_mr3_p2a_v16/external_absence_v1.py'
ABSENCE_SHA256 = 'cedae11c4b9bbf6f4887ae5afe2fa10fff04e5a28595f5c9e748669c8d18493f'
PROTOCOL = 'received-input-pause-drain-v1'
READY = ('monitor_ready', 'initial_inputs_ready', 'motion_ready', 'odometry_recorder_ready')
CONFIGURATION = {'workers': 2, 'episodes_per_worker': 1, 'scenes': ['rooms'],
                 'seed': 101, 'episode_steps': 1}
MAX_BYTES, MAX_LINE, MAX_ROWS = 8 * 1024 * 1024, 1024 * 1024, 20000
STAT_FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def load_absence():
    raw = ABSENCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ABSENCE_SHA256:
        raise ValueError('immutable A16 Evidence source differs')
    spec = importlib.util.spec_from_file_location('v49_immutable_a16_absence', ABSENCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def integer(value):
    return type(value) is int and value >= 0


def read_journal(stream, *, epoch, parse, budget):
    """Decode every bounded row, retaining phase/receipt facts, never raw plant data."""
    result = {'rows': 0, 'bytes': 0, 'complete': False, 'errors': [],
              'stages': [], 'ready_callbacks': [], 'failures': [],
              'release_rows': [], 'reset_complete_rows': []}
    digest = hashlib.sha256()
    previous_wall = None
    previous_clock = None
    callback_fields = set()
    seen_pause = False
    seen_release = False
    while True:
        line = stream.readline(min(MAX_LINE + 1, MAX_BYTES - budget['bytes'] + 1))
        if not line:
            result['complete'] = True
            break
        digest.update(line)
        result['bytes'] += len(line)
        budget['bytes'] += len(line)
        result['rows'] += 1
        budget['rows'] += 1
        ordinal = result['rows']
        if len(line) > MAX_LINE or budget['bytes'] > MAX_BYTES or budget['rows'] > MAX_ROWS:
            result['errors'].append({'line': ordinal, 'reason': 'journal byte/line/row limit exceeded'})
            break
        try:
            row = parse(line)
            if (type(row) is not dict or row.get('schema') != 'mr3-startup-readiness-v1'
                    or row.get('epoch') != epoch or row.get('protocol') != PROTOCOL
                    or type(row.get('kind')) is not str or type(row.get('stage')) is not str
                    or not row['stage'] or not integer(row.get('wall_monotonic_ns'))
                    or not integer(row.get('clock_ns'))
                    or row.get('physical_ns') is not None and not integer(row['physical_ns'])
                    or type(row.get('ready')) is not dict or set(row['ready']) != set(READY)
                    or any(type(row['ready'][field]) is not bool for field in READY)
                    or type(row.get('callback_fields_received')) is not list
                    or any(field not in READY for field in row['callback_fields_received'])
                    or len(set(row['callback_fields_received'])) != len(row['callback_fields_received'])):
                raise ValueError('startup row schema/epoch/protocol/types differ')
            wall, clock = row['wall_monotonic_ns'], row['clock_ns']
            if previous_wall is not None and (wall < previous_wall or clock < previous_clock):
                raise ValueError('startup wall/ROS clock regressed')
            previous_wall, previous_clock = wall, clock
            fact = {'line': ordinal, 'wall_monotonic_ns': wall, 'clock_ns': clock,
                    'physical_ns': row.get('physical_ns'), 'stage': row['stage'],
                    'ready': row['ready'], 'callback_fields_received': row['callback_fields_received']}
            if row['kind'] == 'ready_callback':
                field = row.get('field')
                if field not in READY or type(row.get('receipt')) is not dict:
                    raise ValueError('invalid actual readiness callback')
                callback_fields.add(field)
                result['ready_callbacks'].append({**fact, 'field': field})
            if row['kind'] == 'stage_entered':
                result['stages'].append(fact)
                if row['stage'] == 'pause_requested':
                    if not all(row['ready'][field] for field in READY if field != 'motion_ready'):
                        raise ValueError('pause preceded received upstream three inputs')
                    seen_pause = True
                if row['stage'] == 'request_initial_snapshot_release':
                    if not seen_pause or not all(row['ready'].values()) or callback_fields != set(READY):
                        raise ValueError('release preceded real pause/four ready callbacks and four true values')
                    if row['physical_ns'] != clock:
                        raise ValueError('release was not at the exact paused ROS/physical clock')
                    seen_release = True
                    result['release_rows'].append(fact)
                if row['stage'] == 'reset_complete':
                    if not seen_release:
                        raise ValueError('reset completed without the prior release stage')
                    result['reset_complete_rows'].append(fact)
            if row['kind'] in ('failure', 'exploration_failure_received'):
                result['failures'].append({**fact, 'kind': row['kind'],
                    'error': row.get('error'),
                    'epoch_bound_to_current_startup': row.get('epoch_bound_to_current_startup')})
        except (ValueError, TypeError, KeyError, UnicodeError) as error:
            result['errors'].append({'line': ordinal, 'reason': str(error)})
    result['sha256'] = digest.hexdigest()
    result['startup_completed'] = (result['complete'] and not result['errors']
        and len(result['release_rows']) == 1 and len(result['reset_complete_rows']) == 1
        and not any(row['kind'] == 'failure' or row['epoch_bound_to_current_startup'] is True
                    and row['stage'] != 'reset_complete'
                    for row in result['failures']))
    return result


def proc_identity(pid, proc=Path('/proc')):
    tail = (proc / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'start_ticks': int(tail[19]), 'state': tail[0], 'parent': int(tail[1])}


def observe_identities(evidence, *, active_exclusions, proc=Path('/proc')):
    present, reused, absent, unreadable, exclusions = [], [], [], [], []
    for pid, start in sorted(evidence.identities):
        observed = time.monotonic_ns()
        try:
            current = proc_identity(pid, proc)
            row = {'pid': pid, 'start_ticks': start, 'current_start_ticks': current['start_ticks'],
                   'state': current['state'], 'observed_monotonic_ns': observed}
            if current['start_ticks'] != start:
                reused.append(row)
            elif (pid, start) in active_exclusions and current['state'] != 'Z':
                exclusions.append({**row, 'reason': active_exclusions[(pid, start)],
                    'external_root_freshgone_recheck_required': True})
            else:
                present.append(row)  # A saved exact identity in Z is present too.
        except (FileNotFoundError, ProcessLookupError):
            absent.append({'pid': pid, 'start_ticks': start, 'observed_monotonic_ns': observed})
        except (OSError, ValueError, IndexError) as error:
            unreadable.append({'pid': pid, 'start_ticks': start, 'error': repr(error)})
    return {'present': present, 'same_pid_different_start': reused, 'absent_proc_stat': absent,
            'unreadable': unreadable, 'active_exclusions': exclusions,
            'all_nonexcluded_saved_identities_absent': not (present or unreadable)}


def current_ancestors():
    result, pid = set(), os.getppid()
    while pid > 1:
        try:
            row = proc_identity(pid)
        except (OSError, ValueError, IndexError):
            break
        key = row['pid'], row['start_ticks']
        if key in result:
            break
        result.add(key)
        pid = row['parent']
    return result


def source_proof(scope, freeze, scope_path):
    rows, errors = [], []
    sources = [(item, True) for item in scope['source_bindings']]
    sources.extend((item, False) for item in scope['library_bindings'])
    scope_raw = scope_path.read_bytes()
    sources.append(({'path': str(scope_path), 'bytes': len(scope_raw),
                     'sha256': hashlib.sha256(scope_raw).hexdigest()}, True))
    for item, is_source in sources:
        try:
            path = Path(item['path'])
            if not path.is_absolute() or is_source and not path.is_relative_to(ROOT):
                raise ValueError('source must be canonical absolute repository path; library must be absolute')
            before = path.stat()
            raw = path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            row = {'path': str(path), 'bytes': len(raw), 'sha256': actual, 'git_source': is_source,
                   'stat_before': {key: getattr(before, key) for key in STAT_FIELDS}}
            frozen = raw
            if is_source:
                frozen = subprocess.check_output(['git', 'show', freeze + ':' + str(path.relative_to(ROOT))], cwd=ROOT)
                row['frozen_sha256'] = hashlib.sha256(frozen).hexdigest()
            after = path.stat()
            row['passed'] = (len(raw) == item['bytes'] and actual == item['sha256']
                and raw == frozen and all(getattr(before, k) == getattr(after, k) for k in STAT_FIELDS))
            rows.append(row)
            if not row['passed']:
                raise ValueError('scope/current/Git source bytes differ')
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
            errors.append({'path': item.get('path'), 'reason': str(error)})
    paths = {row['path'] for row in rows if row['passed']}
    for path in (ABSENCE, Path(__file__).resolve()):
        if str(path) not in paths:
            errors.append({'path': str(path), 'reason': 'reviewer and immutable Evidence library must be explicitly frozen in scope'})
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    origin = subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip()
    if head != freeze or origin != freeze:
        errors.append({'path': 'Git HEAD/origin/main', 'reason': 'actual checkout/pushed freeze differs'})
    return {'passed': not errors, 'sources': rows, 'errors': errors,
            'git_head': head, 'origin_main': origin}


def inspect(args):
    started = time.monotonic_ns()
    library = load_absence()
    evidence = library.Evidence()
    scope_path, run, driver = args.scope.resolve(), args.run.resolve(), args.driver.resolve()
    scope = library.parse(scope_path.read_bytes())
    if (scope.get('fixed_configuration') != CONFIGURATION or Path(scope['run_dir']).resolve() != run
            or Path(scope['driver_dir']).resolve() != driver
            or not re.fullmatch(r'[0-9a-f]{40}', args.freeze)
            or type(scope.get('expected_job')) is not list):
        raise ValueError('scope paths/fixed startup-only configuration/freeze differ')
    if args.output.exists() or args.output.resolve().is_relative_to(run):
        raise ValueError('review output must be exclusive and outside the closed native run')
    proof = source_proof(scope, args.freeze, scope_path)
    selected = {scope_path, driver / 'entry.json', driver / 'execution.json',
                run / 'benchmark_metadata.json', run / 'benchmark_summary.json'}
    episode_paths = []
    for worker in (0, 1):
        worker_root = run / ('worker' + str(worker))
        episode = worker_root / 'episode001_rooms_101'
        episode_paths.append((worker, episode))
        selected.add(worker_root / 'worker_summary.json')
        selected.update(episode / name for name in ('metadata.json', 'supervisor_metadata.json',
            'supervisor_shutdown.json', 'summary.json', 'launch.log'))
        selected.update(path for pattern in ('*process*.json', '*manifest*.json', 'infrastructure_*.json')
                        for path in episode.glob(pattern) if path.is_file())
    for path in sorted(selected):
        if not path.exists():
            evidence.error(str(path), 'selected closed metadata input missing (failure is retained)')
            continue
        if path.stat().st_size > 32 * 1024 * 1024:
            evidence.error(str(path), 'metadata/launch input exceeds 32MiB bound')
            continue
        try:
            evidence.consume(path)
        except (OSError, ValueError, TypeError) as error:
            evidence.error(str(path), error)
    documents = evidence.documents
    benchmark = documents.get(str(run / 'benchmark_summary.json'), {})
    metadata = documents.get(str(run / 'benchmark_metadata.json'), {})
    execution = documents.get(str(driver / 'execution.json'), {})
    diagnostic_errors = []
    if (metadata.get('workers') != 2 or metadata.get('steps_per_episode') != 1
            or metadata.get('schedule') != [['rooms', 101]] or metadata.get('freeze') != args.freeze):
        diagnostic_errors.append('actual benchmark fixed configuration/freeze differs')
    if execution.get('actual_argv') != scope['expected_job']:
        diagnostic_errors.append('actual driver benchmark argv differs from scope')
    if (execution.get('actual_waited') is not True or execution.get('actual_returncode') != 0
            or not integer(execution.get('started_monotonic_ns'))
            or not integer(execution.get('ended_monotonic_ns'))
            or execution['ended_monotonic_ns'] < execution['started_monotonic_ns']):
        diagnostic_errors.append('actual native child wait/zero returncode not established')
    budget, journals = {'bytes': 0, 'rows': 0}, []
    for worker, episode in episode_paths:
        supervisor = documents.get(str(episode / 'supervisor_metadata.json'), {})
        worker_metadata = documents.get(str(episode / 'metadata.json'), {})
        shutdown = documents.get(str(episode / 'supervisor_shutdown.json'), {})
        path = episode / 'startup_readiness.jsonl'
        epoch = supervisor.get('epoch')
        if (not epoch or supervisor.get('worker_id') != worker or supervisor.get('scene') != 'rooms'
                or supervisor.get('seed') != 101 or worker_metadata.get('epoch') != epoch
                or supervisor.get('startup_readiness_protocol') != PROTOCOL
                or worker_metadata.get('startup_readiness_protocol') != PROTOCOL):
            diagnostic_errors.append('worker ' + str(worker) + ' actual metadata/epoch/protocol differs')
        try:
            before = path.stat()
            with path.open('rb') as stream:
                journal = read_journal(stream, epoch=epoch, parse=library.parse, budget=budget)
            after = path.stat()
            if any(getattr(before, k) != getattr(after, k) for k in STAT_FIELDS):
                evidence.error(str(path), 'startup journal changed during complete read')
            evidence.stat_before[path] = before
            evidence.bindings.append({'path': str(path), 'bytes': journal['bytes'],
                                      'sha256': journal['sha256'], 'complete': journal['complete']})
            journals.append({'worker_id': worker, 'epoch': epoch, 'path': str(path), **journal})
            if not journal['startup_completed']:
                diagnostic_errors.append('worker ' + str(worker) + ' startup did not independently complete')
        except OSError as error:
            evidence.error(str(path), error)
            diagnostic_errors.append('worker ' + str(worker) + ' startup journal missing/unreadable')
        if (shutdown.get('epoch') != epoch or shutdown.get('forced_shutdown') is not False
                or shutdown.get('failed_sample') is not False or shutdown.get('worker_returncode') != 0
                or shutdown.get('remaining_owned_processes') != []
                or shutdown.get('remaining_owned_zombies') != []):
            diagnostic_errors.append('worker ' + str(worker) + ' clean normal shutdown not established')
    results = benchmark.get('workers_results', [])
    if type(results) is not list:
        results = []
    if (benchmark.get('passed') is not True or len(results) != 2
            or any(type(row) is not dict for row in results)
            or {row.get('worker_id') for row in results} != {0, 1}
            or any(row.get('error') or row.get('cleanup_error') or type(row.get('episodes')) is not list
                   or len(row['episodes']) != 1 or type(row['episodes'][0]) is not dict
                   or row['episodes'][0].get('scene') != 'rooms' or row['episodes'][0].get('seed') != 101
                   or row['episodes'][0].get('transitions') != 1 for row in results)):
        diagnostic_errors.append('two actual clean rooms101/one-return benchmark episodes not established')
    known = {pid for pid, start in evidence.identities}
    unbound = sorted((set(evidence.pid_only) | evidence.launch_pids) - known)
    if not evidence.identities or unbound:
        evidence.error('saved identities', 'empty identity inventory or saved PID without same-object start: ' + repr(unbound))
    ancestors = current_ancestors()
    entry = documents.get(str(driver / 'entry.json'), {})
    active = {}
    for item in entry.get('active_exclusions', []):
        try:
            identity, reason = item['identity'], item['reason']
            key = library.positive_integer(identity['pid']), library.positive_integer(identity['start_ticks'])
            if key not in ancestors or type(reason) is not str or not reason:
                raise ValueError('active exclusion must be a live exact current-review ancestor with a reason')
            active[key] = reason
        except (ValueError, KeyError, TypeError) as error:
            evidence.error(str(driver / 'entry.json'), error)
    observations = observe_identities(evidence, active_exclusions=active)
    evidence.finish()
    for row in proof['sources']:
        try:
            stat = Path(row['path']).stat()
            if any(getattr(stat, key) != value for key, value in row['stat_before'].items()):
                raise ValueError('bound source/library/scope changed during complete review')
        except (OSError, ValueError) as error:
            proof['errors'].append({'path': row['path'], 'reason': str(error)})
    proof['passed'] = not proof['errors']
    closed = not (evidence.errors or not proof['passed'] or observations['present'] or observations['unreadable'])
    diagnostic = closed and not diagnostic_errors
    return {'schema': 'mr3-v49-startup-closed-review-v1', 'passed': diagnostic,
        'closed_review_passed': closed, 'startup_diagnostic_passed': diagnostic,
        'scope': 'two workers rooms101 one step startup engineering diagnosis only',
        'scientific_pass_claimed': False, 'native_qualification': False, 'training_eligible': False,
        'old_failures_reclassified': False, 'native_runs_started_by_review': 0, 'gpu_calls': 0,
        'signals_sent': 0, 'freeze': args.freeze, 'source_proof': proof,
        'started_monotonic_ns': started, 'ended_monotonic_ns': time.monotonic_ns(),
        'identity_count': len(evidence.identities),
        'identities': [{'pid': pid, 'start_ticks': start, 'occurrences': occurrences}
                       for (pid, start), occurrences in sorted(evidence.identities.items())],
        **observations, 'pids_without_saved_start': unbound,
        'errors': evidence.errors, 'diagnostic_errors': diagnostic_errors,
        'input_bindings': evidence.bindings, 'startup_journals': journals,
        'journal_limits': {'total_bytes': MAX_BYTES, 'line_bytes': MAX_LINE, 'total_rows': MAX_ROWS},
        'benchmark_passed': benchmark.get('passed'),
        'excluded_scope': 'No original motion/odometry/physics/map/actor trace, model, truth or scientific auditor is consumed. Active driver/outer ancestors require a later external freshgone review.'}


def self_check():
    library = load_absence()
    epoch = 'artificial-only'

    def row(kind, stage, index, ready=None, **extra):
        return {'schema': 'mr3-startup-readiness-v1', 'epoch': epoch, 'protocol': PROTOCOL,
                'kind': kind, 'stage': stage, 'wall_monotonic_ns': index, 'clock_ns': 10,
                'physical_ns': 10, 'ready': {field: True for field in READY} if ready is None else ready,
                'callback_fields_received': list(READY), **extra}

    callbacks = [row('ready_callback', 'upstream', i, field=field, receipt={'actual': True})
                 for i, field in enumerate(READY)]
    good = callbacks + [row('stage_entered', 'pause_requested', 4),
        row('stage_entered', 'request_initial_snapshot_release', 5),
        row('stage_entered', 'reset_complete', 6)]

    def check(rows, **kwargs):
        raw = b''.join(json.dumps(value).encode() + b'\n' for value in rows)
        return read_journal(io.BytesIO(raw), epoch=epoch, parse=library.parse,
                            budget=kwargs.get('budget', {'bytes': 0, 'rows': 0}))

    assert check(good)['startup_completed']
    assert not check(good[:-1])['startup_completed']
    assert not check(good[1:])['startup_completed']
    wrong = [dict(value) for value in good]
    wrong[0]['epoch'] = 'other-epoch'
    assert check(wrong)['errors']
    wrong = [dict(value) for value in good]
    wrong[-2]['ready'] = dict.fromkeys(READY, False)
    assert check(wrong)['errors']
    wrong = [dict(value) for value in good]
    wrong[-1]['wall_monotonic_ns'] = 1
    assert check(wrong)['errors']
    assert not check(good + [row('failure', 'failed', 7, error='retained')])['startup_completed']
    assert check(good, budget={'bytes': MAX_BYTES, 'rows': 0})['complete'] is False
    assert check(good, budget={'bytes': 0, 'rows': MAX_ROWS})['complete'] is False
    bad = read_journal(io.BytesIO(b'{"epoch":1,"epoch":2}\n'), epoch=epoch,
                       parse=library.parse, budget={'bytes': 0, 'rows': 0})
    assert bad['errors'] and bad['complete']
    evidence = library.Evidence()
    evidence.visit({'pid': 1}, 'artificial-a')
    evidence.visit({'start_ticks': 2}, 'artificial-b')
    assert evidence.errors and not evidence.identities
    evidence = library.Evidence()
    evidence.visit({'pid': 1, 'start_ticks': 2}, 'artificial-c')
    assert (1, 2) in evidence.identities
    with tempfile.TemporaryDirectory(prefix='mr3_v49_artificial_proc_') as directory:
        proc = Path(directory)
        for pid, start, state in ((12, 2, 'Z'), (13, 99, 'R'), (14, 4, 'R')):
            path = proc / str(pid)
            path.mkdir()
            fields = [state, '1'] + ['0'] * 17 + [str(start)]
            (path / 'stat').write_text(str(pid) + ' (artificial only) ' + ' '.join(fields))
        evidence = library.Evidence()
        for pid, start in ((12, 2), (13, 3), (14, 4), (15, 5)):
            evidence.visit({'pid': pid, 'start_ticks': start}, 'artificial-proc')
        observed = observe_identities(evidence, active_exclusions={(14, 4): 'artificial active ancestor'}, proc=proc)
        assert (len(observed['present']) == len(observed['same_pid_different_start'])
                == len(observed['active_exclusions']) == len(observed['absent_proc_stat']) == 1
                and observed['present'][0]['state'] == 'Z'
                and observed['all_nonexcluded_saved_identities_absent'] is False)
    return {'passed': True, 'checks': 13, 'scope': 'artificial journal, same-object Evidence and temporary fake /proc only',
            'native_runs': 0, 'engineering_increment_seconds': '0'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', type=Path)
    parser.add_argument('--freeze')
    parser.add_argument('--run', type=Path)
    parser.add_argument('--driver', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        result = self_check()
    else:
        if any(getattr(args, key) is None for key in ('scope', 'freeze', 'run', 'driver', 'output')):
            parser.error('review requires scope/freeze/run/driver/output')
        result = inspect(args)
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps({key: result[key] for key in ('passed', 'schema', 'checks') if key in result}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
