"""Joint publication wiring with ROS message types, without a ROS graph/plant."""
import copy
import json
from types import MethodType

import pytest

from multi_robot_exploration.motion_safety import MotionSafety, storage_receipt_qos
from multi_robot_exploration.mr3_safety_intent import payload_sha256
from multi_robot_exploration.mr3_motion_authority import PROFILE as MOTION_AUTHORITY_PROFILE
from test_motion_safety import node_fixture


@pytest.mark.parametrize('reach_enabled,depth', ((False, 1), (True, 256)))
def test_storage_qos_changes_only_reach_history_capacity(reach_enabled, depth):
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, ReliabilityPolicy
    qos = storage_receipt_qos(reach_enabled)
    assert qos.depth == depth and qos.history == HistoryPolicy.KEEP_LAST
    assert qos.reliability == ReliabilityPolicy.RELIABLE
    assert qos.durability == DurabilityPolicy.TRANSIENT_LOCAL
    assert storage_receipt_qos().depth == 1


@pytest.mark.parametrize('value', (None, 0, 1, 'legacy', 'mr3-reach-v1'))
def test_storage_qos_cannot_enable_reach_via_a_truthy_nonboolean(value):
    with pytest.raises(ValueError, match='boolean'):
        storage_receipt_qos(value)


class Owner:
    def __init__(self, name, decide):
        self.name, self.decider = name, decide
        self.current_intent = {'intent_sequence': 1}
        self.stopped = False
        self.sequence = 1

    def decide(self, request, own, peers, clock, delivered):
        return self.decider(self.name, request, peers)

    def stop(self):
        self.stopped = True

    def publish_target(self, target):
        return self.make_intent(target['clock_ns'], target)

    def make_intent(self, clock, target):
        self.sequence += 1
        value = {'schema': 'mr3-safety-intent-v1', 'epoch': 'episode',
                 'robot': self.name, 'intent_sequence': self.sequence,
                 'source_clock_ns': clock, 'role': 'STOP' if self.stopped else 'HOLD',
                 'anchor': None, 'admitted_signs': [],
                 'lineage': ({'previous_intent_sequence': 1, 'previous_role': 'HOLD'}
                             if self.stopped else {'release_clock_ns': None}),
                 'target': copy.deepcopy(target)}
        self.current_intent = value
        return value

    def status(self):
        return {'permanent_stop': self.stopped}


def fixture(decider=None):
    node, clock, events = node_fixture()
    if decider is None:
        decider = lambda name, request, peers: {'allow': True, 'reason': 'fixture_clear',
                                               'output': list(request), 'minimum_margin_m': None}
    node.reach_enabled = True
    node.motion_authority_profile = MOTION_AUTHORITY_PROFILE
    # This fixture already substitutes Owner.decide to isolate joint publication
    # ordering. Supply the corresponding explicitly artificial receiver result;
    # real owner/stop/receipt handshakes are covered by the callback suite.
    node.receiving_permission = lambda name, tracker, request, clock_ns: {
        "effective_request": [request["v"], request["w"]] if request is not None else [0., 0.],
        "permission": "normal_reach" if request is not None else "zero_only",
        "state": "ACTIVE", "raw_goal_generation": None,
        "raw_goal_association": "UNKNOWN_UNSTAMPED_TWIST",
        "scope": "ARTIFICIAL_RECEIVER_RESULT_FOR_JOINT_PUBLICATION_ONLY"}
    node._reach_emitting = False
    node.started = True
    node.normal_control_model_fault = None
    node.issued_motion = set()
    node.reach = {name: Owner(name, decider) for name in node.outputs}
    for state in node.received['robots']:
        state['safety'] = {'intent': {'intent_sequence': 1}, 'calibration': {'tag': state['name']}}
    node.received.update(safety_contract='mr3-reach-v1', intent_refs={
        name: {'intent_sequence': 1, 'payload_sha256': 'a'*64} for name in node.outputs})
    node.received['safety_table_sha256'] = payload_sha256({
        row['name']: row['safety'] for row in node.received['robots']})
    node.control_safety_context = {key: copy.deepcopy(node.received[key])
                                   for key in ('safety_table_sha256', 'intent_refs')}
    node.control_inputs_ready = lambda value: True
    node.intent_publishers = {name: type('Publisher', (), {'publish': staticmethod(
        lambda msg, name=name: events.append(('intent', name, json.loads(msg.data))))})()
        for name in node.outputs}
    for method in ('emit_reach_motion', '_emit_reach_motion', 'reach_failure',
                   '_stop_reach_failure', 'publish_reach_intent'):
        setattr(node, method, MethodType(getattr(MotionSafety, method), node))
    node.publish_completed_status = lambda value: None
    return node, clock, events


