"""Read-only reconstruction of a soft departure preference and its native sources."""
import base64
import gzip
import json
import math


def heading_preference_factor(event, required=False):
    saved = event.get('travel_preference', {}).get('departure_heading')
    if saved is None:
        assert not required, 'missing declared departure heading preference'
        return 1.
    assert saved['strategy'] == 'bounded_direct_bearing_departure'
    assert saved['source'] == 'ap_delivered_pose_and_heading'
    now = event['event_time']; name = event['robot']
    preference = event['travel_preference']; ranked = preference['ranking_time_sec']
    assert saved['evaluated_at_sec'] == ranked <= now
    for kind, key in [('pose_state', 'pose_source_time'), ('frame_state', 'frame_source_time')]:
        source = event['inputs'][name + '/' + kind]['source_time']
        assert saved[key] == source and 0 <= ranked - source <= 2. and 0 <= now - source <= 2.
    position, target, yaw = saved['position'], saved['target'], saved['yaw']
    assert len(position) == len(target) == 2
    assert all(math.isfinite(v) for v in (*position, *target, yaw, saved['nominal_distance_m']))
    assert all(math.isclose(a, b, abs_tol=1e-8) for a, b in zip(position, event['current_position']))
    assert target == preference['target']
    distance = preference['own_nominal_distance_m']
    assert distance >= 0 and saved['nominal_distance_m'] == distance
    bearing = math.atan2(target[1] - position[1], target[0] - position[0])
    angle = abs(math.atan2(math.sin(bearing - yaw), math.cos(bearing - yaw)))
    # Independently specified original scoring constants and configured RPP speed.
    travel = 1. + (1. + distance) ** 1.5 - 1.
    expected = dict(bearing_rad=bearing, angle_rad=angle, turn_speed_radps=.7,
        turn_time_estimate_sec=angle / .7, original_travel_time_units=travel,
        factor=max(.25, travel / (travel + angle / .7)))
    assert all(math.isclose(saved[key], value, rel_tol=1e-10, abs_tol=1e-8)
        for key, value in expected.items()), 'departure preference differs from delivered geometry'
    assert .25 <= saved['factor'] <= 1.
    return expected['factor']


def departure_heading_audit(ledger, capture, required=False, frame_offset_sec=.2):
    if not required:
        return None
    from nav_msgs.msg import Odometry
    from tf2_msgs.msg import TFMessage
    from rclpy.serialization import deserialize_message
    events = []
    for line in ledger.open():
        event = json.loads(line)
        if event.get('event') == 'coordinator_navigation_decision' and event.get('kind') in (
                'exploration', 'initial_visual_search'):
            heading_preference_factor(event, True)
            events.append(event)
    wanted = {(event['robot'], kind, round(event['inputs'][event['robot'] + '/' + kind]['source_time'] * 1e9))
        for event in events for kind in ('pose_state', 'frame_state')}
    topics = {f'/{name}/{suffix}' for name, _, _ in wanted for suffix in ('odom', 'tf')}
    sources = {}
    for line in gzip.open(capture, 'rt'):
        row = json.loads(line)
        if row['topic'] not in topics:
            continue
        name = row['topic'].split('/')[1]
        message = deserialize_message(base64.b64decode(row['cdr'], validate=True),
            Odometry if row['topic'].endswith('/odom') else TFMessage)
        if isinstance(message, Odometry):
            stamp = message.header.stamp.sec * 10**9 + message.header.stamp.nanosec
            key = (name, 'pose_state', stamp)
            if key in wanted:
                sources.setdefault(key, []).append(message.pose.pose)
        else:
            for transform in message.transforms:
                if not (transform.header.frame_id.lstrip('/') in ('map', name + '/map')
                        and transform.child_frame_id.lstrip('/') in ('odom', name + '/odom')):
                    continue
                stamp = transform.header.stamp.sec * 10**9 + transform.header.stamp.nanosec - round(frame_offset_sec * 1e9)
                key = (name, 'frame_state', stamp)
                if key in wanted:
                    sources.setdefault(key, []).append(transform.transform)
    assert set(sources) == wanted, 'missing original departure pose/frame CDR'
    def yaw(quaternion):
        return math.atan2(2. * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
            1. - 2. * (quaternion.y**2 + quaternion.z**2))
    for event in events:
        name = event['robot']; saved = event['travel_preference']['departure_heading']
        poses = sources[name, 'pose_state', round(saved['pose_source_time'] * 1e9)]
        frames = sources[name, 'frame_state', round(saved['frame_source_time'] * 1e9)]
        def matches(pose, transform):
            angle = yaw(transform.rotation); cosine, sine = math.cos(angle), math.sin(angle)
            point = (pose.position.x * cosine - pose.position.y * sine + transform.translation.x,
                pose.position.x * sine + pose.position.y * cosine + transform.translation.y)
            return (math.dist(point, saved['position']) <= 1e-8
                and abs(math.atan2(math.sin(yaw(pose.orientation) + angle - saved['yaw']),
                    math.cos(yaw(pose.orientation) + angle - saved['yaw']))) <= 1e-8)
        assert any(matches(pose, transform) for pose in poses for transform in frames), 'departure heading differs from original CDR'
    return dict(status='PASS',executed_preferences=len(events),native_source_bindings=2*len(events),
        scope='Private soft direct-bearing preference; exact original native odom/TF source binding. Full path, energy, source leases and native task success remain independent gates.')
