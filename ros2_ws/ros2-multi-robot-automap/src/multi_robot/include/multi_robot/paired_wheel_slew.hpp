#ifndef MULTI_ROBOT__PAIRED_WHEEL_SLEW_HPP_
#define MULTI_ROBOT__PAIRED_WHEEL_SLEW_HPP_

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace multi_robot
{

struct PairedWheelSlewResult
{
  std::array<double, 2> applied;
  double alpha;
};

// Both wheels advance by the same fraction from current joint rim feedback.
// There is no retained instruction/integrator state. max_accel == 0 preserves
// the driver's disabled-limit semantics; otherwise sim_dt == 0 cannot advance.
inline PairedWheelSlewResult limit_paired_wheel_speeds(
  const std::array<double, 2> & current, const std::array<double, 2> & desired,
  double max_accel, double sim_dt)
{
  if (!std::isfinite(max_accel) || !std::isfinite(sim_dt) || max_accel < 0 || sim_dt < 0) {
    throw std::invalid_argument("wheel slew requires finite nonnegative acceleration/time");
  }
  for (std::size_t i = 0; i < current.size(); ++i) {
    if (!std::isfinite(current[i]) || !std::isfinite(desired[i])) {
      throw std::invalid_argument("wheel slew requires finite current/desired rim speeds");
    }
  }
  if (max_accel == 0) {
    return {desired, 1.0};
  }
  if (sim_dt == 0) {
    return {current, 0.0};
  }
  const std::array<long double, 2> delta{
    static_cast<long double>(desired[0]) - current[0],
    static_cast<long double>(desired[1]) - current[1]};
  const long double budget = static_cast<long double>(max_accel) * sim_dt;
  const long double largest = std::max(std::abs(delta[0]), std::abs(delta[1]));
  if (!std::isfinite(budget) || !std::isfinite(largest)) {
    throw std::invalid_argument("wheel slew arithmetic exceeds finite range");
  }
  if (largest <= budget) {
    return {desired, 1.0};
  }
  const auto at = [&](double alpha) {
      return PairedWheelSlewResult{{
        static_cast<double>(std::fma(static_cast<long double>(alpha), delta[0],
          static_cast<long double>(current[0]))),
        static_cast<double>(std::fma(static_cast<long double>(alpha), delta[1],
          static_cast<long double>(current[1])))}, alpha};
    };
  const auto within_budget = [&](const PairedWheelSlewResult & result) {
      return std::abs(static_cast<long double>(result.applied[0]) - current[0]) <= budget &&
             std::abs(static_cast<long double>(result.applied[1]) - current[1]) <= budget;
    };
  const long double nominal = budget / largest;
  double high = static_cast<double>(nominal);
  if (static_cast<long double>(high) > nominal) {
    high = std::nextafter(high, 0.0);
  }
  auto result = at(high);
  if (within_budget(result)) {
    return result;
  }
  // Round inward if binary64 output rounding would exceed either wheel's
  // exact acceleration budget. The same alpha still drives both wheels.
  double low = 0.0;
  for (unsigned int iteration = 0; iteration < 64; ++iteration) {
    const double middle = low + (high - low) / 2;
    if (middle == low || middle == high) {
      break;
    }
    if (within_budget(at(middle))) {
      low = middle;
    } else {
      high = middle;
    }
  }
  return at(low);
}

}  // namespace multi_robot

#endif  // MULTI_ROBOT__PAIRED_WHEEL_SLEW_HPP_
