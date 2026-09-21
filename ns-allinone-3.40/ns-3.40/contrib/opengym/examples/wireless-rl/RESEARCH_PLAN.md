# 多机器人任务导向 Wi-Fi 通信研究总纲

最后更新：2026-09-17。

本文档记录本项目的长期研究目标、当前决策、实施路线、评测口径和已知风险。它是后续研究
和 agent 协作的方向性依据，不是当前代码功能清单。已经实现的行为以 `USER_GUIDE.md` 和
源码为准，实验事实以日期报告和 `log.md` 为准。

逐步落地顺序、工程产物、退出条件和当前进度见 `IMPLEMENTATION_PLAN.md`。

## 1. 最终目标

在机器人事先不知道地图、包含墙体和障碍物的实验室中，2–3 台移动机器人从同一个充电区域
附近出发，完成以下任务：

1. 依靠激光雷达、本地 SLAM 和 Nav2 自主探索并协同建图；
2. 依靠摄像头寻找指定物体；
3. 通过 Wi-Fi 4 与其他机器人和 AP 侧中央大脑通信；
4. 任意机器人确认目标后，把目标信息可靠传播给中央端和其他机器人；
5. 所有机器人最终到达目标周围各自的安全集合位置，任务才算完成；
6. 单次充电不足以探索整个区域，机器人必须在电量不足前返回起点充电，再继续任务。

最终工作同时包含 ns-3 + ROS 2/Gazebo 可重复仿真、至少 2 台真实机器人实验、强化学习通信
策略与充分 baseline 对比，以及任务、网络和 sim-to-real 指标分析。

## 2. 核心研究问题和边界

建议将论文问题固定为：

> 在受干扰、带宽和时效受限的 Wi-Fi 4 网络中，如何根据任务进展、信息新鲜度、机器人状态
> 和信道状态，学习选择发送者、发送时机和消息类型，从而提高多机器人搜索任务的成功率并
> 缩短完成时间，同时减少通信量、过期信息和无效重复探索？

创新重点是任务导向通信，不是重新发明机器人、SLAM、视觉检测器或 802.11 MAC。

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

截至 2026-09-22，P1 已建立固定 seed、批量运行、真值覆盖率、路径、碰撞和搜索重叠评估，
P2A 已建立可重复的目标确认 MVP，P2B 已完成并通过理想直达事件下的停止探索、安全集合和
稳定完成闭环，P2C 已通过本地能量、安全返航和充电恢复验收；P2D 已完成跨三个场景的
10 项完整理想任务门禁并通过用户验收；P3A 已完成零损 gateway 和旁路审计，等待用户验收。仍有以下限制：

- 同机 ROS 2/DDS 仍是理想网络，没有 Wi-Fi 排队、丢包和干扰；
- P3A 当前仍是同机零损 ideal gateway，没有 Wi-Fi 排队、丢包和干扰；这些将在 P3B/P4 引入；
- 评估器仍可读取 Gazebo 真值；控制链中的地图、odom、TF、检测和 Nav2 命令已经过 gateway，
  机器人全局代价图也只消费 gateway 交付的融合地图；
- 电池/返航/充电和 P2D 跨场景完整基线已形成理想通信闭环，但通信量和 AoI 仍未进入闭环；
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
中断后的降级行为。安全控制不交给 RL；无线断开或策略异常时仍要避免碰撞和电池耗尽。

中央端只能使用已经成功送达的信息，例如最后接收的机器人位置、电量、地图版本和检测结果。
训练时 centralized critic 可以读取完整仿真状态，但执行策略不得读取不可部署的 Gazebo 真值。

## 5. 任务状态机和完成条件

```text
EXPLORE -> FOUND_UNCONFIRMED -> FOUND -> RALLY -> COMPLETE
```

- `EXPLORE`：建图、分工探索并按需充电；
- `FOUND_UNCONFIRMED`：单帧或低置信度检测，尚不触发集合；
- `FOUND`：连续多帧、高置信度或其他规则确认目标；
- `RALLY`：目标位置已可靠送达，中央端给每台机器人分配独立集合位姿；
- `COMPLETE`：所有要求参与的机器人到达对应集合区域并稳定停留；
- 达到 episode 最大时长仍未完成记为失败，不能忽略该样本。

初始完成条件可设为：所有机器人进入目标周围不同的无碰撞集合位置，位置误差小于约定阈值、
速度低于阈值并连续保持 5 秒。目标周围生成多个环形或扇形 staging poses，不能命令所有
机器人驶向同一个坐标。

