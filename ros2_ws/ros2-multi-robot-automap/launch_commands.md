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
colcon build --symlink-install --packages-select \
  multi_robot_interfaces multi_robot merge_map multi_robot_exploration
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
  battery_initial_energy:=40.0 \
  target_x:=-4.0 \
  target_y:=4.0
```

两机器人只需修改：

```text
robot_count:=2
```

这里显式使用 `40.0` 是为了让三机器人手动演示有足够的返航余量。当前代码默认值也已经是
`40.0`；低于这个值只用于低电量/充电压力测试。电池管理器会按“当前任务路径 + 保守返航路径
+ 安全余量”做分配前预算，单台返航或故障时总部只暂停/移除该机器人，健康机器人继续执行。
看到状态栏三行都显示“故障”时，先检查权威原因：

```bash
ros2 topic echo /task_state --once
ros2 topic echo /task_failure --once
ros2 topic echo /robot_failure --once
ros2 topic echo /tb1/battery_state --once --full-length --field data
ros2 topic echo /tb2/battery_state --once --full-length --field data
ros2 topic echo /tb3/battery_state --once --full-length --field data
```

状态栏按逐机器人 `battery_state.mode` 显示活动/返航/充电/故障；全局 `/task_state=FAILED` 只表示
任务本身终止，不再把全局失败误画成所有机器人故障。`/robot_failure` 会记录被隔离的机器人、
原因和剩余参与机器人数量。`battery_initial_energy:=18.0` 只用于两机器人强制
充电 smoke，不建议直接套用到三机器人完整任务。

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
充电时判失败。主 launch 的常规默认值现在为容量 60、初始能量 40；25 在三机器人同时返航时会造成
充电区拥堵，因此只保留为边界失败证据，不作为默认值。

```bash
/usr/bin/python3 scripts/ros_smoke_test.py \
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
/usr/bin/python3 scripts/run_p2d_baseline.py \
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

### 3.7 P3A.5 当前 task-stack 重验证

P3A.5 runner 会为每个 episode 保存尝试记录、启动日志和 ROS graph 快照，并在 summary 中写入
`task_stack_frozen_commit`、源码/配置哈希和环境版本。旁路审计还支持将快照写入指定文件：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run multi_robot_exploration bypass_audit --robot-count 3 \
  --wait-sec 10 --graph-output /tmp/p3a_graph.json
```

正式批量入口是 `scripts/run_p2d_baseline.py`。只有完整矩阵全部 `COMPLETE`、零碰撞、零基础
设施失败且 graph audit 通过时，才将 manifest 中的提交冻结为后续 P3B/P4 基线。当前候选结果
和失败保留规则见 `wireless-rl/report/20260923_p3a5.md`。

### 3.8 P3A.5 held-out 算法消融

`scripts/run_p3a5_ablation.py` 使用 `scripts/p3a5_heldout_scenarios.json` 中冻结的未调试
种子、目标和场景，四个变体只切换 rally 算法开关；评估器的 `COMPLETE`、零碰撞、姿态/速度、
电量和 300 秒规则保持一致：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
/usr/bin/python3 scripts/run_p3a5_ablation.py --run-id p3a5_heldout_20260925
```

变体是完整算法、去掉最长路径目标、去掉地图安全顺序搜索、去掉全局电池暂停并允许两条并发
rally 路线。脚本会为每个变体保存独立 manifest、episode JSON、graph audit 和汇总文件；
不得在看到结果后修改清单或成功规则。

### 3.9 P3B 固定故障 gateway

P3B 仍使用 `GatewayEnvelope`，但 `ideal_gateway` 可以切换到确定性的应用层故障模型。上、下行
分别设置固定延迟和丢包率；目标检测、导航命令和电池失败消息使用有限 ACK 重传，所有尝试写入
`gateway_message_events`，可选 JSONL 账本包含 `source_time`、`enqueue_time`、`admit_time`、
`tx_time`、`delivery_time/drop_time`、消息 ID、序号和尝试次数。默认 `gateway_mode:=ideal` 保持
P3A 零损行为。

先运行不依赖 Gazebo 的固定矩阵门禁：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONPATH="$PWD/src/multi_robot_exploration:$PYTHONPATH"
/usr/bin/python3 scripts/run_p3b_fault_matrix.py
```

故障任务 smoke 可在现有命令上增加参数，例如 10% 上行丢包、0.5 秒下行延迟、固定 seed 和
JSONL 账本：

```bash
/usr/bin/python3 scripts/ros_smoke_test.py \
  --robot-count 2 --world my_world.world --gazebo-seed 101 \
  --evaluation-duration 300 --target-detection --rally \
  --gateway-mode fault --mission-mode rally --gateway-seed 20260925 \
  --uplink-loss-rate 0.10 --downlink-delay-sec 0.5 \
  --gateway-max-retries 2 \
  --gateway-ledger-path log/p3b_fault_seed101.jsonl