def outputs(events):
    return [row for row in events if row[0] == 'output']


def readiness_fixture():
    node, clock, events = fixture()
    node.reach_pending_release = None
    node.control_inputs_ready = MethodType(MotionSafety.control_inputs_ready, node)
    calls, stopped = [], []
    for name, owner in node.reach.items():
        owner.fault = None
        owner.synchronize = lambda value, name=name: calls.append(name) or True
    node.stop_controlled = lambda: stopped.append(True)
    return node, clock, events, calls, stopped


@pytest.mark.parametrize('name', ('tb1', 'tb2', 'tb3'))
def test_latched_tracker_fault_is_visible_even_before_another_prefix_is_ready(name):
    node, clock, events, calls, stopped = readiness_fixture()
    node.reach['tb1'].synchronize = lambda value: calls.append('tb1') or False
    node.reach_pending_release = clock[0]
    node.reach[name].fault = 'retained native causal contradiction'
    assert node.control_inputs_ready(clock[0]) is False
    assert calls == [] and stopped == [True]
    assert node.halted == 'normal_control_model_invalid'
    assert node.normal_control_model_fault['robot'] == name
    assert node.normal_control_model_fault['reason'] == node.reach[name].fault
    assert any(event[0] == 'reach_model_failure' for event in events)
    assert outputs(events) == []


@pytest.mark.parametrize('name', ('tb1', 'tb2', 'tb3'))
def test_new_synchronization_fault_uses_the_existing_observable_failure_path(name):
    node, clock, events, calls, stopped = readiness_fixture()
    def fail(value):
        calls.append(name)
        node.reach[name].fault = 'new native causal contradiction'
        raise ValueError(node.reach[name].fault)
    node.reach[name].synchronize = fail
    assert node.control_inputs_ready(clock[0]) is False
    assert calls == list(node.reach)[:list(node.reach).index(name)+1]
    assert stopped == [True] and node.halted == 'normal_control_model_invalid'
    assert node.normal_control_model_fault['robot'] == name
    assert node.normal_control_model_fault['reason'] == node.reach[name].fault
    assert any(event[0] == 'reach_model_failure' for event in events)


def test_pending_prefix_is_still_a_wait_without_a_model_failure():
    node, clock, events, calls, stopped = readiness_fixture()
    node.reach['tb1'].synchronize = lambda value: calls.append('tb1') or False
    assert node.control_inputs_ready(clock[0]) is False
    assert calls == ['tb1'] and stopped == []
    assert node.halted is None and node.normal_control_model_fault is None
    assert not any(event[0] == 'reach_model_failure' for event in events)


def test_pending_release_is_still_a_wait_without_synchronization_or_failure():
    node, clock, events, calls, stopped = readiness_fixture()
    node.reach_pending_release = clock[0]
    assert node.control_inputs_ready(clock[0]) is False
    assert calls == [] and stopped == []
    assert node.halted is None and node.normal_control_model_fault is None
    assert not any(event[0] == 'reach_model_failure' for event in events)


def test_late_third_robot_fault_suppresses_all_three_before_first_publication():
    def decide(name, request, peers):
        if name == 'tb3':
            raise ValueError('independent third-robot contradiction')
        return {'allow': True, 'reason': 'fixture_clear', 'output': [.2, 0.]}
    node, _, events = fixture(decide)
    node.stop_controlled = lambda: pytest.fail('recursive publication from inside joint admission')
    node.emit_reach_motion()
    assert len(outputs(events)) == 3
    assert all(row[2:] == (0., 0.) for row in outputs(events))
    assert all(owner.stopped for owner in node.reach.values())
    assert node.normal_control_model_fault['robot'] == 'tb3'
    assert node._reach_emitting is False


