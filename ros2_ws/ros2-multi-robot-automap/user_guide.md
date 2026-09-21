# ROS2 多机器人自主建图项目使用指南

常用启动命令、不同 world 和参数速查见 [`launch_commands.md`](launch_commands.md)。

本文档面向当前项目状态：ROS2 Humble + Gazebo Classic + TurtleBot3 Waffle，多机器人通过各自 SLAM 建图，`merge_map` 合并全局地图，`multi_robot_exploration` 统一分配探索目标。

自 2026-09-02 起，本目录已通过 `git subtree` 合入 `Breeze-by/my_ns3-gym`
monorepo，与 ns-3/ns3-gym 共用一个 Git 根。旧的独立检出目录及兼容符号链接
已删除；唯一工作目录是
`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap`，提交和查看状态
必须从 `/home/zhuyulab/ns3-workspace` 进行。

## 1. 项目结构

项目根目录：

```bash
/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
```

关键包：

| 路径 | 作用 |
| --- | --- |
| `src/multi_robot` | 主仿真包。负责 Gazebo 世界、机器人 SDF/URDF、主 launch、Nav2 参数、RViz 配置。 |
| `src/merge_map` | 地图合并包。按栅格原点对齐 `/tbN/map`，合并已知区域并发布 `/merge_map`。 |
| `src/multi_robot_exploration` | 中央协同探索节点。用本地地图验证每台机器人的可达性，用合并地图统一评价信息增益，并分配互不冲突的 Nav2 目标。 |
| `src/multi_robot/params/nav2_params_tb*_0.yaml` | 每台机器人单独的 Nav2 参数。当前主 launch 使用 `tb1` 到 `tb4`。 |
| `src/multi_robot/models/turtlebot3_waffle/model.sdf` | Gazebo 实体模型。当前保留 lidar、imu、diff_drive、joint_state，禁用了深度相机传感器。 |
| `src/saved_map` | `map_saver_cli` 保存合并地图的位置。 |

## 2. 启动链路

主入口：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_task_regions:=true \
  enable_status_panel:=true \
  enable_battery:=true \
  battery_initial_energy:=40.0 \
  enable_rviz:=false
