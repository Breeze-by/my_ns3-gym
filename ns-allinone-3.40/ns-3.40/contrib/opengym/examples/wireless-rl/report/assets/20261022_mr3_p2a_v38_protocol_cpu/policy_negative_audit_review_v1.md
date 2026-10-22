# P2A 导航负回合与完整审计门：只读评估及待定方案

日期：2026-10-22。状态：**ASSESSMENT_ONLY；任何训练审计规则变更均为 PROPOSED_NOT_APPROVED，未激活。**

本文件只读检查当前计划与代码，不读取/重放真实 episode、压缩 protocol 或 trace，不运行测试、World、训练或消费者，不修改生产源码。会话给定 V37 闭合 HEAD 为 `1dce9cc98`；本文件最终归档冻结由本轮提交确定。V37 短活动 FAIL 与其他旧 FAIL 保持，不以此评估改判。

## 判断

当前实现确实存在两个不同层次：**PPO collector 允许普通导航失败作为负回合；完整 native protocol/custody 审计却会拒绝带 dispatcher failure 的回合。** 不能把 collector 的 `training_eligible=True` 等同于整条 P2A 科学链已准入，也不能反过来把所有正常失败终态都说成 collector 基础设施异常。

二维 uniform 短活动全部 PASS **不是原生资格的合同前置条件**。V37 profile→short 的顺序、192 次尝试等是该活动自己的工程目标；未完成目标所以原活动 FAIL。原生资格/PPO admission 不读取此 proxy PASS。下一步不应为了消除所有随机策略负回合而持续修改 FIFO、TTL 或目标频率。

## 当前实际代码边界

下表中 `W` 表示 wireless-rl，`P` 表示 ROS 包的 `multi_robot_exploration` 源目录。

| 层次 | 实际行为与约束 |
|---|---|
| `W/mr3_learning/ppo.py::closed_episode_training_eligibility` | 明确保留普通 navigation/contact 任务失败；只对 motion_safety 的 `settled_turn_model_failure`、`normal_control_model_invalid`、`reach_model_failure` 拒绝训练。闭合 summary 缺失、epoch 错误等也拒绝。 |
| `ppo.py::collect_episodes` | 真正 `terminated` 的负回合保留实际 reward、dt 与终态，`next_value=0`；各 worker 全部关闭后才做 eligibility 检查。RPC、采集或关闭异常使 round 抛错，保留诊断，不补造 GAE/targets 或优化该无效 round。普通负终态自身不触发这一异常分支。 |
| `tests/test_ppo.py::test_ordinary_task_failures_remain_eligible` | 人工 fixture 明确要求普通 `navigation_failure` 保留负 reward 并通过 collector eligibility。该测试不证明完整 native 审计通过。 |
| `audit_reach_ppo.py` 与 immutable `audit_ppo.py` | 合取同冻结资格、原 policy/rollout/GAE/optimizer/scalar/native 以及独立 reach roles；任务失败列表与审计错误分别记录，训练审计并非普遍要求 task success。但原 native protocol gate 仍在。 |
| `scripts/audit_mr3_env.py::audit_protocol` / 当前 versioned protocol dispatch | `protocol_failure` 作为审计错误。现有明确特例仅处理已证明的 peer-stop unsent 分支，没有把 `goal_lease_expired` 注册为可授信的训练负回合。V37 candidate/source 扩展没有改变此项数学门。 |
| `native_custody.py::strict_closed_episode` | 除真实 `pending_goal_count=0` 和正确机器人/epoch 外，还要求 `closed.navigation_failure is False`、worker `failures==[]`、`native_failures==[]`。`native_custody_reach` 保留此原函数，并未给普通导航失败新增分支。 |
| `reach_policy_chain.py::jobs_for_stage` / `stage_evidence` | minimum/pilot/final 都提交 strict custody；完整 stage 必须 scientific audit 和 strict custody 同时 PASS。因此即使 collector 已用某导航负回合更新权重，也不能自动取得该 stage 的科学信用。 |

结论限于这种具体情形：dispatcher 已锁存 `goal_lease_expired`，但后来所有真实 owner 都得到 terminal 并干净关闭。它可能是 collector 的有效负样本，却仍不能按**当前**完整 native protocol/custody 门授信。不能只删 custody 的一个布尔检查就称矛盾解决，因为 protocol gate、来源、物理、关闭等仍然独立必需。

## 硬要求与推荐不能混淆

