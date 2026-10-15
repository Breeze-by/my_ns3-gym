"""Offline bounded-worker callback profile; no ROS node or simulator starts."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from time import perf_counter, sleep

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from test_mr3_information import bridge
from multi_robot_exploration.mr3_information import IdealInformation, map_payload


results = []
for iteration in range(5):
    node = bridge()
    node.map_executor = ThreadPoolExecutor(max_workers=1)
    for index, name in enumerate(node.names):
        grid = OccupancyGrid()
        grid.header.frame_id = "map"
        grid.header.stamp.sec = 1
        grid.info.width = 238
        grid.info.height = 198
        grid.info.resolution = .05
        grid.info.origin.position.x = -6. + index * .05
        grid.info.origin.position.y = -5.
        grid.info.origin.orientation.w = 1.
        grid.data = [0] * (238 * 198)
        node.local_maps[name] = grid
        node.local_map_versions[name] = 1
        odometry, transform = Odometry(), TransformStamped()
        odometry.header.stamp.sec = transform.header.stamp.sec = 2
        odometry.pose.pose.orientation.w = transform.transform.rotation.w = 1.
        node.local_odometry[name] = odometry
        node.local_transforms[name] = transform
    fixture = json.dumps({name: map_payload(grid) for name, grid in node.local_maps.items()},
                         sort_keys=True, separators=(",", ":")).encode()
    started = perf_counter()
    IdealInformation.publish_maps(node)
    capture = perf_counter() - started
    state_durations = []
    while node.map_future is not None and not node.map_future.done():
        started = perf_counter()
        IdealInformation.publish_states(node)
        state_durations.append(perf_counter() - started)
        sleep(.002)
    node.finish_maps()
    node.map_executor.shutdown(wait=True)
    results.append({
        "capture_callback_wall_sec": capture,
        "worker_wall_sec": node.map_diagnostics["worker_wall_sec"],
        "publish_callback_wall_sec": node.map_diagnostics["publish_wall_sec"],
        "state_callback_wall_sec_max": max(state_durations, default=0.),
        "state_callbacks_while_map_pending": len(state_durations),
    })
print(json.dumps({
    "kind": "offline_callback_profile_not_simulator_or_training_throughput",
    "fixture_sha256": hashlib.sha256(fixture).hexdigest(),
    "publisher": "in-memory message collector; no DDS or ROS node",
    "clock": "fixed 2s fixture; timings are perf_counter wall seconds",
    "results": results,
}, sort_keys=True))
