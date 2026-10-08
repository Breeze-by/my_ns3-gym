import base64
import json
from pathlib import Path
import zlib

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_control import rally_budget_node


def original_input_fixture():
    e = json.loads((Path(__file__).parent/'fixtures/p2c_v8_conflicting_maps.json').read_text())['event']
    maps = {}
    for row in e['map_evidence']['route_candidates']:
        s = row['map_evidence']
        g = np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])), dtype='<i2').reshape(s['shape'])
        maps[s['source']] = dict(data=g, resolution=s['resolution'], origin=tuple(s['origin']))
    return e, maps


def test_central_rejects_a_fused_shortcut_vetoed_by_the_delivered_robot_map():
    e, maps = original_input_fixture()
    node, _, _ = rally_budget_node(energy=80.)
    fused, local = maps['delivered_fused'], maps['local']
    node.map_data, node.resolution, node.origin = fused['data'], fused['resolution'], fused['origin']
    node.battery_states['tb1'].update(charge_x=e['home'][0], charge_y=e['home'][1])
    old, _ = c.known_return_route(node.map_data, node.resolution, node.origin, e['position'], e['home'], .8)
    assert old == pytest.approx(.8588835143127292)
    node.robot_maps = {'tb1':local}
    node.robot_map_received_at = {'tb1':10.5}
    assert c.HeadquartersControl.known_home_distance(node, 'tb1', e['position']) is None
    candidates = c.qualified_return_candidates(node.map_data, node.resolution, node.origin,
        e['position'], e['home'], .8, local)
    assert not any(row['qualified'] for row in candidates)
    assert c.rally_return_reservations(node.map_data, node.resolution, node.origin,
        {'tb1':e['position']}, node.battery_states, {'tb1':'RETURNING'}, set(),
        return_maps=node.robot_maps) is None


@pytest.mark.parametrize('stamp', [5.9, 11.1])
def test_stale_or_future_robot_map_is_never_consulted(stamp):
    e, maps = original_input_fixture()
    node, _, _ = rally_budget_node()
    fused = maps['delivered_fused']
    node.map_data, node.resolution, node.origin = fused['data'], fused['resolution'], fused['origin']
    node.battery_states['tb1'].update(charge_x=e['home'][0], charge_y=e['home'][1])
    node.robot_maps = {'tb1':maps['local']}
    node.robot_map_received_at = {'tb1':stamp}
    assert c.HeadquartersControl.delivered_return_maps(node) == {}
    assert c.HeadquartersControl.known_home_distance(node, 'tb1', e['position']) == pytest.approx(.8588835143127292)


def test_fused_known_space_extends_unknown_but_never_a_local_hard_wall():
    fused = np.zeros((60, 100), dtype=np.int16)
    local = np.full_like(fused, -1)
    local[15:45, 5:30] = 0
    geometry = dict(data=local, resolution=.1, origin=(0., 0.))
    args = (fused, .1, (0., 0.), (2.05, 3.05), (8.05, 3.05), .8)
    assert any(row['qualified'] for row in c.qualified_return_candidates(*args, geometry))
    local[:, 45:48] = 100
    assert not any(row['qualified'] for row in c.qualified_return_candidates(*args, geometry))


def test_central_budget_prices_oldest_consulted_map_source():
    node, _, _ = rally_budget_node(energy=80.)
    geometry = dict(data=node.map_data.copy(), resolution=.1, origin=node.origin)
    node.robot_maps = {'tb1':geometry}
    node.robot_map_received_at = {'tb1':7.}
    old = c.HeadquartersControl.task_return_required_energy(node, 'tb1', 7., (8.05, 1.05))
    node.robot_map_received_at['tb1'] = 11.
    new = c.HeadquartersControl.task_return_required_energy(node, 'tb1', 7., (8.05, 1.05))
    assert old-new == pytest.approx(.02*4.)
