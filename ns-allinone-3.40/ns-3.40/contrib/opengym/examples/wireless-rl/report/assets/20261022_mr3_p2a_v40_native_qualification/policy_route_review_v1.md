# V40 strict native 资格与完整 policy 路线审查

2026-10-22；**READ_ONLY_CODE_REVIEW，未运行 World、测试、训练或原件消费者，未修改生产源码/plan。** 最新用户指示已授权自主持续完成 P2A，不再以一般预算/实施批准中断；本轮按工程累计 75000 秒的有限块准备，原 pilot 与 final-only 额度、科学门及旧 FAIL 保持。授权原件由本目录 `authorization_v1.json` 记录。本文件是构造及审查建议，不是资格或学习通过回执。

## 结论与最短路线

继续有价值的方向是**同一新冻结完整 native 资格 → 新 minimum → 从零 pilot → pilot final.zip 的三场完整验证**。不新增“二维随机全 PASS”门，不重开 V37，也不以 CPU/代理通过替代 Gazebo、SLAM、Nav2、真实机体与持续接触监测。P2A 出口仍是[活动实施计划](../../../IMPLEMENTATION_PLAN.md)要求的真实联合 RL 目标、无手工兜底/真值输入、至少一条完整可复现训练/验证链及冻结 95% 任务；参数更新或机器人运动本身不完成 P2A。

本轮保持 V19 封存 policy 配置的 workers、open 开发布局、采集前缀与优化参数，仅改 V40 路径/通信隔离与显式新观测组合。这比改变采样场景或并发更少引入无关变量。minimum 是接口/更新证据，pilot 是有限学习尝试，final 三场是已批准的开发验证；它们不声称 P2C 未见布局可靠性。

## 预算与资格

入场工程已用 `48259.9538193466018`，在 75000 下余 `26740.0461806533982`。完整资格 18000、外部资格/计费收口预约 300、新 minimum 1800，合计 **20100 工程秒**；全额预约后余 `6640.0461806533982`，实际费用按墙钟区间及外尾记录，不能把预约当实费或退回已消费费用。pilot 仍最多 `1870` 决策 / `2905.9547395464029` 秒；final-only 仍最多 900 决策 / 9000 秒，原 open401/402/403。不借用、不重置这些额度；外部 finalization/复核尾部也必须另记实际费用，不能靠 stage 内部 `passed` 隐去。

[reach_preparation](../../../mr3_learning/reach_preparation.py) 的资格仍是 **30 mandatory roles / 12 episodes**，不是将旧 38 项重命名后复用。四阶段如下；unused earlier reservation 的前向借用按现有精确算术执行，总 18000 不变。

| 阶段 | workers / schedule / 每回合 steps | 回合数 | stage / 原生 work 上限秒 |
|---|---|---:|---:|
| interface | 1 / open101 / 32 | 1 | 2400 / 1900 |
| terminal | 1 / open101 两次 / 4 | 2 | 1200 / 850 |
| reset | 2 / open101、open101、rooms101、corridors101 / 32 | 8 | 6500 / 5500 |
| deadline | 1 / open101 / 300 KEEP | 1 | 7900 / 6900 |

资格使用原 outward/cancel、参数读回及独立输入/角度/物理/信息/执行/时序/关闭门，零 GPU/optimizer。失败或余额不足后剩余阶段 SKIPPED；不得用旧资格或某几个角色 PASS 拼全链。只有同 freeze/PLAN SHA 的完整 `mr3-reach-scientific-qualification-v1` 经外部实际 wait、协调进程退出及闭合原件逐字复核后才能进 minimum。`validate_plan` 自身只核 engineering remaining≥18000，**20100 整体入场预约需要本轮 scope/前检额外核准**，不能把该低一级检查当完整预算证明。

## policy_stages 的具体构造

[reach_policy_chain](../../../mr3_learning/reach_policy_chain.py) 要求 plan 的 `policy_stages` **恰有** `minimum`、`pilot`、`validation` 三键；`reach_preparation.build_plan` 不自动生成它。必须在最终 source inventory/PLAN SHA/freeze 前补齐，不能资格通过后再追加。

