"""Explicit seed-bridge execution fixtures; no World, Node or real consumer."""

from fractions import Fraction as Q
import hashlib
import math
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import mr3_proxy2d_navigation as navigation
from multi_robot_exploration.mr3_observation import native_traversable
from multi_robot_exploration.mr3_seed_certificate import (
    certify_estimated_segment, certify_seed_pose_bridge,
)


EXACT = "exact-point-bridge-v1"


def received(grid, resolution, origin):
    return {"grid": grid, "resolution": resolution, "origin": origin,
            "payload_sha256": hashlib.sha256(grid.tobytes()).hexdigest()}


def positive_case(yaw=math.pi / 2):
    grid = np.zeros((41, 41), dtype=np.int8)
    grid[23, 26] = 100
    data = received(grid, .05, (-1.025, -1.025))
    _, clearance = native_traversable(grid, .05)
    offset = clearance[20, 20] - math.sqrt(.08)
    state = {"x": 0., "y": -offset, "yaw": yaw, "source_stamp": 1.}
    return data, state, {"x": 0., "y": -.6}


def cache(nav, data, goal, *, field=None, clearance_override=None):
    """Supply a fixed artificial graph field while retaining actual cell gates."""
    grid, res, origin = data["grid"], data["resolution"], data["origin"]
    traversable, clearance = native_traversable(grid, float(res))
    if field is None:
        field = np.full(grid.shape, np.inf)
        field[traversable] = 1.
    if clearance_override is not None:
        clearance = clearance.copy()
        for cell, value in clearance_override.items():
            clearance[cell] = value
    key = (grid.dtype.str, grid.shape, grid.tobytes(order="C"), res,
           tuple(origin), goal["x"], goal["y"])
    value = (key, traversable, field)
    if nav.seed_rule != "legacy":
        value += (clearance,)
    nav.paths["tb1"] = value
    return traversable, clearance


def corner_case():
    grid = np.zeros((9, 9), dtype=np.int8)
    grid[3, 5] = 100
    data = received(grid, Q(43, 100), (-Q(387, 200), -Q(387, 200)))
    # Exact point at distance .29 from the closed obstacle's upper-left corner.
    x, y = Q(43, 200) - Q(58, 425), -Q(43, 200) + Q(87, 340)
    heading = math.atan2(-float(y), -float(x))
    state = {"x": x, "y": y, "yaw": heading, "source_stamp": 1.}
    return data, state, {"x": Q(129, 100), "y": -Q(43, 100)}


def test_seed_rule_is_explicit_and_legacy_remains_default():
    assert navigation.ProxyNavigator().seed_rule == "legacy"
    assert navigation.ProxyNavigator(seed_rule=EXACT).seed_rule == EXACT
    with pytest.raises(ValueError, match="seed rule"):
        navigation.ProxyNavigator(seed_rule="invented")


def test_false_negative_pose_bound_can_start_only_toward_same_seed_centre():
    data, state, goal = positive_case()
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        output, done = nav.target_velocity("tb1", state, goal, data)
    assert not done and output == (.12, 0.)
    assert proposal.call_count == 1
    start, end = proposal.call_args.args[3:]
    assert start == (state["x"], state["y"])
    assert end[1] > state["y"]  # Seed centre is above; the actual goal is below.
    assert math.dist(start, end) <= math.dist(start, (0., 0.))
    assert nav.blocked_quanta["tb1"] == 0


def test_fallback_misalignment_rotates_in_place_without_translating():
    data, state, goal = positive_case(yaw=0.)
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        assert nav.target_velocity("tb1", state, goal, data) == ((0., .6), False)
    proposal.assert_not_called()


