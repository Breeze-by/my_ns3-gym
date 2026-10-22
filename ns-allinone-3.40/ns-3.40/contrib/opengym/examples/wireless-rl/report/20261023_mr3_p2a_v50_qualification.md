# MR3 P2A V50：完整资格链的reset失败与闭合

## 闭合结果：FAIL，未取得完整资格

唯一冻结 `23e909380b470039bd5680cf2d07710dca71097e` 的整链已真实退出 rc1，所有已提交子进程均实际等待。共 **11实际EP/296原生返回；30必要角色18PASS、2FAIL、10SKIPPED**。deadline、minimum、pilot、final均未提交；本轮0 GPU/optimizer更新、无新模型或95%验证信用。P2A未完成，P2B/gateway不启动。

| 阶段 | 实际结果 |
|---|---|
| interface | 1EP/32返回，9必要角色PASS，阶段2032.384042887秒 |
| terminal | 2EP/8返回，6必要角色PASS，阶段758.807755841秒 |
| reset native | 8EP/256返回、rc0，native4557.609774705秒 |
| reset input/runtime/full | input八叶均PASS；runtime2624.727991544秒PASS；full6342.154525786秒PASS |
| reset angular/physics | 两必要角色FAIL，旧reset workload/probe入口不匹配 |
| reset information/cadence/peer_control/closure | 四必要角色SKIPPED |
| deadline | 六必要角色SKIPPED |

angular原错误为 `benchmark: ValueError('not the exact declared reset workload')`；八份sampled bounds均通过仍不能升格整体PASS。旧入口要求 `mr3-p2a0-outward-cancel-v6`，冻结实际probe为 `mr3-p2a-reach-outward-cancel-v1`。physics原错误为 `ValueError('aggregate requires only the predeclared same-freeze two-worker reset matrix')`，在aggregate数学前拒绝。修复后的reader不能追认本轮FAIL。

可选 `physical_per_episode` 另有6PASS/2FAIL：两份corridors tb3缺合格hard-zero/cancel停止证据。它不是30必要role之一；errors空及closure=True不构成完整physics PASS，该缺口独立保留。

reset完整阶段 **11302.772605716 > 最终effective cap6301.463804643秒**，资源门也FAIL。较早native准入时的6289.815418144不是最终stage cap。matrix内部总墙秒14108.562100044仍在16000以内，不能冲销阶段超额或倒借未执行deadline额度。已提交长reader真实排空，未通过截断隐藏费用。

## 末账、来源和原件

| 完整parent区间 | 工程秒 |
|---|---:|
| preflight |44.276388611|
| matrix |14109.941355542|
| matrix_absence |3.958494258|
| chain_final_absence |3.992724932|
| 同scope区间union |**14162.168963343**|

工程累计 **70121.7738945746018/75000**，余 **4878.2261054253982**。nested native/full/runtime不重复相加；工程外尾7.951219190已含于union。pilot/final各+0，原余1870决策/2905.9547395464029秒与三open401/402/403、900决策/9000秒保持。

[driver原summary](assets/20261023_mr3_p2a_v50_qualification/closed_execution/tmp/mr3_p2a_reach_v50_driver_v1/summary.json)、[matrix原summary](assets/20261023_mr3_p2a_v50_qualification/closed_execution/tmp/mr3_p2a_reach_v50_matrix/summary.json) 和各实际wait/ledger完整封存。最外工具shell argv/env未写入entry/summary，当前材料不能独立恢复其完整原文，明确留此记录，不补造；各实际子阶段完整argv及冻结driver入口均在原回执。matrix实际argv为：

```text
/home/zhuyulab/miniconda3/envs/ns3gym/bin/python -m mr3_learning.reach_preparation --plan /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261023_mr3_p2a_v50_qualification/plan_v1.json --freeze 23e909380b470039bd5680cf2d07710dca71097e
```

两份外部absence原报告各538身份/514 input bindings PASS；随后[独立闭合review v4](assets/20261023_mr3_p2a_v50_qualification/closed_execution/closure_tools/mr3_p2a_v50_independent_closed_review_v4.json)实际PASS：**911源/10ELF一致、545保存PID/start pair freshgone，Z仍计present**。475个distinct PID涉及原canonical PID-only occurrence；原缺same-object-start位置仍保留，global unbound=[]仅表示另有原保存pair提供全局inventory coverage，不能跨对象补start或为原缺失行伪造gone。review不重算科学资格，不重消费原absence所有其他console。

[10项人工closure自检](assets/20261023_mr3_p2a_v50_qualification/checks/closure_v4/mr3_p2a_v50_closure_selfcheck_execution_v4.json)实际PASS、源前后相等。未执行的v1/v2/v3草稿及其已识别静态缺口均保留；工具元数据PASS不改科学FAIL。只读bookkeeping中的文件写入竞争、容器/路径假设错误与idle-agent派发失误均不改原结果、未创建新World或虚报实验费。

[规范库存](assets/20261023_mr3_p2a_v50_qualification/closed_inventory_v1.json)完整：**5070文件、10224871773原字节 → 855260558封存字节、0软链**，inventory SHA `4459f8f76c4ba59dc89d819a3647ddaa6cfa56170aa0d5e999e6c5fcba25afb7`。每个新增gzip反解SHA/size等于原字节，已有压缩原件逐字保存，源stat/成员集保持；原件未删。[封存后字节复核](assets/20261023_mr3_p2a_v50_qualification/closed_archive_review_v1.json)独立重哈希全部encoded文件和完整成员集。无损包装不授科学信用。

## 后继执行

先按[新V51范围](20261023_mr3_p2a_v51_runtime_profile.md)对固定已闭合单EP做一次有界runtime profile，保留24份实际旧source proof字节，定位长reader成本。选择先测后改以隔离测量；`reach_audit_projection.py`本身不在这24源集合内，不能把该helper的所有修改一概说成必破旧runtime proof。

随后显式登记Reach reset angular/physics入口，核immutable旧源/whole-source inverse及真实双reader入口，先人工正反例CPU，再恒等性能优化与新freeze完整资格。原停车证据缺口、版本接线和阶段成本分别处理。不得跨freeze拼18个PASS补齐资格，不降低95%/安全/源龄/FIFO/TTL或沿用不可负担旧预约。

用户已委托持续完成P2A、不再一般审批；后续必要工程块应依据实测作前瞻有界决策，明确是代理在该委托下的规划，不能伪称用户逐数值批准，也不清零旧累计账或自动扩大pilot/final额度。最终仍须实际eligible正更新、同一pilot final.zip、三指定final-only回合全部strict95及完整独立冻结/关闭证据。地图覆盖95%不是95%成功概率。

## 原预声明（冻结前快照，保留原文）

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
