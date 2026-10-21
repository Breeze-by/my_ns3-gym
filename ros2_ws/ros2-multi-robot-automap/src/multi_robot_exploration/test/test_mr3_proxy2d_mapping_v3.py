"""Artificial observation-consistency checks for the disabled V3 candidate.

No World, node, scene, truth loader, episode or saved run is used. Closed-cell
alternatives express numerical ambiguity, not a physical noise bound. These
checks retain both unknown-space costs and persistent-bias counterexamples.
"""

import math

import numpy as np
import pytest

from multi_robot_exploration.mr3_proxy2d_mapping_v3 import SensorMapperV3


def mapper():
    return SensorMapperV3((20, 20), .05, (0., 0.))


def arguments(**overrides):
    values = dict(sensor_pose=(0., .325, 0.), angles=np.array([0.]),
                  ranges=np.array([.299]), range_min=.12, range_max=10.)
    values.update(overrides)
    return values


def scan(instance, scan_id, **overrides):
    return instance.integrate(scan_id, **arguments(**overrides))


def snapshot(instance):
    return instance.grid(), instance.evidence(), instance.memory_bytes


def assert_unchanged(instance, before):
    np.testing.assert_array_equal(instance.grid(), before[0])
    np.testing.assert_array_equal(instance.evidence(), before[1])
    assert instance.memory_bytes == before[2]


def saturate_free(instance):
    for scan_id in range(4):
        assert scan(instance, scan_id, ranges=np.array([1.]), range_max=1.)
    assert instance.evidence()[6, 5] == -4 and instance.grid()[6, 5] == 0


def test_ordinary_off_grid_hit_confirms_occupancy_and_two_free_scans_confirm_free():
    instance = mapper()
    assert scan(instance, 0)
    assert instance.evidence()[6, 5] == 2 and instance.grid()[6, 5] == 100
    assert np.all(instance.evidence()[6, :5] == -1)
    assert np.all(instance.grid()[6, :5] == -1)
    assert scan(instance, 1)
    assert instance.evidence()[6, 5] == 4
    assert np.all(instance.evidence()[6, :5] == -2)
    assert np.all(instance.grid()[6, :5] == 0)


def test_first_hit_vetoes_saturated_free_persistently_and_second_hit_can_confirm():
    instance = mapper()
    saturate_free(instance)
    assert scan(instance, 4)
    assert instance.evidence()[6, 5] == 0 and instance.grid()[6, 5] == -1
    # A later scan that does not observe this cell must not remove the veto.
    assert scan(instance, 5, sensor_pose=(0., .725, 0.))
    assert instance.evidence()[6, 5] == 0 and instance.grid()[6, 5] == -1
    assert scan(instance, 6)
    assert instance.evidence()[6, 5] == 2 and instance.grid()[6, 5] == 100


@pytest.mark.parametrize("pose,angle,expected_free", [
    ((.5, 2.5, 0.), 0., [(2, 0), (2, 1)]),
    ((4.5, 2.5, 0.), math.pi, [(2, 4)]),
])
def test_one_axis_grid_tie_keeps_both_cells_unknown_independent_of_ray_side(
        pose, angle, expected_free):
    instance = SensorMapperV3((8, 8), 1., (0., 0.))
    distance = 2.5 if angle == 0 else 1.5
    for scan_id in range(8):
        scan(instance, scan_id, sensor_pose=pose, angles=np.array([angle]),
             ranges=np.array([distance]))
    assert instance.evidence()[2, 2] == instance.evidence()[2, 3] == 0
    assert instance.grid()[2, 2] == instance.grid()[2, 3] == -1
    assert not np.any(instance.grid() == 100)
    for cell in expected_free:
        assert instance.evidence()[cell] == -4 and instance.grid()[cell] == 0


def test_two_axis_corner_has_four_alternatives_and_creates_no_occupied_evidence():
    instance = SensorMapperV3((8, 8), 1., (0., 0.))
    scan(instance, 0, sensor_pose=(4., 4., -3 * math.pi / 4),
         ranges=np.array([math.sqrt(2)]))
    expected = np.zeros((8, 8), dtype=np.int8)
    expected[4, 4] = -1
    np.testing.assert_array_equal(instance.evidence(), expected)
    assert np.all(instance.grid()[2:4, 2:4] == -1)
    assert not np.any(instance.grid() == 100)


def test_zero_direction_component_does_not_resolve_grid_line_ambiguity():
    instance = SensorMapperV3((8, 8), 1., (0., 0.))
    # The horizontal ray lies on y=3: dy is exactly zero. Both row choices
    # remain alternatives even though the integer free walk uses row 3.
    scan(instance, 0, sensor_pose=(.5, 3., 0.), ranges=np.array([2.]))
    assert instance.evidence()[2, 2] == instance.evidence()[3, 2] == 0
    assert instance.grid()[2, 2] == instance.grid()[3, 2] == -1
    assert instance.evidence()[3, 0] == instance.evidence()[3, 1] == -1
    assert not np.any(instance.grid() == 100)


