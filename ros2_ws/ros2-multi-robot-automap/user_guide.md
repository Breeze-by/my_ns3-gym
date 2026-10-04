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
| `evaluation_stop_on_task_complete` | `false` | P2B 验证时是否在 `COMPLETE`/`PARTIAL_COMPLETE`/`FAILED` 后结束评估 |
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
| `battery_capacity`, `battery_initial_energy` | `60.0`, `40.0` | 满电容量和初始能量；18/24 可显式用于低电量压力测试 |
| `battery_move_cost_per_m` | `1.0` | 每行驶 1 m 的能量成本 |
| `battery_idle_cost_per_sec` | `0.02` | 每仿真秒的基础能量成本 |
| `battery_return_safety_margin` | `8.0` | 预计返航成本之外保留的安全余量 |
| `battery_charge_duration_sec` | `10.0` | 在充电位静止后恢复到目标电量所需仿真秒数 |
| `battery_charge_radius_m` | `0.5` | 充电位判定半径；允许 Nav2 到达误差仍进入充电 |
| `battery_charge_target_fraction` | `0.8` | 充到容量的 80% 后恢复探索，不必等到满电 |
| `battery_return_timeout_sec` | `180.0` | 单次安全返航总超时 |
| `battery_return_path_factor` | `2.0` | 返航路径相对直线距离的保守倍数 |
| `battery_nominal_speed_mps` | `0.18` | 返航时间预算使用的标称速度 |
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

P3A 后 `ideal_gateway` 先把机器人地图包装并交付到 `/gateway/received/tbN/map`；`merge_map` 只订阅
这些 gateway 交付的地图，再发布：

```text
/merge_map
```

`headquarters_control` 只消费 gateway 交付的机器人状态/地图/TF、电池和检测，并订阅融合地图：

```text
/merge_map
/gateway/received/tbN/map
/gateway/received/tbN/odom
/gateway/received/tbN/tf
/gateway/received/tbN/battery_state
/gateway/received/target_detection
/robot_failure
```

启用 P2A 后，独立的 `target_detector` 作为 Gazebo truth sensor provider 订阅
`/gazebo/model_states`，发布候选；P3A 的 gateway 才把它交付给总部：

```text
/gateway/received/target_observation
/gateway/received/target_detection
```

它不发布导航目标。`/target_observation` 依次可能为 `EXPLORE`、
`FOUND_UNCONFIRMED`、`FOUND`；`/target_detection` 只在确认后发布一次，包含发现机器人、
目标 world 坐标和本次检测参数。评估器可以只读 Gazebo truth 计算指标，但不向控制链发布真值。
`headquarters_control` 是 `/task_state` 的唯一发布者；启用
P2B 后还发布 `/rally_assignments` 和 `/task_failure`。

