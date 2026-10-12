"""Real node construction, synthetic action outcomes; no physical task credit."""
import json
import math
import gc
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
from multi_robot_exploration.fleet_planning import MotionProposal, ChargeProposal, FleetProposal
from multi_robot_exploration.global_control import GlobalHeadquartersControl


@pytest.fixture
def node(request):
    count = getattr(request, 'param', 1)
    rclpy.init(args=['--ros-args', '-p', f'robot_count:={count}', '-p', 'enable_battery:=true',
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
    for i in range(2,count+1):
        robot=f'tb{i}'
        n.robot_map_callback(grid,robot)
        n.robot_tf_callback(TFMessage(transforms=[frame]),robot)
        extra=Odometry()
        extra.header.stamp.sec=10
        extra.pose.pose.position.x=extra.pose.pose.position.y=1.25+3*(i-1)
        extra.pose.pose.orientation.w=1.
        n.robot_odom_callback(extra,robot)
        n.battery_state_callback(String(data=json.dumps({**state,
            'charge_x':extra.pose.pose.position.x,'charge_y':extra.pose.pose.position.y})),robot)
    n.consumed_publisher = Mock()
    try:
        yield n
    finally:
        n.shutdown_requested = True
        n.destroy_node()
        assert not any(isinstance(waitable,c.ActionClient) for waitable in n.waitables)
        gc.collect()
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


def delivered_state(node, at, position=(1.25, 1.25), yaw=0., energy=40., obstacle=False):
    node.now = lambda: at
    stamp = int(at)
    grid = OccupancyGrid()
    grid.header.stamp.sec = stamp
    grid.info.width = grid.info.height = 80
    grid.info.resolution = .1
    grid.info.origin.orientation.w = 1.
    grid.data = [0] * 6400
    if obstacle:
        grid.data[12 * 80 + 22] = 100
    node.map_callback(grid)
    node.robot_map_callback(grid, 'tb1')
    frame = TransformStamped()
    frame.header.stamp.sec = stamp
    frame.header.frame_id, frame.child_frame_id = 'map', 'odom'
    frame.transform.rotation.w = 1.
    node.robot_tf_callback(TFMessage(transforms=[frame]), 'tb1')
    odom = Odometry()
    odom.header.stamp.sec = stamp
    odom.pose.pose.position.x, odom.pose.pose.position.y = position
    odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
    node.robot_odom_callback(odom, 'tb1')
    node.battery_state_callback(String(data=json.dumps({**node.battery_states['tb1'],
        'stamp_sec':at, 'energy':energy})), 'tb1')


def test_physical_odom_progress_survives_zero_action_feedback(node):
    _, _, _, _, task = request(node)
    node._feedback(task, SimpleNamespace(feedback=SimpleNamespace(distance_remaining=0.)))
    delivered_state(node, 29., position=(2., 1.25))
    assert task.last_progress_at == 29.
    node.now = lambda: 31.
    node.cancel_stalled_goals()
    assert task.cancel_reason is None
    node.now = lambda: 71.
    node.cancel_stalled_goals()
    assert task.cancel_reason == 'timeout'


def test_turning_progress_cannot_be_renewed_by_old_future_or_reprojected_odom(node):
    _, _, _, _, task = request(node)
    delivered_state(node, 29., yaw=.3)
    assert task.last_progress_at == 29.
    node.now = lambda: 30.
    shifted = TransformStamped()
    shifted.header.stamp.sec = 30
    shifted.header.frame_id, shifted.child_frame_id = 'map', 'odom'
    shifted.transform.rotation.w = 1.
    shifted.transform.translation.x = 3.
    node.robot_tf_callback(TFMessage(transforms=[shifted]), 'tb1')
    assert task.last_progress_at == 29.
    replay = Odometry()
    replay.header.stamp.sec = 29
    replay.pose.pose.position.x, replay.pose.pose.position.y = 6., 6.
    replay.pose.pose.orientation.w = 1.
    node.now = lambda: 31.
    node.robot_odom_callback(replay, 'tb1')
    replay.header.stamp.sec = 40
    node.robot_odom_callback(replay, 'tb1')
    assert task.last_progress_at == 29.
    node.now = lambda: 50.
    node.cancel_stalled_goals()
    assert task.cancel_reason == 'no_progress'


def test_late_acceptance_uses_real_new_state_and_exact_original_goal(node):
    snapshot, proposal, pending, _, task = request(node)
    delivered_state(node, 13.)
    handle, result = accept(node, pending)
    assert not handle.cancel_goal_async.called
    assert task.generation == 1 and node.navigation_tasks['tb1'] is task
    assert task.started_at == 10. and snapshot.sources['tb1/pose_state'] == 10.
    assert task.sources['tb1/pose_state'] == 13. and task.proposal.pose == proposal.pose
    proofs = [json.loads(call.args[0].data) for call in node.consumed_publisher.publish.call_args_list
              if json.loads(call.args[0].data).get('event') == 'coordinator_global_motion_revalidation']
    assert len(proofs) == 1
    from p2c_global_audit import audit_motion
    assert audit_motion(proofs[0]) > 0
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    node.drain_action_done_callbacks()
    assert not node.navigation_tasks and node.successful_exploration_legs['tb1'] == 1


def test_dispatch_anchors_metric_pose_and_preserves_continuous_local_clearance(node):
    grid=OccupancyGrid()
    grid.header.stamp.sec=10
    grid.info.width=grid.info.height=80
    grid.info.resolution=.1
    grid.info.origin.position.x=grid.info.origin.position.y=-.025
    grid.info.origin.orientation.w=1.
    grid.data=[0]*6400
    grid.data[0]=100
    node.robot_map_callback(grid,'tb1')
    odom=Odometry()
    odom.header.stamp.sec=10
    odom.pose.pose.position.x,odom.pose.pose.position.y=.379,.025
    odom.pose.pose.orientation.w=1.
    node.robot_odom_callback(odom,'tb1')
    snapshot=node._snapshot()
    proposed=MotionProposal('tb1','exploration',c.RallyPose(1.75,.05,0.),
                            ((.379,.025),(1.75,.05)),1.,20.)
    actual=node._current_motion(snapshot,proposed,{})
    assert actual is not None
    assert actual.route[0]==snapshot.positions['tb1']
    assert c.route_respects_known_obstacles(node.robot_maps['tb1']['data'],
                                          grid.info.resolution,(-.025,-.025),actual.route)
    from p2c_global_audit import audit_motion
    assert audit_motion({**node._motion_proof(snapshot,SimpleNamespace(generation=1),actual),
                         'event_time':10.}) > 0
    assert node.robot_maps['tb1']['data'][0,0]==100


@pytest.mark.parametrize('energy,obstacle', [(10., False), (40., True)])
def test_late_acceptance_rejects_new_unfunded_or_blocked_state_without_releasing_owner(node, energy, obstacle):
    _, _, pending, _, task = request(node)
    delivered_state(node, 13., energy=energy, obstacle=obstacle)
    handle, result = accept(node, pending)
    assert handle.cancel_goal_async.called and task.cancel_reason == 'source_expired_at_acceptance'
    assert node.navigation_tasks['tb1'] is task and node.successful_exploration_legs.get('tb1', 0) == 0
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_CANCELED))
    node.drain_action_done_callbacks()
    assert not node.navigation_tasks


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


