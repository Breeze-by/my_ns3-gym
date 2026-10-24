#include <gtest/gtest.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <random>
#include <stdexcept>

#include "multi_robot/paired_wheel_slew.hpp"

using multi_robot::limit_paired_wheel_speeds;

TEST(PairedWheelSlew, UsesOneFractionFromCurrentFeedbackInsteadOfRetainedInstruction)
{
  const auto result = limit_paired_wheel_speeds({0.1, -0.1}, {0.4, 0.0}, 1.0, 0.03);
  EXPECT_NEAR(result.alpha, 0.1, 1e-15);
  EXPECT_NEAR(result.applied[0], 0.13, 1e-15);
  EXPECT_NEAR(result.applied[1], -0.09, 1e-15);
  // A repeated call with unchanged measured feedback has no hidden accumulation.
  const auto repeated = limit_paired_wheel_speeds({0.1, -0.1}, {0.4, 0.0}, 1.0, 0.03);
  EXPECT_EQ(repeated.applied, result.applied);
  EXPECT_DOUBLE_EQ(repeated.alpha, result.alpha);
}

TEST(PairedWheelSlew, ZeroTargetBrakesBothWheelsWithoutInventingTurn)
{
  const std::array<double, 2> current{0.4722, 0.1278};
  const auto result = limit_paired_wheel_speeds(current, {0.0, 0.0}, 1.0, 0.034);
  EXPECT_NEAR(result.alpha, 0.034 / 0.4722, 1e-15);
  EXPECT_NEAR(result.applied[0] / current[0], result.applied[1] / current[1], 1e-15);
  EXPECT_LT(result.applied[0], current[0]);
  EXPECT_LT(result.applied[1], current[1]);
  EXPECT_GT(result.applied[0], 0.0);
  EXPECT_GT(result.applied[1], 0.0);
}

TEST(PairedWheelSlew, ReachesBothDesiredSpeedsTogetherAndHasNoDeadbandBranch)
{
  const std::array<double, 2> desired{0.005, -0.004};
  const auto result = limit_paired_wheel_speeds({0.0, 0.0}, desired, 1.0, 0.034);
  EXPECT_EQ(result.applied, desired);
  EXPECT_DOUBLE_EQ(result.alpha, 1.0);
  const auto next = limit_paired_wheel_speeds(result.applied, {0.1, 0.2}, 1.0, 0.034);
  EXPECT_GE(next.applied[0], desired[0]);
  EXPECT_GE(next.applied[1], desired[1]);
  EXPECT_LE(static_cast<long double>(next.applied[0]) - desired[0],
    static_cast<long double>(0.034));
  EXPECT_LE(static_cast<long double>(next.applied[1]) - desired[1],
    static_cast<long double>(0.034));
}

TEST(PairedWheelSlew, DisabledLimitAndZeroTimeHaveExplicitSeparateSemantics)
{
  const std::array<double, 2> current{0.4, -0.2}, desired{-0.1, 0.3};
  EXPECT_EQ(limit_paired_wheel_speeds(current, desired, 0.0, 0.034).applied, desired);
  EXPECT_DOUBLE_EQ(limit_paired_wheel_speeds(current, desired, 0.0, 0.0).alpha, 1.0);
  EXPECT_EQ(limit_paired_wheel_speeds(current, desired, 1.0, 0.0).applied, current);
  EXPECT_DOUBLE_EQ(limit_paired_wheel_speeds(current, desired, 1.0, 0.0).alpha, 0.0);
  EXPECT_EQ(limit_paired_wheel_speeds(current, current, 1.0, 0.034).applied, current);
}

