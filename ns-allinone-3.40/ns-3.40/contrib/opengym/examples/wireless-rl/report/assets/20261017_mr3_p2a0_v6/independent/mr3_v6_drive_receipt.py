from pathlib import Path
import hashlib
import json

root = Path('/home/zhuyulab/ns3-workspace')
package = root / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot'
paths = [package / p for p in (
    'CMakeLists.txt', 'package.xml', 'src/mr3_gazebo_diff_drive.cpp',
    'include/multi_robot/mr3_gazebo_diff_drive.hpp',
    'include/multi_robot/paired_wheel_slew.hpp', 'test/test_paired_wheel_slew.cpp',
    'vendor/gazebo_ros_diff_drive.BSD-3-Clause.txt',
    'vendor/gazebo_ros_diff_drive.PROVENANCE.md',
)]


def item(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


checks = [
    ('/tmp/mr3_p2a0_v6_drive_build_01.log', 'FAIL: CMake SHA256 inputs incorrectly relative to build directory; corrected to CMAKE_CURRENT_SOURCE_DIR absolute paths'),
    ('/tmp/mr3_p2a0_v6_drive_build_02.log', 'PASS intermediate implementation; not final-source proof'),
    ('/tmp/mr3_p2a0_v6_drive_build_03.log', 'PASS intermediate weak-callback lifecycle implementation; later command_topic provenance added'),
    ('/tmp/mr3_p2a0_v6_drive_build_04.log', 'PASS final-source canonical colcon build --packages-select multi_robot --symlink-install'),
    ('/tmp/mr3_p2a0_v6_drive_tests_01.log', 'PASS intermediate 7 helper cases and 13 existing cases'),
    ('/tmp/mr3_p2a0_v6_drive_tests_02.log', 'PASS final 21 gtests in 3 CTest targets, including 8 paired-wheel helper cases'),
    ('/tmp/mr3_p2a0_v6_drive_dlopen_cpu_build.txt', 'PASS g++ C++17 actual plugin factory test build'),
    ('/tmp/mr3_p2a0_v6_drive_dlopen_cpu_result.txt', 'PASS 1000 actual final-library factory/create/destroy cycles without ModelPlugin::Load or a world'),
    ('/tmp/mr3_p2a0_v6_drive_ldd.txt', 'PASS ldd -r, no missing libraries or undefined symbols'),
    ('/tmp/mr3_p2a0_v6_drive_static_verification_v1.json', 'PASS retained upstream odometry bodies, source declarations and installed binary hashes'),
]
receipt = {
    'schema': 'mr3-v6-vendored-drive-checks-v1',
    'base_source_freeze': '57b7c7f372aef4d84acd25fcd97a9944fa1fe9bb',
    'status': 'working candidate, not committed; no native Gazebo run',
    'source_files': [item(p) for p in paths],
    'installed_library': item(root / 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so'),
    'checks': [dict(item(Path(p)), result=result) for p, result in checks],
    'commands': {
        'build': 'source /opt/ros/humble/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon build --packages-select multi_robot --symlink-install --event-handlers console_direct+',
        'test': 'source /opt/ros/humble/setup.bash; export PYTHONNOUSERSITE=1; /usr/bin/python3 /usr/bin/colcon test --packages-select multi_robot --event-handlers console_direct+',
        'static': 'python3 /tmp/mr3_v6_drive_static_verify.py',
        'dlopen': 'source /opt/ros/humble/setup.bash; /tmp/mr3_v6_drive_dlopen_cpu /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so',
        'link': 'ldd -r ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so',
        'whitespace': 'git diff --check (exit 0)',
    },
    'build_warnings': 'Upstream Gazebo CMake PkgConfig naming warning and Gazebo-11 deprecated std::iterator header warning retained; no compilation or link errors in final build.',
    'scope': 'Paired measured-feedback wheel reference logic, producer ownership, source/compiled declarations, dynamic-library loading and CPU mathematical properties only. No physical body response, stopping, collision, task, training, callback race stress, or native shutdown reliability credit.',
    'retained_failure_scope': 'v5 original WORLD odom 1.3969248505326008 angular violation and its 15 actions remain FAIL. Joint feedback, hidden old instructions and actuator receipt times were not recorded there, so old latent state cannot be uniquely replayed or asserted as the proved physical root cause.',
}
out = Path('/tmp/mr3_p2a0_v6_drive_checks_v1.json')
with out.open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(item(out)))
