#!/usr/bin/env python3
"""Independent received-state provenance replay, using only standard library.

This reads recorded producer callbacks and actual publish-call records, then
binds downstream motion callbacks in their original order. It does not import
production code or claim DDS completeness, continuous freshness, or task PASS.
"""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

ROBOTS = ('tb1', 'tb2', 'tb3')
SCHEMA = 'mr3-information-state-audit-v1'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, name + ' must be an integer')
    return value


def finite(value, name):
    require(type(value) in (int, float) and math.isfinite(value), name + ' nonfinite/type')
    return value


def canonical(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return encoded.encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seconds_ns(value):
    return round(finite(value, 'seconds') * 1_000_000_000)


def header_ns(raw):
    stamp = raw['header']['stamp']
    sec = integer(stamp['sec'], 'stamp.sec')
    nano = integer(stamp['nanosec'], 'stamp.nanosec')
    require(nano < 1_000_000_000, 'stamp.nanosec range')
    return sec * 1_000_000_000 + nano


def validate_raw(kind, raw):
    require(type(raw['header']['frame_id']) is str and type(raw['child_frame_id']) is str,
            'raw frame IDs must be strings')
    vectors = ([raw['transform']['translation'], raw['transform']['rotation']] if kind == 'tf'
               else [raw['pose']['pose']['position'], raw['pose']['pose']['orientation'],
                     raw['twist']['twist']['linear'], raw['twist']['twist']['angular']])
    for value in vectors:
        require(isinstance(value, dict) and set(value) in ({'x', 'y', 'z'}, {'x', 'y', 'z', 'w'}),
                'raw vector/quaternion shape')
        require(all(type(number) is float and math.isfinite(number) for number in value.values()),
                'raw ROS float field type/nonfinite')
    if kind == 'odom':
        for name in ('pose', 'twist'):
            value = raw[name]['covariance']
            require(type(value) is list and len(value) == 36
                    and all(type(number) is float and math.isfinite(number) for number in value),
                    'raw odometry covariance shape/type/nonfinite')


def reject_constant(value):
    raise ValueError('nonfinite JSON constant ' + value)


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key ' + key)
        out[key] = value
    return out


def parse(data):
    return json.loads(data, parse_constant=reject_constant, object_pairs_hook=unique_object)


class Inputs:
    def __init__(self):
        self.bindings = []

    def read(self, directory, filename):
        base = directory / filename
        candidates = [path for path in (base, Path(str(base) + '.gz')) if path.is_file()]
        require(candidates, 'missing required input ' + str(base))
        decoded = None
        for path in candidates:
            encoded = path.read_bytes()
            payload = gzip.decompress(encoded) if path.suffix == '.gz' else encoded
            require(decoded is None or payload == decoded,
                    'plain/gzip inputs disagree ' + filename)
            decoded = payload
            self.bindings.append({'path': str(path),
                                  'encoded_sha256': hashlib.sha256(encoded).hexdigest(),
                                  'decoded_sha256': hashlib.sha256(payload).hexdigest(),
                                  'encoded_bytes': len(encoded), 'decoded_bytes': len(payload)})
        return decoded

    def rows(self, directory, filename):
        data = self.read(directory, filename)
        require(not data or data.endswith(b'\n'), 'incomplete JSONL final line ' + filename)
        return [parse(line) for line in data.splitlines() if line.strip()]

    def verify(self):
        for item in self.bindings:
            require(hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
                    == item['encoded_sha256'], 'input changed during audit ' + item['path'])


def yaw(value):
    x, y, z, w = (finite(value[key], 'quaternion.' + key) for key in ('x', 'y', 'z', 'w'))
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y ** 2 + z ** 2))


def state_from_raw(robot, odom, tf, lead_sec):
    """Reconstruct measured/common-frame fields without production helpers."""
    angle = yaw(tf['transform']['rotation'])
    point = odom['pose']['pose']['position']
    translation = tf['transform']['translation']
    heading = angle + yaw(odom['pose']['pose']['orientation'])
    odom_stamp = odom['header']['stamp']
    tf_stamp = tf['header']['stamp']
    odom_seconds = odom_stamp['sec'] + odom_stamp['nanosec'] / 1e9
    tf_seconds = tf_stamp['sec'] + tf_stamp['nanosec'] / 1e9
    return {'robot': robot, 'name': robot,
            'x': translation['x'] + math.cos(angle) * point['x'] - math.sin(angle) * point['y'],
            'y': translation['y'] + math.sin(angle) * point['x'] + math.cos(angle) * point['y'],
            'yaw': math.atan2(math.sin(heading), math.cos(heading)),
            'v': odom['twist']['twist']['linear']['x'],
            'w': odom['twist']['twist']['angular']['z'],
            'odom_source_stamp': odom_seconds, 'tf_source_stamp': tf_seconds - lead_sec,
            'tf_validity_stamp': tf_seconds, 'tf_validity_lead_sec': lead_sec,
            'odometry': odom, 'transform': tf}


