import base64
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zlib

import numpy as np
import pytest
from scipy.spatial import cKDTree

from multi_robot_exploration import control as c
from test_ap_return_consistency import original_input_fixture
from test_control import rally_budget_node


def scalar_reference():
    fixture = json.loads((Path(__file__).parent/'fixtures/p2c_v9_scalar_veto.json').read_text())
    assert hashlib.sha256(fixture['function'].encode()).hexdigest() == fixture['function_sha256']
    scope = dict(np=np, math=math, cKDTree=cKDTree, world_to_grid=c.world_to_grid,
                 RALLY_PATH_CLEARANCE_M=.35)
    exec(fixture['function'], scope)
    return scope['route_respects_known_obstacles']


@pytest.mark.parametrize('seed', range(8))
def test_vectorized_veto_matches_frozen_scalar_for_random_boundaries_and_escapes(seed):
    old = scalar_reference()
    rng = np.random.default_rng(20261008+seed)
    for _ in range(256):
        grid = rng.choice([-1, 0, 100], size=(24, 32), p=[.08, .90, .02]).astype(np.int16)
        resolution = rng.choice([.05, .1, .2])
        origin = tuple(rng.uniform(-2, 2, 2))
        points = rng.integers(-3, 36, size=(rng.integers(1, 9), 2)).astype(float)
        # Include exact cell borders, repeated points, outside space and half-cell centres.
        points += rng.choice([0., .5, np.nextafter(.5, 1.)])
        route = tuple(map(tuple, points*resolution+origin))
        assert c.route_respects_known_obstacles(grid, resolution, origin, route) == old(grid, resolution, origin, route)


def test_vectorized_veto_preserves_original_native_conflicting_map_decisions():
    e, maps = original_input_fixture()
    local, fused = maps['local'], maps['delivered_fused']
    distance, route = c.known_return_route(fused['data'], fused['resolution'], fused['origin'],
                                          e['position'], e['home'], .8, include_route=True)
    assert distance == pytest.approx(.8588835143127292)
    assert not scalar_reference()(local['data'], local['resolution'], local['origin'], route)
    assert not c.route_respects_known_obstacles(local['data'], local['resolution'], local['origin'], route)


def test_immutable_snapshot_reuses_geometry_but_cannot_mutate_or_change_geometry_silently():
    source = np.zeros((50, 100), dtype=np.int16)
    raw = c.immutable_grid_snapshot(source, source.shape)
    cache = {}
    args = (raw, .1, (0., 0.), (8.05, 2.05), .8, cache)
    with patch.object(c.hashlib, 'blake2b', wraps=hashlib.blake2b) as digest:
        first = c.charging_route_field(*args)
        assert c.charging_route_field(*args) is first
        assert digest.call_count == 1
    with pytest.raises(ValueError): raw.setflags(write=True)
    source[:,45] = 100
    assert np.all(raw == 0)
    second = c.immutable_grid_snapshot(source, source.shape)
    second_field = c.charging_route_field(second, *args[1:])
    assert second_field is not first
    assert c.charging_route_field(second, .1, (.01, 0.), (8.05, 2.05), .8, cache) is not second_field
    previous = cache['field']
    assert c.charging_route_field(second, .1, (.01, 0.), (8.05, 2.05), .7, cache) is not previous


@pytest.mark.parametrize('readonly_view', [False, True])
def test_mutable_or_readonly_view_of_mutable_map_invalidates_field_and_obstacle_cache(readonly_view):
    base = np.zeros((50, 100), dtype=np.int16)
    raw = base.view() if readonly_view else base
    if readonly_view: raw.setflags(write=False)
    cache = {}
    route = ((2.05, 2.05), (8.05, 2.05))
    first = c.charging_route_field(raw, .1, (0., 0.), (8.05, 2.05), .8, cache)
    assert c.route_respects_known_obstacles(raw, .1, (0., 0.), route, cache=cache)
    base[:,45] = 100
    assert c.charging_route_field(raw, .1, (0., 0.), (8.05, 2.05), .8, cache) is not first
    assert not c.route_respects_known_obstacles(raw, .1, (0., 0.), route, cache=cache)


def test_assignment_failure_audit_retains_supplied_delivered_inputs_and_rate_limits():
    node, _, _ = rally_budget_node()
    messages = []
    node.consumed_publisher = SimpleNamespace(publish=messages.append)
    node.input_freshness_details = lambda: {'headquarters/fused_map_snapshot': dict(source_time=11.)}
    node.source_map_data = node.map_data.copy()
    node.robot_map_received_at = {'tb1':10.5}
    node.target = (8.05, 1.05)
    node.enable_battery = True
    node.rally_assignment_objective = 'minimax'
    geometry = {'tb1':dict(data=node.map_data, resolution=node.resolution, origin=node.origin)}
    conditional_positions = {'tb1':(1.1, 1.2)}
    for _ in range(2):
        c.HeadquartersControl.record_rally_assignment_failure(node, conditional_positions, geometry, .123)
    assert len(messages) == 1
    e = json.loads(messages[0].data)
    assert e['event'] == 'coordinator_rally_assignment_failed'
    assert e['robot_positions']['tb1'] == [1.1, 1.2]
    assert e['current_positions']['tb1'] == list(node.robot_positions['tb1'])
    assert e['computation_wall_sec'] == .123
    assert e['return_maps']['tb1']['source_time'] == 10.5
    assert e['planning_map']['source'] == 'ap_delivered_planning_map'
    decoded = np.frombuffer(zlib.decompress(base64.b64decode(e['planning_map']['grid'])), dtype='<i2').reshape(e['planning_map']['shape'])
    np.testing.assert_array_equal(decoded, node.map_data)
