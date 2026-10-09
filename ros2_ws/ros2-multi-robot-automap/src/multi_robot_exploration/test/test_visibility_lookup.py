"""Compare every retained ray cell, integer gain and yaw with original math."""
import math

import numpy as np
import pytest

from multi_robot_exploration import control


def original_cells(grid, start, radius_cells, interest=None):
    row, column = start; height, width = grid.shape
    if not (0 <= row < height and 0 <= column < width) or grid[start] != 0:
        return np.empty(0, dtype=np.int64)
    radius = max(1, math.ceil(radius_cells))
    angles = np.linspace(0, 2 * math.pi, max(32, math.ceil(2 * math.pi * radius)), endpoint=False)
    steps = np.arange(.5, radius_cells + .25, .5)
    rows = np.rint(row + np.sin(angles)[:, None] * steps).astype(int)
    columns = np.rint(column + np.cos(angles)[:, None] * steps).astype(int)
    inside = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
    rows = np.clip(rows, 0, height - 1); columns = np.clip(columns, 0, width - 1)
    values = grid[rows, columns]
    visible = np.logical_and.accumulate(inside & ((values < control.OCCUPIED_THRESHOLD)
        if interest is None else values == 0), axis=1)
    informative = values < 0 if interest is None else interest[rows, columns]
    return np.unique((rows * width + columns)[visible & informative])


def original_view(grid, cell, radius, interest):
    cells = original_cells(grid, cell, radius, interest)
    if not cells.size: return 0, 0.
    rows, columns = np.unravel_index(cells, grid.shape)
    bearings = np.arctan2(rows - cell[0], columns - cell[1])
    yaws = np.arange(16) * 2. * math.pi / 16
    delta = np.arctan2(np.sin(bearings[:, None] - yaws), np.cos(bearings[:, None] - yaws))
    gains = np.count_nonzero(np.abs(delta) <= control.INITIAL_SEARCH_VIEW_FOV_RAD / 2., axis=0)
    best = int(np.argmax(gains))
    return int(gains[best]), float(yaws[best])


@pytest.mark.parametrize('seed', range(12))
def test_cells_counts_and_yaw_match_original_on_random_maps_and_edges(seed):
    rng = np.random.default_rng(seed)
    for shape in ((1, 19), (21, 1), (61, 83)):
        grid = rng.choice([-1, 0, 0, 0, 25, 50, 100], size=shape)
        interest = rng.random(shape) > .5
        starts = [(0, 0), (shape[0] - 1, shape[1] - 1), (shape[0] // 2, shape[1] // 2), (-1, 0)]
        for cell in starts:
            if cell[0] >= 0: grid[cell] = 0
            for radius in (.1, .5, 1., 2.5, 19.9999997, 20., 40.0000001):
                for mask in (None, interest):
                    expected = original_cells(grid, cell, radius, mask)
                    actual = control.visible_unknown_gain(grid, cell, radius, mask, return_cells=True)
                    assert actual.dtype == np.int64 and np.array_equal(actual, expected)
                    assert control.visible_unknown_gain(grid, cell, radius, mask) == len(expected)
                assert control.known_search_view(grid, cell, radius, interest) == original_view(grid, cell, radius, interest)


@pytest.mark.parametrize('radius', (1, 2, 5, 20, 40, 41))
def test_every_integer_sector_keeps_original_predicate_and_ties(radius):
    offsets = np.arange(-radius, radius + 1)
    rows, columns = np.meshgrid(offsets, offsets, indexing='ij')
    for fov in (math.pi / 2., math.pi / 3., math.pi):
        bearings = np.arctan2(rows.ravel(), columns.ravel())
        yaws = np.arange(16) * 2. * math.pi / 16
        delta = np.arctan2(np.sin(bearings[:, None] - yaws), np.cos(bearings[:, None] - yaws))
        expected = (np.abs(delta) <= fov / 2.).reshape((2 * radius + 1, 2 * radius + 1, 16))
        actual = control.known_search_sector_table(radius, fov)
        assert np.array_equal(actual, expected)
        assert control.immutable_grid(actual)


def test_unrounded_projections_preserve_translation_rounding_at_large_integer_cells():
    radius = 40.0000001
    dy, dx = control.visibility_ray_projections(radius)
    assert control.immutable_grid(dy) and control.immutable_grid(dx)
    angles = np.linspace(0., 2 * math.pi, math.ceil(2 * math.pi * math.ceil(radius)), endpoint=False)
    steps = np.arange(.5, radius + .25, .5)
    for coordinate in (0, 1, 2, 39, 40, 41, 1000, 1001, 1000000, 1000001):
        assert np.array_equal(np.rint(coordinate + dy), np.rint(coordinate + np.sin(angles)[:, None] * steps))
        assert np.array_equal(np.rint(coordinate + dx), np.rint(coordinate + np.cos(angles)[:, None] * steps))


def test_lookup_memory_is_bounded_and_arrays_cannot_be_reopened_for_write():
    for radius in range(1, 15):
        projections = control.visibility_ray_projections(float(radius))
        sectors = control.known_search_sector_table(radius, math.pi / 2.)
        for array in (*projections, sectors):
            with pytest.raises(ValueError): array.flags.writeable = True
    assert control.visibility_ray_projections.cache_info().currsize <= 8
    assert control.known_search_sector_table.cache_info().currsize <= 8
