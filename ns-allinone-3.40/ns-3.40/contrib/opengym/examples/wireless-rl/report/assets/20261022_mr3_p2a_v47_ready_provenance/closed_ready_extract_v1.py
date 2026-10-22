"""Disabled finite two-stream V45 startup diagnosis; no replay or new World.

Real consumption requires root to copy/freeze this source and declare a scope.
--self-check uses artificial BytesIO rows only; no original is opened by it.
"""
import argparse
from collections import Counter, deque
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from types import ModuleType

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
BASE_PATH = W / 'report/assets/20261022_mr3_p2a_v46_startup_diagnosis/closed_startup_extract_v1.py'
BASE_SHA256 = '5dd2334e926d0ce87a0e7d4d3bfe8e48c758e680db61c1e1bcf812eaacbabe02'
EPOCH = 'mr3_p2a_reach_v45_reset_w1_e3_df93697f'
NATIVE_FREEZE = 'cace46e08e53b7e89a434e23721db85ac993f6f5'
RUN = ROOT / ('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v45/'
              'mr3_p2a_reach_v45_reset/worker1/episode003_rooms_101')
INVENTORY = W / 'report/assets/20261022_mr3_p2a_v45_preparation_classification/closed_inventory_v1.json'
INVENTORY_SHA256 = 'dc1522d6214840488b4f1130eff448b61d3175454922a7a0e4ae0f743218f2a0'
FILES = {'driver_odometry_receipts.jsonl': 'driver', 'motion_safety.jsonl': 'motion'}
EXPECTED_BYTES = {'driver_odometry_receipts.jsonl': 71649012, 'motion_safety.jsonl': 312731331}
MIB = 1024 * 1024
MAX_INPUT = 512 * MIB
MAX_LINE = 4 * MIB
MAX_OUTPUT = 2 * MIB
MAX_SELECTED = 200
MAX_KEYS = 256
ROBOTS = ('tb1', 'tb2', 'tb3')


def base_helpers():
    raw = BASE_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA256:
        raise ValueError('fixed V46 helper source differs')
    module = ModuleType('_mr3_v47_fixed_v46_helpers')
    module.__file__ = str(BASE_PATH)
    exec(compile(raw, str(BASE_PATH), 'exec'), module.__dict__)
    return module


def compact(value, present=True):
    """Bound descriptive strings; never include message/raw_json objects."""
    if not present:
        return {'status': 'NOT_RECORDED'}
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    result = {'sha256': hashlib.sha256(raw).hexdigest(), 'json_bytes': len(raw),
              'type': type(value).__name__}
    if value is None or type(value) in (bool, int, float):
        result['value'] = value
    elif type(value) is str:
        result.update(text=value[:512], text_truncated=len(value) > 512)
    return result


def add(counter, key):
    if key not in counter and len(counter) >= MAX_KEYS:
        raise ValueError('finite distinct diagnostic counter bound exceeded')
    counter[key] += 1


def first_last(table, key, item):
    if key not in table:
        if len(table) >= MAX_KEYS:
            raise ValueError('finite first/last example bound exceeded')
        table[key] = {'first': item, 'last': item, 'count': 1}
    else:
        table[key]['last'] = item
        table[key]['count'] += 1


class Selection:
    def __init__(self):
        self.rows, self.omitted, self.candidates = [], 0, 0

    def append(self, row):
        self.candidates += 1
        if len(self.rows) < MAX_SELECTED:
            self.rows.append(row)
        else:
            self.omitted += 1


def envelope(row, kind, b):
    b.require(type(row) is dict, 'JSONL row is not an object')
    expected = 'mr3-driver-odometry-receipt-v1' if kind == 'driver' else 'mr3-motion-safety-v1'
    b.require(row.get('schema') == expected, 'record schema differs')
    b.require(row.get('epoch') == EPOCH, 'record epoch differs')
    b.require(type(row.get('kind')) is str and 0 < len(row['kind']) <= 128, 'invalid event kind')
    b.require(type(row.get('record_sequence')) is int and row['record_sequence'] > 0,
              'missing typed positive record_sequence')


