"""Real information callbacks bind safety metadata; no ROS/native startup."""
import copy
import json
from types import MethodType, SimpleNamespace

import pytest
from std_msgs.msg import String

from multi_robot_exploration.mr3_information import (
    IdealInformation, odom_payload, publisher_graph_identity,
)
from multi_robot_exploration.mr3_safety_intent import canonical_json, payload_sha256
from test_mr3_information import input_odom, input_rows, input_tf, state_input_bridge


def endpoint(topic):
    robot = topic.split('/')[1]
    intent = topic.endswith('/safety_intent')
    return SimpleNamespace(
        node_name='motion_safety' if intent else 'turtlebot3_diff_drive',
        node_namespace='/' if intent else '/' + robot,
        topic_type='std_msgs/msg/String', endpoint_gid=bytes([7 if intent else 9]) * 24)


def reach_bridge():
    node = state_input_bridge()
    node.safety_contract = 'mr3-reach-v1'
    for name in ('initialize_safety_inputs', 'receive_safety_input', 'safety_for_state'):
        setattr(node, name, MethodType(getattr(IdealInformation, name), node))
    node.initialize_safety_inputs()
    node.get_publishers_info_by_topic = lambda topic: [endpoint(topic)]
    return node


def intent(epoch, robot, source, sequence=1):
    return {'schema': 'mr3-safety-intent-v1', 'epoch': epoch, 'robot': robot,
            'intent_sequence': sequence, 'source_clock_ns': source, 'role': 'HOLD',
            'anchor': None, 'admitted_signs': [], 'lineage': {'release_clock_ns': None},
            'target': {'schema': 'mr3-drive-target-v1', 'epoch': epoch, 'robot': robot,
                       'clock_ns': source, 'decision_sequence': sequence,
                       'linear_x': 0., 'angular_z': 0.}}


def calibration(epoch, robot, odom, sequence=1):
    source = odom.header.stamp.sec * 10**9 + odom.header.stamp.nanosec
    return {'schema': 'mr3-odom-calibration-v1', 'epoch': epoch, 'robot': robot,
            'source_clock_ns': source, 'publication_sequence': sequence,
            'coefficient_c': 1., 'coefficient_s': 0., 'odometry': odom_payload(odom),
            'conversion_contract': 'float32-trig-binary64-rn-v1',
            'producer_frame': 'world-common-model-origin-v1'}


def ingress(node, kind, robot, value):
    node.receive_safety_input(kind, robot, String(data=canonical_json(value)))


def test_covariance_projection_is_builtin_float_with_original_json_values():
    odom = input_odom(1_000_000_000)
    # Humble's generated ROS covariance getter yields numpy.float64 elements.
    original = {'pose': list(odom.pose.covariance), 'twist': list(odom.twist.covariance)}
    projected = odom_payload(odom)
    for name in ('pose', 'twist'):
        assert all(type(value) is float for value in projected[name]['covariance'])
        assert json.dumps(projected[name]['covariance']) == json.dumps(original[name])
    canonical_json(projected)


def prime(node, *, send_intents=True, send_calibration=True, source=None):
    source = node.clock_ns - 10_000_000 if source is None else source
    odoms, intents, calibrations = {}, {}, {}
    for robot in node.names:
        odom = input_odom(source)
        odoms[robot] = odom
        IdealInformation.receive_local_odom(node, robot, odom)
        IdealInformation.receive_local_tf(node, robot, input_tf(source))
        intents[robot] = intent(node.epoch, robot, source)
        calibrations[robot] = calibration(node.epoch, robot, odom)
        if send_intents:
            ingress(node, 'intent', robot, intents[robot])
        if send_calibration:
            ingress(node, 'calibration', robot, calibrations[robot])
    return odoms, intents, calibrations


def references(intents):
    return {name: {'intent_sequence': value['intent_sequence'],
                   'payload_sha256': payload_sha256(value)} for name, value in intents.items()}


def commit(node, intents, identifier='phase1'):
    value = {'schema': 'mr3-state-phase-request-v2', 'epoch': node.epoch,
             'request_id': identifier, 'operation': 'commit',
             'target_time_ns': node.clock_ns, 'expected_intents': references(intents)}
    node.receive_state_phase_request(String(data=canonical_json(value)))
    return value


def ack(node):
    return json.loads(node.state_phase_publisher.messages[-1].data)


