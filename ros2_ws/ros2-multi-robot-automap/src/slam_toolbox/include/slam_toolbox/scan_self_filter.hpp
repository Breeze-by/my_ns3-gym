#ifndef SLAM_TOOLBOX__SCAN_SELF_FILTER_HPP_
#define SLAM_TOOLBOX__SCAN_SELF_FILTER_HPP_

#include <cmath>
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

}  // namespace scan_self_filter
}  // namespace slam_toolbox

#endif  // SLAM_TOOLBOX__SCAN_SELF_FILTER_HPP_
