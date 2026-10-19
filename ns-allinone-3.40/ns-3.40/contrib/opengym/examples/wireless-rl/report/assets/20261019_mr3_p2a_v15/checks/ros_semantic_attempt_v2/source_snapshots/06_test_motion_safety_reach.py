"""Joint publication wiring with ROS message types, without a ROS graph/plant."""
import copy
import json
from types import MethodType

import pytest

from multi_robot_exploration.motion_safety import MotionSafety
from multi_robot_exploration.mr3_safety_intent import payload_sha256
from test_motion_safety import node_fixture


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
    for method in ('emit_reach_motion', '_emit_reach_motion', 'reach_failure', 'publish_reach_intent'):
        setattr(node, method, MethodType(getattr(MotionSafety, method), node))
    node.publish_completed_status = lambda value: None
    return node, clock, events


def outputs(events):
    return [row for row in events if row[0] == 'output']


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