启用 P2C 后，每台机器人各运行一个本地 `battery_manager`。它只读取本机 `/tbN/odom`、
`/tbN/tf` 和全局任务终态，发布 transient `/tbN/battery_state`，并在安全余量触发后直接
调用本机 Nav2 返回该机器人的独立出生/充电位。总部根据电池模式暂停或恢复任务分配，但不能
否决返航；总部会按电池状态动态维护参与机器人集合。明确失败经 `/battery_failure` 汇入
`/robot_failure`，只有全部机器人都失败时才发布权威 `/task_failure`。第一版 `c_tx=0`。

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
刚刚访问过或过近的目标（连续惩罚，仍允许必要的重访）
规划失败或被拒绝的坏目标附近（短期惩罚，仍允许地图更新后的重试）
```

Nav2 goal 处理也拆成：

```text
goal accepted/rejected
最终 result succeeded/failed
```

中央协调器使用 gateway 交付的位姿和本地地图状态，在融合 `/merge_map` 上计算可达前沿
及安全观察点。按信息增益和距离评分候选，逐条检查停驻机器人避让和活动路线预约，并保留
至少 1.2 m 的目标间距；一条冲突候选不会挡住同一机器人的其他前沿。同一个大前沿可提供
多个分散观察点。路线准入后的候选才占用并发名额，待确认的 action 也占用名额。

控制器订阅 gateway 交付的每台机器人 `/gateway/received/tbN/tf`，用实时 `map→odom` 把里程计位置转换到 SLAM 地图坐标后
再做 Dijkstra 可达性判断。禁止把 odom 坐标直接当 map 坐标。候选计算从前沿向外枚举有限
邻域，避免旧实现的“地图候选数 × 前沿长度”二次循环阻塞 ROS 执行器。

目标被接受后最多执行 60 仿真秒。成功目标短期降低重访评分，避免 A→B→A 往返；失败目标
释放预留并短期降低评分，地图更新后仍可重试；启动期或瞬态拒绝只释放，不永久拉黑候选。一个前沿组的首选
栅格无效时，会继续尝试同组其他安全栅格，而不是丢弃整个组。

返航也只使用融合地图上验证过的自由空间路径；当前 footprint 被障碍净空膨胀暂时包围时，
先走一条短的地图安全脱困路径，再重新规划充电位，不再发送穿过障碍物的直线临时航点。

建图模式只启动 SLAM Toolbox，不再同时启动 AMCL，确保每台机器人只有一个
`map→odom` 发布源。自定义 multi-robot SLAM 回调会保存最新 scan header，使 SLAM 的 TF
发布线程真正工作。Nav2 使用各自 gateway 交付的融合地图和 Smac 2D；机器人规划器允许 unknown，中央分段目标
必须是具有 0.45 m 障碍净空的已知自由栅格。

主 launch 在机器人生成 10 秒后启动第一套 Nav2，后续机器人按 60 秒错峰，避免多个导航栈
同时初始化造成资源竞争。`nav2_ready_gate` 同时检查所有 `/tbN/navigate_to_pose` action
server 和所有导航生命周期节点；全部 active 后立即启动控制器和评估器，不再固定等待最后一套 Nav2 启动后的额外 60 秒。
门控超时会列出未就绪的 action 并阻止探索带病启动。探索行为树不使用的
`smoother_server` 不再启动；速度平滑器 `velocity_smoother` 仍保留。

P3A.6 候选版本增加滚动空间预约：探索最多三台并发，按当前已交付位姿为停驻机器人保留
0.6 m 动态障碍，并在活动路线之间维持 1.8 m 隔离。每个候选通过路线预约后才占用并发名额，
冲突候选不会遮蔽同一机器人的其他前沿。交给 Nav2 的航点在首个遮挡转角前截断，最长 5 m；
Nav2 goal checker 航点到达容差收紧为 0.02 m，避免短航点在原地被反复判为到达。每轮每机器人复用一次
Dijkstra 距离场，下一轮地图/位姿更新后重新计算。返航开始时取消其他探索动作，尚未确认的
动作在接受回调中也会检查返航状态。固定任务验收条件保持原样，候选算法尚未重新冻结。

新的 P3A.6 候选使用 Nav2 Humble 的 Regulated Pure Pursuit（RPP）替代 DWB，开启
曲率和近障碍限速、预测碰撞检测，最大线速度仍为 0.26 m/s。Nav2 局部/全局圆半径为
0.25 m，以覆盖 Gazebo 偏心底盘的约 0.237 m 后角；可视分段也用于集合和本地返航。
全局电池暂停只在进入 RETURNING 时触发一次取消，连续心跳不再打断恢复动作。
静止机器人占用返航路线时，协调器可派发最近的路线外避让点，并保留最终集合位供恢复。
RPP 配置与旧 DWB 结果属于不同 task-stack 候选，必须新开正式批次验证。

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
使用 0.35 m 路径净空；通过最长 5 m、遮挡转角前截断的可视航点逐段执行。
协调器用已交付融合地图和实时机器人位姿预约路径；相距至少 1.8 m 的无冲突路径默认允许
两台机器人并行，路径冲突时只有低优先级机器人等待，实际位置接近时它会取消当前航段让路并
重新规划。发现机器人拥有首轮优先级，但其他机器人不再等待它完成整个集合。RALLY action 的
卡住超时上限为 30 秒，然后立即重新规划。只有所有机器人位置误差不超过 0.35 m、线速度不超过
0.05 m/s、角速度不超过 0.10 rad/s 并连续保持 5 个仿真秒，协调器才发布 `COMPLETE`。

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
出生充电位，只有在半径 0.5 m 内且速度低于集合静止门槛时才开始充电。定时器会独立检查
到位和静止状态，因此不会依赖某一条 odom 回调；默认充到容量的 80% 就恢复探索。充电不会
重启 SLAM、清空地图或重置任务状态。`--require-charge` 使 smoke 在没有真实发生充电时判失败。

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
10/10 `COMPLETE`、零碰撞，强制充电回归完成两次充电；这些结果属于 gateway 提交时的历史代码状态，
后续 HEAD 修改后需重新生成 manifest 并重跑，P3A 仍待用户验收。

### 9.5 P3A 显式零损 gateway

P3A 使用 `multi_robot_interfaces/GatewayEnvelope` 将地图、位姿、TF、电量、检测和任务命令包装为带发送者、序号、生成时间、TTL、ACK 和载荷长度的消息。`ideal_gateway` 使用本地队列和接收状态存储实现零损交付，`navigation_gateway` 将中央导航命令转换为机器人本地 Nav2 action；源码清单和 ROS graph 均检查中央没有机器人原始 topic/action 直连，也没有机器人 Nav2 对中央 `/merge_map` 的直订阅。运行时审计命令为：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run multi_robot_exploration bypass_audit --robot-count 3 --wait-sec 10
```

