#!/usr/bin/env python3
"""Independent recorded state -> peer -> guard -> target storage -> physics proof.

Only the Python standard library and a SHA-pinned older independent reader are
loaded. Actual calls/receipts are established by their native component logs;
this is neither a Nav2 consumption ACK nor proof of continuous body dynamics.
"""
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct

ROOT = Path('/home/zhuyulab/ns3-workspace')
HELPER_SHA = 'ba3e89fa6feda9406f984310adccf17c2f0638644fd0d26f0c2e9040ec0e7653'
_HELPER_RELATIVE = Path('20261017_mr3_p2a0_v9/independent/mr3_independent_information_v1.py')
_candidates = ([Path(__file__).resolve().parents[2] / _HELPER_RELATIVE]
               if len(Path(__file__).resolve().parents) > 2 else [])
_candidates.append(ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/'
                           'examples/wireless-rl/report/assets') / _HELPER_RELATIVE)
HELPER = next(path for path in _candidates if path.is_file()
              and hashlib.sha256(path.read_bytes()).hexdigest() == HELPER_SHA)
SPEC = importlib.util.spec_from_file_location('pinned_independent_information_helpers', HELPER)
HELPERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPERS)
canonical, digest, require = HELPERS.canonical, HELPERS.digest, HELPERS.require
ROBOTS = ('tb1', 'tb2', 'tb3')


def integer(value, name, minimum=0):
    return HELPERS.integer(value, name, minimum)


def same(left, right, reason):
    require(canonical(left) == canonical(right), reason)


def yaw(value):
    x, y, z, w = (HELPERS.finite(value[k], 'quaternion') for k in ('x', 'y', 'z', 'w'))
    # This is the original peer/control numeric contract, including op order.
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def peer_pose(odom, transform):
    rotation = transform['transform']['rotation']
    angle = yaw(rotation)
    position = odom['pose']['pose']['position']
    translation = transform['transform']['translation']
    return (translation['x'] + math.cos(angle) * position['x']
            - math.sin(angle) * position['y'],
            translation['y'] + math.sin(angle) * position['x']
            + math.cos(angle) * position['y'],
            yaw(odom['pose']['pose']['orientation']) + angle)


@lru_cache(maxsize=1024)
def disk_offsets(age):
    radius = .25 + .04 + .26 * (max(0.0, age) + .55)
    start, stop, step = -radius, radius + .025, .025
    count = math.ceil((stop - start) / step)
    effective_step = (start + step) - start
    offsets = [start + i * effective_step for i in range(count)]
    return tuple((dx, dy) for dy in offsets for dx in offsets
                 if dx * dx + dy * dy <= radius * radius)


def cloud_bytes(peers):
    output = bytearray()
    for x, y, age in peers:
        for dx, dy in disk_offsets(age):
            output.extend(struct.pack('<fff', x + dx, y + dy, 0.))
    return bytes(output)


def expected_outputs(selected, target):
    poses, stamps = {}, {}
    for robot in ROBOTS:
        odom, tf = selected['odom', robot]['raw'], selected['tf', robot]['raw']
        odom_ns, tf_ns = HELPERS.header_ns(odom), HELPERS.header_ns(tf) - 200_000_000
        require(odom_ns > 0 and 0 <= target - odom_ns <= 500_000_000
                and 0 <= target - tf_ns <= 500_000_000, 'peer original source500ms gate')
        poses[robot] = peer_pose(odom, tf)
        # Original side layer uses source seconds, preserving float op order.
        stamp = odom['header']['stamp']
        odom_seconds = stamp['sec'] + stamp['nanosec'] / 1e9
        stamp = tf['header']['stamp']
        tf_seconds = stamp['sec'] + stamp['nanosec'] / 1e9 - .2
        stamps[robot] = min(odom_seconds, tf_seconds)
    for i, robot in enumerate(ROBOTS):
        for other in ROBOTS[i + 1:]:
            require(math.hypot(poses[robot][0] - poses[other][0],
                               poses[robot][1] - poses[other][1]) >= .5,
                    'original peer body envelope overlap')
    output = {}
    for robot in ROBOTS:
        x, y, heading = poses[robot]
        peers = []
        for other in ROBOTS:
            if other == robot:
                continue
            dx, dy = poses[other][0] - x, poses[other][1] - y
            peers.append((math.cos(heading) * dx + math.sin(heading) * dy,
                          -math.sin(heading) * dx + math.cos(heading) * dy,
                          target / 1e9 - stamps[other]))
        data = cloud_bytes(peers)
        header = {'frame_id': 'base_link',
                  'stamp': selected['odom', robot]['raw']['header']['stamp']}
        scan = {'header': header, 'angle_min': -math.pi,
                'angle_increment': 2 * math.pi / 2048,
                'angle_max': -math.pi + 2047 * (2 * math.pi / 2048),
                'time_increment': 0.0, 'scan_time': 0.0, 'range_min': .01, 'range_max': 20.0,
                'range_count': 2048, 'all_ranges_positive_infinity': True,
                'ranges_sha256': hashlib.sha256(struct.pack('<' + 'f' * 2048,
                                                            *([math.inf] * 2048))).hexdigest(),
                'intensities': []}
        cloud = {'header': header, 'height': 1, 'width': len(data) // 12,
                 'fields': [{'name': key, 'offset': offset, 'datatype': 7, 'count': 1}
                            for key, offset in (('x', 0), ('y', 4), ('z', 8))],
                 'is_bigendian': False, 'point_step': 12, 'row_step': len(data),
                 'is_dense': True, 'data_bytes': len(data),
                 'data_sha256': hashlib.sha256(data).hexdigest()}
        output[robot, 'scan'], output[robot, 'cloud'] = scan, cloud
    return output


