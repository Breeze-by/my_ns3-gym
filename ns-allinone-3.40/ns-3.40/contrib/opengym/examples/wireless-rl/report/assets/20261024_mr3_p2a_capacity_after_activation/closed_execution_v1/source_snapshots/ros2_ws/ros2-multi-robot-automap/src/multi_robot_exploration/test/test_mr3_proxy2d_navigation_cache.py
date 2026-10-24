"""Artificial received-grid equivalence checks; no World, Node or episode."""
import hashlib
from pathlib import Path
import subprocess
from types import ModuleType
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import mr3_proxy2d_navigation as navigation


BASELINE_FREEZE = "9b33cf9b6ab491fd5e3b15269adb30d43be1354c"
BASELINE_PATH = ("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/"
                 "multi_robot_exploration/mr3_proxy2d_navigation.py")
BASELINE_SHA256 = "40076b07ad7bced55bc8afa8a73c21a9ec4da9d50c42eff6121328db46e2cc88"


def baseline_module():
    """Execute the unchanged, SHA-bound V24 implementation as a CPU oracle."""
    root = Path(__file__).resolve().parents[5]
    raw = subprocess.check_output(["git", "show", BASELINE_FREEZE + ":" + BASELINE_PATH], cwd=root)
    assert hashlib.sha256(raw).hexdigest() == BASELINE_SHA256
    module = ModuleType("multi_robot_exploration._proxy2d_navigation_v24_reference")
    module.__package__ = "multi_robot_exploration"
    module.__file__ = BASELINE_FREEZE + ":" + BASELINE_PATH
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module


def artificial_map(sequence=0, *, size=32):
    values = np.full((size, size), -1, dtype=np.int16)
    values[2:-2, 2:-2] = 0
    return {"grid": values, "resolution": .1, "origin": (-size / 20, -size / 20),
            "payload_sha256": hashlib.sha256(str(sequence).encode()).hexdigest()}


def assert_field_equal(current, expected, name):
    assert current.blocked_quanta == expected.blocked_quanta
    if name in expected.paths:
        np.testing.assert_array_equal(current.paths[name][1], expected.paths[name][1])
        np.testing.assert_array_equal(current.paths[name][2], expected.paths[name][2])


@pytest.fixture(scope="module")
def reference():
    return baseline_module()


def test_stamp_only_changes_reuse_exact_field_and_match_frozen_baseline(reference):
    current, expected = navigation.ProxyNavigator(), reference.ProxyNavigator()
    state, goal = {"x": -.5, "y": -.5, "yaw": .2}, {"x": .8, "y": .7}
    original_new, original_old = navigation._path_distances, reference._path_distances
    with patch.object(navigation, "_path_distances", wraps=original_new) as new_build, \
            patch.object(reference, "_path_distances", wraps=original_old) as old_build:
        for sequence in range(12):
            received = artificial_map(sequence)
            assert current.target_velocity("tb1", state, goal, received) == expected.target_velocity(
                "tb1", state, goal, received)
            assert_field_equal(current, expected, "tb1")
        assert new_build.call_count == 1
        assert old_build.call_count == 12


@pytest.mark.parametrize("change", ["cell", "resolution", "origin", "dtype", "shape", "goal"])
def test_all_geometric_inputs_invalidate_even_a_reused_payload_id(reference, change):
    current, expected = navigation.ProxyNavigator(), reference.ProxyNavigator()
    received = artificial_map()
    state, goal = {"x": -.5, "y": -.5, "yaw": .2}, {"x": .8, "y": .7}
    assert current.target_velocity("tb1", state, goal, received) == expected.target_velocity(
        "tb1", state, goal, received)
    if change == "cell": received["grid"][16, 16] = 100
    elif change == "resolution": received["resolution"] = .09
    elif change == "origin": received["origin"] = (-1.7, -1.7)
    elif change == "dtype": received["grid"] = received["grid"].astype(np.int8)
    elif change == "shape": received["grid"] = received["grid"].reshape(16, 64)
    else: goal = {"x": .5, "y": .9}
    expected.paths.clear()  # Independent original kernels, never the new key.
    with patch.object(navigation, "_path_distances", wraps=navigation._path_distances) as build:
        assert current.target_velocity("tb1", state, goal, received) == expected.target_velocity(
            "tb1", state, goal, received)
        assert build.call_count == 1
    assert_field_equal(current, expected, "tb1")


