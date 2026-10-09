"""Reject unsupported geometry, renewed heartbeat and altered incoming yaw."""
import json
import math

import numpy as np
import pytest

from multi_robot_exploration.control import grid_audit_evidence
from p2c_navigation_dispatch import navigation_dispatch_audit
from p2c_rally_transit_heading import audit_transit_heading, transit_heading_audit


def event():
    inputs={
        'headquarters/target_detection':dict(source_time=7.,ttl_sec=60.,age_sec=3.),
        'headquarters/fused_map_snapshot':dict(source_time=10.,ttl_sec=5.,age_sec=0.),
        'tb2/pose_state':dict(source_time=10.,ttl_sec=2.,age_sec=0.),
        'tb2/frame_state':dict(source_time=10.,ttl_sec=2.,age_sec=0.)}
    return dict(event='coordinator_navigation_decision',event_time=10.,robot='tb1',kind='rally',task_phase='RALLY',
        requested_position=[2.05,1.05],requested_yaw=0.,inputs=inputs,
        dispatch_lease_deadline_sec=12.,dispatch_goal_source_time_sec=10.,
        rally_transit_observer=dict(observer='tb2',evaluated_at_sec=10.,target=[2.05,3.05],
            confirmation=dict(robot='tb2',source_time=7.,target=[2.05,3.05],view_distance_m=3.,view_fov_rad=math.pi/2),
            observer_source_time=7.,heartbeat_sec=5.,position=[3.05,3.05],yaw=math.pi,velocity=[0.,0.],
            final_pose=[3.05,3.05,math.pi],route=[[1.05,1.05],[2.05,1.05]],incoming_yaw=0.,
            participant_final_pose=[1.05,3.05,.5],position_tolerance_m=.35,
            linear_tolerance_mps=.05,angular_tolerance_radps=.1,view_distance_m=3.,view_fov_rad=math.pi/2,
            map=grid_audit_evidence(np.zeros((60,60),dtype=int),.1,(0.,0.),'ap_delivered_planning_map',10.,10.)))


def test_supported_geometry_and_additional_original_heartbeat(tmp_path):
    e=event(); audit_transit_heading(e)
    p=tmp_path/'ledger.jsonl'; p.write_text(json.dumps(e)+'\n')
    assert navigation_dispatch_audit(p,True)['decisions']==1


def test_quaternion_round_trip_keeps_the_same_noncardinal_incoming_angle():
    e=event();s=e['rally_transit_observer'];angle=math.atan2(.5,1.)
    e['requested_position']=[2.05,1.55];s['route'][-1]=e['requested_position']
    s['incoming_yaw']=angle
    e['requested_yaw']=2*math.atan2(math.sin(angle/2),math.cos(angle/2))
    audit_transit_heading(e)


@pytest.mark.parametrize('corruption', ['same_robot','stale_heartbeat','renewed_heartbeat','heartbeat_limit',
    'translated','turning','yaw','future_pose','map_epoch','final','goal_yaw','route_yaw','camera_range','camera_fov'])
def test_unsupported_transit_witness_is_rejected(corruption):
    e=event(); s=e['rally_transit_observer']
    if corruption=='same_robot':s['observer']='tb1'
    if corruption=='stale_heartbeat':s['observer_source_time']=4.;s['confirmation']['source_time']=4.;e['inputs']['headquarters/target_detection']['source_time']=4.
    if corruption=='renewed_heartbeat':s['observer_source_time']=10.
    if corruption=='heartbeat_limit':s['heartbeat_sec']=60.
    if corruption=='translated':s['position']=[3.5,3.05]
    if corruption=='turning':s['velocity'][1]=.11
    if corruption=='yaw':s['yaw']=0.
    if corruption=='future_pose':e['inputs']['tb2/pose_state']['source_time']=11.
    if corruption=='map_epoch':s['map']['source_time']=11.
    if corruption=='final':s['participant_final_pose'][:2]=e['requested_position']
    if corruption=='goal_yaw':e['requested_yaw']=.3
    if corruption=='route_yaw':s['route'][0]=[2.05,.05]
    if corruption=='camera_range':s['view_distance_m']=1.2
    if corruption=='camera_fov':s['view_fov_rad']=0.
    with pytest.raises(AssertionError):audit_transit_heading(e)


def test_heartbeat_expiry_after_preparation_rejects_even_with_current_pose(tmp_path):
    e=event();e['event_time']=e['dispatch_goal_source_time_sec']=12.01
    for key,row in e['inputs'].items():
        if key!='headquarters/target_detection':row['source_time']=12.;row['age_sec']=.01
    e['inputs']['headquarters/target_detection']['age_sec']=5.01
    p=tmp_path/'ledger.jsonl';p.write_text(json.dumps(e)+'\n')
    with pytest.raises(AssertionError):navigation_dispatch_audit(p,True)


def test_supported_peer_confirmation_requires_the_original_consumed_receipt(tmp_path):
    e=event();p=tmp_path/'ledger.jsonl'
    receipt=dict(event='target_reconfirmed',message_type='target_detection',robot='tb2',source_time=7.)
    p.write_text(json.dumps(receipt)+'\n'+json.dumps(e)+'\n')
    assert transit_heading_audit(p,True)['supported_intermediate_legs']==1
    receipt['robot']='tb1'
    p.write_text(json.dumps(receipt)+'\n'+json.dumps(e)+'\n')
    with pytest.raises(AssertionError):transit_heading_audit(p,True)
