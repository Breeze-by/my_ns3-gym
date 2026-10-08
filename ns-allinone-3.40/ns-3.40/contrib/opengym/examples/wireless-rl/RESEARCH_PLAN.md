# 面向多机器人任务的无线通信调度研究总纲

2026-10-08评审结论：既有P1–P3的工程证据按原边界保留，P3C.5技术PASS，用户于2026-10-08已验收；不能直接推导无线性能、一般安全或RL收益。更严格只读重审通过P3A.6十一原任务、P3B.5六十三原任务/31配对、P3C三原任务和P3C.5十四原任务。新增协议内容/预声明绑定与模型冻结检查已修复审计遗漏。**本地与部分中央返航预算仍用欧氏距离×系数，原计划的已知地图路径预算要求尚未关闭；进入P4A-1闭环及P5正式比较前必须完成安全补强和新的任务冻结。** 当前没有容量模型，Wi-Fi瓶颈状态是“未测量/不可由该模型识别”，不能称为已测得无瓶颈的负结果。完整要求映射、反例、修订理由和验证见[项目评审](report/20261008_project_review.md)及[机读证据](report/20261008_project_review.json)。本轮只有审阅、只读重放和审计/文档修改，没有启动新的Gazebo/ns-3/Wi-Fi/RL任务。

2026-10-07最新进展：P3C已验收，P3C.5技术完成、严格门禁PASS，待用户验收。bea7f8b冻结14原格11原生COMPLETE/3 RALLY超时、零碰撞/耗尽/失效/infra/retry；forced217.5秒各机充电一次。真实协议/阶段分层/控制成本/截止与AoI/可部署观测/实时回放完成；原任务和前两技术失败候选保持。任务/生成器/源TTL/原生门槛/安全不变。当前应用模型未证明容量瓶颈，未标定真实airtime/J，保持负载、不得人为增流量或启动RL。见[P3C.5最终报告](report/20261007_p3c5_gate.md)和[前瞻协议](report/20261007_p3c5_protocol.md)。未进入P4/ns-3/Wi-Fi/RL。

2026-10-07已验收边界：P3A.6、P3B.5、P3C均已由用户验收。P3C原三任务COMPLETE197.1/235.0/265.6秒、658快照/26852 CSV行同源及63历史任务/1879流/31 TDI回放证据保持，见[P3C报告](report/20261007_p3c_gate.md)。监控只读；控台经独立服务更新应用故障并对齐曲线。P3C.5现为技术完成待用户验收；809已暴露，后续未见验证须另行冻结。

最后更新：2026-10-08；旧日期段落保留各自历史状态，当前路线以正文和本次评审为准。

本文档记录本项目的长期研究目标、当前决策、实施路线、评测口径和已知风险。它是后续研究
和 agent 协作的方向性依据，不是当前代码功能清单。已经实现的行为以
`ros2_ws/ros2-multi-robot-automap/user_guide.md` 和
源码为准，实验事实以日期报告和 `log.md` 为准。

逐步落地顺序、工程产物、退出条件和当前进度见 `IMPLEMENTATION_PLAN.md`。

## 0. 本轮路线决策（2026-09-29）

以下决策已根据教师评审意见和用户确认纳入主计划；它们是研究边界，不能被后续
实现自行扩大：

| 决策 | 当前约定 | 状态 |
|---|---|---|
| 学习范式 | 默认采用集中式、部分可观测的单智能体通信调度器（POMDP 视角）；多机器人不自动等于 MARL | 已确认；实现待完成 |
| 第一版学习变量 | 固定消息语义、消息生成方式和机器人任务栈，只学习应用层消息准入；不直接学习 SLAM、Nav2、任务分配或 MAC | 已确认；实现待完成 |
| 协议可见性 | candidate/request/grant/heartbeat/critical-event 是必要机制；中枢只能使用已交付的摘要、请求和状态，不能免费读取机器人当前队列或消息价值 | P3C.5技术PASS；待用户验收 |
| 网络边界 | 调度器控制应用消息是否进入发送通道；Wi-Fi DCF/EDCA、排队、竞争、重传和交付仍由网络模型负责 | 已确认；实现待完成 |
| 实验顺序 | 先做应用负载/控制开销审计，再做 Wi-Fi 瓶颈测量；只有存在可测通信决策空间时才训练 RL | P3C.5技术PASS；无线标定/容量实验待后续 |
| 强基线 | task-value greedy、freshness/deadline、link-aware、SchedNet-inspired（公平适配）必须纳入同一消息接口比较 | 已确认；实现待完成 |
| 任务栈门禁 | 当前 task-stack 优化后先新增 P3A.6 重新冻结，再进入网络/RL；P3A.5 仅保留为历史证据 | 已确认；P3A.6 于2026-10-01验收通过 |
| 研究主线 | 重点是无线通信问题；机器人任务作为固定工作负载和端到端验证，论文方向由最终证据决定，不预先锁定为机器人或 MARL 论文 | 已确认 |
| RL 结论 | RL 没有超过强非学习基线也可以是有效结果，不为制造优势而改变规则或人为拥塞 | 已确认 |

教师评审记录见 [`report/20260929_teacher_research_route_review.md`](report/20260929_teacher_research_route_review.md)。
评审中的相关工作重叠判断用于收窄主张：不能把真实 Wi-Fi、异构机器人、选择性通信或实物
部署单独当作创新；最接近方法的逐项比较和负载证据仍为待完成工作。

### 0.1 P3C.5 后的路线修订（2026-10-08）

最终任务和最低实物目标不变；学习仍是集中式、部分可观测的单智能体准入策略。调整工作顺序和论证条件：

1. P3C.5协议工程范围已由用户于2026-10-08验收；旧14格的3次超时完整保留。完成返航路径预算与无路可返时的安全降级，重新冻结任务栈；不得用延长300秒、降低5秒保持或挑选补跑关闭安全/稳定性问题。
2. P4A-0先确定实际传输字节、身份/版本/源时间、分片重组和消息级交付契约。P3C.5 ledger只保存普通数据的元信息，不能单靠它恢复数据内容；新采集须保存不可变payload或可校验的内容存储引用。
3. 把P4B分为先行的P4B-0负载/位姿trace无线测量和P4B-1闭环标定验证。先用原负载测服务时间、排队、重传、信道忙和总代价，再投入完整Gazebo时钟桥接；同时尽早做P8A中的普通网卡/AP单链路测量。被动trace只支持网络负载/容量判断，不支持反事实任务收益。
4. P4A-1闭环仍是端到端任务结论的必要条件；保持ROS/system Python与ns3gym/conda进程隔离。网络trace的确定性与全栈异步重复性的验收分开，不要求仅靠相同Gazebo seed产生完全相同任务轨迹。
5. P5先运行强非学习方法。只有可测的总成本—任务权衡、非空且可执行的动作，以及强贪心难以处理的时序现象同时存在，才进入P6；无RL分支仍完成P7统计和P8双机验证。

主假设改为“在完整成功率、失败惩罚完成时间和安全约束不劣下，降低**包括控制与重传的总网络代价**”。payload bytes只作分解指标。P3C.5的新增控制已占ideal总发送CDR约32–38%，忽略它可能颠倒结论。Wi-Fi无瓶颈只有在P4B测量后才可能成为研究负结果；若任务不敏感但能节约总代价，优先完成非学习节流研究，仍不自动训练RL。

## 1. 最终目标

在机器人事先不知道地图、包含墙体和障碍物的实验室中，2–3 台移动机器人从同一个充电区域
附近出发，完成以下任务：

