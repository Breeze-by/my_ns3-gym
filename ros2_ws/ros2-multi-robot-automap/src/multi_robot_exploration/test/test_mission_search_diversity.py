import copy
import math

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_exploration_charging import charge_node,assignment,install_candidates
from test_relative_frontier_travel import travel_event


def visits(count=20):
    return [dict(source='ap_delivered_pose_history',robot='tb1',position=[4.5+.5*i,3.],
        observed_at_sec=9.,pose_source_time=8.5,frame_source_time=8.7) for i in range(count)]


@pytest.mark.parametrize('count',[0,1,4,20,100])
def test_local_preference_counts_only_nearby_visits_and_never_vetoes_travel(count):
    node,_,_,_=charge_node()
    args=(node.map_data,node.resolution,node.origin)
    e=c.mission_search_diversity((7.,3.),node.battery_states,visits(count),*args)
    expected=list(range(1,min(count,10)))
    assert e['visible_visit_indices']==expected
    assert e['factor']==pytest.approx(max(.25,1./math.sqrt(1.+len(expected))))
    assert c.mission_search_diversity((2.1,3.),node.battery_states,visits(count),*args)['factor']==1.
    assert c.mission_search_diversity((2.,5.5),node.battery_states,visits(count),*args)['factor']==1.


def test_charger_metadata_defines_center_without_hidden_target_or_current_queue():
    states={'tb1':dict(charge_x=-2.,charge_y=0.),'tb2':dict(charge_x=2.,charge_y=0.)}
    args=(np.zeros((30,30),dtype=int),.5,(-5.,-5.))
    result=c.mission_search_diversity((-4.,0.),states,[],*args)
    assert result['center']==[0.,0.] and not result['near_home_neutral'] and result['factor']==1.
    assert c.mission_search_diversity((1.,1.),{},[],*args) is None


@pytest.mark.parametrize('bad',[None,{},dict(charge_x=float('nan'),charge_y=0.),dict(charge_x='invalid',charge_y=0.)])
def test_missing_or_invalid_historical_home_metadata_keeps_finite_preference(bad):
    states={'tb1':dict(charge_x=0.,charge_y=0.),'tb2':bad}
    args=(np.zeros((30,30),dtype=int),.5,(-5.,-5.))
    assert c.mission_search_diversity((4.,0.),states,[],*args)['center']==[0.,0.]
    assert c.mission_search_diversity((4.,0.),{'tb2':bad},[],*args) is None


@pytest.mark.parametrize('obstacle',[100,-1])
def test_same_direction_other_room_is_not_penalized_across_wall_or_unknown(obstacle):
    grid=np.zeros((80,80),dtype=int);grid[:,35]=obstacle
    history=visits(1);history[0]['position']=[3.05,4.05]
    states={'tb1':dict(charge_x=0.,charge_y=4.)}
    separated=c.mission_search_diversity((4.05,4.05),states,history,grid,.1,(0.,0.))
    assert not separated['visible_visit_indices'] and separated['factor']==1.
    grid[40,35]=0
    visible=c.mission_search_diversity((4.05,4.05),states,history,grid,.1,(0.,0.))
    assert visible['visible_visit_indices']==[0] and visible['factor']==pytest.approx(1./math.sqrt(2))


def test_dense_local_history_has_positive_floor_and_outside_map_history_is_skipped():
    grid=np.zeros((80,80),dtype=int)
    history=visits(20)
    for i,visit in enumerate(history):visit['position']=[3.05+.5*(i%5),3.05+.5*(i//5)]
    states={'tb1':dict(charge_x=0.,charge_y=0.)}
    result=c.mission_search_diversity((4.05,4.05),states,history,grid,.1,(0.,0.))
    assert len(result['visible_visit_indices'])==20 and result['factor']==.25
    history.append(dict(history[0],position=[-1.,4.05]))
    assert c.mission_search_diversity((.05,4.05),states,history,grid,.1,(0.,0.))['visible_visit_indices']==[]


@pytest.mark.parametrize('mission',[False,True])
def test_complete_object_mission_prefers_less_travelled_direction_with_original_admission(monkeypatch,mission):
    node,requests,_,sent=charge_node();node.enable_rally=mission
    node.robot_positions['tb2']=(1.,1.);node.robot_states['tb2']='active'
    for state in node.battery_states.values():state['energy']=80.
    node.initial_search_visits={i:v for i,v in enumerate(visits())}
    east=assignment(7.,3.,distance=5.,utility=100.)
    north=assignment(2.,5.5,distance=2.5,utility=60.)
    install_candidates(monkeypatch,{'tb1':[east,north]})
    c.HeadquartersControl.assign_idle_robots(node)
    assert not requests and len(sent)==1
    assert (sent[0][1].x,sent[0][1].y)==((north.x,north.y) if mission else (east.x,east.y))
    assert node.exploration_travel_choices['tb1']['required_energy']<80.


@pytest.mark.parametrize('bad',[None,'factor','count','radius','neutral','center','homes','source','stale','duplicate','missing'])
def test_spatial_reader_rebuilds_map_visibility_model_anchor_history_and_score(bad):
    from check_p2c_gate import exploration_travel_audit
    e=travel_event();f=e['travel_preference']
    import base64,zlib
    s=e['planning_map'];grid=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
    f['mission_spatial_diversity']=c.mission_search_diversity(f['target'],e['battery_states'],visits(),grid,s['resolution'],s['origin'])
    f['adjusted_utility']*=f['mission_spatial_diversity']['factor'];d=f['mission_spatial_diversity']
    if bad=='factor':d['factor']=1.
    if bad=='count':d['visible_visit_indices'].append(999)
    if bad=='radius':d['radius_m']+=1.
    if bad=='neutral':d['near_home_neutral']=not d['near_home_neutral']
    if bad=='center':d['center'][0]+=1.
    if bad=='homes':d['homes']['tb1'][0]+=1.
    if bad=='source':d['visits'][0]['source']='ground_truth'
    if bad=='stale':d['visits'][0]['frame_source_time']=6.
    if bad=='duplicate':d['visits'].append(copy.deepcopy(d['visits'][0]))
    if bad=='missing':f.pop('mission_spatial_diversity')
    if bad is None:
        assert exploration_travel_audit([e],True,require_diversity=True)['spatial_diversity_witnesses']==1
    else:
        with pytest.raises((AssertionError,KeyError)):
            exploration_travel_audit([e],True,require_diversity=True)
