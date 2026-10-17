// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: BSD-3-Clause
#ifndef MULTI_ROBOT__MR3_DRIVE_TARGET_HPP_
#define MULTI_ROBOT__MR3_DRIVE_TARGET_HPP_

#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <nlohmann/json.hpp>

namespace multi_robot
{
struct DriveTarget
{
  std::string epoch;
  std::string robot;
  int64_t clock_ns;
  int64_t decision_sequence;
  double linear_x;
  double angular_z;
};

inline int64_t DriveTargetInteger(const nlohmann::json & value, bool positive)
{
  if (!value.is_number_integer() ||
    (value.is_number_unsigned() &&
    value.get<uint64_t>() > static_cast<uint64_t>(std::numeric_limits<int64_t>::max())))
  {
    throw std::invalid_argument("drive target requires signed-range integer endpoints");
  }
  const auto result = value.get<int64_t>();
  if (result < 0 || (positive && result == 0)) {
    throw std::invalid_argument("drive target integer endpoint out of range");
  }
  return result;
}

inline DriveTarget ParseDriveTarget(const nlohmann::json & value)
{
  if (!value.is_object() || value.size() != 7 ||
    value.value("schema", std::string()) != "mr3-drive-target-v1" ||
    !value.at("epoch").is_string() || !value.at("robot").is_string() ||
    !value.at("linear_x").is_number() || !value.at("angular_z").is_number())
  {
    throw std::invalid_argument("invalid drive target schema/fields/types");
  }
  DriveTarget target{value.at("epoch").get<std::string>(),
    value.at("robot").get<std::string>(), DriveTargetInteger(value.at("clock_ns"), false),
    DriveTargetInteger(value.at("decision_sequence"), true),
    value.at("linear_x").get<double>(), value.at("angular_z").get<double>()};
  if (target.epoch.empty() || target.robot.empty() || !std::isfinite(target.linear_x) ||
    !std::isfinite(target.angular_z) || std::abs(target.linear_x) > .26 ||
    std::abs(target.angular_z) > .8)
  {
    throw std::invalid_argument("drive target identity/finite command limits");
  }
  return target;
}

inline void ValidateDriveTarget(
  const DriveTarget & target, const std::string & epoch, const std::string & robot,
  int64_t actual_world_clock_ns, int64_t previous_decision_sequence,
  int64_t previous_source_clock_ns)
{
  if (target.epoch != epoch || target.robot != robot) {
    throw std::invalid_argument("drive target epoch/robot mismatch");
  }
  if (target.clock_ns > actual_world_clock_ns) {
    throw std::invalid_argument("drive target source clock is future");
  }
  if (target.decision_sequence <= previous_decision_sequence) {
    throw std::invalid_argument("drive target decision sequence is stale");
  }
  if (target.clock_ns < previous_source_clock_ns) {
    throw std::invalid_argument("drive target source clock regressed");
  }
}
}  // namespace multi_robot
#endif  // MULTI_ROBOT__MR3_DRIVE_TARGET_HPP_
