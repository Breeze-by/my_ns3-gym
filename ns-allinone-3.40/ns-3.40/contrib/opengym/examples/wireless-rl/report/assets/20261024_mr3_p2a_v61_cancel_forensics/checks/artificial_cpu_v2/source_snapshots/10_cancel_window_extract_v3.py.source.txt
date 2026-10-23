"""Prospective bounded CANCEL description; never a scientific re-audit.

Draft only: the pending spec cannot open raw inputs. A new clean source/spec/
resource freeze and complete V60 closure must precede any actual invocation.
Every declared encoded and decoded input is completely hashed, independently
of how few rows match the fixed windows. No model, native run, or World starts.
"""
import argparse
from collections import Counter, deque
from decimal import Decimal
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time


ROOT = Path('/home/zhuyulab/ns3-workspace')
EVIDENCE_FREEZE = '935b466bd076002afdfe161b55a508938de2a8b0'
EPOCH = 'mr3_p2a_reach_v60_reset_w1_e2_d678c4be'
ROBOT = 'tb2'
GOALS = (EPOCH + ':tb2:1', EPOCH + ':tb2:14')
PRIMARY = {'id': 'first_cancel_failed', 'start_ns': 42600000000, 'end_ns': 46100000000}
SECONDARY = {'id': 'second_cancel_control', 'start_ns': 54600000000, 'end_ns': 55600000000}
MANDATORY = {'adapter', 'motion', 'drive', 'odom', 'launch'}
LIMIT_KEYS = {'total_encoded_bytes', 'total_decoded_bytes', 'line_bytes',
              'lines_per_file', 'selected_records', 'selected_raw_bytes',
              'output_bytes', 'work_seconds'}
ADAPTER_KINDS = {'native_send', 'native_cancel', 'delivery', 'protocol', 'action',
                 'action_rejected', 'rpc_error', 'edge_goal_not_sent', 'safety_stop',
                 'task_terminal', 'task_terminal_received'}
MOTION_KINDS = {'configuration', 'raw_request', 'reach_decision', 'actual_cmd_vel', 'reach_driver_ingress',
                'own_odom', 'reach_intent_publish', 'output_completed', 'control_request',
                'control_commit', 'control_ack', 'control_ack_published', 'release',
                'reach_model_failure', 'normal_control_model_invalid'}
JOINT_MOTION_KINDS = {'configuration', 'output_completed', 'control_request', 'control_commit',
                      'control_ack', 'control_ack_published', 'release',
                      'reach_model_failure', 'normal_control_model_invalid'}
LAUNCH_LITERALS = ('Failed to cancel action server for', 'Failed to get result for',
                   'in node halt!', 'Received request for goal cancellation',
                   'Client requested to cancel the goal. Cancelling.', 'Aborting handle.')
