"""A fused/local disagreement is inspected without granting its blocked route."""
import copy
import gzip
import json
import math
from pathlib import Path

import numpy as np
import pytest
from multi_robot_exploration import control as c
from p2c_outbound_routes import decode
from p2c_rally_connection import audit_geometry, audit_priority
from test_rally_proposal_handoff import node_fixture, records


def original(index=0):
    path=Path(__file__).with_name('fixtures')/'p2c_v65_reinspection_inputs.json.gz'
    with gzip.open(path,'rt') as stream:e=json.load(stream)['events'][index]
    saved=e['planning_map'];local=e['return_maps']['tb2']
    return e,decode(saved),dict(data=decode(local),resolution=local['resolution'],origin=local['origin'])


@pytest.mark.parametrize('index',[0,-1])
def test_original_blocked_approach_is_inspected_from_a_fully_qualified_known_leg(index):
    e,raw,local=original(index);saved=e['planning_map'];res=saved['resolution'];origin=saved['origin']
    before=raw.tobytes(),local['data'].tobytes()
    bodies=[e['robot_positions']['tb1']]
    pose,witness=c.rally_connection_reinspection(raw,res,origin,e['robot_positions']['tb2'],e['target'],local,bodies)
    # The new endpoint faces the central passage rather than the old right-hand frontiers.
    assert -.2<pose.x<0. and .2<pose.y<.35
    assert witness['fused_remaining_distance_m']<witness['current_fused_remaining_distance_m']-.4
    combined=c.constrained_return_grid(raw,res,origin,local)
    assert c.traversable_grid(combined,res,.45)[c.world_to_grid(pose.x,pose.y,res,*origin)]
    plan=c.plan_rally_leg(pose,raw,res,origin,e['robot_positions']['tb2'],5.,blocked_positions=bodies,local_map=local)
    assert plan[0] is not None and len(plan[1])>2
    assert c.route_respects_known_obstacles(local['data'],local['resolution'],local['origin'],plan[1])
    assert before==(raw.tobytes(),local['data'].tobytes())
    poses=c.rally_pose_candidates(raw,res,origin,e['target'],False,True)
    safe=c.traversable_grid(combined,res,.35)
    start,_=c.navigation_start_route(combined,safe,c.world_to_grid(*e['robot_positions']['tb2'],res,*origin),math.ceil(.6/res))
    field=c.path_distance_grid(safe,start)
    assert not any(np.isfinite(field[c.world_to_grid(p.x,p.y,res,*origin)]) for p in poses)


def synthetic(ghost=100):
    raw=np.zeros((120,120),dtype=np.int16);raw[:,50]=100;raw[55:64,50]=0;raw[110:,:]=-1
    local=raw.copy();local[59:62,53]=ghost
    return raw,dict(data=local,resolution=.1,origin=(0.,0.))


@pytest.mark.parametrize('value',[1,49,50,100])
def test_every_positive_local_cell_remains_an_obstacle(value):
    raw,local=synthetic(value)
    result=c.rally_connection_reinspection(raw,.1,(0.,0.),(9.,4.7),(2.,7.),local)
    assert result is not None
    pose,_=result;combined=c.constrained_return_grid(raw,.1,(0.,0.),local)
    assert np.all(combined[59:62,53]==100)
    assert pose.x>5.3 and c.traversable_grid(combined,.1,.45)[c.world_to_grid(pose.x,pose.y,.1,0.,0.)]


@pytest.mark.parametrize('condition',['missing_local','connected','fused_disconnected','unknown_start','occupied_start','no_target_poses'])
def test_no_reinspection_without_a_known_fused_connection_and_missing_conservative_connection(condition):
    raw,local=synthetic()
    if condition=='missing_local':local=None
    if condition=='connected':local['data']=raw.copy()
    if condition=='fused_disconnected':raw[:,50]=100
    if condition=='unknown_start':raw[47,90]=-1
    if condition=='occupied_start':raw[47,90]=100
    if condition=='no_target_poses':raw[:,:50]=-1
    assert c.rally_connection_reinspection(raw,.1,(0.,0.),(9.,4.7),(2.,7.),local) is None


