<!-- 2026-10-07: P3C metrics and live fault console validated; GUI defaults documented below. -->

# 多机器人任务启动命令速查

本文只记录当前代码可直接使用的启动入口和参数。完整架构、实现说明和实验结果见
[`user_guide.md`](user_guide.md)。当前推荐入口是：

```text
multi_robot/gazebo_multirobot_mapping_with_nav2.launch.py
```

它同时启动 Gazebo、1–4 台 TurtleBot3、在线 SLAM、Nav2、地图融合、中央协同探索和
P2C 本地电池/充电管理；可选目标检测与 P2B 集结任务。手动运行默认同时打开贴地的 Gazebo
重点区域标记和每机器人实时状态栏。

最近核对：2026-10-08。P3A.6、P3B.5、P3C 已获用户验收；P3C.5已获用户验收（2026-10-08）；P2C.1安全补强为独立开发候选。
本次[项目评审](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261008_project_review.md)修补只读审计、重审原证据，原冻结任务证据不变。当前P2C.1已更改返航与任务准入预算，进入后续闭环实验前须完成新冻结和完整集成验证；当前无容量模型，Wi-Fi瓶颈尚未测量。
历史验收任务栈冻结在 `d8d361b`，P3B.5最终报告提交为 `d0b1561`；当前P2C.1候选尚待新冻结，原十格不能替代其验证。
本文第 1–8 节用于当前运行，第 9 节保留历史候选记录；其中“未通过”“未暴露”等描述
只适用于记录当时。当前结果见 [P3B.5 完整报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261006_p3b5_gate.md)。

维护要求：以后新增或修改 launch 参数、默认组件或推荐运行方式时，必须在同一个提交中同步
更新本文的默认命令和参数表。

2026-10-07最新状态：用户已验收原57格＋独立方向延迟6原任务；P3C 默认通信面板及独立故障配置服务已通过三真实任务、实时/CSV同源及实际Qt验证。任务算法不变。见[P3C报告与控台截图](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261007_p3c_gate.md)。

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

以下内容按当时的代码状态保留，不作为当前推荐参数或验收状态。当前入口及结果见第 1–8 节。

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


### P3B.5 固定故障任务配对矩阵历史记录（2026-10-01）

P3A.6 已验收。故障替身仍是应用层模型，不是 Wi-Fi/ns-3。
本地 battery_manager 用自己的 Nav2 action 执行安全返航；网络命令不能抢占 RETURNING，
融合地图断流后使用本机器人地图。中央导航、任务和提前充电请求仍经过 gateway。
`gateway_drop_message_types` 可按消息类别丢弃；`gateway_blackout_intervals` 从中央首次EXPLORE开始计仿真秒
JSON 区间（半开），例如 `gateway_blackout_intervals:='[[80,100]]'`。
`inject_failure_robot:=tb3 inject_failure_after_sec:=45.0` 仅用于仿真，从该机器人第一条
odom 起计时触发真实本地 FAILED；默认空机器人/-1 禁用。

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
source install/setup.bash
source /usr/share/gazebo/setup.sh
export TURTLEBOT3_MODEL=waffle PYTHONNOUSERSITE=1
export GAZEBO_MASTER_URI=http://127.0.0.1:11420
/usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_formal --ros-domain-base 30
```

manifest 正式冻结27个case；同配置ideal共享一次对照，任务终态/通信账本/旁路图全部保留。
`--validate-only` 检查计划，`--cases CASE...` 只用于独立开发批次。
`--resume` 只执行同commit/config尚未运行的格；不覆盖失败或重复整轮挑成功。
`ros_smoke_test.py --collect-fault-result` 收集有界故障结果，不把预期通信失败当作启动失败；
默认 smoke 的成功门禁不变。target 模式在中央消费交付事件后结束，本地确认时间另记。
全丢包时评估器也从就绪任务节点与真值位姿开始计时，不依赖融合地图是否送达。
通信静默只阻止新分配/完成确认，不从required集合移除机器人；只有显式失败才能隔离。

P3B.5启动修复：search_target在最后一台机器人spawn后生成，再错峰启动Nav2；smoke必须实际检查目标实体存在。连续丢包相对中央EXPLORE计时（ledger记录fault_epoch），不消耗在冷启动阶段。

正式runner默认同时记录只读safety_events.jsonl，观察local battery转态和中央robot_failure发布时刻，用于返充/隔离时间；该观察节点从不向控制链发布。新增零电量理想/故障配对仅检查真实battery_exhaustion/FAILED，理想已失败的格不计TDI。

P3B.5时间校准：Gateway从实际SLAM YAML的transform_timeout恢复TF的scan源时间（源码原生TF header=scan+timeout）；只修改AP副本，本地TF不变。缓存clock未追上sensor stamp时延后虚拟enqueue/tx到源时间，不允许负的排队时间。ledger含callback_time与clock_deferred。
`gateway_reorder_step_sec:=0.3 gateway_reorder_window:=8` 可让5Hz pose实际乱序；默认step仍0.05。ideal忽略故障queue capacity，使用4096正常有限队列；fault的queue capacity=1是显式拥塞注入，不改任务负载。

P3B.5 固定批量验证（先提交任务栈；每次使用新 run-id，原目录不覆盖）：

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_tasks_new
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_p3b5_tasks.py --run-id p3b5_safety_new --config scripts/p3b5_safety_probe_manifest.json
```

第一条使用27案例/41episode的完整配对矩阵；第二条是开发种子303的两项安全探针（4episode），分别观察长断网期间本地返航/充电状态、验证已接受导航动作的本地deadline取消。高idle_cost只用于该配对安全探针，正常任务默认能耗不变。FAILED现在显式取消电池管理器持有的返航动作，晚到的接受响应仍按模式校验取消。


2026-10-01 集结等待预算候选：默认电池启用时，首次最终集结派发等待串行预充电完成（安全让路仍可执行）；预算加入其他机器人的剩余路线及返航/实际充电时间的idle耗能，计算连锁充电需求。充电后按实际位置重排地图安全顺序。本地安全返航、能耗参数与完成标准不变；尚待同提交完整门禁验证。


2026-10-01 启动确认候选：默认robot/target使用spawn_entity_checked，spawn_timeout现在覆盖服务发现、单次创建请求与实际实体确认的总wall-clock预算；回包丢失但实体已出现可以继续，实体未出现/已有同名实体则失败并终止启动。该helper只读取启动实体清单，不将Gazebo truth交给任务控制。原launch命令不变。


2026-10-01 路线预留候选：替代上述全局预充电屏障。提前充电仍串行，但已充满机器人可沿不冲突路径前进；当前及待执行返航路线保留，充电机器人保留实际占位，未知返航几何则等待。活跃队友只有在其包含当前位置的剩余路线已预留时移出静态绕路mask；跟随者停在预留冲突前，不穿过停靠/故障机器人。等待能量预算、本地安全保留量、速度/clearance/300秒完成标准不变。


2026-10-01 TF接入候选：每机器人默认启动gateway_tf_ingress，原生map→odom的新样本经/tbN/gateway/source_tf进入统一gateway；重复TF/odom-base不会排在多端点网关前。源header不改，min_interval0.5s/TTL2s不放宽；本地Nav2仍接原生TF。不同mission mode和ideal/fault均使用相同接入路径。


P3B.5 原生启动检查候选：生成器以 ModelStates 和 `/get_model_list` 只读服务核对实体；只重查清单，不重复生成。smoke 使用持久原生 GetState、图查询和真实消息订阅，严格核对 ACTIVE 状态 ID/标签；检查仍有总时限，不改变 Nav2 生命周期。

