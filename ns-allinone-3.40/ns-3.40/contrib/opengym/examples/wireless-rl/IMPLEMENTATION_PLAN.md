# 多机器人任务导向无线通信调度工程实施计划

最后更新：2026-10-08（历史段落保留原日期）。

本次[项目评审](report/20261008_project_review.md)已完成只读复核和审计修补：749功能检查/1 skip、四包build、150不可变任务/模型文件/54静态协议格通过；P3A.6十一、P3B.5六十三、P3C三、P3C.5十四原任务均重审通过，原结果未改。技术PASS不代表完整研究要求已满足：返航触发预算的欧氏距离启发式仍未关闭原路径预算要求；Wi-Fi容量尚未测量。用户于2026-10-08已验收P3C.5，并授权先完成独立P2C.1安全补强。下一步采用下述P4子门顺序，先做安全补强/重新冻结和包契约、被动无线测量，再做闭环、强基线及条件式学习；本轮未执行这些新阶段。

当前状态：用户已验收P3C/P3C.5；P2C.1完整路径能量预算和安全降级补强进行中。
bea7f8b冻结14原始格全部自然关闭：11原生COMPLETE/3 RALLY超时，零碰撞/耗尽/失效/infra/retry，forced217.5秒各机充电一次。
1272实时快照/2372766输入回放、2087分层/220552发送成本/29894突发记录、14时序/图/协议审计通过；723功能/四包build/68不可变源码/54静态格及实际ROS/Qt验证通过。
v1/v2技术失败候选与全部原任务失败保持；native300秒/TTL/5秒/任务/安全不变。当前应用模型没有容量机制，瓶颈不可由它识别；保持真实负载，不人为增流量或启动RL。
证据见[P3C.5最终报告](report/20261007_p3c5_gate.md)和[原前瞻协议](report/20261007_p3c5_protocol.md)。P4/ns-3/Wi-Fi/RL尚未开始。

本文把 `RESEARCH_PLAN.md` 的研究路线拆成可逐步实现、验证和验收的工程检查点。
研究边界、论文问题和最终指标仍以 `RESEARCH_PLAN.md` 为准；当前功能以源码和
`ros2_ws/ros2-multi-robot-automap/user_guide.md` 为准；实验事实以 `log.md` 和日期报告为准。

2026-10-07 P3C已验收证据：冻结6a0a8eb的ideal/forced/dynamic三原任务原生COMPLETE（197.1/235.0/265.6s），零碰撞/耗尽/失效/infra/retry，forced各机充电一次。658实时快照/26852 CSV行同源、63历史原任务/1879流/31冻结TDI回放、676组件/四包build/68任务安全源/54静态协议/实际ROS与Qt控台审核通过。源/显示修订和原失败分别保留，见[P3C最终报告](report/20261007_p3c_gate.md)。

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

2026-10-06最新状态：2026-10-06 P3B.5技术门禁PASS，待用户验收：v106原57格冻结d8d361bfd9d81e0c7a00c428ea66cfac4b3a1a76，2026-10-06 06:24–08:42:53UTC自然关闭；41主格/27pair+十fixed+六辅助，57时间与57图审核、54纯协议全部PASS，0接触/infra/操作失败、0整轮retry/backfill。十fixed原生COMPLETE；forced ideal155.2s各charge1。首次809/28091集合ideal/fault120.9/126.6s原生COMPLETE，目标两侧FOUND、覆盖率两侧达标，仅过程指标。真实tb3失败隔离0.1s，两健康机原生PARTIAL_COMPLETE148.9s/最低19.47128，success=false。TDI18eligible/5物理簇均值0.685185，95%描述性簇bootstrap[0.487179,0.823529]，10000次seed17011；rally fault5COMPLETE/20pair、1PARTIAL，其余真实失败/静默/超时保留，复用ideal不独立计样本。原checker摘要格式FAIL已5c1f931保留，77c201b仅修复只读摘要校验，636组件17.49s/九篡改反例PASS，原12审计函数AST和全部任务栈/原始记录未变；同57原数据重新严格审计PASS，无Gazebo重跑。lab101真实执行一次tb2驻点保留并原生完成，但无单因素收益或最坏保证；lab303294.8s仅5.2s余量。53参数旁录完整，E0双格和物理返充双格为独立原生证据。七port/所有owner/观察器/冻结source/helper/config及17用户资料SHA通过；JSON/MD/PNG视觉QA PASS。P3A.6已验收22c95a7历史冻结保留；809现已暴露，之后控制变化需新留出。报告report/20261006_p3b5_gate.json/.md与_results.png，技术完成待用户验收，未进入P3C/ns3/WiFi/RL。

2026-10-07逐条需求复核完成：原v106 57格严格checker PASS保留，独立上下行0.5/2秒延迟已按预冻结09f15df补齐四TASK case/六原始episode（同场景复用同配置ideal），共63原始/31pair；新增fault三COMPLETE、一300s timeout且0导航，六格0碰撞/耗尽/失效/infra/retry。两ideal176.8/150.2s，新fault252.9/181.4/timeout300/175.9s。原任务源码与d8d361b一致，原300s/.35/.05/.1/5s、TTL/安全门槛未改。新增4eligible/2簇TDI均值.25 CI[0,.5]；合计22eligible/5簇.606061 CI[.384615,.8]，固定矩阵描述性cluster bootstrap，不覆盖原失败理想配对。目标未发现坐标null的只读checker错误原trace/SHA保留，配置绑定改为CLI且不伪造观测，54相关检查PASS；参数0实际取4096队列，旧说明及冻结快照保留，当前仅更正说明文字。63ledger/graph核验、六实际sim-clock/SLAM2s旁录、owned两master/domain全部关闭、17用户资料SHA不变。逐条F/M/S/O/T证据与每格任务/方向类型账本、展开清单、TDI及原始增量在report/20261007_p3b5_requirement_audit.md/.json。P3B.5技术复核PASS待用户验收，尚未进入P3C/ns3/WiFi/RL；809已暴露，控制变化需新留出，原lab303仍仅5.2s余量。

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
| P2C | 电池、返航和充电 | 可校准能量、本地优先返航、独立充电目标、失败原因；原验收区域不重叠，当前区域几何另声明 | 至少一次被迫充电的 episode 中无耗尽，保留地图/任务并在充电后继续；不可返航和耗尽正确失败 | 已验收；P2C.1独立补强进行中 |
| P2C.1 | 评审后完整路径能量与安全补强 | 同源完整接触区路径、预算包络/失路停止、预测与实际账本、算法组件比较、新冻结任务栈 | 新源码完成组件和四包构建；同提交十理想原格及强制充电原生COMPLETE；实际断网独立返航、失路/耗尽反例、新未暴露拓扑/元组和全部失败留存；逐次预算/地图/实际成本可审计 | 进行中；尚非新任务验收 |
| P2D | 完整理想通信任务基线 | 统一 runner、完整状态/阶段指标、跨目标场景矩阵 | 至少 3 个预先验证的 world/目标/能量场景各跑 seeds 101/202/303，完成探索→发现→必要充电→集合；另做 2 机器人交叉检查 | 已验收 |
| P3A | 显式消息协议和零损 gateway | 本地候选队列、序号/时间戳/ACK/过期、接收信息存储、命令适配器、旁路清单 | 零损 finite-rate 语义、旁路审计和安全等价通过；不把完成时间当作 P2D 等价 | 已验收 |
| P3A.5 | 历史 task-stack 重验证（冻结候选） | 历史 commit 的 P2D/P3A 完整矩阵、强制充电回归、manifest、ROS graph edge 白名单 | 仅作为历史证据；不能替代当前 HEAD 的重新冻结 | 已验收 |
| P3A.6 | 当前 task-stack 重新冻结 | 当前 HEAD 的 P2D/P3A 完整矩阵、强制充电回归、commit/config/environment manifest、ROS graph edge 白名单 | 在网络/RL 前重新跑固定门禁并输出 `task_stack_frozen_commit`；后续任务栈改动必须另开批次 | 已验收（2026-10-01） |
| P3B | 固定 delay/loss 网络替身（已完成范围） | 独立上下行、固定 seed 队列、TTL/版本、重复/乱序、重传、逐消息账本和 stale-state 降级 | 4 项协议单测、54 格固定协议 matrix `PASS`；故障语义和安全降级可复现 | 已验收 |
| P3B.5 | 故障条件下的完整任务闭环 | Gazebo fault-mode 任务矩阵、理想配对基线、任务/电池/碰撞/安全降级指标、机器人本地 freshness 保障、队列语义收敛 | 覆盖 `coverage/target/rally`、多 world/seed、丢包/延迟/TTL/deadline/retry/overflow；每格保留 ledger 和任务结果；健康机器人继续，未交付信息不触发错误任务；输出故障退化报告 | 已验收：2026-10-07 |
| P3C | gateway 通信指标、实时可视化与在线故障控台 | 默认监控面板、独立故障配置入口、CSV/JSON 指标快照、ideal/fault 对比报告 | 消息与attempt字节闭合；显示吞吐/PDR/丢包/时延/队列/重试/AoI/任务；控台变更有实际生效仿真时刻及曲线反馈，监控只读，headless保存同数据 | 已验收：2026-10-07 |
| P3C.5 | 应用负载与协议控制开销审计 | candidate/request/grant/heartbeat/critical-event 的频率、字节、队列、AoI、deadline、控制开销与可观测性报告 | 在真实候选生成规则下测量负载，明确中央未知信息和审计边界；不得把仿真器隐藏队列作为输入 | 已验收：2026-10-08，原14格保留 |
| P4A | ns-3 数据包与时间同步 | P4A-0不可变消息/分片契约；P4A-1因果clock桥接、mobility与资源记录 | 固定输入+RNG streams/seed的网络ledger一致；消息/逐包字节闭合；关闭返航缺口并重新冻结后才做闭环，异步任务重复性另报告变异 | 待完成；A-0可先行，A-1有安全前置条件 |
| P4B | Wi-Fi 4测量与标定 | P4B-0原负载/位姿trace网络试验及早期实测；P4B-1闭环标定/独立验证 | 含控制/重试的真实网络总成本、排队/过期/竞争可对账；B-0先于A-1；无实测只称synthetic sensitivity，不宣称sim-to-real | 待完成 |
| P5 | 强非学习通信调度基线与 RL go/no-go | 冻结场景/seed/主指标/最小动作集及 no/ideal/always/periodic/random/event、task-value greedy、freshness/deadline、link-aware、SchedNet-inspired | 同一 gateway 和配对 seed 一键运行，CSV 含所有任务失败和基础设施失败；完成负载/瓶颈审计后记录是否进入 RL | 待完成 |
| P6 | 条件式集中式 POMDP 学习调度（RL） | 可部署观测、candidate/request/grant 准入动作、硬安全覆盖、checkpoint | 仅在 P5 go 条件满足后训练；validation 选模并完成 held-out 比较；不以胜过 baseline 为工程条件 | 待完成 |
| P7 | 泛化、消融和统计（有/无RL均执行） | 场景拆分、至少20个配对held-out元组（每主要world≥6，推荐24）、非劣界与precision、簇/重复设计 | 先过完整成功率/失败惩罚时间/安全约束，再比较预注册的一个总网络成本；包含控制和重试；早期FAILED不按独立右删失；精度不足增样或报告不确定 | 待完成 |
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

下列0.25m/10s及190.1s结果为2026-09-17初始P2C实现/验收配置，不是当前默认值。当前默认半径0.8m、充电6s、目标电量80%；独立姿态不保证区域不重叠，也不证明机械对接/共享充电排队。当前路径预算缺口见研究总纲§7与本次评审。

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

### P3B.5：故障任务闭环与保障性降级（2026-10-07已验收）

2026-10-07已验收原57格与新增独立方向延迟六原任务。完成范围见[完成情况](report/20261007_p3b5_completion_status.md)与[逐条需求审计](report/20261007_p3b5_requirement_audit.md)。2026-10-08重审仍支持故障/源时效/局部优先级和记录完整性；原研究总纲§7的地图路径能量要求另发现尚未关闭，不能把本矩阵的局部安全证据推广为一般返航保证。下列契约和历史结果保留，后续安全修复使用新冻结。

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

P3C 在已验收的 P3B.5 任务矩阵之上建立通信可观测性层，让 gateway 不再是黑盒。2026-10-07用户新增实时通信控台：通过独立配置服务在线设置应用层故障并记录生效时刻，既有任务算法、消息TTL、导航deadline及本地安全规则不改。监控节点只读，不把可视化节点放进任务控制闭环。默认 GUI 运行时打开监控面板；headless
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

