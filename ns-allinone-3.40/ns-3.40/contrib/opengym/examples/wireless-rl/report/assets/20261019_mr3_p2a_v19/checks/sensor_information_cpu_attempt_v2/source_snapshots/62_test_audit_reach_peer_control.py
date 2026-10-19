"""Independent synthetic v2 protocol fixtures; no plant/native qualification."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from mr3_learning import audit_reach_peer_control as audit
from mr3_learning.tests import test_audit_reach_information as sample

NAMES = audit.ROBOTS
EPOCH, FREEZE = sample.EPOCH, sample.FREEZE
T0, RELEASE, FINAL = 1_000_000_000, sample.CLOCK, sample.CLOCK + 20_000_000


def odom(name):
    value = sample.raw_odom()
    value['pose']['pose']['position']['x'] = float(NAMES.index(name) * 2.)
    return value


def graph_twist(name, owner='motion_safety'):
    output = owner == 'motion_safety'
    return {'scope': 'graph_at_callback', 'topic': f'/{name}/cmd_vel' if output else f'/{name}/cmd_vel_unguarded',
            'valid': True, 'endpoints': [{'namespace': '/' if output else '/' + name,
            'node': owner, 'topic_type': 'geometry_msgs/msg/Twist', 'endpoint_gid': '39' * 24}]}


def twist(v=0., w=0.):
    return {'linear': {'x': v, 'y': 0., 'z': 0.}, 'angular': {'x': 0., 'y': 0., 'z': w}}


def make_fixture():
    """A whole decoded evidence chain with zero actions and real protocol facts.

    Physics and all payloads here are declared synthetic test inputs; successful
    replay cannot establish actual source, dynamics, task success or admission.
    """
    core, _ = audit.load_impl(); host, _ = audit.load_implementation()
    base = host.BASE
    raw = sample.fixture()
    info = copy.deepcopy(raw['information_states.jsonl'])
    for row in info:
        kind, value = row['kind'], row['payload']
        if kind == 'odom_ingress':
            value['raw'] = odom(value['robot']); value['raw_sha256'] = audit.sha(value['raw'])
        elif kind == 'calibration_ingress':
            value['value']['odometry'] = odom(value['robot'])
            value['payload_sha256'] = audit.sha(value['value'])
            value['raw_json'] = audit.canonical(value['value']).decode()
            value['raw_json_sha256'] = audit.hashlib.sha256(value['raw_json'].encode()).hexdigest()
        elif kind == 'state_phase_request' and value['request']['operation'] == 'commit':
            row['wall_monotonic_ns'] = 180
        elif kind in ('tf_promote', 'state_selection', 'state_send'):
            row['wall_monotonic_ns'] += 55
            if kind == 'state_send':
                name = value['robot']; payload = value['envelope']['payload']
                payload['odometry'] = odom(name)
                payload['x'] = odom(name)['pose']['pose']['position']['x']
                payload['safety']['calibration']['odometry'] = odom(name)
                value['payload_sha256'] = audit.sha(payload)
    publication = next(r['payload'] for r in info if r['kind'] == 'state_publish')
    for name, envelope in publication['envelopes'].items():
        payload = envelope['payload']
        payload['odometry'] = odom(name); payload['x'] = odom(name)['pose']['pose']['position']['x']
        payload['safety']['calibration']['odometry'] = odom(name)
    bundle = publication['message']
    for row in bundle['robots']:
        name = row['name']; row['odometry'] = odom(name)
        row['x'] = odom(name)['pose']['pose']['position']['x']
        row['safety']['calibration']['odometry'] = odom(name)
    table = {r['name']: r['safety'] for r in bundle['robots']}
    bundle['safety_table_sha256'] = audit.sha(table)
    publication['message_sha256'] = audit.sha(bundle)
    publication['side_publish_started_wall_monotonic_ns'] = 195
    for side in publication['side_publications']:
        side['odom_sha256'] = audit.sha(odom(side['robot']))
    state_ack = next(r['payload']['ack'] for r in info
                     if r['kind'] == 'state_phase_ack' and r['payload']['ack']['operation'] == 'commit')
    state_ack.update(bundle_sha256=audit.sha(bundle), safety_table_sha256=audit.sha(table),
                     side_publish_started_wall_monotonic_ns=195)
    for name in NAMES:
        state_ack['robots'][name].update(odom_sha256=audit.sha(odom(name)), safety_sha256=audit.sha(table[name]))
    state_take = next(r['payload']['ack'] for r in info
                     if r['kind'] == 'state_phase_ack' and r['payload']['ack']['operation'] == 'takeover')
    peer = copy.deepcopy(raw['peer_phase.jsonl'])
    for row in peer:
        kind, value = row['kind'], row['payload']
        if kind == 'controlled': row['wall_monotonic_ns'] = 120
        elif kind == 'request_received' and value['operation'] == 'takeover': row['wall_monotonic_ns'] = 121
        elif kind == 'ack_published' and value['ack']['operation'] == 'takeover':
            row['wall_monotonic_ns'] = 132
            value.update(publish_started_wall_monotonic_ns=130, publish_completed_wall_monotonic_ns=131)
        elif kind == 'received_odom':
            value['raw'] = odom(value['robot']); value['raw_sha256'] = audit.sha(value['raw'])
        elif kind == 'received_state_bundle':
            value.update(message=copy.deepcopy(bundle), message_sha256=audit.sha(bundle))
        elif kind == 'request_received': value['state_commit'] = copy.deepcopy(state_ack)
    matched = next(r['payload'] for r in peer if r['kind'] == 'inputs_matched')
    peer_request = next(r['payload'] for r in peer if r['kind'] == 'request_received' and r['payload']['operation'] == 'commit')
    matched['request'] = copy.deepcopy(peer_request)
    for name in NAMES:
        matched['inputs']['odom:' + name]['raw_sha256'] = audit.sha(odom(name))
    matched['inputs']['bundle']['message_sha256'] = audit.sha(bundle)
    matched['inputs']['safety']['safety_table_sha256'] = audit.sha(table)
    selected = {(kind, n): {'raw': odom(n) if kind == 'odom' else sample.raw_tf()}
                for kind in ('odom', 'tf') for n in NAMES}
    expected = core.expected_outputs(selected, RELEASE)
    outputs = next(r['payload']['publications'] for r in peer if r['kind'] == 'obstacles_published')
    for item in outputs:
        item['payload'] = expected[item['robot'], item['kind']]
        item['message_sha256'] = audit.sha(item['payload'])
    peer_ack = next(r['payload']['ack'] for r in peer if r['kind'] == 'ack_published' and r['payload']['ack']['operation'] == 'commit')
    peer_ack.update(state_commit=copy.deepcopy(state_ack), bundle_sha256=audit.sha(bundle),
        safety_table_sha256=audit.sha(table), inputs=copy.deepcopy(matched['inputs']),
        publications=copy.deepcopy(outputs), obstacle_publication_sha256=audit.sha(outputs))
    peer_take = next(r['payload']['ack'] for r in peer if r['kind'] == 'ack_published' and r['payload']['ack']['operation'] == 'takeover')
    motion = sample.Ledger('mr3-motion-safety-v1', motion=True)
    motion.add('configuration', {'safety_contract': audit.CONTRACT, 'controlled_execution': True}, 5, T0)
    for i, name in enumerate(NAMES):
        motion.add('own_odom', {'robot': name, 'input_sequence': 1, 'message': odom(name)}, 10+i, T0)
    requests = {}
    takeover_request = {'schema': 'mr3-motion-control-request-v2', 'epoch': EPOCH,
        'request_id': 'take', 'operation': 'takeover', 'target_time_ns': T0}
    motion.add('control_request', takeover_request, 15, T0)

    def intent_publish(value, wall, clock):
        motion.add('reach_intent_publish', {'robot': value['robot'], 'intent': value,
            'payload_sha256': audit.sha(value), 'scope': 'actual_publisher_call_returned_not_delivery',
            'publish_started_wall_monotonic_ns': wall, 'publish_completed_wall_monotonic_ns': wall+1}, wall+2, clock)

    def decision(name, seq, value, wall, clock, stop=False, table_hash=None):
        motion.add('reach_decision', {'robot': name, 'clock_ns': clock, 'decision_sequence': seq,
            'request': requests.get(name), 'own_state': None,
            'received_peers': {n: copy.deepcopy(next(r for r in bundle['robots'] if r['name'] == n))
                               if table_hash is not None else None for n in NAMES if n != name},
            'decision': {'allow': False, 'reason': 'reach_hold', 'output': [0., 0.]},
            'intent': value, 'tracker': {}, 'safety_table_sha256': table_hash,
            'started': stop, 'ready': not stop, **({'phase_kind': 'stop'} if stop else {})}, wall, clock)

    def completed(seq, intents, clock, first_wall, *, stop=False, table_hash=None):
        for i, name in enumerate(NAMES):
            motion.add('actual_cmd_vel', {'robot': name, 'observed_decision_sequence': seq,
                'twist': twist(), 'publisher_identity': graph_twist(name)}, first_wall+i, clock)
        status = {'schema': 'mr3-motion-safety-status-v2', 'epoch': EPOCH, 'clock_ns': clock,
            'ready': not stop, 'completion_scope': 'publication_and_local_topic_receipt',
            'decision_sequences': {n: seq for n in NAMES},
            'outputs': {n: {'linear_x': 0., 'angular_z': 0.} for n in NAMES},
            'safety_contract': audit.CONTRACT, 'intent_refs': audit.information.intent_refs(
                {n: {'intent': intents[n]} for n in NAMES}), 'safety_table_sha256': table_hash,
            **({'phase_kind': 'stop'} if stop else {})}
        motion.add('output_completed', {'status': status, 'publish_started_wall_monotonic_ns': first_wall+3,
            'publish_completed_wall_monotonic_ns': first_wall+4}, first_wall+5, clock)
        return status

    def control_ack(request, status, wall):
        ack = {'schema': 'mr3-motion-control-ack-v2', 'epoch': EPOCH,
            **{k: request[k] for k in ('request_id', 'operation', 'target_time_ns')},
            'clock_ns': status['clock_ns'], 'ok': True, 'status': status,
            **{k: status[k] for k in audit.SAFETY}}
        motion.add('control_ack', ack, wall, status['clock_ns'])
        motion.add('control_ack_published', {'ack': ack, 'publish_started_wall_monotonic_ns': wall+1,
            'publish_completed_wall_monotonic_ns': wall+2}, wall+3, status['clock_ns'])
        return ack

    first = {n: sample.intent(n) for n in NAMES}
    for i, name in enumerate(NAMES):
        intent_publish(first[name], 20+3*i, T0)
        decision(name, 1, first[name], 22+3*i, T0)
    take_status = completed(1, first, T0, 30)
    motion_take = control_ack(takeover_request, take_status, 36)
    motion.add('control_dependency', {'component': 'state', 'value': state_ack}, 230)
    motion.add('reach_state_ingress', {'message': bundle, 'raw_json': audit.canonical(bundle).decode(),
        'publisher_identity': sample.graph('/mr3/received/states', 'mr3_information', '/')}, 239)
    motion.add('received_states', bundle, 240)
    normal_request = {'schema': 'mr3-motion-control-request-v2', 'epoch': EPOCH,
        'request_id': 'commit', 'operation': 'commit', 'target_time_ns': RELEASE,
        'state_commit': copy.deepcopy(state_ack), 'peer_commit': copy.deepcopy(peer_ack)}
    motion.add('control_request', normal_request, 286)
    motion.add('control_dependency', {'component': 'peer', 'value': peer_ack}, 290)
    second = {n: sample.intent(n, 2, RELEASE) for n in NAMES}
    for i, name in enumerate(NAMES):
        intent_publish(second[name], 300+3*i, RELEASE)
        decision(name, 2, second[name], 302+3*i, RELEASE, table_hash=audit.sha(table))
    normal_status = completed(2, second, RELEASE, 320, table_hash=audit.sha(table))
    motion.add('control_commit', {'request': normal_request}, 330)
    normal_ack = control_ack(normal_request, normal_status, 340)
    motion.add('release', {'stamp': RELEASE/1e9}, 350)
    post_hold = {}
    for i, name in enumerate(NAMES):
        post_hold[name] = sample.intent(name, 3, RELEASE)
        post_hold[name].update(anchor={'source_clock_ns': sample.SOURCE, 'odometry': odom(name)},
                               lineage={'release_clock_ns': RELEASE}, target=second[name]['target'])
        intent_publish(post_hold[name], 360+3*i, RELEASE)
    motion.add('terminal', {'epoch': EPOCH, 'end_sim_time_sec': FINAL/1e9, 'termination_reason': 'timeout'}, 585, FINAL)
    stop_request = {'schema': 'mr3-motion-control-request-v2', 'epoch': EPOCH,
        'request_id': 'stop', 'operation': 'stop', 'target_time_ns': FINAL, 'reason': 'task_terminal'}
    motion.add('control_request', stop_request, 600, FINAL)
    stopped = {}
    for i, name in enumerate(NAMES):
        stopped[name] = copy.deepcopy(post_hold[name])
        stopped[name].update(intent_sequence=4, source_clock_ns=FINAL, role='STOP',
                             lineage={'previous_intent_sequence': 3, 'previous_role': 'HOLD'})
        stopped[name]['target'] = dict(second[name]['target'], clock_ns=FINAL, decision_sequence=3)
        intent_publish(stopped[name], 610+3*i, FINAL)
        decision(name, 3, stopped[name], 612+3*i, FINAL, stop=True, table_hash=audit.sha(table))
    stop_status = completed(3, stopped, FINAL, 620, stop=True, table_hash=audit.sha(table))
    stop_ack = control_ack(stop_request, stop_status, 630)
    worker = []

    def worker_add(kind, wall, clock, **payload):
        worker.append({'schema': audit.PROTOCOL, 'epoch': EPOCH, 'kind': kind,
            'wall_monotonic_ns': wall, 'worker_clock_ns': clock, 'worker_physical_ns': clock, **copy.deepcopy(payload)})

    worker_add('request', 13, T0, component='motion', request=takeover_request)
    worker_add('ack_received', 40, T0, component='motion', ack=motion_take)
    worker_add('ack_consumed', 41, T0, component='motion', ack=motion_take)
    worker_add('request', 90, T0, component='state', request=next(r['payload']['request'] for r in info
        if r['kind'] == 'state_phase_request' and r['payload']['request']['operation'] == 'takeover'))
    worker_add('ack_received', 113, T0, component='state', ack=state_take)
    worker_add('ack_consumed', 114, T0, component='state', ack=state_take)
    worker_add('request', 119, T0, component='peer', request=next(r['payload'] for r in peer
        if r['kind'] == 'request_received' and r['payload']['operation'] == 'takeover'))
    worker_add('ack_received', 133, T0, component='peer', ack=peer_take)
    worker_add('ack_consumed', 134, T0, component='peer', ack=peer_take)
    worker_add('request', 175, RELEASE, component='state', request=next(r['payload']['request'] for r in info
        if r['kind'] == 'state_phase_request' and r['payload']['request']['operation'] == 'commit'))
    worker_add('ack_received', 222, RELEASE, component='state', ack=state_ack)
    worker_add('ack_consumed', 223, RELEASE, component='state', ack=state_ack)
    worker_add('request', 224, RELEASE, component='peer', request=peer_request)
    worker_add('ack_received', 283, RELEASE, component='peer', ack=peer_ack)
    worker_add('ack_consumed', 284, RELEASE, component='peer', ack=peer_ack)
    worker_add('request', 285, RELEASE, component='motion', request=normal_request)
    worker_add('ack_received', 344, RELEASE, component='motion', ack=normal_ack)
    worker_add('ack_consumed', 345, RELEASE, component='motion', ack=normal_ack)
    for i, name in enumerate(NAMES):
        worker_add('owner_intent_received', 375+i, RELEASE, robot=name, intent=post_hold[name],
            payload_sha256=audit.sha(post_hold[name]), identity_scope='graph_at_callback_not_per_packet_identity',
            publisher_graph=[{'namespace': '/', 'node': 'motion_safety', 'type': 'std_msgs/msg/String',
                              'endpoint_gid': '29'*24}])
    worker_add('release_intents_captured', 400, RELEASE, release_clock_ns=RELEASE,
        intent_refs=audit.information.intent_refs({n: {'intent': post_hold[n]} for n in NAMES}))
    worker_add('request', 590, FINAL, component='motion', request=stop_request)
    worker_add('stop_observed', 626, FINAL, status=stop_status, origin='stop_topic', duplicate=False)
    worker_add('ack_received', 640, FINAL, component='motion', ack=stop_ack)
    worker_add('ack_consumed', 641, FINAL, component='motion', ack=stop_ack)
    physics = [{'epoch': EPOCH, 'request_id': key, 'start_time_ns': begin, 'end_time_ns': end,
        'start_iterations': begin//1_000_000, 'end_iterations': end//1_000_000,
        'steps': (end-begin)//1_000_000, 'ok': True, 'paused': True}
        for key, begin, end in (('pause', T0, T0), ('boot', T0, RELEASE), ('task', RELEASE, FINAL))]
    drivers = {}; acks = {}
    for name in NAMES:
        records = [{'schema': 'mr3-drive-actuation-v2', 'epoch': EPOCH, 'robot': name,
                    'record_sequence': 1, 'kind': 'configuration', 'sim_time_ns': 0}]
        acks[name] = {}
        for seq, clock in ((1, T0), (2, RELEASE), (3, FINAL)):
            acks[name][seq] = {'schema': 'mr3-drive-target-consumed-v1', 'epoch': EPOCH, 'robot': name,
                'clock_ns': clock, 'source_clock_ns': clock, 'decision_sequence': seq,
                'cmd_seq': seq, 'linear_x': 0., 'angular_z': 0.}
            records.append({'schema': 'mr3-drive-actuation-v2', 'epoch': EPOCH, 'robot': name,
                'record_sequence': len(records)+1, 'kind': 'command_received', 'sim_time_ns': clock,
                'cmd_seq': seq, 'target_clock_ns': clock, 'target_decision_sequence': seq,
                'desired_v': 0., 'desired_w': 0.})
        drivers[name] = records
    drive = []

    def drive_add(kind, wall, clock, **payload):
        drive.append({'epoch': EPOCH, 'kind': kind, 'wall_monotonic_ns': wall,
                      'worker_physical_ns': clock, 'worker_clock_ns': clock, **copy.deepcopy(payload)})

    drive_add('physics_completed', 8, T0, receipt=physics[0])
    for i, name in enumerate(NAMES):
        drive_add('ack_received', 42+i, T0, topic_robot=name, ack=acks[name][1])
    drive_add('ack_consumed', 145, T0, expected_motion=take_status, receipts={n: acks[n][1] for n in NAMES})
    drive_add('advance_permitted', 150, T0, request_id='boot', steps=20, start_time_ns=T0,
        expected_motion=take_status, receipts={n: acks[n][1] for n in NAMES}, control_kind='bootstrap_zero', control_request_id='take')
    drive_add('physics_completed', 170, RELEASE, receipt=physics[1])
    for i, name in enumerate(NAMES):
        drive_add('ack_received', 346+i, RELEASE, topic_robot=name, ack=acks[name][2])
    drive_add('ack_consumed', 420, RELEASE, expected_motion=normal_status, receipts={n: acks[n][2] for n in NAMES})
    drive_add('advance_permitted', 430, RELEASE, request_id='task', steps=20, start_time_ns=RELEASE,
        expected_motion=normal_status, receipts={n: acks[n][2] for n in NAMES}, control_kind='normal', control_request_id='commit')
    drive_add('physics_completed', 500, FINAL, receipt=physics[2])
    for i, name in enumerate(NAMES):
        drive_add('ack_received', 642+i, FINAL, topic_robot=name, ack=acks[name][3])
    drive_add('ack_consumed', 650, FINAL, expected_motion=stop_status, receipts={n: acks[n][3] for n in NAMES})
    motion_phase = []
    for status, received_wall, consumed_wall in ((take_status, 40, 41), (normal_status, 344, 345)):
        for kind, wall in (('ack_received', received_wall), ('ack_consumed', consumed_wall)):
            motion_phase.append({'epoch': EPOCH, 'kind': kind, 'ack': copy.deepcopy(status),
                'wall_monotonic_ns': wall, 'worker_clock_ns': status['clock_ns'], 'worker_physical_ns': status['clock_ns']})
    result = {'metadata.json': {'epoch': EPOCH, 'freeze': FREEZE, 'safety_contract': audit.CONTRACT,
        'execution_phase_protocol': audit.PROTOCOL, 'reset_handshake': 'paused-controlled-state-peer-guard-storage-v2'},
        'summary.json': {}, 'information_states.jsonl': info, 'peer_phase.jsonl': peer,
        'motion_safety.jsonl': motion.rows, 'control_phase_worker.jsonl': worker,
        'drive_phase_worker.jsonl': drive, 'motion_phase_worker.jsonl': motion_phase,
        'physics.jsonl': physics, 'transitions.jsonl': [{'kind': 'reset', 'info': {'release_time_ns': RELEASE}}]}
    result.update({f'drive_{n}.jsonl': drivers[n] for n in NAMES})
    return result


class ReachPeerControlTests(unittest.TestCase):
    def setUp(self):
        self.core, self.provenance = audit.load_impl()
        self.host, _ = audit.load_implementation()

    def replay(self, data):
        return audit.replay_records(data, self.core, self.host)

    def test_whole_source_inverse_and_no_original_audit_invocation(self):
        self.assertTrue(self.provenance['whole_inverse_exact'])
        self.assertEqual(self.provenance['whole_inverse_sha256'], audit.ORIGINAL_SHA)
        self.assertEqual(len(self.provenance['identity_only_source_edits']), 9)
        self.assertIs(self.core.validate_status, audit.validate_status)

    def test_full_synthetic_chain_peer_control_fifo_and_bootstrap(self):
        result = self.replay(make_fixture())
        self.assertTrue(result['passed'])
        self.assertEqual(result['controlled_execution_replay']['bootstrap_zero_quanta'], 1)
        self.assertEqual(result['controlled_execution_replay']['stop_clocks'], [FINAL])
        self.assertEqual(result['motion_fifo']['unmatched'], dict.fromkeys(NAMES, 0))

    def test_full_body_cloud_byte_tamper_is_rejected_even_with_rehashed_claims(self):
        data = make_fixture()
        row = next(r for r in data['peer_phase.jsonl'] if r['kind'] == 'obstacles_published')
        item = next(p for p in row['payload']['publications'] if p['kind'] == 'cloud')
        item['payload']['data_sha256'] = '0'*64; item['message_sha256'] = audit.sha(item['payload'])
        with self.assertRaisesRegex(ValueError, 'immutable independent geometry'):
            self.replay(data)

    def test_bundle_safety_not_discarded_by_legacy_geometry(self):
        data = make_fixture()
        row = next(r for r in data['peer_phase.jsonl'] if r['kind'] == 'received_state_bundle')
        row['payload']['message']['robots'][0]['safety']['intent']['extra'] = 1
        row['payload']['message_sha256'] = audit.sha(row['payload']['message'])
        with self.assertRaises(ValueError):
            self.replay(data)

    def test_state_only_request_without_peer_actual_callback_cannot_move(self):
        data = make_fixture()
        rows = data['motion_safety.jsonl']
        rows[:] = [r for r in rows if not (r['kind'] == 'control_dependency' and r['payload']['component'] == 'peer')]
        for i, row in enumerate(rows, 1): row['record_sequence'] = i
        with self.assertRaisesRegex(ValueError, 'actually receive current dependency'):
            self.replay(data)

    def test_cmd_vel_actual_fifo_reordering_is_rejected(self):
        data = make_fixture()
        row = next(r for r in data['motion_safety.jsonl'] if r['kind'] == 'actual_cmd_vel')
        row['payload']['observed_decision_sequence'] = 2
        with self.assertRaises(ValueError):
            self.replay(data)

    def test_denied_guard_must_emit_strict_zero(self):
        data = make_fixture()
        row = next(r for r in data['motion_safety.jsonl'] if r['kind'] == 'reach_decision')
        row['payload']['decision']['output'][1] = .1
        with self.assertRaises(ValueError):
            self.replay(data)

    def test_new_status_cannot_claim_old_consumed_refs_as_new_output_refs(self):
        data = make_fixture()
        row = next(r for r in data['motion_safety.jsonl'] if r['kind'] == 'output_completed'
                   and r['payload']['status']['clock_ns'] == RELEASE)
        row['payload']['status']['intent_refs']['tb1']['intent_sequence'] = 1
        with self.assertRaisesRegex(ValueError, 'new refs'):
            self.replay(data)

    def test_nonterminal_negative_callback_stays_failed_when_abandoned(self):
        data = make_fixture()
        row = next(r for r in data['control_phase_worker.jsonl'] if r['kind'] == 'ack_received')
        row['ack'].update(ok=False, error='real_failure')
        with self.assertRaisesRegex(ValueError, 'sticky'):
            self.replay(data)

    def test_old_profile_and_old_receipts_refused(self):
        data = make_fixture(); data['metadata.json']['safety_contract'] = 'legacy'
        with self.assertRaisesRegex(ValueError, 'old profile'):
            self.replay(data)
        status = next(r['payload']['status'] for r in make_fixture()['motion_safety.jsonl'] if r['kind'] == 'output_completed')
        status['schema'] = 'mr3-motion-safety-status-v1'
        with self.assertRaises(ValueError): audit.validate_status(status, EPOCH)

    def test_postrelease_refs_require_real_subscribed_hold_packets(self):
        data = make_fixture()
        data['control_phase_worker.jsonl'][:] = [r for r in data['control_phase_worker.jsonl']
                                                if not (r['kind'] == 'owner_intent_received' and r['robot'] == 'tb2')]
        with self.assertRaisesRegex(ValueError, 'missing actual owner callbacks'):
            self.replay(data)

    def test_advance_before_actual_driver_ack_consumption_is_rejected(self):
        data = make_fixture()
        data['drive_phase_worker.jsonl'][:] = [r for r in data['drive_phase_worker.jsonl']
                                              if not (r['kind'] == 'ack_consumed' and r['expected_motion']['clock_ns'] == RELEASE)]
        with self.assertRaisesRegex(ValueError, 'three receipts consumed'):
            self.replay(data)

    def test_episode_api_binds_raw_files_and_exclusive_output(self):
        data = make_fixture()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name, value in data.items():
                content = ''.join(json.dumps(r, allow_nan=False)+'\n' for r in value) if name.endswith('.jsonl') else json.dumps(value)
                (directory/name).write_text(content)
            result = audit.audit_episode(directory, FREEZE)
            self.assertTrue(result['passed'], result['errors'])
            self.assertFalse(result['historical_38_role_qualification'])
            self.assertIn(str(directory/'motion_safety.jsonl'), result['bindings'])
            self.assertIn('control_phase_worker.jsonl', result['artifact_proof'])
            output = directory/'keep.json'; output.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'exclusive'):
                audit.main([str(directory), '--freeze', FREEZE, '--output', str(output)])
            self.assertEqual(output.read_text(), 'keep')

    def turn_case(self):
        data = make_fixture()
        bundle = copy.deepcopy(next(r['payload']['message'] for r in data['information_states.jsonl']
                                    if r['kind'] == 'state_publish'))
        intent = sample.intent('tb1', 2, RELEASE)
        intent.update(role='D', anchor={'source_clock_ns': sample.SOURCE, 'odometry': odom('tb1')},
                      lineage={'anchor_intent_sequence': 2})
        intent['target']['angular_z'] = .2
        next(r for r in bundle['robots'] if r['name'] == 'tb1')['safety']['intent'] = copy.deepcopy(intent)
        table = {r['name']: r['safety'] for r in bundle['robots']}
        bundle.update(safety_table_sha256=audit.sha(table), intent_refs=audit.information.intent_refs(table))
        motion = audit.motion_replay_class(self.core)(EPOCH, {}, {}, SimpleNamespace(complete_publications=[]), self.host.BASE)
        motion.received = bundle
        request = {'v': .1, 'w': .2, 'received_stamp': RELEASE/1e9, 'sequence': 1,
                   'publisher_identity': graph_twist('tb1', 'velocity_smoother'), 'supported': True}
        motion.raw_requests['tb1'] = copy.deepcopy(request)
        motion.owner_intents['tb1'][2] = {'intent': copy.deepcopy(intent)}
        value = {'robot': 'tb1', 'clock_ns': RELEASE, 'decision_sequence': 2,
            'request': request, 'ready': True, 'started': True,
            'received_peers': {r['name']: copy.deepcopy(r) for r in bundle['robots'] if r['name'] != 'tb1'},
            'intent': intent, 'safety_table_sha256': audit.sha(table),
            'decision': {'allow': True, 'reason': 'linear_brake_preserve_requested_turn', 'output': [0., .2],
                'component_filter': {'canonical_input': [.1, .2],
                                     'rejected_transition_checks': {'tb2': {'geometric_necessary': False}}}}}
        return motion, value

    def test_partial_linear_brake_preserves_actual_requested_turn_only(self):
        motion, value = self.turn_case()
        motion.check_decision(value, RELEASE)
        value['decision']['output'][1] = .3
        value['intent']['target']['angular_z'] = .3
        motion.owner_intents['tb1'][2]['intent']['target']['angular_z'] = .3
        with self.assertRaisesRegex(ValueError, 'new velocity/heading'):
            motion.check_decision(value, RELEASE)

    def test_actual_request_cannot_be_replaced_by_a_new_recorded_claim(self):
        motion, value = self.turn_case()
        value['request']['v'] = .15
        with self.assertRaisesRegex(ValueError, 'actual request callback'):
            motion.check_decision(value, RELEASE)

    def test_denied_filter_with_matching_target_still_cannot_issue_turn(self):
        motion, value = self.turn_case()
        value['decision']['allow'] = False
        with self.assertRaisesRegex(ValueError, 'strict zero'):
            motion.check_decision(value, RELEASE)

    def test_stale_actual_request_is_zeroed_at_one_nanosecond_past_limit(self):
        motion, value = self.turn_case()
        source = (RELEASE - 200_000_001)/1e9
        value['request']['received_stamp'] = source
        motion.raw_requests['tb1']['received_stamp'] = source
        with self.assertRaisesRegex(ValueError, 'unavailable actual request'):
            motion.check_decision(value, RELEASE)


if __name__ == '__main__':
    unittest.main()