def information_acks(rows, epoch):
    publications, acknowledgements, requests = {}, {}, {}
    terminal_notices = []
    for row in rows:
        require(row['epoch'] == epoch, 'information cross-epoch row')
        value = row['payload']
        if row['kind'] == 'state_terminal_received':
            terminal_notices.append(value['notice'])
        if row['kind'] == 'state_phase_request':
            request = value['request']
            identity = request['request_id']
            if identity not in requests:
                requests[identity] = (request, row['wall_monotonic_ns'])
            else:
                same(request, requests[identity][0], 'state raw request identity changed')
        if row['kind'] == 'state_publish':
            same(value['message_sha256'], digest(value['message']), 'information bundle SHA')
            publications[value['message_sha256']] = row
        if row['kind'] != 'state_phase_ack':
            continue
        ack = value['ack']
        require(ack['schema'] == 'mr3-state-phase-ack-v1' and ack['epoch'] == epoch
                and type(ack['ok']) is bool, 'state ACK schema/epoch/type')
        identity = ack['request_id']
        require(identity in requests, 'state ACK without actual raw request callback')
        request, request_wall = requests[identity]
        start = integer(value['publish_started_wall_monotonic_ns'], 'state ACK start', 1)
        end = integer(value['publish_completed_wall_monotonic_ns'], 'state ACK end', 1)
        require(request_wall <= start <= end <= row['wall_monotonic_ns'],
                'state ACK publication window')
        if ack['ok'] is True and ack.get('operation') == 'commit':
            publication = publications.get(ack['bundle_sha256'])
            require(publication is not None, 'state ACK without actual bundle publication')
            published = publication['payload']
            integer(ack['state_sequence'], 'state ACK positive sequence', 1)
            integer(published['message']['sequence'], 'actual bundle positive sequence', 1)
            require(type(ack['clock_ns']) is int and type(ack['target_time_ns']) is int
                    and ack['clock_ns'] == ack['target_time_ns'] == publication['clock_ns'],
                    'information commit exact clock')
            same(
                ack['state_sequence'],
                published['message']['sequence'],
                'state ACK bundle sequence')
            require(published['publish_completed_wall_monotonic_ns'] <= start,
                    'state ACK before bundle calls returned')
        elif ack['ok'] is True:
            require(ack['operation'] == 'takeover', 'unknown state ACK operation')
        else:
            require(type(ack.get('error')) is str and ack['error'], 'state negative ACK error')
            if ack['error'] == 'state_phase_task_terminal':
                require(ack.get('scope') == 'terminal_cancelled_uncommitted_state_phase'
                        and any(canonical(notice) == canonical(ack.get('terminal_notice'))
                                for notice in terminal_notices),
                        'terminal cancellation has no actual prior information notice')
                require(type(ack['clock_ns']) is int and type(ack['target_time_ns']) is int
                        and 0 <= ack['clock_ns'] <= ack['target_time_ns']
                        and HELPERS.seconds_ns(ack['terminal_notice']['end_sim_time_sec'])
                        <= ack['target_time_ns'], 'terminal cancellation clock/notice boundary')
        if identity in acknowledgements:
            same(acknowledgements[identity]['ack'], ack, 'immutable information ACK changed')
        else:
            acknowledgements[identity] = {'ack': ack,
                                          'request': request, 'request_wall': request_wall,
                                          'publish_started_wall_monotonic_ns': start,
                                          'publish_completed_wall_monotonic_ns': end}
    return acknowledgements


