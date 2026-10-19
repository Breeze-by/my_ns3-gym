// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: BSD-3-Clause
#ifndef MULTI_ROBOT__MR3_DRIVE_FEED_HPP_
#define MULTI_ROBOT__MR3_DRIVE_FEED_HPP_

#include <array>
#include <cfenv>
#include <cfloat>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef __SSE__
#include <xmmintrin.h>
#endif
#include <nlohmann/json.hpp>
#include "multi_robot/mr3_drive_target.hpp"

#if defined(__FAST_MATH__) || (defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ != 0)
#error "MR3 odometry calibration requires no-fast-math compilation"
#endif

namespace multi_robot::drive_feed
{
static_assert(std::numeric_limits<float>::is_iec559 &&
  std::numeric_limits<float>::digits == 24 && sizeof(float) == 4,
  "MR3 odometry conversion requires IEEE binary32 float");
static_assert(std::numeric_limits<double>::is_iec559 &&
  std::numeric_limits<double>::digits == 53 && sizeof(double) == 8 && FLT_EVAL_METHOD == 0,
  "MR3 odometry conversion requires IEEE binary64 without excess precision");

/// Check the actual physics thread without changing its floating-point state.
inline void ValidateConversionEnvironment()
{
  if (std::fegetround() != FE_TONEAREST) {
    throw std::runtime_error("MR3 odometry conversion requires round-to-nearest");
  }
#ifdef __SSE__
  // DAZ and FTZ are separate from the language rounding mode on x86/SSE.
  const auto csr = _mm_getcsr();
  if ((csr & ((1U << 6) | (1U << 15) | _MM_ROUND_MASK)) != _MM_ROUND_NEAREST) {
    throw std::runtime_error("MR3 odometry conversion requires RN without DAZ/FTZ");
  }
#endif
  volatile double tiny_double = std::numeric_limits<double>::denorm_min();
  volatile float tiny_float = std::numeric_limits<float>::denorm_min();
  const double doubled_double = tiny_double + tiny_double;
  const float doubled_float = tiny_float + tiny_float;
  if (doubled_double == 0.0 || doubled_float == 0.0F) {
    throw std::runtime_error("MR3 odometry conversion requires gradual underflow");
  }
}

struct AppliedPair
{
  unsigned int pair_index;
  // Both wheel vectors retain the native order: RIGHT, LEFT.
  std::array<double, 2> current_rim_mps;
  std::array<double, 2> desired_rim_mps;
  std::array<double, 2> applied_rim_mps;
  double alpha;
  double max_acceleration_mps2;
};

inline nlohmann::json Applied(
  const std::string & epoch, const std::string & robot, int64_t source_clock_ns,
  uint64_t actuation_sequence, uint64_t cmd_seq, int64_t dt_ns,
  const nlohmann::json & original_target, const std::vector<AppliedPair> & pairs)
{
  const auto target = ParseDriveTarget(original_target);
  if (target.epoch != epoch || target.robot != robot ||
    target.clock_ns > source_clock_ns || source_clock_ns < 0 ||
    actuation_sequence == 0 || cmd_seq == 0 || dt_ns <= 0 || pairs.empty())
  {
    throw std::invalid_argument("invalid actual applied feed identity/endpoints");
  }
  auto values = nlohmann::json::array();
  for (std::size_t i = 0; i < pairs.size(); ++i) {
    const auto & pair = pairs[i];
    if (pair.pair_index != i || !std::isfinite(pair.alpha) || pair.alpha < 0.0 ||
      pair.alpha > 1.0 || !std::isfinite(pair.max_acceleration_mps2))
    {
      throw std::invalid_argument("invalid applied pair identity/limiter metadata");
    }
    for (const auto & wheel : {pair.current_rim_mps, pair.desired_rim_mps,
        pair.applied_rim_mps})
    {
      for (const double value : wheel) {
        if (!std::isfinite(value)) {
          throw std::invalid_argument("nonfinite applied pair wheel value");
        }
      }
    }
    values.push_back({{"pair_index", pair.pair_index},
      {"current_rim_mps", pair.current_rim_mps}, {"desired_rim_mps", pair.desired_rim_mps},
      {"applied_rim_mps", pair.applied_rim_mps}, {"alpha", pair.alpha},
      {"max_acceleration_mps2", pair.max_acceleration_mps2}});
  }
  return {{"schema", "mr3-drive-applied-v1"}, {"epoch", epoch}, {"robot", robot},
    {"source_clock_ns", source_clock_ns}, {"actuation_sequence", actuation_sequence},
    {"cmd_seq", cmd_seq}, {"dt_ns", dt_ns}, {"target", original_target}, {"pairs", values}};
}

inline nlohmann::json OdometryCalibration(
  const std::string & epoch, const std::string & robot, int64_t source_clock_ns,
  uint64_t publication_sequence, float coefficient_c, float coefficient_s,
  const nlohmann::json & original_odometry)
{
  if (epoch.empty() || robot.empty() || source_clock_ns < 0 || publication_sequence == 0 ||
    !std::isfinite(coefficient_c) || !std::isfinite(coefficient_s) ||
    std::abs(coefficient_c) > 1.0F || std::abs(coefficient_s) > 1.0F ||
    (coefficient_c == 0.0F && coefficient_s == 0.0F))
  {
    throw std::invalid_argument("invalid odometry calibration identity/coefficients");
  }
  const auto & stamp = original_odometry.at("header").at("stamp");
  const auto sec = DriveTargetInteger(stamp.at("sec"), false);
  const auto nsec = DriveTargetInteger(stamp.at("nanosec"), false);
  if (nsec >= 1000000000LL || sec != source_clock_ns / 1000000000LL ||
    nsec != source_clock_ns % 1000000000LL)
  {
    throw std::invalid_argument("calibration must bind the same odometry source");
  }
  // Promote the actually used binary32 values. Never reconstruct from yaw or
  // normalise c/s: c*c+s*s is not assumed to equal one.
  return {{"schema", "mr3-odom-calibration-v1"}, {"epoch", epoch}, {"robot", robot},
    {"source_clock_ns", source_clock_ns}, {"publication_sequence", publication_sequence},
    {"coefficient_c", static_cast<double>(coefficient_c)},
    {"coefficient_s", static_cast<double>(coefficient_s)}, {"odometry", original_odometry},
    {"conversion_contract", "float32-trig-binary64-rn-v1"},
    {"producer_frame", "world-common-model-origin-v1"}};
}
}  // namespace multi_robot::drive_feed
#endif  // MULTI_ROBOT__MR3_DRIVE_FEED_HPP_
