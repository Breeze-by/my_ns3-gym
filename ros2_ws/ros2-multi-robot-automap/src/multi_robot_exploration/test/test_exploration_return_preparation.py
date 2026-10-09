"""A funded escape clears a real return corridor before the charge request."""
import copy
import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

from multi_robot_exploration import control as c
from p2c_return_preparation import audit_preparation, decode_grid


def node():
    names = ['tb1', 'tb2']
    grid = c.immutable_grid_snapshot(np.zeros((200, 200), dtype=np.int16), (200, 200))
    positions = {'tb1': (-4., 0.), 'tb2': (0., 0.)}
    states = {name:dict(energy=80., capacity=100., charge_target_fraction=.8,
        charge_x=3. if name == 'tb1' else 0., charge_y=0. if name == 'tb1' else -4.,
        charge_radius_m=.8, move_cost_per_m=1., idle_cost_per_sec=.02,
        return_path_factor=2., nominal_speed_mps=.18, return_safety_margin=8.) for name in names}
    events, sent, requests = [], [], []
    h = SimpleNamespace(clock=10., task_state='EXPLORE', enable_battery=True, enable_rally=True,
        map_data=grid, source_map_data=grid, resolution=.1, origin=(-10., -10.), map_received_at=10.,
        robot_positions=positions, robot_states=dict.fromkeys(names, 'idle'),
        battery_states=states, battery_modes=dict.fromkeys(names, 'ACTIVE'),
        robot_maps={n:dict(data=grid, resolution=.1, origin=(-10., -10.)) for n in names},
        robot_map_received_at=dict.fromkeys(names, 10.), robot_odom_received_at=dict.fromkeys(names, 10.),
        robot_tf_received_at=dict.fromkeys(names, 10.), battery_state_received_at=dict.fromkeys(names, 10.),
        map_self_return_cells={}, return_distance_caches={},
        pending_exploration_return_yield=None, exploration_return_yields={},
        exploration_resume_intents={'tb2': (4., 2., 1000)}, successful_exploration_legs={'tb2': 7},
        initial_search_next=dict.fromkeys(names, True), initial_search_goals=dict.fromkeys(names, False),
        target_history=[], bad_targets=[], target_search_active=False,
        rally_charge_requested={}, exploration_charge_budgets={}, rally_precharge_staging={},
        survey_robot=None, survey_goal_handle=None, survey_goal_pending=False,
        rally_goal_handles=dict.fromkeys(names), rally_goal_pending=dict.fromkeys(names, False),
        rally_battery_preempted=dict.fromkeys(names, False),
        goal_handles=dict.fromkeys(names), goal_targets=dict.fromkeys(names), goal_routes=dict.fromkeys(names, ()),
        goal_started_at=dict.fromkeys(names), goal_last_progress_at=dict.fromkeys(names),
        goal_best_distance=dict.fromkeys(names), goal_last_position=dict.fromkeys(names),
        goal_known_count=dict.fromkeys(names, 0), goal_initial_gain=dict.fromkeys(names, 0),
        cancel_requested=dict.fromkeys(names, False), battery_preempted=dict.fromkeys(names, False),
        consumed_publisher=SimpleNamespace(publish=lambda msg:events.append(json.loads(msg.data))),
        charge_request_publishers={n:SimpleNamespace(publish=lambda msg,n=n:requests.append((n,json.loads(msg.data)))) for n in names},
        get_logger=lambda:SimpleNamespace(info=lambda _:None, warn=lambda _:None),
        active_exclusions=lambda:[], check_exploration_completion=lambda:None)
    h.now = lambda:h.clock
    h.participating_robots = h.input_robot_names = lambda:[n for n,m in h.battery_modes.items() if m != 'FAILED']
    def inputs():
        out = {'headquarters/fused_map_snapshot':dict(source_time=h.map_received_at, ttl_sec=5.)}
        for n in h.participating_robots():
            for kind, stamps, ttl in [('pose_state',h.robot_odom_received_at,2.), ('frame_state',h.robot_tf_received_at,2.),
                    ('map_snapshot',h.robot_map_received_at,5.), ('battery_state',h.battery_state_received_at,5.)]:
                out[n+'/'+kind] = dict(source_time=stamps[n], ttl_sec=ttl)
        return out
    h.input_freshness_details = inputs
    h.fresh_robot_inputs = lambda:all(0 <= h.now()-s['source_time'] <= s['ttl_sec'] for s in inputs().values())
    def send(name, assignment):
        sent.append((name, assignment))
        goal = PoseStamped();goal.pose.position.x=assignment.navigation_x;goal.pose.position.y=assignment.navigation_y
        goal.pose.orientation.z=math.sin(assignment.navigation_yaw/2.);goal.pose.orientation.w=math.cos(assignment.navigation_yaw/2.)
        c.HeadquartersControl.record_navigation_decision(h, name, 'exploration_return_yield', goal, None, h.goal_routes[name])
    h.send_goal = send
    return h, events, sent, requests