### P3C.5：应用负载与协议控制开销审计（技术PASS，待用户验收）

在训练前，用冻结的任务栈和真实候选生成规则测量每类消息的生成频率、payload 字节、
candidate/request/grant/heartbeat/critical-event 控制字节、队列深度、AoI、TTL/deadline、
重试和等待时间。审计必须覆盖上行和下行，并把控制消息本身计入 payload、airtime 和能耗
账本。中央只能使用已经交付的摘要、请求、心跳和历史反馈；机器人隐藏队列不能作为免费观测。

退出条件：给出按任务阶段、消息类型、方向和机器人分层的负载分布，明确实际应用负载是否可能
造成排队/过期/竞争；若负载不足，记录“通信不是瓶颈”，不得先改规则或人为增加拥塞。

2026-10-07完整14格通过应用/协议/观测审计，11原生COMPLETE/3超时全部保留；
阶段/类型/方向/机器人分层、控制与关键/ACK成本、授权等待/源龄/AoI/队列/原TTL/有限重试、实时回放见[报告](report/20261007_p3c5_gate.md)。
现阶段没有PHY/MAC/速率/射频功率模型，实际airtime/J为null、逐attempt保留条件系数，不能伪造实测值。
容量在该模型中不可识别；保留负载和注入delay/loss敏感性，不把“没有容量机制”称为测得无瓶颈的负结果。无线负结果只能来自后续P4B测量。

### P4–P7：网络、策略和统计（待完成）

2026-10-08起按以下依赖推进。保留原P4A/P4B编号，用子门明确先后；每门仍独立验收，不把表中待完成内容当已有功能。

| 子门/工作 | 必须交付与退出条件 | 依赖与限制 |
|---|---|---|
| 返航安全补强与任务重新冻结 | 本地完整已知地图→有效充电接触区路径预算；中央去程/返航预算；无路有界停止/失败；记录预算与实际消耗/预测误差；新提交完整理想十格、forced、实际断网返航、不可达/耗尽反例 | P4A-1/P5闭环前必须关闭；旧300s/.35/.05/.1/5s不变；新未暴露组合，不能回填旧失败 |
| P4A-0 消息/包契约 | 固定wire schema和immutable payload/hash，logical message/fragment身份；MTU/重组/丢片/重复/过期；逐层字节守恒；固定输入+显式RNG streams/seed重放ledger完全一致 | P3C.5验收后可做；原metadata ledger不够恢复payload；接收不能读取原ROS最新对象 |
| P4B-0 先行负载/容量测量 | 原负载及2/3机器人位姿trace、AP/STA 802.11n、参数来源；全网TX时间/观察点busy、MAC队列/重传/过期和总成本；早期普通Wi-Fi链路实测/合成标签 | A-0之后、A-1之前；被动trace不证明任务收益；背景流须有实测/应用依据 |
| P4A-1 因果闭环 | 冻结一种message/clock ACK、退出、背压协议；窗Δ/量化误差与敏感性；位置→mobility与消息重组→ROS交付；源TTL不刷新；桥接断开停止推进/明确失败；wall/sim/RTF/CPU/RAM | 安全冻结与A-0/B-0后；ROS/system Python、ns3gym/conda独立进程；固定输入网络确定性与异步任务变异分开验收 |
| P4B-1 标定与闭环验证 | 部分位置/干扰拟合、独立位置/条件验证；分布误差和任务差异分别报告；网络/任务因果链及无干扰/合理干扰对账 | A-1之后；未校准只支持合成敏感性，不作sim-to-real结论 |
| P5 准入决策与强基线 | 固定主成本、成功/时间非劣界及安全条件；有实际消息且在deadline前可执行的动作；task-value、freshness/deadline、link-aware等；部署观测与真实控制成本 | 不同策略共享协议/生成规则，实际消息序列允许闭环变化；控制成本不能免费 |
| P6 条件式学习 | 可部署历史观测、validation-only选模与预算，强方法同条件比较 | 只有P5发现可测长期取舍且强启发式存在可解释限制时GO；训练并不保证研究优势 |
| P7/P8 完整验证 | 分层未见元组、策略顺序平衡、按簇配对区间；两机器人真实检测/无线/返航/集合 | 无RL分支同样执行；实物网络标定部分已从B-0提前，不代表P8任务已完成 |

首选复用现有UDP/ZMQ依赖，协议选择以可验证因果推进为准。wall-clock联调仅作演示；不同Δ、异步到达和进程负载不能隐藏为网络时延。先做单次与固定输入重放性能测量再确定训练预算。PHY选择以本地ns-3 3.40文档为准，不为测Wi-Fi-only场景引入不需要的频谱模型或环境升级。

P5 在任何训练前冻结场景、训练/validation/test 划分、四类独立 seed、episode horizon、
主指标和基于真实候选队列的最小动作集。先运行task-value greedy、freshness/deadline、link-aware等非学习强基线；SchedNet-inspired必须声明是启发式适配还是学习式评分，后者遵守学习准入和同样的选模/测试链路，不能标作非学习或原论文复现。所有方法固定消息语义/生成规则、任务栈和控制协议参数，真实控制包成本按策略计费。
动作同时考虑机器人上行与必要的中央下行；2/3 机器人按同一生成规则使用各自固定维度 checkpoint，
不提前实现可变规模策略。所有 baseline 包括 ideal 都使用相同 gateway；正式启动前失败单独记为
`infrastructure_failure` 并保留，`episode_start` 后的任何故障都算任务失败，不得挑选补跑。
只有B-0/B-1实际测量后才能记录“在已测条件中未出现网络瓶颈”。如任务不敏感但可省总成本，优先非学习节流；如果成本也无有意义改善，保留网络/协议负结果，不能虚构拥塞或硬设无物理依据的预算制造RL空间。

P5 还要冻结一个 `task_stack_frozen_commit`：它必须在当前 HEAD 上重跑通过 P2D/P3A 的完整门禁；
之后的探索、充电或导航优化另开 exploratory 批次，未经整套任务门禁不得替换网络/RL 基线。
P1/P2/P3 的 101/202/303 只作开发和集成 seed；正式 train/validation/held-out manifest 按
world、目标、能量和干扰分层，且不得与这些 seed 重叠。正式 runner 必须保留 pre-start
`infrastructure_failure`、post-start task failure，并写入 commit/config/environment manifest。

P6 只有在 P3C.5/P4B 证明存在可测的长期通信决策空间后才启动，默认采用集中式、部分可观测
单智能体准入调度；不因机器人数量而改成 MARL。工程退出条件是可部署观测、validation-only
选模、held-out 评估和硬安全覆盖正确。是否优于最强 heuristic 是研究结果而不是工程门槛；
RL没有优势时保留负结果。P7对有/无RL两分支都实施：至少20个独立场景/seed配对held-out元组只是覆盖下限，样本量按预先冻结的非劣界/精度计算。重复嵌套在元组内，共用ideal不能伪装独立，策略顺序预先随机/平衡。先报告success和安全区间，再报告失败取H的惩罚完成时间、含控制/重传的总成本配对区间；早期任务FAILED不当独立右删失，成本只统计真实暴露时间且不能凭快速失败节流获胜。只有预注册主结论获得区间支持时才声称优势。

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

2026-10-05 P3B.5 v60组件：ACTIVE且无需预充电的真实观测者驻点选择，把待充电同伴home路线的驻点机体绕行加入名义时间评分；按observer候选/home缓存masked距离场，缺路线保留有限30s恢复代价而非假不可行，部分界仍乐观。本地返充独立监督已接受Nav2单腿：0.1m单调进展、20s无进展或max(30s,2*已知自由腿长/名义速+10s)超时仅请求一次取消，保留handle至result后重新规划，CHARGING/FAILED/terminal不干预；原总返航时限/储备/稳定充电未改。原300s/.35/.05/.1/5s与native completion函数原样，487组件13.72s、四包build5.38s、source3r0旁路。首return夹具漏callback1fail39pass、修正后321PASS；首parking夹具强求特定侧点1fail1pass，实际另一个funded非阻塞点更优，修正为验证入口不被堵与两条masked路线，全部487PASS；失败日志保留。独立AP条件重算选侧方点并消除预测绕行，0.81454s只是单次组件样本，无任务/因果/最坏保证。报告report/20261005_p3b5_observer_parking_return_progress_component.json。v59五格两失败已02c8d86完整归档，809/28091仍未执行；新独立开发和正式57格尚待验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v60独立开发五格FAIL，冻结79a3b05b5101418cd99dd8cb7cd6d4630c0eb823；2026-10-04 17:39:47–17:52:26UTC三个owner全部exit0、原观察器自然关闭。lab3/101原生COMPLETE198.5s/charge0/最低23.35519；force ideal原生COMPLETE214.8s/各charge1/最低8.91814，force fault300.1s RALLY timeout/各charge1/最低8.03192，安全子门通过但非任务成功。zero ideal283.8s检测/291.2s RALLY、300.0s timeout/各charge1/最低4.03001；zero fault原生COMPLETE271.6s/总charge1/最低21.73648。五格0碰撞/0耗尽/0failed/0infra、五ledger TTL/version与graph旁路PASS；原生阈值未改，无重试/回填。前沿接续/驻点绕行成本/返航watchdog尚不能解决晚发现；只读日志证实远端不够完整任务预算的探索fallback与返航先于迟到的西北发现，watchdog有一次真实取消，但不作单因素因果或最坏时保证。完整报告report/20261005_p3b5_parking_return_development.json/.md。809/28091从未执行，正式57格/PASS图文未启动，P3B.5仍未完成，无ns3/RL。