1. 依靠激光雷达、本地 SLAM 和 Nav2 自主探索并协同建图；
2. 依靠摄像头寻找指定物体；
3. 通过 Wi-Fi 4 与其他机器人和 AP 侧中央大脑通信；
4. 任意机器人确认目标后，把目标信息可靠传播给中央端和其他机器人；
5. 所有仍参与任务的机器人最终到达目标周围各自的安全集合位置；无故障时任务为完整完成，
   已有机器人故障时明确标记为部分完成；
6. 单次充电不足以探索整个区域，机器人必须在电量不足前返回起点充电，再继续任务。

最终工作包含 ns-3 + ROS 2/Gazebo 可重复仿真、至少 2 台真实机器人实验、固定消息语义下的
无线通信调度比较，以及任务、网络和 sim-to-real 指标分析。RL 只有在负载和瓶颈审计证明存在
长期通信决策空间时才进入实验；若强非学习方法已足够，保留该结果，不强行训练或宣称 RL 优势。

## 2. 核心研究问题和边界

建议将论文问题固定为：

> 在中央端只能看到带时延的候选摘要、请求、心跳和已交付状态，且 Wi-Fi 存在排队、竞争、
> 丢包和时效约束的条件下，如何调度固定语义的应用消息准入，使多机器人任务获得真正有用
> 的新信息，并在相同任务算法和网络资源下改善任务—通信权衡？

第一版把它建模为集中式、部分可观测的单智能体通信调度问题。动作是“准入哪个端点的哪类
候选消息”，也包括不准入普通消息；机器人数量不决定学习范式。消息内容、消息编码和机器人
SLAM/Nav2/探索/检测/电池算法保持固定。调度器不替代 Wi-Fi MAC，也不直接控制 MCS、功率、
信道或导航。

创新主张必须来自无线约束下的可检验困难和证据，不能把真实 Wi-Fi、任务收益、异构机器人、
选择性通信或实物部署中的任一项单独当作新颖性。

正式实验必须形成以下因果闭环：

```text
通信策略
  -> 实际生成或抑制消息
  -> ns-3 Wi-Fi 排队、竞争、干扰、丢包和时延
  -> 接收端获得不同且可能过期的信息
  -> 地图融合、探索分配和集合行为发生变化
  -> 任务成功率、完成时间和其他指标发生变化
```

如果 ROS 2 节点仍能绕过 ns-3 读取最新地图、位置或目标真值，实验不成立。仅在旁边运行一个
独立 ns-3 仿真并记录网络指标，也不能证明网络影响了机器人任务。

本项目的研究主张分四层，不能跨层替代：

1. **任务工程层**：P1/P2 证明探索、检测、返航、充电和集合在理想网络下正确；
2. **协议因果层**：P3 证明所有跨端信息经过同一消息语义，并且丢失、延迟、过期会产生可解释的任务后果；
3. **无线策略层**：P4–P7 证明 ns-3 Wi-Fi 指标与任务变化闭合，并比较启发式和 RL；
4. **实物层**：P8 证明真实感知、真实 UDP/Wi-Fi 和安全行为可以复用同一协议。

只有完成对应层的退出条件，论文才能使用该层的结论。历史 toy MDP、理想 gateway 和 Gazebo
真值检测分别只能支持工具链、协议和任务工程层结论，不能单独支持“Wi-Fi RL 提升任务”的主张。

## 3. 现有资产和复用决策

### 3.1 当前 ns-3 项目

本目录的 `wireless-rl` 是 5 用户抽象队列调度 MDP。它已经验证 ns3-gym、baseline、DQN、
checkpoint、GPU 和多 seed 评估链路，但没有真实 Wi-Fi 节点、数据包、传播、干扰或机器人
任务。历史 DQN 结果应保留为前期方法验证，不能外推为机器人 Wi-Fi 场景的结果。下一阶段的
主要瓶颈是环境建模，不是继续在 toy MDP 上堆算法。

### 3.2 ROS 2 多机器人项目

已有任务项目位于：

```text
/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
```

源码已经包含 Gazebo 中 1–4 台 TurtleBot3、每台机器人的激光雷达、SLAM Toolbox、Nav2、
局部地图合并、总部式 frontier 选择和 `NavigateToPose` 目标分配，以及相应 launch、世界、
模型和参数。

研究决策是复用它作为任务层和高保真验证平台，不从零重写机器人。优先保留 Gazebo、机器人
模型、SLAM、Nav2、世界和 frontier 方法，只在必要边界新增任务评估、能量、目标检测、显式
通信和实验控制。

截至 2026-09-29，P1/P2 已完成并验收；P3A 和 P3A.5 的 gateway、旁路审计、固定矩阵和强制
充电回归仅作为历史证据保留。当前 HEAD 尚未通过新增的 P3A.6 重新冻结门禁；在该门禁完成前，
不能把 task-stack 称为网络/RL 基线。P3B 中的固定应用层 fault transport、协议矩阵、消息
账本和 stale-state 安全语义已由用户验收；Gazebo fault-mode 完整任务矩阵和 ns-3 coupling
没有混入 P3B 的完成声明，重新标记为 P3B.5。P3C 将专门负责 gateway 通信指标和默认可视化，
之后才进入 P4A 的 ns-3 数据包/时间桥接。详见 `report/20260928_p3b.md`、
`report/20260928_p3b5_plan.md` 和 `report/20260928_p3c_plan.md`。
仍有以下限制：

- 同机 ROS 2/DDS 仍是理想网络，没有 Wi-Fi 排队、丢包和干扰；
- P3A/P3A.5 的冻结结果是历史批次，不等于当前 HEAD 已冻结为网络实验基线；P3A.6 需在当前
  task-stack 上重跑 P2D/P3A 门禁后才可建立新的基线；
- P3B 已完成的 fault substitute 仍是应用层模型，不是 Wi-Fi 物理层或 MAC 仿真；P3B.5 要验证
  故障如何改变完整任务，P3C 要把变化实时显示并固化成指标；
- 评估器仍可读取 Gazebo 真值；控制链中的地图、odom、TF、检测和 Nav2 命令已经过 gateway，
  机器人全局代价图也只消费 gateway 交付的融合地图；
- 电池/返航/充电和 P2D 跨场景完整基线已形成理想通信闭环，但通信量、AoI 和曲线可视化仍未进入闭环；
- 在线地图合并依赖已对齐的地图 origin，不处理一般未知初始位姿配准；
- 多 Nav2 栈冷启动仍可能发生基础设施超时，必须与任务失败分开记录；
- 工程包含 fork 的 Nav2/SLAM 和较多历史配置，不应先做无关的大规模清理。

初始位置共同已知是可接受的简化。实物可利用共同充电区建立公共初始坐标系；论文应声明不
处理任意未知初始位姿下的地图配准。

## 4. 目标系统

```text
Robot 1..N
  camera -> local detector
  lidar  -> local SLAM -> local map
  odom, battery, task state
             |
             v
      candidate message queue
             |
      communication decision
             |
             v
      Wi-Fi 4 / ns-3 network
             |
             v
AP / headquarters
  received-information store
  global map merge
  exploration/task allocation
  communication policy or coordinator
             |
        Wi-Fi downlink
             |
             v
       robot-local Nav2
```

机器人本地必须保留传感器、SLAM、局部地图、避障、Nav2、当前任务、低电量自主返航和通信
中断后的降级行为。安全控制不交给调度器；无线断开或策略异常时仍要避免碰撞和电池耗尽。

协议必须显式区分：

