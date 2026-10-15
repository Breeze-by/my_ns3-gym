"""Offline native-message callback profile; no ROS node or simulator starts."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter

from nav_msgs.msg import OccupancyGrid
from test_mr3_information import bridge


SOURCE = (
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/"
    "multi_robot_exploration/mr3_information.py"
)
FREEZE = "d6ce831"
code = subprocess.check_output(["git", "show", f"{FREEZE}:{SOURCE}"])
with tempfile.TemporaryDirectory(prefix="mr3-sync-profile-") as directory:
    path = Path(directory) / "information.py"
    path.write_bytes(code)
    spec = importlib.util.spec_from_file_location("mr3_frozen_information_profile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    node = bridge()
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
    fixture = json.dumps({name: module.map_payload(grid)
                          for name, grid in node.local_maps.items()},
                         sort_keys=True, separators=(",", ":")).encode()
    timings = []
    for iteration in range(5):
        started = perf_counter()
        module.IdealInformation.publish_maps(node)
        timings.append(perf_counter() - started)
    print(json.dumps({
        "kind": "offline_callback_profile_not_simulator_or_training_throughput",
        "source_freeze": FREEZE, "source_path": SOURCE,
        "fixture_sha256": hashlib.sha256(fixture).hexdigest(),
        "fixture": "3 full 238x198 free grids, .05m, stamp1s, origins(-6+i*.05,-5)",
        "publisher": "in-memory message collector; no DDS or ROS node",
        "publish_maps_wall_sec": timings,
    }, sort_keys=True))
