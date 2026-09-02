# ROS2 多机器人自主建图项目使用指南

本文档面向当前项目状态：ROS2 Humble + Gazebo Classic + TurtleBot3 Waffle，多机器人通过各自 SLAM 建图，`merge_map` 合并全局地图，`multi_robot_exploration` 统一分配探索目标。

自 2026-09-02 起，本目录已通过 `git subtree` 合入 `Breeze-by/my_ns3-gym`
monorepo，与 ns-3/ns3-gym 共用一个 Git 根。旧路径
`/home/zhuyulab/ros2_ws/ros2-multi-robot-automap` 只是指向本目录的兼容符号链接；
提交和查看状态必须从 `/home/zhuyulab/ns3-workspace` 进行。

## 1. 项目结构

项目根目录：

```bash
/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
```

关键包：

| 路径 | 作用 |
| --- | --- |
| `src/multi_robot` | 主仿真包。负责 Gazebo 世界、机器人 SDF/URDF、主 launch、Nav2 参数、RViz 配置。 |
| `src/merge_map` | 地图合并包。订阅 `/tbN/map`，发布 `/merge_map`，并启动一个全局地图 RViz。 |
| `src/multi_robot_exploration` | 总控探索节点。订阅 `/merge_map` 和各机器人 `/tbN/odom`，向 `/tbN/navigate_to_pose` 发送 Nav2 目标。 |
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
| merge_map | `ros2 launch merge_map merge_map_launch.py` |
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

因此 `/tbN/map` 订阅数量、探索线程数量和 Gazebo 中的机器人数量保持一致。

## 4. RViz 策略

当前推荐策略：

```text
保留 Gazebo GUI
保留 1 个全局地图 RViz
关闭每机器人 RViz
```

参数含义：

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `enable_gzclient` | `true` | 是否启动 Gazebo GUI |
| `enable_rviz` | `false` | 是否启动每台机器人单独 RViz |
| `enable_merge_rviz` | `true` | 是否启动一个全局 `/merge_map` RViz |

也就是说，常用命令里 `enable_rviz:=false` 不会关闭全局地图 RViz，只会关闭每机器人 RViz。

如需完全关闭 RViz：

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false
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
/tbN/odom
/tbN/cmd_vel
```

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

### 6.5 探索目标筛选与失败重试

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

规划失败或执行失败后，机器人会重新进入 idle，下一轮换 frontier；同一机器人连续失败多次后，会把该目标加入 visited，减少重复尝试。

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

推荐 3 机器人运行：

```bash
source /opt/ros/humble/setup.bash
source /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle

ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 \
  enable_gzclient:=true \
  enable_rviz:=false
```

预期：

```text
Gazebo GUI 打开
只打开 1 个 RViz2
Gazebo 中有 tb1、tb2、tb3
RViz 中显示 /merge_map
没有每机器人单独 RViz
```

## 9. 验证

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

## 11. 后续接入 ns-3 的建议切入点

当前闭环为：

```text
robot 上行：/tbN/odom、/tbN/scan、/tbN/map
server 决策：headquarters_control 基于 /merge_map 分配目标
server 下行：/tbN/navigate_to_pose 或 /tbN/cmd_vel
```

后续插入通信延迟、丢包、调度模块时，建议优先从这两类边界入手：

```text
上行：机器人状态/地图到服务器
下行：服务器目标或速度命令到机器人
```

当前阶段不建议重构 Nav2 或 SLAM，先保持：

```text
Gazebo + SLAM + merge_map + Nav2 + headquarters_control
```

这个闭环稳定，再替换通信链路。
