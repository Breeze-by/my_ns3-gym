"""Retained reverse-tree geometry must preserve every original route vertex."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from multi_robot_exploration import control as c


def reference():
    saved = json.loads((Path(__file__).parent / 'fixtures/p2c_v34_return_route_reference.json').read_text())
    assert hashlib.sha256(saved['function'].encode()).hexdigest() == saved['function_sha256']
    scope = dict(vars(c))
    exec(saved['function'], scope)
    return scope['known_return_route']


@pytest.mark.parametrize('seed', range(8))
def test_shared_suffixes_match_original_vertices_costs_and_missing_paths(seed):
    old = reference()
    rng = np.random.default_rng(20261009 + seed)
    raw = np.zeros((70, 120), dtype=np.int16)
    for _ in range(8):
        r, col = rng.integers([10, 20], [60, 90])
        raw[r:r+3, col:col+3] = rng.choice([-1, 100])
    raw = c.immutable_grid_snapshot(raw, raw.shape)
    resolution = (.05, .1, .2)[seed % 3]
    origin = (-2.15, -3.37)
    home = c.grid_to_world(35, 108, resolution, *origin)
    previous, current = {}, {}
    for row, col in rng.integers([0, 0], [70, 120], size=(96, 2)):
        point = c.grid_to_world(int(row), int(col), resolution, *origin)
        args = (raw, resolution, origin, point, home, .8)
        assert c.known_return_route(*args, cache=current, include_route=True) == old(
            *args, cache=previous, include_route=True)
        assert len(current.get('route_suffixes', {})) <= 2048
        assert all(len(shared) <= 2048 for shared, _ in current.get('route_suffixes', {}).values())


def test_neighboring_start_reuses_tail_without_skipping_any_safety_vertex(monkeypatch):
    raw = c.immutable_grid_snapshot(np.zeros((30, 120), dtype=np.int16), (30, 120))
    home, point = (10.05, 1.05), (1.05, 1.05)
    cache = {}
    c.known_return_route(raw, .1, (0., 0.), point, home, .8, cache, True)
    calls = []
    original = c.grid_to_world
    def counted(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(c, 'grid_to_world', counted)
    actual = c.known_return_route(raw, .1, (0., 0.), (1.15, 1.05), home, .8, cache, True)
    cached_calls = len(calls)
    calls.clear()
    expected = reference()(raw, .1, (0., 0.), (1.15, 1.05), home, .8, {}, True)
    assert actual == expected and len(expected[1]) > 70
    assert cached_calls < len(calls) / 8


def test_long_route_bounds_each_retained_shared_tail():
    raw = c.immutable_grid_snapshot(np.zeros((1, 2500), dtype=np.int16), (1, 2500))
    args = (raw, .05, (0., 0.), (.025, .025), (124.925, .025), .8)
    cache = {}
    actual = c.known_return_route(*args, cache=cache, include_route=True)
    assert actual == reference()(*args, cache={}, include_route=True)
    assert len(actual[1]) > 2048
    assert len(cache['route_suffixes']) <= 2048
    assert all(len(shared) <= 2048 for shared, _ in cache['route_suffixes'].values())


@pytest.mark.parametrize('readonly_alias', [False, True])
def test_mutated_source_and_changed_home_cannot_reuse_a_stale_suffix(readonly_alias):
    base = np.zeros((30, 120), dtype=np.int16)
    raw = base.view()
    if readonly_alias:
        raw.setflags(write=False)
    cache = {}
    args = (raw, .1, (0., 0.), (1.05, 1.05), (10.05, 1.05), .8)
    assert c.known_return_route(*args, cache=cache, include_route=True)[0] is not None
    prior = cache['field']
    base[:, 60] = 100
    assert c.known_return_route(*args, cache=cache, include_route=True) == (None, ())
    assert cache['field'] is not prior and not cache.get('route_suffixes')
    next_args = (raw, .1, (.01, 0.), (1.05, 1.05), (3.05, 1.05), .7)
    assert c.known_return_route(*next_args, cache=cache, include_route=True) == reference()(
        *next_args, cache={}, include_route=True)
