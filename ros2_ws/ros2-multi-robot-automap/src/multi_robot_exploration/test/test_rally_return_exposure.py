import math
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as c


@pytest.mark.parametrize('clearance, expected', [(.6, 0.), (.45, 0.), (.4, .5), (.35, 1.), (.2, 1.)])
def test_soft_exposure_prices_narrow_known_route_without_authorizing_motion(clearance, expected):
    route = ((1.05, 1.05), (2.05, 1.05))
    field = np.full((40, 40), clearance)
    before = field.copy()
    assert c.return_route_clearance_exposure(route, .1, (0., 0.), field) == pytest.approx(expected)
    assert np.array_equal(field, before)


def test_soft_exposure_retains_unavailable_geometry():
    field = np.full((40, 40), .6)
    assert c.return_route_clearance_exposure(((1., 1.),), .1, (0., 0.), field) == 0.
    assert math.isinf(c.return_route_clearance_exposure(((-1., 1.), (1., 1.)), .1, (0., 0.), field))


def test_funded_observer_prefers_earlier_arrival_with_both_complete_returns_qualified(monkeypatch):
    grid = np.zeros((200, 200), dtype=np.int16)
    grid[100:120, :] = 100
    grid[100:120, 92:108] = 0
    target = (5.05, 7.)
    poses = [c.RallyPose(5.05, 6.55, math.pi/2), c.RallyPose(5.05, 4.45, math.pi/2)]
    monkeypatch.setattr(c, 'rally_pose_candidates', lambda *args, **kwargs: poses)
    position = (5.05, 6.65)
    state = dict(mode='ACTIVE', energy=80., charge_x=5.05, charge_y=3.05,
        capacity=100., charge_target_fraction=.8, nominal_speed_mps=.18,
        idle_cost_per_sec=.02, move_cost_per_m=1., return_path_factor=2.,
        return_safety_margin=8., charge_duration_sec=6.)
    assigned = c.assign_rally_poses(grid, .05, (0., 0.), {'tb1': position}, target,
        battery_states={'tb1': state}, observer_robot='tb1')
    assert assigned == {'tb1': poses[0]}
    for pose in poses:
        cell = c.world_to_grid(pose.x, pose.y, .05, 0., 0.)
        target_cell = c.world_to_grid(*target, .05, 0., 0.)
        assert c.traversable_grid(grid, .05, c.RALLY_CLEARANCE_M)[cell]
        assert c.has_known_line_of_sight(grid, cell, target_cell)
        routes = c.qualified_return_candidates(grid, .05, (0., 0.), (pose.x, pose.y), (5.05, 3.05), .8)
        assert any(r['qualified'] for r in routes)
        approach = c.plan_rally_leg(pose, grid, .05, (0., 0.), position)[1]
        distance = sum(math.dist(a, b) for a, b in zip((position, *approach), approach))
        contact = min(r['path_distance_m'] for r in routes if r['qualified'])
        required = c.battery_assignment_required_energy(distance, contact, 1., .02, 2., .18, 8.) + .02*5.
        assert required < state['energy']


def test_new_tf_reprojects_cached_odometry_without_renewing_odometry_or_velocity():
    node = SimpleNamespace(task_state='RALLY', robot_odom_received_at={}, robot_tf_received_at={},
        robot_velocities={}, map_to_odom={'tb1': None}, robot_positions={}, robot_yaws={},
        goal_last_position={'tb1': None}, robot_states={'tb1': 'idle'}, rally_hold_started_at=5.,
        rally_targets={'tb1': c.RallyPose(1., 2., 0.)}, rally_position_tolerance=.35,
        rally_linear_tolerance=.05, rally_angular_tolerance=.1, now=lambda: 30.)
    odom = Odometry(); odom.header.stamp.sec = 10
    odom.pose.pose.position.x = 1.; odom.pose.pose.orientation.w = 1.
    c.HeadquartersControl.robot_odom_callback(node, odom, 'tb1')
    transform = TransformStamped(); transform.header.stamp.sec = 11
    transform.header.frame_id = 'tb1/map'; transform.child_frame_id = 'tb1/odom'
    transform.transform.translation.y = 2.; transform.transform.rotation.w = 1.
    c.HeadquartersControl.robot_tf_callback(node, TFMessage(transforms=[transform]), 'tb1')
    assert node.robot_positions['tb1'] == (1., 2.) and node.rally_hold_started_at == 5.
    assert node.robot_odom_received_at['tb1'] == 10. and node.robot_tf_received_at['tb1'] == 11.
    transform.header.stamp.sec = 12; transform.transform.translation.x = 1.
    c.HeadquartersControl.robot_tf_callback(node, TFMessage(transforms=[transform]), 'tb1')
    assert node.robot_positions['tb1'] == (2., 2.) and node.rally_hold_started_at is None
    assert node.rally_last_hold_reset['source_time'] == 10.
    assert node.robot_odom_received_at['tb1'] == 10. and node.robot_velocities['tb1'] == (0., 0.)


def test_returning_robot_map_veto_witness_retains_consulted_map_lease():
    grid = np.zeros((40, 40), dtype=np.int16)
    node = SimpleNamespace(now=lambda: 11., input_freshness_details=lambda: {},
        consumed_publisher=Mock(), battery_states={'tb2': {'charge_radius_m': .8}},
        map_data=grid, resolution=.1, origin=(0., 0.), map_received_at=10.,
        robot_map_received_at={'tb2': 10.5})
    local = dict(data=grid, resolution=.1, origin=(0., 0.))
    c.HeadquartersControl.record_return_map_veto(node, 'tb2', (1., 1.), (3., 3.), [], local)
    import json
    e = json.loads(node.consumed_publisher.publish.call_args[0][0].data)
    assert e['inputs']['tb2/map_snapshot'] == dict(source_time=10.5, age_sec=.5, ttl_sec=5.)
