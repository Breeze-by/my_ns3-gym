"""Navigation peer envelopes retain their frozen geometry as command caps change."""
import hashlib
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from multi_robot_exploration import control, mr3_motion_safety
from multi_robot_exploration.peer_obstacles import body_points


ROOT = Path(__file__).resolve().parents[5]
READER = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
                 'report/assets/20261017_mr3_p2a0_v10/independent/'
                 'mr3_independent_control_phase_v1.py')
READER_SHA = '04cd7d079c16004b20320868943bcdac899da7646304d30cbad0804d1a6ee8d3'
assert hashlib.sha256(READER.read_bytes()).hexdigest() == READER_SHA
SPEC = importlib.util.spec_from_file_location('navigation_peer_original_reader', READER)
ORIGINAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORIGINAL)


@pytest.mark.parametrize('peers,expected_sha', [
    ([(.0035573180185501274, .8999927477116304, .20699999999999363),
      (.45169310917406413, .44819738839512113, .18099999999999739)],
     '77c65732d1c16d0a5f06cadbd2d4bac812027ee3dadb7e418fdf2ea727381193'),
    ([(-.0034901435528687484, -.8999930107189699, .2079999999999984),
      (.4481695114093964, -.4517619097019747, .18099999999999739)],
     'e6dfbe4bb9174a6d055c7db9b022d9c1a1846d62a5280257f10017a95799d00d'),
    ([(-.4516043348259083, -.44828683742219005, .2079999999999984),
      (-.44822526043443106, .45170659716568096, .20699999999999363)],
     'f2479d1e2667f662e89689f46216199d7feadeea2cc64de211c75c36b417aebe'),
])
def test_actual_cloud_replays_v14_counterexample_with_original_navigation_geometry(
        peers, expected_sha):
    # These relative positions/ages are the three exact selected-input clouds
    # at V14 peer_phase line5544; the original native FAIL is not relabelled.
    original = ORIGINAL.cloud_bytes(peers)
    assert hashlib.sha256(original).hexdigest() == expected_sha
    points = body_points(peers)
    assert points.shape == (len(original) // 12, 3)
    assert hashlib.sha256(points.tobytes()).hexdigest() == expected_sha


@pytest.mark.parametrize('age', [0., .2, .5])
def test_grid_and_cloud_use_the_same_original_age_dependent_navigation_disk(age):
    peers = [(0., 0., age)]
    original = np.zeros((81, 81), dtype=np.int16)
    original[0, 0], original[0, 1] = 100, -1
    resolution, origin = .025, (-1.0125, -1.0125)
    radius = .25 + .04 + .26 * (age + .55)
    expected = original.copy()
    for row in range(expected.shape[0]):
        for column in range(expected.shape[1]):
            x = origin[0] + (column + .5) * resolution
            y = origin[1] + (row + .5) * resolution
            if x * x + y * y <= radius * radius:
                expected[row, column] = 100
    result = control.grid_with_peers(original, resolution, origin, peers)
    assert np.array_equal(result, expected)
    assert original[40, 40] == 0 and original[0, 1] == -1
    assert hashlib.sha256(body_points(peers).tobytes()).digest() == hashlib.sha256(
        ORIGINAL.cloud_bytes(peers)).digest()


def test_changed_command_cap_cannot_shrink_navigation_grid(monkeypatch):
    # Load an isolated real control module so import-time aliases are exercised
    # without reloading or replacing the shared class/function objects.
    monkeypatch.setattr(mr3_motion_safety, 'COMMAND_SPEED_LIMIT', .07)
    name = 'navigation_peer_independent_command_cap_test'
    spec = importlib.util.spec_from_file_location(name, control.__file__)
    isolated = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, isolated)
    spec.loader.exec_module(isolated)
    original = np.zeros((81, 81), dtype=np.int16)
    expected = control.grid_with_peers(original, .025, (-1.0125, -1.0125), [(0., 0., .2)])
    actual = isolated.grid_with_peers(original, .025, (-1.0125, -1.0125), [(0., 0., .2)])
    assert np.array_equal(actual, expected)
    assert isolated.peer_safety_radius(.2) == .25 + .04 + .26 * (.2 + .55)