DRIVE_KINDS = {'configuration', 'reset', 'initial_encoder_configuration', 'initial_encoder_receive',
               'command_received', 'actuation', 'status_publish', 'target_rejected'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate JSON member')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def object_value(value, label):
    require(type(value) is dict, label + ' must be an object')
    return value


def fingerprint(value):
    return {key: getattr(value, key) for key in
            ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def identity(pid):
    # Same /proc field extraction as the existing preparation identity helper.
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': int(pid), 'parent': int(fields[1]), 'group': int(fields[2]),
                'session': int(fields[3]), 'start_ticks': int(fields[19]), 'state': fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def validate_spec(spec):
    # This guard deliberately precedes every raw, inventory and receipt open.
    require(type(spec) is dict and spec.get('schema') == 'mr3-cancel-window-extraction-spec-v1',
            'wrong descriptive extraction specification')
    require(type(spec.get('admitted')) is bool and spec['admitted'] is True,
            'pending/unadmitted spec cannot open any raw input')
    require(spec.get('evidence_freeze') == EVIDENCE_FREEZE
            and spec.get('epoch') == EPOCH and spec.get('robot') == ROBOT
            and spec.get('fixed_goal_ids') == list(GOALS)
            and spec.get('next_goal_fact_bound_ns') == 49860000000,
            'fixed old evidence/actor/goal references differ')
    require(spec.get('windows') == [PRIMARY, SECONDARY],
            'only the declared primary and explicitly declared secondary windows are allowed')
    require(spec.get('execution_freeze_binding') == 'required-new-clean-cli',
            'a new exact execution freeze is required')
    limits = spec.get('limits')
    require(type(limits) is dict and set(limits) == LIMIT_KEYS
            and all(integer(value, 1) for value in limits.values()), 'all finite integer resource caps are required')
    require(type(spec.get('inputs')) is dict and set(spec['inputs']) == MANDATORY,
            'exactly the fixed five input streams are required')
    for label, item in spec['inputs'].items():
        require(type(item) is dict and type(item.get('path')) is str
                and Path(item['path']).is_absolute() and item.get('codec') in ('identity', 'gzip')
                and item.get('format') == ('text' if label == 'launch' else 'jsonl')
                and type(item.get('inventory_original_path')) is str
                and Path(item['inventory_original_path']).is_absolute()
                and integer(item.get('encoded_bytes')) and digest(item.get('encoded_sha256'))
                and integer(item.get('decoded_byte_limit'), 1),
                'missing exact encoded/decoded input declaration: ' + label)
        require((item.get('decoded_bytes') is None and item.get('decoded_sha256') is None) or
                (integer(item.get('decoded_bytes')) and digest(item.get('decoded_sha256'))),
                'expected decoded pin must be a complete pair or explicitly unavailable')
        if item['codec'] == 'identity':
            require(item['decoded_byte_limit'] >= item['encoded_bytes'] and
                    (item.get('decoded_bytes') is None or item['decoded_bytes'] == item['encoded_bytes']
                     and item['decoded_sha256'] == item['encoded_sha256']), 'plain decoded content must equal encoded content')
        elif item.get('decoded_bytes') is not None:
            require(item['decoded_byte_limit'] >= item['decoded_bytes'], 'decoded pin exceeds its allocated cap')
    require(sum(item['encoded_bytes'] for item in spec['inputs'].values()) <= limits['total_encoded_bytes']
            and sum(item['decoded_byte_limit'] for item in spec['inputs'].values()) <= limits['total_decoded_bytes'],
            'resource reservation does not cover whole declared inputs')
    for key in ('closed_inventory', 'closed_quiescence_review', 'consumer'):
        ref = spec.get(key)
        require(type(ref) is dict and type(ref.get('path')) is str and Path(ref['path']).is_absolute()
                and digest(ref.get('sha256')) and integer(ref.get('bytes'), 1),
                'missing exact provenance binding: ' + key)
    require(type(spec.get('interpretation_sources')) is dict and spec['interpretation_sources'],
            'old source interpretation must be explicitly bound')
    return spec


def bound_document(ref):
    path = Path(ref['path']); before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not path.is_symlink()
            and before.st_size == ref['bytes'], 'provenance file stat/type differs')
    raw = path.read_bytes()
    require(fingerprint(before) == fingerprint(path.lstat()) and sha(raw) == ref['sha256'],
            'provenance file SHA/stat differs')
    return decode(raw)


def provenance(spec, execution_freeze, spec_path, expected_spec_raw):
    require(type(execution_freeze) is str and re.fullmatch('[0-9a-f]{40}', execution_freeze)
            and execution_freeze != EVIDENCE_FREEZE, 'new forensic execution freeze required')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)
    require(git('rev-parse', 'HEAD').decode().strip() == execution_freeze
            == git('rev-parse', 'origin/main').decode().strip()
            and not git('status', '--porcelain'), 'forensic source is not its clean pushed freeze')
    require(spec_path.is_absolute() and '..' not in spec_path.parts
            and spec_path == spec_path.resolve(strict=True) and spec_path.is_relative_to(ROOT),
            'execution specification must be canonical inside its new source freeze')
    spec_stat = spec_path.lstat()
    require(stat.S_ISREG(spec_stat.st_mode) and spec_path.read_bytes() == expected_spec_raw
            == git('show', execution_freeze + ':' + str(spec_path.relative_to(ROOT))),
            'execution spec/resource/input pins are not the exact new frozen bytes')
    consumer = Path(__file__).resolve(); require(str(consumer) == spec['consumer']['path'], 'consumer path differs')
    current = consumer.read_bytes(); relative = str(consumer.relative_to(ROOT))
    require(sha(current) == spec['consumer']['sha256'] and len(current) == spec['consumer']['bytes']
            and git('show', execution_freeze + ':' + relative) == current,
            'consumer differs from its declared new source freeze')
    for relative, pin in spec['interpretation_sources'].items():
        require(type(relative) is str and not Path(relative).is_absolute() and '..' not in Path(relative).parts
                and digest(pin.get('sha256')) and integer(pin.get('bytes'), 1), 'invalid old source identity')
        raw = git('show', EVIDENCE_FREEZE + ':' + relative)
        require(raw == (ROOT / relative).read_bytes() and len(raw) == pin['bytes']
                and sha(raw) == pin['sha256'], 'old interpretation source changed: ' + relative)
    review = bound_document(spec['closed_quiescence_review'])
    require(review.get('freeze') == EVIDENCE_FREEZE and review.get('passed') is True
            and review.get('parent_wait_proof_valid') is True
            and review.get('all_saved_owned_PID_start_identities_fresh_gone') is True
            and review.get('identity_inventory_complete_under_A16_rules') is True
            and review.get('root_tool_session_id') == 30588
            and type(review.get('root_tool_actual_returncode_observed')) is int,
            'old activity has no genuine closed/quiescent metadata proof')
    # Old scientific FAIL is allowed and retained; quiescence is not science.
    inventory = bound_document(spec['closed_inventory'])
    freeze_field = spec['closed_inventory'].get('freeze_field')
    require(freeze_field in ('freeze', 'execution_freeze')
            and inventory.get(freeze_field) == EVIDENCE_FREEZE
            and type(inventory.get('entries')) is list, 'closed inventory identity is incomplete')
    for label, item in spec['inputs'].items():
        matches = [row for row in inventory['entries']
                   if row.get('original') == item['inventory_original_path']]
        require(len(matches) == 1 and matches[0].get('original_bytes') == item['encoded_bytes']
                and matches[0].get('original_sha256') == item['encoded_sha256']
                and matches[0].get('source_stat_stable') is True,
                'raw input is not the exact declared original inventory object: ' + label)
        require(item['path'] == item['inventory_original_path'] == matches[0]['original'],
                'raw path is not the exact inventory original encoded object: ' + label)
    return {'execution_freeze': execution_freeze, 'evidence_freeze': EVIDENCE_FREEZE,
            'execution_specification': {'path': str(spec_path), 'sha256': sha(expected_spec_raw),
                                        'bytes': len(expected_spec_raw), 'stat': fingerprint(spec_stat)},
            'consumer': spec['consumer'], 'closed_inventory': spec['closed_inventory'],
            'closed_quiescence_review': spec['closed_quiescence_review'],
            'old_activity_scientific_passed': review.get('activity_passed'),
            'interpretation_sources': spec['interpretation_sources']}


