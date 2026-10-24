"""Real bridge publication preserves received odometry for actor activity."""

import copy
import json
import math

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry

from test_mr3_adapter import make_adapter, stamp
from test_mr3_information import bridge
from multi_robot_exploration.mr3_information import IdealInformation, odom_payload


def received_pipeline():
    adapter, clock = make_adapter()
    information = bridge()
    information.state_sequence = adapter.state["sequence"]
    information.now = lambda: clock[0]
    observed = OccupancyGrid()
    observed.header.frame_id = "map"
    observed.header.stamp = stamp(clock[0])
    observed.info.resolution = .1
    observed.info.width = observed.info.height = 40
    observed.info.origin.position.x = observed.info.origin.position.y = -2.
    observed.info.origin.orientation.w = 1.
    observed.data = [0] * 1600
    information.local_maps = {name: copy.deepcopy(observed) for name in information.names}
    information.local_map_versions = dict.fromkeys(information.names, 1)
    IdealInformation.publish_maps(information)
    adapter.receive_map(information.map_publisher.messages[-1])
    for name in information.names:
        adapter.receive_local_map(name, information.received_map_publishers[name].messages[-1])
        adapter.receive_navigation_map(name, information.navigation_publishers[name].messages[-1])
    return information, adapter, clock


def sensors(information, now, distance, correction=0.):
    for index, name in enumerate(information.names):
        odometry, transform = Odometry(), TransformStamped()
        odometry.header.stamp = transform.header.stamp = stamp(now)
        odometry.header.frame_id = f"{name}/odom"
        odometry.child_frame_id = f"{name}/base_footprint"
        odometry.pose.pose.position.x = distance * (index + 1)
        odometry.pose.pose.orientation.w = 1.
        transform.header.frame_id = "map"
        transform.child_frame_id = f"{name}/odom"
        transform.transform.translation.x = index - 1. + correction
        transform.transform.rotation.w = 1.
        information.local_odometry[name] = odometry
        information.local_transforms[name] = transform


def publish_received(information, adapter):
    IdealInformation.publish_states(information)
    message = information.state_publisher.messages[-1]
    adapter.receive_states(message)
    return json.loads(message.data)


def test_received_bridge_odometry_reaches_activity_and_frozen_encoded_observation(monkeypatch):
    information, adapter, clock = received_pipeline()
    for now, distance, correction in ((1., 0., 0.), (1.2, .03, 0.), (1.4, .09, .4)):
        clock[0] = now
        sensors(information, now, distance, correction)
        received = publish_received(information, adapter)
        for index, name in enumerate(information.names):
            robot = received["robots"][index]
            original = odom_payload(information.local_odometry[name])
            assert robot["odometry"] == original
            assert robot["odometry"]["header"]["frame_id"] == f"{name}/odom"
            assert robot["odom_source_stamp"] == now
            assert robot["source_stamp"] == robot["received_stamp"] == now
            assert information.received.get("state", name).payload["odometry"] == original
    adapter.publish_observation()
    adapter.finish_observation()
    snapshot = adapter.snapshot
    assert snapshot["schema"] == "mr3-observation-v3"
    assert snapshot["source_stamp"] == 1.4
    for index, name in enumerate(information.names):
        robot = snapshot["robots"][index]
        activity = robot["activity"]
        assert activity["started_at"] == 1.
        assert activity["state_sequence"] == received["sequence"]
        assert activity["last_odom_source_stamp"] == 1.4
        assert activity["sample_count"] == 3 and activity["path_observation_complete"]
        assert math.isclose(activity["estimated_path_m"], .09 * (index + 1))
        assert activity["estimated_path_m"] > .05
        assert math.isclose(robot["x"], index - 1. + .4 + .09 * (index + 1))
    frozen = copy.deepcopy(snapshot)
    # New local sensors cannot reach the actor while logical delivery is blocked.
    clock[0] = 1.6
    sensors(information, 1.6, 9., 4.)
    monkeypatch.setattr(information.transport, "deliver", lambda *args, **kwargs: ())
    received = publish_received(information, adapter)
    for index, name in enumerate(information.names):
        robot = received["robots"][index]
        assert robot["odometry"]["header"]["stamp"] == {"sec": 1, "nanosec": 400000000}
        assert robot["source_stamp"] == robot["received_stamp"] == 1.4
        assert adapter.activity.snapshot(name) == frozen["robots"][index]["activity"] | {
            "state_sequence": received["sequence"]}
    assert adapter.snapshot == frozen
