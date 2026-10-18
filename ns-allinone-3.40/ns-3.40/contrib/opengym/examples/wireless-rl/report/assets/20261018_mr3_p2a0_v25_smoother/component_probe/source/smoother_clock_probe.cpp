// Finite synthetic ROS component probe. No Gazebo, robot, goal, map or policy.
// Uses the unmodified public/protected header of Nav2 1.1.20 only for read access.
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

#include <nlohmann/json.hpp>
#include "geometry_msgs/msg/twist.hpp"
#include "lifecycle_msgs/msg/state.hpp"
#include "nav2_velocity_smoother/velocity_smoother.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rosgraph_msgs/msg/clock.hpp"

using Json = nlohmann::json;
using Steady = std::chrono::steady_clock;
using namespace std::chrono_literals;

class ReadableSmoother : public nav2_velocity_smoother::VelocitySmoother
{
public:
  explicit ReadableSmoother(const rclcpp::NodeOptions & options)
  : VelocitySmoother(options) {}

  bool TimerIsSteady() {return timer_ && timer_->is_steady();}
  bool InputMatches(double v, double w) const
  {
    return command_ && command_->linear.x == v && command_->angular.z == w;
  }
};

std::string ReadFile(const std::string & path)
{
  std::ifstream input(path);
  if (!input) {throw std::runtime_error("cannot read " + path);}
  return std::string(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
}

void ExclusiveJson(const std::string & path, const Json & value)
{
  const std::string bytes = value.dump(2) + "\n";
  const int fd = ::open(path.c_str(), O_CREAT | O_EXCL | O_WRONLY, 0644);
  if (fd < 0) {throw std::runtime_error("exclusive output open failed");}
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto count = ::write(fd, bytes.data() + offset, bytes.size() - offset);
    if (count <= 0) {::close(fd); throw std::runtime_error("output write failed");}
    offset += static_cast<std::size_t>(count);
  }
  if (::fsync(fd) != 0) {::close(fd); throw std::runtime_error("output fsync failed");}
  if (::close(fd) != 0) {throw std::runtime_error("output close failed");}
}

