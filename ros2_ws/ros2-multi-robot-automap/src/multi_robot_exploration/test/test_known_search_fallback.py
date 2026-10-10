"""A blocked primary admission may safely use the existing camera search."""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest
from geometry_msgs.msg import PoseStamped
from multi_robot_exploration import control as c
from check_p2c_gate import exploration_travel_audit
from test_exploration_charging import assignment, charge_node, install_candidates
from p2c_return_preparation import decode_grid


def fallback_node():
    node,requests,events,sent=charge_node()
    node.enable_rally=True
    node.robot_states['tb2']='active'
    node.initial_search_next={'tb1':False}
    node.initial_search_visits={}
    node.initial_search_views={}
    node.initial_search_goals={}
    node.target_search_visits=[]
    node.clock=10.
    node.now=lambda:node.clock
    node.initial_search_views[0]=dict(robot='tb1',position=[2.,3.],yaw=0.,observed_at_sec=10.,
        pose_source_time=10.,frame_source_time=10.,source='ap_delivered_pose_and_heading_history')
    for state in node.battery_states.values():
        state.update(energy=80.,mode='ACTIVE',stamp_sec=10.,charge_count=1)
    node.input_freshness_details=lambda:{'headquarters/fused_map_snapshot':dict(
        source_time=node.map_received_at,age_sec=node.now()-node.map_received_at,ttl_sec=5.),
        **{name+'/'+kind:dict(source_time=stamps[name],age_sec=node.now()-stamps[name],ttl_sec=ttl)
            for name in node.robot_positions for kind,ttl,stamps in (
                ('pose_state',2.,node.robot_odom_received_at),('frame_state',2.,node.robot_tf_received_at),
                ('map_snapshot',5.,node.robot_map_received_at),('battery_state',5.,node.battery_state_received_at))}}
    node.fresh_robot_inputs=lambda:all(0<=sample['age_sec']<=sample['ttl_sec']
        for sample in node.input_freshness_details().values())
    def publish(name,a):
        goal=PoseStamped();goal.pose.position.x=a.navigation_x;goal.pose.position.y=a.navigation_y
        yaw=a.navigation_yaw or 0.;goal.pose.orientation.z=math.sin(yaw/2.);goal.pose.orientation.w=math.cos(yaw/2.)
        if c.HeadquartersControl.record_navigation_decision(node,name,'initial_visual_search',goal,None,node.goal_routes[name]):
            sent.append((name,a))
    node.send_goal=publish
    return node,requests,events,sent


@pytest.mark.parametrize('phase',['EXPLORE','FOUND_UNCONFIRMED'])
def test_two_empty_primary_rounds_admit_a_real_camera_candidate(monkeypatch,phase):
    node,requests,events,sent=fallback_node();node.task_state=phase
    install_candidates(monkeypatch,{})
    c.HeadquartersControl.assign_idle_robots(node)
    assert len(sent)==len(events)==1 and not requests
    saved=events[0]['travel_preference']['known_space_fallback']
    assert saved['primary_attempts']==[
        dict(refine=False,admitted=0,considered_candidates={'tb1':0}),
        dict(refine=True,admitted=0,considered_candidates={'tb1':0})]
    assert node.initial_search_goals['tb1']
    result=exploration_travel_audit(events,True,True,True,True,True,True,True,True)
    assert result['initial_visual_witnesses']==1


def test_admitted_primary_frontier_does_not_generate_fallback(monkeypatch):
    node,_,_,sent=fallback_node()
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:pytest.fail('primary was admitted'))
    c.HeadquartersControl.assign_idle_robots(node)
    assert len(sent)==1 and 'known_space_fallback' not in node.exploration_travel_choices['tb1']


def test_mapping_only_mode_does_not_generate_fallback(monkeypatch):
    node,_,events,sent=fallback_node();node.enable_rally=False
    install_candidates(monkeypatch,{})
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:pytest.fail('mapping-only fallback'))
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not events


def test_already_attempted_primary_camera_pool_is_not_repeated_a_third_time(monkeypatch):
    node,_,events,sent=fallback_node();node.initial_search_next['tb1']=True
    install_candidates(monkeypatch,{})
    calls=[]
    def empty(*args,**kwargs):calls.append(kwargs);return []
    monkeypatch.setattr(c,'known_space_search_candidates',empty)
    c.HeadquartersControl.assign_idle_robots(node)
    assert len(calls)==2 and not sent and not events


@pytest.mark.parametrize('reason',['stale','body','no_return','full_capacity','returning','active_limit'])
def test_fallback_does_not_bypass_original_hard_guards(monkeypatch,reason):
    node,requests,events,sent=fallback_node();install_candidates(monkeypatch,{})
    if reason=='stale':node.clock=12.001
    if reason=='body':node.robot_positions['tb2']=(2.,3.)
    if reason=='no_return':
        monkeypatch.setattr(c.HeadquartersControl,'exploration_required_energy',lambda *a,**k:None)
    if reason=='full_capacity':node.battery_states['tb1']['capacity']=1.;node.battery_states['tb1']['energy']=0.
    if reason=='returning':node.battery_modes['tb2']='RETURNING'
    if reason=='active_limit':
        monkeypatch.setattr(c,'EXPLORATION_MAX_CONCURRENT',1)
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests and not any(e.get('event')=='coordinator_navigation_decision' for e in events)