正式历史结果位于 `log/p2d_baseline/p3a_formal_gateway_3scenes_v2/`；当前 HEAD 的 P3A.5 需重新生成
带 commit/config/environment manifest 的矩阵。P3B 才会在同一协议上加入固定 delay/loss，当前 P3A 不代表 Wi-Fi 性能结果。

### 9.6 P3B 固定故障 gateway

`ideal_gateway` 现在也支持 P3B 的确定性故障模式，默认参数仍是 `gateway_mode:=ideal`。设置
`gateway_mode:=fault` 后，上行和下行分别经过固定延迟/丢包队列；`fault_seed` 保证同一输入得到
同一事件顺序，`gateway_duplicate_rate` 和 `gateway_reorder_window` 用于重复和乱序测试。地图、
位姿和 TF 继续按序号、TTL 接收，旧版本不会覆盖新版本；中央协调器在这些输入超过
`message_freshness_timeout_sec` 后暂停新的分配。目标检测、导航命令和电池失败消息使用有限重试，
导航命令超过 `navigation_command_deadline_sec` 会中止。

先运行协议门禁：

```bash
export PYTHONPATH="$PWD/src/multi_robot_exploration:$PYTHONPATH"
python3 scripts/run_p3b_fault_matrix.py
```

运行任务 smoke 时可传入 `--gateway-mode fault`、`--uplink-loss-rate`、`--downlink-loss-rate`、
`--uplink-delay-sec`、`--downlink-delay-sec`、`--gateway-seed`、`--gateway-queue-capacity` 和
`--gateway-ledger-path`。账本和
`/gateway/message_events` 都保留每次尝试的消息 ID、序号、生成/入队/准入/发送/交付或丢弃时间、
TTL、重复标记和重试次数。P3B 只验证应用层故障语义，尚未接入 ns-3 Wi-Fi。

P3B.5 当前候选在 FOUND 阶段允许为 RETURNING/CHARGING 机器人从新鲜电池消息中的
充电位规划后续集合点，避免全员恢复 ACTIVE 后才开始分配。该位置只是未来路线起点，
不会覆盖收到的实际位姿；RALLY 派发仍检查实际机体、返航路线预约、ACTIVE 模式和完整
能量预算。集合点不足时，额外地图探查仍须等待电池就绪。受控返航准备在原始起点已知
自由但膨胀净空不足时复用有界脱困规划；未知/占用起点仍拒绝，不清除地图，原 .75m
航段和 50s 准备期限保持。这些候选通过组件检查，完整固定任务与故障验收仍待重跑。
让路机器人正在移动时，其他普通集合航段也可参与原并发预约检查；只有路线分离、
并发名额与能量条件满足才派发，避免不相关的让路动作造成全局串行等待。
临时让路还记录其受益机器人：确认停到让路点后，仅该受益机器人可暂时忽略让路者的
未来接近路线预约，真实停车机体及所有活动路线仍保护；其他跟随者继续服从原优先预约。
当阻挡者需多段移动到新的永久集合点时，请求它移开的机器人也暂让出自己的未来优先权，
让恢复航段能够继续；恢复完成或独立返航让路接管后清理这项关系，仍检查真实机体与路线。