```

`mission_mode` 固定为 `coverage`、`target` 或 `rally`，并与评估器终止条件保持一致。100% 丢包
时目标检测不会进入 `RALLY`；导航命令在 deadline 后中止，不能无限等待。P3B 只验证确定性故障和
消息语义，不宣称已经接入 ns-3 Wi-Fi。需要测试队列溢出时设置
`gateway_queue_capacity:=N`；当前实现把默认 0 转成每方向 4096 条在途消息，正数用于显式限制容量。

P3B launch 参数完整表：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `gateway_mode` | `ideal` | `ideal` 或 `fault` |
| `mission_mode` | `auto` | `coverage`、`target`、`rally`；`auto` 从启用的任务功能推导 |
| `gateway_seed` | `1` | 固定故障 seed |
| `uplink_loss_rate` | `0.0` | 上行丢包概率，范围 `[0,1]` |
| `downlink_loss_rate` | `0.0` | 下行丢包概率，范围 `[0,1]` |
| `uplink_delay_sec` | `0.0` | 上行固定仿真延迟 |
| `downlink_delay_sec` | `0.0` | 下行固定仿真延迟 |
| `gateway_duplicate_rate` | `0.0` | 重复概率，范围 `[0,1]` |
| `gateway_reorder_window` | `0` | 乱序窗口；`0` 或 `1` 表示关闭 |
| `gateway_ack_timeout_sec` | `1.0` | 可靠消息 ACK 等待时间 |
| `gateway_max_retries` | `2` | 可靠消息最大重试次数 |
| `gateway_queue_capacity` | `0` | 每方向队列参数；当前 gateway 的 0 使用 4096 默认容量，正数表示显式容量 |
| `gateway_ledger_path` | 空 | 可选 JSONL 账本路径 |
| `message_freshness_timeout_sec` | `5.0` | 地图/位姿/TF 超时后暂停中央新分配 |
| `navigation_command_deadline_sec` | `90.0` | 导航命令超过 deadline 后 abort |

## 4. 切换 Gazebo world

当前已验证的场景：

| 参数值 | 场景特点 |
| --- | --- |
| `my_world.world` | 当前目标搜索和 P2B 集结的正式场景 |
| `p1c_open.world` | 开放区域和离散障碍 |
| `p1c_rooms.world` | 多房间、门洞和遮挡 |
| `p1c_corridors.world` | 长走廊、绕行和支路 |
| `p3a5_holdout.world` | P3A.5 未调试 holdout；目标 `(4.4, 3.4)`，种子 404/505；不属于 P2D 正式矩阵 |

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

仓库还保留 `maze.sdf`、`multi_empty_world.world`、`turtlebot3_world.world` 和 `world_01.world`；
它们没有当前任务的冻结目标、集合位或正式验证记录，启动前不要把它们当成 P2D/P3A.5 场景。

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
参数接受整数或浮点数；文档示例使用 `360.0` 只是为了和其他秒参数保持一致。

### 目标检测与集结

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_target_detection` | `false` | 生成红色目标并启动仿真检测器 |
| `enable_rally` | `false` | 确认目标后停止探索并执行集结 |
| `target_x` | `-4.0` | 目标 world x 坐标；不会随机生成 |
| `target_y` | `4.0` | 目标 world y 坐标；不会随机生成 |
| `target_max_distance_m` | `3.0` | 最大检测距离 |
| `target_field_of_view_deg` | `90.0` | 水平检测视场角 |
| `target_confirmation_frames` | `3` | 连续可见多少帧后确认目标 |
| `rally_position_tolerance_m` | `0.35` | 最终位置误差上限 |
| `rally_linear_tolerance_mps` | `0.05` | 最终线速度上限 |
| `rally_angular_tolerance_radps` | `0.10` | 最终角速度上限 |
| `rally_hold_sec` | `5.0` | 全体满足条件后的连续保持时间 |
| `rally_max_retries` | `2` | 初次集合 action 失败后的重试次数 |
| `rally_goal_timeout_sec` | `30.0` | 单个集合 action 卡住多久后取消并重新规划 |
| `rally_assignment_objective` | `minimax` | 集合分配目标：`minimax` 或 `total_path` |
| `use_map_safe_rally_order` | `true` | 按当前地图和动态占位检查集合顺序 |
| `global_battery_rally_pause` | `false` | 是否在安全返航时暂停其他集合航段；默认只暂停返航机器人 |
| `rally_max_concurrent` | `2` | 同时派发的无冲突集合航段上限；路径冲突时自动让低优先级机器人等待或让路 |

