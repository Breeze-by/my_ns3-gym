"""Incoming intermediate yaw requires a stationary, current observing peer."""
import copy
import json
import math
from std_msgs.msg import String

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_navigation_dispatch_boundary import boundary_node


def transit_node():
    node, clock, sources, events, client, _ = boundary_node()
    node.target = (2.05, 3.05); node.target_observing_robot = 'tb2'
    node.target_received_source_time = 10.; node.target_view_distance = 3.
    node.target_view_fov_rad = math.pi/2
    node.target_observer_confirmations = {'tb2':dict(robot='tb2',source_time=10.,target=list(node.target),
        view_distance_m=3.,view_fov_rad=math.pi/2)}
    node.robot_positions['tb2'] = (3.05, 3.05)
    node.robot_yaws = {'tb1':0., 'tb2':math.pi}
    node.robot_velocities = {'tb1':(0.,0.), 'tb2':(0.,0.)}
    node.battery_modes['tb2'] = 'ACTIVE'
    node.robot_states = {'tb1':'idle', 'tb2':'idle'}
    node.rally_targets = {'tb1':c.RallyPose(1.05,3.05,.5), 'tb2':c.RallyPose(3.05,3.05,math.pi)}
    node.rally_arrived = {'tb1':False, 'tb2':True}
    node.rally_charge_requested = set(); node.rally_probe_targets = {}
    node.rally_goal_handles = {'tb1':None, 'tb2':None}; node.goal_handles = {'tb1':None, 'tb2':None}
    node.rally_goal_pending['tb2'] = False
    node.survey_robot = None; node.survey_goal_pending = False; node.survey_goal_handle = None
    node.rally_position_tolerance = .35; node.rally_linear_tolerance = .05; node.rally_angular_tolerance = .1
    node.map_data = np.zeros((60,60),dtype=int); node.map_received_at = 10.
    for key in ('pose_state','frame_state','map_snapshot','battery_state'):
        sources['tb2/'+key] = dict(source_time=10., ttl_sec=2. if key in ('pose_state','frame_state') else 5.)
    pose = c.RallyPose(2.05,1.05,0.); route = ((1.05,1.05),(2.05,1.05))
    return node, clock, sources, events, client, pose, route


def test_supported_intermediate_leg_keeps_incoming_yaw_without_changing_route_or_final():
    node, _, sources, events, client, pose, route = transit_node()
    original = copy.deepcopy(sources); final = dict(node.rally_targets)
    c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,route))
    sent = client.send_goal_async.call_args.args[0].pose.pose
    assert 2*math.atan2(sent.orientation.z,sent.orientation.w) == 0.
    assert node.rally_targets == final and node.rally_leg_routes['tb1'] is route
    assert sources == original and events[0]['rally_transit_observer']['observer'] == 'tb2'


def test_latest_confirmation_by_the_moving_robot_keeps_the_other_peers_original_support():
    node,clock,sources,events,client,pose,route=transit_node()
    clock[0]=10.1;node.target_observing_robot='tb1';node.target_received_source_time=10.1
    sources['headquarters/target_detection']['source_time']=10.1
    node.target_observer_confirmations['tb1']=dict(node.target_observer_confirmations['tb2'],robot='tb1',source_time=10.1)
    c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,route))
    assert client.send_goal_async.called
    assert events[0]['rally_transit_observer']['observer']=='tb2'
    assert events[0]['rally_transit_observer']['observer_source_time']==10.
    assert events[0]['inputs']['headquarters/target_detection']['source_time']==10.1


def test_confirmation_cache_keeps_only_original_new_accepted_stationary_receipts():
    node,clock,_,events,_,_,_=transit_node();clock[0]=10.1
    def receipt(value,target_x=2.05):
        return String(data=json.dumps(dict(robot='tb1',target_x=target_x,target_y=3.05,
            max_distance_m=2.9,field_of_view_deg=80.,stamp_sec=value,
            _gateway=dict(source_time=value,delivery_time=clock[0]))))
    c.HeadquartersControl.target_detection_callback(node,receipt(10.1))
    accepted=copy.deepcopy(node.target_observer_confirmations)
    assert accepted['tb1']==dict(robot='tb1',source_time=10.1,target=[2.05,3.05],
        view_distance_m=2.9,view_fov_rad=math.radians(80.))
    assert accepted['tb2']['source_time']==10.
    assert events[-1]['event']=='target_reconfirmed'
    for value in (10.1,10.,10.2):c.HeadquartersControl.target_detection_callback(node,receipt(value))
    clock[0]=10.3
    c.HeadquartersControl.target_detection_callback(node,receipt(10.2,9.))
    assert node.target_observer_confirmations==accepted and len(events)==1


