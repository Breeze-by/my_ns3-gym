<!-- 2026-10-07: P3C metrics and live fault console validated; GUI defaults documented below. -->

# 多机器人任务启动命令速查

## 2026-10-12 全局任务规划候选

长会话已暂停并以 `b32c891` 为基础恢复；当前在独立分支实现全局任务规划。主 launch 新参数 `mission_planner:=global`（默认）采用单规划线程、联合探索和统一动作所有权；`mission_planner:=baseline` 保留恢复后的控制策略用于明确声明的比较。`ros_smoke_test.py` 对应 `--mission-planner global|baseline`。两种模式共享原完整返航预算、网关协议、原生能量记账以及内部 SLAM 自体回波修复；原始 scan、Nav2、物理模型和完成阈值保持。默认值变化不意味着任务已验收。

P2C.1 完整集成仍未验收，917 留出未调用。新开发与正式实验使用 `p2c_integration_manifest.json` 中的 global 声明、新提交和新 run-id，不能复用 v43–v95 历史结果。技术说明见 [`20261012_p2c1_global_mission.md`](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261012_p2c1_global_mission.md)。

2026-10-13中断恢复候选沿用上述入口。global模式在原目标租约内补回已交付观察者的安全原地朝向恢复，充电请求过期时继续延后依赖；集合在同等安全/补能条件下优先完整名义任务耗时。四开发3PASS/1FAIL后，下一候选恢复探索与等待共用的原绝对收益比较；未发补能需求只提供规划依赖，实际导航、已发请求和本地返航仍保留所有权，闲置且有完整预算的机器人可为当前返航或补能依赖清道。baseline保留原集合排序。原300秒、5秒保持、源TTL、完整返航预算及物理刺激保持，新行为仍需新冻结的完整任务门禁。

恢复报告：[`20261012_p2c1_session_recovery.md`](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261012_p2c1_session_recovery.md)。

## P3C 实时通信指标与控台

默认主 launch 同时启动 `gateway_metrics`、通信曲线窗口和在线通信故障控台。窗口包含上/下行吞吐与 goodput、已结算发送尝试 PDR/loss、源到交付时延/AoI、队列/重试、逐消息类别字节堆叠、任务/电池事件。关闭窗口不停止指标采集。手动模式 ledger 自动放在 `/tmp/multi_robot_gateway/<UTC_PID>/messages.jsonl`，同目录 `messages_metrics/` 保存结果；显式 `gateway_ledger_path` 时默认结果目录为账本同级 `<stem>_metrics/`。可用 `gateway_metrics_output_dir:=<新的空目录>` 指定路径，已有目录会被拒绝以保护证据。

批量/headless 命令必须加入：

```text
enable_gzclient:=false enable_rviz:=false enable_merge_rviz:=false enable_status_panel:=false enable_gateway_monitor:=false
```

`ros_smoke_test.py` 已自动关闭通信 GUI，继续默认保存指标。需要关闭在线配置入口时加 `enable_gateway_fault_control:=false`；监测继续运行。窗口关闭后可以在同 ROS_DOMAIN_ID 的终端重新打开：

```bash
ros2 run multi_robot_exploration gateway_monitor
```

在控台选择 `fault`，修改上/下行丢包百分比、延迟、重复、乱序、ACK 等待、有限重试、队列容量、丢弃类别或断网区间，点击“应用通信配置”。服务确认的配置版本/生效仿真时刻同时出现在账本与曲线；`ideal` 模式保留输入值但有效损伤为零。队列容量输入 `0` 表示4096，断网输入 `[[15,30]]` 相对任务首次 `EXPLORE` 时刻。未知类别不会自动影响其他消息。实时修改只影响新发送 attempt，在途 attempt 保留原发送配置；不清队列、不更新源时间、不重置任务。

脚本/另一终端使用同一个原子服务，例如上行10%丢包、下行0.5秒延迟：