阶段报告见
`ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20260928_p3b.md`；其中区分了
已完成的协议门禁、保留的 ROS fault-mode 失败样本和仍未完成的 Gazebo/ns-3 验收工作。

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
评估器可以继续读取 Gazebo 真值，但不得向控制链发布。`zero-loss finite-rate` baseline 同样经过
gateway，只把交付设为零丢包和零附加时延，同时保留真实候选生成频率；`oracle unlimited` 只作理论
上界，不能恢复旧直连。

P3B 将在此 gateway 上继续加入固定 delay/loss 和逐消息账本；在此之前不要把 P3A 的零损结果
解读为 Wi-Fi 性能结论。

P2B 起只有全体仍参与任务的机器人在不同安全集合位姿连续稳定 5 秒后的 `COMPLETE` 才是完整任务成功；
如果已有机器人故障，剩余机器人集合稳定后发布 `PARTIAL_COMPLETE`，表示任务完成了可用机器人的
部分。评估器将其记录为部分完成而不是完整成功。`FOUND` 和 P1C 的 90% 覆盖率只是过程指标。
当前 TurtleBot3 模型为降低仿真负载关闭了相机；
P2A 真值检测只用于仿真 MVP，P8A 实物前必须恢复真实相机检测适配器，不能把 Gazebo 真值
结果当作实物感知成果。

2026-10-01 安全候选移除了集合中忽略机器人位置的软障碍兜底：无安全路线时触发
停驻机器人让路/目标恢复，不能直接放行无动态障碍约束的长路线。停在中间航点的
健康机器人也可参与通道恢复。碰撞日志及 episode JSON 的 `collision_history` 保存
接触对象、仿真时间和阶段；成功条件和计数不变。该候选尚未通过 P3A.6 固定门禁。

2026-10-01 前沿收益候选使用已交付地图的稀疏射线计数，已知障碍后的未知格不计入
当前观察点收益；探索最多三台，但仍需各自路线通过 1.8 m 预约隔离和动态障碍检查。
集合并发参数不变。新候选需要独立固定门禁；db21e92 的两机器人强制充电回归
（271.6 s COMPLETE、零碰撞、每台一次充电）仅是此前提交的证据。

阻塞恢复现在先验证动态避障可视短段并立即派发阻塞者的移动动作，避免优先等待者
每个 timer 反复分配目标、让阻塞者没有执行机会。此修复仍须独立提交上的正式验证。

2026-10-01 当前采样候选先保留1.2 m 宽间距观察点，再以0.2 m 补充局部替代点，
每组仍最多12个；观察点净空0.45 m不变。派发拒绝零utility/已在航点容差内的目标，
可视导航采用最远安全直线并预约该直线。四台 Nav2 XY 容差为0.02 m，任务稳定
门限仍是0.35 m/0.05 m/s/0.10 rad/s/5 s。此前 bd2f0f2 固定十格是6/10 COMPLETE、
全部零碰撞；当前源码候选尚待独立正式门禁，不能作为已冻结的网络基线。

2026-10-01 消息和避让候选：相关TF/更新源时间通过筛选后才占用原发送窗口，
避免odom/base无关TF或重复消息饿死map/odom；限频、源时间、TTL、新鲜度门限不变。
临时避让选择离等待路线至少0.8 m的最近可达refuge，不再把远离目标当成腾出通道。
7c53717固定十格6/10 COMPLETE、全部零碰撞，四个超时保留；新候选108项组件检查
和构建/源码审计通过，正式矩阵与强制充电仍待完成。

