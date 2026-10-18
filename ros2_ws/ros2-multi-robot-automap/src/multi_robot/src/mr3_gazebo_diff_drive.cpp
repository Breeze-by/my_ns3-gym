// Copyright (c) 2010, Daniel Hewlett, Antons Rebguns
// All rights reserved.
//
// Software License Agreement (BSD License 2.0)
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions
// are met:
//
//  * Redistributions of source code must retain the above copyright
//    notice, this list of conditions and the following disclaimer.
//  * Redistributions in binary form must reproduce the above
//    copyright notice, this list of conditions and the following
//    disclaimer in the documentation and/or other materials provided
//    with the distribution.
//  * Neither the name of the company nor the names of its
//    contributors may be used to endorse or promote products derived
//    from this software without specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
// "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
// LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
// FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
// COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
// INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
// BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
// LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
// CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
// LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
// ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
// POSSIBILITY OF SUCH DAMAGE.

/*
 * \file  gazebo_ros_diff_drive.cpp
 *
 * \brief A differential drive plugin for gazebo. Based on the diffdrive plugin
 * developed for the erratic robot (see copyright notice above). The original
 * plugin can be found in the ROS package gazebo_erratic_plugins.
 *
 * \author  Piyush Khandelwal (piyushk@gmail.com)
 *
 * $ Id: 06/21/2013 11:23:40 AM piyushk $
 */

/*
 *
 * The support of acceleration limit was added by
 * \author   George Todoran <todorangrg@gmail.com>
 * \author   Markus Bader <markus.bader@tuwien.ac.at>
 * \date 22th of May 2014
 */

#include <gazebo/common/Time.hh>
#include <gazebo/physics/Joint.hh>
#include <gazebo/physics/Link.hh>
#include <gazebo/physics/Model.hh>
#include <gazebo/physics/World.hh>
#include <multi_robot/mr3_gazebo_diff_drive.hpp>
#include <gazebo_ros/conversions/builtin_interfaces.hpp>
#include <gazebo_ros/conversions/geometry_msgs.hpp>
#include <gazebo_ros/node.hpp>
#include <geometry_msgs/msg/pose2_d.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <std_msgs/msg/string.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <sdf/sdf.hh>

#ifdef NO_ERROR
// NO_ERROR is a macro defined in Windows that's used as an enum in tf2
#undef NO_ERROR
#endif

#ifdef IGN_PROFILER_ENABLE
#include <ignition/common/Profiler.hh>
#endif

#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2_ros/transform_broadcaster.h>
#include <tf2_ros/transform_listener.h>

#include <memory>
#include <nlohmann/json.hpp>
#include <dlfcn.h>
#include <cstdio>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>
#include "multi_robot/paired_wheel_slew.hpp"
#include "multi_robot/mr3_drive_target.hpp"
#include "multi_robot/mr3_odometry_json.hpp"

namespace mr3_gazebo_plugins
{
namespace
{
void LibraryAnchor() {}

int64_t SimNanoseconds(const gazebo::common::Time & time)
{
  return static_cast<int64_t>(time.sec) * 1000000000LL + time.nsec;
}
}  // namespace

class MR3GazeboDiffDrivePrivate
{
public:
  /// Indicates where the odometry info is coming from
  enum OdomSource
  {
    /// Use an ancoder
    ENCODER = 0,

    /// Use ground truth from simulation world
    WORLD = 1,
  };

  /// Indicates which wheel
  enum
  {
    /// Right wheel
    RIGHT = 0,

    /// Left wheel
    LEFT = 1,
  };

  /// Callback to be called at every simulation iteration.
  /// \param[in] _info Updated simulation info.
  void OnUpdate(const gazebo::common::UpdateInfo & _info);

  /// Callback when a velocity command is received.
  /// \param[in] _msg Twist command message.
  void OnCmdVel(const geometry_msgs::msg::Twist::SharedPtr _msg);
  /// Consume a versioned guard target in adapter mode, rejecting stale state.
  void OnTarget(const std_msgs::msg::String::SharedPtr message);

  /// Update wheel velocities according to latest target velocities.
  void UpdateWheelVelocities();
  /// Append execution provenance without reading external robot information.
  void Audit(const char * kind, int64_t sim_time_ns, nlohmann::json fields);
  void AuditOdometry(const char * kind, int64_t sim_time_ns, nlohmann::json fields);

  /// Update odometry according to encoder.
  /// \param[in] _current_time Current simulation time
  void UpdateOdometryEncoder(const gazebo::common::Time & _current_time);

  /// Update odometry according to world
  void UpdateOdometryWorld();

  /// Publish odometry transforms
  /// \param[in] _current_time Current simulation time
  geometry_msgs::msg::TransformStamped PublishOdometryTf(
    const gazebo::common::Time & _current_time);

  /// Publish trasforms for the wheels
  /// \param[in] _current_time Current simulation time
  void PublishWheelsTf(const gazebo::common::Time & _current_time);

  /// Publish odometry messages
  /// \param[in] _current_time Current simulation time
  void PublishOdometryMsg(const gazebo::common::Time & _current_time);

  /// A pointer to the GazeboROS node.
  gazebo_ros::Node::SharedPtr ros_node_;

  /// Subscriber to command velocities
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr target_sub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  bool tagged_commands_{false};

  /// Odometry publisher
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odometry_pub_;

  /// Connection to event called at every world iteration.
  gazebo::event::ConnectionPtr update_connection_;