```

主 launch 文件：

```text
src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py
```

它负责启动：

| 模块 | 启动位置 |
| --- | --- |
| Gazebo server | include `gazebo_ros/launch/gzserver.launch.py` |
| Gazebo GUI | include `gazebo_ros/launch/gzclient.launch.py`，由 `enable_gzclient` 控制 |
| 机器人 spawn | `gazebo_ros/spawn_entity.py`，按 `robot_count` 顺序启动 `tb1..tb4` |
| robot_state_publisher | 每个机器人一个 namespace：`/tb1`、`/tb2` 等 |
| joint_state_publisher | 每个机器人一个 |
| Nav2 | include `src/multi_robot/launch/nav2_bringup/bringup_launch.py` |
| slam_toolbox | include `slam_toolbox/launch/online_async_multirobot_launch.py` |
| merge_map | 主 launch 直接启动 `merge_map` 节点，确保退出时不会遗留子 launch 进程 |
| Nav2 就绪门控 | 等待所有 `/tbN/navigate_to_pose` action server 可用 |
| headquarters_control | `ros2 run multi_robot_exploration control` |
| Gazebo 任务区域 | `task_visualizer` 生成无碰撞的重点区域标记，默认开启 |
| 机器人状态栏 | `robot_status_panel` 显示任务、电池、位姿和速度，默认开启 |
| 每机器人 RViz | 由 `enable_rviz` 控制，默认关闭 |
| 全局地图 RViz | 由 `enable_merge_rviz` 控制，默认开启 |

## 3. robot_count 如何生效

主 launch 中维护一个 `all_robots` 列表：

```text
tb1, tb2, tb3, tb4
```

`robot_count` 会被限制在 `1..4`，然后取前 N 台：

```text
robot_count:=1 -> tb1
robot_count:=2 -> tb1, tb2
robot_count:=3 -> tb1, tb2, tb3
robot_count:=4 -> tb1, tb2, tb3, tb4
```

同一个 `robot_count` 会传给：

```text
merge_map
multi_robot_exploration/control
```

因此 `/tbN/map`、`/tbN/tf` 订阅数量、Nav2 action client 数量和 Gazebo 中的机器人数量保持一致。

## 4. RViz 策略

当前推荐策略按观察目的二选一，避免同时运行两个高负载前端：

```text
观察机器人运动：Gazebo GUI 开，全局/每机器人 RViz 关
观察合并地图：Gazebo GUI 关，全局 RViz 开，每机器人 RViz 关
```

机器资源充足时可以同时打开 Gazebo GUI 和全局 RViz，但这不是手动演示的默认建议。

参数含义：

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `world` | `my_world.world` | `multi_robot/worlds` 中的 world 文件名；拒绝目录路径和不存在的文件 |
| `enable_gzclient` | `true` | 是否启动 Gazebo GUI |
| `enable_task_regions` | `true` | 是否在 Gazebo 标出起始/充电、检测和集合区域 |
| `enable_status_panel` | `true` | 是否打开每机器人实时状态栏 |
| `enable_rviz` | `false` | 是否启动每台机器人单独 RViz |
| `enable_merge_rviz` | `true` | 是否启动一个全局 `/merge_map` RViz |
| `gazebo_seed` | `1` | Gazebo 随机种子；正式运行必须显式记录 |
| `spawn_timeout` | `90.0` | 每台机器人等待 Gazebo spawn 服务的秒数 |
| `nav2_ready_timeout_sec` | `180.0` | 等待全部 Nav2 action 可发现且 `bt_navigator=active` 的最长墙钟秒数；超时不启动探索 |
| `auto_save_map` | `true` | headquarters 是否自动保存合并地图；smoke 时关闭 |
| `enable_task_evaluator` | `false` | 是否启动只读任务评估器 |
| `evaluation_episode_id` | `episode` | CSV/JSON 文件名和 episode 标识 |
| `evaluation_output_dir` | `/tmp/multi_robot_evaluation` | 评估结果目录 |
| `evaluation_duration_sec` | `0.0` | 仿真超时；0 表示只在 shutdown 时保存 |
| `evaluation_coverage_threshold` | `0.0` | 正确自由空间覆盖率成功阈值；0 表示仅按超时结束，当前 P1C 正式口径传 0.90 |
| `evaluation_stop_on_target_found` | `false` | P2A 验证时是否在目标确认后立即结束评估 |
| `evaluation_stop_on_task_complete` | `false` | P2B 验证时是否在 `COMPLETE`/`FAILED` 后结束评估 |
| `enable_target_detection` | `false` | 是否生成搜索目标并启动 P2A 真值检测节点 |
| `enable_rally` | `false` | 是否由协调器在确认目标后停止探索并执行 P2B 集合 |
| `target_x`, `target_y` | `-4.0`, `4.0` | 搜索目标在 world 坐标系中的位置 |
| `target_max_distance_m` | `3.0` | 检测最大距离 |
| `target_field_of_view_deg` | `90.0` | 水平检测视场角 |
| `target_confirmation_frames` | `3` | 确认目标所需的连续可见帧数 |
| `rally_position_tolerance_m` | `0.35` | `COMPLETE` 的单机器人平面误差上限 |
| `rally_linear_tolerance_mps` | `0.05` | `COMPLETE` 的线速度上限 |
| `rally_angular_tolerance_radps` | `0.10` | `COMPLETE` 的角速度上限 |
| `rally_hold_sec` | `5.0` | 全体同时满足误差和速度门槛的连续保持时间 |
| `rally_max_retries` | `2` | 每台集合导航失败后的最大重试次数 |
| `exploration_goal_timeout_sec` | `60.0` | 单个 Nav2 目标的最大仿真秒数 |
| `enable_battery` | `true` | 是否启动每机器人一个 P2C 本地能量/充电管理器 |
| `battery_capacity`, `battery_initial_energy` | `100.0`, `40.0` | 满电容量和 episode 初始能量；较低初始值保留三机器人充电区安全余量 |
| `battery_move_cost_per_m` | `1.0` | 每行驶 1 m 的能量成本 |
| `battery_idle_cost_per_sec` | `0.02` | 每仿真秒的基础能量成本 |
| `battery_return_safety_margin` | `5.0` | 预计返航成本之外保留的安全余量 |
| `battery_charge_duration_sec` | `10.0` | 在充电位静止后恢复满电所需仿真秒数 |
| `battery_return_timeout_sec` | `120.0` | 单次安全返航总超时 |
| `battery_charge_timeout_sec` | `60.0` | 进入充电模式后的总超时 |

### 4.1 Gazebo 重点区域和实时状态栏

手动运行主 launch 时两项默认开启，无需额外命令。Gazebo 中的颜色含义为：

- 蓝色高亮贴地边界环：半径 1 m 的共同起始/充电区；
- 绿色圆盘：每台机器人半径 0.25 m 的独立充电位；
- 红色贴地边界环：启用目标检测时的最大检测距离；
- 橙色圆盘：`/rally_assignments` 发布后各机器人的最终集合位姿。

这些实体只有 visual、没有 collision，不参与 lidar、碰撞、规划或任务评分。独立 Qt 状态栏
实时显示全局任务阶段，以及每台机器人的当前动作、Nav2 状态、电池模式和电量、odom 位姿、
线速度和角速度。无桌面的 headless 运行应显式关闭界面；区域标记也可单独关闭：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  enable_status_panel:=false \
  enable_task_regions:=false
```

也就是说，常用命令里 `enable_rviz:=false` 不会关闭全局地图 RViz，只会关闭每机器人 RViz。