def test_nominal_field_reuse_keeps_live_prefix_but_invalidates_changed_start_cell(node):
    first=node._snapshot()
    cache=node._nominal_caches(first,'tb1')
    cache['nominal_rally_routes']={'field':'same_geometry'}
    shifted=replace(first,positions={'tb1':(1.251,1.25)})
    assert node._nominal_caches(shifted,'tb1')['nominal_rally_routes']['field']=='same_geometry'
    advanced=replace(first,positions={'tb1':(1.45,1.25)})
    assert 'nominal_rally_routes' not in node._nominal_caches(advanced,'tb1')


def test_shifted_map_origin_funds_exact_final_connector_and_actual_stop(node):
    grid=OccupancyGrid()
    grid.header.stamp.sec=10
    grid.info.width=grid.info.height=80
    grid.info.resolution=.1
    grid.info.origin.position.x=.02
    grid.info.origin.orientation.w=1.
    grid.data=[0]*6400
    node.map_callback(grid)
    node.robot_map_callback(grid,'tb1')
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(3.,3.),10.
    final=c.RallyPose(2.25,1.25,math.atan2(1.75,.75))
    node.rally_targets=node.rally_final_targets={'tb1':final}
    proposed=MotionProposal('tb1','rally',final,((1.25,1.25),(2.25,1.25)),1.,15.)
    snapshot=node._snapshot()
    actual=node._current_motion(snapshot,proposed,{})
    assert actual is not None and actual.complete_route[-1]==(final.x,final.y)
    assert actual.route[-1]!=(final.x,final.y)
    from multi_robot_exploration.fleet_planning import complete_budget
    nominal=complete_budget(replace(snapshot,at_time=actual.budget_time),'tb1',
        actual.complete_route,(final.x,final.y),{},actual.wait_sec)
    stopped=complete_budget(replace(snapshot,at_time=actual.budget_time),'tb1',
        actual.route,(actual.pose.x,actual.pose.y),{},actual.wait_sec)
    assert actual.required_energy==max(nominal,stopped)


