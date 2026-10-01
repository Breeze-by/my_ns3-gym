import pytest
import json
from pathlib import Path

from stage_p3b5_return_probe import owned_coordinator, known_staging_prefix


def process(root, pid, parent, domain, coordinator=False):
    directory = root / str(pid)
    directory.mkdir()
    (directory / 'stat').write_text(f'{pid} (python with spaces) S {parent} 0 0')
    (directory / 'cmdline').write_bytes(b'python\0' + (b'__node:=headquarters_control\0' if coordinator else b''))
    (directory / 'environ').write_bytes(f'ROS_DOMAIN_ID={domain}\0'.encode())


def test_fixture_signals_only_the_same_domain_owned_descendant(tmp_path):
    process(tmp_path, 10, 1, 180)
    process(tmp_path, 20, 10, 180)
    process(tmp_path, 30, 20, 180, True)
    process(tmp_path, 40, 1, 180, True)
    process(tmp_path, 50, 10, 181, True)
    assert owned_coordinator(10, '180', tmp_path) == 30
    with pytest.raises(RuntimeError):
        owned_coordinator(99, '180', tmp_path)
    process(tmp_path, 60, 20, 180, True)
    with pytest.raises(RuntimeError):
        owned_coordinator(10, '180', tmp_path)


def test_declared_staging_paths_have_full_navigation_clearance():
    import math
    import numpy as np
    from multi_robot_exploration.control import traversable_grid, has_known_line_of_sight, world_to_grid
    from multi_robot_exploration.task_evaluator import load_truth_grid
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / 'scripts/p3b5_staged_return_probe_manifest.json').read_text())
    truth = load_truth_grid(root / 'src/multi_robot/worlds/my_world.world')
    grid = np.where(traversable_grid(np.where(truth.occupied, 100, 0), truth.resolution), 0, 100)
    homes = {'tb1': (0., -.45), 'tb2': (0., .45)}
    cell = lambda p: world_to_grid(*p, truth.resolution, truth.origin_x, truth.origin_y)
    for name, pose in config['return_staging']['poses'].items():
        assert math.dist(homes[name], pose[:2]) >= 1.8
        assert has_known_line_of_sight(grid, cell(homes[name]), cell(pose[:2]))
    # Centerline-only visibility had accepted the original unsafe test points.
    assert not has_known_line_of_sight(grid, cell(homes['tb1']), cell((-2., -.45)))
    assert not has_known_line_of_sight(grid, cell(homes['tb2']), cell((2., .45)))


def test_staging_uses_known_visible_prefix_without_waiting_for_unknown_final_point():
    import math
    import numpy as np
    grid=np.zeros((30,50),dtype=int)
    grid[:,17:]=100
    waypoint=known_staging_prefix(grid,.1,(0.,0.),(1.,1.),(3.,1.))
    assert waypoint is not None and .5<=math.dist((1.,1.),waypoint)<=.75
    assert waypoint[0]<1.7 and waypoint[1]==1.
    # A known far endpoint does not allow crossing an unknown/occupied gap.
    grid[:,12]=100
    grid[:,17:]=0
    assert known_staging_prefix(grid,.1,(0.,0.),(1.,1.),(3.,1.)) is None
    assert known_staging_prefix(grid,.1,(0.,0.),(-1.,1.),(3.,1.)) is None
