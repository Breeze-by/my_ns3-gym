"""P2C: full-route budgets, source boundaries and bounded local degradation."""
import json
import math
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from multi_robot_exploration import control
from multi_robot_exploration.battery_manager import BatteryManager, plan_charging_leg


def detour_grid(blocked=False):
    grid = np.zeros((44, 44), dtype=np.int16)
    grid[:44 if blocked else 35, 20] = 100
    return grid


def manager(grid=None, position=(3.1, 1.1), home=(5.1, 1.1), energy=40.):
    events, states = [], []
    node = SimpleNamespace(robot_name='tb1', now=lambda:11., mode='ACTIVE',
        mission_terminal=False, map_position=position, charge_x=home[0], charge_y=home[1],
        last_odom_time=11., map_tf_source_time=11., frame_stamp_offset=.5,
        charge_radius=.8, energy=energy, move_cost=1., idle_cost=.02,
        return_path_factor=2., nominal_speed=.18, safety_margin=8., return_recovery_wait=30.,
        no_route_timeout=30., return_map=detour_grid() if grid is None else grid,
        return_map_resolution=.2, return_map_origin=(0.,0.), return_map_source_time=10.,
        return_map_source='local', return_map_version=1, return_map_generation=1,
        return_route_cache={}, return_route_caches={}, return_map_candidates={},
        return_no_route_since=None, return_audit_start=None, total_motion_distance=0.,
        total_energy_elapsed=0., return_count=0, return_cancels=0, return_rejections=0,
        return_goal_handle=None, return_goal_pending=False, return_goal_cancel_requested=False,
        return_audit_publisher=SimpleNamespace(publish=lambda msg: events.append(json.loads(msg.data))),
        publish_state=lambda:states.append(node.mode), failure_publisher=Mock(),get_logger=Mock())
    for method in ('in_charging_zone','current_return_budget','begin_return','guard_return_budget',
                   'audit_return','finish_return_audit','return_map_evidence','fail'):
        setattr(node, method, MethodType(getattr(BatteryManager, method), node))
    return node, events, states


def central(grid=None, position=(3.1,1.1), home=(5.1,1.1)):
    return SimpleNamespace(map_data=detour_grid() if grid is None else grid,
        resolution=.2, origin=(0.,0.), map_received_at=10., now=lambda:11.,
        robot_odom_received_at={'tb1':11.}, robot_positions={'tb1':position},
        battery_modes={'tb1':'ACTIVE'}, battery_states={'tb1':dict(energy=40.,
            charge_x=home[0],charge_y=home[1],charge_radius_m=.8,
            move_cost_per_m=1.,idle_cost_per_sec=.02,return_path_factor=2.,
            nominal_speed_mps=.18,return_safety_margin=8.)})


def test_detour_counterexample_is_closed_in_both_local_and_central_budgets():
    node, _, _ = manager()
    local = node.current_return_budget(include_route=True)
    old = 2. * 2. * (1. + .02 / .18) + 8.
    assert local['path_distance_m'] > 13.
    assert local['required_energy'] > old + 20.
    hq = central()
    assert control.HeadquartersControl.exploration_required_energy(hq,'tb1',0.,(3.1,1.1)) == pytest.approx(local['required_energy'])
    assert local['path_distance_m'] == pytest.approx(sum(math.dist(a,b) for a,b in zip(local['route'],local['route'][1:])))
    leg, prefix = plan_charging_leg(node.return_map,.2,(0.,0.),node.map_position,(5.1,1.1),.8)
    assert leg is not None and local['path_distance_m'] > 2. * sum(math.dist(a,b) for a,b in zip(prefix,prefix[1:]))


@pytest.mark.parametrize('kind',['disconnected','unknown_home','occupied_start','stale','future'])
def test_unavailable_route_has_no_finite_local_or_central_fallback(kind):
    grid=detour_grid(kind=='disconnected')
    if kind=='unknown_home':grid[:,21:]=-1
    if kind=='occupied_start':grid[5,15]=100
    node,_,_=manager(grid)
    hq=central(grid)
    if kind in ('stale','future'):
        node.return_map_source_time = hq.map_received_at = 5. if kind=='stale' else 12.
    assert node.current_return_budget() is None
    assert control.HeadquartersControl.exploration_required_energy(hq,'tb1',0.,(3.1,1.1)) is None


def test_cache_reuses_geometry_but_in_place_obstacle_change_invalidates_it():
    grid=detour_grid(); cache={}
    first=control.charging_route_field(grid,.2,(0.,0.),(5.1,1.1),.8,cache)
    assert control.charging_route_field(grid.copy(),.2,(0.,0.),(5.1,1.1),.8,cache) is first
    grid[:,20]=100
    assert control.known_return_route(grid,.2,(0.,0.),(3.1,1.1),(5.1,1.1),.8,cache)[0] is None
    assert cache['field'] is not first
    second=cache['field']
    control.charging_route_field(grid,.2,(-.2,0.),(5.1,1.1),.8,cache)
    assert cache['field'] is not second


