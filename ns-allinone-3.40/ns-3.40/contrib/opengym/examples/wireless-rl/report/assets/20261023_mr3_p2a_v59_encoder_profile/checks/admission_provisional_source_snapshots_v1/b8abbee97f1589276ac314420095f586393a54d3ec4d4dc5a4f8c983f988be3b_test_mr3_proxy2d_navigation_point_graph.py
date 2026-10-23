"""Artificial supplied-goal attachment execution, never World or real input."""
from fractions import Fraction as Q
import hashlib
import math
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import mr3_point_graph as point_graph
from multi_robot_exploration import mr3_proxy2d_navigation as nav
from multi_robot_exploration.mr3_seed_certificate import (
    canonical_cell_centre, canonical_seed_cell, certify_estimated_segment,
)


RULE = "point-attachment-3x3-v1"
SEED = "exact-point-bridge-v2"


def navigator():
    return nav.ProxyNavigator(seed_rule=SEED, start_graph_rule=RULE)


def received(grid, resolution=.5, origin=(-1.75, -1.75)):
    return {"grid": grid, "resolution": resolution, "origin": origin,
            "payload_sha256": hashlib.sha256(grid.tobytes()).hexdigest()}


def false_cell_case():
    grid = np.zeros((7, 7), np.int8)
    grid[3, 4] = 100
    return received(grid), {"x": -.2, "y": 0., "yaw": math.pi, "source_stamp": 1.}, {
        "x": -1., "y": 0., "goal_id": "policy-original"}


def cache(controller, data, goal, field):
    grid, res, origin = data["grid"], data["resolution"], data["origin"]
    traversable, clearance = nav.native_traversable(grid, res)
    key = (grid.dtype.str, grid.shape, grid.tobytes(order="C"), res,
           tuple(origin), goal["x"], goal["y"])
    controller.paths["tb3"] = (key, traversable, field, clearance)
    return traversable


@pytest.mark.parametrize("seed", ["legacy", "exact-point-bridge-v1"])
def test_new_graph_rule_requires_explicit_exact_v2_seed(seed):
    with pytest.raises(ValueError):
        nav.ProxyNavigator(seed_rule=seed, start_graph_rule=RULE)


def test_graph_rule_is_strict_and_default_is_original():
    assert nav.ProxyNavigator().start_graph_rule == "original-seed-cell"
    assert navigator().start_graph_rule == RULE
    for invalid in (None, True, "point-attachment", "nearby-free"):
        with pytest.raises(ValueError):
            nav.ProxyNavigator(seed_rule=SEED, start_graph_rule=invalid)


def test_false_containing_cell_can_start_with_a_certified_original_graph_attachment():
    data, state, goal = false_cell_case()
    before_state, before_goal, before_grid = dict(state), dict(goal), data["grid"].copy()
    old = nav.ProxyNavigator(seed_rule=SEED)
    assert old.target_velocity("tb3", state, goal, data) == ((0., 0.), False)
    controller = navigator()
    with patch.object(controller, "_point_graph_continuation", wraps=controller._point_graph_continuation) as follow:
        output, done = controller.target_velocity("tb3", state, goal, data)
    assert not done and output == (.12, 0.)
    navigation, proposed, anchor, route, traversable, field = follow.call_args.args
    current = canonical_seed_cell((state["x"], state["y"]), data["resolution"], data["origin"], data["grid"].shape)
    following = canonical_seed_cell(proposed, data["resolution"], data["origin"], data["grid"].shape)
    assert not traversable[current] and not traversable[following]
    retained = controller._point_graph_continuation(navigation, proposed, anchor, route, traversable, field)
    assert retained is not None and traversable[retained] and math.isfinite(field[retained])
    next_attachments = point_graph.point_graph_attachments(data["grid"], data["resolution"], data["origin"], proposed)
    assert list(retained) in [entry["cell"] for entry in next_attachments["anchors"]]
    assert certify_estimated_segment(data["grid"], data["resolution"], data["origin"],
        (state["x"], state["y"]), proposed)["accepted"]
    assert state == before_state and goal == before_goal
    np.testing.assert_array_equal(data["grid"], before_grid)


