# 多机器人任务导向无线通信调度工程实施计划

最后更新：2026-09-29。

本文把 `RESEARCH_PLAN.md` 的研究路线拆成可逐步实现、验证和验收的工程检查点。
研究边界、论文问题和最终指标仍以 `RESEARCH_PLAN.md` 为准；当前功能以源码和
`ros2_ws/ros2-multi-robot-automap/user_guide.md` 为准；实验事实以 `log.md` 和日期报告为准。

## 1. 实施原则

- 一次只完成一个可运行、可判定的检查点，完成后由用户检查再进入下一步；
- 先建立无 RL 的正确任务闭环，再完成协议可见性、应用负载和 Wi-Fi 瓶颈审计，随后比较强非学习
  基线；只有审计证明存在长期通信决策空间时才训练策略；
- 每个检查点必须同时交付代码、最短验证、日志和必要文档；
- 所有跨机器人/AP 信息最终必须经过显式通信边界，不能保留 ROS 直连旁路；
- 固定世界、参数和 seed 后再做策略比较，失败和超时也进入结果；
- 完整任务成功只对应 `COMPLETE`；发生机器人故障后剩余机器人集合产生
  `PARTIAL_COMPLETE`，这是可审计的部分完成，不计入完整成功率；覆盖率和 `FOUND` 是过程指标；
- 正式批次区分启动前基础设施失败和启动后任务失败，并保留全部尝试；
- 第一版固定消息内容/生成方式和机器人任务算法，只控制应用层消息准入；不提前实现 MARL、
  PPO/MAPPO、复杂地图压缩、未知初始位姿配准或 DDS-over-ns-3。

## 2. 当前基线

截至 2026-09-29（历史证据与当前 HEAD 分开）：

- ns-3 `wireless-rl` 是 5 用户抽象队列调度 MDP，训练、checkpoint、GPU、baseline
  和 held-out seeds 链路已验证；它只作为 RL 工具链资产保留；
- ROS 2 项目已有 Gazebo、1–4 台 TurtleBot3、SLAM Toolbox、Nav2、地图合并和
  headquarters frontier 分配；
- 主 launch 已用 action 可发现性和每台 `bt_navigator=active` 双重门控协同控制器，
  移除固定的 60 秒额外等待；任一导航栈未真正激活时不会带病开始探索；
- P3A 已将中央协调器、地图合并、检测事件和 Nav2 命令切换到显式零损 gateway；机器人
  Nav2 全局代价图也只消费 gateway 交付的融合地图，源码/ROS graph forbidden-bypass 审计通过；
- P1B 已加入只读真值评估器；P1C 已打通融合地图前沿、共享全局导航、分段路径和
  多机器人避让，最终代码上的 2/3 机器人 seeds 101/202/303 均达到 90% 且零碰撞，
  并已通过用户验收；
- P2A 已加入不参与探索决策的 Gazebo 真值目标检测并通过用户验收；P2B 已加入权威任务
  状态机、停止探索、安全集合位姿和全体稳定判定，正式 3 机器人 seeds 101/202/303 与
  2 机器人交叉验证均以 `COMPLETE`、零碰撞结束，并已通过用户验收；
- P2C 已加入机器人本地能量计、安全余量返航、独立充电位和充电恢复；两机器人强制充电
  episode 中两台各完成一次充电并最终 `COMPLETE`、零碰撞，并已通过用户验收；验收后补充
  了 Gazebo 重点区域标记和默认开启的机器人实时状态栏；显式消息和 Wi-Fi 场景仍未实现；
- P2D 已加入统一串行 runner、三个预验证 world/目标/能量场景和 schema v7 分阶段指标；
  lab/rooms 在 40 初始能量、走廊在 45 初始能量下完成 9 个三机器人固定 seed 和 1 个双机器人
  交叉检查，10 项均 `COMPLETE`、零碰撞，已通过用户验收；
- P3A 的 `GatewayEnvelope`、零损队列、接收状态存储、导航本地适配器和 forbidden-bypass
  审计已由用户验收；P3A.5 的当前 task-stack 重验证、固定 10 格矩阵、强制充电回归和
  manifest 也已由用户验收，冻结候选为 `2933c24`；
- P3B 的已完成范围已由用户验收：固定 seed 的应用层 delay/loss fault transport、TTL/版本、
  重复/乱序、ACK/有限重传、逐 attempt ledger、stale-state 安全语义，以及 54 格协议矩阵。
  P3B 原计划中尚未完成的 Gazebo fault-mode 任务矩阵、故障下任务指标和 ns-3 bridge 已重新
  标记为 P3B.5，不再把它们混写成 P3B 已完成；
- 当前工作边界是先完成 P3A.6 task-stack 重新冻结，再进入 P3B.5/P3C.5、Wi-Fi 瓶颈审计和强基线；
  P3A.5 的冻结结果只作为历史证据，不能直接作为当前网络/RL 基线；
- P2B 前路线审计补充了 P2D 完整任务集成门、P4A 时间/包级对账门和正式统计规则；教师评审
  后新增 P3A.6、P3C.5、强非学习调度基线和 RL go/no-go 门，详见
  `report/20260917_roadmap_audit.md`；P2D、P3A、P3A.5 和 P3B 已按各自边界验收；当前顺序先完成 P3A.6，再推进 P3B.5；
- 2026-09-02 只完成过一次单机器人 headless 启动检查，暴露过冷启动 spawn 超时和
  退出阶段重复 shutdown/map 保存问题。

## 3. 检查点和退出条件

状态使用 `待完成`、`进行中`、`待用户验收`、`已验收`、`阻塞`；`待完成` 统一表示尚未完成，
不暗示已经实现。

