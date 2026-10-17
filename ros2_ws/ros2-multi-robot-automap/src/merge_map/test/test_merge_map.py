from nav_msgs.msg import OccupancyGrid
import pytest

from merge_map.merge_map import merge_maps, merge_navigation_map


def make_grid(data, width, origin_x=0.0):
    grid = OccupancyGrid()
    grid.header.frame_id = "map"
    grid.info.resolution = 1.0
    grid.info.width = width
    grid.info.height = len(data) // width
    grid.info.origin.position.x = origin_x
    grid.info.origin.orientation.w = 1.0
    grid.data = data
    return grid


def test_merge_preserves_union_and_does_not_erase_conflicting_obstacles():
    first = make_grid([0, 0, -1, -1], 4)
    second = make_grid([100, 0, 0], 3, origin_x=1.0)

    merged = merge_maps([first, second])

    assert merged.header.frame_id == "map"
    assert merged.info.origin.orientation.w == 1.0
    assert list(merged.data) == [0, 100, 0, 0]


def test_merge_uses_grid_aligned_origin_offsets():
    first = make_grid([0, 0], 2, origin_x=-1.0)
    second = make_grid([100, 0], 2, origin_x=1.0)

    merged = merge_maps([first, second])

    assert merged.info.origin.position.x == -1.0
    assert merged.info.width == 4
    assert list(merged.data) == [0, 0, 100, 0]
    assert first.info.origin.position.x == -1.0
    assert second.info.origin.position.x == 1.0


def test_fractional_offsets_preserve_obstacle_area_and_unknown_edges():
    first = make_grid([-1, -1], 2)
    second = make_grid([100, 0], 2, origin_x=0.4)
    merged = merge_maps([first, second])
    assert merged.info.width == 3
    assert list(merged.data) == [100, 100, -1]


def test_fractional_free_cells_require_full_observation():
    first = make_grid([-1, -1], 2)
    second = make_grid([0, 0], 2, origin_x=0.4)
    assert list(merge_maps([first, second]).data) == [-1, 0, -1]


@pytest.mark.parametrize("invalid", ["rotation", "frame", "dimensions", "value"])
def test_invalid_map_contract_is_rejected(invalid):
    grid = make_grid([0], 1)
    if invalid == "rotation":
        grid.info.origin.orientation.z = 2 ** -0.5
        grid.info.origin.orientation.w = 2 ** -0.5
    elif invalid == "frame":
        grid.header.frame_id = "other_map"
    elif invalid == "dimensions":
        grid.info.height = 0
    else:
        grid.data = [101]
    with pytest.raises(ValueError):
        merge_maps([grid])


def test_merge_stamp_uses_latest_input_instead_of_robot_order():
    first = make_grid([0], 1)
    second = make_grid([0], 1)
    first.header.stamp.sec = 10
    second.header.stamp.sec = 2
    assert merge_maps([first, second]).header.stamp.sec == 10


def test_navigation_preserves_all_own_known_values_and_only_fills_own_unknown():
    own = make_grid([0, 100, -1, -1, -1], 5)
    shared = make_grid([100, 0, 100, 0, -1], 5)
    assert list(merge_maps([own, shared]).data) == [100, 100, 100, 0, -1]
    assert list(merge_navigation_map(own, shared).data) == [0, 100, 100, 0, -1]
    assert list(own.data) == [0, 100, -1, -1, -1]
    assert list(shared.data) == [100, 0, 100, 0, -1]


def test_fractional_navigation_keeps_own_occupied_area_and_requires_full_own_free():
    own = make_grid([100, 0, 0], 3, origin_x=.4)
    shared = make_grid([0, 100, 100, 100], 4)
    result = merge_navigation_map(own, shared)
    assert list(result.data) == [100, 100, 0, 100]
    # The final partly observed own-free cell is not promoted to own authority.
    assert result.data[-1] == 100


def test_navigation_does_not_depend_on_robot_seed_history_or_target():
    own, shared = make_grid([0, -1, 100], 3), make_grid([100, -1, 0], 3)
    assert merge_navigation_map(own, shared) == merge_navigation_map(own, shared)
    assert list(merge_navigation_map(own, shared).data) == [0, -1, 100]
