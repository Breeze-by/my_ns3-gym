"""A ready normal batch gets original admission before forced blocker recovery."""
import copy
import gzip
import json
import math
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest
from builtin_interfaces.msg import Time
from multi_robot_exploration import control as c
from p2c_return_preparation import decode_grid

FIXTURE=json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v88_prepared_rally_inputs.json.gz','rt'))

def node(case='dev_rooms202'):
    saved=next(r for r in FIXTURE['originals'] if r['case']==case)
    e=saved['event'];names=list(e['robot_positions']);clock=[10.]
    h=SimpleNamespace()
    for name,method in c.HeadquartersControl.__dict__.items():
        if callable(method) and not name.startswith('__'):
            setattr(h,name,MethodType(method,h))
    h.__dict__.update(enable_rally=True,enable_battery=True,task_state='RALLY',
        shutdown_requested=False,last_input_availability=True,last_input_diagnostic_at=10.,
        battery_monitor_started_at=10.,message_freshness_timeout_sec=5.,
        robot_positions={n:tuple(p) for n,p in e['robot_positions'].items()},
        robot_yaws={n:math.atan2(e['target'][1]-p[1],e['target'][0]-p[0]) for n,p in e['robot_positions'].items()},
        robot_velocities=dict.fromkeys(names,(0.,0.)),robot_states=dict.fromkeys(names,'idle'),
        goal_handles=dict.fromkeys(names),battery_modes=dict.fromkeys(names,'ACTIVE'),
        battery_states=copy.deepcopy(saved['battery_snapshot']),
        map_data=decode_grid(e['planning_map']),source_map_data=None,
        resolution=e['planning_map']['resolution'],origin=e['planning_map']['origin'],
        map_self_return_cells=e['self_return_cells'],
        robot_maps={n:dict(data=decode_grid(g),resolution=g['resolution'],origin=g['origin']) for n,g in e['return_maps'].items()},
        map_received_at=10.,robot_map_received_at=dict.fromkeys(names,10.),
        robot_odom_received_at=dict.fromkeys(names,10.),robot_tf_received_at=dict.fromkeys(names,10.),
        battery_state_received_at=dict.fromkeys(names,10.),target_received_source_time=10.,
        target=tuple(e['target']),target_view_distance=3.,target_view_fov_rad=math.pi/2,
        target_observing_robot=e['detecting_robot'],detecting_robot=e['detecting_robot'],
        target_scan_robot=None,target_scan_handle=None,survey_robot=None,
        survey_goal_handle=None,survey_goal_pending=False,survey_attempts=0,
        rally_charge_requested={},rally_precharge_staging={},rally_detour_budgets={},
        rally_targets={n:c.RallyPose(*p) for n,p in e['assignment'].items()},
        rally_final_targets={n:c.RallyPose(*p) for n,p in e['assignment'].items()},
        rally_dispatch_order=e['dispatch_order'][:],rally_arrived=dict.fromkeys(names,False),
        rally_goal_handles=dict.fromkeys(names),rally_goal_pending=dict.fromkeys(names,False),
        rally_goal_started_at=dict.fromkeys(names),rally_leg_routes=dict.fromkeys(names,()),
        rally_leg_poses=dict.fromkeys(names),rally_yield_requested=dict.fromkeys(names,False),
        rally_battery_preempted=dict.fromkeys(names,False),rally_attempts=dict.fromkeys(names,0),
        rally_recovery_requested=dict.fromkeys(names,False),rally_route_unavailable_since=dict.fromkeys(names,0.),
        rally_recovery_beneficiaries={},rally_yield_targets=set(),return_yield_targets={},
        rally_probe_targets=set(),rally_preflight_complete=True,rally_precharge_active=False,
        rally_max_concurrent=2,rally_max_retries=2,rally_goal_timeout_sec=60.,goal_timeout_sec=60.,
        rally_position_tolerance=.35,rally_linear_tolerance=.05,rally_angular_tolerance=.1,
        rally_hold_sec=5.,rally_hold_started_at=None,rally_wait_budgets={},rally_charge_budgets={},
        num_robots=len(names),last_rally_dispatch_at=0.,global_battery_rally_pause=False,
        use_map_safe_rally_order=True,now=lambda:clock[0],
        participating_robots=lambda:names[:],input_robot_names=lambda:names[:],
        robot_nav_clients={n:Mock() for n in names},charge_request_publishers={n:Mock() for n in names},
        consumed_publisher=Mock(),record_navigation_decision=Mock(return_value=True),
        publish_rally_assignments=Mock(),publish_task_state=Mock(),fail_task=Mock(),
        stop_target_scan=lambda:False,release_return_yields=lambda:None,yield_to_returning_robot=lambda:None,
        get_logger=lambda:Mock(),get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(to_msg=lambda:Time(sec=int(clock[0])))))
    for state in h.battery_states.values():state['stamp_sec']=10.  # explicitly controlled unit source epoch
    for client in h.robot_nav_clients.values():client.server_is_ready.return_value=True
    return h,clock


