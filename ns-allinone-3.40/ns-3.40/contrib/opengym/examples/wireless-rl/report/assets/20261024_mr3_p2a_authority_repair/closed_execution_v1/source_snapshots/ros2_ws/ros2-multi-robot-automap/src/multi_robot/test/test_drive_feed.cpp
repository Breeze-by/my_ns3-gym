// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include <cfenv>
#include <cmath>
#include <limits>
#include "multi_robot/mr3_drive_feed.hpp"

namespace
{
namespace feed = multi_robot::drive_feed;

nlohmann::json Target()
{
  return {{"schema", "mr3-drive-target-v1"}, {"epoch", "episode"}, {"robot", "tb2"},
    {"clock_ns", 100}, {"decision_sequence", 3}, {"linear_x", 0}, {"angular_z", -.3}};
}

std::vector<feed::AppliedPair> Pairs()
{
  return {{0, {{.1, -.1}}, {{.03, -.03}}, {{.08, -.08}}, .25, 1.0},
    {1, {{.2, -.2}}, {{.04, -.04}}, {{.12, -.12}}, .5, 2.0}};
}

nlohmann::json Odometry()
{
  const nlohmann::json vector{{"x", .001}, {"y", -.002}, {"z", 0.0}};
  const nlohmann::json quaternion{{"x", 0.0}, {"y", 0.0}, {"z", .1}, {"w", .9}};
  const nlohmann::json covariance = std::vector<double>(36, .00001);
  return {{"header", {{"stamp", {{"sec", 1}, {"nanosec", 20}}}, {"frame_id", "odom"}}},
    {"child_frame_id", "base_footprint"},
    {"pose", {{"pose", {{"position", vector}, {"orientation", quaternion}}},
      {"covariance", covariance}}},
    {"twist", {{"twist", {{"linear", vector}, {"angular", vector}}},
      {"covariance", covariance}}}};
}

struct RestoreEnvironment
{
  int rounding = std::fegetround();
#ifdef __SSE__
  unsigned int csr = _mm_getcsr();
#endif
  ~RestoreEnvironment()
  {
    std::fesetround(rounding);
#ifdef __SSE__
    _mm_setcsr(csr);
#endif
  }
};
}  // namespace

TEST(DriveFeed, AppliedBindsOriginalSevenFieldTargetAndEveryRightLeftPair)
{
  auto target = Target();
  const auto pairs = Pairs();
  const auto value = feed::Applied("episode", "tb2", 134, 7, 5, 34, target, pairs);
  ASSERT_EQ(value.size(), 9u);
  EXPECT_EQ(value.at("schema"), "mr3-drive-applied-v1");
  EXPECT_EQ(value.at("target"), target);
  EXPECT_EQ(value.at("target").size(), 7u);
  EXPECT_TRUE(value.at("target").at("linear_x").is_number_integer());
  EXPECT_EQ(value.at("source_clock_ns"), 134);
  EXPECT_EQ(value.at("actuation_sequence"), 7);
  EXPECT_EQ(value.at("cmd_seq"), 5);
  EXPECT_EQ(value.at("dt_ns"), 34);
  ASSERT_EQ(value.at("pairs").size(), 2u);
  for (std::size_t i = 0; i < pairs.size(); ++i) {
    const auto & actual = value.at("pairs").at(i);
    EXPECT_EQ(actual.size(), 6u);
    EXPECT_EQ(actual.at("pair_index"), i);
    EXPECT_EQ(actual.at("current_rim_mps"), pairs[i].current_rim_mps);
    EXPECT_EQ(actual.at("desired_rim_mps"), pairs[i].desired_rim_mps);
    EXPECT_EQ(actual.at("applied_rim_mps"), pairs[i].applied_rim_mps);
  }
  target["decision_sequence"] = 999;
  EXPECT_EQ(value.at("target").at("decision_sequence"), 3);
  EXPECT_EQ(nlohmann::json::parse(value.dump()), value);
}

TEST(DriveFeed, AppliedCannotInventAnInitialOrFutureOrForeignTarget)
{
  for (const auto & owner : {std::make_pair("other", "tb2"),
      std::make_pair("episode", "tb1")})
  {
    EXPECT_THROW(feed::Applied(owner.first, owner.second, 134, 7, 5, 34,
      Target(), Pairs()), std::invalid_argument);
  }
  EXPECT_THROW(feed::Applied("episode", "tb2", 99, 7, 5, 34, Target(), Pairs()),
    std::invalid_argument);
  auto invalid = Target(); invalid["decision_sequence"] = 0;
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 7, 5, 34, invalid, Pairs()),
    std::invalid_argument);
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 0, 5, 34, Target(), Pairs()),
    std::invalid_argument);
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 7, 0, 34, Target(), Pairs()),
    std::invalid_argument);
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 7, 5, 0, Target(), Pairs()),
    std::invalid_argument);
}