def advance_sources(h, value):
    h.clock = h.map_received_at = value
    for name in h.robot_positions:
        for stamps in [h.robot_map_received_at, h.robot_odom_received_at, h.robot_tf_received_at, h.battery_state_received_at]:
            stamps[name] = value


def test_search_keeps_only_intent_and_fresh_callback_funds_escape():
    h, events, sent, requests = node()
    assert c.HeadquartersControl.prepare_exploration_return(h, 'tb1')
    assert not sent and not requests and h.pending_exploration_return_yield is not None
    assert set(h.pending_exploration_return_yield) == {'robot','returning','refuge','task_phase'}
    h.clock = 13.
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert not sent and not requests
    advance_sources(h, 13.)
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert len(sent) == 1 and sent[0][0] == 'tb2' and not requests
    assert sent[0][1].viewpoint.information_gain == sent[0][1].utility == 0
    assert audit_preparation(events[0]) == 'yield'


@pytest.mark.parametrize('reason', ['stale','future','blocked_refuge','unknown_route','unfunded','moved_blocker','phase','own_return','live_peer'])
def test_proposed_geometry_has_no_authority_after_inputs_change(reason):
    h, events, sent, requests = node()
    c.HeadquartersControl.prepare_exploration_return(h, 'tb1')
    proposal = h.pending_exploration_return_yield
    if reason == 'stale':h.clock=12.001
    if reason == 'future':h.robot_tf_received_at['tb2']=11.
    if reason == 'blocked_refuge':
        g=np.array(h.map_data);g[c.world_to_grid(proposal['refuge'].x,proposal['refuge'].y,h.resolution,*h.origin)]=100
        h.map_data=h.source_map_data=g
    if reason == 'unknown_route':
        g=np.array(h.map_data);g[:,110:112]=-1;h.map_data=h.source_map_data=g
        h.robot_maps['tb1']['data']=g
    if reason == 'unfunded':h.battery_states['tb2']['energy']=1.
    if reason == 'moved_blocker':h.robot_positions['tb2']=(0.,-3.)
    if reason == 'phase':h.task_state='FOUND'
    if reason == 'own_return':h.battery_modes['tb2']='RETURNING'
    if reason == 'live_peer':h.robot_states['tb2']='active'
    c.HeadquartersControl.admit_exploration_return_yield(h)
    assert not sent and not requests


def test_charge_is_withheld_until_actual_delivered_body_clears_corridor():
    h, events, sent, requests = node()
    h.battery_states['tb1']['energy']=25.
    a=c.Assignment(c.Viewpoint(1,160,60,161,60,1000,10),-4.,6.,6.,100.,-4.,6.)
    assert c.HeadquartersControl.request_exploration_charge(h,[('tb1',a)])
    assert not requests and not h.rally_charge_requested
    c.HeadquartersControl.admit_exploration_return_yield(h)
    assert len(sent)==1 and not requests
    assert not c.HeadquartersControl.request_exploration_charge(h,[('tb1',a)])
    h.robot_positions['tb2']=(sent[0][1].navigation_x,sent[0][1].navigation_y)
    c.HeadquartersControl.finish_goal(h,'tb2',True)
    assert h.successful_exploration_legs['tb2']==7
    assert h.exploration_resume_intents['tb2']==(4.,2.,1000)
    assert h.initial_search_next['tb2'] and not h.target_history
    assert c.HeadquartersControl.request_exploration_charge(h,[('tb1',a)])
    assert len(requests)==1 and audit_preparation(events[-1])=='charge'


def test_failed_robot_body_is_never_treated_as_an_empty_corridor():
    h, _, sent, requests = node();h.battery_modes['tb2']='FAILED'
    assert c.HeadquartersControl.prepare_exploration_return(h,'tb1')
    assert h.pending_exploration_return_yield is None and not sent and not requests


@pytest.mark.parametrize('position',[None,(float('nan'),0.),(0.,)])
def test_unavailable_or_malformed_peer_body_cannot_authorize_a_charge(position):
    h, _, sent, requests=node();h.robot_positions['tb2']=position
    assert not c.HeadquartersControl.fresh_return_preparation_inputs(h)
    assert c.HeadquartersControl.prepare_exploration_return(h,'tb1')
    assert h.pending_exploration_return_yield is None and not sent and not requests


def test_failed_escape_retains_original_bad_target_lease_without_search_credit():
    h, _, sent, _ = node();c.HeadquartersControl.prepare_exploration_return(h,'tb1')
    c.HeadquartersControl.admit_exploration_return_yield(h)
    a=sent[0][1];c.HeadquartersControl.finish_goal(h,'tb2',False)
    assert h.bad_targets==[(a.x,a.y,10.+c.BAD_TARGET_SEC)]
    assert h.successful_exploration_legs['tb2']==7 and h.exploration_resume_intents['tb2']==(4.,2.,1000)
    assert not h.exploration_return_yields and h.robot_states['tb2']=='idle'