def test_bounded_escape_selects_a_charger_connected_component():
    grid=np.zeros((60,60),dtype=np.int16)
    grid[28:31,:]=100;grid[28:31,25:29]=0
    position,home,res=(2.65,2.95),(2.65,4.15),.1
    safe,distances,_=control.charging_route_field(grid,res,(0.,0.),home,.8)
    initial=control.world_to_grid(*position,res,0.,0.)
    nearest,_=control.navigation_start_route(grid,safe,initial,6)
    assert nearest is not None and not np.isfinite(distances[nearest])
    distance,route=control.known_return_route(grid,res,(0.,0.),position,home,.8,include_route=True)
    assert distance is not None and math.dist(route[-1],home)<=.6+1e-8
    assert all(grid[control.world_to_grid(*p,res,0.,0.)]==0 for p in route)
    leg,prefix=plan_charging_leg(grid,res,(0.,0.),position,home,.8)
    assert leg is not None and np.isfinite(distances[control.world_to_grid(leg.x,leg.y,res,0.,0.)])
    assert len(prefix)-1<=6 and all(p in route for p in prefix)


def test_original_v2_failure_map_has_a_bounded_connected_escape():
    import base64,zlib
    from pathlib import Path
    event=json.loads((Path(__file__).with_name('fixtures')/'p2c_v2_wrong_escape.json').read_text())
    saved=event['map_evidence'];res=saved['resolution'];origin=saved['origin']
    grid=np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape'])
    safe,distances,_=control.charging_route_field(grid,res,origin,event['home'],event['charge_radius_m'])
    initial=control.world_to_grid(*event['position'],res,*origin)
    nearest,_=control.navigation_start_route(grid,safe,initial,math.ceil(.6/res))
    assert grid[initial]==0 and not safe[initial] and not np.isfinite(distances[nearest])
    distance,route=control.known_return_route(grid,res,origin,event['position'],event['home'],.8,include_route=True)
    assert distance is not None and 4.<distance<5.
    leg,prefix=plan_charging_leg(grid,res,origin,event['position'],event['home'],.8)
    assert leg is not None and len(prefix)-1<=math.ceil(.6/res)
    assert np.isfinite(distances[control.world_to_grid(leg.x,leg.y,res,*origin)])
    assert all(p in route for p in prefix)


@pytest.mark.parametrize('source',['local','delivered_fused'])
def test_fresh_complete_source_survives_other_source_loss_without_hidden_ap_input(source):
    node,_,_=manager(detour_grid(True))
    good=detour_grid()
    other='delivered_fused' if source=='local' else 'local'
    node.return_map_candidates={source:(good,.2,(0.,0.),10.,2,source),
        other:(detour_grid(True),.2,(0.,0.),10.,3,other)}
    budget=node.current_return_budget()
    assert budget is not None and budget['map_source']==source and budget['map_version']==2
    assert np.array_equal(node.return_map,good)
    node.now=lambda:16.
    assert node.current_return_budget() is None  # Reading a source never renews its TTL.


@pytest.mark.parametrize('source',['last_odom_time','map_tf_source_time'])
@pytest.mark.parametrize('stamp',[None,float('nan'),8.9,12.])
def test_native_pose_lease_rejects_missing_stale_and_future_sources(source,stamp):
    node,_,_=manager()
    setattr(node,source,stamp)
    assert node.current_return_budget() is None
    node.map_position=(node.charge_x,node.charge_y)
    assert not node.in_charging_zone()  # A stale pose cannot invent charging contact.


def test_native_pose_age_is_priced_and_preserved_in_the_return_prediction():
    node,_,_=manager();node.map_tf_source_time=9.5;node.last_odom_time=10.75
    budget=node.current_return_budget()
    assert budget['pose_age_sec']==1.5 and budget['frame_source_time']==9.5
    expected=control.return_energy_budget(budget['path_distance_m'],1.,.02,2.,.18,8.,30.,1.,1.5)
    assert budget['required_energy']==pytest.approx(expected['required_energy'])