2026-10-01 集结能量候选：电池启用时，主集合派发前检查完整任务路线、最终位姿
返航保留量及稳定等待耗能；不足时生成/gateway/request/tbN/charge候选，通过既有
envelope/可靠传输送达/tbN/gateway/charge_request，由本地电池管理器提前返航充电。
源时间/TTL10 s/去重防迟到重复动作，原自动安全返航及能量/速度/300秒/COMPLETE
门限不变。普通与fault gateway使用同一新命令路径；不能直接发布机器人接收端。
容量目标也不足则明确任务失败。当前124项组件检查/构建/源码审计通过，正式门禁待完成；
baec4e8的失败与post-start中断全部保留，不能作为冻结基线。


2026-10-01 后续：c08ca65 clean lab303在300 s仍RALLY，16碰撞事件；三台同时提前
返航造成tb2/tb3路线冲突。失败episode/graph/日志保留，其他九格和forced未运行。
新候选按就近顺序串行提前返航，RETURNING/CHARGING及请求在途期间不启动下一台，
等待者仍受能量预算限制；127项测试、四包构建、源码审计通过，正式门禁仍待完成。


2026-10-01 最终P3A.6集成门禁通过、待验收：冻结任务栈22c95a7，固定十格全部
COMPLETE/零碰撞，同提交forced303为190.4 s COMPLETE、两台各充电一次、零碰撞/耗尽。
127项测试、四包构建、源码审计与十一图回放通过。正式参数仍为集合并发2、global pause
关闭及300秒/.35 m/.05 m/s/.10 rad/s/5秒门限。之前各段“候选待验证”是历史开发记录，
当前结果见wireless-rl/report/20261001_p3a6_freeze.md与.json。以后改变任务算法或配置
必须重新跑门禁；开发seed结果不替代holdout测试。

2026-10-02 P3B.5通道恢复候选：优先让阻挡机器人沿可视安全短段到完整等待路线外的最近refuge，保留其原最终集合点；没有可行refuge再永久重分配。能量/净空/源新鲜度与路线预约门限不变。281项组件检查、四包构建与源码审计通过；70b6c61的固定lab101超时失败保留，本候选正式矩阵尚未开始，不能称为P3B.5验收通过。

2026-10-02后续P3B.5候选要求最新观测者的临时refuge和实际派发短段终点符合已交付检测范围与已知地图LOS，避免让行后目标lease丢失；仍面对目标、保留完整能量/预约检查。四台Nav2内部BT动作/服务确认有界等待改为500ms（原20ms在多机器人调度下出现确认失败），不是网关命令deadline或任务超时修改。04d23e8失败及夹具操作失败保留；新矩阵未运行，P3B.5未通过。

2026-10-03 P3B.5后续候选重审已执行及等待gateway接受的rally路线，独立返航出现后取消冲突航段，迟到接受仍取消；安全让路只等待自身排空和实际并发名额，并检查其他在途路线，保留原集合目标。消息验收在一个只读DDS context内同时检查scan/merge_map/电池实际callback，保持原QoS和90s共同wall上限并打印待收topic。307组件检查、四包构建、source audit及实际多类型DDS接收/缺数据拒绝通过；3cc5529原固定16碰撞与补充消息超时失败均保留，新完整矩阵尚未运行，P3B.5未通过。

2026-10-03 P3B.5恢复搜索候选：源60秒目标lease过期后保持任务阶段，原地四向扫描后按当前地图前沿搜索；无可行前沿时按已知自由可达格和未访问邻域收益继续安全短段搜索，实际到位后由刚移动机器人重新扫描。visited只表示搜索偏好，不能替代camera检测；过期目标坐标不进入候选计算。同snapshot/visit batch共享ray gain，动态route继续独立检查。真实RETURNING/CHARGING才可抢占已admit普通腿，prospective home staging intent只约束新派发。317检查/构建通过，56479c0固定timeout/0碰撞与强回充PASS保留，尚非完整P3B.5通过。