| 编号 | 工程检查点 | 主要产物 | 最短退出条件 | 状态 |
|---|---|---|---|---|
| P0 | 项目审计与路线固化 | 本文、文档入口、基线说明 | 规划与源码现状一致，后续步骤有明确依赖 | 已验收 |
| P1A | 可重复 ROS headless smoke | 固定 Gazebo seed、spawn 超时、自动 smoke 工具、干净退出 | 1/2/3 机器人均检查 topic、Nav2、lidar、合并地图并 PASS | 已验收 |
| P1B | 独立真值任务评估器 | episode CSV/JSON、阶段/失败原因、覆盖率、路径、碰撞接口 | 固定短 episode 输出字段完整，评估器不参与控制 | 已验收 |
| P1C | 快速理想通信探索基线 | 可选择 world、共同出生/充电区、seed、90% 覆盖率和 180 秒上限的批量入口与日期报告 | 原地图及开放/房间/走廊 held-out 地图达到 90%；2 机器人最慢不高于 120 秒、3 机器人最慢不高于 90 秒；零碰撞；记录 `observed_accuracy`/`occupied_iou`，后续批次须在运行前冻结非劣界 | 已验收 |
| P2A | 目标检测与确认 MVP | Gazebo 真值评估、视场/距离/遮挡、连续帧确认 | 目标不可见时不触发，可见并满足规则时进入 `FOUND` | 已验收 |
| P2B | 集合状态机 | 权威任务状态机、停止探索、独立 staging poses、保持判定 | 3 机器人收到理想直达目标事件后取消探索，在不同安全位姿以位置误差≤0.35 m、线/角速度≤0.05 m/s、0.10 rad/s 连续稳定 5 秒并只在此时进入 `COMPLETE` | 已验收 |
| P2C | 电池、返航和充电 | 可校准能量、本地安全返航、非重叠充电位、失败原因 | 至少一次被迫充电的 episode 中无耗尽，保留地图/任务并在充电后继续；不可返航和耗尽正确失败 | 已验收 |
| P2D | 完整理想通信任务基线 | 统一 runner、完整状态/阶段指标、跨目标场景矩阵 | 至少 3 个预先验证的 world/目标/能量场景各跑 seeds 101/202/303，完成探索→发现→必要充电→集合；另做 2 机器人交叉检查 | 已验收 |
| P3A | 显式消息协议和零损 gateway | 本地候选队列、序号/时间戳/ACK/过期、接收信息存储、命令适配器、旁路清单 | 零损 finite-rate 语义、旁路审计和安全等价通过；不把完成时间当作 P2D 等价 | 已验收 |
| P3A.5 | 历史 task-stack 重验证（冻结候选） | 历史 commit 的 P2D/P3A 完整矩阵、强制充电回归、manifest、ROS graph edge 白名单 | 仅作为历史证据；不能替代当前 HEAD 的重新冻结 | 已验收 |
| P3A.6 | 当前 task-stack 重新冻结 | 当前 HEAD 的 P2D/P3A 完整矩阵、强制充电回归、commit/config/environment manifest、ROS graph edge 白名单 | 在网络/RL 前重新跑固定门禁并输出 `task_stack_frozen_commit`；后续任务栈改动必须另开批次 | 已验收（2026-10-01） |
| P3B | 固定 delay/loss 网络替身（已完成范围） | 独立上下行、固定 seed 队列、TTL/版本、重复/乱序、重传、逐消息账本和 stale-state 降级 | 4 项协议单测、54 格固定协议 matrix `PASS`；故障语义和安全降级可复现 | 已验收 |
| P3B.5 | 故障条件下的完整任务闭环 | Gazebo fault-mode 任务矩阵、理想配对基线、任务/电池/碰撞/安全降级指标、机器人本地 freshness 保障、队列语义收敛 | 覆盖 `coverage/target/rally`、多 world/seed、丢包/延迟/TTL/deadline/retry/overflow；每格保留 ledger 和任务结果；健康机器人继续，未交付信息不触发错误任务；输出故障退化报告 | 待完成 |
| P3C | gateway 通信指标与实时可视化 | 默认打开的 gateway 监控面板、实时曲线、CSV/JSON 指标快照、ideal/fault 对比报告 | 生成/准入/发送/交付/丢弃字节闭合；实时显示吞吐、PDR、丢包、时延、队列、重试、AoI 和任务阶段；面板不参与控制，headless 也可保存同一数据 | 待完成 |
| P3C.5 | 应用负载与协议控制开销审计 | candidate/request/grant/heartbeat/critical-event 的频率、字节、队列、AoI、deadline、控制开销与可观测性报告 | 在真实候选生成规则下测量负载，明确中央未知信息和审计边界；不得把仿真器隐藏队列作为输入 | 待完成 |
| P4A | ns-3 数据包与时间同步 | P4A-0 trace ledger、P4A-1 固定窗/lock-step、Gazebo mobility、真实消息大小、资源/RTF 记录 | trace 生成/准入/发送/交付/丢弃字节闭合；相同 seed 事件账本一致；P4A-1 无墙钟竞态，记录 wall time、sim time、RTF 和资源峰值 | 待完成 |
| P4B | Wi-Fi 4 场景、负载与瓶颈审计 | AP+2/3 STA、传播、墙损耗、背景干扰、网络指标、实测校准集/验证集 | 在 P3C.5 负载和协议开销下测量排队、过期、竞争和交付瓶颈；参数有来源；无实测时标为 synthetic sensitivity，不宣称 sim-to-real | 待完成 |
| P5 | 强非学习通信调度基线与 RL go/no-go | 冻结场景/seed/主指标/最小动作集及 no/ideal/always/periodic/random/event、task-value greedy、freshness/deadline、link-aware、SchedNet-inspired | 同一 gateway 和配对 seed 一键运行，CSV 含所有任务失败和基础设施失败；完成负载/瓶颈审计后记录是否进入 RL | 待完成 |
| P6 | 条件式集中式 POMDP 学习调度（RL） | 可部署观测、candidate/request/grant 准入动作、硬安全覆盖、checkpoint | 仅在 P5 go 条件满足后训练；validation 选模并完成 held-out 比较；不以胜过 baseline 为工程条件 | 待完成 |
| P7 | 泛化、消融和统计 | 场景拆分、至少 20 个配对 held-out episode（每个主要 world≥6，推荐 24）、power/precision、置信区间、观测消融 | 先报告成功率及 95% CI，再报告 RMST/通信指标配对区间；主终点预注册为安全不劣下的 payload/airtime；若精度不足增加样本；明确优势、负结果及失效原因 | 待完成 |
| P8A | 单机实物链路与真实感知 | 相机检测适配器、UDP gateway、时钟同步、无线测量和安全返航 | 单机器人不使用 Gazebo 真值完成检测、消息交付、返航充电流程，并校准仿真关键分布 | 待完成 |
| P8B | 双机实物与 sim-to-real | 两机器人端到端任务、主要 baseline/（如有）RL 对比、失败样本 | 两机器人完成搜索、通知、必要充电和集合；保留全部尝试并报告仿真—实物差异 | 待完成 |

P8 前必须先冻结 `DetectionProvider` 消息契约：P2A/P3B 可使用集中式 Gazebo truth provider 或
离线 replay 验证消息路径，P8A 只替换为每机器人 camera provider；不能让真实视觉和网络首次集成
同时发生。当前 P2C/P2D 的独立充电位只隔离了通信变量，不能证明共享充电器的排队行为；P8B 需另做
单充电器/排队 stress 条件，并把并行充电能力列为硬件约束或明确排除。

## 4. 近期实施顺序

### P1A：可重复启动基础

实施：

1. 主 launch 显式传递 Gazebo seed，并把单机器人 spawn 等待时间参数化；
2. smoke 时关闭 GUI、RViz 和自动地图保存；
3. 自动检查每台机器人 `/scan`、`/odom`、`/map`、`/cmd_vel`，以及 Nav2
   controller/planner 的 `active` 状态；
4. 接收至少一条 lidar 和 `/merge_map` 消息；
5. 只终止本次 launch 的进程组，并判定是否能在超时内退出；
6. 分别运行 1、2、3 机器人，原始输出保存在 ROS workspace 的忽略目录，结论追加
   到 `log.md`。

此步骤只证明基础栈能够启动、产生数据并有界退出，不证明探索完成或跨 seed 可重复。

### P1B：真值评估器

预计先新增一个只读 ROS 2 节点，不修改 frontier/Nav2 决策。第一版只采集：

- episode 标识、world、seed、robot count、开始/结束仿真时间；
- 每台机器人轨迹长度和搜索期访问 mask；
- 合并地图已知 free/occupied 比例，以及相对固定真值地图的覆盖率；
- Nav2 goal 成功/失败、碰撞事件接口、任务阶段和终止原因；
- 超时样本写为失败，不只保存成功 episode。

验收先用构造的占据栅格和轨迹做单元测试，再跑一个短 ROS episode。只有评估口径稳定后，
才进入 P1C 多 seed 基线。

### P1C：理想通信基线

把 world、出生点、Gazebo seed、最大仿真时长和输出目录固化到批量运行入口。至少运行
2 机器人多个固定 seeds；这是保留的历史 direct-ideal 探索上界，不等同于后续
`zero-loss finite-rate` gateway。若基础探索不能稳定结束，先修 frontier/终止判定，不进入目标或网络层。

用户于 2026-09-14 确认首版使用 `my_world.world`，起始区域同时作为充电区域。首版采用
90% 正确自由空间覆盖率和 600 仿真秒超时。早期控制器在 300–600 秒仍停留于约 75%–80%，
一度把 75%/300 秒作为临时工程口径；该结论已被本轮根因修复后的结果取代，而不是通过修改
world、真值或覆盖定义降低门槛。

