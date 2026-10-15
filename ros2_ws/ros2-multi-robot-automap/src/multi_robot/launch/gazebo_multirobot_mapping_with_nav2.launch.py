#!/usr/bin/env python3
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    RegisterEventHandler,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


def launch_setup(context, *args, **kwargs):
    actions = []

    # ========= Runtime launch arguments =========
    robot_count_cfg = LaunchConfiguration("robot_count")
    use_sim_time = LaunchConfiguration("use_sim_time")
    enable_drive = LaunchConfiguration("enable_drive")
    enable_rviz = LaunchConfiguration("enable_rviz")
    enable_merge_rviz = LaunchConfiguration("enable_merge_rviz")
    enable_gzclient = LaunchConfiguration("enable_gzclient")
    gazebo_seed = LaunchConfiguration("gazebo_seed")
    world_name = LaunchConfiguration("world")
    spawn_timeout = LaunchConfiguration("spawn_timeout")
    auto_save_map = LaunchConfiguration("auto_save_map")
    goal_timeout = LaunchConfiguration("exploration_goal_timeout_sec")
    response_timeout = LaunchConfiguration("navigation_response_timeout_sec")
    cancel_timeout = LaunchConfiguration("navigation_cancel_timeout_sec")
    nav2_ready_timeout = LaunchConfiguration("nav2_ready_timeout_sec")
    enable_task_evaluator = LaunchConfiguration("enable_task_evaluator")
    evaluation_episode_id = LaunchConfiguration("evaluation_episode_id")
    evaluation_output_dir = LaunchConfiguration("evaluation_output_dir")
    evaluation_duration = LaunchConfiguration("evaluation_duration_sec")
    evaluation_coverage = LaunchConfiguration("evaluation_coverage_threshold")
    evaluation_contract = LaunchConfiguration("evaluation_contract_path")
    stop_on_evaluation = LaunchConfiguration("stop_on_evaluation_complete")

    try:
        robot_count = int(robot_count_cfg.perform(context))
    except ValueError:
        raise ValueError("robot_count must be an integer between 1 and 4") from None

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
            "x_pose": "-0.45",
            "y_pose": "0.0",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
    ]

    if not 1 <= robot_count <= len(all_robots):
        raise ValueError("robot_count must be an integer between 1 and 4")
    robots = all_robots[:robot_count]
    execution_mode = LaunchConfiguration("execution_mode").perform(context)
    if execution_mode not in ("baseline", "adapter"):
        raise ValueError("execution_mode must be baseline or adapter")
    adapter_mode = execution_mode == "adapter"
    if adapter_mode and robot_count != 3:
        raise ValueError("MR3 adapter requires robot_count=3")
    if adapter_mode and IfCondition(enable_drive).evaluate(context):
        raise ValueError("MR3 adapter requires enable_drive=false")
    episode_epoch = LaunchConfiguration("mr3_episode_epoch")

    print(f"\n[INFO] Requested robot_count = {robot_count}")
    print(f"[INFO] Active robots = {[robot['name'] for robot in robots]}\n")

    # ========= Package paths =========
    multi_robot_share = get_package_share_directory("multi_robot")
    model_path = os.path.join(multi_robot_share, "models")
    existing_model_path = os.environ.get("GAZEBO_MODEL_PATH", "")
    actions.append(SetEnvironmentVariable(
        "GAZEBO_MODEL_PATH",
        os.pathsep.join(path for path in (model_path, existing_model_path) if path),
    ))
    merge_map_share = get_package_share_directory("merge_map")
    nav_launch_dir = os.path.join(multi_robot_share, "launch", "nav2_bringup")

    my_robot = "turtlebot3_waffle"

    urdf = os.path.join(multi_robot_share, "urdf", my_robot + ".urdf")
    model = os.path.join(multi_robot_share, "models", my_robot, "model.sdf")
    world_filename = world_name.perform(context)
    if os.path.basename(world_filename) != world_filename:
        raise ValueError("world must be a filename from multi_robot/worlds")
    world = os.path.join(multi_robot_share, "worlds", world_filename)
    if not os.path.isfile(world):
        raise ValueError(f"world does not exist: {world_filename}")

    map_file_path = os.path.join(multi_robot_share, "maps", "turtlebot3_world.yaml")

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
                "robot_count": robot_count,
                "use_sim_time": use_sim_time,
            }
        ],
        output="screen",
    )
    if adapter_mode:
        actions.append(Node(
            package="multi_robot_exploration", executable="mr3_information",
            name="mr3_information", output="screen",
            parameters=[{"use_sim_time": use_sim_time, "robot_count": 3,
                         "episode_epoch": episode_epoch, "tf_validity_lead_sec": .2}],
        ))
    else:
        actions.append(merge_map_node)
    if evaluation_contract.perform(context):
        contact_reducer = Node(
            package="multi_robot", executable="mr3_contact_reducer",
            name="mr3_contact_reducer", output="screen",
            parameters=[{"use_sim_time": use_sim_time}],
        )
        actions.append(contact_reducer)
        actions.append(RegisterEventHandler(OnProcessExit(
            target_action=contact_reducer,
            on_exit=lambda event, event_context: (
                [EmitEvent(event=Shutdown(reason="Contact reducer exited"))]
                if not event_context.is_shutdown else []
            ),
        )))
    actions.append(Node(
        package="multi_robot_exploration", executable="peer_obstacles",
        name="peer_obstacles", output="screen",
        parameters=[{"robot_count": robot_count, "use_sim_time": use_sim_time,
                     "task_release_start": adapter_mode,
                     "tf_source_lead_sec": .2 if adapter_mode else 0.}],
        remappings=([
            (f"/{robot['name']}/{topic}", f"/mr3/received/{robot['name']}/{topic}")
            for robot in robots for topic in ("odom", "tf")
        ] if adapter_mode else []),
    ))

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
        remappings=([("/merge_map", "/mr3/received/map")] if adapter_mode else []),
    )
    actions.append(merge_rviz)

    control_node = Node(
        package="multi_robot_exploration",
        executable="mr3_adapter" if adapter_mode else "control",
        name="mr3_adapter" if adapter_mode else "headquarters_control",
        parameters=[
            {
                "robot_count": robot_count,
                "auto_save_map": auto_save_map,
                "use_sim_time": use_sim_time,
                "goal_timeout_sec": goal_timeout,
                "navigation_response_timeout_sec": response_timeout,
                "navigation_cancel_timeout_sec": cancel_timeout,
                "require_task_monitor_ready": bool(evaluation_contract.perform(context)),
                **({"episode_epoch": episode_epoch,
                    "audit_path": LaunchConfiguration("mr3_audit_path")} if adapter_mode else {}),
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
                "robot_count": robot_count,
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
                "robot_count": robot_count,
                "episode_id": evaluation_episode_id,
                "world_file": world,
                "gazebo_seed": gazebo_seed,
                "output_dir": evaluation_output_dir,
                "max_duration_sec": evaluation_duration,
                "coverage_threshold": evaluation_coverage,
                "task_contract_path": evaluation_contract,
            }
        ],
        output="screen",
        condition=IfCondition(enable_task_evaluator),
        remappings=([("/merge_map", "/mr3/received/map")] if adapter_mode else []),
    )
    # ========= Gazebo =========
    server_state = {
        "started": None, "environment": None, "exited": False, "stopping": False,
        "server_returncode": None, "stop_cli_returncode": None,
    }

    def remember_gzserver(event, event_context):
        if not event.cmd or os.path.basename(event.cmd[0]) != "gzserver" or world not in event.cmd:
            return []
        if server_state["started"] is not None:
            return [
                LogInfo(msg="ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR ambiguous_owned_server"),
                EmitEvent(event=Shutdown(reason="Ambiguous owned Gazebo server")),
            ]
        server_state["started"] = event
        server_state["environment"] = dict(
            event_context.environment if event.env is None else event.env
        )
        return [LogInfo(msg=(
            f"Owned Gazebo server {event.process_name} started with pid={event.pid}"
        ))]

    def owned_gzserver_exited(event, event_context):
        started = server_state["started"]
        if started is None or not (
            event.action is started.action and event.pid == started.pid
            and event.process_name == started.process_name
        ):
            return []
        server_state["exited"] = True
        server_state["server_returncode"] = event.returncode
        if not server_state["stopping"] and not event_context.is_shutdown:
            return [
                LogInfo(msg=(
                    "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR "
                    f"server_exited_before_evaluation exit_code={event.returncode}"
                )),
                EmitEvent(event=Shutdown(reason="Gazebo exited before evaluation completion")),
            ]
        result = []
        if event.returncode != 0:
            result.append(LogInfo(msg=(
                f"ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exit_code={event.returncode}"
            )))
        if not event_context.is_shutdown and (
            event.returncode != 0
            or (server_state["stopping"] and server_state["stop_cli_returncode"] == 0)
        ):
            result.append(EmitEvent(event=Shutdown(
                reason="Owned Gazebo server exited after evaluation"
            )))
        return result

    def native_stop_timeout(event_context):
        if event_context.is_shutdown or (
            server_state["server_returncode"] == 0 and server_state["stop_cli_returncode"] == 0
        ):
            return []
        reason = "stop_cli_exit" if server_state["exited"] else "server_exit"
        return [
            LogInfo(msg=f"ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR {reason}_timeout_10_wall_sec"),
            EmitEvent(event=Shutdown(reason="Gazebo native stop timed out")),
        ]

    def native_stop_cli_exited(event, event_context):
        server_state["stop_cli_returncode"] = event.returncode
        result = []
        if event.returncode != 0:
            result.append(LogInfo(msg=(
                f"ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR stop_cli_exit_code={event.returncode}"
            )))
        if not event_context.is_shutdown and (
            event.returncode != 0 or server_state["server_returncode"] == 0
        ):
            result.append(EmitEvent(event=Shutdown(reason="Gazebo native stop completed")))
        return result

    def evaluation_finished(event, event_context):
        if (
            not IfCondition(stop_on_evaluation).evaluate(event_context)
            or event_context.is_shutdown or server_state["stopping"]
        ):
            return []
        server_state["stopping"] = True
        if server_state["started"] is None:
            return [
                LogInfo(msg="ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR owned_server_not_started"),
                EmitEvent(event=Shutdown(reason="Owned Gazebo server was not started")),
            ]
        if server_state["exited"]:
            return [
                LogInfo(msg="ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exited_before_evaluation"),
                EmitEvent(event=Shutdown(reason="Gazebo exited before evaluation completion")),
            ]
        stop_command = ExecuteProcess(
            cmd=["gz", "topic", "-p", "/gazebo/server/control", "-m", "stop: true"],
            name="mr3_gazebo_native_stop", output="screen", shell=False,
            env=server_state["environment"],
        )
        return [
            RegisterEventHandler(OnProcessExit(
                target_action=stop_command,
                on_exit=native_stop_cli_exited,
            )),
            stop_command,
            TimerAction(period=10.0, actions=[OpaqueFunction(function=native_stop_timeout)]),
        ]

    actions.extend([
        RegisterEventHandler(OnProcessStart(on_start=remember_gzserver),
                             condition=IfCondition(stop_on_evaluation)),
        RegisterEventHandler(OnProcessExit(on_exit=owned_gzserver_exited),
                             condition=IfCondition(stop_on_evaluation)),
        RegisterEventHandler(OnProcessExit(
            target_action=task_evaluator, on_exit=evaluation_finished,
        )),
    ])
    gzserver_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("gazebo_ros"),
                "launch",
                "gzserver.launch.py",
            )
        ),
        launch_arguments={"world": world, "seed": gazebo_seed, "server_required": "false"}.items(),
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
    nav_bringups = []

    for robot in robots:
        robot_name = robot["name"]
        namespace = "/" + robot_name

        params_file = os.path.join(
            multi_robot_share,
            "params",
            f"nav2_params_{robot_name}_0.yaml",
        )
        if adapter_mode:
            # Keep local sensing and every Nav2 parameter unchanged; only the
            # two global static-map inputs use the declared robot-side copy.
            params_file = RewrittenYaml(
                source_file=params_file, convert_types=True,
                param_rewrites={
                    "global_costmap.global_costmap.ros__parameters.map_topic":
                        f"/{robot_name}/navigation_map",
                    "global_costmap.global_costmap.ros__parameters.static_layer.map_topic":
                        f"/{robot_name}/navigation_map",
                },
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

        nav_bringups.append(bringup_cmd)

        last_spawn_action = spawn_robot

    # ========= RViz and optional drive nodes =========
    # Start RViz only after the last robot has been spawned.
    # By default enable_rviz is false to reduce CPU/GPU load.
    if last_spawn_action is not None:
        staggered_nav = [
            TimerAction(
                period=10.0 + 45.0 * index,
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
    ld.add_action(DeclareLaunchArgument(
        "execution_mode", default_value="baseline",
        description="baseline: handcrafted controller; adapter: exclusive MR3 joint action endpoint.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "mr3_episode_epoch", default_value="mr3-p1b",
        description="Unique process-rebuilt episode identity for the ideal policy interface.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "mr3_audit_path", default_value="",
        description="Optional exclusive-create JSONL policy observation/protocol audit.",
    ))

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
            default_value="3",
            description="Number of robots to spawn. MR3 uses 3; compatibility range: 1 to 4.",
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
            default_value="300.0",
            description="Wall seconds to wait for every Nav2 action server.",
        )
    )

    for name, description in (
        ("navigation_response_timeout_sec", "Simulated seconds to await goal acceptance."),
        ("navigation_cancel_timeout_sec",
         "Simulated seconds to await cancellation and a terminal result."),
    ):
        ld.add_action(DeclareLaunchArgument(name, default_value="10.0", description=description))
    ld.add_action(DeclareLaunchArgument(
        "stop_on_evaluation_complete", default_value="true",
        description="Stop the owned launch when the enabled evaluator exits.",
    ))

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

    ld.add_action(DeclareLaunchArgument(
        "evaluation_contract_path", default_value="",
        description="MR3 task contract JSON; empty preserves schema 3 evaluation.",
    ))

    ld.add_action(OpaqueFunction(function=launch_setup))

    return ld