class PeerReplay:
    def __init__(self, epoch, state_acks):
        self.epoch, self.state_acks = epoch, state_acks
        self.configured, self.controlled = False, False
        self.inputs = defaultdict(list)
        self.input_sequences = defaultdict(int)
        self.bundles = []
        self.pending = None
        self.matched = None
        self.matched_refs = None
        self.expected_publications = None
        self.match_wall = None
        self.publication = None
        self.requests = {}
        self.request_walls = {}
        self.acks = {}
        self.record_sequence = 0
        self.commit_sequence = 0
        self.last_clock = None
        self.warmup_publications = 0

    def record(self, row):
        require(row['schema'] == 'mr3-peer-phase-audit-v1' and row['epoch'] == self.epoch,
                'peer ledger schema/epoch')
        require(type(row['record_sequence']) is int
                and row['record_sequence'] == self.record_sequence + 1, 'peer record sequence')
        self.record_sequence += 1
        integer(row['clock_ns'], 'peer actual clock')
        wall = integer(row['wall_monotonic_ns'], 'peer record wall', 1)
        kind, value = row['kind'], row['payload']
        if kind == 'configuration':
            require(
                not self.configured and self.record_sequence == 1,
                'peer configuration first/unique')
            require(value['stepped_mode'] is True and canonical(value['tf_source_lead_sec'])
                    == canonical(.2), 'peer stepped/source contract')
            same(
                value['input_topics'],
                {kind + ':' + robot: '/mr3/received/' + robot + '/' + kind
                 for kind in ('odom', 'tf') for robot in ROBOTS},
                'peer received-only actual topics')
            self.configured = True
            return
        require(self.configured, 'missing peer configuration')
        if kind in ('received_odom', 'received_tf'):
            source = kind.split('_')[1]
            robot = value['robot']
            require(robot in ROBOTS, 'peer input robot')
            key = source, robot
            seq = integer(value['input_sequence'], 'peer input sequence', 1)
            require(seq == self.input_sequences[key] + 1, 'peer input sequence gap')
            self.input_sequences[key] = seq
            HELPERS.validate_raw(source, value['raw'])
            same(value['raw_sha256'], digest(value['raw']), 'peer original input SHA')
            same(value['topic'], '/mr3/received/' + robot + '/' + source, 'peer actual side topic')
            require(type(value['received_wall_monotonic_ns']) is int and 0 <
                    value['received_wall_monotonic_ns'] <= wall, 'peer input callback wall')
            self.inputs[key].append(value)
            self.inputs[key] = self.inputs[key][-32:]
        elif kind == 'received_state_bundle':
            same(value['message_sha256'], digest(value['message']), 'peer received bundle SHA')
            require(value['message']['epoch'] == self.epoch, 'peer actual bundle epoch')
            require(type(value['received_wall_monotonic_ns']) is int and 0 <
                    value['received_wall_monotonic_ns'] <= wall, 'peer bundle callback wall')
            self.bundles.append(value)
            self.bundles = self.bundles[-32:]
        elif kind == 'controlled':
            require(not self.controlled and value['operation']
                    == 'takeover', 'peer takeover unique')
            self.controlled = True
        elif kind == 'warmup_obstacles_published':
            require(not self.controlled, 'automatic peer publication after takeover')
            self.warmup_publications += 1
        elif kind == 'request_received':
            require(self.controlled, 'peer request before takeover')
            require(self.pending is None, 'peer overlapping requests')
            request = value
            require(request['schema'] == 'mr3-peer-phase-request-v1'
                    and request['epoch'] == self.epoch, 'peer request identity')
            integer(request['target_time_ns'], 'peer request target')
            identity = request['request_id']
            require(type(identity) is str and identity and identity not in self.requests,
                    'peer request identity reused')
            if request['operation'] == 'commit':
                state = self.state_acks.get(identity)
                require(state is not None, 'peer request lacks actual information ACK')
                same(request['state_commit'], state['ack'],
                     'peer borrowed/fabricated information ACK')
                require(state['publish_started_wall_monotonic_ns'] <= wall,
                        'peer request before real information ACK call')
                require(self.last_clock is None or request['target_time_ns'] > self.last_clock,
                        'peer normal clock repeated/regressed')
            else:
                require(request['operation'] == 'takeover' and 'state_commit' not in request,
                        'peer takeover request scope')
            self.requests[identity] = request
            self.request_walls[identity] = wall
            self.pending = request
            self.matched = self.publication = None
        elif kind == 'inputs_matched':
            require(self.pending is not None and row['clock_ns'] == self.pending['target_time_ns'],
                    'peer matching did not occur at exact target clock')
            self.match(value, wall)
        elif kind == 'obstacles_published':
            require(self.pending is not None and self.matched is not None,
                    'peer publication before actual source callbacks matched')
            same(value['request_id'], self.pending['request_id'], 'peer publication identity')
            same(
                row['clock_ns'],
                self.pending['target_time_ns'],
                'peer publish exact actual clock')
            require(self.publication is None, 'duplicate actual peer publication')
            expected = self.expected_publications
            publications = value['publications']
            require(len(publications) == 6
                    and {(p['robot'], p['kind']) for p in publications} == set(expected),
                    'six real peer outputs required')
            for item in publications:
                key = item['robot'], item['kind']
                topic = '/'+key[0]+('/peer_obstacles' if key[1] == 'scan' else '/peer_footprints')
                same(item['topic'], topic, 'actual obstacle topic')
                same(
                    item['payload'],
                    expected[key],
                    'actual obstacle fields/cloud bytes differ from original geometry')
                same(item['message_sha256'], digest(item['payload']), 'peer output metadata SHA')
                start = integer(item['publish_started_wall_monotonic_ns'], 'peer publish start', 1)
                end = integer(item['publish_completed_wall_monotonic_ns'], 'peer publish end', 1)
                require(self.match_wall <= start <= end <= wall, 'peer actual publish call window')
            self.publication = publications
        elif kind in ('ack_published', 'cached_ack_published'):
            self.ack(value, wall, kind == 'cached_ack_published')
        elif kind in ('invalid_phase_request', 'invalid_state_bundle'):
            raise ValueError('peer recorded invalid protocol input')
        else:
            raise ValueError('unknown peer audit kind ' + str(kind))

    def match(self, value, wall):
        require(self.pending is not None and self.pending['operation'] == 'commit',
                'peer input match without normal commit')
        same(value['request'], self.pending, 'peer input match request differs')
        state = self.pending['state_commit']
        refs, selected = value['inputs'], {}
        require(set(refs) == {'bundle'} | {k+':'+r for k in ('odom', 'tf') for r in ROBOTS},
                'peer match must contain bundle and six actual side refs')
        bundles = [
            b for b in self.bundles
            if b['message_sha256'] == state['bundle_sha256'] and
            canonical(b['message']['sequence']) ==
            canonical(state['state_sequence']) and b['received_wall_monotonic_ns'] >=
            state['bundle_publish_started_wall_monotonic_ns']]
        require(bundles, 'peer match has no actual current bundle receipt')
        bundle = bundles[-1]
        same(refs['bundle'], {'state_sequence': state['state_sequence'],
             'message_sha256': bundle['message_sha256'],
                              'received_wall_monotonic_ns': bundle['received_wall_monotonic_ns']},
             'peer actual bundle callback ref')
        require(set(state['robots']) == set(ROBOTS), 'peer state ACK three robot refs')
        rows = {row['name']: row for row in bundle['message']['robots']}
        require(set(rows) == set(ROBOTS), 'peer bundle three robots')
        for robot in ROBOTS:
            expected, actual = state['robots'][robot], rows[robot]
            require(actual['epoch'] == self.epoch and actual['valid'] is True,
                    'peer actual received robot invalid/epoch')
            for field in ('sequence', 'version', 'source_ns', 'odom_source_ns', 'tf_source_ns'):
                integer(expected[field], 'peer state reference ' + field, 1)
            for field in ('sequence', 'version'):
                same(actual[field], expected[field], 'peer bundle robot identity differs')
            for field in ('source', 'odom_source', 'tf_source'):
                same(HELPERS.seconds_ns(actual[field + '_stamp']), expected[field + '_ns'],
                     'peer bundle original source differs')
            require(
                expected['source_ns'] == min(
                    expected['odom_source_ns'],
                    expected['tf_source_ns']) and 0 <= self.pending['target_time_ns'] -
                expected['source_ns'] <= 500_000_000,
                'peer state source age/reference gate')
            for kind in ('odom', 'tf'):
                same(expected[kind + '_topic'], '/mr3/received/' + robot + '/' + kind,
                     'peer state side topic differs')
                candidates = [
                    v for v in self.inputs[kind, robot]
                    if v['raw_sha256'] ==
                    expected[kind + '_sha256'] and v['received_wall_monotonic_ns'] >=
                    state['side_publish_started_wall_monotonic_ns']]
                require(candidates, 'peer matched old/fabricated side callback')
                sample = candidates[-1]
                same(refs[kind+':'+robot], {key: sample[key] for key in (
                     'input_sequence', 'raw_sha256', 'received_wall_monotonic_ns')},
                     'peer actual side callback ref differs')
                require(HELPERS.header_ns(sample['raw']) - (200_000_000 if kind == 'tf' else 0)
                        == expected[kind+'_source_ns'], 'peer raw source stamp differs')
                selected[kind, robot] = sample
        self.matched = selected
        self.matched_refs = refs
        self.match_wall = wall
        self.expected_publications = expected_outputs(selected, self.pending['target_time_ns'])

    def ack(self, value, wall, cached):
        ack = value['ack']
        start = integer(value['publish_started_wall_monotonic_ns'], 'peer ACK start', 1)
        end = integer(value['publish_completed_wall_monotonic_ns'], 'peer ACK end', 1)
        require(start <= end <= wall, 'peer ACK publish window')
        require(ack['schema'] == 'mr3-peer-phase-ack-v1' and ack['epoch'] == self.epoch,
                'peer ACK schema/epoch')
        identity = ack['request_id']
        if cached:
            require(identity in self.acks, 'cached peer ACK not actually completed')
            same(ack, self.acks[identity]['ack'], 'cached peer ACK changed')
            return
        require(self.pending is not None, 'unsolicited peer ACK')
        request = self.pending
        require(type(ack['ok']) is bool and ack['request_id'] == request['request_id']
                and ack['operation'] == request['operation'], 'peer ACK request identity')
        same(ack['target_time_ns'], request['target_time_ns'], 'peer ACK target identity')
        require(type(ack['clock_ns']) is int, 'peer ACK clock type')
        if ack['ok']:
            require(ack['clock_ns'] == request['target_time_ns'], 'peer ACK actual exact clock')
            if ack['operation'] == 'commit':
                require(self.publication is not None,
                        'peer success ACK before six actual publish calls')
                same(ack['state_commit'], request['state_commit'], 'peer ACK state substitution')
                same(
                    ack['state_sequence'],
                    request['state_commit']['state_sequence'],
                    'peer state sequence')
                same(
                    ack['bundle_sha256'],
                    request['state_commit']['bundle_sha256'],
                    'peer bundle SHA')
                same(ack['inputs'], self.matched_refs, 'peer ACK actual input refs mismatch')
                same(ack['publications'], self.publication, 'peer ACK actual outputs mismatch')
                same(ack['obstacle_publication_sha256'], digest(
                    self.publication), 'peer outputs composite SHA')
                self.commit_sequence += 1
                same(ack['commit_sequence'], self.commit_sequence, 'peer commit sequence')
                same(ack['scope'], 'actual_obstacle_publish_calls_returned', 'peer ACK scope')
                require(all(p['publish_completed_wall_monotonic_ns'] <= start
                            for p in self.publication),
                        'peer ACK published before obstacles returned')
                self.last_clock = ack['clock_ns']
            else:
                same(ack['scope'], 'automatic_obstacle_timer_disabled', 'peer takeover scope')
        else:
            require(type(ack.get('error')) is str and ack['error'], 'peer negative ACK reason')
        self.acks[identity] = {'ack': ack, 'request': request,
                               'request_wall': self.request_walls[identity],
                               'publish_started_wall_monotonic_ns': start,
                               'publish_completed_wall_monotonic_ns': end}
        self.pending = None

    def finish(self):
        require(self.configured and self.controlled and self.commit_sequence > 0,
                'no actual controlled peer commits')
        return {'commits': self.commit_sequence, 'warmup_publications': self.warmup_publications,
                'raw_inputs': dict((kind+':'+robot, self.input_sequences[kind, robot])
                                   for kind in ('odom', 'tf') for robot in ROBOTS)}


