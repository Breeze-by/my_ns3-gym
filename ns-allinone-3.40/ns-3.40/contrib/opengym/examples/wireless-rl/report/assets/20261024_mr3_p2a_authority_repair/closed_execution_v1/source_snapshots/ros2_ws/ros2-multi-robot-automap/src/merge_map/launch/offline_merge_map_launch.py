import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    TimerAction,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def lifecycle_action(node_name, transition, delay):
    return TimerAction(
        period=delay,
        actions=[
            LogInfo(msg=f"{transition.capitalize()} {node_name}"),
            ExecuteProcess(
                cmd=["ros2", "lifecycle", "set", f"/{node_name}", transition],
                output="screen",
            ),
        ],
    )


def launch_setup(context, *args, **kwargs):
    robot_count = int(LaunchConfiguration("robot_count").perform(context))
    maps_directory = LaunchConfiguration("maps_directory").perform(context)
    frame_id = LaunchConfiguration("frame_id").perform(context)
    if not os.path.isdir(maps_directory):
        raise ValueError(f"Maps directory '{maps_directory}' does not exist")

    map_files = sorted(
        name for name in os.listdir(maps_directory) if name.endswith(".yaml")
    )
    if len(map_files) != robot_count:
        raise ValueError(
            f"Expected {robot_count} map files, found {len(map_files)}"
        )

    actions = [LogInfo(msg=f"Loading offline maps: {', '.join(map_files)}")]
    for index, map_file in enumerate(map_files):
        node_name = f"map_server_{index + 1}"
        actions.extend(
            [
                Node(
                    package="nav2_map_server",
                    executable="map_server",
                    name=node_name,
                    output="screen",
                    parameters=[
                        {
                            "frame_id": frame_id,
                            "topic_name": f"tb{index + 1}/map",
                            "use_sim_time": False,
                            "yaml_filename": os.path.join(
                                maps_directory, map_file
                            ),
                        }
                    ],
                ),
                lifecycle_action(node_name, "configure", 2.0),
                lifecycle_action(node_name, "activate", 5.0),
            ]
        )

    actions.append(
        Node(
            package="merge_map",
            executable="offline_merge_map",
            name="offline_merge_map",
            output="screen",
            parameters=[
                {"frame_id": frame_id},
                {"output_topic": "/map"},
                {"robot_count": robot_count},
            ],
        )
    )
    rviz_file = os.path.join(
        get_package_share_directory("merge_map"),
        "config",
        "offline_merge_map.rviz",
    )
    actions.append(
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            output="screen",
            arguments=["-d", rviz_file],
        )
    )
    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_count", default_value="2"),
            DeclareLaunchArgument("maps_directory"),
            DeclareLaunchArgument("frame_id", default_value="map"),
            OpaqueFunction(function=launch_setup),
        ]
    )