def test_native_tf_uses_scan_source_not_future_validity_and_replay_cannot_replace_it():
    from geometry_msgs.msg import TransformStamped
    from tf2_msgs.msg import TFMessage
    node,_,_=manager();node.frame_stamp_offset=2.;node.map_tf_source_time=None
    node.previous_odom_position=(3.,4.);node.map_to_odom=None
    tf=TransformStamped();tf.header.frame_id='tb1/map';tf.child_frame_id='tb1/odom'
    tf.header.stamp.sec=13;tf.transform.rotation.w=1.;tf.transform.translation.x=1.
    BatteryManager.tf_callback(node,TFMessage(transforms=[tf]))
    assert node.map_tf_source_time==11. and node.map_position==(4.,4.)
    tf.header.stamp.sec=12;tf.transform.translation.x=9.
    BatteryManager.tf_callback(node,TFMessage(transforms=[tf]))
    assert node.map_tf_source_time==11. and node.map_position==(4.,4.)
    tf.header.stamp.sec=100
    BatteryManager.tf_callback(node,TFMessage(transforms=[tf]))
    assert node.map_tf_source_time==11. and node.map_position==(4.,4.)


def test_stale_native_pose_cannot_finish_a_charge_or_have_a_return_budget():
    node,_,_=manager(position=(5.1,1.1));node.mode='CHARGING'
    node.charge_stable_started_at=1.;node.last_odom_time=8.
    BatteryManager.update_charging(node,11.)
    assert node.mode=='CHARGING' and node.charge_stable_started_at is None
    assert node.current_return_budget() is None


def test_no_route_wait_cancels_once_keeps_handle_and_fails_with_positive_energy():
    node, events, states=manager(detour_grid(True))
    node.begin_return(None,reason='no_known_route')
    handle=Mock();node.return_goal_handle=handle
    assert not node.guard_return_budget(12.,None)
    assert not node.guard_return_budget(20.,None)
    handle.cancel_goal_async.assert_called_once()
    assert node.return_goal_handle is handle and node.energy>0.
    assert not node.guard_return_budget(41.,None)
    assert node.mode=='FAILED' and node.failure_reason=='battery_return_unreachable'
    assert states==['RETURNING','FAILED'] and events[-1]['outcome']=='battery_return_unreachable'


def test_map_recovery_resumes_a_funded_held_task_without_forcing_a_charge():
    node,events,states=manager(detour_grid(True),energy=60.)
    node.begin_return(None,reason='no_known_route')
    node.return_map=detour_grid()
    budget=node.current_return_budget()
    assert not node.guard_return_budget(13.,budget)
    assert node.mode=='ACTIVE' and states==['RETURNING','ACTIVE']
    assert events[-1]['outcome']=='route_recovered_resume'


@pytest.mark.parametrize('violation',['floor','distance','time'])
def test_runtime_envelope_cancels_motion_before_exhaustion(violation):
    node,_,_=manager()
    node.begin_return(node.current_return_budget()['required_energy'])
    budget=node.return_audit_start['budget']
    if violation=='floor':node.energy=8.
    if violation=='distance':node.total_motion_distance=budget['path_distance_m']*2.
    now=11.+budget['travel_time_budget_sec']+budget['waiting_time_budget_sec'] if violation=='time' else 12.
    assert not node.guard_return_budget(now,budget)
    assert node.mode=='FAILED' and node.energy>0.
    assert node.failure_reason=={'floor':'battery_return_reserve_depleted',
        'distance':'battery_return_motion_envelope','time':'battery_return_time_envelope'}[violation]


def test_return_prediction_error_and_native_snapshot_are_reconstructible():
    import base64,zlib
    node,events,_=manager()
    node.begin_return(node.current_return_budget()['required_energy'])
    saved=events[0]['map_evidence']
    restored=np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape'])
    assert np.array_equal(restored,node.return_map)
    node.energy-=12.;node.total_motion_distance=10.;node.total_energy_elapsed=100.
    prediction=node.return_audit_start['budget']['required_energy']-8.
    node.finish_return_audit('charger_stopped')
    result=events[-1]
    assert result['actual_energy_spent']==12. and result['actual_distance_m']==10.
    assert result['actual_elapsed_sec']==100. and result['prediction_error']==pytest.approx(12.-prediction)
    assert node.return_audit_start is None


@pytest.mark.parametrize('seed',range(12))
def test_reverse_contact_field_matches_forward_shortest_path_on_changing_maps(seed):
    rng=np.random.default_rng(seed)
    grid=np.zeros((36,36),dtype=np.int16)
    for _ in range(5):
        r,c=rng.integers(5,29,size=2);grid[r:r+3,c:c+2]=100
    grid[rng.random(grid.shape)<.01]=-1
    home=(1.1,1.1);res=.2;cache={}
    safe, reverse, _=control.charging_route_field(grid,res,(0.,0.),home,.8,cache)
    rows,cols=np.indices(grid.shape)
    contact=safe & ((res*(cols+.5)-home[0])**2+(res*(rows+.5)-home[1])**2<=(.8-.2)**2)
    for cell in np.argwhere(safe)[::73]:
        cell=tuple(cell)
        forward=control.path_distance_grid(safe,cell)
        expected=float(np.min(forward[contact])) if np.any(contact) else math.inf
        assert reverse[cell]==pytest.approx(expected)
        position=control.grid_to_world(*cell,res,0.,0.)
        distance,route=control.known_return_route(grid,res,(0.,0.),position,home,.8,cache,True)
        if distance is not None:
            assert distance==pytest.approx(sum(math.dist(a,b) for a,b in zip(route,route[1:])))
            assert math.dist(route[-1],home)<=.8
            assert all(grid[control.world_to_grid(*p,res,0.,0.)]==0 for p in route)