def valid_output(value):
    require(type(value) is dict and set(value) == {"linear_x", "angular_z"},
            "motion output shape")
    for key, limit in (("linear_x", .26), ("angular_z", .8)):
        require(type(value[key]) is float and math.isfinite(value[key])
                and abs(value[key]) <= limit, "motion output finite typed hard limit")


def validate_status(status, epoch):
    require(status["schema"] == "mr3-motion-safety-status-v1" and status["epoch"] == epoch,
            "motion status identity")
    integer(status["clock_ns"], "status clock")
    require(type(status["ready"]) is bool and status["completion_scope"]
            == "publication_and_local_topic_receipt", "motion status completion scope")
    require(set(status["decision_sequences"]) == set(status["outputs"]) == set(ROBOTS),
            "status needs three robots")
    for robot in ROBOTS:
        integer(status["decision_sequences"][robot], "status decision sequence", 1)
        valid_output(status["outputs"][robot])
    stop = status.get("phase_kind") == "stop"
    if "phase_kind" in status:
        require(stop and status["ready"] is False, "only explicit permanent stop category")
        same(status["outputs"], {r: {"linear_x": 0., "angular_z": 0.} for r in ROBOTS},
             "permanent stop must be strict three zero")
    return stop


def status_key(status):
    return status["clock_ns"], "stop" if status.get("phase_kind") == "stop" else "normal"