  /// Distance between the wheels, in meters.
  std::vector<double> wheel_separation_;

  /// Diameter of wheels, in meters.
  std::vector<double> wheel_diameter_;

  /// Maximum wheel torque, in Nm.
  double max_wheel_torque_;

  /// Maximum wheel acceleration
  double max_wheel_accel_;

  /// Desired wheel speed.
  std::vector<double> desired_wheel_speed_;

  /// Speed sent to wheel.
  std::vector<double> wheel_speed_instr_;

  /// Pointers to wheel joints.
  std::vector<gazebo::physics::JointPtr> joints_;

  /// Pointer to model.
  gazebo::physics::ModelPtr model_;

  /// To broadcast TFs
  std::shared_ptr<tf2_ros::TransformBroadcaster> transform_broadcaster_;

  /// Protect variables accessed on callbacks.
  std::mutex lock_;

  /// Linear velocity in X received on command (m/s).
  double target_x_{0.0};

  /// Angular velocity in Z received on command (rad/s).
  double target_rot_{0.0};

  // Snapshot command and sequence under lock_ before actuation. A command
  // received later cannot change the provenance of the current update.
  uint64_t command_sequence_{0};
  uint64_t consumed_command_sequence_{0};
  int64_t target_decision_sequence_{0};
  int64_t target_clock_ns_{0};
  int64_t consumed_target_decision_sequence_{0};
  int64_t consumed_target_clock_ns_{0};
  double consumed_x_{0.0};
  double consumed_rot_{0.0};
  uint64_t actuation_sequence_{0};
  std::string epoch_;
  std::string robot_;
  std::unique_ptr<std::FILE, decltype(&std::fclose)> audit_{nullptr, &std::fclose};
  std::mutex audit_lock_;
  uint64_t audit_sequence_{0};
  std::unique_ptr<std::FILE, decltype(&std::fclose)> odometry_audit_{nullptr, &std::fclose};
  uint64_t odometry_audit_sequence_{0};
  uint64_t odometry_publication_sequence_{0};
  int64_t odometry_period_ns_{0};
  int64_t last_odometry_time_ns_{0};

  /// Update period in seconds.
  double update_period_;

  /// Last update time.
  gazebo::common::Time last_update_time_;

  /// Keep encoder data.
  geometry_msgs::msg::Pose2D pose_encoder_;

  /// Odometry frame ID
  std::string odometry_frame_;

  /// Last time the encoder was updated
  gazebo::common::Time last_encoder_update_;

  /// Either ENCODER or WORLD
  OdomSource odom_source_;

  /// Keep latest odometry message
  nav_msgs::msg::Odometry odom_;

  /// Robot base frame ID
  std::string robot_base_frame_;

  /// True to publish odometry messages.
  bool publish_odom_;

  /// True to publish wheel-to-base transforms.
  bool publish_wheel_tf_;

  /// True to publish odom-to-world transforms.
  bool publish_odom_tf_;

  /// Store number of wheel pairs
  unsigned int num_wheel_pairs_;