def test_negative_world_coordinates_use_the_declared_origin_for_closed_candidates():
    instance = SensorMapperV3((8, 8), 1., (-4., -4.))
    scan(instance, 0, sensor_pose=(.5, -1.5, 0.), angles=np.array([math.pi]),
         ranges=np.array([1.5]))
    assert instance.evidence()[2, 2] == instance.evidence()[2, 3] == 0
    assert instance.evidence()[2, 4] == -1
    assert not np.any(instance.grid() == 100)


@pytest.mark.parametrize("pose,angle,distance", [
    ((1.5, 2.5, 0.), math.pi, 1.5),  # raw x choices {-1,0}.
    ((1., 1., 0.), -3 * math.pi / 4, math.sqrt(2)),  # Four raw choices, one inside.
])
def test_clipping_out_of_map_alternatives_never_turns_raw_ambiguity_into_unique_hit(
        pose, angle, distance):
    instance = SensorMapperV3((8, 8), 1., (0., 0.))
    for scan_id in range(4):
        scan(instance, scan_id, sensor_pose=pose, angles=np.array([angle]),
             ranges=np.array([distance]))
    assert not np.any(instance.grid() == 100)
    target = (2, 0) if angle == math.pi else (0, 0)
    assert instance.evidence()[target] == 0 and instance.grid()[target] == -1


@pytest.mark.parametrize("ulps,expected_score,expected_value", [(1, 0, -1), (16, -4, 0)])
def test_small_negative_lattice_endpoint_uses_ulp_guard_without_metric_expansion(
        ulps, expected_score, expected_value):
    instance = SensorMapperV3((8, 8), 1., (0., 0.))
    for scan_id in range(4):
        scan(instance, scan_id, sensor_pose=(.5, 2.5, 0.),
             ranges=np.array([1.]), range_max=1.)
    assert instance.evidence()[2, 0] == -4
    endpoint = -ulps * np.spacing(1.)
    scan(instance, 4, sensor_pose=(1.5, 2.5, 0.), angles=np.array([math.pi]),
         ranges=np.array([1.5 - endpoint]))
    assert instance.evidence()[2, 0] == expected_score
    assert instance.grid()[2, 0] == expected_value
    assert not np.any(instance.grid() == 100)


def test_unique_hit_ambiguous_support_and_free_conflicts_are_order_independent():
    first, reordered = mapper(), mapper()
    ranges = np.array([.299, .3, .399, .299])
    scan(first, 0, angles=np.zeros(4), ranges=ranges)
    scan(reordered, 0, angles=np.zeros(4), ranges=ranges[[2, 1, 3, 0]])
    expected = np.zeros((20, 20), dtype=np.int8)
    expected[6, :5] = -1
    expected[6, 5] = expected[6, 7] = 2
    # Cell 6 is only an alternative of the x=.3 ambiguous endpoint. It gets
    # neither the longer ray's free vote nor an invented occupied vote.
    np.testing.assert_array_equal(first.evidence(), expected)
    np.testing.assert_array_equal(reordered.evidence(), expected)
    assert first.grid()[6, 6] == -1


def test_ambiguous_hits_preserve_prior_positive_evidence_without_adding_any():
    instance = mapper()
    scan(instance, 0)
    scan(instance, 1)
    for scan_id in range(2, 10):
        scan(instance, scan_id, ranges=np.array([.3]))
        assert instance.evidence()[6, 5] == 4 and instance.grid()[6, 5] == 100
        assert instance.evidence()[6, 6] == 0 and instance.grid()[6, 6] == -1


def test_duplicate_source_scan_is_idempotent_while_same_geometry_new_scan_accumulates():
    instance = mapper()
    assert scan(instance, 7) is True
    before = snapshot(instance)
    assert scan(instance, 7) is False
    assert_unchanged(instance, before)
    assert scan(instance, 8) is True
    assert instance.evidence()[6, 5] == 4
    assert np.all(instance.grid()[6, :5] == 0)


@pytest.mark.parametrize("changed", [
    {"sensor_pose": (0., .325, .01)}, {"angles": np.array([.01])},
    {"ranges": np.array([np.nextafter(.299, np.inf)])},
    {"range_min": .1}, {"range_max": 20.},
])
def test_scan_id_payload_conflicts_are_atomic(changed):
    instance = mapper()
    scan(instance, 7)
    before = snapshot(instance)
    with pytest.raises(ValueError):
        scan(instance, 7, **changed)
    assert_unchanged(instance, before)
    assert scan(instance, 7) is False
    assert scan(instance, 8) is True


