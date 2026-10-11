"""Abandoned first-window geometry must be repriced on a fresh callback."""
import copy
import gzip
import json
from pathlib import Path

import pytest

from multi_robot_exploration import control as c
from p2c_initial_replenishment import audit_first_window_handoffs, audit_initial_prefix
from test_exploration_charging import assignment, install_candidates
from test_exploration_return_preparation import advance_sources
from test_first_leg_return_heading import first_node

FIXTURE = json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v81_first_window_handoff_inputs.json.gz', 'rt'))
assert FIXTURE['source_commit'] == 'b9ef25542d498b3a076f8bd350519298a974345b'


def original_assign():
    namespace = dict(vars(c))
    exec(compile(FIXTURE['original_assign'], '<original b9ef255 assign>', 'exec'), namespace)
    return namespace['assign_idle_robots']


def fresh(h, value):
    advance_sources(h, value)
    for state in h.battery_states.values():
        state['stamp_sec'] = value


def abandoned(monkeypatch, use_original=False):
    h, requests, events, sent = first_node()
    install_candidates(monkeypatch, {'tb1': [assignment(4., y, distance=2., utility=100.-i)
        for i, y in enumerate((2.4, 2.6, 2.8, 3., 3.2, 3.4))]})
    base = c.initial_replenishment_leg
    calls = []
    def expire(plan, preference):
        result = base(plan, preference)
        calls.append(result)
        if len(calls) == 4:
            h.clock += 2.001
        return result
    monkeypatch.setattr(c, 'initial_replenishment_leg', expire)
    assign = original_assign() if use_original else c.HeadquartersControl.assign_idle_robots
    assign(h)
    assert not sent and not requests and not h.successful_exploration_legs
    assert len(calls) == 4 and all(calls[:3])
    assert events[-1]['event'] == 'coordinator_planning_lease_expired'
    return h, requests, events, sent, calls, assign, base


def test_original_repeats_expensive_scan_new_callback_revalidates_three_points(monkeypatch):
    results = []
    for use_original in (True, False):
        with monkeypatch.context() as patch:
            h, requests, events, sent, calls, assign, _ = abandoned(patch, use_original)
            saved = copy.deepcopy(h.pending_exploration_geometry)
            fresh(h, 13.); calls.clear(); assign(h)
            results.append((len(calls), len(sent)))
            assert not requests and not h.successful_exploration_legs
            if not use_original:
                assert len(saved['first_window_geometry']['tb1']['points']) == 3
                assert set(saved['first_window_geometry']['tb1']) == {'points', 'generated_at_sec', 'expired_at_sec'}
                decisions = [e for e in events if e.get('event') == 'coordinator_navigation_decision']
                expirations = [e for e in events if e.get('event') == 'coordinator_planning_lease_expired']
                assert audit_first_window_handoffs({'tb1': decisions}, expirations, True)['revalidated_navigation'] == 1
                assert audit_initial_prefix({'tb1': decisions}, {}, True, True)['bounded_first_legs'] == 1
    assert results == [(4, 0), (3, 1)]


def test_partial_geometry_progress_across_robot_batches_still_reprices_every_route(monkeypatch):
    h, requests, events, sent = first_node()
    h.robot_states['tb2'] = 'idle'; h.robot_positions['tb2'] = (5., 3.)
    h.battery_states['tb2'].update(energy=40., charge_count=0, charge_x=5., charge_y=3., charge_radius_m=.8)
    install_candidates(monkeypatch, {name: [assignment(x, y, distance=2., utility=100.-i)
        for i, y in enumerate((2.4, 2.6, 2.8, 3., 3.2, 3.4))]
        for name, x in (('tb1', 4.), ('tb2', 7.))})
    base = c.initial_replenishment_leg; calls = {}
    def expire(plan, preference):
        result = base(plan, preference); key = tuple(preference['robot_position'])
        calls[key] = calls.get(key, 0)+1
        if calls[key] == 4: h.clock += 2.001
        return result
    monkeypatch.setattr(c, 'initial_replenishment_leg', expire)
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and set(h.pending_exploration_geometry['first_window_geometry']) == {'tb1'}
    fresh(h, 13.); calls.clear(); c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and set(h.pending_exploration_geometry['first_window_geometry']) == {'tb1', 'tb2'}
    fresh(h, 16.); calls.clear(); c.HeadquartersControl.assign_idle_robots(h)
    assert set(name for name, _ in sent) == {'tb1', 'tb2'} and all(value == 3 for value in calls.values())
    assert not requests and not h.successful_exploration_legs
    decisions = [e for e in events if e.get('event') == 'coordinator_navigation_decision']
    expired = [e for e in events if e.get('event') == 'coordinator_planning_lease_expired']
    by_robot = {name: [e for e in decisions if e['robot'] == name] for name in ('tb1', 'tb2')}
    assert audit_first_window_handoffs(by_robot, expired, True)['revalidated_navigation'] == 2
    assert audit_initial_prefix(by_robot, {}, True, True)['bounded_first_legs'] == 2


