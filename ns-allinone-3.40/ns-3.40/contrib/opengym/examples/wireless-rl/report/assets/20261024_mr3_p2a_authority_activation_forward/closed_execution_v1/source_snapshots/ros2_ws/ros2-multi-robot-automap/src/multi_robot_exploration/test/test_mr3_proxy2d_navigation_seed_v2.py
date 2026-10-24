"""Explicit v2 local execution; artificial grids and states, no World/Node."""

from fractions import Fraction as Q
import hashlib
import math
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import mr3_proxy2d_navigation as navigation
from multi_robot_exploration.mr3_observation import native_traversable
from multi_robot_exploration.mr3_seed_certificate import (
    canonical_cell_centre, canonical_seed_cell, certify_estimated_segment,
    certify_seed_pose_bridge,
)


V2 = "exact-point-bridge-v2"


def received(grid, resolution=.05, origin=(-1.025, -1.025)):
    return {"grid": grid, "resolution": resolution, "origin": origin,
            "payload_sha256": hashlib.sha256(grid.tobytes()).hexdigest()}


def cache(nav, data, goal, *, field=None):
    """Retain real cell gates; a supplied scalar field isolates local routing."""
    grid, res, origin = data["grid"], data["resolution"], data["origin"]
    traversable, clearance = native_traversable(grid, float(res))
    if field is None:
        field = np.full(grid.shape, np.inf)
        field[traversable] = 1.
    key = (grid.dtype.str, grid.shape, grid.tobytes(order="C"), res,
           tuple(origin), goal["x"], goal["y"])
    value = (key, traversable, field)
    if nav.seed_rule != "legacy":
        value += (clearance,)
    nav.paths["tb1"] = value
    return traversable, field


def open_case(yaw=0.):
    data = received(np.zeros((41, 41), dtype=np.int8))
    return data, {"x": 0., "y": 0., "yaw": yaw, "source_stamp": 1.}, {"x": .7, "y": 0.}


def corner_case():
    grid = np.zeros((9, 9), dtype=np.int8)
    grid[3, 5] = 100
    data = received(grid, Q(43, 100), (-Q(387, 200), -Q(387, 200)))
    x, y = Q(43, 200) - Q(58, 425), -Q(43, 200) + Q(87, 340)
    state = {"x": x, "y": y, "yaw": math.atan2(-float(y), -float(x)), "source_stamp": 1.}
    return data, state, {"x": Q(129, 100), "y": -Q(43, 100)}


def test_v2_is_explicit_and_does_not_replace_legacy_or_v1_rules():
    assert navigation.ProxyNavigator().seed_rule == "legacy"
    for rule in ("legacy", "exact-point-bridge-v1", V2):
        assert navigation.ProxyNavigator(seed_rule=rule).seed_rule == rule
    with pytest.raises(ValueError, match="seed rule"):
        navigation.ProxyNavigator(seed_rule="exact-point-bridge-v3")


def test_canonical_robot_cell_is_used_before_graph_admission():
    data = received(np.zeros((40, 40), dtype=np.int8), .05, (0, 0))
    state, goal = {"x": .45, "y": .45, "yaw": 0.}, {"x": 1., "y": .45}
    nav = navigation.ProxyNavigator(seed_rule=V2)
    traversable, field = cache(nav, data, goal)
    # Old float cell remains admitted; exact ownership must independently fail.
    field[8, 8] = np.inf
    assert traversable[8, 8] and traversable[9, 9] and math.isfinite(field[9, 9])
    with patch.object(nav, "_exact_goal_velocity", side_effect=AssertionError("graph bypass")):
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    field[8, 8] = 1.
    with patch.object(nav, "_exact_goal_velocity", return_value=(0., 0.)) as execute:
        nav.target_velocity("tb1", state, goal, data)
    assert execute.call_args.args[3] == (8, 8)


def test_goal_away_can_start_directly_instead_of_recentering_toward_peer_direction():
    data, state, goal = open_case(-math.pi / 2)
    data["grid"][23, 26] = 100
    _, clearance = native_traversable(data["grid"], .05)
    state["y"] = -(clearance[20, 20] - math.sqrt(.08))
    goal.update(x=0., y=-.6)
    before_state, before_goal = dict(state), dict(goal)
    v1 = navigation.ProxyNavigator(seed_rule="exact-point-bridge-v1")
    v2 = navigation.ProxyNavigator(seed_rule=V2)
    assert v1.target_velocity("tb1", state, goal, data)[0][0] == 0.
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as checks:
        output, done = v2.target_velocity("tb1", state, goal, data)
    assert not done and output == (.12, 0.)
    assert checks.call_count == 2  # Whole route, then actual 20ms proposal.
    assert checks.call_args_list[0].args[4][1] < state["y"]
    assert checks.call_args_list[-1].args[4][1] < state["y"]
    assert state == before_state and goal == before_goal