1. `candidate`：机器人在本地生成的低开销候选摘要；
2. `request`：机器人请求某类候选获得发送机会，或报告关键事件；
3. `grant`：中央为端点/消息类型授予短期准入机会或预算；
4. `heartbeat`：最低限度的状态和可达性通告；
5. `critical-event`：目标确认、返航、急停等受保护事件，具有最大等待和有限重试规则。

这些控制消息本身的字节、排队、时延、丢失和重试必须进入通信账本。中央端只能使用已经
成功送达的摘要、请求、心跳和消息，例如最后接收的机器人位置、电量、地图版本和检测结果；
不能读取机器人当前隐藏队列或消息价值。训练时可以采用带完整状态的 centralized critic 作为
明确标注的训练特权，但执行策略只能使用可部署的历史观测，且这不改变单智能体范式。

## 5. 任务状态机和完成条件

```text
EXPLORE -> FOUND_UNCONFIRMED -> FOUND -> RALLY -> COMPLETE
                                             \-> PARTIAL_COMPLETE（已有机器人故障）
```

- `EXPLORE`：建图、分工探索并按需充电；
- `FOUND_UNCONFIRMED`：单帧或低置信度检测，尚不触发集合；
- `FOUND`：连续多帧、高置信度或其他规则确认目标；
- `RALLY`：目标位置已可靠送达，中央端给每台机器人分配独立集合位姿；
- `COMPLETE`：所有要求参与的机器人到达对应集合区域并稳定停留；
- `PARTIAL_COMPLETE`：至少一台机器人已被明确隔离，剩余要求参与的机器人到达对应集合区域并稳定停留；
  它是终态和任务结果类别，但 `success=true` 仍只保留给完整 `COMPLETE`；
- 达到 episode 最大时长仍未完成记为失败，不能忽略该样本。

初始完成条件可设为：所有机器人进入目标周围不同的无碰撞集合位置，位置误差小于约定阈值、
速度低于阈值并连续保持 5 秒。目标周围生成多个环形或扇形 staging poses，不能命令所有
机器人驶向同一个坐标。

从 P2B 起固定第一版判定：每台要求参与的机器人与其独立集合位姿的平面误差不超过
0.35 m、线速度不超过 0.05 m/s、角速度不超过 0.10 rad/s，并且全体条件连续保持 5 个仿真
秒。任何机器人离开容差区或重新运动都会重置全体保持计时。无故障时要求参与的机器人集合在
episode 开始时固定；故障必须通过显式 `/robot_failure` 事件进入评估器。故障后集合可以缩小，
但不能通过静默丢弃机器人获得完整成功；评估器必须同时输出 `required_robot_names`、
`failed_robots`、`completion_status` 和 `partial_completion`。

`episode_start` 定义为所有 Nav2 栈就绪且任务控制开始的仿真时刻；`FOUND` 是目标本地确认
时刻；`RALLY` 是中央端收到有效目标信息并成功生成全部集合任务的时刻；`COMPLETE` 是上述
全体保持条件满足的时刻。最终任务的 `success=true` 只对应 `COMPLETE`。P1C 的 90% 覆盖率
是探索能力基准，P2 及后续任务可以在较低覆盖率发现目标，不能把 90% 覆盖当作任务成功的
额外条件或用 `FOUND` 代替最终成功。

需要明确：找到目标但消息未送达时不能进入 `RALLY`；低电量机器人必要时先充电再集合；目标
周围必须有足够可达空间；“陌生环境”只表示机器人不知道，评估器仍可使用真值。

## 6. 探索、地图和目标检测

### 6.1 探索与地图

第一版保持现有 frontier + Nav2，不同时研究新路径规划算法。中央端只使用收到的地图更新和
位置分配不同 frontier，机器人本地负责实际规划和避障。

需要新增独立任务评估器，以已知真值地图计算：达到 75%、80%、90%、95% 正确覆盖率所需时间、
最终覆盖率、地图 IoU/占据栅格准确率、路径长度、探索重叠、Nav2 失败和碰撞。

第一版可以假设地图初始坐标已对齐。只有网络闭环和评估稳定后，再决定是否改进地图增量、
压缩或配准。

### 6.2 目标检测

视觉不是第一阶段研究变量，建议分两步：

1. 仿真 MVP 使用摄像头视场、距离、遮挡和连续可见帧定义检测事件，可加入定位噪声、漏检率
   和误报率；
2. 稳定后替换为 Gazebo RGB/RGB-D 图像上的固定检测器，实物使用相同类别和流程。

普通单目 RGB 分类不能直接给出可导航目标位置。实物 MVP 优先使用 AprilTag、ArUco 或
RGB-D；若使用普通物体检测，还必须实现距离估计和 camera-to-map 坐标变换。为处理误报，
使用连续帧、置信度阈值或第二次观察确认。

## 7. 电量和充电

2026-10-08 用户授权独立 P2C.1 补强。当前候选在原能量单位中比较完整栅格 Dijkstra、A* 与充电接触区反向多源缓存，并验证可见短腿优化；不将组件CPU时间当任务收益。预算包络声明路径偏离系数、标称速度、恢复时间和反应余量，运行时超过包络必须停止/明确失败；未知或失路不获得几何替代预算。地图/轨迹突变、无限阻塞或失控执行器仍不属于一般最坏安全保证，实物需独立标定/验证。原300秒任务、5秒原生保持及已有源TTL不变。

不要硬编码“走固定距离后返航”，从可校准的简单模型开始：

```text
E_next = E
         - c_move * traveled_distance
         - c_idle * elapsed_time
         - c_tx * transmitted_bytes
```

若测量表明通信能耗相对移动可忽略，可在消融中令 `c_tx = 0`。本地返航条件为：

```text
remaining_energy <= estimated_energy_to_home + safety_margin
```

这是硬安全约束，不由 RL 覆盖。MVP 中充电区是起点附近区域，机器人进入并静止固定时间后
恢复满电，不必先实现机械对接。

2026-10-08源码复核：本地触发与提前充电回调、中央探索预算仍含欧氏距离×固定path factor；实际返航导航使用已知自由地图，并不等于触发预算已使用完整地图路径。原定P3B/P4前关闭的要求**未满足**，不得由零事故样本替代。构造反例及原源码SHA见本次评审。

进入P4A-1闭环、P5正式比较前必须补齐：按机器人本地已知地图估计到**任一有效充电接触区的完整路径**（不能只计首个短腿），计入路径/时间、取消与恢复等待、状态年龄和余量；中央去程准入也使用其已交付地图上的对应返航预算，不读取本地隐藏地图。未知或不可达不能回退为直线可行，须停止新增运动、执行有界安全等待/明确失败，并记录触发原因、路线/地图版本、预算、实际返航消耗及预测误差。最短路径加标称速度仍不是最坏情况上界，保守余量要有声明的适用条件和验证。修复改变任务算法，必须新提交、新批次重验完整理想十格、强制充电、真实断网返航和失路/耗尽反例，再冻结；历史P3B.5/P3C.5结果不回填。

必须定义：充电后保留地图和任务状态；掉线时仍按本地信息返航；低电量与 `RALLY` 冲突时
先保证安全；充电位是否支持并行；无法返航、耗尽电量和路径失败如何计为任务失败。

返航和集合必然重走旧区域。因此分别报告搜索期重复覆盖和返航/集合的必要重复移动，不能用
一个数字错误惩罚充电机制。

## 8. 显式通信消息

不把完整 ROS 2 DDS 图直接穿过 ns-3。机器人内部继续使用 ROS 2；跨机器人/AP 的消息经过
明确的应用层出口。

