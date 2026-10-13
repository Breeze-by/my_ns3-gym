"""Read-only odom/TF diagnostic alongside a bounded native smoke."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage
from sensor_msgs.msg import PointCloud2
from rosgraph_msgs.msg import Clock

root = Path.cwd()
audit = root / 'log/p1c_repair_body_20261014'
records = json.loads((audit / 'commands.json').read_text())
if records[-1]['case'] == '2r_peer_diagnostic' and 'returncode' not in records[-1]:
    records[-1].update(returncode=1, finished_wall_time=datetime.datetime.now().isoformat(),
                      diagnosis='probe setup ParameterAlreadyDeclaredException; no simulator started')
run_id = '20261014_p1c_repair_body_2r_peer_diagnostic_v2'
out = audit / run_id
out.mkdir()
command = ['/usr/bin/python3', 'scripts/ros_smoke_test.py', '--robot-count', '2',
           '--world', 'my_world.world', '--gazebo-seed', '101', '--startup-timeout', '300',
           '--message-timeout', '90', '--shutdown-timeout', '60', '--dwell-seconds', '15',
           '--log-dir', str(out / 'launch_logs')]
record = {'case': '2r_peer_diagnostic_v2',
          'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
          'command': command, 'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
          'gazebo_master_uri': os.environ['GAZEBO_MASTER_URI'], 'output_dir': str(out),
          'started_wall_time': datetime.datetime.now().isoformat(),
          'readonly_probe': str(Path(__file__).resolve())}
records.append(record)
(audit / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
rclpy.init()
node = Node('peer_input_readonly_probe')
state = {}
subs = []
counts = {}
for i in range(1, 3):
    name = f'tb{i}'

    def odom(m, name=name):
        state[name + '_odom'] = {'stamp': m.header.stamp.sec + m.header.stamp.nanosec / 1e9,
                                'frame': m.header.frame_id, 'child': m.child_frame_id,
                                'x': m.pose.pose.position.x, 'y': m.pose.pose.position.y}

    def tf(m, name=name, depth=20):
        key = name + '_tf' + str(depth)
        counts[key] = counts.get(key, 0) + 1
        for t in m.transforms:
            state[key + '_' + t.child_frame_id] = {
                'stamp': t.header.stamp.sec + t.header.stamp.nanosec / 1e9,
                'frame': t.header.frame_id, 'child': t.child_frame_id}

    def tf1(m, name=name):
        tf(m, name, 1)

    def cloud(m, name=name):
        state[name + '_cloud'] = {'stamp': m.header.stamp.sec + m.header.stamp.nanosec / 1e9,
                                 'width': m.width, 'frame': m.header.frame_id}

    subs.extend([node.create_subscription(Odometry, f'/{name}/odom', odom, 1),
                 node.create_subscription(TFMessage, f'/{name}/tf', tf, 20),
                 node.create_subscription(TFMessage, f'/{name}/tf', tf1, 1),
                 node.create_subscription(PointCloud2, f'/{name}/peer_footprints', cloud, 1)])
subs.append(node.create_subscription(Clock, '/clock', lambda m: state.update(
    clock=m.clock.sec + m.clock.nanosec / 1e9), qos_profile_sensor_data))
console = (audit / (run_id + '.console.log')).open('x')
process = subprocess.Popen(command, stdout=console, stderr=subprocess.STDOUT, text=True)
end = time.monotonic() + 360
latest = time.monotonic()
snapshots = []
while process.poll() is None and time.monotonic() < end:
    rclpy.spin_once(node, timeout_sec=.1)
    if time.monotonic() - latest >= 1:
        latest = time.monotonic()
        sample = {'wall_time': datetime.datetime.now().isoformat(), 'data': dict(state),
                  'counts': dict(counts)}
        snapshots.append(sample)
        (out / 'readonly_peer_timeline.json').write_text(json.dumps(snapshots, indent=2) + '\n')
if process.poll() is None:
    process.terminate()
rc = process.wait(timeout=90)
console.close()
node.destroy_node()
rclpy.shutdown()
record.update(returncode=rc, finished_wall_time=datetime.datetime.now().isoformat())
(audit / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
print('Diagnostic return', rc, 'samples', len(snapshots))
print(json.dumps(snapshots[-2:], indent=2))
