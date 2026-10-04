# 面向多机器人任务的无线通信调度研究总纲

最后更新：2026-09-29。

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
| 协议可见性 | candidate/request/grant/heartbeat/critical-event 是必要机制；中枢只能使用已交付的摘要、请求和状态，不能免费读取机器人当前队列或消息价值 | 已确认；实现待完成 |
| 网络边界 | 调度器控制应用消息是否进入发送通道；Wi-Fi DCF/EDCA、排队、竞争、重传和交付仍由网络模型负责 | 已确认；实现待完成 |
| 实验顺序 | 先做应用负载/控制开销审计，再做 Wi-Fi 瓶颈测量；只有存在可测通信决策空间时才训练 RL | 已确认；审计待完成 |
| 强基线 | task-value greedy、freshness/deadline、link-aware、SchedNet-inspired（公平适配）必须纳入同一消息接口比较 | 已确认；实现待完成 |
| 任务栈门禁 | 当前 task-stack 优化后先新增 P3A.6 重新冻结，再进入网络/RL；P3A.5 仅保留为历史证据 | 已确认；P3A.6 于2026-10-01验收通过 |
| 研究主线 | 重点是无线通信问题；机器人任务作为固定工作负载和端到端验证，论文方向由最终证据决定，不预先锁定为机器人或 MARL 论文 | 已确认 |
| RL 结论 | RL 没有超过强非学习基线也可以是有效结果，不为制造优势而改变规则或人为拥塞 | 已确认 |

教师评审记录见 [`report/20260929_teacher_research_route_review.md`](report/20260929_teacher_research_route_review.md)。
评审中的相关工作重叠判断用于收窄主张：不能把真实 Wi-Fi、异构机器人、选择性通信或实物
部署单独当作创新；最接近方法的逐项比较和负载证据仍为待完成工作。

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

当前按欧氏距离乘固定 path factor 估算返航能耗，只能作为可行性启发式，不能宣称一般安全保证。
在 P3B/P4 前应改为本地已知地图上的保守路径代价；无可行路径时立即进入明确失败或安全降级，并
把返航估计误差和通信延迟余量单独记录。

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
4. P4A-0 用 canonical JSONL trace 对账应用生成、准入、ns-3 发送、交付和过期字节，先排除 ROS/Gazebo
   时间因素；
5. P4A-1 选择并冻结一种桥接实现（首选带 message/clock ACK、退出和背压协议的 ZMQ 或 UDP），再用
   固定决策窗或 lock-step 把 Gazebo 位姿和任务推进接入 ns-3；相同 seed 必须重复得到同一事件账本；
6. P4B 最后加入 802.11n AP/STA、传播、墙损耗和背景干扰；ideal、无干扰和受干扰只作为网络条件，
   不能为了制造 RL 优势任意加流量；
7. TapBridge、network namespace 和 DDS-over-ns-3 仅作为后期扩展。

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
空动作。关键安全消息具有强制发送或最大等待时间，避免 RL 永久压制目标发现、返航或急停
信息；RL 可以决定提前发送，但不能越过 deadline。2 机器人和 3 机器人使用同一生成规则但
分别训练输出维度匹配的 checkpoint，不为跨机器人数量泛化提前引入可变规模网络。只有需要
同周期多消息、连续压缩率或联合动作时，才引入 PPO/MultiDiscrete。

### 10.2 观测

观测必须严格按中央真实可得的信息构造，不能把机器人当前队列和消息价值作为免费输入。

- AP 已知的机器人最后位置、电量和任务状态；
- 每类信息 AoI；
- 最近收到的 candidate/request/heartbeat 摘要及其年龄、请求状态和 grant 状态；
- AP 已知的上行/下行待发送消息类型、endpoint、大小、生成时间和队列摘要；机器人未交付的
  隐藏队列必须表示为未知或仅以最近摘要表示；
- 最近覆盖率增量、地图版本和 frontier 数量；
- 机器人是否探索、返航、充电或集合；
- 最近投递率、时延、重传、信道忙比例和链路质量；
- 最近成功通信时间。

输入必须来自可部署测量，训练全局状态和执行观测要明确分开。

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

至少包括以下同接口、同消息内容、同任务栈和同控制开销的策略：

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
`no communication` 表示跨端消息全部不交付，但机器人本地避障、低电量返航和已知任务继续
工作。这样 baseline 的差异只来自通信，而不是两套任务实现。

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
建议主终点为“在 success rate、碰撞和电量安全不劣的约束下，降低应用 payload bytes/airtime”；
success rate、RMST、AoI、时延和重复探索作为次级终点。若 network-not-bottleneck 门显示任务对
合理 Wi-Fi 负载不敏感，应保留该负结果，不扩展动作空间制造显著性。

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
`COMPLETE`。失败 episode 的时间分析使用固定 horizon 的 restricted mean survival time
（RMST）或等价的删失生存分析；仅成功样本均值只能作为次要描述。

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
- 先用确定性时间窗接入 ns-3 数据包、移动和真实消息大小，证明重复运行及逐包账本一致；
- 完成 P3C.5：测量 candidate/request/grant/heartbeat/critical-event 的应用负载、控制字节、
  队列和时效分布；
- 再建立 AP + 2/3 STA、传播、墙损耗和同信道干扰，并用实测或公开依据固定参数，确认现实
  负载是否真的形成排队/过期/交付瓶颈；
- 退出：P3C 指标守恒且可视化通过；P4A 相同 seed 可复现，包生成/准入/交付账本闭合，理想、
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
- 采集无线数据校准 ns-3。

### 月 11：2 机器人实物，条件允许时 3 机器人

- 完成搜索、通知、返航充电和集合；
- 对比至少 periodic、task-priority 和 RL，并保留失败样本。

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
