"""Geodesic preference is conditional; complete body-safe budgets remain hard."""
import copy
import json
import math

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_exploration_charging import charge_node, assignment, install_candidates


def test_nominal_field_prices_actual_start_and_known_free_escape():
    grid=np.zeros((50,60),dtype=int);grid[:,20]=100;grid[35:45,20]=0
    position=(1.87,2.06);resolution=.1
    traversable=c.traversable_grid(grid,resolution,c.PATH_CLEARANCE_M)
    start,escape=c.navigation_start_route(grid,traversable,
        c.world_to_grid(*position,resolution,0.,0.),6)
    assert start is not None and len(escape)>1
    points=[c.grid_to_world(*cell,resolution,0.,0.) for cell in escape]
    offset=math.dist(position,points[0])+sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    field=c.exploration_distance_field(grid,traversable,resolution,(0.,0.),position)
    assert field[start]==pytest.approx(offset) and offset>0.
    target=(40,40)
    assert field[target]==pytest.approx(c.path_distance_grid(traversable,start)[target]*resolution+offset)
    grid[c.world_to_grid(*position,resolution,0.,0.)]=-1
    assert c.exploration_distance_field(grid,traversable,resolution,(0.,0.),position) is None


def test_relative_distance_uses_the_known_detour_not_euclidean_proximity():
    grid=np.zeros((80,80),dtype=int);grid[:,40]=100;grid[68:76,40]=0
    positions={'tb1':(7.1,8.1),'tb2':(11.1,2.1)};target=(9.1,8.1)
    mask=c.traversable_grid(grid,.2,c.PATH_CLEARANCE_M)
    fields={name:c.exploration_distance_field(grid,mask,.2,(0.,0.),p) for name,p in positions.items()}
    cell=c.world_to_grid(*target,.2,0.,0.)
    assert math.dist(positions['tb1'],target)<math.dist(positions['tb2'],target)
    assert fields['tb1'][cell]>fields['tb2'][cell]
    node,_,_,_=charge_node();node.enable_battery=False
    node.resolution=.2;node.robot_positions=positions
    goal=assignment(*target,distance=float(fields['tb1'][cell]))
    preference=c.HeadquartersControl.frontier_travel_preference(node,'tb1',goal,fields)
    assert 0.<preference['factor']<1. and set(preference['peers'])=={'tb2'}
    assert c.relative_travel_factor(goal.path_distance_m,[float('inf'),float('nan')])==1.


@pytest.mark.parametrize('peer_energy',[80.,10.])
def test_funded_peer_preference_reduces_redundant_cross_map_assignment(monkeypatch,peer_energy):
    node,requests,_,sent=charge_node()
    node.robot_positions={'tb1':(2.05,3.05),'tb2':(8.05,3.05)}
    node.robot_states['tb2']='active'
    node.battery_states['tb1']['energy']=80.;node.battery_states['tb2']['energy']=peer_energy
    east=assignment(9.05,3.05,distance=7.,utility=100.)
    west=assignment(2.05,5.05,distance=2.,utility=60.)
    install_candidates(monkeypatch,{'tb1':[east,west]})
    c.HeadquartersControl.assign_idle_robots(node)
    assert not requests and len(sent)==1
    assert sent[0][1].x==(west.x if peer_energy==80. else east.x)


def test_actual_body_detour_can_veto_a_nominally_funded_frontier(monkeypatch):
    node,requests,_,sent=charge_node();node.robot_positions['tb2']=(4.,3.)
    goal=assignment(distance=4.)
    nominal=c.HeadquartersControl.exploration_required_energy(node,'tb1',4.,(6.,3.))
    node.battery_states['tb1']['energy']=nominal+.01
    install_candidates(monkeypatch,{'tb1':[goal]})
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and len(requests)==1
    assert requests[0][1]['required_energy']>node.battery_states['tb1']['energy']


