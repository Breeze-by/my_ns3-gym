"""Full measured velocity and honest invalid-normal/zero-cleanup regressions."""

from collections import deque
import copy
import math
from types import SimpleNamespace

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import pytest

from multi_robot_exploration.motion_safety import MotionSafety
from multi_robot_exploration.mr3_control_phase import ControlPhaseClient
from multi_robot_exploration.mr3_information import odom_payload
from multi_robot_exploration.mr3_motion_safety import (
    ROBOTS, SettledTurnTracker, measured_velocity_error, valid_state,
)
from test_motion_safety import node_fixture, state
from test_mr3_motion_control import dependencies, request, send, setup, takeover


PEAK_VX = .25164306169129336
PEAK_VY = -.17380055821233364


def odometry(source_ns, vx=.1, vy=0., wx=0., wy=0., wz=0.):
    message = Odometry()
    message.header.frame_id, message.child_frame_id = 'odom', 'base_footprint'
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(source_ns, 10**9)
    message.pose.pose.orientation.w = 1.
    message.twist.twist.linear.x, message.twist.twist.linear.y = vx, vy
    message.twist.twist.angular.x = wx
    message.twist.twist.angular.y = wy
    message.twist.twist.angular.z = wz
    return message


def model_node(clock_ns=1_020_000_000, release_ns=1_000_000_000):
    own, peers = {}, []
    histories = {name: {'odom': deque(), 'tf': deque()} for name in ROBOTS}
    trackers = {name: SettledTurnTracker() for name in ROBOTS}
    for index, name in enumerate(ROBOTS):
        message = odometry(clock_ns)
        histories[name]['odom'].append((1, message))
        value = state(name, index * 3., 0., v=.1, stamp=clock_ns / 1e9)
        value.pop('odometry')  # Match the actual source-pinned own-state projection.
        value.update(input_sequences={'odom': 1, 'tf': 1},
                     odom_source_stamp=clock_ns / 1e9, tf_source_stamp=clock_ns / 1e9)
        own[name] = value
        peers.append(dict(value, sequence=1, odometry=odom_payload(message)))
        if release_ns is not None:
            trackers[name].release(release_ns)
    node = SimpleNamespace(
        epoch='episode', started=release_ns is not None, stop_time=None, halted=None,
        normal_control_model_fault=None, settled_turn=trackers,
        own_input_history=histories, local_state=lambda name: own[name],
        received={'epoch': 'episode', 'sequence': 1, 'robots': peers},
        odometry={}, input_sequences={name: {'odom': 1} for name in ROBOTS},
        record=lambda *args: None)
    node.normal_velocity_fault = lambda target: MotionSafety.normal_velocity_fault(node, target)
    return node, own


def test_v12_full_planar_peak_is_rejected_for_own_scalar_and_received_raw():
    # V12 w0/e3 tb2 source92.617, raw input2650: the original failure stays retained.
    value = state('tb1', 0., 0., v=PEAK_VX)
    value['planar_speed_mps'] = math.hypot(PEAK_VX, PEAK_VY)
    value['odometry']['twist']['twist']['linear']['y'] = PEAK_VY
    assert value['planar_speed_mps'] == .3058281617710947
    assert not valid_state(value, 1., 'episode', require_raw=True)
    del value['odometry']
    assert not valid_state(value, 1., 'episode')


@pytest.mark.parametrize('vx,vy,accepted', [
    (.3, 0., True), (-.3, 0., True), (.18, .24, True),
    (math.nextafter(.3, math.inf), 0., False), (PEAK_VX, PEAK_VY, False),
])
def test_measured_boundary_has_no_command_endpoint_tolerance(vx, vy, accepted):
    value = state('tb1', 0., 0., v=vx)
    value['planar_speed_mps'] = math.hypot(vx, vy)
    value['odometry']['twist']['twist']['linear']['y'] = vy
    assert valid_state(value, 1., 'episode', require_raw=True) is accepted


def test_raw_required_peer_and_exact_raw_scalar_v_w_binding():
    value = state('tb1', 0., 0., v=.1)
    rawless = dict(value)
    del rawless['odometry']
    assert valid_state(rawless, 1., 'episode')
    assert not valid_state(rawless, 1., 'episode', require_raw=True)
    for key, invalid in [('planar_speed_mps', .2), ('v', 0.), ('w', False)]:
        changed = copy.deepcopy(value)
        changed[key] = invalid
        assert measured_velocity_error(changed, require_raw=True) is not None


def test_rawless_scalar_cannot_hide_impossible_v_or_untyped_w():
    value = state('tb1', 0., 0., v=.1)
    del value['odometry']
    value['planar_speed_mps'] = .05
    assert measured_velocity_error(value) == 'inconsistent_planar_speed'
    value['planar_speed_mps'] = .1
    for key in ('v', 'w'):
        for bad in (True, None, float('nan'), float('inf')):
            changed = dict(value, **{key: bad})
            assert measured_velocity_error(changed) == 'invalid_measured_velocity'