2026-10-05 P3B.5 v61组件：中央探索只准入当前可负担的完整前沿任务；未负担的前沿仍经当前地图/机体/可见短腿检查作为充电候选，不再执行已预计会被本地储备中断的远端fallback。所有已接收探索动作结束、无RETURNING/CHARGING后，只通过原gateway charge_request串行请求一个idle机器人提前充电，优先近home并保留当前前沿意图；充电后重新生成/核验。预算不小于充电目标或无效context不重复充电，现有rally pending owner覆盖阶段切换，2s重发；原10s请求租约保持，只在更新ACTIVE source超过租约后释放丢失请求，发现目标进入RALLY也适用。本地接受EXPLORE/FOUND_UNCONFIRMED/FOUND/RALLY有效幂等请求，拒绝未来/过期/terminal。增加charge决策输入租约与消费因果审核。516组件14.76s、四包build5.28s、source3r0旁路；native300s/.35/.05/.1/5s函数AST与d3acb28一致。首夹具5fail61pass：4漏导入、1误写5s而原租约10s；修正108PASS；跨阶段修复前515PASS日志保留。case template首命令漏--run-id仅参数解析失败，修正只读validate-only；不是任务启动/重试。组件报告report/20261005_p3b5_exploration_charge_admission_component.json。v60五格失败已d3acb28归档；809/28091未暴露，其旧cf73 controller声明待开发通过后前瞻重新冻结；新开发/正式57格仍未验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v61独立开发五格FAIL，冻结cf829cf23ae56adb65ca9a54b13b34132cddbd09；2026-10-04 18:18:54–18:31:08UTC所有原owner/观察器自然关闭，lab exit1、force/zero pool exit0。force ideal原生COMPLETE209.8s/各charge1/最低8.79340，zero fault原生COMPLETE160.8s/charge0/最低23.15425。lab3/101检测126.3/RALLY128.4、300.3s timeout/charge1/最低13.98203，tb1/tb2尚RETURNING；zero ideal检测133.7/RALLY143.7、300.0s timeout/各charge1/最低14.29596。force fault300.4s EXPLORE timeout、tb1 charge1/tb2 charge0且末端仅CHARGING3.5s/最低7.38321，未满足各机器人充电安全子门。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge消费与决策租约PASS、五graph0旁路，无整轮重试/回填。提前探索充电真实执行，但只在所有可负担任务耗尽才考虑充电，会让已充电同伴连续获任务而饿死idle充电候选；当前驻点成本只计真实observer，其他funded驻点也可能挡charged peer；RALLY名义预算仍无最坏时间保证。报告report/20261005_p3b5_frontier_charge_admission_development.json/.md保留全部原始命令/日志/取证，时间差不作单因素收益。809/28091从未执行，正式57格/PASS图文未启动，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v62组件：当前2/3机前沿调度对无可负担替代、充电后可执行的idle同伴建立公平充电窗口；不再要求所有机器人耗尽funded工作才充电。停止新增探索腿但不取消原已接受动作，原动作自然结束后经同gateway串行请求返充，CHARGING期间有待充电同伴则暂缓新探索；同机器人有当前funded替代仍正常准入，无效/超容量预算不关闭其他funded准入。当前批次每机器人只保留最高效用的可行充电意图，跳过重复较低效用unfunded路线，但所有funded候选仍检查；20候选夹具路线调用≤2。集合叶评分对每个ACTIVE且无需预充电的驻点body累加charged peers home路线的单体绕行代价，而非只计observer；按body候选/home源缓存，非负部分界仍乐观，缺masked路线沿用有限30s恢复代价。它是加性静态启发式，不证明联合body路线可行，实际派发仍检查全部body/在途/返航/输入租约/能量。窄入口原parent分配nonobserver堵住第三机路径，新分配侧移后联合body路线4.0m；单组件0.02647/0.03615s不是任务/最坏收益。304定向11.48s、全部521组件14.11s、四包build5.36s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。v61五格3FAIL已c3319f0归档；报告report/20261005_p3b5_charging_fairness_parked_peers_component.json。新独立开发及正式57格仍待验证，809/28091未暴露，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v62独立开发五格FAIL，冻结d2a9b47b4deb5b19294d529a5a3209ceddef9d93；2026-10-04 18:56:08–19:09:44UTC三个owner全部exit0、原观察器自然关闭。lab3/101原生COMPLETE184.7s/charge1/最低25.69497，zero ideal原生COMPLETE163.0s/charge0/最低20.02148，force fault原生COMPLETE294.2s/各charge1/最低8.90970。force ideal284.6s才检测、285.8s RALLY、300.3s timeout/各charge1/最低7.52388；zero fault261.6s才检测、269.4s RALLY、300.1s timeout/各charge1/最低15.33104。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge消费与决策租约PASS、五graph0旁路，无整轮重试/回填。公平充电与全驻点成本仍未解决长探索与远端返充；原生300s/.35/.05/.1/5s标准未改，时间差不作单因素收益。报告report/20261005_p3b5_charging_fairness_development.json/.md保留全部原命令/日志/取证，包括v61关闭后LOS/FOV只读诊断及首次函数名错误；真值不作控制输入。809/28091从未执行，正式57格/PASS图文未启动，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v63组件：探索成功计数仅在真实成功的EXPLORE/FOUND_UNCONFIRMED前沿腿递增；已完成至少一腿、能量≤充电目标50%、离home>.35m且≤2×交付charge_radius的idle机器人，当前前沿准入且当前地图/所有同伴body允许已知自由可见航段真正到达home目标格时，可以优先通过原gateway补能。请求预算max(完整前沿预算,充电目标50%)，低于充电目标；不在初始出生位直接补满，不绕过本地储备或原10s租约。先让既有动作自然结束，串行返充并保留意图，充电后重新生成当前前沿；已满/远端/无成功腿/过期输入/阻塞home不触发机会补能。修复有active同伴但无selected时提前结束粗候选循环：仍执行当前body约束下的可达组件细化，空闲同伴可获得合法替代。531全组件14.40s、四包build5.78s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。首定向13fail319pass：home栅格中心被错误使用.02m比较而拒绝，及旧无电池夹具缺enable字段；改用同目标格判断/缺字段默认禁用后全531PASS，首次日志保留。机会阈值/返充/路径时间仍为启发式，无任务时限或收益证明。v62五格2FAIL已83cb590归档；报告report/20261005_p3b5_opportunity_charging_refinement_component.json。809/28091从未执行，新独立开发/正式57格待验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v63独立开发五格FAIL，冻结a113550bec575cee8b386befec53f5130c18e482；2026-10-04 19:19:40–19:32:40UTC所有原owner/观察器自然关闭，lab exit1、force/zero exit0。force ideal原生COMPLETE260.3s/各charge1/最低12.17092；zero ideal/fault原生COMPLETE257.6/218.8s/各总charge2/最低13.66549、38.13748。lab3/101检测271.9/RALLY273.8、300.2s timeout/总charge3/最低17.00048；force fault300.0s RALLY timeout/各charge1/最低13.22627，通过充电安全子门但非任务成功。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge与决策租约PASS、五graph0旁路，无整轮重试/回填。本批AP每10s覆盖探索及发现/集合，地图重复数组以cell_count/SHA记录，原字节hash保留。近home50%机会策略未解决普通E40组晚发现；部分contact航段已进入充电区但被必须同home格条件拒绝，本地返充发送端把规划staged.yaw覆盖为零，需要修复，但不宣称已证明任务耗时根因。报告report/20261005_p3b5_opportunity_charging_development.json/.md完整保留五格及只读AP前缀诊断。809/28091从未执行，正式57格/PASS图文未启动，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v64组件：本地RETURNING发送端保留已知自由规划staged.yaw，不再把每个中间腿朝向强写为零；最终home格仍按原planner零朝向，逃离fallback保持原行为，位置/路线/储备/返航时限/watchdog及充电稳定门不变。机会补能阈值从充电目标50%收紧到25%，请求预算max(完整前沿预算,充电目标25%)；普通E40富余阶段不因出生邻近再次充电，已真实成功探索、>.35m且≤2×charge_radius、当前数据新鲜、经同gateway串行请求等条件保持。可见已知自由home航段到达charge_radius−.2m接触区即可，而非必须与home同格，仍保留目标误差余量/peer body检查。537全组件14.86s、四包build5.48s、source3r0旁路，native300s/.35/.05/.1/5s函数AST不变。新增普通能量不机会返充、可见接触区/边缘拒绝、0/正负pi/2执行朝向检查；本版首次全组件PASS。阈值、返航/行程仍为启发式，源码朝向错配已确认，但不宣称已证明任务耗时根因或收益。v63五格1必需FAIL已5041fc8归档；报告report/20261005_p3b5_charging_contact_heading_component.json。809/28091从未执行，新独立开发/正式57格待验证，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v65独立开发五格PASS，冻结a49924abd43ff4406a982d73415b2ac304444cea；所有原owner/观察器自然关闭后审核并归档。p3b5_v65_dev_fixed_lab101_lab_far_northwest_3r_seed101 COMPLETE/249.7s/charge1/minimum23.35615；p3b5_v65_dev_forced_ideal_forced2_rally_86fbb43bc6 COMPLETE/226.4s/charge2/minimum16.37324；p3b5_v65_dev_forced_forced_charge_outage_fault RALLY/300.3s/charge2/minimum9.07872；p3b5_v65_dev_zero_ideal_lab2_rally_8d4d5c469d COMPLETE/145.1s/charge0/minimum20.71604；p3b5_v65_dev_zero_zero_rally_lab_fault COMPLETE/143.6s/charge0/minimum26.94027。五格0碰撞/0耗尽/0failed/0infra、五ledger因果/TTL/version/charge与决策租约PASS、五graph0旁路，强制fault按既定子门只计各机充电/正能量/无碰撞安全，超时不计任务成功；无整轮重试/回填。25%近home接触区机会补能与规划返充朝向在实际执行，但无单因素任务消融，不作因果加速或最坏时限保证。报告report/20261005_p3b5_contact_heading_development.json/.md保留五格原结果/精确命令/源与环境/hash/AP/账本/图审核。809/28091从未执行；开发PASS不代替正式57格，P3B.5仍待完整冻结门禁，无ns3/RL。

2026-10-05 P3B.5 v66前瞻正式冻结准备：已关闭并完整保留v65五个独立开发原始结果且开发PASS；保持809.world/seed809/fault28091/目标(4.4,-3.4)/3r/E45原字节与最初静态声明，更新当前control与battery源hash及未暴露失败历史。809此前从未任务执行；同提交强制原生/E0/受控物理返充及十fixed全部PASS后才允许首次运行。57格/27pair/41主格、300s/.35/.05/.1/5s、原故障强度保持，不重试/回填。当前仍待正式完整门禁，无ns3/RL。

2026-10-05 P3B.5 v66正式原候选FAIL，冻结61de29f69d3d8e92f83fa21dc2b202cef032f662；2026-10-04 19:55:11–20:06:46UTC所有owned owner/观察器自然关闭，initial exit[0,0,1,0]。5started/5raw、52unrun含全部固定与809；无整轮重试/选择回填。force ideal原生COMPLETE185.4s/各charge1/最低15.71204；force fault300.2s RALLY timeout/各charge1/最低14.00499通过安全子门但非任务成功。E0双格预声明FAILED1.5/.5s，无导航；受控返充ideal准备50s只完成tb2，staging exit1、300.3s RALLY timeout/各charge1/最低9.46559，断网配对未启动。五格0接触/0infra，但1操作准备失败；五ledger因果/TTL/version/charge与决策租约PASS、五graph0旁路、54纯协议PASS。原始AP地图起点known-free却处于净空膨胀区，共享规划可向后脱离，fixture的欧氏目标单调前进条件拒绝该安全逃离；自回波helper没有清任何格且不恢复路径，不能通过清障碍修复。只读条件回放不证明任务因果。809/28091从未执行，707已暴露历史不变。完整strict checker/PASS图文未执行，P3B.5未完成，无ns3/RL。报告report/20261005_p3b5_staging_geometry_failed_candidate.json/.md保留五原始与52unrun、源码/环境/命令/hash/图/账本/地图及失败诊断；domain222未动。

2026-10-05 P3B.5 v67准备程序修复与前瞻协议：受控返充fixture在known-free但净空膨胀起点复用现有navigation_start_route的.6m有界自由逃离；允许先增加距最终point的欧氏距离，之后通过当前地图共享plan_rally_leg已知自由visible路径绕行。不清障碍/未知格、不引入native truth，原始地图保持；四源TTL/current battery ACTIVE/gateway串行既有行为保持。最终点/50s/.75m/.35m/blackout60–250/1.1m远端/.5m实际Nav2返航/300s及原生保持门槛不变，native_completion_ok/episode_ok AST不变。61相关检查1.83s、539全组件14.80s、四包build5.30s/source3r0旁路、54配置检查及27cases/41primary validate-only PASS。控制器/电池算法源与v65开发PASS/v66force185.4原生PASS相同；v66五原始1操作FAIL及52unrun已c9719c5归档。809.world/seed809/fault28091此前从未执行，保留原字节/最初声明及全部未暴露历史，新增fixture源hash和当前准备协议。新冻结完整57格需initial强制原生/E0/受控实际返充及十fixed全PASS后首次809；本组件不是正式P3B.5通过，无ns3/RL。

2026-10-05 P3B.5 v67原候选FAIL，冻结a7952b59ae9df722eabf3beddc5c159bf4e9a01c；2026-10-04 20:23:16–20:51:34UTC全部owned任务/观察器自然关闭，initial全0、lab101 exit0、lab202任务exit1。8started/8raw、49unrun含剩余8fixed与809，无重试/回填。强制ideal原生COMPLETE211.2s/各charge1/最低16.75387，强制fault300.1s RALLY timeout/各charge1/最低8.48774安全PASS；E0双格预声明FAILED2.0/1.1s且无导航。受控准备两侧均50s内双机到位，两侧各charge1/0接触/最低9.67712、9.59143，断网62–248实际返航path1.22875/1.14257、net1.22331/1.13431、NavEXEC1.22872/1.14254m，严格安全审计PASS；原timeout不计任务成功。首fixed lab101原生243.1s/charge1/最低23.62608；lab202 RALLY timeout300.4s/charge2/最低20.78276，tb1距最终1.41806m、其余两机已到位。八格0接触/0infra/0操作失败，八ledger及八graph PASS、54纯协议PASS。保存AP地图条件回放提示完整高优先未来路线预约拒绝了部分实际body可行短腿；充电preflight需要完全动作排空才能重排，但持续新腿可能使其迟迟不能完成。只读条件几何不是原buffer或任务收益因果证明，待开发修复。809/28091仍从未执行，完整strict PASS报告/图未生成，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v68组件：实际发出集合预充电请求即使preflight失效；充电完成后停止接纳新集合腿，已接纳/待接受腿自然排空，再按当前地图与机体重算串行接近次序，原有本地安全/让行继续运行。完整串行机体避障可行排列优先减少后车未来路线覆盖前车当前位置、但反向不覆盖的单向接近逆序；只有未来优先级阻塞、实际已接纳/返航路线允许，且重新计算得到更少逆序时才排空重算，不在动作执行中换序。1.8m路线保留、.6m机体/.35m静态净空、源TTL/能量/300s/.35/.05/.1/5s原生完成门不变，native函数AST一致。542组件14.94s、四包build5.07s、source3r0旁路通过。历史中间单测1次作用域NameError、2项fixture恰到5s电池TTL而失败均保留，修复测试本身后284控制检查11.89s通过。v67 lab202接收AP快照回放中三种次序评分仍选tb3/tb2/tb1，32个已评估完整分配叶仍选入口观察驻点；不是原FOUND缓冲或反事实任务，不宣称该修正已经解决lab202超时或证明耗时收益。v67八原始FAIL与49unrun已f4dc4bb归档。报告report/20261005_p3b5_postcharge_order_component.json。新独立lab202/lab101及force/zero开发回归待执行；809/28091从未执行，正式57格尚未完成，无ns3/RL。