class EncodedHash(io.RawIOBase):
    def __init__(self, stream, expected, deadline):
        self.stream, self.expected, self.deadline = stream, expected, deadline
        self.hasher, self.count = hashlib.sha256(), 0
    def readable(self):
        return True
    def readinto(self, target):
        require(time.monotonic() < self.deadline, 'work deadline expired; unread suffix retained')
        raw = self.stream.read(len(target)); self.count += len(raw); self.hasher.update(raw)
        require(self.count <= self.expected, 'encoded input exceeded declared whole size')
        target[:len(raw)] = raw
        return len(raw)


def seconds_ref(value, field):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'invalid source simulation seconds: ' + field)
    exact = Decimal(str(value)) * Decimal(1000000000)
    nearest = exact.to_integral_value()
    return {'field': field, 'selection_ns': int(nearest), 'original_value': value,
            'selection_rounding_only': exact != nearest,
            'domain': 'source-recorded simulation clock; rounded only for window selection'}


def clock_refs(row, label):
    refs = []
    for field in ({'adapter': ('stamp',), 'motion': ('sim_time_sec',),
                   'drive': (), 'odom': ()}.get(label, ())):
        if field in row: refs.append(seconds_ref(row[field], field))
    fields = {'drive': ('sim_time_ns',), 'odom': ('source_clock_ns', 'sim_time_ns')}.get(label, ())
    for field in fields:
        if field in row:
            require(integer(row[field]), 'invalid source nanosecond clock: ' + field)
            refs.append({'field': field, 'selection_ns': row[field],
                         'original_value': row[field], 'domain': 'source-recorded simulation ns'})
    payload = object_value(row.get('payload', {}), 'record payload')
    if label == 'motion' and row.get('kind') == 'own_odom':
        message = object_value(payload.get('message'), 'raw odometry message')
        header = object_value(message.get('header'), 'raw odometry header')
        stamp = object_value(header.get('stamp'), 'raw odometry stamp')
        require(integer(stamp.get('sec')) and integer(stamp.get('nanosec'))
                and stamp['nanosec'] < 1000000000, 'invalid actual raw odometry header source clock')
        refs.append({'field': 'payload.message.header.stamp',
                     'selection_ns': stamp['sec'] * 1000000000 + stamp['nanosec'],
                     'original_value': stamp, 'domain': 'source-recorded odometry simulation header'})
    if label == 'motion' and row.get('kind') == 'reach_driver_ingress':
        message = object_value(payload.get('message'), 'native receipt message')
        for field in ('source_clock_ns', 'clock_ns'):
            if field in message:
                require(integer(message[field]), 'invalid actual native receipt source clock')
                refs.append({'field': 'payload.message.' + field, 'selection_ns': message[field],
                             'original_value': message[field], 'domain': 'source-recorded native receipt simulation ns'})
    return refs


