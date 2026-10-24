"""Artificial grids and independent distance oracle; no scene or World."""
from fractions import Fraction as Q
import math

import numpy as np
import pytest


from multi_robot_exploration import mr3_point_graph as candidate


def number(value):
    return Q.from_float(float(value)) if isinstance(value, (float, np.floating)) else Q(int(value)) if isinstance(value, np.integer) else Q(value)


def segment_box_distance(start, end, box):
    """Independent t-interval quadratic minimization, not slab/corner distance."""
    delta = tuple(end[i] - start[i] for i in range(2))
    knots = {Q(0), Q(1)}
    for axis in range(2):
        if delta[axis]:
            for boundary in (box[axis], box[axis + 2]):
                t = (boundary - start[axis]) / delta[axis]
                if 0 < t < 1:
                    knots.add(t)
    def squared(t):
        return sum(max(box[i] - start[i] - t * delta[i], Q(0),
                       start[i] + t * delta[i] - box[i + 2]) ** 2 for i in range(2))
    knots = sorted(knots)
    answers = [squared(t) for t in knots]
    for lo, hi in zip(knots, knots[1:]):
        mid = (lo + hi) / 2
        numerator = denominator = Q(0)
        for axis in range(2):
            point = start[axis] + mid * delta[axis]
            boundary = box[axis] if point < box[axis] else box[axis + 2] if point > box[axis + 2] else None
            if boundary is not None:
                numerator -= (start[axis] - boundary) * delta[axis]
                denominator += delta[axis] ** 2
        if denominator:
            answers.append(squared(max(lo, min(hi, numerator / denominator))))
    return min(answers)


def full_grid_oracle(grid, resolution, origin, start, end):
    res, origin = number(resolution), tuple(map(number, origin))
    start, end = tuple(map(number, start)), tuple(map(number, end))
    right, top = origin[0] + grid.shape[1] * res, origin[1] + grid.shape[0] * res
    def exterior(point):
        return max(Q(0), min(point[0] - origin[0], point[1] - origin[1],
                             right - point[0], top - point[1])) ** 2
    distance = min(Q(29, 100) ** 2, exterior(start), exterior(end))
    for r in range(grid.shape[0]):
        for c in range(grid.shape[1]):
            if grid[r, c] != 0:
                box = (origin[0] + c * res, origin[1] + r * res,
                       origin[0] + (c + 1) * res, origin[1] + (r + 1) * res)
                distance = min(distance, segment_box_distance(start, end, box))
    return distance


def old_cell_false_case():
    grid = np.zeros((7, 7), np.int8)
    grid[3, 4] = 100
    return grid, .5, (-1.75, -1.75), (-Q(1, 5), Q(0))


def assert_all_anchors_match_oracle(grid, res, origin, pose, result):
    traversable, _ = candidate.native_traversable(grid, res)
    rq, oq, pq = number(res), tuple(map(number, origin)), tuple(map(number, pose))
    row = math.floor((pq[1] - oq[1]) / rq)
    col = math.floor((pq[0] - oq[0]) / rq)
    expected = []
    actual_nodes = result["candidate_nodes"]
    for r in range(max(0, row - 1), min(grid.shape[0] - 1, row + 1) + 1):
        for c in range(max(0, col - 1), min(grid.shape[1] - 1, col + 1) + 1):
            if traversable[r, c]:
                centre = (oq[0] + (Q(c) + Q(1, 2)) * rq, oq[1] + (Q(r) + Q(1, 2)) * rq)
                proof = next(node for node in actual_nodes if node["cell"] == [r, c])["bridge_certificate"]
                distance = full_grid_oracle(grid, res, origin, pose, centre)
                assert Q(proof["segment_distance_squared_capped_exact"]) == distance
                if distance >= Q(29, 100) ** 2:
                    expected.append([r, c])
    assert [anchor["cell"] for anchor in result["anchors"]] == expected


