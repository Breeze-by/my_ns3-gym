"""Frontier sampling stays exact; rectangle bounds never become real gains."""
import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from multi_robot_exploration import control
from test_exploration_resume import conditional_snapshot_node


@pytest.mark.parametrize('seed', range(12))
def test_deferred_viewpoint_geometry_bound_and_resolved_bids_match_original(seed):
    rng = np.random.default_rng(seed)
    grid = np.full((48, 71), -1, dtype=int)
    grid[7:-7, 7:-7] = 0
    for _ in range(5):
        row, col = rng.integers([12, 12], [36, 58])
        grid[row:row+2, col:col+2] = 100
    resolution = (.08, .1, .2)[seed % 3]
    origin = (-2., -3.)
    point = control.grid_to_world(24, 35, resolution, *origin)
    eager = control.prepare_frontier_data(grid, resolution)
    lazy = control.prepare_frontier_data(grid, resolution, defer_gain=True)
    assert eager[2] and set(eager[2]) == set(lazy[2])
    for group in eager[2]:
        assert len(eager[2][group]) == len(lazy[2][group])
        for actual, bound in zip(eager[2][group], lazy[2][group]):
            assert dataclasses.astuple(actual)[:5] == dataclasses.astuple(bound)[:5]
            assert actual.group_size == bound.group_size
            assert actual.information_gain <= bound.information_gain
    kwargs = dict(excluded_targets=[(point[0]+1., point[1])])
    old, _ = control.robot_candidate_assignments(grid, resolution, origin, 'tb1', point,
                                               frontier_data=eager, **kwargs)
    proposed, _ = control.robot_candidate_assignments(grid, resolution, origin, 'tb1', point,
                                                    frontier_data=lazy, **kwargs)
    cache = {}
    resolved = [control.resolve_frontier_gain(row[3], grid, resolution, cache)
                for row in proposed]
    resolved = [a for a in resolved if a is not None]
    assert resolved == [row[3] for row in old]
    ordered = list(control.lazy_priority_candidates(
        [row[3] for row in proposed],
        lambda a: control.resolve_frontier_gain(a, grid, resolution, cache),
        lambda a: a.utility, lambda a: a.utility))
    assert ordered == sorted(resolved, key=lambda a: -a.utility)
    assert all(type(a) is control.Assignment and type(a.viewpoint) is control.Viewpoint
               for a in ordered)


def mapping_snapshot_node():
    saved = json.loads((Path(__file__).parent / 'fixtures/p2c_v33_two_robot_computation.json').read_text())
    e = saved['event']; node, sent = conditional_snapshot_node(e, {})
    node.robot_states = {name: 'idle' for name in node.robot_states}
    node.enable_rally = True; node.initial_search_next = {}
    node.initial_search_visits = {}; node.initial_search_views = {}
    node.successful_exploration_legs = {}; node.target_search_visits = []
    node.exploration_travel_choices = {}; node.frontier_charge_lookahead = None
    return node, sent


def test_actual_delivered_map_admission_avoids_unused_mapping_rays(monkeypatch):
    node, sent = mapping_snapshot_node(); cells = []
    original = control.visible_unknown_gain
    def priced(*args, **kwargs):
        cells.append(args[1]); return original(*args, **kwargs)
    monkeypatch.setattr(control, 'visible_unknown_gain', priced)
    control.HeadquartersControl.assign_idle_robots(node)
    assert sent and len(cells) == len(set(cells))
    generated = sum(map(len, node.frontier_geometry_cache[1][2].values()))
    assert len(cells) < generated / 2
    assert all(type(a.viewpoint) is control.Viewpoint for _, a in sent)
    for name, assignment in sent:
        gain = original(node.map_data, (assignment.viewpoint.row, assignment.viewpoint.column),
                        control.INFORMATION_RADIUS_M / node.resolution)
        assert node.exploration_travel_choices[name]['information_gain'] == gain


def test_geometry_cache_is_not_reused_after_map_replacement(monkeypatch):
    node, sent = mapping_snapshot_node()
    control.HeadquartersControl.assign_idle_robots(node)
    stale = node.frontier_geometry_cache
    node.map_data = control.immutable_grid_snapshot(node.map_data, node.map_data.shape)
    node.robot_states = {name: 'idle' for name in node.robot_states}; node.goal_routes = {}
    calls = []; original = control.prepare_frontier_data
    def prepare(*args, **kwargs):
        calls.append(args[0]); return original(*args, **kwargs)
    monkeypatch.setattr(control, 'prepare_frontier_data', prepare)
    control.HeadquartersControl.assign_idle_robots(node)
    assert calls and all(grid is node.map_data for grid in calls)
    assert node.frontier_geometry_cache is not stale


def test_two_frontier_forecast_uses_same_exact_alternatives_with_deferred_pool():
    node, _ = mapping_snapshot_node(); name = 'tb1'
    kwargs = dict(raw_grid=node.map_data, resolution=node.resolution,
                  origin=node.origin, robot_name=name, robot_position=node.robot_positions[name])
    eager, _ = control.robot_candidate_assignments(**kwargs)
    lazy, _ = control.robot_candidate_assignments(**kwargs,
        frontier_data=control.prepare_frontier_data(node.map_data, node.resolution, defer_gain=True))
    first = max((row[3] for row in eager), key=lambda a: a.utility)
    node.frontier_charge_lookahead = (node.map_data, node.map_received_at,
                                    {name: [row[3] for row in eager]})
    expected = control.HeadquartersControl.frontier_lookahead_budget(node, name, first, 1., 80.)
    assert expected is not None
    cache = {}
    node.frontier_charge_lookahead = (node.map_data, node.map_received_at,
                                    {name: [row[3] for row in lazy]}, cache)
    actual = control.HeadquartersControl.frontier_lookahead_budget(node, name, first, 1., 80.)
    assert actual == expected
    assert cache and len(cache) < len(lazy)
