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


def test_driver_actuation_tail_and_wheel_tf_remain_exact_accepted_source_bytes():
    root = Path(__file__).resolve().parents[5]
    relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp"
    before = subprocess.check_output([
        "git", "show", "92f8bdf5bba1ba245dc53ca0964eef81a7fff938:" + relative], cwd=root).decode()
    current = (root / relative).read_text()
    start = "  // Update robot in case new velocities have been requested\n"
    end = "\nvoid MR3GazeboDiffDrivePrivate::UpdateWheelVelocities()"
    assert current.split(start, 1)[1].split(end, 1)[0] == before.split(start, 1)[1].split(end, 1)[0]
    start = "void MR3GazeboDiffDrivePrivate::UpdateOdometryWorld()\n"
    assert current.split(start, 1)[1].split("\n}\n", 1)[0] == before.split(start, 1)[1].split("\n}\n", 1)[0]
    start = "void MR3GazeboDiffDrivePrivate::PublishWheelsTf("
    end = "\nvoid MR3GazeboDiffDrivePrivate::PublishOdometryMsg("
    assert current.split(start, 1)[1].split(end, 1)[0] == before.split(start, 1)[1].split(end, 1)[0]
    helper = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/paired_wheel_slew.hpp"
    assert (root / helper).read_bytes() == subprocess.check_output([
        "git", "show", "92f8bdf5bba1ba245dc53ca0964eef81a7fff938:" + helper], cwd=root)
