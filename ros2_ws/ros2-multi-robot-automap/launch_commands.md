# 当前三机器人传统基线启动命令

2026-10-14：新路线为 [MR3](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)，P0已验收，当前P1A实施/验证中。
**这些命令仍启动已有前沿控制器，不是 RL**；本页没有虚构训练或 gateway 命令。
所有推荐运行显式固定三台，活动默认已改为三台，保留1–4历史兼容。

## 环境与构建

ROS 使用系统 Python 与 ROS 2 Humble，学习端 `ns3gym` 不用于启动 ROS 节点。
请在未激活 conda、未 source 其他 ROS workspace 的新终端执行：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1
```

这是已验证的同主机 ROS 发现 profile，不等于正式多主机部署或 ns-3 网络模拟。
切换源码版本需要先评估旧 build/install 的路径/包缓存；必要时移到工作区外备份，
从 underlay 干净重建，保留 log。重新开终端 source，不能认为增量构建已删除旧入口。

## 三台手动演示

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 world:=p1c_rooms.world gazebo_seed:=101 \
  enable_gzclient:=true enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false
```

持续建图，Ctrl+C 结束。改为 `world:=my_world.world`、`p1c_open.world` 或
`p1c_corridors.world` 可运行现有其他场景，均是开发/已知场景，不叫未见布局。
看地图时可设置 `enable_gzclient:=false enable_merge_rviz:=true`；`enable_rviz` 只控制
每机器人 RViz，不控制全局 RViz。保持 `enable_drive:=false`，避免另一个速度发布者。

就绪需要三台 action 可发现和每台六个 Nav2 lifecycle 全部 active，不是固定 sleep。
主模式使用 SLAM，三台 Smac2D 的非滚动全局地图均来自实时融合图。轮关节状态由 Gazebo
插件发布，robot_state_publisher 生成 TF。peer_layer 的完整队友机体包络来自观测
odom/TF，不使用真值、不进入 SLAM；任务中源数据失效锁存控制失败并取消目标。
这些实时共享输入**尚未受网络限制**，后续 MR3-P3A 必须消除旁路。

## 已有 90% 工程评估（不验收 MR3 的 95% 任务）

```bash
MR3_RUN_ID=mr3_frontier90_$(date +%Y%m%d_%H%M%S)
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 world:=p1c_rooms.world gazebo_seed:=101 \
  enable_gzclient:=false enable_rviz:=false enable_merge_rviz:=false \
  auto_save_map:=false enable_task_evaluator:=true \
  evaluation_episode_id:=$MR3_RUN_ID \
  evaluation_output_dir:=/tmp/$MR3_RUN_ID \
  evaluation_duration_sec:=180.0 evaluation_coverage_threshold:=0.90
```

每次使用新 episode id/目录，拒绝覆盖旧结果。schema3 在截止之前达标、接触 topic 记录为零、
每台碰撞监测有消息、无控制失败才成功。传感器只覆盖 `base_collision`，不能证明
全机体零非支撑接触；现有监测门禁也不等于持续新鲜度证明，两项均需在 P1A 闭合。
评估器完成默认关闭整个 launch，结果冻结且检查原生子进程；父进程0不能掩盖 abort。
`stop_on_evaluation_complete:=false` 仅用于人工诊断。

把阈值改0.95并不自动完成 MR3-P1A：需先验证任务 ROI、真值几何、质量和95%可达性，
并预声明任务预算/新schema。不要把旧90%/180秒结果、或95%配置本身写成新任务成功。

## MR3-P1A 合同评估与传统开发矩阵

P1A合同模式为schema4，真值/世界哈希、完整ROI、95%/300仿真秒、地图质量、三台参与、
18个组件持续接触监测和导航终态闭合共同决定成功。详细口径见
[MR3_TASK_CONTRACT.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_TASK_CONTRACT.md)。
以下为实际已实现入口；原生验证结果仍以P1A报告为准。

```bash
MR3_BATCH_ID=mr3_p1a_rooms_$(date +%Y%m%d_%H%M%S)
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --task-contract src/multi_robot/config/mr3_p1a/rooms.json \
  --startup-timeout 300 --evaluation-wait-timeout 900 --run-id $MR3_BATCH_ID
```

open/corridors使用对应world与 `open.json` / `corridors.json`，每次新run-id。
合同确定任务300仿真秒，300/900墙秒分别是启动/基础设施保护，不能当成延长任务。
参数与合同显式冲突会拒绝。任务t0为控制器仿真时间放行；启动预热地图单列，达标后的
取消闭合计入任务截止。合同模式不接受两/四台、schema3或曾中断的监测作为成功。
`my_world`暂不提供95%合同；validation/test/confirmation布局本步不运行。

## 当前自动检查与传统批量入口

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/ros_smoke_test.py \
  --robot-count 3 --world p1c_rooms.world --gazebo-seed 101 --startup-timeout 300

MR3_BATCH_ID=mr3_frontier90_batch_$(date +%Y%m%d_%H%M%S)
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --duration 180 --coverage-threshold 0.90 --startup-timeout 300 \
  --evaluation-wait-timeout 360 --run-id $MR3_BATCH_ID
```

这只是可执行示例，本轮未执行。smoke 是启动/消息/关闭检查，任务结果另列。
runner 对任务或基础设施失败返回非零；启动保护是墙钟，任务预算是仿真时间。
所有正式检查也属于实验，必须追加共享 [log.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/log.md)，包括失败、冻结提交、
完整命令、seed、环境、原件路径和结论，不自动覆盖或继承旧 run-id。

Nav2 接受/取消终态默认期限为10仿真秒，对应
`navigation_response_timeout_sec` / `navigation_cancel_timeout_sec`；当前目标上限
`exploration_goal_timeout_sec:=60.0`。这不是未来 Wi-Fi 命令 TTL 的现成实现。

## 故障诊断和证据

先确认生命周期、TF/map frame、最新 scan/odom、原生日志和自己的残留进程。
若原生日志显示 FastDDS 生命周期响应发送超时，停止本次实验后可用安装的官方工具
清理失效共享内存；工具会检查锁并保留在用资源：

```bash
/usr/bin/python3 /opt/ros/humble/tools/fastdds/fastdds.py shm clean
```

不使用无范围 pkill 或手工删除所有 DDS 段。清理后新 run-id 复测，原失败保持。
该工具不是已证明的所有时序故障修复方法。

运行源码 `c9344e1` 的最近三机器人90%工程结果为 rooms60.2s、corridors81.9s，seed101，
180仿真秒上限、基体接触记录为零、原生干净退出；未重跑完整多种子矩阵或95%任务。
详见 [工程修复报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261013_p1c_engineering_repair.md)。