2026-10-05 P3B.5 v69独立六格开发PASS，冻结9ac2fb7dc10193c93092efdcf17f198fcb7554a8；所有原owner/观察器自然关闭后审核归档。p3b5_v69_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/197.9s/charge1/min23.28236；p3b5_v69_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/160.4s/charge0/min27.08704；p3b5_v69_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/178.4s/charge2/min14.77575；p3b5_v69_dev_forced_forced_charge_outage_fault PASS/RALLY/300.2s/charge2/min12.72806；p3b5_v69_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/202.2s/charge1/min20.56833；p3b5_v69_dev_zero_zero_rally_lab_fault PASS/COMPLETE/201.3s/charge1/min22.96403。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_postcharge_order_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。充电后排空/重算只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v67不同，无单因素消融，不把较早发现或较短完成时间归因于次序修正，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v70正式协议前瞻重冻：v69六原始开发PASS后，将controller源SHA冻结为aa6cd7c03016e38ae7f5eec808b226b5fdb67f206a1038f7e61d27c4a06cb9d2，809.world/seed809/fault28091仍从未执行；原world/目标/3r/E45/300s/独立fault seed/电池/准备装置/原生完成阈值不变。追加v67冻结a7952b5八started/49unrun/原lab202 RALLY timeout失败与未暴露历史，不替换结果。54配置检查0.64s、54协议元数据矩阵、27case/41primary validate-only PASS；控制组件542/四包5.07s/旁路及六开发ledger/graph已有证据。新clean pushed同提交正式57格先initial强制原生ideal/E0/受控实际返充与十fixed PASS，再首次809及其余primary/safety。各独立world可在不同master/ROS domain/CPU组同时运行，全部原owner/观察器关闭后才审核/修改；不增加整轮重试或降低门槛。本协议及开发PASS不是P3B.5验收通过，完整正式门禁待执行，无ns3/RL。

2026-10-05 P3B.5 v70原候选FAIL，冻结4653c13e6de18b8ad8ade2bc4c734ab76005c9b2；全部owned任务与观察器自然关闭后归档。6started/6raw、51unrun含十fixed/809；p3b5_v70_zero_ideal_lab2_rally_0678e85373 FAILED/1.7s/charge0/min0.00000；p3b5_v70_zero_battery_exhaust_lab_fault FAILED/1.3s/charge0/min0.00000；p3b5_v70_forced_ideal_forced2_rally_86fbb43bc6 COMPLETE/235.2s/charge2/min16.20114；p3b5_v70_forced_forced_charge_outage_fault COMPLETE/300.1s/charge2/min9.92663；p3b5_v70_returnproof_ideal_forced2_rally_4c7c808f36 RALLY/300.1s/charge2/min9.60870；p3b5_v70_returnproof_physical_return_under_blackout_fault EXPLORE/300.1s/charge2/min9.54496。E0 ideal已FAILED1.7s/双机无Nav且中央失败名单完整，但原生评估tb1 battery_message_count0、mode/initial_energy为null，严格E0前置断言拒绝；fault FAILED1.3s双机原生字段完整。独立只读安全观察器收到tb2/tb1 FAILED原生消息于2072.082/2072.282；task evaluator在FAILED后的固定0.5s drain先写终态，快终止可能早于另一路原生电池回调。缺失证据保留为空，不从配置/网关推断0或FAILED、不放宽断言；需有界终态收集回归。无整轮重试/回填，六ledger/graph已审核；报告report/20261005_p3b5_failure_battery_snapshot_failed_candidate.json/.md。809/28091仍从未执行，完整P3B.5未通过，无ns3/RL。

2026-10-05 P3B.5 v71只读评估组件及v72前瞻协议：FAILED仍至少排空0.5秒；未收到每台原生电池状态、或已声明失败者原生mode尚非FAILED时，最多按现有battery TTL5秒收集，且不越过原任务300秒时限。重复FAILED不重置首次等待起点；到界仍保留缺失null，不从配置/AP/native安全旁录推断字段。已完整的失败证据仍按原0.5秒结束；FAILED期间不回落到coverage完成。该过程只采集证据，任务控制/本地安全已经失败或停止，不发布导航。34评估检查2.11s、546全组件15.18s、四包5.20s/source3r0旁路通过；新增迟到/永久缺失/非FAILED旧状态/重复FAILED/任务时限回归。原生保持函数和严格native_completion_ok/episode_ok源码一致。controller/battery/apparatus与v69六开发PASS字节相同；v70六原始失败/51unrun已afefd96归档，实际返航子门PASS，未回填。54配置及27case/41primary validate-only PASS；未暴露809 world/seed/fault保持字节及条件，新增evaluator源hash和v70未暴露失败历史。报告report/20261005_p3b5_failure_evidence_component.json。新clean pushed正式57格先initial强制原生/E0/实际返航及十fixed全PASS，再首次809。完整P3B.5尚未通过，无ns3/RL。

2026-10-05 P3B.5 v72原候选FAIL，冻结a9745c393194aa941e289d812a57b2c890918380；全部owned任务/观察器/master自然关闭后归档。15started/15raw、42unrun（lab303及全部其余primary/safety，含809），不重试/回填。initial强制ideal原生217.9s/两机各charge1、E0双格原生FAILED证据完整且无Nav、受控实际断网返航子门与54协议PASS。九个已启动fixed中八个原生合格COMPLETE；lab101293.7s仅6.3s余量，lab202 RALLY timeout300.1s/2charges/最低20.22274，tb1仍距最终1.30480m、tb2/tb3已到位。其余world池自然执行原声明格后才结束，不因lab失败取消。十五格0接触/0infra/0操作失败，十五ledger/graph审计PASS。只读AP条件profile集合排序重复16–17个距离场、约1.14–1.26s；不是原控制执行器耗时或任务因果证明。中间路点仍朝最终目标，绕墙时可能增加转向，需独立优化验证。helper端口生成range(16950,16854)为空，错误ports[] preflight与原源保留；bootstrap任务首次前实际声明16650..53，独立fixed world声明16950..52，实际七port/PID/env关闭另显式审计PASS，未影响同提交源或重跑任务。报告report/20261005_p3b5_postcharge_lab202_failed_candidate.json/.md。809/28091仍从未执行，完整strict PASS报告/图未生成，P3B.5尚未通过，无ns3/RL。

2026-10-05 P3B.5 v73集合路径组件：串行排列评分仅在同一次不可变地图规划、同一机器人起点和完全相同机体障碍坐标配置内复用距离场；不同排列机体位置独立key，函数返回即丢弃，回退复用同一未屏蔽intent，不跨地图/位姿/TTL缓存。中间已验证路点与预约截断停点按实际入站路径末端0.3m弦朝向，减少绕墙时朝最终目标的额外转向；最终集合pose仍保留原请求yaw，交付目标可见朝向修正与实际body/live/return/源TTL/能量准入均保持。288控制14.41s、550全组件15.95s、四包build5.18s/source3r0旁路通过；新增绕墙朝向/最终yaw、预约截断与障碍配置/地图缓存隔离回归。首新增夹具两项假设错误（整段直线与栅格末段方向差0.061rad；预约障碍未在预期点触发）已按实际几何修正，原失败日志保留，未改生产门限。五个保存AP快照新旧源码排序、路线及坐标相同；缓存条件对照构建16–17→11–12个距离场，离线中位耗时约1.10–1.22→.75–.86s，实际新旧源码再次对照约.51–1.11→.31–.84s，受同时任务负载变化影响，非原控制执行器计时或任务因果收益。原生保持与严格native_completion_ok/episode_ok源码一致，300s/.35m/.05mps/.1radps/5s及原TTL/净空不变。v72十五原始失败/42unrun已f62262f归档，未回填；809/28091仍从未执行。报告report/20261005_p3b5_incoming_heading_cache_component.json。需要新冻结独立开发回归与完整正式57格，P3B.5尚未通过，无ns3/RL。

2026-10-05 P3B.5 v74独立六格开发FAIL，冻结b5f6be544bab0cca7b7022648b8a4a6ff1f53671；所有原owner/观察器自然关闭后审核归档。p3b5_v74_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/233.1s/charge2/min26.14744；p3b5_v74_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/195.0s/charge1/min20.71743；p3b5_v74_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/269.7s/charge2/min8.54416；p3b5_v74_dev_forced_forced_charge_outage_fault PASS/EXPLORE/300.2s/charge2/min12.38229；p3b5_v74_dev_zero_ideal_lab2_rally_8d4d5c469d FAIL/RALLY/300.1s/charge2/min15.46393；p3b5_v74_dev_zero_zero_rally_lab_fault PASS/COMPLETE/189.9s/charge0/min19.26797。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_incoming_heading_cache_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。中间路径入站朝向/局部距离场缓存只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v72不同，无单因素消融，不把较早发现或较短完成时间归因于朝向/缓存修正，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v75边际信息组件：普通前沿评分以当前交付地图的同一遮挡射线计算新增未知格比例，扣除健康同伴当前位置与已派发活动导航短段终点的预测观测重叠；不使用未执行的未来完整目标、目标真值或原生物理信息。评分乘以max(0.35,未重叠格/原可见格)，保留所有原候选与窄通道退路，原IG/路径距离/地图未知状态不变；不宣称预测格已完成。可见格cache随frontier cache按每次地图交付和规划副本变化失效，缓存只复用同一地图/半径。554全组件17.36s、四包build5.47s/source3r0旁路通过；新增共享/独立前沿、墙遮挡/有效未知格、同snapshot缓存和新地图丢弃旧cache回归。首三项失败是旧替身不接受新增keyword，已修正签名且原日志保留，无生产门限修改。保存AP三帧双机条件对照确认六组旧函数与无惩罚新函数候选完全相同，加惩罚后仍保留相同候选/路径/IG；该离线比较仅使用peer当前位姿，未还原原controller活动goal/回调buffer，不能证明任务耗时或因果收益。v74 late discovery/串行充电期间等待的原FAIL保留；另两种只读充电工作率和已返航后的出站refuge几何诊断已归档，但不足支持提前充电或出站抢占收益，未实现这些策略。原生完成与严格native_completion_ok/episode_ok、300s/.35m/.05mps/.1radps/5s、源TTL/实际body/live/return/完整能量准入保持。报告report/20261005_p3b5_marginal_information_component.json。新独立开发与正式57格待验证，809/28091从未执行，现协议controller hash尚待开发PASS后前瞻重冻；P3B.5未通过，无ns3/RL。

2026-10-05 P3B.5 v76独立六格开发FAIL，冻结6fb534998f652af8a388f80581ec69c542319ddb；所有原owner/观察器自然关闭后审核归档。p3b5_v76_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.0s/charge2/min19.87777；p3b5_v76_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/RALLY/300.0s/charge2/min21.13376；p3b5_v76_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/226.4s/charge2/min15.19251；p3b5_v76_dev_forced_forced_charge_outage_fault PASS/FOUND/300.2s/charge2/min9.06194；p3b5_v76_dev_zero_ideal_lab2_rally_8d4d5c469d FAIL/COMPLETE/300.4s/charge2/min17.67561；p3b5_v76_dev_zero_zero_rally_lab_fault PASS/COMPLETE/181.4s/charge1/min23.30388。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_marginal_information_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。当前交付地图上的边际信息重叠评分只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v74不同，无单因素消融，不把较早发现或较短完成时间归因于边际信息评分，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v77探索入站朝向组件：撤回尚未通过开发门禁的v75同伴重叠评分及其可见格cache，恢复b5f6be5的原ray IG/组评分/候选函数；v76三项超时和全部六原始结果已61e43ca完整归档，不宣称已隔离出重叠评分因果。探索Assignment可携带实际已验证短段的入站yaw，仅当派发终点地图格不同于完整frontier viewpoint时保留；send_goal传到同一gateway/Nav2，不再丢弃中间绕墙朝向。到最终观察格仍用原frontier方向；既有rally路径cache/入站yaw保持，原路线/坐标/IG/效用/完整能量与源TTL/机体/返航准入不改。552全组件16.43s、四包build7.33s/source3r0旁路通过；新增真正assign_idle_robots→send_goal→Nav2请求回归，分别验证绕墙中间航点与最终frontier朝向。保存v74已关闭AP三帧双机条件几何显示中间前沿方向与入站方向约0.57–1.64rad差；未采集原cmd_vel/executor，不宣称实际耗时收益。另试组大小bonus封顶的离线排序六组首选均不变，未实施；没有新增提前充电/出站抢占/驻点自动完成策略。原生与严格native完成函数、300s/.35/.05/.1/5s及电池/评估器/准备装置/809world字节保持。报告report/20261005_p3b5_exploration_heading_component.json。下一六格独立开发与新冻结完整57格待运行，809/28091从未执行，旧P3A.6接受冻结保持；P3B.5未通过，无ns3/RL。

