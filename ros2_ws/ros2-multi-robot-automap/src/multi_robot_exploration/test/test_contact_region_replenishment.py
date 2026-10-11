"""Occupied charger centres cannot hide qualified one-time contact regions."""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from multi_robot_exploration import control as c
from p2c_initial_replenishment import initial_replenishment_audit
from test_initial_replenishment import conditional_node, node
from test_exploration_charging import assignment

FIXTURE=Path(__file__).parent/'fixtures/p2c_v87_contact_region_inputs.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='27e182f0fc87a06c9638d06707de640edadb3eea18cd94a435f1299f222bd0b2'
REFERENCE=json.load(gzip.open(FIXTURE,'rt'))


def original_budget():
    literal=REFERENCE['original_budget']
    assert hashlib.sha256(literal.encode()).hexdigest()==REFERENCE['original_budget_sha256']
    namespace=dict(vars(c));exec(compile(literal,'<6df4 original charge budget>','exec'),namespace)
    return namespace['exploration_charge_budget']


def snapshot(robot,after):
    return next(row for row in REFERENCE['originals'] if row['case']=='dev_lab101'
        and row['event']['robot']==robot and row['event']['event_time']-2135.482>after)


def actual_node(robot='tb1',after=30.):
    row=snapshot(robot,after);event=row['event'];preference=event['travel_preference']
    return conditional_node(dict(event=event,
        ordinary_successes=preference['camera_first_search']['completed_exploration_legs']))


@pytest.mark.parametrize('robot,after', [('tb1',30.),('tb3',70.)])
def test_closed_originals_have_body_safe_contact_plans_after_centre_veto(robot,after):
    h,name,goal=actual_node(robot,after)
    assert original_budget()(h,name,goal,True) is None
    result=c.HeadquartersControl.exploration_charge_budget(h,name,goal,True)
    assert result is not None and result[1]==80.
    saved=h.initial_replenishment_evidence[name]
    assert saved['trip_required_energy']<result[0]<result[1]
    assert saved['contact_region']['strategy']=='qualified_contact_endpoint'
    home=saved['home'];radius=h.battery_states[name]['charge_radius_m']
    assert math.dist(saved['contact_goal'][:2],home)<=radius-.2
    assert c.route_respects_known_obstacles(h.robot_maps[name]['data'],h.robot_maps[name]['resolution'],
        h.robot_maps[name]['origin'],(h.robot_positions[name],*saved['contact_route']),clearance_m=.35)
    assert all(math.dist(p,q)>=.35 for p in saved['contact_route'][1:]
        for n,q in h.robot_positions.items() if n!=name)


def test_contact_region_does_not_bypass_the_original_blocked_peer_case():
    h,name,goal=actual_node('tb3',30.)
    assert original_budget()(h,name,goal,True) is None
    assert c.HeadquartersControl.exploration_charge_budget(h,name,goal,True) is None
    assert not h.initial_replenishment_evidence


@pytest.mark.parametrize('reason',('no_work','prior_charge','bool_count','missing_count','mapping','far','full','capacity','unknown'))
def test_fallback_cannot_create_one_time_authority_from_ineligible_inputs(reason):
    h,name,goal=actual_node()
    if reason=='no_work':h.successful_exploration_legs.clear()
    if reason=='prior_charge':h.battery_states[name]['charge_count']=1
    if reason=='bool_count':h.battery_states[name]['charge_count']=False
    if reason=='missing_count':h.battery_states[name].pop('charge_count')
    if reason=='mapping':h.enable_rally=False
    if reason=='far':h.robot_positions[name]=[-3.,-3.]
    if reason=='full':h.battery_states[name]['energy']=80.
    if reason=='capacity':h.battery_states[name]['capacity']=10.
    if reason=='unknown':
        h.map_data=np.full_like(h.map_data,-1)
        for geometry in h.robot_maps.values():geometry['data']=np.full_like(geometry['data'],-1)
    assert c.HeadquartersControl.exploration_charge_budget(h,name,goal,True)==original_budget()(h,name,goal,True)
    assert not h.initial_replenishment_evidence