| 消息 | 相对大小 | 时效要求 | 初始可靠性策略 |
|---|---:|---:|---|
| heartbeat、位姿、电量、任务状态 | 小 | 高 | 周期发送，允许旧包丢失 |
| frontier 摘要 | 小 | 中 | best effort |
| 地图增量或局部子图 | 中/大 | 中 | 新版本取代旧版本 |
| 融合地图或相关区域回传 | 中/大 | 中 | 新版本取代旧版本 |
| 目标检测结果 | 小 | 极高 | 序号、ACK、重传 |
| 检测缩略图或特征 | 中 | 高 | 策略可选 |
| 探索目标、返航/集合命令 | 小 | 极高 | 序号、ACK、重传 |
| 任务能量预算充电请求 | 小 | 10 s TTL | 序号、ACK、重传、局部去重/能量确认 |

每个消息至少包含类型、发送者、序号、生成时间、任务阶段、payload 长度和 payload。正式账本还要
区分 `source_time`、`enqueue_time`、`admit_time`、`tx_time`、`delivery_time`、`drop_time`、
`message_id` 和尝试次数，不能用 gateway 回调时刻代替传感器生成时刻。过期地图更新应在发送前或队列中
丢弃，避免继续占用信道；检测事件要同时记录本地确认、gateway 交付和中央消费三个时刻。

仿真和实物尽量复用同一消息语义：仿真由 ns-3 决定交付，实物使用真实 UDP/Wi-Fi；接收端
ROS 节点只消费成功交付的消息。

## 9. ns-3 Wi-Fi 4 场景和耦合

MVP 配置：

- 1 个 802.11n AP，2 个 STA，稳定后增加第 3 个；
- 20 MHz，固定 MCS 起步，之后再评估速率控制；
- SpectrumWifiPhy 和基础设施模式；
- 机器人间消息先通过 AP 转发；
- 一个同信道干扰 BSS 或可控背景 UDP 流；
- 从 Gazebo 同步机器人位置到 ns-3 mobility model；
- 用距离、穿墙和必要的衰落模型近似实验室；
- 记录 MAC 排队、重传、信道忙比例、airtime、交付和端到端时延。

初始 RL 只控制应用消息是否进入网络，802.11 DCF 仍负责实际竞争。不要一开始同时控制 MCS、
发射功率、信道、压缩率和 MAC 参数。

耦合顺序：

1. P3B 用确定性的固定 delay/loss 队列验证序号、TTL、重复、乱序、ACK、重传和基础安全降级；
2. P3B.5 在同一替身上运行完整 Gazebo fault-mode 任务矩阵，验证 freshness、保持/等待、单机故障
   隔离、`PARTIAL_COMPLETE` 和故障下任务指标；
3. P3C 从 gateway ledger 建立默认可视化和实时通信曲线，先证明指标守恒、时间对齐和
   ideal/fault 可比较，再进入 ns-3；
4. P4A-0用固定canonical输入、显式独立RNG streams和seed对账应用消息与网络分片/重组、发送、交付、过期；同一输入网络事件账本必须完全一致。固定序列化和payload内容哈希；接收端只能在完整消息成功重组且源TTL有效后回调，禁止从仍存活的ROS对象读取“最新值”。
5. P4B-0在冻结的原负载、位姿和协议成本下先建立802.11n AP+2/3 STA trace试验，明确PHY/MAC/传播/墙损耗/背景流来源；尽早做普通Wi-Fi单链路测量。当前ns-3 3.40的Wi-Fi-only同信道试验可从YansWifiPhy起步，只有频率相关或混合技术干扰才需要SpectrumWifiPhy；不为本项目升级整个环境。
6. 关闭返航安全缺口后，P4A-1冻结桥接与因果推进协议，再用固定窗/lock-step接入Gazebo。窗口Δ、源时间量化、可接收边界、背压和clock/message ACK须先声明并做敏感性验证。原始异步ROS任务的重复轨迹按独立重复实验报告变异；只对固定输入网络重放承诺逐事件一致。wall-clock超时标记为基础设施/耦合失败，不能变成仿真传输时延。
7. P4B-1完成独立位置/干扰条件的标定验证、闭环通信故障梯度和逐层对账。无实测只称合成敏感性；不得为制造RL优势任意加流量。然后进入P5强基线与准入决策审计。
8. TapBridge、network namespace 和 DDS-over-ns-3 仅作为后期扩展。

必须解决 Gazebo、ROS 2、ns-3 和训练循环的时间同步。优先采用固定时间窗或 lock-step：收集
候选消息、推进网络、交付结果，再推进任务。wall-clock 实时联调可以演示，但不能默认具有
正式实验所需的确定性。

## 10. 强化学习问题

### 10.1 动作

第一版保持离散动作，便于复用 DQN，但不能把两机器人和单向上行硬编码成最终接口。动作表示
“本决策窗准入哪个 endpoint 的哪类候选消息”，候选至少覆盖机器人上行状态、地图、检测，
以及中央下行融合地图和任务命令。两台机器人可从以下概念集合开始：

```text
0: 不准入普通消息（受保护 heartbeat/critical-event 仍遵守协议上限）
per robot: uplink status / map update / detection evidence
per robot: downlink fused-map update / task command
```

最终最小动作集合在 P5 根据真实候选队列和瓶颈测量冻结，不为“动作更多”保留没有实际消息的
空动作。当前P3C.5普通队列只有map/pose/TF上行；AP本机融合地图下行当前直接准入。已确认检测、电池和导航属于受保护路径，不能把它们当作可任意禁止的普通动作；额外检测证据等尚无独立候选生成器，不为概念表创建空动作。双向策略须先实现真实AP本地候选/准入并计费，再进入学习。

关键安全消息具有强制准入或最大本地准入等待，避免RL永久压制目标发现、返航或急停；这不保证无线断开时的交付。固定有限重试、TTL/deadline和本地降级始终优先；RL可以决定提前发送，但不能越过deadline。2 机器人和 3 机器人使用同一生成规则但
分别训练输出维度匹配的 checkpoint，不为跨机器人数量泛化提前引入可变规模网络。只有需要
同周期多消息、连续压缩率或联合动作时，才引入 PPO/MultiDiscrete。

### 10.2 观测

观测必须严格按中央真实可得的信息构造，不能把机器人当前队列和消息价值作为免费输入。

- AP 已知的机器人最后位置、电量和任务状态；
- 每类信息 AoI；
- 最近收到的 candidate/request/heartbeat 摘要及其年龄、请求状态和 grant 状态；
- AP 已知的上行/下行待发送消息类型、endpoint、大小、生成时间和队列摘要；机器人未交付的
  隐藏队列必须表示为未知或仅以最近摘要表示；
- 最近已交付地图的已知格增量、地图版本和frontier数量；不是evaluator的真值正确覆盖率；
- 机器人是否探索、返航、充电或集合；
- 最近投递率、时延、重传、信道忙比例和链路质量；
- 最近成功通信时间。

输入必须来自可部署测量，训练全局状态和执行观测要明确分开。AP本机发送队列可直接观察；远端实时MAC/应用队列仍不可直接读取。STA上报RSSI、重传和忙时等信息须记录采样时刻、交付年龄及上报成本；离线全局PHY/MAC counters不能免费成为执行观测。

当前P3C.5 candidate只有类型、版本、大小、源时间/截止、端点与任务阶段，不含未交付地图的真实新信息量。task-value baseline必须从这些已收到字段和AP旧地图预测价值，不能先读被拒绝payload或真值再决定准入。若增添本地gain摘要，须作为显式付费协议扩展预先冻结、复查可见性/负载，不能事后免费添加。训练reward可用离线真值，但不得经观测或摘要泄漏给执行策略。

### 10.3 奖励