@pytest.mark.parametrize('node', [2], indirect=True)
def test_fleet_wait_uses_same_price_epoch_when_peer_crosses_charge_threshold(node):
    from multi_robot_exploration.fleet_planning import complete_budget
    node.task_state = 'RALLY'
    node.target, node.target_received_source_time = (3.5, 3.), 10.
    finals = {'tb1':c.RallyPose(2.25, 1.25, math.atan2(1.75, 1.25)),
              'tb2':c.RallyPose(5.25, 4.25, math.atan2(-1.25, -1.75))}
    node.rally_targets = node.rally_final_targets = finals
    original = node._snapshot()
    base, travel = {}, {}
    for robot, final in finals.items():
        _, leg = c.plan_rally_leg(final, original.grid, original.resolution, original.origin,
                                 original.positions[robot])
        full = (original.positions[robot], *leg)
        base[robot] = complete_budget(original, robot, full, (final.x, final.y), {}, 5.)
        travel[robot] = sum(math.dist(a,b) for a,b in zip(full,full[1:])) / .18
    old_requirements, _ = c.rally_wait_requirements(base, original.batteries,
        dict.fromkeys(finals, 'ACTIVE'), travel, dict.fromkeys(finals, 36.))
    # Pose-age reaction pricing grows by more than this margin at t=11.
    node.battery_states['tb2']['energy'] = old_requirements['tb2'] + .15
    snapshot = node._snapshot()
    old_wait = node._current_wait(snapshot, 'tb1')
    node.now = lambda: 11.
    proposed = MotionProposal('tb1', 'rally', finals['tb1'], ((1.25,1.25),(2.25,1.25)), 1., 20.)
    actual = node._current_motion(snapshot, proposed, {})
    assert actual is not None and actual.budget_time == 11.
    assert actual.wait_sec >= old_wait + node.rally_hold_sec + 30.
    from p2c_global_audit import audit_motion
    assert audit_motion({**node._motion_proof(snapshot, SimpleNamespace(generation=1), actual),
                         'event_time':11.}) > 0