@pytest.mark.parametrize('missing', ['intent', 'calibration'])
def test_rpc_refs_cannot_replace_real_safety_ingress(missing):
    node = reach_bridge()
    _, intents, calibrations = prime(
        node, send_intents=missing != 'intent', send_calibration=missing != 'calibration')
    commit(node, intents)
    assert node.pending_state_phase is not None and not node.state_publisher.messages
    for robot in node.names:
        ingress(node, missing, robot, intents[robot] if missing == 'intent' else calibrations[robot])
    assert ack(node)['ok'] is True
    assert node.state_sequence == 1 and node.clock_ns == 2_000_000_000


def test_actual_envelope_preserves_raw_projection_and_binds_whole_safety_table():
    node = reach_bridge()
    odoms, intents, calibrations = prime(node)
    commit(node, intents)
    result = ack(node)
    bundle = json.loads(node.state_publisher.messages[-1].data)
    assert result['schema'] == 'mr3-state-phase-ack-v2'
    assert result['safety_contract'] == 'mr3-reach-v1'
    assert result['bundle_sha256'] == payload_sha256(bundle)
    table = {row['name']: row['safety'] for row in bundle['robots']}
    assert bundle['safety_table_sha256'] == result['safety_table_sha256'] == payload_sha256(table)
    assert bundle['intent_refs'] == result['intent_refs'] == references(intents)
    for row in bundle['robots']:
        name = row['name']
        envelope = node.received.get('state', name)
        assert envelope.payload['safety'] == {'intent': intents[name], 'calibration': calibrations[name]}
        assert row['odometry'] == calibrations[name]['odometry'] == odom_payload(odoms[name])
        assert result['robots'][name]['safety_sha256'] == payload_sha256(table[name])
        assert result['robots'][name]['source_ns'] == 1_990_000_000
    assert not any(p.messages for p in node.navigation_publishers.values())
    selected = input_rows(node, 'state_selection')
    assert all(row['schema'] == 'mr3-information-state-audit-v2' for row in selected)
    assert all(row['payload']['safety_input_sequences'] for row in selected)


def test_future_safety_cannot_displace_an_exact_causal_reference():
    node = reach_bridge()
    _, intents, _ = prime(node)
    future = {}
    for robot in node.names:
        future[robot] = intent(node.epoch, robot, 2_020_000_000, 2)
        ingress(node, 'intent', robot, future[robot])
        odom = input_odom(2_020_000_000)
        IdealInformation.receive_local_odom(node, robot, odom)
        ingress(node, 'calibration', robot, calibration(node.epoch, robot, odom, 2))
    commit(node, intents)
    assert ack(node)['intent_refs'] == references(intents)
    node.clock_ns = 2_020_000_000
    commit(node, future, 'phase2')
    assert ack(node)['ok'] and ack(node)['intent_refs'] == references(future)
    assert all(row['source_clock_ns'] == node.clock_ns for row in
               (record.payload['safety']['calibration'] for record in
                [node.received.get('state', name) for name in node.names]))


def test_normal_intent_waits_for_its_independently_delivered_causal_raw_source():
    node = reach_bridge()
    _, _, _ = prime(node)
    intents = {}
    for robot in node.names:
        value = intent(node.epoch, robot, node.clock_ns, 3)
        value.update(role='N', admitted_signs=[1], anchor={
            'source_clock_ns': 1_980_000_000,
            'odometry': odom_payload(input_odom(1_980_000_000))}, lineage={
                'anchor_intent_sequence': 1, 'transition_intent_sequence': 2,
                'actuation_sequence': 1, 'actuation_source_clock_ns': 1_994_000_000,
                'causal_source_clock_ns': 1_995_000_000, 'cmd_seq': 1})
        value['target']['linear_x'] = .1
        intents[robot] = value
        ingress(node, 'intent', robot, value)
    commit(node, intents)
    assert node.pending_state_phase is not None and not node.clock_failed
    assert not node.state_publisher.messages
    for robot in node.names:
        odom = input_odom(1_995_000_000)
        IdealInformation.receive_local_odom(node, robot, odom)
        ingress(node, 'calibration', robot, calibration(node.epoch, robot, odom, 2))
    assert ack(node)['ok'] and ack(node)['intent_refs'] == references(intents)


