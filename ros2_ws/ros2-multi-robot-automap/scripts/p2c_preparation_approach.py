"""Reconstruct a bounded FOUND approach without granting RALLY authority."""
import base64
import gzip
import json
import math

import numpy as np

from multi_robot_exploration import control
from p2c_outbound_routes import audit_outbound, bind_original_maps, decode


def segment_distance(point, start, end):
    edge = [b-a for a,b in zip(start,end)]
    square = sum(v*v for v in edge)
    fraction = min(1.,max(0.,sum((p-a)*v for p,a,v in zip(point,start,edge))/square)) if square else 0.
    return math.dist(point,[a+fraction*v for a,v in zip(start,edge)])


def audit_preparation(event, survey, connection_reinspection=False):
    saved=event['rally_preparation'];name=event['robot'];peer=saved['survey_robot']
    assert event['kind']=='rally_preparation_approach' and event['task_phase']=='FOUND' and name!=peer
    assert saved['timeout_sec']==60. and saved['dynamic_clearance_m']==.6
    assert saved['survey_attempt']>=1 and abs(saved['survey_goal_source_time_sec']-survey['dispatch_goal_source_time_sec'])<=2e-9
    assert survey['robot']==peer and survey['kind'] in ('target_information_survey','target_survey')
    choice=survey.get('target_survey_selection')
    if choice is not None:assert saved['target']==choice['target']
    original=survey['outbound_map_route']['route']
    assert saved['original_survey_route']==original
    witness=saved.get('connection_reinspection')
    if witness is None:
        assert saved['stage_destination']==original[-1]
    else:
        assert connection_reinspection,'undeclared parallel known connection reinspection'
        from p2c_rally_connection import rebuild_reinspection
        geometry=event['outbound_map_route']
        reference=dict(planning_map=geometry['planning_map'],inputs=event['inputs'],event_time=event['event_time'],
            robot_positions=saved['robot_positions'],current_positions=saved['robot_positions'],target=saved['target'])
        rebuilt=rebuild_reinspection(reference,name,geometry['local_map'])
        assert rebuilt is not None and rebuilt[1]==witness,'parallel reinspection differs from current conservative sources'
        assert np.allclose(saved['stage_destination'],rebuilt[0][1:3],rtol=0,atol=1e-8)
        raw=decode(geometry['planning_map']);local=geometry['local_map']
        local=dict(data=decode(local),resolution=local['resolution'],origin=local['origin'])
        previous=control.plan_rally_leg(control.RallyPose(*original[-1],0.),raw,
            geometry['planning_map']['resolution'],geometry['planning_map']['origin'],saved['robot_positions'][name],5.,
            blocked_positions=[body for other,body in saved['robot_positions'].items() if other!=name and body is not None],
            local_map=local)
        assert previous[0] is None,'parallel reinspection bypassed an available original full approach'
    assert list(saved['robot_positions'][name])==event['current_position']
    route=event['outbound_map_route']['route'];audit_outbound(event)
    length=sum(math.dist(a,b) for a,b in zip(route,route[1:]))
    assert .75<=length<=5.+1e-8 and math.dist(route[0],route[-1])>.35
    assert math.isclose(length,saved['path_distance_m'],abs_tol=1e-8)
    for other,body in saved['robot_positions'].items():
        assert body is not None and len(body)==2 and all(math.isfinite(v) for v in body)
        assert saved['battery_states'][other]['mode']=='ACTIVE'
        if other!=name:
            assert all(segment_distance(body,a,b)>=.6-1e-8 for a,b in zip(route,route[1:]))
    reservation=control.remaining_rally_route(original,saved['robot_positions'][peer])
    assert np.allclose(reservation,saved['survey_reservation'],rtol=0,atol=1e-8)
    assert saved['reserved_routes'] and len(saved['reserved_routes'][0])==len(reservation)
    assert np.allclose(saved['reserved_routes'][0],reservation,rtol=0,atol=1e-8)
    assert all(math.dist(p,q)>=1.8-1e-8 for reserved in saved['reserved_routes'] for p in route for q in reserved)
    geometry=event['outbound_map_route'];grid=decode(geometry['planning_map']);local=geometry['local_map']
    local=dict(data=decode(local),resolution=local['resolution'],origin=local['origin'])
    combined=control.constrained_return_grid(grid,geometry['planning_map']['resolution'],geometry['planning_map']['origin'],local)
    assert combined is not None
    resolution=geometry['planning_map']['resolution'];origin=geometry['planning_map']['origin']
    assert control.traversable_grid(combined,resolution,.45)[control.world_to_grid(*route[-1],resolution,*origin)]
    state=saved['battery_states'][name];at=saved['required_energy_evaluated_at_sec'];assert at<=event['event_time']
    assert saved['available_energy']==state['energy']
    assert state['stamp_sec']==event['inputs'][name+'/battery_state']['source_time']
    home=(state['charge_x'],state['charge_y'])
    candidates=control.qualified_return_candidates(grid,resolution,origin,route[-1],home,state['charge_radius_m'],local)
    distance=min((c['path_distance_m'] for c in candidates if c['qualified']),default=None);assert distance is not None
    map_age=max(at-event['inputs'][key]['source_time'] for key in ('headquarters/fused_map_snapshot',name+'/map_snapshot'))
    pose_age=max(at-event['inputs'][name+'/'+kind]['source_time'] for kind in ('pose_state','frame_state'))
    assert 0<=map_age<=5. and 0<=pose_age<=2.
    required=control.battery_assignment_required_energy(length,distance,state['move_cost_per_m'],state['idle_cost_per_sec'],
        state['return_path_factor'],state['nominal_speed_mps'],state['return_safety_margin'],
        state.get('return_recovery_wait_sec',control.RETURN_RECOVERY_WAIT_SEC),map_age,pose_age)+state['idle_cost_per_sec']*60.
    assert math.isclose(required,saved['required_energy'],rel_tol=1e-10,abs_tol=1e-8) and state['energy']>required


