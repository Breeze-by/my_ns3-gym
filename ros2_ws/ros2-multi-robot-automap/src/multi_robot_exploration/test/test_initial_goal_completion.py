"""Only funded initial ordinary completion may suppress informational cancellation."""
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from nav_msgs.msg import OccupancyGrid
from rclpy.serialization import serialize_message

from multi_robot_exploration import control as c
from p2c_initial_replenishment import initial_replenishment_audit
from p2c_outbound_routes import decode
from test_initial_replenishment import node as charge_node
from test_exploration_charging import assignment

FIXTURE = Path(__file__).parent / 'fixtures/p2c_v73_first_goal_inputs.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == 'fb8df27fdc8e6231ce41bbfb1ea41ef5766fad3240fe414913ba43bb3c8708d1'
SAVED = json.load(gzip.open(FIXTURE, 'rt'))


def original_cancel():
    source = SAVED['original_cancel']
    assert hashlib.sha256(source.encode()).hexdigest() == SAVED['original_cancel_sha256']
    namespace = dict(vars(c));exec(compile(source, '<d0be454 original cancel>', 'exec'), namespace)
    return namespace['cancel_stalled_goals']


def node():
    h, requests, events, sent = charge_node()
    h.successful_exploration_legs.clear()
    h.robot_positions['tb1'] = (2.5, 3.)
    h.robot_states['tb1'] = 'active'
    h.goal_timeout_sec = 60.
    h.goal_handles = {'tb1': Mock(), 'tb2': None}
    h.goal_started_at = {'tb1': 1., 'tb2': None}
    h.goal_last_progress_at = {'tb1': 9., 'tb2': None}
    h.goal_targets = {'tb1': assignment(3.5, 3., distance=1.), 'tb2': None}
    h.goal_initial_gain = {'tb1': 1000, 'tb2': 0}
    h.goal_routes = {'tb1': ((2.5, 3.), (3.5, 3.)), 'tb2': ()}
    h.cancel_requested = dict.fromkeys(h.robot_positions, False)
    h.target_information_gain = lambda *args: c.visible_unknown_gain(h.map_data, c.world_to_grid(*args,h.resolution,*h.origin), c.INFORMATION_RADIUS_M/h.resolution)
    h.target_search_active = False
    return h, requests, events, sent


def test_frozen_cancellation_and_current_completion_preserve_actual_goal_ownership(monkeypatch):
    monkeypatch.setattr(c.HeadquartersControl, 'has_funded_frontier_alternative', lambda *args: True)
    h,_,_,_ = node();original_cancel()(h)
    assert h.goal_handles['tb1'].cancel_goal_async.called and h.cancel_requested['tb1']
    h,requests,events,sent = node();goal=h.goal_handles['tb1'];c.HeadquartersControl.cancel_stalled_goals(h)
    assert h.goal_handles['tb1'] is goal and not goal.cancel_goal_async.called
    assert not requests and not sent and h.successful_exploration_legs == {}
    assert len(events)==1 and events[0]['event']=='coordinator_initial_exploration_completion_hold'
    assert events[0]['trip_required_energy'] < events[0]['required_energy'] < 40.
    c.HeadquartersControl.cancel_stalled_goals(h);assert len(events)==1


@pytest.mark.parametrize('reason', ['mapping_only','no_battery','rally','search','yield','idle','native_return','peer_return',
    'completed','bool_completed','charged','bool_count','missing_count','far','home','full','capacity','fraction','radius',
    'energy','nan','future_progress','blocked','local_blocked','unknown','body','peer_route','stale','missing_local','timeout','stalled'])
