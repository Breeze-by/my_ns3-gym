"""Artificial sensor-stream checks for the disabled mapper-v2 candidate.

No World, node, task scene, truth loader, episode or saved journal is used.
The named wall/ghost cases describe supplied measurements, not knowledge
available to the mapper or a proof about actual noisy task performance.
"""

import math

import numpy as np
import pytest

from multi_robot_exploration.mr3_proxy2d_mapping import SensorMapperV2


def mapper():
    return SensorMapperV2((20, 20), .05, (0., 0.))


def payload(**overrides):
    values = dict(sensor_pose=(0., .325, 0.), angles=np.array([0.]),
                  ranges=np.array([.299]), range_min=.12, range_max=10.)
    values.update(overrides)
    return values


def scan(instance, scan_id, **overrides):
    return instance.integrate(scan_id, **payload(**overrides))


def snapshot(instance):
    return instance.grid(), instance.evidence(), instance.memory_bytes


def assert_unchanged(instance, before):
    np.testing.assert_array_equal(instance.grid(), before[0])
    np.testing.assert_array_equal(instance.evidence(), before[1])
    assert instance.memory_bytes == before[2]


@pytest.mark.parametrize("pose,angle,expected_free", [
    ((.5, 2.5, 0.), 0., [(2, 0), (2, 1)]),
    ((4.5, 2.5, 0.), math.pi, [(2, 4), (2, 3)]),
    ((2.5, .5, 0.), math.pi / 2, [(0, 2), (1, 2)]),
    ((2.5, 4.5, 0.), -math.pi / 2, [(4, 2), (3, 2)]),
])
def test_four_grid_aligned_faces_choose_ray_forward_hit_cell(pose, angle, expected_free):
    # Four measurements of the faces of the artificial square [2,3] x [2,3].
    instance = SensorMapperV2((6, 6), 1., (0., 0.))
    assert scan(instance, 0, sensor_pose=pose, angles=np.array([angle]), ranges=np.array([1.5]))
    expected = np.zeros((6, 6), dtype=np.int8)
    for cell in expected_free:
        expected[cell] = -1
    expected[2, 2] = 2
    np.testing.assert_array_equal(instance.evidence(), expected)
    assert set(map(tuple, np.argwhere(instance.grid() == 100))) == {(2, 2)}
    assert not np.any(instance.grid() == 0)  # One free vote remains unknown.


def test_negative_diagonal_corner_tie_moves_both_hit_coordinates_forward():
    instance = SensorMapperV2((6, 6), 1., (0., 0.))
    scan(instance, 0, sensor_pose=(4., 4., -3 * math.pi / 4),
         angles=np.array([0.]), ranges=np.array([math.sqrt(2)]))
    expected = np.zeros((6, 6), dtype=np.int8)
    expected[4, 4] = expected[3, 3] = -1
    expected[2, 2] = 2
    np.testing.assert_array_equal(instance.evidence(), expected)


@pytest.mark.parametrize("heading", [math.pi / 4, -math.pi / 2, math.pi / 2])
def test_sensor_heading_and_relative_ray_angle_use_the_same_common_frame(heading):
    straight, rotated = mapper(), mapper()
    scan(straight, 0)
    scan(rotated, 0, sensor_pose=(0., .325, heading), angles=np.array([-heading]))
    np.testing.assert_array_equal(rotated.evidence(), straight.evidence())
    np.testing.assert_array_equal(rotated.grid(), straight.grid())


def test_oblique_ray_uses_integer_walk_without_filling_a_wall_volume():
    instance = SensorMapperV2((6, 6), 1., (0., 0.))
    scan(instance, 0, sensor_pose=(1.25, 1.25, math.pi / 4),
         ranges=np.array([1.25 * math.sqrt(2)]))
    expected = np.zeros((6, 6), dtype=np.int8)
    expected[1, 1], expected[2, 2] = -1, 2
    np.testing.assert_array_equal(instance.evidence(), expected)
    assert np.count_nonzero(instance.grid() == 100) == 1


@pytest.mark.parametrize("ulps,expected_column", [(1, 2), (16, 3)])
def test_grid_tie_roundoff_guard_is_in_ulps_not_a_metric_hit_band(ulps, expected_column):
    instance = SensorMapperV2((6, 6), 1., (0., 0.))
    endpoint = 3. + ulps * np.spacing(3.)
    scan(instance, 0, sensor_pose=(4.5, 2.5, 0.), angles=np.array([math.pi]),
         ranges=np.array([4.5 - endpoint]))
    assert set(map(tuple, np.argwhere(instance.grid() == 100))) == {(2, expected_column)}