  /// Covariance in odometry
  double covariance_[3];
};

MR3GazeboDiffDrive::MR3GazeboDiffDrive()
: impl_(std::make_shared<MR3GazeboDiffDrivePrivate>())
{
}

MR3GazeboDiffDrive::~MR3GazeboDiffDrive()
{
  // Stop both producers before releasing the plugin's owner. Each in-flight
  // callback holds its own temporary owner, while queued callbacks hold weak
  // references only; they cannot extend a model/node/callback ownership cycle.
  auto state = std::move(impl_);
  if (state) {
    state->update_connection_.reset();
    state->cmd_vel_sub_.reset();
    state->target_sub_.reset();
  }
}

void MR3GazeboDiffDrive::Load(gazebo::physics::ModelPtr _model, sdf::ElementPtr _sdf)
{
  impl_->model_ = _model;

  // Initialize ROS node
  impl_->ros_node_ = gazebo_ros::Node::Get(_sdf);
  impl_->robot_ = impl_->ros_node_->get_namespace();
  if (!impl_->robot_.empty() && impl_->robot_.front() == '/') {
    impl_->robot_.erase(0, 1);
  }
  impl_->epoch_ = _sdf->Get<std::string>("mr3_epoch", "").first;
  impl_->tagged_commands_ = _sdf->Get<bool>("mr3_tagged_commands", false).first;
  if (impl_->tagged_commands_ && (impl_->epoch_.empty() || impl_->robot_.empty())) {
    throw std::invalid_argument("tagged drive commands require epoch and robot namespace");
  }
  const auto audit_path = _sdf->Get<std::string>("mr3_audit_path", "").first;
  if (!audit_path.empty()) {
    if (impl_->epoch_.empty()) {
      throw std::invalid_argument("mr3_audit_path requires mr3_epoch");
    }
    const auto parent = std::filesystem::path(audit_path).parent_path();
    if (!parent.empty()) {
      std::filesystem::create_directories(parent);
    }
    // Exclusive creation protects earlier native evidence, including failures.
    impl_->audit_.reset(std::fopen(audit_path.c_str(), "wx"));
    if (!impl_->audit_) {
      throw std::runtime_error("cannot exclusively create MR3 drive audit: " + audit_path);
    }
  }

  // Get QoS profiles
  const gazebo_ros::QoS & qos = impl_->ros_node_->get_qos();

  // Get number of wheel pairs in the model
  impl_->num_wheel_pairs_ = static_cast<unsigned int>(_sdf->Get<int>("num_wheel_pairs", 1).first);

  if (impl_->num_wheel_pairs_ < 1) {
    impl_->num_wheel_pairs_ = 1;
    RCLCPP_WARN(
      impl_->ros_node_->get_logger(),
      "Drive requires at least one pair of wheels. Setting [num_wheel_pairs] to 1");
  }

  // Dynamic properties
  impl_->max_wheel_accel_ = _sdf->Get<double>("max_wheel_acceleration", 0.0).first;
  impl_->max_wheel_torque_ = _sdf->Get<double>("max_wheel_torque", 5.0).first;

  // Get joints and Kinematic properties
  std::vector<gazebo::physics::JointPtr> left_joints, right_joints;

  for (auto left_joint_elem = _sdf->GetElement("left_joint"); left_joint_elem != nullptr;
    left_joint_elem = left_joint_elem->GetNextElement("left_joint"))
  {
    auto left_joint_name = left_joint_elem->Get<std::string>();
    auto left_joint = _model->GetJoint(left_joint_name);
    if (!left_joint) {
      RCLCPP_ERROR(
        impl_->ros_node_->get_logger(),
        "Joint [%s] not found, plugin will not work.", left_joint_name.c_str());
      impl_->ros_node_.reset();
      return;
    }
    left_joint->SetParam("fmax", 0, impl_->max_wheel_torque_);
    left_joints.push_back(left_joint);
  }

  for (auto right_joint_elem = _sdf->GetElement("right_joint"); right_joint_elem != nullptr;
    right_joint_elem = right_joint_elem->GetNextElement("right_joint"))
  {
    auto right_joint_name = right_joint_elem->Get<std::string>();
    auto right_joint = _model->GetJoint(right_joint_name);
    if (!right_joint) {
      RCLCPP_ERROR(
        impl_->ros_node_->get_logger(),
        "Joint [%s] not found, plugin will not work.", right_joint_name.c_str());
      impl_->ros_node_.reset();
      return;
    }
    right_joint->SetParam("fmax", 0, impl_->max_wheel_torque_);
    right_joints.push_back(right_joint);
  }

  if (left_joints.size() != right_joints.size() || left_joints.size() != impl_->num_wheel_pairs_) {
    RCLCPP_ERROR(
      impl_->ros_node_->get_logger(),
      "Inconsistent number of joints specified. Plugin will not work.");
    impl_->ros_node_.reset();
    return;
  }

  unsigned int index;
  for (index = 0; index < impl_->num_wheel_pairs_; ++index) {
    impl_->joints_.push_back(right_joints[index]);
    impl_->joints_.push_back(left_joints[index]);
  }

  index = 0;
  impl_->wheel_separation_.assign(impl_->num_wheel_pairs_, 0.34);
  for (auto wheel_separation = _sdf->GetElement("wheel_separation"); wheel_separation != nullptr;
    wheel_separation = wheel_separation->GetNextElement("wheel_separation"))
  {
    if (index >= impl_->num_wheel_pairs_) {
      RCLCPP_WARN(impl_->ros_node_->get_logger(), "Ignoring rest of specified <wheel_separation>");
      break;
    }
    impl_->wheel_separation_[index] = wheel_separation->Get<double>();
    RCLCPP_INFO(
      impl_->ros_node_->get_logger(),
      "Wheel pair %i separation set to [%fm]", index + 1, impl_->wheel_separation_[index]);
    index++;
  }

  index = 0;
  impl_->wheel_diameter_.assign(impl_->num_wheel_pairs_, 0.15);
  for (auto wheel_diameter = _sdf->GetElement("wheel_diameter"); wheel_diameter != nullptr;
    wheel_diameter = wheel_diameter->GetNextElement("wheel_diameter"))
  {
    if (index >= impl_->num_wheel_pairs_) {
      RCLCPP_WARN(impl_->ros_node_->get_logger(), "Ignoring rest of specified <wheel_diameter>");
      break;
    }
    impl_->wheel_diameter_[index] = wheel_diameter->Get<double>();
    RCLCPP_INFO(
      impl_->ros_node_->get_logger(),
      "Wheel pair %i diameter set to [%fm]", index + 1, impl_->wheel_diameter_[index]);
    index++;
  }

  impl_->wheel_speed_instr_.assign(2 * impl_->num_wheel_pairs_, 0);
  impl_->desired_wheel_speed_.assign(2 * impl_->num_wheel_pairs_, 0);

  // Update rate
  auto update_rate = _sdf->Get<double>("update_rate", 100.0).first;
  if (update_rate > 0.0) {
    impl_->update_period_ = 1.0 / update_rate;
  } else {
    impl_->update_period_ = 0.0;
  }
  impl_->last_update_time_ = _model->GetWorld()->SimTime();


  // Odometry
  impl_->odometry_frame_ = _sdf->Get<std::string>("odometry_frame", "odom").first;
  impl_->robot_base_frame_ = _sdf->Get<std::string>("robot_base_frame", "base_footprint").first;
  impl_->odom_source_ = static_cast<MR3GazeboDiffDrivePrivate::OdomSource>(
    _sdf->Get<int>("odometry_source", 1).first);
  const auto odometry_period = _sdf->Get<std::string>("mr3_odometry_period_ns", "").first;
  if (odometry_period != "" && odometry_period != "0" && odometry_period != "20000000") {
    throw std::invalid_argument("MR3 odometry period must be coupled or exactly 20000000ns");
  }
  impl_->odometry_period_ns_ = odometry_period == "20000000" ? 20000000 : 0;
  if (impl_->odometry_period_ns_ != 0 &&
    (!impl_->tagged_commands_ || impl_->odom_source_ != MR3GazeboDiffDrivePrivate::WORLD))
  {
    throw std::invalid_argument("independent MR3 odometry requires tagged WORLD source");
  }
  impl_->last_odometry_time_ns_ = SimNanoseconds(impl_->last_update_time_);

  // Advertise odometry topic
  impl_->publish_odom_ = _sdf->Get<bool>("publish_odom", false).first;
  if (impl_->publish_odom_) {
    impl_->odometry_pub_ = impl_->ros_node_->create_publisher<nav_msgs::msg::Odometry>(
      "odom", qos.get_publisher_qos("odom", rclcpp::QoS(1)));

    RCLCPP_INFO(
      impl_->ros_node_->get_logger(), "Advertise odometry on [%s]",
      impl_->odometry_pub_->get_topic_name());
  }

  // Create TF broadcaster if needed
  impl_->publish_wheel_tf_ = _sdf->Get<bool>("publish_wheel_tf", false).first;
  impl_->publish_odom_tf_ = _sdf->Get<bool>("publish_odom_tf", false).first;
  if (impl_->publish_wheel_tf_ || impl_->publish_odom_tf_) {
    impl_->transform_broadcaster_ =
      std::make_shared<tf2_ros::TransformBroadcaster>(impl_->ros_node_);

    if (impl_->publish_odom_tf_) {
      RCLCPP_INFO(
        impl_->ros_node_->get_logger(),
        "Publishing odom transforms between [%s] and [%s]", impl_->odometry_frame_.c_str(),
        impl_->robot_base_frame_.c_str());
    }

    for (index = 0; index < impl_->num_wheel_pairs_; ++index) {
      if (impl_->publish_wheel_tf_) {
        RCLCPP_INFO(
          impl_->ros_node_->get_logger(),
          "Publishing wheel transforms between [%s], [%s] and [%s]",
          impl_->robot_base_frame_.c_str(),
          impl_->joints_[2 * index + MR3GazeboDiffDrivePrivate::LEFT]->GetName().c_str(),
          impl_->joints_[2 * index + MR3GazeboDiffDrivePrivate::RIGHT]->GetName().c_str());
      }
    }
  }

  impl_->covariance_[0] = _sdf->Get<double>("covariance_x", 0.00001).first;
  impl_->covariance_[1] = _sdf->Get<double>("covariance_y", 0.00001).first;
  impl_->covariance_[2] = _sdf->Get<double>("covariance_yaw", 0.001).first;

  if (impl_->odometry_period_ns_ != 0) {
    if (!impl_->publish_odom_ || !impl_->publish_odom_tf_) {
      throw std::invalid_argument("independent MR3 odometry requires both odom and TF publication");
    }
    if (impl_->audit_) {
      const auto path = std::filesystem::path(audit_path).parent_path() /
        ("odometry_" + impl_->robot_ + ".jsonl");
      impl_->odometry_audit_.reset(std::fopen(path.c_str(), "wx"));
      if (!impl_->odometry_audit_) {
        throw std::runtime_error("cannot exclusively create native odometry audit: " + path.string());
      }
    }
  }

  if (impl_->audit_) {
    Dl_info library_info{};
    std::string library_path;
    if (dladdr(reinterpret_cast<void *>(&LibraryAnchor), &library_info) && library_info.dli_fname) {
      library_path = std::filesystem::canonical(library_info.dli_fname).string();
    }
    std::vector<std::string> joint_names;
    for (const auto & joint : impl_->joints_) {
      joint_names.push_back(joint->GetName());
    }
    impl_->Audit("configuration", SimNanoseconds(_model->GetWorld()->SimTime()), {
    {"library_filename", "libmr3_gazebo_diff_drive.so"},
    {"loaded_library_path", library_path},
    {"upstream_source_sha256", "7a6ef5eb9b48292f1b4f3d9a16907815d5d5a751e0a5635a1cac84315b95b498"},
    {"compiled_source_sha256", MR3_DRIVE_SOURCE_SHA256},
    {"compiled_header_sha256", MR3_DRIVE_HEADER_SHA256},
    {"compiled_helper_sha256", MR3_DRIVE_HELPER_SHA256},
    {"compiled_target_contract_sha256", MR3_DRIVE_TARGET_SHA256},
    {"compiled_odometry_json_sha256", MR3_ODOMETRY_JSON_HEADER_SHA256},
    {"command_mode", impl_->tagged_commands_ ? "tagged" : "twist"},
    {"command_topic", impl_->ros_node_->get_node_topics_interface()->resolve_topic_name(
      impl_->tagged_commands_ ? "mr3_drive/target" : "cmd_vel")},
    {"status_topic", impl_->tagged_commands_ ?
      impl_->ros_node_->get_node_topics_interface()->resolve_topic_name("mr3_drive/status") : ""},
    {"wheel_order", {"right", "left"}}, {"joint_names", joint_names},
    {"wheel_separation_m", impl_->wheel_separation_},
    {"wheel_diameter_m", impl_->wheel_diameter_},
    {"max_acceleration_mps2", impl_->max_wheel_accel_},
    {"max_torque_nm", impl_->max_wheel_torque_}, {"update_rate_hz", update_rate},
    {"mr3_odometry_period_ns", impl_->odometry_period_ns_},
    {"odometry_source", static_cast<int>(impl_->odom_source_)},
    {"num_wheel_pairs", impl_->num_wheel_pairs_},
      {"actuation_algorithm", "measured_joint_rim_paired_common_fraction_v1"}});
    impl_->AuditOdometry("configuration", SimNanoseconds(impl_->last_update_time_), {
      {"period_ns", impl_->odometry_period_ns_}, {"actuation_update_rate_hz", update_rate},
      {"provider", "WORLD"}, {"phase", "world_update_begin_before_actuation"},
      {"odometry_frame", impl_->odometry_frame_}, {"robot_base_frame", impl_->robot_base_frame_},
      {"loaded_library_path", library_path},
      {"compiled_source_sha256", MR3_DRIVE_SOURCE_SHA256},
      {"compiled_header_sha256", MR3_DRIVE_HEADER_SHA256},
      {"compiled_helper_sha256", MR3_DRIVE_HELPER_SHA256},
      {"compiled_target_contract_sha256", MR3_DRIVE_TARGET_SHA256},
      {"compiled_odometry_json_sha256", MR3_ODOMETRY_JSON_HEADER_SHA256},
      {"scope", "actual native publication calls; no DDS receipt or navigation consumption claim"}});
  }

  // Subscribe after configuration so the first command has declared provenance.
  if (impl_->tagged_commands_) {
    const auto status_qos = rclcpp::QoS(1).reliable().transient_local();
    impl_->status_pub_ = impl_->ros_node_->create_publisher<std_msgs::msg::String>(
      "mr3_drive/status", status_qos);
    impl_->target_sub_ = impl_->ros_node_->create_subscription<std_msgs::msg::String>(
      "mr3_drive/target", rclcpp::QoS(1).reliable().transient_local(),
      [weak = std::weak_ptr<MR3GazeboDiffDrivePrivate>(impl_)](
        const std_msgs::msg::String::SharedPtr message)
      {
        if (auto state = weak.lock()) {
          state->OnTarget(message);
        }
      });
    RCLCPP_INFO(impl_->ros_node_->get_logger(), "Subscribed tagged targets to [%s]",
      impl_->target_sub_->get_topic_name());
  } else {
    impl_->cmd_vel_sub_ = impl_->ros_node_->create_subscription<geometry_msgs::msg::Twist>(
      "cmd_vel", qos.get_subscription_qos("cmd_vel", rclcpp::QoS(1)),
      [weak = std::weak_ptr<MR3GazeboDiffDrivePrivate>(impl_)](
        const geometry_msgs::msg::Twist::SharedPtr message)
      {
        if (auto state = weak.lock()) {
          state->OnCmdVel(message);
        }
      });
    RCLCPP_INFO(impl_->ros_node_->get_logger(), "Subscribed to [%s]",
      impl_->cmd_vel_sub_->get_topic_name());
  }

  // Listen to the update event (broadcast every simulation iteration)
  impl_->update_connection_ = gazebo::event::Events::ConnectWorldUpdateBegin(
    [weak = std::weak_ptr<MR3GazeboDiffDrivePrivate>(impl_)](
      const gazebo::common::UpdateInfo & info)
    {
      if (auto state = weak.lock()) {
        state->OnUpdate(info);
      }
    });
}

void MR3GazeboDiffDrive::Reset()
{
  std::lock_guard<std::mutex> scoped_lock(impl_->lock_);
  impl_->last_update_time_ =
    impl_->joints_[MR3GazeboDiffDrivePrivate::LEFT]->GetWorld()->SimTime();
  impl_->last_odometry_time_ns_ = SimNanoseconds(impl_->last_update_time_);
  for (unsigned int i = 0; i < impl_->num_wheel_pairs_; ++i) {
    if (impl_->joints_[2 * i + MR3GazeboDiffDrivePrivate::LEFT] &&
      impl_->joints_[2 * i + MR3GazeboDiffDrivePrivate::RIGHT])
    {
      impl_->joints_[2 * i + MR3GazeboDiffDrivePrivate::LEFT]->SetParam(
        "fmax", 0, impl_->max_wheel_torque_);
      impl_->joints_[2 * i + MR3GazeboDiffDrivePrivate::RIGHT]->SetParam(
        "fmax", 0, impl_->max_wheel_torque_);
    }
  }
  impl_->pose_encoder_.x = 0;
  impl_->pose_encoder_.y = 0;
  impl_->pose_encoder_.theta = 0;
  impl_->target_x_ = 0;
  impl_->target_rot_ = 0;
  std::fill(impl_->desired_wheel_speed_.begin(), impl_->desired_wheel_speed_.end(), 0.0);
  std::fill(impl_->wheel_speed_instr_.begin(), impl_->wheel_speed_instr_.end(), 0.0);
  impl_->Audit("reset", SimNanoseconds(impl_->last_update_time_), {
    {"cmd_seq", impl_->command_sequence_}, {"target_reset", true},
    {"target_decision_sequence", impl_->target_decision_sequence_},
    {"target_clock_ns", impl_->target_clock_ns_},
    {"desired_v", 0.0}, {"desired_w", 0.0},
    {"internal_instruction_rim_mps", impl_->wheel_speed_instr_}});
}

void MR3GazeboDiffDrivePrivate::OnUpdate(const gazebo::common::UpdateInfo & _info)
{
#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE("MR3GazeboDiffDrivePrivate::OnUpdate");
#endif
  // Update encoder even if we're going to skip this update
  if (odom_source_ == ENCODER) {
    UpdateOdometryEncoder(_info.simTime);
  }

  double seconds_since_last_update = (_info.simTime - last_update_time_).Double();

  const auto now_ns = SimNanoseconds(_info.simTime);
  const bool actuation_due = !(seconds_since_last_update < update_period_);
  const bool independent_odometry = odometry_period_ns_ != 0;
  const bool odometry_due = independent_odometry ?
    now_ns - last_odometry_time_ns_ >= odometry_period_ns_ : actuation_due;
  if (!actuation_due && !odometry_due) {
    return;
  }

#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE_BEGIN("UpdateOdometryWorld");
#endif
  // Update odom message if using ground truth
  if (odometry_due && odom_source_ == WORLD) {
    UpdateOdometryWorld();
  }
#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE_END();
  IGN_PROFILE_BEGIN("PublishOdometryMsg");
#endif
  if (odometry_due && publish_odom_) {
    PublishOdometryMsg(_info.simTime);
  }
#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE_END();
  IGN_PROFILE_BEGIN("PublishWheelsTf");
#endif
  if (actuation_due && publish_wheel_tf_) {
    PublishWheelsTf(_info.simTime);
  }
#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE_END();
  IGN_PROFILE_BEGIN("PublishOdometryTf");
#endif
  geometry_msgs::msg::TransformStamped published_transform;
  if (odometry_due && publish_odom_tf_) {
    published_transform = PublishOdometryTf(_info.simTime);
  }
  if (odometry_due && independent_odometry) {
    last_odometry_time_ns_ = now_ns;
    AuditOdometry("publication", now_ns, {
      {"publication_sequence", ++odometry_publication_sequence_},
      {"source_clock_ns", now_ns}, {"odometry", multi_robot::odometry_json::odometry(odom_)},
      {"transform", multi_robot::odometry_json::transform(published_transform)},
      {"odom_published", publish_odom_}, {"odom_tf_published", publish_odom_tf_},
      {"publication_scope", "actual_publisher_calls_returned_not_delivery"}});
  }
#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE_END();
#endif
  if (!actuation_due) {
    return;
  }
#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE_BEGIN("UpdateWheelVelocities");
#endif
  // Update robot in case new velocities have been requested
  // Keep command selection, wheel writes and their audit atomic with respect
  // to OnCmdVel, so cmd_seq is the latest recorded received command.
  std::lock_guard<std::mutex> scoped_lock(lock_);
  UpdateWheelVelocities();
#ifdef IGN_PROFILER_ENABLE
  IGN_PROFILE_END();
#endif
  // Current speed
  std::vector<double> current_speed(2 * num_wheel_pairs_);
  for (unsigned int i = 0; i < num_wheel_pairs_; ++i) {
    current_speed[2 * i + LEFT] =
      joints_[2 * i + LEFT]->GetVelocity(0) * (wheel_diameter_[i] / 2.0);
    current_speed[2 * i + RIGHT] =
      joints_[2 * i + RIGHT]->GetVelocity(0) * (wheel_diameter_[i] / 2.0);
  }

  ++actuation_sequence_;
  const auto dt_ns = SimNanoseconds(_info.simTime) - SimNanoseconds(last_update_time_);
  for (unsigned int i = 0; i < num_wheel_pairs_; ++i) {
    const std::array<double, 2> current{
      current_speed[2 * i + RIGHT], current_speed[2 * i + LEFT]};
    const std::array<double, 2> desired{
      desired_wheel_speed_[2 * i + RIGHT], desired_wheel_speed_[2 * i + LEFT]};
    // Start from measured joint rim speed each update. One fraction for both
    // wheels preserves the body-twist line segment and cannot accumulate a
    // hidden command past its target when the physical joint lags.
    const auto limited = multi_robot::limit_paired_wheel_speeds(
      current, desired, max_wheel_accel_, seconds_since_last_update);
    wheel_speed_instr_[2 * i + RIGHT] = limited.applied[RIGHT];
    wheel_speed_instr_[2 * i + LEFT] = limited.applied[LEFT];
    joints_[2 * i + LEFT]->SetParam(
      "vel", 0, limited.applied[LEFT] / (wheel_diameter_[i] / 2.0));
    joints_[2 * i + RIGHT]->SetParam(
      "vel", 0, limited.applied[RIGHT] / (wheel_diameter_[i] / 2.0));
    Audit("actuation", SimNanoseconds(_info.simTime), {
      {"actuation_seq", actuation_sequence_}, {"pair_index", i},
      {"cmd_seq", consumed_command_sequence_},
      {"target_decision_sequence", consumed_target_decision_sequence_},
      {"target_clock_ns", consumed_target_clock_ns_},
      {"desired_v", consumed_x_}, {"desired_w", consumed_rot_},
      {"dt_ns", dt_ns}, {"dt_sec", seconds_since_last_update},
      {"current_rim_mps", current}, {"desired_rim_mps", desired},
      {"applied_rim_mps", limited.applied}, {"alpha", limited.alpha},
      {"max_acceleration_mps2", max_wheel_accel_}});
  }

  last_update_time_ = _info.simTime;
}

void MR3GazeboDiffDrivePrivate::UpdateWheelVelocities()
{
  double vr = target_x_;
  double va = target_rot_;
  consumed_command_sequence_ = command_sequence_;
  consumed_target_decision_sequence_ = target_decision_sequence_;
  consumed_target_clock_ns_ = target_clock_ns_;
  consumed_x_ = vr;
  consumed_rot_ = va;

  for (unsigned int i = 0; i < num_wheel_pairs_; ++i) {
    desired_wheel_speed_[2 * i + LEFT] = vr - va * wheel_separation_[i] / 2.0;
    desired_wheel_speed_[2 * i + RIGHT] = vr + va * wheel_separation_[i] / 2.0;
  }
}

void MR3GazeboDiffDrivePrivate::OnCmdVel(const geometry_msgs::msg::Twist::SharedPtr _msg)
{
  std::lock_guard<std::mutex> scoped_lock(lock_);
  target_x_ = _msg->linear.x;
  target_rot_ = _msg->angular.z;
  ++command_sequence_;
  Audit("command_received", SimNanoseconds(model_->GetWorld()->SimTime()), {
    {"cmd_seq", command_sequence_}, {"desired_v", target_x_}, {"desired_w", target_rot_},
    {"target_decision_sequence", 0}, {"target_clock_ns", 0}});
}

void MR3GazeboDiffDrivePrivate::OnTarget(const std_msgs::msg::String::SharedPtr message)
{
  std::lock_guard<std::mutex> scoped_lock(lock_);
  const auto clock_ns = SimNanoseconds(model_->GetWorld()->SimTime());
  multi_robot::DriveTarget target;
  try {
    target = multi_robot::ParseDriveTarget(nlohmann::json::parse(message->data));
    multi_robot::ValidateDriveTarget(target, epoch_, robot_, clock_ns,
      target_decision_sequence_, target_clock_ns_);
  } catch (const std::exception & error) {
    Audit("target_rejected", clock_ns, {
      {"reason", error.what()}, {"raw_target", message->data},
      {"retained_target_decision_sequence", target_decision_sequence_},
      {"retained_target_clock_ns", target_clock_ns_}, {"retained_cmd_seq", command_sequence_}});
    return;
  }
  // Validation completes before any command state changes. In particular a
  // delayed older decision can never overwrite a newer already consumed one.
  target_x_ = target.linear_x;
  target_rot_ = target.angular_z;
  target_decision_sequence_ = target.decision_sequence;
  target_clock_ns_ = target.clock_ns;
  ++command_sequence_;
  Audit("command_received", clock_ns, {
    {"cmd_seq", command_sequence_}, {"desired_v", target_x_}, {"desired_w", target_rot_},
    {"target_decision_sequence", target_decision_sequence_},
    {"target_clock_ns", target_clock_ns_}});
  const nlohmann::json status{
    {"schema", "mr3-drive-target-consumed-v1"}, {"epoch", epoch_}, {"robot", robot_},
    {"clock_ns", clock_ns}, {"decision_sequence", target_decision_sequence_},
    {"source_clock_ns", target_clock_ns_}, {"cmd_seq", command_sequence_},
    {"linear_x", target_x_}, {"angular_z", target_rot_}};
  std_msgs::msg::String response;
  response.data = status.dump();
  status_pub_->publish(response);
  Audit("status_publish", clock_ns, {
    {"cmd_seq", command_sequence_}, {"desired_v", target_x_}, {"desired_w", target_rot_},
    {"target_decision_sequence", target_decision_sequence_},
    {"target_clock_ns", target_clock_ns_}, {"status", status},
    {"scope", "target_storage_and_status_publication"}});
}

void MR3GazeboDiffDrivePrivate::Audit(
  const char * kind, int64_t sim_time_ns, nlohmann::json fields)
{
  if (!audit_) {
    return;
  }
  std::lock_guard<std::mutex> guard(audit_lock_);
  fields.update({{"schema", "mr3-drive-actuation-v2"}, {"kind", kind},
    {"epoch", epoch_}, {"robot", robot_},
    {"record_sequence", ++audit_sequence_}, {"sim_time_ns", sim_time_ns}});
  const auto line = fields.dump() + "\n";
  if (std::fwrite(line.data(), 1, line.size(), audit_.get()) != line.size() ||
    std::fflush(audit_.get()) != 0)
  {
    throw std::runtime_error("cannot persist MR3 drive execution audit");
  }
}

void MR3GazeboDiffDrivePrivate::AuditOdometry(
  const char * kind, int64_t sim_time_ns, nlohmann::json fields)
{
  if (!odometry_audit_) {
    return;
  }
  std::lock_guard<std::mutex> guard(audit_lock_);
  fields.update({{"schema", "mr3-world-odometry-publication-v1"}, {"kind", kind},
    {"epoch", epoch_}, {"robot", robot_},
    {"record_sequence", ++odometry_audit_sequence_}, {"sim_time_ns", sim_time_ns}});
  const auto line = fields.dump() + "\n";
  if (std::fwrite(line.data(), 1, line.size(), odometry_audit_.get()) != line.size() ||
    std::fflush(odometry_audit_.get()) != 0)
  {
    throw std::runtime_error("cannot persist actual native odometry publication audit");
  }
}

void MR3GazeboDiffDrivePrivate::UpdateOdometryEncoder(const gazebo::common::Time & _current_time)
{
  double vl = joints_[LEFT]->GetVelocity(0);
  double vr = joints_[RIGHT]->GetVelocity(0);

  double seconds_since_last_update = (_current_time - last_encoder_update_).Double();
  last_encoder_update_ = _current_time;

  double b = wheel_separation_[0];

  // Book: Sigwart 2011 Autonompus Mobile Robots page:337
  double sl = vl * (wheel_diameter_[0] / 2.0) * seconds_since_last_update;
  double sr = vr * (wheel_diameter_[0] / 2.0) * seconds_since_last_update;
  double ssum = sl + sr;

  double sdiff = sr - sl;

  double dx = (ssum) / 2.0 * cos(pose_encoder_.theta + (sdiff) / (2.0 * b));
  double dy = (ssum) / 2.0 * sin(pose_encoder_.theta + (sdiff) / (2.0 * b));
  double dtheta = (sdiff) / b;

  pose_encoder_.x += dx;
  pose_encoder_.y += dy;
  pose_encoder_.theta += dtheta;

  double w = dtheta / seconds_since_last_update;
  double v = sqrt(dx * dx + dy * dy) / seconds_since_last_update;

  tf2::Quaternion qt;
  tf2::Vector3 vt;
  qt.setRPY(0, 0, pose_encoder_.theta);
  vt = tf2::Vector3(pose_encoder_.x, pose_encoder_.y, 0);

  odom_.pose.pose.position.x = vt.x();
  odom_.pose.pose.position.y = vt.y();
  odom_.pose.pose.position.z = vt.z();

  odom_.pose.pose.orientation.x = qt.x();
  odom_.pose.pose.orientation.y = qt.y();
  odom_.pose.pose.orientation.z = qt.z();
  odom_.pose.pose.orientation.w = qt.w();

  odom_.twist.twist.angular.z = w;
  odom_.twist.twist.linear.x = v;
  odom_.twist.twist.linear.y = 0;
}

void MR3GazeboDiffDrivePrivate::UpdateOdometryWorld()
{
  auto pose = model_->WorldPose();
  odom_.pose.pose.position = gazebo_ros::Convert<geometry_msgs::msg::Point>(pose.Pos());
  odom_.pose.pose.orientation = gazebo_ros::Convert<geometry_msgs::msg::Quaternion>(pose.Rot());

  // Get velocity in odom frame
  auto linear = model_->WorldLinearVel();
  odom_.twist.twist.angular.z = model_->WorldAngularVel().Z();

  // Convert velocity to child_frame_id(aka base_footprint)
  float yaw = pose.Rot().Yaw();
  odom_.twist.twist.linear.x = cosf(yaw) * linear.X() + sinf(yaw) * linear.Y();
  odom_.twist.twist.linear.y = cosf(yaw) * linear.Y() - sinf(yaw) * linear.X();
}

geometry_msgs::msg::TransformStamped MR3GazeboDiffDrivePrivate::PublishOdometryTf(
  const gazebo::common::Time & _current_time)
{
  geometry_msgs::msg::TransformStamped msg;
  msg.header.stamp = gazebo_ros::Convert<builtin_interfaces::msg::Time>(_current_time);
  msg.header.frame_id = odometry_frame_;
  msg.child_frame_id = robot_base_frame_;
  msg.transform.translation =
    gazebo_ros::Convert<geometry_msgs::msg::Vector3>(odom_.pose.pose.position);
  msg.transform.rotation = odom_.pose.pose.orientation;

  transform_broadcaster_->sendTransform(msg);
  return msg;
}

void MR3GazeboDiffDrivePrivate::PublishWheelsTf(const gazebo::common::Time & _current_time)
{
  for (unsigned int i = 0; i < 2 * num_wheel_pairs_; ++i) {
    auto pose_wheel = joints_[i]->GetChild()->RelativePose();

    geometry_msgs::msg::TransformStamped msg;
    msg.header.stamp = gazebo_ros::Convert<builtin_interfaces::msg::Time>(_current_time);
    msg.header.frame_id = joints_[i]->GetParent()->GetName();
    msg.child_frame_id = joints_[i]->GetChild()->GetName();
    msg.transform.translation = gazebo_ros::Convert<geometry_msgs::msg::Vector3>(pose_wheel.Pos());
    msg.transform.rotation = gazebo_ros::Convert<geometry_msgs::msg::Quaternion>(pose_wheel.Rot());

    transform_broadcaster_->sendTransform(msg);
  }
}

void MR3GazeboDiffDrivePrivate::PublishOdometryMsg(const gazebo::common::Time & _current_time)
{
  // Set covariance
  odom_.pose.covariance[0] = covariance_[0];
  odom_.pose.covariance[7] = covariance_[1];
  odom_.pose.covariance[14] = 1000000000000.0;
  odom_.pose.covariance[21] = 1000000000000.0;
  odom_.pose.covariance[28] = 1000000000000.0;
  odom_.pose.covariance[35] = covariance_[2];

  odom_.twist.covariance[0] = covariance_[0];
  odom_.twist.covariance[7] = covariance_[1];
  odom_.twist.covariance[14] = 1000000000000.0;
  odom_.twist.covariance[21] = 1000000000000.0;
  odom_.twist.covariance[28] = 1000000000000.0;
  odom_.twist.covariance[35] = covariance_[2];

  // Set header
  odom_.header.frame_id = odometry_frame_;
  odom_.child_frame_id = robot_base_frame_;
  odom_.header.stamp = gazebo_ros::Convert<builtin_interfaces::msg::Time>(_current_time);

  // Publish
  odometry_pub_->publish(odom_);
}
GZ_REGISTER_MODEL_PLUGIN(MR3GazeboDiffDrive)
}  // namespace mr3_gazebo_plugins