def audit_motion(rows, publications, epoch):
    published = {}
    for item in publications:
        published.setdefault(item['message_sha256'], []).append(item)
    current = {}
    counts = Counter()
    sequence = 0
    received_sequence = 0
    for row in rows:
        require(row['epoch'] == epoch, 'motion cross-epoch row')
        require(type(row['record_sequence']) is int and row['record_sequence'] == sequence + 1,
                'motion record sequence gap')
        sequence += 1
        kind, value = row['kind'], row['payload']
        if kind == 'received_states':
            stamp = row['wall_monotonic_ns']
            matches = [p for p in published.get(digest(value), [])
                       if p['wall_monotonic_ns'] <= stamp]
            require(matches, 'motion received state has no earlier actual publication')
            require(value['epoch'] == epoch, 'received state epoch')
            require(type(value['sequence']) is int and value['sequence'] > received_sequence,
                    'received bundle sequence duplicate/regression')
            received_sequence = value['sequence']
            require(len(value['robots']) == 3
                    and {r['name'] for r in value['robots']} == set(ROBOTS),
                    'received state robot identities')
            current = {robot['name']: robot for robot in value['robots']}
            counts['received_bundles'] += 1
        elif kind == 'decision':
            robot = value['robot']
            require(robot in ROBOTS, 'motion decision robot')
            expected = {name: current.get(name) for name in ROBOTS if name != robot}
            require(canonical(value['received_peers']) == canonical(expected),
                    'motion decision borrowed different/late received state')
            counts['decisions'] += 1
    require(counts['received_bundles'] > 0 and counts['decisions'] > 0,
            'no real received bundles/decisions to bind')
    return dict(counts)


# Producer ledger replay is below; raw callbacks are replayed in producer order,
# while downstream decisions use their own independently recorded callback order.

