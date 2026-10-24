"""A reach peer ACK must consume one actual, complete, immutable safety table."""
import copy
import json
from types import SimpleNamespace

import pytest
from std_msgs.msg import String

from multi_robot_exploration import peer_obstacles as peer
from multi_robot_exploration.mr3_safety_intent import canonical_json, payload_sha256
from test_mr3_information_reach import calibration, intent, references
from test_peer_phase import deliver, fixture, inputs, output_count, send, takeover


def reach_fixture(clock_ns=1_100_000_000):
    node, now, odoms, transforms = fixture(clock_ns=clock_ns)
    node.safety_contract = 'mr3-reach-v1'
    node.phase_bundle_publisher_gid = None
    node.get_publishers_info_by_topic = lambda topic: [SimpleNamespace(
        node_name='mr3_information', node_namespace='/',
        topic_type='std_msgs/msg/String', endpoint_gid=bytes([11]) * 24)]
    return node, now, odoms, transforms


def reach_takeover(node):
    return send(node, {'schema': 'mr3-peer-phase-request-v2', 'epoch': node.epoch,
                       'request_id': 'takeover', 'target_time_ns': node.get_clock().now().nanoseconds,
                       'operation': 'takeover'})


def reach_inputs(node, odoms, transforms, before_callback=True):
    request, bundle = inputs(node, odoms, transforms, before_callback=False)
    intents = {}
    for row in bundle['robots']:
        name = row['name']
        source = peer.stamp_ns(odoms[name].header.stamp)
        intents[name] = intent(node.epoch, name, source)
        row['safety'] = {'intent': intents[name],
                         'calibration': calibration(node.epoch, name, odoms[name])}
    table = {row['name']: row['safety'] for row in bundle['robots']}
    bundle.update(safety_contract='mr3-reach-v1', intent_refs=references(intents),
                  safety_table_sha256=payload_sha256(table))
    state = request['state_commit']
    request['schema'] = 'mr3-peer-phase-request-v2'
    state.update(schema='mr3-state-phase-ack-v2', bundle_sha256=peer.payload_sha(bundle),
                 **{key: copy.deepcopy(bundle[key]) for key in
                    ('safety_contract', 'intent_refs', 'safety_table_sha256')})
    for row in bundle['robots']:
        state['robots'][row['name']]['safety_sha256'] = payload_sha256(row['safety'])
    if before_callback:
        deliver(node, odoms, transforms, bundle)
    return request, bundle


def latest_ack(node):
    return json.loads(node.phase_ack_pub.messages[-1].data)


def test_common_bundle_is_actually_received_before_reach_ack():
    node, _, odoms, tf = reach_fixture()
    assert reach_takeover(node)['schema'] == 'mr3-peer-phase-ack-v2'
    request, bundle = reach_inputs(node, odoms, tf, before_callback=False)
    send(node, request)
    assert node.phase_pending is not None and output_count(node) == 0
    deliver(node, odoms, tf, bundle)
    node.poll_phase()
    ack = latest_ack(node)
    assert ack['ok'] and ack['state_commit'] == request['state_commit']
    assert ack['safety_table_sha256'] == bundle['safety_table_sha256']
    assert ack['intent_refs'] == bundle['intent_refs']
    assert ack['inputs']['safety']['intent_refs'] == bundle['intent_refs']
    assert ack['inputs']['bundle']['publisher_identity']['scope'] == 'graph_at_callback'
    assert ack['inputs']['bundle']['publisher_identity']['packet_publisher_gid_available'] is False
    assert output_count(node) == 6


@pytest.mark.parametrize('changed', ['table_digest', 'intent_ref', 'robot_safety_hash'])
def test_phase_request_cannot_replace_actual_safety_table(changed):
    node, _, odoms, tf = reach_fixture()
    reach_takeover(node)
    request, _ = reach_inputs(node, odoms, tf)
    state = request['state_commit']
    if changed == 'table_digest':
        state['safety_table_sha256'] = '0' * 64
    elif changed == 'intent_ref':
        state['intent_refs']['tb1']['payload_sha256'] = '0' * 64
    else:
        state['robots']['tb1']['safety_sha256'] = '0' * 64
    ack = send(node, request)
    assert ack['ok'] is False and output_count(node) == 0
    assert 'safety' in ack['error']


