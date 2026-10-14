# 当前三机器人传统基线启动命令

2026-10-15：新路线为 [MR3](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md)，P0已验收，P1A待用户验收，P1B未开始。
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

这是历史schema3/普通演示的同主机 ROS 发现 profile；P1A合同模式使用下方明确的
UDP-only配置。两者都不等于正式多主机部署或 ns-3 网络模拟。
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
每台碰撞监测有消息、无控制失败才成功。schema3只读取 `base_collision`，不能证明
全机体零非支撑接触；其监测门禁也不等于持续新鲜度证明。全机体门禁使用下面的schema4。
评估器完成默认先请求本launch的Gazebo原生停止，等待真实server退出后关闭其余节点；
结果冻结且检查原生子进程，父进程0不能掩盖 abort。
`stop_on_evaluation_complete:=false` 仅用于人工诊断。

把阈值改0.95并不自动完成 MR3-P1A：需先验证任务 ROI、真值几何、质量和95%可达性，
并预声明任务预算/新schema。不要把旧90%/180秒结果、或95%配置本身写成新任务成功。

## MR3-P1A 合同评估与传统开发矩阵

P1A合同模式为schema4，真值/世界哈希、完整ROI、95%/300仿真秒、地图质量、三台参与、
18个组件持续接触监测和导航终态闭合共同决定成功。详细口径见
[MR3_TASK_CONTRACT.md](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_TASK_CONTRACT.md)。
以下为实际已实现入口；原生验证结果仍以P1A报告为准。
合同launch自动启动C++ `mr3_contact_reducer`。18条原始接触消息仍保留，汇总输出为
`/mr3_contacts/tbN/<component>`；只合并同一消息中重复的碰撞对，保留原header和
每对首次完整几何样本，原样本数量保存在state.info。生产20Hz和0.5仿真秒源龄/接收龄
门限不变。原始发布端和汇总节点使用可靠的100条历史，防止启动负载下仅5条历史
被覆盖；该改动是否消除缺口以新冻结原生结果为准。原始消息序列缺口、无法审计或
多个源发布者锁存为失败。runner在任务退出后还核查唯一18路汇总、逐条输入/输出、
完整序列和原生子进程；原生JSON成功不能掩盖基础设施失败。

P1A smoke/baseline在任何ROS命令或初始化之前自动应用下面的同主机UDP-only环境，
并在metadata的 `transport_environment` 记录所选变量和 `profile_sha256`。
手动直接启动合同launch时先在已source上述ROS/Gazebo环境的终端执行：

```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=0
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/src/multi_robot/config/mr3_fastdds_loopback_udp.xml"
export SKIP_DEFAULT_XML=1
unset FASTDDS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML RMW_FASTRTPS_PUBLICATION_MODE
export ROS_DOMAIN_ID=98 GAZEBO_MASTER_URI=http://127.0.0.1:11861
```

XML关闭内建transport，仅启用白名单为127.0.0.1的UDPv4；没有更改socket缓冲或
UDP transport的默认发送阻塞方式。`ROS_LOCALHOST_ONLY=0` 由显式loopback白名单约束通信范围，
`SKIP_DEFAULT_XML=1` 只阻止工作目录的默认XML覆盖显式profile，仍加载上方指定文件。
legacy入口不会自动改为此环境；重新打开终端并使用前面的历史profile可复现其原环境。
第六版另为三台各六个Nav2节点的 `change_state` 响应writer配置精确命名profile：
`rr/tbN/NODE/change_stateReply`，共18项；NODE为 `controller_server`、`planner_server`、
`behavior_server`、`bt_navigator`、`waypoint_follower`、`velocity_smoother`。
只将这些response writer的reliability `max_blocking_time` 从默认100ms改为5墙秒，
为启动时响应writer等待对应reader匹配提供有界窗口，也约束这些writer的DDS写入阻塞；
它不按ROS仿真时钟计时。没有新增Nav2 transition重试，也没有改变其无超时future等待；
reader匹配为何延迟、客户端为何可能一直等待的根因仍未解决。
profile只绑定这些命名writer，不随启动阶段结束而撤销；不设置默认writer、service-wide
fallback或reader配置，contact/control、get_state及request writer保持原有QoS。
`RMW_FASTRTPS_USE_QOS_FROM_XML` 继续unset，ROS端点QoS转换仍保留该max-blocking字段。
静态SDK/RMW验证另列为
[证据](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/lifecycle_reply_qos_v6_static_proof.json)，
不代表实际启动已通过；配置是否改善响应问题仍以新冻结
原生结果为准，不宣称已证明SHM或abort根因。300墙秒启动、300仿真秒任务、95%及
.5仿真秒接触健康门禁均不变，控制策略与物理参数未改。