def test_live_expiration_discards_fallback_then_new_delivery_reprices(monkeypatch):
    node,requests,events,sent=fallback_node();install_candidates(monkeypatch,{})
    original=c.known_space_search_candidates
    def expire(*args,**kwargs):
        rows=original(*args,**kwargs);node.clock=12.001;return rows
    monkeypatch.setattr(c,'known_space_search_candidates',expire)
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests
    assert any(e.get('event')=='coordinator_planning_lease_expired' for e in events)
    monkeypatch.setattr(c,'known_space_search_candidates',original)
    node.clock=13.;node.map_received_at=13.
    for stamps in (node.robot_odom_received_at,node.robot_tf_received_at,node.robot_map_received_at,node.battery_state_received_at):
        stamps.update(dict.fromkeys(node.robot_positions,13.))
    for state in node.battery_states.values():state['stamp_sec']=13.
    c.HeadquartersControl.assign_idle_robots(node)
    assert len(sent)==1
    event=next(e for e in events if e.get('event')=='coordinator_navigation_decision')
    assert event['travel_preference']['known_space_fallback']['generated_at_sec']==13.
    assert event['travel_preference']['required_energy_evaluated_at_sec']==13.


@pytest.mark.parametrize('corruption',['undeclared','phase','admitted','rounds','refine_type','missing_robot','negative_count','old','future'])
def test_independent_reader_rejects_invalid_fallback_provenance(monkeypatch,corruption):
    node,_,events,_=fallback_node();install_candidates(monkeypatch,{})
    c.HeadquartersControl.assign_idle_robots(node)
    events=copy.deepcopy(events);event=events[0];saved=event['travel_preference']['known_space_fallback']
    if corruption=='phase':event['task_phase']='RALLY'
    if corruption=='admitted':saved['primary_attempts'][0]['admitted']=1
    if corruption=='rounds':saved['primary_attempts'].pop()
    if corruption=='refine_type':saved['primary_attempts'][0]['refine']=0
    if corruption=='missing_robot':saved['primary_attempts'][0]['considered_candidates'].clear()
    if corruption=='negative_count':saved['primary_attempts'][0]['considered_candidates']['tb1']=-1
    if corruption=='old':saved['generated_at_sec']=7.9
    if corruption=='future':saved['generated_at_sec']=10.1
    with pytest.raises(AssertionError):
        exploration_travel_audit(events,True,True,True,True,True,True,True,corruption!='undeclared')


def original_snapshot_node(saved):
    node,requests,events,sent=fallback_node()
    event=saved['event'];data=event['diagnostic_inputs'];planning=data['planning_map']
    node.clock=event['planning_started_at_sec']
    node.map_data=decode_grid(planning);node.source_map_data=decode_grid(data['source_map'])
    node.resolution=planning['resolution'];node.origin=planning['origin'];node.map_received_at=planning['source_time']
    node.frontier_cache=None
    node.robot_positions=data['robot_positions'];node.robot_states=dict(data['robot_states'])
    node.battery_states=data['battery_states'];node.battery_modes=data['battery_modes']
    node.robot_maps={name:dict(data=decode_grid(row),resolution=row['resolution'],origin=row['origin'])
        for name,row in data['return_maps'].items()}
    for attribute,kind in [('robot_odom_received_at','pose_state'),('robot_tf_received_at','frame_state'),
                           ('robot_map_received_at','map_snapshot'),('battery_state_received_at','battery_state')]:
        setattr(node,attribute,{name:event['inputs_at_start'][name+'/'+kind]['source_time'] for name in node.robot_positions})
    node.initial_search_next=dict(data['initial_search_next'])
    node.initial_search_visits=dict(enumerate(data['initial_search_visits']))
    node.initial_search_views=dict(enumerate(data['initial_search_views']))
    node.exploration_resume_intents=dict(data['exploration_resume_intents'])
    node.successful_exploration_legs=dict(data['successful_exploration_legs'])
    node.rally_charge_requested=dict(data['rally_charge_requested'])
    node.goal_routes=dict(data['goal_routes'])
    node.active_exclusions=lambda:data['exclusions']
    node.map_self_return_cells=data['self_return_cells']
    return node,requests,events,sent


def test_original_late_delivered_snapshot_has_a_safe_fallback_when_frozen_parent_admits_none():
    path=Path(__file__).parent/'fixtures/p2c_v71_known_search_fallback.json.gz'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='c95b85c2a0fa61a2ff383de4074a056b6e1929397fc269098fb961cde12acd19'
    saved=json.load(gzip.open(path,'rt'))
    source=saved['original_assign']
    assert hashlib.sha256(source.encode()).hexdigest()==saved['original_assign_sha256']
    namespace=dict(vars(c));exec(compile(source,'<d205de1 original assign>','exec'),namespace)
    old,old_requests,_,old_sent=original_snapshot_node(copy.deepcopy(saved))
    namespace['assign_idle_robots'](old)
    assert not old_sent and not old_requests
    new,requests,events,sent=original_snapshot_node(copy.deepcopy(saved))
    c.HeadquartersControl.assign_idle_robots(new)
    assert len(sent)==1 and not requests and sent[0][0]=='tb2'
    assert events[0]['travel_preference']['known_space_fallback']['primary_attempts'][1]['considered_candidates']['tb2']>0
    assert exploration_travel_audit(events,True,True,True,True,True,True,True,True)['initial_visual_witnesses']==1
