# 2026-09-23 项目目标、路线和指标审查

## 审查范围和结论

本轮阅读了 `RESEARCH_PLAN.md`、`IMPLEMENTATION_PLAN.md`、无线 RL 的 `AGENTS.md`、完整
`log.md`、P1/P2/P3A 日期报告、ROS 2 `user_guide.md`，并核对了当前源码和 Git 历史。没有
启动新的 Gazebo、ROS 2 或 ns-3 仿真；这轮工作的对象是研究合同、阶段依赖和现有成功语义。

总体方向是合理的：先建立无网络退化的完整任务，再切断旁路、验证消息因果，最后接入 ns-3、
比较启发式和 RL，最后做真实感知和双机实验。P1C、P2A、P2B、P2C、P2D 已经把任务层的
主要工程风险暴露并收敛，P3A 的 gateway 也把架构边界补齐了。

当前仍不能声称“Wi-Fi RL 已经改善多机器人任务”。原因是 P3A 仍是同机零损 gateway，P3A
formal v2 运行后 HEAD 又修改了电池、协调器和路径净空，且消息时间账本、旧状态降级、真实
丢包/重传、ns-3 lock-step 和 Wi-Fi 校准都未完成。P3A 的历史结果可证明设计方向，不足以作为
当前 HEAD 的验收证据。下一步必须先在当前 task stack 上重跑 P2D/P3A 并冻结基线，不能直接
进入 P3B 或训练。

## 之前路线中合理的部分

| 部分 | 评审结论 | 依据 |
|---|---|---|
| P1A/P1B | 范围清楚，评估器只读，启动前基础设施故障与任务失败已有区分方向 | `IMPLEMENTATION_PLAN.md` P1A/P1B；P1B report |
| P1C | 90% 正确自由空间覆盖适合作为探索过程门；跨三类静态地图的零碰撞结果足以作为工程回归 | `report/20260917_p1c_optimization.md`、`p1c_generalization.md` |
| P2A | 作为可重复的检测事件 MVP 合理，但它是 Gazebo truth provider，不是视觉识别成果 | `IMPLEMENTATION_PLAN.md` P2A；`target_detector.py` |
| P2B | `COMPLETE`、独立 staging pose、速度/位置阈值和连续保持窗口定义正确 | `RESEARCH_PLAN.md` 任务状态机；P2B report |
| P2C | 本地安全返航优先于中央策略，`c_tx=0` 在字节账本出现前保持诚实 | P2C report；`battery_manager.py` |
| P2D | 作为“组件完成后再接网络”的完整理想任务集成门合理；但它是开发/集成门，不是最终统计上界 | P2D report；固定 seed 101/202/303 |
| P3A | 统一 `GatewayEnvelope`、接收状态、导航本地适配器和旁路审计是正确边界 | P3A report；`ideal_gateway.py`、`navigation_gateway.py` |

## 必须修正的高优先级问题

### 1. P3A 证据与当前代码状态不一致

P3A formal v2 来自 gateway 实现提交 `bbe8482`，之后至少有电池、协调器和净空修改（当前
HEAD 为 `cc01656`）。因此旧的 10/10 `COMPLETE` 和强制充电结果不能自动代表当前代码。
路线现在新增 P3A.5：当前 HEAD 重跑 P2D/P3A 矩阵和强制充电回归，输出 Git commit、工作树
dirty 状态、world/参数/协议哈希、ROS/Gazebo/ns-3 版本和 seed manifest，并把结果标为
`task_stack_frozen_commit`。在该门通过前，P3A 仍为“待用户验收”，P3B 不开始。

### 2. `COMPLETE` 唯一成功规则在代码中曾被绕过

`task_evaluator.py` 原先的 `episode_succeeded()` 同时接受 `coverage_reached`、`target_found`
和 `task_complete`，而且 `coverage_reached` 会被输出映射成 `COMPLETE`。`ros_smoke_test.py`
也按三种终止原因检查成功。这与 P2B 以后只有全体机器人稳定集合才算成功的研究合同冲突。

本轮已做最小修复：

- rally 模式只接受 `task_complete`；
- rally 模式不会被 coverage timer 或 target-found timer 提前结束；
- P1C 覆盖率 smoke 和 P2A target-found smoke 保留原有独立语义；
- 增加 `test_rally_mode_rejects_process_only_termination()`。

这修复的是统计语义，不替代后续独立稳定保持证明。评估器仍需在 P3B/P4A 记录实际观察到的
5 秒稳定窗口，而不是只相信 `/task_state=COMPLETE`。

还需把 `mission_mode={coverage,target,rally}` 作为一个显式实验参数冻结。当前 launch 仍把
`enable_target_detection`、`enable_rally`、`evaluation_stop_on_target_found` 和
`evaluation_stop_on_task_complete` 分开传递；P3B 前应由一个 mode 值派生这些开关，避免 smoke、
评估器和 runner 对同一 episode 得出不同成功条件。