def test_old_id_and_mutating_input_arrays_cannot_rewrite_consumed_scan():
    instance = mapper()
    values = arguments()
    instance.integrate(7, **values)
    before = snapshot(instance)
    with pytest.raises(ValueError):
        scan(instance, 6)
    values["ranges"][0] = .301
    with pytest.raises(ValueError):
        instance.integrate(7, **values)
    assert_unchanged(instance, before)
    assert scan(instance, 7) is False


def test_actual_new_free_observations_can_clear_a_persistent_hit_veto_and_a_ghost():
    instance = mapper()
    scan(instance, 0)
    scan(instance, 1)
    for scan_id, score, value in zip(range(2, 8), [3, 2, 1, 0, -1, -2],
                                    [100, 100, -1, -1, -1, 0]):
        scan(instance, scan_id, ranges=np.array([1.]), range_max=1.)
        assert instance.evidence()[6, 5] == score and instance.grid()[6, 5] == value
    # A new hit vetoes this negative prior; two subsequent new free scans can
    # confirm free again. An unobserved scan alone did not do so above.
    scan(instance, 8)
    assert instance.evidence()[6, 5] == 0 and instance.grid()[6, 5] == -1
    scan(instance, 9, ranges=np.array([1.]), range_max=1.)
    assert instance.evidence()[6, 5] == -1 and instance.grid()[6, 5] == -1
    scan(instance, 10, ranges=np.array([1.]), range_max=1.)
    assert instance.evidence()[6, 5] == -2 and instance.grid()[6, 5] == 0
    assert not np.any(instance.grid() == 100)


def test_max_range_grid_line_endpoint_is_only_free_not_ambiguous_hit_support():
    instance = SensorMapperV3((4, 4), 1., (0., 0.))
    for scan_id in range(2):
        scan(instance, scan_id, sensor_pose=(1.5, .5, 0.), angles=np.array([math.pi]),
             ranges=np.array([.5]), range_max=.5)
    assert instance.evidence()[0, 1] == -2 and instance.grid()[0, 1] == 0
    assert instance.evidence()[0, 0] == 0
    assert not np.any(instance.grid() == 100)


def test_continuous_two_mm_bias_can_still_clear_the_real_edge_instead_of_a_ghost():
    # Prescribed range .299 is followed by persistent .301. The mapper has no
    # access to whether this is noise, pose bias or an obstacle disappearing.
    instance = mapper()
    scan(instance, 0)
    scan(instance, 1)
    for scan_id in range(2, 8):
        scan(instance, scan_id, ranges=np.array([.301]))
    assert instance.evidence()[6, 5] == -2 and instance.grid()[6, 5] == 0
    assert instance.evidence()[6, 6] == 4 and instance.grid()[6, 6] == 100


def test_output_copies_and_fixed_beam_memory_remain_bounded_without_support_history():
    instance = mapper()
    assert instance.memory_bytes == 400
    assert instance.grid().dtype == instance.evidence().dtype == np.int8
    angles = np.zeros(3)
    expected_memory = 400 + 3 * 8 + 3 * 8 * 2 + 2 * 8
    for scan_id in range(32):
        scan(instance, scan_id, angles=angles, ranges=np.array([.299, .3, .399]))
        assert instance.memory_bytes == expected_memory
        assert np.max(np.abs(instance.evidence())) <= 4
    before = snapshot(instance)
    external_grid, external_evidence = instance.grid(), instance.evidence()
    external_grid.fill(0)
    external_evidence.fill(99)
    assert_unchanged(instance, before)


@pytest.mark.parametrize("invalid", [
    {"scan_id": -1}, {"scan_id": True}, {"scan_id": 8.0},
    {"sensor_pose": (0., 0.)}, {"sensor_pose": (1e100, 0., 0.)},
    {"angles": np.array([])}, {"angles": np.array([float("nan")])},
    {"ranges": np.array([.299, .301])}, {"ranges": np.array([1 + 2j])},
    {"ranges": np.array([.119])}, {"ranges": np.array([10.001])},
    {"range_min": 0.}, {"range_max": float("inf")},
    {"ranges": np.array([500_000.]), "range_max": 600_000.},
])
def test_invalid_input_and_bounded_workspace_reject_before_persistent_state_change(invalid):
    instance = mapper()
    scan(instance, 7)
    before = snapshot(instance)
    values = dict(invalid)
    scan_id = values.pop("scan_id", 8)
    with pytest.raises(ValueError):
        scan(instance, scan_id, **values)
    assert_unchanged(instance, before)
    assert scan(instance, 8) is True