@pytest.mark.parametrize('node', [2], indirect=True)
@pytest.mark.parametrize('kind', ['charge_clearance', 'exploration'])
def test_charge_waits_for_its_clearance_owner_but_cancels_other_crossing_traffic(node, kind):
    from multi_robot_exploration.fleet_planning import contact_route
    delivered_state(node, 11., position=(4.25, 1.25), energy=20.)
    odom = Odometry()
    odom.header.stamp.sec = 11
    odom.pose.pose.position.x, odom.pose.pose.position.y = 2.75, 1.25
    odom.pose.pose.orientation.w = 1.
    node.robot_odom_callback(odom, 'tb2')
    node.battery_state_callback(String(data=json.dumps({**node.battery_states['tb2'],
        'stamp_sec':11., 'energy':60.})), 'tb2')
    snapshot = node._snapshot()
    returning = contact_route(snapshot, 'tb1', snapshot.positions['tb1'], {})
    intent = ChargeProposal('tb1', 60., returning['route'],
        'unfunded_information_task', (6.75, 1.25))
    if kind == 'charge_clearance':
        node.global_charge_intent = intent
        node.global_charge_context = snapshot.context
    snapshot = node._snapshot()
    proposed = MotionProposal('tb2', kind, c.RallyPose(2.75,4.25,0.),
        ((2.75,1.25),(2.75,4.25)), 1., 20., beneficiary='tb1' if kind=='charge_clearance' else None)
    actual = node._current_motion(snapshot, proposed, {})
    assert actual is not None
    pending = Future()
    client = Mock()
    client.server_is_ready.return_value = True
    client.send_goal_async.return_value = pending
    node.robot_nav_clients['tb2'] = client
    node.charge_request_publishers['tb1'] = Mock()
    assert node._send_motion(snapshot, actual)
    task = node.navigation_tasks['tb2']
    proof = next(json.loads(call.args[0].data) for call in node.consumed_publisher.publish.call_args_list
                 if json.loads(call.args[0].data).get('event')=='coordinator_global_motion_admission')
    from p2c_global_audit import audit_motion
    assert audit_motion(proof) > 0
    node.global_charge_intent = intent
    node.global_charge_context = snapshot.context
    node._prepare_charge(node._snapshot())
    assert node.navigation_tasks['tb2'] is task
    assert task.cancel_reason == (None if kind=='charge_clearance' else 'return_corridor')
    assert not node.charge_request_publishers['tb1'].publish.called


@pytest.mark.parametrize('node', [2], indirect=True)
def test_clearance_selection_meets_the_sender_landing_mask_and_original_route_audit(node):
    from multi_robot_exploration.fleet_planning import plan_fleet
    delivered_state(node,11.,position=(4.25,1.25),energy=20.)
    odom=Odometry()
    odom.header.stamp.sec=11
    odom.pose.pose.position.x,odom.pose.pose.position.y=2.75,1.25
    odom.pose.pose.orientation.w=1.
    node.robot_odom_callback(odom,'tb2')
    grid=OccupancyGrid()
    grid.header.stamp.sec=11
    grid.info.width=grid.info.height=80
    grid.info.resolution=.1
    grid.info.origin.orientation.w=1.
    grid.data=[0]*6400
    # Near the original .35m refuge, without blocking the .35m approach.
    grid.data[30*80+30]=100
    node.map_callback(grid)
    for robot in node.robot_positions:
        node.robot_map_callback(grid,robot)
    node.battery_state_callback(String(data=json.dumps({**node.battery_states['tb2'],
        'stamp_sec':11.,'energy':60.})), 'tb2')
    node.global_charge_intent=ChargeProposal('tb1',60.,((4.25,1.25),(1.25,1.25)),
        'unfunded_information_task',(6.75,1.25))
    snapshot=node._snapshot()
    proposal=plan_fleet(snapshot)
    assert len(proposal.motions)==1 and proposal.motions[0].kind=='charge_clearance'
    actual=node._current_motion(snapshot,proposal.motions[0],{})
    assert actual is not None
    from multi_robot_exploration.fleet_planning import robot_grid
    constrained=robot_grid(snapshot,actual.robot,{})
    cell=c.world_to_grid(actual.pose.x,actual.pose.y,snapshot.resolution,*snapshot.origin)
    assert c.traversable_grid(constrained,snapshot.resolution,.45)[cell]
    from p2c_global_audit import audit_motion
    assert audit_motion({**node._motion_proof(snapshot,SimpleNamespace(generation=1),actual),
                         'event_time':node.now()})>0
    assert constrained[30,30]==100


