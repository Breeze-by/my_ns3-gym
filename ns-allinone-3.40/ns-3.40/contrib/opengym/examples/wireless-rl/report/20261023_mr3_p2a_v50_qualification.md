# MR3 P2A V50：完整资格与真实学习链

准备完成，尚未启动本版本 World/native/PPO。V49 的两回合启动 PASS 及所有旧 FAIL 保留，不能填充本次完整资格。用户已授权自主持续完成 P2A；P2B/gateway 不启动。

本版本只新增 PPO 的永久故障准入保护：当前 epoch 的 `motion_safety` / `mr3-reach-runtime-fault-v1` 无论具体 reason 均在构造 targets/训练前拒绝；错/缺 epoch 是坏回执，也不能准入。三个旧 reason literal 保留，正常导航/接触任务失败仍可作为负样本。新人工用例验证全部环境关闭后拒绝整轮、targets 与 train 未调用。实际 [fresh CPU](assets/20261023_mr3_p2a_v50_qualification/checks/ppo_fault_cpu_v1/actual_wait.json) 47项 PASS；新编排分类/实际模块 help 8项 PASS，双环境导入、计划生成、计划校验均 PASS。见 [索引](assets/20261023_mr3_p2a_v50_qualification/cpu_validation_index_v1.json)。V49 其余 CPU 仅按当前源相等复用，旧 PPO 字节不供新行为信用。新 CPU 不供 native 或学习信用。

工程入场 **55959.6049312316018/75000**，余 **19040.3950687683982**。采用显式 `bounded-original-workload-v1`，只缩紧资源预约，保留完整工作量与全部门。

| 工程项目 | 预约墙秒 |
|---|---:|
| 完整资格 matrix | 16000 |
| 新 seed41 minimum，16 eligible 决策与正更新、完整审计 | 1800 |
| 外部关闭、资格和工程收口 | 300 |
| 实际 preflight | 120 |
| 合计 | **18220** |

四阶段 base2300/1000/5800/6900，native base1800/750/4800/5900；close120、原 forward-carry、未提交后续阶段保留规则不变。仍是 interface/open101×32、terminal/open101两回合×4、reset/两worker各open101/open101/rooms101/corridors101×32、deadline/open101×300，共 **12EP/30必要角色**。所有真 return、模型/源龄/时钟、18接触流、原生身份/关闭与独立 reader 门保留。超时会完整收费并 FAIL；预约不是 OS 硬终止或吞吐保证。

[封存计划](assets/20261023_mr3_p2a_v50_qualification/plan_v1.json) SHA `ac5e6d4e6fabadb37ac9d8336cfeaa00ec7401b956fb2cab9842ae410ccb206e`，911份源/准备输入、10个实际 ELF，三 policy 阶段均登记，实际执行前须同一新 commit/push freeze。

只有完整新资格与工程余额准入通过才启动 minimum。只有 minimum 真正16 eligible/正参数更新及完整审计通过才启动 pilot。pilot 从头训练、不复用 minimum/旧模型；**请求上限64决策**、workers2、首轮每环境 cap32，原 episode max64/batch64/epochs4/native2100和总2905.9547395464029秒保持。任务提前终止可开后续轮，墙钟收口也可能得到较少样本，只有真实关闭的 eligible 样本与正参数更新才计；不承诺刚好2EP或64样本。选择64是在原1870余额内争取更多实际经验，V49两首步并不证明长步成本或充分学习。

只有完整 pilot 与 final.zip 成功才使用该同一 checkpoint/固定权重及归一化做 open401/402/403 三个 final-only 回合，0验证更新，全部 strict95%/质量/安全/参与/终态门必须通过。final余额仍900决策/9000秒，pilot/final外部300分别计入各自原总额；不把费用挪入工程。全部 required failure 均停止后继，排空已提交工作、保留失败并检查保存身份。工程阶段 PASS、最小学习 PASS 或 driver PASS 都不能代替真正 P2A 出口。

静态 [policy entry review](assets/20261023_mr3_p2a_v50_qualification/independent_policy_entry_review_v1.json) 无阻断；[最终独立封存review v2](assets/20261023_mr3_p2a_v50_qualification/independent_sealed_plan_review_v2.json) PASS，无阻断：983份选定输入结束SHA复查、911当前源/10ELF及compiled/build/CPU恢复链均一致。首稿把原有reset `physical_per_episode` 的role=None/required=False描述附加审计误当必要role，已保留[v1原件](assets/20261023_mr3_p2a_v50_qualification/independent_sealed_plan_review_v1.json)及失败副本；v2独立核30个真正role全required=True，与V45同一可选描述项一致，没有放宽计划或门。该首稿不是native科学FAIL。计划校验首次工具调用因错误 cwd 未创建进程，已单独[如实记录](assets/20261023_mr3_p2a_v50_qualification/checks/plan_check_tool_launch_error_v0.json)，随后正确 cwd 的唯一实际校验 PASS，不伪造失败等待回执或删除记录。当前无新工程费用，P2A 未完成。
