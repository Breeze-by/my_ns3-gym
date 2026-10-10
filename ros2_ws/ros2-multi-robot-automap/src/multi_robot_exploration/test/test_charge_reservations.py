"""A charge that pauses new exploration must not reserve discarded plans."""
import pytest

from multi_robot_exploration import control
from test_exploration_charging import assignment, charge_node, install_candidates


def crossing_node(monkeypatch):
    node, requests, decisions, sent = charge_node()
    node.robot_positions['tb2'] = (5., 3.)
    node.battery_states['tb2'].update(charge_x=5., charge_y=3.)
    node.battery_states['tb1']['energy'] = 80.
    install_candidates(monkeypatch, {
        'tb1': [assignment(7., 3., 5., utility=1000.)],
        'tb2': [assignment(3., 3., 2., utility=100.)],
    })
    return node, requests, decisions, sent


def test_needed_charge_precedes_an_unissued_crossing_peer_plan(monkeypatch):
    node, requests, decisions, sent = crossing_node(monkeypatch)
    control.HeadquartersControl.assign_idle_robots(node)
    assert not sent and [name for name, _ in requests] == ['tb2']
    assert node.robot_states == {'tb1': 'idle', 'tb2': 'idle'}
    assert node.exploration_resume_intents['tb2'] == (3., 3., 1000)
    assert 10. < requests[0][1]['required_energy'] < 80.
    assert decisions[0]['return_preparation']['returning'] == 'tb2'


def test_funded_actions_keep_the_original_concurrent_route_reservations(monkeypatch):
    node, requests, _, sent = crossing_node(monkeypatch)
    node.battery_states['tb2']['energy'] = 80.
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and [name for name, _ in sent] == ['tb1']


def test_body_detour_can_make_a_nominally_funded_candidate_require_charge(monkeypatch):
    node, requests, _, sent = crossing_node(monkeypatch)
    # The old nominal estimate is affordable, but the unchanged body-masked
    # complete path is longer. Charging still pauses the unissued peer plan.
    goal = assignment(3., 3., .1, utility=100.)
    install_candidates(monkeypatch, {
        'tb1': [assignment(7., 3., 5., utility=1000.)], 'tb2': [goal]})
    nominal = control.HeadquartersControl.exploration_required_energy(
        node, 'tb2', goal.path_distance_m, (goal.x, goal.y))
    node.battery_states['tb2']['energy'] = nominal + .1
    assert node.exploration_battery_factor('tb2', .1, (3., 3.)) == 1.
    control.HeadquartersControl.assign_idle_robots(node)
    assert not sent and [name for name, _ in requests] == ['tb2']
    assert requests[0][1]['available_energy'] < requests[0][1]['required_energy']


def test_real_accepted_peer_route_still_blocks_the_charge_window(monkeypatch):
    node, requests, _, sent = crossing_node(monkeypatch)
    node.robot_states['tb1'] = 'active'
    node.goal_routes['tb1'] = ((2., 3.), (4.5, 3.))
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and not sent
    assert node.robot_states['tb1'] == 'active'
    assert node.goal_routes['tb1'] == ((2., 3.), (4.5, 3.))


@pytest.mark.parametrize('mode', ['RETURNING', 'CHARGING'])
def test_native_return_or_charging_owner_remains_serial(monkeypatch, mode):
    node, requests, _, sent = crossing_node(monkeypatch)
    node.battery_modes['tb1'] = mode
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and not sent


def test_unfundable_charge_does_not_suppress_independent_funded_work(monkeypatch):
    node, requests, _, sent = crossing_node(monkeypatch)
    node.battery_states['tb2']['capacity'] = 12.
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and [name for name, _ in sent] == ['tb1']


def test_body_obstacle_is_still_present_when_pricing_charge_intent(monkeypatch):
    node, requests, _, _ = crossing_node(monkeypatch)
    seen = []
    original = control.plan_rally_leg
    def plan(pose, *args, **kwargs):
        seen.append((pose, kwargs['blocked_positions']))
        return original(pose, *args, **kwargs)
    monkeypatch.setattr(control, 'plan_rally_leg', plan)
    control.HeadquartersControl.assign_idle_robots(node)
    assert requests
    assert any((pose.x, pose.y) == (3., 3.) and (2., 3.) in blocked
               for pose, blocked in seen)


def test_planning_expiry_cannot_publish_the_charge_or_the_peer_plan(monkeypatch):
    node, requests, _, sent = crossing_node(monkeypatch)
    clock = [10.]
    node.now = lambda: clock[0]
    original = control.plan_rally_leg
    def plan(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] = 13.
        return result
    monkeypatch.setattr(control, 'plan_rally_leg', plan)
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and not sent and not node.rally_charge_requested