@pytest.mark.parametrize('barrier',['unissued','published','native_return','owned'])
def test_whole_fleet_reassignment_releases_only_unissued_dependencies(node,barrier):
    if barrier=='owned':
        request(node)
    delivered_state(node,11.,obstacle=True)
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(3.,3.),11.
    old=c.RallyPose(2.25,1.25,math.atan2(1.75,.75))
    replacement=c.RallyPose(1.25,2.25,math.atan2(.75,1.75))
    node.rally_targets=node.rally_final_targets={'tb1':old}
    intent=ChargeProposal('tb1',60.,((1.25,1.25),),'whole_rally_and_wait',(old.x,old.y))
    node.global_charge_intent=intent
    if barrier=='published':
        node.global_charge_requested_at=11.
        node.rally_charge_requested['tb1']=11.
    elif barrier=='native_return':
        node.now=lambda:11.5
        node.battery_state_callback(String(data=json.dumps({**node.battery_states['tb1'],
            'mode':'RETURNING','stamp_sec':11.5})), 'tb1')
    snapshot=node._snapshot()
    node.global_charge_context=snapshot.context
    node.planning_worker.close()
    node.planning_worker=Mock()
    node.planning_worker.poll.return_value=FleetProposal(snapshot,final_poses={'tb1':replacement})
    node.charge_request_publishers['tb1']=Mock()
    node.update_mission()
    if barrier=='unissued':
        assert node.rally_final_targets=={'tb1':replacement}
        assert node.global_charge_intent is None and node.deferred_charge_intent is None
    else:
        assert node.rally_final_targets=={'tb1':old}
        assert node.global_charge_intent is intent
    assert not node.charge_request_publishers['tb1'].publish.called


def test_fresh_fleet_assignment_cannot_erase_a_local_positive_obstacle(node):
    delivered_state(node,11.)
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(3.,3.),11.
    local=OccupancyGrid()
    local.header.stamp.sec=11
    local.info.width=local.info.height=80
    local.info.resolution=.1
    local.info.origin.orientation.w=1.
    local.data=[0]*6400
    local.data[22*80+12]=100
    node.robot_map_callback(local,'tb1')
    final=c.RallyPose(1.25,2.25,math.atan2(.75,1.75))
    snapshot=node._snapshot()
    assert snapshot.grid[22,12]==0
    assert not node._validate_final_poses(snapshot,{'tb1':final})
    assert snapshot.maps['tb1']['data'][22,12]==100


