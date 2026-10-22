# MR3 原生 reset 启动契约

V49 的 `received-input-pause-drain-v1` 定义由 Supervisor 管理的原生 reach reset。
当前源码在 `safety_contract='mr3-reach-v1'`（control version 2）时自动选择该协议，
并在 reset 请求、Supervisor/worker metadata 和成功 reset 的 info 中显式登记。
没有新增启动协议 CLI 或可选开关；单独运行 ROS launch 不执行这套私有 reset 握手。

本契约补充固定的 [环境契约](MR3_ENV_CONTRACT.md) 和
[reach 安全契约](MR3_REACH_CONTRACT.md)，不修改它们的原始字节。
它只规定启动次序、实际接收记录和失败预算；新源码仍须在自己的冻结上取得必要资格。
历史启动 FAIL 保留，不能据本契约推断旧 worker 当时哪个 ready 条件为假。

## 实际输入与启动次序

四个 readiness 字段来自 worker 的实际 ROS 回调。初始默认 False 不等于收到过 False；
节点出现、上游日志记载 publish 或另一个订阅者收到消息，均不能替代 worker 的接收。

| worker 字段 | 实际接收依据 |
| --- | --- |
| `monitor_ready` | `/task_monitor_ready` 的 Bool |
| `initial_inputs_ready` | `/mr3/initial_inputs_ready` 的 `mr3-initial-inputs-ready-v1` ACK；epoch 必须匹配，状态序列、地图摘要、三机名称及来源/接收时间通过原校验 |
| `odometry_recorder_ready` | `/mr3/odometry_recorder/ready` 的 Bool；被动 recorder 自己的 ready 不能替其他组件作证 |
| `motion_ready` | `/motion_safety/ready` 的 Bool |

reach reset 严格执行以下次序，各等待共用同一个启动工作截止时间：

1. `await_received_upstream_inputs`：等待 `monitor_ready=True`、有效本 epoch
   `initial_inputs_ready` 和 `odometry_recorder_ready=True`。此时不要求 motion-ready。
2. `pause_requested`：启动真实 step helper，取得 `physics(0)` 的暂停回执。
   ACK 时刻不得在实际暂停时刻之后；随后用原有有限真实预热 tick 对齐 `/clock` 和物理时钟。
   这些 tick 不计入 policy transition。
3. 通过原唯一 motion 输出端点及 tagged driver 拓扑检查，进入 `paused_topology_verified`。
   此时允许 motion-ready 仍为 False；不能在无 pending commit 的暂停时钟上等待它自行重算。
4. `takeover_and_storage_barriers`：完成真实 motion/state/peer takeover ACK。
   takeover 目标必须全零且不能为 STOP；三台真实 driver 的匹配 storage ACK 全到后，
   才允许原有 20ms 全零 bootstrap。在其新边界，原 state→peer→motion commit 必须取得
   全部真实依赖及完整来源前缀，才产生新 status；同一旧时钟的输出不覆盖、不重复发放。
   之后初始 motion status 必须 ready 且未 stopping，并再次取得三台真实 storage ACK。
5. `await_controlled_motion_prefix`：等待原上游三项仍成立且实际 `motion_ready=True`。
   ready status 不能替代 Bool 回调，Bool 也不能替代精确边界的 status 或 storage ACK。
   此后才进入 `request_initial_snapshot_release`：完成原 snapshot 的实际 drain、水位、交付 bundle、
   clock 和摘要屏障，且状态序列不能早于初始输入 ACK；由该 snapshot 触发原任务 release。
   evaluator 必须确认同一开始时刻，三个真实 post-release HOLD intent 引用必须交付，
   reward ledger 必须以零奖励、非终态初始化，evaluator phase 必须为 LIVE，才记
   `reset_complete` 并返回初始观测。

初始 snapshot 之前收到的 motion 输出必须始终全零，包括已 takeover 的阶段。
暂停和四项 ready 不替代上述任何屏障。真实来源前缀、.5s 源龄、全零资格、guard 自己的
storage receipt 屏障、实际应用、物理/接触、终态及95%任务门全部保持；没有补造 ACK、
重戳、重锚、默认通过或无效训练样本。

