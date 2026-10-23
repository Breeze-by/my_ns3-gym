#ifndef MR3_V58_INITIAL_ZERO_ENCODER_SERVO_V1_HPP_
#define MR3_V58_INITIAL_ZERO_ENCODER_SERVO_V1_HPP_

// Disabled diagnostic candidate. Exact local encoder readings are assumed.
// A wheel-angle reference is not a body-position or safety-certificate anchor.
// This controller provides no body-slip, fixed-R, or physical-safety guarantee.
#include <multi_robot/paired_wheel_slew.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace multi_robot::mr3_v58
{
inline constexpr double WHEEL_RADIUS = 0.033;
inline constexpr double WHEEL_SEPARATION = 0.287;
inline constexpr double MAX_ACCEL = 1.0;
inline constexpr double POSITION_GAIN = 1.0;  // inverse seconds
inline constexpr double MAX_FEEDBACK_RIM = 0.005;
inline constexpr double CAPTURE_MAX_RIM = 0.01;
inline constexpr std::int64_t UPDATE_PERIOD_NS = 34000000;

struct ServoState
{
  bool armed = true;
  bool reference_valid = false;
  std::uint64_t capture_count = 0;
  std::uint64_t rest_samples = 0;
  std::array<double, 2> reference{};
};

struct ServoResult
{
  bool armed = true;
  bool reference_valid = false;
  bool captured_this_update = false;
  bool feedback_active = false;
  std::uint64_t capture_count = 0;
  std::uint64_t rest_samples = 0;
  std::array<double, 2> q{}, qd{}, reference{}, current_rim{};
  std::array<double, 2> body_desired_rim{}, servo_desired_rim{};
  double desired_v = 0.0, desired_w = 0.0;
  std::int64_t dt_ns = UPDATE_PERIOD_NS;
  PairedWheelSlewResult limited{{0.0, 0.0}, 0.0};
};

class InitialZeroEncoderServo
{
public:
  ServoState state() const { return state_; }

  ServoResult update(
    const std::array<double, 2> & q, const std::array<double, 2> & qd,
    double desired_v, double desired_w, std::int64_t dt_ns = UPDATE_PERIOD_NS)
  {
    if (dt_ns != UPDATE_PERIOD_NS || !std::isfinite(desired_v) || !std::isfinite(desired_w)) {
      throw std::invalid_argument("initial encoder hold requires finite body target and actual34ms");
    }
    ServoResult result;
    result.q = q;
    result.qd = qd;
    result.desired_v = desired_v;
    result.desired_w = desired_w;
    result.dt_ns = dt_ns;
    result.body_desired_rim = {
      desired_v + desired_w * WHEEL_SEPARATION / 2.0,
      desired_v - desired_w * WHEEL_SEPARATION / 2.0};
    for (std::size_t i = 0; i < 2; ++i) {
      result.current_rim[i] = qd[i] * WHEEL_RADIUS;
      if (!std::isfinite(q[i]) || !std::isfinite(qd[i]) ||
          !std::isfinite(result.current_rim[i]) || !std::isfinite(result.body_desired_rim[i])) {
        throw std::invalid_argument("initial encoder hold requires finite encoder/derived values");
      }
    }

    // Commit state only after every derived value and the original slew succeed.
    ServoState next = state_;
    const bool zero = desired_v == 0.0 && desired_w == 0.0;
    if (!zero) {
      next.armed = false;  // Includes pure turn and any subnormal nonzero body request.
      next.rest_samples = 0;
    }
    if (next.armed && !next.reference_valid) {
      if (std::max(std::abs(result.current_rim[0]), std::abs(result.current_rim[1])) <= CAPTURE_MAX_RIM) {
        ++next.rest_samples;
      } else {
        next.rest_samples = 0;
      }
      if (next.rest_samples == 3) {
        next.reference = q;  // One capture, no refresh or position unwrapping.
        next.reference_valid = true;
        ++next.capture_count;
        result.captured_this_update = true;
      }
    }
    result.servo_desired_rim = result.body_desired_rim;
    result.feedback_active = next.armed && next.reference_valid;
    if (result.feedback_active) {
      for (std::size_t i = 0; i < 2; ++i) {
        const double feedback = WHEEL_RADIUS * (next.reference[i] - q[i]) * POSITION_GAIN;
        if (!std::isfinite(feedback)) {
          throw std::invalid_argument("initial encoder hold feedback exceeds finite range");
        }
        result.servo_desired_rim[i] = std::clamp(feedback, -MAX_FEEDBACK_RIM, MAX_FEEDBACK_RIM);
      }
    }
    result.limited = limit_paired_wheel_speeds(
      result.current_rim, result.servo_desired_rim, MAX_ACCEL,
      static_cast<double>(dt_ns) / 1000000000.0);
    result.armed = next.armed;
    result.reference_valid = next.reference_valid;
    result.capture_count = next.capture_count;
    result.rest_samples = next.rest_samples;
    result.reference = next.reference;
    state_ = next;
    return result;
  }

private:
  ServoState state_;
};
}  // namespace multi_robot::mr3_v58
#endif