def test_missing_nonfinite_or_malformed_raw_is_rejected_without_scalar_bypass():
    for bad in (None, [], {'twist': None}, {'twist': {'twist': None}}):
        value = state('tb1', 0., 0., v=.1)
        value['odometry'] = bad
        assert not valid_state(value, 1., 'episode', require_raw=True)
    for bad in (True, float('nan'), float('inf')):
        value = state('tb1', 0., 0., v=.1)
        value['odometry']['twist']['twist']['linear']['y'] = bad
        assert not valid_state(value, 1., 'episode', require_raw=True)


def test_causal_history_peak_is_not_erased_by_a_newer_healthy_selected_sample():
    node, own = model_node(92_660_000_000, 75_100_000_000)
    node.own_input_history['tb2']['odom'] = deque([
        (2650, odometry(92_617_000_000, PEAK_VX, PEAK_VY)),
        (2651, odometry(92_651_000_000))])
    own['tb2']['input_sequences']['odom'] = 2651
    own['tb2'].update(source_stamp=92.651, odom_source_stamp=92.651)
    fault = node.normal_velocity_fault(92_660_000_000)
    assert fault['reason'] == 'measured_planar_speed_exceeded'
    assert fault['role'] == 'own_history' and fault['input_sequence'] == 2650
    assert fault['odom_source_ns'] == 92_617_000_000
    assert fault['classification'] == 'normal_control_model_invalid_not_task_attributed'


def test_full_own_angular_xyz_is_checked_from_raw_not_only_projected_wz():
    node, own = model_node()
    node.own_input_history['tb1']['odom'] = deque([(1, odometry(1_020_000_000, wx=1.3))])
    assert measured_velocity_error(own['tb1']) is None  # Rawless projection has wz only.
    assert node.normal_velocity_fault(1_020_000_000)['reason'] == 'measured_angular_speed_exceeded'


def test_future_callback_and_unselected_warmup_peak_do_not_create_a_new_latch():
    node, _ = model_node()
    node.own_input_history['tb1']['odom'].appendleft((0, odometry(990_000_000, vx=.9)))
    MotionSafety.receive_odom(node, odometry(1_039_000_000, vx=.31), 'tb1')
    assert node.halted is None
    assert node.normal_velocity_fault(1_020_000_000) is None
    assert node.normal_velocity_fault(1_040_000_000)['odom_source_ns'] == 1_039_000_000


def test_malformed_received_twist_has_a_structured_fault_not_attribute_error():
    node, _ = model_node()
    node.received['robots'][0]['odometry']['twist'] = None
    fault = node.normal_velocity_fault(1_020_000_000)
    assert fault['reason'] == 'invalid_measured_velocity' and fault['twist'] is None


def test_actual_history_fault_produces_negative_ack_and_explicit_stop_remains_usable():
    node, phase = setup()
    takeover(node, phase)
    model, own = model_node(node.clock, node.clock - 20_000_000)
    model.own_input_history['tb1']['odom'] = deque([
        (2, odometry(node.clock - 1_000_000, PEAK_VX, PEAK_VY))])
    own['tb1'].update(v=PEAK_VX, planar_speed_mps=math.hypot(PEAK_VX, PEAK_VY),
                      source_stamp=(node.clock - 1_000_000) / 1e9,
                      odom_source_stamp=(node.clock - 1_000_000) / 1e9)
    own['tb1']['input_sequences']['odom'] = 2
    node.normal_velocity_fault = model.normal_velocity_fault
    node.received = model.received
    refs = dependencies(node, phase)
    identity = 'boundary' + str(node.clock)
    send(phase, request(node, 'commit', identity, **refs))
    ack = phase.responses[identity][1]
    assert ack['ok'] is False and ack['error'] == 'normal_control_model_invalid'
    assert node.halted == 'normal_control_model_invalid'
    assert node.normal_control_model_fault['input_sequence'] == 2
    assert (node.clock, 'normal') not in node.calls and (node.clock, 'stop') in node.calls
    client = ControlPhaseClient(node.epoch)
    client.begin('motion', 'commit', node.clock, request_id=identity)
    client.receive('motion', ack, node.clock, node.clock)
    assert client.consume(allow_error=True)['ok'] is False
    with pytest.raises(ValueError):
        client.begin('motion', 'commit', node.clock + 20_000_000)
    send(phase, request(node, 'stop'))
    assert phase.responses['stop40000000'][1]['ok'] is True
    assert phase.responses['stop40000000'][1]['status']['phase_kind'] == 'stop'


def test_model_invalid_stop_has_real_local_receipts_without_generic_task_failure():
    node, clock, events = node_fixture()
    node.started, node.halted = True, 'normal_control_model_invalid'
    node.completed_motion, node.issued_motion = {}, set()
    node.control_phase = SimpleNamespace(
        stop_publisher=SimpleNamespace(publish=lambda msg: events.append(
            ('stop_status', msg.data))),
        poll=lambda: None)
    MotionSafety.emit_motion(node, stop=True)
    assert not any(event[0] in ('failure_pub', 'stop_status') for event in events)
    for name in ROBOTS:
        MotionSafety.receive_actual(node, Twist(), name)
    assert (clock[0], 'stop') in node.completed_motion
    assert not any(event[0] == 'failure_pub' for event in events)
