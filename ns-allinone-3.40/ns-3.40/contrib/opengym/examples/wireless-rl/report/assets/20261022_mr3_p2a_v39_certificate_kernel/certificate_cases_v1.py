"""Fixed artificial inputs for V39; no scene, sensor, World or episode data."""

from fractions import Fraction as Q
import random

import numpy as np


def random_case(sample, *, seed=3800, density=.3):
    rng = random.Random(seed + sample)
    grid = np.zeros((9, 11), np.int16)
    for row in range(grid.shape[0]):
        for col in range(grid.shape[1]):
            if rng.random() < density:
                grid[row, col] = rng.choice((-1, 1, 25, 100))
    start = (Q(rng.randint(-400, 400), 1000), Q(rng.randint(-400, 400), 1000))
    end = start if sample % 3 == 0 else (
        Q(rng.randint(-500, 500), 1000), Q(rng.randint(-500, 500), 1000))
    return grid, Q(1, 5), (-Q(11, 10), -Q(9, 10)), start, end


def segment_cases():
    result = []
    pairs = [
        ((0, 0), (0, 0)), ((0, 0), (Q(1, 10), Q(1, 10))),
        ((Q(1, 1000), -Q(1, 1000)), (Q(2, 1000), Q(3, 1000))),
        ((Q(1, 10**30), 0), (0, Q(1, 10**30))),
        ((-10, -10), (-9, -9)), ((-10, -10), (10, 10)),
        ((Q(7, 2), 0), (Q(7, 2), 0)), ((0, 0), (7, 0)),
    ]
    for index, (start, end) in enumerate(pairs):
        grid = np.zeros((7, 7), np.int8)
        grid[1, 2], grid[3, 4], grid[5, 5] = -1, 100, 1
        result.append((f"adversarial-{index}",
            (grid, 1, (-Q(7, 2), -Q(7, 2)), start, end)))
    for index, delta in enumerate((Q(0), Q(1, 10**30), -Q(1, 10**30))):
        grid = np.zeros((7, 7), np.int8)
        grid[3, 4] = 100
        point = (Q(21, 100) + delta, Q(0))
        result.append((f"threshold-{index}",
            (grid, 1, (-Q(7, 2), -Q(7, 2)), point, point)))
    for sample in range(16):
        result.append((f"fixed-random-{sample}", random_case(sample)))
    return result


def seed_cases():
    result = []
    for gate in (True, False):
        for value in (-1, 0, 1, 100):
            grid = np.zeros((7, 7), np.int8)
            grid[3, 3], grid[3, 4] = value, 100
            result.append((f"gate-{gate}-value-{value}",
                (grid, .5, (-1.75, -1.75), (-.2, 0.), (3, 3)), gate))
    for index, delta in enumerate((Q(0), Q(1, 10**30), -Q(1, 10**30))):
        grid = np.zeros((7, 7), np.int8)
        grid[3, 4] = 100
        result.append((f"threshold-{index}",
            (grid, 1, (-Q(7, 2), -Q(7, 2)), (Q(21, 100) + delta, 0), (3, 3)), True))
    grid = np.zeros((5, 5), np.int8)
    grid[1, 3] = 100
    result.append(("unsafe-bridge-interior", (grid, Q(43, 100),
        (-Q(43, 40), -Q(43, 40)), (Q(43, 250), Q(43, 500)), (2, 2)), True))
    for sample in range(16):
        grid, res, origin, start, _ = random_case(sample)
        # Exact rational floor, independent of either kernel under test.
        col = (start[0] - origin[0]) // res
        row = (start[1] - origin[1]) // res
        result.append((f"fixed-random-{sample}",
            (grid, res, origin, start, (row, col)), True))
    for name, point, cell in (
        ("outside-map", (-1, 0), (-1, 0)),
        ("near-exterior", (Q(1, 100), Q(1, 2)), (0, 0)),
        ("wrong-original-cell", (Q(9, 2), Q(7, 2)), (3, 3)),
    ):
        result.append((name, (np.zeros((7, 7), np.int8), 1, (0, 0), point, cell), True))
    return result
