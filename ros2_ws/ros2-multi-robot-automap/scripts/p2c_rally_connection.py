"""Rebuild private geometric survey proposals and bind their actual dispatches."""
import json
import math
import base64
import gzip

import numpy as np
from multi_robot_exploration import control
from p2c_outbound_routes import audit_outbound, bind_original_maps, decode


def audit_geometry(event):
    saved=event['planning_map'];grid=decode(saved)
    assert saved['source']=='ap_delivered_planning_map'
    assert saved['source_time']==event['inputs']['headquarters/fused_map_snapshot']['source_time']
    assert saved['source_time']<=event['event_time']<=event['computation_completed_at_sec']
    assert sorted(event['robot_positions'])==event['names']
    assert len(event['target'])==2 and np.isfinite(event['target']).all()
    data=control.prepare_frontier_data(grid,saved['resolution']);ranked=[]
    for name,position in event['robot_positions'].items():
        if event['battery_modes'][name]!='ACTIVE' or name==event['observer_robot']:continue
        if event.get('prioritized_names') and name not in event['prioritized_names']:continue
        options,_=control.robot_candidate_assignments(grid,saved['resolution'],saved['origin'],name,position,
            frontier_data=data,blocked_positions=[p for other,p in event['current_positions'].items()
                if other!=name and p is not None])
        for utility,_,_,assignment in options:
            view=assignment.viewpoint
            edge=control.grid_to_world(view.frontier_row,view.frontier_column,saved['resolution'],*saved['origin'])
            pose=(assignment.x,assignment.y,math.atan2(view.frontier_row-view.row,view.frontier_column-view.column))
            ranked.append((math.dist(edge,event['target']),-utility,name,pose))
    expected=[(name,*pose) for _,_,name,pose in sorted(ranked,key=lambda r:r[:3])]
    assert len(expected)==len(event['candidates']) and expected
    for actual,wanted in zip(event['candidates'],expected):
        assert actual[0]==wanted[0] and np.allclose(actual[1:],wanted[1:],rtol=0,atol=1e-8)
    return len(expected)


def audit_priority(event,assignment):
    """Rebuild the missing approach from original cells, without trusting its label."""
    assert assignment['event']=='coordinator_rally_assignment_failed'
    diagnostic=assignment['geometry_diagnostics'];name=diagnostic['robot']
    assert diagnostic['reason']=='disconnected_rally_approach'
    assert event['prioritized_names']==[name] and name!=event['observer_robot']
    assert event['target']==assignment['target'] and event['robot_positions']==assignment['robot_positions']
    assert event['current_positions']==assignment['current_positions']
    assert event['planning_map']==assignment['planning_map']
    assert event['event_time']>=assignment['computation_completed_at_sec']
    assert event['battery_modes'][name]=='ACTIVE'
    saved=assignment['planning_map'];raw=decode(saved)
    poses=control.rally_pose_candidates(raw,saved['resolution'],saved['origin'],assignment['target'],
        False,diagnostic['stratified'],adaptive_outer=not diagnostic['stratified'])
    assert len(poses)==diagnostic['candidate_count'] and len(poses)>=len(assignment['robot_positions'])
    local=assignment['return_maps'].get(name)
    geometry=None if local is None else dict(data=decode(local),resolution=local['resolution'],origin=local['origin'])
    grid=control.constrained_return_grid(raw,saved['resolution'],saved['origin'],geometry) if geometry else raw
    assert grid is not None
    safe=control.traversable_grid(grid,saved['resolution'],.35)
    cell=control.world_to_grid(*assignment['robot_positions'][name],saved['resolution'],*saved['origin'])
    start,_=control.navigation_start_route(grid,safe,cell,max(1,math.ceil(.6/saved['resolution'])))
    distances=control.path_distance_grid(safe,start)
    assert not any(np.isfinite(distances[control.world_to_grid(p.x,p.y,saved['resolution'],*saved['origin'])]) for p in poses)
    for stream in ('headquarters/fused_map_snapshot',name+'/map_snapshot',name+'/pose_state',name+'/frame_state'):
        assert event['inputs'][stream]['source_time']==assignment['inputs'][stream]['source_time']
    return len(poses)