```bash
/usr/bin/python3 scripts/gateway_configure.py --set \
  network_mode='"fault"' uplink_loss_rate=0.1 downlink_delay_sec=0.5
```

恢复理想通信：

```bash
/usr/bin/python3 scripts/gateway_configure.py --set network_mode='"ideal"'
```

仅查询当前配置时不传 `--set`。服务名称为 `/gateway/configure`，类型 `rcl_interfaces/srv/SetParametersAtomically`；`/gateway/fault_configuration` 是权威生效值。节点启动 ROS 参数保持冻结，`ros2 param set` 会明确拒绝；运行中的配置必须走上述服务。TTL、导航 deadline、原生保持和本地安全参数不在控台白名单。`--expected-revision N` 可防止覆盖其他操作；GUI发现版本变化时要求读入当前配置再应用。

按仿真时间自动施加故障，可直接使用集成清单的 schedule，或编写 JSON 数组：

```json
[{"after_sec":15,"parameters":{"network_mode":"fault","uplink_loss_rate":0.1}},
 {"after_sec":30,"parameters":{"network_mode":"ideal"}}]
```

```bash
/usr/bin/python3 scripts/gateway_configure.py --schedule schedule.json --output log/configuration_new.jsonl
```

自动保存 `inputs.jsonl`、`live.jsonl`、`live_windows.csv`、`windows.csv/jsonl`、`summary.json`、`events.jsonl`、`curves.svg`。实时窗口是账本当前前缀的最近1秒暂定结果，负载下可能跳过tick，最终累计量对账完整输入；需要连续固定1秒窗口的完整回放时执行：

```bash
PYTHONNOUSERSITE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python scripts/export_gateway_metrics.py \
  --ledger <ledger.jsonl> --episode <原生任务结果.json> --task-events <safety_events.jsonl> --output <新的导出目录>
```

验证 GUI/文件同源：`scripts/export_gateway_metrics.py --verify-live <metrics目录>`。配对曲线导出加 `--reference <ideal导出目录>`；GUI加载参考目录的 `windows.jsonl`。world/seed/任务模式/机器人数量及可用的目标、能量、原生门槛必须一致。未发现目标的结果坐标保持null，配对验证使用原运行清单的目标声明，不能填入观测。细节与指标口径见 `user_guide.md` 的 P3C 节。

## P3C.5 负载与协议审计

bea7f8b冻结14原格已全部自然结束并通过严格审计：11原生COMPLETE/3 RALLY超时，原失败保持；零碰撞/耗尽/失效/infra/retry。曲线、角色成本、2/3机器人四拓扑与原生结果见[P3C.5最终报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261007_p3c5_gate.md)。本轮不进入P4/ns-3/Wi-Fi/RL。

新增启动参数 `gateway_admission_protocol:=true` 启用 candidate/request/grant/heartbeat。
默认 `false` 保留已验收 P3C 的直接准入路径；审计两侧使用相同任务栈与候选规则。
普通上行完整 payload 在机器人队列中等待有效 grant，源 TTL 不续期；检测、
电池/返充和导航关键消息独立于 grant。总部已拥有的下行队列执行本地准入，
不伪装成发给自身的控制包；发往机器人的 grant/heartbeat 与原 ACK 全部计费。

指标节点在 SIGINT 后有90秒完成只读导出，之后才升级终止信号；任务300秒、
原生5秒保持、源TTL和本地安全不受影响。网关关闭后仍将本地候选终止事件写入文件，
不再依赖已失效的DDS发布上下文。完整审计要求 gateway 与 metrics 都正常退出，不能发生SIGTERM/SIGKILL升级。P3C.5 runner外层收尾等待120秒；这些都是任务停止后的wall-time收尾预算。

在第1节环境初始化后，用新目录运行清单中的一个格，例如：

```bash
taskset -c 0-79 /usr/bin/python3 scripts/run_p3c5_audit.py \
  --case lab2 --run-id my_p3c5_new --domain 180 --gazebo-port 19920
```