def row_summary(row, kind, reference):
    out = {**reference, 'kind': row['kind'], 'record_sequence': row['record_sequence']}
    for field in ('clock_ns', 'wall_monotonic_ns', 'sim_time_sec'):
        if field in row and type(row[field]) in (int, float):
            out[field] = row[field]
    if kind == 'driver':
        for field in ('robot', 'driver_identity_match', 'driver_gid_stable'):
            if field in row:
                value = row[field]
                if field == 'robot':
                    out[field] = value if type(value) is str and len(value) <= 32 else 'NOT_RECORDED_OR_INVALID_ROBOT'
                else:
                    out[field] = value if type(value) is bool else 'NOT_RECORDED_OR_NONBOOL'
        if row['kind'] == 'ready':
            # Report the recorder's emitted ready event, not worker delivery.
            out['ready_publication_recorded'] = True
    else:
        payload = row.get('payload')
        if type(payload) is dict:
            for field in ('robot', 'clock_ns', 'ready', 'started', 'decision_sequence', 'phase_kind'):
                if field in payload and (payload[field] is None or type(payload[field]) in (str, bool, int, float)):
                    value = payload[field]
                    out[field] = value if type(value) is not str or len(value) <= 128 else compact(value)
            if 'raw_json' in payload:
                raw = payload['raw_json']
                encoded = raw.encode() if type(raw) is str else json.dumps(raw, sort_keys=True).encode()
                out['raw_json_sha256'] = hashlib.sha256(encoded).hexdigest()
                out['raw_json_bytes'] = len(encoded)
            if 'reason' in payload:
                out['reason'] = compact(payload['reason'])
            if 'data' in payload and row['kind'] == 'failure':
                out['failure_data'] = compact(payload['data'])
            if row['kind'] == 'reach_decision':
                decision, tracker = payload.get('decision'), payload.get('tracker')
                if type(decision) is dict:
                    out['allow'] = decision.get('allow') if type(decision.get('allow')) is bool else 'NOT_RECORDED_OR_NONBOOL'
                    out['reason'] = compact(decision.get('reason'), 'reason' in decision)
                if type(tracker) is dict:
                    out['tracker_fault'] = compact(tracker.get('fault'), 'fault' in tracker)
                    out['tracker_permanent_stop'] = tracker.get('permanent_stop') if type(tracker.get('permanent_stop')) is bool else 'NOT_RECORDED_OR_NONBOOL'
    return out