def controlled_node():
    h,requests,events,sent=node()
    h.robot_positions['tb1']=(3.2,3.)
    h.map_data=h.map_data.copy();h.map_data[30,20]=100
    h.source_map_data=h.map_data
    for geometry in h.robot_maps.values():geometry['data']=h.map_data
    return h,requests,events,sent


def controlled_reader_inputs():
    h,requests,events,sent=controlled_node()
    goal=assignment(3.5,3.,distance=.5)
    assert original_budget()(h,'tb1',goal,True) is None
    assert c.HeadquartersControl.request_exploration_charge(h,[('tb1',goal)])
    assert len(requests)==len(events)==1 and not sent
    assert events[0]['initial_replenishment']['contact_region']
    rows=[dict(event='coordinator_navigation_decision',robot='tb1',kind='exploration',event_time=9.),
        dict(event='enqueue',message_type='navigation_goal',recipient='tb1',correlation_id=1,event_time=9.),
        dict(event='navigation_outcome',recipient='tb1',correlation_id=1,status=4,event_time=9.5),events[0]]
    native=[dict(topic='/tb1/battery_state',observer_time=10.,data=copy.deepcopy(h.battery_states['tb1']))]
    return rows,native


@pytest.mark.parametrize('reason',(None,'undeclared','source','distance','qualified_route','endpoint','goal','route','no_work','native_count','stale'))
def test_independent_reader_binds_fallback_to_original_preparation_and_sources(tmp_path,reason):
    rows,native=controlled_reader_inputs();e=rows[-1];contact=e['initial_replenishment']['contact_region']
    if reason=='source':contact['source']='invented'
    if reason=='distance':contact['path_distance_m']+=.1
    if reason=='qualified_route':contact['qualified_route']=[[100.,100.]]
    if reason=='endpoint':contact['endpoint']=[100.,100.]
    if reason=='goal':e['initial_replenishment']['contact_goal'][0]+=.1
    if reason=='route':e['initial_replenishment']['contact_route']=[[100.,100.]]
    if reason=='no_work':rows[2]['status']=5
    if reason=='native_count':native[0]['data']['charge_count']=1
    if reason=='stale':e['inputs']['tb1/frame_state']['source_time']=7.
    ledger,raw=tmp_path/'ledger.jsonl',tmp_path/'native.jsonl'
    ledger.write_text(''.join(json.dumps(r)+'\n' for r in rows));raw.write_text(''.join(json.dumps(r)+'\n' for r in native))
    if reason is None:
        assert initial_replenishment_audit(ledger,True,raw,allow_contact_region=True)['policy_requests']==1
    else:
        with pytest.raises(AssertionError):initial_replenishment_audit(ledger,True,raw,allow_contact_region=reason!='undeclared')


@pytest.mark.parametrize('change',('stale','live_peer','charging','returning','future','expired_during_plan'))
def test_contact_fallback_keeps_original_request_time_guards(monkeypatch,change):
    h,requests,events,sent=controlled_node()
    if change=='stale':h.clock=12.001
    if change=='future':h.robot_tf_received_at['tb1']=10.1
    if change=='live_peer':h.robot_states['tb2']='active'
    if change=='charging':h.battery_modes['tb2']='CHARGING'
    if change=='returning':h.battery_modes['tb2']='RETURNING'
    if change=='expired_during_plan':
        old=c.plan_rally_leg
        def expire(*args,**kwargs):
            result=old(*args,**kwargs);h.clock=13.;return result
        monkeypatch.setattr(c,'plan_rally_leg',expire)
    c.HeadquartersControl.request_exploration_charge(h,[('tb1',assignment(3.5,3.,distance=.5))])
    assert not requests and not events and not sent
