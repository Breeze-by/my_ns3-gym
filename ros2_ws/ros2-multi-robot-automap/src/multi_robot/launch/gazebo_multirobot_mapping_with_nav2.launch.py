#!/usr/bin/env python3
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    RegisterEventHandler,
    IncludeLaunchDescription,
    ExecuteProcess,
    OpaqueFunction,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node


def launch_setup(context, *args, **kwargs):
    actions = []

    # ========= Runtime launch arguments =========
    robot_count_cfg = LaunchConfiguration("robot_count")
    use_sim_time = LaunchConfiguration("use_sim_time")
    enable_drive = LaunchConfiguration("enable_drive")
    enable_rviz = LaunchConfiguration("enable_rviz")
    enable_merge_rviz = LaunchConfiguration("enable_merge_rviz")
    enable_gzclient = LaunchConfiguration("enable_gzclient")

    try:
        robot_count = int(robot_count_cfg.perform(context))
    except ValueError:
        robot_count = 2

    # ========= Available robots =========
    # Add more robots here if needed. robot_count will select the first N robots.
    all_robots = [
        {
            "name": "tb1",
            "x_pose": "5.0",
            "y_pose": "4.0",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb2",
            "x_pose": "-4.5",
            "y_pose": "4.0",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb3",
            "x_pose": "6.0",
            "y_pose": "-1.5",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb4",
            "x_pose": "-4.0",
            "y_pose": "-4.5",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
    ]

    robot_count = max(1, min(robot_count, len(all_robots)))
    robots = all_robots[:robot_count]

    print(f"\n[INFO] Requested robot_count = {robot_count}")
    print(f"[INFO] Active robots = {[robot['name'] for robot in robots]}\n")

    # ========= Package paths =========
    multi_robot_share = get_package_share_directory("multi_robot")
    nav_launch_dir = os.path.join(multi_robot_share, "launch", "nav2_bringup")

    my_robot = "turtlebot3_waffle"

    urdf = os.path.join(multi_robot_share, "urdf", my_robot + ".urdf")
    model = os.path.join(multi_robot_share, "models", my_robot, "model.sdf")
    world = os.path.join(multi_robot_share, "worlds", "my_world.world")

    # Keep the original map path style used by this project.
    map_file_path = os.path.join(
        multi_robot_share,
        "../../../../src/multi_robot/maps/turtlebot3_world.yaml",
    )

    remappings = [("/tf", "tf"), ("/tf_static", "tf_static")]

    # ========= Start merge_map and headquarters control =========
    merge_map_launch = ExecuteProcess(
        cmd=[
            "ros2",
            "launch",
            "merge_map",
            "merge_map_launch.py",
            ["robot_count:=", robot_count_cfg],
            ["enable_rviz:=", enable_merge_rviz],
        ],
        output="screen",
    )
    actions.append(merge_map_launch)

    control_node = ExecuteProcess(
        cmd=[
            "ros2",
            "run",
            "multi_robot_exploration",
            "control",
            "--ros-args",
            "-p",
            ["robot_count:=", robot_count_cfg],
        ],
        output="screen",
    )
    actions.append(control_node)

    # ========= Gazebo =========
    gzserver_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("gazebo_ros"),
                "launch",
                "gzserver.launch.py",
            )
        ),
        launch_arguments={"world": world}.items(),
    )
    actions.append(gzserver_cmd)

    gzclient_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("gazebo_ros"),
                "launch",
                "gzclient.launch.py",
            )
        ),
        condition=IfCondition(enable_gzclient),
    )
    actions.append(gzclient_cmd)

    # ========= Spawn robots sequentially =========
    last_spawn_action = None

    for robot in robots:
        robot_name = robot["name"]
        namespace = "/" + robot_name

        params_file = os.path.join(
            multi_robot_share,
            "params",
            f"nav2_params_{robot_name}_0.yaml",
        )

        print(f"Namespace: {namespace}, PARAM Config: {params_file}\n")

        robot_state_publisher = Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            namespace=namespace,
            output="screen",
            parameters=[
                {
                    "use_sim_time": use_sim_time,
                    "publish_frequency": 10.0,
                }
            ],
            remappings=remappings,
            arguments=[urdf],
        )

        joint_state_publisher_node = Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            namespace=namespace,
            name="joint_state_publisher",
            parameters=[{"use_sim_time": use_sim_time}],
            remappings=remappings,
        )

        spawn_robot = Node(
            package="gazebo_ros",
            executable="spawn_entity.py",
            arguments=[
                "-file",
                model,
                "-entity",
                robot_name,
                "-robot_namespace",
                namespace,
                "-x",
                robot["x_pose"],
                "-y",
                robot["y_pose"],
                "-z",
                robot["z_pose"],
                "-R",
                robot["roll"],
                "-P",
                robot["pitch"],
                "-Y",
                robot["yaw"],
            ],
            output="screen",
        )

        bringup_cmd = IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    multi_robot_share,
                    "launch",
                    "nav2_bringup",
                    "bringup_launch.py",
                )
            ),
            launch_arguments={
                "slam": "False",
                "namespace": namespace,
                "use_namespace": "True",
                "map": map_file_path,
                "map_server": "False",
                "params_file": params_file,
                "default_bt_xml_filename": os.path.join(
                    get_package_share_directory("nav2_bt_navigator"),
                    "behavior_trees",
                    "navigate_to_pose_w_replanning_and_recovery.xml",
                ),
                "autostart": "True",
                "use_sim_time": use_sim_time,
                "log_level": "warn",
            }.items(),
        )

        slam_toolbox_node = IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    get_package_share_directory("slam_toolbox"),
                    "launch",
                    "online_async_multirobot_launch.py",
                )
            ),
            launch_arguments={
                "namespace": namespace,
                "use_sim_time": use_sim_time,
            }.items(),
        )

        node_tf_map_to_odom = Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            arguments=[
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                f"{robot_name}/map",
                f"{robot_name}/odom",
            ],
            parameters=[{"use_sim_time": use_sim_time}],
            output="screen",
        )

        robot_actions = [
            robot_state_publisher,
            spawn_robot,
            bringup_cmd,
            joint_state_publisher_node,
            node_tf_map_to_odom,
            slam_toolbox_node,
        ]

        if last_spawn_action is None:
            for action in robot_actions:
                actions.append(action)
        else:
            spawn_robot_event = RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=last_spawn_action,
                    on_exit=robot_actions,
                )
            )
            actions.append(spawn_robot_event)

        last_spawn_action = spawn_robot

    # ========= RViz and optional drive nodes =========
    # Start RViz only after the last robot has been spawned.
    # By default enable_rviz is false to reduce CPU/GPU load.
    if last_spawn_action is not None:
        for robot in robots:
            robot_name = robot["name"]
            namespace = "/" + robot_name

            rviz_config_file = os.path.join(
                multi_robot_share,
                "rviz",
                f"multi_robot_maping_{robot_name}.rviz",
            )

            print(f"Namespace: {namespace}, RViz Config: {rviz_config_file}\n")

            rviz_cmd = IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(nav_launch_dir, "rviz_launch.py")
                ),
                launch_arguments={
                    "use_sim_time": use_sim_time,
                    "namespace": namespace,
                    "use_namespace": "True",
                    "rviz_config": rviz_config_file,
                    "log_level": "warn",
                }.items(),
                condition=IfCondition(enable_rviz),
            )

            drive_turtlebot3 = Node(
                package="turtlebot3_gazebo",
                executable="turtlebot3_drive",
                namespace=namespace,
                output="screen",
                condition=IfCondition(enable_drive),
            )

            post_spawn_event = RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=last_spawn_action,
                    on_exit=[rviz_cmd, drive_turtlebot3],
                )
            )

            actions.append(post_spawn_event)

    return actions


def generate_launch_description():
    ld = LaunchDescription()

    ld.add_action(
        DeclareLaunchArgument(
            "robot_count",
            default_value="2",
            description="Number of robots to spawn. Valid range: 1 to 4.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="true",
            description="Use simulation time.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_drive",
            default_value="false",
            description="Enable turtlebot3_drive teleop-like drive node.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_rviz",
            default_value="false",
            description="Enable per-robot RViz windows. Default false to reduce load.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_merge_rviz",
            default_value="true",
            description="Enable the single global merged-map RViz window.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_gzclient",
            default_value="true",
            description="Enable Gazebo GUI client.",
        )
    )

    ld.add_action(OpaqueFunction(function=launch_setup))

    return ld