截至 2026-09-16，系统已修复自定义 SLAM 漏发 `map→odom`、建图时错误并行启动 AMCL、
控制器混用 odom/map 坐标、重复 merge 进程、单前沿单候选、前沿计算阻塞和边缘目标净空不足。
中央协调器在每台机器人的本地地图上生成多组可达安全观察点，用合并地图的信息增益统一评分，
并对活动目标做空间去重。seeds 101/202/303 的 180 秒正确自由空间覆盖率分别为
93.87%/93.90%/93.88%，达到 90% 用时 141.3/161.4/134.9 秒，三轮均零碰撞、零搜索重叠。
以上结果仅作为优化起点。P1C 后续固定 world、真值、覆盖定义、动力学上限和 seeds
101/202/303，分别评估 2/3 机器人；主指标为 `time_to_90`，同时报告 120/180 秒覆盖率、
路径、目标成功/取消/失败、碰撞、搜索重叠和地图准确率。优先优化协同分区与任务分配、
前沿效用、地图融合时效和 Nav2 目标执行，拒绝任何以降低安全距离、放宽覆盖定义或修改真值
获得的表面加速。90%/180 秒保留为正确性上限，不再视为速度优化完成条件；首轮以两机器人
平均 time-to-90 明显低于现有 145.9 秒、三机器人相对两机器人继续加速为方向，最终阈值由
多 seed 证据确定。95% 仍是可选更高里程碑。历史阈值实验见
`report/20260916_p1c.md`，本轮基础修复与最终证据见
`report/20260916_p1c_foundation.md`。完成 2/3 机器人加速优化并由用户验收后再进入 P2。

2026-09-17 的加速轮次保持 world、真值、覆盖定义、传感器、速度和安全距离不变，修复了
控制器/导航地图不一致、Navfn 在动态融合图上的规划失败、超过可靠距离的长目标、目标穿过
队友当前位置，以及“action 存在但 lifecycle 未 active”被错误放行的问题。最终使用融合图
统一提取前沿和路径，Nav2 全局静态层消费 `/merge_map`，Smac 2D 在完整非滚动全局代价图
上规划，并把超过 5 m 的中央最短路径拆成连续航段；局部激光和 DWB 继续负责实时避障。

最终代码上的正式结果如下：2 机器人 seeds 101/202/303 的 `time_to_90` 为
98.9/79.6/104.4 秒（均值 94.3 秒，原基线 145.9 秒）；3 机器人为
78.3/69.8/69.5 秒（均值 72.5 秒）。六轮全部达到 90%、碰撞总数为 0；两机器人重叠均为
0，三机器人最大重叠 0.44%，平均观测准确率分别为 97.25% 和 97.59%。因此保留 180 秒
作为故障可见的硬 episode 上限，采用“2 机器人固定 seeds 最慢不高于 120 秒、3 机器人
最慢不高于 90 秒”作为当前速度验收线；600 秒不再合理。详细过程和失败尝试见
`report/20260917_p1c_optimization.md`。该轮结果随后通过跨地图检查并由用户验收。

用户随后要求补充跨地图验收。项目新增开放障碍、房间门洞和长绕行走廊三张同量级地图，
而不修改控制器、Nav2、传感器、真值或评分。3 机器人在每张地图的 seeds 101/202/303
共九轮全部达到 90%，最坏 `time_to_90=75.5 s`，全部零碰撞，最低准确率 97.47%，最大
搜索重叠 1.91%。最难地图/最坏 seed 的两机器人交叉验证为 85.5 秒、零碰撞。主 launch、
smoke 和 runner 现在显式接收 world 文件并记录 metadata；详细证据见
`report/20260917_p1c_generalization.md`。该结果验证代表性静态室内几何，不替代 P7 的大规模
随机地图、动态障碍和分布外泛化研究。用户于 2026-09-17 验收 P1C。

### P2A：目标检测与确认 MVP

P2A 使用 Gazebo 中无碰撞体的红色静态圆柱作为搜索目标，默认位置 `(-4, 4)`。独立
`target_detector` 从 `/gazebo/model_states` 读取机器人和目标真值位姿，并使用与评估器相同的
world 真值栅格检查静态墙体视线。机器人必须在 3.0 m 内、目标位于 90 度水平视场内、视线
无遮挡，并连续 3 帧满足条件，才会从 `EXPLORE` 经 `FOUND_UNCONFIRMED` 进入 `FOUND`。
任一不可见帧会清零该机器人的确认计数。P2A 验收时该节点曾直接发布 `/task_state`；P2B
实现后它只发布 `/target_observation` 和 `/target_detection`，由协调器唯一发布权威
`/task_state`。检测器仍不修改探索目标、Nav2、地图、传感器、安全距离或评分规则。

3 机器人在 `my_world.world`、目标 `(-4, 4)`、seeds 101/202/303 下分别于
60.7/72.9/61.5 仿真秒确认目标，均由 `tb1` 发现，三轮碰撞和搜索重叠均为 0。目标放在
`(100, 100)` 的 10 秒负例保持 `EXPLORE`、`target_found=false` 并按 timeout 结束，证明
不可见目标不会误触发。构造栅格单元测试同时覆盖超距、视场外、墙体遮挡和连续帧重置。
完整命令、基础设施失败和逐轮指标见 `report/20260917_p2a.md`。P2A 现为
`已验收`。

### P2B：集合状态机

P2B 仍处于理想通信阶段。这里的“目标消息送达”明确指 P2A 事件在同机 ROS 中直接到达任务
协调器，不宣称已经验证网络可靠性。P2A 检测器在 P2B 中降为观测/事件生产者，不再拥有全局
任务状态；任务协调器成为 `/task_state` 的唯一权威发布者。协调器收到首次有效 `FOUND`
事件后停止新探索分配并取消所有活动探索 goal；从当前已知自由地图中生成 3 个不同、可达、
具备至少 0.45 m 障碍净空且相互间隔至少 0.8 m 的 staging poses，朝向目标，并进入
`RALLY`。发现机器人优先驶向自己的目标附近集合位，其余机器人再安全串行进场。不能把所有
机器人发送到目标坐标，也不能因为某台失败而从 required set 删除它。

`COMPLETE` 的固定第一版判定是：每台机器人到各自集合位姿的平面误差不超过 0.35 m、线速度
不超过 0.05 m/s、角速度不超过 0.10 rad/s，且全体连续保持 5 个仿真秒；任一条件破坏即
重置保持计时。无足够安全集合位姿、导航重试耗尽或 episode timeout 都要给出明确失败原因。
单元测试覆盖遮挡扇区、位姿去重、状态非法回退和保持计时重置；正式检查以 3 机器人
seeds 101/202/303 为主，2 机器人只做一次交叉验证。P2B 成功是 `COMPLETE`，不是 `FOUND`
或 90% 覆盖。

实现结果：目标确认后协调器会取消全部探索 goal，必要时让发现机器人补充目标区域地图，
再从已知自由空间分配朝向目标的独立集合位姿。最终位姿障碍净空至少 0.45 m、相互间距至少
0.8 m；到达路径使用 0.35 m 净空和不超过 1.5 m 的分段目标。协调器基于融合地图和实时
机器人位姿，为短航段做 1.2 m 路径预约，每次最多放行两个互不冲突的机器人；接近时由低
优先级机器人取消当前短航段并让行，随后重新规划。发现机器人拥有首轮优先级，但不再要求
其他机器人等它完成整个集合。协调器发布 `/rally_assignments` 和明确的
`/task_failure`；当前评估器 schema v6 记录阶段时间、发现时覆盖率、集合目标、最终误差/速度和
最小间距，并把 episode 内碰撞计为权威任务失败。

