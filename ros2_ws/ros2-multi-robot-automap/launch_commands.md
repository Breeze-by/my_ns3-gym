# 多机器人任务启动命令速查

本文只记录当前代码可直接使用的启动入口和参数。完整架构、实现说明和实验结果见
[`user_guide.md`](user_guide.md)。当前推荐入口是：

```text
multi_robot/gazebo_multirobot_mapping_with_nav2.launch.py
```

它同时启动 Gazebo、1–4 台 TurtleBot3、在线 SLAM、Nav2、地图融合、中央协同探索和
P2C 本地电池/充电管理；可选目标检测与 P2B 集结任务。手动运行默认同时打开贴地的 Gazebo
重点区域标记和每机器人实时状态栏。

维护要求：以后新增或修改 launch 参数、默认组件或推荐运行方式时，必须在同一个提交中同步
更新本文的默认命令和参数表。

## 1. 每个新终端先执行

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
```

只有源码修改或首次检出后才需要重新编译：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
colcon build --symlink-install \
  --packages-select multi_robot merge_map multi_robot_exploration
source install/setup.bash
```

## 2. 默认手动启动：三机器人完整搜索与集结任务

该命令打开 Gazebo，显示红色圆柱目标。机器人自主探索；确认目标后，最多两台机器人执行
互不冲突的并发短航段，最终全部聚集在目标附近的不同安全位置。

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=my_world.world \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_task_regions:=true \
  enable_status_panel:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false \
  auto_save_map:=false \
  gazebo_seed:=101 \
  nav2_ready_timeout_sec:=360.0 \
  enable_target_detection:=true \
  enable_rally:=true \
  enable_battery:=true \
  battery_initial_energy:=24.0 \
  target_x:=-4.0 \
  target_y:=4.0
```

两机器人只需修改：

```text
robot_count:=2
```

`gazebo_seed` 影响 Gazebo 随机过程，不会随机目标位置。目标位置始终由 `target_x`、
`target_y` 指定。当前正式验证位置是 `my_world.world` 中的 `(-4, 4)`。

## 3. 常用运行模式

### 3.1 只做协同探索和在线建图

不生成搜索目标，也不执行集结：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=my_world.world \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false \
  auto_save_map:=false \
  gazebo_seed:=101 \
  enable_target_detection:=false \
  enable_rally:=false \
  enable_battery:=true
```

### 3.2 只看合并地图

关闭 Gazebo GUI，打开一个显示 `/merge_map` 的全局 RViz，计算负载通常低于同时打开两个
图形界面：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=my_world.world \
  robot_count:=3 \
  enable_gzclient:=false \
  enable_task_regions:=false \
  enable_status_panel:=false \
  enable_rviz:=false \
  enable_merge_rviz:=true \
  auto_save_map:=false \
  gazebo_seed:=101 \
  enable_battery:=true
```

### 3.3 只验证目标检测，不执行集结

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=my_world.world \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false \
  auto_save_map:=false \
  gazebo_seed:=101 \
  enable_target_detection:=true \
  enable_rally:=false \
  enable_battery:=true \
  target_x:=-4.0 \
  target_y:=4.0
```

### 3.4 强制发生一次充电的完整任务

以下配置把所有机器人初始能量进一步降到 18；smoke 的 `--require-charge` 会在没有实际完成
充电时判失败。主 launch 的常规默认值现在为容量 60、初始能量 24；25 在三机器人同时返航时会造成
充电区拥堵，因此只保留为边界失败证据，不作为默认值。

```bash
python3 scripts/ros_smoke_test.py \
  --world my_world.world --robot-count 2 --gazebo-seed 303 \
  --startup-timeout 300 --message-timeout 90 --shutdown-timeout 60 \
  --evaluation-duration 300 --coverage-threshold 0 \
  --evaluation-wait-timeout 600 --target-detection --rally \
  --battery --require-charge --battery-initial-energy 18 \
  --target-x -4 --target-y 4 \
  --episode-id manual_p2c_forced_charge
```

### 3.5 P2D 完整理想通信基线

场景、目标和初始电量统一保存在 `scripts/p2d_scenarios.json`。默认 runner 串行运行三个场景的
seeds 101/202/303，并追加一次走廊场景双机器人交叉检查；每轮上限均为 300 仿真秒：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 scripts/run_p2d_baseline.py \
  --seeds 101 202 303 \
  --run-id p2d_formal_ideal_3scenes \
  --ros-domain-base 130