class LedgerReplay:
    def __init__(self, epoch):
        self.epoch = epoch
        self.counts = Counter()
        self.config = None
        self.lead_sec = None
        self.lead_ns = None
        self.raw = {(kind, robot): {} for kind in ('odom', 'tf') for robot in ROBOTS}
        self.pending = {(kind, robot): [] for kind in ('odom', 'tf') for robot in ROBOTS}
        self.current = {(kind, robot): None for kind in ('odom', 'tf') for robot in ROBOTS}
        self.admitted = {(kind, robot): [] for kind in ('odom', 'tf') for robot in ROBOTS}
        self.last_inputs = {(kind, robot): 0 for kind in ('odom', 'tf') for robot in ROBOTS}
        self.selections = {}
        self.sent = {}
        self.latest_sent = {}
        self.latest_delivered = {}
        self.published = []
        self.last_published_cycle = 0
        self.sequence = 0
        self.last_wall = -1
        self.failed = False

    def record(self, row):
        require(row['schema'] == SCHEMA and row['epoch'] == self.epoch,
                'ledger schema/epoch mismatch')
        require(type(row['record_sequence']) is int
                and row['record_sequence'] == self.sequence + 1,
                'ledger record sequence gap')
        self.sequence += 1
        clock = integer(row['clock_ns'], 'clock_ns')
        wall = integer(row['wall_monotonic_ns'], 'wall_monotonic_ns', 1)
        require(wall >= self.last_wall, 'ledger wall time regressed')
        self.last_wall = wall
        kind, value = row['kind'], row['payload']
        require(isinstance(value, dict), 'ledger payload object')
        self.counts[kind] += 1
        if kind == 'configuration':
            require(self.config is None and self.sequence == 1,
                    'configuration must be first/unique')
            self.config = value
            self.lead_sec = finite(value['tf_validity_lead_sec'], 'tf_validity_lead_sec')
            require(self.lead_sec == .2, 'TF actual source must retain declared .2 lead')
            self.lead_ns = seconds_ns(self.lead_sec)
            require(type(value['pending_limit']) is int and value['pending_limit'] == 256,
                    'pending bound must remain integer256')
            require(canonical(value['state_period_sec']) == canonical(.1),
                    'state period must remain .1sec')
            require(value['odom_pending_order'] == 'source_ns_ascending'
                    and value['tf_pending_order'] == 'accepted_header_ascending',
                    'pending source order contract')
            return
        require(self.config is not None, 'missing configuration')
        if kind in ('odom_ingress', 'tf_ingress'):
            self.ingress(kind.split('_')[0], value, clock)
        elif kind == 'tf_promote':
            self.tf_promote(value, clock)
        elif kind == 'state_selection':
            self.selection(value, clock)
        elif kind == 'state_send':
            self.send(value, clock)
        elif kind == 'state_publish':
            self.publish(value, clock, wall)
        else:
            raise ValueError('unknown ledger kind ' + str(kind))

    def ingress(self, kind, value, clock):
        robot = value['robot']
        require(robot in ROBOTS, 'ingress robot')
        key = (kind, robot)
        seq = integer(value['input_sequence'], 'input_sequence', 1)
        require(seq == self.last_inputs[key] + 1, 'raw input sequence gap')
        self.last_inputs[key] = seq
        raw = value['raw']
        validate_raw(kind, raw)
        require(digest(raw) == value['raw_sha256'], 'raw ingress SHA mismatch')
        source = header_ns(raw) - (self.lead_ns if kind == 'tf' else 0)
        require(type(value['source_ns']) is int and value['source_ns'] == source,
                'raw header/declared source mismatch')
        if kind == 'tf':
            require(raw['header']['frame_id'].lstrip('/') == 'map'
                    and raw['child_frame_id'].lstrip('/') == 'odom', 'TF link scope')
        item = {'sequence': seq, 'source_ns': source, 'raw': raw,
                'raw_sha256': value['raw_sha256'], 'clock_ns': clock}
        require('matched_input_sequence' in value, 'missing matched identity field')
        admission, matched = value['admission'], value['matched_input_sequence']
        queue = self.pending[key]
        current = self.current[key]
        if kind == 'odom':
            duplicate = next((q for q in ([current] if current else []) + queue
                              if q['source_ns'] == source), None)
            if duplicate:
                expected = ('duplicate' if duplicate['raw_sha256'] == item['raw_sha256']
                            else 'conflicting_duplicate')
                expected_match = duplicate['sequence']
            elif current and source < current['source_ns']:
                expected, expected_match = 'backwards', None
            elif len(queue) >= 256:
                expected, expected_match = 'queue_overflow', None
            else:
                expected, expected_match = 'queued', None
        elif queue and header_ns(raw) <= header_ns(queue[-1]['raw']):
            expected, expected_match = 'ignored_pending_order', queue[-1]['sequence']
        elif len(queue) >= 256:
            expected, expected_match = 'queue_overflow', None
        else:
            expected, expected_match = 'queued', None
        require((matched is None or type(matched) is int) and admission == expected
                and matched == expected_match, 'incorrect ingress admission')
        self.raw[key][seq] = item
        if admission == 'queued':
            queue.append(item)
            if kind == 'odom':
                queue.sort(key=lambda q: (q['source_ns'], q['sequence']))
            self.admitted[key].append(item)
        elif admission in ('conflicting_duplicate', 'queue_overflow'):
            self.failed = True
            raise ValueError('recorded fail-closed ingress ' + admission)
        if source > clock:
            self.counts[kind + '_future_ingress'] += 1

    def expected_latest(self, kind, robot, clock):
        # Global callback prefix is an independent oracle, not producer's chosen ref.
        eligible = [q for q in self.admitted[kind, robot] if q['source_ns'] <= clock]
        return max(eligible, key=lambda q: (q['source_ns'], q['sequence'])) if eligible else None

    def promote(self, kind, robot, clock):
        key = kind, robot
        queue = self.pending[key]
        ready = [q for q in queue if q['source_ns'] <= clock]
        self.pending[key] = [q for q in queue if q['source_ns'] > clock]
        if ready:
            latest = max(ready, key=lambda q: (q['source_ns'], q['sequence']))
            if self.current[key] is None or latest['source_ns'] >= self.current[key]['source_ns']:
                self.current[key] = latest
        expected = self.expected_latest(kind, robot, clock)
        require(self.current[key] == expected, 'promotion differs from admitted callback prefix')
        return expected

    def tf_promote(self, value, clock):
        robot = value['robot']
        require(robot in ROBOTS, 'TF promote robot')
        selected = self.promote('tf', robot, clock)
        require(selected is not None and type(value['selected_input_sequence']) is int
                and value['selected_input_sequence'] == selected['sequence'],
                'incorrect TF promotion selected input')
        require(type(value['pending_tf_input_sequences']) is list
                and all(type(v) is int for v in value['pending_tf_input_sequences'])
                and value['pending_tf_input_sequences']
                == [q['sequence'] for q in self.pending['tf', robot]],
                'TF promotion lost/added pending input')

    def selection(self, value, clock):
        cycle = integer(value['cycle_id'], 'cycle_id', 1)
        robot = value['robot']
        require(robot in ROBOTS and (cycle, robot) not in self.selections,
                'duplicate/invalid selection')
        require(cycle == self.last_published_cycle + 1, 'selection cycle gap')
        require(all(item['clock_ns'] == clock for (number, _), item in self.selections.items()
                    if number == cycle), 'selection first capture clocks differ')
        odom = self.promote('odom', robot, clock)
        # Every selection must reflect current TF eligibility even when maps
        # have already promoted it. No future TF may freshen the state source.
        tf = self.expected_latest('tf', robot, clock)
        require(self.current['tf', robot] == tf, 'missing TF promote before selection')
        expected_reason = 'missing_odom' if odom is None else 'missing_tf' if tf is None else None
        state = None
        if odom is not None and tf is not None:
            if min(odom['source_ns'], tf['source_ns']) < 0:
                expected_reason = 'future_source'
            else:
                state = state_from_raw(robot, odom['raw'], tf['raw'], self.lead_sec)
                if not all(type(state[k]) in (int, float) and math.isfinite(state[k])
                           for k in ('x', 'y', 'yaw', 'v', 'w')):
                    expected_reason = 'nonfinite_state'
        for kind, selected in (('odom', odom), ('tf', tf)):
            require((value[kind + '_input_sequence'] is None
                     or type(value[kind + '_input_sequence']) is int)
                    and value[kind + '_input_sequence']
                    == (selected['sequence'] if selected else None),
                    'selection is not latest causal ' + kind)
            require((value[kind + '_source_ns'] is None
                     or type(value[kind + '_source_ns']) is int)
                    and value[kind + '_source_ns']
                    == (selected['source_ns'] if selected else None),
                    'selection source does not match raw ' + kind)
            expected_pending = [q['sequence'] for q in self.pending[kind, robot]]
            require(type(value['pending_' + kind + '_input_sequences']) is list
                    and all(type(v) is int for v in value['pending_' + kind + '_input_sequences'])
                    and value['pending_' + kind + '_input_sequences'] == expected_pending,
                    'selection dropped/added future ' + kind)
        require(value['skip_reason'] == expected_reason, 'unjustified state selection skip')
        self.selections[cycle, robot] = {'clock_ns': clock, 'state': state,
                                         'skip_reason': expected_reason,
                                         'odom': odom, 'tf': tf}
        if any(q['source_ns'] > clock for q in self.pending['odom', robot]):
            self.counts['selections_retaining_future_odom'] += 1

    def send(self, value, clock):
        cycle, robot = integer(value['cycle_id'], 'cycle_id', 1), value['robot']
        selected = self.selections.get((cycle, robot))
        require(selected is not None and selected['skip_reason'] is None,
                'send lacks valid selection')
        require((cycle, robot) not in self.sent, 'duplicate state send')
        envelope = value['envelope']
        previous = self.latest_sent.get(robot)
        expected_sequence = 1 if previous is None else previous['sequence'] + 1
        require(envelope['epoch'] == self.epoch and envelope['stream'] == 'state'
                and envelope['source'] == robot, 'sent envelope identity')
        require(type(envelope['sequence']) is int and envelope['sequence'] == expected_sequence
                and type(envelope['version']) is int
                and envelope['version'] == expected_sequence, 'sent envelope sequence/version')
        require(envelope['received_stamp'] is None, 'sent envelope already received')
        require(canonical(envelope['generated_stamp']) == canonical(selected['clock_ns'] / 1e9),
                'send generated clock differs from selection clock')
        require(clock == selected['clock_ns'], 'send row differs from first captured clock')
        source = min(selected['state']['odom_source_stamp'], selected['state']['tf_source_stamp'])
        require(canonical(envelope['source_stamp']) == canonical(source),
                'envelope source freshened/min source mismatch')
        require(canonical(envelope['payload']) == canonical(selected['state']),
                'sent state differs from selected raw callback payloads')
        require(value['payload_sha256'] == digest(envelope['payload']), 'sent payload SHA')
        self.sent[cycle, robot] = envelope
        self.latest_sent[robot] = envelope

    def publish(self, value, clock, row_wall):
        cycle = integer(value['cycle_id'], 'cycle_id', 1)
        require(cycle == self.last_published_cycle + 1, 'publish cycle gap')
        require(all((cycle, robot) in self.selections for robot in ROBOTS),
                'publish lacks three selections')
        require(all(self.selections[cycle, robot]['clock_ns'] <= clock for robot in ROBOTS),
                'publication clock before selection capture')
        require(value['scope'] == 'actual_publish_calls_returned',
                'not actual completed publish calls')
        start = integer(value['publish_started_wall_monotonic_ns'], 'publish start', 1)
        end = integer(value['publish_completed_wall_monotonic_ns'], 'publish end', 1)
        require(start <= end <= row_wall, 'invalid actual publish timing')
        message = value['message']
        require(digest(message) == value['message_sha256'], 'published message SHA')
        require(message['epoch'] == self.epoch and type(message['sequence']) is int
                and message['sequence'] == cycle, 'published bundle identity')
        require(len(message['robots']) == 3
                and {r['name'] for r in message['robots']} == set(ROBOTS),
                'published bundle robot identities')
        robots = {r['name']: r for r in message['robots']}
        envelopes = value['envelopes']
        require(set(envelopes) == set(ROBOTS), 'published envelope robot identities')
        sides = value['side_publications']
        require(len({p['robot'] for p in sides}) == len(sides), 'duplicate side publication')
        side_by_robot = {p['robot']: p for p in sides}
        expected_sides = set()
        for robot in ROBOTS:
            selection = self.selections[cycle, robot]
            require(((cycle, robot) in self.sent) == (selection['skip_reason'] is None),
                    'selection/send missing or unexpected')
            envelope = envelopes[robot]
            sent = self.latest_sent.get(robot)
            if sent is None:
                require(envelope is None, 'received envelope without preceding send')
                placeholder = {
                    'robot': robot, 'name': robot, 'valid': False,
                    'x': 0.0, 'y': 0.0, 'yaw': 0.0, 'v': 0.0, 'w': 0.0,
                    'epoch': self.epoch, 'sequence': 0, 'version': 0,
                    'source_stamp': None, 'received_stamp': None}
                require(canonical(robots[robot]) == canonical(placeholder),
                        'missing state placeholder')
                continue
            require(isinstance(envelope, dict), 'missing delivered envelope')
            stripped = dict(envelope)
            received = stripped.pop('received_stamp')
            original = dict(sent)
            original.pop('received_stamp')
            require(canonical(stripped) == canonical(original),
                    'received envelope differs from actual latest send')
            require(seconds_ns(received) <= clock and received >= envelope['generated_stamp'],
                    'received envelope clock invalid')
            if (cycle, robot) in self.sent:
                require(canonical(received) == canonical(clock / 1e9),
                        'sampled ideal delivery is not actual publish cycle')
            else:
                require(canonical(envelope) == canonical(self.latest_delivered.get(robot)),
                        'cached delivery changed its original received stamp/payload')
            self.latest_delivered[robot] = envelope
            state = dict(envelope['payload'])
            transform = state.pop('transform')
            state.update(epoch=self.epoch, sequence=envelope['sequence'],
                         version=envelope['version'],
                         source_stamp=envelope['source_stamp'], received_stamp=received,
                         valid=(envelope['source_stamp'] > 0
                                and 0 <= clock - seconds_ns(envelope['source_stamp'])
                                <= 500_000_000))
            require(canonical(robots[robot]) == canonical(state),
                    'published state differs from delivered envelope')
            expected_sides.add(robot)
            side = side_by_robot.get(robot)
            require(side is not None and side['odom_topic'] == '/mr3/received/' + robot + '/odom'
                    and side['tf_topic'] == '/mr3/received/' + robot + '/tf',
                    'side topic identity')
            require(side['odom_sha256'] == digest(state['odometry'])
                    and side['tf_sha256'] == digest(transform)
                    and type(side['envelope_sequence']) is int
                    and side['envelope_sequence'] == envelope['sequence'],
                    'side publish source/hash binding')
        require(set(side_by_robot) == expected_sides, 'side publication missing/unexpected')
        self.last_published_cycle = cycle
        self.published.append({'message_sha256': value['message_sha256'],
                               'wall_monotonic_ns': start, 'cycle_id': cycle})

    def finish(self):
        require(self.config is not None and self.published, 'no producer publication availability')
        require(all(self.last_inputs[kind, robot] > 0
                    for kind in ('odom', 'tf') for robot in ROBOTS),
                'missing real ingress for a robot/source')
        require(not self.failed, 'producer failure')
        require(all(cycle <= self.last_published_cycle for cycle, _ in self.selections),
                'incomplete final selection cycle')
        return dict(self.counts)


