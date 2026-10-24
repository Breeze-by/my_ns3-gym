#ifndef MULTI_ROBOT__MR3_ODOMETRY_JSON_HPP_
#define MULTI_ROBOT__MR3_ODOMETRY_JSON_HPP_

#include <geometry_msgs/msg/transform_stamped.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nlohmann/json.hpp>
#include <std_msgs/msg/header.hpp>
#include <tf2_msgs/msg/tf_message.hpp>

namespace multi_robot::odometry_json
{

inline nlohmann::json header(const std_msgs::msg::Header & value)
{
  return {{"stamp", {{"sec", value.stamp.sec}, {"nanosec", value.stamp.nanosec}}},
    {"frame_id", value.frame_id}};
}

template<typename Vector>
inline nlohmann::json xyz(const Vector & value)
{
  return {{"x", value.x}, {"y", value.y}, {"z", value.z}};
}

inline nlohmann::json quaternion(const geometry_msgs::msg::Quaternion & value)
{
  return {{"x", value.x}, {"y", value.y}, {"z", value.z}, {"w", value.w}};
}

inline nlohmann::json odometry(const nav_msgs::msg::Odometry & value)
{
  return {{"header", header(value.header)}, {"child_frame_id", value.child_frame_id},
    {"pose", {{"pose", {{"position", xyz(value.pose.pose.position)},
                         {"orientation", quaternion(value.pose.pose.orientation)}}},
              {"covariance", value.pose.covariance}}},
    {"twist", {{"twist", {{"linear", xyz(value.twist.twist.linear)},
                           {"angular", xyz(value.twist.twist.angular)}}},
               {"covariance", value.twist.covariance}}}};
}

inline nlohmann::json transform(const geometry_msgs::msg::TransformStamped & value)
{
  return {{"header", header(value.header)}, {"child_frame_id", value.child_frame_id},
    {"transform", {{"translation", xyz(value.transform.translation)},
                   {"rotation", quaternion(value.transform.rotation)}}}};
}

inline nlohmann::json tf_message(const tf2_msgs::msg::TFMessage & value)
{
  auto transforms = nlohmann::json::array();
  for (const auto & item : value.transforms) {
    transforms.push_back(transform(item));
  }
  return {{"transforms", transforms}};
}

}  // namespace multi_robot::odometry_json
#endif  // MULTI_ROBOT__MR3_ODOMETRY_JSON_HPP_
