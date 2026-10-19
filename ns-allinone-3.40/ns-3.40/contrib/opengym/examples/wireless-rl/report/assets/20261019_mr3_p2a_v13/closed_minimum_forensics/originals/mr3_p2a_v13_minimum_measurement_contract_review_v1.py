"""Closed-file arithmetic only: no ROS imports, consumers, or task acceptance."""
from pathlib import Path
import ctypes
import hashlib
import json
import math
import statistics
import time
import xml.etree.ElementTree as ET

ROOT = Path('/home/zhuyulab/ns3-workspace')
EP = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v13_minimal/native/round0000/worker0/episode001_open_101'
OUT = Path('/tmp/mr3_p2a_v13_minimum_measurement_contract_review_v1.json')
start = time.monotonic_ns()
libm = ctypes.CDLL('libm.so.6')
for name in ('sinf', 'cosf'):
    getattr(libm, name).argtypes = [ctypes.c_float]
    getattr(libm, name).restype = ctypes.c_float

def spec(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def stat(values):
    return {'count': len(values), 'minimum': min(values), 'maximum': max(values),
            'mean': statistics.mean(values)}

def stamp(odom):
    v = odom['header']['stamp']
    return v['sec'] * 10**9 + v['nanosec']

def point(odom):
    return odom['pose']['pose']['position']

def rpy(odom):
    q = odom['pose']['pose']['orientation']
    x, y, z, w = (q[k] for k in ('x', 'y', 'z', 'w'))
    return (math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)),
            math.asin(max(-1., min(1., 2*(w*y-z*x)))),
            math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))

first_failure = None
own = []
first_active = None
failure_decision = None
for line, raw in enumerate((EP / 'motion_safety.jsonl').open(), 1):
    row = json.loads(raw)
    value = row['payload']
    if row['kind'] == 'own_odom' and value['robot'] == 'tb3':
        own.append((line, value['input_sequence'], value['message']))
    elif row['kind'] == 'decision' and value['robot'] == 'tb3':
        cert = (value.get('own_state') or {}).get('settled_turn') or {}
        if first_active is None and cert.get('active_since_ns') is not None:
            first_active = {'line': line, 'decision_clock_ns': value['clock_ns'],
                            'certificate': cert}
        if first_failure is not None:
            failure_decision = {'line': line, 'decision_clock_ns': value['clock_ns'],
                                'certificate': cert, 'request': value.get('request')}
            break
    elif row['kind'] == 'settled_turn_model_failure' and first_failure is None:
        first_failure = {'line': line, 'row': row}

assert first_failure and first_active and failure_decision
cert = failure_decision['certificate']
anchor = cert['active_anchor_source_ns']
samples = [(line, seq, odom) for line, seq, odom in own if stamp(odom) >= anchor]
assert samples[0][2] and stamp(samples[0][2]) == anchor
rows = []
path = 0.
for idx, (line, seq, odom) in enumerate(samples):
    xyz = point(odom)
    linear = odom['twist']['twist']['linear']
    angular = odom['twist']['twist']['angular']
    roll, pitch, yaw = rpy(odom)
    c, s = libm.cosf(yaw), libm.sinf(yaw)
    scale = math.hypot(c, s)
    # Exact inverse of the producer's 2x2 yaw matrix, including float trig.
    vx = (c*linear['x'] - s*linear['y']) / (c*c+s*s)
    vy = (s*linear['x'] + c*linear['y']) / (c*c+s*s)
    chord = dt = None
    if idx:
        previous = samples[idx-1][2]
        p = point(previous)
        dt = (stamp(odom)-stamp(previous))/1e9
        chord = math.hypot(xyz['x']-p['x'], xyz['y']-p['y'])
        path += chord
    rows.append({'source_ns': stamp(odom), 'motion_line': line, 'input_sequence': seq,
                 'position_xyz': xyz, 'body_xy': [linear['x'], linear['y']],
                 'body_z': linear['z'], 'planar_speed_mps': math.hypot(linear['x'], linear['y']),
                 'world_xy_reconstructed': [vx,vy], 'angular_z': angular['z'],
                 'roll_rad': roll, 'pitch_rad': pitch, 'yaw_rad': yaw,
                 'float_yaw_norm_scale': scale, 'dt_sec': dt, 'chord_m': chord,
                 'cumulative_path_m': path})