```

当前冻结矩阵为：

| 场景 | 目标 `(x, y)` | 初始能量 |
| --- | --- | --- |
| `my_world.world` | `(-4.0, 4.0)` | `40.0` |
| `p1c_rooms.world` | `(5.0, 3.0)` | `40.0` |
| `p1c_corridors.world` | `(-4.5, -0.5)` | `45.0` |

该正式 runner 显式固定满电容量为 `100.0`，因此历史 P2D 结果不受手动启动默认容量下调影响。

`--validate-only` 只检查配置和 world 文件；目标真值空闲、三集合位可达和最小间距由
`test_p2d_scenario_targets_are_free_and_rallyable` 自动验证。正式结果写入
`log/p2d_baseline/<run-id>/summary.json` 和 `summary.csv`。runner 的启动门限默认为 600 墙钟秒，
以包含三套 Nav2 的固定错峰启动；这不改变每轮 300 仿真秒任务上限。

2026-09-18 的最终基线由 `p2d_formal_ideal_energy40_v5` 中 lab/rooms 六项，以及
`p2d_formal_corridors_energy45_v6` 中走廊三 seeds 和双机器人交叉检查四项组成；10 项均为
`COMPLETE`、零碰撞。走廊 40 能量的双机器人检查会在任务后段返充并于 300 秒超时，因此在
正式批次前把该场景统一校准为 45；主 launch 的通用默认值仍为 40。

### 3.6 P3A 显式零损 gateway

主 launch 现在默认启动一个 `ideal_gateway`、每台机器人一个 `navigation_gateway`，所有
中央地图/位姿/TF/电量/检测输入和 Nav2 目标都经过 `GatewayEnvelope`。地图合并消费
`/gateway/received/tbN/map`，机器人全局代价图消费 `/tbN/gateway/merge_map`，中央只使用
`/gateway/received/...` 接收状态；P3A 不改变理想链路的零丢包、零附加时延语义。

源码和运行时旁路审计可单独执行：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run multi_robot_exploration bypass_audit --robot-count 3 --wait-sec 10
```

历史 gateway 矩阵使用 `scripts/run_p2d_baseline.py` 的同一场景配置，运行 ID 为
`p3a_formal_gateway_3scenes_v2`；结果写入 `log/p2d_baseline/<run-id>/`。该批次 10/10
`COMPLETE`、零碰撞，另有 `p3a_gateway_forced_charge_2r_seed303` 以初始能量 18 完成两次
充电并 `COMPLETE`。由于之后 HEAD 修改了协调器、电池和净空逻辑，当前 P3A.5 必须在冻结
commit 上重跑并写入 manifest，不能把此历史目录直接当成当前验收证据。

## 4. 切换 Gazebo world

当前已验证的场景：

| 参数值 | 场景特点 |
| --- | --- |
| `my_world.world` | 当前目标搜索和 P2B 集结的正式场景 |
| `p1c_open.world` | 开放区域和离散障碍 |
| `p1c_rooms.world` | 多房间、门洞和遮挡 |
| `p1c_corridors.world` | 长走廊、绕行和支路 |

例如，在房间地图上运行三机器人协同探索：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  world:=p1c_rooms.world \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false \
  auto_save_map:=false \
  gazebo_seed:=202 \
  enable_battery:=true
```

`world` 只接受 `src/multi_robot/worlds/` 中的文件名，不接受绝对路径。新增自定义 world 后
重新编译 `multi_robot`：

```bash
colcon build --symlink-install --packages-select multi_robot
source install/setup.bash
```

在其他 world 上启用目标和集结时，需要自行选择位于真值地图范围内、无遮挡、可到达且周围
有足够集合空间的 `target_x/target_y`。不能直接假定 `(-4, 4)` 对所有地图都有效。

### World 与地图文件的区别

- `world:=xxx.world`：选择 Gazebo 环境、墙体和障碍物。
- `/tbN/map`：每台机器人运行时由 SLAM 实时生成的地图。
- `/merge_map`：多台机器人地图的实时融合结果。
- `.yaml/.pgm`：保存后的静态地图；当前主任务入口不接收它们。

仓库中的 `gazebo_multirobot_navigation.launch.py` 是旧的预建图入口，仍硬编码
`my_world.world`、4 台机器人出生点和固定地图文件，不是当前 P1/P2 任务的推荐入口。

## 5. 常用参数

查看代码当前声明的完整参数列表：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  --show-args
```