### 3. P3B 不能只测“检测包丢失”

现有计划的 100% 丢弃检测测试是必要但不充分的最小例子。P3B 现在固定为 deterministic fault
matrix：丢包率 0/10%/100%，延迟 0/0.5/2 秒，并覆盖重复、乱序、TTL 过期、ACK、重传和消息
版本。每次 attempt 要记录：

```text
source_time, enqueue_time, admit_time, tx_time,
delivery_time or drop_time, message_id, sequence, version,
correlation_id, retry_index, drop_reason
```

检测未交付不能进入 `RALLY`；导航命令必须有 deadline、幂等 command id、最大重试次数和超时
abort；过期位置/TF 要暂停新的中央分配并进入安全降级，过期地图不得触发重规划，旧版本不能
覆盖新版本。`navigation_gateway.py` 当前等待 action result 没有完整的网络 deadline，这一项
必须在 P3B 退出前补齐。

### 4. 接收状态目前缺少 stale-state 语义

当前控制器已有电池 freshness 检查，但 gateway 交付的 map、odom、TF 在更新后没有统一年龄门禁。
如果网络中断后继续消费旧位置或旧地图，任务可能仍“正常”完成，无法把任务变化归因于网络。
P3B/P4A 必须为各消息类型冻结 TTL 和失败后果，并把 generation time 与 delivery time 分开。
`GatewayEnvelope.generation_time` 不能用 gateway 回调时刻代替传感器原始时间戳。

### 5. P4 必须先拆账本和时间，再做无线参数

P4 现在拆成：

1. **P4A-0 trace ledger**：离线候选消息 trace 的生成、准入、发送、交付、丢弃字节闭合；
2. **P4A-1 lock-step**：固定决策窗、Gazebo mobility、ns-3 时间推进和重复运行一致性；
3. **P4B Wi-Fi calibration**：802.11n AP/STA、传播、墙损耗、背景干扰和真实测量校准。

ROS 2/rclpy 使用 system Python，wireless-rl/ns3-gym 使用 `ns3gym` conda；不能因为环境差异
把两者强行放进一个 Python 进程，应通过明确的 UDP/ZMQ/文件/clock-handshake 桥接。P4A runner
还要记录 wall time、sim time、RTF、消息吞吐和 CPU/RAM 峰值，才能决定是否需要 trace/replay
训练环境。

### 6. P2D 的能量和发现者不能被误读成跨场景性能

corridors 使用 45 初始能量，是在 energy-40 返航超时后的统一可行性配置；它不能和 lab/rooms
的 40 直接比较完成时间。energy-40 失败应作为 stress evidence 保留，正式网络比较要把能量
档案作为场景因素固定。

P2A 三个正式 seed 都由 `tb1` 发现目标，当前矩阵没有证明多发送者竞争。P5 起要加入能让
`tb2`/`tb3` 发现目标的目标或出生排列，或按 `detecting_robot` 分层；P2D 现有 101/202/303
只作开发/集成门，不能充当最终 held-out 测试集。

### 7. 研究主张过多，必须预注册主终点

当前同时关注成功率、完成时间、bytes/airtime、AoI、重复探索、发送者、发送时机和消息类型，
容易出现多目标调参。P5 现在要求预注册一条主假设和一个主终点。建议主终点为：

> 在 success rate、碰撞和电量安全不劣的约束下，降低应用 payload bytes/airtime。

success rate、RMST、AoI、时延和重复探索作为次级终点。若合理消息负载下 Wi-Fi 不是瓶颈，
保留该负结果，不扩展动作空间制造 RL 优势。

### 8. 真实视觉应通过 provider 替换

当前 `target_detector.py` 是一个节点读取 `/gazebo/model_states` 中全部机器人和目标，不是
每机器人相机检测器。P8A 若同时首次接入真实视觉和网络，会产生不可定位的混杂变量。路线现在
先冻结 `DetectionProvider` 消息契约：truth provider 或离线 replay 用于 P2A/P3B/P4 的消息路径，
P8A 只替换成每机器人 camera provider；不能把 Gazebo truth 结果写成视觉 sim-to-real 结果。
当前评估器在 raw `/target_detection` 上记录 `target_found` 和 `time_to_detect`，这可用于 truth/debug
或独立的 target 过程模式；它不得作为网络 `time_to_inform`、AoI 或交付率。后者必须从 gateway
ledger 的 `local_confirm -> delivered -> consumed` 事件计算，并要求每个 DetectionProvider 候选带
`robot_id` 和 `source_time`。

### 9. 返航安全模型要声明边界