def actor_and_class(row, label):
    payload = object_value(row.get('payload', {}), 'record payload')
    actor = row.get('robot', payload.get('robot'))
    if label == 'adapter' and row.get('kind') == 'delivery':
        actor = payload.get('source', actor)
    kind = row.get('kind', row.get('operation', 'untyped'))
    if label == 'motion' and kind == 'reach_driver_ingress':
        kind += ':' + str(payload.get('kind'))
    if label == 'motion' and row.get('kind') in MOTION_KINDS - JOINT_MOTION_KINDS:
        require(actor in ('tb1', 'tb2', 'tb3'), 'critical motion record lacks an attributable robot')
    if label == 'adapter' and row.get('kind') in ('native_send', 'native_cancel', 'delivery'):
        require(actor in ('tb1', 'tb2', 'tb3'), 'critical adapter record lacks an attributable robot')
    if label in ('drive', 'odom'):
        require(actor == ROBOT, 'single-robot native stream has missing/different actor')
    return actor, str(kind)


def relevant(row, label, actor, kind):
    if label == 'adapter': return row.get('kind') in ADAPTER_KINDS and actor in (None, ROBOT)
    if label == 'motion':
        return row.get('kind') in MOTION_KINDS and (actor == ROBOT or
               actor in (None, 'joint') and row.get('kind') in JOINT_MOTION_KINDS)
    if label in ('drive', 'odom'): return actor == ROBOT
    return False


def goal_dependency(row, label):
    if label != 'adapter': return False
    payload = object_value(row.get('payload', {}), 'adapter payload')
    inner = object_value(payload.get('payload', {}), 'adapter envelope payload')
    goal = payload.get('goal_id', inner.get('goal_id'))
    if goal not in GOALS: return False
    kind = row.get('kind')
    return kind in ('native_send', 'native_cancel') or (kind == 'delivery' and
        payload.get('stream') == 'receipt' and inner.get('type') in ('accept', 'cancel', 'result')) or (
        kind == 'protocol' and payload.get('type') in
        ('send_goal', 'cancel_goal', 'cancel_response', 'protocol_terminal', 'pending_goal_expired'))