### 场景、机器人和界面

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `world` | `my_world.world` | `multi_robot/worlds` 中的文件名 |
| `robot_count` | `2` | 机器人数量，范围 1–4 |
| `gazebo_seed` | `1` | Gazebo 随机种子 |
| `enable_gzclient` | `true` | Gazebo 图形界面 |
| `enable_task_regions` | `true` | 在 Gazebo 中绘制起始/充电、检测和集合区域 |
| `enable_status_panel` | `true` | 打开实时机器人状态栏 |
| `enable_rviz` | `false` | 每台机器人各开一个 RViz，通常不要开启 |
| `enable_merge_rviz` | `true` | 单个全局合并地图 RViz |
| `enable_drive` | `false` | 启动旧的手动 drive 辅助节点 |
| `use_sim_time` | `true` | 使用 Gazebo 仿真时间 |
| `auto_save_map` | `true` | 定期保存合并地图；演示和 smoke 建议关闭 |
| `spawn_timeout` | `90.0` | 单台机器人等待 spawn 服务的墙钟秒数 |
| `nav2_ready_timeout_sec` | `180.0` | 等待所有 Nav2 栈 active 的墙钟秒数 |
| `exploration_goal_timeout_sec` | `60.0` | 单个探索/集合 action 的仿真秒上限 |

Gazebo GUI 和全局 RViz 建议二选一。三机器人冷启动时可把
`nav2_ready_timeout_sec` 设置为 `360.0`，它只是失败上限，不是固定等待时间。该 launch
参数必须写成浮点数；例如 `360` 会被 ROS 解析为整数并导致 Nav2 就绪门控启动失败。

### 目标检测与集结

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_target_detection` | `false` | 生成红色目标并启动仿真检测器 |
| `enable_rally` | `false` | 确认目标后停止探索并执行集结 |
| `target_x`, `target_y` | `-4.0`, `4.0` | 目标 world 坐标；不会随机生成 |
| `target_max_distance_m` | `3.0` | 最大检测距离 |
| `target_field_of_view_deg` | `90.0` | 水平检测视场角 |
| `target_confirmation_frames` | `3` | 连续可见多少帧后确认目标 |
| `rally_position_tolerance_m` | `0.35` | 最终位置误差上限 |
| `rally_linear_tolerance_mps` | `0.05` | 最终线速度上限 |
| `rally_angular_tolerance_radps` | `0.10` | 最终角速度上限 |
| `rally_hold_sec` | `5.0` | 全体满足条件后的连续保持时间 |
| `rally_max_retries` | `2` | 初次集合 action 失败后的重试次数 |

### 电池、返航和充电

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_battery` | `true` | 启动每机器人一个本地电池管理器 |
| `battery_capacity` | `60.0` | 满电容量 |
| `battery_initial_energy` | `24.0` | episode 初始能量；默认让探索较早触发返航 |
| `battery_move_cost_per_m` | `1.0` | 每行驶 1 m 的能量成本 |
| `battery_idle_cost_per_sec` | `0.02` | 每仿真秒基础能量成本 |
| `battery_return_safety_margin` | `5.0` | 预计返航成本外的安全余量 |
| `battery_charge_duration_sec` | `10.0` | 在充电位静止后恢复到目标电量所需仿真秒数 |
| `battery_charge_radius_m` | `0.5` | 充电位判定半径；允许 Nav2 到达误差仍进入充电 |
| `battery_charge_target_fraction` | `0.8` | 充到容量的 80% 后恢复探索 |
| `battery_return_timeout_sec` | `120.0` | 返航超时 |
| `battery_charge_timeout_sec` | `60.0` | 充电超时 |

当前 `c_tx=0`；P3 有真实消息字节账本后才校准通信能耗。每台机器人使用自己的出生点作为
非重叠充电位，低电量返航是本地硬安全行为，不由中央或后续 RL 覆盖。

`enable_rally:=true` 必须与 `enable_target_detection:=true` 一起使用。Gazebo 会显示红色圆柱
目标和红色贴地检测边界；中央发布 `/rally_assignments` 后还会显示橙色集合点。