## 一个绝对 deadline 与清理预留

父 Supervisor 在 `reset()` 入口取真实 `monotonic_ns`，早于关闭上一轮、创建新 worker、
解释器导入及 reset RPC。设该入口为 `t_reset`、配置启动上限为 `T`：reach 要求
`0<T<=420s`，默认420s，绝对 deadline 为 `D=t_reset+T`。
请求显式携带 `startup_deadline_monotonic_ns=D`；发送前检查是否过期，实际发送后再扣去
已耗时间，以剩余时间约束接收等待，不另给一次420s。

worker 在构造早期校验协议及绝对 deadline，取当时真实时间 `t_worker`，定义：

```text
startup_wait_deadline = min(t_worker + 400s, D - 60s - 5s)
```

400s 是原 worker 最大启动等待；60s 是原失败清理预留，5s 是响应裕量，均包含在父上限内。
默认420s且无前置耗时时，工作窗口最多355s；构造/import/RPC 已耗时间会进一步缩短它。
上游等待、暂停后的等待、拓扑、takeover、storage、snapshot 和 release 共用该工作截止时间，
每个原局部等待还保留自己的更小上限。没有为两个 ready 阶段各分配400s。
工作预算已耗尽时，在启动 ROS/launch 前即可拒绝。启动失败的清理截止时间为
`min(清理开始时刻+60s, D-5s)`；helper IPC/process wait、时钟对齐、条件等待及关闭等待
均按当时剩余清理时间截断，没有剩余时间即交给父进程的原 owned-process fallback。
成功 reset 后发生的任务故障保留原60s清理窗口，不套用已经过去的启动 deadline。

这些是实际 monotonic deadline 和等待预算，不是操作系统硬实时保证。阻塞调用、异常或父
deadline 到达仍须记失败，并由原 owned-process TERM/KILL、实际 wait/reap 和独立 absence
检查收口；预留不等于清理一定成功，也不允许额外延长活动预算。

## 接收日志与故障

reach worker 独占创建 `startup_readiness.jsonl`，schema 为 `mr3-startup-readiness-v1`。
每行含 epoch、protocol、kind、stage、实际 `clock_ns`、已知时的 `physical_ns`、
`wall_monotonic_ns`、四项当前 ready 快照及 `callback_fields_received`。
初始化记录不伪装成回调；Bool 的首次实际接收（包括 False）及后续变化记录原 topic/data，
初次有效 initial-input ACK 记录原消息。阶段进入与失败也记录当时快照。
日志可继续记录后续回调；启动完成后不沿用启动期的 fail-fast 解释任务终态。

`/exploration_failure` 接收保留原 String.data。启动期收到可解析、epoch 匹配的实际 JSON
故障，在原健康检查处立即失败并记录 receipt；旧 epoch 或无 epoch 的消息仍保留原记录和
原有处理，不被推断为本 epoch 的健康结论。motion_safety 的首次永久 reach fault 发布包含
component、epoch 及原 fault 的 schema/robot/reason/clock；日志不把它替换成猜测的 ready 原因。

任何失败仍是 infrastructure failure：记录原异常，执行原有 ordered abort cleanup，
保留真实 STOP/零目标、导航取消和进程关闭责任，不返回成功 reset、奖励或训练样本。
回调/journal 只证明记录到的接收和执行次序，不单独证明连续物理安全、原生资格或P2A完成。

## legacy 兼容

`legacy` / control version 1 保留原次序：四项 ready → 两项拓扑检查 → helper 暂停及实际时钟
对齐 → 原 takeover/storage/release。它不发送上述 protocol/deadline 字段、不创建新启动日志，
旧 metadata/result 省略新增字段；legacy 请求携带新字段会拒绝。当前 reach 的新启动路径
只能以新源版本和新冻结验证，不能借 legacy 或历史 reach 原件取得新信用。