@pytest.mark.parametrize('node', [2], indirect=True)
def test_refuge_waits_for_beneficiary_full_completion_and_rejects_late_return_proposals(node,monkeypatch,tmp_path):
    from multi_robot_exploration.fleet_planning import plan_fleet
    node.get_clock=Mock()
    node.get_clock.return_value.now.side_effect=lambda:rclpy.time.Time(seconds=node.now())
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(3.5,3.),10.
    finals={'tb1':c.RallyPose(2.25,1.25,math.atan2(1.75,1.25)),
            'tb2':c.RallyPose(5.25,4.25,math.atan2(-1.25,-1.75))}
    node.rally_targets=node.rally_final_targets=finals
    snapshot=node._snapshot()
    retreat=MotionProposal('tb1','rally_yield',c.RallyPose(1.25,3.25,0.),
        ((1.25,1.25),(1.25,3.25)),1.,20.,beneficiary='tb2')
    actual=node._current_motion(snapshot,retreat,{})
    assert actual is not None and actual.wait_sec>=35.
    from p2c_global_audit import audit_motion
    proof={**node._motion_proof(snapshot,SimpleNamespace(generation=1),actual),'event_time':10.}
    assert audit_motion(proof)>0
    # Even recomputing the scalar energy after deleting its waiting allowance
    # cannot turn an unpriced refuge into a valid admission.
    from p2c_global_audit import geometry_world,scalar_budget
    grid,maps=geometry_world(proof)
    no_wait={**proof,'waiting_time_budget_sec':0.}
    no_wait['required_energy']=scalar_budget(no_wait,grid,maps,actual.complete_route,
        (actual.pose.x,actual.pose.y),0.)
    with pytest.raises(AssertionError,match='unfunded refuge waiting'):
        audit_motion(no_wait)
    client=Mock()
    client.server_is_ready.return_value=True
    pending=Future()
    client.send_goal_async.return_value=pending
    node.robot_nav_clients['tb1']=client
    assert node._send_motion(snapshot,actual)
    _,result=accept(node,pending)
    delivered_state(node,11.,position=(1.25,3.25))
    result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    node.drain_action_done_callbacks()
    assert 'tb1' not in node.navigation_tasks
    parked=node._snapshot()
    assert parked.yielded_for=={'tb1':('tb2',)}
    assert not any(m.robot=='tb1' and m.kind=='rally' for m in plan_fleet(parked).motions)
    resume=MotionProposal('tb1','rally',finals['tb1'],((1.25,3.25),(2.25,1.25)),1.,20.)
    assert node._current_motion(parked,resume,{}) is None
    assert node._current_motion(replace(parked,yielded_for={}),resume,{}) is not None
    # A real successful short leg belongs to the beneficiary, but it does not
    # finish that robot's permanent endpoint or release the refuge.
    short=MotionProposal('tb2','rally',c.RallyPose(4.85,4.25,finals['tb2'].yaw),
        ((4.25,4.25),(4.85,4.25)),1.,20.)
    short_actual=node._current_motion(parked,short,{})
    assert short_actual is not None
    second=Mock()
    second.server_is_ready.return_value=True
    short_pending=Future()
    second.send_goal_async.return_value=short_pending
    node.robot_nav_clients['tb2']=second
    assert node._send_motion(parked,short_actual)
    _,short_result=accept(node,short_pending)
    short_result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    node.drain_action_done_callbacks()
    assert not node.rally_arrived['tb2'] and node._snapshot().yielded_for
    last_snapshot=node._snapshot()
    final_motion=replace(short,pose=finals['tb2'])
    final_actual=node._current_motion(last_snapshot,final_motion,{})
    assert final_actual is not None
    final_pending=Future()
    second.send_goal_async.return_value=final_pending
    assert node._send_motion(last_snapshot,final_actual)
    _,final_result=accept(node,final_pending)
    odom=Odometry()
    odom.header.stamp.sec=11
    odom.header.stamp.nanosec=500000000
    odom.pose.pose.position.x,odom.pose.pose.position.y=5.25,4.25
    odom.pose.pose.orientation.w=1.
    node.now=lambda:11.5
    node.robot_odom_callback(odom,'tb2')
    node.rally_arrived['tb2']=True  # A prior arrival flag cannot close this real Future.
    assert node._snapshot().yielded_for and 'tb2' in node.navigation_tasks
    final_result.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
    node.drain_action_done_callbacks()
    released=node._snapshot()
    assert node.rally_arrived['tb2'] and not released.yielded_for
    assert node._current_motion(released,resume,{}) is not None
    assert not node.successful_exploration_legs
    # This fixture has no original DDS/native recording. Exercise the ledger
    # lifecycle independently; the existing real DDS tests retain binding.
    import p2c_global_audit as reader
    records=[json.loads(call.args[0].data) for call in node.consumed_publisher.publish.call_args_list]
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records))
    monkeypatch.setattr(reader,'bind_sources',lambda *args:0)
    audited=reader.global_mission_audit(tmp_path,True)
    assert audited['sent']==audited['closed']==3 and not audited['refuge_dependencies_at_shutdown']
    release=next(row for row in records if row['event']=='coordinator_global_rally_yield_released')
    release['world']['positions']['tb2']=[4.25,4.25]
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records))
    with pytest.raises(AssertionError):
        reader.global_mission_audit(tmp_path,True)


@pytest.mark.parametrize('node', [2], indirect=True)
def test_missing_fresh_inputs_do_not_release_a_refuge_from_old_arrival_data(node):
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(3.,3.),10.
    node.rally_targets=node.rally_final_targets={'tb1':c.RallyPose(1.25,1.25,math.pi/4),
                                                'tb2':c.RallyPose(4.25,4.25,-3*math.pi/4)}
    node.global_rally_yields={'tb1':{'tb2'}}
    node.rally_arrived['tb2']=True
    node.now=lambda:12.1
    assert node._snapshot() is None
    assert node.global_rally_yields=={'tb1':{'tb2'}}


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