def scan(stream, kind, byte_limit, picker, b):
    digest, count, lines, valid = hashlib.sha256(), 0, 0, 0
    event_counts, errors, error_count = Counter(), [], 0
    tail = deque(maxlen=20)
    ready_events, ready_first, ready_last = 0, None, None
    packet_flags, invalid_packets, invalid_examples = Counter(), Counter(), {}
    ready_state, ready_flips, decision_counts, reason_counts = {}, Counter(), Counter(), Counter()
    fault_counts, reason_details, decision_examples = Counter(), {}, {}
    failure_reasons, failure_examples, failure_details = Counter(), {}, {}
    previous_sequence, regressions = None, 0
    for raw in iter(lambda: stream.readline(MAX_LINE + 1), b''):
        count += len(raw); lines += 1; digest.update(raw)
        b.require(count <= byte_limit and len(raw) <= MAX_LINE, 'finite byte/line bound exceeded')
        ref = {'stream': kind, 'line_1based': lines, 'line_sha256': hashlib.sha256(raw).hexdigest()}
        try:
            b.require(raw.endswith(b'\n'), 'partial final JSONL line')
            row = b.decode(raw)
            envelope(row, kind, b)
            item = row_summary(row, kind, ref)
            valid += 1
            add(event_counts, row['kind'])
            if previous_sequence is not None and row['record_sequence'] <= previous_sequence:
                regressions += 1
            previous_sequence = row['record_sequence']
            tail.append(item)
            if kind == 'driver':
                if row['kind'] == 'ready':
                    ready_events += 1
                    ready_first = item if ready_first is None else ready_first
                    ready_last = item
                    picker.append({**item, 'selection_reason': 'recorder_ready_event'})
                elif row['kind'] in ('odom', 'tf'):
                    b.require(row.get('robot') in ROBOTS, 'driver packet robot differs')
                    phase = 'after_first_ready_event' if ready_events else 'before_first_ready_event'
                    invalid = False
                    for field in ('driver_identity_match', 'driver_gid_stable'):
                        value = row.get(field, 'NOT_RECORDED')
                        label = str(value) if type(value) is bool else 'NOT_RECORDED_OR_NONBOOL'
                        key = '|'.join((phase, row['kind'], row['robot'], field, label))
                        add(packet_flags, key)
                        if value is False:
                            invalid = True
                            first_last(invalid_examples, '|'.join((phase, row['kind'], row['robot'], field)), item)
                    if invalid:
                        add(invalid_packets, phase)
                        picker.append({**item, 'ready_phase': phase, 'selection_reason': 'driver_identity_or_gid_false'})
            else:
                payload = row.get('payload')
                b.require(type(payload) is dict, 'motion payload is not an object')
                if row['kind'] == 'reach_decision':
                    robot = payload.get('robot')
                    b.require(robot in ROBOTS, 'reach decision robot differs')
                    ready, started = payload.get('ready', 'NOT_RECORDED'), payload.get('started', 'NOT_RECORDED')
                    decision, tracker = payload.get('decision'), payload.get('tracker')
                    b.require(type(decision) is dict and type(tracker) is dict, 'reach decision/tracker not objects')
                    allow = decision.get('allow', 'NOT_RECORDED')
                    for field, value in (('ready', ready), ('started', started), ('allow', allow)):
                        b.require(type(value) is bool or value == 'NOT_RECORDED', 'recorded boolean has wrong type: ' + field)
                    add(decision_counts, '|'.join((robot, 'ready='+str(ready), 'started='+str(started), 'allow='+str(allow))))
                    reason = compact(decision.get('reason'), 'reason' in decision)
                    reason_key = reason.get('sha256', 'NOT_RECORDED')
                    add(reason_counts, robot+'|'+reason_key)
                    b.require(reason_key in reason_details or len(reason_details) < MAX_KEYS, 'reason detail bound exceeded')
                    reason_details[reason_key] = reason
                    fault = compact(tracker.get('fault'), 'fault' in tracker)
                    add(fault_counts, robot+'|'+fault.get('sha256', 'NOT_RECORDED'))
                    first_last(decision_examples, robot+'|'+reason_key+'|'+fault.get('sha256', 'NOT_RECORDED'), item)
                    initial = robot not in ready_state
                    previous = ready_state.get(robot)
                    ready_state[robot] = ready
                    if initial or ready != previous:
                        if not initial:
                            add(ready_flips, robot+'|'+str(previous)+'->'+str(ready))
                        picker.append({**item, 'previous_recorded_ready': 'NOT_RECORDED' if initial else previous,
                            'selection_reason': 'first_motion_ready_record' if initial else 'motion_ready_changed'})
                if row['kind'].startswith('invalid_') or row['kind'] in ('reach_model_failure', 'failure'):
                    reason = compact(payload.get('reason', payload.get('data')),
                                     'reason' in payload or 'data' in payload)
                    key = row['kind']+'|'+reason.get('sha256', 'NOT_RECORDED')
                    add(failure_reasons, key)
                    b.require(key in failure_details or len(failure_details) < MAX_KEYS, 'failure detail bound exceeded')
                    failure_details[key] = reason
                    first_last(failure_examples, key, item)
                    picker.append({**item, 'selection_reason': 'invalid_or_reach_fault_event'})
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
            # Finite-bound failures remain a failed extraction, never truncated success.
            if 'bound exceeded' in str(error):
                raise
            error_count += 1
            if len(errors) < 20:
                errors.append({**ref, 'error': str(error)[:512]})
    result = {'bytes': count, 'sha256': digest.hexdigest(), 'lines': lines,
        'valid_epoch_schema_rows': valid, 'event_counts': dict(event_counts),
        'parse_or_schema_error_count': error_count, 'parse_or_schema_errors': errors,
        'parse_or_schema_errors_omitted': error_count-len(errors),
        'all_rows_valid': error_count == 0, 'absence_inference_from_event_counts_allowed': error_count == 0,
        'record_sequence_nonincreasing_count': regressions, 'tail': list(tail),
        'count_scope': 'Complete hashed input lines; event counts describe accepted epoch/schema rows only.'}
    if kind == 'driver':
        result.update(ready_event_count=ready_events, first_ready_event=ready_first, last_ready_event=ready_last,
            packet_flag_counts=dict(packet_flags), invalid_packet_counts_by_ready_phase=dict(invalid_packets),
            invalid_flag_first_last=invalid_examples,
            worker_received_recorder_ready='NOT_RECORDED',
            actual_ready_bool_publication_history='Only explicit ready event; later false Bool publication is not separately logged.')
    else:
        result.update(decision_boolean_counts=dict(decision_counts), ready_transitions_by_robot=dict(ready_flips),
            last_recorded_ready_by_robot=ready_state, decision_reason_counts=dict(reason_counts),
            reason_descriptions=reason_details, tracker_fault_counts=dict(fault_counts),
            decision_reason_fault_first_last=decision_examples, invalid_and_failure_reason_counts=dict(failure_reasons),
            invalid_and_failure_reason_descriptions=failure_details, invalid_and_failure_first_last=failure_examples,
            worker_received_motion_ready='NOT_RECORDED')
    return result