清单 `scripts/p3c5_traffic_manifest.json` 固定14格，`p3c5_control_schema.json`
固定控制字段。每格保存原生结果、ledger、graph、实时输入/曲线与源/环境摘要；
有结果或目录时拒绝覆盖。运行前必须提交推送干净源码，用户资料目录除外。
`--validate-only` 只显示命令与摘要。不要使用已存在的 run-id 回填失败。

`/gateway/admission_observation` 只含已交付摘要/请求/心跳及历史。机器人当前队列
始终未知；心跳队列值是带源龄的历史快照，不能当成即时队列。ledger 中
`local_queue_audit` 是离线诊断，不能作为中央策略输入。

airtime/radio joules 当前没有 PHY/MAC 或功率校准，保存为 null；每次发送另外保存
`8*envelope_cdr_bytes/1e6` 条件系数，可代入 Mbps 与瓦数，不能称为实测无线占用或能耗。
任务能量仍是原距离/时间模型单位。现有控台与 P3C 曲线会计入新增控制消息。

每个候选首次立即发送candidate/request，未授权时相隔至少.75秒重发、总计最多三组；不是所有候选全局限速。GUI/导出参考配对必须同时匹配admission_protocol，缺flag的已验收旧direct记录为false；协议开/关结果不能标成同协议TDI。

只读重审当前原14格到新的输出目录（不启动Gazebo）：

```bash
export PYTHONNOUSERSITE=1
export PYTHONPATH="$PWD/src/multi_robot_exploration:$PYTHONPATH"
/usr/bin/python3 scripts/check_p3c_source.py --output log/p3c5/review_source_new.json
/usr/bin/python3 scripts/check_p3c5_gate.py \
  --run-root log/p3c5/p3c5_v3 --source log/p3c5/review_source_new.json \
  --runtime log/p3c5/runtime_v10 --output log/p3c5/review_gate_new --workers 3
```

原ledger/实时输入保留log忽略目录；Git中的报告、审阅副本和无损成本/strata/burst归档绑定原始SHA。实际最终审计用gate_v21，后续纯显示源码检查用v24_source.json。再次实验须先新提交推送冻结、使用新run-id，不能回填v3。

2026-10-08审计器额外绑定已交付内容、grant版本/大小/接收端、重试序号/间隔，以及实际命令/原生文件/冻结清单；源码检查扩至150文件，含完整models/urdf。上述只读命令仍适用。本次新输出在`log/project_review/20261008/`，原14格全部PASS、11 COMPLETE/3 timeout保持；新输出不冒充原实验时审计器版本。后续任务算法修复将使当前源码相对旧冻结检查失败，这是需要新基线与新集成批次的信号，不能简单绕过检查。

## 1. 每个新终端先执行

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle
export PYTHONNOUSERSITE=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
unset FASTRTPS_DEFAULT_PROFILES_FILE ROS_DISCOVERY_SERVER
```

从 P3B.5 v102 起，新验证候选显式使用 Fast DDS 的 UDPv4 transport。所有机器人、总部、
理想/损伤 gateway 基线及独立只读观察器都从这个终端环境启动；它改变本机 ROS 中间件传输，
网关故障模型仍由原 launch 参数控制。原 v101 的原生初始化超时完整保留，UDP 组件不证明
该超时的根因；P3B.5 已由 v106 同提交完整57格、方向延迟补验及只读校验通过，并于2026-10-07由用户验收。
完整结果见 [P3B.5报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261006_p3b5_gate.md)。实验 manifest 会记录 RMW、transport 环境以及已指定 XML
profile 的路径/摘要；正式验证不混用两种环境。`FASTRTPS_DEFAULT_PROFILES_FILE` 若指定了禁用
builtin transports 的 profile，会覆盖这项 transport 选择，应在冻结前核对实际初始化记录。

首次检出或尚未构建本工作区时，先构建全部包，包括仓库内的自定义 SLAM Toolbox：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
colcon build --symlink-install
source install/setup.bash
```

