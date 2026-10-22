# V49 后 P2A 学习与验收可行性静态评估

本评估只读当前代码和活动计划，没有读取本轮 trace、模型或科学原件，没有运行实验，没有修改仓库。V49 已成功的 2-worker/rooms101/1-step 启动活动仅提供原声明的工程信用。root 报告其关闭后工程余额为 19040.3950687683982/75000 秒；pilot 仍为 1870 决策/2905.9547395464029 秒，final-only 三回合额度未动。

## 准确的出口

P2A 的计划出口是：三机器人 Gazebo 中网络真正选择目标、无手工目标兜底和 actor 真值输入，达到冻结的 95% 任务，且存在完整可复现训练/验证链。不是只完成优化器更新，也不是只证明机器人运动。见 IMPLEMENTATION_PLAN.md 的 MR3-P2A 段（206–223 行）。

当前可执行 policy-chain 把此出口具体化为：完整同冻结原生资格；minimum 恰 16 个 eligible 决策且正更新；pilot 2–1870 个 eligible 决策且正更新；从该 pilot 的唯一 final.zip 进行零更新验证，在 **open401、open402、open403 各一个完整回合，合计三个回合**中全部 strict task success。不是 open/rooms/corridors 各三种子共九回合。每回合保留原 95%、300 仿真秒、地图质量、三机参与、真实接触/监测、来源、关闭和物理门。

P2C 的跨布局正式矩阵和至少 90% 成功率是后续范围，不能额外塞入 P2A，也不能用 P2A 三个已知开发布局回合宣称泛化。没有合格 final.zip 时，验证必须 SKIPPED；存在 final.zip 但三回合失败，则保留真实 FAIL，不能以正更新替代。

代码锚点：mr3_learning/reach_policy_chain.py::validate_spec、check_native_result、validate_predecessor；当前 validation 固定三个 open 种子、300-step 上限/900-decision 上限、task_successes==3、task_failures==[]，并绑定 pilot final.zip SHA。

## pilot16 是当前直接可执行路径

不能把 `--episode-steps 64` 当作首更新必须完成 64 步。当前 admission 只要求 pilot `2 <= decisions <= 1870`，并保持 episode-steps=64。ppo.py 会计算 `count=min(workers,remaining)`，再计算每 EP 的 `cap=min(episode_steps, remaining//count+...)`。因此 **pilot decisions=16、workers=2 会实际各采最多 8 个决策**，而不是各采 64。

它要求全部真实回合结束、进程关闭及 training-eligibility 通过之后才构造 buffer；有效合计至少两个样本即可 model.train。batch-size 是 minibatch/model 配置，不是这段自定义完整回合 collector 的采样门。即使样本少于 batch-size，实际最后 minibatch 仍可优化。代码还要求参数确实变化，最终保存 final.zip。

墙钟到期也不是“丢掉不足 64 的 rollout”：collector 在下一真实物理 step 使用原 external-truncation 路径，保留末观测的真实 bootstrap，完成原生关闭/eligibility，再更新。需要事前给该在途 step、关闭、内部审计和外部 finalize 留足时间，不能把 soft deadline 当 OS 硬停止。

这条路径不需要增加决策/墙秒额度，也不需要二维训练、恢复旧权重或放宽数学/任务门。必须为它生成新的显式 plan/scope/freeze，保持原最低资格。它证明“有真实训练和终模型”，**不证明 16 个决策足以学会 95%**。minimum 与 pilot 当前各自从头初始化；不能把 minimum 或旧 v5 权重偷偷作为 pilot 初始化。

代码锚点：ppo.py::collect_episodes（约180–285）、main 的 caps/收集/训练/保存（约478–598）；reach_policy_chain.py 127–137、258–269。`ppo train --checkpoint` 当前明确拒绝，需要另行声明的恢复路线。

## 吞吐的实际限制

以 root 给出的“31 墙秒/step”为条件估算，不能把它升级为尚未独立测得的长期吞吐。特别是一决策活动可能含启动/关闭，必须区分“每 worker 的 step 成本”和“全体每个有效返回的成本”。

| 条件估算 | 不计启动/关闭/审计的乐观上限或成本 |
|---|---:|
| 31 秒为全体每个 eligible decision 成本 | 原生 pilot 2100 秒约 67.7 个决策 |
| 31 秒为单 worker 成本，两个 worker 真并行 | 原生 pilot 2100 秒约 135.5 个决策 |
| 两 worker 各 8 步 | 约 248 秒采样，另计启动/关闭和审计 |
| 两 worker 各 64 步 | 约 1984 秒采样，原生 2100 内只剩 116 秒其他费用 |
| 三个验证 EP 真并行、各到 300 步 | 单 EP 9300 秒，已超过原生 8500/总9000，尚未算启动/审计 |