如需完全关闭 RViz：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false
```

P1C 跨地图验收提供三张额外静态 world：

| World | 主要结构 |
| --- | --- |
| `p1c_open.world` | 开放空间、离散和斜置障碍 |
| `p1c_rooms.world` | 多房间、门洞和遮挡 |
| `p1c_corridors.world` | 长绕行、交替出口和支路走廊 |

例如启动房间地图：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=p1c_rooms.world robot_count:=3 \
  enable_gzclient:=true enable_merge_rviz:=false
```

## 5. 当前数据流

每台机器人在 Gazebo 中发布：

```text
/tbN/cmd_vel
/tbN/odom
/tbN/scan
/tbN/imu
/tbN/joint_states
```

每台机器人对应一个 SLAM 地图：

```text
/tb1/map
/tb2/map
/tb3/map
/tb4/map
```

`merge_map` 订阅所有 active robot 的 `/tbN/map`，发布：

```text
/merge_map
```

`headquarters_control` 订阅：

```text
/merge_map
/tbN/map
/tbN/odom
/tbN/tf
```

启用 P2A 后，独立的 `target_detector` 还订阅 `/gazebo/model_states`，发布：

```text
/target_observation
/target_detection
```

它不发布导航目标。`/target_observation` 依次可能为 `EXPLORE`、
`FOUND_UNCONFIRMED`、`FOUND`；`/target_detection` 只在确认后发布一次，包含发现机器人、
目标 world 坐标和本次检测参数。`headquarters_control` 是 `/task_state` 的唯一发布者；启用
P2B 后还发布 `/rally_assignments` 和 `/task_failure`。

启用 P2C 后，每台机器人各运行一个本地 `battery_manager`。它只读取本机 `/tbN/odom`、
`/tbN/tf` 和全局任务终态，发布 transient `/tbN/battery_state`，并在安全余量触发后直接
调用本机 Nav2 返回该机器人的独立出生/充电位。总部根据电池模式暂停或恢复任务分配，但不能
否决返航；明确失败经 `/battery_failure` 汇入权威 `/task_failure`。第一版 `c_tx=0`。

并向每台机器人发送 Nav2 action：

```text
/tbN/navigate_to_pose
```

## 6. 稳定性优化内容

本轮优化以小改动为主，没有改变整体架构。

### 6.1 关闭不必要相机负载

修改文件：

```text
src/multi_robot/models/turtlebot3_waffle/model.sdf
```

已删除 Gazebo 深度相机 `<sensor name="camera" type="depth">` 和 `libgazebo_ros_camera.so` 插件。保留机器人主体、lidar、imu、diff_drive、joint_state。

目的：

```text
减少 camera / depth / pointcloud 相关话题和 Gazebo 传感器计算负载。
```

### 6.2 降低 Nav2 频率

修改文件：

```text
src/multi_robot/params/nav2_params_tb1_0.yaml
src/multi_robot/params/nav2_params_tb2_0.yaml
src/multi_robot/params/nav2_params_tb3_0.yaml
src/multi_robot/params/nav2_params_tb4_0.yaml
```

关键变化：

| 参数 | 原值 | 新值 |
| --- | --- | --- |
| `bt_loop_duration` | `10 ms` | `100 ms` |
| `controller_frequency` | `20 Hz` | `10 Hz` |
| `expected_planner_frequency` | `20 Hz` | `2 Hz` |
| local costmap `update_frequency` | `5 Hz` | `3 Hz` |
| local costmap `publish_frequency` | `2 Hz` | `1 Hz` |
| global costmap `update_frequency` | `1 Hz` | `0.5 Hz` |
| global costmap `publish_frequency` | `1 Hz` | `0.5 Hz` |
| recovery `cycle_frequency` | `10 Hz` | `5 Hz` |
| EKF `frequency` | `30 Hz` | `20 Hz` |
| DWB `debug_trajectory_details` | `True` | `False` |

目的：

```text
降低 Control loop missed、Planner loop missed、BT tick exceeded 的发生频率。
```

### 6.3 全局 RViz 参数化

修改文件：

```text
src/merge_map/launch/merge_map_launch.py
src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py
```

新增：

```text
enable_merge_rviz:=true/false
```

目的：

```text
默认保留一个全局地图 RViz，同时明确区分“全局 RViz”和“每机器人 RViz”。
```

### 6.4 map_saver 限频

修改文件：

```text
src/multi_robot_exploration/multi_robot_exploration/control.py
```

`map_saver_cli` 不再在“所有机器人 idle”时立刻反复触发，改为节点启动后至少等待 60 秒，之后两次自动保存之间至少间隔 60 秒。保存命令显式使用 `-t /merge_map`，不再依赖 `/map` remap。

可通过参数调整：

```bash
ros2 run multi_robot_exploration control --ros-args \
  -p robot_count:=3 \
  -p save_map_interval_sec:=600.0
```