def test_noncontiguous_equal_values_keep_the_same_c_order_geometry(reference):
    current, expected = navigation.ProxyNavigator(), reference.ProxyNavigator()
    received = artificial_map()
    state, goal = {"x": -.5, "y": -.5, "yaw": .2}, {"x": .8, "y": .7}
    current.target_velocity("tb1", state, goal, received)
    received["grid"] = np.asfortranarray(received["grid"])
    assert not received["grid"].flags.c_contiguous
    received["payload_sha256"] = "b" * 64
    with patch.object(navigation, "_path_distances", wraps=navigation._path_distances) as build:
        assert current.target_velocity("tb1", state, goal, received) == expected.target_velocity(
            "tb1", state, goal, received)
        assert build.call_count == 0
    assert_field_equal(current, expected, "tb1")


@pytest.mark.parametrize("topology", ["open", "wall", "corner", "unknown", "outside", "arrival"])
def test_commands_and_blocked_counts_match_full_original_replanning(reference, topology):
    current, expected = navigation.ProxyNavigator(), reference.ProxyNavigator()
    received = artificial_map()
    state, goal = {"x": -.5, "y": -.5, "yaw": .2}, {"x": .8, "y": .7}
    if topology == "wall": received["grid"][15:18, :] = 100
    elif topology == "corner": received["grid"][14:18, 17:] = 100
    elif topology == "unknown": received["grid"][15:18, :] = -1
    elif topology == "outside": state["x"] = -5.
    elif topology == "arrival": goal = {"x": -.4, "y": -.4}
    for sequence in range(3):
        received["payload_sha256"] = hashlib.sha256(str(sequence).encode()).hexdigest()
        expected.paths.clear()
        assert current.target_velocity("tb1", state, goal, received) == expected.target_velocity(
            "tb1", state, goal, received)
        assert_field_equal(current, expected, "tb1")


@pytest.mark.parametrize("digest", [None, 17, "", "a" * 63, "a" * 65])
def test_original_payload_identity_rejection_is_preserved(reference, digest):
    state, goal = {"x": -.5, "y": -.5, "yaw": 0.}, {"x": .8, "y": .7}
    received = artificial_map()
    received["payload_sha256"] = digest
    for implementation in (navigation, reference):
        with pytest.raises(ValueError, match="content identity"):
            implementation.ProxyNavigator().target_velocity("tb1", state, goal, received)


def test_no_goal_and_arrival_still_return_before_map_validation(reference):
    for implementation in (navigation, reference):
        nav = implementation.ProxyNavigator()
        state = {"x": 0., "y": 0., "yaw": 0.}
        assert nav.target_velocity("tb1", state, None, {}) == ((0., 0.), False)
        assert nav.target_velocity("tb1", state, {"x": .01, "y": .01}, {}) == ((0., 0.), True)


def test_local_scan_pair_safety_and_bounded_robot_cache_remain_live(reference):
    current, expected = navigation.ProxyNavigator(), reference.ProxyNavigator()
    states = {name: {"x": index * .7 - .7, "y": 0., "yaw": 0., "source_stamp": .1}
              for index, name in enumerate(navigation.ROBOTS)}
    goals = {name: {"x": .9, "y": 0.} for name in navigation.ROBOTS}
    maps = {name: artificial_map() for name in navigation.ROBOTS}
    scans = {name: {"angles": np.array([-.2, 0., .2]), "ranges": np.array([3., 3., 3.])}
             for name in navigation.ROBOTS}
    for sequence in range(6):
        for name in navigation.ROBOTS:
            maps[name]["payload_sha256"] = hashlib.sha256(str(sequence).encode()).hexdigest()
        if sequence == 2: scans["tb1"]["ranges"][:] = .2
        if sequence == 3: states["tb2"]["x"] = -.65
        now = .1 if sequence < 4 else .4  # Current source age still gates motion.
        expected.paths.clear()
        outputs = current.commands(states, goals, maps, scans, now)
        assert outputs == expected.commands(states, goals, maps, scans, now)
        if sequence == 0:
            assert outputs[0]["tb1"][0] > 0.  # A clear, fresh scan really permits forward motion.
        elif sequence == 2:
            assert outputs[0]["tb1"][0] == 0.  # New local range stops the cached path.
        elif sequence == 3:
            assert outputs[0]["tb1"] == outputs[0]["tb2"] == (0., 0.)  # Current pair separation.
        elif sequence >= 4:
            assert all(value == (0., 0.) for value in outputs[0].values())  # Current source ages.
        assert current.blocked_quanta == expected.blocked_quanta
        assert len(current.paths) <= 3
        for name in expected.paths:
            assert_field_equal(current, expected, name)
