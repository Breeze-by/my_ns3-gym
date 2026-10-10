import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from multi_robot_exploration import control


def refuge_node():
    names = ('tb1', 'tb2'); clock = [11.]
    grid = control.immutable_grid_snapshot(np.zeros((100,100),dtype=np.int16),(100,100))
    targets = {'tb1':control.RallyPose(7.05,2.05,0.), 'tb2':control.RallyPose(7.05,5.05,0.)}
    inputs = {'headquarters/fused_map_snapshot':dict(source_time=10.,ttl_sec=5.),
              'headquarters/target_detection':dict(source_time=10.,ttl_sec=60.)}
    for name in names:
        for kind,ttl in (('pose_state',2.),('frame_state',2.),('map_snapshot',5.),('battery_state',5.)):
            inputs[name+'/'+kind] = dict(source_time=10.,ttl_sec=ttl)
    node = SimpleNamespace(enable_battery=True, rally_charge_requested={},
        battery_modes=dict.fromkeys(names,'ACTIVE'), rally_goal_handles=dict.fromkeys(names),
        rally_goal_pending=dict.fromkeys(names,False), goal_handles=dict.fromkeys(names),
        robot_states=dict.fromkeys(names,'idle'), target_scan_robot=None, target_scan_handle=None,
        survey_goal_handle=None, survey_goal_pending=False,
        rally_arrived={'tb1':True,'tb2':False}, return_yield_targets={'tb1':'tb2'},
        rally_yield_targets={'tb1'}, rally_recovery_beneficiaries={},
        rally_route_unavailable_since=dict.fromkeys(names),
        rally_targets={'tb1':control.RallyPose(1.05,2.05,0.),'tb2':targets['tb2']},
        rally_final_targets=targets, rally_dispatch_order=['tb2','tb1'],
        robot_positions={'tb1':(1.05,2.05),'tb2':(1.05,5.05)},
        map_data=grid, map_received_at=10., resolution=.1, origin=(0.,0.),
        robot_maps={n:dict(data=grid,resolution=.1,origin=(0.,0.)) for n in names},
        robot_map_received_at=dict.fromkeys(names,10.), robot_odom_received_at=dict.fromkeys(names,10.),
        robot_tf_received_at=dict.fromkeys(names,10.),
        battery_states={n:dict(energy=100.,charge_x=1.05,charge_y=2.05 if n=='tb1' else 5.05,
            mode='ACTIVE',move_cost_per_m=1.,idle_cost_per_sec=.02,return_path_factor=2.,
            nominal_speed_mps=.18,return_safety_margin=8.,charge_radius_m=.8,
            return_recovery_wait_sec=30.) for n in names},
        target=(8.05,3.05), detecting_robot='tb1', rally_hold_sec=5.,
        rally_wait_budgets_sec={}, rally_wait_budgets=dict.fromkeys(names,20.),
        rally_preflight_complete=True, rally_precharge_active=False, rally_hold_started_at=10.,
        now=lambda:clock[0], input_freshness_details=lambda:copy.deepcopy(inputs),
        fresh_robot_inputs=lambda:True, fresh_target=lambda:True,
        consumed_publisher=Mock(), publish_rally_assignments=Mock())
    return node,clock,inputs


