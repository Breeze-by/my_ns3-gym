# Local MR3 differential-drive plugin

This is a local derivative of `gazebo_plugins` 3.9.0. It builds
`libmr3_gazebo_diff_drive.so` under the independent `mr3_gazebo_plugins`
namespace and `MR3GazeboDiffDrive` class. It does not replace the system library.
The original copyright, BSD conditions and disclaimer remain in both source
files and in `gazebo_ros_diff_drive.BSD-3-Clause.txt`.

Primary upstream source:

- <https://github.com/ros-simulation/gazebo_ros_pkgs/blob/3.9.0/gazebo_plugins/src/gazebo_ros_diff_drive.cpp>
- <https://github.com/ros-simulation/gazebo_ros_pkgs/blob/3.9.0/gazebo_plugins/include/gazebo_plugins/gazebo_ros_diff_drive.hpp>
- <https://github.com/ros2-gbp/gazebo_ros_pkgs-release/blob/release/humble/gazebo_plugins/3.9.0-1/src/gazebo_ros_diff_drive.cpp>

The upstream and Humble release implementation downloads are identical:
23,278 bytes, SHA-256
`7a6ef5eb9b48292f1b4f3d9a16907815d5d5a751e0a5635a1cac84315b95b498`.
The installed package inspected on 2026-10-17 was
`ros-humble-gazebo-plugins 3.9.0-1jammy.20260325.235919`; its system library
SHA-256 was `931a0b3f83d08a8728fe82461c72ec85e0a360f8b50e88471c214cfaa7c72027`.
The package version identifies its declared source release; these facts do not
constitute a reproducible-build proof for that system binary.

The local actuation change replaces accumulated instructions based on joint
tracking error with `multi_robot::limit_paired_wheel_speeds`. Each update starts
from the two measured joint rim speeds. A single fraction moves both toward
their command-derived targets within `max_wheel_acceleration * sim_dt` per
wheel. The applied body twist is therefore on the line segment between the
measured wheel-derived and desired body twists. This removes hidden instruction
accumulation, including the upstream near-target branch's stale instruction
state. It is a property of the issued wheel references, not a proof of the
physical body's response under contact, slip or finite torque.

The original wheel geometry, torque, acceleration, update cadence,
odometry source and odometry computations remain controlled by the same SDF
parameters. The active model retains 30 Hz, separation 0.287 m, diameter
0.066 m, acceleration 1 m/s², torque 20 Nm and WORLD odometry. No truth state
enters actuation: it uses only the final command topic and its own joint
velocity feedback. The inherited WORLD odometry remains an output calculation.

SDF `mr3_tagged_commands` selects the actuator input contract. False retains
the baseline Twist subscription. The adapter selects true: only the unique
guard's epoch/robot/clock/decision-sequence target on `mr3_drive/target` can
update desired velocity. A rejected or older target cannot overwrite state.
After storing a valid target under the command mutex, the driver publishes
`mr3_drive/status` with its actual world clock and exact target identity.
The stepped worker requires all three matching stored-target receipts before
each 20 ms physical advance. This receipt establishes target storage, not a
30 Hz actuator update or physical body response. Both endpoints use reliable
transient-local depth-one latest-target/status delivery.

Optional SDF `mr3_audit_path` enables exclusive-create JSONL execution records;
`mr3_epoch` is then required. Empty audit path disables writing. Records include
configuration and the loaded library path from `dladdr`, actual callback
command receipt and the command consumed at every actuator update, exact
simulation timestamps, measured/desired/applied wheel rim speeds and the common
fraction. Command selection, actuation and its record are locked together.
Writes are flushed and failures propagate as native failures. CMake embeds the
implementation/header/wheel-helper/target-contract hashes and tracks them as
configure dependencies.
The actual installed shared-object hash must also be captured independently.
The public plugin cancels update/subscription producers before releasing its
private state. The callbacks capture a weak pointer and temporarily retain
state only while executing, avoiding raw-private callbacks and ownership cycles.

These traces establish the executed command/actuator chain. They do not replace
independent raw body-speed, angular acceleration, collision, stopping response,
task or shutdown checks. Historical v5 angular overshoot remains a failure; its
unrecorded joint feedback and plugin internal state cannot be uniquely replayed
from WORLD odometry and command-topic receipts alone.
