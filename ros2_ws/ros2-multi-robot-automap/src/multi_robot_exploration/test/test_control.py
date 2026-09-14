import numpy as np

from multi_robot_exploration import control


def test_frontier_group_uses_an_alternative_to_last_target():
    control.VISITED.clear()
    control.BAD_TARGETS.clear()
    grid = np.zeros((30, 30), dtype=int)
    group = [(10, column) for column in range(5, 25)]
    last_target = control.grid_to_world(10, 15, 0.1, 0.0, 0.0)

    target = control.findClosestGroup(
        grid,
        [(1, group)],
        current=(10, 10),
        resolution=0.1,
        originX=0.0,
        originY=0.0,
        last_target=last_target,
    )

    assert target is not None
    assert np.linalg.norm(np.subtract(target, last_target)) >= 0.8
