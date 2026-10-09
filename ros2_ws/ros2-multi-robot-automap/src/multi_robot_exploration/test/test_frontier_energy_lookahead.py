"""A fresh two-frontier forecast can use a real near-home charging opportunity."""
from dataclasses import replace
import base64
import copy
import zlib

import numpy as np

import pytest

from multi_robot_exploration import control
from test_exploration_charging import opportunity_node, assignment, install_candidates


def goals():
    first = assignment(3.5, 3., distance=.5, utility=100.)
    second = assignment(8., 3., distance=5., utility=90.)
    second = replace(second, viewpoint=replace(second.viewpoint, group_id=2))
    return first, second


def setup():
    node, requests, decisions, sent = opportunity_node()
    node.battery_states['tb1']['energy'] = 24.
    node.robot_positions['tb2'] = (8.,5.)
    first, second = goals()
    node.frontier_charge_lookahead = (node.map_data, node.map_received_at, {'tb1':[first, second]})
    node.opportunity_charge_evidence = {}
    return node, requests, decisions, sent, first, second


def test_two_step_forecast_triggers_above_the_old_fixed_quarter_threshold(monkeypatch):
    node, requests, decisions, sent, first, second = setup()
    install_candidates(monkeypatch, {'tb1':[first, second]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(requests) == 1 and not sent
    forecast = decisions[0]['opportunity_lookahead']
    assert forecast['strategy'] == 'two_current_frontiers'
    assert 24. < forecast['required_energy'] < 80.
    assert requests[0][1]['required_energy'] == pytest.approx(forecast['required_energy'])
    assert forecast['first_position'] == [3.5, 3.] and forecast['second_position'] == [8., 3.]
    assert forecast['map_evidence']['source'] == 'ap_delivered_planning_map'
    # The second frontier is a forecast, not a second dispatched action.
    assert node.exploration_resume_intents['tb1'] == (3.5, 3., 1000)


@pytest.mark.parametrize('reason', ['same_group','overlap','low_gain','low_utility','blocked',
    'unknown','old_map_object','stale','unfundable','full_energy','live_peer','no_work','not_near_home'])
def test_forecast_never_authorizes_unknown_stale_unfundable_or_unsafe_charging(monkeypatch, reason):
    node, requests, decisions, sent, first, second = setup()
    if reason == 'same_group': second = replace(second, viewpoint=replace(second.viewpoint, group_id=1))
    if reason == 'overlap': second = replace(second, x=3.6)
    if reason == 'low_gain': second = replace(second, viewpoint=replace(second.viewpoint, information_gain=200))
    if reason == 'low_utility': second = replace(second, utility=49.)
    if reason == 'blocked': node.map_data[:,55:57] = 100
    if reason == 'unknown': node.map_data[:,55:57] = -1
    if reason == 'unfundable': node.battery_states['tb1']['capacity'] = 30.
    if reason == 'full_energy': node.battery_states['tb1']['energy'] = 80.
    if reason == 'live_peer': node.robot_states['tb2'] = 'active'
    if reason == 'no_work': node.successful_exploration_legs.clear()
    if reason == 'not_near_home': node.robot_positions['tb1'] = (4.,3.)
    if reason == 'stale':
        node.map_received_at = 4.
        node.fresh_robot_inputs = lambda: False
    if reason == 'old_map_object':
        node.frontier_charge_lookahead = (node.map_data.copy(), node.map_received_at, {'tb1':[first,second]})
        assert control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.) is None
        return
    install_candidates(monkeypatch, {'tb1':[first, second]})
    control.HeadquartersControl.assign_idle_robots(node)
    # An unfunded second frontier must not suppress the funded first task.
    assert not requests


def test_forecast_prices_full_endpoint_return_and_ignores_unreachable_alternative():
    node, _, _, _, first, second = setup()
    forecast = control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.)
    assert forecast['between_distance_m'] > 4.4
    assert forecast['home_distance_m'] > 5.
    expected = control.HeadquartersControl.task_return_required_energy(node,'tb1',
        first.path_distance_m + forecast['between_distance_m'], (second.x, second.y))
    assert forecast['required_energy'] == pytest.approx(expected)
    node.map_data[:,55:57] = 100
    assert control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.) is None


def test_one_map_update_discards_previous_lookahead_and_body_detour_is_priced():
    node, _, _, _, first, second = setup()
    original = control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.)
    node.robot_positions['tb2'] = (5.5,3.)
    blocked = control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.)
    assert blocked['between_distance_m'] > original['between_distance_m']
    node.map_data = node.map_data.copy()
    assert control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.) is None


@pytest.mark.parametrize('corruption',[None,'path','cost','group','map','age'])
def test_read_only_forecast_audit_reconstructs_and_rejects_forged_decisions(corruption):
    from check_p2c_gate import lookahead_audit
    node, _, _, _, first, _ = setup()
    forecast=control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.)
    event=dict(event='coordinator_charge_decision',robot='tb1',event_time=10.,available_energy=24.,
               required_energy=forecast['required_energy'],opportunity_lookahead=copy.deepcopy(forecast),
               inputs={'headquarters/fused_map_snapshot':dict(source_time=10.),
                           'tb1/map_snapshot':dict(source_time=10.),
                           'tb1/frame_state':dict(age_sec=0.),
                       'tb1/pose_state':dict(age_sec=0.)})
    f=event['opportunity_lookahead']
    if corruption=='path':f['between_distance_m']+=1.
    if corruption=='cost':f['required_energy']+=1.;event['required_energy']=f['required_energy']
    if corruption=='group':f['second_group']=f['first_group']
    if corruption=='map':
        saved=f['map_evidence']
        raw=np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape']).copy()
        raw[:,55:57]=100
        saved['grid']=base64.b64encode(zlib.compress(raw.tobytes())).decode()
    if corruption=='age':f['pose_age_sec']=2.1
    if corruption is None:
        assert lookahead_audit([event])['two_frontier_charge_decisions']==1
    else:
        with pytest.raises(AssertionError):lookahead_audit([event])


@pytest.mark.parametrize('corruption',[None,'omit_frame','renew_odom','scalar_age','future_frame'])
def test_compound_pose_forecast_audit_requires_the_original_frame_age(corruption):
    from check_p2c_gate import lookahead_audit
    node,_,_,_,first,_=setup()
    node.robot_tf_received_at={'tb1':9.3,'tb2':10.}
    forecast=control.HeadquartersControl.frontier_lookahead_budget(node,'tb1',first,24.,80.)
    assert forecast['pose_age_sec']==pytest.approx(.7)
    event=dict(event='coordinator_charge_decision',robot='tb1',event_time=10.,available_energy=24.,
        required_energy=forecast['required_energy'],opportunity_lookahead=copy.deepcopy(forecast),
        inputs={'headquarters/fused_map_snapshot':dict(source_time=10.),
                'tb1/map_snapshot':dict(source_time=10.),
                'tb1/pose_state':dict(age_sec=0.),'tb1/frame_state':dict(age_sec=.7)})
    f=event['opportunity_lookahead']
    if corruption=='omit_frame':f['pose_source_ages_sec'].pop('frame')
    if corruption=='renew_odom':f['pose_source_ages_sec']['odom']=.1
    if corruption=='scalar_age':f['pose_age_sec']=0.
    if corruption=='future_frame':f['pose_source_ages_sec']['frame']=-.1;event['inputs']['tb1/frame_state']['age_sec']=-.1
    if corruption is None:assert lookahead_audit([event],True)['two_frontier_charge_decisions']==1
    else:
        with pytest.raises(AssertionError):lookahead_audit([event],True)
