// Passive local delivery evidence. This node never publishes commands or state.
#include <nav_msgs/msg/odometry.hpp>
#include <nlohmann/json.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rmw/types.h>
#include <std_msgs/msg/bool.hpp>
#include <tf2_msgs/msg/tf_message.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "multi_robot/mr3_odometry_json.hpp"

namespace
{
using Json = nlohmann::json;

template<typename Bytes>
std::string hex(const Bytes & bytes)
{
  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (const auto value : bytes) {
    output << std::setw(2) << static_cast<unsigned int>(value);
  }
  return output.str();
}

int64_t wall_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}

class OdometryRecorder : public rclcpp::Node
{
public:
  OdometryRecorder()
  : Node("mr3_odometry_recorder")
  {
    epoch_ = declare_parameter<std::string>("episode_epoch", "");
    const auto output = declare_parameter<std::string>("output_path", "");
    if (epoch_.empty() || output.empty() || !std::filesystem::path(output).is_absolute()) {
      throw std::invalid_argument("passive odometry recorder requires epoch and absolute output_path");
    }
    file_.reset(std::fopen(output.c_str(), "wx"));
    if (!file_) {
      throw std::runtime_error("cannot exclusively create passive odometry receipt file: " + output);
    }
    ready_ = create_publisher<std_msgs::msg::Bool>(
      "/mr3/odometry_recorder/ready", rclcpp::QoS(1).reliable().transient_local());
    ready_->publish(std_msgs::msg::Bool());
    write("configuration", "", {
      {"compiled_source_sha256", MR3_ODOMETRY_RECORDER_SOURCE_SHA256},
      {"compiled_odometry_json_sha256", MR3_ODOMETRY_JSON_HEADER_SHA256},
      {"output_path", output}, {"use_sim_time", get_parameter("use_sim_time").as_bool()},
      {"robots", {"tb1", "tb2", "tb3"}}, {"reliable_queue_depth", 1000},
      {"scope", "passive packet reception only; not actor input or navigation consumption"}});
    const auto qos = rclcpp::QoS(1000).reliable();
    for (size_t index = 0; index < robots_.size(); ++index) {
      const auto robot = robots_[index];
      odometry_.push_back(create_subscription<nav_msgs::msg::Odometry>(
        "/" + robot + "/odom", qos,
        [this, robot, index](nav_msgs::msg::Odometry::ConstSharedPtr message,
          const rclcpp::MessageInfo & info)
        {
          const auto clock = now().nanoseconds();
          const auto wall = wall_ns();
          receive("odom", robot, index, "/" + robot + "/odom", "nav_msgs/msg/Odometry",
            multi_robot::odometry_json::odometry(*message), info,
            {{"clock_ns", clock}, {"wall_monotonic_ns", wall}});
        }));
      transforms_.push_back(create_subscription<tf2_msgs::msg::TFMessage>(
        "/" + robot + "/tf", qos,
        [this, robot, index](tf2_msgs::msg::TFMessage::ConstSharedPtr message,
          const rclcpp::MessageInfo & info)
        {
          const auto clock = now().nanoseconds();
          const auto wall = wall_ns();
          for (size_t transform = 0; transform < message->transforms.size(); ++transform) {
            const auto & value = message->transforms[transform];
            if (value.header.frame_id != "odom" || value.child_frame_id != "base_footprint") {
              continue;
            }
            receive("tf", robot, index, "/" + robot + "/tf", "tf2_msgs/msg/TFMessage",
              multi_robot::odometry_json::transform(value), info,
              {{"clock_ns", clock}, {"wall_monotonic_ns", wall},
               {"transform_index", transform},
               {"tf_message", multi_robot::odometry_json::tf_message(*message)}});
          }
        }));
    }
  }

private:
  void write(const char * kind, const std::string & robot, Json fields)
  {
    fields.update({{"schema", "mr3-driver-odometry-receipt-v1"}, {"kind", kind},
      {"epoch", epoch_}, {"robot", robot}, {"record_sequence", ++sequence_}});
    if (!fields.contains("clock_ns")) {
      fields["clock_ns"] = now().nanoseconds();
    }
    if (!fields.contains("wall_monotonic_ns")) {
      fields["wall_monotonic_ns"] = wall_ns();
    }
    const auto line = fields.dump() + "\n";
    if (std::fwrite(line.data(), 1, line.size(), file_.get()) != line.size() ||
      std::fflush(file_.get()) != 0)
    {
      throw std::runtime_error("cannot persist actual passive odometry receipt");
    }
  }