def test_entry_anchor_at_exact_current_centre_does_not_require_zero_length_arrival():
    data = received(np.zeros((7, 7), np.int8))
    state = {"x": 0., "y": 0., "yaw": 0., "source_stamp": 1.}
    goal = {"x": 1., "y": 0., "goal_id": "stable"}
    controller = navigator()
    with patch.object(controller, "_point_graph_continuation", wraps=controller._point_graph_continuation) as follow:
        assert controller.target_velocity("tb3", state, goal, data) == ((.12, 0.), False)
    assert follow.call_args.args[2] == (3, 3)
    assert follow.call_args.args[3]  # The same policy goal's descending graph route.


@pytest.mark.parametrize("nearest_field", [math.inf, 10.])
def test_min_bridge_plus_goal_field_can_choose_a_longer_non_nearest_attachment(nearest_field):
    data, state, goal = false_cell_case()
    field = np.full(data["grid"].shape, np.inf)
    field[3, 2], field[2, 3] = nearest_field, 1.
    selected = canonical_cell_centre((2, 3), data["resolution"], data["origin"])
    state["yaw"] = math.atan2(selected[1] - state["y"], selected[0] - state["x"])
    controller = navigator()
    cache(controller, data, goal, field)
    attachments = point_graph.point_graph_attachments(data["grid"], data["resolution"], data["origin"],
        (state["x"], state["y"]))
    assert min(attachments["anchors"], key=lambda entry: entry["bridge_length_m"])["cell"] == [3, 2]
    with patch.object(controller, "_point_graph_continuation", wraps=controller._point_graph_continuation) as follow:
        assert controller.target_velocity("tb3", state, goal, data) == ((.12, 0.), False)
    assert follow.call_args.args[2] == (2, 3)


def test_equal_total_cost_has_deterministic_row_column_tie_break():
    data = received(np.zeros((7, 7), np.int8))
    state = {"x": 0., "y": 0., "yaw": -math.pi / 2, "source_stamp": 1.}
    goal = {"x": 1., "y": 0.}
    field = np.full(data["grid"].shape, np.inf)
    field[2, 3] = field[3, 2] = 1.
    controller = navigator()
    cache(controller, data, goal, field)
    with patch.object(controller, "_point_graph_continuation", wraps=controller._point_graph_continuation) as follow:
        assert controller.target_velocity("tb3", state, goal, data) == ((.12, 0.), False)
    assert follow.call_args.args[2] == (2, 3)


def test_all_attachments_outside_goal_component_stop_without_neighbor_borrowing():
    data, state, goal = false_cell_case()
    controller = navigator()
    cache(controller, data, goal, np.full(data["grid"].shape, np.inf))
    with patch.object(controller, "_exact_waypoint_velocity", side_effect=AssertionError("disconnected route")):
        assert controller.target_velocity("tb3", state, goal, data) == ((0., 0.), False)


def test_nominal_handoff_keeps_a_goal_connected_anchor_in_the_new_fixed_window():
    data = received(np.zeros((9, 9), np.int8), 1., (-4.5, -4.5))
    traversable, _ = nav.native_traversable(data["grid"], 1.)
    field = np.ones(data["grid"].shape)
    proposed, original, route = (.51, 0.), (4, 3), [(4, 4), (4, 5)]
    assert canonical_seed_cell(proposed, 1., data["origin"], data["grid"].shape) == (4, 5)
    retained = nav.ProxyNavigator._point_graph_continuation(data, proposed, original, route, traversable, field)
    assert retained == (4, 4)
    result = point_graph.point_graph_attachments(data["grid"], 1., data["origin"], proposed)
    assert list(retained) in [entry["cell"] for entry in result["anchors"]]
    assert list(original) not in [entry["cell"] for entry in result["anchors"]]


@pytest.mark.parametrize("failure", ["window", "traversable", "field", "unknown", "outside_node"])
def test_continuation_rejects_each_missing_original_attachment_condition(failure):
    data = received(np.zeros((9, 9), np.int8), 1., (-4.5, -4.5))
    traversable, _ = nav.native_traversable(data["grid"], 1.)
    field = np.ones(data["grid"].shape)
    proposed, anchor = (.51, 0.), (4, 4)
    if failure == "window":
        anchor = (4, 3)
    if failure == "traversable":
        traversable[anchor] = False
    if failure == "field":
        field[anchor] = np.inf
    if failure == "unknown":
        data["grid"][4, 5] = -1
    if failure == "outside_node":
        proposed, anchor = (-4., 0.), (4, -1)
    assert nav.ProxyNavigator._point_graph_continuation(data, proposed, anchor, [], traversable, field) is None


