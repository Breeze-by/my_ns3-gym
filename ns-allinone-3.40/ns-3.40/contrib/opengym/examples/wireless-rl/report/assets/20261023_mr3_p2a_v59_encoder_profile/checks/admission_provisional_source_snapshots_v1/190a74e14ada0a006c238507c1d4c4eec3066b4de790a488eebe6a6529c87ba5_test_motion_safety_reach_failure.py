"""Permanent-fault publication and real zero-target wiring; no ROS graph/plant."""
import copy
import json
from types import MethodType, SimpleNamespace

import pytest
from std_msgs.msg import String

from multi_robot_exploration import motion_safety
from multi_robot_exploration.motion_safety import MotionSafety
from multi_robot_exploration.mr3_motion_control import MotionControlPhase
from test_motion_safety_reach import fixture, outputs


def fault_fixture(*, started=False, decider=None):
    node, clock, events = fixture(decider)
    node.started = started
    node.reach_pending_release = clock[0]
    node._reach_failure_message = None
    node._reach_failure_message_epoch = None
    node._reach_failure_stop_requested = False
    requests = []

    def ensure_stop():
        requests.append(True)
        node.emit_reach_motion(stop=True)

    node.control_phase = SimpleNamespace(controlled=True, ensure_stop=ensure_stop)
    node.stop_controlled = MethodType(MotionSafety.stop_controlled, node)
    return node, clock, events, requests


def publications(events):
    return [json.loads(row[1]) for row in events if row[0] == 'failure_pub']


def retained_faults(events):
    return [row[1] for row in events if row[0] == 'reach_model_failure']


@pytest.mark.parametrize('started', (False, True))
def test_first_permanent_fault_is_factual_before_or_after_release_and_still_stops(started):
    node, clock, events, requests = fault_fixture(started=started)
    node.reach_failure('tb3', ValueError('calibration publication stream gap/regression'))
    fault = {'schema': 'mr3-reach-runtime-fault-v1', 'robot': 'tb3',
             'reason': 'calibration publication stream gap/regression', 'clock_ns': clock[0]}
    assert node.normal_control_model_fault == fault
    assert retained_faults(events) == [fault]
    assert publications(events) == [{'component': 'motion_safety', 'epoch': node.epoch, **fault}]
    assert node.failure_sent is True and node._reach_failure_stop_requested is True
    assert node.halted == 'normal_control_model_invalid' and node.reach_pending_release is None
    assert node.started is started
    assert requests == [True]
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))
    assert all(owner.stopped for owner in node.reach.values())


def test_repeated_faults_keep_first_robot_reason_clock_and_do_not_repeat_stop_or_broadcast():
    node, clock, events, requests = fault_fixture()
    node.reach_failure('tb3', ValueError('first contradiction'))
    first = copy.deepcopy(node.normal_control_model_fault)
    for index in range(8):
        clock[0] += 20_000_000
        node.reach_failure('tb1', ValueError('later contradiction ' + str(index)))
    assert node.normal_control_model_fault == first
    assert retained_faults(events) == [first]
    assert len(publications(events)) == 1 and publications(events)[0]['reason'] == first['reason']
    assert requests == [True] and len(outputs(events)) == 3
    assert node.halted == 'normal_control_model_invalid' and node.reach_pending_release is None


def test_pre_takeover_noop_does_not_suppress_a_later_real_controlled_stop():
    node, _, events, _ = fault_fixture()
    phase = SimpleNamespace(node=node, controlled=False, stopping=False)
    phase.ensure_stop = MethodType(MotionControlPhase.ensure_stop, phase)
    node.control_phase = phase
    node.ensure_motion_output = MethodType(MotionSafety.ensure_motion_output, node)
    node.emit_motion = node.emit_reach_motion
    node.reach_failure('tb3', ValueError('first contradiction before takeover'))
    first = copy.deepcopy(node.normal_control_model_fault)
    assert node._reach_failure_stop_requested is False and phase.stopping is False
    assert outputs(events) == []
    # Exercise the same real stop method after its controlled precondition
    # changes; this does not synthesize a takeover or a normal safety ACK.
    phase.controlled = True
    node.reach_failure('tb1', ValueError('later fault while controlled'))
    assert phase.stopping is True and node._reach_failure_stop_requested is True
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))
    assert all(owner.stopped for owner in node.reach.values())
    assert node.normal_control_model_fault == first
    assert len(publications(events)) == len(retained_faults(events)) == 1


