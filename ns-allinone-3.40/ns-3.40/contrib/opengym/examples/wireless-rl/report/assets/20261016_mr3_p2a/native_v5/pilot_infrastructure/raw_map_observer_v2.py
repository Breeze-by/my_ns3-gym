#!/usr/bin/python3
"""PREPARED ONLY: finite read-only map/global-costmap diagnostic in one existing MR3 worker.

No application publisher, parameter change, service/action call, process signal,
TF transformation, truth subscription, or simulator control is present. Standard
rclpy's internal /parameter_events publisher is recorded as framework plumbing.
Raw grids are preserved as canonical map_payload JSON gzip files, not CNN rasters.
Asynchronous receipt time alone never establishes a native causal map binding.
"""

import argparse
from array import array
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time


WORKSPACE = Path('/home/zhuyulab/ns3-workspace')
ROS = WORKSPACE / 'ros2_ws/ros2-multi-robot-automap'
RUN = ROS / 'log/mr3_ppo/mr3_p2a_v5_pilot'
ROBOTS = ('tb1', 'tb2', 'tb3')
SOURCE_PATHS = (
    ROS / 'src/multi_robot_exploration/multi_robot_exploration/mr3_information.py',
    ROS / 'src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py',
    ROS / 'src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py',
    ROS / 'src/merge_map/merge_map/merge_map.py',
    ROS / 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py',
    *(ROS / f'src/multi_robot/params/nav2_params_{name}_0.yaml' for name in ROBOTS),
    *(ROS / f'install/multi_robot/share/multi_robot/params/nav2_params_{name}_0.yaml'
      for name in ROBOTS),
    Path('/opt/ros/humble/include/nav2_costmap_2d/nav2_costmap_2d/costmap_2d_publisher.hpp'),
    Path('/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/node.py'),
)
TRANSPORT_KEYS = (
    'RMW_IMPLEMENTATION', 'ROS_LOCALHOST_ONLY', 'FASTRTPS_DEFAULT_PROFILES_FILE',
    'SKIP_DEFAULT_XML', 'FASTDDS_DEFAULT_PROFILES_FILE', 'RMW_FASTRTPS_USE_QOS_FROM_XML',
    'RMW_FASTRTPS_PUBLICATION_MODE',
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def process_identity(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'parent': int(fields[1]), 'group': os.getpgid(pid),
            'session': os.getsid(pid), 'start_ticks': int(fields[19]), 'state': fields[0]}


def stamp(value):
    return {'sec': value.sec, 'nanosec': value.nanosec}


def map_payload(message):
    origin = message.info.origin
    return {'header': {'stamp': stamp(message.header.stamp),
                       'frame_id': message.header.frame_id},
            'info': {'map_load_time': stamp(message.info.map_load_time),
                     'resolution': message.info.resolution, 'width': message.info.width,
                     'height': message.info.height,
                     'origin': {'position': {key: getattr(origin.position, key)
                                             for key in ('x', 'y', 'z')},
                                'orientation': {key: getattr(origin.orientation, key)
                                                for key in ('x', 'y', 'z', 'w')}}},
            'data': list(message.data)}


def geometry_digest(payload):
    info = payload['info']
    cells = array('h', payload['data'])
    if cells.itemsize != 2:
        raise ValueError('geometry hash requires 16-bit signed array cells')
    if sys.byteorder != 'little':
        cells.byteswap()
    metadata = {'resolution': info['resolution'],
                'origin': [info['origin']['position'][key] for key in ('x', 'y')],
                'shape': [info['height'], info['width']]}
    digest = hashlib.sha256(canonical(metadata))
    digest.update(cells.tobytes())
    return digest.hexdigest()


def saved_actor_snapshot(directory):
    """Read only the latest complete line from a bounded append-only file suffix."""
    path = directory / 'transitions.jsonl'
    with path.open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        start = max(0, size - 2 * 1024 * 1024)
        stream.seek(start)
        data = stream.read(size - start)
    if start:
        boundary = data.find(b'\n')
        if boundary < 0:
            return None
        start += boundary + 1
        data = data[boundary + 1:]
    end = data.rfind(b'\n')
    if end < 0:
        return None
    complete = data[:end]
    previous = complete.rfind(b'\n')
    line = complete[previous + 1:]
    record = json.loads(line)
    snapshot = record['snapshot']
    return {'snapshot': snapshot, 'file_size_when_read': size,
            'complete_line_start_offset': start + previous + 1,
            'complete_line_end_offset': start + end + 1, 'line_sha256': sha(line + b'\n'),
            'watermarks': record.get('info', {}).get('watermarks'),
            'read_monotonic_ns': time.monotonic_ns()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-directory', type=Path, required=True)
    parser.add_argument('--domain-id', type=int, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=float, default=15.)
    args = parser.parse_args()
    if not 2. <= args.wall_seconds <= 20. or not 0 <= args.domain_id <= 232:
        parser.error('require 2 <= wall-seconds <= 20 and one supported domain')
    if sys.executable != '/usr/bin/python3' or os.environ.get('PYTHONNOUSERSITE') != '1':
        parser.error('use /usr/bin/python3 with PYTHONNOUSERSITE=1 in sourced system ROS')
    episode, output = args.episode_directory.resolve(), args.output_directory.resolve()
    episode.relative_to(RUN / 'native')
    if output.parent != RUN or not output.name.startswith('raw_map_observer_'):
        parser.error('output must be a NEW raw_map_observer_* child of the ignored pilot')
    supervisor_bytes = (episode / 'supervisor_metadata.json').read_bytes()
    native_bytes = (episode / 'metadata.json').read_bytes()
    supervisor, native = json.loads(supervisor_bytes), json.loads(native_bytes)
    epoch = supervisor['epoch']
    if native['epoch'] != epoch or supervisor['domain_id'] != args.domain_id:
        parser.error('explicit domain/epoch does not match the selected existing worker')
    worker = process_identity(supervisor['worker_identity']['pid'])
    if (worker['start_ticks'] != supervisor['worker_identity']['start_ticks']
            or worker['state'] in ('Z', 'X')):
        parser.error('selected worker PID identity is no longer current')
    transport = native['transport_environment']
    for key in TRANSPORT_KEYS:
        if transport.get(key) is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = str(transport[key])
    profile = Path(transport['FASTRTPS_DEFAULT_PROFILES_FILE'])
    if sha(profile.read_bytes()) != transport['profile_sha256']:
        parser.error('worker DDS profile bytes differ from its saved metadata')
    os.environ['ROS_DOMAIN_ID'] = str(args.domain_id)
    output.mkdir(exist_ok=False)
    for name in ('maps', 'observations'):
        (output / name).mkdir()
    events = (output / 'events.jsonl').open('x', buffering=1)
    started = time.monotonic()
    deadline = started + args.wall_seconds
    done = threading.Event()

    def hard_deadline():
        if not done.wait(max(0., deadline - time.monotonic())):
            os._exit(124)  # Own observer only; no signal or interaction with any worker.

    watchdog = threading.Thread(target=hard_deadline, daemon=True)
    watchdog.start()
    topics = []
    for name in ROBOTS:
        topics.extend([(f'/{name}/map', 'raw_own', name),
                       (f'/mr3/received/{name}/map', 'received_own', name),
                       (f'/{name}/navigation_map', 'navigation', name),
                       (f'/{name}/global_costmap/costmap', 'global_costmap', name)])
    topics.append(('/mr3/received/map', 'received_fused', None))
    metadata = {'schema': 'mr3-read-only-raw-map-observer-v2',
                'utc_start': datetime.now(timezone.utc).isoformat(),
                'observer_identity': process_identity(os.getpid()), 'worker_identity': worker,
                'episode_directory': str(episode), 'epoch': epoch, 'domain_id': args.domain_id,
                'native_freeze': native['freeze'], 'argv': [sys.executable, *sys.argv],
                'cwd': os.getcwd(), 'wall_seconds': args.wall_seconds,
                'source_sha256': {str(path): sha(path.read_bytes())
                                  for path in (*SOURCE_PATHS, Path(__file__).resolve())},
                'selected_native_metadata_sha256': sha(native_bytes),
                'selected_supervisor_metadata_sha256': sha(supervisor_bytes),
                'transport_environment': {key: os.environ.get(key) for key in TRANSPORT_KEYS},
                'map_subscriptions': [{'topic': topic, 'role': role, 'robot': name}
                                      for topic, role, name in topics],
                'other_subscriptions': ['/mr3/map_metadata', '/mr3/observation', '/clock'],
                'qos': {'maps_and_metadata': 'keep_last1/transient_local/best_effort',
                        'observation': 'keep_last4/volatile/best_effort',
                        'clock': 'keep_last1/volatile/best_effort'},
                'qos_limitation': 'Best-effort may miss messages; no completeness credit.',
                'framework_only_publisher': '/parameter_events (standard rclpy constructor)',
                'application_publishers': [], 'service_calls': [], 'action_calls': [],
                'truth_topics': [], 'transforms_applied': [],
                'installed_global_costmap_file_contract': {
                    'static_layer.footprint_clearing_enabled': True,
                    'robot_radius_m': .22, 'always_send_full_costmap': True,
                    'publish_frequency_hz': .5, 'live_parameter_queries_performed': False},
                'global_costmap_scope': 'Published nav_msgs/OccupancyGrid master-costmap '
                                        'values are preserved, including inflation and footprint '
                                        'clearing, unlike raw static-map occupancy. '
                                        'Require aligned frame, geometry, source time and robot '
                                        'pose before interpreting start/route feasibility.',
                'frame_contract': 'preserve map header/origin; expected map frame and identity '
                                  'map orientation; no TF subscription or invented registration'}
    (output / 'metadata.json').write_bytes(canonical(metadata) + b'\n')
    clock = [None]
    counts, captured_maps, actors, bundle_metadata, errors = {}, [], [], [], []
    node = context = executor = None

    def event(kind, **payload):
        events.write(canonical({'kind': kind, 'receipt_monotonic_ns': time.monotonic_ns(),
                                'last_received_clock_ns': clock[0], **payload}).decode() + '\n')

    def archive(subdir, payload):
        encoded = canonical(payload)
        digest = sha(encoded)
        path = output / subdir / (digest + '.json.gz')
        if not path.exists():
            with path.open('xb') as target:
                target.write(gzip.compress(encoded, compresslevel=1, mtime=0))
        return digest, str(path.relative_to(output))

    def add_actor(snapshot, origin, proof=None):
        if snapshot['epoch'] != epoch or snapshot['robot_order'] != list(ROBOTS):
            raise ValueError('actor snapshot is from another epoch/robot contract')
        expected = sha(canonical({key: value for key, value in snapshot.items()
                                  if key != 'digest'}))
        if expected != snapshot['digest']:
            raise ValueError('actor snapshot digest differs')
        _, artifact = archive('observations', snapshot)
        actors.append({'snapshot': snapshot, 'origin': origin, 'proof': proof,
                       'artifact': artifact})
        event('actor_snapshot', origin=origin, sequence=snapshot['sequence'],
              digest=snapshot['digest'], artifact=artifact, saved_line_proof=proof)

    def save_native_actor(label):
        saved = saved_actor_snapshot(episode)
        if saved:
            snapshot = saved.pop('snapshot')
            add_actor(snapshot, label, saved)

    def map_callback(topic, role, name, message):
        payload = map_payload(message)
        digest, artifact = archive('maps', payload)
        info = payload['info']
        orientation = info['origin']['orientation']
        common_frame = (payload['header']['frame_id'].lstrip('/') == 'map'
                        and all(abs(orientation[key]) <= 1e-6 for key in ('x', 'y', 'z'))
                        and abs(abs(orientation['w']) - 1.) <= 1e-6)
        valid_grid = (info['resolution'] > 0
                      and len(payload['data']) == info['height'] * info['width']
                      and all(value == -1 or 0 <= value <= 100 for value in payload['data']))
        item = {'topic': topic, 'role': role, 'robot': name, 'payload_sha256': digest,
                'geometry_sha256': geometry_digest(payload), 'artifact': artifact,
                'header': payload['header'], 'info': payload['info'],
                'common_frame_identity_orientation': common_frame,
                'valid_occupancy_grid': valid_grid,
                'last_received_clock_ns': clock[0]}
        captured_maps.append(item)
        counts[topic] = counts.get(topic, 0) + 1
        event('map', **item)

    def string_callback(topic, message):
        payload = json.loads(message.data)
        if topic == '/mr3/observation':
            add_actor(payload, 'subscribed_observation')
        else:
            if payload['epoch'] != epoch or set(payload['map_sources']) != set(ROBOTS):
                raise ValueError('map metadata epoch/source contract differs')
            bundle_metadata.append(payload)
            event('map_metadata', topic=topic, payload=payload)
        counts[topic] = counts.get(topic, 0) + 1

    def guarded(callback):
        def receive(message):
            try:
                callback(message)
            except Exception as error:
                errors.append(repr(error))
                event('callback_error', error=repr(error))
        return receive

    try:
        save_native_actor('saved_transition_before')
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from rclpy.signals import SignalHandlerOptions
        from nav_msgs.msg import OccupancyGrid
        from rosgraph_msgs.msg import Clock
        from std_msgs.msg import String

        context = Context()
        rclpy.init(args=[], context=context, domain_id=args.domain_id,
                   signal_handler_options=SignalHandlerOptions.NO)
        node = Node('mr3_raw_map_observer_' + str(os.getpid()), context=context,
                    enable_rosout=False, start_parameter_services=False,
                    use_global_arguments=False)
        map_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.BEST_EFFORT)
        volatile_qos = QoSProfile(depth=4, reliability=ReliabilityPolicy.BEST_EFFORT)
        for topic, role, name in topics:
            node.create_subscription(OccupancyGrid, topic, guarded(
                lambda message, t=topic, r=role, n=name: map_callback(t, r, n, message)), map_qos)
        node.create_subscription(String, '/mr3/map_metadata', guarded(
            lambda message: string_callback('/mr3/map_metadata', message)), map_qos)
        node.create_subscription(String, '/mr3/observation', guarded(
            lambda message: string_callback('/mr3/observation', message)), volatile_qos)
        node.create_subscription(Clock, '/clock',
                                 lambda message: clock.__setitem__(
                                     0, message.clock.sec * 10**9 + message.clock.nanosec),
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        event('observer_endpoints', publishers=[p.topic_name for p in node.publishers],
              services=[s.srv_name for s in node.services],
              clients=[c.srv_name for c in node.clients], subscriptions=len(topics) + 3)
        if list(node.services) or list(node.clients):
            raise RuntimeError('unexpected observer service/client endpoint')
        if [publisher.topic_name for publisher in node.publishers] != ['/parameter_events']:
            raise RuntimeError('unexpected application publisher endpoint')
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        while context.ok() and time.monotonic() < deadline - .5:
            executor.spin_once(timeout_sec=min(.05, max(0., deadline - .5 - time.monotonic())))
        save_native_actor('saved_transition_after')
    except Exception as error:
        errors.append(repr(error))
        event('observer_error', error=repr(error))
    finally:
        try:
            if node is not None:
                node.destroy_node()
            if executor is not None:
                executor.shutdown(timeout_sec=0.)
            if context is not None and context.ok():
                context.shutdown()
        except Exception as error:
            errors.append('observer cleanup: ' + repr(error))
        matches = []
        for item in captured_maps:
            saved = [actor for actor in actors if actor['origin'].startswith('saved_transition')]
            nearest = min(saved, key=lambda actor: abs(
                actor['snapshot']['source_stamp'] * 10**9 - item['last_received_clock_ns'])) \
                if saved and item['last_received_clock_ns'] is not None else None
            exact = []
            for actor in actors if (item['common_frame_identity_orientation']
                                    and item['valid_occupancy_grid']) else []:
                snapshot = actor['snapshot']
                if item['role'] in ('raw_own', 'received_own'):
                    path_map = snapshot['path_maps'][item['robot']]
                    if item['geometry_sha256'] == path_map.get('geometry_sha256'):
                        exact.append({'actor_digest': snapshot['digest'],
                                      'actor_origin': actor['origin'], 'geometry_equal': True,
                                      'full_payload_equal': (
                                          item['payload_sha256'] ==
                                          path_map.get('payload_sha256'))})
                elif item['role'] == 'received_fused':
                    bundles = [bundle for bundle in bundle_metadata
                               if bundle['map_version'] == snapshot['map_version']
                               and bundle['map_sources'] == snapshot['map']['sources']]
                    if any(bundle['map_payload_sha256'] == item['payload_sha256']
                           for bundle in bundles):
                        exact.append({'actor_digest': snapshot['digest'],
                                      'actor_origin': actor['origin'],
                                      'full_payload_matches_versioned_bundle': True})
            matches.append({'map_artifact': item['artifact'], 'topic': item['topic'],
                            'exact_observed_matches': exact,
                            'nearest_saved_actor_digest_by_observer_clock':
                            nearest['snapshot']['digest'] if nearest else None})
        summary = {'schema': metadata['schema'], 'utc_end': datetime.now(timezone.utc).isoformat(),
                   'wall_seconds': time.monotonic() - started, 'topic_message_counts': counts,
                   'unique_map_artifacts': len({item['artifact'] for item in captured_maps}),
                   'actor_snapshots_recorded': len(actors), 'errors': errors, 'matches': matches,
                   'claim_scope': 'asynchronous standalone diagnostic; nearest time is not causal '
                                  'binding; require exact native geometry/full-payload and bundle '
                                  'matches before source attribution. Navigation maps have no '
                                  'saved actor digest and require separate exact bundle replay. '
                                  'Global costmaps also require timestamp/pose alignment and '
                                  'costmap-specific value semantics; no planner outcome inferred.',
                   'native_worker_or_simulator_control_calls': 0}
        with (output / 'summary.json').open('xb') as target:
            target.write(canonical(summary) + b'\n')
        event('observer_finished', errors=len(errors), wall_seconds=time.monotonic() - started)
        events.close()
        done.set()
    return 0 if captured_maps and not errors else 2


if __name__ == '__main__':
    raise SystemExit(main())