@pytest.mark.parametrize("clean_range,error,expected_column", [
    (.299, .002, 6), (.299, .01, 6),
    (.301, -.002, 5), (.301, -.01, 5),
])
def test_two_mm_and_one_cm_errors_can_still_move_hit_into_another_cell(
        clean_range, error, expected_column):
    # Error is supplied explicitly. No Gaussian frequency or task claim follows.
    instance = mapper()
    scan(instance, 0, ranges=np.array([clean_range + error]))
    clean_column = 5 if clean_range == .299 else 6
    assert expected_column != clean_column
    assert instance.evidence()[6, expected_column] == 2
    assert instance.grid()[6, expected_column] == 100
    assert instance.grid()[6, clean_column] != 100


def test_stable_hit_survives_one_positive_range_error_but_persistent_bias_can_clear_it():
    instance = mapper()
    scan(instance, 0)
    scan(instance, 1)
    assert instance.evidence()[6, 5] == 4 and instance.grid()[6, 5] == 100
    expected_score = [3, 2, 1, 0, -1, -2]
    expected_grid = [100, 100, -1, -1, -1, 0]
    for scan_id, score, value in zip(range(2, 8), expected_score, expected_grid):
        scan(instance, scan_id, ranges=np.array([.301]))
        assert instance.evidence()[6, 5] == score
        assert instance.grid()[6, 5] == value
    # This is the same sensor-only mechanism that permits clearing a ghost.
    # It does not establish a repair of the original false-free quality gate.
    assert instance.grid()[6, 6] == 100


def test_one_hit_then_one_conflicting_free_vote_becomes_unknown_not_free():
    instance = mapper()
    scan(instance, 0)
    scan(instance, 1, ranges=np.array([.301]))
    assert instance.evidence()[6, 5] == 1
    assert instance.grid()[6, 5] == -1


def test_each_cell_has_one_vote_per_scan_and_hit_wins_conflicts_in_any_beam_order():
    original, permuted, duplicated = mapper(), mapper(), mapper()
    ranges = np.array([.299, .399, .299])
    scan(original, 0, angles=np.zeros(3), ranges=ranges)
    scan(permuted, 0, angles=np.zeros(3), ranges=ranges[[1, 2, 0]])
    scan(duplicated, 0, angles=np.zeros(100), ranges=np.full(100, .299))
    expected = np.zeros((20, 20), dtype=np.int8)
    expected[6, :5], expected[6, 5], expected[6, 6], expected[6, 7] = -1, 2, -1, 2
    np.testing.assert_array_equal(original.evidence(), expected)
    np.testing.assert_array_equal(permuted.evidence(), expected)
    assert duplicated.evidence()[6, 5] == 2
    assert np.all(duplicated.evidence()[6, :5] == -1)


def test_same_scan_is_idempotent_but_identical_new_scan_accumulates():
    instance = mapper()
    args = payload()
    assert instance.integrate(7, **args) is True
    before = snapshot(instance)
    assert instance.integrate(7, **payload()) is False
    assert_unchanged(instance, before)
    assert instance.integrate(8, **payload()) is True
    assert instance.evidence()[6, 5] == 4
    assert instance.grid()[6, 5] == 100
    assert np.all(instance.evidence()[6, :5] == -2)
    assert np.all(instance.grid()[6, :5] == 0)


@pytest.mark.parametrize("changed", [
    {"sensor_pose": (0., .325, .01)},
    {"angles": np.array([.01])},
    {"ranges": np.array([np.nextafter(.299, np.inf)])},
    {"range_min": .1}, {"range_max": 20.},
])
def test_latest_scan_id_cannot_be_reused_with_any_changed_payload_field(changed):
    instance = mapper()
    scan(instance, 7)
    before = snapshot(instance)
    with pytest.raises(ValueError):
        scan(instance, 7, **changed)
    assert_unchanged(instance, before)
    assert scan(instance, 7) is False
    assert scan(instance, 8) is True


def test_old_scan_id_is_rejected_and_mutating_callers_arrays_cannot_rewrite_identity():
    instance = mapper()
    args = payload()
    instance.integrate(7, **args)
    before = snapshot(instance)
    with pytest.raises(ValueError):
        scan(instance, 6)
    assert_unchanged(instance, before)
    args["ranges"][0] = .301
    with pytest.raises(ValueError):
        instance.integrate(7, **args)
    assert_unchanged(instance, before)
    assert scan(instance, 7) is False