@pytest.mark.parametrize('change', ['map', 'body', 'budget', 'expired_again'])
def test_point_hints_do_not_authorize_work_after_current_inputs_change(monkeypatch, change):
    h, requests, events, sent, calls, assign, base = abandoned(monkeypatch)
    fresh(h, 13.); calls.clear()
    if change == 'map':
        h.map_data[:, 30:32] = 100
    elif change == 'body':
        h.robot_positions['tb2'] = h.robot_positions['tb1']
    elif change == 'budget':
        h.battery_states['tb1']['energy'] = 1.
    else:
        def expire_again(*args):
            result = base(*args); h.clock = 15.001; return result
        monkeypatch.setattr(c, 'initial_replenishment_leg', expire_again)
    assign(h)
    assert not sent and not requests and not h.successful_exploration_legs
    assert not any(e.get('event') == 'coordinator_navigation_decision' for e in events)


@pytest.mark.parametrize('change', ['expired_hint', 'phase', 'ordinary_success', 'native_charge'])
def test_old_or_ineligible_geometry_returns_to_current_candidate_generation(monkeypatch, change):
    h, _, events, sent, calls, assign, base = abandoned(monkeypatch)
    fresh(h, 71. if change == 'expired_hint' else 13.)
    if change == 'phase':
        h.task_state = 'FOUND_UNCONFIRMED'
    elif change == 'ordinary_success':
        h.successful_exploration_legs['tb1'] = 2
    elif change == 'native_charge':
        h.battery_states['tb1']['charge_count'] = 1
    calls.clear()
    def count(*args):
        calls.append(1); return base(*args)
    monkeypatch.setattr(c, 'initial_replenishment_leg', count)
    # The original literal uses its own globals; this case uses current code.
    c.HeadquartersControl.assign_idle_robots(h)
    assert sent
    event = next(e for e in events if e.get('event') == 'coordinator_navigation_decision')
    assert event['travel_preference']['first_window_geometry_preference'] is None
    assert len(calls) > 3 if change in ('expired_hint', 'phase') else not calls


def test_unfunded_or_unusable_homeward_hints_keep_a_funded_normal_route(monkeypatch):
    h, requests, events, sent, _, assign, base = abandoned(monkeypatch)
    fresh(h, 13.); h.robot_positions['tb1'] = (3.15, 3.)
    h.battery_states['tb1']['energy'] = 20.
    install_candidates(monkeypatch, {'tb1': [assignment(.5, 5.5, distance=5., utility=100.),
        assignment(3.5, 3., distance=.35, utility=10.)]})
    monkeypatch.setattr(c, 'initial_replenishment_leg', base)
    assign(h)
    assert len(sent) == 1 and sent[0][1].x == 3.5 and not requests
    event = next(e for e in events if e.get('event') == 'coordinator_navigation_decision')
    assert event['travel_preference']['initial_replenishment_prefix'] is None
    expired = [e for e in events if e.get('event') == 'coordinator_planning_lease_expired']
    assert audit_first_window_handoffs({'tb1': [event]}, expired, True)['revalidated_navigation'] == 1


@pytest.mark.parametrize('tamper', ['missing', 'undeclared', 'prior_missing', 'point', 'too_many',
    'route_reused', 'budget_reused', 'extra_budget', 'future', 'old_source', 'context', 'selected'])
def test_reader_rejects_old_authority_or_untraceable_points(monkeypatch, tamper):
    h, _, events, _, _, assign, base = abandoned(monkeypatch)
    fresh(h, 13.); monkeypatch.setattr(c, 'initial_replenishment_leg', base); assign(h)
    event = copy.deepcopy(next(e for e in events if e.get('event') == 'coordinator_navigation_decision'))
    expired = copy.deepcopy([e for e in events if e.get('event') == 'coordinator_planning_lease_expired'])
    saved = event['travel_preference']['first_window_geometry_preference']
    if tamper == 'missing': del event['travel_preference']['first_window_geometry_preference']
    elif tamper == 'prior_missing': expired = []
    elif tamper == 'point': saved['points'][0][0] += .1
    elif tamper == 'too_many': saved['points'].append([9., 9.])
    elif tamper in ('route_reused', 'budget_reused'): saved[tamper] = True
    elif tamper == 'extra_budget': saved['required_energy'] = 0.
    elif tamper == 'future': saved['expired_at_sec'] = 14.
    elif tamper == 'old_source': event['inputs']['tb1/pose_state']['source_time'] = 10.
    elif tamper == 'context': saved['context'][0] = 'RALLY'
    elif tamper == 'selected': saved['current_candidate_points'] = [[9., 9.]]
    with pytest.raises(AssertionError):
        audit_first_window_handoffs({'tb1': [event]}, expired, tamper != 'undeclared')