class Selection:
    def __init__(self, windows, limits):
        self.windows, self.limits = windows, limits
        self.rows, self.context = {}, {}
        self.counts = Counter(); self.drops = 0; self.raw_bytes = 0
        self.first_next_send = None
        self.goal_context = Counter()
    def retain(self, key, value, reason):
        if key in self.rows:
            self.rows[key]['selection_reasons'].add(reason); return
        size = len(value['raw_utf8'].encode())
        if len(self.rows) >= self.limits['selected_records'] or self.raw_bytes + size > self.limits['selected_raw_bytes']:
            self.drops += 1; return
        self.raw_bytes += size; self.rows[key] = dict(value, selection_reasons={reason})
    def accept(self, row, label, ordinal, offset, raw):
        actor, kind = actor_and_class(row, label)
        if not relevant(row, label, actor, kind): return
        refs = clock_refs(row, label)
        require(refs, 'relevant row has no source-supported simulation clock')
        value = {'input': label, 'line_1based': ordinal, 'decoded_byte_offset': offset,
                 'original_line_sha256': sha(raw), 'raw_utf8': raw.decode('utf-8'),
                 'source_record_sequence': row.get('record_sequence'),
                 'source_clock_refs': refs, 'actor': actor, 'record_class': kind}
        key = label, ordinal
        if row.get('kind') in ('configuration', 'initial_encoder_configuration'):
            self.retain(key, value, 'original_configuration_context')
        if label == 'drive' and row.get('kind') == 'initial_encoder_receive' and (
                integer(row.get('cmd_seq'), 1) and row.get('cmd_seq') == row.get('first_nonzero_received_cmd_seq')):
            self.retain(key, value, 'original_first_nonzero_receive_latch_dependency')
        if goal_dependency(row, label):
            self.retain(key, value, 'fixed_goal_transaction_dependency')
            payload = row['payload']; inner = payload.get('payload', {})
            goal = payload.get('goal_id', inner.get('goal_id'))
            category = row['kind'] if row['kind'] != 'delivery' else 'receipt:' + inner['type']
            self.goal_context[goal + ':' + category] += 1
        if label == 'adapter' and row.get('kind') == 'native_send' and actor == ROBOT:
            source = refs[0]['selection_ns']
            if source > 42860000000 and self.first_next_send is None:
                self.first_next_send = {'clock_ns': source, 'line_1based': ordinal,
                                        'goal_id': row.get('payload', {}).get('goal_id')}
                self.retain(key, value, 'first_native_send_after_primary_cancel_fact_pointer')
        for window in self.windows:
            clocks = [ref['selection_ns'] for ref in refs]
            if any(window['start_ns'] <= clock <= window['end_ns'] for clock in clocks):
                self.retain(key, value, window['id'] + ':source_clock_window')
                self.counts[window['id'] + ':' + label + ':' + str(actor) + ':' + kind] += 1
            # Context never shares a cache across robot or event/command class.
            cache = (label, window['id'], actor, kind)
            if refs[0]['selection_ns'] < window['start_ns']:
                self.context[cache, 'before'] = key, value
            elif refs[0]['selection_ns'] > window['end_ns']:
                self.context.setdefault((cache, 'after'), (key, value))
    def finish(self):
        for (cache, side), (key, value) in self.context.items():
            self.retain(key, value, cache[1] + ':boundary_' + side + ':' + cache[3])
        output = []
        # Group by original input and line, never by cross-process wall/sim time.
        for key in sorted(self.rows):
            value = dict(self.rows[key]); value['selection_reasons'] = sorted(value['selection_reasons'])
            output.append(value)
        return output


def unrestored_dependencies(selected):
    """Describe bounded selected-row links; never silently claim absent links restored."""
    rows = [(item, decode(item['raw_utf8'])) for item in selected if item['input'] != 'launch']
    drive = [row for item, row in rows if item['input'] == 'drive']
    motion = [row for item, row in rows if item['input'] == 'motion']
    commands = [row for row in drive if row.get('kind') == 'command_received']
    receives = [row for row in drive if row.get('kind') == 'initial_encoder_receive']
    decisions = [row['payload'] for row in motion if row.get('kind') == 'reach_decision']
    applied = [row['payload']['message'] for row in motion if row.get('kind') == 'reach_driver_ingress'
               and row['payload'].get('kind') == 'applied']
    missing = []
    actuations = [row for row in drive if row.get('kind') == 'actuation']
    if not actuations:
        missing.append('selected_native_actuation_absent')
    for act in actuations:
        key = 'actuation:' + str(act.get('actuation_seq')) + ':pair:' + str(act.get('pair_index'))
        command = [row for row in commands if row.get('cmd_seq') == act.get('cmd_seq')
                   and row.get('target_decision_sequence') == act.get('target_decision_sequence')
                   and row.get('target_clock_ns') == act.get('target_clock_ns')]
        if len(command) != 1:
            missing.append(key + ':unique_command_received_not_restored')
        if not any(row.get('decision_sequence') == act.get('target_decision_sequence')
                   and row.get('clock_ns') == act.get('target_clock_ns') for row in decisions):
            missing.append(key + ':guard_decision_not_restored')
        encoder = object_value(act.get('initial_encoder_hold'), 'selected actuation encoder source')
        target = encoder.get('genuine_consumed_target')
        feeds = [row for row in applied if row.get('cmd_seq') == act.get('cmd_seq')
                 and row.get('actuation_sequence') == act.get('actuation_seq')
                 and row.get('source_clock_ns') == act.get('sim_time_ns')
                 and row.get('target') == target and row.get('dt_ns') == act.get('dt_ns')]
        pairs = [pair for feed in feeds for pair in feed.get('pairs', [])
                 if type(pair) is dict and pair.get('pair_index') == act.get('pair_index')]
        fields = ('current_rim_mps', 'desired_rim_mps', 'applied_rim_mps', 'alpha', 'max_acceleration_mps2')
        if len(pairs) != 1 or any(pairs[0].get(field) != act.get(field) for field in fields):
            missing.append(key + ':exact_APPLIED_target_sequence_clock_pair_not_restored')
        first = encoder.get('first_nonzero_received_cmd_seq')
        latch = [row for row in receives if integer(first, 1) and row.get('cmd_seq') == first
                 and row.get('first_nonzero_received_cmd_seq') == first
                 and row.get('sim_time_ns') == encoder.get('first_nonzero_received_clock_ns')
                 and row.get('stored_target') == encoder.get('first_nonzero_received_target')]
        if len(latch) != 1:
            missing.append(key + ':original_first_nonzero_receive_not_restored')
    return missing


