import base64
import json
from pathlib import Path
import zlib

import numpy as np
import pytest

from multi_robot_exploration import control as c
from multi_robot_exploration.battery_manager import BatteryManager
from test_ap_return_consistency import original_input_fixture
from test_return_budget import manager


def delivered_fixture():
    event=json.loads((Path(__file__).parent/'fixtures/p2c_v10_delivered_corridors.json').read_text())['event']
    def decode(s):
        return dict(data=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape']),
                    resolution=s['resolution'],origin=tuple(s['origin']))
    return event,decode(event['planning_map']),decode(event['return_maps']['tb1'])


def test_all_33_original_delivered_endpoints_get_obstacle_respecting_alternatives():
    e,fused,local=delivered_fixture();state=e['battery_states']['tb1']
    home=(state['charge_x'],state['charge_y']);cache={};count=0
    for pose in c.rally_pose_candidates(fused['data'],fused['resolution'],fused['origin'],e['target']):
        rows=c.qualified_return_candidates(fused['data'],fused['resolution'],fused['origin'],
            (pose.x,pose.y),home,state['charge_radius_m'],local,cache)
        assert len(rows)==3
        assert not any(row['qualified'] for row in rows[:2])
        assert rows[2]['source']=='constrained_fused' and rows[2]['qualified']
        assert c.route_respects_known_obstacles(local['data'],local['resolution'],local['origin'],rows[2]['route'])
        count+=1
    assert count==33


def test_native_failed_v8_input_stays_unavailable_after_conservative_search():
    e,maps=original_input_fixture();fused,local=maps['delivered_fused'],maps['local']
    rows=c.qualified_return_candidates(fused['data'],fused['resolution'],fused['origin'],e['position'],e['home'],.8,local)
    assert len(rows)==3 and not any(row['qualified'] for row in rows)


def test_original_delivered_assignment_becomes_feasible_without_changing_any_budget_parameters():
    e,fused,_=delivered_fixture()
    maps={name:dict(data=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape']),
        resolution=s['resolution'],origin=s['origin']) for name,s in e['return_maps'].items()}
    assigned=c.assign_rally_poses(fused['data'],fused['resolution'],fused['origin'],e['robot_positions'],e['target'],
        objective=e['objective'],battery_states=e['battery_states'],observer_robot=e['observer_robot'],
        current_positions=e['current_positions'],hold_sec=e['hold_sec'],return_maps=maps)
    assert set(assigned)==set(e['robot_positions'])


def test_projection_preserves_unknown_and_both_sources_occupied_cells_with_offset_origins():
    fused=np.full((12,20),-1,dtype=np.int16);fused[2:10,2:18]=0;fused[3,3]=100
    local=np.full((10,12),-1,dtype=np.int16);local[4,4]=25;local[6,5]=100
    original_fused,original_local=fused.copy(),local.copy()
    geom=dict(data=local,resolution=.13,origin=(.27,.18));cache={}
    combined=c.constrained_return_grid(fused,.1,(0.,0.),geom,cache)
    assert combined[3,3]==100 and combined[0,0]==-1
    assert np.all(combined[7:9,7:9]==100)
    np.testing.assert_array_equal(fused,original_fused)
    np.testing.assert_array_equal(local,original_local)
    assert not np.any((fused<0) & (combined==0))
    previous=combined
    local[2,2]=100
    assert c.constrained_return_grid(fused,.1,(0.,0.),geom,cache) is not previous
    assert c.constrained_return_grid(fused,.1,(0.,0.),geom,cache)[4,5]==100
    with pytest.raises(ValueError):combined.setflags(write=True)


def test_native_selects_constrained_complete_route_and_prices_both_fresh_map_sources():
    e,fused,local=delivered_fixture();state=e['battery_states']['tb1']
    pose=c.rally_pose_candidates(fused['data'],fused['resolution'],fused['origin'],e['target'])[0]
    node,_,_=manager()
    node.map_position=(pose.x,pose.y);node.charge_x=state['charge_x'];node.charge_y=state['charge_y']
    node.return_map_source_time=9.
    node.return_map_candidates={'local':(local['data'],local['resolution'],local['origin'],8.,4,'local'),
        'delivered_fused':(fused['data'],fused['resolution'],fused['origin'],9.,5,'delivered_fused')}
    node.now=lambda:10.
    node.last_odom_time=9.9;node.map_tf_source_time=9.8
    result=BatteryManager.current_return_budget(node,True)
    assert result['map_source']=='constrained_fused'
    assert result['map_source_time']==8. and result['map_version']==5
    assert result['map_input_age_sec']==2.
    assert result['path_distance_m']==pytest.approx(8.821930140457622)
    assert len(node.return_candidate_audits)==3
    assert node.return_candidate_audits[-1]['qualified']


def test_stale_local_obstacles_are_not_combined_with_fresh_native_fused_map():
    e,fused,local=delivered_fixture();state=e['battery_states']['tb1']
    pose=c.rally_pose_candidates(fused['data'],fused['resolution'],fused['origin'],e['target'])[0]
    node,_,_=manager();node.map_position=(pose.x,pose.y)
    node.charge_x=state['charge_x'];node.charge_y=state['charge_y'];node.return_map_source_time=9.
    node.return_map_candidates={'local':(local['data'],local['resolution'],local['origin'],4.9,4,'local'),
        'delivered_fused':(fused['data'],fused['resolution'],fused['origin'],9.,5,'delivered_fused')}
    node.now=lambda:10.;node.last_odom_time=9.9;node.map_tf_source_time=9.8
    result=BatteryManager.current_return_budget(node,True)
    assert result['map_source']=='delivered_fused' and len(node.return_candidate_audits)==1
