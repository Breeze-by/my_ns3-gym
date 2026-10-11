"""A disconnected robot can inspect its barrier without crossing either map."""
import copy
import gzip
import json
import math
from pathlib import Path

import numpy as np
import pytest
from multi_robot_exploration import control as c
from p2c_outbound_routes import decode
from p2c_rally_connection import audit_geometry, audit_priority, rebuild_reinspection
from test_rally_proposal_handoff import node_fixture, records


def original(index=1):
    path=Path(__file__).with_name('fixtures')/'p2c_v85_route_disagreement_inputs.json.gz'
    with gzip.open(path,'rt') as stream:saved=json.load(stream)
    event=saved['events'][index];planning=event['planning_map'];local=event['return_maps']['tb2']
    scope=vars(c).copy();exec(saved['reference_function'],scope)
    return event,decode(planning),dict(data=decode(local),resolution=local['resolution'],origin=local['origin']),scope['rally_connection_reinspection']


def arguments(event,raw,local):
    saved=event['planning_map']
    return (raw,saved['resolution'],saved['origin'],event['robot_positions']['tb2'],event['target'],local,
        [p for name,p in event['current_positions'].items() if name!='tb2' and p is not None])


def test_original_descent_keeps_the_same_choice_and_rank():
    event,raw,local,reference=original(0)
    assert c.rally_connection_reinspection(*arguments(event,raw,local))==reference(*arguments(event,raw,local))


@pytest.mark.parametrize('index',[1,2])
def test_original_stopped_descent_gets_a_different_fully_safe_observation_leg(index):
    event,raw,local,reference=original(index);args=arguments(event,raw,local)
    before=raw.tobytes(),local['data'].tobytes()
    assert reference(*args) is None
    pose,witness=c.rally_connection_reinspection(*args)
    assert witness['strategy']=='known_route_disagreement_view'
    assert math.dist(args[3],(pose.x,pose.y))>=.75
    assert math.dist((pose.x,pose.y),witness['barrier_world'])<=2.
    assert witness['angular_parallax_rad']>=math.pi/8
    barrier=tuple(witness['barrier_local_cell'])
    assert local['data'][barrier]>0
    assert raw[c.world_to_grid(*witness['barrier_world'],args[1],*args[2])]==0
    combined=c.constrained_return_grid(raw,args[1],args[2],local)
    assert c.traversable_grid(combined,args[1],.45)[tuple(witness['cell'])]
    plan=c.plan_rally_leg(pose,raw,args[1],args[2],args[3],5.,blocked_positions=args[6],local_map=local)
    assert plan[0] is not None
    route=(args[3],*plan[1]);distance=sum(math.dist(a,b) for a,b in zip(route,route[1:]))
    assert .75<distance<=5.
    assert c.route_respects_known_obstacles(raw,args[1],args[2],route)
    assert c.route_respects_known_obstacles(local['data'],local['resolution'],local['origin'],route)
    # Full return to the original contact region, with unchanged native costs.
    state=event['battery_states']['tb2'];home=(state['charge_x'],state['charge_y'])
    returns=c.qualified_return_candidates(raw,args[1],args[2],(pose.x,pose.y),home,state['charge_radius_m'],local)
    contact=min(r['path_distance_m'] for r in returns if r['qualified'])
    ages=event['inputs'];map_age=max(ages['headquarters/fused_map_snapshot']['age_sec'],ages['tb2/map_snapshot']['age_sec'])
    pose_age=max(ages['tb2/pose_state']['age_sec'],ages['tb2/frame_state']['age_sec'])
    required=c.battery_assignment_required_energy(distance,contact,state['move_cost_per_m'],state['idle_cost_per_sec'],
        state['return_path_factor'],state['nominal_speed_mps'],state['return_safety_margin'],
        state['return_recovery_wait_sec'],map_age,pose_age)+state['idle_cost_per_sec']*60.
    assert state['energy']>required
    rebuilt,expected=rebuild_reinspection(event,'tb2',event['return_maps']['tb2'])
    assert witness==expected and np.allclose((pose.x,pose.y,pose.yaw),rebuilt[1:],rtol=0,atol=1e-8)
    assert before==(raw.tobytes(),local['data'].tobytes())


