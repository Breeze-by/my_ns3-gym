"""Synthetic protocol evidence only; no plant, ROS or actor eligibility credit."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from mr3_learning import audit_reach_information as audit


EPOCH = 'synthetic-reach-information'
FREEZE = 'a' * 40
SOURCE = 990_000_000
CLOCK = 1_020_000_000


def stamp(ns):
    return {'sec': ns // 10**9, 'nanosec': ns % 10**9}


def raw_odom():
    vector = {'x': 0., 'y': 0., 'z': 0.}
    return {'header': {'stamp': stamp(SOURCE), 'frame_id': 'odom'}, 'child_frame_id': 'base_footprint',
            'pose': {'pose': {'position': copy.deepcopy(vector),
                             'orientation': dict(vector, w=1.)}, 'covariance': [0.] * 36},
            'twist': {'twist': {'linear': copy.deepcopy(vector), 'angular': copy.deepcopy(vector)},
                      'covariance': [0.] * 36}}


def raw_tf():
    return {'header': {'stamp': stamp(SOURCE + 200_000_000), 'frame_id': 'map'},
            'child_frame_id': 'odom', 'transform': {'translation': {'x': 0., 'y': 0., 'z': 0.},
            'rotation': {'x': 0., 'y': 0., 'z': 0., 'w': 1.}}}


def intent(robot, seq=1, clock=1_000_000_000):
    return {'schema': 'mr3-safety-intent-v1', 'epoch': EPOCH, 'robot': robot,
            'intent_sequence': seq, 'source_clock_ns': clock, 'role': 'HOLD', 'anchor': None,
            'admitted_signs': [], 'lineage': {'release_clock_ns': None},
            'target': {'schema': 'mr3-drive-target-v1', 'epoch': EPOCH, 'robot': robot,
                       'clock_ns': clock, 'decision_sequence': seq, 'linear_x': 0., 'angular_z': 0.}}


def calibration(robot):
    return {'schema': 'mr3-odom-calibration-v1', 'epoch': EPOCH, 'robot': robot,
            'source_clock_ns': SOURCE, 'publication_sequence': 1, 'coefficient_c': 1.,
            'coefficient_s': 0., 'odometry': raw_odom(),
            'conversion_contract': 'float32-trig-binary64-rn-v1',
            'producer_frame': 'world-common-model-origin-v1'}


def graph(topic, node, namespace):
    return {'scope': 'graph_at_callback', 'packet_publisher_gid_available': False,
            'topic': topic, 'valid': True, 'error': None,
            'endpoints': [{'node_name': node, 'node_namespace': namespace,
                           'topic_type': 'std_msgs/msg/String', 'endpoint_gid': '19' * 24}]}


class Ledger:
    def __init__(self, schema, motion=False):
        self.schema, self.motion, self.rows = schema, motion, []

    def add(self, kind, payload, wall, clock=CLOCK):
        row = {'schema': self.schema, 'epoch': EPOCH, 'record_sequence': len(self.rows)+1,
               'kind': kind, 'wall_monotonic_ns': wall, 'payload': copy.deepcopy(payload)}
        row['sim_time_sec' if self.motion else 'clock_ns'] = clock/1e9 if self.motion else clock
        self.rows.append(row)
        return row


def fixture():
    """Construct complete raw→state→peer→three-guard evidence, independently."""
    host, _ = audit.load_implementation(); base = host.BASE
    info = Ledger('mr3-information-state-audit-v2')
    peer = Ledger('mr3-peer-phase-audit-v2')
    motion = Ledger('mr3-motion-safety-v1', motion=True)
    table = {n: {'intent': intent(n), 'calibration': calibration(n)} for n in audit.ROBOTS}
    refs = audit.intent_refs(table)
    info.add('configuration', {'tf_validity_lead_sec': .2, 'pending_limit': 256,
        'state_period_sec': .1, 'odom_pending_order': 'source_ns_ascending',
        'tf_pending_order': 'accepted_header_ascending', 'safety_contract': audit.CONTRACT,
        'safety_identity_scope': 'graph_at_callback', 'safety_history_limit': 256}, 5)
    wall = 40
    for name in audit.ROBOTS:
        for kind, raw in (('odom', raw_odom()), ('tf', raw_tf())):
            info.add(kind + '_ingress', {'robot': name, 'input_sequence': 1, 'raw': raw,
                'raw_sha256': audit.sha(raw), 'source_ns': SOURCE, 'admission': 'queued',
                'matched_input_sequence': None}, wall, 1_000_000_000)
            wall += 1
        for kind in ('intent', 'calibration'):
            value = table[name][kind]
            topic = f'/{name}/mr3/safety_intent' if kind == 'intent' else f'/{name}/mr3_drive/odometry_calibration'
            encoded = audit.canonical(value).decode()
            info.add(kind + '_ingress', {'robot': name, 'input_sequence': 1, 'topic': topic,
                'raw_json': encoded, 'raw_json_sha256': audit.hashlib.sha256(encoded.encode()).hexdigest(),
                'publisher_identity': graph(topic, 'motion_safety' if kind == 'intent' else 'turtlebot3_diff_drive',
                                            '/' if kind == 'intent' else '/' + name),
                'received_wall_monotonic_ns': wall, 'value': value, 'payload_sha256': audit.sha(value),
                'source_clock_ns': value['source_clock_ns'], 'producer_sequence': 1, 'admission': 'queued'},
                wall + 1, 1_000_000_000)
            wall += 2
    takeover = {'schema': 'mr3-state-phase-request-v2', 'epoch': EPOCH, 'request_id': 'take',
                'operation': 'takeover', 'target_time_ns': 1_000_000_000, 'expected_intents': refs}
    info.add('state_phase_request', {'request': takeover, 'duplicate': False}, 100, 1_000_000_000)
    take_ack = {'schema': 'mr3-state-phase-ack-v2', 'epoch': EPOCH, 'request_id': 'take',
                'operation': 'takeover', 'target_time_ns': 1_000_000_000, 'clock_ns': 1_000_000_000,
                'ok': True, 'state_sequence': None, 'bundle_sha256': None, 'robots': {},
                'scope': 'periodic_state_publication_disabled', 'safety_contract': audit.CONTRACT,
                'intent_refs': None, 'safety_table_sha256': None}
    info.add('state_phase_ack', {'ack': take_ack, 'cached': False,
        'publish_started_wall_monotonic_ns': 110, 'publish_completed_wall_monotonic_ns': 111}, 112, 1_000_000_000)
    request = dict(takeover, request_id='commit', operation='commit', target_time_ns=CLOCK)
    info.add('state_phase_request', {'request': request, 'duplicate': False}, 120)
    envelopes, delivered, rows, sides = {}, {}, [], []
    wall = 130
    for name in audit.ROBOTS:
        info.add('tf_promote', {'robot': name, 'selected_input_sequence': 1,
                              'pending_tf_input_sequences': []}, wall); wall += 1
        info.add('state_selection', {'cycle_id': 1, 'robot': name, 'odom_input_sequence': 1,
            'tf_input_sequence': 1, 'odom_source_ns': SOURCE, 'tf_source_ns': SOURCE,
            'pending_odom_input_sequences': [], 'pending_tf_input_sequences': [], 'skip_reason': None,
            'safety_input_sequences': {'intent': 1, 'calibration': 1}}, wall); wall += 1
        payload = base.state_from_raw(name, raw_odom(), raw_tf(), .2)
        payload['safety'] = copy.deepcopy(table[name])
        source = min(payload['odom_source_stamp'], payload['tf_source_stamp'])
        envelope = {'epoch': EPOCH, 'stream': 'state', 'source': name, 'sequence': 1, 'version': 1,
                    'generated_stamp': CLOCK/1e9, 'received_stamp': None, 'source_stamp': source, 'payload': payload}
        envelopes[name] = copy.deepcopy(envelope)
        info.add('state_send', {'cycle_id': 1, 'robot': name, 'envelope': envelope,
                               'payload_sha256': audit.sha(payload)}, wall); wall += 1
        delivered[name] = dict(copy.deepcopy(envelope), received_stamp=CLOCK/1e9)
        row = copy.deepcopy(payload)
        row.update(epoch=EPOCH, sequence=1, version=1, source_stamp=source,
                   received_stamp=CLOCK/1e9, valid=True)
        rows.append(row)
        sides.append({'robot': name, 'odom_topic': f'/mr3/received/{name}/odom',
            'tf_topic': f'/mr3/received/{name}/tf', 'odom_sha256': audit.sha(raw_odom()),
            'tf_sha256': audit.sha(raw_tf()), 'envelope_sequence': 1})
    bundle = {'epoch': EPOCH, 'sequence': 1, 'robots': rows, 'map_version': 0,
        'map_source_stamp': None, 'map_received_stamp': None, 'map_sources': {}, 'map_payload_sha256': None,
        'navigation_composition': {'version': 'synthetic-out-of-role'}, 'navigation_sources': {},
        'information_diagnostics': {}, 'safety_contract': audit.CONTRACT,
        'intent_refs': refs, 'safety_table_sha256': audit.sha(table)}
    info.add('state_publish', {'cycle_id': 1, 'message': bundle, 'message_sha256': audit.sha(bundle),
        'envelopes': delivered, 'side_publications': sides, 'scope': 'actual_publish_calls_returned',
        'side_publish_started_wall_monotonic_ns': 190, 'publish_started_wall_monotonic_ns': 200,
        'publish_completed_wall_monotonic_ns': 201}, 205)
    bindings = {}
    for name, side in zip(audit.ROBOTS, sides):
        payload = envelopes[name]['payload']
        bindings[name] = {'sequence': 1, 'version': 1, 'source_stamp': envelopes[name]['source_stamp'],
            'source_ns': round(envelopes[name]['source_stamp']*1e9),
            'odom_source_ns': round(payload['odom_source_stamp']*1e9),
            'tf_source_ns': round(payload['tf_source_stamp']*1e9),
            **{k: side[k] for k in ('odom_topic', 'tf_topic', 'odom_sha256', 'tf_sha256')},
            'safety_sha256': audit.sha(table[name])}
    state_ack = dict(take_ack, request_id='commit', operation='commit', clock_ns=CLOCK,
        target_time_ns=CLOCK, state_sequence=1, bundle_sha256=audit.sha(bundle), robots=bindings,
        scope='actual_state_and_side_publish_calls_returned', intent_refs=refs,
        safety_table_sha256=audit.sha(table), side_publish_started_wall_monotonic_ns=190,
        bundle_publish_started_wall_monotonic_ns=200, bundle_publish_completed_wall_monotonic_ns=201)
    info.add('state_phase_ack', {'ack': state_ack, 'cached': False,
        'publish_started_wall_monotonic_ns': 220, 'publish_completed_wall_monotonic_ns': 221}, 222)
    peer.add('configuration', {'stepped_mode': True, 'tf_source_lead_sec': .2,
        'input_topics': {kind + ':' + n: f'/mr3/received/{n}/{kind}'
                        for kind in ('odom', 'tf') for n in audit.ROBOTS}}, 5)
    peer_take = {'schema': 'mr3-peer-phase-request-v2', 'epoch': EPOCH, 'request_id': 'take',
                 'operation': 'takeover', 'target_time_ns': 1_000_000_000}
    peer.add('controlled', peer_take, 100, 1_000_000_000)
    peer.add('request_received', peer_take, 101, 1_000_000_000)
    peer.add('ack_published', {'ack': {'schema': 'mr3-peer-phase-ack-v2', 'epoch': EPOCH,
        'request_id': 'take', 'operation': 'takeover', 'target_time_ns': 1_000_000_000,
        'clock_ns': 1_000_000_000, 'ok': True, 'scope': 'automatic_obstacle_timer_disabled',
        'safety_contract': audit.CONTRACT, 'intent_refs': None, 'safety_table_sha256': None},
        'publish_started_wall_monotonic_ns': 110, 'publish_completed_wall_monotonic_ns': 111}, 112, 1_000_000_000)
    side_refs = {}; wall = 210
    for name in audit.ROBOTS:
        for kind, raw in (('odom', raw_odom()), ('tf', raw_tf())):
            peer.add('received_' + kind, {'robot': name, 'input_sequence': 1, 'raw': raw,
                'raw_sha256': audit.sha(raw), 'topic': f'/mr3/received/{name}/{kind}',
                'received_wall_monotonic_ns': wall}, wall+1)
            side_refs[kind + ':' + name] = {'input_sequence': 1, 'raw_sha256': audit.sha(raw),
                                            'received_wall_monotonic_ns': wall}
            wall += 2
    received_bundle = {'message': bundle, 'message_sha256': audit.sha(bundle),
        'received_wall_monotonic_ns': 223,
        'publisher_identity': graph('/mr3/received/states', 'mr3_information', '/')}
    peer.add('received_state_bundle', received_bundle, 224)
    peer_request = {'schema': 'mr3-peer-phase-request-v2', 'epoch': EPOCH, 'request_id': 'commit',
                    'operation': 'commit', 'target_time_ns': CLOCK, 'state_commit': state_ack}
    peer.add('request_received', peer_request, 225)
    side_refs['bundle'] = {'state_sequence': 1, 'message_sha256': audit.sha(bundle),
        'received_wall_monotonic_ns': 223, 'publisher_identity': received_bundle['publisher_identity']}
    side_refs['safety'] = {'safety_contract': audit.CONTRACT, 'intent_refs': refs,
                           'safety_table_sha256': audit.sha(table)}
    peer.add('inputs_matched', {'request': peer_request, 'inputs': side_refs}, 250)
    outputs = [{'robot': name, 'kind': kind,
        'topic': f'/{name}/peer_obstacles' if kind == 'scan' else f'/{name}/peer_footprints',
        'payload': {'synthetic_only': True}, 'message_sha256': audit.sha({'synthetic_only': True}),
        'publish_started_wall_monotonic_ns': 260, 'publish_completed_wall_monotonic_ns': 261}
        for name in audit.ROBOTS for kind in ('scan', 'cloud')]
    peer.add('obstacles_published', {'request_id': 'commit', 'publications': outputs}, 265)
    peer_ack = {'schema': 'mr3-peer-phase-ack-v2', 'epoch': EPOCH, 'request_id': 'commit',
        'operation': 'commit', 'clock_ns': CLOCK, 'target_time_ns': CLOCK, 'ok': True,
        'scope': 'actual_obstacle_publish_calls_returned', 'safety_contract': audit.CONTRACT,
        'intent_refs': refs, 'safety_table_sha256': audit.sha(table), 'commit_sequence': 1,
        'state_commit': state_ack, 'state_sequence': 1, 'bundle_sha256': audit.sha(bundle),
        'inputs': side_refs, 'publications': outputs, 'obstacle_publication_sha256': audit.sha(outputs)}
    peer.add('ack_published', {'ack': peer_ack, 'publish_started_wall_monotonic_ns': 280,
                             'publish_completed_wall_monotonic_ns': 281}, 282)
    motion.add('configuration', {'safety_contract': audit.CONTRACT, 'controlled_execution': True}, 5)
    for i, name in enumerate(audit.ROBOTS):
        motion.add('own_odom', {'robot': name, 'input_sequence': 1, 'message': raw_odom()}, 10+i, 1_000_000_000)
    for i, name in enumerate(audit.ROBOTS):
        motion.add('reach_intent_publish', {'robot': name, 'intent': table[name]['intent'],
            'payload_sha256': audit.sha(table[name]['intent']), 'scope': 'actual_publisher_call_returned_not_delivery',
            'publish_started_wall_monotonic_ns': 20+i, 'publish_completed_wall_monotonic_ns': 21+i},
            22+i, 1_000_000_000)
    motion.add('control_dependency', {'component': 'state', 'value': state_ack}, 230)
    motion.add('reach_state_ingress', {'message': bundle, 'raw_json': audit.canonical(bundle).decode(),
        'publisher_identity': graph('/mr3/received/states', 'mr3_information', '/')}, 239)
    motion.add('received_states', bundle, 240)
    motion.add('control_dependency', {'component': 'peer', 'value': peer_ack}, 290)
    new_table = {}
    for i, name in enumerate(audit.ROBOTS):
        new = intent(name, 2, CLOCK); new_table[name] = {'intent': new}
        motion.add('reach_intent_publish', {'robot': name, 'intent': new, 'payload_sha256': audit.sha(new),
            'scope': 'actual_publisher_call_returned_not_delivery', 'publish_started_wall_monotonic_ns': 300+3*i,
            'publish_completed_wall_monotonic_ns': 301+3*i}, 302+3*i)
        motion.add('reach_decision', {'robot': name, 'clock_ns': CLOCK, 'intent': new,
            'received_peers': {r['name']: r for r in rows if r['name'] != name},
            'safety_table_sha256': audit.sha(table)}, 303+3*i)
    motion.add('control_commit', {'request': {'schema': 'mr3-motion-control-request-v2',
        'epoch': EPOCH, 'request_id': 'commit', 'operation': 'commit', 'target_time_ns': CLOCK,
        'state_commit': state_ack, 'peer_commit': peer_ack}}, 330)
    status = {'schema': 'mr3-motion-safety-status-v2', 'safety_contract': audit.CONTRACT,
              'intent_refs': audit.intent_refs(new_table), 'safety_table_sha256': audit.sha(table)}
    motion_ack = {'ok': True, 'request_id': 'commit', 'status': status, 'target_time_ns': CLOCK,
        'intent_refs': status['intent_refs'], 'safety_table_sha256': status['safety_table_sha256']}
    motion.add('control_ack', motion_ack, 340)
    motion.add('control_ack_published', {'ack': motion_ack, 'publish_started_wall_monotonic_ns': 341,
                                       'publish_completed_wall_monotonic_ns': 342}, 343)
    return {'information_states.jsonl': info.rows, 'peer_phase.jsonl': peer.rows,
            'motion_safety.jsonl': motion.rows}


def normal_lineage_fixture(*, successor=False):
    """An independent synthetic motion-prefix unit, alongside the whole-chain test.

    Supplied Information/Peer publications are explicit synthetic records. This
    tests the independent lineage consumer, not another native or full reader.
    """
    evidence = fixture()
    motion = Ledger('mr3-motion-safety-v1', motion=True)
    motion.rows = copy.deepcopy(evidence['motion_safety.jsonl'])
    publications = [copy.deepcopy(r['payload']) for r in evidence['information_states.jsonl']
                    if r['kind'] == 'state_publish']
    information = SimpleNamespace(complete_publications=publications,
        ack_publications=[{'ack': r['payload']['ack'],
                           'start': r['payload']['publish_started_wall_monotonic_ns']}
                          for r in evidence['information_states.jsonl'] if r['kind'] == 'state_phase_ack'],
        actual_intent_ingress=[r['payload'] for r in evidence['information_states.jsonl']
                               if r['kind'] == 'intent_ingress'])
    peer = SimpleNamespace(ack_publications=[{'ack': r['payload']['ack'],
                                             'start': r['payload']['publish_started_wall_monotonic_ns']}
                                            for r in evidence['peer_phase.jsonl'] if r['kind'] == 'ack_published'])
    anchor = {'source_clock_ns': SOURCE, 'odometry': raw_odom()}

    def publish(value, wall):
        motion.add('reach_intent_publish', {'robot': 'tb1', 'intent': value,
            'payload_sha256': audit.sha(value), 'scope': 'actual_publisher_call_returned_not_delivery',
            'publish_started_wall_monotonic_ns': wall, 'publish_completed_wall_monotonic_ns': wall+1},
            wall+2, value['source_clock_ns'])

    disk = intent('tb1', 3, 1_040_000_000)
    disk.update(role='D', anchor=anchor, lineage={'anchor_intent_sequence': 3})
    publish(disk, 350)
    announcement = intent('tb1', 4, 1_060_000_000)
    announcement.update(role='X', anchor=anchor, admitted_signs=[1],
                        lineage={'anchor_intent_sequence': 3, 'transition_intent_sequence': 4})
    publish(announcement, 360)
    bundle = copy.deepcopy(publications[0]['message']); bundle['sequence'] = 2
    for row in bundle['robots']:
        name = row['name']
        row.update(sequence=2, version=2, received_stamp=1.08)
        row['safety']['intent'] = copy.deepcopy(announcement if name == 'tb1' else intent(name, 2, CLOCK))
    table = {r['name']: r['safety'] for r in bundle['robots']}
    bundle['intent_refs'], bundle['safety_table_sha256'] = audit.intent_refs(table), audit.sha(table)
    publications.append({'message': bundle, 'message_sha256': audit.sha(bundle),
                         'publish_started_wall_monotonic_ns': 365})
    motion.add('reach_state_ingress', {'message': bundle, 'raw_json': audit.canonical(bundle).decode(),
        'publisher_identity': graph('/mr3/received/states', 'mr3_information', '/')}, 370, 1_080_000_000)
    motion.add('received_states', bundle, 371, 1_080_000_000)
    moving = copy.deepcopy(announcement)
    moving.update(intent_sequence=5, source_clock_ns=1_080_000_000)
    moving['target'].update(clock_ns=1_080_000_000, decision_sequence=5, linear_x=.1)
    publish(moving, 380)
    actual = {'schema': 'mr3-drive-applied-v1', 'epoch': EPOCH, 'robot': 'tb1',
        'source_clock_ns': 1_090_000_000, 'actuation_sequence': 1, 'cmd_seq': 5, 'dt_ns': 34_000_000,
        'target': copy.deepcopy(moving['target']), 'pairs': [{'pair_index': 0,
            'current_rim_mps': [.1, .1], 'desired_rim_mps': [.1, .1], 'applied_rim_mps': [.1, .1],
            'alpha': 1., 'max_acceleration_mps2': 1.}]}
    motion.add('reach_driver_ingress', {'robot': 'tb1', 'kind': 'applied', 'message': actual,
        'raw_json': audit.canonical(actual).decode(),
        'publisher_identity': graph('/tb1/mr3_drive/applied', 'turtlebot3_diff_drive', '/tb1')},
        390, 1_090_000_000)
    later_raw = raw_odom(); later_raw['header']['stamp'] = stamp(1_100_000_000)
    motion.add('own_odom', {'robot': 'tb1', 'input_sequence': 2, 'message': later_raw}, 400, 1_100_000_000)
    normal = copy.deepcopy(moving)
    normal.update(role='N', intent_sequence=6, source_clock_ns=1_100_000_000)
    normal['target'].update(clock_ns=1_100_000_000, decision_sequence=6)
    normal['lineage'].update(actuation_sequence=1, actuation_source_clock_ns=1_090_000_000,
                             causal_source_clock_ns=1_100_000_000, cmd_seq=5)
    publish(normal, 410)
    if successor:
        next_raw = copy.deepcopy(later_raw); next_raw['header']['stamp'] = stamp(1_120_000_000)
        motion.add('own_odom', {'robot': 'tb1', 'input_sequence': 3, 'message': next_raw}, 420, 1_120_000_000)
        next_intent = copy.deepcopy(normal)
        next_intent.update(intent_sequence=7, source_clock_ns=1_120_000_000)
        next_intent['target'].update(clock_ns=1_120_000_000, decision_sequence=7, angular_z=.1)
        next_intent['lineage']['causal_source_clock_ns'] = 1_120_000_000
        publish(next_intent, 430)
    return motion.rows, information, peer


class ReachInformationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.evidence = fixture()

    def tearDown(self):
        self.temp.cleanup()

    def run_audit(self):
        (self.directory / 'metadata.json').write_text(json.dumps({'epoch': EPOCH, 'freeze': FREEZE}))
        (self.directory / 'summary.json').write_text('{}\n')
        for name, rows in self.evidence.items():
            (self.directory / name).write_text(''.join(json.dumps(r, allow_nan=False)+'\n' for r in rows))
        return audit.audit_episode(self.directory, FREEZE)

    def test_full_augmented_delivery_and_old_consumed_table_new_refs_are_separate(self):
        result = self.run_audit()
        self.assertTrue(result['passed'], result['errors'])
        self.assertFalse(result['historical_38_role_qualification'])
        self.assertFalse(result['native_admission'])
        self.assertEqual(result['motion_counts']['full_three_guard_commits'], 1)

    def test_complete_new_profile_row_requires_actual_delivered_transform(self):
        row = next(r for r in self.evidence['information_states.jsonl'] if r['kind'] == 'state_publish')
        row['payload']['message']['robots'][0].pop('transform')
        row['payload']['message_sha256'] = audit.sha(row['payload']['message'])
        result = self.run_audit()
        self.assertFalse(result['passed'])
        self.assertIn('published state differs from delivered envelope', result['errors'][0])

    def test_changed_bundle_transform_cannot_replace_the_exact_delivered_tf(self):
        row = next(r for r in self.evidence['information_states.jsonl'] if r['kind'] == 'state_publish')
        row['payload']['message']['robots'][0]['transform']['transform']['translation']['x'] = .01
        row['payload']['message_sha256'] = audit.sha(row['payload']['message'])
        result = self.run_audit()
        self.assertFalse(result['passed'])
        self.assertIn('published state differs from delivered envelope', result['errors'][0])

    def test_changed_sent_transform_cannot_bypass_actual_raw_tf_selection(self):
        row = next(r for r in self.evidence['information_states.jsonl'] if r['kind'] == 'state_send')
        row['payload']['envelope']['payload']['transform']['transform']['translation']['x'] = .01
        row['payload']['payload_sha256'] = audit.sha(row['payload']['envelope']['payload'])
        result = self.run_audit()
        self.assertFalse(result['passed'])
        self.assertIn('sent state differs', result['errors'][0])

    def test_private_new_projection_restores_entire_immutable_legacy_source(self):
        import inspect
        host, proof = audit.load_implementation()
        projected = proof['reach_delivery_transform_projection']
        self.assertTrue(projected['whole_source_inverse_equal'])
        self.assertEqual(projected['whole_source_inverse_sha256'], projected['original_source']['sha256'])
        self.assertEqual(projected['literal_count'], 1)
        legacy, _ = audit.load_measurement_implementation()
        self.assertIn("transform = state.pop('transform')", inspect.getsource(legacy.RawReplay.publish))
        self.assertIsNot(host.RawReplay.publish, legacy.RawReplay.publish)

    def test_extra_metadata_cannot_be_masked_by_original_measurement_oracle(self):
        row = next(r for r in self.evidence['information_states.jsonl'] if r['kind'] == 'state_send')
        row['payload']['envelope']['payload']['safety']['intent']['unrecognized'] = 0
        row['payload']['payload_sha256'] = audit.sha(row['payload']['envelope']['payload'])
        result = self.run_audit()
        self.assertFalse(result['passed'])
        self.assertIn('sent state differs', result['errors'][0])

    def test_missing_real_calibration_ingress_cannot_be_replaced_by_selected_snapshot(self):
        rows = self.evidence['information_states.jsonl']
        rows[:] = [r for r in rows if not (r['kind'] == 'calibration_ingress' and r['payload']['robot'] == 'tb1')]
        for i, row in enumerate(rows, 1):
            row['record_sequence'] = i
        result = self.run_audit()
        self.assertFalse(result['passed'])
        self.assertIn('missing actual', result['errors'][0])

    def test_missing_owner_publication_is_not_proved_by_information_graph(self):
        rows = self.evidence['motion_safety.jsonl']
        rows[:] = [r for r in rows if not (r['kind'] == 'reach_intent_publish'
                   and r['payload']['robot'] == 'tb1' and r['payload']['intent']['intent_sequence'] == 1)]
        for i, row in enumerate(rows, 1):
            row['record_sequence'] = i
        result = self.run_audit()
        self.assertFalse(result['passed'])

    def test_peer_cannot_use_request_instead_of_real_received_bundle(self):
        rows = self.evidence['peer_phase.jsonl']
        rows[:] = [r for r in rows if r['kind'] != 'received_state_bundle']
        for i, row in enumerate(rows, 1):
            row['record_sequence'] = i
        result = self.run_audit()
        self.assertFalse(result['passed'])
        self.assertIn('actual matching bundle callback', result['errors'][0])

    def test_motion_guard_cannot_consume_a_different_frozen_table(self):
        row = next(r for r in self.evidence['motion_safety.jsonl'] if r['kind'] == 'reach_decision')
        row['payload']['safety_table_sha256'] = '0' * 64
        result = self.run_audit()
        self.assertFalse(result['passed'])
        self.assertIn('different complete frozen table', result['errors'][0])

    def test_publisher_completed_is_not_required_before_actual_callback(self):
        row = next(r for r in self.evidence['motion_safety.jsonl'] if r['kind'] == 'reach_intent_publish')
        row['payload']['publish_completed_wall_monotonic_ns'] = 100
        row['wall_monotonic_ns'] = 100
        # A real callback can execute before the publishing call returns. Keep
        # the owner record prefix monotonic while preserving that valid order.
        rows = self.evidence['motion_safety.jsonl']
        for item in rows[row['record_sequence']:]:
            item['wall_monotonic_ns'] = max(item['wall_monotonic_ns'], 100)
        result = self.run_audit()
        self.assertTrue(result['passed'], result['errors'])

    def test_graph_scope_cannot_be_promoted_to_packet_authentication(self):
        row = next(r for r in self.evidence['information_states.jsonl'] if r['kind'] == 'intent_ingress')
        row['payload']['publisher_identity']['packet_publisher_gid_available'] = True
        result = self.run_audit()
        self.assertFalse(result['passed'])

    def test_exact_half_second_age_and_one_nanosecond_future_or_stale(self):
        host, _ = audit.load_implementation(); value = intent('tb1')
        audit.validate_intent(value, EPOCH, 'tb1', host.BASE, 1_500_000_000)
        for now in (999_999_999, 1_500_000_001):
            with self.assertRaises(ValueError):
                audit.validate_intent(value, EPOCH, 'tb1', host.BASE, now)

    def test_duplicate_json_raw_and_incomplete_prefix_are_rejected(self):
        row = next(r for r in self.evidence['information_states.jsonl'] if r['kind'] == 'intent_ingress')
        row['payload']['raw_json'] = '{"schema":1,"schema":2}'
        row['payload']['raw_json_sha256'] = audit.hashlib.sha256(row['payload']['raw_json'].encode()).hexdigest()
        self.assertFalse(self.run_audit()['passed'])
        self.evidence = fixture()
        self.evidence['peer_phase.jsonl'][3]['record_sequence'] += 1
        self.assertFalse(self.run_audit()['passed'])

    def test_output_refuses_existing_file(self):
        output = self.directory / 'existing.json'; output.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'exclusive'):
            audit.main([str(self.directory), '--output', str(output)])
        self.assertEqual(output.read_text(), 'keep')


class NormalLineageTests(unittest.TestCase):
    def audit_motion(self, rows, information, peer):
        host, _ = audit.load_implementation()
        return audit.audit_motion(rows, information, peer, EPOCH, host.BASE)

    def test_actual_applied_then_strict_later_raw_normal_lineage(self):
        rows, information, peer = normal_lineage_fixture()
        result = self.audit_motion(rows, information, peer)
        self.assertEqual(result['reach_driver_ingress'], 1)
        self.assertEqual(result['reach_intent_publish'], 10)

    def test_compatible_normal_successor_keeps_original_anchor_and_actual_application(self):
        rows, information, peer = normal_lineage_fixture(successor=True)
        result = self.audit_motion(rows, information, peer)
        self.assertEqual(result['reach_intent_publish'], 11)

    def test_same_stamp_raw_is_not_strictly_post_actuation(self):
        rows, information, peer = normal_lineage_fixture()
        value = rows[-1]['payload']['intent']
        value['lineage']['causal_source_clock_ns'] = value['lineage']['actuation_source_clock_ns']
        rows[-1]['payload']['payload_sha256'] = audit.sha(value)
        with self.assertRaisesRegex(ValueError, 'strict post-actuation'):
            self.audit_motion(rows, information, peer)

    def test_missing_real_post_actuation_callback_is_not_proved_by_a_promise(self):
        rows, information, peer = normal_lineage_fixture()
        rows[:] = [r for r in rows if not (r['kind'] == 'own_odom' and r['payload']['input_sequence'] == 2)]
        for i, row in enumerate(rows, 1):
            row['record_sequence'] = i
        with self.assertRaisesRegex(ValueError, 'strict later actual own raw'):
            self.audit_motion(rows, information, peer)

    def test_storage_receipt_cannot_substitute_for_actual_application(self):
        rows, information, peer = normal_lineage_fixture()
        value = next(r['payload'] for r in rows if r['kind'] == 'reach_driver_ingress')
        value['kind'] = 'storage'
        value['publisher_identity'] = graph('/tb1/mr3_drive/status', 'turtlebot3_diff_drive', '/tb1')
        # This is a synthetic storage receipt. It intentionally repeats the
        # target identity but cannot enter the actual-application prefix.
        value['message'] = {'epoch': EPOCH, 'robot': 'tb1', 'cmd_seq': 5,
                            'target': value['message']['target']}
        value['raw_json'] = audit.canonical(value['message']).decode()
        with self.assertRaisesRegex(ValueError, 'actual earlier applied'):
            self.audit_motion(rows, information, peer)

    def test_owner_x_publication_without_real_delivered_x_cannot_establish_normal(self):
        rows, information, peer = normal_lineage_fixture()
        rows[:] = [r for r in rows if not (r['kind'] in ('reach_state_ingress', 'received_states')
                                          and r['payload'].get('sequence', r['payload'].get('message', {}).get('sequence')) == 2)]
        for i, row in enumerate(rows, 1):
            row['record_sequence'] = i
        with self.assertRaisesRegex(ValueError, 'prior delivered X'):
            self.audit_motion(rows, information, peer)

    def test_normal_cannot_use_current_intent_as_its_transition_witness(self):
        rows, information, peer = normal_lineage_fixture()
        value = rows[-1]['payload']['intent']
        value['lineage']['transition_intent_sequence'] = value['intent_sequence']
        rows[-1]['payload']['payload_sha256'] = audit.sha(value)
        with self.assertRaises(ValueError):
            self.audit_motion(rows, information, peer)


if __name__ == '__main__':
    unittest.main()
