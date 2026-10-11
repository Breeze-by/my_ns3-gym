"""A successful visual prefix retains its pool until the full viewpoint."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from multi_robot_exploration import control as c
from check_p2c_gate import exploration_travel_audit
from p2c_outbound_routes import check_route
from curve_reference import preserve_straight_prefix,assert_full_prefix_safety
from test_camera_primary import install_publication
from test_exploration_resume import assignment, finish_node
from test_known_search_fallback import original_snapshot_node

FIXTURE=Path(__file__).parent/'fixtures/p2c_v90_visual_continuation.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='4b85c20f5a4427775e0b8ad3250d8419f1d92442f51a94a2a6287be5523e19cf'
SAVED=json.load(gzip.open(FIXTURE,'rt'))


def original_finish():
    source=SAVED['original_finish_goal']
    assert hashlib.sha256(source.encode()).hexdigest()==SAVED['original_finish_goal_sha256']
    namespace=dict(vars(c));exec(compile(source,'<ad5 original finish_goal>','exec'),namespace)
    return namespace['finish_goal']


def finish_visual(phase='EXPLORE',prefix=True,visual=True,success=True,preempted=False):
    h=finish_node(assignment(8.,3.,navigation=(2.,3.) if prefix else (8.,3.)),phase,preempted)
    h.enable_rally=True;h.initial_search_next={'tb1':False};h.initial_search_goals={'tb1':visual}
    h.successful_exploration_legs={'tb1':5}
    return h


@pytest.mark.parametrize('phase',['EXPLORE','FOUND_UNCONFIRMED'])
def test_original_successful_partial_camera_command_loses_pool_and_new_keeps_it(phase):
    old=finish_visual(phase);original_finish()(old,'tb1',True)
    new=finish_visual(phase);c.HeadquartersControl.finish_goal(new,'tb1',True)
    assert not old.initial_search_next['tb1'] and new.initial_search_next['tb1']
    assert old.exploration_resume_intents==new.exploration_resume_intents=={'tb1':(8.,3.,1000)}
    assert old.successful_exploration_legs==new.successful_exploration_legs=={'tb1':6}
    assert new.robot_states['tb1']=='idle' and new.goal_targets['tb1'] is None


@pytest.mark.parametrize('reason',['mapping_prefix','full_camera','full_mapping','canceled','battery_preempted',
    'failed_battery','rally_phase','mapping_only','return_clearance','no_assignment'])
def test_other_finish_contexts_keep_original_behavior(reason):
    def node():
        h=finish_visual()
        if reason=='mapping_prefix':h.initial_search_goals['tb1']=False
        if reason.startswith('full_'):
            h.goal_targets['tb1']=assignment(8.,3.)
            h.initial_search_goals['tb1']=reason=='full_camera'
        if reason=='battery_preempted':h.battery_preempted['tb1']=True
        if reason=='failed_battery':h.battery_modes['tb1']='FAILED'
        if reason=='rally_phase':h.task_state='RALLY'
        if reason=='mapping_only':h.enable_rally=False
        if reason=='return_clearance':h.exploration_return_yields={'tb1':{}}
        if reason=='no_assignment':h.goal_targets['tb1']=None
        return h
    old=node();new=node();success=reason not in ('canceled','battery_preempted')
    original_finish()(old,'tb1',success,blacklist=False)
    c.HeadquartersControl.finish_goal(new,'tb1',success,blacklist=False)
    for attribute in ('initial_search_next','exploration_resume_intents','successful_exploration_legs',
            'robot_states','goal_targets','goal_routes','target_history','bad_targets'):
        assert getattr(old,attribute)==getattr(new,attribute)


def snapshot_node(retain):
    h,requests,events,sent=original_snapshot_node(copy.deepcopy(SAVED))
    data=SAVED['event']['diagnostic_inputs'];h.robot_yaws=dict(data['robot_yaws'])
    h.robot_names=list(h.robot_positions)
    h.input_robot_names=lambda:list(h.robot_positions)
    h.participating_robots=lambda:list(h.robot_positions)
    h.charge_request_publishers={name:SimpleNamespace(publish=lambda msg,n=name:requests.append((n,json.loads(msg.data))))
        for name in h.robot_positions}
    assert len(h.input_robot_names())==len(h.participating_robots())==len(h.robot_maps)==3
    h.pending_exploration_geometry=None;h.pending_exploration_charge_geometry=None
    if retain:
        for item in SAVED['partial_visual_commands']:
            name=item['robot'];command=item['command'];preference=command['travel_preference']
            n=finish_node(assignment(*preference['target'],gain=preference['information_gain'],navigation=command['requested_position']),preempted=False)
            n.enable_rally=True;n.initial_search_next={name:False};n.initial_search_goals={name:True}
            if name!='tb1':
                for field,value in vars(n).items():
                    if isinstance(value,dict) and 'tb1' in value:value[name]=value.pop('tb1')
            c.HeadquartersControl.finish_goal(n,name,True)
            assert n.exploration_resume_intents[name]==tuple(data['exploration_resume_intents'][name])
            h.initial_search_next[name]=n.initial_search_next[name]
    install_publication(h,events,sent)
    return h,requests,events,sent


@pytest.mark.parametrize('retain',[False,True])
@pytest.mark.parametrize('curved',[False,True])
def test_original_delivered_three_robot_snapshot_rebuilds_full_safe_choice(retain,curved,monkeypatch):
    if not curved:
        preserve_straight_prefix(monkeypatch)
    h,requests,events,sent=snapshot_node(retain)
    c.HeadquartersControl.assign_idle_robots(h)
    expected=SAVED['comparisons']['both_visual_pools' if retain else 'original']
    assert len(sent)==2 and requests==expected['requests']==[]
    for (name,a),goal in zip(sent,expected['goals']):
        f=h.exploration_travel_choices[name]
        assert name==goal['robot']
        if not curved:
            assert [a.navigation_x,a.navigation_y]==goal['position']
        assert [a.x,a.y]==goal['target'] and h.initial_search_goals[name]==goal['visual']
        assert a.path_distance_m==pytest.approx(goal['planned_distance_m'])
        assert f['required_energy']==pytest.approx(goal['required_energy'])
        assert f['required_energy']<h.battery_states[name]['energy']
        assert f['continuation_weight']==goal['continuation_weight']
    decisions=[e for e in events if e.get('event')=='coordinator_navigation_decision']
    assert len(decisions)==2
    for e in decisions:
        route=e['outbound_map_route']['route']
        assert route[-1]==pytest.approx(e['requested_position'])
        check_route(e['planning_map'],route)
        check_route(e['return_maps'][e['robot']],route,local=True)
    assert not c.routes_conflict(decisions[0]['outbound_map_route']['route'][1:],
                                decisions[1]['outbound_map_route']['route'][1:])
    assert_full_prefix_safety(h,sent)
    rebuilt=exploration_travel_audit(events,True,True,True,True,True,True,True,True)
    assert rebuilt['status']=='PASS' and rebuilt['resumed_frontier_witnesses']==(2 if retain else 0)


@pytest.mark.parametrize('reason',['stale','future','wrong_phase','unfunded'])
def test_retained_visual_pool_keeps_current_original_admission_guards(reason):
    h,requests,events,sent=snapshot_node(True)
    if reason=='stale':h.clock+=2.01
    if reason=='future':h.robot_tf_received_at['tb1']=h.clock+.01
    if reason=='wrong_phase':h.task_state='RALLY'
    if reason=='unfunded':
        for state in h.battery_states.values():state['energy']=0.
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and not any(e.get('event')=='coordinator_navigation_decision' for e in events)
