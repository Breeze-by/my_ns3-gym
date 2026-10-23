"""Bounded V62 metadata/five-pstats review; no scientific/native consumer."""
import argparse
import hashlib
import importlib.util
import json
import marshal
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

import fixed_integration_v1 as integration
import fixed_process_profile_v1 as core

HERE = Path(__file__).resolve().parent
ROOT, RUN = integration.ROOT, integration.RUN
DRIVER = Path('/tmp/mr3_p2a_v62_parent_v1')
CANONICAL = integration.W / 'report/assets/20261024_mr3_p2a_v62_process_profile'
A16 = integration.W / 'report/assets/20261019_mr3_p2a_v16/external_absence_v1.py'
PROFILE = 'mr3-p2a-v62-open101-8step-cprofile-v1'
LANES = {'motion_safety': ('main',), 'adapter': ('main', 'encoder'), 'worker': ('main', 'ros_spin')}


def require(value, message):
    if not value:
        raise ValueError(message)


def fingerprint(value):
    return [getattr(value, name) for name in ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


class Inputs:
    """Fixed bounded files, read once including complete SHA; no telemetry parser."""
    def __init__(self, deadline_ns):
        self.deadline_ns, self.rows, self.before = deadline_ns, [], {}
        self.metadata_bytes = self.pstats_bytes = 0

    def check_time(self):
        require(time.monotonic_ns() < self.deadline_ns, 'review/complete-parent cooperative deadline exceeded')

    def read(self, path, *, pstats=False, cap=4 * 1024**2):
        self.check_time()
        require(path.is_absolute() and path == path.resolve(strict=True), 'input path has a symlink component')
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode) and before.st_size <= cap, 'input is not bounded regular data')
        counter = 'pstats_bytes' if pstats else 'metadata_bytes'
        limit = 128 * 1024**2 if pstats else 64 * 1024**2
        require(getattr(self, counter) + before.st_size <= limit, 'cumulative input limit exceeded')
        raw = path.read_bytes()
        setattr(self, counter, getattr(self, counter) + len(raw))
        require(len(raw) == before.st_size and fingerprint(before) == fingerprint(path.lstat()), 'input changed during read')
        self.before[path] = fingerprint(before)
        self.rows.append(dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                              read_passes=1, stat=fingerprint(before)))
        self.check_time()
        return raw

    def finish(self):
        self.check_time()
        for path, before in self.before.items():
            require(fingerprint(path.lstat()) == before, 'bound input changed before review ended: ' + str(path))


def pstats_description(raw):
    values = marshal.loads(raw)
    require(type(values) is dict and values, 'pstats table is empty or malformed')
    rows = []
    for key, value in values.items():
        require(type(key) is tuple and len(key) == 3 and type(key[0]) is str
                and type(key[1]) is int and type(key[2]) is str, 'pstats function key is malformed')
        require(type(value) is tuple and len(value) == 5, 'pstats function row is malformed')
        cc, nc, tt, ct, callers = value
        require(type(cc) is int and type(nc) is int and 0 <= cc <= nc
                and type(tt) in (int, float) and type(ct) in (int, float)
                and math.isfinite(tt) and math.isfinite(ct) and tt >= 0 and ct >= 0
                and type(callers) is dict, 'pstats count/time is malformed')
        rows.append(dict(filename=key[0], line=key[1], function=key[2],
                         primitive_calls=cc, total_calls=nc, self_seconds=tt, cumulative_seconds=ct))
    return dict(function_count=len(rows), self_seconds_sum=sum(row['self_seconds'] for row in rows),
                top_self=sorted(rows, key=lambda row: row['self_seconds'], reverse=True)[:30],
                top_cumulative=sorted(rows, key=lambda row: row['cumulative_seconds'], reverse=True)[:30],
                timing_scope='cProfile function elapsed time; waiting included; cumulative rows overlap; not CPU or C++ kernel decomposition')