def scan(path, label, item, selection, deadline, limits):
    require(time.monotonic() < deadline, 'work deadline expired before another raw open')
    require(path.is_absolute() and '..' not in path.parts and path == path.resolve(strict=True),
            'raw path must be absolute canonical and have no symlink component')
    before = path.lstat(); require(stat.S_ISREG(before.st_mode) and not path.is_symlink()
        and before.st_size == item['encoded_bytes'], 'input type/encoded size differs before open')
    errors = []; error_count = 0; count = total = 0; decoded_hash = hashlib.sha256()
    complete = False; previous_sequence = 0; selected_text = deque(maxlen=2); pending_text = 0
    def error(message):
        nonlocal error_count
        error_count += 1
        if len(errors) < 32: errors.append(message)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as original:
        require(fingerprint(os.fstat(original.fileno())) == fingerprint(before), 'opened input identity changed')
        hashed = EncodedHash(original, item['encoded_bytes'], deadline)
        buffered = io.BufferedReader(hashed)
        stream = gzip.GzipFile(fileobj=buffered, mode='rb') if item['codec'] == 'gzip' else buffered
        try:
            while True:
                require(time.monotonic() < deadline, 'work deadline expired; unread suffix retained')
                raw = stream.readline(limits['line_bytes'] + 1)
                if not raw:
                    complete = True; break
                offset = total; count += 1; total += len(raw); decoded_hash.update(raw)
                require(total <= item['decoded_byte_limit'] and count <= limits['lines_per_file']
                        and len(raw) <= limits['line_bytes'], 'decoded byte/line limit exceeded; unread suffix retained')
                try:
                    if label == 'launch':
                        literal = raw.decode('utf-8'); hit = any(token in literal for token in LAUNCH_LITERALS)
                        value = {'input': label, 'line_1based': count, 'decoded_byte_offset': offset,
                                 'original_line_sha256': sha(raw), 'raw_utf8': literal,
                                 'source_record_sequence': None, 'source_clock_refs': [],
                                 'clock_domain': 'UNKNOWN_UNMAPPED_NATIVE_LOG',
                                 'actor': ROBOT if ROBOT in literal else 'UNKNOWN', 'record_class': 'native_log'}
                        if hit:
                            for old_key, old_value in selected_text:
                                selection.retain(old_key, old_value, 'native_cancel_literal_preceding_context')
                            selection.retain((label, count), value, 'native_cancel_literal_whole_closed_log')
                            pending_text = 2
                        elif pending_text:
                            selection.retain((label, count), value, 'native_cancel_literal_following_context')
                            pending_text -= 1
                        selected_text.append(((label, count), value))
                    else:
                        require(raw.endswith(b'\n'), 'incomplete JSONL tail')
                        row = decode(raw); require(type(row) is dict, 'JSONL record is not an object')
                        if 'epoch' in row: require(row['epoch'] == EPOCH, 'cross-epoch input row')
                        if label in ('adapter', 'motion', 'drive', 'odom'):
                            require(row.get('epoch') == EPOCH, 'mandatory stream row lacks exact epoch')
                        if label == 'drive':
                            require(row.get('kind') in DRIVE_KINDS, 'unknown native event kind')
                        if label == 'odom':
                            require(row.get('kind') in ('configuration', 'publication'), 'unknown native odometry event kind')
                        if label == 'motion' and row.get('kind') == 'reach_driver_ingress':
                            require(row.get('payload', {}).get('kind') in ('calibration', 'storage', 'applied'),
                                    'unknown native ingress feed class')
                        if label in ('motion', 'drive', 'odom'):
                            require(integer(row.get('record_sequence'), 1)
                                    and row['record_sequence'] == previous_sequence + 1,
                                    'complete native/motion record prefix gap')
                            previous_sequence = row['record_sequence']
                        selection.accept(row, label, count, offset, raw)
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
                    error('line ' + str(count) + ': ' + str(exc))
                    # Continue full SHA/parse; a bad row can never become absence.
            if complete:
                while buffered.read(65536):
                    pass  # Account any gzip-buffered encoded suffix, never skip its SHA.
        except (OSError, EOFError, ValueError, OverflowError) as exc:
            error(str(exc)); complete = False
        encoded_count, encoded_sha = hashed.count, hashed.hasher.hexdigest()
    after = path.lstat()
    if fingerprint(before) != fingerprint(after): error('input source stat changed')
    expected_decoded_bytes = item['encoded_bytes'] if item['codec'] == 'identity' else item.get('decoded_bytes')
    expected_decoded_sha = item['encoded_sha256'] if item['codec'] == 'identity' else item.get('decoded_sha256')
    if complete and (encoded_count != item['encoded_bytes'] or encoded_sha != item['encoded_sha256']):
        error('whole encoded SHA or byte count differs from closed declaration')
    if complete and expected_decoded_bytes is not None and (
            total != expected_decoded_bytes or decoded_hash.hexdigest() != expected_decoded_sha):
        error('whole decoded SHA or byte count differs from its available expected pin')
    return {'input': label, 'path': str(path), 'stat_before': fingerprint(before), 'stat_after': fingerprint(after),
            'encoded_input_open_count': 1, 'decoded_scan_pass_count': 1,
            'encoded_validation_additional_read_bytes': 0,
            'encoded_parse_read_bytes': encoded_count, 'decoded_parse_bytes': total,
            'expected_decoded_pin_available': expected_decoded_bytes is not None,
            'expected_decoded_pin_source': 'plain_identity' if item['codec'] == 'identity' else
                'predeclared' if expected_decoded_bytes is not None else 'UNAVAILABLE_ENCODED_CONTENT_FIXED',
            'cost_scope': 'one encoded read pass hashes while decoding/parsing; boundary dependencies use the same scan',
            'encoded_bytes_read': encoded_count, 'encoded_sha256_of_read_bytes': encoded_sha,
            'decoded_bytes_read': total, 'decoded_sha256_of_read_bytes': decoded_hash.hexdigest(),
            'lines_read': count, 'whole_input_read': complete,
            'whole_binding_and_parse_complete': complete and error_count == 0,
            'error_count': error_count, 'errors': errors,
            'omitted_error_count': max(0, error_count - len(errors))}