2026-10-05 P3B.5 v78独立六格开发PASS，冻结e0b0345effe09e77e977feef3a8da1d4d89bb337；所有原owner/观察器自然关闭后审核归档。p3b5_v78_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/286.3s/charge2/min20.00280；p3b5_v78_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/235.7s/charge2/min23.16123；p3b5_v78_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/227.3s/charge2/min10.63302；p3b5_v78_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min10.57457；p3b5_v78_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/197.4s/charge1/min22.29280；p3b5_v78_dev_zero_zero_rally_lab_fault PASS/COMPLETE/180.6s/charge1/min24.13382。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_exploration_heading_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。保留到实际探索派发的中间入站朝向只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与v76不同，无单因素消融，不把较早发现或较短完成时间归因于探索入站朝向，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v79前瞻正式协议：v78六个独立原始开发全部关闭并严格PASS后，按当前探索入站朝向controller源hash重冻未执行的809.world/seed809/fault28091。追加v72正式15started/42unrun、v74独立六格zero ideal晚发现和v76独立六格三项超时历史，不覆盖旧失败或回填。world/电池/评估器/受控返航准备装置字节、300s与原生.35/.05/.1/5s保持；仅controller元数据/未暴露历史更新。61配置检查1.53s、27case/41unique validate-only和源码旁路通过；正式初始协议matrix仍为原54格，尚待新提交执行。552组件/build7.33与六开发ledger/graph已有记录；首静态validate-only命令缺必填run-id退出2，未启动任务，原错误保留后补参数。正式57格仍须新clean pushed同提交先强制原生ideal、E0双格、受控实际返充及全部十fixed PASS，再首次809并运行其余原primary/safety；所有同批owner/观察器自然关闭后才写报告/改源。独立master/domain/CPU池之间宿主资源仍共享，不声称任务轨迹可逐步重演；开发时间差不作因果收益。报告report/20261005_p3b5_exploration_heading_holdout_protocol.json。这是前瞻协议，不是P3B.5完成；完整严格报告待运行，无ns3/RL。

2026-10-05 P3B.5 v79原始批次验收FAIL，冻结c4c943ffc5dcecc7252f1eaba2f52dd7ce7f016d；2026-10-05 00:22:25至01:06:49UTC全部owned任务与观察器自然关闭。16started/16raw、41unrun，未重试/回填；809.world/seed809/fault28091仍从未执行。initial强制ideal原生COMPLETE220.3s/两机各charge1；fault RALLY timeout300.3s/各charge1/最低9.49659，仅安全子门PASS。E0双格FAILED1.9/2.6s、实际原生电量0、无导航；受控断网返充strict物理子门与54协议PASS。两机在守护窗口从距home1.959/2.008m开始，真实路径1.165/1.227m、净进展1.151/1.218m、Nav2 EXEC运动1.165/1.226m，各实际充电一次。全部十个固定原任务均满足未修改的episode_ok/native5秒保持，完成时间165.6至256.5s，零碰撞/耗尽/失效；但原fixed_ideal_batches继承same_candidate要求environment完全相同，而预声明world池CPU0–19/20–39/40–59不同，汇总AssertionError: environment，不能判全门禁PASS。其余环境字段一致，原manifest与失败helper全部保留，没有归一化/重写结果。16账本TTL/version及16通信图旁路审计PASS，0接触/0基础设施失败/0操作失败；实际17550..56七port/PID/env关闭及全部原helper/config/source/17用户资料哈希PASS，foreign222/master11345未动。修正下一批实验装置为全部固定world同一CPU亲和性并在首次任务前断言一致，保持严格checker/算法/任务300s/.35/.05/.1/5s/原故障与能量参数。报告report/20261005_p3b5_fixed_environment_failed_candidate.json/.md。完整strict checker/PASS图文未执行，P3B.5尚未通过，无ns3/WiFi/RL。

2026-10-05 P3B.5 v80前瞻正式协议：v79全部16原始任务/观察器自然关闭并归档ef24835后，保持controller/battery/evaluator/staging/world字节，重新预声明尚未执行的809.world/seed809/fault28091。v79十个固定任务全部原生COMPLETE，但strict same_candidate因预声明CPU0–19/20–39/40–59不同拒绝environment相等；原manifest不改，16started/41unrun与错误完整保留，不回填。新批全部十fixed及其观察器统一CPU0–79，独立world可在相同scheduler池并行，同world seeds串行；首次任务前AST解析实际helper计划并核验全部固定CPU相等、实际进程继承相同亲和性，原严格environment比较不改。初始/主故障池仍按0–19/20–39/40–59/60–79分区并用独立domain/master；所有池共享宿主资源/SMT，不宣称跨批耗时差为因果收益。61配置检查1.49s、27case/41unique validate-only和source3r旁路通过；552组件16.43s/四包7.33s及v78六开发PASS源仍相同。正式57格须新clean pushed同提交先强制原生ideal、E0双格、受控实际返充与十fixed全PASS，再首次809和其余primary/safety；原300s/.35/.05/.1/5s、源TTL、实际机体净空、能量与故障强度不变。报告report/20261005_p3b5_fixed_affinity_holdout_protocol.json。这是前瞻协议，完整P3B.5尚未通过，无ns3/WiFi/RL。

2026-10-05 P3B.5 v80原候选FAIL，冻结196154e6d8627d48b0c6a2747c52f35ac3f5eed9；2026-10-05 01:18:13–02:03:36UTC全部原owner/观察器自然关闭。15started/15raw、42unrun（lab303及其余primary/safety含809），无retry/backfill。initial强制ideal原生COMPLETE218.3s/各charge1/最低9.84126；fault RALLY timeout300.4s/各charge1/最低14.33392，仅安全PASS。E0双格FAILED1.4/2.2s/原生字段完整且无导航；受控实际断网返航与54协议PASS。两机实际路径1.142/1.149m、净进展1.135/1.139m、EXEC运动1.142/1.149m、各实际charge1。九个已运行固定格八个原生COMPLETE，lab101291.7s仅8.3s余量；lab202 RALLY timeout300.3s，两机已经各charge1/到位，tb3后期返航、终态CHARGING且charge_count0/距final5.64859m，最低14.92095，零耗尽/碰撞。全部固定manifest的实际CPU亲和性0–79及其他environment字段相同，v79汇总装置问题已消除，但任务失败仍不能判全门禁PASS。15账本/15图审计PASS，0接触/infra/操作失败；17750..56实际七port/PID/env、全部冻结helper/config/source与17用户资料哈希审核通过。保存AP在240.3/250.3秒两帧位置/速度合格、输入新鲜、目标tb3确认持续，但10秒采样不能证明连续5秒原生保持或原协调器内部flags；259秒左右tb3又要求返充。需要补足保持阻断的实际原因，不能以离散样本替代成功、放宽门限或直接宣称预算/物理抖动为根因。报告report/20261005_p3b5_observer_late_charge_failed_candidate.json/.md。809.world/seed809/fault28091仍从未执行；完整strict checker/PASS图文未执行，P3B.5未完成，无ns3/WiFi/RL。

2026-10-05 P3B.5 v81保持诊断组件：在原本地/gateway/consumed记录每5秒的导航静止、位置速度、电池/预算、预充电和保持起点；原odom越界重置附实际源时间与原因。仅加入诊断，不改变任务决策、原生完成或保持重置。去除这些诊断语句后整个control.py AST与289a6ac一致；日志I/O可能影响调度，静态等价不是运行耗时等价。首组件13fail/539pass23.70s因旧替身漏robot_velocities，补齐测试夹具后552PASS16.77s，四包build5.35s、source3r0旁路；原失败日志保留。battery/evaluator/staging/strict checker/manifest/809world字节不变。v80原15started/42unrun失败已289a6ac归档，未回填；诊断还未证明晚充电根因或修复算法。报告report/20261005_p3b5_rally_hold_diagnostic_component.json；接下来冻结独立原始诊断任务，全部owner/观察器自然关闭后再依据实际原因改进。809/seed809/fault28091仍未执行；P3B.5未完成，无ns3/WiFi/RL。

2026-10-05 P3B.5 v82独立保持诊断PASS，冻结7d2a5310d6dff88fc58be9f92af0dd6b6f1412a1，02:21:04–02:27:20UTC原owner/观察器自然关闭；lab202原生COMPLETE202.6s/0charge/min19.72218/0碰撞，ledger/graph与实际master17950/domain24/CPU0–79关闭审核PASS。三机已到位、无pending/live/yield/probe、预充电完成/预算充足后，tb2交付角速度.15991/.20801重置5s保持；0.1–0.2s原生ModelStates旁录在相近源时间实测约.19–.21rad/s峰值，说明保持重置有实际运动依据。最终原生51样本5s/最大角速度.09084/最大位置误差.02775m、观察gap.1s，完成门限不改。未采集实际cmd_vel，停止后运动的控制/动力学原因尚未确定，也不能推断该独立成功任务证明了v80失败原因。报告report/20261005_p3b5_rally_hold_diagnostic_development.json/.md；后续只读采集Nav2原输入/输出再选择运动算法优化。原15/42失败不回填；809/28091仍未暴露，P3B.5正式57格未通过，无ns3/RL。

2026-10-05 P3B.5 v83独立lab101运动/时钟诊断FAIL，冻结473810d3c0188eb8efc282059980c5324a03f6d7，02:32:39–02:40:41UTC全部原任务/AP与补充观察器关闭；检测227.5s/RALLY229.7s，任务timeout300.2s/charge2/0碰撞/无原生保持。原运动观察器缺scripts导入路径失败，第一补充进程父归属校验失败，第二补充输出目录重复失败，第三补充在任务开始后正常采集；原冻结helper未修改、任务未重启，部分采集不标完整装置PASS。三机真实参数查询确认controller_server用sim时间而velocity_smoother均use_sim_time=false、其20Hz/OPEN_LOOP/速度及加减速使用默认值；YAML缺该节点参数段。最后转向.7rad/s后输入/输出已归零，任务297.4–297.5s原生角速度约.131/.184rad/s，交付.16221重置保持；不能推断非零命令重放或clock配置就是物理峰值原因。Humble源码平滑回调是wall timer，命令超时now()使用节点时钟；下一步修复可确认的timeout时钟不一致，不宣称修改了wall callback或消除了物理抖动。ledger/graph、显式18050/domain23及所有owner/PID/source/helper/用户资料关闭审核PASS；准备器stdout的domain24标签是文字错误，实际计划/runner/domain均23且保留原文本。报告report/20261005_p3b5_motion_clock_diagnostic_development.json/.md。全部失败保留、不回填；809/28091仍从未执行，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v84 Nav2平滑器时钟组件：四份机器人Nav2 YAML新增velocity_smoother.ros__parameters.use_sim_time=true，launch原RewrittenYaml仍可随use_sim_time覆盖；修复v83实际三机参数确认的controller sim/smoother wall时钟不一致。语义比对确认每份YAML只新增该时钟键；20Hz/OPEN_LOOP/速度/加减速/1s超时数值默认、RPP/angular.7/accel3.2、Nav2.02/.25、Gazebo物理参数均不改。Humble平滑回调仍wall timer，变更统一的是命令超时节点时钟，不宣称改变了回调时基或解决物理峰值因果。现有四参数配置/身体/RPP测试加入时钟一致性，552组件16.26s、四包build5.23s/source3r0旁路PASS。controller/battery/evaluator/strict checker/staging/manifest/809world/SDF字节不变，300s/.35/.05/.1/5s不放宽。原v83任务超时与三次测量失败已0a1d00e归档，未重启/回填；组件报告report/20261005_p3b5_velocity_smoother_clock_component.json。下一六格独立开发将查询实际clock配置并保留所有原始结果，随后新冻结正式57格；809/28091仍未暴露，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v85独立六格开发FAIL，冻结14c4c416d7cd30eb958b20a528e660bebf4b6943；所有原owner/观察器自然关闭后审核归档。p3b5_v85_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/174.1s/charge1/min22.64706；p3b5_v85_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/247.0s/charge2/min23.44580；p3b5_v85_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/189.7s/charge2/min15.51925；p3b5_v85_dev_forced_forced_charge_outage_fault PASS/COMPLETE/296.8s/charge2/min9.89349；p3b5_v85_dev_zero_ideal_lab2_rally_8d4d5c469d FAIL/EXPLORE/300.3s/charge1/min3.21880；p3b5_v85_dev_zero_zero_rally_lab_fault PASS/COMPLETE/202.3s/charge1/min21.89626。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_velocity_smoother_clock_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。Nav2平滑器命令超时仿真时钟只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于Nav2平滑器时钟，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 lab202原参数只返回五项true，缺/tb3/controller_server，测量FAIL且不推断第六项。原冻结审核器未改；新关闭后只读归档器将缺响应列为测量失败并完整保留六任务。失败zero ideal原ledger有27条过期输入诊断，个人地图源龄超过5s时融合地图/pose/TF/电池仍新鲜；实际overlay地图周期5s恰等于TTL5s，缺交付余量。此为确认的配置冲突，尚不能证明加快更新就能完成任务或解决返航停滞。