def proposal():
    node,clock,_,_=node_fixture();e,raw,local=original()
    node.map_data=node.source_map_data=raw;node.resolution=e['planning_map']['resolution'];node.origin=e['planning_map']['origin']
    node.target=e['target'];node.robot_positions=e['robot_positions'];node.target_observing_robot='tb1'
    node.robot_maps={name:dict(data=decode(row),resolution=row['resolution'],origin=row['origin']) for name,row in e['return_maps'].items()}
    clock[0]=e['computation_completed_at_sec'];node.map_received_at=e['planning_map']['source_time']
    node.robot_map_received_at={name:row['source_time'] for name,row in e['return_maps'].items()}
    node.input_freshness_details=lambda:e['inputs']
    assert c.HeadquartersControl.survey_rally_connection(node,node.robot_positions,'tb2',e['event_time'])
    event=records(node)[-1]
    assert event['candidates'][0][0]=='tb2' and event['reinspection_inputs']['tb2']['choice'] is not None
    return e,event


def test_original_raw_maps_and_soft_rank_are_independently_rebuilt():
    assignment,event=proposal()
    assert audit_priority(event,assignment)>2
    assert audit_geometry(event,True)==len(event['candidates'])


@pytest.mark.parametrize('change',['omit_contract','omit_input','missing_local','fake_source','changed_cell','changed_rank','changed_pose','erase_obstacle'])
def test_reader_rejects_unbound_or_weakened_reinspection(change):
    assignment,event=proposal();event=copy.deepcopy(event)
    row=event['reinspection_inputs']['tb2']
    if change=='omit_contract':del event['reinspection_inputs']
    if change=='omit_input':event['reinspection_inputs']={}
    if change=='missing_local':row['local_map']=None
    if change=='fake_source':row['local_map']['source_time']-=1.
    if change=='changed_cell':row['choice']['cell'][0]+=1
    if change=='changed_rank':row['choice']['fused_remaining_distance_m']-=.1
    if change=='changed_pose':event['candidates'][0][1]+=.1
    if change=='erase_obstacle':
        grid=decode(row['local_map']).copy();grid[grid>0]=0
        row['local_map']=c.grid_audit_evidence(grid,row['local_map']['resolution'],row['local_map']['origin'],'ap_delivered_robot_map',row['local_map']['source_time'],row['local_map']['version'])
    with pytest.raises(AssertionError):
        audit_geometry(event,True)
        audit_priority(event,assignment)


def test_body_at_the_preferred_endpoint_cannot_authorize_the_old_endpoint():
    raw,local=synthetic();position=(9.,4.7);target=(2.,7.)
    first,_=c.rally_connection_reinspection(raw,.1,(0.,0.),position,target,local)
    answer=c.rally_connection_reinspection(raw,.1,(0.,0.),position,target,local,[(first.x,first.y)])
    assert answer is None or math.dist((first.x,first.y),(answer[0].x,answer[0].y))>.6


def test_original_six_frames_keep_ordinary_route_and_source_authority():
    from p2c_rally_connection import rebuild_reinspection
    for i in range(6):
        e,raw,local=original(i);saved=e['planning_map'];bodies=[e['robot_positions']['tb1']]
        pose,witness=c.rally_connection_reinspection(raw,saved['resolution'],saved['origin'],e['robot_positions']['tb2'],e['target'],local,bodies)
        event=dict(planning_map=saved,inputs=e['inputs'],event_time=e['event_time'],robot_positions=e['robot_positions'],current_positions=e['current_positions'],target=e['target'])
        rebuilt,expected=rebuild_reinspection(event,'tb2',e['return_maps']['tb2'])
        assert witness==expected and np.allclose((pose.x,pose.y,pose.yaw),rebuilt[1:],rtol=0,atol=1e-8)