正式 3 机器人 seeds 101/202/303 分别在 134.5/171.9/177.3 仿真秒进入 `COMPLETE`，最终
正确自由空间覆盖率为 0.924/0.947/0.938，集合位姿最小间距为 1.210/1.221/1.414 m；全部
机器人误差均不高于 0.237 m，线/角速度均低于门槛，三轮碰撞为 0。2 机器人 seed 303
交叉验证在 96.5 秒完成，最小间距 2.025 m、零碰撞。全任务上限固定为 300 秒；这只替代
P1C 覆盖率任务的 180 秒上限，没有放宽任何 `COMPLETE` 判据。完整实现、失败演进和证据见
`report/20260917_p2b.md`。后续专项审查确认较低覆盖来自目标发现后按规则停止探索，而非
地图融合退化；集合 action 完整失败后的重试改用更短航段。并行集合和激进 watchdog 均因
安全/稳定性反例撤回。后续冲突感知并发只并行不相交的短航段，在 seeds 101/202/303 上把
平均集合阶段从 77.6 秒降至 61.7 秒且三轮零碰撞；详见
`report/20260917_p2b_audit.md`。用户于 2026-09-17 验收 P2B。

### P2C：电池、返航和充电

第一版能量模型保持可解释且可校准：移动距离和空闲时间扣能，`c_tx` 在 P3 尚无真实字节
账本前固定为 0。返航阈值使用“预计回家能量 + 安全余量”，属于机器人本地硬约束，任何中央
策略或后续 RL 都不能覆盖。仿真为每台机器人提供一个互不重叠的充电位，避免把充电排队变成
未研究的混杂变量；实物容量在 P8 重新按实际设备固定。

验收必须包含至少一个参数预先固定、会迫使一台或多台机器人充电的完整 episode，证明返航、
静止充电、地图和任务状态保留、充满后恢复均生效；同时用构造测试验证无法返航、耗尽和充电
超时的失败原因。不能把电池设得永远无需充电来通过检查。

实现结果：每台机器人运行独立 `battery_manager`，使用 odom 行驶距离和仿真经过时间扣能，
按保守路径系数估计返航移动/时间能耗并加安全余量；`c_tx=0`。低能量会在本地抢占当前 Nav2
任务并返回本机出生充电位，总部只消费 `ACTIVE/RETURNING/CHARGING/FAILED` 模式以暂停和
恢复分配，不能否决返航。充电位半径 0.25 m 且彼此不重叠，机器人必须在位姿范围内静止
10 个仿真秒才恢复满电；SLAM、地图和任务状态不会重置。

两机器人 `my_world.world` seed 303 强制充电轮使用容量 100、初始能量 18、移动成本 1/m、
时间成本 0.02/s 和安全余量 5。tb1/tb2 各返航并充电一次，最低能量 6.81/6.66，随后继续
探索，在 118.2 秒确认目标、126.2 秒进入 `RALLY`、190.1 秒进入 `COMPLETE`；最终覆盖
92.15%、总路径 49.733 m、碰撞和搜索重叠均为 0。评估器 schema v6 记录逐机器人初始、
最低、最终能量、返航/充电次数与充电时间。构造测试覆盖耗尽、返航超时/重试耗尽和充电
超时；完整证据见 `report/20260917_p2c.md`。用户于 2026-09-18 验收 P2C。

验收后的操作可视化补充不改变控制或评分：Gazebo 中用无 collision 的贴地高亮边界/圆盘标出
共同起始/充电区、每台机器人充电位、目标检测半径和状态机发布的集合位姿；独立 Qt 状态栏只读
订阅任务状态、Nav2 action、odom 和电池状态，实时显示每台机器人的动作、模式、位置和速度。
手动 launch 默认开启，两项都可用参数关闭；验证与使用说明见
`report/20260918_p2c_visualization.md`。

### P2D：完整理想通信任务基线

P2B/P2C 的组件通过后仍不能直接进入网络层，先增加 P2D 作为缺失的集成门。正式场景在运行
前固定为至少 3 个 `(world, target pose, energy profile)` 元组，覆盖不同地图结构和目标位置，
并预先验证目标周围有足够集合空间；每个场景运行 seeds 101/202/303，另选最难场景做一次
2 机器人检查。初始硬上限为 300 仿真秒；若 pilot 证明不合理，只能在正式批次前统一修改并
记录理由，不能按 seed 或策略调整。

P2D 输出完整阶段时间、最终状态、路径、分阶段重叠、充电、最低电量、碰撞和失败原因。
这组结果是后续所有通信策略共同的 ideal task upper bound；P1C 的 180 秒/90% 阈值不直接
套用到包含检测、充电和集合的完整任务。

2026-09-18 已完成实现与正式门禁。固定场景为 `my_world.world/(-4,4)/40`、
`p1c_rooms.world/(5,3)/40` 和 `p1c_corridors.world/(-4.5,-0.5)/45`。lab/rooms 六项记录在
`p2d_formal_ideal_energy40_v5`，走廊三 seeds 与双机器人交叉检查四项记录在
`p2d_formal_corridors_energy45_v6`；10 项全部 `COMPLETE`、零碰撞，完成时间范围
87.5–229.6 秒。lab seed 202 在 40 能量下实际完成一次安全返充后继续完成任务。走廊 40 能量
双机器人 pilot 会在后段返充并于 300 秒超时，因此按“正式批次前统一修改”的规则将该场景
提高到 45，而没有按 seed 调参。实现、失败样本和逐项结果见 `report/20260918_p2d.md`。

### P3：显式通信与因果闭环

P3A 先实现同语义的零损 gateway，不接 ns-3。跨边界上行至少包括地图版本/增量、位姿、电量、
任务状态和本地检测；下行至少包括融合地图版本/相关区域以及探索、返航和集合命令。当前代码中
`target_detector` 的 Gazebo 真值只可作为机器人本地传感器模拟器产生候选事件，中央不得直订
原始 `/target_detection`；`merge_map` 和协调器只能消费接收信息存储，中央命令由机器人本地
适配器调用 Nav2。P3A 代码已将 1–3 号机器人的 Nav2 全局代价图切换到 gateway 成功交付的融合地图；
验收时若 ROS graph 或源码审计发现回归，必须拒绝该批次，不能继续免费获得中央最新地图。
评估器可以读取真值，但不得发布给控制链。

P3A 必须维护机器可检查的 forbidden-bypass 清单，并用 ROS graph/源码测试验证中央执行节点
没有直订 `/tbN/map`、`/tbN/odom`、`/tbN/tf` 或直建 `/tbN/navigate_to_pose` action client，
机器人执行节点也没有绕过 gateway 直订中央 `/merge_map`；历史 P3A.5 已覆盖 launch remap、动态 topic 和 evaluator/truth 例外；当前 P3A.6 必须在
当前 HEAD 上重新执行同一审计。
零损 gateway 应复现 P2D 的消息语义，而不是保留两套实现；当前 P3A formal v2 因后续 HEAD
修改而只能作为 frozen historical evidence，必须在当前 task-stack commit 上重跑并写入 commit、
工作树状态、配置/协议哈希和环境版本 manifest 后才可验收。P3A 的 ideal 定义为
`zero-loss finite-rate`，保留真实候选生成/限频，不称为 unlimited。