已有完整构建、仅修改以下四包时，可用增量构建：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
colcon build --symlink-install --packages-select \
  multi_robot_interfaces multi_robot merge_map multi_robot_exploration
source install/setup.bash
```

修改 `slam_toolbox` 源码或其 launch 后，还需构建该包；新终端仍执行本节环境初始化。

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
  enable_gateway_monitor:=true \
  enable_gateway_fault_control:=true \
  enable_rviz:=false \
  enable_merge_rviz:=false \
  auto_save_map:=false \
  gazebo_seed:=101 \
  nav2_ready_timeout_sec:=360.0 \
  enable_target_detection:=true \
  enable_rally:=true \
  gateway_mode:=ideal \
  mission_mode:=rally \
  rally_max_concurrent:=2 \
  global_battery_rally_pause:=false \
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
  --run-id "p3b5_current_fixed_$(date +%Y%m%d_%H%M%S)" \
  --ros-domain-base 130 \
  --infrastructure-retries 0
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
充电并 `COMPLETE`。之后 P3A.6 的冻结 `22c95a7` 已验收，当前 P3B.5 的冻结 `d8d361b`
另行通过同提交门禁；早期目录不能替代这两批各自的证据。

### 3.7 当前 task-stack 理想重验证与 P3A.5 历史入口

P3A.5 runner 会为每个 episode 保存尝试记录、启动日志和 ROS graph 快照，并在 summary 中写入
`task_stack_frozen_commit`、源码/配置哈希和环境版本。旁路审计还支持将快照写入指定文件：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run multi_robot_exploration bypass_audit --robot-count 3 \
  --wait-sec 10 --graph-output /tmp/p3a_graph.json
```

正式批量入口是 `scripts/run_p2d_baseline.py`，当前命令见第 3.5 节；同提交十格必须全部原生
`COMPLETE`、零碰撞、零基础设施失败且 graph/ledger audit 通过。P3A.6 已验收的历史冻结为
`22c95a7`；当前 P3B.5 的十格证据属于 `d8d361b`，两批不能混算。
`wireless-rl/report/20260923_p3a5.md` 是早期候选报告。

### 3.8 P3A.5 历史 held-out 算法消融入口

`scripts/run_p3a5_ablation.py` 使用 `scripts/p3a5_heldout_scenarios.json` 中原预声明的
种子、目标和场景。这是历史协议入口，不能据此把当前重复运行称为新的未暴露测试。
四个变体只切换 rally 算法开关；评估器的 `COMPLETE`、零碰撞、姿态/速度、
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
| `gateway_drop_message_types` | 空 | fault 模式按逗号分隔的消息类别丢弃 |
| `gateway_reorder_step_sec` | `0.05` | 乱序槽延迟；测试 5 Hz pose 乱序可用 `0.3` |
| `gateway_blackout_intervals` | `[]` | 从中央首次 EXPLORE 起计的仿真秒半开区间 JSON |
| `inject_failure_robot` | 空 | 仿真失败注入机器人，例如 `tb3`；空值禁用 |
| `inject_failure_after_sec` | `-1.0` | 从被注入机器人首条 odom 起计；负值禁用 |
| `message_freshness_timeout_sec` | `5.0` | 中央输入新鲜度上限；仍受各类 TTL 约束，pose/TF 为 2 s、map/battery 为 5 s |
| `navigation_command_deadline_sec` | `90.0` | 导航命令超过 deadline 后 abort |
| `enable_return_probe_pause` | `false` | 仅用于补充受控返航夹具；普通任务保持关闭 |

### 3.10 当前 P3B.5 配对任务入口

先执行第 1 节环境初始化。只检查完整主矩阵配置、不启动 Gazebo：

```bash
/usr/bin/python3 scripts/run_p3b5_tasks.py \
  --run-id p3b5_current_plan --ros-domain-base 30 --validate-only
```

