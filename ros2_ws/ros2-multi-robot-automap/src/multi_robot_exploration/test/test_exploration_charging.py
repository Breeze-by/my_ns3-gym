"""Unfunded frontier admission must recover through leased serial charging."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control


def assignment(x=6., y=3., distance=4., gain=1000, utility=100.):
    return control.Assignment(control.Viewpoint(1, 30, 60, 30, 61, gain, 10),
                              x, y, distance, utility, x, y)


def charge_node():
    positions={'tb1':(2.,3.), 'tb2':(8.,3.)}
    states={name:dict(energy=10.,capacity=100.,charge_target_fraction=.8,
        charge_x=2.,charge_y=3.,move_cost_per_m=1.,idle_cost_per_sec=.02,
        return_path_factor=2.,nominal_speed_mps=.18,return_safety_margin=8.) for name in positions}
    requests=[];decisions=[];sent=[];logs=[]
    node=SimpleNamespace(enable_battery=True,task_state='EXPLORE',now=lambda:10.,
        fresh_robot_inputs=lambda:True,battery_modes={name:'ACTIVE' for name in positions},
        battery_states=states,robot_positions=positions,
        robot_states={name:'idle' for name in positions},
        rally_charge_requested={},exploration_charge_budgets={},exploration_resume_intents={},
        charge_request_publishers={name:SimpleNamespace(publish=lambda msg,n=name:requests.append((n,json.loads(msg.data)))) for name in positions},
        consumed_publisher=SimpleNamespace(publish=lambda msg:decisions.append(json.loads(msg.data))),
        input_freshness_details=lambda:{'tb1/pose_state':dict(source_time=node.robot_odom_received_at['tb1'],
            age_sec=node.now()-node.robot_odom_received_at['tb1'],ttl_sec=2.),
            'headquarters/target_detection':dict(source_time=0.,age_sec=node.now(),ttl_sec=5.)},
        get_logger=lambda:SimpleNamespace(warn=logs.append,info=logs.append),
        map_data=np.zeros((60,100),dtype=int),resolution=.1,origin=(0.,0.),
        map_received_at=10.,robot_odom_received_at=dict.fromkeys(positions,10.),
        robot_maps={name:{} for name in positions},
        input_robot_names=lambda:list(positions),participating_robots=lambda:list(positions),
        active_exclusions=lambda:[],goal_routes={},goal_targets={},goal_initial_gain={},
        target_information_gain=lambda *args:1000,send_goal=lambda name,goal:sent.append((name,goal)),
        battery_state_received_at={name:10. for name in positions},
        last_no_assignment_log=-float('inf'))
    node.frontier_cache=control.prepare_frontier_data(node.map_data,node.resolution)
    node.exploration_battery_factor=lambda *args:control.HeadquartersControl.exploration_battery_factor(node,*args)
    return node,requests,decisions,sent


def install_candidates(monkeypatch, goals):
    def candidates(grid,resolution,origin,name,*args,**kwargs):
        return [(a.utility,name,a.viewpoint.group_id,a) for a in goals.get(name,[])],dict(frontier_groups=1,groups_with_viewpoints=1)
    monkeypatch.setattr(control,'robot_candidate_assignments',candidates)


def test_valid_unfunded_frontier_requests_charge_and_remembers_intent(monkeypatch):
    node,requests,decisions,sent=charge_node()
    install_candidates(monkeypatch,{'tb1':[assignment()], 'tb2':[assignment(4.,3.)]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert not sent and len(requests)==len(decisions)==1
    name,event=requests[0]
    assert name=='tb1' and event['task_phase']=='EXPLORE' and event['reason']=='exploration_energy_budget'
    assert 10.<event['required_energy']<80.
    assert node.exploration_resume_intents['tb1']==(6.,3.,1000)
    assert set(node.rally_charge_requested)=={'tb1'}
    assert 'headquarters/target_detection' not in decisions[0]['inputs']


def test_funded_lower_utility_frontier_runs_before_any_charge(monkeypatch):
    node,requests,_,sent=charge_node()
    cheap=assignment(2.5,3.,distance=.5,utility=1.)
    install_candidates(monkeypatch,{'tb1':[assignment(),cheap]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and len(sent)==1 and sent[0][1].x==2.5


@pytest.mark.parametrize('reason',['stale','blocked','returning','charging','live','capacity','malformed'])
def test_no_request_from_expired_unreachable_live_or_unfundable_context(monkeypatch,reason):
    node,requests,_,sent=charge_node()
    install_candidates(monkeypatch,{'tb1':[assignment()]})
    if reason=='stale':node.fresh_robot_inputs=lambda:False
    if reason=='blocked':node.map_data[:,40:42]=100
    if reason in ('returning','charging'):node.battery_modes['tb2']=reason.upper()
    if reason=='live':node.robot_states['tb2']='active'
    if reason=='capacity':node.battery_states['tb1']['capacity']=12.
    if reason=='malformed':node.battery_states['tb1']['charge_target_fraction']=float('nan')
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and not sent


def test_lost_request_retries_only_same_idle_owner_with_current_input_leases():
    node,requests,_,_=charge_node()
    goals=[('tb1',assignment()),('tb2',assignment(4.,3.))]
    assert control.HeadquartersControl.request_exploration_charge(node,goals)
    node.now=lambda:11.
    assert control.HeadquartersControl.request_exploration_charge(node,goals)
    assert len(requests)==1
    node.now=lambda:12.
    assert control.HeadquartersControl.request_exploration_charge(node,goals)
    assert [name for name,event in requests]==['tb1','tb1']
    assert requests[-1][1]['stamp_sec']==12.
    node.battery_modes['tb1']='RETURNING'
    assert not control.HeadquartersControl.request_exploration_charge(node,goals)
    assert len(requests)==2


@pytest.mark.parametrize('fresh_confirmation',[False,True])
def test_expired_pending_request_releases_only_after_new_active_battery_state(monkeypatch,fresh_confirmation):
    node,requests,_,sent=charge_node()
    expiry=10.+control.CHARGE_REQUEST_TTL_SEC
    node.now=lambda:expiry+1.
    node.map_received_at=expiry
    node.robot_odom_received_at=dict.fromkeys(node.battery_modes,expiry)
    node.rally_charge_requested['tb1']=10.
    node.exploration_charge_budgets['tb1']=30.
    node.battery_states['tb1']['energy']=40.
    node.battery_state_received_at['tb1']=expiry if fresh_confirmation else expiry-.1
    from std_msgs.msg import String
    control.HeadquartersControl.battery_state_callback(node,String(data=json.dumps({
        **node.battery_states['tb1'],'mode':'ACTIVE',
        'stamp_sec':node.battery_state_received_at['tb1']})), 'tb1')
    install_candidates(monkeypatch,{'tb1':[assignment()]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert bool(sent)==fresh_confirmation and not requests
    assert ('tb1' in node.rally_charge_requested) is not fresh_confirmation


def test_unfundable_charge_request_never_loops_after_full_charge():
    node,requests,_,_=charge_node()
    node.battery_states['tb1']['energy']=80.
    assert not control.HeadquartersControl.request_exploration_charge(node,[('tb1',assignment(distance=100.))])
    assert not requests and not node.rally_charge_requested


def test_delivered_charge_resume_releases_owner_and_retains_search_preference():
    node,requests,_,_=charge_node()
    assert control.HeadquartersControl.request_exploration_charge(node,[('tb1',assignment())])
    node.battery_modes['tb1']='CHARGING'
    node.rally_precharge_staging={}
    from std_msgs.msg import String
    control.HeadquartersControl.battery_state_callback(node,String(data=json.dumps({
        **node.battery_states['tb1'],'mode':'ACTIVE','energy':80.,'stamp_sec':30.})), 'tb1')
    assert not node.rally_charge_requested and not node.exploration_charge_budgets
    assert node.exploration_resume_intents['tb1']==(6.,3.,1000)


def test_terminal_mission_cannot_request_an_exploration_charge():
    node,requests,_,_=charge_node()
    node.task_state='COMPLETE'
    assert not control.HeadquartersControl.request_exploration_charge(node,[('tb1',assignment())])
    assert not requests


def test_pending_exploration_charge_can_expire_after_target_detection():
    node,requests,_,_=charge_node()
    assert control.HeadquartersControl.request_exploration_charge(node,[('tb1',assignment())])
    node.task_state='RALLY'
    node.now=lambda:21.
    from std_msgs.msg import String
    control.HeadquartersControl.battery_state_callback(node,String(data=json.dumps({
        **node.battery_states['tb1'],'mode':'ACTIVE','stamp_sec':21.})), 'tb1')
    assert not node.rally_charge_requested and not node.exploration_charge_budgets


@pytest.mark.parametrize('live_peer',[False,True])
def test_funded_peer_cannot_starve_needed_idle_charge_admission(monkeypatch,live_peer):
    node,requests,_,sent=charge_node()
    node.battery_states['tb2']['energy']=80.
    node.robot_states['tb2']='active' if live_peer else 'idle'
    install_candidates(monkeypatch,{'tb1':[assignment()],
                                   'tb2':[assignment(8.,4.,distance=1.,utility=1000.)]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert not sent
    assert len(requests)==(0 if live_peer else 1)
    if live_peer:
        node.robot_states['tb2']='idle'  # The original accepted action drains.
        control.HeadquartersControl.assign_idle_robots(node)
        assert len(requests)==1 and not sent
    assert requests[0][0]=='tb1'


def test_unfundable_peer_cannot_block_an_independent_funded_admission(monkeypatch):
    node,requests,_,sent=charge_node()
    node.battery_states['tb1']['capacity']=12.
    node.battery_states['tb2']['energy']=80.
    install_candidates(monkeypatch,{'tb1':[assignment()],
                                   'tb2':[assignment(8.,4.,distance=1.,utility=1000.)]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests and len(sent)==1 and sent[0][0]=='tb2'


def test_lower_unfunded_candidates_do_not_repeat_full_route_planning(monkeypatch):
    from unittest.mock import patch
    node,requests,_,sent=charge_node()
    goals=[assignment(6.+i*.05,3.,utility=100.-i) for i in range(20)]
    install_candidates(monkeypatch,{'tb1':goals})
    with patch.object(control,'plan_rally_leg',wraps=control.plan_rally_leg) as planning:
        control.HeadquartersControl.assign_idle_robots(node)
    assert len(requests)==1 and not sent
    assert node.exploration_resume_intents['tb1'][0]==6.
    assert planning.call_count<=2


def opportunity_node():
    node,requests,decisions,sent=charge_node()
    node.robot_positions['tb1']=(3.,3.)
    node.battery_states['tb1'].update(energy=18.,charge_radius_m=.8)
    node.successful_exploration_legs={'tb1':1}
    return node,requests,decisions,sent


def test_funded_frontier_passing_home_can_request_opportunity_charge(monkeypatch):
    node,requests,decisions,sent=opportunity_node()
    goal=assignment(3.5,3.,distance=.5)
    install_candidates(monkeypatch,{'tb1':[goal]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert not sent and len(requests)==len(decisions)==1
    assert requests[0][1]['required_energy']==20.
    assert node.exploration_resume_intents['tb1']==(3.5,3.,1000)


@pytest.mark.parametrize('reason',['spawn','no_success','full','normal_energy','distant','blocked_home','invalid_radius','live_peer','stale'])
def test_opportunity_charge_requires_real_work_and_current_safe_home_route(monkeypatch,reason):
    node,requests,_,sent=opportunity_node()
    if reason=='spawn':node.robot_positions['tb1']=(2.,3.)
    if reason=='no_success':node.successful_exploration_legs.clear()
    if reason=='full':node.battery_states['tb1']['energy']=80.
    if reason=='normal_energy':node.battery_states['tb1']['energy']=38.
    if reason=='distant':node.robot_positions['tb1']=(4.,3.)
    if reason=='blocked_home':node.map_data[:,23]=100
    if reason=='invalid_radius':node.battery_states['tb1']['charge_radius_m']=float('nan')
    if reason=='live_peer':node.robot_states['tb2']='active'
    if reason=='stale':node.fresh_robot_inputs=lambda:False
    install_candidates(monkeypatch,{'tb1':[assignment(3.5,3.,distance=.5)]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert not requests
    assert bool(sent)==(reason not in ('live_peer','stale','blocked_home','invalid_radius'))


def test_idle_robot_refines_reachable_candidates_while_peer_action_remains_live(monkeypatch):
    node,requests,_,sent=charge_node()
    node.battery_states['tb1']['energy']=80.
    node.robot_states['tb2']='active'
    calls=[]
    goal=assignment(3.,3.,distance=1.)
    def candidates(grid,resolution,origin,name,*args,**kwargs):
        refined='blocked_positions' in kwargs
        calls.append(refined)
        return ([(goal.utility,name,goal.viewpoint.group_id,goal)] if refined else []),dict(frontier_groups=1,groups_with_viewpoints=1)
    monkeypatch.setattr(control,'robot_candidate_assignments',candidates)
    control.HeadquartersControl.assign_idle_robots(node)
    assert calls==[False,True] and not requests
    assert len(sent)==1 and sent[0][0]=='tb1'


@pytest.mark.parametrize('contact_x,expected',[(2.5,True),(2.7,False)])
def test_visible_home_leg_only_needs_to_reach_the_safe_charging_contact_zone(monkeypatch,contact_x,expected):
    node,requests,_,sent=opportunity_node()
    original=control.plan_rally_leg
    def plan(pose,*args,**kwargs):
        if (pose.x,pose.y)==(2.,3.):
            return control.RallyPose(contact_x,3.,0.),((3.,3.),(contact_x,3.))
        return original(pose,*args,**kwargs)
    monkeypatch.setattr(control,'plan_rally_leg',plan)
    install_candidates(monkeypatch,{'tb1':[assignment(3.5,3.,distance=.5)]})
    control.HeadquartersControl.assign_idle_robots(node)
    assert bool(requests)==expected and bool(sent) is not expected