native = {}
for line, raw in enumerate((EP / 'odometry_tb3.jsonl').open(), 1):
    row = json.loads(raw)
    if row['kind'] == 'publication':
        native[row['source_clock_ns']] = (line, row['odometry'])
matches = []
for row, (_, _, odom) in zip(rows, samples):
    source = native[row['source_ns']]
    matches.append(source[1] == odom)
assert all(matches)

drive = []
for line, raw in enumerate((EP / 'drive_tb3.jsonl').open(), 1):
    row = json.loads(raw)
    if row['kind'] == 'actuation' and anchor <= row['sim_time_ns'] <= rows[-1]['source_ns']:
        drive.append({'line': line, 'sim_time_ns': row['sim_time_ns'],
                      'desired_v': row['desired_v'], 'desired_w': row['desired_w'],
                      'current_rim_mps': row['current_rim_mps'],
                      'applied_rim_mps': row['applied_rim_mps'],
                      'measured_wheel_center_v_mps': sum(row['current_rim_mps'])/2,
                      'applied_wheel_center_v_mps': sum(row['applied_rim_mps'])/2})

spawned = ET.parse(EP / 'drive_model_tb3.sdf').getroot().find('model')
links = spawned.findall('link')
base_joint = next(v for v in spawned.findall('joint') if v.get('name')=='base_joint')
base_link = next(v for v in links if v.get('name')=='base_link')
endpoint = rows[-1]
duration = (endpoint['source_ns']-anchor)/1e9
net = math.hypot(endpoint['position_xyz']['x']-rows[0]['position_xyz']['x'],
                 endpoint['position_xyz']['y']-rows[0]['position_xyz']['y'])
speed_integral = sum((a['planar_speed_mps']+b['planar_speed_mps'])/2*b['dt_sec']
                     for a,b in zip(rows,rows[1:]))
vector_integral = [sum((a['world_xy_reconstructed'][k]+b['world_xy_reconstructed'][k])/2*b['dt_sec']
                       for a,b in zip(rows,rows[1:])) for k in (0,1)]
yaw_integral = sum((a['angular_z']+b['angular_z'])/2*b['dt_sec'] for a,b in zip(rows,rows[1:]))
sources = [
    ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp',
    ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py',
    ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py',
    ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot/models/turtlebot3_waffle/model.sdf',
]
official = Path('/tmp/mr3_p2a0_v13_stop_point_review_v1')
official_index = json.loads((official/'official_sources_v1.json').read_text())
official_specs=[]
for item in official_index:
    current=spec(Path(item['path']))
    assert current['sha256']==item['sha256']
    current['url']=item['url']
    official_specs.append(current)

