#ifndef SLAM_TOOLBOX__SCAN_SELF_FILTER_HPP_
#define SLAM_TOOLBOX__SCAN_SELF_FILTER_HPP_

#include <cmath>
#include <algorithm>
#include <limits>
#include <vector>

namespace slam_toolbox
{
namespace scan_self_filter
{

// A configured physical chassis interior, in the mapper's base frame.
// Points on the boundary and outside it remain obstacle observations.
inline bool insideBody(
  double range, double angle, double sensor_x, double sensor_y,
  double sensor_yaw, const std::vector<double> & box)
{
  if (box.size() != 4 || !std::isfinite(range) || range <= 0.0 ||
    !std::isfinite(angle) || !std::isfinite(sensor_x) ||
    !std::isfinite(sensor_y) || !std::isfinite(sensor_yaw))
  {
    return false;
  }
  const double x = sensor_x + range * std::cos(angle + sensor_yaw);
  const double y = sensor_y + range * std::sin(angle + sensor_yaw);
  return box[0] < x && x < box[1] && box[2] < y && y < box[3];
}

// Associate a boundary-noise run with an interior return and three matched rays.
// NaN rejection removes a measurement; Karto does not trace it as free space.
inline std::vector<bool> selfReturnMask(
  const std::vector<float> & ranges, double angle_min, double increment,
  double range_min, double range_max, double sensor_x, double sensor_y,
  double sensor_yaw, const std::vector<double> & box, double uncertainty)
{
  std::vector<bool> interior(ranges.size(), false);
  for (size_t i = 0; i < ranges.size(); ++i) {
    interior[i] = ranges[i] > range_min && ranges[i] < range_max &&
      insideBody(ranges[i], angle_min + i * increment, sensor_x, sensor_y, sensor_yaw, box);
  }
  if (box.size() != 4 || !std::isfinite(uncertainty) || uncertainty <= 0.0 ||
    !std::isfinite(increment) || increment == 0.0 ||
    !(box[0] < sensor_x && sensor_x < box[1] && box[2] < sensor_y && sensor_y < box[3]))
  {
    return interior;
  }
  std::vector<bool> band = interior;
  const bool wrap = ranges.size() >= 9 &&
    (ranges.size() - 1) * std::abs(increment) >= 2.0 * std::acos(-1.0) - 2.0 * std::abs(increment);
  for (size_t i = 0; i < ranges.size(); ++i) {
    if (interior[i] || !(ranges[i] > range_min && ranges[i] < range_max)) {
      continue;
    }
    const double angle = angle_min + i * increment + sensor_yaw;
    const double dx = std::cos(angle), dy = std::sin(angle);
    double surface = std::numeric_limits<double>::infinity();
    if (dx != 0.0) {
      surface = std::min(surface, ((dx > 0.0 ? box[1] : box[0]) - sensor_x) / dx);
    }
    if (dy != 0.0) {
      surface = std::min(surface, ((dy > 0.0 ? box[3] : box[2]) - sensor_y) / dy);
    }
    if (!std::isfinite(surface) || std::abs(ranges[i] - surface) > uncertainty) {
      continue;
    }
    band[i] = true;
  }
  std::vector<bool> result = interior;
  size_t start = 0;
  if (wrap) {
    const auto gap = std::find(band.begin(), band.end(), false);
    if (gap != band.end()) {
      start = (std::distance(band.begin(), gap) + 1) % ranges.size();
    }
  }
  size_t processed = 0;
  while (processed < ranges.size()) {
    std::vector<size_t> cluster;
    size_t seeds = 0;
    while (processed < ranges.size()) {
      const size_t index = (start + processed++) % ranges.size();
      if (!band[index]) {
        break;
      }
      cluster.push_back(index);
      seeds += interior[index] ? 1 : 0;
    }
    if (seeds >= 1 && cluster.size() >= 3) {
      for (size_t index : cluster) {
        result[index] = true;
      }
    }
  }
  return result;
}

}  // namespace scan_self_filter
}  // namespace slam_toolbox

#endif  // SLAM_TOOLBOX__SCAN_SELF_FILTER_HPP_
