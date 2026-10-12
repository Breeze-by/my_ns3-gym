"""Typed DDS, real ActionServer/Futures and actual timer-driven fleet planning.

The server models action lifecycle only. This test grants no native navigation,
physics, charging or task-success credit.
"""
import json
import time
import copy
import pytest

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionServer, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.task import Future
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.global_control import GlobalHeadquartersControl
from p2c_navigation_capture import NavigationCapture
from p2c_global_audit import global_mission_audit


def test_real_dds_worker_dispatch_result_and_cancel_ownership(tmp_path):
    rclpy.init(args=['--ros-args', '-p', 'robot_count:=1', '-p', 'use_sim_time:=true',
                    '-p', 'enable_battery:=true', '-p', 'enable_rally:=false'])
    node = GlobalHeadquartersControl()
    source = Node('global_dds_lifecycle_source')
    observer = Node('global_dds_read_only_capture')
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(source)
    executor.add_node(observer)
    executor.add_node(node)
    latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                        durability=DurabilityPolicy.TRANSIENT_LOCAL)
    publishers = {
        'clock': source.create_publisher(Clock, '/clock', 10),
        'fused': source.create_publisher(OccupancyGrid, '/merge_map', latched),
        'map': source.create_publisher(OccupancyGrid, '/gateway/received/tb1/map', 1),
        'odom': source.create_publisher(Odometry, '/gateway/received/tb1/odom', 1),
        'tf': source.create_publisher(TFMessage, '/gateway/received/tb1/tf', 1),
        'battery': source.create_publisher(String, '/gateway/received/tb1/battery_state', latched),
        'native_battery': source.create_publisher(String, '/tb1/battery_state', latched),
    }
    capture = NavigationCapture(observer, tmp_path / 'navigation_inputs.jsonl.gz', 1)
    native = []
    source.create_subscription(String, '/tb1/battery_state',
        lambda msg: native.append(dict(topic='/tb1/battery_state', data=json.loads(msg.data))), latched)
    events, goals = [], []
    source.create_subscription(String, '/gateway/consumed',
        lambda msg: events.append(json.loads(msg.data)), 100)

    async def execute(handle):
        completion = Future()
        goals.append((handle, completion))
        await completion
        if handle.is_cancel_requested:
            handle.canceled()
        else:
            handle.succeed()
        return NavigateToPose.Result()

    server = ActionServer(source, NavigateToPose, '/gateway/tb1/navigate_to_pose', execute,
        cancel_callback=lambda _: CancelResponse.ACCEPT, callback_group=ReentrantCallbackGroup())
    sim = 10.

    def publish():
        stamp = Clock()
        stamp.clock.sec = int(sim)
        stamp.clock.nanosec = round((sim - int(sim)) * 1e9)
        publishers['clock'].publish(stamp)
        # State source stamps must never be injected ahead of the actual clock.
        for _ in range(20):
            executor.spin_once(timeout_sec=.003)
            if node.now() >= sim - 1e-8:
                break
        grid = OccupancyGrid()
        # Repeat one original stationary snapshot. Repetition does not renew
        # its lease; the actual clock and budget evaluation still advance.
        grid.header.stamp.sec = 10
        grid.header.frame_id = 'map'
        grid.info.width = grid.info.height = 80
        grid.info.resolution = .1
        grid.info.origin.orientation.w = 1.
        grid.data = [0] * 6400
        publishers['fused'].publish(grid)
        publishers['map'].publish(grid)
        odom = Odometry()
        odom.header.stamp = grid.header.stamp
        odom.pose.pose.position.x = odom.pose.pose.position.y = 4.25
        odom.pose.pose.orientation.w = 1.
        publishers['odom'].publish(odom)
        frame = TransformStamped()
        frame.header.stamp = grid.header.stamp
        frame.header.frame_id, frame.child_frame_id = 'map', 'odom'
        frame.transform.rotation.w = 1.
        publishers['tf'].publish(TFMessage(transforms=[frame]))
        state = dict(mode='ACTIVE', stamp_sec=10., energy=80., charge_x=4.25, charge_y=4.25,
            capacity=100., charge_target_fraction=.8, charge_radius_m=.8, move_cost_per_m=1.,
            idle_cost_per_sec=.02, return_path_factor=2., nominal_speed_mps=.18,
            return_safety_margin=8., charge_duration_sec=6.)
        publishers['battery'].publish(String(data=json.dumps(state)))
        publishers['native_battery'].publish(String(data=json.dumps(state)))

    def pump_until(predicate, wall_limit=12.):
        nonlocal sim
        deadline = time.monotonic() + wall_limit
        while time.monotonic() < deadline:
            sim += .005
            publish()
            for _ in range(8):
                executor.spin_once(timeout_sec=.003)
            time.sleep(.015)
            if predicate():
                return
        raise AssertionError(dict(phase=node.task_state, goals=len(goals), now=node.now(),
            sim=sim, use_sim_time=node.get_parameter('use_sim_time').value,
            positions=node.robot_positions, sources=node.input_freshness_details(),
            pending=list(node.navigation_tasks), events=events[-5:]))

    try:
        pump_until(lambda: len(goals) == 1 and node.navigation_tasks.get('tb1') is not None
                   and node.navigation_tasks['tb1'].handle is not None)
        task = node.navigation_tasks['tb1']
        assert task.proposal.kind == 'exploration'
        assert task.proposal.budget_time is not None
        assert task.proposal.required_energy < 80.
        node.return_probe_paused = True
        for _ in range(30):
            publish()
            executor.spin_once(timeout_sec=.005)
        assert len(goals) == 1 and node.navigation_tasks['tb1'] is task
        goals[0][1].set_result(True)
        pump_until(lambda: not node.navigation_tasks)
        assert node.successful_exploration_legs['tb1'] == 1
        node.return_probe_paused = False
        pump_until(lambda: len(goals) == 2 and node.navigation_tasks['tb1'].handle is not None)
        current = node.navigation_tasks['tb1']
        assert current.generation > task.generation
        node.return_probe_paused = True
        node.cancel_navigation('tb1', 'local_return')
        pump_until(lambda: goals[1][0].is_cancel_requested)
        assert node.navigation_tasks['tb1'] is current and len(goals) == 2
        goals[1][1].set_result(True)
        pump_until(lambda: not node.navigation_tasks)
        assert node.successful_exploration_legs['tb1'] == 1
        pump_until(lambda: sum(e.get('event') == 'coordinator_global_motion_closed' for e in events) == 2)
        assert any(e.get('event') == 'coordinator_global_motion_sent' for e in events)
        assert not any(e.get('event') == 'coordinator_global_planner_error' for e in events)
        capture.close()
        capture = None
        (tmp_path / 'ledger.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        (tmp_path / 'safety_events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in native))
        audit = global_mission_audit(tmp_path, True)
        assert audit['sent'] == audit['closed'] == 2
        assert audit['original_map_bindings'] >= 2 and not audit['pending_at_owned_shutdown']
        # The independent reader must reject changed budgets and generations.
        for field in ('required_energy','generation'):
            altered = copy.deepcopy(events)
            witness = next(e for e in altered if e.get('event')=='coordinator_global_motion_admission')
            witness[field] += 1
            (tmp_path / 'ledger.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in altered))
            with pytest.raises(AssertionError):
                global_mission_audit(tmp_path, True)
    finally:
        node.shutdown_requested = True
        for handle, future in goals:
            if not future.done():
                future.set_result(True)
        executor.shutdown(timeout_sec=5.)
        if capture is not None:
            capture.close()
        server.destroy()
        node.destroy_node()
        observer.destroy_node()
        source.destroy_node()
        rclpy.shutdown()
