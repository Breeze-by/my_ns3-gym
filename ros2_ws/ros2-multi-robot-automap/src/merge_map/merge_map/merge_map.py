import math

import numpy as np

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy


NAVIGATION_COMPOSITION_VERSION = "mr3-own-known-shared-unknown-v1"


def _resample_grid(grid, rows, columns, min_x, min_y, resolution):
    """Conservative positive-area projection onto a declared output lattice."""
    incoming = np.asarray(grid.data, dtype=np.int16)
    expected_size = grid.info.width * grid.info.height
    if incoming.size != expected_size:
        raise ValueError("Occupancy grid data size does not match its dimensions")
    incoming = incoming.reshape(grid.info.height, grid.info.width)
    if np.any((incoming < -1) | (incoming > 100)):
        raise ValueError("Occupancy values must be -1 or between 0 and 100")
    offset_x = (min_x - grid.info.origin.position.x) / resolution
    offset_y = (min_y - grid.info.origin.position.y) / resolution
    first_column = np.floor(columns + offset_x + 1e-9).astype(int)
    last_column = np.ceil(columns + offset_x + 1.0 - 1e-9).astype(int) - 1
    first_row = np.floor(rows + offset_y + 1e-9).astype(int)
    last_row = np.ceil(rows + offset_y + 1.0 - 1e-9).astype(int) - 1
    fully_free = np.ones(rows.shape, dtype=bool)
    resampled = np.full(rows.shape, -1, dtype=np.int16)
    for sample_row, sample_column in (
        (first_row, first_column), (first_row, last_column),
        (last_row, first_column), (last_row, last_column),
    ):
        inside = ((sample_row >= 0) & (sample_row < grid.info.height)
                  & (sample_column >= 0) & (sample_column < grid.info.width))
        sample = np.full(rows.shape, -1, dtype=np.int16)
        sample[inside] = incoming[sample_row[inside], sample_column[inside]]
        fully_free &= inside & (sample >= 0) & (sample < 50)
        resampled = np.maximum(resampled, sample)
    resampled[(resampled < 50) & ~fully_free] = -1
    return resampled


def merge_maps(maps, frame_id="map"):
    """
    Merge common-frame grids conservatively, including fractional offsets.

    A free cell must be fully observed as free. Any overlapping occupied
    evidence wins a conflict; this merger cannot identify dynamic obstacles.
    Rotated maps require registration and are rejected explicitly.
    """
    if not maps:
        raise ValueError("At least one occupancy grid is required")

    resolution = maps[0].info.resolution
    if not math.isfinite(resolution) or resolution <= 0:
        raise ValueError("Map resolution must be positive")
    if any(
        not math.isclose(grid.info.resolution, resolution) for grid in maps
    ):
        raise ValueError("All occupancy grids must use the same resolution")

    for grid in maps:
        if grid.header.frame_id.lstrip("/") != frame_id.lstrip("/"):
            raise ValueError("All occupancy grids must share the output frame")
        if grid.info.width <= 0 or grid.info.height <= 0:
            raise ValueError("Occupancy grid dimensions must be positive")
        origin = grid.info.origin
        if not all(math.isfinite(v) for v in (origin.position.x, origin.position.y)):
            raise ValueError("Occupancy grid origin must be finite")
        q = origin.orientation
        if (
            any(not math.isfinite(v) or abs(v) > 1e-6 for v in (q.x, q.y, q.z))
            or not math.isclose(abs(q.w), 1.0, abs_tol=1e-6)
        ):
            raise ValueError("Rotated occupancy grids require registration")

    min_x = min(grid.info.origin.position.x for grid in maps)
    min_y = min(grid.info.origin.position.y for grid in maps)
    max_x = max(grid.info.origin.position.x + grid.info.width * resolution for grid in maps)
    max_y = max(grid.info.origin.position.y + grid.info.height * resolution for grid in maps)
    width = math.ceil((max_x - min_x) / resolution - 1e-9)
    height = math.ceil((max_y - min_y) / resolution - 1e-9)
    merged = np.full((height, width), -1, dtype=np.int16)

    rows, columns = np.indices((height, width))
    for grid in maps:
        # Each output cell intersects at most two input rows and columns.
        # Occupancy is conservative over every positive-area intersection;
        # free evidence requires the entire output cell to be covered.
        resampled = _resample_grid(grid, rows, columns, min_x, min_y, resolution)
        merged = np.maximum(merged, resampled)

    merged_map = OccupancyGrid()
    latest = max(maps, key=lambda grid: grid.header.stamp.sec * 10**9 + grid.header.stamp.nanosec)
    merged_map.header.stamp = latest.header.stamp
    merged_map.header.frame_id = frame_id
    merged_map.info.map_load_time = latest.info.map_load_time
    merged_map.info.resolution = resolution
    merged_map.info.width = width
    merged_map.info.height = height
    source_origin = maps[0].info.origin
    merged_map.info.origin.position.x = min_x
    merged_map.info.origin.position.y = min_y
    merged_map.info.origin.position.z = source_origin.position.z
    merged_map.info.origin.orientation.x = source_origin.orientation.x
    merged_map.info.origin.orientation.y = source_origin.orientation.y
    merged_map.info.origin.orientation.z = source_origin.orientation.z
    merged_map.info.origin.orientation.w = source_origin.orientation.w
    if merged_map.info.origin.orientation.w == 0.0:
        merged_map.info.origin.orientation.w = 1.0
    merged_map.data = merged.ravel().tolist()
    return merged_map


def merge_navigation_map(own, delivered_shared, frame_id="map"):
    """Preserve observed own cells; use delivered sharing only for own unknown.

    This is an explicitly different navigation composition from the global
    occupied-wins evaluation map. It neither edits either input nor clears a
    cell by robot pose/history. Every own occupied overlap remains occupied;
    own free authority requires a fully observed output cell.
    """
    navigation = merge_maps([own, delivered_shared], frame_id)
    rows, columns = np.indices((navigation.info.height, navigation.info.width))
    observed_own = _resample_grid(
        own, rows, columns, navigation.info.origin.position.x,
        navigation.info.origin.position.y, navigation.info.resolution)
    conservative = np.asarray(navigation.data, dtype=np.int16).reshape(rows.shape)
    navigation.data = np.where(observed_own >= 0, observed_own, conservative).ravel().tolist()
    return navigation


class MergeMapNode(Node):
    def __init__(self):
        super().__init__("merge_map_node")
        self.frame_id = self.declare_parameter("frame_id", "map").value
        self.output_topic = self.declare_parameter(
            "output_topic", "/merge_map"
        ).value
        self.robot_count = self.declare_parameter("robot_count", 3).value

        qos = QoSProfile(depth=10)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        qos.reliability = ReliabilityPolicy.RELIABLE
        self.publisher = self.create_publisher(
            OccupancyGrid, self.output_topic, qos
        )
        self.maps = [None] * self.robot_count
        self.map_subscriptions = []
        for index in range(self.robot_count):
            topic = f"/tb{index + 1}/map"
            self.map_subscriptions.append(
                self.create_subscription(
                    OccupancyGrid,
                    topic,
                    lambda msg, idx=index: self.map_callback(msg, idx),
                    qos,
                )
            )

    def map_callback(self, msg, index):
        self.maps[index] = msg
        if all(self.maps):
            try:
                self.publisher.publish(merge_maps(self.maps, self.frame_id))
            except ValueError as error:
                self.get_logger().error(str(error))


def main(args=None):
    rclpy.init(args=args)
    node = MergeMapNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