2026-10-05 P3B.5 v87地图更新余量组件：实际in-repo slam_toolbox overlay的map_update_interval从5.0缩短至2.0s；原publish loop rclcpp::Rate仍为Humble host system_clock，地图header仍最新实际scan源时间。个人/融合地图源TTL5s、pose/TF2s、电池5s及过期拒绝不变，不用重复发布时刻续租。现有规划源租约回归改用一个真实producer周期加TF偏移后的地图源龄，正常帧可用、过期map仍拒绝；552检查18.30s、含slam_toolbox的五包build6.17s、source3r0旁路PASS。YAML语义只改生成周期，SLAM C++、controller/battery/evaluator/strict checker/staging/四Nav2配置/manifest/809world/模型字节不变。地图计算和消息负载增加，所有ideal/fault需同新冻结栈；2s为wall标称而非最大sim源龄保证，需新独立开发实测，不宣称修复已带来任务成功或单因素耗时收益。v85六原始FAIL与测量缺响应已d17f97a完整归档；809/28091仍未暴露，正式57格待执行，P3B.5尚未完成，无ns3/WiFi/RL。组件报告report/20261005_p3b5_map_publication_margin_component.json。

2026-10-05 P3B.5 v88独立六格开发FAIL，冻结da2b5c2105c5999460c6548e2a2d2fd02d29b52f；所有原owner/观察器自然关闭后审核归档。p3b5_v88_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.3s/charge3/min15.77163；p3b5_v88_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/RALLY/300.3s/charge3/min16.06252；p3b5_v88_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/250.6s/charge2/min8.01925；p3b5_v88_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min10.82606；p3b5_v88_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/212.2s/charge1/min21.92480；p3b5_v88_dev_zero_zero_rally_lab_fault PASS/COMPLETE/208.6s/charge1/min23.51223。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_map_publication_margin_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。两秒实际地图生成周期统一用于ideal/fault，地图header保留实际scan源时间，TTL不变，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于地图周期，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 六格真实Nav2与SLAM参数响应齐全且正确，无缺响应；只读服务查询重发记录保留，不是任务重试。源地图交付龄和更新间隔全部在JSON保留，不能把AP观测年龄当成原协调器缓存或最大时限。两个fixed均charge3、RALLY timeout300.3s、0接触；最后观测者tb2在同伴返充后离开，未有新观测者接替确认；目标源过期触发盲扫描/普通前沿重搜。现guard只保护5s，而已接纳target租约60s，下一候选保持最后观测者角色至有效租约内实际接替，不能延长target TTL/用expired目标派发或阻止本地安全返航。

2026-10-05 P3B.5 v90观测者角色租约组件：最后交付确认对应的观测者角色保留至原target源租约60s内的实际同伴新确认接替，5s心跳缺口不再被当作交接完成。角色保护不宣称当下仍可见，不生成检测/不续租source；本地非ACTIVE、已接纳早充请求及capacity不足仍优先。相机heartbeat/朝向修复5s、target TTL60s、其他源TTL/早充串行/全路线+等待+返航预算/机体净空/300s/.35/.05/.1/5s原生门不改。仅rally_observation_guard和prepare_rally_charges AST变化，其余控制函数AST一致；battery/evaluator/strict checker/staging/四Nav2/SLAM2s配置与C++/manifest/809world/SDF字节不变。现有handoff回归加入超过5s但有效target的实际等待、真实新peer确认才移交；边界60s/未来stamp/非finite/返航/充电/FAILED-peer均覆盖。556检查18.00s、四包build5.31s/source3r0旁路PASS；组件不证明任务收益，下一独立六格需完整关闭、保留再新冻结正式57格。v88六原始FAIL已14a5798完整归档，不回填；809/28091仍未执行，P3B.5未完成，无ns3/WiFi/RL。报告report/20261005_p3b5_observer_role_lease_component.json。

2026-10-05 P3B.5 v91独立六格开发FAIL，冻结2d1a1b8204811aa54ba2557bdbb3b277bb97476e；所有原owner/观察器自然关闭后审核归档。p3b5_v91_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.2s/charge2/min18.31056；p3b5_v91_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/FAILED/180.7s/charge0/min29.75193；p3b5_v91_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/233.0s/charge2/min10.58555；p3b5_v91_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min10.83913；p3b5_v91_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/196.2s/charge1/min21.57276；p3b5_v91_dev_zero_zero_rally_lab_fault PASS/COMPLETE/198.8s/charge1/min21.89806。全部中间结果/源、六ledger/graph、精确命令/环境/hash/AP见report/20261005_p3b5_observer_role_lease_development.json/.md。强制fault仅按既定各机充电/正能量/无碰撞安全子门验收，未原生完成不计任务成功；lab101/lab202、force ideal和zero pair必须原生5秒保持。原target60s租约内保护最后观测者角色，只有真实同伴确认才移交；心跳5s/其他源TTL不变，控制只用交付输入，旧动作自然结束，完整机体/实际路线/源TTL/能量准入保持。本次轨迹与历史候选不同，无单因素消融，不把较早发现或较短完成时间归因于角色保护，不宣称最坏时限保证。无整轮重试/回填；809/28091从未执行，开发结果不代替新冻结正式57格，P3B.5尚未完成，无ns3/RL。 六格真实参数响应齐全且正确；时间审计五PASS、lab101 FAIL，六运行图独立审核PASS（见审计更正）；无source/helper/用户资料改动，无任务重试。lab101角色保护实际保持到确认缺口超过24s但仍RALLY timeout300.2；原生旁录tb2静止距target2.167m、yaw2.454、target方向1.592，误差约.862rad>FOV半角.785，实际朝向恢复缺失，不续租或推断仍可见。lab202在180.7s因insufficient_rally_poses FAILED、0charge/min29.75193，无物理失败机器人；三原AP末期条件回放各18候选，tb2可达16而tb1/tb3与home仅达2，原图与现有自回波规划副本均无完整三机分配。单纯候选数量不能保证连通；需调查连接区域，而不是放宽净空/穿未知格。AP回放不是原内部buffer或反事实任务，原生只读取证不反馈控制，不宣称角色修改已解决任务。

2026-10-05 P3B.5 v91归档审计更正：此前734bc85“所有原ledger/graph审核通过”错误，后置核验KeyError(temporal_audit)后仍继续提交；现分别审计六原始格，未修改原checker/ledger/helper。lab101时间审计FAIL，首个observer_handoff_wait在2243.282使用2234.082确认、年龄9.2s，违反原5s交接门槛；其余五时间审计PASS，六运行图独立PASS，三个原生COMPLETE、两fixed任务失败及forced fault安全结果不变。原JSON/失败audit/原始物理旁录/hash/提交保留，report/20261005_p3b5_observer_role_lease_audit_correction.json/.md明确取代旧“六时间通过”结论。全部原owner/观察器/四master已关闭，原源/配置/helper/用户17文件及raw hash一致。v90角色保护60s未满足既定5s门槛，不能进入正式验收；后续恢复5s并修复实际朝向/连接调查，绝不放宽checker、TTL、能量、净空或原生完成条件。未重跑、回填或执行809/28091，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v93组件PASS（未作任务成功声明）：基于v91失败及审计更正恢复原观测交接5s门槛，严格checker不改。等待且未到最终驻点的最近观测者，可在当前已知安全位置对准交付目标；按原.35静态/.6机体/实际路线/返航预约/并发/源TTL检查，以自身返航储备加原goal-timeout空耗准入，独立本地返航可抢占，沿用有限survey动作/次数。真实调查前缀在已知可见且范围内时面向目标；完整驻点分配受阻且原靠近调查不可派发时，复用射线收益前沿候选，按边界距目标/原utility排序调查连接区域，保留观测机器人，可走先远离目标的已知安全绕行；不虚构未知格连通，不增加动作框架。朝向成功不延长地图准备计时或标记最终到位。首次聚焦9FAIL/301PASS（新地图假设错误及旧到位路径重叠），修正后311PASS12.88s；最终573PASS15.98s、四包5.37s、3r源码零旁路PASS，其他控制函数AST/电池/原生/evaluator/staging/协议/world/model/SLAM与Nav2参数hash不变。详见report/20261005_p3b5_observation_connection_component.json。开发101/202/303非holdout；809/28091未执行，新独立六格与新同提交正式57格待验证，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v94独立六格开发FAIL，冻结9b513fab47c445e1da44bb0304cc77bb301a3000；全部原owner/观察器自然关闭后逐项审核。p3b5_v94_dev_fixed_lab101_lab_far_northwest_3r_seed101 FAIL/RALLY/300.0s/charge3/min21.04333；p3b5_v94_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/280.3s/charge2/min25.82174；p3b5_v94_dev_forced_ideal_forced2_rally_86fbb43bc6 FAIL/RALLY/300.3s/charge2/min15.92234；p3b5_v94_dev_forced_forced_charge_outage_fault PASS/RALLY/300.1s/charge2/min10.36649；p3b5_v94_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/226.3s/charge1/min18.72230；p3b5_v94_dev_zero_zero_rally_lab_fault FAIL/FAILED/213.1s/charge0/min17.41613。时间审计6/6 PASS、运行图6/6 PASS、原生COMPLETE2/6，参数测量失败0；缺失不推断、各审计独立，不因一项失败跳过其它证据。强制fault仅各机充电/正能量/无碰撞安全子门，未原生完成不计任务成功。恢复既定观测交接5s；待行观测者对准有效交付目标、调查腿可见时朝向目标，分配受阻复用实际射线收益前沿绕行调查连接区域；不续租或虚构未知格，不增加完整任务重试，原地图/电池/poseTF/target TTL、净空/机体/能量/300s与.35/.05/.1/5s原生门槛均不变。所有源/参数/helper/用户17文件hash及四master/PID关闭核验通过，完整源/原始/hash/AP/物理旁录/精确命令见report/20261005_p3b5_observation_connection_development.json/.md。共享宿主及启发式预算不提供最坏时限保证，无单因素归因；几何视觉proxy/原生与AP只读取证不参与控制。809/28091从未执行，开发101/202/303不是holdout，本批不是正式57格替代，P3B.5尚未完成，无ns3/RL。

2026-10-05 P3B.5 v96组件PASS、尚非集成验收：v94六原始全部自然关闭并FAIL归档后，修复探索前沿过期重规划：原“stale”分支要求20s无进展，正常时钟/进展更新下被原stalled条件覆盖；旧收益取中间航点也不代表最终观察点。现在只在源新鲜、原3s成熟/收益门槛、距航点>.75m，且另有空间分离/实际机体/在途预约/已知可见有效前缀/完整去返预算均合格的前沿时取消旧腿，待旧结果才正常重分配；预算不足/近到达/摄像重搜/本地RETURNING/已取消均保留原行为。观测者可在当前已知.35净空且.6机体安全的位置对准未过期检测，即使融合目标LOS尚未知；调查端点/原路线预约不改，只改变范围内观测者朝向，不授权走入未知或宣称可见。v94旁录lab101首次无遮挡样本187.9s、确认188.1s，证据支持物理接近偏晚；zero fault安全驻点/目标LOS未知/yaw出FOV条件回放只读取证不当原buffer或反事实成功。聚焦323PASS13.43s，最终585PASS16.27s、四包5.32s、3r源码零旁路；其它控制函数AST/严格checker/电池/evaluator/准备夹具/world/model/参数hash不变。详见report/20261005_p3b5_fresh_frontier_replan_component.json。无原生控制输入、门槛/TTL/时限/次数放宽；809/28091仍未执行；新独立六格及同提交正式57格待通过，P3B.5未完成，无ns3/RL。

