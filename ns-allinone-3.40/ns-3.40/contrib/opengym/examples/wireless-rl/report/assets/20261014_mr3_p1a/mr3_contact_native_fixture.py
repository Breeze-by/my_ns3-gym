#!/usr/bin/python3
"""Isolated three-robot Gazebo contact fixture; no Nav2/exploration is launched.

Run from a system ROS Humble terminal. Evidence/log paths are never overwritten.
The only process group stopped by this script is the one it starts itself.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS_ROOT = ROOT / 'ros2_ws/ros2-multi-robot-automap'
MODEL = ROS_ROOT / 'src/multi_robot/models/turtlebot3_waffle/model.sdf'
URDF = ROS_ROOT / 'src/multi_robot/urdf/turtlebot3_waffle.urdf'
WORLD = ROS_ROOT / 'src/multi_robot/worlds/p1c_open.world'
MODULE = ROS_ROOT / 'src/multi_robot_exploration/multi_robot_exploration/mr3_contacts.py'


def prepare_fixture_world(destination):
    with destination.open('xb') as output:
        output.write(WORLD.read_bytes())
    return destination


def rotate(q, point):
    # Unit quaternion rotation; Gazebo state poses supply the full collision pose.
    x, y, z = point
    tx = 2 * (q.y * z - q.z * y)
    ty = 2 * (q.z * x - q.x * z)
    tz = 2 * (q.x * y - q.y * x)
    return (x + q.w * tx + q.y * tz - q.z * ty,
            y + q.w * ty + q.z * tx - q.x * tz,
            z + q.w * tz + q.x * ty - q.y * tx)


def stationary_pose_window(rows):
    """Require a fresh sampled1s window, bounding full3D pose and orientation.

    Reported vertical velocity remains evidence; pose variation independently
    bounds actual scanner height while planar and angular speeds must be low.
    """
    if len(rows) < 2:
        return False
    cutoff = rows[-1]['source_time_sec'] - 1.0
    index = 0
    while index + 1 < len(rows) and rows[index + 1]['source_time_sec'] <= cutoff:
        index += 1
    window = rows[index:]
    if any(row['source_time_sec'] <= 0 or not all(math.isfinite(value) for value in (
            [row['source_time_sec'], row['receipt_time_sec'], row['planar_speed_m_s'],
             row['angular_speed_rad_s']] + row['position'] + row['quaternion']))
           for row in window):
        return False
    if window[-1]['source_time_sec'] - window[0]['source_time_sec'] < 1.0:
        return False
    if any(row['planar_speed_m_s'] >= .005 or row['angular_speed_rad_s'] >= .02
           or not 0 <= row['receipt_time_sec'] - row['source_time_sec'] <= .5
           for row in window):
        return False
    if any(not 0 < b['source_time_sec'] - a['source_time_sec'] <= .5
           for a, b in zip(window, window[1:])):
        return False
    span = math.sqrt(sum((max(row['position'][axis] for row in window)
                          - min(row['position'][axis] for row in window))**2
                         for axis in range(3)))
    if span > .001:
        return False
    for index, first in enumerate(window):
        a = first['quaternion']
        for second in window[index + 1:]:
            b = second['quaternion']
            norm = math.sqrt(sum(v*v for v in a) * sum(v*v for v in b))
            if not math.isfinite(norm) or norm <= 0:
                return False
            dot = abs(sum(x*y for x, y in zip(a, b))) / norm
            if 2 * math.acos(min(1.0, dot)) > .002:
                return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--ros-domain-id', type=int, required=True)
    parser.add_argument('--gazebo-port', type=int, required=True)
    parser.add_argument('--contact-transport', choices=['raw', 'compact'], default='raw')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    fixture_world = prepare_fixture_world(args.output_dir / 'contact_fixture.world')
    # Bind-test the selected Gazebo port; do not connect to an unrelated server.
    with socket.socket() as test_socket:
        test_socket.bind(('127.0.0.1', args.gazebo_port))
    os.environ.update(ROS_DOMAIN_ID=str(args.ros_domain_id),
                      GAZEBO_MASTER_URI=f'http://127.0.0.1:{args.gazebo_port}',
                      ROS_LOCALHOST_ONLY='1', PYTHONNOUSERSITE='1')
    os.environ['GAZEBO_MODEL_PATH'] = os.pathsep.join([
        str(ROS_ROOT / 'src/multi_robot/models'), os.environ.get('GAZEBO_MODEL_PATH', ''),
    ])
    import rclpy
    from gazebo_msgs.msg import ContactsState
    from gazebo_msgs.srv import SpawnEntity, DeleteEntity, GetEntityState, SetEntityState
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from std_msgs.msg import String
    from rosidl_runtime_py.convert import message_to_ordereddict
    from multi_robot_exploration.mr3_task_contract import audit_lidar_slice_invariance

    spec = importlib.util.spec_from_file_location('mr3_contacts_fixture_module', MODULE)
    contacts_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = contacts_module
    spec.loader.exec_module(contacts_module)
    monitor = contacts_module.ContactMonitor(
        ['tb1', 'tb2', 'tb3'], {'ground_plane::link::collision'},
        compact=args.contact_transport == 'compact')
    result = {'command': sys.argv, 'fixture_only': True, 'robot_count': 3,
              'model': str(MODEL), 'world': str(WORLD), 'cases': {}, 'success': False,
              'fixture_world': str(fixture_world),
              'state_plugin': {'namespace': '/gazebo', 'update_rate_hz': 10.0},
              'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (MODEL, URDF, WORLD, fixture_world, MODULE, Path(__file__))}}
    if monitor.compact:
        for path in (ROS_ROOT / 'src/multi_robot/src/mr3_contact_reducer.cpp',
                     ROS_ROOT / 'src/multi_robot/include/multi_robot/contact_reducer.hpp',
                     ROS_ROOT / 'install/multi_robot/lib/multi_robot/mr3_contact_reducer'):
            result['source_sha256'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    process = None
    reducer = None
    node = None
    executor = None
    rclpy.init()
    log = (args.output_dir / 'launch.log').open('x')
    try:
        node = Node('mr3_native_contact_fixture', parameter_overrides=[Parameter('use_sim_time', value=True)])
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        raw = {(robot, name): {'empty_count': 0, 'support_count': 0,
                              'last_support_source': None, 'support_pairs': [],
                              'pairs': [], 'last_source': None, 'empty_sources_first32': [],
                              'first_non_support_sample': None}
               for robot in monitor.robot_names for name in contacts_module.CONTACT_COMPONENTS}
        pending = []
        transport_failures = []
        processing = {'callback_count': 0, 'callback_wall_sec': 0.0,
                      'max_callback_wall_sec': 0.0, 'max_callback_source_age_sec': 0.0,
                      'pending_peak': 0, 'drain_wall_sec': 0.0}
        result['lidar_slice_invariance'] = audit_lidar_slice_invariance(WORLD, .02, .25, .131)
        if not result['lidar_slice_invariance']['invariant']:
            raise RuntimeError('fixture world has a geometry slice transition in [.02,.25]m')

        def now():
            return node.get_clock().now().nanoseconds / 1e9

        def on_contact(robot, name, message):
            callback_begin = time.perf_counter()
            row = raw[(robot, name)]
            source = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
            row['last_source'] = source
            processing['max_callback_source_age_sec'] = max(
                processing['max_callback_source_age_sec'], now() - source)
            if not message.states:
                row['empty_count'] += 1
                if len(row['empty_sources_first32']) < 32:
                    row['empty_sources_first32'].append(source)
            retained, filtered = contacts_module.filter_non_support_contacts(
                robot, name, message.states, monitor.support_collision_names,
            )
            row['support_count'] += filtered
            if filtered:
                row['last_support_source'] = source
            retained_pairs = {(state.collision1_name, state.collision2_name) for state in retained}
            if retained and row['first_non_support_sample'] is None:
                row['first_non_support_sample'] = {
                    'source_time_sec': source,
                    'state': message_to_ordereddict(retained[0]),
                }
            all_pairs = {(state.collision1_name, state.collision2_name) for state in message.states}
            for pair in sorted(all_pairs - retained_pairs):
                if list(pair) not in row['support_pairs']:
                    row['support_pairs'].append(list(pair))
            for pair in sorted(retained_pairs):
                if list(pair) not in row['pairs']:
                    row['pairs'].append(list(pair))
            # /clock and contact callbacks are separate DDS streams. Buffer
            # source-future arrivals until the local clock watermark reaches
            # them, rather than rewriting their source time or permitting it.
            pending.append((source, robot, name, message))
            processing['pending_peak'] = max(processing['pending_peak'], len(pending))
            elapsed = time.perf_counter() - callback_begin
            processing['callback_count'] += 1
            processing['callback_wall_sec'] += elapsed
            processing['max_callback_wall_sec'] = max(processing['max_callback_wall_sec'], elapsed)

        subscriptions = [node.create_subscription(
            ContactsState, topic,
            lambda message, robot=robot, name=name: on_contact(robot, name, message), 100,
        ) for robot in monitor.robot_names for name, topic in contacts_module.contact_topics(
            robot, compact=monitor.compact).items()]
        failure_subscription = node.create_subscription(
            String, '/exploration_failure', lambda msg: transport_failures.append(msg.data),
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))
        spawn_client = node.create_client(SpawnEntity, '/spawn_entity')
        delete_client = node.create_client(DeleteEntity, '/delete_entity')
        get_client = node.create_client(GetEntityState, '/gazebo/get_entity_state')
        set_client = node.create_client(SetEntityState, '/gazebo/set_entity_state')

        def spin():
            executor.spin_once(timeout_sec=0.05)
            drain_begin = time.perf_counter()
            receipt = now()
            ready = [entry for entry in pending if entry[0] <= receipt]
            pending[:] = [entry for entry in pending if entry[0] > receipt]
            for _, robot, name, message in ready:
                monitor.update(robot, name, message, receipt)
            processing['drain_wall_sec'] += time.perf_counter() - drain_begin

        def wait(predicate, timeout, label):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                spin()
                if process.poll() is not None:
                    raise RuntimeError(f'owned gzserver launch exited: {process.returncode}')
                if reducer is not None and reducer.poll() is not None:
                    raise RuntimeError(f'owned contact reducer exited: {reducer.returncode}')
                if transport_failures:
                    raise RuntimeError('contact transport failure: ' + transport_failures[0])
                if predicate():
                    return
            raise TimeoutError(label)

        def call(client, request, label):
            wait(lambda: client.service_is_ready(), 30, label + ' unavailable')
            future = client.call_async(request)
            wait(future.done, 30, label + ' timeout')
            response = future.result()
            if not response.success:
                raise RuntimeError(label + ' rejected: ' + getattr(response, 'status_message', ''))
            return response

        def spawn(name, xml, x=0.0, y=0.0, z=0.01, namespace=''):
            request = SpawnEntity.Request()
            request.name, request.xml, request.robot_namespace = name, xml, namespace
            request.initial_pose.position.x = x
            request.initial_pose.position.y = y
            request.initial_pose.position.z = z
            request.initial_pose.orientation.w = 1.0
            request.reference_frame = 'world'
            call(spawn_client, request, 'spawn ' + name)

        process = subprocess.Popen([
            'ros2', 'launch', 'gazebo_ros', 'gzserver.launch.py', f'world:={fixture_world}',
            'seed:=101', 'verbose:=true', 'server_required:=true',
        ], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        if monitor.compact:
            reducer = subprocess.Popen([
                'ros2', 'run', 'multi_robot', 'mr3_contact_reducer',
                '--ros-args', '-p', 'use_sim_time:=true',
            ], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for robot, x in [('tb1', -2.0), ('tb2', 0.0), ('tb3', 2.0)]:
            spawn(robot, MODEL.read_text(), x=x, namespace='/' + robot)
        wait(lambda: monitor.summary(now())['fresh'], 30, '18 live contact sources not ready')

        # Lift already-discovered robots briefly to obtain genuine empty contact
        # updates from wheel/caster sensors as well as base/lidar. This is an
        # isolated physical fixture, never a mapping or safe-navigation episode.
        support_keys = [(robot, component) for robot in monitor.robot_names
                        for component, spec in contacts_module.CONTACT_COMPONENTS.items()
                        if spec.support_eligible]
        support_before_lift = {key: raw[key]['support_count'] for key in support_keys}
        for robot in monitor.robot_names:
            request = GetEntityState.Request()
            request.name, request.reference_frame = robot, 'world'
            state = call(get_client, request, 'get ' + robot).state
            state.name = robot
            state.reference_frame = 'world'
            state.pose.position.z += 0.4
            state.twist.linear.x = state.twist.linear.y = state.twist.linear.z = 0.0
            state.twist.angular.x = state.twist.angular.y = state.twist.angular.z = 0.0
            set_request = SetEntityState.Request()
            set_request.state = state
            call(set_client, set_request, 'lift ' + robot)
        wait(lambda: all(row['empty_count'] > 0 for row in raw.values()), 15,
             'not every one of the 18 sensors produced an empty state')
        after_lift_sim_time = now()
        wait(lambda: all(raw[key]['support_count'] > support_before_lift[key]
                         and raw[key]['last_support_source'] is not None
                         and raw[key]['last_support_source'] > after_lift_sim_time
                         for key in support_keys), 20,
             'new normal wheel/caster support contact after lift missing')
        result['support_after_lift'] = {
            f'{robot}/{component}': {
                'before_count': support_before_lift[(robot, component)],
                'after_count': raw[(robot, component)]['support_count'],
                'last_source': raw[(robot, component)]['last_support_source'],
                'post_lift_source_cutoff': after_lift_sim_time,
            } for robot, component in support_keys
        }
        # Lifting produces real physical motion. A pair of support samples does
        # not establish settlement: require a fresh bounded-pose source window
        # for each robot, without setting poses or changing the physics model.
        result['settlement_samples'] = {robot: [] for robot in monitor.robot_names}
        settled = {robot: False for robot in monitor.robot_names}
        settlement_deadline = time.monotonic() + 30.0
        while not all(settled.values()):
            if time.monotonic() >= settlement_deadline:
                raise TimeoutError('settlement_timeout: no fresh1simsec bounded-pose window for all3')
            for robot in monitor.robot_names:
                request = GetEntityState.Request()
                request.name, request.reference_frame = robot + '::base_scan', 'world'
                response = call(get_client, request, 'settlement state ' + robot)
                source = response.header.stamp.sec + response.header.stamp.nanosec / 1e9
                wait(lambda: now() >= source, 2, 'settlement source clock watermark missing')
                receipt = now()
                if receipt - source > .5:
                    raise RuntimeError('settlement state source stale: ' + robot)
                state = response.state
                linear = math.sqrt(sum(getattr(state.twist.linear, axis)**2 for axis in 'xyz'))
                planar = math.hypot(state.twist.linear.x, state.twist.linear.y)
                angular = math.sqrt(sum(getattr(state.twist.angular, axis)**2 for axis in 'xyz'))
                row = {'source_time_sec': source, 'receipt_time_sec': receipt,
                       'entity': robot + '::base_scan',
                       'linear_speed_m_s': linear, 'angular_speed_rad_s': angular,
                       'planar_speed_m_s': planar,
                       'linear_twist_m_s': [getattr(state.twist.linear, axis) for axis in 'xyz'],
                       'angular_twist_rad_s': [getattr(state.twist.angular, axis) for axis in 'xyz'],
                       'position': [getattr(state.pose.position, axis) for axis in 'xyz'],
                       'quaternion': [getattr(state.pose.orientation, axis) for axis in 'xyzw']}
                result['settlement_samples'][robot].append(row)
                settled[robot] = stationary_pose_window(result['settlement_samples'][robot])
            next_sample = now() + .05
            wait(lambda: now() >= next_sample, 2, 'settlement sampling clock did not advance')
        wait(lambda: monitor.summary(now())['fresh'], 20, 'contact sources not fresh after settling')
        monitor.start(now())
        steady_begin = (now(), time.monotonic(), time.process_time())
        end = now() + 2.0
        wait(lambda: now() >= end, 15, 'two simulated seconds of monitoring did not complete')
        result['steady_monitoring'] = monitor.summary(now())
        result['steady_timing'] = {
            'sim_sec': now() - steady_begin[0],
            'wall_sec': time.monotonic() - steady_begin[1],
            'fixture_cpu_sec': time.process_time() - steady_begin[2],
        }
        if result['steady_monitoring']['ever_unhealthy']:
            raise RuntimeError('continuous contact freshness failed in steady fixture phase')
        result['settled_robot_poses'] = {}
        for robot in monitor.robot_names:
            request = GetEntityState.Request()
            request.name, request.reference_frame = robot + '::base_scan', 'world'
            response = call(get_client, request, 'settled pose ' + robot)
            source = response.header.stamp.sec + response.header.stamp.nanosec / 1e9
            wait(lambda: now() >= source, 2, 'settled pose clock watermark missing')
            if now() - source > .5:
                raise RuntimeError('settled pose source stale: ' + robot)
            pose = response.state.pose
            ray_offset = rotate(pose.orientation, (-.064, 0, .121))
            normal = rotate(pose.orientation, (0, 0, 1))
            vertical_span = 10.0 * math.sqrt(max(0.0, 1.0 - normal[2]**2))
            actual_height = pose.position.z + ray_offset[2]
            beam_envelope = [actual_height - vertical_span, actual_height + vertical_span]
            variation_bound = .001 + (10.0 + math.hypot(.064, .121)) * math.sin(.002)
            result['settled_robot_poses'][robot] = {
                'entity': robot + '::base_scan',
                'source_time_sec': source, 'receipt_time_sec': now(),
                'sensor_link_position': [pose.position.x, pose.position.y, pose.position.z],
                'sensor_link_quaternion': [pose.orientation.x, pose.orientation.y,
                                     pose.orientation.z, pose.orientation.w],
                'actual_sdf_ray_height_m': pose.position.z + ray_offset[2],
                'declared_lidar_height_m': .131,
                'height_error_m': pose.position.z + ray_offset[2] - .131,
                'lidar_plane_normal': normal,
                'beam_height_envelope_at10m': beam_envelope,
                'sampled_window_vertical_variation_bound_m': variation_bound,
            }
            if abs(result['settled_robot_poses'][robot]['height_error_m']) > .002:
                raise RuntimeError('settled laser height differs from declared slice by over2mm: ' + robot)
            if beam_envelope[0] <= 0:
                raise RuntimeError('settled laser beam envelope crosses ground: ' + robot)
            if (beam_envelope[0] - variation_bound < .02
                    or beam_envelope[1] + variation_bound > .25):
                raise RuntimeError('settled laser beam outside verified slice band: ' + robot)

        # Each fixture is a real static sphere, just inside its target's side
        # boundary. Query the collision entity (not a hard-coded robot pose) to
        # account for actual settlement and the caster's ball joint orientation.
        placements = {
            'base': ((0.1385, 0, 0), 0.012),
            'lidar': ((0.0568, 0, 0), 0.012),
            'wheel_left': ((0, 0, 0.012), 0.006),
            'wheel_right': ((0, 0, -0.012), 0.006),
            'caster_back_left': ((0.007, 0, 0), 0.004),
            'caster_back_right': ((0.007, 0, 0), 0.004),
        }
        for component, (offset, radius) in placements.items():
            component_spec = contacts_module.CONTACT_COMPONENTS[component]
            own = f'tb1::{component_spec.link}::{component_spec.collision}'
            request = GetEntityState.Request()
            request.name, request.reference_frame = own, 'world'
            pose = call(get_client, request, 'get ' + own).state.pose
            dx, dy, dz = rotate(pose.orientation, offset)
            position = (pose.position.x + dx, pose.position.y + dy, pose.position.z + dz)
            fixture = 'mr3_fixture_' + component
            xml = (f"<sdf version='1.7'><model name='{fixture}'><static>true</static>"
                   f"<link name='wall'><collision name='collision'><geometry><sphere>"
                   f"<radius>{radius}</radius></sphere></geometry></collision></link></model></sdf>")
            fixture_collision = fixture + '::wall::collision'
            spawn(fixture, xml, *position)
            try:
                wait(lambda: any(own in pair and fixture_collision in pair
                                 for pair in raw[('tb1', component)]['pairs']), 10,
                     'real non-support contact not observed for ' + component)
                result['cases'][component] = {'success': True, 'own_collision': own,
                    'fixture_collision': fixture_collision, 'fixture_position': position,
                    'fixture_radius': radius,
                    'observed_pairs': raw[('tb1', component)]['pairs']}
            finally:
                request = DeleteEntity.Request()
                request.name = fixture
                call(delete_client, request, 'delete ' + fixture)
        final_health = monitor.summary(now())
        if not final_health['fresh'] or final_health['ever_unhealthy']:
            raise RuntimeError('full fixture interval contact monitoring was interrupted')
        result['success'] = True
    except Exception as error:
        result['error'] = str(error)
    finally:
        if node is not None:
            result['contacts'] = {f'{robot}/{name}': row for (robot, name), row in raw.items()}
            result['final_monitoring'] = monitor.summary(node.get_clock().now().nanoseconds / 1e9)
            result['processing'] = processing
            result['transport_failures'] = transport_failures
            executor.remove_node(node)
            executor.shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                result['forced_termination'] = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                    result['forced_kill'] = True
        if process is not None:
            result['launch_returncode'] = process.returncode
            if process.returncode != 0 or result.get('forced_termination') or result.get('forced_kill'):
                result['success'] = False
                result.setdefault('error', 'owned launch did not exit cleanly')
        if reducer is not None:
            if reducer.poll() is None:
                os.killpg(reducer.pid, signal.SIGINT)
                try:
                    reducer.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    result['reducer_forced_termination'] = True
                    os.killpg(reducer.pid, signal.SIGTERM)
                    reducer.wait(timeout=10)
            result['reducer_returncode'] = reducer.returncode
            if reducer.returncode != 0 or result.get('reducer_forced_termination'):
                result['success'] = False
                result.setdefault('error', 'contact reducer did not exit cleanly')
        log.close()
        native_failures = [line for line in (args.output_dir / 'launch.log').read_text(
            errors='replace').splitlines() if (
                'process has died' in line or 'failed to terminate' in line
                or "sending signal 'SIGTERM'" in line or "sending signal 'SIGKILL'" in line
            )]
        result['native_launch_failures'] = native_failures
        summaries = [line.split('MR3_CONTACT_REDUCER_SUMMARY ', 1)[1]
                     for line in (args.output_dir / 'launch.log').read_text(
                         errors='replace').splitlines() if 'MR3_CONTACT_REDUCER_SUMMARY ' in line]
        if monitor.compact:
            if len(summaries) != 1:
                result['success'] = False
                result.setdefault('error', 'exactly one reducer summary required')
            else:
                result['reducer_audit'] = json.loads(summaries[0])
                audit = result['reducer_audit']
                if (len(audit['topics']) != 18 or not audit['publication_sequence_supported']
                        or any(row['received'] != row['published'] or row['sequence_gaps']
                               or row['sequence_duplicates'] or row['sequence_regressions']
                               or row['sequence_unavailable'] or row['publisher_count'] != 1
                               for row in audit['topics'].values())):
                    result['success'] = False
                    result.setdefault('error', 'reducer source sequence/count audit failed')
        if native_failures:
            result['success'] = False
            result.setdefault('error', 'native child exit/escalation failure')
        with (args.output_dir / 'fixture_result.json').open('x') as output:
            json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
        print(json.dumps({'success': result['success'], 'error': result.get('error'),
                          'result': str(args.output_dir / 'fixture_result.json')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
