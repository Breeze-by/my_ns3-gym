"""Target-area preferences never authorize unknown travel or unfunded returns."""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_rally_observation_recovery import observer_node
from check_p2c_gate import target_survey_audit


def survey_node():
    node,client=observer_node();events=[]
    grid=np.zeros((100,100),dtype='<i2');grid[60:,:50]=-1
    grid.setflags(write=False)
    node.map_data=node.source_map_data=grid
    node.target=(2.05,6.55);node.target_received_source_time=99.5
    node.task_state='FOUND';node.message_freshness_timeout_sec=5.
    node.map_self_return_cells={}
    node.robot_tf_received_at=dict.fromkeys(node.robot_positions,100.)
    node.robot_map_received_at=dict.fromkeys(node.robot_positions,100.)
    node.battery_state_received_at=dict.fromkeys(node.robot_positions,100.)
    node.robot_maps={name:dict(data=grid,resolution=.1,origin=(0.,0.)) for name in node.robot_positions}
    for state in node.battery_states.values():state.update(energy=80.,mode='ACTIVE',stamp_sec=100.)
    node.robot_nav_clients['tb2']=client
    node.participating_robots=lambda:list(node.robot_positions)
    node.input_robot_names=lambda:[name for name in node.robot_positions if node.battery_modes[name]=='ACTIVE']
    node.input_freshness_details=lambda:c.HeadquartersControl.input_freshness_details(node)
    node.consumed_publisher=SimpleNamespace(publish=lambda msg:events.append(json.loads(msg.data)))
    node.record_navigation_decision=lambda *args:c.HeadquartersControl.record_navigation_decision(node,*args)
    node.send_survey_goal=lambda *args:c.HeadquartersControl.send_survey_goal(node,*args)
    return node,client,events


def survey_event():
    node,_,events=survey_node()
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions)
    assert node.target_survey_choice is None
    return next(e for e in events if e.get('kind')=='target_information_survey')


def test_target_gain_prefers_near_observer_and_bounds_choices_without_editing_map():
    node,_,_=survey_node();before=node.map_data.copy()
    choices=c.target_survey_candidates(node.map_data,.1,(0.,0.),node.robot_positions,node.battery_modes,node.target)
    assert choices and choices[0]['robot']=='tb1'
    assert len(choices)<=4 and all(sum(r['robot']==name for r in choices)<=2 for name in node.robot_positions)
    assert choices==c.target_survey_candidates(node.map_data,.1,(0.,0.),node.robot_positions,node.battery_modes,node.target)
    assert np.array_equal(node.map_data,before)
    safe=c.traversable_grid(node.map_data,.1,c.ROBOT_CLEARANCE_M)
    for row in choices:
        cell=c.world_to_grid(*row['desired_position'],.1,0.,0.)
        assert safe[cell] and node.map_data[cell]==0
        assert row['target_gain']>0 and row['utility']==pytest.approx(row['target_gain']/(1+row['path_distance_m']))
        assert type(row['group']) is int
    json.dumps(choices)


def test_local_known_view_can_map_target_when_straight_target_descent_is_exhausted():
    node,_,events=survey_node();node.robot_positions['tb1']=(2.05,5.55)
    assert c.rally_survey_pose(node.map_data,.1,(0.,0.),node.robot_positions['tb1'],node.target) is None
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions)
    event=next(e for e in events if e.get('kind')=='target_information_survey')
    assert event['robot']=='tb1' and event['target_survey_selection']['choice']['target_gain']>0
    assert target_survey_audit([event],True,3.,.35,curved_surveys=True)['target_information_survey_witnesses']==1
    assert np.all(node.map_data[60:,:50]==-1)


@pytest.mark.parametrize('condition',['no_unknown','far_target','failed','invalid_radius','invalid_target'])
def test_uninformative_and_inactive_cases_have_no_survey(condition):
    node,_,_=survey_node();target=node.target;radius=3.
    if condition=='no_unknown':node.map_data=np.zeros((100,100),dtype=int)
    if condition=='far_target':target=(100.,100.)
    if condition=='failed':node.battery_modes=dict.fromkeys(node.robot_positions,'FAILED')
    if condition=='invalid_radius':radius=float('nan')
    if condition=='invalid_target':target=(float('inf'),2.)
    assert not c.target_survey_candidates(node.map_data,.1,(0.,0.),node.robot_positions,node.battery_modes,target,radius)


