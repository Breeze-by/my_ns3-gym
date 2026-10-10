"""Soft heading preferences retain full admission and bind exact native sources."""
import base64
import copy
import gzip
import json
import math
from pathlib import Path

import pytest
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.serialization import serialize_message
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as c
from check_p2c_gate import exploration_travel_audit
from p2c_departure_heading import departure_heading_audit, heading_preference_factor
from test_known_search_fallback import original_snapshot_node


@pytest.mark.parametrize('distance', [0., .5, 2., 10.])
@pytest.mark.parametrize('angle', [0., math.pi / 2, math.pi, 5 * math.pi])
def test_turn_penalty_is_bounded_and_wraps_to_the_shortest_angle(distance, angle):
    saved = c.exploration_departure_heading((0., 0.), angle, (1., 0.), distance)
    wrapped = min(angle % (2 * math.pi), 2 * math.pi - angle % (2 * math.pi))
    assert math.isclose(saved['angle_rad'], wrapped, abs_tol=1e-12)
    assert .25 <= saved['factor'] <= 1.
    assert math.isclose(saved['factor'], max(.25, (1 + distance)**1.5 /
        ((1 + distance)**1.5 + wrapped / .7)))
    if wrapped == 0:
        assert saved['factor'] == 1.


@pytest.mark.parametrize('position,yaw,target,distance', [
    (None, 0., (1., 0.), 1.), ((0., 0.), None, (1., 0.), 1.),
    ((0., 0.), float('nan'), (1., 0.), 1.), ((0., 0.), 0., (float('inf'), 0.), 1.),
    ((0., 0.), 0., (1., 0.), -1.), ((0., 0.), 0., (1., 0.), float('inf')),
    ((0., 0.), 0., (1., 0.), 1e308),
])
def test_unavailable_estimate_keeps_the_original_score(position, yaw, target, distance):
    assert c.exploration_departure_heading(position, yaw, target, distance) is None


def publish_decision(node, sent, name, assignment):
    goal = PoseStamped(); goal.pose.position.x = assignment.navigation_x
    goal.pose.position.y = assignment.navigation_y
    yaw = assignment.navigation_yaw or 0.
    goal.pose.orientation.z, goal.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
    kind = ('initial_visual_search' if node.exploration_travel_choices.get(name, {}).get('search_kind') == 'known_space'
        else 'exploration')
    if c.HeadquartersControl.record_navigation_decision(node, name, kind, goal, None, node.goal_routes[name]):
        sent.append((name, assignment))


@pytest.mark.parametrize('index', range(6))
def test_original_snapshot_reproduces_frozen_and_prototype_choices(monkeypatch, index):
    path = Path(__file__).parent / 'fixtures/p2c_v77_departure_heading.json.gz'
    saved = json.load(gzip.open(path, 'rt'))
    assert saved['source_commit'] == 'ff2a22d4738a9a4ae15867d62a256d2b8c26ff67'
    sample = saved['snapshots'][index]
    namespace = dict(vars(c))
    exec(compile(saved['original_sources']['assign'], '<ff2a22d assign>', 'exec'), namespace)
    old_assign = namespace['assign_idle_robots']
    exec(compile(saved['original_sources']['preference'], '<ff2a22d preference>', 'exec'), namespace)
    old_preference = namespace['frontier_travel_preference']
    for label, assign in [('original', old_assign), ('prototype', c.HeadquartersControl.assign_idle_robots)]:
        node, requests, events, sent = original_snapshot_node(copy.deepcopy(sample))
        node.robot_yaws = sample['delivered_yaws']
        node.send_goal = lambda name, a: publish_decision(node, sent, name, a)
        with monkeypatch.context() as patch:
            if label == 'original':
                patch.setattr(c.HeadquartersControl, 'frontier_travel_preference', old_preference)
            assign(node)
        expected = sample['comparison'][label]
        assert len(sent) == len(expected['selections'])
        assert [list(row) for row in requests] == expected['charge_requests']
        for (name, a), row in zip(sent, expected['selections']):
            assert name == row['robot']
            assert (a.x, a.y) == tuple(row['target'])
            assert math.isclose(a.path_distance_m, row['path_distance_m'], abs_tol=1e-10)
            assert math.isclose(a.utility, row['utility'], abs_tol=1e-8)
        result = exploration_travel_audit(events, True, True, True, True, True, True, True, True)
        assert result['executed_frontier_witnesses'] == len(sent)