  void receive(const std::string & kind, const std::string & robot, size_t robot_index,
    const std::string & topic, const std::string & type, Json message,
    const rclcpp::MessageInfo & info, Json extra)
  {
    const auto & actual = info.get_rmw_message_info();
    std::array<uint8_t, RMW_GID_STORAGE_SIZE> packet_gid;
    std::copy(std::begin(actual.publisher_gid.data), std::end(actual.publisher_gid.data),
      packet_gid.begin());
    const auto gid = hex(packet_gid);
    auto endpoints = Json::array();
    size_t matching_driver = 0;
    const auto entries = get_publishers_info_by_topic(topic);
    for (const auto & entry : entries) {
      const auto endpoint_gid = hex(entry.endpoint_gid());
      endpoints.push_back({{"namespace", entry.node_namespace()}, {"node", entry.node_name()},
          {"topic_type", entry.topic_type()}, {"endpoint_gid", endpoint_gid}});
      if (endpoint_gid == gid && entry.node_namespace() == "/" + robot &&
        entry.node_name() == "turtlebot3_diff_drive" && entry.topic_type() == type)
      {
        ++matching_driver;
      }
    }
    const bool nonzero_gid = std::any_of(packet_gid.begin(), packet_gid.end(),
      [](uint8_t value) {return value != 0;});
    const bool driver_match = nonzero_gid && matching_driver == 1 &&
      (kind == "tf" || entries.size() == 1);
    const auto stream = robot_index * 2 + (kind == "tf" ? 1 : 0);
    const bool stable_gid = observed_gids_[stream].empty() || observed_gids_[stream] == gid;
    extra.update({{"topic", topic}, {"message", message}, {"publisher_gid", gid},
      {"source_timestamp", actual.source_timestamp}, {"received_timestamp", actual.received_timestamp},
      {"publication_sequence_number", actual.publication_sequence_number},
      {"reception_sequence_number", actual.reception_sequence_number},
      {"publication_sequence_number_supported",
        actual.publication_sequence_number != RMW_MESSAGE_INFO_SEQUENCE_NUMBER_UNSUPPORTED},
      {"reception_sequence_number_supported",
        actual.reception_sequence_number != RMW_MESSAGE_INFO_SEQUENCE_NUMBER_UNSUPPORTED},
      {"from_intra_process", actual.from_intra_process},
      {"publisher_graph", {{"topic", topic}, {"endpoints", endpoints},
                            {"scope", "graph_at_callback; actual packet GID independently recorded"}}},
      {"driver_identity_match", driver_match}, {"driver_gid_stable", stable_gid},
      {"scope", "actual passive ROS packet receipt; not navigation consumption"}});
    write(kind.c_str(), robot, extra);
    if (driver_match && stable_gid) {
      observed_gids_[stream] = gid;
      observed_[stream] = true;
    } else if (ready_sent_) {
      failed_after_ready_ = true;
      ready_->publish(std_msgs::msg::Bool());
    }
    if (!ready_sent_ && !failed_after_ready_ &&
      std::all_of(observed_.begin(), observed_.end(), [](bool value) {return value;}))
    {
      std_msgs::msg::Bool ready;
      ready.data = true;
      ready_->publish(ready);
      ready_sent_ = true;
      write("ready", "", {{"publisher_gids", observed_gids_},
          {"scope", "all three real driver odometry and odom-to-base TF streams observed"}});
    }
  }

  const std::array<std::string, 3> robots_{"tb1", "tb2", "tb3"};
  std::array<bool, 6> observed_{};
  std::array<std::string, 6> observed_gids_;
  bool ready_sent_{false};
  bool failed_after_ready_{false};
  std::string epoch_;
  uint64_t sequence_{0};
  std::unique_ptr<std::FILE, decltype(&std::fclose)> file_{nullptr, &std::fclose};
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr ready_;
  std::vector<rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr> odometry_;
  std::vector<rclcpp::Subscription<tf2_msgs::msg::TFMessage>::SharedPtr> transforms_;
};
}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  int result = 0;
  try {
    rclcpp::spin(std::make_shared<OdometryRecorder>());
  } catch (const std::exception & error) {
    std::fprintf(stderr, "MR3 passive odometry recorder failed: %s\n", error.what());
    result = 1;
  }
  rclcpp::shutdown();
  return result;
}
