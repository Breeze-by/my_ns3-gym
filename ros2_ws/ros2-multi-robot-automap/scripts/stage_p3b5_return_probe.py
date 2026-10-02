"""Simulation-only exposure fixture; staging commands use the AP gateway.

Pause this runner's mission dispatch with DDS alive; stage two robots on disjoint
known-free legs, then leave native battery/Nav2 untouched during the outage.
Native battery observations only release the dispatcher guard after both
have charged. They are never used to choose or dispatch a navigation command.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import time


def gateway_fault_epoch(data, current_time):
    """Use the transport's blackout clock, not another node's phase receipt."""
    event = json.loads(data)
    if event.get('event') != 'fault_epoch':
        return None
    epoch = float(event['event_time'])
    if not math.isfinite(epoch) or not 0 <= epoch <= current_time:
        raise ValueError('Invalid gateway fault epoch')
    return epoch


def owned_coordinator(owner, domain, proc_root=Path('/proc')):
    """Identify exactly one descendant, never signal another ROS session."""
    parents = {}
    candidates = []
    for directory in proc_root.iterdir():
        if not directory.name.isdigit():
            continue
        try:
            pid = int(directory.name)
            parents[pid] = int((directory / 'stat').read_text().rsplit(')', 1)[1].split()[1])
            command = (directory / 'cmdline').read_bytes().split(b'\0')
            environment = (directory / 'environ').read_bytes().split(b'\0')
        except (OSError, ValueError):
            continue
        if (b'__node:=headquarters_control' in command
                and f'ROS_DOMAIN_ID={domain}'.encode() in environment):
            candidates.append(pid)
    found = []
    for pid in candidates:
        ancestor = pid
        seen = set()
        while ancestor in parents and ancestor not in seen:
            seen.add(ancestor)
            ancestor = parents[ancestor]
            if ancestor == owner:
                found.append(pid)
                break
    if len(found) != 1:
        raise RuntimeError(f'Expected one owned coordinator, found {found}')
    return found[0]


def known_staging_prefix(clear, resolution, origin, position, target, limit=.75, raw_grid=None):
    """Bounded visible leg toward a declared fixture point; never cross unknown."""
    from multi_robot_exploration.control import has_known_line_of_sight, world_to_grid
    distance = math.dist(position, target)
    if distance == 0:
        return None
    start = world_to_grid(*position, resolution, *origin)
    if not (0 <= start[0] < clear.shape[0] and 0 <= start[1] < clear.shape[1]):
        return None
    length = min(limit, distance)
    minimum = min(.5, distance)
    # Use the task stack's bounded known-free clearance escape when an
    # occupied cell near the current body inflates an otherwise free start.
    # Unknown/occupied starts still fail; never clear or edit the source map.
    if raw_grid is not None and clear[start] != 0:
        from multi_robot_exploration.control import plan_rally_leg, RallyPose
        point = tuple(p + (t-p) * length / distance for p, t in zip(position, target))
        pose, _ = plan_rally_leg(
            RallyPose(*point, 0.), raw_grid, resolution, origin, position,
            limit, visible_only=True,
        )
        if (pose is not None and math.dist(position, (pose.x, pose.y)) <= limit
                and math.dist((pose.x, pose.y), target) < distance):
            return pose.x, pose.y
        return None
    while length >= minimum - 1e-8:
        point = tuple(p + (t - p) * length / distance for p, t in zip(position, target))
        end = world_to_grid(*point, resolution, *origin)
        if (0 <= end[0] < clear.shape[0] and 0 <= end[1] < clear.shape[1]
                and has_known_line_of_sight(clear, start, end)):
            return point
        length -= resolution
    return None


def main():
    import numpy as np
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import OccupancyGrid, Odometry
    from rcl_interfaces.msg import ParameterType
    from rcl_interfaces.srv import GetParameters
    from std_msgs.msg import String
    from tf2_msgs.msg import TFMessage
    from multi_robot_exploration.control import (
        transform_point_2d, traversable_grid, world_to_grid,
    )
    from multi_robot_exploration.fault_model import STATE_TTL_SEC

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-pid', type=int, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.config.read_text())['return_staging']
    rclpy.init()
    node = Node('p3b5_remote_return_fixture', parameter_overrides=[Parameter('use_sim_time', value=True)])
    latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
    volatile = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
    stream = args.output.open('w', buffering=1)
    epoch = None
    coordinator = None
    pause_confirmed = False
    pause_query = None
    pause_client = node.create_client(GetParameters, '/headquarters_control/get_parameters')
    latest = {name: {} for name in fixture['poses']}
    batteries = {}
    handles = {}
    results = {}
    sent = set()
    staged = set()
    last_wait = {}
    saved_grids = set()
    clearance_cache = {}
    wall_start = time.monotonic()
    code = 1

    def now():
        return node.get_clock().now().nanoseconds / 1e9

    def record(event, **data):
        stream.write(json.dumps({'event': event, 'observer_time': now(), **data}) + '\n')

    def waiting(name, reason, **details):
        if now() - last_wait.get(name, -float('inf')) >= 5:
            record('staging_wait', robot=name, reason=reason, **details)
            last_wait[name] = now()

    def phase(message):
        nonlocal coordinator
        if message.data == 'EXPLORE' and coordinator is None:
            coordinator = owned_coordinator(args.owner_pid, os.environ['ROS_DOMAIN_ID'])
            record('coordinator_identified', pid=coordinator)

    def gateway_event(message):
        nonlocal epoch
        if epoch is None:
            value = gateway_fault_epoch(message.data, now())
            if value is not None:
                epoch = value
                record('gateway_epoch_observed', epoch=epoch)

    def received(name, kind, message):
        if kind == 'battery_state':
            message = json.loads(message.data)
            stamp = message['stamp_sec']
        elif kind == 'frame_state':
            transforms = [t for t in message.transforms
                          if t.header.frame_id.lstrip('/').endswith('map')
                          and t.child_frame_id.lstrip('/').endswith('odom')]
            if not transforms:
                return
            message = transforms[-1]
            stamp = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
        else:
            stamp = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
        latest[name][kind] = (stamp, message)

    def position(name):
        odom = latest[name]['pose_state'][1].pose.pose.position
        transform = latest[name]['frame_state'][1].transform
        return transform_point_2d(odom.x, odom.y, transform)

    def accepted(name, future):
        handle = future.result()
        if not handle.accepted:
            raise RuntimeError(f'{name}: staging goal rejected')
        handles[name] = handle
        handle.get_result_async().add_done_callback(lambda f, n=name: results.update({n: f.result().status}))
        record('staging_accepted', robot=name)

    clients = {name: ActionClient(node, NavigateToPose, f'/gateway/{name}/navigate_to_pose')
               for name in latest}
    node.create_subscription(String, '/task_state', phase, latched)
    node.create_subscription(String, '/gateway/message_events', gateway_event, 100)
    for name in latest:
        for kind, suffix, message_type, qos in (
            ('map_snapshot', 'map', OccupancyGrid, latched),
            ('pose_state', 'odom', Odometry, volatile),
            ('frame_state', 'tf', TFMessage, volatile),
            ('battery_state', 'battery_state', String, latched),
        ):
            node.create_subscription(message_type, f'/gateway/received/{name}/{suffix}',
                                     lambda m, n=name, k=kind: received(n, k, m), qos)
        node.create_subscription(String, f'/{name}/battery_state',
                                 lambda m, n=name: batteries.update({n: json.loads(m.data)}), latched)
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=.05)
            if time.monotonic() - wall_start > fixture['wall_timeout_sec']:
                raise TimeoutError('Fixture wall deadline exceeded')
            if epoch is None or coordinator is None:
                continue
            offset = now() - epoch
            if offset > fixture['stage_deadline_sec'] and len(staged) != len(latest):
                record('stage_deadline', staged=sorted(staged), received_types={n: sorted(x) for n, x in latest.items()})
                raise TimeoutError(f'Staging deadline exceeded; staged={sorted(staged)}')
            if not pause_confirmed:
                if pause_query is None and pause_client.service_is_ready():
                    request = GetParameters.Request()
                    request.names = ['enable_return_probe_pause']
                    pause_query = pause_client.call_async(request)
                if pause_query is None or not pause_query.done():
                    continue
                values = pause_query.result().values
                if (len(values) != 1 or values[0].type != ParameterType.PARAMETER_BOOL
                        or not values[0].bool_value):
                    raise RuntimeError('Owned coordinator did not enable simulation fixture pause')
                pause_confirmed = True
                record('coordinator_suspended', pid=coordinator, epoch=epoch,
                       method='simulation_only_dispatch_guard; DDS remains live')
            for name, target in fixture['poses'].items():
                if name in staged:
                    continue
                data = latest[name]
                leases = {kind: {'source_time': stamp, 'age_sec': now() - stamp,
                                  'ttl_sec': STATE_TTL_SEC[kind]} for kind, (stamp, _) in data.items()}
                if (len(leases) != 4 or any(not 0 <= x['age_sec'] < x['ttl_sec'] for x in leases.values())
                        or data['battery_state'][1]['mode'] != 'ACTIVE'):
                    waiting(name, 'input_lease_or_battery_mode', inputs=leases,
                            battery_mode=data.get('battery_state', (None, {}))[1].get('mode'))
                    continue
                current = position(name)
                if name in results:
                    if results[name] != 4:
                        raise RuntimeError(f'{name}: staging result {results[name]}')
                    if math.dist(current, target[:2]) <= fixture['position_tolerance_m']:
                        if name not in staged:
                            staged.add(name)
                            record('staged', robot=name, position=current, target=target, inputs=leases)
                        continue
                    # A completed intermediate leg is not a completed exposure.
                    del results[name]
                    handles.pop(name, None)
                    sent.remove(name)
                if name in sent:
                    continue
                if not clients[name].server_is_ready():
                    waiting(name, 'gateway_action_not_ready')
                    continue
                grid = data['map_snapshot'][1]
                if abs(grid.info.origin.orientation.z) > 1e-6:
                    raise RuntimeError('Rotated grid unsupported by fixture')
                raw = np.asarray(grid.data).reshape(grid.info.height, grid.info.width)
                map_stamp = data['map_snapshot'][0]
                if name not in clearance_cache or clearance_cache[name][0] != map_stamp:
                    clearance_cache[name] = (map_stamp, np.where(traversable_grid(raw, grid.info.resolution), 0, 100))
                clear = clearance_cache[name][1]
                origin = (grid.info.origin.position.x, grid.info.origin.position.y)
                start = world_to_grid(*current, grid.info.resolution, *origin)
                waypoint = known_staging_prefix(clear, grid.info.resolution, origin, current, target[:2],
                                                 fixture['navigation_leg_limit_m'], raw_grid=raw)
                end = world_to_grid(*target[:2], grid.info.resolution, *origin)
                if waypoint is None:
                    if name not in saved_grids:
                        import hashlib
                        snapshot = args.output.with_name(f'{name}_staging_map.npz')
                        np.savez_compressed(snapshot, raw=raw, resolution=grid.info.resolution, origin=origin,
                                            position=current, target=target, source_time=data['map_snapshot'][0])
                        record('staging_geometry_snapshot', robot=name, path=str(snapshot),
                               content_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest())
                        saved_grids.add(name)
                    waiting(name, 'no_clear_known_prefix', current_position=current, target=target, inputs=leases,
                            start_cell=start, end_cell=end)
                    continue
                leases = {kind: {'source_time': stamp, 'age_sec': now() - stamp,
                                  'ttl_sec': STATE_TTL_SEC[kind]} for kind, (stamp, _) in data.items()}
                if any(not 0 <= x['age_sec'] < x['ttl_sec'] for x in leases.values()):
                    continue
                goal = NavigateToPose.Goal()
                goal.pose.header.frame_id = 'map'
                goal.pose.header.stamp = node.get_clock().now().to_msg()
                goal.pose.pose.position.x, goal.pose.pose.position.y = waypoint
                goal.pose.pose.orientation.z = math.sin(target[2] / 2)
                goal.pose.pose.orientation.w = math.cos(target[2] / 2)
                sent.add(name)
                record('staging_requested', robot=name, target=target, waypoint=waypoint,
                       current_position=current, inputs=leases, map_source_time=map_stamp)
                clients[name].send_goal_async(goal).add_done_callback(lambda f, n=name: accepted(n, f))
            if len(staged) == len(latest) and all(batteries.get(n, {}).get('charge_count', 0) >= 1 for n in latest):
                record('both_charged', staged=sorted(staged), batteries=batteries)
                code = 0
                break
    except (KeyboardInterrupt, ExternalShutdownException):
        record('interrupted')
    except Exception as error:
        record('fixture_failed', reason=repr(error))
    finally:
        if coordinator is not None and pause_confirmed:
            # The coordinator belongs to the still-running parent experiment.
            try:
                if owned_coordinator(args.owner_pid, os.environ['ROS_DOMAIN_ID']) == coordinator:
                    os.kill(coordinator, signal.SIGUSR2)
                    record('coordinator_resumed', pid=coordinator, method='owned_SIGUSR2')
            except (OSError, RuntimeError):
                pass
        stream.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