TEST(DriveFeed, MissingReorderedAndNonfinitePairsDoNotProducePlausibleReceipts)
{
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 7, 5, 34, Target(), {}),
    std::invalid_argument);
  auto pairs = Pairs(); pairs[0].pair_index = 1;
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 7, 5, 34, Target(), pairs),
    std::invalid_argument);
  pairs = Pairs(); pairs[1].applied_rim_mps[1] = std::numeric_limits<double>::infinity();
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 7, 5, 34, Target(), pairs),
    std::invalid_argument);
  pairs = Pairs(); pairs[0].alpha = std::numeric_limits<double>::quiet_NaN();
  EXPECT_THROW(feed::Applied("episode", "tb2", 134, 7, 5, 34, Target(), pairs),
    std::invalid_argument);
}

TEST(DriveFeed, CalibrationCarriesActualBinary32CoefficientsWithoutNormalising)
{
  const float c = .6F, s = .8F;
  const auto original = Odometry();
  const auto value = feed::OdometryCalibration("episode", "tb2", 1000000020, 9,
    c, s, original);
  ASSERT_EQ(value.size(), 10u);
  EXPECT_EQ(value.at("schema"), "mr3-odom-calibration-v1");
  EXPECT_EQ(value.at("conversion_contract"), "float32-trig-binary64-rn-v1");
  EXPECT_EQ(value.at("producer_frame"), "world-common-model-origin-v1");
  EXPECT_EQ(value.at("publication_sequence"), 9);
  EXPECT_DOUBLE_EQ(value.at("coefficient_c").get<double>(), static_cast<double>(c));
  EXPECT_DOUBLE_EQ(value.at("coefficient_s").get<double>(), static_cast<double>(s));
  const double norm_squared = static_cast<double>(c) * c + static_cast<double>(s) * s;
  EXPECT_NE(norm_squared, 1.0);
  EXPECT_EQ(value.at("odometry"), original);
  EXPECT_EQ(nlohmann::json::parse(value.dump()), value);
  EXPECT_FALSE(value.contains("world_linear_velocity"));
}

TEST(DriveFeed, CalibrationRejectsEvenOneNanosecondSourceMismatchAndInvalidCoefficients)
{
  EXPECT_THROW(feed::OdometryCalibration("episode", "tb2", 1000000021, 9,
    .6F, .8F, Odometry()), std::invalid_argument);
  EXPECT_THROW(feed::OdometryCalibration("episode", "tb2", 1000000020, 0,
    .6F, .8F, Odometry()), std::invalid_argument);
  for (float invalid : {std::numeric_limits<float>::infinity(),
      std::numeric_limits<float>::quiet_NaN(), 1.01F})
  {
    EXPECT_THROW(feed::OdometryCalibration("episode", "tb2", 1000000020, 9,
      invalid, .8F, Odometry()), std::invalid_argument);
  }
  EXPECT_THROW(feed::OdometryCalibration("episode", "tb2", 1000000020, 9,
    0.F, 0.F, Odometry()), std::invalid_argument);
}

TEST(DriveFeed, PhysicsThreadMustUseRoundToNearestAndGradualUnderflow)
{
  RestoreEnvironment restore;
  ASSERT_EQ(std::fesetround(FE_TONEAREST), 0);
#ifdef __SSE__
  _mm_setcsr(_mm_getcsr() & ~((1U << 6) | (1U << 15)));
#endif
  EXPECT_NO_THROW(feed::ValidateConversionEnvironment());
  ASSERT_EQ(std::fesetround(FE_DOWNWARD), 0);
  EXPECT_THROW(feed::ValidateConversionEnvironment(), std::runtime_error);
}

#ifdef __SSE__
TEST(DriveFeed, PhysicsThreadRejectsIndependentSseDazFtzAndRoundingChanges)
{
  RestoreEnvironment restore;
  ASSERT_EQ(std::fesetround(FE_TONEAREST), 0);
  const auto nearest = _mm_getcsr() & ~((1U << 6) | (1U << 15) | _MM_ROUND_MASK);
  for (unsigned int forbidden : {(1U << 6), (1U << 15),
      static_cast<unsigned int>(_MM_ROUND_UP)})
  {
    _mm_setcsr(nearest | forbidden);
    EXPECT_THROW(feed::ValidateConversionEnvironment(), std::runtime_error);
  }
}
#endif