主 launch 当前只显式传 `robot_count`，保存间隔使用默认 `60.0` 秒。调试时也可以关闭自动保存：

```bash
ros2 run multi_robot_exploration control --ros-args \
  -p robot_count:=3 \
  -p auto_save_map:=false
```

### 6.5 协同探索、目标筛选与失败重试

修改文件：

```text
src/multi_robot_exploration/multi_robot_exploration/control.py
```

目标点现在会避开：

```text
过小 frontier 分组
非 free cell
unknown cell
地图边界附近
0.45m 内存在障碍物的 cell
刚刚访问过或过近的目标
规划失败或被拒绝的坏目标附近
```

Nav2 goal 处理也拆成：

```text
goal accepted/rejected
最终 result succeeded/failed
```

中央协调器为每台机器人在自己的 `/tbN/map` 上计算已知自由空间连通域和多组安全观察点，
再用 `/merge_map` 中仍未知的栅格数统一评分。一次分配会为所有 idle 机器人选择相距至少
1.2 m 的不同目标；同一个大前沿可以提供多个空间分散的观察点，因此机器人不会各自抢同一点，
也不会因为“每个前沿只保留一个目标”而串行等待。

控制器订阅每台机器人的 `/tbN/tf`，用实时 `map→odom` 把里程计位置转换到 SLAM 地图坐标后
再做 Dijkstra 可达性判断。禁止把 odom 坐标直接当 map 坐标。候选计算从前沿向外枚举有限
邻域，避免旧实现的“地图候选数 × 前沿长度”二次循环阻塞 ROS 执行器。

目标被接受后最多执行 60 仿真秒。成功目标短期保留在访问历史，避免 A→B→A 往返；失败目标
释放预留并加入坏目标集合；启动期或瞬态拒绝只释放，不永久拉黑候选。一个前沿组的首选
栅格无效时，会继续尝试同组其他安全栅格，而不是丢弃整个组。

建图模式只启动 SLAM Toolbox，不再同时启动 AMCL，确保每台机器人只有一个
`map→odom` 发布源。自定义 multi-robot SLAM 回调会保存最新 scan header，使 SLAM 的 TF
发布线程真正工作。Nav2 使用各自本地 SLAM 地图，A* 允许穿过待探索 unknown，但最终目标
必须是具有 0.45 m 障碍净空的已知自由栅格。

主 launch 在机器人生成 10 秒后启动第一套 Nav2，后续机器人按 45 秒错峰，避免多个导航栈
同时初始化造成资源竞争。`nav2_ready_gate` 同时检查所有 `/tbN/navigate_to_pose` action
server；全部可用后立即启动控制器和评估器，不再固定等待最后一套 Nav2 启动后的额外 60 秒。
门控超时会列出未就绪的 action 并阻止探索带病启动。探索行为树不使用的
`smoother_server` 不再启动；速度平滑器 `velocity_smoother` 仍保留。

### 6.6 地图融合

`merge_map` 验证输入分辨率和数据尺寸，按每张 OccupancyGrid 的世界原点计算整数栅格偏移，
用 NumPy 合并所有机器人已知区域。unknown 只在没有机器人观测时保留；已知冲突采用 free
优先，清理由其他机器人动态占据造成的机器人残影。输出固定为 `frame_id=map`、
`topic=/merge_map`，frame 和 topic 不再混用。主 launch 直接拥有 merge 节点，实验结束后不会
遗留多个 `/merge_map` publisher 污染下一轮。

## 7. 编译

推荐每次修改后执行：

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install --packages-select multi_robot merge_map multi_robot_exploration
source install/setup.bash
```

如果 shell 没有 ROS 环境：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
```

## 8. 启动

启动前清理旧进程：

```bash
pkill -f gzserver
pkill -f gzclient
pkill -f gazebo
pkill -f rviz2
```

推荐的两机器人 Gazebo 演示：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle

ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=2 \
  enable_gzclient:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false \
  auto_save_map:=false \
  gazebo_seed:=101
```

协同探索不再固定等待两分钟。全部 Nav2 action server 实际就绪后，终端会依次出现：

```text
All 2 Nav2 action servers are ready.
Nav2 ready; starting cooperative exploration.
```

2026-09-16 的两机器人 headless smoke 中，门控开始后 56.7 墙钟秒全部就绪，7.0 秒后
两台机器人收到不同目标；这是实测参考，不是新的固定等待值。

## 9. 验证

修改或重新构建后，优先使用有界 headless smoke 工具：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle

python3 scripts/ros_smoke_test.py --robot-count 1 --gazebo-seed 1
python3 scripts/ros_smoke_test.py --robot-count 2 --gazebo-seed 1
python3 scripts/ros_smoke_test.py --robot-count 3 --gazebo-seed 1
```