def fresh_saved_identities(evidence, proc_root=Path('/proc')):
    rows = []
    for (pid, start), occurrences in sorted(evidence.identities.items()):
        at = time.monotonic_ns()
        try:
            fields = (proc_root / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
            current, state = int(fields[19]), fields[0]
            gone = current != start
        except (FileNotFoundError, ProcessLookupError):
            current, state, gone = None, None, True
        rows.append(dict(pid=pid, start_ticks=start, current_start_ticks=current,
                         state=state, gone=gone, observed_monotonic_ns=at, occurrences=occurrences))
    return rows


def review(args):
    started = time.monotonic_ns()
    result = dict(schema='mr3-v62-fixed-profile-review-v1', diagnostic_profile=PROFILE,
                  passed=False, scientific_qualification=False, capacity_qualified=False,
                  P2A_passed=False, started_monotonic_ns=started, reviewer_identity=core.identity(),
                  actual_argv=[v.decode() for v in Path('/proc/self/cmdline').read_bytes().split(b'\0') if v],
                  errors=[], roles={}, identity_review_scope='same-object saved identities in declared closed metadata/profile receipts; no raw logs, no unrecorded-process absence claim')
    read = Inputs(started + 300 * 10**9)
    try:
        require(args.run == RUN and args.driver == DRIVER and args.scope == CANONICAL / 'scope_v1.json'
                and args.output == DRIVER / 'profile_review_v1.json', 'fixed V62 review paths differ')
        git = lambda *values: subprocess.check_output(['git', *values], cwd=ROOT)
        require(HERE == CANONICAL and args.freeze == git('rev-parse', 'HEAD').decode().strip()
                == git('rev-parse', 'origin/main').decode().strip() and not git('status', '--porcelain'),
                'exact canonical clean pushed source freeze required')
        pins = json.loads((HERE / 'base_source_pins_v1.json').read_text())
        for source in [*HERE.glob('*.py'), HERE / 'base_source_pins_v1.json', args.scope, A16,
                       *[Path(value) for value in pins['sources']]]:
            require(git('show', args.freeze + ':' + str(source.relative_to(ROOT))) == read.read(source),
                    'frozen review/source/spec bytes differ')
        module_spec = importlib.util.spec_from_file_location('mr3_v62_original_a16_evidence', A16)
        a16 = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(a16)
        evidence = a16.Evidence()
        load = lambda path: a16.parse(read.read(path))
        scope = load(args.scope)
        require(scope.get('diagnostic_profile') == PROFILE and scope.get('run_root') == str(RUN), 'fixed scope profile/run differs')
        resource = scope['resource']
        for key, expected in [('parent_cap_seconds', 1800), ('native_allocation_seconds', 1500),
                              ('close_reserve_seconds', 120), ('review_max_seconds', 300)]:
            require(type(resource.get(key)) is int and resource[key] == expected, 'fixed typed resource differs: ' + key)
        entry, execution, launcher = load(DRIVER / 'entry.json'), load(DRIVER / 'execution.json'), load(RUN / 'launcher.json')
        require(entry['freeze'] == args.freeze and type(entry['complete_parent_started_monotonic_ns']) is int,
                'parent entry freeze/start missing')
        read.deadline_ns = min(read.deadline_ns, entry['complete_parent_started_monotonic_ns'] + 1800 * 10**9)
        actual = execution['launcher']
        require(execution['schema'] == 'mr3-v62-profile-execution-v1' and actual['actual_waited'] is True
                and type(actual['actual_returncode']) is int and actual['actual_returncode'] == 0
                and actual['wait_errors'] == [] and actual['signals'] == []
                and actual['actual_argv'] == entry['actual_expected_launcher_argv']
                and type(actual['started_monotonic_ns']) is int and type(actual['ended_monotonic_ns']) is int
                and entry['complete_parent_started_monotonic_ns'] <= actual['started_monotonic_ns'] < actual['ended_monotonic_ns'],
                'genuine normal launcher wait/argv boundary failed')
        require(launcher['freeze'] == args.freeze and launcher['diagnostic_profile'] == PROFILE
                and launcher['scientific_qualification'] is False and launcher['capacity_qualified'] is False
                and launcher['nav2_parameter_readback_taken'] is False, 'diagnostic launcher scope differs')
        evidence.visit(actual['identity'], str(DRIVER / 'execution.json') + '/launcher/identity')
        result['operational_identities_excluded_from_runtime_absence'] = {
            key: entry.get(key) for key in ('driver_identity', 'bootstrap_identity', 'observed_nonowned_ancestors')}
        native, episode = RUN / 'native', core.OWNED_EPISODE
        paths = [native / 'benchmark_metadata.json', native / 'benchmark_summary.json',
                 native / 'worker0/worker_summary.json', *[episode / name for name in
                 ['metadata.json', 'supervisor_metadata.json', 'supervisor_shutdown.json', 'summary.json', 'nav2_shutdown.json', 'native_stop.json']]]
        documents = {}
        for path in paths:
            value = load(path)
            evidence.visit(value, str(path))
            documents[path] = value
        summary = documents[native / 'benchmark_summary.json']
        require(summary['passed'] is True and type(summary['valid_transitions']) is int and summary['valid_transitions'] == 8
                and type(summary['workers']) is int and summary['workers'] == 1
                and type(summary['steps_per_episode']) is int and summary['steps_per_episode'] == 8
                and summary['schedule'] == [['open', 101]] and summary['freeze'] == args.freeze
                and summary['actuation_profile'] == 'initial-zero-encoder-hold-v1'
                and summary['preparation_motion_probe'] is False and summary['training_eligible'] is False,
                'fixed eight actual transition diagnostic incomplete')
        workers = summary['workers_results']
        require(len(workers) == 1 and workers[0]['worker_id'] == 0 and workers[0]['error'] is None
                and len(workers[0]['episodes']) == 1, 'single fixed worker/episode failed')
        ep = workers[0]['episodes'][0]
        require(ep['scene'] == 'open' and type(ep['seed']) is int and ep['seed'] == 101
                and ep['transitions'] == 8 and ep['truncated'] is True and ep['terminated'] is False
                and ep['output_directory'] == str(episode), 'fixed episode did not return eight normal steps')
        epoch = ep['epoch']
        shutdown = documents[episode / 'supervisor_shutdown.json']
        worker_end = documents[episode / 'summary.json']
        require(shutdown['epoch'] == epoch and shutdown['worker_returncode'] == 0
                and shutdown['forced_shutdown'] is False and shutdown['failed_sample'] is False
                and shutdown['remaining_owned_processes'] == [] and shutdown['remaining_owned_zombies'] == []
                and worker_end['epoch'] == epoch and worker_end['transition_count'] == 8
                and worker_end['launch_returncode'] == 0 and worker_end['native_failures'] == []
                and worker_end['closed']['pending_goal_count'] == 0,
                'normal native/worker close failed')
        known = {(row['pid'], row['start_ticks']) for row in shutdown['owned_processes_seen']}
        for role, lanes in LANES.items():
            directory = episode / 'profiles' / role
            start, finish = load(directory / 'started.json'), load(directory / 'finished.json')
            require(start['profile_id'] == finish['profile_id'] == PROFILE and start['role'] == finish['role'] == role
                    and start['identity'] == finish['identity'] and finish['profile_complete'] is True
                    and finish['source_stable'] is True and finish['profile_errors'] == []
                    and start['parameters'] == finish['parameters']
                    and finish['scientific_qualification'] is False, 'complete real fixed role receipt failed: ' + role)
            identity = start['identity']
            require((identity['pid'], identity['start_ticks']) in known, 'profile role not in actual supervisor saved inventory')
            evidence.visit(start, str(directory / 'started.json'))
            evidence.visit(finish, str(directory / 'finished.json'))
            require(start['actual_argv'] == ['/usr/bin/python3', '-B', str(HERE / 'fixed_roles_entry_v1.py'), *start['program_argv']]
                    and start['program_argv'][0] == str(core.PROGRAMS[role]), 'actual fixed wrapper argv differs')
            expected_sources = {str(core.PROGRAMS[role]): core.PROGRAM_SHA256[role],
                                str(core.SOURCES[role][0]): core.SOURCES[role][1]}
            require(set(start['sources']) == set(expected_sources)
                    and all(start['sources'][path]['sha256'] == digest for path, digest in expected_sources.items()),
                    'actual role bound console/source receipt differs')
            for item in start['parameters']:
                snapshot = Path(item['snapshot'])
                require(snapshot.parent == directory and snapshot.name.startswith('parameters_'), 'parameter snapshot path differs')
                raw = read.read(snapshot, cap=1024**2)
                require(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'], 'actual parameter snapshot differs')
            profiles = finish['profiles']
            require(len(profiles) == len(lanes) and {row['lane'] for row in profiles} == set(lanes), 'fixed role lane set differs')
            rows = []
            for profile in profiles:
                lane = profile['lane']
                path = directory / (lane + '.pstats')
                require(profile['path'] == str(path) and profile['thread_exit_observed'] is (lane != 'main')
                        and type(profile['calls']) is int and profile['calls'] > 0, 'thread/profile completion differs')
                raw = read.read(path, pstats=True, cap=32 * 1024**2)
                require(len(raw) == profile['bytes'] and hashlib.sha256(raw).hexdigest() == profile['sha256'], 'complete pstats bytes differ')
                rows.append(dict(**profile, description=pstats_description(raw)))
            result['roles'][role] = dict(identity=identity, profiles=rows,
                process_cpu_ns=finish['process_cpu_ns'], elapsed_monotonic_ns=finish['ended_monotonic_ns'] - finish['started_monotonic_ns'])
            if role != 'worker':
                resolution = load(directory / 'console_resolution.json')
                require(resolution['role'] == role and resolution['source_sha256'] == core.SOURCES[role][1]
                        and Path(resolution['source_path']) == core.SOURCES[role][0].resolve()
                        and resolution['loaded_function_is_bound_module_main'] is True, 'bound console resolution failed')
        for source, directory in [(integration.SUPERVISOR, RUN / 'supervisor_projection'),
                                  (integration.WORKER, episode / 'profiles/worker/source_projection')]:
            record = load(directory / 'projection.json')
            base, changed = read.read(directory / 'base.py'), read.read(directory / 'executed_projection.py')
            expected, edits = integration.project(source, base)
            require(base == integration.bound_source(source) and changed == expected
                    and record['original_path'] == str(source) and record['edits'] == [list(row) for row in edits]
                    and record['original_sha256'] == hashlib.sha256(base).hexdigest()
                    and record['executed_projection_sha256'] == hashlib.sha256(changed).hexdigest()
                    and record['compile_filename'] == str(source) and record['whole_byte_inverse_checked'] is True,
                    'fixed transparent whole-source projection differs')
        hook = load(episode / 'profiles/adapter/encoder_hook.json')
        require(hook['source_sha256'] == core.SOURCES['adapter'][1], 'actual encoder hook source differs')
        require(len({(row['identity']['pid'], row['identity']['start_ticks']) for row in result['roles'].values()}) == 3,
                'three role process identities are not distinct')
        require(not evidence.errors and evidence.identities, 'saved identity parsing failed or empty')
        result['identities'] = fresh_saved_identities(evidence)
        require(all(row['gone'] for row in result['identities']), 'saved PID/start remains including zombie')
        known_pids = {pid for pid, start in evidence.identities}
        result['pids_without_saved_start'] = sorted(set(evidence.pid_only) - known_pids)
        require(not result['pids_without_saved_start'], 'PID-only occurrence remains UNKNOWN without saved start')
        read.finish()
        result.update(passed=True, epoch=epoch, actual_returned_transitions=8,
                      all_saved_identities_fresh_gone=True, all_five_profiles_complete=True,
                      source_projection_whole_inverse_verified=True, parameter_readback_taken=False,
                      actual_parameter_snapshots_verified=True)
    except (OSError, ValueError, KeyError, TypeError, IndexError, EOFError, subprocess.CalledProcessError) as error:
        result['errors'].append(repr(error))
    result.update(ended_monotonic_ns=time.monotonic_ns(), input_bindings=read.rows,
                  metadata_bytes_read=read.metadata_bytes, pstats_bytes_read=read.pstats_bytes,
                  limits=dict(review_max_seconds=300, pstats_each_bytes=32 * 1024**2,
                              pstats_total_bytes=128 * 1024**2, metadata_total_bytes=64 * 1024**2),
                  partial=not result['passed'], signals_sent=0, raw_streams_read=0,
                  scientific_readers_executed=0, native_runs=0)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    for flag in ('scope', 'run', 'driver', 'output'):
        parser.add_argument('--' + flag, required=True, type=Path)
    args = parser.parse_args(argv)
    require(args.output == DRIVER / 'profile_review_v1.json'
            and args.output.parent == args.output.parent.resolve(strict=True), 'fixed output path differs')
    result = review(args)
    with args.output.open('x') as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write('\n')
    print(json.dumps({key: result[key] for key in ('schema', 'passed', 'partial', 'errors', 'pstats_bytes_read')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