def test_table_content_is_rehashed_instead_of_trusting_copied_digest_labels():
    node, _, events = fixture()
    node.received['robots'][0]['safety']['calibration']['tag'] = 'tampered'
    node.emit_reach_motion()
    assert node.halted == 'normal_control_model_invalid'
    assert all(row[2:] == (0., 0.) for row in outputs(events))


def test_every_decider_uses_one_frozen_received_peer_bundle():
    observed = []
    def decide(name, request, peers):
        observed.append(copy.deepcopy(peers))
        node.received['robots'][1]['safety']['calibration']['tag'] = 'changed_after_freeze'
        return {'allow': True, 'reason': 'fixture_clear', 'output': list(request)}
    node, _, events = fixture(decide)
    node.emit_reach_motion()
    assert len(observed) == 3
    assert observed[0]['tb2']['safety']['calibration']['tag'] == 'tb2'
    assert observed[2]['tb2']['safety']['calibration']['tag'] == 'tb2'
    assert outputs(events)[0][2:] == (.2, 0.)


def test_new_output_intent_refs_are_distinct_from_the_consumed_table_hash():
    node, clock, _ = fixture()
    consumed = node.control_safety_context['safety_table_sha256']
    node.emit_reach_motion()
    status = node.pending_status[(clock[0], 'normal')]
    assert status['safety_table_sha256'] == consumed
    assert all(ref['intent_sequence'] == 2 for ref in status['intent_refs'].values())
    assert status['intent_refs'] != node.control_safety_context['intent_refs']


def test_intent_publish_receipt_brackets_actual_publisher_call():
    node, _, events = fixture()
    node.emit_reach_motion()
    records = [row[1] for row in events if row[0] == 'reach_intent_publish']
    assert len(records) == 3
    assert all(0 < row['publish_started_wall_monotonic_ns']
               <= row['publish_completed_wall_monotonic_ns'] for row in records)


def test_missing_request_still_checks_initial_hold_and_publishes_zero():
    called = []
    def decide(name, request, peers):
        called.append((name, request))
        return {'allow': False, 'reason': 'hold', 'output': [0., 0.]}
    node, _, events = fixture(decide)
    node.requests = {}
    node.emit_reach_motion()
    assert called == [(name, [0., 0.]) for name in node.outputs]
    assert all(row[2:] == (0., 0.) for row in outputs(events))


def test_native_graph_endpoint_change_is_a_permanent_joint_fault():
    from types import SimpleNamespace
    from std_msgs.msg import String
    node, _, events = fixture()
    node.reach_publisher_gids = {}
    node.try_reach_release = lambda: None
    node.control_phase = None
    stopped, admitted = [], []
    node.stop_controlled = lambda: stopped.append(True)
    node.reach['tb1'].receive_calibration = lambda value: admitted.append(value)
    gid = [bytes([1])*24]
    node.get_publishers_info_by_topic = lambda topic: [SimpleNamespace(
        node_namespace='/tb1', node_name='turtlebot3_diff_drive',
        topic_type='std_msgs/msg/String', endpoint_gid=gid[0])]
    # This fixture isolates graph custody; the schema parser has independent
    # real-payload tests. It cannot claim a physical calibration application.
    message = String(data=json.dumps({'epoch': node.epoch}))
    MotionSafety.receive_reach_feed(node, message, 'tb1', 'calibration')
    gid[0] = bytes([2])*24
    MotionSafety.receive_reach_feed(node, message, 'tb1', 'calibration')
    assert len(admitted) == 1 and stopped == [True]
    assert node.halted == 'normal_control_model_invalid'
    assert any(event[0] == 'invalid_reach_driver_ingress' for event in events)


def test_foreign_common_bundle_publisher_cannot_replace_delivered_modes():
    from types import SimpleNamespace
    from std_msgs.msg import String
    node, _, events = fixture()
    node.reach_publisher_gids = {}
    node.get_publishers_info_by_topic = lambda topic: [SimpleNamespace(
        node_namespace='/', node_name='foreign_node', topic_type='std_msgs/msg/String',
        endpoint_gid=bytes([1])*24)]
    stopped = []
    node.stop_controlled = lambda: stopped.append(True)
    value = dict(node.received, epoch=node.epoch)
    MotionSafety.receive_states(node, String(data=json.dumps(value)))
    assert node.received is None and stopped == [True]
    assert node.halted == 'normal_control_model_invalid'
    assert any(event[0] == 'reach_state_ingress' for event in events)