@pytest.mark.parametrize('value',[1,49,50,100])
def test_observation_preference_preserves_every_positive_local_obstacle(value):
    event,raw,local,_=original();local['data']=local['data'].copy()
    local['data'][local['data']>0]=value
    before=local['data'].tobytes();pose,_=c.rally_connection_reinspection(*arguments(event,raw,local))
    combined=c.constrained_return_grid(raw,event['planning_map']['resolution'],event['planning_map']['origin'],local)
    assert c.traversable_grid(combined,event['planning_map']['resolution'],.45)[c.world_to_grid(pose.x,pose.y,event['planning_map']['resolution'],*event['planning_map']['origin'])]
    assert local['data'].tobytes()==before


def proposal():
    node,clock,_,_=node_fixture();event,raw,local,_=original();saved=event['planning_map']
    node.map_data=node.source_map_data=raw;node.resolution=saved['resolution'];node.origin=saved['origin']
    node.target=event['target'];node.robot_positions=event['robot_positions'];node.target_observing_robot='tb1'
    node.battery_modes={name:state['mode'] for name,state in event['battery_states'].items()}
    node.robot_maps={name:dict(data=decode(row),resolution=row['resolution'],origin=row['origin']) for name,row in event['return_maps'].items()}
    clock[0]=event['computation_completed_at_sec'];node.map_received_at=saved['source_time']
    node.robot_map_received_at={name:row['source_time'] for name,row in event['return_maps'].items()}
    node.participating_robots=lambda:sorted(event['robot_positions'])
    node.input_freshness_details=lambda:event['inputs']
    assert c.HeadquartersControl.survey_rally_connection(node,node.robot_positions,'tb2',event['event_time'])
    return event,records(node)[-1]


def test_complete_proposal_and_failed_approach_are_independently_bound():
    original_event,event=proposal()
    assert event['reinspection_inputs']['tb2']['choice']['strategy']=='known_route_disagreement_view'
    assert audit_priority(event,original_event)>2
    assert audit_geometry(event,True)==len(event['candidates'])


@pytest.mark.parametrize('change',['barrier_cell','barrier_world','score','parallax','blocked_cell','endpoint','erase_obstacle','old_source'])
def test_reader_rejects_changed_observation_geometry_and_unbound_sources(change):
    original_event,event=proposal();event=copy.deepcopy(event);row=event['reinspection_inputs']['tb2'];witness=row['choice']
    if change=='barrier_cell':witness['barrier_local_cell'][0]+=1
    if change=='barrier_world':witness['barrier_world'][0]+=.1
    if change=='score':witness['score']+=.1
    if change=='parallax':witness['angular_parallax_rad']+=.1
    if change=='blocked_cell':witness['first_blocked_fused_route_cell'][0]+=1
    if change=='endpoint':event['candidates'][0][1]+=.1
    if change=='old_source':row['local_map']['source_time']-=1.
    if change=='erase_obstacle':
        grid=decode(row['local_map']).copy();grid[tuple(witness['barrier_local_cell'])]=0
        saved=row['local_map'];row['local_map']=c.grid_audit_evidence(grid,saved['resolution'],saved['origin'],saved['source'],saved['source_time'],saved['version'])
    with pytest.raises(AssertionError):
        audit_geometry(event,True)
        audit_priority(event,original_event)


def test_current_peer_body_blocks_the_preferred_observation_pose():
    event,raw,local,_=original();args=list(arguments(event,raw,local))
    first,_=c.rally_connection_reinspection(*args);args[6].append((first.x,first.y))
    answer=c.rally_connection_reinspection(*args)
    assert answer is None or math.dist((first.x,first.y),(answer[0].x,answer[0].y))>=.6
