"""Clock advances in final preparation/publication must never create a goal owner."""
import copy
import json
import math
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from geometry_msgs.msg import PoseStamped
from builtin_interfaces.msg import Time

from multi_robot_exploration import control as c
from test_control import target_scan_node
from test_rally_observation_recovery import observer_node


def boundary_node():
    clock = [10.]
    sources = {
        'headquarters/fused_map_snapshot': dict(source_time=10., ttl_sec=5.),
        'headquarters/target_detection': dict(source_time=10., ttl_sec=60.),
        'tb1/pose_state': dict(source_time=10., ttl_sec=2.),
        'tb1/frame_state': dict(source_time=10., ttl_sec=2.),
        'tb1/map_snapshot': dict(source_time=10., ttl_sec=5.),
        'tb1/battery_state': dict(source_time=10., ttl_sec=5.),
    }
    events = []
    client = Mock(); client.server_is_ready.return_value = True
    pose = c.RallyPose(2.05, 1.05, 0.)
    node = SimpleNamespace(now=lambda: clock[0], task_state='RALLY',
        input_freshness_details=lambda: copy.deepcopy(sources),
        consumed_publisher=SimpleNamespace(publish=lambda msg: events.append(json.loads(msg.data))),
        robot_positions={'tb1': (1.05, 1.05)}, robot_nav_clients={'tb1': client},
        fresh_robot_inputs=lambda: clock[0] <= 12., fresh_target=lambda: True,
        return_yield_targets={}, battery_modes={'tb1': 'ACTIVE'}, enable_battery=False,
        rally_attempts={'tb1': 0}, rally_max_retries=2, rally_targets={'tb1': pose},
        rally_goal_pending={'tb1': False}, rally_leg_routes={'tb1': ()}, rally_leg_poses={'tb1': None},
        get_logger=lambda: Mock(), resolution=.1, origin=(0., 0.),
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: Time(sec=10))),
        rally_goal_response=Mock())
    node.record_navigation_decision=lambda *args: c.HeadquartersControl.record_navigation_decision(node, *args)
    return node, clock, sources, events, client, pose


@pytest.mark.parametrize('at', [12.01, 9.99, math.nan, math.inf])
def test_expired_future_or_nonfinite_boundary_has_no_publication(at):
    node, clock, sources, events, _, _ = boundary_node(); original=copy.deepcopy(sources)
    clock[0] = at
    assert not node.record_navigation_decision('tb1', 'rally', PoseStamped())
    assert not events and sources == original


@pytest.mark.parametrize('sample', [dict(source_time=None, ttl_sec=2.),
    dict(source_time=math.nan, ttl_sec=2.), dict(source_time=math.inf, ttl_sec=2.),
    dict(source_time='10', ttl_sec=2.), dict(source_time=10.),
    dict(source_time=10., ttl_sec=0.), dict(source_time=10., ttl_sec=-1.),
    dict(source_time=10., ttl_sec=math.nan), dict(source_time=10., ttl_sec=None)])
def test_missing_or_invalid_original_lease_is_rejected(sample):
    node, _, sources, events, _, _=boundary_node();sources['tb1/pose_state']=sample
    assert not node.record_navigation_decision('tb1', 'rally', PoseStamped())
    assert not events


def test_absent_leases_are_not_an_empty_success():
    node, _, sources, events, _, _=boundary_node();sources.clear()
    assert not node.record_navigation_decision('tb1', 'rally', PoseStamped())
    assert not events


@pytest.mark.parametrize('kind,admitted', [('rally', False), ('target_survey', False),
    ('target_observation_heading', False), ('local_return_yield', True),
    ('target_reacquisition_scan', True), ('target_reacquisition_exploration', True)])
def test_only_original_target_independent_kinds_can_ignore_an_old_target(kind, admitted):
    node, _, sources, events, _, _=boundary_node();sources['headquarters/target_detection']['source_time']=-100.
    if kind=='target_reacquisition_exploration':node.goal_routes={'tb1': ((1.05,1.05),)}
    assert node.record_navigation_decision('tb1', kind, PoseStamped()) is admitted
    assert bool(events) is admitted


def test_expiry_during_prepared_json_rejects_before_publication(monkeypatch):
    node, clock, sources, events, _, _=boundary_node();original=copy.deepcopy(sources)
    dumps=c.json.dumps
    def slow(value, **kwargs):
        if value.get('event')=='coordinator_navigation_decision':clock[0]=12.1
        return dumps(value, **kwargs)
    monkeypatch.setattr(c.json, 'dumps', slow)
    assert not node.record_navigation_decision('tb1', 'rally', PoseStamped())
    assert not events and sources==original