当前集合策略预约动态避障路线，并发送最长 5 m、转角前截断的可视航点；
Nav2 action 失败、实时位置发生冲突或机器人需要让路时会缩短航段并重新规划；
单个集合 action 卡住 30 秒会被取消并触发恢复。需要最保守串行调试时可显式设置
`rally_max_concurrent:=1`。

P3A.6 候选控制器采用滚动路线预约：探索最多三台机器人并发，只有经过停驻位置避让和
1.8 m 路线隔离检查的航段才能放行。共享通道等待已有路线释放，候选冲突时尝试其他前沿；
可视航点最长 5 m，在遮挡转角前分段。Nav2 的航点到达容差为 0.02 m，任务 COMPLETE
仍要求原来的 0.35 m/速度门限/连续 5 s。任何机器人返航时取消其他探索航段，待返航结束再
恢复分配。当前仍需通过 P3A.6 完整固定矩阵才能作为网络实验冻结基线。

当前 P3A.6 的下一版候选采用 RPP 控制器（最大线速度 0.26 m/s，预测碰撞检测开启），
局部与全局 costmap 半径为 0.25 m；集合和本地返航也使用最长 5 m 的可视航点。
返航通道被停驻机器人占用时，先让该机器人到路线外临时避让位，再恢复最终集合任务。
每次进入 RETURNING 只触发一次全局取消，周期状态消息不会反复打断让路；返航者进入
充电后，已到达避让位的机器人恢复原最终目标。串行/全局暂停的 RPP 诊断为零碰撞但超时；
`rally_max_concurrent:=2` 与 `global_battery_rally_pause:=false` 的 lab/3r/101 定向回归
已在 235.2 s COMPLETE、零碰撞。完整矩阵尚待验证，此配置还不是已冻结的网络基线。

### 电池、返航和充电

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `enable_battery` | `true` | 启动每机器人一个本地电池管理器 |
| `battery_capacity` | `60.0` | 满电容量 |
| `battery_initial_energy` | `40.0` | 每台机器人初始能量；18/24 可显式用于低电量压力测试 |
| `battery_move_cost_per_m` | `1.0` | 每行驶 1 m 的能量成本 |
| `battery_idle_cost_per_sec` | `0.02` | 每仿真秒基础能量成本 |
| `battery_return_safety_margin` | `8.0` | 预计返航成本外的安全余量 |
| `battery_charge_duration_sec` | `6.0` | 在充电区域内稳定后恢复到目标电量所需仿真秒数 |
| `battery_charge_radius_m` | `0.8` | 充电区域半径；机器人进入该区域即可停止返航并开始稳定充电 |
| `battery_charge_target_fraction` | `0.8` | 充到容量的 80% 后恢复探索 |
| `battery_return_timeout_sec` | `180.0` | 返航超时 |
| `battery_return_path_factor` | `2.0` | 返航路径相对直线距离的保守倍数 |
| `battery_nominal_speed_mps` | `0.18` | 返航时间预算使用的标称速度 |
| `battery_charge_timeout_sec` | `60.0` | 充电超时 |

当前 `c_tx=0`；P3 有真实消息字节账本后才校准通信能耗。每台机器人使用自己的出生点作为
非重叠充电位，低电量返航是本地硬安全行为，不由中央或后续 RL 覆盖。

充电判断允许机器人停在充电位周围 `0.8 m` 的区域内，不要求精确压到出生点；进入区域后会取消
返航目标，速度低于约 `0.15 m/s` 即开始计时，地图/里程计抖动允许额外 `0.2 m` 的保持带。
默认稳定充电时间为 `6 s`，避免机器人在充电区附近来回调整导致电量继续下降。

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
| `evaluation_stop_on_task_complete` | `false` | 在 `COMPLETE`/`PARTIAL_COMPLETE`/`FAILED` 后结束评估 |

手工演示通常不需要评估器。正式、有界运行优先使用下一节的 smoke 工具，它会管理结果文件和
进程退出。

## 6. Headless 自动验证

ROS 2 launch、smoke 和 baseline 脚本使用系统 ROS Python；先加载 ROS 2 和工作区环境：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
export PYTHONNOUSERSITE=1
```

这里的 ROS 脚本命令显式使用 `/usr/bin/python3`。`ns3gym` conda 环境只用于
`wireless-rl` 下的 ns-3/Python 实验，不要用它替代 ROS 2 的系统解释器。

三机器人完整 P2B 验证：

```bash
/usr/bin/python3 scripts/ros_smoke_test.py \
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
/usr/bin/python3 scripts/run_ideal_baseline.py \
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
                                               \-> PARTIAL_COMPLETE（有机器人故障）
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