class MotionReplay:
    """Actual guard callback/order and local Twist consumption, without guard maths."""

    def __init__(self, epoch, state_acks, peer_acks):
        self.epoch, self.state_acks, self.peer_acks = epoch, state_acks, peer_acks
        self.decisions, self.observed = {}, {}
        self.decision_received = {}
        self.completed, self.acks, self.requests = {}, {}, {}
        self.dependencies, self.received = {}, None
        self.commit_records = {}
        self.last_sequences = dict.fromkeys(ROBOTS, 0)
        self.stop_seen = False
        self.first_stop_wall = None
        self.takeovers = 0
        self.release = []
        self.controlled = False
        self.current_request = None
        self.record_sequence = 0
        self.output_pending = defaultdict(list)
        self.stop_cause = False

    def record(self, row):
        require(row["epoch"] == self.epoch and row["schema"] == "mr3-motion-safety-v1",
                "motion raw schema/epoch")
        require(type(row['record_sequence']) is int
                and row['record_sequence'] == self.record_sequence + 1,
                'motion raw record sequence gap/reorder')
        self.record_sequence += 1
        wall = integer(row["wall_monotonic_ns"], "motion callback wall", 1)
        kind, value = row["kind"], row["payload"]
        require(kind not in ('control_failure', 'invalid_received_states',
                             'clock_changed_during_decision'),
                'actual recorded control protocol failure: ' + kind)
        if kind in (
            'failure',
            'terminal',
            'stop_request',
            'settled_turn_model_failure',
                'control_failure'):
            self.stop_cause = True
        if kind == "release":
            self.release.append((HELPERS.seconds_ns(value["stamp"]), wall))
        elif kind == "received_states":
            self.received = value
        elif kind == "control_dependency":
            component, ack = value["component"], value["value"]
            require(component in ("state", "peer"), "guard dependency component")
            actual = (self.state_acks if component == "state" else self.peer_acks).get(
                ack["request_id"])
            require(actual is not None, "guard fabricated dependency callback")
            same(ack, actual["ack"], "guard substituted actual dependency")
            require(actual["publish_started_wall_monotonic_ns"] <= wall,
                    "guard dependency callback precedes actual publish start")
            self.dependencies[component, ack["request_id"]] = (ack, wall)
        elif kind == "control_request":
            request = value
            identity = request["request_id"]
            require(request["epoch"] == self.epoch and request["schema"]
                    == "mr3-motion-control-request-v1", "guard request identity")
            if identity in self.requests:
                same(request, self.requests[identity][0], "guard request identity changed")
            else:
                self.requests[identity] = (request, wall)
                self.current_request = request
            if request['operation'] == 'stop':
                self.stop_cause = True
            if request["operation"] == "takeover":
                self.controlled = True
                self.takeovers += 1
        elif kind == "control_commit":
            request = value["request"]
            identity = request["request_id"]
            require(identity in self.requests, "guard commit before actual request callback")
            same(request, self.requests[identity][0], "guard commit request changed")
            self.check_dependencies(request, wall)
            require(identity not in self.commit_records, "guard normal commit repeated")
            self.commit_records[identity] = wall
        elif kind == "decision":
            robot = value["robot"]
            require(robot in ROBOTS, "guard decision robot")
            seq = integer(value["decision_sequence"], "decision sequence", 1)
            require(seq == self.last_sequences[robot] + 1, "guard decision sequence discontinuity")
            self.last_sequences[robot] = seq
            output = value["decision"]["output"]
            require(type(output) is list and len(output) == 2, "guard output vector")
            valid_output({"linear_x": output[0], "angular_z": output[1]})
            stop = value.get("phase_kind") == "stop"
            require(not self.stop_seen or stop, "normal output after permanent stop")
            if not stop and self.controlled:
                request = self.current_request
                require(request is not None and request['target_time_ns'] == value['clock_ns'],
                        'controlled normal decision lacks its actual exact-clock request')
                if request['operation'] == 'takeover':
                    same(output, [0., 0.], 'takeover may only issue strict zero')
                else:
                    self.check_dependencies(request, wall)
            if stop:
                require(self.stop_cause, 'permanent stop without actual recorded trigger/request')
                same(output, [0., 0.], "stop decision output is nonzero")
                self.stop_seen = True
                if self.first_stop_wall is None:
                    self.first_stop_wall = wall
            self.decisions[robot, seq] = (value, wall)
            self.output_pending[robot].append(seq)
            self.decision_received[robot, seq] = digest(
                self.received) if self.received is not None else None
        elif kind == "actual_cmd_vel":
            robot, seq = value["robot"], value["observed_decision_sequence"]
            require((robot, seq) in self.decisions, "local actual receipt without prior decision")
            require(self.output_pending[robot] and self.output_pending[robot].pop(0) == seq,
                    'actual local Twist did not consume decision FIFO')
            decision, _ = self.decisions[robot, seq]
            require((robot, seq) not in self.observed, "local decision receipt repeated")
            output = decision["decision"]["output"]
            expected = {"linear": {"x": output[0], "y": 0., "z": 0.},
                        "angular": {"x": 0., "y": 0., "z": output[1]}}
            same(value["twist"], expected, "actual local Twist differs from filtered guard output")
            identity = value["publisher_identity"]
            require(identity["valid"] is True and identity["scope"] == "graph_at_callback"
                    and identity["topic"] == "/" + robot + "/cmd_vel",
                    "actual local output publisher graph identity")
            endpoints = identity["endpoints"]
            require(len(endpoints) == 1 and endpoints[0]["namespace"] == "/"
                    and endpoints[0]["node"] == "motion_safety", "actual output sole publisher")
            self.observed[robot, seq] = wall
        elif kind == "output_completed":
            status = value["status"]
            stop = validate_status(status, self.epoch)
            start = integer(value["publish_started_wall_monotonic_ns"], "status pub start", 1)
            end = integer(value["publish_completed_wall_monotonic_ns"], "status pub end", 1)
            require(start <= end <= wall, "actual status publish call window")
            for robot in ROBOTS:
                seq = status["decision_sequences"][robot]
                require((robot, seq) in self.observed and self.observed[robot, seq] <= start,
                        "output completed before all three actual local receipts")
                decision, _ = self.decisions[robot, seq]
                same(decision["clock_ns"], status["clock_ns"], "status/decision exact clock")
                same(decision["decision"]["output"], [status["outputs"][robot]["linear_x"],
                     status["outputs"][robot]["angular_z"]], "status/decision output differs")
                require((decision.get("phase_kind") == "stop") == stop,
                        "status replaced normal category with stop or reverse")
                require(type(decision["ready"]) is bool and (stop or
                        decision["ready"] == status["ready"]), "normal ready status differs")
            key = status_key(status)
            require(key not in self.completed,
                    "motion status overwritten within same clock/category")
            if stop and (key[0], "normal") in self.completed:
                normal = self.completed[key[0], "normal"]["status"]
                require(all(status["decision_sequences"][r] > normal["decision_sequences"][r]
                            for r in ROBOTS), "stop does not supersede normal sequences")
            self.completed[key] = {"status": status, "start": start, "end": end}
        elif kind in ("control_ack_published", "control_cached_ack_published"):
            self.ack(value, wall, kind == "control_cached_ack_published")

    def check_dependencies(self, request, wall):
        identity, target = request["request_id"], request["target_time_ns"]
        require(request["operation"] == "commit", "normal guard commit operation")
        for component in ("state", "peer"):
            actual = self.dependencies.get((component, identity))
            require(actual is not None and actual[1] <= wall,
                    "guard decision did not actually receive current dependency")
            expected = request[component + "_commit"]
            same(actual[0], expected, "guard borrowed another clock dependency")
            require(expected["target_time_ns"] == expected["clock_ns"] == target
                    and expected["ok"] is True, "guard dependency exact successful clock")
        same(request["peer_commit"]["state_commit"], request["state_commit"],
             "guard state/peer commits differ")
        require(self.received is not None, "guard lacks actual received bundle callback")
        same(digest(self.received), request["state_commit"]["bundle_sha256"],
             "guard actual received bundle differs from state commit")
        same(self.received["sequence"], request["state_commit"]["state_sequence"],
             "guard received bundle sequence differs")

    def ack(self, value, wall, cached):
        ack = value["ack"]
        start = integer(value["publish_started_wall_monotonic_ns"], "motion ACK start", 1)
        end = integer(value["publish_completed_wall_monotonic_ns"], "motion ACK end", 1)
        require(start <= end <= wall, "motion ACK actual publication window")
        identity = ack["request_id"]
        require(ack["schema"] == "mr3-motion-control-ack-v1" and ack["epoch"] == self.epoch,
                "motion ACK schema/epoch")
        if identity in self.acks:
            require(cached, "motion ACK completed twice without cache")
            same(ack, self.acks[identity]["ack"], "immutable normal/stop ACK changed")
            return
        require(not cached and identity in self.requests,
                "motion ACK without real request callback")
        request, request_wall = self.requests[identity]
        require(request_wall <= start and type(ack["ok"]) is bool
                and ack["operation"] == request["operation"], "motion ACK request identity")
        same(ack["target_time_ns"], request["target_time_ns"], "motion ACK target mismatch")
        if ack["ok"]:
            status = ack["status"]
            stop = validate_status(status, self.epoch)
            same(status["clock_ns"], ack["clock_ns"], "motion ACK/status clock")
            same(ack["clock_ns"], request["target_time_ns"], "motion ACK actual exact clock")
            complete = self.completed.get(status_key(status))
            require(complete is not None and complete["end"] <= start,
                    "motion ACK before actual status completion")
            same(status, complete["status"], "motion ACK substituted status")
            if request["operation"] == "takeover":
                require(not stop, "takeover cannot borrow permanent stop")
                same(status["outputs"], {r: {"linear_x": 0., "angular_z": 0.} for r in ROBOTS},
                     "takeover requires actual three-zero status")
            elif not stop:
                require(identity in self.commit_records, "normal ACK without dependency commit")
                for robot in ROBOTS:
                    _, decision_wall = self.decisions[robot, status["decision_sequences"][robot]]
                    same(self.decision_received[robot, status["decision_sequences"][robot]],
                         request["state_commit"]["bundle_sha256"],
                         "normal decision preceded actual current bundle callback")
                    require(request_wall <= decision_wall and all(
                        self.dependencies[c, identity][1] <= decision_wall
                        for c in ("state", "peer")),
                        "normal decision before actual request/dependency callbacks")
        else:
            require(type(ack.get("error")) is str and ack["error"], "negative motion ACK reason")
        self.acks[identity] = {"ack": ack, "request": request, "request_wall": request_wall,
                               "publish_started_wall_monotonic_ns": start,
                               "publish_completed_wall_monotonic_ns": end}