工具检查每台机器人的核心 topic、Nav2 controller/planner/bt_navigator lifecycle，以及至少一条
lidar 和合并地图消息。它只终止自己启动的进程组；原始 launch 输出写入被 Git 忽略的
`log/smoke/`。每次正式 smoke 的命令和结论仍必须追加到 wireless-rl 的 `log.md`。

带 P1B 评估器的短 episode：

```bash
python3 scripts/ros_smoke_test.py \
  --robot-count 2 \
  --gazebo-seed 13 \
  --evaluation-duration 10 \
  --evaluation-wait-timeout 240 \
  --startup-timeout 240 \
  --shutdown-timeout 60
```

评估器只订阅数据，不发布控制命令。它使用 `/gazebo/model_states` 计算真值路径和固定
0.1 m 访问 mask，使用 `/tbN/collision` 统计带冷却和持续时间的接触事件，使用 Nav2
action status 统计成功、取消和失败目标。

地图真值直接从当前 SDF world 生成：应用 `<state>` 中的模型位置，在机器人 lidar
高度对静态 box collision 做 0.05 m 栅格化，再把 `/merge_map` 重采样到同一世界坐标。
输出同时包含正确自由空间覆盖率、已知覆盖率、观测区域准确率和 occupied IoU。当前
`my_world.world` 有一个位于实验室外部的 SUV mesh collision 未栅格化，输出字段
`truth_unsupported_collision_count=1` 会保留这个限制；如果以后把 mesh 障碍物放进可达
任务区域，必须先增加 mesh 真值处理。

CSV/JSON 默认写入 `log/evaluation/`（由 smoke 工具指定并被 Git 忽略）。P1C 当前定义为：
`correct_free_coverage_ratio >= 0.90` 时记录 `success=true` 和
`termination_reason=coverage_reached`；180 仿真秒未达到则记录 timeout。输出 schema v6
还包含 75%/80%/90%/95% 首次达到时间、每台机器人起终点、导航目标结果、路径、碰撞、
搜索重叠，以及目标是否发现、发现机器人、发现时间、发现时覆盖率、目标位置和检测规则。
schema v6 另含逐机器人初始/最低/最终能量、返航和充电次数、充电时长与充电位。从 schema
v5 起，episode 内任一接触都会使权威 `success=false`，即使状态机随后到达
`COMPLETE`；`termination_reason` 仍保留实际终止事件，`failure_reason=collision`。

P1C 理想通信批量入口（每个 seed 启动独立 ROS/Gazebo 进程）：

```bash
python3 scripts/run_ideal_baseline.py \
  --world p1c_corridors.world \
  --seeds 101 202 303 \
  --robot-count 2 \
  --duration 180 \
  --coverage-threshold 0.90 \
  --goal-timeout 60 \
  --message-timeout 90 \
  --run-id <unique-run-id>
```

结果写入 `log/ideal_baseline/<run-id>/`：每个 episode 的 CSV/JSON 位于 `episodes/`，
原始 launch 日志位于 `launch_logs/`，批次根目录含增量更新的 `summary.csv/json`。目录已被
Git 忽略，但正式运行的命令、commit、seed、参数和结论必须追加到 wireless-rl `log.md`。

截至 2026-09-17，P1C 已完成并通过用户验收。world、真值、评价规则、速度和传感器
保持不变时，最终代码在 seeds 101/202/303 上的 90% 首达时间为：2 机器人
98.9/79.6/104.4 秒（均值 94.3 秒），3 机器人 78.3/69.8/69.5 秒（均值 72.5 秒）。
六轮全部零碰撞；两机器人零搜索重叠，三机器人最大重叠 0.44%。因此 180 秒作为硬上限，
当前验收线为 2 机器人最慢不高于 120 秒、3 机器人最慢不高于 90 秒；600 秒不再使用。
早期结果保留为缺陷修复历史。完整优化与失败尝试见
`report/20260917_p1c_optimization.md`；95% 仍是可选更高覆盖目标。

同日跨地图验收保持控制器、Nav2、真值、传感器、速度、安全距离和评分不变，在
`p1c_open.world`、`p1c_rooms.world`、`p1c_corridors.world` 上分别运行 3 机器人
seeds 101/202/303。九轮全部达到 90%，最坏用时 75.5 秒，全部零碰撞；最低观测准确率
97.47%，最大搜索重叠 1.91%。最难走廊地图 seed 202 的两机器人交叉验证用时 85.5 秒、
零碰撞。完整逐轮结果、无效基础设施轮次和适用边界见
`report/20260917_p1c_generalization.md`。

### 9.1 P2A 目标检测验证

P2A 使用无 collision 的红色静态圆柱作为 Gazebo 搜索目标，因此它不会改变 lidar、地图真值
或可通行区域。检测节点读取 Gazebo 真值位姿，但只有同时满足以下条件才认为当前帧可见：