P3B 先不接真实 Wi-Fi，而是用固定 seed fault matrix 覆盖 0/10%/100% 丢包、0/0.5/2 秒延迟、
重复、乱序、TTL 过期和 ACK/重传。每个 attempt 都写入 `source_time`、`enqueue_time`、
`admit_time`、`tx_time`、`delivery_time` 或 `drop_time`、`message_id`、版本和 correlation id。
冻结单一 `mission_mode={coverage,target,rally}`，launch 参数、评估器终止条件和 smoke 成功检查都
从该值派生；P3B/P4 的检测时延只从 `local_confirm -> delivered -> consumed` 账本计算，评估器
对 raw `/target_detection` 的订阅仅保留为 truth/debug。
100% 丢弃检测必须阻止 `RALLY`，命令在 deadline 内重传或明确失败，过期位置/TF 暂停新的中央分配，
过期地图不触发重规划，旧地图/状态不得覆盖新版本。导航命令必须有 deadline、幂等 command id、
最大重试次数和超时 abort，不能无限等待结果。

### P3A.6：当前 task-stack 重新冻结（2026-10-01已验收）

P3A.5 的 10 格结果是历史冻结候选，不能直接支撑当前网络/RL 比较。P3A.6 必须在当前
HEAD 上重新运行 P2D 完整理想任务和 P3A gateway 门禁，固定 commit、工作树状态、场景/目标/
电量、环境版本、协议哈希和 ROS graph/source bypass 白名单。所有机器人任务算法、消息生成
语义和安全规则在此门之后冻结；后续改动必须新开实验批次并重新验证。

退出条件：固定矩阵全部保留真实结果（包括失败），任务成功严格为 `COMPLETE`，零碰撞和
充电回归满足既有门禁；产出 `task_stack_frozen_commit`，并由报告明确区分历史证据与当前基线。

2026-10-01 当前重新冻结通过：`task_stack_frozen_commit=22c95a770a8812452c43fc177e4a00b5c032e6ef`。
clean同提交三批次1+7+2全部十格COMPLETE/零碰撞，无失效/耗尽、基础设施失败或整格
重试；同提交forced303为190.4 s COMPLETE、每台一次充电、零碰撞/耗尽。
127项组件检查、四包构建、源码与十一份运行时图审计通过。任务物理、电量、300 s、
COMPLETE/稳定门限未放宽。RPP/射线/分层/可视预约/最近refuge/相关TF限频，以及
完整集结能量预算和同gateway可靠TTL10 s串行提前充电构成当前冻结算法。
所有历史失败保留；其中baec4e8 rooms101是16.9 s post-start shutdown中断，
c08ca65 lab303有16碰撞事件，均不作为新基线。开发seed不替代最终holdout验证。
完整结果/命令/哈希/复核工具见report/20261001_p3a6_freeze.md/.json与log.md。
P3A.6门禁已于2026-10-01验收；P3B.5正在推进，后续任务栈变更须新批次重验证。

### P3B.5：故障任务闭环与保障性降级（待完成）

P3B.5 接收 P3B 的固定故障替身，但把验证对象从“协议消息是否按规则丢弃”推进到“消息故障
如何改变完整机器人任务”。这一阶段仍不接真实 ns-3 Wi-Fi；它只回答任务层和机器人安全层
是否正确面对已经定义好的延迟、丢包、过期和重试结果。

必须先冻结一份 `p3b5_fault_manifest`，每个 case 同时保存：task-stack commit、world、目标、
robot count、battery config、mission mode、fault seed、上下行 fault 参数、TTL、deadline、
retry、queue capacity、episode horizon 和环境版本。每个故障 case 都要有同 seed/同配置的
`gateway_mode=ideal` 配对对照。

任务矩阵至少覆盖：

1. `coverage`、`target`、`rally` 三种任务模式；
2. `my_world`、rooms、corridors 和至少一个未用于调参的 holdout world；
3. 2/3 机器人、开发 seed 与冻结的 fault seed 分层；
4. 上行/下行独立的 0%、10%、100% 丢包，0/0.5/2 秒延迟，固定 burst/独立丢包、TTL 过期、
   deadline、重试耗尽、重复、乱序和 queue overflow；
5. 目标检测、地图/位姿/TF、探索分配、集合导航、电池状态和返航命令各自的故障后果。

P3B.5 必须把机器人本地保障性行为写成可验收的消息契约：

- 地图、位姿、TF 超过 freshness TTL 时，中央不得分配新任务或据此重规划；机器人继续执行
  已接受且仍安全的本地目标，目标完成、超时或安全条件失效后进入安全停止/等待；
- 检测消息没有按时交付时不得进入 `RALLY`；已经进入 `RALLY` 后目标信息过期不得生成新的
  集合决策；
- 导航命令没有新鲜确认或超过 deadline 时，机器人取消/停止该命令并进入可恢复等待，不能
  无期限保持旧命令；
- 电池返航、低电量保护、碰撞急停和本地避障始终优先于网络策略；网络断开不能阻止安全返航；
- 重新收到新鲜地图/位姿/命令后，系统只能按版本和任务阶段恢复，不能用旧消息回滚状态；
- 单机器人故障隔离后，健康机器人继续探索或集合；剩余集合完成发布 `PARTIAL_COMPLETE`，
  不把部分完成计入 `COMPLETE` 成功率。

P3B.5 的每个 episode 必须同时输出任务结果和通信账本摘要：`COMPLETE`、
`PARTIAL_COMPLETE`、`FAILED`、`timeout`、`no_data`、`stale_state`、`navigation_deadline`、
`collision`、`battery_failure`、充电次数、最低电量、集合误差，以及按消息类型/方向的生成、
交付、丢弃、过期、重试和队列统计。高丢包条件不要求人为完成；验收要求是失败原因和降级动作
可解释、可复现、不会伪造成功。

为了把“通信变差了多少”压缩成一个可比较的主指标，正式报告冻结
`task_degradation_index (TDI)`：仅纳入 ideal 配对为 `COMPLETE` 的 episode；故障运行完整完成时
`TDI=0`，故障后为 `PARTIAL_COMPLETE` 时取
`1 - healthy_required_robot_count / required_robot_count`，故障、超时或安全终止时取 `TDI=1`。
跨 episode 报告 TDI 均值和 95% 置信区间，同时保留完成时间增量、覆盖率、最低电量、碰撞和
AoI/时延增量等原始指标。TDI 只表示任务结果退化，不能替代通信 PDR，也不能掩盖理想配对本身失败。

### P3C：gateway 通信指标和可视化

P3C 在 P3B.5 任务矩阵之上建立通信可观测性层，让 gateway 不再是黑盒。它不改变消息调度、
机器人控制或故障参数，不把可视化节点放进控制闭环。默认 GUI 运行时打开监控面板；headless
运行默认写出同一套 CSV/JSON/PNG（或等价无界面产物），保证手动运行和批量实验指标一致。

每个固定仿真时间窗（建议 1 秒，同时保留 episode 累计值）按 `direction`、`message_type`、
`sender`、`recipient` 统计：

- 生成消息数/字节、准入消息数/字节、发送 attempt 数/字节、成功交付数/字节；
- 丢包、TTL 过期、队列溢出、重复、乱序、重试耗尽的消息数/字节；
- goodput、offered throughput、delivery/PDR、loss rate、retry rate；
- queue depth、queue wait、admit-to-tx、tx-to-delivery、端到端 `source_time -> delivery_time`
  延迟，以及 p50/p95/p99/max；
- 每类消息 AoI 的 mean/p95/max、fresh-state ratio、stale-state duration；
- 导航命令 deadline success/abort、检测 `local_confirm -> delivered -> consumed` 时间、
  电池/返航状态消息新鲜度和任务状态传播时间。

面板至少包含四组同步曲线：

1. 上下行吞吐、PDR、丢包/过期率和重试率；
2. 排队/传输/端到端时延及 p95；
3. AoI/freshness、队列深度和消息类型占用；
4. 任务阶段（EXPLORE/FOUND/RALLY/COMPLETE/PARTIAL_COMPLETE/FAILED）、机器人运动、
   充电/故障事件与通信曲线的时间对齐。