result = {
 'schema': 'mr3-v13-minimum-measurement-contract-readonly-review-v1',
 'scope': 'Closed-file arithmetic/static source only. Not a science consumer, new simulator run, task credit, or repaired model claim.',
 'runtime_freeze': '0063aa233ba3008ddcc1eb09ea8068112eea3965',
 'episode': str(EP),
 'first_failure': first_failure,
 'first_active_decision': first_active,
 'first_post_failure_decision': failure_decision,
 'measurement_contract': {
   'rest_speed': 'hypot raw linear.x/linear.y, not xyz; linear.z only finite-checked',
   'drift_path': 'sum raw odometry pose XY chord from activation anchor; no SLAM or map-to-odom transform',
   'producer_pose': 'model WorldPose, copied directly to odom pose',
   'producer_velocity': 'Model WorldLinearVel delegates to canonical Link origin velocity; ODE offset subtracts CoG before dBodyGetRelPointVel; not bare CoG velocity',
   'projection': 'world XY rotated by float yaw via cosf/sinf; no z input and no reference-point translation',
   'first_spawned_link': links[0].get('name'),
   'first_link_pose': links[0].findtext('pose', default='0 0 0 0 0 0 (SDF default)'),
   'base_joint_parent': base_joint.findtext('parent'),
   'base_joint_child': base_joint.findtext('child'),
   'base_joint_pose': base_joint.findtext('pose', default='0 0 0 0 0 0 (SDF default)'),
   'base_link_inertial_pose': base_link.findtext('inertial/pose'),
   'limits': 'Instantaneous speeds and finite-interval chords are distinct; small ongoing real XY motion can exceed a fixed cumulative whole-segment budget without a speed violation.',
 },
 'closed_data_arithmetic': {
   'sample_count':len(rows),'source_first_ns':anchor,'source_last_ns':endpoint['source_ns'],
   'duration_sec':duration,'path_m':path,'recorded_path_m':cert['active_path_m'],
   'path_equals_recorded_exactly':path==cert['active_path_m'],
   'net_xy_displacement_m':net,
   'mean_chord_speed_mps':path/duration,
   'chord_speed_mps':stat([v['chord_m']/v['dt_sec'] for v in rows[1:]]),
   'planar_speed_mps':stat([v['planar_speed_mps'] for v in rows]),
   'speed_trapezoid_integral_m':speed_integral,
   'world_velocity_trapezoid_xy_m':vector_integral,
   'observed_endpoint_delta_xy_m':[endpoint['position_xyz'][k]-rows[0]['position_xyz'][k] for k in ('x','y')],
   'angular_velocity_integral_rad':yaw_integral,
   'max_float_rotation_norm_relative_error':max(abs(v['float_yaw_norm_scale']-1) for v in rows),
   'max_abs_roll_rad':max(abs(v['roll_rad']) for v in rows),
   'max_abs_pitch_rad':max(abs(v['pitch_rad']) for v in rows),
   'all_body_linear_z_zero':all(v['body_z']==0 for v in rows),
   'every_received_odom_equals_native_publication':all(matches),
   'native_matches':len(matches),'last_sample':endpoint,
   'all_native_desired_v_zero':all(v['desired_v']==0 for v in drive),
   'all_applied_rim_pair_means_zero':all(v['applied_wheel_center_v_mps']==0 for v in drive),
   'native_actuation_count':len(drive),
   'measured_joint_pair_center_v_mps':stat([v['measured_wheel_center_v_mps'] for v in drive]),
 },
 'not_established':[
   'No independent full3D link/CoG/contact impulse stream in this uninstrumented training episode identifies a particular ODE constraint, friction or collision mechanism.',
   'Native wheel joint targets are not a guarantee of zero body-center motion; measured wheel feedback and world pose can differ through contact/constraint dynamics.',
   'Finite-difference path is a sampled lower bound on continuous travel; it is not reduced to net displacement or filtered to remove accumulated motion.',
   'Rest speed or angular limits were not raised; old original failure and no-retry status are unchanged.',
 ],
 'sources':[spec(p) for p in sources],
 'official_sources':official_specs,
 'data_sources':[spec(EP/f) for f in ('motion_safety.jsonl','odometry_tb3.jsonl','drive_tb3.jsonl','drive_model_tb3.sdf','metadata.json','summary.json')],
 'sample_trace':rows,
 'native_actuation_trace':drive,
 'cpu_started_wall_monotonic_ns':start,
}
result['cpu_completed_wall_monotonic_ns']=time.monotonic_ns()
result['cpu_duration_sec']=(result['cpu_completed_wall_monotonic_ns']-start)/1e9
OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'output':spec(OUT),'cpu_duration_sec':result['cpu_duration_sec'],
                  'first_failure':first_failure,'arithmetic':result['closed_data_arithmetic']},indent=2))
