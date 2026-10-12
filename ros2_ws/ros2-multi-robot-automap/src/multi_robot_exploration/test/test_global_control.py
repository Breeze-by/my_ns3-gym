"""Real node construction, synthetic action outcomes; no physical task credit."""
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.task import Future
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as c
from multi_robot_exploration.fleet_planning import MotionProposal
from multi_robot_exploration.global_control import GlobalHeadquartersControl


@pytest.fixture
def node():
    rclpy.init(args=['--ros-args', '-p', 'robot_count:=1', '-p', 'enable_battery:=true',
                    '-p', 'enable_rally:=true'])
    n = GlobalHeadquartersControl()
    for timer in n.timers:
        timer.cancel()
    n.now = lambda: 10.
    grid = OccupancyGrid()
    grid.header.stamp.sec = 10
    grid.header.frame_id = 'map'
    grid.info.width, grid.info.height, grid.info.resolution = 80, 80, .1
    grid.info.origin.orientation.w = 1.
    grid.data = [0] * 6400
    n.map_callback(grid)
    n.robot_map_callback(grid, 'tb1')
    frame = TransformStamped()
    frame.header.stamp.sec = 10
    frame.header.frame_id, frame.child_frame_id = 'map', 'odom'
    frame.transform.rotation.w = 1.
    n.robot_tf_callback(TFMessage(transforms=[frame]), 'tb1')
    odom = Odometry()
    odom.header.stamp.sec = 10
    odom.pose.pose.position.x, odom.pose.pose.position.y = 1.25, 1.25
    odom.pose.pose.orientation.w = 1.
    n.robot_odom_callback(odom, 'tb1')
    state = dict(mode='ACTIVE', stamp_sec=10., energy=40., charge_x=1.25,
        charge_y=1.25, capacity=100., charge_target_fraction=.8, charge_radius_m=.8,
        move_cost_per_m=1., idle_cost_per_sec=.02, return_path_factor=2.,
        nominal_speed_mps=.18, return_safety_margin=8., charge_duration_sec=6.)
    n.battery_state_callback(String(data=json.dumps(state)), 'tb1')
    n.consumed_publisher = Mock()
    try:
        yield n
    finally:
        n.shutdown_requested = True
        n.destroy_node()
        rclpy.shutdown()


def request(node, kind='exploration'):
    snapshot = node._snapshot()
    assert snapshot is not None
    proposal = MotionProposal('tb1', kind, c.RallyPose(2.25, 1.25, 0.),
        ((1.25, 1.25), (2.25, 1.25)), 1., 15., frozenset({1}))
    pending = Future()
    client = Mock()
    client.server_is_ready.return_value = True
    client.send_goal_async.return_value = pending
    node.robot_nav_clients['tb1'] = client
    assert node._send_motion(snapshot, proposal)
    return snapshot, proposal, pending, client, node.navigation_tasks['tb1']


def accept(node, pending):
    result = Future()
    handle = Mock()
    handle.accepted = True
    handle.get_result_async.return_value = result
    pending.set_result(handle)
    node.drain_action_done_callbacks()
    return handle, result


def test_pending_cancel_retains_owner_until_matching_real_future_closes(node):
    snapshot, proposal, pending, client, task = request(node)
    assert not node._send_motion(snapshot, proposal)
    assert client.send_goal_async.call_count == 1
    node.cancel_navigation('tb1', 'local_return')
    result = Future()
    handle = Mock()
    handle.accepted = True
    handle.get_result_async.return_value = result
    pending.set_result(handle)
    assert node.navigation_tasks['tb1'].handle is None
    node.drain_action_done_callbacks()
    assert handle.cancel_goal_async.called and node.navigation_tasks['tb1'] is task
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    assert 'tb1' in node.navigation_tasks
    node.drain_action_done_callbacks()
    assert not node.navigation_tasks and not node.successful_exploration_legs
    assert node.global_nav_failures.get('tb1', 0) == 0


def test_old_result_cannot_release_new_navigation_generation(node):
    _, _, pending, _, old = request(node)
    _, result = accept(node, pending)
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    node.drain_action_done_callbacks()
    _, _, _, _, current = request(node)
    node._goal_result(old, result)
    assert node.navigation_tasks['tb1'] is current
    assert node.successful_exploration_legs['tb1'] == 1