def test_scalar_bound_pass_does_not_bypass_full_segment_or_proposal_checks():
    data, state, goal = open_case()
    nav = navigation.ProxyNavigator(seed_rule=V2)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as checks, \
            patch.object(navigation, "certify_seed_pose_bridge", side_effect=AssertionError("unneeded bridge")):
        assert nav.target_velocity("tb1", state, goal, data) == ((.12, 0.), False)
    assert checks.call_count == 2
    start, whole_end = checks.call_args_list[0].args[3:]
    _, proposed = checks.call_args_list[1].args[3:]
    assert whole_end[0] > proposed[0] > start[0]
    assert math.dist(start, proposed) <= .12 * .02 + 1e-17


def test_five_node_corner_cut_tries_existing_route_nodes_longest_to_shortest():
    data, state, goal = corner_case()
    nav = navigation.ProxyNavigator(seed_rule=V2)
    field = np.full(data["grid"].shape, np.inf)
    route = [(4, 4), (5, 4), (5, 5), (5, 6), (5, 7), (4, 7), (3, 7)]
    for index, cell in enumerate(route):
        field[cell] = len(route) - index - 1
    traversable, _ = cache(nav, data, goal, field=field)
    nodes = navigation._lookahead_cells(traversable, field, (4, 4))
    assert len(nodes) == 5 and all(traversable[cell] for cell in nodes)
    candidates = [canonical_cell_centre(cell, data["resolution"], data["origin"])
                  for cell in reversed(nodes)]
    accepted_index = next(index for index, endpoint in enumerate(candidates)
        if certify_estimated_segment(data["grid"], data["resolution"], data["origin"],
                                      (state["x"], state["y"]), endpoint)["accepted"])
    assert accepted_index > 0  # The old five-node straight shortcut is unsafe.
    chosen = candidates[accepted_index]
    state["yaw"] = math.atan2(chosen[1] - state["y"], chosen[0] - state["x"])
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as checks, \
            patch.object(navigation, "certify_seed_pose_bridge", side_effect=AssertionError("direct route exists")):
        output, done = nav.target_velocity("tb1", state, goal, data)
    assert not done and output == (.12, 0.)
    assert [call.args[4] for call in checks.call_args_list[:-1]] == candidates[:accepted_index + 1]


def test_all_direct_segments_rejected_uses_only_same_seed_centre_bridge():
    data, state, goal = open_case(math.pi)
    state["x"] = .01
    nav = navigation.ProxyNavigator(seed_rule=V2)
    original = certify_estimated_segment
    def reject_long_direct(grid, res, origin, start, end):
        return {"accepted": False} if math.dist(start, end) > .02 else original(grid, res, origin, start, end)
    with patch.object(navigation, "certify_estimated_segment", side_effect=reject_long_direct) as checks, \
            patch.object(navigation, "certify_seed_pose_bridge", wraps=certify_seed_pose_bridge) as bridge:
        output, done = nav.target_velocity("tb1", state, goal, data)
    assert not done and output == (.12, 0.) and checks.call_count == 6
    assert bridge.call_count == 1 and bridge.call_args.args[4] == (20, 20)
    assert checks.call_args.args[4][0] < state["x"]


def test_real_bridge_interior_unsafe_stops_after_original_point_and_cell_pass():
    data, state, goal = corner_case()
    state.update(x=Q(43, 250), y=Q(43, 500), yaw=0.)
    nav = navigation.ProxyNavigator(seed_rule=V2)
    cache(nav, data, goal)  # Constant field: no descending supplied-goal node.
    result = certify_seed_pose_bridge(data["grid"], data["resolution"], data["origin"],
        (state["x"], state["y"]), (4, 4), seed_cell_traversable=True)
    assert result["reason"] == "seed_bridge_body_clearance"
    assert Q(result["point_distance_squared_capped_exact"]) == Q(29, 100) ** 2
    with patch.object(nav, "_exact_waypoint_velocity", side_effect=AssertionError("unsafe bridge")):
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)


def test_real_point_unsafe_cannot_be_bypassed_by_safe_graph_nodes():
    grid = np.zeros((7, 7), dtype=np.int8)
    grid[3, 4] = 100
    data = received(grid, 1., (-3.5, -3.5))
    state, goal = {"x": .25, "y": 0., "yaw": math.pi}, {"x": -2., "y": 0.}
    nav = navigation.ProxyNavigator(seed_rule=V2)
    with patch.object(nav, "_exact_waypoint_velocity", side_effect=AssertionError("unsafe point")):
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    assert nav.blocked_quanta["tb1"] == 1


def test_alignment_tolerance_does_not_authorize_an_unsafe_actual_quantum():
    data, state, goal = corner_case()
    state["yaw"] += .05
    nav = navigation.ProxyNavigator(seed_rule=V2)
    cache(nav, data, goal)
    assert certify_seed_pose_bridge(data["grid"], data["resolution"], data["origin"],
        (state["x"], state["y"]), (4, 4), seed_cell_traversable=True)["accepted"]
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as checks:
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    assert checks.call_count == 1 and not certify_estimated_segment(*checks.call_args.args)["accepted"]