P3C 的验收必须证明指标不是“看起来有图”：账本生成/准入/发送/交付/丢弃消息数和字节逐类
守恒；曲线使用仿真时间而非 GUI 刷新时间；ideal/fault 同 seed 可以叠加比较；GUI 关闭时仍
能保存相同数据；可视化节点只读 gateway ledger/metrics，不发布任务控制消息。P3C 输出的
故障退化图应回答：哪类消息先受影响、延迟还是丢包主导、AoI 何时超过安全 TTL、任务何时从
COMPLETE 退化为 PARTIAL_COMPLETE/FAILED，以及健康机器人是否保持了保障性动作。

### P3C.5：应用负载与协议控制开销审计（待完成）

在训练前，用冻结的任务栈和真实候选生成规则测量每类消息的生成频率、payload 字节、
candidate/request/grant/heartbeat/critical-event 控制字节、队列深度、AoI、TTL/deadline、
重试和等待时间。审计必须覆盖上行和下行，并把控制消息本身计入 payload、airtime 和能耗
账本。中央只能使用已经交付的摘要、请求、心跳和历史反馈；机器人隐藏队列不能作为免费观测。

退出条件：给出按任务阶段、消息类型、方向和机器人分层的负载分布，明确实际应用负载是否可能
造成排队/过期/竞争；若负载不足，记录“通信不是瓶颈”，不得先改规则或人为增加拥塞。

### P4–P7：网络、策略和统计（待完成）

P4 拆为两个退出点：P4A-0 先用 canonical JSONL 候选消息 trace 对账应用生成/准入与 ns-3 逐包发送、交付、
丢弃字节；P4A-1 选择并冻结一种桥接实现（首选带 message/clock ACK、退出和背压协议的 ZMQ 或 UDP），
再解决固定决策窗或 lock-step、Gazebo mobility 和时间同步；P4B 最后加入 Wi-Fi 4
传播、墙损耗和背景干扰。ROS 2/rclpy（system Python）与 ns3gym（conda Python）保持独立进程，
通过明确的 UDP/ZMQ/文件或 clock-handshake 桥接，不把两个环境强行混进同一 Python。这样“网络参数
不理想”和“联动时间竞态”不会混成一个问题。相同 seed 的 P4A 重复运行必须一致，应用消息字节与
ns-3 逐包记录必须可对账，并记录 wall time、sim time、RTF、消息吞吐和 CPU/RAM 峰值。

P5 在任何训练前冻结场景、训练/validation/test 划分、四类独立 seed、episode horizon、
主指标和基于真实候选队列的最小动作集。先运行 task-value greedy、freshness/deadline、
link-aware 和 SchedNet-inspired 强基线；所有方法固定消息内容、机器人任务栈和协议控制开销。
动作同时考虑机器人上行与必要的中央下行；2/3 机器人按同一生成规则使用各自固定维度 checkpoint，
不提前实现可变规模策略。所有 baseline 包括 ideal 都使用相同 gateway；正式启动前失败单独记为
`infrastructure_failure` 并保留，`episode_start` 后的任何故障都算任务失败，不得挑选补跑。
若合理消息负载和干扰下任务几乎不受网络影响，应记录“通信不是瓶颈”的负结果，不能用虚构
拥塞强行创造 RL 空间。

P5 还要冻结一个 `task_stack_frozen_commit`：它必须在当前 HEAD 上重跑通过 P2D/P3A 的完整门禁；
之后的探索、充电或导航优化另开 exploratory 批次，未经整套任务门禁不得替换网络/RL 基线。
P1/P2/P3 的 101/202/303 只作开发和集成 seed；正式 train/validation/held-out manifest 按
world、目标、能量和干扰分层，且不得与这些 seed 重叠。正式 runner 必须保留 pre-start
`infrastructure_failure`、post-start task failure，并写入 commit/config/environment manifest。

P6 只有在 P3C.5/P4B 证明存在可测的长期通信决策空间后才启动，默认采用集中式、部分可观测
单智能体准入调度；不因机器人数量而改成 MARL。工程退出条件是可部署观测、validation-only
选模、held-out 评估和硬安全覆盖正确。是否优于最强 heuristic 是研究结果而不是工程门槛；
RL 没有优势时保留负结果。P7 的主比较至少使用 20 个
独立且策略间配对的 held-out episode：先报告 success rate 和 95% Wilson 区间，再用固定
horizon 的 RMST 与配对 bootstrap 比较时间/通信指标；只有区间支持改善且安全不退化时才
声称 RL 有优势。

## 5. 每个检查点的交付模板

完成检查点时必须提供：

1. 改了什么，以及哪些计划内容明确未做；
2. 验收命令、代码 commit 和 seed/参数；
3. PASS/FAIL、输出路径、已知限制；
4. `log.md` 追加记录，必要时新增当日 `report/YYYYMMDD.md`；
5. `git diff --check`、`git add -n .`、focused commit 和 push；
6. 将上表状态改为 `待用户验收`，等待用户决定接受、返工或调整下一步。

## 6. 需要用户参与的节点

- 每个 `待用户验收` 检查点之后再进入下一项；
- P1C 前确认正式使用的实验室 world、出生/充电区域和合理 episode 超时；
- P2A 前确认目标类别和仿真检测规则；
- P2D 正式批次前确认 world/目标/能量场景矩阵和统一 episode 上限；
- P4B 前确认计划使用的 Wi-Fi 4 频段、信道、MCS 和实验室墙体参数来源；
- P5 正式比较前确认主指标、训练/validation/test 划分和样本预算；
- P8A 前确认真实机器人、相机目标类别、网卡/AP/OpenWiFi 数量和可用实验场地。

2026-10-04 P3B.5派发恢复候选已通过376组件检查、四包构建和source-only旁路审计。cab0568原43episode及所有开发失败完整归档；新候选修复final格航向、短暂观测间断、充电后的refuge退出和闲置future approach等待环。独立开发结果不能作为正式固定格或主故障/TDI证据。下一轮必须先新clean commit/push，再以同environment/CPU0-19完成全部十fixed，之后才运行原完整fault矩阵及首次707/fault27077；仍为待完成，原P3A.6冻结不改。

2026-10-04 P3B.5能量与观测者分配候选：在已交付电池启用时，集合点组合先避免让ACTIVE真实观测者返充，再最大化其扣除完整名义预算后的剩余电量；随后比较预计充电台数、串行路线/返航/充电时间，最后按原minimax或total_path路径指标决胜。预算包含去程、独立返航reserve、五秒保持、同伴路线和串行充电等待；无电池上下文时保留原路径分配。RETURNING/CHARGING不享有视觉观测者余量优先权，home仅为未来规划起点，不替代收到的真实位姿。分配只是预测，实际TTL、地图/LOS/净空、机体/在途腿/返航预约、完整绕行能量与本地安全仍逐次检查，不放宽300秒或完成标准。

组合搜索复用距离场、每机器人候选能量和最小预算；先解析观测者，再通过单列候选下界与单调等待闭包剪枝，完整组合使用实际选定值。大自由地图三个组件样例与旧原型分配一致，最慢从6.554秒降为约0.181秒；单次组件测量不代表任务因果加速或最坏时间保证。18个实际收到的AP快照/显式合成电池边界比较通过，非原协调器内部buffer重演。

