"""New source cadence must satisfy the existing certificate and preserve wheels."""

from pathlib import Path
import subprocess

import pytest

from multi_robot_exploration.mr3_motion_safety import SettledTurnTracker


def payload(source_ns):
    return {"header": {"stamp": {"sec": source_ns // 10**9, "nanosec": source_ns % 10**9},
                       "frame_id": "odom"}, "child_frame_id": "base_footprint",
            "pose": {"pose": {"position": {"x": 0., "y": 0., "z": 0.}}},
            "twist": {"twist": {"linear": {"x": 0., "y": 0., "z": 0.},
                                "angular": {"x": 0., "y": 0., "z": .8}}}}


def certificate_clocks(period_ms, phase_ms):
    tracker = SettledTurnTracker()
    tracker.output(0., 0, 1)
    source_sequence = 0
    records = []
    for milliseconds in range(1, 2201):
        if milliseconds >= phase_ms and (milliseconds - phase_ms) % period_ms == 0:
            source_sequence += 1
            tracker.observe(payload(milliseconds * 1_000_000), source_sequence)
        if milliseconds >= 1100 and milliseconds % 20 == 0:
            records.append((milliseconds, tracker.certificate(milliseconds * 1_000_000)))
    return records


@pytest.mark.parametrize("phase_ms", range(20))
def test_fifty_hz_real_distinct_sources_fit_original_three_sample_100ms_gate(phase_ms):
    records = certificate_clocks(20, phase_ms)
    assert records and all(certificate is not None for _, certificate in records)
    for clock_ms, certificate in records:
        samples = certificate["samples"]
        assert len(samples) == 3
        assert [samples[index + 1]["source_ns"] - samples[index]["source_ns"]
                for index in range(2)] == [20_000_000, 20_000_000]
        assert 40_000_000 <= clock_ms * 1_000_000 - samples[0]["source_ns"] <= 59_000_000


def test_old_34ms_odd_phase_retains_its_real_340ms_qualification_holes():
    failed = [clock for clock, certificate in certificate_clocks(34, 19)
              if certificate is None]
    assert len(failed) >= 3
    assert all(second - first == 340 for first, second in zip(failed, failed[1:]))


def test_driver_math_and_wheel_tf_preserve_accepted_bytes_after_exact_feed_projection():
    root = Path(__file__).resolve().parents[5]
    relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp"
    before = subprocess.check_output([
        "git", "show", "92f8bdf5bba1ba245dc53ca0964eef81a7fff938:" + relative], cwd=root).decode()
    current = (root / relative).read_text()
    start = "  // Update robot in case new velocities have been requested\n"
    end = "\nvoid MR3GazeboDiffDrivePrivate::UpdateWheelVelocities()"
    tail = current.split(start, 1)[1].split(end, 1)[0]
    # V15 intentionally adds real write-result/receipt instrumentation. Remove
    # only these exact declared additions, then compare the complete remaining
    # actuator body to the accepted implementation; no math is wildcarded.
    additions = [
        '''  std::vector<multi_robot::drive_feed::AppliedPair> applied_pairs;
  if (tagged_commands_ && !consumed_target_message_.is_null()) {
    applied_pairs.reserve(num_wheel_pairs_);
  }
  bool wheel_writes_succeeded = true;
''',
        '    wheel_writes_succeeded = wheel_writes_succeeded && left_written && right_written;\n',
        '''    if (tagged_commands_ && !consumed_target_message_.is_null()) {
      applied_pairs.push_back({i, current, desired, limited.applied,
        limited.alpha, max_wheel_accel_});
    }
''',
        '''  // All pairs have actually been written in this WorldUpdateBegin phase.
  // lock_ still protects this exact target snapshot against OnTarget.
  if (tagged_commands_ && !consumed_target_message_.is_null()) {
    if (!wheel_writes_succeeded) {
      throw std::runtime_error("MR3 applied feed cannot acknowledge a failed wheel SetParam");
    }
    std_msgs::msg::String applied;
    applied.data = multi_robot::drive_feed::Applied(
      epoch_, robot_, now_ns, actuation_sequence_, consumed_command_sequence_,
      dt_ns, consumed_target_message_, applied_pairs).dump();
    applied_pub_->publish(applied);
  }

''',
    ]
    for addition in additions:
        assert tail.count(addition) == 1
        tail = tail.replace(addition, '')
    for wheel in ('left', 'right'):
        prefix = f'const bool {wheel}_written = joints_'
        assert tail.count(prefix) == 1
        tail = tail.replace(prefix, 'joints_')
    assert tail == before.split(start, 1)[1].split(end, 1)[0]
    start = "void MR3GazeboDiffDrivePrivate::UpdateOdometryWorld()\n"
    body = current.split(start, 1)[1].split("\n}\n", 1)[0]
    environment = '''  if (tagged_commands_) {
    multi_robot::drive_feed::ValidateConversionEnvironment();
  }
'''
    coefficients = '''  const float coefficient_c = cosf(yaw);
  const float coefficient_s = sinf(yaw);
  odometry_coefficient_c_ = coefficient_c;
  odometry_coefficient_s_ = coefficient_s;
'''
    for addition in (environment, coefficients):
        assert body.count(addition) == 1
        body = body.replace(addition, '')
    body = body.replace('coefficient_c *', 'cosf(yaw) *').replace('coefficient_s *', 'sinf(yaw) *')
    assert body == before.split(start, 1)[1].split("\n}\n", 1)[0]
    start = "void MR3GazeboDiffDrivePrivate::PublishWheelsTf("
    end = "\nvoid MR3GazeboDiffDrivePrivate::PublishOdometryMsg("
    assert current.split(start, 1)[1].split(end, 1)[0] == before.split(start, 1)[1].split(end, 1)[0]
    helper = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/paired_wheel_slew.hpp"
    assert (root / helper).read_bytes() == subprocess.check_output([
        "git", "show", "92f8bdf5bba1ba245dc53ca0964eef81a7fff938:" + helper], cwd=root)


def test_actual_driver_load_fixes_tagged20ms_and_preserves_untagged_contract(tmp_path):
    root = Path(__file__).resolve().parents[5]
    relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp"
    current = (root / relative).read_text()
    start = current.index('  if (_sdf->HasElement("mr3_odometry_period_ns")) {')
    end = current.index('  impl_->last_odometry_time_ns_ =', start)
    actual_period_branch = current[start:end]
    start = current.index('  if (impl_->odometry_period_ns_ != 0) {', end)
    end = current.index('    if (impl_->audit_) {', start)
    actual_publication_guard = current[start:end] + '  }\n'
    # Compile the actual Load branches with only their independent input fields.
    # This exercises the real production decisions without a Gazebo world/node.
    head = r"""
#include <cassert>
#include <cstdint>
#include <stdexcept>
#include <string>
struct Sdf {
  bool obsolete;
  bool HasElement(const std::string & key) const {
    assert(key == "mr3_odometry_period_ns"); return obsolete;
  }
};
struct MR3GazeboDiffDrivePrivate {
  enum { WORLD = 1 };
  bool tagged_commands_; int odom_source_; int64_t odometry_period_ns_;
  bool publish_odom_; bool publish_odom_tf_;
};
struct Result { bool accepted; int64_t period; };
Result actual(bool tagged, int source, bool obsolete, bool odom, bool tf) {
  Sdf sdf{obsolete}; auto * _sdf = &sdf;
  MR3GazeboDiffDrivePrivate data{tagged, source, 0, odom, tf}; auto * impl_ = &data;
  try {
"""
    tail = r"""
    return {true, impl_->odometry_period_ns_};
  } catch (const std::invalid_argument &) { return {false, -1}; }
}
int main() {
  for (bool tagged : {false, true}) for (int source : {0, 1})
  for (bool obsolete : {false, true}) for (bool odom : {false, true})
  for (bool tf : {false, true}) {
    auto result = actual(tagged, source, obsolete, odom, tf);
    bool expected = !obsolete && (!tagged || (source == 1 && odom && tf));
    assert(result.accepted == expected);
    if (result.accepted) assert(result.period == (tagged ? 20000000 : 0));
  }
}
"""
    source = tmp_path / "actual_load_contract.cpp"
    source.write_text(head + actual_period_branch + actual_publication_guard + tail)
    binary = tmp_path / "actual_load_contract"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True, capture_output=True, text=True)
    subprocess.run([str(binary)], check=True, capture_output=True, text=True)