当前电池 manager 以欧氏回家距离乘固定 path factor 估算返航能耗。走廊 energy-40 的失败说明
它不是一般安全保证。P3B/P4 前应改为本地已知地图的保守路径代价；若无可行路径要立即报告明确
失败或安全降级，并记录返航估计误差、消息延迟余量和耗尽风险。共享充电器排队也应在 P8 作为
独立 stress 因素验证，不能从当前非重叠 charger 结果泛化。

### 10. 评估器还需补齐三项独立性

在 P3B/P4A 退出前补齐：

- 评估器独立重算 rally 的连续稳定保持时间，并输出 `stable_hold_observed_sec`；
- 碰撞监测 topic 必须有启动后心跳，监测未激活时记 measurement/infrastructure failure，不能把缺数据当零碰撞；
- 路径和访问 mask 按固定仿真时间或 odom 累计采样，不随 Gazebo 发布频率变化；记录采样协议和跳步数量。

## 修订后的路线

```text
P1/P2 accepted development gates
  -> P3A protocol implementation (historical matrix retained)
  -> P3A.5 current-HEAD P2D/P3A revalidation + frozen task-stack commit
  -> P3B deterministic delay/loss + stale-state/ACK/retry safety
  -> P4A-0 offline trace ledger
  -> P4A-1 lock-step ROS/Gazebo/ns-3 coupling
  -> P4B Wi-Fi 4 calibration and network-not-bottleneck gate
  -> P5 frozen manifest + non-learning baselines + preregistered endpoint
  -> P6 central DQN engineering chain (new environment, no toy checkpoint transfer)
  -> P7 held-out paired statistics and ablations
  -> P8A provider replacement + single-robot real link
  -> P8B two-robot hardware task and sim-to-real comparison
```

这里没有重新排序已经验收的 P1/P2；改变的是 P3 之后的门禁粒度和证据要求。P4B 若未能证明
通信会改变任务，最合理的结果是停止扩展 RL、报告 network-not-bottleneck，并把贡献收敛为
协议/测量/负结果，而不是人为制造拥塞。

## 本轮已修改的文件

- `RESEARCH_PLAN.md`：加入四层主张边界、zero-loss finite-rate 与 oracle unlimited 区分、消息时间账本、
  stale-state、held-out manifest、主终点、P4A 子门和校准规则。
- `IMPLEMENTATION_PLAN.md`：修正过时的 P2D 状态，新增 P3A.5，细化 P3B/P4A/P4B/P7 退出条件，
  增加 task-stack freeze、DetectionProvider 和共享充电器 stress 边界。
- `AGENTS.md`（仓库根和 wireless-rl）：统一为 P2D 已验收、P3A 等待当前 HEAD 重验证；禁止直接进入 P3B。
- `ros2-multi-robot-automap/user_guide.md`：同步 P3A 后 gateway 数据流，避免文档继续描述已删除的直连。
- `task_evaluator.py`、`ros_smoke_test.py`、`test_task_evaluator.py`：修正 rally 模式的成功终止语义并加回归测试。
- `log.md`：记录本轮无仿真审查、代码修复和下一阶段未完成项。

本轮未声称 P3A 已验收，也未把当前 HEAD 的任务性能当作网络基线。下一次可执行工作应是
P3A.5 当前 HEAD 重验证和 manifest 生成；完成并由用户验收后，才开始 P3B。

## 证据定位

以下位置用于把审查结论绑定到当前工作树，而不是只依赖日期报告中的摘要：

- 阶段状态和当前证据边界：`RESEARCH_PLAN.md:86-101`、`IMPLEMENTATION_PLAN.md:58-80`。
- 消息时间账本和检测三段时刻：`RESEARCH_PLAN.md:242-248`；P3B 字段与 mode 要求：
  `IMPLEMENTATION_PLAN.md:264-290`。
- gateway 限频、生成时间、交付和 ACK：`ideal_gateway.py:165-236,285-395`；当前限频并不注入
  delay/drop，`generation_time` 仍是 gateway 回调时间。
- 导航命令等待结果：`navigation_gateway.py:133-163`；当前循环没有完整 deadline/幂等重试上限。
- 电池 freshness 与尚未统一门禁的 map/odom/TF：`control.py:1377-1390,1802-1858`。
- truth provider 读取 Gazebo 全局 model states：`target_detector.py:68-164`；评估器 raw 检测订阅和
  时间记录：`task_evaluator.py:341-375,539-557`。
- rally 成功判断与覆盖率 timer：`task_evaluator.py:218-226,591-600,708-740`；smoke 成功条件和
  参数互斥检查：`ros_smoke_test.py:254-285,435-445`。
- 旁路审计目前的源码/节点 topic 范围：`bypass_audit.py:24-112`。
- 历史 P3A formal v2 与当前 HEAD 的差异：Git 提交 `bbe8482` 之后至当前 `cc01656` 的电池、
  协调器和净空修改；因此 P3A.5 必须在冻结 commit 上重新生成 manifest 和结果。