2026-10-04 P3B.5完成判定候选：协调器每个交付odom超限样本都重置集合保持窗口，避免定时检查漏掉瞬时运动。只读评估器schema9分别记录`coordinator_completion_time_sec`（中央声明）与`completion_time_sec`（原生连续观测合格），在当前集合位与健康参与名单上独立核验原0.35m/0.05mps/0.10radps/5s，并在新原生样本合格后终止；原300s horizon不延长。原生ModelStates无header，proof明确使用observer仿真时间，采样间断超过原pose TTL2s或任一超限样本会重置，不宣称完整物理连续采样。Gazebo真值不进入控制链。中央声明后未合格仍可timeout，不能据声明计入成功。被第二个实际返航取消的idle避让机器人可重选安全refuge，仍检查所有返航/在途路线/真实机体并保留final目标。a63ac0b原固定中央COMPLETE213.7s但原生tb2角速度0.19315radps超限，原5episode失败候选完整保留；338组件检查与四包build通过，新冻结全矩阵待运行，P3B.5未通过。

2026-10-04 P3B.5路线一致性候选：临时refuge已经按受益者原waiting route核验后，保留受益者原集合目标，避免再选新目标使避让证书失去对应路线；永久重分配仍走原恢复分支。普通中间rally航点在新鲜交付检测和当前地图预测LOS/距离合格时朝目标中心，保留导航位置/route/完整能量检查；最终集合yaw、充电staging和本地返航避让不改。预测可见不能代替真实camera确认，不使用过期坐标。348组件检查、四包构建、旁路审计及原AP几何反例通过；2786b14原固定timeout300.4/3charges/0碰撞与5原episode全部保留，本候选须新冻结全矩阵，P3B.5未通过。

2026-10-04 P3B.5派发恢复候选：按最终地图格识别final腿，保留原集合yaw，避免连续集合位与grid-center的量化偏差触发重复请求。充电staging只预约实际在途腿/机体；未执行的future-home路线不当作本地返航，真实RETURNING/CHARGING和已发charge请求仍受保护。目标60s lease内的短暂camera间断不把最后真实观测者调回home staging，本地电量reserve仍可抢占。返航refuge保持到充电后的owner实际派发/到位；若它挡住owner出站，复用普通安全恢复重新避让，并移除local-return例外，使新腿重新执行目标时效/完整能量检查。已停在temporary refuge的未来集合路线延期预约，实际body、pending/accepted航段与真实返航仍保护，避免三机器人等待环。

376组件检查、四包build、source-only旁路审计通过。cab0568原43started/43raw/0碰撞完整保留，其中固定lab3/202 timeout300.2导致失败，707未启动；不能据其13 COMPLETE或1 PARTIAL_COMPLETE宣布P3B.5通过。独立/tmp源码开发lab202从三次失败迭代到COMPLETE230.9/0碰撞/两次charge，原生5.0s保持合格；rooms101开发COMPLETE129.3也只属开发证据，不回填正式格。新正式v40必须新clean commit/push，先同environment/CPU0-19完成全部十fixed原300s/零重试，再启动原27故障case/第一次707及fault27077，最终以同提交完整门禁为准。原参数和启动命令保持，P3B.5仍待完成。

2026-10-04较早P3B.5能量与观测者分配候选（历史规则，已由下面v55规则替代）：在已交付电池启用时，集合点组合先避免让ACTIVE真实观测者返充，再最大化其扣除完整名义预算后的剩余电量；随后比较预计充电台数、串行路线/返航/充电时间，最后按原minimax或total_path路径指标决胜。预算包含去程、独立返航reserve、五秒保持、同伴路线和串行充电等待；无电池上下文时保留原路径分配。RETURNING/CHARGING不享有视觉观测者余量优先权，home仅为未来规划起点，不替代收到的真实位姿。分配只是预测，实际TTL、地图/LOS/净空、机体/在途腿/返航预约、完整绕行能量与本地安全仍逐次检查，不放宽300秒或完成标准。

组合搜索复用距离场、每机器人候选能量和最小预算；先解析观测者，再通过单列候选下界与单调等待闭包剪枝，完整组合使用实际选定值。大自由地图三个组件样例与旧原型分配一致，最慢从6.554秒降为约0.181秒；单次组件测量不代表任务因果加速或最坏时间保证。18个实际收到的AP快照/显式合成电池边界比较通过，非原协调器内部buffer重演。