def normal_plans(h):
    h.prepare_rally_charges()
    plans={};targets={}
    for name in h.rally_dispatch_order:
        plan=c.plan_rally_leg(h.rally_targets[name],h.map_data,h.resolution,h.origin,
            h.robot_positions[name],min(c.MAX_NAVIGATION_LEG_M,c.rally_leg_limit(h.rally_attempts[name])),
            blocked_positions=[p for other,p in h.robot_positions.items() if other!=name],
            visible_only=False,local_map=h.robot_maps[name])
        if plan[0] is not None:plans[name]=plan;targets[name]=h.rally_targets[name]
    return plans,targets


def admit(h,plans,targets,returns=None):
    return c.HeadquartersControl.admit_prepared_rally_plans(h,plans,targets,set(),set(),
        h.rally_approach_routes,set(),set(),{} if returns is None else returns,recovery_waiter='tb2')


def test_frozen_update_replaces_a_ready_approach_new_update_posts_normal_batch_first():
    outcomes=[]
    for original in (True,False):
        h,_=node();before=dict(h.rally_targets)
        namespace=dict(vars(c));exec(compile(FIXTURE['original_update_mission'],'<frozen 8bf45eb update>','exec'),namespace)
        update=namespace['update_mission'] if original else c.HeadquartersControl.update_mission
        update(h)
        posted=[n for n,client in h.robot_nav_clients.items() if client.send_goal_async.called]
        outcomes.append((posted,set(h.rally_yield_targets)))
        if not original:
            assert h.rally_targets==before and not h.rally_recovery_beneficiaries
            assert h.rally_goal_pending['tb3'] and not h.rally_arrived['tb3']
    assert outcomes==[(['tb1'],{'tb1'}),(['tb3'],set())]


def test_after_controlled_peer_completion_normal_blocker_approach_is_not_replaced():
    h,clock=node();c.HeadquartersControl.update_mission(h)
    # Synthetic unit completion of the original posted final goal, not native truth.
    h.rally_goal_pending['tb3']=False;h.rally_arrived['tb3']=True
    final=h.rally_final_targets['tb3'];h.robot_positions['tb3']=(final.x,final.y)
    clock[0]=11.;h.map_received_at=h.target_received_source_time=11.
    for field in ('robot_map_received_at','robot_odom_received_at','robot_tf_received_at','battery_state_received_at'):
        setattr(h,field,dict.fromkeys(h.robot_positions,11.))
    before=dict(h.rally_targets);c.HeadquartersControl.update_mission(h)
    assert h.robot_nav_clients['tb1'].send_goal_async.called
    assert h.rally_targets==before and not h.rally_yield_targets
    assert not any(h.rally_arrived[n] for n in ('tb1','tb2'))


@pytest.mark.parametrize('case',['dev_rooms202','dev_corridors303'])
def test_original_full_budget_and_reservations_admit_prepared_batch(case):
    h,_=node(case);before=copy.deepcopy(h.battery_states);plans,targets=normal_plans(h)
    result=admit(h,plans,targets)
    assert result==(True,False) and any(h.rally_goal_pending.values())
    assert h.battery_states==before and not any(h.rally_arrived.values())
    witness=json.loads(h.consumed_publisher.publish.call_args.args[0].data)
    assert not witness['native_credit_added'] and witness['admission']=='original_send_rally_goal'


