"""An advancing clock must revoke a plan before any motion or charge dispatch."""
import copy
from types import SimpleNamespace

import pytest
from multi_robot_exploration import control
from test_exploration_charging import assignment, charge_node, install_candidates


def test_age_normalization_preserves_source_stamps_and_missing_inputs():
    inputs={'pose':dict(source_time=9.,age_sec=0.,ttl_sec=2.),
            'map':dict(source_time=None,age_sec=None,ttl_sec=5.)}
    original=copy.deepcopy(inputs)
    bound=control.input_freshness_at(inputs,11.1)
    assert inputs==original and bound['pose']['source_time']==9.
    assert bound['pose']['ttl_sec']==2. and bound['pose']['age_sec']==pytest.approx(2.1)
    assert bound['map']==inputs['map']


@pytest.mark.parametrize('expired_at',[12.01,9.99])
def test_expiry_or_clock_reset_during_candidate_generation_dispatches_nothing(monkeypatch,expired_at):
    node,requests,decisions,sent=charge_node()
    node.battery_states['tb1']['energy']=70.
    original_stamps=dict(node.robot_odom_received_at)
    def candidates(*args,**kwargs):
        node.now=lambda:expired_at
        a=assignment()
        return [(a.utility,'tb1',a.viewpoint.group_id,a)],dict(frontier_groups=1,groups_with_viewpoints=1)
    monkeypatch.setattr(control,'robot_candidate_assignments',candidates)
    control.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests and not node.rally_charge_requested
    assert all(state=='idle' for state in node.robot_states.values())
    assert node.robot_odom_received_at==original_stamps
    assert len(decisions)==1 and decisions[0]['event']=='coordinator_planning_lease_expired'
    assert decisions[0]['source_deadline_sec']==12.


def test_expiry_during_route_admission_does_not_leave_a_live_owner(monkeypatch):
    node,requests,decisions,sent=charge_node()
    node.battery_states['tb1']['energy']=70.
    install_candidates(monkeypatch,{'tb1':[assignment()]})
    original=control.plan_rally_leg
    def delayed(*args,**kwargs):
        result=original(*args,**kwargs)
        node.now=lambda:12.01
        return result
    monkeypatch.setattr(control,'plan_rally_leg',delayed)
    control.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests and not node.rally_charge_requested
    assert all(state=='idle' for state in node.robot_states.values())
    assert decisions[-1]['event']=='coordinator_planning_lease_expired'


def test_charge_budget_that_outlives_input_lease_creates_no_request(monkeypatch):
    node,requests,decisions,_=charge_node()
    time=[10.]
    node.now=lambda:time[0]
    node.fresh_robot_inputs=lambda:time[0]<=12.
    def delayed(*args,**kwargs):
        time[0]=12.01
        return (10.,30.,(2.,3.))
    monkeypatch.setattr(control.HeadquartersControl,'exploration_charge_budget',delayed)
    assert not control.HeadquartersControl.request_exploration_charge(node,[('tb1',assignment())])
    assert not requests and not decisions and not node.rally_charge_requested
    assert not node.exploration_resume_intents


def test_shutdown_rejects_new_input_admission_without_touching_ros():
    node=SimpleNamespace(shutdown_requested=True)
    assert not control.HeadquartersControl.fresh_robot_inputs(node)


def test_expired_remaining_lazy_candidate_revokes_earlier_provisional_plan(monkeypatch):
    node, requests, decisions, sent = charge_node()
    install_candidates(monkeypatch, {'tb1': [assignment(4., 3., utility=100.)],
                                     'tb2': [assignment(6., 3., utility=1.)]})
    calls = []
    def budget(*args):
        calls.append(args)
        if len(calls) == 2:  # First candidate's body-masked route price.
            node.now = lambda: 12.01
        return 1.
    node.exploration_battery_factor = budget
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(calls) == 2
    assert not sent and not requests and not node.rally_charge_requested
    assert all(state == 'idle' for state in node.robot_states.values())
    assert decisions[-1]['event'] == 'coordinator_planning_lease_expired'
    assert decisions[-1]['stage'] == 'candidate_generation'
