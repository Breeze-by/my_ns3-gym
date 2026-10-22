# V38 固定 protocol 法证：独立判断与因果边界

2026-10-22；**REVIEW_ONLY；不改变 V37 FAIL、执行行为或现有训练准入。** 本次只读 `/tmp/mr3_p2a_v38_protocol_forensic_v1.json` 派生报告，没有打开压缩原件、重放状态或运行 World/测试。报告 schema 为 `mr3-v38-fixed-protocol-forensic-v1`，提取冻结 `a44e1b844678ece45cfd377ea43e7ed65901cce3`，证据冻结 `13e95f29fcc094b19c42fbdeb7d9a76644dee0e9`；其单次解析为 935 行 / 336574 解码字节，选取 102 行，来源与输入前后稳定。原 protocol 压缩身份 SHA256 为 `506e4e491f1a1993b9481f79ef09b1080efdb5de94a7faa5b5906ec69f4ee3e5`。

**结论：新 tb3 目标的续租已生成，但实际交付未早于原截止时间；54.1 秒租约失败是记录支持的真实终态原因。不能再归因为“没有生成续租”，也不能据此证明具体全局 FIFO 队首阻塞链。**

## 可核实的时间线

下列行号均为派生报告保存的原 protocol **1-based 行号**；时间为仿真秒，完整 epoch 为 `proxy2d_w2_e1_f96a1433`，简写目标 `tb3:46` / `tb3:53` 都保留此前缀。

| 原行号 | 记录事实 |
|---|---|
| 883、889、893 | 旧 `tb3:46` 的取消命令生成于 52.1、交付于 52.5；取消 ACK 交付于 53.1，`CANCELED` result 交付于 53.3。 |
| 895 → 896 | 53.3 先记录旧目标 `protocol_terminal=CANCELED`，再记录新 `tb3:53` 的 `send_goal`；新目标 `created_at=52.1`，`expires_at=lease_until=54.1`，未因等待取消而刷新 TTL。 |
| 902 | 新命令生成于 53.3，实际交付于 53.9，仍携带原 54.1 截止时间。 |
| **904 → 907** | **54.1 先记录 `goal_lease_expired`；随后同一时钟记录新目标 heartbeat 的交付。该 heartbeat 生成于 53.4，交付于 54.1，携带 `expires_at=55.4`。** 它没有在原截止前交付。 |
| 916、918 | 新目标 `accept=True` 在端点于 53.9 生成，54.5 才交付；随后记录因 `navigation_failure` 取消该目标。接受生成、接受交付和 dispatcher 请求是不同事件。 |
| 931、934 → 935 | 新目标取消 ACK 于 55.1 交付；`CANCELED` result 与 dispatcher terminal 于 55.3 记录。该目标最终闭合，不等于此文件独立证明全队物理停止及完整进程关闭。 |

从记录可算：创建到 dispatcher 发送已过 1.2 秒，命令再经 0.6 秒交付，端点收到时原 TTL 只余 0.2 秒；这是时间分解，尚不是对每段延迟的队列因果分配。源代码既定规则在 `renew` 前先检查到期；54.1 的迟达续租不能追溯撤销已锁存失败，不应把同一时间戳当作可忽略的误差。

## 尚不能证明的部分

实际交付记录与现有共享 FIFO 代码、人工反例相容，支持把“取消等待后命令已老化，后续可靠消息又迟达”作为调查方向；本文件没有完整 enqueue/dequeue、队首或 backlog 日志，**不能重建全局队列、确定实际阻塞头、证明缺失记录对应未生成消息，或证明改变调度必定挽救本回合**。相邻已记录交付的生成间隔也不等于生成流本身的间隔。本次仅限代理协议，不提供 native Nav2、物理、安全或 95% 任务证据。

## PPO 与下一步边界

普通、真实终止且完整安全闭合的导航负回合可以是 PPO collector 的有效负样本子集；但**本次代理法证没有训练信用**，报告明确 `training_eligible=false`、`qualification=false`、`native_credit=false`，策略/GPU/优化调用均为零。当前 native 完整链仍由 protocol gate 拒绝该 `protocol_failure`，strict custody 也要求 `navigation_failure=false`；不能用 collector 的宽口径替代完整准入。详见[负回合审计评估](policy_negative_audit_review_v1.md)。

维持现有停止、无重试与旧 FAIL，TTL、FIFO、续租频率、95%/300 秒、接触及其他物理门均不放宽。法证 PASS 只表示有界提取与身份检查通过。若要接受原子 fail-safe 闭合导航负回合作为完整训练证据，应先明确独立安全、数据身份、实际终态和关闭证明，形成训练专用的新审计版本；**该变更仍为 PROPOSED_NOT_APPROVED，未实施或激活**。不以追求随机代理活动全 PASS 为由继续无界修改执行模型。
