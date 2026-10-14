// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: MIT

#include <array>
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "multi_robot/contact_reducer.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rmw/features.h"
#include "std_msgs/msg/string.hpp"

namespace multi_robot
{

class ContactReducer : public rclcpp::Node
{
public:
  ContactReducer()
  : Node("mr3_contact_reducer")
  {
    const auto names = declare_parameter<std::vector<std::string>>(
      "robot_names", std::vector<std::string>{"tb1", "tb2", "tb3"});
    if (names.size() != 3 || std::set<std::string>(names.begin(), names.end()) !=
      std::set<std::string>{"tb1", "tb2", "tb3"})
    {
      throw std::invalid_argument("MR3 contact monitoring requires exactly tb1/tb2/tb3");
    }
    sequence_supported_ = rmw_feature_supported(
      RMW_FEATURE_MESSAGE_INFO_PUBLICATION_SEQUENCE_NUMBER);
    RCLCPP_INFO(
      get_logger(), "Publication sequence auditing supported: %s",
      sequence_supported_ ? "true" : "false");
    const auto qos = rclcpp::QoS(rclcpp::KeepLast(100)).reliable();
    failure_publisher_ = create_publisher<std_msgs::msg::String>(
      "/exploration_failure", rclcpp::QoS(1).reliable().transient_local());
    for (const auto & robot : names) {
      for (const auto & component : components_) {
        const auto key = robot + "/" + component;
        const auto input = "/" + robot + "/collision" +
          (component == "base" ? "" : "/" + component);
        const auto output = "/mr3_contacts/" + key;
        auto publisher = create_publisher<gazebo_msgs::msg::ContactsState>(output, qos);
        publishers_.push_back(publisher);
        stats_.emplace(key, Statistics{});
        subscriptions_.push_back(
          create_subscription<gazebo_msgs::msg::ContactsState>(
            input, qos,
            [this, key, publisher](
              gazebo_msgs::msg::ContactsState::ConstSharedPtr message,
              const rclcpp::MessageInfo & info)
            {
              auto & stats = stats_.at(key);
              ++stats.received;
              stats.raw_states += message->states.size();
              const auto & metadata = info.get_rmw_message_info();
              const auto sequence = metadata.publication_sequence_number;
              if (sequence_supported_ && sequence != RMW_MESSAGE_INFO_SEQUENCE_NUMBER_UNSUPPORTED) {
                ++stats.sequence_observed;
                std::array<uint8_t, RMW_GID_STORAGE_SIZE> gid;
                std::copy_n(metadata.publisher_gid.data, gid.size(), gid.begin());
                auto previous = stats.last_sequences.find(gid);
                if (previous != stats.last_sequences.end()) {
                  if (sequence > previous->second + 1) {
                    const auto missing = sequence - previous->second - 1;
                    stats.sequence_gaps += missing;
                    RCLCPP_ERROR(
                      get_logger(), "%s: raw publication sequence gap, %s messages missing",
                      key.c_str(), std::to_string(missing).c_str());
                    publish_failure(key, "contact_transport_sequence_gap", missing);
                  } else if (sequence == previous->second) {
                    ++stats.sequence_duplicates;
                    publish_failure(key, "contact_transport_sequence_duplicate");
                  } else if (sequence < previous->second) {
                    ++stats.sequence_regressions;
                    RCLCPP_ERROR(
                      get_logger(), "%s: raw publication sequence regressed",
                      key.c_str());
                    publish_failure(key, "contact_transport_sequence_regression");
                  }
                }
                stats.last_sequences[gid] = sequence;
              } else {
                ++stats.sequence_unavailable;
              }
              auto compact = reduce_contacts(*message);
              stats.compact_states += compact.states.size();
              publisher->publish(compact);
              ++stats.published;
            }));
        RCLCPP_INFO(get_logger(), "%s -> %s", input.c_str(), output.c_str());
      }
    }
  }

  ~ContactReducer() override
  {
    // This summary also survives ROS context shutdown; it is diagnostic data,
    // never a source-freshness heartbeat or a replacement contact message.
    std::cout << "MR3_CONTACT_REDUCER_SUMMARY {\"publication_sequence_supported\":" <<
      (sequence_supported_ ? "true" : "false") << ",\"topics\":{";
    bool first = true;
    for (const auto & entry : stats_) {
      if (!first) {
        std::cout << ',';
      }
      first = false;
      const auto & stats = entry.second;
      std::cout << '"' << entry.first << "\":{\"received\":" << stats.received <<
        ",\"published\":" << stats.published << ",\"raw_states\":" << stats.raw_states <<
        ",\"compact_states\":" << stats.compact_states <<
        ",\"sequence_observed\":" << stats.sequence_observed <<
        ",\"sequence_unavailable\":" << stats.sequence_unavailable <<
        ",\"publisher_count\":" << stats.last_sequences.size() <<
        ",\"sequence_gaps\":" << stats.sequence_gaps <<
        ",\"sequence_duplicates\":" << stats.sequence_duplicates <<
        ",\"sequence_regressions\":" << stats.sequence_regressions << '}';
    }
    std::cout << "}}" << std::endl;
  }

private:
  void publish_failure(const std::string & key, const std::string & reason, uint64_t missing = 0)
  {
    std_msgs::msg::String failure;
    failure.data = "{\"component\":\"mr3_contact_reducer\",\"robot_component\":\"" + key +
      "\",\"reason\":\"" + reason + "\",\"missing_messages\":" +
      std::to_string(missing) + "}";
    failure_publisher_->publish(failure);
    RCLCPP_ERROR(get_logger(), "%s: %s", key.c_str(), reason.c_str());
  }

  struct Statistics
  {
    uint64_t received = 0;
    uint64_t published = 0;
    uint64_t raw_states = 0;
    uint64_t compact_states = 0;
    uint64_t sequence_observed = 0;
    uint64_t sequence_unavailable = 0;
    uint64_t sequence_gaps = 0;
    uint64_t sequence_duplicates = 0;
    uint64_t sequence_regressions = 0;
    std::map<std::array<uint8_t, RMW_GID_STORAGE_SIZE>, uint64_t> last_sequences;
  };

  const std::vector<std::string> components_{
    "base", "lidar", "wheel_left", "wheel_right", "caster_back_left", "caster_back_right"};
  bool sequence_supported_ = false;
  std::map<std::string, Statistics> stats_;
  std::vector<rclcpp::Publisher<gazebo_msgs::msg::ContactsState>::SharedPtr> publishers_;
  std::vector<rclcpp::Subscription<gazebo_msgs::msg::ContactsState>::SharedPtr> subscriptions_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr failure_publisher_;
};

}  // namespace multi_robot

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<multi_robot::ContactReducer>();
  rclcpp::spin(node);
  node.reset();
  rclcpp::shutdown();
  return 0;
}