2026-10-05 P3B.5 v97独立六格开发FAIL，冻结8c0ad72523847e43c7b7457ea2781885c3f24c43；全部原owner/观察器自然关闭后逐项审核。p3b5_v97_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/247.1s/charge1/min18.80650；p3b5_v97_dev_fixed_lab202_lab_far_northwest_3r_seed202 FAIL/RALLY/300.0s/charge1/min19.49767；p3b5_v97_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/211.5s/charge2/min16.22351；p3b5_v97_dev_forced_forced_charge_outage_fault PASS/EXPLORE/300.1s/charge2/min9.00373；p3b5_v97_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/238.4s/charge1/min24.29664；p3b5_v97_dev_zero_zero_rally_lab_fault PASS/COMPLETE/187.5s/charge1/min23.51882。时间审计6/6 PASS、运行图6/6 PASS、原生COMPLETE4/6，参数测量失败0；缺失不推断、各审计独立，不因一项失败跳过其它证据。强制fault仅各机充电/正能量/无碰撞安全子门，未原生完成不计任务成功。保留原交接5s；最终前沿收益过期且另有当前可达/完整预算/实际机体/在途预约/有效可见前缀的替代时，进展中可取消并排空旧腿再正常重选。近到达/无预算或替代/地图过期/本地返航/相机重搜保持原行为。有效检测只指导安全位置的观测朝向，即使目标LOS未知也不授权未知格位移；不续租或虚构未知格，不增加完整任务重试，原地图/电池/poseTF/target TTL、净空/机体/能量/300s与.35/.05/.1/5s原生门槛均不变。所有源/参数/helper/用户17文件hash及四master/PID关闭核验通过，完整源/原始/hash/AP/物理旁录/精确命令见report/20261005_p3b5_fresh_frontier_replan_development.json/.md。共享宿主及启发式预算不提供最坏时限保证，无单因素归因；几何视觉proxy/原生与AP只读取证不参与控制。809/28091从未执行，开发101/202/303不是holdout，本批不是正式57格替代，P3B.5尚未完成，无ns3/RL。

2026-10-06 P3B.5 v99返航前缀组件PASS、尚非集成验收：v97六原始已自然关闭FAIL归档8cc441d。lab202实际tb3返充前两腿各20s停滞取消且Smac多次lethal-start；只读AP90/100自身格有多格占用簇，原单格自回波规则未清任何格，110..160自身虽known-free仍在净空膨胀区，原规划把短逃离与远端返航组合派发。现在只有已验证home/contact路线存在且包含原有known-free净空逃离时，先发送该原短前缀及实际入射yaw，待原动作结果再重规划；原占用/未知起点仍拒绝，所有障碍/未知/净空/机体/储备/TTL/返航总时限/watchdog保持，Smac/RPP仍可拒绝动作，不保证恢复或因果加速。54定向2.01s、591全组件17.28s、四包5.26s、3r源码零旁路；仅plan_charging_leg改动，其它电池函数AST/control/严格checker/原生300s与.35/.05/.1/5s/所有Nav2和SLAM参数hash不变。第一次inline只读诊断因stdin文件名失败，独立文件helper修正成功，原失败保留；无任务重试。证据report/20261006_p3b5_return_escape_prefix_component.json。开发101/202/303不是holdout；809/28091仍未执行，独立六格及正式57格待通过，P3B.5未完成，无ns3/RL。

2026-10-06 P3B.5 v100独立六格开发PASS，冻结4233c620cb714f87a9c3067ff8fd9ce0bb267e2d；全部原owner/观察器自然关闭后逐项审核。p3b5_v100_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/286.1s/charge2/min22.78632；p3b5_v100_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/187.9s/charge1/min23.65887；p3b5_v100_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/230.9s/charge2/min14.63966；p3b5_v100_dev_forced_forced_charge_outage_fault PASS/RALLY/300.3s/charge2/min9.35914；p3b5_v100_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/198.2s/charge1/min22.87146；p3b5_v100_dev_zero_zero_rally_lab_fault PASS/COMPLETE/148.1s/charge0/min25.73072。时间审计6/6 PASS、运行图6/6 PASS、原生COMPLETE5/6，参数测量失败0；缺失不推断、各审计独立，不因一项失败跳过其它证据。强制fault仅各机充电/正能量/无碰撞安全子门，未原生完成不计任务成功。保留原交接5s；存在原有效home/contact路线且包含当前known-free净空逃离时，先执行该原短前缀，原动作结果后重新规划返航；占用/未知起点仍拒绝，不清任何障碍格，原机体/净空/返航总期限/储备/watchdog/Smac与RPP拒绝保护不变；不续租或虚构未知格，不增加完整任务重试，原地图/电池/poseTF/target TTL、净空/机体/能量/300s与.35/.05/.1/5s原生门槛均不变。所有源/参数/helper/用户17文件hash及四master/PID关闭核验通过，完整源/原始/hash/AP/物理旁录/精确命令见report/20261006_p3b5_return_escape_prefix_development.json/.md。共享宿主及启发式预算不提供最坏时限保证，无单因素归因；几何视觉proxy/原生与AP只读取证不参与控制。809/28091从未执行，开发101/202/303不是holdout，本批不是正式57格替代，P3B.5尚未完成，无ns3/RL。

2026-10-06 P3B.5 v101前瞻正式协议：v100全部六个独立开发原owner/观察器自然关闭且完整PASS归档后，更新当前control与battery源hash、四Nav2参数与SLAM2s参数，保持尚未执行的809.world/seed809/fault28091/目标(4.4,-3.4)/3rE45与原静态声明字节；原v80的15started/42unrun失败及其旧controller/battery/hash保留在冻结历史。开发源码仍为591组件17.28s、四包5.26s、3r源码零旁路；仅原已知自由净空逃离先单独执行，再于原回调重规划长返充，原占用/未知起点/障碍/净空/储备/Smac/RPP保护与时限不改。61配置检查、27case/41unique validate-only和source旁路PASS，无Gazebo任务启动。正式57格包括27pair/41主格、十fixed和六安全探针；所有fixed与AP观察器统一CPU0–79，其它池仍20逻辑CPU分区，独立world可并行同world seed串行，宿主/SMT共享不提供因果或最坏时间保证。AP只读参数请求使用有界2s重发，只测真实Nav2时钟/SLAM参数和map源龄，不重试任务、不续源header、不用于控制。所有源码/helper/协议首次执行前hash冻结，全部started原任务自然关闭前不改；原300s/.35/.05/.1/5s与TTLs/故障强度保持。必须先forced ideal原生保持、E0反例、真实受控断网返航与十fixed全部PASS，才能首次809及剩余主/安全矩阵；任何失败原样保留，无整轮重试或回填。证据report/20261006_p3b5_return_escape_holdout_protocol.json。P3B.5尚待完整严格门禁，无ns3/WiFi/RL。

2026-10-06 P3B.5 v101正式原候选FAIL，冻结0fff5eb4ed3b57e1f60a9f7a6e8d1ecdabac1b93；04:30:04–04:43:13UTC全部原owner/观察器自然关闭。5attempted/4native-started/4raw，1强制ideal启动600s超时且episode_started=false/无原生结果、图和安全trace；52not-invoked含全部十fixed及809（53未进入原生评估）。不把summary缺结果行计为raw或启动，不推断该格碰撞/电量。原force fault未调用；E0双格原生FAILED2.1/1.9s且无导航；controlled-return双格EXPLORE timeout300.3/300.1s，各机器人charge1、最低9.70732/9.56846，仅安全子门。实际fault黑障62..248s两机返航路径1.21190/1.16494m、净回home进展1.20063/1.15387m、Nav2 EXEC运动1.21188/1.16491m，关闭后原strict physical-return审核PASS。54纯协议/5账本因果TTL版本与决策租约PASS，4图0旁路，1图缺失；四raw0接触，1infra/操作失败。原网关观察器exit0；附加AP因无result被owner SIGINT后重复rclpy.shutdown报错exit1，最终metadata未写完整，原traceback与部分数据保留。原tb2 SLAM只到stack-size输出、未Ceres/Lidar初始化，tb2 planner lifecycle异步请求失败；只读/proc五线程均futex、没有已观察到UDP等待线程，不能据此证明SHM/DDS根因。实际19350..56七端口/PIDs/master环境后代关闭、全部冻结source/config/helper与17用户资料哈希通过；原600s启动/300s任务及原生5s等阈值未放宽，无整轮重试/回填。准备helper第一次在push未完成时被clean-pushed guard拒绝、未创建helper/未启动任务；卡住SSH push仅终止已核验自有git/ssh，随后IPv4 bounded push成功，再首次启动本批；全部记录保留。归档第一次读取缺失result字段KeyError（原summary确无该键），修正仅只读归档器用get，任务没有重启。809.world/seed809/fault28091从未执行；完整strict gate/PASS图文未执行，P3B.5仍未完成，无ns3/WiFi/RL。证据report/20261006_p3b5_native_startup_failed_candidate.json/.md；下一候选只在全部关闭后前瞻验证原生启动环境，不能把当前缺失结果修补为成功。

2026-10-06 P3B.5 v102原生启动环境组件：本机FastDDS2.6.11官方实现与实际库均支持FASTDDS_BUILTIN_TRANSPORTS=UDPv4；新候选统一显式RMW=rmw_fastrtps_cpp/UDPv4，尚无新环境任务门禁PASS。新增manifest记录RMW、builtin transport、FASTRTPS XML路径与source digest；原same_candidate直接拒绝环境改变和同路径XML字节改变，未修改strict checker/native evaluator/control/battery算法。598组件17.04s、四包build6.87s、source3r0旁路；其中三项检查先确认reference自比通过，再只改transport/RMW/XML字节并要求environment断言失败。中间件探针原第一组4个native DEFAULT描述符通过，但16个demo ROS进程因话题末段纯数字参数解析失败，原stdout/exit与全部自有关闭保留；没有Gazebo/任务/809启动。修正命名后另起v102b独立组件探针，DEFAULT/UDPv4各四domain，8个native实际描述符+32个C++/Python ROS进程、16监听者双向交付各至少两条，全部PASS且自然/预声明10s窗口后正常关闭。实际UDPv4描述符为udp1/shm0/other0；DEFAULT为udp1/shm1。只证明当前模式配置与这些交付，不证明v101初始化卡住是SHM根因、消除所有死锁、任务提速或最坏启动时限。新推荐终端命令显式export环境，同环境覆盖机器人/总部/所有理想与故障基线/只读观察器；profile若关闭builtin transports可覆盖该环境，因此冻结前禁用未声明profile并核验actual descriptor。原v101的5attempted/4native/1absent/52not-invoked失败已ae50fe1归档，不修补/回填；v100六开发PASS是在原环境的算法证据，不能代替新环境任务验证。809.world/seed809/fault28091仍未执行；需新冻结完整57格、原forced/E0/物理返充→十fixed→新留出主矩阵。原300s/.35/.05/.1/5s与源TTL/故障强度不变，P3B.5未完成，无ns3/WiFi/RL。证据report/20261006_p3b5_native_transport_component.json。

2026-10-06 P3B.5 v103前瞻正式冻结：v101所有原owner/AP/网关观察器自然关闭且失败完整ae50fe1归档后，v102中间件组件dab2270已提交推送；当前control/battery/世界809原字节不变。新批统一显式RMW_IMPLEMENTATION=rmw_fastrtps_cpp/FASTDDS_BUILTIN_TRANSPORTS=UDPv4，所有机器人/总部/ideal及fault基线/只读观察器同环境；不使用未声明XML/discovery server。manifest新增环境记录，strict checker/native evaluator/control/battery均原字节；64配置1.51s、27case/41unique validate-only、source3r0旁路PASS；v102为598组件17.04s/四包6.87s和实际native descriptors/双向C++Python交付PASS，尚非新环境任务成功。原算法v100六独立开发PASS是在此前中间件环境，不能替代当前集成；v101五次调用/四原生启动/一缺结果/52未调用原失败仍保留。新AP helper仅只读真实参数/map源龄与实际RMW标识，使用本机已提供try_shutdown避免信号关闭后的重复shutdown异常；原AP partial metadata/traceback保持。正式仍57格：27pair/41主格+十fixed+六辅助；所有fixed/AP为实际CPU0–79，独立world可并行，同world seed串行；initial/main20逻辑CPU分池。所有源/helper/配置/最终报告builder在第一次运行前hash冻结；必须先强制ideal真实原生保持/E0/断网实际返航，再十fixed全部PASS，才首次运行809.world/seed809/fault28091/目标(4.4,-3.4)/3rE45及剩余主/安全矩阵。809从未运行，初静态world字节及真实launch连通补查保留；原300s/.35/.05/.1/5s、源TTL与故障强度保持，不重试/回填。全部已启动原owner/观察器自然关闭前不改源/文档/helper。证据report/20261006_p3b5_native_transport_holdout_protocol.json；P3B.5仍待完整strict gate，未启动ns3/WiFi/RL。

