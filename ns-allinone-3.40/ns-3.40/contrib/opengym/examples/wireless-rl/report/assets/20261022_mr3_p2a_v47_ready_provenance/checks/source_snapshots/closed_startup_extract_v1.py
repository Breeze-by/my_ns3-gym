"""One bounded, read-only V45 failed-startup extraction; no scientific verdict.

Only eight declared originals are consumed. No production imports, telemetry
replay, map blobs, truth, models, ROS calls or process signalling are used.
--self-check exercises only artificial in-memory inputs.
"""
import argparse
from collections import Counter, deque
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
RUN = ROS / ('log/mr3_p2a_reach_v45/mr3_p2a_reach_v45_reset/'
             'worker1/episode003_rooms_101')
EPOCH = 'mr3_p2a_reach_v45_reset_w1_e3_df93697f'
NATIVE_FREEZE = 'cace46e08e53b7e89a434e23721db85ac993f6f5'
MIB = 1024 * 1024
FILES = {'launch.log': 2 * MIB, 'adapter.jsonl': 8 * MIB, **dict.fromkeys((
    'metadata.json', 'supervisor_metadata.json', 'infrastructure_failure.json',
    'infrastructure_cleanup.json', 'nav2_shutdown.json', 'supervisor_shutdown.json'), MIB)}
P = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/'
SOURCE_PATHS = [P + name for name in ('mr3_adapter.py', 'motion_safety.py', 'task_evaluator.py')]
SOURCE_PATHS += ['ros2_ws/ros2-multi-robot-automap/scripts/' + name
                 for name in ('mr3_env_worker.py', 'run_mr3_adapter_probe.py')]
SOURCE_PATHS += ['ros2_ws/ros2-multi-robot-automap/src/multi_robot/' + name for name in (
    'launch/gazebo_multirobot_mapping_with_nav2.launch.py', 'src/mr3_odometry_recorder.cpp')]
NATIVE_STOP = re.compile(
    r'\[INFO\] \[mr3_gazebo_native_stop-(\d+)\]: process started with pid \[(\d+)\]')
SELECT = re.compile(r'mr3_gazebo_native_stop|MR3_|ready|[Aa]ctivat|[Ee]rror|[Ff]ail|'
                    r'Timeout|[Ii]nitial|[Ss]tartup|exited|finished|signal|shutdown')


def require(ok, text):
    if not ok:
        raise ValueError(text)


def identity():
    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': os.getpid(), 'parent': os.getppid(), 'start_ticks': int(fields[19]),
            'group': os.getpgrp(), 'session': os.getsid(0)}