def test_max_range_is_free_only_including_endpoint_without_hit_tie_correction():
    instance = SensorMapperV2((4, 4), 1., (0., 0.))
    args = dict(sensor_pose=(1.5, .5, 0.), angles=np.array([math.pi]),
                ranges=np.array([.5]), range_max=.5)
    scan(instance, 0, **args)
    assert instance.evidence()[0, 1] == -1
    assert instance.evidence()[0, 0] == 0
    scan(instance, 1, **args)
    assert instance.grid()[0, 1] == 0
    assert not np.any(instance.grid() == 100)


def test_repeated_consistent_max_range_free_evidence_can_clear_a_ghost():
    instance = mapper()
    scan(instance, 0)
    scan(instance, 1)
    for scan_id in range(2, 8):
        scan(instance, scan_id, ranges=np.array([1.]), range_max=1.)
    assert instance.evidence()[6, 5] == -2
    assert instance.grid()[6, 5] == 0
    assert not np.any(instance.grid() == 100)


def test_saturated_free_prior_remains_free_on_first_hit_and_needs_three_new_hits():
    # The asymmetric fixed scores delay recognizing a new obstacle. Keep this
    # cost visible; this disabled candidate is not a navigation safety repair.
    instance = mapper()
    for scan_id in range(4):
        scan(instance, scan_id, ranges=np.array([1.]), range_max=1.)
    assert instance.evidence()[6, 5] == -4 and instance.grid()[6, 5] == 0
    for scan_id, score, value in ((4, -2, 0), (5, 0, -1), (6, 2, 100)):
        scan(instance, scan_id)
        assert instance.evidence()[6, 5] == score
        assert instance.grid()[6, 5] == value


def test_outputs_are_detached_int8_and_persistent_memory_does_not_grow_with_scans():
    instance = mapper()
    assert instance.grid().dtype == instance.evidence().dtype == np.int8
    assert np.all(instance.grid() == -1) and np.all(instance.evidence() == 0)
    assert instance.memory_bytes == 20 * 20
    angles = np.array([0., .1, -.1])
    expected_memory = 20 * 20 + 3 * 8 + len(angles) * 8 * 2 + 2 * 8
    for scan_id in range(64):
        scan(instance, scan_id, angles=angles, ranges=np.array([.299, .4 + .001 * (scan_id % 2), .5]))
        assert instance.memory_bytes == expected_memory
        assert np.max(np.abs(instance.evidence())) <= 4
    before = snapshot(instance)
    external_grid, external_evidence = instance.grid(), instance.evidence()
    external_grid.fill(17)
    external_evidence.fill(99)
    assert_unchanged(instance, before)


@pytest.mark.parametrize("overrides", [
    {"scan_id": -1}, {"scan_id": True}, {"scan_id": 8.0},
    {"sensor_pose": (0., 0.)}, {"sensor_pose": (0., 0., float("nan"))},
    {"sensor_pose": (1e100, 0., 0.)},
    {"angles": np.array([])}, {"angles": np.array([[0.]])},
    {"angles": np.array([float("inf")])}, {"angles": np.array([1 + 2j])},
    {"ranges": np.array([.299, .301])}, {"ranges": np.array([[.299]])},
    {"ranges": np.array([float("nan")])}, {"ranges": np.array([float("inf")])},
    {"ranges": np.array([.119])}, {"ranges": np.array([10.001])},
    {"range_min": 0.}, {"range_min": float("nan")},
    {"range_max": float("inf")}, {"range_min": 10., "range_max": 10.},
    {"ranges": np.array([500_000.]), "range_max": 600_000.},
])
def test_invalid_scan_or_excessive_workspace_is_atomic_and_does_not_consume_id(overrides):
    instance = mapper()
    scan(instance, 7)
    before = snapshot(instance)
    values = dict(overrides)
    scan_id = values.pop("scan_id", 8)
    with pytest.raises(ValueError):
        scan(instance, scan_id, **values)
    assert_unchanged(instance, before)
    assert scan(instance, 8) is True


@pytest.mark.parametrize("shape,resolution,origin", [
    ((0, 2), .05, (0., 0.)), ((2, -1), .05, (0., 0.)),
    ((True, 2), .05, (0., 0.)), ((2., 2), .05, (0., 0.)),
    ((2, 2, 2), .05, (0., 0.)),
    ((2, 2), 0., (0., 0.)), ((2, 2), -.05, (0., 0.)),
    ((2, 2), float("inf"), (0., 0.)), ((2, 2), True, (0., 0.)),
    ((2, 2), .05, (0.,)), ((2, 2), .05, (0., float("nan"))),
])
def test_invalid_geometry_is_rejected_before_allocating_a_candidate(shape, resolution, origin):
    with pytest.raises(ValueError):
        SensorMapperV2(shape, resolution, origin)