@pytest.mark.parametrize('change', ['calibration_raw', 'table_claim', 'intent_claim'])
def test_bundle_payload_is_not_trusted_because_its_claims_match_a_request(change):
    node, now, odoms, tf = reach_fixture()
    reach_takeover(node)
    request, bundle = reach_inputs(node, odoms, tf, before_callback=False)
    if change == 'calibration_raw':
        bundle['robots'][0]['safety']['calibration']['odometry']['twist']['twist']['linear']['x'] = .1
        table = {row['name']: row['safety'] for row in bundle['robots']}
        bundle['safety_table_sha256'] = payload_sha256(table)
        request['state_commit']['safety_table_sha256'] = bundle['safety_table_sha256']
        request['state_commit']['robots']['tb1']['safety_sha256'] = payload_sha256(table['tb1'])
    elif change == 'table_claim':
        bundle['safety_table_sha256'] = '0' * 64
        request['state_commit']['safety_table_sha256'] = '0' * 64
    else:
        bundle['intent_refs']['tb1']['payload_sha256'] = '0' * 64
        request['state_commit']['intent_refs'] = copy.deepcopy(bundle['intent_refs'])
    request['state_commit']['bundle_sha256'] = peer.payload_sha(bundle)
    deliver(node, odoms, tf, bundle)
    assert not node.phase_bundles
    send(node, request)
    assert node.phase_pending is not None and output_count(node) == 0
    now[0] += 1
    node.poll_phase()
    assert latest_ack(node)['ok'] is False and output_count(node) == 0


def test_reach_metadata_does_not_change_scan_or_full_body_geometry():
    old, _, odoms, tf = fixture()
    takeover(old)
    request, _ = inputs(old, odoms, tf)
    old_ack = send(old, request)
    new, _, odoms, tf = reach_fixture()
    reach_takeover(new)
    request, _ = reach_inputs(new, odoms, tf)
    new_ack = send(new, request)
    assert old_ack['ok'] and new_ack['ok']
    assert [(x['robot'], x['kind'], x['payload']) for x in old_ack['publications']] == [
        (x['robot'], x['kind'], x['payload']) for x in new_ack['publications']]


@pytest.mark.parametrize('age_ns,valid', [(500_000_000, True), (500_000_001, False)])
def test_reach_state_age_keeps_the_original_exact_closed_endpoint(age_ns, valid):
    node, _, odoms, tf = reach_fixture(clock_ns=1_000_000_000 + age_ns)
    reach_takeover(node)
    request, _ = reach_inputs(node, odoms, tf)
    ack = send(node, request)
    assert ack['ok'] is valid
    assert output_count(node) == (6 if valid else 0)


def test_foreign_state_publisher_never_supplies_a_common_mode_table():
    node, _, odoms, tf = reach_fixture()
    reach_takeover(node)
    node.get_publishers_info_by_topic = lambda topic: [SimpleNamespace(
        node_name='imposter', node_namespace='/',
        topic_type='std_msgs/msg/String', endpoint_gid=bytes([11]) * 24)]
    _, bundle = reach_inputs(node, odoms, tf, before_callback=False)
    node.receive_state_bundle(String(data=canonical_json(bundle)))
    assert not node.phase_bundles
    assert 'graph identity' in json.loads(node.phase_audit.getvalue().splitlines()[-1])['payload']['reason']


def test_v1_request_cannot_enter_explicit_reach_mode():
    node, _, _, _ = reach_fixture()
    ack = takeover(node)
    assert ack['schema'] == 'mr3-peer-phase-ack-v2' and not ack['ok']
    assert not node.phase_controlled