```bash
MR3_BATCH_ID=mr3_p1a_rooms_$(date +%Y%m%d_%H%M%S)
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_ideal_baseline.py \
  --world p1c_rooms.world --robot-count 3 --seeds 101 202 303 \
  --task-contract src/multi_robot/config/mr3_p1a/rooms.json \
  --startup-timeout 300 --evaluation-wait-timeout 900 --run-id $MR3_BATCH_ID
```

open/corridors使用对应world与 `open.json` / `corridors.json`，每次新run-id。
评估器等待有效正ROS仿真时钟，再一次建立18路接触订阅；此后收到的所有放行前
接触保留，18路持续新鲜且无非支撑接触才可放行。这不覆盖订阅建立之前的每个历史
触碰。未来消息先按当前时钟排水，真正未来队列超过256条立即失败并记录诊断；
不改源时间戳或.5秒门限。任务提前结束时，runner优先读取原生JSON并审计退出，
不继续等待已经消失的topic。300墙秒约束Nav2/ROS就绪，后续时钟/监测等待仍由
900墙秒评估保护约束。
P1A第六版按rooms、corridors、open逐场景串行执行，每场景内部也串行重启三种子。
第六版计划使用独立ROS域98/99/100与Gazebo端口11861/11862/11863；保持所有任务与墙钟保护门限。
这用于减少并发启动压力，不表示一次Nav2响应超时的根因已经确定。精确预声明见
[native plan](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a/predeclared_native_plan.json)。
冻结`5e47802`累计10次尝试含1次保留的原生基础设施失败，得到9个有效单元；结果见
[P1A报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261014_mr3_p1a.md)。
合同确定任务300仿真秒，300/900墙秒分别是启动/基础设施保护，不能当成延长任务。
参数与合同显式冲突会拒绝。任务t0为控制器仿真时间放行；启动预热地图单列，达标后的
取消闭合计入任务截止。合同模式不接受两/四台、schema3或曾中断的监测作为成功。
`my_world`暂不提供95%合同；validation/test/confirmation布局本步不运行。

默认 `stop_on_evaluation_complete:=true` 时，评估器退出后launch向记录的owned
gzserver环境（包括实际 `GAZEBO_MASTER_URI`）执行
`gz topic -p /gazebo/server/control -m "stop: true"`。
必须同时观察同一启动action、PID和进程名的server退出0及stop CLI退出0，才关闭其余节点；
两者可任意先后，CLI退出0不等于server已停止。10墙秒仍未收到任一必要退出事件则输出
`MR3_GAZEBO_NATIVE_STOP_ERROR` 并兜底关闭；CLI失败或server非零退出也保留错误标记和
真实子进程退出码。runner把该标记判为基础设施失败，即使之后CLI/server退出0；
SIGABRT等真实失败不会被屏蔽。有效任务失败或无效JSON也先等待同一原生关闭流程，
然后保留原失败结果。该关闭保护不改变300仿真秒任务预算。
`stop_on_evaluation_complete:=false` 不发出原生stop请求，供人工诊断。

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
