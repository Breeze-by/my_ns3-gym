// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: MIT

#ifndef MULTI_ROBOT__CONTACT_REDUCER_HPP_
#define MULTI_ROBOT__CONTACT_REDUCER_HPP_

#include <map>
#include <string>
#include <utility>
#include <vector>

#include "gazebo_msgs/msg/contacts_state.hpp"

namespace multi_robot
{

/// Preserve every collision pair and the original header in each raw message.
/// Repeated unordered pairs share their first complete geometry sample. No
/// states are filtered and no information is combined across source messages.
inline gazebo_msgs::msg::ContactsState reduce_contacts(
  const gazebo_msgs::msg::ContactsState & raw)
{
  gazebo_msgs::msg::ContactsState compact;
  compact.header = raw.header;
  std::map<std::pair<std::string, std::string>, std::size_t> indices;
  std::vector<std::size_t> sample_counts;
  for (const auto & state : raw.states) {
    const auto key = state.collision1_name <= state.collision2_name ?
      std::make_pair(state.collision1_name, state.collision2_name) :
      std::make_pair(state.collision2_name, state.collision1_name);
    const auto inserted = indices.emplace(key, compact.states.size());
    if (inserted.second) {
      compact.states.push_back(state);
      sample_counts.push_back(1);
    } else {
      ++sample_counts[inserted.first->second];
    }
  }
  for (std::size_t index = 0; index < compact.states.size(); ++index) {
    auto & state = compact.states[index];
    state.info = "mr3_contact_reduce_v1 raw_pair_samples=" +
      std::to_string(sample_counts[index]) + "\n" + state.info;
  }
  return compact;
}

}  // namespace multi_robot

#endif  // MULTI_ROBOT__CONTACT_REDUCER_HPP_