def test_invalid_or_unsafe_continuation_keeps_original_cancel(monkeypatch,reason):
    monkeypatch.setattr(c.HeadquartersControl,'has_funded_frontier_alternative',lambda *args:True)
    h,requests,events,sent=node()
    if reason=='mapping_only':h.enable_rally=False
    if reason=='no_battery':h.enable_battery=False
    if reason=='rally':h.task_state='RALLY'
    if reason=='search':h.target_search_active=True
    if reason=='yield':h.exploration_return_yields={'tb1':{}}
    if reason=='idle':h.robot_states['tb1']='idle'
    if reason=='native_return':h.battery_modes['tb1']='RETURNING'
    if reason=='peer_return':h.battery_modes['tb2']='RETURNING'
    if reason=='completed':h.successful_exploration_legs['tb1']=1
    if reason=='bool_completed':h.successful_exploration_legs['tb1']=False
    if reason=='charged':h.battery_states['tb1']['charge_count']=1
    if reason=='bool_count':h.battery_states['tb1']['charge_count']=False
    if reason=='missing_count':h.battery_states['tb1'].pop('charge_count')
    if reason=='far':h.goal_targets['tb1']=assignment(5.,3.)
    if reason=='home':h.goal_targets['tb1']=assignment(2.,3.)
    if reason=='full':h.battery_states['tb1']['energy']=80.
    if reason=='capacity':h.battery_states['tb1']['capacity']=-1.
    if reason=='fraction':h.battery_states['tb1']['charge_target_fraction']=1.1
    if reason=='radius':h.battery_states['tb1']['charge_radius_m']=0.
    if reason=='energy':h.battery_states['tb1']['energy']=.1
    if reason=='nan':h.battery_states['tb1']['energy']=float('nan')
    if reason=='future_progress':h.goal_last_progress_at['tb1']=11.
    if reason=='blocked':h.map_data=h.map_data.copy();h.map_data[:,30:32]=100;h.source_map_data=h.map_data
    if reason=='local_blocked':h.robot_maps['tb1']=dict(data=h.map_data.copy(),resolution=h.resolution,origin=h.origin);h.robot_maps['tb1']['data'][:,30:32]=100
    if reason=='unknown':h.map_data=h.map_data.copy();h.map_data[:,30:32]=-1;h.source_map_data=h.map_data
    if reason=='body':h.robot_positions['tb2']=(3.,3.)
    if reason=='peer_route':h.robot_states['tb2']='active';h.goal_routes['tb2']=((3.,2.),(3.,4.))
    if reason=='stale':h.clock=12.001
    if reason=='missing_local':h.robot_maps.pop('tb1')
    if reason=='timeout':h.clock=61.;h.goal_last_progress_at['tb1']=60.
    if reason=='stalled':h.clock=30.;h.goal_last_progress_at['tb1']=9.
    assert not c.HeadquartersControl.funded_initial_goal_completion(h,'tb1',h.goal_targets['tb1'])
    if reason in ('timeout','stalled'):
        c.HeadquartersControl.cancel_stalled_goals(h);assert h.goal_handles['tb1'].cancel_goal_async.called
    assert not requests and not sent and not events


@pytest.mark.parametrize('stage', ['route','price','serialization','publication'])
def test_expiry_during_work_or_private_publication_cannot_continue(monkeypatch,stage):
    h,_,events,_=node()
    if stage=='route':
        original=c.plan_rally_leg
        def expire(*args,**kwargs):result=original(*args,**kwargs);h.clock=13.;return result
        monkeypatch.setattr(c,'plan_rally_leg',expire)
    if stage=='price':
        original=c.HeadquartersControl.exploration_required_energy
        def expire(*args,**kwargs):result=original(*args,**kwargs);h.clock=13.;return result
        monkeypatch.setattr(c.HeadquartersControl,'exploration_required_energy',expire)
    if stage=='serialization':
        original=c.json.dumps
        def expire(*args,**kwargs):result=original(*args,**kwargs);h.clock=13.;return result
        monkeypatch.setattr(c.json,'dumps',expire)
    if stage=='publication':
        def expire(message):events.append(json.loads(message.data));h.clock=13.
        h.consumed_publisher.publish=expire
    assert not c.HeadquartersControl.funded_initial_goal_completion(h,'tb1',h.goal_targets['tb1'])
    assert len(events)==(1 if stage=='publication' else 0)


def test_original_lab_tb2_first_endpoint_is_currently_near_home_and_funded():
    saved=next(s for s in SAVED['snapshots'] if s['case']=='dev_lab101' and s['event']['robot']=='tb2')
    e=saved['event'];planning=e['planning_map'];names=e['robot_positions'];name=e['robot']
    h,_,events,_=node();h.robot_positions=copy.deepcopy(names);h.battery_states=copy.deepcopy(e['battery_states'])
    h.battery_modes={n:s['mode'] for n,s in h.battery_states.items()};h.robot_states=dict.fromkeys(names,'idle');h.robot_states[name]='active'
    h.clock=e['event_time'];h.map_data=decode(planning);h.source_map_data=h.map_data;h.resolution=planning['resolution'];h.origin=planning['origin'];h.map_received_at=planning['source_time']
    h.robot_maps={n:dict(data=decode(m),resolution=m['resolution'],origin=m['origin']) for n,m in e['return_maps'].items()}
    for attr,kind in [('robot_map_received_at','map_snapshot'),('robot_odom_received_at','pose_state'),('robot_tf_received_at','frame_state'),('battery_state_received_at','battery_state')]:
        setattr(h,attr,{n:e['inputs'][n+'/'+kind]['source_time'] for n in names})
    h.input_robot_names=lambda:list(names);h.participating_robots=lambda:list(names)
    h.goal_started_at={name:h.clock-.5};h.goal_last_progress_at={name:h.clock};h.goal_initial_gain={name:3285};h.goal_routes=dict.fromkeys(names,())
    goal=assignment(*e['requested_position'],distance=1.24)
    assert .35 < np.linalg.norm(np.array(e['requested_position'])-np.array([0.,.45])) <= 1.6
    assert c.HeadquartersControl.funded_initial_goal_completion(h,name,goal)
    assert len(events)==1 and events[0]['required_energy'] < h.battery_states[name]['energy']
    # This uses the original dispatch snapshot, not unrecorded cancellation-time state.