397组件检查、四包build和source-only旁路审计通过。原834a0fd六started/六raw/0碰撞完整保留：lab101 COMPLETE265.4、lab202 timeout300.4/RALLY导致固定门禁FAIL；所有其余fixed/fullfault/707均未执行。v44开发timeout300.1/一次完成charge/0接触，随后晚返航；v45开发COMPLETE195.8/一次charge/0接触仅为开发证据；v47开发timeout300.0/RALLY仍未合格，保留。无完整current-body串行order时，v48改按未来最终位对后续接近路线的阻挡次数选择恢复顺序，实际机体与安全派发不放宽；v48本身仍timeout300.1/三charge，保留。v49探索偏好纳入前沿终点的返航距离及连续预算缺口，保持有用前沿退路与本地硬reserve。优化后的v49独立开发COMPLETE185.4/charge0/最低22.56212/0接触，原生5.5秒保持合格。全部失败、对照失败及开发source/import/hash/命令单列，均不回填正式固定格/TDI。新v41必须clean commit/push后以相同CPU0–19完成全部十fixed，再启动原27故障case和首次707/fault27077；P3B.5仍待完成。

2026-10-04 P3B.5地图起点与调查安全候选：在原source map之外维护规划副本；仅在原pose/TF 2s、map 5s源时效通过时，把已交付机体位置所在、八邻域全为已知自由且物理对角线≤0.1m的单格孤立占据回波作为自身回波处理。原始地图不改，墙线/连接障碍/未知格不清除；其他机器人实际机体、在途腿、返航与本地Nav2安全继续约束。此为受限回波启发式，不是一般障碍识别或最坏情况安全保证；导航账本保存使用的格、分辨率、origin与原输入源时效。原始occupied/unknown起点函数仍拒绝这类起点；独立规划副本的有界处理由单独反例验证。

目标区调查改为已知地图上的可视短腿，复用实际机体、在途集合与本地返航预约；若完整当前去程/终点返航预算不足，则缩短可选调查而非派发无资金全程goal。peer返航取消已接受或pending调查，晚接受也执行取消。FOUND调查成功不再因尚无最终集合位而被回调提前忽略；调查不能使用过期目标或绕过同gateway。300s、硬reserve、Nav2限制、0.35m/0.05mps/0.1radps/5s完成门槛保持。

原42b099e正式七started/七raw保留：fixed lab101/202 COMPLETE286.7/242.7且0接触，lab303 timeout300.3/FOUND、两charge、6接触；E0 pair正确FAILED/no nav，受控返航两侧仅EXPLORE300.3/300.1安全过程证据。固定FAIL阻止其余七fixed、fullfault与首次707启动。11张原AP快照的纯几何分配均无三机解，tb2原始起点单格100、可达candidate0；条件规划副本重放恢复11张三机解，非原内部buffer/任务重演。两个不改control的附加局部地图诊断均不作为formal证据：v50标签303实际上seed202，RALLY timeout300.1/0接触，绑定错误与实际参数保留；v51实际303 COMPLETE171.6/0接触，未重现单格故障。候选v52 lab303/202独立开发COMPLETE244.8/166.9，v53同source rooms101 COMPLETE126.1，均0接触、原生保持合格；成功开发格不回填正式格。416组件、四包build/source审计通过，P3B.5仍待新clean提交的完整门禁；已验收P3A.6冻结22c95a7保持。

2026-10-04 P3B.5基础设施复验候选：011786e同提交十fixed全部原生合格COMPLETE且零碰撞，但完整批次不能PASS：首次707 ideal COMPLETE148.1s，接下来的fault27077在机器人生成前未取得新鲜原生模型清单，90s原检查超时，episode未开始。原失败、所有其余自然结束结果、命令/图/账本/源哈希在report/20261004_p3b5_model_inventory_failed_candidate.json保留，未回填或挑成功。

三个网络中断后遗留的v11只读观察器按原输出路径、已消失owner与已释放master核对后仅用SIGINT关闭；复用domain产生的旧流混合尾部不当作原v11任务证据。新的只读观察器在导入rclpy前绑定Linux父进程死亡信号，托管runner传入确切owner PID以闭合初始化竞态；正常退出仍保存原观察记录。该机制不作用于任务控制节点。两个真实ROS观察器父进程退出检查通过。

