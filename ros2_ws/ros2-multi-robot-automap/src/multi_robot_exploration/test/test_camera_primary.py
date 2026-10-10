"""Task camera preference needs actual work and the original hard admission."""
import copy
import gzip
import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from geometry_msgs.msg import PoseStamped
from multi_robot_exploration import control as c
from p2c_initial_replenishment import initial_replenishment_audit
from test_known_search_fallback import fallback_node, original_snapshot_node
from test_exploration_charging import assignment, install_candidates

FIXTURE=Path(__file__).parent/'fixtures/p2c_v74_camera_primary.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='2166663a0fa432fabd214ae89d9db7a2dc35b77533980958aebc570e6bc084c6'
SAVED=json.load(gzip.open(FIXTURE,'rt'))


def original():
    source=SAVED['original_assign'];assert hashlib.sha256(source.encode()).hexdigest()==SAVED['original_assign_sha256']
    ns=dict(vars(c));exec(compile(source,'<1dbc38d assign>', 'exec'),ns);return ns['assign_idle_robots']


def install_publication(h,events,sent):
    def publish(name,a):
        goal=PoseStamped();goal.pose.position.x=a.navigation_x;goal.pose.position.y=a.navigation_y
        frontier=c.grid_to_world(a.viewpoint.frontier_row,a.viewpoint.frontier_column,h.resolution,*h.origin)
        yaw=a.navigation_yaw if a.navigation_yaw is not None else math.atan2(frontier[1]-a.navigation_y,frontier[0]-a.navigation_x)
        goal.pose.orientation.z=math.sin(yaw/2.);goal.pose.orientation.w=math.cos(yaw/2.)
        kind='initial_visual_search' if h.initial_search_goals.get(name,False) else 'exploration'
        if c.HeadquartersControl.record_navigation_decision(h,name,kind,goal,None,h.goal_routes[name]):sent.append((name,a))
    h.send_goal=publish


def node():
    h,requests,events,sent=fallback_node();h.successful_exploration_legs={'tb1':1}
    install_publication(h,events,sent);return h,requests,events,sent


def test_real_work_prefers_existing_camera_pool_over_mapping_without_changing_first_work(monkeypatch):
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    h,_,_,old_sent=node();original()(h);assert len(old_sent)==1 and not h.initial_search_goals['tb1']
    h,requests,events,sent=node();c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and not requests and h.initial_search_goals['tb1']
    saved=events[0]['travel_preference']['camera_first_search']
    assert saved['selected_kind']=='camera' and saved['completed_exploration_legs']==1
    assert saved['mapping_reason'] is saved['primary_attempts'] is None


@pytest.mark.parametrize('reason',['no_work','bool_work','no_history','mapping_only'])
def test_context_without_camera_first_qualification_keeps_original_mapping(monkeypatch,reason):
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    h,_,events,sent=node()
    if reason=='no_work':h.successful_exploration_legs.clear()
    if reason=='bool_work':h.successful_exploration_legs['tb1']=True
    if reason=='no_history':h.initial_search_views.clear()
    if reason=='mapping_only':h.enable_rally=False
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:pytest.fail('camera qualification bypassed'))
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and not h.initial_search_goals.get('tb1',False)
    assert events[0]['travel_preference'].get('camera_first_search') is None


def test_empty_camera_pool_immediately_uses_original_mapping(monkeypatch):
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]});h,_,events,sent=node();calls=[]
    def empty(*a,**k):calls.append(k);return []
    monkeypatch.setattr(c,'known_space_search_candidates',empty)
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==len(calls)==1 and not h.initial_search_goals['tb1']
    saved=events[0]['travel_preference']['camera_first_search'];assert saved['selected_kind']=='mapping' and saved['mapping_reason']=='empty_visual_pool'


def test_empty_camera_and_mapping_pools_do_not_repeat_mapping_a_third_time(monkeypatch):
    h,_,_,sent=node();calls=[]
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:[])
    def mapping(*a,**k):calls.append(bool(k.get('blocked_positions')));return [],dict(frontier_groups=0,groups_with_viewpoints=0)
    monkeypatch.setattr(c,'robot_candidate_assignments',mapping)
    c.HeadquartersControl.assign_idle_robots(h)
    assert calls==[False,True] and not sent


def test_two_unfunded_camera_rounds_still_admit_a_funded_mapping_goal(monkeypatch):
    h,requests,events,sent=node();install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    camera=replace(assignment(4.,4.,distance=2.),navigation_yaw=math.pi/2)
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:[(camera.utility,'tb1',camera.viewpoint.group_id,camera)])
    budget=h.exploration_battery_factor;h.exploration_battery_factor=lambda n,d,p:0. if tuple(p)==(4.,4.) else budget(n,d,p)
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and not requests and not h.initial_search_goals['tb1']
    saved=events[0]['travel_preference']['camera_first_search'];assert saved['selected_kind']=='mapping'
    assert saved['mapping_reason']=='two_visual_rounds_without_action'
    assert [r['refine'] for r in saved['primary_attempts']]==[False,True]
    assert all(r['admitted']==0 for r in saved['primary_attempts'])


@pytest.mark.parametrize('reason',['stale','body','no_return','capacity','returning','concurrency'])
def test_camera_priority_keeps_original_hard_dispatch_guards(monkeypatch,reason):
    h,requests,events,sent=node()
    if reason=='stale':h.clock=12.001
    if reason=='body':h.robot_positions['tb2']=(2.,3.)
    if reason=='no_return':monkeypatch.setattr(c.HeadquartersControl,'exploration_required_energy',lambda *a,**k:None)
    if reason=='capacity':h.battery_states['tb1'].update(capacity=1.,energy=0.)
    if reason=='returning':h.battery_modes['tb2']='RETURNING'
    if reason=='concurrency':monkeypatch.setattr(c,'EXPLORATION_MAX_CONCURRENT',1)
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and not requests and not any(e.get('event')=='coordinator_navigation_decision' for e in events)


