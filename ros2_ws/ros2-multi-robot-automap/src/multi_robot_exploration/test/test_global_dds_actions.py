"""Typed DDS, real ActionServer/Futures and actual timer-driven fleet planning.

The server models action lifecycle only. This test grants no native navigation,
physics, charging or task-success credit.
"""
import json
import time
import copy
import math
import threading
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
from rclpy.serialization import deserialize_message
from rclpy.task import Future
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.global_control import GlobalHeadquartersControl
from p2c_navigation_capture import NavigationCapture
from p2c_global_audit import global_mission_audit


@pytest.mark.parametrize('late_acceptance', [False, True])
def test_real_dds_worker_dispatch_result_and_cancel_ownership(tmp_path, late_acceptance):
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
    captured_sources = set()
    original_record = capture.record

    def record(topic, kind, data):
        original_record(topic, kind, data)
        if topic.endswith('/odom'):
            message = deserialize_message(data, Odometry)
            captured_sources.add((topic, message.header.stamp.sec))
        elif topic.endswith('/tf'):
            message = deserialize_message(data, TFMessage)
            captured_sources.update((topic, transform.header.stamp.sec) for transform in message.transforms)

    capture.record = record
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
    state_source = 10.
    last_state_publish_wall = -math.inf
    held_responses = []
    original_response = node._goal_response

    def delayed_response(task, future):
        held_responses.append((task, future))

    if late_acceptance:
        # Delay only serialized consumption of the real acceptance Future.
        # The actual server and DDS continue running with the same owner.
        node._goal_response = delayed_response

    def publish():
        nonlocal last_state_publish_wall
        stamp = Clock()
        stamp.clock.sec = int(sim)
        stamp.clock.nanosec = round((sim - int(sim)) * 1e9)
        publishers['clock'].publish(stamp)
        # State source stamps must never be injected ahead of the actual clock.
        for _ in range(20):
            executor.spin_once(timeout_sec=.003)
            if node.now() >= sim - 1e-8:
                break
        # Keep fixture map traffic near its real rate, so the read-only
        # observer can service pose/TF before its map queue fills indefinitely.
        # The clock still advances; repeating a source never renews its lease.
        wall = time.monotonic()
        if wall-last_state_publish_wall < .5:
            return
        last_state_publish_wall = wall
        grid = OccupancyGrid()
        # Repeat one original stationary snapshot. Repetition does not renew
        # its lease; the actual clock and budget evaluation still advance.
        grid.header.stamp.sec = int(state_source)
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
        state = dict(mode='ACTIVE', stamp_sec=state_source, energy=80., charge_x=4.25, charge_y=4.25,
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
                   and (held_responses if late_acceptance else node.navigation_tasks['tb1'].handle is not None))
        task = node.navigation_tasks['tb1']
        assert task.proposal.kind == 'exploration'
        assert task.proposal.budget_time is not None
        assert task.proposal.required_energy < 80.
        node.return_probe_paused = True
        if late_acceptance:
            sim = state_source = 13.
            pump_until(lambda: node.robot_odom_received_at['tb1'] == 13.
                       and node.robot_tf_received_at['tb1'] == 13.
                       and node.battery_state_received_at['tb1'] == 13.
                       and node.map_received_at == 13.
                       and ('/gateway/received/tb1/odom', 13) in captured_sources
                       and ('/gateway/received/tb1/tf', 13) in captured_sources)
            assert task.sources['tb1/pose_state'] == 10. and not task.handle
            node._goal_response = original_response
            delayed_task, completed = held_responses.pop()
            assert delayed_task is task and completed.done()
            node.action_done_callbacks.put((lambda future: original_response(task, future), completed))
            node.action_done_guard.trigger()
            pump_until(lambda: task.handle is not None and any(
                event.get('event') == 'coordinator_global_motion_revalidated' for event in events))
            assert task.cancel_reason is None and task.sources['tb1/pose_state'] == 13.
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
        assert audit['current_revalidations'] == int(late_acceptance)
        assert audit['original_map_bindings'] >= 2 and not audit['pending_at_owned_shutdown']
        # The independent reader must reject changed budgets and generations.
        for field in ('required_energy','generation'):
            altered = copy.deepcopy(events)
            witness = next(e for e in altered if e.get('event')=='coordinator_global_motion_admission')
            witness[field] += 1
            (tmp_path / 'ledger.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in altered))
            with pytest.raises(AssertionError):
                global_mission_audit(tmp_path, True)
        if late_acceptance:
            altered = copy.deepcopy(events)
            witness = next(event for event in altered
                           if event.get('event') == 'coordinator_global_motion_revalidation')
            witness['requested_yaw'] += .2
            (tmp_path / 'ledger.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in altered))
            with pytest.raises(AssertionError, match='changed an issued goal'):
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


def test_real_dds_receipts_during_serial_work_apply_full_objects_without_renewing_sources():
    rclpy.init(args=['--ros-args', '-p', 'robot_count:=3', '-p', 'use_sim_time:=true',
                    '-p', 'enable_battery:=true', '-p', 'enable_rally:=true'])
    node = GlobalHeadquartersControl()
    node.return_probe_paused = True
    for timer in node.timers:
        timer.cancel()
    source = Node('global_dds_ingress_source')
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    executor.add_node(source)
    spin = threading.Thread(target=executor.spin)
    latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                        durability=DurabilityPolicy.TRANSIENT_LOCAL)
    clock = source.create_publisher(Clock, '/clock', 10)
    fused = source.create_publisher(OccupancyGrid, '/merge_map', 1)
    observation = source.create_publisher(String, '/gateway/received/target_observation', latched)
    detection = source.create_publisher(String, '/gateway/received/target_detection', latched)
    publishers = {robot:{kind:source.create_publisher(message, f'/gateway/received/{robot}/{kind}',
        latched if kind=='battery_state' else 1) for kind,message in
        (('map',OccupancyGrid),('odom',Odometry),('tf',TFMessage),('battery_state',String))}
        for robot in ('tb1','tb2','tb3')}
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    snapshots = {}

    def wait(predicate):
        deadline = time.monotonic() + 5.
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        raise AssertionError('DDS ingress condition did not close')

    def publish_clock(at):
        stamp = Clock()
        stamp.clock.sec = int(at)
        stamp.clock.nanosec = round((at-int(at))*1e9)
        clock.publish(stamp)
        wait(lambda: node.now() >= at-1e-8)

    def publish_states(at):
        grid = OccupancyGrid()
        grid.header.stamp.sec = int(at)
        grid.info.width = grid.info.height = 80
        grid.info.resolution = .1
        grid.info.origin.orientation.w = 1.
        grid.data = [0]*6400
        fused.publish(grid)
        observation.publish(String(data='EXPLORE'))
        for index,robot in enumerate(publishers):
            publishers[robot]['map'].publish(grid)
            odom = Odometry()
            odom.header.stamp.sec = int(at)
            odom.pose.pose.position.x = odom.pose.pose.position.y = (1.25,4.25,6.25)[index]
            odom.pose.covariance[0] = 17.+index
            yaw = (0.,.8,-2.6)[index]
            odom.pose.pose.orientation.z = math.sin(yaw/2)
            odom.pose.pose.orientation.w = math.cos(yaw/2)
            publishers[robot]['odom'].publish(odom)
            frame = TransformStamped()
            frame.header.stamp.sec = int(at)
            frame.header.frame_id,frame.child_frame_id='map','odom'
            frame.transform.translation.x = .25 if at==13. else 0.
            frame.transform.rotation.w=1.
            unrelated = TransformStamped()
            unrelated.header.frame_id,unrelated.child_frame_id='camera','optical'
            publishers[robot]['tf'].publish(TFMessage(transforms=[unrelated,frame]))
            state = dict(mode='ACTIVE',stamp_sec=at,energy=40.,charge_x=1.25,charge_y=1.25,
                capacity=100.,charge_target_fraction=.8,charge_radius_m=.8,move_cost_per_m=1.,
                idle_cost_per_sec=.02,return_path_factor=2.,nominal_speed_mps=.18,
                return_safety_margin=8.,charge_duration_sec=6.,retained_vector=[index,7])
            publishers[robot]['battery_state'].publish(String(data=json.dumps(state)))

    def held_serial_callback():
        snapshots['old'] = node._snapshot()
        entered.set()
        if not release.wait(4.):
            return
        snapshots['new'] = node._snapshot()
        finished.set()

    guard = node.create_guard_condition(held_serial_callback)
    spin.start()
    try:
        time.sleep(.3)
        publish_clock(10.)
        for _ in range(5):
            publish_states(10.)
            time.sleep(.04)
        wait(lambda: all(node.robot_odom_received_at[robot]==10.
                        and node.battery_state_received_at[robot]==10. for robot in publishers))
        guard.trigger()
        wait(entered.is_set)
        old = snapshots['old']
        assert old is not None and old.at_time==10.
        publish_clock(13.)
        for _ in range(3):
            publish_states(13.)
            time.sleep(.04)
        wait(lambda: len(node.received_snapshot_callbacks)>=13)
        with node.received_snapshot_lock:
            for robot in publishers:
                received = node.received_snapshot_callbacks[(f'/gateway/received/{robot}/tf', None)][1]
                assert len(received.transforms)==2 and received.transforms[0].child_frame_id=='optical'
        for robot in ('tb2','tb3'):
            detection.publish(String(data=json.dumps(dict(robot=robot,target_x=6.,target_y=6.,
                max_distance_m=3.,field_of_view_deg=90.,_gateway=dict(source_time=13.,delivery_time=13.)))))
            wait(lambda: ('/gateway/received/target_detection',robot) in node.received_snapshot_callbacks)
        detection.publish(String(data=json.dumps(dict(robot=[]))))
        # Clock and receipts advance, but actual mission state remains frozen.
        assert node.robot_positions==old.positions and node.map_received_at==10.
        assert node.target is None and old.sources['tb1/pose_state']==10.
        release.set()
        wait(finished.is_set)
        new = snapshots['new']
        assert new is not None and new.target==(6.,6.) and new.at_time==13.
        for index,robot in enumerate(publishers):
            assert new.sources[robot+'/pose_state']==new.sources[robot+'/frame_state']==13.
            assert new.sources[robot+'/battery_state']==new.sources[robot+'/map_snapshot']==13.
            assert node.robot_last_odom[robot].pose.covariance[0]==17.+index
            assert new.batteries[robot]['retained_vector']==[index,7]
            assert new.positions[robot][0]==old.positions[robot][0]+.25
        assert node.global_confirmations['tb2']==node.global_confirmations['tb3']==13.
        assert old.sources['tb1/pose_state']==10. and old.positions!=new.positions
        publish_clock(15.1)
        publish_states(13.)  # Repeating an old object cannot renew its source.
        checked = threading.Event()
        expired = {}
        def check_expired():
            expired['snapshot']=node._snapshot()
            checked.set()
        expiry_guard=node.create_guard_condition(check_expired)
        expiry_guard.trigger()
        wait(checked.is_set)
        assert expired['snapshot'] is None and not node.navigation_tasks
    finally:
        release.set()
        node.shutdown_requested=True
        executor.shutdown(timeout_sec=5.)
        spin.join(timeout=5.)
        node.destroy_node()
        source.destroy_node()
        rclpy.shutdown()
