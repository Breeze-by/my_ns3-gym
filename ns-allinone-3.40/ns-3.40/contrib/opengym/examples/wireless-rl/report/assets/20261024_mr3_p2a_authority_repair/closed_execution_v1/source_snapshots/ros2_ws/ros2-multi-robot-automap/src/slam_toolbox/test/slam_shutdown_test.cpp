// Copyright 2026 MR3 contributors
// SPDX-License-Identifier: Apache-2.0

#include <memory>
#include <string>

#include "gtest/gtest.h"
#include "slam_toolbox/slam_toolbox_multirobot.hpp"

namespace
{

class ShutdownProbe : public slam_toolbox::MultiRobotSlamToolbox
{
public:
  explicit ShutdownProbe(const rclcpp::NodeOptions & options)
  : MultiRobotSlamToolbox(options) {}

  void registerLaser(const std::string & name)
  {
    // Exercise the real Dataset/SensorManager destruction path without scans,
    // Gazebo, navigation, sensor publication or any training process.
    dataset_->Add(karto::LaserRangeFinder::CreateLaserRangeFinder(
        karto::LaserRangeFinder_Custom, karto::Name(name)));
  }

  bool scanCallbacksPresent() const
  {
    return tfL_ && scan_filter_ && scan_filter_sub_;
  }

  bool stopCallbacksAndCheckReleased()
  {
    stopScanCallbacks();
    return !tfL_ && !scan_filter_ && !scan_filter_sub_;
  }
};

TEST(SlamShutdown, ConfiguredOwnerAndRegisteredSensorsAreReleasedBeforeProcessExit)
{
  for (int episode = 0; episode < 3; ++episode) {
    rclcpp::init(0, nullptr);
    rclcpp::NodeOptions options;
    options.parameter_overrides({
      rclcpp::Parameter("map_update_interval", .01),
      rclcpp::Parameter("transform_publish_period", .01)});
    auto node = std::make_shared<ShutdownProbe>(options);
    node->configure();
    const std::string sensor_name = "mr3_shutdown_probe_" + std::to_string(episode);
    node->registerLaser(sensor_name);
    ASSERT_NE(karto::SensorManager::GetInstance()->GetSensorByName(
        karto::Name(sensor_name)), nullptr);
    std::weak_ptr<ShutdownProbe> weak = node;

    rclcpp::shutdown();
    node.reset();

    // An owned helper retaining its owner prevents this destructor (including
    // joining the map/TF threads and unregistering the sensor) from running.
    EXPECT_TRUE(weak.expired()) << "owned SLAM helpers retained their node";
    EXPECT_THROW(karto::SensorManager::GetInstance()->GetSensorByName(
        karto::Name(sensor_name)), karto::Exception);
  }
}

TEST(SlamShutdown, ScanListenerAndFilterStopIdempotentlyWhileContextIsLive)
{
  rclcpp::init(0, nullptr);
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("map_update_interval", .01),
    rclcpp::Parameter("transform_publish_period", .01)});
  auto node = std::make_shared<ShutdownProbe>(options);
  node->configure();
  EXPECT_TRUE(node->scanCallbacksPresent());
  EXPECT_TRUE(rclcpp::ok());
  EXPECT_TRUE(node->stopCallbacksAndCheckReleased());
  EXPECT_TRUE(rclcpp::ok());
  EXPECT_TRUE(node->stopCallbacksAndCheckReleased());
  std::weak_ptr<ShutdownProbe> weak = node;
  rclcpp::shutdown();
  node.reset();
  EXPECT_TRUE(weak.expired());
}

}  // namespace