def test_publish_callback_reentry_and_exact_own_echo_cannot_rebroadcast_or_restop():
    node, _, events, requests = fault_fixture()
    publish = node.failure_pub.publish

    def receive_during_publish(message):
        publish(message)
        MotionSafety.receive_failure(node, message)
        node.reach_failure('tb2', ValueError('publication callback reentry'))

    node.failure_pub.publish = receive_during_publish
    node.reach_failure('tb3', ValueError('first contradiction'))
    assert len(publications(events)) == len(retained_faults(events)) == 1
    assert node.normal_control_model_fault['robot'] == 'tb3'
    assert requests == [True] and len(outputs(events)) == 3
    assert not any(row[0] == 'failure' for row in events)


def test_stop_barrier_reentry_is_deduplicated_and_original_zero_output_still_runs():
    node, _, events, requests = fault_fixture()

    def reentrant_stop():
        requests.append(True)
        node.reach_failure('tb1', ValueError('stop callback reentry'))
        node.emit_reach_motion(stop=True)

    node.control_phase.ensure_stop = reentrant_stop
    node.reach_failure('tb3', ValueError('first contradiction'))
    assert requests == [True]
    assert len(publications(events)) == len(retained_faults(events)) == 1
    assert node.normal_control_model_fault['robot'] == 'tb3'
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))


def test_fault_inside_joint_emission_does_not_reenter_stop_and_all_targets_are_zero():
    def reject_third(name, request, peers):
        if name == 'tb3':
            raise ValueError('late third-robot contradiction')
        return {'allow': True, 'reason': 'fixture_clear', 'output': [.2, 0.]}

    node, _, events, requests = fault_fixture(started=True, decider=reject_third)
    publish = node.failure_pub.publish

    def echo_during_joint_admission(message):
        publish(message)
        MotionSafety.receive_failure(node, message)
        node.reach_failure('tb1', ValueError('publication reentry during joint admission'))

    node.failure_pub.publish = echo_during_joint_admission
    node.emit_reach_motion()
    assert requests == [] and node._reach_emitting is False
    assert len(publications(events)) == len(retained_faults(events)) == 1
    assert node.normal_control_model_fault['robot'] == 'tb3'
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))
    assert all(owner.stopped for owner in node.reach.values())
    # A subsequent external fault callback can still request the real barrier.
    node.reach_failure('tb2', ValueError('later delivery'))
    assert requests == [True] and len(publications(events)) == 1


def test_publication_error_propagates_but_does_not_skip_stop_and_can_retry_same_first_fact():
    node, _, events, requests = fault_fixture()
    publish = node.failure_pub.publish

    def broken_publish(message):
        raise RuntimeError('publication failed')

    node.failure_pub.publish = broken_publish
    with pytest.raises(RuntimeError, match='publication failed'):
        node.reach_failure('tb3', ValueError('first contradiction'))
    assert requests == [True] and node.failure_sent is False
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))
    assert node.halted == 'normal_control_model_invalid'
    node.failure_pub.publish = publish
    node.reach_failure('tb1', ValueError('later contradiction'))
    assert len(publications(events)) == len(retained_faults(events)) == 1
    assert publications(events)[0]['robot'] == 'tb3' and publications(events)[0]['reason'] == 'first contradiction'
    assert requests == [True]


def test_publication_error_inside_joint_emission_still_stops_without_recursive_retry():
    node, _, events, requests = fault_fixture(started=True)
    # A genuine existing table gate fails in both the original phase and its
    # zero-stop emission. Publication must not recursively fail before zeros.
    node.received['safety_table_sha256'] = 'b' * 64
    attempts = []

    def broken_publish(message):
        attempts.append(json.loads(message.data))
        raise RuntimeError('publication failed during joint admission')

    node.failure_pub.publish = broken_publish
    with pytest.raises(RuntimeError, match='publication failed during joint admission'):
        node.emit_reach_motion()
    assert len(attempts) == 1 and len(retained_faults(events)) == 1
    assert node.normal_control_model_fault['robot'] == 'joint'
    assert node.normal_control_model_fault['reason'] == 'frozen safety table differs from actual phase'
    assert node.failure_sent is False and node._reach_emitting is False
    assert requests == [True] and node._reach_failure_stop_requested is True
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))
    assert all(owner.stopped for owner in node.reach.values())