def test_same_returner_updates_do_not_cancel_its_certified_escape():
    h, _, _, _ = node();h.battery_modes['tb1']='RETURNING'
    c.HeadquartersControl.prepare_exploration_return(h,'tb1');c.HeadquartersControl.admit_exploration_return_yield(h)
    canceled=[];h.goal_handles['tb2']=SimpleNamespace(cancel_goal_async=lambda:canceled.append(True))
    event=dict(**h.battery_states['tb1'],mode='RETURNING',stamp_sec=10.)
    c.HeadquartersControl.battery_state_callback(h,String(data=json.dumps(event)),'tb1')
    assert not canceled
    h.exploration_return_yields.clear()
    c.HeadquartersControl.battery_state_callback(h,String(data=json.dumps(event)),'tb1')
    assert canceled==[True]


@pytest.mark.parametrize('mode',['RETURNING','CHARGING'])
@pytest.mark.parametrize('bad',['missing','stale','future'])
def test_inactive_body_leases_are_required_even_when_ordinary_inputs_are_ready(mode,bad):
    h, _, sent, requests = node();h.battery_modes['tb1']=mode
    h.fresh_robot_inputs=lambda:True  # Ordinary admissions omit this inactive robot.
    h.robot_tf_received_at['tb1']={'missing':None,'stale':7.99,'future':11.}[bad]
    assert not c.HeadquartersControl.fresh_return_preparation_inputs(h)
    assert c.HeadquartersControl.prepare_exploration_return(h,'tb1')
    assert h.pending_exploration_return_yield is None and not sent and not requests


@pytest.mark.parametrize('tamper',['route','price','source','endpoint','clearance','local_map','body','phase','inactive_source'])
def test_independent_reader_rejects_corrupted_escape_authority(tamper):
    h, events, _, _ = node();c.HeadquartersControl.prepare_exploration_return(h,'tb1')
    c.HeadquartersControl.admit_exploration_return_yield(h);event=copy.deepcopy(events[0]);w=event['return_preparation']
    if tamper=='route':w['protected_routes']['tb1'][0][0]+=1.
    if tamper=='price':w['required_energy']-=1.
    if tamper=='source':event['inputs']['tb2/frame_state']['source_time']=0.
    if tamper=='endpoint':event['requested_position']=[0.,0.]
    if tamper=='clearance':w['clearance_m']=.5
    if tamper=='local_map':w['return_maps']['tb2']['source_time']-=.1
    if tamper=='body':w['robot_positions']['tb2']=[0.,-3.]
    if tamper=='phase':event['task_phase']='RALLY'
    if tamper=='inactive_source':
        w['battery_modes']['tb1']='RETURNING';w['inputs']['tb1/frame_state']['source_time']=7.99
    with pytest.raises((AssertionError,ValueError)):
        audit_preparation(event)


def test_original_v44_delivered_geometry_has_a_funded_visible_refuge():
    path=Path(__file__).with_name('fixtures')/'p2c_v44_return_preparation_inputs.json.gz'
    record=json.loads(gzip.decompress(path.read_bytes()))
    assert record['source_commit']=='39e1840930c692612d0cf0584050ae961dce4fff'
    e=record['event'];d=e['diagnostic_inputs'];h, events, sent, requests=node()
    h.clock=e['planning_started_at_sec'];w=d['planning_map']
    h.map_data=decode_grid(w);h.source_map_data=decode_grid(d['source_map'])
    h.resolution=w['resolution'];h.origin=w['origin'];h.map_received_at=w['source_time']
    h.robot_positions=d['robot_positions'];h.robot_states=d['robot_states'];h.battery_states=d['battery_states'];h.battery_modes=d['battery_modes']
    h.robot_maps={n:dict(data=decode_grid(s),resolution=s['resolution'],origin=s['origin']) for n,s in d['return_maps'].items()}
    h.map_self_return_cells=d['self_return_cells']
    for kind,attr in [('pose_state','robot_odom_received_at'),('frame_state','robot_tf_received_at'),
            ('map_snapshot','robot_map_received_at'),('battery_state','battery_state_received_at')]:
        setattr(h,attr,{n:e['inputs_at_start'][n+'/'+kind]['source_time'] for n in h.robot_positions})
    for attr in ['goal_handles','goal_targets','goal_started_at','goal_last_progress_at','goal_best_distance','goal_last_position']:
        setattr(h,attr,dict.fromkeys(h.robot_positions))
    h.goal_routes=dict.fromkeys(h.robot_positions,());h.goal_initial_gain=dict.fromkeys(h.robot_positions,0)
    assert h.fresh_robot_inputs()
    assert c.HeadquartersControl.prepare_exploration_return(h,'tb3')
    assert h.pending_exploration_return_yield['robot']=='tb2'
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert len(sent)==1 and not requests and audit_preparation(events[0])=='yield'
