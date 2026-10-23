// Copyright (c) 2022 Samsung Research
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <chrono>
#include <limits>
#include <memory>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "nav2_velocity_smoother/velocity_smoother.hpp"
#include "rclcpp/create_timer.hpp"

using namespace std::chrono_literals;
using nav2_util::declare_parameter_if_not_declared;
using std::placeholders::_1;
using rcl_interfaces::msg::ParameterType;

namespace nav2_velocity_smoother
{

VelocitySmoother::VelocitySmoother(const rclcpp::NodeOptions & options)
: LifecycleNode("velocity_smoother", "", options),
  last_command_time_{0, 0, get_clock()->get_clock_type()}
{
}

VelocitySmoother::~VelocitySmoother()
{
  if (timer_) {
    timer_->cancel();
    timer_.reset();
  }
}

nav2_util::CallbackReturn
VelocitySmoother::on_configure(const rclcpp_lifecycle::State &)
{
  RCLCPP_INFO(get_logger(), "Configuring velocity smoother");
  auto node = shared_from_this();
  std::string feedback_type;
  double velocity_timeout_dbl;

  // Configure-only, default-off diagnostic input. Reuse an existing ROS service
  // payload; these fields are not dynamic writes to the node's parameters.
  rcl_interfaces::msg::ParameterDescriptor diagnostic_descriptor;
  diagnostic_descriptor.read_only = true;
  declare_parameter_if_not_declared(
    node, "mr3_diagnostic_enabled", rclcpp::ParameterValue(false), diagnostic_descriptor);
  declare_parameter_if_not_declared(
    node, "mr3_diagnostic_epoch", rclcpp::ParameterValue(std::string("")),
    diagnostic_descriptor);
  declare_parameter_if_not_declared(
    node, "mr3_diagnostic_arm", rclcpp::ParameterValue(std::string("")),
    diagnostic_descriptor);
  node->get_parameter("mr3_diagnostic_enabled", diagnostic_enabled_);
  node->get_parameter("mr3_diagnostic_epoch", diagnostic_epoch_);
  node->get_parameter("mr3_diagnostic_arm", diagnostic_arm_);
  diagnostic_active_ = false;
  diagnostic_sequence_ = 0;
  diagnostic_clock_ns_ = -1;
  if (diagnostic_enabled_) {
    const std::string ns = get_namespace();
    if (!get_parameter("use_sim_time").as_bool() ||
      (ns != "/tb1" && ns != "/tb2" && ns != "/tb3") ||
      diagnostic_epoch_.empty() || diagnostic_epoch_.size() > 200 ||
      diagnostic_epoch_.find_first_not_of(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-") != std::string::npos ||
      (diagnostic_arm_ != "continuous" && diagnostic_arm_ != "pulse"))
    {
      throw std::runtime_error("Invalid explicit three-robot simulated diagnostic configuration");
    }
    diagnostic_robot_ = ns.substr(1);
  }

  // Smoothing metadata
  declare_parameter_if_not_declared(node, "smoothing_frequency", rclcpp::ParameterValue(20.0));
  declare_parameter_if_not_declared(
    node, "feedback", rclcpp::ParameterValue(std::string("OPEN_LOOP")));
  declare_parameter_if_not_declared(node, "scale_velocities", rclcpp::ParameterValue(false));
  node->get_parameter("smoothing_frequency", smoothing_frequency_);
  node->get_parameter("feedback", feedback_type);
  node->get_parameter("scale_velocities", scale_velocities_);

  // Kinematics
  declare_parameter_if_not_declared(
    node, "max_velocity", rclcpp::ParameterValue(std::vector<double>{0.50, 0.0, 2.5}));
  declare_parameter_if_not_declared(
    node, "min_velocity", rclcpp::ParameterValue(std::vector<double>{-0.50, 0.0, -2.5}));
  declare_parameter_if_not_declared(
    node, "max_accel", rclcpp::ParameterValue(std::vector<double>{2.5, 0.0, 3.2}));
  declare_parameter_if_not_declared(
    node, "max_decel", rclcpp::ParameterValue(std::vector<double>{-2.5, 0.0, -3.2}));
  node->get_parameter("max_velocity", max_velocities_);
  node->get_parameter("min_velocity", min_velocities_);
  node->get_parameter("max_accel", max_accels_);
  node->get_parameter("max_decel", max_decels_);

  for (unsigned int i = 0; i != 3; i++) {
    if (max_decels_[i] > 0.0) {
      throw std::runtime_error(
              "Positive values set of deceleration! These should be negative to slow down!");
    }
    if (max_accels_[i] < 0.0) {
      throw std::runtime_error(
              "Negative values set of acceleration! These should be positive to speed up!");
    }
    if (min_velocities_[i] > max_velocities_[i]) {
      throw std::runtime_error(
              "Min velocities are higher than max velocities!");
    }
  }

  // Get feature parameters
  declare_parameter_if_not_declared(node, "odom_topic", rclcpp::ParameterValue("odom"));
  declare_parameter_if_not_declared(node, "odom_duration", rclcpp::ParameterValue(0.1));
  declare_parameter_if_not_declared(
    node, "deadband_velocity", rclcpp::ParameterValue(std::vector<double>{0.0, 0.0, 0.0}));
  declare_parameter_if_not_declared(node, "velocity_timeout", rclcpp::ParameterValue(1.0));
  node->get_parameter("odom_topic", odom_topic_);
  node->get_parameter("odom_duration", odom_duration_);
  node->get_parameter("deadband_velocity", deadband_velocities_);
  node->get_parameter("velocity_timeout", velocity_timeout_dbl);
  velocity_timeout_ = rclcpp::Duration::from_seconds(velocity_timeout_dbl);

  if (max_velocities_.size() != 3 || min_velocities_.size() != 3 ||
    max_accels_.size() != 3 || max_decels_.size() != 3 || deadband_velocities_.size() != 3)
  {
    throw std::runtime_error(
            "Invalid setting of kinematic and/or deadband limits!"
            " All limits must be size of 3 representing (x, y, theta).");
  }

  // Get control type
  if (feedback_type == "OPEN_LOOP") {
    open_loop_ = true;
  } else if (feedback_type == "CLOSED_LOOP") {
    open_loop_ = false;
    odom_smoother_ = std::make_unique<nav2_util::OdomSmoother>(node, odom_duration_, odom_topic_);
  } else {
    throw std::runtime_error("Invalid feedback_type, options are OPEN_LOOP and CLOSED_LOOP.");
  }

  // Setup inputs / outputs
  smoothed_cmd_pub_ = create_publisher<geometry_msgs::msg::Twist>("cmd_vel_smoothed", 1);
  if (diagnostic_enabled_ && std::string(smoothed_cmd_pub_->get_topic_name()) !=
    "/" + diagnostic_robot_ + "/cmd_vel_unguarded")
  {
    throw std::runtime_error("Diagnostic output must be the original unguarded request boundary");
  }
  cmd_sub_ = create_subscription<geometry_msgs::msg::Twist>(
    "cmd_vel", rclcpp::QoS(1),
    std::bind(&VelocitySmoother::inputCommandCallback, this, std::placeholders::_1));
  if (diagnostic_enabled_) {
    diagnostic_service_ = create_service<DiagnosticApply>(
      "~/mr3_diagnostic_apply",
      std::bind(&VelocitySmoother::applyDiagnostic, this,
      std::placeholders::_1, std::placeholders::_2));
  }

  return nav2_util::CallbackReturn::SUCCESS;
}

nav2_util::CallbackReturn
VelocitySmoother::on_activate(const rclcpp_lifecycle::State &)
{
  RCLCPP_INFO(get_logger(), "Activating");
  smoothed_cmd_pub_->on_activate();
  diagnostic_active_ = diagnostic_enabled_;
  if (!diagnostic_enabled_) {
    double timer_duration_ms = 1000.0 / smoothing_frequency_;
    timer_ = rclcpp::create_timer(
      get_node_base_interface(), get_node_timers_interface(), get_clock(),
      rclcpp::Duration(std::chrono::milliseconds(static_cast<int>(timer_duration_ms))),
      std::bind(&VelocitySmoother::smootherTimer, this));
  }

  dyn_params_handler_ = this->add_on_set_parameters_callback(
    std::bind(&VelocitySmoother::dynamicParametersCallback, this, _1));

  // create bond connection
  createBond();
  return nav2_util::CallbackReturn::SUCCESS;
}

nav2_util::CallbackReturn
VelocitySmoother::on_deactivate(const rclcpp_lifecycle::State &)
{
  RCLCPP_INFO(get_logger(), "Deactivating");
  diagnostic_active_ = false;
  if (timer_) {
    timer_->cancel();
    timer_.reset();
  }
  smoothed_cmd_pub_->on_deactivate();
  dyn_params_handler_.reset();

  // destroy bond connection
  destroyBond();
  return nav2_util::CallbackReturn::SUCCESS;
}

nav2_util::CallbackReturn
VelocitySmoother::on_cleanup(const rclcpp_lifecycle::State &)
{
  RCLCPP_INFO(get_logger(), "Cleaning up");
  diagnostic_active_ = false;
  smoothed_cmd_pub_.reset();
  odom_smoother_.reset();
  cmd_sub_.reset();
  diagnostic_service_.reset();
  return nav2_util::CallbackReturn::SUCCESS;
}

nav2_util::CallbackReturn
VelocitySmoother::on_shutdown(const rclcpp_lifecycle::State &)
{
  RCLCPP_INFO(get_logger(), "Shutting down");
  diagnostic_active_ = false;
  return nav2_util::CallbackReturn::SUCCESS;
}

void VelocitySmoother::inputCommandCallback(const geometry_msgs::msg::Twist::SharedPtr msg)
{
  if (diagnostic_enabled_) {
    return;
  }
  // If message contains NaN or Inf, ignore
  if (!nav2_util::validateTwist(*msg)) {
    RCLCPP_ERROR(get_logger(), "Velocity message contains NaNs or Infs! Ignoring as invalid!");
    return;
  }

  command_ = msg;
  last_command_time_ = now();
}

void VelocitySmoother::applyDiagnostic(
  const std::shared_ptr<DiagnosticApply::Request> request,
  std::shared_ptr<DiagnosticApply::Response> response)
{
  auto & result = response->result;
  result.successful = false;
  result.reason = "diagnostic mode is disabled or inactive";
  if (!diagnostic_enabled_ || !diagnostic_active_) {
    return;
  }
  // Default mutually-exclusive callback group serializes this service with
  // lifecycle callbacks. No timer exists in this mode, and normal input is ignored.
  std::map<std::string, rcl_interfaces::msg::ParameterValue> fields;
  for (const auto & parameter : request->parameters) {
    if (!fields.emplace(parameter.name, parameter.value).second) {
      result.reason = "duplicate diagnostic field";
      return;
    }
  }
  if (fields.size() != 5 || fields.count("epoch") != 1 || fields.count("arm") != 1 ||
    fields.count("sequence") != 1 || fields.count("clock_ns") != 1 ||
    fields.count("angular_millirad") != 1 ||
    fields.at("epoch").type != ParameterType::PARAMETER_STRING ||
    fields.at("arm").type != ParameterType::PARAMETER_STRING ||
    fields.at("sequence").type != ParameterType::PARAMETER_INTEGER ||
    fields.at("clock_ns").type != ParameterType::PARAMETER_INTEGER ||
    fields.at("angular_millirad").type != ParameterType::PARAMETER_INTEGER)
  {
    result.reason = "diagnostic fields/types differ from the fixed contract";
    return;
  }
  const auto sequence = fields.at("sequence").integer_value;
  const auto clock_ns = fields.at("clock_ns").integer_value;
  const auto angular = fields.at("angular_millirad").integer_value;
  if (fields.at("epoch").string_value != diagnostic_epoch_ ||
    fields.at("arm").string_value != diagnostic_arm_ ||
    diagnostic_sequence_ == std::numeric_limits<int64_t>::max() ||
    sequence != diagnostic_sequence_ + 1 || clock_ns <= 0 || clock_ns % 1000000 != 0 ||
    (diagnostic_clock_ns_ >= 0 &&
    (diagnostic_clock_ns_ > std::numeric_limits<int64_t>::max() - 20000000 ||
    clock_ns != diagnostic_clock_ns_ + 20000000)) ||
    (angular != 0 && angular != 800))
  {
    result.reason = "diagnostic epoch/arm/sequence/1ms clock/20ms phase/velocity rejected";
    return;
  }
  // Humble's independent clock thread may not yet have consumed the paused
  // boundary's /clock message when this service is taken. Wait only for that
  // local clock reader; this does not step physics or retry a publication.
  const auto clock_deadline = std::chrono::steady_clock::now() + 2s;
  auto observed_clock = now().nanoseconds();
  while (observed_clock < clock_ns) {
    if (std::chrono::steady_clock::now() >= clock_deadline) {
      result.reason = "diagnostic exact clock synchronization timed out";
      return;
    }
    std::this_thread::sleep_for(1ms);
    observed_clock = now().nanoseconds();
  }
  if (observed_clock != clock_ns) {
    result.reason = "diagnostic requested clock is already past";
    return;
  }
  geometry_msgs::msg::Twist command;
  command.angular.z = angular == 800 ? 0.8 : 0.0;
  const auto publication_clock = now().nanoseconds();
  if (publication_clock != clock_ns) {
    result.reason = "diagnostic clock changed before publication";
    return;
  }
  const auto wall_ns = []() {
      return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    };
  const auto started_wall = wall_ns();
  smoothed_cmd_pub_->publish(command);
  const auto completed_wall = wall_ns();
  diagnostic_sequence_ = sequence;
  diagnostic_clock_ns_ = clock_ns;
  // The source ACK proves this publication only. The fixture must independently
  // wait for the original guard's actual request/decision and native storage.
  std::ostringstream receipt;
  receipt << "{\"schema\":\"mr3-smoother-diagnostic-ack-v1\",\"epoch\":\""
          << diagnostic_epoch_ << "\",\"robot\":\"" << diagnostic_robot_
          << "\",\"arm\":\"" << diagnostic_arm_ << "\",\"sequence\":" << sequence
          << ",\"clock_ns\":" << clock_ns << ",\"angular_millirad\":" << angular
          << ",\"linear_x\":0.0,\"publication_clock_ns\":" << publication_clock
          << ",\"publication_started_wall_monotonic_ns\":" << started_wall
          << ",\"publication_completed_wall_monotonic_ns\":" << completed_wall
          << ",\"output_topic\":\"" << smoothed_cmd_pub_->get_topic_name()
          << "\",\"completion_scope\":\"smoother_publication_only_not_guard_or_storage\"}";
  result.reason = receipt.str();
  result.successful = true;
}

double VelocitySmoother::findEtaConstraint(
  const double v_curr, const double v_cmd, const double accel, const double decel)
{
  // Exploiting vector scaling properties
  double dv = v_cmd - v_curr;

  double v_component_max;
  double v_component_min;

  // Accelerating if magnitude of v_cmd is above magnitude of v_curr
  // and if v_cmd and v_curr have the same sign (i.e. speed is NOT passing through 0.0)
  // Decelerating otherwise
  if (abs(v_cmd) >= abs(v_curr) && v_curr * v_cmd >= 0.0) {
    v_component_max = accel / smoothing_frequency_;
    v_component_min = -accel / smoothing_frequency_;
  } else {
    v_component_max = -decel / smoothing_frequency_;
    v_component_min = decel / smoothing_frequency_;
  }

  if (dv > v_component_max) {
    return v_component_max / dv;
  }

  if (dv < v_component_min) {
    return v_component_min / dv;
  }

  return -1.0;
}

double VelocitySmoother::applyConstraints(
  const double v_curr, const double v_cmd,
  const double accel, const double decel, const double eta)
{
  double dv = v_cmd - v_curr;

  double v_component_max;
  double v_component_min;

  // Accelerating if magnitude of v_cmd is above magnitude of v_curr
  // and if v_cmd and v_curr have the same sign (i.e. speed is NOT passing through 0.0)
  // Decelerating otherwise
  if (abs(v_cmd) >= abs(v_curr) && v_curr * v_cmd >= 0.0) {
    v_component_max = accel / smoothing_frequency_;
    v_component_min = -accel / smoothing_frequency_;
  } else {
    v_component_max = -decel / smoothing_frequency_;
    v_component_min = decel / smoothing_frequency_;
  }

  return v_curr + std::clamp(eta * dv, v_component_min, v_component_max);
}

void VelocitySmoother::smootherTimer()
{
  if (diagnostic_enabled_) {
    return;
  }
  // Wait until the first command is received
  if (!command_) {
    return;
  }

  auto cmd_vel = std::make_unique<geometry_msgs::msg::Twist>();

  // Check for velocity timeout. If nothing received, publish zeros to apply deceleration
  if (now() - last_command_time_ > velocity_timeout_) {
    if (last_cmd_ == geometry_msgs::msg::Twist() || stopped_) {
      stopped_ = true;
      return;
    }
    *command_ = geometry_msgs::msg::Twist();
  }

  stopped_ = false;

  // Get current velocity based on feedback type
  geometry_msgs::msg::Twist current_;
  if (open_loop_) {
    current_ = last_cmd_;
  } else {
    current_ = odom_smoother_->getTwist();
  }

  // Apply absolute velocity restrictions to the command
  command_->linear.x = std::clamp(command_->linear.x, min_velocities_[0], max_velocities_[0]);
  command_->linear.y = std::clamp(command_->linear.y, min_velocities_[1], max_velocities_[1]);
  command_->angular.z = std::clamp(command_->angular.z, min_velocities_[2], max_velocities_[2]);

  // Find if any component is not within the acceleration constraints. If so, store the most
  // significant scale factor to apply to the vector <dvx, dvy, dvw>, eta, to reduce all axes
  // proportionally to follow the same direction, within change of velocity bounds.
  // In case eta reduces another axis out of its own limit, apply accel constraint to guarantee
  // output is within limits, even if it deviates from requested command slightly.
  double eta = 1.0;
  if (scale_velocities_) {
    double curr_eta = -1.0;

    curr_eta = findEtaConstraint(
      current_.linear.x, command_->linear.x, max_accels_[0], max_decels_[0]);
    if (curr_eta > 0.0 && std::fabs(1.0 - curr_eta) > std::fabs(1.0 - eta)) {
      eta = curr_eta;
    }

    curr_eta = findEtaConstraint(
      current_.linear.y, command_->linear.y, max_accels_[1], max_decels_[1]);
    if (curr_eta > 0.0 && std::fabs(1.0 - curr_eta) > std::fabs(1.0 - eta)) {
      eta = curr_eta;
    }

    curr_eta = findEtaConstraint(
      current_.angular.z, command_->angular.z, max_accels_[2], max_decels_[2]);
    if (curr_eta > 0.0 && std::fabs(1.0 - curr_eta) > std::fabs(1.0 - eta)) {
      eta = curr_eta;
    }
  }

  cmd_vel->linear.x = applyConstraints(
    current_.linear.x, command_->linear.x, max_accels_[0], max_decels_[0], eta);
  cmd_vel->linear.y = applyConstraints(
    current_.linear.y, command_->linear.y, max_accels_[1], max_decels_[1], eta);
  cmd_vel->angular.z = applyConstraints(
    current_.angular.z, command_->angular.z, max_accels_[2], max_decels_[2], eta);
  last_cmd_ = *cmd_vel;

  // Apply deadband restrictions & publish
  cmd_vel->linear.x = fabs(cmd_vel->linear.x) < deadband_velocities_[0] ? 0.0 : cmd_vel->linear.x;
  cmd_vel->linear.y = fabs(cmd_vel->linear.y) < deadband_velocities_[1] ? 0.0 : cmd_vel->linear.y;
  cmd_vel->angular.z = fabs(cmd_vel->angular.z) <
    deadband_velocities_[2] ? 0.0 : cmd_vel->angular.z;

  smoothed_cmd_pub_->publish(std::move(cmd_vel));
}

rcl_interfaces::msg::SetParametersResult
VelocitySmoother::dynamicParametersCallback(std::vector<rclcpp::Parameter> parameters)
{
  rcl_interfaces::msg::SetParametersResult result;
  result.successful = true;
  if (diagnostic_enabled_) {
    result.successful = false;
    result.reason = "diagnostic configuration is fixed until cleanup/reconfigure";
    return result;
  }

  for (auto parameter : parameters) {
    const auto & type = parameter.get_type();
    const auto & name = parameter.get_name();

    if (type == ParameterType::PARAMETER_DOUBLE) {
      if (name == "smoothing_frequency") {
        smoothing_frequency_ = parameter.as_double();
        if (timer_) {
          timer_->cancel();
          timer_.reset();
        }

        double timer_duration_ms = 1000.0 / smoothing_frequency_;
        timer_ = rclcpp::create_timer(
          get_node_base_interface(), get_node_timers_interface(), get_clock(),
          rclcpp::Duration(std::chrono::milliseconds(static_cast<int>(timer_duration_ms))),
          std::bind(&VelocitySmoother::smootherTimer, this));
      } else if (name == "velocity_timeout") {
        velocity_timeout_ = rclcpp::Duration::from_seconds(parameter.as_double());
      } else if (name == "odom_duration") {
        odom_duration_ = parameter.as_double();
        odom_smoother_ =
          std::make_unique<nav2_util::OdomSmoother>(
          shared_from_this(), odom_duration_, odom_topic_);
      }
    } else if (type == ParameterType::PARAMETER_DOUBLE_ARRAY) {
      if (parameter.as_double_array().size() != 3) {
        RCLCPP_WARN(get_logger(), "Invalid size of parameter %s. Must be size 3", name.c_str());
        result.successful = false;
        break;
      }

      if (name == "max_velocity") {
        max_velocities_ = parameter.as_double_array();
      } else if (name == "min_velocity") {
        min_velocities_ = parameter.as_double_array();
      } else if (name == "max_accel") {
        for (unsigned int i = 0; i != 3; i++) {
          if (parameter.as_double_array()[i] < 0.0) {
            RCLCPP_WARN(
              get_logger(),
              "Negative values set of acceleration! These should be positive to speed up!");
            result.successful = false;
          }
        }
        max_accels_ = parameter.as_double_array();
      } else if (name == "max_decel") {
        for (unsigned int i = 0; i != 3; i++) {
          if (parameter.as_double_array()[i] > 0.0) {
            RCLCPP_WARN(
              get_logger(),
              "Positive values set of deceleration! These should be negative to slow down!");
            result.successful = false;
          }
        }
        max_decels_ = parameter.as_double_array();
      } else if (name == "deadband_velocity") {
        deadband_velocities_ = parameter.as_double_array();
      }
    } else if (type == ParameterType::PARAMETER_STRING) {
      if (name == "feedback") {
        if (parameter.as_string() == "OPEN_LOOP") {
          open_loop_ = true;
          odom_smoother_.reset();
        } else if (parameter.as_string() == "CLOSED_LOOP") {
          open_loop_ = false;
          odom_smoother_ =
            std::make_unique<nav2_util::OdomSmoother>(
            shared_from_this(), odom_duration_, odom_topic_);
        } else {
          RCLCPP_WARN(
            get_logger(), "Invalid feedback_type, options are OPEN_LOOP and CLOSED_LOOP.");
          result.successful = false;
          break;
        }
      } else if (name == "odom_topic") {
        odom_topic_ = parameter.as_string();
        odom_smoother_ =
          std::make_unique<nav2_util::OdomSmoother>(
          shared_from_this(), odom_duration_, odom_topic_);
      }
    }
  }

  return result;
}

}  // namespace nav2_velocity_smoother

#include "rclcpp_components/register_node_macro.hpp"
RCLCPP_COMPONENTS_REGISTER_NODE(nav2_velocity_smoother::VelocitySmoother)
