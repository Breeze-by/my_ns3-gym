// Static SDK/RMW proof only. No participant, ROS context, node or endpoint is created.
// Adapted from the preserved P1A lifecycle_reply_qos_v6_checker.cpp.
#include <fastdds/dds/publisher/qos/DataWriterQos.hpp>
#include <fastrtps/attributes/PublisherAttributes.h>
#include <fastrtps/xmlparser/XMLProfileManager.h>
#include <rmw/qos_profiles.h>
#include <rmw_fastrtps_shared_cpp/names.hpp>
#include <rmw_fastrtps_shared_cpp/qos.hpp>

#include <iostream>
#include <set>
#include <string>
#include <utility>
#include <vector>

using eprosima::fastdds::dds::DataWriterQos;
using eprosima::fastrtps::PublisherAttributes;
using eprosima::fastrtps::xmlparser::XMLProfileManager;
using eprosima::fastrtps::xmlparser::XMLP_ret;

int main(int argc, char **argv)
{
  if (argc != 2 || XMLProfileManager::loadXMLFile(argv[1]) != XMLP_ret::XML_OK) {
    return 1;
  }
  PublisherAttributes defaults;
  XMLProfileManager::getDefaultPublisherAttributes(defaults);
  const auto default_duration = defaults.qos.m_reliability.max_blocking_time;
  if (default_duration.seconds != 0 || default_duration.nanosec != 100000000) {
    return 2;
  }
  const std::vector<std::string> nodes = {
    "controller_server", "planner_server", "behavior_server", "bt_navigator",
    "waypoint_follower", "velocity_smoother"};
  const std::vector<std::pair<std::string, int>> services = {
    {"change_state", 5}, {"get_state", 1}};
  std::set<std::string> unselected = {
    "service", "default", "/clock", "rt/clock", "/exploration_start", "rt/exploration_start",
    "/exploration_stopped", "rt/exploration_stopped", "/exploration_failure",
    "rt/exploration_failure", "rr/tb1/velocity_smoother/Get_stateReply"};
  int count = 0, change_count = 0, get_count = 0;
  for (int robot = 1; robot <= 3; ++robot) {
    const auto robot_name = "/tb" + std::to_string(robot);
    for (const auto &node : nodes) {
      for (const auto &service : services) {
        const auto service_name = robot_name + "/" + node + "/" + service.first;
        const auto name = _create_topic_name(
          &rmw_qos_profile_services_default, ros_service_response_prefix,
          service_name.c_str(), "Reply").to_string();
        if (name != "rr" + service_name + "Reply") {
          return 3;
        }
        PublisherAttributes profile;
        if (XMLProfileManager::fillPublisherAttributes(name, profile, false) != XMLP_ret::XML_OK) {
          return 4;
        }
        auto expected = defaults;
        expected.qos.m_reliability.kind = eprosima::fastdds::dds::RELIABLE_RELIABILITY_QOS;
        expected.qos.m_reliability.max_blocking_time.seconds = service.second;
        expected.qos.m_reliability.max_blocking_time.nanosec = 0;
        if (!(profile == expected)) {
          return 5;
        }
        DataWriterQos writer;
        // Same attributes-to-QoS assignment as installed SDK PublisherImpl.
        writer.reliability() = profile.qos.m_reliability;
        writer.history() = profile.topic.historyQos;
        // Actual installed RMW conversion, with no ROS context initialization.
        if (!get_datawriter_qos(rmw_qos_profile_services_default, writer) ||
          writer.reliability().max_blocking_time.seconds != service.second ||
          writer.reliability().max_blocking_time.nanosec != 0 ||
          writer.reliability().kind != eprosima::fastdds::dds::RELIABLE_RELIABILITY_QOS ||
          writer.history().depth != static_cast<int>(rmw_qos_profile_services_default.depth))
        {
          return 6;
        }
        ++count;
        service.second == 5 ? ++change_count : ++get_count;
        unselected.insert("rq" + service_name + "Request");
        unselected.insert(name + "Extra");
        unselected.insert(name + "/");
        unselected.insert("rr/tb4/" + node + "/" + service.first + "Reply");
        unselected.insert("rr/tb0/" + node + "/" + service.first + "Reply");
      }
    }
    for (const auto &component : {"base", "lidar", "wheel_left", "wheel_right",
        "caster_back_left", "caster_back_right"})
    {
      const auto raw = robot_name + "/collision" +
        (std::string(component) == "base" ? "" : "/" + std::string(component));
      unselected.insert(raw);
      unselected.insert("rt" + raw);
      unselected.insert("rt/mr3_contacts" + robot_name + "/" + component);
    }
  }
  for (const auto &name : unselected) {
    PublisherAttributes probe = defaults;
    if (XMLProfileManager::fillPublisherAttributes(name, probe, false) != XMLP_ret::XML_ERROR ||
      !(probe == defaults))
    {
      return 7;
    }
    DataWriterQos writer;
    auto qos = rmw_qos_profile_default;
    if (name.find("collision") != std::string::npos ||
      name.find("mr3_contacts") != std::string::npos)
    {
      qos.depth = 100;
    }
    if (!get_datawriter_qos(qos, writer) ||
      writer.reliability().max_blocking_time != default_duration)
    {
      return 8;
    }
  }
  if (count != 36 || change_count != 18 || get_count != 18) {
    return 9;
  }
  std::cout << "{\"participant_created\":false,\"ros_context_initialized\":false,"
    "\"selected_response_writers\":" << count << ",\"change_state_reply_count\":" <<
    change_count << ",\"get_state_reply_count\":" << get_count <<
    ",\"installed_rmw_name_mangling_verified\":true,"
    "\"other_publisher_attributes_unchanged\":true,"
    "\"default_blocking_ns\":100000000,\"change_state_after_rmw_blocking_ns\":5000000000,"
    "\"get_state_after_rmw_blocking_ns\":1000000000,"
    "\"ros_service_reliability\":\"RELIABLE\",\"ros_service_depth\":" <<
    rmw_qos_profile_services_default.depth << ",\"unmatched_writer_profiles_checked\":" <<
    unselected.size() << ",\"unmatched_blocking_ns\":100000000}\n";
  return 0;
}
