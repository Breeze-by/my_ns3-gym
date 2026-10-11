"""Original fragmented paths, preserved return reservations and legacy fallback."""
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
from multi_robot_exploration import control as c
from p2c_outbound_routes import check_route
from p2c_return_preparation import decode_grid

FIXTURE=json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v92_exploration_curves.json.gz','rt'))
ROWS=FIXTURE['rows']

def arguments(row):
    e=row['original_event'];f=e['travel_preference'];g=e['planning_map'];name=e['robot'];local=e['return_maps'][name]
    return (c.RallyPose(*f['target'],0.),decode_grid(g),g['resolution'],g['origin'],e['current_position']),dict(
        blocked_positions=f['blocked_positions'],local_map=dict(data=decode_grid(local),resolution=local['resolution'],origin=local['origin']))

def admitted(plans,row):
    for plan in plans:
        result=c.reserve_rally_prefix(plan,row['reservations'])
        if result is not None and math.dist(row['original_event']['current_position'],(result[0].x,result[0].y))>c.NAVIGATION_POSITION_TOLERANCE_M:
            return result
    return None

@pytest.mark.parametrize('row',ROWS,ids=lambda row:f"{row['robot']}_{row['time']:.1f}")
def test_original_curve_or_legacy_prefix_keeps_full_qualified_return(row):
    args,kwargs=arguments(row);plans=c.exploration_leg_plans(*args,curved=True,**kwargs);assert len(plans)==2
    result=admitted(plans,row);assert result is not None
    choice='curved' if row['plans']['curved']['goal'] is not None else 'straight';expected=row['plans'][choice]
    assert (result[0].x,result[0].y)==pytest.approx(expected['goal'][:2])
    e=row['original_event'];whole=(e['current_position'],*result[1]);name=e['robot'];grid=e['planning_map']
    check_route(grid,whole);check_route(e['return_maps'][name],whole,local=True)
    assert all(not c.routes_conflict(result[1],route) for route in row['reservations'])
    assert all(math.dist(point,body)>=c.PATH_CLEARANCE_M for point in result[1][1:] for body in kwargs['blocked_positions'])
    state=e['battery_states'][name];home=(state['charge_x'],state['charge_y'])
    candidates=c.qualified_return_candidates(args[1],args[2],args[3],(result[0].x,result[0].y),home,state['charge_radius_m'],kwargs['local_map'])
    assert any(candidate['qualified'] for candidate in candidates)
    assert expected['funded'] and expected['required_energy']<state['energy']
    assert math.dist(e['current_position'],(result[0].x,result[0].y))>=row['plans']['straight']['displacement_m']-1e-8

@pytest.mark.parametrize('row',ROWS,ids=lambda row:f"{row['robot']}_{row['time']:.1f}")
def test_default_policy_retains_exact_original_visible_plan(row):
    args,kwargs=arguments(row);plans=c.exploration_leg_plans(*args,**kwargs)
    old=c.plan_rally_leg(*args,c.MAX_NAVIGATION_LEG_M,clearance_m=c.PATH_CLEARANCE_M,visible_only=True,**kwargs)
    assert plans==(old,)
    result=admitted(plans,row);assert result is not None
    assert (result[0].x,result[0].y)==pytest.approx(row['original_event']['requested_position'])

def test_reservation_covering_start_rejects_both_options():
    row=ROWS[-1];args,kwargs=arguments(row);plans=c.exploration_leg_plans(*args,curved=True,**kwargs)
    blocked={**row,'reservations':[(tuple(args[-1]),)]}
    assert admitted(plans,blocked) is None

def test_shared_geometry_cache_does_not_modify_original_grids():
    args,kwargs=arguments(ROWS[-1]);cache={};before=[hashlib.sha256(grid.tobytes()).hexdigest() for grid in (args[1],kwargs['local_map']['data'])]
    plans=c.exploration_leg_plans(*args,curved=True,route_cache=cache,**kwargs)
    assert plans and 'field' in cache
    assert before==[hashlib.sha256(grid.tobytes()).hexdigest() for grid in (args[1],kwargs['local_map']['data'])]