预期为 27 个 pair case、41 个唯一主矩阵 episode。独立开发可只运行零故障配对：

```bash
/usr/bin/python3 scripts/run_p3b5_tasks.py \
  --run-id "p3b5_current_zero_$(date +%Y%m%d_%H%M%S)" \
  --cases zero_rally_lab --ros-domain-base 30
```

去掉 `--cases` 会运行完整 41 主格；这条入口本身不包含十格固定理想回归和六个辅助安全格。
完整 P3B.5 门禁还要求同提交、同声明环境的十格回归、四个自然安全探针和两个受控物理返航格，
并以严格 checker 审核全部证据。正式执行顺序是强制充电原生保持/E0/物理返航、十格 fixed，
最后其余主矩阵及留出；不能把单个 runner 的 exit 0 当成完整门禁。

当前最终 57 格已在 `d8d361b` 完成。`p3b5_holdout809.world` / seed 809 / fault seed 28091
已于本批首次运行，之后重复运行属于回归；控制算法改变后需要新的预声明未暴露留出组合。
只有 rally 的原生 `COMPLETE` 是完整任务成功，`PARTIAL_COMPLETE`、`FOUND` 和覆盖率达标
分别保留为部分完成或过程指标；强故障超时按原结果保留。

## 4. 切换 Gazebo world

当前已验证的场景：

| 参数值 | 场景特点 |
| --- | --- |
| `my_world.world` | 当前目标搜索和 P2B 集结的正式场景 |
| `p1c_open.world` | 开放区域和离散障碍 |
| `p1c_rooms.world` | 多房间、门洞和遮挡 |
| `p1c_corridors.world` | 长走廊、绕行和支路 |
| `p3a5_holdout.world` | P3A.5 历史预声明 holdout；目标 `(4.4, 3.4)`，种子 404/505；重复运行不自动构成新留出 |
| `p3a5_holdout.world` | P3B.5 历史留出场景，707 已暴露；不再作为新未见测试 |
| `p3b5_holdout809.world` | 当前 P3B.5 首次留出已完成；目标 `(4.4, -3.4)`，3 台、seed 809、初始能量 45 |

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
| `rally_assignment_objective` | `minimax` | 路径决胜指标：`minimax` 或 `total_path`；启用电池时先避免观测者返充，再比较充电数、串行时间和额外余量 |
| `use_map_safe_rally_order` | `true` | 按当前地图和动态占位检查集合顺序 |
| `global_battery_rally_pause` | `false` | 是否在安全返航时暂停其他集合航段；默认只暂停返航机器人 |
| `rally_max_concurrent` | `2` | 同时派发的无冲突集合航段上限；路径冲突时自动让低优先级机器人等待或让路 |

当前集合策略预约动态避障路线，并发送最长 5 m、转角前截断的可视航点；
Nav2 action 失败、实时位置发生冲突或机器人需要让路时会缩短航段并重新规划；
单个集合 action 卡住 30 秒会被取消并触发恢复。需要最保守串行调试时可显式设置
`rally_max_concurrent:=1`。

当前控制器沿用 P3A.6 的滚动路线预约：探索最多三台机器人并发，只有经过停驻位置避让和
1.8 m 路线隔离检查的航段才能放行。共享通道等待已有路线释放，候选冲突时尝试其他前沿；
可视航点最长 5 m，在遮挡转角前分段。Nav2 的航点到达容差为 0.02 m，任务 COMPLETE
仍要求原来的 0.35 m/速度门限/连续 5 s。任何机器人返航时取消其他探索航段，待返航结束再
恢复分配。P3A.6 已验收；当前任务栈另由 P3B.5 的同提交十格与完整故障门禁验证。

