"""An expired probe search carries a point, never old navigation authority."""
import copy
import gzip
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from builtin_interfaces.msg import Time

from multi_robot_exploration import control as c
from test_rally_observation_recovery import observer_node

FIXTURE = json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v82_first_window_reservation_inputs.json.gz', 'rt'))


def node():
    h, client = observer_node();clock = [13.]
    h.now = lambda: clock[0]
    names = list(h.robot_positions)
    h.map_data[:, 65] = 100
    h.robot_maps = {n:dict(data=h.map_data,resolution=h.resolution,origin=h.origin) for n in names}
    h.robot_odom_received_at = dict.fromkeys(names,13.)
    h.robot_tf_received_at = dict.fromkeys(names,13.)
    h.robot_map_received_at = dict.fromkeys(names,13.)
    h.battery_state_received_at = dict.fromkeys(names,13.)
    h.map_received_at = h.target_received_source_time = 13.
    h.robot_nav_clients['tb2'] = client
    h.participating_robots = h.input_robot_names = lambda:names[:]
    h.rally_targets = {'tb1':c.RallyPose(2.05,2.05,0.),'tb2':c.RallyPose(6.05,8.05,0.)}
    h.rally_final_targets = dict(h.rally_targets)
    h.rally_arrived = {'tb1':True,'tb2':False}
    h.rally_probe_targets = set();h.rally_probe_robot = None
    h.rally_yield_targets = set();h.rally_route_unavailable_since = {'tb1':None,'tb2':10.}
    h.goal_handles = dict.fromkeys(names)
    h.fresh_robot_inputs = lambda:all(0<=clock[0]-v<=2. for v in h.robot_tf_received_at.values())
    h.fresh_robot_poses = h.fresh_robot_inputs
    h.fresh_target = lambda:0<=clock[0]-h.target_received_source_time<=60.
    h.send_survey_goal = lambda *a,**k:c.HeadquartersControl.send_survey_goal(h,*a,**k)
    h.get_clock = lambda:Mock(now=lambda:Mock(to_msg=lambda:Time(sec=int(clock[0]))))
    h.task_state = 'RALLY'
    h.pending_rally_probe_geometry = dict(robot='tb2',point=[7.05,8.05],generated_at_sec=10.,
        expired_at_sec=12.1,target=tuple(h.target),participants=tuple(names),final_pose=h.rally_final_targets['tb2'])
    return h, client, clock


def renew(h, clock, value):
    clock[0] = value;h.map_received_at = h.target_received_source_time = value
    for field in ('robot_odom_received_at','robot_tf_received_at','robot_map_received_at','battery_state_received_at'):
        setattr(h,field,dict.fromkeys(h.robot_positions,value))


def test_current_route_budget_and_heading_admit_the_point_without_work_or_charge_credit():
    h, client, _ = node();before = copy.deepcopy(h.battery_states)
    assert c.HeadquartersControl.admit_rally_probe(h)
    assert client.send_goal_async.call_count == 1 and h.survey_goal_pending
    goal = client.send_goal_async.call_args.args[0].pose
    assert (goal.pose.position.x,goal.pose.position.y) == pytest.approx((7.05,8.05))
    assert h.record_navigation_decision.call_args.args[1] == 'target_survey'
    assert h.rally_probe_targets == {'tb2'} and h.rally_route_unavailable_since['tb2'] == 13.
    assert h.pending_rally_probe_geometry is None and h.battery_states == before


@pytest.mark.parametrize('change', ['stale','target','participants','final','phase','too_old',
    'route_timeout','charged','returning_peer','pending_charge','yield','active_frontier',
    'active_rally','survey','arrived','occupied','body','no_return','low_energy','final_reachable'])
