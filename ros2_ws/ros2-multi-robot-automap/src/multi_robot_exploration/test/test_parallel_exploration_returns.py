"""Ordinary work can proceed only outside fresh complete local return routes."""
import copy
import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

from multi_robot_exploration import control as c
from p2c_outbound_routes import audit_exploration_returns, audit_outbound, decode
from test_exploration_return_preparation import node as base_node


def fixture(case='dev_corridors303', robot='tb3'):
    path = Path(__file__).with_name('fixtures')/'p2c_v86_parallel_returns.json.gz'
    data = json.load(gzip.open(path, 'rt'))
    event = data['originals'][case]
    saved = event['return_preparation']
    h, events, _, _ = base_node()
    h.clock = event['event_time']
    h.map_data = decode(saved['planning_map'])
    h.source_map_data = decode(saved['source_map'])
    h.resolution, h.origin = saved['planning_map']['resolution'], saved['planning_map']['origin']
    h.map_received_at = saved['planning_map']['source_time']
    h.robot_positions = copy.deepcopy(saved['robot_positions'])
    h.battery_states = copy.deepcopy(saved['battery_states'])
    h.battery_modes = dict(saved['battery_modes'])
    h.battery_modes['tb1'] = h.battery_states['tb1']['mode'] = 'RETURNING'
    h.robot_maps = {name: dict(data=decode(g), resolution=g['resolution'], origin=g['origin'])
                    for name, g in saved['return_maps'].items()}
    for attr, kind in [('robot_odom_received_at','pose_state'),('robot_tf_received_at','frame_state'),
                       ('robot_map_received_at','map_snapshot'),('battery_state_received_at','battery_state')]:
        setattr(h, attr, {name: saved['inputs'][name+'/'+kind]['source_time'] for name in h.robot_positions})
    names = list(h.robot_positions)
    for attr in ('goal_handles','goal_targets','goal_started_at','goal_last_progress_at','goal_best_distance','goal_last_position',
                 'rally_goal_handles'):
        setattr(h, attr, dict.fromkeys(names))
    for attr in ('cancel_requested','battery_preempted','rally_goal_pending','rally_battery_preempted','initial_search_goals'):
        setattr(h, attr, dict.fromkeys(names, False))
    h.robot_states = dict.fromkeys(names, 'idle')
    h.goal_routes = dict.fromkeys(names, ())
    h.goal_known_count = h.goal_initial_gain = dict.fromkeys(names, 0)
    h.message_freshness_timeout_sec = 5.
    h.frontier_cache = None
    h.participating_robots = lambda:c.HeadquartersControl.participating_robots(h)
    h.input_robot_names = lambda:c.HeadquartersControl.input_robot_names(h)
    h.fresh_robot_poses = lambda:c.HeadquartersControl.fresh_robot_poses(h)
    h.fresh_robot_inputs = lambda:c.HeadquartersControl.fresh_robot_inputs(h)
    h.input_freshness_details = lambda:c.HeadquartersControl.input_freshness_details(h)
    h.record_navigation_decision = lambda *a:c.HeadquartersControl.record_navigation_decision(h,*a)
    witness = next(w for w in data['separation_probe'][case]['witnesses'] if w['robot'] == robot)
    h.goal_routes[robot] = tuple(map(tuple, witness['route']))
    h.goal_targets[robot] = c.Assignment(c.Viewpoint(1,1,1,1,1,witness['exact_gain'],1),
        *witness['full_target'], witness['full_body_path_distance_m'], 1.,
        *witness['navigation_goal'][:2], witness['navigation_goal'][2])
    h.exploration_travel_choices = {robot:dict(eligible_robot_names=[robot])}
    return h, events, witness, data


def reference(data, name):
    scope = vars(c).copy()
    exec(data['reference_methods'][name], scope)
    return scope[name]


@pytest.mark.parametrize('case,robot', [('dev_lab101','tb2'),('dev_lab101','tb3'),
                                      ('dev_corridors303','tb2'),('dev_corridors303','tb3')])