def stamp(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON member: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def state_summary(row):
    payload, now = row.get('payload'), row.get('stamp')
    if type(payload) is not dict:
        return {'states_fresh_at_record_stamp': 'NOT_RECORDED'}
    result = {'stamp': now, 'sequence': payload.get('sequence'), 'robots': []}
    robots = payload.get('robots')
    complete = type(robots) is list and len(robots) == 3 and finite(now)
    fresh = complete
    for robot in robots if type(robots) is list else []:
        require(type(robot) is dict, 'state_update robot is not an object')
        item = {key: robot[key] for key in ('name', 'valid', 'epoch', 'source_stamp',
            'received_stamp', 'odom_source_stamp', 'tf_source_stamp', 'tf_validity_stamp') if key in robot}
        measured = all(key in robot for key in ('valid', 'source_stamp', 'received_stamp'))
        complete = complete and measured
        for key in ('source_stamp', 'received_stamp'):
            value = robot.get(key)
            item[key + '_age_at_record_sec'] = now - value if finite(now) and finite(value) else 'NOT_RECORDED'
        fresh = fresh and robot.get('valid') is True and all(
            finite(robot.get(key)) and 0 <= now - robot[key] <= .5
            for key in ('source_stamp', 'received_stamp'))
        result['robots'].append(item)
    result['states_fresh_at_record_stamp'] = bool(fresh) if complete else 'NOT_RECORDED'
    result['scope'] = 'Logged state callback stamp only; not every later maintain() or worker receipt.'
    return result


def scan(stream, kind, limit):
    digest, count, line_count = hashlib.sha256(), 0, 0
    errors, error_count, selected, omitted = [], 0, [], 0
    counts, last_states, tail = Counter(), deque(maxlen=3), deque(maxlen=20)
    starts, native_lines, previous_state_stamp, regressions = [], [], None, 0
    native_name_count = 0
    for raw in iter(lambda: stream.readline(MIB + 1), b''):
        count += len(raw); line_count += 1; digest.update(raw)
        require(count <= limit and len(raw) <= MIB, 'finite byte/line bound exceeded')
        reference = {'line_1based': line_count, 'line_sha256': hashlib.sha256(raw).hexdigest()}
        if kind == 'launch':
            text = raw.decode('utf-8', errors='replace').rstrip('\r\n')
            matches = NATIVE_STOP.findall(text)
            starts.extend({'suffix': suffix, 'pid': int(pid), **reference} for suffix, pid in matches)
            require(len(starts) <= 1000, 'native-stop match bound exceeded')
            if 'mr3_gazebo_native_stop' in text:
                native_name_count += 1
                if len(native_lines) < 100:
                    native_lines.append({**reference, 'text': text[:4096], 'text_truncated': len(text) > 4096})
            tail.append({**reference, 'text': text[:2048], 'text_truncated': len(text) > 2048})
            if SELECT.search(text):
                if len(selected) < 200:
                    selected.append({**reference, 'text': text[:4096], 'text_truncated': len(text) > 4096})
                else:
                    omitted += 1
            continue
        try:
            row = decode(raw)
            require(type(row) is dict and type(row.get('kind')) is str, 'invalid adapter event envelope')
            require(row.get('epoch') == EPOCH, 'adapter event epoch differs')
            counts[row['kind']] += 1
            if row['kind'] == 'state_update':
                state = state_summary(row)
                current = row.get('stamp')
                if finite(current) and finite(previous_state_stamp) and current < previous_state_stamp:
                    regressions += 1
                previous_state_stamp = current
                last_states.append({**reference, **state})
            elif row['kind'] in ('initial_inputs_ready', 'invalid_state', 'invalid_map_metadata',
                    'task_start', 'task_stopped', 'safety_stop', 'rpc_error', 'protocol', 'state_stale'):
                if len(selected) < 100:
                    payload = row.get('payload')
                    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
                    selected.append({**reference, 'kind': row['kind'], 'stamp': row.get('stamp'),
                        'payload': payload if len(encoded) <= 16384 else None,
                        'payload_omitted_for_bound': len(encoded) > 16384,
                        'payload_keys': sorted(payload) if type(payload) is dict else None})
                else:
                    omitted += 1
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            error_count += 1
            if len(errors) < 20:
                errors.append({**reference, 'error': str(error)[:512]})
    common = {'bytes': count, 'sha256': digest.hexdigest(), 'lines': line_count,
              'selected': selected, 'selected_omitted': omitted,
              'parse_error_count': error_count, 'parse_errors': errors,
              'parse_errors_omitted': error_count - len(errors)}
    if kind == 'launch':
        common.update(native_stop_exact_regex=NATIVE_STOP.pattern,
            native_stop_started_matches=starts, native_stop_started_match_count=len(starts),
            original_identity_condition=('exactly_one' if len(starts) == 1 else
                                         'missing' if not starts else 'ambiguous'),
            native_stop_name_lines=native_lines, tail=list(tail),
            native_stop_name_lines_omitted=native_name_count - len(native_lines),
            original_helper_not_executed=True)
    else:
        common.update(event_counts=dict(counts), last_state_updates=list(last_states),
            state_stamp_regressions=regressions,
            initial_inputs_ready_event_count=counts['initial_inputs_ready'],
            task_start_event_count=counts['task_start'])
    return common


def consume(path, limit, kind):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'unsupported/oversize source: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(before), 'source changed before open')
        if kind in ('launch', 'adapter'):
            value = scan(stream, kind, limit)
        else:
            raw = stream.read(limit + 1)
            require(len(raw) <= limit, 'metadata byte bound exceeded')
            value = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'document': decode(raw)}
        require(stamp(os.fstat(stream.fileno())) == stamp(before), 'source changed while open')
    after = path.lstat()
    require(stamp(before) == stamp(after) and value['bytes'] == before.st_size, 'source changed during read')
    return value, {'path': str(path), 'bytes': value['bytes'], 'sha256': value['sha256'],
                   'stat_before': stamp(before), 'stat_after': stamp(after)}


def source_bindings(freeze):
    require(re.fullmatch(r'[0-9a-f]{40}', freeze) is not None, 'source freeze must be exact Git SHA')
    result = []
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        before = path.lstat(); raw = path.read_bytes()
        require(stamp(path.lstat()) == stamp(before), 'runtime source changed during read')
        frozen = subprocess.run(['git', 'show', freeze + ':' + relative], cwd=ROOT,
                                check=True, capture_output=True, timeout=10).stdout
        require(raw == frozen, 'current source differs from declared freeze: ' + relative)
        result.append({'path': relative, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                       'stat': stamp(before), 'git_freeze': freeze})
    return result