当前使用 RPP 控制器（最大线速度 0.26 m/s，预测碰撞检测开启），
局部与全局 costmap 半径为 0.25 m；集合和本地返航也使用最长 5 m 的可视航点。
返航通道被停驻机器人占用时，先让该机器人到路线外临时避让位，再恢复最终集合任务。
每次进入 RETURNING 只触发一次全局取消，周期状态消息不会反复打断让路；返航者进入
充电后重新核验集合路线；合法、已完成且朝向正确的避让位可在全部安全/能量条件通过后保留为最终位。
默认 `rally_max_concurrent:=2`、`global_battery_rally_pause:=false`；Nav2 controller 与
velocity_smoother 使用仿真时间，当前多机器人 SLAM 地图重建周期为 2 s。
十格固定原生 COMPLETE 的结果见本页顶部报告，不保证其他场景都在 300 s 内完成。

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

当前 P3B.5 完成判定使用 schema 9：收到 `COMPLETE`/`PARTIAL_COMPLETE` 先记录中央声明，
只有新原生 ModelStates 样本在当前集合位/参与名单上满足原位置与速度限制、连续观测 5 s 后
才记录合格完成并结束。`coordinator_completion_time_sec` 与 `completion_time_sec` 分别保存
声明/合格时间，300 s 时限不延长；超过 pose TTL 2 s 的观察间断重置。真值只读，不反馈任务控制。
单看状态栏或 `/task_state=COMPLETE` 不能替代评估 JSON 的 `native_rally_hold_proof`。

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
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
unset FASTRTPS_DEFAULT_PROFILES_FILE ROS_DISCOVERY_SERVER
```

这里的 ROS 脚本命令显式使用 `/usr/bin/python3`。`ns3gym` conda 环境只用于
`wireless-rl` 下的 ns-3/Python 实验，不要用它替代 ROS 2 的系统解释器。

三机器人当前完整任务验证（正式 runner 使用容量 100；手动 launch 默认容量为 60）：

```bash
/usr/bin/python3 scripts/ros_smoke_test.py \
  --world my_world.world \
  --robot-count 3 \
  --gazebo-seed 101 \
  --startup-timeout 600 \
  --message-timeout 90 \
  --shutdown-timeout 60 \
  --evaluation-duration 300 \
  --coverage-threshold 0 \
  --evaluation-wait-timeout 900 \
  --target-detection \
  --rally \
  --battery --battery-capacity 100 --battery-initial-energy 40 \
  --gateway-mode ideal --mission-mode rally \
  --target-x -4 \
  --target-y 4 \
  --target-max-distance 3 \
  --target-field-of-view 90 \
  --target-confirmation-frames 3 \
  --episode-id "manual_p3b5_seed101_$(date +%Y%m%d_%H%M%S)"
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
  独立值，例如 `export ROS_DOMAIN_ID=73`，并为每个实例选择不同的
  `GAZEBO_MASTER_URI`，例如 `export GAZEBO_MASTER_URI=http://127.0.0.1:19730`。
- 如果三机器人启动偶发超时，先重试一个干净 ROS domain，并检查日志中点名的 Nav2
  lifecycle；不要绕过就绪门控。
- `enable_rviz:=false` 只关闭每机器人 RViz，不会关闭全局 RViz；完全关闭还必须设置
  `enable_merge_rviz:=false`。
- 目标只是 Gazebo 可视标记，没有 collision，不会改变 lidar 地图或成为障碍物。

### 2026-10-07 独立方向延迟补验入口

保持已有任务算法和300秒原生任务门槛。预冻结四case对应六个独立任务；每个场景的两个方向共用一个同配置ideal对照，不把共用ideal重复计为独立样本。

```bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 scripts/run_p3b5_tasks.py \
  --config scripts/p3b5_directional_delay_manifest.json \
  --run-id "p3b5_directional_delay_check_$(date +%Y%m%d_%H%M%S)" \
  --ros-domain-base 180 --validate-only
```

`--validate-only`只检查清单，输出4 case/6任务，不启动Gazebo。已完成正式补验使用19700/19701专用master、开发seed202/101和fault seed17011；原始冻结命令、三COMPLETE/一过期等待timeout和TDI在上述审计报告记录。参数0实际选择默认4096队列，当前清单仅更正说明；复核原六格时使用报告归档的09f15df清单。