def test_expiry_during_final_metadata_encoding_rejects_before_publication(monkeypatch):
    node, clock, _, events, _, _=boundary_node();dumps=c.json.dumps
    def slow(value, **kwargs):
        if 'dispatch_goal_source_time_sec' in value:clock[0]=12.1
        return dumps(value, **kwargs)
    monkeypatch.setattr(c.json, 'dumps', slow)
    assert not node.record_navigation_decision('tb1', 'rally', PoseStamped())
    assert not events


def test_rally_logger_delay_cannot_create_pending_state_or_consume_an_attempt():
    node, clock, sources, events, client, pose=boundary_node();original=copy.deepcopy(sources)
    logger=Mock();logger.info.side_effect=lambda _: clock.__setitem__(0,12.1);node.get_logger=lambda:logger
    c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,((1.05,1.05),(2.05,1.05))))
    assert not client.send_goal_async.called and not events
    assert not node.rally_goal_pending['tb1'] and not node.rally_leg_routes['tb1']
    assert node.rally_leg_poses['tb1'] is None and node.rally_attempts['tb1']==0
    assert sources==original


@pytest.mark.parametrize('cause', ['clock', 'shutdown'])
def test_expiry_after_private_publication_revokes_before_goal_submission(cause):
    node, clock, sources, events, client, pose=boundary_node();original=copy.deepcopy(sources)
    def publish(msg):
        events.append(json.loads(msg.data))
        if cause=='clock':clock[0]=12.1
        else:node.shutdown_requested=True
    node.consumed_publisher.publish=publish
    c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,((1.05,1.05),(2.05,1.05))))
    assert not client.send_goal_async.called and not node.rally_goal_pending['tb1']
    assert not node.rally_leg_routes['tb1'] and node.rally_leg_poses['tb1'] is None
    assert node.rally_attempts['tb1']==0 and sources==original
    assert [e['event'] for e in events]==['coordinator_navigation_decision','coordinator_navigation_dispatch_revoked']
    assert events[0]['event_time']==events[0]['dispatch_goal_source_time_sec']==10.
    assert events[1]['decision_time_sec']==10. and events[1]['dispatch_lease_deadline_sec']==12.
    assert events[1]['shutdown_requested']==(cause=='shutdown')


def test_exact_original_ttl_boundary_and_goal_header_keep_the_original_stamps():
    node, clock, sources, events, client, pose=boundary_node();original=copy.deepcopy(sources);clock[0]=12.
    c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,((1.05,1.05),(2.05,1.05))))
    assert client.send_goal_async.call_count==1 and node.rally_goal_pending['tb1']
    header=client.send_goal_async.call_args.args[0].pose.header.stamp
    assert header.sec+header.nanosec/1e9==events[0]['event_time']==12.
    assert events[0]['inputs']['tb1/pose_state']['source_time']==10.
    assert events[0]['inputs']['tb1/pose_state']['age_sec']==2. and sources==original


def test_survey_failed_boundary_preserves_attempt_and_owner_state():
    node, client=observer_node();node.record_navigation_decision=lambda *args:False
    assert not c.HeadquartersControl.send_survey_goal(node,'tb1',c.RallyPose(2.05,2.05,math.pi/2),True)
    assert not client.send_goal_async.called and node.survey_attempts==0
    assert not node.survey_goal_pending and node.survey_goal_handle is None


def test_reacquisition_failed_boundary_does_not_occupy_a_robot_or_heading():
    node, goals, _=target_scan_node();node.record_navigation_decision=lambda *args:False
    original=copy.deepcopy(node.target_scan_steps)
    c.HeadquartersControl.reacquire_target_by_scanning(node)
    assert not goals and node.target_scan_robot is None and node.target_scan_steps==original


def test_frontier_failed_boundary_releases_an_unsent_route():
    node, _, _, _, client, _=boundary_node();node.task_state='EXPLORE'
    node.robot_states={'tb1':'active'};node.goal_targets={'tb1':object()};node.goal_routes={'tb1':((1.,1.),(2.,1.))}
    node.record_navigation_decision=lambda *args:False
    a=c.Assignment(c.Viewpoint(0,10,20,10,20,5,2),2.05,1.05,1.,1.,2.05,1.05)
    c.HeadquartersControl.send_goal(node,'tb1',a)
    assert not client.send_goal_async.called and node.robot_states['tb1']=='idle'
    assert node.goal_targets['tb1'] is None and node.goal_routes['tb1']==()