def self_check():
    for size in (0, 1, 2):
        raw = b''.join(('[INFO] [mr3_gazebo_native_stop-%d]: process started with pid [%d]\n'
                        % (index + 1, index + 100)).encode() for index in range(size))
        assert scan(io.BytesIO(raw), 'launch', MIB)['native_stop_started_match_count'] == size
    def event(kind, payload, stamp=1.):
        return json.dumps({'kind': kind, 'payload': payload, 'stamp': stamp, 'epoch': EPOCH}).encode() + b'\n'
    assert scan(io.BytesIO(event('initial_inputs_ready', {})), 'adapter', MIB)['initial_inputs_ready_event_count'] == 1
    assert scan(io.BytesIO(b''), 'adapter', MIB)['initial_inputs_ready_event_count'] == 0
    missing = event('state_update', {'sequence': 1, 'robots': [{'name': name} for name in ('tb1', 'tb2', 'tb3')]})
    assert scan(io.BytesIO(missing), 'adapter', MIB)['last_state_updates'][0]['states_fresh_at_record_stamp'] == 'NOT_RECORDED'
    robots = [{'name': name, 'valid': True, 'source_stamp': .9, 'received_stamp': .95}
              for name in ('tb1', 'tb2', 'tb3')]
    normal = event('state_update', {'sequence': 2, 'robots': robots})
    assert scan(io.BytesIO(normal), 'adapter', MIB)['last_state_updates'][0]['states_fresh_at_record_stamp'] is True
    unordered = normal + event('state_update', {'sequence': 1, 'robots': robots}, stamp=.8)
    assert scan(io.BytesIO(unordered), 'adapter', MIB)['state_stamp_regressions'] == 1
    bad = scan(io.BytesIO(b'not-json\n' * 25), 'adapter', MIB)
    assert bad['parse_error_count'] == 25 and len(bad['parse_errors']) == 20 and bad['parse_errors_omitted'] == 5
    try:
        scan(io.BytesIO(b'x' * 9), 'launch', 8)
    except ValueError:
        pass
    else:
        raise AssertionError('byte cap did not reject')
    return {'schema': 'mr3-v46-startup-forensic-artificial-check-v1', 'checks': 10,
            'passed': True, 'native_files_read': 0, 'scientific_credit': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--source-freeze')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.self_check:
        require(args.output is None and args.source_freeze is None, 'self-check is an isolated in-memory role')
        print(json.dumps(self_check()), flush=True)
        return 0
    require(args.output is not None and args.source_freeze is not None, 'output and source-freeze required')
    require(not args.output.exists() and not args.output.is_symlink(), 'exclusive output already exists')
    require(not args.output.absolute().is_relative_to(RUN), 'output cannot be inside original episode')
    start, bindings = time.monotonic_ns(), source_bindings(args.source_freeze)
    inputs, results = [], {}
    for name, limit in FILES.items():
        kind = 'launch' if name == 'launch.log' else 'adapter' if name == 'adapter.jsonl' else 'metadata'
        results[name], proof = consume(RUN / name, limit, kind)
        inputs.append(proof)
    require(results['metadata.json']['document'].get('freeze') == NATIVE_FREEZE
            and results['metadata.json']['document'].get('epoch') == EPOCH
            and results['supervisor_metadata.json']['document'].get('epoch') == EPOCH
            and results['infrastructure_failure.json']['document'].get('request', {}).get('epoch') == EPOCH,
            'closed metadata does not bind the declared native freeze/epoch')
    for proof in inputs:
        require(stamp(Path(proof['path']).lstat()) == proof['stat_before'], 'original changed before result seal')
    require(source_bindings(args.source_freeze) == bindings, 'runtime source changed before result seal')
    result = {'schema': 'mr3-v46-closed-startup-forensic-v1', 'identity': identity(),
        'source_freeze': args.source_freeze, 'native_freeze': NATIVE_FREEZE, 'epoch': EPOCH,
        'source_bindings': bindings, 'inputs': inputs, 'results': results,
        'started_monotonic_ns': start, 'ended_monotonic_ns': time.monotonic_ns(),
        'worker_ready_bools_at_timeout': {name: 'NOT_RECORDED' for name in
            ('monitor_ready', 'initial_inputs_ready', 'motion_ready', 'odometry_recorder_ready')},
        'adapter_gate_histories': {name: 'NOT_RECORDED' for name in
            ('monitor_ready', 'map_inputs_match', 'navigation_action_servers_ready')},
        'limitations': ['State freshness is computed only at recorded state_update stamps.',
            'A published initial_inputs_ready event does not prove the worker received it.',
            'Absent events do not reconstruct unrecorded callback booleans/discovery history.',
            'No map/driver/motion/information payloads or private truth are consumed.',
            'Original native_stop identity regex is reported, not repaired or overridden.'],
        'diagnostic_only': True, 'old_failures_preserved': True,
        'scientific_qualification_claimed': False, 'fees_recomputed': False}
    raw = (json.dumps(result, indent=2, allow_nan=False) + '\n').encode()
    require(len(raw) <= 4 * MIB, 'finite output bound exceeded')
    with args.output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'output': str(args.output), 'bytes': len(raw), 'inputs': len(inputs),
                      'diagnostic_only': True}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
