// Static SDK/RMW QoS proof. No participant, node, writer or reader is created.
#include <fastdds/dds/publisher/qos/DataWriterQos.hpp>
#include <fastrtps/attributes/PublisherAttributes.h>
#include <fastrtps/xmlparser/XMLProfileManager.h>
#include <rmw/qos_profiles.h>
#include <rmw_fastrtps_shared_cpp/qos.hpp>
#include <rmw_fastrtps_shared_cpp/names.hpp>

#include <iostream>
#include <string>
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
  int count = 0;
  for (int robot = 1; robot <= 3; ++robot) {
    for (const auto &node : nodes) {
      const auto service_name = "/tb" + std::to_string(robot) + "/" + node + "/change_state";
      const auto name = _create_topic_name(
        &rmw_qos_profile_services_default, ros_service_response_prefix,
        service_name.c_str(), "Reply").to_string();
      if (name != "rr" + service_name + "Reply") {
        return 9;
      }
      PublisherAttributes profile;
      if (XMLProfileManager::fillPublisherAttributes(name, profile, false) != XMLP_ret::XML_OK) {
        return 3;
      }
      auto expected_profile = defaults;
      expected_profile.qos.m_reliability.kind = eprosima::fastdds::dds::RELIABLE_RELIABILITY_QOS;
      expected_profile.qos.m_reliability.max_blocking_time.seconds = 5;
      expected_profile.qos.m_reliability.max_blocking_time.nanosec = 0;
      if (!(profile == expected_profile)) {
        return 8;
      }
      DataWriterQos writer;
      // Same field assignment as installed SDK PublisherImpl::set_qos_from_attributes.
      writer.reliability() = profile.qos.m_reliability;
      writer.history() = profile.topic.historyQos;
      if (writer.reliability().max_blocking_time.seconds != 5 ||
        writer.reliability().max_blocking_time.nanosec != 0)
      {
        return 4;
      }
      // Call the actual installed RMW conversion function; no ROS context is initialized.
      if (!get_datawriter_qos(rmw_qos_profile_services_default, writer) ||
        writer.reliability().max_blocking_time.seconds != 5 ||
        writer.reliability().max_blocking_time.nanosec != 0 ||
        writer.reliability().kind != eprosima::fastdds::dds::RELIABLE_RELIABILITY_QOS ||
        writer.history().depth != static_cast<int>(rmw_qos_profile_services_default.depth))
      {
        return 5;
      }
      ++count;
    }
  }
  const std::vector<std::string> unselected = {
    "service", "/exploration_start", "rt/exploration_start",
    "/exploration_stopped", "rt/exploration_stopped", "/exploration_failure",
    "rt/exploration_failure", "/tb1/collision", "rt/tb1/collision",
    "/mr3_contacts/tb1/base", "rt/mr3_contacts/tb1/base", "/clock", "rt/clock",
    "rr/tb1/controller_server/get_stateReply", "rq/tb1/controller_server/change_stateRequest",
    "rr/tb4/controller_server/change_stateReply"};
  for (const auto &name : unselected) {
    PublisherAttributes probe = defaults;
    if (XMLProfileManager::fillPublisherAttributes(name, probe, false) != XMLP_ret::XML_ERROR ||
      probe.qos.m_reliability.max_blocking_time != default_duration)
    {
      return 6;
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
      return 7;
    }
  }
  std::cout << "{\"participant_created\":false,\"selected_response_writers\":" << count <<
    ",\"installed_rmw_name_mangling_verified\":true,"
    "\"other_publisher_attributes_unchanged\":true,"
    "\"default_blocking_ns\":100000000,\"selected_xml_blocking_ns\":5000000000,"
    "\"selected_after_rmw_conversion_blocking_ns\":5000000000,"
    "\"ros_service_reliability\":\"RELIABLE\",\"ros_service_depth\":" <<
    rmw_qos_profile_services_default.depth << ",\"unmatched_writer_profiles_checked\":" <<
    unselected.size() << ",\"unmatched_blocking_ns\":100000000}\n";
  return 0;
}