def bind_original_positions(events, capture, frame_offset_sec):
    from nav_msgs.msg import Odometry
    from tf2_msgs.msg import TFMessage
    from rclpy.serialization import deserialize_message
    wanted={}
    for index,event in enumerate(events):
        for name,point in event['rally_preparation']['robot_positions'].items():
            for kind in ('pose_state','frame_state'):
                key=(name,kind,round(event['inputs'][name+'/'+kind]['source_time']*1e9))
                wanted.setdefault(key,[]).append((index,name,point))
    sources={};topics={f'/{name}/{suffix}' for name,_,_ in wanted for suffix in ('odom','tf')}
    with gzip.open(capture,'rt') as stream:
        for line in stream:
            row=json.loads(line)
            if row['topic'] not in topics:continue
            name=row['topic'].split('/')[1]
            message=deserialize_message(base64.b64decode(row['cdr']),Odometry if row['topic'].endswith('/odom') else TFMessage)
            if isinstance(message,Odometry):
                ns=message.header.stamp.sec*10**9+message.header.stamp.nanosec;key=(name,'pose_state',ns)
                if key in wanted:sources.setdefault(key,[]).append(message.pose.pose.position)
            else:
                for t in message.transforms:
                    if not(t.header.frame_id.lstrip('/').endswith('map') and t.child_frame_id.lstrip('/').endswith('odom')):continue
                    ns=t.header.stamp.sec*10**9+t.header.stamp.nanosec-round(frame_offset_sec*1e9);key=(name,'frame_state',ns)
                    if key in wanted:sources.setdefault(key,[]).append(t.transform)
    assert set(sources)==set(wanted),'missing original preparation pose/TF CDR'
    count=0
    for event in events:
        for name,point in event['rally_preparation']['robot_positions'].items():
            odoms=sources[(name,'pose_state',round(event['inputs'][name+'/pose_state']['source_time']*1e9))]
            frames=sources[(name,'frame_state',round(event['inputs'][name+'/frame_state']['source_time']*1e9))]
            assert any(math.dist(control.transform_point_2d(p.x,p.y,t),point)<=1e-8 for p in odoms for t in frames),'preparation body differs from original pose/TF'
            count+=2
    return count


def preparation_approach_audit(path, required=False, capture=None, frame_offset_sec=.2, connection_reinspection=False):
    if not required:return None
    surveys={};pending={};seen=set();events=[];closed=revoked=0
    def source_key(records,robot,stamp):
        matches=[key for key in records if key[0]==robot and abs(key[1]-stamp)<=2e-9]
        assert len(matches)==1,'missing or ambiguous preparation action source'
        return matches[0]
    for line in path.open():
        event=json.loads(line);kind=event.get('event')
        if kind=='coordinator_navigation_decision':
            if event['kind'] in ('target_information_survey','target_survey'):
                surveys[event['robot'],event['dispatch_goal_source_time_sec']]=event
            elif event['kind']=='rally_preparation_approach':
                saved=event['rally_preparation'];key=(event['robot'],event['dispatch_goal_source_time_sec'])
                once=(event['robot'],saved['survey_robot'],saved['survey_goal_source_time_sec'])
                assert once not in seen,'repeated preparation during one bounded survey'
                seen.add(once);survey=surveys[source_key(surveys,saved['survey_robot'],saved['survey_goal_source_time_sec'])]
                audit_preparation(event,survey,connection_reinspection);pending[key]=event;events.append(event)
            elif event['kind']=='rally':assert not pending,'RALLY dispatched before preparation Futures drained'
        elif kind=='coordinator_rally_preparation_finished':
            pending.pop(source_key(pending,event['robot'],event['goal_source_time_sec']))
            closed+=1
        elif kind=='coordinator_navigation_dispatch_revoked' and event['kind']=='rally_preparation_approach':
            original=pending.pop((event['robot'],event['decision_time_sec']),None);assert original is not None
            saved=original['rally_preparation']
            seen.remove((original['robot'],saved['survey_robot'],saved['survey_goal_source_time_sec']))
            revoked+=1
    maps=bind_original_maps(events,capture) if events and capture is not None else 0
    poses=bind_original_positions(events,capture,frame_offset_sec) if events and capture is not None else 0
    return dict(status='PASS',decisions=len(events),closed_futures=closed,publication_revocations=revoked,
        pending_at_task_stop=len(pending),original_maps=maps,original_pose_frame_bindings=poses,
        scope='Current complete prefix/return/wait budget, body and survey reservations, original CDR and no RALLY dispatch before closure; optional motion at task stop retains native shutdown evidence')
