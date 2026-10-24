// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: MIT

#ifndef MULTI_ROBOT__CONTACT_REDUCER_HPP_
#define MULTI_ROBOT__CONTACT_REDUCER_HPP_

#include <array>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "gazebo_msgs/msg/contacts_state.hpp"
#include "rmw/types.h"

namespace multi_robot
{

using PublisherId = std::array<uint8_t, RMW_GID_STORAGE_SIZE>;

/// Audit one raw topic without discarding a message when its source is invalid.
struct ContactSourceAudit
{
  uint64_t observed = 0;
  uint64_t unavailable = 0;
  uint64_t gaps = 0;
  uint64_t duplicates = 0;
  uint64_t regressions = 0;
  std::set<PublisherId> publishers;
  std::map<PublisherId, uint64_t> last_sequences;

  std::pair<std::string, uint64_t> observe(
    const PublisherId & publisher, uint64_t sequence, bool feature_supported)
  {
    publishers.insert(publisher);
    std::pair<std::string, uint64_t> failure;
    if (publishers.size() > 1 && !multiple_reported_) {
      multiple_reported_ = true;
      failure.first = "contact_transport_multiple_publishers";
    }
    if (!feature_supported || sequence == RMW_MESSAGE_INFO_SEQUENCE_NUMBER_UNSUPPORTED) {
      ++unavailable;
      if (!unavailable_reported_) {
        unavailable_reported_ = true;
        failure.first = feature_supported ?
          "contact_transport_sequence_metadata_unavailable" :
          "contact_transport_sequence_unsupported";
      }
      return failure;
    }
    ++observed;
    const auto previous = last_sequences.find(publisher);
    if (previous != last_sequences.end()) {
      if (sequence > previous->second + 1) {
        const auto missing = sequence - previous->second - 1;
        gaps += missing;
        failure = {"contact_transport_sequence_gap", missing};
      } else if (sequence == previous->second) {
        ++duplicates;
        failure.first = "contact_transport_sequence_duplicate";
      } else if (sequence < previous->second) {
        ++regressions;
        failure.first = "contact_transport_sequence_regression";
      }
    }
    last_sequences[publisher] = sequence;
    return failure;
  }

private:
  bool unavailable_reported_ = false;
  bool multiple_reported_ = false;
};

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