def test_original_geometry_has_funded_work_outside_the_complete_return(case, robot):
    h, _, witness, _ = fixture(case, robot)
    before = h.source_map_data.tobytes(), {n:m['data'].tobytes() for n,m in h.robot_maps.items()}
    protected = c.HeadquartersControl.exploration_return_reservations(h, robot, h.goal_routes[robot])
    assert protected is not None and 'tb1' in protected
    assert all(not c.routes_conflict(witness['route'], route, 1.8) for route in protected.values())
    required = c.HeadquartersControl.exploration_required_energy(h, robot,
        max(witness['full_body_path_distance_m'], witness['nominal_distance_m']), witness['full_target'])
    assert required is not None and h.battery_states[robot]['energy'] > required
    assert before == (h.source_map_data.tobytes(), {n:m['data'].tobytes() for n,m in h.robot_maps.items()})


@pytest.mark.parametrize('change', ['stale_return_pose','stale_return_frame','future_return_frame','stale_return_map',
    'stale_return_battery','missing_local_map','unknown_return','conflict','own_return','failed_body','missing_body'])
def test_missing_or_unavailable_full_return_authority_keeps_the_pause(change):
    h, _, _, _ = fixture()
    if change == 'stale_return_pose':h.robot_odom_received_at['tb1'] = h.clock-2.001
    if change == 'stale_return_frame':h.robot_tf_received_at['tb1'] = h.clock-2.001
    if change == 'future_return_frame':h.robot_tf_received_at['tb1'] = h.clock+.001
    if change == 'stale_return_map':h.robot_map_received_at['tb1'] = h.clock-5.001
    if change == 'stale_return_battery':h.battery_state_received_at['tb1'] = h.clock-5.001
    if change == 'missing_local_map':h.robot_maps['tb1'] = None
    if change == 'unknown_return':
        grid = np.full(h.map_data.shape,-1,dtype=np.int16)
        h.source_map_data = h.map_data = grid
        h.robot_maps['tb1']['data'] = grid
    if change == 'conflict':h.goal_routes['tb3'] = (h.robot_positions['tb3'],h.robot_positions['tb1'])
    if change == 'own_return':h.battery_modes['tb3'] = h.battery_states['tb3']['mode'] = 'RETURNING'
    if change == 'failed_body':h.battery_modes['tb2'] = 'FAILED'
    if change == 'missing_body':h.robot_positions['tb1'] = None
    assert c.HeadquartersControl.exploration_return_reservations(h,'tb3',h.goal_routes['tb3']) is None


def test_pending_charge_protects_the_same_complete_route_before_mode_changes():
    h, _, _, _ = fixture()
    h.battery_modes['tb1'] = h.battery_states['tb1']['mode'] = 'ACTIVE'
    h.rally_charge_requested['tb1'] = h.clock
    assert 'tb1' in c.HeadquartersControl.exploration_return_reservations(h,'tb3',h.goal_routes['tb3'])
    assert c.HeadquartersControl.exploration_return_reservations(h,'tb1',h.goal_routes['tb3']) is None


@pytest.mark.parametrize('scope', ['mapping','reacquisition'])
def test_original_return_pause_is_preserved_outside_full_object_exploration(scope):
    h, _, _, _ = fixture()
    if scope == 'mapping':h.enable_rally = False
    else:h.task_state = 'RALLY'
    assert c.HeadquartersControl.exploration_return_reservations(h) is None
    h.battery_modes['tb1'] = 'ACTIVE';h.rally_charge_requested['tb1'] = h.clock
    assert c.HeadquartersControl.exploration_return_reservations(h) == {}


def test_same_original_battery_update_cancels_old_work_but_keeps_a_separated_leg():
    canceled = []
    for old in (True,False):
        h, _, _, data = fixture()
        handle = Mock();h.goal_handles['tb3'] = handle;h.robot_states['tb3'] = 'active'
        h.battery_modes['tb1'] = 'ACTIVE'
        event = String(data=json.dumps(h.battery_states['tb1']))
        (reference(data,'battery_state_callback') if old else c.HeadquartersControl.battery_state_callback)(h,event,'tb1')
        canceled.append(handle.cancel_goal_async.call_count)
        assert h.successful_exploration_legs['tb2'] == 7
    assert canceled == [1,0]


