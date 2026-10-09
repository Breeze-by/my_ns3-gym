"""Deferred camera/known-space scores resolve to the old exact gain and yaw."""
import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_exploration_resume import conditional_snapshot_node


@pytest.mark.parametrize('seed', range(8))
@pytest.mark.parametrize('camera', [False, True])
def test_all_resolved_candidates_and_stable_order_match_eager(seed, camera):
    grid = np.full((55, 79), -1, dtype=np.int16)
    grid[5:-5, 5:-5] = 0
    rng = np.random.default_rng(seed + 3901)
    for _ in range(5):
        r, col = rng.integers([10, 10], [40, 60])
        grid[r:r+2, col:col+2] = 100
    resolution = (.08, .1, .2)[seed % 3]
    origin = (-2., -3.)
    position = c.grid_to_world(25, 35, resolution, *origin)
    kwargs = dict(visited=[position], face_interest=camera,
        camera_views=[dict(position=position, yaw=seed * .31)] if camera else None)
    args = (grid, resolution, origin, 'tb1', position)
    eager = c.known_space_search_candidates(*args, gain_cache={}, **kwargs)
    cache = {}
    deferred = c.known_space_search_candidates(*args, gain_cache=cache, defer_gain=True, **kwargs)
    actual = [c.resolve_search_gain(row[3], grid, resolution, cache) for row in deferred]
    assert [a for a in actual if a is not None] == [row[3] for row in eager]
    ordered = list(c.lazy_priority_candidates([row[3] for row in deferred],
        lambda a: c.resolve_search_gain(a, grid, resolution, cache),
        lambda a: a.utility, lambda a: a.utility))
    assert ordered == sorted((row[3] for row in eager), key=lambda a: -a.utility)
    assert all(type(a) is c.Assignment and type(a.viewpoint) is c.Viewpoint for a in ordered)


def late_visual_node():
    saved = json.loads((Path(__file__).parent / 'fixtures/p2c_v31_visual_computation.json').read_text())
    e = saved['event']
    node, sent = conditional_snapshot_node(e, {})
    node.input_robot_names = lambda: e['travel_preference']['eligible_robot_names']
    node.robot_maps.setdefault('tb1', None)
    node.robot_states = {name: 'idle' for name in node.robot_states}
    node.enable_rally = True
    node.initial_search_next = {e['robot']: True}
    node.rally_charge_requested = {'tb1': e['event_time']}
    node.initial_search_visits = {i: v for i, v in enumerate(e['travel_preference']['initial_search_visits'])}
    node.initial_search_views = {i: v for i, v in enumerate(e['travel_preference']['initial_search_views'])}
    node.successful_exploration_legs = {e['robot']: 1}
    node.target_search_visits = []
    node.exploration_travel_choices = {}
    node.frontier_charge_lookahead = None
    return node, sent


def test_saved_visual_admission_resolves_exact_yaw_and_does_not_execute_bounds(monkeypatch):
    node, sent = late_visual_node()
    calls = []
    original = c.known_search_view
    def compute(*args):
        calls.append(args[1])
        return original(*args)
    monkeypatch.setattr(c, 'known_search_view', compute)
    c.HeadquartersControl.assign_idle_robots(node)
    assert sent and len(calls) < 79
    history = list(node.initial_search_views.values())
    interest = c.camera_search_interest(node.map_data, node.resolution, node.origin, history)
    for _, a in sent:
        gain, yaw = original(node.map_data, (a.viewpoint.row, a.viewpoint.column),
                             c.INFORMATION_RADIUS_M / node.resolution, interest)
        assert type(a) is c.Assignment and type(a.viewpoint) is c.Viewpoint
        assert a.viewpoint.information_gain == gain and a.navigation_yaw == yaw


def test_zero_visibility_still_returns_empty_for_frontier_fallback():
    grid = np.full((50, 80), -1, dtype=np.int16)
    grid[20:30, 20:30] = 0
    # No current known cell remains interesting after the explicit history.
    views = [dict(position=(2.5, 2.5), yaw=i * np.pi / 8) for i in range(16)]
    kwargs = dict(face_interest=True, camera_views=views)
    for deferred in (False, True):
        assert not c.known_space_search_candidates(grid, .1, (0., 0.), 'tb1',
            (2.5, 2.5), [], gain_cache={}, defer_gain=deferred, **kwargs)