def reader_inputs():
    h,_,events,_=node();h.resolution=float(np.float32(h.resolution))
    for data in h.robot_maps.values():data['resolution']=h.resolution
    assert c.HeadquartersControl.funded_initial_goal_completion(h,'tb1',h.goal_targets['tb1'])
    event=events[0]
    rows=[dict(event='coordinator_navigation_decision',robot='tb1',kind='exploration',event_time=.5,requested_position=[3.5,3.]),
        dict(event='enqueue',message_type='navigation_goal',recipient='tb1',correlation_id=1,event_time=.5),event]
    native=[dict(topic='/tb1/battery_state',data=copy.deepcopy(h.battery_states['tb1']))]
    cdr=[]
    for key,topic in [('planning_map','/merge_map'),('local_map','/tb1/map')]:
        saved=event['outbound_map_route'][key];raw=decode(saved);msg=OccupancyGrid();msg.header.stamp.sec=int(saved['source_time']);msg.info.height,msg.info.width=raw.shape;msg.info.resolution=saved['resolution'];msg.info.origin.position.x,msg.info.origin.position.y=saved['origin'];msg.info.origin.orientation.w=1.;msg.data=raw.ravel().tolist()
        cdr.append(dict(topic=topic,cdr=base64.b64encode(serialize_message(msg)).decode()))
    return rows,native,cdr


@pytest.mark.parametrize('corrupt', ['valid','undeclared','missing_command','replaced_goal','wrong_kind','prior_success','charged','native_mismatch','timeout','no_progress','stale','future','age','route','body','peer_route','price','wait','unknown_map_source','gain','unrecorded_clear'])
def test_independent_reader_binds_real_command_raw_maps_native_state_and_budget(tmp_path,corrupt):
    rows,native,cdr=reader_inputs();e=rows[-1]
    if corrupt=='missing_command':rows.pop(1)
    if corrupt=='replaced_goal':rows[0]['requested_position']=[3.6,3.]
    if corrupt=='wrong_kind':rows[0]['kind']='exploration_return_yield'
    if corrupt=='prior_success':rows.insert(2,dict(event='navigation_outcome',recipient='tb1',correlation_id=1,status=4,event_time=2.))
    if corrupt=='charged':e['battery_states']['tb1']['charge_count']=1
    if corrupt=='native_mismatch':native[0]['data']['energy']=41.
    if corrupt=='timeout':e['goal_accepted_at_sec']=-51.
    if corrupt=='no_progress':e['goal_accepted_at_sec']=-20.;e['last_progress_at_sec']=-11.
    if corrupt=='stale':e['inputs']['tb1/frame_state']['source_time']=7.
    if corrupt=='future':e['inputs']['tb1/frame_state']['source_time']=11.
    if corrupt=='age':e['inputs']['tb1/frame_state']['age_sec']=.1
    if corrupt=='route':e['remaining_distance_m']+=.1
    if corrupt=='body':e['robot_positions']['tb2']=[3.,3.]
    if corrupt=='peer_route':e['robot_states']['tb2']='active';e['remaining_peer_routes']={'tb2':[[3.,2.],[3.,4.]]}
    if corrupt=='price':e['trip_required_energy']+=.1
    if corrupt=='wait':e['remaining_wait_energy']+=.1
    if corrupt=='unknown_map_source':cdr.clear()
    if corrupt=='gain':e['remaining_information_gain']=1
    if corrupt=='unrecorded_clear':e['planning_map_self_return_cells']={'tb1':[20,20]}
    ledger=tmp_path/'ledger.jsonl';ledger.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    safety=tmp_path/'native.jsonl';safety.write_text(''.join(json.dumps(r)+'\n' for r in native))
    capture=tmp_path/'cdr.jsonl.gz'
    with gzip.open(capture,'wt') as out:out.write(''.join(json.dumps(r)+'\n' for r in cdr))
    if corrupt=='valid':assert initial_replenishment_audit(ledger,True,safety,True,capture)['first_goal_completion_holds']==1
    else:
        with pytest.raises(AssertionError):initial_replenishment_audit(ledger,True,safety,corrupt!='undeclared',capture)