@pytest.mark.parametrize('condition,released', [
    ('safe',True),('charging',False),('pending_charge',False),('unfinished_refuge',False),
    ('active_rally',False),('pending_rally',False),('active_frontier',False),('survey',False),
    ('stale_inputs',False),('stale_target',False),('missing_local',False),('missing_position',False),
    ('low_leader',False),('low_owner',False),('missing_wait',False),('invalid_wait',False),
    ('occupied_leader',False),('occupied_owner',False),('late_publication',False),
    ('expired_original_pose',False),('future_body_blocks_corridor',False),
    ('missing_final_owner',False),
    ('pending_frontier',False),('pending_scan',False),('accepted_scan',False),
])
def test_early_release_requires_funded_fresh_complete_serial_paths(condition,released):
    node,clock,inputs=refuge_node()
    if condition=='charging':node.battery_modes['tb2']='CHARGING'
    if condition=='pending_charge':node.rally_charge_requested['tb2']=10.
    if condition=='unfinished_refuge':node.rally_arrived['tb1']=False
    if condition=='active_rally':node.rally_goal_handles['tb1']=object()
    if condition=='pending_rally':node.rally_goal_pending['tb1']=True
    if condition=='active_frontier':node.goal_handles['tb2']=object()
    if condition=='pending_frontier':node.robot_states['tb2']='active'
    if condition=='pending_scan':node.target_scan_robot='tb2'
    if condition=='accepted_scan':node.target_scan_handle=object()
    if condition=='survey':node.survey_goal_pending=True
    if condition=='stale_inputs':node.fresh_robot_inputs=lambda:False
    if condition=='stale_target':node.fresh_target=lambda:False
    if condition=='missing_local':node.robot_maps.pop('tb2')
    if condition=='missing_position':node.robot_positions['tb2']=None
    if condition=='missing_final_owner':node.rally_final_targets.pop('tb2')
    if condition=='low_leader':node.battery_states['tb1']['energy']=1.
    if condition=='low_owner':node.battery_states['tb2']['energy']=1.
    if condition=='missing_wait':node.rally_wait_budgets.pop('tb2')
    if condition=='invalid_wait':node.rally_wait_budgets['tb2']=float('nan')
    if condition.startswith('occupied_'):
        robot='tb1' if condition=='occupied_leader' else 'tb2'
        raw=node.robot_maps[robot]['data'].copy();raw[control.world_to_grid(*node.robot_positions[robot],.1,0.,0.)]=100
        node.robot_maps[robot]={**node.robot_maps[robot],'data':raw}
    if condition=='late_publication':node.consumed_publisher.publish.side_effect=lambda message:clock.__setitem__(0,13.)
    if condition=='expired_original_pose':inputs['tb2/pose_state']['source_time']=8.
    if condition=='future_body_blocks_corridor':
        raw=np.full((100,100),-1,dtype=np.int16);raw[30:43,5:95]=0
        node.map_data=raw;node.robot_maps={n:dict(data=raw,resolution=.1,origin=(0.,0.)) for n in node.battery_modes}
        node.robot_positions={'tb1':(1.55,3.55),'tb2':(8.55,3.55)}
        node.rally_final_targets={'tb1':control.RallyPose(5.05,3.55,0.),'tb2':control.RallyPose(2.55,3.55,0.)}
    before=dict(node.rally_targets)
    prior_handles=dict(node.rally_goal_handles); prior_pending=dict(node.rally_goal_pending)
    control.HeadquartersControl.release_return_yields(node)
    assert ('tb1' not in node.return_yield_targets) is released
    assert node.publish_rally_assignments.called is released
    assert node.rally_goal_pending==prior_pending and node.rally_goal_handles==prior_handles
    if released:
        assert node.rally_targets['tb1']==node.rally_final_targets['tb1']
        assert not node.rally_arrived['tb1'] and not node.rally_yield_targets
        assert node.rally_dispatch_order==['tb1','tb2']
        assert not node.rally_preflight_complete and node.rally_precharge_active
        assert node.rally_hold_started_at is None
    else:
        assert node.rally_targets==before
        assert node.rally_arrived['tb1'] is (condition!='unfinished_refuge')


def test_original_release_when_owner_has_a_reserved_leg_stays_available():
    node,_,_=refuge_node();node.rally_goal_pending['tb2']=True
    node.fresh_robot_inputs=lambda:False
    control.HeadquartersControl.release_return_yields(node)
    assert not node.return_yield_targets and node.publish_rally_assignments.called
    assert not node.consumed_publisher.publish.called


def test_eligibility_reader_reconstructs_complete_routes_and_original_budget():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
    from p2c_refuge_release import audit_eligibility
    node,_,_=refuge_node();control.HeadquartersControl.release_return_yields(node)
    event=json.loads(node.consumed_publisher.publish.call_args.args[0].data)
    assert len(audit_eligibility(event))==2
    for mutation in ('expired','energy','future_body','route','charging','wait','owner_first'):
        changed=copy.deepcopy(event)
        if mutation=='expired':changed['inputs']['tb2/frame_state']['source_time']=0.
        if mutation=='energy':changed['required_energy']['tb2']-=1.
        if mutation=='future_body':changed['final_targets']['tb1'][:2]=changed['final_targets']['tb2'][:2]
        if mutation=='route':changed['routes']['tb2'][-1]=[8.,8.]
        if mutation=='charging':changed['battery_modes']['tb2']='CHARGING'
        if mutation=='wait':changed['wait_budgets_sec']['tb2']=-1.
        if mutation=='owner_first':changed['order'].reverse()
        with pytest.raises(AssertionError):audit_eligibility(changed)
