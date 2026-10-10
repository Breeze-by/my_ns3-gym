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


def rally_connection_audit(path,required=False,capture=None):
    if not required:return None
    events=[json.loads(line) for line in path.open()]
    proposals={};trials=0;accepted=[];points=0
    for offset,event in enumerate(events):
        kind=event.get('event')
        if kind=='coordinator_rally_connection_geometry':
            epoch=event['event_time'];assert epoch not in proposals
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
    return dict(status='PASS',geometric_proposals=len(proposals),geometric_candidates=points,
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
