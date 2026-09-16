from nav_msgs.msg import OccupancyGrid

from merge_map.merge_map import merge_maps


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


def test_merge_preserves_union_and_clears_conflicting_dynamic_obstacles():
    first = make_grid([0, 0, -1, -1], 4)
    second = make_grid([100, 0, 0], 3, origin_x=1.0)

    merged = merge_maps([first, second])

    assert merged.header.frame_id == "map"
    assert merged.info.origin.orientation.w == 1.0
    assert list(merged.data) == [0, 0, 0, 0]


def test_merge_uses_grid_aligned_origin_offsets():
    first = make_grid([0, 0], 2, origin_x=-1.0)
    second = make_grid([100, 0], 2, origin_x=1.0)

    merged = merge_maps([first, second])

    assert merged.info.origin.position.x == -1.0
    assert merged.info.width == 4
    assert list(merged.data) == [0, 0, 100, 0]
    assert first.info.origin.position.x == -1.0
    assert second.info.origin.position.x == 1.0