397组件检查、四包build和source-only旁路审计通过。原834a0fd六started/六raw/0碰撞完整保留：lab101 COMPLETE265.4、lab202 timeout300.4/RALLY导致固定门禁FAIL；所有其余fixed/fullfault/707均未执行。v44开发timeout300.1/一次完成charge/0接触，随后晚返航；v45开发COMPLETE195.8/一次charge/0接触仅为开发证据；v47开发timeout300.0/RALLY仍未合格，保留。无完整current-body串行order时，v48改按未来最终位对后续接近路线的阻挡次数选择恢复顺序，实际机体与安全派发不放宽；v48本身仍timeout300.1/三charge，保留。v49探索偏好纳入前沿终点的返航距离及连续预算缺口，保持有用前沿退路与本地硬reserve。优化后的v49独立开发COMPLETE185.4/charge0/最低22.56212/0接触，原生5.5秒保持合格。全部失败、对照失败及开发source/import/hash/命令单列，均不回填正式固定格/TDI。新v41必须clean commit/push后以相同CPU0–19完成全部十fixed，再启动原27故障case和首次707/fault27077；P3B.5仍待完成。

2026-10-04 P3B.5地图起点与调查安全候选：在原source map之外维护规划副本；仅在原pose/TF 2s、map 5s源时效通过时，把已交付机体位置所在、八邻域全为已知自由且物理对角线≤0.1m的单格孤立占据回波作为自身回波处理。原始地图不改，墙线/连接障碍/未知格不清除；其他机器人实际机体、在途腿、返航与本地Nav2安全继续约束。此为受限回波启发式，不是一般障碍识别或最坏情况安全保证；导航账本保存使用的格、分辨率、origin与原输入源时效。原始occupied/unknown起点函数仍拒绝这类起点；独立规划副本的有界处理由单独反例验证。

目标区调查改为已知地图上的可视短腿，复用实际机体、在途集合与本地返航预约；若完整当前去程/终点返航预算不足，则缩短可选调查而非派发无资金全程goal。peer返航取消已接受或pending调查，晚接受也执行取消。FOUND调查成功不再因尚无最终集合位而被回调提前忽略；调查不能使用过期目标或绕过同gateway。300s、硬reserve、Nav2限制、0.35m/0.05mps/0.1radps/5s完成门槛保持。

原42b099e正式七started/七raw保留：fixed lab101/202 COMPLETE286.7/242.7且0接触，lab303 timeout300.3/FOUND、两charge、6接触；E0 pair正确FAILED/no nav，受控返航两侧仅EXPLORE300.3/300.1安全过程证据。固定FAIL阻止其余七fixed、fullfault与首次707启动。11张原AP快照的纯几何分配均无三机解，tb2原始起点单格100、可达candidate0；条件规划副本重放恢复11张三机解，非原内部buffer/任务重演。两个不改control的附加局部地图诊断均不作为formal证据：v50标签303实际上seed202，RALLY timeout300.1/0接触，绑定错误与实际参数保留；v51实际303 COMPLETE171.6/0接触，未重现单格故障。候选v52 lab303/202独立开发COMPLETE244.8/166.9，v53同source rooms101 COMPLETE126.1，均0接触、原生保持合格；成功开发格不回填正式格。416组件、四包build/source审计通过，P3B.5仍待新clean提交的完整门禁；已验收P3A.6冻结22c95a7保持。

2026-10-04 P3B.5基础设施复验候选：011786e同提交十fixed全部原生合格COMPLETE且零碰撞，但完整批次不能PASS：首次707 ideal COMPLETE148.1s，接下来的fault27077在机器人生成前未取得新鲜原生模型清单，90s原检查超时，episode未开始。原失败、所有其余自然结束结果、命令/图/账本/源哈希在report/20261004_p3b5_model_inventory_failed_candidate.json保留，未回填或挑成功。