def test_hint_cannot_authorize_navigation_when_current_guards_fail(change):
    h, client, clock = node()
    if change == 'stale':clock[0] = 15.001
    elif change == 'target':h.target = (2.15,4.05)
    elif change == 'participants':h.participating_robots = lambda:['tb2']
    elif change == 'final':h.rally_final_targets['tb2'] = c.RallyPose(6.15,8.05,0.)
    elif change == 'phase':h.task_state = 'FOUND'
    elif change == 'too_old':h.pending_rally_probe_geometry['generated_at_sec'] = -48.
    elif change == 'route_timeout':h.rally_route_unavailable_since['tb2'] = -47.
    elif change == 'charged':h.battery_modes['tb2'] = 'CHARGING'
    elif change == 'returning_peer':h.battery_modes['tb1'] = 'RETURNING'
    elif change == 'pending_charge':h.rally_charge_requested['tb1'] = 13.
    elif change == 'yield':h.rally_yield_targets.add('tb2')
    elif change == 'active_frontier':h.goal_handles['tb1'] = object()
    elif change == 'active_rally':h.rally_goal_pending['tb1'] = True
    elif change == 'survey':h.survey_goal_pending = True
    elif change == 'arrived':h.rally_arrived['tb2'] = True
    elif change == 'occupied':h.map_data[76:86,68:76] = 100
    elif change == 'body':h.robot_positions['tb1'] = (7.8,8.05)
    elif change == 'no_return':h.battery_states['tb2']['charge_x'] = 0.
    elif change == 'low_energy':h.battery_states['tb2']['energy'] = 1.
    else:h.map_data[:,65] = 0
    assert not c.HeadquartersControl.admit_rally_probe(h)
    assert not client.send_goal_async.called and h.survey_attempts == 0


def test_expiration_during_current_reprice_keeps_hint_without_renewing_its_epoch(monkeypatch):
    h, client, clock = node();hint = copy.deepcopy(h.pending_rally_probe_geometry)
    original = h.exploration_battery_factor
    def expired(*args):
        result = original(*args);clock[0] = 15.001;return result
    monkeypatch.setattr(h,'exploration_battery_factor',expired)
    assert not c.HeadquartersControl.admit_rally_probe(h)
    assert not client.send_goal_async.called and not h.rally_probe_targets
    assert h.pending_rally_probe_geometry == hint
    monkeypatch.setattr(h,'exploration_battery_factor',original);renew(h,clock,16.)
    assert c.HeadquartersControl.admit_rally_probe(h) and client.send_goal_async.call_count == 1


def test_original_slow_search_expires_again_new_update_uses_fresh_point(monkeypatch):
    results = []
    for original in (True,False):
        h, client, clock = node();h.pending_rally_probe_geometry = None
        h.__dict__.update(enable_rally=True,last_input_availability=True,last_input_diagnostic_at=13.,
            message_freshness_timeout_sec=5.,battery_monitor_started_at=13.,stop_target_scan=lambda:False,
            release_return_yields=lambda:None,yield_to_returning_robot=lambda:None,
            last_rally_dispatch_at=10.,global_battery_rally_pause=False,
            prepare_rally_charges=lambda:set(),rally_preflight_complete=True,
            rally_dispatch_order=['tb1','tb2'],rally_approach_routes=dict.fromkeys(h.robot_positions,()),
            rally_recovery_requested=dict.fromkeys(h.robot_positions,False),
            rally_goal_started_at=dict.fromkeys(h.robot_positions),rally_yield_requested=dict.fromkeys(h.robot_positions,False),
            rally_attempts=dict.fromkeys(h.robot_positions,0),rally_hold_started_at=None,
            survey_robot=None,rally_max_concurrent=2,rally_goal_timeout_sec=60.,
            get_logger=lambda:Mock(),robot_velocities=dict.fromkeys(h.robot_positions,(0.,0.)),
            rally_linear_tolerance=.02,rally_angular_tolerance=.05,active_batteries_ready=lambda:True,
            input_freshness_details=lambda:{},consumed_publisher=Mock(),publish_rally_assignments=Mock())
        searches = []
        with monkeypatch.context() as patch:
            patch.setattr(c.HeadquartersControl,'restore_observer_heading',lambda _:False)
            patch.setattr(c,'reassign_rally_pose',lambda *a,**k:None)
            def slow(*a,**k):
                searches.append(clock[0]);clock[0] += 2.1
                return c.RallyPose(7.05,8.05,0.)
            patch.setattr(c,'rally_survey_pose',slow)
            namespace = dict(vars(c))
            exec(compile(FIXTURE['original_update_mission'],'<original 2f4aeda update>', 'exec'),namespace)
            update = namespace['update_mission'] if original else c.HeadquartersControl.update_mission
            update(h)
            assert not client.send_goal_async.called and not h.rally_probe_targets
            assert bool(h.pending_rally_probe_geometry) is (not original)
            renew(h,clock,16.);update(h)
        results.append((len(searches),client.send_goal_async.call_count))
    assert results == [(2,0),(1,1)]