| 参数 | minimum | pilot | validation |
|---|---|---|---|
| `--mode` | train，从零 | train，从零 | evaluate |
| `--workers` | 1 | 2 | 4 上限；3 个 schedule 实际最多 3 env |
| `--schedule` | open:101 | open:101 | open:401,open:402,open:403 |
| `--decisions` | 16 | 1870 上限 | 900 上限 |
| `--episode-steps` | 16 | 64 外部采集前缀 | 300 完整任务 |
| `--seed` | 41 | 41 | 41 |
| `--batch-size / --epochs` | 16 / 4 | 64 / 4 | 64 / 4；不优化 |
| `--device` | cuda:0 | cuda:0 | cuda:0 |
| 原生 `--wall-seconds` ceiling | 1150 | 2100 | 8500 |
| spec `wall_seconds` | 1800 | 2905.9547395464029 | 9000 |
| spec `tail_reserve_seconds` | 500 | 500 | 500 |
| `--checkpoint` | 禁止 | 禁止 | 只允许 P_RUN/final.zip |

其中 workers/minimum episode-steps/batch/device 等部分不是 `stage_spec` 的全部硬编码数学条件，但应按上表**显式封存**，避免依赖可变默认。精确命令前缀必须为 `[plan.learner_python, "-m", "mr3_learning.ppo"]`，共同参数为：

```text
--safety-contract mr3-reach-v1
--seed-rule exact-point-bridge-v2
--start-graph-rule point-attachment-3x3-v1
--reach-plan PLAN --reach-qualification QUAL
--output-root RUN_ROOT --run-id EXCLUSIVE_STAGE_ID
```

`PLAN`、`QUAL`、run/output 路径全部预先确定为绝对路径；`run_directory == RUN_ROOT/run-id`，spec 的 `output_directory` 必须与 run 不同。domain/port 使用 diagnostic agent 为 V40 核定的无冲突范围，不改变机器人数量；参数只出现一次。

各 spec 还需严格 condition：

```text
minimum: {requires: matrix_qualification}
pilot: {requires: minimum_complete,
        previous_stage_summary: M_OUT/summary.json,
        previous_stage_outer_wait: M_WAIT/actual_wait.json,
        previous_stage_final_absence: M_FINAL}
validation: {requires: pilot_complete,
             previous_stage_summary: P_OUT/summary.json,
             previous_stage_outer_wait: P_WAIT/actual_wait.json,
             previous_stage_final_absence: P_FINAL}
```

这里 M/P/V_RUN、M/P/V_OUT 及 WAIT/FINAL 是 diagnostic agent 最终 plan 中的实际绝对路径，不是可直接执行的占位目录。stage 执行前自行重算前阶段 `stage_evidence`，要求保存的 final-absence 原件与重算结果逐字段一致且 PASS。validation 的 checkpoint SHA 必须等于已闭合 pilot 的 `final.zip`，不能选 minimum、intermediate 或其他 run。

## 学习、终态与失败阻断

[ppo.py](../../../mr3_learning/ppo.py) 固定 gamma=lambda=1、lr=.0003、entropy=.01、target_kl=.03；`n_steps=batch_size`，共享固定 encoder、1000 联合离散动作及保存的 mask，无在线归一化。四 epochs 是最大值，KL 可提前停止，不能保证最小链必有恰好四次更新。minimum 最终必须恰有 16 个有效 native 决策及真实正更新；pilot 可在墙钟前缀结束，只要完整审计通过、2≤有效决策≤1870 且有真实更新，代码不要求用尽 1870。它不保证在 2100 原生秒内获得多少完整 round 或达到 95%。

所有当前 round worker 真正终止/外部截断、关闭并通过 eligibility 后才构造 PPO targets。真正 terminated 的任务负回合零 bootstrap；外部采集前缀只保留一次真实下一观测 value bootstrap，不伪装为 300 秒完成。RPC/时钟/关闭/已知 motion-model invalid 使 round 抛错，保存实际诊断前缀，不补造终态、GAE、成功数或训练样本。

