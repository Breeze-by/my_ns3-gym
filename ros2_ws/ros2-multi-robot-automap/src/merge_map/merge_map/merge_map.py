import math

import numpy as np

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy


def merge_maps(maps, frame_id="map"):
    """Merge aligned occupancy grids and clear stale occupied evidence."""
    if not maps:
        raise ValueError("At least one occupancy grid is required")

    resolution = maps[0].info.resolution
    if resolution <= 0:
        raise ValueError("Map resolution must be positive")
    if any(
        not math.isclose(grid.info.resolution, resolution) for grid in maps
    ):
        raise ValueError("All occupancy grids must use the same resolution")

    min_x = min(grid.info.origin.position.x for grid in maps)
    min_y = min(grid.info.origin.position.y for grid in maps)
    offsets = [
        (
            round((grid.info.origin.position.x - min_x) / resolution),
            round((grid.info.origin.position.y - min_y) / resolution),
        )
        for grid in maps
    ]
    width = max(
        offset_x + grid.info.width
        for grid, (offset_x, _) in zip(maps, offsets)
    )
    height = max(
        offset_y + grid.info.height
        for grid, (_, offset_y) in zip(maps, offsets)
    )
    merged = np.full((height, width), -1, dtype=np.int16)

    for grid, (offset_x, offset_y) in zip(maps, offsets):
        incoming = np.asarray(grid.data, dtype=np.int16)
        expected_size = grid.info.width * grid.info.height
        if incoming.size != expected_size:
            raise ValueError(
                "Occupancy grid data size does not match its dimensions"
            )
        incoming = incoming.reshape(grid.info.height, grid.info.width)
        region = merged[
            offset_y:offset_y + grid.info.height,
            offset_x:offset_x + grid.info.width,
        ]
        incoming_known = incoming >= 0
        only_incoming_known = incoming_known & (region < 0)
        both_known = incoming_known & (region >= 0)
        region[only_incoming_known] = incoming[only_incoming_known]
        # A free ray observation clears stale occupied evidence such as another
        # robot's former position. Static walls remain occupied when the other
        # maps are unknown or also observe them as occupied.
        region[both_known] = np.minimum(
            region[both_known], incoming[both_known]
        )

    merged_map = OccupancyGrid()
    merged_map.header.stamp = maps[-1].header.stamp
    merged_map.header.frame_id = frame_id
    merged_map.info.map_load_time = maps[-1].info.map_load_time
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


class MergeMapNode(Node):
    def __init__(self):
        super().__init__("merge_map_node")
        self.frame_id = self.declare_parameter("frame_id", "map").value
        self.output_topic = self.declare_parameter(
            "output_topic", "/merge_map"
        ).value
        self.robot_count = self.declare_parameter("robot_count", 3).value
        self.input_topic_template = self.declare_parameter(
            "input_topic_template", "/tb{index}/map"
        ).value

        qos = QoSProfile(depth=10)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        qos.reliability = ReliabilityPolicy.RELIABLE
        self.publisher = self.create_publisher(
            OccupancyGrid, self.output_topic, qos
        )
        self.maps = [None] * self.robot_count
        self.map_subscriptions = []
        for index in range(self.robot_count):
            topic = self.input_topic_template.format(index=index + 1)
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
