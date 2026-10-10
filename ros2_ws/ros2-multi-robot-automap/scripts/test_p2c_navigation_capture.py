"""Exact CDR recording, including scan infinities and late static transforms."""
import base64
import gzip
import json
import time
import hashlib
from pathlib import Path

import pytest
import numpy as np
import rclpy
from geometry_msgs.msg import TransformStamped, Pose
from geometry_msgs.msg import Twist
from gazebo_msgs.msg import ModelStates
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.serialization import deserialize_message, serialize_message
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage

from p2c_navigation_capture import NavigationCapture
from check_p2c_gate import navigation_capture_audit
from run_p2d_baseline import file_digest


def test_exact_raw_dds_inputs_and_existing_file_protection(tmp_path):
    rclpy.init()
    source = Node('p2c_capture_test_source')
    observer = Node('p2c_capture_test_observer')
    output = tmp_path / 'inputs.jsonl.gz'
    capture = None
    try:
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        transform = TransformStamped()
        transform.header.frame_id = 'base_link'
        transform.child_frame_id = 'base_scan'
        transform.transform.rotation.w = 1.
        static = TFMessage(transforms=[transform])
        static_pub = source.create_publisher(TFMessage, '/tb1/tf_static', latched)
        static_pub.publish(static)
        capture = NavigationCapture(observer, output, 1)
        with pytest.raises(FileExistsError):
            NavigationCapture(observer, output, 1)
        scan = LaserScan()
        scan.header.stamp.sec = 17
        scan.header.frame_id = 'base_scan'
        scan.ranges = [float('inf'), float('nan'), .4]
        grid = OccupancyGrid()
        grid.header.stamp.sec = 16
        grid.info.width, grid.info.height, grid.info.resolution = 2, 2, .05
        grid.info.origin.orientation.w = 1.
        grid.data = [-1, 0, 100, 0]
        scan_pub = source.create_publisher(LaserScan, '/tb1/scan', 10)
        map_pub = source.create_publisher(OccupancyGrid, '/tb1/map', latched)
        command = Twist(); command.linear.x = .2; command.angular.z = -.7
        state = ModelStates(name=['tb1'], pose=[Pose()], twist=[Twist()])
        command_pub = source.create_publisher(Twist, '/tb1/cmd_vel', 10)
        nav_command_pub = source.create_publisher(Twist, '/tb1/cmd_vel_nav', 10)
        state_pub = source.create_publisher(ModelStates, '/gazebo/model_states', 10)
        expected = {'/tb1/cmd_vel': serialize_message(command), '/tb1/cmd_vel_nav': serialize_message(command),
                    '/gazebo/model_states': serialize_message(state),
                    '/tb1/scan': serialize_message(scan), '/tb1/map': serialize_message(grid),
                    '/tb1/tf_static': serialize_message(static)}
        deadline = time.monotonic() + 5.
        while time.monotonic() < deadline and not set(expected) <= capture.counts.keys():
            scan_pub.publish(scan)
            map_pub.publish(grid)
            command_pub.publish(command); nav_command_pub.publish(command); state_pub.publish(state)
            rclpy.spin_once(observer, timeout_sec=.02)
        assert set(expected) <= capture.counts.keys(), capture.counts
        # Direct bytes round trip checks the recorder; DDS CDR padding is not canonical.
        capture.record('/recorder_bytes', 'sensor_msgs/msg/LaserScan', expected['/tb1/scan'])
        capture.close()
        capture = None
        with gzip.open(output, 'rt') as stream:
            rows = [json.loads(line) for line in stream]
        for row in rows:
            payload = base64.b64decode(row['cdr'])
            if row['topic'] == '/recorder_bytes':
                assert payload == expected['/tb1/scan']
            elif row['topic'] == '/tb1/map':
                assert deserialize_message(payload, OccupancyGrid) == deserialize_message(expected[row['topic']], OccupancyGrid)
            elif row['topic'] == '/tb1/tf_static':
                assert deserialize_message(payload, TFMessage) == static
            elif row['topic'].endswith('/cmd_vel') or row['topic'].endswith('/cmd_vel_nav'):
                assert deserialize_message(payload, Twist) == command
            elif row['topic'] == '/gazebo/model_states':
                assert deserialize_message(payload, ModelStates) == state
            else:
                received = deserialize_message(payload, LaserScan)
                assert received.header == scan.header
                assert np.array_equal(received.ranges, scan.ranges, equal_nan=True)
        assert {row['type'] for row in rows} == {
            'sensor_msgs/msg/LaserScan', 'nav_msgs/msg/OccupancyGrid', 'tf2_msgs/msg/TFMessage',
            'geometry_msgs/msg/Twist', 'gazebo_msgs/msg/ModelStates'}
        assert all(row['received_wall_ns'] > 0 for row in rows)
        assert not any(topic.startswith(('/tb1/', '/merge_map'))
                       for topic, _ in observer.get_publisher_names_and_types_by_node(observer.get_name(), '/'))
    finally:
        if capture is not None:
            capture.close()
        observer.destroy_node()
        source.destroy_node()
        rclpy.shutdown()