def test_diagonal_corner_cut_cannot_create_a_charger_path():
    safe=np.array([[True,False],[False,True]])
    goals=np.array([[False,False],[False,True]])
    field=control.path_distance_grid(safe,None,True,goal_mask=goals)[0]
    assert math.isinf(field[0,0])


@pytest.mark.parametrize('parameter',['distance_m','move_cost','idle_cost','path_factor','nominal_speed','safety_margin','source_age_sec','pose_age_sec'])
def test_nonfinite_return_budget_inputs_are_rejected(parameter):
    values=dict(distance_m=2.,move_cost=1.,idle_cost=.02,path_factor=2.,nominal_speed=.18,safety_margin=8.,source_age_sec=0.,pose_age_sec=0.)
    values[parameter]=float('nan')
    with pytest.raises(ValueError):control.return_energy_budget(**values)


@pytest.mark.parametrize('fault',['disconnected_map','stale_native_frame'])
def test_actual_ros_unavailable_input_emits_positive_energy_failure_without_nav_goal(fault):
    """Actual DDS/clock/action interfaces, synthetic map; no physical-motion claim."""
    import time
    import rclpy
    from rclpy.action import ActionServer
    from rclpy.qos import QoSProfile,DurabilityPolicy
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import OccupancyGrid,Odometry
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import String
    from tf2_msgs.msg import TFMessage
    from geometry_msgs.msg import TransformStamped
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','initial_energy:=40.0',
        '-p','charge_x:=5.1','-p','charge_y:=1.1'],domain_id=207 if fault=='disconnected_map' else 208)
    node=None;server=None;goals=[];failures=[]
    try:
        node=BatteryManager()
        def execute(handle):
            goals.append(handle.request);handle.abort();return NavigateToPose.Result()
        server=ActionServer(node,NavigateToPose,'/tb1/navigate_to_pose',execute)
        qos=QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        node.create_subscription(String,'/battery_failure',lambda m:failures.append(m.data),qos)
        clock=node.create_publisher(Clock,'/clock',10)
        maps=node.create_publisher(OccupancyGrid,'/tb1/map',qos)
        odoms=node.create_publisher(Odometry,'/tb1/odom',10)
        transforms=node.create_publisher(TFMessage,'/tb1/tf',10)
        grid=OccupancyGrid();grid.info.resolution=.2;grid.info.height=grid.info.width=44
        grid.data=(detour_grid(True) if fault=='disconnected_map' else np.zeros((44,44))).astype(np.int8).ravel().tolist()
        tf=TransformStamped();tf.header.frame_id='tb1/map';tf.child_frame_id='tb1/odom';tf.transform.rotation.w=1.
        odom=Odometry();odom.pose.pose.position.x=3.1;odom.pose.pose.position.y=1.1
        deadline=time.monotonic()+8.
        for stamp in range(10,45):
            msg=Clock();msg.clock.sec=stamp
            clock.publish(msg)
            while node.now()<stamp and time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.01)
            assert node.now()==stamp
            grid.header.stamp.sec=odom.header.stamp.sec=stamp
            tf.header.stamp.sec=stamp if fault=='disconnected_map' else 10
            tf.header.stamp.nanosec=500000000 if fault=='stale_native_frame' else 0
            maps.publish(grid);transforms.publish(TFMessage(transforms=[tf]));odoms.publish(odom)
            for _ in range(5):rclpy.spin_once(node,timeout_sec=.01)
            if node.mode=='FAILED':break
        for _ in range(10):rclpy.spin_once(node,timeout_sec=.01)
        expected='battery_return_unreachable' if fault=='disconnected_map' else 'battery_return_pose_unavailable'
        assert node.mode=='FAILED' and node.failure_reason==expected
        assert node.energy>node.safety_margin and not goals
        assert failures==[expected+':tb1']
        assert node.return_goal_handle is None and not node.return_goal_pending
    finally:
        if server is not None:server.destroy()
        if node is not None:node.destroy_node()
        rclpy.shutdown()
