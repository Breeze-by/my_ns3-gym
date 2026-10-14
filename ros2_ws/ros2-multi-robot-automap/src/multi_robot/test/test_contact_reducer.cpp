// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: MIT

#include <string>
#include <vector>

#include "gtest/gtest.h"
#include "multi_robot/contact_reducer.hpp"

namespace
{

gazebo_msgs::msg::ContactState contact(const std::string & first, const std::string & second)
{
  gazebo_msgs::msg::ContactState state;
  state.collision1_name = first;
  state.collision2_name = second;
  state.info = "original sensor info";
  geometry_msgs::msg::Wrench wrench;
  wrench.force.x = 1.25;
  wrench.force.y = -2.5;
  wrench.torque.z = 3.75;
  state.wrenches.push_back(wrench);
  state.total_wrench = wrench;
  geometry_msgs::msg::Vector3 position;
  position.x = 0.31;
  position.y = -0.27;
  position.z = 0.03;
  state.contact_positions.push_back(position);
  geometry_msgs::msg::Vector3 normal;
  normal.z = 1.0;
  state.contact_normals.push_back(normal);
  state.depths.push_back(0.002);
  return state;
}

gazebo_msgs::msg::ContactsState message()
{
  gazebo_msgs::msg::ContactsState raw;
  raw.header.frame_id = "wheel_left_link";
  raw.header.stamp.sec = 42;
  raw.header.stamp.nanosec = 987654321;
  return raw;
}

}  // namespace

TEST(ContactReducer, RepeatedPairKeepsFirstCompleteGeometryAndExactRawCount)
{
  auto raw = message();
  const auto first = contact(
    "tb1::wheel_left_link::wheel_left_collision", "ground_plane::link::collision");
  for (int index = 0; index < 50; ++index) {
    auto sample = first;
    sample.contact_positions[0].x += index;
    sample.info += std::to_string(index);
    raw.states.push_back(sample);
  }
  const auto compact = multi_robot::reduce_contacts(raw);
  ASSERT_EQ(compact.states.size(), 1u);
  EXPECT_EQ(compact.header, raw.header);
  auto expected = raw.states.front();
  expected.info = "mr3_contact_reduce_v1 raw_pair_samples=50\n" + expected.info;
  EXPECT_EQ(compact.states.front(), expected);
  EXPECT_EQ(raw.states.size(), 50u);
  EXPECT_EQ(raw.states.front().info, "original sensor info0");
}

TEST(ContactReducer, ReversedPairIsTheSamePairButFirstOrientationIsPreserved)
{
  auto raw = message();
  raw.states.push_back(contact("tb2::base_link::base_collision", "tb1::base_link::base_collision"));
  raw.states.push_back(contact("tb1::base_link::base_collision", "tb2::base_link::base_collision"));
  const auto compact = multi_robot::reduce_contacts(raw);
  ASSERT_EQ(compact.states.size(), 1u);
  EXPECT_EQ(compact.states.front().collision1_name, raw.states.front().collision1_name);
  EXPECT_EQ(compact.states.front().collision2_name, raw.states.front().collision2_name);
  EXPECT_EQ(
    compact.states.front().info,
    "mr3_contact_reduce_v1 raw_pair_samples=2\noriginal sensor info");
}

TEST(ContactReducer, EverySupportWallRobotAndUnknownPairIsRetained)
{
  auto raw = message();
  raw.states = {
    contact("tb1::wheel_left_link::wheel_left_collision", "ground_plane::link::collision"),
    contact("tb1::wheel_left_link::wheel_left_collision", "walls::wall::collision"),
    contact("tb1::base_link::base_collision", "ground_plane::link::collision"),
    contact("tb1::base_link::base_collision", "tb2::base_link::base_collision"),
    contact("unknown", ""),
  };
  const auto compact = multi_robot::reduce_contacts(raw);
  ASSERT_EQ(compact.states.size(), raw.states.size());
  for (std::size_t index = 0; index < raw.states.size(); ++index) {
    auto expected = raw.states[index];
    expected.info = "mr3_contact_reduce_v1 raw_pair_samples=1\n" + expected.info;
    EXPECT_EQ(compact.states[index], expected);
  }
}

TEST(ContactReducer, EmptyMessageKeepsOriginalFrameAndSourceTime)
{
  const auto raw = message();
  const auto compact = multi_robot::reduce_contacts(raw);
  EXPECT_TRUE(compact.states.empty());
  EXPECT_EQ(compact.header, raw.header);
}

TEST(ContactReducer, ContactEmptyContactAreThreeIndependentOutputs)
{
  auto active = message();
  active.states.push_back(contact("tb1::base_link::base_collision", "walls::wall::collision"));
  auto empty = message();
  empty.header.stamp.sec += 1;
  auto next = active;
  next.header.stamp.sec += 2;
  const std::vector<gazebo_msgs::msg::ContactsState> raw{active, empty, next};
  std::vector<gazebo_msgs::msg::ContactsState> compact;
  for (const auto & sample : raw) {
    compact.push_back(multi_robot::reduce_contacts(sample));
  }
  ASSERT_EQ(compact.size(), raw.size());
  EXPECT_EQ(compact[0].states.size(), 1u);
  EXPECT_TRUE(compact[1].states.empty());
  EXPECT_EQ(compact[2].states.size(), 1u);
  for (std::size_t index = 0; index < raw.size(); ++index) {
    EXPECT_EQ(compact[index].header, raw[index].header);
  }
}