```text
+ unique coverage increment
+ first confirmed detection
+ first successful delivery of confirmed detection
+ newly arrived robot near target
+ terminal mission success
- elapsed time
- transmitted bytes or airtime
- expired information
- avoidable exploration overlap
- collision events
```

能量安全作为硬约束。奖励只用于训练，论文必须报告真实任务和网络指标，不能用 reward 代替
结论。历史 5 用户 toy MDP 的 checkpoint 不迁移到任务网络，也不作为新环境的 warm start；新策略
从消息队列和网络账本重新定义观测、动作与奖励。

最小顺序是：先实现 AP 侧中央离散通信策略；检查它是否依赖不可部署全局信息；如需机器人
本地决策，再使用共享 actor、本地观测和 centralized training。MAPPO、复杂多智能体通信和
直接 D2D 都是扩展。实物机器人只做推理，不计划在线训练。

## 11. Baselines 和实验公平性

至少包括以下同接口、同消息语义/生成规则、同任务栈和同控制协议参数的策略；实际控制包数和代价按各策略真实行为计入，并不强求相同：

- no communication；
- historical direct-ideal（仅 P1C 历史探索上界）；`zero-loss finite-rate`（公平 gateway 基线）；
- always send；
- fixed-period send；
- random；
- event-triggered：变化超过阈值才发；
- **task-value greedy**：按预计对任务决策的边际价值与资源代价排序；
- **freshness/deadline**：按 AoI、TTL 和截止时间优先级排序；
- **link-aware**：把交付概率/预计 airtime 与任务价值联合排序；
- **SchedNet-inspired**：借鉴发送者优先级/共享预算思想，但适配本项目固定消息语义和真实
  candidate/request/grant 接口；不能声称复现原论文，也不能使用本项目不可得的信息；
- 只有在前述审计证明存在长期时序收益后，才加入集中式 DQN 或其他 RL。

所有策略共享机器人、探索、Nav2、检测、电池、地图和 Wi-Fi 参数，只改变通信决策。训练、
validation 和 held-out test 场景/seeds 必须独立。每个策略使用相同地图、目标、出生点、电池、
干扰和 seed，并用新进程或已证明完整的 reset 运行。

`zero-loss finite-rate` 和 `oracle unlimited` 必须分开命名。前者经过与其他策略相同的消息生成、
序列化、gateway、接收信息存储和本地命令适配器，只把网络传输设为零丢包、零附加时延，但保留真实
候选生成频率和限频；后者只作上界，不用于与通信策略的公平比较。不得把有限生成率误写成网络限制，
也不得恢复旧 ROS 直连作为任一种 ideal。
`full outage`表示跨端消息全部不交付，只保留本地安全，是故障压力下界。
`no ordinary admission`表示不准入普通消息，但仍执行同协议的heartbeat/critical/ACK规则，是策略基线；不得把它误称为完全无通信。协议开/关另作架构消融，不纳入同协议TDI或主策略比较。

在正式比较前冻结地图/目标/电池/干扰场景、训练/验证/测试划分、所有 seed 族和 episode
上限。Gazebo、场景、网络和策略随机数使用分开的显式 seed；策略之间使用相同测试元组做
配对比较。若 Wi-Fi 测量表明现实负载下网络不是瓶颈，不得通过不现实流量制造 RL 优势：先
报告该结果，再只使用可由地图增量、检测证据或实测背景流解释的负载。

P2D 的三个场景是完整任务集成门，不是跨场景性能排名；走廊使用 45 初始能量是可行性配置，
不能和 lab/rooms 的 40 直接比较完成时间。正式通信比较必须把能量档案作为场景因素固定，并保留
energy-40 的失败 stress 结果。目标发现者必须进入结果字段；现有 P2A 三轮都由 `tb1` 发现，只能
证明当前固定目标/出生排列。P5 起至少加入能让 `tb2` 或 `tb3` 发现目标的目标/出生排列，或按
`detecting_robot` 分层报告，否则无法评估多发送者竞争。

P5 还必须预注册一条主假设和一个主终点，避免同时为成功率、时间、字节、AoI 和重复探索调参。
在此之前必须完成应用负载与协议控制开销审计，以及合理负载下的 Wi-Fi 瓶颈测量；不允许用
不现实流量制造 RL 优势。
主终点为“在完整成功率、失败惩罚完成时间和安全不劣的约束下，降低总网络代价”。P5前必须冻结成功率和时间非劣界、安全准入条件、一个主成本单位及样本精度预算；不能事后挑payload、airtime或J中最显著的一个。payload/CDR/airtime/J、AoI、时延和重复探索分别报告，不混加单位。无网络测量时只报告应用成本；实际P4B测得任务对合理Wi-Fi负载不敏感时才保留无线负结果，不扩展动作空间制造显著性。

固定生成规则不等于固定实现后的消息序列：闭环任务轨迹不同会产生不同消息。固定trace公平比较只能检验网络行为，策略任务收益必须由因果闭环验证。被动重放旧attempt时，不能同时把旧应用重试作为外部流量、又让新协议重试一次；重试归属必须在trace契约中声明。

## 12. 正式指标

### 12.1 任务

- `success_rate`：在超时和安全约束内完成的比例；
- `completion_time`：从释放到全部机器人稳定到达集合点；
- `time_to_detect`、`time_to_inform`、`time_to_rally`；
- `coverage_at_detection`、最终覆盖率和地图准确率；
- 路径长度、充电次数、充电等待和最低剩余电量；
- Nav2 失败、无法返航、电量耗尽和碰撞。

先比较 success rate，再比较 completion time。不能只统计成功 episode 的平均时间。
`time_to_detect` 从 `episode_start` 到本地确认；`time_to_inform` 从本地确认到中央成功接收；
`time_to_rally` 从 `episode_start` 到进入 `RALLY`；`completion_time` 从 `episode_start` 到
`COMPLETE`。固定horizon H下使用失败惩罚完成时间：成功取min(completion_time,H)，任何FAILED/PARTIAL/timeout取H；所有原始运行都进入均值和配对差。早期任务失败是无法再成功的吸收结果，不能在失败时刻按独立右删失处理，否则会奖励快速失败。若用生存形式，报告成功累计发生概率F_success(t)和积分∫[0,H](1−F_success(t))dt，与上述惩罚均值一致；基础设施失败单列可靠性及敏感性分析。只有成功样本的时间均值作为次要描述。当前单对`rmst_300_delta_sec`是这个300秒惩罚时间的贡献，不是一对数据即可估计总体生存曲线。

### 12.2 重复探索

按固定分辨率建立每台机器人搜索阶段访问 mask：

```text
overlap_ratio = (sum_i |visited_i| - |union_i visited_i|)
                / max(1, |union_i visited_i|)
```

搜索、返航、充电和集合阶段分别统计。按固定距离或仿真时间采样，避免指标随 ROS 发布频率
变化。

### 12.2A P3C gateway 可视化指标

P3C 的通信监控必须直接来自 gateway ledger/metrics，而不是来自 GUI 刷新次数或 ROS topic
回调次数。按固定 1 秒仿真时间窗，同时保存 episode 累计值，至少输出：

| 指标组 | 指标 |
|---|---|
| 负载与交付 | generated/admitted/attempted/delivered messages 和 bytes、goodput、offered throughput |
| 故障 | loss/PDR、TTL expired、queue overflow、duplicate、reorder、retry exhausted |
| 时延 | queue wait、admit→tx、tx→delivery、source→delivery 的 mean/p50/p95/p99/max |
| 新鲜度 | 每类消息 AoI mean/p95/max、fresh-state ratio、stale-state duration |
| 任务耦合 | detection confirm→delivered→consumed、命令 deadline success/abort、任务阶段和故障事件、ideal/fault 的 `task_degradation_index (TDI)` |