def test_expiration_during_camera_generation_rejects_then_new_sources_reprice(monkeypatch):
    h,requests,events,sent=node();fn=c.known_space_search_candidates
    def expired(*a,**k):rows=fn(*a,**k);h.clock=13.;return rows
    monkeypatch.setattr(c,'known_space_search_candidates',expired)
    c.HeadquartersControl.assign_idle_robots(h);assert not sent and not requests
    assert any(e.get('event')=='coordinator_planning_lease_expired' for e in events)
    monkeypatch.setattr(c,'known_space_search_candidates',fn);h.clock=13.;h.map_received_at=13.
    for stamps in (h.robot_odom_received_at,h.robot_tf_received_at,h.robot_map_received_at,h.battery_state_received_at):stamps.update(dict.fromkeys(h.robot_positions,13.))
    for s in h.battery_states.values():s['stamp_sec']=13.
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and events[-1]['travel_preference']['required_energy_evaluated_at_sec']==13.


@pytest.mark.parametrize('index',range(4))
def test_original_checkpoints_choose_a_funded_camera_leg_with_current_physical_budget(index):
    h,requests,events,sent=original_snapshot_node(copy.deepcopy(SAVED['snapshots'][index]));install_publication(h,events,sent)
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and not requests and h.initial_search_goals[sent[0][0]]
    expected=SAVED['comparisons'][index]['candidate']['goals'][0]
    a=sent[0][1];assert [a.navigation_x,a.navigation_y]==expected['position'] and a.navigation_yaw==expected['yaw']
    assert a.path_distance_m==pytest.approx(expected['planned_distance_m'])
    saved=events[0]['travel_preference'];assert saved['required_energy'] < h.battery_states[sent[0][0]]['energy']
    assert saved['camera_first_search']['completed_exploration_legs']>=1


def reader_inputs():
    h,_,events,_=node();c.HeadquartersControl.assign_idle_robots(h);assert len(events)==1
    return [dict(event='coordinator_navigation_decision',robot='tb1',kind='exploration',event_time=9.,travel_preference={'camera_first_search':None}),
        dict(event='enqueue',message_type='navigation_goal',recipient='tb1',correlation_id=1,event_time=9.),
        dict(event='navigation_outcome',recipient='tb1',correlation_id=1,status=4,event_time=9.5),events[0]]


@pytest.mark.parametrize('case',['valid','missing','undeclared','no_command','canceled','yield_success','bool_work','extra_work','no_history','history_count','future','old','wrong_kind','reason','attempts'])
def test_reader_requires_original_ordinary_success_and_current_declared_choice(tmp_path,case):
    rows=reader_inputs();e=rows[-1];f=e['travel_preference'];s=f['camera_first_search']
    if case=='missing':f.pop('camera_first_search')
    if case=='no_command':rows.pop(1)
    if case=='canceled':rows[2]['status']=5
    if case=='yield_success':rows[0]['kind']='exploration_return_yield'
    if case=='bool_work':s['completed_exploration_legs']=True
    if case=='extra_work':s['completed_exploration_legs']=2
    if case=='no_history':s['camera_history_count']=0
    if case=='history_count':s['camera_history_count']+=1
    if case=='future':s['generated_at_sec']=11.
    if case=='old':s['generated_at_sec']=7.
    if case=='wrong_kind':e['kind']='exploration'
    if case=='reason':s['mapping_reason']='empty_visual_pool'
    if case=='attempts':s['primary_attempts']=[]
    p=tmp_path/'ledger.jsonl';p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    if case=='valid':assert initial_replenishment_audit(p,False,None,False,None,True)['camera_first_search']['camera_primary']==1
    else:
        with pytest.raises(AssertionError):initial_replenishment_audit(p,False,None,False,None,case!='undeclared')


@pytest.mark.parametrize('reason', ['empty_visual_pool', 'two_visual_rounds_without_action'])
def test_reader_accepts_fresh_full_budget_mapping_after_declared_camera_attempts(tmp_path, monkeypatch, reason):
    h, requests, events, sent = node()
    install_candidates(monkeypatch, {'tb1': [assignment(4., 3.)]})
    if reason == 'empty_visual_pool':
        monkeypatch.setattr(c, 'known_space_search_candidates', lambda *a, **k: [])
    else:
        camera = replace(assignment(4., 4., distance=2.), navigation_yaw=math.pi/2)
        monkeypatch.setattr(c, 'known_space_search_candidates',
            lambda *a, **k: [(camera.utility, 'tb1', camera.viewpoint.group_id, camera)])
        budget = h.exploration_battery_factor
        h.exploration_battery_factor = lambda n, d, p: 0. if tuple(p) == (4., 4.) else budget(n, d, p)
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent) == 1 and not requests
    rows = [dict(event='coordinator_navigation_decision', robot='tb1', kind='exploration',
                 event_time=9., travel_preference={'camera_first_search': None}),
            dict(event='enqueue', message_type='navigation_goal', recipient='tb1', correlation_id=1, event_time=9.),
            dict(event='navigation_outcome', recipient='tb1', correlation_id=1, status=4, event_time=9.5), events[0]]
    p = tmp_path/'ledger.jsonl'
    p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    saved = events[0]['travel_preference']['camera_first_search']
    assert saved['mapping_reason'] == reason
    assert initial_replenishment_audit(p, False, None, False, None, True)['camera_first_search']['mapping_after_camera'] == 1