三个网络中断后遗留的v11只读观察器按原输出路径、已消失owner与已释放master核对后仅用SIGINT关闭；复用domain产生的旧流混合尾部不当作原v11任务证据。新的只读观察器在导入rclpy前绑定Linux父进程死亡信号，托管runner传入确切owner PID以闭合初始化竞态；正常退出仍保存原观察记录。该机制不作用于任务控制节点。两个真实ROS观察器父进程退出检查通过。

run_p3b5_tasks默认domain base改为30；run_p3b5_return_probe默认90。domain范围提前校验0..232，严格使用声明的连续ID，不再取模改写；完整矩阵30..70，物理探针90/91。并发批次须事先分配互不重叠的domain范围及Gazebo master；下一冻结全批次使用显式20..95。生成器仅增加ModelStates消息和GetModelList请求/响应/超时计数，分开报告无清单和实体重名，原90s总检查、单次创建、原生存在性确认保持。独立lab101裸世界诊断在domain201与18均约2s收到模型/clock与服务成功，未复现原失败。Linux默认临时端口范围与高domain的重叠是配置风险，不能据此宣称已证明失败根因（[ROS2 Humble官方domain说明](https://github.com/ros2/ros2_documentation/blob/humble/source/Concepts/Intermediate/About-Domain-ID.rst)）。

425组件检查、四包build和source旁路审计通过；controller、故障manifest、300s、完成门限与安全保留量字节/参数不变。707已经在011786e暴露，后续只能称同策略基础设施复验，不称首次或全新未暴露heldout；保留首次ideal与任务前失败，fault27077的首次声明不改。新clean提交仍须先跑全十fixed再完整57episode门禁；P3B.5尚未通过，P3A.6已验收冻结22c95a7保持，无ns3/WiFi/RL。

2026-10-04 P3B.5 v55集合分配组件改进：避免ACTIVE观测者返充仍为首位；其后先比较所需充电台数和名义串行行程/返充时间，再比较额外观测者电量余量，最后按minimax/total_path决胜。额外余量不再迫使已满足完整预算的同伴充电或绕行。17相关/427全组件、四包5.24s构建、source审计通过；旧新自由图夹具额外位移8→0m、可避免充电1→0台，低电量观测者保护保留，非仿真因果结果。证据见report/20261004_p3b5_charge_time_assignment_component.json。v43原57失败保留，尚未通过P3B.5；需独立开发回归和新冻结完整矩阵，算法改变后的留出协议使用新未暴露组合，不能重用707声称未暴露验证。

2026-10-04 P3B.5 v55独立开发回归通过，冻结cc21503：force ideal原生COMPLETE297.3s/两机各charge1；zero ideal/fault原生COMPLETE235.6/215.7s/各总charge1；force断网fault RALLY timeout300.3s，但两机各charge1、最低8.307、零碰撞。四原始结果、账本/graph/source/AP快照在report/20261004_p3b5_charge_time_assignment_development.json保留，不回填v43原57失败，开发仍非正式验收。force ideal仅2.7s余量，名义优化不是最坏时限保证。

新正式v56协议在首次运行前改用p3b5_holdout809.world/seed809/fault28091/目标(4.4,-3.4)/3r/E45；这是交错隔断、中央开口、旋转块与柱的新拓扑，静态SDF/visual一致、十box和0.45m净空连通检查通过，尚未运行新场景。707及旧27077首次声明/暴露原样保留为历史，不能称未见测试。主矩阵27case/41unique、同提交十fixed和六安全探针、300s/.35m/.05mps/.1radps/5s、原开发fault17011和已有故障强度保持。新冻结须先检查force ideal真实native保持，再全十fixed，随后含新留出的完整主矩阵；P3B.5尚未完成，无ns3/RL。

2026-10-04 v56冻结前检查：429组件12.92s、四包构建5.29s、source-only3r旁路0违规，27case/41unique清单validate-only通过，未启动Gazebo。runner manifest现在按实际选择case记录seed，不再硬编码707；严格gate新增预声明world/seed/fault及world/control纯bytes SHA验证。native_completion_ok与episode_ok两函数相对cc21503完全相同，300s/.35/.05/.1/5s与安全阈值未放宽。