TEST(PairedWheelSlew, RejectsNegativeAndEveryNonfiniteInputEvenWithLimitDisabled)
{
  for (const auto value : {std::numeric_limits<double>::quiet_NaN(),
      std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()})
  {
    EXPECT_THROW(limit_paired_wheel_speeds({value, 0}, {0, 0}, 1, 0.034),
      std::invalid_argument);
    EXPECT_THROW(limit_paired_wheel_speeds({0, value}, {0, 0}, 1, 0.034),
      std::invalid_argument);
    EXPECT_THROW(limit_paired_wheel_speeds({0, 0}, {value, 0}, 0, 0.034),
      std::invalid_argument);
    EXPECT_THROW(limit_paired_wheel_speeds({0, 0}, {0, value}, 0, 0.034),
      std::invalid_argument);
    EXPECT_THROW(limit_paired_wheel_speeds({0, 0}, {0, 0}, value, 0.034),
      std::invalid_argument);
    EXPECT_THROW(limit_paired_wheel_speeds({0, 0}, {0, 0}, 1, value),
      std::invalid_argument);
  }
  EXPECT_THROW(limit_paired_wheel_speeds({0, 0}, {0, 0}, -1, 0.034),
    std::invalid_argument);
  EXPECT_THROW(limit_paired_wheel_speeds({0, 0}, {0, 0}, 1, -0.034),
    std::invalid_argument);
}

TEST(PairedWheelSlew, FiniteExtremesDoNotOverflowDifferenceOrMakeNan)
{
  const double largest = std::numeric_limits<double>::max();
  const auto result = limit_paired_wheel_speeds({largest, -largest}, {-largest, largest},
    largest, 0.25);
  EXPECT_TRUE(std::isfinite(result.alpha));
  for (const auto speed : result.applied) {
    EXPECT_TRUE(std::isfinite(speed));
  }
  EXPECT_NEAR(result.alpha, 0.125, 1e-15);
}

TEST(PairedWheelSlew, RandomPairsHaveExactRimBudgetSharedAlphaAndConvexBodyVelocity)
{
  std::mt19937_64 random(20261017);
  std::uniform_real_distribution<double> speed(-0.4722, 0.4722);
  std::uniform_real_distribution<double> acceleration(0.01, 2.0);
  std::uniform_real_distribution<double> duration(0.0001, 0.2);
  for (unsigned int example = 0; example < 20000; ++example) {
    const std::array<double, 2> current{speed(random), speed(random)};
    const std::array<double, 2> desired{speed(random), speed(random)};
    const double max_accel = acceleration(random), dt = duration(random);
    const auto result = limit_paired_wheel_speeds(current, desired, max_accel, dt);
    ASSERT_GE(result.alpha, 0.0);
    ASSERT_LE(result.alpha, 1.0);
    const long double budget = static_cast<long double>(max_accel) * dt;
    const long double largest = std::max(
      std::abs(static_cast<long double>(desired[0]) - current[0]),
      std::abs(static_cast<long double>(desired[1]) - current[1]));
    EXPECT_LE(static_cast<long double>(result.alpha), std::min(1.0L, budget / largest));
    for (std::size_t wheel = 0; wheel < current.size(); ++wheel) {
      EXPECT_LE(std::abs(static_cast<long double>(result.applied[wheel]) - current[wheel]),
        budget);
      EXPECT_GE(result.applied[wheel], std::min(current[wheel], desired[wheel]));
      EXPECT_LE(result.applied[wheel], std::max(current[wheel], desired[wheel]));
      const double expected = static_cast<double>(std::fma(
          static_cast<long double>(result.alpha),
          static_cast<long double>(desired[wheel]) - current[wheel],
          static_cast<long double>(current[wheel])));
      EXPECT_DOUBLE_EQ(result.applied[wheel], expected);
    }
    for (const double sign : {-1.0, 1.0}) {
      const double actual = result.applied[0] + sign * result.applied[1];
      const double expected = (1 - result.alpha) * (current[0] + sign * current[1]) +
        result.alpha * (desired[0] + sign * desired[1]);
      EXPECT_NEAR(actual, expected, 3e-16);
    }
  }
}