每个点必须带 `sim_time`、direction、message_type、sender、recipient、seed、mission_mode 和
fault configuration。面板默认打开但只读；关闭 GUI 后仍生成相同 CSV/JSON。P3C 的曲线至少
包括上下行吞吐/PDR/丢包、p95 时延、AoI/队列深度和任务阶段时间轴，并支持同 seed 的 ideal
与 fault 叠加。

`TDI` 只纳入 ideal 配对为 `COMPLETE` 的 episode：fault 为 `COMPLETE` 时为 0，
`PARTIAL_COMPLETE` 时为 `1 - healthy_required_robot_count / required_robot_count`，失败/超时/安全终止时为 1。
同时报告完成时间、覆盖率、电量、碰撞、AoI 和时延的增量；TDI 是任务退化摘要，不能替代 packet PDR。

P3C 的可视化验收条件是：生成→准入→发送→交付/丢弃的消息数和字节逐类守恒；曲线使用仿真
时间；GUI 与 headless 结果一致；可从曲线定位“哪类消息先退化、何时超过 TTL、任务何时从
COMPLETE 变为 PARTIAL_COMPLETE/FAILED”。可视化节点不得发布任务控制、导航或电池命令。

### 12.3 碰撞

使用 Gazebo contact sensor 或机器人/障碍物最小距离。连续接触在冷却窗口内只算一个事件，
同时记录持续时间，避免每 timestep 重复计数。

### 12.4 通信和信息时效

- 应用层生成、准入发送、成功交付和过期丢弃字节；
- payload bytes 与 MAC/PHY airtime 分开；
- PDR、吞吐、重传、排队时延和端到端时延；
- 每类信息 mean/p95/max AoI；
- `AoI(t) = t - source_time(latest_delivered_information)`；同时报告 `delivery_time-source_time`
  和 `delivery_time-admit_time`，不能用 gateway 回调时刻重置 AoI；
- 地图、位姿、检测和命令使用各自过期阈值。

总成本必须含data、candidate/request/grant/heartbeat/critical、应用ACK、应用重试和真实MAC重传；逐层列出字节，防止重复计费。P3C.5的total attempted envelope CDR是应用代理，尚无IP/UDP/DDS/MAC/PHY占用；`8*CDR_bytes/1e6`只能是条件系数，任务电量也不是焦耳。

P4B默认候选主成本为全网各radio的真实TX持续时间之和A_tx，包括控制帧、前导码和重传，按唯一物理发送区间计量，不能用每个MPDU回调重复累加聚合PPDU时长。并发radio的TX之和可大于任务时长；另报固定观察点TX/RX/CCA_BUSY区间并集的busy比例，不把它当A_tx。硬件难以可靠测A_tx时，应在正式比较前改选可测的总wire bytes并明确限制。射频/网卡能量须基于校准的TX/RX/idle功耗和驻留时间或实测电量，不能将发射RF功率或任务能量单位直接替换为整机radio joules。

任务失败时通信只统计真实暴露时间，不虚构到H的尾部流量。低成本但失败的策略不能判优：先过成功/时间/安全约束，再比较总代价，同时报告按真实仿真时间的成本率、各阶段成本和受保护消息的不可消除成本。不能只选成功episode比较代价。

### 12.5 实验完整性与统计

- 每个启动尝试都记录。`episode_start` 前的 spawn/Nav2/进程故障标记为
  `infrastructure_failure`，允许修复后在相同元组重跑，但原失败仍进入基础设施可靠性统计；
- `episode_start` 后的 timeout、掉线、规划失败、电量耗尽、碰撞或进程异常都是任务失败，
  不得用补跑成功样本替换；
- 正式批次固定 Git commit、配置哈希、场景清单和 seed 清单，中途改代码后必须开新批次；
- 主比较至少使用 20 个互相独立、策略间配对的 held-out episode，三个主要 world 各至少 6 个；
  推荐 24 个（每个 world 8 个）。先报告 success rate 的
  95% Wilson 区间，再报告配对 bootstrap 的 RMST/通信指标差值区间。若区间不足以支持结论，
  先按预期差异和配对相关性做 power/precision 计算；若区间仍不足则增加样本或明确报告不确定，
  而不是把 20/24 当成充分或挑 seed；
- 工程 seed `101/202/303` 只用于 P1/P2/P3 验收，视为开发/集成门，不是最终论文测试集。P5 前必须
  生成不可改的 train/validation/held-out manifest，按 world、目标、能量和干扰分层，并记录 Git
  commit、工作树 dirty 状态、world/参数/协议哈希和 ROS/Gazebo/ns-3 版本。
- DQN 工程验收是训练、validation 选模和 held-out 测试链路正确，不把“必须胜过所有
  heuristic”写成可通过调参强行满足的工程条件。只有预注册主指标相对最强非学习 baseline
  的 95% 区间支持改善且安全指标不退化，才声称学习策略有优势；否则保留负结果。

20/24仅是覆盖下限，不保证足以证实高成功率或非劣。独立单元是预冻结场景/seed元组，重复运行嵌套在元组内；共享ideal参考的多个fault pair不能重复算独立样本。策略顺序在每元组内预先随机/平衡，固定CPU/版本/启动/reset规则，按元组/物理场景配对或分簇统计。有限样本零接触不是零风险认证；接受何种风险上界和非劣界须在看正式结果前确定。P3B.5五物理簇的描述性CI不替代该设计。101/202/303、707、809及本次读过的场景均已暴露，不再称未见测试。

非劣必须由成功率差/惩罚时间差的预声明方向置信界满足δ证明，“差异不显著”或p>0.05不证明非劣。安全风险上界和成本改善也须有支持所需精度的样本；采用何种配对/分簇估计、置信水平和多重比较顺序在正式运行前冻结。

## 13. 仿真到实物

仿真和实物复用任务消息、序号、时间戳、ACK 和过期规则：

```text
simulation: gateway -> ns-3 Wi-Fi -> gateway
hardware:   gateway -> UDP/real Wi-Fi -> gateway
```

机器人内部 ROS 2 话题留在本机，跨机器通信不依赖完整 DDS 图。

OpenWiFi 可作为 Wi-Fi 4 AP 或一个受控 STA，但 MVP 不要求所有节点都使用 SDR。顺序是普通
802.11n 网卡跑通 1 robot + AP、再跑 2 robots、然后替换 AP 或一个 STA 为 OpenWiFi，只有
稳定性和硬件数量允许时才扩展。

实物需要机器人和 AP 时钟同步，并保留序号校验乱序和丢包。先用 chrony/NTP，只有精度不足
时才增加 PTP。

在真实实验室采集多个位置的 RSSI、MCS、PER、吞吐、时延、重传和干扰，再用部分位置校准 ns-3 的
距离损耗、穿墙、衰落和背景流，并用未参与拟合的位置验证。若没有实测校准，只能称为合成网络
敏感性实验，不能写成 sim-to-real 无线结论；即使有校准，也要分别报告网络分布误差和任务差异。

## 14. 主要风险

### Wi-Fi 不是瓶颈

2–3 台机器人只发送低频位置和一次目标事件时，Wi-Fi 4 很可能足够，RL 无事可做。应测量并
合理引入地图增量、frontier、检测证据和真实背景干扰，不能为制造优势使用不现实拥塞。

### 仿真旁路或真值泄漏

中央不得直订阅机器人原始地图/odom，执行策略不得读取目标真值。所有跨端信息只经 gateway。