def test_original_cell_can_fail_while_unchanged_point_attaches_to_all_safe_original_neighbors():
    args = old_cell_false_case()
    result = candidate.point_graph_attachments(*args)
    assert result["accepted"] and result["production_enabled"] and not result["graph_mutated"]
    assert result["profile"] == "mr3-point-graph-attachment-3x3-v1"
    assert result["schema"] == "mr3-point-graph-attachment-v1"
    assert result["canonical_cell"] == [3, 3] and result["canonical_value"] == 0
    assert not result["canonical_cell_original_traversable"]
    assert result["point_certificate"]["accepted"]
    assert [3, 3] not in [anchor["cell"] for anchor in result["anchors"]]
    assert [3, 2] in [anchor["cell"] for anchor in result["anchors"]]
    assert_all_anchors_match_oracle(*args, result)
    # Row/column order retains all anchors, rather than choosing the shortest.
    assert result["anchors"][0]["bridge_length_m"] > result["anchors"][1]["bridge_length_m"]


def test_same_centre_bridge_can_fail_despite_original_cell_and_actual_point_passing():
    grid = np.zeros((5, 5), np.int8)
    grid[1, 3] = 100
    args = (grid, Q(43, 100), (-Q(43, 40), -Q(43, 40)), (Q(43, 250), Q(43, 500)))
    result = candidate.point_graph_attachments(*args)
    assert result["canonical_cell"] == [2, 2] and result["canonical_cell_original_traversable"]
    assert result["point_certificate"]["accepted"]
    same = next(node for node in result["candidate_nodes"] if node["cell"] == [2, 2])
    assert not same["bridge_certificate"]["accepted"]
    assert [2, 2] not in [anchor["cell"] for anchor in result["anchors"]]
    assert result["anchors"]
    assert_all_anchors_match_oracle(*args, result)


def test_window_is_clipped_fixed_3x3_without_outward_search_or_selected_goal():
    grid = np.zeros((3, 3), np.int8)
    result = candidate.point_graph_attachments(grid, 1., (0, 0), (Q(3, 10), Q(3, 10)))
    assert result["window_inclusive"] == [0, 1, 0, 1]
    assert [node["cell"] for node in result["candidate_nodes"]] == [[0, 0], [0, 1], [1, 0], [1, 1]]
    assert [anchor["cell"] for anchor in result["anchors"]] == [[0, 0], [0, 1], [1, 0], [1, 1]]
    traversable, _ = candidate.native_traversable(grid, 1.)
    assert traversable[2, 2]  # A valid farther graph node is deliberately absent.
    assert "selected_anchor" not in result and "goal" not in result and "command" not in result


def test_safe_point_without_any_original_graph_node_rejects_without_new_graph():
    grid = np.zeros((3, 9), np.int8)
    result = candidate.point_graph_attachments(grid, .2, (0, 0), (.9, .3))
    assert result["point_certificate"]["accepted"]
    assert not result["accepted"] and result["reason"] == "no_certified_anchor_in_fixed_3x3"
    assert len(result["candidate_nodes"]) == 9 and not result["anchors"]
    assert not any(node["original_traversable"] for node in result["candidate_nodes"])


@pytest.mark.parametrize("value,reason", [(-1, "canonical_cell_unknown"), (1, "canonical_cell_occupied"),
                                         (100, "canonical_cell_occupied")])
def test_nonfree_canonical_cell_never_borrows_a_free_neighbor(value, reason):
    grid, res, origin, pose = old_cell_false_case()
    grid[3, 3] = value
    result = candidate.point_graph_attachments(grid, res, origin, pose)
    assert result["canonical_cell"] == [3, 3]
    assert not result["accepted"] and result["reason"] == reason
    assert result["point_certificate"] is None and not result["candidate_nodes"]


@pytest.mark.parametrize("pose", [(0., 0.), (.24, 0.)])
def test_true_point_clearance_failure_stops_before_anchor_enumeration(pose):
    grid, res, origin, _ = old_cell_false_case()
    result = candidate.point_graph_attachments(grid, res, origin, pose)
    assert not result["accepted"] and result["reason"] == "estimated_point_body_clearance"
    assert not result["point_certificate"]["accepted"] and not result["candidate_nodes"]