### 评估器

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_task_evaluator` | `false` | 启动只读真值评估器 |
| `evaluation_episode_id` | `episode` | 输出文件的 episode 名称 |
| `evaluation_output_dir` | `/tmp/multi_robot_evaluation` | CSV/JSON 输出目录 |
| `evaluation_duration_sec` | `0.0` | 仿真超时；0 表示等到外部退出 |
| `evaluation_coverage_threshold` | `0.0` | 正确自由空间覆盖率终止阈值 |
| `evaluation_stop_on_target_found` | `false` | 在 `FOUND` 后结束评估 |
| `evaluation_stop_on_task_complete` | `false` | 在 `COMPLETE`/`FAILED` 后结束评估 |

手工演示通常不需要评估器。正式、有界运行优先使用下一节的 smoke 工具，它会管理结果文件和
进程退出。

## 6. Headless 自动验证

项目 Python 命令必须在 `ns3gym` conda 环境中运行：

```bash
source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh
conda activate ns3gym
export PYTHONNOUSERSITE=1
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
```

三机器人完整 P2B 验证：

```bash
python scripts/ros_smoke_test.py \
  --world my_world.world \
  --robot-count 3 \
  --gazebo-seed 101 \
  --startup-timeout 360 \
  --message-timeout 90 \
  --shutdown-timeout 60 \
  --evaluation-duration 300 \
  --coverage-threshold 0 \
  --evaluation-wait-timeout 480 \
  --target-detection \
  --rally \
  --target-x -4 \
  --target-y 4 \
  --target-max-distance 3 \
  --target-field-of-view 90 \
  --target-confirmation-frames 3 \
  --episode-id manual_p2b_seed101
```

输出位置：

```text
log/smoke/                 原始 launch 日志
log/evaluation/*.json     结构化结果
log/evaluation/*.csv      单行表格结果
```

P1C 跨 seed、跨 world 探索评估（`zero_loss_finite_rate`，不是 oracle unlimited）：

```bash
python scripts/run_ideal_baseline.py \
  --world p1c_corridors.world \
  --seeds 101 202 303 \
  --robot-count 3 \
  --duration 180 \
  --coverage-threshold 0.90 \
  --goal-timeout 60 \
  --message-timeout 90 \
  --run-id manual_corridors_3r
```

正式实验必须把命令、commit、参数、成功和失败结果追加到 wireless-rl 的 `log.md`。

## 7. 运行时查看状态

主 launch 默认打开“多机器人任务状态”窗口，直接显示全局任务阶段，以及每台机器人的
当前动作、Nav2 状态、电池、电量、位置、线速度和角速度。Gazebo 中默认显示蓝色共同
起始/充电区和绿色独立充电位；启用目标检测后显示红色检测范围，生成集合分配后显示橙色
集合位姿。这些标记没有 collision，不影响传感器和导航。

服务器或自动化运行可传入：

```text
enable_status_panel:=false enable_task_regions:=false
```

命令行话题仍可用于核对原始数据。在另一个已执行第 1 节环境初始化的终端运行：

```bash
ros2 topic echo --qos-durability transient_local \
  /task_state std_msgs/msg/String
```

状态顺序：

```text
EXPLORE -> FOUND_UNCONFIRMED -> FOUND -> RALLY -> COMPLETE
```

查看目标确认事件和最终集合点：

```bash
ros2 topic echo --qos-durability transient_local --once \
  /target_detection std_msgs/msg/String

ros2 topic echo --qos-durability transient_local --once \
  /rally_assignments std_msgs/msg/String
```

查看某台机器人的当前能量、模式和累计充电次数：

```bash
ros2 topic echo --qos-durability transient_local --once \
  /tb1/battery_state std_msgs/msg/String
```

查看地图、机器人速度和 Nav2 状态：

```bash
ros2 topic hz /merge_map
ros2 topic hz /tb1/cmd_vel
ros2 lifecycle get /tb1/controller_server
ros2 lifecycle get /tb1/planner_server
ros2 lifecycle get /tb1/bt_navigator
```

正常启动后主终端应出现：

```text
All N Nav2 stacks are active.
Nav2 ready; starting cooperative exploration.
```

## 8. 退出和常见注意事项

- 在启动终端按 `Ctrl-C`，等待 Gazebo 和 ROS 子进程退出。
- 不要在另一个仿真实例仍运行时启动同一 ROS domain；需要并行运行时为所有相关终端设置同一个
  独立值，例如 `export ROS_DOMAIN_ID=73`。
- 如果三机器人启动偶发超时，先重试一个干净 ROS domain，并检查日志中点名的 Nav2
  lifecycle；不要绕过就绪门控。
- `enable_rviz:=false` 只关闭每机器人 RViz，不会关闭全局 RViz；完全关闭还必须设置
  `enable_merge_rviz:=false`。
- 目标只是 Gazebo 可视标记，没有 collision，不会改变 lidar 地图或成为障碍物。