@pytest.mark.parametrize('condition',['safe','low_energy','stale_map','stale_target','live_survey'])
def test_actual_dispatch_preserves_energy_freshness_and_live_handle_guards(condition):
    node,client,events=survey_node()
    if condition=='low_energy':
        for state in node.battery_states.values():state['energy']=1.
    if condition=='stale_map':node.fresh_robot_inputs=lambda:False
    if condition=='stale_target':node.fresh_target=lambda:False
    if condition=='live_survey':node.survey_goal_handle=object()
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions)==(condition=='safe')
    assert client.send_goal_async.called==(condition=='safe')
    assert node.target_survey_choice is None
    if condition=='safe':
        event=next(e for e in events if e.get('kind')=='target_information_survey')
        assert target_survey_audit([event],True,3.,curved_surveys=True)['target_information_survey_witnesses']==1
        assert event['target_survey_selection']['required_energy']<80.


@pytest.mark.parametrize('corruption',[None,'gain','cost','utility','endpoint','prefix','energy','body',
    'future_tf','stale_map','target_lease','target_age','radius','tolerance','missing','unfunded','undeclared'])
def test_independent_reader_rejects_forged_gain_path_budget_and_leases(corruption):
    event=copy.deepcopy(survey_event());s=event['target_survey_selection'];choice=s['choice']
    if corruption=='gain':choice['target_gain']+=1
    if corruption=='cost':choice['path_distance_m']+=1.
    if corruption=='utility':choice['utility']+=1.
    if corruption=='endpoint':event['requested_position'][0]+=.5
    if corruption=='prefix':s['admitted_route'][0][0]+=.5
    if corruption=='energy':s['required_energy']-=1.
    if corruption=='body':event['robot_positions']['tb2']=choice['desired_position']
    if corruption=='future_tf':event['inputs']['tb1/frame_state'].update(source_time=101.,age_sec=-1.)
    if corruption=='stale_map':event['planning_map']['source_time']=90.
    if corruption=='target_lease':event['inputs']['headquarters/target_detection'].update(source_time=101.,age_sec=-1.)
    if corruption=='target_age':event['inputs']['headquarters/target_detection']['age_sec']=3.
    if corruption=='radius':s['radius_m']=4.
    if corruption=='tolerance':s['position_tolerance_m']=.1
    if corruption=='missing':del event['target_survey_selection']
    if corruption=='unfunded':event['battery_states'][event['robot']]['energy']=1.
    if corruption is None:
        assert target_survey_audit([event],True,3.,.35,curved_surveys=True)['target_information_survey_witnesses']==1
    else:
        with pytest.raises((AssertionError,KeyError)):
            target_survey_audit([event],corruption!='undeclared',3.,.35,curved_surveys=True)


def test_curved_survey_requires_an_explicit_reader_declaration():
    event=survey_event()
    assert event['target_survey_selection']['visible_only'] is False
    with pytest.raises(AssertionError,match='undeclared survey path policy'):
        target_survey_audit([event],True,3.,.35)


def test_curve_survey_reaches_known_viewpoint_beyond_visible_prefix():
    node,client,events=survey_node()
    grid=np.full((100,100),100,dtype='<i2')
    grid[15:25,5:75]=0
    grid[15:70,55:75]=0
    grid[70:85,55:75]=-1
    node.map_data=node.source_map_data=grid
    node.target=(6.05,7.05)
    node.robot_positions={'tb1':(5.55,2.05),'tb2':(1.05,2.05)}
    for name,position in node.robot_positions.items():
        node.battery_states[name].update(charge_x=position[0],charge_y=position[1])
    node.robot_maps={n:dict(data=grid,resolution=.1,origin=(0.,0.)) for n in node.robot_positions}
    pose=c.RallyPose(6.05,4.05,0.)
    blocked=[node.robot_positions['tb2']]
    visible=c.plan_rally_leg(pose,grid,.1,(0.,0.),node.robot_positions['tb1'],
        blocked_positions=blocked,visible_only=True,local_map=node.robot_maps['tb1'])
    curve=c.plan_rally_leg(pose,grid,.1,(0.,0.),node.robot_positions['tb1'],
        blocked_positions=blocked,local_map=node.robot_maps['tb1'])
    assert curve[0] is not None
    assert visible[0] is not None
    assert c.math.dist(node.robot_positions['tb1'],(curve[0].x,curve[0].y))>1.+c.math.dist(
        node.robot_positions['tb1'],(visible[0].x,visible[0].y))
    assert c.HeadquartersControl.send_survey_goal(node,'tb1',pose)
    assert client.send_goal_async.called
    decision=next(e for e in events if e.get('event')=='coordinator_navigation_decision')
    assert np.allclose(decision['requested_position'],(curve[0].x,curve[0].y))
