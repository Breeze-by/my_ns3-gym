"""Lossless evaluator-only navigation inputs; no publishers or control outputs."""
import base64
import gzip
import json
import time
from collections import Counter

from map_msgs.msg import OccupancyGridUpdate
from nav_msgs.msg import OccupancyGrid, Odometry, Path
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage


def navigation_topics(robot_count):
    topics = [('/merge_map', OccupancyGrid, True)]
    for i in range(1, robot_count + 1):
        prefix = f'/tb{i}/'
        topics.extend((prefix + suffix, message_type, latched) for suffix, message_type, latched in (
            ('map', OccupancyGrid, True), ('gateway/merge_map', OccupancyGrid, True),
            ('global_costmap/costmap', OccupancyGrid, True),
            ('global_costmap/costmap_updates', OccupancyGridUpdate, False),
            ('local_costmap/costmap', OccupancyGrid, True),
            ('local_costmap/costmap_updates', OccupancyGridUpdate, False),
            ('scan', LaserScan, False), ('odom', Odometry, False),
            ('tf', TFMessage, False), ('tf_static', TFMessage, True),
            ('plan', Path, False),
        ))
    return topics


class NavigationCapture:
    def __init__(self, node, output, robot_count):
        self.node = node
        self.stream = gzip.open(output, 'xt', compresslevel=1)
        self.counts = Counter()
        self.subscriptions = []
        for topic, message_type, latched in navigation_topics(robot_count):
            qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE if latched else ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.TRANSIENT_LOCAL if latched else DurabilityPolicy.VOLATILE)
            type_name = message_type.__module__.split('.')[0] + '/msg/' + message_type.__name__
            self.subscriptions.append(node.create_subscription(message_type, topic,
                lambda data, t=topic, kind=type_name: self.record(t, kind, data), qos, raw=True))

    def record(self, topic, type_name, data):
        self.stream.write(json.dumps(dict(topic=topic, type=type_name,
            received_sim_time=self.node.get_clock().now().nanoseconds / 1e9,
            received_wall_ns=time.time_ns(), cdr=base64.b64encode(data).decode('ascii')),
            separators=(',', ':'), allow_nan=False) + '\n')
        self.counts[topic] += 1

    def close(self):
        self.stream.close()
        print('NAVIGATION_CAPTURE_CLOSED ' + json.dumps(self.counts, sort_keys=True), flush=True)