@pytest.mark.parametrize('condition', ['same_robot','stale','future','not_arrived','displaced',
    'linear','angular','nonfinite','wrong_yaw','occluded','unknown','range','charging','pending','active',
    'exploring','survey','return_yield','charge_requested','probe','outgoing_yaw','single_point'])
def test_missing_stationary_observation_support_restores_original_target_heading(condition):
    node, _, sources, events, client, pose, route = transit_node()
    if condition=='same_robot':node.target_observer_confirmations={'tb1':dict(node.target_observer_confirmations['tb2'],robot='tb1')}
    if condition in ('stale','future'):
        value=4.9 if condition=='stale' else 10.1
        node.target_received_source_time=value;sources['headquarters/target_detection']['source_time']=value
        node.target_observer_confirmations['tb2']['source_time']=value
    if condition=='not_arrived':node.rally_arrived['tb2']=False
    if condition=='displaced':node.robot_positions['tb2']=(3.5,3.05)
    if condition=='linear':node.robot_velocities['tb2']=(.0501,0.)
    if condition=='angular':node.robot_velocities['tb2']=(0.,.1001)
    if condition=='nonfinite':node.robot_yaws['tb2']=math.nan
    if condition=='wrong_yaw':node.robot_yaws['tb2']=0.
    if condition in ('occluded','unknown'):node.map_data[30,25]=100 if condition=='occluded' else -1
    if condition=='range':node.target_view_distance=1.2;node.target_observer_confirmations['tb2']['view_distance_m']=1.2
    if condition=='charging':node.battery_modes['tb2']='CHARGING'
    if condition=='pending':node.rally_goal_pending['tb2']=True
    if condition=='active':node.rally_goal_handles['tb2']=object()
    if condition=='exploring':node.robot_states['tb2']='exploring'
    if condition=='survey':node.survey_robot='tb2';node.survey_goal_pending=True
    if condition=='return_yield':node.return_yield_targets['tb2']='tb3'
    if condition=='charge_requested':node.rally_charge_requested={'tb2'}
    if condition=='probe':node.rally_probe_targets['tb2']=(1.,1.)
    if condition=='outgoing_yaw':pose=c.RallyPose(pose.x,pose.y,.7)
    if condition=='single_point':route=(route[-1],)
    original_heading=c.rally_observation_heading(pose,node.target,node.map_data,node.resolution,node.origin,node.target_view_distance)
    c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,route))
    if condition=='future':
        assert not client.send_goal_async.called
        return
    assert not events[0].get('rally_transit_observer')
    sent=client.send_goal_async.call_args.args[0].pose.pose
    assert 2*math.atan2(sent.orientation.z,sent.orientation.w) == pytest.approx(original_heading.yaw)


def test_final_pose_and_safety_staging_keep_original_yaw():
    for kind in ('final','local_return_yield','charge_staging'):
        node, _, _, events, client, pose, route=transit_node()
        if kind=='final':node.rally_targets['tb1']=pose
        if kind=='local_return_yield':node.return_yield_targets['tb1']='tb2'
        c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,route),charge_staging=kind=='charge_staging')
        assert not events[0].get('rally_transit_observer')
        sent=client.send_goal_async.call_args.args[0].pose.pose
        assert sent.orientation.z == 0. and sent.orientation.w == 1.


@pytest.mark.parametrize('stage', ['preparation','publication'])
def test_observer_heartbeat_is_rechecked_after_heavy_preparation(monkeypatch,stage):
    node, clock, sources, events, client, pose, route=transit_node()
    clock[0]=10.95; node.target_received_source_time=6.
    sources['headquarters/target_detection']['source_time']=6.
    node.target_observer_confirmations['tb2']['source_time']=6.
    dumps=c.json.dumps
    def slow(value,**kwargs):
        if value.get('event')=='coordinator_navigation_decision':clock[0]=11.05
        return dumps(value,**kwargs)
    if stage=='preparation':monkeypatch.setattr(c.json,'dumps',slow)
    else:
        publish=node.consumed_publisher.publish
        def delayed(msg):publish(msg);clock[0]=11.05
        node.consumed_publisher.publish=delayed
    c.HeadquartersControl.send_rally_goal(node,'tb1',(pose,route))
    assert not client.send_goal_async.called
    if stage=='preparation':assert not events
    else:assert events[-1]['event']=='coordinator_navigation_dispatch_revoked'
    assert not node.rally_goal_pending['tb1'] and node.rally_attempts['tb1']==0