@pytest.mark.parametrize('inside_emission', (False, True))
def test_fault_log_error_propagates_and_cannot_skip_the_actual_stop(inside_emission):
    node, _, events, requests = fault_fixture(started=True)
    record = node.record

    def broken_record(kind, payload):
        if kind == 'reach_model_failure':
            raise OSError('fault log write failed')
        record(kind, payload)

    node.record = broken_record
    with pytest.raises(OSError, match='fault log write failed'):
        if inside_emission:
            node.received['safety_table_sha256'] = 'b' * 64
            node.emit_reach_motion()
        else:
            node.reach_failure('tb3', ValueError('first contradiction'))
    assert node.normal_control_model_fault is not None
    assert node.halted == 'normal_control_model_invalid' and node.reach_pending_release is None
    assert node._reach_emitting is False and requests == [True]
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))


def test_stop_error_is_not_swallowed_or_marked_done_and_later_stop_can_retry():
    node, _, events, requests = fault_fixture()
    ensure_stop = node.control_phase.ensure_stop

    def broken_stop():
        raise RuntimeError('stop barrier failed')

    node.control_phase.ensure_stop = broken_stop
    with pytest.raises(RuntimeError, match='stop barrier failed'):
        node.reach_failure('tb3', ValueError('first contradiction'))
    assert node._reach_failure_stop_requested is False and node.failure_sent is True
    assert node.halted == 'normal_control_model_invalid' and node.reach_pending_release is None
    node.control_phase.ensure_stop = ensure_stop
    node.reach_failure('tb1', ValueError('later contradiction'))
    assert requests == [True] and node._reach_failure_stop_requested is True
    assert len(publications(events)) == len(retained_faults(events)) == 1
    assert len(outputs(events)) == 3 and all(row[2:] == (0., 0.) for row in outputs(events))


@pytest.mark.parametrize('changed', ({'epoch': 'other-episode'}, {'reason': 'another failure'},
                                    {'robot': 'tb2'}, {'clock_ns': 2_000_000_000}))
def test_same_component_external_failure_is_not_ignored_by_partial_payload_match(changed):
    node, _, events, requests = fault_fixture()
    node.reach_failure('tb3', ValueError('first contradiction'))
    payload = publications(events)[0]
    payload.update(changed)
    message = String(data=json.dumps(payload, sort_keys=True, allow_nan=False))
    MotionSafety.receive_failure(node, message)
    assert requests == [True, True]
    assert any(row == ('failure', {'data': message.data}) for row in events)
    assert node.normal_control_model_fault['robot'] == 'tb3'
    assert node.normal_control_model_fault['reason'] == 'first contradiction'
    assert len(publications(events)) == 1


def test_cached_echo_from_old_epoch_does_not_skip_current_external_failure_handling():
    node, _, events, requests = fault_fixture()
    node.reach_failure('tb3', ValueError('first contradiction'))
    message = String(data=node._reach_failure_message)
    node.epoch = 'new-episode'
    MotionSafety.receive_failure(node, message)
    assert requests == [True, True]
    assert any(row == ('failure', {'data': message.data}) for row in events)


def test_healthy_reach_output_does_not_publish_or_log_any_failure():
    node, _, events, requests = fault_fixture(started=True)
    node.emit_reach_motion()
    assert publications(events) == retained_faults(events) == []
    assert node.failure_sent is False and node.normal_control_model_fault is None
    assert node._reach_failure_message is None and node._reach_failure_stop_requested is False
    assert requests == []
    assert len(outputs(events)) == 3 and any(row[2] > 0 for row in outputs(events))


def test_original_invalid_ingress_receipts_remain_complete_while_fault_broadcast_is_once(monkeypatch):
    node, _, events, requests = fault_fixture()
    node.reach_publisher_gids = {}
    node.try_reach_release = lambda: None
    monkeypatch.setattr(motion_safety, 'publisher_graph_identity', lambda *args: {
        'valid': True, 'endpoints': [{'endpoint_gid': 'a' * 48}]})

    def reject(value):
        raise ValueError('calibration publication stream gap/regression')

    node.reach['tb1'].receive_calibration = reject
    messages = [String(data=json.dumps({'epoch': node.epoch, 'artificial_sequence': i})) for i in (1, 2)]
    for message in messages:
        MotionSafety.receive_reach_feed(node, message, 'tb1', 'calibration')
    ingress = [row[1] for row in events if row[0] == 'invalid_reach_driver_ingress']
    assert [row['raw_json'] for row in ingress] == [message.data for message in messages]
    assert len(publications(events)) == len(retained_faults(events)) == 1
    assert requests == [True] and node.halted == 'normal_control_model_invalid'