### 时间不同步和不可复现

明确主时钟或固定步进协议；实时联调不默认等价于确定性正式实验。

### 奖励漏洞

RL 可能通过停止发送、停止探索、牺牲某台机器人或拖延来减少惩罚。使用超时失败、终局奖励、
硬安全约束和逐项指标审计，不能只观察总 reward。

### 全栈训练速度

GPU 只加速神经网络，Gazebo、Nav2、SLAM 和大部分 ns-3 仍受 CPU 限制。P3B/P4A runner 必须
记录 wall time、sim time、RTF、消息吞吐和资源峰值；先用这些数据决定训练预算。只有采样速度
被证明不足时，才新增简化网格或 trace-based 预训练，并在高保真 ROS 2 + ns-3 上做最终验证。

### 接收信息过期

P3B.5/P4 必须把 generation time、delivery time、TTL 和消息版本带入接收状态存储。位置/TF 过期时
暂停新的中央分配并进入本地安全模式，地图过期时禁止基于旧图重规划，检测和返航/集合命令按 TTL、
ACK 和明确失败处理；机器人可以完成当前仍安全的本地目标，之后保持/停止并等待新鲜状态，不能
无限执行旧命令；只记录丢包而继续消费旧状态不能证明网络因果。P3C 要把这些 freshness 事件与
吞吐、延迟、AoI 和任务阶段画在同一仿真时间轴上。

目标检测的 raw `/target_detection` 订阅只能用于 truth/debug 和独立的过程模式，不能用于网络
`time_to_inform`、AoI 或交付率。正式网络指标必须从 gateway ledger 的
`local_confirm -> delivered -> consumed` 事件计算；DetectionProvider 输出的每个候选还必须带
`robot_id` 和 `source_time`，以区分本地观测、gateway 交付和中央消费。

### 拥堵与混杂变量

“同一起点”实现为同一充电区内互不重叠的位姿，探索时分配不同方向，充电和目标附近使用
staging poses。先固定检测器、SLAM 和 Nav2，再比较通信；新增视觉噪声、配准误差或规划策略
时做单独消融。

## 15. 一年路线和退出条件

### 月 1–2：恢复任务和真值评估

- 跑通 1、2、3 机器人 headless/GUI smoke；
- 固定世界、出生点、seed、超时和输出；
- 实现覆盖率、路径、碰撞、任务阶段和失败原因；
- 退出：2 机器人理想通信在多个固定 seed 下可重复完成基础探索。

### 月 3：完整理想通信任务

- P2B 加入目标后停止探索、不同安全集合位姿、到达/速度/连续保持判定；
- P2C 加入可校准能量、低电量本地返航、非重叠充电位和充电后恢复；
- P2D 冻结至少三个不同 world/目标/能量场景，建立完整理想通信任务基线；
- 退出：无网络退化时完成探索、发现、充电和全体集合，任务成功严格对应 `COMPLETE`。

### 月 4：显式通信边界、P3B 和 P3B.5

- 定义最小消息和 gateway，切断中央端对地图、位置、检测和 Nav2 action 的全部直连，并
  切断机器人 Nav2 对中央 `/merge_map` 的免费订阅；
- 将仿真检测事件放入发现机器人的本地候选队列，中央只消费成功交付事件；
- P3B 固定 delay/loss、TTL、版本、重复/乱序、ACK/重传和 ledger 语义；
- P3B.5 用多 world/seed、三种 mission mode 和配对 ideal 跑 Gazebo fault-mode 任务矩阵；
- 验证 stale-state 保持/等待、deadline、单机故障隔离、剩余机器人集合和 `PARTIAL_COMPLETE`；
- 退出：协议门禁与完整任务故障结果分开可审计，故障不伪造成功，安全降级动作可复现。

### 月 5：P3C/P3C.5 可视化、协议审计与 ns-3 Wi-Fi 4 准备

- P3C 默认打开 gateway 监控面板，输出吞吐、PDR、丢包、延迟、队列、重试、AoI、freshness
  和任务阶段同步曲线；GUI/headless 使用同一 metrics ledger；
- 完成 P3C.5：测量 candidate/request/grant/heartbeat/critical-event 的应用负载、控制字节、
  队列和时效分布；
- 按§0.1/§9先关闭安全缺口，完成包契约和被动无线测量，再投入闭环时钟耦合；提前采集普通Wi-Fi单链路标定数据；
- 退出：P3C 指标守恒且可视化通过；P4A固定输入网络trace可复现，包生成/准入/交付账本闭合，理想、
  无干扰和受干扰的网络指标形成解释得通的梯度；任务指标按批次统计，不要求每个 seed 人为单调。

### 月 6：强非学习 baselines 与 RL go/no-go

- 先冻结场景、四类 seed、主指标、episode horizon 和最小双向动作集合；
- 完成 task-value greedy、freshness/deadline、link-aware、SchedNet-inspired 以及既有 baseline；
- 结合 P3C.5/P4B 结果判断是否存在通信决策空间；
- 退出：同一 gateway 下脚本、CSV、基础设施/任务失败记录和统计可一键复现，并记录“训练 RL”
  或“保留非学习方法”的决定及理由。

### 月 7–8：条件式学习调度（如审计允许）

- 仅在 P3C.5/P4B 证明存在可测时序通信决策空间后，训练集中式、部分可观测 DQN；
- 检查 candidate/request/grant 协议、可部署观测和奖励漏洞；
- 仅在动作结构需要时做 PPO，不默认引入 MARL；
- 退出：validation-only 选模和 held-out 链路正确；是否胜过最强 heuristic 作为结果如实报告，
  RL 没有优势时保留负结果。

### 月 9：泛化和消融

- 至少 20 个配对 held-out episode，先报告成功率区间和 RMST，再比较通信指标；
- 改变目标、障碍、干扰、电池和传播参数；
- 消融 AoI、任务状态和信道观测；
- 退出：明确有效范围、失效条件和原因。

### 月 10：实物单机器人链路

- 恢复真实相机检测适配器，禁止使用 Gazebo 真值；
- 复用 gateway 和消息协议；
- 普通 Wi-Fi 先跑通，再接 OpenWiFi；
- 早期P4B-0已经开始的无线标定在此与真实检测/返航任务集成，不把无线参数首次拟合推迟到全部策略实验之后。

### 月 11：2 机器人实物，条件允许时 3 机器人

- 完成搜索、通知、返航充电和集合；
- 对比至少periodic与最强非学习方法；仅P6已获准且验证有效时加入RL，保留失败样本。

### 月 12：统计和论文

- 固化代码环境，完成消融、sim-to-real 差异、限制讨论和复现说明。

## 16. 最低可交付和扩展边界

一年期最低成果：

```text
2 robots
+ one charging area
+ one static target
+ Wi-Fi 4 AP/STA with measured or justified load conditions
+ explicit candidate/request/grant/heartbeat/critical-event protocol
+ strong task/network-aware non-learning baselines
+ repeatable simulation
+ two-robot hardware validation
```

集中式 RL 是条件式扩展，不是最低成果的预设交付物；是否加入最终论文由 P3C.5/P4B 负载审计
和 P5 baseline 结果决定。

以下是扩展，不应成为前期阻塞项：第 3 台实物机器人、PPO/MAPPO、直接 D2D、所有节点使用
OpenWiFi、学习式地图/图像压缩、未知初始位姿地图配准、机械自动对接充电、动态目标/障碍、
以及同时学习导航、任务分配和通信。

## 17. 后续 agent 工作规则

