#!/usr/bin/python3
"""Read-only static probe/API review. Executes no C++, ROS, build or child process."""
from pathlib import Path
import hashlib
import json
import time

D = Path(__file__).parent
BASE = Path('/tmp/mr3_p2a0_v25_smoother_clock_source_review_v1')


def bound(path):
    def identity(s):
        return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
    before = path.stat()
    raw = path.read_bytes()
    assert identity(before) == identity(path.stat())
    return raw, {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                 'bytes': len(raw), 'stat': identity(before)}


def main():
    started = time.monotonic()
    paths = [Path(__file__), BASE / 'handoff_v1.json',
             BASE / 'probe/smoother_clock_probe.cpp', BASE / 'probe/CMakeLists.txt',
             BASE / 'probe/run_probe_pair_v1.py', BASE / 'proposed_package/src/velocity_smoother.cpp',
             BASE / 'primary/tag_1_1_20_velocity_smoother.cpp',
             Path('/opt/ros/humble/include/rclcpp/rclcpp/create_timer.hpp'),
             Path('/opt/ros/humble/include/rclcpp/rclcpp/timer.hpp'),
             Path('/opt/ros/humble/include/rclcpp/rclcpp/duration.hpp'),
             Path('/opt/ros/humble/include/nav2_velocity_smoother/velocity_smoother.hpp'),
             Path('/opt/ros/humble/share/nav2_velocity_smoother/cmake/ament_cmake_export_libraries-extras.cmake')]
    captured = [bound(path) for path in paths]
    handoff = json.loads(captured[1][0])
    for index,key in ((2,'probe_cpp_sha256'),(4,'probe_wrapper_sha256'),(5,'source_sha256')):
        assert captured[index][1]['sha256'] == handoff[key]
    probe, wrapper, fixed, stock, api, timer, duration, header = [captured[i][0].decode() for i in (2,4,5,6,7,8,9,10)]
    assert 'std::shared_ptr<node_interfaces::NodeBaseInterface> node_base' in api
    assert 'std::shared_ptr<node_interfaces::NodeTimersInterface> node_timers' in api
    assert 'rclcpp::Clock::SharedPtr clock' in api and 'rclcpp::Duration period' in api
    assert 'return clock_->get_clock_type() == RCL_STEADY_TIME;' in timer
    assert 'rclcpp::TimerBase::SharedPtr timer_' in header
    assert 'geometry_msgs::msg::Twist::SharedPtr command_' in header
    assert header.index('protected:') < header.index('rclcpp::TimerBase::SharedPtr timer_')
    assert fixed.count('timer_ = rclcpp::create_timer(') == 2
    assert fixed.count('get_node_base_interface(), get_node_timers_interface(), get_clock(),') == 2
    assert probe.index('rclcpp::init(argc, argv)') < probe.index('executor = std::make_unique')
    assert 'auto clock_pub = driver->create_publisher<rosgraph_msgs::msg::Clock>' in probe
    assert 'smoother->set_parameters({rclcpp::Parameter("smoothing_frequency", 10.)})' in probe
    timeout_begin = stock.index('if (now() - last_command_time_ > velocity_timeout_)')
    timeout_end = stock.index('  stopped_ = false;', timeout_begin)
    stopped_return = stock.index('      return;', timeout_begin)
    assert timeout_begin < stopped_return < timeout_end
    assert '"velocity_timeout", rclcpp::ParameterValue(1.0)' in stock
    assert 'last_command_time_ = now();' in stock
    assert 'process.wait()' in wrapper and 'process.kill(' not in wrapper and 'process.terminate(' not in wrapper
    assert 'RTLD_NOW | RTLD_NOLOAD' in probe and '::dladdr(symbol, &info)' in probe
    assert 'os.path.samefile(value['loaded_library_path'], library)' in wrapper
    result = {
        'schema': 'mr3-v25-smoother-probe-api-independent-static-review-v1',
        'verdict': 'no_identified_static_API_or_fixture_blocker',
        'scope': 'Static source/header review only. No compilation, C++ execution, ROS/DDS, native, official tests or canonical mutations.',
        'input_bindings': [x[1] for x in captured],
        'reviewed_probe_sha256': captured[2][1]['sha256'],
        'reviewed_wrapper_sha256': captured[4][1]['sha256'],
        'reviewed_proposed_library_source_sha256': captured[5][1]['sha256'],
        'findings': [
            {'topic': 'HumbletimerAPI', 'conclusion': 'Both replacement sites match installed create_timer(base,timers,clock,Duration,callback) template; explicit chrono milliseconds Duration is supported. GenericTimer receives the node clock and is_steady reports RCL_STEADY_TIME only.',
             'source_locations': ['create_timer.hpp:36-51', 'duration.hpp:41-50', 'timer.hpp:262-265']},
            {'topic': 'Public/protectedinterfaces', 'conclusion': 'Timer and command access are legitimate protected members; lifecycle trigger methods are public inherited APIs. SingleThreadedExecutor is created after init. Node namespaces and topic names agree.'},
            {'topic': 'Lifecycleandclocks', 'conclusion': 'configure/activate precede match waits and synthetic clock. Initial1s jump is drained before command. Fixed test advances9*50ms; dynamic reconfiguration10Hz recreates timer with same clock. Pause checks include no-command jump drainage and actual output subscription.'},
            {'topic': 'Zero5thstepquestion', 'conclusion': 'No unconditional zero-output early return. The return is nested inside ROS velocity_timeout. Zero command refreshes last_command_time at1.45s; finalclock1.95s is only.5s later, below default1s. Both stock/fixed can continue publishing after reaching zero in this fixture. Float subtraction can leave tiny positive vx until5th step; no exact-rest assumption is needed.',
             'static_times_ns': {'command_refresh': 1450000000, 'last_clock': 1950000000, 'elapsed': 500000000, 'default_timeout': 1000000000},
             'source_locations': ['officialvelocity_smoother.cpp:258-266', 'officialvelocity_smoother.cpp:194', 'probe:paused_10hz/advance_10hz']},
            {'topic': 'Libraryselection', 'conclusion': 'Actual linked function dlsym/dladdr and maps recorded. Per-child LD_LIBRARY_PATH puts selected stock/fixed directory first; wrapper requires samefile with intended library and actual mapped path plus source/library hash/stat before/after. A misselected runtime library becomes a failure. Build receipt is bound by bytes but not independently interpreted in wrapper; root canonical build proof supplies that separate source/ELF relationship.'},
            {'topic': 'Cleanupandguards', 'conclusion': 'Normal lifecycle deactivation/cleanup then node/executor reset and shutdown; exceptions keep passed false.10s is cooperative work-loop deadline,15s is measured natural-close ceiling and wrapper also checks it. Neither is a preemptive guarantee for blocked middleware/lifecycle/destructor; wrapper deliberately uses wait without timeout/signal/retry. No ROS/Gazebo/task claim follows.'},
            {'topic': 'Measuredscope', 'conclusion': 'Probe asserts timer clock type, paused output counts, resumed output, configuredcaps and normal cleanup. It does not assert every50ms/100ms actual delta or continuous dv/dt. Any later output-increment review is separate, from actual samples and phase clocks; no body1.2, contact, stopping or matrix proof supplied.'}
        ],
        'root_stop_fixture_concern': 'Resolved by exact defaulttimeout nesting, not by modifying source or relaxing assertions.',
        'required_changes_identified': [],
        'future_actual_probe_status': 'Not executed by reviewer; compile/link/RMW/discovery/performance still require actual result.',
        'no_build_or_run': True, 'no_canonical_write': True}
    assert [x[1] for x in captured] == [bound(path)[1] for path in paths]
    result['all_input_bindings_end_stable'] = True
    result['review_wall_seconds'] = time.monotonic() - started
    out = D / 'review_v1.json'
    assert not out.exists()
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'review': str(out), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                      'verdict': result['verdict'], 'input_bindings_stable': True}))

if __name__ == '__main__':
    main()
