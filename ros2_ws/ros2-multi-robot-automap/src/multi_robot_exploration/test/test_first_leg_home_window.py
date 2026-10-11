"""A real near-home prefix survives a prior clearance escape."""
import copy
import gzip
import json
import math
from pathlib import Path

import pytest

from multi_robot_exploration import control as c
from p2c_initial_replenishment import audit_initial_prefix
from p2c_return_preparation import decode_grid
from test_exploration_charging import assignment, install_candidates
from test_first_leg_return_heading import first_node

FIXTURE = json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v80_first_window_inputs.json.gz', 'rt'))
assert FIXTURE['source_commit'] == 'e309353c13ec979e504da61fc8d132fa6cfc1b14'


def reference_assign():
    namespace = dict(vars(c))
    for source in FIXTURE['original_sources'].values():
        exec(compile(source, '<e309353 original>', 'exec'), namespace)
    return namespace['assign_idle_robots']


def displaced_node():
    h, requests, events, sent = first_node()
    h.robot_positions['tb1'] = (3.15, 3.)
    h.pending_exploration_geometry = dict(context=('EXPLORE', False, ('tb1','tb2'), None),
        generated_at=9., points={'tb1':((5.,3.),)}, cursor={})
    return h, requests, events, sent


def test_original_corridor_has_a_funded_real_homeward_prefix_after_clearance():
    event = FIXTURE['event']; name = event['robot']; planning = event['planning_map']
    position = event['current_position']; state = event['battery_states'][name]
    preference = c.initial_replenishment_prefix(state, position, 0, planning['resolution'])
    assert preference is not None
    namespace = dict(vars(c)); exec(FIXTURE['original_sources']['initial_replenishment_prefix'], namespace)
    assert namespace['initial_replenishment_prefix'](state, position, 0, planning['resolution']) is None
    target = event['travel_preference']['deferred_geometry_preference']['points'][24]
    local = event['return_maps'][name]
    full = c.plan_rally_leg(c.RallyPose(*target,0.), decode_grid(planning), planning['resolution'], planning['origin'], position,
        blocked_positions=[p for n,p in event['robot_positions'].items() if n!=name], clearance_m=c.PATH_CLEARANCE_M,
        visible_only=True, local_map=dict(data=decode_grid(local), resolution=local['resolution'], origin=local['origin']))
    leg = c.initial_replenishment_leg(full, preference)
    assert leg is not None
    endpoint = (leg[0].x,leg[0].y)
    assert math.dist(endpoint, position) == pytest.approx(.9809125484999476)
    assert math.dist(endpoint, (.45,0.)) == pytest.approx(1.0030070970142704)
    assert leg[1] == full[1][:len(leg[1])]


def test_current_geometry_prefers_real_homeward_work_before_old_deferred_outward_points(monkeypatch):
    install_candidates(monkeypatch, {'tb1':[assignment(5.,3.,distance=2.,utility=100.), assignment(1.,3.,distance=2.,utility=50.)]})
    results=[]
    for assign in (reference_assign(), c.HeadquartersControl.assign_idle_robots):
        h, requests, events, sent = displaced_node(); assign(h)
        assert len(sent)==1 and not requests and not h.successful_exploration_legs
        results.append((sent[0][1],events[-1]))
    assert results[0][0].x==5. and results[1][0].x==1.
    new=results[1][1]
    assert .7<=math.dist(new['requested_position'],(2.,3.))<=1.25
    assert math.dist(new['requested_position'],new['current_position'])>.35
    assert audit_initial_prefix({'tb1':[new]}, {}, True, True)['bounded_first_legs']==1
    assert new['travel_preference']['planned_distance_m']>math.dist(new['requested_position'],new['current_position'])


def test_no_near_home_route_keeps_the_original_long_ordinary_candidate(monkeypatch):
    install_candidates(monkeypatch, {'tb1':[assignment(5.,3.,distance=2.)]})
    h, requests, events, sent=displaced_node(); c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and sent[0][1].x==5. and not requests
    assert h.exploration_travel_choices['tb1']['initial_replenishment_prefix'] is None


def test_unfunded_preferred_full_frontier_keeps_a_funded_normal_alternative(monkeypatch):
    install_candidates(monkeypatch, {'tb1':[assignment(.5,5.5,distance=5.,utility=100.), assignment(3.5,3.,distance=.35,utility=10.)]})
    h, requests, _, sent=displaced_node();h.battery_states['tb1']['energy']=20.
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and sent[0][1].x==3.5 and not requests
    assert h.exploration_travel_choices['tb1']['initial_replenishment_prefix'] is None


def test_reserved_window_prefix_keeps_an_unreserved_original_route(monkeypatch):
    install_candidates(monkeypatch, {'tb1':[assignment(4.,3.,distance=2.)]})
    h, requests, _, sent=first_node();original=c.reserve_rally_prefix
    def reserve(plan,reservations):
        return None if math.dist((plan[0].x,plan[0].y),(2.,3.))<=1.25 else original(plan,reservations)
    monkeypatch.setattr(c,'reserve_rally_prefix',reserve)
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and sent[0][1].x==4. and not requests
    assert h.exploration_travel_choices['tb1']['initial_replenishment_prefix'] is None


def test_expiration_inside_geometry_discards_both_candidate_tiers(monkeypatch):
    install_candidates(monkeypatch, {'tb1':[assignment(4.,3.,distance=2.)]})
    h, requests, events, sent=first_node();original=c.initial_replenishment_leg
    def expire(*args):
        result=original(*args);h.clock=12.001;return result
    monkeypatch.setattr(c,'initial_replenishment_leg',expire)
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and not requests and not h.successful_exploration_legs
    assert any(e.get('event')=='coordinator_planning_lease_expired' for e in events)


@pytest.mark.parametrize('tamper', ['legacy','minimum','maximum','motion','unreserved','short','past_success','body'])
def test_reader_rebuilds_route_and_rejects_invalid_window_authority(monkeypatch,tamper):
    install_candidates(monkeypatch, {'tb1':[assignment(4.,3.,distance=2.)]})
    h,_,events,_=first_node();c.HeadquartersControl.assign_idle_robots(h)
    event=copy.deepcopy(events[-1]);saved=event['travel_preference']['initial_replenishment_prefix']; successes={}
    if tamper=='legacy':saved['strategy']='first_real_leg_near_home'
    if tamper=='minimum':saved['minimum_home_distance_m']=0.
    if tamper=='maximum':saved['maximum_home_distance_m']=1.6
    if tamper=='motion':saved['minimum_motion_m']=.02
    if tamper=='unreserved':saved['window_endpoint'][0]+=.1
    if tamper=='short':event['requested_position']=event['current_position']
    if tamper=='past_success':successes={'tb1':[9.]}
    if tamper=='body':event['robot_positions']['tb2']=saved['window_endpoint']
    with pytest.raises(AssertionError):audit_initial_prefix({'tb1':[event]}, successes, True, True)