2026-10-06 P3B.5 v103原候选FAIL，冻结dbed34c0ed708803e131ef00ecff7791e6b3cde3；2026-10-06 05:01:23–05:46:58UTC所有原owner/观察器自然关闭。16started/16raw、41unrun（其余primary/safety含809），无retry/backfill。uniform rmw_fastrtps_cpp/UDPv4真实环境；initial强制ideal原生COMPLETE249.3s/各charge1/最低14.00323，fault300.0s RALLY timeout/各charge1/最低9.23028，仅既定安全PASS。E0双格原生FAILED2.8/.6s/无导航；受控返充两格准备exit0，断网62..248s两机实际路径1.20333/1.14938m、净进展1.19708/1.14094m、EXEC运动1.20330/1.14935m、各charge1，物理返充子门PASS；54纯协议PASS。十固定全部运行，九个原生COMPLETE：lab101260.1、lab202168.4、rooms101/202/303114.8/153.6/177.4、corridors101/202/303194.2/221.9/226.1、双机corridors202175.0s。lab303检测113.9/RALLY116.2、timeout300.4s，tb2/tb3各charge1、最低19.45906、所有终态ACTIVE。终态位置误差均<.1m但原生completion/native proof为null；原中央诊断near298.9s开始保持，299.7s收到tb1角速度.12946rad/s>原.1门限重置，未完成连续5s。16账本因果/TTL/version/决策租约与16图审计PASS，0接触/infra/操作失败，除预声明E0终止外无耗尽或failed机器人；十fixed实际CPU0–79及environment一致，观察器实际RMW/UDP、Nav2模拟时钟/SLAM2s参数保留。19450..56七port/PID/env、全部冻结helper/config/source与17用户资料哈希审核PASS。已关闭AP与路线日志显示观测者让开后继充电机器人的进路后才末段回位；这是诊断证据，不能由离散AP样本证明原生保持或宣称因果加速/最坏时间保证。归档脚本首次把环境大写key误读为小写→KeyError，修正只读归档并保留首错误；未重复任务。报告report/20261006_p3b5_rally_hold_time_failed_candidate.json/.md。300s/.35/.05/.1/5s、poseTF2/mapbattery5/target60/handoff5、body.6/static.35/集合位.45/route1.8阈值与严格checker未放宽；809.world/seed809/fault28091从未执行。完整strict checker/PASS图文未执行，P3B.5未完成，无ns3/WiFi/RL。

2026-10-06 P3B.5 v104合法避让驻点保留组件PASS：v103十fixed中lab303末段原生保持失败已7442599归档。仅在所有非避让同伴到位、在途/待接收动作结束后，对已完成目标朝向的临时驻点，用当前交付地图检查原.45净空/已知目标视线/相机range减.35误差余量/原.8最终位间距/.6当前body间距；所有电池ACTIVE、无返充请求、输入/目标新鲜且完整保持返航预算充足时，将同一个已到达pose保留为final。无新动作或朝向声明；原发布路径、能量预检重做、保持计时重置、原生300s/.35/.05/.1/5s继续。无效驻点按原逻辑回旧final。46定向1.40s、627组件18.50s、四包5.46s、3r源码零旁路；仅update_mission及新增retain_rally_refuge，其余控制函数AST、电池/严格checker/评估器/Nav2/SLAM/809字节不变。首状态机夹具遗漏logger两次失败44/45pass和首广测路径错误no-tests原日志保留，修正全PASS，无任务重跑。已关闭AP三帧几何支持合法驻点，但不证明运行准入/连续原生保持/因果加速或最坏时限。证据report/20261006_p3b5_rally_refuge_retention_component.json；809/28091从未执行，需新独立lab101/202/303+force/zero开发和完整57冻结。P3B.5未完成，无ns3/RL。

2026-10-06 P3B.5 v105独立七格开发PASS，冻结c204e6464f0e010ae19c92c5f310e1607a877081；2026-10-06 06:03:27–06:16:55UTC所有原owner/观察器自然关闭后审核。p3b5_v105_dev_fixed_lab101_lab_far_northwest_3r_seed101 PASS/COMPLETE/140.9s/charge0/min23.91124；p3b5_v105_dev_fixed_lab202_lab_far_northwest_3r_seed202 PASS/COMPLETE/204.8s/charge1/min20.79709；p3b5_v105_dev_fixed_lab303_lab_far_northwest_3r_seed303 PASS/COMPLETE/200.6s/charge1/min23.04201；p3b5_v105_dev_forced_ideal_forced2_rally_86fbb43bc6 PASS/COMPLETE/287.1s/charge2/min9.26002；p3b5_v105_dev_forced_forced_charge_outage_fault PASS/RALLY/300.4s/charge2/min9.72368；p3b5_v105_dev_zero_ideal_lab2_rally_8d4d5c469d PASS/COMPLETE/191.4s/charge1/min22.62572；p3b5_v105_dev_zero_zero_rally_lab_fault PASS/COMPLETE/120.2s/charge0/min27.41611。七账本因果/TTL/version/决策租约与七图审计PASS，六任务原生COMPLETE；强制fault300.4s RALLY timeout、各charge1/最低9.72368/0碰撞，仅预声明安全子门PASS，不计任务成功。七格0接触/耗尽/failed/infra，七个只读Nav2模拟时钟/SLAM2s参数与实际rmw_fastrtps_cpp/UDPv4测量完整；五master/PID/env、所有冻结source/config/helper与17用户资料hash PASS。强制ideal287.1s仅12.9s余量，预算仍无最坏时限保证。开发日志未出现Retaining分支触发，本批证实此控制SHA的任务回归，不证明新增避让驻点分支实际触发或单因素因果收益；组件夹具与原v103关闭地图几何证据仍独立保留。完整原始/命令/源及环境/hash/AP/物理旁录/审计见report/20261006_p3b5_rally_refuge_retention_development.json/.md。全部300s/.35/.05/.1/5s与源租约/实际返充/能量/机体/净空/预约阈值未改，无retry/backfill；809/28091从未执行，开发101/202/303不是holdout，开发PASS不能替代新完整57门禁。P3B.5尚未完成，无ns3/WiFi/RL。

2026-10-06 P3B.5 v106前瞻正式冻结：v103十fixed原lab303保持失败和全部16原始已7442599归档；新控制v104c204e64与v105七独立开发PASS已2b87e5c保留并推送。原809.world/seed809/fault28091/目标(4.4,-3.4)/3rE45仍从未执行，world字节及最初静态/真实launch补查保留；更新当前controller SHA、控制源提交与开发引用，追加v103失败历史。当前保留合法已完成避让驻点仅为条件性恢复优化；七开发六原生COMPLETE、forced fault安全PASS，日志未见新分支触发，不能宣称新分支物理验证/因果加速或最坏时限。新批所有机器人/总部/ideal/fault/只读观察器统一显式rmw_fastrtps_cpp/UDPv4，无XML/discovery server；627组件18.50s/四包5.46s/源码3r零旁路，64配置1.71s、27case/41unique validate-only PASS，无仿真启动。正式仍57格：27pair/41主格+十fixed+六辅助；所有fixed/AP实际CPU0–79，initial/main20逻辑CPU分池，master19650..19656与独立domain。运行前冻结所有source/helper/config/report-builder哈希，按强制ideal真实原生保持/E0/实际断网返充→十fixed全PASS→首次809及其余主/安全矩阵推进；所有原owner/观察器自然关闭前不改源/文档/helper。300s/.35/.05/.1/5s、地图/电池5/poseTF2/target60/handoff5、原故障强度和实际储备/返充/机体/静态/最终位/在途预约保护不变，不重试/回填/把开发替代正式格。证据report/20261006_p3b5_rally_refuge_holdout_protocol.json；P3B.5仍待完整strict gate，无ns3/WiFi/RL。

2026-10-06 P3B.5 v106全57原始自然关闭，冻结d8d361bfd9d81e0c7a00c428ea66cfac4b3a1a76；2026-10-06 06:24–08:42:53UTC。57raw/0unrun/0retry，0接触/infra/操作失败，57ledger与57graph独立PASS、54纯协议PASS。十fixed全部原生COMPLETE，lab303294.8s仅5.2s余量；forced ideal155.2s各charge1。首次809六格全部保留，rally ideal/fault120.9/126.6s原生COMPLETE，target两侧FOUND、coverage两侧达标。single_failure原生PARTIAL_COMPLETE148.9s，tb3为预声明真实FAILED、两健康机保持证明完整、最低19.47128、0碰撞。七port/PID/env与所有冻结source/helper/config、17用户资料hash PASS。原完整strict checker exit1：staging_source_sha256生产端为SHA256(文件名+原字节)，校验端却比较纯源码SHA；两行存储594a3fe...，原源码和预声明纯字节47ce799...完全一致。原FAIL traceback/源码、全部57原结果与命令/环境/hash/AP保留，不改原manifest、不补写结果、不重跑Gazebo。809已首次暴露，后续控制算法变化需真正新留出；只读校验修复待完成，P3B.5尚未PASS，无ns3/WiFi/RL。

2026-10-06 P3B.5 v107只读摘要校验组件PASS：原v106全57同提交任务及首次checker FAIL已5c1f931独立归档。仅checker按原生产端file_digest的文件名+原字节SHA验证，并新增保存源码=实际文件=预声明纯字节SHA和实际命令脚本路径绑定；未接受纯字节摘要冒充旧字段、未改producer或任何任务栈/协议/原始数据。九组有效/篡改检查、全636组件17.49s PASS；除main接入外原12审计函数AST相同，57原始文件树全部SHA重核、17用户资料不变。原生300s/.35/.05/.1/5s、源TTL、碰撞/正电量、真实返充与5s隔离条件未变。完整修复后只读checker仍待执行，组件PASS不代替任务门禁；809已在原d8d361b首曝，本次非新任务/未见验证，无ns3/RL。证据report/20261006_p3b5_staging_digest_reader_component.json。

2026-10-06 P3B.5技术门禁PASS，待用户验收：v106原57格冻结d8d361bfd9d81e0c7a00c428ea66cfac4b3a1a76，2026-10-06 06:24–08:42:53UTC自然关闭；41主格/27pair+十fixed+六辅助，57时间与57图审核、54纯协议全部PASS，0接触/infra/操作失败、0整轮retry/backfill。十fixed原生COMPLETE；forced ideal155.2s各charge1。首次809/28091集合ideal/fault120.9/126.6s原生COMPLETE，目标两侧FOUND、覆盖率两侧达标，仅过程指标。真实tb3失败隔离0.1s，两健康机原生PARTIAL_COMPLETE148.9s/最低19.47128，success=false。TDI18eligible/5物理簇均值0.685185，95%描述性簇bootstrap[0.487179,0.823529]，10000次seed17011；rally fault5COMPLETE/20pair、1PARTIAL，其余真实失败/静默/超时保留，复用ideal不独立计样本。原checker摘要格式FAIL已5c1f931保留，77c201b仅修复只读摘要校验，636组件17.49s/九篡改反例PASS，原12审计函数AST和全部任务栈/原始记录未变；同57原数据重新严格审计PASS，无Gazebo重跑。lab101真实执行一次tb2驻点保留并原生完成，但无单因素收益或最坏保证；lab303294.8s仅5.2s余量。53参数旁录完整，E0双格和物理返充双格为独立原生证据。七port/所有owner/观察器/冻结source/helper/config及17用户资料SHA通过；JSON/MD/PNG视觉QA PASS。P3A.6已验收22c95a7历史冻结保留；809现已暴露，之后控制变化需新留出。报告report/20261006_p3b5_gate.json/.md与_results.png，技术完成待用户验收，未进入P3C/ns3/WiFi/RL。