def test_funded_observer_demand_is_cleared_before_observer_execution_guard(node):
    final=c.RallyPose(1.25,1.25,math.pi/4)
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(2.,2.),10.
    node.target_observing_robot='tb1'
    node.global_confirmations['tb1']=10.
    node.rally_targets=node.rally_final_targets={'tb1':final}
    node.rally_arrived['tb1']=True
    node.global_charge_intent=ChargeProposal('tb1',60.,((1.25,1.25),),
        'whole_rally_and_wait',(1.25,1.25))
    node.global_charge_context=node._snapshot().context
    node.charge_request_publishers['tb1']=Mock()
    node._prepare_charge(node._snapshot())
    assert node.global_charge_intent is None
    assert not node.charge_request_publishers['tb1'].publish.called
    node._hold(node._snapshot())
    assert node.rally_hold_started_at==10.


@pytest.mark.parametrize('node',[2],indirect=True)
def test_independent_fresh_observer_source_does_not_rewind_global_target_lease(node):
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(2.,2.),10.
    node.target_observing_robot='tb1'
    node.global_confirmations['tb1']=10.
    packet=dict(robot='tb2',target_x=2.,target_y=2.,max_distance_m=3.,field_of_view_deg=90.,
                _gateway=dict(source_time=9.9,delivery_time=10.))
    node.target_detection_callback(String(data=json.dumps(packet)))
    assert node.target_received_source_time==10. and node.target_observing_robot=='tb1'
    assert node.global_confirmations['tb2']==9.9
    assert not node._active_observer(node._snapshot(),'tb1')
    packet['_gateway']['source_time']=10.1
    node.target_detection_callback(String(data=json.dumps(packet)))
    assert node.global_confirmations['tb2']==9.9


@pytest.mark.parametrize('node',[2],indirect=True)
def test_blocked_observer_does_not_starve_other_funded_serial_charging(node):
    node.now=lambda:11.
    grid=OccupancyGrid()
    grid.header.stamp.sec=11
    grid.info.width=grid.info.height=80
    grid.info.resolution=.1
    grid.info.origin.orientation.w=1.
    grid.data=[0]*6400
    node.map_callback(grid)
    for robot,position,energy in [('tb1',(6.25,6.25),26.),('tb2',(4.25,4.25),15.)]:
        node.robot_map_callback(grid,robot)
        frame=TransformStamped()
        frame.header.stamp.sec=11
        frame.header.frame_id,frame.child_frame_id='map','odom'
        frame.transform.rotation.w=1.
        node.robot_tf_callback(TFMessage(transforms=[frame]),robot)
        odom=Odometry()
        odom.header.stamp.sec=11
        odom.pose.pose.position.x,odom.pose.pose.position.y=position
        odom.pose.pose.orientation.w=1.
        node.robot_odom_callback(odom,robot)
        node.battery_state_callback(String(data=json.dumps({**node.battery_states[robot],
            'stamp_sec':11.,'energy':energy})),robot)
    node.task_state='RALLY'
    node.target,node.target_received_source_time=(7.,7.),11.
    node.target_observing_robot='tb1'
    node.global_confirmations['tb1']=11.
    node.rally_targets=node.rally_final_targets={
        'tb1':c.RallyPose(7.25,5.25,math.atan2(1.75,-.25)),
        'tb2':c.RallyPose(6.25,7.25,math.atan2(-.25,.75))}
    observer=ChargeProposal('tb1',60.,((6.25,6.25),(1.25,1.25)),
        'whole_rally_and_wait',(7.25,5.25))
    other=ChargeProposal('tb2',40.,((4.25,4.25),),
        'whole_rally_and_wait',(6.25,7.25))
    snapshot=node._snapshot()
    node.global_charge_intent=observer
    node.global_charge_context=snapshot.context
    node._prepare_charge(snapshot)
    assert node.global_charge_intent is observer
    node.planning_worker.close()
    node.planning_worker=Mock()
    node.planning_worker.poll.return_value=FleetProposal(snapshot,charges=(other,))
    node.charge_request_publishers['tb2']=Mock()
    node.update_mission()
    assert node.global_charge_intent is other and node.deferred_charge_intent is observer
    assert node.global_charge_requested_at==11.
    assert node.charge_request_publishers['tb2'].publish.call_count==1
