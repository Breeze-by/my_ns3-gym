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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--ros-domain-id', type=int, required=True)
    parser.add_argument('--gazebo-port', type=int, required=True)
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

    spec = importlib.util.spec_from_file_location('mr3_contacts_fixture_module', MODULE)
    contacts_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = contacts_module
    spec.loader.exec_module(contacts_module)
    monitor = contacts_module.ContactMonitor(['tb1', 'tb2', 'tb3'], {'ground_plane::link::collision'})
    result = {'command': sys.argv, 'fixture_only': True, 'robot_count': 3,
              'model': str(MODEL), 'world': str(WORLD), 'cases': {}, 'success': False,
              'fixture_world': str(fixture_world),
              'state_plugin': {'namespace': '/gazebo', 'update_rate_hz': 10.0},
              'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (MODEL, URDF, WORLD, fixture_world, MODULE, Path(__file__))}}
    process = None
    node = None
    rclpy.init()
    log = (args.output_dir / 'launch.log').open('x')
    try:
        node = Node('mr3_native_contact_fixture', parameter_overrides=[Parameter('use_sim_time', value=True)])
        raw = {(robot, name): {'empty_count': 0, 'support_count': 0, 'support_pairs': [],
                              'pairs': [], 'last_source': None, 'empty_sources_first32': []}
               for robot in monitor.robot_names for name in contacts_module.CONTACT_COMPONENTS}
        pending = []

        def now():
            return node.get_clock().now().nanoseconds / 1e9

        def on_contact(robot, name, message):
            row = raw[(robot, name)]
            source = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
            row['last_source'] = source
            if not message.states:
                row['empty_count'] += 1
                if len(row['empty_sources_first32']) < 32:
                    row['empty_sources_first32'].append(source)
            retained, filtered = contacts_module.filter_non_support_contacts(
                robot, name, message.states, monitor.support_collision_names,
            )
            row['support_count'] += filtered
            for state in message.states:
                _, single_filtered = contacts_module.filter_non_support_contacts(
                    robot, name, [state], monitor.support_collision_names,
                )
                pair = [state.collision1_name, state.collision2_name]
                if single_filtered and pair not in row['support_pairs']:
                    row['support_pairs'].append(pair)
            for state in retained:
                pair = [state.collision1_name, state.collision2_name]
                if pair not in row['pairs']:
                    row['pairs'].append(pair)
            # /clock and contact callbacks are separate DDS streams. Buffer
            # source-future arrivals until the local clock watermark reaches
            # them, rather than rewriting their source time or permitting it.
            pending.append((source, robot, name, message))

        subscriptions = [node.create_subscription(
            ContactsState, topic,
            lambda message, robot=robot, name=name: on_contact(robot, name, message), 100,
        ) for robot in monitor.robot_names for name, topic in contacts_module.contact_topics(robot).items()]
        spawn_client = node.create_client(SpawnEntity, '/spawn_entity')
        delete_client = node.create_client(DeleteEntity, '/delete_entity')
        get_client = node.create_client(GetEntityState, '/gazebo/get_entity_state')
        set_client = node.create_client(SetEntityState, '/gazebo/set_entity_state')

        def spin():
            rclpy.spin_once(node, timeout_sec=0.05)
            receipt = now()
            ready = [entry for entry in pending if entry[0] <= receipt]
            pending[:] = [entry for entry in pending if entry[0] > receipt]
            for _, robot, name, message in ready:
                monitor.update(robot, name, message, receipt)

        def wait(predicate, timeout, label):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                spin()
                if process.poll() is not None:
                    raise RuntimeError(f'owned gzserver launch exited: {process.returncode}')
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
        for robot, x in [('tb1', -2.0), ('tb2', 0.0), ('tb3', 2.0)]:
            spawn(robot, MODEL.read_text(), x=x, namespace='/' + robot)
        wait(lambda: monitor.summary(now())['fresh'], 30, '18 live contact sources not ready')

        # Lift already-discovered robots briefly to obtain genuine empty contact
        # updates from wheel/caster sensors as well as base/lidar. This is an
        # isolated physical fixture, never a mapping or safe-navigation episode.
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
        support_keys = [(robot, component) for robot in monitor.robot_names
                        for component, spec in contacts_module.CONTACT_COMPONENTS.items()
                        if spec.support_eligible]
        wait(lambda: all(raw[key]['support_count'] > 0 for key in support_keys), 20,
             'normal wheel/caster support contact missing')
        wait(lambda: monitor.summary(now())['fresh'], 20, 'contact sources not fresh after settling')
        monitor.start(now())
        end = now() + 2.0
        wait(lambda: now() >= end, 15, 'two simulated seconds of monitoring did not complete')
        result['steady_monitoring'] = monitor.summary(now())
        if result['steady_monitoring']['ever_unhealthy']:
            raise RuntimeError('continuous contact freshness failed in steady fixture phase')
        result['settled_robot_poses'] = {}
        for robot in monitor.robot_names:
            request = GetEntityState.Request()
            request.name, request.reference_frame = robot, 'world'
            pose = call(get_client, request, 'settled pose ' + robot).state.pose
            ray_offset = rotate(pose.orientation, (-.064, 0, .121))
            result['settled_robot_poses'][robot] = {
                'model_position': [pose.position.x, pose.position.y, pose.position.z],
                'model_quaternion': [pose.orientation.x, pose.orientation.y,
                                     pose.orientation.z, pose.orientation.w],
                'actual_sdf_ray_height_m': pose.position.z + ray_offset[2],
                'declared_lidar_height_m': .131,
                'height_error_m': pose.position.z + ray_offset[2] - .131,
            }

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
        result['success'] = True
    except Exception as error:
        result['error'] = str(error)
    finally:
        if node is not None:
            result['contacts'] = {f'{robot}/{name}': row for (robot, name), row in raw.items()}
            result['final_monitoring'] = monitor.summary(node.get_clock().now().nanoseconds / 1e9)
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                    result['forced_kill'] = True
        if process is not None:
            result['launch_returncode'] = process.returncode
            if process.returncode != 0 or result.get('forced_kill'):
                result['success'] = False
                result.setdefault('error', 'owned launch did not exit cleanly')
        log.close()
        with (args.output_dir / 'fixture_result.json').open('x') as output:
            json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
        print(json.dumps({'success': result['success'], 'error': result.get('error'),
                          'result': str(args.output_dir / 'fixture_result.json')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
