from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import subprocess


root = Path('/home/zhuyulab/ns3-workspace')
ros = root / 'ros2_ws/ros2-multi-robot-automap'
assets = root / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a'
prefixes = ['ros2_ws/ros2-multi-robot-automap/src', 'ros2_ws/ros2-multi-robot-automap/scripts']
freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert freeze == subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=root, text=True).strip()
assert not subprocess.check_output(['git', 'diff', 'HEAD', '--', *prefixes], cwd=root)
assert not subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--', *prefixes], cwd=root)
files = []
for rel in subprocess.check_output(['git', 'ls-files', '-z', '--', *prefixes], cwd=root).decode().split('\0'):
    if not rel:
        continue
    path = root / rel
    data = path.read_bytes()
    assert data == subprocess.check_output(['git', 'show', freeze + ':' + rel], cwd=root)
    files.append(dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), scope='tracked_source'))

critical = ['models/turtlebot3_waffle/model.sdf', 'urdf/turtlebot3_waffle.urdf',
            'launch/gazebo_multirobot_mapping_with_nav2.launch.py', 'config/mr3_fastdds_loopback_udp.xml']
critical += ['config/mr3_p1a/' + name + '.json' for name in ['rooms', 'corridors', 'open']]
critical += ['worlds/p1c_' + name + '.world' for name in ['rooms', 'corridors', 'open']]
installed_checks = []
for rel in critical:
    source = ros / 'src/multi_robot' / rel
    installed = ros / 'install/multi_robot/share/multi_robot' / rel
    assert source.read_bytes() == installed.read_bytes(), rel
    files.append(dict(path=str(installed), sha256=hashlib.sha256(installed.read_bytes()).hexdigest(),
                      scope='installed_runtime_source_identical'))
    installed_checks.append(dict(source=str(source), installed=str(installed), identical=True))
for name in ['control', 'task_evaluator', 'mr3_contacts', 'mr3_task_contract', 'nav2_ready_gate', 'peer_obstacles']:
    installed = Path(importlib.util.find_spec('multi_robot_exploration.' + name).origin)
    source = ros / 'src/multi_robot_exploration/multi_robot_exploration' / (name + '.py')
    assert installed.read_bytes() == source.read_bytes(), name
    files.append(dict(path=str(installed), sha256=hashlib.sha256(installed.read_bytes()).hexdigest(),
                      scope='resolved_python_import_source_identical'))
    installed_checks.append(dict(source=str(source), installed=str(installed), identical=True))

native_paths = [ros / 'install/multi_robot/lib/multi_robot/mr3_contact_reducer']
native_paths += [p for p in (ros / 'install').rglob('*.so') if 'peer' in p.name]
for path in native_paths:
    files.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      scope='installed_native_binary'))
out = dict(recorded_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), source_freeze=freeze,
           type='Predeclared_matrix5_source_and_installed_runtime_binding', files=files,
           installed_source_identity_checks=installed_checks,
           hash_algorithm='sha256', simulator_runs=0, training_runs=0)
path = assets / 'runtime_component_manifest_matrix5.json'
with path.open('x') as output:
    json.dump(out, output, indent=2)
    output.write('\n')
print(json.dumps(dict(source_freeze=freeze, files=len(files), installed_source_checks=len(installed_checks),
                      native_binaries=len(native_paths), result='PASS'), indent=2))
