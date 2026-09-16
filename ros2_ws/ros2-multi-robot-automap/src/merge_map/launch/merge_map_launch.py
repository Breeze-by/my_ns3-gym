import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    rviz_file = os.path.join(
        get_package_share_directory("merge_map"),
        "config",
        "map_merge_tb1_tb2.rviz",
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "frame_id",
                default_value="map",
                description="Frame ID for the merged map",
            ),
            DeclareLaunchArgument(
                "output_topic",
                default_value="/merge_map",
                description="Topic used to publish the merged map",
            ),
            DeclareLaunchArgument(
                "robot_count",
                default_value="3",
                description="Number of robots",
            ),
            DeclareLaunchArgument(
                "enable_rviz",
                default_value="true",
                description="Start one global RViz window for the merged map",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="rviz2",
                output="screen",
                arguments=["-d", rviz_file],
                parameters=[{"use_sim_time": True}],
                condition=IfCondition(LaunchConfiguration("enable_rviz")),
            ),
            Node(
                package="merge_map",
                executable="merge_map",
                name="merge_map",
                output="screen",
                parameters=[
                    {"frame_id": LaunchConfiguration("frame_id")},
                    {"output_topic": LaunchConfiguration("output_topic")},
                    {"robot_count": LaunchConfiguration("robot_count")},
                    {"use_sim_time": True},
                ],
            ),
        ]
    )
