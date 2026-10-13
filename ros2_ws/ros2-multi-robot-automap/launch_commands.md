# 当前 P1C 建图导航启动命令

此文件描述 `main` 的实际运行方式。研究路线等待用户的新指示；不启动目标检测、充电、集合或通信 gateway。

## 环境与构建

ROS 使用系统 Python 和 ROS 2 Humble。ns-3 的 `ns3gym` 环境不用于 ROS 节点。

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
PYTHONNOUSERSITE=1 colcon build --symlink-install --allow-overriding nav2_bringup
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
```

切换源码版本后，将旧 `build/`、`install/` 移到工作区外备份，再从 `/opt/ros/humble` 重建。
保留 `log/`，并使用新终端重新 source；已 source 的旧环境不能通过修改文件自动更新。

## 手动演示

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=2 world:=my_world.world gazebo_seed:=101 \
  enable_gzclient:=true enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false
```

此模式持续建图，Ctrl+C 结束。`robot_count` 为 1–4 的整数，非法值拒绝；四台均采用融合地图、
Smac 2D 和非滚动全局代价图。模型资源通过安装包的 `models` 路径解析。

## 有界覆盖评估

每次使用新的 episode id 和输出目录。默认启用 `stop_on_evaluation_complete`，评估结束后关闭
整个 launch；设为 false 仅用于人工诊断，结果仍在截止时冻结。

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=2 world:=my_world.world gazebo_seed:=101 \
  enable_gzclient:=false enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false enable_task_evaluator:=true \
  evaluation_episode_id:=mapping_unique_run \
  evaluation_output_dir:=/tmp/mapping_unique_run \
  evaluation_duration_sec:=180.0 evaluation_coverage_threshold:=0.90
```

schema v3 成功需要截止前覆盖达标、零接触、碰撞监测有数据且无导航握手失败。
`trajectory_overlap_ratio` 和兼容字段 `search_overlap_ratio` 都表示中心轨迹栅格重叠。
真值只由评估器读取；地图融合要求共同坐标系，旋转地图直接拒绝。

## 自动检查与批量入口

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/ros_smoke_test.py \
  --robot-count 4 --gazebo-seed 101 --startup-timeout 300

PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --duration 180 --coverage-threshold 0.90 --startup-timeout 300 \
  --evaluation-wait-timeout 360 --run-id mapping_unique_batch
```

启动期限为墙钟保护，任务上限为仿真时间，不能互相替代。smoke PASS 与任务 PASS 分开输出；
批量 runner 对任务或基础设施失败都返回非零。新实验必须在共享 `wireless-rl/log.md` 记录
完整命令、冻结提交、参数、失败和结果；旧实验不得覆盖或计入新版本成绩。

Nav2 接受响应和取消到终态的默认期限均为 10 仿真秒，分别由
`navigation_response_timeout_sec`、`navigation_cancel_timeout_sec` 配置；原目标执行上限保持
`exploration_goal_timeout_sec:=60.0`。协议失败通过 `/exploration_failure` 明确终止评估。