class ControlReplay:
    def __init__(self, epoch, component_acks, motion):
        self.epoch, self.component_acks, self.motion = epoch, component_acks, motion
        self.requests, self.received, self.consumed = {}, {}, {}
        self.pending = None
        self.stopped = False
        self.stop_observed = []
        self.stopped_at = []

    def record(self, row):
        require(row["schema"] == "mr3-controlled-execution-phase-v1"
                and row["epoch"] == self.epoch, "worker control schema/epoch")
        wall = integer(row["wall_monotonic_ns"], "worker control wall", 1)
        target = integer(row["worker_physical_ns"], "worker physical paused clock")
        integer(row["worker_clock_ns"], "worker actual clock")
        kind = row["kind"]
        if kind in ("request", "ack_consumed", "ack_rejected"):
            require(row["worker_clock_ns"] == target,
                    "worker consumption is not exact paused clock")
        if kind == "request":
            component, request = row["component"], row["request"]
            require(component in ("state", "peer", "motion"), "worker component")
            require(request["epoch"] == self.epoch and type(request["target_time_ns"]) is int
                    and request["target_time_ns"] == target, "worker request exact epoch/clock")
            identity, operation = request["request_id"], request["operation"]
            require(type(identity) is str and identity, "worker request identity")
            key = component, identity
            require(key not in self.requests, "worker reused completed request identity")
            if self.pending is not None:
                require(component == "motion" and operation == "stop",
                        "overlapping non-stop worker requests")
                self.pending = None
            require(not self.stopped or operation == "stop", "normal request after permanent stop")
            if operation == "stop":
                self.stopped_at.append(wall)
                require(component == "motion", "only motion may stop")
                self.stopped = True
            elif operation == "commit":
                if component == "peer":
                    previous = self.consumed.get(("state", identity))
                    require(previous is not None and previous[1] <= wall,
                            "peer request before actual state ACK consumed")
                    same(request["state_commit"], previous[0], "worker peer state substitution")
                elif component == "motion":
                    for dependency in ("state", "peer"):
                        previous = self.consumed.get((dependency, identity))
                        require(previous is not None and previous[1] <= wall,
                                "motion request before actual peer/state ACK consumed")
                        same(request[dependency+"_commit"], previous[0],
                             "worker motion dependency substitution")
            else:
                require(operation == "takeover", "worker request operation")
            self.requests[key] = request, wall
            self.pending = key
        elif kind == "ack_received":
            component, ack = row["component"], row["ack"]
            if ack.get("epoch") != self.epoch:
                return  # Actual ignored callback, never eligible for consume/physics.
            key = component, ack["request_id"]
            require(key in self.requests, "worker ACK callback before own request")
            actual = self.component_acks.get(component, {}).get(ack["request_id"])
            require(actual is not None, "worker fabricated component ACK callback")
            same(ack, actual["ack"], "worker ACK differs from actual published bytes")
            same(self.requests[key][0], actual["request"], "actual node received another request")
            require(self.requests[key][1] <= actual["request_wall"],
                    "component request callback precedes actual worker request")
            same(ack["operation"], self.requests[key][0]["operation"],
                 "worker ACK operation differs from request")
            require(actual["publish_started_wall_monotonic_ns"] <= wall,
                    "worker ACK callback before actual publication started")
            if self.pending == key:
                same(ack["target_time_ns"], target, "worker callback borrowed future/old ACK")
                same(row["worker_clock_ns"], target, "pending ACK callback outside paused clock")
            require(self.requests[key][1] <= wall, "ACK before real worker request")
            if (component == 'motion' and ack.get('status', {}).get('phase_kind') == 'stop'):
                self.stopped_at.append(wall)
            self.received[key] = ack, wall
        elif kind in ("ack_consumed", "ack_rejected"):
            component, ack = row["component"], row["ack"]
            key = component, ack["request_id"]
            require(self.pending == key and key in self.received,
                    "worker consumed ACK without matching actual callback")
            actual, received_wall = self.received[key]
            same(ack, actual, "worker consumed changed ACK")
            require(received_wall <= wall and type(ack["ok"]) is bool,
                    "worker consume precedes callback")
            require((kind == "ack_consumed") == ack["ok"], "worker accepted a failed ACK")
            if kind == 'ack_rejected':
                require(component == 'state' and ack.get('error') == 'state_phase_task_terminal'
                        and type(ack.get('terminal_notice')) is dict
                        and ack.get('scope') == 'terminal_cancelled_uncommitted_state_phase',
                        'nonterminal execution phase rejection is a real control failure')
            if kind == 'ack_consumed':
                same(ack["clock_ns"], target, "worker consumed nonexact clock")
            else:
                require(type(ack['clock_ns']) is int and 0 <= ack['clock_ns'] <= target,
                        'actual terminal cancellation clock exceeds target')
            if kind == "ack_consumed":
                self.consumed[key] = ack, wall
                if component == "motion" and ack["status"].get("phase_kind") == "stop":
                    self.stopped_at.append(wall)
                    self.stopped = True
            self.pending = None
        elif kind == "stop_observed":
            status = row["status"]
            require(validate_status(status, self.epoch), "stop observed contains normal status")
            actual = self.motion.completed.get(status_key(status))
            require(actual is not None and actual["start"] <= wall,
                    "worker stop notification before actual stop publication")
            same(status, actual["status"], "worker stop notification substituted status")
            require(row["origin"] in ("stop_topic", "control_ack")
                    and type(row["duplicate"]) is bool, "stop callback origin/duplicate type")
            same(row['duplicate'], any(canonical(s) == canonical(status)
                                       for s, _ in self.stop_observed),
                 'stop duplicate flag differs')
            if row['origin'] == 'control_ack':
                require(any(component == 'motion'
                            and canonical(ack.get('status')) == canonical(status)
                            and consumed_wall <= wall for (component, _), (ack, consumed_wall)
                            in self.consumed.items()),
                        'stop control ACK origin has no actual consumed ACK')
            self.stopped = True
            self.stop_observed.append((status, wall))
            self.stopped_at.append(wall)
        elif kind == "terminal_cancelled":
            self.stopped_at.append(wall)
            require(row["ack"]["ok"] is False and row["ack"]["error"]
                    == "state_phase_task_terminal", "invalid terminal cancellation")
            self.stopped = True
        else:
            raise ValueError("unknown worker control event " + str(kind))


def native_receipts(rows, epoch, robot):
    result = {}
    for row in rows:
        require(row["epoch"] == epoch and row["robot"] == robot, "native driver identity")
        if row["kind"] != "command_received":
            continue
        seq = integer(row["cmd_seq"], "native actual command sequence", 1)
        require(seq not in result, "native command sequence repeated")
        result[seq] = {"schema": "mr3-drive-target-consumed-v1", "epoch": epoch, "robot": robot,
                       "clock_ns": row["sim_time_ns"],
                       "source_clock_ns": row["target_clock_ns"],
                       "decision_sequence": row["target_decision_sequence"],
                       "cmd_seq": seq, "linear_x": row["desired_v"], "angular_z": row["desired_w"]}
    return result