- 机器人到目标不超过 `target_max_distance_m`；
- 目标在机器人朝向两侧各半个水平视场角内；
- 机器人和目标之间的线段不穿过当前 world 的静态占据真值；
- 同一机器人连续满足以上条件达到 `target_confirmation_frames` 帧。

任一不可见帧会清零该机器人的连续计数。默认关闭该功能，因而原有 P1C 启动行为不变。
正式 3 机器人验证命令示例：

```bash
python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed 101 \
  --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 180 --coverage-threshold 0 \
  --evaluation-wait-timeout 390 --target-detection \
  --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2a_target_detection_3r_seed101
```

seeds 101/202/303 的目标确认时间为 60.7/72.9/61.5 仿真秒，均由 `tb1` 发现，碰撞和
搜索重叠均为 0。目标置于 `(100, 100)` 的 10 秒负例没有发布确认，结果保持
`target_found=false`、`task_phase=EXPLORE`。完整证据见 `report/20260917_p2a.md`。P2A 已通过
用户验收；检测器在 P2B 中降为观测/事件生产者，权威任务状态由协调器发布。

### 9.2 P2B 集合状态机验证

启用 `--rally` 后，确认目标会使协调器取消全部活动探索目标，从当前已知自由地图生成不同、
可达并朝向目标的集合位姿。最终位姿要求至少 0.45 m 障碍净空和 0.8 m 相互间距；集合导航
使用 0.35 m 路径净空、最长 1.5 m 分段目标。协调器用融合地图和实时机器人位姿预约短路径；
相距至少 1.2 m 的路径最多允许两台机器人并发，路径冲突时只有低优先级机器人等待，实际位置
接近时它会取消当前短航段让行并重新规划。发现机器人拥有首轮优先级，但其他机器人不再等待
它完成整个集合。只有所有机器人位置误差不超过 0.35 m、线速度不超过 0.05 m/s、角速度不
超过 0.10 rad/s 并连续保持 5 个仿真秒，协调器才发布 `COMPLETE`。

正式命令模板：

```bash
python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 3 --gazebo-seed 101 \
  --startup-timeout 360 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout 480 --target-detection --rally \
  --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2b_rally_3r_seed101
```

最终 3 机器人 seeds 101/202/303 分别在 134.5/171.9/177.3 仿真秒进入 `COMPLETE`，
三轮均零碰撞，集合点最小间距为 1.210/1.221/1.414 m，最大最终位置误差 0.237 m。
2 机器人 seed 303 交叉验证在 96.5 秒完成，零碰撞。完整逐机器人速度、失败演进和原始
episode 标识见 `report/20260917_p2b.md`。P2B 已于 2026-09-17 通过用户验收。

随后对覆盖率和耗时的专项审查增加了 `coverage_at_detection`。两机器人复核在 75.57%
覆盖时确认目标，停止探索后以 81.62% 最终覆盖完成，观测准确率为 97.40%、搜索重叠为 0；
因此该低覆盖来自 P2B 的“发现后停止 frontier 探索”规则，而不是融合失败。三机器人审查轮的
发现时覆盖为 86.95%–87.42%，最终覆盖为 93.91%–94.27%，同样未见地图质量退化。

无约束的全并行中间航段曾在共同入口造成 43 次接触，已撤回；10 秒无进展取消也会过早打断
Nav2 内部恢复，未保留。当前冲突感知并发在 seeds 101/202/303 上均 `COMPLETE` 且零碰撞，
`RALLY` 到 `COMPLETE` 分别为 57.6/58.0/69.4 秒，平均 61.7 秒；原正式串行轮平均为
77.6 秒。一个集合 action 完整失败后仍会把下一次航段缩短为 0.75 m、0.5 m，避免原样重发
同一航点。详情见 `report/20260917_p2b_audit.md`。

发现机器人优先修复后的两机器人 seed 303 复核中，tb1 在 65.1 秒确认目标后首先收到集合
goal，并在约 5.2 秒后到达自己的目标附近集合位；117.9 秒进入 `COMPLETE`，两机器人最终
误差为 0.215/0.206 m，碰撞为 0。该轮是冲突感知并发前的回归证据。

### 9.3 P2C 电池、返航和充电验证

`--battery` 会启动机器人本地能量模型。能量按 odom 行驶距离和仿真经过时间扣除；返航阈值
为保守预计返航能耗加固定安全余量。触发后本地管理器抢占探索/集合 action，返回本机器人的
出生充电位，只有在半径 0.25 m 内且速度低于集合静止门槛时才开始充电。充电不会重启 SLAM、
清空地图或重置任务状态。`--require-charge` 使 smoke 在没有真实发生充电时判失败。

两机器人强制充电验收命令：

```bash
python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout 600 --target-detection --rally \
  --battery --require-charge --battery-initial-energy 18 \
  --battery-capacity 100 --battery-move-cost 1 \
  --battery-idle-cost 0.02 --battery-safety-margin 5 \
  --battery-charge-duration 10 --battery-return-timeout 120 \
  --battery-charge-timeout 60 \
  --target-x -4 --target-y 4 --target-max-distance 3 \
  --target-field-of-view 90 --target-confirmation-frames 3 \
  --episode-id p2c_forced_charge_2r_seed303
```