@pytest.mark.parametrize('condition',['no_slot','live_corridor','low_energy','server','stale','future','own_return'])
def test_no_posted_normal_goal_returns_false_for_original_recovery(condition):
    h,clock=node();plans,targets=normal_plans(h)
    returns={}
    if condition=='no_slot':h.rally_max_concurrent=0
    elif condition=='live_corridor':returns={'tb1':tuple(h.robot_positions.values())}
    elif condition=='low_energy':h.battery_states['tb3']['energy']=0.
    elif condition=='server':h.robot_nav_clients['tb3'].server_is_ready.return_value=False
    elif condition=='stale':clock[0]=12.001
    elif condition=='future':clock[0]=9.
    else:h.battery_modes['tb3']='RETURNING'
    assert admit(h,plans,targets,returns)==(False,False)
    assert not any(client.send_goal_async.called for client in h.robot_nav_clients.values())
    assert not any(h.rally_goal_pending.values())
    assert not h.consumed_publisher.publish.called


def test_failed_batch_attempt_preserves_original_blocker_recovery(monkeypatch):
    h,_=node()
    monkeypatch.setattr(c.HeadquartersControl,'admit_prepared_rally_plans',lambda *a,**k:(False,False))
    c.HeadquartersControl.update_mission(h)
    assert h.rally_yield_targets=={'tb1'} and h.rally_recovery_beneficiaries=={'tb1':'tb2'}
    assert h.robot_nav_clients['tb1'].send_goal_async.call_count==1


def test_source_expiration_during_original_budget_does_not_post(monkeypatch):
    h,clock=node();plans,targets=normal_plans(h);original=h.rally_plan_has_energy
    def expire(*args):
        funded=original(*args);clock[0]=12.001;return funded
    h.rally_plan_has_energy=expire
    assert admit(h,plans,targets)==(False,False)
    assert not any(client.send_goal_async.called for client in h.robot_nav_clients.values())
    assert h.robot_odom_received_at==dict.fromkeys(h.robot_positions,10.)


def witness():
    h,_=node();plans,targets=normal_plans(h);assert admit(h,plans,targets)==(True,False)
    return json.loads(h.consumed_publisher.publish.call_args.args[0].data)


def test_independent_reader_rebuilds_original_geometry_and_exact_budget():
    from p2c_prepared_dispatch import rebuild
    assert len(rebuild(witness()))==1


@pytest.mark.parametrize('field',['goal','route','prepared','yaw','price','distance','remaining',
    'capacity','wait','hold','source','future','native_stamp','order','body','native_credit'])
def test_independent_reader_rejects_forged_batch(field):
    from p2c_prepared_dispatch import rebuild
    event=witness();row=event['dispatched'][0];name=row['robot']
    if field=='goal':row['position'][0]+=.1
    elif field=='route':row['route'][0][0]+=.1
    elif field=='prepared':event['prepared_plans'][name]['route'][0][0]+=.1
    elif field=='yaw':event['prepared_plans'][name]['goal'][2]+=.1
    elif field=='price':row['budget']['required_energy']-=1.
    elif field=='distance':row['budget']['actual_distance_m']+=1.
    elif field=='remaining':row['budget']['remaining_route'][0][0]+=.1
    elif field=='capacity':row['budget']['available_energy']=event['battery_states'][name]['energy']=0.
    elif field=='wait':row['budget']['wait_budget_sec']+=1.
    elif field=='hold':row['budget']['hold_sec']=4.
    elif field=='source':event['inputs'][name+'/frame_state']['source_time']=7.
    elif field=='future':event['inputs'][name+'/frame_state']['source_time']=11.
    elif field=='native_stamp':event['battery_states'][name]['stamp_sec']=9.
    elif field=='order':event['dispatch_order'].reverse()
    elif field=='body':event['robot_positions']['tb1']=event['robot_positions'][name][:]
    else:event['native_credit_added']=True
    with pytest.raises((AssertionError,ValueError)):rebuild(event)