def consume(path, kind, limit, picker, b):
    before = path.lstat()
    b.require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'unsupported/oversize original')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        b.require(b.stamp(os.fstat(stream.fileno())) == b.stamp(before), 'original changed before open')
        result = scan(stream, kind, limit, picker, b)
        b.require(b.stamp(os.fstat(stream.fileno())) == b.stamp(before), 'original changed while open')
    after = path.lstat()
    b.require(b.stamp(before) == b.stamp(after) and result['bytes'] == before.st_size, 'original changed during read')
    return result, {'path': str(path), 'bytes': result['bytes'], 'sha256': result['sha256'],
                    'stat_before': b.stamp(before), 'stat_after': b.stamp(after)}


def source_bindings(freeze, b):
    b.require(type(freeze) is str and len(freeze) == 40 and all(c in '0123456789abcdef' for c in freeze), 'exact source freeze required')
    paths = [BASE_PATH, Path(__file__).resolve(), INVENTORY,
        ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_odometry_recorder.cpp',
        ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py',
        ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_runtime.py']
    rows = []
    for path in paths:
        before = path.lstat(); raw = path.read_bytes()
        b.require(b.stamp(path.lstat()) == b.stamp(before), 'interpretation source changed during read')
        relative = str(path.relative_to(ROOT))
        frozen = subprocess.run(['git','show',freeze+':'+relative],cwd=ROOT,check=True,capture_output=True,timeout=10).stdout
        b.require(frozen == raw, 'current source differs from exact freeze: '+relative)
        rows.append({'path':relative,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                     'stat':b.stamp(before),'git_freeze':freeze})
    return rows


def self_check(b):
    def raw(kind, payload=None, *, stream='driver', epoch=EPOCH, **fields):
        row={'schema':'mr3-driver-odometry-receipt-v1' if stream=='driver' else 'mr3-motion-safety-v1',
             'epoch':epoch,'kind':kind,'record_sequence':1,**fields}
        if stream=='motion':row['payload']=payload or {}
        return json.dumps(row).encode()+b'\n'
    def read(data, kind='driver', limit=MIB):return scan(io.BytesIO(data),kind,limit,Selection(),b)
    packet=raw('odom',robot='tb1',driver_identity_match=True,driver_gid_stable=True,message={'secret':'DO_NOT_OUTPUT'})
    a=read(packet);assert a['ready_event_count']==0 and 'DO_NOT_OUTPUT' not in json.dumps(a)
    a=read(raw('ready',robot=''));assert a['ready_event_count']==1
    a=read(raw('odom',robot='tb1',driver_identity_match=False,driver_gid_stable=True));assert a['invalid_packet_counts_by_ready_phase']['before_first_ready_event']==1
    a=read(raw('ready',robot='')+raw('odom',robot='tb1',driver_identity_match=False,driver_gid_stable=True));assert a['invalid_packet_counts_by_ready_phase']['after_first_ready_event']==1
    a=read(raw('ready',robot='')+raw('tf',robot='tb2',driver_identity_match=True,driver_gid_stable=False));assert a['invalid_flag_first_last']['after_first_ready_event|tf|tb2|driver_gid_stable']['count']==1
    def decision(ready):return raw('reach_decision',{'robot':'tb1','clock_ns':1,'ready':ready,'started':False,'decision':{'reason':'before_release','allow':False},'tracker':{'fault':None}},stream='motion')
    a=read(decision(False)+decision(True),'motion');assert a['ready_transitions_by_robot']['tb1|False->True']==1
    a=read(raw('invalid_reach_driver_ingress',{'robot':'tb1','reason':'bad source','raw_json':'SECRET','message':{'secret':'DO_NOT_OUTPUT'}},stream='motion'),'motion');encoded=json.dumps(a);assert 'SECRET' not in encoded and 'DO_NOT_OUTPUT' not in encoded and 'raw_json_sha256' in encoded and len(a['invalid_and_failure_reason_counts'])==1
    a=read(raw('ready',epoch='wrong')+b'{"schema":"wrong"}\n');assert a['parse_or_schema_error_count']==2 and not a['absence_inference_from_event_counts_allowed']
    a=read(b'not-json\n'*25);assert a['parse_or_schema_error_count']==25 and len(a['parse_or_schema_errors'])==20 and a['parse_or_schema_errors_omitted']==5
    try:read(b'x'*9,limit=8)
    except ValueError:pass
    else:raise AssertionError('byte bound did not reject')
    return {'schema':'mr3-v47-two-stream-artificial-self-check-v1','passed':True,'checks':10,
            'originals_read':0,'Worlds':0,'scientific_qualification_credit':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check',action='store_true')
    parser.add_argument('--source-freeze')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    b=base_helpers()
    if args.self_check:
        b.require(args.output is None and args.source_freeze is None,'self-check is in-memory only')
        print(json.dumps(self_check(b)),flush=True);return 0
    b.require(args.output is not None and args.source_freeze is not None,'output and source-freeze required')
    b.require(not args.output.exists() and not args.output.is_symlink(),'exclusive output exists')
    b.require(not args.output.resolve().is_relative_to(RUN.resolve()),'output cannot be inside original episode')
    start=time.monotonic_ns();sources=source_bindings(args.source_freeze,b)
    inventory_raw=INVENTORY.read_bytes();b.require(hashlib.sha256(inventory_raw).hexdigest()==INVENTORY_SHA256,'fixed V45 inventory differs')
    originals={row['original']:row for row in b.decode(inventory_raw)['entries']}
    b.require(sum((RUN/name).lstat().st_size for name in FILES)<=MAX_INPUT,'aggregate original byte bound exceeded')
    picker=Selection();results={};inputs=[];consumed=0
    for name,kind in FILES.items():
        result,proof=consume(RUN/name,kind,MAX_INPUT-consumed,picker,b);consumed+=proof['bytes']
        original=originals[proof['path']]
        b.require(proof['bytes']==original['original_bytes']==EXPECTED_BYTES[name] and proof['sha256']==original['original_sha256'],'original SHA/bytes differ from fixed V45 inventory')
        inputs.append(proof);results[name]=result
    for row in inputs:b.require(b.stamp(Path(row['path']).lstat())==row['stat_before'],'original changed before result seal')
    b.require(source_bindings(args.source_freeze,b)==sources,'interpretation source changed before seal')
    result={'schema':'mr3-v47-two-stream-startup-forensic-v1','identity':b.identity(),
        'source_freeze':args.source_freeze,'native_freeze':NATIVE_FREEZE,'epoch':EPOCH,
        'source_bindings':sources,'inputs':inputs,'results':results,'original_bytes':consumed,
        'selection_candidates':picker.candidates,'selected':picker.rows,'selected_omitted':picker.omitted,
        'started_monotonic_ns':start,'ended_monotonic_ns':time.monotonic_ns(),
        'diagnostic_only':True,'old_failures_preserved':True,'scientific_qualification_claimed':False,
        'worker_ready_bools_at_timeout':'NOT_RECORDED','mathematical_replay_performed':False,
        'limitations':['Event/flag counts are recorded descriptions only, not a new scientific or eligibility verdict.',
            'Recorder ready event and later invalid packet flags do not prove worker ready callback state.',
            'Motion ready changes are per-robot reach_decision records, not received worker Bool messages.',
            'No raw message, raw_json, physical state, map, certificate or model is emitted or replayed.',
            'Malformed/wrong-epoch/schema rows are bounded errors; event absence is not established when any row is invalid.',
            'All counters reject excessive distinct keys; selection/tail/example omissions are explicit.']}
    encoded=(json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    b.require(len(encoded)<=MAX_OUTPUT,'finite output bound exceeded')
    with args.output.open('xb') as stream:stream.write(encoded)
    print(json.dumps({'output':str(args.output),'bytes':len(encoded),'inputs':2,'diagnostic_only':True}),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