从 P2B 起固定第一版判定：每台要求参与的机器人与其独立集合位姿的平面误差不超过
0.35 m、线速度不超过 0.05 m/s、角速度不超过 0.10 rad/s，并且全体条件连续保持 5 个仿真
秒。任何机器人离开容差区或重新运动都会重置全体保持计时。要求参与的机器人集合在 episode
开始时固定，不能通过静默丢弃故障机器人获得成功。

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

每个消息至少包含类型、发送者、序号、生成时间、任务阶段、payload 长度和 payload。过期地图
更新应在发送前或队列中丢弃，避免继续占用信道。

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

1. 用固定 delay/loss 的最小消息队列验证禁用直连后任务确实随网络退化；
2. 把消息交付替换为 ns-3 Wi-Fi 数据包；
3. 正式仿真优先使用显式消息桥和固定决策间隔；
4. TapBridge、network namespace 和 DDS-over-ns-3 仅作为后期扩展。

必须解决 Gazebo、ROS 2、ns-3 和训练循环的时间同步。优先采用固定时间窗或 lock-step：收集
候选消息、推进网络、交付结果，再推进任务。wall-clock 实时联调可以演示，但不能默认具有
正式实验所需的确定性。

## 10. 强化学习问题

### 10.1 动作

第一版保持离散动作，便于复用 DQN，但不能把两机器人和单向上行硬编码成最终接口。动作表示
“本决策窗准入哪个 endpoint 的哪类候选消息”，候选至少覆盖机器人上行状态、地图、检测，
以及中央下行融合地图和任务命令。两台机器人可从以下概念集合开始：

```text
0: 本周期不发送
per robot: uplink status / map update / detection evidence
per robot: downlink fused-map update / task command
```

最终最小动作集合在 P5 根据真实候选队列和瓶颈测量冻结，不为“动作更多”保留没有实际消息的
空动作。关键安全消息具有强制发送或最大等待时间，避免 RL 永久压制目标发现、返航或急停
信息；RL 可以决定提前发送，但不能越过 deadline。2 机器人和 3 机器人使用同一生成规则但
分别训练输出维度匹配的 checkpoint，不为跨机器人数量泛化提前引入可变规模网络。只有需要
同周期多消息、连续压缩率或联合动作时，才引入 PPO/MultiDiscrete。

### 10.2 观测

- AP 已知的机器人最后位置、电量和任务状态；
- 每类信息 AoI；
- 上下行待发送消息类型、endpoint、大小、生成时间和队列长度；
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
结论。

最小顺序是：先实现 AP 侧中央离散通信策略；检查它是否依赖不可部署全局信息；如需机器人
本地决策，再使用共享 actor、本地观测和 centralized training。MAPPO、复杂多智能体通信和
直接 D2D 都是扩展。实物机器人只做推理，不计划在线训练。

## 11. Baselines 和实验公平性

至少包括：

- no communication；
- ideal/unlimited communication，作为任务上界；
- always send；
- fixed-period send；
- random；
- event-triggered：变化超过阈值才发；
- task-priority：目标/低电量优先于状态和地图；
- network-aware heuristic：信道好时发送大消息；
- DQN，动作空间确有需要时再增加 PPO。

所有策略共享机器人、探索、Nav2、检测、电池、地图和 Wi-Fi 参数，只改变通信决策。训练、
validation 和 held-out test 场景/seeds 必须独立。每个策略使用相同地图、目标、出生点、电池、
干扰和 seed，并用新进程或已证明完整的 reset 运行。

`ideal/unlimited` 也必须经过与其他策略相同的消息序列化、gateway、接收信息存储和本地命令
适配器，只把网络传输设为零丢包、零附加时延和无限准入；不得恢复旧 ROS 直连作为“ideal”。
`no communication` 表示跨端消息全部不交付，但机器人本地避障、低电量返航和已知任务继续
工作。这样 baseline 的差异只来自通信，而不是两套任务实现。

在正式比较前冻结地图/目标/电池/干扰场景、训练/验证/测试划分、所有 seed 族和 episode
上限。Gazebo、场景、网络和策略随机数使用分开的显式 seed；策略之间使用相同测试元组做
配对比较。若 Wi-Fi 测量表明现实负载下网络不是瓶颈，不得通过不现实流量制造 RL 优势：先
报告该结果，再只使用可由地图增量、检测证据或实测背景流解释的负载。

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