def audit_episode(directory, freeze):
    inputs = Inputs()
    result = {'episode': str(directory), 'passed': False, 'errors': [], 'inputs': inputs.bindings,
              'scope': ('recorded producer ingress/selection/send/delivery/publish and actual '
                        'motion receipt order; does not prove middleware completeness, eliminate '
                        'all timer races, or award task success')}
    try:
        metadata = parse(inputs.read(directory, 'metadata.json'))
        require(metadata['freeze'] == freeze, 'metadata freeze mismatch')
        epoch = metadata['epoch']
        result['epoch'] = epoch
        physics = inputs.rows(directory, 'physics.jsonl')
        result['physics_end_ns'] = max(integer(row['end_time_ns'], 'physics end')
                                       for row in physics)
        inputs.read(directory, 'transitions.jsonl')
        inputs.read(directory, 'summary.json')
        ledger = inputs.rows(directory, 'information_states.jsonl')
        motion = inputs.rows(directory, 'motion_safety.jsonl')
        replay = LedgerReplay(epoch)
        for line, row in enumerate(ledger, 1):
            try:
                replay.record(row)
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                message = 'information ledger line' + str(line) + ': ' + str(error)
                raise ValueError(message) from error
        result['producer_counts'] = replay.finish()
        result['motion_binding_counts'] = audit_motion(motion, replay.published, epoch)
        release = [seconds_ns(row['payload']['stamp'])
                   for row in motion if row['kind'] == 'release']
        require(len(release) == 1, 'missing/duplicate real task release')
        result['task_release_ns'] = release[0]
        require(result['task_release_ns'] <= result['physics_end_ns'],
                'release beyond physics end')
        result['publications_at_or_after_task_release'] = sum(
            row['clock_ns'] >= release[0] and row['kind'] == 'state_publish' for row in ledger)
        result['passed'] = True
    except (ValueError, KeyError, TypeError, OverflowError, OSError) as error:
        result['errors'].append(str(error))
    try:
        inputs.verify()
    except (ValueError, OSError) as error:
        result['passed'] = False
        result['errors'].append(str(error))
    return result


def audit(directory, freeze):
    if (directory / 'metadata.json').is_file():
        episodes = [directory]
    else:
        episodes = sorted(p for p in directory.glob('worker*/episode*') if p.is_dir())
    results = [audit_episode(path, freeze) for path in episodes]
    return {'schema': 'mr3-independent-information-review-v1', 'freeze': freeze,
            'consumer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'root': str(directory), 'passed': bool(results) and all(r['passed'] for r in results),
            'episodes': results,
            'errors': [] if results else ['no episode directories'],
            'criteria': {'raw_ingress_to_latest_causal_selection': True,
                         'future_pending_preserved': True,
                         'tf_source_is_validity_minus_point2': True,
                         'full_payload_sha_and_actual_publish_calls': True,
                         'received_callback_before_decision_binding': True,
                         'state_age_limit_sec_unchanged': .5},
            'limitations': [
                'A producer callback ledger documents that callback; it does not prove absence '
                'of DDS loss.',
                'Successful provenance replay cannot substitute for original full safety, phase, '
                'shutdown, contact, physical, activity, or task acceptance gates.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.directory, args.freeze)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output),
                      'episodes': len(result['episodes'])}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