1. 实现前先读本文，再读 `ros2_ws/ros2-multi-robot-automap/user_guide.md`、源码和最新日期报告；
2. 不把规划描述成已经实现，不用 toy MDP 结果支撑机器人 Wi-Fi 结论；
3. 每次只推进一个可验证阶段，先建立无 RL 的正确闭环；
4. 没有测量前不增加多智能体框架、复杂 wrapper、manager 或新通信中间件；
5. 每种通信方案都检查 ROS 直连旁路和真值泄漏；
6. 每次训练、评估、baseline、消融、仿真 smoke 和实物试验，都在同一会话追加 `log.md`，
   包括失败和中断；
7. 新实验使用新日期报告，不覆盖历史报告；
8. ns-3 和 ROS 2 已位于同一 monorepo；从 `/home/zhuyulab/ns3-workspace`
   检查整体 Git 状态并保留用户改动；
9. 设计与本文冲突时，以用户最新要求、实验证据和代码为准，并同步更新本文。

2026-10-01 更新：P3A.6 用户验收通过；22c95a7 的冻结证据见 report/20261001_p3a6_freeze.md/.json。此前“当前 HEAD 尚未冻结/待完成”均为2026-09-29历史状态。现在推进 P3B.5 的应用层故障任务闭环；必要的本地安全修复须同提交重跑理想门禁，未进入 ns-3/RL。

2026-10-04 P3B.5 v55独立开发回归通过，冻结cc21503：force ideal原生COMPLETE297.3s/两机各charge1；zero ideal/fault原生COMPLETE235.6/215.7s/各总charge1；force断网fault RALLY timeout300.3s，但两机各charge1、最低8.307、零碰撞。四原始结果、账本/graph/source/AP快照在report/20261004_p3b5_charge_time_assignment_development.json保留，不回填v43原57失败，开发仍非正式验收。force ideal仅2.7s余量，名义优化不是最坏时限保证。

新正式v56协议在首次运行前改用p3b5_holdout809.world/seed809/fault28091/目标(4.4,-3.4)/3r/E45；这是交错隔断、中央开口、旋转块与柱的新拓扑，静态SDF/visual一致、十box和0.45m净空连通检查通过，尚未运行新场景。707及旧27077首次声明/暴露原样保留为历史，不能称未见测试。主矩阵27case/41unique、同提交十fixed和六安全探针、300s/.35m/.05mps/.1radps/5s、原开发fault17011和已有故障强度保持。新冻结须先检查force ideal真实native保持，再全十fixed，随后含新留出的完整主矩阵；P3B.5尚未完成，无ns3/RL。

2026-10-04 P3B.5 v56原候选FAIL，冻结3d079215caacf9e5e31866ca4db236a5cff3236c；14:55:48–15:17:15UTC自然结束，7started/7raw/0接触/0基础设施失败、7账本审计PASS，其余50格未运行。初始force ideal原生COMPLETE273.6s/各charge1、E0双格和双机真实断网返充探针通过；首个固定lab3/101在99.8s进入RALLY、300.4s timeout，2charges、最低20.8966，不能代替完整验收。只读原生诊断见tb2视线无遮挡时朝向转出90度FOV并产生检测间断，原因仍待核验。全部原始失败保留，不回填/重试/放宽300s与原生保持门限。新809/28091从未执行，可在仅开发seed修复后重新冻结控制SHA再首次暴露；初静态文件误把通用采样点标为spawn/charge，原文件保留，另以真实launch三个起点/充电点补查0.45m连通PASS，world未改。证据见report/20261004_p3b5_charge_time_lab101_failed_candidate.json。全部owned owner/观察器/master关闭后才归档，domain222未动；完整strict checker/PASS报告/图未执行，P3B.5仍待完成，无ns-3/RL。

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


2026-10-08 P2C.1 v2 两步前沿机会充电候选：v1四原始已自然关闭且FAIL保留。继续使用完整接触区路径/有界本地包络，比较由当前交付地图生成的两个不同、仍有信息量的前沿；实际完成探索且经过现有近home范围、具有当前可见安全接触短腿时，若二步完整去返预算超当前电量但可由原充电目标供给，则沿原串行gateway请求提前充电。最多检查三个同批次较高效用替代，不读取未发现目标或真值；预测不是未来动作，每次派发仍重新核验源TTL/实际body/路线/完整预算。保留原25%低电机会分支，不在初始spawn补满。每个新前瞻决定保存AP交付规划地图、两段路径/完整返航/能量模型与源龄，供只读重建。这是有界二步可行性预测启发式，非全局最优MPC/未知未来收益保证；组件和任务性能分开，充电时间及实际能量误差同样纳入门禁。尚无新任务结果。917仍未暴露，需独立v2新freeze和4开发/17正式/物理blackout门禁，不覆盖v1原失败。


2026-10-08 P2C.1 v2首个forced严格FAIL，tb1正电量失路FAILED、任务EXPLORE timeout300s；全部原始保留，未启动其余开发/正式/blackout/917。原地图复核确认最近净空逃离点位于充电断连区域；新v3只在原0.6m已知自由逃离内选择充电反向场有限点，预算/执行同源，原障碍/净空/300s/5s/TTL保持。824功能/1skip、四包build、172保护/54协议PASS，旧/新同图None/4.5624307m。待新freeze/cohort，不称任务完成。见[连通逃离组件](report/20261008_p2c_connected_escape_components.md)与[v2原失败](report/20261008_p2c_v2_failed_development.md)。


2026-10-08 P2C.1 v4补齐本地pose/TF2秒源龄与原生TF有效时间→实际SLAM source偏移、最新TF×odom重算；过期输入无有限预算或稳定充电进展，30秒有界停止/明确正能量失效。完整路径算法保持v3，原300s/5s/地图5s/余量未放宽；840功能/1skip、四包5.48s、172保护/54协议PASS，actual ROS synthetic stale-frame/disconnected皆正能量失败/零goal。v3首forced原格COMPLETE287.5s/两charge/min9.385784与269快照已保持，但为partial开发，不能替代v4新源码正式门禁。参见[本地源龄组件](report/20261008_p2c_native_pose_components.md)与[v3原格](report/20261008_p2c_v3_partial_development.md)。917未暴露；新4开发/17正式/两blackout待验证，无P4/ns3/Wi-Fi/RL。


2026-10-08 P2C.1 v4真实时序FAIL：原生源略领先/clock被丢弃导致tb2电量冻结、forced未完成；原任务/worker收尾升级保留。新v5以标准heapq有界暂存128项/原2秒，clock成熟后按源处理，不续戳/重复计费；初始无姿态先停止等待、已负担恢复不补满。每5秒native只读能量账本覆盖完整距离/时间/charge credits平衡与冻结反例，不送AP/不加流量。847功能/1skip、实际DDS先样本后clock、四包5.39s、172保护/54协议PASS；控制完整路径算法不改，待新4开发/17正式/两blackout冻结，917未暴露。见[原生时钟组件](report/20261008_p2c_native_clock_components.md)与[v4失败](report/20261008_p2c_v4_failed_development.md)。


2026-10-08 P2C.1 v6补充：v5起点姿态等待在快速odom入口错误转为充电，虽nativeCOMPLETE251.1/239live/能量PASS，强制返航证据不合格，原记录与新增reader FAIL完整保留。统一充电入口现先恢复已负担等待；实际DDS两个clock到达顺序、850功能/1skip、四包5.46s/172保护/54协议PASS。新4开发/17正式/两物理blackout待同提交冻结，917未暴露；原TTL/300s/5s保持，P3C.5已验收，无P4/ns3/Wi-Fi/RL。证据：[v6组件报告](report/20261008_p2c_charging_entry_components.md)。
