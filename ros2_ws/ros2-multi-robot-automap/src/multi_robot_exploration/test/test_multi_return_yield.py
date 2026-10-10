"""One qualified escape can clear several concurrent return cycles."""
import copy
import json
from types import SimpleNamespace

import pytest
from std_msgs.msg import String

from multi_robot_exploration import control as c
from p2c_return_preparation import audit_preparation
from test_exploration_return_preparation import node


def prepared():
    h, events, sent, _ = node()
    h.map_known_count = 0
    h.robot_positions['tb3'] = (-4., 4.)
    h.robot_states['tb3'] = 'idle'
    h.battery_states['tb3'] = {**h.battery_states['tb1'], 'charge_y': 4., 'return_count': 2}
    h.battery_states['tb1']['return_count'] = 2
    h.battery_modes['tb1'] = h.battery_modes['tb3'] = 'RETURNING'
    for attr in ('robot_maps', 'robot_map_received_at', 'robot_odom_received_at', 'robot_tf_received_at',
                 'battery_state_received_at', 'goal_handles', 'goal_targets', 'goal_routes',
                 'rally_goal_handles', 'rally_goal_pending', 'rally_battery_preempted',
                 'cancel_requested', 'battery_preempted'):
        values = getattr(h, attr)
        values['tb3'] = copy.deepcopy(values['tb1'])
    assert c.HeadquartersControl.prepare_exploration_return(h, 'tb1')
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert len(sent) == 1 and audit_preparation(events[0]) == 'yield'
    assert h.exploration_return_yields['tb2']['protected_return_cycles'] == {'tb1': 2, 'tb3': 2}
    return h, events, sent


def test_acceptance_keeps_escape_for_both_qualified_returners(monkeypatch):
    h, _, sent = prepared();canceled = [];callbacks = []
    handle = SimpleNamespace(accepted=True, cancel_goal_async=lambda:canceled.append(True),
                             get_result_async=lambda:object())
    monkeypatch.setattr(c.HeadquartersControl, 'defer_action_done_callback',
                        lambda self, future, callback:callbacks.append(callback))
    c.HeadquartersControl.goal_response_callback(h, 'tb2', SimpleNamespace(result=lambda:handle))
    assert h.goal_handles['tb2'] is handle and callbacks and not canceled


@pytest.mark.parametrize('returner', ['tb1', 'tb3'])
def test_battery_heartbeats_preserve_both_qualified_return_cycles(returner):
    h, _, _ = prepared();canceled = []
    h.goal_handles['tb2'] = SimpleNamespace(cancel_goal_async=lambda:canceled.append(True))
    event = dict(**h.battery_states[returner], mode='RETURNING', stamp_sec=10.)
    c.HeadquartersControl.battery_state_callback(h, String(data=json.dumps(event)), returner)
    assert not canceled and not h.cancel_requested['tb2']
    event['return_count'] += 1
    c.HeadquartersControl.battery_state_callback(h, String(data=json.dumps(event)), returner)
    assert canceled == [True] and h.cancel_requested['tb2']


@pytest.mark.parametrize('reason', ['uncovered', 'new_cycle', 'missing_route', 'ordinary'])
def test_unqualified_returners_still_cancel_on_acceptance(monkeypatch, reason):
    h, _, sent = prepared();canceled = []
    preparation = h.exploration_return_yields['tb2']
    if reason == 'uncovered':preparation['protected_return_cycles'].pop('tb3')
    if reason == 'new_cycle':h.battery_states['tb3']['return_count'] += 1
    if reason == 'missing_route':preparation['protected_routes'].pop('tb3')
    if reason == 'ordinary':h.exploration_return_yields.clear()
    handle = SimpleNamespace(accepted=True, cancel_goal_async=lambda:canceled.append(True),
                             get_result_async=lambda:object())
    monkeypatch.setattr(c.HeadquartersControl, 'defer_action_done_callback', lambda *args:None)
    c.HeadquartersControl.goal_response_callback(h, 'tb2', SimpleNamespace(result=lambda:handle))
    assert canceled == [True] and h.battery_preempted['tb2']


@pytest.mark.parametrize('reason', ['missing', 'extra', 'changed'])
def test_reader_rejects_return_cycle_authority_changes(reason):
    _, events, _ = prepared();event = copy.deepcopy(events[0])
    cycles = event['return_preparation']['protected_return_cycles']
    if reason == 'missing':cycles.pop('tb3')
    if reason == 'extra':cycles['tb2'] = 0
    if reason == 'changed':cycles['tb3'] += 1
    with pytest.raises(AssertionError):audit_preparation(event)


def test_prospective_owner_is_bound_to_its_next_return_cycle():
    h, _, sent, _ = node();h.battery_states['tb1']['return_count'] = 1
    c.HeadquartersControl.prepare_exploration_return(h, 'tb1')
    c.HeadquartersControl.admit_exploration_return_yield(h)
    assert sent and h.exploration_return_yields['tb2']['protected_return_cycles'] == {'tb1': 2}
    preparation = h.exploration_return_yields['tb2']
    assert c.exploration_yield_covers_return(preparation, 'tb1', {'return_count': 2})
    assert not c.exploration_yield_covers_return(preparation, 'tb1', {'return_count': 3})