TEST(PairedWheelSlew, IdealNoSlipZeroTargetFitsRetainedGlobalStopEnvelope)
{
  // Command/joint model only: this deliberately does not model body contact,
  // slip or torque tracking. Hold each old speed for a complete 34 ms frame
  // and conservatively add another full frame on top of .16 s reaction.
  constexpr double dt = 0.034;
  for (int linear = -30; linear <= 30; ++linear) {
    for (int angular = -24; angular <= 24; ++angular) {
      const double v = linear / 100.0, w = angular / 20.0;
      std::array<double, 2> current{v - 0.1435 * w, v + 0.1435 * w};
      double path = 0.30 * (0.16 + dt), elapsed = 0.16 + dt;
      unsigned int frames = 0;
      while (current != std::array<double, 2>{0.0, 0.0} && frames < 64) {
        path += std::abs((current[0] + current[1]) / 2) * dt;
        current = limit_paired_wheel_speeds(current, {0.0, 0.0}, 1.0, dt).applied;
        elapsed += dt;
        ++frames;
      }
      EXPECT_LT(frames, 64u);
      EXPECT_LE(path, 0.144);
      EXPECT_LE(elapsed, 0.78);
    }
  }
}

// Native P2A.0 v12 rows; exact binary64 nominal ratios are retained in the
// independent Fraction evidence. A rounded long-double equality is insufficient.
TEST(PairedWheelSlew, ActualZeroTargetNominalRatioCannotRoundOutward)
{
  const auto result = limit_paired_wheel_speeds(
    {0.03870224258609071, 0.05117593092848239}, {0.0, 0.0}, 1.0, 0.034);
  // The true ratio is strictly below 0x1.5428efc955958p-1.
  EXPECT_LE(result.alpha, 0x1.5428efc955957p-1);
  EXPECT_NEAR(result.alpha, 0.6643748219746994, 1e-12);
}

TEST(PairedWheelSlew, ActualMixedTargetNominalRatioCannotRoundOutward)
{
  const auto result = limit_paired_wheel_speeds(
    {0.05503729208154675, 0.05598067674745284},
    {0.20562105263157898, 0.31437894736842104}, 1.0, 0.034);
  // The true ratio is strictly below 0x1.0d79b990149f5p-3.
  EXPECT_LE(result.alpha, 0x1.0d79b990149f4p-3);
  EXPECT_NEAR(result.alpha, 0.13157982798527681, 1e-12);
}

TEST(PairedWheelSlew, FastPathCannotLoseTinyCurrentAcrossTheExactBudgetBoundary)
{
  for (const double sign : {-1.0, 1.0}) {
    const auto result = limit_paired_wheel_speeds(
      {-sign * 1e-300, 0.0}, {sign * 0.034, 0.0}, 1.0, 0.034);
    // Returning desired would move by binary64(0.034) + binary64(1e-300),
    // strictly exceeding budget even though that sum rounds to 0.034 in LD.
    EXPECT_LT(sign * result.applied[0], 0.034);
    EXPECT_GT(sign * result.applied[0], 0.0);
    EXPECT_LT(result.alpha, 1.0);
    EXPECT_NEAR(result.alpha, 1.0, 1e-12);
    EXPECT_DOUBLE_EQ(result.applied[1], 0.0);
  }
}

TEST(PairedWheelSlew, RoundedAppliedStepCannotHideTinyCurrentBeyondBudget)
{
  for (const double sign : {-1.0, 1.0}) {
    const auto result = limit_paired_wheel_speeds(
      {-sign * 1e-300, 0.0}, {sign * 0.068, 0.0}, 1.0, 0.034);
    // The old within-budget LD subtraction also lost the original tiny value.
    EXPECT_LT(sign * result.applied[0], 0.034);
    EXPECT_GT(sign * result.applied[0], 0.0);
    EXPECT_LT(result.alpha, 0.5);
    EXPECT_NEAR(result.alpha, 0.5, 1e-12);
    EXPECT_DOUBLE_EQ(result.applied[1], 0.0);
  }
}