validation 配置 workers=4，但 collector 在仅有三个 schedule 项时实际 count=3。它不需要必然走满 300：若真正早达 95%，可以提前成功。不过在每 worker 31 秒/step 的条件下，原生 8500 秒允许的最长共同路径不到 274 步，扣启动/关闭后更短。不能把 wall 外部截断视作任务成功。

想在 native 2100 秒用满 1870 决策，需要全体有效吞吐至少 0.8905 decision/秒；两个 worker 的理想单 worker step 成本约不超过 2.25 秒，并且还未扣其他费用。故仅把 rollout 缩短或多做 PPO epochs，不能填补数量级的数据缺口。增加 epochs 不增加新环境经验，甚至可能过拟合；不能把优化器调用数当充分学习证据。

## 建议的执行顺序

1. 先关闭本次 V49，保留成功的工程证据；下一冻结修完已经识别的实际 PPO pre-update eligibility 新 fault-schema 识别缺口。新 motion failure 的 reason 是具体错误字符串，旧 collector 只认三个 reason literal，必须按当前 epoch/component/真实 fault schema 保守拒绝该非法 plant 样本，保持普通任务负样本可用。随后一次完成既定新冻结资格，不继续无目的启动探针。
2. 若目标是先获得完整可复现最小训练链，可以采用当前已支持的 minimum16→pilot16，保留 final-only 原规则。将其准确称为最小学习/端到端验证，不预告 95% 会通过。最终若真实通过即形成 P2A 证据；若未通过，失败是真实能力结论，不能再以“多几个正更新”改判。
3. 若目标是提高“达到 95%”的概率，建议在花掉珍贵 final-only 回合前，前瞻声明一个有实质经验量的训练方案。优先考虑真实语义不变的吞吐优化与 1/2/4-worker 资源配置；它们仍需新冻结/真实容量证据，不能假定线性扩展。缩短 collection prefix 可以增加反馈轮数，保留真实外部截断和 bootstrap，但现 policy-chain 已把 64 写为显式规则，改这个 literal 必须新版本声明，不能借旧 plan 信用。
4. 二维预训练是可考虑的路线调整，**当前并没有可直接启用的训练后端/资格**：ProxySupervisor、相关 activity 都明确 training_eligible=False/零更新；PPO 原生 collector 会读原生关闭/eligibility，不能把代理 summary 伪装为原生回执。零更新一致性和历史容量也不证明足够训练吞吐、策略可迁移或原生 95%。

## 在原余额内的二维路线应如何明确声明

最新用户授权自主持续完成 P2A，可以据此准备一份具体的新路线与预算记录，而不是再次询问一般实施批准。但不能把旧 V22 的零更新授权重写为已有二维训练资格，也不能把 75000 工程块当作自动增加的 pilot 训练额度。

最保守的做法是：预训练与原生微调合计仍计入剩余 **1870 决策/2905.9547395464029 秒**，把后端、训练种子、每段最大样本/墙秒、模型 SHA 链、失败停止、所有 optimizer/GPU 调用、实际 final checkpoint 选择规则提前锁定。例如可以研究“二维至多 1806 决策＋原生至多64决策”的候选，但这是 **PROPOSED，未激活**，不能当成已可运行或足够学习的方案。

若预训练段只分配约 650–700 秒，该例需要至少约 2.6–2.8 decision/秒，尚未计其独立核验；历史短二维容量约 0.61 总decision/秒不能满足此条件，且它不是当前新规则训练吞吐证明。必须先有廉价、有限的当前训练路径容量证据；未满足则不启动这个配额组合。原生64决策在两个 worker/31秒假设下约 992 秒采样，还需真实启动/关闭、内部审计和外部 finalize。每项都进入同一 pilot 完整时间账，不能把预训练或 finalizer 藏进其他 scope。

该路线还需要：独立显式的二维训练 eligibility/audit，received-only 相同 encoder/candidate/action/mask/奖励接口；无 actor 全图真值；完整源与地图/终态日志；保持 full-task objective 的 bootstrap；在同一训练种子、预声明样本与时间预算内唯一从头训练→预训练 checkpoint→原生微调→最终 checkpoint 的来源链；不能从多个中间模型按 final401/402/403 结果挑选。最终仍只由新的合格 Gazebo 实验授予物理/95% 信用。

1870 个便宜样本也没有充分学习的数学保证。若既定额度下仍不能达标，准确结论是“P2A 未完成、当前配置/预算下未取得能力证据”，而不是扩充隐藏训练、伪造代理信用、放松 95% 或转进 P2B。路线调整应增加有效经验、减少真正计算成本，避免继续围绕仅能产生极少新样本的工程链反复补丁。
