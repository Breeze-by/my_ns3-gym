"""A grid-centre path must not propose an escape rejected at the actual pose."""
import gzip
import json
import math
from pathlib import Path

import numpy as np
import pytest

from multi_robot_exploration import control as c
from p2c_outbound_routes import decode
from p2c_return_preparation import audit_preparation
from test_exploration_return_preparation import node, advance_sources


def original_node():
    fixture = Path(__file__).with_name('fixtures')/'p2c_v54_refuge_input.json.gz'
    with gzip.open(fixture, 'rt') as stream:
        event = json.load(stream)['original_event']
    d = event['diagnostic_inputs']
    h, events, sent, requests = node()
    def geometry(s):
        a = decode(s)
        return dict(data=c.immutable_grid_snapshot(a, a.shape), resolution=s['resolution'], origin=s['origin'])
    planning = geometry(d['planning_map'])
    h.map_data = planning['data']; h.source_map_data = geometry(d['source_map'])['data']
    h.resolution = planning['resolution']; h.origin = planning['origin']
    h.map_received_at = d['planning_map']['source_time']; h.clock = event['planning_started_at_sec']
    h.map_self_return_cells = d['self_return_cells']
    h.robot_positions = d['robot_positions']; h.robot_states = d['robot_states']
    h.battery_states = d['battery_states']; h.battery_modes = d['battery_modes']
    h.robot_maps = {name: geometry(s) for name, s in d['return_maps'].items()}
    h.robot_map_received_at = {name: s['source_time'] for name, s in d['return_maps'].items()}
    for kind, stamps in [('pose_state', h.robot_odom_received_at), ('frame_state', h.robot_tf_received_at),
                         ('battery_state', h.battery_state_received_at)]:
        for name in h.robot_positions:
            stamps[name] = event['inputs_at_start'][name+'/'+kind]['source_time']
    return h, events, sent, requests


def test_original_default_geometry_reproduces_unadmittable_half_metre_refuge():
    h, _, sent, requests = original_node()
    protected = c.rally_return_reservations(h.map_data, h.resolution, h.origin, h.robot_positions,
        h.battery_states, h.battery_modes, {'tb2'}, {}, c.HeadquartersControl.delivered_return_maps(h))
    old = c.rally_yield_pose(h.map_data, h.resolution, h.origin, h.robot_positions['tb1'], (0., .45),
        blocked_positions=[h.robot_positions['tb2']], reserved_routes=tuple(protected.values()),
        route_separation_m=1.8, visible_only=True, local_map=h.robot_maps['tb1'])
    assert math.dist(h.robot_positions['tb1'], (old.x, old.y)) == pytest.approx(.48341256243793473)
    h.pending_exploration_return_yield = dict(robot='tb1', returning='tb2', refuge=old, task_phase='EXPLORE')
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert h.pending_exploration_return_yield is None and not sent and not requests


@pytest.mark.parametrize('shift', [(0., 0.), (.023, -.017), (-.025, .025)])
def test_original_complete_paths_and_energy_admit_the_next_actual_half_metre_escape(shift):
    h, events, sent, requests = original_node()
    h.origin = tuple(a+b for a, b in zip(h.origin, shift))
    h.robot_positions = {name: tuple(a+b for a, b in zip(p, shift)) for name, p in h.robot_positions.items()}
    for state in h.battery_states.values():
        state['charge_x'] += shift[0]; state['charge_y'] += shift[1]
    for geometry in h.robot_maps.values():
        geometry['origin'] = tuple(a+b for a, b in zip(geometry['origin'], shift))
    before = h.map_data.tobytes(), {name: g['data'].tobytes() for name, g in h.robot_maps.items()}
    assert c.HeadquartersControl.prepare_exploration_return(h, 'tb2')
    point = h.pending_exploration_return_yield['refuge']
    assert math.dist(h.robot_positions['tb1'], (point.x, point.y)) == pytest.approx(.5077995210232744)
    assert not sent and not requests
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert len(sent) == 1 and sent[0][0] == 'tb1' and not requests
    assert audit_preparation(events[-1]) == 'yield'
    assert h.exploration_return_yields['tb1']['clearance_m'] == 1.8
    assert h.exploration_return_yields['tb1']['required_energy'] < h.battery_states['tb1']['energy']
    assert before == (h.map_data.tobytes(), {name: g['data'].tobytes() for name, g in h.robot_maps.items()})


@pytest.mark.parametrize('condition', ['expired', 'future', 'occupied', 'unfunded'])
def test_better_geometry_keeps_original_live_admission_rejections(condition):
    h, _, sent, requests = original_node()
    c.HeadquartersControl.prepare_exploration_return(h, 'tb2')
    proposal = h.pending_exploration_return_yield
    if condition == 'expired': h.clock += 3.
    if condition == 'future': h.robot_tf_received_at['tb1'] = h.clock+1.
    if condition == 'occupied':
        grid = np.array(h.map_data)
        grid[c.world_to_grid(proposal['refuge'].x, proposal['refuge'].y, h.resolution, *h.origin)] = 100
        h.map_data = grid
    if condition == 'unfunded': h.battery_states['tb1']['energy'] = 1.
    c.HeadquartersControl.admit_exploration_return_yield(h)
    assert not sent and not requests


def test_expired_intent_waits_for_new_sources_then_admits_once():
    h, _, sent, requests = original_node()
    c.HeadquartersControl.prepare_exploration_return(h, 'tb2')
    h.clock += 3.
    assert c.HeadquartersControl.admit_exploration_return_yield(h) and not sent
    advance_sources(h, h.clock)
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert len(sent) == 1 and not requests and h.pending_exploration_return_yield is None
