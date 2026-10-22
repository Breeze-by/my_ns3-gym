# MR3 P2A V45：准备证明稳定分类与新冻结完整链

## 实际闭合：reset FAIL，未取得完整资格或学习信用

唯一实际冻结`cace46e08e53b7e89a434e23721db85ac993f6f5`已push；driver已实际reap rc1、passed=false、completed_stages=[]。preflight已通过，V44提交前后CPU分类缺口在本轮实际准入闭合；原V44 FAIL不改判。interface及terminal通过下列全部必要工程门；reset在rooms启动/重置期间失败，因此没有完整同freeze12EP/30角色资格，deadline/minimum/pilot/validation均未启动，GPU calls=0、optimizer steps=0，无新final模型或95%任务信用。P2A仍未完成。

| 实际阶段 | 原生/审计结果 | 本轮信用与限制 |
|---|---|---|
| preflight | 实际PASS | 当前分类/源码/ELF/计划准入通过，非任务成功 |
| interface | native rc0，11/11 audit job PASS；其中9个注册必要角色，另有FIFO叶/manifest | 本冻结input/angular/physics/full/runtime/information/cadence/peer-control/closure通过 |
| terminal | native rc0，9/9 audit job PASS；其中6个注册必要角色 | 本冻结两EP终止工程门通过 |
| reset | native rc1、valid_transitions=138，8EP计划未完成，后继audits未运行 | 四个open回合各32步正常关闭；worker0 rooms返回10步，worker1 rooms reset失败 |
| deadline | SKIPPED | 前阶段失败，不能填PASS |
| qualification/minimum/pilot/validation | 未提交/SKIPPED | 完整资格未建立，0学习/0新final模型 |

独立metadata复核确认9个实际EP目录/尝试、15/30注册必要角色已完成，不能把9个尝试写成9个完整合格回合，也不能把interface11个audit job误计11注册角色。

### reset失败的分层事实与因果限制

- 第一失败记录为worker1、episode_index=2（第三回合rooms）、kind=rpc_or_worker_exception、epoch=None，错误`InfrastructureError('reset: IPC response wall guard expired')`；epoch=None是外层reset未返回的记录，不能据此推断没有真实rooms启动。
- 该rooms元数据内层错误为400秒`three-robot delivered-input startup guard expired`；外层420秒reset RPC最终超时。缺失的具体ready谓词仍需有界诊断，当前不归因到某个传感器、模型或纯CPU吞吐。
- infrastructure_cleanup.json记录invalid-sample cleanup FAIL：`native stop CLI identity missing or ambiguous`，耗时19.1034675669秒；supervisor最终worker_returncode=-9、forced_shutdown=true、failed_sample=true。原清理FAIL/强制退出保持，不能写成全程正常退出。
- worker0 rooms在途RPC结束，benchmark实际返回10步后合作停止。EP summary transition_count=11与benchmark verified-return口径不同，不能把11冒充11次已验证返回，也不据此补造样本或当前解释差异。
- 失败样本不训练；停止后的remaining_owned_processes/remaining_owned_zombies为空和最终独立freshgone只证明各自关闭范围，不追认前述cleanup CLI成功或本轮资格通过。

### 真实费用、关闭复核和后续边界

| parent实际wait | 秒数 | scope |
|---|---|---|
| preflight | 41.170046223 | engineering |
| matrix | 5622.183752015 | engineering |
| matrix_absence | 2.874983512 | engineering |
| chain_final_absence | 2.877175219 | engineering |

四parent区间union为5669.105956969秒；各native/consumer/inner wait已包含不重复记费。engineering external实际5.752158731秒已在总额中；工程累计55717.3500277646018/75000、余19282.6499722353982。pilot/validation各实际新增0，原1870决策/2905.9547395464029秒及final-only401/402/403额度保持。

