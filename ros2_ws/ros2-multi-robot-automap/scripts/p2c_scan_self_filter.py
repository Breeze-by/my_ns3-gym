"""Read-only physical-geometry and original-CDR checks of native scan filtering."""
import base64
import gzip
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import json
import numpy as np
import yaml

PROJECT = Path(__file__).resolve().parents[1]


def physical_body_box():
    sdf = ET.parse(PROJECT/'src/multi_robot/models/turtlebot3_waffle/model.sdf')
    urdf = ET.parse(PROJECT/'src/multi_robot/urdf/turtlebot3_waffle.urdf')
    collision = sdf.find(".//link[@name='base_link']/collision[@name='base_collision']")
    sdf_pose = list(map(float, collision.findtext('pose').split()))
    sdf_size = list(map(float, collision.findtext('geometry/box/size').split()))
    collision = urdf.find(".//link[@name='base_link']/collision")
    urdf_pose = list(map(float, collision.find('origin').get('xyz').split()))
    urdf_size = list(map(float, collision.find('geometry/box').get('size').split()))
    assert sdf_pose[3:] == [0., 0., 0.]
    assert list(map(float, collision.find('origin').get('rpy').split())) == [0., 0., 0.]
    boxes = [[p[0]-s[0]/2, p[0]+s[0]/2, p[1]-s[1]/2, p[1]+s[1]/2]
             for p, s in ((sdf_pose, sdf_size), (urdf_pose, urdf_size))]
    return [max(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), min(b[3] for b in boxes)]


def body_return_mask(scan, box, laser):
    ranges = np.asarray(scan.ranges, dtype=float)
    angles = scan.angle_min + np.arange(len(ranges))*scan.angle_increment + laser[2]
    with np.errstate(invalid='ignore'):
        x = laser[0] + ranges*np.cos(angles)
        y = laser[1] + ranges*np.sin(angles)
    return (np.isfinite(ranges) & (ranges > scan.range_min) & (ranges < scan.range_max)
            & (box[0] < x) & (x < box[1]) & (box[2] < y) & (y < box[3]))


def noise_associated_mask(scan, box, laser, uncertainty):
    """Independent reconstruction of a seeded body-surface noise cluster."""
    inside = body_return_mask(scan, box, laser)
    if (not np.isfinite(uncertainty) or uncertainty <= 0
            or not np.isfinite(scan.angle_increment) or scan.angle_increment == 0
            or not (box[0] < laser[0] < box[1] and box[2] < laser[1] < box[3])):
        return inside
    ranges = np.asarray(scan.ranges, dtype=float)
    angles = scan.angle_min + np.arange(len(ranges))*scan.angle_increment + laser[2]
    dx, dy = np.cos(angles), np.sin(angles)
    with np.errstate(divide='ignore', invalid='ignore'):
        tx = np.where(dx != 0, np.where(dx > 0, box[1]-laser[0], box[0]-laser[0])/dx, np.inf)
        ty = np.where(dy != 0, np.where(dy > 0, box[3]-laser[1], box[2]-laser[1])/dy, np.inf)
        surface = np.minimum(tx, ty)
    band = inside | (np.isfinite(ranges) & (ranges > scan.range_min) & (ranges < scan.range_max)
        & np.isfinite(surface) & (np.abs(ranges-surface) <= uncertainty))
    wrap = len(ranges) >= 9 and (len(ranges)-1)*abs(scan.angle_increment) >= 2*np.pi-2*abs(scan.angle_increment)
    result = inside.copy()
    indices = np.flatnonzero(band)
    groups = list(np.split(indices, np.flatnonzero(np.diff(indices) != 1)+1)) if len(indices) else []
    if wrap and len(groups) > 1 and groups[0][0] == 0 and groups[-1][-1] == len(ranges)-1:
        groups = [np.concatenate((groups[-1], groups[0])), *groups[1:-1]]
    for group in groups:
        if np.count_nonzero(inside[group]) >= 1 and len(group) >= 3:
            result[group] = True
    return result


def physical_range_uncertainty():
    sensor = ET.parse(PROJECT/'src/multi_robot/models/turtlebot3_waffle/model.sdf').find(
        ".//sensor[@name='hls_lfcd_lds']/ray")
    assert sensor.findtext('noise/type') == 'gaussian' and float(sensor.findtext('noise/mean')) == 0.
    return 3*float(sensor.findtext('noise/stddev')) + float(sensor.findtext('range/resolution'))/2