补充物理返航开发配对（另加2episode；原四辅助probe保留）：

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id p3b5_return_new --ros-domain-base 90
```

参数冻结在 `scripts/p3b5_return_probe_manifest.json`。只读physics观察器记录 Gazebo 模型位置、本地电池和 Nav2 action 状态，写到 `log/p3b5/<run-id>_physics/`；控制节点不接收这些真值。断网守护窗口内，两机器人均须从距离home至少1.1m开始RETURNING、实际向home进展至少0.5m、至少0.5m路径具有原生Nav2 EXECUTING状态，且各充电一次，无碰撞或FAILED。在充电接触区进入RETURNING只证明状态/充电，不能代替物理导航证据。全部正式门禁预计57个独立episode：41primary、10固定ideal、6辅助；forced ideal复用primary对照。代码候选尚待全矩阵验证。

Gazebo factory 明确表示本次实体已经入队、确认阶段超时时，helper继续在原wall budget内核对实际插入。保存world的非零仿真clock可能让上游ROS-clock确认提前超时；该分支不重发创建。其他拒绝状态仍立即终止启动。

返航让路候选收紧：保护实际charge_radius_m对应的接触区，refuge须直接可见且位于整个返航通道guard之外，不把停在转弯前的短航段当作安全让路完成；busy返航期间暂停不经过预约的恢复/probe分支。yield搜索按最近路径逐个验证候选，1Hz重试；充电半径/能耗/速度/完成门限不变。固定ideal可按1+2+3+4同提交分批，check_p3b5_gate.py --ideal-fixed SUMMARY... 拒绝重复格/不同源码或环境；不能挑选成功覆盖失败。

2026-10-02 本地返航修复候选：充电中心不可达时，在原接触半径内选择已知自由、净空安全且可达的contact点（额外留0.2m目标误差），复用home规划的距离场。local Nav2不可用、map/pose缺失、contact/escape不可达会有5秒限频诊断。电池/半径/clearance不变；旧baec9ea物理探针耗尽已保留，该候选须新冻结验证。只读physics observer的原生UUID转int后输出JSON；wrapper会传播observer失败，任务runner成功不能掩盖测量失败。

2026-10-02 P3B.5 freshness/前沿候选：固定ideal runner默认每episode保存gateway ledger。中央pose/TF从源时间执行2s TTL，map/battery5s；一般freshness参数只能收紧。默认target detector在目标当前可见且连续确认后最多1Hz重确认，经同一gateway交付；60s目标lease过期暂停新集合/调查与完成保持，真实新确认恢复，旧重传不续期。独立本地返航和安全refuge不被目标过期阻止。粗前沿全部安全拒绝时在可达净空区域重新采样，原路线预约/净距不变。原命令/300s/能量配置保持。

2026-10-02 P3B.5 目标重观测：目标60s source lease过期时，默认在新鲜已知自由位姿、无活动导航/本地返航的条件下经同gateway原地尝试四个绝对朝向，四次后30s冷却；不使用过期目标坐标。实际新视觉确认交付后取消并排空扫描，再恢复集合。推荐固定ideal集成命令在原参数后加 `--fail-fast`，第一格失败即保存并停止；故障配对矩阵仍保留全部预设失败case。

2026-10-02 P3B.5 补充返航安全夹具（开发测试，非主任务/TDI）：source Humble/install并设置 `PYTHONNOUSERSITE=1` 后，在独占domain/master执行 ` /usr/bin/python3 scripts/run_p3b5_return_probe.py --run-id <unique_id> --ros-domain-base 180 --config scripts/p3b5_staged_return_probe_manifest.json`。它会暂时SIGSTOP当前runner唯一owned coordinator，经同gateway将tb1/tb2沿不相交已知自由路线移至声明远点；50s准备截止、60..250断网；本地真实充电后SIGCONT。绝不能用于主矩阵/heldout，准备失败仍保存。原自然探索40..250配置和失败证据保留。

2026-10-02 补充返航夹具路径修正：上述config现在使用tb1 `(0,-2.45,-pi/2)`、tb2 `(0,2.45,pi/2)`；原左右点虽LOS可见但不足.45m净空，失败原记录完整保留。运行参数/准备50s/断网60..250均不改，等待原因及首次拒绝地图快照写入episode目录。heldout707首次执行使用独立fault seed27077（manifest对应3个profile），开发仍17011。

2026-10-02 补充安全夹具只经当前map已知自由/可见的≤.75m前缀逐段到声明远点；latest-only接收，不直接派发未知终点。配置finalpoint/50s准备/60..250断网和物理阈值不变，准备失败原记录继续保存。

2026-10-02 补充返航夹具的prepare完成标志为一次性锁存：机器人达到声明远点后不再收到准备目标，等两台原生实际充电完成后才释放coordinator。命令与全部阈值不变；证据分析拒绝完成后/50s后新准备目标，旧ideal重派发失败保留。

2026-10-02 零能量仿真反例：`--battery-initial-energy 0` 仅在use_sim_time启用时允许；本地电池启动即FAILED/battery_exhausted，不发布短暂ACTIVE或导航动作，持续以当前仿真clock发布FAILED状态。评估器保留启动前失败并在原生位姿建立episode后按既有0.5s窗口收齐失败事件，不由reason消息抢先记no_data。正常初始能量/任务参数不变；真实非仿真模式仍拒绝零初始能量。正式预设battery_exhaust_lab理想/故障配对将先行，保留为原矩阵独立格，不在后续lab批次重复。

2026-10-02 P3B.5 航向与充电派发修复候选：tb1..tb4的实际Nav2参数goal_checker.yaw_goal_tolerance从3.14收紧为0.25rad，使viewpoint/原地扫描朝向确实达到后才成功。位置.02m、速度/足迹/碰撞检测/任务完成门限不变。串行预充电中，只在rally导航完全空闲时把ACTIVE且能量已就绪的机器人排在待充电机器人前；当前/未来本地返航路线及停车占位仍保护，不在活动腿中切换优先级。原命令不变，需新同提交十格及故障矩阵。只读physics helper支持--robot-count 3并保存yaw/angular_speed；默认2仍用于原返航配对。

2026-10-02 补充返航fixture更新（supersedes上面历史SIGSTOP命令语义）：`run_p3b5_return_probe.py --config scripts/p3b5_staged_return_probe_manifest.json`自动给smoke加`--enable-return-probe-pause`，对应launch `enable_return_probe_pause:=true`。此default-off/simulation-only开关从启动暂停探索/集合派发，DDS/全部输入callback继续工作，原强制livegraph/source审计不跳过。sidecar先读取owned coordinator实际enable参数为true，确认归属后才准备；两台真实充电后仅以owned SIGUSR2解除guard。不再SIGSTOP整个节点。只能用于该非自主安全夹具，禁止用于primary/fixed/heldout；所有普通命令显式false。50s准备/60..250断网/物理门槛不变。多机任务预算增加一次额外短航段往返的move/idle耗电；将候选能源不足与已commit返充动作区分，仅实际return/request/staging路线成为返充预约；未派发待充者仍保留真实停车占位和approach优先规则。需新冻结整批验证。

2026-10-02 启动失败记录修复候选：/robot_failure每条消息携带中央已隔离的完整failed_robots集合，双方transient-local reliable历史深度为机器人数量；晚加入的评估器按已知roster验证并单调合并，旧快照/重复事件不能恢复失败机器人。原始单robot事件兼容，native电池不替代中央隔离证据。普通命令和任务阈值不变，原零能量漏记失败保留，新冻结重新验证。

2026-10-02 目标恢复搜索候选：默认在目标60s源lease失效后完成一次四向原地扫描；仍无真实新确认时，复用新鲜map/pose/TF/battery的前沿收益和预约短航段，以单机器人继续搜索，保持FOUND/RALLY阶段且不引用过期目标坐标。不与集合/调查/扫描动作并发，不抢占本地返航；新视觉确认后取消并排空所有搜索动作再恢复集合，pending晚接收也取消。恢复探索有原60s超时/停滞检查，日志记录current_map_frontiers依据和实际路线。普通命令/任务成功/TTL/能耗阈值不变，须新冻结全门禁。补充return fixture准备期改用/gateway/message_events的fault_epoch，禁止用中央EXPLORE接收时刻代替断网起点；0..50s准备和62..248s物理窗口保持。

2026-10-02 观测接力候选：目标60s整体lease不变；最近真实新确认机器人在source age≤min(freshness,5s)、ACTIVE且还有健康伙伴时，保留视觉接触，暂缓其主动返充与home staging。健康已充电伙伴仍按原预约/能量规则接近目标，新交付伙伴确认更新observer，释放上一观察者；旧重传不能抢回接力。已admit返航不撤销，本地低电量保护/返航和容量不足失败始终优先，保护不等于豁免能量预算或允许未就绪集合。记录5秒限频handoff wait和实际确认robot，普通命令/时间/能耗/安全阈值不变，须新冻结全门禁。

2026-10-02 headless启动修复候选：所有ros_smoke_test.py及fixed/fault runner的无GUI子进程自动移除DISPLAY，避免继承桌面GLX drawable。原机器人仅CPU ray/IMU/contact传感器；实际模型/物理/seed/Nav2/任务阈值不变。manifest新增headless_launch_display=null、parent_display及GLX/software选项，保持ideal/fault同环境；直接GUI ros2 launch命令仍按原方式运行。prestart_failure_count改为全部未开始episode的attempt数量，包含最后首试失败，不再只统计重试次数；历史记录不改写。新同冻结门禁需要重新执行，不能复用旧探针PASS。

2026-10-02 集合末航向与真实观测公平派发修复候选：中间航段即使停在最终位置容差内，也必须成功执行与最终集合朝向一致的航段才标记arrived，避免跳过最后旋转。ledger同时记录实际请求位置/航向。目标检测器仍需当前可见、原距离/视场/连续三帧且全局最多每秒一次新确认；在所有合格可见机器人之间轮转，避免低编号观察者永久遮蔽伙伴的真实确认。原启动命令、完成位置/速度/5秒保持和消息lease、能量保护不变，须新冻结全门禁。

2026-10-02 实际绕行预算候选：纠正此前“6米”说明，原代码MAX_NAVIGATION_LEG_M=5m，无条件附加往返实际上为10m。新普通集合航段在发送前重新核对实际拟走路线、从末端到当前最终集合点的已知路线、该最终点返航储备、5秒保持和队友等待耗电，替代未发生的固定绕行；路径未知/参数非法/能量不足均不得派发，不足需求交给下一预检串行返充或容量失败。真实charge staging保留原预算直到充电；必要本地返航让路保持原安全优先级，由本地reserve独立保护。集合点重选仅在同一不可变地图/停车mask快照内复用两个距离场，排名/候选/安全门槛不变。命令与300s门槛不变，须新冻结验证。

2026-10-02 原生启动检查隔离候选：headless smoke的ready、model inventory和message检查在独立单次只读worker中执行，父进程以原startup/message墙钟deadline监督初始化、发现及等待，ready仍要求实际ACTIVE，实体/消息仍要求实际收到。worker验证完成后直接结束进程，由内核释放其DDS资源，避免任务runner反复创建/关闭ROS context；超时仅杀自己的检查worker并明确失败，ready期间launch早退仍立即失败。不跳过任何任务/graph/source门禁，不把已有COMPLETE raw盖过runner失败。manifest环境记录native_probe_isolation，所有ideal/fault/固定格共用。普通命令不变，包内算法与上次冻结相同；需新完整批次。

2026-10-02 P3B.5候选的原生命令确认：四台Nav2参数文件中`bt_navigator.default_server_timeout`为500毫秒，仅用于内部动作/服务确认；网关导航期限、300秒任务门禁及所有完成/能量/安全标准保持。现有启动命令无需新增参数；候选仍待同提交完整集成门禁。

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

2026-10-04 P3B.5 v57朝向保持候选：v56原lab101已归档7cc413c，不回填。网关交付odom朝向与map→odom旋转相加并归一化；当前观测者/guard停在集合位附近后，偏离请求yaw超过交付相机FOV的四分之一时重新开放原final导航腿。要求新鲜target/地图/位姿，ACTIVE、无pending/live与local-return refuge，原网关/能量/机体/在途路线/真实返航/并发保护保持。待执行未来路线优先级不阻止近位朝向校正，实际预约仍保护。448组件PASS14.00s、四包build5.10s、source-only3r audit0违规；证据见report/20261004_p3b5_observer_heading_component.json。v56交付yaw与native相符，物理朝向漂移原因未凭cmd_vel确认；候选修复中央未监测到位后朝向的问题，不能把预测或组件PASS当真实检测/任务通过。需要独立lab101/force303开发与新完整冻结，809尚未暴露，P3B.5未完成。

2026-10-05 P3B.5 v58候选只在目标确认源间断超过现有5秒观测者新鲜度窗口、但60秒目标lease仍有效时考虑停驻朝向校正；继续正常检测时允许安静保持。四分之一相机FOV、交付map-frame yaw、新鲜位姿/地图/目标、ACTIVE、网关导航/完整能量/实际body/route/return/并发保护保持。451组件PASS14.21s、四包build5.15s、source3r0旁路、27case/41unique validate-only；native_completion_ok/episode_ok原样，原300s/.35/.05/.1/5s未改。证据report/20261005_p3b5_observer_confirmation_gap_component.json；原v57五格FAIL已5f50357归档，不回填。809world/seed/fault原样未暴露，预声明更新控制SHA与实际launch静态补查并保留旧原文件标签/两次冻结历史。新完整v58自身按先force原生/E0/真实断网返充→十fixed→完整27/41+六辅助推进，提供新的lab101/force集成验证，无需另称独立开发PASS；总57原任务全部保留、无retry。P3B.5未通过，待完整门禁，无ns3/RL。

2026-10-05 P3B.5 v59开发组件：充电/同伴返航取消探索动作后保存搜索意图；恢复只优先最新地图中距原前沿≤1.2m、gain>max(200,原20%)且完整往返预算factor≥1的当前候选，继续经过源TTL/动态身体/已接受路线/可见短腿/gateway。旧意图不是旧指令重放；已观测/阻塞/预算不足回退、成功前缀继续意图、抵达或明确FAILED清除。针对20项1.14s PASS后补明确失败清理检查，完整472项13.60s、四包build5.34s、source3r0旁路。原native_completion_ok/episode_ok与300s/.35/.05/.1/5未改。证据report/20261005_p3b5_interrupted_frontier_component.json；原v58六格FAIL已a6830cc归档，809/28091仍未运行。接续为待集成验证启发式，无因果/最坏时间保证；将先冻结独立lab101/forced303/zero303开发，全部自然关闭后才能修改或归档，再重新冻结正式57格。P3B.5尚未完成，无ns-3/RL。

2026-10-05 P3B.5 v60组件：ACTIVE且无需预充电的真实观测者驻点选择，把待充电同伴home路线的驻点机体绕行加入名义时间评分；按observer候选/home缓存masked距离场，缺路线保留有限30s恢复代价而非假不可行，部分界仍乐观。本地返充独立监督已接受Nav2单腿：0.1m单调进展、20s无进展或max(30s,2*已知自由腿长/名义速+10s)超时仅请求一次取消，保留handle至result后重新规划，CHARGING/FAILED/terminal不干预；原总返航时限/储备/稳定充电未改。原300s/.35/.05/.1/5s与native completion函数原样，487组件13.72s、四包build5.38s、source3r0旁路。首return夹具漏callback1fail39pass、修正后321PASS；首parking夹具强求特定侧点1fail1pass，实际另一个funded非阻塞点更优，修正为验证入口不被堵与两条masked路线，全部487PASS；失败日志保留。独立AP条件重算选侧方点并消除预测绕行，0.81454s只是单次组件样本，无任务/因果/最坏保证。报告report/20261005_p3b5_observer_parking_return_progress_component.json。v59五格两失败已02c8d86完整归档，809/28091仍未执行；新独立开发和正式57格尚待验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v61组件：中央探索只准入当前可负担的完整前沿任务；未负担的前沿仍经当前地图/机体/可见短腿检查作为充电候选，不再执行已预计会被本地储备中断的远端fallback。所有已接收探索动作结束、无RETURNING/CHARGING后，只通过原gateway charge_request串行请求一个idle机器人提前充电，优先近home并保留当前前沿意图；充电后重新生成/核验。预算不小于充电目标或无效context不重复充电，现有rally pending owner覆盖阶段切换，2s重发；原10s请求租约保持，只在更新ACTIVE source超过租约后释放丢失请求，发现目标进入RALLY也适用。本地接受EXPLORE/FOUND_UNCONFIRMED/FOUND/RALLY有效幂等请求，拒绝未来/过期/terminal。增加charge决策输入租约与消费因果审核。516组件14.76s、四包build5.28s、source3r0旁路；native300s/.35/.05/.1/5s函数AST与d3acb28一致。首夹具5fail61pass：4漏导入、1误写5s而原租约10s；修正108PASS；跨阶段修复前515PASS日志保留。case template首命令漏--run-id仅参数解析失败，修正只读validate-only；不是任务启动/重试。组件报告report/20261005_p3b5_exploration_charge_admission_component.json。v60五格失败已d3acb28归档；809/28091未暴露，其旧cf73 controller声明待开发通过后前瞻重新冻结；新开发/正式57格仍未验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v62组件：当前2/3机前沿调度对无可负担替代、充电后可执行的idle同伴建立公平充电窗口；不再要求所有机器人耗尽funded工作才充电。停止新增探索腿但不取消原已接受动作，原动作自然结束后经同gateway串行请求返充，CHARGING期间有待充电同伴则暂缓新探索；同机器人有当前funded替代仍正常准入，无效/超容量预算不关闭其他funded准入。当前批次每机器人只保留最高效用的可行充电意图，跳过重复较低效用unfunded路线，但所有funded候选仍检查；20候选夹具路线调用≤2。集合叶评分对每个ACTIVE且无需预充电的驻点body累加charged peers home路线的单体绕行代价，而非只计observer；按body候选/home源缓存，非负部分界仍乐观，缺masked路线沿用有限30s恢复代价。它是加性静态启发式，不证明联合body路线可行，实际派发仍检查全部body/在途/返航/输入租约/能量。窄入口原parent分配nonobserver堵住第三机路径，新分配侧移后联合body路线4.0m；单组件0.02647/0.03615s不是任务/最坏收益。304定向11.48s、全部521组件14.11s、四包build5.36s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。v61五格3FAIL已c3319f0归档；报告report/20261005_p3b5_charging_fairness_parked_peers_component.json。新独立开发及正式57格仍待验证，809/28091未暴露，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v63组件：探索成功计数仅在真实成功的EXPLORE/FOUND_UNCONFIRMED前沿腿递增；已完成至少一腿、能量≤充电目标50%、离home>.35m且≤2×交付charge_radius的idle机器人，当前前沿准入且当前地图/所有同伴body允许已知自由可见航段真正到达home目标格时，可以优先通过原gateway补能。请求预算max(完整前沿预算,充电目标50%)，低于充电目标；不在初始出生位直接补满，不绕过本地储备或原10s租约。先让既有动作自然结束，串行返充并保留意图，充电后重新生成当前前沿；已满/远端/无成功腿/过期输入/阻塞home不触发机会补能。修复有active同伴但无selected时提前结束粗候选循环：仍执行当前body约束下的可达组件细化，空闲同伴可获得合法替代。531全组件14.40s、四包build5.78s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。首定向13fail319pass：home栅格中心被错误使用.02m比较而拒绝，及旧无电池夹具缺enable字段；改用同目标格判断/缺字段默认禁用后全531PASS，首次日志保留。机会阈值/返充/路径时间仍为启发式，无任务时限或收益证明。v62五格2FAIL已83cb590归档；报告report/20261005_p3b5_opportunity_charging_refinement_component.json。809/28091从未执行，新独立开发/正式57格待验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v64组件：本地RETURNING发送端保留已知自由规划staged.yaw，不再把每个中间腿朝向强写为零；最终home格仍按原planner零朝向，逃离fallback保持原行为，位置/路线/储备/返航时限/watchdog及充电稳定门不变。机会补能阈值从充电目标50%收紧到25%，请求预算max(完整前沿预算,充电目标25%)；普通E40富余阶段不因出生邻近再次充电，已真实成功探索、>.35m且≤2×charge_radius、当前数据新鲜、经同gateway串行请求等条件保持。可见已知自由home航段到达charge_radius−.2m接触区即可，而非必须与home同格，仍保留目标误差余量/peer body检查。537全组件14.86s、四包build5.48s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。新增普通能量不机会返充、可见接触区/边缘拒绝、0/正负pi/2执行朝向检查；本版首次全组件PASS。阈值、返航/行程仍为启发式，源码朝向错配已确认，但不宣称已证明任务耗时根因或收益。v63五格1必需FAIL已5041fc8归档；报告report/20261005_p3b5_charging_contact_heading_component.json。809/28091从未执行，新独立开发/正式57格待验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v66前瞻正式冻结准备：已关闭并完整保留v65五个独立开发原始结果且开发PASS；保持809.world/seed809/fault28091/目标(4.4,-3.4)/3r/E45原字节与最初静态声明，更新当前control与battery源hash及未暴露失败历史。809此前从未任务执行；同提交强制原生/E0/受控物理返充及十fixed全部PASS后才允许首次运行。57格/27pair/41主格、300s/.35/.05/.1/5s、原故障强度保持，不重试/回填。当前仍待正式完整门禁，无ns3/RL。

2026-10-05 P3B.5 v67准备程序修复与前瞻协议：受控返充fixture在known-free但净空膨胀起点复用现有navigation_start_route的.6m有界自由逃离；允许先增加距最终point的欧氏距离，之后通过当前地图共享plan_rally_leg已知自由visible路径绕行。不清障碍/未知格、不引入native truth，原始地图保持；四源TTL/current battery ACTIVE/gateway串行既有行为保持。最终点/50s/.75m/.35m/blackout60–250/1.1m远端/.5m实际Nav2返航/300s及原生保持门槛不变，native_completion_ok/episode_ok AST不变。61相关检查1.83s、539全组件14.80s、四包build5.30s/source3r0旁路、54配置检查及27cases/41primary validate-only PASS。控制器/电池算法源与v65开发PASS/v66force185.4原生PASS相同；v66五原始1操作FAIL及52unrun已c9719c5归档。809.world/seed809/fault28091此前从未执行，保留原字节/最初声明及全部未暴露历史，新增fixture源hash和当前准备协议。新冻结完整57格需initial强制原生/E0/受控实际返充及十fixed全PASS后首次809；本组件不是正式P3B.5通过，无ns3/RL。

2026-10-05 P3B.5 v68组件：实际发出集合预充电请求即使preflight失效；充电完成后停止接纳新集合腿，已接纳/待接受腿自然排空，再按当前地图与机体重算串行接近次序，原有本地安全/让行继续运行。完整串行机体避障可行排列优先减少后车未来路线覆盖前车当前位置、但反向不覆盖的单向接近逆序；只有未来优先级阻塞、实际已接纳/返航路线允许，且重新计算得到更少逆序时才排空重算，不在动作执行中换序。1.8m路线保留、.6m机体/.35m静态净空、源TTL/能量/300s/.35/.05/.1/5s原生完成门不变，native函数AST一致。542组件14.94s、四包build5.07s、source3r0旁路通过。历史中间单测1次作用域NameError、2项fixture恰到5s电池TTL而失败均保留，修复测试本身后284控制检查11.89s通过。v67 lab202接收AP快照回放中三种次序评分仍选tb3/tb2/tb1，32个已评估完整分配叶仍选入口观察驻点；不是原FOUND缓冲或反事实任务，不宣称该修正已经解决lab202超时或证明耗时收益。v67八原始FAIL与49unrun已f4dc4bb归档。报告report/20261005_p3b5_postcharge_order_component.json。新独立lab202/lab101及force/zero开发回归待执行；809/28091从未执行，正式57格尚未完成，无ns3/RL。

2026-10-05 P3B.5 v70正式协议前瞻重冻：v69六原始开发PASS后，将controller源SHA冻结为aa6cd7c03016e38ae7f5eec808b226b5fdb67f206a1038f7e61d27c4a06cb9d2，809.world/seed809/fault28091仍从未执行；原world/目标/3r/E45/300s/独立fault seed/电池/准备装置/原生完成阈值不变。追加v67冻结a7952b5八started/49unrun/原lab202 RALLY timeout失败与未暴露历史，不替换结果。54配置检查0.64s、54协议元数据矩阵、27case/41primary validate-only PASS；控制组件542/四包5.07s/旁路及六开发ledger/graph已有证据。新clean pushed同提交正式57格先initial强制原生ideal/E0/受控实际返充与十fixed PASS，再首次809及其余primary/safety。各独立world可在不同master/ROS domain/CPU组同时运行，全部原owner/观察器关闭后才审核/修改；不增加整轮重试或降低门槛。本协议及开发PASS不是P3B.5验收通过，完整正式门禁待执行，无ns3/RL。

2026-10-05 P3B.5 v71只读评估组件及v72前瞻协议：FAILED仍至少排空0.5秒；未收到每台原生电池状态、或已声明失败者原生mode尚非FAILED时，最多按现有battery TTL5秒收集，且不越过原任务300秒时限。重复FAILED不重置首次等待起点；到界仍保留缺失null，不从配置/AP/native安全旁录推断字段。已完整的失败证据仍按原0.5秒结束；FAILED期间不回落到coverage完成。该过程只采集证据，任务控制/本地安全已经失败或停止，不发布导航。34评估检查2.11s、546全组件15.18s、四包5.20s/source3r0旁路通过；新增迟到/永久缺失/非FAILED旧状态/重复FAILED/任务时限回归。原生保持函数和严格native_completion_ok/episode_ok源码一致。controller/battery/apparatus与v69六开发PASS字节相同；v70六原始失败/51unrun已afefd96归档，实际返航子门PASS，未回填。54配置及27case/41primary validate-only PASS；未暴露809 world/seed/fault保持字节及条件，新增evaluator源hash和v70未暴露失败历史。报告report/20261005_p3b5_failure_evidence_component.json。新clean pushed正式57格先initial强制原生/E0/实际返航及十fixed全PASS，再首次809。完整P3B.5尚未通过，无ns3/RL。

2026-10-05 P3B.5 v73集合路径组件：串行排列评分仅在同一次不可变地图规划、同一机器人起点和完全相同机体障碍坐标配置内复用距离场；不同排列机体位置独立key，函数返回即丢弃，回退复用同一未屏蔽intent，不跨地图/位姿/TTL缓存。中间已验证路点与预约截断停点按实际入站路径末端0.3m弦朝向，减少绕墙时朝最终目标的额外转向；最终集合pose仍保留原请求yaw，交付目标可见朝向修正与实际body/live/return/源TTL/能量准入均保持。288控制14.41s、550全组件15.95s、四包build5.18s/source3r0旁路通过；新增绕墙朝向/最终yaw、预约截断与障碍配置/地图缓存隔离回归。首新增夹具两项假设错误（整段直线与栅格末段方向差0.061rad；预约障碍未在预期点触发）已按实际几何修正，原失败日志保留，未改生产门限。五个保存AP快照新旧源码排序、路线及坐标相同；缓存条件对照构建16–17→11–12个距离场，离线中位耗时约1.10–1.22→.75–.86s，实际新旧源码再次对照约.51–1.11→.31–.84s，受同时任务负载变化影响，非原控制执行器计时或任务因果收益。原生保持与严格native_completion_ok/episode_ok源码一致，300s/.35m/.05mps/.1radps/5s及原TTL/净空不变。v72十五原始失败/42unrun已f62262f归档，未回填；809/28091仍从未执行。报告report/20261005_p3b5_incoming_heading_cache_component.json。需要新冻结独立开发回归与完整正式57格，P3B.5尚未通过，无ns3/RL。

2026-10-05 P3B.5 v75边际信息组件：普通前沿评分以当前交付地图的同一遮挡射线计算新增未知格比例，扣除健康同伴当前位置与已派发活动导航短段终点的预测观测重叠；不使用未执行的未来完整目标、目标真值或原生物理信息。评分乘以max(0.35,未重叠格/原可见格)，保留所有原候选与窄通道退路，原IG/路径距离/地图未知状态不变；不宣称预测格已完成。可见格cache随frontier cache按每次地图交付和规划副本变化失效，缓存只复用同一地图/半径。554全组件17.36s、四包build5.47s/source3r0旁路通过；新增共享/独立前沿、墙遮挡/有效未知格、同snapshot缓存和新地图丢弃旧cache回归。首三项失败是旧替身不接受新增keyword，已修正签名且原日志保留，无生产门限修改。保存AP三帧双机条件对照确认六组旧函数与无惩罚新函数候选完全相同，加惩罚后仍保留相同候选/路径/IG；该离线比较仅使用peer当前位姿，未还原原controller活动goal/回调buffer，不能证明任务耗时或因果收益。v74 late discovery/串行充电期间等待的原FAIL保留；另两种只读充电工作率和已返航后的出站refuge几何诊断已归档，但不足支持提前充电或出站抢占收益，未实现这些策略。原生完成与严格native_completion_ok/episode_ok、300s/.35m/.05mps/.1radps/5s、源TTL/实际body/live/return/完整能量准入保持。报告report/20261005_p3b5_marginal_information_component.json。新独立开发与正式57格待验证，809/28091从未执行，现协议controller hash尚待开发PASS后前瞻重冻；P3B.5未通过，无ns3/RL。

2026-10-05 P3B.5 v77探索入站朝向组件：撤回尚未通过开发门禁的v75同伴重叠评分及其可见格cache，恢复b5f6be5的原ray IG/组评分/候选函数；v76三项超时和全部六原始结果已61e43ca完整归档，不宣称已隔离出重叠评分因果。探索Assignment可携带实际已验证短段的入站yaw，仅当派发终点地图格不同于完整frontier viewpoint时保留；send_goal传到同一gateway/Nav2，不再丢弃中间绕墙朝向。到最终观察格仍用原frontier方向；既有rally路径cache/入站yaw保持，原路线/坐标/IG/效用/完整能量与源TTL/机体/返航准入不改。552全组件16.43s、四包build7.33s/source3r0旁路通过；新增真正assign_idle_robots→send_goal→Nav2请求回归，分别验证绕墙中间航点与最终frontier朝向。保存v74已关闭AP三帧双机条件几何显示中间前沿方向与入站方向约0.57–1.64rad差；未采集原cmd_vel/executor，不宣称实际耗时收益。另试组大小bonus封顶的离线排序六组首选均不变，未实施；没有新增提前充电/出站抢占/驻点自动完成策略。原生与严格native完成函数、300s/.35/.05/.1/5s及电池/评估器/准备装置/809world字节保持。报告report/20261005_p3b5_exploration_heading_component.json。下一六格独立开发与新冻结完整57格待运行，809/28091从未执行，旧P3A.6接受冻结保持；P3B.5未通过，无ns3/RL。

2026-10-05 P3B.5 v80前瞻正式协议：v79全部16原始任务/观察器自然关闭并归档ef24835后，保持controller/battery/evaluator/staging/world字节，重新预声明尚未执行的809.world/seed809/fault28091。v79十个固定任务全部原生COMPLETE，但strict same_candidate因预声明CPU0–19/20–39/40–59不同拒绝environment相等；原manifest不改，16started/41unrun与错误完整保留，不回填。新批全部十fixed及其观察器统一CPU0–79，独立world可在相同scheduler池并行，同world seeds串行；首次任务前AST解析实际helper计划并核验全部固定CPU相等、实际进程继承相同亲和性，原严格environment比较不改。初始/主故障池仍按0–19/20–39/40–59/60–79分区并用独立domain/master；所有池共享宿主资源/SMT，不宣称跨批耗时差为因果收益。61配置检查1.49s、27case/41unique validate-only和source3r旁路通过；552组件16.43s/四包7.33s及v78六开发PASS源仍相同。正式57格须新clean pushed同提交先强制原生ideal、E0双格、受控实际返充与十fixed全PASS，再首次809和其余primary/safety；原300s/.35/.05/.1/5s、源TTL、实际机体净空、能量与故障强度不变。报告report/20261005_p3b5_fixed_affinity_holdout_protocol.json。这是前瞻协议，完整P3B.5尚未通过，无ns3/WiFi/RL。

2026-10-05 P3B.5 v81保持诊断组件：在原本地/gateway/consumed记录每5秒的导航静止、位置速度、电池/预算、预充电和保持起点；原odom越界重置附实际源时间与原因。仅加入诊断，不改变任务决策、原生完成或保持重置。去除这些诊断语句后整个control.py AST与289a6ac一致；日志I/O可能影响调度，静态等价不是运行耗时等价。首组件13fail/539pass23.70s因旧替身漏robot_velocities，补齐测试夹具后552PASS16.77s，四包build5.35s、source3r0旁路；原失败日志保留。battery/evaluator/staging/strict checker/manifest/809world字节不变。v80原15started/42unrun失败已289a6ac归档，未回填；诊断还未证明晚充电根因或修复算法。报告report/20261005_p3b5_rally_hold_diagnostic_component.json；接下来冻结独立原始诊断任务，全部owner/观察器自然关闭后再依据实际原因改进。809/seed809/fault28091仍未执行；P3B.5未完成，无ns3/WiFi/RL。

2026-10-05 P3B.5 v84 Nav2平滑器时钟组件：四份机器人Nav2 YAML新增velocity_smoother.ros__parameters.use_sim_time=true，launch原RewrittenYaml仍可随use_sim_time覆盖；修复v83实际三机参数确认的controller sim/smoother wall时钟不一致。语义比对确认每份YAML只新增该时钟键；20Hz/OPEN_LOOP/速度/加减速/1s超时数值默认、RPP/angular.7/accel3.2、Nav2.02/.25、Gazebo物理参数均不改。Humble平滑回调仍wall timer，变更统一的是命令超时节点时钟，不宣称改变了回调时基或解决物理峰值因果。现有四参数配置/身体/RPP测试加入时钟一致性，552组件16.26s、四包build5.23s/source3r0旁路PASS。controller/battery/evaluator/strict checker/staging/manifest/809world/SDF字节不变，300s/.35/.05/.1/5s不放宽。原v83任务超时与三次测量失败已0a1d00e归档，未重启/回填；组件报告report/20261005_p3b5_velocity_smoother_clock_component.json。下一六格独立开发将查询实际clock配置并保留所有原始结果，随后新冻结正式57格；809/28091仍未暴露，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v87地图发布余量候选：主入口实际使用仓库内slam_toolbox overlay的mapper_params_online_multi_async.yaml，map_update_interval从5.0改为2.0秒。common发布循环仍使用原rclcpp::Rate，地图header仍是实际laser scan源时间，不用发布时刻续租；网关/协调器个人地图及融合地图TTL仍5秒，pose/TF仍2秒。理想与故障baseline统一使用该生成周期，预计增加地图计算和应用消息量；需在新独立开发及正式57格中实测源龄/账本，不宣称最坏交付时限或单因素因果收益。SLAM C++/激光处理/地图分辨率/机体净空/电池/原生5秒保持/300秒时限不改。v85原六任务与缺参数响应已完整FAIL归档；809/28091仍未执行，P3B.5尚未通过。

2026-10-05 P3B.5 v90观测者交接候选：保留最新交付target_detection对应的最后观测者角色直到其原60s源租约失效，不能把5s检测心跳缺口视为同伴已接替。收到另一个机器人实际新确认才转移保护；本地RETURNING/CHARGING/FAILED或已接纳早充请求仍可解除角色保护，capacity不足仍失败。相机心跳/朝向修复5s、target TTL60s、所有其他源TTL及原生完成限制均不改；保护角色不宣称当下仍可见，不生成或续租检测消息。实际同gateway早充串行/全路线与等待能量预算保持，理想/故障全部用新冻结任务栈。v88原六格FAIL和盲重搜/充电轨迹已14a5798保留；下一独立开发及正式57格待验证，809/28091仍未执行，P3B.5尚未通过。

2026-10-05 P3B.5 v93组件PASS（未作任务成功声明）：基于v91失败及审计更正恢复原观测交接5s门槛，严格checker不改。等待且未到最终驻点的最近观测者，可在当前已知安全位置对准交付目标；按原.35静态/.6机体/实际路线/返航预约/并发/源TTL检查，以自身返航储备加原goal-timeout空耗准入，独立本地返航可抢占，沿用有限survey动作/次数。真实调查前缀在已知可见且范围内时面向目标；完整驻点分配受阻且原靠近调查不可派发时，复用射线收益前沿候选，按边界距目标/原utility排序调查连接区域，保留观测机器人，可走先远离目标的已知安全绕行；不虚构未知格连通，不增加动作框架。朝向成功不延长地图准备计时或标记最终到位。首次聚焦9FAIL/301PASS（新地图假设错误及旧到位路径重叠），修正后311PASS12.88s；最终573PASS15.98s、四包5.37s、3r源码零旁路PASS，其他控制函数AST/电池/原生/evaluator/staging/协议/world/model/SLAM与Nav2参数hash不变。详见report/20261005_p3b5_observation_connection_component.json。开发101/202/303非holdout；809/28091未执行，新独立六格与新同提交正式57格待验证，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v96组件PASS、尚非集成验收：v94六原始全部自然关闭并FAIL归档后，修复探索前沿过期重规划：原“stale”分支要求20s无进展，正常时钟/进展更新下被原stalled条件覆盖；旧收益取中间航点也不代表最终观察点。现在只在源新鲜、原3s成熟/收益门槛、距航点>.75m，且另有空间分离/实际机体/在途预约/已知可见有效前缀/完整去返预算均合格的前沿时取消旧腿，待旧结果才正常重分配；预算不足/近到达/摄像重搜/本地RETURNING/已取消均保留原行为。观测者可在当前已知.35净空且.6机体安全的位置对准未过期检测，即使融合目标LOS尚未知；调查端点/原路线预约不改，只改变范围内观测者朝向，不授权走入未知或宣称可见。v94旁录lab101首次无遮挡样本187.9s、确认188.1s，证据支持物理接近偏晚；zero fault安全驻点/目标LOS未知/yaw出FOV条件回放只读取证不当原buffer或反事实成功。聚焦323PASS13.43s，最终585PASS16.27s、四包5.32s、3r源码零旁路；其它控制函数AST/严格checker/电池/evaluator/准备夹具/world/model/参数hash不变。详见report/20261005_p3b5_fresh_frontier_replan_component.json。无原生控制输入、门槛/TTL/时限/次数放宽；809/28091仍未执行；新独立六格及同提交正式57格待通过，P3B.5未完成，无ns3/RL。

2026-10-06 P3B.5 v99返航前缀组件PASS、尚非集成验收：v97六原始已自然关闭FAIL归档8cc441d。lab202实际tb3返充前两腿各20s停滞取消且Smac多次lethal-start；只读AP90/100自身格有多格占用簇，原单格自回波规则未清任何格，110..160自身虽known-free仍在净空膨胀区，原规划把短逃离与远端返航组合派发。现在只有已验证home/contact路线存在且包含原有known-free净空逃离时，先发送该原短前缀及实际入射yaw，待原动作结果再重规划；原占用/未知起点仍拒绝，所有障碍/未知/净空/机体/储备/TTL/返航总时限/watchdog保持，Smac/RPP仍可拒绝动作，不保证恢复或因果加速。54定向2.01s、591全组件17.28s、四包5.26s、3r源码零旁路；仅plan_charging_leg改动，其它电池函数AST/control/严格checker/原生300s与.35/.05/.1/5s/所有Nav2和SLAM参数hash不变。第一次inline只读诊断因stdin文件名失败，独立文件helper修正成功，原失败保留；无任务重试。证据report/20261006_p3b5_return_escape_prefix_component.json。开发101/202/303不是holdout；809/28091仍未执行，独立六格及正式57格待通过，P3B.5未完成，无ns3/RL。

2026-10-06 P3B.5 v101前瞻正式协议：v100全部六个独立开发原owner/观察器自然关闭且完整PASS归档后，更新当前control与battery源hash、四Nav2参数与SLAM2s参数，保持尚未执行的809.world/seed809/fault28091/目标(4.4,-3.4)/3rE45与原静态声明字节；原v80的15started/42unrun失败及其旧controller/battery/hash保留在冻结历史。开发源码仍为591组件17.28s、四包5.26s、3r源码零旁路；仅原已知自由净空逃离先单独执行，再于原回调重规划长返充，原占用/未知起点/障碍/净空/储备/Smac/RPP保护与时限不改。61配置检查、27case/41unique validate-only和source旁路PASS，无Gazebo任务启动。正式57格包括27pair/41主格、十fixed和六安全探针；所有fixed与AP观察器统一CPU0–79，其它池仍20逻辑CPU分区，独立world可并行同world seed串行，宿主/SMT共享不提供因果或最坏时间保证。AP只读参数请求使用有界2s重发，只测真实Nav2时钟/SLAM参数和map源龄，不重试任务、不续源header、不用于控制。所有源码/helper/协议首次执行前hash冻结，全部started原任务自然关闭前不改；原300s/.35/.05/.1/5s与TTLs/故障强度保持。必须先forced ideal原生保持、E0反例、真实受控断网返航与十fixed全部PASS，才能首次809及剩余主/安全矩阵；任何失败原样保留，无整轮重试或回填。证据report/20261006_p3b5_return_escape_holdout_protocol.json。P3B.5尚待完整严格门禁，无ns3/WiFi/RL。

2026-10-06 P3B.5 v103前瞻正式冻结：v101所有原owner/AP/网关观察器自然关闭且失败完整ae50fe1归档后，v102中间件组件dab2270已提交推送；当前control/battery/世界809原字节不变。新批统一显式RMW_IMPLEMENTATION=rmw_fastrtps_cpp/FASTDDS_BUILTIN_TRANSPORTS=UDPv4，所有机器人/总部/ideal及fault基线/只读观察器同环境；不使用未声明XML/discovery server。manifest新增环境记录，strict checker/native evaluator/control/battery均原字节；64配置1.51s、27case/41unique validate-only、source3r0旁路PASS；v102为598组件17.04s/四包6.87s和实际native descriptors/双向C++Python交付PASS，尚非新环境任务成功。原算法v100六独立开发PASS是在此前中间件环境，不能替代当前集成；v101五次调用/四原生启动/一缺结果/52未调用原失败仍保留。新AP helper仅只读真实参数/map源龄与实际RMW标识，使用本机已提供try_shutdown避免信号关闭后的重复shutdown异常；原AP partial metadata/traceback保持。正式仍57格：27pair/41主格+十fixed+六辅助；所有fixed/AP为实际CPU0–79，独立world可并行，同world seed串行；initial/main20逻辑CPU分池。所有源/helper/配置/最终报告builder在第一次运行前hash冻结；必须先强制ideal真实原生保持/E0/断网实际返航，再十fixed全部PASS，才首次运行809.world/seed809/fault28091/目标(4.4,-3.4)/3rE45及剩余主/安全矩阵。809从未运行，初静态world字节及真实launch连通补查保留；原300s/.35/.05/.1/5s、源TTL与故障强度保持，不重试/回填。全部已启动原owner/观察器自然关闭前不改源/文档/helper。证据report/20261006_p3b5_native_transport_holdout_protocol.json；P3B.5仍待完整strict gate，未启动ns3/WiFi/RL。

2026-10-06 P3B.5 v104合法避让驻点保留组件PASS：v103十fixed中lab303末段原生保持失败已7442599归档。仅在所有非避让同伴到位、在途/待接收动作结束后，对已完成目标朝向的临时驻点，用当前交付地图检查原.45净空/已知目标视线/相机range减.35误差余量/原.8最终位间距/.6当前body间距；所有电池ACTIVE、无返充请求、输入/目标新鲜且完整保持返航预算充足时，将同一个已到达pose保留为final。无新动作或朝向声明；原发布路径、能量预检重做、保持计时重置、原生300s/.35/.05/.1/5s继续。无效驻点按原逻辑回旧final。46定向1.40s、627组件18.50s、四包5.46s、3r源码零旁路；仅update_mission及新增retain_rally_refuge，其余控制函数AST、电池/严格checker/评估器/Nav2/SLAM/809字节不变。首状态机夹具遗漏logger两次失败44/45pass和首广测路径错误no-tests原日志保留，修正全PASS，无任务重跑。已关闭AP三帧几何支持合法驻点，但不证明运行准入/连续原生保持/因果加速或最坏时限。证据report/20261006_p3b5_rally_refuge_retention_component.json；809/28091从未执行，需新独立lab101/202/303+force/zero开发和完整57冻结。P3B.5未完成，无ns3/RL。

2026-10-06 P3B.5 v106前瞻正式冻结：v103十fixed原lab303保持失败和全部16原始已7442599归档；新控制v104c204e64与v105七独立开发PASS已2b87e5c保留并推送。原809.world/seed809/fault28091/目标(4.4,-3.4)/3rE45仍从未执行，world字节及最初静态/真实launch补查保留；更新当前controller SHA、控制源提交与开发引用，追加v103失败历史。当前保留合法已完成避让驻点仅为条件性恢复优化；七开发六原生COMPLETE、forced fault安全PASS，日志未见新分支触发，不能宣称新分支物理验证/因果加速或最坏时限。新批所有机器人/总部/ideal/fault/只读观察器统一显式rmw_fastrtps_cpp/UDPv4，无XML/discovery server；627组件18.50s/四包5.46s/源码3r零旁路，64配置1.71s、27case/41unique validate-only PASS，无仿真启动。正式仍57格：27pair/41主格+十fixed+六辅助；所有fixed/AP实际CPU0–79，initial/main20逻辑CPU分池，master19650..19656与独立domain。运行前冻结所有source/helper/config/report-builder哈希，按强制ideal真实原生保持/E0/实际断网返充→十fixed全PASS→首次809及其余主/安全矩阵推进；所有原owner/观察器自然关闭前不改源/文档/helper。300s/.35/.05/.1/5s、地图/电池5/poseTF2/target60/handoff5、原故障强度和实际储备/返充/机体/静态/最终位/在途预约保护不变，不重试/回填/把开发替代正式格。证据report/20261006_p3b5_rally_refuge_holdout_protocol.json；P3B.5仍待完整strict gate，无ns3/WiFi/RL。

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


2026-10-08 P2C.1 当前为v3开发候选：完整充电反向场预算/执行腿使用连通逃离终点，继续原0.6m已知自由逃离/.35m净空与TTL、保留失路30秒停止失败；v1/v2原任务失败已保留，组件824 PASS/1skip不代表新任务验收。两步前沿近站机会充电仅用当前交付状态，未来腿仍重新准入。默认launch/参数未再变化；新正式矩阵需事前推送冻结，917未暴露。报告在 wireless-rl/report/20261008_p2c_connected_escape_components.md。


2026-10-08 P2C.1 v4：battery manager新增原生odom/TF2秒源龄约束；launch自动把实际SLAM配置transform_timeout作为frame_stamp_offset_sec传给battery，值与gateway相同，原生TF不改。在独立直接启动battery manager时，frame_stamp_offset_sec须匹配该TF源实际有效时间偏移（构造默认0.5s；此项目launch从实际SLAM配置读取，当前为0.2s）。过期pose不能累计充电停稳时间或生成有限返航预算；缺姿态30秒停止后报告battery_return_pose_unavailable。原地图5秒/300秒任务/5秒保持及余量不变。840功能/1skip通过，候选仍需新冻结真实任务；917未暴露。


2026-10-08 P2C.1 v5修正：native odom/TF若略领先本节点/clock，保持原源戳暂存（<=原2秒、128项），clock赶上后处理，避免丢弃合法样本造成计费冻结。初始姿态未就绪先停等、已负担后恢复ACTIVE而不补满；原30秒缺输入停止/失败与原生门槛保持。每5秒battery_return_audit增加native只读能量平衡快照，仅评估观察器消费，不作为AP输入或网络流。847功能/1skip通过，当前仍候选，新源码门禁待运行；917未暴露。


2026-10-08 P2C.1 v6补充：v5起点姿态等待在快速odom入口错误转为充电，虽nativeCOMPLETE251.1/239live/能量PASS，强制返航证据不合格，原记录与新增reader FAIL完整保留。统一充电入口现先恢复已负担等待；实际DDS两个clock到达顺序、850功能/1skip、四包5.46s/172保护/54协议PASS。新4开发/17正式/两物理blackout待同提交冻结，917未暴露；原TTL/300s/5s保持，P3C.5已验收，无P4/ns3/Wi-Fi/RL。证据：[v6组件报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261008_p2c_charging_entry_components.md)。


2026-10-08 P2C.1 v7补充：v6四开发三原生COMPLETE/一lab RALLY timeout300.3，四原始失败/766live/成本账本全部保留，17正式/blackout/917未运行。新候选从新鲜完整已知接触区路径中择最小合格预算，融合路径不得清除本地已知障碍；计入最大所用源龄，两地图/成本/否决/择优只存在native只读审计，不作为AP新信息，不增加通信。863功能/1skip、四包5.36s/172保护/54协议和P3C.5旧14 native reader通过；新全批次待冻结运行，不称已有任务收益。证据：[v7组件报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261008_p2c_multimap_components.md)。


2026-10-08 P2C.1 v8：v7四开发三COMPLETE/一lab集合timeout300秒，四格零接触/耗尽/failed，760live及原生能量/返航择源审计通过；原失败完整保留。返充预约现用AP已交付地图的完整接触区路径并复用原几何缓存；充电身体、实际本地安全权威和失路等待保持。集合/剩余/驻点绕行补计实际起点到首网格点距离。初次“五米前缀”诊断已撤回（原默认无限长），首失败与更正保留。866功能/1skip、四包6.25s/172保护/54协议PASS；仍需新同提交4开发/17正式/真实blackout，917未暴露，不宣称任务收益。 证据：[v8组件](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261008_p2c_rally_contact_components.md)。


2026-10-08 P2C.1 v9：v8强制首格EXPLOREtimeout300.1/tb1正电量失路FAILED，原始/282live/成本账本保留，三开发/17正式/blackout/917未运行。中央完整当前/终点预算、集合候选和返充预约现核验同网关交付的机器人图与融合图路径资格；融合捷径不能清除该机器人已知障碍，价格计入最旧已用新鲜源龄。AP私有否决与预测双图证据可重建，不读取本地native隐藏输入、不增加应用流量。本地battery与核心返路算法未改；878功能/1skip、四包5.57s/172保护/54协议PASS，仍须新全cohort，不作任务/硬件安全收益外推。 证据：[中央一致性组件](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261008_p2c_ap_consistency_components.md)。


2026-10-08 P2C.1 v10前瞻：v9首强制原格271.7s因目标区域survey失败，195.3s检测/未RALLY，两机各charge1/最低9.868180/零接触、耗尽和机器人失效；strict FAIL与257live/6返航预算/110能量样本/24AP否决重建完整保留。新候选只对不可变交付地图复用几何，将原连续障碍否决向量化，记录完整失败分配上下文；原300s/5s/TTL/净空保持。组件验证以新报告为准，新4开发/17正式/两真实blackout仍待同提交冻结验证，917未暴露。证据：[v9原失败](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261008_p2c_v9_failed_development.md)。P3C.5已验收，无P4/ns3/Wi-Fi/RL。

2026-10-09 P2C.1候选：v10两开发COMPLETE/两任务失败，完整FAIL保留；v11增加由两原图确定重建的constrained_fused返路候选，source_time取最旧，两原源TTL均不延长，不改变原Nav2/物理/300s/5s。新任务必须从clean pushed freeze调用原run_p2c_tasks，17formal/blackout/917尚未执行。证据见无线研究目录report/20261009_p2c_v10_failed_development.md；当前P2C.1未通过。

2026-10-09 P2C.1 v12前瞻：v11强制首格原生RALLY timeout300.2，发现222.1/集合223.8s，两机各charge1/最低15.327770819，零接触、耗尽或机器人失效；strict FAIL和18份原证据保留。tb2在已有接触区补能（native返航运动约9.16e-7m），不得当远端返航证明。旧终点失去合格返航后缺少在线重选；新候选仅在idle/未到位/非observer/无活动动作和安全返充时，搜索原1..2.6m区域的已知自由可见网格，保留0.45m净空/0.8m间距，核验完整去返/源龄/保持等待成本，再交原派发复查。构造旧AP双图+0.4s后的live快照证明稀疏候选无合格点、网格替代约0.135m；非原控制器反事实/任务收益。原300s/5s/TTL/Nav2/物理/重试保持；仍需新clean pushed4dev/17formal/2physical，917未暴露，P3C.5已验收，无P4/ns3/Wi-Fi/RL。

v12组件验证：937功能/1skip48.75s、最终37定向18.78s（含重选→再预算）/四包5.45s/172保护/54协议PASS；两次构造夹具FAIL原样保留并仅修正夹具源戳/缺属性，不改原始任务。报告：20261009_p2c_repair_components.md/.json；任务门禁仍待新冻结。

2026-10-09 P2C.1 v13前瞻：v12四原开发FAIL（forcedCOMPLETE295.2s；lab surveyFAILED224.5s；rooms EXPLOREtimeout300.2s；corr RALLYtimeout300.2s），四格零接触/耗尽/真实机器人失效、原始和48附件保留。房间2200条网关frame accepted最大0.204s而中央TF约12s，改AP四类连续状态订阅keep-last1、保持原源戳/事件/TTL；实际DDS50快照旧队列首31/41、新队列首50验证PASS。连续障碍采样改批量数组，原资格/完整路径保持，938功能/四包5.85s/172保护/54协议PASS。新4开发/17正式/两真实断网仍须clean pushed冻结；917未暴露，P3C.5已验收，无P4/ns3/Wi-Fi/RL。证据：20261009_p2c_snapshot_components.md与20261009_p2c_v12_failed_development.md。

2026-10-09 P2C.1 v14组件PASS、尚待新冻结任务：v13强制首原格RALLY timeout300.3/两机各charge1/min9.464354/零接触耗尽失效，tb2末段返航未闭合与AP咨询map漏键严格FAIL保留。新候选以已合格完整返路软净空暴露择点，补原环形样本与最多464个角边界分层点，精确缓存原有界逃离可达性；新TF重投影不续odom源戳，成功分配可独立重建。961功能/四包5.33s/172保护/54协议/actual DDS PASS；密集负查询17.34→5.57s，正查询略慢，构造分配更耗时，均非任务因果或硬时限。原300s/5s/TTL/native battery/Nav2/SLAM/物理保持；新4开发/17正式/2真实断网仍待clean pushed freeze，917未暴露。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。证据：20261009_p2c_angular_components.md与20261009_p2c_v13_failed_development.md。

2026-10-09 P2C.1 v15组件PASS、待新冻结任务：v14同提交四原3 COMPLETE（forced285.2/lab245.9/rooms275.7）/走廊RALLY timeout300.4，四零接触耗尽失效、原始与末次native return未closed FAIL保留。原网关TF交付≤.142s而native末段源龄多次>2s，提示本地队列积压；新仅native TF/交付融合图latest1，odom原10和全部非构造方法AST/control字节保持。actual DDS/domain218、961功能/四包5.43s/172保护/54协议PASS；原源戳/TTL/300s/5s/物理/安全不放宽。新4开发/17正式/2真实断网须clean pushed freeze，917未暴露；P3C.5已用户验收，无P4/ns-3/Wi-Fi/RL。证据：20261009_p2c_native_snapshot_components.md与20261009_p2c_v14_failed_development.md。

2026-10-09 P2C.1 v16相关TF组件PASS、待新冻结任务：v15首forced原EXPLORE timeout300.0/零充电/min10.576148/零接触耗尽失效；122native快照中110 TF过期且对应网关源龄≤1s，原始和未closed返航FAIL保留。新两个executor worker只并行轻量TF筛选入箱，原状态/电量/动作/充电在同一串行组，TF队列20/相关源后合并/guard唤醒，odom10与原源戳/2s/5s/128未来heap/安全保持。actual混合DDS/domain220、104定向/966全功能/四包5.20s/172保护/54协议PASS；control字节未改，新4开发/17正式/两真实断网仍待clean pushed freeze，917未暴露。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。报告20261009_p2c_relevant_tf_components.md与20261009_p2c_v15_failed_development.md。

2026-10-09 P2C.1 v17相对已知路径调度组件PASS、待新冻结任务：v16首forced原RALLY timeout300.3/检测280.8/两机各charge1/min9.728593/零接触耗尽失效；120native快照零TF过期，四返航闭合/能量PASS，原任务FAIL完整保留。新前沿效用按更近且当前预算充足同伴的已知路径作非零软折扣；补真实起点/有界逃离与完整机体绕行成本，派发重新核验完整去返预算。中央预算源龄改max(odom,TF)，保存两源龄及每条实际探索的交付图/模型/距离/折扣，strict reader重建。994功能/四包5.26s/172保护/54协议/实际AP DDS/192路径一致性PASS；native battery字节保持。原300s/5s/TTLs/净空/SLAM/Nav2/物理保持；新4开发/17正式/两真实断网仍待clean pushed freeze，917未暴露。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。报告20261009_p2c_relative_travel_components.md与20261009_p2c_v16_failed_development.md。