def example():
    odom = Odometry(); odom.header.stamp.sec = 10
    odom.pose.pose.position.x, odom.pose.pose.position.y = 1., 2.
    odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = math.sin(.4), math.cos(.4)
    transform = TransformStamped(); transform.header.stamp.sec = 10; transform.header.stamp.nanosec = 200000000
    transform.header.frame_id, transform.child_frame_id = 'map', 'tb1/odom'
    transform.transform.translation.x, transform.transform.translation.y = .3, -.2
    transform.transform.rotation.z, transform.transform.rotation.w = math.sin(.2), math.cos(.2)
    position = (math.cos(.4) - 2. * math.sin(.4) + .3, math.sin(.4) + 2. * math.cos(.4) - .2)
    heading = c.exploration_departure_heading(position, 1.2, (3., 4.), 5.)
    heading.update(pose_source_time=10., frame_source_time=10., evaluated_at_sec=11., source='ap_delivered_pose_and_heading')
    event = dict(event='coordinator_navigation_decision', kind='exploration', robot='tb1', event_time=11.5,
        current_position=list(position), inputs={f'tb1/{kind}':dict(source_time=10.) for kind in ('pose_state','frame_state')},
        travel_preference=dict(ranking_time_sec=11., own_nominal_distance_m=5., target=[3.,4.], departure_heading=heading))
    return event, odom, TFMessage(transforms=[transform])


@pytest.mark.parametrize('tamper', [None, 'missing', 'factor', 'yaw', 'pose', 'source', 'future', 'cdr_missing', 'cdr_stamp', 'cdr_yaw'])
def test_independent_reader_rejects_tampered_geometry_sources_and_native_cdr(tmp_path, tamper):
    event, odom, frame = example(); heading = event['travel_preference']['departure_heading']
    if tamper == 'missing': del event['travel_preference']['departure_heading']
    if tamper == 'factor': heading['factor'] = 1.
    if tamper == 'yaw': heading['yaw'] += .3
    if tamper == 'pose': heading['position'][0] += .1
    if tamper == 'source': heading['frame_source_time'] = 9.
    if tamper == 'future': event['event_time'] = 9.9
    if tamper == 'cdr_stamp': odom.header.stamp.sec = 9
    if tamper == 'cdr_yaw': odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = 0., 1.
    ledger = tmp_path / 'ledger.jsonl'; ledger.write_text(json.dumps(event) + '\n')
    capture = tmp_path / 'inputs.jsonl.gz'
    with gzip.open(capture, 'wt') as stream:
        for topic, message in [('/tb1/odom', odom), ('/tb1/tf', frame)]:
            if tamper == 'cdr_missing' and topic.endswith('/tf'):continue
            stream.write(json.dumps(dict(topic=topic, cdr=base64.b64encode(serialize_message(message)).decode())) + '\n')
    if tamper is None:
        assert departure_heading_audit(ledger, capture, True)['native_source_bindings'] == 2
    else:
        with pytest.raises(AssertionError): departure_heading_audit(ledger, capture, True)


def test_missing_witness_is_optional_only_when_not_required():
    event, _, _ = example(); del event['travel_preference']['departure_heading']
    assert heading_preference_factor(event) == 1.
    with pytest.raises(AssertionError): heading_preference_factor(event, True)


@pytest.mark.parametrize('reason', ['fresh', 'mapping_only', 'battery_off', 'stale', 'future', 'missing_frame', 'missing_yaw'])
def test_heading_preference_uses_only_a_fresh_complete_task_source(reason):
    from test_known_search_fallback import fallback_node
    from test_exploration_charging import assignment
    node, _, _, _ = fallback_node(); node.robot_yaws = {'tb1':math.pi}
    if reason == 'mapping_only':node.enable_rally=False
    if reason == 'battery_off':node.enable_battery=False
    if reason == 'stale':node.robot_odom_received_at['tb1']=7.9
    if reason == 'future':node.robot_tf_received_at['tb1']=10.1
    if reason == 'missing_frame':node.robot_tf_received_at['tb1']=None
    if reason == 'missing_yaw':node.robot_yaws['tb1']=None
    saved=c.HeadquartersControl.frontier_travel_preference(node,'tb1',assignment(4.,3.),{})
    assert ('departure_heading' in saved) == (reason == 'fresh')
    if reason == 'fresh':assert .25 <= saved['departure_heading']['factor'] < 1.


def test_turn_speed_matches_all_existing_controller_parameters():
    import yaml
    directory=Path(__file__).resolve().parents[2]/'multi_robot/params'
    for index in range(1,4):
        document=yaml.safe_load((directory/f'nav2_params_tb{index}_0.yaml').read_text())
        assert document['controller_server']['ros__parameters']['FollowPath']['rotate_to_heading_angular_vel']==.7