保留运行 `p2c_forced_charge_2r_seed303_pilot3` 中，tb1/tb2 各返航并充电一次，最低能量
分别为 6.81/6.66；之后继续探索，在 118.2 秒确认目标、126.2 秒进入 `RALLY`、190.1 秒
进入 `COMPLETE`。最终覆盖率 92.15%、总路径 49.733 m、搜索重叠和碰撞均为 0。逐机器人
最终集合误差为 0.216/0.128 m，最终电池模式均为 `ACTIVE`。耗尽、返航不可达和充电超时由
构造测试验证为明确失败原因。P2C 已于 2026-09-18 通过用户验收；P2D 已完成实现和正式矩阵并通过用户验收；P3A 已完成实现和正式 gateway 矩阵，当前待用户验收。验收后新增的
Gazebo 重点区域和实时状态栏只读现有任务数据，不改变 P2C 控制与评分口径。

### 9.4 P2D 完整理想通信任务基线

`scripts/run_p2d_baseline.py` 串行执行 `scripts/p2d_scenarios.json` 中冻结的完整任务场景，自动
使用独立 `ROS_DOMAIN_ID`，并汇总 JSON/CSV。lab/rooms 初始能量为 40，走廊困难场景为 45，
均显著低于 100 满电容量；电池始终启用，但不会用“每轮必须充电”把本来成功的短任务人为判失败。25
能在单轮中触发并完成充电，但三机器人可能同时返航、拥堵相邻充电位，因此未作为正式默认值。