def audit_advances(rows, physical, epoch, control, native, release):
    received, latest, consumed, permits, completed = {}, {}, {}, {}, {}
    bootstrap, normal, stops, alignments = 0, 0, 0, 0
    source_stop_overlaps = []
    takeover = {c: [(k, v) for k, v in control.consumed.items()
                    if k[0] == c and v[0]["operation"] == "takeover"]
                for c in ("state", "peer", "motion")}
    require(all(len(values) == 1 for values in takeover.values()),
            "exactly three actual takeovers required")
    for row in rows:
        require(row["epoch"] == epoch, "drive worker cross epoch")
        wall = integer(row["wall_monotonic_ns"], "drive worker wall", 1)
        kind = row["kind"]
        if kind == "ack_received":
            ack, robot = row["ack"], row["topic_robot"]
            require(robot in ROBOTS and ack["robot"] == robot,
                    "drive callback subscribed robot differs")
            if ack.get("epoch") != epoch:
                continue
            expected = native[robot].get(ack["cmd_seq"])
            require(expected is not None, "drive callback lacks actual native stored command")
            same(ack, expected, "drive callback/storage identity or value differs")
            previous = latest.get(robot)
            require(
                previous is None or ack["cmd_seq"] >= previous["cmd_seq"],
                "drive callback sequence regressed")
            latest[robot] = ack
            received[robot, ack["cmd_seq"]] = ack, wall
        elif kind == "ack_consumed":
            motion, receipts = row["expected_motion"], row["receipts"]
            validate_status(motion, epoch)
            require(set(receipts) == set(ROBOTS), "three drive receipts required")
            for robot in ROBOTS:
                ack = receipts[robot]
                actual = received.get((robot, ack["cmd_seq"]))
                require(actual is not None and actual[1] <= wall,
                        "native target consumed without actual prior callback")
                same(ack, actual[0], "native consumed ACK changed")
                same(ack, latest[robot], "native old cache used after newer target storage")
                same(
                    ack["decision_sequence"],
                    motion["decision_sequences"][robot],
                    "native wrong guard seq")
                same(ack["source_clock_ns"], motion["clock_ns"], "native wrong source clock")
                same(ack["clock_ns"], motion["clock_ns"], "native not stored at paused clock")
                same({k: ack[k] for k in ("linear_x", "angular_z")}, motion["outputs"][robot],
                     "native stored wrong filtered output")
            consumed[digest(motion)] = receipts, wall
        elif kind == "advance_permitted":
            motion, receipts = row["expected_motion"], row["receipts"]
            validate_status(motion, epoch)
            start, steps = row["start_time_ns"], row["steps"]
            require(type(start) is int and type(steps) is int and 0 < steps <= 20,
                    "positive physical permission clock/steps")
            require(row["worker_physical_ns"] == row["worker_clock_ns"] == start ==
                    motion["clock_ns"], "physics permission is not exact paused clock")
            previous = consumed.get(digest(motion))
            require(
                previous is not None and previous[1] <= wall,
                "physics before native three receipts consumed")
            same(receipts, previous[0], "physics substituted native receipts")
            require(all(canonical(receipts[r]) == canonical(latest[r]) for r in ROBOTS),
                    "physics used old native cached target after change")
            category, identity = row.get("control_kind"), row.get("control_request_id")
            require(category in ("normal", "bootstrap_zero", "stop"),
                    "unclassified controlled physics permission")
            key = "motion", identity
            ack = control.consumed.get(key)
            require(ack is not None and ack[1] <= wall,
                    "physics before real motion control ACK consumed")
            same(ack[0]["status"], motion,
                 "physics status differs from consumed motion control ACK")
            if category != 'stop':
                require(not any(stopped <= wall for stopped in control.stopped_at),
                        'positive non-stop physics after worker actually processed stop')
                if (control.motion.first_stop_wall is not None
                        and control.motion.first_stop_wall <= wall):
                    source_stop_overlaps.append({
                        'request_id': row['request_id'], 'permit_wall_ns': wall,
                        'guard_first_stop_wall_ns': control.motion.first_stop_wall,
                        'control_kind': category})
            if category == "bootstrap_zero":
                bootstrap += 1
                require(bootstrap == 1 and steps == 20 and start < release,
                        "bootstrap must be unique pre-release twenty ticks")
                require(ack[0]["operation"] == "takeover" and all(
                    values[0][0][1] == identity and values[0][1][1] <= wall
                    and values[0][1][0]["target_time_ns"] == start
                    for values in takeover.values()),
                    "bootstrap lacks three same-clock takeovers")
                same(motion["outputs"], {r: {"linear_x": 0., "angular_z": 0.} for r in ROBOTS},
                     "bootstrap borrowed nonzero output")
            elif category == "normal":
                require(
                    not any(
                        w <= wall for _,
                        w in control.stop_observed),
                    "normal physics after permanent stop")
                require(ack[0]["operation"] == "commit" and motion["ready"] is True
                        and "phase_kind" not in motion, "normal physics lacks ready fresh chain")
                for component in ("state", "peer"):
                    dependency = control.consumed.get((component, identity))
                    require(dependency is not None and dependency[1] <= ack[1],
                            "normal physics lacks consumed state/peer chain")
                normal += 1
            else:
                require(
                    motion.get("phase_kind") == "stop" and any(
                        canonical(s) == canonical(motion) and w <= wall for s,
                        w in control.stop_observed),
                    "stop physics without actual permanent stop notification")
                stops += 1
            require(row["request_id"] not in permits and row["request_id"] not in completed,
                    "physical permission repeated or after actual completion")
            permits[row["request_id"]] = row
        elif kind == "physics_completed":
            receipt = row["receipt"]
            identity = receipt["request_id"]
            require(identity not in completed, "physical completion identity repeated")
            if identity in permits:
                require(permits[identity]['wall_monotonic_ns'] <= wall,
                        'physics completion before actual permission')
            completed[identity] = receipt
    require(len({r['request_id'] for r in physical}) == len(physical)
            and set(completed) == {r['request_id'] for r in physical},
            'physical helper file/completion trace identity coverage differs')
    require(bootstrap == 1 and normal > 0,
            "missing bootstrap or actual controlled normal advances")
    for receipt in physical:
        identity = receipt["request_id"]
        require(identity in completed, "physical receipt lacks real helper completion trace")
        same(receipt, completed[identity], "physical file/worker helper receipt differs")
        require(receipt["epoch"] == epoch and receipt["ok"] is True and receipt["paused"] is True,
                "physical receipt identity/status")
        ticks = integer(receipt["end_iterations"], "physical end iterations") - integer(
            receipt["start_iterations"], "physical start iterations")
        require(
            ticks >= 0 and receipt["end_time_ns"] -
            receipt["start_time_ns"] == ticks *
            1_000_000,
            "physical time/iteration mismatch")
        if ticks == 0:
            continue
        permission = permits.get(identity)
        if permission is None:
            require(ticks == 1 and receipt["end_time_ns"] < release
                    and receipt["end_time_ns"] <= takeover["motion"][0][1][0]["target_time_ns"],
                    "positive physics missing normal/stop/bootstrap permission")
            alignments += 1
            require(alignments <= 50, "pre-control one-tick alignment exceeded old bound")
        else:
            require(permission["start_time_ns"] == receipt["start_time_ns"] and permission
                    ["steps"] == ticks, "permission differs from actual physical advance")
    require(set(permits) <= {r["request_id"]
            for r in physical}, "permission without real physical completion")
    initial = [(ack, wall) for (component, _), (ack, wall) in control.consumed.items()
               if component == "motion" and ack["operation"] == "commit"
               and ack.get("status", {}).get("phase_kind") != "stop"
               and ack["status"]["clock_ns"] == release]
    require(len(initial) == 1 and initial[0][1] <= control.motion.release[0][1],
            "task release before its first actual fresh normal controlled chain")
    return {
        "bootstrap_zero_advances": bootstrap,
        "normal_advances": normal,
        "permanent_stop_advances": stops,
        "precontrolled_alignment_ticks": alignments,
        "source_stop_before_nonstop_permit_diagnostic_only": source_stop_overlaps,
        "scope": ("actual publications, local topic receipts and driver target storage; "
                  "not body stop or Nav2 consumption")}