def main(argv=None):
    consumer_identity = identity(os.getpid())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.resolve().is_relative_to(ROOT) and not args.output.exists(),
            'exclusive outside-repository output required')
    started = time.monotonic_ns()
    result = {'schema': 'mr3-cancel-window-description-v1', 'passed': False, 'errors': [],
              'scientific_qualification': False, 'root_cause_proved': False,
              'causal_status': 'UNKNOWN_DESCRIPTIVE_ONLY', 'old_FAIL_rejudged': False,
              'started_monotonic_ns': started, 'input_reports': [],
              'consumer_identity': consumer_identity,
              'actual_argv': [sys.executable, *sys.argv]}
    output_cap = 65536
    try:
        require(consumer_identity is not None, 'consumer /proc start identity unavailable')
        spec_raw = args.spec.read_bytes(); spec = validate_spec(decode(spec_raw))
        output_cap = spec['limits']['output_bytes']; deadline = time.monotonic() + spec['limits']['work_seconds']
        result['spec'] = {'path': str(args.spec), 'sha256': sha(spec_raw)}
        result['source_before'] = provenance(spec, args.freeze, args.spec, spec_raw)
        require(time.monotonic() < deadline, 'work cap exceeded by source/provenance validation')
        selection = Selection(spec['windows'], spec['limits'])
        for label, item in spec['inputs'].items():
            result['input_reports'].append(scan(Path(item['path']), label, item, selection,
                                                deadline, spec['limits']))
        result['selected_records'] = selection.finish()
        result['unrestored_dependencies'] = unrestored_dependencies(result['selected_records'])
        result['selected_counts'] = dict(selection.counts)
        result['fixed_goal_context_counts'] = dict(selection.goal_context)
        result['missing_window_inputs'] = [window['id'] + ':' + label
            for window in spec['windows'] for label in ('adapter', 'motion', 'drive', 'odom')
            if not any(key.startswith(window['id'] + ':' + label + ':') and count > 0
                       for key, count in selection.counts.items())]
        result['missing_fixed_goal_context'] = [goal + ':' + category for goal in GOALS
            for category in ('native_send', 'native_cancel', 'receipt:accept', 'receipt:cancel', 'receipt:result')
            if not selection.goal_context[goal + ':' + category]]
        result['input_cost_totals'] = {
            'encoded_validation_additional_read_bytes': 0,
            'encoded_parse_read_bytes': sum(row['encoded_parse_read_bytes'] for row in result['input_reports']),
            'decoded_parse_bytes': sum(row['decoded_parse_bytes'] for row in result['input_reports']),
            'encoded_input_open_count': len(result['input_reports']),
            'source_provenance_passes': 2,
            'source_provenance_cost_scope': 'two complete inventory/quiescence metadata reads and source/git checks; included in complete work/parent wall, not window-hit cost'}
        result['selection_drop_count'] = selection.drops
        result['first_native_send_after_primary_cancel'] = selection.first_next_send
        result['source_after'] = provenance(spec, args.freeze, args.spec, spec_raw)
        require(time.monotonic() < deadline, 'work cap exceeded by complete description/source checks')
        require(result['source_before'] == result['source_after'], 'source/provenance changed during description')
        result['description_complete'] = all(row['whole_binding_and_parse_complete']
            for row in result['input_reports']) and selection.drops == 0 \
            and not result['missing_window_inputs'] and not result['missing_fixed_goal_context'] \
            and not result['unrestored_dependencies']
        result['passed'] = result['description_complete']
        if not result['passed']: result['errors'].append('INCOMPLETE_INPUT_PARSE_BINDING_OR_SELECTION')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, subprocess.SubprocessError) as exc:
        result['errors'].append(str(exc))
    result['ended_monotonic_ns'] = time.monotonic_ns()
    result['scope'] = ('Fixed old closed cancel windows and explicitly bounded dependencies only; '
                       'full input costs/encoded+decoded hashes, original source time/sequence/line order. '
                       'No cross-process total order, invented source stamp, bound change, or science verdict.')
    encoded = canonical(result) + b'\n'
    if len(encoded) > output_cap:
        cost = {'encoded_parse_read_bytes': sum(row['encoded_parse_read_bytes'] for row in result['input_reports']),
                'decoded_parse_bytes': sum(row['decoded_parse_bytes'] for row in result['input_reports']),
                'encoded_input_open_count': len(result['input_reports']),
                'complete_input_count': sum(row['whole_binding_and_parse_complete'] for row in result['input_reports'])}
        result = {key: result[key] for key in ('schema', 'started_monotonic_ns', 'ended_monotonic_ns',
                                              'consumer_identity', 'actual_argv')}
        result.update(passed=False, scientific_qualification=False, root_cause_proved=False,
                      causal_status='UNKNOWN_OUTPUT_LIMIT', old_FAIL_rejudged=False,
                      input_cost_summary=cost,
                      errors=['output limit exceeded; detailed description omitted; original inputs unchanged'])
        encoded = canonical(result) + b'\n'
    require(len(encoded) <= output_cap, 'fixed failure receipt exceeds output reservation')
    with args.output.open('xb') as stream: stream.write(encoded)
    print(json.dumps({'passed': result['passed'], 'root_cause_proved': False, 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