def test_point_clearance_does_not_replace_the_whole_nextpoint_to_anchor_bridge():
    grid = np.zeros((5, 5), np.int8)
    grid[1, 3] = 100
    data = received(grid, Q(43, 100), (-Q(43, 40), -Q(43, 40)))
    proposed = (Q(43, 250), Q(43, 500))
    traversable, _ = nav.native_traversable(grid, .43)
    field = np.ones(grid.shape)
    assert traversable[2, 2]
    assert certify_estimated_segment(grid, data["resolution"], data["origin"], proposed, proposed)["accepted"]
    assert nav.ProxyNavigator._point_graph_continuation(data, proposed, (2, 2), [], traversable, field) is None


def test_no_translation_is_emitted_if_every_nominal_nextpoint_loses_attachment():
    data = received(np.zeros((7, 7), np.int8))
    state, goal = {"x": 0., "y": 0., "yaw": 0.}, {"x": 1., "y": 0.}
    controller = navigator()
    with patch.object(controller, "_point_graph_continuation", return_value=None) as continuation:
        assert controller.target_velocity("tb3", state, goal, data) == ((0., 0.), False)
    assert continuation.call_count >= 1


def test_current_to_nextpoint_certificate_remains_mandatory():
    data = received(np.zeros((7, 7), np.int8))
    state, goal = {"x": 0., "y": 0., "yaw": 0.}, {"x": 1., "y": 0.}
    controller = navigator()
    real = certify_estimated_segment
    def reject_actual_proposal(grid, res, origin, start, end):
        return {"accepted": False} if 0 < math.dist(start, end) < .01 else real(grid, res, origin, start, end)
    with patch.object(nav, "certify_estimated_segment", side_effect=reject_actual_proposal), \
            patch.object(controller, "_point_graph_continuation", side_effect=AssertionError("uncertified proposal")):
        assert controller.target_velocity("tb3", state, goal, data) == ((0., 0.), False)


@pytest.mark.parametrize("change", ["unknown", "point"])
def test_new_mode_keeps_the_raw_canonical_cell_and_exact_point_gates(change):
    data, state, goal = false_cell_case()
    if change == "unknown":
        data["grid"][3, 3] = -1
    else:
        state["x"] = 0.  # .25m from the closed occupied square, below .29.
    assert navigator().target_velocity("tb3", state, goal, data) == ((0., 0.), False)


@pytest.mark.parametrize("seed", ["legacy", "exact-point-bridge-v1", SEED])
def test_default_and_explicit_original_modes_have_identical_old_outputs(seed):
    data = received(np.zeros((7, 7), np.int8))
    state, goal = {"x": 0., "y": 0., "yaw": .05}, {"x": 1., "y": 0.}
    with patch.object(point_graph, "point_graph_attachments", side_effect=AssertionError("default loaded new mode")):
        implicit = nav.ProxyNavigator(seed_rule=seed)
        explicit = nav.ProxyNavigator(seed_rule=seed, start_graph_rule="original-seed-cell")
        assert implicit.target_velocity("tb3", state, goal, data) == explicit.target_velocity("tb3", state, goal, data)


@pytest.mark.parametrize("veto", ["scan", "peer", "stale"])
def test_existing_scan_real_peer_and_freshness_gates_still_override_new_mode(veto):
    controller = navigator()
    states = {name: {"x": 3. * index, "y": 0., "yaw": 0., "source_stamp": 1.}
              for index, name in enumerate(nav.ROBOTS)}
    scans = {name: {"angles": np.array([0.]), "ranges": np.array([10.])} for name in states}
    if veto == "scan":
        scans["tb1"]["ranges"][0] = .399
    if veto == "peer":
        states["tb2"]["x"] = .3
    if veto == "stale":
        states["tb1"]["source_stamp"] = .799
    with patch.object(controller, "target_velocity", return_value=((.12, 0.), False)):
        outputs, _ = controller.commands(states, {}, {name: {} for name in states}, scans, 1.)
    assert outputs["tb1"] == (0., 0.)


def test_no_goal_and_arrival_preempt_the_new_geometry_path():
    controller = navigator()
    state = {"x": 0., "y": 0., "yaw": 0.}
    assert controller.target_velocity("tb3", state, None, {}) == ((0., 0.), False)
    assert controller.target_velocity("tb3", state, {"x": .01, "y": .01}, {}) == ((0., 0.), True)