独立[关闭review v2](assets/20261022_mr3_p2a_v45_preparation_classification/independent_closed_review_v2.json) PASS/review_errors=[]，activity_passed=false、independent_p2a_requirements_met=false：846源码/10ELF与Git/plan一致，433保存PID/start均freshgone（Z仍计存在）；两份外部absence PASS。该review没有重跑科学consumer或读取raw native trace，核验通过不覆盖真实reset FAIL。首轮reviewer对SKIPPED阶段的格式假设异常及[原失败回执](assets/20261022_mr3_p2a_v45_preparation_classification/independent_review_failed_v1.json)保留，v2只修metadata遍历，未改活动结果。

[规范库存](assets/20261022_mr3_p2a_v45_preparation_classification/closed_inventory_v1.json)封存3672原件、7195493305字节为589754938字节，0链接；逐文件原SHA、无损解压SHA/字节和源前后stat一致，整个成员集合稳定。现有gzip/zip按原字节保留；原件没有删除，未启动的policy目录不存在。字节归档不重判科学结果、不加载模型、工程新增0。

下一V46先在≤300工程秒新scope内定位缺失ready谓词和stopCLI身份；不直接加超时、不重试V45、不改95%/安全/source门。原20100完整资格/minimum/外尾预约已比当前余额多817.3500277646018秒，不能沿用旧scope或假称足够；后继完整链必须据真实startup/reset/审计成本另行前瞻制定可执行范围，不混冻结或删必要角色。用户自主完成P2A授权保持，P2B/gateway未开始。

## 本次唯一实际命令

cwd=canonical wireless-rl：

```text
rtk proxy env PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m report.assets.20261022_mr3_p2a_v45_preparation_classification.execute_chain_v1 --freeze cace46e08e53b7e89a434e23721db85ac993f6f5
```

实际/tmp前缀为mr3_p2a_reach_v45，native根为canonical ROS log/mr3_p2a_reach_v45；原summary/命令/失败与关闭证据保持，不覆盖原预声明或CPU回执。

## 准备期原声明（以下为运行前历史快照）

2026-10-22准备收口。用户自主持续完成P2A授权有效，不再询问一般实施批准。[V44](20261022_mr3_p2a_v44_support_native.md)实际preflight FAIL及7.010229336秒费用保留；本活动仅修准备层分类，不改变任何生产数学、执行或learner行为。P2A未完成，当前尚无V45 World/native/PPO。

## 修改边界与严格准入

[prepare_plan_v1.py](assets/20261022_mr3_p2a_v45_preparation_classification/prepare_plan_v1.py)显式纳入全部ROS `test_*.py`，使新测试提交前后分类稳定；仍逐文件核当前字节与CPU原始输入，不能用仅“都已通过”的标志替代来源等式。V44失败是提交后3条测试进入动态source_inventory导致proof分类计数变动，未证明support数学或plant失败；新分类不追认V44实际前检通过。

[classification_admission_v1.py](assets/20261022_mr3_p2a_v45_preparation_classification/classification_admission_v1.py)要求实际classification_cpu_v2的成功wait、精确pytest argv，以及prepare/preflight/cpu_driver/test/classification_admission五项源码与回执、source recovery、current逐项相等；preflight还必须将重新计算结果与plan的prospective_classification_regression完整相等，防止修复代码未经验证直接进入native。原source/ELF/custody、30必要角色、物理/安全/95%及PPO独立门全部保持。

## 人工证据及计划封存

V45复用[V44 CPU索引](assets/20261022_mr3_p2a_v44_support_native/cpu_validation_index_v1.json)中的geometry523、learner202、reader12、snapshot9共746人工检查与双环境readiness，前提是所需当前源码逐字相同；原schema、index和v44 IDs明确保留溯源。本轮未重新执行这746项，不将它们计为V45新增测试；它们不提供任何native/plant/训练信用。