@pytest.mark.parametrize('kind,credit', [('exploration', 1), ('local_return_yield', 0),
    ('charge_clearance', 0), ('rally_yield', 0), ('target_information_survey', 0)])
def test_only_real_ordinary_success_counts_as_exploration_work(node, kind, credit):
    if kind in ('rally_yield', 'target_information_survey'):
        node.target = (3., 3.)
        node.target_received_source_time = 10.
        node.task_state = 'RALLY' if kind == 'rally_yield' else 'FOUND'
    _, _, pending, _, _ = request(node, kind)
    _, result = accept(node, pending)
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    node.drain_action_done_callbacks()
    assert node.successful_exploration_legs.get('tb1', 0) == credit
    assert not node.navigation_tasks


def test_encoding_delay_cannot_send_an_expired_navigation(node):
    snapshot = node._snapshot()
    proposal = MotionProposal('tb1', 'exploration', c.RallyPose(2.25, 1.25, 0.),
        ((1.25, 1.25), (2.25, 1.25)), 1., 15.)
    client = Mock()
    client.server_is_ready.return_value = True
    node.robot_nav_clients['tb1'] = client
    original = node._emit
    def slow_proof(event, **details):
        original(event, **details)
        if event == 'coordinator_global_motion_admission':
            node.now = lambda: 12.1
    node._emit = slow_proof
    assert not node._send_motion(snapshot, proposal)
    assert not client.send_goal_async.called and not node.navigation_tasks


def test_late_acceptance_cancels_expired_sources_without_new_work(node):
    _, _, pending, _, task = request(node)
    node.now = lambda: 12.1
    handle, result = accept(node, pending)
    assert task.cancel_reason == 'source_expired_at_acceptance'
    assert handle.cancel_goal_async.called
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    node.drain_action_done_callbacks()
    assert not node.navigation_tasks and not node.successful_exploration_legs


def test_future_and_repeated_battery_sources_cannot_change_received_state(node):
    original = dict(node.battery_states['tb1'])
    bad = {**original, 'mode': 'RETURNING', 'stamp_sec': 10.1}
    node.battery_state_callback(String(data=json.dumps(bad)), 'tb1')
    assert node.battery_states['tb1'] == original
    bad['stamp_sec'] = 10.
    node.battery_state_callback(String(data=json.dumps(bad)), 'tb1')
    assert node.battery_states['tb1'] == original


def test_admission_path_cache_cannot_reuse_an_obsolete_map_or_body_epoch(node):
    first = node._snapshot()
    cache = node._admission_caches(first, 'tb1')
    cache['motion_routes'] = {'obsolete': True}
    assert node._admission_caches(first, 'tb1') is cache and 'motion_routes' in cache
    moved = replace(first, positions={'tb1': (1.45, 1.25)})
    assert 'motion_routes' not in node._admission_caches(moved, 'tb1')
    grid = first.grid.copy()
    grid[12, 22] = 100
    grid.flags.writeable = False
    changed = replace(first, grid=grid)
    assert 'motion_routes' not in node._admission_caches(changed, 'tb1')
    proposal = MotionProposal('tb1', 'exploration', c.RallyPose(2.25, 1.25, 0.),
        ((1.25, 1.25), (2.25, 1.25)), 1., 15.)
    assert node._current_motion(changed, proposal, {}) is None
def test_stationary_arrival_waits_for_original_five_second_hold(node):
    final = c.RallyPose(1.25, 1.25, 0.)
    node.task_state = 'RALLY'
    node.target, node.target_received_source_time = (2., 2.), 10.
    node.rally_targets = node.rally_final_targets = {'tb1': final}
    node.rally_arrived['tb1'] = True
    snapshot = node._snapshot()
    node._hold(snapshot)
    assert node.rally_hold_started_at == 10. and node.task_state == 'RALLY'
    node.now = lambda: 14.9
    fresh = replace(snapshot, at_time=14.9, sources={key: 14.9 for key in snapshot.sources})
    node._hold(fresh)
    assert node.task_state == 'RALLY'
    node.now = lambda: 15.
    node._hold(replace(fresh, at_time=15., sources={key: 15. for key in fresh.sources}))
    assert node.task_state == 'COMPLETE'