@pytest.mark.parametrize("angle", [-.05, .05])
def test_direct_translation_is_zero_angular_velocity_not_the_old_turning_arc(angle):
    data, state, goal = open_case(angle)
    nav = navigation.ProxyNavigator(seed_rule=V2)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as checks:
        output, _ = nav.target_velocity("tb1", state, goal, data)
    assert output == (.12, 0.)
    end = checks.call_args.args[4]
    assert end == (.12 * .02 * math.cos(angle), .12 * .02 * math.sin(angle))
    old_w = -2 * angle
    arc = (.12 / old_w * (math.sin(angle + old_w * .02) - math.sin(angle)),
           -.12 / old_w * (math.cos(angle + old_w * .02) - math.cos(angle)))
    assert math.dist(end, arc) > 1e-7


def test_misaligned_direct_path_rotates_without_a_translation_proposal():
    data, state, goal = open_case(math.pi / 2)
    nav = navigation.ProxyNavigator(seed_rule=V2)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as checks:
        assert nav.target_velocity("tb1", state, goal, data) == ((0., -.6), False)
    assert checks.call_count == 1


def test_direct_path_certificate_does_not_replace_the_quantum_certificate():
    data, state, goal = open_case()
    nav = navigation.ProxyNavigator(seed_rule=V2)
    with patch.object(navigation, "certify_estimated_segment", side_effect=[{"accepted": True}, {"accepted": False}]) as checks:
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)
    assert checks.call_count == 2 and nav.blocked_quanta["tb1"] == 1


def test_remaining_waypoint_distance_caps_the_actual_represented_proposal():
    data, state, goal = open_case()
    nav = navigation.ProxyNavigator(seed_rule=V2)
    centre = canonical_cell_centre((20, 20), data["resolution"], data["origin"])
    state.update(x=centre[0] - Q(1, 10000), y=centre[1])
    cache(nav, data, goal)
    before = dict(state)
    with patch.object(navigation, "certify_estimated_segment", wraps=certify_estimated_segment) as checks:
        output, done = nav.target_velocity("tb1", state, goal, data)
    assert not done and output[1] == 0.
    assert 0 < output[0] <= .0001 / .02
    start, end = checks.call_args.args[3:]
    exact = lambda x: x if isinstance(x, Q) else Q.from_float(float(x))
    assert sum((exact(end[i]) - exact(start[i])) ** 2 for i in range(2)) <= Q(1, 10000) ** 2
    assert state == before


@pytest.mark.parametrize("failure", ["unknown", "cell", "field", "outside"])
def test_original_seed_cell_graph_and_bounds_fail_before_any_v2_segment(failure):
    data, state, goal = open_case()
    nav = navigation.ProxyNavigator(seed_rule=V2)
    if failure == "unknown":
        data["grid"][20, 20] = -1
    if failure == "outside":
        state["x"] = -99.
    traversable, field = cache(nav, data, goal)
    if failure == "cell":
        traversable[20, 20] = False
    if failure == "field":
        field[20, 20] = np.inf
    with patch.object(navigation, "certify_estimated_segment", side_effect=AssertionError("upstream bypass")), \
            patch.object(navigation, "certify_seed_pose_bridge", side_effect=AssertionError("upstream bypass")):
        assert nav.target_velocity("tb1", state, goal, data) == ((0., 0.), False)


@pytest.mark.parametrize("veto", ["scan", "pair", "stale"])
def test_original_scan_pair_and_state_freshness_still_override_v2(veto):
    nav = navigation.ProxyNavigator(seed_rule=V2)
    states = {name: {"x": float(3 * index), "y": 0., "yaw": 0., "source_stamp": 1.}
              for index, name in enumerate(navigation.ROBOTS)}
    scans = {name: {"angles": np.array([0.]), "ranges": np.array([10.])} for name in states}
    if veto == "scan":
        scans["tb1"]["ranges"][0] = .399
    if veto == "stale":
        states["tb1"]["source_stamp"] = .799
    with patch.object(nav, "target_velocity", return_value=((.12, 0.), False)), \
            patch.object(navigation, "pair_certificate", return_value={"geometric_necessary": veto != "pair"}):
        outputs, reached = nav.commands(states, {}, {name: {} for name in states}, scans, 1.)
    assert outputs["tb1"] == (0., 0.) and reached == []


def test_no_supplied_goal_and_arrival_stop_before_map_or_certification():
    nav = navigation.ProxyNavigator(seed_rule=V2)
    state = {"x": 0., "y": 0., "yaw": 0.}
    assert nav.target_velocity("tb1", state, None, {}) == ((0., 0.), False)
    assert nav.target_velocity("tb1", state, {"x": .01, "y": .01}, {}) == ((0., 0.), True)


def test_lookahead_retains_no_corner_cut_and_five_existing_nodes_only():
    traversable = np.ones((9, 9), bool)
    field = np.full((9, 9), np.inf)
    for index in range(8):
        field[4, index] = 8 - index
    assert navigation._lookahead_cells(traversable, field, (4, 0)) == [(4, i) for i in range(1, 6)]
    traversable[3, 4] = False
    field[3, 5] = -1.
    assert (3, 5) not in navigation._lookahead_cells(traversable, field, (4, 4))[:1]
