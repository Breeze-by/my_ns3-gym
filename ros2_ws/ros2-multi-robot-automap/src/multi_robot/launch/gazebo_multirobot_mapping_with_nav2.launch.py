#!/usr/bin/env python3
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    RegisterEventHandler,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    TimerAction,
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
    enable_task_regions = LaunchConfiguration("enable_task_regions")
    enable_status_panel = LaunchConfiguration("enable_status_panel")
    gazebo_seed = LaunchConfiguration("gazebo_seed")
    world_name = LaunchConfiguration("world")
    spawn_timeout = LaunchConfiguration("spawn_timeout")
    auto_save_map = LaunchConfiguration("auto_save_map")
    goal_timeout = LaunchConfiguration("exploration_goal_timeout_sec")
    nav2_ready_timeout = LaunchConfiguration("nav2_ready_timeout_sec")
    enable_task_evaluator = LaunchConfiguration("enable_task_evaluator")
    evaluation_episode_id = LaunchConfiguration("evaluation_episode_id")
    evaluation_output_dir = LaunchConfiguration("evaluation_output_dir")
    evaluation_duration = LaunchConfiguration("evaluation_duration_sec")
    evaluation_coverage = LaunchConfiguration("evaluation_coverage_threshold")
    evaluation_stop_on_target = LaunchConfiguration(
        "evaluation_stop_on_target_found"
    )
    evaluation_stop_on_complete = LaunchConfiguration(
        "evaluation_stop_on_task_complete"
    )
    enable_target_detection = LaunchConfiguration("enable_target_detection")
    enable_rally = LaunchConfiguration("enable_rally")
    target_x = LaunchConfiguration("target_x")
    target_y = LaunchConfiguration("target_y")
    target_max_distance = LaunchConfiguration("target_max_distance_m")
    target_fov = LaunchConfiguration("target_field_of_view_deg")
    target_confirmation_frames = LaunchConfiguration(
        "target_confirmation_frames"
    )
    rally_position_tolerance = LaunchConfiguration(
        "rally_position_tolerance_m"
    )
    rally_linear_tolerance = LaunchConfiguration(
        "rally_linear_tolerance_mps"
    )
    rally_angular_tolerance = LaunchConfiguration(
        "rally_angular_tolerance_radps"
    )
    rally_hold_sec = LaunchConfiguration("rally_hold_sec")
    rally_max_retries = LaunchConfiguration("rally_max_retries")
    enable_battery = LaunchConfiguration("enable_battery")
    battery_capacity = LaunchConfiguration("battery_capacity")
    battery_initial_energy = LaunchConfiguration("battery_initial_energy")
    battery_move_cost = LaunchConfiguration("battery_move_cost_per_m")
    battery_idle_cost = LaunchConfiguration("battery_idle_cost_per_sec")
    battery_safety_margin = LaunchConfiguration(
        "battery_return_safety_margin"
    )
    battery_charge_duration = LaunchConfiguration(
        "battery_charge_duration_sec"
    )
    battery_return_timeout = LaunchConfiguration(
        "battery_return_timeout_sec"
    )
    battery_charge_timeout = LaunchConfiguration(
        "battery_charge_timeout_sec"
    )

    try:
        robot_count = int(robot_count_cfg.perform(context))
    except ValueError:
        robot_count = 2

    # ========= Available robots =========
    # Add more robots here if needed. robot_count will select the first N robots.
    all_robots = [
        {
            "name": "tb1",
            "x_pose": "0.0",
            "y_pose": "-0.45",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb2",
            "x_pose": "0.0",
            "y_pose": "0.45",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb3",
            "x_pose": "0.45",
            "y_pose": "0.0",
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
    merge_map_share = get_package_share_directory("merge_map")
    nav_launch_dir = os.path.join(multi_robot_share, "launch", "nav2_bringup")

    my_robot = "turtlebot3_waffle"

    urdf = os.path.join(multi_robot_share, "urdf", my_robot + ".urdf")
    model = os.path.join(multi_robot_share, "models", my_robot, "model.sdf")
    target_model = os.path.join(
        multi_robot_share, "models", "search_target", "model.sdf"
    )
    world_filename = world_name.perform(context)
    if os.path.basename(world_filename) != world_filename:
        raise ValueError("world must be a filename from multi_robot/worlds")
    world = os.path.join(multi_robot_share, "worlds", world_filename)
    if not os.path.isfile(world):
        raise ValueError(f"world does not exist: {world_filename}")

    # Keep the original map path style used by this project.
    map_file_path = os.path.join(
        multi_robot_share,
        "../../../../src/multi_robot/maps/turtlebot3_world.yaml",
    )

    remappings = [("/tf", "tf"), ("/tf_static", "tf_static")]

    # ========= Start merge_map and headquarters control =========
    merge_map_node = Node(
        package="merge_map",
        executable="merge_map",
        name="merge_map",
        parameters=[
            {
                "frame_id": "map",
                "output_topic": "/merge_map",
                "robot_count": robot_count_cfg,
                "use_sim_time": use_sim_time,
            }
        ],
        output="screen",
    )
    actions.append(merge_map_node)

    merge_rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="merge_map_rviz",
        output="screen",
        arguments=[
            "-d",
            os.path.join(merge_map_share, "config", "map_merge_tb1_tb2.rviz"),
        ],
        parameters=[{"use_sim_time": use_sim_time}],
        condition=IfCondition(enable_merge_rviz),
    )
    actions.append(merge_rviz)

    control_node = Node(
        package="multi_robot_exploration",
        executable="control",
        name="headquarters_control",
        parameters=[
            {
                "robot_count": robot_count_cfg,
                "auto_save_map": auto_save_map,
                "use_sim_time": use_sim_time,
                "goal_timeout_sec": goal_timeout,
                "enable_rally": enable_rally,
                "enable_battery": enable_battery,
                "rally_position_tolerance_m": rally_position_tolerance,
                "rally_linear_tolerance_mps": rally_linear_tolerance,
                "rally_angular_tolerance_radps": rally_angular_tolerance,
                "rally_hold_sec": rally_hold_sec,
                "rally_max_retries": rally_max_retries,
            }
        ],
        output="screen",
    )

    nav2_ready_gate = Node(
        package="multi_robot_exploration",
        executable="nav2_ready_gate",
        name="nav2_ready_gate",
        parameters=[
            {
                "robot_count": robot_count_cfg,
                "timeout_sec": nav2_ready_timeout,
            }
        ],
        output="screen",
    )

    task_evaluator = Node(
        package="multi_robot_exploration",
        executable="task_evaluator",
        name="task_evaluator",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "robot_count": robot_count_cfg,
                "episode_id": evaluation_episode_id,
                "world_file": world,
                "gazebo_seed": gazebo_seed,
                "output_dir": evaluation_output_dir,
                "max_duration_sec": evaluation_duration,
                "coverage_threshold": evaluation_coverage,
                "stop_on_target_found": evaluation_stop_on_target,
                "stop_on_task_complete": evaluation_stop_on_complete,
            }
        ],
        output="screen",
        condition=IfCondition(enable_task_evaluator),
    )

    target_detector = Node(
        package="multi_robot_exploration",
        executable="target_detector",
        name="target_detector",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "robot_count": robot_count_cfg,
                "world_file": world,
                "target_model": "search_target",
                "max_distance_m": target_max_distance,
                "field_of_view_deg": target_fov,
                "confirmation_frames": target_confirmation_frames,
            }
        ],
        output="screen",
        condition=IfCondition(enable_target_detection),
    )

    # ========= Gazebo =========
    gzserver_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("gazebo_ros"),
                "launch",
                "gzserver.launch.py",
            )
        ),
        launch_arguments={"world": world, "seed": gazebo_seed}.items(),
    )
    actions.append(gzserver_cmd)

    actions.append(
        Node(
            package="multi_robot_exploration",
            executable="task_visualizer",
            name="task_visualizer",
            parameters=[
                {
                    "use_sim_time": use_sim_time,
                    "robot_count": robot_count_cfg,
                    "charge_xs": [
                        float(robot["x_pose"]) for robot in robots
                    ],
                    "charge_ys": [
                        float(robot["y_pose"]) for robot in robots
                    ],
                    "target_x": target_x,
                    "target_y": target_y,
                    "target_radius_m": target_max_distance,
                    "show_target_region": enable_target_detection,
                }
            ],
            output="screen",
            condition=IfCondition(enable_task_regions),
        )
    )

    actions.append(
        Node(
            package="multi_robot_exploration",
            executable="robot_status_panel",
            name="robot_status_panel",
            parameters=[
                {
                    "use_sim_time": use_sim_time,
                    "robot_count": robot_count_cfg,
                }
            ],
            output="screen",
            condition=IfCondition(enable_status_panel),
        )
    )

    actions.append(
        Node(
            package="gazebo_ros",
            executable="spawn_entity.py",
            arguments=[
                "-file",
                target_model,
                "-entity",
                "search_target",
                "-timeout",
                spawn_timeout,
                "-x",
                target_x,
                "-y",
                target_y,
                "-z",
                "0.5",
            ],
            output="screen",
            condition=IfCondition(enable_target_detection),
        )
    )

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
    nav_bringups = []
    battery_nodes = []

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
                "-timeout",
                spawn_timeout,
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
                os.path.join(nav_launch_dir, "bringup_launch.py")
            ),
            launch_arguments={
                # SLAM is started below with the project's multi-robot launch.
                # Keep this true so Nav2 does not also start AMCL and publish a
                # competing map->odom transform while the map is being built.
                "slam": "True",
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

        robot_actions = [
            robot_state_publisher,
            spawn_robot,
            joint_state_publisher_node,
            slam_toolbox_node,
        ]
        battery_nodes.append(
            Node(
                package="multi_robot_exploration",
                executable="battery_manager",
                namespace=namespace,
                name="battery_manager",
                parameters=[
                    {
                        "use_sim_time": use_sim_time,
                        "robot_name": robot_name,
                        "charge_x": float(robot["x_pose"]),
                        "charge_y": float(robot["y_pose"]),
                        "capacity": battery_capacity,
                        "initial_energy": battery_initial_energy,
                        "move_cost_per_m": battery_move_cost,
                        "idle_cost_per_sec": battery_idle_cost,
                        "return_safety_margin": battery_safety_margin,
                        "charge_duration_sec": battery_charge_duration,
                        "return_timeout_sec": battery_return_timeout,
                        "charge_timeout_sec": battery_charge_timeout,
                    }
                ],
                output="screen",
                condition=IfCondition(enable_battery),
            )
        )

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

        nav_bringups.append(bringup_cmd)

        last_spawn_action = spawn_robot

    # ========= RViz and optional drive nodes =========
    # Start RViz only after the last robot has been spawned.
    # By default enable_rviz is false to reduce CPU/GPU load.
    if last_spawn_action is not None:
        staggered_nav = [
            TimerAction(
                period=10.0 + 60.0 * index,
                actions=[bringup],
            )
            for index, bringup in enumerate(nav_bringups)
        ]
        staggered_nav.append(nav2_ready_gate)
        actions.append(
            RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=last_spawn_action,
                    on_exit=staggered_nav,
                )
            )
        )

        def start_control_when_ready(event, context):
            if event.returncode == 0:
                return [
                    LogInfo(msg="Nav2 ready; starting cooperative exploration."),
                    control_node,
                    *battery_nodes,
                    target_detector,
                    task_evaluator,
                ]
            return [
                LogInfo(
                    msg=(
                        "ERROR: Nav2 readiness failed; cooperative exploration "
                        "was not started."
                    )
                )
            ]

        actions.append(
            RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=nav2_ready_gate,
                    on_exit=start_control_when_ready,
                )
            )
        )

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
            "world",
            default_value="my_world.world",
            description="World filename installed by the multi_robot package.",
        )
    )

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

    ld.add_action(
        DeclareLaunchArgument(
            "enable_task_regions",
            default_value="true",
            description="Draw start, charging, detection, and rally regions.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_status_panel",
            default_value="true",
            description="Open the live per-robot operator status panel.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "gazebo_seed",
            default_value="1",
            description="Gazebo random seed used for repeatable runs.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "spawn_timeout",
            default_value="90.0",
            description="Seconds each robot may wait for Gazebo spawn services.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "auto_save_map",
            default_value="true",
            description="Allow headquarters to save merged maps.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "exploration_goal_timeout_sec",
            default_value="60.0",
            description="Simulated seconds before canceling a stalled Nav2 goal.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "nav2_ready_timeout_sec",
            default_value="180.0",
            description="Wall seconds to wait for every Nav2 action server.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_task_evaluator",
            default_value="false",
            description="Record task and ground-truth metrics.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_episode_id",
            default_value="episode",
            description="Identifier used for evaluator CSV and JSON files.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_output_dir",
            default_value="/tmp/multi_robot_evaluation",
            description="Directory for evaluator CSV and JSON files.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_duration_sec",
            default_value="0.0",
            description="Simulation seconds before a timeout result; 0 waits for shutdown.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_coverage_threshold",
            default_value="0.0",
            description="Correct-free coverage ratio that completes exploration.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_stop_on_target_found",
            default_value="false",
            description="End evaluator successfully when a target is confirmed.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_stop_on_task_complete",
            default_value="false",
            description="End evaluator successfully only after COMPLETE.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_target_detection",
            default_value="false",
            description="Spawn and detect the P2 simulation target.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_rally",
            default_value="false",
            description="Enable P2B rally after target confirmation.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "target_x", default_value="-4.0", description="Target world x."
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "target_y", default_value="4.0", description="Target world y."
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "target_max_distance_m",
            default_value="3.0",
            description="Maximum simulation detection distance.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "target_field_of_view_deg",
            default_value="90.0",
            description="Horizontal simulation camera field of view.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "target_confirmation_frames",
            default_value="3",
            description="Consecutive visible frames required for FOUND.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "rally_position_tolerance_m",
            default_value="0.35",
            description="Maximum final rally position error.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "rally_linear_tolerance_mps",
            default_value="0.05",
            description="Maximum final rally linear speed.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "rally_angular_tolerance_radps",
            default_value="0.10",
            description="Maximum final rally angular speed.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "rally_hold_sec",
            default_value="5.0",
            description="Simulated seconds all robots must remain stable.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "rally_max_retries",
            default_value="2",
            description="Retries after an initial failed rally goal.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_battery",
            default_value="true",
            description="Enable per-robot P2C energy and charging managers.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_capacity",
            default_value="100.0",
            description="Full battery energy units.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_initial_energy",
            default_value="100.0",
            description="Initial energy units for every active robot.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_move_cost_per_m",
            default_value="1.0",
            description="Energy consumed per traveled metre.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_idle_cost_per_sec",
            default_value="0.02",
            description="Energy consumed per elapsed simulation second.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_return_safety_margin",
            default_value="5.0",
            description="Energy reserve retained beyond estimated return cost.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_charge_duration_sec",
            default_value="10.0",
            description="Stable simulated seconds required to recharge.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_return_timeout_sec",
            default_value="120.0",
            description="Maximum simulated seconds allowed for a return.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "battery_charge_timeout_sec",
            default_value="60.0",
            description="Maximum simulated seconds allowed at a charger.",
        )
    )

    ld.add_action(OpaqueFunction(function=launch_setup))

    return ld
