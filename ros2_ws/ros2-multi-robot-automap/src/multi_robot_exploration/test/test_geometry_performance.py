"""Exact obstacle geometry and immutable-only return memoization."""
import math

import numpy as np
import pytest
from scipy import ndimage

from multi_robot_exploration import control


def disk_reference(grid, radius):
    offsets = np.arange(-radius, radius + 1)
    rows, columns = np.meshgrid(offsets, offsets, indexing='ij')
    return ndimage.binary_dilation(grid >= control.OCCUPIED_THRESHOLD,
        structure=rows * rows + columns * columns <= radius ** 2)


@pytest.mark.parametrize('seed', range(12))
def test_edt_keeps_every_disk_cell_on_random_rectangles_and_borders(seed):
    rng = np.random.default_rng(seed)
    for shape in ((1, 1), (1, 19), (21, 1), (7, 13), (61, 83)):
        for density in (0., .01, .2, 1.):
            grid = np.where(rng.random(shape) < density, 100, -1).astype(np.int16)
            for radius in (0, 1, 2, 3, 5, 7, 9, 13):
                assert np.array_equal(control.inflated_obstacle_mask(grid, radius),
                    disk_reference(grid, radius))


def test_exact_closed_disk_includes_pythagorean_boundary_and_excludes_next_cell():
    grid = np.zeros((35, 35), dtype=np.int16); grid[17, 17] = 50
    for radius, offset in ((5, (3, 4)), (13, (5, 12))):
        mask = control.inflated_obstacle_mask(grid, radius)
        assert mask[17 + offset[0], 17 + offset[1]]
        assert not mask[17 + offset[0], 18 + offset[1]]
        assert np.array_equal(mask, disk_reference(grid, radius))


def snapshot(grid):
    return control.immutable_grid_snapshot(grid, grid.shape)


def fixture():
    grid = np.zeros((50, 70), dtype=np.int16)
    grid[15:35, 33] = 100
    return snapshot(grid)


def query(grid, cache, position=(2.1, 4.1), home=(12.1, 4.1), radius=.8,
          origin=(0., 0.), local=None):
    return control.qualified_return_candidates(grid, .2, origin, position, home, radius, local, cache)


def test_same_immutable_sources_reuse_paths_without_exposing_mutable_result_rows(monkeypatch):
    grid = fixture(); cache = {}; calls = []
    original = control.known_return_route
    def traced(*args, **kwargs):
        calls.append(args[3]); return original(*args, **kwargs)
    monkeypatch.setattr(control, 'known_return_route', traced)
    expected = query(grid, None); calls.clear()
    first = query(grid, cache); assert first == expected and len(calls) == 1
    first[0]['qualified'] = False; first.append({'source': 'invented'})
    assert query(grid, cache) == expected and len(calls) == 1
    assert query(grid, cache, position=(2.3, 4.1)) == query(grid, None, position=(2.3, 4.1))


def test_caller_cannot_mutate_a_cached_route_through_a_list_position():
    grid = fixture(); cache = {}; position = [2.1, 4.1]
    first = query(grid, cache, position=position)
    expected = query(grid, None)
    first[0]['route'][0][0] = 4.
    assert query(grid, cache) == expected


@pytest.mark.parametrize('change', ['new_fused', 'new_local', 'origin', 'local_origin', 'home', 'radius'])
def test_all_consulted_geometry_invalidates_cached_qualification(change):
    grid = fixture(); local = dict(data=grid, resolution=.2, origin=(0., 0.)); cache = {}
    query(grid, cache, local=local); old = cache['qualified_paths']['results']
    kwargs = dict(local=local)
    if change == 'new_fused':
        changed = grid.copy(); changed[:, 40] = 100; grid = snapshot(changed)
    if change == 'new_local':
        changed = grid.copy(); changed[:, 40] = 100; kwargs['local'] = {**local, 'data': snapshot(changed)}
    if change == 'origin': kwargs['origin'] = (-.2, 0.)
    if change == 'local_origin': kwargs['local'] = {**local, 'origin': (-.2, 0.)}
    if change == 'home': kwargs['home'] = (11.1, 4.1)
    if change == 'radius': kwargs['radius'] = 1.
    assert query(grid, cache, **kwargs) == query(grid, None, **kwargs)
    assert cache['qualified_paths']['results'] is not old


@pytest.mark.parametrize('mutate_local', [False, True])
def test_writable_alias_cannot_reuse_an_old_qualification(mutate_local):
    frozen = fixture(); mutable = frozen.copy(); alias = mutable.view(); alias.flags.writeable = False
    grid = frozen if mutate_local else alias
    local = dict(data=alias, resolution=.2, origin=(0., 0.)) if mutate_local else None
    cache = {}; first = query(grid, cache, local=local)
    assert all(row['qualified'] for row in first)
    mutable[:, 40] = 100
    after = query(grid, cache, local=local)
    assert after == query(grid, None, local=local)
    assert not any(row['qualified'] for row in after)
    assert 'qualified_paths' not in cache


def test_geometry_memo_bound_and_new_source_without_local_veto():
    grid = fixture(); cache = {}; local = dict(data=grid, resolution=.2, origin=(0., 0.))
    query(grid, cache, local=local)
    assert query(grid, cache) == query(grid, None)
    for index in range(140):
        position = (2.1 + index * .001, 4.1)
        assert query(grid, cache, position=position) == query(grid, None, position=position)
        assert len(cache['qualified_paths']['results']) <= 128


def test_missing_and_nonfinite_position_preserves_unavailable_route():
    grid = fixture()
    for position in (None, (math.nan, 4.), (math.inf, 4.)):
        assert query(grid, {}, position=position) == query(grid, None, position=position)