## 9. 历史候选与门禁记录

逐版本候选过程已集中到日期报告和实验日志。已回退长会话的报告、完整附件与清理前指南可从备份分支 `backup/project-before-report-cleanup-20261012` 读取；路径见[归档索引](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/ARCHIVE_INDEX.json)。历史结果仅支持对应冻结的结论，不能当作当前参数或完整验收。

以下 P2C.1 安全预算与准备就绪内容仍适用于恢复源码。示例中的已完成实验 run-id 只作历史记录；新实验必须另预声明、冻结并使用新的 run-id。

## P2C.1 完整返航路径与预算（2026-10-08 开发候选）

P3C.5已获用户验收。当前本地电池按完整已知自由路径到可用充电接触区计算储备；中央探索/集合准入只使用交付地图。`battery_return_path_factor:=2.0`现在乘完整路径长度。新增`battery_return_recovery_wait_sec:=30.0`计入取消/恢复等待，`battery_return_no_route_wait_sec:=30.0`限制未知/失路等待。原地图5秒、pose/TF2秒TTL、300秒任务和5秒原生保持不变。

无路时停止新增运动并取消已接受本地腿；地图恢复且预算充分的暂停任务可继续，持续失路、储备底线或距离/时间包络越界会明确失败。每0.5秒检查安全预算，额外预留1秒、0.3 m/s的反应运动；该包络仍需新Gazebo集成和实物条件标定。

`/tbN/battery_return_audit`是本地只读取证输出，保存地图压缩快照、路线/版本、预算、取消/拒绝次数、实际距离/时间/消耗与预测误差。它不进入AP控制观测，也不属于原P3C.5无线流量证据；原报告不重算为新算法结果。自动任务观察器保存至`safety_events.jsonl`。

```bash
ros2 launch multi_robot gazebo_multirobot_mapping_with_nav2.launch.py \
  robot_count:=3 enable_battery:=true battery_initial_energy:=40.0 \
  battery_return_path_factor:=2.0 \
  battery_return_recovery_wait_sec:=30.0 battery_return_no_route_wait_sec:=30.0 \
  enable_gzclient:=true enable_status_panel:=true \
  enable_rviz:=false enable_merge_rviz:=false auto_save_map:=false
```

以上是开发候选入口，尚未将旧任务冻结的COMPLETE或零事故外推到当前候选。

P2C.1 v2（2026-10-08，未集成候选）：原近站机会充电现增加两步当前前沿完整预算预测，只有已完成真实探索、有新鲜可见接触路线且充电可供给当前两个不同前沿时使用。原25%低电分支保留；预测不预派发第二个目标，不在初始spawn补满。所有原源TTL/本地抢占/串行请求/任务300秒/原生5秒保持均不变；新AP只读地图证明在ledger的`coordinator_charge_decision.opportunity_lookahead`，不会把本地审计地图交给AP。v1原开发FAIL及三COMPLETE/一timeout保留，当前仍待独立新freeze/gates，P3C.5已验收，无P4/ns3/Wi-Fi/RL。

### P2C.1 物理断网补充门禁（独立冻结原始证据）

先通过新的四开发与十固定/强制充电/零电量安全格，再执行这两个原始安全探针，最后才首次暴露917。它们沿用原预声明E40/idle0.15、50秒准备、60–250秒断网、62–248秒物理核验、远端≥1.1m/实测返航与执行Nav2运动≥0.5m、300秒horizon；中央simulation-only dispatch guard和原fixture刺激保持，不能作为完整任务或TDI样本。安全、控制与记录必须在同一个clean pushed freeze，禁止重跑/回填或运行中修改源码。新owner统一保存原fixture源/命令/物理observer/退出状态/全部SHA；标准任务没有这些刺激。

在前文ROS环境与canonical工作区下：