评估结果 schema 7 除完整探索、检测、集合和完成时间外，还分别记录 `EXPLORE`、`FOUND`、
`RALLY` 的路径长度、访问栅格并集和重叠率。`search_overlap_ratio` 现在严格只表示探索阶段，
`total_overlap_ratio` 才表示整个 episode。正式运行命令和固定矩阵见
[`launch_commands.md`](launch_commands.md#35-p2d-完整理想通信基线)。

2026-09-18 最终 10 项门禁全部以 `COMPLETE`、零碰撞结束：lab/rooms 的三个 seeds 使用 40
能量，走廊三个 seeds 与双机器人交叉检查使用 45。至少一项 lab 任务在 40 能量下完成一次
安全返充并继续到 `COMPLETE`，说明低电量闭环确实参与任务。P2D 已验收；P3A gateway 矩阵另外完成
10/10 `COMPLETE`、零碰撞，强制充电回归完成两次充电；P3A 当前待用户验收。

### 9.5 P3A 显式零损 gateway

P3A 使用 `multi_robot_interfaces/GatewayEnvelope` 将地图、位姿、TF、电量、检测和任务命令包装为带发送者、序号、生成时间、TTL、ACK 和载荷长度的消息。`ideal_gateway` 使用本地队列和接收状态存储实现零损交付，`navigation_gateway` 将中央导航命令转换为机器人本地 Nav2 action；源码清单和 ROS graph 均检查中央没有机器人原始 topic/action 直连，也没有机器人 Nav2 对中央 `/merge_map` 的直订阅。运行时审计命令为：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run multi_robot_exploration bypass_audit --robot-count 3 --wait-sec 10
```

正式结果位于 `log/p2d_baseline/p3a_formal_gateway_3scenes_v2/`；P3B 才会在同一协议上加入固定 delay/loss，当前 P3A 不代表 Wi-Fi 性能结果。

以下命令适合运行中的人工诊断：

检查每台机器人是否有控制话题：

```bash
ros2 topic list | grep "/tb[0-9]/cmd_vel$"
```

检查 Nav2 lifecycle：

```bash
ros2 lifecycle get /tb1/controller_server
ros2 lifecycle get /tb2/controller_server
ros2 lifecycle get /tb3/controller_server

ros2 lifecycle get /tb1/planner_server
ros2 lifecycle get /tb2/planner_server
ros2 lifecycle get /tb3/planner_server
```

预期：

```text
active
```

检查速度输出：

```bash
ros2 topic hz /tb1/cmd_vel
ros2 topic hz /tb2/cmd_vel
ros2 topic hz /tb3/cmd_vel
```

检查合并地图：

```bash
ros2 topic hz /merge_map
```

检查 GUI 数量：

```bash
pgrep -af rviz2
pgrep -af gzclient
```

预期：

```text
rviz2 只有一个
gzclient 有一个
```

检查相机话题是否已消失：

```bash
ros2 topic list | grep -E "camera|depth|pointcloud|points"
```

理想情况下不应再看到由 TurtleBot3 Waffle 模型发布的相机、深度图或点云话题。

## 10. 常见问题

### 10.1 Control loop missed its desired rate

通常表示 CPU/Gazebo/Nav2 总负载过高。当前已通过关闭相机和降低 `controller_frequency` 缓解。若仍频繁出现，可以继续尝试：

```text
关闭 Gazebo 中 lidar 可视化
降低机器人数量
降低 local_costmap update_frequency
关闭全局 RViz：enable_merge_rviz:=false
```

### 10.2 Planner loop missed its desired rate

当前 `expected_planner_frequency` 已降为 `2.0`。如果仍出现，重点检查：

```text
CPU 是否满载
/merge_map 是否过大
目标点是否落在障碍物或未知区域附近
```

### 10.3 GridBased failed to generate a valid path

常见原因：

```text
目标点在障碍物膨胀区内
目标点在地图边界附近
目标点在当前 rolling global_costmap 外
目标点对应区域还未被 SLAM 稳定观测
```

当前 `headquarters_control` 已增加目标点筛选和失败换点机制。少量失败仍是正常现象，关键是机器人应能自动换目标继续探索。

### 10.4 DWBLocalPlanner No valid trajectories

常见原因：

```text
机器人离障碍物过近
局部 costmap 中目标方向被障碍物挡住
Nav2 目标点太贴墙
```

当前主要通过目标点避障和降低计算压力缓解。若仍严重，可考虑增大目标点安全距离或调整 DWB 参数。

### 10.5 map_saver Failed to spin map subscription

常见原因：

```text
保存太频繁
/merge_map 暂时没有 latched 数据
map_saver_cli 与系统高负载竞争
```

当前已默认 60 秒限频保存，并显式保存 `/merge_map`。调试阶段也可以临时关闭自动保存逻辑，或在探索结束后手动保存：

```bash
ros2 run nav2_map_server map_saver_cli \
  -t /merge_map \
  -f /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/src/saved_map/manual_merged_map \
  --ros-args \
  -p map_subscribe_transient_local:=true
```

### 10.6 Nav2 readiness timed out

门控会列出尚未提供 `/tbN/navigate_to_pose` 的机器人，并且不会启动
`headquarters_control`。先检查对应机器人的生命周期和 TF：

```bash
ros2 lifecycle get /tb1/controller_server
ros2 lifecycle get /tb1/planner_server
ros2 lifecycle get /tb1/bt_navigator
ros2 run tf2_ros tf2_echo map base_footprint --ros-args \
  -r /tf:=/tb1/tf -r /tf_static:=/tb1/tf_static
```

所有 lifecycle 节点应为 `active`，TF 应持续更新。GUI 场景优先关闭全局 RViz以降低负载：

```text
enable_merge_rviz:=false
```

不要通过恢复固定长延时或忽略未就绪机器人来绕过门控。需要更多诊断时间时，仅调整
`nav2_ready_timeout_sec`；该参数是失败上限，不是正常启动延时。

## 11. 后续接入 ns-3 的建议切入点

P3A 后当前闭环为：

```text
robot 上行：本地 `/tbN/odom`、`/tbN/map`、TF、电量、检测 -> gateway -> `/gateway/received/...`
server 决策：`headquarters_control` 基于 gateway 接收地图分配目标
server 下行：gateway -> `/gateway/{robot}/navigate_to_pose` -> 本地 `/{robot}/navigate_to_pose`
```

底层机器人 topic 仍由本地 SLAM/Nav2 使用，但跨机器人/AP 信息不再绕过 gateway。P3A 的边界为：

```text
上行：本地地图版本/增量、位姿、电量、任务状态、目标检测 -> gateway -> 中央接收信息存储
下行：融合地图版本/相关区域、探索/返航/集合命令 -> gateway -> 机器人本地适配器
```

中央协调器和 `merge_map` 不直订 `/tbN/map`、`/tbN/odom`、`/tbN/tf` 或原始目标检测，中央
不直接调用 `/{robot}/navigate_to_pose`；1–3 号机器人的 Nav2 全局代价图消费
`/tbN/gateway/merge_map`。源码/运行时 forbidden-bypass 审计是 P3A 的退出条件。
评估器可以继续读取 Gazebo 真值，但不得向控制链发布。`ideal/unlimited` baseline 同样经过
gateway，只把交付设为零丢包和零附加时延，不能恢复旧直连。

P3B 将在此 gateway 上继续加入固定 delay/loss 和逐消息账本；在此之前不要把 P3A 的零损结果
解读为 Wi-Fi 性能结论。

P2B 起只有全体机器人在不同安全集合位姿连续稳定 5 秒后的 `COMPLETE` 才是任务成功；
`FOUND` 和 P1C 的 90% 覆盖率只是过程指标。当前 TurtleBot3 模型为降低仿真负载关闭了相机；
P2A 真值检测只用于仿真 MVP，P8A 实物前必须恢复真实相机检测适配器，不能把 Gazebo 真值
结果当作实物感知成果。