@pytest.mark.parametrize("heading_error", [-.05, .05])
def test_aligned_fallback_certifies_the_proposed_straight_motion_not_an_arc(heading_error):
    data, state, goal = positive_case(yaw=math.pi / 2 + heading_error)
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        output, _ = nav.target_velocity("tb1", state, goal, data)
    assert output == (.12, 0.)
    _, end = proposal.call_args.args[3:]
    straight = (state["x"] + .12 * .02 * math.cos(state["yaw"]),
                state["y"] + .12 * .02 * math.sin(state["yaw"]))
    assert end == straight
    angular = -2 * heading_error  # The old simultaneous-turn controller's arc.
    curved = (state["x"] + .12 / angular * (math.sin(state["yaw"] + angular * .02) - math.sin(state["yaw"])),
              state["y"] - .12 / angular * (math.cos(state["yaw"] + angular * .02) - math.cos(state["yaw"])))
    assert math.dist(end, curved) > 1e-7


def test_angle_tolerance_does_not_authorize_a_geometrically_unsafe_step():
    data, state, goal = corner_case()
    seed = (4, 4)
    assert certify_seed_pose_bridge(data["grid"], data["resolution"], data["origin"],
        (state["x"], state["y"]), seed, seed_cell_traversable=True)["accepted"]
    state["yaw"] += .05  # Inside alignment tolerance, but points toward the corner.
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    traversable, _ = cache(nav, data, goal)
    assert traversable[seed]
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    assert proposal.call_count == 1 and nav.blocked_quanta["tb1"] == 1
    assert not certify_estimated_segment(*proposal.call_args.args)["accepted"]


def test_five_cell_lookahead_cutting_a_corner_is_not_borrowed_from_seed_bridge():
    data, state, goal = corner_case()
    field = np.full(data["grid"].shape, np.inf)
    route = [(4, 4), (5, 4), (5, 5), (5, 6), (5, 7), (4, 7), (3, 7)]
    for index, cell in enumerate(route):
        field[cell] = len(route) - index - 1
    legacy = navigation.ProxyNavigator()
    exact = navigation.ProxyNavigator(seed_rule=EXACT)
    for nav in (legacy, exact):
        traversable, _ = cache(nav, data, goal, field=field)
        assert all(traversable[cell] for cell in route)
    original_atan2 = math.atan2
    with patch.object(navigation.math, "atan2", wraps=original_atan2) as angles:
        legacy.target_velocity("tb1", state, goal, data)
    dy, dx = angles.call_args_list[0].args
    old_waypoint = (float(state["x"]) + dx, float(state["y"]) + dy)
    assert not certify_estimated_segment(data["grid"], data["resolution"], data["origin"],
        (state["x"], state["y"]), old_waypoint)["accepted"]
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        output, done = exact.target_velocity("tb1", state, goal, data)
    assert not done and output == (.12, 0.)
    _, endpoint = proposal.call_args.args[3:]
    assert math.dist(tuple(map(float, endpoint)), old_waypoint) > .5


def test_bridge_interior_failure_stops_even_when_current_point_and_original_cell_pass():
    grid = np.zeros((9, 9), dtype=np.int8)
    grid[3, 5] = 100
    data = received(grid, Q(43, 100), (-Q(387, 200), -Q(387, 200)))
    state = {"x": Q(43, 250), "y": Q(43, 500), "yaw": 0.}
    goal = {"x": -1., "y": 0.}
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    cache(nav, data, goal)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    proposal.assert_not_called()
    assert nav.blocked_quanta["tb1"] == 1


def test_point_clearance_failure_stops_before_any_translation_proposal():
    grid = np.zeros((7, 7), dtype=np.int8)
    grid[3, 4] = 100
    data = received(grid, 1., (-3.5, -3.5))
    state, goal = {"x": .25, "y": 0., "yaw": math.pi}, {"x": -1., "y": 0.}
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    cache(nav, data, goal)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    proposal.assert_not_called()