```bash
taskset -c 0-79 /usr/bin/python3 scripts/run_p2c_tasks.py \
  --manifest scripts/p2c_blackout_manifest.json --case physical_ideal \
  --run-id p2c1_blackout --domain 218 --gazebo-port 20298
taskset -c 0-79 /usr/bin/python3 scripts/run_p2c_tasks.py \
  --manifest scripts/p2c_blackout_manifest.json --case physical_fault \
  --run-id p2c1_blackout --domain 219 --gazebo-port 20299
/usr/bin/python3 scripts/check_p2c_blackout.py \
  --run-root "$PWD/log/p2c/p2c1_blackout" --output log/p2c1_blackout_gate.json
/usr/bin/python3 scripts/check_p2c_gate.py \
  --run-root "$PWD/log/p2c/p2c1_gate" \
  --blackout-root "$PWD/log/p2c/p2c1_blackout" --output log/p2c1_gate.json
```

实际使用尚未占用的domain/端口和全新run-id；222/11345属于用户会话，不能复用。完整P2C.1门禁现在必须包含两个同冻结物理探针；单格/开发PASS仍只是该范围验证。预算单位是仿真模型单位，不是joules或硬件校准安全保证。

默认电池节点现在由launch把本机原TF订阅remap到`/tbN/battery/source_tf`；该topic由现有本机TF入口节点从原TF提取并保留源时间，在gateway故障之前运行，入口缓存100/原生20，odom10与源TTL不变。原AP输入仍使用gateway/source_tf与gateway/received路径；不得向中央添加本地native订阅。标准启动命令和场景参数不变；此默认源绑定需要v20新原始任务冻结验证。

## P2C.1 独立返航准备就绪验证（2026-10-09）

这是独立受控安全表征，不是完整任务验收。p2c_blackout_manifest.json现使用stage_p2c_return_probe.py适配器，在原准备器前等待真实Nav2全局costmap新鲜且范围覆盖原准备位；原准备器/50秒期限/已知自由短腿/网关/断网及物理门限保持。旧对子保留FAIL，新对子必须使用新run-id和clean pushed freeze；两格都要运行并保留。原物理observations只做审计，不进入AP或无线负载。

准备就绪还要求原gateway交付battery中连续两个不同源时刻的ACTIVE、跨原0.5秒心跳且各自在原5秒TTL内；同源重复不计，RETURNING重置。只适配独立准备器，不改变task/native/原50秒期限。前两组原对子FAIL均保留，新stable run是第三独立对子，不能覆盖/回填。

本批已在609ba9d冻结执行并严格PASS（受控安全对子）；以下保留实际命令，已有run-id不可再次使用。后续新实验须另预声明/冻结/新run-id，并使用ROS Humble、仓库install、PYTHONNOUSERSITE=1与FastDDS UDPv4：

```bash
taskset -c 0-79 /usr/bin/python3 scripts/run_p2c_tasks.py --manifest scripts/p2c_blackout_manifest.json --case physical_ideal --run-id 20261009_p2c_return_stable --domain 218 --gazebo-port 20298
taskset -c 0-79 /usr/bin/python3 scripts/run_p2c_tasks.py --manifest scripts/p2c_blackout_manifest.json --case physical_fault --run-id 20261009_p2c_return_stable --domain 219 --gazebo-port 20299
```

这两个名字仅供本次首次运行，已存在则不可重用/覆盖；后续必须先冻结新的前瞻声明和run-id。关闭全部owned进程后用check_p2c_blackout.py --run-root log/p2c/20261009_p2c_return_stable --expected-commit 本次冻结SHA --output 新审计文件核对实际准备/物理/source证据；Nav2动作或准备器失败均使对子FAIL，后来native COMPLETE不能代替准备成功。

完整P2C.1B仍未通过。原v41 PARTIAL_COMPLETE保留success=false；新4开发→17正式+2物理要在同源通过，917尚未调用，不开展P4/ns-3/Wi-Fi/RL。