@pytest.mark.parametrize('age_ns,valid', [(500_000_000, True), (500_000_001, False)])
def test_intent_source_age_is_independent_of_fresh_measurement_age(age_ns, valid):
    node = reach_bridge()
    _, _, _ = prime(node, send_intents=False)
    intents = {robot: intent(node.epoch, robot, node.clock_ns-age_ns)
               for robot in node.names}
    for robot in node.names:
        ingress(node, 'intent', robot, intents[robot])
    commit(node, intents)
    assert ack(node)['ok'] is valid
    assert bool(node.state_publisher.messages) is valid


def test_wrong_calibration_raw_payload_fails_before_state_publication():
    node = reach_bridge()
    _, intents, calibrations = prime(node, send_calibration=False)
    calibrations['tb1']['odometry']['pose']['pose']['position']['x'] = .25
    for robot in node.names:
        ingress(node, 'calibration', robot, calibrations[robot])
    commit(node, intents)
    assert not ack(node)['ok'] and node.clock_failed
    assert not node.state_publisher.messages
    failures = input_rows(node, 'state_input_failure')
    assert 'exact selected raw odometry' in failures[-1]['payload']['reason']


def test_conflicting_requested_intent_hash_cannot_select_a_real_other_payload():
    node = reach_bridge()
    _, intents, _ = prime(node)
    altered = copy.deepcopy(intents)
    altered['tb1']['target']['decision_sequence'] += 1
    commit(node, altered)
    assert not ack(node)['ok'] and not node.state_publisher.messages
    assert 'reference conflicts' in input_rows(node, 'state_input_failure')[-1]['payload']['reason']


@pytest.mark.parametrize('change', ['foreign_graph', 'multiple_graph', 'changed_gid'])
def test_safety_graph_identity_is_real_graph_scope_and_fail_closed(change):
    node = reach_bridge()
    if change == 'changed_gid':
        ingress(node, 'intent', 'tb1', intent(node.epoch, 'tb1', node.clock_ns, 1))
    original = endpoint('/tb1/mr3/safety_intent')
    if change == 'foreign_graph':
        original.node_name = 'imposter'
    elif change == 'changed_gid':
        original.endpoint_gid = bytes([8]) * 24
    node.get_publishers_info_by_topic = lambda topic: (
        [original, copy.deepcopy(original)] if change == 'multiple_graph' else [original])
    ingress(node, 'intent', 'tb1', intent(node.epoch, 'tb1', node.clock_ns, 2))
    assert node.clock_failed
    recorded = input_rows(node, 'intent_ingress')[-1]['payload']
    assert recorded['admission'] == 'rejected'
    assert recorded['publisher_identity']['scope'] == 'graph_at_callback'
    assert recorded['publisher_identity']['packet_publisher_gid_available'] is False


def test_duplicate_json_members_are_preserved_as_rejected_wire_input():
    node = reach_bridge()
    value = canonical_json(intent(node.epoch, 'tb1', node.clock_ns))
    wire = value[:-1] + ',"role":"HOLD"}'
    node.receive_safety_input('intent', 'tb1', String(data=wire))
    row = input_rows(node, 'intent_ingress')[-1]['payload']
    assert row['raw_json'] == wire and row['admission'] == 'rejected'
    assert node.clock_failed and not node.safety_histories['intent', 'tb1']


def test_ingress_copies_and_duplicates_never_freshen_source_or_received_identity():
    node = reach_bridge()
    value = intent(node.epoch, 'tb1', node.clock_ns)
    ingress(node, 'intent', 'tb1', value)
    original = copy.deepcopy(node.safety_histories['intent', 'tb1'][0])
    node.clock_ns += 20_000_000
    ingress(node, 'intent', 'tb1', value)
    value['target']['linear_x'] = .2
    assert node.safety_histories['intent', 'tb1'] == [original]
    assert input_rows(node, 'intent_ingress')[-1]['payload']['admission'] == 'duplicate'


def test_legacy_phase_still_rejects_v2_or_extra_reference_fields():
    node = state_input_bridge()
    _, intents, _ = prime(node, send_intents=False, send_calibration=False)
    commit(node, intents)
    assert ack(node)['schema'] == 'mr3-state-phase-ack-v1' and not ack(node)['ok']
    assert not node.state_publisher.messages


def test_graph_helper_never_invents_packet_identity():
    node = reach_bridge()
    result = publisher_graph_identity(node, '/tb1/mr3/safety_intent', 'motion_safety', '/')
    assert result['valid'] and result['scope'] == 'graph_at_callback'
    assert not result['packet_publisher_gid_available']
