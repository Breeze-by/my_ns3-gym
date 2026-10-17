from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

root = Path('/home/zhuyulab/ns3-workspace')
package = root / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot'
upstream_path = Path('/tmp/mr3_p2a0_v5_diffdrive_primary_source_v1/upstream_3.9.0.cpp')
upstream = upstream_path.read_text()
current_path = package / 'src/mr3_gazebo_diff_drive.cpp'
current = current_path.read_text()


def function(text, name):
    match = re.search(r'^void \w+::' + name + r'\(', text, re.M)
    assert match, name
    start = text.index('{', match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


functions = {}
for name in ('UpdateOdometryEncoder', 'UpdateOdometryWorld', 'PublishOdometryTf',
             'PublishWheelsTf', 'PublishOdometryMsg'):
    original = function(upstream, name).replace('GazeboRosDiffDrive', 'MR3GazeboDiffDrive')
    actual = function(current, name)
    functions[name] = {
        'unchanged_except_private_class_rename': actual == original,
        'sha256': hashlib.sha256(actual.encode()).hexdigest(),
    }
    assert actual == original, name
assert 'wheel_speed_instr_[2 * i + LEFT] +=' not in current
assert 'wheel_speed_instr_[2 * i + RIGHT] +=' not in current
assert current.count('std::weak_ptr<MR3GazeboDiffDrivePrivate>(impl_)') == 3
assert 'state->update_connection_.reset();' in current
assert 'state->cmd_vel_sub_.reset();' in current
assert 'state->target_sub_.reset();' in current
assert 'mr3-drive-actuation-v2' in current
assert 'mr3_drive/target' in current and 'mr3_drive/status' in current
assert 'rclcpp::QoS(1).reliable().transient_local()' in current
assert 'std::bind(' not in current
assert 'std::fopen(audit_path.c_str(), "wx")' in current
flags = (root / 'ros2_ws/ros2-multi-robot-automap/build/multi_robot/CMakeFiles/mr3_gazebo_diff_drive.dir/flags.make').read_text()
sources = {}
for label, relative in (
    ('SOURCE', 'src/mr3_gazebo_diff_drive.cpp'),
    ('HEADER', 'include/multi_robot/mr3_gazebo_diff_drive.hpp'),
    ('HELPER', 'include/multi_robot/paired_wheel_slew.hpp'),
    ('TARGET', 'include/multi_robot/mr3_drive_target.hpp'),
):
    path = package / relative
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert f'MR3_DRIVE_{label}_SHA256=\\"{sha}\\"' in flags, label
    sources[str(path.relative_to(root))] = sha
xmls = list((root / 'ros2_ws/ros2-multi-robot-automap/build/multi_robot/test_results/multi_robot').glob('*.gtest.xml'))
tests = {'tests': 0, 'failures': 0, 'errors': 0, 'disabled': 0}
for path in xmls:
    node = ET.fromstring(path.read_bytes())
    for key in tests:
        tests[key] += int(node.attrib.get(key, 0))
assert tests['tests'] > 0 and tests['failures'] == tests['errors'] == 0
so = root / 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so'
receipt = {
    'schema': 'mr3-v7-drive-static-source-verification-v1',
    'passed': True,
    'upstream_cpp_sha256': hashlib.sha256(upstream_path.read_bytes()).hexdigest(),
    'unchanged_odometry_functions': functions,
    'compiled_hashes_match_current_sources': sources,
    'installed_library_realpath': str(so.resolve()),
    'installed_library_sha256': hashlib.sha256(so.read_bytes()).hexdigest(),
    'gtests': tests,
    'scope': 'Source/binary hash declaration, retained odometry computations, weak callback ownership structure and CPU tests; no Gazebo, native physical response, task, or braking credit.',
}
out = Path('/tmp/mr3_p2a0_v7_drive_static_verification_v1.json')
with out.open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(receipt, indent=2))