int main(int argc, char ** argv)
{
  const auto started = Steady::now();
  const auto work_deadline = started + 10s;  // Reserve normal teardown inside 15 s.
  std::string mode, output;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string key = argv[i];
    if (key == "--mode") {mode = argv[i + 1];}
    else if (key == "--output") {output = argv[i + 1];}
    else {std::cerr << "unknown argument\n"; return 2;}
  }
  if ((mode != "stock" && mode != "fixed") || output.empty() || argc != 5) {
    std::cerr << "required: --mode stock|fixed --output ABSENT_ABSOLUTE_JSON\n";
    return 2;
  }
  Json result = {{"schema", "mr3-v25-real-smoother-clock-probe-v1"},
    {"mode", mode}, {"passed", false}, {"normal_cleanup", false},
    {"process_id", ::getpid()}, {"samples", Json::array()}, {"events", Json::array()},
    {"scope", "Synthetic real ROS component timer probe only; no Gazebo/task/body-bound/matrix credit."}};
  std::shared_ptr<ReadableSmoother> smoother;
  rclcpp::Node::SharedPtr driver;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor;
  bool initialized = false;
  bool added = false;
  std::string phase = "initialization";
  const auto elapsed_ns = [&]() {
      return std::chrono::duration_cast<std::chrono::nanoseconds>(Steady::now() - started).count();
    };
  const auto require = [](bool condition, const std::string & reason) {
      if (!condition) {throw std::runtime_error(reason);}
    };
  try {
    // The library is already a linked dependency; NOLOAD must not load another copy.
    void * handle = ::dlopen("libvelocity_smoother_core.so", RTLD_NOW | RTLD_NOLOAD);
    require(handle != nullptr, "linked smoother library is not loaded");
    void * symbol = ::dlsym(handle,
      "_ZN22nav2_velocity_smoother16VelocitySmoother16applyConstraintsEddddd");
    Dl_info info{};
    require(symbol != nullptr && ::dladdr(symbol, &info) != 0 && info.dli_fname,
      "actual smoother library symbol/dladdr unavailable");
    result["loaded_library_path"] = info.dli_fname;
    result["library_symbol"] = "VelocitySmoother::applyConstraints(double,double,double,double,double)";
    result["process_maps_at_start"] = ReadFile("/proc/self/maps");
    result["process_stat_at_start"] = ReadFile("/proc/self/stat");
    rclcpp::init(argc, argv);
    initialized = true;
    executor = std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
    rclcpp::NodeOptions options;
    options.arguments({"--ros-args", "-r", "__ns:=/mr3_v25_smoother_probe"});
    options.enable_rosout(false).start_parameter_services(false)
    .start_parameter_event_publisher(false).use_intra_process_comms(false);
    options.parameter_overrides({rclcpp::Parameter("use_sim_time", true),
      rclcpp::Parameter("feedback", std::string("OPEN_LOOP")), rclcpp::Parameter("smoothing_frequency", 20.),
      rclcpp::Parameter("max_velocity", std::vector<double>{.20, 0., .8}),
      rclcpp::Parameter("min_velocity", std::vector<double>{-.20, 0., -.8}),
      rclcpp::Parameter("max_accel", std::vector<double>{.5, 0., 3.2}),
      rclcpp::Parameter("max_decel", std::vector<double>{-.5, 0., -3.2})});
    smoother = std::make_shared<ReadableSmoother>(options);
    rclcpp::NodeOptions driver_options;
    driver_options.enable_rosout(false).start_parameter_services(false)
    .start_parameter_event_publisher(false).use_intra_process_comms(false);
    driver = std::make_shared<rclcpp::Node>("mr3_smoother_probe_driver", driver_options);
    auto clock_pub = driver->create_publisher<rosgraph_msgs::msg::Clock>(
      "/clock", rclcpp::ClockQoS().reliable());
    auto command_pub = driver->create_publisher<geometry_msgs::msg::Twist>(
      "/mr3_v25_smoother_probe/cmd_vel", rclcpp::QoS(10).reliable());
    auto output_sub = driver->create_subscription<geometry_msgs::msg::Twist>(
      "/mr3_v25_smoother_probe/cmd_vel_smoothed", rclcpp::QoS(100).reliable(),
      [&](geometry_msgs::msg::Twist::ConstSharedPtr message, const rclcpp::MessageInfo & metadata) {
        require(std::isfinite(message->linear.x) && std::isfinite(message->angular.z),
          "nonfinite actual output");
        require(std::abs(message->linear.x) <= .20 && std::abs(message->angular.z) <= .8,
          "actual command cap exceeded");
        std::ostringstream gid;
        gid << std::hex << std::setfill('0');
        for (const auto byte : metadata.get_rmw_message_info().publisher_gid.data) {
          gid << std::setw(2) << static_cast<unsigned int>(byte);
        }
        result["samples"].push_back({{"phase", phase}, {"wall_elapsed_ns", elapsed_ns()},
          {"component_clock_ns", smoother->now().nanoseconds()},
          {"linear_x", message->linear.x}, {"angular_z", message->angular.z},
          {"publisher_gid", gid.str()}});
      });
    executor->add_node(smoother->get_node_base_interface());
    executor->add_node(driver);
    added = true;
    const auto spin_once = [&]() {
        require(Steady::now() < work_deadline, "cooperative 10-second work guard expired");
        executor->spin_some(5ms);
        std::this_thread::sleep_for(1ms);
      };
    const auto wait = [&](const std::function<bool()> & predicate) {
        while (!predicate()) {spin_once();}
      };
    const auto spin_for = [&](Steady::duration duration) {
        const auto until = Steady::now() + duration;
        while (Steady::now() < until) {spin_once();}
      };
    require(smoother->configure().id() == lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE,
      "configure did not reach inactive");
    require(smoother->activate().id() == lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE,
      "activate did not reach active");
    result["actual_configured_parameters"] = {
      {"use_sim_time", smoother->get_parameter("use_sim_time").as_bool()},
      {"feedback", smoother->get_parameter("feedback").as_string()},
      {"smoothing_frequency", smoother->get_parameter("smoothing_frequency").as_double()},
      {"max_velocity", smoother->get_parameter("max_velocity").as_double_array()},
      {"min_velocity", smoother->get_parameter("min_velocity").as_double_array()},
      {"max_accel", smoother->get_parameter("max_accel").as_double_array()},
      {"max_decel", smoother->get_parameter("max_decel").as_double_array()}};
    result["clock_type"] = static_cast<int>(smoother->get_clock()->get_clock_type());
    result["timer_is_steady_after_activate"] = smoother->TimerIsSteady();
    require(smoother->TimerIsSteady() == (mode == "stock"), "unexpected actual timer clock type");
    wait([&]() {return clock_pub->get_subscription_count() >= 1 &&
      command_pub->get_subscription_count() == 1 && output_sub->get_publisher_count() == 1;});
    std::int64_t clock_ns = 1'000'000'000;
    const auto publish_clock = [&]() {
        rosgraph_msgs::msg::Clock message;
        message.clock.sec = static_cast<std::int32_t>(clock_ns / 1'000'000'000);
        message.clock.nanosec = static_cast<std::uint32_t>(clock_ns % 1'000'000'000);
        clock_pub->publish(message);
        result["events"].push_back({{"kind", "clock_published"},
          {"clock_ns", clock_ns}, {"wall_elapsed_ns", elapsed_ns()}});
        wait([&]() {return smoother->now().nanoseconds() == clock_ns;});
      };
    const auto publish_command = [&](double v, double w) {
        geometry_msgs::msg::Twist message;
        message.linear.x = v;
        message.angular.z = w;
        command_pub->publish(message);
        result["events"].push_back({{"kind", "command_published"},
          {"linear_x", v}, {"angular_z", w}, {"component_clock_ns", clock_ns},
          {"wall_elapsed_ns", elapsed_ns()}});
        wait([&]() {return smoother->InputMatches(v, w);});
      };
    publish_clock();
    // Drain the initial forward clock jump while no command exists.
    spin_for(120ms);
    phase = "paused_20hz";
    publish_command(.20, -.8);
    auto count = result["samples"].size();
    spin_for(350ms);
    const auto paused20 = result["samples"].size() - count;
    result["paused_20hz_output_count"] = paused20;
    require(mode == "stock" ? paused20 >= 3 : paused20 == 0,
      "paused 20Hz output behavior does not match expected stock/fixed clock");
    phase = "advance_20hz";
    for (int i = 0; i < 9; ++i) {
      count = result["samples"].size();
      clock_ns += 50'000'000;
      publish_clock();
      wait([&]() {return result["samples"].size() > count;});
    }
    const auto changed = smoother->set_parameters({rclcpp::Parameter("smoothing_frequency", 10.)});
    require(changed.size() == 1 && changed.front().successful, "frequency reconfiguration rejected");
    result["timer_is_steady_after_frequency_change"] = smoother->TimerIsSteady();
    require(smoother->TimerIsSteady() == (mode == "stock"), "recreated timer uses wrong clock");
    phase = "paused_10hz";
    publish_command(0., 0.);
    count = result["samples"].size();
    spin_for(350ms);
    const auto paused10 = result["samples"].size() - count;
    result["paused_10hz_output_count"] = paused10;
    require(mode == "stock" ? paused10 >= 2 : paused10 == 0,
      "paused recreated timer behavior does not match expected stock/fixed clock");
    phase = "advance_10hz";
    for (int i = 0; i < 5; ++i) {
      count = result["samples"].size();
      clock_ns += 100'000'000;
      publish_clock();
      wait([&]() {return result["samples"].size() > count;});
    }
    result["mechanism_observed"] = mode == "stock" ?
      "wall callbacks advance OPEN_LOOP output while ROS time is paused" :
      "both timers follow the node ROS clock; paused ROS time does not advance output";
    result["passed"] = true;
  } catch (const std::exception & error) {
    result["error"] = error.what();
  }
  try {
    if (smoother) {
      if (smoother->get_current_state().id() == lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
        if (smoother->deactivate().id() != lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE) {
          throw std::runtime_error("deactivate failed");
        }
      }
      if (smoother->get_current_state().id() == lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE) {
        if (smoother->cleanup().id() != lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED) {
          throw std::runtime_error("cleanup failed");
        }
      }
      result["final_lifecycle_state"] = smoother->get_current_state().id();
      if (added) {
        executor->remove_node(smoother->get_node_base_interface());
        executor->remove_node(driver);
      }
    }
    smoother.reset();
    driver.reset();
    executor.reset();
    if (initialized) {rclcpp::shutdown();}
    result["normal_cleanup"] = true;
  } catch (const std::exception & error) {
    result["cleanup_error"] = error.what();
    result["passed"] = false;
    if (initialized && rclcpp::ok()) {rclcpp::shutdown();}
  }
  result["wall_seconds"] = std::chrono::duration<double>(Steady::now() - started).count();
  if (result["wall_seconds"].get<double>() > 15.) {
    result["passed"] = false;
    result["wall_ceiling_exceeded"] = true;
  }
  result["process_maps_at_end"] = ReadFile("/proc/self/maps");
  result["process_stat_at_end"] = ReadFile("/proc/self/stat");
  try {ExclusiveJson(output, result);} catch (const std::exception & error) {
    std::cerr << error.what() << '\n'; return 1;
  }
  return result["passed"].get<bool>() ? 0 : 1;
}