def scan_self_filter_audit(row, directory):
    declaration = row['config'].get('native_scan_self_filter')
    if not declaration:
        return None
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import LaserScan
    from tf2_msgs.msg import TFMessage
    from run_p2d_baseline import file_digest

    assert row['config'].get('navigation_input_capture'), 'missing raw native scan evidence'
    box = declaration['body_box_m']
    laser = declaration['laser_to_base_xy_yaw']
    uncertainty = declaration.get('range_uncertainty_m', 0.)
    assert uncertainty == 0. or uncertainty == physical_range_uncertainty()
    assert np.allclose(box, physical_body_box(), rtol=0, atol=1e-15)
    params = yaml.safe_load((PROJECT/'src/slam_toolbox/config/mapper_params_online_multi_async.yaml').read_text())
    configured_params = next(iter(params.values()))['ros__parameters']
    assert configured_params['scan_self_filter_body_box'] == box
    assert configured_params.get('scan_self_filter_range_uncertainty_m', 0.) == uncertainty
    for name, path in (('slam', 'src/slam_toolbox'), ('robot_models', 'src/multi_robot/models'),
                       ('robot_description', 'src/multi_robot/urdf'), ('scan_self_filter_reader', 'scripts/p2c_scan_self_filter.py')):
        assert row['source_digests'][name] == file_digest(PROJECT/path), ('unbound native filter source', name)
    pattern = re.compile(r'\[([^\]\s]+)\.slam_toolbox\]: SCAN_SELF_FILTER source=([\d.]+) frame=(\S+) removed=(\d+)')
    witnesses = []
    configured = {}
    for path in sorted((directory/'launch').glob('*.log')):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if 'SCAN_SELF_FILTER_CONFIG box=' in line:
                match = re.search(r'\[([^\]\s]+)\.slam_toolbox\]: SCAN_SELF_FILTER_CONFIG box=([^\s]+)', line)
                assert match, ('malformed native filter configuration', path.name, number)
                actual = list(map(float, match[2].split(',')))
                assert np.allclose(actual, box, rtol=0, atol=1e-15)
                assert match[1] not in configured or configured[match[1]] == actual
                configured[match[1]] = actual
                noise = re.search(r'uncertainty=([\d.]+)', line)
                assert (float(noise[1]) if noise else 0.) == uncertainty
            if 'SCAN_SELF_FILTER source=' not in line:
                continue
            match = pattern.search(line)
            assert match, ('malformed native scan witness', path.name, number)
            name, source, frame, removed = match.groups()
            witnesses.append((name, round(float(source)*1e9), frame, int(removed)))
    originals = {}
    extrinsics = {}
    scan_count = 0
    with gzip.open(directory/'navigation_inputs.jsonl.gz', 'rt') as stream:
        for line in stream:
            e = json.loads(line)
            topic = e['topic']
            if topic.endswith('/scan'):
                name = topic.split('/')[1]
                msg = deserialize_message(base64.b64decode(e['cdr']), LaserScan)
                key = (name, msg.header.stamp.sec*10**9+msg.header.stamp.nanosec, msg.header.frame_id)
                count = int(noise_associated_mask(msg, box, laser, uncertainty).sum())
                assert key not in originals or originals[key] == count, ('ambiguous original scan', key)
                originals[key] = count
                scan_count += 1
            elif topic.endswith('/tf_static'):
                name = topic.split('/')[1]
                msg = deserialize_message(base64.b64decode(e['cdr']), TFMessage)
                for t in msg.transforms:
                    if (t.header.frame_id, t.child_frame_id) not in (
                            ('base_footprint', 'base_link'), ('base_link', declaration['laser_frame'])):
                        continue
                    values = (t.transform.translation.x, t.transform.translation.y,
                              t.transform.rotation.x, t.transform.rotation.y, t.transform.rotation.z, t.transform.rotation.w)
                    key = (name, t.header.frame_id, t.child_frame_id)
                    assert key not in extrinsics or extrinsics[key] == values
                    extrinsics[key] = values
    for i in range(1, row['result']['robot_count']+1):
        name = f'tb{i}'
        assert name in configured, ('missing native body filter configuration', name)
        assert extrinsics[name, 'base_footprint', 'base_link'] == (0., 0., 0., 0., 0., 1.)
        assert extrinsics[name, 'base_link', declaration['laser_frame']] == (laser[0], laser[1], 0., 0., 0., 1.)
        assert laser[2] == 0., 'runtime witness requires the declared planar native laser'
    for name, source, frame, removed in witnesses:
        assert frame == declaration['laser_frame']
        assert removed > 0 and originals.get((name, source, frame)) == removed, ('native/raw mask mismatch', name, source, removed)
    return dict(status='PASS',original_scans=scan_count,native_witnesses=len(witnesses),
        rejected_body_returns=sum(w[3] for w in witnesses),body_box_m=box,
        physical_geometry_bound=True,full_slam_source_bound=True,raw_scan_control_flow_unchanged=True)
