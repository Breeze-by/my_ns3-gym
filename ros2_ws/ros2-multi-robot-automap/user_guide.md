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
`termination_reason=coverage_reached`；180 仿真秒未达到则记录 timeout。输出 schema v5
还包含 75%/80%/90%/95% 首次达到时间、每台机器人起终点、导航目标结果、路径、碰撞、
搜索重叠，以及目标是否发现、发现机器人、发现时间、发现时覆盖率、目标位置和检测规则。
从 schema v5 起，episode 内任一接触都会使权威 `success=false`，即使状态机随后到达
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
episode 标识见 `report/20260917_p2b.md`。P2B 当前等待用户验收；P2C 尚未开始。

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

当前闭环为：

```text
robot 上行：/tbN/odom、/tbN/scan、/tbN/map
server 决策：headquarters_control 基于 /merge_map 分配目标
server 下行：/tbN/navigate_to_pose 或 /tbN/cmd_vel
```

这些都是当前理想通信直连，不是未来网络实验可保留的路径。P3A 必须统一替换以下边界：

```text
上行：本地地图版本/增量、位姿、电量、任务状态、目标检测 -> gateway -> 中央接收信息存储
下行：融合地图版本/相关区域、探索/返航/集合命令 -> gateway -> 机器人本地适配器
```

中央协调器和 `merge_map` 届时不能继续直订 `/tbN/map`、`/tbN/odom`、`/tbN/tf` 或原始
目标检测，中央也不能直接调用 `/tbN/navigate_to_pose`。当前 1–3 号机器人的 Nav2 全局
代价图还直订 `/merge_map`，它也必须改为 gateway 成功交付的融合地图，或明确退回本地地图。
评估器可以继续读取 Gazebo 真值，但不得向控制链发布。`ideal/unlimited` baseline 同样经过
gateway，只把交付设为零丢包和零附加时延，不能恢复旧直连。

在 P3 之前继续按 `IMPLEMENTATION_PLAN.md` 完成：

```text
P2C 电池/返航/充电
P2D 跨 world/目标/能量场景的完整理想通信任务基线
```

P2B 起只有全体机器人在不同安全集合位姿连续稳定 5 秒后的 `COMPLETE` 才是任务成功；
`FOUND` 和 P1C 的 90% 覆盖率只是过程指标。当前 TurtleBot3 模型为降低仿真负载关闭了相机；
P2A 真值检测只用于仿真 MVP，P8A 实物前必须恢复真实相机检测适配器，不能把 Gazebo 真值
结果当作实物感知成果。