| V45实际准备活动 | 结果 | child实际等待 | 回执/console |
|---|---|---|---|
| classification_cpu_v1 | 6 PASS | 5.273681813s | [wait](assets/20261022_mr3_p2a_v45_preparation_classification/checks/classification_cpu_v1/actual_wait.json) / [console](assets/20261022_mr3_p2a_v45_preparation_classification/checks/classification_cpu_v1/console.log) |
| classification_cpu_v2 | 严格准入源加入后同6项重验PASS，非新增6项 | 5.099110667s | [wait](assets/20261022_mr3_p2a_v45_preparation_classification/checks/classification_cpu_v2/actual_wait.json) / [console](assets/20261022_mr3_p2a_v45_preparation_classification/checks/classification_cpu_v2/console.log) |
| prepare_plan_cpu_v1 | 846 source/10 ELF/3 policy封存PASS | 2.33828766s | [wait](assets/20261022_mr3_p2a_v45_preparation_classification/checks/prepare_plan_cpu_v1/actual_wait.json) / [console](assets/20261022_mr3_p2a_v45_preparation_classification/checks/prepare_plan_cpu_v1/console.log) |
| plan_check_cpu_v1 | 四native stage/12EP/30必要角色/三policy PASS | 0.360798041s | [wait](assets/20261022_mr3_p2a_v45_preparation_classification/checks/plan_check_cpu_v1/actual_wait.json) / [console](assets/20261022_mr3_p2a_v45_preparation_classification/checks/plan_check_cpu_v1/console.log) |

四次均实际reap rc0、source_unchanged=true；准备proof分类计数271、classification_passed=true，846项source实际hash复核无漂移，工程费0；[source recovery/快照](assets/20261022_mr3_p2a_v45_preparation_classification/checks)保留对应测试源码。生产support及独立重放helper未变，`reach_geometry_rule=cone-support-v2`继续与seedv2/point-graph显式贯穿所有原生与policy入口，默认binary-cone-v1保持。

| 封存输入 | 字节数 | SHA256 |
|---|---|---|
| [plan_v1.json](assets/20261022_mr3_p2a_v45_preparation_classification/plan_v1.json) | 232809 | `0964c074510e0601d23b33b5493e71e6dd95e945adb24dda621649d76f1bd8b5` |
| [native_custody_binding_v1.json](assets/20261022_mr3_p2a_v45_preparation_classification/native_custody_binding_v1.json) | 131832 | `cd71046df7d14c2cff3f8843854b611f136b51e8e395fd4c6428cafaa0bb8aab` |

## 一次新活动与费用边界

[scope](assets/20261022_mr3_p2a_v45_preparation_classification/scope_v1.json)与[预算](assets/20261022_mr3_p2a_v45_preparation_classification/budget_acceptance_v1.json)以工程入场50048.2440707956018/75000、余24951.7559292043982为准。完整资格18000＋工程外尾300＋minimum1800＝20100，准备/有限取证另800，总预约20900，未预约余4051.7559292043982。只记完整parent实际wait区间union，嵌套费用不叠加；失败同样计费和封存。

新freeze同四stage/12EP/30必要角色完整native资格及关闭核验通过后才minimum；minimum需16合格样本/正更新才可pilot，pilot取得合格final.zip后才final-only open401/402/403。pilot仍限1870决策/2905.9547395464029秒，validation900决策/9000秒，每场严格95%/质量/参与/0接触及全部独立安全门保持。pilot/final外尾300分别在原各自CAP内保留，不转记工程；无模型时validation必须SKIPPED，不补样/重试原活动。

## 运行前预声明入口（历史；本轮已按顶部精确freeze实际执行）

cwd=canonical wireless-rl；EXACT40须替换为本活动实现、计划、必要检查完成并push后的新40位冻结SHA，链闭合前不改绑定源/plan或中途commit。

```text
rtk proxy env PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m report.assets.20261022_mr3_p2a_v45_preparation_classification.execute_chain_v1 --freeze EXACT40
```

这是新活动预声明，不是V44重试或失败改判；人工准备通过仍须实际post-freeze preflight。P2A未完成，P2B/gateway未开始。

[独立入场静态审查](assets/20261022_mr3_p2a_v45_preparation_classification/independent_entry_review_v1.json)PASS、blocking=[]；核846源/10ELF、271稳定分类、实际回归准入和完整角色/费用。该审查没有执行新原生活动。