run_p3b5_tasks默认domain base改为30；run_p3b5_return_probe默认90。domain范围提前校验0..232，严格使用声明的连续ID，不再取模改写；完整矩阵30..70，物理探针90/91。并发批次须事先分配互不重叠的domain范围及Gazebo master；下一冻结全批次使用显式20..95。生成器仅增加ModelStates消息和GetModelList请求/响应/超时计数，分开报告无清单和实体重名，原90s总检查、单次创建、原生存在性确认保持。独立lab101裸世界诊断在domain201与18均约2s收到模型/clock与服务成功，未复现原失败。Linux默认临时端口范围与高domain的重叠是配置风险，不能据此宣称已证明失败根因（[ROS2 Humble官方domain说明](https://github.com/ros2/ros2_documentation/blob/humble/source/Concepts/Intermediate/About-Domain-ID.rst)）。

425组件检查、四包build和source旁路审计通过；controller、故障manifest、300s、完成门限与安全保留量字节/参数不变。707已经在011786e暴露，后续只能称同策略基础设施复验，不称首次或全新未暴露heldout；保留首次ideal与任务前失败，fault27077的首次声明不改。新clean提交仍须先跑全十fixed再完整57episode门禁；P3B.5尚未通过，P3A.6已验收冻结22c95a7保持，无ns3/WiFi/RL。

2026-10-04 P3B.5 v43完整57次候选已自然结束，冻结584dadc；最终严格门禁FAIL，尚未完成P3B.5。十固定格原生合格COMPLETE，57次均0接触/0基础设施失败，57份时序账本审计PASS，425组件/四包build/54协议矩阵通过；这些不能代替完整门禁。主强制充电ideal中央297.5s声明COMPLETE，但300.0s截止时success=false、completion_time_sec=null、native_rally_hold_proof=null、termination=timeout，各机器人虽充电一次仍未合格。零注入zero_rally_lab同样RALLY超时，作为稳定性限制保留，不归因于通信损伤。完整原始结果、源/环境/协议/命令/graph/ledger哈希、观察器关闭与严格checker traceback见report/20261004_p3b5_forced_native_hold_failed_candidate.json；全部原格保留，不重跑回填或放宽300s/5s/位速阈值。当前需继续独立开发改进集合能量/时间分配并重新冻结。707此前011786e已暴露，584为同算法基础设施复验；下一次控制算法变化后必须使用预先冻结、真正未暴露的新留出组合，不再把707称为未暴露验证。P3A.6已验收22c95a7历史冻结保持；无ns-3/Wi-Fi/RL实验。

2026-10-04 P3B.5 v55独立开发回归通过，冻结cc21503：force ideal原生COMPLETE297.3s/两机各charge1；zero ideal/fault原生COMPLETE235.6/215.7s/各总charge1；force断网fault RALLY timeout300.3s，但两机各charge1、最低8.307、零碰撞。四原始结果、账本/graph/source/AP快照在report/20261004_p3b5_charge_time_assignment_development.json保留，不回填v43原57失败，开发仍非正式验收。force ideal仅2.7s余量，名义优化不是最坏时限保证。

新正式v56协议在首次运行前改用p3b5_holdout809.world/seed809/fault28091/目标(4.4,-3.4)/3r/E45；这是交错隔断、中央开口、旋转块与柱的新拓扑，静态SDF/visual一致、十box和0.45m净空连通检查通过，尚未运行新场景。707及旧27077首次声明/暴露原样保留为历史，不能称未见测试。主矩阵27case/41unique、同提交十fixed和六安全探针、300s/.35m/.05mps/.1radps/5s、原开发fault17011和已有故障强度保持。新冻结须先检查force ideal真实native保持，再全十fixed，随后含新留出的完整主矩阵；P3B.5尚未完成，无ns3/RL。

2026-10-04 v56冻结前检查：429组件12.92s、四包构建5.29s、source-only3r旁路0违规，27case/41unique清单validate-only通过，未启动Gazebo。runner manifest现在按实际选择case记录seed，不再硬编码707；严格gate新增预声明world/seed/fault及world/control纯bytes SHA验证。native_completion_ok与episode_ok两函数相对cc21503完全相同，300s/.35/.05/.1/5s与安全阈值未放宽。

2026-10-04 P3B.5 v56原候选FAIL，冻结3d079215caacf9e5e31866ca4db236a5cff3236c；14:55:48–15:17:15UTC自然结束，7started/7raw/0接触/0基础设施失败、7账本审计PASS，其余50格未运行。初始force ideal原生COMPLETE273.6s/各charge1、E0双格和双机真实断网返充探针通过；首个固定lab3/101在99.8s进入RALLY、300.4s timeout，2charges、最低20.8966，不能代替完整验收。只读原生诊断见tb2视线无遮挡时朝向转出90度FOV并产生检测间断，原因仍待核验。全部原始失败保留，不回填/重试/放宽300s与原生保持门限。新809/28091从未执行，可在仅开发seed修复后重新冻结控制SHA再首次暴露；初静态文件误把通用采样点标为spawn/charge，原文件保留，另以真实launch三个起点/充电点补查0.45m连通PASS，world未改。证据见report/20261004_p3b5_charge_time_lab101_failed_candidate.json。全部owned owner/观察器/master关闭后才归档，domain222未动；完整strict checker/PASS报告/图未执行，P3B.5仍待完成，无ns-3/RL。

2026-10-04 P3B.5 v57朝向保持候选：v56原lab101已归档7cc413c，不回填。网关交付odom朝向与map→odom旋转相加并归一化；当前观测者/guard停在集合位附近后，偏离请求yaw超过交付相机FOV的四分之一时重新开放原final导航腿。要求新鲜target/地图/位姿，ACTIVE、无pending/live与local-return refuge，原网关/能量/机体/在途路线/真实返航/并发保护保持。待执行未来路线优先级不阻止近位朝向校正，实际预约仍保护。448组件PASS14.00s、四包build5.10s、source-only3r audit0违规；证据见report/20261004_p3b5_observer_heading_component.json。v56交付yaw与native相符，物理朝向漂移原因未凭cmd_vel确认；候选修复中央未监测到位后朝向的问题，不能把预测或组件PASS当真实检测/任务通过。需要独立lab101/force303开发与新完整冻结，809尚未暴露，P3B.5未完成。

20261005 P3B.5 v57独立五格开发FAIL，冻结f8297fa，15:53–16:06:36UTC自然结束后归档；lab3/101 RALLY timeout300.3s/1charge/最低20.27738/0碰撞。force ideal/fault原生COMPLETE295.3/299.5s、各两机charge1；zero ideal/fault原生COMPLETE247.5/167.0s、总charge1/0。五账本时序TTL/versions与graph旁路审计通过，五格0接触/0infra，无任务重试。lab最终位置误差小于3.3cm，但原生近末段最长合格窗口3.0s；289.7/298.7s额外朝向腿发出时目标源龄仍1.2s，候选需要限制持续正常检测时的校正，避免干扰保持。原开发失败不回填v56，不放宽300s/.35/.05/.1/5s；809/28091未执行。完整证据见report/20261005_p3b5_observer_heading_development.json；P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v58候选只在目标确认源间断超过现有5秒观测者新鲜度窗口、但60秒目标lease仍有效时考虑停驻朝向校正；继续正常检测时允许安静保持。四分之一相机FOV、交付map-frame yaw、新鲜位姿/地图/目标、ACTIVE、网关导航/完整能量/实际body/route/return/并发保护保持。451组件PASS14.21s、四包build5.15s、source3r0旁路、27case/41unique validate-only；native_completion_ok/episode_ok原样，原300s/.35/.05/.1/5s未改。证据report/20261005_p3b5_observer_confirmation_gap_component.json；原v57五格FAIL已5f50357归档，不回填。809world/seed/fault原样未暴露，预声明更新控制SHA与实际launch静态补查并保留旧原文件标签/两次冻结历史。新完整v58自身按先force原生/E0/真实断网返充→十fixed→完整27/41+六辅助推进，提供新的lab101/force集成验证，无需另称独立开发PASS；总57原任务全部保留、无retry。P3B.5未通过，待完整门禁，无ns3/RL。

2026-10-05 P3B.5 v58原候选FAIL，冻结cf73eebd875d990bd782cef572d09b484b23900a；2026-10-04 16:19:20–16:33:04UTC自然关闭。6started/6raw、0接触/0基础设施失败、6账本与6图审计PASS、54纯协议PASS。强制充电ideal直到242.2s检测、260.2s进入RALLY，300.4s仍有tb1在最终路线中，各charge1、最低8.11062，无原生COMPLETE，不能判通过；force fault300.2s也RALLY timeout。E0双格为预声明FAILED且无导航；controlled remote双格各充电一次/正能量/0接触，关闭后只读严格physical-return审计PASS，证明断网窗口中的实际Nav2返航，并非任务成功。其余51格含全部固定与809未启动；新809/28091仍未暴露，原707不得视为未暴露。只读日志显示返航取消西侧前沿后，充电恢复按即时收益重分配到东侧，再回西侧而造成较晚检测；这是待开发验证的任务接续问题，不是单次运行的因果收益证明。报告见report/20261005_p3b5_confirmation_gap_forced_failed_candidate.json。所有owned owner/观察器/master自然关闭后归档，domain222未动。完整strict checker/PASS报告/图未执行，P3B.5仍未完成，无ns-3/WiFi/RL。

2026-10-05 P3B.5 v59开发组件：充电/同伴返航取消探索动作后保存搜索意图；恢复只优先最新地图中距原前沿≤1.2m、gain>max(200,原20%)且完整往返预算factor≥1的当前候选，继续经过源TTL/动态身体/已接受路线/可见短腿/gateway。旧意图不是旧指令重放；已观测/阻塞/预算不足回退、成功前缀继续意图、抵达或明确FAILED清除。针对20项1.14s PASS后补明确失败清理检查，完整472项13.60s、四包build5.34s、source3r0旁路。原native_completion_ok/episode_ok与300s/.35/.05/.1/5未改。证据report/20261005_p3b5_interrupted_frontier_component.json；原v58六格FAIL已a6830cc归档，809/28091仍未运行。接续为待集成验证启发式，无因果/最坏时间保证；将先冻结独立lab101/forced303/zero303开发，全部自然关闭后才能修改或归档，再重新冻结正式57格。P3B.5尚未完成，无ns-3/RL。

2026-10-05 P3B.5 v59独立开发五格FAIL，冻结5dcb398e1dbe72f9c34c667f924b2306ff11ffed；2026-10-04 16:49–17:01:48UTC所有原owner/观察器自然结束。force ideal原生COMPLETE216.0s、检测132.8/RALLY148.0s、各机器人charge1/最低8.63273；zero ideal原生COMPLETE231.9s/总charge1。force fault EXPLORE timeout300.1s、各charge1/最低7.73411，安全检查通过但不是任务成功。lab3/101在91.5s发现/93.7s RALLY，300.4s仍tb3距最终位1.733m、总charge2/最低22.18681；zero fault300.4s RALLY timeout、tb1返航耗尽至0/FAILED，真实安全失败必须修复。五格0碰撞/0infra、五ledger TTL/versions与graph旁路PASS，无重试/回填/阈值放宽。接续日志存在但不能把不同async轨迹的时间差视为单因素收益。只读AP条件路线诊断提示驻点机体增加后继绕行，并发现local return无单腿进度取消监督；报告report/20261005_p3b5_interrupted_frontier_development.json完整保留。809/28091未执行，正式57格/PASS图文未启动，P3B.5仍未完成，无ns3/RL。