@pytest.mark.parametrize("failure", ["cell", "field", "outside"])
def test_original_cell_graph_and_map_bounds_still_reject_before_exact_fallback(failure):
    data, state, goal = positive_case()
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    if failure == "cell":
        data["grid"][20, 20] = -1
    if failure == "outside":
        state["x"] = -99.
    field = np.full(data["grid"].shape, np.inf) if failure == "field" else None
    cache(nav, data, goal, field=field)
    with patch.object(navigation, "certify_seed_pose_bridge", side_effect=AssertionError("upstream bypass")):
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    assert nav.blocked_quanta["tb1"] == 1


def test_old_scalar_bound_recovery_restores_original_lookahead_without_exact_calls():
    data, state, goal = positive_case()
    state["x"], state["y"] = 0., 0.
    legacy, exact = navigation.ProxyNavigator(), navigation.ProxyNavigator(seed_rule=EXACT)
    with patch.object(navigation, "certify_seed_pose_bridge", side_effect=AssertionError("not fallback")), \
            patch.object(navigation, "certify_estimated_segment", side_effect=AssertionError("not fallback")):
        assert exact.target_velocity("tb1", state, goal, data) == legacy.target_velocity("tb1", state, goal, data)


def test_short_remaining_distance_caps_translation_without_snapping_state():
    data, state, goal = positive_case()
    centre = tuple(data["origin"][axis] + 20.5 * data["resolution"] for axis in range(2))
    state["x"], state["y"] = centre[0], centre[1] - .0001
    remaining = math.dist((state["x"], state["y"]), centre)
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    # A legitimate more conservative cell lower bound, still at the original gate.
    cache(nav, data, goal, clearance_override={(20, 20): .29})
    before = dict(state)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as proposal:
        output, _ = nav.target_velocity("tb1", state, goal, data)
    assert 0 < output[0] <= remaining / .02 and output[1] == 0.
    start, end = proposal.call_args.args[3:]
    assert math.dist(start, end) <= remaining
    assert state == before


@pytest.mark.parametrize("veto", ["scan", "stale", "pair"])
def test_existing_scan_pair_and_freshness_vetoes_still_override_exact_fallback(veto):
    nav = navigation.ProxyNavigator(seed_rule=EXACT)
    states = {name: {"x": float(index * 3), "y": 0., "yaw": 0., "source_stamp": 1.}
              for index, name in enumerate(navigation.ROBOTS)}
    scans = {name: {"angles": np.array([0.]), "ranges": np.array([10.])} for name in navigation.ROBOTS}
    if veto == "scan":
        scans["tb1"]["ranges"][0] = .399
    if veto == "stale":
        states["tb1"]["source_stamp"] = .799
    certificate = {"geometric_necessary": veto != "pair"}
    with patch.object(nav, "target_velocity", return_value=((.12, 0.), False)), \
            patch.object(navigation, "pair_certificate", return_value=certificate):
        outputs, reached = nav.commands(states, {}, {name: {} for name in states}, scans, 1.)
    assert outputs["tb1"] == (0., 0.) and reached == []
    assert nav.blocked_quanta["tb1"] >= 1


@pytest.mark.parametrize("rule", ["legacy", EXACT])
def test_no_goal_and_arrival_still_stop_before_any_map_or_new_certificate(rule):
    nav = navigation.ProxyNavigator(seed_rule=rule)
    state = {"x": 0., "y": 0., "yaw": 0.}
    assert nav.target_velocity("tb1", state, None, {}) == ((0., 0.), False)
    assert nav.target_velocity("tb1", state, {"x": .01, "y": .01}, {}) == ((0., 0.), True)


@pytest.mark.parametrize("start,end", [((-10, -10), (-9, -9)), ((0, 0), (8, 8)),
                                       ((Q(3, 2), Q(3, 2)), (4, Q(3, 2)))])
def test_arbitrary_segment_kernel_rejects_outside_and_empty_local_windows(start, end):
    result = certify_estimated_segment(np.zeros((3, 3), dtype=np.int8), 1, (0, 0), start, end)
    assert not result["accepted"]