@pytest.mark.parametrize('tamper', [None, 'digest', 'command', 'source', 'close', 'missing_topics', 'cdr'])
def test_capture_audit_rejects_missing_or_changed_originals(tmp_path, tamper):
    output = tmp_path / 'navigation_inputs.jsonl.gz'
    record = dict(topic='/tb1/scan', type='sensor_msgs/msg/LaserScan',
                  cdr=base64.b64encode(b'\x00\x01\x00\x00').decode(), received_sim_time=17., received_wall_ns=1)
    if tamper == 'cdr':
        record['cdr'] = '!invalid'
    with gzip.open(output, 'wt') as stream:
        stream.write(json.dumps(record) + '\n')
    (tmp_path / 'observer.log').write_text('NAVIGATION_CAPTURE_CLOSED {"/tb1/scan": 1}\n')
    row = dict(config={'navigation_input_capture': True}, case='empty_battery', result={'robot_count': 1},
        observer_command=['--navigation-input-output', str(output)],
        source_digests={'navigation_capture': file_digest(Path(__file__).with_name('p2c_navigation_capture.py'))},
        evidence_sha256={output.name: hashlib.sha256(output.read_bytes()).hexdigest()})
    if tamper == 'digest': row['evidence_sha256'][output.name] = 'bad'
    if tamper == 'command': row['observer_command'][1] = 'other.gz'
    if tamper == 'source': row['source_digests']['navigation_capture'] = 'bad'
    if tamper == 'close': (tmp_path / 'observer.log').write_text('')
    if tamper == 'missing_topics': row['case'] = 'dev_forced2'
    if tamper is None:
        assert navigation_capture_audit(row, tmp_path)['messages'] == 1
    else:
        with pytest.raises((AssertionError, ValueError)):
            navigation_capture_audit(row, tmp_path)


@pytest.mark.parametrize('tamper', [None, 'missing', 'wrong_type', 'duplicate', 'outside', 'close'])
def test_motion_capture_keeps_legal_zero_commands_and_checks_subscriptions(tmp_path, tamper):
    from p2c_navigation_capture import navigation_topics
    output=tmp_path/'navigation_inputs.jsonl.gz'
    topic='/outside' if tamper=='outside' else '/tb1/scan'
    record=dict(topic=topic,type='sensor_msgs/msg/LaserScan',cdr=base64.b64encode(b'\0\1\0\0').decode(),
        received_sim_time=10.,received_wall_ns=1)
    with gzip.open(output,'wt') as stream:stream.write(json.dumps(record)+'\n')
    declared={topic:kind.__module__.split('.')[0]+'/msg/'+kind.__name__ for topic,kind,_ in navigation_topics(1)}
    if tamper=='wrong_type':declared['/tb1/cmd_vel']='nav_msgs/msg/Odometry'
    markers=[] if tamper=='missing' else ['NAVIGATION_CAPTURE_SUBSCRIPTIONS '+json.dumps(declared)]
    if tamper=='duplicate':markers*=2
    if tamper!='close':markers+=['NAVIGATION_CAPTURE_CLOSED '+json.dumps({topic:1})]
    (tmp_path/'observer.log').write_text('\n'.join(markers)+'\n')
    row=dict(config=dict(navigation_input_capture=True,native_velocity_command_capture=True),case='empty_battery',
        result=dict(robot_count=1),observer_command=['--navigation-input-output',str(output)],
        source_digests=dict(navigation_capture=file_digest(Path(__file__).with_name('p2c_navigation_capture.py'))),
        evidence_sha256={output.name:hashlib.sha256(output.read_bytes()).hexdigest()})
    if tamper is None:
        result=navigation_capture_audit(row,tmp_path)
        assert result['messages']==1 and '/tb1/cmd_vel' not in result['topic_counts']
    else:
        with pytest.raises(AssertionError):navigation_capture_audit(row,tmp_path)