@pytest.mark.parametrize('change', ['conflict','stale','safe'])
def test_original_execution_check_revokes_conflicting_or_stale_live_work(change):
    h, _, _, _ = fixture();handle = Mock()
    h.goal_handles['tb3'] = handle;h.robot_states['tb3'] = 'active'
    h.goal_started_at['tb3'] = h.goal_last_progress_at['tb3'] = h.clock
    h.goal_timeout_sec = 60.;h.target_information_gain = lambda *a:1000
    if change == 'conflict':h.goal_routes['tb3'] = (h.robot_positions['tb3'],h.robot_positions['tb1'])
    if change == 'stale':h.robot_tf_received_at['tb1'] = h.clock-2.001
    c.HeadquartersControl.cancel_stalled_goals(h)
    assert handle.cancel_goal_async.call_count == int(change != 'safe')
    assert h.cancel_requested['tb3'] == (change != 'safe')


@pytest.mark.parametrize('change', ['safe','conflict','stale','future','missing_map','own_return'])
def test_late_action_acceptance_rechecks_current_complete_return_authority(change):
    h, _, _, _ = fixture();handle = Mock(accepted=True);future = Mock()
    future.result.return_value = handle
    h.map_known_count = 100
    if change == 'conflict':h.goal_routes['tb3'] = (h.robot_positions['tb3'],h.robot_positions['tb1'])
    if change == 'stale':h.robot_tf_received_at['tb1'] = h.clock-2.001
    if change == 'future':h.robot_tf_received_at['tb1'] = h.clock+.001
    if change == 'missing_map':h.robot_maps['tb1'] = None
    if change == 'own_return':h.battery_modes['tb3'] = 'RETURNING'
    c.HeadquartersControl.goal_response_callback(h,'tb3',future)
    assert handle.cancel_goal_async.call_count == int(change != 'safe')
    assert h.cancel_requested['tb3'] == (change != 'safe')
    handle.get_result_async.assert_called_once()
    handle.get_result_async.return_value.add_done_callback.assert_called_once()
    assert h.successful_exploration_legs['tb2'] == 7


def navigation_event():
    h, events, witness, _ = fixture()
    goal = PoseStamped();goal.pose.position.x,goal.pose.position.y = witness['navigation_goal'][:2]
    goal.pose.orientation.z = math.sin(witness['navigation_goal'][2]/2.)
    goal.pose.orientation.w = math.cos(witness['navigation_goal'][2]/2.)
    assert h.record_navigation_decision('tb3','initial_visual_search',goal,None,h.goal_routes['tb3'])
    event = events[-1]
    assert audit_outbound(event) > 1
    assert audit_exploration_returns(event,True) is not None
    return h,event


def test_private_decision_keeps_original_body_sources_and_complete_reservations():
    h,event = navigation_event()
    assert event['inputs']['tb1/frame_state']['source_time'] == h.robot_tf_received_at['tb1']
    assert set(event['exploration_safety_returns']['return_maps']) == set(h.robot_positions)
    assert not event['exploration_pending_charge_requests']
    assert event['dispatch_lease_deadline_sec'] <= h.robot_tf_received_at['tb1']+2.


@pytest.mark.parametrize('change', ['missing','shortened','changed_route','changed_mode','changed_source',
    'future_source','old_source','missing_body_source','clearance','pending_epoch'])
def test_independent_reader_rejects_unbound_or_weakened_reservations(change):
    _,event = navigation_event();event = copy.deepcopy(event);saved = event['exploration_safety_returns']
    if change == 'missing':event['exploration_safety_returns'] = None
    if change == 'shortened':saved['protected_routes']['tb1'] = saved['protected_routes']['tb1'][:1]
    if change == 'changed_route':saved['route'][-1] = saved['protected_routes']['tb1'][0]
    if change == 'changed_mode':saved['battery_modes']['tb1'] = 'ACTIVE'
    if change == 'changed_source':saved['return_maps']['tb1']['source_time'] -= .1
    if change == 'future_source':saved['inputs']['tb1/frame_state']['source_time'] = event['event_time']+.1
    if change == 'old_source':saved['inputs']['tb1/frame_state']['source_time'] = event['event_time']-2.1
    if change == 'missing_body_source':event['inputs'].pop('tb1/frame_state')
    if change == 'clearance':saved['clearance_m'] = .6
    if change == 'pending_epoch':event['exploration_pending_charge_requests']['tb2'] = event['event_time']+.1
    with pytest.raises(AssertionError):audit_exploration_returns(event,True)
