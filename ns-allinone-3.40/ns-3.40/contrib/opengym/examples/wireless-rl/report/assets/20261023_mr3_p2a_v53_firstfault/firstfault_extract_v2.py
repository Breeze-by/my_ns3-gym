"""Disabled, fixed two-input V52 FIRSTFAULT description; no scientific replay.

The eventual execution requires an admitted exact spec and a new Git source
seal. This module imports no repository implementation, ROS, math or model.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
P = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration'
EP = ROOT / ('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v52/'
             'mr3_p2a_reach_v52_deadline/worker0/episode001_open_101')
INVENTORY = ROOT / W / 'report/assets/20261023_mr3_p2a_v52_qualification/closed_inventory_v1.json'
EPOCH = 'mr3_p2a_reach_v52_deadline_w0_e1_426a2555'
OLD_FREEZE = '1fa55bc56d5bb9e230d4b397f962d83b1604b278'
SCHEMA = 'mr3-v53-firstfault-spec-v1'
RESULT_SCHEMA = 'mr3-v53-firstfault-description-v1'
PROTOCOL = 'received-input-pause-drain-v1'
FILES = {'motion': ('motion_safety.jsonl', 2458997272),
         'startup': ('startup_readiness.jsonl', 286052)}
SOURCE_PATHS = (P + '/motion_safety.py', P + '/mr3_motion_control.py',
                P + '/mr3_reach_runtime.py',
                'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py',
                'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/'
                'gazebo_multirobot_mapping_with_nav2.launch.py',
                W + '/mr3_learning/benchmark.py', W + '/mr3_learning/supervisor.py')
LIMITS = {'total_input_bytes': 3 * 1024**3, 'line_bytes': 8 * 1024**2,
          'lines_per_file': 1000000, 'selected_records': 256,
          'output_bytes': 2 * 1024**2, 'work_seconds': 240}
ROBOTS = ('tb1', 'tb2', 'tb3')
FAULTS = ('reach_model_failure', 'normal_control_model_invalid',
          'invalid_reach_driver_ingress', 'invalid_received_states',
          'control_failure', 'control_ack')
WINDOW_KINDS = ('own_odom', 'reach_driver_ingress', 'reach_intent_publish',
                'control_request', 'control_failure', 'control_ack',
                'control_ack_published')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        value = dict(items)
        require(len(value) == len(items), 'duplicate JSON key')
        return value
    def constant(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    canonical(value)  # Includes overflowed ordinary numbers such as 1e999.
    return value


def text(value):
    return type(value) is str and bool(value)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def freeze(value):
    return type(value) is str and len(value) == 40 and all(c in '0123456789abcdef' for c in value)


def validate_spec(spec):
    require(type(spec) is dict and spec.get('schema') == SCHEMA, 'wrong spec schema')
    require(spec.get('admitted') is True, 'pending spec cannot read raw inputs')
    require(spec.get('epoch') == EPOCH and spec.get('evidence_freeze') == OLD_FREEZE,
            'wrong fixed episode/evidence freeze')
    require(spec.get('failure_clock_ns') == 244580000000
            and spec.get('sim_window') == ['244.48', '244.62'], 'fixed failure/window differs')
    require(spec.get('limits') == LIMITS, 'fixed limits differ')
    require(spec.get('execution_freeze_binding') == 'required-exact-cli',
            'new execution freeze must come from exact required CLI, not evidence freeze')
    require(type(spec.get('inputs')) is dict and set(spec['inputs']) == set(FILES), 'exact two inputs required')
    for label, (name, size) in FILES.items():
        item = spec['inputs'][label]
        require(type(item) is dict and item.get('path') == str(EP / name)
                and type(item.get('bytes')) is int and item['bytes'] == size
                and digest(item.get('sha256')), 'unbound/wrong fixed input: ' + label)
        inventory = item.get('inventory_ref')
        require(type(inventory) is dict and inventory.get('path') == str(INVENTORY)
                and digest(inventory.get('sha256')) and integer(inventory.get('bytes'), 1)
                and inventory['bytes'] <= 16 * 1024**2, 'canonical inventory reference required')
    require(sum(item['bytes'] for item in spec['inputs'].values()) <= LIMITS['total_input_bytes'],
            'total input limit exceeded')
    pins = spec.get('interpretation_sources')
    require(type(pins) is dict and set(pins) == set(SOURCE_PATHS), 'exact interpretation sources required')
    require(all(type(v) is dict and digest(v.get('sha256')) and integer(v.get('bytes'), 1)
                for v in pins.values()), 'pending interpretation source pin')
    consumer = spec.get('consumer')
    require(type(consumer) is dict and text(consumer.get('path'))
            and digest(consumer.get('sha256')) and integer(consumer.get('bytes'), 1), 'pending consumer pin')
    return spec


def validate_row(row, label):
    require(type(row) is dict and row.get('epoch') == EPOCH, 'record epoch/object differs')
    require(text(row.get('kind')) and len(row['kind']) <= 128
            and integer(row.get('wall_monotonic_ns')), 'invalid record kind/wall')
    if label == 'motion':
        require(row.get('schema') == 'mr3-motion-safety-v1'
                and integer(row.get('record_sequence'), 1), 'invalid motion schema/sequence')
        require(finite(row.get('sim_time_sec')) and row['sim_time_sec'] >= 0,
                'nonfinite/invalid motion sim timestamp')
        require(type(row.get('payload')) is dict, 'motion payload must be an object')
    else:
        require(row.get('schema') == 'mr3-startup-readiness-v1'
                and row.get('protocol') == PROTOCOL, 'invalid startup schema/protocol')
        require(integer(row.get('clock_ns')) and (row.get('physical_ns') is None
                or integer(row['physical_ns'])) and text(row.get('stage')), 'invalid startup clock/stage')
        ready = row.get('ready')
        require(type(ready) is dict and set(ready) == {
            'monitor_ready', 'initial_inputs_ready', 'motion_ready', 'odometry_recorder_ready'}
            and all(type(v) is bool for v in ready.values()), 'invalid actual ready fields')
        require(type(row.get('callback_fields_received')) is list
                and all(text(v) for v in row['callback_fields_received']), 'invalid callback fields')


def validate_ack(value):
    require(type(value) is dict and value.get('schema') == 'mr3-motion-control-ack-v2'
            and value.get('epoch') == EPOCH and text(value.get('request_id'))
            and integer(value.get('target_time_ns')) and integer(value.get('clock_ns'))
            and value.get('operation') in ('commit', 'takeover', 'stop')
            and type(value.get('ok')) is bool and value.get('safety_contract') == 'mr3-reach-v1',
            'invalid selected motion ACK')
    if not value['ok']:
        require(text(value.get('error')), 'negative ACK missing error')


def validate_selected(row, label):
    if label == 'startup':
        receipt = row.get('receipt')
        require(type(receipt) is dict and receipt.get('topic') == '/exploration_failure'
                and type(receipt.get('data')) is str
                and type(row.get('epoch_bound_to_current_startup')) is bool,
                'invalid actual failure callback receipt')
        # String.data can legitimately be non-JSON. Never infer its epoch.
        return
    p, kind = row['payload'], row['kind']
    if kind in ('reach_model_failure', 'normal_control_model_invalid'):
        require(p.get('schema') == 'mr3-reach-runtime-fault-v1'
                and p.get('robot') in (*ROBOTS, 'joint') and text(p.get('reason')),
                'fault missing exact robot/reason/schema')
        key = 'clock_ns' if kind == 'reach_model_failure' else 'commit_clock_ns'
        require(integer(p.get(key)), 'fault missing actual source clock')
    elif kind == 'invalid_reach_driver_ingress':
        require(p.get('robot') in ROBOTS and p.get('kind') in ('calibration', 'applied', 'storage')
                and text(p.get('reason')) and type(p.get('raw_json')) is str, 'invalid ingress fault fields')
    elif kind in ('invalid_received_states', 'control_failure'):
        require(text(p.get('reason') if kind == 'invalid_received_states' else p.get('error')),
                'fault missing reason/error')
    elif kind == 'control_ack':
        validate_ack(p)
    elif kind == 'control_ack_published':
        validate_ack(p.get('ack'))
        require(integer(p.get('publish_started_wall_monotonic_ns'))
                and integer(p.get('publish_completed_wall_monotonic_ns')), 'invalid ACK publication fields')
    elif kind == 'control_request':
        require(p.get('schema') == 'mr3-motion-control-request-v2' and p.get('epoch') == EPOCH
                and text(p.get('request_id')) and integer(p.get('target_time_ns'))
                and p.get('operation') in ('commit', 'takeover', 'stop'), 'invalid selected control request')
    elif kind == 'own_odom':
        require(p.get('robot') in ROBOTS and integer(p.get('input_sequence'), 1)
                and type(p.get('message')) is dict, 'invalid selected actual own odometry')
        stamp = p['message'].get('header', {}).get('stamp', {})
        require(integer(stamp.get('sec')) and integer(stamp.get('nanosec'))
                and stamp['nanosec'] < 1000000000, 'invalid selected odometry source time')
    elif kind == 'reach_driver_ingress':
        require(p.get('robot') in ROBOTS and p.get('kind') in ('calibration', 'applied', 'storage')
                and type(p.get('message')) is dict and type(p.get('raw_json')) is str
                and type(p.get('publisher_identity')) is dict, 'invalid selected driver ingress')
    elif kind == 'reach_intent_publish':
        require(p.get('robot') in ROBOTS and type(p.get('intent')) is dict, 'invalid selected intent')


class Selection:
    def __init__(self):
        self.first_faults, self.window, self.first_callback = {}, {}, None
        self.kind_counts, self.relevant_counts, self.window_counts = Counter(), Counter(), Counter()

    def accept(self, row, label, line, raw):
        count_key = (label, row['kind'])
        require(count_key in self.kind_counts or len(self.kind_counts) < 128, 'too many distinct record kinds')
        self.kind_counts[count_key] += 1
        kind = row['kind']
        relevant = label == 'motion' and kind in FAULTS and (
            kind != 'control_ack' or row['payload'].get('ok') is False)
        callback = label == 'startup' and kind == 'exploration_failure_received'
        window = (label == 'motion' and kind in WINDOW_KINDS
                  and Decimal('244.48') <= Decimal(str(row['sim_time_sec'])) <= Decimal('244.62'))
        if not (relevant or callback or window):
            return
        validate_selected(row, label)
        item = {'input': label, 'line_1based': line, 'raw_line_sha256': hashlib.sha256(raw).hexdigest(),
                'raw_line_bytes': len(raw), 'record': row}
        if relevant:
            self.relevant_counts[kind] += 1
            self.first_faults.setdefault(kind, item)  # Physical file order, never wall-sorted.
        if callback and self.first_callback is None:
            self.first_callback = item
        if window:
            p = row['payload']
            robot = p['robot'] if kind in ('own_odom', 'reach_driver_ingress', 'reach_intent_publish') else 'joint'
            key = (kind, robot, p['kind'] if kind == 'reach_driver_ingress' else '')
            self.window_counts[key] += 1
            slot = self.window.setdefault(key, {'first': item, 'last': item})
            slot['last'] = item

    def finish(self, parse_complete, limits):
        selected = {}
        for item in [*self.first_faults.values(), self.first_callback,
                     *(v[k] for v in self.window.values() for k in ('first', 'last'))]:
            if item is not None:
                selected.setdefault((item['input'], item['line_1based']), item)
        records, dropped = [], 0
        size = 0
        for item in selected.values():
            raw = canonical(item)
            if len(records) >= limits['selected_records'] or size + len(raw) > limits['output_bytes'] // 2:
                dropped += 1
            else:
                records.append(item)
                size += len(raw)
        first = next((item for item in self.first_faults.values()
                      if item['record']['kind'] in ('reach_model_failure', 'normal_control_model_invalid')), None)
        if first is not None:
            # Both entries were captured in scan order; select by original line.
            first = min((item for item in self.first_faults.values()
                         if item['record']['kind'] in ('reach_model_failure', 'normal_control_model_invalid')),
                        key=lambda item: item['line_1based'])
        status = ('RECORDED' if first and parse_complete else
                  'RECORDED_BUT_FIRST_UNPROVEN_PARTIAL_PARSE' if first else
                  'NOT_RECORDED' if parse_complete else 'UNKNOWN_PARTIAL_PARSE')
        return {'first_runtime_fault_status': status, 'first_runtime_fault': first,
                'first_failure_callback_status': ('RECORDED' if self.first_callback else
                    'NOT_RECORDED' if parse_complete else 'UNKNOWN_PARTIAL_PARSE'),
                'first_failure_callback': self.first_callback,
                'first_fault_refs': {k: {'input': v['input'], 'line_1based': v['line_1based']}
                                     for k, v in self.first_faults.items()},
                'kind_counts': {label + '/' + kind: n for (label, kind), n in self.kind_counts.items()},
                'relevant_counts': dict(self.relevant_counts),
                'window_bucket_counts': {'/'.join(k): n for k, n in self.window_counts.items()},
                'selection_rule': 'first per relevant kind; fixed-window first+last per kind/robot/feed; no wall-time sort',
                'selected_records': records, 'selected_count': len(records),
                'selection_dropped': dropped, 'selection_complete_for_declared_rule': dropped == 0}


def scan(stream, label, expected, selection, deadline, limits=LIMITS):
    h, count, total, errors, error_count = hashlib.sha256(), 0, 0, [], 0
    complete = False
    previous = 0
    def error(message):
        nonlocal error_count
        error_count += 1
        if len(errors) < 24:
            errors.append(message)
    while True:
        if time.monotonic() >= deadline:
            error('work deadline expired; unread suffix preserved')
            break
        raw = stream.readline(limits['line_bytes'] + 1)
        if not raw:
            complete = True
            break
        total += len(raw)
        h.update(raw)
        count += 1
        if total > expected['bytes'] or count > limits['lines_per_file']:
            error('byte or line limit exceeded; unread suffix preserved')
            break
        if len(raw) > limits['line_bytes']:
            error('oversized JSON line; unread suffix preserved')
            break
        try:
            row = decode(raw)
            validate_row(row, label)
            if label == 'motion':
                require(row['record_sequence'] == previous + 1, 'record_sequence gap/regression')
                previous = row['record_sequence']
            selection.accept(row, label, count, raw)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
            error('line ' + str(count) + ': ' + str(exc))
            # Still parse the remaining records and hash every byte. A bad row
            # always rejects completeness/PASS; it can never become NOT_RECORDED.
    actual_sha = h.hexdigest()
    if complete and (total != expected['bytes'] or actual_sha != expected['sha256']):
        error('whole-input SHA/bytes differ from fixed inventory')
    return {'input': label, 'bytes_read': total, 'lines_read': count, 'sha256_of_read_bytes': actual_sha,
            'whole_input_read': complete, 'whole_input_sha256': actual_sha if complete else None,
            'parse_and_binding_complete': complete and error_count == 0,
            'error_count': error_count, 'errors': errors, 'omitted_errors': max(0, error_count - len(errors))}


def stat_fields(st):
    return {k: getattr(st, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def identity():
    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': os.getpid(), 'parent': os.getppid(), 'group': os.getpgrp(),
            'session': os.getsid(0), 'start_ticks': int(fields[19])}


def provenance(spec, execution_freeze):
    require(freeze(execution_freeze), 'exact new execution freeze required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=10).strip()
    require(head == execution_freeze, 'actual execution HEAD differs')
    result = {'execution_freeze': head, 'evidence_freeze': OLD_FREEZE, 'interpretation_sources': {}}
    refs = {canonical(item['inventory_ref']) for item in spec['inputs'].values()}
    require(len(refs) == 1, 'the two inputs must use one canonical closed inventory')
    ref = next(iter(spec['inputs'].values()))['inventory_ref']
    inv_stat = INVENTORY.lstat()
    require(stat.S_ISREG(inv_stat.st_mode) and inv_stat.st_size == ref['bytes'], 'closed inventory stat differs')
    inventory_raw = INVENTORY.read_bytes()
    require(INVENTORY.lstat() == inv_stat and hashlib.sha256(inventory_raw).hexdigest() == ref['sha256'],
            'closed inventory SHA/stat differs')
    inventory = decode(inventory_raw)
    require(type(inventory) is dict and inventory.get('byte_archive_complete') is True
            and inventory.get('freeze') == OLD_FREEZE
            and type(inventory.get('entries')) is list, 'closed inventory not complete')
    for item in spec['inputs'].values():
        matches = [row for row in inventory['entries'] if type(row) is dict and row.get('original') == item['path']]
        require(len(matches) == 1 and matches[0].get('original_bytes') == item['bytes']
                and matches[0].get('original_sha256') == item['sha256']
                and matches[0].get('source_stat_stable') is True
                and matches[0].get('decoded_bytes_verified') is True,
                'input is not exactly bound to canonical original bytes')
    result['closed_inventory'] = dict(ref)
    for relative, pin in spec['interpretation_sources'].items():
        current = (ROOT / relative).read_bytes()
        frozen = subprocess.check_output(['git', 'show', OLD_FREEZE + ':' + relative], cwd=ROOT, timeout=10)
        require(current == frozen and len(current) == pin['bytes']
                and hashlib.sha256(current).hexdigest() == pin['sha256'], 'interpretation source differs: ' + relative)
        result['interpretation_sources'][relative] = dict(pin)
    consumer = Path(__file__).resolve()
    require(str(consumer) == spec['consumer']['path'], 'consumer path differs')
    raw = consumer.read_bytes()
    require(len(raw) == spec['consumer']['bytes'] and hashlib.sha256(raw).hexdigest()
            == spec['consumer']['sha256'], 'consumer SHA differs')
    relative = str(consumer.relative_to(ROOT))
    require(subprocess.check_output(['git', 'show', head + ':' + relative], cwd=ROOT, timeout=10) == raw,
            'new consumer differs from its own execution freeze')
    result['consumer'] = dict(spec['consumer'])
    return result



def encode_result(result, limit=LIMITS['output_bytes']):
    """A failed description must itself still obey the hard output byte cap."""
    raw = canonical(result)
    if len(raw) + 1 <= limit:
        return raw
    minimal = {'schema': RESULT_SCHEMA, 'passed': False,
        'errors': ['output_byte_limit_exceeded; detailed description omitted'],
        'output_truncated': True, 'identity': result.get('identity'),
        'started_monotonic_ns': result.get('started_monotonic_ns'),
        'ended_monotonic_ns': result.get('ended_monotonic_ns'),
        'scientific_qualification': False,
        'first_runtime_fault_status': 'OMITTED_OUTPUT_LIMIT',
        'first_failure_callback_status': 'OMITTED_OUTPUT_LIMIT'}
    result.clear()
    result.update(minimal)
    raw = canonical(result)
    require(len(raw) + 1 <= limit, 'fixed failure receipt exceeds output byte cap')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args(argv)
    started = time.monotonic_ns()
    deadline = time.monotonic() + LIMITS['work_seconds']
    result = {'schema': RESULT_SCHEMA, 'passed': False, 'errors': [], 'input_reports': [],
              'identity': identity(), 'actual_argv': [sys.executable, *sys.argv],
              'started_monotonic_ns': started, 'scientific_qualification': False,
              'scope': 'fixed closed FIRSTFAULT description only; no mathematical replay or new qualification'}
    with args.output.open('x') as out:
        try:
            spec_bytes = args.spec.read_bytes()
            spec = validate_spec(decode(spec_bytes))
            result['spec'] = {'path': str(args.spec.resolve()), 'sha256': hashlib.sha256(spec_bytes).hexdigest()}
            before = provenance(spec, args.freeze)
            result['source_before'] = before
            snapshots = {}
            selection = Selection()
            for label in FILES:
                item = spec['inputs'][label]
                path = Path(item['path'])
                original = path.lstat()
                require(stat.S_ISREG(original.st_mode) and not path.is_symlink()
                        and original.st_size == item['bytes'], 'input not exact regular file: ' + label)
                snapshots[label] = stat_fields(original)
                with path.open('rb') as stream:
                    require(stat_fields(os.fstat(stream.fileno())) == snapshots[label], 'input opened different inode')
                    report = scan(stream, label, item, selection, deadline)
                report['path'] = str(path)
                report['stat_before'] = snapshots[label]
                report['stat_after'] = stat_fields(path.lstat())
                if report['stat_after'] != snapshots[label]:
                    report['errors'].append('input stat changed while reading')
                    report['error_count'] += 1
                    report['parse_and_binding_complete'] = False
                result['input_reports'].append(report)
            complete = (len(result['input_reports']) == 2 and
                        all(row['parse_and_binding_complete'] for row in result['input_reports']))
            result.update(selection.finish(complete, LIMITS))
            result['source_after'] = provenance(spec, args.freeze)
            require(result['source_after'] == before, 'interpretation or consumer source changed')
            for label, item in spec['inputs'].items():
                require(stat_fields(Path(item['path']).lstat()) == snapshots[label], 'input stat changed after scan')
            result['passed'] = complete and result['selection_complete_for_declared_rule']
        except BaseException as error:
            result['errors'].append(type(error).__name__ + ': ' + str(error))
            result['passed'] = False
        result['ended_monotonic_ns'] = time.monotonic_ns()
        result['within_work_limit'] = time.monotonic() <= deadline
        result['passed'] = result['passed'] and result['within_work_limit'] and not result['errors']
        raw = encode_result(result)
        out.write(raw.decode() + '\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
