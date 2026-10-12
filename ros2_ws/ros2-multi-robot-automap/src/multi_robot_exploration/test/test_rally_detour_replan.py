"""Complete original geometry, budget and cancellation lifecycle regressions."""
import copy,json,textwrap
from types import SimpleNamespace
import pytest
from multi_robot_exploration import control as c
from rally_detour_reference import fixture_node
from p2c_prepared_dispatch import rebuild_detour_cancel,detour_cancel_audit


def request(node):return c.HeadquartersControl.cancel_obsolete_rally_detour(node)


def test_original_active_detour_is_canceled_with_complete_wait_and_return_budget():
    node,events,canceled,_=fixture_node()
    assert node.rally_wait_budgets=={} and request(node)
    assert canceled==['tb3'] and node.rally_goal_handles['tb3'] is not None
    event=next(e for e in events if e['event']=='coordinator_rally_detour_cancel')
    assert event['comparison']['saved_distance_m']==pytest.approx(4.327749811548899)
    assert event['movement_authorized'] is False and event['held_required_energy']<node.battery_states['tb3']['energy']
    rebuild_detour_cancel(event)
    assert not request(node) and canceled==['tb3']


@pytest.mark.parametrize('condition',['phase','disabled','shutdown','observer','pending_charge','charging_peer',
    'stale_pose','future_pose','stale_map','missing_map','stale_target','near_waypoint','yield','return_yield',
    'probe','preparation','low_energy','peer_low_energy','bad_model','held_body','held_route','no_peer_route','missing_action_context'])
def test_rejected_detours_preserve_active_goal(condition):
    node,events,canceled,_=fixture_node();handle=node.rally_goal_handles['tb3']
    if condition=='phase':node.task_state='FOUND'
    if condition=='disabled':node.enable_battery=False
    if condition=='shutdown':node.shutdown_requested=True
    if condition=='observer':node.target_observing_robot=node.rally_observer_guard='tb3'
    if condition=='pending_charge':node.rally_charge_requested['tb1']=node.clock
    if condition=='charging_peer':node.battery_modes['tb1']='CHARGING'
    if condition=='stale_pose':node.robot_tf_received_at['tb3']=node.clock-2.01
    if condition=='future_pose':node.robot_tf_received_at['tb3']=node.clock+.01
    if condition=='stale_map':node.robot_map_received_at['tb3']=node.clock-5.01
    if condition=='missing_map':node.robot_maps['tb3']=None
    if condition=='stale_target':node.target_received_source_time=node.clock-60.01
    if condition=='near_waypoint':node.rally_leg_poses['tb3']=c.RallyPose(*node.robot_positions['tb3'],0.)
    if condition=='yield':node.rally_yield_requested['tb3']=True
    if condition=='return_yield':node.return_yield_targets['tb3']='tb1'
    if condition=='probe':node.rally_probe_targets.add('tb3')
    if condition=='preparation':node.rally_preparation_approaches={'tb3':{}}
    if condition=='low_energy':node.battery_states['tb3']['energy']=0.
    if condition=='peer_low_energy':node.battery_states['tb1']['energy']=0.
    if condition=='bad_model':node.battery_states['tb3']['nominal_speed_mps']=0.
    if condition=='held_body':node.robot_positions['tb2']=node.robot_positions['tb3']
    if condition=='held_route':node.rally_leg_routes['tb2']=(node.robot_positions['tb2'],node.robot_positions['tb3'])
    if condition=='no_peer_route':node.rally_leg_routes['tb2']=()
    if condition=='missing_action_context':del node.goal_handles
    assert not request(node) and canceled==[] and node.rally_goal_handles['tb3'] is handle
    assert not [e for e in events if e['event']=='coordinator_rally_detour_cancel']


@pytest.mark.parametrize('checkpoint',[260.,280.])
def test_unconnected_original_late_maps_do_not_cancel(checkpoint):
    node,_,canceled,_=fixture_node(checkpoint);assert not request(node) and not canceled


@pytest.mark.parametrize('status',[4,5,6])
def test_only_expected_canceled_result_avoids_the_original_failure_increment(status):
    node,events,_,saved=fixture_node();assert request(node);handle=node.rally_goal_handles['tb3']
    future=SimpleNamespace(result=lambda:SimpleNamespace(status=status))
    c.HeadquartersControl.rally_goal_result(node,'tb3',handle,future)
    assert node.rally_goal_handles['tb3'] is None and 'tb3' not in node.rally_detour_cancellations
    assert node.rally_attempts['tb3']==int(status==6)
    assert detour_cancel_audit(events,True)['closed']==1
    old,_,_,_=fixture_node();original=old.rally_goal_handles['tb3'];namespace=dict(c.__dict__)
    exec(textwrap.dedent(saved['frozen_result_method']),namespace)
    namespace['rally_goal_result'](old,'tb3',original,future)
    assert old.rally_attempts['tb3']==int(status!=4)


def test_late_wrong_handle_cannot_close_current_cancellation():
    node,_,_,_=fixture_node();assert request(node);handle=node.rally_goal_handles['tb3']
    c.HeadquartersControl.rally_goal_result(node,'tb3',object(),SimpleNamespace(result=lambda:SimpleNamespace(status=5)))
    assert node.rally_goal_handles['tb3'] is handle and node.rally_detour_cancellations['tb3'] is handle


def test_cancel_transport_exception_retains_the_active_action():
    node,events,canceled,_=fixture_node();handle=node.rally_goal_handles['tb3']
    def rejected():raise RuntimeError('controlled cancel submission failure')
    handle.cancel_goal_async=rejected
    assert not request(node) and not canceled and node.rally_goal_handles['tb3'] is handle
    assert 'tb3' not in node.rally_detour_cancellations and not events


def test_price_computation_cannot_renew_the_original_pose_lease(monkeypatch):
    node,_,canceled,_=fixture_node();original=c.HeadquartersControl.task_return_required_energy
    def delayed(self,*args,**kwargs):
        answer=original(self,*args,**kwargs);self.clock+=2.1;return answer
    monkeypatch.setattr(c.HeadquartersControl,'task_return_required_energy',delayed)
    assert not request(node) and not canceled


@pytest.mark.parametrize('field',['saving','route','budget','wait','source','battery_stamp','held_budget','body','authority','observer'])
def test_independent_reader_rejects_tampered_cancellation(field):
    node,events,_,_=fixture_node();assert request(node)
    event=copy.deepcopy(next(e for e in events if e['event']=='coordinator_rally_detour_cancel'))
    if field=='saving':event['comparison']['saved_distance_m']+=1.
    if field=='route':event['comparison']['current_full_route'][-1][0]+=.5
    if field=='budget':event['required_budgets']['tb3']-=1.
    if field=='wait':event['wait_budgets_sec']['tb3']=0.
    if field=='source':event['inputs']['tb3/frame_state']['source_time']=event['event_time']+1.
    if field=='battery_stamp':event['battery_states']['tb3']['stamp_sec']-=.1
    if field=='held_budget':event['held_required_energy']-=1.
    if field=='body':event['peer_remaining_routes']['tb2'].append(event['robot_positions']['tb3'])
    if field=='authority':event['movement_authorized']=True
    if field=='observer':event['observer_robot']='tb3'
    with pytest.raises((AssertionError,ValueError)):rebuild_detour_cancel(event)


def test_reader_requires_matching_real_result_closure():
    node,events,_,_=fixture_node();assert request(node)
    with pytest.raises(AssertionError,match='closure'):detour_cancel_audit(events,True)
