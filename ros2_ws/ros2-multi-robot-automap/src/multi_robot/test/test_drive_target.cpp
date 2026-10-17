// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include <cmath>
#include <limits>
#include "multi_robot/mr3_drive_target.hpp"

namespace
{
nlohmann::json Target()
{
  return {{"schema", "mr3-drive-target-v1"}, {"epoch", "episode"}, {"robot", "tb2"},
    {"clock_ns", 100}, {"decision_sequence", 3}, {"linear_x", .26}, {"angular_z", -.8}};
}
}

TEST(DriveTarget, ExactEndpointsAndCurrentWorldClockAreAccepted)
{
  const auto target = multi_robot::ParseDriveTarget(Target());
  EXPECT_NO_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb2", 100, 2, 100));
  EXPECT_DOUBLE_EQ(target.linear_x, .26);
  EXPECT_DOUBLE_EQ(target.angular_z, -.8);
}

TEST(DriveTarget, MissingExtraWrongSchemaAndNonobjectAreRejected)
{
  for (const auto * key : {"schema", "epoch", "robot", "clock_ns", "decision_sequence",
      "linear_x", "angular_z"})
  {
    auto value = Target(); value.erase(key);
    EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
  }
  auto value = Target(); value["extra"] = true;
  EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
  value = Target(); value["schema"] = "unknown";
  EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
  EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(nlohmann::json::array()));
}

TEST(DriveTarget, IntegerFieldsDoNotCoerceFloatBoolOrOverflow)
{
  for (const auto * key : {"clock_ns", "decision_sequence"}) {
    for (const auto & invalid : {nlohmann::json(1.0), nlohmann::json(true),
        nlohmann::json(-1), nlohmann::json("1"),
        nlohmann::json(std::numeric_limits<uint64_t>::max())})
    {
      auto value = Target(); value[key] = invalid;
      EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
    }
  }
  auto value = Target(); value["decision_sequence"] = 0;
  EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
  value = Target(); value["clock_ns"] = 0;
  EXPECT_NO_THROW(multi_robot::ParseDriveTarget(value));
}

TEST(DriveTarget, TaggedCommandsRejectEvenOneUlpBeyondTheFinalGuardCaps)
{
  for (const auto & item : {std::make_pair("linear_x", .26), std::make_pair("angular_z", .8)}) {
    for (double sign : {-1., 1.}) {
      auto value = Target(); value[item.first] = sign * item.second;
      EXPECT_NO_THROW(multi_robot::ParseDriveTarget(value));
      value[item.first] = sign * std::nextafter(item.second, std::numeric_limits<double>::infinity());
      EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
    }
  }
}

TEST(DriveTarget, NonfiniteAndNonNumericCommandsAndEmptyIdentityAreRejected)
{
  for (const auto * key : {"linear_x", "angular_z"}) {
    for (const auto & invalid : {nlohmann::json(std::numeric_limits<double>::infinity()),
        nlohmann::json(std::numeric_limits<double>::quiet_NaN()), nlohmann::json(true),
        nlohmann::json("0.1")})
    {
      auto value = Target(); value[key] = invalid;
      EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
    }
  }
  for (const auto * key : {"epoch", "robot"}) {
    auto value = Target(); value[key] = "";
    EXPECT_ANY_THROW(multi_robot::ParseDriveTarget(value));
  }
}

TEST(DriveTarget, WrongRobotOrEpochCannotEnterState)
{
  const auto target = multi_robot::ParseDriveTarget(Target());
  EXPECT_THROW(multi_robot::ValidateDriveTarget(target, "other", "tb2", 100, 0, 0), std::invalid_argument);
  EXPECT_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb1", 100, 0, 0), std::invalid_argument);
}

TEST(DriveTarget, FutureOneNanosecondIsRejectedWithoutTolerance)
{
  const auto target = multi_robot::ParseDriveTarget(Target());
  EXPECT_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb2", 99, 0, 0), std::invalid_argument);
  EXPECT_NO_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb2", 100, 0, 0));
}

TEST(DriveTarget, EqualOrOlderDecisionCannotOverwriteNewerTarget)
{
  const auto target = multi_robot::ParseDriveTarget(Target());
  for (int64_t previous : {3, 4, 100}) {
    EXPECT_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb2", 100, previous, 0),
      std::invalid_argument);
  }
  EXPECT_NO_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb2", 100, 1, 0));
}

TEST(DriveTarget, SourceClockCannotRegressButSameClockHigherDecisionIsAllowed)
{
  const auto target = multi_robot::ParseDriveTarget(Target());
  EXPECT_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb2", 101, 2, 101), std::invalid_argument);
  EXPECT_NO_THROW(multi_robot::ValidateDriveTarget(target, "episode", "tb2", 101, 2, 100));
}