@pytest.mark.parametrize('frame',[9.,7.9,10.1,None])
def test_ap_budget_prices_both_original_pose_sources_and_rejects_invalid_tf(frame):
    node,_,_,_=charge_node();node.robot_tf_received_at={'tb1':frame,'tb2':10.}
    node.robot_odom_received_at['tb1']=9.8
    if frame==9.:
        assert c.HeadquartersControl.delivered_pose_age(node,'tb1')==1.
        now=c.HeadquartersControl.task_return_required_energy(node,'tb1',1.,(3.,3.))
        node.robot_tf_received_at['tb1']=9.8
        fresh=c.HeadquartersControl.task_return_required_energy(node,'tb1',1.,(3.,3.))
        assert now>fresh
    else:
        with pytest.raises(ValueError):c.HeadquartersControl.task_return_required_energy(node,'tb1',1.,(3.,3.))


def travel_event():
    node,_,_,_=charge_node();node.robot_positions={'tb1':(2.05,3.05),'tb2':(8.05,5.05)}
    node.robot_tf_received_at=dict.fromkeys(node.robot_positions,9.5)
    for state in node.battery_states.values():state.update(energy=80.,mode='ACTIVE',stamp_sec=10.)
    grid=node.map_data;mask=c.traversable_grid(grid,.1,c.PATH_CLEARANCE_M)
    fields={name:c.exploration_distance_field(grid,mask,.1,(0.,0.),p) for name,p in node.robot_positions.items()}
    target=(7.05,3.05);cell=c.world_to_grid(*target,.1,0.,0.)
    distance=float(fields['tb1'][cell]);goal=assignment(*target,distance=distance)
    f=c.HeadquartersControl.frontier_travel_preference(node,'tb1',goal,fields)
    blocked=[node.robot_positions['tb2']]
    planned=float(c.exploration_distance_field(grid,c.block_dynamic_positions(mask,.1,(0.,0.),blocked),
        .1,(0.,0.),node.robot_positions['tb1'])[cell])
    f.update(base_utility=100.,battery_factor=1.,adjusted_utility=100.*f['factor'],
        nominal_blocked_positions=[],blocked_positions=blocked,planned_distance_m=planned,
        required_energy=c.HeadquartersControl.exploration_required_energy(node,'tb1',planned,target))
    inputs={'headquarters/fused_map_snapshot':dict(source_time=10.,age_sec=0.)}
    for name in node.robot_positions:
        inputs.update({name+'/'+kind:dict(source_time=stamp,age_sec=10.-stamp)
            for kind,stamp in (('pose_state',10.),('frame_state',9.5),('battery_state',10.))})
    e=dict(event='coordinator_navigation_decision',kind='exploration',event_time=10.,robot='tb1',
        current_position=node.robot_positions['tb1'],robot_positions=node.robot_positions,
        battery_states=node.battery_states,travel_preference=f,inputs=inputs,return_maps={},self_return_cells={},
        planning_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_planning_map',10.,10.),
        source_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_fused_map',10.,10.))
    return json.loads(json.dumps(e))


@pytest.mark.parametrize('corruption',[None,'nominal','planned','peer_distance','peer_cost','factor',
    'utility','own_cost','insufficient_energy','future_tf','wrong_source','missing','blocked_body','map'])
def test_executed_frontier_audit_rejects_forged_travel_energy_and_sources(corruption):
    from check_p2c_gate import exploration_travel_audit
    e=copy.deepcopy(travel_event());f=e['travel_preference']
    if corruption=='nominal':f['own_nominal_distance_m']+=1.
    if corruption=='planned':f['planned_distance_m']-=1.
    if corruption=='peer_distance':f['peers']['tb2']['distance_m']-=1.
    if corruption=='peer_cost':f['peers']['tb2']['required_energy']-=1.
    if corruption=='factor':f['factor']=1.
    if corruption=='utility':f['adjusted_utility']+=1.
    if corruption=='own_cost':f['required_energy']-=1.
    if corruption=='insufficient_energy':e['battery_states']['tb1']['energy']=1.
    if corruption=='future_tf':e['inputs']['tb1/frame_state'].update(source_time=11.,age_sec=-1.)
    if corruption=='wrong_source':e['planning_map']['source']='native_hidden_map'
    if corruption=='missing':e.pop('travel_preference')
    if corruption=='blocked_body':f['blocked_positions']=[]
    if corruption=='map':e['source_map']['source_time']=9.
    if corruption is None:
        result=exploration_travel_audit([e],True)
        assert result['executed_frontier_witnesses']==result['relative_travel_discounts']==1
    else:
        with pytest.raises((AssertionError,KeyError)):exploration_travel_audit([e],True)