### 12.3 碰撞

使用 Gazebo contact sensor 或机器人/障碍物最小距离。连续接触在冷却窗口内只算一个事件，
同时记录持续时间，避免每 timestep 重复计数。

### 12.4 通信和信息时效

- 应用层生成、准入发送、成功交付和过期丢弃字节；
- payload bytes 与 MAC/PHY airtime 分开；
- PDR、吞吐、重传、排队时延和端到端时延；
- 每类信息 mean/p95/max AoI；
- `AoI(t) = t - generation_time(latest_delivered_information)`；
- 地图、位姿、检测和命令使用各自过期阈值。

### 12.5 实验完整性与统计

- 每个启动尝试都记录。`episode_start` 前的 spawn/Nav2/进程故障标记为
  `infrastructure_failure`，允许修复后在相同元组重跑，但原失败仍进入基础设施可靠性统计；
- `episode_start` 后的 timeout、掉线、规划失败、电量耗尽、碰撞或进程异常都是任务失败，
  不得用补跑成功样本替换；
- 正式批次固定 Git commit、配置哈希、场景清单和 seed 清单，中途改代码后必须开新批次；
- 主比较至少使用 20 个互相独立、策略间配对的 held-out episode；先报告 success rate 的
  95% Wilson 区间，再报告配对 bootstrap 的 RMST/通信指标差值区间。若区间不足以支持结论，
  增加样本或明确报告不确定，而不是挑 seed；
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

在真实实验室采集多个位置的 RSSI、MCS、PER、吞吐、时延、重传和干扰，再校准 ns-3 的
距离损耗、穿墙、衰落和背景流。仿真不必复制每个物理细节，但关键分布和任务退化趋势应与
实测一致。

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

GPU 只加速神经网络，Gazebo、Nav2、SLAM 和大部分 ns-3 仍受 CPU 限制。先测量 headless
episode 速度；只有采样速度被证明不足时，才新增简化网格环境或 trace-based 预训练。高保真
ROS 2 + ns-3 始终用于最终验证。

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

### 月 4：显式通信边界

- 定义最小消息和 gateway，切断中央端对地图、位置、检测和 Nav2 action 的全部直连，并
  切断机器人 Nav2 对中央 `/merge_map` 的免费订阅；
- 将仿真检测事件放入发现机器人的本地候选队列，中央只消费成功交付事件；
- 用固定 delay/loss 验证因果关系；
- 退出：零损链路复现 P2D，丢弃检测/地图/命令产生符合逻辑的任务后果，自动旁路审计通过。

### 月 5：ns-3 Wi-Fi 4

- 先用确定性时间窗接入 ns-3 数据包、移动和真实消息大小，证明重复运行及逐包账本一致；
- 再建立 AP + 2/3 STA、传播、墙损耗和同信道干扰，并用实测或公开依据固定参数；
- 退出：相同 seed 可复现，包生成/准入/交付账本闭合，理想、无干扰和受干扰的网络指标
  形成解释得通的梯度；任务指标按批次统计，不要求每个 seed 人为单调。

### 月 6：非学习 baselines

- 先冻结场景、四类 seed、主指标、episode horizon 和最小双向动作集合；
- 完成全部 baseline 和 held-out seeds 配套运行，检查现实负载下是否确有通信决策空间；
- 退出：同一 gateway 下脚本、CSV、基础设施/任务失败记录和统计可一键复现。

### 月 7–8：DQN，必要时 PPO

- 中央离散动作 DQN，检查可部署观测和奖励漏洞；
- 仅在动作结构需要时做 PPO；
- 退出：validation-only 选模和 held-out 链路正确；是否胜过 heuristic 作为结果如实报告。

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
+ Wi-Fi 4 AP/STA with realistic interference
+ explicit task messages
+ central DQN
+ strong rule-based baselines
+ repeatable simulation
+ two-robot hardware validation
```

以下是扩展，不应成为前期阻塞项：第 3 台实物机器人、PPO/MAPPO、直接 D2D、所有节点使用
OpenWiFi、学习式地图/图像压缩、未知初始位姿地图配准、机械自动对接充电、动态目标/障碍、
以及同时学习导航、任务分配和通信。

## 17. 后续 agent 工作规则

1. 实现前先读本文，再读 `USER_GUIDE.md`、源码和最新日期报告；
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