- [当前实施计划](../../../IMPLEMENTATION_PLAN.md) 的 P2A 出口仍是真正由网络选目标的三机器人 Gazebo 训练/验证链及冻结 95% 任务；[研究计划](../../../RESEARCH_PLAN.md) 要求保留策略诱发的超时、握手、死锁等失败，不将其剔除为无效测量。
- `reach_preparation.validate_plan`、`reach_policy_chain` 和 `ppo.main` 的原生准入要求同冻结完整资格及同 seed/start 组合，没有 proxy uniform PASS 门。现有 30 mandatory roles、12 episodes 与完整 matrix/minimum 约束不因 V37 改变。
- 完整原生链仍须预约 20100 工程秒；V37 后工程余额 `3740.3614838083982/52000` 不足。75000 提案仍待明确批准。pilot 剩余 `1870` decisions / `2905.9547395464029` 秒及 final-only 原额度不借用、不重置。
- 最终验证仍要求原 open401/402/403 三场、同一 final checkpoint、零优化更新、全部严格成功；95%/300 秒、地图质量、三台参与、18 路接触、源龄、物理及 ownership 门不放宽。有效训练负样本永远不能算最终成功。

因此，在预算批准且完整资格通过后，**当前模式可以按现门执行 native 链，不存在必须先新增负回合审计版本的逻辑前置条件**；但不能承诺带 dispatcher failure 的回合还能让该链 PASS。若要在完整训练证据中接受这类闭合负回合，必须先明确新的训练审计契约。

## 待定的窄范围训练负回合审计方案

**以下全部为 PROPOSED_NOT_APPROVED；没有更改 reader、资格、训练或执行行为。**

原子闭合、按规定 fail-safe 停止的导航负回合，在研究上可以是有效数据。前提是独立证据证明它是契约规定的任务转移，而不是物理模型失效、时钟/交付违规、数据伪造或未解决所有权。最低必要证明包括：

1. 原 action/mask/观测版本、权重及 epoch/goal ID、创建/到期/实际交付、续租和首个失败时间完整可追溯；失败分类与真实终态一致，不刷新旧命令 TTL。
2. 失败后真实停止、late acceptance/cancel/result 全部闭合；没有凭超时释放 owner，没有遗留未知目标或进程，完整 native 与 Nav2 关闭回执成立。
3. 原 clock/state/peer/guard/storage ACK、动作 FIFO、收到的信息来源、物理执行、停止模型及持续接触监测等独立门全部保留。建议首个候选分支仅考虑**零真实接触且其他原安全门均通过**的闭合导航负回合；不把 control-model invalid 或真实安全违例洗成“普通负样本”。
4. 仅保留实际返回 transition、reward、dt、终态和零 bootstrap；不得删失败、补样、重放失败活动来填成功数，也不得把其他 worker 被全局停止的 prefix 伪装为完整任务或成功。
5. 新版本必须同时覆盖 PPO 的 protocol/训练数据审计与训练专用 custody 判定。原 reader 的 FAIL 原样保留，另给范围明确的新判定；不能移除失败事件后宣称旧审计通过。资格工程矩阵、最终成功审计与默认路径不因此放门。

这不是延长 TTL、放松 FIFO 或提高续租频率的方案。若另提 transport 行为版本，须说明其科学动机与交付语义，并单独预声明；不能仅以“随机短活动尚未全 PASS”作为修改依据。

## 建议下一项最小工作

先完成 V38 固定的一文件 protocol 法证与 disabled CPU 证书，保持其真实有限作用域。随后优先形成一页**训练负回合审计决定**，而不是继续大规模工程循环：

- 若保留当前严格 native gate：明确训练期间的 dispatcher failure 将使完整审计/闭合失败；预算批准后按新冻结资格→minimum→pilot→final 推进，不新增“proxy 必须全 PASS”的门。
- 若希望此类原子闭合负回合得到完整训练信用：先列窄范围 allowlist 与独立必要证据，设计纯人工 records 的 collector/原 protocol/custody 对照；同时覆盖正常闭合负回合、未释放 owner、control-model invalid、错 epoch、错 goal、伪造终态和物理不安全反例。先审定新规则，再考虑生产实现、统一验证与新冻结；不得在当前 run 中追认。

本评估推荐先解决这项**审计口径决定**。它直接关系到已有有效负样本能否被完整链接受，比为满足随机活动的全 PASS 而连续修改执行模型更接近 P2A 的真实出口。即使采用新审计版本，也不替代新的原生资格和真实学习/最终验证证据。
