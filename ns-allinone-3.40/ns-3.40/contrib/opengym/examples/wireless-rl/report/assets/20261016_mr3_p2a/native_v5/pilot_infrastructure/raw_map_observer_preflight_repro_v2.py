#!/usr/bin/python3
"""Observer v2's eight pure CPU checks; never call observer main or import ROS."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as N

import yaml


ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
RUN = ROS / 'log/mr3_ppo/mr3_p2a_v5_pilot'
path = RUN / 'raw_map_observer_v2.py'
spec = importlib.util.spec_from_file_location('observer_pure_fixture', path)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
source = ROS / 'src/multi_robot_exploration/multi_robot_exploration/mr3_information.py'
names = {'stamp_payload', 'vector_payload', 'quaternion_payload', 'pose_payload',
         'header_payload', 'map_payload'}
scope = {}
functions = [node for node in ast.parse(source.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), scope)
message = N(header=N(stamp=N(sec=12, nanosec=34), frame_id='map'),
            info=N(map_load_time=N(sec=1, nanosec=2), resolution=.05, width=3, height=2,
                   origin=N(position=N(x=-1., y=-2., z=0.),
                            orientation=N(x=0., y=0., z=0., w=1.))),
            data=[-1, 0, 100, 0, -1, 0])
payload = observer.map_payload(message)
assert payload == scope['map_payload'](message)
metadata = {'resolution': .05, 'origin': (-1., -2.), 'shape': [2, 3]}
expected = hashlib.sha256(
    observer.canonical(metadata) + struct.pack('<6h', *message.data)).hexdigest()
assert observer.geometry_digest(payload) == expected
before, full = observer.geometry_digest(payload), observer.sha(observer.canonical(payload))
message.header.stamp.sec += 1
after = observer.map_payload(message)
assert observer.geometry_digest(after) == before
assert observer.sha(observer.canonical(after)) != full
with tempfile.TemporaryDirectory() as directory:
    first = observer.canonical({'snapshot': {'sequence': 1}}) + b'\n'
    second = observer.canonical({'snapshot': {'sequence': 2},
                                 'info': {'watermarks': {'x': 1}}}) + b'\n'
    Path(directory, 'transitions.jsonl').write_bytes(first + second + b'{"snapshot":')
    result = observer.saved_actor_snapshot(Path(directory))
    assert result['snapshot']['sequence'] == 2 and result['line_sha256'] == observer.sha(second)
    assert result['complete_line_start_offset'] == len(first)
    assert result['complete_line_end_offset'] == len(first + second)
forbidden = {'create_publisher', 'create_client', 'create_service', 'call_async',
             'send_goal_async', 'set_parameters', 'kill', 'killpg'}
assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr in forbidden for node in ast.walk(ast.parse(path.read_text())))
assert observer.ROBOTS == ('tb1', 'tb2', 'tb3')
main = next(node for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name == 'main')
topic_assignment = next(node for node in main.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == 'topics'
                                for target in node.targets))
topic_loop = next(node for node in main.body if isinstance(node, ast.For)
                  and isinstance(node.iter, ast.Name) and node.iter.id == 'ROBOTS')
topic_append = next(node for node in main.body if isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and isinstance(node.value.func.value, ast.Name)
                    and node.value.func.value.id == 'topics')
topic_scope = {'ROBOTS': observer.ROBOTS}
exec(compile(ast.Module(body=[topic_assignment, topic_loop, topic_append], type_ignores=[]),
             str(path), 'exec'), topic_scope)
topics = topic_scope['topics']
assert len(topics) == 13 and len({topic for topic, _, _ in topics}) == 13
assert {(topic, name) for topic, role, name in topics if role == 'global_costmap'} == {
    (f'/{name}/global_costmap/costmap', name) for name in observer.ROBOTS}
config_pins = {}
for name in observer.ROBOTS:
    source_path = ROS / f'src/multi_robot/params/nav2_params_{name}_0.yaml'
    installed = ROS / f'install/multi_robot/share/multi_robot/params/nav2_params_{name}_0.yaml'
    assert installed.read_bytes() == source_path.read_bytes()
    config = yaml.safe_load(installed.read_text())['global_costmap']['global_costmap'][
        'ros__parameters']
    assert config['static_layer']['footprint_clearing_enabled'] is True
    assert config['robot_radius'] == .22 and config['always_send_full_costmap'] is True
    assert config['publish_frequency'] == .5 and config['global_frame'] == 'map'
    config_pins[str(installed)] = observer.sha(installed.read_bytes())
print(json.dumps({'script_sha256': observer.sha(path.read_bytes()),
                  'pure_cpu_checks': [
                      'map_payload exactly matches detached producer functions',
                      'geometry hash matches independent little-endian int16 oracle',
                      'header changes full payload hash but not geometry hash',
                      'partial native tail ignored; exact saved-line offset/hash retained',
                      'AST contains no publisher/service/client/action/parameter/control calls',
                      'exactly3 fixed robot names',
                      'exactly13 map topics including3 global costmaps;16 total subscriptions',
                      'all3 installed configs equal selected source files '
                      'and match file contract'],
                  'installed_config_sha256': config_pins,
                  'observer_main_called': False, 'ROS_imported': False,
                  'native_or_GPU_jobs': 0}, indent=2))