def test_diagonal_corner_and_unknown_square_use_closed_square_distance():
    for value in (-1, 100):
        grid = np.zeros((7, 7), np.int8)
        grid[4, 4] = value
        result = candidate.point_graph_attachments(grid, 1., (-3.5, -3.5), (Q(2, 5), Q(2, 5)))
        assert not result["accepted"] and result["reason"] == "estimated_point_body_clearance"
        assert Q(result["point_certificate"]["segment_distance_squared_capped_exact"]) == Q(1, 50)


@pytest.mark.parametrize("pose", [(-.01, .5), (3., .5), (.1, .5)])
def test_outside_and_map_exterior_clearance_are_blocked(pose):
    result = candidate.point_graph_attachments(np.zeros((3, 3), np.int8), 1., (0, 0), pose)
    assert not result["accepted"] and not result["anchors"]
    assert result["reason"] == ("point_outside_received_map" if pose[0] < 0 or pose[0] >= 3 else
                                "estimated_point_body_clearance")


def test_binary_canonical_ownership_does_not_snap_to_float_division_neighbor():
    result = candidate.point_graph_attachments(np.zeros((40, 40), np.int8), .05, (0, 0), (.45, .45))
    assert result["canonical_cell"] == [8, 8]
    assert result["estimated_point_exact"] == [str(Q.from_float(.45))] * 2
    assert result["window_inclusive"] == [7, 9, 7, 9]


def test_exact_planning_lengths_and_inputs_are_detached_without_motion():
    grid, res, origin, pose = old_cell_false_case()
    before = grid.copy()
    result = candidate.point_graph_attachments(grid, res, origin, pose)
    for anchor in result["anchors"]:
        centre = tuple(Q(value) for value in anchor["centre_exact"])
        expected = sum((centre[i] - pose[i]) ** 2 for i in range(2))
        assert Q(anchor["bridge_length_squared_exact"]) == expected
        assert anchor["bridge_length_m"] == math.sqrt(float(expected))
    np.testing.assert_array_equal(grid, before)
    grid[:] = 100
    assert result["anchors"] and result["canonical_value"] == 0
    assert pose == (-Q(1, 5), Q(0))


@pytest.mark.parametrize("grid,res,origin,pose", [
    (np.zeros((3, 3), np.int8), True, (0, 0), (1, 1)),
    (np.zeros((3, 3), np.int8), 1., (False, 0), (1, 1)),
    (np.zeros((3, 3), np.int8), 1., (0, 0), (True, 1)),
    (np.zeros((3, 3), np.int8), 0., (0, 0), (1, 1)),
    (np.zeros((3, 3), np.int8), 1., (0, 0), (np.nan, 1)),
    (np.zeros((3, 3), float), 1., (0, 0), (1, 1)),
    (np.full((3, 3), 101, np.int16), 1., (0, 0), (1, 1)),
])
def test_invalid_inputs_reject_atomically(grid, res, origin, pose):
    before = grid.copy()
    with pytest.raises(ValueError):
        candidate.point_graph_attachments(grid, res, origin, pose)
    np.testing.assert_array_equal(grid, before)


@pytest.mark.parametrize("grid", [None, np.empty((0, 0), np.int8)])
def test_empty_received_map_rejects_instead_of_searching(grid):
    result = candidate.point_graph_attachments(grid, 1., (0, 0), (0, 0))
    assert not result["accepted"] and result["reason"] == "empty_received_map"
    assert result["canonical_cell"] is None and result["point_certificate"] is None


@pytest.mark.parametrize("delta,accepted", [(Q(0), True), (-Q(1, 10**12), True), (Q(1, 10**12), False)])
def test_exact_point_threshold_equality_is_kept_without_tolerance(delta, accepted):
    grid = np.zeros((5, 5), np.int8)
    grid[2, 3] = 100
    result = candidate.point_graph_attachments(grid, 1., (-2.5, -2.5), (Q(21, 100) + delta, Q(0)))
    assert result["point_certificate"]["accepted"] == accepted
    assert result["accepted"] == accepted
    if not accepted:
        assert result["reason"] == "estimated_point_body_clearance" and not result["candidate_nodes"]
