"""Only odd real ordinary completions add camera priority; hard gates remain."""
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from multi_robot_exploration import control as c
from p2c_initial_replenishment import initial_replenishment_audit
from check_p2c_gate import exploration_travel_audit
from test_camera_primary import node, install_publication
from test_exploration_charging import assignment, install_candidates
from test_known_search_fallback import original_snapshot_node

FIXTURE=Path(__file__).parent/'fixtures/p2c_v75_alternating_search.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='854184a0f2e44e424c7e3a74f49f043a1156263f98c3624d43b3b0f9628b3534'
SAVED=json.load(gzip.open(FIXTURE,'rt'))


@pytest.mark.parametrize('completed', [0,1,2,3,4,5,12,13,True,1.0])
def test_only_odd_integer_work_adds_camera_priority(completed,monkeypatch):
    h,requests,events,sent=node()
    h.successful_exploration_legs={'tb1':completed}
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    c.HeadquartersControl.assign_idle_robots(h)
    camera=type(completed) is int and completed>=1 and completed%2==1
    assert len(sent)==1 and not requests and h.initial_search_goals['tb1']==camera
    saved=events[0]['travel_preference']['camera_first_search']
    if camera:
        assert saved['completed_exploration_legs']==completed and saved['selected_kind']=='camera'
    else:
        assert saved is None and sent[0][1].viewpoint.group_id==assignment(4.,3.).viewpoint.group_id


def test_even_turn_preserves_original_explicit_visual_flag(monkeypatch):
    h,requests,events,sent=node();h.successful_exploration_legs={'tb1':2}
    h.initial_search_next={'tb1':True}
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    c.HeadquartersControl.assign_idle_robots(h)
    assert len(sent)==1 and not requests and h.initial_search_goals['tb1']
    assert events[0]['travel_preference']['camera_first_search'] is None


@pytest.mark.parametrize('index',range(7))
@pytest.mark.parametrize('fresh',[False,True])
def test_original_retained_and_fresh_checkpoints_match_prototype_and_full_budget(index,fresh):
    h,requests,events,sent=original_snapshot_node(copy.deepcopy(SAVED['snapshots'][index]))
    if fresh:
        h.pending_exploration_geometry=None;h.pending_exploration_charge_geometry=None
    install_publication(h,events,sent)
    c.HeadquartersControl.assign_idle_robots(h)
    expected=SAVED['comparisons'][index]['candidate_fresh' if fresh else 'candidate']
    actual=[dict(robot=n,position=[a.navigation_x,a.navigation_y],yaw=a.navigation_yaw,
                 visual=h.initial_search_goals.get(n,False),planned_distance_m=a.path_distance_m)
            for n,a in sent]
    keys=('robot','position','yaw','visual','planned_distance_m')
    assert actual==[{k:a[k] for k in keys} for a in expected['goals']]
    assert requests==expected['requests']
    for name,_ in sent:
        preference=h.exploration_travel_choices[name]
        assert preference['required_energy']<h.battery_states[name]['energy']
        if preference.get('camera_first_search') is not None:
            assert preference['camera_first_search']['completed_exploration_legs']%2==1
    assert exploration_travel_audit(events,True,True,True,True,True,True,True,True)['status']=='PASS'


@pytest.mark.parametrize('reason',['stale','returning','missing_route','low_capacity'])
@pytest.mark.parametrize('completed',[1,2])
def test_both_work_turns_retain_original_hard_admission(monkeypatch,reason,completed):
    h,requests,events,sent=node();h.successful_exploration_legs={'tb1':completed}
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    if reason=='stale':h.clock=12.001
    elif reason=='returning':h.battery_modes['tb2']='RETURNING'
    elif reason=='missing_route':monkeypatch.setattr(c.HeadquartersControl,'exploration_required_energy',lambda *a,**k:None)
    else:h.battery_states['tb1'].update(capacity=1.,energy=0.)
    c.HeadquartersControl.assign_idle_robots(h)
    assert not sent and not requests


@pytest.mark.parametrize('case',['old_even_allowed','new_even_rejected','undeclared','canceled_work','odd_valid','extra_work'])
def test_reader_checks_turn_against_real_prior_ordinary_outcomes(tmp_path,case):
    h,_,events,_=node();c.HeadquartersControl.assign_idle_robots(h)
    rows=[]
    for correlation,at in [(1,8.),(2,9.)]:
        rows.extend([dict(event='coordinator_navigation_decision',robot='tb1',kind='exploration',
                         event_time=at,travel_preference={'camera_first_search':None}),
                     dict(event='enqueue',message_type='navigation_goal',recipient='tb1',correlation_id=correlation,event_time=at),
                     dict(event='navigation_outcome',recipient='tb1',correlation_id=correlation,status=4,event_time=at+.5)])
    saved=events[0]['travel_preference']['camera_first_search']
    saved['completed_exploration_legs']=1 if case=='odd_valid' else 3 if case=='extra_work' else 2
    if case=='canceled_work':rows[5]['status']=5
    rows.append(events[0]);p=tmp_path/'ledger.jsonl';p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    declared=case!='undeclared';alternate=case!='old_even_allowed'
    if case in ('old_even_allowed','odd_valid'):
        result=initial_replenishment_audit(p,False,None,False,None,declared,alternate)
        assert result['camera_first_search']['camera_primary']==1
        assert result['camera_first_search']['alternating_declared']==alternate
    else:
        with pytest.raises(AssertionError):initial_replenishment_audit(p,False,None,False,None,declared,alternate)
