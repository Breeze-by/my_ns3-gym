#include <gtest/gtest.h>
#include <array>
#include <limits>
#include "multi_robot/mr3_initial_zero_encoder_servo.hpp"

namespace {
using multi_robot::initial_encoder_hold_v1::InitialZeroEncoderServo;
constexpr std::array<double, 2> stopped{0.0, 0.0};

TEST(InitialZeroEncoderReceive, ZeroReceiveDoesNotCountAsActuation)
{
  InitialZeroEncoderServo servo;
  for (unsigned int i = 0; i < 100; ++i) servo.ObserveReceivedTarget(0.0, 0.0);
  EXPECT_EQ(servo.state().rest_samples, 0U);
  EXPECT_FALSE(servo.state().reference_valid);
  auto first = servo.update({0.1, -0.2}, stopped, 0.0, 0.0);
  EXPECT_FALSE(first.reference_valid);
  servo.ObserveReceivedTarget(0.0, 0.0);
  auto second = servo.update({0.10001, -0.20001}, stopped, 0.0, 0.0);
  EXPECT_EQ(second.rest_samples, 2U);
  EXPECT_FALSE(second.reference_valid);
  const std::array<double, 2> capture{0.10002, -0.20002};
  auto third = servo.update(capture, stopped, 0.0, 0.0);
  ASSERT_TRUE(third.reference_valid);
  EXPECT_TRUE(third.captured_this_update);
  EXPECT_EQ(third.reference, capture);
  for (unsigned int i = 0; i < 10; ++i) servo.ObserveReceivedTarget(0.0, 0.0);
  auto later = servo.update({0.10003, -0.20003}, stopped, 0.0, 0.0);
  EXPECT_EQ(later.capture_count, 1U);
  EXPECT_EQ(later.reference, capture);
  EXPECT_LT(later.servo_desired_rim[0], 0.0);
  EXPECT_GT(later.servo_desired_rim[1], 0.0);
}

TEST(InitialZeroEncoderReceive, TransientNonzeroDisarmsBeforeConsumption)
{
  InitialZeroEncoderServo servo;
  servo.update({0.0, 0.0}, stopped, 0.0, 0.0);
  servo.update({0.0, 0.0}, stopped, 0.0, 0.0);
  servo.ObserveReceivedTarget(1e-300, 0.0);
  servo.ObserveReceivedTarget(0.0, 0.0);  // The nonzero target was never consumed.
  const auto result = servo.update({0.2, -0.2}, stopped, 0.0, 0.0);
  EXPECT_FALSE(result.armed);
  EXPECT_FALSE(result.reference_valid);
  EXPECT_FALSE(result.feedback_active);
  EXPECT_EQ(result.capture_count, 0U);
  EXPECT_EQ(result.limited.applied, stopped);
  EXPECT_EQ(result.rest_samples, 0U);
}

TEST(InitialZeroEncoderReceive, PureTurnLocksReferenceUntilFreshObject)
{
  InitialZeroEncoderServo servo;
  const std::array<double, 2> reference{0.01, -0.01};
  for (unsigned int i = 0; i < 3; ++i) servo.update(reference, stopped, 0.0, 0.0);
  servo.ObserveReceivedTarget(0.0, -1e-300);
  for (unsigned int i = 0; i < 10; ++i) servo.ObserveReceivedTarget(0.0, 0.0);
  const std::array<double, 2> qd{0.3, -0.2};
  const auto actual = servo.update({0.2, -0.2}, qd, 0.0, 0.0);
  const std::array<double, 2> current{qd[0] * 0.033, qd[1] * 0.033};
  const auto original = multi_robot::limit_paired_wheel_speeds(current, stopped, 1.0, 0.034);
  EXPECT_FALSE(actual.armed);
  EXPECT_FALSE(actual.feedback_active);
  EXPECT_EQ(actual.capture_count, 1U);
  EXPECT_EQ(actual.reference, reference);
  EXPECT_EQ(actual.limited.applied, original.applied);
  EXPECT_EQ(actual.limited.alpha, original.alpha);
  InitialZeroEncoderServo fresh;
  for (unsigned int i = 0; i < 3; ++i) fresh.update({0.3, -0.3}, stopped, 0.0, 0.0);
  EXPECT_TRUE(fresh.state().armed);
  EXPECT_EQ(fresh.state().capture_count, 1U);
  EXPECT_NE(fresh.state().reference, reference);
}

TEST(InitialZeroEncoderReceive, NonfiniteReceiveDoesNotMutateState)
{
  InitialZeroEncoderServo servo;
  servo.update({0.0, 0.0}, stopped, 0.0, 0.0);
  const auto before = servo.state();
  EXPECT_THROW(servo.ObserveReceivedTarget(std::numeric_limits<double>::infinity(), 0.0),
    std::invalid_argument);
  EXPECT_THROW(servo.ObserveReceivedTarget(0.0, std::numeric_limits<double>::quiet_NaN()),
    std::invalid_argument);
  const auto after = servo.state();
  EXPECT_EQ(after.armed, before.armed);
  EXPECT_EQ(after.reference_valid, before.reference_valid);
  EXPECT_EQ(after.reference, before.reference);
  EXPECT_EQ(after.capture_count, before.capture_count);
  EXPECT_EQ(after.rest_samples, before.rest_samples);
}
}  // namespace
