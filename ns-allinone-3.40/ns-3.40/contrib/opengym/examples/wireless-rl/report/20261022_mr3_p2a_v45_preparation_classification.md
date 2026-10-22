# MR3 P2A V45：准备证明稳定分类与新冻结完整链

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

## 下一步实际入口（尚未执行）

cwd=canonical wireless-rl；EXACT40须替换为本活动实现、计划、必要检查完成并push后的新40位冻结SHA，链闭合前不改绑定源/plan或中途commit。

```text
rtk proxy env PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m report.assets.20261022_mr3_p2a_v45_preparation_classification.execute_chain_v1 --freeze EXACT40
```

这是新活动预声明，不是V44重试或失败改判；人工准备通过仍须实际post-freeze preflight。P2A未完成，P2B/gateway未开始。

[独立入场静态审查](assets/20261022_mr3_p2a_v45_preparation_classification/independent_entry_review_v1.json)PASS、blocking=[]；核846源/10ELF、271稳定分类、实际回归准入和完整角色/费用。该审查没有执行新原生活动。