def rally_connection_audit(path,required=False,capture=None):
    if not required:return None
    events=[json.loads(line) for line in path.open()]
    proposals={};assignments={};trials=0;accepted=[];points=0;priority_inputs=[]
    for offset,event in enumerate(events):
        kind=event.get('event')
        if kind=='coordinator_rally_assignment_failed':assignments[event['event_time']]=event
        if kind=='coordinator_rally_connection_geometry':
            epoch=event['event_time'];assert epoch not in proposals
            if event.get('prioritized_names'):
                assignment=assignments[event['assignment_evaluated_at_sec']]
                audit_priority(event,assignment)
                name=event['prioritized_names'][0]
                # Reuse the raw local/planning CDR binder; these are inputs,
                # not a second claimed navigation dispatch.
                priority_inputs.append(dict(robot=name,planning_map_self_return_cells=assignment['self_return_cells'],
                    outbound_map_route=dict(local_map=assignment['return_maps'][name],planning_map=assignment['planning_map'])))
            points+=audit_geometry(event);proposals[epoch]=event
        elif kind=='coordinator_rally_connection_trial':
            proposal=proposals[event['generated_at_sec']]
            assert event['target']==proposal['target'] and event['event_time']>=proposal['computation_completed_at_sec']
            candidate=proposal['candidates'][event['index']]
            assert event['robot']==candidate[0] and np.allclose(event['desired_pose'],candidate[1:],rtol=0,atol=1e-8)
            assert event['completed_at_sec']>=event['event_time']
            for name in proposal['names']:
                for suffix,ttl in (('pose_state',2.),('frame_state',2.),('battery_state',5.),('map_snapshot',5.)):
                    lease=event['inputs'][name+'/'+suffix];age=event['event_time']-lease['source_time']
                    assert 0<=age<=ttl and lease['ttl_sec']==ttl and math.isclose(age,lease['age_sec'],abs_tol=1e-8)
            target=event['inputs']['headquarters/target_detection']
            assert 0<=event['event_time']-target['source_time']<=60.
            if event['accepted']:
                choices=[e for e in events[:offset] if e.get('event')=='coordinator_navigation_decision'
                    and e['robot']==event['robot'] and e['kind']=='target_survey'
                    and event['event_time']<=e['event_time']<=event['completed_at_sec']]
                assert len(choices)==1,'accepted proposal needs its actual source-bound navigation decision'
                decision=choices[0];assert decision['task_phase']=='FOUND';audit_outbound(decision)
                for key in ('pose_state','frame_state','battery_state','map_snapshot'):
                    assert decision['inputs'][event['robot']+'/'+key]['source_time']==event['inputs'][event['robot']+'/'+key]['source_time']
                accepted.append(decision)
            trials+=1
    sources=bind_original_maps(accepted,capture) if capture is not None and accepted else 0
    generated_sources=bind_geometry_maps(proposals.values(),capture) if capture is not None and proposals else 0
    priority_sources=bind_original_maps(priority_inputs,capture) if capture is not None and priority_inputs else 0
    return dict(status='PASS',geometric_proposals=len(proposals),geometric_candidates=points,
        disconnected_approaches_rebuilt=len(priority_inputs),original_priority_source_maps=priority_sources,
        current_input_trials=trials,actual_dispatches=len(accepted),original_dispatch_source_maps=sources,
        original_geometric_source_maps=generated_sources,
        scope='Original geometric ranking and current dispatch/source binding; no physical movement, persistent connectivity or native task completion claim')


def bind_geometry_maps(proposals,capture):
    from nav_msgs.msg import OccupancyGrid
    from rclpy.serialization import deserialize_message

    wanted={}
    for event in proposals:
        epoch=round(event['planning_map']['source_time']*1e9)
        wanted.setdefault(epoch,[]).append(event)
    found=set()
    with gzip.open(capture,'rt') as stream:
        for line in stream:
            row=json.loads(line)
            if row['topic']!='/merge_map':continue
            msg=deserialize_message(base64.b64decode(row['cdr']),OccupancyGrid)
            epoch=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
            if epoch not in wanted:continue
            original=np.asarray(msg.data).reshape(msg.info.height,msg.info.width)
            for event in wanted[epoch]:
                saved=event['planning_map'];planned=decode(saved)
                assert original.shape==planned.shape and msg.info.resolution==saved['resolution']
                assert saved['origin']==[msg.info.origin.position.x,msg.info.origin.position.y]
                changed=set(map(tuple,np.argwhere(original!=planned)))
                assert changed==set(map(tuple,event['planning_map_self_return_cells'].values()))
                for r,c in changed:
                    assert 1<=r<original.shape[0]-1 and 1<=c<original.shape[1]-1
                    assert original[r,c]>=50 and planned[r,c]==0 and saved['resolution']*math.sqrt(2)<=.1
                    window=original[r-1:r+2,c-1:c+2].copy();window[1,1]=0;assert np.all(window==0)
            found.add(epoch)
    assert found==wanted.keys(),('missing original geometric source map',wanted.keys()-found)
    return len(found)