普通导航失败可能通过 collector 的已知模型筛查，但 **完整 protocol/custody 的当前严格门仍可拒绝它**；`goal_lease_expired` 不会因是负样本而被完整链接受。V38 负回合新审计方案没有激活。任一必需读者、strict custody、实际返回码、阶段预算、源码稳定性或外部身份消失门失败，当前链停止，后继不执行；保留原 FAIL，无同活动重试。用户持续推进授权不等于可将失败删去或放松 TTL/FIFO/安全门。

validation 用同一个 final checkpoint 确定性 mask-aware 推理、零 optimizer/零参数变化。900 是采样上限：提前严格成功可少于 900；必须完成三场 schedule、全部三次真实严格成功且 `task_failures=[]`。成功仍要求 schema4、三台、正确自由覆盖≥95%、300 秒前、地图质量、三台参与、18 路零真实接触/持续新鲜监测、导航 ownership 闭合等全部原门。

## 来源链与执行前必要检查

1. 新冻结保持 seed/start 组合从 plan→三 policy argv→supervisor/worker/ROS launch→metadata/snapshot→资格/读者逐层相同；导航 candidate 为 `mr3-navigation-geometric-staging-v8-point-graph-v1`。original seed FAIL 保持真实，point attachment 单独证明，不把新模式别名给旧 v2。
2. 完整 source inventory、installed library/binary/build proof、ENV 逐字 inverse 和 immutable PPO/protocol 数学门全部保留。V39 seed certificate 字节按新 freeze 绑定，不能借旧资格；point helper 的现有静态 pin 不因该恒等优化改变。新 budget 授权记在 V40 scope，避免无必要改动已逐字绑定的环境合同正文。
3. native PPO 的独立 point 几何重建没有只停在私有 validator：`audit_reach_ppo`→`audit_reach_preparation.load_impl` 的 `exact_archives`→`audit_seed_inputs.audit_episode`，对每个实际回合执行完整 received-input snapshot 重建；原 archives、Information、activity、runtime、FIFO、物理/接触和 custody 仍合取。私有 hash/encoder validator 自身不是几何 oracle。
4. 实际 preflight 必须绑定 `mr3-reach-preflight-v1`、freeze、PLAN SHA、PASS；在同一 ns3gym 环境记录依赖/CUDA 可用性与设备身份。已只读确认本机 SB3 `get_device` 在 CUDA 不可用时会退回 CPU，因此**仅有 argv `cuda:0` 不证明真实 GPU**；前检应拒绝 CUDA 不可用，并清除从纯 CPU 活动继承的空 `CUDA_VISIBLE_DEVICES`。本审查没有执行新的硬件探测。
5. qualification 和三个 policy 阶段都要求同一 clean pushed HEAD==origin/main==freeze。**链结束/失败前不提交中途报告或修改 plan/源码**，否则即使文档 commit 也改变 freeze，后继不能沿用原资格。先封存全路径/registry，再运行，结束后统一归档提交。
6. 外层使用 `reach_execution --scope engineering/pilot/validation` 真实 wait；policy 的 `--source` 至少绑定 PLAN 与 `reach_policy_chain.py`。内层 child 命令必须 `python -m ...`，不要插 `-B`，否则现有 exact argv/proc-cmdline 门拒绝；用 `PYTHONDONTWRITEBYTECODE=1` 控制缓存。必须先等主协调器退出，再以独立调用做 qualification/finalization；协调器自身的内部 PASS 不代替外部消失证明。

建议准备端现在做的是完整 registry 的纯 CPU/static 准入验证与 source/binary/preflight 收口，然后按此链执行。没有发现需要先更改 95%、物理、任务或负回合审计规则才能尝试当前 strict native 链的合同前置条件；若当前门失败，按实际失败定位并形成下一项具体修复，不能将“持续执行”实现为无界原样重跑。

## V40冻结前费用收口修订

minimum外部finalize与资格/全链身份收口共用原300工程秒。pilot/validation各在原总CAP内显式预留300秒external_finalize_reserve_seconds，主deadline为2605.9547395464029/8700秒，内部500秒尾部保持；NATIVE_CAPS不增加，只从剩余主预算向下派生。所属finalizer真实wait计本phase，同主wait区间union及完整端点均不超过原CAP后才放后继；超额全部实扣并FAIL，不搬入工程。默认0保留旧范围，新可选配置只在新freeze使用。