def audit_episode(directory, freeze, peer_only=False):
    inputs = HELPERS.Inputs()
    result = {"episode": str(directory), "passed": False, "errors": [], "inputs": inputs.bindings}
    try:
        metadata = HELPERS.parse(inputs.read(directory, "metadata.json"))
        require(metadata["freeze"] == freeze, "episode source freeze differs")
        epoch = metadata["epoch"]
        require(type(epoch) is str and epoch, "episode epoch")
        result["epoch"] = epoch
        inputs.read(directory, "summary.json")
        inputs.read(directory, "transitions.jsonl")
        physical = inputs.rows(directory, "physics.jsonl")
        require(physical, "no actual physical helper receipts")
        result["physics_end_ns"] = max(integer(p["end_time_ns"], "physical end") for p in physical)
        information = inputs.rows(directory, "information_states.jsonl")
        state_acks = information_acks(information, epoch)
        peer = PeerReplay(epoch, state_acks)
        for number, row in enumerate(inputs.rows(directory, "peer_phase.jsonl"), 1):
            try:
                peer.record(row)
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                raise ValueError("peer line " + str(number) + ": " + str(error)) from error
        result["peer"] = peer.finish()
        if not peer_only:
            motion = MotionReplay(epoch, state_acks, peer.acks)
            motion_rows = inputs.rows(directory, "motion_safety.jsonl")
            for number, row in enumerate(motion_rows, 1):
                try:
                    motion.record(row)
                except (ValueError, KeyError, TypeError, OverflowError) as error:
                    raise ValueError("motion line " + str(number) + ": " + str(error)) from error
            require(len(motion.release) == 1, "missing/duplicate actual task release")
            release = motion.release[0][0]
            result["task_release_ns"] = release
            require(release <= result["physics_end_ns"], "task release beyond actual physics end")
            control = ControlReplay(epoch, {"state": state_acks, "peer": peer.acks,
                                            "motion": motion.acks}, motion)
            for number, row in enumerate(inputs.rows(directory, "control_phase_worker.jsonl"), 1):
                try:
                    control.record(row)
                except (ValueError, KeyError, TypeError, OverflowError) as error:
                    raise ValueError(
                        "worker control line " +
                        str(number) +
                        ": " +
                        str(error)) from error
            native = {robot: native_receipts(inputs.rows(directory, "drive_" + robot + ".jsonl"),
                                             epoch, robot) for robot in ROBOTS}
            result["control"] = audit_advances(inputs.rows(directory, "drive_phase_worker.jsonl"),
                                               physical, epoch, control, native, release)
            result["normal_motion_clocks"] = sum(key[1] == "normal" for key in motion.completed)
            result["permanent_stop_motion_clocks"] = sum(
                key[1] == "stop" for key in motion.completed)
        result["passed"] = True
    except (ValueError, KeyError, TypeError, OverflowError, OSError, AssertionError) as error:
        result["errors"].append(str(error))
    try:
        inputs.verify()
    except (ValueError, OSError) as error:
        result["passed"] = False
        result["errors"].append(str(error))
    return result


def audit(directory, freeze, peer_only=False):
    if (directory / "metadata.json").is_file() or (directory / "metadata.json.gz").is_file():
        episodes = [directory]
    else:
        episodes = sorted(path for path in directory.glob("worker*/episode*") if path.is_dir())
    results = [audit_episode(path, freeze, peer_only) for path in episodes]
    return {
        "schema": "mr3-independent-controlled-execution-review-v1",
        "freeze": freeze,
        "consumer_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "independent_helper_sha256": HELPER_SHA,
        "root": str(directory),
        "mode": "peer_only" if peer_only else "full_control_including_peer",
        "passed": bool(results) and all(
            item["passed"] for item in results),
        "episodes": results,
        "errors": [] if results else ["no episode directories"],
        "criteria": {
                "original_peer_body_gate_m": .5,
                "original_peer_source_age_sec": .5,
                "actual_bundle_and_six_side_callbacks": True,
                "original_scan_fields_and_cloud_data_sha": True,
                "actual_obstacle_publish_calls_before_peer_ack": True,
                "normal_chain_before_each_controlled_positive_physics": not peer_only,
                "unique_pre_release_twenty_tick_zero_bootstrap": not peer_only,
                "permanent_stop_is_separate_strict_zero_not_freshness_credit": not peer_only,
                "three_actual_native_target_storage_receipts": not peer_only},
        "limitations": [
            "Publication-call ACKs do not establish Nav2 obstacle consumption.",
            "Native storage ACKs do not establish actuator execution or body rest.",
            "A guard-source stop whose DDS notification is still in flight is diagnosed; "
            "the worker prefix gate begins at its actual stop receipt or stop request. "
            "This is not a cross-process atomic or zero-latency stop claim. "
            "Original at-most20ms terminal drain and160ms driver response gates remain mandatory.",
            "Original information, driver160ms, guard mathematical, physical, "
            "contact, activity, shutdown and task audits remain separate mandatory gates.",
            "Two modes of this same reader are overlapping evidence, "
            "not independent replications."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--peer-only", action="store_true")
    args = parser.parse_args()
    result = audit(args.directory, args.freeze, args.peer_only)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "mode": result["mode"], "episodes": len(
        result["episodes"]), "output": str(args.output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
