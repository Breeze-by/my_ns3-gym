#include "slam_toolbox/slam_toolbox_multirobot.hpp"
#include "slam_toolbox/scan_self_filter.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>

namespace slam_toolbox
{

/*****************************************************************************/
MultiRobotSlamToolbox::MultiRobotSlamToolbox(rclcpp::NodeOptions options)
: SlamToolbox(options)
/*****************************************************************************/
{
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.read_only = true;
    const auto box = declare_parameter(
        "scan_self_filter_body_box", std::vector<double>{}, descriptor);
    if (!box.empty() && (box.size() != 4 ||
        !std::all_of(box.begin(), box.end(), [](double v) {return std::isfinite(v);}) ||
        box[0] >= box[1] || box[2] >= box[3]))
    {
        throw std::invalid_argument("scan_self_filter_body_box requires xmin,xmax,ymin,ymax");
    }
    if (!box.empty()) {
        RCLCPP_INFO(get_logger(), "SCAN_SELF_FILTER_CONFIG box=%.9f,%.9f,%.9f,%.9f",
            box[0], box[1], box[2], box[3]);
    }
    // Subscribes to raw laser scan topic
    laser_scan_sub_ = this->create_subscription<sensor_msgs::msg::LaserScan>(
        "/scan", 10, std::bind(&MultiRobotSlamToolbox::laserCallback, this, std::placeholders::_1));
}

/*****************************************************************************/
void MultiRobotSlamToolbox::laserCallback(
  sensor_msgs::msg::LaserScan::ConstSharedPtr scan)
/*****************************************************************************/
{
    // The common transform publisher only emits map->odom after a scan header
    // has been recorded.  Without this, maps update but Nav2 never receives a
    // map frame and remains stuck during lifecycle activation.
    scan_header = scan->header;

    // Process raw laser scans
    Pose2 pose;
    if (!pose_helper_->getOdomPose(pose, scan->header.stamp)) {
        RCLCPP_WARN(get_logger(), "Failed to compute odom pose");
        return;
    }

    LaserRangeFinder * laser = getLaser(scan);
    if (!laser) {
        RCLCPP_WARN(get_logger(), "Failed to create laser device for %s; discarding scan", scan->header.frame_id.c_str());
        return;
    }

    const auto box = get_parameter("scan_self_filter_body_box").as_double_array();
    if (box.empty() || lasers_[scan->header.frame_id].isInverted()) {
        addScan(laser, scan, pose);
        return;
    }

    auto filtered = std::make_shared<sensor_msgs::msg::LaserScan>(*scan);
    const auto offset = laser->GetOffsetPose();
    size_t removed = 0;
    for (size_t i = 0; i < filtered->ranges.size(); ++i) {
        const double range = scan->ranges[i];
        if (range > scan->range_min && range < scan->range_max &&
            scan_self_filter::insideBody(range,
                scan->angle_min + i * static_cast<double>(scan->angle_increment),
                offset.GetX(), offset.GetY(), offset.GetHeading(), box))
        {
            filtered->ranges[i] = std::numeric_limits<float>::quiet_NaN();
            ++removed;
        }
    }
    if (removed) {
        RCLCPP_INFO(get_logger(), "SCAN_SELF_FILTER source=%.9f frame=%s removed=%zu",
            rclcpp::Time(scan->header.stamp).nanoseconds() / 1.e9,
            scan->header.frame_id.c_str(), removed);
        addScan(laser, filtered, pose);
    } else {
        addScan(laser, scan, pose);
    }
}

/*****************************************************************************/
LaserRangeFinder * MultiRobotSlamToolbox::getLaser(
  const sensor_msgs::msg::LaserScan::ConstSharedPtr & scan)
/*****************************************************************************/
{
    const std::string & frame = scan->header.frame_id;
    if (lasers_.find(frame) == lasers_.end()) {
        try {
            lasers_[frame] = laser_assistant_->toLaserMetadata(*scan);
            dataset_->Add(lasers_[frame].getLaser(), true);
        } catch (tf2::TransformException & e) {
            RCLCPP_ERROR(get_logger(), "Failed to compute laser pose[%s], aborting initialization (%s)", frame.c_str(), e.what());
            return nullptr;
        }
    }

    return lasers_[frame].getLaser();
}

/*****************************************************************************/
bool MultiRobotSlamToolbox::deserializePoseGraphCallback(
  const std::shared_ptr<rmw_request_id_t> request_header,
  const std::shared_ptr<slam_toolbox::srv::DeserializePoseGraph::Request> req,
  std::shared_ptr<slam_toolbox::srv::DeserializePoseGraph::Response> resp)
/*****************************************************************************/
{
    if (req->match_type == procType::LOCALIZE_AT_POSE) {
        RCLCPP_WARN(get_logger(), "Requested a localization deserialization in non-localization mode.");
        return false;
    }

    return SlamToolbox::deserializePoseGraphCallback(request_header, req, resp);
}

}  // namespace slam_toolbox
